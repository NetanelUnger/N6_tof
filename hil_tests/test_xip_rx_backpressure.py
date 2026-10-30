"""Exercise actual SPI startup policy against unsafe modes; host registers only."""
from pathlib import Path
from test_xip_boot import run_native

PREFIX=r'''
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#define HAL_SPI_STATE_RESET 0
#define HAL_SPI_STATE_READY 1
#define SPI_CR1_SPE 1U
#define SPI_CR1_MASRX 256U
#define SPI_MODE_MASTER 4U
#define SPI_DIRECTION_2LINES 0U
#define SPI_DATASIZE_8BIT 7U
#define SPI_MASTER_RX_AUTOSUSP_ENABLE SPI_CR1_MASRX
#define SET_BIT(r,b) ((r)|=(b))
#define LogError(...) ((void)0)
#define Debug_UART_Log(...) ((void)0)
typedef void (*spi_transaction_complete_t)(void);
static spi_transaction_complete_t transaction_complete_callback;
static struct Registers {uint32_t CR1;} registers;
static struct {uint32_t State;struct {uint32_t Mode,Direction,DataSize,MasterReceiverAutoSusp;} Init;struct Registers *Instance;} handle;
#define NCP_SPI_HANDLE handle
#define CHIP_EN_GPIO_Port 0
#define CHIP_EN_Pin 0
#define GPIO_PIN_SET 1
static int power;
#define HAL_GPIO_WritePin(...) (++power)
'''
TEST=r'''
static void complete(void){}
static void ready(void){handle.State=HAL_SPI_STATE_READY;handle.Instance=&registers;
handle.Init.Mode=SPI_MODE_MASTER;handle.Init.Direction=SPI_DIRECTION_2LINES;
handle.Init.DataSize=SPI_DATASIZE_8BIT;handle.Init.MasterReceiverAutoSusp=0;registers.CR1=0x1000;power=0;transaction_complete_callback=0;}
int main(void){
ready();assert(spi_port_init(complete)==0);assert(power==1&&transaction_complete_callback==complete);
#if N6_SPI_RX_FLOW_CONTROL
assert(registers.CR1==0x1100&&handle.Init.MasterReceiverAutoSusp==256);
for(int n=0;n<5;n++){ready();if(n==0)registers.CR1|=SPI_CR1_SPE;
if(n==1)handle.Init.Mode=0;if(n==2)handle.Init.Direction=1;if(n==3)handle.Init.DataSize=3;if(n==4)handle.State=2;
uint32_t original=registers.CR1;assert(spi_port_init(complete)==-1);
assert(registers.CR1==original&&handle.Init.MasterReceiverAutoSusp==0&&power==0&&transaction_complete_callback==0);}
#else
assert(registers.CR1==0x1000&&handle.Init.MasterReceiverAutoSusp==0);
#endif
ready();handle.State=HAL_SPI_STATE_RESET;assert(spi_port_init(complete)==-1&&power==0);
puts("PASS actual startup: flow-control modes, production default on, unsafe modes fail before chip power");}
'''

def main():
    root=Path(__file__).resolve().parents[1]
    source=(root/'AppliNonSecure/Core/Src/spi_port.c').read_text()
    body=source[source.index('int32_t spi_port_init('):source.index('int32_t spi_port_deinit(')]
    for enabled in [0,1]:
        run_native(PREFIX+f'\n#define N6_SPI_RX_FLOW_CONTROL {enabled}\n'+body+TEST)

if __name__=='__main__':main()
