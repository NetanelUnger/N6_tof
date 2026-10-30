"""Actual bounded time reporter with hardware/UART mocked; no device access."""
from pathlib import Path
from test_xip_boot import run_native
HARNESS=r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#define N6_RESOURCE_DIAGNOSTICS 1
#define TX_TIMER_TICKS_PER_SECOND 100
static uint32_t tick,mask,isr,calls,maxlen;static int fail;
uint32_t tx_time_get(void){return tick;}
uint32_t __get_PRIMASK(void){return mask;}
uint32_t __get_IPSR(void){return isr;}
void __disable_irq(void){mask=1;}
void __set_PRIMASK(uint32_t p){mask=p;}
int Debug_UART_Write(const void*p,size_t n){
 assert(n<=96&&((const char*)p)[n-2]=='\r'&&((const char*)p)[n-1]=='\n');
 ++calls;if(n>maxlen)maxlen=(uint32_t)n;return fail?-1:0;
}
#define N6_TIME_CAPTURE(a,b) do{for(unsigned i=0;i<8;++i){(a)[i]=UINT32_MAX;(b)[i]=UINT32_MAX;}}while(0)
#include "timebase_probe_impl.inc"
int main(void){
 Debug_UART_TimeProbePoll();assert(!calls);
 mask=1;Debug_UART_StartTimeProbe();assert(mask==1&&time_probe_remaining==30);mask=0;
 tick=99;Debug_UART_TimeProbePoll();assert(!calls);
 tick=100;Debug_UART_TimeProbePoll();assert(calls==2&&time_probe_remaining==29);
 Debug_UART_TimeProbePoll();assert(calls==2);
 tick=200;isr=1;Debug_UART_TimeProbePoll();assert(calls==2);isr=0;
 fail=1;Debug_UART_TimeProbePoll();assert(calls==4);Debug_UART_TimeProbePoll();assert(calls==4);
 fail=0;for(unsigned i=0;i<100;++i){tick+=100;Debug_UART_TimeProbePoll();}
 assert(calls==60&&time_probe_remaining==0&&maxlen==82);
 tick=UINT32_MAX-49;Debug_UART_StartTimeProbe();tick=50;Debug_UART_TimeProbePoll();assert(calls==62);
 puts("PASS bounded30samples/60lines,96byte capacity, no formatter, RTOS pacing with stalledHAL, ISR gate, queue failure rate and wrap");
}
'''
if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    run_native(HARNESS,extra_includes=[root/'AppliNonSecure/Core/Src'],retain_artifacts=True)
