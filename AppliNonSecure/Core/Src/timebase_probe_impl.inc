/* UART task only. Fixed hex encoding, no formatter/heap/ISR output.
 * Ordinary .bss, explicit finite30 samples, paced by RTOS rather than HAL.
 * Values are successive scalar reads, not an atomic hardware snapshot. */
#if (N6_RESOURCE_DIAGNOSTICS == 1U)
static volatile uint32_t time_probe_remaining;
static uint32_t time_probe_tick;
#ifndef N6_TIME_CAPTURE
#define N6_TIME_CAPTURE(times,timer) do { \
  Debug_CLI_Status_t cli;uint32_t update[5]; \
  Debug_CLI_GetStatus(&cli);Firmware_Update_GetTimeProbe(update); \
  (times)[0]=HAL_GetTick();(times)[1]=tx_time_get();(times)[2]=cli.cycles; \
  for(uint32_t i=0;i<5U;++i)(times)[3U+i]=update[i]; \
  (timer)[0]=TIM6->CR1;(timer)[1]=TIM6->PSC;(timer)[2]=TIM6->ARR; \
  (timer)[3]=TIM6->CNT;(timer)[4]=TIM6->DIER;(timer)[5]=TIM6->SR; \
  (timer)[6]=__HAL_RCC_TIM6_IS_CLK_SLEEP_ENABLED() \
    |(NVIC_GetEnableIRQ(TIM6_IRQn)<<8)|(NVIC_GetPendingIRQ(TIM6_IRQn)<<9) \
    |(NVIC_GetPriority(TIM6_IRQn)<<16)|(NVIC_GetPriority(PendSV_IRQn)<<24); \
  (timer)[7]=__get_PRIMASK()|(__get_BASEPRI()<<8)|(NVIC_GetPriority(SysTick_IRQn)<<24); \
}while(0)
#endif
_Static_assert(8U*9U+8U+2U<=96U,"time diagnostic line bound");
void Debug_UART_StartTimeProbe(void)
{
  uint32_t p=__get_PRIMASK();__disable_irq();
  time_probe_tick=tx_time_get();time_probe_remaining=30U;
  __set_PRIMASK(p);
}
static void time_probe_line(const char *prefix,uint32_t size,const uint32_t values[8])
{
  char line[96];uint32_t n=0U;
  for(uint32_t i=0;i<size;++i)line[n++]=prefix[i];
  static const char hex[]="0123456789ABCDEF";
  for(uint32_t i=0;i<8U;++i){
    for(int shift=28;shift>=0;shift-=4)line[n++]=hex[(values[i]>>shift)&15U];
    line[n++]=' ';
  }
  line[n++]='\r';line[n++]='\n';(void)Debug_UART_Write(line,n);
}
static void Debug_UART_TimeProbePoll(void)
{
  if(!time_probe_remaining||__get_IPSR())return;
  uint32_t now=tx_time_get();
  if((uint32_t)(now-time_probe_tick)<TX_TIMER_TICKS_PER_SECOND)return;
  time_probe_tick=now;--time_probe_remaining;
  uint32_t times[8],timer[8];N6_TIME_CAPTURE(times,timer);
  time_probe_line("[TIME] ",7U,times);time_probe_line("[TIMER] ",8U,timer);
}
#else
void Debug_UART_StartTimeProbe(void){}
static void Debug_UART_TimeProbePoll(void){}
#endif
