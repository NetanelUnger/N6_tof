#include "debug_cli.h"

#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "app_console.h"
#include "app_features.h"
#include "app_logging.h"
#include "app_route.h"
#include "cloud_relay.h"
#include "debug_uart.h"
#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
#include "display_app.h"
#endif
#include "firmware_update.h"
#include "firmware_build_version.h"
#include "logging_levels.h"
#include "main.h"
#include "menu.h"
#include "rps_ai.h"
#include "tof_app.h"
#include "vl53l9_interface.h"
#include "usb_cdc_transport.h"
#include "wifi_ble_app.h"
#if (APP_ST67W6X_ENABLED == 1U)
#include "w6x_api.h"
#endif

#define CLI_RX_CHUNK_SIZE       (64U)
#define CLI_BLE_RX_CHUNK_SIZE   (512U)
#define CLI_LINE_SIZE           (192U)
#define CLI_PRINT_SIZE          (768U)
#define CLI_MAX_ARGUMENTS       (8)
#define CLI_HISTORY_DEPTH       (16U)
#define CLI_BLE_RX_BURST        (8U)
#define CLI_BLE_TX_WAIT_TICKS   (TX_TIMER_TICKS_PER_SECOND / 20U)
#define CLI_WIFI_RESULTS_PER_POLL (2U)
#define CLI_WIFI_DEFERRED_RESULTS (4U)

typedef enum
{
  CLI_SECRET_NONE = 0,
  CLI_SECRET_WIFI_PASSWORD
} CliSecretMode_t;

typedef struct
{
  char print_buffer[CLI_PRINT_SIZE];
  char menu_input[CLI_LINE_SIZE];
  char menu_reply[CLI_PRINT_SIZE];
  Menu_t menu;
  uint32_t console_mode;
  CliSecretMode_t secret_mode;
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  uint8_t pending_ssid[W6X_WIFI_MAX_SSID_SIZE + 1U];
  char pending_password[W6X_WIFI_MAX_PASSWORD_SIZE + 1U];
  size_t pending_password_length;
#endif
  uint32_t previous_was_cr;
  uint32_t first_input_logged;
  uint32_t session_ready;
  uint32_t prompt_already_sent;
  char history[CLI_HISTORY_DEPTH][CLI_LINE_SIZE];
  char history_draft[CLI_LINE_SIZE];
  size_t history_count;
  size_t history_index;
  uint32_t escape_state;
  AppRoute_t route;
} CliSession_t;

typedef struct
{
  uint32_t available;
  uint32_t reset_changes_generation;
  uint32_t saved_route_becomes_stale;
  uint32_t credential_isolation;
  uint32_t cancel_is_scoped;
  uint32_t reset_is_scoped;
} CliM2Diagnostic_t;

/* Keep the Cloud session in its dedicated SRAM4 section. */
typedef struct { CliSession_t session; } CliCloudStorage_t;
static CliCloudStorage_t cli_cloud_storage
    __attribute__((section(".cloud_shared_bss"), aligned(8), used));

typedef struct
{
  struct
  {
    volatile uint32_t started;
    volatile uint32_t cycles;
    volatile uint32_t last_tick;
  } thread;
  struct
  {
    CliSession_t usb;
    CliSession_t *cloud;
    CliSession_t *ble;
    CliSession_t *active;
    CliSession_t *update;
  } sessions;
  struct
  {
    uint32_t cloud_command_active;
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    AppRequestId_t cloud_wifi_request_id;
    WifiBle_WifiResult_t wifi_deferred[CLI_WIFI_DEFERRED_RESULTS];
    uint8_t wifi_deferred_valid[CLI_WIFI_DEFERRED_RESULTS];
#endif
  } work;
  struct
  {
    CliM2Diagnostic_t m2_diagnostic;
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    uint32_t wifi_results_routed;
    uint32_t wifi_results_stale;
    uint32_t wifi_result_write_errors;
    uint32_t wifi_results_deferred_overflow;
#endif
  } counters;
} CliContext_t;

static CliContext_t cli_context;

void Debug_CLI_GetStatus(Debug_CLI_Status_t *status)
{
  if (status == NULL)
  {
    return;
  }
  status->started = cli_context.thread.started;
  status->cycles = cli_context.thread.cycles;
  status->last_tick = cli_context.thread.last_tick;
  status->usb_session_ready = cli_context.sessions.usb.session_ready;
  status->ble_session_ready = (cli_context.sessions.ble != NULL) ?
                              cli_context.sessions.ble->session_ready : 0U;
  status->cloud_session_ready = (cli_context.sessions.cloud != NULL) ?
                                cli_context.sessions.cloud->session_ready : 0U;
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  status->wifi_results_routed = cli_context.counters.wifi_results_routed;
  status->wifi_results_stale = cli_context.counters.wifi_results_stale;
  status->wifi_result_write_errors = cli_context.counters.wifi_result_write_errors;
#else
  status->wifi_results_routed = 0U;
  status->wifi_results_stale = 0U;
  status->wifi_result_write_errors = 0U;
#endif
}

#define cli_usb_session cli_context.sessions.usb
#define cli_cloud_session (*cli_context.sessions.cloud)
#define cli_ble_session cli_context.sessions.ble
#define cli_active_session cli_context.sessions.active
#define cli_update_session cli_context.sessions.update
#define cli_cloud_command_active cli_context.work.cloud_command_active
#define cli_m2_diagnostic cli_context.counters.m2_diagnostic
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
#define cli_cloud_wifi_request_id cli_context.work.cloud_wifi_request_id
#define cli_wifi_results_routed cli_context.counters.wifi_results_routed
#define cli_wifi_results_stale cli_context.counters.wifi_results_stale
#define cli_wifi_result_write_errors cli_context.counters.wifi_result_write_errors
#define cli_wifi_results_deferred_overflow cli_context.counters.wifi_results_deferred_overflow
#define cli_wifi_deferred cli_context.work.wifi_deferred
#define cli_wifi_deferred_valid cli_context.work.wifi_deferred_valid
#endif
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
extern TX_BYTE_POOL *MX_RadioBytePool_Get(void);
#endif

/* The command implementation below remains intentionally transport-agnostic.
 * These aliases bind all editor/parser state to the session currently being
 * serviced by the single CLI broker thread. */
#define cli_print_buffer       (cli_active_session->print_buffer)
#define cli_menu_input         (cli_active_session->menu_input)
#define cli_menu_reply         (cli_active_session->menu_reply)
#define cli_menu               (cli_active_session->menu)
#define cli_console_mode       (cli_active_session->console_mode)
#define cli_secret_mode        (cli_active_session->secret_mode)
#define cli_previous_was_cr    (cli_active_session->previous_was_cr)
#define cli_first_input_logged (cli_active_session->first_input_logged)
#define cli_cdc_session_ready  (cli_active_session->session_ready)
#define cli_prompt_already_sent (cli_active_session->prompt_already_sent)
#define cli_history            (cli_active_session->history)
#define cli_history_draft      (cli_active_session->history_draft)
#define cli_history_count      (cli_active_session->history_count)
#define cli_history_index      (cli_active_session->history_index)
#define cli_escape_state       (cli_active_session->escape_state)
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
#define cli_pending_password   (cli_active_session->pending_password)
#define cli_pending_password_length \
    (cli_active_session->pending_password_length)
#endif

static void cli_process_byte(uint8_t byte);
static void cli_enter_console(void);
static Menu_Status_t cli_session_init(CliSession_t *session,
                                      AppTransport_t transport);
static UINT cli_session_write(CliSession_t *session, const void *buffer,
                              ULONG length);
static int32_t cli_update_write(const void *buffer, size_t length,
                                void *context);
static void cli_session_reset(CliSession_t *session, uint32_t stop_usb_streams);
static uint32_t cli_next_generation(uint32_t generation);
static uint32_t cli_route_is_current(const AppRoute_t *current,
                                     const AppRoute_t *saved);
static const char *cli_transport_name(AppTransport_t transport);
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
static void cli_poll_wifi_results(void);
static UINT cli_wifi_result_print(const char *format, ...);
static uint32_t cli_wifi_result_deliver(WifiBle_WifiResult_t *result);
static void cli_wifi_result_defer(const WifiBle_WifiResult_t *result);
static void cli_wifi_note_submission(AppRequestId_t request_id);
#endif
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static void __attribute__((optimize("Os"))) cli_poll_ble(void);
static uint32_t cli_ble_session_allocate(void);
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
static void cli_poll_cloud(void);
#endif
static int cli_split_arguments(char *line, char *argv[], int max_arguments);
static int cli_get_arguments(const char *command, char *copy,
                             size_t copy_size, char *argv[],
                             int max_arguments);
static int32_t cli_menu_send(const char *text, size_t length, void *context);
static uint32_t cli_token_equals(const char *left, const char *right);
static uint32_t cli_prefix_matches(const char *text, const char *prefix);
static int cli_parse_u32(const char *text, uint32_t *value);
static void cli_redraw_input(void);
static void cli_history_record(const char *command);
static void cli_history_move(int direction);
static void cli_complete_input(void);
static size_t cli_completion_candidate_count(void);
static int cli_completion_candidate(size_t index, char *candidate,
                                    size_t capacity);
static void cli_command_help(Menu_t *menu, const char *command);
static void cli_command_version(Menu_t *menu, const char *command);
static void cli_command_status(Menu_t *menu, const char *command);
static void cli_command_usb(Menu_t *menu, const char *command);
static void cli_command_clear(Menu_t *menu, const char *command);
static void cli_command_map(Menu_t *menu, const char *command);
static void cli_command_tof(Menu_t *menu, const char *command);
static void __attribute__((optimize("Os")))
cli_command_dataset(Menu_t *menu, const char *command);
static void cli_command_rps(Menu_t *menu, const char *command);
static void cli_command_debug(Menu_t *menu, const char *command);
static void cli_command_reboot(Menu_t *menu, const char *command);
static void cli_command_firmware_update(Menu_t *menu, const char *command);
static void cli_command_unknown(Menu_t *menu, const char *command);
static void cli_print(const char *format, ...);
static void cli_prompt(void);
static void cli_show_help(void);
static void cli_show_status(void);
static void cli_show_tof_status(void);
#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
static void cli_show_display_status(void);
#endif
static void cli_show_usb_status(void);
static void cli_show_map_channels(void);
static void cli_show_map_processing(void);
static const TOF_ImageFilterDescriptor_t *cli_find_map_filter(
    int argc, char *const argv[], size_t *filter_argument_count);
static const char *cli_tof_state_name(TOF_App_State_t state);
static const char *cli_radio_state_name(WifiBle_State_t state);
static const char *cli_log_level_name(uint32_t level);
static void cli_command_radio(Menu_t *menu, const char *command);
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
static void cli_command_cloud(Menu_t *menu, const char *command);
static const char *cli_cloud_state_name(CloudRelay_State_t state);
#endif
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
static void cli_command_wifi(Menu_t *menu, const char *command);
static void cli_session_clear_credentials(CliSession_t *session);
#endif
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static void cli_command_ble(Menu_t *menu, const char *command);
#endif
#if (APP_ST67W6X_ENABLED == 1U)
static uint32_t cli_radio_is_ready(void);
#endif
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
static void cli_wifi_status(void);
static void cli_wifi_scan(void);
static void cli_wifi_connect_password(CliSession_t *session);
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
static void cli_m2_run_diagnostic(void);
#endif
#endif
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static void __attribute__((optimize("Os"))) cli_ble_status(void);
#endif

/*
 * Adding a command requires one table entry and one handler.  The menu passes
 * the complete line, including every argument, to the selected handler.
 */
static const Menu_Object_t cli_menu_objects[] =
{
  MENU_OBJECT("help", cli_command_help),
  MENU_OBJECT("menu", cli_command_help),
  MENU_OBJECT("?", cli_command_help),
  MENU_OBJECT("version", cli_command_version),
  MENU_OBJECT("status", cli_command_status),
  MENU_OBJECT("usb", cli_command_usb),
  MENU_OBJECT("clear", cli_command_clear),
  MENU_OBJECT("MAP", cli_command_map),
  MENU_OBJECT("map", cli_command_map),
  MENU_OBJECT("tof", cli_command_tof),
  MENU_OBJECT("DATASET", cli_command_dataset),
  MENU_OBJECT("dataset", cli_command_dataset),
  MENU_OBJECT("RPS", cli_command_rps),
  MENU_OBJECT("rps", cli_command_rps),
  MENU_OBJECT("debug", cli_command_debug),
  MENU_OBJECT("Start UART Firmware Update", cli_command_firmware_update),
  MENU_OBJECT("update", cli_command_firmware_update),
  MENU_OBJECT("radio", cli_command_radio),
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  MENU_OBJECT("cloud", cli_command_cloud),
#endif
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  MENU_OBJECT("wifi", cli_command_wifi),
#endif
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  MENU_OBJECT("ble", cli_command_ble),
#endif
  MENU_OBJECT("reboot", cli_command_reboot)
};

static const char *const cli_completion_base[] =
{
  "help",
  "menu",
  "version",
  "status",
  "usb status",
  "clear",
  "MAP ON",
  "MAP OFF",
  "MAP CHANNELS",
#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
  "MAP ON SCREEN",
  "MAP OFF SCREEN",
  "MAP ON DISPLAY",
  "MAP OFF DISPLAY",
#endif
  "MAP PROCESSING",
  "tof status",
  "tof pause",
  "tof resume",
  "DATASET STREAM ON",
  "DATASET STREAM OFF",
  "DATASET STREAM STATUS",
  "RPS STATUS",
  "RPS ON",
  "RPS OFF",
  "debug off",
  "debug error",
  "debug warn",
  "debug info",
  "debug debug",
  "debug ping ",
  "debug route",
  "debug uart",
  "debug uart burst",
  "debug uart overflow",
  "Start UART Firmware Update",
  "update",
  "radio hardware",
  "radio status",
#if (APP_ST67W6X_ENABLED == 1U)
  "radio info",
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  "cloud status",
  "cloud endpoint",
  "cloud pair ",
  "cloud enable",
  "cloud disable",
  "cloud reconnect",
  "cloud unpair yes",
#endif
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  "wifi status",
  "wifi ip",
  "wifi scan",
  "wifi connect ",
  "wifi disconnect",
  "wifi disconnect forget",
#endif
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  "ble status",
  "ble adv on",
  "ble adv off",
  "ble disconnect",
#endif
  "reboot yes",
};

void Debug_CLI_Run(void)
{
  uint8_t rx_buffer[CLI_RX_CHUNK_SIZE];
  Menu_Status_t menu_status;

  cli_context.sessions.cloud = &cli_cloud_storage.session;
  cli_active_session = &cli_usb_session;
  cli_context.thread.started = 1U;
  (void)memset(&cli_usb_session, 0, sizeof(cli_usb_session));
  menu_status = cli_session_init(&cli_usb_session, APP_TRANSPORT_USB);
  if (menu_status != MENU_STATUS_OK)
  {
    Debug_UART_Log("CLI", "USB menu initialization failed: %d",
                   (int)menu_status);
    for (;;)
    {
      tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND);
    }
  }
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  (void)memset(&cli_cloud_session, 0, sizeof(cli_cloud_session));
  menu_status = cli_session_init(&cli_cloud_session, APP_TRANSPORT_CLOUD);
  if (menu_status != MENU_STATUS_OK)
  {
    Debug_UART_Log("CLI", "Cloud menu initialization failed: %d",
                   (int)menu_status);
  }
  else
  {
    cli_cloud_session.console_mode = 1U;
    cli_cloud_session.session_ready = 1U;
  }
#endif
#if ((APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U) && \
     (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U))
  cli_m2_run_diagnostic();
#endif

  for (;;)
  {
    ULONG actual_length = 0U;

    cli_context.thread.cycles++;
    cli_context.thread.last_tick = HAL_GetTick();

    Firmware_Update_Poll(HAL_GetTick());
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
    cli_poll_ble();
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
    cli_poll_cloud();
#endif
    cli_active_session = &cli_usb_session;

    if (App_Console_IsReady() == 0U)
    {
      if ((Firmware_Update_IsActive() != 0U) &&
          (cli_update_session == &cli_usb_session))
      {
        Firmware_Update_Cancel();
      }
      if (cli_cdc_session_ready != 0U)
      {
        cli_session_reset(&cli_usb_session, 1U);
      }
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
      cli_poll_wifi_results();
#endif
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
      tx_thread_sleep(((Firmware_Update_IsActive() != 0U) &&
                       ((cli_update_session == cli_ble_session) ||
                        (cli_update_session == &cli_cloud_session))) ?
                      1U : (TX_TIMER_TICKS_PER_SECOND / 10U));
#else
      tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 10U);
#endif
      continue;
    }

    if (cli_cdc_session_ready == 0U)
    {
      cli_cdc_session_ready = 1U;
      cli_enter_console();
    }
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    cli_poll_wifi_results();
#endif

#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
    /* Do not block for a CDC packet while BLE owns XMODEM.  Its RX queue is
     * deliberately shallow and must be drained fast enough that ATT writes
     * receive protocol-level ACK/NAK rather than being silently discarded. */
    if ((Firmware_Update_IsActive() != 0U) &&
        ((cli_update_session == cli_ble_session) ||
         (cli_update_session == &cli_cloud_session)))
    {
      tx_thread_sleep(1U);
      continue;
    }
#endif

    UINT status = App_Console_Read(rx_buffer, sizeof(rx_buffer), &actual_length);
    if (status != TX_SUCCESS)
    {
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
      cli_poll_ble();
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
      cli_poll_cloud();
#endif
      continue;
    }

    if ((Firmware_Update_IsActive() != 0U) &&
        (cli_update_session == &cli_usb_session))
    {
      Firmware_Update_Feed(rx_buffer, (size_t)actual_length, HAL_GetTick());
      Firmware_Update_Poll(HAL_GetTick());
      continue;
    }

    if ((actual_length != 0U) && (cli_first_input_logged == 0U))
    {
      cli_first_input_logged = 1U;
      Debug_UART_Log("CLI", "first CDC input reached CLI: %lu byte(s), first=0x%02X",
                     (unsigned long)actual_length,
                     (unsigned int)rx_buffer[0]);
    }

    for (ULONG i = 0U; i < actual_length; ++i)
    {
      cli_process_byte(rx_buffer[i]);
      if ((Firmware_Update_IsActive() != 0U) &&
          (cli_update_session == &cli_usb_session))
      {
        ULONG next = i + 1U;
        ULONG remaining;

        /* The command can end in CRLF inside one CDC chunk.  CR activated raw
         * mode; its paired LF still belongs to the CLI and must not become the
         * first byte reported to XMODEM. */
        if ((rx_buffer[i] == '\r') && (next < actual_length) &&
            (rx_buffer[next] == '\n'))
        {
          next++;
        }
        remaining = actual_length - next;
        if (remaining != 0U)
        {
          Firmware_Update_Feed(&rx_buffer[next], (size_t)remaining,
                               HAL_GetTick());
          Firmware_Update_Poll(HAL_GetTick());
        }
        break;
      }
    }

#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
    cli_poll_ble();
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
    cli_poll_cloud();
#endif
  }
}

static Menu_Status_t cli_session_init(CliSession_t *session,
                                      AppTransport_t transport)
{
  session->route.transport = transport;
  session->route.session_generation =
      cli_next_generation(session->route.session_generation);
  session->history_index = 0U;
  return Menu_Init(&session->menu,
                   cli_menu_objects,
                   MENU_OBJECT_COUNT(cli_menu_objects),
                   session->menu_input,
                   sizeof(session->menu_input),
                   session->menu_reply,
                   sizeof(session->menu_reply),
                   cli_menu_send,
                   session,
                   cli_command_unknown);
}

static void cli_session_reset(CliSession_t *session, uint32_t stop_usb_streams)
{
  CliSession_t *previous = cli_active_session;

  session->route.session_generation =
      cli_next_generation(session->route.session_generation);

  cli_active_session = session;
  cli_console_mode = 0U;
  cli_secret_mode = CLI_SECRET_NONE;
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  cli_session_clear_credentials(session);
#endif
  cli_previous_was_cr = 0U;
  cli_escape_state = 0U;
  cli_history_index = cli_history_count;
  (void)memset(cli_history_draft, 0, sizeof(cli_history_draft));
  cli_first_input_logged = 0U;
  cli_cdc_session_ready = 0U;
  cli_prompt_already_sent = 0U;
  Menu_Reset(&cli_menu);
  (void)memset(cli_menu_input, 0, sizeof(cli_menu_input));
  if (session->route.transport != APP_TRANSPORT_USB)
  {
    /* A reconnect may be a different peer. Do not expose the previous peer's
     * command history through terminal cursor keys. */
    (void)memset(cli_history, 0, sizeof(cli_history));
    (void)memset(cli_history_draft, 0, sizeof(cli_history_draft));
    cli_history_count = 0U;
    cli_history_index = 0U;
  }
  if (stop_usb_streams != 0U)
  {
    TOF_App_SetMapEnabled(0U);
    TOF_App_SetDatasetStreamEnabled(0U);
  }
  cli_active_session = previous;
}

static uint32_t cli_next_generation(uint32_t generation)
{
  generation++;
  return (generation != 0U) ? generation : 1U;
}

static uint32_t cli_route_is_current(const AppRoute_t *current,
                                     const AppRoute_t *saved)
{
  if ((current == NULL) || (saved == NULL))
  {
    return 0U;
  }
  return ((current->transport == saved->transport) &&
          (current->session_generation == saved->session_generation) &&
          (current->session_generation != 0U)) ? 1U : 0U;
}

static const char *cli_transport_name(AppTransport_t transport)
{
  switch (transport)
  {
    case APP_TRANSPORT_USB: return "USB";
    case APP_TRANSPORT_BLE: return "BLE";
    case APP_TRANSPORT_CLOUD: return "Cloud";
    case APP_TRANSPORT_SYSTEM: return "System";
    default: return "unknown";
  }
}

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
static UINT cli_wifi_result_print(const char *format, ...)
{
  va_list args;
  int length;

  va_start(args, format);
  length = vsnprintf(cli_print_buffer, sizeof(cli_print_buffer), format, args);
  va_end(args);
  if ((length <= 0) || ((size_t)length >= sizeof(cli_print_buffer)))
  {
    return TX_SIZE_ERROR;
  }
  return cli_session_write(cli_active_session, cli_print_buffer,
                           (ULONG)length);
}

static void cli_wifi_note_submission(AppRequestId_t request_id)
{
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  if (cli_active_session->route.transport == APP_TRANSPORT_CLOUD)
  {
    cli_cloud_wifi_request_id = request_id;
  }
#else
  (void)request_id;
#endif
}

static void cli_wifi_result_defer(const WifiBle_WifiResult_t *result)
{
  for (uint32_t i = 0U; i < CLI_WIFI_DEFERRED_RESULTS; ++i)
  {
    if (cli_wifi_deferred_valid[i] == 0U)
    {
      cli_wifi_deferred[i] = *result;
      cli_wifi_deferred_valid[i] = 1U;
      return;
    }
  }
  /* Always release the worker's result slot, even if one blocked session
   * fills the bounded CLI mailbox. Other transports must keep progressing. */
  cli_wifi_results_deferred_overflow++;
}

static uint32_t cli_wifi_result_deliver(WifiBle_WifiResult_t *result)
{
  CliSession_t *previous = cli_active_session;
  CliSession_t *target = NULL;
  UINT write_status = TX_SUCCESS;

  switch (result->route.transport)
  {
    case APP_TRANSPORT_USB:
      if ((App_Console_IsReady() != 0U) &&
          (cli_usb_session.session_ready != 0U)) target = &cli_usb_session;
      break;
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
    case APP_TRANSPORT_BLE:
      if ((cli_ble_session != NULL) &&
          (cli_ble_session->session_ready != 0U))
      {
        WifiBle_RuntimeStatus_t runtime;
        WIFI_BLE_App_GetRuntimeStatus(&runtime);
        if ((runtime.ble_connected != 0U) &&
            (runtime.ble_transport_ready != 0U) &&
            (runtime.ble_cli_tx_subscribed != 0U) &&
            (runtime.ble_session_generation ==
             result->route.session_generation)) target = cli_ble_session;
      }
      break;
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
    case APP_TRANSPORT_CLOUD:
      if (cli_cloud_session.session_ready != 0U)
      {
        CloudRelay_Status_t cloud_status;
        CloudRelay_GetStatus(&cloud_status);
        if ((cloud_status.enabled != 0U) &&
            (cloud_status.paired != 0U) &&
            (cli_next_generation(cloud_status.generation) ==
             result->route.session_generation) &&
            (cli_cloud_command_active != 0U) &&
            (cli_cloud_wifi_request_id == result->request_id))
        {
          target = &cli_cloud_session;
        }
      }
      break;
#endif
    default:
      break;
  }

  if ((target == NULL) ||
      (cli_route_is_current(&target->route, &result->route) == 0U))
  {
    cli_wifi_results_stale++;
    return 1U;
  }

  /* Only the owning session may defer its text. A password prompt or XMODEM
   * on USB must not retain BLE/Cloud results in the worker's four slots. */
  if ((target->secret_mode != CLI_SECRET_NONE) ||
      ((Firmware_Update_IsActive() != 0U) &&
       (cli_update_session == target)))
  {
    return 0U;
  }

#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  if (target->route.transport == APP_TRANSPORT_CLOUD)
  {
    char record[256];
    int length = snprintf(record, sizeof(record),
        "Wi-Fi %s request id=%" PRIu32 ": %s (%" PRId32
        "); scan_count=%" PRIu32 "; IPv4=%u.%u.%u.%u\r\n",
        (result->operation == WIFI_BLE_WIFI_OPERATION_SCAN) ? "scan" :
        (result->operation == WIFI_BLE_WIFI_OPERATION_CONNECT) ? "connect" :
        (result->operation == WIFI_BLE_WIFI_OPERATION_DISCONNECT) ?
            "disconnect" : "unknown",
        (uint32_t)result->request_id,
        W6X_StatusToStr((W6X_Status_t)result->final_status),
        result->final_status, result->scan_results.count,
        result->wifi_status.ip_address[0],
        result->wifi_status.ip_address[1],
        result->wifi_status.ip_address[2],
        result->wifi_status.ip_address[3]);
    if ((length <= 0) || ((size_t)length >= sizeof(record)))
    {
      cli_wifi_result_write_errors++;
      return 1U;
    }
    write_status = CloudRelay_TryWriteOutput(record, (size_t)length, 0U);
    if (write_status != TX_SUCCESS)
    {
      if ((write_status != TX_QUEUE_FULL) &&
          (write_status != TX_NOT_AVAILABLE))
      {
        cli_wifi_result_write_errors++;
      }
      return 0U;
    }
    cli_wifi_results_routed++;
    cli_cloud_wifi_request_id = 0U;
    return 1U;
  }
#endif

  cli_active_session = target;
  write_status = cli_wifi_result_print(
      "\r\nWi-Fi %s request id=%" PRIu32 ": %s (%" PRId32 ").\r\n",
      (result->operation == WIFI_BLE_WIFI_OPERATION_SCAN) ? "scan" :
      (result->operation == WIFI_BLE_WIFI_OPERATION_CONNECT) ? "connect" :
      (result->operation == WIFI_BLE_WIFI_OPERATION_DISCONNECT) ?
          "disconnect" : "unknown",
      (uint32_t)result->request_id,
      W6X_StatusToStr((W6X_Status_t)result->final_status),
      result->final_status);

  if ((write_status == TX_SUCCESS) &&
      (result->final_status == (int32_t)W6X_STATUS_OK))
  {
    if (result->operation == WIFI_BLE_WIFI_OPERATION_SCAN)
    {
      uint32_t count = result->scan_results.count;
      if (count > WIFI_BLE_WIFI_SCAN_MAX_APS) count = WIFI_BLE_WIFI_SCAN_MAX_APS;
      write_status = cli_wifi_result_print(
          "Wi-Fi scan: %" PRIu32 " network(s).\r\n", count);
      for (uint32_t i = 0U; (i < count) &&
           (write_status == TX_SUCCESS); ++i)
      {
        const WifiBle_WifiAccessPoint_t *ap =
            &result->scan_results.access_points[i];
        write_status = cli_wifi_result_print(
            "  CH %u RSSI %d %-13.13s %-5.5s %.32s\r\n",
            (unsigned int)ap->channel, (int)ap->rssi,
            W6X_WiFi_SecurityToStr(ap->security),
            W6X_WiFi_ProtocolToStr((W6X_WiFi_Protocol_e)ap->protocol),
            ap->ssid);
      }
    }
    else if ((result->operation == WIFI_BLE_WIFI_OPERATION_CONNECT) &&
             (result->wifi_status.ip_valid != 0U))
    {
      const WifiBle_WifiStatus_t *wifi = &result->wifi_status;
      write_status = cli_wifi_result_print(
          "Wi-Fi connected to %.32s. IPv4: %u.%u.%u.%u\r\n",
          wifi->ssid, wifi->ip_address[0], wifi->ip_address[1],
          wifi->ip_address[2], wifi->ip_address[3]);
    }
  }

  if (write_status == TX_SUCCESS)
  {
    cli_wifi_results_routed++;
    cli_redraw_input();
  }
  else
  {
    cli_wifi_result_write_errors++;
  }
  cli_active_session = previous;
  return 1U;
}

static void cli_poll_wifi_results(void)
{
  WifiBle_WifiResult_t result;

  for (uint32_t i = 0U; i < CLI_WIFI_DEFERRED_RESULTS; ++i)
  {
    if ((cli_wifi_deferred_valid[i] != 0U) &&
        (cli_wifi_result_deliver(&cli_wifi_deferred[i]) != 0U))
    {
      (void)memset(&cli_wifi_deferred[i], 0,
                   sizeof(cli_wifi_deferred[i]));
      cli_wifi_deferred_valid[i] = 0U;
    }
  }

  for (uint32_t drained = 0U; drained < CLI_WIFI_RESULTS_PER_POLL; ++drained)
  {
    UINT status = WIFI_BLE_App_WifiReceiveResult(&result);
    if (status == TX_QUEUE_EMPTY) break;
    if (status != TX_SUCCESS)
    {
      Debug_UART_Log("CLI", "Wi-Fi result receive failed: %u", status);
      break;
    }
    if (cli_wifi_result_deliver(&result) == 0U)
    {
      cli_wifi_result_defer(&result);
    }
    (void)memset(&result, 0, sizeof(result));
  }
}
#endif

#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static uint32_t cli_ble_session_allocate(void)
{
  static uint32_t last_attempt_tick;
  TX_BYTE_POOL *radio_pool = MX_RadioBytePool_Get();
  void *memory = NULL;
  Menu_Status_t menu_status;
  uint32_t now = HAL_GetTick();

  if ((last_attempt_tick != 0U) &&
      ((uint32_t)(now - last_attempt_tick) < 1000U))
  {
    return 0U;
  }
  last_attempt_tick = now;

  if ((radio_pool == NULL) ||
      (tx_byte_allocate(radio_pool, &memory, sizeof(CliSession_t),
                        TX_NO_WAIT) != TX_SUCCESS))
  {
    Debug_UART_Log("CLI", "BLE CLI session allocation failed; CDC remains available");
    return 0U;
  }

  cli_ble_session = (CliSession_t *)memory;
  (void)memset(cli_ble_session, 0, sizeof(*cli_ble_session));
  menu_status = cli_session_init(cli_ble_session, APP_TRANSPORT_BLE);
  if (menu_status != MENU_STATUS_OK)
  {
    Debug_UART_Log("CLI", "BLE menu initialization failed: %d",
                   (int)menu_status);
    (void)tx_byte_release(cli_ble_session);
    cli_ble_session = NULL;
    return 0U;
  }

  Debug_UART_Log("CLI", "BLE CLI session allocated in SRAM4 after radio ready (%lu bytes)",
                 (unsigned long)sizeof(CliSession_t));
  return 1U;
}

static void __attribute__((optimize("Os"))) cli_poll_ble(void)
{
  WifiBle_RuntimeStatus_t runtime;
  uint8_t rx_buffer[CLI_BLE_RX_CHUNK_SIZE];
  AppRoute_t runtime_route;

  WIFI_BLE_App_GetRuntimeStatus(&runtime);
  if ((cli_ble_session == NULL) &&
      (runtime.state == WIFI_BLE_STATE_READY) &&
      (cli_ble_session_allocate() == 0U))
  {
    return;
  }
  if (cli_ble_session == NULL)
  {
    return;
  }

  runtime_route.transport = APP_TRANSPORT_BLE;
  runtime_route.session_generation =
      (runtime.ble_session_generation != 0U) ?
      runtime.ble_session_generation : 1U;
  if (cli_route_is_current(&cli_ble_session->route, &runtime_route) == 0U)
  {
    if ((Firmware_Update_IsActive() != 0U) &&
        (cli_update_session == cli_ble_session))
    {
      Firmware_Update_Cancel();
    }
    if (cli_ble_session->session_ready != 0U)
    {
      Debug_UART_Log("CLI", "BLE CLI session closed (generation %lu)",
                     (unsigned long)
                         cli_ble_session->route.session_generation);
    }
    /* The radio runtime already advances its generation on both connect and
     * disconnect. Reset the parser exactly once, then align to that epoch in
     * case the CLI broker missed more than one radio transition. */
    cli_session_reset(cli_ble_session, 0U);
    cli_ble_session->route.session_generation =
        runtime_route.session_generation;
  }
  if ((runtime.ble_transport_ready == 0U) ||
      (runtime.ble_connected == 0U))
  {
    return;
  }

  /* Notifications are the response path.  Keep writes queued until the peer
   * subscribes, then establish one clean terminal session for this link. */
  if (runtime.ble_cli_tx_subscribed == 0U)
  {
    return;
  }

  cli_active_session = cli_ble_session;
  if (cli_cdc_session_ready == 0U)
  {
    cli_cdc_session_ready = 1U;
    cli_enter_console();
    Debug_UART_Log("CLI", "BLE CLI session ready (generation %lu)",
                   (unsigned long)runtime.ble_session_generation);
  }

  for (uint32_t burst = 0U; burst < CLI_BLE_RX_BURST; ++burst)
  {
    ULONG actual_length = 0U;
    UINT status = WIFI_BLE_App_StreamRead(WIFI_BLE_STREAM_CLI,
                                          rx_buffer,
                                          sizeof(rx_buffer),
                                          &actual_length,
                                          TX_NO_WAIT);
    if ((status != TX_SUCCESS) || (actual_length == 0U))
    {
      break;
    }
    Debug_UART_NcpTracePing("CLI RX dequeued", rx_buffer,
                            (size_t)actual_length);

    if (cli_first_input_logged == 0U)
    {
      cli_first_input_logged = 1U;
      Debug_UART_Log("CLI", "first BLE input reached CLI: %lu byte(s), first=0x%02X",
                     (unsigned long)actual_length,
                     (unsigned int)rx_buffer[0]);
    }

    if ((Firmware_Update_IsActive() != 0U) &&
        (cli_update_session == cli_ble_session))
    {
      Firmware_Update_Feed(rx_buffer, (size_t)actual_length, HAL_GetTick());
      Firmware_Update_Poll(HAL_GetTick());
      continue;
    }

    for (ULONG i = 0U; i < actual_length; ++i)
    {
      cli_process_byte(rx_buffer[i]);
      if ((Firmware_Update_IsActive() != 0U) &&
          (cli_update_session == cli_ble_session))
      {
        ULONG next = i + 1U;
        if ((rx_buffer[i] == '\r') && (next < actual_length) &&
            (rx_buffer[next] == '\n'))
        {
          next++;
        }
        if (next < actual_length)
        {
          Firmware_Update_Feed(&rx_buffer[next],
                               (size_t)(actual_length - next),
                               HAL_GetTick());
          Firmware_Update_Poll(HAL_GetTick());
        }
        break;
      }
    }
  }

  cli_active_session = &cli_usb_session;
}
#endif

#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
static void cli_poll_cloud(void)
{
  CloudRelay_Input_t input;
  CloudRelay_Status_t status;
  AppRoute_t runtime_route;
  uint32_t update_was_active;

  cli_active_session = &cli_cloud_session;

  CloudRelay_GetStatus(&status);
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  if (((status.enabled == 0U) || (status.paired == 0U)) &&
      (cli_cloud_wifi_request_id != 0U))
  {
    cli_cloud_wifi_request_id = 0U;
    cli_cloud_command_active = 0U;
  }
#endif
  runtime_route.transport = APP_TRANSPORT_CLOUD;
  /* Cloud Relay generation identifies a logical capability/control epoch,
   * not each short-lived HTTP socket. Offset its zero-based runtime value so
   * every public route generation remains non-zero. */
  runtime_route.session_generation = cli_next_generation(status.generation);
  if (cli_route_is_current(&cli_cloud_session.route, &runtime_route) == 0U)
  {
    if ((Firmware_Update_IsActive() != 0U) &&
        (cli_update_session == &cli_cloud_session))
    {
      Firmware_Update_Cancel();
      cli_update_session = NULL;
    }
    cli_session_reset(&cli_cloud_session, 0U);
    cli_cloud_session.route.session_generation =
        runtime_route.session_generation;
    cli_cloud_session.console_mode = 1U;
    cli_cloud_session.session_ready = 1U;
    cli_cloud_command_active = 0U;
    cli_cloud_wifi_request_id = 0U;
  }

  /* XMODEM finalizes asynchronously after EOT. Close the logical browser
   * command only after the updater has emitted its final ACK/result. */
  if ((cli_cloud_command_active != 0U) &&
      (cli_update_session == &cli_cloud_session) &&
      (Firmware_Update_IsActive() == 0U))
  {
    Firmware_Update_Poll(HAL_GetTick());
    if (CloudRelay_CompleteCommand() == TX_SUCCESS)
    {
      cli_cloud_command_active = 0U;
      cli_update_session = NULL;
    }
  }

  /* A long command (notably "help") can temporarily fill the bounded Cloud
   * output queue.  Do not lease the next browser command until the completion
   * marker for the previous command has also been accepted by the relay. */
  if ((cli_cloud_command_active != 0U) &&
      (cli_update_session != &cli_cloud_session) &&
      (cli_cloud_wifi_request_id == 0U))
  {
    if (CloudRelay_CompleteCommand() == TX_SUCCESS)
    {
      cli_cloud_command_active = 0U;
    }
    else
    {
      cli_active_session = &cli_usb_session;
      return;
    }
  }

  if (cli_cloud_wifi_request_id != 0U)
  {
    cli_active_session = &cli_usb_session;
    return;
  }

  if (CloudRelay_ReadInput(&input) != TX_SUCCESS)
  {
    cli_active_session = &cli_usb_session;
    return;
  }

  cli_cloud_command_active = 1U;
  update_was_active = Firmware_Update_IsActive();
  if ((input.binary != 0U) &&
      (cli_update_session == &cli_cloud_session) &&
      (Firmware_Update_IsActive() != 0U))
  {
    Firmware_Update_Feed(input.data, input.length, HAL_GetTick());
    Firmware_Update_Poll(HAL_GetTick());
  }
  else if (input.binary == 0U)
  {
    for (uint32_t index = 0U; index < input.length; ++index)
    {
      cli_process_byte(input.data[index]);
      if ((Firmware_Update_IsActive() != 0U) &&
          (cli_update_session == &cli_cloud_session))
      {
        break;
      }
    }
  }

  (void)CloudRelay_AcknowledgeInput(
      &input, (cli_cloud_wifi_request_id != 0U) ? 1U : 0U);
  if ((update_was_active == 0U) &&
      !((Firmware_Update_IsActive() != 0U) &&
        (cli_update_session == &cli_cloud_session)) &&
      (cli_cloud_wifi_request_id == 0U))
  {
    if (CloudRelay_CompleteCommand() == TX_SUCCESS)
    {
      cli_cloud_command_active = 0U;
    }
  }
  else if ((input.completed != 0U) &&
           (Firmware_Update_IsActive() == 0U))
  {
    Firmware_Update_Poll(HAL_GetTick());
    if (CloudRelay_CompleteCommand() == TX_SUCCESS)
    {
      cli_cloud_command_active = 0U;
      cli_update_session = NULL;
    }
  }

  cli_active_session = &cli_usb_session;
}
#endif

static void cli_process_byte(uint8_t byte)
{
  Menu_Status_t menu_status;

  if ((byte == '\n') && (cli_previous_was_cr != 0U))
  {
    cli_previous_was_cr = 0U;
    return;
  }
  cli_previous_was_cr = (byte == '\r') ? 1U : 0U;

  if (cli_console_mode == 0U)
  {
    if ((byte >= '1') && (byte <= '5'))
    {
      TOF_App_Channel_t channel = (TOF_App_Channel_t)(byte - '0');
      uint32_t mask = TOF_App_ToggleMapChannel(channel);
      Debug_UART_Log("CLI", "MAP channel %lu (%s) toggled; mask=0x%02lx",
                     (unsigned long)channel,
                     TOF_App_GetChannelName(channel),
                     (unsigned long)mask);
      return;
    }
    if ((byte == '\r') || (byte == '\n'))
    {
      cli_enter_console();
    }
    return;
  }

  if (cli_escape_state != 0U)
  {
    if (cli_escape_state == 1U)
    {
      cli_escape_state = ((byte == '[') || (byte == 'O')) ? 2U : 0U;
      return;
    }

    cli_escape_state = 0U;
    if (byte == 'A')
    {
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
      if (cli_secret_mode == CLI_SECRET_NONE)
#endif
      cli_history_move(-1);
    }
    else if (byte == 'B')
    {
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
      if (cli_secret_mode == CLI_SECRET_NONE)
#endif
      cli_history_move(1);
    }
    return;
  }

  if (byte == 0x1BU)
  {
    cli_escape_state = 1U;
    return;
  }

  if (byte == '\t')
  {
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    if (cli_secret_mode == CLI_SECRET_NONE)
#endif
    {
      cli_complete_input();
    }
    return;
  }

  if ((byte == '\r') || (byte == '\n'))
  {
    /* USB locally echoes the command and needs a line break before its reply.
     * BLE and Cloud are message-oriented and do not echo input; a standalone
     * CRLF there consumes one bounded TX slot per command and can crowd out a
     * real reply during a burst. */
    if (cli_active_session->route.transport == APP_TRANSPORT_USB)
    {
      cli_print("\r\n");
    }

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    if (cli_secret_mode == CLI_SECRET_WIFI_PASSWORD)
    {
      cli_pending_password[cli_pending_password_length] = '\0';
      cli_wifi_connect_password(cli_active_session);
      /* The radio request has copied or rejected both values before return.
       * Scrub the complete fixed capacities on every submission outcome. */
      cli_session_clear_credentials(cli_active_session);
      if (cli_prompt_already_sent != 0U)
      {
        cli_prompt_already_sent = 0U;
      }
      else
      {
        cli_prompt();
      }
      return;
    }
#endif

    cli_history_record(Menu_GetPendingInput(&cli_menu));
    cli_history_index = cli_history_count;
    (void)memset(cli_history_draft, 0, sizeof(cli_history_draft));
    menu_status = Menu_Process(&cli_menu, &byte, 1U);
    if (menu_status == MENU_STATUS_INPUT_TOO_LONG)
    {
      (void)Menu_Reply(&cli_menu, "Command is too long.");
      Debug_UART_Log("CLI", "discarded an overlength command");
    }

    if ((cli_console_mode != 0U) &&
        (cli_secret_mode == CLI_SECRET_NONE) &&
        (Firmware_Update_IsActive() == 0U))
    {
      if (cli_prompt_already_sent != 0U)
      {
        cli_prompt_already_sent = 0U;
      }
      else
      {
        cli_prompt();
      }
    }
    return;
  }

  if ((byte == 0x08U) || (byte == 0x7FU))
  {
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    if (cli_secret_mode == CLI_SECRET_WIFI_PASSWORD)
    {
      if (cli_pending_password_length != 0U)
      {
        --cli_pending_password_length;
        cli_pending_password[cli_pending_password_length] = '\0';
      }
      return;
    }
#endif

    if (Menu_GetPendingLength(&cli_menu) != 0U)
    {
      cli_history_index = cli_history_count;
      (void)Menu_Process(&cli_menu, &byte, 1U);
      cli_print("\b \b");
    }
    return;
  }

  if (byte == 0x03U)
  {
    cli_secret_mode = CLI_SECRET_NONE;
    cli_escape_state = 0U;
    cli_history_index = cli_history_count;
    (void)memset(cli_history_draft, 0, sizeof(cli_history_draft));
    Menu_Reset(&cli_menu);
    (void)memset(cli_menu_input, 0, sizeof(cli_menu_input));
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    cli_session_clear_credentials(cli_active_session);
#endif
    cli_print("^C\r\n");
    cli_prompt();
    return;
  }

  if ((byte >= 0x20U) && (byte <= 0x7EU))
  {
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    if (cli_secret_mode == CLI_SECRET_WIFI_PASSWORD)
    {
      if (cli_pending_password_length < (sizeof(cli_pending_password) - 1U))
      {
        cli_pending_password[cli_pending_password_length++] = (char)byte;
      }
      else
      {
        cli_session_clear_credentials(cli_active_session);
        cli_print("\r\nPassword is too long; credentials cleared.\r\n");
        cli_prompt();
      }
      return;
    }
#endif

    cli_history_index = cli_history_count;
    menu_status = Menu_Process(&cli_menu, &byte, 1U);
    if (menu_status == MENU_STATUS_INPUT_TOO_LONG)
    {
      cli_print("\r\n");
      (void)Menu_Reply(&cli_menu, "Command is too long.");
      Debug_UART_Log("CLI", "input exceeded the %u-byte command buffer",
                     (unsigned int)sizeof(cli_menu_input));
      return;
    }

    /* CDC is an interactive terminal and expects local echo. BLE commands are
     * message-oriented writes; echoing each byte would consume one bounded TX
     * slot and could starve the actual reply on a slow notification link. */
    if (cli_active_session->route.transport == APP_TRANSPORT_USB)
    {
      (void)cli_session_write(cli_active_session, &byte, 1U);
    }
  }
}

static void cli_enter_console(void)
{
  cli_console_mode = 1U;
  cli_secret_mode = CLI_SECRET_NONE;
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  cli_session_clear_credentials(cli_active_session);
#endif
  cli_escape_state = 0U;
  cli_history_index = cli_history_count;
  (void)memset(cli_history_draft, 0, sizeof(cli_history_draft));
  Menu_Reset(&cli_menu);
  if (cli_active_session->route.transport == APP_TRANSPORT_USB)
  {
    TOF_App_SetMapEnabled(0U);
    Debug_UART_Log("CLI", "USB CDC menu entered; depth map disabled");
  }

  /* BLE is message-oriented and starts with a small bounded notification
   * queue while the connection parameters and CCCD are still settling.  The
   * multi-kilobyte interactive help banner can fill that queue before the
   * first command, dropping the prompt or its first PONG even though the link
   * itself is healthy.  Publish one short readiness record instead; the same
   * complete command table remains available through an explicit `help`.
   * USB keeps the teaching-oriented full startup menu. */
  if (cli_active_session->route.transport == APP_TRANSPORT_BLE)
  {
    cli_print("N6 BLE CLI ready. Firmware version: "
              NATI_LAB_FIRMWARE_VERSION_TEXT
              ". Type help for commands.\r\n");
    cli_prompt();
    return;
  }

  cli_print("\033[?25h\033[2J\033[H"
            "+------------------------------------------------+\r\n"
            "|            NATI LAB N6 CONTROL MENU            |\r\n"
            "+------------------------------------------------+\r\n"
            "  Application firmware version: "
            NATI_LAB_FIRMWARE_VERSION_TEXT "\r\n");
  cli_print("  USB CDC carries menu/map/update traffic only.\r\n"
            "  All debug diagnostics are on the ST-LINK VCP.\r\n\r\n");
  cli_show_help();
  cli_print("\r\n");
  cli_prompt();
}

static void cli_command_help(Menu_t *menu, const char *command)
{
  (void)menu;
  (void)command;
  cli_show_help();
}

static void cli_command_version(Menu_t *menu, const char *command)
{
  (void)command;
  (void)Menu_Reply(menu,
                   "Firmware version: " NATI_LAB_FIRMWARE_VERSION_TEXT);
}

static void cli_command_status(Menu_t *menu, const char *command)
{
  (void)menu;
  (void)command;
  cli_show_status();
}

static void cli_command_usb(Menu_t *menu, const char *command)
{
  char copy[CLI_LINE_SIZE];
  char *argv[CLI_MAX_ARGUMENTS];
  int argc = cli_get_arguments(command, copy, sizeof(copy), argv,
                               CLI_MAX_ARGUMENTS);

  if ((argc == 2) && (strcmp(argv[1], "status") == 0))
  {
    cli_show_usb_status();
  }
  else
  {
    (void)Menu_Reply(menu, "Usage: usb status");
  }
}

static void cli_command_clear(Menu_t *menu, const char *command)
{
  (void)command;
  (void)Menu_Reply(menu, "\033[2J\033[H");
}

static void cli_command_map(Menu_t *menu, const char *command)
{
  char copy[CLI_LINE_SIZE];
  char *argv[CLI_MAX_ARGUMENTS];
  int argc = cli_get_arguments(command, copy, sizeof(copy), argv,
                               CLI_MAX_ARGUMENTS);

#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
  if ((argc == 3) &&
      (((cli_token_equals(argv[1], "on") != 0U) &&
        ((cli_token_equals(argv[2], "screen") != 0U) ||
         (cli_token_equals(argv[2], "display") != 0U))) ||
       (((cli_token_equals(argv[1], "screen") != 0U) ||
         (cli_token_equals(argv[1], "display") != 0U)) &&
        (cli_token_equals(argv[2], "on") != 0U))))
  {
    Display_App_SetMapEnabled(1U);
    (void)Menu_Reply(menu,
                     "Screen depth map enabled; processing will publish numbered frames to the display task.");
  }
  else if ((argc == 3) &&
           (((cli_token_equals(argv[1], "off") != 0U) &&
             ((cli_token_equals(argv[2], "screen") != 0U) ||
              (cli_token_equals(argv[2], "display") != 0U))) ||
            (((cli_token_equals(argv[1], "screen") != 0U) ||
              (cli_token_equals(argv[1], "display") != 0U)) &&
             (cli_token_equals(argv[2], "off") != 0U))))
  {
    Display_App_SetMapEnabled(0U);
    (void)Menu_Reply(menu,
                     "Screen depth map disabled; the display task will restore SYSTEM ON when the ToF pipeline is ready.");
  }
  else
#endif
  if ((argc == 2) && (cli_token_equals(argv[1], "on") != 0U))
  {
    if (cli_active_session->route.transport == APP_TRANSPORT_BLE)
    {
      (void)Menu_Reply(menu,
                       "BLE ToF images use the dedicated Notify characteristic; subscribe to it to receive complete CRC-checked frames.");
      return;
    }
    (void)Menu_Reply(menu,
                     "Sensor map enabled. Keys 1..5 toggle channels; Enter returns to the console.");
    TOF_App_SetMapEnabled(1U);
    cli_console_mode = 0U;
  }
  else if ((argc == 2) && (cli_token_equals(argv[1], "off") != 0U))
  {
    if (cli_active_session->route.transport == APP_TRANSPORT_BLE)
    {
      (void)Menu_Reply(menu,
                       "Disable the BLE ToF image CCCD to stop the wireless map stream.");
      return;
    }
    TOF_App_SetMapEnabled(0U);
    (void)Menu_Reply(menu,
                     "Depth map disabled; ranging remains active.");
  }
  else if ((argc >= 2) &&
           (cli_token_equals(argv[1], "channels") != 0U))
  {
    if (argc == 2)
    {
      cli_show_map_channels();
      return;
    }

    if ((argc == 3) && (strlen(argv[2]) == 1U) &&
        (argv[2][0] >= '1') && (argv[2][0] <= '5'))
    {
      (void)TOF_App_ToggleMapChannel(
          (TOF_App_Channel_t)(argv[2][0] - '0'));
      cli_show_map_channels();
      return;
    }

    (void)Menu_Reply(menu, "Usage: MAP CHANNELS [1..5]");
  }
  else if ((argc >= 2) &&
           (cli_token_equals(argv[1], "processing") != 0U))
  {
    const TOF_ImageFilterDescriptor_t *descriptor;
    size_t filter_argument_count = 0U;

    if (argc == 2)
    {
      cli_show_map_processing();
      return;
    }

    descriptor = cli_find_map_filter(argc, argv, &filter_argument_count);
    if (descriptor == NULL)
    {
      (void)Menu_Reply(menu,
                       "Usage: MAP PROCESSING <filter> [value | parameter value]");
      return;
    }

    if ((size_t)argc == (2U + filter_argument_count))
    {
      (void)TOF_App_SelectMapFilter(descriptor->filter);
      cli_show_map_processing();
      return;
    }

    if (((size_t)argc == (3U + filter_argument_count)) &&
        (descriptor->parameter_count == 1U))
    {
      uint32_t value;
      size_t value_argument = 2U + filter_argument_count;
      const TOF_ImageFilterParameter_t *parameter =
          &descriptor->parameters[0];

      if (cli_parse_u32(argv[value_argument], &value) == 0)
      {
        (void)Menu_Reply(menu, "Invalid unsigned integer value.");
        return;
      }

      TOF_ImageProcessingStatus_t result =
          TOF_App_SetMapFilterParameter(descriptor->filter, 0U, value);
      if (result == TOF_IMAGE_PROCESSING_VALUE_OUT_OF_RANGE)
      {
        cli_print("%s must be in the range %" PRIu32 "..%" PRIu32 " %s.\r\n",
                  parameter->name, parameter->minimum, parameter->maximum,
                  parameter->unit);
        return;
      }
      if (result != TOF_IMAGE_PROCESSING_OK)
      {
        (void)Menu_Reply(menu, "Unable to update map processing setting.");
        return;
      }

      (void)TOF_App_SelectMapFilter(descriptor->filter);
      cli_show_map_processing();
      return;
    }

    if ((size_t)argc == (4U + filter_argument_count))
    {
      size_t parameter_index;
      uint32_t value;
      size_t parameter_argument = 2U + filter_argument_count;
      size_t value_argument = parameter_argument + 1U;

      for (parameter_index = 0U;
           parameter_index < descriptor->parameter_count;
           ++parameter_index)
      {
        if (cli_token_equals(argv[parameter_argument],
                             descriptor->parameters[parameter_index].name) != 0U)
        {
          break;
        }
      }

      if ((parameter_index >= descriptor->parameter_count) ||
          (cli_parse_u32(argv[value_argument], &value) == 0))
      {
        (void)Menu_Reply(menu,
                         "Unknown parameter or invalid unsigned integer value.");
        return;
      }

      TOF_ImageProcessingStatus_t result =
          TOF_App_SetMapFilterParameter(descriptor->filter,
                                       parameter_index, value);
      if (result == TOF_IMAGE_PROCESSING_VALUE_OUT_OF_RANGE)
      {
        cli_print("%s must be in the range %" PRIu32 "..%" PRIu32 " %s.\r\n",
                  descriptor->parameters[parameter_index].name,
                  descriptor->parameters[parameter_index].minimum,
                  descriptor->parameters[parameter_index].maximum,
                  descriptor->parameters[parameter_index].unit);
        return;
      }
      if (result != TOF_IMAGE_PROCESSING_OK)
      {
        (void)Menu_Reply(menu, "Unable to update map processing setting.");
        return;
      }

      (void)TOF_App_SelectMapFilter(descriptor->filter);
      cli_show_map_processing();
      return;
    }

    (void)Menu_Reply(menu,
                     "Usage: MAP PROCESSING <filter> [value | parameter value]");
  }
  else
  {
    (void)Menu_Reply(menu,
                     "Usage: MAP ON|OFF [SCREEN] | MAP CHANNELS [1..5] | MAP PROCESSING");
  }
}

static void cli_command_tof(Menu_t *menu, const char *command)
{
  char copy[CLI_LINE_SIZE];
  char *argv[CLI_MAX_ARGUMENTS];
  int argc = cli_get_arguments(command, copy, sizeof(copy), argv,
                               CLI_MAX_ARGUMENTS);

  if ((argc == 2) && (strcmp(argv[1], "status") == 0))
  {
    cli_show_tof_status();
  }
  else if ((argc == 2) && (strcmp(argv[1], "pause") == 0))
  {
    TOF_App_SetPaused(1U);
    (void)Menu_Reply(menu, "ToF autonomous stream paused.");
  }
  else if ((argc == 2) && (strcmp(argv[1], "resume") == 0))
  {
    TOF_App_SetPaused(0U);
    (void)Menu_Reply(menu, "ToF autonomous stream resumed.");
  }
  else
  {
    (void)Menu_Reply(menu, "Usage: tof status|pause|resume");
  }
}

static void __attribute__((optimize("Os")))
cli_command_dataset(Menu_t *menu, const char *command)
{
  char copy[CLI_LINE_SIZE];
  char *argv[CLI_MAX_ARGUMENTS];
  int argc = cli_get_arguments(command, copy, sizeof(copy), argv,
                               CLI_MAX_ARGUMENTS);

  if ((argc == 3) &&
      (cli_token_equals(argv[1], "stream") != 0U) &&
      (cli_token_equals(argv[2], "on") != 0U))
  {
    (void)Menu_Reply(menu,
                     "Dataset stream enabled: N6DF v3, raw 54x42 depth + exact frame-matched 64x50 NPU input + scores, separately CRC32 protected.");
    TOF_App_SetDatasetStreamEnabled(1U);
  }
  else if ((argc == 3) &&
           (cli_token_equals(argv[1], "stream") != 0U) &&
           (cli_token_equals(argv[2], "off") != 0U))
  {
    TOF_App_SetDatasetStreamEnabled(0U);
    (void)Menu_Reply(menu,
                     "Dataset stream disabled; ToF ranging remains active.");
  }
  else if ((argc == 3) &&
           (cli_token_equals(argv[1], "stream") != 0U) &&
           (cli_token_equals(argv[2], "status") != 0U))
  {
    TOF_App_Status_t status;
    TOF_App_GetStatus(&status);
    cli_print("Dataset stream: %s, submitted %" PRIu32
              ", dropped %" PRIu32 ", last frame %" PRIu32
              ", last CRC32 0x%08" PRIX32 "\r\n",
              (status.dataset_stream_enabled != 0U) ? "on" : "off",
              status.dataset_frames_submitted,
              status.dataset_frames_dropped,
              status.dataset_last_frame,
              status.dataset_last_crc32);
  }
  else
  {
    (void)Menu_Reply(menu, "Usage: DATASET STREAM ON|OFF|STATUS");
  }
}

static void cli_command_rps(Menu_t *menu, const char *command)
{
  char copy[CLI_LINE_SIZE];
  char *argv[CLI_MAX_ARGUMENTS];
  RPS_AI_Status_t status;
  int argc = cli_get_arguments(command, copy, sizeof(copy), argv,
                               CLI_MAX_ARGUMENTS);

  if ((argc == 2) && (cli_token_equals(argv[1], "on") != 0U))
  {
    RPS_AI_SetEnabled(1U);
    (void)Menu_Reply(menu, "Neural-ART rock/paper/scissors inference enabled.");
    return;
  }
  if ((argc == 2) && (cli_token_equals(argv[1], "off") != 0U))
  {
    RPS_AI_SetEnabled(0U);
    (void)Menu_Reply(menu, "Neural-ART inference disabled; ToF acquisition remains active.");
    return;
  }
  if ((argc != 2) || (cli_token_equals(argv[1], "status") == 0U))
  {
    (void)Menu_Reply(menu, "Usage: RPS ON|OFF|STATUS");
    return;
  }

  RPS_AI_GetStatus(&status);
  cli_print("RPS status: enabled=%" PRIu32 " ready=%" PRIu32
            " frame=%" PRIu32 " class=%s class_id=%u confidence_permille=%u"
            " scores=%d,%d,%d,%d runs=%" PRIu32 " errors=%" PRIu32
            " last_error=%" PRId32 " inference_ms=%" PRIu32 "\r\n",
            status.enabled, status.ready, status.last_frame,
            RPS_AI_ClassName(status.class_id), (unsigned int)status.class_id,
            (unsigned int)status.confidence_per_mille,
            (int)status.scores[0], (int)status.scores[1],
            (int)status.scores[2], (int)status.scores[3],
            status.runs, status.errors, status.last_error,
            status.inference_ms);
}

static void cli_command_debug(Menu_t *menu, const char *command)
{
  char copy[CLI_LINE_SIZE];
  char *argv[CLI_MAX_ARGUMENTS];
  uint32_t level = UINT32_MAX;
  int argc = cli_get_arguments(command, copy, sizeof(copy), argv,
                               CLI_MAX_ARGUMENTS);

  if ((argc == 3) && (strcmp(argv[1], "ping") == 0))
  {
    if (cli_active_session->route.transport == APP_TRANSPORT_BLE)
    {
      Debug_UART_NcpTracePing("CLI parsed", (const uint8_t *)command,
                              strlen(command));
    }
    if (cli_active_session->route.transport == APP_TRANSPORT_USB)
    {
      cli_print("PONG %s %" PRIu32 "\r\n", argv[2], HAL_GetTick());
    }
    else
    {
      /* debug ping is a high-rate transport diagnostic. Do not append a
       * prompt on message-oriented BLE/Cloud sessions: a short probe token
       * then fits in one default-MTU notification, avoiding a second raw-data
       * AT transaction that can overlap the following inbound write. */
      cli_print("PONG %s %" PRIu32 "\r\n", argv[2], HAL_GetTick());
      cli_prompt_already_sent = 1U;
    }
    return;
  }

  if ((argc == 2) && (strcmp(argv[1], "route") == 0))
  {
    cli_print("CLI route: current=%s/%" PRIu32
              " usb=%" PRIu32 " cloud=%" PRIu32 "\r\n",
              cli_transport_name(cli_active_session->route.transport),
              cli_active_session->route.session_generation,
              cli_usb_session.route.session_generation,
              cli_cloud_session.route.session_generation);
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
    if (cli_ble_session != NULL)
    {
      cli_print("CLI route: ble=%" PRIu32 "\r\n",
                cli_ble_session->route.session_generation);
    }
    else
    {
      cli_print("CLI route: ble=not-allocated\r\n");
    }
#endif
    cli_print("M2 diagnostic: available=%" PRIu32
              " reset_generation=%s stale_route=%s"
              " credential_isolation=%s cancel_scoped=%s reset_scoped=%s\r\n",
              cli_m2_diagnostic.available,
              (cli_m2_diagnostic.reset_changes_generation != 0U) ?
                  "pass" : "fail",
              (cli_m2_diagnostic.saved_route_becomes_stale != 0U) ?
                  "pass" : "fail",
              (cli_m2_diagnostic.credential_isolation != 0U) ?
                  "pass" : "fail",
              (cli_m2_diagnostic.cancel_is_scoped != 0U) ?
                  "pass" : "fail",
              (cli_m2_diagnostic.reset_is_scoped != 0U) ?
                  "pass" : "fail");
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
    cli_print("Wi-Fi results: routed=%" PRIu32 " stale=%" PRIu32
              " write_errors=%" PRIu32 " deferred_overflow=%" PRIu32
              " cloud_pending=%" PRIu32 "\r\n",
              cli_wifi_results_routed, cli_wifi_results_stale,
              cli_wifi_result_write_errors,
              cli_wifi_results_deferred_overflow,
              (uint32_t)cli_cloud_wifi_request_id);
#endif
    return;
  }

  if ((argc == 2) && (strcmp(argv[1], "uart") == 0))
  {
    DebugUart_Status_t status;
    AppLogging_Status_t logging_status;
    const char *test_name;

    Debug_UART_GetStatus(&status);
    App_Logging_GetStatus(&logging_status);
    test_name = (status.test_kind == DEBUG_UART_TEST_BURST) ? "burst" :
                (status.test_kind == DEBUG_UART_TEST_OVERFLOW) ? "overflow" :
                "none";
    cli_print("Debug UART: initialized=%" PRIu32
              " queued=%" PRIu32 " sent=%" PRIu32
              " dropped=%" PRIu32 " queue_full=%" PRIu32
              " pool_full=%" PRIu32 " contention=%" PRIu32
              " oversize=%" PRIu32 " context=%" PRIu32
              " transport=%" PRIu32 " internal=%" PRIu32
              " timeouts=%" PRIu32 " hal_errors=%" PRIu32
              " in_use=%" PRIu32 " capacity=%" PRIu32
              " high_water=%" PRIu32
              " stack_bytes=%" PRIu32 " stack_min_free=%" PRIu32 "\r\n",
              status.initialized, status.queued_messages,
              status.sent_messages, status.dropped_messages,
              status.queue_full_events, status.pool_exhaustions,
              status.producer_contentions, status.oversize_rejections,
              status.context_rejections, status.transport_failures,
              status.internal_errors, status.tx_timeouts,
              status.hal_errors, status.slots_in_use,
              status.slot_capacity, status.queue_high_water,
              status.task_stack_bytes,
              status.task_stack_min_free_bytes);
    cli_print("ST-LINK input: rx_overruns=%" PRIu32
              " rx_errors=%" PRIu32 " watch=%c (0=off)\r\n",
              status.rx_overruns, status.rx_errors,
              (status.watch_component != 0U) ?
                  (int)status.watch_component : '0');
    cli_print("Debug UART test: state=%s kind=%s run=%" PRIu32
              " completed=%" PRIu32 " attempted=%" PRIu32
              " queued_delta=%" PRIu32 " sent_delta=%" PRIu32
              " dropped_delta=%" PRIu32 " queue_full_delta=%" PRIu32
              " pool_full_delta=%" PRIu32 " contention_delta=%" PRIu32
              " oversize_delta=%" PRIu32 " timeout_delta=%" PRIu32
              " hal_error_delta=%" PRIu32 " flush=%" PRId32 "\r\n",
              (status.test_running != 0U) ? "running" : "idle",
              test_name, status.test_run_id, status.test_completed_runs,
              status.test_attempted, status.test_queued_delta,
              status.test_sent_delta, status.test_dropped_delta,
              status.test_queue_full_delta,
              status.test_pool_exhaustion_delta,
              status.test_contention_delta, status.test_oversize_delta,
              status.test_timeout_delta, status.test_hal_error_delta,
              status.test_flush_status);
    cli_print("ST67 logging: submitted=%" PRIu32
              " buffer_exhaustions=%" PRIu32
              " interrupt_rejections=%" PRIu32
              " format_errors=%" PRIu32 "\r\n",
              logging_status.submitted_messages,
              logging_status.buffer_exhaustions,
              logging_status.interrupt_rejections,
              logging_status.format_errors);
    return;
  }

  if ((argc == 3) && (strcmp(argv[1], "uart") == 0) &&
      (strcmp(argv[2], "burst") == 0))
  {
    uint32_t run_id = 0U;
    int32_t start_status =
        Debug_UART_StartTest(DEBUG_UART_TEST_BURST, &run_id);

    cli_print("Debug UART burst: %s run=%" PRIu32 " status=%" PRId32
              "; use 'debug uart' for asynchronous progress/result\r\n",
              (start_status == 0) ? "started" : "not started",
              run_id, start_status);
    return;
  }

  if ((argc == 3) && (strcmp(argv[1], "uart") == 0) &&
      (strcmp(argv[2], "overflow") == 0))
  {
    uint32_t run_id = 0U;
    int32_t start_status =
        Debug_UART_StartTest(DEBUG_UART_TEST_OVERFLOW, &run_id);

    cli_print("Debug UART overflow: %s run=%" PRIu32 " status=%" PRId32
              "; use 'debug uart' for asynchronous progress/result\r\n",
              (start_status == 0) ? "started" : "not started",
              run_id, start_status);
    return;
  }

  if (argc != 2)
  {
    cli_print("Debug level: %s. Usage: debug off|error|warn|info|debug | debug ping <token> | debug route | debug uart [burst|overflow]\r\n",
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
    (void)Menu_Reply(menu,
                     "Usage: debug off|error|warn|info|debug | debug ping <token> | debug route | debug uart [burst|overflow]");
  }
  else
  {
    App_Logging_SetVerbosity(level);
    cli_print("ST67 log level set to %s.\r\n",
              cli_log_level_name(level));
  }
}

static void cli_command_radio(Menu_t *menu, const char *command)
{
  char copy[CLI_LINE_SIZE];
  char *argv[CLI_MAX_ARGUMENTS];
  int argc = cli_get_arguments(command, copy, sizeof(copy), argv,
                               CLI_MAX_ARGUMENTS);

  if ((argc == 2) && (strcmp(argv[1], "hardware") == 0))
  {
    WifiBle_HardwareStatus_t hardware;

    WIFI_BLE_App_GetHardwareStatus(&hardware);
    cli_print("ST67 hardware baseline:\r\n"
              "  build: radio %s, BLE GATT %s, Wi-Fi services %s\r\n"
              "  SPI5: %s, RX DMA %s, TX DMA %s, configured 30 Mbit/s\r\n"
              "  pins: CHIP_EN=%s BOOT=%s CS=%s (active HIGH) SPI_RDY=%s\r\n"
              "  EXTI9 owner: %s\r\n"
              "  manual checks still required: VDDIO=3.3V, JP1/JP2 closed, "
              "SB31/SB34 open\r\n",
              (hardware.radio_enabled != 0U) ? "enabled" : "disabled",
              (hardware.ble_gatt_enabled != 0U) ? "enabled" : "disabled",
              (hardware.wifi_services_enabled != 0U) ? "enabled" : "disabled",
              (hardware.spi_initialized != 0U) ? "initialized" : "not initialized",
              (hardware.spi_rx_dma_ready != 0U) ? "ready" : "missing",
              (hardware.spi_tx_dma_ready != 0U) ? "ready" : "missing",
              (hardware.chip_enable_level != 0U) ? "HIGH" : "LOW",
              (hardware.boot_level != 0U) ? "HIGH" : "LOW",
              (hardware.chip_select_level != 0U) ? "HIGH" : "LOW",
              (hardware.spi_ready_level != 0U) ? "HIGH" : "LOW",
              (hardware.exti9_owner == WIFI_BLE_EXTI9_OWNER_RADIO) ?
                  "PE9/SPI_RDY (ToF polls PD9)" : "PD9/ToF");
    return;
  }

  if ((argc == 2) && (strcmp(argv[1], "status") == 0))
  {
    WifiBle_RuntimeStatus_t runtime;
    WifiBle_HardwareStatus_t hardware;
    const char *init_result;

    WIFI_BLE_App_GetRuntimeStatus(&runtime);
    WIFI_BLE_App_GetHardwareStatus(&hardware);
    if (runtime.state == WIFI_BLE_STATE_READY)
    {
      init_result = "passed";
    }
    else if (runtime.state == WIFI_BLE_STATE_ERROR)
    {
      init_result = "failed; inspect CDC boot log";
    }
    else if (runtime.state == WIFI_BLE_STATE_STARTING)
    {
      init_result = "in progress";
    }
    else
    {
      init_result = "not run";
    }

    cli_print("ST67 radio status:\r\n"
              "  manager: %s\r\n"
              "  W6X_Init: %s\r\n"
              "  BLE maintenance GATT: %s, advertising: %s, link: %s\r\n"
              "  Wi-Fi services: %s\r\n"
              "  Radio loop: count=%" PRIu32 " last_ms=%" PRIu32
              " max_gap_ms=%" PRIu32 "\r\n"
              "  BLE TX pump: last_ms=%" PRIu32
              " max_gap_ms=%" PRIu32 "\r\n",
              cli_radio_state_name(runtime.state),
              init_result,
              (runtime.ble_gatt_ready != 0U) ? "ready" :
                  ((hardware.ble_gatt_enabled != 0U) ? "initializing" : "disabled"),
              (runtime.ble_advertising != 0U) ? "on" : "off",
              (runtime.ble_connected != 0U) ? "connected" : "disconnected",
              (hardware.wifi_services_enabled != 0U) ? "enabled" : "disabled",
              runtime.loop_count, runtime.last_loop_tick,
              runtime.max_loop_gap_ticks, runtime.last_ble_tx_tick,
              runtime.max_ble_tx_gap_ticks);
    return;
  }

#if (APP_ST67W6X_ENABLED == 1U)
  if ((argc == 2) && (strcmp(argv[1], "info") == 0))
  {
    W6X_ModuleInfo_t *info;

    if (cli_radio_is_ready() == 0U) return;
    info = W6X_GetModuleInfo();
    if (info != NULL)
    {
      cli_print("Module: %s (%s)\r\n"
                "NCP MAC: %02X:%02X:%02X:%02X:%02X:%02X\r\n"
                "Build: %.31s\r\n"
                "SDK: %u.%u.%u.%u, AT: %u.%u.%u.%u\r\n"
                "Wi-Fi MAC FW: %u.%u.%u.%u\r\n"
                "BLE controller: %u.%u.%u.%u, stack: %u.%u.%u.%u\r\n"
                "Anti-rollback (read-only): bootloader=%u, app=%u\r\n"
                "Manufacturing: BOM=%u, year=%u, week=%u\r\n",
                info->ModuleID.ModuleName,
                W6X_ModelToStr(info->ModuleID.ModuleID),
                info->Mac_Address[0], info->Mac_Address[1],
                info->Mac_Address[2], info->Mac_Address[3],
                info->Mac_Address[4], info->Mac_Address[5],
                (const char *)info->Build_Date,
                (unsigned int)info->SDK_Version.Major,
                (unsigned int)info->SDK_Version.Sub1,
                (unsigned int)info->SDK_Version.Sub2,
                (unsigned int)info->SDK_Version.Patch,
                (unsigned int)info->AT_Version.Major,
                (unsigned int)info->AT_Version.Sub1,
                (unsigned int)info->AT_Version.Sub2,
                (unsigned int)info->AT_Version.Patch,
                (unsigned int)info->WiFi_MAC_Version.Major,
                (unsigned int)info->WiFi_MAC_Version.Sub1,
                (unsigned int)info->WiFi_MAC_Version.Sub2,
                (unsigned int)info->WiFi_MAC_Version.Patch,
                (unsigned int)info->BT_Controller_Version.Major,
                (unsigned int)info->BT_Controller_Version.Sub1,
                (unsigned int)info->BT_Controller_Version.Sub2,
                (unsigned int)info->BT_Controller_Version.Patch,
                (unsigned int)info->BT_Stack_Version.Major,
                (unsigned int)info->BT_Stack_Version.Sub1,
                (unsigned int)info->BT_Stack_Version.Sub2,
                (unsigned int)info->BT_Stack_Version.Patch,
                (unsigned int)info->AntiRollbackBootloader,
                (unsigned int)info->AntiRollbackApp,
                (unsigned int)info->BomID,
                (unsigned int)info->Manufacturing_Year,
                (unsigned int)info->Manufacturing_Week);
    }
    return;
  }
#endif

#if (APP_ST67W6X_ENABLED == 1U)
  (void)Menu_Reply(menu, "Usage: radio hardware|status|info");
#else
  (void)Menu_Reply(menu, "Usage: radio hardware|status");
#endif
}

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
static void cli_command_wifi(Menu_t *menu, const char *command)
{
  char copy[CLI_LINE_SIZE];
  char *argv[CLI_MAX_ARGUMENTS];
  int argc = cli_get_arguments(command, copy, sizeof(copy), argv,
                               CLI_MAX_ARGUMENTS);

  if ((argc == 2) &&
      ((strcmp(argv[1], "status") == 0) || (strcmp(argv[1], "ip") == 0)))
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
    (void)Menu_Reply(menu, "Usage: wifi connect \"SSID\"");
  }
  else if ((argc == 3) && (strcmp(argv[1], "connect") == 0))
  {
    size_t ssid_length;

    if (cli_radio_is_ready() == 0U) return;
    cli_session_clear_credentials(cli_active_session);
    ssid_length = strlen(argv[2]);
    if ((ssid_length == 0U) || (ssid_length > W6X_WIFI_MAX_SSID_SIZE))
    {
      (void)Menu_Reply(menu, "Invalid SSID length.");
    }
    else
    {
      (void)memset(cli_active_session->pending_ssid, 0,
                   sizeof(cli_active_session->pending_ssid));
      (void)memcpy(cli_active_session->pending_ssid, argv[2], ssid_length);
      cli_secret_mode = CLI_SECRET_WIFI_PASSWORD;
      cli_pending_password_length = 0U;
      (void)memset(cli_menu_input, 0, sizeof(cli_menu_input));
      if (Menu_Reply(menu, "Password (input hidden):") != MENU_STATUS_OK)
      {
        cli_session_clear_credentials(cli_active_session);
        Debug_UART_Log("CLI", "Wi-Fi password prompt delivery failed; credentials cleared");
      }
    }
  }
  else if ((argc >= 2) && (strcmp(argv[1], "disconnect") == 0))
  {
    WifiBle_WifiRequest_t request;
    AppRequestId_t request_id = 0U;
    UINT status;

    if (cli_radio_is_ready() == 0U) return;
    cli_session_clear_credentials(cli_active_session);
    if ((argc > 3) || ((argc == 3) && (strcmp(argv[2], "forget") != 0)))
    {
      (void)Menu_Reply(menu, "Usage: wifi disconnect [forget]");
      return;
    }
    (void)memset(&request, 0, sizeof(request));
    request.operation = WIFI_BLE_WIFI_OPERATION_DISCONNECT;
    request.route = cli_active_session->route;
    request.forget = ((argc == 3) && (strcmp(argv[2], "forget") == 0)) ? 1U : 0U;
    status = WIFI_BLE_App_WifiSubmit(&request, &request_id);
    if (status != TX_SUCCESS)
    {
      cli_print("Wi-Fi disconnect request rejected (ThreadX %u).\r\n",
                (unsigned int)status);
      return;
    }
    cli_print("Wi-Fi disconnect request accepted: id=%" PRIu32 ".\r\n",
              (uint32_t)request_id);
    cli_wifi_note_submission(request_id);
  }
  else
  {
    (void)Menu_Reply(menu,
                     "Usage: wifi status|ip|scan|connect \"SSID\"|disconnect [forget]");
  }
}
#endif

#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static void cli_command_ble(Menu_t *menu, const char *command)
{
  char copy[CLI_LINE_SIZE];
  char *argv[CLI_MAX_ARGUMENTS];
  int argc = cli_get_arguments(command, copy, sizeof(copy), argv,
                               CLI_MAX_ARGUMENTS);

  if ((argc == 2) && (strcmp(argv[1], "status") == 0))
  {
    if (cli_radio_is_ready() == 0U) return;
    cli_ble_status();
  }
  else if ((argc == 3) && (strcmp(argv[1], "adv") == 0))
  {
    UINT status;

    if (cli_radio_is_ready() == 0U) return;
    if (strcmp(argv[2], "on") == 0)
    {
      status = WIFI_BLE_App_RequestAdvertising(1U);
    }
    else if (strcmp(argv[2], "off") == 0)
    {
      status = WIFI_BLE_App_RequestAdvertising(0U);
    }
    else
    {
      (void)Menu_Reply(menu, "Usage: ble adv on|off");
      return;
    }
    cli_print("BLE advertising request: %s\r\n",
              (status == TX_SUCCESS) ? "queued" : "not available");
  }
  else if ((argc == 2) && (strcmp(argv[1], "disconnect") == 0))
  {
    WifiBle_RuntimeStatus_t runtime;

    if (cli_radio_is_ready() == 0U) return;
    WIFI_BLE_App_GetRuntimeStatus(&runtime);
    if (runtime.ble_connected == 0U)
    {
      (void)Menu_Reply(menu, "BLE is not connected.");
    }
    else
    {
      UINT status = WIFI_BLE_App_RequestDisconnect();
      cli_print("BLE disconnect request: %s\r\n",
                (status == TX_SUCCESS) ? "queued" : "not available");
    }
  }
  else
  {
    (void)Menu_Reply(menu, "Usage: ble status|adv on|adv off|disconnect");
  }
}
#endif

#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
static void cli_command_cloud(Menu_t *menu, const char *command)
{
  char copy[CLI_LINE_SIZE];
  char *argv[CLI_MAX_ARGUMENTS];
  int argc = cli_get_arguments(command, copy, sizeof(copy), argv,
                               CLI_MAX_ARGUMENTS);

  if ((argc == 2) && (strcmp(argv[1], "status") == 0))
  {
    CloudRelay_Status_t status;
    CloudRelay_GetStatus(&status);
    cli_print("Cloud Relay: %s, %s, endpoint %s://%s\r\n"
              "Transport security: %s\r\n"
              "Device: %s, workspace: %s, generation %lu\r\n"
              "HTTP: active %lu, last %ld, transport %ld, backoff %lu s\r\n"
              "CLI: input %lu, output %lu, received %lu, acked %lu, sent %lu\r\n"
              "ToF: sent %lu, dropped %lu; request errors %lu\r\n"
              "Worker: loops %lu, last tick %lu, max step %lu ms\r\n"
              "Control queue: %lu/4, high water %lu, rejected %lu\r\n",
              cli_cloud_state_name(status.state),
              (status.paired != 0U) ? "paired" : "not paired",
              CLOUD_RELAY_SCHEME,
              CLOUD_RELAY_HOST,
#if (APP_ST67W6X_CLOUD_USE_TLS == 0U)
              "NONE - plaintext HTTP; pairing/token/CLI exposed (demo only)",
#else
              (APP_ST67W6X_CLOUD_TLS_VERIFY_SERVER != 0U) ?
                  "TLS certificate verified" : "TLS verification DISABLED (insecure demo)",
#endif
              status.device_id,
              (status.workspace_id[0] != '\0') ? status.workspace_id : "-",
              (unsigned long)status.generation,
              (unsigned long)status.request_active,
              (long)status.last_http_status,
              (long)status.last_transport_status,
              (unsigned long)status.backoff_seconds,
              (unsigned long)status.input_ready,
              (unsigned long)status.output_queued,
              (unsigned long)status.commands_received,
              (unsigned long)status.commands_acked,
              (unsigned long)status.output_records,
              (unsigned long)status.tof_frames_sent,
              (unsigned long)status.tof_frames_dropped,
              (unsigned long)status.request_errors,
              (unsigned long)status.worker_loops,
              (unsigned long)status.worker_last_tick,
              (unsigned long)status.worker_max_step_ms,
              (unsigned long)status.control_queued,
              (unsigned long)status.control_high_water,
              (unsigned long)status.control_rejected);
  }
  else if ((argc == 2) && (strcmp(argv[1], "endpoint") == 0))
  {
    cli_print("Cloud Relay endpoint: %s://%s/\r\n",
              CLOUD_RELAY_SCHEME, CLOUD_RELAY_HOST);
  }
  else if ((argc == 3) && (strcmp(argv[1], "pair") == 0))
  {
    UINT result = CloudRelay_RequestPair(argv[2]);
    cli_print("Cloud pairing request: %s.\r\n",
              (result == TX_SUCCESS) ? "queued" : "invalid code or unavailable");
  }
  else if ((argc == 2) && (strcmp(argv[1], "enable") == 0))
  {
    cli_print("Cloud Relay: %s.\r\n",
              (CloudRelay_SetEnabled(1U) == TX_SUCCESS) ? "enable queued" : "unavailable");
  }
  else if ((argc == 2) && (strcmp(argv[1], "disable") == 0))
  {
    cli_print("Cloud Relay: %s.\r\n",
              (CloudRelay_SetEnabled(0U) == TX_SUCCESS) ? "disable queued" : "unavailable");
  }
  else if ((argc == 2) &&
           ((strcmp(argv[1], "reconnect") == 0) ||
            (strcmp(argv[1], "test") == 0)))
  {
    cli_print("Cloud reconnect/test: %s.\r\n",
              (CloudRelay_RequestReconnect() == TX_SUCCESS) ? "queued" : "unavailable");
  }
  else if ((argc == 3) && (strcmp(argv[1], "unpair") == 0) &&
           (strcmp(argv[2], "yes") == 0))
  {
    cli_print("Cloud unpair: %s.\r\n",
              (CloudRelay_Unpair() == TX_SUCCESS) ? "queued" : "unavailable");
  }
  else
  {
    (void)Menu_Reply(menu,
        "Usage: cloud status|endpoint|test|pair <6 digits>|enable|disable|reconnect|unpair yes");
  }
}
#endif

static void cli_command_reboot(Menu_t *menu, const char *command)
{
  char copy[CLI_LINE_SIZE];
  char *argv[CLI_MAX_ARGUMENTS];
  int argc = cli_get_arguments(command, copy, sizeof(copy), argv,
                               CLI_MAX_ARGUMENTS);

  if ((argc == 2) && (strcmp(argv[1], "yes") == 0))
  {
    (void)Menu_Reply(menu, "Rebooting...");
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 10U);
    NVIC_SystemReset();
  }
  else
  {
    (void)Menu_Reply(menu, "Usage: reboot yes");
  }
}

static void cli_command_firmware_update(Menu_t *menu, const char *command)
{
  (void)command;
  if (Firmware_Update_IsActive() != 0U)
  {
    (void)Menu_Reply(menu, "A firmware update is already active.");
    return;
  }
  Menu_Reset(menu);
  TOF_App_SetDatasetStreamEnabled(0U);
  cli_update_session = cli_active_session;
  const char *transport_name =
      (cli_update_session->route.transport == APP_TRANSPORT_BLE) ? "BLE CLI" :
      (cli_update_session->route.transport == APP_TRANSPORT_CLOUD) ? "Cloud CLI" :
      "USB CDC";
  if (Firmware_Update_Start(
          cli_update_write, cli_update_session, transport_name) != 0)
  {
    cli_update_session = NULL;
    (void)Menu_Reply(menu, "Unable to start firmware update mode.");
  }
}

static void cli_command_unknown(Menu_t *menu, const char *command)
{
  (void)command;
  (void)Menu_Reply(menu, "Unknown command. Type 'help'.");
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

static int cli_get_arguments(const char *command, char *copy,
                             size_t copy_size, char *argv[],
                             int max_arguments)
{
  size_t length;

  if ((command == NULL) || (copy == NULL) || (copy_size == 0U) ||
      (argv == NULL) || (max_arguments <= 0))
  {
    return 0;
  }

  length = strlen(command);
  if (length >= copy_size)
  {
    return 0;
  }

  (void)memcpy(copy, command, length + 1U);
  return cli_split_arguments(copy, argv, max_arguments);
}

static int32_t cli_menu_send(const char *text, size_t length, void *context)
{
  CliSession_t *session = (CliSession_t *)context;

  if ((session == NULL) || (text == NULL) || (length == 0U))
  {
    return 0;
  }

  return (int32_t)cli_session_write(session, text, (ULONG)length);
}

static UINT cli_session_write(CliSession_t *session, const void *buffer,
                              ULONG length)
{
  if ((session == NULL) || (buffer == NULL) || (length == 0U))
  {
    return TX_PTR_ERROR;
  }

#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  if (session->route.transport == APP_TRANSPORT_BLE)
  {
    return WIFI_BLE_App_StreamWrite(WIFI_BLE_STREAM_CLI, buffer, length,
                                    CLI_BLE_TX_WAIT_TICKS);
  }
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  if (session->route.transport == APP_TRANSPORT_CLOUD)
  {
    return CloudRelay_WriteOutput(buffer, (size_t)length, 0U);
  }
#endif
  return App_Console_Write(buffer, length);
}

static int32_t cli_update_write(const void *buffer, size_t length,
                                void *context)
{
  CliSession_t *session = (CliSession_t *)context;

  if ((session == NULL) || (length > UINT32_MAX))
  {
    return -1;
  }
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  if (session->route.transport == APP_TRANSPORT_CLOUD)
  {
    uint32_t binary = 0U;
    if ((length == 1U) && (buffer != NULL))
    {
      uint8_t value = *(const uint8_t *)buffer;
      binary = ((value == 0x43U) || (value == 0x06U) ||
                (value == 0x15U) || (value == 0x18U)) ? 1U : 0U;
    }
    return (CloudRelay_WriteOutput(buffer, length, binary) == TX_SUCCESS) ?
           0 : -1;
  }
#endif
  return (cli_session_write(session, buffer, (ULONG)length) == TX_SUCCESS) ?
         0 : -1;
}

static uint32_t cli_token_equals(const char *left, const char *right)
{
  if ((left == NULL) || (right == NULL))
  {
    return 0U;
  }

  while ((*left != '\0') && (*right != '\0'))
  {
    char left_value = *left;
    char right_value = *right;
    if ((left_value >= 'A') && (left_value <= 'Z'))
    {
      left_value = (char)(left_value - 'A' + 'a');
    }
    if ((right_value >= 'A') && (right_value <= 'Z'))
    {
      right_value = (char)(right_value - 'A' + 'a');
    }
    if (left_value != right_value)
    {
      return 0U;
    }
    left++;
    right++;
  }
  return ((*left == '\0') && (*right == '\0')) ? 1U : 0U;
}

static uint32_t cli_prefix_matches(const char *text, const char *prefix)
{
  if ((text == NULL) || (prefix == NULL))
  {
    return 0U;
  }

  while (*prefix != '\0')
  {
    char text_value = *text;
    char prefix_value = *prefix;
    if (text_value == '\0')
    {
      return 0U;
    }
    if ((text_value >= 'A') && (text_value <= 'Z'))
    {
      text_value = (char)(text_value - 'A' + 'a');
    }
    if ((prefix_value >= 'A') && (prefix_value <= 'Z'))
    {
      prefix_value = (char)(prefix_value - 'A' + 'a');
    }
    if (text_value != prefix_value)
    {
      return 0U;
    }
    ++text;
    ++prefix;
  }
  return 1U;
}

static int cli_parse_u32(const char *text, uint32_t *value)
{
  uint32_t parsed = 0U;

  if ((text == NULL) || (value == NULL) || (*text == '\0') || (*text == '-'))
  {
    return 0;
  }

  while (*text != '\0')
  {
    uint32_t digit;
    if ((*text < '0') || (*text > '9'))
    {
      return 0;
    }
    digit = (uint32_t)(*text - '0');
    if (parsed > ((UINT32_MAX - digit) / 10U))
    {
      return 0;
    }
    parsed = (parsed * 10U) + digit;
    ++text;
  }

  *value = parsed;
  return 1;
}

static void cli_redraw_input(void)
{
  const char *input = Menu_GetPendingInput(&cli_menu);

  cli_print("\r\033[K");
  cli_prompt();
  if ((input != NULL) && (*input != '\0'))
  {
    cli_print("%s", input);
  }
}

static void cli_history_record(const char *command)
{
  size_t length;
  char *destination;

  if (command == NULL)
  {
    return;
  }
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
  /* Do not retain the SSID-bearing credential command after submission. */
  if ((cli_prefix_matches(command, "wifi connect") != 0U) &&
      ((command[12] == '\0') || (command[12] == ' ') ||
       (command[12] == '\t')))
  {
    return;
  }
#endif
  length = strlen(command);
  while ((length != 0U) &&
         ((command[length - 1U] == ' ') || (command[length - 1U] == '\t')))
  {
    --length;
  }
  if (length == 0U)
  {
    return;
  }

  if ((cli_history_count != 0U) &&
      (strlen(cli_history[cli_history_count - 1U]) == length) &&
      (strncmp(cli_history[cli_history_count - 1U], command, length) == 0))
  {
    return;
  }

  if (cli_history_count < CLI_HISTORY_DEPTH)
  {
    destination = cli_history[cli_history_count++];
  }
  else
  {
    (void)memmove(cli_history[0], cli_history[1],
                  (CLI_HISTORY_DEPTH - 1U) * sizeof(cli_history[0]));
    destination = cli_history[CLI_HISTORY_DEPTH - 1U];
  }

  (void)memcpy(destination, command, length);
  destination[length] = '\0';
}

static void cli_history_move(int direction)
{
  const char *replacement;

  if (cli_history_count == 0U)
  {
    cli_print("\a");
    return;
  }

  if (direction < 0)
  {
    if (cli_history_index >= cli_history_count)
    {
      const char *pending = Menu_GetPendingInput(&cli_menu);
      size_t length = (pending != NULL) ? strlen(pending) : 0U;
      if (pending != NULL)
      {
        (void)memcpy(cli_history_draft, pending, length + 1U);
      }
      else
      {
        cli_history_draft[0] = '\0';
      }
      cli_history_index = cli_history_count - 1U;
    }
    else if (cli_history_index != 0U)
    {
      --cli_history_index;
    }
    else
    {
      cli_print("\a");
    }
  }
  else
  {
    if (cli_history_index >= cli_history_count)
    {
      cli_print("\a");
      return;
    }
    ++cli_history_index;
  }

  replacement = (cli_history_index < cli_history_count) ?
      cli_history[cli_history_index] : cli_history_draft;
  if (Menu_SetPendingInput(&cli_menu, replacement) == MENU_STATUS_OK)
  {
    cli_redraw_input();
  }
}

static void cli_complete_input(void)
{
  const char *input = Menu_GetPendingInput(&cli_menu);
  size_t input_length = Menu_GetPendingLength(&cli_menu);
  char candidate[CLI_LINE_SIZE];
  char common[CLI_LINE_SIZE];
  size_t common_length = 0U;
  size_t match_count = 0U;
  size_t candidate_count = cli_completion_candidate_count();
  size_t index;

  if (input == NULL)
  {
    return;
  }

  for (index = 0U; index < candidate_count; ++index)
  {
    if ((cli_completion_candidate(index, candidate, sizeof(candidate)) == 0) &&
        (cli_prefix_matches(candidate, input) != 0U))
    {
      if (match_count == 0U)
      {
        (void)memcpy(common, candidate, strlen(candidate) + 1U);
        common_length = strlen(common);
      }
      else
      {
        size_t position = 0U;
        while ((position < common_length) && (candidate[position] != '\0'))
        {
          char left = common[position];
          char right = candidate[position];
          if ((left >= 'A') && (left <= 'Z')) left = (char)(left - 'A' + 'a');
          if ((right >= 'A') && (right <= 'Z')) right = (char)(right - 'A' + 'a');
          if (left != right) break;
          ++position;
        }
        common_length = position;
        common[common_length] = '\0';
      }
      ++match_count;
    }
  }

  if (match_count == 0U)
  {
    cli_print("\a");
    return;
  }

  if (match_count == 1U)
  {
    common_length = strlen(common);
    if ((common_length < (sizeof(common) - 1U)) &&
        (common_length != 0U) && (common[common_length - 1U] != ' '))
    {
      common[common_length++] = ' ';
      common[common_length] = '\0';
    }
  }

  if (common_length > input_length)
  {
    if (Menu_SetPendingInput(&cli_menu, common) == MENU_STATUS_OK)
    {
      cli_history_index = cli_history_count;
      cli_redraw_input();
    }
    return;
  }

  cli_print("\r\n");
  for (index = 0U; index < candidate_count; ++index)
  {
    if ((cli_completion_candidate(index, candidate, sizeof(candidate)) == 0) &&
        (cli_prefix_matches(candidate, input) != 0U))
    {
      cli_print("  %s\r\n", candidate);
    }
  }
  cli_redraw_input();
}

static size_t cli_completion_candidate_count(void)
{
  size_t count = sizeof(cli_completion_base) /
                 sizeof(cli_completion_base[0]);
  size_t filter_index;

  for (filter_index = 0U;
       filter_index < TOF_ImageProcessing_GetFilterCount();
       ++filter_index)
  {
    const TOF_ImageFilterDescriptor_t *descriptor =
        TOF_ImageProcessing_GetDescriptorByIndex(filter_index);
    if (descriptor != NULL)
    {
      count += 1U + descriptor->parameter_count;
    }
  }
  return count;
}

static int cli_completion_candidate(size_t index, char *candidate,
                                    size_t capacity)
{
  size_t base_count = sizeof(cli_completion_base) /
                      sizeof(cli_completion_base[0]);
  size_t filter_index;

  if ((candidate == NULL) || (capacity == 0U))
  {
    return -1;
  }
  if (index < base_count)
  {
    int length = snprintf(candidate, capacity, "%s",
                          cli_completion_base[index]);
    return ((length >= 0) && ((size_t)length < capacity)) ? 0 : -1;
  }
  index -= base_count;

  for (filter_index = 0U;
       filter_index < TOF_ImageProcessing_GetFilterCount();
       ++filter_index)
  {
    const TOF_ImageFilterDescriptor_t *descriptor =
        TOF_ImageProcessing_GetDescriptorByIndex(filter_index);
    size_t parameter_index;

    if (descriptor == NULL)
    {
      continue;
    }
    if (index == 0U)
    {
      int length = snprintf(candidate, capacity, "MAP PROCESSING %s ",
                            descriptor->command);
      return ((length >= 0) && ((size_t)length < capacity)) ? 0 : -1;
    }
    --index;

    for (parameter_index = 0U;
         parameter_index < descriptor->parameter_count;
         ++parameter_index)
    {
      if (index == 0U)
      {
        int length = snprintf(candidate, capacity,
                              "MAP PROCESSING %s %s ",
                              descriptor->command,
                              descriptor->parameters[parameter_index].name);
        return ((length >= 0) && ((size_t)length < capacity)) ? 0 : -1;
      }
      --index;
    }
  }
  return -1;
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
    UINT write_status;
    if (send_length >= sizeof(cli_print_buffer)) send_length = sizeof(cli_print_buffer) - 1U;
    write_status = cli_session_write(cli_active_session, cli_print_buffer,
                                     send_length);
    if (cli_active_session->route.transport == APP_TRANSPORT_BLE)
    {
      Debug_UART_NcpTracePing(write_status == TX_SUCCESS ?
                              "CLI reply queued" : "CLI reply rejected",
                              (const uint8_t *)cli_print_buffer,
                              (size_t)send_length);
    }
  }
}

static void cli_prompt(void)
{
  cli_print("n6> ");
}

static void cli_show_help(void)
{
  cli_print("CLI HELP (%s)\r\n"
            "The same commands are available on USB CDC, BLE and Cloud CLI.\r\n"
            "Keys: Tab=complete, Up/Down=history, Ctrl-C=cancel.\r\n"
            "\r\nGeneral:\r\n"
            "  help | menu | ?\r\n"
            "  version\r\n"
            "  status\r\n"
            "  usb status\r\n"
            "  clear\r\n",
            (cli_active_session->route.transport == APP_TRANSPORT_BLE) ?
                "BLE GATT CLI" :
            (cli_active_session->route.transport == APP_TRANSPORT_CLOUD) ?
                "Cloud CLI" : "USB CDC");

  cli_print("\r\nSensor, display and AI:\r\n"
            "  MAP ON | MAP OFF               ToF stream; dedicated image channel on BLE/Cloud\r\n"
            "  MAP CHANNELS [1..5]            list/toggle channels\r\n"
#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
            "  MAP ON|OFF SCREEN|DISPLAY\r\n"
            "  MAP SCREEN|DISPLAY ON|OFF      equivalent syntax\r\n"
#endif
            "  tof status|pause|resume\r\n"
            "  DATASET STREAM ON|OFF|STATUS\r\n"
            "  RPS ON|OFF|STATUS\r\n");

  cli_print("\r\nMap processing (USB+BLE+Cloud):\r\n"
            "  MAP PROCESSING                       list filters/values/ranges\r\n"
            "  MAP PROCESSING OFF|BOX|MEDIAN|GAUSSIAN|SHARPEN|MIN|MAX\r\n"
            "  MAP PROCESSING OBJECT 1..7 | NPU    stages or exact NPU input\r\n"
            "  MAP PROCESSING <filter> <value>      single-parameter form\r\n"
            "  MAP PROCESSING <filter> <parameter> <value>\r\n"
            "  Parameters: BOX radius/passes; MEDIAN radius/threshold_mm;\r\n"
            "              GAUSSIAN radius/passes; SHARPEN radius/amount_percent;\r\n"
            "              MIN/MAX radius; OBJECT 7 threshold.\r\n");

  cli_print("\r\nRadio and Wi-Fi:\r\n"
            "  debug off|error|warn|info|debug\r\n"
            "  debug ping <token>           transport-only latency probe\r\n"
            "  debug route                  session generations + M2 isolation diagnostic\r\n"
            "  debug uart                   asynchronous UART counters\r\n"
            "  debug uart burst             emit 100 ordered UART test lines\r\n"
            "  debug uart overflow          force bounded-queue drops; never stall\r\n"
            "  radio hardware|status"
#if (APP_ST67W6X_ENABLED == 1U)
            "|info"
#endif
            "\r\n"
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
            "  wifi status | wifi ip         link/DHCP addresses\r\n"
            "  wifi scan                     scan <=15 networks\r\n"
            "  wifi connect \"SSID\"          hidden password + DHCP\r\n"
            "  wifi disconnect [forget]      optionally erase credentials\r\n"
#endif
            );

#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  cli_print("\r\nCloud CLI via " CLOUD_RELAY_SCHEME " Relay:\r\n"
            "  cloud status | cloud endpoint\r\n"
            "  cloud pair <6-digit-code>     available from USB or BLE\r\n"
            "  cloud enable | cloud disable\r\n"
            "  cloud reconnect | cloud test\r\n"
            "  cloud unpair yes              delete the saved device token\r\n"
            "  CLI text/XMODEM and ToF use independent Cloud channels.\r\n");
#endif

  cli_print("\r\nBLE, update and reset:\r\n"
#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
            "  ble status                   GATT/link/MTU/queues\r\n"
            "  ble adv on | ble adv off\r\n"
            "  ble disconnect\r\n"
            "  BLE modes: CLI RX=Write, CLI TX=Notify; ToF image=dedicated Notify.\r\n"
            "             DEBUG TX=Notify; DEBUG RX is disabled by policy.\r\n"
            "  BLE ToF pixels stay on the dedicated ToF-image CCCD.\r\n"
#endif
            "  update                       signed XMODEM firmware update\r\n"
            "  reboot yes\r\n");
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
            "ToF: %s, map %s, channels 0x%02" PRIx32 ", active %" PRIu32 ", dataset %s, frame %" PRIu32 ", %" PRIu32 ".%" PRIu32 " fps\r\n"
            "ST67: %s, Wi-Fi %s, BLE %s, advertising %s\r\n"
            "Log level: %s\r\n",
            HAL_GetTick(), (usb.state_snapshot_busy != 0U) ? "unknown (busy)" :
                           ((usb.active != 0U) ? "active" : "inactive"),
            (unsigned long)usb.session,
            (unsigned long)usb.tx_queue_depth,
            (unsigned long)usb.rx_queue_depth,
            cli_tof_state_name(tof.state),
            (tof.map_enabled != 0U) ? "on" : "off",
            tof.map_channel_mask, (uint32_t)tof.map_active_channel,
            (tof.dataset_stream_enabled != 0U) ? "on" : "off",
            tof.frame_counter,
            tof.fps_x10 / 10U, tof.fps_x10 % 10U,
            cli_radio_state_name(radio.state),
            (radio.wifi_connected != 0U) ? ((radio.wifi_has_ip != 0U) ? "IP ready" : "connected") : "disconnected",
            (radio.ble_connected != 0U) ? "connected" : "disconnected",
            (radio.ble_advertising != 0U) ? "on" : "off",
            cli_log_level_name(App_Logging_GetVerbosity()));
#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
  cli_show_display_status();
#endif
}

static void cli_show_usb_status(void)
{
  USB_CDC_TransportStatus_t status;

  USB_CDC_Transport_GetStatus(&status);
  cli_print("USB CDC transport: %s, host %s, session %lu\r\n"
            "Static slots free: control %lu/8, maps %lu/2, RX %lu/16\r\n"
            "Queues: TX %lu/10, RX %lu/32, in-flight %lu\r\n"
            "TX: queued %lu, completed %lu, callbacks %lu, bytes %lu\r\n"
            "TX flow: dropped %lu, unavailable %lu, slot exhaustion %lu, queue failures %lu\r\n"
            "TX errors: callback timeouts %lu, errors %lu, last %lu\r\n"
            "RX: received %lu, delivered %lu, bytes %lu\r\n"
            "RX flow/errors: dropped %lu, slot exhaustion %lu, queue failures %lu, errors %lu, last %lu\r\n"
            "Worker synchronization failures: %lu\r\n",
            (status.state_snapshot_busy != 0U) ? "unknown (busy)" :
                ((status.active != 0U) ? "active" : "inactive"),
            (status.state_snapshot_busy != 0U) ? "unknown" :
                ((status.host_ready != 0U) ? "open (DTR)" : "closed"),
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
  platform_diagnostics_t i3c;
  TOF_ImageProcessingConfig_t processing;
  const TOF_ImageFilterDescriptor_t *filter;
  TOF_App_GetStatus(&status);
  platform_get_diagnostics(&i3c);
  TOF_App_GetMapProcessingConfig(&processing);
  filter = TOF_ImageProcessing_GetDescriptor(processing.selected_filter);
  cli_print("ToF state: %s\r\n"
            "Resolution: %" PRIu32 "x%" PRIu32 "\r\n"
            "Frame: %" PRIu32 ", rate: %" PRIu32 ".%" PRIu32 " fps\r\n"
            "Pipeline: acquired %" PRIu32 ", processed %" PRIu32 ", dropped %" PRIu32 ", queue failures %" PRIu32 "\r\n"
            "Last valid range: %" PRIu32 "..%" PRIu32 " mm\r\n"
            "Map: %s, channels: 0x%02" PRIx32 ", active: %" PRIu32 " %s, processing: %s, acquisition: %s\r\n",
            cli_tof_state_name(status.state), status.width, status.height,
            status.frame_counter, status.fps_x10 / 10U, status.fps_x10 % 10U,
            status.acquired_frames, status.processed_frames,
            status.dropped_frames, status.queue_failures,
            status.minimum_mm, status.maximum_mm,
            (status.map_enabled != 0U) ? "on" : "off",
            status.map_channel_mask, (uint32_t)status.map_active_channel,
            TOF_App_GetChannelName(status.map_active_channel),
            (filter != NULL) ? filter->display_name : "Off",
            (status.paused != 0U) ? "paused" : "running");
#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
  cli_show_display_status();
#endif
  if (status.state == TOF_APP_STATE_ERROR)
  {
    cli_print("Last error: %s (%d)\r\n",
              (status.error_stage != NULL) ? status.error_stage : "unknown",
              status.error_code);
  }
  cli_print("ToF commands: TX start failures=%" PRIu32
            ", TX completion failures=%" PRIu32
            ", status read failures=%" PRIu32
            ", status timeouts=%" PRIu32 "\r\n",
            status.command_start_failures,
            status.command_tx_wait_failures,
            status.command_status_read_failures,
            status.command_status_timeouts);
  cli_print("I3C failures: HAL errors=%" PRIu32
            ", start/read=%" PRIu32
            ", last stage=%" PRIu32 " HAL=%" PRIu32
            " tick=%" PRIu32 " code=0x%08" PRIx32
            " state=0x%02" PRIx32 " EVR=0x%08" PRIx32 "\r\n",
            i3c.i3c_error_count, i3c.i3c_start_failure_count,
            i3c.last_start_stage, i3c.last_start_hal_status,
            i3c.last_error_tick, i3c.last_error_code,
            i3c.last_i3c_state, i3c.last_evr);
}

static void cli_show_map_channels(void)
{
  uint32_t mask = TOF_App_GetMapChannelMask();

  cli_print("MAP sensor channels (enabled channels alternate one per sensor frame):\r\n");
  for (uint32_t channel = TOF_APP_CHANNEL_DEPTH;
       channel <= TOF_APP_CHANNEL_COUNT;
       ++channel)
  {
    uint32_t bit = 1UL << (channel - 1U);
    cli_print("  [%c] %" PRIu32 " %-11s - %s\r\n",
              ((mask & bit) != 0U) ? 'V' : ' ', channel,
              TOF_App_GetChannelName((TOF_App_Channel_t)channel),
              TOF_App_GetChannelDescription((TOF_App_Channel_t)channel));
  }
  cli_print("Toggle here with MAP CHANNELS <1..5>, or press 1..5 during MAP ON.\r\n");
}

#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
static void cli_show_display_status(void)
{
  Display_App_Status_t status;

  Display_App_GetStatus(&status);
  cli_print(
      "Display: %s, screen map %s, frame in flight %s\r\n"
      "Display screen: %s (last SPI-DMA render, not optical proof)\r\n"
      "Display frames: submitted %" PRIu32 ", rendered %" PRIu32
      ", dropped %" PRIu32 ", errors %" PRIu32 "\r\n"
      "Display frame IDs: submitted %" PRIu32 ", rendered %" PRIu32 "\r\n"
      "Display NPU result: valid %u, frame %" PRIu32
      ", class %s, confidence %u/1000\r\n"
      "Display DMA: completions %" PRIu32 ", errors %" PRIu32
      ", last frame %" PRIu32 ", clears %" PRIu32 "\r\n",
      (status.initialized != 0U) ? "ready" : "not ready",
      (status.map_enabled != 0U) ? "on" : "off",
      (status.frame_in_flight != 0U) ? "yes" : "no",
      (status.screen_state == DISPLAY_APP_SCREEN_LOADING) ? "SYSTEM IS LOADING" :
      (status.screen_state == DISPLAY_APP_SCREEN_SYSTEM_ON) ? "SYSTEM ON" :
      (status.screen_state == DISPLAY_APP_SCREEN_MAP) ? "map" : "none",
      status.submitted_frames, status.rendered_frames,
      status.dropped_frames, status.render_errors,
      status.last_submitted_frame, status.last_rendered_frame,
      (unsigned int)status.last_rendered_rps_valid,
      status.last_rendered_rps_frame,
      RPS_AI_ClassDisplayName(status.last_rendered_rps_class_id),
      (unsigned int)status.last_rendered_rps_confidence_per_mille,
      status.dma_completions, status.dma_errors,
      status.last_render_dma_completions, status.clear_operations);
}
#endif

static void cli_show_map_processing(void)
{
  TOF_ImageProcessingConfig_t config;
  size_t filter_index;

  TOF_App_GetMapProcessingConfig(&config);
  cli_print("MAP PROCESSING filters:\r\n");
  for (filter_index = 0U;
       filter_index < TOF_ImageProcessing_GetFilterCount();
       ++filter_index)
  {
    const TOF_ImageFilterDescriptor_t *descriptor =
        TOF_ImageProcessing_GetDescriptorByIndex(filter_index);
    size_t parameter_index;

    cli_print("  [%c] %-10s %-15s - %s\r\n",
              (config.selected_filter == descriptor->filter) ? 'V' : ' ',
              descriptor->command, descriptor->display_name,
              descriptor->description);
    for (parameter_index = 0U;
         parameter_index < descriptor->parameter_count;
         ++parameter_index)
    {
      const TOF_ImageFilterParameter_t *parameter =
          &descriptor->parameters[parameter_index];
      cli_print("       %-12s = %" PRIu32 " %s  (%" PRIu32 "..%" PRIu32 ")\r\n",
                parameter->name,
                config.values[(size_t)descriptor->filter][parameter_index],
                parameter->unit, parameter->minimum, parameter->maximum);
    }
  }
  cli_print("Select:    MAP PROCESSING BOX\r\n"
            "           MAP PROCESSING OBJECT 1   (raw valid depth)\r\n"
            "           MAP PROCESSING OBJECT 2   (adaptive candidates)\r\n"
            "           MAP PROCESSING OBJECT 3   (nearest component)\r\n"
            "           MAP PROCESSING OBJECT 4   (crop + normalize + resize)\r\n"
            "           MAP PROCESSING OBJECT 5   (+ 600 mm limit + wider crop/model margins)\r\n"
            "           MAP PROCESSING OBJECT 6   (+ aggressive >0 binary + 3x3 stripe repair)\r\n"
            "           MAP PROCESSING OBJECT 7 210 (near-depth binary; higher removes more arm)\r\n"
            "           MAP PROCESSING NPU        (exact model input; fixed threshold 210)\r\n"
            "Configure: MAP PROCESSING BOX radius 2\r\n"
            "           MAP PROCESSING BOX passes 2\r\n"
            "           MAP PROCESSING MEDIAN threshold_mm 100\r\n"
            "           MAP PROCESSING GAUSSIAN passes 2\r\n"
            "           MAP PROCESSING SHARPEN amount_percent 125\r\n"
            "           MAP PROCESSING OBJECT 7 threshold 210 (equivalent long form)\r\n"
            "Median threshold_mm=0 applies the median to every pixel.\r\n"
            "OBJECT 1..7 are cumulative views; NPU uses the promoted fixed threshold 210.\r\n"
            "Legacy MAP PROCESSING OBJECT is an alias for MAP PROCESSING NPU.\r\n");
}

static const TOF_ImageFilterDescriptor_t *cli_find_map_filter(
    int argc, char *const argv[], size_t *filter_argument_count)
{
  size_t index;
  char two_token_command[32];

  if ((argc < 3) || (argv == NULL) || (filter_argument_count == NULL))
  {
    return NULL;
  }

  if (argc >= 4)
  {
    int length = snprintf(two_token_command, sizeof(two_token_command),
                          "%s %s", argv[2], argv[3]);
    if ((length > 0) && ((size_t)length < sizeof(two_token_command)))
    {
      for (index = 0U; index < TOF_ImageProcessing_GetFilterCount(); ++index)
      {
        const TOF_ImageFilterDescriptor_t *descriptor =
            TOF_ImageProcessing_GetDescriptorByIndex(index);
        if ((descriptor != NULL) &&
            (cli_token_equals(two_token_command, descriptor->command) != 0U))
        {
          *filter_argument_count = 2U;
          return descriptor;
        }
      }
    }
  }

  for (index = 0U; index < TOF_ImageProcessing_GetFilterCount(); ++index)
  {
    const TOF_ImageFilterDescriptor_t *descriptor =
        TOF_ImageProcessing_GetDescriptorByIndex(index);
    if ((descriptor != NULL) &&
        (cli_token_equals(argv[2], descriptor->command) != 0U))
    {
      *filter_argument_count = 1U;
      return descriptor;
    }
  }

  if (cli_token_equals(argv[2], "OBJECT") != 0U)
  {
    *filter_argument_count = 1U;
    return TOF_ImageProcessing_GetDescriptor(TOF_IMAGE_FILTER_NPU);
  }
  return NULL;
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

#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
static const char *cli_cloud_state_name(CloudRelay_State_t state)
{
  switch (state)
  {
    case CLOUD_RELAY_STATE_DISABLED: return "disabled";
    case CLOUD_RELAY_STATE_WAIT_WIFI: return "waiting for Wi-Fi";
    case CLOUD_RELAY_STATE_UNPAIRED: return "unpaired";
    case CLOUD_RELAY_STATE_CONNECTING: return "connecting";
    case CLOUD_RELAY_STATE_POLLING: return "polling";
    case CLOUD_RELAY_STATE_BACKOFF: return "backoff";
    case CLOUD_RELAY_STATE_ERROR: return "error";
    default: return "unknown";
  }
}
#endif
#endif

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)
static void cli_session_clear_credentials(CliSession_t *session)
{
  if (session == NULL)
  {
    return;
  }
  (void)memset(session->pending_ssid, 0, sizeof(session->pending_ssid));
  (void)memset(session->pending_password, 0,
               sizeof(session->pending_password));
  session->pending_password_length = 0U;
  session->secret_mode = CLI_SECRET_NONE;
}

#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
static uint32_t cli_memory_is_zero(const void *memory, size_t length)
{
  const uint8_t *bytes = (const uint8_t *)memory;

  for (size_t index = 0U; index < length; ++index)
  {
    if (bytes[index] != 0U)
    {
      return 0U;
    }
  }
  return 1U;
}

static void cli_m2_run_diagnostic(void)
{
  static const char usb_ssid[] = "m2-usb";
  static const char cloud_ssid[] = "m2-cloud";
  static const char usb_kept_ssid[] = "m2-usb-kept";
  AppRoute_t saved_cloud_route = cli_cloud_session.route;
  uint32_t saved_cloud_ready = cli_cloud_session.session_ready;
  uint32_t saved_cloud_console = cli_cloud_session.console_mode;

  (void)memset(&cli_m2_diagnostic, 0, sizeof(cli_m2_diagnostic));
  cli_m2_diagnostic.available = 1U;
  cli_session_clear_credentials(&cli_usb_session);
  cli_session_clear_credentials(&cli_cloud_session);

  (void)memcpy(cli_usb_session.pending_ssid, usb_ssid, sizeof(usb_ssid));
  (void)memcpy(cli_usb_session.pending_password, "usb-secret", 11U);
  cli_usb_session.pending_password_length = 10U;
  cli_usb_session.secret_mode = CLI_SECRET_WIFI_PASSWORD;
  (void)memcpy(cli_cloud_session.pending_ssid, cloud_ssid,
               sizeof(cloud_ssid));
  (void)memcpy(cli_cloud_session.pending_password, "cloud-secret", 13U);
  cli_cloud_session.pending_password_length = 12U;
  cli_cloud_session.secret_mode = CLI_SECRET_WIFI_PASSWORD;

  cli_m2_diagnostic.credential_isolation =
      ((strcmp((const char *)cli_usb_session.pending_ssid, usb_ssid) == 0) &&
       (strcmp((const char *)cli_cloud_session.pending_ssid,
               cloud_ssid) == 0) &&
       (strcmp((const char *)cli_usb_session.pending_ssid,
               (const char *)cli_cloud_session.pending_ssid) != 0)) ? 1U : 0U;

  /* This is the same full-capacity scrub used by Ctrl-C. */
  cli_session_clear_credentials(&cli_usb_session);
  cli_m2_diagnostic.cancel_is_scoped =
      ((cli_memory_is_zero(cli_usb_session.pending_ssid,
                           sizeof(cli_usb_session.pending_ssid)) != 0U) &&
       (cli_memory_is_zero(cli_usb_session.pending_password,
                           sizeof(cli_usb_session.pending_password)) != 0U) &&
       (strcmp((const char *)cli_cloud_session.pending_ssid,
               cloud_ssid) == 0) &&
       (strcmp(cli_cloud_session.pending_password,
               "cloud-secret") == 0)) ? 1U : 0U;

  (void)memcpy(cli_usb_session.pending_ssid, usb_kept_ssid,
               sizeof(usb_kept_ssid));
  cli_session_reset(&cli_cloud_session, 0U);
  cli_m2_diagnostic.reset_changes_generation =
      ((cli_cloud_session.route.transport == saved_cloud_route.transport) &&
       (cli_cloud_session.route.session_generation ==
        cli_next_generation(saved_cloud_route.session_generation))) ? 1U : 0U;
  cli_m2_diagnostic.saved_route_becomes_stale =
      (cli_route_is_current(&cli_cloud_session.route,
                            &saved_cloud_route) == 0U) ? 1U : 0U;
  cli_m2_diagnostic.reset_is_scoped =
      ((cli_memory_is_zero(cli_cloud_session.pending_ssid,
                           sizeof(cli_cloud_session.pending_ssid)) != 0U) &&
       (cli_memory_is_zero(cli_cloud_session.pending_password,
                           sizeof(cli_cloud_session.pending_password)) != 0U) &&
       (strcmp((const char *)cli_usb_session.pending_ssid,
               usb_kept_ssid) == 0)) ? 1U : 0U;

  cli_session_clear_credentials(&cli_usb_session);
  cli_session_clear_credentials(&cli_cloud_session);
  cli_cloud_session.route = saved_cloud_route;
  cli_cloud_session.session_ready = saved_cloud_ready;
  cli_cloud_session.console_mode = saved_cloud_console;
}
#endif

static void cli_wifi_status(void)
{
  WifiBle_WifiStatus_t status;
  WifiBle_RuntimeStatus_t runtime;

  WIFI_BLE_App_GetWifiStatus(&status);
  WIFI_BLE_App_GetRuntimeStatus(&runtime);
  cli_print("Wi-Fi station: %s%s\r\n",
            W6X_WiFi_StateToStr(status.station_state),
            (status.operation_active != 0U) ? " (operation in progress)" : "");
  cli_print("Wi-Fi shadow: %s, query %lu/%lu failed, last tick %lu/status %ld\r\n",
            (runtime.wifi_state_confirmed != 0U) ? "event/query confirmed" : "UNKNOWN",
            (unsigned long)runtime.manager_health.wifi_state_queries,
            (unsigned long)runtime.manager_health.wifi_query_failures,
            (unsigned long)runtime.wifi_last_probe_tick,
            (long)runtime.wifi_last_probe_status);
  if (status.connected != 0U)
  {
    cli_print("SSID: %s, channel: %" PRIu32 ", RSSI: %" PRIi32 " dBm\r\n"
              "AP: %02X:%02X:%02X:%02X:%02X:%02X\r\n",
              status.ssid, status.channel, status.rssi,
              status.ap_mac[0], status.ap_mac[1], status.ap_mac[2],
              status.ap_mac[3], status.ap_mac[4], status.ap_mac[5]);
  }
  if (status.ip_valid != 0U)
  {
    cli_print("IPv4: %u.%u.%u.%u\r\n"
              "Gateway: %u.%u.%u.%u, netmask: %u.%u.%u.%u\r\n",
              status.ip_address[0], status.ip_address[1],
              status.ip_address[2], status.ip_address[3],
              status.gateway_address[0], status.gateway_address[1],
              status.gateway_address[2], status.gateway_address[3],
              status.netmask_address[0], status.netmask_address[1],
              status.netmask_address[2], status.netmask_address[3]);
  }
  else if (status.connected != 0U)
  {
    cli_print("IPv4: not acquired yet.\r\n");
  }
}

static void cli_wifi_scan(void)
{
  WifiBle_WifiRequest_t request;
  AppRequestId_t request_id = 0U;
  UINT status;

  (void)memset(&request, 0, sizeof(request));
  request.operation = WIFI_BLE_WIFI_OPERATION_SCAN;
  request.route = cli_active_session->route;
  status = WIFI_BLE_App_WifiSubmit(&request, &request_id);
  if (status != TX_SUCCESS)
  {
    cli_print("Wi-Fi scan request rejected (ThreadX %u).\r\n",
              (unsigned int)status);
    return;
  }
  cli_print("Wi-Fi scan request accepted: id=%" PRIu32 ".\r\n",
            (uint32_t)request_id);
  cli_wifi_note_submission(request_id);
}

static void cli_wifi_connect_password(CliSession_t *session)
{
  WifiBle_WifiRequest_t request;
  AppRequestId_t request_id = 0U;
  const char *password;
  size_t password_length;
  UINT result;

  if ((session == NULL) ||
      (session->secret_mode != CLI_SECRET_WIFI_PASSWORD))
  {
    cli_print("Wi-Fi credential state is invalid.\r\n");
    return;
  }
  password = session->pending_password;
  password_length = strlen(password);
  if (password_length > W6X_WIFI_MAX_PASSWORD_SIZE)
  {
    cli_print("Password is too long.\r\n");
    return;
  }

  (void)memset(&request, 0, sizeof(request));
  request.operation = WIFI_BLE_WIFI_OPERATION_CONNECT;
  request.route = session->route;
  (void)memcpy(request.ssid, session->pending_ssid,
               sizeof(request.ssid));
  (void)memcpy(request.password, password, password_length + 1U);
  result = WIFI_BLE_App_WifiSubmit(&request, &request_id);
  /* The queue owns its complete copy after a successful submit. Ensure the
   * compiler cannot elide scrubbing of the sensitive stack-owned request. */
  for (size_t i = 0U; i < sizeof(request); ++i)
  {
    ((volatile uint8_t *)&request)[i] = 0U;
  }

  if (result != TX_SUCCESS)
  {
    if (session->route.transport == APP_TRANSPORT_USB)
    {
      cli_print("Wi-Fi connect request rejected (ThreadX %u).\r\n",
                (unsigned int)result);
    }
    else
    {
      cli_print("Wi-Fi connect request rejected (ThreadX %u).\r\nn6> ",
                (unsigned int)result);
      cli_prompt_already_sent = 1U;
    }
    return;
  }
  if (session->route.transport == APP_TRANSPORT_USB)
  {
    cli_print("Wi-Fi connect request accepted: id=%" PRIu32 ".\r\n",
              (uint32_t)request_id);
  }
  else
  {
    cli_print("Wi-Fi connect request accepted: id=%" PRIu32 ".\r\nn6> ",
              (uint32_t)request_id);
    cli_prompt_already_sent = 1U;
  }
  cli_wifi_note_submission(request_id);
}
#endif

#if (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static void __attribute__((optimize("Os"))) cli_ble_status(void)
{
  WifiBle_RuntimeStatus_t runtime;
  WIFI_BLE_App_GetRuntimeStatus(&runtime);

  cli_print("BLE GATT: %s, link: %s, advertising: %s, MTU: %lu\r\n",
            (runtime.ble_gatt_ready != 0U) ? "ready" : "not ready",
            (runtime.ble_connected != 0U) ? "connected" : "disconnected",
            (runtime.ble_advertising != 0U) ? "on" : "off",
            (unsigned long)runtime.ble_mtu);
  cli_print("BLE advertising desired: %s; manager init %lu/%lu fail, advertising %lu/%lu fail, disconnect fail %lu, driver errors %lu (last %ld)\r\n",
            (runtime.ble_advertising_desired != 0U) ? "on" : "off",
            (unsigned long)runtime.manager_health.init_attempts,
            (unsigned long)runtime.manager_health.init_failures,
            (unsigned long)runtime.manager_health.advertising_attempts,
            (unsigned long)runtime.manager_health.advertising_failures,
            (unsigned long)runtime.manager_health.disconnect_failures,
            (unsigned long)runtime.manager_health.driver_error_callbacks,
            (long)runtime.manager_health.last_driver_error);
  cli_print("BLE ADV evidence: %s (not RF proof), retry %lu/3; mode/link confirmed %lu/%lu, recovery pending %lu\r\n",
            (runtime.ble_advertising_evidence == WIFI_BLE_ADV_COMMAND_ACK) ?
                "command ACK" :
            (runtime.ble_advertising_evidence == WIFI_BLE_ADV_CONNECTION_EVENT) ?
                "connection event" : "UNKNOWN",
            (unsigned long)runtime.ble_advertising_retry_count,
            (unsigned long)runtime.ble_mode_confirmed,
            (unsigned long)runtime.ble_link_confirmed,
            (unsigned long)runtime.ble_recovery_pending);
  cli_print("BLE probes: mode %lu, link %lu, failed %lu, corrected %lu, last tick %lu/status %ld; BLE repair %lu/%lu fail; ADV exhausted %lu\r\n",
            (unsigned long)runtime.manager_health.ble_mode_queries,
            (unsigned long)runtime.manager_health.ble_link_queries,
            (unsigned long)runtime.manager_health.ble_query_failures,
            (unsigned long)runtime.manager_health.ble_link_corrections,
            (unsigned long)runtime.ble_last_probe_tick,
            (long)runtime.ble_last_probe_status,
            (unsigned long)runtime.manager_health.ble_recovery_attempts,
            (unsigned long)runtime.manager_health.ble_recovery_failures,
            (unsigned long)runtime.manager_health.advertising_retries_exhausted);
  cli_print("BLE init stage: %lu, last W6X status: %ld\r\n",
            (unsigned long)runtime.ble_init_stage,
            (long)runtime.ble_last_status);
  if (runtime.ble_device_name[0] != '\0')
  {
    cli_print("Name: %s\r\n"
              "Address: %02X:%02X:%02X:%02X:%02X:%02X\r\n",
              runtime.ble_device_name,
              runtime.ble_address[0], runtime.ble_address[1],
              runtime.ble_address[2], runtime.ble_address[3],
              runtime.ble_address[4], runtime.ble_address[5]);
  }
  cli_print("CLI TX notifications: %s; DEBUG TX notifications: %s; ToF image notifications: %s\r\n"
            "Stream transport: %s, generation %lu, ATT payload %lu bytes\r\n"
            "Radio SRAM4 pool: %lu bytes available, %lu fragments\r\n",
            (runtime.ble_cli_tx_subscribed != 0U) ? "subscribed" : "off",
            (runtime.ble_debug_tx_subscribed != 0U) ? "subscribed" : "off",
            (runtime.ble_tof_image_subscribed != 0U) ? "subscribed" : "off",
            (runtime.ble_transport_ready != 0U) ? "ready" : "not ready",
            (unsigned long)runtime.ble_session_generation,
            (unsigned long)runtime.ble_att_payload_limit,
            (unsigned long)runtime.ble_radio_pool_available,
            (unsigned long)runtime.ble_radio_pool_fragments);
  cli_print("CLI RX: queued %lu/%lu high-water, accepted %lu events/%lu bytes, dropped %lu/%lu\r\n"
            "CLI TX: queued %lu/%lu high-water, accepted %lu messages/%lu bytes, sent %lu, dropped %lu/%lu, retries %lu, errors %lu\r\n",
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].rx_queued,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].rx_high_water,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].rx_events,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].rx_bytes,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].rx_dropped_events,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].rx_dropped_bytes,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].tx_queued,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].tx_high_water,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].tx_messages,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].tx_bytes,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].tx_sent_bytes,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].tx_dropped_messages,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].tx_dropped_bytes,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].tx_retries,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].tx_errors);
  cli_print("CLI TX contention: busy %lu, timeout %lu, streak %lu/%lu, duration_ticks %lu/%lu, recoveries %lu\r\n",
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].contention.busy_count,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].contention.timeout_count,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].contention.current_streak,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].contention.peak_streak,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].contention.current_duration_ticks,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].contention.peak_duration_ticks,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].contention.recoveries);
  cli_print("DEBUG RX: disabled by policy, dropped %lu events/%lu bytes\r\n"
            "DEBUG TX: queued %lu/%lu high-water, accepted %lu messages/%lu bytes, sent %lu, dropped %lu/%lu, retries %lu, errors %lu\r\n",
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].rx_dropped_events,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].rx_dropped_bytes,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].tx_queued,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].tx_high_water,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].tx_messages,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].tx_bytes,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].tx_sent_bytes,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].tx_dropped_messages,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].tx_dropped_bytes,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].tx_retries,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].tx_errors);
  cli_print("DEBUG TX contention: busy %lu, timeout %lu, streak %lu/%lu, duration_ticks %lu/%lu, recoveries %lu\r\n",
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].contention.busy_count,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].contention.timeout_count,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].contention.current_streak,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].contention.peak_streak,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].contention.current_duration_ticks,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].contention.peak_duration_ticks,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].contention.recoveries);
  cli_print("Stale generation drops: CLI %lu, DEBUG %lu; total GATT writes %lu, discarded bytes %lu\r\n",
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_CLI].stale_drops,
            (unsigned long)runtime.ble_stream[WIFI_BLE_STREAM_DEBUG].stale_drops,
            (unsigned long)runtime.ble_rx_write_events,
            (unsigned long)runtime.ble_rx_discarded_bytes);
  cli_print("ToF image: submitted %lu, complete %lu, busy drops %lu, aborted %lu; fragments %lu, payload bytes %lu, retries %lu, errors %lu; last %lu/%lu\r\n",
            (unsigned long)runtime.ble_tof_image.frames_submitted,
            (unsigned long)runtime.ble_tof_image.frames_sent,
            (unsigned long)runtime.ble_tof_image.frames_dropped_busy,
            (unsigned long)runtime.ble_tof_image.frames_aborted,
            (unsigned long)runtime.ble_tof_image.fragments_sent,
            (unsigned long)runtime.ble_tof_image.bytes_sent,
            (unsigned long)runtime.ble_tof_image.retries,
            (unsigned long)runtime.ble_tof_image.errors,
            (unsigned long)runtime.ble_tof_image.last_submitted_frame,
            (unsigned long)runtime.ble_tof_image.last_sent_frame);
  cli_print("ToF TX contention: busy %lu, timeout %lu, streak %lu/%lu, duration_ticks %lu/%lu, recoveries %lu\r\n",
            (unsigned long)runtime.ble_tof_image.contention.busy_count,
            (unsigned long)runtime.ble_tof_image.contention.timeout_count,
            (unsigned long)runtime.ble_tof_image.contention.current_streak,
            (unsigned long)runtime.ble_tof_image.contention.peak_streak,
            (unsigned long)runtime.ble_tof_image.contention.current_duration_ticks,
            (unsigned long)runtime.ble_tof_image.contention.peak_duration_ticks,
            (unsigned long)runtime.ble_tof_image.contention.recoveries);
}
#endif
