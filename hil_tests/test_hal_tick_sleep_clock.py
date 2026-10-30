"""Actual project HAL timebase initialization with only register/HAL calls mocked."""
from pathlib import Path
from test_xip_boot import run_native
STUB=r'''
#ifndef TIME_STUB
#define TIME_STUB
#include <stdint.h>
#include <assert.h>
#define __attribute__(x)
typedef int HAL_StatusTypeDef;
#define HAL_OK 0
#define HAL_ERROR 1
#define TIM6 ((void*)6)
#define TIM6_IRQn 6
#define TIM_COUNTERMODE_UP 0
#define TIM_IT_UPDATE 1
typedef struct {void*Instance;struct {uint32_t Period,Prescaler,ClockDivision,CounterMode;}Init;} TIM_HandleTypeDef;
static unsigned clock_on,sleep_clock,priority,irq_on,init_error,start_error,interrupts;
#define __HAL_RCC_TIM6_CLK_ENABLE() (++clock_on)
#define __HAL_RCC_TIM6_CLK_SLEEP_ENABLE() (sleep_clock|=0x10U)
#define __HAL_TIM_DISABLE_IT(p,m) (interrupts&=~(m))
#define __HAL_TIM_ENABLE_IT(p,m) (interrupts|=(m))
static void HAL_NVIC_SetPriority(unsigned n,unsigned p,unsigned s){assert(n==6&&!s);priority=p;}
static void HAL_NVIC_EnableIRQ(unsigned n){assert(n==6);irq_on=1;}
static uint32_t HAL_RCCEx_GetTIMGFreq(void){return 400000000;}
static int HAL_TIM_Base_Init(TIM_HandleTypeDef*p){assert(p->Instance==TIM6);return init_error;}
static int HAL_TIM_Base_Start_IT(TIM_HandleTypeDef*p){assert(p->Instance==TIM6);return start_error;}
#endif
'''
HARNESS=r'''
#include <assert.h>
#include <stdio.h>
#include "stm32n6xx_hal_timebase_tim.c"
int main(void){
 sleep_clock=0xa000;assert(HAL_InitTick(15)==HAL_OK);
 assert(clock_on==1&&sleep_clock==0xa010&&priority==14&&irq_on);
 assert(htim6.Init.Prescaler==399&&htim6.Init.Period==999&&htim6.Init.ClockDivision==0);
 assert(!htim6.Init.CounterMode);
 assert(HAL_InitTick(15)==HAL_OK&&clock_on==2&&sleep_clock==0xa010);
 assert(HAL_InitTick(5)==HAL_OK&&priority==5); /* preserve higher IRQ priority */
 interrupts=1;HAL_SuspendTick();assert(!interrupts&&sleep_clock==0xa010);
 HAL_ResumeTick();assert(interrupts==1&&sleep_clock==0xa010);
 init_error=1;assert(HAL_InitTick(15)==HAL_ERROR);init_error=0;start_error=1;
 assert(HAL_InitTick(15)==1);
 puts("PASS actual HAL timebase: sleep clock/reinit, unrelated bits,399/999, IRQ15clamped14 abovePendSV, higher priority preserved, suspend/resume/errors");
}
'''
if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    run_native(HARNESS,extra_stubs={'stm32n6xx_hal.h':STUB,'stm32n6xx_hal_tim.h':'#include "stm32n6xx_hal.h"\n'},extra_includes=[root/'AppliNonSecure/Core/Src'],retain_artifacts=True)
