"""Actual Cloud worker: cooperative pause and post-reset socket/image ownership."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT, run_native

PREFIX=r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <setjmp.h>
#include <stdio.h>
typedef unsigned UINT,ULONG;
#define TX_INT_DISABLE 1U
#define TX_SUCCESS 0U
#define TX_NO_WAIT 0U
#define TX_OR 1U
#define TX_OR_CLEAR 1U
#define CLOUD_WAKE_FLAG 1U
#define CLOUD_WORKER_WAIT_TICKS 20U
#define CLOUD_HTTP_NONE 0U
typedef struct {unsigned kind;}CloudControlRequest_t;
static struct {int gate;int socket;unsigned http_kind,response_length,address_valid,ca_ready,time_configured,time_ready,close_retry_tick,backoff_step,next_action_tick,network_epoch,tof_pending;unsigned paired,enabled,output_count,hold_command;struct {unsigned worker_loops,worker_last_tick,worker_max_step_ms;}status;}context,*cloud=&context;
static unsigned cloud_recovery_pause,cloud_recovery_quiesced,cloud_recovery_reset_proven;
static unsigned cloud_network_epoch,cloud_prepared,cloud_initialized,cloud_network_ready,cloud_wifi_has_ip,cloud_events;
static unsigned settings_busy;static unsigned AppSettings_IsBusy(void){return settings_busy;}
static unsigned now,gate_available,network_calls,active_reader,release_count,pause_inside,published,passes,limit;
static jmp_buf stopped;
static UINT tx_interrupt_control(UINT n){(void)n;return 0;}
static unsigned HAL_GetTick(void){return now++;}
static int tx_mutex_get(int*g,unsigned t){(void)g;(void)t;return gate_available?0:1;}
static void tx_mutex_put(int*g){(void)g;}
static void tx_event_flags_set(unsigned*p,unsigned f,unsigned op){(void)p;(void)f;(void)op;}
static void tx_event_flags_get(unsigned*p,unsigned f,unsigned op,ULONG*out,unsigned t){(void)p;(void)f;(void)op;(void)out;(void)t;if(++passes==limit)longjmp(stopped,1);}
static UINT cloud_receive_control(CloudControlRequest_t*r){(void)r;return 1;}
static UINT cloud_apply_control(CloudControlRequest_t*r){(void)r;return 0;}
static void cloud_publish_status(void){published++;}
static void cloud_release_tof(void){assert(!active_reader);cloud->tof_pending=0;release_count++;}
void CloudRelay_PauseForRadioRecovery(void);
static void cloud_process(unsigned ip){(void)ip;active_reader=1;network_calls++;if(pause_inside){CloudRelay_PauseForRadioRecovery();assert(!cloud_recovery_quiesced);}active_reader=0;}
static void reset(void){memset(&context,0,sizeof context);cloud=&context;cloud_recovery_pause=cloud_recovery_quiesced=cloud_recovery_reset_proven=cloud_network_epoch=passes=now=network_calls=active_reader=release_count=pause_inside=published=0;gate_available=cloud_prepared=cloud_initialized=cloud_network_ready=cloud_wifi_has_ip=1;context.socket=4;context.tof_pending=context.paired=context.enabled=context.output_count=context.hold_command=1;context.address_valid=1;limit=1;}
static void run(void);
'''
TESTS=r'''
static void run(void){if(!setjmp(stopped))CloudRelay_Run();}
int main(void){
 reset();CloudRelay_PauseForRadioRecovery();assert(cloud_network_epoch==1 && !CloudRelay_IsRadioRecoveryQuiesced());
 run();assert(CloudRelay_IsRadioRecoveryQuiesced() && !network_calls && !cloud->tof_pending && cloud->socket==4);
 puts("PASS pause cancels network epoch; worker alone releases image after previous reader returns, retaining socket identity");
 CloudRelay_RadioResetComplete();gate_available=0;passes=0;run();assert(cloud->socket==4 && cloud_recovery_pause && cloud_recovery_reset_proven);
 puts("PASS busy Cloud gate preserves reset proof and old socket without unsafe field mutation");
 gate_available=1;passes=0;run();assert(cloud->socket==-1 && !cloud_recovery_pause && !cloud_recovery_reset_proven && !cloud->address_valid);
 assert(cloud->paired && cloud->enabled && cloud->output_count==1 && cloud->hold_command);
 puts("PASS hardware-reset proof retires descriptor/address while preserving pairing, enabled intent and command lease/output");
 passes=0;run();assert(network_calls==1);puts("PASS network work resumes only on the next worker pass");
 reset();settings_busy=1;run();assert(!network_calls && cloud->socket==4 && cloud->hold_command);
 CloudRelay_PauseForRadioRecovery();passes=0;run();assert(cloud_recovery_quiesced);settings_busy=0;
 puts("PASS settings owner defers Cloud network work without losing lease/socket; recovery pause still acknowledges");
 reset();pause_inside=1;run();assert(network_calls==1 && !cloud_recovery_quiesced);
 passes=0;run();assert(cloud_recovery_quiesced && network_calls==1);
 puts("PASS recovery request during network call cannot acknowledge until that call has returned");
 reset();cloud_initialized=0;CloudRelay_PauseForRadioRecovery();assert(CloudRelay_IsRadioRecoveryQuiesced());
 puts("PASS disabled/uninitialized Cloud has no reader to wait for");return 0;}
'''

def main():
    source=(ROOT/'AppliNonSecure/Core/Src/cloud_relay.c').read_text()
    run_native(PREFIX+'\n'.join(function(source,name) for name in (
        'CloudRelay_Run','CloudRelay_PauseForRadioRecovery','CloudRelay_IsRadioRecoveryQuiesced',
        'CloudRelay_RadioResetComplete'))+TESTS)

if __name__=='__main__':main()
