#include "app_settings_store.h"
#include "app_features.h"
#include <string.h>

#if (APP_ST67W6X_ENABLED == 1U) && (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
#include "tx_api.h"
#include "w61_at_api.h"
#include "w6x_api.h"
#if defined(__GNUC__)
#define SETTINGS_NOINLINE __attribute__((noinline))
#else
#define SETTINGS_NOINLINE
#endif

/* All settings operations share one nonblocking gate. No new task, payload
 * queue or dynamic settings allocation. Existing Radio/control/Cloud owners
 * are the only callers; their recovery barriers also cover these FS calls. */
/* Inventory precedes encoded data. A typed union saves the former1028-byte
 * permanent list without aliasing, allocation, or a larger owner stack. */
static union { char text[APP_SETTINGS_TEXT_MAX]; W61_FS_FilesList_t files; } settings_buffer;
static AppSettings_Store settings;
static TX_MUTEX settings_gate;
static uint32_t settings_ready, settings_present;
static volatile uint32_t settings_busy, settings_io_active, settings_cancel_epoch;
static uint32_t settings_expected, settings_started, settings_stage, settings_calls;
static W61_Object_t *settings_driver;
static AppSettings_Status settings_status;
#if APP_SETTINGS_TRANSITION_ENABLED
static uint32_t settings_transition_armed,settings_transition_epoch;
#endif
#define settings_files settings_buffer.files
static char settings_names[2][W61_SYS_FS_FILENAME_SIZE]={APP_SETTINGS_SLOT_0,APP_SETTINGS_SLOT_1};

static int settings_safe(void)
{
  W61_Object_t *driver=W61_ObjGet();
  return driver != NULL && driver->Modem.handler.cmd_handler_data != NULL &&
         !driver->Modem.handler_data.tx_desynchronized &&
         !driver->Modem.handler_data.dns_drain_active && driver->Modem.notify_phase==0U;
}

static SETTINGS_NOINLINE int settings_valid(void)
{
  return settings_cancel_epoch==settings_expected && W61_ObjGet()==settings_driver &&
    (uint32_t)(HAL_GetTick()-settings_started)<APP_SETTINGS_OPERATION_MS &&
    settings_driver && settings_driver->Modem.handler.cmd_handler_data &&
    !settings_driver->Modem.handler_data.tx_desynchronized &&
    !settings_driver->Modem.handler_data.dns_drain_active;
}
static void settings_begin(void *context)
{
  (void)context; settings_expected=settings_cancel_epoch;settings_started=HAL_GetTick();
  settings_driver=W61_ObjGet();settings_calls=settings_stage=0U;
}
static void settings_end(void *context)
{ (void)context;settings_io_active=0U;settings_stage=0U; }
static SETTINGS_NOINLINE int settings_call_begin(uint32_t stage)
{
  settings_io_active=1U; /* stop fresh BLE announcements; retain/drain existing owner */
  settings_stage=stage;
  for (;;) {
    UINT posture=tx_interrupt_control(TX_INT_DISABLE);
    if(!settings_valid() || settings_calls>=APP_SETTINGS_MAX_COMMANDS) {
      settings_io_active=0U;(void)tx_interrupt_control(posture);return 0;
    }
    /* A foreign Cloud scope must retire before ours may replace its metadata.
     * Cloud claims its scope atomically against settings_busy below. */
    if(!settings_driver->Modem.notify_phase &&
       (!settings_driver->Modem.handler_data.budget_owner ||
        settings_driver->Modem.handler_data.budget_owner==xTaskGetCurrentTaskHandle())) {
      uint32_t remaining=APP_SETTINGS_OPERATION_MS-(HAL_GetTick()-settings_started);
      if(remaining>APP_SETTINGS_COMMAND_MS)remaining=APP_SETTINGS_COMMAND_MS;
      ++settings_calls;
      W6X_Net_RequestScopeBegin(remaining,&settings_cancel_epoch,settings_expected);
      (void)tx_interrupt_control(posture);return 1;
    }
    (void)tx_interrupt_control(posture);tx_thread_sleep(1U);
  }
}
static SETTINGS_NOINLINE int settings_call_end(W61_Status_t result)
{
  W6X_Net_RequestScopeEnd();settings_io_active=0U;
  tx_thread_sleep(1U); /* terminal/pointers/AT mutex already retired */
  return result==W61_STATUS_OK && settings_valid() ? 0 : -1;
}
static int settings_confirm(void *context)
{
  (void)context;UINT posture=tx_interrupt_control(TX_INT_DISABLE);
  int valid=settings_valid();
  if(valid)settings_stage=7U; /* linearization: cancellation after this is after commit */
  (void)tx_interrupt_control(posture);return valid ? 0 : -1;
}

static int settings_inventory(void *context,uint32_t *slots,uint32_t *legacy)
{
  (void)context; *slots=*legacy=0U;
  memset(&settings_files,0,sizeof(settings_files));
  if(!settings_call_begin(1U))goto invalid;
  if(settings_call_end(W61_FS_ListFiles(W61_ObjGet(),&settings_files)) ||
     settings_files.nb_files>W61_SYS_FS_MAX_FILES) goto invalid; /* SDK rejects overflow/missing terminal; a complete full list is valid */
  for(uint32_t i=0U;i<settings_files.nb_files;++i) {
    const char *name=settings_files.filename[i];
    if(memchr(name,0,W61_SYS_FS_FILENAME_SIZE)==NULL) goto invalid;
    if(!strcmp(name,settings_names[0])) *slots|=1U;
    if(!strcmp(name,settings_names[1])) *slots|=2U;
    if(!strcmp(name,"n6cloud.cfg")) *legacy=1U;
  }
  settings_present=*slots; AppSettings_Scrub(&settings_files,sizeof(settings_files)); return 0;
invalid:
  AppSettings_Scrub(&settings_files,sizeof(settings_files)); return -1;
}

static int settings_size(void *context,unsigned slot,uint32_t *size)
{
  (void)context;
  if(slot>=2U || !settings_call_begin(2U))return -1;
  return settings_call_end(W61_FS_GetSizeFile(W61_ObjGet(),settings_names[slot],size));
}
static int settings_read(void *context,unsigned slot,uint32_t offset,void *data,uint32_t length)
{
  (void)context;
  if(slot>=2U || length>APP_SETTINGS_IO_CHUNK || !settings_call_begin(3U))return -1;
  return settings_call_end(W61_FS_ReadFile(W61_ObjGet(),settings_names[slot],offset,data,length));
}

static int settings_replace(void *context,unsigned slot,const void *data,uint32_t length)
{
  (void)context;
  if(!APP_SETTINGS_WRITES_ENABLED || slot>=2U || !settings_valid()) return -1;
  if(settings_present & (1U<<slot)) {
    if(!settings_call_begin(4U) || settings_call_end(W61_FS_DeleteFile(W61_ObjGet(),settings_names[slot])))return -1;
  }
  if(!settings_call_begin(5U) || settings_call_end(W61_FS_CreateFile(W61_ObjGet(),settings_names[slot])))return -1;
  settings_present|=1U<<slot;
  for(uint32_t offset=0U;offset<length;) {
    uint32_t count=length-offset; if(count>APP_SETTINGS_IO_CHUNK) count=APP_SETTINGS_IO_CHUNK;
    if(!settings_call_begin(6U) || settings_call_end(W61_FS_WriteFile(W61_ObjGet(),settings_names[slot],offset,
       (uint8_t *)data+offset,count))) return -1;
    offset+=count;
  }
  return 0;
}
#if APP_SETTINGS_TRANSITION_ENABLED
static int settings_admit_transition(void *context)
{
  (void)context;
  if(!settings_transition_armed)return 0;
  uint32_t slots=0U,legacy=0U;
  return settings_inventory(NULL,&slots,&legacy) || slots || !legacy || !settings_valid();
}
#define SETTINGS_ADMIT settings_admit_transition
#else
#define SETTINGS_ADMIT NULL
#endif
static const AppSettings_Io settings_io={NULL,settings_begin,settings_end,
    settings_inventory,settings_size,settings_read,settings_replace,settings_confirm,SETTINGS_ADMIT};

static void settings_publish(void)
{
  UINT old=tx_interrupt_control(TX_INT_DISABLE);
  settings_status.result=settings.result;
  settings_status.generation=settings.current.generation;
  settings_status.flags=settings.result==APP_SETTINGS_OK ? settings.current.flags : 0U;
  settings_status.writes_enabled=AppSettings_WritesEnabled();
  (void)tx_interrupt_control(old);
}
static SETTINGS_NOINLINE AppSettings_Result settings_lock(void)
{
  if(!settings_ready) return APP_SETTINGS_UNAVAILABLE;
  if(tx_mutex_get(&settings_gate,TX_NO_WAIT)!=TX_SUCCESS) return APP_SETTINGS_BUSY;
  UINT posture=tx_interrupt_control(TX_INT_DISABLE);settings_busy=1U;
  (void)tx_interrupt_control(posture);return APP_SETTINGS_OK;
}
static SETTINGS_NOINLINE AppSettings_Result settings_unlock(AppSettings_Result result)
{
  AppSettings_Scrub(&settings.pending,sizeof(settings.pending));
  settings_publish(); settings_busy=0U; (void)tx_mutex_put(&settings_gate); return result;
}
static AppSettings_Result settings_merge_ready(uint32_t pairing)
{
  if(!APP_SETTINGS_WRITES_ENABLED) return APP_SETTINGS_READ_ONLY;
#if APP_SETTINGS_TRANSITION_ENABLED
  if(settings_transition_armed && settings_cancel_epoch!=settings_transition_epoch) {
    settings_transition_armed=0U;settings.loaded=0U;settings.result=APP_SETTINGS_IO;
    return APP_SETTINGS_IO;
  }
  if(settings_transition_armed && !pairing) return APP_SETTINGS_READ_ONLY;
#else
  (void)pairing;
#endif
  if(!settings.loaded) return settings.result;
  settings.pending=settings.current; return APP_SETTINGS_OK;
}
static SETTINGS_NOINLINE int copy_field(char *out,size_t capacity,uint16_t *length,const char *in)
{
  size_t size=0U;
  if(in==NULL) return 0;
  while(size<capacity && in[size]!=0) ++size;
  if(size==capacity) return 0;
  AppSettings_Scrub(out,capacity);
  memcpy(out,in,size); *length=(uint16_t)size; return 1;
}

AppSettings_Result AppSettings_InitializeAndLoad(void)
{
  if(!settings_ready) {
    settings.text=settings_buffer.text;
    if(tx_mutex_create(&settings_gate,"NCP settings",TX_INHERIT)!=TX_SUCCESS) return APP_SETTINGS_UNAVAILABLE;
    settings.result=APP_SETTINGS_UNAVAILABLE; settings.active_slot=-1; settings_ready=1U;
  }
  AppSettings_Result r=settings_lock(); if(r!=APP_SETTINGS_OK) return r;
  if(!settings_safe()) return settings_unlock(APP_SETTINGS_BUSY);
#if APP_SETTINGS_TRANSITION_ENABLED
  settings_transition_armed=0U; /* reload discards an uncommitted RAM seed */
#endif
  r=AppSettings_StoreLoad(&settings,&settings_io); return settings_unlock(r);
}
void AppSettings_GetStatus(AppSettings_Status *status)
{
  if(status==NULL) return;
  UINT old=tx_interrupt_control(TX_INT_DISABLE);
  *status=settings_status;
  status->stage=settings_stage;
  status->elapsed_ms=settings_busy ? HAL_GetTick()-settings_started : 0U;
  status->remaining_ms=settings_busy && status->elapsed_ms<APP_SETTINGS_OPERATION_MS ?
    APP_SETTINGS_OPERATION_MS-status->elapsed_ms : 0U;
  if(!settings_ready) status->result=APP_SETTINGS_UNAVAILABLE;
  (void)tx_interrupt_control(old);
}
uint32_t AppSettings_WritesEnabled(void)
{
#if APP_SETTINGS_TRANSITION_ENABLED
  return APP_SETTINGS_WRITES_ENABLED && settings.loaded &&
    (settings.result==APP_SETTINGS_OK || settings.result==APP_SETTINGS_ABSENT) &&
    (!settings_transition_armed || settings_transition_epoch==settings_cancel_epoch);
#else
  return APP_SETTINGS_WRITES_ENABLED;
#endif
}
uint32_t AppSettings_IsBusy(void) { return settings_busy; }
uint32_t AppSettings_IsIoActive(void) { return settings_io_active; }
void AppSettings_Cancel(void) { UINT p=tx_interrupt_control(TX_INT_DISABLE);++settings_cancel_epoch;(void)tx_interrupt_control(p); }

uint32_t AppSettings_WifiUsesReference(void)
{
  AppSettings_Status status; AppSettings_GetStatus(&status);
  return status.result==APP_SETTINGS_OK && (status.flags & APP_SETTINGS_WIFI_REFERENCE)!=0U;
}

AppSettings_Result AppSettings_PrepareCloudTransition(const char *ssid,uint32_t desired)
{
#if APP_SETTINGS_TRANSITION_ENABLED && APP_SETTINGS_WRITES_ENABLED
  if(desired>1U || ssid==NULL) return APP_SETTINGS_INVALID;
  AppSettings_Result r=settings_lock(); if(r!=APP_SETTINGS_OK) return r;
  if(settings_transition_armed || settings.result!=APP_SETTINGS_LEGACY || settings.loaded)
    return settings_unlock(APP_SETTINGS_UNAVAILABLE);
  if(!settings_safe()) return settings_unlock(APP_SETTINGS_BUSY);
  /* A fresh complete list is the proof, not an earlier cached absence. */
  uint32_t slots=0U,legacy=0U;
  settings_begin(NULL);
  if(settings_inventory(NULL,&slots,&legacy) || settings_confirm(NULL)) r=APP_SETTINGS_IO;
  else if(slots || !legacy) r=APP_SETTINGS_UNAVAILABLE;
  else {
    AppSettings_Scrub(&settings.pending,sizeof(settings.pending));
    settings.pending.version=APP_SETTINGS_VERSION;settings.pending.generation=1U;
    settings.pending.flags=APP_SETTINGS_WIFI_PRESENT|APP_SETTINGS_WIFI_REFERENCE;
    if(desired)settings.pending.flags|=APP_SETTINGS_WIFI_DESIRED;
    size_t size=0U;
    if(!copy_field(settings.pending.ssid,sizeof(settings.pending.ssid),&settings.pending.ssid_length,ssid))
      r=APP_SETTINGS_INVALID;
    else r=AppSettings_Encode(&settings.pending,settings.text,APP_SETTINGS_TEXT_MAX,&size);
    if(r==APP_SETTINGS_OK) {
      settings.current=settings.pending;settings.current.generation=0U;
      settings.active_slot=-1;settings.loaded=1U;settings.result=APP_SETTINGS_ABSENT;
      settings_transition_armed=1U; /* no file/credential mutation here */
      settings_transition_epoch=settings_cancel_epoch;
    }
  }
  settings_end(NULL);AppSettings_Scrub(settings.text,APP_SETTINGS_TEXT_MAX);
  return settings_unlock(r);
#else
  (void)ssid;(void)desired;return APP_SETTINGS_READ_ONLY;
#endif
}

AppSettings_Result AppSettings_GetWifi(char ssid[APP_SETTINGS_SSID_CAP],
    char password[APP_SETTINGS_PASSWORD_CAP],uint32_t *desired)
{
  if(ssid==NULL || password==NULL || desired==NULL) return APP_SETTINGS_INVALID;
  AppSettings_Scrub(ssid,APP_SETTINGS_SSID_CAP); AppSettings_Scrub(password,APP_SETTINGS_PASSWORD_CAP); *desired=0U;
  AppSettings_Result r=settings_lock(); if(r!=APP_SETTINGS_OK) return r;
  r=settings.result;
  if(r==APP_SETTINGS_OK) {
    if(!(settings.current.flags & APP_SETTINGS_WIFI_PRESENT)) r=APP_SETTINGS_ABSENT;
    else {
      memcpy(ssid,settings.current.ssid,APP_SETTINGS_SSID_CAP);
      memcpy(password,settings.current.password,APP_SETTINGS_PASSWORD_CAP);
      *desired=(settings.current.flags & APP_SETTINGS_WIFI_DESIRED)!=0U;
    }
  }
  return settings_unlock(r);
}
AppSettings_Result AppSettings_SaveWifi(const char *ssid,const char *password)
{
  AppSettings_Result r=settings_lock(); if(r!=APP_SETTINGS_OK) return r;
  r=settings_merge_ready(0U); if(r!=APP_SETTINGS_OK) return settings_unlock(r);
  if(!copy_field(settings.pending.ssid,sizeof(settings.pending.ssid),&settings.pending.ssid_length,ssid) ||
     !copy_field(settings.pending.password,sizeof(settings.pending.password),&settings.pending.password_length,password))
    return settings_unlock(APP_SETTINGS_INVALID);
  settings.pending.flags &= ~APP_SETTINGS_WIFI_REFERENCE;
  settings.pending.flags|=APP_SETTINGS_WIFI_PRESENT|APP_SETTINGS_WIFI_DESIRED;
  r=AppSettings_StoreCommit(&settings,&settings_io,APP_SETTINGS_WRITES_ENABLED); return settings_unlock(r);
}
AppSettings_Result AppSettings_DisconnectWifi(uint32_t forget)
{
  if(forget>1U) return APP_SETTINGS_INVALID;
  AppSettings_Result r=settings_lock(); if(r!=APP_SETTINGS_OK) return r;
  r=settings_merge_ready(0U); if(r!=APP_SETTINGS_OK) return settings_unlock(r);
  settings.pending.flags &= ~APP_SETTINGS_WIFI_DESIRED;
  if(forget) {
    settings.pending.flags &= ~(APP_SETTINGS_WIFI_PRESENT|APP_SETTINGS_WIFI_REFERENCE);
    settings.pending.ssid_length=settings.pending.password_length=0U;
    AppSettings_Scrub(settings.pending.ssid,sizeof(settings.pending.ssid));
    AppSettings_Scrub(settings.pending.password,sizeof(settings.pending.password));
  }
  r=AppSettings_StoreCommit(&settings,&settings_io,APP_SETTINGS_WRITES_ENABLED); return settings_unlock(r);
}
AppSettings_Result AppSettings_GetCloud(char device[APP_SETTINGS_ID_CAP],
    char workspace[APP_SETTINGS_ID_CAP],char token[APP_SETTINGS_TOKEN_CAP],uint32_t *enabled)
{
  if(device==NULL || workspace==NULL || token==NULL || enabled==NULL) return APP_SETTINGS_INVALID;
  AppSettings_Scrub(device,APP_SETTINGS_ID_CAP); AppSettings_Scrub(workspace,APP_SETTINGS_ID_CAP);
  AppSettings_Scrub(token,APP_SETTINGS_TOKEN_CAP); *enabled=0U;
  AppSettings_Result r=settings_lock(); if(r!=APP_SETTINGS_OK) return r;
  r=settings.result;
  if(r==APP_SETTINGS_OK) {
    if(!(settings.current.flags & APP_SETTINGS_CLOUD_PRESENT)) r=APP_SETTINGS_ABSENT;
    else {
      memcpy(device,settings.current.device_id,APP_SETTINGS_ID_CAP);
      memcpy(workspace,settings.current.workspace_id,APP_SETTINGS_ID_CAP);
      memcpy(token,settings.current.token,APP_SETTINGS_TOKEN_CAP);
      *enabled=(settings.current.flags & APP_SETTINGS_CLOUD_ENABLED)!=0U;
    }
  }
  return settings_unlock(r);
}
AppSettings_Result AppSettings_SaveCloud(const char *device,const char *workspace,
    const char *token,uint32_t enabled)
{
  if(enabled>1U) return APP_SETTINGS_INVALID;
  AppSettings_Result r=settings_lock(); if(r!=APP_SETTINGS_OK) return r;
  r=settings_merge_ready(1U); if(r!=APP_SETTINGS_OK) return settings_unlock(r);
  if(!copy_field(settings.pending.device_id,sizeof(settings.pending.device_id),&settings.pending.device_length,device) ||
     !copy_field(settings.pending.workspace_id,sizeof(settings.pending.workspace_id),&settings.pending.workspace_length,workspace) ||
     !copy_field(settings.pending.token,sizeof(settings.pending.token),&settings.pending.token_length,token))
    return settings_unlock(APP_SETTINGS_INVALID);
  settings.pending.flags|=APP_SETTINGS_CLOUD_PRESENT;
  settings.pending.flags &= ~APP_SETTINGS_CLOUD_ENABLED;
  if(enabled) settings.pending.flags|=APP_SETTINGS_CLOUD_ENABLED;
  r=AppSettings_StoreCommit(&settings,&settings_io,APP_SETTINGS_WRITES_ENABLED);
#if APP_SETTINGS_TRANSITION_ENABLED
  settings_transition_armed=0U; /* no implicit retry/re-arm after unknown outcome */
#endif
  return settings_unlock(r);
}
AppSettings_Result AppSettings_ClearCloud(void)
{
  AppSettings_Result r=settings_lock(); if(r!=APP_SETTINGS_OK) return r;
  r=settings_merge_ready(0U); if(r!=APP_SETTINGS_OK) return settings_unlock(r);
  settings.pending.flags &= ~(APP_SETTINGS_CLOUD_PRESENT|APP_SETTINGS_CLOUD_ENABLED);
  settings.pending.device_length=settings.pending.workspace_length=settings.pending.token_length=0U;
  AppSettings_Scrub(settings.pending.device_id,sizeof(settings.pending.device_id));
  AppSettings_Scrub(settings.pending.workspace_id,sizeof(settings.pending.workspace_id));
  AppSettings_Scrub(settings.pending.token,sizeof(settings.pending.token));
  r=AppSettings_StoreCommit(&settings,&settings_io,APP_SETTINGS_WRITES_ENABLED); return settings_unlock(r);
}
#else
AppSettings_Result AppSettings_InitializeAndLoad(void) { return APP_SETTINGS_UNAVAILABLE; }
uint32_t AppSettings_WritesEnabled(void) { return 0U; }
uint32_t AppSettings_IsBusy(void) { return 0U; }
uint32_t AppSettings_IsIoActive(void) { return 0U; }
void AppSettings_Cancel(void) { }
uint32_t AppSettings_WifiUsesReference(void) { return 0U; }
AppSettings_Result AppSettings_PrepareCloudTransition(const char *s,uint32_t d)
{ (void)s;(void)d;return APP_SETTINGS_UNAVAILABLE; }
void AppSettings_GetStatus(AppSettings_Status *s) { if(s!=NULL){memset(s,0,sizeof(*s));s->result=APP_SETTINGS_UNAVAILABLE;} }
AppSettings_Result AppSettings_GetWifi(char s[APP_SETTINGS_SSID_CAP],char p[APP_SETTINGS_PASSWORD_CAP],uint32_t *d)
{ if(s)AppSettings_Scrub(s,APP_SETTINGS_SSID_CAP);if(p)AppSettings_Scrub(p,APP_SETTINGS_PASSWORD_CAP);if(d)*d=0U;return APP_SETTINGS_UNAVAILABLE; }
AppSettings_Result AppSettings_SaveWifi(const char *s,const char *p)
{ (void)s;(void)p;return APP_SETTINGS_UNAVAILABLE; }
AppSettings_Result AppSettings_DisconnectWifi(uint32_t f) { (void)f;return APP_SETTINGS_UNAVAILABLE; }
AppSettings_Result AppSettings_GetCloud(char d[APP_SETTINGS_ID_CAP],char w[APP_SETTINGS_ID_CAP],char t[APP_SETTINGS_TOKEN_CAP],uint32_t *e)
{ if(d)AppSettings_Scrub(d,APP_SETTINGS_ID_CAP);if(w)AppSettings_Scrub(w,APP_SETTINGS_ID_CAP);if(t)AppSettings_Scrub(t,APP_SETTINGS_TOKEN_CAP);if(e)*e=0U;return APP_SETTINGS_UNAVAILABLE; }
AppSettings_Result AppSettings_SaveCloud(const char *d,const char *w,const char *t,uint32_t e)
{ (void)d;(void)w;(void)t;(void)e;return APP_SETTINGS_UNAVAILABLE; }
AppSettings_Result AppSettings_ClearCloud(void) { return APP_SETTINGS_UNAVAILABLE; }
#endif
