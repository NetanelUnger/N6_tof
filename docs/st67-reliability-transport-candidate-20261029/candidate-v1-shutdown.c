
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
typedef unsigned TickType_t;
#define pdMS_TO_TICKS(ms) (ms)
#define pdTRUE 1
#define SPI_EVT_TXN_PENDING 1U
#define SPI_MSG_CTRL_TRAFFIC_TYPE_MAX 2U
struct spi_buffer {unsigned id;};
struct spi_xfer_engine {void *task;volatile int stop;int initialized;volatile int transport_fault;void *event;void *txq;void *rxq[2];struct spi_buffer *txbuf,*failed_rxbuf;};
static struct spi_xfer_engine xfer_engine;
static unsigned now,ack,abort_ok,freed[10],deletes,powered;
static struct spi_buffer packets[5]={{1},{2},{3},{4},{5}};
static unsigned queued[3];
static unsigned xTaskGetTickCount(void){return now;}
static void vTaskDelay(unsigned ms){now+=ms;if(ack)xfer_engine.stop=2;}
static int xEventGroupSetBits(void *p,unsigned bits){(void)p;(void)bits;return 0;}
static int spi_port_abort(void){return abort_ok?0:-1;}
static int spi_port_set_cs(unsigned active){(void)active;return 0;}
static void vTaskDelete(void *p){assert(xfer_engine.stop==2 && abort_ok);(void)p;deletes++;}
static int xQueueReceive(void *q,struct spi_buffer **p,unsigned wait){(void)wait;unsigned i=(unsigned)(uintptr_t)q-1;if(!queued[i])return 0;*p=&packets[queued[i]-1];queued[i]=0;return 1;}
static void spi_buffer_free(struct spi_buffer *p){assert(abort_ok);assert(++freed[p->id]==1);}
static void vQueueDelete(void*p){(void)p;assert(abort_ok);deletes++;}
static void vEventGroupDelete(void*p){(void)p;deletes++;}
static int spi_port_deinit(void){powered=0;return 0;}
static void reset(void){memset(&xfer_engine,0,sizeof xfer_engine);memset(freed,0,sizeof freed);memset(queued,0,sizeof queued);now=deletes=0;powered=ack=abort_ok=1;xfer_engine.task=(void*)1;xfer_engine.event=(void*)1;xfer_engine.txq=(void*)1;xfer_engine.rxq[0]=(void*)2;xfer_engine.rxq[1]=(void*)3;xfer_engine.txbuf=&packets[3];xfer_engine.failed_rxbuf=&packets[4];queued[0]=1;queued[1]=2;queued[2]=3;}
int32_t spi_transaction_quiesce(uint32_t timeout_ms)
{
  TickType_t started = xTaskGetTickCount();
  if (xfer_engine.task != NULL)
  {
    if (xfer_engine.stop == 0) xfer_engine.stop = 1;
    (void)xEventGroupSetBits(xfer_engine.event, SPI_EVT_TXN_PENDING);
    while (xfer_engine.stop != 2)
    {
      if ((xTaskGetTickCount() - started) >= pdMS_TO_TICKS(timeout_ms)) return -1;
      vTaskDelay(pdMS_TO_TICKS(1U));
    }
  }
  if (spi_port_abort() != 0) return -1;
  (void)spi_port_set_cs(0);
  return 0;
}int32_t spi_transaction_deinit(void)
{
  struct spi_buffer *pending;
  if (spi_transaction_quiesce(2000U) != 0) return -1;
  /* EXTI/DMA callbacks must stop publishing before their event is deleted. */
  xfer_engine.initialized = 0;
  (void)spi_port_deinit();
  if (xfer_engine.task != NULL)
  {
    vTaskDelete(xfer_engine.task);
    xfer_engine.task = NULL;
  }

  /* Clean up resources in case of error */
  if (xfer_engine.txq != NULL)
  {
    while (xQueueReceive(xfer_engine.txq, &pending, 0) == pdTRUE)
      spi_buffer_free(pending);
    vQueueDelete(xfer_engine.txq);
  }

  if (xfer_engine.event != NULL)
  {
    vEventGroupDelete(xfer_engine.event);
  }

  for (int32_t i = 0; i < (int32_t)SPI_MSG_CTRL_TRAFFIC_TYPE_MAX; i++)
  {
    if (xfer_engine.rxq[i] != NULL)
    {
      while (xQueueReceive(xfer_engine.rxq[i], &pending, 0) == pdTRUE)
        spi_buffer_free(pending);
      vQueueDelete(xfer_engine.rxq[i]);
    }
  }

  if (xfer_engine.txbuf != NULL) spi_buffer_free(xfer_engine.txbuf);
  if (xfer_engine.failed_rxbuf != NULL) spi_buffer_free(xfer_engine.failed_rxbuf);
  /* Clear xfer_engine context */
  (void)memset(&xfer_engine, 0, sizeof(struct spi_xfer_engine));

  (void)spi_port_deinit();

  return 0;
}
int main(void){
 reset();xfer_engine.transport_fault=-3;ack=0;assert(spi_transaction_deinit()!=0 && !deletes && powered && xfer_engine.txbuf);
 for(unsigned i=0;i<10;i++)assert(!freed[i]);puts("PASS worker acknowledgment timeout retains all packets and synchronization objects");
 reset();abort_ok=0;assert(spi_transaction_deinit()!=0 && !deletes && powered && xfer_engine.failed_rxbuf);
 puts("PASS failed DMA abort retains destination and refuses lifecycle reset");
 abort_ok=1;assert(spi_transaction_deinit()==0 && !powered && deletes==5);
 for(unsigned i=1;i<=5;i++)assert(freed[i]==1);assert(!xfer_engine.txbuf && !xfer_engine.task && !xfer_engine.transport_fault);
 puts("PASS subsequent proven stop frees queued TX/RX, retained TX and failed DMA destination exactly once");
 assert(spi_transaction_deinit()==0 && deletes==5);puts("PASS repeated deinit is idempotent after complete cleanup");
 return 0;}
