
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
typedef struct {struct {unsigned operation_active;}status;unsigned active_operation;} Control;static Control control;
static struct {struct {unsigned state;}shadow;struct{unsigned wifi_service_started_ms;}work;struct{void*wifi_control_context;}queues;} manager;
/* Preserve member typing used by production. */
static struct {struct{unsigned state;}shadow;struct{unsigned wifi_service_started_ms;}work;
 struct {Control *wifi_control_context;}queues;} radio_manager;
typedef struct {unsigned elapsed_ms,remaining_ms;} AppSettings_Status;
static unsigned settings_busy;static unsigned AppSettings_IsBusy(void){return settings_busy;}
static void AppSettings_GetStatus(AppSettings_Status*s){s->elapsed_ms=4800;s->remaining_ms=8450;}
static unsigned tick,hal,irq;static W61_Object_t *W61_ObjGet(void){return &driver;}
static struct {unsigned state,started_ms,stage;}radio_recovery;
static unsigned tx_interrupt_control(unsigned n){unsigned old=irq;irq=n;return old;}
static unsigned xTaskGetTickCount(void){return tick;}
static unsigned HAL_GetTick(void){return hal;}
static void reset(void){memset(&driver,0,sizeof driver);memset(&radio_manager,0,sizeof radio_manager);memset(&control,0,sizeof control);radio_manager.shadow.state=2;radio_manager.queues.wifi_control_context=&control;tick=hal=irq=0;}

static int spi_fault;static int spi_transaction_faulted(void){return spi_fault;}
void WIFI_BLE_App_GetServiceStatus(WifiBle_ServiceStatus_t *status)
{
  if (!status) return;
  *status = (WifiBle_ServiceStatus_t){ .state = WIFI_BLE_SERVICE_AVAILABLE,
      .reason = "READY" };
#if (APP_ST67W6X_ENABLED == 1U)
  W61_Object_t *driver = W61_ObjGet();
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  TickType_t now = xTaskGetTickCount();
  if (radio_recovery.state != 0U) {
    status->state = radio_recovery.state == 3U ? WIFI_BLE_SERVICE_FAULT : WIFI_BLE_SERVICE_WAITING;
    status->reason = radio_recovery.state == 3U ? "RECOVERY_FAILED" : "RADIO_RECOVERY";
    status->elapsed_ms = radio_recovery.stage ? HAL_GetTick() - radio_recovery.started_ms : 0U;
  } else if (radio_manager.shadow.state != WIFI_BLE_STATE_READY || !driver) {
    status->state = radio_manager.shadow.state == WIFI_BLE_STATE_ERROR ?
        WIFI_BLE_SERVICE_FAULT : WIFI_BLE_SERVICE_WAITING;
    status->reason = radio_manager.shadow.state == WIFI_BLE_STATE_ERROR ? "INIT_FAILED" : "STARTING";
  } else if (spi_transaction_faulted() != 0) {
    status->state = WIFI_BLE_SERVICE_FAULT; status->reason = "SPI_FENCED";
  } else if (driver->Modem.handler_data.tx_desynchronized) {
    status->state = WIFI_BLE_SERVICE_FAULT; status->reason = "AT_FENCED";
  } else if (driver->Modem.handler_data.dns_drain_active) {
    TickType_t deadline = driver->Modem.handler_data.dns_drain_until;
    status->elapsed_ms = (now - (deadline - pdMS_TO_TICKS(20000U))) * portTICK_PERIOD_MS;
    status->state = (int32_t)(now - deadline) >= 0 ? WIFI_BLE_SERVICE_FAULT : WIFI_BLE_SERVICE_WAITING;
    status->reason = "DNS_REPLY";
    status->remaining_ms = status->state == WIFI_BLE_SERVICE_WAITING ?
        (deadline - now) * portTICK_PERIOD_MS : 0U;
  } else if (driver->Modem.notify_phase && driver->Modem.notify_late) {
    status->state = WIFI_BLE_SERVICE_WAITING; status->reason = "BLE_TERMINAL";
    status->elapsed_ms = (now - driver->Modem.notify_started) * portTICK_PERIOD_MS;
    uint32_t limit = driver->Modem.notify_budget * portTICK_PERIOD_MS + 1000U;
    status->remaining_ms = status->elapsed_ms < limit ? limit - status->elapsed_ms : 0U;
  } else if (AppSettings_IsBusy()) {
    AppSettings_Status saved;
    AppSettings_GetStatus(&saved);
    status->state=WIFI_BLE_SERVICE_WAITING;status->reason="SETTINGS_STORE";
    status->elapsed_ms=saved.elapsed_ms;status->remaining_ms=saved.remaining_ms;
  }
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  else if (radio_manager.queues.wifi_control_context &&
      radio_manager.queues.wifi_control_context->status.operation_active) {
    status->state = WIFI_BLE_SERVICE_WAITING;
    WifiBle_WifiOperation_t op = radio_manager.queues.wifi_control_context->active_operation;
    status->reason = op == WIFI_BLE_WIFI_OPERATION_CONNECT ? "WIFI_CONNECT" :
        op == WIFI_BLE_WIFI_OPERATION_DISCONNECT ? "WIFI_DISCONNECT" : "WIFI_SCAN";
    status->elapsed_ms = HAL_GetTick() - radio_manager.work.wifi_service_started_ms;
  }
#endif
  (void)tx_interrupt_control(posture);
#else
  status->state = WIFI_BLE_SERVICE_FAULT; status->reason = "DISABLED";
#endif
}
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
 reset();settings_busy=1;WIFI_BLE_App_GetServiceStatus(&s);assert(s.state==1 && !strcmp(s.reason,"SETTINGS_STORE") && s.elapsed_ms==4800 && s.remaining_ms==8450);
 driver.Modem.handler_data.tx_desynchronized=true;WIFI_BLE_App_GetServiceStatus(&s);assert(s.state==2 && !strcmp(s.reason,"AT_FENCED"));settings_busy=0;
 puts("PASS settings store deadline is public; true fence retains precedence");
 reset();radio_manager.shadow.state=3;WIFI_BLE_App_GetServiceStatus(&s);assert(s.state==2 && !strcmp(s.reason,"INIT_FAILED"));
 puts("PASS failed initialization is public fault rather than a ready radio");
 radio_recovery.state=2;radio_recovery.stage=2;radio_recovery.started_ms=100;hal=250;
 WIFI_BLE_App_GetServiceStatus(&s);assert(s.state==1 && !strcmp(s.reason,"RADIO_RECOVERY") && s.elapsed_ms==150);
 radio_recovery.state=3;WIFI_BLE_App_GetServiceStatus(&s);assert(s.state==2 && !strcmp(s.reason,"RECOVERY_FAILED"));
 puts("PASS lifecycle barrier overrides partially rebuilt driver status and failed recovery remains unavailable");
 radio_recovery.state=0;reset();spi_fault=-3;WIFI_BLE_App_GetServiceStatus(&s);
 assert(s.state==2 && !strcmp(s.reason,"SPI_FENCED") && !driver.Modem.handler_data.tx_desynchronized && !irq);
 puts("PASS SPI fault immediately closes public admission; snapshot does not mutate AT owner");return 0;}
