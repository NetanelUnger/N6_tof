#ifndef N6_WATCHDOG_H
#define N6_WATCHDOG_H
#include "app_features.h"
#include "n6_watchdog_policy.h"
#if (N6_WATCHDOG_ENABLED == 1U)
void N6H_Beat(uint32_t task);
void N6H_Run(void);
uint32_t N6H_UartCommand(uint32_t command);
#define N6H_IDLE_TICKS (TX_TIMER_TICKS_PER_SECOND/10U)
#else
#define N6H_Beat(task) ((void)0)
#define N6H_UartCommand(command) (0U)
#define N6H_IDLE_TICKS TX_WAIT_FOREVER
#endif
#endif
