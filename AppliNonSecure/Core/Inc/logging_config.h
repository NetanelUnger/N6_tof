#ifndef LOGGING_CONFIG_H
#define LOGGING_CONFIG_H

#include "logging_levels.h"

/* Compile all levels in; the runtime default remains INFO and the USB CLI can
 * raise or lower it without rebuilding the firmware. */
#define LOG_LEVEL               LOG_DEBUG
#define LOG_DEFAULT_LEVEL       LOG_INFO
#define MAX_LOG_LEVEL           LOG_DEBUG
#define LOG_INCLUDE_TASKNAME    (1)
#define LOG_INCLUDE_FILENAME    (1)
#define LOG_INCLUDE_TIMESTAMP   (1)
#define MAX_LOG_MESSAGE_LENGTH  (512U)

/* The asynchronous USART1 transport owns a fixed, allocation-free slot pool.
 * Keep the slot size equal to the largest formatted ST67 log record so one
 * normal log line always fits in a single slot. */
#define DEBUG_UART_SLOT_COUNT    (32U)
#define DEBUG_UART_SLOT_SIZE     (512U)

#endif /* LOGGING_CONFIG_H */
