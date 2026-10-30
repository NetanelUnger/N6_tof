
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t TickType_t;
typedef int SemaphoreHandle_t;
struct modem_cmd { int unused; };
struct modem_iface { int32_t (*mdm_write)(struct modem_iface*,const uint8_t*,size_t); };
struct modem_cmd_handler_data {
 bool tx_desynchronized, raw_command_attempted; TickType_t tx_quiet_until; bool tx_quiet_active;
 bool dns_drain_active, dns_wait_active; TickType_t dns_drain_until;
 int last_error;
 int sem_tx_lock; const char *eol; size_t eol_len;
 void *budget_owner;void *user_data;
};
struct modem_cmd_handler { void *cmd_handler_data; };
static unsigned tick, critical, writes, installed, awaits, held, delays, lock_wait;
static unsigned extend_once, during_write;
static unsigned response_ready,mode,response_waits,late_injected;
static void inject_terminal(void);
struct modem {unsigned notify_phase;bool raw_tx_terminal_only,raw_tx_payload_started,notify_recv_seen,raw_tx_response_received;int sem_response,sem_tx_ready;void (*notify_wake)(void);};
static struct modem modem;
#define MODEM_CMD_DEFINE(n) static int32_t n(struct modem_cmd_handler_data *data,uint16_t len,char **argv,uint16_t argc)

static int bus_failure;
static TickType_t response_budget;
#define taskENTER_CRITICAL() (++critical)
#define taskEXIT_CRITICAL() (--critical)
#define pdTRUE 1
#define MODEM_NO_TX_LOCK 1U
#define MODEM_NO_SET_CMDS 2U
#define MODEM_NO_UNSET_CMDS 4U
#define MODEM_TX_ADMISSION_NOWAIT 8U
#define MODEM_TX_TRACK_RAW_WRITE 16U
#define pdMS_TO_TICKS(ms) ((ms)/10U)
#define portTICK_PERIOD_MS 10U
static struct modem_cmd_handler_data data;
static TickType_t xTaskGetTickCount(void) { return tick; }
static void *xTaskGetCurrentTaskHandle(void) { return (void*)1; }
static TickType_t modem_cmd_handler_budget(struct modem_cmd_handler_data *d,TickType_t n) { (void)d;return n; }
static void modem_cmd_handler_defer_tx(struct modem_cmd_handler_data*,TickType_t);
static void vTaskDelay(TickType_t n) {
 assert(!critical);++delays; tick+=n;
 if(extend_once) {extend_once=0;modem_cmd_handler_defer_tx(&data,5);}
}
static int xSemaphoreTake(int sem,TickType_t wait){
 if(sem==1){assert(!held);tick+=lock_wait;assert(lock_wait<=wait);held=1;return 1;}
 assert(sem==2);
 if(!wait){unsigned n=response_ready;response_ready=0;return n;}
 ++response_waits;
 if(mode==2 || mode==3 || (mode==1 && response_waits==2))inject_terminal();
 if(response_ready){response_ready=0;return 1;}
 tick+=wait;return 0;
}
static int xSemaphoreGive(int sem){if(sem==1){assert(held);held=0;}else{assert(sem==2);response_ready=1;}return 1;}
static int modem_cmd_handler_update_cmds(struct modem_cmd_handler_data *d,
 const struct modem_cmd *c,size_t n,bool reset) {
 (void)d;(void)c;(void)n;(void)reset;assert(held);++installed;return 0;
}

static int32_t write_bus(struct modem_iface *iface,const uint8_t *p,size_t n) {
 (void)iface;(void)p;assert(held && !critical);++writes;
 if(bus_failure==1) return -EBUSY;
 if(bus_failure==2) return (int32_t)n-1;
 if(during_write) modem_cmd_handler_defer_tx(&data,10);
 return (int32_t)n;
}
#define Debug_UART_Log(...) ((void)0)
int32_t modem_cmd_handler_get_error(struct modem_cmd_handler_data *data)
{
  if (data == NULL)
  {
    return -EINVAL;
  }

  return data->last_error;
}
int32_t modem_cmd_handler_set_error(struct modem_cmd_handler_data *data, int32_t error_code)
{
  if (data == NULL)
  {
    return -EINVAL;
  }

  data->last_error = error_code;
  return 0;
}
void modem_cmd_handler_defer_tx(struct modem_cmd_handler_data *data, TickType_t ticks)
{
  if (ticks == 0U)
  {
    return;
  }
  taskENTER_CRITICAL();
  data->tx_quiet_until = xTaskGetTickCount() + ticks;
  data->tx_quiet_active = true;
  taskEXIT_CRITICAL();
}
void modem_cmd_handler_dns_drain_complete(struct modem_cmd_handler_data *data)
{
  TickType_t elapsed;
  bool report, fenced;
  int32_t result;
  taskENTER_CRITICAL();
  TickType_t now = xTaskGetTickCount();
  report = data->dns_wait_active;
  elapsed = now - (data->dns_drain_until - pdMS_TO_TICKS(20000U));
  if (data->dns_drain_active)
  {
    /* A real fence is never cleared. After the vendor DNS deadline, even a
     * terminal record is too late to restore admission without reinit. */
    if ((int32_t)(now - data->dns_drain_until) >= 0)
      data->tx_desynchronized = true;
    data->dns_drain_active = false;
  }
  data->dns_wait_active = false;
  fenced = data->tx_desynchronized;
  result = data->last_error;
  taskEXIT_CRITICAL();
  /* Formatting/queue admission must stay outside interrupt exclusion. */
  if (report)
    Debug_UART_Log("RADIO-WAIT", "END reason=DNS_REPLY elapsed_ms=%lu result=%ld fenced=%u outcome=%s",
                   (unsigned long)elapsed * portTICK_PERIOD_MS, (long)result, (unsigned)fenced,
                   fenced ? "fenced" : ((result < 0) ? "failed" : "complete"));
}
int32_t modem_cmd_handler_wait_tx_ready(struct modem_cmd_handler_data *data,
                                       TickType_t budget, bool nonblocking)
{
  TickType_t started_at = xTaskGetTickCount();
  for (;;)
  {
    TickType_t now;
    TickType_t quiet_remaining = 0U;
    bool drain_expired = false;
    taskENTER_CRITICAL();
    now = xTaskGetTickCount();
    if (data->dns_drain_active &&
        ((int32_t)(now - data->dns_drain_until) >= 0))
    {
      data->dns_drain_active = false;
      data->tx_desynchronized = true;
      drain_expired = true;
    }
    bool draining = data->dns_drain_active;
    bool fenced = data->tx_desynchronized;
    /* Settling is short (100 ms), below half the tick counter range. */
    if (data->tx_quiet_active)
    {
      if ((int32_t)(now - data->tx_quiet_until) >= 0)
      {
        data->tx_quiet_active = false;
      }
      else
      {
        quiet_remaining = data->tx_quiet_until - now;
      }
    }
    taskEXIT_CRITICAL();
    if (drain_expired) modem_cmd_handler_dns_drain_complete(data);
    if (fenced) return -EIO;
    if (draining)
    {
      if (nonblocking) return -EBUSY;
      if ((now - started_at) >= budget) return -ETIMEDOUT;
      /* RX stays runnable; no handler replacement or command bytes while the
       * still-owned DNS reply is pending. Every waiter retains its own budget. */
      vTaskDelay(1U);
      continue;
    }
    if (quiet_remaining == 0U)
    {
      return 0;
    }
    if (nonblocking)
    {
      return -EBUSY;
    }
    TickType_t elapsed = now - started_at;
    if ((elapsed >= budget) || (quiet_remaining >= (budget - elapsed)))
    {
      /* No command has been announced, so an exhausted admission budget
       * cannot desynchronize AT. Do not spend it on a doomed transaction. */
      return -ETIMEDOUT;
    }
    vTaskDelay(quiet_remaining);
  }
}
int32_t modem_cmd_handler_await(struct modem_cmd_handler_data *data,
                                SemaphoreHandle_t sem, TickType_t timeout)
{
  int32_t ret = xSemaphoreTake(sem, timeout);

  if (ret == pdTRUE)
  {
    ret = modem_cmd_handler_get_error(data);
  }
  else
  {
    ret = -ETIMEDOUT;
  }

  return ret;
}
int32_t modem_cmd_send_ext(struct modem_iface *iface,
                           struct modem_cmd_handler *handler,
                           const struct modem_cmd *handler_cmds,
                           size_t handler_cmds_len, const uint8_t *buf,
                           SemaphoreHandle_t sem, TickType_t timeout, uint32_t flags)
{
  struct modem_cmd_handler_data *data;
  int32_t ret = 0;
  TickType_t started_at;
  TickType_t remaining;
  TickType_t lock_acquired_at = 0U;
  TickType_t lock_held_ticks = 0U;
  bool tx_lock_acquired = false;
  bool trace_scan = false;
  TickType_t written_at = 0U;

  if ((iface == NULL) || (iface->mdm_write == NULL) ||
      (handler == NULL) || (handler->cmd_handler_data == NULL) ||
      (buf == NULL))
  {
    return -EINVAL;
  }

  if (timeout == 0U)
  {
    /* Semaphore is not needed if there is no timeout */
    sem = NULL;
  }
  else
  {
    if (sem == NULL)
    {
      /* Cannot respect timeout without semaphore */
      return -EINVAL;
    }
  }

  data = (struct modem_cmd_handler_data *)(handler->cmd_handler_data);
  if (timeout != 0U)
  {
    timeout = modem_cmd_handler_budget(data, timeout);
    if (timeout == 0U) return -ETIMEDOUT; /* Expired is never fire-and-forget. */
  }
  started_at = xTaskGetTickCount();
  /* Record only the scan opcode, never AT arguments or credential payloads.
   * This separates command ownership from waiting for another AT owner. */
  trace_scan = ((flags & MODEM_NO_TX_LOCK) == 0U) &&
               (strncmp((const char *)buf, "AT+CWLAP=", 9U) == 0);
  if ((flags & MODEM_NO_TX_LOCK) == 0U)
  {
    if (xSemaphoreTake(data->sem_tx_lock, timeout) != pdTRUE)
    {
      return -ETIMEDOUT;
    }
    tx_lock_acquired = true;
    lock_acquired_at = xTaskGetTickCount();
  }

  if (data->tx_desynchronized)
  {
    ret = -EIO;
    goto unlock_tx_lock;
  }

  /* Keep association settling out of the RX parser and inside this operation's
   * original budget. Guard before installing handlers or writing any AT text. */
  TickType_t admission_elapsed = xTaskGetTickCount() - started_at;
  remaining = (admission_elapsed >= timeout) ? 0U : timeout - admission_elapsed;
  ret = modem_cmd_handler_wait_tx_ready(data, remaining,
                                        (timeout == 0U) || ((flags & MODEM_TX_ADMISSION_NOWAIT) != 0U));
  if (ret < 0)
  {
    goto unlock_tx_lock;
  }
  if ((timeout != 0U) && ((xTaskGetTickCount() - started_at) >= timeout))
  {
    ret = -ETIMEDOUT;
    goto unlock_tx_lock;
  }
  if ((timeout != 0U) && (modem_cmd_handler_budget(data, remaining) == 0U))
  {
    ret = -ETIMEDOUT;
    goto unlock_tx_lock; /* Epoch may have changed while waiting for AT. */
  }

  if ((flags & MODEM_NO_SET_CMDS) == 0U)
  {
    ret = modem_cmd_handler_update_cmds(data, handler_cmds,
                                        handler_cmds_len, true);
    if (ret < 0)
    {
      goto unlock_tx_lock;
    }
  }

#if defined(CONFIG_MODEM_CONTEXT_VERBOSE_DEBUG)
  LOG_HEXDUMP_DBG(buf, strlen(buf), "SENT DATA");

  if (data->eol_len > 0)
  {
    if (data->eol[0] != '\r')
    {
      LOG_HEXDUMP_DBG(data->eol, data->eol_len, "SENT EOL");
    }
  }
  else
  {
    LOG_DBG("EOL not set!!!");
  }
#endif /* CONFIG_MODEM_CONTEXT_VERBOSE_DEBUG */
  if (sem != NULL)
  {
    (void)xSemaphoreTake(sem, 0); /* Reset semaphore (binary) */
  }

  size_t command_len = strlen((char *)buf);
  written_at = xTaskGetTickCount();
  bool trace_dns = (sem != NULL) && ((flags & MODEM_NO_UNSET_CMDS) == 0U) &&
                   (strncmp((const char *)buf, "AT+CIPDOMAIN=", 13U) == 0);
  if (trace_dns)
  {
    /* Report START before publishing the state and before any command bytes:
     * even an immediate terminal callback cannot print END ahead of START.
     * Reuse the existing DNS deadline for elapsed timing; no new timer/task. */
    /* The UART prefix already supplies HAL uptime; RTOS ticks are used only
     * for durations because their epoch starts at scheduler entry. */
    Debug_UART_Log("RADIO-WAIT", "START reason=DNS_REPLY limit_ms=20000");
    taskENTER_CRITICAL();
    data->dns_drain_until = written_at + pdMS_TO_TICKS(20000U);
    data->dns_wait_active = true;
    taskEXIT_CRITICAL();
  }
  if ((flags & MODEM_TX_TRACK_RAW_WRITE) != 0U) data->raw_command_attempted = true;
  int32_t command_written = iface->mdm_write(iface, buf, command_len);
  if (command_written == -EBUSY)
  {
    ret = -EBUSY; /* Explicit bus guarantee: no command bytes were queued. */
    if ((flags & MODEM_TX_TRACK_RAW_WRITE) != 0U) data->raw_command_attempted = false;
  }
  else if (command_written != (int32_t)command_len)
  {
    data->tx_desynchronized = true;
    ret = -EIO;
  }
  else if ((data->eol_len > 0U) &&
           (iface->mdm_write(iface, (uint8_t const *)data->eol,
                             data->eol_len) != (int32_t)data->eol_len))
  {
    data->tx_desynchronized = true;
    ret = -EIO;
  }

  if ((ret == 0) && (sem != NULL))
  {
    /* The TX-lock wait and command write consume the same operation budget
     * as the modem response. Unsigned tick subtraction also handles wrap. */
    TickType_t elapsed = xTaskGetTickCount() - started_at;
    remaining = (elapsed >= timeout) ? 0U : (timeout - elapsed);
    ret = modem_cmd_handler_await(data, sem, remaining);
    /* A scoped timeout has no terminal boundary; a late OK must not satisfy
     * a new operation. Only module reinitialization clears this real fence. */
    if ((ret == -ETIMEDOUT) && (data->budget_owner == xTaskGetCurrentTaskHandle()))
    {
      if (((flags & MODEM_NO_UNSET_CMDS) == 0U) &&
          (strncmp((const char *)buf, "AT+CIPDOMAIN=", 13U) == 0))
      {
        /* Only ordinary DNS can finish beyond the application request budget.
         * Detach its per-call query handlers below; persistent OK/ERROR own
         * the terminal drain. No payload is resent and no caller pointer is
         * retained. SDK DNS is bounded by 20s from command submission. */
        taskENTER_CRITICAL();
        data->dns_drain_until = written_at + pdMS_TO_TICKS(20000U);
        data->dns_drain_active = true;
        taskEXIT_CRITICAL();
        /* Close the timeout/terminal race: the parser may have signalled just
         * before drain publication. Keep timeout as the request's result. */
        if (xSemaphoreTake(sem, 0U) == pdTRUE)
          modem_cmd_handler_dns_drain_complete(data);
        taskENTER_CRITICAL();
        bool pending = data->dns_drain_active;
        TickType_t pending_elapsed = xTaskGetTickCount() - written_at;
        taskEXIT_CRITICAL();
        /* Preserve the timeout notice. RX can finish before this thread queues
         * it, so describe the captured timeout state, not current ownership.
         * Never serialize diagnostic formatting by blocking the RX parser. */
        if (pending)
          Debug_UART_Log("RADIO-WAIT", "PENDING reason=DNS_REPLY elapsed_ms=%lu snapshot=request_timeout; terminal ownership was retained",
                         (unsigned long)pending_elapsed * portTICK_PERIOD_MS);
      }
      else data->tx_desynchronized = true;
    }
  }

  if (trace_dns && (ret < 0) && !data->dns_drain_active)
  {
    /* A failed bus admission may have no parser terminal. Retire its report
     * here exactly once; do not mutate the protocol error or clear a fence. */
    taskENTER_CRITICAL();
    bool report = data->dns_wait_active;
    data->dns_wait_active = false;
    bool fenced = data->tx_desynchronized;
    taskEXIT_CRITICAL();
    if (report)
      Debug_UART_Log("RADIO-WAIT", "END reason=DNS_REPLY elapsed_ms=%lu result=%ld fenced=%u outcome=%s",
                     (unsigned long)(xTaskGetTickCount() - written_at) * portTICK_PERIOD_MS,
                     (long)ret, (unsigned)fenced, fenced ? "fenced" : "failed");
  }

  if ((flags & MODEM_NO_UNSET_CMDS) == 0U)
  {
    (void)modem_cmd_handler_update_cmds(data, NULL, 0U, false);
  }

unlock_tx_lock:
  if (tx_lock_acquired)
  {
    lock_held_ticks = xTaskGetTickCount() - lock_acquired_at;
    (void)xSemaphoreGive(data->sem_tx_lock);
  }
  if (trace_scan)
  {
    Debug_UART_Log("ST67", "Wi-Fi scan AT completed: wait_ticks=%lu held_ticks=%lu result=%ld",
                   (unsigned long)(lock_acquired_at - started_at),
                   (unsigned long)lock_held_ticks, (long)ret);
  }

  return ret;
}MODEM_CMD_DEFINE(on_cmd_ok)
{
  struct modem *mdm = (struct modem *) data->user_data;

  if (mdm->notify_phase != 0U) return 0; /* Only correlated Recv + SEND OK completes this SDK flow. */

  if (mdm->raw_tx_terminal_only && (!mdm->raw_tx_payload_started ||
      ((mdm->notify_phase != 0U) && !mdm->notify_recv_seen)))
  {
    /* Firmware may acknowledge BLEGATTSNTFY with OK before its raw prompt.
     * That acknowledgement neither ends raw ownership nor wakes the sender. */
    return 0;
  }
  if (!mdm->raw_tx_terminal_only)
  {
    (void)modem_cmd_handler_set_error(data, 0);
  }

  mdm->raw_tx_response_received = true;
  (void)xSemaphoreGive(mdm->sem_response);
  modem_cmd_handler_dns_drain_complete(data);
  return 0;
}MODEM_CMD_DEFINE(on_cmd_error)
{
  struct modem *mdm = (struct modem *) data->user_data;

  (void)modem_cmd_handler_set_error(data, -EIO);

  mdm->raw_tx_response_received = true;
  (void)xSemaphoreGive(mdm->sem_response);
  if (mdm->raw_tx_terminal_only)
  {
    (void)xSemaphoreGive(mdm->sem_tx_ready);
  }
  if ((mdm->notify_phase != 0U) && (mdm->notify_wake != NULL)) mdm->notify_wake();
  modem_cmd_handler_dns_drain_complete(data);

  return 0;
}
static void inject_terminal(void){
 ++late_injected;
 if(mode==3)on_cmd_error(&data,5,NULL,0);else on_cmd_ok(&data,2,NULL,0);
}
static void reset(void){
 memset(&data,0,sizeof data);memset(&modem,0,sizeof modem);data.sem_tx_lock=1;data.eol="";
 data.user_data=&modem;modem.sem_response=2;modem.sem_tx_ready=2;
 tick=critical=writes=installed=awaits=held=delays=lock_wait=extend_once=during_write=0;
 response_ready=mode=response_waits=late_injected=bus_failure=0;
}
static int command(const char *text,unsigned budget,unsigned flags){
 struct modem_iface iface={write_bus};struct modem_cmd_handler handler={&data};
 return modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)text,2,budget,flags);
}
int main(void){
 reset();mode=1;
 assert(command("AT+CWJAPS=\"TEST-NOT-SENT-TO-HARDWARE\"",300,0)==-ETIMEDOUT && writes==1 && !held);
 int second=command("AT+CWSTATE?",300,0);
 printf("OBSERVED first timeout; second_result=%d writes=%u late_old_terminal_injected=%u fence=%u\n",second,writes,late_injected,data.tx_desynchronized);fflush(stdout);
 assert(second==-EIO && writes==1 && !late_injected && data.tx_desynchronized);
 puts("PASS missing unscoped connect terminal fences before next query; old OK cannot complete replacement");
 inject_terminal();assert(data.tx_desynchronized && response_ready);
 assert(command("AT",20,0)==-EIO && writes==1 && data.tx_desynchronized);
 puts("PASS late or duplicate OK cannot clear an established fence or admit a later command");
 reset();assert(command("AT+CIPDOMAIN=example.invalid",2000,0)==-ETIMEDOUT);
 assert(data.tx_desynchronized && !data.dns_drain_active && tick==2000);
 puts("PASS unscoped DNS at its full vendor deadline cannot gain an extra drain window");
 reset();modem_cmd_handler_defer_tx(&data,10);
 assert(command("AT",10,0)==-ETIMEDOUT && !writes && !data.tx_desynchronized && !held);
 puts("PASS exhausted admission before bytes is a local timeout without protocol fence");
 reset();mode=2;assert(!command("AT",20,0) && writes==1 && !data.tx_desynchronized && !held);
 reset();mode=3;assert(command("AT",20,0)==-EIO && writes==1 && !data.tx_desynchronized && !held);
 puts("PASS actual OK/ERROR terminal callbacks complete once without declaring desynchronization");
 reset();held=1;assert(command("AT",20,MODEM_NO_TX_LOCK)==-ETIMEDOUT && held && data.tx_desynchronized);
 held=0;puts("PASS caller-owned mutex stays owned while missing terminal closes new protocol admission");
 reset();bus_failure=1;assert(command("AT",20,0)==-EBUSY && !data.tx_desynchronized && !held);
 reset();bus_failure=2;assert(command("AT",20,0)==-EIO && data.tx_desynchronized && !held);
 puts("PASS zero-byte BUSY remains retryable; partial submission remains ambiguous");
 reset();assert(!command("AT",0,0) && writes==1 && !response_waits);
 puts("PASS existing explicit fire-and-forget API remains distinct from a timed request");
 return 0;
}
