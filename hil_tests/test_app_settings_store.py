"""Actual settings codec and transaction engine, with synthetic exact-I/O media.

No hardware, credential file or token is read. Compile the production C units.
"""
from test_wifi_scan_lifetime import ROOT, run_native

def production():
    paths = ('Inc/app_settings.h', 'Inc/app_settings_store.h',
             'Src/app_settings_format.c', 'Src/app_settings_store.c')
    return '\n'.join((ROOT/'AppliNonSecure/Core'/p).read_text().replace(
        '#include "app_settings.h"','').replace('#include "app_settings_store.h"','') for p in paths)

TESTS = r'''
#include <assert.h>
#include <stdio.h>
static char disk[2][APP_SETTINGS_TEXT_MAX];
static uint32_t lengths[2], mask, legacy;
static int inventory_error,size_error,read_error,cut,readback_flip;
static unsigned begins,ends,writes,reads;
static void begin(void *p){(void)p;assert(begins==ends);++begins;}
static void end(void *p){(void)p;assert(begins==ends+1);++ends;}
static int inventory(void*p,uint32_t*m,uint32_t*l){(void)p;*m=mask;*l=legacy;return inventory_error;}
static int size(void*p,unsigned slot,uint32_t*n){(void)p;assert(slot<2);*n=lengths[slot];return size_error;}
static int read_bytes(void*p,unsigned slot,uint32_t offset,void*out,uint32_t n){
 (void)p;assert(slot<2 && n<=APP_SETTINGS_IO_CHUNK && offset+n<=lengths[slot]);++reads;
 if(read_error)return -1;memcpy(out,disk[slot]+offset,n);
 if(readback_flip>=0 && (unsigned)readback_flip>=offset && (unsigned)readback_flip<offset+n)
  ((char*)out)[readback_flip-offset]^=1;
 return 0;
}
static int replace(void*p,unsigned slot,const void*bytes,uint32_t n){
 (void)p;assert(slot<2 && n<=sizeof disk[0]);++writes;mask|=1U<<slot;
 lengths[slot]=cut>=0?(uint32_t)cut:n;assert(lengths[slot]<=n);
 memcpy(disk[slot],bytes,lengths[slot]);return cut>=0?-1:0;
}
static const AppSettings_Io io={NULL,begin,end,inventory,size,read_bytes,replace};
static char store_text[APP_SETTINGS_TEXT_MAX],reboot_text[APP_SETTINGS_TEXT_MAX];
static AppSettings_Store store,reboot;
static AppSettings_Record record,decoded;
static char encoded[APP_SETTINGS_TEXT_MAX+1],bad[APP_SETTINGS_TEXT_MAX+1];
static void zero(const void*p,size_t n){const unsigned char*b=p;for(size_t i=0;i<n;++i)assert(!b[i]);}
static void reset(void){memset(&store,0,sizeof store);memset(&reboot,0,sizeof reboot);store.text=store_text;reboot.text=reboot_text;
 memset(disk,0,sizeof disk);memset(lengths,0,sizeof lengths);mask=legacy=0;
 inventory_error=size_error=read_error=0;cut=readback_flip=-1;begins=ends=writes=reads=0;}
static void fixture(unsigned maximum){
 memset(&record,0,sizeof record);record.version=1;record.generation=1;record.flags=15;
 record.ssid_length=maximum?32:4;record.password_length=maximum?63:4;
 record.device_length=maximum?64:4;record.workspace_length=maximum?64:4;record.token_length=maximum?1024:4;
 memset(record.ssid,'s',record.ssid_length);memset(record.password,'p',record.password_length);
 memset(record.device_id,'d',record.device_length);memset(record.workspace_id,'w',record.workspace_length);
 memset(record.token,'t',record.token_length);
}
static void disk_record(unsigned slot,const AppSettings_Record*r){size_t n=0;
 assert(AppSettings_Encode(r,disk[slot],sizeof disk[slot],&n)==APP_SETTINGS_OK);
 lengths[slot]=(uint32_t)n;mask|=1U<<slot;}
static void baseline(void){reset();fixture(1);disk_record(0,&record);
 assert(AppSettings_StoreLoad(&store,&io)==APP_SETTINGS_OK);assert(store.active_slot==0);
 store.pending=store.current;store.pending.token[0]='u';}
int main(void){
 size_t n;assert(settings_crc("123456789",9)==0xCBF43926U);
 fixture(1);assert(AppSettings_Encode(&record,encoded,sizeof encoded,&n)==APP_SETTINGS_OK);
 assert(n==APP_SETTINGS_TEXT_MAX);for(size_t i=0;i<n;++i)assert(encoded[i]>=33 && encoded[i]<=126);
 assert(AppSettings_Decode(encoded,n,&decoded)==APP_SETTINGS_OK);
 assert(decoded.length==n && decoded.generation==1 && decoded.token_length==1024);
 assert(!memcmp(decoded.token,record.token,sizeof record.token));
 assert(AppSettings_Encode(&record,bad,n-1,&n)==APP_SETTINGS_INVALID && !n);
 assert(AppSettings_Encode(&record,encoded,sizeof encoded,&n)==APP_SETTINGS_OK);
 for(size_t i=0;i<n;++i){memcpy(bad,encoded,n);bad[i]^=1;
  memset(&decoded,0xa5,sizeof decoded);AppSettings_Result result=AppSettings_Decode(bad,n,&decoded);
  assert(result==APP_SETTINGS_CORRUPT || result==APP_SETTINGS_UNSUPPORTED);zero(&decoded,sizeof decoded);}
 for(size_t i=0;i<n;++i){assert(AppSettings_Decode(encoded,i,&decoded)==APP_SETTINGS_CORRUPT);zero(&decoded,sizeof decoded);}
 memcpy(bad,encoded,n);bad[n]='!';assert(AppSettings_Decode(bad,n+1,&decoded)==APP_SETTINGS_CORRUPT);
 puts("PASS maximum 2561 printable bytes, independent CRC vector, every byte mutation/truncation and append");
 fixture(0);
 for(unsigned i=0;i<5;++i){AppSettings_Record r=record;
  if(i==0)r.ssid_length=33;if(i==1)r.password_length=64;if(i==2)r.device_length=65;
  if(i==3)r.workspace_length=65;if(i==4)r.token_length=1025;
  assert(AppSettings_Encode(&r,bad,sizeof bad,&n)==APP_SETTINGS_INVALID);}
 for(unsigned i=0;i<4;++i){AppSettings_Record r=record;
  if(i==0)r.version=2;if(i==1)r.generation=0;if(i==2)r.flags=16;if(i==3)r.flags=2;
  assert(AppSettings_Encode(&r,bad,sizeof bad,&n)==APP_SETTINGS_INVALID);}
 record.ssid[1]=0;assert(AppSettings_Encode(&record,bad,sizeof bad,&n)==APP_SETTINGS_INVALID);
 const char unsafe[]={'\r','\n','"','\\'};
 for(unsigned i=0;i<sizeof unsafe;++i){fixture(0);record.password[0]=unsafe[i];assert(AppSettings_Encode(&record,bad,sizeof bad,&n)==APP_SETTINGS_INVALID);}
 fixture(0);record.token[0]='\r';assert(AppSettings_Encode(&record,bad,sizeof bad,&n)==APP_SETTINGS_INVALID);
 fixture(0);record.password_length=0;memset(record.password,0,sizeof record.password);
 assert(AppSettings_Encode(&record,bad,sizeof bad,&n)==APP_SETTINGS_OK);
 fixture(0);memset(&record,0,sizeof record);record.version=record.generation=1;
 assert(AppSettings_Encode(&record,bad,sizeof bad,&n)==APP_SETTINGS_OK && n==67);
 puts("PASS bounds/schema/flags/terminators/AT-header safety, open network and authoritative tombstone");
 reset();assert(AppSettings_StoreLoad(&store,&io)==APP_SETTINGS_ABSENT && store.loaded);
 store.pending=record;assert(AppSettings_StoreCommit(&store,&io,0)==APP_SETTINGS_READ_ONLY && !writes);
 assert(AppSettings_StoreCommit(&store,&io,1)==APP_SETTINGS_OK && store.current.generation==1);
 assert(AppSettings_StoreLoad(&reboot,&io)==APP_SETTINGS_OK && !reboot.current.flags);
 reset();legacy=1;assert(AppSettings_StoreLoad(&store,&io)==APP_SETTINGS_LEGACY && !store.loaded);
 store.pending=record;assert(AppSettings_StoreCommit(&store,&io,1)==APP_SETTINGS_LEGACY && !writes);
 reset();inventory_error=1;assert(AppSettings_StoreLoad(&store,&io)==APP_SETTINGS_IO && !store.loaded);
 reset();mask=4;assert(AppSettings_StoreLoad(&store,&io)==APP_SETTINGS_IO);
 baseline();size_error=1;assert(AppSettings_StoreLoad(&reboot,&io)==APP_SETTINGS_IO && !reboot.loaded);
 baseline();read_error=1;assert(AppSettings_StoreLoad(&reboot,&io)==APP_SETTINGS_IO);
 baseline();disk[0][0]^=1;assert(AppSettings_StoreLoad(&reboot,&io)==APP_SETTINGS_CORRUPT && !reboot.loaded);
 assert(AppSettings_StoreCommit(&reboot,&io,1)==APP_SETTINGS_CORRUPT && !writes);
 puts("PASS absence proven by inventory; legacy/corrupt/unknown storage never overwritten");
 for(unsigned i=0;i<=APP_SETTINGS_TEXT_MAX;++i){baseline();cut=(int)i;
  assert(AppSettings_StoreCommit(&store,&io,1)==APP_SETTINGS_IO && !store.loaded && store.active_slot==0);
  assert(store.current.generation==1 && store.current.token[0]=='t');
  assert(AppSettings_StoreCommit(&store,&io,1)==APP_SETTINGS_IO && writes==1);
  cut=-1;assert(AppSettings_StoreLoad(&reboot,&io)==APP_SETTINGS_OK);
  assert(reboot.current.generation==(i==APP_SETTINGS_TEXT_MAX?2U:1U));
  assert(!memcmp(disk[0],encoded,APP_SETTINGS_TEXT_MAX));
  zero(store.text,APP_SETTINGS_TEXT_MAX);zero(&store.pending,sizeof store.pending);
 }
 puts("PASS all 2562 interrupted write positions; old slot intact; lost full-write ACK remains unknown until reload");
 for(unsigned i=0;i<APP_SETTINGS_TEXT_MAX;++i){baseline();readback_flip=(int)i;
  assert(AppSettings_StoreCommit(&store,&io,1)==APP_SETTINGS_CORRUPT && !store.loaded && store.active_slot==0);
  assert(store.current.token[0]=='t');}
 baseline();read_error=1;assert(AppSettings_StoreCommit(&store,&io,1)==APP_SETTINGS_IO && !store.loaded);
 baseline();assert(AppSettings_StoreCommit(&store,&io,1)==APP_SETTINGS_OK && store.active_slot==1);
 assert(store.current.generation==2 && store.current.token[0]=='u');
 assert(AppSettings_StoreLoad(&reboot,&io)==APP_SETTINGS_OK && reboot.current.generation==2);
 disk[1][0]^=1;assert(AppSettings_StoreLoad(&reboot,&io)==APP_SETTINGS_OK && reboot.current.generation==1);
 reset();fixture(0);record.generation=UINT32_MAX;disk_record(0,&record);
 assert(AppSettings_StoreLoad(&store,&io)==APP_SETTINGS_OK);store.pending=store.current;
 assert(AppSettings_StoreCommit(&store,&io,1)==APP_SETTINGS_OK && store.current.generation==1);
 assert(AppSettings_StoreLoad(&reboot,&io)==APP_SETTINGS_OK && reboot.current.generation==1);
 reset();fixture(0);disk_record(0,&record);disk_record(1,&record);
 assert(AppSettings_StoreLoad(&store,&io)==APP_SETTINGS_OK);
 record.token[0]='x';disk_record(1,&record);assert(AppSettings_StoreLoad(&store,&io)==APP_SETTINGS_CORRUPT);
 reset();fixture(0);disk_record(0,&record);record.generation+=0x80000000U;disk_record(1,&record);
 assert(AppSettings_StoreLoad(&store,&io)==APP_SETTINGS_CORRUPT);
 baseline();disk_record(1,&record);disk[1][3]='2';
 assert(AppSettings_StoreLoad(&reboot,&io)==APP_SETTINGS_UNSUPPORTED && !reboot.loaded);
 assert(AppSettings_StoreCommit(&reboot,&io,1)==APP_SETTINGS_UNSUPPORTED && !writes);
 assert(begins==ends);zero(reboot.text,APP_SETTINGS_TEXT_MAX);zero(&reboot.pending,sizeof reboot.pending);
 puts("PASS all 2561 readback mutations; commit publication, fallback, sequence wrap/tie/ambiguity and scratch scrubbing");
 return 0;
}
'''
def main():run_native(production()+TESTS)
if __name__=='__main__':main()
