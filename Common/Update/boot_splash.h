#ifndef BOOT_SPLASH_H
#define BOOT_SPLASH_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define N6_FSBL_VERSION_TEXT             "1.1.0"
#define N6_SECURE_RUNTIME_VERSION_TEXT   "1.1.0"

typedef void (*N6_BootSplashWrite_t)(const char *text);

typedef struct
{
  const char *stage;
  const char *version;
  const char *detail_1;
  const char *detail_2;
  const char *detail_3;
  const char *detail_4;
} N6_BootSplashConfig_t;

/* Append-only UART banner: no delay, cursor movement or screen erase.
 * Keep output small because UART wire time contributes to boot latency. */
static void N6_BootSplashShow(N6_BootSplashWrite_t write_text,
                              const N6_BootSplashConfig_t *config)
{
  if ((write_text == NULL) || (config == NULL))
  {
    return;
  }
  write_text("\r\n"
             "  +-----------------------------------------+\r\n"
             "  |  N   N  AAA  TTTTT I   L     AAA  BBBB   |\r\n"
             "  |  NN  N A   A   T   I   L    A   A B   B  |\r\n"
             "  |  N N N AAAAA   T   I   L    AAAAA BBBB   |\r\n"
             "  |  N  NN A   A   T   I   L    A   A B   B  |\r\n"
             "  |  N   N A   A   T   I   LLLL A   A BBBB   |\r\n"
             "  +--------------- Nati Lab ----------------+\r\n");
  if (config->stage != NULL)
  {
    write_text("[BOOT] ");
    write_text(config->stage);
    write_text("\r\n");
  }
  if (config->version != NULL)
  {
    write_text("[BOOT] ");
    write_text(config->version);
    write_text("\r\n");
  }
  if (config->detail_4 != NULL)
  {
    write_text("[BOOT] ");
    write_text(config->detail_4);
    write_text("\r\n");
  }
}

#ifdef __cplusplus
}
#endif

#endif /* BOOT_SPLASH_H */
