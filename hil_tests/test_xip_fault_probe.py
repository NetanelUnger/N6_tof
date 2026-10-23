"""Actual diagnostic C with synthetic read-only registers, never hardware."""
from pathlib import Path
from test_xip_boot import run_native
HARNESS=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define N6_FAULT_PROBE_HOST 1
static struct {uint32_t SR;} spi;
static struct {uint32_t CCR,CBR1,CSAR,CDAR;} tx,rx;
static struct {uint32_t CCR;} scb;
#define SPI5 (&spi)
#define GPDMA1_Channel10 (&tx)
#define GPDMA1_Channel11 (&rx)
#define SCB (&scb)
#define SPI_SR_OVR 0x40U
#define DMA_CCR_EN 1U
static unsigned mask,tick,logs;
#define __get_PRIMASK() mask
#define __disable_irq() (mask=1)
#define __set_PRIMASK(n) (mask=(n))
#define __get_IPSR() 85U
#define __get_BASEPRI() 0U
#define __DMB() ((void)0)
#define HAL_GetTick() tick
#define Debug_UART_Log(...) (++logs)
#include "xip_fault_probe.c"
int main(void){
  tx.CBR1=1320;rx.CBR1=1385;rx.CCR=1;scb.CCR=0x20201;
  tx.CSAR=0x24101000;tx.CDAR=0x40000000;rx.CSAR=0x40000004;rx.CDAR=0x24102000;
  for(unsigned prior=0;prior<=1;prior++){
    mask=prior;XipProbe_Begin(2,78848,1024);assert(mask==prior);
    assert(probe_state.active&&probe_state.phase==2&&probe_state.pre_rx_remaining==1385);
    XipProbe_CaptureFault(1,prior);assert(probe_state.fault_active==1&&probe_state.fault_primask==prior);
    assert(probe_state.fault_rx_dest==0x24102000&&probe_state.fault_ccr==0x20201);
    XipProbe_End();assert(!probe_state.active);
  }
  assert(probe_state.calls==2&&probe_state.overlaps==2&&!probe_state.pre_ovr);
  XipProbe_CaptureFault(6,0);assert(!probe_state.fault_active);
  spi.SR=SPI_SR_OVR;rx.CCR=0;XipProbe_Begin(3,498464,0);XipProbe_End();
  assert(probe_state.pre_ovr==1&&probe_state.overlaps==2&&logs==1);
  unsigned before=logs;XipProbe_ReportFault();assert(logs==before+3);
  XipProbe_ReportFault();assert(logs==before+3);
  assert(tx.CBR1==1320&&rx.CBR1==1385&&rx.CDAR==0x24102000&&spi.SR==SPI_SR_OVR);
  puts("PASS6 actual-C probe groups: IRQ preservation/inside-outside-call/preexistingOVR/addresses/read-only-registers/deduplicated-report");
}
'''
if __name__=='__main__':run_native(HARNESS,extra_includes=[Path(__file__).resolve().parents[1]/'Tools'])
