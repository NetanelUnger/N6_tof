#include "firmware_update.h"

#include <string.h>

#include "app_console.h"
#include "debug_uart.h"
#include "firmware_update_format.h"
#include "main.h"
#include "secure_nsc.h"
#include "tof_app.h"
#include "xmodem_receiver.h"

#define UPDATE_REBOOT_DELAY_MS       (1000U)

static XMODEM_Receiver_t update_xmodem;
static FW_UpdateManifest_t update_manifest;
static uint32_t update_manifest_bytes;
static uint32_t update_image_bytes;
static uint32_t update_secure_session;
static uint32_t update_active;
static uint32_t update_success;
static uint32_t update_result_reported;
static uint32_t update_reboot_at;

static int32_t update_send_byte(uint8_t byte, void *context);
static int32_t update_consume(const uint8_t *data, size_t length,
                              void *context);
static int32_t update_finish(void *context);
static void update_abort(int32_t reason, void *context);
static void update_fail(const char *message);

static int32_t update_send_byte(uint8_t byte, void *context)
{
  (void)context;
  return (App_Console_Write(&byte, 1U) == TX_SUCCESS) ? 0 : -1;
}

static int32_t update_consume(const uint8_t *data, size_t length,
                              void *context)
{
  const uint8_t *cursor = data;
  size_t remaining = length;
  (void)context;

  if ((data == NULL) || (length == 0U) || (update_active == 0U))
  {
    return -1;
  }

  if (update_manifest_bytes < sizeof(update_manifest))
  {
    size_t needed = sizeof(update_manifest) - update_manifest_bytes;
    size_t chunk = (remaining < needed) ? remaining : needed;
    (void)memcpy((uint8_t *)&update_manifest + update_manifest_bytes,
                 cursor, chunk);
    update_manifest_bytes += (uint32_t)chunk;
    cursor += chunk;
    remaining -= chunk;

    if (update_manifest_bytes == sizeof(update_manifest))
    {
      uint32_t status = SECURE_FirmwareUpdateBegin(&update_manifest,
                                                   &update_secure_session);
      if (status != SECURE_FW_UPDATE_OK)
      {
        Debug_UART_Log("UPDATE", "secure begin rejected package: %lu",
                       (unsigned long)status);
        return -2;
      }
      Debug_UART_Log("UPDATE", "authenticated manifest v%lu, image=%lu bytes",
                     (unsigned long)update_manifest.firmware_version,
                     (unsigned long)update_manifest.image_size);
    }
  }

  if (remaining != 0U)
  {
    uint32_t image_remaining;
    size_t image_chunk;

    if (update_secure_session == 0U)
    {
      return -3;
    }
    image_remaining = update_manifest.image_size - update_image_bytes;
    if (image_remaining == 0U)
    {
      return -5;
    }
    image_chunk = (remaining < image_remaining) ? remaining : image_remaining;
    if ((image_chunk != 0U) &&
        (SECURE_FirmwareUpdateWrite(update_secure_session, cursor,
                                    (uint32_t)image_chunk) !=
         SECURE_FW_UPDATE_OK))
    {
      return -4;
    }
    update_image_bytes += (uint32_t)image_chunk;
    cursor += image_chunk;
    remaining -= image_chunk;

    /* Only the unused tail of the final XMODEM block may follow the signed
     * package, and every padding byte must be the conventional CTRL-Z. */
    while (remaining-- != 0U)
    {
      if (*cursor++ != 0x1AU)
      {
        return -5;
      }
    }
  }
  return 0;
}

static int32_t update_finish(void *context)
{
  uint32_t status;
  (void)context;

  if ((update_secure_session == 0U) ||
      (update_manifest_bytes != sizeof(update_manifest)) ||
      (update_image_bytes != update_manifest.image_size))
  {
    return -1;
  }

  status = SECURE_FirmwareUpdateFinalize(update_secure_session);
  if (status != SECURE_FW_UPDATE_OK)
  {
    Debug_UART_Log("UPDATE", "secure finalize failed: %lu",
                   (unsigned long)status);
    return -2;
  }

  update_secure_session = 0U;
  update_active = 0U;
  update_success = 1U;
  return 0;
}

static void update_abort(int32_t reason, void *context)
{
  (void)context;
  if (update_secure_session != 0U)
  {
    (void)SECURE_FirmwareUpdateAbort(update_secure_session);
  }
  update_secure_session = 0U;
  update_active = 0U;
  TOF_App_SetPaused(0U);
  Debug_UART_Log("UPDATE", "XMODEM transfer aborted: %ld", (long)reason);
  if (update_result_reported == 0U)
  {
    update_result_reported = 1U;
    update_fail("transfer cancelled or rejected");
  }
}

static void update_fail(const char *message)
{
  static const char prefix[] = "\r\nFirmware update failed: ";
  static const char suffix[] = "\r\nn6> ";
  (void)App_Console_Write(prefix, sizeof(prefix) - 1U);
  if (message != NULL)
  {
    (void)App_Console_Write(message, (ULONG)strlen(message));
  }
  (void)App_Console_Write(suffix, sizeof(suffix) - 1U);
}

int32_t Firmware_Update_Start(void)
{
  static const char instructions[] =
      "\r\nSigned firmware update mode.\r\n"
      "Send a .n6fw package now using XMODEM-CRC (128-byte or 1K blocks).\r\n"
      "Press Ctrl-X twice in the sender to cancel. Waiting: ";
  XMODEM_Callbacks_t callbacks = {0};

  if (update_active != 0U)
  {
    return -1;
  }

  (void)memset(&update_manifest, 0, sizeof(update_manifest));
  update_manifest_bytes = 0U;
  update_image_bytes = 0U;
  update_secure_session = 0U;
  update_success = 0U;
  update_result_reported = 0U;
  update_reboot_at = 0U;
  update_active = 1U;
  TOF_App_SetMapEnabled(0U);
  TOF_App_SetPaused(1U);

  if (App_Console_Write(instructions, sizeof(instructions) - 1U) !=
      TX_SUCCESS)
  {
    update_active = 0U;
    TOF_App_SetPaused(0U);
    return -2;
  }

  callbacks.send_byte = update_send_byte;
  callbacks.consume = update_consume;
  callbacks.finish = update_finish;
  callbacks.abort = update_abort;
  if (XMODEM_Start(&update_xmodem, &callbacks, HAL_GetTick()) != 0)
  {
    update_active = 0U;
    TOF_App_SetPaused(0U);
    return -3;
  }
  Debug_UART_Log("UPDATE", "XMODEM-CRC receiver started on USB CDC");
  return 0;
}

void Firmware_Update_Feed(const uint8_t *data, size_t length,
                          uint32_t now_ms)
{
  if (update_active != 0U)
  {
    XMODEM_Process(&update_xmodem, data, length, now_ms);
  }
}

void Firmware_Update_Poll(uint32_t now_ms)
{
  if (update_active != 0U)
  {
    XMODEM_Poll(&update_xmodem, now_ms);
  }

  if ((update_success != 0U) && (update_result_reported == 0U))
  {
    static const char success[] =
        "\r\nAuthenticated update stored in the inactive slot. "
        "Rebooting into trial firmware...\r\n";
    update_result_reported = 1U;
    update_reboot_at = now_ms + UPDATE_REBOOT_DELAY_MS;
    (void)App_Console_Write(success, sizeof(success) - 1U);
    Debug_UART_Log("UPDATE", "candidate committed; reset scheduled");
  }

  if ((update_reboot_at != 0U) &&
      ((int32_t)(now_ms - update_reboot_at) >= 0))
  {
    NVIC_SystemReset();
  }
}

void Firmware_Update_Cancel(void)
{
  if (update_active != 0U)
  {
    XMODEM_Cancel(&update_xmodem, -20);
  }
}

uint32_t Firmware_Update_IsActive(void)
{
  return update_active;
}

void Firmware_Update_ConfirmBoot(void)
{
  uint32_t status = SECURE_FirmwareUpdateConfirmBoot();
  if (status == SECURE_FW_UPDATE_OK)
  {
    Debug_UART_Log("UPDATE", "boot confirmed; rollback window closed");
  }
  else
  {
    Debug_UART_Log("UPDATE", "boot confirmation failed: %lu",
                   (unsigned long)status);
  }
}
