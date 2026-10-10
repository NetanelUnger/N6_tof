"""Execute production Begin/Poll/Cancel with adversarial protocol boundaries.

The same bus/semaphore mocks as the synchronous regression are used; replies
are injected separately from Radio cycles. No hardware timing claim is made.
"""
from test_raw_send_response import PREFIX, extract
from test_wifi_scan_lifetime import ROOT, run_native
from test_wifi_assoc_admission import extract_function

TESTS = r'''
static uint8_t payload[244];
static unsigned sent;
static void reset(unsigned mode) {
 memset(&obj,0,sizeof obj);obj.Modem.handler_data.user_data=&obj.Modem;
 obj.Modem.handler_data.sem_tx_lock=1;obj.Modem.handler_data.sem_parse_lock=4;
 obj.Modem.sem_tx_ready=2;obj.Modem.sem_response=3;
 tick=tx_owned=prompt_count=response_count=commands=payloads=busy=initial_ok=fences=releases=0;
 quiet_race=critical=parse_depth=parse_busy=0; task=1;scenario=mode;
 wait_starts=wait_ends=0;wait_last[0]=0;
}
static W61_Status_t begin(void) {
 uint8_t command[]="AT+BLEGATTSNTFY=0,1,244,0\r\n";
 return W61_AT_Common_NotifyBegin(&obj,command,244,100);
}
static W61_Status_t poll(void) { return W61_AT_Common_NotifyPoll(&obj,payload,244,&sent); }
static void prompt(void) { on_cmd_tx_ready(&obj.Modem.handler_data,1,NULL,0); }
static void terminal(bool valid) {
 char *args[]={valid ? "244" : "243"};on_cmd_recv(&obj.Modem.handler_data,0,args,1);
 on_notify_terminal_ok(&obj.Modem.handler_data,0,NULL,0);
}
int main(void) {
 reset(NO_TERMINAL);assert(begin()==W61_STATUS_OK && tx_owned && !tick);
 assert(poll()==W61_STATUS_BUSY && !payloads && !sent && !tick);
 assert(begin()==W61_STATUS_BUSY && commands==1);
 puts("PASS single admitted transaction; polling never waits or recursively acquires TX");
 prompt();assert(poll()==W61_STATUS_BUSY && payloads==1 && tx_owned);
 tick=10;assert(poll()==W61_STATUS_BUSY && !obj.Modem.handler_data.tx_desynchronized);
 assert(wait_starts==1 && !wait_ends);
 tick=12;assert(poll()==W61_STATUS_BUSY && wait_starts==1);
 tick=14;terminal(true);parse_busy=1;
 assert(poll()==W61_STATUS_BUSY && wait_ends==1);parse_busy=0;
 assert(poll()==W61_STATUS_OK && sent==244 && !tx_owned && releases==1);
 assert(wait_starts==1 && wait_ends==1 && strstr(wait_last,"elapsed_ms=140 result=0 fenced=0"));
 assert(poll()==W61_STATUS_ERROR && !sent && payloads==1);
 puts("PASS late terminal retires the same owned payload exactly once without retransmission");
 reset(NO_TERMINAL);assert(begin()==W61_STATUS_OK);prompt();assert(poll()==W61_STATUS_BUSY);
 char *args[]={"244"};on_cmd_recv(&obj.Modem.handler_data,0,args,1);
 on_cmd_ok(&obj.Modem.handler_data,0,NULL,0);
 assert(poll()==W61_STATUS_BUSY && tx_owned && !sent);
 on_notify_terminal_ok(&obj.Modem.handler_data,0,NULL,0);
 assert(poll()==W61_STATUS_OK && sent==244);
 puts("PASS generic OK and Recv alone cannot complete an asynchronous notification");
 reset(NO_TERMINAL);assert(begin()==W61_STATUS_OK);tick=10;
 assert(poll()==W61_STATUS_TIMEOUT && !payloads && obj.Modem.handler_data.tx_desynchronized);
 assert(begin()==W61_STATUS_IO_ERROR && commands==1);
 puts("PASS absent prompt fences at original 100ms execution deadline");
 reset(NO_TERMINAL);assert(begin()==W61_STATUS_OK);prompt();assert(poll()==W61_STATUS_BUSY);
 tick=110;assert(poll()==W61_STATUS_TIMEOUT && !sent && obj.Modem.handler_data.tx_desynchronized);
 assert(wait_starts==1 && wait_ends==1 && strstr(wait_last,"fenced=1"));
 terminal(true);assert(begin()==W61_STATUS_IO_ERROR && obj.Modem.handler_data.tx_desynchronized);
 puts("PASS missing terminal has a bounded drain; late unsolicited response never clears the fence");
 reset(NO_TERMINAL);assert(begin()==W61_STATUS_OK);prompt();assert(poll()==W61_STATUS_BUSY);
 assert(W61_AT_Common_NotifyCancel(&obj)==W61_STATUS_BUSY && tx_owned);
 terminal(true);assert(W61_AT_Common_NotifyPoll(&obj,NULL,0,&sent)==W61_STATUS_OK && !sent);
 assert(!tx_owned && payloads==1);
 puts("PASS cancelled generation drains without retaining a pointer or delivering stale completion");
 reset(NO_TERMINAL);assert(begin()==W61_STATUS_OK);
 assert(W61_AT_Common_NotifyCancel(&obj)==W61_STATUS_IO_ERROR && obj.Modem.handler_data.tx_desynchronized);
 assert(!payloads && !tx_owned);
 puts("PASS cancelled partial raw transfer cannot send data from a new session");
 reset(NO_TERMINAL);assert(begin()==W61_STATUS_OK);prompt();assert(poll()==W61_STATUS_BUSY);
 terminal(false);assert(poll()==W61_STATUS_IO_ERROR && !sent && !obj.Modem.handler_data.tx_desynchronized);
 puts("PASS terminal completion preserves mismatched Recv failure");
 reset(EARLY_ERROR);assert(begin()==W61_STATUS_OK);
 assert(poll()==W61_STATUS_IO_ERROR && !payloads && !obj.Modem.handler_data.tx_desynchronized);
 puts("PASS early terminal rejection retires safely before payload");
 reset(NO_TERMINAL);assert(begin()==W61_STATUS_OK);task=2;
 assert(poll()==W61_STATUS_ERROR && tx_owned && !payloads);
 assert(W61_AT_Common_NotifyCancel(&obj)==W61_STATUS_ERROR);task=1;
 prompt();assert(poll()==W61_STATUS_BUSY);terminal(true);parse_busy=1;
 assert(poll()==W61_STATUS_BUSY && tx_owned);parse_busy=0;
 assert(poll()==W61_STATUS_OK && sent==244 && !tx_owned && !parse_depth);
 puts("PASS task ownership and parser-busy retirement retain the exact transaction");
 reset(NO_TERMINAL);tick=UINT32_MAX-5;assert(begin()==W61_STATUS_OK);
 prompt();assert(poll()==W61_STATUS_BUSY);tick=8;assert(poll()==W61_STATUS_BUSY);
 terminal(true);assert(poll()==W61_STATUS_OK && sent==244);
 puts("PASS unsigned tick wrap preserves execution and drain ownership");
 reset(NO_TERMINAL);busy=1;assert(begin()==W61_STATUS_BUSY && !commands && !tick);
 reset(NO_TERMINAL);parse_busy=1;assert(begin()==W61_STATUS_BUSY && !commands && !tx_owned);
 puts("PASS contended TX/parser admission is nonblocking and writes zero command bytes");
 reset(SEND_FAIL);assert(begin()==W61_STATUS_OK);prompt();assert(poll()==W61_STATUS_BUSY);
 assert(poll()==W61_STATUS_IO_ERROR && !sent && !obj.Modem.handler_data.tx_desynchronized);
 puts("PASS SEND FAIL is a terminal rejection, not an ambiguous missing reply");
 return 0;
}
'''

def main():
    source = (ROOT / 'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c').read_text(encoding='utf-8')
    prefix = PREFIX.replace('enum { W61_STATUS_OK,', 'enum { W61_STATUS_ERROR=99, W61_STATUS_OK=0,')
    prefix = prefix.replace('int sem_tx_lock, last_error;', 'int sem_tx_lock, sem_parse_lock, last_error;')
    prefix = prefix.replace('unsigned notify_phase; bool notify_recv_seen;', '''unsigned notify_phase; bool notify_recv_seen;
 unsigned notify_length,notify_written; TickType_t notify_started,notify_budget;
 bool notify_late,notify_cancelled,notify_finish_pending; int notify_result; void *notify_owner;''')
    prefix = prefix.replace('static W61_Object_t obj;', '''static unsigned parse_depth,parse_busy,task=1;
 static void *xTaskGetCurrentTaskHandle(void) {return (void*)(uintptr_t)task;}
 static W61_Object_t obj;''')
    prefix=prefix.replace('#include <assert.h>', '#include <assert.h>\n#include <stdarg.h>')
    prefix=prefix.replace('static unsigned scenario,', 'static unsigned wait_starts,wait_ends;static char wait_last[192];\nstatic unsigned scenario,')
    prefix=prefix.replace('(void)tag;(void)fmt;++fences;', '''assert(!critical);++fences;
 if(!strcmp(tag,"RADIO-WAIT")) {
  if(!strncmp(fmt,"START",5))++wait_starts;
  if(!strncmp(fmt,"END",3))++wait_ends;
  va_list args;va_start(args,fmt);vsnprintf(wait_last,sizeof wait_last,fmt,args);va_end(args);
 }''')
    prefix = prefix.replace('if(sem==1) { assert(tx_owned);', 'if(sem==4) {assert(parse_depth);--parse_depth;return 1;}\n if(sem==1) { assert(tx_owned);')
    prefix = prefix.replace('if(sem==1) { if(busy)', 'if(sem==4) {assert(!wait);if(parse_busy)return 0;++parse_depth;return 1;}\n if(sem==1) { if(busy)')
    admission = (ROOT / 'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c').read_text(encoding='utf-8')
    helpers = ''.join(extract_function(admission, name) for name in
                      ['modem_cmd_handler_defer_tx', 'modem_cmd_handler_dns_drain_complete', 'modem_cmd_handler_wait_tx_ready'])
    callbacks = ''.join(extract(source, name, True) for name in
                        ['on_cmd_tx_ready', 'on_cmd_recv', 'on_cmd_ok', 'on_cmd_error', 'on_notify_terminal_ok'])
    functions = ''.join(extract_function(source, name) for name in
                        ['notify_finish', 'W61_AT_Common_NotifyBegin', 'W61_AT_Common_NotifyPoll', 'W61_AT_Common_NotifyCancel'])
    run_native(prefix.replace('/* INSERT_REAL_ADMISSION */', helpers) + callbacks + functions + TESTS)

if __name__ == '__main__':
    main()
