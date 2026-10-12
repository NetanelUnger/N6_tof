"""Run the actual scalar SPI fault capture across IRQ/abort/report boundaries."""
import re
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT, run_native

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define SPI_FLAG_OVR 1U
#define SPI_FLAG_MODF 2U
#define SPI_FLAG_FRE 4U
#define SPI_FLAG_UDR 8U
typedef struct {uint32_t CCR,CSR,CBR1,CTR1,CTR2;} DmaRegs;
typedef struct {DmaRegs *Instance;uint32_t State,ErrorCode;} DMA_HandleTypeDef;
typedef struct {uint32_t SR,CR1,CR2,CFG1,CFG2,IER;} SpiRegs;
typedef struct {SpiRegs *Instance;uint32_t State,ErrorCode;DMA_HandleTypeDef *hdmatx,*hdmarx;} SPI_HandleTypeDef;
static DmaRegs txr,rxr;static DMA_HandleTypeDef txd={&txr,1,0},rxd={&rxr,2,0};
static SpiRegs regs;static SPI_HandleTypeDef NCP_SPI_HANDLE={&regs,5,0,&txd,&rxd};
static struct {uint32_t IDR;} pins;
#define SPI_CS_GPIO_Port (&pins)
#define SPI_RDY_GPIO_Port (&pins)
#define CHIP_EN_GPIO_Port (&pins)
#define SPI_CS_Pin 1U
#define SPI_RDY_Pin 2U
#define CHIP_EN_Pin 4U
static uint32_t irq,now=42,logs;
static uint32_t __get_PRIMASK(void){return irq;}
static void __disable_irq(void){irq=1;}
static void __set_PRIMASK(uint32_t n){irq=n;}
static uint32_t HAL_GetTick(void){return now;}
static void Debug_UART_Log(const char*a,const char*b,...){(void)a;(void)b;assert(!irq);logs++;}
static volatile SpiPortFault_t spi_fault;
static volatile uint32_t transfer_id,transfer_phase,transfer_length,transfer_rx_only;
static volatile uint32_t fault_reported;
'''
TESTS = r'''
int main(void){
 SpiPortFault_t f;transfer_id=7;transfer_phase=1;transfer_length=252;pins.IDR=6;
 regs.SR=1;regs.IER=0;spi_port_capture_irq();assert(!spi_fault.count);
 regs.IER=1;txr.CBR1=12;rxr.CBR1=9;rxr.CSR=17;
 irq=1;spi_port_capture_irq();assert(irq==1 && logs==0);
 regs.SR=0;rxr.CSR=0;rxr.CBR1=0;NCP_SPI_HANDLE.ErrorCode=64;
 spi_port_capture_failure(2);assert(spi_fault.count==1 && spi_fault.spi_error==64);
 assert(spi_fault.sr==1 && spi_fault.rx_csr==17 && spi_fault.rx_remaining==9);
 puts("PASS IRQ flags captured before HAL clears them; later callback enriches HAL error without replacing DMA evidence");
 transfer_id++;spi_port_capture_failure(3);assert(spi_fault.transfer==7 && spi_fault.collapsed==1);
 puts("PASS subsequent failure cannot overwrite the unreported first fault");
 irq=0;spi_port_get_fault(&f);assert(!irq && f.phase==1 && f.length==252 && f.pins==6);
 spi_port_report_fault();assert(logs==4);spi_port_report_fault();assert(logs==4);
 NCP_SPI_HANDLE.ErrorCode=0;regs.SR=0;spi_port_get_fault(&f);assert(f.spi_error==64 && f.sr==1);
 puts("PASS retained snapshot survives abort/reinit and formats once from task context");
 transfer_id=9;NCP_SPI_HANDLE.ErrorCode=8;spi_port_capture_failure(2);
 spi_port_report_fault();assert(logs==8 && spi_fault.count==2 && spi_fault.transfer==9);
 puts("PASS subsequent transaction fault is captured after prior report without dynamic allocation");
 return 0;}
'''

def main():
    source = (ROOT/'AppliNonSecure/Core/Src/spi_port.c').read_text()
    header = (ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_port.h').read_text()
    typedef = re.search(r'typedef struct\s*\{.*?\}\s*SpiPortFault_t;', header, re.S)[0]
    names = ('spi_port_set_phase', 'spi_port_capture_failure', 'spi_port_capture_irq', 'spi_port_get_fault', 'spi_port_report_fault')
    run_native('#include <stdint.h>\n'+typedef+PREFIX+'\n'.join(function(source,n) for n in names)+TESTS)
    callback = function(source, 'HAL_SPI_ErrorCallback')
    assert 'spi_port_capture_failure(2U)' in callback and 'LogError' not in callback
    capture = function(source, 'spi_port_capture_failure')
    assert all(s not in capture for s in ('Debug_UART_Log','malloc','vTaskDelay','HAL_SPI_Abort'))
    it = (ROOT/'AppliNonSecure/Core/Src/stm32n6xx_it.c').read_text()
    assert it.index('spi_port_capture_irq();') < it.index('HAL_SPI_IRQHandler(&hspi5);')
    print('PASS ISR capture has no formatting/wait/reset and runs before HAL flag cleanup')

if __name__ == '__main__': main()
