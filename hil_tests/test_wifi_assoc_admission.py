"""Execute actual AT admission with simulated ticks and Wi-Fi parser events.

The shared parser must stay runnable during association. Commands preserve their
original deadline, and guarded admission must not write or change handlers.
"""
import re
from test_wifi_scan_lifetime import ROOT, run_native


def extract_function(source, name):
    match = re.search(r'^(?:static )?(?:void|int|int32_t|uint32_t|TickType_t|W61_Status_t|W6X_Status_t)\s+' +
                      re.escape(name) + r'\([^;]*?\)\s*\{', source, re.M)
    assert match, name
    end = source.index('{', match.start()) + 1
    level = 1
    while level:
        level += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]


PREFIX = r'''
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
 void *budget_owner;
};
struct modem_cmd_handler { void *cmd_handler_data; };
static unsigned tick, critical, writes, installed, awaits, held, delays, lock_wait;
static unsigned extend_once, during_write;
static unsigned response_ready;
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
static int xSemaphoreTake(int sem,TickType_t wait) {
 if(sem==1) { assert(!held);tick+=lock_wait;assert(lock_wait<=wait);held=1; }
 if(sem==2 && wait==0) {unsigned ready=response_ready;response_ready=0;return ready;}
 return 1;
}
static int xSemaphoreGive(int sem) { assert(sem==1 && held);held=0;return 1; }
static int modem_cmd_handler_update_cmds(struct modem_cmd_handler_data *d,
 const struct modem_cmd *c,size_t n,bool reset) {
 (void)d;(void)c;(void)n;(void)reset;assert(held);++installed;return 0;
}
static int modem_cmd_handler_await(struct modem_cmd_handler_data *d,int sem,TickType_t wait) {
 (void)d;(void)sem;assert(held);response_budget=wait;++awaits;return 0;
}
static int32_t write_bus(struct modem_iface *iface,const uint8_t *p,size_t n) {
 (void)iface;(void)p;assert(held && !critical);++writes;
 if(bus_failure==1) return -EBUSY;
 if(bus_failure==2) return (int32_t)n-1;
 if(during_write) modem_cmd_handler_defer_tx(&data,10);
 return (int32_t)n;
}
#define Debug_UART_Log(...) ((void)0)
'''

TESTS = r'''
static void reset(void) {
 memset(&data,0,sizeof data);data.sem_tx_lock=1;data.eol="\r\n";data.eol_len=2;
 tick=critical=writes=installed=awaits=held=delays=lock_wait=extend_once=during_write=0;
 response_budget=0;
 bus_failure=0;
}
static int command(unsigned budget,unsigned flags) {
 struct modem_iface iface={write_bus};struct modem_cmd_handler handler={&data};
 return modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)"AT",2,budget,flags);
}
int main(void) {
 reset();modem_cmd_handler_defer_tx(&data,10);
 assert(!tick && !delays && !critical);
 assert(modem_cmd_handler_wait_tx_ready(&data,10,true)==-EBUSY && !tick);
 puts("PASS parser publishes settling immediately; BLE admission is nonblocking");
 reset();modem_cmd_handler_defer_tx(&data,10);
 assert(command(20,0)==0 && tick==10 && response_budget==10 && writes==2 && !held);
 puts("PASS ordinary command settling consumes its existing response budget");
 reset();modem_cmd_handler_defer_tx(&data,10);
 assert(command(10,0)==-ETIMEDOUT && !writes && !installed && !awaits && !held);
 puts("PASS insufficient admission budget returns before handlers or bus writes");
 reset();modem_cmd_handler_defer_tx(&data,10);
 assert(command(0,MODEM_TX_ADMISSION_NOWAIT)==-EBUSY && !writes && !installed && !delays);
 puts("PASS fire-and-forget/raw announcement cannot bypass association settling");
 reset();modem_cmd_handler_defer_tx(&data,10);lock_wait=3;
 assert(command(20,0)==0 && tick==10 && response_budget==10);
 puts("PASS AT-lock waiting and settling share the same total deadline");
 reset();tick=UINT32_MAX-4;modem_cmd_handler_defer_tx(&data,10);
 assert(command(20,0)==0 && tick==5 && response_budget==10 && !data.tx_quiet_active);
 puts("PASS tick-counter wrap preserves settling and operation budgets");
 reset();modem_cmd_handler_defer_tx(&data,5);extend_once=1;
 assert(command(9,0)==-ETIMEDOUT && tick==5 && !writes && !data.tx_desynchronized);
 puts("PASS repeated association extends settling without extending command deadline");
 reset();data.tx_desynchronized=true;modem_cmd_handler_defer_tx(&data,10);
 assert(command(20,0)==-EIO && data.tx_desynchronized && !delays && !writes);
 puts("PASS existing raw fence wins over settling and is never cleared");
 reset();during_write=1;
 assert(command(20,0)==0 && awaits==1 && writes==2 && data.tx_quiet_active);
 puts("PASS association during an announced command does not block its response");
 reset();bus_failure=1;
 assert(command(20,MODEM_TX_TRACK_RAW_WRITE)==-EBUSY && writes==1 && !held);
 assert(!data.raw_command_attempted && !data.tx_desynchronized);
 puts("PASS bus zero-byte BUSY records no raw announcement and cannot falsely fence");
 reset();bus_failure=2;
 assert(command(20,MODEM_TX_TRACK_RAW_WRITE)==-EIO && writes==1 && !held);
 assert(data.raw_command_attempted && data.tx_desynchronized);
 puts("PASS partial raw command copy records ambiguity and retains a real AT fence");
 return 0;
}
'''


def main():
    folder = ROOT / 'ThirdParty/ST67W6X_Network_Driver'
    source = (folder / 'Driver/W61_at/modem_cmd_handler.c').read_text(encoding='utf-8')
    helpers = ''.join(extract_function(source, name) for name in
                      ['modem_cmd_handler_defer_tx', 'modem_cmd_handler_dns_drain_complete', 'modem_cmd_handler_wait_tx_ready',
                       'modem_cmd_send_ext'])
    run_native(PREFIX + helpers + TESTS)
    wifi = (folder / 'Core/w6x_wifi.c').read_text(encoding='utf-8')
    callback = extract_function(wifi, 'W6X_WiFi_Station_cb')
    connected = callback.split('case W61_WIFI_EVT_CONNECTED_ID:', 1)[1].split('break;', 1)[0]
    assert 'vTaskDelay' not in connected
    assert 'modem_cmd_handler_defer_tx' in connected
    assert 'pdMS_TO_TICKS(100)' in connected
    assert 'APP_wifi_cb(W6X_WIFI_EVT_CONNECTED_ID' in connected
    common = (folder / 'Driver/W61_at/w61_at_common.c').read_text(encoding='utf-8')
    assert re.search(r'case -EBUSY:\s+status = W61_STATUS_BUSY;', common)
    print('PASS callback keeps the original settling period, publishes CONNECTED, and maps BUSY')
    spi = (folder / 'Driver/W61_bus/spi_iface.c').read_text(encoding='utf-8')
    assert 'Debug_UART_NcpTerminalObservedAtSpi();' in spi
    assert not re.search(r'Debug_UART_(?:NcpTrace|Log)\s*\(', spi)
    uart = (ROOT / 'AppliNonSecure/Core/Src/debug_uart.c').read_text(encoding='utf-8')
    capture = extract_function(uart, 'Debug_UART_NcpTerminalObservedAtSpi')
    assert '__atomic_store_n' in capture and '__atomic_add_fetch' in capture
    assert not re.search(r'(?:Log|Write|printf|Queue|alloc|Delay)\s*\(', capture)
    print('PASS 768-byte SPI owner captures terminal scalars without formatting, allocation or waiting')


if __name__ == '__main__':
    main()
