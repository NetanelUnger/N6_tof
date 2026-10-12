"""Execute the actual BLE callback across old-parser stop and fresh init.

Mock only the RTOS/image/RX boundaries. Late records must not resurrect an
old generation or change the exclusive route; fresh subscriptions survive
reinitialization, while command input stays closed until recovery completes.
"""
import re

from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT, run_native


PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
typedef unsigned UINT, W6X_event_id_t;
#define TX_INT_DISABLE 1U
#define BLE_CLI_SERVICE_INDEX 0U
#define BLE_DEBUG_SERVICE_INDEX 1U
#define BLE_RX_CHAR_INDEX 0U
#define BLE_TX_CHAR_INDEX 1U
#define BLE_TOF_IMAGE_CHAR_INDEX 2U
#define BLE_DEBUG_RX_POLICY_ENABLED 0U
#define WIFI_BLE_STREAM_CLI 0U
#define WIFI_BLE_STREAM_DEBUG 1U
#define TOF_STREAM_BLE 2U
#define WIFI_BLE_ADV_CONNECTION_EVENT 1U
enum {W6X_BLE_EVT_CONNECTED_ID=1, W6X_BLE_EVT_DISCONNECTED_ID,
 W6X_BLE_EVT_NOTIFICATION_STATUS_ENABLED_ID, W6X_BLE_EVT_NOTIFICATION_STATUS_DISABLED_ID,
 W6X_BLE_EVT_MTU_SIZE_ID, W6X_BLE_EVT_WRITE_ID};
typedef struct {struct {unsigned conn_handle;}remote_ble_device;
 unsigned service_idx,charac_idx,available_data_length,mtu_size;}W6X_Ble_CbParamData_t;
static struct {unsigned state,stage;}radio_recovery;
static unsigned irq,rx_calls,disconnects,route_requests,route_releases;
static UINT tx_interrupt_control(UINT n){UINT old=irq;irq=n;return old;}
static unsigned HAL_GetTick(void){return 123;}
static void TOF_App_RequestStream(unsigned route){assert(route==TOF_STREAM_BLE);route_requests++;}
static void TOF_App_ReleaseStream(unsigned route){assert(route==TOF_STREAM_BLE);route_releases++;}
static void ble_stream_enqueue_rx(unsigned s,const uint8_t*d,unsigned n){assert(!radio_recovery.state && s==0 && d && n==5);rx_calls++;}
static void ble_note_disconnected(void){disconnects++;}
'''

TESTS = r'''
static void reset(unsigned state,unsigned stage){
 memset(&radio_manager,0,sizeof radio_manager);radio_recovery.state=state;radio_recovery.stage=stage;
 radio_manager.shadow.ble_session_generation=8;radio_manager.shadow.ble_mtu=23;
 irq=rx_calls=disconnects=route_requests=route_releases=0;
}
int main(void){
 W6X_Ble_CbParamData_t event={.remote_ble_device={.conn_handle=4},
     .available_data_length=5,.mtu_size=247};
 for(unsigned state=1;state<=3;state++){
  for(unsigned stage=0;stage<=3;stage++){
   if(state==2 && stage==3)continue;
   reset(state,stage);
   for(unsigned id=1;id<=6;id++)ble_event_callback(id,&event);
   assert(radio_manager.shadow.ble_session_generation==8 && !radio_manager.shadow.ble_connected);
   assert(!radio_manager.shadow.ble_cli_tx_subscribed && radio_manager.shadow.ble_mtu==23);
   assert(!rx_calls && !disconnects && !route_requests && !route_releases);
   assert(radio_manager.counters.ble_rx_write_events==1 && radio_manager.counters.ble_rx_discarded_bytes==5);
   assert(!radio_manager.work.ble_last_activity_tick && !irq);
  }
 }
 puts("PASS late old-parser records and failed recovery cannot resurrect link, generation, subscription or input");
 reset(1,1);event.charac_idx=BLE_TOF_IMAGE_CHAR_INDEX;
 ble_event_callback(W6X_BLE_EVT_NOTIFICATION_STATUS_ENABLED_ID,&event);
 assert(!route_requests && !radio_manager.shadow.ble_tof_image_subscribed);
 puts("PASS old ToF subscription cannot steal the exclusive image route during quiescence");
 reset(2,3);ble_event_callback(W6X_BLE_EVT_CONNECTED_ID,&event);
 assert(radio_manager.shadow.ble_connected && radio_manager.shadow.ble_session_generation==9);
 event.charac_idx=BLE_TX_CHAR_INDEX;
 ble_event_callback(W6X_BLE_EVT_NOTIFICATION_STATUS_ENABLED_ID,&event);
 ble_event_callback(W6X_BLE_EVT_MTU_SIZE_ID,&event);
 assert(radio_manager.shadow.ble_cli_tx_subscribed && radio_manager.shadow.ble_mtu==247);
 event.charac_idx=BLE_RX_CHAR_INDEX;ble_event_callback(W6X_BLE_EVT_WRITE_ID,&event);
 assert(!rx_calls && radio_manager.counters.ble_rx_discarded_bytes==5);
 puts("PASS fresh initialization retains automatic reconnect/CCCD/MTU observations while writes remain closed");
 radio_recovery.state=radio_recovery.stage=0;
 ble_event_callback(W6X_BLE_EVT_WRITE_ID,&event);assert(rx_calls==1);
 event.charac_idx=BLE_TOF_IMAGE_CHAR_INDEX;
 ble_event_callback(W6X_BLE_EVT_NOTIFICATION_STATUS_ENABLED_ID,&event);
 assert(route_requests==1 && radio_manager.shadow.ble_tof_image_subscribed);
 ble_event_callback(W6X_BLE_EVT_NOTIFICATION_STATUS_DISABLED_ID,&event);
 assert(route_releases==1 && !radio_manager.shadow.ble_tof_image_subscribed);
 puts("PASS completed recovery restores normal input and last-request-wins image subscription behavior");
 reset(3,3);ble_event_callback(W6X_BLE_EVT_WRITE_ID,NULL);
 assert(!radio_manager.counters.ble_rx_write_events && !irq);
 puts("PASS malformed null input remains harmless while admission is closed");
 return 0;
}
'''


def main():
    source = (ROOT / 'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    callback = function(source, 'ble_event_callback')
    manager = 'static struct {\n'
    for group in ('shadow', 'work', 'counters'):
        fields = sorted(set(re.findall(r'radio_manager\.' + group + r'\.(\w+)', callback)))
        manager += 'struct {' + ''.join(f'unsigned {field};' for field in fields) + '} ' + group + ';\n'
    manager += ('struct {uint8_t ble_receive_buffer[512];struct {struct {unsigned '
                'rx_dropped_events,rx_dropped_bytes;}stats[2];}*ble_stream_context;}queues;\n'
                '}radio_manager;\n')
    run_native(PREFIX + manager + callback + TESTS)


if __name__ == '__main__':
    main()
