"""Actual C USB-reset stream cleanup: USB stops, BLE/Cloud remain unchanged."""
from test_wifi_scan_lifetime import ROOT, run_native
from test_tof_recovery import function

def main():
    source=(ROOT/'AppliNonSecure/Core/Src/tof_app.c').read_text()
    cli=(ROOT/'AppliNonSecure/Core/Src/debug_cli.c').read_text()
    reset=function(cli,'cli_session_reset')
    start=reset.index('  if (stop_usb_streams != 0U)')
    cleanup=reset[start:reset.index('  cli_active_session = previous;',start)]
    prefix=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef unsigned UINT;
typedef enum {TOF_STREAM_NONE,TOF_STREAM_USB,TOF_STREAM_BLE,TOF_STREAM_CLOUD} TOF_StreamDestination_t;
#define TX_INT_DISABLE 1U
static UINT irq;
static UINT tx_interrupt_control(UINT value){UINT old=irq;irq=value;return old;}
static struct {TOF_StreamDestination_t destination;uint32_t revision,map_enabled,dataset_stream_enabled;} tof_desired;
void TOF_App_SetDatasetStreamEnabled(uint32_t);
'''
    functions='\n'.join(function(source,name) for name in (
        'TOF_App_RequestStream','TOF_App_ReleaseStream','TOF_App_SetMapEnabled',
        'TOF_App_SetDatasetStreamDestination','TOF_App_SetDatasetStreamEnabled','TOF_App_StopUsbStreams'))
    tests=r'''
int main(void){
 for(unsigned dest=0;dest<=3;++dest)for(unsigned map=0;map<2;++map)for(unsigned data=0;data<2;++data){
  tof_desired.destination=dest;tof_desired.map_enabled=map;tof_desired.dataset_stream_enabled=data;tof_desired.revision=17;
  unsigned char before[sizeof tof_desired];memcpy(before,&tof_desired,sizeof before);
  cleanup(0);assert(!memcmp(before,&tof_desired,sizeof before));assert(irq==0);
  cleanup(1);assert(irq==0);
  if(dest==TOF_STREAM_USB){assert(tof_desired.destination==TOF_STREAM_NONE);assert(!tof_desired.map_enabled&&!tof_desired.dataset_stream_enabled);}
  else assert(!memcmp(before,&tof_desired,sizeof before));
  memcpy(before,&tof_desired,sizeof before);cleanup(1);assert(!memcmp(before,&tof_desired,sizeof before));
 }
 puts("PASS actual USB cleanup: USB map/dataset stopped; BLE/Cloud/NONE preserved; repeated cleanup inert; IRQ restored");
 return 0;
}
'''
    run_native(prefix+functions+'\nstatic void cleanup(uint32_t stop_usb_streams){\n'+cleanup+'}\n'+tests)
if __name__=='__main__':main()
