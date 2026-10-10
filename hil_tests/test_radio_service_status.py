"""Read-only public availability snapshot: precedence, time and real fences."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT, run_native

PREFIX=r'''
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
typedef unsigned UINT;typedef uint32_t TickType_t;
#define APP_ST67W6X_ENABLED 1U
#define APP_ST67W6X_WIFI_SERVICES_ENABLED 1U
#define TX_INT_DISABLE 1U
#define WIFI_BLE_STATE_READY 2U
#define WIFI_BLE_STATE_ERROR 3U
#define WIFI_BLE_SERVICE_AVAILABLE 0U
#define WIFI_BLE_SERVICE_WAITING 1U
#define WIFI_BLE_SERVICE_FAULT 2U
#define WIFI_BLE_WIFI_OPERATION_CONNECT 2U
#define WIFI_BLE_WIFI_OPERATION_DISCONNECT 3U
#define pdMS_TO_TICKS(ms) ((ms)/10U)
#define portTICK_PERIOD_MS 10U
typedef unsigned WifiBle_WifiOperation_t;
typedef struct {unsigned state;const char *reason;unsigned elapsed_ms,remaining_ms;} WifiBle_ServiceStatus_t;
typedef struct {struct {struct {bool tx_desynchronized,dns_drain_active;uint32_t dns_drain_until;}handler_data;
 unsigned notify_phase,notify_started,notify_budget;bool notify_late;}Modem;} W61_Object_t;
static W61_Object_t driver;
static struct {struct {unsigned operation_active;}status;unsigned active_operation;}control;
static struct {struct {unsigned state;}shadow;struct{unsigned wifi_service_started_ms;}work;struct{void*wifi_control_context;}queues;} manager;
/* Preserve member typing used by production. */
static struct {struct{unsigned state;}shadow;struct{unsigned wifi_service_started_ms;}work;
 struct {typeof_control_placeholder *wifi_control_context;}queues;} radio_manager;
static unsigned tick,hal,irq;static W61_Object_t *W61_ObjGet(void){return &driver;}
static unsigned tx_interrupt_control(unsigned n){unsigned old=irq;irq=n;return old;}
static unsigned xTaskGetTickCount(void){return tick;}
static unsigned HAL_GetTick(void){return hal;}
static void reset(void){memset(&driver,0,sizeof driver);memset(&radio_manager,0,sizeof radio_manager);memset(&control,0,sizeof control);radio_manager.shadow.state=2;radio_manager.queues.wifi_control_context=&control;tick=hal=irq=0;}
'''
TESTS=r'''
int main(void){WifiBle_ServiceStatus_t s;
 reset();WIFI_BLE_App_GetServiceStatus(&s);assert(s.state==0 && !strcmp(s.reason,"READY") && !irq);
 driver.Modem.handler_data.dns_drain_active=true;driver.Modem.handler_data.dns_drain_until=2000;tick=674;
 WIFI_BLE_App_GetServiceStatus(&s);assert(s.state==1 && s.elapsed_ms==6740 && s.remaining_ms==13260);
 assert(driver.Modem.handler_data.dns_drain_active && !driver.Modem.handler_data.tx_desynchronized);
 puts("PASS DNS waiting exposes original elapsed/remaining budget without altering ownership");
 tick=2000;WIFI_BLE_App_GetServiceStatus(&s);assert(s.state==2 && !s.remaining_ms && !driver.Modem.handler_data.tx_desynchronized);
 puts("PASS expired drain is unavailable, snapshot never creates or clears protocol fence");
 driver.Modem.handler_data.tx_desynchronized=true;driver.Modem.notify_late=true;driver.Modem.notify_phase=4;control.status.operation_active=1;
 WIFI_BLE_App_GetServiceStatus(&s);assert(s.state==2 && !strcmp(s.reason,"AT_FENCED") && driver.Modem.handler_data.tx_desynchronized);
 puts("PASS actual fence takes precedence over DNS/BLE/control work and survives reads");
 reset();driver.Modem.notify_phase=4;driver.Modem.notify_late=true;driver.Modem.notify_budget=10;tick=80;
 WIFI_BLE_App_GetServiceStatus(&s);assert(s.state==1 && !strcmp(s.reason,"BLE_TERMINAL") && s.elapsed_ms==800 && s.remaining_ms==300);
 puts("PASS late BLE terminal reports total original transaction time and bounded drain");
 reset();control.status.operation_active=1;control.active_operation=2;radio_manager.work.wifi_service_started_ms=UINT32_MAX-50;hal=49;
 WIFI_BLE_App_GetServiceStatus(&s);assert(s.state==1 && !strcmp(s.reason,"WIFI_CONNECT") && s.elapsed_ms==100 && !s.remaining_ms);
 control.status.operation_active=0;WIFI_BLE_App_GetServiceStatus(&s);assert(s.state==0 && !s.elapsed_ms);
 puts("PASS Wi-Fi busy duration survives HAL wrap; completion returns available without allocation");
 reset();radio_manager.shadow.state=3;WIFI_BLE_App_GetServiceStatus(&s);assert(s.state==2 && !strcmp(s.reason,"INIT_FAILED"));
 puts("PASS failed initialization is public fault rather than a ready radio");return 0;}
'''

def main():
    source=(ROOT/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    prefix=PREFIX.replace('static struct {struct {unsigned operation_active;}status;unsigned active_operation;}control;',
        'typedef struct {struct {unsigned operation_active;}status;unsigned active_operation;} Control;static Control control;')
    prefix=prefix.replace('typeof_control_placeholder','Control')
    run_native(prefix+function(source,'WIFI_BLE_App_GetServiceStatus')+TESTS)
    cli=(ROOT/'AppliNonSecure/Core/Src/debug_cli.c').read_text()
    guard=cli.index('cli_command_needs_radio(pending)')
    assert guard < cli.index('Menu_Process(&cli_menu, &byte, 1U)',guard)
    assert cli.index('WIFI_BLE_App_BeginReply()',cli.index('static void __attribute__((optimize("Os"))) cli_poll_ble(void)\n{')) < cli.index('WIFI_BLE_App_StreamReadLine(',cli.index('static void __attribute__((optimize("Os"))) cli_poll_ble(void)\n{'))
    print('PASS admission precedes BLE dequeue and radio-dependent command execution; USB shadow commands remain independent')

if __name__=='__main__':main()
