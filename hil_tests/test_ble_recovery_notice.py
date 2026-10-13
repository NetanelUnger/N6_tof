"""Actual recovery event publication: backpressure, terminal drain and epochs."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT, run_native

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef unsigned UINT;typedef unsigned long ULONG;
#define APP_ST67W6X_BLE_GATT_ENABLED 1U
#define TX_SUCCESS 0U
#define TX_NOT_AVAILABLE 1U
#define TX_SIZE_ERROR 2U
#define TX_NO_WAIT 0U
#define TX_INT_DISABLE 1U
#define WIFI_BLE_STREAM_CLI 0U
typedef struct {unsigned sequence,pending,generation,rx_slots,tx_slots,reply_active,notification_generation;}WifiBle_RecoveryNotice_t;
typedef struct {struct {unsigned tx_queued;}stats[1];void *active_tx[1];struct {unsigned active,generation;}reply;}WifiBle_StreamContext_t;
static volatile WifiBle_RecoveryNotice_t ble_recovery_notice;
static volatile uint32_t ble_recovery_input_generation,ble_recovery_delivery_generation;
static WifiBle_StreamContext_t ctx;
static struct {struct {WifiBle_StreamContext_t *ble_stream_context;}queues;struct {unsigned ble_session_generation;}shadow;}radio_manager;
static unsigned irq,begin_error,end_error,writes,ends,race;static char output[256];
static UINT tx_interrupt_control(UINT x){UINT old=irq;irq=x;return old;}
static UINT WIFI_BLE_App_BeginReply(void){if(begin_error)return begin_error;ctx.reply.active=1;ctx.reply.generation=radio_manager.shadow.ble_session_generation;return 0;}
static UINT WIFI_BLE_App_StreamWrite(unsigned s,const void*b,ULONG n,ULONG w){assert(s==0 && w==0 && n<sizeof output);memcpy(output,b,n);output[n]=0;writes++;return 0;}
static UINT WIFI_BLE_App_EndReply(unsigned complete){assert(!complete);ctx.reply.active=0;ends++;if(race){ble_recovery_notice.sequence++;ble_recovery_notice.pending=1;}if(!end_error)ctx.stats[0].tx_queued=1;return end_error;}
static void reset(void){memset(&ctx,0,sizeof ctx);memset(output,0,sizeof output);ble_recovery_notice=(WifiBle_RecoveryNotice_t){.sequence=1,.pending=1,.generation=7};radio_manager.queues.ble_stream_context=&ctx;radio_manager.shadow.ble_session_generation=9;ble_recovery_input_generation=ble_recovery_delivery_generation=0;irq=begin_error=end_error=writes=ends=race=0;}
'''
TESTS = r'''
int main(void){
 reset();begin_error=1;assert(WIFI_BLE_App_SendRecoveryNotice()==1 && !writes && ble_recovery_notice.pending==1);
 begin_error=0;assert(WIFI_BLE_App_SendRecoveryNotice()==1 && writes==1 && ble_recovery_notice.pending==2);
 assert(strstr(output,"outcome=unknown") && strstr(output,"old_generation=7") && !strstr(output,"CLI-RESULT"));
 assert(WIFI_BLE_App_SendRecoveryNotice()==1 && writes==1);
 ctx.stats[0].tx_queued=0;ctx.active_tx[0]=&ctx;assert(WIFI_BLE_App_SendRecoveryNotice()==1);
 ctx.active_tx[0]=0;assert(!WIFI_BLE_App_SendRecoveryNotice() && !ble_recovery_notice.pending);
 assert(!WIFI_BLE_App_SendRecoveryNotice() && writes==1);
 puts("PASS slot backpressure retains notice; old-generation UNKNOWN is an event, input waits for actual terminal drain");
 ble_recovery_input_generation=9;
 assert(WIFI_BLE_App_SendRecoveryNotice()==1 && writes==2 && ble_recovery_notice.pending==2);
 assert(ble_recovery_delivery_generation==9 && strstr(output,"sequence=1"));
 ctx.stats[0].tx_queued=0;assert(!WIFI_BLE_App_SendRecoveryNotice());
 assert(!WIFI_BLE_App_SendRecoveryNotice() && writes==2);
 puts("PASS restored CCCD delivery is repeated once after fresh application input; no command or final replay");
 radio_manager.shadow.ble_session_generation=10;ble_recovery_input_generation=10;
 assert(!WIFI_BLE_App_SendRecoveryNotice() && writes==2);
 puts("PASS a later ordinary connection does not resurrect an already acknowledged recovery event");
 reset();ble_recovery_input_generation=9;
 assert(WIFI_BLE_App_SendRecoveryNotice()==1 && writes==1 && ble_recovery_delivery_generation==9);
 ctx.stats[0].tx_queued=0;assert(!WIFI_BLE_App_SendRecoveryNotice());
 assert(!WIFI_BLE_App_SendRecoveryNotice() && writes==1);
 puts("PASS input already present at first publication needs no duplicate event");
 reset();assert(WIFI_BLE_App_SendRecoveryNotice()==1);
 ble_recovery_input_generation=9;ctx.stats[0].tx_queued=0;
 assert(WIFI_BLE_App_SendRecoveryNotice()==1 && ble_recovery_notice.pending==1 && writes==1);
 assert(WIFI_BLE_App_SendRecoveryNotice()==1 && writes==2);
 puts("PASS input arriving during the proactive event remains held through the confirmed event drain");
 reset();end_error=1;assert(WIFI_BLE_App_SendRecoveryNotice()==1 && ble_recovery_notice.pending==1);
 puts("PASS publication failure never clears pending notice");
 reset();assert(WIFI_BLE_App_SendRecoveryNotice()==1);radio_manager.shadow.ble_session_generation=10;
 assert(WIFI_BLE_App_SendRecoveryNotice()==1 && writes==2 && ble_recovery_notice.notification_generation==10);
 puts("PASS link replacement resends an undrained event without replaying a command");
 reset();race=1;assert(WIFI_BLE_App_SendRecoveryNotice()==1 && ble_recovery_notice.sequence==2 && ble_recovery_notice.pending==1);
 puts("PASS a newer recovery during publication cannot be acknowledged by an older notice");
 reset();ble_recovery_notice.sequence=ble_recovery_notice.generation=ble_recovery_notice.rx_slots=ble_recovery_notice.tx_slots=ble_recovery_notice.reply_active=UINT32_MAX;
 assert(WIFI_BLE_App_SendRecoveryNotice()==1 && strlen(output)<256);
 puts("PASS maximal scalar metadata fits existing bounded response storage");
 return 0;}
'''

def main():
    source = (ROOT/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    run_native(PREFIX+function(source,'WIFI_BLE_App_GetRecoveryNotice')+function(source,'WIFI_BLE_App_SendRecoveryNotice')+TESTS)
    cli_source = (ROOT/'AppliNonSecure/Core/Src/debug_cli.c').read_text().replace('__attribute__((optimize("Os")))', '')
    cli = function(cli_source, 'cli_poll_ble')
    assert cli.index('WIFI_BLE_App_SendRecoveryNotice') < cli.index('WIFI_BLE_App_StreamReadLine')
    assert '!Firmware_Update_IsActive() && WIFI_BLE_App_SendRecoveryNotice()' in cli
    print('PASS CLI publishes event before reading new commands and excludes binary firmware-update input')

if __name__ == '__main__': main()
