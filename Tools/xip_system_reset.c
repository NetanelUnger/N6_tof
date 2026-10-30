/* XIP-only override, separately linked by Build-Xip.ps1.
 * ES0620 Rev5 2.2.22/2.2.23: restore the ROM clock switches before SYSRESETREQ.
 * This is not the separate NRST2.2.18 workaround, and changes no security/OTP.
 * https://www.st.com/resource/en/errata_sheet/es0620-stm32n6xxxx-device-errata-stmicroelectronics.pdf
 */
#ifndef N6_RESET_HOST_TEST
#include "stm32n657xx.h"
#include "debug_uart.h"
#endif

#ifndef N6_RESET_WRITE
#define N6_RESET_WRITE(reg, value) ((reg) = (value))
#endif

#if defined(__GNUC__)
__attribute__((noinline))
#endif
void N6_ResetReport(void)
{
#ifndef N6_RESET_HOST_TEST
  uint32_t current_pc;
  __asm volatile ("mov %0, pc" : "=r" (current_pc));
  Debug_UART_Log("RESET", "CPU PC=%08lX VTOR=%08lX",
                 (unsigned long)current_pc, (unsigned long)SCB->VTOR);
#endif
  Debug_UART_Log("RESET", "mux6/7/8/13=%08lX/%08lX/%08lX/%08lX SR=%08lX",
                 (unsigned long)RCC->CCIPR6, (unsigned long)RCC->CCIPR7,
                 (unsigned long)RCC->CCIPR8, (unsigned long)RCC->CCIPR13,
                 (unsigned long)RCC->SR);
}

#if defined(__GNUC__)
__attribute__((section(".RamFunc"), noinline))
#endif
int N6_SystemReset(void)
{
  const uint32_t uart_mask = RCC_CCIPR13_USART1SEL;
  const uint32_t phy_mask = RCC_CCIPR6_OTGPHY1CKREFSEL | RCC_CCIPR6_XSPI1SEL;
  const uint32_t other_uarts = RCC_CCIPR13_USART2SEL |
                              RCC_CCIPR13_UART4SEL | RCC_CCIPR13_UART5SEL;
  uint32_t before_uart = RCC->CCIPR13;
  uint32_t before_phy = RCC->CCIPR6;
  uint32_t saved_primask;

  /* Diagnostics happen before masking or switching. No flash-resident call is
   * permitted after the first clock write. Record exact preconditions rather
   * than silently treating an unknown clock configuration as safe. */
  N6_ResetReport();
  if ((RCC->SR & (RCC_SR_HSIRDY | RCC_SR_HSERDY | RCC_SR_LSIRDY)) !=
      (RCC_SR_HSIRDY | RCC_SR_HSERDY | RCC_SR_LSIRDY))
    return -1;
  /* BootROM leaves XSPI1 on CLKP (1), measured on confirmed B13. PERSEL0
   * makes CLKP derive from the verified-running HSI; HCLK runs the CPU. Thus
   * XSPI1's CLKP->HCLK switch has both sources; do not alter IC3 or XSPI2.
   * Refuse unfamiliar XSPI1/PER/RTC/SDMMC/UART2/4/5 state instead of changing
   * secure-owned or inactive clock trees without evidence. ES requires RTC2;
   * PER0/RTC2 means0x200 in CCIPR7, not PER2. */
  if (((before_phy & RCC_CCIPR6_XSPI1SEL) > 1U) ||
      ((RCC->CCIPR7 & (RCC_CCIPR7_PERSEL | RCC_CCIPR7_RTCSEL)) !=
       (2UL << RCC_CCIPR7_RTCSEL_Pos)) ||
      ((RCC->CCIPR8 & (RCC_CCIPR8_SDMMC1SEL | RCC_CCIPR8_SDMMC2SEL)) != 0U) ||
      ((before_uart & other_uarts) != 0U))
    return -2;

  saved_primask = __get_PRIMASK();
  __disable_irq();
  /* HSI (current USART1) and PCLK2 (target) are already running. Both USBPHY
   * choices derive from the already stable, running HSE system clock. XSPI2,
   * its IC3 clock and memory mapping remain untouched. */
  N6_RESET_WRITE(RCC->CCIPR13, before_uart & ~uart_mask);
  N6_RESET_WRITE(RCC->CCIPR6, before_phy & ~phy_mask);
  __DSB(); __ISB();
  if (((RCC->CCIPR13 & uart_mask) != 0U) ||
      ((RCC->CCIPR6 & phy_mask) != 0U))
  {
    /* No reset with a failed switch. Restore the application's original muxes
     * while both sources are still available, then return a visible error. */
    N6_RESET_WRITE(RCC->CCIPR6, before_phy);
    N6_RESET_WRITE(RCC->CCIPR13, before_uart);
    __DSB(); __ISB(); __set_PRIMASK(saved_primask);
    return -3;
  }
  NVIC_SystemReset();
  return 0; /* Host fixtures return; the real CMSIS implementation never does. */
}
