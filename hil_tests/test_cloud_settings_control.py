"""Actual Cloud settings control: no provisioning/write before policy and ownership."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT,run_native

MOCK = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <ctype.h>
typedef unsigned UINT;
#define TX_SUCCESS 0
#define TX_NOT_AVAILABLE 1
#define TX_PTR_ERROR 2
#define TX_SIZE_ERROR 3
#define TX_OPTION_ERROR 4
#define TX_NO_WAIT 0
#define CLOUD_RELAY_PAIR_CODE_LENGTH 6
#define CLOUD_TOKEN_SIZE 1025
#define CLOUD_RECORD_MAGIC 0x434C364E
#define Debug_UART_Log(...) ((void)0)
enum {CLOUD_CONTROL_PAIR=1,CLOUD_CONTROL_ENABLE,CLOUD_CONTROL_RECONNECT,CLOUD_CONTROL_UNPAIR,CLOUD_CONTROL_SETTINGS_TRANSITION};
enum {CLOUD_HTTP_NONE,CLOUD_RELAY_STATE_CONNECTING,CLOUD_RELAY_STATE_UNPAIRED};
typedef struct {unsigned kind,value;char code[7];}CloudControlRequest_t;
typedef struct {unsigned magic,enabled;char device_id[65],workspace_id[65],token[1025];}Pairing;
static struct {int gate;Pairing pairing;struct {unsigned request_errors,enabled,paired,generation,backoff_seconds,state;
 char workspace_id[65],device_id[65];}status;
 char response[2400];unsigned http_kind;char pair_code[7],active_command_id[65];unsigned pair_pending,next_action_tick,address_valid,backoff_step,hold_command;
 struct {unsigned active;}reply;void *reply_owner;unsigned input_ready,input_delivered,ack_pending,output_count,output_head,output_tail;
}context,*cloud=&context;
static unsigned policy,queue_calls,published,close_calls,release_calls,clear_calls,save_calls;
static unsigned gate_busy,scrubs,json_fail,json_calls;
static AppSettings_Result load_result,clear_result,save_result;
unsigned AppSettings_WritesEnabled(void){return policy;}
void AppSettings_GetStatus(AppSettings_Status*s){memset(s,0,sizeof *s);s->result=load_result;}
AppSettings_Result AppSettings_ClearCloud(void){assert(!cloud->gate);++clear_calls;return clear_result;}
AppSettings_Result AppSettings_SaveCloud(const char*d,const char*w,const char*t,uint32_t e){
 assert(!cloud->gate && d==cloud->pairing.device_id && w==cloud->pairing.workspace_id && t==cloud->pairing.token && e==cloud->status.enabled);
 ++save_calls;return save_result;}
void AppSettings_Scrub(void*p,size_t n){volatile unsigned char*b=p;while(n--)*b++=0;++scrubs;}
static UINT tx_mutex_get(int*g,unsigned wait){assert(!wait && !*g);if(gate_busy)return 1;*g=1;return 0;}
static UINT tx_mutex_put(int*g){assert(*g);*g=0;return 0;}
static void cloud_close_socket(void){assert(!cloud->gate);++close_calls;}
static void cloud_release_tof(void){++release_calls;}
static void cloud_publish_status(void){assert(!cloud->gate);++published;}
static unsigned HAL_GetTick(void){return 123;}
static UINT cloud_submit_control(const CloudControlRequest_t*r){assert(r->kind==CLOUD_CONTROL_PAIR || r->kind==CLOUD_CONTROL_UNPAIR);++queue_calls;return 0;}
static int json_get_string(const uint8_t*b,size_t n,const char*k,char*out,size_t cap){
 (void)b;(void)n;assert(cap==65 || cap==1025);++json_calls;
 if(json_calls==json_fail)return -1;
 strcpy(out,!strcmp(k,"deviceId")?"synthetic-device":!strcmp(k,"workspaceId")?"synthetic-workspace":"synthetic-token");return 0;}
static void reset(void){memset(&context,0,sizeof context);cloud=&context;
 context.status.paired=1;context.status.enabled=1;context.pairing.magic=CLOUD_RECORD_MAGIC;
 context.reply_owner=&context;context.reply.active=1;context.input_ready=context.output_count=1;
 policy=1;queue_calls=published=close_calls=release_calls=clear_calls=save_calls=gate_busy=scrubs=json_fail=json_calls=0;
 load_result=clear_result=save_result=APP_SETTINGS_OK;}
'''
TESTS = r'''
int main(void){
 reset();policy=0;assert(CloudRelay_RequestPair("123456")==TX_NOT_AVAILABLE && !queue_calls);
 assert(CloudRelay_Unpair()==TX_NOT_AVAILABLE && !queue_calls);
 for(unsigned r=APP_SETTINGS_LEGACY;r<=APP_SETTINGS_UNSUPPORTED;++r){load_result=(AppSettings_Result)r;
  policy=1;assert(CloudRelay_RequestPair("123456")==TX_NOT_AVAILABLE && !queue_calls);}
 load_result=APP_SETTINGS_ABSENT;assert(CloudRelay_RequestPair("123456")==0 && queue_calls==1);
 assert(CloudRelay_RequestPair("12345")==TX_SIZE_ERROR);assert(CloudRelay_RequestPair("12345x")==TX_OPTION_ERROR);
 puts("PASS pairing/unpair admission rejects read-only and unvalidated stores before queue/network provisioning");
 for(unsigned r=APP_SETTINGS_LEGACY;r<=APP_SETTINGS_UNSUPPORTED;++r){reset();clear_result=(AppSettings_Result)r;
  CloudControlRequest_t request={CLOUD_CONTROL_UNPAIR,0,{0}};
  UINT result=cloud_apply_control(&request);
  assert(result==(r==APP_SETTINGS_BUSY?TX_NOT_AVAILABLE:TX_SUCCESS));
  assert(context.status.paired && context.reply.active && context.reply_owner==&context && context.input_ready && context.output_count);
  assert(!close_calls && !release_calls && !request.value && clear_calls==1);
  assert(context.status.request_errors==(r!=APP_SETTINGS_BUSY));}
 reset();gate_busy=1;CloudControlRequest_t request={CLOUD_CONTROL_UNPAIR,0,{0}};
 assert(cloud_apply_control(&request)==TX_NOT_AVAILABLE && request.value==1 && clear_calls==1 && context.status.paired);
 gate_busy=0;assert(cloud_apply_control(&request)==TX_SUCCESS && clear_calls==1);
 assert(!context.status.paired && !context.reply_owner && !context.reply.active && !context.input_ready && !context.output_count);
 puts("PASS failed/unavailable unpair preserves pairing/reply lease; verified tombstone once outside gate before retirement");
 reset();save_result=APP_SETTINGS_READ_ONLY;request.kind=CLOUD_CONTROL_ENABLE;request.value=0;
 assert(cloud_apply_control(&request)==TX_SUCCESS && !context.status.enabled && save_calls==1 && context.status.request_errors==1);
 reset();assert(cloud_save_pairing()==0 && save_calls==1);save_result=APP_SETTINGS_IO;
 assert(cloud_save_pairing()==-1 && save_calls==2);
 puts("PASS enable persistence failure reported; save success means verified adapter result; no FS call holds reply gate");
 for(unsigned f=1;f<=3;++f){reset();json_fail=f;assert(cloud_parse_pair_response(NULL,0)==-1 && scrubs==3 && context.pairing.magic==CLOUD_RECORD_MAGIC);}
 reset();assert(!cloud_parse_pair_response(NULL,0) && scrubs==3 && !strcmp(context.pairing.token,"synthetic-token"));
 puts("PASS parsed token working arrays scrubbed on every parse exit; no old-file deletion or raw binary persistence dependency");
 reset();memset(context.response,'t',sizeof context.response);strcpy(context.pair_code,"123456");
 context.pair_pending=1;cloud_complete_pairing(200,NULL,0);
 assert(context.status.paired && context.status.state==CLOUD_RELAY_STATE_CONNECTING && context.status.generation==1 && save_calls==1);
 for(unsigned i=0;i<sizeof context.response;++i)assert(!context.response[i]);assert(!context.pair_code[0] && !context.pair_pending);
 reset();save_result=APP_SETTINGS_IO;cloud_complete_pairing(200,NULL,0);
 assert(!context.status.paired && !context.pairing.token[0] && context.status.request_errors==1 && !context.status.generation);
 reset();json_fail=2;cloud_complete_pairing(200,NULL,0);assert(!context.status.paired && !save_calls && !context.pairing.token[0]);
 puts("PASS new pairing published only after verified persistence; response/code scrubbed; failed parse/store never uses volatile new access");
 return 0;
}
''' 
def main():
    source=(ROOT/'AppliNonSecure/Core/Src/cloud_relay.c').read_text()
    header=(ROOT/'AppliNonSecure/Core/Inc/app_settings.h').read_text()
    names=('cloud_clear_pairing','cloud_save_pairing','cloud_apply_control',
           'CloudRelay_RequestPair','CloudRelay_Unpair','cloud_parse_pair_response','cloud_complete_pairing')
    run_native(header+MOCK+'\n'.join(function(source,n) for n in names)+TESTS)
    assert 'W6X_FS_WriteFileByContent(' not in source and 'W6X_FS_DeleteFile(' not in source
    print('PASS application has no implicit legacy Cloud write/delete path')
if __name__=='__main__':main()
