#ifndef BOOT_SPLASH_H
#define BOOT_SPLASH_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

#define N6_BOOT_SPLASH_WIDTH             (50U)
#define N6_BOOT_SPLASH_HEIGHT            (50U)
#define N6_BOOT_SPLASH_DURATION_MS       (5000U)
#define N6_FSBL_VERSION_TEXT             "1.1.0"
#define N6_SECURE_RUNTIME_VERSION_TEXT   "1.1.0"

typedef void (*N6_BootSplashWrite_t)(const char *text);
typedef void (*N6_BootSplashDelay_t)(uint32_t milliseconds);

typedef struct
{
  const char *stage;
  const char *version;
  const char *detail_1;
  const char *detail_2;
  const char *detail_3;
  const char *detail_4;
} N6_BootSplashConfig_t;

static void N6_BootSplashWriteLine(N6_BootSplashWrite_t write_text,
                                   const char *text,
                                   uint32_t final_line)
{
  char line[N6_BOOT_SPLASH_WIDTH + 3U];
  size_t text_length = (text != NULL) ? strlen(text) : 0U;
  size_t start;

  if (text_length > (N6_BOOT_SPLASH_WIDTH - 2U))
  {
    text_length = N6_BOOT_SPLASH_WIDTH - 2U;
  }

  line[0] = '|';
  (void)memset(&line[1], ' ', N6_BOOT_SPLASH_WIDTH - 2U);
  line[N6_BOOT_SPLASH_WIDTH - 1U] = '|';
  start = 1U + ((N6_BOOT_SPLASH_WIDTH - 2U - text_length) / 2U);
  if (text_length != 0U)
  {
    (void)memcpy(&line[start], text, text_length);
  }

  if (final_line == 0U)
  {
    line[N6_BOOT_SPLASH_WIDTH] = '\r';
    line[N6_BOOT_SPLASH_WIDTH + 1U] = '\n';
    line[N6_BOOT_SPLASH_WIDTH + 2U] = '\0';
  }
  else
  {
    line[N6_BOOT_SPLASH_WIDTH] = '\0';
  }
  write_text(line);
}

static void N6_BootSplashWriteBorder(N6_BootSplashWrite_t write_text,
                                     uint32_t final_line)
{
  char line[N6_BOOT_SPLASH_WIDTH + 3U];

  line[0] = '+';
  (void)memset(&line[1], '-', N6_BOOT_SPLASH_WIDTH - 2U);
  line[N6_BOOT_SPLASH_WIDTH - 1U] = '+';
  if (final_line == 0U)
  {
    line[N6_BOOT_SPLASH_WIDTH] = '\r';
    line[N6_BOOT_SPLASH_WIDTH + 1U] = '\n';
    line[N6_BOOT_SPLASH_WIDTH + 2U] = '\0';
  }
  else
  {
    line[N6_BOOT_SPLASH_WIDTH] = '\0';
  }
  write_text(line);
}

static const char *N6_BootSplashContent(
    const N6_BootSplashConfig_t *config, uint32_t row)
{
  switch (row)
  {
    case 2U:  return "NATI LAB EMBEDDED SYSTEMS";
    case 5U:  return "N   N   A   TTTTT  I      L      A   BBBB";
    case 6U:  return "NN  N  A A    T    I      L     A A  B   B";
    case 7U:  return "N N N AAAAA   T    I      L    AAAAA BBBB";
    case 8U:  return "N  NN A   A   T    I      L    A   A B   B";
    case 9U:  return "N   N A   A   T    I      LLLL A   A BBBB";
    case 12U: return "========================================";
    case 15U: return config->stage;
    case 18U: return config->version;
    case 22U: return config->detail_1;
    case 24U: return config->detail_2;
    case 26U: return config->detail_3;
    case 28U: return config->detail_4;
    case 33U: return "BOOT SEQUENCE IN PROGRESS";
    case 38U: return "Hardware -> Secure -> Application";
    case 43U: return "This stage remains visible for 5 seconds";
    case 47U: return "Secure embedded systems, made visible";
    default:  return "";
  }
}

static void N6_BootSplashShow(N6_BootSplashWrite_t write_text,
                              N6_BootSplashDelay_t delay,
                              const N6_BootSplashConfig_t *config)
{
  uint32_t row;

  if ((write_text == NULL) || (delay == NULL) || (config == NULL))
  {
    return;
  }

  write_text("\033[?25l\033[2J\033[H");
  N6_BootSplashWriteBorder(write_text, 0U);
  for (row = 1U; row < (N6_BOOT_SPLASH_HEIGHT - 1U); row++)
  {
    N6_BootSplashWriteLine(write_text,
                           N6_BootSplashContent(config, row), 0U);
  }
  N6_BootSplashWriteBorder(write_text, 1U);
  delay(N6_BOOT_SPLASH_DURATION_MS);
  write_text("\033[?25h\033[2J\033[H");
}

#ifdef __cplusplus
}
#endif

#endif /* BOOT_SPLASH_H */
