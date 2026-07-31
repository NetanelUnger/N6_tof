#include "xmodem_receiver.h"

#include <string.h>

#define XMODEM_SOH                 (0x01U)
#define XMODEM_STX                 (0x02U)
#define XMODEM_EOT                 (0x04U)
#define XMODEM_ACK                 (0x06U)
#define XMODEM_NAK                 (0x15U)
#define XMODEM_CAN                 (0x18U)
#define XMODEM_CRC_REQUEST         (0x43U)
#define XMODEM_BLOCK_128           (128U)
#define XMODEM_BLOCK_1K            (1024U)
#define XMODEM_REQUEST_PERIOD_MS   (1000U)
#define XMODEM_PACKET_TIMEOUT_MS   (10000U)
#define XMODEM_MAX_REQUESTS        (16U)
#define XMODEM_MAX_ERRORS          (10U)

static uint16_t xmodem_crc16(const uint8_t *data, size_t length)
{
  uint16_t crc = 0U;

  while (length-- != 0U)
  {
    crc ^= (uint16_t)((uint16_t)*data++ << 8U);
    for (uint32_t bit = 0U; bit < 8U; ++bit)
    {
      crc = ((crc & 0x8000U) != 0U) ?
            (uint16_t)((crc << 1U) ^ 0x1021U) :
            (uint16_t)(crc << 1U);
    }
  }
  return crc;
}

static int32_t xmodem_send(XMODEM_Receiver_t *receiver, uint8_t byte)
{
  if ((receiver->callbacks.send_byte == NULL) ||
      (receiver->callbacks.send_byte(byte,
                                     receiver->callbacks.context) != 0))
  {
    XMODEM_Cancel(receiver, -10);
    return -1;
  }
  return 0;
}

static void xmodem_reject_packet(XMODEM_Receiver_t *receiver)
{
  receiver->packet_length = 0U;
  receiver->packet_expected = 0U;
  receiver->packet_data_length = 0U;
  receiver->error_count++;
  if (receiver->error_count > XMODEM_MAX_ERRORS)
  {
    XMODEM_Cancel(receiver, -11);
  }
  else
  {
    (void)xmodem_send(receiver, XMODEM_NAK);
  }
}

static void xmodem_complete_packet(XMODEM_Receiver_t *receiver)
{
  uint8_t sequence = receiver->packet[0];
  uint8_t complement = receiver->packet[1];
  const uint8_t *payload = &receiver->packet[2];
  uint16_t received_crc =
      (uint16_t)(((uint16_t)receiver->packet[2U +
                                             receiver->packet_data_length]
                  << 8U) |
                 receiver->packet[3U + receiver->packet_data_length]);

  if (((uint8_t)(sequence + complement) != 0xFFU) ||
      (xmodem_crc16(payload, receiver->packet_data_length) != received_crc))
  {
    xmodem_reject_packet(receiver);
    return;
  }

  if (sequence == receiver->expected_sequence)
  {
    if ((receiver->callbacks.consume == NULL) ||
        (receiver->callbacks.consume(payload,
                                     receiver->packet_data_length,
                                     receiver->callbacks.context) != 0))
    {
      XMODEM_Cancel(receiver, -12);
      return;
    }
    receiver->expected_sequence++;
    receiver->transfer_started = 1U;
    receiver->request_count = 0U;
    receiver->error_count = 0U;
    (void)xmodem_send(receiver, XMODEM_ACK);
  }
  else if (sequence == (uint8_t)(receiver->expected_sequence - 1U))
  {
    /* ACK a retransmitted block without delivering it twice. */
    (void)xmodem_send(receiver, XMODEM_ACK);
  }
  else
  {
    xmodem_reject_packet(receiver);
    return;
  }

  receiver->packet_length = 0U;
  receiver->packet_expected = 0U;
  receiver->packet_data_length = 0U;
}

int32_t XMODEM_Start(XMODEM_Receiver_t *receiver,
                     const XMODEM_Callbacks_t *callbacks,
                     uint32_t now_ms)
{
  if ((receiver == NULL) || (callbacks == NULL) ||
      (callbacks->send_byte == NULL) || (callbacks->consume == NULL) ||
      (callbacks->finish == NULL))
  {
    return -1;
  }

  (void)memset(receiver, 0, sizeof(*receiver));
  receiver->callbacks = *callbacks;
  receiver->expected_sequence = 1U;
  receiver->active = 1U;
  receiver->last_activity_ms = now_ms;
  receiver->last_request_ms = now_ms;
  receiver->request_count = 1U;
  return xmodem_send(receiver, XMODEM_CRC_REQUEST);
}

void XMODEM_Process(XMODEM_Receiver_t *receiver, const uint8_t *data,
                    size_t length, uint32_t now_ms)
{
  if ((receiver == NULL) || (data == NULL) ||
      (receiver->active == 0U))
  {
    return;
  }

  while ((length-- != 0U) && (receiver->active != 0U))
  {
    uint8_t byte = *data++;
    receiver->last_activity_ms = now_ms;

    if (receiver->packet_expected != 0U)
    {
      receiver->packet[receiver->packet_length++] = byte;
      if (receiver->packet_length == receiver->packet_expected)
      {
        xmodem_complete_packet(receiver);
      }
      continue;
    }

    if ((byte == XMODEM_SOH) || (byte == XMODEM_STX))
    {
      receiver->packet_data_length = (byte == XMODEM_SOH) ?
                                     XMODEM_BLOCK_128 : XMODEM_BLOCK_1K;
      receiver->packet_expected = receiver->packet_data_length + 4U;
      receiver->packet_length = 0U;
      receiver->cancel_count = 0U;
    }
    else if (byte == XMODEM_EOT)
    {
      if (receiver->callbacks.finish(receiver->callbacks.context) == 0)
      {
        (void)xmodem_send(receiver, XMODEM_ACK);
        receiver->active = 0U;
      }
      else
      {
        XMODEM_Cancel(receiver, -13);
      }
    }
    else if (byte == XMODEM_CAN)
    {
      receiver->cancel_count++;
      if (receiver->cancel_count >= 2U)
      {
        XMODEM_Cancel(receiver, -14);
      }
    }
    else
    {
      receiver->cancel_count = 0U;
    }
  }
}

void XMODEM_Poll(XMODEM_Receiver_t *receiver, uint32_t now_ms)
{
  if ((receiver == NULL) || (receiver->active == 0U))
  {
    return;
  }

  if (receiver->packet_expected != 0U)
  {
    if ((uint32_t)(now_ms - receiver->last_activity_ms) >=
        XMODEM_PACKET_TIMEOUT_MS)
    {
      xmodem_reject_packet(receiver);
      receiver->last_activity_ms = now_ms;
    }
  }
  else if (receiver->transfer_started == 0U)
  {
    if ((uint32_t)(now_ms - receiver->last_request_ms) >=
        XMODEM_REQUEST_PERIOD_MS)
    {
      if (receiver->request_count >= XMODEM_MAX_REQUESTS)
      {
        XMODEM_Cancel(receiver, -15);
      }
      else
      {
        receiver->request_count++;
        receiver->last_request_ms = now_ms;
        (void)xmodem_send(receiver, XMODEM_CRC_REQUEST);
      }
    }
  }
  else if ((uint32_t)(now_ms - receiver->last_activity_ms) >=
           XMODEM_PACKET_TIMEOUT_MS)
  {
    receiver->error_count++;
    receiver->last_activity_ms = now_ms;
    if (receiver->error_count > XMODEM_MAX_ERRORS)
    {
      XMODEM_Cancel(receiver, -16);
    }
    else
    {
      (void)xmodem_send(receiver, XMODEM_NAK);
    }
  }
}

void XMODEM_Cancel(XMODEM_Receiver_t *receiver, int32_t reason)
{
  XMODEM_Abort_t abort_callback;
  void *callback_context;

  if ((receiver == NULL) || (receiver->active == 0U))
  {
    return;
  }

  abort_callback = receiver->callbacks.abort;
  callback_context = receiver->callbacks.context;
  receiver->active = 0U;
  if (receiver->callbacks.send_byte != NULL)
  {
    (void)receiver->callbacks.send_byte(XMODEM_CAN, callback_context);
    (void)receiver->callbacks.send_byte(XMODEM_CAN, callback_context);
  }
  if (abort_callback != NULL)
  {
    abort_callback(reason, callback_context);
  }
}

uint32_t XMODEM_IsActive(const XMODEM_Receiver_t *receiver)
{
  return ((receiver != NULL) && (receiver->active != 0U)) ? 1U : 0U;
}
