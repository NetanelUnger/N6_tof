#ifndef WIFI_BLE_APP_H
#define WIFI_BLE_APP_H

#include <stdint.h>

#include "tx_api.h"

#define WIFI_BLE_DEVICE_NAME_SIZE (26U)
#define WIFI_BLE_ADDRESS_SIZE     (6U)

typedef enum
{
  WIFI_BLE_STATE_DISABLED = 0,
  WIFI_BLE_STATE_STARTING,
  WIFI_BLE_STATE_READY,
  WIFI_BLE_STATE_ERROR
} WifiBle_State_t;

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

typedef struct
{
  WifiBle_State_t state;
  uint32_t wifi_connected;
  uint32_t wifi_has_ip;
  uint32_t ble_gatt_ready;
  uint32_t ble_connected;
  uint32_t ble_advertising;
  uint32_t ble_connection_handle;
  uint32_t ble_mtu;
  uint32_t ble_cli_tx_subscribed;
  uint32_t ble_debug_tx_subscribed;
  uint32_t ble_rx_write_events;
  uint32_t ble_rx_discarded_bytes;
  uint32_t ble_init_stage;
  int32_t ble_last_status;
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

void WIFI_BLE_App_ConfigureHardware(void);
void WIFI_BLE_App_Run(void);
WifiBle_State_t WIFI_BLE_App_GetState(void);
void WIFI_BLE_App_GetRuntimeStatus(WifiBle_RuntimeStatus_t *status);
void WIFI_BLE_App_GetHardwareStatus(WifiBle_HardwareStatus_t *status);
UINT WIFI_BLE_App_RequestAdvertising(uint32_t advertising);
UINT WIFI_BLE_App_RequestDisconnect(void);

#endif /* WIFI_BLE_APP_H */
