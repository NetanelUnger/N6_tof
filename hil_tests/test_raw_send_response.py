"""Execute the actual raw-send path with replies injected at wire boundaries.

This verifies command/prompt/payload ownership, including a terminal ERROR
received before command submission returns. Hardware and ThreadX are mocked.
"""
import re
from test_wifi_scan_lifetime import ROOT, run_native
from test_wifi_assoc_admission import extract_function as function

PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t TickType_t;
typedef uint32_t W61_Status_t;
enum { W61_STATUS_OK, W61_STATUS_BUSY, W61_STATUS_TIMEOUT, W61_STATUS_IO_ERROR };
enum { NORMAL, EARLY_ERROR, WAIT_ERROR, NO_PROMPT, NO_TERMINAL, ZERO_WRITE, EARLY_OK, OK_NO_PROMPT, OK_NO_TERMINAL, OBSERVED, BAD_RECV, SEND_FAIL };
struct modem_cmd_handler_data { void *user_data; int sem_tx_lock, last_error;
 bool tx_desynchronized, raw_command_attempted; TickType_t tx_quiet_until; bool tx_quiet_active;
 bool dns_drain_active, dns_wait_active; TickType_t dns_drain_until; };
struct modem { struct modem_cmd_handler_data handler_data; int iface,handler;
 int sem_tx_ready,sem_response; uint32_t rx_data_len;
 bool raw_tx_terminal_only,raw_tx_response_received,raw_tx_payload_started;
 unsigned notify_phase; bool notify_recv_seen; void (*notify_wake)(void); };
typedef struct { struct modem Modem; } W61_Object_t;
struct modem_cmd { const char *cmd; int32_t (*func)(struct modem_cmd_handler_data*,uint16_t,char**,uint16_t); };
#define MODEM_CMD_DEFINE(name) static int32_t name(struct modem_cmd_handler_data *data, uint16_t len, char **argv, uint16_t argc)
#define MODEM_CMD_DIRECT_DEFINE(name) MODEM_CMD_DEFINE(name)
#define MODEM_CMD_DIRECT(c,f) {c,f}
#define MODEM_CMD(c,f,n,d) {c,f}
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define MODEM_NO_TX_LOCK 1U
#define MODEM_NO_UNSET_CMDS 2U
#define MODEM_TX_ADMISSION_NOWAIT 8U
#define MODEM_TX_TRACK_RAW_WRITE 16U
#define pdMS_TO_TICKS(ms) ((ms)/10U)
#define portTICK_PERIOD_MS 10U
#define pdPASS 1
#define SYS_LOG_DEBUG(...) ((void)0)
static W61_Object_t obj;
static unsigned tick, tx_owned, prompt_count, response_count, commands, payloads;
static unsigned scenario, busy, initial_ok, fences, releases, quiet_race, critical, cancel_before_write;
static void Debug_UART_Log(const char *tag,const char *fmt,...);
static const struct modem_cmd *active_cmds;
static size_t active_count;
MODEM_CMD_DEFINE(on_cmd_ok);
MODEM_CMD_DEFINE(on_cmd_error);
MODEM_CMD_DEFINE(on_cmd_recv);
MODEM_CMD_DIRECT_DEFINE(on_cmd_tx_ready);
static TickType_t xTaskGetTickCount(void) { return tick; }
static TickType_t modem_cmd_handler_budget(struct modem_cmd_handler_data *d,TickType_t n) { (void)d;return n; }
static void vTaskDelay(TickType_t n) { assert(!critical);tick+=n; }
#define taskENTER_CRITICAL() (++critical)
#define taskEXIT_CRITICAL() (--critical)
/* INSERT_REAL_ADMISSION */
static int modem_cmd_handler_set_error(struct modem_cmd_handler_data *data,int e) { data->last_error=e;return 0; }
static int modem_cmd_handler_get_error(struct modem_cmd_handler_data *data) { return data->last_error; }
static int xSemaphoreGive(int sem) {
 if(sem==1) { assert(tx_owned); tx_owned=0; ++releases; }
 else if(sem==2) prompt_count=1;
 else { assert(sem==3);response_count=1; }
 return 1;
}
static int xSemaphoreTake(int sem,TickType_t wait) {
 if(sem==1) { if(busy) {tick+=wait;return 0;} assert(!tx_owned);tx_owned=1;return 1; }
 unsigned *count=sem==2 ? &prompt_count : &response_count;
 if(wait && !*count && sem==2) {
   if(scenario==WAIT_ERROR) on_cmd_error(&obj.Modem.handler_data,0,NULL,0);
   else if(scenario!=EARLY_ERROR && scenario!=NO_PROMPT && scenario!=OK_NO_PROMPT)
     on_cmd_tx_ready(&obj.Modem.handler_data,1,NULL,0);
 }
 if(*count) { *count=0;return 1; }
 tick+=wait;return 0;
}
static int modem_cmd_send_ext(int *iface,int *handler,const struct modem_cmd *cmds,
 size_t n,const uint8_t *cmd,int sem,TickType_t wait,unsigned flags) {
 (void)iface;(void)handler;(void)cmd;(void)sem;
 if(quiet_race) modem_cmd_handler_defer_tx(&obj.Modem.handler_data,10);
 int admission=modem_cmd_handler_wait_tx_ready(&obj.Modem.handler_data,wait,true);
 if(admission) return admission;
 if(cancel_before_write) return -ETIMEDOUT;
 if(flags & MODEM_TX_TRACK_RAW_WRITE) obj.Modem.handler_data.raw_command_attempted=true;
 active_cmds=cmds;active_count=n;
 assert(n==(wait ? 2U : 4U));
 obj.Modem.handler_data.last_error=0;
 unsigned base_flags=MODEM_NO_TX_LOCK|MODEM_NO_UNSET_CMDS|MODEM_TX_ADMISSION_NOWAIT;
 assert(tx_owned && (flags==base_flags || flags==(base_flags|MODEM_TX_TRACK_RAW_WRITE)));++commands;
 if(scenario==EARLY_ERROR) on_cmd_error(&obj.Modem.handler_data,0,NULL,0);
 else if(scenario==EARLY_OK || scenario==OK_NO_PROMPT || scenario==OK_NO_TERMINAL ||
         scenario==OBSERVED || scenario==BAD_RECV || scenario==SEND_FAIL || initial_ok)
   on_cmd_ok(&obj.Modem.handler_data,0,NULL,0);
 if(wait) { assert(response_count);response_count=0;return obj.Modem.handler_data.last_error; }
 return 0;
}
static int modem_cmd_send_data_nolock(int *iface,const uint8_t *data,int size) {
 (void)iface;(void)data;assert(tx_owned);++payloads;
 if(scenario==ZERO_WRITE) return 0;
 if(scenario!=NO_TERMINAL && scenario!=OK_NO_TERMINAL) {
   if(scenario==OBSERVED || scenario==BAD_RECV || scenario==SEND_FAIL) {
     char amount[12];snprintf(amount,sizeof amount,"%d",scenario==BAD_RECV ? size-1 : size);
     char *argv[]={amount};on_cmd_recv(&obj.Modem.handler_data,0,argv,1);
     assert(!response_count); /* Recv is not BLE's terminal boundary. */
     const char *terminal=scenario==SEND_FAIL ? "SEND FAIL" : "SEND OK";
     bool matched=false;
     for(size_t i=0;i<active_count;++i) if(!strcmp(active_cmds[i].cmd,terminal)) {
       active_cmds[i].func(&obj.Modem.handler_data,0,NULL,0);matched=true;break;
     }
     assert(matched);
   }
   else if(obj.Modem.raw_tx_terminal_only) on_cmd_ok(&obj.Modem.handler_data,0,NULL,0);
   else { char amount[12];snprintf(amount,sizeof amount,"%d",size);char *argv[]={amount};
     on_cmd_recv(&obj.Modem.handler_data,0,argv,1); }
 }
 return size;
}
static int modem_cmd_handler_update_cmds(struct modem_cmd_handler_data *d,const void *c,size_t n,bool reset) {
 (void)d;(void)c;(void)n;(void)reset;return 0;
}
static W61_Status_t W61_Status(int ret) {
 return !ret ? W61_STATUS_OK : ret==-EBUSY ? W61_STATUS_BUSY : ret==-ETIMEDOUT ? W61_STATUS_TIMEOUT : W61_STATUS_IO_ERROR;
}
static void Debug_UART_Log(const char *tag,const char *fmt,...) { (void)tag;(void)fmt;++fences; }
'''
TESTS = r'''
static void reset(unsigned mode) {
 memset(&obj,0,sizeof obj);obj.Modem.handler_data.user_data=&obj.Modem;
 obj.Modem.handler_data.sem_tx_lock=1;obj.Modem.sem_tx_ready=2;obj.Modem.sem_response=3;
 tick=tx_owned=prompt_count=response_count=commands=payloads=busy=initial_ok=fences=releases=0;
 quiet_race=critical=cancel_before_write=0;
 scenario=mode;
}
static W61_Status_t send(bool check,bool try_lock) {
 uint8_t command[]="AT+BLEGATTSNTFY=1,2,244,0\r\n", bytes[244]={0};
 return request_send_data(&obj,command,bytes,sizeof bytes,100,check,try_lock);
}
int main(void) {
 reset(EARLY_ERROR);assert(send(false,true)==W61_STATUS_IO_ERROR);
 assert(commands==1 && !payloads && !fences && !tx_owned && releases==1);
 assert(!obj.Modem.handler_data.tx_desynchronized);
 puts("PASS ERROR before command return survives; no payload and no false fence");
 reset(WAIT_ERROR);assert(send(false,true)==W61_STATUS_IO_ERROR);
 assert(!payloads && !fences && tick==0 && !tx_owned);
 puts("PASS ERROR during prompt wait wakes sender and closes rejected transaction");
 reset(NORMAL);assert(send(false,true)==W61_STATUS_OK);
 assert(payloads==1 && !fences && !tx_owned);
 puts("PASS prompt/payload/terminal OK preserves raw ownership");
 reset(NO_PROMPT);assert(send(false,true)==W61_STATUS_TIMEOUT);
 assert(tick==10 && !payloads && fences==1 && !tx_owned);
 assert(obj.Modem.handler_data.tx_desynchronized);
 puts("PASS genuinely missing prompt retains deadline and protective fence");
 reset(NO_TERMINAL);assert(send(false,true)==W61_STATUS_TIMEOUT);
 assert(payloads==1 && fences==1 && tick==10 && !tx_owned);
 puts("PASS missing payload terminal response still fences AT");
 reset(ZERO_WRITE);assert(send(false,true)==W61_STATUS_IO_ERROR);
 assert(payloads==1 && fences==1 && !tx_owned);
 puts("PASS short/zero payload submission still fences raw ownership");
 reset(NORMAL);busy=1;assert(send(false,true)==W61_STATUS_BUSY);
 assert(!commands && !payloads && !fences && !tick);
 puts("PASS busy admission remains immediate without announcing raw mode");
 reset(NORMAL);obj.Modem.handler_data.tx_desynchronized=true;
 assert(send(false,true)==W61_STATUS_IO_ERROR);assert(!commands && !payloads && !tx_owned);
 puts("PASS an existing raw fence is never cleared by retry");
 reset(NORMAL);initial_ok=1;assert(send(true,false)==W61_STATUS_OK);
 assert(payloads==1 && !fences && !tx_owned);
 puts("PASS command-OK flow resets only the consumed command acknowledgement");
 reset(NO_TERMINAL);initial_ok=1;assert(send(true,false)==W61_STATUS_TIMEOUT);
 assert(payloads==1 && fences==1 && obj.Modem.handler_data.tx_desynchronized);
 puts("PASS initial command OK cannot mask a missing payload terminal response");
 reset(EARLY_OK);assert(send(false,true)==W61_STATUS_OK);
 assert(payloads==1 && !fences && !tx_owned);
 puts("PASS observed BLE command OK then prompt then payload OK completes");
 reset(OK_NO_PROMPT);assert(send(false,true)==W61_STATUS_TIMEOUT);
 assert(!payloads && fences==1 && obj.Modem.handler_data.tx_desynchronized);
 puts("PASS initial BLE OK without prompt cannot release raw ownership");
 reset(OK_NO_TERMINAL);assert(send(false,true)==W61_STATUS_TIMEOUT);
 assert(payloads==1 && fences==1 && obj.Modem.handler_data.tx_desynchronized);
 puts("PASS initial BLE OK cannot mask missing payload acknowledgement");
 reset(OBSERVED);assert(send(false,true)==W61_STATUS_OK);
 assert(payloads==1 && !fences && !tx_owned);
 puts("PASS actual handler table accepts observed OK/prompt/Recv/SEND OK sequence");
 reset(BAD_RECV);assert(send(false,true)==W61_STATUS_IO_ERROR);
 assert(payloads==1 && !fences && !tx_owned);
 puts("PASS SEND OK cannot overwrite a mismatched Recv length");
 reset(SEND_FAIL);assert(send(false,true)==W61_STATUS_IO_ERROR);
 assert(payloads==1 && !fences && !tx_owned);
 puts("PASS SEND FAIL closes rejected payload without a false missing-response fence");
 reset(NORMAL);modem_cmd_handler_defer_tx(&obj.Modem.handler_data,10);
 assert(send(false,true)==W61_STATUS_BUSY);
 assert(!commands && !payloads && !fences && !tick && !tx_owned);
 puts("PASS association settling defers BLE immediately without announcing or fencing");
 reset(NORMAL);modem_cmd_handler_defer_tx(&obj.Modem.handler_data,10);
 assert(send(false,false)==W61_STATUS_TIMEOUT);
 assert(!commands && !payloads && !fences && !tick && !tx_owned);
 puts("PASS exhausted blocking admission cannot announce a doomed raw transfer");
 reset(NORMAL);modem_cmd_handler_defer_tx(&obj.Modem.handler_data,4);
 assert(send(false,false)==W61_STATUS_OK);
 assert(tick==4 && payloads==1 && !fences && !tx_owned);
 puts("PASS blocking settling uses original raw deadline then completes normally");
 reset(NORMAL);quiet_race=1;assert(send(false,true)==W61_STATUS_BUSY);
 assert(!commands && !payloads && !fences && !tx_owned);
 puts("PASS association racing the raw precheck returns BUSY with zero command bytes");
 reset(NORMAL);cancel_before_write=1;initial_ok=1;
 obj.Modem.handler_data.raw_command_attempted=true; /* Prior owner's outcome is not ours. */
 assert(send(true,false)==W61_STATUS_TIMEOUT);
 assert(!commands && !payloads && !fences && !tx_owned && !obj.Modem.handler_data.tx_desynchronized);
 puts("PASS stale Cloud epoch cancelled before CIPSEND cannot falsely fence shared AT");
 return 0;
}
'''


def extract(source, name, macro=False):
    pattern = (r'^MODEM_CMD(?:_DIRECT)?_DEFINE\(' + re.escape(name) + r'\)\s*\{'
               if macro else r'^static W61_Status_t\s+' + re.escape(name) + r'\([^;]*?\)\s*\{')
    match = re.search(pattern, source, re.M)
    assert match, name
    end = source.index('{', match.start()) + 1
    level = 1
    while level:
        level += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]


def main():
    source = (ROOT / 'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c').read_text(encoding='utf-8')
    callbacks = ''.join(extract(source, name, True) for name in
                        ['on_cmd_tx_ready', 'on_cmd_recv', 'on_cmd_ok', 'on_cmd_error'])
    admission = (ROOT / 'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c').read_text(encoding='utf-8')
    helpers = ''.join(function(admission, name) for name in
                      ['modem_cmd_handler_defer_tx', 'modem_cmd_handler_dns_drain_complete', 'modem_cmd_handler_wait_tx_ready'])
    run_native(PREFIX.replace('/* INSERT_REAL_ADMISSION */', helpers) + callbacks + extract(source, 'request_send_data') + TESTS)


if __name__ == '__main__':
    main()
