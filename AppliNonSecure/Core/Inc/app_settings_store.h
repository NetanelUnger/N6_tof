#ifndef APP_SETTINGS_STORE_H
#define APP_SETTINGS_STORE_H
#include "app_settings.h"

/* Exact I/O: failure is not absence. begin/end own one finite transaction;
 * adapters separately bound each SDK command and yield only after retirement. */
#define APP_SETTINGS_IO_CHUNK 512U
#define APP_SETTINGS_MAX_COMMANDS 15U /* load: list+2 sizes+12 reads;
                                      * commit: delete+create+6 writes+size+6 reads */
#define APP_SETTINGS_COMMAND_MS 2000U
#define APP_SETTINGS_OPERATION_MS (2000U + 750U * APP_SETTINGS_MAX_COMMANDS)
typedef struct {
  void *context;
  void (*begin)(void *context);
  void (*end)(void *context);
  int (*inventory)(void *context, uint32_t *slots, uint32_t *legacy);
  int (*size)(void *context, unsigned slot, uint32_t *size);
  int (*read)(void *context, unsigned slot, uint32_t offset, void *data, uint32_t length);
  int (*replace)(void *context, unsigned slot, const void *data, uint32_t length);
  int (*confirm)(void *context); /* final cancellation/deadline linearization */
  int (*admit)(void *context); /* optional first-create inventory, before re-encode */
} AppSettings_Io;

typedef struct {
  AppSettings_Record current, pending;
  char *text; /* caller-owned APP_SETTINGS_TEXT_MAX scratch, never heap allocated */
  AppSettings_Result result;
  int active_slot;
  uint32_t loaded;
} AppSettings_Store;

AppSettings_Result AppSettings_StoreLoad(AppSettings_Store *store, const AppSettings_Io *io);
/* The caller holds one mutex, merges fields into pending, and supplies explicit
 * write policy. Only the inactive managed slot can be replaced. */
AppSettings_Result AppSettings_StoreCommit(AppSettings_Store *store,
    const AppSettings_Io *io, uint32_t writes_enabled);
#endif
