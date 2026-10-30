"""Focused actual-C tests; no hardware. Reuses the preserved native fixtures."""
from pathlib import Path
import sys,argparse,importlib.util
R=Path(__file__).resolve().parents[1]

sys.path.insert(0,str(R/'hil_tests'))
from test_wifi_scan_lifetime import run_native
from test_wifi_assoc_admission import extract_function
def load_fixture(name,relative):
    spec=importlib.util.spec_from_file_location(name,R/relative)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.ROOT=R
    return module
spi=load_fixture('spi_fixture','docs/st67-reliability-transport-candidate-20261029/test_st67_cp10.py')
at=load_fixture('at_fixture','docs/st67-reliability-at-timeout-candidate-20261029/test_st67_cp11.py')
def drain():
    text=(R/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c').read_text()
    code=at.timeout_case(text).split('int main(void)')[0]
    code=code.replace('tick+=wait;return 0;', 'tick+=wait;if(mode==4)inject_terminal();return 0;')
    return code+r'''
int main(void){
 reset();assert(command("AT+CWJAPS=TEST",300,0)==-ETIMEDOUT);
 assert(tick==300 && writes==1 && !held && data.dns_drain_active && !data.tx_desynchronized);
 assert(data.dns_drain_until==400 && modem_cmd_handler_wait_tx_ready(&data,0,true)==-EBUSY);
 assert(command("AT+CWSTATE?",10,0)==-ETIMEDOUT && writes==1);
 puts("PASS request returns its original timeout; next command cannot write during bounded terminal drain");
 inject_terminal();assert(!data.dns_drain_active && !data.tx_desynchronized);
 inject_terminal();assert(command("AT",5,0)==-ETIMEDOUT && writes==1);
 tick=data.tx_quiet_until;mode=2;
 assert(!command("AT+CWSTATE?",20,0) && writes==2 && !data.tx_desynchronized);
 puts("PASS late/queued duplicate terminal is retired before new command; fresh command needs its own response");
 reset();assert(command("AT",20,0)==-ETIMEDOUT);mode=3;inject_terminal();
 assert(!data.dns_drain_active && !data.tx_desynchronized);
 puts("PASS late explicit ERROR closes the failed request without an unnecessary reset");
 reset();assert(command("AT",20,0)==-ETIMEDOUT);tick=data.dns_drain_until;
 assert(modem_cmd_handler_wait_tx_ready(&data,0,true)==-EIO && data.tx_desynchronized);
 inject_terminal();assert(command("AT",20,0)==-EIO && writes==1);
 puts("PASS absent terminal expires once; even a later OK cannot clear a genuine fence");
 reset();mode=4;assert(command("AT",20,0)==-ETIMEDOUT);
 assert(!data.dns_drain_active && !data.tx_desynchronized && !held);
 puts("PASS terminal racing drain publication does not strand admission or change the timeout outcome");
 reset();assert(command("AT+CIPSEND=0,10",20,MODEM_TX_TRACK_RAW_WRITE)==-ETIMEDOUT);
 assert(data.tx_desynchronized && !data.dns_drain_active);
 reset();assert(command("AT+RAW",20,MODEM_NO_UNSET_CMDS)==-ETIMEDOUT && data.tx_desynchronized);
 puts("PASS prompt/payload transactions still fence immediately rather than guessing a safe boundary");
 reset();modem_cmd_handler_defer_tx(&data,10);assert(command("AT",10,0)==-ETIMEDOUT);
 assert(!writes && !data.tx_desynchronized && !data.dns_drain_active);
 reset();bus_failure=1;assert(command("AT",20,0)==-EBUSY && !data.tx_desynchronized);
 reset();bus_failure=2;assert(command("AT",20,0)==-EIO && data.tx_desynchronized);
 puts("PASS pre-wire timeout/BUSY remains local; partial write remains fenced");
 reset();assert(command("AT+FS=read",20,0)==-ETIMEDOUT && data.tx_desynchronized && !data.dns_drain_active);
 reset();assert(command("AT+CIPDOMAIN=example.invalid",2000,0)==-ETIMEDOUT && data.tx_desynchronized);
 puts("PASS unclassified binary FS and expired unscoped DNS cannot use plain-terminal recovery");
 reset();tick=UINT32_MAX-40;assert(command("AT",20,0)==-ETIMEDOUT);
 assert(data.dns_drain_until==79 && !data.tx_desynchronized);tick=78;inject_terminal();
 assert(!data.tx_desynchronized && !data.dns_drain_active);
 puts("PASS terminal grace and quiet period survive tick wrap");
 return 0;
}
'''

def ble_priority():
    src=(R/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    return r'''
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#define APP_ST67W6X_WIFI_SERVICES_ENABLED 1U
#define WIFI_BLE_STREAM_CLI 0U
#define W6X_STATUS_BUSY 1
#define W6X_STATUS_OK 0
#define BLE_NOTIFY_TIMEOUT_MS 1000
typedef int W6X_Status_t;
typedef struct {struct {unsigned rx_queued,tx_queued;}stats[1];struct{unsigned active;}reply;} WifiBle_StreamContext_t;
static WifiBle_StreamContext_t streams;
static struct{struct{unsigned notify_source,notify_length,notify_generation,wifi_connect_call_active;}work;
struct{unsigned ble_connection_handle,ble_session_generation;}shadow;
struct{WifiBle_StreamContext_t*ble_stream_context;}queues;}radio_manager;
static unsigned begins,polls,notification_sequence,notification_last_source;static int outcome,settings;
static int AppSettings_IsIoActive(void){return settings;}
static int W6X_Ble_ServerNotifyBegin(unsigned a,unsigned b,unsigned c,unsigned d,unsigned e){++begins;return 0;}
static int W6X_Ble_ServerNotifyPoll(const void*p,unsigned n,unsigned*s){++polls;*s=outcome==0?n:0;return outcome;}
''' +extract_function(src,'ble_notify_fragment')+r'''
int main(void){unsigned sent;char bytes[20]={0};radio_manager.queues.ble_stream_context=&streams;
streams.stats[0].rx_queued=1;assert(ble_notify_fragment(3,0,0,bytes,20,&sent)==1 && !begins);
streams.stats[0].rx_queued=0;streams.stats[0].tx_queued=2;
assert(ble_notify_fragment(3,0,0,bytes,20,&sent)==1 && !begins);
assert(!ble_notify_fragment(1,0,0,bytes,20,&sent) && begins==1);
streams.stats[0].tx_queued=0;streams.reply.active=1;
assert(ble_notify_fragment(5,0,0,bytes,20,&sent)==1 && begins==1);
puts("PASS image/NPU admission yields to queued command, queued reply and active reply; CLI progresses");
streams.reply.active=0;outcome=1;assert(ble_notify_fragment(3,0,0,bytes,20,&sent)==1 && begins==2);
streams.stats[0].tx_queued=1;assert(ble_notify_fragment(1,0,0,bytes,20,&sent)==1 && begins==2);
outcome=0;assert(!ble_notify_fragment(3,0,0,bytes,20,&sent) && begins==2);
assert(!ble_notify_fragment(1,0,0,bytes,20,&sent) && begins==3);
puts("PASS active raw image finishes exactly once before priority changes; no mid-transaction preemption");
return 0;}
'''

def cloud_priority():
    src=(R/'AppliNonSecure/Core/Src/cloud_relay.c').read_text()
    return r'''
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <assert.h>
#include <string.h>
#define CLOUD_RECORD_MAGIC 123U
#define NATI_LAB_FIRMWARE_VERSION_TEXT "test"
#define CLOUD_RELAY_STATE_UNPAIRED 1
#define CLOUD_HTTP_NONE 0
#define CLOUD_HTTP_PAIR 1
#define CLOUD_HTTP_POLL 2
#define CLOUD_HTTP_ACK 3
#define CLOUD_HTTP_OUTPUT 4
#define CLOUD_HTTP_TOF 5
typedef struct{unsigned binary,length,input_sequence,completed;char data[384];}CloudOutputSlot_t;
static struct{unsigned pair_pending,ack_pending,ack_sequence,output_count,output_head,hold_command,input_ready,tof_pending,image_yield_poll,next_action_tick;
char pair_code[8],ack_command_id[40],active_command_id[40];unsigned output_sequence;
struct{unsigned magic;}pairing;struct{char device_id[65];unsigned state,tof_frames_dropped;}status;
CloudOutputSlot_t output[1];char*tof_payload;unsigned tof_width,tof_height,tof_payload_length,tof_payload_crc32;char tof_header[40];
struct{unsigned payload_length,payload_crc32;}tof_info;}ctx,*cloud=&ctx;
static unsigned kind,backoffs,trainings,releases,fail;static const char*url;
static unsigned HAL_GetTick(void){return 0;}
static int cloud_begin_request(unsigned k,const char*m,const char*p,const char*c,const void*b,size_t n,const void*b2,size_t n2,unsigned a){kind=k;url=p;return fail?-1:0;}
static void cloud_backoff(void){++backoffs;}
static unsigned cloud_crc32(const void*p,size_t n){return 0;}
static int cloud_base64_encode(const void*p,size_t n,char*out,size_t max){strcpy(out,"x");return 1;}
static int cloud_json_escape(const void*p,size_t n,char*out,size_t max){strcpy(out,"x");return 1;}
static int cloud_training_next(void){++trainings;return 0;}
static int TofImage_Encode(void*p,size_t n,void*i){return 0;}
static void TofImage_Header(void*p,void*i,unsigned a,unsigned b){}
static void cloud_release_tof(void){++releases;cloud->tof_pending=0;}
static void reset(void){memset(&ctx,0,sizeof ctx);ctx.pairing.magic=123;kind=backoffs=trainings=releases=fail=0;}
''' +extract_function(src,'cloud_start_next_request')+r'''
int main(void){
reset();cloud->tof_pending=1;cloud_start_next_request();assert(kind==CLOUD_HTTP_TOF && releases==1);
cloud->tof_pending=1;cloud_start_next_request();assert(kind==CLOUD_HTTP_POLL && !strcmp(url,"/api/device/commands?waitSeconds=0") && cloud->tof_pending && !cloud->image_yield_poll);
cloud_start_next_request();assert(kind==CLOUD_HTTP_TOF && releases==2);
puts("PASS continuous camera alternates with command polls instead of starving new commands");
cloud->ack_pending=1;cloud_start_next_request();assert(kind==CLOUD_HTTP_ACK && cloud->image_yield_poll);
cloud->ack_pending=0;cloud->output_count=1;cloud_start_next_request();assert(kind==CLOUD_HTTP_OUTPUT && cloud->image_yield_poll);
cloud->output_count=0;fail=1;cloud_start_next_request();assert(kind==CLOUD_HTTP_POLL && backoffs==1 && cloud->image_yield_poll);
puts("PASS ACK/reply keep highest priority; failed poll retains bounded backoff rather than bypassing control");
reset();cloud_start_next_request();assert(kind==CLOUD_HTTP_POLL && !strcmp(url,"/api/device/commands?waitSeconds=1"));
puts("PASS idle path retains its existing long poll; no extra polling task or image buffer");
return 0;}
'''

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('suite');p.add_argument('--label',default='v1');a=p.parse_args()
    f={'drain':drain,'ble_priority':ble_priority,'cloud_priority':cloud_priority,
       'spi':lambda:spi.spi(R,True),'parser':lambda:spi.parser(R),
       'coordinator':lambda:spi.coordinator(R),'framing':lambda:spi.framing_suite(R),
       'shutdown':lambda:spi.shutdown_suite(R),'write_bridge':lambda:spi.write_bridge(R)}
    code=f[a.suite]();run_native(code)
