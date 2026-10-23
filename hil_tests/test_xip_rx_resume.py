"""Actual RX-flow service and RTOS wait: preserve DMA ownership and deadline."""
from pathlib import Path
from test_xip_boot import run_native

PREFIX=r'''
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define HAL_SPI_STATE_BUSY_TX_RX 5
#define HAL_SPI_ERROR_NONE 0
#define HAL_DMA_STATE_BUSY 2
#define HAL_DMA_ERROR_NONE 0
#define SPI_CR1_MASRX 0x100U
#define SPI_CR1_CSTART 0x200U
#define SPI_CR1_SPE 1U
#define SPI_CFG1_RXDMAEN 0x4000U
#define SPI_SR_CTSIZE 0xFFFF0000U
#define SPI_SR_SUSP 0x800U
#define SPI_SR_RXP 1U
#define SPI_SR_RXWNE 0x8000U
#define SPI_SR_RXPLVL 0x6000U
#define SPI_SR_OVR 0x40U
#define SPI_SR_UDR 0x20U
#define SPI_SR_MODF 0x200U
#define SPI_SR_TIFRE 0x100U
#define DMA_CCR_EN 1U
#define DMA_CSR_DTEF 0x400U
#define DMA_CSR_ULEF 0x800U
#define DMA_CSR_USEF 0x1000U
#define DMA_CSR_TOF 0x4000U
#define DMA_CSR_SUSPF 0x2000U
#define SPI_IFCR_SUSPC 0x800U
#define WRITE_REG(r,v) ((r)=(v))
static unsigned mask,logs,transfer_phase=2,transfer_length=1476;
#define __get_PRIMASK() mask
#define __disable_irq() (mask=1)
#define __set_PRIMASK(v) (mask=(v))
#define __DMB() ((void)0)
#define Debug_UART_Log(...) (++logs)
static struct SPIRegs {uint32_t SR,CR1,CFG1,IFCR;} spi;
static struct DMARegs {uint32_t CCR,CSR;} dma;
typedef struct {uint32_t State,ErrorCode;struct DMARegs *Instance;} DMAHandle;
static DMAHandle rx;
static struct {uint32_t State,ErrorCode;struct SPIRegs *Instance;DMAHandle *hdmarx;} h;
'''

def main():
    root=Path(__file__).resolve().parents[1]
    source=(root/'AppliNonSecure/Core/Src/spi_port.c').read_text()
    body=source[source.index('void spi_port_service_rx_flow('):source.index('static HAL_StatusTypeDef spi_port_restore_dma(')]
    prefix=PREFIX+'\n#define NCP_SPI_HANDLE h\n#define N6_XIP_RX_BACKPRESSURE 1\n'
    test=r'''
static void ready(void){memset(&h,0,sizeof h);memset(&rx,0,sizeof rx);memset(&spi,0,sizeof spi);memset(&dma,0,sizeof dma);
h.State=5;h.Instance=&spi;h.hdmarx=&rx;rx.State=2;rx.Instance=&dma;dma.CCR=1;
spi.CR1=0x1301;spi.CFG1=SPI_CFG1_RXDMAEN;spi.SR=(1393U<<16)|SPI_SR_SUSP;}
int main(void){
for(unsigned posture=0;posture<2;posture++){ready();mask=posture;spi_port_service_rx_flow();
assert(spi.IFCR==SPI_IFCR_SUSPC&&mask==posture&&dma.CCR==1&&spi.CR1==0x1301&&rx.State==2);}
for(int n=0;n<20;n++){ready();mask=0;
switch(n){case 0:spi.SR|=SPI_SR_RXP;break;case 1:spi.SR|=SPI_SR_RXWNE;break;case 2:spi.SR|=SPI_SR_RXPLVL;break;
case 3:spi.SR|=SPI_SR_OVR;break;case 4:spi.SR|=SPI_SR_UDR;break;case 5:spi.SR|=SPI_SR_MODF;break;case 6:spi.SR|=SPI_SR_TIFRE;break;
case 7:spi.CR1&=~SPI_CR1_MASRX;break;case 8:spi.CR1&=~SPI_CR1_SPE;break;case 9:spi.CR1&=~SPI_CR1_CSTART;break;
case 10:dma.CCR=0;break;case 11:dma.CSR=DMA_CSR_DTEF;break;case 12:dma.CSR=DMA_CSR_SUSPF;break;
case 13:h.hdmarx=0;break;case 14:rx.Instance=0;break;case 15:rx.State=0;break;case 16:rx.ErrorCode=1;break;
case 17:h.State=0;break;case 18:spi.SR&=~SPI_SR_CTSIZE;break;case 19:spi.SR&=~SPI_SR_SUSP;break;}
spi_port_service_rx_flow();assert(spi.IFCR==0&&mask==0);}
puts("PASS drained-FIFO resume only;20 unsafe states refuse; IRQ posture and DMA ownership preserved");}
'''
    run_native(prefix+body+test)
    source=(root/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.c').read_text()
    start=source.index('static int32_t spi_wait_event(void *evnt_ctx, uint32_t event, int32_t timeout_ms)\n{')
    body=source[start:source.index('static int32_t inline spi_clear_event',start)]
    prefix=r'''
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#define N6_XIP_RX_BACKPRESSURE 1
typedef uint32_t TickType_t;
typedef uint32_t EventBits_t;
struct spi_xfer_engine {void *event;};
#define pdTRUE 1
#define pdFALSE 0
#define pdMS_TO_TICKS(n) ((TickType_t)(n))
#define portMAX_DELAY 0xFFFFFFFFU
#define SPI_EVT_HW_XFER_DONE 8U
static TickType_t tick,arrive;
static unsigned services,waits;
static TickType_t xTaskGetTickCount(void){return tick;}
static unsigned xEventGroupWaitBits(void *e,unsigned b,int c,int a,TickType_t n){tick+=n;waits++;return waits==arrive?b:0;}
static void spi_port_service_rx_flow(void){services++;}
'''
    test=r'''
int main(void){struct spi_xfer_engine e={0};
tick=100;arrive=100;assert(spi_wait_event(&e,8,5)==0);assert(tick==105&&services==4&&waits==5);
tick=0xFFFFFFFD;waits=services=0;arrive=3;assert(spi_wait_event(&e,8,5)==1);assert(tick==0&&services==2&&waits==3);
tick=4;waits=services=0;arrive=99;assert(spi_wait_event(&e,8,0)==0);assert(tick==4&&services==0&&waits==1);
puts("PASS whole-transfer deadline unchanged, tick wrap safe, event and zero-timeout semantics retained");}
'''
    run_native(prefix+body+test)

if __name__=='__main__':main()
