"""Exercise actual scan admission against raw-transfer/late-parser ownership."""
from test_wifi_scan_lifetime import ROOT, PREFIX, run_native, function

MODEM = r'''
typedef uint32_t TickType_t;
typedef uint32_t W61_Status_t;
struct modem_cmd_handler_data { int sem_tx_lock, sem_parse_lock, tx_desynchronized; };
struct modem { struct modem_cmd_handler_data handler_data;
 int iface, handler, sem_response; };
'''
MOCKS = r'''
#include <inttypes.h>
#include <stdbool.h>
enum { W61_STATUS_OK, W61_STATUS_ERROR, W61_STATUS_TIMEOUT, W61_STATUS_IO_ERROR };
#define W61_WIFI_TIMEOUT 60U
#define W61_CMDRSP_STRING_SIZE 128U
#define W61_WIFI_MAX_SSID_SIZE 32U
#define W61_WIFI_MAX_DETECTED_AP 20U
#define W61_NULL_ASSERT(p) assert(p)
#define MODEM_NO_TX_LOCK 1U
#define pdPASS 1
#define MACSTR "%02x:%02x:%02x:%02x:%02x:%02x"
#define MAC2STR(p) p[0],p[1],p[2],p[3],p[4],p[5]
static struct { char SSID[33]; uint8_t MAC[6]; unsigned scan_type,Channel; } ScanOptions;
typedef AP W61_WiFi_AP_t;
static unsigned tick, tx_owned, allocations, sends, delay_count, admission_fails;
static unsigned alloc_fails, send_error, finish_after, parse_busy, raw_active, finish_on_error;
static void W61_WiFi_AT_Event(void*,uint16_t*,char**);
static void finish(void) {
 uint16_t argc=1; char *argv[]={"SCAN_DONE"};
 W61_WiFi_AT_Event(&obj,&argc,argv);
}
static TickType_t xTaskGetTickCount(void) { return tick; }
static TickType_t W61_AT_Common_TakeTxLockBudget(int lock,unsigned timeout,TickType_t *start) {
 assert(lock==1 && !tx_owned); *start=tick;
 if (admission_fails) return 0;
 tick+=4; raw_active=0; tx_owned=1; return timeout-4;
}
static TickType_t W61_AT_Common_RemainingTxBudget(TickType_t start,unsigned timeout) {
 return tick-start>=timeout ? 0 : timeout-(tick-start);
}
static void *pvPortMalloc(size_t bytes) {
 assert(tx_owned && !raw_active && bytes==sizeof(scratch));
 ++allocations; return alloc_fails ? NULL : scratch;
}
static int xSemaphoreTake(int lock,TickType_t wait) {
 assert(lock==2 && tx_owned); (void)wait;return !parse_busy;
}
static int xSemaphoreGive(int lock) {
 assert(tx_owned);if(lock==1) tx_owned=0;else assert(lock==2);return 1;
}
static int modem_cmd_send_ext(int *iface,int *handler,void *commands,int count,
 const uint8_t *cmd,int response,TickType_t budget,unsigned flags) {
 (void)iface;(void)handler;(void)commands;(void)count;(void)response;
 assert(tx_owned && !raw_active && flags==MODEM_NO_TX_LOCK);
 assert(budget==56 && !strncmp((const char*)cmd,"AT+CWLAP=",9));
 ++sends;tick+=2;
 if ((!send_error && !finish_after) || finish_on_error) finish();
 return send_error ? W61_STATUS_TIMEOUT : W61_STATUS_OK;
}
static W61_Status_t W61_Status(int ret) { return ret; }
static void vTaskDelay(unsigned n) {
 assert(tx_owned && n==1); tick+=n; ++delay_count;
 if (finish_after && delay_count==finish_after) finish();
}
static void Debug_UART_Log(const char *tag,const char *fmt,...) {
 (void)tag;(void)fmt;assert(!tx_owned);
}
'''
TESTS = r'''
static void reset(void) {
 memset(&obj,0,sizeof obj);obj.Modem.handler_data.sem_tx_lock=1;
 obj.Modem.handler_data.sem_parse_lock=2;obj.ulcbs.UL_wifi_sta_cb=callback;
 tick=tx_owned=allocations=sends=delay_count=admission_fails=alloc_fails=0;
 send_error=finish_after=parse_busy=callbacks=releases=status=finish_on_error=0; raw_active=1;
}
int main(void) {
 reset();assert(W61_WiFi_Scan(&obj)==W61_STATUS_OK);
 assert(allocations==1 && sends==1 && releases==1 && !tx_owned);
 puts("PASS scan allocates only after raw owner leaves and releases before unlock");
 reset();finish_after=3;assert(W61_WiFi_Scan(&obj)==W61_STATUS_OK);
 assert(delay_count==3 && releases==1 && !tx_owned);
 puts("PASS terminal OK before SCAN_DONE keeps admission locked until callback");
 reset();admission_fails=1;assert(W61_WiFi_Scan(&obj)==W61_STATUS_TIMEOUT);
 assert(!allocations && !sends && !releases && !tx_owned && raw_active);
 puts("PASS failed admission never steals memory from active raw transfer");
 reset();obj.Modem.handler_data.tx_desynchronized=1;
 assert(W61_WiFi_Scan(&obj)==W61_STATUS_IO_ERROR);
 assert(!allocations && !sends && !tx_owned);
 puts("PASS existing AT fence prevents scratch allocation and command send");
 reset();alloc_fails=1;assert(W61_WiFi_Scan(&obj)==W61_STATUS_ERROR);
 assert(allocations==1 && !sends && !tx_owned);
 puts("PASS allocation failure releases admission without sending a command");
 reset();send_error=1;assert(W61_WiFi_Scan(&obj)==W61_STATUS_TIMEOUT);
 assert(releases==1 && !obj.WifiCtx.ScanResults.AP && !tx_owned);
 assert(obj.Modem.handler_data.tx_desynchronized);
 puts("PASS failed command reclaims under parser lock and fences ambiguous response");
 reset();send_error=finish_on_error=1;
 assert(W61_WiFi_Scan(&obj)==W61_STATUS_TIMEOUT);
 assert(releases==1 && !obj.WifiCtx.ScanResults.AP && !tx_owned);
 assert(obj.Modem.handler_data.tx_desynchronized);
 puts("PASS SCAN_DONE before missing terminal response still fences AT ownership");
 reset();finish_after=100;assert(W61_WiFi_Scan(&obj)==W61_STATUS_TIMEOUT);
 assert(tick==60 && releases==1 && !tx_owned);
 puts("PASS missing completion consumes one bounded deadline and reclaims scratch");
 reset();send_error=1;parse_busy=1;
 assert(W61_WiFi_Scan(&obj)==W61_STATUS_TIMEOUT);
 assert(!releases && obj.WifiCtx.ScanResults.AP && !tx_owned);
 assert(obj.Modem.handler_data.tx_desynchronized);
 puts("PASS active parser retains its list; fenced AT prevents new raw senders");
 return 0;
}
'''


def main():
    source = (ROOT / 'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_wifi.c').read_text(encoding='utf-8')
    prefix = PREFIX.replace('typedef struct {\n struct { Scan ScanResults;', MODEM +
                            'typedef struct {\n struct modem Modem;\n struct { Scan ScanResults;', 1)
    assert 'struct modem Modem;' in prefix
    # The extraction helper accepts uint32_t definitions; the return type is
    # an enum on the target, with the same status values in this harness.
    scan = function(source.replace('W61_Status_t W61_WiFi_Scan(', 'uint32_t W61_WiFi_Scan('), 'W61_WiFi_Scan')
    run_native(prefix + MOCKS + function(source, 'W61_WiFi_AT_Event') + scan + TESTS)


if __name__ == '__main__':
    main()
