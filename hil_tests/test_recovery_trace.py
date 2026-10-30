from pathlib import Path
import sys
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'hil_tests'))
from test_wifi_scan_lifetime import run_native
from test_wifi_assoc_admission import extract_function
src=(R/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
header=(R/'AppliNonSecure/Core/Inc/wifi_ble_app.h').read_text()
end=header.index('} WifiBle_RecoveryTrace_t;')+len('} WifiBle_RecoveryTrace_t;')
begin=header.rfind('typedef struct {',0,end)
types=header[begin:end]
run_native(r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
typedef unsigned UINT;
#define APP_ST67W6X_ENABLED 1U
#define APP_ST67W6X_WIFI_SERVICES_ENABLED 1U
#define TX_INT_DISABLE 1
#define portTICK_PERIOD_MS 10U
static UINT tx_interrupt_control(UINT x){return x;}
static unsigned now, ticks, spi_fault, recovery_fault_test;
static uint32_t notification_sequence, notification_last_source;
static uint32_t HAL_GetTick(void){return now;}
static uint32_t xTaskGetTickCount(void){return ticks;}
static int spi_transaction_faulted(void){return spi_fault;}
struct modem {struct{int last_error;bool tx_desynchronized,dns_drain_active;}handler_data;
 unsigned notify_phase,notify_length,notify_written,notify_started,notify_budget;
 bool notify_finish_pending,notify_recv_seen,raw_tx_response_received;int notify_result;};
typedef struct{struct modem Modem;} W61_Object_t;
static W61_Object_t driver;
static W61_Object_t *W61_ObjGet(void){return &driver;}
'''+types+r'''
static struct {WifiBle_RecoveryTrace_t trace;}radio_recovery;
'''+extract_function(src,'radio_capture_recovery_trace')+r'''
int main(void){
 now=24680;ticks=220;notification_sequence=123;notification_last_source=3;
 driver.Modem=(struct modem){.handler_data={.tx_desynchronized=true},
 .notify_length=230,.notify_written=230,.notify_started=10,.notify_budget=100,
 .notify_finish_pending=true,.notify_result=-110};
 radio_capture_recovery_trace();
 WifiBle_RecoveryTrace_t t=radio_recovery.trace;
 assert(t.sequence==1 && t.tick_ms==24680 && t.reason==2);
 assert(t.notification_id==123 && t.notification_source==3 && t.notification_result==-110);
 assert(t.notification_written==230 && t.notification_length==230);
 assert(t.notification_elapsed_ms==2100 && t.notification_budget_ms==1000);
 assert(t.notification_finished && !t.recv_seen && !t.response_seen);
 memset(&driver,0,sizeof driver);assert(!memcmp(&t,&radio_recovery.trace,sizeof t));
 puts("PASS retained scalar timeout context survives driver reinitialization without command text or logging I/O");
 spi_fault=1;radio_capture_recovery_trace();assert(radio_recovery.trace.reason==1);
 spi_fault=0;driver.Modem.handler_data.dns_drain_active=true;
 radio_capture_recovery_trace();assert(radio_recovery.trace.reason==3);
 driver.Modem.handler_data.dns_drain_active=false;recovery_fault_test=1;
 radio_capture_recovery_trace();assert(radio_recovery.trace.reason==4);
 recovery_fault_test=0;radio_capture_recovery_trace();assert(radio_recovery.trace.reason==5);
 assert(radio_recovery.trace.sequence==5);
 driver.Modem.notify_started=UINT32_MAX-9;ticks=10;
 radio_capture_recovery_trace();assert(radio_recovery.trace.notification_elapsed_ms==200);
 puts("PASS distinct SPI/AT/drain/test/explicit triggers and wrapping tick subtraction");
 return 0;}
''')
