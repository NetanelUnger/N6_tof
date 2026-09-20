#include "cloud_relay.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "app_features.h"
#include "firmware_build_version.h"
#include "main.h"
#include "w6x_api.h"

#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)

#define CLOUD_CONTEXT_BUDGET       (9U * 1024U)
#define CLOUD_RESPONSE_SIZE        (2400U)
#define CLOUD_REQUEST_SIZE         (1200U)
#define CLOUD_OUTPUT_SLOT_COUNT    (4U)
#define CLOUD_OUTPUT_SLOT_SIZE     (384U)
#define CLOUD_TOKEN_SIZE           (1025U)
#define CLOUD_TLS_TAG              (7U)
#define CLOUD_HTTP_PORT            (443U)
#define CLOUD_HTTP_TIMEOUT_MS      (4500U)
#define CLOUD_RECV_TIMEOUT_MS      (100U)
#define CLOUD_BACKOFF_MAX_SECONDS  (60U)
#define CLOUD_RECORD_MAGIC         (0x434C364EU) /* N6LC */
#define CLOUD_RECORD_VERSION       (1U)
#define CLOUD_CA_FILE              "n6dg2.pem"

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
  uint32_t output_sequence;
  CloudOutputSlot_t output[CLOUD_OUTPUT_SLOT_COUNT];
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
static char cloud_pair_file[W6X_SYS_FS_FILENAME_SIZE] = "n6cloud.cfg";

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
  cloud->socket = -1;
  cloud->status.enabled = 1U;
  cloud->status.state = CLOUD_RELAY_STATE_WAIT_WIFI;
  if (tx_mutex_create(&cloud->gate, "N6 cloud relay", TX_INHERIT) != TX_SUCCESS)
  {
    (void)tx_byte_release(memory);
    cloud = NULL;
    return TX_MUTEX_ERROR;
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
  return TX_SUCCESS;
}

void CloudRelay_Process(uint32_t wifi_has_ip)
{
  if (cloud == NULL) return;

  if ((cloud->status.enabled == 0U) || (wifi_has_ip == 0U))
  {
    cloud_close_socket();
    if (wifi_has_ip == 0U)
    {
      cloud->time_configured = 0U;
      cloud->time_ready = 0U;
    }
    cloud->status.state = (cloud->status.enabled != 0U) ?
        CLOUD_RELAY_STATE_WAIT_WIFI : CLOUD_RELAY_STATE_DISABLED;
    return;
  }

  /* The NCP validates the Azure certificate. Ensure its clock is trustworthy
   * before the first TLS handshake instead of silently accepting an unknown
   * certificate time. */
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

  (void)tx_mutex_get(&cloud->gate, TX_WAIT_FOREVER);
  *status = cloud->status;
  status->paired = (cloud->pairing.magic == CLOUD_RECORD_MAGIC) ? 1U : 0U;
  status->input_ready = cloud->input_ready;
  status->output_queued = cloud->output_count;
  status->request_active = (cloud->http_kind != CLOUD_HTTP_NONE) ? 1U : 0U;
  (void)snprintf(status->workspace_id, sizeof(status->workspace_id), "%s",
                 cloud->pairing.workspace_id);
  (void)tx_mutex_put(&cloud->gate);
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

  (void)tx_mutex_get(&cloud->gate, TX_WAIT_FOREVER);
  (void)memcpy(cloud->pair_code, code, length + 1U);
  cloud->pair_pending = 1U;
  cloud->next_action_tick = HAL_GetTick();
  (void)tx_mutex_put(&cloud->gate);
  return TX_SUCCESS;
}

UINT CloudRelay_SetEnabled(uint32_t enabled)
{
  if (cloud == NULL) return TX_NOT_AVAILABLE;
  cloud->status.enabled = (enabled != 0U) ? 1U : 0U;
  cloud->pairing.enabled = cloud->status.enabled;
  if (cloud->pairing.magic == CLOUD_RECORD_MAGIC) (void)cloud_save_pairing();
  if (enabled == 0U) cloud_close_socket();
  else cloud->next_action_tick = HAL_GetTick();
  return TX_SUCCESS;
}

UINT CloudRelay_RequestReconnect(void)
{
  if (cloud == NULL) return TX_NOT_AVAILABLE;
  cloud_close_socket();
  cloud->address_valid = 0U;
  cloud->backoff_step = 0U;
  cloud->status.backoff_seconds = 0U;
  cloud->status.generation++;
  cloud->next_action_tick = HAL_GetTick();
  return TX_SUCCESS;
}

UINT CloudRelay_Unpair(void)
{
  if (cloud == NULL) return TX_NOT_AVAILABLE;
  cloud_close_socket();
  cloud_clear_pairing(1U);
  cloud->status.generation++;
  return TX_SUCCESS;
}

UINT CloudRelay_ReadInput(CloudRelay_Input_t *input)
{
  if ((cloud == NULL) || (input == NULL)) return TX_PTR_ERROR;
  (void)tx_mutex_get(&cloud->gate, TX_WAIT_FOREVER);
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

UINT CloudRelay_AcknowledgeInput(const CloudRelay_Input_t *input)
{
  if ((cloud == NULL) || (input == NULL)) return TX_PTR_ERROR;
  (void)tx_mutex_get(&cloud->gate, TX_WAIT_FOREVER);
  if (cloud->ack_pending != 0U)
  {
    (void)tx_mutex_put(&cloud->gate);
    return TX_NOT_AVAILABLE;
  }
  (void)snprintf(cloud->ack_command_id, sizeof(cloud->ack_command_id), "%s",
                 input->command_id);
  cloud->ack_sequence = input->sequence;
  cloud->ack_pending = 1U;
  cloud->input_ready = 0U;
  cloud->input_delivered = 0U;
  (void)tx_mutex_put(&cloud->gate);
  return TX_SUCCESS;
}

UINT CloudRelay_WriteOutput(const void *data, size_t length, uint32_t binary)
{
  const uint8_t *bytes = (const uint8_t *)data;
  uint32_t deadline = HAL_GetTick() + 15000U;
  if ((cloud == NULL) || ((data == NULL) && (length != 0U))) return TX_PTR_ERROR;
  if (cloud->active_command_id[0] == '\0') return TX_NOT_AVAILABLE;

  while (length != 0U)
  {
    size_t chunk = (length > CLOUD_OUTPUT_SLOT_SIZE) ?
        CLOUD_OUTPUT_SLOT_SIZE : length;
    CloudOutputSlot_t *slot;
    (void)tx_mutex_get(&cloud->gate, TX_WAIT_FOREVER);
    if (cloud->output_count >= CLOUD_OUTPUT_SLOT_COUNT)
    {
      (void)tx_mutex_put(&cloud->gate);
      if ((int32_t)(HAL_GetTick() - deadline) >= 0) return TX_QUEUE_FULL;
      tx_thread_sleep(1U);
      continue;
    }
    slot = &cloud->output[cloud->output_tail];
    slot->length = (uint16_t)chunk;
    slot->binary = (binary != 0U) ? 1U : 0U;
    slot->completed = 0U;
    (void)memcpy(slot->data, bytes, chunk);
    cloud->output_tail = (cloud->output_tail + 1U) % CLOUD_OUTPUT_SLOT_COUNT;
    cloud->output_count++;
    (void)tx_mutex_put(&cloud->gate);
    bytes += chunk;
    length -= chunk;
  }
  return TX_SUCCESS;
}

UINT CloudRelay_CompleteCommand(void)
{
  CloudOutputSlot_t *slot;
  if ((cloud == NULL) || (cloud->active_command_id[0] == '\0')) return TX_NOT_AVAILABLE;
  (void)tx_mutex_get(&cloud->gate, TX_WAIT_FOREVER);
  if (cloud->output_count >= CLOUD_OUTPUT_SLOT_COUNT)
  {
    (void)tx_mutex_put(&cloud->gate);
    return TX_QUEUE_FULL;
  }
  slot = &cloud->output[cloud->output_tail];
  (void)memset(slot, 0, sizeof(*slot));
  slot->completed = 1U;
  cloud->output_tail = (cloud->output_tail + 1U) % CLOUD_OUTPUT_SLOT_COUNT;
  cloud->output_count++;
  (void)tx_mutex_put(&cloud->gate);
  return TX_SUCCESS;
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
  (void)tx_mutex_get(&cloud->gate, TX_WAIT_FOREVER);
  if ((cloud->status.enabled == 0U) ||
      (cloud->pairing.magic != CLOUD_RECORD_MAGIC) ||
      (cloud->tof_pending != 0U))
  {
    cloud->status.tof_frames_dropped++;
    (void)tx_mutex_put(&cloud->gate);
    return TX_NOT_AVAILABLE;
  }
  cloud->tof_payload = payload;
  cloud->tof_frame_id = frame_id;
  cloud->tof_payload_crc32 = payload_crc32;
  cloud->tof_payload_length = (uint16_t)length;
  cloud->tof_width = width;
  cloud->tof_height = height;
  cloud->tof_channel_id = channel_id;
  cloud->tof_pending = 1U;
  (void)tx_mutex_put(&cloud->gate);
  return TX_SUCCESS;
}

uint32_t CloudRelay_IsTofFramePending(uint32_t frame_id)
{
  return ((cloud != NULL) && (cloud->tof_pending != 0U) &&
          (cloud->tof_frame_id == frame_id)) ? 1U : 0U;
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
  int32_t tags[1] = { CLOUD_TLS_TAG };
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
  if (cloud->ca_ready == 0U)
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

  cloud->socket = W6X_Net_Socket(AF_INET, SOCK_STREAM, IPPROTO_TLS_1_2);
  if (cloud->socket < 0) return -1;
  if ((W6X_Net_Setsockopt(cloud->socket, SOL_TLS, TLS_SEC_TAG_LIST,
                          tags, sizeof(tags)) != 0) ||
      (W6X_Net_Setsockopt(cloud->socket, SOL_TLS, TLS_HOSTNAME,
                          CLOUD_RELAY_HOST, strlen(CLOUD_RELAY_HOST)) != 0) ||
      (W6X_Net_Setsockopt(cloud->socket, SOL_SOCKET, SO_RCVTIMEO,
                          &timeout, sizeof(timeout)) != 0))
  {
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
        cloud->output_sequence++;
        (void)memset(slot, 0, sizeof(*slot));
        cloud->output_head = (cloud->output_head + 1U) % CLOUD_OUTPUT_SLOT_COUNT;
        if (cloud->output_count != 0U) cloud->output_count--;
        cloud->status.output_records++;
        if (completed != 0U)
        {
          cloud->active_command_id[0] = '\0';
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
      cloud->tof_pending = 0U;
      cloud->tof_payload = NULL;
      return;
    }
    cloud->tof_pending = 0U;
    cloud->tof_payload = NULL;
    cloud->status.tof_frames_dropped++;
    cloud_backoff();
    return;
  }

  if ((cloud->input_ready == 0U) && (cloud->ack_pending == 0U))
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

  (void)tx_mutex_get(&cloud->gate, TX_WAIT_FOREVER);
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
void CloudRelay_Process(uint32_t wifi_has_ip) { (void)wifi_has_ip; }
void CloudRelay_GetStatus(CloudRelay_Status_t *status)
{ if (status != NULL) (void)memset(status, 0, sizeof(*status)); }
UINT CloudRelay_RequestPair(const char *code) { (void)code; return TX_NOT_AVAILABLE; }
UINT CloudRelay_SetEnabled(uint32_t enabled) { (void)enabled; return TX_NOT_AVAILABLE; }
UINT CloudRelay_RequestReconnect(void) { return TX_NOT_AVAILABLE; }
UINT CloudRelay_Unpair(void) { return TX_NOT_AVAILABLE; }
UINT CloudRelay_ReadInput(CloudRelay_Input_t *input) { (void)input; return TX_QUEUE_EMPTY; }
UINT CloudRelay_AcknowledgeInput(const CloudRelay_Input_t *input) { (void)input; return TX_NOT_AVAILABLE; }
UINT CloudRelay_WriteOutput(const void *data, size_t length, uint32_t binary)
{ (void)data; (void)length; (void)binary; return TX_NOT_AVAILABLE; }
UINT CloudRelay_CompleteCommand(void) { return TX_NOT_AVAILABLE; }
UINT CloudRelay_SubmitTofFrame(uint32_t frame_id, uint8_t channel_id,
                               const uint8_t *payload, uint8_t width,
                               uint8_t height, uint32_t payload_crc32)
{ (void)frame_id; (void)channel_id; (void)payload; (void)width; (void)height; (void)payload_crc32; return TX_NOT_AVAILABLE; }
uint32_t CloudRelay_IsTofFramePending(uint32_t frame_id) { (void)frame_id; return 0U; }

#endif
