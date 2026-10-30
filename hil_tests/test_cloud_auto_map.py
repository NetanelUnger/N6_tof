"""Actual Cloud publication function under automatic-map on/off build modes."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT, run_native
PREFIX=r'''
#include <assert.h>
#include <stdio.h>
typedef unsigned UINT;
#define TX_INT_DISABLE 1
#define CLOUD_RECORD_MAGIC 123U
#define CLOUD_HTTP_NONE 0U
#define TOF_STREAM_CLOUD 3U
typedef struct {unsigned paired,enabled,input_ready,output_queued,request_active,control_queued,control_high_water,control_rejected;} Status;
static struct {Status status;struct{unsigned magic;}pairing;unsigned input_ready,output_count,http_kind;} context,*cloud=&context;
static Status cloud_status_snapshot;
static struct{unsigned tx_queue_enqueued;}cloud_control_queue;
static unsigned cloud_control_high_water,cloud_control_rejected,requested,released;
static UINT tx_interrupt_control(UINT x){return x;}
static void TOF_App_RequestStream(unsigned x){assert(x==3);requested++;}
static void TOF_App_ReleaseStream(unsigned x){assert(x==3);released++;}
'''
TEST=r'''
int main(void){
 cloud->pairing.magic=CLOUD_RECORD_MAGIC;cloud->status.enabled=1;cloud->input_ready=1;
 cloud_publish_status();assert(cloud_status_snapshot.paired&&cloud_status_snapshot.enabled&&cloud_status_snapshot.input_ready);
#if APP_CLOUD_AUTO_MAP_ENABLED
 assert(requested==1);
#else
 assert(requested==0);
#endif
 unsigned before=requested;cloud_publish_status();assert(requested==before&&!released);
 cloud->status.enabled=0;cloud_publish_status();assert(released==1&&!cloud_status_snapshot.enabled);
 cloud->status.enabled=1;cloud_publish_status();
#if APP_CLOUD_AUTO_MAP_ENABLED
 assert(requested==before+1);
#else
 assert(!requested);
#endif
 cloud->pairing.magic=0;cloud_publish_status();assert(!cloud_status_snapshot.paired&&released==2);
 puts("PASS actual Cloud publication mode: image opt-in and CLI readiness independent; disable/unpair release preserved");return 0;}
'''
if __name__=='__main__':
 source=(ROOT/'AppliNonSecure/Core/Src/cloud_relay.c').read_text()
 for mode in (0,1):run_native('#define APP_CLOUD_AUTO_MAP_ENABLED '+str(mode)+'\n'+PREFIX+function(source,'cloud_publish_status')+TEST)
