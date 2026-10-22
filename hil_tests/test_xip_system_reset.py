"""Compile actual XIP reset source with register/IRQ/reset mocks only."""
from pathlib import Path
from test_xip_boot import run_native

HARNESS=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define N6_RESET_HOST_TEST 1
typedef struct {volatile uint32_t CCIPR6,CCIPR7,CCIPR8,CCIPR13,SR;} Regs;
static Regs regs;
#define RCC (&regs)
#define RCC_CCIPR13_USART1SEL 7U
#define RCC_CCIPR13_USART2SEL 0x70U
#define RCC_CCIPR13_UART4SEL 0x7000U
#define RCC_CCIPR13_UART5SEL 0x70000U
#define RCC_CCIPR6_OTGPHY1CKREFSEL 0x10000U
#define RCC_CCIPR6_XSPI1SEL 3U
#define RCC_CCIPR7_PERSEL 7U
#define RCC_CCIPR7_RTCSEL 0x300U
#define RCC_CCIPR7_RTCSEL_Pos 8U
#define RCC_CCIPR8_SDMMC1SEL 3U
#define RCC_CCIPR8_SDMMC2SEL 0x30U
#define RCC_SR_HSIRDY 8U
#define RCC_SR_HSERDY 16U
#define RCC_SR_LSIRDY 1U
static unsigned mask,resets,writes,barriers,drop;
static unsigned __get_PRIMASK(void){return mask;}
static void __disable_irq(void){mask=1;}
static void __set_PRIMASK(unsigned n){mask=n;}
static void __DSB(void){barriers++;}
static void __ISB(void){barriers++;}
static void NVIC_SystemReset(void){
 assert(mask==1);assert((regs.CCIPR6&0x10000)==0);assert((regs.CCIPR13&7)==0);resets++;
}
static void Debug_UART_Log(const char*a,const char*b,...){(void)a;(void)b;}
static void write_reg(volatile uint32_t*p,uint32_t v){
 assert(mask==1);writes++;
 if((drop==1&&p==&regs.CCIPR13)||(drop==2&&p==&regs.CCIPR6))return;
 *p=v;
}
#define N6_RESET_WRITE(reg,value) write_reg(&(reg),(value))
#include "xip_system_reset.c"
static void init(void){memset(&regs,0,sizeof(regs));regs.CCIPR6=0x40010000;regs.CCIPR13=0x80000006;regs.CCIPR7=0x80000200;regs.CCIPR8=0x80000000;regs.SR=25;mask=resets=writes=barriers=drop=0;}
int main(void){
 unsigned cases=0;init();assert(N6_SystemReset()==0);assert(resets==1&&writes==2&&barriers>=2);assert(regs.CCIPR6==0x40000000&&regs.CCIPR13==0x80000000);cases++;
 init();regs.CCIPR6&=~0x10000;regs.CCIPR13&=~7;assert(N6_SystemReset()==0&&resets==1);cases++;
 for(unsigned bit=1;bit<=16;bit<<=1){if(!(25&bit))continue;init();regs.SR&=~bit;assert(N6_SystemReset()==-1&&!writes&&!resets&&!mask);cases++;}
 for(unsigned i=0;i<5;i++){
  init();if(i==0)regs.CCIPR6|=1;else if(i==1)regs.CCIPR7|=2;else if(i==2)regs.CCIPR7&=~0x300;else if(i==3)regs.CCIPR8|=1;else regs.CCIPR13|=0x10;
  assert(N6_SystemReset()==-2&&!writes&&!resets&&!mask);cases++;
 }
 for(unsigned which=1;which<=2;which++)for(unsigned prior=0;prior<=1;prior++){
  init();drop=which;mask=prior;assert(N6_SystemReset()==-3&&!resets&&mask==prior);
  assert(regs.CCIPR6==0x40010000&&regs.CCIPR13==0x80000006);cases++;
 }
 init();mask=1;assert(N6_SystemReset()==0&&resets==1&&mask==1);cases++;
 printf("PASS %u actual-C reset scenarios: clocks/defaults/readback/IRQ preservation; no hardware reset\n",cases);
}
'''


if __name__=='__main__':
    run_native(HARNESS,extra_includes=[Path(__file__).resolve().parents[1]/'Tools'])
