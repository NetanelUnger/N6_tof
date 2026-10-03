#ifndef DEBUG_UART_H
#define DEBUG_UART_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define DEBUG_UART_BAUDRATE  (115200U)

#define DEBUG_UART_TEST_NONE      (0U)
#define DEBUG_UART_TEST_BURST     (1U)
#define DEBUG_UART_TEST_OVERFLOW  (2U)

typedef struct
{
  uint32_t initialized;
  uint32_t queued_messages;
  uint32_t sent_messages;
  uint32_t dropped_messages;
  uint32_t queue_full_events;
  uint32_t pool_exhaustions;
  uint32_t producer_contentions;
  uint32_t oversize_rejections;
  uint32_t context_rejections;
  uint32_t transport_failures;
  uint32_t internal_errors;
  uint32_t tx_timeouts;
  uint32_t hal_errors;
  uint32_t slots_in_use;
  uint32_t slot_capacity;
  uint32_t queue_high_water;
  uint32_t rx_overruns;
  uint32_t rx_errors;
  uint32_t watch_component;
  uint32_t task_stack_bytes;
  uint32_t task_stack_min_free_bytes;
  uint32_t test_running;
  uint32_t test_kind;
  uint32_t test_run_id;
  uint32_t test_completed_runs;
  uint32_t test_attempted;
  uint32_t test_queued_delta;
  uint32_t test_sent_delta;
  uint32_t test_dropped_delta;
  uint32_t test_queue_full_delta;
  uint32_t test_pool_exhaustion_delta;
  uint32_t test_contention_delta;
  uint32_t test_oversize_delta;
  uint32_t test_timeout_delta;
  uint32_t test_hal_error_delta;
  int32_t test_flush_status;
} DebugUart_Status_t;

int32_t Debug_UART_Init(void);
int32_t Debug_UART_AsyncInitialize(void);
void Debug_UART_TaskRun(void);
void Debug_UART_TestTaskRun(void);
int32_t Debug_UART_StartTest(uint32_t test_kind, uint32_t *run_id);
int32_t Debug_UART_Write(const void *buffer, size_t length);
int32_t Debug_UART_Flush(uint32_t timeout_ms);
void Debug_UART_GetStatus(DebugUart_Status_t *status);
int32_t Debug_UART_EmergencyWrite(const void *buffer, size_t length);
void Debug_UART_IRQHandler(void);
void Debug_UART_Log(const char *component, const char *format, ...);
uint32_t Debug_UART_GetDroppedMessages(void);
uint32_t Debug_UART_NcpTraceEnabled(void);
void Debug_UART_NcpTrace(const char *direction, const uint8_t *data,
                         size_t length, int32_t transport_result);
void Debug_UART_NcpTracePing(const char *stage, const uint8_t *data,
                             size_t length);
void Debug_UART_NcpTracePingFrame(const char *stage, const uint8_t *data,
                                  size_t length);

/* These two functions do not use HAL state or initialized RAM.  They are safe
 * to call directly from Reset_Handler before .data/.bss initialization. */
void Debug_UART_StartupTrace(uint32_t stage);
void Debug_UART_StartupFault(uint32_t fault_code);

#ifdef __cplusplus
}
#endif

#endif /* DEBUG_UART_H */
