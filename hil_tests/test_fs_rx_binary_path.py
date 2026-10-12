"""Actual SPI-to-parser copy/assembly and FS callback, with synthetic packets."""
from test_wifi_scan_lifetime import ROOT, run_native
from test_wifi_assoc_admission import extract_function
from test_raw_send_response import extract

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define EINVAL 22
#define EIO 5
#define EAGAIN 11
#define ENOMEM 12
#define RX_BUF_SIZE 4096U
#define portMAX_DELAY 0xffffffffU
#define SPI_MSG_CTRL_TRAFFIC_AT_CMD 0
#define AT_LOG_HOST_IN(...) ((void)0)
#define Debug_UART_NcpTrace(...) ((void)0)
#define SYS_LOG_ERROR(...) ((void)0)
#define CONTAINER_OF(p,t,f) ((t*)((char*)(p)-offsetof(t,f)))
static unsigned critical,freed,reads,wakes,packet_size;
#define taskENTER_CRITICAL() (++critical)
#define taskEXIT_CRITICAL() (--critical)
struct modem_iface {int32_t (*mdm_read)(struct modem_iface*,uint8_t*,size_t,size_t*);};
struct modem_cmd_handler_data {void*user_data;uint8_t*rx_buf;size_t rx_buf_len;
 bool tx_desynchronized;int last_error;};
struct modem {struct modem_iface iface;void*spi_rx_pending;uint8_t*spi_rx_pending_data;
 size_t spi_rx_pending_len,spi_rx_pending_offset;void*rx_data;uint32_t rx_data_len;unsigned sem_response;};
#define MODEM_CMD_DIRECT_DEFINE(n) static int32_t n(struct modem_cmd_handler_data*data,uint16_t len,char**argv,uint16_t argc)
static volatile uint32_t fs_read_callbacks,fs_read_declared,fs_read_available,fs_read_copied;
static uint8_t packet[1024];static unsigned ownership;
static int BusIo_SPI_ReceivePtr(unsigned type,void**owner,uint8_t**bytes,unsigned wait){
 assert(!reads && !freed && !ownership && !type && wait==portMAX_DELAY);
 ++reads;ownership=1;*owner=&ownership;*bytes=packet;return (int)packet_size;}
static int BusIo_SPI_Free(void*p){assert(p==&ownership && ownership && !freed);ownership=0;++freed;return 0;}
static int modem_cmd_handler_set_error(struct modem_cmd_handler_data*d,int e){d->last_error=e;return 0;}
static int xSemaphoreGive(unsigned s){++wakes;return 1;}
'''
TESTS = r'''
static void check(unsigned payload_size,unsigned room,bool empty){
 struct modem m={0};uint8_t collected[RX_BUF_SIZE+1]={0},out[260];
 struct modem_cmd_handler_data d={0};d.user_data=&m;d.rx_buf=collected;
 memset(out,0x5a,sizeof out);m.rx_data=out+1;m.rx_data_len=payload_size;
 reads=freed=ownership=wakes=fs_read_copied=0;
 unsigned prefix=(unsigned)sprintf((char*)packet,"+FS:READ,%u,",payload_size);
 if(!empty)for(unsigned i=0;i<payload_size;++i)packet[prefix+i]=(uint8_t)i;
 memcpy(packet+prefix+(empty?0:payload_size),"\r\nOK\r\n",6);
 packet_size=prefix+(empty?0:payload_size)+6;
 /* Force retained-packet copying through every destination room boundary. */
 unsigned copied=0;
 while(copied<packet_size){
  size_t n=0;assert(!modem_iface_spi_read(&m.iface,collected+copied,room,&n));
  assert(n && n<=room && !memcmp(collected+copied,packet+copied,n));copied+=(unsigned)n;
  assert(freed==(copied==packet_size));
 }
 d.rx_buf_len=copied;assert(reads==1 && freed==1 && !ownership && !m.spi_rx_pending);
 int r=on_cmd_fs_readfile(&d,9,NULL,0);
 if(empty){assert(r==-EIO && d.tx_desynchronized && !fs_read_copied);
  for(unsigned i=0;i<sizeof out;++i)assert(out[i]==0x5a);}
 else {assert(r==(int)(prefix+payload_size) && !d.tx_desynchronized);
  assert(out[0]==0x5a && out[payload_size+1]==0x5a);
  for(unsigned i=0;i<payload_size;++i)assert(out[1+i]==(uint8_t)i);}
 assert(!critical);
}
int main(void){
 for(unsigned room=1;room<=33;++room){check(1,room,false);check(6,room,false);
  check(256,room,false);check(1,room,true);}
 /* Actual collector publishes explicit byte count, including embedded NUL. */
 struct modem m={0};uint8_t collected[RX_BUF_SIZE+1]={0};
 m.iface.mdm_read=modem_iface_spi_read;
 struct modem_cmd_handler_data d={&m,collected,0,false,0};
 reads=freed=ownership=0;packet[0]='A';packet[1]=0;packet[2]='B';packet_size=3;
 assert(!cmd_handler_process_iface_data(&d,&m.iface));
 assert(d.rx_buf_len==3 && collected[0]=='A' && collected[1]==0 && collected[2]=='B' && freed==1);
 puts("PASS actual retained SPI copy and collector preserve embedded NUL and all256 byte values");
 puts("PASS33 room boundaries neither truncate nor release ownership early");
 puts("PASS exact FS payload copied; missing byte+OK rejected without fabricated NUL");
 puts("LIMIT hardware SPI queue/DMA and NCP file storage are not emulated");return 0;
}
'''
def main():
    base=ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at'
    common=(base/'w61_at_common.c').read_text(encoding='utf-8')
    handler=(base/'modem_cmd_handler.c').read_text(encoding='utf-8')
    fs=(base/'w61_at_sys.c').read_text(encoding='utf-8')
    run_native(PREFIX+extract_function(common,'modem_iface_spi_read')+
               extract_function(handler,'cmd_handler_process_iface_data')+
               extract(fs,'on_cmd_fs_readfile',True)+TESTS)
if __name__=='__main__':main()
