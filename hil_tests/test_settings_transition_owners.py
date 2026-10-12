"""Actual Cloud preparation dispatcher and public-only Wi-Fi reference snapshot."""
from test_cloud_settings_control import MOCK
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT,run_native

CLOUD_BOUNDARY = r'''
static unsigned prepare_calls,reference_valid=1;
static AppSettings_Result prepare_result=APP_SETTINGS_OK;
static unsigned WIFI_BLE_App_GetRetainedWifiReference(char*s,uint32_t*d){
 assert(!cloud->gate);if(!reference_valid)return 0;strcpy(s,"synthetic-reference");*d=1;return 1;}
static AppSettings_Result AppSettings_PrepareCloudTransition(const char*s,uint32_t d){
 assert(!cloud->gate && !strcmp(s,"synthetic-reference") && d==1);++prepare_calls;
 if(prepare_result==APP_SETTINGS_OK)load_result=APP_SETTINGS_ABSENT;return prepare_result;}
static void idle(void){reset();context.status.paired=context.reply.active=context.input_ready=context.output_count=0;
 context.pairing.magic=0;prepare_calls=0;prepare_result=APP_SETTINGS_OK;reference_valid=1;}
int main(void){
 idle();assert(CloudRelay_RequestSettingsTransition()==TX_SUCCESS && queue_calls==1);
 CloudControlRequest_t request={CLOUD_CONTROL_SETTINGS_TRANSITION,0,{0}};
 assert(cloud_apply_control(&request)==TX_SUCCESS && prepare_calls==1 && !save_calls && !close_calls);
 assert(CloudRelay_RequestPair("123456")==TX_SUCCESS);context.pair_pending=1;
 assert(CloudRelay_RequestPair("123456")==TX_NOT_AVAILABLE);
 for(unsigned i=0;i<6;++i){idle();
  if(i==0)context.status.paired=1;if(i==1)context.pair_pending=1;if(i==2)context.http_kind=1;
  if(i==3)context.reply.active=1;if(i==4)context.input_ready=1;if(i==5)context.output_count=1;
  assert(cloud_apply_control(&request)==TX_SUCCESS && !prepare_calls && context.status.request_errors==1);
  assert(!save_calls && !close_calls && !release_calls);}
 idle();reference_valid=0;assert(cloud_apply_control(&request)==TX_SUCCESS && !prepare_calls);
 idle();prepare_result=APP_SETTINGS_BUSY;assert(cloud_apply_control(&request)==TX_NOT_AVAILABLE && !context.status.request_errors);
 prepare_result=APP_SETTINGS_IO;assert(cloud_apply_control(&request)==TX_SUCCESS && context.status.request_errors==1);
 idle();request.kind=CLOUD_CONTROL_PAIR;strcpy(request.code,"123456");
 for(unsigned i=0;i<3;++i){idle();
  if(i==0)policy=0;if(i==1)context.status.paired=1;if(i==2)context.pair_pending=1;
  assert(cloud_apply_control(&request)==TX_SUCCESS && context.status.request_errors==1 && !context.pair_code[0]);}
 puts("PASS only idle unpaired Cloud owner prepares; no gate/network/pairing call; paired/pending/owned reply blocked, BUSY deferred");
 puts("PASS stale queued pairing admission rechecked at the worker; consumed arm/paired/pending cannot start another exchange");
 return 0;
}
'''

WIFI_BOUNDARY = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#define WIFI_BLE_WIFI_SSID_SIZE 33
#define TX_INT_DISABLE 1
#define WIFI_BLE_STATE_READY 3
#define TX_SUCCESS 0
#define APP_SETTINGS_TRANSITION_ENABLED 1
#define WIFI_BLE_WIFI_OPERATION_CONNECT 1
#define WIFI_BLE_WIFI_OPERATION_DISCONNECT 2
typedef unsigned UINT;
typedef unsigned WifiBle_WifiOperation_t;
static unsigned cancelled;
static void AppSettings_Cancel(void){++cancelled;}
typedef struct {struct {unsigned operation_active;char ssid[33];}status;struct {unsigned tx_queue_enqueued;}request_ready;}WifiBle_WifiControlContext_t;
static WifiBle_WifiControlContext_t context;
static struct {struct {WifiBle_WifiControlContext_t*wifi_control_context;}queues;
 struct {unsigned state,wifi_state_confirmed,wifi_has_ip;}shadow;}radio_manager;
static struct {unsigned state;}radio_recovery;
static unsigned wifi_credentials_saved,wifi_connection_desired,wifi_unified_settings;
static uint8_t wifi_desired_ssid[33];
static UINT tx_interrupt_control(UINT p){return p;}
static void AppSettings_Scrub(void*p,size_t n){memset(p,0,n);}
static void ready(void){memset(&context,0,sizeof context);memset(&radio_manager,0,sizeof radio_manager);
 radio_manager.queues.wifi_control_context=&context;radio_manager.shadow.state=3;
 radio_manager.shadow.wifi_state_confirmed=radio_manager.shadow.wifi_has_ip=1;
 wifi_credentials_saved=wifi_connection_desired=1;wifi_unified_settings=radio_recovery.state=0;
 memset(wifi_desired_ssid,0,sizeof wifi_desired_ssid);strcpy((char*)wifi_desired_ssid,"synthetic-ssid");strcpy(context.status.ssid,"synthetic-ssid");}
'''
WIFI_TEST = r'''
int main(void){char out[33];uint32_t desired=0;
 ready();assert(WIFI_BLE_App_GetRetainedWifiReference(out,&desired) && desired && !strcmp(out,"synthetic-ssid"));
 for(unsigned i=0;i<10;++i){ready();
  if(i==0)wifi_credentials_saved=0;if(i==1)wifi_connection_desired=0;if(i==2)wifi_unified_settings=1;
  if(i==3)radio_recovery.state=1;if(i==4)radio_manager.shadow.state=0;if(i==5)radio_manager.shadow.wifi_state_confirmed=0;
  if(i==6)radio_manager.shadow.wifi_has_ip=0;if(i==7)context.status.operation_active=1;
  if(i==8)context.request_ready.tx_queue_enqueued=1;if(i==9)context.status.ssid[0]='x';
  memset(out,0x5a,sizeof out);desired=1;
  assert(!WIFI_BLE_App_GetRetainedWifiReference(out,&desired) && !desired);
  for(unsigned j=0;j<sizeof out;++j)assert(!out[j]);
 }
 ready();assert(!WIFI_BLE_App_GetRetainedWifiReference(NULL,&desired));
 wifi_cancel_settings_on_request(1,1);wifi_cancel_settings_on_request(0,0);assert(!cancelled);
 wifi_cancel_settings_on_request(0,1);wifi_cancel_settings_on_request(0,2);assert(cancelled==2);
 puts("PASS public SSID/intent snapshot requires confirmed idle retained-reference state; ten stale/ownership states return scrubbed outputs; no AT/password access");
 puts("PASS candidate accepted connect/disconnect retires prepared intent; rejected request/scan does not cancel");
 return 0;}
'''

def main():
    header=(ROOT/'AppliNonSecure/Core/Inc/app_settings.h').read_text()
    cloud=(ROOT/'AppliNonSecure/Core/Src/cloud_relay.c').read_text()
    mock=MOCK.replace('r->kind==CLOUD_CONTROL_UNPAIR)', 'r->kind==CLOUD_CONTROL_UNPAIR || r->kind==CLOUD_CONTROL_SETTINGS_TRANSITION)')
    functions='\n'.join(function(cloud,n) for n in ('cloud_clear_pairing','cloud_save_pairing','cloud_apply_control','CloudRelay_RequestSettingsTransition','CloudRelay_RequestPair'))
    split=CLOUD_BOUNDARY.index('int main(void)')
    run_native('#define APP_SETTINGS_TRANSITION_ENABLED 1\n#define APP_SETTINGS_WRITES_ENABLED 1\n'+header+mock+CLOUD_BOUNDARY[:split]+functions+CLOUD_BOUNDARY[split:])
    wifi=(ROOT/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    run_native(WIFI_BOUNDARY+function(wifi,'WIFI_BLE_App_GetRetainedWifiReference')+function(wifi,'wifi_cancel_settings_on_request')+WIFI_TEST)

if __name__=='__main__':main()
