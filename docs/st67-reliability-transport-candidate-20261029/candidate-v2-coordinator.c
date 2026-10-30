
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
typedef unsigned UINT;typedef int W6X_Status_t;
#define APP_ST67W6X_ENABLED 1U
#define APP_ST67W6X_WIFI_SERVICES_ENABLED 1U
#define APP_ST67W6X_BLE_GATT_ENABLED 0U
#define APP_ST67W6X_CLOUD_RELAY_ENABLED 0U
#define TX_INT_DISABLE 1U
#define TX_SUCCESS 0U
#define TX_NOT_AVAILABLE 9U
#define TX_TIMER_TICKS_PER_SECOND 1000U
#define WIFI_BLE_STATE_READY 2U
#define WIFI_CONTROL_WORK_FLAG 8U
#define TX_OR 1U
#define pdTRUE 1U
#define W6X_STATUS_ERROR 2
#define W6X_STATUS_OK 0
#define CHIP_EN_GPIO_Port 0
#define CHIP_EN_Pin 0
#define GPIO_PIN_RESET 0
typedef struct modem_cmd_handler_data {bool tx_desynchronized,dns_drain_active;unsigned dns_drain_until,sem_tx_lock;} Handler;
typedef struct {struct {Handler handler_data;unsigned notify_phase;void *modem_task_handle;}Modem;}W61_Object_t;
typedef struct {unsigned state,attempts,successes,failures,started_ms,elapsed_ms,radio_quiesced,cloud_quiesced,stage,wifi_reconnect_required;int last_status;}WifiBle_RecoveryStatus_t;
static W61_Object_t driver;
static volatile WifiBle_RecoveryStatus_t radio_recovery;
static unsigned recovery_window_started,recovery_window_attempts,recovery_invalid_request_id;
static unsigned recovery_fault_test;
static unsigned wifi_connection_desired;
static void wifi_restore_connection(void){}
static struct {struct {unsigned state,wifi_has_ip,wifi_connected,wifi_state_confirmed;}shadow;struct {unsigned wifi_last_request_id;}work;}radio_manager;
static unsigned settings_cancellations;static void AppSettings_Cancel(void){++settings_cancellations;}
static unsigned now,cloud_ack,mutex_available,spi_result,init_result,powered,destructions,inits,paused,logs;
static int radio_control_events;
static unsigned HAL_GetTick(void){return now;}static unsigned xTaskGetTickCount(void){return now;}
static W61_Object_t *W61_ObjGet(void){return &driver;}
static UINT tx_interrupt_control(UINT x){(void)x;return 0;}
static void tx_thread_sleep(unsigned x){now+=x;}
static void CloudRelay_PauseForRadioRecovery(void){paused++;}
static unsigned CloudRelay_IsRadioRecoveryQuiesced(void){return cloud_ack;}
static unsigned xSemaphoreTake(unsigned h,unsigned t){(void)h;(void)t;return mutex_available;}
static unsigned xSemaphoreGive(unsigned h){(void)h;return 1;}
static void tx_event_flags_set(void*p,unsigned f,unsigned op){(void)p;(void)f;(void)op;}
static void Debug_UART_Log(const char*a,const char*b,...){(void)a;(void)b;logs++;}
static int spi_transaction_quiesce(unsigned t){(void)t;return spi_result;}
static void vTaskDelete(void*t){(void)t;destructions++;}
static void W6X_WiFi_DeInit(void){assert(driver.Modem.handler_data.tx_desynchronized);destructions++;}
static void W6X_DeInit(void){destructions++;powered=0;}
static unsigned HAL_GPIO_ReadPin(unsigned p,unsigned n){(void)p;(void)n;return powered;}
static int W6X_Init(void){assert(!powered);inits++;powered=1;driver.Modem.handler_data.tx_desynchronized=false;return init_result;}
static int W6X_WiFi_Init(void){return 0;}static int wifi_enable_station_dhcp(void){return 0;}
static void wifi_refresh_status(void){}
static void CloudRelay_SetNetworkState(unsigned r,unsigned ip){(void)r;(void)ip;}
static void CloudRelay_RadioResetComplete(void){assert(inits && init_result==0);}
static void reset(void){memset(&driver,0,sizeof driver);memset((void*)&radio_recovery,0,sizeof radio_recovery);memset(&radio_manager,0,sizeof radio_manager);radio_manager.shadow.state=2;radio_manager.work.wifi_last_request_id=5;recovery_window_started=recovery_window_attempts=0;now=1000;cloud_ack=mutex_available=powered=1;spi_result=init_result=destructions=inits=paused=logs=0;driver.Modem.modem_task_handle=(void*)1;}

static int spi_fault;static int spi_transaction_faulted(void){return spi_fault;}
UINT WIFI_BLE_App_RequestRadioRecovery(void)
{
#if (APP_ST67W6X_ENABLED == 1U) && ((APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U) || (APP_ST67W6X_BLE_GATT_ENABLED == 1U))
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  if ((radio_recovery.state == 1U) || (radio_recovery.state == 2U) ||
      ((radio_recovery.state == 3U) && (radio_recovery.stage >= 2U)) ||
      (radio_manager.shadow.state != WIFI_BLE_STATE_READY))
  {
    (void)tx_interrupt_control(posture);
    return TX_NOT_AVAILABLE;
  }
  radio_recovery.started_ms = 0U;
  radio_recovery.stage = 0U;
  radio_recovery.radio_quiesced = 0U;
  radio_recovery.state = 1U;
  (void)tx_interrupt_control(posture);
  return TX_SUCCESS;
#else
  return TX_NOT_AVAILABLE;
#endif
}
static void radio_recovery_pump(void)
{
#if (APP_ST67W6X_ENABLED == 1U) && ((APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U) || (APP_ST67W6X_BLE_GATT_ENABLED == 1U))
  if (radio_recovery.state == 0U)
  {
    W61_Object_t *driver = W61_ObjGet();
    struct modem_cmd_handler_data *handler = &driver->Modem.handler_data;
    if (spi_transaction_faulted() != 0) handler->tx_desynchronized = true;
    if (handler->tx_desynchronized || (handler->dns_drain_active &&
        (int32_t)(xTaskGetTickCount() - handler->dns_drain_until) >= 0))
      (void)WIFI_BLE_App_RequestRadioRecovery();
    else return; /* ordinary contention/late terminal never resets the NCP */
  }
  if ((radio_recovery.state != 1U) || radio_recovery.radio_quiesced) return;
  if (radio_recovery.stage == 0U)
  {
    radio_recovery.started_ms = HAL_GetTick();
    radio_recovery.stage = 1U;
    radio_recovery.wifi_reconnect_required = radio_manager.shadow.wifi_connected;
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    radio_recovery.wifi_reconnect_required = wifi_connection_desired;
#endif
    AppSettings_Cancel(); /* retire any FS owner before the existing quiescence barrier */
    CloudRelay_PauseForRadioRecovery();
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    recovery_invalid_request_id = radio_manager.work.wifi_last_request_id;
#endif
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
    UINT posture = tx_interrupt_control(TX_INT_DISABLE);
    WifiBle_StreamContext_t *streams = radio_manager.queues.ble_stream_context;
    ++ble_recovery_notice.sequence;
    ble_recovery_notice.pending = 1U;
    ble_recovery_input_generation = ble_recovery_delivery_generation = 0U;
    ble_recovery_notice.generation = radio_manager.shadow.ble_session_generation;
    ble_recovery_notice.rx_slots = streams ? streams->stats[WIFI_BLE_STREAM_CLI].rx_queued : 0U;
    ble_recovery_notice.tx_slots = streams ? streams->stats[WIFI_BLE_STREAM_CLI].tx_queued : 0U;
    ble_recovery_notice.reply_active = streams ? streams->reply.active : 0U;
    radio_manager.shadow.ble_connected = 0U;
    radio_manager.shadow.ble_cli_tx_subscribed = 0U;
    radio_manager.shadow.ble_debug_tx_subscribed = 0U;
    radio_manager.shadow.ble_tof_image_subscribed = 0U;
    radio_manager.shadow.ble_rps_subscribed = 0U;
    radio_manager.shadow.ble_transport_ready = 0U;
    radio_manager.shadow.ble_connection_handle = 0xFFU;
    radio_manager.shadow.ble_mtu = 23U;
    ++radio_manager.shadow.ble_session_generation;
    if (ble_control.state) ble_control.job.cancelled = 1U;
    (void)tx_interrupt_control(posture);
    Debug_UART_Log("CLI-RECOVERY", "BLE generation=%lu outcome=unknown rx_slots=%lu tx_slots=%lu active_reply=%lu; link retiring, no command replay",
        (unsigned long)ble_recovery_notice.generation,
        (unsigned long)ble_recovery_notice.rx_slots, (unsigned long)ble_recovery_notice.tx_slots,
        (unsigned long)ble_recovery_notice.reply_active);
#endif
    W61_Object_t *driver = W61_ObjGet();
    const char *reason = spi_transaction_faulted() != 0 ? "SPI_FENCED" :
        driver->Modem.handler_data.tx_desynchronized ? "AT_FENCED" :
        driver->Modem.handler_data.dns_drain_active ? "DNS_EXPIRED" :
        recovery_fault_test ? "TEST_MISSING_RESPONSE" : "EXPLICIT_REQUEST";
    Debug_UART_Log("RADIO-RECOVERY", "START reason=%s started_ms=%lu", reason,
                   (unsigned long)radio_recovery.started_ms);
  }
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  ble_notify_retire_stale(); /* only Radio may cancel its notification owner */
  if (radio_manager.work.notify_source) return;
  ble_stream_purge_stale();
  WifiBle_TofImageContext_t *image = radio_manager.queues.ble_tof_image_context;
  if (image && (image->state != BLE_TOF_IMAGE_FILLING) &&
      !CloudRelay_IsTofFramePending(image->frame_id)) image->state = BLE_TOF_IMAGE_FREE;
  if (image && image->state != BLE_TOF_IMAGE_FREE) return;
#endif
  radio_recovery.radio_quiesced = 1U;
  (void)tx_event_flags_set(&radio_control_events, WIFI_CONTROL_WORK_FLAG, TX_OR);
#endif
}
static void radio_recovery_execute(void)
{
#if (APP_ST67W6X_ENABLED == 1U) && ((APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U) || (APP_ST67W6X_BLE_GATT_ENABLED == 1U))
  if (radio_recovery.state != 1U) { tx_thread_sleep(1U); return; }
  W61_Object_t *driver = W61_ObjGet();
  W6X_Status_t status = W6X_STATUS_ERROR;
  uint32_t now = HAL_GetTick();
  if ((now - recovery_window_started) >= 60000U)
  { recovery_window_started = now; recovery_window_attempts = 0U; }
  radio_recovery.cloud_quiesced = CloudRelay_IsRadioRecoveryQuiesced();
  if (!radio_recovery.radio_quiesced || !radio_recovery.cloud_quiesced)
  {
    if (radio_recovery.stage && (now - radio_recovery.started_ms >= 35000U)) goto failed;
    (void)tx_event_flags_set(&radio_control_events, WIFI_CONTROL_WORK_FLAG, TX_OR);
    tx_thread_sleep(1U);
    return;
  }
  /* A foreign transaction must have returned. Never force-release its mutex. */
  if (driver->Modem.notify_phase ||
      (xSemaphoreTake(driver->Modem.handler_data.sem_tx_lock, 0U) != pdTRUE))
  {
    if (now - radio_recovery.started_ms >= 35000U) goto failed;
    (void)tx_event_flags_set(&radio_control_events, WIFI_CONTROL_WORK_FLAG, TX_OR);
    tx_thread_sleep(1U);
    return;
  }
  if (recovery_window_attempts >= 3U)
  {
    (void)xSemaphoreGive(driver->Modem.handler_data.sem_tx_lock);
    goto failed;
  }
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U) && (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  if (recovery_fault_test)
  {
    recovery_fault_test = 0U;
    (void)xSemaphoreGive(driver->Modem.handler_data.sem_tx_lock);
    HAL_GPIO_WritePin(CHIP_EN_GPIO_Port, CHIP_EN_Pin, GPIO_PIN_RESET);
    W6X_Net_RequestScopeBegin(1000U, NULL, 0U);
    status = (W6X_Status_t)W61_AT_Common_SetExecute(driver, (uint8_t *)"AT\r\n", 1000U);
    W6X_Net_RequestScopeEnd();
    Debug_UART_Log("RADIO-RECOVERY", "TEST missing NCP response status=%ld genuine_fence=%lu",
                   (long)status, (unsigned long)driver->Modem.handler_data.tx_desynchronized);
    if (!driver->Modem.handler_data.tx_desynchronized) goto failed;
    if (xSemaphoreTake(driver->Modem.handler_data.sem_tx_lock, 0U) != pdTRUE) goto failed;
  }
#endif
  /* Admission is closed and all application owners acknowledged. Fence host
   * deinit commands too; only fresh initialization after power-off clears it. */
  driver->Modem.handler_data.tx_desynchronized = true;
  (void)xSemaphoreGive(driver->Modem.handler_data.sem_tx_lock);
  ++recovery_window_attempts;
  ++radio_recovery.attempts;
  radio_recovery.state = 2U;
  radio_recovery.stage = 2U;
  if (spi_transaction_quiesce(2000U) != 0) goto failed;
  /* Stop unsolicited callbacks before subsystem context/queues are destroyed. */
  if (driver->Modem.modem_task_handle)
  {
    vTaskDelete(driver->Modem.modem_task_handle);
    driver->Modem.modem_task_handle = NULL;
  }
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  W6X_Ble_DeInit();
  radio_manager.shadow.ble_gatt_ready = radio_manager.shadow.ble_advertising = 0U;
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  W6X_Net_DeInit();
  cloud_net_ready = 0U;
#endif
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  W6X_WiFi_DeInit();
#endif
  W6X_DeInit(); /* transport cleanup powers CHIP_EN off */
  if (HAL_GPIO_ReadPin(CHIP_EN_GPIO_Port, CHIP_EN_Pin) != GPIO_PIN_RESET) goto failed;
  radio_manager.shadow.wifi_has_ip = radio_manager.shadow.wifi_connected = 0U;
  radio_manager.shadow.wifi_state_confirmed = 0U;
  tx_thread_sleep((TX_TIMER_TICKS_PER_SECOND >= 10U) ? TX_TIMER_TICKS_PER_SECOND / 10U : 1U);
  radio_recovery.stage = 3U;
  status = W6X_Init();
  if (status != W6X_STATUS_OK) goto failed;
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  status = W6X_WiFi_Init();
  if (status != W6X_STATUS_OK) goto failed;
  status = wifi_enable_station_dhcp();
  if (status != W6X_STATUS_OK) goto failed;
  wifi_refresh_status();
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  status = W6X_Net_Init();
  if (status != W6X_STATUS_OK) goto failed;
  cloud_net_ready = 1U;
#endif
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  status = W6X_Ble_Init(W6X_BLE_MODE_SERVER, radio_manager.queues.ble_receive_buffer,
                         sizeof(radio_manager.queues.ble_receive_buffer) - 1U);
  if (status != W6X_STATUS_OK) goto failed;
  status = ble_configure_gatt_server();
  if (status != W6X_STATUS_OK) goto failed;
  if (!radio_manager.shadow.ble_advertising_desired)
  {
    status = W6X_Ble_AdvStop();
    if (status != W6X_STATUS_OK) goto failed;
    radio_manager.shadow.ble_advertising = 0U;
  }
  radio_manager.work.ble_recovery_pending = 0U;
  radio_manager.work.ble_restart_advertising_pending = 0U;
  radio_manager.work.ble_connect_pending = 0U;
  radio_manager.work.ble_adv_request = BLE_ADV_REQUEST_NONE;
  radio_manager.work.ble_disconnect_request = 0U;
  W6X_Ble_ServerNotifySetWakeCallback(ble_notification_wake);
  radio_manager.shadow.ble_transport_ready = 1U;
#endif
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  wifi_restore_connection();
  /* An unanswered restore AT is a fresh genuine fault. Do not publish READY
   * over it or silently retry an uncertain association. */
  if (driver->Modem.handler_data.tx_desynchronized) goto failed;
#endif
  CloudRelay_SetNetworkState(1U, radio_manager.shadow.wifi_has_ip);
  CloudRelay_RadioResetComplete(); /* proof: old NCP sockets no longer exist */
  radio_recovery.last_status = status;
  radio_recovery.elapsed_ms = HAL_GetTick() - radio_recovery.started_ms;
  ++radio_recovery.successes;
  Debug_UART_Log("RADIO-RECOVERY", "END result=ready elapsed_ms=%lu attempts=%lu; BLE reconnect required, wifi_credentials_required=%lu",
                   (unsigned long)radio_recovery.elapsed_ms, (unsigned long)radio_recovery.attempts,
                   (unsigned long)radio_recovery.wifi_reconnect_required);
  radio_recovery.stage = radio_recovery.radio_quiesced = 0U;
  radio_recovery.state = 0U;
  /* Resume processing old accepted requests as explicit failures, not replay. */
  (void)tx_event_flags_set(&radio_control_events, WIFI_CONTROL_WORK_FLAG, TX_OR);
  return;
failed:
  recovery_fault_test = 0U;
  radio_recovery.last_status = status;
  radio_recovery.elapsed_ms = radio_recovery.stage ? HAL_GetTick() - radio_recovery.started_ms : 0U;
  ++radio_recovery.failures;
  radio_recovery.state = 3U;
  Debug_UART_Log("RADIO-RECOVERY", "END result=failed stage=%lu elapsed_ms=%lu status=%ld; admission remains closed",
                   (unsigned long)radio_recovery.stage, (unsigned long)radio_recovery.elapsed_ms, (long)status);
#endif
}
int main(void){
 reset();radio_recovery_pump();assert(!radio_recovery.state && !paused);
 driver.Modem.handler_data.dns_drain_active=true;driver.Modem.handler_data.dns_drain_until=2000;
 radio_recovery_pump();assert(!radio_recovery.state);
 puts("PASS ordinary contention and unexpired DNS drain do not trigger NCP reset");
 now=2000;radio_recovery_pump();assert(radio_recovery.state==1 && paused==1 && recovery_invalid_request_id==5);
 assert(!destructions && !inits);puts("PASS expired DNS requests coordinated barrier before hardware mutation");
 cloud_ack=0;radio_recovery_execute();assert(!destructions && radio_recovery.state==1);
 cloud_ack=1;radio_recovery.radio_quiesced=0;radio_recovery_execute();assert(!destructions);
 radio_recovery.radio_quiesced=1;mutex_available=0;radio_recovery_execute();assert(!destructions);
 mutex_available=1;driver.Modem.notify_phase=4;radio_recovery_execute();assert(!destructions);
 puts("PASS Cloud, Radio, foreign AT lock and notification ownership each block teardown");
 driver.Modem.notify_phase=0;radio_recovery_execute();assert(!radio_recovery.state && radio_recovery.successes==1 && inits==1 && destructions==3);
 assert(radio_recovery.elapsed_ms>=100 && logs==2 && !driver.Modem.handler_data.tx_desynchronized);
 puts("PASS successful reset only clears fence through fresh initialization after power-off proof");
 reset();driver.Modem.handler_data.tx_desynchronized=true;radio_recovery_pump();spi_result=-1;radio_recovery_execute();
 assert(radio_recovery.state==3 && !destructions && !inits && driver.Modem.handler_data.tx_desynchronized);
 assert(WIFI_BLE_App_RequestRadioRecovery()!=0);puts("PASS failed SPI stop retains memory/fence and cannot retry unsafe partial lifecycle");
 reset();driver.Modem.handler_data.tx_desynchronized=true;radio_recovery_pump();cloud_ack=0;now+=35000;radio_recovery_execute();
 assert(radio_recovery.state==3 && !destructions);puts("PASS stalled Cloud acknowledgment is bounded and fails closed without reset");
 reset();WIFI_BLE_App_RequestRadioRecovery();radio_recovery_pump();init_result=2;radio_recovery_execute();
 assert(radio_recovery.state==3 && radio_recovery.failures==1 && inits==1);
 assert(WIFI_BLE_App_RequestRadioRecovery()!=0);puts("PASS fresh-init failure keeps admission closed without automatic reset loop");
 reset();WIFI_BLE_App_RequestRadioRecovery();radio_recovery_pump();recovery_window_attempts=3;radio_recovery_execute();
 assert(radio_recovery.state==3 && !destructions && !inits);puts("PASS three attempts per minute bounds repeated module resets");
 reset();recovery_window_started=UINT32_MAX-500;recovery_window_attempts=3;now=60000;WIFI_BLE_App_RequestRadioRecovery();radio_recovery_pump();radio_recovery_execute();
 assert(radio_recovery.successes==1 && recovery_window_attempts==1);puts("PASS reset budget recovers across tick wrap");
 reset();now=0;cloud_ack=0;WIFI_BLE_App_RequestRadioRecovery();radio_recovery_pump();
 assert(radio_recovery.stage==1 && !radio_recovery.started_ms && paused==1);
 now=20;radio_recovery.radio_quiesced=0;radio_recovery_pump();
 assert(paused==1 && !radio_recovery.started_ms && logs==1);
 now=35000;radio_recovery_execute();
 assert(radio_recovery.state==3 && radio_recovery.elapsed_ms==35000 && !destructions);
 assert(WIFI_BLE_App_RequestRadioRecovery()==0 && !radio_recovery.stage);
 radio_recovery_pump();assert(paused==2 && radio_recovery.started_ms==35000);
 puts("PASS uptime zero starts one barrier with a bounded owner deadline; safe retry starts a new stage");

 reset();spi_fault=-3;radio_recovery_pump();
 assert(driver.Modem.handler_data.tx_desynchronized && radio_recovery.state==1 && paused==1 && !destructions && !inits);
 cloud_ack=0;radio_recovery_execute();assert(!destructions && !inits && radio_recovery.state==1);
 puts("PASS transport fault requests existing owner barrier, fences AT, and waits for Cloud without direct reset");
 return 0;}
