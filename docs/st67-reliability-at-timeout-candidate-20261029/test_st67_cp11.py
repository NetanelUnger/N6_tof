"""Actual sender/await/terminal callbacks; simulated semaphore timing, no hardware."""
from pathlib import Path
import sys, argparse
HERE=Path(__file__).parent
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
OUT=HERE/'evidence/st67-cp11-at-timeout-candidate'
sys.path.insert(0,str(ROOT/'hil_tests'))
from test_wifi_scan_lifetime import run_native
from test_wifi_assoc_admission import PREFIX, TESTS, extract_function
from test_raw_send_response import extract
import test_cloud_request_budget as cloud

def timeout_case(driver):
    prefix=PREFIX.replace('void *budget_owner;','void *budget_owner;void *user_data;')
    prefix=prefix.replace('static unsigned response_ready;','''static unsigned response_ready,mode,response_waits,late_injected;
static void inject_terminal(void);
struct modem {unsigned notify_phase;bool raw_tx_terminal_only,raw_tx_payload_started,notify_recv_seen,raw_tx_response_received;int sem_response,sem_tx_ready;void (*notify_wake)(void);};
static struct modem modem;
#define MODEM_CMD_DEFINE(n) static int32_t n(struct modem_cmd_handler_data *data,uint16_t len,char **argv,uint16_t argc)
''')
    a=prefix.index('static int xSemaphoreTake(');b=prefix.index('static int modem_cmd_handler_update_cmds(',a)
    prefix=prefix[:a]+'''static int xSemaphoreTake(int sem,TickType_t wait){
 if(sem==1){assert(!held);tick+=lock_wait;assert(lock_wait<=wait);held=1;return 1;}
 assert(sem==2);
 if(!wait){unsigned n=response_ready;response_ready=0;return n;}
 ++response_waits;
 if(mode==2 || mode==3 || (mode==1 && response_waits==2))inject_terminal();
 if(response_ready){response_ready=0;return 1;}
 tick+=wait;return 0;
}
static int xSemaphoreGive(int sem){if(sem==1){assert(held);held=0;}else{assert(sem==2);response_ready=1;}return 1;}
'''+prefix[b:]
    old=extract_function(prefix,'modem_cmd_handler_await');prefix=prefix.replace(old,'')
    helpers='\n'.join(extract_function(driver,n) for n in ('modem_cmd_handler_get_error','modem_cmd_handler_set_error','modem_cmd_handler_defer_tx','modem_cmd_handler_dns_drain_complete','modem_cmd_handler_wait_tx_ready','modem_cmd_handler_await','modem_cmd_send_ext'))
    common=(ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c').read_text()
    callbacks=extract(common,'on_cmd_ok',True)+extract(common,'on_cmd_error',True)
    tests=r'''
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
'''
    return prefix+helpers+callbacks+tests

def admission(driver):
    return PREFIX+'\n'.join(extract_function(driver,n) for n in ('modem_cmd_handler_defer_tx','modem_cmd_handler_dns_drain_complete','modem_cmd_handler_wait_tx_ready','modem_cmd_send_ext'))+TESTS

def scoped(driver):
    # Reuse the existing actual-C budget suite, substituting only extracted driver source.
    prefix=cloud.ADMISSION_PREFIX.replace('void *budget_owner;','void *budget_owner;TickType_t budget_started,budget_ticks;const volatile uint32_t *budget_generation;uint32_t budget_expected;')
    prefix=prefix.replace('static TickType_t modem_cmd_handler_budget(struct modem_cmd_handler_data *d,TickType_t n) { (void)d;return n; }','')
    prefix=prefix.replace('static unsigned extend_once, during_write;','static unsigned extend_once,during_write,change_epoch_on_lock,await_timeout;')
    prefix=prefix.replace('held=1; }','held=1;if(change_epoch_on_lock)++*(unsigned*)data.budget_generation; }')
    prefix=prefix.replace('++awaits;return 0;','++awaits;if(await_timeout==2)response_ready=1;return await_timeout ? -ETIMEDOUT : 0;')
    return prefix+'\n'.join(extract_function(driver,n) for n in ('modem_cmd_handler_budget','modem_cmd_handler_defer_tx','modem_cmd_handler_dns_drain_complete','modem_cmd_handler_wait_tx_ready','modem_cmd_send_ext'))+cloud.BUDGET_TESTS

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',action='store_true');p.add_argument('--suite',choices=['timeout','admission','scoped'],default='timeout');p.add_argument('--label',required=True);a=p.parse_args()
    source=(ROOT if a.baseline else OUT/'candidate')/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c'
    code={'timeout':timeout_case,'admission':admission,'scoped':scoped}[a.suite](source.read_text())
    dest=OUT/(a.label+'.c');assert not dest.exists();dest.write_text(code,newline='\n');run_native(code)
