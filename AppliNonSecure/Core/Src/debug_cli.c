#include "debug_cli.h"

#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "app_console.h"
#include "app_features.h"
#include "app_logging.h"
#include "logging_levels.h"
#include "main.h"
#include "tof_app.h"
#include "usb_cdc_transport.h"
#include "wifi_ble_app.h"
#if (APP_ST67W6X_ENABLED == 1U)
#include "w6x_api.h"
#endif

#define CLI_RX_CHUNK_SIZE       (64U)
#define CLI_LINE_SIZE           (192U)
#define CLI_PRINT_SIZE          (768U)
#define CLI_MAX_ARGUMENTS       (8)
#define CLI_WIFI_SCAN_MAX_APS   (15U)

static char cli_line[CLI_LINE_SIZE];
static size_t cli_line_length;
static char cli_print_buffer[CLI_PRINT_SIZE];
static uint32_t cli_console_mode;
static uint32_t cli_secret_mode;
static uint32_t cli_previous_was_cr;
#if (APP_ST67W6X_ENABLED == 1U)
static uint8_t cli_pending_ssid[W6X_WIFI_MAX_SSID_SIZE + 1U];
static volatile uint32_t cli_wifi_scan_active;
#endif

static void cli_process_byte(uint8_t byte);
static void cli_enter_console(void);
static void cli_execute_line(char *line);
static int cli_split_arguments(char *line, char *argv[], int max_arguments);
static void cli_print(const char *format, ...);
static void cli_prompt(void);
static void cli_show_help(void);
static void cli_show_status(void);
static void cli_show_tof_status(void);
static void cli_show_usb_status(void);
static const char *cli_tof_state_name(TOF_App_State_t state);
static const char *cli_radio_state_name(WifiBle_State_t state);
static const char *cli_log_level_name(uint32_t level);
#if (APP_ST67W6X_ENABLED == 1U)
static uint32_t cli_radio_is_ready(void);
static void cli_wifi_status(void);
static void cli_wifi_scan(void);
static void cli_wifi_connect_password(const char *password);
static void cli_wifi_scan_callback(int32_t status, W6X_WiFi_Scan_Result_t *results);
static void cli_ble_status(void);
#endif

void Debug_CLI_Run(void)
{
  uint8_t rx_buffer[CLI_RX_CHUNK_SIZE];

  for (;;)
  {
    ULONG actual_length = 0U;

    if (App_Console_IsReady() == 0U)
    {
      cli_console_mode = 0U;
      cli_secret_mode = 0U;
      cli_line_length = 0U;
      tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 10U);
      continue;
    }

    UINT status = App_Console_Read(rx_buffer, sizeof(rx_buffer), &actual_length);
    if (status != TX_SUCCESS)
    {
      tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 20U);
      continue;
    }

    for (ULONG i = 0U; i < actual_length; ++i)
    {
      cli_process_byte(rx_buffer[i]);
    }
  }
}

static void cli_process_byte(uint8_t byte)
{
  if ((byte == '\n') && (cli_previous_was_cr != 0U))
  {
    cli_previous_was_cr = 0U;
    return;
  }
  cli_previous_was_cr = (byte == '\r') ? 1U : 0U;

  if (cli_console_mode == 0U)
  {
    cli_enter_console();
    if ((byte == '\r') || (byte == '\n'))
    {
      return;
    }
  }

  if ((byte == '\r') || (byte == '\n'))
  {
    cli_print("\r\n");
    cli_line[cli_line_length] = '\0';

#if (APP_ST67W6X_ENABLED == 1U)
    if (cli_secret_mode != 0U)
    {
      cli_wifi_connect_password(cli_line);
      (void)memset(cli_line, 0, sizeof(cli_line));
      (void)memset(cli_pending_ssid, 0, sizeof(cli_pending_ssid));
      cli_line_length = 0U;
      cli_secret_mode = 0U;
      cli_prompt();
      return;
    }
#endif

    if (cli_line_length != 0U)
    {
      cli_execute_line(cli_line);
    }
    cli_line_length = 0U;
    if ((cli_console_mode != 0U) && (cli_secret_mode == 0U))
    {
      cli_prompt();
    }
    return;
  }

  if ((byte == 0x08U) || (byte == 0x7FU))
  {
    if (cli_line_length != 0U)
    {
      --cli_line_length;
      cli_line[cli_line_length] = '\0';
      if (cli_secret_mode == 0U)
      {
        cli_print("\b \b");
      }
    }
    return;
  }

  if (byte == 0x03U)
  {
    (void)memset(cli_line, 0, sizeof(cli_line));
    cli_line_length = 0U;
    cli_secret_mode = 0U;
#if (APP_ST67W6X_ENABLED == 1U)
    (void)memset(cli_pending_ssid, 0, sizeof(cli_pending_ssid));
#endif
    cli_print("^C\r\n");
    cli_prompt();
    return;
  }

  if ((byte >= 0x20U) && (byte <= 0x7EU) &&
      (cli_line_length < (sizeof(cli_line) - 1U)))
  {
    cli_line[cli_line_length++] = (char)byte;
    if (cli_secret_mode == 0U)
    {
      (void)App_Console_Write(&byte, 1U);
    }
  }
}

static void cli_enter_console(void)
{
  cli_console_mode = 1U;
  cli_line_length = 0U;
  cli_secret_mode = 0U;
  TOF_App_SetMapEnabled(0U);
  cli_print("\033[?25h\033[2J\033[H"
            "N6 sensor console - USB CDC\r\n"
            "The depth map is hidden; ranging is still active.\r\n"
            "Type 'help' for commands.\r\n\r\n");
  cli_prompt();
}

static void cli_execute_line(char *line)
{
  char *argv[CLI_MAX_ARGUMENTS];
  int argc = cli_split_arguments(line, argv, CLI_MAX_ARGUMENTS);

  if (argc == 0)
  {
    return;
  }

  if ((strcmp(argv[0], "help") == 0) || (strcmp(argv[0], "menu") == 0) ||
      (strcmp(argv[0], "?") == 0))
  {
    cli_show_help();
  }
  else if (strcmp(argv[0], "status") == 0)
  {
    cli_show_status();
  }
  else if ((strcmp(argv[0], "usb") == 0) && (argc == 2) &&
           (strcmp(argv[1], "status") == 0))
  {
    cli_show_usb_status();
  }
  else if (strcmp(argv[0], "clear") == 0)
  {
    cli_print("\033[2J\033[H");
  }
  else if (strcmp(argv[0], "map") == 0)
  {
    if ((argc == 2) && (strcmp(argv[1], "on") == 0))
    {
      cli_print("Depth map enabled. Press Enter to return to the console.\r\n");
      TOF_App_SetMapEnabled(1U);
      cli_console_mode = 0U;
    }
    else if ((argc == 2) && (strcmp(argv[1], "off") == 0))
    {
      TOF_App_SetMapEnabled(0U);
      cli_print("Depth map disabled; ranging remains active.\r\n");
    }
    else
    {
      cli_print("Usage: map on|off\r\n");
    }
  }
  else if (strcmp(argv[0], "tof") == 0)
  {
    if ((argc == 2) && (strcmp(argv[1], "status") == 0))
    {
      cli_show_tof_status();
    }
    else if ((argc == 2) && (strcmp(argv[1], "pause") == 0))
    {
      TOF_App_SetPaused(1U);
      cli_print("ToF autonomous stream paused.\r\n");
    }
    else if ((argc == 2) && (strcmp(argv[1], "resume") == 0))
    {
      TOF_App_SetPaused(0U);
      cli_print("ToF autonomous stream resumed.\r\n");
    }
    else
    {
      cli_print("Usage: tof status|pause|resume\r\n");
    }
  }
  else if (strcmp(argv[0], "debug") == 0)
  {
    uint32_t level = UINT32_MAX;
    if (argc != 2)
    {
      cli_print("Debug level: %s. Usage: debug off|error|warn|info|debug\r\n",
                cli_log_level_name(App_Logging_GetVerbosity()));
      return;
    }
    if (strcmp(argv[1], "off") == 0) level = LOG_NONE;
    else if (strcmp(argv[1], "error") == 0) level = LOG_ERROR;
    else if (strcmp(argv[1], "warn") == 0) level = LOG_WARN;
    else if (strcmp(argv[1], "info") == 0) level = LOG_INFO;
    else if (strcmp(argv[1], "debug") == 0) level = LOG_DEBUG;

    if (level == UINT32_MAX)
    {
      cli_print("Usage: debug off|error|warn|info|debug\r\n");
    }
    else
    {
      App_Logging_SetVerbosity(level);
      cli_print("ST67 log level set to %s.\r\n", cli_log_level_name(level));
    }
  }
#if (APP_ST67W6X_ENABLED == 1U)
  else if (strcmp(argv[0], "radio") == 0)
  {
    if ((argc == 2) && (strcmp(argv[1], "info") == 0))
    {
      if (cli_radio_is_ready() == 0U) return;
      W6X_ModuleInfo_t *info = W6X_GetModuleInfo();
      if (info != NULL)
      {
        cli_print("Module: %s (%s)\r\n"
                  "NCP MAC: %02X:%02X:%02X:%02X:%02X:%02X\r\n"
                  "Build: %.31s\r\n",
                  info->ModuleID.ModuleName,
                  W6X_ModelToStr(info->ModuleID.ModuleID),
                  info->Mac_Address[0], info->Mac_Address[1], info->Mac_Address[2],
                  info->Mac_Address[3], info->Mac_Address[4], info->Mac_Address[5],
                  info->Build_Date);
      }
    }
    else
    {
      cli_print("Usage: radio info\r\n");
    }
  }
  else if (strcmp(argv[0], "wifi") == 0)
  {
    if ((argc == 2) && (strcmp(argv[1], "status") == 0))
    {
      if (cli_radio_is_ready() == 0U) return;
      cli_wifi_status();
    }
    else if ((argc == 2) && (strcmp(argv[1], "scan") == 0))
    {
      if (cli_radio_is_ready() == 0U) return;
      cli_wifi_scan();
    }
    else if ((argc == 2) && (strcmp(argv[1], "connect") == 0))
    {
      cli_print("Usage: wifi connect \"SSID\"\r\n");
    }
    else if ((argc == 3) && (strcmp(argv[1], "connect") == 0))
    {
      if (cli_radio_is_ready() == 0U) return;
      size_t ssid_length = strlen(argv[2]);
      if ((ssid_length == 0U) || (ssid_length > W6X_WIFI_MAX_SSID_SIZE))
      {
        cli_print("Invalid SSID length.\r\n");
      }
      else
      {
        (void)memset(cli_pending_ssid, 0, sizeof(cli_pending_ssid));
        (void)memcpy(cli_pending_ssid, argv[2], ssid_length);
        cli_secret_mode = 1U;
        cli_line_length = 0U;
        cli_print("Password (input hidden): ");
      }
    }
    else if ((argc >= 2) && (strcmp(argv[1], "disconnect") == 0))
    {
      if (cli_radio_is_ready() == 0U) return;
      uint32_t forget = ((argc == 3) && (strcmp(argv[2], "forget") == 0)) ? 1U : 0U;
      W6X_Status_t status = W6X_WiFi_Disconnect(forget);
      cli_print("Wi-Fi disconnect: %s%s\r\n", W6X_StatusToStr(status),
                (forget != 0U) ? " (stored credentials removed)" : "");
    }
    else
    {
      cli_print("Usage: wifi status|scan|connect \"SSID\"|disconnect [forget]\r\n");
    }
  }
  else if (strcmp(argv[0], "ble") == 0)
  {
    if ((argc == 2) && (strcmp(argv[1], "status") == 0))
    {
      if (cli_radio_is_ready() == 0U) return;
      cli_ble_status();
    }
    else if ((argc == 3) && (strcmp(argv[1], "adv") == 0))
    {
      if (cli_radio_is_ready() == 0U) return;
      W6X_Status_t status;
      if (strcmp(argv[2], "on") == 0)
      {
        status = W6X_Ble_AdvStart();
        if (status == W6X_STATUS_OK) WIFI_BLE_App_SetAdvertisingState(1U);
      }
      else if (strcmp(argv[2], "off") == 0)
      {
        status = W6X_Ble_AdvStop();
        if (status == W6X_STATUS_OK) WIFI_BLE_App_SetAdvertisingState(0U);
      }
      else
      {
        cli_print("Usage: ble adv on|off\r\n");
        return;
      }
      cli_print("BLE advertising: %s\r\n", W6X_StatusToStr(status));
    }
    else if ((argc == 2) && (strcmp(argv[1], "disconnect") == 0))
    {
      if (cli_radio_is_ready() == 0U) return;
      WifiBle_RuntimeStatus_t runtime;
      WIFI_BLE_App_GetRuntimeStatus(&runtime);
      if (runtime.ble_connected == 0U)
      {
        cli_print("BLE is not connected.\r\n");
      }
      else
      {
        W6X_Status_t status = W6X_Ble_Disconnect(runtime.ble_connection_handle);
        cli_print("BLE disconnect: %s\r\n", W6X_StatusToStr(status));
      }
    }
    else
    {
      cli_print("Usage: ble status|adv on|adv off|disconnect\r\n");
    }
  }
#endif
  else if ((strcmp(argv[0], "reboot") == 0) && (argc == 2) &&
           (strcmp(argv[1], "yes") == 0))
  {
    cli_print("Rebooting...\r\n");
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 10U);
    NVIC_SystemReset();
  }
  else
  {
    cli_print("Unknown command. Type 'help'.\r\n");
  }
}

static int cli_split_arguments(char *line, char *argv[], int max_arguments)
{
  int argc = 0;
  char *cursor = line;

  while ((*cursor != '\0') && (argc < max_arguments))
  {
    while ((*cursor == ' ') || (*cursor == '\t')) ++cursor;
    if (*cursor == '\0') break;

    if (*cursor == '"')
    {
      ++cursor;
      argv[argc++] = cursor;
      while ((*cursor != '\0') && (*cursor != '"')) ++cursor;
    }
    else
    {
      argv[argc++] = cursor;
      while ((*cursor != '\0') && (*cursor != ' ') && (*cursor != '\t')) ++cursor;
    }

    if (*cursor != '\0') *cursor++ = '\0';
  }
  return argc;
}

static void cli_print(const char *format, ...)
{
  va_list args;
  va_start(args, format);
  int length = vsnprintf(cli_print_buffer, sizeof(cli_print_buffer), format, args);
  va_end(args);

  if (length > 0)
  {
    ULONG send_length = (ULONG)length;
    if (send_length >= sizeof(cli_print_buffer)) send_length = sizeof(cli_print_buffer) - 1U;
    (void)App_Console_Write(cli_print_buffer, send_length);
  }
}

static void cli_prompt(void)
{
  cli_print("n6> ");
}

static void cli_show_help(void)
{
  cli_print("Commands:\r\n"
            "  (Press Enter while the map is visible to open this console.)\r\n"
            "  status                         system summary\r\n"
            "  usb status                     USB queues, pool, flow/error counters\r\n"
            "  map on|off                     show/hide the color depth map\r\n"
            "  tof status|pause|resume        inspect/control ranging\r\n"
            "  debug off|error|warn|info|debug ST67 runtime log level\r\n"
#if (APP_ST67W6X_ENABLED == 1U)
            "  radio info                     ST67 module identity\r\n"
            "  wifi status|scan               Wi-Fi state and nearby networks\r\n"
            "  wifi connect \"SSID\"          connect; password is requested hidden\r\n"
            "  wifi disconnect [forget]       disconnect, optionally erase credentials\r\n"
            "  ble status|adv on|adv off       BLE state and advertising\r\n"
            "  ble disconnect                 disconnect current BLE peer\r\n"
#endif
            "  clear                          clear terminal\r\n"
            "  reboot yes                     reset the STM32\r\n");
}

static void cli_show_status(void)
{
  TOF_App_Status_t tof;
  WifiBle_RuntimeStatus_t radio;
  USB_CDC_TransportStatus_t usb;
  TOF_App_GetStatus(&tof);
  WIFI_BLE_App_GetRuntimeStatus(&radio);
  USB_CDC_Transport_GetStatus(&usb);

  cli_print("Uptime: %" PRIu32 " ms\r\n"
            "USB CDC: %s, session %lu, TX queue %lu, RX queue %lu\r\n"
            "ToF: %s, map %s, frame %" PRIu32 ", %" PRIu32 ".%" PRIu32 " fps\r\n"
            "ST67: %s, Wi-Fi %s, BLE %s, advertising %s\r\n"
            "Log level: %s\r\n",
            HAL_GetTick(), (usb.active != 0U) ? "active" : "inactive",
            (unsigned long)usb.session,
            (unsigned long)usb.tx_queue_depth,
            (unsigned long)usb.rx_queue_depth,
            cli_tof_state_name(tof.state),
            (tof.map_enabled != 0U) ? "on" : "off", tof.frame_counter,
            tof.fps_x10 / 10U, tof.fps_x10 % 10U,
            cli_radio_state_name(radio.state),
            (radio.wifi_connected != 0U) ? ((radio.wifi_has_ip != 0U) ? "IP ready" : "connected") : "disconnected",
            (radio.ble_connected != 0U) ? "connected" : "disconnected",
            (radio.ble_advertising != 0U) ? "on" : "off",
            cli_log_level_name(App_Logging_GetVerbosity()));
}

static void cli_show_usb_status(void)
{
  USB_CDC_TransportStatus_t status;

  USB_CDC_Transport_GetStatus(&status);
  cli_print("USB CDC transport: %s, session %lu\r\n"
            "Static slots free: control %lu/8, maps %lu/2, RX %lu/16\r\n"
            "Queues: TX %lu/10, RX %lu/32, in-flight %lu\r\n"
            "TX: queued %lu, completed %lu, callbacks %lu, bytes %lu\r\n"
            "TX flow: dropped %lu, unavailable %lu, slot exhaustion %lu, queue failures %lu\r\n"
            "TX errors: callback timeouts %lu, errors %lu, last %lu\r\n"
            "RX: received %lu, delivered %lu, bytes %lu\r\n"
            "RX flow/errors: dropped %lu, slot exhaustion %lu, queue failures %lu, errors %lu, last %lu\r\n"
            "Worker synchronization failures: %lu\r\n",
            (status.active != 0U) ? "active" : "inactive",
            (unsigned long)status.session,
            (unsigned long)status.tx_control_slots_free,
            (unsigned long)status.tx_map_slots_free,
            (unsigned long)status.rx_slots_free,
            (unsigned long)status.tx_queue_depth,
            (unsigned long)status.rx_queue_depth,
            (unsigned long)status.tx_in_flight,
            (unsigned long)status.tx_packets_queued,
            (unsigned long)status.tx_packets_completed,
            (unsigned long)status.tx_callback_completions,
            (unsigned long)status.tx_bytes_completed,
            (unsigned long)status.tx_packets_dropped,
            (unsigned long)status.tx_unavailable_drops,
            (unsigned long)status.tx_slot_exhaustions,
            (unsigned long)status.tx_queue_failures,
            (unsigned long)status.tx_callback_timeouts,
            (unsigned long)status.tx_errors,
            (unsigned long)status.tx_last_error,
            (unsigned long)status.rx_packets_received,
            (unsigned long)status.rx_packets_delivered,
            (unsigned long)status.rx_bytes_received,
            (unsigned long)status.rx_packets_dropped,
            (unsigned long)status.rx_slot_exhaustions,
            (unsigned long)status.rx_queue_failures,
            (unsigned long)status.rx_errors,
            (unsigned long)status.rx_last_error,
            (unsigned long)status.worker_sync_failures);
}

static void cli_show_tof_status(void)
{
  TOF_App_Status_t status;
  TOF_App_GetStatus(&status);
  cli_print("ToF state: %s\r\n"
            "Resolution: %" PRIu32 "x%" PRIu32 "\r\n"
            "Frame: %" PRIu32 ", rate: %" PRIu32 ".%" PRIu32 " fps\r\n"
            "Pipeline: acquired %" PRIu32 ", processed %" PRIu32 ", dropped %" PRIu32 ", queue failures %" PRIu32 "\r\n"
            "Last valid range: %" PRIu32 "..%" PRIu32 " mm\r\n"
            "Map: %s, acquisition: %s\r\n",
            cli_tof_state_name(status.state), status.width, status.height,
            status.frame_counter, status.fps_x10 / 10U, status.fps_x10 % 10U,
            status.acquired_frames, status.processed_frames,
            status.dropped_frames, status.queue_failures,
            status.minimum_mm, status.maximum_mm,
            (status.map_enabled != 0U) ? "on" : "off",
            (status.paused != 0U) ? "paused" : "running");
  if (status.state == TOF_APP_STATE_ERROR)
  {
    cli_print("Last error: %s (%d)\r\n",
              (status.error_stage != NULL) ? status.error_stage : "unknown",
              status.error_code);
  }
}

static const char *cli_tof_state_name(TOF_App_State_t state)
{
  switch (state)
  {
    case TOF_APP_STATE_STARTING: return "starting";
    case TOF_APP_STATE_READY: return "ready";
    case TOF_APP_STATE_PAUSED: return "paused";
    case TOF_APP_STATE_ERROR: return "error";
    default: return "unknown";
  }
}

static const char *cli_radio_state_name(WifiBle_State_t state)
{
  switch (state)
  {
    case WIFI_BLE_STATE_DISABLED: return "disabled";
    case WIFI_BLE_STATE_STARTING: return "starting";
    case WIFI_BLE_STATE_READY: return "ready";
    case WIFI_BLE_STATE_ERROR: return "error";
    default: return "unknown";
  }
}

static const char *cli_log_level_name(uint32_t level)
{
  switch (level)
  {
    case LOG_NONE: return "off";
    case LOG_ERROR: return "error";
    case LOG_WARN: return "warn";
    case LOG_INFO: return "info";
    case LOG_DEBUG: return "debug";
    default: return "unknown";
  }
}

#if (APP_ST67W6X_ENABLED == 1U)
static uint32_t cli_radio_is_ready(void)
{
  if (WIFI_BLE_App_GetState() != WIFI_BLE_STATE_READY)
  {
    cli_print("ST67 is not ready (state: %s).\r\n",
              cli_radio_state_name(WIFI_BLE_App_GetState()));
    return 0U;
  }
  return 1U;
}

static void cli_wifi_status(void)
{
  W6X_WiFi_StaStateType_e state = W6X_WIFI_STATE_STA_DISCONNECTED;
  W6X_WiFi_Connect_t connection = {0};
  W6X_Status_t status = W6X_WiFi_Station_GetState(&state, &connection);
  if (status != W6X_STATUS_OK)
  {
    cli_print("Wi-Fi status failed: %s\r\n", W6X_StatusToStr(status));
    return;
  }

  cli_print("Wi-Fi station: %s\r\n", W6X_WiFi_StateToStr(state));
  if ((state == W6X_WIFI_STATE_STA_CONNECTED) || (state == W6X_WIFI_STATE_STA_GOT_IP))
  {
    cli_print("SSID: %s, channel: %" PRIu32 ", RSSI: %" PRIi32 " dBm\r\n"
              "AP: %02X:%02X:%02X:%02X:%02X:%02X\r\n",
              connection.SSID, connection.Channel, connection.Rssi,
              connection.MAC[0], connection.MAC[1], connection.MAC[2],
              connection.MAC[3], connection.MAC[4], connection.MAC[5]);
  }
}

static void cli_wifi_scan(void)
{
  W6X_WiFi_Scan_Opts_t options = {0};
  if (cli_wifi_scan_active != 0U)
  {
    cli_print("A Wi-Fi scan is already running.\r\n");
    return;
  }
  options.Scan_type = W6X_WIFI_SCAN_ACTIVE;
  options.MaxCnt = CLI_WIFI_SCAN_MAX_APS;
  cli_wifi_scan_active = 1U;
  W6X_Status_t status = W6X_WiFi_Scan(&options, cli_wifi_scan_callback);
  if (status != W6X_STATUS_OK)
  {
    cli_wifi_scan_active = 0U;
    cli_print("Wi-Fi scan failed to start: %s\r\n", W6X_StatusToStr(status));
  }
  else
  {
    cli_print("Wi-Fi scan started; results will follow asynchronously.\r\n");
  }
}

static void cli_wifi_connect_password(const char *password)
{
  W6X_WiFi_Connect_Opts_t options = {0};
  size_t password_length = strlen(password);
  if (password_length > W6X_WIFI_MAX_PASSWORD_SIZE)
  {
    cli_print("Password is too long.\r\n");
    return;
  }
  (void)memcpy(options.SSID, cli_pending_ssid, sizeof(cli_pending_ssid));
  (void)memcpy(options.Password, password, password_length);
  W6X_Status_t status = W6X_WiFi_Connect(&options);
  (void)memset(&options, 0, sizeof(options));
  cli_print("Wi-Fi connect request: %s. Use 'wifi status' to follow it.\r\n",
            W6X_StatusToStr(status));
}

static void cli_wifi_scan_callback(int32_t status, W6X_WiFi_Scan_Result_t *results)
{
  cli_wifi_scan_active = 0U;
  cli_print("\r\nWi-Fi scan complete (status %" PRIi32 ").\r\n", status);
  if ((status != (int32_t)W6X_STATUS_OK) || (results == NULL) || (results->AP == NULL))
  {
    cli_print("No scan results available.\r\nn6> ");
    return;
  }

  cli_print("%-4s %-5s %-5s %s\r\n", "CH", "RSSI", "MODE", "SSID");
  for (uint32_t i = 0U; i < results->Count; ++i)
  {
    cli_print("%-4u %-5d %-5s %s\r\n",
              (unsigned int)results->AP[i].Channel,
              (int)results->AP[i].RSSI,
              W6X_WiFi_ProtocolToStr(results->AP[i].Protocol),
              results->AP[i].SSID);
  }
  cli_print("n6> ");
}

static void cli_ble_status(void)
{
  WifiBle_RuntimeStatus_t runtime;
  char name[W6X_BLE_DEVICE_NAME_SIZE] = {0};
  uint8_t address[6] = {0};
  WIFI_BLE_App_GetRuntimeStatus(&runtime);

  W6X_Status_t name_status = W6X_Ble_GetDeviceName(name);
  W6X_Status_t address_status = W6X_Ble_GetBDAddress(address);
  cli_print("BLE: %s, advertising: %s\r\n",
            (runtime.ble_connected != 0U) ? "connected" : "disconnected",
            (runtime.ble_advertising != 0U) ? "on" : "off");
  if (name_status == W6X_STATUS_OK) cli_print("Name: %s\r\n", name);
  if (address_status == W6X_STATUS_OK)
  {
    cli_print("Address: %02X:%02X:%02X:%02X:%02X:%02X\r\n",
              address[0], address[1], address[2], address[3], address[4], address[5]);
  }
}
#endif
