"""Run actual recovery coordinator C against ownership/reset failure scenarios."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT, run_native

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
typedef unsigned UINT;typedef int W6X_Status_t;
#define APP_ST67W6X_ENABLED 1U
#define APP_ST67W6X_WIFI_SERVICES_ENABLED 1U
#define APP_ST67W6X_BLE_GATT_ENABLED 0U
#define APP_ST67W6X_CLOUD_RELAY_ENABLED 0U
#define TX_INT_DISABLE 1U
#define TX_SUCCESS 0U
#define TX_NOT_AVAILABLE 9U
#define TX_TIMER_TICKS_PER_SECOND 1000U
#define WIFI_BLE_STATE_READY 2U
#define WIFI_CONTROL_WORK_FLAG 8U
#define TX_OR 1U
#define pdTRUE 1U
#define W6X_STATUS_ERROR 2
#define W6X_STATUS_OK 0
#define CHIP_EN_GPIO_Port 0
#define CHIP_EN_Pin 0
#define GPIO_PIN_RESET 0
typedef struct modem_cmd_handler_data {bool tx_desynchronized,dns_drain_active;unsigned dns_drain_until,sem_tx_lock;} Handler;
typedef struct {struct {Handler handler_data;unsigned notify_phase;void *modem_task_handle;}Modem;}W61_Object_t;
typedef struct {unsigned state,attempts,successes,failures,started_ms,elapsed_ms,radio_quiesced,cloud_quiesced,stage,wifi_reconnect_required;int last_status;}WifiBle_RecoveryStatus_t;
static W61_Object_t driver;
static volatile WifiBle_RecoveryStatus_t radio_recovery;
static unsigned recovery_window_started,recovery_window_attempts,recovery_invalid_request_id;
static unsigned recovery_fault_test;
static unsigned trace_calls;
static void radio_capture_recovery_trace(void){++trace_calls;}
static int spi_transaction_faulted(void){return 0;}
static unsigned wifi_connection_desired;
static void wifi_restore_connection(void){}
static struct {struct {unsigned state,wifi_has_ip,wifi_connected,wifi_state_confirmed;}shadow;struct {unsigned wifi_last_request_id;}work;}radio_manager;
static unsigned settings_cancellations;static void AppSettings_Cancel(void){++settings_cancellations;}
static unsigned now,cloud_ack,mutex_available,spi_result,init_result,powered,destructions,inits,paused,logs;
static int radio_control_events;
static unsigned HAL_GetTick(void){return now;}static unsigned xTaskGetTickCount(void){return now;}
static W61_Object_t *W61_ObjGet(void){return &driver;}
static UINT tx_interrupt_control(UINT x){(void)x;return 0;}
static void tx_thread_sleep(unsigned x){now+=x;}
static void CloudRelay_PauseForRadioRecovery(void){paused++;}
static unsigned CloudRelay_IsRadioRecoveryQuiesced(void){return cloud_ack;}
static unsigned xSemaphoreTake(unsigned h,unsigned t){(void)h;(void)t;return mutex_available;}
static unsigned xSemaphoreGive(unsigned h){(void)h;return 1;}
static void tx_event_flags_set(void*p,unsigned f,unsigned op){(void)p;(void)f;(void)op;}
static void Debug_UART_Log(const char*a,const char*b,...){(void)a;(void)b;logs++;}
static int spi_transaction_quiesce(unsigned t){(void)t;return spi_result;}
static void vTaskDelete(void*t){(void)t;destructions++;}
static void W6X_WiFi_DeInit(void){assert(driver.Modem.handler_data.tx_desynchronized);destructions++;}
static void W6X_DeInit(void){destructions++;powered=0;}
static unsigned HAL_GPIO_ReadPin(unsigned p,unsigned n){(void)p;(void)n;return powered;}
static int W6X_Init(void){assert(!powered);inits++;powered=1;driver.Modem.handler_data.tx_desynchronized=false;return init_result;}
static int W6X_WiFi_Init(void){return 0;}static int wifi_enable_station_dhcp(void){return 0;}
static void wifi_refresh_status(void){}
static void CloudRelay_SetNetworkState(unsigned r,unsigned ip){(void)r;(void)ip;}
static void CloudRelay_RadioResetComplete(void){assert(inits && init_result==0);}
static void reset(void){trace_calls=0;memset(&driver,0,sizeof driver);memset((void*)&radio_recovery,0,sizeof radio_recovery);memset(&radio_manager,0,sizeof radio_manager);radio_manager.shadow.state=2;radio_manager.work.wifi_last_request_id=5;recovery_window_started=recovery_window_attempts=0;now=1000;cloud_ack=mutex_available=powered=1;spi_result=init_result=destructions=inits=paused=logs=0;driver.Modem.modem_task_handle=(void*)1;}
'''
TESTS = r'''
int main(void){
 reset();radio_recovery_pump();assert(!radio_recovery.state && !paused);
 driver.Modem.handler_data.dns_drain_active=true;driver.Modem.handler_data.dns_drain_until=2000;
 radio_recovery_pump();assert(!radio_recovery.state);
 puts("PASS ordinary contention and unexpired DNS drain do not trigger NCP reset");
 now=2000;radio_recovery_pump();assert(radio_recovery.state==1 && paused==1 && recovery_invalid_request_id==5);
 assert(!destructions && !inits);puts("PASS expired DNS requests coordinated barrier before hardware mutation");
 cloud_ack=0;radio_recovery_execute();assert(!destructions && radio_recovery.state==1);
 cloud_ack=1;radio_recovery.radio_quiesced=0;radio_recovery_execute();assert(!destructions);
 radio_recovery.radio_quiesced=1;mutex_available=0;radio_recovery_execute();assert(!destructions);
 mutex_available=1;driver.Modem.notify_phase=4;radio_recovery_execute();assert(!destructions);
 puts("PASS Cloud, Radio, foreign AT lock and notification ownership each block teardown");
 driver.Modem.notify_phase=0;radio_recovery_execute();assert(!radio_recovery.state && radio_recovery.successes==1 && inits==1 && destructions==3);
 assert(radio_recovery.elapsed_ms>=100 && logs==2 && !driver.Modem.handler_data.tx_desynchronized);
 puts("PASS successful reset only clears fence through fresh initialization after power-off proof");
 reset();driver.Modem.handler_data.tx_desynchronized=true;radio_recovery_pump();spi_result=-1;radio_recovery_execute();
 assert(radio_recovery.state==3 && !destructions && !inits && driver.Modem.handler_data.tx_desynchronized);
 assert(WIFI_BLE_App_RequestRadioRecovery()!=0);puts("PASS failed SPI stop retains memory/fence and cannot retry unsafe partial lifecycle");
 reset();driver.Modem.handler_data.tx_desynchronized=true;radio_recovery_pump();cloud_ack=0;now+=35000;radio_recovery_execute();
 assert(radio_recovery.state==3 && !destructions);puts("PASS stalled Cloud acknowledgment is bounded and fails closed without reset");
 reset();WIFI_BLE_App_RequestRadioRecovery();radio_recovery_pump();init_result=2;radio_recovery_execute();
 assert(radio_recovery.state==3 && radio_recovery.failures==1 && inits==1);
 assert(WIFI_BLE_App_RequestRadioRecovery()!=0);puts("PASS fresh-init failure keeps admission closed without automatic reset loop");
 reset();WIFI_BLE_App_RequestRadioRecovery();radio_recovery_pump();recovery_window_attempts=3;radio_recovery_execute();
 assert(radio_recovery.state==3 && !destructions && !inits);puts("PASS three attempts per minute bounds repeated module resets");
 reset();recovery_window_started=UINT32_MAX-500;recovery_window_attempts=3;now=60000;WIFI_BLE_App_RequestRadioRecovery();radio_recovery_pump();radio_recovery_execute();
 assert(radio_recovery.successes==1 && recovery_window_attempts==1);puts("PASS reset budget recovers across tick wrap");
 reset();now=0;cloud_ack=0;WIFI_BLE_App_RequestRadioRecovery();radio_recovery_pump();
 assert(radio_recovery.stage==1 && !radio_recovery.started_ms && paused==1);
 now=20;radio_recovery.radio_quiesced=0;radio_recovery_pump();
 assert(paused==1 && !radio_recovery.started_ms && logs==1 && trace_calls==1);
 now=35000;radio_recovery_execute();
 assert(radio_recovery.state==3 && radio_recovery.elapsed_ms==35000 && !destructions);
 assert(WIFI_BLE_App_RequestRadioRecovery()==0 && !radio_recovery.stage);
 radio_recovery_pump();assert(paused==2 && radio_recovery.started_ms==35000);
 puts("PASS uptime zero starts one barrier with a bounded owner deadline; safe retry starts a new stage");
 return 0;}
'''

def main():
    source = (ROOT / 'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    run_native(PREFIX + '\n'.join(function(source, name) for name in (
        'WIFI_BLE_App_RequestRadioRecovery', 'radio_recovery_pump', 'radio_recovery_execute')) + TESTS)

if __name__ == '__main__':
    main()
