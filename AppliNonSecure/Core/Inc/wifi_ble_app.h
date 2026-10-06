#ifndef WIFI_BLE_APP_H
#define WIFI_BLE_APP_H

#include <stdint.h>

#include "app_route.h"
#include "tx_api.h"

#define WIFI_BLE_DEVICE_NAME_SIZE (26U)
#define WIFI_BLE_ADDRESS_SIZE     (6U)
#define WIFI_BLE_WIFI_SSID_SIZE   (33U)
#define WIFI_BLE_WIFI_PASSWORD_SIZE (64U) /* 63 characters plus NUL. */
#define WIFI_BLE_WIFI_SCAN_MAX_APS (15U)

typedef enum
{
  WIFI_BLE_WIFI_OPERATION_NONE = 0,
  WIFI_BLE_WIFI_OPERATION_SCAN,
  WIFI_BLE_WIFI_OPERATION_CONNECT,
  WIFI_BLE_WIFI_OPERATION_DISCONNECT
} WifiBle_WifiOperation_t;

/* The submit path must copy the complete request before returning; no field
 * borrows caller-owned storage. The producer must zero fields that do not
 * apply to the selected operation. Password is sensitive and the M3.4 worker
 * must scrub it immediately after consumption. */
typedef struct
{
  WifiBle_WifiOperation_t operation;
  AppRequestId_t request_id;
  AppRoute_t route;
  char ssid[WIFI_BLE_WIFI_SSID_SIZE];
  char password[WIFI_BLE_WIFI_PASSWORD_SIZE];
  uint32_t forget;
} WifiBle_WifiRequest_t;

typedef enum
{
  WIFI_BLE_STATE_DISABLED = 0,
  WIFI_BLE_STATE_STARTING,
  WIFI_BLE_STATE_READY,
  WIFI_BLE_STATE_ERROR
} WifiBle_State_t;

typedef enum
{
  WIFI_BLE_STREAM_CLI = 0,
  WIFI_BLE_STREAM_DEBUG,
  WIFI_BLE_STREAM_COUNT
} WifiBle_Stream_t;

/* The ToF image characteristic carries exact little-endian float32 samples.
 * A logical frame is split across self-describing BLE notifications; the
 * receiver must validate the complete payload CRC before displaying it. */
#define WIFI_BLE_TOF_IMAGE_UUID             "7a1e0004-b5a3-f393-e0a9-e50e24dcca9e"
#define WIFI_BLE_TOF_FRAGMENT_MAGIC         (0x364EU) /* bytes "N6" */
#define WIFI_BLE_TOF_FRAGMENT_VERSION       (1U)
#define WIFI_BLE_TOF_FRAGMENT_HEADER_SIZE   (20U)
#define WIFI_BLE_TOF_FRAGMENT_FLAG_START    (1U << 0)
#define WIFI_BLE_TOF_FRAGMENT_FLAG_END      (1U << 1)
#define WIFI_BLE_TOF_PIXEL_FORMAT_FLOAT32_LE (1U)

typedef struct
{
  uint32_t busy_count;
  uint32_t timeout_count;
  uint32_t current_streak;
  uint32_t peak_streak;
  uint32_t current_duration_ticks;
  uint32_t peak_duration_ticks;
  uint32_t recoveries;
} WifiBle_TxContentionStatus_t;

typedef struct
{
  uint32_t frames_submitted;
  uint32_t frames_sent;
  uint32_t frames_dropped_busy;
  uint32_t frames_aborted;
  uint32_t fragments_sent;
  uint32_t bytes_sent;
  uint32_t retries;
  uint32_t errors;
  uint32_t last_submitted_frame;
  uint32_t last_sent_frame;
  WifiBle_TxContentionStatus_t contention;
} WifiBle_TofImageStatus_t;

typedef struct
{
  uint32_t rx_queued;
  uint32_t rx_high_water;
  uint32_t rx_events;
  uint32_t rx_bytes;
  uint32_t rx_dropped_events;
  uint32_t rx_dropped_bytes;
  uint32_t tx_queued;
  uint32_t tx_high_water;
  uint32_t tx_messages;
  uint32_t tx_bytes;
  uint32_t tx_sent_bytes;
  uint32_t tx_dropped_messages;
  uint32_t tx_dropped_bytes;
  uint32_t tx_retries;
  uint32_t tx_errors;
  uint32_t stale_drops;
  WifiBle_TxContentionStatus_t contention;
} WifiBle_StreamStatus_t;

typedef enum
{
  WIFI_BLE_INIT_STAGE_IDLE = 0,
  WIFI_BLE_INIT_STAGE_STACK,
  WIFI_BLE_INIT_STAGE_ADDRESS,
  WIFI_BLE_INIT_STAGE_DEVICE_NAME,
  WIFI_BLE_INIT_STAGE_TX_POWER,
  WIFI_BLE_INIT_STAGE_ADV_PARAMS,
  WIFI_BLE_INIT_STAGE_ADV_DATA,
  WIFI_BLE_INIT_STAGE_SCAN_RESPONSE,
  WIFI_BLE_INIT_STAGE_CLI_SERVICE,
  WIFI_BLE_INIT_STAGE_DEBUG_SERVICE,
  WIFI_BLE_INIT_STAGE_CHARACTERISTICS,
  WIFI_BLE_INIT_STAGE_REGISTER,
  WIFI_BLE_INIT_STAGE_SECURITY,
  WIFI_BLE_INIT_STAGE_ADV_START,
  WIFI_BLE_INIT_STAGE_READY
} WifiBle_InitStage_t;

/* ADV has no state query in the ST67 AT contract. ACK is evidence that the
 * command was accepted, not proof that packets are present on the air. */
typedef enum
{
  WIFI_BLE_ADV_UNKNOWN = 0,
  WIFI_BLE_ADV_COMMAND_ACK,
  WIFI_BLE_ADV_CONNECTION_EVENT
} WifiBle_AdvEvidence_t;

typedef struct
{
  uint32_t init_attempts;
  uint32_t init_failures;
  uint32_t advertising_attempts;
  uint32_t advertising_failures;
  uint32_t disconnect_failures;
  uint32_t driver_error_callbacks;
  int32_t last_driver_error;
  uint32_t ble_mode_queries;
  uint32_t ble_link_queries;
  uint32_t ble_query_failures;
  uint32_t ble_link_corrections;
  uint32_t ble_recovery_attempts;
  uint32_t ble_recovery_failures;
  uint32_t advertising_retries_exhausted;
  uint32_t wifi_state_queries;
  uint32_t wifi_query_failures;
} WifiBle_ManagerHealth_t;

typedef struct
{
  WifiBle_State_t state;
  uint32_t wifi_connected;
  uint32_t wifi_has_ip;
  uint32_t wifi_state_confirmed;
  uint32_t wifi_last_probe_tick;
  int32_t wifi_last_probe_status;
  uint32_t loop_count;
  /* Legacy field names: all four values below come from HAL_GetTick()
   * and therefore use milliseconds, not ThreadX scheduler ticks. */
  uint32_t last_loop_tick;
  uint32_t max_loop_gap_ticks;
  uint32_t last_ble_tx_tick;
  uint32_t max_ble_tx_gap_ticks;
  uint32_t ble_gatt_ready;
  uint32_t ble_connected;
  uint32_t ble_advertising;
  uint32_t ble_advertising_desired;
  WifiBle_AdvEvidence_t ble_advertising_evidence;
  uint32_t ble_advertising_retry_count;
  uint32_t ble_recovery_pending;
  uint32_t ble_mode_confirmed;
  uint32_t ble_link_confirmed;
  uint32_t ble_last_probe_tick;
  int32_t ble_last_probe_status;
  uint32_t ble_connection_handle;
  uint32_t ble_mtu;
  uint32_t ble_cli_tx_subscribed;
  uint32_t ble_debug_tx_subscribed;
  uint32_t ble_tof_image_subscribed;
  uint32_t ble_rx_write_events;
  uint32_t ble_rx_discarded_bytes;
  uint32_t ble_session_generation;
  uint32_t ble_att_payload_limit;
  uint32_t ble_transport_ready;
  uint32_t ble_radio_pool_available;
  uint32_t ble_radio_pool_fragments;
  uint32_t ble_init_stage;
  int32_t ble_last_status;
  WifiBle_ManagerHealth_t manager_health;
  WifiBle_StreamStatus_t ble_stream[WIFI_BLE_STREAM_COUNT];
  WifiBle_TofImageStatus_t ble_tof_image;
  char ble_device_name[WIFI_BLE_DEVICE_NAME_SIZE];
  uint8_t ble_address[WIFI_BLE_ADDRESS_SIZE];
} WifiBle_RuntimeStatus_t;

typedef enum
{
  WIFI_BLE_EXTI9_OWNER_TOF = 0,
  WIFI_BLE_EXTI9_OWNER_RADIO
} WifiBle_Exti9Owner_t;

typedef struct
{
  uint32_t radio_enabled;
  uint32_t wifi_services_enabled;
  uint32_t ble_gatt_enabled;
  uint32_t spi_initialized;
  uint32_t spi_rx_dma_ready;
  uint32_t spi_tx_dma_ready;
  uint32_t chip_enable_level;
  uint32_t boot_level;
  uint32_t chip_select_level;
  uint32_t spi_ready_level;
  WifiBle_Exti9Owner_t exti9_owner;
} WifiBle_HardwareStatus_t;

typedef struct
{
  char ssid[WIFI_BLE_WIFI_SSID_SIZE];
  uint8_t mac[6];
  uint32_t security;
  uint32_t protocol;
  int32_t rssi;
  uint8_t channel;
} WifiBle_WifiAccessPoint_t;

typedef struct
{
  int32_t status;
  uint32_t count;
  WifiBle_WifiAccessPoint_t access_points[WIFI_BLE_WIFI_SCAN_MAX_APS];
} WifiBle_WifiScanResults_t;

typedef struct
{
  uint32_t connected;
  uint32_t has_ip;
  uint32_t ip_valid;
  uint32_t operation_active;
  uint32_t station_state;
  int32_t last_status;
  char ssid[WIFI_BLE_WIFI_SSID_SIZE];
  uint8_t ap_mac[6];
  uint32_t channel;
  int32_t rssi;
  uint8_t ip_address[4];
  uint8_t gateway_address[4];
  uint8_t netmask_address[4];
} WifiBle_WifiStatus_t;

/* A result is a self-contained snapshot and never refers back to a request
 * slot. The producer must zero snapshots and fields that are not relevant to
 * the completed operation. */
typedef struct
{
  WifiBle_WifiOperation_t operation;
  AppRequestId_t request_id;
  AppRoute_t route;
  int32_t final_status;
  WifiBle_WifiStatus_t wifi_status;
  WifiBle_WifiScanResults_t scan_results;
} WifiBle_WifiResult_t;

void WIFI_BLE_App_ConfigureHardware(void);
void WIFI_BLE_App_Run(void);
void WIFI_BLE_App_WifiControlRun(void);
WifiBle_State_t WIFI_BLE_App_GetState(void);
void WIFI_BLE_App_GetRuntimeStatus(WifiBle_RuntimeStatus_t *status);
void WIFI_BLE_App_GetHardwareStatus(WifiBle_HardwareStatus_t *status);
UINT WIFI_BLE_App_RequestAdvertising(uint32_t advertising);
UINT WIFI_BLE_App_RequestDisconnect(void);
void WIFI_BLE_App_GetWifiStatus(WifiBle_WifiStatus_t *status);
UINT WIFI_BLE_App_WifiSubmit(const WifiBle_WifiRequest_t *request,
                             AppRequestId_t *request_id);
UINT WIFI_BLE_App_WifiReceiveResult(WifiBle_WifiResult_t *result);
UINT WIFI_BLE_App_StreamWrite(WifiBle_Stream_t stream, const void *buffer,
                              ULONG length, ULONG wait_option);
UINT WIFI_BLE_App_StreamRead(WifiBle_Stream_t stream, void *buffer,
                             ULONG capacity, ULONG *actual_length,
                             ULONG wait_option);
uint32_t WIFI_BLE_App_IsTofImageSubscribed(void);
uint32_t WIFI_BLE_App_IsTofImageIdle(void);
UINT WIFI_BLE_App_PublishTofImage(uint32_t frame_id, uint8_t channel_id,
                                  const float *pixels, uint8_t width,
                                  uint8_t height);

#endif /* WIFI_BLE_APP_H */
