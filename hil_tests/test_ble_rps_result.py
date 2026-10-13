"""Actual Radio result sender: minimum MTU, pinned scores, age and backpressure."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT, run_native

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct {uint32_t enabled,ready,last_frame,runs,errors,inference_ms,last_result_tick;int32_t last_error;uint16_t confidence_per_mille;uint8_t class_id;int8_t scores[4];}RPS_AI_Status_t;
#define RPS_AI_CLASS_COUNT 4
#define BLE_DEBUG_SERVICE_INDEX 1
#define BLE_RPS_RESULT_CHAR_INDEX 2
#define W6X_STATUS_BUSY 1
#define W6X_STATUS_OK 0
typedef int W6X_Status_t;
static struct {struct {uint32_t ble_session_generation,ble_connected,ble_rps_subscribed;}shadow;struct {uint32_t notify_source;}work;}radio_manager;
static struct {char line[192];uint32_t generation,sample_tick,due;uint16_t length,offset;}ble_rps;
static uint32_t now,mtu,busy,active,failed;static RPS_AI_Status_t sample;static char received[512];static unsigned used;
static uint32_t HAL_GetTick(void){return now;}
static uint32_t Firmware_Update_IsActive(void){return active;}
static void RPS_AI_GetStatus(RPS_AI_Status_t*s){*s=sample;}
static const char *RPS_AI_ClassName(uint8_t c){return ((const char*[]){"none","rock","paper","scissors"})[c];}
static uint32_t ble_att_payload_size(void){return mtu;}
static W6X_Status_t ble_notify_fragment(uint32_t source,uint8_t srv,uint8_t chr,const void*d,uint32_t n,uint32_t*sent){assert(source==5 && srv==1 && chr==2 && n && n<=mtu);*sent=0;if(busy)return 1;if(failed)return 2;assert(used+n<sizeof received);memcpy(received+used,d,n);used+=n;received[used]=0;*sent=n;return 0;}
static void reset(void){memset(&ble_rps,0,sizeof ble_rps);memset(received,0,sizeof received);used=busy=failed=active=0;now=1000;mtu=20;sample=(RPS_AI_Status_t){.enabled=1,.ready=1,.last_frame=65535,.runs=17,.last_result_tick=990,.class_id=2,.confidence_per_mille=996,.scores={-128,-127,127,-128}};radio_manager.shadow.ble_connected=radio_manager.shadow.ble_rps_subscribed=1;radio_manager.shadow.ble_session_generation=7;}
'''
TEST = r'''
int main(void){
 reset();ble_rps_process_tx();assert(used==20);sample.class_id=1;sample.confidence_per_mille=4;
 while(ble_rps.length){now+=10;ble_rps_process_tx();}
 assert(strstr(received,"\"c\":\"paper\"") && strstr(received,"\"p\":996") && strstr(received,"\"f\":65535") && received[used-1]=='\n');
 char*age=strstr(received,"\"a\":\"")+5;assert(strtoul(age,0,10)==now-990);
 unsigned old=used;ble_rps_process_tx();assert(used==old);now+=500;ble_rps_process_tx();assert(used>old);
 puts("PASS MTU20 fragments pin real scores/frame and refresh unsplit age footer; rate bounded at 2Hz");
 reset();busy=1;ble_rps_process_tx();assert(!used);now+=3000;busy=0;while(!used || ble_rps.length)ble_rps_process_tx();assert(strstr(received,"0000003010"));
 puts("PASS backpressure cannot advertise an old result with age zero");
 reset();sample.enabled=0;mtu=244;ble_rps_process_tx();assert(strstr(received,"\"ok\":0") && strstr(received,"unknown"));
 reset();sample.last_error=5;mtu=244;ble_rps_process_tx();assert(strstr(received,"\"ok\":0"));
 reset();sample.runs=0;mtu=244;ble_rps_process_tx();assert(strstr(received,"\"ok\":0"));
 reset();now=3000;mtu=244;ble_rps_process_tx();assert(strstr(received,"\"ok\":0"));
 puts("PASS disabled/not-run/error/stale statuses are invalid without invented class or confidence");
 reset();ble_rps_process_tx();radio_manager.shadow.ble_rps_subscribed=0;ble_rps_process_tx();assert(!ble_rps.length);old=used;ble_rps_process_tx();assert(used==old);
 radio_manager.shadow.ble_rps_subscribed=1;radio_manager.shadow.ble_session_generation=8;ble_rps_process_tx();assert(ble_rps.generation==8);
 reset();active=1;ble_rps_process_tx();assert(!used);
 reset();sample.last_result_tick=UINT32_MAX-9;now=10;mtu=244;ble_rps_process_tx();assert(strstr(received,"0000000020"));
 puts("PASS unsubscribe, new connection, binary update exclusion and tick wrap");
 return 0;}
'''

if __name__ == '__main__':
    src=(ROOT/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    run_native(PREFIX.replace('#include <stdio.h>','#include <stdio.h>\n#include <stdlib.h>')+function(src.replace('static uint16_t ble_rps_format', 'static uint32_t ble_rps_format'),'ble_rps_format')+function(src,'ble_rps_process_tx')+TEST)


