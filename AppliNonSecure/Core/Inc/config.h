#ifndef N6_CONFIG_H
#define N6_CONFIG_H

/* Development diagnostics. Change application diagnostic output here, then rebuild.
 * Fault reporting and explicitly requested CLI status/data are operational
 * output and remain available. Resource counters and watchdog stay active. */
#define N6_DEBUG_OUTPUT_ENABLED       (1U)
#define N6_CLI_DIAGNOSTICS_ENABLED    (1U)

/* Optional GC9A01 screen: uncomment to build its task, driver and hardware. */
/* #define APP_GC9A01_DISPLAY_ENABLED */

/* ST67 logging switches share the same compile-time policy. */
#define WIFI_LOG_ENABLE              N6_DEBUG_OUTPUT_ENABLED
#define NET_LOG_ENABLE               N6_DEBUG_OUTPUT_ENABLED
#define SYS_LOG_ENABLE               N6_DEBUG_OUTPUT_ENABLED
#define W61_AT_LOG_ENABLE            N6_DEBUG_OUTPUT_ENABLED
#define MDM_CMD_LOG_ENABLE           N6_DEBUG_OUTPUT_ENABLED

#endif /* N6_CONFIG_H */
