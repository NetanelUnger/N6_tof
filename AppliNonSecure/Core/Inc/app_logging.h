#ifndef APP_LOGGING_H
#define APP_LOGGING_H

#include <stdint.h>

void App_Logging_SetVerbosity(uint32_t level);
uint32_t App_Logging_GetVerbosity(void);

#endif /* APP_LOGGING_H */
