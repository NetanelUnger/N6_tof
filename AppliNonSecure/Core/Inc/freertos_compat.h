#ifndef FREERTOS_COMPAT_H
#define FREERTOS_COMPAT_H

#include "tx_api.h"

UINT FreeRTOS_Compat_Init(TX_BYTE_POOL *byte_pool);

typedef struct
{
  ULONG failures;
  ULONG requested_bytes;
  ULONG available_bytes;
  ULONG fragments;
  ULONG threadx_status;
  ULONG tick;
} FreeRTOS_Compat_AllocationStatus_t;

void FreeRTOS_Compat_GetAllocationStatus(FreeRTOS_Compat_AllocationStatus_t *status);

#endif /* FREERTOS_COMPAT_H */
