#ifndef APP_SETTINGS_H
#define APP_SETTINGS_H

#include <stddef.h>
#include <stdint.h>

/* Personal/open Wi-Fi uses SSID/password, not an enterprise username. */
#define APP_SETTINGS_SSID_CAP 33U
#define APP_SETTINGS_PASSWORD_CAP 64U
#define APP_SETTINGS_ID_CAP 65U
#define APP_SETTINGS_TOKEN_CAP 1025U
#define APP_SETTINGS_VERSION 1U
#define APP_SETTINGS_TEXT_MAX 2561U
#define APP_SETTINGS_WIFI_PRESENT 1U
#define APP_SETTINGS_WIFI_DESIRED 2U
#define APP_SETTINGS_CLOUD_PRESENT 4U
#define APP_SETTINGS_CLOUD_ENABLED 8U
/* Explicit reference is different from an open-network empty password.
 * Old readers reject this reserved flag as unsupported, never as open Wi-Fi. */
#define APP_SETTINGS_WIFI_REFERENCE 16U
#define APP_SETTINGS_FLAGS_ALL 31U
#define APP_SETTINGS_SLOT_0 "n6settings0.cfg"
#define APP_SETTINGS_SLOT_1 "n6settings1.cfg"

/* Product profile: verified alternating-slot persistence is enabled.
 * Legacy-only or invalid storage still requires explicit recovery/preparation. */
#ifndef APP_SETTINGS_WRITES_ENABLED
#define APP_SETTINGS_WRITES_ENABLED 1U
#endif
/* RAM-only, explicit user preparation; never automatic legacy migration. */
#ifndef APP_SETTINGS_TRANSITION_ENABLED
#define APP_SETTINGS_TRANSITION_ENABLED 1U
#endif

typedef enum {
  APP_SETTINGS_OK = 0, APP_SETTINGS_ABSENT, APP_SETTINGS_LEGACY,
  APP_SETTINGS_CORRUPT, APP_SETTINGS_IO, APP_SETTINGS_BUSY,
  APP_SETTINGS_READ_ONLY, APP_SETTINGS_INVALID, APP_SETTINGS_UNAVAILABLE,
  APP_SETTINGS_UNSUPPORTED
} AppSettings_Result;

typedef struct {
  uint16_t version, length; /* schema and exact serialized length, not sizeof */
  uint32_t generation, flags, crc32;
  uint16_t ssid_length, password_length, device_length, workspace_length, token_length;
  char ssid[APP_SETTINGS_SSID_CAP];
  char password[APP_SETTINGS_PASSWORD_CAP];
  char device_id[APP_SETTINGS_ID_CAP], workspace_id[APP_SETTINGS_ID_CAP];
  char token[APP_SETTINGS_TOKEN_CAP];
} AppSettings_Record;

void AppSettings_Scrub(void *data, size_t size);
AppSettings_Result AppSettings_Encode(const AppSettings_Record *record,
    char *text, size_t capacity, size_t *length);
AppSettings_Result AppSettings_Decode(const char *text, size_t length,
    AppSettings_Record *record);

/* Metadata only: never expose settings arrays in diagnostics. */
typedef struct {
  AppSettings_Result result;
  uint32_t generation, flags, writes_enabled;
  uint32_t stage, elapsed_ms, remaining_ms;
} AppSettings_Status;

AppSettings_Result AppSettings_InitializeAndLoad(void); /* initial Radio owner */
void AppSettings_GetStatus(AppSettings_Status *status);
uint32_t AppSettings_WritesEnabled(void);
uint32_t AppSettings_IsBusy(void);
uint32_t AppSettings_IsIoActive(void); /* fresh BLE admission only; owned replies still drain */
void AppSettings_Cancel(void); /* no mutex wait; retire generation, never clear a fence */
AppSettings_Result AppSettings_GetWifi(char ssid[APP_SETTINGS_SSID_CAP],
    char password[APP_SETTINGS_PASSWORD_CAP], uint32_t *desired);
uint32_t AppSettings_WifiUsesReference(void);
/* Requires validated retained-reference intent, complete inventory and absent
 * managed slots. Seeds RAM only; first new pairing commit supplies Cloud fields. */
AppSettings_Result AppSettings_PrepareCloudTransition(const char *ssid, uint32_t desired);
AppSettings_Result AppSettings_SaveWifi(const char *ssid, const char *password);
AppSettings_Result AppSettings_DisconnectWifi(uint32_t forget);
AppSettings_Result AppSettings_GetCloud(char device[APP_SETTINGS_ID_CAP],
    char workspace[APP_SETTINGS_ID_CAP], char token[APP_SETTINGS_TOKEN_CAP], uint32_t *enabled);
AppSettings_Result AppSettings_SaveCloud(const char *device, const char *workspace,
    const char *token, uint32_t enabled);
AppSettings_Result AppSettings_ClearCloud(void);

#endif
