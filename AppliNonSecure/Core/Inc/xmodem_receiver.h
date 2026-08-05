#ifndef XMODEM_RECEIVER_H
#define XMODEM_RECEIVER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef int32_t (*XMODEM_SendByte_t)(uint8_t byte, void *context);
typedef int32_t (*XMODEM_Consume_t)(const uint8_t *data, size_t length,
                                   void *context);
typedef int32_t (*XMODEM_Finish_t)(void *context);
typedef void (*XMODEM_Abort_t)(int32_t reason, void *context);

typedef struct
{
  XMODEM_SendByte_t send_byte;
  XMODEM_Consume_t consume;
  XMODEM_Finish_t finish;
  XMODEM_Abort_t abort;
  void *context;
} XMODEM_Callbacks_t;

typedef struct
{
  XMODEM_Callbacks_t callbacks;
  uint8_t packet[1028];
  uint32_t packet_length;
  uint32_t packet_expected;
  uint32_t packet_data_length;
  uint32_t last_activity_ms;
  uint32_t last_request_ms;
  uint32_t request_count;
  uint32_t error_count;
  uint32_t raw_byte_count;
  uint32_t accepted_block_count;
  uint8_t expected_sequence;
  uint8_t active;
  uint8_t transfer_started;
  uint8_t cancel_count;
} XMODEM_Receiver_t;

int32_t XMODEM_Start(XMODEM_Receiver_t *receiver,
                     const XMODEM_Callbacks_t *callbacks,
                     uint32_t now_ms);
void XMODEM_Process(XMODEM_Receiver_t *receiver, const uint8_t *data,
                    size_t length, uint32_t now_ms);
void XMODEM_Poll(XMODEM_Receiver_t *receiver, uint32_t now_ms);
void XMODEM_Cancel(XMODEM_Receiver_t *receiver, int32_t reason);
uint32_t XMODEM_IsActive(const XMODEM_Receiver_t *receiver);

#ifdef __cplusplus
}
#endif

#endif /* XMODEM_RECEIVER_H */
