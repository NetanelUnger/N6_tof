"""Execute the production post-dispatch completion branches, including OTA."""
from test_wifi_scan_lifetime import ROOT, run_native
from test_wifi_assoc_admission import extract_function
PREFIX=r'''
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#define TX_SUCCESS 0U
static int cli_cloud_session,cli_usb_session;
static int *cli_update_session,*cli_active_session;
static unsigned cli_cloud_wifi_request_id,cli_cloud_command_active,firmware,completed,polls,busy;
static unsigned Firmware_Update_IsActive(void){return firmware;}
static void Firmware_Update_Poll(unsigned tick){(void)tick;++polls;}
static unsigned HAL_GetTick(void){return 123;}
static unsigned CloudRelay_CompleteCommand(void){++completed;return busy?1:TX_SUCCESS;}
static void reset(void){cli_update_session=0;cli_active_session=&cli_cloud_session;cli_cloud_wifi_request_id=firmware=completed=polls=busy=0;cli_cloud_command_active=1;}
'''
TESTS=r'''
int main(void){
 reset();cli_cloud_wifi_request_id=17;finish(0,1);
 assert(!completed && cli_cloud_command_active && !polls);
 puts("PASS ordinary end-of-line cannot complete pending asynchronous Wi-Fi work");
 reset();finish(0,1);assert(completed==1 && !cli_cloud_command_active);
 reset();busy=1;finish(0,1);assert(completed==1 && cli_cloud_command_active);
 puts("PASS ordinary completion retains ownership when marker admission is busy");
 reset();cli_update_session=&cli_cloud_session;firmware=1;finish(0,1);
 assert(!completed && cli_cloud_command_active);
 finish(1,1);assert(!completed);
 firmware=0;finish(1,1);assert(completed==1 && !cli_cloud_command_active && !cli_update_session && polls==1);
 puts("PASS active XMODEM remains held and its terminal record still completes after finalization");
 return 0;
}
'''
def main():
    source=(ROOT/'AppliNonSecure/Core/Src/debug_cli.c').read_text()
    code=extract_function(source,'cli_poll_cloud')
    start=code.index('  if ((update_was_active == 0U) &&')
    end=code.index('  cli_active_session = &cli_usb_session;',start)
    branch=code[start:end]
    wrapper='static void finish(unsigned update_was_active,unsigned end){struct{unsigned completed;}input={end};\n'+branch+'}\n'
    run_native(PREFIX+wrapper+TESTS)

if __name__=='__main__':main()
