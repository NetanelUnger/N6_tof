#include "freertos_compat.h"

#include <string.h>

#include "FreeRTOS.h"
#include "event_groups.h"
#include "main.h"
#include "queue.h"
#include "semphr.h"
#include "task.h"

typedef struct
{
  TX_THREAD thread;
  VOID *stack;
  TaskFunction_t entry;
  void *argument;
} freertos_compat_task_t;

struct freertos_compat_queue
{
  TX_QUEUE queue;
  VOID *storage;
  UINT message_words;
};

typedef enum
{
  FREERTOS_COMPAT_BINARY_SEMAPHORE,
  FREERTOS_COMPAT_MUTEX
} freertos_compat_semaphore_kind_t;

struct freertos_compat_semaphore
{
  freertos_compat_semaphore_kind_t kind;
  union
  {
    TX_SEMAPHORE semaphore;
    TX_MUTEX mutex;
  } object;
};

struct freertos_compat_event_group
{
  TX_EVENT_FLAGS_GROUP group;
};

static TX_BYTE_POOL *compat_byte_pool;
static UINT critical_nesting;
static UINT critical_previous_posture;

static void freertos_task_entry(ULONG input);
static UINT freertos_priority_to_threadx(UBaseType_t priority);
static UINT freertos_wait_to_threadx(TickType_t wait);

UINT FreeRTOS_Compat_Init(TX_BYTE_POOL *byte_pool)
{
  compat_byte_pool = byte_pool;
  critical_nesting = 0U;
  return (byte_pool != TX_NULL) ? TX_SUCCESS : TX_PTR_ERROR;
}

void *pvPortMalloc(size_t size)
{
  VOID *memory = TX_NULL;

  if ((compat_byte_pool == TX_NULL) || (size == 0U))
  {
    return NULL;
  }

  if (tx_byte_allocate(compat_byte_pool, &memory, (ULONG)size, TX_NO_WAIT) != TX_SUCCESS)
  {
    return NULL;
  }

  return memory;
}

void vPortFree(void *memory)
{
  if (memory != NULL)
  {
    (void)tx_byte_release(memory);
  }
}

BaseType_t xPortIsInsideInterrupt(void)
{
  return (__get_IPSR() != 0U) ? pdTRUE : pdFALSE;
}

void freertos_compat_enter_critical(void)
{
  UINT previous = tx_interrupt_control(TX_INT_DISABLE);
  if (critical_nesting == 0U)
  {
    critical_previous_posture = previous;
  }
  ++critical_nesting;
}

void freertos_compat_exit_critical(void)
{
  if (critical_nesting > 0U)
  {
    --critical_nesting;
    if (critical_nesting == 0U)
    {
      (void)tx_interrupt_control(critical_previous_posture);
    }
  }
}

void freertos_compat_assert(const char *file, uint32_t line)
{
  (void)file;
  (void)line;
  Error_Handler();
}

BaseType_t xTaskCreate(TaskFunction_t task_code, const char *name,
                       uint32_t stack_depth, void *argument,
                       UBaseType_t priority, TaskHandle_t *created_task)
{
  freertos_compat_task_t *task;
  ULONG stack_size;

  if ((task_code == NULL) || (compat_byte_pool == TX_NULL))
  {
    return pdFAIL;
  }

  task = (freertos_compat_task_t *)pvPortMalloc(sizeof(*task));
  if (task == NULL)
  {
    return pdFAIL;
  }
  (void)memset(task, 0, sizeof(*task));

  stack_size = (ULONG)stack_depth * (ULONG)sizeof(StackType_t);
  if (stack_size < TX_MINIMUM_STACK)
  {
    stack_size = TX_MINIMUM_STACK;
  }

  task->stack = pvPortMalloc(stack_size);
  if (task->stack == NULL)
  {
    vPortFree(task);
    return pdFAIL;
  }

  task->entry = task_code;
  task->argument = argument;
  if (tx_thread_create(&task->thread, (CHAR *)name, freertos_task_entry,
                       (ULONG)task, task->stack, stack_size,
                       freertos_priority_to_threadx(priority),
                       freertos_priority_to_threadx(priority),
                       TX_NO_TIME_SLICE, TX_AUTO_START) != TX_SUCCESS)
  {
    vPortFree(task->stack);
    vPortFree(task);
    return pdFAIL;
  }

  if (created_task != NULL)
  {
    *created_task = &task->thread;
  }
  return pdPASS;
}

void vTaskDelete(TaskHandle_t task_handle)
{
  TX_THREAD *thread = task_handle;
  TX_THREAD *current = tx_thread_identify();
  freertos_compat_task_t *task;

  if (thread == TX_NULL)
  {
    thread = current;
  }
  if (thread == TX_NULL)
  {
    return;
  }

  task = (freertos_compat_task_t *)thread;
  (void)tx_thread_terminate(thread);

  /* A running thread cannot release its own stack safely.  ThreadX leaves a
     terminated self-delete object allocated, matching FreeRTOS deferred cleanup. */
  if (thread != current)
  {
    (void)tx_thread_delete(thread);
    vPortFree(task->stack);
    vPortFree(task);
  }
}

void vTaskDelay(TickType_t ticks)
{
  (void)tx_thread_sleep((ULONG)ticks);
}

TickType_t xTaskGetTickCount(void)
{
  return tx_time_get();
}

TaskHandle_t xTaskGetCurrentTaskHandle(void)
{
  return tx_thread_identify();
}

const char *pcTaskGetName(TaskHandle_t task)
{
  CHAR *name = (CHAR *)"unknown";
  TX_THREAD *thread = (task != TX_NULL) ? task : tx_thread_identify();

  if (thread != TX_NULL)
  {
    (void)tx_thread_info_get(thread, &name, TX_NULL, TX_NULL, TX_NULL,
                             TX_NULL, TX_NULL, TX_NULL, TX_NULL);
  }
  return name;
}

BaseType_t xTaskGetSchedulerState(void)
{
  return (tx_thread_identify() == TX_NULL) ? taskSCHEDULER_NOT_STARTED : taskSCHEDULER_RUNNING;
}

QueueHandle_t xQueueCreate(UBaseType_t length, UBaseType_t item_size)
{
  struct freertos_compat_queue *queue;
  ULONG storage_size;

  if ((length == 0U) || (item_size == 0U))
  {
    return NULL;
  }

  queue = (struct freertos_compat_queue *)pvPortMalloc(sizeof(*queue));
  if (queue == NULL)
  {
    return NULL;
  }
  (void)memset(queue, 0, sizeof(*queue));

  queue->message_words = (UINT)((item_size + sizeof(ULONG) - 1U) / sizeof(ULONG));
  if (queue->message_words > TX_16_ULONG)
  {
    vPortFree(queue);
    return NULL;
  }

  storage_size = (ULONG)length * (ULONG)queue->message_words * sizeof(ULONG);
  queue->storage = pvPortMalloc(storage_size);
  if (queue->storage == NULL)
  {
    vPortFree(queue);
    return NULL;
  }

  if (tx_queue_create(&queue->queue, "ST67W6X queue", queue->message_words,
                      queue->storage, storage_size) != TX_SUCCESS)
  {
    vPortFree(queue->storage);
    vPortFree(queue);
    return NULL;
  }
  return queue;
}

BaseType_t xQueueSend(QueueHandle_t queue, const void *item, TickType_t wait)
{
  if ((queue == NULL) || (item == NULL))
  {
    return pdFAIL;
  }
  return (tx_queue_send(&queue->queue, (VOID *)item,
                        freertos_wait_to_threadx(wait)) == TX_SUCCESS) ? pdPASS : pdFAIL;
}

BaseType_t xQueueSendToBack(QueueHandle_t queue, const void *item, TickType_t wait)
{
  return xQueueSend(queue, item, wait);
}

BaseType_t xQueueReceive(QueueHandle_t queue, void *item, TickType_t wait)
{
  if ((queue == NULL) || (item == NULL))
  {
    return pdFAIL;
  }
  return (tx_queue_receive(&queue->queue, item,
                           freertos_wait_to_threadx(wait)) == TX_SUCCESS) ? pdPASS : pdFAIL;
}

UBaseType_t uxQueueMessagesWaiting(QueueHandle_t queue)
{
  ULONG enqueued = 0U;
  if (queue != NULL)
  {
    (void)tx_queue_info_get(&queue->queue, TX_NULL, &enqueued, TX_NULL,
                            TX_NULL, TX_NULL, TX_NULL);
  }
  return (UBaseType_t)enqueued;
}

void vQueueDelete(QueueHandle_t queue)
{
  if (queue != NULL)
  {
    (void)tx_queue_delete(&queue->queue);
    vPortFree(queue->storage);
    vPortFree(queue);
  }
}

SemaphoreHandle_t xSemaphoreCreateBinary(void)
{
  struct freertos_compat_semaphore *sem =
    (struct freertos_compat_semaphore *)pvPortMalloc(sizeof(*sem));
  if (sem == NULL)
  {
    return NULL;
  }
  sem->kind = FREERTOS_COMPAT_BINARY_SEMAPHORE;
  if (tx_semaphore_create(&sem->object.semaphore, "ST67W6X binary", 0U) != TX_SUCCESS)
  {
    vPortFree(sem);
    return NULL;
  }
  return sem;
}

SemaphoreHandle_t xSemaphoreCreateMutex(void)
{
  struct freertos_compat_semaphore *sem =
    (struct freertos_compat_semaphore *)pvPortMalloc(sizeof(*sem));
  if (sem == NULL)
  {
    return NULL;
  }
  sem->kind = FREERTOS_COMPAT_MUTEX;
  if (tx_mutex_create(&sem->object.mutex, "ST67W6X mutex", TX_INHERIT) != TX_SUCCESS)
  {
    vPortFree(sem);
    return NULL;
  }
  return sem;
}

BaseType_t xSemaphoreTake(SemaphoreHandle_t sem, TickType_t wait)
{
  UINT status;
  if (sem == NULL)
  {
    return pdFALSE;
  }
  status = (sem->kind == FREERTOS_COMPAT_MUTEX) ?
           tx_mutex_get(&sem->object.mutex, freertos_wait_to_threadx(wait)) :
           tx_semaphore_get(&sem->object.semaphore, freertos_wait_to_threadx(wait));
  return (status == TX_SUCCESS) ? pdTRUE : pdFALSE;
}

BaseType_t xSemaphoreGive(SemaphoreHandle_t sem)
{
  UINT status;
  if (sem == NULL)
  {
    return pdFALSE;
  }
  status = (sem->kind == FREERTOS_COMPAT_MUTEX) ?
           tx_mutex_put(&sem->object.mutex) : tx_semaphore_put(&sem->object.semaphore);
  return (status == TX_SUCCESS) ? pdTRUE : pdFALSE;
}

BaseType_t xSemaphoreGiveFromISR(SemaphoreHandle_t sem,
                                 BaseType_t *higher_priority_task_woken)
{
  if (higher_priority_task_woken != NULL)
  {
    *higher_priority_task_woken = pdFALSE;
  }
  return xSemaphoreGive(sem);
}

void vSemaphoreDelete(SemaphoreHandle_t sem)
{
  if (sem != NULL)
  {
    if (sem->kind == FREERTOS_COMPAT_MUTEX)
    {
      (void)tx_mutex_delete(&sem->object.mutex);
    }
    else
    {
      (void)tx_semaphore_delete(&sem->object.semaphore);
    }
    vPortFree(sem);
  }
}

EventGroupHandle_t xEventGroupCreate(void)
{
  struct freertos_compat_event_group *group =
    (struct freertos_compat_event_group *)pvPortMalloc(sizeof(*group));
  if (group == NULL)
  {
    return NULL;
  }
  if (tx_event_flags_create(&group->group, "ST67W6X events") != TX_SUCCESS)
  {
    vPortFree(group);
    return NULL;
  }
  return group;
}

EventBits_t xEventGroupWaitBits(EventGroupHandle_t group, EventBits_t bits,
                               BaseType_t clear_on_exit,
                               BaseType_t wait_for_all,
                               TickType_t wait)
{
  ULONG actual = 0U;
  UINT option;

  if (group == NULL)
  {
    return 0U;
  }

  if (wait_for_all != pdFALSE)
  {
    option = (clear_on_exit != pdFALSE) ? TX_AND_CLEAR : TX_AND;
  }
  else
  {
    option = (clear_on_exit != pdFALSE) ? TX_OR_CLEAR : TX_OR;
  }
  (void)tx_event_flags_get(&group->group, bits, option, &actual,
                           freertos_wait_to_threadx(wait));
  return actual;
}

EventBits_t xEventGroupSetBits(EventGroupHandle_t group, EventBits_t bits)
{
  if (group == NULL)
  {
    return 0U;
  }
  (void)tx_event_flags_set(&group->group, bits, TX_OR);
  return xEventGroupGetBits(group);
}

BaseType_t xEventGroupSetBitsFromISR(EventGroupHandle_t group, EventBits_t bits,
                                     BaseType_t *higher_priority_task_woken)
{
  UINT status;
  if (higher_priority_task_woken != NULL)
  {
    *higher_priority_task_woken = pdFALSE;
  }
  if (group == NULL)
  {
    return pdFAIL;
  }
  status = tx_event_flags_set(&group->group, bits, TX_OR);
  return (status == TX_SUCCESS) ? pdPASS : pdFAIL;
}

EventBits_t xEventGroupClearBits(EventGroupHandle_t group, EventBits_t bits)
{
  EventBits_t previous = xEventGroupGetBits(group);
  if (group != NULL)
  {
    (void)tx_event_flags_set(&group->group, ~bits, TX_AND);
  }
  return previous;
}

EventBits_t xEventGroupGetBits(EventGroupHandle_t group)
{
  ULONG actual = 0U;
  if (group != NULL)
  {
    (void)tx_event_flags_get(&group->group, 0xFFFFFFFFUL, TX_OR,
                             &actual, TX_NO_WAIT);
  }
  return actual;
}

void vEventGroupDelete(EventGroupHandle_t group)
{
  if (group != NULL)
  {
    (void)tx_event_flags_delete(&group->group);
    vPortFree(group);
  }
}

static void freertos_task_entry(ULONG input)
{
  freertos_compat_task_t *task = (freertos_compat_task_t *)input;
  task->entry(task->argument);
  (void)tx_thread_terminate(&task->thread);
}

static UINT freertos_priority_to_threadx(UBaseType_t priority)
{
  UINT max_priority = (TX_MAX_PRIORITIES > 1U) ? (TX_MAX_PRIORITIES - 1U) : 1U;
  UINT mapped;

  if (priority >= configMAX_PRIORITIES)
  {
    priority = configMAX_PRIORITIES - 1U;
  }
  mapped = max_priority - (UINT)((priority * (max_priority - 1U)) /
                                 (configMAX_PRIORITIES - 1U));
  return (mapped == 0U) ? 1U : mapped;
}

static UINT freertos_wait_to_threadx(TickType_t wait)
{
  return (wait == portMAX_DELAY) ? TX_WAIT_FOREVER : (UINT)wait;
}
