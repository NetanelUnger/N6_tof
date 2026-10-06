#include "cloud_relay.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "app_features.h"
#include "debug_uart.h"
#include "firmware_build_version.h"
#include "main.h"
#include "w6x_api.h"

#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)

#define CLOUD_CONTEXT_BUDGET       (9U * 1024U)
#define CLOUD_RESPONSE_SIZE        (2400U)
#define CLOUD_REQUEST_SIZE         (1200U)
#define CLOUD_OUTPUT_SLOT_COUNT    (8U)
#define CLOUD_OUTPUT_SLOT_SIZE     (384U)
#define CLOUD_TOKEN_SIZE           (1025U)
#if (APP_ST67W6X_CLOUD_USE_TLS == 1U)
#define CLOUD_HTTP_PORT            (443U)
#define CLOUD_TLS_TAG              (7U)
#define CLOUD_CA_FILE              "n6dg2.pem"
#else
#define CLOUD_HTTP_PORT            (80U)
#endif
#define CLOUD_HTTP_TIMEOUT_MS      (4500U)
#define CLOUD_RECV_TIMEOUT_MS      (100U)
#define CLOUD_BACKOFF_MAX_SECONDS  (60U)
#define CLOUD_RECORD_MAGIC         (0x434C364EU) /* N6LC */
#define CLOUD_RECORD_VERSION       (1U)
#define CLOUD_CONTROL_SLOT_COUNT   (4U)
#define CLOUD_WAKE_FLAG            (1UL)
#define CLOUD_WORKER_WAIT_TICKS    ((TX_TIMER_TICKS_PER_SECOND >= 50U) ? \
                                   (TX_TIMER_TICKS_PER_SECOND / 50U) : 1U)

typedef enum
{
  CLOUD_CONTROL_PAIR = 1,
  CLOUD_CONTROL_ENABLE,
  CLOUD_CONTROL_RECONNECT,
  CLOUD_CONTROL_UNPAIR
} CloudControlKind_t;

typedef struct
{
  ULONG kind;
  ULONG value;
  char code[8];
} CloudControlRequest_t;

_Static_assert(sizeof(CloudControlRequest_t) == 4U * sizeof(ULONG),
               "Cloud control queue must copy exactly four ULONGs");

static TX_EVENT_FLAGS_GROUP cloud_events;
static TX_QUEUE cloud_control_queue;
static ULONG cloud_control_storage[CLOUD_CONTROL_SLOT_COUNT * 4U];
static volatile uint32_t cloud_prepared;
static volatile uint32_t cloud_initialized;
static volatile uint32_t cloud_network_ready;
static volatile uint32_t cloud_wifi_has_ip;
static uint32_t cloud_control_high_water;
static uint32_t cloud_control_rejected;
static CloudRelay_Status_t cloud_status_snapshot;

typedef enum
{
  CLOUD_HTTP_NONE = 0,
  CLOUD_HTTP_PAIR,
  CLOUD_HTTP_POLL,
  CLOUD_HTTP_ACK,
  CLOUD_HTTP_OUTPUT,
  CLOUD_HTTP_TOF
} CloudHttpKind_t;

typedef struct
{
  uint32_t magic;
  uint16_t version;
  uint16_t length;
  uint32_t enabled;
  char device_id[65];
  char workspace_id[65];
  char token[CLOUD_TOKEN_SIZE];
  uint32_t crc32;
} CloudPairingRecord_t;

typedef struct
{
  uint16_t length;
  uint8_t binary;
  uint8_t completed;
  uint8_t data[CLOUD_OUTPUT_SLOT_SIZE];
} CloudOutputSlot_t;

typedef struct
{
  TX_MUTEX gate;
  CloudRelay_Status_t status;
  CloudPairingRecord_t pairing;
  char pair_code[CLOUD_RELAY_PAIR_CODE_LENGTH + 1U];
  uint32_t pair_pending;
  CloudRelay_Input_t input;
  uint32_t input_ready;
  uint32_t input_delivered;
  uint32_t ack_pending;
  char ack_command_id[CLOUD_RELAY_COMMAND_ID_SIZE];
  uint32_t ack_sequence;
  char active_command_id[CLOUD_RELAY_COMMAND_ID_SIZE];
  uint32_t hold_command;
  uint32_t output_sequence;
  CloudOutputSlot_t *output;
  uint32_t output_head;
  uint32_t output_tail;
  uint32_t output_count;
  const uint8_t *tof_payload;
  uint32_t tof_frame_id;
  uint32_t tof_payload_crc32;
  uint16_t tof_payload_length;
  uint8_t tof_width;
  uint8_t tof_height;
  uint8_t tof_channel_id;
  uint32_t tof_pending;
  uint8_t tof_header[20];
  int32_t socket;
  CloudHttpKind_t http_kind;
  uint32_t http_deadline;
  uint32_t response_length;
  uint8_t response[CLOUD_RESPONSE_SIZE + 1U];
  char request[CLOUD_REQUEST_SIZE];
  ip_addr_t server_address;
  uint32_t address_valid;
  uint32_t ca_ready;
  uint32_t time_configured;
  uint32_t time_ready;
  uint32_t next_action_tick;
  uint32_t backoff_step;
} CloudRelayContext_t;

_Static_assert(sizeof(CloudRelayContext_t) <= CLOUD_CONTEXT_BUDGET,
               "Cloud Relay context exceeded its SRAM4 budget");

static CloudRelayContext_t *cloud;
/* Keep bounded output storage in application SRAM rather than reducing the
 * already narrow SRAM4 radio byte-pool reserve. No post-init allocation. */
static CloudOutputSlot_t cloud_output_slots[CLOUD_OUTPUT_SLOT_COUNT];
static char cloud_pair_file[W6X_SYS_FS_FILENAME_SIZE] = "n6cloud.cfg";

#if (APP_ST67W6X_CLOUD_USE_TLS == 1U)
static const char cloud_root_ca[] =
  "-----BEGIN CERTIFICATE-----\r\n"
  "MIIDjjCCAnagAwIBAgIQAzrx5qcRqaC7KGSxHQn65TANBgkqhkiG9w0BAQsFADBh\r\n"
  "MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3\r\n"
  "d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH\r\n"
  "MjAeFw0xMzA4MDExMjAwMDBaFw0zODAxMTUxMjAwMDBaMGExCzAJBgNVBAYTAlVT\r\n"
  "MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxGTAXBgNVBAsTEHd3dy5kaWdpY2VydC5j\r\n"
  "b20xIDAeBgNVBAMTF0RpZ2lDZXJ0IEdsb2JhbCBSb290IEcyMIIBIjANBgkqhkiG\r\n"
  "9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuzfNNNx7a8myaJCtSnX/RrohCgiN9RlUyfuI\r\n"
  "2/Ou8jqJkTx65qsGGmvPrC3oXgkkRLpimn7Wo6h+4FR1IAWsULecYxpsMNzaHxmx\r\n"
  "1x7e/dfgy5SDN67sH0NO3Xss0r0upS/kqbitOtSZpLYl6ZtrAGCSYP9PIUkY92eQ\r\n"
  "q2EGnI/yuum06ZIya7XzV+hdG82MHauVBJVJ8zUtluNJbd134/tJS7SsVQepj5Wz\r\n"
  "tCO7TG1F8PapspUwtP1MVYwnSlcUfIKdzXOS0xZKBgyMUNGPHgm+F6HmIcr9g+UQ\r\n"
  "vIOlCsRnKPZzFBQ9RnbDhxSJITRNrw9FDKZJobq7nMWxM4MphQIDAQABo0IwQDAP\r\n"
  "BgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB/wQEAwIBhjAdBgNVHQ4EFgQUTiJUIBiV\r\n"
  "5uNu5g/6+rkS7QYXjzkwDQYJKoZIhvcNAQELBQADggEBAGBnKJRvDkhj6zHd6mcY\r\n"
  "1Yl9PMWLSn/pvtsrF9+wX3N3KjITOYFnQoQj8kVnNeyIv/iPsGEMNKSuIEyExtv4\r\n"
  "NeF22d+mQrvHRAiGfzZ0JFrabA0UWTW98kndth/Jsw1HKj2ZL7tcu7XUIOGZX1NG\r\n"
  "Fdtom/DzMNU+MeKNhJ7jitralj41E6Vf8PlwUHBHQRFXGU7Aj64GxJUTFy8bJZ91\r\n"
  "8rGOmaFvE7FBcf6IKshPECBV1/MUReXgRPTqh5Uykw7+U0b6LJ3/iyK5S9kJRaTe\r\n"
  "pLiaWN0bfVKfjllDiIGknibVb63dDcY3fe0Dkhvld1927jyNxF1WW6LZZm6zNTfl\r\n"
  "MrY=\r\n"
  "-----END CERTIFICATE-----\r\n";
#endif

static uint32_t cloud_crc32(const void *data, size_t length);
static void cloud_store_u16(uint8_t *target, uint16_t value);
static void cloud_store_u32(uint8_t *target, uint32_t value);
static void cloud_close_socket(void);
static void cloud_backoff(void);
static int cloud_send_all(int32_t socket, const void *data, size_t length);
static int cloud_begin_request(CloudHttpKind_t kind, const char *method,
                               const char *path, const char *content_type,
                               const void *body, size_t body_length,
                               const void *body2, size_t body2_length,
                               uint32_t authenticated);
static void cloud_receive_step(void);
static int cloud_response_ready(void);
static int cloud_decode_response(int *status, uint8_t **body,
                                 size_t *body_length);
static void cloud_finish_request(void);
static void cloud_start_next_request(void);
static int cloud_load_pairing(void);
static int cloud_save_pairing(void);
static void cloud_clear_pairing(uint32_t delete_file);
static int cloud_parse_pair_response(const uint8_t *body, size_t length);
static int cloud_parse_command(const uint8_t *body, size_t length);
static int json_get_string(const uint8_t *json, size_t length,
                           const char *key, char *value, size_t capacity);
static int json_get_u32(const uint8_t *json, size_t length,
                        const char *key, uint32_t *value);
static int json_get_bool(const uint8_t *json, size_t length,
                         const char *key, uint32_t *value);
static int cloud_json_escape(const uint8_t *source, size_t length,
                             char *target, size_t capacity);
static int cloud_base64_encode(const uint8_t *source, size_t length,
                               char *target, size_t capacity);
static int cloud_base64_decode(const char *source, uint8_t *target,
                               size_t capacity, size_t *length);
static const uint8_t *cloud_find_ci(const uint8_t *haystack, size_t haystack_length,
                                    const char *needle);
static UINT cloud_output_admission_self_test(void);
static void cloud_process(uint32_t wifi_has_ip);
static void cloud_publish_status(void);
static void cloud_release_tof(void);
static UINT cloud_submit_control(const CloudControlRequest_t *request);
static UINT cloud_apply_control(const CloudControlRequest_t *request);
static UINT cloud_control_queue_self_test(void);
static UINT cloud_receive_control(CloudControlRequest_t *request);

UINT CloudRelay_Prepare(void)
{
  UINT result;
  if (cloud_prepared != 0U) return TX_SUCCESS;
  result = tx_event_flags_create(&cloud_events, "N6 cloud wake");
  if (result != TX_SUCCESS) return result;
  result = tx_queue_create(&cloud_control_queue, "N6 cloud control", TX_4_ULONG,
                           cloud_control_storage, sizeof(cloud_control_storage));
  if (result != TX_SUCCESS)
  {
    (void)tx_event_flags_delete(&cloud_events);
    return result;
  }
  result = cloud_control_queue_self_test();
  if (result != TX_SUCCESS)
  {
    (void)tx_queue_delete(&cloud_control_queue);
    (void)tx_event_flags_delete(&cloud_events);
    return result;
  }
  cloud_prepared = 1U;
  return TX_SUCCESS;
}

void CloudRelay_SetNetworkState(uint32_t ready, uint32_t wifi_has_ip)
{
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  uint32_t changed = ((cloud_network_ready != ready) ||
                       (cloud_wifi_has_ip != wifi_has_ip)) ? 1U : 0U;
  cloud_network_ready = ready;
  cloud_wifi_has_ip = wifi_has_ip;
  (void)tx_interrupt_control(posture);
  if ((changed != 0U) && (cloud_prepared != 0U))
  {
    (void)tx_event_flags_set(&cloud_events, CLOUD_WAKE_FLAG, TX_OR);
  }
}

void CloudRelay_Run(void)
{
  CloudControlRequest_t request = {0};
  uint32_t request_pending = 0U;
  ULONG flags;

  for (;;)
  {
    if (cloud_initialized != 0U)
    {
      uint32_t started = HAL_GetTick();
      if ((request_pending == 0U) &&
          (cloud_receive_control(&request) == TX_SUCCESS))
      {
        request_pending = 1U;
      }
      if ((request_pending != 0U) &&
          (cloud_apply_control(&request) == TX_SUCCESS))
      {
        (void)memset(&request, 0, sizeof(request));
        request_pending = 0U;
      }
      cloud_process((cloud_network_ready != 0U) ? cloud_wifi_has_ip : 0U);
      cloud->status.worker_loops++;
      cloud->status.worker_last_tick = HAL_GetTick();
      uint32_t elapsed = cloud->status.worker_last_tick - started;
      if (elapsed > cloud->status.worker_max_step_ms)
      {
        cloud->status.worker_max_step_ms = elapsed;
      }
      cloud_publish_status();
    }
    /* Wake for owned input/network changes; even an immediately ready event
     * is followed by a finite wait on the next idle iteration, never a spin. */
    (void)tx_event_flags_get(&cloud_events, CLOUD_WAKE_FLAG, TX_OR_CLEAR,
                             &flags, CLOUD_WORKER_WAIT_TICKS);
  }
}

static void cloud_publish_status(void)
{
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  cloud->status.paired = (cloud->pairing.magic == CLOUD_RECORD_MAGIC) ? 1U : 0U;
  cloud->status.input_ready = cloud->input_ready;
  cloud->status.output_queued = cloud->output_count;
  cloud->status.request_active = (cloud->http_kind != CLOUD_HTTP_NONE) ? 1U : 0U;
  cloud->status.control_queued = cloud_control_queue.tx_queue_enqueued;
  cloud->status.control_high_water = cloud_control_high_water;
  cloud->status.control_rejected = cloud_control_rejected;
  cloud_status_snapshot = cloud->status;
  (void)tx_interrupt_control(posture);
}

static UINT cloud_submit_control(const CloudControlRequest_t *request)
{
  UINT result;
  UINT posture;
  if ((cloud_prepared == 0U) || (cloud_network_ready == 0U) ||
      (cloud_initialized == 0U))
  {
    return TX_NOT_AVAILABLE;
  }
  /* Queue publication and high-water sampling form one short operation. */
  posture = tx_interrupt_control(TX_INT_DISABLE);
  result = tx_queue_send(&cloud_control_queue, (VOID *)request, TX_NO_WAIT);
  if (result != TX_SUCCESS) cloud_control_rejected++;
  else if (cloud_control_queue.tx_queue_enqueued > cloud_control_high_water)
  {
    cloud_control_high_water = cloud_control_queue.tx_queue_enqueued;
  }
  (void)tx_interrupt_control(posture);
  if (result == TX_SUCCESS)
  {
    (void)tx_event_flags_set(&cloud_events, CLOUD_WAKE_FLAG, TX_OR);
  }
  return result;
}

static UINT cloud_receive_control(CloudControlRequest_t *request)
{
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  ULONG *slot = cloud_control_queue.tx_queue_read;
  UINT result = tx_queue_receive(&cloud_control_queue, request, TX_NO_WAIT);
  /* ThreadX copies by value but retains the old ring bytes. Scrub the consumed
   * pairing code before another producer can reuse that slot. */
  if (result == TX_SUCCESS) (void)memset(slot, 0, sizeof(*request));
  (void)tx_interrupt_control(posture);
  return result;
}

static UINT cloud_apply_control(const CloudControlRequest_t *request)
{
  uint32_t save = 0U;
  uint32_t delete_file = 0U;
  /* Only this worker can close/reopen a socket or touch the NCP filesystem.
   * The gate is never held across those blocking operations. */
  if ((request->kind == CLOUD_CONTROL_RECONNECT) ||
      (request->kind == CLOUD_CONTROL_UNPAIR) ||
      ((request->kind == CLOUD_CONTROL_ENABLE) && (request->value == 0U)))
  {
    cloud_close_socket();
  }
  if (tx_mutex_get(&cloud->gate, TX_NO_WAIT) != TX_SUCCESS) return TX_NOT_AVAILABLE;
  switch (request->kind)
  {
    case CLOUD_CONTROL_PAIR:
      (void)memcpy(cloud->pair_code, request->code, sizeof(cloud->pair_code));
      cloud->pair_pending = 1U;
      cloud->next_action_tick = HAL_GetTick();
      break;
    case CLOUD_CONTROL_ENABLE:
      cloud->status.enabled = (request->value != 0U) ? 1U : 0U;
      cloud->pairing.enabled = cloud->status.enabled;
      save = (cloud->pairing.magic == CLOUD_RECORD_MAGIC) ? 1U : 0U;
      if (request->value == 0U)
      {
        cloud->hold_command = 0U;
        cloud_release_tof();
      }
      else cloud->next_action_tick = HAL_GetTick();
      break;
    case CLOUD_CONTROL_RECONNECT:
      cloud->address_valid = 0U;
      cloud->backoff_step = 0U;
      cloud->status.backoff_seconds = 0U;
      cloud->status.generation++;
      cloud->hold_command = 0U;
      cloud_release_tof();
      cloud->next_action_tick = HAL_GetTick();
      break;
    case CLOUD_CONTROL_UNPAIR:
      cloud_clear_pairing(0U);
      cloud->pair_pending = 0U;
      (void)memset(cloud->pair_code, 0, sizeof(cloud->pair_code));
      cloud->status.generation++;
      cloud_release_tof();
      delete_file = 1U;
      break;
    default:
      break;
  }
  (void)tx_mutex_put(&cloud->gate);
  cloud_publish_status();
  if (save != 0U) (void)cloud_save_pairing();
  if (delete_file != 0U) (void)W6X_FS_DeleteFile(cloud_pair_file);
  return TX_SUCCESS;
}

static UINT cloud_control_queue_self_test(void)
{
  CloudControlRequest_t sent = { .kind = CLOUD_CONTROL_PAIR, .code = "000000" };
  CloudControlRequest_t received;
  for (ULONG index = 0U; index < CLOUD_CONTROL_SLOT_COUNT; ++index)
  {
    sent.value = index;
    if (tx_queue_send(&cloud_control_queue, &sent, TX_NO_WAIT) != TX_SUCCESS) return TX_NOT_AVAILABLE;
  }
  if (tx_queue_send(&cloud_control_queue, &sent, TX_NO_WAIT) != TX_QUEUE_FULL) return TX_NOT_AVAILABLE;
  (void)memset(&sent, 0, sizeof(sent));
  for (ULONG index = 0U; index < CLOUD_CONTROL_SLOT_COUNT; ++index)
  {
    if ((tx_queue_receive(&cloud_control_queue, &received, TX_NO_WAIT) != TX_SUCCESS) ||
        (received.kind != CLOUD_CONTROL_PAIR) || (received.value != index) ||
        (strcmp(received.code, "000000") != 0)) return TX_NOT_AVAILABLE;
  }
  (void)memset(&received, 0, sizeof(received));
  (void)memset(cloud_control_storage, 0, sizeof(cloud_control_storage));
  return TX_SUCCESS;
}

UINT CloudRelay_Initialize(TX_BYTE_POOL *pool, const char *suggested_device_id)
{
  void *memory = NULL;

  if ((pool == NULL) || (cloud != NULL))
  {
    return (cloud != NULL) ? TX_SUCCESS : TX_PTR_ERROR;
  }
  if (tx_byte_allocate(pool, &memory, sizeof(CloudRelayContext_t),
                       TX_NO_WAIT) != TX_SUCCESS)
  {
    return TX_NO_MEMORY;
  }

  cloud = (CloudRelayContext_t *)memory;
  (void)memset(cloud, 0, sizeof(*cloud));
  (void)memset(cloud_output_slots, 0, sizeof(cloud_output_slots));
  cloud->output = cloud_output_slots;
  cloud->socket = -1;
  cloud->status.enabled = 1U;
  cloud->status.state = CLOUD_RELAY_STATE_WAIT_WIFI;
#if (APP_ST67W6X_CLOUD_USE_TLS == 0U)
  Debug_UART_Log("CLOUD", "WARNING: plaintext HTTP: pairing code/token and CLI are exposed (demo only)");
#elif (APP_ST67W6X_CLOUD_TLS_VERIFY_SERVER == 0U)
  Debug_UART_Log("CLOUD", "WARNING: TLS server verification disabled (demo only)");
#endif
  if (tx_mutex_create(&cloud->gate, "N6 cloud relay", TX_INHERIT) != TX_SUCCESS)
  {
    (void)tx_byte_release(memory);
    cloud = NULL;
    return TX_MUTEX_ERROR;
  }

  if (cloud_output_admission_self_test() != TX_SUCCESS)
  {
    (void)tx_mutex_delete(&cloud->gate);
    (void)memset(cloud_output_slots, 0, sizeof(cloud_output_slots));
    (void)memset(cloud, 0, sizeof(*cloud));
    (void)tx_byte_release(memory);
    cloud = NULL;
    return TX_NOT_AVAILABLE;
  }

  if ((suggested_device_id != NULL) && (suggested_device_id[0] != '\0'))
  {
    (void)snprintf(cloud->status.device_id,
                   sizeof(cloud->status.device_id), "%s", suggested_device_id);
  }
  else
  {
    (void)snprintf(cloud->status.device_id,
                   sizeof(cloud->status.device_id), "n6-device");
  }
  (void)cloud_load_pairing();
  cloud_publish_status();
  cloud_initialized = 1U;
  return TX_SUCCESS;
}

static void cloud_process(uint32_t wifi_has_ip)
{
  if (cloud == NULL) return;

  if ((cloud->status.enabled == 0U) || (wifi_has_ip == 0U))
  {
    cloud_close_socket();
    cloud_release_tof();
#if (APP_ST67W6X_CLOUD_USE_TLS == 1U)
    if (wifi_has_ip == 0U)
    {
      cloud->time_configured = 0U;
      cloud->time_ready = 0U;
    }
#endif
    cloud->status.state = (cloud->status.enabled != 0U) ?
        CLOUD_RELAY_STATE_WAIT_WIFI : CLOUD_RELAY_STATE_DISABLED;
    return;
  }

  /* An unpaired relay has no network work.  In particular, do not issue a
   * synchronous SNTP command merely because STA got IP. */
  if ((cloud->pair_pending == 0U) &&
      (cloud->pairing.magic != CLOUD_RECORD_MAGIC))
  {
    cloud->status.state = CLOUD_RELAY_STATE_UNPAIRED;
    return;
  }

#if (APP_ST67W6X_CLOUD_USE_TLS == 1U)
  /* Only TLS certificate validation needs a reliable NCP wall clock. */
  if (cloud->time_configured == 0U)
  {
    static uint8_t server1[] = "time.cloudflare.com";
    static uint8_t server2[] = "pool.ntp.org";
    if (W6X_Net_SNTP_SetConfiguration(1U, 0, server1, server2, NULL) !=
        W6X_STATUS_OK)
    {
      cloud->status.last_transport_status = -30;
      cloud->next_action_tick = HAL_GetTick() + 5000U;
      return;
    }
    cloud->time_configured = 1U;
    cloud->next_action_tick = HAL_GetTick() + 5000U;
    cloud->status.state = CLOUD_RELAY_STATE_CONNECTING;
    return;
  }
  if (cloud->time_ready == 0U)
  {
    W6X_Net_Time_t current_time;
    if ((int32_t)(HAL_GetTick() - cloud->next_action_tick) < 0) return;
    (void)memset(&current_time, 0, sizeof(current_time));
    if ((W6X_Net_SNTP_GetTime(&current_time) != W6X_STATUS_OK) ||
        (current_time.year < 2024U))
    {
      cloud->status.last_transport_status = -31;
      cloud->next_action_tick = HAL_GetTick() + 5000U;
      return;
    }
    cloud->time_ready = 1U;
    cloud->next_action_tick = HAL_GetTick();
  }
#endif

  if (cloud->http_kind != CLOUD_HTTP_NONE)
  {
    cloud_receive_step();
    return;
  }
  if ((int32_t)(HAL_GetTick() - cloud->next_action_tick) < 0)
  {
    return;
  }

  cloud_start_next_request();
}

void CloudRelay_GetStatus(CloudRelay_Status_t *status)
{
  if (status == NULL) return;
  (void)memset(status, 0, sizeof(*status));
  if (cloud == NULL)
  {
    status->state = CLOUD_RELAY_STATE_DISABLED;
    return;
  }

  /* Diagnostics/Radio never wait behind DNS, sockets or filesystem work. */
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  *status = cloud_status_snapshot;
  (void)tx_interrupt_control(posture);
}

UINT CloudRelay_RequestPair(const char *code)
{
  size_t length;
  if ((cloud == NULL) || (code == NULL)) return TX_PTR_ERROR;
  length = strlen(code);
  if (length != CLOUD_RELAY_PAIR_CODE_LENGTH) return TX_SIZE_ERROR;
  for (size_t index = 0U; index < length; ++index)
  {
    if (!isdigit((unsigned char)code[index])) return TX_OPTION_ERROR;
  }

  CloudControlRequest_t request = { .kind = CLOUD_CONTROL_PAIR };
  (void)memcpy(request.code, code, length + 1U);
  UINT result = cloud_submit_control(&request);
  (void)memset(&request, 0, sizeof(request));
  return result;
}

UINT CloudRelay_SetEnabled(uint32_t enabled)
{
  CloudControlRequest_t request = { .kind = CLOUD_CONTROL_ENABLE, .value = enabled };
  return cloud_submit_control(&request);
}

UINT CloudRelay_RequestReconnect(void)
{
  CloudControlRequest_t request = { .kind = CLOUD_CONTROL_RECONNECT };
  return cloud_submit_control(&request);
}

UINT CloudRelay_Unpair(void)
{
  CloudControlRequest_t request = { .kind = CLOUD_CONTROL_UNPAIR };
  return cloud_submit_control(&request);
}

UINT CloudRelay_ReadInput(CloudRelay_Input_t *input)
{
  if ((cloud == NULL) || (input == NULL)) return TX_PTR_ERROR;
  UINT lock_status = tx_mutex_get(&cloud->gate, TX_NO_WAIT);
  if (lock_status != TX_SUCCESS) return lock_status;
  if ((cloud->input_ready == 0U) || (cloud->input_delivered != 0U))
  {
    (void)tx_mutex_put(&cloud->gate);
    return TX_QUEUE_EMPTY;
  }
  *input = cloud->input;
  cloud->input_delivered = 1U;
  (void)tx_mutex_put(&cloud->gate);
  return TX_SUCCESS;
}

UINT CloudRelay_AcknowledgeInput(const CloudRelay_Input_t *input,
                                  uint32_t hold_command)
{
  if ((cloud == NULL) || (input == NULL)) return TX_PTR_ERROR;
  /* An accepted input must not lose its ACK merely because the lower-priority
   * frame publisher was preempted while holding the unrelated ToF gate. This
   * bounded metadata publication never waits and does no network work. */
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  if ((cloud->ack_pending != 0U) || (cloud->input_ready == 0U) ||
      (cloud->input_delivered == 0U) ||
      (cloud->input.sequence != input->sequence) ||
      (strcmp(cloud->input.command_id, input->command_id) != 0))
  {
    (void)tx_interrupt_control(posture);
    return TX_NOT_AVAILABLE;
  }
  if ((hold_command != 0U) &&
      (strcmp(cloud->active_command_id, input->command_id) != 0))
  {
    (void)tx_interrupt_control(posture);
    return TX_NOT_AVAILABLE;
  }
  (void)memcpy(cloud->ack_command_id, input->command_id,
                sizeof(cloud->ack_command_id));
  cloud->ack_sequence = input->sequence;
  cloud->ack_pending = 1U;
  cloud->hold_command = (hold_command != 0U) ? 1U : 0U;
  cloud->input_ready = 0U;
  cloud->input_delivered = 0U;
  (void)tx_interrupt_control(posture);
  return TX_SUCCESS;
}

UINT CloudRelay_WriteOutput(const void *data, size_t length, uint32_t binary)
{
  const uint8_t *bytes = (const uint8_t *)data;
  size_t required_slots;
  uint32_t tail;
  UINT status;
  UINT posture;

  if ((cloud == NULL) || ((data == NULL) && (length != 0U))) return TX_PTR_ERROR;
  required_slots = (length / CLOUD_OUTPUT_SLOT_SIZE) +
                   ((length % CLOUD_OUTPUT_SLOT_SIZE) != 0U ? 1U : 0U);
  status = tx_mutex_get(&cloud->gate, TX_NO_WAIT);
  if (status != TX_SUCCESS) return status;
  if (cloud->active_command_id[0] == '\0')
  {
    (void)tx_mutex_put(&cloud->gate);
    return TX_NOT_AVAILABLE;
  }
  if ((cloud->output_count > CLOUD_OUTPUT_SLOT_COUNT) ||
      (required_slots > (CLOUD_OUTPUT_SLOT_COUNT - cloud->output_count)))
  {
    (void)tx_mutex_put(&cloud->gate);
    return TX_QUEUE_FULL;
  }

  /* Fill unpublished slots first. Readers see the complete response only
   * after the single tail/count commit; a rejection changes neither. */
  tail = cloud->output_tail;
  while (length != 0U)
  {
    size_t chunk = (length > CLOUD_OUTPUT_SLOT_SIZE) ?
        CLOUD_OUTPUT_SLOT_SIZE : length;
    CloudOutputSlot_t *slot = &cloud->output[tail];
    (void)memset(slot, 0, sizeof(*slot));
    slot->length = (uint16_t)chunk;
    slot->binary = (binary != 0U) ? 1U : 0U;
    (void)memcpy(slot->data, bytes, chunk);
    tail = (tail + 1U) % CLOUD_OUTPUT_SLOT_COUNT;
    bytes += chunk;
    length -= chunk;
  }
  posture = tx_interrupt_control(TX_INT_DISABLE);
  cloud->output_tail = tail;
  cloud->output_count += (uint32_t)required_slots;
  (void)tx_interrupt_control(posture);
  (void)tx_mutex_put(&cloud->gate);
  return TX_SUCCESS;
}

UINT CloudRelay_TryWriteOutput(const void *data, size_t length,
                               uint32_t binary)
{
  if ((cloud == NULL) || (data == NULL)) return TX_PTR_ERROR;
  if ((length == 0U) || (length > CLOUD_OUTPUT_SLOT_SIZE))
  {
    return TX_SIZE_ERROR;
  }
  return CloudRelay_WriteOutput(data, length, binary);
}

UINT CloudRelay_CompleteCommand(void)
{
  CloudOutputSlot_t *slot;
  UINT status;
  UINT posture;

  if (cloud == NULL) return TX_NOT_AVAILABLE;
  status = tx_mutex_get(&cloud->gate, TX_NO_WAIT);
  if (status != TX_SUCCESS) return status;
  if (cloud->active_command_id[0] == '\0')
  {
    (void)tx_mutex_put(&cloud->gate);
    return TX_NOT_AVAILABLE;
  }
  if (cloud->output_count >= CLOUD_OUTPUT_SLOT_COUNT)
  {
    (void)tx_mutex_put(&cloud->gate);
    return TX_QUEUE_FULL;
  }
  slot = &cloud->output[cloud->output_tail];
  (void)memset(slot, 0, sizeof(*slot));
  slot->completed = 1U;
  posture = tx_interrupt_control(TX_INT_DISABLE);
  cloud->output_tail = (cloud->output_tail + 1U) % CLOUD_OUTPUT_SLOT_COUNT;
  cloud->output_count++;
  (void)tx_interrupt_control(posture);
  (void)tx_mutex_put(&cloud->gate);
  return TX_SUCCESS;
}

static UINT cloud_output_admission_self_test(void)
{
  uint8_t payload[CLOUD_OUTPUT_SLOT_SIZE + 1U];
  UINT result = TX_NOT_AVAILABLE;

  /* Initialization is the only caller: no Cloud producer/consumer is active.
   * Force a one-slot-short rejection and verify that no partial record leaks. */
  (void)memset(payload, 0xA5, sizeof(payload));
  (void)memcpy(cloud->active_command_id, "m51-self-test", sizeof("m51-self-test"));
  for (uint32_t i = 0U; i < CLOUD_OUTPUT_SLOT_COUNT - 1U; ++i)
  {
    if (CloudRelay_WriteOutput(payload, CLOUD_OUTPUT_SLOT_SIZE, 0U) != TX_SUCCESS)
    {
      goto done;
    }
  }
  if ((CloudRelay_WriteOutput(payload, sizeof(payload), 1U) != TX_QUEUE_FULL) ||
      (cloud->output_count != CLOUD_OUTPUT_SLOT_COUNT - 1U) ||
      (cloud->output_tail != CLOUD_OUTPUT_SLOT_COUNT - 1U) ||
      (cloud->output[CLOUD_OUTPUT_SLOT_COUNT - 1U].length != 0U))
  {
    goto done;
  }
  if ((CloudRelay_CompleteCommand() != TX_SUCCESS) ||
      (CloudRelay_CompleteCommand() != TX_QUEUE_FULL) ||
      (cloud->output_count != CLOUD_OUTPUT_SLOT_COUNT))
  {
    goto done;
  }

  (void)memset(cloud_output_slots, 0, sizeof(cloud_output_slots));
  cloud->output_head = 0U;
  cloud->output_tail = 0U;
  cloud->output_count = 0U;
  if ((CloudRelay_WriteOutput(payload, sizeof(payload), 1U) != TX_SUCCESS) ||
      (cloud->output_count != 2U) ||
      (cloud->output[0].length != CLOUD_OUTPUT_SLOT_SIZE) ||
      (cloud->output[1].length != 1U) ||
      (cloud->output[0].binary != 1U) ||
      (cloud->output[1].data[0] != 0xA5U) ||
      (CloudRelay_CompleteCommand() != TX_SUCCESS) ||
      (cloud->output_count != 3U) ||
      (cloud->output[2].completed != 1U))
  {
    goto done;
  }
  result = TX_SUCCESS;

done:
  (void)memset(cloud_output_slots, 0, sizeof(cloud_output_slots));
  (void)memset(cloud->active_command_id, 0, sizeof(cloud->active_command_id));
  cloud->output_head = 0U;
  cloud->output_tail = 0U;
  cloud->output_count = 0U;
  return result;
}

UINT CloudRelay_SubmitTofFrame(uint32_t frame_id, uint8_t channel_id,
                               const uint8_t *payload, uint8_t width,
                               uint8_t height, uint32_t payload_crc32)
{
  uint32_t length = (uint32_t)width * (uint32_t)height * sizeof(float);
  if ((cloud == NULL) || (payload == NULL) || (width == 0U) || (height == 0U) ||
      (width > 54U) || (height > 42U) || (length > UINT16_MAX))
  {
    return TX_PTR_ERROR;
  }
  UINT lock_status = tx_mutex_get(&cloud->gate, TX_NO_WAIT);
  if (lock_status != TX_SUCCESS) return lock_status;
  if ((cloud->status.enabled == 0U) ||
      (cloud->pairing.magic != CLOUD_RECORD_MAGIC) ||
      (cloud->tof_pending != 0U))
  {
    cloud->status.tof_frames_dropped++;
    (void)tx_mutex_put(&cloud->gate);
    return TX_NOT_AVAILABLE;
  }
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  cloud->tof_payload = payload;
  cloud->tof_frame_id = frame_id;
  cloud->tof_payload_crc32 = payload_crc32;
  cloud->tof_payload_length = (uint16_t)length;
  cloud->tof_width = width;
  cloud->tof_height = height;
  cloud->tof_channel_id = channel_id;
  cloud->tof_pending = 1U;
  (void)tx_interrupt_control(posture);
  (void)tx_mutex_put(&cloud->gate);
  return TX_SUCCESS;
}

uint32_t CloudRelay_IsTofFramePending(uint32_t frame_id)
{
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  uint32_t pending = ((cloud != NULL) && (cloud->tof_pending != 0U) &&
                      (cloud->tof_frame_id == frame_id)) ? 1U : 0U;
  (void)tx_interrupt_control(posture);
  return pending;
}

static void cloud_release_tof(void)
{
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  /* Release last: another thread may immediately reuse the shared buffer. */
  cloud->tof_payload = NULL;
  cloud->tof_pending = 0U;
  (void)tx_interrupt_control(posture);
}

static uint32_t cloud_crc32(const void *data, size_t length)
{
  const uint8_t *bytes = (const uint8_t *)data;
  uint32_t crc = 0xFFFFFFFFU;
  for (size_t index = 0U; index < length; ++index)
  {
    crc ^= bytes[index];
    for (uint32_t bit = 0U; bit < 8U; ++bit)
    {
      crc = (crc >> 1U) ^ ((crc & 1U) ? 0xEDB88320U : 0U);
    }
  }
  return crc ^ 0xFFFFFFFFU;
}

static void cloud_store_u16(uint8_t *target, uint16_t value)
{
  target[0] = (uint8_t)value;
  target[1] = (uint8_t)(value >> 8U);
}

static void cloud_store_u32(uint8_t *target, uint32_t value)
{
  target[0] = (uint8_t)value;
  target[1] = (uint8_t)(value >> 8U);
  target[2] = (uint8_t)(value >> 16U);
  target[3] = (uint8_t)(value >> 24U);
}

static void cloud_close_socket(void)
{
  if ((cloud != NULL) && (cloud->socket >= 0))
  {
    (void)W6X_Net_Close(cloud->socket);
    cloud->socket = -1;
  }
  if (cloud != NULL)
  {
    cloud->http_kind = CLOUD_HTTP_NONE;
    cloud->response_length = 0U;
  }
}

static void cloud_backoff(void)
{
  static const uint8_t seconds[] = { 2U, 5U, 15U, 30U, 60U };
  uint32_t index = cloud->backoff_step;
  if (index >= (sizeof(seconds) / sizeof(seconds[0]))) index =
      (sizeof(seconds) / sizeof(seconds[0])) - 1U;
  cloud->status.backoff_seconds = seconds[index];
  cloud->next_action_tick = HAL_GetTick() + seconds[index] * 1000U;
  if (cloud->backoff_step + 1U < (sizeof(seconds) / sizeof(seconds[0])))
  {
    cloud->backoff_step++;
  }
  cloud->status.state = CLOUD_RELAY_STATE_BACKOFF;
  cloud->status.request_errors++;
  cloud_close_socket();
}

static int cloud_send_all(int32_t socket, const void *data, size_t length)
{
  const uint8_t *cursor = (const uint8_t *)data;
  while (length != 0U)
  {
    ssize_t sent = W6X_Net_Send(socket, cursor, length, 0);
    if (sent <= 0) return -1;
    cursor += (size_t)sent;
    length -= (size_t)sent;
  }
  return 0;
}

static int cloud_begin_request(CloudHttpKind_t kind, const char *method,
                               const char *path, const char *content_type,
                               const void *body, size_t body_length,
                               const void *body2, size_t body2_length,
                               uint32_t authenticated)
{
  struct sockaddr_in address;
#if (APP_ST67W6X_CLOUD_USE_TLS == 1U)
  /* Vendor Setsockopt reads an int32_t but counts TLS tags in single bytes. */
  int32_t tags[1] = { CLOUD_TLS_TAG };
#endif
  uint32_t timeout = CLOUD_RECV_TIMEOUT_MS;
  int length;

  if (cloud->address_valid == 0U)
  {
    if (W6X_Net_ResolveHostAddressByType(
            CLOUD_RELAY_HOST, &cloud->server_address,
            W6X_NET_DNS_ADDRTYPE_IPV4) != W6X_STATUS_OK)
    {
      cloud->status.last_transport_status = -10;
      return -1;
    }
    cloud->address_valid = 1U;
  }
#if (APP_ST67W6X_CLOUD_USE_TLS == 1U)
  if ((APP_ST67W6X_CLOUD_TLS_VERIFY_SERVER != 0U) &&
      (cloud->ca_ready == 0U))
  {
    if (W6X_Net_TLS_Credential_AddByContent(
            CLOUD_TLS_TAG, W6X_NET_TLS_CREDENTIAL_CA_CERTIFICATE,
            CLOUD_CA_FILE, cloud_root_ca,
            (uint32_t)strlen(cloud_root_ca)) != 0)
    {
      cloud->status.last_transport_status = -11;
      return -1;
    }
    cloud->ca_ready = 1U;
  }
#endif

#if (APP_ST67W6X_CLOUD_USE_TLS == 1U)
  cloud->socket = W6X_Net_Socket(AF_INET, SOCK_STREAM, IPPROTO_TLS_1_2);
#else
  cloud->socket = W6X_Net_Socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
#endif
  if (cloud->socket < 0)
  {
    cloud->status.last_transport_status = -12;
    return -1;
  }
#if (APP_ST67W6X_CLOUD_USE_TLS == 1U)
  if (((APP_ST67W6X_CLOUD_TLS_VERIFY_SERVER != 0U) &&
       (W6X_Net_Setsockopt(cloud->socket, SOL_TLS, TLS_SEC_TAG_LIST,
                           tags, 1U) != 0)) ||
      (W6X_Net_Setsockopt(cloud->socket, SOL_TLS, TLS_HOSTNAME,
                          CLOUD_RELAY_HOST, strlen(CLOUD_RELAY_HOST)) != 0))
  {
    cloud->status.last_transport_status = -13;
    cloud_close_socket();
    return -1;
  }
#endif
  if (W6X_Net_Setsockopt(cloud->socket, SOL_SOCKET, SO_RCVTIMEO,
                         &timeout, sizeof(timeout)) != 0)
  {
    cloud->status.last_transport_status = -13;
    cloud_close_socket();
    return -1;
  }

  (void)memset(&address, 0, sizeof(address));
  address.sin_family = AF_INET;
  address.sin_port = PP_HTONS(CLOUD_HTTP_PORT);
  address.sin_addr.s_addr = cloud->server_address.u_addr.ip4.addr;
  if (W6X_Net_Connect(cloud->socket, (struct sockaddr *)&address,
                      sizeof(address)) != 0)
  {
    cloud->status.last_transport_status = -14;
    cloud->address_valid = 0U;
    cloud_close_socket();
    return -1;
  }

  length = snprintf(
      cloud->request, sizeof(cloud->request),
      "%s %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: n6-cloud/1\r\n"
      "Accept: application/json\r\n%s%s%s"
      "Content-Type: %s\r\nContent-Length: %lu\r\nConnection: close\r\n\r\n",
      method, path, CLOUD_RELAY_HOST,
      (authenticated != 0U) ? "Authorization: Bearer " : "",
      (authenticated != 0U) ? cloud->pairing.token : "",
      (authenticated != 0U) ? "\r\n" : "",
      content_type, (unsigned long)(body_length + body2_length));
  if ((length <= 0) || ((size_t)length >= sizeof(cloud->request)) ||
      (cloud_send_all(cloud->socket, cloud->request, (size_t)length) != 0) ||
      ((body_length != 0U) &&
       (cloud_send_all(cloud->socket, body, body_length) != 0)) ||
      ((body2_length != 0U) &&
       (cloud_send_all(cloud->socket, body2, body2_length) != 0)))
  {
    cloud->status.last_transport_status = -15;
    cloud_close_socket();
    return -1;
  }

  cloud->http_kind = kind;
  cloud->http_deadline = HAL_GetTick() + CLOUD_HTTP_TIMEOUT_MS;
  cloud->response_length = 0U;
  cloud->status.requests++;
  cloud->status.request_active = 1U;
  cloud->status.state = (kind == CLOUD_HTTP_POLL) ?
      CLOUD_RELAY_STATE_POLLING : CLOUD_RELAY_STATE_CONNECTING;
  return 0;
}

static void cloud_receive_step(void)
{
  ssize_t received;
  if (cloud->response_length >= CLOUD_RESPONSE_SIZE)
  {
    cloud->status.last_transport_status = -20;
    cloud_backoff();
    return;
  }

  received = W6X_Net_Recv(cloud->socket,
                          &cloud->response[cloud->response_length],
                          CLOUD_RESPONSE_SIZE - cloud->response_length, 0);
  if (received > 0)
  {
    cloud->response_length += (uint32_t)received;
    cloud->response[cloud->response_length] = 0U;
    if (cloud_response_ready() != 0)
    {
      cloud_finish_request();
    }
    return;
  }
  if ((received == 0) && (cloud->response_length != 0U))
  {
    cloud_finish_request();
    return;
  }
  if ((int32_t)(HAL_GetTick() - cloud->http_deadline) >= 0)
  {
    cloud->status.last_transport_status = -21;
    cloud_backoff();
  }
}

static int cloud_response_ready(void)
{
  const uint8_t *header_end = NULL;
  const uint8_t *content_length;
  const uint8_t *chunked;
  size_t header_length;
  uint32_t length = 0U;

  for (uint32_t index = 0U; index + 3U < cloud->response_length; ++index)
  {
    if ((cloud->response[index] == '\r') && (cloud->response[index + 1U] == '\n') &&
        (cloud->response[index + 2U] == '\r') && (cloud->response[index + 3U] == '\n'))
    {
      header_end = &cloud->response[index + 4U];
      break;
    }
  }
  if (header_end == NULL) return 0;
  header_length = (size_t)(header_end - cloud->response);
  if ((cloud->response_length >= 12U) &&
      ((cloud->response[9] == '2') && (cloud->response[10] == '0') &&
       (cloud->response[11] == '4')))
  {
    return 1;
  }

  content_length = cloud_find_ci(cloud->response, header_length,
                                 "content-length:");
  if (content_length != NULL)
  {
    content_length += strlen("content-length:");
    while ((*content_length == ' ') || (*content_length == '\t')) content_length++;
    while (isdigit((unsigned char)*content_length))
    {
      length = length * 10U + (uint32_t)(*content_length - '0');
      content_length++;
    }
    return (cloud->response_length >= header_length + length) ? 1 : 0;
  }

  chunked = cloud_find_ci(cloud->response, header_length,
                          "transfer-encoding: chunked");
  if (chunked != NULL)
  {
    return (cloud_find_ci(header_end,
                          cloud->response_length - header_length,
                          "\r\n0\r\n\r\n") != NULL) ? 1 : 0;
  }
  return 0;
}

static int cloud_decode_response(int *status, uint8_t **body,
                                 size_t *body_length)
{
  uint8_t *header_end = NULL;
  size_t header_length;
  const uint8_t *chunked;
  if ((status == NULL) || (body == NULL) || (body_length == NULL)) return -1;
  if (sscanf((char *)cloud->response, "HTTP/%*u.%*u %d", status) != 1) return -1;

  for (uint32_t index = 0U; index + 3U < cloud->response_length; ++index)
  {
    if ((cloud->response[index] == '\r') && (cloud->response[index + 1U] == '\n') &&
        (cloud->response[index + 2U] == '\r') && (cloud->response[index + 3U] == '\n'))
    {
      header_end = &cloud->response[index + 4U];
      break;
    }
  }
  if (header_end == NULL) return -1;
  header_length = (size_t)(header_end - cloud->response);
  chunked = cloud_find_ci(cloud->response, header_length,
                          "transfer-encoding: chunked");
  if (chunked == NULL)
  {
    *body = header_end;
    *body_length = cloud->response_length - header_length;
    return 0;
  }

  {
    uint8_t *source = header_end;
    uint8_t *target = header_end;
    uint8_t *end = &cloud->response[cloud->response_length];
    while (source < end)
    {
      char *line_end;
      unsigned long chunk_length;
      cloud->response[cloud->response_length] = 0U;
      line_end = strstr((char *)source, "\r\n");
      if ((line_end == NULL) || ((uint8_t *)line_end >= end)) return -1;
      *line_end = '\0';
      chunk_length = strtoul((char *)source, NULL, 16);
      source = (uint8_t *)line_end + 2U;
      if (chunk_length == 0U) break;
      if ((chunk_length > (unsigned long)(end - source)) ||
          (source + chunk_length + 2U > end)) return -1;
      (void)memmove(target, source, chunk_length);
      target += chunk_length;
      source += chunk_length;
      if ((source[0] != '\r') || (source[1] != '\n')) return -1;
      source += 2U;
    }
    *body = header_end;
    *body_length = (size_t)(target - header_end);
    *target = 0U;
  }
  return 0;
}

static void cloud_finish_request(void)
{
  CloudHttpKind_t kind = cloud->http_kind;
  uint8_t *body = NULL;
  size_t body_length = 0U;
  int status = 0;
  int parsed = cloud_decode_response(&status, &body, &body_length);
  cloud_close_socket();
  cloud->status.request_active = 0U;
  if (parsed != 0)
  {
    cloud->status.last_transport_status = -22;
    cloud_backoff();
    return;
  }
  cloud->status.last_http_status = status;
  cloud->backoff_step = 0U;
  cloud->status.backoff_seconds = 0U;
  cloud->status.last_transport_status = 0;

  if (status == 409)
  {
    cloud->next_action_tick = HAL_GetTick() + 30000U;
    cloud->status.backoff_seconds = 30U;
    cloud->status.state = CLOUD_RELAY_STATE_BACKOFF;
    return;
  }
  if ((status == 401) || (status == 403))
  {
    cloud->status.state = CLOUD_RELAY_STATE_ERROR;
    cloud->next_action_tick = HAL_GetTick() + 30000U;
    return;
  }

  switch (kind)
  {
    case CLOUD_HTTP_PAIR:
      if ((status == 200) && (cloud_parse_pair_response(body, body_length) == 0))
      {
        cloud->pair_pending = 0U;
        (void)memset(cloud->pair_code, 0, sizeof(cloud->pair_code));
        cloud->status.paired = 1U;
        cloud->status.state = CLOUD_RELAY_STATE_CONNECTING;
        cloud->status.generation++;
        (void)cloud_save_pairing();
      }
      else
      {
        cloud->pair_pending = 0U;
        (void)memset(cloud->pair_code, 0, sizeof(cloud->pair_code));
        cloud->status.request_errors++;
        cloud->status.state = CLOUD_RELAY_STATE_UNPAIRED;
      }
      break;
    case CLOUD_HTTP_POLL:
      if (status == 204)
      {
        cloud->status.state = CLOUD_RELAY_STATE_POLLING;
      }
      else if ((status == 200) && (cloud_parse_command(body, body_length) == 0))
      {
        cloud->status.commands_received++;
      }
      else
      {
        cloud_backoff();
        return;
      }
      break;
    case CLOUD_HTTP_ACK:
      if (status == 204)
      {
        cloud->ack_pending = 0U;
        cloud->status.commands_acked++;
      }
      else
      {
        cloud_backoff();
        return;
      }
      break;
    case CLOUD_HTTP_OUTPUT:
      if (status == 202)
      {
        CloudOutputSlot_t *slot = &cloud->output[cloud->output_head];
        uint32_t completed = slot->completed;
        UINT posture;
        cloud->output_sequence++;
        (void)memset(slot, 0, sizeof(*slot));
        /* Match the producer's short publication critical section: the
         * consumer must not overwrite a concurrent count increment. */
        posture = tx_interrupt_control(TX_INT_DISABLE);
        cloud->output_head = (cloud->output_head + 1U) % CLOUD_OUTPUT_SLOT_COUNT;
        if (cloud->output_count != 0U) cloud->output_count--;
        (void)tx_interrupt_control(posture);
        cloud->status.output_records++;
        if (completed != 0U)
        {
          cloud->active_command_id[0] = '\0';
          cloud->hold_command = 0U;
          cloud->output_sequence = 0U;
        }
      }
      else
      {
        cloud_backoff();
        return;
      }
      break;
    case CLOUD_HTTP_TOF:
      if ((status == 202) || (status == 204)) cloud->status.tof_frames_sent++;
      else cloud->status.tof_frames_dropped++;
      break;
    default:
      break;
  }
  cloud->next_action_tick = HAL_GetTick();
}

static void cloud_start_next_request(void)
{
  char body[900];
  char path[180];
  int length;

  if (cloud->pair_pending != 0U)
  {
    length = snprintf(body, sizeof(body),
                      "{\"code\":\"%s\",\"deviceId\":\"%s\","
                      "\"name\":\"%s\",\"firmwareVersion\":\"%s\"}",
                      cloud->pair_code, cloud->status.device_id,
                      cloud->status.device_id, NATI_LAB_FIRMWARE_VERSION_TEXT);
    if ((length > 0) && ((size_t)length < sizeof(body)) &&
        (cloud_begin_request(CLOUD_HTTP_PAIR, "POST", "/api/device/pair",
                             "application/json", body, (size_t)length,
                             NULL, 0U, 0U) == 0)) return;
    cloud_backoff();
    return;
  }

  if (cloud->pairing.magic != CLOUD_RECORD_MAGIC)
  {
    cloud->status.state = CLOUD_RELAY_STATE_UNPAIRED;
    cloud->next_action_tick = HAL_GetTick() + 1000U;
    return;
  }

  if (cloud->ack_pending != 0U)
  {
    length = snprintf(body, sizeof(body), "{\"sequence\":%lu}",
                      (unsigned long)cloud->ack_sequence);
    (void)snprintf(path, sizeof(path), "/api/device/commands/%s/ack",
                   cloud->ack_command_id);
    if ((length > 0) && (cloud_begin_request(
            CLOUD_HTTP_ACK, "POST", path, "application/json", body,
            (size_t)length, NULL, 0U, 1U) == 0)) return;
    cloud_backoff();
    return;
  }

  if (cloud->output_count != 0U)
  {
    CloudOutputSlot_t *slot = &cloud->output[cloud->output_head];
    char encoded[520];
    if (slot->binary != 0U)
    {
      if (cloud_base64_encode(slot->data, slot->length,
                              encoded, sizeof(encoded)) < 0)
      {
        cloud_backoff();
        return;
      }
      length = snprintf(body, sizeof(body),
                        "{\"kind\":\"binary\",\"sequence\":%lu,"
                        "\"dataBase64\":\"%s\",\"offset\":0,"
                        "\"crc32\":\"%08lx\",\"completed\":%s}",
                        (unsigned long)cloud->output_sequence, encoded,
                        (unsigned long)cloud_crc32(slot->data, slot->length),
                        (slot->completed != 0U) ? "true" : "false");
    }
    else
    {
      if (cloud_json_escape(slot->data, slot->length,
                            encoded, sizeof(encoded)) < 0)
      {
        cloud_backoff();
        return;
      }
      length = snprintf(body, sizeof(body),
                        "{\"kind\":\"text\",\"sequence\":%lu,"
                        "\"text\":\"%s\",\"completed\":%s}",
                        (unsigned long)cloud->output_sequence, encoded,
                        (slot->completed != 0U) ? "true" : "false");
    }
    (void)snprintf(path, sizeof(path), "/api/device/commands/%s/output",
                   cloud->active_command_id);
    if ((length > 0) && ((size_t)length < sizeof(body)) &&
        (cloud_begin_request(CLOUD_HTTP_OUTPUT, "POST", path,
                             "application/json", body, (size_t)length,
                             NULL, 0U, 1U) == 0))
    {
      return;
    }
    cloud_backoff();
    return;
  }

  if (cloud->tof_pending != 0U)
  {
    cloud_store_u16(&cloud->tof_header[0], 0x364EU);
    cloud->tof_header[2] = 1U;
    cloud->tof_header[3] = 3U;
    cloud_store_u32(&cloud->tof_header[4], cloud->tof_frame_id);
    cloud_store_u16(&cloud->tof_header[8], 0U);
    cloud_store_u16(&cloud->tof_header[10], cloud->tof_payload_length);
    cloud->tof_header[12] = cloud->tof_width;
    cloud->tof_header[13] = cloud->tof_height;
    cloud->tof_header[14] = cloud->tof_channel_id;
    cloud->tof_header[15] = 1U;
    cloud_store_u32(&cloud->tof_header[16], cloud->tof_payload_crc32);
    if (cloud_begin_request(CLOUD_HTTP_TOF, "POST", "/api/device/tof/frames",
                            "application/octet-stream", cloud->tof_header,
                            sizeof(cloud->tof_header), cloud->tof_payload,
                            cloud->tof_payload_length, 1U) == 0)
    {
      cloud_release_tof();
      return;
    }
    cloud_release_tof();
    cloud->status.tof_frames_dropped++;
    cloud_backoff();
    return;
  }

  if ((cloud->hold_command == 0U) &&
      (cloud->input_ready == 0U) && (cloud->ack_pending == 0U))
  {
    if (cloud_begin_request(CLOUD_HTTP_POLL, "GET",
                            "/api/device/commands?waitSeconds=1",
                            "application/json", NULL, 0U, NULL, 0U, 1U) == 0)
    {
      return;
    }
    cloud_backoff();
  }
}

static int cloud_load_pairing(void)
{
  uint32_t size = 0U;
  uint32_t crc;
  if ((W6X_FS_GetSizeFile(cloud_pair_file, &size) != W6X_STATUS_OK) ||
      (size != sizeof(cloud->pairing)) ||
      (W6X_FS_ReadFile(cloud_pair_file, 0U, (uint8_t *)&cloud->pairing,
                       sizeof(cloud->pairing)) != W6X_STATUS_OK))
  {
    cloud_clear_pairing(0U);
    return -1;
  }
  crc = cloud->pairing.crc32;
  cloud->pairing.crc32 = 0U;
  if ((cloud->pairing.magic != CLOUD_RECORD_MAGIC) ||
      (cloud->pairing.version != CLOUD_RECORD_VERSION) ||
      (cloud->pairing.length != sizeof(cloud->pairing)) ||
      (cloud_crc32(&cloud->pairing, sizeof(cloud->pairing)) != crc) ||
      (memchr(cloud->pairing.device_id, '\0', sizeof(cloud->pairing.device_id)) == NULL) ||
      (memchr(cloud->pairing.workspace_id, '\0', sizeof(cloud->pairing.workspace_id)) == NULL) ||
      (memchr(cloud->pairing.token, '\0', sizeof(cloud->pairing.token)) == NULL))
  {
    cloud_clear_pairing(0U);
    return -1;
  }
  cloud->pairing.crc32 = crc;
  cloud->status.enabled = cloud->pairing.enabled;
  cloud->status.paired = 1U;
  (void)snprintf(cloud->status.device_id, sizeof(cloud->status.device_id),
                 "%s", cloud->pairing.device_id);
  (void)snprintf(cloud->status.workspace_id, sizeof(cloud->status.workspace_id),
                 "%s", cloud->pairing.workspace_id);
  return 0;
}

static int cloud_save_pairing(void)
{
  CloudPairingRecord_t verify;
  cloud->pairing.magic = CLOUD_RECORD_MAGIC;
  cloud->pairing.version = CLOUD_RECORD_VERSION;
  cloud->pairing.length = sizeof(cloud->pairing);
  cloud->pairing.enabled = cloud->status.enabled;
  cloud->pairing.crc32 = 0U;
  cloud->pairing.crc32 = cloud_crc32(&cloud->pairing, sizeof(cloud->pairing));
  if ((W6X_FS_WriteFileByContent(cloud_pair_file,
                                 (const char *)&cloud->pairing,
                                 sizeof(cloud->pairing)) != W6X_STATUS_OK) ||
      (W6X_FS_ReadFile(cloud_pair_file, 0U, (uint8_t *)&verify,
                       sizeof(verify)) != W6X_STATUS_OK) ||
      (memcmp(&verify, &cloud->pairing, sizeof(verify)) != 0))
  {
    return -1;
  }
  return 0;
}

static void cloud_clear_pairing(uint32_t delete_file)
{
  if (cloud == NULL) return;
  (void)memset(&cloud->pairing, 0, sizeof(cloud->pairing));
  cloud->status.paired = 0U;
  cloud->status.workspace_id[0] = '\0';
  cloud->active_command_id[0] = '\0';
  cloud->hold_command = 0U;
  cloud->input_ready = 0U;
  cloud->input_delivered = 0U;
  cloud->ack_pending = 0U;
  cloud->output_count = 0U;
  cloud->output_head = 0U;
  cloud->output_tail = 0U;
  if (delete_file != 0U) (void)W6X_FS_DeleteFile(cloud_pair_file);
}

static int cloud_parse_pair_response(const uint8_t *body, size_t length)
{
  char device_id[65];
  char workspace_id[65];
  char token[CLOUD_TOKEN_SIZE];
  if ((json_get_string(body, length, "deviceId", device_id,
                       sizeof(device_id)) != 0) ||
      (json_get_string(body, length, "workspaceId", workspace_id,
                       sizeof(workspace_id)) != 0) ||
      (json_get_string(body, length, "deviceToken", token,
                       sizeof(token)) != 0)) return -1;

  (void)memset(&cloud->pairing, 0, sizeof(cloud->pairing));
  (void)snprintf(cloud->pairing.device_id, sizeof(cloud->pairing.device_id),
                 "%s", device_id);
  (void)snprintf(cloud->pairing.workspace_id,
                 sizeof(cloud->pairing.workspace_id), "%s", workspace_id);
  (void)snprintf(cloud->pairing.token, sizeof(cloud->pairing.token), "%s", token);
  (void)snprintf(cloud->status.device_id, sizeof(cloud->status.device_id),
                 "%s", device_id);
  (void)snprintf(cloud->status.workspace_id, sizeof(cloud->status.workspace_id),
                 "%s", workspace_id);
  cloud->pairing.magic = CLOUD_RECORD_MAGIC;
  cloud->pairing.enabled = 1U;
  return 0;
}

static int cloud_parse_command(const uint8_t *body, size_t length)
{
  CloudRelay_Input_t input;
  char kind[12];
  char encoded[1600];
  char crc_text[12];
  uint32_t expected_crc;
  size_t decoded_length;

  (void)memset(&input, 0, sizeof(input));
  if ((json_get_string(body, length, "id", input.command_id,
                       sizeof(input.command_id)) != 0) ||
      (json_get_string(body, length, "kind", kind, sizeof(kind)) != 0) ||
      (json_get_u32(body, length, "sequence", &input.sequence) != 0) ||
      (json_get_bool(body, length, "completed", &input.completed) != 0))
  {
    return -1;
  }

  if (strcmp(kind, "text") == 0)
  {
    char line[CLOUD_RELAY_INPUT_MAX - 2U];
    if (json_get_string(body, length, "line", line, sizeof(line)) != 0) return -1;
    input.length = (uint32_t)strlen(line);
    (void)memcpy(input.data, line, input.length);
    input.data[input.length++] = '\r';
    input.data[input.length++] = '\n';
    input.binary = 0U;
    (void)snprintf(cloud->active_command_id,
                   sizeof(cloud->active_command_id), "%s", input.command_id);
    cloud->output_sequence = 0U;
  }
  else if (strcmp(kind, "binary") == 0)
  {
    if ((json_get_string(body, length, "dataBase64", encoded,
                         sizeof(encoded)) != 0) ||
        (json_get_string(body, length, "crc32", crc_text,
                         sizeof(crc_text)) != 0) ||
        (json_get_u32(body, length, "offset", &input.offset) != 0) ||
        (cloud_base64_decode(encoded, input.data, sizeof(input.data),
                             &decoded_length) != 0)) return -1;
    expected_crc = (uint32_t)strtoul(crc_text, NULL, 16);
    if (cloud_crc32(input.data, decoded_length) != expected_crc) return -1;
    input.length = (uint32_t)decoded_length;
    input.binary = 1U;
    if (strcmp(cloud->active_command_id, input.command_id) != 0) return -1;
  }
  else return -1;

  if (tx_mutex_get(&cloud->gate, TX_NO_WAIT) != TX_SUCCESS) return -1;
  if (cloud->input_ready != 0U)
  {
    cloud->status.duplicate_records++;
    (void)tx_mutex_put(&cloud->gate);
    return -1;
  }
  cloud->input = input;
  cloud->input_ready = 1U;
  cloud->input_delivered = 0U;
  (void)tx_mutex_put(&cloud->gate);
  return 0;
}

static const uint8_t *json_find_value(const uint8_t *json, size_t length,
                                      const char *key)
{
  size_t key_length = strlen(key);
  size_t index = 0U;
  while (index < length)
  {
    if (json[index] != '"') { index++; continue; }
    index++;
    size_t start = index;
    uint32_t escaped = 0U;
    while (index < length)
    {
      if ((json[index] == '"') && (escaped == 0U)) break;
      if ((json[index] == '\\') && (escaped == 0U)) escaped = 1U;
      else escaped = 0U;
      index++;
    }
    if (index >= length) return NULL;
    if (((index - start) == key_length) &&
        (memcmp(&json[start], key, key_length) == 0))
    {
      index++;
      while ((index < length) && isspace((unsigned char)json[index])) index++;
      if ((index >= length) || (json[index] != ':')) return NULL;
      index++;
      while ((index < length) && isspace((unsigned char)json[index])) index++;
      return (index < length) ? &json[index] : NULL;
    }
    index++;
  }
  return NULL;
}

static int json_get_string(const uint8_t *json, size_t length,
                           const char *key, char *value, size_t capacity)
{
  const uint8_t *cursor = json_find_value(json, length, key);
  const uint8_t *end = json + length;
  size_t output = 0U;
  if ((cursor == NULL) || (cursor >= end) || (*cursor++ != '"') ||
      (capacity == 0U)) return -1;
  while (cursor < end)
  {
    uint8_t byte = *cursor++;
    if (byte == '"')
    {
      value[output] = '\0';
      return 0;
    }
    if (byte == '\\')
    {
      if (cursor >= end) return -1;
      byte = *cursor++;
      if (byte == 'n') byte = '\n';
      else if (byte == 'r') byte = '\r';
      else if (byte == 't') byte = '\t';
      else if ((byte != '"') && (byte != '\\') && (byte != '/')) return -1;
    }
    if ((byte < 0x20U) || (output + 1U >= capacity)) return -1;
    value[output++] = (char)byte;
  }
  return -1;
}

static int json_get_u32(const uint8_t *json, size_t length,
                        const char *key, uint32_t *value)
{
  const uint8_t *cursor = json_find_value(json, length, key);
  const uint8_t *end = json + length;
  uint32_t result = 0U;
  uint32_t digits = 0U;
  if ((cursor == NULL) || (value == NULL)) return -1;
  while ((cursor < end) && isdigit((unsigned char)*cursor))
  {
    if (result > (UINT32_MAX - (uint32_t)(*cursor - '0')) / 10U) return -1;
    result = result * 10U + (uint32_t)(*cursor++ - '0');
    digits++;
  }
  if (digits == 0U) return -1;
  *value = result;
  return 0;
}

static int json_get_bool(const uint8_t *json, size_t length,
                         const char *key, uint32_t *value)
{
  const uint8_t *cursor = json_find_value(json, length, key);
  if ((cursor == NULL) || (value == NULL)) return -1;
  if (((size_t)(json + length - cursor) >= 4U) &&
      (memcmp(cursor, "true", 4U) == 0)) { *value = 1U; return 0; }
  if (((size_t)(json + length - cursor) >= 5U) &&
      (memcmp(cursor, "false", 5U) == 0)) { *value = 0U; return 0; }
  return -1;
}

static int cloud_json_escape(const uint8_t *source, size_t length,
                             char *target, size_t capacity)
{
  size_t output = 0U;
  for (size_t index = 0U; index < length; ++index)
  {
    const char *escape = NULL;
    char unicode[7];
    if (source[index] == '"') escape = "\\\"";
    else if (source[index] == '\\') escape = "\\\\";
    else if (source[index] == '\r') escape = "\\r";
    else if (source[index] == '\n') escape = "\\n";
    else if (source[index] == '\t') escape = "\\t";
    else if (source[index] < 0x20U)
    {
      (void)snprintf(unicode, sizeof(unicode), "\\u%04x", source[index]);
      escape = unicode;
    }
    if (escape != NULL)
    {
      size_t escape_length = strlen(escape);
      if (output + escape_length >= capacity) return -1;
      (void)memcpy(&target[output], escape, escape_length);
      output += escape_length;
    }
    else
    {
      if (output + 1U >= capacity) return -1;
      target[output++] = (char)source[index];
    }
  }
  target[output] = '\0';
  return (int)output;
}

static int cloud_base64_encode(const uint8_t *source, size_t length,
                               char *target, size_t capacity)
{
  static const char alphabet[] =
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  size_t output = 0U;
  for (size_t index = 0U; index < length; index += 3U)
  {
    uint32_t value = (uint32_t)source[index] << 16U;
    size_t remaining = length - index;
    if (remaining > 1U) value |= (uint32_t)source[index + 1U] << 8U;
    if (remaining > 2U) value |= source[index + 2U];
    if (output + 4U >= capacity) return -1;
    target[output++] = alphabet[(value >> 18U) & 0x3FU];
    target[output++] = alphabet[(value >> 12U) & 0x3FU];
    target[output++] = (remaining > 1U) ? alphabet[(value >> 6U) & 0x3FU] : '=';
    target[output++] = (remaining > 2U) ? alphabet[value & 0x3FU] : '=';
  }
  target[output] = '\0';
  return (int)output;
}

static int cloud_base64_value(char character)
{
  if ((character >= 'A') && (character <= 'Z')) return character - 'A';
  if ((character >= 'a') && (character <= 'z')) return character - 'a' + 26;
  if ((character >= '0') && (character <= '9')) return character - '0' + 52;
  if (character == '+') return 62;
  if (character == '/') return 63;
  return -1;
}

static int cloud_base64_decode(const char *source, uint8_t *target,
                               size_t capacity, size_t *length)
{
  size_t input_length = strlen(source);
  size_t output = 0U;
  if ((input_length == 0U) || ((input_length % 4U) != 0U)) return -1;
  for (size_t index = 0U; index < input_length; index += 4U)
  {
    int a = cloud_base64_value(source[index]);
    int b = cloud_base64_value(source[index + 1U]);
    int c = (source[index + 2U] == '=') ? 0 : cloud_base64_value(source[index + 2U]);
    int d = (source[index + 3U] == '=') ? 0 : cloud_base64_value(source[index + 3U]);
    uint32_t value;
    if ((a < 0) || (b < 0) || (c < 0) || (d < 0)) return -1;
    value = ((uint32_t)a << 18U) | ((uint32_t)b << 12U) |
            ((uint32_t)c << 6U) | (uint32_t)d;
    if (output >= capacity) return -1;
    target[output++] = (uint8_t)(value >> 16U);
    if (source[index + 2U] != '=')
    {
      if (output >= capacity) return -1;
      target[output++] = (uint8_t)(value >> 8U);
    }
    if (source[index + 3U] != '=')
    {
      if (output >= capacity) return -1;
      target[output++] = (uint8_t)value;
    }
  }
  *length = output;
  return 0;
}

static const uint8_t *cloud_find_ci(const uint8_t *haystack, size_t haystack_length,
                                    const char *needle)
{
  size_t needle_length = strlen(needle);
  if (needle_length == 0U) return haystack;
  for (size_t index = 0U; index + needle_length <= haystack_length; ++index)
  {
    size_t offset;
    for (offset = 0U; offset < needle_length; ++offset)
    {
      if (tolower((unsigned char)haystack[index + offset]) !=
          tolower((unsigned char)needle[offset])) break;
    }
    if (offset == needle_length) return &haystack[index];
  }
  return NULL;
}

#else

UINT CloudRelay_Initialize(TX_BYTE_POOL *pool, const char *suggested_device_id)
{ (void)pool; (void)suggested_device_id; return TX_NOT_AVAILABLE; }
UINT CloudRelay_Prepare(void) { return TX_NOT_AVAILABLE; }
void CloudRelay_Run(void) { }
void CloudRelay_SetNetworkState(uint32_t ready, uint32_t wifi_has_ip)
{ (void)ready; (void)wifi_has_ip; }
void CloudRelay_GetStatus(CloudRelay_Status_t *status)
{ if (status != NULL) (void)memset(status, 0, sizeof(*status)); }
UINT CloudRelay_RequestPair(const char *code) { (void)code; return TX_NOT_AVAILABLE; }
UINT CloudRelay_SetEnabled(uint32_t enabled) { (void)enabled; return TX_NOT_AVAILABLE; }
UINT CloudRelay_RequestReconnect(void) { return TX_NOT_AVAILABLE; }
UINT CloudRelay_Unpair(void) { return TX_NOT_AVAILABLE; }
UINT CloudRelay_ReadInput(CloudRelay_Input_t *input) { (void)input; return TX_QUEUE_EMPTY; }
UINT CloudRelay_AcknowledgeInput(const CloudRelay_Input_t *input,
                                  uint32_t hold_command)
{ (void)input; (void)hold_command; return TX_NOT_AVAILABLE; }
UINT CloudRelay_WriteOutput(const void *data, size_t length, uint32_t binary)
{ (void)data; (void)length; (void)binary; return TX_NOT_AVAILABLE; }
UINT CloudRelay_TryWriteOutput(const void *data, size_t length,
                               uint32_t binary)
{ (void)data; (void)length; (void)binary; return TX_NOT_AVAILABLE; }
UINT CloudRelay_CompleteCommand(void) { return TX_NOT_AVAILABLE; }
UINT CloudRelay_SubmitTofFrame(uint32_t frame_id, uint8_t channel_id,
                               const uint8_t *payload, uint8_t width,
                               uint8_t height, uint32_t payload_crc32)
{ (void)frame_id; (void)channel_id; (void)payload; (void)width; (void)height; (void)payload_crc32; return TX_NOT_AVAILABLE; }
uint32_t CloudRelay_IsTofFramePending(uint32_t frame_id) { (void)frame_id; return 0U; }

#endif
