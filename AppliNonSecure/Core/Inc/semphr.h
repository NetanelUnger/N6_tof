#ifndef SEMPHR_H
#define SEMPHR_H

#include "FreeRTOS.h"

typedef struct freertos_compat_semaphore *SemaphoreHandle_t;

SemaphoreHandle_t xSemaphoreCreateBinary(void);
SemaphoreHandle_t xSemaphoreCreateMutex(void);
BaseType_t xSemaphoreTake(SemaphoreHandle_t semaphore, TickType_t wait);
BaseType_t xSemaphoreGive(SemaphoreHandle_t semaphore);
BaseType_t xSemaphoreGiveFromISR(SemaphoreHandle_t semaphore,
                                 BaseType_t *higher_priority_task_woken);
void vSemaphoreDelete(SemaphoreHandle_t semaphore);

#endif /* SEMPHR_H */
