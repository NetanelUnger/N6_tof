from pathlib import Path
import sys
sys.path.insert(0,str(Path('hil_tests').resolve()))
from test_cli_reply_ownership import function
def read(p):return Path(p).read_text(encoding='utf-8')
def write(p,s):Path(p).write_text(s,encoding='utf-8',newline='\r\n')
wpath='AppliNonSecure/Core/Src/wifi_ble_app.c'
w=read(wpath).replace('#include "app_cli_reply.h"','#include "app_cli_reply.h"\n#include "app_settings.h"',1)
w=w.replace('static uint8_t wifi_desired_ssid[W6X_WIFI_MAX_SSID_SIZE + 1U];','static uint8_t wifi_desired_ssid[W6X_WIFI_MAX_SSID_SIZE + 1U];\nstatic uint32_t wifi_unified_settings;',1)
old=function(w,'wifi_remember_connection')
new=old.replace('W6X_Status_t saved = W6X_WiFi_AddCredentials(options->SSID, options->Password);','AppSettings_Result saved = AppSettings_SaveWifi((const char *)options->SSID,\n                                                 (const char *)options->Password);')
new=new.replace('(void)memset(options->Password, 0, sizeof(options->Password));','AppSettings_Scrub(options->Password, sizeof(options->Password));')
new=new.replace('(saved == W6X_STATUS_OK)', '(saved == APP_SETTINGS_OK)')
new=new.replace('  Debug_UART_Log(', '  wifi_unified_settings = wifi_credentials_saved;\n  Debug_UART_Log(',1)
w=w.replace(old,new)
old=function(w,'wifi_restore_connection')
new=old.replace('  options.Secured = 1U; /* CWJAPS: fetch password inside NCP; never fetch it into SRAM. */','''  if (wifi_unified_settings)
  {
    uint32_t desired = 0U;
    AppSettings_Result loaded = AppSettings_GetWifi((char *)options.SSID,
                                                   (char *)options.Password, &desired);
    if (loaded != APP_SETTINGS_OK || !desired ||
        memcmp(options.SSID, wifi_desired_ssid, sizeof(options.SSID)))
    {
      AppSettings_Scrub(&options, sizeof(options));
      Debug_UART_Log("RADIO-RECOVERY", "Wi-Fi settings unavailable result=%ld", (long)loaded);
      return;
    }
    options.Secured = 0U; /* Existing CWJAP personal/open authentication. */
  }
  else options.Secured = 1U; /* Retained legacy NCP credential reference only. */''')
new=new.replace('(void)memset(&options, 0, sizeof(options));','AppSettings_Scrub(&options, sizeof(options));')
w=w.replace(old,new)
old=function(w,'wifi_forget_connection')
new='''static W6X_Status_t wifi_forget_connection(uint32_t forget)
{
  /* Volatile cancellation always applies, including a failed persistent save. */
  wifi_connection_desired = 0U;
  radio_recovery.wifi_reconnect_required = 0U;
  AppSettings_Result saved = AppSettings_DisconnectWifi(forget);
  Debug_UART_Log("WIFI-SETTINGS", "disconnect store result=%ld forget=%lu", (long)saved,
                 (unsigned long)forget);
  if (saved != APP_SETTINGS_OK) return W6X_STATUS_ERROR;
  if (forget)
  {
    wifi_credentials_saved = wifi_unified_settings = 0U;
    AppSettings_Scrub(wifi_desired_ssid, sizeof(wifi_desired_ssid));
  }
  return W6X_STATUS_OK;
}'''
w=w.replace(old,new)
w=w.replace('      driver->Modem.handler_data.dns_drain_active || driver->Modem.notify_phase)',
            '      driver->Modem.handler_data.dns_drain_active || driver->Modem.notify_phase ||\n      AppSettings_IsBusy())',1)
w=w.replace('    status = W6X_WiFi_Disconnect(request->forget);','    /* Persistent removal is handled only by the settings owner above. */\n    status = W6X_WiFi_Disconnect(0U);',1)
needle='#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)\n  if ((cloud_net_ready != 0U)'
assert needle in w
w=w.replace(needle,'''#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  AppSettings_Result settings_result = AppSettings_InitializeAndLoad();
  W6X_WiFi_Connect_Opts_t saved_options = {0};
  uint32_t saved_desired = 0U;
  if (settings_result == APP_SETTINGS_OK &&
      AppSettings_GetWifi((char *)saved_options.SSID, (char *)saved_options.Password,
                          &saved_desired) == APP_SETTINGS_OK)
  {
    memcpy(wifi_desired_ssid, saved_options.SSID, sizeof(wifi_desired_ssid));
    wifi_connection_desired = saved_desired;
    wifi_credentials_saved = wifi_unified_settings = 1U;
  }
  AppSettings_Scrub(&saved_options, sizeof(saved_options));
  Debug_UART_Log("NCP-SETTINGS", "load result=%ld writes=%lu", (long)settings_result,
                 (unsigned long)AppSettings_WritesEnabled());
#endif

'''+needle,1)
write(wpath,w)
cpath='AppliNonSecure/Core/Src/cloud_relay.c'
c=read(cpath).replace('#include "app_cli_reply.h"','#include "app_cli_reply.h"\n#include "app_settings.h"',1)
# A mutable, by-value request retains its completed tombstone phase while a
# concurrent CLI lease holds the Cloud gate. No FS operation holds that gate.
c=c.replace('cloud_apply_control(const CloudControlRequest_t *request)','cloud_apply_control(CloudControlRequest_t *request)')
old=function(c,'cloud_apply_control')
new=old.replace('  uint32_t delete_file = 0U;', '''  if (request->kind == CLOUD_CONTROL_UNPAIR && request->value == 0U)
  {
    AppSettings_Result result = AppSettings_ClearCloud();
    if (result == APP_SETTINGS_BUSY) return TX_NOT_AVAILABLE;
    if (result != APP_SETTINGS_OK)
    {
      Debug_UART_Log("CLOUD-CONFIG", "unpair rejected: store result=%ld", (long)result);
      cloud->status.request_errors++;
      cloud_publish_status();
      return TX_SUCCESS; /* terminal failure, consume request without clearing pairing */
    }
    request->value = 1U; /* committed once, even if the gate is temporarily busy */
  }''')
new=new.replace('      delete_file = 1U;','')
new=new.replace('  if (save != 0U) (void)cloud_save_pairing();','  if (save != 0U && cloud_save_pairing() != 0) cloud->status.request_errors++;')
new=new.replace('  if (delete_file != 0U) (void)W6X_FS_DeleteFile(cloud_pair_file);','  cloud_publish_status();')
c=c.replace(old,new)
old=function(c,'CloudRelay_RequestPair')
new=old.replace('  size_t length;','''  AppSettings_Status settings_status;
  AppSettings_GetStatus(&settings_status);
  if (!AppSettings_WritesEnabled() ||
      (settings_status.result != APP_SETTINGS_OK && settings_status.result != APP_SETTINGS_ABSENT))
    return TX_NOT_AVAILABLE; /* no provisioning exchange without an approved writable store */
  size_t length;''')
c=c.replace(old,new)
old=function(c,'CloudRelay_Unpair')
new=old.replace('  CloudControlRequest_t request','  if (!AppSettings_WritesEnabled()) return TX_NOT_AVAILABLE;\n  CloudControlRequest_t request',1)
c=c.replace(old,new)
old=function(c,'cloud_load_pairing')
new=old.replace('  uint32_t crc;','''  uint32_t crc;
  AppSettings_Scrub(&cloud->pairing, sizeof(cloud->pairing));
  AppSettings_Result loaded = AppSettings_GetCloud(cloud->pairing.device_id,
      cloud->pairing.workspace_id, cloud->pairing.token, &cloud->pairing.enabled);
  if (loaded == APP_SETTINGS_OK)
  {
    cloud->pairing.magic = CLOUD_RECORD_MAGIC;
    cloud->pairing.version = CLOUD_RECORD_VERSION;
    cloud->pairing.length = sizeof(cloud->pairing);
    cloud->pairing.crc32 = cloud_crc32(&cloud->pairing, sizeof(cloud->pairing));
    goto accepted;
  }
  /* A validated unified tombstone is authoritative. Only inventory-proven
   * legacy-only storage may use the strict old binary read, without migration. */
  if (loaded != APP_SETTINGS_LEGACY)
  {
    Debug_UART_Log("CLOUD-CONFIG", "unified load result=%ld", (long)loaded);
    cloud_clear_pairing(0U);
    return -1;
  }''')
new=new.replace('  cloud->status.enabled = cloud->pairing.enabled;','accepted:\n  cloud->status.enabled = cloud->pairing.enabled;',1)
c=c.replace(old,new)
old=function(c,'cloud_save_pairing')
new='''static int cloud_save_pairing(void)
{
  AppSettings_Result saved = AppSettings_SaveCloud(cloud->pairing.device_id,
      cloud->pairing.workspace_id, cloud->pairing.token, cloud->status.enabled);
  Debug_UART_Log("CLOUD-CONFIG", "unified save result=%ld verified=%lu", (long)saved,
                 (unsigned long)(saved == APP_SETTINGS_OK));
  return saved == APP_SETTINGS_OK ? 0 : -1;
}'''
c=c.replace(old,new)
c=c.replace('  if (delete_file != 0U) (void)W6X_FS_DeleteFile(cloud_pair_file);',
            '  (void)delete_file; /* legacy records are never removed implicitly */')
c=c.replace('        (void)cloud_save_pairing();','        if (cloud_save_pairing() != 0) cloud->status.request_errors++;',1)
write(cpath,c)
