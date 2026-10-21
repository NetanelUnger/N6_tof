"""Production Cloud training state/ACK code with mocked network boundaries."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'hil_tests'))
from test_wifi_scan_lifetime import run_native

PREFIX=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <assert.h>
typedef unsigned UINT;
typedef int TOF_StreamDestination_t;
enum {TOF_STREAM_NONE,TOF_STREAM_USB,TOF_STREAM_BLE,TOF_STREAM_CLOUD};
enum {CLOUD_HTTP_NONE,CLOUD_HTTP_TRAIN_CONTROL=6,CLOUD_HTTP_TRAIN_FRAME=7};
#define TOF_IMAGE_TRAINING_N6DF 5
#define TX_INT_DISABLE 1
typedef struct {uint32_t active,attempts,acknowledged,failures,pending,goal,remaining_ms;char session[33];}CloudRelay_TrainingStatus_t;
static unsigned draining;
static unsigned now=100,route,dataset,cloud_wifi_has_ip=1,released,backoffs;
static char tof_capture_identity[33];
static struct {int http_kind;unsigned tof_pending,tof_frame_id,tof_payload_length;
  struct {unsigned mode,timestamp_ms,payload_crc32;}tof_info;uint8_t*tof_payload;
}mock,*cloud=&mock;
static uint32_t HAL_GetTick(void){return now;}
static UINT tx_interrupt_control(UINT p){return p;}
static int Firmware_Update_IsActive(void){return 0;}
static int TOF_App_GetStreamDestination(void){return draining?0:route;}
static int TOF_App_GetRequestedStreamDestination(void){return route;}
static int TOF_App_IsDatasetStreamEnabled(void){return dataset;}
static void TOF_App_SetDatasetStreamDestination(unsigned enabled,int destination){dataset=!!enabled;if(enabled)route=destination;else if(route==(unsigned)destination)route=0;}
static void TOF_App_RequestStream(int next){route=next;}
static void cloud_close_socket(void){cloud->http_kind=0;}
static void cloud_release_tof(void){if(cloud->tof_pending)++released;cloud->tof_pending=0;}
static void cloud_backoff(void){++backoffs;cloud->http_kind=0;}
static const void*sent_pointer;static size_t sent_length;
static int cloud_begin_request(int kind,const char*method,const char*path,const char*content,const void*body,size_t size,const void*body2,size_t size2,unsigned auth){
 assert(auth==1 && !body2 && !size2);(void)content;
 if(kind==CLOUD_HTTP_TRAIN_FRAME){assert(!strcmp(method,"POST"));assert(strstr(path,"/frames"));sent_pointer=body;sent_length=size;}
 cloud->http_kind=kind;return 0;
}
'''
TESTS=r'''
static const char*control="{\"sessionId\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"bootId\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"remainingMs\":60000,\"rateHz\":2,\"remainingSamples\":2,\"protocol\":\"N6DF4\",\"captureVersion\":1}";
static const char*ack="{\"stored\":true,\"frameId\":7,\"timestampMs\":100,\"wireCrc32\":4660,\"bootId\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\"}";
static void reset(void){memset(&mock,0,sizeof mock);memset(&training,0,sizeof training);memset(tof_capture_identity,0,33);now=100;route=dataset=released=backoffs=draining=0;}
static void start(void){cloud_training_control(200,(const uint8_t*)control,strlen(control));assert(training.active && route==TOF_STREAM_CLOUD && dataset);}
int main(void){
 reset();draining=1;start();cloud_training_tick();assert(training.active && dataset && route==TOF_STREAM_CLOUD);draining=0;assert(CloudRelay_IsTrainingFrameDue());
 uint8_t bytes[]={1,2,3,4};mock.tof_payload=bytes;mock.tof_payload_length=sizeof bytes;mock.tof_pending=1;
 mock.tof_frame_id=7;mock.tof_info.mode=5;mock.tof_info.timestamp_ms=100;mock.tof_info.payload_crc32=4660;
 assert(cloud_training_next());assert(sent_pointer==bytes && sent_length==sizeof bytes && mock.tof_pending && !released);
 cloud_training_ack(500,(const uint8_t*)"{}",2);assert(mock.tof_pending && !released && backoffs==1);
 assert(cloud_training_next());assert(training.attempts==2 && sent_pointer==bytes && !memcmp(bytes,"\1\2\3\4",4));
 const char*wrong="{\"stored\":true,\"frameId\":8}";
 cloud_training_ack(200,(const uint8_t*)wrong,strlen(wrong));assert(mock.tof_pending && !released);
 cloud_training_ack(200,(const uint8_t*)ack,strlen(ack));assert(training.acknowledged==1 && !mock.tof_pending && released==1 && training.active);
 mock.tof_pending=1;mock.tof_frame_id=8;mock.tof_info.timestamp_ms=600;assert(cloud_training_next());
 const char*ack2="{\"stored\":true,\"frameId\":8,\"timestampMs\":600,\"wireCrc32\":4660,\"bootId\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\"}";
 cloud_training_ack(200,(const uint8_t*)ack2,strlen(ack2));assert(training.acknowledged==2 && !training.active && !dataset && route==TOF_STREAM_NONE);
 CloudRelay_TrainingStatus_t status;CloudRelay_GetTrainingStatus(&status);assert(status.acknowledged==2 && !status.pending);
 puts("PASS snapshot retained across unknown/mismatched replies; identical retry; matching durable ACK releases; count bound stops");
 reset();start();route=TOF_STREAM_BLE;dataset=1;cloud_training_tick();assert(!training.active && route==TOF_STREAM_BLE && dataset);
 puts("PASS capture cleanup preserves a newer BLE owner");
 reset();start();now=training.deadline;cloud_training_tick();assert(!training.active && !dataset && !route);
 puts("PASS local deadline stops without network or browser");
 reset();route=TOF_STREAM_USB;cloud_training_control(200,(const uint8_t*)control,strlen(control));assert(!training.active && route==TOF_STREAM_USB);
 puts("PASS existing USB owner is not taken over");
 reset();const char*invalid="{\"sessionId\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"bootId\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"remainingMs\":600001,\"rateHz\":2,\"remainingSamples\":2,\"protocol\":\"N6DF4\",\"captureVersion\":1}";
 cloud_training_control(200,(const uint8_t*)invalid,strlen(invalid));assert(!training.active && !route);
 puts("PASS oversized/unsupported control fails closed");
 return 0;
}
'''


def extract(source,name):
    import re
    match=re.search(r'(?m)^(?:static )?(?:int|void)\s+'+name+r'\([^;]*?\)\s*\{',source)
    assert match,name
    pos=match.end();depth=1
    while depth:
        depth+=(source[pos]=='{')-(source[pos]=='}');pos+=1
    return source[match.start():pos]+'\n'


class NativeCloudTraining(unittest.TestCase):
    def test_actual_control_ack_and_snapshot_ownership(self):
        root=Path(__file__).resolve().parents[2]
        cloud=(root/'AppliNonSecure/Core/Src/cloud_relay.c').read_text(encoding='utf-8')
        start=cloud.rindex('static const uint8_t *json_find_value(')
        end=cloud.index('static int cloud_json_escape(',start)
        tof=(root/'AppliNonSecure/Core/Src/tof_app.c').read_text(encoding='utf-8')
        identity=extract(tof,'TOF_App_SetCaptureIdentity')+extract(tof,'TOF_App_GetCaptureIdentity')
        implementation=(root/'AppliNonSecure/Core/Src/cloud_training.inc').read_text(encoding='utf-8')
        run_native(PREFIX+identity+cloud[start:end]+implementation+TESTS)


if __name__=='__main__':unittest.main()
