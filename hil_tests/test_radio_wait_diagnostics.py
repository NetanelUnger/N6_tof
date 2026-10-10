"""Execute real DNS admission/drain diagnostics; verify paired UART transitions."""
from test_wifi_scan_lifetime import ROOT, run_native
from test_wifi_assoc_admission import PREFIX, extract_function

LOGGER = r'''
#include <stdarg.h>
static unsigned events;
static char messages[16][192];
static unsigned delayed, immediate;
static unsigned terminal_during_pending;
static void modem_cmd_handler_dns_drain_complete(struct modem_cmd_handler_data*);
static void Debug_UART_Log(const char *tag,const char *format,...) {
 assert(!critical);
 assert(!strcmp(tag,"RADIO-WAIT") && events<16);
 if(terminal_during_pending && strstr(format,"PENDING reason=DNS_REPLY")) {
  terminal_during_pending=0;tick+=12;modem_cmd_handler_dns_drain_complete(&data);
 }
 va_list args;va_start(args,format);vsnprintf(messages[events++],192,format,args);va_end(args);
}
'''

TESTS = r'''
static void reset_test(void) {
 memset(&data,0,sizeof data);data.sem_tx_lock=1;data.eol="";
 tick=critical=writes=installed=awaits=held=delays=lock_wait=extend_once=during_write=0;
 response_ready=response_budget=bus_failure=events=delayed=immediate=terminal_during_pending=0;
 memset(messages,0,sizeof messages);
}
static int dns(void) {
 struct modem_iface iface={write_bus};struct modem_cmd_handler handler={&data};
 return modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)"AT+CIPDOMAIN=redacted",2,450,0);
}
int main(void) {
 reset_test();immediate=1;assert(!dns());
 assert(events==2 && strstr(messages[0],"START reason=DNS_REPLY") && strstr(messages[1],"END reason=DNS_REPLY"));
 assert(strstr(messages[1],"elapsed_ms=0 result=0 fenced=0"));
 assert(!data.dns_wait_active && !data.dns_drain_active);
 puts("PASS immediate DNS terminal cannot report END before START");
 reset_test();delayed=1;data.budget_owner=(void*)1;
 assert(dns()==-ETIMEDOUT && events==2 && tick==450 && data.dns_wait_active && data.dns_drain_active);
 assert(strstr(messages[1],"PENDING reason=DNS_REPLY elapsed_ms=4500"));
 for(unsigned i=0;i<50;++i)assert(modem_cmd_handler_wait_tx_ready(&data,0,true)==-EBUSY);
 assert(events==2);tick=744;modem_cmd_handler_dns_drain_complete(&data);
 assert(events==3 && strstr(messages[2],"elapsed_ms=7440 result=0 fenced=0"));
 modem_cmd_handler_dns_drain_complete(&data);assert(events==3 && !data.tx_desynchronized);
 puts("PASS late DNS reports pending and full 7440ms ownership once; busy retries do not flood UART");
 reset_test();delayed=1;data.budget_owner=(void*)1;assert(dns()==-ETIMEDOUT);
 tick=2000;assert(modem_cmd_handler_wait_tx_ready(&data,0,true)==-EIO);
 assert(events==3 && strstr(messages[2],"elapsed_ms=20000") && strstr(messages[2],"fenced=1"));
 modem_cmd_handler_dns_drain_complete(&data);assert(events==3 && data.tx_desynchronized);
 puts("PASS drain expiry reports fenced END once; late reply never announces recovery");
 reset_test();modem_cmd_handler_defer_tx(&data,450);
 assert(dns()==-ETIMEDOUT && !events && !writes);
 puts("PASS pre-write admission timeout cannot announce a DNS wait that never began");
 reset_test();bus_failure=1;assert(dns()==-EBUSY);
 assert(events==2 && strstr(messages[1],"result=-16 fenced=0") && !data.dns_wait_active);
 puts("PASS zero-byte bus rejection closes its diagnostic pair without a false fence");
 reset_test();bus_failure=2;assert(dns()==-EIO);
 assert(events==2 && strstr(messages[1],"fenced=1") && data.tx_desynchronized);
 puts("PASS partial command write ends diagnostics as a true fenced failure");
 reset_test();delayed=1;data.budget_owner=(void*)1;assert(dns()==-ETIMEDOUT);
 data.tx_desynchronized=true;tick=600;modem_cmd_handler_dns_drain_complete(&data);
 assert(events==3 && strstr(messages[2],"fenced=1") && data.tx_desynchronized);
 puts("PASS an independent existing fence is visible and never cleared by completion");
 reset_test();tick=UINT32_MAX-5;immediate=1;assert(!dns());
 assert(events==2 && strstr(messages[1],"elapsed_ms=100"));
 puts("PASS elapsed milliseconds survive RTOS tick wrap");
 reset_test();delayed=1;data.budget_owner=(void*)1;terminal_during_pending=1;
 assert(dns()==-ETIMEDOUT && events==3);
 assert(strstr(messages[1],"END reason=DNS_REPLY elapsed_ms=4620"));
 assert(strstr(messages[2],"PENDING reason=DNS_REPLY elapsed_ms=4500"));
 assert(strstr(messages[2],"snapshot=request_timeout") && !data.dns_drain_active);
 puts("PASS preempted PENDING remains a timeout snapshot, not a claim of still-active ownership");
 reset_test();delayed=1;data.budget_owner=(void*)1;assert(dns()==-ETIMEDOUT);
 tick=2000;assert(modem_cmd_handler_wait_tx_ready(&data,0,true)==-EIO);
 assert(strstr(messages[2],"outcome=fenced"));
 puts("PASS expired DNS explicitly reports fenced outcome even without a terminal error code");
 return 0;
}
'''

def main():
    source=(ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c').read_text(encoding='utf-8')
    prefix=PREFIX.replace('#define Debug_UART_Log(...) ((void)0)', '')
    prefix=prefix.replace('static TickType_t xTaskGetTickCount(void)', LOGGER+'\nstatic TickType_t xTaskGetTickCount(void)')
    prefix=prefix.replace('static int32_t write_bus(', 'static void modem_cmd_handler_dns_drain_complete(struct modem_cmd_handler_data*);\nstatic int32_t write_bus(')
    prefix=prefix.replace('return (int32_t)n;', '''if(immediate) {if(tick>UINT32_MAX-10)tick+=10;modem_cmd_handler_dns_drain_complete(&data);}return (int32_t)n;''')
    prefix=prefix.replace('++awaits;return 0;', '++awaits;if(delayed){tick+=wait;return -ETIMEDOUT;}return 0;')
    code='\n'.join(extract_function(source,name) for name in
                    ['modem_cmd_handler_defer_tx','modem_cmd_handler_dns_drain_complete','modem_cmd_handler_wait_tx_ready','modem_cmd_send_ext'])
    run_native(prefix+code+TESTS)
    wifi=(ROOT/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text(encoding='utf-8')
    for reason,call in [('WIFI_CONNECT','W6X_WiFi_Connect(&options)'),('WIFI_DISCONNECT','W6X_WiFi_Disconnect(request->forget)')]:
        start=wifi.index('START reason='+reason)
        assert start<wifi.index(call,start)<wifi.index('END reason='+reason,start)
    print('PASS existing Wi-Fi worker brackets connect/disconnect calls with timing reports')

if __name__=='__main__':main()
