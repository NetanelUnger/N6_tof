#ifndef FREERTOS_H
#define FREERTOS_H

/*
 * Minimal FreeRTOS API compatibility layer used only by ST's ST67W6X
 * network driver.  Every primitive below is implemented with ThreadX.
 */

#include <stddef.h>
#include <stdint.h>
#include "stm32n6xx.h"
#include "tx_api.h"

typedef int32_t BaseType_t;
typedef uint32_t UBaseType_t;
typedef ULONG TickType_t;
typedef ULONG StackType_t;
typedef TX_THREAD *TaskHandle_t;
typedef void (*TaskFunction_t)(void *argument);

#define pdFALSE                 ((BaseType_t)0)
#define pdTRUE                  ((BaseType_t)1)
#define pdFAIL                  ((BaseType_t)0)
#define pdPASS                  ((BaseType_t)1)

#define portMAX_DELAY           ((TickType_t)TX_WAIT_FOREVER)
#define portTICK_PERIOD_MS      (1000U / TX_TIMER_TICKS_PER_SECOND)
#define configTICK_RATE_HZ      TX_TIMER_TICKS_PER_SECOND
#define configMAX_PRIORITIES    (56U)

#define pdMS_TO_TICKS(ms) \
  ((TickType_t)((((uint64_t)(ms)) * TX_TIMER_TICKS_PER_SECOND + 999ULL) / 1000ULL))

void *pvPortMalloc(size_t size);
void vPortFree(void *memory);
BaseType_t xTaskCreate(TaskFunction_t task_code, const char *name,
                       uint32_t stack_depth, void *argument,
                       UBaseType_t priority, TaskHandle_t *created_task);
void vTaskDelete(TaskHandle_t task);
void vTaskDelay(TickType_t ticks);
TickType_t xTaskGetTickCount(void);
TaskHandle_t xTaskGetCurrentTaskHandle(void);
const char *pcTaskGetName(TaskHandle_t task);
BaseType_t xTaskGetSchedulerState(void);
BaseType_t xPortIsInsideInterrupt(void);
void freertos_compat_enter_critical(void);
void freertos_compat_exit_critical(void);
void freertos_compat_assert(const char *file, uint32_t line);

#define taskENTER_CRITICAL()    freertos_compat_enter_critical()
#define taskEXIT_CRITICAL()     freertos_compat_exit_critical()
#define portYIELD_FROM_ISR(x)   do { (void)(x); } while (0)
#define configASSERT(x)         do { if (!(x)) freertos_compat_assert(__FILE__, __LINE__); } while (0)

#endif /* FREERTOS_H */
