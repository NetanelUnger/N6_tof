
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define EINVAL 22
#define EIO 5
#define EAGAIN 11
#define ENOMEM 12
#define RX_BUF_SIZE 4096U
#define portMAX_DELAY 0xffffffffU
#define SPI_MSG_CTRL_TRAFFIC_AT_CMD 0
#define AT_LOG_HOST_IN(...) ((void)0)
#define Debug_UART_NcpTrace(...) ((void)0)
#define SYS_LOG_ERROR(...) ((void)0)
#define CONTAINER_OF(p,t,f) ((t*)((char*)(p)-offsetof(t,f)))
static unsigned spi_fault,delay_count,fault_on_receive;
static int spi_transaction_faulted(void){return (int)spi_fault;}
static void vTaskDelay(unsigned n){assert(n==1);++delay_count;}
static unsigned critical,freed,reads,wakes,packet_size;
#define taskENTER_CRITICAL() (++critical)
#define taskEXIT_CRITICAL() (--critical)
struct modem_iface {int32_t (*mdm_read)(struct modem_iface*,uint8_t*,size_t,size_t*);};
struct modem_cmd_handler_data {void*user_data;uint8_t*rx_buf;size_t rx_buf_len;
 bool tx_desynchronized;int last_error;};
struct modem {struct modem_cmd_handler_data handler_data;struct modem_iface iface;void*spi_rx_pending;uint8_t*spi_rx_pending_data;
 size_t spi_rx_pending_len,spi_rx_pending_offset;void*rx_data;uint32_t rx_data_len;unsigned sem_response;};
#define MODEM_CMD_DIRECT_DEFINE(n) static int32_t n(struct modem_cmd_handler_data*data,uint16_t len,char**argv,uint16_t argc)
static volatile uint32_t fs_read_callbacks,fs_read_declared,fs_read_available,fs_read_copied;
static uint8_t packet[1024];static unsigned ownership;
static int BusIo_SPI_ReceivePtr(unsigned type,void**owner,uint8_t**bytes,unsigned wait){
 assert(!reads && !freed && !ownership && !type && wait==portMAX_DELAY);
 if(fault_on_receive)spi_fault=1;
 ++reads;ownership=1;*owner=&ownership;*bytes=packet;return (int)packet_size;}
static int BusIo_SPI_Free(void*p){assert(p==&ownership && ownership && !freed);ownership=0;++freed;return 0;}
static int modem_cmd_handler_set_error(struct modem_cmd_handler_data*d,int e){d->last_error=e;return 0;}
static int xSemaphoreGive(unsigned s){++wakes;return 1;}
static int32_t modem_iface_spi_read(struct modem_iface *iface,
                                    uint8_t *buf, size_t size, size_t *bytes_read)
{
  struct modem *mdm;
  size_t available;
  size_t copy_len;
  int32_t received;

  if ((iface == NULL) || (buf == NULL) || (bytes_read == NULL) || (size == 0U))
  {
    return -EINVAL;
  }

  mdm = CONTAINER_OF(iface, struct modem, iface);
  *bytes_read = 0U;
  if (spi_transaction_faulted() != 0)
  {
    mdm->handler_data.tx_desynchronized = true;
    /* Retained packet tail belongs to teardown; do not feed a later parser.
     * The parser must yield while the existing recovery owner quiesces it. */
    vTaskDelay(1U);
    return -EIO;
  }
  if (mdm->spi_rx_pending == NULL)
  {
    /* Take ownership of the complete framed SPI packet. Never ask spi_read()
     * to copy into the parser's remaining space: that API frees the packet
     * even when its destination is shorter than the packet. */
    received = BusIo_SPI_ReceivePtr(SPI_MSG_CTRL_TRAFFIC_AT_CMD,
                                    &mdm->spi_rx_pending,
                                    &mdm->spi_rx_pending_data,
                                    portMAX_DELAY);
    if ((received <= 0) || (mdm->spi_rx_pending == NULL) ||
        (mdm->spi_rx_pending_data == NULL))
    {
      if (mdm->spi_rx_pending != NULL)
      {
        (void)BusIo_SPI_Free(mdm->spi_rx_pending);
        mdm->spi_rx_pending = NULL;
      }
      mdm->spi_rx_pending_data = NULL;
      return (received < 0) ? received : -EIO;
    }
    mdm->spi_rx_pending_len = (size_t)received;
    mdm->spi_rx_pending_offset = 0U;
  }

  available = mdm->spi_rx_pending_len - mdm->spi_rx_pending_offset;
  copy_len = (available < size) ? available : size;
  (void)memcpy(buf, mdm->spi_rx_pending_data + mdm->spi_rx_pending_offset,
               copy_len);
  mdm->spi_rx_pending_offset += copy_len;
  AT_LOG_HOST_IN(buf, copy_len);
  Debug_UART_NcpTrace("RX read", buf, copy_len, (int32_t)copy_len);
  *bytes_read = copy_len;

  if (mdm->spi_rx_pending_offset == mdm->spi_rx_pending_len)
  {
    (void)BusIo_SPI_Free(mdm->spi_rx_pending);
    mdm->spi_rx_pending = NULL;
    mdm->spi_rx_pending_data = NULL;
    mdm->spi_rx_pending_len = 0U;
    mdm->spi_rx_pending_offset = 0U;
  }
  return 0;
}static int32_t cmd_handler_process_iface_data(struct modem_cmd_handler_data *data, struct modem_iface *iface)
{
  size_t bytes_read = 0;
  int32_t ret;

  if ((data->rx_buf == NULL) || (iface == NULL) || (iface->mdm_read == NULL))
  {
    return -EINVAL;
  }
  /* Read as much as possible into the linear buffer */
  size_t room = RX_BUF_SIZE - data->rx_buf_len;
  if (room == 0U)
  {
    return -ENOMEM;
  }
  ret = iface->mdm_read(iface, data->rx_buf + data->rx_buf_len, room, &bytes_read);
  if ((ret < 0) || (bytes_read == 0U))
  {
    return 0;
  }
  data->rx_buf_len += bytes_read;

  return 0;
}MODEM_CMD_DIRECT_DEFINE(on_cmd_fs_readfile)
{
  struct modem *mdm = (struct modem *) data->user_data;

  uint8_t *ptr;
  uint32_t offset;
  uint8_t *endptr;
  uint32_t rx_data_len;

  ++fs_read_callbacks;
  fs_read_available = data->rx_buf_len;

  if (data->rx_buf == NULL)
  {
    return -EINVAL;
  }
  ptr = data->rx_buf + len;
  data->rx_buf[data->rx_buf_len] = 0;

  rx_data_len = strtol((char *) ptr, (char **)&endptr, 10);
  fs_read_declared = rx_data_len;
  if ((endptr == ptr) || (*endptr != ','))
  {
    SYS_LOG_ERROR("Invalid FS read response format");
    return -EINVAL;
  }
  offset = endptr - data->rx_buf + 1;

  /* A declared byte must actually be present before its delimiter. Empty+OK
   * is a malformed binary response, not a validated encoding for NUL. */
  if (rx_data_len == 1U)
  {
    size_t available = data->rx_buf_len - offset;
    const uint8_t *payload = data->rx_buf + offset;
    if ((available >= 3U) && (payload[1] == '\r') && (payload[2] == '\n'))
    {
      /* A real binary byte, including CR, LF or NUL. */
    }
    else if (((available >= 6U) && !memcmp(payload, "\r\nOK\r\n", 6U)) ||
             ((available >= 8U) && !memcmp(payload, "\r\n\r\nOK\r\n", 8U)))
    {
      taskENTER_CRITICAL();
      data->tx_desynchronized = true;
      (void)modem_cmd_handler_set_error(data, -EIO);
      (void)xSemaphoreGive(mdm->sem_response);
      taskEXIT_CRITICAL();
      return -EIO;
    }
    else return -EAGAIN;
  }

  if (data->rx_buf_len >= (offset + rx_data_len))
  {
    taskENTER_CRITICAL();
    if ((mdm->rx_data == NULL) || (rx_data_len != mdm->rx_data_len))
    {
      /* A length mismatch has no trustworthy binary boundary. Do not copy or
       * accept a following OK as success; only coordinated restart clears it. */
      data->tx_desynchronized = true;
      (void)modem_cmd_handler_set_error(data, -EIO);
      (void)xSemaphoreGive(mdm->sem_response);
      taskEXIT_CRITICAL();
      return -EINVAL;
    }
    (void)memcpy(mdm->rx_data, endptr + 1, rx_data_len);
    fs_read_copied = rx_data_len;
    taskEXIT_CRITICAL();
    return offset + rx_data_len;
  }
  else
  {
    return -EAGAIN;
  }
}
static void check(unsigned payload_size,unsigned room,bool empty){
 struct modem m={0};uint8_t collected[RX_BUF_SIZE+1]={0},out[260];
 struct modem_cmd_handler_data d={0};d.user_data=&m;d.rx_buf=collected;
 memset(out,0x5a,sizeof out);m.rx_data=out+1;m.rx_data_len=payload_size;
 reads=freed=ownership=wakes=fs_read_copied=0;
 unsigned prefix=(unsigned)sprintf((char*)packet,"+FS:READ,%u,",payload_size);
 if(!empty)for(unsigned i=0;i<payload_size;++i)packet[prefix+i]=(uint8_t)i;
 memcpy(packet+prefix+(empty?0:payload_size),"\r\nOK\r\n",6);
 packet_size=prefix+(empty?0:payload_size)+6;
 /* Force retained-packet copying through every destination room boundary. */
 unsigned copied=0;
 while(copied<packet_size){
  size_t n=0;assert(!modem_iface_spi_read(&m.iface,collected+copied,room,&n));
  assert(n && n<=room && !memcmp(collected+copied,packet+copied,n));copied+=(unsigned)n;
  assert(freed==(copied==packet_size));
 }
 d.rx_buf_len=copied;assert(reads==1 && freed==1 && !ownership && !m.spi_rx_pending);
 int r=on_cmd_fs_readfile(&d,9,NULL,0);
 if(empty){assert(r==-EIO && d.tx_desynchronized && !fs_read_copied);
  for(unsigned i=0;i<sizeof out;++i)assert(out[i]==0x5a);}
 else {assert(r==(int)(prefix+payload_size) && !d.tx_desynchronized);
  assert(out[0]==0x5a && out[payload_size+1]==0x5a);
  for(unsigned i=0;i<payload_size;++i)assert(out[1+i]==(uint8_t)i);}
 assert(!critical);
}
int main(void){
 for(unsigned room=1;room<=33;++room){check(1,room,false);check(6,room,false);
  check(256,room,false);check(1,room,true);}
 /* Actual collector publishes explicit byte count, including embedded NUL. */
 struct modem m={0};uint8_t collected[RX_BUF_SIZE+1]={0};
 m.iface.mdm_read=modem_iface_spi_read;
 struct modem_cmd_handler_data d={&m,collected,0,false,0};
 reads=freed=ownership=0;packet[0]='A';packet[1]=0;packet[2]='B';packet_size=3;
 assert(!cmd_handler_process_iface_data(&d,&m.iface));
 assert(d.rx_buf_len==3 && collected[0]=='A' && collected[1]==0 && collected[2]=='B' && freed==1);
 puts("PASS actual retained SPI copy and collector preserve embedded NUL and all256 byte values");
 puts("PASS33 room boundaries neither truncate nor release ownership early");
 puts("PASS exact FS payload copied; missing byte+OK rejected without fabricated NUL");
 
 struct modem guard={0};uint8_t out[8];size_t n=99;
 reads=freed=ownership=0;spi_fault=1;delay_count=0;memset(out,0xa5,sizeof out);
 assert(modem_iface_spi_read(&guard.iface,out,8,&n)==-EIO && !n && !reads && !freed && guard.handler_data.tx_desynchronized && delay_count==1);
 spi_fault=0;guard.handler_data.tx_desynchronized=false;packet_size=8;memset(packet,0x45,8);
 assert(!modem_iface_spi_read(&guard.iface,out,2,&n) && n==2 && ownership && !freed);
 unsigned offset=(unsigned)guard.spi_rx_pending_offset;spi_fault=1;n=99;memset(out,0xa5,sizeof out);
 assert(modem_iface_spi_read(&guard.iface,out,8,&n)==-EIO && !n && guard.spi_rx_pending_offset==offset && !freed && ownership && out[0]==0xa5);
 BusIo_SPI_Free(guard.spi_rx_pending);guard.spi_rx_pending=NULL;
 puts("PASS sticky fault blocks new packet read and retained parser tail without early free");
 memset(&guard,0,sizeof guard);reads=freed=ownership=0;spi_fault=0;fault_on_receive=1;n=99;memset(out,0xa5,sizeof out);
 assert(modem_iface_spi_read(&guard.iface,out,8,&n)==-EIO && !n && ownership && !freed && out[0]==0xa5 && guard.handler_data.tx_desynchronized);
 BusIo_SPI_Free(guard.spi_rx_pending);
 puts("PASS fault racing queued receive publishes zero bytes and retains ownership for teardown");

 puts("LIMIT hardware SPI queue/DMA and NCP file storage are not emulated");return 0;
}
