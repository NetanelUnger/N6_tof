"""Execute actual CLI writer/formatter; prove sticky failures reach the trailer."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT, run_native

PREFIX=r'''
#include <assert.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdint.h>
typedef unsigned UINT; typedef unsigned long ULONG;
#define APP_ST67W6X_BLE_GATT_ENABLED 1U
#define APP_ST67W6X_CLOUD_RELAY_ENABLED 1U
#define APP_TRANSPORT_USB 0U
#define APP_TRANSPORT_BLE 1U
#define APP_TRANSPORT_CLOUD 2U
#define TX_SUCCESS 0U
#define TX_PTR_ERROR 1U
#define WIFI_BLE_STREAM_CLI 0U
#define CLI_BLE_TX_WAIT_TICKS 1U
typedef struct {struct{unsigned transport;}route;unsigned reply_reserved,reply_failed;}CliSession_t;
static CliSession_t session,*cli_active_session=&session;
static char cli_print_buffer[768];static UINT result;
static UINT WIFI_BLE_App_StreamWrite(unsigned a,const void*b,ULONG c,unsigned d){(void)a;(void)b;(void)c;(void)d;return result;}
static UINT CloudRelay_WriteOutput(const void*a,size_t b,unsigned c){(void)a;(void)b;(void)c;return result;}
static UINT App_Console_Write(const void*a,ULONG b){(void)a;(void)b;return result;}
#define Debug_UART_NcpTracePing(...) ((void)0)
'''
TESTS=r'''
int main(void){
 for(unsigned transport=1;transport<=2;transport++){
  session=(CliSession_t){.route.transport=transport,.reply_reserved=1};result=2;
  assert(cli_session_write(&session,"lost",4)==2 && session.reply_failed);
  result=0;assert(!cli_session_write(&session,"next",4) && session.reply_failed);
 }
 puts("PASS BLE/Cloud write failure remains sticky across subsequent successful writes");
 session=(CliSession_t){.route.transport=2,.reply_reserved=1};result=0;
 cli_print("%0800d",1);assert(session.reply_failed);
 puts("PASS formatter truncation cannot silently produce a complete response");
 session=(CliSession_t){.route.transport=0,.reply_reserved=0};result=2;
 cli_print("local");assert(!session.reply_failed);
 puts("PASS independent USB output never poisons a remote reply lease");return 0;
}
'''

def main():
    source=(ROOT/'AppliNonSecure/Core/Src/debug_cli.c').read_text()
    code='\n'.join(function(source,n) for n in ['cli_session_write','cli_print'])
    run_native(PREFIX+code+TESTS)
    process=function(source,'cli_process_byte')
    assert process.index('WIFI_BLE_App_EndReply(0U)') < process.index('Menu_Process(')
    assert 'cli_active_session->reply_reserved = 0U;' in process
    assert 'Wi-Fi connect rejected before execution' in process
    print('PASS raw XMODEM reservation released before dispatch; password admission checks availability')

if __name__=='__main__':main()
