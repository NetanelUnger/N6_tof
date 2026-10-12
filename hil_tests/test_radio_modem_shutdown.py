"""Run actual modem teardown: stop proof before deleting task/packet/mutexes."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT,run_native

PREFIX=r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
struct modem {void *modem_task_handle,*spi_rx_pending,*spi_rx_pending_data;unsigned spi_rx_pending_len,spi_rx_pending_offset;struct{void*rx_buf,*sem_tx_lock,*sem_parse_lock;}handler_data;unsigned char rx_assembly[20];void *sem_response,*sem_if_ready,*sem_tx_ready;unsigned iface;};
typedef struct {struct modem Modem;}W61_Object_t;
static unsigned stop_ok,stop_calls,io_calls,task_deleted,packet_freed,semaphores_deleted;
static int spi_transaction_quiesce(unsigned timeout){assert(timeout==2000);stop_calls++;return stop_ok?0:-1;}
static void vTaskDelete(void*task){(void)task;assert(stop_ok && !io_calls);task_deleted++;}
static int io_deinit(unsigned *iface){(void)iface;assert(task_deleted && stop_ok);io_calls++;return 0;}
static int BusIo_SPI_Free(void*packet){(void)packet;assert(io_calls);packet_freed++;return 0;}
static void vSemaphoreDelete(void *sem){assert(sem && io_calls);semaphores_deleted++;}
'''
TESTS=r'''
int main(void){W61_Object_t driver={0};struct modem*m=&driver.Modem;
 m->modem_task_handle=m->spi_rx_pending=m->spi_rx_pending_data=(void*)1;m->handler_data.rx_buf=m->rx_assembly;m->sem_response=(void*)2;m->sem_if_ready=(void*)3;m->sem_tx_ready=(void*)4;m->handler_data.sem_tx_lock=(void*)5;m->handler_data.sem_parse_lock=(void*)6;
 W61_AT_ModemDeInit(&driver);assert(!task_deleted && !packet_freed && !semaphores_deleted && m->handler_data.sem_tx_lock);
 puts("PASS failed SPI stop leaves parser, queued-packet reference and all mutex/semaphores alive");
 stop_ok=1;W61_AT_ModemDeInit(&driver);assert(task_deleted==1 && packet_freed==1 && semaphores_deleted==5);
 assert(!m->handler_data.sem_tx_lock && !m->handler_data.sem_parse_lock && !m->handler_data.rx_buf && !m->modem_task_handle && !m->spi_rx_pending);
 puts("PASS proven stop precedes parser deletion, bus teardown, packet free and complete five-semaphore cleanup");
 return 0;}
'''

def main():
    source=(ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c').read_text()
    run_native(PREFIX+function(source,'W61_AT_ModemDeInit')+TESTS)

if __name__=='__main__':main()
