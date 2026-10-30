"""Actual-C regressions for an isolated candidate; no firmware build or hardware."""
from pathlib import Path
import argparse, re, sys
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
HERE=Path(__file__).parent
OUT=HERE/'evidence/st67-cp10-transport-candidate'
sys.path.insert(0,str(ROOT/'hil_tests'))
from test_wifi_scan_lifetime import run_native
from test_spi_fs_framing import block
import test_spi_fs_framing as framing
import test_st67_spi_pressure as pressure
import test_radio_coordinated_recovery as recovery
import test_radio_service_status as service
import test_fs_rx_binary_path as fs
import test_radio_spi_shutdown as shutdown
from test_wifi_assoc_admission import extract_function
from test_raw_send_response import extract

SPI_TESTS=r'''
static void reset(struct spi_xfer_engine *e,unsigned which){
 assert(!live && !received);memset(e,0,sizeof *e);scenario=which;
 transaction=cs_high=cs_low=accepted=attempted=abort_calls=elapsed=0;
 allocations=reads=wire_offset=queue_calls=fail_small=fail_first_alloc=0;
 queue_full=ack_stuck=stop_after=fail_remaining=abort_failures=ready_waits=0;
 ready=1;e->rxq[0]=(void*)1;e->rxq_bound=1;active=e;
}
static void add_tx(struct spi_xfer_engine *e){
 e->txbuf=spi_buffer_alloc(4,sizeof(struct spi_header));assert(e->txbuf);
 memset(e->txbuf->data,0xa5,4);assert(spi_buffer_push(e->txbuf,sizeof(struct spi_header)));
}
static void release_retained(struct spi_xfer_engine *e){
 assert(e->stop && !e->failed_rxbuf);
 if(e->txbuf){spi_buffer_free(e->txbuf);e->txbuf=NULL;}
 assert(!live);
}
int main(void){
 struct spi_xfer_engine e;
 reset(&e,2);add_tx(&e);fail_remaining=1;
 struct spi_buffer *saved=e.txbuf;
 spi_do_xfer(&e,0);
 assert(accepted==1 && attempted==1 && transaction==1);
 puts("PASS ambiguous remaining-RX failure never replays accepted TX");
#if CANDIDATE
 assert(e.transport_fault==SPI_XFER_TRANSPORT_ERROR && e.stop==1 && e.txbuf==saved && live==1 && !received && abort_calls==1);
 ready=1;spi_do_xfer(&e,0);assert(transaction==1 && e.txbuf==saved);
 release_retained(&e);
 puts("PASS new RDY activation cannot revive sticky fault; TX retained for teardown");
 reset(&e,4);add_tx(&e);spi_do_xfer(&e,0);
 assert(e.transport_fault==SPI_XFER_PROTOCOL_ERROR && accepted==1 && transaction==1 && e.stat.hdr_err==1 && abort_calls==0);
 release_retained(&e);
 puts("PASS invalid peer header stops without replay even when local DMA completed");
 reset(&e,5);add_tx(&e);spi_do_xfer(&e,0);
 assert(e.transport_fault==SPI_XFER_TRANSPORT_ERROR && accepted==1 && transaction==1 && abort_calls==1);
 release_retained(&e);
 reset(&e,5);spi_do_xfer(&e,0);
 assert(e.transport_fault && !accepted && transaction==1 && !live);
 puts("PASS first-transfer ambiguity fences both TX-present and RX-only transactions");
 reset(&e,2);add_tx(&e);fail_remaining=1;abort_failures=2;spi_do_xfer(&e,0);
 assert(e.transport_fault && e.stop && accepted==1 && abort_calls==3 && elapsed==200 && !e.failed_rxbuf && live==1);
 release_retained(&e);
 puts("PASS failed DMA abort retains RX/TX and local stack until successful third abort; no replay");
 reset(&e,1);add_tx(&e);spi_do_xfer(&e,0);
 assert(transaction==4 && cs_high==4 && cs_low==4 && attempted==2 && accepted==1 && !live && !e.txbuf && !e.transport_fault);
 puts("PASS explicit rx_stall retains original packet across separate transactions and accepts once");
 reset(&e,0);add_tx(&e);fail_first_alloc=1;spi_do_xfer(&e,0);
 assert(transaction==1 && cs_high==2 && accepted==1 && !live && !e.transport_fault && e.stat.mem_err==1);
 puts("PASS proven zero-wire allocation failure remains retryable");
 reset(&e,7);ready=0;add_tx(&e);spi_do_xfer(&e,0);
 assert(ready_waits==2 && transaction==1 && cs_high==2 && accepted==1 && !live && !e.transport_fault);
 puts("PASS pre-transfer ready timeout remains retryable without creating a protocol fence");
 reset(&e,3);queue_full=1;stop_after=4;assert(spi_xfer_one(&e,NULL,1)==0);
 assert(e.stop && queue_calls==4 && elapsed==40 && !live && !e.transport_fault);
 puts("PASS external stop still escapes full RX queue; independent aggregate queue bound remains open");
 memset(&xfer_engine,0,sizeof xfer_engine);xfer_engine.initialized=1;xfer_engine.transport_fault=-3;
 struct spi_msg msg={0};uint8_t payload[4]={1,2,3,4};msg.op_type=SPI_MSG_OP_DATA;msg.data=payload;msg.data_len=4;
 unsigned prior=allocations;assert(spi_write(&msg,0)==-6 && spi_read(&msg,0)==-6 && allocations==prior);
 assert(spi_transaction_faulted()==-3);xfer_engine.transport_fault=0;xfer_engine.stop=1;
 assert(spi_write(&msg,0)==-6 && spi_read(&msg,0)==-6 && allocations==prior);
 puts("PASS fault/stop refuse new read/write before allocation and do not return soft BUSY");
#endif
 return 0;
}
'''

def spi(root,candidate):
    captured=[];framing.ROOT=root;framing.run_native=captured.append;framing.main();code=captured[0]
    prefix=framing.PREFIX.replace('static int spi_port_is_ready(void){return 1;}','static int spi_port_is_ready(void);')
    prefix=prefix.replace('static int spi_port_abort(void){return 0;}','static int spi_port_abort(void);').replace('static void vTaskDelay(unsigned n){(void)n;}','static void vTaskDelay(unsigned n);')
    prefix=prefix.replace('static unsigned live,allocations','static unsigned fail_first_alloc;\nstatic unsigned live,allocations')
    prefix=prefix.replace(' if (fail_small && allocations==2) return NULL;',' if(fail_first_alloc){fail_first_alloc=0;return NULL;}\n if (fail_small && allocations==2) return NULL;')
    mocks=pressure.MOCKS.replace('static unsigned fail_first_alloc;','static unsigned abort_failures,ready_waits;')
    mocks=mocks.replace(' if(event==SPI_EVT_HDR_ACKED', ' if(event==SPI_EVT_TXN_RDY && ms>0 && scenario==7){return ++ready_waits>1;}\n if(event==SPI_EVT_HDR_ACKED')
    mocks=mocks.replace(' memcpy(rx,wire,n);wire_offset=n;', ' if(scenario==4)((struct spi_header*)wire)->magic=0;\n if(scenario==5)return -1;\n memcpy(rx,wire,n);wire_offset=n;')
    mocks=mocks.replace(' if((scenario==1 && transaction==4)', ' if(scenario==0 || scenario==7)ready=0;\n if((scenario==1 && transaction==4)')
    mocks+='''
static int spi_port_is_ready(void){return ready;}
static int spi_port_abort(void){++abort_calls;return abort_calls<=abort_failures?-1:0;}
static void vTaskDelay(unsigned n){elapsed+=n;if(abort_failures && abort_calls<=abort_failures){assert(active->failed_rxbuf && active->txbuf && live==2);}}
'''
    source=(root/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.c').read_text()
    extra=''
    if candidate:
        header=(root/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.h').read_text()
        mocks='static struct spi_xfer_engine xfer_engine;\n'+mocks
        mocks+='\ntypedef int BaseType_t;typedef unsigned TickType_t;\n#define portMAX_DELAY 0xffffffffU\n#define SPI_EVT_TXN_PENDING 1U\n'
        mocks+='\n'.join(x for x in header.splitlines() if x.startswith('#define SPI_MSG_') and '(' not in x)+'\n'
        mocks+='\n'.join(block(header,r'^struct '+n+r'\s*\{')+';' for n in ('spi_msg_control','spi_msg'))
        mocks+='\nstatic int xQueueReceive(void*q,void*p,unsigned n){assert(0);return 0;}\nstatic int xEventGroupSetBits(void*p,unsigned n){assert(0);return 0;}\n'
        extra='\n'.join(block(source,r'^(?:static )?[^\n;]*\b'+n+r'\([^;]*?\)\s*\{') for n in ('spi_transaction_faulted','spi_read','spi_write'))
    actual=block(source,r'^static int32_t spi_do_xfer\([^;]*?\)\s*\{')
    code=code.replace(framing.PREFIX,prefix).replace(framing.MOCKS,mocks).replace(framing.TESTS,actual+extra+SPI_TESTS)
    return '#define CANDIDATE '+str(int(candidate))+'\n#define SPI_XFER_PROTOCOL_ERROR (-4)\n#define SPI_XFER_MAX_RETRIES 3U\n#define SPI_XFER_MAX_CONTIGUOUS_BURST 8U\n#define SPI_XFER_F_SKIP_FIRST_TXN_WAIT 1U\n'+code

def parser(root):
    base=ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at'
    common=(root/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c').read_text()
    prefix=fs.PREFIX.replace('struct modem {struct modem_iface iface;', 'struct modem {struct modem_cmd_handler_data handler_data;struct modem_iface iface;')
    prefix=prefix.replace('static unsigned critical,','static unsigned spi_fault,delay_count,fault_on_receive;\nstatic int spi_transaction_faulted(void){return (int)spi_fault;}\nstatic void vTaskDelay(unsigned n){assert(n==1);++delay_count;}\nstatic unsigned critical,')
    prefix=prefix.replace(' ++reads;ownership=1;', ' if(fault_on_receive)spi_fault=1;\n ++reads;ownership=1;')
    added=r'''
 struct modem guard={0};uint8_t out[8];size_t n=99;
 reads=freed=ownership=0;spi_fault=1;delay_count=0;memset(out,0xa5,sizeof out);
 assert(modem_iface_spi_read(&guard.iface,out,8,&n)==-EIO && !n && !reads && !freed && guard.handler_data.tx_desynchronized && delay_count==1);
 spi_fault=0;guard.handler_data.tx_desynchronized=false;packet_size=8;memset(packet,0x45,8);
 assert(!modem_iface_spi_read(&guard.iface,out,2,&n) && n==2 && ownership && !freed);
 unsigned offset=(unsigned)guard.spi_rx_pending_offset;spi_fault=1;n=99;memset(out,0xa5,sizeof out);
 assert(modem_iface_spi_read(&guard.iface,out,8,&n)==-EIO && !n && guard.spi_rx_pending_offset==offset && !freed && ownership && out[0]==0xa5);
 BusIo_SPI_Free(guard.spi_rx_pending);guard.spi_rx_pending=NULL;
 puts("PASS sticky fault blocks new packet read and retained parser tail without early free");
 memset(&guard,0,sizeof guard);reads=freed=ownership=0;spi_fault=0;fault_on_receive=1;n=99;memset(out,0xa5,sizeof out);
 assert(modem_iface_spi_read(&guard.iface,out,8,&n)==-EIO && !n && ownership && !freed && out[0]==0xa5 && guard.handler_data.tx_desynchronized);
 BusIo_SPI_Free(guard.spi_rx_pending);
 puts("PASS fault racing queued receive publishes zero bytes and retains ownership for teardown");
'''
    tests=fs.TESTS.replace('puts("LIMIT hardware',added+'\n puts("LIMIT hardware')
    return prefix+extract_function(common,'modem_iface_spi_read')+extract_function((base/'modem_cmd_handler.c').read_text(),'cmd_handler_process_iface_data')+extract((base/'w61_at_sys.c').read_text(),'on_cmd_fs_readfile',True)+tests

def coordinator(root):
    source=(root/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    prefix=recovery.PREFIX.replace('static int spi_transaction_faulted(void){return 0;}','')+'\nstatic int spi_fault;static int spi_transaction_faulted(void){return spi_fault;}\n'
    tests=recovery.TESTS.replace(' return 0;',r'''
 reset();spi_fault=-3;radio_recovery_pump();
 assert(driver.Modem.handler_data.tx_desynchronized && radio_recovery.state==1 && paused==1 && !destructions && !inits);
 cloud_ack=0;radio_recovery_execute();assert(!destructions && !inits && radio_recovery.state==1);
 puts("PASS transport fault requests existing owner barrier, fences AT, and waits for Cloud without direct reset");
 return 0;''')
    return prefix+'\n'.join(block(source,r'^(?:static )?[^\n;]*\b'+n+r'\([^;]*?\)\s*\{') for n in ('WIFI_BLE_App_RequestRadioRecovery','radio_recovery_pump','radio_recovery_execute'))+tests

def availability(root):
    source=(root/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    prefix=service.PREFIX.replace('static struct {struct {unsigned operation_active;}status;unsigned active_operation;}control;', 'typedef struct {struct {unsigned operation_active;}status;unsigned active_operation;} Control;static Control control;').replace('typeof_control_placeholder','Control')
    prefix+='\nstatic int spi_fault;static int spi_transaction_faulted(void){return spi_fault;}\n'
    tests=service.TESTS.replace('return 0;',r'''
 radio_recovery.state=0;reset();spi_fault=-3;WIFI_BLE_App_GetServiceStatus(&s);
 assert(s.state==2 && !strcmp(s.reason,"SPI_FENCED") && !driver.Modem.handler_data.tx_desynchronized && !irq);
 puts("PASS SPI fault immediately closes public admission; snapshot does not mutate AT owner");return 0;''')
    return prefix+extract_function(source,'WIFI_BLE_App_GetServiceStatus')+tests

def framing_suite(root):
    captures=[];framing.ROOT=root;framing.run_native=captures.append;framing.main();return captures[0].replace('#define SPI_XFER_TRANSPORT_ERROR (-3)','#define SPI_XFER_TRANSPORT_ERROR (-3)\n#define SPI_XFER_PROTOCOL_ERROR (-4)')

def shutdown_suite(root):
    source=(root/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.c').read_text()
    prefix=shutdown.PREFIX.replace('int initialized;','int initialized;volatile int transport_fault;')
    tests=shutdown.TESTS.replace(' reset();ack=0;',' reset();xfer_engine.transport_fault=-3;ack=0;').replace(' reset();abort_ok=0;',' reset();xfer_engine.transport_fault=-3;abort_ok=0;').replace('puts("PASS failed DMA abort', 'assert(xfer_engine.transport_fault==-3);puts("PASS failed DMA abort').replace('assert(!xfer_engine.txbuf && !xfer_engine.task);','assert(!xfer_engine.txbuf && !xfer_engine.task && !xfer_engine.transport_fault);')
    return prefix+extract_function(source,'spi_transaction_quiesce')+extract_function(source,'spi_transaction_deinit')+tests

def write_bridge(root):
    source=(root/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c').read_text()
    prefix=r'''
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <assert.h>
#define EIO 5
#define EBUSY 16
#define SPI_MSG_CTRL_TRAFFIC_AT_CMD 0U
#define IO_SEND_TIMEOUT 2000U
#define portTICK_PERIOD_MS 1U
#define pdMS_TO_TICKS(n) (n)
#define AT_LOG_HOST_OUT(...) ((void)0)
#define Debug_UART_NcpTrace(...) ((void)0)
#define CONTAINER_OF(p,t,f) ((t*)((char*)(p)-offsetof(t,f)))
struct modem_iface {unsigned marker;};
struct modem_cmd_handler_data {bool tx_desynchronized;};
struct modem {struct modem_iface iface;struct modem_cmd_handler_data handler_data;unsigned notify_phase;void*notify_owner;};
static int fault,result;static unsigned writes,last_budget;
static int spi_transaction_faulted(void){return fault;}
static void *xTaskGetCurrentTaskHandle(void){return (void*)1;}
static unsigned modem_cmd_handler_budget(struct modem_cmd_handler_data*p,unsigned n){assert(n==2000);return 700;}
static int BusIo_SPI_SendData(unsigned type,uint8_t*p,size_t n,unsigned timeout){assert(type==0 && n==4);++writes;last_budget=timeout;return result;}
'''
    tests=r'''
int main(void){struct modem m={0};uint8_t data[4]={1,2,3,4};
 fault=-3;assert(modem_iface_spi_write(&m.iface,data,4)==-EIO && !writes && m.handler_data.tx_desynchronized);
 assert(modem_iface_spi_write(&m.iface,data,0)==0 && !writes && m.handler_data.tx_desynchronized);
 puts("PASS sticky bus fault fences AT write without touching SPI queue; zero-length call sends nothing");
 fault=0;m.handler_data.tx_desynchronized=false;m.notify_phase=1;m.notify_owner=(void*)1;
 result=-3;assert(modem_iface_spi_write(&m.iface,data,4)==-EBUSY && !last_budget);
 result=-5;assert(modem_iface_spi_write(&m.iface,data,4)==-EBUSY);
 result=-6;assert(modem_iface_spi_write(&m.iface,data,4)==-6 && !m.handler_data.tx_desynchronized);
 puts("PASS only existing zero-byte allocation/queue failures map to notification BUSY; hard lifecycle fault is not retryable BUSY");
 m.notify_phase=0;result=4;assert(modem_iface_spi_write(&m.iface,data,4)==4 && last_budget==700);
 result=-3;assert(modem_iface_spi_write(&m.iface,data,4)==-3 && last_budget==700);
 puts("PASS ordinary owner retains its existing scoped bus budget and error semantics");return 0;}
'''
    return prefix+extract_function(source,'modem_iface_spi_write')+tests

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--suite',choices=['spi','parser','coordinator','availability','framing','shutdown','write_bridge'],required=True);a.add_argument('--baseline',action='store_true');a.add_argument('--label',required=True);args=a.parse_args()
    root=ROOT if args.baseline else OUT/'candidate'
    code=spi(root,not args.baseline) if args.suite=='spi' else {'parser':parser,'coordinator':coordinator,'availability':availability,'framing':framing_suite,'shutdown':shutdown_suite,'write_bridge':write_bridge}[args.suite](root)
    path=OUT/(args.label+'.c');assert not path.exists();path.write_text(code,newline='\n');run_native(code)
