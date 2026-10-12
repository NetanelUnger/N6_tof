"""Actual FS reader/callback: bounds, terminal proof, returned-pointer lifetime."""
from test_wifi_scan_lifetime import ROOT, run_native
from test_wifi_assoc_admission import extract_function
from test_raw_send_response import extract

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#define EINVAL 22
#define EIO 5
#define EAGAIN 11
typedef unsigned TickType_t;
typedef unsigned W61_Status_t;
enum {W61_STATUS_OK,W61_STATUS_ERROR,W61_STATUS_TIMEOUT};
#define W61_CMDRSP_STRING_SIZE 128
#define W61_NCP_TIMEOUT 2000
#define MODEM_NO_TX_LOCK 1U
#define MODEM_TX_TRACK_RAW_WRITE 2U
#define W61_NULL_ASSERT(x) assert(x)
#define W61_NULL_ASSERT_STR(x,s) assert(x)
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define SYS_LOG_ERROR(...) ((void)0)
#define Debug_UART_Log(...) ((void)0)
#define portTICK_PERIOD_MS 1
static unsigned critical;
#define taskENTER_CRITICAL() (++critical)
#define taskEXIT_CRITICAL() (--critical)
struct modem_cmd_handler_data {void*user_data;uint8_t*rx_buf;unsigned rx_buf_len;unsigned sem_tx_lock;bool tx_desynchronized,raw_command_attempted;int last_error;};
struct modem {struct {void*cmd_handler_data;} handler;unsigned iface,sem_response;void*rx_data;uint32_t rx_data_len;};
typedef struct {struct modem Modem;} W61_Object_t;
#define MODEM_CMD_DIRECT_DEFINE(n) static int32_t n(struct modem_cmd_handler_data*data,uint16_t len,char**argv,uint16_t argc)
struct modem_cmd{const char*prefix;};
#define MODEM_CMD_DIRECT(s,f) {s}
static volatile uint32_t fs_read_callbacks,fs_read_declared,fs_read_available,fs_read_copied;
static unsigned mode,releases,wakes,ticks;
static int32_t modem_cmd_send_ext(unsigned*,void*,struct modem_cmd*,unsigned,const uint8_t*,unsigned,unsigned,unsigned);
static unsigned W61_Status(int r){return (unsigned)r;}
static unsigned xTaskGetTickCount(void){return ticks;}
static unsigned W61_AT_Common_TakeTxLockBudget(unsigned l,unsigned t,unsigned*s){*s=ticks;return mode==7?0:t;}
static unsigned W61_AT_Common_RemainingTxBudget(unsigned s,unsigned t){return t;}
static int xSemaphoreGive(unsigned sem){if(sem==1){assert(!critical);++releases;}else++wakes;return 1;}
static int modem_cmd_handler_set_error(struct modem_cmd_handler_data*d,int e){d->last_error=e;return 0;}
'''
STUB = r'''
static int32_t modem_cmd_send_ext(unsigned*i,void*h,struct modem_cmd*cmd,unsigned n,const uint8_t*text,unsigned sem,unsigned timeout,unsigned flags){
 struct modem_cmd_handler_data*d=((struct {void*cmd_handler_data;}*)h)->cmd_handler_data;
 struct modem*m=d->user_data;assert(flags==(MODEM_NO_TX_LOCK|MODEM_TX_TRACK_RAW_WRITE));
 assert(m->rx_data && m->rx_data_len==8 && n==1 && timeout==2000 && !critical);
 if(mode==1)return W61_STATUS_TIMEOUT; /* no bus submission */
 d->raw_command_attempted=true;
 if(mode==2)return W61_STATUS_TIMEOUT; /* unanswered wire command */
 if(mode==3)return W61_STATUS_ERROR; /* definite ERROR */
 if(mode==4)return W61_STATUS_OK; /* terminal without payload */
 uint8_t packet[40]={0};unsigned declared=mode==5?12:mode==6?4:8;
 unsigned prefix=(unsigned)sprintf((char*)packet,"+FS:READ,%u,",declared);
 if(mode==8){
  memcpy(packet+prefix,"abc\r\n",5);d->rx_buf=packet;d->rx_buf_len=prefix+5;
  assert(on_cmd_fs_readfile(d,9,NULL,0)==-EAGAIN && !fs_read_copied);
  return W61_STATUS_TIMEOUT;
 }
 for(unsigned j=0;j<declared;++j)packet[prefix+j]=(uint8_t)(j*11); /* embedded NUL is valid */
 d->rx_buf=packet;d->rx_buf_len=prefix+declared;
 assert(on_cmd_fs_readfile(d,9,NULL,0)==(mode==5||mode==6?-EINVAL:(int)d->rx_buf_len));
 if(mode==5||mode==6)d->last_error=0; /* a raced OK must not erase the fence */
 return W61_STATUS_OK;
}
'''
TESTS = r'''
int main(void){
 struct modem_cmd_handler_data d={0};W61_Object_t o={0};uint8_t out[10];
 o.Modem.handler.cmd_handler_data=&d;o.Modem.sem_response=2;d.user_data=&o.Modem;d.sem_tx_lock=1;
 for(mode=0;mode<=8;++mode){
  memset(out,0x5a,sizeof out);d.tx_desynchronized=false;releases=wakes=0;
  unsigned r=W61_FS_ReadFile(&o,"mock",0,out+1,8);
  assert(!critical && !o.Modem.rx_data && !o.Modem.rx_data_len);
  assert(out[0]==0x5a && out[9]==0x5a);
  if(!mode){assert(r==W61_STATUS_OK && !d.tx_desynchronized);for(unsigned j=0;j<8;++j)assert(out[1+j]==(uint8_t)(j*11));}
  else{assert(r!=W61_STATUS_OK);for(unsigned j=0;j<8;++j)assert(out[1+j]==0x5a);}
  assert(d.tx_desynchronized==(mode==2||mode==4||mode==5||mode==6||mode==8));
  assert(releases==(mode==7?0:1));
 }
 uint8_t packet[]="+FS:READ,8,abcdefgh";d.rx_buf=packet;d.rx_buf_len=sizeof(packet)-1;
 assert(on_cmd_fs_readfile(&d,9,NULL,0)==-EINVAL && d.tx_desynchronized && !critical);
 /* Missing bytes are never reconstructed, even with a complete terminal OK.
  * Test every partial prefix, both separator forms and real delimiter bytes. */
 const char *empty[]={"\r\nOK\r\n","\r\n\r\nOK\r\n"};
 for(unsigned form=0;form<2;++form){
  uint8_t p[40]={0},byte=0x5a;unsigned prefix=(unsigned)sprintf((char*)p,"+FS:READ,1,");
  unsigned length=(unsigned)strlen(empty[form]);memcpy(p+prefix,empty[form],length);
  o.Modem.rx_data=&byte;o.Modem.rx_data_len=1;d.tx_desynchronized=false;d.rx_buf=p;
  for(unsigned partial=0;partial<length;++partial){
   /* The parser writes a sentinel; restore the complete fixture each time. */
   memcpy(p+prefix,empty[form],length);d.rx_buf_len=prefix+partial;
   assert(on_cmd_fs_readfile(&d,9,NULL,0)==-EAGAIN && byte==0x5a && !d.tx_desynchronized);
  }
  memcpy(p+prefix,empty[form],length);d.rx_buf_len=prefix+length;
  assert(on_cmd_fs_readfile(&d,9,NULL,0)==-EIO && byte==0x5a && d.tx_desynchronized && !critical);
 }
 const uint8_t real[]={0,'\r','\n',0xff,'O'};
 for(unsigned j=0;j<sizeof real;++j){
  uint8_t p[40]={0},byte=0x5a;unsigned prefix=(unsigned)sprintf((char*)p,"+FS:READ,1,");
  p[prefix]=real[j];memcpy(p+prefix+1,"\r\nOK\r\n",6);
  o.Modem.rx_data=&byte;o.Modem.rx_data_len=1;d.tx_desynchronized=false;d.rx_buf=p;d.rx_buf_len=prefix+7;
  assert(on_cmd_fs_readfile(&d,9,NULL,0)==(int)(prefix+1) && byte==real[j] && !critical);
 }
 {uint8_t p[]="+FS:READ,1,\r\nERROR\r\n",byte=0x5a;
  o.Modem.rx_data=&byte;o.Modem.rx_data_len=1;d.rx_buf=p;d.rx_buf_len=sizeof(p)-1;
  assert(on_cmd_fs_readfile(&d,9,NULL,0)==-EAGAIN && byte==0x5a);}
 {uint8_t p[]="+FS:READ,65544,abcdefgh",byte[8]={0};
  fs_read_copied=0;
  o.Modem.rx_data=byte;o.Modem.rx_data_len=8;d.rx_buf=p;d.rx_buf_len=sizeof(p)-1;
  assert(on_cmd_fs_readfile(&d,9,NULL,0)==-EAGAIN && !fs_read_copied);
  for(unsigned j=0;j<8;++j)assert(!byte[j]);}
 puts("PASS actual NUL/CR/LF/binary bytes preserved; empty+OK never fabricates a byte");
 puts("PASS oversized declaration cannot wrap to caller's 8-byte length");
 puts("PASS exact binary payload bounded and output retired before AT release");
 puts("PASS pre-write timeout/definite ERROR preserve admission; unanswered submission fences");
 puts("PASS missing/short/oversized payload and raced OK cannot report success or overwrite memory");
 puts("PASS late callback with retired output never writes returned storage");return 0;
}
'''

def main():
    source=(ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_sys.c').read_text(encoding='utf-8')
    run_native(PREFIX+extract(source,'on_cmd_fs_readfile',True)+extract_function(source,'W61_FS_ReadFile')+STUB+TESTS)
if __name__=='__main__':main()
