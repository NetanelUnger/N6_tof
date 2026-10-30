"""Actual one-shot diagnostic code under simulated HAL DMA state transitions."""
from pathlib import Path
from test_xip_boot import run_native

HARNESS=r'''
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#define HAL_OK 0U
#define HAL_SPI_STATE_RESET 0U
#define HAL_SPI_STATE_BUSY_TX_RX 1U
#define HAL_DMA_STATE_BUSY 1U
#define HAL_DMA_STATE_SUSPEND 2U
#define SPI_CR1_MASRX 0x100U
#define SPI_SR_SUSP 0x800U
struct DMARegs{uint32_t CBR1;};struct SPIRegs{uint32_t CR1,SR;};
typedef struct{uint32_t State;struct DMARegs *Instance;} DMA_HandleTypeDef;
typedef struct{uint32_t State;struct SPIRegs *Instance;DMA_HandleTypeDef *hdmarx;} Spi;
static struct DMARegs dma_regs={400};static struct SPIRegs spi_regs={SPI_CR1_MASRX,0};
static DMA_HandleTypeDef dma={HAL_DMA_STATE_BUSY,&dma_regs};
static Spi NCP_SPI_HANDLE={HAL_SPI_STATE_BUSY_TX_RX,&spi_regs,&dma};
static uint32_t transfer_id=7,transaction_failed,rx_flow_resumes,active,mask,suspends,resumes,fail_suspend,fail_resume,produce_susp=1,complete_on_resume;
static uint32_t Firmware_Update_IsActive(void){return active;}
static uint32_t __get_PRIMASK(void){return mask;}
static void __disable_irq(void){mask=1;}
static void __set_PRIMASK(uint32_t p){mask=p;}
static uint32_t HAL_DMAEx_Suspend(DMA_HandleTypeDef*p){++suspends;if(fail_suspend)return 1;p->State=HAL_DMA_STATE_SUSPEND;if(produce_susp)spi_regs.SR=SPI_SR_SUSP;return HAL_OK;}
static void spi_port_flow_test_complete(void);
static uint32_t HAL_DMAEx_Resume(DMA_HandleTypeDef*p){++resumes;if(fail_resume)return 1;p->State=HAL_DMA_STATE_BUSY;if(complete_on_resume)spi_port_flow_test_complete();return HAL_OK;}
static void Debug_UART_Log(const char*a,const char*b,...){assert(!mask);}
#include "spi_flow_probe_impl.inc"
static void reset(void){flow_test=(SpiFlowTest){0};spi_regs.SR=0;dma.State=HAL_DMA_STATE_BUSY;fail_suspend=fail_resume=active=complete_on_resume=0;produce_susp=1;}
int main(void){
assert(spi_port_maybe_test_rx_flow(520)==0&&suspends==0);
assert(spi_port_arm_rx_flow_test()==0&&flow_test.stage==1&&!mask);
assert(spi_port_arm_rx_flow_test()==-2);
assert(spi_port_maybe_test_rx_flow(32)==0&&suspends==0&&flow_test.stage==1&&flow_test.max_seen==32);
assert(spi_port_cancel_rx_flow_test()==0&&flow_test.stage==0);assert(spi_port_cancel_rx_flow_test()==-1);
assert(spi_port_arm_rx_flow_test()==0);
active=1;assert(spi_port_maybe_test_rx_flow(520)==0&&suspends==0);assert(spi_port_arm_rx_flow_test()==-1);active=0;
dma.State=0;assert(spi_port_maybe_test_rx_flow(520)==0&&suspends==0);dma.State=HAL_DMA_STATE_BUSY;
assert(spi_port_maybe_test_rx_flow(520)==0&&suspends==1&&resumes==1);
assert(flow_test.sr==SPI_SR_SUSP&&flow_test.left==400&&flow_test.stage==4&&dma.State==HAL_DMA_STATE_BUSY);
assert(spi_regs.SR==SPI_SR_SUSP); /* Probe does NOT clear SPI suspend. */
spi_port_flow_test_complete();assert(flow_test.stage==5&&flow_test.completed==1);
spi_port_report_flow_test();assert(flow_test_reported==5);
reset();spi_port_arm_rx_flow_test();fail_suspend=1;unsigned n=resumes;
assert(spi_port_maybe_test_rx_flow(520)==-1&&flow_test.stage==9&&resumes==n);
reset();spi_port_arm_rx_flow_test();fail_resume=1;assert(spi_port_maybe_test_rx_flow(520)==-1&&flow_test.stage==9);
reset();spi_port_arm_rx_flow_test();produce_susp=0;assert(spi_port_maybe_test_rx_flow(520)==0&&flow_test.sr==0); /* bounded NOT_EXERCISED */
reset();spi_port_arm_rx_flow_test();complete_on_resume=1;assert(spi_port_maybe_test_rx_flow(520)==0&&flow_test.stage==5&&flow_test.completed==1);
reset();spi_port_arm_rx_flow_test();spi_port_maybe_test_rx_flow(520);transaction_failed=1;spi_port_flow_test_complete();assert(flow_test.completed==2);
puts("PASS one-shot DMA pause/resume: update/size/state gates, real-SUSP evidence, no SPI flag clear, HAL failures, bounded no-SUSP and completion race");
}
'''

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    body=(root/'AppliNonSecure/Core/Src/spi_flow_probe_impl.inc').read_text()
    worker=body[body.index('static int32_t spi_port_maybe_test_rx_flow'):body.index('static void spi_port_flow_test_complete')]
    assert 'Debug_UART' not in worker and 'RXDR' not in worker.replace('read RXDR','') and 'malloc(' not in worker
    run_native(HARNESS,extra_includes=[root/'AppliNonSecure/Core/Src'],retain_artifacts=True)
