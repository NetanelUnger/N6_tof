/* XIP diagnostic object only, linked explicitly by Build-Xip -FaultProbe.
 * Reads CPU/SPI/DMA status; does not change cache, IRQ priority or bus clocks.
 * active=1 means inside the NS call interval, not proof of exact hardware OVR
 * onset. Pending IRQ can run in LeaveFlash before the veneer returns. pre_sr
 * distinguishes an OVR already present before the Secure operation.
 */
#include "xip_fault_probe.h"
#ifndef N6_FAULT_PROBE_HOST
#include "main.h"
#include "debug_uart.h"
#endif

typedef struct {
  uint32_t calls, overlaps, pre_ovr, active, phase, offset, length, started;
  uint32_t pre_sr, pre_rx_ccr, pre_rx_remaining, pre_tx_remaining;
  uint32_t faults, source, fault_active, fault_phase, fault_offset, fault_length;
  uint32_t fault_pre_sr, fault_pre_rx_ccr, fault_pre_rx_remaining, fault_pre_tx_remaining;
  uint32_t fault_ccr, fault_ipsr, fault_primask, fault_basepri;
  uint32_t fault_tx_src, fault_tx_dest, fault_rx_src, fault_rx_dest;
} XipProbeState;
static volatile XipProbeState probe_state;
static uint32_t probe_reported;

void XipProbe_Begin(uint32_t phase, uint32_t offset, uint32_t length)
{
  uint32_t saved=__get_PRIMASK();__disable_irq();
  probe_state.active=0U;
  probe_state.phase=phase;probe_state.offset=offset;probe_state.length=length;
  probe_state.started=HAL_GetTick();
  probe_state.pre_sr=SPI5->SR;
  probe_state.pre_rx_ccr=GPDMA1_Channel11->CCR;
  probe_state.pre_rx_remaining=GPDMA1_Channel11->CBR1;
  probe_state.pre_tx_remaining=GPDMA1_Channel10->CBR1;
  ++probe_state.calls;
  if ((probe_state.pre_rx_ccr & DMA_CCR_EN)!=0U)++probe_state.overlaps;
  if ((probe_state.pre_sr & SPI_SR_OVR)!=0U)++probe_state.pre_ovr;
  probe_state.active=1U;__DMB();__set_PRIMASK(saved);
}

void XipProbe_End(void)
{
  uint32_t phase=probe_state.phase;
  probe_state.active=0U;__DMB();
  if (phase==3U || phase==5U)
    Debug_UART_Log("XIP-PROBE","phase=%lu calls=%lu RX-overlap=%lu pre-OVR=%lu faults=%lu NS-tick-delta=%lu",
      (unsigned long)phase,(unsigned long)probe_state.calls,(unsigned long)probe_state.overlaps,
      (unsigned long)probe_state.pre_ovr,(unsigned long)probe_state.faults,
      (unsigned long)(HAL_GetTick()-probe_state.started));
}

void XipProbe_CaptureFault(uint32_t source,uint32_t prior_primask)
{
  /* Caller already owns the short IRQ-masked first-fault snapshot. */
  ++probe_state.faults;probe_state.source=source;
  probe_state.fault_active=probe_state.active;probe_state.fault_phase=probe_state.phase;
  probe_state.fault_offset=probe_state.offset;probe_state.fault_length=probe_state.length;
  probe_state.fault_pre_sr=probe_state.pre_sr;probe_state.fault_pre_rx_ccr=probe_state.pre_rx_ccr;
  probe_state.fault_pre_rx_remaining=probe_state.pre_rx_remaining;probe_state.fault_pre_tx_remaining=probe_state.pre_tx_remaining;
  probe_state.fault_ccr=SCB->CCR;probe_state.fault_ipsr=__get_IPSR();
  probe_state.fault_primask=prior_primask;probe_state.fault_basepri=__get_BASEPRI();
  probe_state.fault_tx_src=GPDMA1_Channel10->CSAR;probe_state.fault_tx_dest=GPDMA1_Channel10->CDAR;
  probe_state.fault_rx_src=GPDMA1_Channel11->CSAR;probe_state.fault_rx_dest=GPDMA1_Channel11->CDAR;
}

void XipProbe_ReportFault(void)
{
  XipProbeState p;
  uint32_t saved=__get_PRIMASK();__disable_irq();p=probe_state;__set_PRIMASK(saved);
  if (p.faults==probe_reported)return;
  probe_reported=p.faults;
  Debug_UART_Log("XIP-PROBE","fault=%lu source=%lu call-active=%lu phase=%lu offset=%lu length=%lu CCR=%08lX IPSR=%lu BASEPRI=%08lX entry-mask=%lu",
    (unsigned long)p.faults,(unsigned long)p.source,(unsigned long)p.fault_active,(unsigned long)p.fault_phase,
    (unsigned long)p.fault_offset,(unsigned long)p.fault_length,(unsigned long)p.fault_ccr,
    (unsigned long)p.fault_ipsr,(unsigned long)p.fault_basepri,(unsigned long)p.fault_primask);
  Debug_UART_Log("XIP-PROBE","pre SR=%08lX RX-CCR=%08lX RX-left=%lu TX-left=%lu",
    (unsigned long)p.fault_pre_sr,(unsigned long)p.fault_pre_rx_ccr,
    (unsigned long)p.fault_pre_rx_remaining,(unsigned long)p.fault_pre_tx_remaining);
  Debug_UART_Log("XIP-PROBE","TX src/dst=%08lX/%08lX RX src/dst=%08lX/%08lX",
    (unsigned long)p.fault_tx_src,(unsigned long)p.fault_tx_dest,
    (unsigned long)p.fault_rx_src,(unsigned long)p.fault_rx_dest);
}
