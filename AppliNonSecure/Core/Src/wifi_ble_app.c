#include "wifi_ble_app.h"
#include "app_cli_reply.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "app_features.h"
#include "bsp_conf.h"
#include "cloud_relay.h"
#include "tof_app.h"
#include "debug_uart.h"
#include "logging.h"
#include "main.h"
#include "vl53l9_interface.h"
#include "spi_iface.h"
#include "w61_at_api.h"
#include "w6x_api.h"

/* Avoid including app_azure_rtos.h here: its generated USB-PD include graph
 * collides with the Nucleo BSP types already pulled in through main.h. */
extern TX_BYTE_POOL *MX_RadioBytePool_Get(void);

#define WIFI_BLE_RX_BUFFER_SIZE (512U)

#define BLE_CLI_RX_SLOT_COUNT       (8U)
#define BLE_DEBUG_RX_SLOT_COUNT     (2U)
#define BLE_CLI_TX_SLOT_COUNT       (8U)
#define BLE_DEBUG_TX_SLOT_COUNT     (8U)
#define BLE_RX_SLOT_PAYLOAD_SIZE    (WIFI_BLE_RX_BUFFER_SIZE)
#define BLE_CLI_TX_SLOT_SIZE        (768U)
#define BLE_DEBUG_TX_SLOT_SIZE      (256U)
#define BLE_NOTIFY_TIMEOUT_MS       (100U)
#define BLE_NOTIFY_MAX_ATTEMPTS     (3U)
#define BLE_DEBUG_RX_POLICY_ENABLED (0U)
#define BLE_STREAM_CONTEXT_BUDGET   (16U * 1024U)
#define BLE_TOF_IMAGE_MAX_WIDTH     (54U)
#define BLE_TOF_IMAGE_MAX_HEIGHT    (42U)
#define BLE_TOF_IMAGE_MAX_PIXELS    (BLE_TOF_IMAGE_MAX_WIDTH * \
                                     BLE_TOF_IMAGE_MAX_HEIGHT)
#define BLE_TOF_IMAGE_MAX_BYTES     (BLE_TOF_IMAGE_MAX_PIXELS * sizeof(float))
#define BLE_TOF_IMAGE_CONTEXT_BUDGET (10U * 1024U)
#define BLE_CLI_TX_MAX_WAIT_TICKS   ((TX_TIMER_TICKS_PER_SECOND >= 20U) ? \
                                     (TX_TIMER_TICKS_PER_SECOND / 20U) : 1U)

#define BLE_CLI_SERVICE_INDEX   (0U)
#define BLE_DEBUG_SERVICE_INDEX (1U)
#define BLE_RX_CHAR_INDEX       (0U)
#define BLE_TX_CHAR_INDEX       (1U)
#define BLE_TOF_IMAGE_CHAR_INDEX (2U)
#define BLE_ADV_REQUEST_NONE    (2U)
#define BLE_HEALTH_PROBE_INTERVAL_MS (15000U)
#define BLE_CONNECTED_IDLE_MS       (5000U)
#define BLE_STALLED_TX_PROBE_TICKS   (5U * TX_TIMER_TICKS_PER_SECOND)
#define BLE_ADV_RETRY_BASE_MS       (1000U)
#define BLE_ADV_MAX_ATTEMPTS        (3U)
#define BLE_RECOVERY_COOLDOWN_MS    (10000U)
#define BLE_RECOVERY_MAX_ATTEMPTS   (3U)
#define WIFI_HEALTH_PROBE_WAIT_TICKS (30U * TX_TIMER_TICKS_PER_SECOND)

#define WIFI_CONTROL_SCAN_DONE_FLAG    (1UL << 1U)
#define WIFI_CONTROL_RADIO_READY_FLAG  (1UL << 2U)
#define WIFI_CONTROL_WORK_FLAG         (1UL << 3U)
#define RADIO_NOTIFICATION_WAKE_FLAG   (1UL << 4U)
#define WIFI_CONTROL_SCAN_WAIT_TICKS   (30U * TX_TIMER_TICKS_PER_SECOND)
#define WIFI_EVENT_CONNECTED_FLAG      (1UL << 0U)
#define WIFI_EVENT_GOT_IP_FLAG         (1UL << 1U)
#define WIFI_EVENT_DISCONNECTED_FLAG   (1UL << 2U)
#define WIFI_CONTROL_SLOT_COUNT         (4U)
/* Covers four owned request/result slots, pointer queues, fixed storage and
 * status snapshot. The existing event object is now common to Wi-Fi/BLE. */
#define WIFI_CONTROL_CONTEXT_BUDGET    (6U * 1024U)
#define WIFI_QUEUE_CREATED_REQUEST_FREE  (1UL << 0U)
#define WIFI_QUEUE_CREATED_REQUEST_READY (1UL << 1U)
#define WIFI_QUEUE_CREATED_RESULT_FREE   (1UL << 2U)
#define WIFI_QUEUE_CREATED_RESULT_READY  (1UL << 3U)

#define BLE_CLI_SERVICE_UUID    "7a1e0001b5a3f393e0a9e50e24dcca9e"
#define BLE_CLI_RX_UUID         "7a1e0002b5a3f393e0a9e50e24dcca9e"
#define BLE_CLI_TX_UUID         "7a1e0003b5a3f393e0a9e50e24dcca9e"
#define BLE_TOF_IMAGE_UUID      "7a1e0004b5a3f393e0a9e50e24dcca9e"
#define BLE_DEBUG_SERVICE_UUID  "7a1e0101b5a3f393e0a9e50e24dcca9e"
#define BLE_DEBUG_RX_UUID       "7a1e0102b5a3f393e0a9e50e24dcca9e"
#define BLE_DEBUG_TX_UUID       "7a1e0103b5a3f393e0a9e50e24dcca9e"

/* Complete 128-bit CLI service UUID. UUID bytes in AD structures are
 * little-endian; W6X GATT creation below uses the normal textual order.
 * Do not prepend a Flags AD structure: the ST67 firmware owns GAP flags. */
#define BLE_ADV_DATA \
  "11079ECADC240EE5A9E093F3A3B501001E7A"

#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
_Static_assert(W6X_BLE_MAX_CREATED_SERVICE_NBR >= 2U,
               "BLE maintenance requires two custom services");
_Static_assert(W6X_BLE_MAX_CHAR_NBR >= 3U,
               "The CLI service requires RX, TX and ToF image characteristics");
_Static_assert(WIFI_BLE_RX_BUFFER_SIZE > W6X_BLE_MAX_NOTIF_IND_DATA_LENGTH,
               "BLE callback buffer must hold one maximum ATT value");

typedef struct
{
  uint8_t service_index;
  uint8_t char_index;
  const char *uuid;
  uint8_t properties;
  uint8_t permissions;
  const char *description;
} WifiBle_GattCharacteristic_t;

typedef struct
{
  uint32_t generation;
  uint16_t length;
  uint8_t data[BLE_RX_SLOT_PAYLOAD_SIZE];
} WifiBle_RxSlot_t;

typedef struct
{
  uint32_t generation;
  uint16_t length;
  uint16_t offset;
  uint8_t retries;
  uint8_t data[BLE_CLI_TX_SLOT_SIZE];
} WifiBle_CliTxSlot_t;

typedef struct
{
  uint32_t generation;
  uint16_t length;
  uint16_t offset;
  uint8_t retries;
  uint8_t data[BLE_DEBUG_TX_SLOT_SIZE];
} WifiBle_DebugTxSlot_t;

typedef struct
{
  TX_QUEUE cli_rx_free;
  TX_QUEUE cli_rx_ready;
  TX_QUEUE debug_rx_free;
  TX_QUEUE debug_rx_ready;
  TX_QUEUE cli_tx_free;
  TX_QUEUE cli_tx_ready;
  TX_QUEUE debug_tx_free;
  TX_QUEUE debug_tx_ready;
  ULONG cli_rx_free_storage[BLE_CLI_RX_SLOT_COUNT];
  ULONG cli_rx_ready_storage[BLE_CLI_RX_SLOT_COUNT];
  ULONG debug_rx_free_storage[BLE_DEBUG_RX_SLOT_COUNT];
  ULONG debug_rx_ready_storage[BLE_DEBUG_RX_SLOT_COUNT];
  ULONG cli_tx_free_storage[BLE_CLI_TX_SLOT_COUNT];
  ULONG cli_tx_ready_storage[BLE_CLI_TX_SLOT_COUNT];
  ULONG debug_tx_free_storage[BLE_DEBUG_TX_SLOT_COUNT];
  ULONG debug_tx_ready_storage[BLE_DEBUG_TX_SLOT_COUNT];
  WifiBle_RxSlot_t cli_rx_slots[BLE_CLI_RX_SLOT_COUNT];
  WifiBle_RxSlot_t debug_rx_slots[BLE_DEBUG_RX_SLOT_COUNT];
  WifiBle_CliTxSlot_t cli_tx_slots[BLE_CLI_TX_SLOT_COUNT];
  WifiBle_DebugTxSlot_t debug_tx_slots[BLE_DEBUG_TX_SLOT_COUNT];
  void *active_tx[WIFI_BLE_STREAM_COUNT];
  WifiBle_StreamStatus_t stats[WIFI_BLE_STREAM_COUNT];
  uint32_t contention_start_tick[WIFI_BLE_STREAM_COUNT];
  AppCliReply_t reply;
  TX_THREAD *reply_owner;
} WifiBle_StreamContext_t;

typedef enum
{
  BLE_TOF_IMAGE_FREE = 0,
  BLE_TOF_IMAGE_FILLING,
  BLE_TOF_IMAGE_READY,
  BLE_TOF_IMAGE_ACTIVE,
  BLE_TOF_IMAGE_WAIT_CLOUD
} WifiBle_TofImageState_t;

typedef struct
{
  volatile WifiBle_TofImageState_t state;
  uint32_t generation;
  uint32_t frame_id;
  uint32_t payload_crc32;
  uint16_t payload_length;
  uint16_t offset;
  uint8_t width;
  uint8_t height;
  uint8_t channel_id;
  uint8_t retries;
  WifiBle_TofImageStatus_t stats;
  uint32_t contention_start_tick;
  uint8_t payload[BLE_TOF_IMAGE_MAX_BYTES] __attribute__((aligned(4)));
} WifiBle_TofImageContext_t;

_Static_assert(sizeof(void *) <= sizeof(ULONG),
               "ThreadX pointer queues require one ULONG per pointer");
_Static_assert(sizeof(WifiBle_StreamContext_t) <= BLE_STREAM_CONTEXT_BUDGET,
               "BLE stream queues exceeded their SRAM4 design budget");
_Static_assert(sizeof(WifiBle_TofImageContext_t) <=
               BLE_TOF_IMAGE_CONTEXT_BUDGET,
               "BLE ToF image context exceeded its SRAM4 design budget");

static const WifiBle_GattCharacteristic_t ble_characteristics[] =
{
  {
    BLE_CLI_SERVICE_INDEX, BLE_RX_CHAR_INDEX, BLE_CLI_RX_UUID,
    W6X_BLE_CHAR_PROP_WRITE_WITHOUT_RESP | W6X_BLE_CHAR_PROP_WRITE_WITH_RESP,
    W6X_BLE_CHAR_PERM_WRITE, "CLI RX"
  },
  {
    BLE_CLI_SERVICE_INDEX, BLE_TX_CHAR_INDEX, BLE_CLI_TX_UUID,
    W6X_BLE_CHAR_PROP_NOTIFY, W6X_BLE_CHAR_PERM_READ, "CLI TX"
  },
  {
    BLE_CLI_SERVICE_INDEX, BLE_TOF_IMAGE_CHAR_INDEX, BLE_TOF_IMAGE_UUID,
    W6X_BLE_CHAR_PROP_NOTIFY, W6X_BLE_CHAR_PERM_READ, "ToF image TX"
  },
  {
    BLE_DEBUG_SERVICE_INDEX, BLE_RX_CHAR_INDEX, BLE_DEBUG_RX_UUID,
    W6X_BLE_CHAR_PROP_WRITE_WITHOUT_RESP | W6X_BLE_CHAR_PROP_WRITE_WITH_RESP,
    W6X_BLE_CHAR_PERM_WRITE, "DEBUG RX (reserved)"
  },
  {
    BLE_DEBUG_SERVICE_INDEX, BLE_TX_CHAR_INDEX, BLE_DEBUG_TX_UUID,
    W6X_BLE_CHAR_PROP_NOTIFY, W6X_BLE_CHAR_PERM_READ, "DEBUG TX"
  }
};
#endif

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
typedef struct
{
  volatile WifiBle_WifiOperation_t active_operation;
  WifiBle_WifiStatus_t status;
  WifiBle_WifiScanResults_t scan_results;

  /* M3.2 fixed storage. Queue messages contain one slot pointer. */
  TX_QUEUE request_free;
  TX_QUEUE request_ready;
  TX_QUEUE result_free;
  TX_QUEUE result_ready;
  ULONG request_free_storage[WIFI_CONTROL_SLOT_COUNT];
  ULONG request_ready_storage[WIFI_CONTROL_SLOT_COUNT];
  ULONG result_free_storage[WIFI_CONTROL_SLOT_COUNT];
  ULONG result_ready_storage[WIFI_CONTROL_SLOT_COUNT];
  WifiBle_WifiRequest_t request_slots[WIFI_CONTROL_SLOT_COUNT];
  WifiBle_WifiResult_t result_slots[WIFI_CONTROL_SLOT_COUNT];
} WifiBle_WifiControlContext_t;

_Static_assert(WIFI_CONTROL_SLOT_COUNT == 4U,
               "Wi-Fi control requires exactly four slots per pool");
_Static_assert(sizeof(void *) <= sizeof(ULONG),
               "ThreadX pointer queues require one ULONG per pointer");
_Static_assert(WIFI_BLE_WIFI_SSID_SIZE == (W6X_WIFI_MAX_SSID_SIZE + 1U),
               "Public and vendor Wi-Fi SSID sizes must match");
_Static_assert(WIFI_BLE_WIFI_PASSWORD_SIZE ==
               (W6X_WIFI_MAX_PASSWORD_SIZE + 1U),
               "Public and vendor Wi-Fi password sizes must match");
_Static_assert(WIFI_BLE_WIFI_SCAN_MAX_APS <= UINT8_MAX,
               "Vendor scan count is uint8_t");
_Static_assert(sizeof(WifiBle_WifiControlContext_t) <=
               WIFI_CONTROL_CONTEXT_BUDGET,
               "Wi-Fi control context exceeded its SRAM4 design budget");

#endif

/* One owner for the NCP shadow, pending work, diagnostics and queue storage.
 * The large queue contexts themselves remain in the bounded SRAM4 radio pool. */
typedef struct
{
  struct
  {
    volatile WifiBle_State_t state;
    volatile uint32_t wifi_connected;
    volatile uint32_t wifi_has_ip;
    volatile uint32_t wifi_state_confirmed;
    volatile uint32_t ble_gatt_ready;
    volatile uint32_t ble_connected;
    volatile uint32_t ble_advertising;
    volatile uint32_t ble_advertising_desired;
    volatile WifiBle_AdvEvidence_t ble_advertising_evidence;
    volatile uint32_t ble_mode_confirmed;
    volatile uint32_t ble_link_confirmed;
    volatile uint32_t ble_connection_handle;
    volatile uint32_t ble_mtu;
    volatile uint32_t ble_cli_tx_subscribed;
    volatile uint32_t ble_debug_tx_subscribed;
    volatile uint32_t ble_tof_image_subscribed;
    volatile uint32_t ble_session_generation;
    volatile uint32_t ble_transport_ready;
    volatile uint32_t ble_init_stage;
    volatile int32_t ble_last_status;
    char ble_device_name[WIFI_BLE_DEVICE_NAME_SIZE];
    uint8_t ble_address[WIFI_BLE_ADDRESS_SIZE];
  } shadow;
  struct
  {
    volatile uint32_t ble_connect_pending;
    volatile uint32_t ble_restart_advertising_pending;
    volatile uint32_t ble_adv_request;
    volatile uint32_t ble_disconnect_request;
    volatile uint32_t ble_stream_flush_pending;
    volatile uint32_t ble_recovery_pending;
    volatile uint32_t ble_advertising_retry_count;
    volatile uint32_t ble_advertising_retry_due_tick;
    uint32_t ble_recovery_retry_count;
    uint32_t ble_recovery_due_tick;
    uint32_t ble_probe_due_tick;
    uint32_t ble_last_probe_tick;
    int32_t ble_last_probe_status;
    uint32_t ble_probe_link_next;
    uint32_t notify_source; /* 0 idle, stream+1, 3 ToF, 4 cancelled drain */
    uint32_t notify_generation;
    uint32_t notify_length;
    uint32_t ble_tx_stall_reported;
    volatile uint32_t ble_last_activity_tick;
    uint32_t ble_mode_mismatch_count;
    uint32_t ble_link_mismatch_count;
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    volatile uint32_t wifi_pending_event_bits;
    volatile uint32_t wifi_event_generation;
    volatile uint32_t wifi_connect_call_active;
    volatile uint32_t wifi_service_started_ms;
    uint32_t wifi_last_probe_tick;
    int32_t wifi_last_probe_status;
    AppRequestId_t wifi_last_request_id;
#endif
  } work;
  struct
  {
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
    uint8_t ble_receive_buffer[WIFI_BLE_RX_BUFFER_SIZE];
    WifiBle_StreamContext_t *ble_stream_context;
    WifiBle_TofImageContext_t *ble_tof_image_context;
    TX_BYTE_POOL *ble_radio_pool;
#endif
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    WifiBle_WifiControlContext_t *wifi_control_context;
#endif
  } queues;
  struct
  {
    volatile uint32_t wifi_ble_loop_count;
    volatile uint32_t wifi_ble_last_loop_tick;
    volatile uint32_t wifi_ble_max_loop_gap_ticks;
    volatile uint32_t wifi_ble_last_tx_tick;
    volatile uint32_t wifi_ble_max_tx_gap_ticks;
    volatile uint32_t ble_rx_write_events;
    volatile uint32_t ble_rx_discarded_bytes;
    volatile WifiBle_ManagerHealth_t faults;
  } counters;
} WifiBle_RadioManagerContext_t;

static WifiBle_RadioManagerContext_t radio_manager =
{
  .shadow = {
    .state = WIFI_BLE_STATE_DISABLED,
    .ble_advertising_desired = 1U,
    .ble_connection_handle = 0xFFU,
    .ble_mtu = 23U,
    .ble_init_stage = WIFI_BLE_INIT_STAGE_IDLE
  },
  .work = { .ble_adv_request = BLE_ADV_REQUEST_NONE }
};

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U) || (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static TX_EVENT_FLAGS_GROUP radio_control_events;
static volatile uint32_t radio_control_events_ready;
#endif

#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
typedef enum
{
  BLE_CONTROL_CONNECT = 1, BLE_CONTROL_DISCONNECT, BLE_CONTROL_ADV,
  BLE_CONTROL_MODE, BLE_CONTROL_LINK, BLE_CONTROL_RECOVER
} BleControlOperation_t;
typedef struct
{
  BleControlOperation_t operation;
  uint32_t generation, revision, handle, desired, submitted_at;
  uint32_t cancelled, stage;
  W6X_Status_t status, secondary_status;
  W6X_Ble_Mode_e mode;
  char name[WIFI_BLE_DEVICE_NAME_SIZE];
  uint8_t address[WIFI_BLE_ADDRESS_SIZE];
} BleControlJob_t;
/* Single by-value mailbox: FREE -> PENDING -> RUNNING -> COMPLETE -> FREE.
 * Only Radio publishes/consumes, only the existing control worker executes.
 * Interrupt exclusion publishes fully initialized data; no W6X call under it. */
static struct
{
  volatile uint32_t state;
  BleControlJob_t job;
  WifiBle_ControlStatus_t stats;
} ble_control;
static uint32_t ble_adv_revision;
static uint32_t ble_control_submit(BleControlOperation_t operation);
static void ble_control_execute(void);
static void ble_control_complete(void);
static uint32_t ble_control_current(const BleControlJob_t *job);
static W6X_Status_t ble_configure_gatt_job(BleControlJob_t *job, uint32_t startup);
static void ble_apply_gatt(const BleControlJob_t *job);
static void ble_apply_probe(const BleControlJob_t *job);
#endif

#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
/* The Cloud Relay must not use W6X_Net_* before W6X_Net_Init succeeds. */
static uint32_t cloud_net_ready;

static void network_event_callback(W6X_event_id_t event_id, void *event_args)
{
  /* W6X_Net_cb owns socket bookkeeping and wakes its receive semaphore. */
  (void)event_id;
  (void)event_args;
}
#endif

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
static void wifi_event_callback(W6X_event_id_t event_id, void *event_args);
static void wifi_scan_callback(int32_t status,
                               W6X_WiFi_Scan_Result_t *results);
static UINT wifi_control_initialize(void);
static void wifi_control_rollback(uint32_t queue_mask);
static UINT wifi_create_pointer_queue(TX_QUEUE *queue, CHAR *name,
                                      ULONG *storage);
static UINT wifi_request_slot_acquire(WifiBle_WifiRequest_t **slot);
static UINT wifi_request_slot_publish(WifiBle_WifiRequest_t *slot);
static UINT wifi_request_slot_receive(WifiBle_WifiRequest_t **slot);
static UINT wifi_request_slot_release(WifiBle_WifiRequest_t *slot);
static UINT wifi_result_slot_acquire(WifiBle_WifiResult_t **slot);
static UINT wifi_result_slot_acquire_wait(WifiBle_WifiResult_t **slot);
static UINT wifi_result_slot_publish(WifiBle_WifiResult_t *slot);
static UINT wifi_result_slot_receive(WifiBle_WifiResult_t **slot);
static UINT wifi_result_slot_release(WifiBle_WifiResult_t *slot);
static UINT wifi_control_queue_self_test(void);
static void wifi_execute_request(WifiBle_WifiRequest_t *request,
                                 WifiBle_WifiResult_t *result);
static UINT wifi_validate_owned_request(const WifiBle_WifiRequest_t *request,
                                        size_t *ssid_length,
                                        size_t *password_length);
static AppRequestId_t wifi_allocate_request_id(void);
static void wifi_process_pending_events(void);
static void wifi_refresh_status(void);
static W6X_Status_t wifi_enable_station_dhcp(void);
static W6X_Status_t wifi_get_station_ip(uint8_t ip_address[4],
                                        uint8_t gateway_address[4],
                                        uint8_t netmask_address[4]);
#endif
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static void ble_event_callback(W6X_event_id_t event_id, void *event_args);
static W6X_Status_t ble_configure_gatt_server(void);
static void ble_process_pending_events(void);
static void ble_notification_wake(void);
static void ble_reconcile_advertising(uint32_t now);
static void ble_probe_shadow(uint32_t now);
static void ble_recover_subsystem(uint32_t now);
static void ble_note_disconnected(void);
static uint32_t ble_tick_due(uint32_t now, uint32_t due);
static UINT ble_stream_initialize(void);
static void ble_stream_enqueue_rx(WifiBle_Stream_t stream,
                                  const uint8_t *data, uint32_t length);
static void ble_stream_process_tx(WifiBle_Stream_t stream);
static void __attribute__((optimize("Os"))) ble_tof_image_process_tx(void);
static void __attribute__((optimize("Os"))) ble_tof_image_drop_active(void);
static uint32_t __attribute__((optimize("Os")))
ble_crc32(const void *data, size_t length);
static void __attribute__((optimize("Os")))
ble_write_u16(uint8_t *destination, uint16_t value);
static void __attribute__((optimize("Os")))
ble_write_u32(uint8_t *destination, uint32_t value);
static void ble_stream_purge_stale(void);
static void ble_stream_drop_tx(WifiBle_Stream_t stream);
static uint32_t ble_att_payload_size(void);
static UINT ble_create_pointer_queue(TX_QUEUE *queue, CHAR *name,
                                     ULONG *storage, ULONG slot_count);
static void ble_purge_queue(TX_QUEUE *ready_queue, TX_QUEUE *free_queue,
                            WifiBle_Stream_t stream, uint32_t is_tx);
#endif
static void error_callback(W6X_Status_t status, const char *function_name);
static void log_output(const char *message);

void WIFI_BLE_App_ConfigureHardware(void)
{
  GPIO_InitTypeDef gpio = { 0 };

  /* Hold the NCP in its non-programming, disabled state.  ST's ST67 transport
     uses an unusual active-high SPI chip select, so LOW is the inactive level. */
  HAL_GPIO_WritePin(SPI_CS_GPIO_Port, SPI_CS_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(BOOT_GPIO_Port, BOOT_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(CHIP_EN_GPIO_Port, CHIP_EN_Pin, GPIO_PIN_RESET);

  HAL_NVIC_DisableIRQ(EXTI9_IRQn);
  __HAL_GPIO_EXTI_CLEAR_IT(GPIO_PIN_9);
  HAL_NVIC_ClearPendingIRQ(EXTI9_IRQn);

#if (APP_ST67W6X_ENABLED == 1U)
  /* EXTI9 can select only one GPIO port.  SPI_RDY is edge-sensitive in both
     directions, so PE9 owns the line while the radio transport is enabled. */
  HAL_GPIO_DeInit(TOF_INT_GPIO_Port, TOF_INT_Pin);
  gpio.Pin = TOF_INT_Pin;
  gpio.Mode = GPIO_MODE_INPUT;
  gpio.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(TOF_INT_GPIO_Port, &gpio);

  HAL_GPIO_DeInit(SPI_RDY_GPIO_Port, SPI_RDY_Pin);
  gpio.Pin = SPI_RDY_Pin;
  gpio.Mode = GPIO_MODE_IT_RISING_FALLING;
  gpio.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(SPI_RDY_GPIO_Port, &gpio);
#else
  /* With the NCP disabled, keep PE9 passive and give EXTI9 to the active-low
     ToF interrupt. */
  HAL_GPIO_DeInit(SPI_RDY_GPIO_Port, SPI_RDY_Pin);
  gpio.Pin = SPI_RDY_Pin;
  gpio.Mode = GPIO_MODE_INPUT;
  gpio.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(SPI_RDY_GPIO_Port, &gpio);

  HAL_GPIO_DeInit(TOF_INT_GPIO_Port, TOF_INT_Pin);
  gpio.Pin = TOF_INT_Pin;
  gpio.Mode = GPIO_MODE_IT_FALLING;
  gpio.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(TOF_INT_GPIO_Port, &gpio);
#endif

  HAL_NVIC_SetPriority(EXTI9_IRQn, 5U, 0U);
  HAL_NVIC_EnableIRQ(EXTI9_IRQn);
}

void WIFI_BLE_App_Run(void)
{
  W6X_Status_t status;
  uint32_t now;
  static W6X_App_Cb_t callbacks = {
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    .APP_wifi_cb = wifi_event_callback,
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
    .APP_net_cb = network_event_callback,
#else
    .APP_net_cb = NULL,
#endif
#else
    .APP_wifi_cb = NULL,
    .APP_net_cb = NULL,
#endif
    .APP_mqtt_cb = NULL,
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
    .APP_ble_cb = ble_event_callback,
#else
    .APP_ble_cb = NULL,
#endif
    .APP_error_cb = error_callback,
  };

  radio_manager.counters.faults.init_attempts++;
  radio_manager.shadow.state = WIFI_BLE_STATE_STARTING;
  radio_manager.counters.wifi_ble_loop_count = 0U;
  radio_manager.counters.wifi_ble_last_loop_tick = 0U;
  radio_manager.counters.wifi_ble_max_loop_gap_ticks = 0U;
  radio_manager.counters.wifi_ble_last_tx_tick = 0U;
  radio_manager.counters.wifi_ble_max_tx_gap_ticks = 0U;
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  cloud_net_ready = 0U;
#endif

  /* Give USB CDC time to enumerate so the complete bring-up log is visible. */
  tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND);
  (void)vLoggingInit(log_output);
  LogInfo("\r\nST67W6X: starting dedicated Wi-Fi/BLE thread...\r\n");

#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  if (ble_stream_initialize() != TX_SUCCESS)
  {
    LogError("ST67W6X BLE bounded-stream initialization failed.\r\n");
    status = W6X_STATUS_ERROR;
    goto error;
  }
#endif

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U) || (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  if (tx_event_flags_create(&radio_control_events, "ST67 control") != TX_SUCCESS)
  {
    status = W6X_STATUS_ERROR;
    goto error;
  }
  radio_control_events_ready = 1U;
#endif

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  if (wifi_control_initialize() != TX_SUCCESS)
  {
    LogError("ST67W6X Wi-Fi control initialization failed.\r\n");
    status = W6X_STATUS_ERROR;
    goto error;
  }
#endif

  status = W6X_RegisterAppCb(&callbacks);
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X callback registration failed: %" PRIi32 "\r\n", status);
    goto error;
  }

  LogInfo("ST67W6X pre-init pins: CHIP_EN=%lu BOOT=%lu CS=%lu SPI_RDY=%lu\r\n",
          (unsigned long)HAL_GPIO_ReadPin(CHIP_EN_GPIO_Port, CHIP_EN_Pin),
          (unsigned long)HAL_GPIO_ReadPin(BOOT_GPIO_Port, BOOT_Pin),
          (unsigned long)HAL_GPIO_ReadPin(SPI_CS_GPIO_Port, SPI_CS_Pin),
          (unsigned long)HAL_GPIO_ReadPin(SPI_RDY_GPIO_Port, SPI_RDY_Pin));

  status = W6X_Init();
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X driver initialization failed: %" PRIi32 "\r\n", status);
    goto error;
  }

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  status = W6X_WiFi_Init();
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X Wi-Fi initialization failed: %" PRIi32 "\r\n", status);
    goto error;
  }

  status = wifi_enable_station_dhcp();
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X station DHCP setup failed: %" PRIi32 "\r\n", status);
    goto error;
  }
  wifi_refresh_status();
#endif

#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  /* The Cloud worker owns SNTP/socket calls after READY. The vendor Net API
   * keeps its W61 pointer NULL until this initialization completes. */
  status = W6X_Net_Init();
  if (status == W6X_STATUS_OK)
  {
    cloud_net_ready = 1U;
  }
  else
  {
    LogError("ST67W6X Network initialization failed: %" PRIi32
             "; Cloud Relay disabled, Wi-Fi/BLE remain available.\r\n", status);
  }
#endif

#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  (void)memset(radio_manager.queues.ble_receive_buffer, 0, sizeof(radio_manager.queues.ble_receive_buffer));
  radio_manager.shadow.ble_init_stage = WIFI_BLE_INIT_STAGE_STACK;
  status = W6X_Ble_Init(W6X_BLE_MODE_SERVER, radio_manager.queues.ble_receive_buffer,
                        sizeof(radio_manager.queues.ble_receive_buffer) - 1U);
  radio_manager.shadow.ble_last_status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE initialization failed: %" PRIi32 "\r\n", status);
    goto error;
  }

  status = ble_configure_gatt_server();
  if (status != W6X_STATUS_OK)
  {
    goto error;
  }
#endif

#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  if ((cloud_net_ready != 0U) &&
      (CloudRelay_Initialize(MX_RadioBytePool_Get(), radio_manager.shadow.ble_device_name) != TX_SUCCESS))
  {
    LogError("ST67W6X Cloud Relay initialization failed; Wi-Fi/BLE remain available.\r\n");
    cloud_net_ready = 0U;
  }
#endif

  radio_manager.shadow.state = WIFI_BLE_STATE_READY;
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U) || (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  if (tx_event_flags_set(&radio_control_events,
                         WIFI_CONTROL_RADIO_READY_FLAG, TX_OR) != TX_SUCCESS)
  {
    LogError("ST67W6X Wi-Fi control ready signal failed.\r\n");
    status = W6X_STATUS_ERROR;
    goto error;
  }
#endif
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  LogInfo("ST67W6X: BLE maintenance GATT server is advertising.\r\n");
  LogInfo("ST67W6X: bounded CLI/DEBUG streams, signed BLE XMODEM and ToF image notifications ready.\r\n");
#endif
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  LogInfo("ST67W6X: Wi-Fi station service is ready; no credentials are configured.\r\n");
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  if (cloud_net_ready != 0U)
  {
    LogInfo("ST67W6X: HTTPS Cloud CLI relay is ready; use 'cloud pair <code>'.\r\n");
  }
#endif
#if ((APP_ST67W6X_BLE_GATT_ENABLED == 0U) && \
     (APP_ST67W6X_WIFI_SERVICES_ENABLED == 0U))
  LogInfo("ST67W6X: SPI/AT transport and module identity are ready.\r\n");
  LogInfo("ST67W6X: Wi-Fi and BLE services are disabled.\r\n");
#endif

  radio_manager.counters.wifi_ble_last_loop_tick = HAL_GetTick();
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  W6X_Ble_ServerNotifySetWakeCallback(ble_notification_wake);
#endif
  for (;;)
  {
    uint32_t loop_gap;

    now = HAL_GetTick();
    loop_gap = now - radio_manager.counters.wifi_ble_last_loop_tick;
    radio_manager.counters.wifi_ble_last_loop_tick = now;
    radio_manager.counters.wifi_ble_loop_count++;
    if (loop_gap > radio_manager.counters.wifi_ble_max_loop_gap_ticks)
    {
      radio_manager.counters.wifi_ble_max_loop_gap_ticks = loop_gap;
    }
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    wifi_process_pending_events();
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
    /* Publish only scalar readiness; DNS/socket/protocol work belongs to the
     * Cloud worker. Shared ToF payload lifetime uses an explicit Cloud lease. */
    CloudRelay_SetNetworkState(cloud_net_ready,
                               radio_manager.shadow.wifi_has_ip);
#endif
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
    ble_process_pending_events();
    now = HAL_GetTick();
    if (radio_manager.counters.wifi_ble_last_tx_tick != 0U)
    {
      uint32_t ble_tx_gap = now - radio_manager.counters.wifi_ble_last_tx_tick;
      if (ble_tx_gap > radio_manager.counters.wifi_ble_max_tx_gap_ticks)
      {
        radio_manager.counters.wifi_ble_max_tx_gap_ticks = ble_tx_gap;
      }
    }
    radio_manager.counters.wifi_ble_last_tx_tick = now;
#endif
#if ((APP_ST67W6X_BLE_GATT_ENABLED == 1U) || \
     (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U))
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
    ULONG notify_flags;
    (void)tx_event_flags_get(&radio_control_events, RADIO_NOTIFICATION_WAKE_FLAG,
                             TX_OR_CLEAR, &notify_flags,
                             (TX_TIMER_TICKS_PER_SECOND >= 50U) ?
                             (TX_TIMER_TICKS_PER_SECOND / 50U) : 1U);
#else
    tx_thread_sleep((TX_TIMER_TICKS_PER_SECOND >= 50U) ?
                    (TX_TIMER_TICKS_PER_SECOND / 50U) : 1U);
#endif
#else
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND);
#endif
  }

error:
  radio_manager.counters.faults.init_failures++;
  radio_manager.shadow.state = WIFI_BLE_STATE_ERROR;
  LogError("ST67W6X thread stopped in ERROR state; ToF continues running.\r\n");
  for (;;)
  {
    tx_thread_sleep(5U * TX_TIMER_TICKS_PER_SECOND);
  }
}

WifiBle_State_t WIFI_BLE_App_GetState(void)
{
  return radio_manager.shadow.state;
}

void WIFI_BLE_App_GetServiceStatus(WifiBle_ServiceStatus_t *status)
{
  if (!status) return;
  *status = (WifiBle_ServiceStatus_t){ .state = WIFI_BLE_SERVICE_AVAILABLE,
      .reason = "READY" };
#if (APP_ST67W6X_ENABLED == 1U)
  W61_Object_t *driver = W61_ObjGet();
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  TickType_t now = xTaskGetTickCount();
  if (radio_manager.shadow.state != WIFI_BLE_STATE_READY || !driver) {
    status->state = radio_manager.shadow.state == WIFI_BLE_STATE_ERROR ?
        WIFI_BLE_SERVICE_FAULT : WIFI_BLE_SERVICE_WAITING;
    status->reason = radio_manager.shadow.state == WIFI_BLE_STATE_ERROR ? "INIT_FAILED" : "STARTING";
  } else if (driver->Modem.handler_data.tx_desynchronized) {
    status->state = WIFI_BLE_SERVICE_FAULT; status->reason = "AT_FENCED";
  } else if (driver->Modem.handler_data.dns_drain_active) {
    TickType_t deadline = driver->Modem.handler_data.dns_drain_until;
    status->elapsed_ms = (now - (deadline - pdMS_TO_TICKS(20000U))) * portTICK_PERIOD_MS;
    status->state = (int32_t)(now - deadline) >= 0 ? WIFI_BLE_SERVICE_FAULT : WIFI_BLE_SERVICE_WAITING;
    status->reason = "DNS_REPLY";
    status->remaining_ms = status->state == WIFI_BLE_SERVICE_WAITING ?
        (deadline - now) * portTICK_PERIOD_MS : 0U;
  } else if (driver->Modem.notify_phase && driver->Modem.notify_late) {
    status->state = WIFI_BLE_SERVICE_WAITING; status->reason = "BLE_TERMINAL";
    status->elapsed_ms = (now - driver->Modem.notify_started) * portTICK_PERIOD_MS;
    uint32_t limit = driver->Modem.notify_budget * portTICK_PERIOD_MS + 1000U;
    status->remaining_ms = status->elapsed_ms < limit ? limit - status->elapsed_ms : 0U;
  }
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  else if (radio_manager.queues.wifi_control_context &&
      radio_manager.queues.wifi_control_context->status.operation_active) {
    status->state = WIFI_BLE_SERVICE_WAITING;
    WifiBle_WifiOperation_t op = radio_manager.queues.wifi_control_context->active_operation;
    status->reason = op == WIFI_BLE_WIFI_OPERATION_CONNECT ? "WIFI_CONNECT" :
        op == WIFI_BLE_WIFI_OPERATION_DISCONNECT ? "WIFI_DISCONNECT" : "WIFI_SCAN";
    status->elapsed_ms = HAL_GetTick() - radio_manager.work.wifi_service_started_ms;
  }
#endif
  (void)tx_interrupt_control(posture);
#else
  status->state = WIFI_BLE_SERVICE_FAULT; status->reason = "DISABLED";
#endif
}

void WIFI_BLE_App_GetRuntimeStatus(WifiBle_RuntimeStatus_t *status)
{
  UINT posture;

  if (status == NULL)
  {
    return;
  }

  status->state = radio_manager.shadow.state;
  status->wifi_connected = radio_manager.shadow.wifi_connected;
  status->wifi_has_ip = radio_manager.shadow.wifi_has_ip;
  status->wifi_state_confirmed = radio_manager.shadow.wifi_state_confirmed;
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  status->wifi_last_probe_tick = radio_manager.work.wifi_last_probe_tick;
  status->wifi_last_probe_status = radio_manager.work.wifi_last_probe_status;
#else
  status->wifi_last_probe_tick = 0U;
  status->wifi_last_probe_status = 0;
#endif
  status->loop_count = radio_manager.counters.wifi_ble_loop_count;
  status->last_loop_tick = radio_manager.counters.wifi_ble_last_loop_tick;
  status->max_loop_gap_ticks = radio_manager.counters.wifi_ble_max_loop_gap_ticks;
  status->last_ble_tx_tick = radio_manager.counters.wifi_ble_last_tx_tick;
  status->max_ble_tx_gap_ticks = radio_manager.counters.wifi_ble_max_tx_gap_ticks;
  status->ble_gatt_ready = radio_manager.shadow.ble_gatt_ready;
  status->ble_connected = radio_manager.shadow.ble_connected;
  status->ble_advertising = radio_manager.shadow.ble_advertising;
  status->ble_advertising_desired = radio_manager.shadow.ble_advertising_desired;
  status->ble_advertising_evidence = radio_manager.shadow.ble_advertising_evidence;
  status->ble_advertising_retry_count = radio_manager.work.ble_advertising_retry_count;
  status->ble_recovery_pending = radio_manager.work.ble_recovery_pending;
  status->ble_mode_confirmed = radio_manager.shadow.ble_mode_confirmed;
  status->ble_link_confirmed = radio_manager.shadow.ble_link_confirmed;
  status->ble_last_probe_tick = radio_manager.work.ble_last_probe_tick;
  status->ble_last_probe_status = radio_manager.work.ble_last_probe_status;
  status->ble_connection_handle = radio_manager.shadow.ble_connection_handle;
  status->ble_mtu = radio_manager.shadow.ble_mtu;
  status->ble_cli_tx_subscribed = radio_manager.shadow.ble_cli_tx_subscribed;
  status->ble_debug_tx_subscribed = radio_manager.shadow.ble_debug_tx_subscribed;
  status->ble_tof_image_subscribed = radio_manager.shadow.ble_tof_image_subscribed;
  status->ble_rx_write_events = radio_manager.counters.ble_rx_write_events;
  status->ble_rx_discarded_bytes = radio_manager.counters.ble_rx_discarded_bytes;
  status->ble_session_generation = radio_manager.shadow.ble_session_generation;
  status->ble_att_payload_limit =
      (radio_manager.shadow.ble_mtu > 3U) ? ((radio_manager.shadow.ble_mtu - 3U) < W6X_BLE_MAX_NOTIF_IND_DATA_LENGTH ?
                       (radio_manager.shadow.ble_mtu - 3U) : W6X_BLE_MAX_NOTIF_IND_DATA_LENGTH) : 20U;
  status->ble_transport_ready = radio_manager.shadow.ble_transport_ready;
  status->ble_radio_pool_available = 0U;
  status->ble_radio_pool_fragments = 0U;
  status->ble_init_stage = radio_manager.shadow.ble_init_stage;
  status->ble_last_status = radio_manager.shadow.ble_last_status;
  status->manager_health = radio_manager.counters.faults;
  memset(&status->ble_control, 0, sizeof(status->ble_control));
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  {
    UINT posture = tx_interrupt_control(TX_INT_DISABLE);
    status->ble_control = ble_control.stats;
    status->ble_control.state = ble_control.state;
    status->ble_control.operation = ble_control.job.operation;
    (void)tx_interrupt_control(posture);
  }
#endif
  (void)memset(status->ble_stream, 0, sizeof(status->ble_stream));
  (void)memset(&status->ble_tof_image, 0, sizeof(status->ble_tof_image));
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  posture = tx_interrupt_control(TX_INT_DISABLE);
  if (radio_manager.queues.ble_stream_context != NULL)
  {
    status->ble_stream[WIFI_BLE_STREAM_CLI] =
        radio_manager.queues.ble_stream_context->stats[WIFI_BLE_STREAM_CLI];
    status->ble_stream[WIFI_BLE_STREAM_DEBUG] =
        radio_manager.queues.ble_stream_context->stats[WIFI_BLE_STREAM_DEBUG];
  }
  if (radio_manager.queues.ble_tof_image_context != NULL)
  {
    status->ble_tof_image = radio_manager.queues.ble_tof_image_context->stats;
  }
  (void)tx_interrupt_control(posture);
  if (radio_manager.queues.ble_radio_pool != NULL)
  {
    ULONG available = 0U;
    ULONG fragments = 0U;
    if (tx_byte_pool_info_get(radio_manager.queues.ble_radio_pool, TX_NULL, &available, &fragments,
                              TX_NULL, TX_NULL, TX_NULL) == TX_SUCCESS)
    {
      status->ble_radio_pool_available = available;
      status->ble_radio_pool_fragments = fragments;
    }
  }
#else
  (void)posture;
#endif
  (void)memcpy(status->ble_device_name, radio_manager.shadow.ble_device_name,
               sizeof(status->ble_device_name));
  (void)memcpy(status->ble_address, radio_manager.shadow.ble_address,
               sizeof(status->ble_address));
}

void WIFI_BLE_App_GetHardwareStatus(WifiBle_HardwareStatus_t *status)
{
  if (status == NULL)
  {
    return;
  }

  status->radio_enabled = APP_ST67W6X_ENABLED;
  status->wifi_services_enabled = APP_ST67W6X_WIFI_SERVICES_ENABLED;
  status->ble_gatt_enabled = APP_ST67W6X_BLE_GATT_ENABLED;
  status->spi_initialized =
      (NCP_SPI_HANDLE.State != HAL_SPI_STATE_RESET) ? 1U : 0U;
  status->spi_rx_dma_ready = (NCP_SPI_HANDLE.hdmarx != NULL) ? 1U : 0U;
  status->spi_tx_dma_ready = (NCP_SPI_HANDLE.hdmatx != NULL) ? 1U : 0U;
  status->chip_enable_level =
      (uint32_t)HAL_GPIO_ReadPin(CHIP_EN_GPIO_Port, CHIP_EN_Pin);
  status->boot_level =
      (uint32_t)HAL_GPIO_ReadPin(BOOT_GPIO_Port, BOOT_Pin);
  status->chip_select_level =
      (uint32_t)HAL_GPIO_ReadPin(SPI_CS_GPIO_Port, SPI_CS_Pin);
  status->spi_ready_level =
      (uint32_t)HAL_GPIO_ReadPin(SPI_RDY_GPIO_Port, SPI_RDY_Pin);
#if (APP_ST67W6X_ENABLED == 1U)
  status->exti9_owner = WIFI_BLE_EXTI9_OWNER_RADIO;
#else
  status->exti9_owner = WIFI_BLE_EXTI9_OWNER_TOF;
#endif
}

UINT WIFI_BLE_App_RequestAdvertising(uint32_t advertising)
{
  if (radio_manager.shadow.ble_gatt_ready == 0U)
  {
    return TX_NOT_AVAILABLE;
  }
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  ble_adv_revision++;
#endif
  radio_manager.shadow.ble_advertising_desired = (advertising != 0U) ? 1U : 0U;
  radio_manager.shadow.ble_advertising_evidence = WIFI_BLE_ADV_UNKNOWN;
  radio_manager.work.ble_advertising_retry_count = 0U;
  radio_manager.work.ble_advertising_retry_due_tick = 0U;
  radio_manager.work.ble_adv_request = (advertising != 0U) ? 1U : 0U;
  (void)tx_interrupt_control(posture);
  return TX_SUCCESS;
}

UINT WIFI_BLE_App_RequestDisconnect(void)
{
  if (radio_manager.shadow.ble_connected == 0U)
  {
    return TX_NOT_AVAILABLE;
  }
  radio_manager.work.ble_disconnect_request = 1U;
  return TX_SUCCESS;
}

void WIFI_BLE_App_GetWifiStatus(WifiBle_WifiStatus_t *status)
{
  if (status == NULL)
  {
    return;
  }

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  if (radio_manager.queues.wifi_control_context != NULL)
  {
    UINT posture = tx_interrupt_control(TX_INT_DISABLE);
    *status = radio_manager.queues.wifi_control_context->status;
    status->connected = radio_manager.shadow.wifi_connected;
    status->has_ip = radio_manager.shadow.wifi_has_ip;
    (void)tx_interrupt_control(posture);
    return;
  }
#endif

  (void)memset(status, 0, sizeof(*status));
  status->last_status = (int32_t)W6X_STATUS_ERROR;
}

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
static UINT wifi_validate_owned_request(const WifiBle_WifiRequest_t *request,
                                        size_t *ssid_length,
                                        size_t *password_length)
{
  const char *ssid_end;
  const char *password_end;

  if ((request == NULL) || (ssid_length == NULL) ||
      (password_length == NULL))
  {
    return TX_PTR_ERROR;
  }
  if (request->route.session_generation == 0U)
  {
    return TX_OPTION_ERROR;
  }
  switch (request->route.transport)
  {
    case APP_TRANSPORT_USB:
    case APP_TRANSPORT_BLE:
    case APP_TRANSPORT_CLOUD:
    case APP_TRANSPORT_SYSTEM:
      break;

    default:
      return TX_OPTION_ERROR;
  }

  ssid_end = (const char *)memchr(request->ssid, '\0',
                                  sizeof(request->ssid));
  password_end = (const char *)memchr(request->password, '\0',
                                      sizeof(request->password));
  if ((ssid_end == NULL) || (password_end == NULL))
  {
    return TX_SIZE_ERROR;
  }
  *ssid_length = (size_t)(ssid_end - request->ssid);
  *password_length = (size_t)(password_end - request->password);

  switch (request->operation)
  {
    case WIFI_BLE_WIFI_OPERATION_SCAN:
      return TX_SUCCESS;

    case WIFI_BLE_WIFI_OPERATION_CONNECT:
      return (*ssid_length != 0U) ? TX_SUCCESS : TX_SIZE_ERROR;

    case WIFI_BLE_WIFI_OPERATION_DISCONNECT:
      return (request->forget <= 1U) ? TX_SUCCESS : TX_OPTION_ERROR;

    case WIFI_BLE_WIFI_OPERATION_NONE:
    default:
      return TX_OPTION_ERROR;
  }
}

static AppRequestId_t wifi_allocate_request_id(void)
{
  AppRequestId_t request_id;
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);

  request_id = radio_manager.work.wifi_last_request_id + 1U;
  if (request_id == 0U)
  {
    request_id = 1U;
  }
  radio_manager.work.wifi_last_request_id = request_id;
  (void)tx_interrupt_control(posture);
  return request_id;
}
#endif

UINT WIFI_BLE_App_WifiSubmit(const WifiBle_WifiRequest_t *request,
                             AppRequestId_t *request_id)
{
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  WifiBle_WifiRequest_t *slot = NULL;
  AppRequestId_t assigned_id;
  size_t ssid_length = 0U;
  size_t password_length = 0U;
  UINT result;

  if ((request == NULL) || (request_id == NULL))
  {
    return TX_PTR_ERROR;
  }
  result = wifi_validate_owned_request(request, &ssid_length,
                                       &password_length);
  if (result != TX_SUCCESS)
  {
    return result;
  }
  result = wifi_request_slot_acquire(&slot);
  if (result != TX_SUCCESS)
  {
    return result;
  }

  assigned_id = wifi_allocate_request_id();
  (void)memset(slot, 0, sizeof(*slot));
  slot->operation = request->operation;
  slot->request_id = assigned_id;
  slot->route = request->route;
  if (request->operation == WIFI_BLE_WIFI_OPERATION_CONNECT)
  {
    (void)memcpy(slot->ssid, request->ssid, ssid_length + 1U);
    (void)memcpy(slot->password, request->password, password_length + 1U);
  }
  else if (request->operation == WIFI_BLE_WIFI_OPERATION_DISCONNECT)
  {
    slot->forget = request->forget;
  }

  result = wifi_request_slot_publish(slot);
  if (result != TX_SUCCESS)
  {
    UINT release_result = wifi_request_slot_release(slot);
    return (release_result == TX_SUCCESS) ? result : release_result;
  }
  *request_id = assigned_id;
  return TX_SUCCESS;
#else
  (void)request;
  (void)request_id;
  return TX_NOT_AVAILABLE;
#endif
}

UINT WIFI_BLE_App_WifiReceiveResult(WifiBle_WifiResult_t *result)
{
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  WifiBle_WifiResult_t *slot = NULL;
  UINT status;

  if (result == NULL)
  {
    return TX_PTR_ERROR;
  }
  status = wifi_result_slot_receive(&slot);
  if (status != TX_SUCCESS)
  {
    return status;
  }
  *result = *slot;
  return wifi_result_slot_release(slot);
#else
  (void)result;
  return TX_NOT_AVAILABLE;
#endif
}

UINT WIFI_BLE_App_BeginReply(void)
{
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  WifiBle_StreamContext_t *ctx = radio_manager.queues.ble_stream_context;
  ULONG free_count = 0U;
  void *slot;
  void *owned[BLE_CLI_TX_SLOT_COUNT];
  if (!ctx || !radio_manager.shadow.ble_connected ||
      !radio_manager.shadow.ble_cli_tx_subscribed) return TX_NOT_AVAILABLE;
  if (ctx->reply.active) return TX_NOT_AVAILABLE;
  (void)tx_queue_info_get(&ctx->cli_tx_free, TX_NULL, &free_count, TX_NULL,
                           TX_NULL, TX_NULL, TX_NULL);
  if (free_count != BLE_CLI_TX_SLOT_COUNT) return TX_QUEUE_FULL;
  /* The CLI is the sole ordinary CLI producer. Reserve before reading input;
   * Radio only returns free slots. No reply can exhaust this owned batch. */
  for (uint32_t i = 0U; i < BLE_CLI_TX_SLOT_COUNT; ++i) {
    UINT result = tx_queue_receive(&ctx->cli_tx_free, &slot, TX_NO_WAIT);
    if (result != TX_SUCCESS) {
      for (uint32_t j = 0U; j < i; ++j)
        (void)tx_queue_send(&ctx->cli_tx_free, &owned[j], TX_NO_WAIT);
      return result;
    }
    owned[i] = slot;
  }
  ctx->reply = (AppCliReply_t){ .active = 1U,
      .generation = radio_manager.shadow.ble_session_generation };
  ctx->reply_owner = tx_thread_identify();
  return TX_SUCCESS;
#else
  return TX_NOT_AVAILABLE;
#endif
}

UINT WIFI_BLE_App_EndReply(uint32_t completed)
{
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  WifiBle_StreamContext_t *ctx = radio_manager.queues.ble_stream_context;
  if (!ctx || !ctx->reply.active || ctx->reply_owner != tx_thread_identify())
    return TX_NOT_AVAILABLE;
  if (completed) {
    const char *trailer = ctx->reply.overflow ?
      "\r\n[CLI-RESULT] state=failed reason=OUTPUT_LIMIT\r\nn6> " :
      completed == 3U ? "\r\n[CLI-RESULT] state=failed reason=WRITE_ERROR\r\n" :
      completed == 2U ? "\r\n[CLI-RESULT] state=rejected reason=SERVICE_UNAVAILABLE\r\n" :
      "\r\n[CLI-RESULT] state=complete\r\n";
    (void)AppCliReply_Append(&ctx->reply, ctx->cli_tx_slots[0].data,
        sizeof(ctx->cli_tx_slots[0]), BLE_CLI_TX_SLOT_SIZE,
        BLE_CLI_TX_SLOT_COUNT, trailer, strlen(trailer), 1U);
  }
  uint32_t current = radio_manager.shadow.ble_connected &&
      radio_manager.shadow.ble_cli_tx_subscribed &&
      ctx->reply.generation == radio_manager.shadow.ble_session_generation;
  uint32_t count = (ctx->reply.bytes + BLE_CLI_TX_SLOT_SIZE - 1U) / BLE_CLI_TX_SLOT_SIZE;
  UINT publication = TX_SUCCESS;
  for (uint32_t i = 0U; i < BLE_CLI_TX_SLOT_COUNT; ++i) {
    WifiBle_CliTxSlot_t *slot = &ctx->cli_tx_slots[i];
    if (current && i < count) {
      slot->generation = ctx->reply.generation;
      slot->length = (uint16_t)((ctx->reply.bytes - i * BLE_CLI_TX_SLOT_SIZE) > BLE_CLI_TX_SLOT_SIZE ?
          BLE_CLI_TX_SLOT_SIZE : ctx->reply.bytes - i * BLE_CLI_TX_SLOT_SIZE);
      slot->offset = 0U; slot->retries = 0U;
      UINT posture = tx_interrupt_control(TX_INT_DISABLE);
      UINT result = tx_queue_send(&ctx->cli_tx_ready, &slot, TX_NO_WAIT);
      if (result == TX_SUCCESS) {
        ctx->stats[WIFI_BLE_STREAM_CLI].tx_queued++;
        ctx->stats[WIFI_BLE_STREAM_CLI].tx_messages++;
        ctx->stats[WIFI_BLE_STREAM_CLI].tx_bytes += slot->length;
        if (ctx->stats[0].tx_queued > ctx->stats[0].tx_high_water)
          ctx->stats[0].tx_high_water = ctx->stats[0].tx_queued;
      }
      (void)tx_interrupt_control(posture);
      if (result != TX_SUCCESS) {
        publication = result;
        (void)tx_queue_send(&ctx->cli_tx_free, &slot, TX_NO_WAIT);
      }
    } else (void)tx_queue_send(&ctx->cli_tx_free, &slot, TX_NO_WAIT);
  }
  ctx->reply.active = 0U;
  ctx->reply_owner = NULL;
  return current ? publication : TX_NOT_AVAILABLE;
#else
  (void)completed;
  return TX_NOT_AVAILABLE;
#endif
}

UINT WIFI_BLE_App_StreamWrite(WifiBle_Stream_t stream, const void *buffer,
                              ULONG length, ULONG wait_option)
{
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  TX_QUEUE *free_queue;
  TX_QUEUE *ready_queue;
  void *slot = NULL;
  uint32_t subscribed;
  ULONG capacity;
  UINT posture;
  UINT result;

  if ((stream >= WIFI_BLE_STREAM_COUNT) || (buffer == NULL) || (length == 0U))
  {
    return TX_PTR_ERROR;
  }
  if ((radio_manager.shadow.ble_transport_ready == 0U) || (radio_manager.shadow.ble_connected == 0U) ||
      (radio_manager.queues.ble_stream_context == NULL))
  {
    return TX_NOT_AVAILABLE;
  }

  subscribed = (stream == WIFI_BLE_STREAM_CLI) ?
               radio_manager.shadow.ble_cli_tx_subscribed : radio_manager.shadow.ble_debug_tx_subscribed;
  if (subscribed == 0U)
  {
    return TX_NOT_AVAILABLE;
  }

  if ((stream == WIFI_BLE_STREAM_CLI) &&
      radio_manager.queues.ble_stream_context->reply.active) {
    WifiBle_StreamContext_t *ctx = radio_manager.queues.ble_stream_context;
    if (ctx->reply_owner != tx_thread_identify()) return TX_NOT_AVAILABLE;
    return AppCliReply_Append(&ctx->reply, ctx->cli_tx_slots[0].data,
        sizeof(ctx->cli_tx_slots[0]), BLE_CLI_TX_SLOT_SIZE,
        BLE_CLI_TX_SLOT_COUNT, buffer, length, 0U) ? TX_SIZE_ERROR : TX_SUCCESS;
  }

  if (stream == WIFI_BLE_STREAM_CLI)
  {
    free_queue = &radio_manager.queues.ble_stream_context->cli_tx_free;
    ready_queue = &radio_manager.queues.ble_stream_context->cli_tx_ready;
    capacity = BLE_CLI_TX_SLOT_SIZE;
    if ((wait_option == TX_WAIT_FOREVER) ||
        (wait_option > BLE_CLI_TX_MAX_WAIT_TICKS))
    {
      wait_option = BLE_CLI_TX_MAX_WAIT_TICKS;
    }
  }
  else
  {
    free_queue = &radio_manager.queues.ble_stream_context->debug_tx_free;
    ready_queue = &radio_manager.queues.ble_stream_context->debug_tx_ready;
    capacity = BLE_DEBUG_TX_SLOT_SIZE;
    /* Debug mirroring is best-effort and must never stall its producer. */
    wait_option = TX_NO_WAIT;
  }

  if (length > capacity)
  {
    posture = tx_interrupt_control(TX_INT_DISABLE);
    radio_manager.queues.ble_stream_context->stats[stream].tx_dropped_messages++;
    radio_manager.queues.ble_stream_context->stats[stream].tx_dropped_bytes += length;
    (void)tx_interrupt_control(posture);
    return TX_SIZE_ERROR;
  }

  result = tx_queue_receive(free_queue, &slot, wait_option);
  if (result != TX_SUCCESS)
  {
    posture = tx_interrupt_control(TX_INT_DISABLE);
    radio_manager.queues.ble_stream_context->stats[stream].tx_dropped_messages++;
    radio_manager.queues.ble_stream_context->stats[stream].tx_dropped_bytes += length;
    (void)tx_interrupt_control(posture);
    return result;
  }

  if ((radio_manager.shadow.ble_connected == 0U) ||
      (((stream == WIFI_BLE_STREAM_CLI) ? radio_manager.shadow.ble_cli_tx_subscribed :
                                           radio_manager.shadow.ble_debug_tx_subscribed) == 0U))
  {
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    return TX_NOT_AVAILABLE;
  }

  if (stream == WIFI_BLE_STREAM_CLI)
  {
    WifiBle_CliTxSlot_t *tx_slot = (WifiBle_CliTxSlot_t *)slot;
    tx_slot->generation = radio_manager.shadow.ble_session_generation;
    tx_slot->length = (uint16_t)length;
    tx_slot->offset = 0U;
    tx_slot->retries = 0U;
    (void)memcpy(tx_slot->data, buffer, length);
  }
  else
  {
    WifiBle_DebugTxSlot_t *tx_slot = (WifiBle_DebugTxSlot_t *)slot;
    tx_slot->generation = radio_manager.shadow.ble_session_generation;
    tx_slot->length = (uint16_t)length;
    tx_slot->offset = 0U;
    tx_slot->retries = 0U;
    (void)memcpy(tx_slot->data, buffer, length);
  }

  result = tx_queue_send(ready_queue, &slot, TX_NO_WAIT);
  if (result != TX_SUCCESS)
  {
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    posture = tx_interrupt_control(TX_INT_DISABLE);
    radio_manager.queues.ble_stream_context->stats[stream].tx_dropped_messages++;
    radio_manager.queues.ble_stream_context->stats[stream].tx_dropped_bytes += length;
    (void)tx_interrupt_control(posture);
    return result;
  }

  posture = tx_interrupt_control(TX_INT_DISABLE);
  radio_manager.queues.ble_stream_context->stats[stream].tx_messages++;
  radio_manager.queues.ble_stream_context->stats[stream].tx_bytes += length;
  radio_manager.queues.ble_stream_context->stats[stream].tx_queued++;
  if (radio_manager.queues.ble_stream_context->stats[stream].tx_queued >
      radio_manager.queues.ble_stream_context->stats[stream].tx_high_water)
  {
    radio_manager.queues.ble_stream_context->stats[stream].tx_high_water =
        radio_manager.queues.ble_stream_context->stats[stream].tx_queued;
  }
  (void)tx_interrupt_control(posture);
  return TX_SUCCESS;
#else
  (void)stream;
  (void)buffer;
  (void)length;
  (void)wait_option;
  return TX_NOT_AVAILABLE;
#endif
}

static UINT ble_stream_read(WifiBle_Stream_t stream, void *buffer,
                             ULONG capacity, ULONG *actual_length,
                             ULONG wait_option, uint32_t line_mode)
{
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  TX_QUEUE *free_queue;
  TX_QUEUE *ready_queue;
  WifiBle_RxSlot_t *slot = NULL;
  UINT result;
  UINT posture;

  if (actual_length != NULL)
  {
    *actual_length = 0U;
  }
  if ((stream >= WIFI_BLE_STREAM_COUNT) || (buffer == NULL) ||
      (actual_length == NULL))
  {
    return TX_PTR_ERROR;
  }
  if ((radio_manager.shadow.ble_transport_ready == 0U) || (radio_manager.queues.ble_stream_context == NULL))
  {
    return TX_NOT_AVAILABLE;
  }

  free_queue = (stream == WIFI_BLE_STREAM_CLI) ?
               &radio_manager.queues.ble_stream_context->cli_rx_free :
               &radio_manager.queues.ble_stream_context->debug_rx_free;
  ready_queue = (stream == WIFI_BLE_STREAM_CLI) ?
                &radio_manager.queues.ble_stream_context->cli_rx_ready :
                &radio_manager.queues.ble_stream_context->debug_rx_ready;

  do
  {
    result = tx_queue_receive(ready_queue, &slot, wait_option);
    if (result != TX_SUCCESS)
    {
      return result;
    }
    posture = tx_interrupt_control(TX_INT_DISABLE);
    if (radio_manager.queues.ble_stream_context->stats[stream].rx_queued != 0U)
    {
      radio_manager.queues.ble_stream_context->stats[stream].rx_queued--;
    }
    (void)tx_interrupt_control(posture);

    if (slot->generation != radio_manager.shadow.ble_session_generation)
    {
      (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
      posture = tx_interrupt_control(TX_INT_DISABLE);
      radio_manager.queues.ble_stream_context->stats[stream].stale_drops++;
      (void)tx_interrupt_control(posture);
      slot = NULL;
      wait_option = TX_NO_WAIT;
    }
  } while (slot == NULL);

  *actual_length = slot->length;
  if (!line_mode && capacity < slot->length)
  {
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    return TX_SIZE_ERROR;
  }

  if (line_mode) {
    if (*actual_length > capacity) *actual_length = capacity;
    for (ULONG i = 0U; i < *actual_length; ++i) {
      if (slot->data[i] == '\r' || slot->data[i] == '\n') {
        *actual_length = i + 1U;
        if (slot->data[i] == '\r' && i + 1U < slot->length &&
            i + 1U < capacity && slot->data[i + 1U] == '\n') ++*actual_length;
        break;
      }
    }
  }
  (void)memcpy(buffer, slot->data, *actual_length);
  if (*actual_length < slot->length) {
    slot->length -= (uint16_t)*actual_length;
    (void)memmove(slot->data, slot->data + *actual_length, slot->length);
    posture = tx_interrupt_control(TX_INT_DISABLE);
    result = tx_queue_front_send(ready_queue, &slot, TX_NO_WAIT);
    if (result == TX_SUCCESS) radio_manager.queues.ble_stream_context->stats[stream].rx_queued++;
    (void)tx_interrupt_control(posture);
    if (result != TX_SUCCESS) {
      uint32_t generation = slot->generation;
      (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
      Debug_UART_Log("CLI", "RX remainder rejected; generation=%lu status=%u",
          (unsigned long)generation, result);
      return result;
    }
  } else (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
  return TX_SUCCESS;
#else
  (void)stream;
  (void)buffer;
  (void)capacity;
  (void)wait_option;
  (void)line_mode;
  if (actual_length != NULL)
  {
    *actual_length = 0U;
  }
  return TX_NOT_AVAILABLE;
#endif
}

UINT WIFI_BLE_App_StreamRead(WifiBle_Stream_t stream, void *buffer,
                             ULONG capacity, ULONG *actual_length,
                             ULONG wait_option)
{
  return ble_stream_read(stream, buffer, capacity, actual_length, wait_option, 0U);
}

UINT WIFI_BLE_App_StreamReadLine(void *buffer, ULONG capacity,
                                 ULONG *actual_length)
{
  if (!capacity) return TX_SIZE_ERROR;
  return ble_stream_read(WIFI_BLE_STREAM_CLI, buffer, capacity, actual_length, TX_NO_WAIT, 1U);
}

uint32_t WIFI_BLE_App_IsTofImageSubscribed(void)
{
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  CloudRelay_Status_t cloud_status;
  uint32_t ble_requested = ((radio_manager.shadow.ble_transport_ready != 0U) &&
      (radio_manager.shadow.ble_connected != 0U) && (radio_manager.shadow.ble_tof_image_subscribed != 0U)) ? 1U : 0U;
  CloudRelay_GetStatus(&cloud_status);
  TOF_StreamDestination_t destination = TOF_App_GetStreamDestination();
  return ((radio_manager.queues.ble_tof_image_context != NULL) &&
          (((destination == TOF_STREAM_BLE) && (ble_requested != 0U)) ||
           ((destination == TOF_STREAM_CLOUD) &&
            (cloud_status.enabled != 0U) &&
            (cloud_status.paired != 0U)))) ? 1U : 0U;
#else
  return 0U;
#endif
}

uint32_t WIFI_BLE_App_IsTofImageIdle(void)
{
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  return ((radio_manager.queues.ble_tof_image_context == NULL) ||
          (radio_manager.queues.ble_tof_image_context->state == BLE_TOF_IMAGE_FREE)) ? 1U : 0U;
#else
  return 1U;
#endif
}

UINT __attribute__((optimize("Os")))
WIFI_BLE_App_PublishTofImage(uint32_t frame_id, uint8_t channel_id,
                             const float *pixels, uint8_t width,
                             uint8_t height)
{
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  size_t pixel_count;
  size_t payload_length;
  UINT posture;

  if ((pixels == NULL) || (width == 0U) || (height == 0U) ||
      (width > BLE_TOF_IMAGE_MAX_WIDTH) ||
      (height > BLE_TOF_IMAGE_MAX_HEIGHT))
  {
    return TX_PTR_ERROR;
  }
  if (WIFI_BLE_App_IsTofImageSubscribed() == 0U)
  {
    return TX_NOT_AVAILABLE;
  }

  pixel_count = (size_t)width * height;
  payload_length = pixel_count * sizeof(float);
  if ((pixel_count > BLE_TOF_IMAGE_MAX_PIXELS) ||
      (payload_length > UINT16_MAX))
  {
    return TX_SIZE_ERROR;
  }

  posture = tx_interrupt_control(TX_INT_DISABLE);
  if (radio_manager.queues.ble_tof_image_context->state != BLE_TOF_IMAGE_FREE)
  {
    radio_manager.queues.ble_tof_image_context->stats.frames_dropped_busy++;
    (void)tx_interrupt_control(posture);
    return TX_QUEUE_FULL;
  }
  radio_manager.queues.ble_tof_image_context->state = BLE_TOF_IMAGE_FILLING;
  radio_manager.queues.ble_tof_image_context->generation = radio_manager.shadow.ble_session_generation;
  (void)tx_interrupt_control(posture);

  (void)memcpy(radio_manager.queues.ble_tof_image_context->payload, pixels, payload_length);
  radio_manager.queues.ble_tof_image_context->frame_id = frame_id;
  radio_manager.queues.ble_tof_image_context->payload_crc32 =
      ble_crc32(radio_manager.queues.ble_tof_image_context->payload, payload_length);
  radio_manager.queues.ble_tof_image_context->payload_length = (uint16_t)payload_length;
  radio_manager.queues.ble_tof_image_context->offset = 0U;
  radio_manager.queues.ble_tof_image_context->width = width;
  radio_manager.queues.ble_tof_image_context->height = height;
  radio_manager.queues.ble_tof_image_context->channel_id = channel_id;
  radio_manager.queues.ble_tof_image_context->retries = 0U;

  /* The processing task cannot change active owner inside this publication.
   * A Cloud frame goes directly to WAIT_CLOUD, never BLE READY. Admission
   * failure releases immediately; there is no second-destination fallback. */
  TOF_StreamDestination_t destination = TOF_App_GetStreamDestination();
  UINT admitted = TX_SUCCESS;
  if (destination == TOF_STREAM_CLOUD)
  {
    admitted = CloudRelay_SubmitTofFrame(
        frame_id, channel_id, radio_manager.queues.ble_tof_image_context->payload,
        width, height, radio_manager.queues.ble_tof_image_context->payload_crc32);
  }
  posture = tx_interrupt_control(TX_INT_DISABLE);
  if ((admitted != TX_SUCCESS) ||
      ((destination != TOF_STREAM_BLE) && (destination != TOF_STREAM_CLOUD)))
  {
    radio_manager.queues.ble_tof_image_context->state = BLE_TOF_IMAGE_FREE;
    (void)tx_interrupt_control(posture);
    return TX_NOT_AVAILABLE;
  }
  radio_manager.queues.ble_tof_image_context->stats.frames_submitted++;
  radio_manager.queues.ble_tof_image_context->stats.last_submitted_frame = frame_id;
  radio_manager.queues.ble_tof_image_context->state =
      (destination == TOF_STREAM_CLOUD) ? BLE_TOF_IMAGE_WAIT_CLOUD : BLE_TOF_IMAGE_READY;
  (void)tx_interrupt_control(posture);
  return TX_SUCCESS;
#else
  (void)frame_id;
  (void)channel_id;
  (void)pixels;
  (void)width;
  (void)height;
  return TX_NOT_AVAILABLE;
#endif
}

void HAL_GPIO_EXTI_Rising_Callback(uint16_t gpio_pin)
{
#if (APP_ST67W6X_ENABLED == 1U)
  if (gpio_pin == SPI_RDY_Pin)
  {
    (void)spi_on_txn_data_ready();
  }
#else
  (void)gpio_pin;
#endif
}

void HAL_GPIO_EXTI_Falling_Callback(uint16_t gpio_pin)
{
#if (APP_ST67W6X_ENABLED == 0U)
  if (gpio_pin == TOF_INT_Pin)
  {
    platform_notify_gpio_interrupt();
  }
#endif
#if (APP_ST67W6X_ENABLED == 1U)
  if (gpio_pin == SPI_RDY_Pin)
  {
    (void)spi_on_header_ack();
  }
#else
  (void)gpio_pin;
#endif
}

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
static UINT wifi_create_pointer_queue(TX_QUEUE *queue, CHAR *name,
                                      ULONG *storage)
{
  return tx_queue_create(queue, name, TX_1_ULONG, storage,
                         WIFI_CONTROL_SLOT_COUNT * (ULONG)sizeof(ULONG));
}

static UINT wifi_request_slot_acquire(WifiBle_WifiRequest_t **slot)
{
  void *message = NULL;
  UINT result;

  if (slot == NULL)
  {
    return TX_PTR_ERROR;
  }
  *slot = NULL;
  if (radio_manager.queues.wifi_control_context == NULL)
  {
    return TX_NOT_AVAILABLE;
  }
  result = tx_queue_receive(&radio_manager.queues.wifi_control_context->request_free, &message,
                            TX_NO_WAIT);
  if (result == TX_QUEUE_EMPTY)
  {
    return TX_QUEUE_FULL;
  }
  if (result == TX_SUCCESS)
  {
    if (message == NULL)
    {
      return TX_QUEUE_ERROR;
    }
    *slot = (WifiBle_WifiRequest_t *)message;
  }
  return result;
}

static UINT wifi_request_slot_publish(WifiBle_WifiRequest_t *slot)
{
  void *message = slot;
  UINT result;

  if ((radio_manager.queues.wifi_control_context == NULL) || (slot == NULL))
  {
    return TX_PTR_ERROR;
  }
  result = tx_queue_send(&radio_manager.queues.wifi_control_context->request_ready, &message,
                         TX_NO_WAIT);
  if (result == TX_SUCCESS)
  {
    (void)tx_event_flags_set(&radio_control_events,
                             WIFI_CONTROL_WORK_FLAG, TX_OR);
  }
  return result;
}

static UINT wifi_request_slot_receive(WifiBle_WifiRequest_t **slot)
{
  void *message = NULL;
  UINT result;

  if (slot == NULL)
  {
    return TX_PTR_ERROR;
  }
  *slot = NULL;
  if (radio_manager.queues.wifi_control_context == NULL)
  {
    return TX_NOT_AVAILABLE;
  }
  result = tx_queue_receive(&radio_manager.queues.wifi_control_context->request_ready, &message,
                            TX_NO_WAIT);
  if (result == TX_SUCCESS)
  {
    if (message == NULL)
    {
      return TX_QUEUE_ERROR;
    }
    *slot = (WifiBle_WifiRequest_t *)message;
  }
  return result;
}

static UINT wifi_request_slot_release(WifiBle_WifiRequest_t *slot)
{
  void *message = slot;

  if (slot == NULL)
  {
    return TX_PTR_ERROR;
  }
  (void)memset(slot, 0, sizeof(*slot));
  if (radio_manager.queues.wifi_control_context == NULL)
  {
    return TX_NOT_AVAILABLE;
  }
  return tx_queue_send(&radio_manager.queues.wifi_control_context->request_free, &message,
                       TX_NO_WAIT);
}

static UINT wifi_result_slot_acquire(WifiBle_WifiResult_t **slot)
{
  void *message = NULL;
  UINT result;

  if (slot == NULL)
  {
    return TX_PTR_ERROR;
  }
  *slot = NULL;
  if (radio_manager.queues.wifi_control_context == NULL)
  {
    return TX_NOT_AVAILABLE;
  }
  result = tx_queue_receive(&radio_manager.queues.wifi_control_context->result_free, &message,
                            TX_NO_WAIT);
  if (result == TX_QUEUE_EMPTY)
  {
    return TX_QUEUE_FULL;
  }
  if (result == TX_SUCCESS)
  {
    if (message == NULL)
    {
      return TX_QUEUE_ERROR;
    }
    *slot = (WifiBle_WifiResult_t *)message;
  }
  return result;
}

static UINT wifi_result_slot_acquire_wait(WifiBle_WifiResult_t **slot)
{
  void *message = NULL;
  UINT result;

  if (slot == NULL)
  {
    return TX_PTR_ERROR;
  }
  *slot = NULL;
  if (radio_manager.queues.wifi_control_context == NULL)
  {
    return TX_NOT_AVAILABLE;
  }
  do
  {
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
    ble_control_execute();
#endif
    result = tx_queue_receive(&radio_manager.queues.wifi_control_context->result_free,
                              &message, 1U);
  } while (result == TX_QUEUE_EMPTY);
  if (result == TX_SUCCESS)
  {
    if (message == NULL)
    {
      return TX_QUEUE_ERROR;
    }
    *slot = (WifiBle_WifiResult_t *)message;
  }
  return result;
}

static UINT wifi_result_slot_publish(WifiBle_WifiResult_t *slot)
{
  void *message = slot;

  if ((radio_manager.queues.wifi_control_context == NULL) || (slot == NULL))
  {
    return TX_PTR_ERROR;
  }
  return tx_queue_send(&radio_manager.queues.wifi_control_context->result_ready, &message,
                       TX_NO_WAIT);
}

static UINT wifi_result_slot_receive(WifiBle_WifiResult_t **slot)
{
  void *message = NULL;
  UINT result;

  if (slot == NULL)
  {
    return TX_PTR_ERROR;
  }
  *slot = NULL;
  if (radio_manager.queues.wifi_control_context == NULL)
  {
    return TX_NOT_AVAILABLE;
  }
  result = tx_queue_receive(&radio_manager.queues.wifi_control_context->result_ready, &message,
                            TX_NO_WAIT);
  if (result == TX_SUCCESS)
  {
    if (message == NULL)
    {
      return TX_QUEUE_ERROR;
    }
    *slot = (WifiBle_WifiResult_t *)message;
  }
  return result;
}

static UINT wifi_result_slot_release(WifiBle_WifiResult_t *slot)
{
  void *message = slot;

  if (slot == NULL)
  {
    return TX_PTR_ERROR;
  }
  (void)memset(slot, 0, sizeof(*slot));
  if (radio_manager.queues.wifi_control_context == NULL)
  {
    return TX_NOT_AVAILABLE;
  }
  return tx_queue_send(&radio_manager.queues.wifi_control_context->result_free, &message,
                       TX_NO_WAIT);
}

static UINT wifi_queue_expect_count(TX_QUEUE *queue, ULONG expected)
{
  ULONG count = 0U;
  UINT result = tx_queue_info_get(queue, TX_NULL, &count, TX_NULL, TX_NULL,
                                  TX_NULL, TX_NULL);

  if (result != TX_SUCCESS)
  {
    return result;
  }
  return (count == expected) ? TX_SUCCESS : TX_QUEUE_ERROR;
}

static uint32_t wifi_memory_is_zero(const void *memory, size_t size)
{
  const uint8_t *bytes = (const uint8_t *)memory;

  for (size_t i = 0U; i < size; ++i)
  {
    if (bytes[i] != 0U)
    {
      return 0U;
    }
  }
  return 1U;
}

static UINT wifi_control_queue_self_test(void)
{
  WifiBle_WifiRequest_t *requests[WIFI_CONTROL_SLOT_COUNT] = {0};
  WifiBle_WifiResult_t *results[WIFI_CONTROL_SLOT_COUNT] = {0};
  WifiBle_WifiRequest_t *extra_request = NULL;
  WifiBle_WifiRequest_t *received_request = NULL;
  WifiBle_WifiResult_t *extra_result = NULL;
  WifiBle_WifiResult_t *received_result = NULL;
  UINT status;

  if ((wifi_queue_expect_count(&radio_manager.queues.wifi_control_context->request_free,
                               WIFI_CONTROL_SLOT_COUNT) != TX_SUCCESS) ||
      (wifi_queue_expect_count(&radio_manager.queues.wifi_control_context->request_ready, 0U) !=
       TX_SUCCESS) ||
      (wifi_queue_expect_count(&radio_manager.queues.wifi_control_context->result_free,
                               WIFI_CONTROL_SLOT_COUNT) != TX_SUCCESS) ||
      (wifi_queue_expect_count(&radio_manager.queues.wifi_control_context->result_ready, 0U) !=
       TX_SUCCESS))
  {
    return TX_QUEUE_ERROR;
  }

  for (uint32_t i = 0U; i < WIFI_CONTROL_SLOT_COUNT; ++i)
  {
    status = wifi_request_slot_acquire(&requests[i]);
    if ((status != TX_SUCCESS) || (requests[i] == NULL))
    {
      return TX_QUEUE_ERROR;
    }
    for (uint32_t j = 0U; j < i; ++j)
    {
      if (requests[i] == requests[j])
      {
        return TX_QUEUE_ERROR;
      }
    }
  }
  if (wifi_request_slot_acquire(&extra_request) != TX_QUEUE_FULL)
  {
    return TX_QUEUE_ERROR;
  }
  for (uint32_t i = 0U; i < WIFI_CONTROL_SLOT_COUNT; ++i)
  {
    if (wifi_request_slot_publish(requests[i]) != TX_SUCCESS)
    {
      return TX_QUEUE_ERROR;
    }
  }
  for (uint32_t i = 0U; i < WIFI_CONTROL_SLOT_COUNT; ++i)
  {
    if ((wifi_request_slot_receive(&received_request) != TX_SUCCESS) ||
        (received_request != requests[i]))
    {
      return TX_QUEUE_ERROR;
    }
    (void)memset(received_request, 0xA5, sizeof(*received_request));
    if ((wifi_request_slot_release(received_request) != TX_SUCCESS) ||
        (wifi_memory_is_zero(received_request, sizeof(*received_request)) ==
         0U))
    {
      return TX_QUEUE_ERROR;
    }
  }

  for (uint32_t i = 0U; i < WIFI_CONTROL_SLOT_COUNT; ++i)
  {
    status = wifi_result_slot_acquire(&results[i]);
    if ((status != TX_SUCCESS) || (results[i] == NULL))
    {
      return TX_QUEUE_ERROR;
    }
    for (uint32_t j = 0U; j < i; ++j)
    {
      if (results[i] == results[j])
      {
        return TX_QUEUE_ERROR;
      }
    }
  }
  if (wifi_result_slot_acquire(&extra_result) != TX_QUEUE_FULL)
  {
    return TX_QUEUE_ERROR;
  }
  for (uint32_t i = 0U; i < WIFI_CONTROL_SLOT_COUNT; ++i)
  {
    if (wifi_result_slot_publish(results[i]) != TX_SUCCESS)
    {
      return TX_QUEUE_ERROR;
    }
  }
  for (uint32_t i = 0U; i < WIFI_CONTROL_SLOT_COUNT; ++i)
  {
    if ((wifi_result_slot_receive(&received_result) != TX_SUCCESS) ||
        (received_result != results[i]))
    {
      return TX_QUEUE_ERROR;
    }
    (void)memset(received_result, 0xA5, sizeof(*received_result));
    if ((wifi_result_slot_release(received_result) != TX_SUCCESS) ||
        (wifi_memory_is_zero(received_result, sizeof(*received_result)) ==
         0U))
    {
      return TX_QUEUE_ERROR;
    }
  }

  if ((wifi_queue_expect_count(&radio_manager.queues.wifi_control_context->request_free,
                               WIFI_CONTROL_SLOT_COUNT) != TX_SUCCESS) ||
      (wifi_queue_expect_count(&radio_manager.queues.wifi_control_context->request_ready, 0U) !=
       TX_SUCCESS) ||
      (wifi_queue_expect_count(&radio_manager.queues.wifi_control_context->result_free,
                               WIFI_CONTROL_SLOT_COUNT) != TX_SUCCESS) ||
      (wifi_queue_expect_count(&radio_manager.queues.wifi_control_context->result_ready, 0U) !=
       TX_SUCCESS))
  {
    return TX_QUEUE_ERROR;
  }
  return TX_SUCCESS;
}

static void wifi_control_rollback(uint32_t queue_mask)
{
  WifiBle_WifiControlContext_t *context = radio_manager.queues.wifi_control_context;

  if (context == NULL)
  {
    return;
  }
  if ((queue_mask & WIFI_QUEUE_CREATED_RESULT_READY) != 0U)
  {
    (void)tx_queue_delete(&context->result_ready);
  }
  if ((queue_mask & WIFI_QUEUE_CREATED_RESULT_FREE) != 0U)
  {
    (void)tx_queue_delete(&context->result_free);
  }
  if ((queue_mask & WIFI_QUEUE_CREATED_REQUEST_READY) != 0U)
  {
    (void)tx_queue_delete(&context->request_ready);
  }
  if ((queue_mask & WIFI_QUEUE_CREATED_REQUEST_FREE) != 0U)
  {
    (void)tx_queue_delete(&context->request_free);
  }
  (void)memset(context, 0, sizeof(*context));
  radio_manager.queues.wifi_control_context = NULL;
  radio_manager.work.wifi_pending_event_bits = 0U;
  (void)tx_byte_release(context);
}

static UINT wifi_control_initialize(void)
{
  TX_BYTE_POOL *radio_pool = MX_RadioBytePool_Get();
  void *memory = NULL;
  ULONG available = 0U;
  ULONG fragments = 0U;
  ULONG ignored_flags = 0U;
  uint32_t queue_mask = 0U;
  UINT result;

  if ((radio_pool == NULL) ||
      (tx_byte_allocate(radio_pool, &memory,
                        sizeof(WifiBle_WifiControlContext_t),
                        TX_NO_WAIT) != TX_SUCCESS))
  {
    return TX_NO_MEMORY;
  }

  radio_manager.queues.wifi_control_context = (WifiBle_WifiControlContext_t *)memory;
  (void)memset(radio_manager.queues.wifi_control_context, 0, sizeof(*radio_manager.queues.wifi_control_context));
  radio_manager.queues.wifi_control_context->status.last_status = (int32_t)W6X_STATUS_OK;

  result = wifi_create_pointer_queue(&radio_manager.queues.wifi_control_context->request_free,
                                     "WiFi request free",
                                     radio_manager.queues.wifi_control_context->request_free_storage);
  if (result != TX_SUCCESS)
  {
    goto fail;
  }
  queue_mask |= WIFI_QUEUE_CREATED_REQUEST_FREE;
  result = wifi_create_pointer_queue(
      &radio_manager.queues.wifi_control_context->request_ready, "WiFi request ready",
      radio_manager.queues.wifi_control_context->request_ready_storage);
  if (result != TX_SUCCESS)
  {
    goto fail;
  }
  queue_mask |= WIFI_QUEUE_CREATED_REQUEST_READY;
  result = wifi_create_pointer_queue(&radio_manager.queues.wifi_control_context->result_free,
                                     "WiFi result free",
                                     radio_manager.queues.wifi_control_context->result_free_storage);
  if (result != TX_SUCCESS)
  {
    goto fail;
  }
  queue_mask |= WIFI_QUEUE_CREATED_RESULT_FREE;
  result = wifi_create_pointer_queue(&radio_manager.queues.wifi_control_context->result_ready,
                                     "WiFi result ready",
                                     radio_manager.queues.wifi_control_context->result_ready_storage);
  if (result != TX_SUCCESS)
  {
    goto fail;
  }
  queue_mask |= WIFI_QUEUE_CREATED_RESULT_READY;

  for (uint32_t i = 0U; i < WIFI_CONTROL_SLOT_COUNT; ++i)
  {
    result = wifi_request_slot_release(
        &radio_manager.queues.wifi_control_context->request_slots[i]);
    if (result != TX_SUCCESS)
    {
      goto fail;
    }
  }
  for (uint32_t i = 0U; i < WIFI_CONTROL_SLOT_COUNT; ++i)
  {
    result = wifi_result_slot_release(&radio_manager.queues.wifi_control_context->result_slots[i]);
    if (result != TX_SUCCESS)
    {
      goto fail;
    }
  }

  result = wifi_control_queue_self_test();
  if (result != TX_SUCCESS)
  {
    LogError("ST67W6X Wi-Fi queues: self-test FAIL (%u).\r\n", result);
    goto fail;
  }
  (void)tx_event_flags_get(&radio_control_events,
                           WIFI_CONTROL_WORK_FLAG, TX_OR_CLEAR,
                           &ignored_flags, TX_NO_WAIT);
  (void)tx_byte_pool_info_get(radio_pool, TX_NULL, &available, &fragments,
                              TX_NULL, TX_NULL, TX_NULL);
  LogInfo("ST67W6X Wi-Fi queues: self-test PASS, 4+4 slots, context %lu bytes, radio pool %lu bytes free.\r\n",
          (unsigned long)sizeof(*radio_manager.queues.wifi_control_context),
          (unsigned long)available);
  return TX_SUCCESS;

fail:
  wifi_control_rollback(queue_mask);
  return result;
}

static W6X_Status_t wifi_enable_station_dhcp(void)
{
  W61_Object_t *driver = W61_ObjGet();
  W61_Net_DhcpType_e dhcp = W61_NET_DHCP_STA_ENABLED;
  uint32_t enable = 1U;
  W61_Status_t status;

  if (driver == NULL)
  {
    return W6X_STATUS_ERROR;
  }
  status = W61_Net_SetDhcpConfig(driver, &dhcp, &enable);
  return (status == W61_STATUS_OK) ? W6X_STATUS_OK : W6X_STATUS_ERROR;
}

static W6X_Status_t wifi_get_station_ip(uint8_t ip_address[4],
                                        uint8_t gateway_address[4],
                                        uint8_t netmask_address[4])
{
  W61_Object_t *driver = W61_ObjGet();
  W61_Status_t status;

  if (driver == NULL)
  {
    return W6X_STATUS_ERROR;
  }
  status = W61_Net_Station_GetIPAddress(driver);
  if (status != W61_STATUS_OK)
  {
    return W6X_STATUS_ERROR;
  }
  (void)memcpy(ip_address, driver->NetCtx.Net_sta_info.IP_Addr, 4U);
  (void)memcpy(gateway_address, driver->NetCtx.Net_sta_info.Gateway_Addr, 4U);
  (void)memcpy(netmask_address, driver->NetCtx.Net_sta_info.IP_Mask, 4U);
  return W6X_STATUS_OK;
}

static void wifi_refresh_status(void)
{
  W6X_WiFi_StaStateType_e state = W6X_WIFI_STATE_STA_DISCONNECTED;
  W6X_WiFi_Connect_t connection = {0};
  W6X_Status_t status;
  uint32_t generation;

  if (radio_manager.queues.wifi_control_context == NULL)
  {
    return;
  }
  generation = radio_manager.work.wifi_event_generation;
  radio_manager.work.wifi_last_probe_tick = HAL_GetTick();
  W61_Object_t *driver = W61_ObjGet();
  if ((driver != NULL) && driver->Modem.handler_data.dns_drain_active)
  {
    /* Read-only DNS owns AT until its terminal; do not turn deferred status
     * admission into a false disconnect or sit on TX while awaiting it. */
    radio_manager.shadow.wifi_state_confirmed = 0U;
    radio_manager.work.wifi_last_probe_status = W6X_STATUS_BUSY;
    return;
  }
  radio_manager.counters.faults.wifi_state_queries++;
  status = W6X_WiFi_Station_GetState(&state, &connection);
  radio_manager.work.wifi_last_probe_status = status;
  if (generation != radio_manager.work.wifi_event_generation)
  {
    /* A newer event supersedes the AT response that was in flight. */
    return;
  }
  if (status != W6X_STATUS_OK)
  {
    radio_manager.shadow.wifi_state_confirmed = 0U;
    radio_manager.counters.faults.wifi_query_failures++;
    radio_manager.queues.wifi_control_context->status.last_status = (int32_t)status;
    return;
  }
  radio_manager.shadow.wifi_state_confirmed = 1U;
  radio_manager.queues.wifi_control_context->status.station_state = (uint32_t)state;

  if ((state == W6X_WIFI_STATE_STA_CONNECTED) ||
      (state == W6X_WIFI_STATE_STA_GOT_IP))
  {
    radio_manager.shadow.wifi_connected = 1U;
    (void)memset(radio_manager.queues.wifi_control_context->status.ssid, 0,
                 sizeof(radio_manager.queues.wifi_control_context->status.ssid));
    (void)memcpy(radio_manager.queues.wifi_control_context->status.ssid, connection.SSID,
                 sizeof(radio_manager.queues.wifi_control_context->status.ssid) - 1U);
    (void)memcpy(radio_manager.queues.wifi_control_context->status.ap_mac, connection.MAC,
                 sizeof(radio_manager.queues.wifi_control_context->status.ap_mac));
    radio_manager.queues.wifi_control_context->status.channel = connection.Channel;
    radio_manager.queues.wifi_control_context->status.rssi = connection.Rssi;
  }
  else
  {
    radio_manager.shadow.wifi_connected = 0U;
    radio_manager.shadow.wifi_has_ip = 0U;
    radio_manager.queues.wifi_control_context->status.ip_valid = 0U;
    (void)memset(radio_manager.queues.wifi_control_context->status.ssid, 0,
                 sizeof(radio_manager.queues.wifi_control_context->status.ssid));
    (void)memset(radio_manager.queues.wifi_control_context->status.ap_mac, 0,
                 sizeof(radio_manager.queues.wifi_control_context->status.ap_mac));
    (void)memset(radio_manager.queues.wifi_control_context->status.ip_address, 0,
                 sizeof(radio_manager.queues.wifi_control_context->status.ip_address));
    (void)memset(radio_manager.queues.wifi_control_context->status.gateway_address, 0,
                 sizeof(radio_manager.queues.wifi_control_context->status.gateway_address));
    (void)memset(radio_manager.queues.wifi_control_context->status.netmask_address, 0,
                 sizeof(radio_manager.queues.wifi_control_context->status.netmask_address));
  }

  if ((state == W6X_WIFI_STATE_STA_GOT_IP) || (radio_manager.shadow.wifi_has_ip != 0U))
  {
    status = wifi_get_station_ip(
        radio_manager.queues.wifi_control_context->status.ip_address,
        radio_manager.queues.wifi_control_context->status.gateway_address,
        radio_manager.queues.wifi_control_context->status.netmask_address);
    radio_manager.queues.wifi_control_context->status.ip_valid =
        (status == W6X_STATUS_OK) ? 1U : 0U;
    if (status == W6X_STATUS_OK)
    {
      radio_manager.shadow.wifi_has_ip = 1U;
    }
    else radio_manager.shadow.wifi_state_confirmed = 0U;
  }
  radio_manager.queues.wifi_control_context->status.connected = radio_manager.shadow.wifi_connected;
  radio_manager.queues.wifi_control_context->status.has_ip = radio_manager.shadow.wifi_has_ip;
}

static void wifi_execute_request(WifiBle_WifiRequest_t *request,
                                 WifiBle_WifiResult_t *result)
{
  W6X_Status_t status = W6X_STATUS_ERROR;
  WifiBle_WifiOperation_t active_operation = WIFI_BLE_WIFI_OPERATION_NONE;
  ULONG ignored_flags = 0U;
  UINT posture;

  if ((radio_manager.queues.wifi_control_context == NULL) || (request == NULL) || (result == NULL))
  {
    return;
  }
  (void)memset(result, 0, sizeof(*result));
  result->operation = request->operation;
  result->request_id = request->request_id;
  result->route = request->route;

  if (request->operation == WIFI_BLE_WIFI_OPERATION_SCAN)
  {
    active_operation = WIFI_BLE_WIFI_OPERATION_SCAN;
  }
  else if (request->operation == WIFI_BLE_WIFI_OPERATION_CONNECT)
  {
    active_operation = WIFI_BLE_WIFI_OPERATION_CONNECT;
  }
  else if (request->operation == WIFI_BLE_WIFI_OPERATION_DISCONNECT)
  {
    active_operation = WIFI_BLE_WIFI_OPERATION_DISCONNECT;
  }

  posture = tx_interrupt_control(TX_INT_DISABLE);
  radio_manager.queues.wifi_control_context->active_operation = active_operation;
  radio_manager.work.wifi_service_started_ms = HAL_GetTick();
  radio_manager.queues.wifi_control_context->status.operation_active =
      (uint32_t)active_operation;
  (void)tx_interrupt_control(posture);

  if (active_operation == WIFI_BLE_WIFI_OPERATION_SCAN)
  {
    W6X_WiFi_Scan_Opts_t options = {0};
    UINT wait_status;

    (void)tx_event_flags_get(&radio_control_events,
                             WIFI_CONTROL_SCAN_DONE_FLAG, TX_OR_CLEAR,
                             &ignored_flags, TX_NO_WAIT);
    (void)memset(&radio_manager.queues.wifi_control_context->scan_results, 0,
                 sizeof(radio_manager.queues.wifi_control_context->scan_results));
    radio_manager.queues.wifi_control_context->scan_results.status =
        (int32_t)W6X_STATUS_ERROR;
    options.Scan_type = W6X_WIFI_SCAN_ACTIVE;
    options.MaxCnt = WIFI_BLE_WIFI_SCAN_MAX_APS;
    status = W6X_WiFi_Scan(&options, wifi_scan_callback);
    if (status == W6X_STATUS_OK)
    {
      wait_status = tx_event_flags_get(&radio_control_events,
                                       WIFI_CONTROL_SCAN_DONE_FLAG,
                                       TX_OR_CLEAR, &ignored_flags,
                                       WIFI_CONTROL_SCAN_WAIT_TICKS);
      if (wait_status == TX_SUCCESS)
      {
        status = (W6X_Status_t)radio_manager.queues.wifi_control_context->scan_results.status;
      }
      else
      {
        status = (wait_status == TX_NO_EVENTS) ?
                 W6X_STATUS_TIMEOUT : W6X_STATUS_ERROR;
        (void)memset(&radio_manager.queues.wifi_control_context->scan_results, 0,
                     sizeof(radio_manager.queues.wifi_control_context->scan_results));
        radio_manager.queues.wifi_control_context->scan_results.status = (int32_t)status;
      }
    }
    else
    {
      radio_manager.queues.wifi_control_context->scan_results.status = (int32_t)status;
    }
    result->scan_results = radio_manager.queues.wifi_control_context->scan_results;
  }
  else if (active_operation == WIFI_BLE_WIFI_OPERATION_CONNECT)
  {
    W6X_WiFi_Connect_Opts_t options = {0};

    (void)memcpy(options.SSID, request->ssid, sizeof(options.SSID));
    (void)memcpy(options.Password, request->password,
                 sizeof(options.Password));
    /* The stack-local W6X options now own the working copy. Do not retain the
     * sensitive password in the queued request during the blocking call. */
    (void)memset(request->password, 0, sizeof(request->password));
    /* Set before the first association AT bytes. CONNECTED can arrive while
     * NCP is delaying a newly announced BLE raw prompt. An existing owner
     * still drains; no fresh notification may announce during this call. */
    radio_manager.work.wifi_connect_call_active = 1U;
    uint32_t wait_started = HAL_GetTick();
    Debug_UART_Log("RADIO-WAIT", "START reason=WIFI_CONNECT started_ms=%lu",
                   (unsigned long)wait_started);
    status = W6X_WiFi_Connect(&options);
    radio_manager.work.wifi_connect_call_active = 0U;
    Debug_UART_Log("RADIO-WAIT", "END reason=WIFI_CONNECT elapsed_ms=%lu result=%ld",
                   (unsigned long)(HAL_GetTick() - wait_started), (long)status);
    (void)memset(&options, 0, sizeof(options));
    wifi_refresh_status();
    if ((status == W6X_STATUS_OK) &&
        (radio_manager.queues.wifi_control_context->status.ip_valid == 0U))
    {
      status = W6X_STATUS_ERROR;
    }
  }
  else if (active_operation == WIFI_BLE_WIFI_OPERATION_DISCONNECT)
  {
    uint32_t wait_started = HAL_GetTick();
    Debug_UART_Log("RADIO-WAIT", "START reason=WIFI_DISCONNECT started_ms=%lu",
                   (unsigned long)wait_started);
    status = W6X_WiFi_Disconnect(request->forget);
    Debug_UART_Log("RADIO-WAIT", "END reason=WIFI_DISCONNECT elapsed_ms=%lu result=%ld",
                   (unsigned long)(HAL_GetTick() - wait_started), (long)status);
    wifi_refresh_status();
  }

  posture = tx_interrupt_control(TX_INT_DISABLE);
  radio_manager.queues.wifi_control_context->status.last_status = (int32_t)status;
  radio_manager.queues.wifi_control_context->status.operation_active = 0U;
  radio_manager.queues.wifi_control_context->active_operation = WIFI_BLE_WIFI_OPERATION_NONE;
  (void)tx_interrupt_control(posture);
  result->final_status = (int32_t)status;
  result->wifi_status = radio_manager.queues.wifi_control_context->status;
}


static void wifi_process_pending_events(void)
{
  uint32_t events;
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);

  events = radio_manager.work.wifi_pending_event_bits;
  radio_manager.work.wifi_pending_event_bits = 0U;
  (void)tx_interrupt_control(posture);
  if ((events & WIFI_EVENT_CONNECTED_FLAG) != 0U)
  {
    LogInfo("ST67W6X Wi-Fi connected.\r\n");
  }
  if ((events & WIFI_EVENT_GOT_IP_FLAG) != 0U)
  {
    LogInfo("ST67W6X Wi-Fi address acquired.\r\n");
  }
  if ((events & WIFI_EVENT_DISCONNECTED_FLAG) != 0U)
  {
    LogInfo("ST67W6X Wi-Fi disconnected.\r\n");
  }
}

static void wifi_event_callback(W6X_event_id_t event_id, void *event_args)
{
  UINT posture;

  (void)event_args;
  posture = tx_interrupt_control(TX_INT_DISABLE);
  radio_manager.work.wifi_event_generation++;
  radio_manager.shadow.wifi_state_confirmed = 1U;
  if (event_id == W6X_WIFI_EVT_CONNECTED_ID)
  {
    radio_manager.shadow.wifi_connected = 1U;
    radio_manager.work.wifi_pending_event_bits |= WIFI_EVENT_CONNECTED_FLAG;
  }
  else if (event_id == W6X_WIFI_EVT_GOT_IP_ID)
  {
    radio_manager.shadow.wifi_has_ip = 1U;
    radio_manager.work.wifi_pending_event_bits |= WIFI_EVENT_GOT_IP_FLAG;
  }
  else if (event_id == W6X_WIFI_EVT_DISCONNECTED_ID)
  {
    radio_manager.shadow.wifi_connected = 0U;
    radio_manager.shadow.wifi_has_ip = 0U;
    radio_manager.work.wifi_pending_event_bits |= WIFI_EVENT_DISCONNECTED_FLAG;
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
    CloudRelay_NetworkLost();
#endif
  }
  (void)tx_interrupt_control(posture);
}

static void wifi_scan_callback(int32_t status,
                               W6X_WiFi_Scan_Result_t *results)
{
  uint32_t count = 0U;

  if ((radio_manager.queues.wifi_control_context == NULL) ||
      (radio_manager.queues.wifi_control_context->active_operation !=
       WIFI_BLE_WIFI_OPERATION_SCAN))
  {
    return;
  }
  (void)memset(&radio_manager.queues.wifi_control_context->scan_results, 0,
               sizeof(radio_manager.queues.wifi_control_context->scan_results));
  radio_manager.queues.wifi_control_context->scan_results.status = status;
  if ((status == (int32_t)W6X_STATUS_OK) &&
      (results != NULL) && (results->AP != NULL))
  {
    count = results->Count;
    if (count > WIFI_BLE_WIFI_SCAN_MAX_APS)
    {
      count = WIFI_BLE_WIFI_SCAN_MAX_APS;
    }
    for (uint32_t i = 0U; i < count; ++i)
    {
      WifiBle_WifiAccessPoint_t *destination =
          &radio_manager.queues.wifi_control_context->scan_results.access_points[i];
      (void)memcpy(destination->ssid, results->AP[i].SSID,
                   sizeof(destination->ssid) - 1U);
      (void)memcpy(destination->mac, results->AP[i].MAC,
                   sizeof(destination->mac));
      destination->security = (uint32_t)results->AP[i].Security;
      destination->protocol = (uint32_t)results->AP[i].Protocol;
      destination->rssi = results->AP[i].RSSI;
      destination->channel = results->AP[i].Channel;
    }
  }
  radio_manager.queues.wifi_control_context->scan_results.count = count;
  (void)tx_event_flags_set(&radio_control_events,
                           WIFI_CONTROL_SCAN_DONE_FLAG, TX_OR);
}
#endif

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U) || (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
void WIFI_BLE_App_WifiControlRun(void)
{
  ULONG actual_flags = 0U;
  UINT status;

  while (radio_control_events_ready == 0U)
  {
    tx_thread_sleep(1U);
  }
  status = tx_event_flags_get(&radio_control_events,
                              WIFI_CONTROL_RADIO_READY_FLAG, TX_AND,
                              &actual_flags, TX_WAIT_FOREVER);
  if (status != TX_SUCCESS)
  {
    LogError("ST67W6X Wi-Fi control radio-ready wait failed (%u).\r\n",
             status);
    return;
  }

  for (;;)
  {
    status = tx_event_flags_get(&radio_control_events,
                                WIFI_CONTROL_WORK_FLAG, TX_OR_CLEAR,
                                &actual_flags, WIFI_HEALTH_PROBE_WAIT_TICKS);
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    /* BLE mailbox wakes must not indefinitely postpone a failed Wi-Fi
     * refresh. Pace retry on the existing probe timestamp and worker. */
    if ((radio_manager.shadow.wifi_state_confirmed == 0U) &&
        (radio_manager.shadow.wifi_connected != 0U) &&
        ((HAL_GetTick() - radio_manager.work.wifi_last_probe_tick) >= 1000U))
      wifi_refresh_status();
#endif
    if (status == TX_NO_EVENTS)
    {
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
      if ((radio_manager.shadow.ble_connected != 0U) &&
          ((HAL_GetTick() - radio_manager.work.ble_last_activity_tick) <
           BLE_CONNECTED_IDLE_MS))
      {
        continue;
      }
#endif
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
      wifi_refresh_status();
#endif
      continue;
    }
    if (status != TX_SUCCESS)
    {
      LogError("ST67W6X Wi-Fi control work wait failed (%u).\r\n", status);
      return;
    }

    for (;;)
    {
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
      ble_control_execute();
#endif
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
      WifiBle_WifiRequest_t *request = NULL;
      WifiBle_WifiResult_t *result = NULL;
      UINT release_status;

      status = wifi_request_slot_receive(&request);
      if (status == TX_QUEUE_EMPTY)
      {
        break;
      }
      if (status != TX_SUCCESS)
      {
        LogError("ST67W6X Wi-Fi request receive failed (%u).\r\n", status);
        break;
      }

      status = wifi_result_slot_acquire_wait(&result);
      if (status != TX_SUCCESS)
      {
        LogError("ST67W6X Wi-Fi result acquire failed (%u).\r\n", status);
        (void)wifi_request_slot_release(request);
        continue;
      }

      wifi_execute_request(request, result);
      release_status = wifi_request_slot_release(request);
      status = wifi_result_slot_publish(result);
      if (status != TX_SUCCESS)
      {
        (void)wifi_result_slot_release(result);
        LogError("ST67W6X Wi-Fi result publish failed (%u).\r\n", status);
      }
      if (release_status != TX_SUCCESS)
      {
        LogError("ST67W6X Wi-Fi request release failed (%u).\r\n",
                 release_status);
      }
#else
      break;
#endif
    }
  }
}
#else
void WIFI_BLE_App_WifiControlRun(void) {}
#endif

#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static void ble_event_callback(W6X_event_id_t event_id, void *event_args)
{
  W6X_Ble_CbParamData_t *event = (W6X_Ble_CbParamData_t *)event_args;
  radio_manager.work.ble_last_activity_tick = HAL_GetTick();

  if (event_id == W6X_BLE_EVT_CONNECTED_ID)
  {
    if (event != NULL)
    {
      UINT posture = tx_interrupt_control(TX_INT_DISABLE);
      radio_manager.shadow.ble_session_generation++;
      radio_manager.work.ble_link_mismatch_count = 0U;
      radio_manager.work.ble_mode_mismatch_count = 0U;
      radio_manager.shadow.ble_connected = 1U;
      radio_manager.shadow.ble_advertising = 0U;
      radio_manager.shadow.ble_advertising_evidence = WIFI_BLE_ADV_CONNECTION_EVENT;
      radio_manager.shadow.ble_mode_confirmed = 1U;
      radio_manager.shadow.ble_link_confirmed = 1U;
      radio_manager.shadow.ble_connection_handle = event->remote_ble_device.conn_handle;
      radio_manager.work.ble_connect_pending = 1U;
      radio_manager.work.ble_stream_flush_pending = 1U;
      (void)tx_interrupt_control(posture);
    }
  }
  else if (event_id == W6X_BLE_EVT_DISCONNECTED_ID)
  {
    ble_note_disconnected();
    radio_manager.shadow.ble_link_confirmed = 1U;
  }
  else if ((event_id == W6X_BLE_EVT_NOTIFICATION_STATUS_ENABLED_ID) ||
           (event_id == W6X_BLE_EVT_NOTIFICATION_STATUS_DISABLED_ID))
  {
    uint32_t enabled =
        (event_id == W6X_BLE_EVT_NOTIFICATION_STATUS_ENABLED_ID) ? 1U : 0U;
    if (event != NULL)
    {
      if ((event->service_idx == BLE_CLI_SERVICE_INDEX) &&
          (event->charac_idx == BLE_TX_CHAR_INDEX))
      {
        radio_manager.shadow.ble_cli_tx_subscribed = enabled;
      }
      else if ((event->service_idx == BLE_DEBUG_SERVICE_INDEX) &&
               (event->charac_idx == BLE_TX_CHAR_INDEX))
      {
        radio_manager.shadow.ble_debug_tx_subscribed = enabled;
      }
      else if ((event->service_idx == BLE_CLI_SERVICE_INDEX) &&
               (event->charac_idx == BLE_TOF_IMAGE_CHAR_INDEX))
      {
        radio_manager.shadow.ble_tof_image_subscribed = enabled;
        if (enabled != 0U) TOF_App_RequestStream(TOF_STREAM_BLE);
        else TOF_App_ReleaseStream(TOF_STREAM_BLE);
      }
    }
  }
  else if ((event_id == W6X_BLE_EVT_MTU_SIZE_ID) && (event != NULL))
  {
    radio_manager.shadow.ble_mtu = event->mtu_size;
  }
  else if ((event_id == W6X_BLE_EVT_WRITE_ID) && (event != NULL))
  {
    radio_manager.counters.ble_rx_write_events++;
    if ((radio_manager.shadow.ble_connected == 0U) ||
        (event->remote_ble_device.conn_handle != radio_manager.shadow.ble_connection_handle) ||
        (event->charac_idx != BLE_RX_CHAR_INDEX) ||
        (event->available_data_length == 0U) ||
        (event->available_data_length > sizeof(radio_manager.queues.ble_receive_buffer)))
    {
      radio_manager.counters.ble_rx_discarded_bytes += event->available_data_length;
    }
    else if (event->service_idx == BLE_CLI_SERVICE_INDEX)
    {
      ble_stream_enqueue_rx(WIFI_BLE_STREAM_CLI, radio_manager.queues.ble_receive_buffer,
                            event->available_data_length);
    }
    else if (event->service_idx == BLE_DEBUG_SERVICE_INDEX)
    {
#if (BLE_DEBUG_RX_POLICY_ENABLED == 1U)
      ble_stream_enqueue_rx(WIFI_BLE_STREAM_DEBUG, radio_manager.queues.ble_receive_buffer,
                            event->available_data_length);
#else
      UINT posture = tx_interrupt_control(TX_INT_DISABLE);
      radio_manager.counters.ble_rx_discarded_bytes += event->available_data_length;
      if (radio_manager.queues.ble_stream_context != NULL)
      {
        radio_manager.queues.ble_stream_context->stats[WIFI_BLE_STREAM_DEBUG].rx_dropped_events++;
        radio_manager.queues.ble_stream_context->stats[WIFI_BLE_STREAM_DEBUG].rx_dropped_bytes +=
            event->available_data_length;
      }
      (void)tx_interrupt_control(posture);
#endif
    }
    else
    {
      radio_manager.counters.ble_rx_discarded_bytes += event->available_data_length;
    }
  }
}

static void ble_note_disconnected(void)
{
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  radio_manager.work.ble_last_activity_tick = HAL_GetTick();
  radio_manager.shadow.ble_session_generation++;
  radio_manager.work.ble_link_mismatch_count = 0U;
  radio_manager.shadow.ble_connected = 0U;
  radio_manager.shadow.ble_advertising = 0U;
  radio_manager.shadow.ble_advertising_evidence = WIFI_BLE_ADV_UNKNOWN;
  radio_manager.work.ble_connect_pending = 0U;
  radio_manager.shadow.ble_connection_handle = 0xFFU;
  radio_manager.shadow.ble_cli_tx_subscribed = 0U;
  radio_manager.shadow.ble_debug_tx_subscribed = 0U;
  radio_manager.shadow.ble_tof_image_subscribed = 0U;
  TOF_App_ReleaseStream(TOF_STREAM_BLE);
  radio_manager.shadow.ble_mtu = 23U;
  radio_manager.work.ble_restart_advertising_pending = 1U;
  radio_manager.work.ble_stream_flush_pending = 1U;
  radio_manager.work.ble_advertising_retry_count = 0U;
  radio_manager.work.ble_advertising_retry_due_tick = 0U;
  (void)tx_interrupt_control(posture);
}

static UINT ble_create_pointer_queue(TX_QUEUE *queue, CHAR *name,
                                     ULONG *storage, ULONG slot_count)
{
  return tx_queue_create(queue, name, TX_1_ULONG, storage,
                         slot_count * (ULONG)sizeof(ULONG));
}

static UINT ble_stream_initialize(void)
{
  VOID *memory = TX_NULL;
  VOID *image_memory = TX_NULL;
  ULONG available = 0U;
  ULONG fragments = 0U;
  void *slot;

  radio_manager.queues.ble_radio_pool = MX_RadioBytePool_Get();
  if ((radio_manager.queues.ble_radio_pool == NULL) ||
      (tx_byte_allocate(radio_manager.queues.ble_radio_pool, &memory,
                        (ULONG)sizeof(WifiBle_StreamContext_t),
                        TX_NO_WAIT) != TX_SUCCESS))
  {
    return TX_POOL_ERROR;
  }

  radio_manager.queues.ble_stream_context = (WifiBle_StreamContext_t *)memory;
  (void)memset(radio_manager.queues.ble_stream_context, 0, sizeof(*radio_manager.queues.ble_stream_context));

  if (tx_byte_allocate(radio_manager.queues.ble_radio_pool, &image_memory,
                       (ULONG)sizeof(WifiBle_TofImageContext_t),
                       TX_NO_WAIT) != TX_SUCCESS)
  {
    (void)tx_byte_release(radio_manager.queues.ble_stream_context);
    radio_manager.queues.ble_stream_context = NULL;
    return TX_POOL_ERROR;
  }
  radio_manager.queues.ble_tof_image_context = (WifiBle_TofImageContext_t *)image_memory;
  (void)memset(radio_manager.queues.ble_tof_image_context, 0, sizeof(*radio_manager.queues.ble_tof_image_context));

  if ((ble_create_pointer_queue(&radio_manager.queues.ble_stream_context->cli_rx_free,
                                "BLE CLI RX free",
                                radio_manager.queues.ble_stream_context->cli_rx_free_storage,
                                BLE_CLI_RX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&radio_manager.queues.ble_stream_context->cli_rx_ready,
                                "BLE CLI RX ready",
                                radio_manager.queues.ble_stream_context->cli_rx_ready_storage,
                                BLE_CLI_RX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&radio_manager.queues.ble_stream_context->debug_rx_free,
                                "BLE debug RX free",
                                radio_manager.queues.ble_stream_context->debug_rx_free_storage,
                                BLE_DEBUG_RX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&radio_manager.queues.ble_stream_context->debug_rx_ready,
                                "BLE debug RX ready",
                                radio_manager.queues.ble_stream_context->debug_rx_ready_storage,
                                BLE_DEBUG_RX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&radio_manager.queues.ble_stream_context->cli_tx_free,
                                "BLE CLI TX free",
                                radio_manager.queues.ble_stream_context->cli_tx_free_storage,
                                BLE_CLI_TX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&radio_manager.queues.ble_stream_context->cli_tx_ready,
                                "BLE CLI TX ready",
                                radio_manager.queues.ble_stream_context->cli_tx_ready_storage,
                                BLE_CLI_TX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&radio_manager.queues.ble_stream_context->debug_tx_free,
                                "BLE debug TX free",
                                radio_manager.queues.ble_stream_context->debug_tx_free_storage,
                                BLE_DEBUG_TX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&radio_manager.queues.ble_stream_context->debug_tx_ready,
                                "BLE debug TX ready",
                                radio_manager.queues.ble_stream_context->debug_tx_ready_storage,
                                BLE_DEBUG_TX_SLOT_COUNT) != TX_SUCCESS))
  {
    return TX_QUEUE_ERROR;
  }

  for (uint32_t i = 0U; i < BLE_CLI_RX_SLOT_COUNT; ++i)
  {
    slot = &radio_manager.queues.ble_stream_context->cli_rx_slots[i];
    if (tx_queue_send(&radio_manager.queues.ble_stream_context->cli_rx_free, &slot,
                      TX_NO_WAIT) != TX_SUCCESS)
    {
      return TX_QUEUE_ERROR;
    }
  }
  for (uint32_t i = 0U; i < BLE_DEBUG_RX_SLOT_COUNT; ++i)
  {
    slot = &radio_manager.queues.ble_stream_context->debug_rx_slots[i];
    if (tx_queue_send(&radio_manager.queues.ble_stream_context->debug_rx_free, &slot,
                      TX_NO_WAIT) != TX_SUCCESS)
    {
      return TX_QUEUE_ERROR;
    }
  }
  for (uint32_t i = 0U; i < BLE_CLI_TX_SLOT_COUNT; ++i)
  {
    slot = &radio_manager.queues.ble_stream_context->cli_tx_slots[i];
    if (tx_queue_send(&radio_manager.queues.ble_stream_context->cli_tx_free, &slot,
                      TX_NO_WAIT) != TX_SUCCESS)
    {
      return TX_QUEUE_ERROR;
    }
  }
  for (uint32_t i = 0U; i < BLE_DEBUG_TX_SLOT_COUNT; ++i)
  {
    slot = &radio_manager.queues.ble_stream_context->debug_tx_slots[i];
    if (tx_queue_send(&radio_manager.queues.ble_stream_context->debug_tx_free, &slot,
                      TX_NO_WAIT) != TX_SUCCESS)
    {
      return TX_QUEUE_ERROR;
    }
  }

  radio_manager.shadow.ble_transport_ready = 1U;
  if (tx_byte_pool_info_get(radio_manager.queues.ble_radio_pool, TX_NULL, &available, &fragments,
                            TX_NULL, TX_NULL, TX_NULL) == TX_SUCCESS)
  {
    LogInfo("ST67W6X BLE streams: %lu-byte queues + %lu-byte ToF frame, radio pool %lu bytes free in %lu fragments.\r\n",
            (unsigned long)sizeof(*radio_manager.queues.ble_stream_context),
            (unsigned long)sizeof(*radio_manager.queues.ble_tof_image_context),
            (unsigned long)available, (unsigned long)fragments);
  }
  return TX_SUCCESS;
}

static void ble_stream_enqueue_rx(WifiBle_Stream_t stream,
                                  const uint8_t *data, uint32_t length)
{
  TX_QUEUE *free_queue;
  TX_QUEUE *ready_queue;
  WifiBle_RxSlot_t *slot = NULL;
  UINT posture;

  if ((radio_manager.queues.ble_stream_context == NULL) || (data == NULL) ||
      (stream >= WIFI_BLE_STREAM_COUNT) ||
      (length > BLE_RX_SLOT_PAYLOAD_SIZE))
  {
    radio_manager.counters.ble_rx_discarded_bytes += length;
    return;
  }

  free_queue = (stream == WIFI_BLE_STREAM_CLI) ?
               &radio_manager.queues.ble_stream_context->cli_rx_free :
               &radio_manager.queues.ble_stream_context->debug_rx_free;
  ready_queue = (stream == WIFI_BLE_STREAM_CLI) ?
                &radio_manager.queues.ble_stream_context->cli_rx_ready :
                &radio_manager.queues.ble_stream_context->debug_rx_ready;

  if (tx_queue_receive(free_queue, &slot, TX_NO_WAIT) != TX_SUCCESS)
  {
    posture = tx_interrupt_control(TX_INT_DISABLE);
    radio_manager.counters.ble_rx_discarded_bytes += length;
    radio_manager.queues.ble_stream_context->stats[stream].rx_dropped_events++;
    radio_manager.queues.ble_stream_context->stats[stream].rx_dropped_bytes += length;
    (void)tx_interrupt_control(posture);
    return;
  }

  slot->generation = radio_manager.shadow.ble_session_generation;
  slot->length = (uint16_t)length;
  (void)memcpy(slot->data, data, length);
  if (tx_queue_send(ready_queue, &slot, TX_NO_WAIT) != TX_SUCCESS)
  {
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    posture = tx_interrupt_control(TX_INT_DISABLE);
    radio_manager.counters.ble_rx_discarded_bytes += length;
    radio_manager.queues.ble_stream_context->stats[stream].rx_dropped_events++;
    radio_manager.queues.ble_stream_context->stats[stream].rx_dropped_bytes += length;
    (void)tx_interrupt_control(posture);
    return;
  }

  posture = tx_interrupt_control(TX_INT_DISABLE);
  radio_manager.queues.ble_stream_context->stats[stream].rx_events++;
  radio_manager.queues.ble_stream_context->stats[stream].rx_bytes += length;
  radio_manager.queues.ble_stream_context->stats[stream].rx_queued++;
  if (radio_manager.queues.ble_stream_context->stats[stream].rx_queued >
      radio_manager.queues.ble_stream_context->stats[stream].rx_high_water)
  {
    radio_manager.queues.ble_stream_context->stats[stream].rx_high_water =
        radio_manager.queues.ble_stream_context->stats[stream].rx_queued;
  }
  (void)tx_interrupt_control(posture);
  if (stream == WIFI_BLE_STREAM_CLI)
  {
    Debug_UART_NcpTracePing("BLE RX queued", data, length);
  }
}

static uint32_t ble_att_payload_size(void)
{
  /* A negotiated MTU change must not alter an already announced raw length. */
  if ((radio_manager.work.notify_source != 0U) && (radio_manager.work.notify_source != 4U))
    return radio_manager.work.notify_length;
  uint32_t payload = (radio_manager.shadow.ble_mtu > 3U) ? (radio_manager.shadow.ble_mtu - 3U) : 20U;
  if (payload > W6X_BLE_MAX_NOTIF_IND_DATA_LENGTH)
  {
    payload = W6X_BLE_MAX_NOTIF_IND_DATA_LENGTH;
  }
  return payload;
}

static void ble_tx_contention_note(WifiBle_TxContentionStatus_t *stats,
                                   uint32_t *started_at, W6X_Status_t result)
{
  uint32_t now = (uint32_t)tx_time_get();
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);

  if (stats->current_streak == 0U)
  {
    *started_at = now;
  }
  if (result == W6X_STATUS_BUSY)
  {
    stats->busy_count++;
  }
  else
  {
    stats->timeout_count++;
  }
  if (stats->current_streak != UINT32_MAX)
  {
    stats->current_streak++;
  }
  if (stats->current_streak > stats->peak_streak)
  {
    stats->peak_streak = stats->current_streak;
  }
  stats->current_duration_ticks = now - *started_at;
  if (stats->current_duration_ticks > stats->peak_duration_ticks)
  {
    stats->peak_duration_ticks = stats->current_duration_ticks;
  }
  (void)tx_interrupt_control(posture);
}

static void ble_tx_contention_finish(WifiBle_TxContentionStatus_t *stats,
                                     uint32_t *started_at, uint32_t recovered)
{
  uint32_t now = (uint32_t)tx_time_get();
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);

  if (stats->current_streak != 0U)
  {
    uint32_t duration = now - *started_at;
    if (duration > stats->peak_duration_ticks)
    {
      stats->peak_duration_ticks = duration;
    }
    if (recovered != 0U)
    {
      stats->recoveries++;
    }
    stats->current_streak = 0U;
    stats->current_duration_ticks = 0U;
  }
  (void)tx_interrupt_control(posture);
}

/* A single source owns the asynchronous driver transaction. Source storage
 * and offsets remain in their existing slots/snapshot; no packet copy/queue.
 * An image packet is reconstructed on the stack for each poll, then copied by
 * the bus before Poll returns. Driver never borrows that stack pointer. */
static W6X_Status_t ble_notify_fragment(uint32_t source, uint8_t service,
                                        uint8_t characteristic, const void *data,
                                        uint32_t length, uint32_t *sent)
{
  *sent = 0U;
  if ((radio_manager.work.notify_source != 0U) &&
      (radio_manager.work.notify_source != source)) return W6X_STATUS_BUSY;
  if (radio_manager.work.notify_source == 0U)
  {
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    if (radio_manager.work.wifi_connect_call_active != 0U) return W6X_STATUS_BUSY;
#endif
    W6X_Status_t admitted = W6X_Ble_ServerNotifyBegin(
        (uint8_t)radio_manager.shadow.ble_connection_handle, service, characteristic,
        length, BLE_NOTIFY_TIMEOUT_MS);
    if (admitted != W6X_STATUS_OK) return admitted;
    radio_manager.work.notify_source = source;
    radio_manager.work.notify_generation = radio_manager.shadow.ble_session_generation;
    radio_manager.work.notify_length = length;
  }
  W6X_Status_t result = W6X_Ble_ServerNotifyPoll(data, length, sent);
  if (result != W6X_STATUS_BUSY) radio_manager.work.notify_source = 0U;
  return result;
}

static void ble_notification_wake(void)
{
  if (radio_control_events_ready != 0U)
    (void)tx_event_flags_set(&radio_control_events, RADIO_NOTIFICATION_WAKE_FLAG, TX_OR);
}

static void ble_notify_retire_stale(void)
{
  uint32_t source = radio_manager.work.notify_source;
  if (source == 0U) return;
  uint32_t subscribed = (source == 1U) ? radio_manager.shadow.ble_cli_tx_subscribed :
      (source == 2U) ? radio_manager.shadow.ble_debug_tx_subscribed :
      radio_manager.shadow.ble_tof_image_subscribed;
  if ((source != 4U) && ((radio_manager.shadow.ble_connected == 0U) ||
      (radio_manager.work.notify_generation != radio_manager.shadow.ble_session_generation) ||
      (subscribed == 0U) || ((source == 3U) &&
       (TOF_App_GetStreamDestination() != TOF_STREAM_BLE))))
  {
    /* Cancel before old slots are returned. A fully queued payload retains
     * protocol ownership but no source pointers, and its result is discarded. */
    radio_manager.work.notify_source =
        (W6X_Ble_ServerNotifyCancel() == W6X_STATUS_BUSY) ? 4U : 0U;
  }
  if (radio_manager.work.notify_source == 4U)
  {
    uint32_t ignored;
    if (W6X_Ble_ServerNotifyPoll(NULL, 0U, &ignored) != W6X_STATUS_BUSY)
      radio_manager.work.notify_source = 0U;
  }
}

static void ble_stream_process_tx(WifiBle_Stream_t stream)
{
  TX_QUEUE *free_queue;
  TX_QUEUE *ready_queue;
  void *slot;
  uint8_t *data;
  uint16_t *length;
  uint16_t *offset;
  uint8_t *retries;
  uint32_t generation;
  uint32_t fragment;
  uint32_t sent = 0U;
  uint32_t subscribed;
  W6X_Status_t result;
  UINT posture;

  if ((radio_manager.queues.ble_stream_context == NULL) || (stream >= WIFI_BLE_STREAM_COUNT))
  {
    return;
  }

  subscribed = (stream == WIFI_BLE_STREAM_CLI) ?
               radio_manager.shadow.ble_cli_tx_subscribed : radio_manager.shadow.ble_debug_tx_subscribed;
  if ((radio_manager.shadow.ble_connected == 0U) || (subscribed == 0U))
  {
    ble_stream_drop_tx(stream);
    return;
  }

  free_queue = (stream == WIFI_BLE_STREAM_CLI) ?
               &radio_manager.queues.ble_stream_context->cli_tx_free :
               &radio_manager.queues.ble_stream_context->debug_tx_free;
  ready_queue = (stream == WIFI_BLE_STREAM_CLI) ?
                &radio_manager.queues.ble_stream_context->cli_tx_ready :
                &radio_manager.queues.ble_stream_context->debug_tx_ready;
  slot = radio_manager.queues.ble_stream_context->active_tx[stream];
  if (slot == NULL)
  {
    if (tx_queue_receive(ready_queue, &slot, TX_NO_WAIT) != TX_SUCCESS)
    {
      return;
    }
    radio_manager.queues.ble_stream_context->active_tx[stream] = slot;
  }

  if (stream == WIFI_BLE_STREAM_CLI)
  {
    WifiBle_CliTxSlot_t *tx_slot = (WifiBle_CliTxSlot_t *)slot;
    generation = tx_slot->generation;
    length = &tx_slot->length;
    offset = &tx_slot->offset;
    retries = &tx_slot->retries;
    data = tx_slot->data;
  }
  else
  {
    WifiBle_DebugTxSlot_t *tx_slot = (WifiBle_DebugTxSlot_t *)slot;
    generation = tx_slot->generation;
    length = &tx_slot->length;
    offset = &tx_slot->offset;
    retries = &tx_slot->retries;
    data = tx_slot->data;
  }

  if (generation != radio_manager.shadow.ble_session_generation)
  {
    ble_tx_contention_finish(&radio_manager.queues.ble_stream_context->stats[stream].contention,
                             &radio_manager.queues.ble_stream_context->contention_start_tick[stream], 0U);
    radio_manager.queues.ble_stream_context->active_tx[stream] = NULL;
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    posture = tx_interrupt_control(TX_INT_DISABLE);
    if (radio_manager.queues.ble_stream_context->stats[stream].tx_queued != 0U)
    {
      radio_manager.queues.ble_stream_context->stats[stream].tx_queued--;
    }
    radio_manager.queues.ble_stream_context->stats[stream].stale_drops++;
    (void)tx_interrupt_control(posture);
    return;
  }

  fragment = (uint32_t)(*length - *offset);
  if (fragment > ble_att_payload_size())
  {
    fragment = ble_att_payload_size();
  }
  result = ble_notify_fragment((uint32_t)stream + 1U,
                                (stream == WIFI_BLE_STREAM_CLI) ?
                                BLE_CLI_SERVICE_INDEX : BLE_DEBUG_SERVICE_INDEX,
                                BLE_TX_CHAR_INDEX, &data[*offset], fragment,
                                &sent);
  if ((result == W6X_STATUS_BUSY) || (result == W6X_STATUS_TIMEOUT))
  {
    ble_tx_contention_note(&radio_manager.queues.ble_stream_context->stats[stream].contention,
                           &radio_manager.queues.ble_stream_context->contention_start_tick[stream], result);
    return; /* Retain the active slot and offset for the next manager cycle. */
  }
  if ((result == W6X_STATUS_OK) && (sent != 0U))
  {
    ble_tx_contention_finish(&radio_manager.queues.ble_stream_context->stats[stream].contention,
                             &radio_manager.queues.ble_stream_context->contention_start_tick[stream], 1U);
    if (sent > fragment)
    {
      sent = fragment;
    }
    *offset = (uint16_t)(*offset + sent);
    *retries = 0U;
    posture = tx_interrupt_control(TX_INT_DISABLE);
    radio_manager.queues.ble_stream_context->stats[stream].tx_sent_bytes += sent;
    (void)tx_interrupt_control(posture);
    if (*offset >= *length)
    {
      radio_manager.queues.ble_stream_context->active_tx[stream] = NULL;
      (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
      posture = tx_interrupt_control(TX_INT_DISABLE);
      if (radio_manager.queues.ble_stream_context->stats[stream].tx_queued != 0U)
      {
        radio_manager.queues.ble_stream_context->stats[stream].tx_queued--;
      }
      (void)tx_interrupt_control(posture);
    }
    return;
  }

  ble_tx_contention_finish(&radio_manager.queues.ble_stream_context->stats[stream].contention,
                           &radio_manager.queues.ble_stream_context->contention_start_tick[stream], 0U);
  (*retries)++;
  posture = tx_interrupt_control(TX_INT_DISABLE);
  radio_manager.queues.ble_stream_context->stats[stream].tx_retries++;
  radio_manager.queues.ble_stream_context->stats[stream].tx_errors++;
  (void)tx_interrupt_control(posture);
  if (*retries >= BLE_NOTIFY_MAX_ATTEMPTS)
  {
    uint32_t dropped = (uint32_t)(*length - *offset);
    radio_manager.queues.ble_stream_context->active_tx[stream] = NULL;
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    posture = tx_interrupt_control(TX_INT_DISABLE);
    if (radio_manager.queues.ble_stream_context->stats[stream].tx_queued != 0U)
    {
      radio_manager.queues.ble_stream_context->stats[stream].tx_queued--;
    }
    radio_manager.queues.ble_stream_context->stats[stream].tx_dropped_messages++;
    radio_manager.queues.ble_stream_context->stats[stream].tx_dropped_bytes += dropped;
    (void)tx_interrupt_control(posture);
  }
}

static void __attribute__((optimize("Os"))) ble_tof_image_drop_active(void)
{
  UINT posture;

  if (radio_manager.queues.ble_tof_image_context == NULL)
  {
    return;
  }
  ble_tx_contention_finish(&radio_manager.queues.ble_tof_image_context->stats.contention,
                           &radio_manager.queues.ble_tof_image_context->contention_start_tick, 0U);
  posture = tx_interrupt_control(TX_INT_DISABLE);
  if ((radio_manager.queues.ble_tof_image_context->state == BLE_TOF_IMAGE_READY) ||
      (radio_manager.queues.ble_tof_image_context->state == BLE_TOF_IMAGE_ACTIVE))
  {
    radio_manager.queues.ble_tof_image_context->state =
        (CloudRelay_IsTofFramePending(radio_manager.queues.ble_tof_image_context->frame_id) != 0U) ?
            BLE_TOF_IMAGE_WAIT_CLOUD : BLE_TOF_IMAGE_FREE;
    radio_manager.queues.ble_tof_image_context->stats.frames_aborted++;
  }
  (void)tx_interrupt_control(posture);
}

static void __attribute__((optimize("Os"))) ble_tof_image_process_tx(void)
{
  uint8_t packet[W6X_BLE_MAX_NOTIF_IND_DATA_LENGTH];
  uint32_t att_payload;
  uint32_t chunk_length;
  uint32_t packet_length;
  uint32_t sent = 0U;
  uint8_t flags = 0U;
  W6X_Status_t result;
  UINT posture;

  if (radio_manager.queues.ble_tof_image_context == NULL)
  {
    return;
  }
  if (radio_manager.queues.ble_tof_image_context->state == BLE_TOF_IMAGE_WAIT_CLOUD)
  {
    if (CloudRelay_IsTofFramePending(radio_manager.queues.ble_tof_image_context->frame_id) == 0U)
    {
      radio_manager.queues.ble_tof_image_context->state = BLE_TOF_IMAGE_FREE;
    }
    return;
  }
  if ((radio_manager.shadow.ble_connected == 0U) ||
      (radio_manager.shadow.ble_tof_image_subscribed == 0U) ||
      (TOF_App_GetStreamDestination() != TOF_STREAM_BLE))
  {
    ble_tof_image_drop_active();
    return;
  }
  if (radio_manager.queues.ble_tof_image_context->state == BLE_TOF_IMAGE_READY)
  {
    radio_manager.queues.ble_tof_image_context->state = BLE_TOF_IMAGE_ACTIVE;
  }
  if (radio_manager.queues.ble_tof_image_context->state != BLE_TOF_IMAGE_ACTIVE)
  {
    return;
  }
  if (radio_manager.queues.ble_tof_image_context->generation != radio_manager.shadow.ble_session_generation)
  {
    ble_tof_image_drop_active();
    return;
  }

  att_payload = ble_att_payload_size();
  if (att_payload <= WIFI_BLE_TOF_FRAGMENT_HEADER_SIZE)
  {
    /* Wait for the negotiated MTU.  A 23-byte ATT MTU has no room for the
     * self-describing header plus image data. */
    return;
  }
  chunk_length = (uint32_t)(radio_manager.queues.ble_tof_image_context->payload_length -
                            radio_manager.queues.ble_tof_image_context->offset);
  if (chunk_length > (att_payload - WIFI_BLE_TOF_FRAGMENT_HEADER_SIZE))
  {
    chunk_length = att_payload - WIFI_BLE_TOF_FRAGMENT_HEADER_SIZE;
  }
  if (radio_manager.queues.ble_tof_image_context->offset == 0U)
  {
    flags |= WIFI_BLE_TOF_FRAGMENT_FLAG_START;
  }
  if (((uint32_t)radio_manager.queues.ble_tof_image_context->offset + chunk_length) >=
      radio_manager.queues.ble_tof_image_context->payload_length)
  {
    flags |= WIFI_BLE_TOF_FRAGMENT_FLAG_END;
  }

  ble_write_u16(&packet[0], WIFI_BLE_TOF_FRAGMENT_MAGIC);
  packet[2] = WIFI_BLE_TOF_FRAGMENT_VERSION;
  packet[3] = flags;
  ble_write_u32(&packet[4], radio_manager.queues.ble_tof_image_context->frame_id);
  ble_write_u16(&packet[8], radio_manager.queues.ble_tof_image_context->offset);
  ble_write_u16(&packet[10], radio_manager.queues.ble_tof_image_context->payload_length);
  packet[12] = radio_manager.queues.ble_tof_image_context->width;
  packet[13] = radio_manager.queues.ble_tof_image_context->height;
  packet[14] = radio_manager.queues.ble_tof_image_context->channel_id;
  packet[15] = WIFI_BLE_TOF_PIXEL_FORMAT_FLOAT32_LE;
  ble_write_u32(&packet[16], radio_manager.queues.ble_tof_image_context->payload_crc32);
  (void)memcpy(&packet[WIFI_BLE_TOF_FRAGMENT_HEADER_SIZE],
               &radio_manager.queues.ble_tof_image_context->payload[radio_manager.queues.ble_tof_image_context->offset],
               chunk_length);
  packet_length = WIFI_BLE_TOF_FRAGMENT_HEADER_SIZE + chunk_length;

  result = ble_notify_fragment(3U,
                                BLE_CLI_SERVICE_INDEX,
                                BLE_TOF_IMAGE_CHAR_INDEX,
                                packet, packet_length, &sent);
  if ((result == W6X_STATUS_BUSY) || (result == W6X_STATUS_TIMEOUT))
  {
    ble_tx_contention_note(&radio_manager.queues.ble_tof_image_context->stats.contention,
                           &radio_manager.queues.ble_tof_image_context->contention_start_tick, result);
    return; /* Preserve the frame and offset until the next manager cycle. */
  }
  if ((result == W6X_STATUS_OK) && (sent == packet_length))
  {
    ble_tx_contention_finish(&radio_manager.queues.ble_tof_image_context->stats.contention,
                             &radio_manager.queues.ble_tof_image_context->contention_start_tick, 1U);
    radio_manager.queues.ble_tof_image_context->offset =
        (uint16_t)(radio_manager.queues.ble_tof_image_context->offset + chunk_length);
    radio_manager.queues.ble_tof_image_context->retries = 0U;
    posture = tx_interrupt_control(TX_INT_DISABLE);
    radio_manager.queues.ble_tof_image_context->stats.fragments_sent++;
    radio_manager.queues.ble_tof_image_context->stats.bytes_sent += chunk_length;
    if (radio_manager.queues.ble_tof_image_context->offset >=
        radio_manager.queues.ble_tof_image_context->payload_length)
    {
      radio_manager.queues.ble_tof_image_context->stats.frames_sent++;
      radio_manager.queues.ble_tof_image_context->stats.last_sent_frame =
          radio_manager.queues.ble_tof_image_context->frame_id;
      radio_manager.queues.ble_tof_image_context->state =
          (CloudRelay_IsTofFramePending(radio_manager.queues.ble_tof_image_context->frame_id) != 0U) ?
              BLE_TOF_IMAGE_WAIT_CLOUD : BLE_TOF_IMAGE_FREE;
    }
    (void)tx_interrupt_control(posture);
    return;
  }

  ble_tx_contention_finish(&radio_manager.queues.ble_tof_image_context->stats.contention,
                           &radio_manager.queues.ble_tof_image_context->contention_start_tick, 0U);
  radio_manager.queues.ble_tof_image_context->retries++;
  posture = tx_interrupt_control(TX_INT_DISABLE);
  radio_manager.queues.ble_tof_image_context->stats.retries++;
  radio_manager.queues.ble_tof_image_context->stats.errors++;
  if (radio_manager.queues.ble_tof_image_context->retries >= BLE_NOTIFY_MAX_ATTEMPTS)
  {
    radio_manager.queues.ble_tof_image_context->stats.frames_aborted++;
    radio_manager.queues.ble_tof_image_context->state =
        (CloudRelay_IsTofFramePending(radio_manager.queues.ble_tof_image_context->frame_id) != 0U) ?
            BLE_TOF_IMAGE_WAIT_CLOUD : BLE_TOF_IMAGE_FREE;
  }
  (void)tx_interrupt_control(posture);
}

static uint32_t __attribute__((optimize("Os")))
ble_crc32(const void *data, size_t length)
{
  const uint8_t *bytes = (const uint8_t *)data;
  uint32_t crc = 0xFFFFFFFFUL;

  while (length-- != 0U)
  {
    crc ^= *bytes++;
    for (uint32_t bit = 0U; bit < 8U; ++bit)
    {
      uint32_t mask = (uint32_t)(-(int32_t)(crc & 1UL));
      crc = (crc >> 1U) ^ (0xEDB88320UL & mask);
    }
  }
  return ~crc;
}

static void __attribute__((optimize("Os")))
ble_write_u16(uint8_t *destination, uint16_t value)
{
  destination[0] = (uint8_t)value;
  destination[1] = (uint8_t)(value >> 8U);
}

static void __attribute__((optimize("Os")))
ble_write_u32(uint8_t *destination, uint32_t value)
{
  destination[0] = (uint8_t)value;
  destination[1] = (uint8_t)(value >> 8U);
  destination[2] = (uint8_t)(value >> 16U);
  destination[3] = (uint8_t)(value >> 24U);
}

static void ble_purge_queue(TX_QUEUE *ready_queue, TX_QUEUE *free_queue,
                            WifiBle_Stream_t stream, uint32_t is_tx)
{
  ULONG count = 0U;
  void *slot;

  (void)tx_queue_info_get(ready_queue, TX_NULL, &count, TX_NULL, TX_NULL,
                          TX_NULL, TX_NULL);
  for (ULONG i = 0U; i < count; ++i)
  {
    uint32_t generation = 0U;
    if (tx_queue_receive(ready_queue, &slot, TX_NO_WAIT) != TX_SUCCESS)
    {
      break;
    }
    (void)memcpy(&generation, slot, sizeof(generation));
    if (generation == radio_manager.shadow.ble_session_generation)
    {
      (void)tx_queue_send(ready_queue, &slot, TX_NO_WAIT);
    }
    else
    {
      UINT posture;
      (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
      posture = tx_interrupt_control(TX_INT_DISABLE);
      if (is_tx != 0U)
      {
        if (radio_manager.queues.ble_stream_context->stats[stream].tx_queued != 0U)
        {
          radio_manager.queues.ble_stream_context->stats[stream].tx_queued--;
        }
      }
      else if (radio_manager.queues.ble_stream_context->stats[stream].rx_queued != 0U)
      {
        radio_manager.queues.ble_stream_context->stats[stream].rx_queued--;
      }
      radio_manager.queues.ble_stream_context->stats[stream].stale_drops++;
      (void)tx_interrupt_control(posture);
    }
  }
}

static void ble_stream_purge_stale(void)
{
  if (radio_manager.queues.ble_stream_context == NULL)
  {
    return;
  }

  ble_purge_queue(&radio_manager.queues.ble_stream_context->cli_rx_ready,
                  &radio_manager.queues.ble_stream_context->cli_rx_free,
                  WIFI_BLE_STREAM_CLI, 0U);
  ble_purge_queue(&radio_manager.queues.ble_stream_context->debug_rx_ready,
                  &radio_manager.queues.ble_stream_context->debug_rx_free,
                  WIFI_BLE_STREAM_DEBUG, 0U);
  ble_purge_queue(&radio_manager.queues.ble_stream_context->cli_tx_ready,
                  &radio_manager.queues.ble_stream_context->cli_tx_free,
                  WIFI_BLE_STREAM_CLI, 1U);
  ble_purge_queue(&radio_manager.queues.ble_stream_context->debug_tx_ready,
                  &radio_manager.queues.ble_stream_context->debug_tx_free,
                  WIFI_BLE_STREAM_DEBUG, 1U);

  for (uint32_t i = 0U; i < WIFI_BLE_STREAM_COUNT; ++i)
  {
    void *slot = radio_manager.queues.ble_stream_context->active_tx[i];
    uint32_t generation = 0U;
    if (slot == NULL)
    {
      continue;
    }
    (void)memcpy(&generation, slot, sizeof(generation));
    if (generation != radio_manager.shadow.ble_session_generation)
    {
      TX_QUEUE *free_queue = (i == WIFI_BLE_STREAM_CLI) ?
                             &radio_manager.queues.ble_stream_context->cli_tx_free :
                             &radio_manager.queues.ble_stream_context->debug_tx_free;
      UINT posture;
      ble_tx_contention_finish(&radio_manager.queues.ble_stream_context->stats[i].contention,
                               &radio_manager.queues.ble_stream_context->contention_start_tick[i], 0U);
      radio_manager.queues.ble_stream_context->active_tx[i] = NULL;
      (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
      posture = tx_interrupt_control(TX_INT_DISABLE);
      if (radio_manager.queues.ble_stream_context->stats[i].tx_queued != 0U)
      {
        radio_manager.queues.ble_stream_context->stats[i].tx_queued--;
      }
      radio_manager.queues.ble_stream_context->stats[i].stale_drops++;
      (void)tx_interrupt_control(posture);
    }
  }
}

static void ble_stream_drop_tx(WifiBle_Stream_t stream)
{
  TX_QUEUE *free_queue;
  TX_QUEUE *ready_queue;
  void *slot;
  UINT posture;

  if ((radio_manager.queues.ble_stream_context == NULL) || (stream >= WIFI_BLE_STREAM_COUNT))
  {
    return;
  }
  ble_tx_contention_finish(&radio_manager.queues.ble_stream_context->stats[stream].contention,
                           &radio_manager.queues.ble_stream_context->contention_start_tick[stream], 0U);
  free_queue = (stream == WIFI_BLE_STREAM_CLI) ?
               &radio_manager.queues.ble_stream_context->cli_tx_free :
               &radio_manager.queues.ble_stream_context->debug_tx_free;
  ready_queue = (stream == WIFI_BLE_STREAM_CLI) ?
                &radio_manager.queues.ble_stream_context->cli_tx_ready :
                &radio_manager.queues.ble_stream_context->debug_tx_ready;

  slot = radio_manager.queues.ble_stream_context->active_tx[stream];
  if (slot != NULL)
  {
    uint32_t dropped;
    if (stream == WIFI_BLE_STREAM_CLI)
    {
      WifiBle_CliTxSlot_t *tx_slot = (WifiBle_CliTxSlot_t *)slot;
      dropped = (uint32_t)(tx_slot->length - tx_slot->offset);
    }
    else
    {
      WifiBle_DebugTxSlot_t *tx_slot = (WifiBle_DebugTxSlot_t *)slot;
      dropped = (uint32_t)(tx_slot->length - tx_slot->offset);
    }
    radio_manager.queues.ble_stream_context->active_tx[stream] = NULL;
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    posture = tx_interrupt_control(TX_INT_DISABLE);
    if (radio_manager.queues.ble_stream_context->stats[stream].tx_queued != 0U)
    {
      radio_manager.queues.ble_stream_context->stats[stream].tx_queued--;
    }
    radio_manager.queues.ble_stream_context->stats[stream].tx_dropped_messages++;
    radio_manager.queues.ble_stream_context->stats[stream].tx_dropped_bytes += dropped;
    (void)tx_interrupt_control(posture);
  }
  while (tx_queue_receive(ready_queue, &slot, TX_NO_WAIT) == TX_SUCCESS)
  {
    uint32_t dropped = (stream == WIFI_BLE_STREAM_CLI) ?
        ((WifiBle_CliTxSlot_t *)slot)->length :
        ((WifiBle_DebugTxSlot_t *)slot)->length;
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    posture = tx_interrupt_control(TX_INT_DISABLE);
    if (radio_manager.queues.ble_stream_context->stats[stream].tx_queued != 0U)
    {
      radio_manager.queues.ble_stream_context->stats[stream].tx_queued--;
    }
    radio_manager.queues.ble_stream_context->stats[stream].tx_dropped_messages++;
    radio_manager.queues.ble_stream_context->stats[stream].tx_dropped_bytes += dropped;
    (void)tx_interrupt_control(posture);
  }
}

static uint32_t ble_control_current(const BleControlJob_t *job)
{
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  uint32_t current = job->generation == radio_manager.shadow.ble_session_generation;
  if (job->operation == BLE_CONTROL_ADV)
    current &= job->revision == ble_adv_revision;
  (void)tx_interrupt_control(posture);
  return current;
}

static uint32_t ble_control_submit(BleControlOperation_t operation)
{
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  if (ble_control.state != 0U)
  {
    ble_control.stats.deferred++;
    (void)tx_interrupt_control(posture);
    return 0U;
  }
  BleControlJob_t *job = &ble_control.job;
  memset(job, 0, sizeof(*job));
  job->operation = operation;
  job->generation = radio_manager.shadow.ble_session_generation;
  job->revision = ble_adv_revision;
  job->handle = radio_manager.shadow.ble_connection_handle;
  job->desired = radio_manager.shadow.ble_advertising_desired;
  job->submitted_at = HAL_GetTick();
  job->status = W6X_STATUS_BUSY;
  job->secondary_status = W6X_STATUS_BUSY;
  if (operation == BLE_CONTROL_CONNECT) radio_manager.work.ble_connect_pending = 0U;
  if (operation == BLE_CONTROL_DISCONNECT) radio_manager.work.ble_disconnect_request = 0U;
  ble_control.stats.submitted++;
  ble_control.state = 1U;
  (void)tx_interrupt_control(posture);
  (void)tx_event_flags_set(&radio_control_events, WIFI_CONTROL_WORK_FLAG, TX_OR);
  return 1U;
}

static void ble_control_execute(void)
{
  BleControlJob_t job;
  uint32_t started, elapsed;
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  if (ble_control.state != 1U)
  { (void)tx_interrupt_control(posture); return; }
  job = ble_control.job;
  ble_control.state = 2U;
  started = HAL_GetTick();
  elapsed = started - job.submitted_at;
  if (elapsed > ble_control.stats.max_queue_ms) ble_control.stats.max_queue_ms = elapsed;
  (void)tx_interrupt_control(posture);

  if (ble_control_current(&job) == 0U) job.cancelled = 1U;
  else switch (job.operation)
  {
    case BLE_CONTROL_CONNECT:
      job.status = W6X_Ble_ExchangeMTU(job.handle);
      if (ble_control_current(&job) != 0U)
        job.secondary_status = W6X_Ble_SetConnParam(job.handle, 12U, 24U, 0U, 400U);
      else job.cancelled = 1U;
      break;
    case BLE_CONTROL_DISCONNECT:
      if (job.handle != 0xFFU) job.status = W6X_Ble_Disconnect(job.handle);
      else job.cancelled = 1U;
      break;
    case BLE_CONTROL_ADV:
      job.status = job.desired ? W6X_Ble_AdvStart() : W6X_Ble_AdvStop();
      break;
    case BLE_CONTROL_MODE:
      job.status = W6X_Ble_GetInitMode(&job.mode);
      break;
    case BLE_CONTROL_LINK:
      job.status = W6X_Ble_GetConn(&job.handle, job.address);
      break;
    case BLE_CONTROL_RECOVER:
      job.stage = WIFI_BLE_INIT_STAGE_STACK;
      job.status = W6X_Ble_Init(W6X_BLE_MODE_SERVER,
          radio_manager.queues.ble_receive_buffer,
          sizeof(radio_manager.queues.ble_receive_buffer) - 1U);
      if ((job.status == W6X_STATUS_OK) && (ble_control_current(&job) != 0U))
        job.status = ble_configure_gatt_job(&job, 0U);
      else if (ble_control_current(&job) == 0U) job.cancelled = 1U;
      break;
    default: job.cancelled = 1U; break;
  }

  posture = tx_interrupt_control(TX_INT_DISABLE);
  elapsed = HAL_GetTick() - started;
  if (elapsed > ble_control.stats.max_call_ms) ble_control.stats.max_call_ms = elapsed;
  ble_control.job = job;
  ble_control.state = 3U;
  (void)tx_interrupt_control(posture);
}

static void ble_control_complete(void)
{
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  if (ble_control.state != 3U)
  { (void)tx_interrupt_control(posture); return; }
  BleControlJob_t job = ble_control.job;
  ble_control.state = 0U;
  ble_control.stats.completed++;
  ble_control.stats.last_status = job.status;
  if ((job.cancelled != 0U) || (ble_control_current(&job) == 0U))
  {
    ble_control.stats.stale++;
    (void)tx_interrupt_control(posture);
    return;
  }
  /* BUSY means the command did not gain admission; preserve confirmed state
   * and retry intent. The vendor currently uses it for immediate admission. */
  if (job.status == W6X_STATUS_BUSY)
  {
    ble_control.stats.deferred++;
    if (job.operation == BLE_CONTROL_CONNECT) radio_manager.work.ble_connect_pending = 1U;
    if (job.operation == BLE_CONTROL_DISCONNECT) radio_manager.work.ble_disconnect_request = 1U;
    (void)tx_interrupt_control(posture);
    return;
  }
  radio_manager.shadow.ble_last_status = job.status;
  switch (job.operation)
  {
    case BLE_CONTROL_CONNECT:
      /* Failed MTU exchange leaves default/current negotiated MTU valid. */
      if (job.secondary_status == W6X_STATUS_BUSY) radio_manager.work.ble_connect_pending = 1U;
      break;
    case BLE_CONTROL_DISCONNECT:
      if (job.status != W6X_STATUS_OK) radio_manager.counters.faults.disconnect_failures++;
      break;
    case BLE_CONTROL_ADV:
      if (job.status == W6X_STATUS_OK)
      {
        radio_manager.shadow.ble_advertising = job.desired;
        radio_manager.shadow.ble_advertising_evidence = WIFI_BLE_ADV_COMMAND_ACK;
        radio_manager.work.ble_advertising_retry_count = 0U;
        radio_manager.work.ble_advertising_retry_due_tick = 0U;
      }
      else
      {
        radio_manager.shadow.ble_advertising_evidence = WIFI_BLE_ADV_UNKNOWN;
        radio_manager.counters.faults.advertising_failures++;
        radio_manager.work.ble_advertising_retry_count++;
        radio_manager.work.ble_advertising_retry_due_tick = HAL_GetTick() +
            (BLE_ADV_RETRY_BASE_MS << (radio_manager.work.ble_advertising_retry_count - 1U));
        if (radio_manager.work.ble_advertising_retry_count >= BLE_ADV_MAX_ATTEMPTS)
          radio_manager.counters.faults.advertising_retries_exhausted++;
      }
      break;
    case BLE_CONTROL_MODE:
    case BLE_CONTROL_LINK:
      /* Apply below after releasing interrupts; function takes its own lock. */
      break;
    case BLE_CONTROL_RECOVER:
      radio_manager.shadow.ble_init_stage = job.stage;
      if (job.status == W6X_STATUS_OK)
      {
        ble_apply_gatt(&job);
        radio_manager.work.ble_recovery_pending = 0U;
        radio_manager.work.ble_recovery_retry_count = 0U;
      }
      else
      {
        radio_manager.counters.faults.ble_recovery_failures++;
        radio_manager.work.ble_recovery_retry_count++;
        radio_manager.work.ble_recovery_due_tick = HAL_GetTick() + BLE_RECOVERY_COOLDOWN_MS;
      }
      break;
    default: break;
  }
  (void)tx_interrupt_control(posture);
  if ((job.operation == BLE_CONTROL_MODE) || (job.operation == BLE_CONTROL_LINK)) ble_apply_probe(&job);
  if ((job.status != W6X_STATUS_OK) ||
      ((job.operation == BLE_CONTROL_CONNECT) && (job.secondary_status != W6X_STATUS_OK)))
    LogWarn("ST67W6X BLE control op=%u generation=%lu result=%ld secondary=%ld.\r\n",
            (unsigned)job.operation, (unsigned long)job.generation,
            (long)job.status, (long)job.secondary_status);
  if ((job.operation == BLE_CONTROL_RECOVER) && (job.status == W6X_STATUS_OK))
    LogInfo("ST67W6X BLE-only state recovery completed; advertising follows desired state.\r\n");
}

static W6X_Status_t ble_configure_gatt_job(BleControlJob_t *job, uint32_t startup)
{
  W6X_Status_t status;
  uint8_t *address = job->address;
  char *device_name = job->name;

  job->stage = WIFI_BLE_INIT_STAGE_ADDRESS;
  if ((startup == 0U) && (ble_control_current(job) == 0U))
  { job->cancelled = 1U; return W6X_STATUS_BUSY; }
  status = W6X_Ble_GetBDAddress(address);
  job->status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE address read failed: %" PRIi32 "\r\n", status);
    return status;
  }

  (void)snprintf(device_name, sizeof(job->name), "N6-MAINT-%02X%02X",
                 address[4], address[5]);
  job->stage = WIFI_BLE_INIT_STAGE_DEVICE_NAME;
  if ((startup == 0U) && (ble_control_current(job) == 0U))
  { job->cancelled = 1U; return W6X_STATUS_BUSY; }
  status = W6X_Ble_SetDeviceName(device_name);
  job->status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE device-name setup failed: %" PRIi32 "\r\n", status);
    return status;
  }

  job->stage = WIFI_BLE_INIT_STAGE_TX_POWER;
  if ((startup == 0U) && (ble_control_current(job) == 0U))
  { job->cancelled = 1U; return W6X_STATUS_BUSY; }
  status = W6X_Ble_SetTxPower(0U);
  job->status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE TX-power setup failed: %" PRIi32 "\r\n", status);
    return status;
  }
  job->stage = WIFI_BLE_INIT_STAGE_ADV_DATA;
  if ((startup == 0U) && (ble_control_current(job) == 0U))
  { job->cancelled = 1U; return W6X_STATUS_BUSY; }
  status = W6X_Ble_SetAdvData(BLE_ADV_DATA);
  job->status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE advertising-data setup failed: %" PRIi32 "\r\n", status);
    return status;
  }
  job->stage = WIFI_BLE_INIT_STAGE_CLI_SERVICE;
  if ((startup == 0U) && (ble_control_current(job) == 0U))
  { job->cancelled = 1U; return W6X_STATUS_BUSY; }
  status = W6X_Ble_CreateService(BLE_CLI_SERVICE_INDEX,
                                 BLE_CLI_SERVICE_UUID,
                                 W6X_BLE_UUID_TYPE_128);
  job->status = status;
  if (status == W6X_STATUS_OK)
  {
    job->stage = WIFI_BLE_INIT_STAGE_DEBUG_SERVICE;
    if ((startup == 0U) && (ble_control_current(job) == 0U))
    { job->cancelled = 1U; return W6X_STATUS_BUSY; }
    status = W6X_Ble_CreateService(BLE_DEBUG_SERVICE_INDEX,
                                   BLE_DEBUG_SERVICE_UUID,
                                   W6X_BLE_UUID_TYPE_128);
    job->status = status;
  }
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE service creation failed: %" PRIi32 "\r\n", status);
    return status;
  }

  job->stage = WIFI_BLE_INIT_STAGE_CHARACTERISTICS;
  for (size_t i = 0U;
       i < (sizeof(ble_characteristics) / sizeof(ble_characteristics[0]));
       ++i)
  {
    if ((startup == 0U) && (ble_control_current(job) == 0U))
    { job->cancelled = 1U; return W6X_STATUS_BUSY; }
    status = W6X_Ble_CreateCharacteristic(
        ble_characteristics[i].service_index,
        ble_characteristics[i].char_index,
        ble_characteristics[i].uuid,
        W6X_BLE_UUID_TYPE_128,
        ble_characteristics[i].properties,
        ble_characteristics[i].permissions);
    job->status = status;
    if (status != W6X_STATUS_OK)
    {
      LogError("ST67W6X BLE %s characteristic creation failed: %" PRIi32 "\r\n",
               ble_characteristics[i].description, status);
      return status;
    }
  }

  job->stage = WIFI_BLE_INIT_STAGE_REGISTER;
  if ((startup == 0U) && (ble_control_current(job) == 0U))
  { job->cancelled = 1U; return W6X_STATUS_BUSY; }
  status = W6X_Ble_RegisterCharacteristics();
  job->status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE characteristic registration failed: %" PRIi32 "\r\n", status);
    return status;
  }

  /* Development-stage Just Works capability.  This configures GAP I/O
   * capability but does not authorize firmware installation or XMODEM. */
  job->stage = WIFI_BLE_INIT_STAGE_SECURITY;
  if ((startup == 0U) && (ble_control_current(job) == 0U))
  { job->cancelled = 1U; return W6X_STATUS_BUSY; }
  status = W6X_Ble_SetSecurityParam(W6X_BLE_SEC_IO_NO_INPUT_OUTPUT);
  job->status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE security-parameter setup failed: %" PRIi32 "\r\n", status);
    return status;
  }

  job->stage = WIFI_BLE_INIT_STAGE_READY;
  return W6X_STATUS_OK;
}

static void ble_apply_gatt(const BleControlJob_t *job)
{
  memcpy(radio_manager.shadow.ble_device_name, job->name, sizeof(job->name));
  memcpy(radio_manager.shadow.ble_address, job->address, sizeof(job->address));
  radio_manager.shadow.ble_init_stage = job->stage;
  radio_manager.shadow.ble_gatt_ready = 1U;
  radio_manager.shadow.ble_mode_confirmed = 1U;
  radio_manager.shadow.ble_link_confirmed = 1U;
  radio_manager.shadow.ble_advertising_evidence = WIFI_BLE_ADV_UNKNOWN;
  radio_manager.work.ble_advertising_retry_count = 0U;
  radio_manager.work.ble_advertising_retry_due_tick = 0U;
  radio_manager.work.ble_probe_due_tick = HAL_GetTick() + BLE_HEALTH_PROBE_INTERVAL_MS;
}

static W6X_Status_t ble_configure_gatt_server(void)
{
  BleControlJob_t job = {0};
  W6X_Status_t status = ble_configure_gatt_job(&job, 1U);
  radio_manager.shadow.ble_init_stage = job.stage;
  radio_manager.shadow.ble_last_status = status;
  if (status != W6X_STATUS_OK) return status;
  ble_apply_gatt(&job);
  radio_manager.counters.faults.advertising_attempts++;
  status = W6X_Ble_AdvStart();
  radio_manager.shadow.ble_last_status = status;
  if (status != W6X_STATUS_OK)
  { radio_manager.counters.faults.advertising_failures++; return status; }
  radio_manager.shadow.ble_advertising = 1U;
  radio_manager.shadow.ble_advertising_evidence = WIFI_BLE_ADV_COMMAND_ACK;
  LogInfo("ST67W6X BLE: %s, CLI/DEBUG UART and ToF image notifications registered.\r\n", job.name);
  return status;
}

static void ble_process_pending_events(void)
{
  ble_notify_retire_stale();
  ble_control_complete();
  if (radio_manager.work.ble_stream_flush_pending != 0U)
  {
    radio_manager.work.ble_stream_flush_pending = 0U;
    ble_stream_purge_stale();
  }

  if (radio_manager.work.ble_disconnect_request != 0U)
    (void)ble_control_submit(BLE_CONTROL_DISCONNECT);

  if (radio_manager.work.ble_adv_request != BLE_ADV_REQUEST_NONE)
  {
    radio_manager.work.ble_adv_request = BLE_ADV_REQUEST_NONE;
    radio_manager.work.ble_advertising_retry_due_tick = 0U;
  }

  if (radio_manager.work.ble_connect_pending != 0U)
    (void)ble_control_submit(BLE_CONTROL_CONNECT);

  if (radio_manager.work.ble_restart_advertising_pending != 0U)
  {
    radio_manager.work.ble_restart_advertising_pending = 0U;
    radio_manager.work.ble_advertising_retry_due_tick = 0U;
  }

  ble_recover_subsystem(HAL_GetTick());
  ble_reconcile_advertising(HAL_GetTick());

  /* One ATT fragment per stream and manager cycle is the notification-credit
   * window.  It bounds module call time and prevents the image stream from
   * monopolizing CLI/XMODEM while keeping every W6X send in this owner thread. */
  ble_stream_process_tx(WIFI_BLE_STREAM_CLI);
  ble_stream_process_tx(WIFI_BLE_STREAM_DEBUG);
  ble_tof_image_process_tx();
  ble_probe_shadow(HAL_GetTick());
}

static uint32_t ble_tick_due(uint32_t now, uint32_t due)
{
  return (due == 0U) || ((int32_t)(now - due) >= 0) ? 1U : 0U;
}

static void ble_reconcile_advertising(uint32_t now)
{
  uint32_t requested;

  if ((radio_manager.shadow.ble_gatt_ready == 0U) ||
      (radio_manager.work.ble_recovery_pending != 0U) ||
      (radio_manager.shadow.ble_mode_confirmed == 0U) ||
      (radio_manager.shadow.ble_link_confirmed == 0U))
  {
    return;
  }
  if (radio_manager.shadow.ble_connected != 0U)
  {
    /* A connected peripheral cannot advertise on this single-link profile. */
    radio_manager.shadow.ble_advertising = 0U;
    radio_manager.shadow.ble_advertising_evidence =
        WIFI_BLE_ADV_CONNECTION_EVENT;
    return;
  }
  requested = radio_manager.shadow.ble_advertising_desired;
  if ((radio_manager.shadow.ble_advertising_evidence ==
       WIFI_BLE_ADV_COMMAND_ACK) &&
      (radio_manager.shadow.ble_advertising == requested))
  {
    return;
  }
  if ((radio_manager.work.ble_advertising_retry_count >=
       BLE_ADV_MAX_ATTEMPTS) ||
      (ble_tick_due(now, radio_manager.work.ble_advertising_retry_due_tick) == 0U))
  {
    return;
  }

  if (ble_control_submit(BLE_CONTROL_ADV) != 0U)
    radio_manager.counters.faults.advertising_attempts++;
}

static void ble_recover_subsystem(uint32_t now)
{

  if ((radio_manager.work.ble_recovery_pending == 0U) ||
      (radio_manager.work.ble_recovery_retry_count >= BLE_RECOVERY_MAX_ATTEMPTS) ||
      (ble_tick_due(now, radio_manager.work.ble_recovery_due_tick) == 0U))
  {
    return;
  }
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  if ((radio_manager.queues.wifi_control_context != NULL) &&
      (radio_manager.queues.wifi_control_context->active_operation !=
       WIFI_BLE_WIFI_OPERATION_NONE))
  {
    return;
  }
#endif
  if (radio_manager.shadow.ble_connected != 0U)
  {
    return;
  }
  if (ble_control_submit(BLE_CONTROL_RECOVER) != 0U)
    radio_manager.counters.faults.ble_recovery_attempts++;
}

static void ble_probe_shadow(uint32_t now)
{
  uint32_t queued_tx = 0U;
  uint32_t stalled_tx = 0U;

  if ((radio_manager.shadow.ble_gatt_ready == 0U) ||
      (radio_manager.work.ble_recovery_pending != 0U) ||
      (ble_tick_due(now, radio_manager.work.ble_probe_due_tick) == 0U))
  {
    return;
  }

  if (radio_manager.queues.ble_stream_context != NULL)
  {
    for (uint32_t stream = 0U; stream < WIFI_BLE_STREAM_COUNT; stream++)
    {
      const WifiBle_StreamStatus_t *stats =
          &radio_manager.queues.ble_stream_context->stats[stream];
      queued_tx |= (stats->tx_queued != 0U) ? 1U : 0U;
      stalled_tx |= (stats->contention.current_duration_ticks >=
                     BLE_STALLED_TX_PROBE_TICKS) ? 1U : 0U;
    }
  }
  if (radio_manager.queues.ble_tof_image_context != NULL)
  {
    queued_tx |= (radio_manager.queues.ble_tof_image_context->state !=
                  BLE_TOF_IMAGE_FREE) ? 1U : 0U;
    stalled_tx |= (radio_manager.queues.ble_tof_image_context->stats.contention.current_duration_ticks >=
                   BLE_STALLED_TX_PROBE_TICKS) ? 1U : 0U;
  }
  if (stalled_tx == 0U)
  {
    radio_manager.work.ble_tx_stall_reported = 0U;
  }
  else if (radio_manager.work.ble_tx_stall_reported == 0U)
  {
    struct spi_stat spi_stats = {0};
    uint32_t cli_streak = 0U;
    uint32_t cli_queued = 0U;
    UINT posture = tx_interrupt_control(TX_INT_DISABLE);
    (void)spi_get_stats(&spi_stats);
    (void)tx_interrupt_control(posture);
    if (radio_manager.queues.ble_stream_context != NULL)
    {
      cli_streak = radio_manager.queues.ble_stream_context->stats[WIFI_BLE_STREAM_CLI].contention.current_streak;
      cli_queued = radio_manager.queues.ble_stream_context->stats[WIFI_BLE_STREAM_CLI].tx_queued;
    }
    radio_manager.work.ble_tx_stall_reported = 1U;
    LogWarn("ST67W6X BLE TX stalled: CLI streak=%lu queued=%lu; checking NCP link.\r\n",
            (unsigned long)cli_streak, (unsigned long)cli_queued);
    LogWarn("ST67W6X SPI snapshot: tx=%lu rx=%lu io=%lu txn_timeout=%lu retry_exhaust=%lu.\r\n",
            (unsigned long)spi_stats.tx_pkts,
            (unsigned long)spi_stats.rx_pkts,
            (unsigned long)spi_stats.io_err,
            (unsigned long)spi_stats.wait_txn_timeouts,
            (unsigned long)spi_stats.retry_exhaustions);
    LogWarn("ST67W6X BLE TX stall pins: RDY=%lu CS=%lu SPI state=%lu error=0x%08lX; probe pending.\r\n",
            (unsigned long)HAL_GPIO_ReadPin(SPI_RDY_GPIO_Port, SPI_RDY_Pin),
            (unsigned long)HAL_GPIO_ReadPin(SPI_CS_GPIO_Port, SPI_CS_Pin),
            (unsigned long)NCP_SPI_HANDLE.State,
            (unsigned long)NCP_SPI_HANDLE.ErrorCode);
  }
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  if ((radio_manager.queues.wifi_control_context != NULL) &&
      (radio_manager.queues.wifi_control_context->active_operation !=
       WIFI_BLE_WIFI_OPERATION_NONE))
  {
    return;
  }
#endif
  if ((radio_manager.shadow.ble_connected != 0U) &&
      ((now - radio_manager.work.ble_last_activity_tick) <
       BLE_CONNECTED_IDLE_MS) && (stalled_tx == 0U))
  {
    return;
  }
  /* A permanently queued notification must not prevent the only AT-based
   * BLE link probe forever. Keep ordinary traffic protected, but allow one
   * bounded probe at the normal interval after a sustained TX stall. */
  if ((queued_tx != 0U) && (stalled_tx == 0U))
  {
    return;
  }

  BleControlOperation_t operation = (radio_manager.work.ble_probe_link_next == 0U) ?
      BLE_CONTROL_MODE : BLE_CONTROL_LINK;
  if (ble_control_submit(operation) != 0U)
  {
    radio_manager.work.ble_last_probe_tick = now;
    radio_manager.work.ble_probe_due_tick = now + BLE_HEALTH_PROBE_INTERVAL_MS;
    radio_manager.work.ble_probe_link_next ^= 1U;
    if (operation == BLE_CONTROL_MODE) radio_manager.counters.faults.ble_mode_queries++;
    else radio_manager.counters.faults.ble_link_queries++;
  }
}

static void ble_apply_probe(const BleControlJob_t *job)
{
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  if (ble_control_current(job) == 0U)
  { (void)tx_interrupt_control(posture); return; }
  W6X_Status_t status = job->status;
  uint32_t generation = job->generation;
  if (job->operation == BLE_CONTROL_MODE)
  {
    W6X_Ble_Mode_e mode = job->mode;
    if (generation != radio_manager.shadow.ble_session_generation)
    {
      /* A connection event superseded this in-flight mode observation. */
      (void)tx_interrupt_control(posture);
      return;
    }
    if (status == W6X_STATUS_OK)
    {
      if (mode == W6X_BLE_MODE_SERVER)
      {
        radio_manager.work.ble_mode_mismatch_count = 0U;
        radio_manager.shadow.ble_mode_confirmed = 1U;
      }
      else
      {
        radio_manager.shadow.ble_mode_confirmed = 0U;
        if (++radio_manager.work.ble_mode_mismatch_count < 2U)
        {
          radio_manager.shadow.ble_advertising_evidence =
              WIFI_BLE_ADV_UNKNOWN;
          radio_manager.work.ble_last_probe_status = status;
          (void)tx_interrupt_control(posture);
          return;
        }
        radio_manager.shadow.ble_gatt_ready = 0U;
        radio_manager.shadow.ble_advertising_evidence = WIFI_BLE_ADV_UNKNOWN;
        radio_manager.shadow.ble_link_confirmed = 0U;
        ble_note_disconnected();
        radio_manager.work.ble_recovery_pending = 1U;
        radio_manager.work.ble_recovery_retry_count = 0U;
        radio_manager.work.ble_recovery_due_tick = 0U;

      }
    }
    else
    {
      radio_manager.shadow.ble_mode_confirmed = 0U;
    }
  }
  else
  {
    uint32_t handle = job->handle;
    if ((status == W6X_STATUS_OK) &&
        (generation == radio_manager.shadow.ble_session_generation))
    {
      uint32_t mismatch =
          ((handle == 0xFFU) != (radio_manager.shadow.ble_connected == 0U)) ||
          ((handle != 0xFFU) &&
           (handle != radio_manager.shadow.ble_connection_handle));
      if (mismatch == 0U)
      {
        radio_manager.work.ble_link_mismatch_count = 0U;
        radio_manager.shadow.ble_link_confirmed = 1U;
      }
      else if (++radio_manager.work.ble_link_mismatch_count >= 2U)
      {
        radio_manager.counters.faults.ble_link_corrections++;
        radio_manager.work.ble_link_mismatch_count = 0U;
        if (handle == 0xFFU)
        {
          ble_note_disconnected();
        }
        else
        {
          radio_manager.shadow.ble_session_generation++;
          radio_manager.shadow.ble_connected = 1U;
          radio_manager.shadow.ble_connection_handle = handle;
          radio_manager.shadow.ble_advertising = 0U;
          radio_manager.shadow.ble_advertising_evidence =
              WIFI_BLE_ADV_CONNECTION_EVENT;
          radio_manager.shadow.ble_cli_tx_subscribed = 0U;
          radio_manager.shadow.ble_debug_tx_subscribed = 0U;
          radio_manager.shadow.ble_tof_image_subscribed = 0U;
          radio_manager.work.ble_stream_flush_pending = 1U;
          radio_manager.work.ble_connect_pending = 1U;
        }
        radio_manager.shadow.ble_link_confirmed = 1U;
      }
      else
      {
        radio_manager.shadow.ble_link_confirmed = 0U;
      }
    }
    else if (status == W6X_STATUS_OK)
    {
      /* A callback updated the link while the AT query was in flight. */
      (void)tx_interrupt_control(posture);
      return;
    }
    else
    {
      radio_manager.shadow.ble_link_confirmed = 0U;
    }
  }
  radio_manager.work.ble_last_probe_status = status;
  if (status != W6X_STATUS_OK)
  {
    radio_manager.counters.faults.ble_query_failures++;
    radio_manager.shadow.ble_advertising_evidence = WIFI_BLE_ADV_UNKNOWN;
  }
  (void)tx_interrupt_control(posture);
}

#endif

static void error_callback(W6X_Status_t status, const char *function_name)
{
  /* Notification admission is deliberately nonblocking. The stream pump
   * retains its fragment on BUSY and accounts for it in its contention
   * counters; it is not a driver failure. Keep real notification errors and
   * BUSY from other control operations visible. */
  if ((status == W6X_STATUS_BUSY) && (function_name != NULL) &&
      ((strcmp(function_name, "W6X_Ble_ServerNotify") == 0) ||
       (strcmp(function_name, "W6X_Ble_ServerNotifyBegin") == 0) ||
       (strcmp(function_name, "W6X_Ble_ServerNotifyPoll") == 0) ||
       (strcmp(function_name, "W6X_Ble_ServerNotifyCancel") == 0)))
  {
    return;
  }

  radio_manager.counters.faults.driver_error_callbacks++;
  radio_manager.counters.faults.last_driver_error = status;
  LogError("ST67W6X error in %s: %" PRIi32 "\r\n",
           (function_name != NULL) ? function_name : "?", status);
}

static void log_output(const char *message)
{
  if (message != NULL)
  {
    /* Debug_UART_Write copies into its fixed queue and never waits for the
     * physical USART once asynchronous logging is initialized. */
    (void)Debug_UART_Write(message, strlen(message));
  }
}
