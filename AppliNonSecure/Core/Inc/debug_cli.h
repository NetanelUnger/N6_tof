#ifndef DEBUG_CLI_H
#define DEBUG_CLI_H

#include <stdint.h>
#include "tx_api.h"

typedef struct
{
  uint32_t started;
  uint32_t cycles;
  uint32_t last_tick;
  uint32_t usb_session_ready;
  uint32_t ble_session_ready;
  uint32_t cloud_session_ready;
  uint32_t wifi_results_routed;
  uint32_t wifi_results_stale;
  uint32_t wifi_result_write_errors;
} Debug_CLI_Status_t;

void Debug_CLI_Run(void);
void Debug_CLI_GetStatus(Debug_CLI_Status_t *status);

#endif /* DEBUG_CLI_H */
