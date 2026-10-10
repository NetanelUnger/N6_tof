"""Execute production bounded replies, BLE slot leases and RX remainder handling."""
import re
from test_wifi_scan_lifetime import ROOT, run_native
from test_wifi_assoc_admission import extract_function


def function(source, name):
    # Existing extractor also used for driver tests; add the ThreadX return type.
    return extract_function(re.sub(r'^(static )?UINT\b', r'\1int', source, flags=re.M), name)


PREFIX = r'''
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdbool.h>
typedef unsigned UINT; typedef unsigned long ULONG; typedef int TX_THREAD;
#define APP_ST67W6X_BLE_GATT_ENABLED 1U
#define TX_SUCCESS 0U
#define TX_NOT_AVAILABLE 1U
#define TX_QUEUE_FULL 2U
#define TX_QUEUE_EMPTY 3U
#define TX_PTR_ERROR 4U
#define TX_SIZE_ERROR 5U
#define TX_NO_WAIT 0U
#define TX_WAIT_FOREVER 9999U
#define TX_INT_DISABLE 1U
#define TX_NULL NULL
#define BLE_CLI_TX_SLOT_COUNT 8U
#define BLE_CLI_TX_SLOT_SIZE 768U
#define BLE_CLI_TX_MAX_WAIT_TICKS 5U
#define BLE_DEBUG_TX_SLOT_SIZE 256U
#define WIFI_BLE_STREAM_COUNT 2U
#define WIFI_BLE_STREAM_CLI 0U
#define WIFI_BLE_STREAM_DEBUG 1U
typedef unsigned WifiBle_Stream_t;
typedef struct {void *items[8];unsigned count;} TX_QUEUE;
typedef struct {unsigned generation;uint16_t length,offset;uint8_t retries;uint8_t data[768];} WifiBle_CliTxSlot_t;
typedef struct {unsigned generation;uint16_t length,offset;uint8_t retries;uint8_t data[256];} WifiBle_DebugTxSlot_t;
typedef struct {unsigned generation;uint16_t length;uint8_t data[512];} WifiBle_RxSlot_t;
typedef struct {unsigned tx_dropped_messages,tx_dropped_bytes,tx_messages,tx_bytes,tx_queued,tx_high_water,rx_queued,stale_drops;} Stats;
typedef struct {
 TX_QUEUE cli_tx_free,cli_tx_ready,debug_tx_free,debug_tx_ready;
 TX_QUEUE cli_rx_free,cli_rx_ready,debug_rx_free,debug_rx_ready;
 WifiBle_CliTxSlot_t cli_tx_slots[8];WifiBle_DebugTxSlot_t debug_tx_slots[8];
 Stats stats[2];AppCliReply_t reply;TX_THREAD *reply_owner;
} WifiBle_StreamContext_t;
static WifiBle_StreamContext_t context;
static struct {
 struct {unsigned ble_connected,ble_cli_tx_subscribed,ble_debug_tx_subscribed,ble_transport_ready,ble_session_generation;} shadow;
 struct {WifiBle_StreamContext_t *ble_stream_context;} queues;
} radio_manager;
static unsigned irq,takes,fail_take;
static TX_THREAD task=1, other=2;static TX_THREAD *current=&task;
static TX_THREAD *tx_thread_identify(void){return current;}
static UINT tx_interrupt_control(UINT n){UINT old=irq;irq=n;return old;}
#define Debug_UART_Log(...) do {assert(!irq);} while(0)
static UINT tx_queue_info_get(TX_QUEUE*q,void*a,ULONG*n,void*b,void*c,void*d,void*e){(void)a;(void)b;(void)c;(void)d;(void)e;*n=q->count;return 0;}
static UINT tx_queue_receive(TX_QUEUE*q,void*p,ULONG wait){assert(wait==0);if(fail_take && ++takes==fail_take)return 3;if(!q->count)return 3;*(void**)p=q->items[0];--q->count;memmove(q->items,q->items+1,q->count*sizeof(void*));return 0;}
static UINT tx_queue_send(TX_QUEUE*q,void*p,ULONG wait){assert(wait==0);if(q->count==8)return 2;q->items[q->count++]=*(void**)p;return 0;}
static UINT tx_queue_front_send(TX_QUEUE*q,void*p,ULONG wait){assert(wait==0);if(q->count==8)return 2;memmove(q->items+1,q->items,q->count*sizeof(void*));q->items[0]=*(void**)p;++q->count;return 0;}
static void reset(void){memset(&context,0,sizeof context);memset(&radio_manager,0,sizeof radio_manager);radio_manager.queues.ble_stream_context=&context;radio_manager.shadow.ble_connected=radio_manager.shadow.ble_cli_tx_subscribed=radio_manager.shadow.ble_transport_ready=1;radio_manager.shadow.ble_session_generation=7;irq=takes=fail_take=0;current=&task;for(unsigned i=0;i<8;i++){void*p=&context.cli_tx_slots[i];tx_queue_send(&context.cli_tx_free,&p,0);}}
'''

TESTS = r'''
int main(void){
 reset();assert(!WIFI_BLE_App_BeginReply());assert(context.reply.active && !context.cli_tx_free.count);
 for(unsigned i=0;i<30;i++)assert(!WIFI_BLE_App_StreamWrite(0,"text\r\n",6,0));
 assert(!context.cli_tx_ready.count && context.reply.bytes==180);
 assert(!WIFI_BLE_App_EndReply(1));assert(context.cli_tx_ready.count==1 && context.cli_tx_free.count==7);
 assert(strstr((char*)context.cli_tx_slots[0].data,"state=complete"));
 assert(WIFI_BLE_App_BeginReply()==TX_QUEUE_FULL);
 puts("PASS reserve before execution; thirty print calls pack into one owned slot; next command blocked until drained");
 reset();assert(!WIFI_BLE_App_BeginReply());char large[6016];memset(large,'x',sizeof large);
 assert(!WIFI_BLE_App_StreamWrite(0,large,sizeof large,0));
 assert(WIFI_BLE_App_StreamWrite(0,"xx",2,0)==TX_SIZE_ERROR && context.reply.bytes==sizeof large);
 assert(!WIFI_BLE_App_EndReply(1));assert(context.cli_tx_ready.count==8);
 assert(strstr((char*)context.cli_tx_slots[7].data,"state=failed reason=OUTPUT_LIMIT"));
 puts("PASS bounded response overflow has reserved explicit failure, no partial append or missing completion");
 reset();assert(!WIFI_BLE_App_BeginReply());current=&other;
 assert(WIFI_BLE_App_StreamWrite(0,"foreign",7,0)==TX_NOT_AVAILABLE);
 assert(WIFI_BLE_App_EndReply(1)==TX_NOT_AVAILABLE);current=&task;
 assert(!WIFI_BLE_App_EndReply(0) && context.cli_tx_free.count==8);
 puts("PASS another producer cannot borrow the CLI reply lease; empty lease returns all slots");
 reset();assert(!WIFI_BLE_App_BeginReply());assert(!WIFI_BLE_App_StreamWrite(0,"secret old output",17,0));
 radio_manager.shadow.ble_session_generation=8;
 assert(WIFI_BLE_App_EndReply(1)==TX_NOT_AVAILABLE && !context.cli_tx_ready.count && context.cli_tx_free.count==8);
 puts("PASS session replacement cancels old reply without exposing it to new peer");
 reset();fail_take=3;assert(WIFI_BLE_App_BeginReply()!=0 && context.cli_tx_free.count==8 && !context.reply.active);
 puts("PASS failed slot reservation rolls back every acquired slot before command acceptance");
 reset();assert(!WIFI_BLE_App_BeginReply());assert(!WIFI_BLE_App_EndReply(2));
 assert(strstr((char*)context.cli_tx_slots[0].data,"state=rejected"));
 puts("PASS rejection has its own final result rather than claiming command success");
 reset();WifiBle_RxSlot_t slot={.generation=7,.length=8};memcpy(slot.data,"one\rtwo\r",8);void*p=&slot;
 tx_queue_send(&context.cli_rx_ready,&p,0);context.stats[0].rx_queued=1;
 char out[32]={0};ULONG n=0;
 assert(!ble_stream_read(0,out,sizeof out,&n,0,1) && n==4 && !memcmp(out,"one\r",4));
 assert(slot.length==4 && context.cli_rx_ready.count==1 && !context.cli_rx_free.count && context.stats[0].rx_queued==1);
 assert(!ble_stream_read(0,out,sizeof out,&n,0,1) && n==4 && !memcmp(out,"two\r",4));
 assert(!context.cli_rx_ready.count && context.cli_rx_free.count==1);
 puts("PASS multiple commands in one ATT value retain ordered RX remainder until next reply lease");
 reset();slot.generation=7;slot.length=9;memcpy(slot.data,"one\r\nnext",9);p=&slot;tx_queue_send(&context.cli_rx_ready,&p,0);
 assert(!ble_stream_read(0,out,sizeof out,&n,0,1) && n==5 && slot.length==4);
 assert(!ble_stream_read(0,out,2,&n,0,1) && n==2 && slot.length==2);
 puts("PASS CRLF and bounded partial text reads preserve all following bytes");
 reset();slot.generation=6;slot.length=4;p=&slot;tx_queue_send(&context.cli_rx_ready,&p,0);
 assert(ble_stream_read(0,out,sizeof out,&n,0,1)==TX_QUEUE_EMPTY && context.stats[0].stale_drops==1);
 puts("PASS stale RX generations are retired before any command dispatch");
 reset();assert(!WIFI_BLE_App_BeginReply());assert(!WIFI_BLE_App_StreamWrite(0,"partial",7,0));
 assert(!WIFI_BLE_App_EndReply(3));assert(strstr((char*)context.cli_tx_slots[0].data,"state=failed reason=WRITE_ERROR"));
 puts("PASS failed handler write has explicit failure, never a false completion");
 return 0;
}
'''

def main():
    source=(ROOT/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    header=(ROOT/'AppliNonSecure/Core/Inc/app_cli_reply.h').read_text()
    code='\n'.join(function(source,name) for name in ['WIFI_BLE_App_BeginReply','WIFI_BLE_App_EndReply','WIFI_BLE_App_StreamWrite','ble_stream_read'])
    run_native(header+PREFIX+code+TESTS)

if __name__=='__main__':main()
