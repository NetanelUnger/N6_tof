"""Host characterization and isolated candidate; production C is never edited."""
from pathlib import Path
import sys, re, difflib
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
OUT=Path(__file__).resolve().parent/'evidence/st67-cp5-20261028'
sys.path.insert(0,str(ROOT/'hil_tests'))
from test_spi_fs_framing import block
from test_resource_diagnostics import STUB
from test_xip_boot import run_native

def actual(source,name):
    return block(source,r'^(?:static )?[^\n;]*\b'+name+r'\([^;]*?\)\s*\{')

def logger(candidate,enabled):
    source=(ROOT/'AppliNonSecure/Core/Src/debug_uart.c').read_text()
    code=actual(source,'Debug_UART_Write')
    if candidate:
        old='  (void)buffer;\n  return (int32_t)length;'
        new='  (void)buffer;\n  (void)length;\n  return 0; /* Same zero-success contract as enabled output. */'
        assert code.count(old)==1
        changed=source.replace(old,new,1)
        code=code.replace(old,new)
        patch=''.join(difflib.unified_diff(source.splitlines(True),changed.splitlines(True),
            fromfile='a/AppliNonSecure/Core/Src/debug_uart.c',tofile='b/AppliNonSecure/Core/Src/debug_uart.c'))
        (OUT/'PROPOSED-NOT-APPLIED-quiet-logger.patch').write_text(patch,encoding='utf-8')
    pre=r'''
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#define N6_RESOURCE_DIAGNOSTICS 1
#define N6_RESOURCE_SOURCE N6R_USB
#include "resource_diag.h"
static uint32_t mask,tick,ipsr,sinks,queued,polled;
static uint32_t debug_uart_ready,debug_uart_async_active;
static int32_t result;
static int32_t Debug_UART_QueueWrite(const void*p,size_t n){++queued;return result;}
static int32_t Debug_UART_PollingWrite(const void*p,size_t n){++polled;return result;}
'''
    # resource_diag.h reaches config.h, which defines the quiet baseline.
    # Apply the comparison switch after that include so both variants execute.
    pre += f'\n#undef N6_DEBUG_OUTPUT_ENABLED\n#define N6_DEBUG_OUTPUT_ENABLED {enabled}\n'
    post=r'''
static int32_t sink(const void*p,size_t n){++sinks;return N6R_QueuedBytes(Debug_UART_Write(p,n),n);}
#define N6R_HOST 1
#define N6R_STORAGE
#define N6R_LOCK() mask
#define N6R_DISABLE() (mask=1)
#define N6R_UNLOCK(p) (mask=(p))
#define N6R_ISR() ipsr
#define N6R_NOW() tick
#define N6R_SINK(p,n) sink(p,n)
#include "resource_diag_impl.inc"
int main(void){
 const char message[]="diagnostic";
#if N6_DEBUG_OUTPUT_ENABLED
 assert(Debug_UART_Write(NULL,0)==0);
 assert(Debug_UART_Write(message,sizeof message)==-1 && !queued && !polled);
 debug_uart_ready=debug_uart_async_active=1;result=-6;
 assert(Debug_UART_Write(message,sizeof message)==-6 && queued==1);
 result=0;assert(Debug_UART_Write(message,sizeof message)==0 && queued==2);
 debug_uart_async_active=0;result=-2;
 assert(Debug_UART_Write(message,sizeof message)==-2 && polled==1);
 result=0;assert(Debug_UART_Write(message,sizeof message)==0 && polled==2);
 puts("PASS enabled writer preserves zero success and negative queue/poll failures");
#else
 N6R_Init();N6R_Record(N6R_USB,N6R_ALLOC,7,1,32,NULL);
 tick=1000;N6R_ReportDeferred();tick=2000;N6R_ReportDeferred();tick=3000;N6R_ReportDeferred();
 assert(n6r_failures[N6R_USB][N6R_ALLOC].count==1 && !queued && !polled);
#if CANDIDATE
 assert(sinks==1 && n6r_reported[N6R_USB][N6R_ALLOC]==1);
 puts("PASS isolated quiet-writer candidate retires one report and retains captured failure without I/O");
#else
 assert(sinks==3 && n6r_reported[N6R_USB][N6R_ALLOC]==0);
 puts("REPRODUCED baseline quiet writer: three attempts for one unchanged captured failure; success adapter never retires row");
#endif
#endif
 return 0;
}
'''
    run_native(f'#define N6_DEBUG_OUTPUT_ENABLED {enabled}\n#define CANDIDATE {int(candidate)}\n'+pre+code+post,
        extra_stubs={'tx_api.h':STUB},extra_includes=[ROOT/'AppliNonSecure/Core/Inc',ROOT/'AppliNonSecure/Core/Src'],retain_artifacts=True)

def callback():
    core=ROOT/'ThirdParty/ST67W6X_Network_Driver'
    types='\n'.join(re.search(r'typedef enum\s*\{[^}]*\}\s*'+name+r';',(core/path).read_text())[0]
        for name,path in [('W6X_Status_t','Api/w6x_types.h'),('W61_Status_t','Driver/W61_at/w61_at_api.h')])
    pre=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static struct {struct {struct {uint32_t driver_error_callbacks;int32_t last_driver_error;} faults;} counters;} radio_manager;
static struct {void(*APP_error_cb)(W6X_Status_t,const char*);} W6X_CbHandler;
#define LogError(...) ((void)0)
'''
    code=actual((ROOT/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text(),'error_callback')
    code+=actual((core/'Core/w6x_sys.c').read_text(),'TranslateErrorStatus_W61_W6X')
    cases=r'''
int main(void){
 W6X_CbHandler.APP_error_cb=error_callback;
 assert(TranslateErrorStatus_W61_W6X(W61_STATUS_OK,"W6X_WiFi_Connect")==W6X_STATUS_OK);
 assert(!radio_manager.counters.faults.driver_error_callbacks);
 TranslateErrorStatus_W61_W6X(W61_STATUS_ERROR,"W6X_WiFi_Connect");
 assert(radio_manager.counters.faults.driver_error_callbacks==1 && radio_manager.counters.faults.last_driver_error==2);
 TranslateErrorStatus_W61_W6X(W61_STATUS_ERROR,"W6X_Ble_ExchangeMTU");
 assert(radio_manager.counters.faults.driver_error_callbacks==2 && radio_manager.counters.faults.last_driver_error==2);
 TranslateErrorStatus_W61_W6X(W61_STATUS_ERROR,"W6X_GetPowerMode");
 assert(radio_manager.counters.faults.driver_error_callbacks==3);
 puts("PASS actual shared error callback counts WiFi, BLE and system failures identically; last=2 has no operation provenance");
 const char*names[]={"W6X_Ble_ServerNotify","W6X_Ble_ServerNotifyBegin","W6X_Ble_ServerNotifyPoll","W6X_Ble_ServerNotifyCancel"};
 for(unsigned i=0;i<4;++i)TranslateErrorStatus_W61_W6X(W61_STATUS_BUSY,names[i]);
 assert(radio_manager.counters.faults.driver_error_callbacks==3);
 TranslateErrorStatus_W61_W6X(W61_STATUS_BUSY,"W6X_WiFi_Connect");
 assert(radio_manager.counters.faults.driver_error_callbacks==4 && radio_manager.counters.faults.last_driver_error==1);
 TranslateErrorStatus_W61_W6X(W61_STATUS_TIMEOUT,names[0]);
 assert(radio_manager.counters.faults.driver_error_callbacks==5 && radio_manager.counters.faults.last_driver_error==3);
 TranslateErrorStatus_W61_W6X(W61_STATUS_UNEXPECTED_RESPONSE,NULL);
 assert(radio_manager.counters.faults.driver_error_callbacks==6 && radio_manager.counters.faults.last_driver_error==4);
 puts("PASS only notification admission BUSY is excluded; real notification failure and other-owner BUSY remain visible");
 W6X_CbHandler.APP_error_cb=NULL;
 TranslateErrorStatus_W61_W6X(W61_STATUS_ERROR,"absent");
 assert(radio_manager.counters.faults.driver_error_callbacks==6);
 return 0;
}
'''
    from test_wifi_scan_lifetime import run_native as simple
    simple('#include <stdint.h>\n'+types+pre+code+cases)

if __name__=='__main__':
    callback()
    logger(False,0)
    logger(True,0)
    logger(True,1)
