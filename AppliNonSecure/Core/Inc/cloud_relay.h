#ifndef CLOUD_RELAY_H
#define CLOUD_RELAY_H

#include <stddef.h>
#include <stdint.h>

#include "app_features.h"
#include "tx_api.h"

#define CLOUD_RELAY_HOST \
  "natilab-n6-h6bjh2ffbadtfyaw.israelcentral-01.azurewebsites.net"
#if (APP_ST67W6X_CLOUD_USE_TLS == 1U)
#define CLOUD_RELAY_SCHEME "https"
#else
#define CLOUD_RELAY_SCHEME "http"
#endif
#define CLOUD_RELAY_PAIR_CODE_LENGTH (6U)
#define CLOUD_RELAY_COMMAND_ID_SIZE  (81U)
#define CLOUD_RELAY_INPUT_MAX        (1152U)

typedef enum
{
  CLOUD_RELAY_STATE_DISABLED = 0,
  CLOUD_RELAY_STATE_WAIT_WIFI,
  CLOUD_RELAY_STATE_UNPAIRED,
  CLOUD_RELAY_STATE_CONNECTING,
  CLOUD_RELAY_STATE_POLLING,
  CLOUD_RELAY_STATE_BACKOFF,
  CLOUD_RELAY_STATE_ERROR
} CloudRelay_State_t;

typedef struct
{
  CloudRelay_State_t state;
  uint32_t enabled;
  uint32_t paired;
  uint32_t request_active;
  uint32_t input_ready;
  uint32_t output_queued;
  uint32_t generation;
  uint32_t requests;
  uint32_t request_errors;
  uint32_t commands_received;
  uint32_t commands_acked;
  uint32_t output_records;
  uint32_t duplicate_records;
  uint32_t tof_frames_sent;
  uint32_t tof_frames_dropped;
  int32_t last_http_status;
  int32_t last_transport_status;
  uint32_t backoff_seconds;
  char device_id[65];
  char workspace_id[65];
} CloudRelay_Status_t;

typedef struct
{
  char command_id[CLOUD_RELAY_COMMAND_ID_SIZE];
  uint32_t sequence;
  uint32_t offset;
  uint32_t completed;
  uint32_t binary;
  uint32_t length;
  uint8_t data[CLOUD_RELAY_INPUT_MAX];
} CloudRelay_Input_t;

UINT CloudRelay_Initialize(TX_BYTE_POOL *pool, const char *suggested_device_id);
void CloudRelay_Process(uint32_t wifi_has_ip);
void CloudRelay_GetStatus(CloudRelay_Status_t *status);

UINT CloudRelay_RequestPair(const char *code);
UINT CloudRelay_SetEnabled(uint32_t enabled);
UINT CloudRelay_RequestReconnect(void);
UINT CloudRelay_Unpair(void);

UINT CloudRelay_ReadInput(CloudRelay_Input_t *input);
/* hold_command prevents a new lease after ACK until this command's completed
 * output record is accepted by the server. */
UINT CloudRelay_AcknowledgeInput(const CloudRelay_Input_t *input,
                                  uint32_t hold_command);
UINT CloudRelay_WriteOutput(const void *data, size_t length, uint32_t binary);
/* Copy one bounded output record atomically, with no wait for queue space. */
UINT CloudRelay_TryWriteOutput(const void *data, size_t length,
                               uint32_t binary);
UINT CloudRelay_CompleteCommand(void);

UINT CloudRelay_SubmitTofFrame(uint32_t frame_id, uint8_t channel_id,
                               const uint8_t *payload, uint8_t width,
                               uint8_t height, uint32_t payload_crc32);
uint32_t CloudRelay_IsTofFramePending(uint32_t frame_id);

#endif /* CLOUD_RELAY_H */
