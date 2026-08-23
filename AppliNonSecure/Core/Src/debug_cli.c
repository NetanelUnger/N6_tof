#include "debug_cli.h"

#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "app_console.h"
#include "app_features.h"
#include "app_logging.h"
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
#include "usb_cdc_transport.h"
#include "wifi_ble_app.h"
#if (APP_ST67W6X_ENABLED == 1U)
#include "w6x_api.h"
#endif

#define CLI_RX_CHUNK_SIZE       (64U)
#define CLI_LINE_SIZE           (192U)
#define CLI_PRINT_SIZE          (768U)
#define CLI_MAX_ARGUMENTS       (8)
#define CLI_HISTORY_DEPTH       (16U)
#define CLI_WIFI_SCAN_MAX_APS   (15U)

static char cli_line[CLI_LINE_SIZE];
static size_t cli_line_length;
static char cli_print_buffer[CLI_PRINT_SIZE];
static char cli_menu_input[CLI_LINE_SIZE];
static char cli_menu_reply[CLI_PRINT_SIZE];
static Menu_t cli_menu;
static uint32_t cli_console_mode;
static uint32_t cli_secret_mode;
static uint32_t cli_previous_was_cr;
static uint32_t cli_first_input_logged;
static uint32_t cli_cdc_session_ready;
static char cli_history[CLI_HISTORY_DEPTH][CLI_LINE_SIZE];
static char cli_history_draft[CLI_LINE_SIZE];
static size_t cli_history_count;
static size_t cli_history_index;
static uint32_t cli_escape_state;
#if (APP_ST67W6X_ENABLED == 1U)
static uint8_t cli_pending_ssid[W6X_WIFI_MAX_SSID_SIZE + 1U];
static volatile uint32_t cli_wifi_scan_active;
#endif

static void cli_process_byte(uint8_t byte);
static void cli_enter_console(void);
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
static void cli_show_map_processing(void);
static const TOF_ImageFilterDescriptor_t *cli_find_map_filter(
    const char *command);
static const char *cli_tof_state_name(TOF_App_State_t state);
static const char *cli_radio_state_name(WifiBle_State_t state);
static const char *cli_log_level_name(uint32_t level);
#if (APP_ST67W6X_ENABLED == 1U)
static void cli_command_radio(Menu_t *menu, const char *command);
static void cli_command_wifi(Menu_t *menu, const char *command);
static void cli_command_ble(Menu_t *menu, const char *command);
static uint32_t cli_radio_is_ready(void);
static void cli_wifi_status(void);
static void cli_wifi_scan(void);
static void cli_wifi_connect_password(const char *password);
static void cli_wifi_scan_callback(int32_t status, W6X_WiFi_Scan_Result_t *results);
static void cli_ble_status(void);
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
#if (APP_ST67W6X_ENABLED == 1U)
  MENU_OBJECT("radio", cli_command_radio),
  MENU_OBJECT("wifi", cli_command_wifi),
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
  "Start UART Firmware Update",
  "update",
#if (APP_ST67W6X_ENABLED == 1U)
  "radio info",
  "wifi status",
  "wifi scan",
  "wifi connect ",
  "wifi disconnect",
  "wifi disconnect forget",
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

  menu_status = Menu_Init(&cli_menu,
                          cli_menu_objects,
                          MENU_OBJECT_COUNT(cli_menu_objects),
                          cli_menu_input,
                          sizeof(cli_menu_input),
                          cli_menu_reply,
                          sizeof(cli_menu_reply),
                          cli_menu_send,
                          NULL,
                          cli_command_unknown);
  if (menu_status != MENU_STATUS_OK)
  {
    Debug_UART_Log("CLI", "menu initialization failed: %d",
                   (int)menu_status);
    for (;;)
    {
      tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND);
    }
  }

  for (;;)
  {
    ULONG actual_length = 0U;

    Firmware_Update_Poll(HAL_GetTick());

    if (App_Console_IsReady() == 0U)
    {
      Firmware_Update_Cancel();
      cli_console_mode = 0U;
      cli_secret_mode = 0U;
      cli_line_length = 0U;
      cli_previous_was_cr = 0U;
      cli_escape_state = 0U;
      cli_history_index = cli_history_count;
      cli_first_input_logged = 0U;
      cli_cdc_session_ready = 0U;
      Menu_Reset(&cli_menu);
      TOF_App_SetMapEnabled(0U);
      TOF_App_SetDatasetStreamEnabled(0U);
      tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 10U);
      continue;
    }

    if (cli_cdc_session_ready == 0U)
    {
      cli_cdc_session_ready = 1U;
      cli_enter_console();
    }

    UINT status = App_Console_Read(rx_buffer, sizeof(rx_buffer), &actual_length);
    if (status != TX_SUCCESS)
    {
      tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 20U);
      continue;
    }

    if (Firmware_Update_IsActive() != 0U)
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
      if (Firmware_Update_IsActive() != 0U)
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
  }
}

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
#if (APP_ST67W6X_ENABLED == 1U)
      if (cli_secret_mode == 0U)
#endif
      cli_history_move(-1);
    }
    else if (byte == 'B')
    {
#if (APP_ST67W6X_ENABLED == 1U)
      if (cli_secret_mode == 0U)
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
#if (APP_ST67W6X_ENABLED == 1U)
    if (cli_secret_mode == 0U)
#endif
    {
      cli_complete_input();
    }
    return;
  }

  if ((byte == '\r') || (byte == '\n'))
  {
    cli_print("\r\n");

#if (APP_ST67W6X_ENABLED == 1U)
    if (cli_secret_mode != 0U)
    {
      cli_line[cli_line_length] = '\0';
      cli_wifi_connect_password(cli_line);
      (void)memset(cli_line, 0, sizeof(cli_line));
      (void)memset(cli_pending_ssid, 0, sizeof(cli_pending_ssid));
      cli_line_length = 0U;
      cli_secret_mode = 0U;
      cli_prompt();
      return;
    }
#endif

    cli_history_record(Menu_GetPendingInput(&cli_menu));
    cli_history_index = cli_history_count;
    cli_history_draft[0] = '\0';
    menu_status = Menu_Process(&cli_menu, &byte, 1U);
    if (menu_status == MENU_STATUS_INPUT_TOO_LONG)
    {
      (void)Menu_Reply(&cli_menu, "Command is too long.");
      Debug_UART_Log("CLI", "discarded an overlength command");
    }

    if ((cli_console_mode != 0U) && (cli_secret_mode == 0U) &&
        (Firmware_Update_IsActive() == 0U))
    {
      cli_prompt();
    }
    return;
  }

  if ((byte == 0x08U) || (byte == 0x7FU))
  {
#if (APP_ST67W6X_ENABLED == 1U)
    if (cli_secret_mode != 0U)
    {
      if (cli_line_length != 0U)
      {
        --cli_line_length;
        cli_line[cli_line_length] = '\0';
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
    (void)memset(cli_line, 0, sizeof(cli_line));
    cli_line_length = 0U;
    cli_secret_mode = 0U;
    cli_escape_state = 0U;
    cli_history_index = cli_history_count;
    cli_history_draft[0] = '\0';
    Menu_Reset(&cli_menu);
#if (APP_ST67W6X_ENABLED == 1U)
    (void)memset(cli_pending_ssid, 0, sizeof(cli_pending_ssid));
#endif
    cli_print("^C\r\n");
    cli_prompt();
    return;
  }

  if ((byte >= 0x20U) && (byte <= 0x7EU))
  {
#if (APP_ST67W6X_ENABLED == 1U)
    if (cli_secret_mode != 0U)
    {
      if (cli_line_length < (sizeof(cli_line) - 1U))
      {
        cli_line[cli_line_length++] = (char)byte;
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

    (void)App_Console_Write(&byte, 1U);
  }
}

static void cli_enter_console(void)
{
  cli_console_mode = 1U;
  cli_line_length = 0U;
  cli_secret_mode = 0U;
  cli_escape_state = 0U;
  cli_history_index = cli_history_count;
  cli_history_draft[0] = '\0';
  Menu_Reset(&cli_menu);
  TOF_App_SetMapEnabled(0U);
  Debug_UART_Log("CLI", "USB CDC menu entered; depth map disabled");
  cli_print("\033[?25h\033[2J\033[H"
            "+------------------------------------------------+\r\n"
            "|            NATI LAB N6 CONTROL MENU            |\r\n"
            "+------------------------------------------------+\r\n"
            "  Application firmware version: "
            NATI_LAB_FIRMWARE_VERSION_TEXT "\r\n"
            "  USB CDC carries menu/map/update traffic only.\r\n"
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
      (cli_token_equals(argv[1], "on") != 0U) &&
      ((cli_token_equals(argv[2], "screen") != 0U) ||
       (cli_token_equals(argv[2], "display") != 0U)))
  {
    Display_App_SetMapEnabled(1U);
    (void)Menu_Reply(menu,
                     "Screen depth map enabled; processing will publish numbered frames to the display task.");
  }
  else if ((argc == 3) &&
           (cli_token_equals(argv[1], "off") != 0U) &&
           ((cli_token_equals(argv[2], "screen") != 0U) ||
            (cli_token_equals(argv[2], "display") != 0U)))
  {
    Display_App_SetMapEnabled(0U);
    (void)Menu_Reply(menu,
                     "Screen depth map disabled; the display task will clear the centered map area.");
  }
  else
#endif
  if ((argc == 2) && (cli_token_equals(argv[1], "on") != 0U))
  {
    (void)Menu_Reply(menu,
                     "Depth map enabled. Press Enter to return to the console.");
    TOF_App_SetMapEnabled(1U);
    cli_console_mode = 0U;
  }
  else if ((argc == 2) && (cli_token_equals(argv[1], "off") != 0U))
  {
    TOF_App_SetMapEnabled(0U);
    (void)Menu_Reply(menu,
                     "Depth map disabled; ranging remains active.");
  }
  else if ((argc >= 2) &&
           (cli_token_equals(argv[1], "processing") != 0U))
  {
    const TOF_ImageFilterDescriptor_t *descriptor;

    if (argc == 2)
    {
      cli_show_map_processing();
      return;
    }

    descriptor = cli_find_map_filter(argv[2]);
    if (descriptor == NULL)
    {
      (void)Menu_Reply(menu,
                       "Usage: MAP PROCESSING <filter> [parameter value]");
      return;
    }

    if (argc == 3)
    {
      (void)TOF_App_SelectMapFilter(descriptor->filter);
      cli_show_map_processing();
      return;
    }

    if (argc == 5)
    {
      size_t parameter_index;
      uint32_t value;

      for (parameter_index = 0U;
           parameter_index < descriptor->parameter_count;
           ++parameter_index)
      {
        if (cli_token_equals(argv[3],
                             descriptor->parameters[parameter_index].name) != 0U)
        {
          break;
        }
      }

      if ((parameter_index >= descriptor->parameter_count) ||
          (cli_parse_u32(argv[4], &value) == 0))
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
                     "Usage: MAP PROCESSING <filter> [parameter value]");
  }
  else
  {
    (void)Menu_Reply(menu,
                     "Usage: MAP ON|OFF [SCREEN] or MAP PROCESSING");
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
                     "Dataset stream enabled: N6DF v2, 54x42 uint16 millimetres + frame-matched NPU scores, CRC32 protected.");
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
    (void)Menu_Reply(menu, "Usage: debug off|error|warn|info|debug");
  }
  else
  {
    App_Logging_SetVerbosity(level);
    cli_print("ST67 log level set to %s.\r\n",
              cli_log_level_name(level));
  }
}

#if (APP_ST67W6X_ENABLED == 1U)
static void cli_command_radio(Menu_t *menu, const char *command)
{
  char copy[CLI_LINE_SIZE];
  char *argv[CLI_MAX_ARGUMENTS];
  int argc = cli_get_arguments(command, copy, sizeof(copy), argv,
                               CLI_MAX_ARGUMENTS);

  if ((argc == 2) && (strcmp(argv[1], "info") == 0))
  {
    W6X_ModuleInfo_t *info;

    if (cli_radio_is_ready() == 0U) return;
    info = W6X_GetModuleInfo();
    if (info != NULL)
    {
      cli_print("Module: %s (%s)\r\n"
                "NCP MAC: %02X:%02X:%02X:%02X:%02X:%02X\r\n"
                "Build: %.31s\r\n",
                info->ModuleID.ModuleName,
                W6X_ModelToStr(info->ModuleID.ModuleID),
                info->Mac_Address[0], info->Mac_Address[1],
                info->Mac_Address[2], info->Mac_Address[3],
                info->Mac_Address[4], info->Mac_Address[5],
                info->Build_Date);
    }
  }
  else
  {
    (void)Menu_Reply(menu, "Usage: radio info");
  }
}

static void cli_command_wifi(Menu_t *menu, const char *command)
{
  char copy[CLI_LINE_SIZE];
  char *argv[CLI_MAX_ARGUMENTS];
  int argc = cli_get_arguments(command, copy, sizeof(copy), argv,
                               CLI_MAX_ARGUMENTS);

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
    (void)Menu_Reply(menu, "Usage: wifi connect \"SSID\"");
  }
  else if ((argc == 3) && (strcmp(argv[1], "connect") == 0))
  {
    size_t ssid_length;

    if (cli_radio_is_ready() == 0U) return;
    ssid_length = strlen(argv[2]);
    if ((ssid_length == 0U) || (ssid_length > W6X_WIFI_MAX_SSID_SIZE))
    {
      (void)Menu_Reply(menu, "Invalid SSID length.");
    }
    else
    {
      (void)memset(cli_pending_ssid, 0, sizeof(cli_pending_ssid));
      (void)memcpy(cli_pending_ssid, argv[2], ssid_length);
      cli_secret_mode = 1U;
      cli_line_length = 0U;
      (void)Menu_Reply(menu, "Password (input hidden):");
    }
  }
  else if ((argc >= 2) && (strcmp(argv[1], "disconnect") == 0))
  {
    uint32_t forget;
    W6X_Status_t status;

    if (cli_radio_is_ready() == 0U) return;
    forget = ((argc == 3) && (strcmp(argv[2], "forget") == 0)) ? 1U : 0U;
    status = W6X_WiFi_Disconnect(forget);
    cli_print("Wi-Fi disconnect: %s%s\r\n", W6X_StatusToStr(status),
              (forget != 0U) ? " (stored credentials removed)" : "");
  }
  else
  {
    (void)Menu_Reply(menu,
                     "Usage: wifi status|scan|connect \"SSID\"|disconnect [forget]");
  }
}

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
    W6X_Status_t status;

    if (cli_radio_is_ready() == 0U) return;
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
      (void)Menu_Reply(menu, "Usage: ble adv on|off");
      return;
    }
    cli_print("BLE advertising: %s\r\n", W6X_StatusToStr(status));
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
      W6X_Status_t status =
          W6X_Ble_Disconnect(runtime.ble_connection_handle);
      cli_print("BLE disconnect: %s\r\n", W6X_StatusToStr(status));
    }
  }
  else
  {
    (void)Menu_Reply(menu, "Usage: ble status|adv on|adv off|disconnect");
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
  Menu_Reset(menu);
  TOF_App_SetDatasetStreamEnabled(0U);
  if (Firmware_Update_Start() != 0)
  {
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
  (void)context;

  if ((text == NULL) || (length == 0U))
  {
    return 0;
  }

  return (int32_t)App_Console_Write(text, (ULONG)length);
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
            "  (MAP ON shows the map; Enter returns to this menu.)\r\n"
            "  version                        running application version\r\n"
            "  status                         system summary\r\n"
            "  usb status                     USB queues, pool, flow/error counters\r\n"
            "  MAP ON                         show map until Enter is pressed\r\n"
#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
            "  MAP ON SCREEN|DISPLAY          show map + NPU result on the SPI display\r\n"
            "  MAP OFF SCREEN|DISPLAY         stop and clear the SPI display map\r\n"
#endif
            "  MAP PROCESSING                 select/configure depth filtering\r\n"
            "  tof status|pause|resume        inspect/control ranging\r\n"
            "  DATASET STREAM ON|OFF|STATUS   CRC-protected 16-bit ToF training frames\r\n"
            "  RPS ON|OFF|STATUS              Neural-ART inference and raw int8 scores\r\n"
            "  debug off|error|warn|info|debug ST67 runtime log level\r\n"
            "  Start UART Firmware Update      receive signed .n6fw via XMODEM-CRC\r\n"
            "  update                          short alias for firmware update\r\n"
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
            "ToF: %s, map %s, dataset %s, frame %" PRIu32 ", %" PRIu32 ".%" PRIu32 " fps\r\n"
            "ST67: %s, Wi-Fi %s, BLE %s, advertising %s\r\n"
            "Log level: %s\r\n",
            HAL_GetTick(), (usb.active != 0U) ? "active" : "inactive",
            (unsigned long)usb.session,
            (unsigned long)usb.tx_queue_depth,
            (unsigned long)usb.rx_queue_depth,
            cli_tof_state_name(tof.state),
            (tof.map_enabled != 0U) ? "on" : "off",
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
  TOF_ImageProcessingConfig_t processing;
  const TOF_ImageFilterDescriptor_t *filter;
  TOF_App_GetStatus(&status);
  TOF_App_GetMapProcessingConfig(&processing);
  filter = TOF_ImageProcessing_GetDescriptor(processing.selected_filter);
  cli_print("ToF state: %s\r\n"
            "Resolution: %" PRIu32 "x%" PRIu32 "\r\n"
            "Frame: %" PRIu32 ", rate: %" PRIu32 ".%" PRIu32 " fps\r\n"
            "Pipeline: acquired %" PRIu32 ", processed %" PRIu32 ", dropped %" PRIu32 ", queue failures %" PRIu32 "\r\n"
            "Last valid range: %" PRIu32 "..%" PRIu32 " mm\r\n"
            "Map: %s, processing: %s, acquisition: %s\r\n",
            cli_tof_state_name(status.state), status.width, status.height,
            status.frame_counter, status.fps_x10 / 10U, status.fps_x10 % 10U,
            status.acquired_frames, status.processed_frames,
            status.dropped_frames, status.queue_failures,
            status.minimum_mm, status.maximum_mm,
            (status.map_enabled != 0U) ? "on" : "off",
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
}

#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
static void cli_show_display_status(void)
{
  Display_App_Status_t status;

  Display_App_GetStatus(&status);
  cli_print(
      "Display: %s, screen map %s, frame in flight %s\r\n"
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

    cli_print("  [%c] %-7s %-12s - %s\r\n",
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
            "Configure: MAP PROCESSING BOX radius 2\r\n"
            "           MAP PROCESSING BOX passes 2\r\n"
            "           MAP PROCESSING MEDIAN threshold_mm 100\r\n"
            "           MAP PROCESSING GAUSSIAN passes 2\r\n"
            "           MAP PROCESSING SHARPEN amount_percent 125\r\n"
            "Median threshold_mm=0 applies the median to every pixel.\r\n");
}

static const TOF_ImageFilterDescriptor_t *cli_find_map_filter(
    const char *command)
{
  size_t index;

  for (index = 0U; index < TOF_ImageProcessing_GetFilterCount(); ++index)
  {
    const TOF_ImageFilterDescriptor_t *descriptor =
        TOF_ImageProcessing_GetDescriptorByIndex(index);
    if ((descriptor != NULL) &&
        (cli_token_equals(command, descriptor->command) != 0U))
    {
      return descriptor;
    }
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
