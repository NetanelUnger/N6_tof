#ifndef APP_LOGGING_H
#define APP_LOGGING_H

#include <stdint.h>

typedef struct
{
  uint32_t submitted_messages;
  uint32_t buffer_exhaustions;
  uint32_t interrupt_rejections;
  uint32_t format_errors;
} AppLogging_Status_t;

void App_Logging_SetVerbosity(uint32_t level);
uint32_t App_Logging_GetVerbosity(void);
void App_Logging_GetStatus(AppLogging_Status_t *status);

#endif /* APP_LOGGING_H */
