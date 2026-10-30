"""Actual SPI worker under explicit protocol/resource fault models, never HIL."""
from pathlib import Path
import sys
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
sys.path.insert(0,str(ROOT/'hil_tests'))
import test_spi_fs_framing as fixture
from test_wifi_scan_lifetime import run_native

MOCKS=r'''
static unsigned transaction,cs_high,cs_low,accepted,attempted,abort_calls,elapsed;
static unsigned ready,scenario,fail_remaining,queue_full,ack_stuck,stop_after;
static unsigned fail_first_alloc;
static struct spi_xfer_engine *active;
static int32_t spi_wait_event(void *p,uint32_t event,int32_t ms){
 struct spi_xfer_engine *e=p;
 if(event==SPI_EVT_HDR_ACKED && ack_stuck){elapsed+=ms;if(++queue_calls==stop_after)e->stop=1;return 0;}
 return 1;
}
static int32_t spi_clear_event(struct spi_xfer_engine *e,uint32_t event){active=e;reads=wire_offset=0;return 0;}
static int32_t spi_txrx(struct spi_xfer_engine *e,void *tx,void *rx,uint16_t n){
 active=e;++transaction;++reads;assert(n%4==0);
 struct spi_header *sent=tx;
 unsigned stalled=scenario==1 && transaction<=2;
 unsigned payload=scenario==2 && transaction==1 ? 96 : scenario==3 ? 96 : 0;
 if(sent->len){++attempted;if(!stalled)++accepted;}
 memset(wire,0,sizeof wire);SPI_HEADER_INIT((struct spi_header*)wire,0,payload);
 ((struct spi_header*)wire)->rx_stall=stalled;
 memset(wire+sizeof(struct spi_header),0x51,payload);
 memcpy(rx,wire,n);wire_offset=n;
 if((scenario==1 && transaction==4)||(scenario==2 && transaction==2))ready=0;
 return 0;
}
static int32_t spi_rx(struct spi_xfer_engine *e,void *rx,uint16_t n){
 ++reads;if(fail_remaining){fail_remaining=0;return -1;}
 memcpy(rx,wire+wire_offset,n);wire_offset+=n;return 0;
}
static int xQueueSend(QueueHandle_t q,void *p,unsigned wait){
 assert(wait==10);++queue_calls;
 if(queue_full){elapsed+=wait;if(queue_calls==stop_after)active->stop=1;return 0;}
 assert(!received);received=*(struct spi_buffer**)p;return pdTRUE;
}
static int spi_port_set_cs(unsigned on){if(on)++cs_high;else ++cs_low;return 0;}
static struct spi_buffer *spi_get_txbuf(struct spi_xfer_engine *e){return e->txbuf;}
'''

TESTS=r'''
static void reset(struct spi_xfer_engine *e,unsigned which){
 assert(!live && !received);memset(e,0,sizeof *e);scenario=which;
 transaction=cs_high=cs_low=accepted=attempted=abort_calls=elapsed=0;
 allocations=reads=wire_offset=queue_calls=fail_small=fail_first_alloc=0;
 queue_full=ack_stuck=stop_after=fail_remaining=0;ready=1;
 e->rxq[0]=(void*)1;e->rxq_bound=1;active=e;
}
static void add_tx(struct spi_xfer_engine *e){
 e->txbuf=spi_buffer_alloc(4,sizeof(struct spi_header));assert(e->txbuf);
 assert(spi_buffer_push(e->txbuf,sizeof(struct spi_header)));
}
int main(void){
 struct spi_xfer_engine e;
 reset(&e,1);add_tx(&e);spi_do_xfer(&e,0);
 assert(transaction==4 && cs_high==4 && cs_low==4 && attempted==2 && accepted==1 && !live && !e.txbuf);
 puts("PASS actual rx_stall retains the same TX across separate CS cycles, sends empty probes until clear, and releases only after one modeled acceptance");
 reset(&e,0);add_tx(&e);struct spi_buffer *saved=e.txbuf;
 fail_first_alloc=1;assert(spi_xfer_one(&e,e.txbuf,1)==-1);
 assert(!transaction && e.txbuf==saved && live==1 && e.stat.mem_err==1);
 spi_buffer_free(e.txbuf);e.txbuf=NULL;
 puts("PASS first RX allocation failure sends no SPI bytes and preserves the exact owned TX packet");
 reset(&e,3);queue_full=1;stop_after=4;
 assert(spi_xfer_one(&e,NULL,1)==0 && e.stop && queue_calls==4 && elapsed==40 && !live && e.stat.rx_drop==1);
 puts("PASS full RX queue cooperatively exits on stop and frees one retained packet; NO independent total-wait bound proven");
 reset(&e,0);ack_stuck=1;stop_after=3;
 assert(spi_xfer_one(&e,NULL,1)==0 && e.stop && elapsed==300 && e.stat.wait_hdr_ack_timeouts==2 && !live);
 puts("REPRODUCED header ACK remains high: repeated 100ms waits require ready-low or external stop; no total operation deadline in this loop");
 reset(&e,2);add_tx(&e);fail_remaining=1;spi_do_xfer(&e,0);
 assert(transaction==2 && cs_high==2 && cs_low==2 && accepted==2 && attempted==2 && abort_calls==2 && !live && !e.txbuf);
 puts("REPRODUCED no-replay criterion FAIL in injected model: full TX accepted, remaining RX fails, worker transmits identical TX again; physical NCP acceptance remains unknown");
 return 0;
}
'''

if __name__=='__main__':
    captured=[];fixture.run_native=captured.append;fixture.main()
    code=captured[0]
    prefix=fixture.PREFIX.replace('static int spi_port_is_ready(void){return 1;}', 'static int spi_port_is_ready(void);')
    prefix=prefix.replace('static int spi_port_abort(void){return 0;}','static int spi_port_abort(void);')
    prefix=prefix.replace('static void vTaskDelay(unsigned n){(void)n;}','static void vTaskDelay(unsigned n);')
    prefix=prefix.replace(' if (fail_small && allocations==2) return NULL;',
        ' if (fail_first_alloc){fail_first_alloc=0;return NULL;}\n if (fail_small && allocations==2) return NULL;')
    prefix=prefix.replace('static unsigned live,allocations', 'static unsigned fail_first_alloc;\nstatic unsigned live,allocations')
    mocks=MOCKS.replace('static unsigned fail_first_alloc;','')
    mocks+='\nstatic int spi_port_is_ready(void){return ready;}\nstatic int spi_port_abort(void){++abort_calls;return 0;}\nstatic void vTaskDelay(unsigned n){elapsed+=n;}\n'
    source=(ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.c').read_text()
    actual_do=fixture.block(source,r'^static int32_t spi_do_xfer\([^;]*?\)\s*\{')
    code=code.replace(fixture.PREFIX,prefix).replace(fixture.MOCKS,mocks).replace(fixture.TESTS,actual_do+TESTS)
    code='#define SPI_XFER_MAX_RETRIES 3U\n#define SPI_XFER_MAX_CONTIGUOUS_BURST 8U\n#define SPI_XFER_F_SKIP_FIRST_TXN_WAIT 1U\n'+code
    run_native(code)
