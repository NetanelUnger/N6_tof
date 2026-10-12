"""Execute production SPI packet framing with synthetic public FS replies.

Mock only the byte transfer, allocator and scheduler/queue boundary. This tests
header-first/remaining transfer, alignment and short-packet resizing before the
existing retained-copy/parser tests. It cannot prove DMA, wire or NCP FS state.
"""
import re
from test_wifi_scan_lifetime import ROOT, run_native


def block(source, pattern):
    match = re.search(pattern, source, re.M)
    assert match, pattern
    end = source.index('{', match.start()) + 1
    level = 1
    while level:
        level += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]


PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <inttypes.h>
typedef void *TaskHandle_t;
typedef void *EventGroupHandle_t;
typedef void *QueueHandle_t;
#define SPI_BUF_ALIGN_MASK 3U
#define SPI_XFER_TXN_RDY_TIMEOUT (-2)
#define SPI_XFER_TRANSPORT_ERROR (-3)
#define SPI_EVT_TXN_RDY 2U
#define SPI_EVT_HDR_ACKED 4U
#define SPI_EVT_HW_XFER_DONE 8U
#define SPI_WAIT_TXN_TIMEOUT_MS 2000
#define SPI_WAIT_HDR_ACK_TIMEOUT_MS 100
#define SPI_STAT_INC(s,m,v) ((s)->m += (v))
#define pdMS_TO_TICKS(n) (n)
#define pdTRUE 1
#define spi_err(...) ((void)0)
#define spi_trace(...) ((void)0)
static unsigned live,allocations,fail_small,reads,wire_offset,queue_calls;
static unsigned first_size,second_size,fail_read;
static uint8_t wire[4096];
static struct spi_buffer *received;
static void *pvPortMalloc(size_t n) {
 ++allocations;
 if (fail_small && allocations==2) return NULL;
 void *p=malloc(n);assert(p);++live;return p;
}
static void vPortFree(void *p) {assert(p && live);--live;free(p);}
static unsigned Debug_UART_NcpTraceEnabled(void){return 0;}
static void Debug_UART_NcpTerminalObservedAtSpi(void){assert(0);}
static void *spi_port_memcpy(void *d,const void *s,size_t n){return memcpy(d,s,n);}
static void spi_port_set_phase(unsigned n){(void)n;}
static int spi_port_is_ready(void){return 1;}
static int spi_port_abort(void){return 0;}
static void vTaskDelay(unsigned n){(void)n;}
'''

MOCKS = r'''
static int32_t spi_wait_event(void *e,uint32_t event,int32_t ms){(void)e;(void)event;(void)ms;return 1;}
static int32_t spi_clear_event(struct spi_xfer_engine *e,uint32_t event){(void)e;(void)event;return 0;}
static int read_bytes(void *dest,unsigned n) {
 assert(n%4==0 && wire_offset+n<=sizeof wire);
 ++reads;if(reads==fail_read)return -1;
 memcpy(dest,wire+wire_offset,n);wire_offset+=n;return 0;
}
static int32_t spi_txrx(struct spi_xfer_engine *e,void *tx,void *rx,uint16_t n) {
 (void)e;assert(tx && !reads);first_size=n;return read_bytes(rx,n);
}
static int32_t spi_rx(struct spi_xfer_engine *e,void *rx,uint16_t n) {
 (void)e;assert(reads==1);second_size=n;return read_bytes(rx,n);
}
static int xQueueSend(QueueHandle_t q,void *p,unsigned wait) {
 assert(q==(void*)1 && wait==10 && !received);
 received=*(struct spi_buffer**)p;++queue_calls;return pdTRUE;
}
'''

TESTS = r'''
static void packet(const uint8_t *payload,unsigned len,unsigned txlen,unsigned small_fail) {
 struct spi_xfer_engine e={0};
 struct spi_buffer *tx=NULL;
 assert(!live && !received);
 memset(wire,0xA5,sizeof wire);
 struct spi_header *h=(struct spi_header*)wire;
 SPI_HEADER_INIT(h,SPI_MSG_CTRL_TRAFFIC_AT_CMD,len);
 memcpy(wire+sizeof *h,payload,len);
 if(txlen){
   tx=spi_buffer_alloc(txlen,sizeof *h);
   assert(tx);memset(tx->data,0xC3,txlen);
   assert(spi_buffer_push(tx,sizeof *h));
   e.txbuf=tx;
 }
 allocations=reads=wire_offset=queue_calls=first_size=second_size=0;
 fail_small=small_fail;fail_read=0;
 e.rxq[0]=(void*)1;e.rxq_bound=1;
 assert(spi_xfer_one(&e,tx,1)==0);
 assert(received && received->len==len && queue_calls==1);
 assert(memcmp(received->data,payload,len)==0);
 assert(spi_buffer_get_traffic_type(received)==SPI_MSG_CTRL_TRAFFIC_AT_CMD);
 assert(e.stat.rx_bytes==len && e.stat.rx_pkts==1 && !e.txbuf);
 unsigned expected_first=txlen ? ((txlen+sizeof *h+3)&~3U) : sizeof *h;
 unsigned expected_second=len+sizeof *h>expected_first ?
   ((len+sizeof *h-expected_first+3)&~3U) : 0;
 assert(first_size==expected_first && second_size==expected_second);
 assert(reads==1+(expected_second!=0));
 assert(e.stat.mem_err==(small_fail && len<256));
 spi_buffer_free(received);received=NULL;assert(!live);
}
int main(void){
 assert(sizeof(struct spi_header)==8);
 /* Public response with the real NUL byte, and the previously observed
    malformed response without it. Preserve their distinct exact lengths. */
 const uint8_t valid[]={'+','F','S',':','R','E','A','D',',','1',',',0,'\r','\n'};
 const uint8_t absent[]="+FS:READ,1,\r\n";
 unsigned txsizes[]={0,1,3,4,8,13,14,64,255,256,SPI_XFER_MTU_BYTES};
 for(unsigned i=0;i<sizeof txsizes/sizeof *txsizes;i++){
   packet(valid,sizeof valid,txsizes[i],0);
   packet(absent,sizeof absent-1,txsizes[i],0);
 }
 puts("PASS real NUL remains 14 bytes; absent payload remains 13 bytes across 11 aligned TX/header/remaining-transfer boundaries");
 uint8_t values[SPI_XFER_MTU_BYTES];
 for(unsigned i=0;i<sizeof values;i++)values[i]=(uint8_t)i;
 unsigned lengths[]={1,3,4,7,8,13,14,31,255,256,257,SPI_XFER_MTU_BYTES};
 for(unsigned j=0;j<sizeof lengths/sizeof *lengths;j++)
   for(unsigned i=0;i<sizeof txsizes/sizeof *txsizes;i++)
     packet(values,lengths[j],txsizes[i],0);
 puts("PASS all 256 byte values unchanged; 132 short-resize/full-buffer MTU and TX/RX length combinations");
 packet(valid,sizeof valid,0,1);
 packet(absent,sizeof absent-1,14,1);
 puts("PASS failed small-buffer resize retains exact original packet and releases each allocation once");
 for(unsigned step=1;step<=2;step++){
   struct spi_xfer_engine e={0};e.rxq[0]=(void*)1;e.rxq_bound=1;
   memset(wire,0,sizeof wire);SPI_HEADER_INIT((struct spi_header*)wire,0,sizeof valid);
   memcpy(wire+8,valid,sizeof valid);
   allocations=reads=wire_offset=queue_calls=0;fail_small=0;fail_read=step;
   assert(spi_xfer_one(&e,NULL,0)==SPI_XFER_TRANSPORT_ERROR);
   assert(!received && !live && !queue_calls);
 }
 puts("PASS either transfer failure publishes no partial FS packet and frees RX only after successful local abort");
 return 0;
}
'''


def main():
    source = (ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.c').read_text()
    header = (ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.h').read_text()
    config = (ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_default_config.h').read_text()
    mtu = re.search(r'^#define W61_MAX_SPI_XFER\s+(\d+U)', config, re.M)[1]
    structs = '\n'.join(block(header, r'^struct '+name+r'\s*\{')+';' for name in ('spi_stat','spi_buffer'))
    traffic = re.search(r'typedef enum\s*\{[^}]*SPI_MSG_CTRL_TRAFFIC_AT_CMD[^}]*\}\s*spi_msg_ctrl_t;', header)[0]
    callback = re.search(r'typedef void \(\*spi_rxd_notify_func_t\).*?;', header)[0]
    packet_header = block(source, r'^struct spi_header\s*\{')+';'
    engine = block(source, r'^struct spi_xfer_engine\s*\{')+';'
    init = re.search(r'^#define SPI_HEADER_INIT[^\n]*\\\n.*?while \(false\)', source, re.M | re.S)[0]
    states = re.search(r'enum\s*\{[^}]*SPI_XFER_STATE_IDLE[^}]*\};', source)[0]
    definitions = structs+traffic+callback+'\n#pragma pack(push,1)\n'+packet_header+'\n#pragma pack(pop)\n'+engine
    funcs = '\n'.join(block(source, r'^(?:static )?[^\n;]*\b'+name+r'\([^;]*?\)\s*\{')
                      for name in ('spi_buffer_set_traffic_type','spi_buffer_get_traffic_type',
                                   'spi_buffer_push','spi_buffer_pull','spi_buffer_alloc',
                                   'spi_buffer_free','spi_header_validate','spi_xfer_one'))
    run_native('#include <stdint.h>\n#define SPI_HEADER_MAGIC_CODE 0x55AAU\n'
               '#define SPI_XFER_MTU_BYTES '+mtu+'\n'+PREFIX+definitions+'\n'+states+'\n'+init+'\n'+MOCKS+funcs+TESTS)


if __name__ == '__main__':
    main()
