#include "wifi_ble_app.h"

#include <inttypes.h>
#include <string.h>

#include "app_features.h"
#include "debug_uart.h"
#include "logging.h"
#include "main.h"
#include "vl53l9_interface.h"
#include "spi_iface.h"
#include "w6x_api.h"

#define WIFI_BLE_RX_BUFFER_SIZE (512U)

static uint8_t ble_receive_buffer[WIFI_BLE_RX_BUFFER_SIZE];
static volatile WifiBle_State_t wifi_ble_state = WIFI_BLE_STATE_DISABLED;
static volatile uint32_t wifi_connected;
static volatile uint32_t wifi_has_ip;
static volatile uint32_t ble_connected;
static volatile uint32_t ble_advertising;
static volatile uint32_t ble_connection_handle;

static void wifi_event_callback(W6X_event_id_t event_id, void *event_args);
static void ble_event_callback(W6X_event_id_t event_id, void *event_args);
static void error_callback(W6X_Status_t status, const char *function_name);
static void log_output(const char *message);

void WIFI_BLE_App_Run(void)
{
  W6X_Status_t status;
  static W6X_App_Cb_t callbacks = {
    .APP_wifi_cb = wifi_event_callback,
    .APP_net_cb = NULL,
    .APP_mqtt_cb = NULL,
    .APP_ble_cb = ble_event_callback,
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

  status = W6X_WiFi_Init();
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X Wi-Fi initialization failed: %" PRIi32 "\r\n", status);
    goto error;
  }

  (void)memset(ble_receive_buffer, 0, sizeof(ble_receive_buffer));
  status = W6X_Ble_Init(W6X_BLE_MODE_SERVER, ble_receive_buffer,
                        sizeof(ble_receive_buffer) - 1U);
  if (status != W6X_STATUS_OK)
  {
    LogError("ST67W6X BLE initialization failed: %" PRIi32 "\r\n", status);
    goto error;
  }

  wifi_ble_state = WIFI_BLE_STATE_READY;
  LogInfo("ST67W6X: Wi-Fi station and BLE server are ready.\r\n");
  LogInfo("ST67W6X: no credentials or OTA service are enabled yet.\r\n");

  for (;;)
  {
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND);
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
  status->ble_connected = ble_connected;
  status->ble_advertising = ble_advertising;
  status->ble_connection_handle = ble_connection_handle;
}

void WIFI_BLE_App_SetAdvertisingState(uint32_t advertising)
{
  ble_advertising = (advertising != 0U) ? 1U : 0U;
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

static void ble_event_callback(W6X_event_id_t event_id, void *event_args)
{
  if (event_id == W6X_BLE_EVT_CONNECTED_ID)
  {
    W6X_Ble_CbParamData_t *event = (W6X_Ble_CbParamData_t *)event_args;
    ble_connected = 1U;
    ble_advertising = 0U;
    if (event != NULL)
    {
      ble_connection_handle = event->remote_ble_device.conn_handle;
    }
    LogInfo("ST67W6X BLE connected.\r\n");
  }
  else if (event_id == W6X_BLE_EVT_DISCONNECTED_ID)
  {
    ble_connected = 0U;
    ble_connection_handle = 0U;
    LogInfo("ST67W6X BLE disconnected.\r\n");
  }
}

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
