"""Execute owner-specific deadline admission and Cloud network epoch recovery."""
from test_wifi_scan_lifetime import ROOT, run_native
from test_wifi_assoc_admission import PREFIX as ADMISSION_PREFIX, extract_function

BUDGET_TESTS = r'''
int main(void) {
 struct modem_iface iface={write_bus};struct modem_cmd_handler handler={&data};
 memset(&data,0,sizeof data);data.sem_tx_lock=1;data.eol="";
 unsigned epoch=7;data.budget_owner=(void*)1;data.budget_started=0;data.budget_ticks=450;
 data.budget_generation=&epoch;data.budget_expected=7;
 tick=440;assert(modem_cmd_handler_budget(&data,2000)==10);
 assert(modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)"AT+CIPDOMAIN",2,2000,0)==0);
 assert(response_budget==10 && writes==1 && !held);
 puts("PASS DNS and ordinary command waits consume remaining total request budget, not vendor 20s");
 tick=450;assert(modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)"AT",2,2000,0)==-ETIMEDOUT);
 assert(writes==1 && !held);
 puts("PASS expired request cannot issue a fire-and-forget command");
 tick=0;epoch=8;assert(!modem_cmd_handler_budget(&data,2000));
 assert(modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)"AT",2,2000,0)==-ETIMEDOUT && writes==1);
 puts("PASS stale network epoch stops subsequent AT commands before bytes or handlers");
 data.budget_owner=(void*)2;assert(modem_cmd_handler_budget(&data,2000)==2000);
 data.budget_owner=NULL;assert(modem_cmd_handler_budget(&data,2000)==2000);
 puts("PASS another task and unscoped operations keep their independent budget");
 data.budget_owner=(void*)1;epoch=7;data.budget_started=UINT32_MAX-4;data.budget_ticks=20;tick=5;
 assert(modem_cmd_handler_budget(&data,2000)==10);
 puts("PASS operation deadline subtraction survives RTOS tick wrap");
 data.budget_started=tick=0;data.budget_ticks=10;lock_wait=1;change_epoch_on_lock=1;
 assert(modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)"AT",2,100,0)==-ETIMEDOUT && !held && writes==1);
 puts("PASS epoch change during mutex admission is checked again before transmission");
 data.raw_command_attempted=false;
 assert(modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)"AT+CIPSEND=0,527",2,100,
                          MODEM_TX_TRACK_RAW_WRITE)==-ETIMEDOUT);
 assert(!data.raw_command_attempted && !data.tx_desynchronized && writes==1);
 puts("PASS actual scoped CIPSEND epoch rejection records zero bus attempts");
 epoch=7;change_epoch_on_lock=lock_wait=0;await_timeout=1;
 assert(modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)"AT",2,100,0)==-ETIMEDOUT);
 assert(data.tx_desynchronized && !held);
 puts("PASS unresolved scoped command response keeps a real AT fence; no unsafe retry");
 data.tx_desynchronized=false;data.raw_command_attempted=false;
 assert(modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)"AT+CIPSEND=0,527",2,100,
                          MODEM_TX_TRACK_RAW_WRITE)==-ETIMEDOUT);
 assert(data.raw_command_attempted && data.tx_desynchronized);
 puts("PASS CIPSEND written without response records ambiguity and keeps the real fence");
 data.tx_desynchronized=false;tick=0;data.budget_started=0;data.budget_ticks=450;
 assert(modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)"AT+CIPDOMAIN=host",2,2000,0)==-ETIMEDOUT);
 assert(!data.tx_desynchronized && data.dns_drain_active && data.dns_drain_until==2000 && !held);
 unsigned before=writes;
 assert(modem_cmd_handler_wait_tx_ready(&data,0,true)==-EBUSY && writes==before);
 assert(modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)"AT",2,10,0)==-ETIMEDOUT && writes==before);
 tick=660;modem_cmd_handler_dns_drain_complete(&data);
 assert(!data.dns_drain_active && !data.tx_desynchronized);
 data.budget_owner=NULL;await_timeout=0;
 assert(modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)"AT",2,10,0)==0 && writes==before+1);
 puts("PASS late DNS retains read-only admission after request timeout; terminal permits fresh requests");
 data.dns_drain_active=true;data.dns_drain_until=700;tick=700;
 assert(modem_cmd_handler_wait_tx_ready(&data,0,true)==-EIO && data.tx_desynchronized);
 modem_cmd_handler_dns_drain_complete(&data);assert(data.tx_desynchronized);
 puts("PASS expired DNS drain becomes a real fence; late replies cannot clear it");
 data.dns_drain_active=true;data.dns_drain_until=800;tick=710;
 modem_cmd_handler_dns_drain_complete(&data);assert(data.tx_desynchronized);
 puts("PASS terminal drain never clears an independent raw fence");
 data.tx_desynchronized=false;data.dns_drain_active=true;data.dns_drain_until=5;tick=UINT32_MAX-4;
 assert(modem_cmd_handler_wait_tx_ready(&data,0,true)==-EBUSY);
 tick=4;modem_cmd_handler_dns_drain_complete(&data);assert(!data.tx_desynchronized);
 puts("PASS DNS terminal drain deadline survives tick wrap");
 data.dns_drain_active=false;data.tx_desynchronized=false;tick=0;
 data.budget_owner=(void*)1;data.budget_started=0;data.budget_ticks=450;await_timeout=2;
 assert(modem_cmd_send_ext(&iface,&handler,NULL,0,(const uint8_t*)"AT+CIPDOMAIN=host",2,2000,0)==-ETIMEDOUT);
 assert(!data.dns_drain_active && !data.tx_desynchronized && !held);
 puts("PASS terminal racing timeout publication cannot strand DNS admission");
 return 0;
}
'''

CLOUD_PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#define APP_ST67W6X_CLOUD_USE_TLS 0
#define CLOUD_RECORD_MAGIC 123U
#define TOF_STREAM_CLOUD 3U
enum {CLOUD_HTTP_NONE,CLOUD_HTTP_TOF};
enum {CLOUD_RELAY_STATE_WAIT_WIFI,CLOUD_RELAY_STATE_DISABLED,CLOUD_RELAY_STATE_UNPAIRED};
typedef unsigned UINT;
static unsigned tick,close_failed,close_calls,releases,receives,starts;
static volatile uint32_t cloud_network_epoch;
static struct {
 unsigned network_epoch,tof_pending,http_kind,address_valid,backoff_step,next_action_tick;
 int socket; struct {unsigned enabled,backoff_seconds,tof_frames_dropped,state;} status;
 unsigned pair_pending;struct {unsigned magic,enabled;} pairing;
} context,*cloud=&context;
static unsigned HAL_GetTick(void){return tick;}
static unsigned TOF_App_GetStreamDestination(void){return TOF_STREAM_CLOUD;}
static void cloud_close_socket(void){++close_calls;cloud->http_kind=CLOUD_HTTP_NONE;if(!close_failed)cloud->socket=-1;}
static void cloud_release_tof(void){++releases;cloud->tof_pending=0;}
static void cloud_receive_step(void){++receives;}
static void cloud_start_next_request(void){++starts;}
#define Debug_UART_Log(...) ((void)0)
'''

CLOUD_TESTS = r'''
int main(void) {
 cloud->socket=2;cloud->http_kind=CLOUD_HTTP_TOF;cloud->tof_pending=1;
 cloud->network_epoch=5;cloud_network_epoch=6;cloud->address_valid=1;
 cloud->backoff_step=4;cloud->next_action_tick=10000;cloud->status.enabled=1;
 cloud->pairing.magic=CLOUD_RECORD_MAGIC;
 cloud_process(1); /* Link was lost and regained entirely between worker steps. */
 assert(close_calls==1 && releases==1 && starts==1 && !receives);
 assert(!cloud->address_valid && !cloud->backoff_step && cloud->socket==-1);
 assert(cloud->status.enabled==1 && cloud->pairing.magic==CLOUD_RECORD_MAGIC);
 puts("PASS warm reconnect retires stale socket/response and DNS even when IP is already ready");
 cloud->socket=3;cloud->http_kind=CLOUD_HTTP_TOF;cloud_network_epoch=7;close_failed=1;
 cloud_process(1);assert(cloud->socket==3 && starts==1 && !receives);
 cloud_process(1);assert(starts==1);
 puts("PASS unresolved close prevents opening another socket or committing a stale response");
 close_failed=0;cloud_process(1);assert(starts==2 && cloud->socket==-1);
 puts("PASS confirmed retirement restores requests using the retained desired state");
 cloud_process(0);assert(cloud->status.state==CLOUD_RELAY_STATE_WAIT_WIFI && starts==2);
 puts("PASS loss of IP leaves Cloud waiting while enabled/pairing intent is preserved");
 return 0;
}
'''

def main():
    driver = (ROOT / 'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c').read_text(encoding='utf-8')
    prefix = ADMISSION_PREFIX.replace('void *budget_owner;', '''void *budget_owner;
 TickType_t budget_started,budget_ticks;const volatile uint32_t *budget_generation;uint32_t budget_expected;''')
    prefix = prefix.replace('static TickType_t modem_cmd_handler_budget(struct modem_cmd_handler_data *d,TickType_t n) { (void)d;return n; }', '')
    prefix = prefix.replace('static unsigned extend_once, during_write;', 'static unsigned extend_once,during_write,change_epoch_on_lock,await_timeout;')
    prefix = prefix.replace('held=1; }', 'held=1;if(change_epoch_on_lock)++*(unsigned*)data.budget_generation; }')
    prefix = prefix.replace('++awaits;return 0;', '++awaits;if(await_timeout==2)response_ready=1;return await_timeout ? -ETIMEDOUT : 0;')
    code = '\n'.join(extract_function(driver, name) for name in
                     ['modem_cmd_handler_defer_tx','modem_cmd_handler_dns_drain_complete','modem_cmd_handler_wait_tx_ready','modem_cmd_send_ext'])
    helper = extract_function(driver, 'modem_cmd_handler_budget')
    run_native(prefix + helper + code + BUDGET_TESTS)
    source = (ROOT / 'AppliNonSecure/Core/Src/cloud_relay.c').read_text(encoding='utf-8')
    run_native(CLOUD_PREFIX + extract_function(source, 'cloud_process') + CLOUD_TESTS)
    begin = extract_function(source, 'cloud_begin_request')
    assert begin.index('http_deadline =') < begin.index('cloud_begin_request_inner(')
    assert 'cloud_network_epoch' in begin and 'W6X_Net_RequestScopeEnd' in begin
    print('PASS actual request wrapper starts deadline before DNS/open/send and closes its scope')

if __name__ == '__main__':
    main()
