
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <assert.h>
#define EIO 5
#define EBUSY 16
#define SPI_MSG_CTRL_TRAFFIC_AT_CMD 0U
#define IO_SEND_TIMEOUT 2000U
#define portTICK_PERIOD_MS 1U
#define pdMS_TO_TICKS(n) (n)
#define AT_LOG_HOST_OUT(...) ((void)0)
#define Debug_UART_NcpTrace(...) ((void)0)
#define CONTAINER_OF(p,t,f) ((t*)((char*)(p)-offsetof(t,f)))
struct modem_iface {unsigned marker;};
struct modem_cmd_handler_data {bool tx_desynchronized;};
struct modem {struct modem_iface iface;struct modem_cmd_handler_data handler_data;unsigned notify_phase;void*notify_owner;};
static int fault,result;static unsigned writes,last_budget;
static int spi_transaction_faulted(void){return fault;}
static void *xTaskGetCurrentTaskHandle(void){return (void*)1;}
static unsigned modem_cmd_handler_budget(struct modem_cmd_handler_data*p,unsigned n){assert(n==2000);return 700;}
static int BusIo_SPI_SendData(unsigned type,uint8_t*p,size_t n,unsigned timeout){assert(type==0 && n==4);++writes;last_budget=timeout;return result;}
static int32_t modem_iface_spi_write(struct modem_iface *iface,
                                      const uint8_t *buf, size_t size)
{
  int32_t result;
  if (size == 0U)
  {
    return 0;
  }
  AT_LOG_HOST_OUT((uint8_t *)buf, size);
  struct modem *mdm = CONTAINER_OF(iface, struct modem, iface);
  if (spi_transaction_faulted() != 0)
  {
    mdm->handler_data.tx_desynchronized = true;
    return -EIO;
  }
  bool notification = (mdm->notify_phase != 0U) &&
                      (mdm->notify_owner == xTaskGetCurrentTaskHandle());
  result = BusIo_SPI_SendData(SPI_MSG_CTRL_TRAFFIC_AT_CMD, (uint8_t *)buf, size,
                              notification ? 0U : (uint32_t)(modem_cmd_handler_budget(
                                  &mdm->handler_data, pdMS_TO_TICKS(IO_SEND_TIMEOUT)) * portTICK_PERIOD_MS));
  /* DATA mode copies/enqueues atomically; these errors queue zero bytes. */
  if (notification && ((result == -3) || (result == -5))) result = -EBUSY;
  Debug_UART_NcpTrace("TX queued", buf, size, result);
  return result;
}
int main(void){struct modem m={0};uint8_t data[4]={1,2,3,4};
 fault=-3;assert(modem_iface_spi_write(&m.iface,data,4)==-EIO && !writes && m.handler_data.tx_desynchronized);
 assert(modem_iface_spi_write(&m.iface,data,0)==0 && !writes && m.handler_data.tx_desynchronized);
 puts("PASS sticky bus fault fences AT write without touching SPI queue; zero-length call sends nothing");
 fault=0;m.handler_data.tx_desynchronized=false;m.notify_phase=1;m.notify_owner=(void*)1;
 result=-3;assert(modem_iface_spi_write(&m.iface,data,4)==-EBUSY && !last_budget);
 result=-5;assert(modem_iface_spi_write(&m.iface,data,4)==-EBUSY);
 result=-6;assert(modem_iface_spi_write(&m.iface,data,4)==-6 && !m.handler_data.tx_desynchronized);
 puts("PASS only existing zero-byte allocation/queue failures map to notification BUSY; hard lifecycle fault is not retryable BUSY");
 m.notify_phase=0;result=4;assert(modem_iface_spi_write(&m.iface,data,4)==4 && last_budget==700);
 result=-3;assert(modem_iface_spi_write(&m.iface,data,4)==-3 && last_budget==700);
 puts("PASS ordinary owner retains its existing scoped bus budget and error semantics");return 0;}
