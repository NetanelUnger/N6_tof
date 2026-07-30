#ifndef APP_CONSOLE_H
#define APP_CONSOLE_H

#include "tx_api.h"

typedef struct
{
  CHAR *data;
  ULONG capacity;
  VOID *handle;
} App_Console_FrameBuffer_t;

UINT App_Console_Init(void);
UINT App_Console_IsReady(void);
UINT App_Console_Write(const void *buffer, ULONG length);
UINT App_Console_WriteAsync(const void *buffer, ULONG length);
UINT App_Console_Read(void *buffer, ULONG requested_length, ULONG *actual_length);
UINT App_Console_AcquireFrameBuffer(App_Console_FrameBuffer_t *buffer);
UINT App_Console_CommitFrameBuffer(App_Console_FrameBuffer_t *buffer,
                                   ULONG length);
void App_Console_CancelFrameBuffer(App_Console_FrameBuffer_t *buffer);

#endif /* APP_CONSOLE_H */
