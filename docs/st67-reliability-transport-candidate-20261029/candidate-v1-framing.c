#include <stdint.h>
#define SPI_HEADER_MAGIC_CODE 0x55AAU
#define SPI_XFER_MTU_BYTES 1520U

#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <inttypes.h>
typedef void *TaskHandle_t;
typedef void *EventGroupHandle_t;
typedef void *QueueHandle_t;
#define SPI_BUF_ALIGN_MASK 3U
#define SPI_XFER_TXN_RDY_TIMEOUT (-2)
#define SPI_XFER_TRANSPORT_ERROR (-3)
#define SPI_XFER_PROTOCOL_ERROR (-4)
#define SPI_EVT_TXN_RDY 2U
#define SPI_EVT_HDR_ACKED 4U
#define SPI_EVT_HW_XFER_DONE 8U
#define SPI_WAIT_TXN_TIMEOUT_MS 2000
#define SPI_WAIT_HDR_ACK_TIMEOUT_MS 100
#define SPI_STAT_INC(s,m,v) ((s)->m += (v))
#define pdMS_TO_TICKS(n) (n)
#define pdTRUE 1
#define spi_err(...) ((void)0)
#define spi_trace(...) ((void)0)
static unsigned live,allocations,fail_small,reads,wire_offset,queue_calls;
static unsigned first_size,second_size,fail_read;
static uint8_t wire[4096];
static struct spi_buffer *received;
static void *pvPortMalloc(size_t n) {
 ++allocations;
 if (fail_small && allocations==2) return NULL;
 void *p=malloc(n);assert(p);++live;return p;
}
static void vPortFree(void *p) {assert(p && live);--live;free(p);}
static unsigned Debug_UART_NcpTraceEnabled(void){return 0;}
static void Debug_UART_NcpTerminalObservedAtSpi(void){assert(0);}
static void *spi_port_memcpy(void *d,const void *s,size_t n){return memcpy(d,s,n);}
static void spi_port_set_phase(unsigned n){(void)n;}
static int spi_port_is_ready(void){return 1;}
static int spi_port_abort(void){return 0;}
static void vTaskDelay(unsigned n){(void)n;}
struct spi_stat
{
  uint64_t tx_pkts;                 /*!< Number of transmitted packets */
  uint64_t tx_bytes;                /*!< Number of transmitted bytes */
  uint64_t rx_pkts;                 /*!< Number of received packets */
  uint64_t rx_bytes;                /*!< Number of received bytes */
  uint64_t rx_drop;                 /*!< Number of dropped received packets */
  uint64_t io_err;                  /*!< Number of I/O errors */
  uint64_t hdr_err;                 /*!< Number of header errors */
  uint64_t wait_txn_timeouts;       /*!< Number of wait transaction timeouts */
  uint64_t recovered_lost_ready;    /*!< Ready pin recovered a missing/coalesced event */
  uint64_t transport_recoveries;    /*!< Local SPI aborts completed before retry */
  uint64_t retry_exhaustions;       /*!< Bounded transaction retry windows exhausted */
  uint64_t wait_msg_xfer_timeouts;  /*!< Number of wait message transfer timeouts */
  uint64_t wait_hdr_ack_timeouts;   /*!< Number of wait header ack timeouts */
  uint64_t mem_err;                 /*!< Number of memory errors */
  uint64_t rx_stall;                /*!< Number of RX stalls */
};
struct spi_buffer
{
  /** Pointer to the data */
  void *data;
  /** Length of the data */
  uint16_t len;
  /** Capacity of the buffer, >= len */
  uint32_t cap;
  /** Buffer flags */
  uint32_t flags;
  /** Control block for private data */
  unsigned char cb[16];
};typedef enum
{
  SPI_MSG_CTRL_TRAFFIC_AT_CMD = 0,
  SPI_MSG_CTRL_TRAFFIC_NETWORK_STA,
  SPI_MSG_CTRL_TRAFFIC_NETWORK_AP,
  SPI_MSG_CTRL_TRAFFIC_HCI,
  SPI_MSG_CTRL_TRAFFIC_OT,
  SPI_MSG_CTRL_TRAFFIC_TYPE_MAX,
} spi_msg_ctrl_t;typedef void (*spi_rxd_notify_func_t)(void *arg);
#pragma pack(push,1)
struct spi_header
{
  /** Magic number for header validation */
  uint16_t magic;
  /** Length of the payload */
  uint16_t len;
  /** Header version */
  uint8_t version : 2;
  /** Peer RX is stalled */
  uint8_t rx_stall : 1;
  /** Header flags */
  uint8_t flags : 5;
  /** Message type */
  uint8_t type;
  /** Reserved for future use */
  uint16_t rsvd;
};
#pragma pack(pop)
struct spi_xfer_engine
{
  /** Transfer task handle */
  TaskHandle_t task;
  /** Stop flag for clean shutdown */
  volatile int32_t stop; /* 0 running, 1 requested, 2 worker acknowledged */
  /** Initialization flag */
  int32_t initialized;
  /** Sticky ambiguity; cleared only by proven transport teardown. */
  volatile int32_t transport_fault;
  /** Event flags for synchronization */
  EventGroupHandle_t event;
  /** Current transfer state */
  int32_t state;
  /** Slave RX is stalled */
  int32_t rx_stall;
  /** Single transmit queue */
  QueueHandle_t txq;
  /** Array of receive queues by type */
  QueueHandle_t rxq[SPI_MSG_CTRL_TRAFFIC_TYPE_MAX];
  /** Bitmap of bound traffic types */
  uint8_t rxq_bound;
  /** Current transmit buffer */
  struct spi_buffer *txbuf;
  struct spi_buffer *failed_rxbuf; /* retained until DMA abort is proven */
  /** Transfer statistics */
  struct spi_stat stat;
  /** Received data callbacks for each traffic type */
  spi_rxd_notify_func_t cb[SPI_MSG_CTRL_TRAFFIC_TYPE_MAX];
  /** Callback arguments for each traffic type */
  void *cb_arg[SPI_MSG_CTRL_TRAFFIC_TYPE_MAX];
};
enum
{
  SPI_XFER_STATE_IDLE,
  SPI_XFER_STATE_FIRST_PART,
  SPI_XFER_STATE_SECOND_PART,
  SPI_XFER_STATE_TXN_DONE,
};
#define SPI_HEADER_INIT(h, _type, _len) do {                                     \
                                             (h)->magic = SPI_HEADER_MAGIC_CODE; \
                                             (h)->type = _type;                  \
                                             (h)->version = 0;                   \
                                             (h)->rx_stall = 0;                  \
                                             (h)->flags = 0;                     \
                                             (h)->len = _len;                    \
                                             (h)->rsvd = 0;                      \
                                           } while (false)

static int32_t spi_wait_event(void *e,uint32_t event,int32_t ms){(void)e;(void)event;(void)ms;return 1;}
static int32_t spi_clear_event(struct spi_xfer_engine *e,uint32_t event){(void)e;(void)event;return 0;}
static int read_bytes(void *dest,unsigned n) {
 assert(n%4==0 && wire_offset+n<=sizeof wire);
 ++reads;if(reads==fail_read)return -1;
 memcpy(dest,wire+wire_offset,n);wire_offset+=n;return 0;
}
static int32_t spi_txrx(struct spi_xfer_engine *e,void *tx,void *rx,uint16_t n) {
 (void)e;assert(tx && !reads);first_size=n;return read_bytes(rx,n);
}
static int32_t spi_rx(struct spi_xfer_engine *e,void *rx,uint16_t n) {
 (void)e;assert(reads==1);second_size=n;return read_bytes(rx,n);
}
static int xQueueSend(QueueHandle_t q,void *p,unsigned wait) {
 assert(q==(void*)1 && wait==10 && !received);
 received=*(struct spi_buffer**)p;++queue_calls;return pdTRUE;
}
static inline void spi_buffer_set_traffic_type(struct spi_buffer *buf, uint8_t type)
{
  buf->cb[0] = type;
}
static inline uint8_t spi_buffer_get_traffic_type(struct spi_buffer *buf)
{
  return buf->cb[0];
}
static inline void *spi_buffer_push(struct spi_buffer *buf, uint32_t size)
{
  char *p, *start, *data;

  if (buf == NULL)
  {
    return NULL;
  }

  if (size == 0U)
  {
    return buf->data;
  }

  p = (char *)buf;
  data = buf->data;
  start = p + sizeof(struct spi_buffer);
  if ((data - size) < start)
  {
    spi_err("Illegal try of spi buffer push!\n");
    return NULL;
  }

  buf->data = data - size;
  buf->len += size;
  return buf->data;
}
static inline void *spi_buffer_pull(struct spi_buffer *buf, uint32_t size)
{
  char *p, *end, *data;

  if (buf == NULL)
  {
    return NULL;
  }

  if (size == 0U)
  {
    return buf->data;
  }

  p = (char *)buf;
  data = buf->data;
  end = p + sizeof(struct spi_buffer) + buf->cap;
  if ((data + size) > end)
  {
    spi_err("Illegal try of spi buffer pull\n");
    return NULL;
  }

  buf->data = data + size;
  buf->len -= size;
  return buf->data;
}
static struct spi_buffer *spi_buffer_alloc(uint32_t size, uint32_t reserve)
{
  uint32_t cap;
  uint32_t extra;
  struct spi_buffer *buf;
  uint32_t desc_size = sizeof(struct spi_buffer);

  cap = (size + reserve + SPI_BUF_ALIGN_MASK) & ~SPI_BUF_ALIGN_MASK;
  buf = pvPortMalloc(cap + desc_size);
  if (buf == NULL)
  {
    return NULL;
  }

  buf->flags = 0;
  buf->len = size;
  buf->cap = cap;
  buf->data = (char *)buf + desc_size + reserve;
  (void)memset(buf->cb, 0, sizeof(buf->cb));
  /* Fill in the debug pattern. */
  extra = cap - size - reserve;
  while (extra > 0U)
  {
    uint8_t *p = (uint8_t *)buf + desc_size;

    p[cap - extra] = 0x88;
    extra--;
  }
  return buf;
}
void spi_buffer_free(struct spi_buffer *buf)
{
  if (buf)
  {
    vPortFree(buf);
  }
}
static int32_t inline spi_header_validate(struct spi_header *hdr)
{
  if (hdr->magic != SPI_HEADER_MAGIC_CODE)
  {
    spi_err("Invalid magic 0x%" PRIx16 "\n", hdr->magic);
    return 0;
  }

  if (hdr->len > SPI_XFER_MTU_BYTES)
  {
    spi_err("invalid len %" PRIu16 "\n", hdr->len);
    return 0;
  }
  return 1;
}
static int32_t spi_xfer_one(struct spi_xfer_engine *engine, struct spi_buffer *txbuf,
                            int32_t wait_txn_rdy)
{
  void *txp;
  int32_t ret;
  int32_t err = -1;
  uint16_t xfer_size;
  struct spi_header mh;
  struct spi_header *pmh;
  struct spi_header *psh;
  struct spi_buffer *rxbuf = NULL;
  int32_t rx_restore = 0;

  spi_trace(SPI_TP_NONE, "wait_txn_rdy %" PRIi32 "\n", wait_txn_rdy);
  engine->state = SPI_XFER_STATE_FIRST_PART;
  spi_port_set_phase(SPI_XFER_STATE_FIRST_PART);
  if (wait_txn_rdy != 0)
  {
    /* SPI_RDY is level-readable as well as edge-signalled.  Sampling it on
     * both sides of the bounded event wait closes the race where EXTI sets a
     * coalesced/lost event while the pin already advertises readiness. */
    if (spi_port_is_ready() != 0)
    {
      if (spi_wait_event(engine, SPI_EVT_TXN_RDY, 0) == 0)
      {
        SPI_STAT_INC(&engine->stat, recovered_lost_ready, 1U);
      }
    }
    else if (spi_wait_event(engine, SPI_EVT_TXN_RDY,
                            SPI_WAIT_TXN_TIMEOUT_MS) == 0)
    {
      SPI_STAT_INC(&engine->stat, wait_txn_timeouts, 1U);
      if (spi_port_is_ready() != 0)
      {
        /* Consume a late event if it raced the timeout.  The high level is
         * sufficient proof that this transaction may proceed even if the
         * edge was not retained by the event group. */
        (void)spi_wait_event(engine, SPI_EVT_TXN_RDY, 0);
        SPI_STAT_INC(&engine->stat, recovered_lost_ready, 1U);
      }
      else
      {
        spi_err("waiting for spi txn ready timeouted\n");
        return SPI_XFER_TXN_RDY_TIMEOUT;
      }
    }
  }

  /* Re-initialize events in case of pending ones. */
  (void)spi_clear_event(engine, SPI_EVT_HW_XFER_DONE | SPI_EVT_HDR_ACKED);

  /* Yes, this allocation will be wasted if there is no data from slave. */
  rxbuf = spi_buffer_alloc(SPI_XFER_MTU_BYTES + sizeof(struct spi_header), 0);
  if (rxbuf == NULL)
  {
    spi_err("No mem for rxbuf\n");
    SPI_STAT_INC(&engine->stat, mem_err, 1U);
    return -1;
  }

  spi_trace(SPI_TP_FIRST_TXN_START, "start the first transaction\n");
  if (txbuf != NULL)
  {
    uint16_t msglen;
    uint8_t type = spi_buffer_get_traffic_type(txbuf);

    if (engine->rx_stall == 0)
    {
      pmh = txbuf->data;

      msglen = txbuf->len - sizeof(struct spi_header);

      /* Initialize master header. */
      SPI_HEADER_INIT(pmh, type, msglen);
      txp = txbuf->data;
      xfer_size = (txbuf->len + SPI_BUF_ALIGN_MASK) & ~SPI_BUF_ALIGN_MASK;
    }
    else
    {
      SPI_HEADER_INIT(&mh, 0, 0);
      txp = &mh;
      xfer_size = sizeof(struct spi_header);
    }
  }
  else
  {
    /* Initialize master header. */
    SPI_HEADER_INIT(&mh, 0, 0);
    txp = &mh;
    xfer_size = sizeof(struct spi_header);
  }

  if (spi_txrx(engine, txp, rxbuf->data, xfer_size) != 0)
  {
    spi_err("Failed to do the first transaction\n");
    err = SPI_XFER_TRANSPORT_ERROR;
    goto out;
  }

  psh = rxbuf->data;
  spi_trace(SPI_TP_FIRST_TXN_END,
            "slave spi header, magic 0x%" PRIx16 ", len (%" PRIu16 ", 0x%" PRIx16 "), version %" PRIu16
            ", type %" PRIx16 ", flags 0x%" PRIx16 ", rsvd 0x%" PRIx16 "\n",
            psh->magic, psh->len, psh->len, psh->version, psh->type, psh->flags, psh->rsvd);
  ret = spi_header_validate(psh);
  if (ret == 0)
  {
    spi_err("Invalid spi header from peer, magic 0x%" PRIx16 ", len (%" PRIu16 ", 0x%" PRIx16 "), version %" PRIu16
            ", type %" PRIx16 "flags 0x%" PRIx16 ", rsvd 0x%" PRIx16 "\n",
            psh->magic, psh->len, psh->len, psh->version, psh->type, psh->flags, psh->rsvd);
    SPI_STAT_INC(&engine->stat, hdr_err, 1U);
    err = SPI_XFER_PROTOCOL_ERROR;
    goto out;
  }

  if (engine->rx_stall == 0)
  {
    if (psh->rx_stall != 0U)
    {
      SPI_STAT_INC(&engine->stat, rx_stall, 1U);
      spi_trace(SPI_TP_NONE, "Slave RX stalled\n");
    }
  }
  else if (psh->rx_stall == 0U)
  {
    rx_restore = 1;
  }
  else
  {
    /* Normal case */
  }
  engine->rx_stall = psh->rx_stall;

  /* Receive the remaining data from slave if any. */
  if ((psh->len + sizeof(struct spi_header)) > xfer_size)
  {
    uint8_t *rxp = (uint8_t *)rxbuf->data;
    uint16_t remain = psh->len + sizeof(struct spi_header) - xfer_size;

    spi_trace(SPI_TP_SECOND_TXN_START, "Receiving remaining data\n");
    engine->state = SPI_XFER_STATE_SECOND_PART;
    spi_port_set_phase(SPI_XFER_STATE_SECOND_PART);
    remain = (remain + SPI_BUF_ALIGN_MASK) & ~SPI_BUF_ALIGN_MASK;
    rxp += xfer_size;
    if (spi_rx(engine, rxp, remain) != 0)
    {
      spi_err("Failed to receive the remaining bytes\n");
      err = SPI_XFER_TRANSPORT_ERROR;
      goto out;
    }
    spi_trace(SPI_TP_SECOND_TXN_END, "Remaining transfer completed\n");
  }

  /* Free txbuf after the message transaction. */
  if (txbuf != NULL)
  {
    if ((engine->rx_stall == 0) && (rx_restore == 0))
    {
      engine->txbuf = NULL;
      spi_buffer_free(txbuf);
    }
  }

  if (psh->len > 0U)
  {
    SPI_STAT_INC(&engine->stat, rx_pkts, 1U);
    SPI_STAT_INC(&engine->stat, rx_bytes, psh->len);
    (void)spi_buffer_pull(rxbuf, sizeof(struct spi_header));
    /* Rx buffer length fix-up */
    rxbuf->len = psh->len;
    /* Get message type from header and store in buffer's control block */
    uint8_t msg_type = psh->type;
    spi_buffer_set_traffic_type(rxbuf, msg_type);

    /*
     * Note: Thread safety consideration required here.
     * If a queue is unbound by another thread while we're accessing it,
     * or if multiple transfers are accessing rxq_bound bitmap concurrently,
     * race conditions could occur. Consider using appropriate synchronization.
     */

    /* Select appropriate queue based on type */
    if ((msg_type < (uint8_t)SPI_MSG_CTRL_TRAFFIC_TYPE_MAX) &&
        ((engine->rxq_bound & (1U << msg_type)) != 0U))
    {
      if (psh->len < 256U)
      {
        struct spi_buffer *rxbuf_resized = spi_buffer_alloc(psh->len, 0);
        if (rxbuf_resized == NULL)
        {
          spi_err("No mem for rxbuf\n");
          SPI_STAT_INC(&engine->stat, mem_err, 1U);
        }
        else
        {
          rxbuf_resized->flags = rxbuf->flags;
          (void)spi_port_memcpy(rxbuf_resized->data, rxbuf->data, psh->len);
          spi_buffer_free(rxbuf);
          rxbuf = rxbuf_resized;
        }
      }

      /* A fixed terminal-only trace distinguishes arrival at SPI from later
       * parser consumption. Exact records only: never expose packet contents. */
      if ((Debug_UART_NcpTraceEnabled() != 0U) &&
          (((rxbuf->len == 11U) && (memcmp(rxbuf->data, "\r\nSEND OK\r\n", 11U) == 0)) ||
           ((rxbuf->len == 13U) && (memcmp(rxbuf->data, "\r\nSEND FAIL\r\n", 13U) == 0))))
      {
        Debug_UART_NcpTerminalObservedAtSpi();
      }
      do
      {
        ret = xQueueSend(engine->rxq[msg_type], &rxbuf, pdMS_TO_TICKS(10U));
      } while ((ret != pdTRUE) && (engine->stop == 0));
      if (ret != pdTRUE)
      {
        spi_trace(SPI_TP_NONE, "failed to send to type %d rxq, msg discarded\r\n", msg_type);
        spi_buffer_free(rxbuf);
        SPI_STAT_INC(&engine->stat, rx_drop, 1U);
      }
      else
      {
        if (engine->cb[msg_type] != NULL)
        {
          engine->cb[msg_type](engine->cb_arg[msg_type]);
        }
      }
    }
    else
    {
      /* No queue bound for this type, discard message */
      spi_trace(SPI_TP_NONE, "No queue bound for type %d, msg discarded\r\n", msg_type);
      spi_buffer_free(rxbuf);
      SPI_STAT_INC(&engine->stat, rx_drop, 1U);
    }
  }
  else if (rxbuf != NULL)
  {
    spi_buffer_free(rxbuf);
  }
  else
  {
    /* No rx bytes to read */
  }

  /* Wait until slave acknowledged header. */
  spi_trace(SPI_TP_WAIT_HDR_ACK_START, "waiting for header ack\n");
  while (spi_wait_event(engine, SPI_EVT_HDR_ACKED, SPI_WAIT_HDR_ACK_TIMEOUT_MS) == 0)
  {
    if ((spi_port_is_ready() == 0) || (engine->stop != 0))
    {
      break;
    }

    SPI_STAT_INC(&engine->stat, wait_hdr_ack_timeouts, 1U);
  }
  spi_trace(SPI_TP_WAIT_HDR_ACK_END, "Got header ack\n");

  return 0;

out:
  /* Bytes may already have reached the NCP. Local DMA cleanup cannot prove
   * rejection or restore the peer parser boundary. Stop before any replay;
   * retain TX ownership for the existing coordinated teardown. */
  engine->transport_fault = err;
  engine->stop = 1;
  /* A timed-out DMA can still reference this destination. Never release it
   * before both local DMA channels have stopped. Failure closes this worker. */
  if ((err == SPI_XFER_TRANSPORT_ERROR) && (spi_port_abort() != 0))
  {
    engine->failed_rxbuf = rxbuf;
    engine->stop = 1;
    /* Keep this stack frame too: DMA TX may still reference the local header.
     * The recovery barrier times out without deleting us. Only this DMA owner
     * retries its local abort, sleeping between attempts rather than spinning. */
    do { vTaskDelay(pdMS_TO_TICKS(100U)); } while (spi_port_abort() != 0);
    engine->failed_rxbuf = NULL;
  }
  spi_buffer_free(rxbuf);
  return err;
}
static void packet(const uint8_t *payload,unsigned len,unsigned txlen,unsigned small_fail) {
 struct spi_xfer_engine e={0};
 struct spi_buffer *tx=NULL;
 assert(!live && !received);
 memset(wire,0xA5,sizeof wire);
 struct spi_header *h=(struct spi_header*)wire;
 SPI_HEADER_INIT(h,SPI_MSG_CTRL_TRAFFIC_AT_CMD,len);
 memcpy(wire+sizeof *h,payload,len);
 if(txlen){
   tx=spi_buffer_alloc(txlen,sizeof *h);
   assert(tx);memset(tx->data,0xC3,txlen);
   assert(spi_buffer_push(tx,sizeof *h));
   e.txbuf=tx;
 }
 allocations=reads=wire_offset=queue_calls=first_size=second_size=0;
 fail_small=small_fail;fail_read=0;
 e.rxq[0]=(void*)1;e.rxq_bound=1;
 assert(spi_xfer_one(&e,tx,1)==0);
 assert(received && received->len==len && queue_calls==1);
 assert(memcmp(received->data,payload,len)==0);
 assert(spi_buffer_get_traffic_type(received)==SPI_MSG_CTRL_TRAFFIC_AT_CMD);
 assert(e.stat.rx_bytes==len && e.stat.rx_pkts==1 && !e.txbuf);
 unsigned expected_first=txlen ? ((txlen+sizeof *h+3)&~3U) : sizeof *h;
 unsigned expected_second=len+sizeof *h>expected_first ?
   ((len+sizeof *h-expected_first+3)&~3U) : 0;
 assert(first_size==expected_first && second_size==expected_second);
 assert(reads==1+(expected_second!=0));
 assert(e.stat.mem_err==(small_fail && len<256));
 spi_buffer_free(received);received=NULL;assert(!live);
}
int main(void){
 assert(sizeof(struct spi_header)==8);
 /* Public response with the real NUL byte, and the previously observed
    malformed response without it. Preserve their distinct exact lengths. */
 const uint8_t valid[]={'+','F','S',':','R','E','A','D',',','1',',',0,'\r','\n'};
 const uint8_t absent[]="+FS:READ,1,\r\n";
 unsigned txsizes[]={0,1,3,4,8,13,14,64,255,256,SPI_XFER_MTU_BYTES};
 for(unsigned i=0;i<sizeof txsizes/sizeof *txsizes;i++){
   packet(valid,sizeof valid,txsizes[i],0);
   packet(absent,sizeof absent-1,txsizes[i],0);
 }
 puts("PASS real NUL remains 14 bytes; absent payload remains 13 bytes across 11 aligned TX/header/remaining-transfer boundaries");
 uint8_t values[SPI_XFER_MTU_BYTES];
 for(unsigned i=0;i<sizeof values;i++)values[i]=(uint8_t)i;
 unsigned lengths[]={1,3,4,7,8,13,14,31,255,256,257,SPI_XFER_MTU_BYTES};
 for(unsigned j=0;j<sizeof lengths/sizeof *lengths;j++)
   for(unsigned i=0;i<sizeof txsizes/sizeof *txsizes;i++)
     packet(values,lengths[j],txsizes[i],0);
 puts("PASS all 256 byte values unchanged; 132 short-resize/full-buffer MTU and TX/RX length combinations");
 packet(valid,sizeof valid,0,1);
 packet(absent,sizeof absent-1,14,1);
 puts("PASS failed small-buffer resize retains exact original packet and releases each allocation once");
 for(unsigned step=1;step<=2;step++){
   struct spi_xfer_engine e={0};e.rxq[0]=(void*)1;e.rxq_bound=1;
   memset(wire,0,sizeof wire);SPI_HEADER_INIT((struct spi_header*)wire,0,sizeof valid);
   memcpy(wire+8,valid,sizeof valid);
   allocations=reads=wire_offset=queue_calls=0;fail_small=0;fail_read=step;
   assert(spi_xfer_one(&e,NULL,0)==SPI_XFER_TRANSPORT_ERROR);
   assert(!received && !live && !queue_calls);
 }
 puts("PASS either transfer failure publishes no partial FS packet and frees RX only after successful local abort");
 return 0;
}
