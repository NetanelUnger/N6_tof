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

#define WIFI_BLE_RX_BUFFER_SIZE (512U)

#define BLE_CLI_SERVICE_INDEX   (0U)
#define BLE_DEBUG_SERVICE_INDEX (1U)
#define BLE_RX_CHAR_INDEX       (0U)
#define BLE_TX_CHAR_INDEX       (1U)
#define BLE_ADV_REQUEST_NONE    (2U)

#define BLE_CLI_SERVICE_UUID    "7a1e0001b5a3f393e0a9e50e24dcca9e"
#define BLE_CLI_RX_UUID         "7a1e0002b5a3f393e0a9e50e24dcca9e"
#define BLE_CLI_TX_UUID         "7a1e0003b5a3f393e0a9e50e24dcca9e"
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
_Static_assert(W6X_BLE_MAX_CHAR_NBR >= 2U,
               "Each BLE maintenance service requires RX and TX");
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

static uint8_t ble_receive_buffer[WIFI_BLE_RX_BUFFER_SIZE];
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
static volatile uint32_t ble_rx_write_events;
static volatile uint32_t ble_rx_discarded_bytes;
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

  status = W6X_RegisterAppCb(&callbacks);
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X callback registration failed: %" PRIi32 "\r\n", status);
    goto error;
  }

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
  LogInfo("ST67W6X: CLI/DEBUG payload routing and wireless update are not enabled yet.\r\n");
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
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 20U);
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
  status->ble_rx_write_events = ble_rx_write_events;
  status->ble_rx_discarded_bytes = ble_rx_discarded_bytes;
  status->ble_init_stage = ble_init_stage;
  status->ble_last_status = ble_last_status;
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
      ble_connected = 1U;
      ble_advertising = 0U;
      ble_connection_handle = event->remote_ble_device.conn_handle;
      ble_connect_pending = 1U;
    }
  }
  else if (event_id == W6X_BLE_EVT_DISCONNECTED_ID)
  {
    ble_connected = 0U;
    ble_connect_pending = 0U;
    ble_connection_handle = 0xFFU;
    ble_cli_tx_subscribed = 0U;
    ble_debug_tx_subscribed = 0U;
    ble_mtu = 23U;
    ble_restart_advertising_pending = 1U;
  }
  else if ((event_id == W6X_BLE_EVT_NOTIFICATION_STATUS_ENABLED_ID) ||
           (event_id == W6X_BLE_EVT_NOTIFICATION_STATUS_DISABLED_ID))
  {
    uint32_t enabled =
        (event_id == W6X_BLE_EVT_NOTIFICATION_STATUS_ENABLED_ID) ? 1U : 0U;
    if ((event != NULL) && (event->charac_idx == BLE_TX_CHAR_INDEX))
    {
      if (event->service_idx == BLE_CLI_SERVICE_INDEX)
      {
        ble_cli_tx_subscribed = enabled;
      }
      else if (event->service_idx == BLE_DEBUG_SERVICE_INDEX)
      {
        ble_debug_tx_subscribed = enabled;
      }
    }
  }
  else if ((event_id == W6X_BLE_EVT_MTU_SIZE_ID) && (event != NULL))
  {
    ble_mtu = event->mtu_size;
  }
  else if ((event_id == W6X_BLE_EVT_WRITE_ID) && (event != NULL))
  {
    /* The GATT endpoints exist in this stage, but no byte stream is attached
     * yet.  Account for every dropped write so validation cannot mistake an
     * accepted ATT write for an operational CLI/debug transport. */
    ble_rx_write_events++;
    ble_rx_discarded_bytes += event->available_data_length;
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
  LogInfo("ST67W6X BLE: %s, CLI and DEBUG UART GATT services registered.\r\n",
          device_name);
  return W6X_STATUS_OK;
}

static void ble_process_pending_events(void)
{
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
