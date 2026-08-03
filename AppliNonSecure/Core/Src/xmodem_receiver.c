#include "xmodem_receiver.h"

#include <string.h>

#include "debug_uart.h"

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
#define XMODEM_MAX_REQUESTS        (120U)
#define XMODEM_MAX_ERRORS          (10U)
#define XMODEM_RAW_TRACE_BYTES     (20U)

static uint32_t xmodem_trace_current_block(
    const XMODEM_Receiver_t *receiver)
{
  uint32_t block_number = receiver->accepted_block_count + 1U;

  return ((block_number <= 2U) || ((block_number % 64U) == 0U)) ? 1U : 0U;
}

static void xmodem_trace_raw_byte(const XMODEM_Receiver_t *receiver,
                                  uint8_t byte)
{
  uint32_t raw_offset = receiver->raw_byte_count;

  if (raw_offset >= XMODEM_RAW_TRACE_BYTES)
  {
    return;
  }

  if (receiver->packet_expected == 0U)
  {
    const char *action = "ignored while waiting for SOH/STX/EOT/CAN";

    if (byte == XMODEM_SOH)
    {
      action = "SOH: start a 128-byte XMODEM block";
    }
    else if (byte == XMODEM_STX)
    {
      action = "STX: start a 1024-byte XMODEM block";
    }
    else if (byte == XMODEM_EOT)
    {
      action = "EOT: finalize the authenticated package";
    }
    else if (byte == XMODEM_CAN)
    {
      action = "CAN: count sender cancellation byte";
    }

    Debug_UART_Log("XMODEM", "RX raw[%lu]=0x%02X -> %s",
                   (unsigned long)raw_offset, (unsigned int)byte, action);
  }
  else if (receiver->packet_length == 0U)
  {
    Debug_UART_Log("XMODEM", "RX raw[%lu]=0x%02X -> block sequence",
                   (unsigned long)raw_offset, (unsigned int)byte);
  }
  else if (receiver->packet_length == 1U)
  {
    Debug_UART_Log("XMODEM",
                   "RX raw[%lu]=0x%02X -> sequence complement",
                   (unsigned long)raw_offset, (unsigned int)byte);
  }
  else
  {
    uint32_t payload_offset = receiver->packet_length - 2U;

    Debug_UART_Log(
        "XMODEM",
        "RX raw[%lu]=0x%02X -> payload[%lu], buffered until CRC passes",
        (unsigned long)raw_offset, (unsigned int)byte,
        (unsigned long)payload_offset);
  }
}

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
  if ((byte == XMODEM_CRC_REQUEST) &&
      ((receiver->request_count <= 3U) ||
       ((receiver->request_count % 10U) == 0U)))
  {
    Debug_UART_Log("XMODEM", "TX 'C' CRC request #%lu",
                   (unsigned long)receiver->request_count);
  }
  else if ((byte == XMODEM_ACK) &&
           ((receiver->accepted_block_count <= 2U) ||
            ((receiver->accepted_block_count % 64U) == 0U)))
  {
    Debug_UART_Log("XMODEM", "TX ACK after accepted block #%lu",
                   (unsigned long)receiver->accepted_block_count);
  }
  else if (byte == XMODEM_NAK)
  {
    Debug_UART_Log("XMODEM", "TX NAK; errors=%lu",
                   (unsigned long)receiver->error_count);
  }

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
  Debug_UART_Log("XMODEM",
                 "rejecting packet; collected=%lu expected=%lu errors=%lu",
                 (unsigned long)receiver->packet_length,
                 (unsigned long)receiver->packet_expected,
                 (unsigned long)(receiver->error_count + 1U));
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
  uint16_t calculated_crc = xmodem_crc16(payload,
                                          receiver->packet_data_length);
  uint16_t received_crc =
      (uint16_t)(((uint16_t)receiver->packet[2U +
                                             receiver->packet_data_length]
                  << 8U) |
                 receiver->packet[3U + receiver->packet_data_length]);

  if (xmodem_trace_current_block(receiver) != 0U)
  {
    Debug_UART_Log(
        "XMODEM",
        "packet complete: seq=%u complement=0x%02X payload=%lu CRC rx=0x%04X calc=0x%04X",
        (unsigned int)sequence, (unsigned int)complement,
        (unsigned long)receiver->packet_data_length,
        (unsigned int)received_crc, (unsigned int)calculated_crc);
  }

  if (((uint8_t)(sequence + complement) != 0xFFU) ||
      (calculated_crc != received_crc))
  {
    Debug_UART_Log(
        "XMODEM",
        "packet validation failed: seq-sum=0x%02X CRC-match=%lu",
        (unsigned int)((uint8_t)(sequence + complement)),
        (unsigned long)((calculated_crc == received_crc) ? 1U : 0U));
    xmodem_reject_packet(receiver);
    return;
  }

  if (sequence == receiver->expected_sequence)
  {
    int32_t consume_status;

    if (xmodem_trace_current_block(receiver) != 0U)
    {
      Debug_UART_Log("XMODEM",
                     "delivering block #%lu seq=%u to update consumer",
                     (unsigned long)(receiver->accepted_block_count + 1U),
                     (unsigned int)sequence);
    }
    consume_status = (receiver->callbacks.consume == NULL) ? -1 :
        receiver->callbacks.consume(payload, receiver->packet_data_length,
                                    receiver->callbacks.context);
    if (consume_status != 0)
    {
      Debug_UART_Log("XMODEM",
                     "update consumer rejected block #%lu: status=%ld",
                     (unsigned long)(receiver->accepted_block_count + 1U),
                     (long)consume_status);
      XMODEM_Cancel(receiver, -12);
      return;
    }
    receiver->accepted_block_count++;
    if ((receiver->accepted_block_count <= 2U) ||
        ((receiver->accepted_block_count % 64U) == 0U))
    {
      Debug_UART_Log("XMODEM", "consumer accepted block #%lu",
                     (unsigned long)receiver->accepted_block_count);
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
    Debug_UART_Log("XMODEM", "duplicate seq=%u; ACK without redelivery",
                   (unsigned int)sequence);
    (void)xmodem_send(receiver, XMODEM_ACK);
  }
  else
  {
    Debug_UART_Log("XMODEM", "unexpected seq=%u; expected=%u",
                   (unsigned int)sequence,
                   (unsigned int)receiver->expected_sequence);
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
    xmodem_trace_raw_byte(receiver, byte);
    receiver->raw_byte_count++;

    if (receiver->packet_expected != 0U)
    {
      receiver->packet[receiver->packet_length++] = byte;
      if ((xmodem_trace_current_block(receiver) != 0U) &&
          (receiver->packet_length == 2U))
      {
        Debug_UART_Log("XMODEM",
                       "header buffered: seq=%u complement=0x%02X expected-seq=%u",
                       (unsigned int)receiver->packet[0],
                       (unsigned int)receiver->packet[1],
                       (unsigned int)receiver->expected_sequence);
      }
      else if ((xmodem_trace_current_block(receiver) != 0U) &&
               (receiver->packet_length ==
                (receiver->packet_data_length + 2U)))
      {
        Debug_UART_Log("XMODEM",
                       "payload buffered (%lu bytes); awaiting two CRC bytes",
                       (unsigned long)receiver->packet_data_length);
      }
      else if ((xmodem_trace_current_block(receiver) != 0U) &&
               (receiver->packet_length ==
                (receiver->packet_data_length + 3U)))
      {
        Debug_UART_Log("XMODEM", "CRC high byte buffered: 0x%02X",
                       (unsigned int)byte);
      }
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
      if (xmodem_trace_current_block(receiver) != 0U)
      {
        Debug_UART_Log("XMODEM",
                       "block start accepted: data=%lu packet-tail=%lu bytes",
                       (unsigned long)receiver->packet_data_length,
                       (unsigned long)receiver->packet_expected);
      }
    }
    else if (byte == XMODEM_EOT)
    {
      Debug_UART_Log("XMODEM", "EOT received after %lu accepted blocks",
                     (unsigned long)receiver->accepted_block_count);
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
      Debug_UART_Log("XMODEM", "CAN received (%u/2)",
                     (unsigned int)receiver->cancel_count);
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
      Debug_UART_Log("XMODEM",
                     "packet timeout: collected=%lu of %lu tail bytes",
                     (unsigned long)receiver->packet_length,
                     (unsigned long)receiver->packet_expected);
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
    Debug_UART_Log("XMODEM", "TX CAN CAN; cancelling reason=%ld",
                   (long)reason);
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
