"""Actual exact binary pairing read: original CRC/schema and no reconstruction."""
from test_wifi_scan_lifetime import ROOT, run_native
from test_wifi_assoc_admission import extract_function

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
typedef unsigned W6X_Status_t;
enum {W6X_STATUS_OK,W6X_STATUS_ERROR,W6X_STATUS_TIMEOUT};
#define CLOUD_RECORD_MAGIC 0x434C364EU
#define CLOUD_RECORD_VERSION 1U
#define Debug_UART_Log(...) ((void)0)
typedef struct {uint32_t magic;uint16_t version,length;uint32_t enabled;
 char device_id[65],workspace_id[65],token[1025];uint32_t crc32;} CloudPairingRecord_t;
static struct {CloudPairingRecord_t pairing;struct {unsigned enabled,paired;
 char device_id[65],workspace_id[65];}status;} context,*cloud=&context;
static CloudPairingRecord_t stored;
static char cloud_pair_file[]="fixture";
static unsigned calls,begins,ends,elapsed,cost,fail_call,clears,size_error,partial_bytes;
static unsigned unified_mode;
AppSettings_Result AppSettings_GetCloud(char*d,char*w,char*t,uint32_t*e){
 if(!unified_mode)return APP_SETTINGS_LEGACY;
 if(unified_mode==1){strcpy(d,"unified-device");strcpy(w,"unified-workspace");strcpy(t,"synthetic-unified-token");*e=1;return APP_SETTINGS_OK;}
 return unified_mode==2?APP_SETTINGS_ABSENT:unified_mode==3?APP_SETTINGS_CORRUPT:APP_SETTINGS_IO;
}
static void W6X_Net_RequestScopeBegin(unsigned budget,void*p,unsigned g){
 assert(budget==2000 && !p && !g && begins==ends);++begins;elapsed=0;}
static void W6X_Net_RequestScopeEnd(void){assert(begins==ends+1);++ends;}
static unsigned W6X_FS_GetSizeFile(char*f,uint32_t*s){assert(f==cloud_pair_file);
 *s=(unsigned)sizeof(stored)-size_error;return W6X_STATUS_OK;}
static unsigned W6X_FS_ReadFile(char*f,unsigned offset,void*out,unsigned length){
 assert(f==cloud_pair_file && !offset && length==sizeof(stored) && begins==ends+1);
 ++calls;if(calls==fail_call || elapsed+cost>2000){
  memcpy(out,&stored,partial_bytes);return W6X_STATUS_TIMEOUT;}
 elapsed+=cost;memcpy(out,&stored,sizeof stored);return W6X_STATUS_OK;}
static void cloud_clear_pairing(unsigned delete_file){assert(!delete_file);++clears;
 memset(&cloud->pairing,0,sizeof(cloud->pairing));cloud->status.paired=0;}
'''
TESTS = r'''
static void crc(void){stored.crc32=0;stored.crc32=cloud_crc32(&stored,sizeof stored);}
static void prepare(void){
 memset(&stored,0,sizeof stored);memset(&context,0,sizeof context);
 stored.magic=CLOUD_RECORD_MAGIC;stored.version=1;stored.length=sizeof stored;stored.enabled=1;
 strcpy(stored.device_id,"test-device");strcpy(stored.workspace_id,"test-workspace");
 strcpy(stored.token,"synthetic-fixture");crc();
 calls=begins=ends=elapsed=fail_call=clears=size_error=partial_bytes=0;cost=1;
}
static void scrubbed(void){const uint8_t*p=(const uint8_t*)&cloud->pairing;
 for(unsigned i=0;i<sizeof(cloud->pairing);++i)assert(!p[i]);
 assert(!cloud->status.paired && clears==1 && begins==ends);}
int main(void){
 assert(sizeof stored==1172 && offsetof(CloudPairingRecord_t,crc32)==1168);
 prepare();assert(cloud_load_pairing()==0 && cloud->status.paired && cloud->status.enabled);
 assert(!memcmp(&stored,&cloud->pairing,sizeof stored) && begins==1 && ends==1);
 assert(calls==1);
 puts("PASS exact binary payload and original full-record CRC required; no reconstruction");
 prepare();stored.enabled=0;crc();assert(!cloud_load_pairing() && !cloud->status.enabled);
 prepare();stored.token[100]=0xa5;crc();assert(!cloud_load_pairing());
 assert(!memcmp(&stored,&cloud->pairing,sizeof stored));
 prepare();((uint8_t*)&stored)[1167]=0xa5;crc();assert(!cloud_load_pairing());
 assert(!memcmp(&stored,&cloud->pairing,sizeof stored));
 puts("PASS actual nonzero tails/ABI padding preserved exactly; no saved file deletion");
 for(unsigned fault=0;fault<5;++fault){prepare();
  if(fault==0)stored.magic^=1;else if(fault==1)stored.version=2;
  else if(fault==2)stored.length--;else if(fault==3)stored.crc32^=1;
  else memset(stored.device_id,'x',sizeof stored.device_id);
  if(fault!=3)crc();assert(cloud_load_pairing()==-1);scrubbed();}
 prepare();size_error=1;assert(cloud_load_pairing()==-1 && !calls && !begins);scrubbed();
 for(unsigned partial=0;partial<sizeof stored;++partial){prepare();fail_call=1;partial_bytes=partial;
  assert(cloud_load_pairing()==-1);scrubbed();assert(calls==1 && begins==1);}
 prepare();cost=2000;assert(!cloud_load_pairing() && calls==1 && elapsed==2000 && begins==1);
 prepare();cost=2001;partial_bytes=16;assert(cloud_load_pairing()==-1);scrubbed();
 assert(calls==1 && !elapsed && begins==1);
 puts("PASS incomplete reads scrub volatile state; one original 2000ms budget is never renewed");
 puts("PASS original version/length/CRC/terminated strings and saved enable intent required");
 prepare();unified_mode=1;assert(!cloud_load_pairing() && cloud->status.paired && !calls && !begins);
 assert(!strcmp(cloud->pairing.token,"synthetic-unified-token"));
 for(unsigned m=2;m<=4;++m){prepare();unified_mode=m;assert(cloud_load_pairing()==-1 && !calls && !begins);scrubbed();}
 puts("PASS unified validated record preferred; tombstone/corrupt/unknown storage never falls back to legacy credentials");
 return 0;
}
'''
def main():
    source=(ROOT/'AppliNonSecure/Core/Src/cloud_relay.c').read_text(encoding='utf-8')
    funcs=''.join(extract_function(source,n) for n in
                  ('cloud_crc32','cloud_read_pairing_record','cloud_load_pairing'))
    header=(ROOT/'AppliNonSecure/Core/Inc/app_settings.h').read_text()
    codec=(ROOT/'AppliNonSecure/Core/Src/app_settings_format.c').read_text().replace('#include "app_settings.h"','')
    run_native(header+codec+PREFIX+funcs+TESTS)
if __name__=='__main__':main()
