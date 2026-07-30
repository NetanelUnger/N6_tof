#ifndef WIFI_BLE_APP_H
#define WIFI_BLE_APP_H

#include <stdint.h>

#include "tx_api.h"

typedef enum
{
  WIFI_BLE_STATE_DISABLED = 0,
  WIFI_BLE_STATE_STARTING,
  WIFI_BLE_STATE_READY,
  WIFI_BLE_STATE_ERROR
} WifiBle_State_t;

typedef struct
{
  WifiBle_State_t state;
  uint32_t wifi_connected;
  uint32_t wifi_has_ip;
  uint32_t ble_connected;
  uint32_t ble_advertising;
  uint32_t ble_connection_handle;
} WifiBle_RuntimeStatus_t;

void WIFI_BLE_App_Run(void);
WifiBle_State_t WIFI_BLE_App_GetState(void);
void WIFI_BLE_App_GetRuntimeStatus(WifiBle_RuntimeStatus_t *status);
void WIFI_BLE_App_SetAdvertisingState(uint32_t advertising);

#endif /* WIFI_BLE_APP_H */
