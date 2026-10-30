"""Actual C scheduler, CLI parser/admission and busy-publication frame IDs."""
from test_wifi_scan_lifetime import ROOT, run_native
from test_tof_recovery import function

def main():
    header=(ROOT/'AppliNonSecure/Core/Inc/demo_map.h').read_text(encoding='utf-8')
    cli=(ROOT/'AppliNonSecure/Core/Src/debug_cli.c').read_text(encoding='utf-8')
    wifi=(ROOT/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text(encoding='utf-8')
    run_native(header+r'''
#include <assert.h>
#include <stdio.h>
int main(void) {
 DemoMap_Status s={0};
 DemoMap_Start(&s,1000,3,100);assert(!DemoMap_Due(&s,1099));
 assert(DemoMap_Due(&s,1100) && s.sequence==1 && s.last_ms==1100 && s.next_ms==2100);
 assert(!DemoMap_Due(&s,1100));assert(DemoMap_Due(&s,4600));
 assert(s.sequence==4 && s.skipped==2 && s.late_slots==2 && s.next_ms==5100 && s.last_ms==4100);
 assert(!DemoMap_Due(&s,4600));
 DemoMap_Start(&s,300,3,0xfffffff0U);assert(!DemoMap_Due(&s,283));
 assert(DemoMap_Due(&s,284) && s.sequence==1 && s.last_ms==284);
 assert(DemoMap_Due(&s,584) && s.sequence==2);
 DemoMap_Start(&s,300,3,0);assert(DemoMap_Due(&s,1200));
 assert(s.sequence==4 && s.skipped==3 && s.late_slots==3 && s.next_ms==1500);
 assert(!DemoMap_Due(&s,1200));
 for(unsigned period=100;period<=60000;period+=59900){
  DemoMap_Start(&s,period,3,0xfffffff0U);
  assert(!DemoMap_Due(&s,0xfffffff0U+period-1));
  assert(DemoMap_Due(&s,0xfffffff0U+period) && s.sequence==1);
 }
 uint32_t bad[]={0,1,2,99,60001,0x7fffffff,0xffffffff};
 for(unsigned i=0;i<sizeof bad/sizeof bad[0];++i){
  assert(!DemoMap_ValidInterval(bad[i]));DemoMap_Start(&s,bad[i],3,100);
  assert(!s.interval_ms && !DemoMap_Due(&s,0x7fffffff));
 }
 s.epoch=0xffffffff;DemoMap_Start(&s,1000,3,0);assert(s.epoch==1);
 uint8_t b[2268*4+4];memset(b,0xA5,sizeof b);
 for(unsigned seq=1;seq<=2269;++seq){
  DemoMap_Fill(b,2268,seq);unsigned high=0;
  for(unsigned i=0;i<2268;++i){float f;memcpy(&f,b+i*4,4);
   if(f==3500){++high;assert(i==(seq-1)%2268);}else assert(f==500);}
  assert(high==1);for(unsigned i=2268*4;i<sizeof b;++i)assert(b[i]==0xA5);
 }
 puts("PASS 1000/300ms deadlines, bounds100/60000, missed slots/no burst, tick/epoch wrap, stop and pixel guards");
 return 0;
}
''')
    prefix=header+r'''
#include <assert.h>
#include <stdio.h>
#include <stdarg.h>
typedef unsigned UINT;typedef int Menu_t;typedef unsigned TOF_StreamDestination_t;
#define TX_SUCCESS 0U
#define TX_OPTION_ERROR 1U
#define TX_NOT_AVAILABLE 2U
#define TX_QUEUE_FULL 3U
#define TX_INT_DISABLE 0U
#define APP_ST67W6X_BLE_GATT_ENABLED 1U
#define CLI_LINE_SIZE 192U
#define CLI_MAX_ARGUMENTS 8
#define APP_TRANSPORT_BLE 1U
#define TOF_STREAM_NONE 0U
#define TOF_STREAM_BLE 2U
#define TOF_STREAM_CLOUD 3U
static DemoMap_Status demo_map;
static uint32_t tick,requested,dataset,released,publish_calls,publish_ids[16];
static int publication_busy;
static struct {struct {void *ble_tof_image_context;} queues;} radio_manager={{(void*)1}};
static struct {struct {unsigned transport;} route;} session;
static void *dummy_session=&session;
#define cli_active_session (&session)
static char output[2048];
static UINT tx_interrupt_control(UINT p){return p;}
static uint32_t HAL_GetTick(void){return tick;}
static uint32_t TOF_App_IsDatasetStreamEnabled(void){return dataset;}
static uint32_t TOF_App_GetRequestedStreamDestination(void){return requested;}
static void TOF_App_RequestStream(unsigned d){requested=d;}
static void TOF_App_ReleaseStream(unsigned d){released=d;requested=0;}
static const char *TOF_App_StreamName(unsigned d){return d==TOF_STREAM_BLE ? "BLE" : "CLOUD";}
static unsigned WIFI_BLE_App_GetImageEncoding(void){return 3;}
static void cli_print(const char *fmt,...){va_list a;va_start(a,fmt);vsnprintf(output+strlen(output),sizeof output-strlen(output),fmt,a);va_end(a);}
static int Menu_Reply(Menu_t *m,const char *s){(void)m;snprintf(output,sizeof output,"%s",s);return 0;}
static UINT wifi_publish_image(uint32_t seq,uint8_t ch,const float *data,uint8_t w,uint8_t h,const void *rps,uint32_t stamp,uint32_t epoch){
 (void)ch;(void)data;(void)w;(void)h;(void)rps;
 assert(epoch==demo_map.epoch && stamp==demo_map.last_ms);
 if(publication_busy)return publication_busy==1 ? TX_QUEUE_FULL : publication_busy==2 ? TX_NOT_AVAILABLE : TX_OPTION_ERROR;
 publish_ids[publish_calls++]=seq;return TX_SUCCESS;
}
'''
    functions='\n'.join(function(cli,n) for n in ('cli_split_arguments','cli_get_arguments','cli_token_equals','cli_parse_u32'))
    functions+='\n'+function(wifi.replace('UINT WIFI_BLE_App_SetDemoMap(', 'uint32_t WIFI_BLE_App_SetDemoMap('),'WIFI_BLE_App_SetDemoMap')
    functions+='\n'+function(wifi,'WIFI_BLE_App_GetDemoMapStatus')
    functions+='\n'+function(cli,'cli_command_demo')
    functions+='\n'+function(wifi,'demo_map_process')
    run_native(prefix+functions+r'''
static void command(const char *s){output[0]=0;cli_command_demo(NULL,s);}
int main(void){
 tick=50;command("DEMO MAP ON 1000");assert(demo_map.interval_ms==1000 && requested==TOF_STREAM_CLOUD && demo_map.next_ms==1050);
 assert(strstr(output,"interval 1000 ms"));
 session.route.transport=APP_TRANSPORT_BLE;command("demo map on 300");
 assert(demo_map.interval_ms==300 && requested==TOF_STREAM_BLE && demo_map.next_ms==350);
 command("DEMO MAP ON 100 CLOUD");assert(demo_map.interval_ms==100 && requested==TOF_STREAM_CLOUD);
 command("DEMO MAP ON 60000 BLE");assert(demo_map.interval_ms==60000 && requested==TOF_STREAM_BLE);
 const char *bad[]={"1","2","0","99","60001","4294967296","-300","+300","300ms","3e2","300.0","0x12c","999999999999999999999"};
 char text[192];
 for(unsigned i=0;i<sizeof bad/sizeof bad[0];++i){
  DemoMap_Status old=demo_map;snprintf(text,sizeof text,"DEMO MAP ON %s",bad[i]);command(text);
  assert(!memcmp(&old,&demo_map,sizeof old) && strstr(output,"Usage:") && strstr(output,"legacy ON 1/2 rejected"));
 }
 command("DEMO MAP ON");assert(strstr(output,"Usage:"));
 command("DEMO MAP ON 300 BLE extra");assert(strstr(output,"Usage:"));
 DemoMap_Status old=demo_map;command("DEMO MAP ON 300 USB");assert(strstr(output,"rejected") && !memcmp(&old,&demo_map,sizeof old));
 dataset=1;command("DEMO MAP ON 300 BLE");assert(strstr(output,"rejected") && !memcmp(&old,&demo_map,sizeof old));dataset=0;
 assert(WIFI_BLE_App_SetDemoMap(1,TOF_STREAM_CLOUD)==TX_OPTION_ERROR && !memcmp(&old,&demo_map,sizeof old));
 command("DEMO MAP STATUS");assert(strstr(output,"interval 60000 ms"));
 command("DEMO MAP OFF");assert(!demo_map.interval_ms && released==TOF_STREAM_BLE);
 tick=0;command("DEMO MAP ON 1000 CLOUD");
 for(tick=1000;tick<=5000;tick+=1000){publication_busy=(tick%2000)==0;demo_map_process();}
 assert(demo_map.sequence==5 && demo_map.accepted==3 && demo_map.skipped==2 && demo_map.late_slots==0);
 assert(publish_calls==3 && publish_ids[0]==1 && publish_ids[1]==3 && publish_ids[2]==5);
 assert(demo_map.publish_busy==2 && !demo_map.publish_unavailable && !demo_map.publish_other);
 tick=10000;publication_busy=0;demo_map_process();
 assert(publish_calls==4 && publish_ids[3]==10 && demo_map.skipped==6 && demo_map.late_slots==4);
 demo_map_process();assert(publish_calls==4);
 tick=11000;publication_busy=2;demo_map_process();
 tick=12000;publication_busy=3;demo_map_process();
 assert(demo_map.publish_busy==2 && demo_map.publish_unavailable==1 && demo_map.publish_other==1);
 assert(demo_map.skipped==demo_map.late_slots+demo_map.publish_busy+demo_map.publish_unavailable+demo_map.publish_other);
 requested=TOF_STREAM_BLE;demo_map_process();assert(!demo_map.interval_ms);
 puts("PASS actual CLI+admission: units, bounds, overflow/bad/legacy input, routes, dataset exclusion, OFF; busy IDs1/3/5 and late no-burst");
 return 0;
}
''')

if __name__=='__main__':main()
