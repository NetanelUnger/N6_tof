#ifndef EVENT_GROUPS_H
#define EVENT_GROUPS_H

#include "FreeRTOS.h"

typedef ULONG EventBits_t;
typedef struct freertos_compat_event_group *EventGroupHandle_t;

EventGroupHandle_t xEventGroupCreate(void);
EventBits_t xEventGroupWaitBits(EventGroupHandle_t group, EventBits_t bits,
                               BaseType_t clear_on_exit,
                               BaseType_t wait_for_all,
                               TickType_t wait);
EventBits_t xEventGroupSetBits(EventGroupHandle_t group, EventBits_t bits);
BaseType_t xEventGroupSetBitsFromISR(EventGroupHandle_t group, EventBits_t bits,
                                     BaseType_t *higher_priority_task_woken);
EventBits_t xEventGroupClearBits(EventGroupHandle_t group, EventBits_t bits);
EventBits_t xEventGroupGetBits(EventGroupHandle_t group);
void vEventGroupDelete(EventGroupHandle_t group);

#endif /* EVENT_GROUPS_H */
