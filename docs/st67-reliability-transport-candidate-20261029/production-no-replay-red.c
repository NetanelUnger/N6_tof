#define CANDIDATE 0
#define SPI_XFER_PROTOCOL_ERROR (-4)
#define SPI_XFER_MAX_RETRIES 3U
#define SPI_XFER_MAX_CONTIGUOUS_BURST 8U
#define SPI_XFER_F_SKIP_FIRST_TXN_WAIT 1U
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
static unsigned fail_first_alloc;
static unsigned live,allocations,fail_small,reads,wire_offset,queue_calls;
static unsigned first_size,second_size,fail_read;
static uint8_t wire[4096];
static struct spi_buffer *received;
static void *pvPortMalloc(size_t n) {
 ++allocations;
 if(fail_first_alloc){fail_first_alloc=0;return NULL;}
 if (fail_small && allocations==2) return NULL;
 void *p=malloc(n);assert(p);++live;return p;
}
static void vPortFree(void *p) {assert(p && live);--live;free(p);}
static unsigned Debug_UART_NcpTraceEnabled(void){return 0;}
static void Debug_UART_NcpTerminalObservedAtSpi(void){assert(0);}
static void *spi_port_memcpy(void *d,const void *s,size_t n){return memcpy(d,s,n);}
static void spi_port_set_phase(unsigned n){(void)n;}
static int spi_port_is_ready(void);
static int spi_port_abort(void);
static void vTaskDelay(unsigned n);
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

static unsigned transaction,cs_high,cs_low,accepted,attempted,abort_calls,elapsed;
static unsigned ready,scenario,fail_remaining,queue_full,ack_stuck,stop_after;
static unsigned abort_failures,ready_waits;
static struct spi_xfer_engine *active;
static int32_t spi_wait_event(void *p,uint32_t event,int32_t ms){
 struct spi_xfer_engine *e=p;
 if(event==SPI_EVT_TXN_RDY && ms>0 && scenario==7){return ++ready_waits>1;}
 if(event==SPI_EVT_HDR_ACKED && ack_stuck){elapsed+=ms;if(++queue_calls==stop_after)e->stop=1;return 0;}
 return 1;
}
static int32_t spi_clear_event(struct spi_xfer_engine *e,uint32_t event){active=e;reads=wire_offset=0;return 0;}
static int32_t spi_txrx(struct spi_xfer_engine *e,void *tx,void *rx,uint16_t n){
 active=e;++transaction;++reads;assert(n%4==0);
 struct spi_header *sent=tx;
 unsigned stalled=scenario==1 && transaction<=2;
 unsigned payload=scenario==2 && transaction==1 ? 96 : scenario==3 ? 96 : 0;
 if(sent->len){++attempted;if(!stalled)++accepted;}
 memset(wire,0,sizeof wire);SPI_HEADER_INIT((struct spi_header*)wire,0,payload);
 ((struct spi_header*)wire)->rx_stall=stalled;
 memset(wire+sizeof(struct spi_header),0x51,payload);
 if(scenario==4)((struct spi_header*)wire)->magic=0;
 if(scenario==5)return -1;
 memcpy(rx,wire,n);wire_offset=n;
 if(scenario==0 || scenario==7)ready=0;
 if((scenario==1 && transaction==4)||(scenario==2 && transaction==2))ready=0;
 return 0;
}
static int32_t spi_rx(struct spi_xfer_engine *e,void *rx,uint16_t n){
 ++reads;if(fail_remaining){fail_remaining=0;return -1;}
 memcpy(rx,wire+wire_offset,n);wire_offset+=n;return 0;
}
static int xQueueSend(QueueHandle_t q,void *p,unsigned wait){
 assert(wait==10);++queue_calls;
 if(queue_full){elapsed+=wait;if(queue_calls==stop_after)active->stop=1;return 0;}
 assert(!received);received=*(struct spi_buffer**)p;return pdTRUE;
}
static int spi_port_set_cs(unsigned on){if(on)++cs_high;else ++cs_low;return 0;}
static struct spi_buffer *spi_get_txbuf(struct spi_xfer_engine *e){return e->txbuf;}

static int spi_port_is_ready(void){return ready;}
static int spi_port_abort(void){++abort_calls;return abort_calls<=abort_failures?-1:0;}
static void vTaskDelay(unsigned n){elapsed+=n;if(abort_failures && abort_calls<=abort_failures){assert(active->failed_rxbuf && active->txbuf && live==2);}}
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
}static int32_t spi_do_xfer(struct spi_xfer_engine *engine, uint32_t flags)
{
  struct spi_buffer *txbuf;
  int32_t xfer_status;
  int32_t rx_pending;
  int32_t wait_txn_rdy;
  uint32_t burst_count = 0U;
  uint32_t retry_count = 0U;

  /*
   * The NCP owns SPI_RDY. If a boot-mode, wiring or protocol fault holds it
   * high, the original unbounded loop keeps this high-priority worker ready
   * forever and can starve the ThreadX application. A one-tick pause after a
   * bounded burst preserves pending work and normal multi-packet transfers,
   * while allowing modem-init timeouts and diagnostics to run.
   */
  while (engine->stop == 0)
  {
    /* Get txbuf */
    txbuf = spi_get_txbuf(engine);

    /* Read data ready GPIO level */
    rx_pending = spi_port_is_ready();

    spi_trace(SPI_TP_NONE, "txbuf %" PRIuPTR ", rx_pending %" PRIi32 "\n", txbuf, rx_pending);
    /* Check if txbuf is valid or data is ready for transfer */
    if ((txbuf != NULL) || (rx_pending == 1))
    {
      /* Assert chip select */
      spi_trace(SPI_TP_ASSERT_CS, "Assert CS\n");
      (void)spi_port_set_cs(1);

      /* Transfer one packet */
      if ((flags & SPI_XFER_F_SKIP_FIRST_TXN_WAIT) != 0U)
      {
        flags &= ~SPI_XFER_F_SKIP_FIRST_TXN_WAIT;
        wait_txn_rdy = 0;
      }
      else
      {
        wait_txn_rdy = 1;
      }

      xfer_status = spi_xfer_one(engine, txbuf, wait_txn_rdy);

      /* De-assert chip select */
      spi_trace(SPI_TP_DEASSERT_CS, "Deassert CS\n");
      (void)spi_port_set_cs(0);
      engine->state = SPI_XFER_STATE_TXN_DONE;

      if (xfer_status != 0)
      {
        int32_t ready_after_failure = spi_port_is_ready();

        retry_count++;
        if (xfer_status == SPI_XFER_TRANSPORT_ERROR)
        {
          /* A timed-out DMA leaves HAL_SPI busy, so another transfer would
           * fail immediately. Abort only the local peripheral/DMA state after
           * CS is low; the NCP is not reset and the owned TX buffer is kept. */
          if (spi_port_abort() == 0)
          {
            SPI_STAT_INC(&engine->stat, transport_recoveries, 1U);
          }
          else
          {
            spi_err("failed to abort incomplete local spi transaction\n");
          }
        }
        if (xfer_status == SPI_XFER_TXN_RDY_TIMEOUT)
        {
          /* The level may have changed while CS was being deasserted.  Count
           * this as a recovered edge and retry inside this bounded activation;
           * setting a fresh event here would reset the local retry budget. */
          if (ready_after_failure != 0)
          {
            SPI_STAT_INC(&engine->stat, recovered_lost_ready, 1U);
          }
        }

        /* A polling/DMA failure can leave SPI_RDY high with no future edge.
         * Retry the same owned buffer while the NCP still requests service.
         * If a TX buffer is retained, a low level is also safe: the next
         * spi_xfer_one() performs its normal bounded ready wait. */
        if ((retry_count < SPI_XFER_MAX_RETRIES) &&
            ((ready_after_failure != 0) || (engine->txbuf != NULL)))
        {
          vTaskDelay(pdMS_TO_TICKS(1U));
          continue;
        }

        /* Ownership remains with engine->txbuf.  Do not free or dequeue a
         * replacement. After an exhausted window the worker returns to its
         * event wait; a later real ready/TX event can retry this exact packet. */
        if (retry_count >= SPI_XFER_MAX_RETRIES)
        {
          SPI_STAT_INC(&engine->stat, retry_exhaustions, 1U);
          spi_err("spi transaction retries exhausted; tx buffer retained\n");
        }
        break;
      }

      retry_count = 0U;

      burst_count++;
      if (burst_count >= SPI_XFER_MAX_CONTIGUOUS_BURST)
      {
        burst_count = 0U;
        vTaskDelay(pdMS_TO_TICKS(1U));
      }
    }
    else
    {
      /* Neither txbuf nor rx_pending require processing, exit loop */
      break;
    }
  }

  return 0;
}
static void reset(struct spi_xfer_engine *e,unsigned which){
 assert(!live && !received);memset(e,0,sizeof *e);scenario=which;
 transaction=cs_high=cs_low=accepted=attempted=abort_calls=elapsed=0;
 allocations=reads=wire_offset=queue_calls=fail_small=fail_first_alloc=0;
 queue_full=ack_stuck=stop_after=fail_remaining=abort_failures=ready_waits=0;
 ready=1;e->rxq[0]=(void*)1;e->rxq_bound=1;active=e;
}
static void add_tx(struct spi_xfer_engine *e){
 e->txbuf=spi_buffer_alloc(4,sizeof(struct spi_header));assert(e->txbuf);
 memset(e->txbuf->data,0xa5,4);assert(spi_buffer_push(e->txbuf,sizeof(struct spi_header)));
}
static void release_retained(struct spi_xfer_engine *e){
 assert(e->stop && !e->failed_rxbuf);
 if(e->txbuf){spi_buffer_free(e->txbuf);e->txbuf=NULL;}
 assert(!live);
}
int main(void){
 struct spi_xfer_engine e;
 reset(&e,2);add_tx(&e);fail_remaining=1;
 struct spi_buffer *saved=e.txbuf;
 spi_do_xfer(&e,0);
 assert(accepted==1 && attempted==1 && transaction==1);
 puts("PASS ambiguous remaining-RX failure never replays accepted TX");
#if CANDIDATE
 assert(e.transport_fault==SPI_XFER_TRANSPORT_ERROR && e.stop==1 && e.txbuf==saved && live==1 && !received && abort_calls==1);
 ready=1;spi_do_xfer(&e,0);assert(transaction==1 && e.txbuf==saved);
 release_retained(&e);
 puts("PASS new RDY activation cannot revive sticky fault; TX retained for teardown");
 reset(&e,4);add_tx(&e);spi_do_xfer(&e,0);
 assert(e.transport_fault==SPI_XFER_PROTOCOL_ERROR && accepted==1 && transaction==1 && e.stat.hdr_err==1 && abort_calls==0);
 release_retained(&e);
 puts("PASS invalid peer header stops without replay even when local DMA completed");
 reset(&e,5);add_tx(&e);spi_do_xfer(&e,0);
 assert(e.transport_fault==SPI_XFER_TRANSPORT_ERROR && accepted==1 && transaction==1 && abort_calls==1);
 release_retained(&e);
 reset(&e,5);spi_do_xfer(&e,0);
 assert(e.transport_fault && !accepted && transaction==1 && !live);
 puts("PASS first-transfer ambiguity fences both TX-present and RX-only transactions");
 reset(&e,2);add_tx(&e);fail_remaining=1;abort_failures=2;spi_do_xfer(&e,0);
 assert(e.transport_fault && e.stop && accepted==1 && abort_calls==3 && elapsed==200 && !e.failed_rxbuf && live==1);
 release_retained(&e);
 puts("PASS failed DMA abort retains RX/TX and local stack until successful third abort; no replay");
 reset(&e,1);add_tx(&e);spi_do_xfer(&e,0);
 assert(transaction==4 && cs_high==4 && cs_low==4 && attempted==2 && accepted==1 && !live && !e.txbuf && !e.transport_fault);
 puts("PASS explicit rx_stall retains original packet across separate transactions and accepts once");
 reset(&e,0);add_tx(&e);fail_first_alloc=1;spi_do_xfer(&e,0);
 assert(transaction==1 && cs_high==2 && accepted==1 && !live && !e.transport_fault && e.stat.mem_err==1);
 puts("PASS proven zero-wire allocation failure remains retryable");
 reset(&e,7);ready=0;add_tx(&e);spi_do_xfer(&e,0);
 assert(ready_waits==2 && transaction==1 && cs_high==2 && accepted==1 && !live && !e.transport_fault);
 puts("PASS pre-transfer ready timeout remains retryable without creating a protocol fence");
 reset(&e,3);queue_full=1;stop_after=4;assert(spi_xfer_one(&e,NULL,1)==0);
 assert(e.stop && queue_calls==4 && elapsed==40 && !live && !e.transport_fault);
 puts("PASS external stop still escapes full RX queue; independent aggregate queue bound remains open");
 memset(&xfer_engine,0,sizeof xfer_engine);xfer_engine.initialized=1;xfer_engine.transport_fault=-3;
 struct spi_msg msg={0};uint8_t payload[4]={1,2,3,4};msg.op_type=SPI_MSG_OP_DATA;msg.data=payload;msg.data_len=4;
 unsigned prior=allocations;assert(spi_write(&msg,0)==-6 && spi_read(&msg,0)==-6 && allocations==prior);
 assert(spi_transaction_faulted()==-3);xfer_engine.transport_fault=0;xfer_engine.stop=1;
 assert(spi_write(&msg,0)==-6 && spi_read(&msg,0)==-6 && allocations==prior);
 puts("PASS fault/stop refuse new read/write before allocation and do not return soft BUSY");
#endif
 return 0;
}
