#include "wifi_ble_app.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "app_features.h"
#include "bsp_conf.h"
#include "debug_uart.h"
#include "logging.h"
#include "main.h"
#include "vl53l9_interface.h"
#include "spi_iface.h"
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
} WifiBle_StreamContext_t;

typedef enum
{
  BLE_TOF_IMAGE_FREE = 0,
  BLE_TOF_IMAGE_FILLING,
  BLE_TOF_IMAGE_READY,
  BLE_TOF_IMAGE_ACTIVE
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
  uint8_t payload[BLE_TOF_IMAGE_MAX_BYTES] __attribute__((aligned(4)));
} WifiBle_TofImageContext_t;

_Static_assert(sizeof(void *) <= sizeof(ULONG),
               "ThreadX pointer queues require one ULONG per pointer");
_Static_assert(sizeof(WifiBle_StreamContext_t) <= BLE_STREAM_CONTEXT_BUDGET,
               "BLE stream queues exceeded their SRAM4 design budget");
_Static_assert(sizeof(WifiBle_TofImageContext_t) <=
               BLE_TOF_IMAGE_CONTEXT_BUDGET,
               "BLE ToF image context exceeded its SRAM4 design budget");

static uint8_t ble_receive_buffer[WIFI_BLE_RX_BUFFER_SIZE];
static WifiBle_StreamContext_t *ble_stream_context;
static WifiBle_TofImageContext_t *ble_tof_image_context;
static TX_BYTE_POOL *ble_radio_pool;
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
static volatile WifiBle_State_t wifi_ble_state = WIFI_BLE_STATE_DISABLED;
static volatile uint32_t wifi_connected;
static volatile uint32_t wifi_has_ip;
static volatile uint32_t ble_gatt_ready;
static volatile uint32_t ble_connected;
static volatile uint32_t ble_advertising;
static volatile uint32_t ble_connection_handle = 0xFFU;
static volatile uint32_t ble_mtu = 23U;
static volatile uint32_t ble_cli_tx_subscribed;
static volatile uint32_t ble_debug_tx_subscribed;
static volatile uint32_t ble_tof_image_subscribed;
static volatile uint32_t ble_rx_write_events;
static volatile uint32_t ble_rx_discarded_bytes;
static volatile uint32_t ble_session_generation;
static volatile uint32_t ble_transport_ready;
static volatile uint32_t ble_stream_flush_pending;
static volatile uint32_t ble_init_stage = WIFI_BLE_INIT_STAGE_IDLE;
static volatile int32_t ble_last_status;
static volatile uint32_t ble_connect_pending;
static volatile uint32_t ble_restart_advertising_pending;
static volatile uint32_t ble_adv_request = BLE_ADV_REQUEST_NONE;
static volatile uint32_t ble_disconnect_request;
static char ble_device_name[WIFI_BLE_DEVICE_NAME_SIZE];
static uint8_t ble_address[WIFI_BLE_ADDRESS_SIZE];

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
static void wifi_event_callback(W6X_event_id_t event_id, void *event_args);
#endif
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static void ble_event_callback(W6X_event_id_t event_id, void *event_args);
static W6X_Status_t ble_configure_gatt_server(void);
static void ble_process_pending_events(void);
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
  static W6X_App_Cb_t callbacks = {
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    .APP_wifi_cb = wifi_event_callback,
#else
    .APP_wifi_cb = NULL,
#endif
    .APP_net_cb = NULL,
    .APP_mqtt_cb = NULL,
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
    .APP_ble_cb = ble_event_callback,
#else
    .APP_ble_cb = NULL,
#endif
    .APP_error_cb = error_callback,
  };

  wifi_ble_state = WIFI_BLE_STATE_STARTING;

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
#endif

#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  (void)memset(ble_receive_buffer, 0, sizeof(ble_receive_buffer));
  ble_init_stage = WIFI_BLE_INIT_STAGE_STACK;
  status = W6X_Ble_Init(W6X_BLE_MODE_SERVER, ble_receive_buffer,
                        sizeof(ble_receive_buffer) - 1U);
  ble_last_status = status;
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

  wifi_ble_state = WIFI_BLE_STATE_READY;
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  LogInfo("ST67W6X: BLE maintenance GATT server is advertising.\r\n");
  LogInfo("ST67W6X: bounded CLI/DEBUG streams, signed BLE XMODEM and ToF image notifications ready.\r\n");
#elif (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  LogInfo("ST67W6X: Wi-Fi station service is ready; no credentials are configured.\r\n");
#else
  LogInfo("ST67W6X: SPI/AT transport and module identity are ready.\r\n");
  LogInfo("ST67W6X: Wi-Fi and BLE services are disabled.\r\n");
#endif

  for (;;)
  {
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
    ble_process_pending_events();
    tx_thread_sleep((TX_TIMER_TICKS_PER_SECOND >= 50U) ?
                    (TX_TIMER_TICKS_PER_SECOND / 50U) : 1U);
#else
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND);
#endif
  }

error:
  wifi_ble_state = WIFI_BLE_STATE_ERROR;
  LogError("ST67W6X thread stopped in ERROR state; ToF continues running.\r\n");
  for (;;)
  {
    tx_thread_sleep(5U * TX_TIMER_TICKS_PER_SECOND);
  }
}

WifiBle_State_t WIFI_BLE_App_GetState(void)
{
  return wifi_ble_state;
}

void WIFI_BLE_App_GetRuntimeStatus(WifiBle_RuntimeStatus_t *status)
{
  UINT posture;

  if (status == NULL)
  {
    return;
  }

  status->state = wifi_ble_state;
  status->wifi_connected = wifi_connected;
  status->wifi_has_ip = wifi_has_ip;
  status->ble_gatt_ready = ble_gatt_ready;
  status->ble_connected = ble_connected;
  status->ble_advertising = ble_advertising;
  status->ble_connection_handle = ble_connection_handle;
  status->ble_mtu = ble_mtu;
  status->ble_cli_tx_subscribed = ble_cli_tx_subscribed;
  status->ble_debug_tx_subscribed = ble_debug_tx_subscribed;
  status->ble_tof_image_subscribed = ble_tof_image_subscribed;
  status->ble_rx_write_events = ble_rx_write_events;
  status->ble_rx_discarded_bytes = ble_rx_discarded_bytes;
  status->ble_session_generation = ble_session_generation;
  status->ble_att_payload_limit =
      (ble_mtu > 3U) ? ((ble_mtu - 3U) < W6X_BLE_MAX_NOTIF_IND_DATA_LENGTH ?
                       (ble_mtu - 3U) : W6X_BLE_MAX_NOTIF_IND_DATA_LENGTH) : 20U;
  status->ble_transport_ready = ble_transport_ready;
  status->ble_radio_pool_available = 0U;
  status->ble_radio_pool_fragments = 0U;
  status->ble_init_stage = ble_init_stage;
  status->ble_last_status = ble_last_status;
  (void)memset(status->ble_stream, 0, sizeof(status->ble_stream));
  (void)memset(&status->ble_tof_image, 0, sizeof(status->ble_tof_image));
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  posture = tx_interrupt_control(TX_INT_DISABLE);
  if (ble_stream_context != NULL)
  {
    status->ble_stream[WIFI_BLE_STREAM_CLI] =
        ble_stream_context->stats[WIFI_BLE_STREAM_CLI];
    status->ble_stream[WIFI_BLE_STREAM_DEBUG] =
        ble_stream_context->stats[WIFI_BLE_STREAM_DEBUG];
  }
  if (ble_tof_image_context != NULL)
  {
    status->ble_tof_image = ble_tof_image_context->stats;
  }
  (void)tx_interrupt_control(posture);
  if (ble_radio_pool != NULL)
  {
    ULONG available = 0U;
    ULONG fragments = 0U;
    if (tx_byte_pool_info_get(ble_radio_pool, TX_NULL, &available, &fragments,
                              TX_NULL, TX_NULL, TX_NULL) == TX_SUCCESS)
    {
      status->ble_radio_pool_available = available;
      status->ble_radio_pool_fragments = fragments;
    }
  }
#else
  (void)posture;
#endif
  (void)memcpy(status->ble_device_name, ble_device_name,
               sizeof(status->ble_device_name));
  (void)memcpy(status->ble_address, ble_address,
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
  if (ble_gatt_ready == 0U)
  {
    return TX_NOT_AVAILABLE;
  }
  ble_adv_request = (advertising != 0U) ? 1U : 0U;
  return TX_SUCCESS;
}

UINT WIFI_BLE_App_RequestDisconnect(void)
{
  if (ble_connected == 0U)
  {
    return TX_NOT_AVAILABLE;
  }
  ble_disconnect_request = 1U;
  return TX_SUCCESS;
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
  if ((ble_transport_ready == 0U) || (ble_connected == 0U) ||
      (ble_stream_context == NULL))
  {
    return TX_NOT_AVAILABLE;
  }

  subscribed = (stream == WIFI_BLE_STREAM_CLI) ?
               ble_cli_tx_subscribed : ble_debug_tx_subscribed;
  if (subscribed == 0U)
  {
    return TX_NOT_AVAILABLE;
  }

  if (stream == WIFI_BLE_STREAM_CLI)
  {
    free_queue = &ble_stream_context->cli_tx_free;
    ready_queue = &ble_stream_context->cli_tx_ready;
    capacity = BLE_CLI_TX_SLOT_SIZE;
    if ((wait_option == TX_WAIT_FOREVER) ||
        (wait_option > BLE_CLI_TX_MAX_WAIT_TICKS))
    {
      wait_option = BLE_CLI_TX_MAX_WAIT_TICKS;
    }
  }
  else
  {
    free_queue = &ble_stream_context->debug_tx_free;
    ready_queue = &ble_stream_context->debug_tx_ready;
    capacity = BLE_DEBUG_TX_SLOT_SIZE;
    /* Debug mirroring is best-effort and must never stall its producer. */
    wait_option = TX_NO_WAIT;
  }

  if (length > capacity)
  {
    posture = tx_interrupt_control(TX_INT_DISABLE);
    ble_stream_context->stats[stream].tx_dropped_messages++;
    ble_stream_context->stats[stream].tx_dropped_bytes += length;
    (void)tx_interrupt_control(posture);
    return TX_SIZE_ERROR;
  }

  result = tx_queue_receive(free_queue, &slot, wait_option);
  if (result != TX_SUCCESS)
  {
    posture = tx_interrupt_control(TX_INT_DISABLE);
    ble_stream_context->stats[stream].tx_dropped_messages++;
    ble_stream_context->stats[stream].tx_dropped_bytes += length;
    (void)tx_interrupt_control(posture);
    return result;
  }

  if ((ble_connected == 0U) ||
      (((stream == WIFI_BLE_STREAM_CLI) ? ble_cli_tx_subscribed :
                                           ble_debug_tx_subscribed) == 0U))
  {
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    return TX_NOT_AVAILABLE;
  }

  if (stream == WIFI_BLE_STREAM_CLI)
  {
    WifiBle_CliTxSlot_t *tx_slot = (WifiBle_CliTxSlot_t *)slot;
    tx_slot->generation = ble_session_generation;
    tx_slot->length = (uint16_t)length;
    tx_slot->offset = 0U;
    tx_slot->retries = 0U;
    (void)memcpy(tx_slot->data, buffer, length);
  }
  else
  {
    WifiBle_DebugTxSlot_t *tx_slot = (WifiBle_DebugTxSlot_t *)slot;
    tx_slot->generation = ble_session_generation;
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
    ble_stream_context->stats[stream].tx_dropped_messages++;
    ble_stream_context->stats[stream].tx_dropped_bytes += length;
    (void)tx_interrupt_control(posture);
    return result;
  }

  posture = tx_interrupt_control(TX_INT_DISABLE);
  ble_stream_context->stats[stream].tx_messages++;
  ble_stream_context->stats[stream].tx_bytes += length;
  ble_stream_context->stats[stream].tx_queued++;
  if (ble_stream_context->stats[stream].tx_queued >
      ble_stream_context->stats[stream].tx_high_water)
  {
    ble_stream_context->stats[stream].tx_high_water =
        ble_stream_context->stats[stream].tx_queued;
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

UINT WIFI_BLE_App_StreamRead(WifiBle_Stream_t stream, void *buffer,
                             ULONG capacity, ULONG *actual_length,
                             ULONG wait_option)
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
  if ((ble_transport_ready == 0U) || (ble_stream_context == NULL))
  {
    return TX_NOT_AVAILABLE;
  }

  free_queue = (stream == WIFI_BLE_STREAM_CLI) ?
               &ble_stream_context->cli_rx_free :
               &ble_stream_context->debug_rx_free;
  ready_queue = (stream == WIFI_BLE_STREAM_CLI) ?
                &ble_stream_context->cli_rx_ready :
                &ble_stream_context->debug_rx_ready;

  do
  {
    result = tx_queue_receive(ready_queue, &slot, wait_option);
    if (result != TX_SUCCESS)
    {
      return result;
    }
    posture = tx_interrupt_control(TX_INT_DISABLE);
    if (ble_stream_context->stats[stream].rx_queued != 0U)
    {
      ble_stream_context->stats[stream].rx_queued--;
    }
    (void)tx_interrupt_control(posture);

    if (slot->generation != ble_session_generation)
    {
      (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
      posture = tx_interrupt_control(TX_INT_DISABLE);
      ble_stream_context->stats[stream].stale_drops++;
      (void)tx_interrupt_control(posture);
      slot = NULL;
      wait_option = TX_NO_WAIT;
    }
  } while (slot == NULL);

  *actual_length = slot->length;
  if (capacity < slot->length)
  {
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    return TX_SIZE_ERROR;
  }

  (void)memcpy(buffer, slot->data, slot->length);
  (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
  return TX_SUCCESS;
#else
  (void)stream;
  (void)buffer;
  (void)capacity;
  (void)wait_option;
  if (actual_length != NULL)
  {
    *actual_length = 0U;
  }
  return TX_NOT_AVAILABLE;
#endif
}

uint32_t WIFI_BLE_App_IsTofImageSubscribed(void)
{
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  return ((ble_transport_ready != 0U) && (ble_connected != 0U) &&
          (ble_tof_image_subscribed != 0U) &&
          (ble_tof_image_context != NULL)) ? 1U : 0U;
#else
  return 0U;
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
  if (ble_tof_image_context->state != BLE_TOF_IMAGE_FREE)
  {
    ble_tof_image_context->stats.frames_dropped_busy++;
    (void)tx_interrupt_control(posture);
    return TX_QUEUE_FULL;
  }
  ble_tof_image_context->state = BLE_TOF_IMAGE_FILLING;
  ble_tof_image_context->generation = ble_session_generation;
  (void)tx_interrupt_control(posture);

  (void)memcpy(ble_tof_image_context->payload, pixels, payload_length);
  ble_tof_image_context->frame_id = frame_id;
  ble_tof_image_context->payload_crc32 =
      ble_crc32(ble_tof_image_context->payload, payload_length);
  ble_tof_image_context->payload_length = (uint16_t)payload_length;
  ble_tof_image_context->offset = 0U;
  ble_tof_image_context->width = width;
  ble_tof_image_context->height = height;
  ble_tof_image_context->channel_id = channel_id;
  ble_tof_image_context->retries = 0U;

  posture = tx_interrupt_control(TX_INT_DISABLE);
  ble_tof_image_context->stats.frames_submitted++;
  ble_tof_image_context->stats.last_submitted_frame = frame_id;
  ble_tof_image_context->state = BLE_TOF_IMAGE_READY;
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
static void wifi_event_callback(W6X_event_id_t event_id, void *event_args)
{
  (void)event_args;
  if (event_id == W6X_WIFI_EVT_CONNECTED_ID)
  {
    wifi_connected = 1U;
    LogInfo("ST67W6X Wi-Fi connected.\r\n");
  }
  else if (event_id == W6X_WIFI_EVT_GOT_IP_ID)
  {
    wifi_has_ip = 1U;
    LogInfo("ST67W6X Wi-Fi address acquired.\r\n");
  }
  else if (event_id == W6X_WIFI_EVT_DISCONNECTED_ID)
  {
    wifi_connected = 0U;
    wifi_has_ip = 0U;
    LogInfo("ST67W6X Wi-Fi disconnected.\r\n");
  }
}
#endif

#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static void ble_event_callback(W6X_event_id_t event_id, void *event_args)
{
  W6X_Ble_CbParamData_t *event = (W6X_Ble_CbParamData_t *)event_args;

  if (event_id == W6X_BLE_EVT_CONNECTED_ID)
  {
    if (event != NULL)
    {
      ble_session_generation++;
      ble_connected = 1U;
      ble_advertising = 0U;
      ble_connection_handle = event->remote_ble_device.conn_handle;
      ble_connect_pending = 1U;
      ble_stream_flush_pending = 1U;
    }
  }
  else if (event_id == W6X_BLE_EVT_DISCONNECTED_ID)
  {
    ble_session_generation++;
    ble_connected = 0U;
    ble_connect_pending = 0U;
    ble_connection_handle = 0xFFU;
    ble_cli_tx_subscribed = 0U;
    ble_debug_tx_subscribed = 0U;
    ble_tof_image_subscribed = 0U;
    ble_mtu = 23U;
    ble_restart_advertising_pending = 1U;
    ble_stream_flush_pending = 1U;
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
        ble_cli_tx_subscribed = enabled;
      }
      else if ((event->service_idx == BLE_DEBUG_SERVICE_INDEX) &&
               (event->charac_idx == BLE_TX_CHAR_INDEX))
      {
        ble_debug_tx_subscribed = enabled;
      }
      else if ((event->service_idx == BLE_CLI_SERVICE_INDEX) &&
               (event->charac_idx == BLE_TOF_IMAGE_CHAR_INDEX))
      {
        ble_tof_image_subscribed = enabled;
      }
    }
  }
  else if ((event_id == W6X_BLE_EVT_MTU_SIZE_ID) && (event != NULL))
  {
    ble_mtu = event->mtu_size;
  }
  else if ((event_id == W6X_BLE_EVT_WRITE_ID) && (event != NULL))
  {
    ble_rx_write_events++;
    if ((ble_connected == 0U) ||
        (event->remote_ble_device.conn_handle != ble_connection_handle) ||
        (event->charac_idx != BLE_RX_CHAR_INDEX) ||
        (event->available_data_length == 0U) ||
        (event->available_data_length > sizeof(ble_receive_buffer)))
    {
      ble_rx_discarded_bytes += event->available_data_length;
    }
    else if (event->service_idx == BLE_CLI_SERVICE_INDEX)
    {
      ble_stream_enqueue_rx(WIFI_BLE_STREAM_CLI, ble_receive_buffer,
                            event->available_data_length);
    }
    else if (event->service_idx == BLE_DEBUG_SERVICE_INDEX)
    {
#if (BLE_DEBUG_RX_POLICY_ENABLED == 1U)
      ble_stream_enqueue_rx(WIFI_BLE_STREAM_DEBUG, ble_receive_buffer,
                            event->available_data_length);
#else
      UINT posture = tx_interrupt_control(TX_INT_DISABLE);
      ble_rx_discarded_bytes += event->available_data_length;
      if (ble_stream_context != NULL)
      {
        ble_stream_context->stats[WIFI_BLE_STREAM_DEBUG].rx_dropped_events++;
        ble_stream_context->stats[WIFI_BLE_STREAM_DEBUG].rx_dropped_bytes +=
            event->available_data_length;
      }
      (void)tx_interrupt_control(posture);
#endif
    }
    else
    {
      ble_rx_discarded_bytes += event->available_data_length;
    }
  }
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

  ble_radio_pool = MX_RadioBytePool_Get();
  if ((ble_radio_pool == NULL) ||
      (tx_byte_allocate(ble_radio_pool, &memory,
                        (ULONG)sizeof(WifiBle_StreamContext_t),
                        TX_NO_WAIT) != TX_SUCCESS))
  {
    return TX_POOL_ERROR;
  }

  ble_stream_context = (WifiBle_StreamContext_t *)memory;
  (void)memset(ble_stream_context, 0, sizeof(*ble_stream_context));

  if (tx_byte_allocate(ble_radio_pool, &image_memory,
                       (ULONG)sizeof(WifiBle_TofImageContext_t),
                       TX_NO_WAIT) != TX_SUCCESS)
  {
    (void)tx_byte_release(ble_stream_context);
    ble_stream_context = NULL;
    return TX_POOL_ERROR;
  }
  ble_tof_image_context = (WifiBle_TofImageContext_t *)image_memory;
  (void)memset(ble_tof_image_context, 0, sizeof(*ble_tof_image_context));

  if ((ble_create_pointer_queue(&ble_stream_context->cli_rx_free,
                                "BLE CLI RX free",
                                ble_stream_context->cli_rx_free_storage,
                                BLE_CLI_RX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&ble_stream_context->cli_rx_ready,
                                "BLE CLI RX ready",
                                ble_stream_context->cli_rx_ready_storage,
                                BLE_CLI_RX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&ble_stream_context->debug_rx_free,
                                "BLE debug RX free",
                                ble_stream_context->debug_rx_free_storage,
                                BLE_DEBUG_RX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&ble_stream_context->debug_rx_ready,
                                "BLE debug RX ready",
                                ble_stream_context->debug_rx_ready_storage,
                                BLE_DEBUG_RX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&ble_stream_context->cli_tx_free,
                                "BLE CLI TX free",
                                ble_stream_context->cli_tx_free_storage,
                                BLE_CLI_TX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&ble_stream_context->cli_tx_ready,
                                "BLE CLI TX ready",
                                ble_stream_context->cli_tx_ready_storage,
                                BLE_CLI_TX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&ble_stream_context->debug_tx_free,
                                "BLE debug TX free",
                                ble_stream_context->debug_tx_free_storage,
                                BLE_DEBUG_TX_SLOT_COUNT) != TX_SUCCESS) ||
      (ble_create_pointer_queue(&ble_stream_context->debug_tx_ready,
                                "BLE debug TX ready",
                                ble_stream_context->debug_tx_ready_storage,
                                BLE_DEBUG_TX_SLOT_COUNT) != TX_SUCCESS))
  {
    return TX_QUEUE_ERROR;
  }

  for (uint32_t i = 0U; i < BLE_CLI_RX_SLOT_COUNT; ++i)
  {
    slot = &ble_stream_context->cli_rx_slots[i];
    if (tx_queue_send(&ble_stream_context->cli_rx_free, &slot,
                      TX_NO_WAIT) != TX_SUCCESS)
    {
      return TX_QUEUE_ERROR;
    }
  }
  for (uint32_t i = 0U; i < BLE_DEBUG_RX_SLOT_COUNT; ++i)
  {
    slot = &ble_stream_context->debug_rx_slots[i];
    if (tx_queue_send(&ble_stream_context->debug_rx_free, &slot,
                      TX_NO_WAIT) != TX_SUCCESS)
    {
      return TX_QUEUE_ERROR;
    }
  }
  for (uint32_t i = 0U; i < BLE_CLI_TX_SLOT_COUNT; ++i)
  {
    slot = &ble_stream_context->cli_tx_slots[i];
    if (tx_queue_send(&ble_stream_context->cli_tx_free, &slot,
                      TX_NO_WAIT) != TX_SUCCESS)
    {
      return TX_QUEUE_ERROR;
    }
  }
  for (uint32_t i = 0U; i < BLE_DEBUG_TX_SLOT_COUNT; ++i)
  {
    slot = &ble_stream_context->debug_tx_slots[i];
    if (tx_queue_send(&ble_stream_context->debug_tx_free, &slot,
                      TX_NO_WAIT) != TX_SUCCESS)
    {
      return TX_QUEUE_ERROR;
    }
  }

  ble_transport_ready = 1U;
  if (tx_byte_pool_info_get(ble_radio_pool, TX_NULL, &available, &fragments,
                            TX_NULL, TX_NULL, TX_NULL) == TX_SUCCESS)
  {
    LogInfo("ST67W6X BLE streams: %lu-byte queues + %lu-byte ToF frame, radio pool %lu bytes free in %lu fragments.\r\n",
            (unsigned long)sizeof(*ble_stream_context),
            (unsigned long)sizeof(*ble_tof_image_context),
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

  if ((ble_stream_context == NULL) || (data == NULL) ||
      (stream >= WIFI_BLE_STREAM_COUNT) ||
      (length > BLE_RX_SLOT_PAYLOAD_SIZE))
  {
    ble_rx_discarded_bytes += length;
    return;
  }

  free_queue = (stream == WIFI_BLE_STREAM_CLI) ?
               &ble_stream_context->cli_rx_free :
               &ble_stream_context->debug_rx_free;
  ready_queue = (stream == WIFI_BLE_STREAM_CLI) ?
                &ble_stream_context->cli_rx_ready :
                &ble_stream_context->debug_rx_ready;

  if (tx_queue_receive(free_queue, &slot, TX_NO_WAIT) != TX_SUCCESS)
  {
    posture = tx_interrupt_control(TX_INT_DISABLE);
    ble_rx_discarded_bytes += length;
    ble_stream_context->stats[stream].rx_dropped_events++;
    ble_stream_context->stats[stream].rx_dropped_bytes += length;
    (void)tx_interrupt_control(posture);
    return;
  }

  slot->generation = ble_session_generation;
  slot->length = (uint16_t)length;
  (void)memcpy(slot->data, data, length);
  if (tx_queue_send(ready_queue, &slot, TX_NO_WAIT) != TX_SUCCESS)
  {
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    posture = tx_interrupt_control(TX_INT_DISABLE);
    ble_rx_discarded_bytes += length;
    ble_stream_context->stats[stream].rx_dropped_events++;
    ble_stream_context->stats[stream].rx_dropped_bytes += length;
    (void)tx_interrupt_control(posture);
    return;
  }

  posture = tx_interrupt_control(TX_INT_DISABLE);
  ble_stream_context->stats[stream].rx_events++;
  ble_stream_context->stats[stream].rx_bytes += length;
  ble_stream_context->stats[stream].rx_queued++;
  if (ble_stream_context->stats[stream].rx_queued >
      ble_stream_context->stats[stream].rx_high_water)
  {
    ble_stream_context->stats[stream].rx_high_water =
        ble_stream_context->stats[stream].rx_queued;
  }
  (void)tx_interrupt_control(posture);
}

static uint32_t ble_att_payload_size(void)
{
  uint32_t payload = (ble_mtu > 3U) ? (ble_mtu - 3U) : 20U;
  if (payload > W6X_BLE_MAX_NOTIF_IND_DATA_LENGTH)
  {
    payload = W6X_BLE_MAX_NOTIF_IND_DATA_LENGTH;
  }
  return payload;
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

  if ((ble_stream_context == NULL) || (stream >= WIFI_BLE_STREAM_COUNT))
  {
    return;
  }

  subscribed = (stream == WIFI_BLE_STREAM_CLI) ?
               ble_cli_tx_subscribed : ble_debug_tx_subscribed;
  if ((ble_connected == 0U) || (subscribed == 0U))
  {
    ble_stream_drop_tx(stream);
    return;
  }

  free_queue = (stream == WIFI_BLE_STREAM_CLI) ?
               &ble_stream_context->cli_tx_free :
               &ble_stream_context->debug_tx_free;
  ready_queue = (stream == WIFI_BLE_STREAM_CLI) ?
                &ble_stream_context->cli_tx_ready :
                &ble_stream_context->debug_tx_ready;
  slot = ble_stream_context->active_tx[stream];
  if (slot == NULL)
  {
    if (tx_queue_receive(ready_queue, &slot, TX_NO_WAIT) != TX_SUCCESS)
    {
      return;
    }
    ble_stream_context->active_tx[stream] = slot;
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

  if (generation != ble_session_generation)
  {
    ble_stream_context->active_tx[stream] = NULL;
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    posture = tx_interrupt_control(TX_INT_DISABLE);
    if (ble_stream_context->stats[stream].tx_queued != 0U)
    {
      ble_stream_context->stats[stream].tx_queued--;
    }
    ble_stream_context->stats[stream].stale_drops++;
    (void)tx_interrupt_control(posture);
    return;
  }

  fragment = (uint32_t)(*length - *offset);
  if (fragment > ble_att_payload_size())
  {
    fragment = ble_att_payload_size();
  }
  result = W6X_Ble_ServerNotify((uint8_t)ble_connection_handle,
                                (stream == WIFI_BLE_STREAM_CLI) ?
                                BLE_CLI_SERVICE_INDEX : BLE_DEBUG_SERVICE_INDEX,
                                BLE_TX_CHAR_INDEX, &data[*offset], fragment,
                                &sent, BLE_NOTIFY_TIMEOUT_MS);
  if ((result == W6X_STATUS_OK) && (sent != 0U))
  {
    if (sent > fragment)
    {
      sent = fragment;
    }
    *offset = (uint16_t)(*offset + sent);
    *retries = 0U;
    posture = tx_interrupt_control(TX_INT_DISABLE);
    ble_stream_context->stats[stream].tx_sent_bytes += sent;
    (void)tx_interrupt_control(posture);
    if (*offset >= *length)
    {
      ble_stream_context->active_tx[stream] = NULL;
      (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
      posture = tx_interrupt_control(TX_INT_DISABLE);
      if (ble_stream_context->stats[stream].tx_queued != 0U)
      {
        ble_stream_context->stats[stream].tx_queued--;
      }
      (void)tx_interrupt_control(posture);
    }
    return;
  }

  (*retries)++;
  posture = tx_interrupt_control(TX_INT_DISABLE);
  ble_stream_context->stats[stream].tx_retries++;
  ble_stream_context->stats[stream].tx_errors++;
  (void)tx_interrupt_control(posture);
  if (*retries >= BLE_NOTIFY_MAX_ATTEMPTS)
  {
    uint32_t dropped = (uint32_t)(*length - *offset);
    ble_stream_context->active_tx[stream] = NULL;
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    posture = tx_interrupt_control(TX_INT_DISABLE);
    if (ble_stream_context->stats[stream].tx_queued != 0U)
    {
      ble_stream_context->stats[stream].tx_queued--;
    }
    ble_stream_context->stats[stream].tx_dropped_messages++;
    ble_stream_context->stats[stream].tx_dropped_bytes += dropped;
    (void)tx_interrupt_control(posture);
  }
}

static void __attribute__((optimize("Os"))) ble_tof_image_drop_active(void)
{
  UINT posture;

  if (ble_tof_image_context == NULL)
  {
    return;
  }
  posture = tx_interrupt_control(TX_INT_DISABLE);
  if ((ble_tof_image_context->state == BLE_TOF_IMAGE_READY) ||
      (ble_tof_image_context->state == BLE_TOF_IMAGE_ACTIVE))
  {
    ble_tof_image_context->state = BLE_TOF_IMAGE_FREE;
    ble_tof_image_context->stats.frames_aborted++;
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

  if (ble_tof_image_context == NULL)
  {
    return;
  }
  if ((ble_connected == 0U) || (ble_tof_image_subscribed == 0U))
  {
    ble_tof_image_drop_active();
    return;
  }
  if (ble_tof_image_context->state == BLE_TOF_IMAGE_READY)
  {
    ble_tof_image_context->state = BLE_TOF_IMAGE_ACTIVE;
  }
  if (ble_tof_image_context->state != BLE_TOF_IMAGE_ACTIVE)
  {
    return;
  }
  if (ble_tof_image_context->generation != ble_session_generation)
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
  chunk_length = (uint32_t)(ble_tof_image_context->payload_length -
                            ble_tof_image_context->offset);
  if (chunk_length > (att_payload - WIFI_BLE_TOF_FRAGMENT_HEADER_SIZE))
  {
    chunk_length = att_payload - WIFI_BLE_TOF_FRAGMENT_HEADER_SIZE;
  }
  if (ble_tof_image_context->offset == 0U)
  {
    flags |= WIFI_BLE_TOF_FRAGMENT_FLAG_START;
  }
  if (((uint32_t)ble_tof_image_context->offset + chunk_length) >=
      ble_tof_image_context->payload_length)
  {
    flags |= WIFI_BLE_TOF_FRAGMENT_FLAG_END;
  }

  ble_write_u16(&packet[0], WIFI_BLE_TOF_FRAGMENT_MAGIC);
  packet[2] = WIFI_BLE_TOF_FRAGMENT_VERSION;
  packet[3] = flags;
  ble_write_u32(&packet[4], ble_tof_image_context->frame_id);
  ble_write_u16(&packet[8], ble_tof_image_context->offset);
  ble_write_u16(&packet[10], ble_tof_image_context->payload_length);
  packet[12] = ble_tof_image_context->width;
  packet[13] = ble_tof_image_context->height;
  packet[14] = ble_tof_image_context->channel_id;
  packet[15] = WIFI_BLE_TOF_PIXEL_FORMAT_FLOAT32_LE;
  ble_write_u32(&packet[16], ble_tof_image_context->payload_crc32);
  (void)memcpy(&packet[WIFI_BLE_TOF_FRAGMENT_HEADER_SIZE],
               &ble_tof_image_context->payload[ble_tof_image_context->offset],
               chunk_length);
  packet_length = WIFI_BLE_TOF_FRAGMENT_HEADER_SIZE + chunk_length;

  result = W6X_Ble_ServerNotify((uint8_t)ble_connection_handle,
                                BLE_CLI_SERVICE_INDEX,
                                BLE_TOF_IMAGE_CHAR_INDEX,
                                packet, packet_length, &sent,
                                BLE_NOTIFY_TIMEOUT_MS);
  if ((result == W6X_STATUS_OK) && (sent == packet_length))
  {
    ble_tof_image_context->offset =
        (uint16_t)(ble_tof_image_context->offset + chunk_length);
    ble_tof_image_context->retries = 0U;
    posture = tx_interrupt_control(TX_INT_DISABLE);
    ble_tof_image_context->stats.fragments_sent++;
    ble_tof_image_context->stats.bytes_sent += chunk_length;
    if (ble_tof_image_context->offset >=
        ble_tof_image_context->payload_length)
    {
      ble_tof_image_context->stats.frames_sent++;
      ble_tof_image_context->stats.last_sent_frame =
          ble_tof_image_context->frame_id;
      ble_tof_image_context->state = BLE_TOF_IMAGE_FREE;
    }
    (void)tx_interrupt_control(posture);
    return;
  }

  ble_tof_image_context->retries++;
  posture = tx_interrupt_control(TX_INT_DISABLE);
  ble_tof_image_context->stats.retries++;
  ble_tof_image_context->stats.errors++;
  if (ble_tof_image_context->retries >= BLE_NOTIFY_MAX_ATTEMPTS)
  {
    ble_tof_image_context->stats.frames_aborted++;
    ble_tof_image_context->state = BLE_TOF_IMAGE_FREE;
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
    if (generation == ble_session_generation)
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
        if (ble_stream_context->stats[stream].tx_queued != 0U)
        {
          ble_stream_context->stats[stream].tx_queued--;
        }
      }
      else if (ble_stream_context->stats[stream].rx_queued != 0U)
      {
        ble_stream_context->stats[stream].rx_queued--;
      }
      ble_stream_context->stats[stream].stale_drops++;
      (void)tx_interrupt_control(posture);
    }
  }
}

static void ble_stream_purge_stale(void)
{
  if (ble_stream_context == NULL)
  {
    return;
  }

  ble_purge_queue(&ble_stream_context->cli_rx_ready,
                  &ble_stream_context->cli_rx_free,
                  WIFI_BLE_STREAM_CLI, 0U);
  ble_purge_queue(&ble_stream_context->debug_rx_ready,
                  &ble_stream_context->debug_rx_free,
                  WIFI_BLE_STREAM_DEBUG, 0U);
  ble_purge_queue(&ble_stream_context->cli_tx_ready,
                  &ble_stream_context->cli_tx_free,
                  WIFI_BLE_STREAM_CLI, 1U);
  ble_purge_queue(&ble_stream_context->debug_tx_ready,
                  &ble_stream_context->debug_tx_free,
                  WIFI_BLE_STREAM_DEBUG, 1U);

  for (uint32_t i = 0U; i < WIFI_BLE_STREAM_COUNT; ++i)
  {
    void *slot = ble_stream_context->active_tx[i];
    uint32_t generation = 0U;
    if (slot == NULL)
    {
      continue;
    }
    (void)memcpy(&generation, slot, sizeof(generation));
    if (generation != ble_session_generation)
    {
      TX_QUEUE *free_queue = (i == WIFI_BLE_STREAM_CLI) ?
                             &ble_stream_context->cli_tx_free :
                             &ble_stream_context->debug_tx_free;
      UINT posture;
      ble_stream_context->active_tx[i] = NULL;
      (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
      posture = tx_interrupt_control(TX_INT_DISABLE);
      if (ble_stream_context->stats[i].tx_queued != 0U)
      {
        ble_stream_context->stats[i].tx_queued--;
      }
      ble_stream_context->stats[i].stale_drops++;
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

  if ((ble_stream_context == NULL) || (stream >= WIFI_BLE_STREAM_COUNT))
  {
    return;
  }
  free_queue = (stream == WIFI_BLE_STREAM_CLI) ?
               &ble_stream_context->cli_tx_free :
               &ble_stream_context->debug_tx_free;
  ready_queue = (stream == WIFI_BLE_STREAM_CLI) ?
                &ble_stream_context->cli_tx_ready :
                &ble_stream_context->debug_tx_ready;

  slot = ble_stream_context->active_tx[stream];
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
    ble_stream_context->active_tx[stream] = NULL;
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    posture = tx_interrupt_control(TX_INT_DISABLE);
    if (ble_stream_context->stats[stream].tx_queued != 0U)
    {
      ble_stream_context->stats[stream].tx_queued--;
    }
    ble_stream_context->stats[stream].tx_dropped_messages++;
    ble_stream_context->stats[stream].tx_dropped_bytes += dropped;
    (void)tx_interrupt_control(posture);
  }
  while (tx_queue_receive(ready_queue, &slot, TX_NO_WAIT) == TX_SUCCESS)
  {
    uint32_t dropped = (stream == WIFI_BLE_STREAM_CLI) ?
        ((WifiBle_CliTxSlot_t *)slot)->length :
        ((WifiBle_DebugTxSlot_t *)slot)->length;
    (void)tx_queue_send(free_queue, &slot, TX_NO_WAIT);
    posture = tx_interrupt_control(TX_INT_DISABLE);
    if (ble_stream_context->stats[stream].tx_queued != 0U)
    {
      ble_stream_context->stats[stream].tx_queued--;
    }
    ble_stream_context->stats[stream].tx_dropped_messages++;
    ble_stream_context->stats[stream].tx_dropped_bytes += dropped;
    (void)tx_interrupt_control(posture);
  }
}

static W6X_Status_t ble_configure_gatt_server(void)
{
  W6X_Status_t status;
  uint8_t address[W6X_BLE_BD_ADDR_SIZE] = {0};
  char device_name[W6X_BLE_DEVICE_NAME_SIZE] = {0};

  ble_init_stage = WIFI_BLE_INIT_STAGE_ADDRESS;
  status = W6X_Ble_GetBDAddress(address);
  ble_last_status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE address read failed: %" PRIi32 "\r\n", status);
    return status;
  }

  (void)snprintf(device_name, sizeof(device_name), "N6-MAINT-%02X%02X",
                 address[4], address[5]);
  ble_init_stage = WIFI_BLE_INIT_STAGE_DEVICE_NAME;
  status = W6X_Ble_SetDeviceName(device_name);
  ble_last_status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE device-name setup failed: %" PRIi32 "\r\n", status);
    return status;
  }
  (void)memcpy(ble_device_name, device_name, sizeof(ble_device_name));
  (void)memcpy(ble_address, address, sizeof(ble_address));

  ble_init_stage = WIFI_BLE_INIT_STAGE_TX_POWER;
  status = W6X_Ble_SetTxPower(0U);
  ble_last_status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE TX-power setup failed: %" PRIi32 "\r\n", status);
    return status;
  }
  ble_init_stage = WIFI_BLE_INIT_STAGE_ADV_DATA;
  status = W6X_Ble_SetAdvData(BLE_ADV_DATA);
  ble_last_status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE advertising-data setup failed: %" PRIi32 "\r\n", status);
    return status;
  }
  ble_init_stage = WIFI_BLE_INIT_STAGE_CLI_SERVICE;
  status = W6X_Ble_CreateService(BLE_CLI_SERVICE_INDEX,
                                 BLE_CLI_SERVICE_UUID,
                                 W6X_BLE_UUID_TYPE_128);
  ble_last_status = status;
  if (status == W6X_STATUS_OK)
  {
    ble_init_stage = WIFI_BLE_INIT_STAGE_DEBUG_SERVICE;
    status = W6X_Ble_CreateService(BLE_DEBUG_SERVICE_INDEX,
                                   BLE_DEBUG_SERVICE_UUID,
                                   W6X_BLE_UUID_TYPE_128);
    ble_last_status = status;
  }
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE service creation failed: %" PRIi32 "\r\n", status);
    return status;
  }

  ble_init_stage = WIFI_BLE_INIT_STAGE_CHARACTERISTICS;
  for (size_t i = 0U;
       i < (sizeof(ble_characteristics) / sizeof(ble_characteristics[0]));
       ++i)
  {
    status = W6X_Ble_CreateCharacteristic(
        ble_characteristics[i].service_index,
        ble_characteristics[i].char_index,
        ble_characteristics[i].uuid,
        W6X_BLE_UUID_TYPE_128,
        ble_characteristics[i].properties,
        ble_characteristics[i].permissions);
    ble_last_status = status;
    if (status != W6X_STATUS_OK)
    {
      LogError("ST67W6X BLE %s characteristic creation failed: %" PRIi32 "\r\n",
               ble_characteristics[i].description, status);
      return status;
    }
  }

  ble_init_stage = WIFI_BLE_INIT_STAGE_REGISTER;
  status = W6X_Ble_RegisterCharacteristics();
  ble_last_status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE characteristic registration failed: %" PRIi32 "\r\n", status);
    return status;
  }

  /* Development-stage Just Works capability.  This configures GAP I/O
   * capability but does not authorize firmware installation or XMODEM. */
  ble_init_stage = WIFI_BLE_INIT_STAGE_SECURITY;
  status = W6X_Ble_SetSecurityParam(W6X_BLE_SEC_IO_NO_INPUT_OUTPUT);
  ble_last_status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE security-parameter setup failed: %" PRIi32 "\r\n", status);
    return status;
  }

  ble_init_stage = WIFI_BLE_INIT_STAGE_ADV_START;
  status = W6X_Ble_AdvStart();
  ble_last_status = status;
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE advertising start failed: %" PRIi32 "\r\n", status);
    return status;
  }

  ble_gatt_ready = 1U;
  ble_advertising = 1U;
  ble_init_stage = WIFI_BLE_INIT_STAGE_READY;
  LogInfo("ST67W6X BLE: %s, CLI/DEBUG UART and ToF image notifications registered.\r\n",
          device_name);
  return W6X_STATUS_OK;
}

static void ble_process_pending_events(void)
{
  if (ble_stream_flush_pending != 0U)
  {
    ble_stream_flush_pending = 0U;
    ble_stream_purge_stale();
  }

  if (ble_disconnect_request != 0U)
  {
    W6X_Status_t status;
    uint32_t handle = ble_connection_handle;
    ble_disconnect_request = 0U;
    if ((ble_connected != 0U) && (handle != 0xFFU))
    {
      status = W6X_Ble_Disconnect(handle);
      if (status != W6X_STATUS_OK)
      {
        LogError("ST67W6X BLE disconnect request failed: %" PRIi32 "\r\n",
                 status);
      }
    }
  }

  if (ble_adv_request != BLE_ADV_REQUEST_NONE)
  {
    W6X_Status_t status;
    uint32_t requested_state = ble_adv_request;
    ble_adv_request = BLE_ADV_REQUEST_NONE;
    if (ble_connected != 0U)
    {
      LogWarn("ST67W6X BLE advertising request ignored while connected.\r\n");
    }
    else
    {
      status = (requested_state != 0U) ? W6X_Ble_AdvStart() :
                                        W6X_Ble_AdvStop();
      if (status == W6X_STATUS_OK)
      {
        ble_advertising = requested_state;
      }
      else
      {
        LogError("ST67W6X BLE advertising request failed: %" PRIi32 "\r\n",
                 status);
      }
    }
  }

  if (ble_connect_pending != 0U)
  {
    W6X_Status_t mtu_status;
    W6X_Status_t conn_status;
    uint32_t handle = ble_connection_handle;
    ble_connect_pending = 0U;

    LogInfo("ST67W6X BLE connected (handle %" PRIu32 ").\r\n", handle);
    mtu_status = W6X_Ble_ExchangeMTU(handle);
    conn_status = W6X_Ble_SetConnParam(handle, 12U, 24U, 0U, 400U);
    if (mtu_status != W6X_STATUS_OK)
    {
      LogWarn("ST67W6X BLE MTU exchange request failed: %" PRIi32 "\r\n",
              mtu_status);
    }
    if (conn_status != W6X_STATUS_OK)
    {
      LogWarn("ST67W6X BLE connection-parameter request failed: %" PRIi32 "\r\n",
              conn_status);
    }
  }

  if (ble_restart_advertising_pending != 0U)
  {
    W6X_Status_t status;
    ble_restart_advertising_pending = 0U;
    LogInfo("ST67W6X BLE disconnected; restarting advertising.\r\n");
    status = W6X_Ble_AdvStart();
    if (status == W6X_STATUS_OK)
    {
      ble_advertising = 1U;
    }
    else
    {
      LogError("ST67W6X BLE advertising restart failed: %" PRIi32 "\r\n",
               status);
    }
  }

  /* One ATT fragment per stream and manager cycle is the notification-credit
   * window.  It bounds module call time and prevents the image stream from
   * monopolizing CLI/XMODEM while keeping every W6X send in this owner thread. */
  ble_stream_process_tx(WIFI_BLE_STREAM_CLI);
  ble_stream_process_tx(WIFI_BLE_STREAM_DEBUG);
  ble_tof_image_process_tx();
}
#endif

static void error_callback(W6X_Status_t status, const char *function_name)
{
  LogError("ST67W6X error in %s: %" PRIi32 "\r\n",
           (function_name != NULL) ? function_name : "?", status);
}

static void log_output(const char *message)
{
  if (message != NULL)
  {
    (void)Debug_UART_Write(message, strlen(message));
  }
}
