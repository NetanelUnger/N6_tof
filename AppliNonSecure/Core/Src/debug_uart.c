/**
  ******************************************************************************
  * @file    debug_uart.c
  * @brief   Bounded asynchronous debug output through the ST-LINK VCP.
  ******************************************************************************
  *
  * USART1 TX/RX are connected to the on-board ST-LINK through PE5/PE6.
  * This small logger deliberately owns and initializes those pins itself so
  * that boot and USB failures can be reported without depending on USBX.
  */

#include "debug_uart.h"

#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "logging_config.h"
#include "debug_cli.h"
#include "main.h"
#include "tof_app.h"
#include "tx_api.h"
#include "usb_cdc_transport.h"
#include "wifi_ble_app.h"
#include "app_usbx_device.h"

#define DEBUG_UART_LINE_SIZE    (256U)
#define DEBUG_UART_TIMEOUT_MS   (100U)
#define DEBUG_UART_TX_MARGIN_MS (20U)
#define DEBUG_UART_EVENT_TX_COMPLETE (1UL << 0)
#define DEBUG_UART_EVENT_TX_ERROR    (1UL << 1)
#define DEBUG_UART_TEST_EVENT_BURST    (1UL << 0)
#define DEBUG_UART_TEST_EVENT_OVERFLOW (1UL << 1)
#define DEBUG_UART_TEST_EVENT_COMMAND  (1UL << 2)
#define DEBUG_UART_TEST_LINE_COUNT     (100U)
#define DEBUG_UART_TEST_FLUSH_MS       (3000U)
#define DEBUG_UART_RX_RING_SIZE        (16U)
#define DEBUG_UART_WATCH_TICKS         (5U * TX_TIMER_TICKS_PER_SECOND)

typedef struct DebugUartSlot DebugUartSlot_t;

struct DebugUartSlot
{
  uint16_t length;
  uint16_t reserved;
  DebugUartSlot_t *next;
  uint8_t data[DEBUG_UART_SLOT_SIZE];
};

typedef enum
{
  DEBUG_UART_TX_OK = 0,
  DEBUG_UART_TX_TIMEOUT,
  DEBUG_UART_TX_HAL_ERROR
} DebugUartTxResult_t;

typedef enum
{
  DEBUG_UART_DROP_POOL = 0,
  DEBUG_UART_DROP_CONTENTION,
  DEBUG_UART_DROP_OVERSIZE,
  DEBUG_UART_DROP_CONTEXT,
  DEBUG_UART_DROP_TRANSPORT,
  DEBUG_UART_DROP_INTERNAL
} DebugUartDropReason_t;

_Static_assert(DEBUG_UART_SLOT_COUNT > 0U,
               "The debug UART slot pool must not be empty");
_Static_assert(DEBUG_UART_SLOT_SIZE >= MAX_LOG_MESSAGE_LENGTH,
               "A formatted ST67 log record must fit in one UART slot");
_Static_assert(sizeof(void *) <= sizeof(ULONG),
               "ThreadX pointer queues require one ULONG per pointer");

static UART_HandleTypeDef debug_uart_handle;
static volatile uint32_t debug_uart_ready;
static volatile uint32_t debug_uart_async_initialized;
static volatile uint32_t debug_uart_async_active;
static volatile uint32_t debug_uart_dropped_messages;
static volatile uint32_t debug_uart_queued_messages;
static volatile uint32_t debug_uart_sent_messages;
static volatile uint32_t debug_uart_queue_full_events;
static volatile uint32_t debug_uart_pool_exhaustions;
static volatile uint32_t debug_uart_producer_contentions;
static volatile uint32_t debug_uart_oversize_rejections;
static volatile uint32_t debug_uart_context_rejections;
static volatile uint32_t debug_uart_transport_failures;
static volatile uint32_t debug_uart_internal_errors;
static volatile uint32_t debug_uart_tx_timeouts;
static volatile uint32_t debug_uart_hal_errors;
static volatile uint32_t debug_uart_slots_in_use;
static volatile uint32_t debug_uart_queue_high_water;
static volatile uint32_t debug_uart_test_pending;
static volatile uint32_t debug_uart_test_running;
static volatile uint32_t debug_uart_test_kind;
static volatile uint32_t debug_uart_test_run_id;
static volatile uint32_t debug_uart_test_completed_runs;
static volatile uint32_t debug_uart_test_attempted;
static volatile uint32_t debug_uart_test_queued_delta;
static volatile uint32_t debug_uart_test_sent_delta;
static volatile uint32_t debug_uart_test_dropped_delta;
static volatile uint32_t debug_uart_test_queue_full_delta;
static volatile uint32_t debug_uart_test_pool_exhaustion_delta;
static volatile uint32_t debug_uart_test_contention_delta;
static volatile uint32_t debug_uart_test_oversize_delta;
static volatile uint32_t debug_uart_test_timeout_delta;
static volatile uint32_t debug_uart_test_hal_error_delta;
static volatile int32_t debug_uart_test_flush_status;
static DebugUartSlot_t debug_uart_slots[DEBUG_UART_SLOT_COUNT];
static TX_QUEUE debug_uart_free_queue;
static TX_QUEUE debug_uart_ready_queue;
static TX_EVENT_FLAGS_GROUP debug_uart_tx_events;
static TX_EVENT_FLAGS_GROUP debug_uart_test_events;
static TX_THREAD *debug_uart_owner_thread;
static ULONG debug_uart_free_queue_storage[DEBUG_UART_SLOT_COUNT];
static ULONG debug_uart_ready_queue_storage[DEBUG_UART_SLOT_COUNT];
static uint8_t debug_uart_rx_byte;
static volatile uint8_t debug_uart_rx_ring[DEBUG_UART_RX_RING_SIZE];
static volatile uint32_t debug_uart_rx_head;
static volatile uint32_t debug_uart_rx_tail;
static volatile uint32_t debug_uart_rx_overruns;
static volatile uint32_t debug_uart_rx_errors;
static volatile uint32_t debug_uart_rx_armed;
static volatile uint32_t debug_uart_watch_component;
static ULONG debug_uart_watch_last_tick;
static volatile uint32_t debug_uart_ncp_trace_enabled;
static volatile uint32_t debug_uart_ncp_trace_sequence;
static volatile uint32_t debug_uart_ncp_terminal_spi_tick;
static volatile uint32_t debug_uart_ncp_terminal_spi_sequence;
static uint32_t debug_uart_ncp_terminal_reported_sequence;

static void Debug_UART_ArmRx(void);

static uint32_t Debug_UART_CriticalEnter(void)
{
  uint32_t interrupt_state = __get_PRIMASK();

  __disable_irq();
  __DMB();
  return interrupt_state;
}

static void Debug_UART_CriticalExit(uint32_t interrupt_state)
{
  __DMB();
  if ((interrupt_state & 1U) == 0U)
  {
    __enable_irq();
  }
}

static void Debug_UART_RecordDrop(DebugUartDropReason_t reason)
{
  uint32_t interrupt_state = Debug_UART_CriticalEnter();

  debug_uart_dropped_messages++;
  switch (reason)
  {
    case DEBUG_UART_DROP_POOL:
      debug_uart_pool_exhaustions++;
      debug_uart_queue_full_events++;
      break;
    case DEBUG_UART_DROP_CONTENTION:
      debug_uart_producer_contentions++;
      break;
    case DEBUG_UART_DROP_OVERSIZE:
      debug_uart_oversize_rejections++;
      break;
    case DEBUG_UART_DROP_CONTEXT:
      debug_uart_context_rejections++;
      break;
    case DEBUG_UART_DROP_TRANSPORT:
      debug_uart_transport_failures++;
      break;
    case DEBUG_UART_DROP_INTERNAL:
    default:
      debug_uart_internal_errors++;
      break;
  }
  Debug_UART_CriticalExit(interrupt_state);
}

static void Debug_UART_RecordTransportFailure(DebugUartTxResult_t result)
{
  uint32_t interrupt_state = Debug_UART_CriticalEnter();

  debug_uart_dropped_messages++;
  debug_uart_transport_failures++;
  if (result == DEBUG_UART_TX_TIMEOUT)
  {
    debug_uart_tx_timeouts++;
  }
  else
  {
    debug_uart_hal_errors++;
  }
  Debug_UART_CriticalExit(interrupt_state);
}

static void Debug_UART_RecordInternalError(uint32_t message_dropped)
{
  uint32_t interrupt_state = Debug_UART_CriticalEnter();

  debug_uart_internal_errors++;
  if (message_dropped != 0U)
  {
    debug_uart_dropped_messages++;
  }
  Debug_UART_CriticalExit(interrupt_state);
}

static uint32_t Debug_UART_StackMinimumFree(void)
{
#ifndef TX_DISABLE_STACK_FILLING
  TX_THREAD *thread = debug_uart_owner_thread;
  ULONG fill_value = 0xEFEFEFEFUL;
  ULONG *cursor;
  ULONG *end;

  if (thread == TX_NULL)
  {
    return 0U;
  }
#ifdef TX_ENABLE_RANDOM_NUMBER_STACK_FILLING
  fill_value = thread->tx_thread_stack_fill_value;
#endif
  cursor = (ULONG *)thread->tx_thread_stack_start;
  end = (ULONG *)((uint8_t *)thread->tx_thread_stack_start +
                  thread->tx_thread_stack_size);
  while ((cursor < end) && (*cursor == fill_value))
  {
    cursor++;
  }
  return (uint32_t)((uint8_t *)cursor -
                    (uint8_t *)thread->tx_thread_stack_start);
#else
  return 0U;
#endif
}

static void Debug_UART_TrackSlotsAdded(uint32_t count)
{
  uint32_t interrupt_state = Debug_UART_CriticalEnter();

  debug_uart_slots_in_use += count;
  if (debug_uart_slots_in_use > debug_uart_queue_high_water)
  {
    debug_uart_queue_high_water = debug_uart_slots_in_use;
  }
  Debug_UART_CriticalExit(interrupt_state);
}

static void Debug_UART_TrackSlotReleased(void)
{
  uint32_t interrupt_state = Debug_UART_CriticalEnter();

  if (debug_uart_slots_in_use != 0U)
  {
    debug_uart_slots_in_use--;
  }
  Debug_UART_CriticalExit(interrupt_state);
}

static void Debug_UART_ReleaseSlot(DebugUartSlot_t *slot)
{
  if (slot != NULL)
  {
    slot->length = 0U;
    slot->next = NULL;
    (void)tx_queue_send(&debug_uart_free_queue, &slot, TX_NO_WAIT);
  }
}

static int32_t Debug_UART_QueueWrite(const void *buffer, size_t length)
{
  const uint8_t *source = (const uint8_t *)buffer;
  DebugUartSlot_t *reserved_slots[DEBUG_UART_SLOT_COUNT];
  size_t remaining = length;
  size_t offset = 0U;
  uint32_t required_slots;
  uint32_t slot_index;
  UINT status;

  if ((length == 0U) ||
      (length > ((size_t)DEBUG_UART_SLOT_COUNT * DEBUG_UART_SLOT_SIZE)))
  {
    Debug_UART_RecordDrop(DEBUG_UART_DROP_OVERSIZE);
    return -3;
  }
  required_slots = (uint32_t)((length + DEBUG_UART_SLOT_SIZE - 1U) /
                              DEBUG_UART_SLOT_SIZE);

  /* ThreadX queue APIs are not valid producer primitives from an ISR. */
  if (__get_IPSR() != 0U)
  {
    Debug_UART_RecordDrop(DEBUG_UART_DROP_CONTEXT);
    return -4;
  }

  /* Each producer owns its reserved slots until it publishes one linked-list
   * head to the ready queue.  This preserves multi-slot message boundaries
   * without a producer mutex or a wait path. */
  for (slot_index = 0U; slot_index < required_slots; slot_index++)
  {
    status = tx_queue_receive(&debug_uart_free_queue,
                              &reserved_slots[slot_index], TX_NO_WAIT);
    if (status != TX_SUCCESS)
    {
      while (slot_index != 0U)
      {
        slot_index--;
        Debug_UART_ReleaseSlot(reserved_slots[slot_index]);
      }
      Debug_UART_RecordDrop(DEBUG_UART_DROP_POOL);
      return -5;
    }
  }
  Debug_UART_TrackSlotsAdded(required_slots);

  for (slot_index = 0U; slot_index < required_slots; slot_index++)
  {
    size_t chunk = (remaining > DEBUG_UART_SLOT_SIZE) ?
                   DEBUG_UART_SLOT_SIZE : remaining;
    DebugUartSlot_t *slot = reserved_slots[slot_index];

    memcpy(slot->data, &source[offset], chunk);
    slot->length = (uint16_t)chunk;
    slot->next = (slot_index + 1U < required_slots) ?
                 reserved_slots[slot_index + 1U] : NULL;
    offset += chunk;
    remaining -= chunk;
  }

  status = tx_queue_send(&debug_uart_ready_queue, &reserved_slots[0],
                         TX_NO_WAIT);
  if (status != TX_SUCCESS)
  {
    /* With at most one ready-queue entry per in-use message and one slot per
     * message minimum, this is an internal invariant failure. */
    for (slot_index = 0U; slot_index < required_slots; slot_index++)
    {
      Debug_UART_ReleaseSlot(reserved_slots[slot_index]);
      Debug_UART_TrackSlotReleased();
    }
    Debug_UART_RecordInternalError(1U);
    return -6;
  }

  {
    uint32_t interrupt_state = Debug_UART_CriticalEnter();

    debug_uart_queued_messages++;
    Debug_UART_CriticalExit(interrupt_state);
  }
  return 0;
}

static int32_t Debug_UART_PollingWrite(const void *buffer, size_t length)
{
  const uint8_t *data = (const uint8_t *)buffer;

  while (length != 0U)
  {
    uint16_t chunk = (length > UINT16_MAX) ? UINT16_MAX : (uint16_t)length;

    if (HAL_UART_Transmit(&debug_uart_handle, (uint8_t *)data, chunk,
                          DEBUG_UART_TIMEOUT_MS) != HAL_OK)
    {
      Debug_UART_RecordTransportFailure(DEBUG_UART_TX_HAL_ERROR);
      return -2;
    }

    data += chunk;
    length -= chunk;
  }
  return 0;
}

static ULONG Debug_UART_TransmitTimeoutTicks(uint16_t length)
{
  uint64_t wire_time_us;
  uint64_t timeout_ms;
  uint64_t timeout_ticks;

  /* One start bit, eight data bits, and one stop bit per byte. */
  wire_time_us = (((uint64_t)length * 10ULL * 1000000ULL) +
                  DEBUG_UART_BAUDRATE - 1ULL) / DEBUG_UART_BAUDRATE;
  timeout_ms = ((wire_time_us + 999ULL) / 1000ULL) +
               DEBUG_UART_TX_MARGIN_MS;
  timeout_ticks = ((timeout_ms * TX_TIMER_TICKS_PER_SECOND) + 999ULL) /
                  1000ULL;
  if (timeout_ticks == 0ULL)
  {
    timeout_ticks = 1ULL;
  }
  return (ULONG)timeout_ticks;
}

static DebugUartTxResult_t Debug_UART_TransmitSlot(DebugUartSlot_t *slot)
{
  ULONG actual_flags = 0U;
  HAL_StatusTypeDef hal_status;
  UINT status;

  (void)tx_event_flags_get(&debug_uart_tx_events,
                           DEBUG_UART_EVENT_TX_COMPLETE |
                           DEBUG_UART_EVENT_TX_ERROR,
                           TX_OR_CLEAR, &actual_flags, TX_NO_WAIT);
  hal_status = HAL_UART_Transmit_IT(&debug_uart_handle, slot->data,
                                    slot->length);
  if (hal_status != HAL_OK)
  {
    return DEBUG_UART_TX_HAL_ERROR;
  }

  status = tx_event_flags_get(&debug_uart_tx_events,
                              DEBUG_UART_EVENT_TX_COMPLETE |
                              DEBUG_UART_EVENT_TX_ERROR,
                              TX_OR_CLEAR, &actual_flags,
                              Debug_UART_TransmitTimeoutTicks(slot->length));
  if (status != TX_SUCCESS)
  {
    (void)HAL_UART_AbortTransmit(&debug_uart_handle);
    return DEBUG_UART_TX_TIMEOUT;
  }
  if ((actual_flags & DEBUG_UART_EVENT_TX_ERROR) != 0U)
  {
    (void)HAL_UART_AbortTransmit(&debug_uart_handle);
    return DEBUG_UART_TX_HAL_ERROR;
  }
  return ((actual_flags & DEBUG_UART_EVENT_TX_COMPLETE) != 0U) ?
         DEBUG_UART_TX_OK : DEBUG_UART_TX_HAL_ERROR;
}

static void Debug_UART_RawString(const char *message)
{
  uint32_t timeout;

  while ((message != NULL) && (*message != '\0'))
  {
    timeout = 1000000U;
    while (((USART1->ISR & USART_ISR_TXE_TXFNF) == 0U) && (timeout != 0U))
    {
      timeout--;
    }

    if (timeout == 0U)
    {
      return;
    }

    USART1->TDR = (uint8_t)*message;
    message++;
  }
}

void Debug_UART_StartupTrace(uint32_t stage)
{
  switch (stage)
  {
    case 1U:
      Debug_UART_RawString("[NS-STARTUP] Reset_Handler entered\r\n");
      break;
    case 2U:
      Debug_UART_RawString("[NS-STARTUP] SystemInit returned\r\n");
      break;
    case 3U:
      Debug_UART_RawString("[NS-STARTUP] .data initialized\r\n");
      break;
    case 4U:
      Debug_UART_RawString("[NS-STARTUP] .bss initialized\r\n");
      break;
    case 5U:
      Debug_UART_RawString("[NS-STARTUP] calling main\r\n");
      break;
    default:
      Debug_UART_RawString("[NS-STARTUP] unknown stage\r\n");
      break;
  }
}

void Debug_UART_StartupFault(uint32_t fault_code)
{
  switch (fault_code)
  {
    case 1U:
      Debug_UART_RawString("[NS-FAULT] HardFault\r\n");
      break;
    case 2U:
      Debug_UART_RawString("[NS-FAULT] MemManage\r\n");
      break;
    case 3U:
      Debug_UART_RawString("[NS-FAULT] BusFault\r\n");
      break;
    case 4U:
      Debug_UART_RawString("[NS-FAULT] UsageFault\r\n");
      break;
    case 5U:
      Debug_UART_RawString("[NS-FAULT] SecureFault\r\n");
      break;
    default:
      Debug_UART_RawString("[NS-FAULT] unknown fault\r\n");
      break;
  }
}

int32_t Debug_UART_Init(void)
{
  GPIO_InitTypeDef gpio_init = {0};
  RCC_PeriphCLKInitTypeDef peripheral_clock = {0};

  if (debug_uart_ready != 0U)
  {
    return 0;
  }

  peripheral_clock.PeriphClockSelection = RCC_PERIPHCLK_USART1;
  /* HSI is kept enabled by the FSBL and avoids relying on an unconfigured IC9. */
  peripheral_clock.Usart1ClockSelection = RCC_USART1CLKSOURCE_HSI;
  if (HAL_RCCEx_PeriphCLKConfig(&peripheral_clock) != HAL_OK)
  {
    return -1;
  }

  __HAL_RCC_GPIOE_CLK_ENABLE();
  __HAL_RCC_USART1_CLK_ENABLE();

  gpio_init.Pin = GPIO_PIN_5 | GPIO_PIN_6;
  gpio_init.Mode = GPIO_MODE_AF_PP;
  gpio_init.Pull = GPIO_PULLUP;
  gpio_init.Speed = GPIO_SPEED_FREQ_HIGH;
  gpio_init.Alternate = GPIO_AF7_USART1;
  HAL_GPIO_Init(GPIOE, &gpio_init);

  debug_uart_handle.Instance = USART1;
  debug_uart_handle.Init.BaudRate = DEBUG_UART_BAUDRATE;
  debug_uart_handle.Init.WordLength = UART_WORDLENGTH_8B;
  debug_uart_handle.Init.StopBits = UART_STOPBITS_1;
  debug_uart_handle.Init.Parity = UART_PARITY_NONE;
  debug_uart_handle.Init.Mode = UART_MODE_TX_RX;
  debug_uart_handle.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  debug_uart_handle.Init.OverSampling = UART_OVERSAMPLING_16;
  debug_uart_handle.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  debug_uart_handle.Init.ClockPrescaler = UART_PRESCALER_DIV1;
  debug_uart_handle.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;

  if (HAL_UART_Init(&debug_uart_handle) != HAL_OK)
  {
    return -2;
  }

  if (HAL_UARTEx_SetTxFifoThreshold(&debug_uart_handle,
                                    UART_TXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    return -3;
  }

  if (HAL_UARTEx_SetRxFifoThreshold(&debug_uart_handle,
                                    UART_RXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    return -4;
  }

  if (HAL_UARTEx_DisableFifoMode(&debug_uart_handle) != HAL_OK)
  {
    return -5;
  }

  HAL_NVIC_SetPriority(USART1_IRQn, 5U, 0U);
  HAL_NVIC_ClearPendingIRQ(USART1_IRQn);
  HAL_NVIC_EnableIRQ(USART1_IRQn);

  debug_uart_ready = 1U;
  return 0;
}

int32_t Debug_UART_AsyncInitialize(void)
{
  uint32_t slot_index;
  UINT status;

  if (debug_uart_async_initialized != 0U)
  {
    return 0;
  }
  if (debug_uart_ready == 0U)
  {
    return -1;
  }

  status = tx_queue_create(&debug_uart_free_queue, "Debug UART free slots",
                           1U, debug_uart_free_queue_storage,
                           sizeof(debug_uart_free_queue_storage));
  if (status != TX_SUCCESS)
  {
    return -2;
  }
  status = tx_queue_create(&debug_uart_ready_queue, "Debug UART ready slots",
                           1U, debug_uart_ready_queue_storage,
                           sizeof(debug_uart_ready_queue_storage));
  if (status != TX_SUCCESS)
  {
    (void)tx_queue_delete(&debug_uart_free_queue);
    return -3;
  }
  status = tx_event_flags_create(&debug_uart_tx_events,
                                 "Debug UART TX events");
  if (status != TX_SUCCESS)
  {
    (void)tx_queue_delete(&debug_uart_ready_queue);
    (void)tx_queue_delete(&debug_uart_free_queue);
    return -4;
  }
  status = tx_event_flags_create(&debug_uart_test_events,
                                 "Debug UART tests");
  if (status != TX_SUCCESS)
  {
    (void)tx_event_flags_delete(&debug_uart_tx_events);
    (void)tx_queue_delete(&debug_uart_ready_queue);
    (void)tx_queue_delete(&debug_uart_free_queue);
    return -5;
  }

  for (slot_index = 0U; slot_index < DEBUG_UART_SLOT_COUNT; slot_index++)
  {
    DebugUartSlot_t *slot = &debug_uart_slots[slot_index];

    Debug_UART_ReleaseSlot(slot);
  }

  debug_uart_async_initialized = 1U;
  return 0;
}

void Debug_UART_TaskRun(void)
{
  DebugUartSlot_t *slot;
  DebugUartSlot_t *next_slot;
  DebugUartTxResult_t transmit_result;
  uint32_t interrupt_state;
  UINT status;

  if (debug_uart_async_initialized == 0U)
  {
    return;
  }

  interrupt_state = Debug_UART_CriticalEnter();
  debug_uart_owner_thread = tx_thread_identify();
  /* tx_application_define runs before scheduling begins.  Activate queued
   * output only now, when its sole consumer can actually drain the pool. */
  debug_uart_async_active = 1U;
  Debug_UART_CriticalExit(interrupt_state);
  Debug_UART_ArmRx();
  for (;;)
  {
    status = tx_queue_receive(&debug_uart_ready_queue, &slot,
                              TX_WAIT_FOREVER);
    if (status != TX_SUCCESS)
    {
      Debug_UART_RecordInternalError(0U);
      tx_thread_sleep(1U);
      continue;
    }

    transmit_result = DEBUG_UART_TX_OK;
    while (slot != NULL)
    {
      next_slot = slot->next;
      if (transmit_result == DEBUG_UART_TX_OK)
      {
        transmit_result = Debug_UART_TransmitSlot(slot);
        if (transmit_result != DEBUG_UART_TX_OK)
        {
          Debug_UART_RecordTransportFailure(transmit_result);
        }
      }
      Debug_UART_ReleaseSlot(slot);
      Debug_UART_TrackSlotReleased();
      slot = next_slot;
    }

    if (transmit_result == DEBUG_UART_TX_OK)
    {
      interrupt_state = Debug_UART_CriticalEnter();
      debug_uart_sent_messages++;
      Debug_UART_CriticalExit(interrupt_state);
    }
  }
}

int32_t Debug_UART_StartTest(uint32_t test_kind, uint32_t *run_id)
{
  ULONG event;
  uint32_t interrupt_state;
  UINT status;

  if ((test_kind != DEBUG_UART_TEST_BURST) &&
      (test_kind != DEBUG_UART_TEST_OVERFLOW))
  {
    return -1;
  }
  if (debug_uart_async_active == 0U)
  {
    return -2;
  }

  interrupt_state = Debug_UART_CriticalEnter();
  if ((debug_uart_test_pending != 0U) || (debug_uart_test_running != 0U))
  {
    Debug_UART_CriticalExit(interrupt_state);
    return -3;
  }
  debug_uart_test_pending = 1U;
  debug_uart_test_kind = test_kind;
  debug_uart_test_run_id++;
  debug_uart_test_attempted = 0U;
  debug_uart_test_queued_delta = 0U;
  debug_uart_test_sent_delta = 0U;
  debug_uart_test_dropped_delta = 0U;
  debug_uart_test_queue_full_delta = 0U;
  debug_uart_test_pool_exhaustion_delta = 0U;
  debug_uart_test_contention_delta = 0U;
  debug_uart_test_oversize_delta = 0U;
  debug_uart_test_timeout_delta = 0U;
  debug_uart_test_hal_error_delta = 0U;
  debug_uart_test_flush_status = -3;
  if (run_id != NULL)
  {
    *run_id = debug_uart_test_run_id;
  }
  Debug_UART_CriticalExit(interrupt_state);

  event = (test_kind == DEBUG_UART_TEST_BURST) ?
          DEBUG_UART_TEST_EVENT_BURST : DEBUG_UART_TEST_EVENT_OVERFLOW;
  status = tx_event_flags_set(&debug_uart_test_events, event, TX_OR);
  if (status != TX_SUCCESS)
  {
    interrupt_state = Debug_UART_CriticalEnter();
    debug_uart_test_pending = 0U;
    debug_uart_internal_errors++;
    Debug_UART_CriticalExit(interrupt_state);
    return -4;
  }
  return 0;
}

static void Debug_UART_ArmRx(void)
{
  if ((debug_uart_async_active != 0U) && (debug_uart_rx_armed == 0U) &&
      (HAL_UART_Receive_IT(&debug_uart_handle, &debug_uart_rx_byte, 1U) == HAL_OK))
  {
    debug_uart_rx_armed = 1U;
  }
}

static void Debug_UART_PrintSnapshot(uint32_t component)
{
  uint32_t now = HAL_GetTick();

  if ((component == 'r') || (component == 'a'))
  {
    WifiBle_RuntimeStatus_t radio;
    WIFI_BLE_App_GetRuntimeStatus(&radio);
    Debug_UART_Log("WATCH-RADIO", "state=%u loop=%lu age=%lums gap_max=%lums BLE mode=%lu link=%lu GATT=%lu conn=%lu MTU=%lu",
                   (unsigned)radio.state, (unsigned long)radio.loop_count,
                   (unsigned long)(now - radio.last_loop_tick),
                   (unsigned long)radio.max_loop_gap_ticks,
                   (unsigned long)radio.ble_mode_confirmed,
                   (unsigned long)radio.ble_link_confirmed,
                   (unsigned long)radio.ble_gatt_ready,
                   (unsigned long)radio.ble_connected,
                   (unsigned long)radio.ble_mtu);
    Debug_UART_Log("WATCH-RADIO", "ADV desired=%lu observed=%lu evidence=%u retry=%lu recovery=%lu probe_status=%ld",
                   (unsigned long)radio.ble_advertising_desired,
                   (unsigned long)radio.ble_advertising,
                   (unsigned)radio.ble_advertising_evidence,
                   (unsigned long)radio.ble_advertising_retry_count,
                   (unsigned long)radio.ble_recovery_pending,
                   (long)radio.ble_last_probe_status);
    Debug_UART_Log("WATCH-RADIO", "WiFi link=%lu IP=%lu confirmed=%lu query_fail=%lu",
                   (unsigned long)radio.wifi_connected,
                   (unsigned long)radio.wifi_has_ip,
                   (unsigned long)radio.wifi_state_confirmed,
                   (unsigned long)radio.manager_health.wifi_query_failures);
    Debug_UART_Log("WATCH-RADIO", "BLE rx_drop=%lu tx_drop=%lu tx_err=%lu busy=%lu timeout=%lu pool_free=%lu",
                   (unsigned long)radio.ble_stream[WIFI_BLE_STREAM_CLI].rx_dropped_bytes,
                   (unsigned long)radio.ble_stream[WIFI_BLE_STREAM_CLI].tx_dropped_messages,
                   (unsigned long)radio.ble_stream[WIFI_BLE_STREAM_CLI].tx_errors,
                   (unsigned long)radio.ble_stream[WIFI_BLE_STREAM_CLI].contention.busy_count,
                   (unsigned long)radio.ble_stream[WIFI_BLE_STREAM_CLI].contention.timeout_count,
                   (unsigned long)radio.ble_radio_pool_available);
    Debug_UART_Log("WATCH-RADIO", "BLE init_fail=%lu adv_fail=%lu query_fail=%lu recovery_fail=%lu",
                   (unsigned long)radio.manager_health.init_failures,
                   (unsigned long)radio.manager_health.advertising_failures,
                   (unsigned long)radio.manager_health.ble_query_failures,
                   (unsigned long)radio.manager_health.ble_recovery_failures);
  }
  if ((component == 't') || (component == 'a'))
  {
    TOF_App_Status_t tof;
    TOF_App_GetStatus(&tof);
    Debug_UART_Log("WATCH-TOF", "state=%u acq=%lu age=%lums proc=%lu age=%lums frame=%lu fps_x10=%lu queue_fail=%lu drop=%lu",
                   (unsigned)tof.state,
                   (unsigned long)tof.acquisition_cycles,
                   (unsigned long)(now - tof.acquisition_last_tick),
                   (unsigned long)tof.processing_cycles,
                   (unsigned long)(now - tof.processing_last_tick),
                   (unsigned long)tof.frame_counter,
                   (unsigned long)tof.fps_x10,
                   (unsigned long)tof.queue_failures,
                   (unsigned long)tof.dropped_frames);
    Debug_UART_Log("WATCH-TOF", "acquired=%lu processed=%lu range=%lu..%lu mm paused=%lu error=%d stage=%s",
                   (unsigned long)tof.acquired_frames,
                   (unsigned long)tof.processed_frames,
                   (unsigned long)tof.minimum_mm,
                   (unsigned long)tof.maximum_mm,
                   (unsigned long)tof.paused, tof.error_code,
                   (tof.error_stage != NULL) ? tof.error_stage : "none");
    Debug_UART_Log("WATCH-TOF", "desired=%lu destination=%s recovery=%lu/%lu/%lu budget=%lu/3 generation=%lu stage=%s error=%d",
                   (unsigned long)tof.desired_revision,
                   TOF_App_StreamName(tof.stream_requested),
                   (unsigned long)tof.recovery_attempts,
                   (unsigned long)tof.recovery_successes,
                   (unsigned long)tof.recovery_failures,
                   (unsigned long)tof.recovery_consecutive_attempts,
                   (unsigned long)tof.recovery_generation,
                   (tof.recovery_stage != NULL) ? tof.recovery_stage : "none",
                   tof.recovery_error);
  }
  if ((component == 'c') || (component == 'a'))
  {
    Debug_CLI_Status_t cli;
    Debug_CLI_GetStatus(&cli);
    Debug_UART_Log("WATCH-CLI", "started=%lu cycles=%lu age=%lums USB=%lu BLE=%lu Cloud=%lu wifi_routed=%lu stale=%lu write_err=%lu",
                   (unsigned long)cli.started, (unsigned long)cli.cycles,
                   (unsigned long)(now - cli.last_tick),
                   (unsigned long)cli.usb_session_ready,
                   (unsigned long)cli.ble_session_ready,
                   (unsigned long)cli.cloud_session_ready,
                   (unsigned long)cli.wifi_results_routed,
                   (unsigned long)cli.wifi_results_stale,
                   (unsigned long)cli.wifi_result_write_errors);
  }
  if ((component == 'u') || (component == 'a'))
  {
    App_USBX_DeviceStatus_t manager;
    USB_CDC_TransportStatus_t cdc;
    App_USBX_Device_GetStatus(&manager);
    USB_CDC_Transport_GetStatus(&cdc);
    Debug_UART_Log("WATCH-USB", "manager=%lu events=%lu event_age_ticks=%lu device=%u CDC=%u DTR=%u recovery=%u post_fail=%lu",
                   (unsigned long)manager.manager_started,
                   (unsigned long)manager.events_processed,
                   (unsigned long)(tx_time_get() - manager.last_event_tick),
                   (unsigned)manager.device_started,
                   (unsigned)manager.cdc_active,
                   (unsigned)manager.dtr_asserted,
                   (unsigned)manager.recovery_count,
                   (unsigned long)manager.event_post_failures);
    Debug_UART_Log("WATCH-USB", "session=%lu host=%u TXq=%lu RXq=%lu in_flight=%lu TXdrop=%lu timeout=%lu",
                   (unsigned long)cdc.session, (unsigned)cdc.host_ready,
                   (unsigned long)cdc.tx_queue_depth,
                   (unsigned long)cdc.rx_queue_depth,
                   (unsigned long)cdc.tx_in_flight,
                   (unsigned long)cdc.tx_packets_dropped,
                   (unsigned long)cdc.tx_callback_timeouts);
    Debug_UART_Log("WATCH-USB", "RXdrop=%lu RXerr=%lu sync_fail=%lu state_snapshot_busy=%u",
                   (unsigned long)cdc.rx_packets_dropped,
                   (unsigned long)cdc.rx_errors,
                   (unsigned long)cdc.worker_sync_failures,
                   (unsigned)cdc.state_snapshot_busy);
  }
}

static void Debug_UART_ProcessCommands(void)
{
  for (;;)
  {
    uint32_t interrupt_state = Debug_UART_CriticalEnter();
    uint32_t tail = debug_uart_rx_tail;
    uint32_t command;

    if (tail == debug_uart_rx_head)
    {
      Debug_UART_CriticalExit(interrupt_state);
      break;
    }
    command = debug_uart_rx_ring[tail];
    debug_uart_rx_tail = (tail + 1U) % DEBUG_UART_RX_RING_SIZE;
    Debug_UART_CriticalExit(interrupt_state);

    if ((command == '\r') || (command == '\n'))
    {
      continue;
    }
    if (command == '?')
    {
      Debug_UART_Log("WATCH", "keys: a=all, r/t/c/u=one-shot Radio/ToF/CLI/USB, R/T/C/U=watch every 5s, n=NCP trace toggle, 0=watch off, ?=help");
    }
    else if (command == 'n')
    {
      uint32_t enabled = __atomic_load_n(&debug_uart_ncp_trace_enabled,
                                         __ATOMIC_RELAXED) == 0U ? 1U : 0U;
      __atomic_store_n(&debug_uart_ncp_trace_enabled, enabled,
                       __ATOMIC_RELAXED);
      Debug_UART_Log("NCP", "trace %s; AT arguments and arbitrary payloads are hidden; press n to toggle",
                     enabled != 0U ? "ON" : "OFF");
    }
    else if (command == '0')
    {
      debug_uart_watch_component = 0U;
      Debug_UART_Log("WATCH", "periodic diagnostics off; ordinary logs remain on");
    }
    else if ((command == 'a') || (command == 'r') || (command == 't') ||
             (command == 'c') || (command == 'u'))
    {
      Debug_UART_PrintSnapshot(command);
    }
    else if ((command == 'R') || (command == 'T') || (command == 'C') ||
             (command == 'U'))
    {
      debug_uart_watch_component = command + ('a' - 'A');
      debug_uart_watch_last_tick = tx_time_get();
      Debug_UART_Log("WATCH", "periodic %c snapshot every 5s; press 0 to stop",
                     (int)debug_uart_watch_component);
      Debug_UART_PrintSnapshot(debug_uart_watch_component);
    }
  }
}

void Debug_UART_TestTaskRun(void)
{
  DebugUart_Status_t before;
  DebugUart_Status_t after;
  ULONG actual_flags = 0U;
  uint32_t interrupt_state;
  uint32_t line;
  uint32_t test_kind;
  int32_t flush_status;
  UINT status;

  for (;;)
  {
    Debug_UART_ArmRx();
    status = tx_event_flags_get(&debug_uart_test_events,
                                DEBUG_UART_TEST_EVENT_BURST |
                                DEBUG_UART_TEST_EVENT_OVERFLOW |
                                DEBUG_UART_TEST_EVENT_COMMAND,
                                TX_OR_CLEAR, &actual_flags,
                                TX_TIMER_TICKS_PER_SECOND);
    if ((status != TX_SUCCESS) && (status != TX_NO_EVENTS))
    {
      Debug_UART_RecordInternalError(0U);
      tx_thread_sleep(1U);
      continue;
    }

    if (status == TX_NO_EVENTS)
    {
      actual_flags = 0U;
    }
    if ((actual_flags & DEBUG_UART_TEST_EVENT_COMMAND) != 0U)
    {
      Debug_UART_ProcessCommands();
    }
    if ((debug_uart_watch_component != 0U) &&
        ((ULONG)(tx_time_get() - debug_uart_watch_last_tick) >=
         DEBUG_UART_WATCH_TICKS))
    {
      debug_uart_watch_last_tick = tx_time_get();
      Debug_UART_PrintSnapshot(debug_uart_watch_component);
    }
    if ((actual_flags & (DEBUG_UART_TEST_EVENT_BURST |
                         DEBUG_UART_TEST_EVENT_OVERFLOW)) == 0U)
    {
      continue;
    }

    test_kind = ((actual_flags & DEBUG_UART_TEST_EVENT_BURST) != 0U) ?
                DEBUG_UART_TEST_BURST : DEBUG_UART_TEST_OVERFLOW;
    interrupt_state = Debug_UART_CriticalEnter();
    debug_uart_test_pending = 0U;
    debug_uart_test_running = 1U;
    debug_uart_test_kind = test_kind;
    debug_uart_test_attempted = DEBUG_UART_TEST_LINE_COUNT;
    Debug_UART_CriticalExit(interrupt_state);

    Debug_UART_GetStatus(&before);
    for (line = 1U; line <= DEBUG_UART_TEST_LINE_COUNT; line++)
    {
      if (test_kind == DEBUG_UART_TEST_BURST)
      {
        Debug_UART_Log("UART-TEST", "M1-BURST %03" PRIu32 "/100", line);
        tx_thread_sleep(1U);
      }
      else
      {
        Debug_UART_Log("UART-TEST", "M1-OVERFLOW %03" PRIu32 "/100", line);
      }
    }
    flush_status = Debug_UART_Flush(DEBUG_UART_TEST_FLUSH_MS);
    Debug_UART_GetStatus(&after);

    interrupt_state = Debug_UART_CriticalEnter();
    debug_uart_test_queued_delta =
        after.queued_messages - before.queued_messages;
    debug_uart_test_sent_delta =
        after.sent_messages - before.sent_messages;
    debug_uart_test_dropped_delta =
        after.dropped_messages - before.dropped_messages;
    debug_uart_test_queue_full_delta =
        after.queue_full_events - before.queue_full_events;
    debug_uart_test_pool_exhaustion_delta =
        after.pool_exhaustions - before.pool_exhaustions;
    debug_uart_test_contention_delta =
        after.producer_contentions - before.producer_contentions;
    debug_uart_test_oversize_delta =
        after.oversize_rejections - before.oversize_rejections;
    debug_uart_test_timeout_delta =
        after.tx_timeouts - before.tx_timeouts;
    debug_uart_test_hal_error_delta =
        after.hal_errors - before.hal_errors;
    debug_uart_test_flush_status = flush_status;
    debug_uart_test_completed_runs++;
    debug_uart_test_running = 0U;
    Debug_UART_CriticalExit(interrupt_state);
  }
}

int32_t Debug_UART_Flush(uint32_t timeout_ms)
{
  ULONG started_at;
  ULONG timeout_ticks;

  if (debug_uart_async_active == 0U)
  {
    return 0;
  }
  if (tx_thread_identify() == debug_uart_owner_thread)
  {
    return -1;
  }

  timeout_ticks = (ULONG)((((uint64_t)timeout_ms *
                            TX_TIMER_TICKS_PER_SECOND) + 999ULL) / 1000ULL);
  started_at = tx_time_get();
  for (;;)
  {
    uint32_t interrupt_state = Debug_UART_CriticalEnter();
    uint32_t slots_in_use = debug_uart_slots_in_use;

    Debug_UART_CriticalExit(interrupt_state);
    if (slots_in_use == 0U)
    {
      return 0;
    }
    if ((timeout_ticks == 0U) ||
        ((ULONG)(tx_time_get() - started_at) >= timeout_ticks))
    {
      return -2;
    }
    tx_thread_sleep(1U);
  }
}

void Debug_UART_IRQHandler(void)
{
  HAL_UART_IRQHandler(&debug_uart_handle);
}

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *uart_handle)
{
  if ((uart_handle == &debug_uart_handle) &&
      (debug_uart_async_active != 0U))
  {
    (void)tx_event_flags_set(&debug_uart_tx_events,
                             DEBUG_UART_EVENT_TX_COMPLETE, TX_OR);
  }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart_handle)
{
  if (uart_handle == &debug_uart_handle)
  {
    uint32_t next = (debug_uart_rx_head + 1U) % DEBUG_UART_RX_RING_SIZE;

    debug_uart_rx_armed = 0U;
    if (next != debug_uart_rx_tail)
    {
      debug_uart_rx_ring[debug_uart_rx_head] = debug_uart_rx_byte;
      __DMB();
      debug_uart_rx_head = next;
      (void)tx_event_flags_set(&debug_uart_test_events,
                               DEBUG_UART_TEST_EVENT_COMMAND, TX_OR);
    }
    else
    {
      debug_uart_rx_overruns++;
    }
    Debug_UART_ArmRx();
  }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart_handle)
{
  if ((uart_handle == &debug_uart_handle) &&
      (debug_uart_async_active != 0U))
  {
    debug_uart_rx_armed = 0U;
    debug_uart_rx_errors++;
    /* USART framing/overrun errors belong to RX.  Do not fail an unrelated
     * asynchronous TX; its own bounded completion wait detects TX failure. */
  }
}

int32_t Debug_UART_Write(const void *buffer, size_t length)
{
  if ((buffer == NULL) || (length == 0U))
  {
    return 0;
  }

  if (debug_uart_ready == 0U)
  {
    return -1;
  }

  if (debug_uart_async_active != 0U)
  {
    return Debug_UART_QueueWrite(buffer, length);
  }

  return Debug_UART_PollingWrite(buffer, length);
}

int32_t Debug_UART_EmergencyWrite(const void *buffer, size_t length)
{
  if ((buffer == NULL) || (length == 0U))
  {
    return 0;
  }
  if (debug_uart_ready == 0U)
  {
    return -1;
  }
  return Debug_UART_PollingWrite(buffer, length);
}

void Debug_UART_Log(const char *component, const char *format, ...)
{
  char line[DEBUG_UART_LINE_SIZE];
  const char *name = (component != NULL) ? component : "APP";
  int prefix_length;
  int body_length;
  size_t used;
  va_list arguments;

  if ((debug_uart_ready == 0U) || (format == NULL))
  {
    return;
  }

  prefix_length = snprintf(line, sizeof(line), "[%010lu][%s] ",
                           (unsigned long)HAL_GetTick(), name);
  if ((prefix_length < 0) || ((size_t)prefix_length >= sizeof(line)))
  {
    Debug_UART_RecordDrop(DEBUG_UART_DROP_INTERNAL);
    return;
  }

  va_start(arguments, format);
  body_length = vsnprintf(&line[prefix_length],
                          sizeof(line) - (size_t)prefix_length,
                          format, arguments);
  va_end(arguments);

  if (body_length < 0)
  {
    Debug_UART_RecordDrop(DEBUG_UART_DROP_INTERNAL);
    return;
  }

  used = (size_t)prefix_length + (size_t)body_length;
  if (used >= (sizeof(line) - 2U))
  {
    used = sizeof(line) - 3U;
  }

  line[used++] = '\r';
  line[used++] = '\n';
  line[used] = '\0';

  (void)Debug_UART_Write(line, used);
}

uint32_t Debug_UART_GetDroppedMessages(void)
{
  uint32_t dropped_messages;
  uint32_t interrupt_state = Debug_UART_CriticalEnter();

  dropped_messages = debug_uart_dropped_messages;
  Debug_UART_CriticalExit(interrupt_state);
  return dropped_messages;
}

uint32_t Debug_UART_NcpTraceEnabled(void)
{
  return __atomic_load_n(&debug_uart_ncp_trace_enabled, __ATOMIC_RELAXED);
}

static const char *Debug_UART_NcpMeaning(const char *verb)
{
  if (strcmp(verb, "AT+BLEINIT?") == 0) return "query BLE mode";
  if (strcmp(verb, "AT+BLECONN?") == 0) return "query BLE link";
  if (strcmp(verb, "AT+BLEADVSTART") == 0) return "start BLE advertising";
  if (strcmp(verb, "AT+BLEADVSTOP") == 0) return "stop BLE advertising";
  if (strcmp(verb, "AT+BLEGATTSNTFY") == 0) return "send BLE notification";
  if (strcmp(verb, "AT+BLEEXCHANGEMTU") == 0) return "exchange BLE MTU";
  if (strcmp(verb, "+BLE:GATTWRITE") == 0) return "BLE client write event";
  if (strcmp(verb, "+BLE:CONNECTED") == 0) return "BLE link connected";
  if (strcmp(verb, "+BLE:DISCONNECTED") == 0) return "BLE link disconnected";
  if (strcmp(verb, "+BLE:NOTIFICATION") == 0) return "BLE notification setting changed";
  if (strcmp(verb, "+BLEINIT") == 0) return "BLE mode response";
  if (strcmp(verb, "+BLECONN") == 0) return "BLE link response";
  return NULL;
}

/* Deliberately print only protocol verbs, fixed replies and event names. AT
 * arguments may contain Wi-Fi passwords, cloud tokens or arbitrary GATT data.
 * Each bus chunk gets a sequence number even when the NCP splits a line. */
void Debug_UART_NcpTerminalObservedAtSpi(void)
{
  /* The SPI owner has a 768-byte stack. Never format or enqueue a UART
   * record here: retain just timestamp/sequence before publishing RX. */
  __atomic_store_n(&debug_uart_ncp_terminal_spi_tick, HAL_GetTick(), __ATOMIC_RELAXED);
  (void)__atomic_add_fetch(&debug_uart_ncp_terminal_spi_sequence, 1U, __ATOMIC_RELEASE);
}

void Debug_UART_NcpTrace(const char *direction, const uint8_t *data,
                         size_t length, int32_t transport_result)
{
  char verb[40];
  const char *meaning = "data (contents hidden)";
  const char *description = NULL;
  size_t start = 0U;
  size_t count = 0U;
  uint32_t sequence;
  uint32_t terminal_reply = 0U;

  if ((Debug_UART_NcpTraceEnabled() == 0U) || (data == NULL) ||
      (length == 0U) || (direction == NULL))
  {
    return;
  }
  sequence = __atomic_add_fetch(&debug_uart_ncp_trace_sequence, 1U,
                                __ATOMIC_RELAXED);
  while ((start < length) && ((data[start] == '\r') || (data[start] == '\n')))
  {
    start++;
  }
  if ((length - start >= 2U) && (data[start] == 'A') &&
      (data[start + 1U] == 'T'))
  {
    while ((start < length) && (count < sizeof(verb) - 1U))
    {
      uint8_t byte = data[start++];
      if ((byte == '=') || (byte == '?') || (byte == '\r') ||
          (byte == '\n') || (byte == ' '))
      {
        if (byte == '?')
        {
          verb[count++] = '?';
        }
        break;
      }
      if (((byte < 'A') || (byte > 'Z')) &&
          ((byte < '0') || (byte > '9')) && (byte != '+'))
      {
        break;
      }
      verb[count++] = (char)byte;
    }
    verb[count] = '\0';
    meaning = verb;
  }
  else if ((length - start >= 2U) && (data[start] == 'O') &&
           (data[start + 1U] == 'K'))
  {
    meaning = "OK (command accepted)";
  }
  else if ((length - start >= 5U) &&
           (memcmp(&data[start], "ERROR", 5U) == 0))
  {
    meaning = "ERROR (command rejected)";
  }
  else if ((start < length) && (data[start] == '>'))
  {
    meaning = "ready for raw data";
  }
  else if ((length - start >= 7U) &&
           (memcmp(&data[start], "SEND OK", 7U) == 0))
  {
    meaning = "SEND OK (payload accepted)";
    terminal_reply = 1U;
  }
  else if ((length - start >= 9U) &&
           (memcmp(&data[start], "SEND FAIL", 9U) == 0))
  {
    meaning = "SEND FAIL (payload rejected)";
    terminal_reply = 1U;
  }
  else if ((length - start >= 5U) &&
           (memcmp(&data[start], "Recv ", 5U) == 0))
  {
    meaning = "Recv (payload length acknowledgement)";
  }
  else if ((start < length) && (data[start] == '+'))
  {
    while ((start < length) && (count < sizeof(verb) - 1U))
    {
      uint8_t byte = data[start++];
      if ((byte == ':') || (byte == ',') || (byte == '\r') ||
          (byte == '\n'))
      {
        /* One colon is part of the +BLE:<event> event name. */
        if ((byte == ':') && (count == 4U) &&
            (memcmp(verb, "+BLE", 4U) == 0))
        {
          verb[count++] = ':';
          continue;
        }
        break;
      }
      if (((byte < 'A') || (byte > 'Z')) &&
          ((byte < '0') || (byte > '9')) && (byte != '+') &&
          (byte != '_'))
      {
        break;
      }
      verb[count++] = (char)byte;
    }
    verb[count] = '\0';
    meaning = verb;
  }
  if (meaning == verb)
  {
    description = Debug_UART_NcpMeaning(verb);
  }
  uint32_t terminal_sequence = __atomic_load_n(&debug_uart_ncp_terminal_spi_sequence, __ATOMIC_ACQUIRE);
  if (terminal_reply && (strcmp(direction, "RX read") == 0) &&
      (terminal_sequence != debug_uart_ncp_terminal_reported_sequence))
  {
    uint32_t spi_tick = __atomic_load_n(&debug_uart_ncp_terminal_spi_tick, __ATOMIC_RELAXED);
    debug_uart_ncp_terminal_reported_sequence = terminal_sequence;
    Debug_UART_Log("NCP", "#%lu %s %s (%lu bytes, transport=%ld, spi_tick=%lu parser_age_ms=%lu)",
                   (unsigned long)sequence, direction, meaning,
                   (unsigned long)length, (long)transport_result,
                   (unsigned long)spi_tick, (unsigned long)(HAL_GetTick() - spi_tick));
  }
  else if (description != NULL)
  {
    Debug_UART_Log("NCP", "#%lu %s %s: %s (%lu bytes, transport=%ld)",
                   (unsigned long)sequence, direction, meaning, description,
                   (unsigned long)length, (long)transport_result);
  }
  else
  {
    Debug_UART_Log("NCP", "#%lu %s %s (%lu bytes, transport=%ld)",
                   (unsigned long)sequence, direction, meaning,
                   (unsigned long)length, (long)transport_result);
  }
}

/* Only the one-character hexadecimal HIL token is safe to show. Never log
 * other CLI commands, which can contain credentials or update payloads. */
void Debug_UART_NcpTracePing(const char *stage, const uint8_t *data,
                             size_t length)
{
  size_t token_at;
  uint8_t token;

  if ((Debug_UART_NcpTraceEnabled() == 0U) || (stage == NULL) ||
      (data == NULL))
  {
    return;
  }
  if ((length >= 12U) && (memcmp(data, "debug ping ", 11U) == 0))
  {
    token_at = 11U;
  }
  else if ((length >= 7U) && (memcmp(data, "PONG ", 5U) == 0))
  {
    token_at = 5U;
  }
  else
  {
    return;
  }
  token = data[token_at];
  if (!(((token >= '0') && (token <= '9')) ||
        ((token >= 'A') && (token <= 'F'))) ||
      ((token_at + 1U < length) && (data[token_at + 1U] != '\r') &&
       (data[token_at + 1U] != ' ') &&
       (data[token_at + 1U] != '\0')))
  {
    return;
  }
  Debug_UART_Log("NCP-CLI", "%s ping token=%c", stage, (int)token);
}

void Debug_UART_NcpTracePingFrame(const char *stage, const uint8_t *data,
                                  size_t length)
{
  if ((Debug_UART_NcpTraceEnabled() == 0U) || (data == NULL) ||
      (length < 13U))
  {
    return;
  }
  for (size_t index = 0U; index + 13U <= length; ++index)
  {
    if (memcmp(&data[index], "debug ping ", 11U) == 0)
    {
      Debug_UART_NcpTracePing(stage, &data[index], length - index);
      return;
    }
  }
}

void Debug_UART_GetStatus(DebugUart_Status_t *status)
{
  uint32_t interrupt_state;
  uint32_t stack_minimum_free;

  if (status == NULL)
  {
    return;
  }

  stack_minimum_free = Debug_UART_StackMinimumFree();
  interrupt_state = Debug_UART_CriticalEnter();
  status->initialized = debug_uart_async_active;
  status->queued_messages = debug_uart_queued_messages;
  status->sent_messages = debug_uart_sent_messages;
  status->dropped_messages = debug_uart_dropped_messages;
  status->queue_full_events = debug_uart_queue_full_events;
  status->pool_exhaustions = debug_uart_pool_exhaustions;
  status->producer_contentions = debug_uart_producer_contentions;
  status->oversize_rejections = debug_uart_oversize_rejections;
  status->context_rejections = debug_uart_context_rejections;
  status->transport_failures = debug_uart_transport_failures;
  status->internal_errors = debug_uart_internal_errors;
  status->tx_timeouts = debug_uart_tx_timeouts;
  status->hal_errors = debug_uart_hal_errors;
  status->slots_in_use = debug_uart_slots_in_use;
  status->slot_capacity = DEBUG_UART_SLOT_COUNT;
  status->queue_high_water = debug_uart_queue_high_water;
  status->rx_overruns = debug_uart_rx_overruns;
  status->rx_errors = debug_uart_rx_errors;
  status->watch_component = debug_uart_watch_component;
  status->task_stack_bytes = (debug_uart_owner_thread != TX_NULL) ?
                             (uint32_t)debug_uart_owner_thread->tx_thread_stack_size :
                             0U;
  status->task_stack_min_free_bytes = stack_minimum_free;
  status->test_running =
      ((debug_uart_test_pending != 0U) || (debug_uart_test_running != 0U)) ?
      1U : 0U;
  status->test_kind = debug_uart_test_kind;
  status->test_run_id = debug_uart_test_run_id;
  status->test_completed_runs = debug_uart_test_completed_runs;
  status->test_attempted = debug_uart_test_attempted;
  status->test_queued_delta = debug_uart_test_queued_delta;
  status->test_sent_delta = debug_uart_test_sent_delta;
  status->test_dropped_delta = debug_uart_test_dropped_delta;
  status->test_queue_full_delta = debug_uart_test_queue_full_delta;
  status->test_pool_exhaustion_delta =
      debug_uart_test_pool_exhaustion_delta;
  status->test_contention_delta = debug_uart_test_contention_delta;
  status->test_oversize_delta = debug_uart_test_oversize_delta;
  status->test_timeout_delta = debug_uart_test_timeout_delta;
  status->test_hal_error_delta = debug_uart_test_hal_error_delta;
  status->test_flush_status = debug_uart_test_flush_status;
  Debug_UART_CriticalExit(interrupt_state);
}
