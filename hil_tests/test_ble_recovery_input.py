"""Actual RX enqueue: readiness must precede a preempting CLI consumer."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT, run_native
from test_ble_recovery_notice import PREFIX

prefix = PREFIX.replace('typedef unsigned UINT;', 'typedef unsigned TX_QUEUE;typedef unsigned UINT;')
prefix = prefix.replace('unsigned tx_queued;', 'unsigned tx_queued,rx_events,rx_bytes,rx_queued,rx_high_water,rx_dropped_events,rx_dropped_bytes;')
prefix = prefix.replace('stats[1]', 'stats[2]').replace('active_tx[1]', 'active_tx[2]')
prefix = prefix.replace('struct {unsigned active,generation;}reply;', 'struct {unsigned active,generation;}reply;TX_QUEUE cli_rx_free,cli_rx_ready,debug_rx_free,debug_rx_ready;')
prefix = prefix.replace('}shadow;}radio_manager;', '}shadow;struct {unsigned ble_rx_discarded_bytes;}counters;}radio_manager;')
mock = r'''
#define WIFI_BLE_STREAM_COUNT 2U
#define BLE_RX_SLOT_PAYLOAD_SIZE 512U
typedef unsigned WifiBle_Stream_t;
typedef struct {unsigned generation;uint16_t length;uint8_t data[512];}WifiBle_RxSlot_t;
static WifiBle_RxSlot_t input;
static unsigned free_fail,ready_fail,preemptions;
static UINT tx_queue_receive(TX_QUEUE*q,void*p,ULONG wait){(void)q;assert(!wait);if(free_fail)return 1;*(void**)p=&input;return 0;}
static UINT tx_queue_send(TX_QUEUE*q,void*p,ULONG wait){assert(!wait);if(q==&ctx.cli_rx_ready){if(ready_fail)return 1;assert(*(void**)p==&input);assert(ble_recovery_input_generation==input.generation);assert(WIFI_BLE_App_SendRecoveryNotice()==TX_NOT_AVAILABLE);++preemptions;}return 0;}
static void Debug_UART_NcpTracePing(const char*t,const void*d,unsigned n){(void)t;(void)d;(void)n;}
'''
tests = r'''
int main(void){
 const uint8_t text[5]={'p','i','n','g','\r'};
 reset();ble_recovery_notice.pending=0;ble_recovery_notice.notification_generation=9;
 ble_stream_enqueue_rx(0,text,5);
 assert(preemptions==1 && writes==1 && ble_recovery_notice.pending==2 && ctx.stats[0].rx_queued==1);
 puts("PASS queue-woken CLI sees readiness before input and holds it through the recovery event");
 reset();free_fail=1;ble_stream_enqueue_rx(0,text,5);
 assert(!ble_recovery_input_generation && !writes && ctx.stats[0].rx_dropped_events==1);
 puts("PASS no free RX slot cannot mark an unobserved enqueue as ready");
 reset();free_fail=0;ready_fail=1;ble_recovery_notice.pending=0;ble_recovery_notice.notification_generation=9;
 ble_stream_enqueue_rx(0,text,5);
 assert(!ctx.stats[0].rx_queued && ctx.stats[0].rx_dropped_events==1 && ble_recovery_input_generation==9);
 assert(WIFI_BLE_App_SendRecoveryNotice()==TX_NOT_AVAILABLE && writes==1);
 puts("PASS dropped fresh input may receive a warning but never executes or manufactures a command final");
 return 0;
}
'''

if __name__ == '__main__':
    source=(ROOT/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    run_native(prefix+function(source,'WIFI_BLE_App_GetRecoveryNotice')+
               function(source,'WIFI_BLE_App_SendRecoveryNotice')+mock+
               function(source,'ble_stream_enqueue_rx')+tests)
