"""Actual control-owner C: ordinary link loss, bounded retry and cancellation."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT, run_native

PREFIX = r'''
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef unsigned UINT;
#define TX_INT_DISABLE 1U
#define WIFI_BLE_STATE_READY 2U
#define WIFI_BLE_WIFI_OPERATION_CONNECT 1U
#define WIFI_BLE_WIFI_OPERATION_NONE 0U
typedef struct {struct {unsigned operation_active;}status;unsigned active_operation;struct {unsigned tx_queue_enqueued;}request_ready;}WifiBle_WifiControlContext_t;
typedef struct {struct {struct {unsigned tx_desynchronized,dns_drain_active;}handler_data;unsigned notify_phase;}Modem;}W61_Object_t;
static WifiBle_WifiControlContext_t context;
static W61_Object_t driver;
static unsigned no_driver,now,calls,succeed,busy_seen;
static struct {struct {unsigned wifi_has_ip,wifi_connected,wifi_state_confirmed,state;}shadow;
 struct {WifiBle_WifiControlContext_t *wifi_control_context;}queues;
 struct {unsigned wifi_service_started_ms,wifi_connect_call_active;}work;}radio_manager;
static struct {unsigned state;}radio_recovery;
static unsigned wifi_connection_desired,wifi_credentials_saved,wifi_link_restore_attempts,wifi_link_restore_last_ms,settings_busy;
static unsigned skip_sdk;
static unsigned AppSettings_IsBusy(void){return settings_busy;}
static W61_Object_t *W61_ObjGet(void){return no_driver?0:&driver;}
static unsigned HAL_GetTick(void){return now;}
static unsigned tx_interrupt_control(unsigned x){(void)x;return 0;}
static void Debug_UART_Log(const char*a,const char*b,...){(void)a;(void)b;}
static uint32_t wifi_restore_connection(void){assert(context.status.operation_active&&context.active_operation==1&&radio_manager.work.wifi_connect_call_active);if(skip_sdk)return 0;busy_seen++;calls++;now+=123;radio_manager.shadow.wifi_has_ip=succeed;radio_manager.work.wifi_connect_call_active=0;return 1;}
static void reset(void){memset(&context,0,sizeof context);memset(&driver,0,sizeof driver);memset(&radio_manager,0,sizeof radio_manager);radio_manager.queues.wifi_control_context=&context;radio_manager.shadow.state=2;radio_manager.shadow.wifi_state_confirmed=1;radio_recovery.state=0;wifi_connection_desired=wifi_credentials_saved=1;wifi_link_restore_attempts=wifi_link_restore_last_ms=0;now=calls=succeed=no_driver=busy_seen=0;}
'''
TESTS = r'''
int main(void){
 reset();succeed=1;wifi_link_restore_pump();assert(calls==1&&busy_seen==1&&!context.status.operation_active&&!context.active_operation&&!wifi_link_restore_attempts);
 puts("PASS ordinary confirmed link loss restores via existing owner and reports waiting during the call");
 reset();wifi_connection_desired=0;wifi_link_restore_attempts=3;wifi_link_restore_pump();assert(!calls&&!wifi_link_restore_attempts);
 puts("PASS explicit disconnect cancels automatic restoration");
 reset();wifi_credentials_saved=0;wifi_link_restore_pump();assert(!calls);
 reset();radio_manager.shadow.wifi_state_confirmed=0;wifi_link_restore_pump();assert(!calls);
 reset();radio_manager.shadow.wifi_connected=1;wifi_link_restore_pump();assert(!calls);
 reset();radio_recovery.state=2;wifi_link_restore_pump();assert(!calls);
 reset();radio_manager.shadow.state=1;wifi_link_restore_pump();assert(!calls);
 reset();no_driver=1;wifi_link_restore_pump();assert(!calls);
 reset();context.status.operation_active=1;wifi_link_restore_pump();assert(!calls);
 reset();context.request_ready.tx_queue_enqueued=1;wifi_link_restore_pump();assert(!calls&&!wifi_link_restore_attempts&&!radio_manager.work.wifi_connect_call_active);
 puts("PASS no credentials, unconfirmed state, DHCP, other work, missing driver and reset never submit");
 reset();driver.Modem.handler_data.tx_desynchronized=1;wifi_link_restore_pump();assert(!calls&&driver.Modem.handler_data.tx_desynchronized);
 reset();driver.Modem.handler_data.dns_drain_active=1;wifi_link_restore_pump();assert(!calls&&driver.Modem.handler_data.dns_drain_active);
 reset();driver.Modem.notify_phase=1;wifi_link_restore_pump();assert(!calls&&driver.Modem.notify_phase);
 reset();settings_busy=1;wifi_link_restore_pump();assert(!calls&&!wifi_link_restore_attempts);settings_busy=0;
 reset();skip_sdk=1;wifi_link_restore_pump();assert(!calls&&!wifi_link_restore_attempts&&!context.status.operation_active&&!radio_manager.work.wifi_connect_call_active);skip_sdk=0;
 puts("PASS true fence and owned DNS/BLE replies are preserved without retry submission");
 reset();wifi_link_restore_pump();assert(calls==1&&wifi_link_restore_attempts==1);now+=9999;wifi_link_restore_pump();assert(calls==1);now++;wifi_link_restore_pump();assert(calls==2);now+=10000;wifi_link_restore_pump();assert(calls==3&&wifi_link_restore_attempts==3);now+=100000;wifi_link_restore_pump();assert(calls==3);
 puts("PASS at most three attempts, spaced from call completion; no unbounded retry");
 radio_manager.shadow.wifi_has_ip=1;wifi_link_restore_pump();assert(!wifi_link_restore_attempts);radio_manager.shadow.wifi_has_ip=0;succeed=1;wifi_link_restore_pump();assert(calls==4);
 reset();now=UINT32_MAX-200;wifi_link_restore_pump();now+=10000;wifi_link_restore_pump();assert(calls==2);
 puts("PASS new successful-IP lifecycle and uptime wraparound keep retry admission correct");
 return 0;
}
'''

def main():
    source = (ROOT / 'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    run_native(PREFIX + function(source, 'wifi_link_restore_pump') + TESTS)
    worker = function(source.replace('void WIFI_BLE_App_WifiControlRun',
                                     'static void WIFI_BLE_App_WifiControlRun'),
                      'WIFI_BLE_App_WifiControlRun')
    assert worker.count('wifi_link_restore_pump();') == 2
    assert 'if (status == TX_QUEUE_EMPTY)\n      {\n        wifi_link_restore_pump();' in worker
    callback = function(source, 'wifi_event_callback')
    assert 'wifi_restore_connection' not in callback and 'wifi_link_restore_pump' not in callback
    print('PASS only existing worker performs restoration, after queued user work; callback only wakes')

if __name__ == '__main__':
    main()
