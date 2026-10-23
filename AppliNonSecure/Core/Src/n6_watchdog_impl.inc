/* Included once by app_threadx.c, in the existing confirmation task. */
#if (N6_WATCHDOG_ENABLED == 1U)
#include "stm32n6xx_ll_iwdg.h"
static N6H_Progress n6h_progress[N6H_COUNT];
static uint32_t n6h_started,n6h_required;
static volatile uint32_t n6h_failure,n6h_ready;
static volatile uint32_t n6h_supervisor_fault;
static uint32_t n6h_arm,n6h_armed_at;
static const uint32_t n6h_seconds[N6H_COUNT]={3,4,8,12,6,6,35,45,35};

void N6H_Beat(uint32_t task)
{
  if(task>=N6H_COUNT || __get_IPSR()!=0U)return;
  __atomic_store_n(&n6h_progress[task].last,(uint32_t)tx_time_get(),__ATOMIC_RELAXED);
  uint32_t count=__atomic_load_n(&n6h_progress[task].count,__ATOMIC_RELAXED);
  __atomic_store_n(&n6h_progress[task].count,count<2U?count+1U:2U,__ATOMIC_RELEASE);
}

uint32_t N6H_UartCommand(uint32_t command)
{
  uint32_t now=(uint32_t)tx_time_get();
  uint32_t busy=Firmware_Update_IsBusy();
  uint32_t healthy=__atomic_load_n(&n6h_ready,__ATOMIC_ACQUIRE) && !n6h_failure;
  if(command=='w' || command=='s') {
    n6h_arm=0U;
    if(!healthy || busy) { Debug_UART_Log("WDT","arm rejected: not healthy or updater busy");return 1U; }
    n6h_armed_at=now;n6h_arm=(command=='w')?1U:2U;
    Debug_UART_Log("WDT","ARM target=%s expiry=5s; send W; any other key cancels",
      n6h_arm==1U?"UART-control-task":"supervisor-task");
    return 1U;
  }
  if(command=='W') {
    uint32_t kind=n6h_arm;n6h_arm=0U;
    if(!N6H_ArmValid(kind,now,n6h_armed_at,5U*TX_TIMER_TICKS_PER_SECOND,healthy,busy)) {
      Debug_UART_Log("WDT","W rejected: absent/expired arm, unhealthy, or updater busy");return 1U;
    }
    Debug_UART_Log("WDT","FAULT target=%s intentional while(1); IRQs remain enabled; awaiting IWDG",
      kind==1U?"UART-control-task":"supervisor-task");
    /* Existing bounded flush; no formatting/allocation in the intentional loop. */
    (void)Debug_UART_Flush(1000U);
    if(kind==1U) { for(;;) { __NOP(); } }
    __atomic_store_n(&n6h_supervisor_fault,1U,__ATOMIC_RELEASE);
    return 1U;
  }
  if(command!='\r' && command!='\n')n6h_arm=0U;
  return 0U;
}

void N6H_Run(void)
{
  uint32_t budgets[N6H_COUNT];
  uint32_t reset=RCC->RSR;
  Debug_UART_Log("WDT","reset RSR=%08lX IWDG=%lu; MCU reset does not power-cycle external devices",
    (unsigned long)reset,(unsigned long)((reset&RCC_RSR_IWDGRSTF)!=0U));
  __HAL_RCC_CLEAR_RESET_FLAGS();
  n6h_required=(1UL<<N6H_UART_TX)|(1UL<<N6H_UART_CONTROL)|
               (1UL<<N6H_TOF_ACQUIRE)|(1UL<<N6H_TOF_PROCESS);
#if APP_USB_CLI_ENABLED
  n6h_required|=1UL<<N6H_CLI;
#endif
#if APP_GC9A01_DISPLAY_ENABLED
  n6h_required|=1UL<<N6H_DISPLAY;
#endif
#if APP_ST67W6X_ENABLED
  n6h_required|=1UL<<N6H_RADIO;
#endif
#if APP_ST67W6X_WIFI_SERVICES_ENABLED || APP_ST67W6X_BLE_GATT_ENABLED
  n6h_required|=1UL<<N6H_WIFI_CONTROL;
#endif
#if APP_ST67W6X_CLOUD_RELAY_ENABLED
  n6h_required|=1UL<<N6H_CLOUD;
#endif
  for(uint32_t i=0;i<N6H_COUNT;i++)budgets[i]=n6h_seconds[i]*TX_TIMER_TICKS_PER_SECOND;
  n6h_started=(uint32_t)tx_time_get();
  /* Software start only, no option bytes, debug-freeze or RIF writes. The
   * STM32N6 HAL/LL software-start sequence, nominal16s at32kHz, /256*(1999+1).
   * Never refresh from ISR, UART, owner heartbeat or NOR writer. */
  LL_IWDG_Enable(IWDG);
  LL_IWDG_EnableWriteAccess(IWDG);
  LL_IWDG_SetPrescaler(IWDG,LL_IWDG_PRESCALER_256);
  LL_IWDG_SetReloadCounter(IWDG,1999U);
  IWDG->EWCR=0U;IWDG->ICR=IWDG_ICR_EWIC;
  uint32_t sync=(uint32_t)tx_time_get();
  while(IWDG->SR&(IWDG_SR_PVU|IWDG_SR_RVU|IWDG_SR_WVU|IWDG_SR_EWU)) {
    if((uint32_t)(tx_time_get()-sync)>TX_TIMER_TICKS_PER_SECOND) {
      Debug_UART_Log("WDT","register sync failed; no feed or boot confirmation");
      for(;;)tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND);
    }
    tx_thread_sleep(1U);
  }
  LL_IWDG_SetWindow(IWDG,4095U);
  sync=(uint32_t)tx_time_get();
  while(IWDG->SR&IWDG_SR_WVU) {
    if((uint32_t)(tx_time_get()-sync)>TX_TIMER_TICKS_PER_SECOND)break;
    tx_thread_sleep(1U);
  }
  Debug_UART_Log("WDT","register readback PR=%lu RLR=%lu WINR=%lu SR=%08lX",
    (unsigned long)IWDG->PR,(unsigned long)IWDG->RLR,
    (unsigned long)IWDG->WINR,(unsigned long)IWDG->SR);
  if(IWDG->PR!=LL_IWDG_PRESCALER_256 || IWDG->RLR!=1999U ||
     IWDG->WINR!=4095U || (IWDG->SR&IWDG_SR_ONF)==0U || (IWDG->SR&IWDG_SR_WVU)) {
    Debug_UART_Log("WDT","register readback rejected; no feed or boot confirmation");
    for(;;)tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND);
  }
  Debug_UART_Log("WDT","START nominal16s required=%03lX supervisor priority6; no unconditional feed",
    (unsigned long)n6h_required);
  for(;;) {
    if(__atomic_load_n(&n6h_supervisor_fault,__ATOMIC_ACQUIRE))for(;;)__NOP();
    uint32_t now=(uint32_t)tx_time_get(),missing=0U;
    N6H_Progress observed[N6H_COUNT];
    for(uint32_t i=0;i<N6H_COUNT;i++) {
      observed[i].count=__atomic_load_n(&n6h_progress[i].count,__ATOMIC_ACQUIRE);
      observed[i].last=__atomic_load_n(&n6h_progress[i].last,__ATOMIC_RELAXED);
      if((n6h_required&(1UL<<i)) && observed[i].count<2U)missing|=1UL<<i;
    }
    uint32_t bad=N6H_BadMask(observed,budgets,n6h_required,now);
    /* Startup is a single bounded grace, not a renewable maintenance bypass.
     * Missing tasks must enter a real loop before boot can be confirmed. */
    if(!n6h_ready && (uint32_t)(now-n6h_started)<45U*TX_TIMER_TICKS_PER_SECOND)
      bad&=~missing;
    else bad|=missing;
    if(bad && !n6h_failure) {
      n6h_failure=bad;
      Debug_UART_Log("WDT","TASK STALE mask=%03lX; feeding permanently stopped until reset",
        (unsigned long)bad);
    }
    if(!n6h_failure) {
      if(!missing && !n6h_ready) {
        __atomic_store_n(&n6h_ready,1U,__ATOMIC_RELEASE);
        Firmware_Update_ConfirmBoot();
        Debug_UART_Log("WDT","HEALTHY required=%03lX; w then W=UART task hang, s then W=supervisor hang",
          (unsigned long)n6h_required);
      }
      LL_IWDG_ReloadCounter(IWDG);
    }
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND/10U);
  }
}
#endif
