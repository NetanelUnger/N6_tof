"""Real parser timeout/retry/recovery; injected timestamps are not HIL wall time."""
from pathlib import Path
from test_xip_boot import run_native
HARNESS=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "xmodem_receiver.c"
static unsigned ack,nak,consume,finish,aborts;
static int send_byte(uint8_t b,void*p){(void)p;if(b==6)++ack;if(b==21)++nak;return 0;}
static int take(const uint8_t*p,size_t n,void*c){(void)p;(void)c;assert(n==128);++consume;return 0;}
static int end(void*p){(void)p;++finish;return 0;}
static void cancel(int32_t why,void*p){(void)why;(void)p;++aborts;}
int main(void){
 XMODEM_Receiver_t r;XMODEM_Callbacks_t cb={send_byte,take,end,cancel,0};
 uint8_t packet[133]={1,1,254};memset(packet+3,26,128);
 unsigned crc=xmodem_crc16(packet+3,128);packet[131]=(uint8_t)(crc>>8);packet[132]=(uint8_t)crc;
 assert(!XMODEM_Start(&r,&cb,0));XMODEM_Process(&r,packet,17,0);
 assert(r.packet_length==16&&r.packet_expected==132&&!consume);
 /* A stalled source clock cannot enforce a real wall bound: observed bug model. */
 for(unsigned wall=0;wall<25000;wall+=100)XMODEM_Poll(&r,0);assert(!nak);
 XMODEM_Poll(&r,9999);assert(!nak);XMODEM_Poll(&r,10000);assert(nak==1&&!r.packet_expected);
 XMODEM_Process(&r,packet,sizeof(packet),10001);assert(consume==1&&ack==1);
 XMODEM_Process(&r,packet,sizeof(packet),10002);assert(consume==1&&ack==2); /* lostACK retry idempotence */
 uint8_t eot=4;XMODEM_Process(&r,&eot,1,10003);assert(finish==1&&!XMODEM_IsActive(&r));
 assert(!XMODEM_Start(&r,&cb,UINT32_MAX-4999));XMODEM_Process(&r,packet,17,UINT32_MAX-4999);
 XMODEM_Poll(&r,4999);assert(nak==1);XMODEM_Poll(&r,5000);assert(nak==2);
 uint8_t can[2]={24,24};XMODEM_Process(&r,can,2,5001);assert(aborts==1&&!XMODEM_IsActive(&r));
 puts("PASS real parser10s boundary/wrap, stalledclock reproducer, partial recovery, valid subsequent transfer and duplicate block consumedonce; NOT hardwarewall acceptance");
}
'''
if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    run_native(HARNESS,extra_stubs={'debug_uart.h':'#define Debug_UART_Log(...) ((void)0)\n'},extra_includes=[root/'AppliNonSecure/Core/Src',root/'AppliNonSecure/Core/Inc'],retain_artifacts=True)
