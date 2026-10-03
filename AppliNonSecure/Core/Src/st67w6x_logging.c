#include "logging.h"
#include "app_logging.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "task.h"

#define ST67_LOG_BUFFER_COUNT  (4U)

_Static_assert(sizeof(void *) <= sizeof(ULONG),
               "ThreadX pointer queues require one ULONG per pointer");

static TX_QUEUE logging_free_buffers;
static ULONG logging_free_buffer_storage[ST67_LOG_BUFFER_COUNT];
static char logging_buffers[ST67_LOG_BUFFER_COUNT][MAX_LOG_MESSAGE_LENGTH];
static UINT logging_initialized;
static uint32_t logging_level = LOG_DEFAULT_LEVEL;
static void (*logging_output)(const char *message);
static uint32_t logging_submitted_messages;
static uint32_t logging_buffer_exhaustions;
static uint32_t logging_interrupt_rejections;
static uint32_t logging_format_errors;

void *vLoggingInit(void (*LogOutput_cb)(const char *message))
{
  logging_output = LogOutput_cb;
  if (logging_initialized == 0U)
  {
    uint32_t index;

    if (tx_queue_create(&logging_free_buffers, "ST67 log buffers", 1U,
                        logging_free_buffer_storage,
                        sizeof(logging_free_buffer_storage)) != TX_SUCCESS)
    {
      return NULL;
    }
    for (index = 0U; index < ST67_LOG_BUFFER_COUNT; index++)
    {
      char *buffer = logging_buffers[index];

      if (tx_queue_send(&logging_free_buffers, &buffer, TX_NO_WAIT) != TX_SUCCESS)
      {
        (void)tx_queue_delete(&logging_free_buffers);
        return NULL;
      }
    }
    logging_initialized = 1U;
  }
  return &logging_free_buffers;
}

void vLoggingSetVerbosity(uint32_t level)
{
  if (level <= MAX_LOG_LEVEL)
  {
    __atomic_store_n(&logging_level, level, __ATOMIC_RELAXED);
  }
}

void App_Logging_SetVerbosity(uint32_t level)
{
  vLoggingSetVerbosity(level);
}

uint32_t App_Logging_GetVerbosity(void)
{
  return __atomic_load_n(&logging_level, __ATOMIC_RELAXED);
}

void App_Logging_GetStatus(AppLogging_Status_t *status)
{
  if (status == NULL)
  {
    return;
  }

  status->submitted_messages =
      __atomic_load_n(&logging_submitted_messages, __ATOMIC_RELAXED);
  status->buffer_exhaustions =
      __atomic_load_n(&logging_buffer_exhaustions, __ATOMIC_RELAXED);
  status->interrupt_rejections =
      __atomic_load_n(&logging_interrupt_rejections, __ATOMIC_RELAXED);
  status->format_errors =
      __atomic_load_n(&logging_format_errors, __ATOMIC_RELAXED);
}

void vLoggingPrintf(uint32_t log_level, const uint8_t metadata_print,
                    const uint32_t line_number, const char *const file_name,
                    const char *const format, ...)
{
  static const char *const level_name[] = { "NONE", "ERROR", "WARN", "INFO", "DEBUG" };
  char *logging_buffer;
  int offset = 0;
  int format_result;
  va_list args;

  if ((log_level > __atomic_load_n(&logging_level, __ATOMIC_RELAXED)) ||
      (log_level > MAX_LOG_LEVEL) ||
      (logging_initialized == 0U) || (logging_output == NULL))
  {
    return;
  }

  /* ThreadX queue services are not used from interrupt context.  Transport
   * callbacks may log from SPI/DMA interrupts, so count those rejections. */
  if (xPortIsInsideInterrupt() != pdFALSE)
  {
    (void)__atomic_fetch_add(&logging_interrupt_rejections, 1U,
                             __ATOMIC_RELAXED);
    return;
  }

  if (tx_queue_receive(&logging_free_buffers, &logging_buffer,
                       TX_NO_WAIT) != TX_SUCCESS)
  {
    (void)__atomic_fetch_add(&logging_buffer_exhaustions, 1U,
                             __ATOMIC_RELAXED);
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
    offset = snprintf(logging_buffer, MAX_LOG_MESSAGE_LENGTH,
                      "[%s][%lu][%s:%lu] ", level_name[log_level],
                      (unsigned long)xTaskGetTickCount(), short_name,
                      (unsigned long)line_number);
    if (offset < 0)
    {
      (void)__atomic_fetch_add(&logging_format_errors, 1U, __ATOMIC_RELAXED);
      (void)tx_queue_send(&logging_free_buffers, &logging_buffer, TX_NO_WAIT);
      return;
    }
    if ((size_t)offset >= MAX_LOG_MESSAGE_LENGTH)
    {
      offset = (int)MAX_LOG_MESSAGE_LENGTH - 1;
    }
  }

  va_start(args, format);
  format_result = vsnprintf(&logging_buffer[offset],
                            MAX_LOG_MESSAGE_LENGTH - (size_t)offset,
                            format, args);
  va_end(args);
  logging_buffer[MAX_LOG_MESSAGE_LENGTH - 1U] = '\0';
  if (format_result < 0)
  {
    (void)__atomic_fetch_add(&logging_format_errors, 1U, __ATOMIC_RELAXED);
    (void)tx_queue_send(&logging_free_buffers, &logging_buffer, TX_NO_WAIT);
    return;
  }
  /* The output callback copies into a fixed UART slot.  Physical USART1
   * transmission happens later in the owner task.  This buffer belongs to
   * this message until that copy returns, so producers never share storage. */
  logging_output(logging_buffer);
  (void)__atomic_fetch_add(&logging_submitted_messages, 1U, __ATOMIC_RELAXED);
  (void)tx_queue_send(&logging_free_buffers, &logging_buffer, TX_NO_WAIT);
}

void vLoggingDeInit(void)
{
  if (logging_initialized != 0U)
  {
    (void)tx_queue_delete(&logging_free_buffers);
    logging_initialized = 0U;
  }
  logging_output = NULL;
}
