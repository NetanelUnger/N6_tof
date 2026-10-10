"""Actual Radio notification ownership through route/session/MTU changes."""
from test_wifi_scan_lifetime import ROOT, run_native
from test_wifi_assoc_admission import extract_function

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
typedef unsigned W6X_Status_t;
enum {W6X_STATUS_OK,W6X_STATUS_BUSY,W6X_STATUS_ERROR};
#define BLE_NOTIFY_TIMEOUT_MS 100U
#define W6X_BLE_MAX_NOTIF_IND_DATA_LENGTH 244U
#define TOF_STREAM_BLE 2U
#define APP_ST67W6X_WIFI_SERVICES_ENABLED 1U
static struct {struct {unsigned ble_mtu,ble_connection_handle,ble_session_generation,
 ble_connected,ble_cli_tx_subscribed,ble_debug_tx_subscribed,ble_tof_image_subscribed;} shadow;
 struct {unsigned notify_source,notify_generation,notify_length,wifi_connect_call_active;} work;} radio_manager;
static unsigned route=TOF_STREAM_BLE,begin_calls,poll_calls,cancel_calls,pending=1,sent_length;
static unsigned TOF_App_GetStreamDestination(void) {return route;}
static unsigned W6X_Ble_ServerNotifyBegin(unsigned conn,unsigned service,unsigned characteristic,unsigned length,unsigned timeout) {
 (void)conn;(void)service;(void)characteristic;assert(timeout==100);++begin_calls;sent_length=length;return 0;
}
static unsigned W6X_Ble_ServerNotifyPoll(const void *data,unsigned length,unsigned *sent) {
 ++poll_calls;*sent=0;if(pending)return W6X_STATUS_BUSY;
 if(data){assert(length==sent_length);*sent=length;}return W6X_STATUS_OK;
}
static unsigned W6X_Ble_ServerNotifyCancel(void) {++cancel_calls;return W6X_STATUS_BUSY;}
'''

TESTS = r'''
int main(void) {
 uint8_t packet[244]={0};unsigned sent=999;
 radio_manager.shadow.ble_connected=1;radio_manager.shadow.ble_mtu=247;
 radio_manager.shadow.ble_cli_tx_subscribed=radio_manager.shadow.ble_tof_image_subscribed=1;
 radio_manager.shadow.ble_session_generation=5;
 radio_manager.work.wifi_connect_call_active=1;
 assert(ble_notify_fragment(3,0,2,packet,132,&sent)==W6X_STATUS_BUSY && !sent && !begin_calls);
 radio_manager.work.wifi_connect_call_active=0;
 assert(ble_notify_fragment(3,0,2,packet,132,&sent)==W6X_STATUS_BUSY && !sent);
 assert(begin_calls==1 && radio_manager.work.notify_source==3);
 assert(ble_notify_fragment(1,0,1,packet,15,&sent)==W6X_STATUS_BUSY && begin_calls==1 && poll_calls==1);
 puts("PASS image and CLI cannot consume each other's pending transaction result");
 radio_manager.work.wifi_connect_call_active=1;
 radio_manager.shadow.ble_mtu=23;
 assert(ble_att_payload_size()==132); /* Rebuild the same image header/chunk. */
 pending=0;assert(ble_notify_fragment(3,0,2,packet,132,&sent)==0 && sent==132);
 assert(radio_manager.work.notify_source==0 && ble_att_payload_size()==20);
 assert(ble_notify_fragment(1,0,1,packet,15,&sent)==W6X_STATUS_BUSY && !sent && begin_calls==1);
 radio_manager.work.wifi_connect_call_active=0;
 puts("PASS association blocks only fresh announcements; already-owned notification still finishes");
 puts("PASS mid-transfer MTU change cannot alter announced length; completion advances once");
 pending=1;assert(ble_notify_fragment(1,0,1,packet,15,&sent)==W6X_STATUS_BUSY);
 radio_manager.shadow.ble_session_generation=6;ble_notify_retire_stale();
 assert(cancel_calls==1 && radio_manager.work.notify_source==4);
 assert(ble_notify_fragment(1,0,1,packet,15,&sent)==W6X_STATUS_BUSY && begin_calls==2);
 pending=0;ble_notify_retire_stale();assert(!radio_manager.work.notify_source && cancel_calls==1);
 assert(ble_notify_fragment(1,0,1,packet,15,&sent)==0 && sent==15 && begin_calls==3);
 puts("PASS old BLE generation drains/discards before a fresh slot may begin");
 pending=1;assert(ble_notify_fragment(3,0,2,packet,132,&sent)==W6X_STATUS_BUSY);
 route=1;ble_notify_retire_stale();assert(cancel_calls==2 && radio_manager.work.notify_source==4);
 pending=0;ble_notify_retire_stale();assert(!radio_manager.work.notify_source);
 puts("PASS last-request-wins image handover cancels old result without another image buffer");
 return 0;
}
'''

def main():
    source = (ROOT / 'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text(encoding='utf-8')
    code = '\n'.join(extract_function(source, name) for name in
                     ['ble_att_payload_size','ble_notify_fragment','ble_notify_retire_stale'])
    run_native(PREFIX + code + TESTS)
    events = extract_function(source, 'ble_process_pending_events')
    assert events.index('ble_notify_retire_stale') < events.index('ble_stream_purge_stale')
    wake = extract_function(source, 'ble_notification_wake')
    assert 'tx_event_flags_set' in wake and 'RADIO_NOTIFICATION_WAKE_FLAG' in wake
    assert 'tx_thread_sleep' not in wake and 'Log' not in wake
    print('PASS cancellation precedes slot purge; parser wake only signals an existing event')
    callback = extract_function(source, 'error_callback')
    run_native(r'''
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#include <inttypes.h>
typedef int W6X_Status_t;
enum { W6X_STATUS_OK, W6X_STATUS_BUSY, W6X_STATUS_ERROR };
static struct { struct { struct { unsigned driver_error_callbacks; int last_driver_error; } faults; } counters; } radio_manager;
static unsigned log_calls;
#define LogError(...) (++log_calls)
''' + callback + r'''
int main(void) {
 const char *names[]={"W6X_Ble_ServerNotify", "W6X_Ble_ServerNotifyBegin",
                      "W6X_Ble_ServerNotifyPoll", "W6X_Ble_ServerNotifyCancel"};
 for(unsigned i=0;i<4;i++) error_callback(W6X_STATUS_BUSY,names[i]);
 assert(!log_calls && !radio_manager.counters.faults.driver_error_callbacks);
 for(unsigned i=0;i<4;i++) error_callback(W6X_STATUS_ERROR,names[i]);
 error_callback(W6X_STATUS_BUSY,"W6X_Ble_GetConn");
 error_callback(W6X_STATUS_BUSY,NULL);
 assert(log_calls==6 && radio_manager.counters.faults.driver_error_callbacks==6);
 puts("PASS async notification BUSY is expected; real errors and control BUSY remain visible");
 return 0;
}
''')

if __name__ == '__main__':
    main()
