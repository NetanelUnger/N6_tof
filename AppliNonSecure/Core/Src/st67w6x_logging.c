#include "logging.h"
#include "app_logging.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "task.h"

static TX_MUTEX logging_mutex;
static UINT logging_initialized;
static uint32_t logging_level = LOG_DEFAULT_LEVEL;
static void (*logging_output)(const char *message);
static char logging_buffer[MAX_LOG_MESSAGE_LENGTH];

void *vLoggingInit(void (*LogOutput_cb)(const char *message))
{
  logging_output = LogOutput_cb;
  if (logging_initialized == 0U)
  {
    if (tx_mutex_create(&logging_mutex, "ST67W6X log", TX_INHERIT) != TX_SUCCESS)
    {
      return NULL;
    }
    logging_initialized = 1U;
  }
  return &logging_mutex;
}

void vLoggingSetVerbosity(uint32_t level)
{
  if (level <= MAX_LOG_LEVEL)
  {
    logging_level = level;
  }
}

void App_Logging_SetVerbosity(uint32_t level)
{
  vLoggingSetVerbosity(level);
}

uint32_t App_Logging_GetVerbosity(void)
{
  return logging_level;
}

void vLoggingPrintf(uint32_t log_level, const uint8_t metadata_print,
                    const uint32_t line_number, const char *const file_name,
                    const char *const format, ...)
{
  static const char *const level_name[] = { "NONE", "ERROR", "WARN", "INFO", "DEBUG" };
  int offset = 0;
  va_list args;

  if ((log_level > logging_level) || (log_level > MAX_LOG_LEVEL) ||
      (logging_initialized == 0U) || (logging_output == NULL))
  {
    return;
  }

  /* USBX and ThreadX mutex services are not ISR-safe.  Transport callbacks
     may log from SPI/DMA interrupt context, so those messages are dropped. */
  if (xPortIsInsideInterrupt() != pdFALSE)
  {
    return;
  }

  if (tx_mutex_get(&logging_mutex, TX_WAIT_FOREVER) != TX_SUCCESS)
  {
    return;
  }

  if ((metadata_print != 0U) && (log_level < (sizeof(level_name) / sizeof(level_name[0]))))
  {
    const char *short_name = file_name;
    const char *slash;
    if (short_name == NULL)
    {
      short_name = "?";
    }
    slash = strrchr(short_name, '/');
    if (slash == NULL)
    {
      slash = strrchr(short_name, '\\');
    }
    if (slash != NULL)
    {
      short_name = slash + 1;
    }
    offset = snprintf(logging_buffer, sizeof(logging_buffer),
                      "[%s][%lu][%s:%lu] ", level_name[log_level],
                      (unsigned long)xTaskGetTickCount(), short_name,
                      (unsigned long)line_number);
    if (offset < 0)
    {
      offset = 0;
    }
    if ((size_t)offset >= sizeof(logging_buffer))
    {
      offset = (int)sizeof(logging_buffer) - 1;
    }
  }

  va_start(args, format);
  (void)vsnprintf(&logging_buffer[offset], sizeof(logging_buffer) - (size_t)offset,
                  format, args);
  va_end(args);
  logging_buffer[sizeof(logging_buffer) - 1U] = '\0';
  logging_output(logging_buffer);

  (void)tx_mutex_put(&logging_mutex);
}

void vLoggingDeInit(void)
{
  if (logging_initialized != 0U)
  {
    (void)tx_mutex_delete(&logging_mutex);
    logging_initialized = 0U;
  }
  logging_output = NULL;
}
