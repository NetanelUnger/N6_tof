"""Execute real mailbox, completion and GATT setup C with mocked modem replies.

These checks cover ownership and callback races, not radio timing; HIL remains
required for shared-AT contention and actual image delivery.
"""
import re
from test_wifi_scan_lifetime import ROOT, run_native


def function(source, name):
    match = re.search(r"\nstatic [^\n]+ " + name + r"\([^;]*?\)\n\{", source)
    if not match:
        raise ValueError(name)
    start = match.start() + 1
    end = source.index("{", match.start()) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <inttypes.h>
typedef uint32_t UINT;
typedef int W6X_Status_t;
typedef int W6X_Ble_Mode_e;
enum { W6X_STATUS_OK, W6X_STATUS_BUSY, W6X_STATUS_ERROR, W6X_STATUS_TIMEOUT };
#define TX_INT_DISABLE 1U
#define TX_OR 0U
#define APP_ST67W6X_WIFI_SERVICES_ENABLED 0U
#define APP_ST67W6X_BLE_GATT_ENABLED 1U
#define TX_SUCCESS 0U
#define TX_QUEUE_EMPTY 1U
#define TX_PTR_ERROR 2U
#define TX_NOT_AVAILABLE 3U
#define TX_QUEUE_ERROR 4U
typedef struct { uint32_t marker; } WifiBle_WifiResult_t;
typedef struct { uint32_t result_free; } WifiContext;
#define WIFI_BLE_DEVICE_NAME_SIZE 26U
#define WIFI_BLE_ADDRESS_SIZE 6U
#define WIFI_CONTROL_WORK_FLAG 8U
#define BLE_HEALTH_PROBE_INTERVAL_MS 15000U
#define BLE_ADV_RETRY_BASE_MS 1000U
#define BLE_ADV_MAX_ATTEMPTS 3U
#define BLE_RECOVERY_COOLDOWN_MS 10000U
#define W6X_BLE_MODE_SERVER 2U
#define W6X_BLE_UUID_TYPE_128 0U
#define W6X_BLE_SEC_IO_NO_INPUT_OUTPUT 0U
#define BLE_CLI_SERVICE_INDEX 0U
#define BLE_DEBUG_SERVICE_INDEX 1U
#define BLE_CLI_SERVICE_UUID "cli"
#define BLE_DEBUG_SERVICE_UUID "debug"
#define BLE_ADV_DATA "adv"
#define LogWarn(...) assert(irq==0)
#define LogError(...) assert(irq==0)
#define LogInfo(...) assert(irq==0)
static uint32_t irq, tick, calls, wakeups, mutate_at, failure_at, busy_at;
static uint32_t result_mode, result_handle, pumps;
static uint32_t result_waits;
static WifiBle_WifiResult_t wifi_result;
static int radio_control_events;
static UINT tx_interrupt_control(UINT p) { UINT old=irq; irq=p; return old; }
static uint32_t HAL_GetTick(void) { return tick; }
static int tx_event_flags_set(void *g,uint32_t flags,UINT mode) {
 assert(irq==0); ++wakeups; return 0;
}
static int tx_queue_receive(void *queue,void **message,uint32_t wait) {
 assert(wait==1 && irq==0); tick+=10;
 if (++result_waits < 4) return TX_QUEUE_EMPTY;
 *message=&wifi_result; return TX_SUCCESS;
}
'''

MOCKS = r'''
static int call(void) {
 assert(irq==0); ++calls; tick+=2000;
 /* While the worker waits, the Radio owner can keep pumping. */
 pumps+=100;
 if (calls==mutate_at) radio_manager.shadow.ble_session_generation++;
 if (calls==busy_at) return W6X_STATUS_BUSY;
 return calls==failure_at ? W6X_STATUS_TIMEOUT : W6X_STATUS_OK;
}
static int W6X_Ble_ExchangeMTU(uint32_t h) { return call(); }
static int W6X_Ble_SetConnParam(uint32_t h,int a,int b,int c,int d) { return call(); }
static int W6X_Ble_Disconnect(uint32_t h) { return call(); }
static int W6X_Ble_AdvStart(void) { return call(); }
static int W6X_Ble_AdvStop(void) { return call(); }
static int W6X_Ble_GetInitMode(W6X_Ble_Mode_e *m) { *m=result_mode;return call(); }
static int W6X_Ble_GetConn(uint32_t *h,uint8_t *a) { *h=result_handle;return call(); }
static int W6X_Ble_Init(int mode,void *buffer,size_t n) { return call(); }
static int W6X_Ble_GetBDAddress(uint8_t *a) { a[4]=0xb8;a[5]=0xfb;return call(); }
static int W6X_Ble_SetDeviceName(const char *n) { return call(); }
static int W6X_Ble_SetTxPower(int power) { return call(); }
static int W6X_Ble_SetAdvData(const char *d) { return call(); }
static int W6X_Ble_CreateService(int i,const char *u,int t) { return call(); }
static int W6X_Ble_CreateCharacteristic(int a,int b,const char *u,int t,int p,int q) { return call(); }
static int W6X_Ble_RegisterCharacteristics(void) { return call(); }
static int W6X_Ble_SetSecurityParam(int p) { return call(); }
static const struct { int service_index,char_index; const char *uuid;
 int properties,permissions; const char *description; } ble_characteristics[5] = {{0}};
static void ble_note_disconnected(void) {
 radio_manager.shadow.ble_session_generation++;
 radio_manager.shadow.ble_connected=0;
 radio_manager.shadow.ble_connection_handle=0xff;
}
static uint32_t ble_control_current(const BleControlJob_t *job);
static W6X_Status_t ble_configure_gatt_job(BleControlJob_t *job, uint32_t startup);
static void ble_apply_gatt(const BleControlJob_t *job);
static void ble_apply_probe(const BleControlJob_t *job);
static void ble_control_execute(void);
'''

TESTS = r'''
static void reset(void) {
 memset(&radio_manager,0,sizeof radio_manager); memset(&ble_control,0,sizeof ble_control);
 irq=tick=calls=wakeups=mutate_at=failure_at=busy_at=pumps=ble_adv_revision=result_waits=0;
 radio_manager.shadow.ble_session_generation=4;
 radio_manager.shadow.ble_connection_handle=7;
 radio_manager.shadow.ble_mode_confirmed=radio_manager.shadow.ble_link_confirmed=1;
 radio_manager.shadow.ble_advertising_desired=1;
 result_mode=W6X_BLE_MODE_SERVER; result_handle=7;
}
int main(void) {
 reset(); assert(ble_control_submit(BLE_CONTROL_CONNECT));
 assert(calls==0 && ble_control.state==1 && wakeups==1);
 radio_manager.shadow.ble_connection_handle=8;
 assert(!ble_control_submit(BLE_CONTROL_LINK)); assert(ble_control.job.handle==7);
 ble_control_execute(); assert(calls==2 && pumps==200 && ble_control.state==3);
 assert(!ble_control_submit(BLE_CONTROL_LINK));
 ble_control_complete(); assert(irq==0 && ble_control.state==0);
 assert(ble_control.stats.submitted==1 && ble_control.stats.completed==1);
 puts("PASS publish is nonblocking, fixed mailbox retains request through completion");

 reset(); ble_control_submit(BLE_CONTROL_DISCONNECT);
 radio_manager.shadow.ble_session_generation++; ble_control_execute(); ble_control_complete();
 assert(calls==0 && ble_control.stats.stale==1);
 puts("PASS stale queued disconnect is cancelled before any command");

 reset(); mutate_at=1; ble_control_submit(BLE_CONTROL_CONNECT);
 ble_control_execute(); ble_control_complete(); assert(calls==1 && ble_control.stats.stale==1);
 puts("PASS connection event during MTU cancels remaining old-link configuration");

 reset(); ble_control_submit(BLE_CONTROL_ADV); ble_control_execute();
 ble_adv_revision++; radio_manager.shadow.ble_advertising_desired=0;
 ble_control_complete(); assert(ble_control.stats.stale==1 && !radio_manager.shadow.ble_advertising);
 puts("PASS obsolete advertising ACK cannot override newer desired state");

 reset(); busy_at=1; ble_control_submit(BLE_CONTROL_MODE); ble_control_execute(); ble_control_complete();
 assert(radio_manager.shadow.ble_mode_confirmed && radio_manager.shadow.ble_link_confirmed);
 assert(!radio_manager.counters.faults.ble_query_failures);
 puts("PASS BUSY preserves confirmed link/mode and does not create a false fault");

 reset(); busy_at=1; ble_control_submit(BLE_CONTROL_DISCONNECT); ble_control_execute(); ble_control_complete();
 assert(radio_manager.work.ble_disconnect_request && !radio_manager.counters.faults.disconnect_failures);
 puts("PASS deferred disconnect remains requested without counting failure");

 reset(); ble_control_submit(BLE_CONTROL_RECOVER); ble_control_execute();
 assert(!radio_manager.shadow.ble_gatt_ready && !radio_manager.shadow.ble_device_name[0]);
 ble_control_complete(); assert(radio_manager.shadow.ble_gatt_ready);
 assert(!strcmp(radio_manager.shadow.ble_device_name,"N6-MAINT-B8FB"));
 assert(!radio_manager.shadow.ble_advertising);
 puts("PASS recovery publishes local GATT result; advertising is reconciled separately");

 reset(); mutate_at=4; ble_control_submit(BLE_CONTROL_RECOVER); ble_control_execute(); ble_control_complete();
 assert(calls==4 && ble_control.stats.stale==1 && !radio_manager.shadow.ble_gatt_ready);
 puts("PASS callback during recovery stops remaining GATT commands and rejects result");

 reset(); failure_at=1; ble_control_submit(BLE_CONTROL_ADV); ble_control_execute(); ble_control_complete();
 assert(radio_manager.work.ble_advertising_retry_count==1);
 assert(radio_manager.work.ble_advertising_retry_due_tick==3000);
 puts("PASS real advertising timeout retains bounded retry policy");

 reset(); radio_manager.shadow.ble_connected=1; result_handle=0xff;
 for(int i=0;i<2;i++) { ble_control_submit(BLE_CONTROL_LINK); ble_control_execute(); ble_control_complete(); }
 assert(!radio_manager.shadow.ble_connected && radio_manager.counters.faults.ble_link_corrections==1);
 assert(irq==0);
 puts("PASS successful repeated mismatch repairs link with atomic generation check");

 reset(); tick=0xfffffff0U; ble_control_submit(BLE_CONTROL_MODE); tick+=40;
 ble_control_execute(); ble_control_complete();
 assert(ble_control.stats.max_queue_ms==40 && ble_control.stats.max_call_ms==2000);
 puts("PASS separate queue/execution durations remain correct across timer wrap");

 reset(); WifiContext context={0}; radio_manager.queues.wifi_control_context=&context;
 ble_control_submit(BLE_CONTROL_MODE); WifiBle_WifiResult_t *result=NULL;
 assert(wifi_result_slot_acquire_wait(&result)==TX_SUCCESS && result==&wifi_result);
 assert(result_waits==4 && calls==1 && ble_control.state==3);
 ble_control_complete(); assert(ble_control.stats.completed==1);
 puts("PASS Wi-Fi result backpressure services BLE without losing Wi-Fi result ownership");
 return 0;
}
'''


def main():
    source = (ROOT / 'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    names = ['ble_control_current', 'ble_control_submit', 'ble_control_execute',
             'ble_control_complete', 'ble_configure_gatt_job', 'ble_apply_gatt',
             'ble_apply_probe', 'wifi_result_slot_acquire_wait']
    actual = '\n'.join(function(source, name) for name in names)
    # Lightweight hardware boundary retains each real state field used by code.
    shadow = sorted(set(re.findall(r'radio_manager.shadow.(\w+)', actual)))
    work = sorted(set(re.findall(r'radio_manager.work.(\w+)', actual)))
    faults = sorted(set(re.findall(r'radio_manager.counters.faults.(\w+)', actual)))
    shadow_fields = '\n'.join(f'uint32_t {x};' for x in shadow if x not in ['ble_device_name','ble_address'])
    shadow_fields += '\nchar ble_device_name[26]; uint8_t ble_address[6];'
    manager = 'static struct { struct {' + shadow_fields + '} shadow; struct {'
    manager += '\n'.join(f'uint32_t {x};' for x in work) + '} work; struct { struct {'
    manager += '\n'.join(f'uint32_t {x};' for x in faults) + '} faults; } counters;'
    manager += 'struct { uint8_t ble_receive_buffer[512]; WifiContext *wifi_control_context; } queues; } radio_manager;\n'
    constants = sorted(set(re.findall(r'\bWIFI_BLE_(?:INIT_STAGE|ADV)_\w+', actual)))
    constants = '\n'.join(f'#define {x} {i+10}U' for i,x in enumerate(constants))
    start = source.index('typedef enum\n{\n  BLE_CONTROL_CONNECT')
    end = source.index('static uint32_t ble_control_submit(', start)
    types = source[start:end]
    header = (ROOT / 'AppliNonSecure/Core/Inc/wifi_ble_app.h').read_text()
    end = header.index('} WifiBle_ControlStatus_t;') + len('} WifiBle_ControlStatus_t;')
    stats = header[header.rfind('typedef struct', 0, end):end]
    run_native(PREFIX + constants + '\n' + stats + '\n' + manager + types + MOCKS + actual + TESTS)
    for name in ['ble_process_pending_events','ble_reconcile_advertising','ble_recover_subsystem','ble_probe_shadow']:
        code = function(source,name)
        assert not re.search(r'W6X_Ble_\w+\(', code), name
    print('PASS Radio runtime control paths contain no blocking W6X BLE call')


if __name__ == '__main__':
    main()
