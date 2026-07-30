#ifndef DEBUG_UART_H
#define DEBUG_UART_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define DEBUG_UART_BAUDRATE  (115200U)

int32_t Debug_UART_Init(void);
int32_t Debug_UART_Write(const void *buffer, size_t length);
void Debug_UART_Log(const char *component, const char *format, ...);
uint32_t Debug_UART_GetDroppedMessages(void);

/* These two functions do not use HAL state or initialized RAM.  They are safe
 * to call directly from Reset_Handler before .data/.bss initialization. */
void Debug_UART_StartupTrace(uint32_t stage);
void Debug_UART_StartupFault(uint32_t fault_code);

#ifdef __cplusplus
}
#endif

#endif /* DEBUG_UART_H */
