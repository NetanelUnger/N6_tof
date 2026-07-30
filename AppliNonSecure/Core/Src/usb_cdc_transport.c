#include "usb_cdc_transport.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "app_usbx_device.h"
#include "debug_uart.h"
#include "ux_device_cdc_acm.h"

#define USB_CDC_TX_CONTROL_SLOT_COUNT  (8U)
#define USB_CDC_TX_CONTROL_SLOT_SIZE   (768U)
#define USB_CDC_TX_MAP_SLOT_COUNT      (2U)
#define USB_CDC_TX_MAP_SLOT_SIZE       (48U * 1024U)
#define USB_CDC_TX_QUEUE_DEPTH         (USB_CDC_TX_CONTROL_SLOT_COUNT + \
                                        USB_CDC_TX_MAP_SLOT_COUNT)
#define USB_CDC_RX_SLOT_COUNT          (16U)
#define USB_CDC_RX_SLOT_SIZE           (512U)
#define USB_CDC_TX_STACK_SIZE          (12U * 1024U)
#define USB_CDC_RX_STACK_SIZE          (12U * 1024U)
#define USB_CDC_WORKER_PRIORITY        (9U)
#define USB_CDC_MAX_TX_ATTEMPTS        (3U)
#define USB_CDC_ERROR_BACKOFF_TICKS    (((TX_TIMER_TICKS_PER_SECOND / 100U) != 0U) ? \
                                        (TX_TIMER_TICKS_PER_SECOND / 100U) : 1U)

#define USB_CDC_FLAG_ACTIVE            (1UL << 0)
#define USB_CDC_FLAG_RX_IDLE           (1UL << 1)
#define USB_CDC_FLAG_TX_IDLE           (1UL << 2)
#define USB_CDC_FLAG_WORKERS_IDLE      (USB_CDC_FLAG_RX_IDLE | USB_CDC_FLAG_TX_IDLE)

typedef enum
{
  USB_CDC_SLOT_FREE = 0,
  USB_CDC_SLOT_RESERVED,
  USB_CDC_SLOT_QUEUED,
  USB_CDC_SLOT_IN_FLIGHT,
  USB_CDC_SLOT_DELIVERY
} USB_CDC_SlotState_t;

typedef enum
{
  USB_CDC_TX_CONTROL = 0,
  USB_CDC_TX_MAP
} USB_CDC_TxKind_t;

typedef struct
{
  UCHAR *data;
  ULONG capacity;
  ULONG length;
  ULONG session;
  USB_CDC_SlotState_t state;
  USB_CDC_TxKind_t kind;
} USB_CDC_TxSlot_t;

typedef struct
{
  UCHAR data[USB_CDC_RX_SLOT_SIZE];
  ULONG length;
  ULONG session;
  USB_CDC_SlotState_t state;
} USB_CDC_RxSlot_t;

static TX_QUEUE usb_cdc_tx_queue;
static TX_QUEUE usb_cdc_rx_ingress_queue;
static TX_QUEUE usb_cdc_rx_delivery_queue;
static TX_EVENT_FLAGS_GROUP usb_cdc_worker_flags;
static TX_MUTEX usb_cdc_state_mutex;
static TX_MUTEX usb_cdc_io_mutex;
static TX_MUTEX usb_cdc_rx_consumer_mutex;
static TX_SEMAPHORE usb_cdc_control_free;
static TX_SEMAPHORE usb_cdc_map_free;
static TX_SEMAPHORE usb_cdc_rx_free;
static TX_SEMAPHORE usb_cdc_tx_completion;
static TX_THREAD usb_cdc_tx_thread;
static TX_THREAD usb_cdc_rx_thread;

static ULONG usb_cdc_tx_queue_storage[USB_CDC_TX_QUEUE_DEPTH];
static ULONG usb_cdc_rx_ingress_storage[USB_CDC_RX_SLOT_COUNT];
static ULONG usb_cdc_rx_delivery_storage[USB_CDC_RX_SLOT_COUNT];
static ULONG usb_cdc_tx_stack[USB_CDC_TX_STACK_SIZE / sizeof(ULONG)];
static ULONG usb_cdc_rx_stack[USB_CDC_RX_STACK_SIZE / sizeof(ULONG)];

static UCHAR usb_cdc_control_storage[USB_CDC_TX_CONTROL_SLOT_COUNT]
                                     [USB_CDC_TX_CONTROL_SLOT_SIZE];
static UCHAR usb_cdc_map_storage[USB_CDC_TX_MAP_SLOT_COUNT]
                                 [USB_CDC_TX_MAP_SLOT_SIZE]
                                 __attribute__((aligned(32)));
static USB_CDC_TxSlot_t usb_cdc_tx_slots[USB_CDC_TX_QUEUE_DEPTH];
static USB_CDC_RxSlot_t usb_cdc_rx_slots[USB_CDC_RX_SLOT_COUNT]
                                       __attribute__((aligned(32)));

static UINT usb_cdc_initialized;
static UINT usb_cdc_active;
static ULONG usb_cdc_session;
static UX_SLAVE_CLASS_CDC_ACM *usb_cdc_instance;
static USB_CDC_RxSlot_t *usb_cdc_rx_consumer_slot;
static ULONG usb_cdc_rx_consumer_offset;

static USB_CDC_TxSlot_t *volatile usb_cdc_inflight_slot;
static volatile ULONG usb_cdc_submit_sequence;
static volatile ULONG usb_cdc_completion_sequence;
static volatile UINT usb_cdc_completion_status;
static volatile ULONG usb_cdc_completion_length;

static ULONG usb_cdc_tx_packets_queued;
static ULONG usb_cdc_tx_packets_completed;
static ULONG usb_cdc_tx_bytes_completed;
static ULONG usb_cdc_tx_packets_dropped;
static ULONG usb_cdc_tx_slot_exhaustions;
static ULONG usb_cdc_tx_callback_completions;
static ULONG usb_cdc_tx_errors;
static ULONG usb_cdc_tx_last_error;
static ULONG usb_cdc_rx_packets_received;
static ULONG usb_cdc_rx_packets_delivered;
static ULONG usb_cdc_rx_bytes_received;
static ULONG usb_cdc_rx_packets_dropped;
static ULONG usb_cdc_rx_slot_exhaustions;
static ULONG usb_cdc_rx_errors;
static ULONG usb_cdc_rx_last_error;

static void usb_cdc_tx_thread_entry(ULONG thread_input);
static void usb_cdc_rx_thread_entry(ULONG thread_input);
static UINT usb_cdc_write_callback(UX_SLAVE_CLASS_CDC_ACM *cdc_acm,
                                   UINT status, ULONG length);
static UINT usb_cdc_read_callback(UX_SLAVE_CLASS_CDC_ACM *cdc_acm,
                                  UINT status, UCHAR *data, ULONG length);
static UINT usb_cdc_snapshot(UX_SLAVE_CLASS_CDC_ACM **instance,
                             ULONG *session);
static UINT usb_cdc_tx_slot_acquire(USB_CDC_TxKind_t kind,
                                    ULONG wait_option,
                                    USB_CDC_TxSlot_t **slot);
static UINT usb_cdc_tx_slot_commit(USB_CDC_TxSlot_t *slot, ULONG length,
                                   ULONG wait_option);
static void usb_cdc_tx_slot_release(USB_CDC_TxSlot_t *slot);
static UINT usb_cdc_tx_slot_is_current(const USB_CDC_TxSlot_t *slot);
static UINT usb_cdc_rx_slot_acquire(ULONG session, USB_CDC_RxSlot_t **slot);
static void usb_cdc_rx_slot_release(USB_CDC_RxSlot_t *slot);
static UINT usb_cdc_rx_slot_is_current(const USB_CDC_RxSlot_t *slot);
static void usb_cdc_flush_tx_queue(void);
static void usb_cdc_flush_rx_queue(TX_QUEUE *queue);
static void usb_cdc_release_consumer_slot(void);
static void usb_cdc_signal_tx_completion(UINT status, ULONG length);
static void usb_cdc_counter_add(ULONG *counter, ULONG value);
static void usb_cdc_set_last_error(ULONG *counter, ULONG *last_error,
                                   UINT status);

UINT USB_CDC_Transport_Init(void)
{
  UINT index;

  if (usb_cdc_initialized != 0U)
  {
    return TX_SUCCESS;
  }

  for (index = 0U; index < USB_CDC_TX_CONTROL_SLOT_COUNT; ++index)
  {
    usb_cdc_tx_slots[index].data = usb_cdc_control_storage[index];
    usb_cdc_tx_slots[index].capacity = USB_CDC_TX_CONTROL_SLOT_SIZE;
    usb_cdc_tx_slots[index].kind = USB_CDC_TX_CONTROL;
    usb_cdc_tx_slots[index].state = USB_CDC_SLOT_FREE;
  }
  for (index = 0U; index < USB_CDC_TX_MAP_SLOT_COUNT; ++index)
  {
    USB_CDC_TxSlot_t *slot =
        &usb_cdc_tx_slots[USB_CDC_TX_CONTROL_SLOT_COUNT + index];
    slot->data = usb_cdc_map_storage[index];
    slot->capacity = USB_CDC_TX_MAP_SLOT_SIZE;
    slot->kind = USB_CDC_TX_MAP;
    slot->state = USB_CDC_SLOT_FREE;
  }
  for (index = 0U; index < USB_CDC_RX_SLOT_COUNT; ++index)
  {
    usb_cdc_rx_slots[index].state = USB_CDC_SLOT_FREE;
  }

  if ((tx_queue_create(&usb_cdc_tx_queue, "USB CDC TX slot queue",
                       TX_1_ULONG, usb_cdc_tx_queue_storage,
                       sizeof(usb_cdc_tx_queue_storage)) != TX_SUCCESS) ||
      (tx_queue_create(&usb_cdc_rx_ingress_queue,
                       "USB CDC RX callback queue", TX_1_ULONG,
                       usb_cdc_rx_ingress_storage,
                       sizeof(usb_cdc_rx_ingress_storage)) != TX_SUCCESS) ||
      (tx_queue_create(&usb_cdc_rx_delivery_queue,
                       "USB CDC RX delivery queue", TX_1_ULONG,
                       usb_cdc_rx_delivery_storage,
                       sizeof(usb_cdc_rx_delivery_storage)) != TX_SUCCESS))
  {
    return TX_QUEUE_ERROR;
  }

  if (tx_event_flags_create(&usb_cdc_worker_flags,
                            "USB CDC worker state") != TX_SUCCESS)
  {
    return TX_GROUP_ERROR;
  }

  if ((tx_mutex_create(&usb_cdc_state_mutex, "USB CDC state",
                       TX_INHERIT) != TX_SUCCESS) ||
      (tx_mutex_create(&usb_cdc_io_mutex, "USB CDC submit/stop",
                       TX_INHERIT) != TX_SUCCESS) ||
      (tx_mutex_create(&usb_cdc_rx_consumer_mutex,
                       "USB CDC RX consumer", TX_INHERIT) != TX_SUCCESS))
  {
    return TX_MUTEX_ERROR;
  }

  if ((tx_semaphore_create(&usb_cdc_control_free,
                           "USB CDC control slots",
                           USB_CDC_TX_CONTROL_SLOT_COUNT) != TX_SUCCESS) ||
      (tx_semaphore_create(&usb_cdc_map_free, "USB CDC map slots",
                           USB_CDC_TX_MAP_SLOT_COUNT) != TX_SUCCESS) ||
      (tx_semaphore_create(&usb_cdc_rx_free, "USB CDC RX slots",
                           USB_CDC_RX_SLOT_COUNT) != TX_SUCCESS) ||
      (tx_semaphore_create(&usb_cdc_tx_completion,
                           "USB CDC TX callback", 0U) != TX_SUCCESS))
  {
    return TX_SEMAPHORE_ERROR;
  }

  if (tx_thread_create(&usb_cdc_rx_thread, "USB CDC RX worker",
                       usb_cdc_rx_thread_entry, 0U,
                       usb_cdc_rx_stack, sizeof(usb_cdc_rx_stack),
                       USB_CDC_WORKER_PRIORITY, USB_CDC_WORKER_PRIORITY,
                       TX_NO_TIME_SLICE, TX_AUTO_START) != TX_SUCCESS)
  {
    return TX_THREAD_ERROR;
  }

  if (tx_thread_create(&usb_cdc_tx_thread, "USB CDC TX scheduler",
                       usb_cdc_tx_thread_entry, 0U,
                       usb_cdc_tx_stack, sizeof(usb_cdc_tx_stack),
                       USB_CDC_WORKER_PRIORITY, USB_CDC_WORKER_PRIORITY,
                       TX_NO_TIME_SLICE, TX_AUTO_START) != TX_SUCCESS)
  {
    return TX_THREAD_ERROR;
  }

  usb_cdc_session = 1U;
  usb_cdc_initialized = 1U;
  Debug_UART_Log("CDC", "static transport ready: 8x768 control, 2x48KiB map, 16x512 RX");
  return TX_SUCCESS;
}

UINT USB_CDC_Transport_Start(UX_SLAVE_CLASS_CDC_ACM *instance)
{
  UINT status;

  if ((usb_cdc_initialized == 0U) || (instance == UX_NULL))
  {
    return TX_PTR_ERROR;
  }

  usb_cdc_flush_tx_queue();
  usb_cdc_flush_rx_queue(&usb_cdc_rx_ingress_queue);
  usb_cdc_flush_rx_queue(&usb_cdc_rx_delivery_queue);
  usb_cdc_release_consumer_slot();

  if (tx_mutex_get(&usb_cdc_state_mutex, TX_WAIT_FOREVER) != TX_SUCCESS)
  {
    return TX_MUTEX_ERROR;
  }
  ++usb_cdc_session;
  usb_cdc_instance = instance;
  usb_cdc_active = 1U;
  (void)tx_mutex_put(&usb_cdc_state_mutex);

  (void)tx_event_flags_set(&usb_cdc_worker_flags,
                           ~USB_CDC_FLAG_WORKERS_IDLE, TX_AND);
  (void)tx_event_flags_set(&usb_cdc_worker_flags, USB_CDC_FLAG_ACTIVE,
                           TX_OR);

  status = USB_CDC_LL_StartCallbacks(instance, usb_cdc_write_callback,
                                     usb_cdc_read_callback);
  if (status != UX_SUCCESS)
  {
    USB_CDC_Transport_BeginStop();
    return status;
  }

  Debug_UART_Log("CDC", "callback RX/TX data plane started (session=%lu)",
                 (unsigned long)usb_cdc_session);
  return TX_SUCCESS;
}

void USB_CDC_Transport_BeginStop(void)
{
  UX_SLAVE_CLASS_CDC_ACM *instance = UX_NULL;
  ULONG wake_message = 0U;

  if (usb_cdc_initialized == 0U)
  {
    return;
  }

  if (tx_mutex_get(&usb_cdc_state_mutex, TX_WAIT_FOREVER) == TX_SUCCESS)
  {
    instance = usb_cdc_instance;
    usb_cdc_active = 0U;
    usb_cdc_instance = UX_NULL;
    ++usb_cdc_session;
    (void)tx_mutex_put(&usb_cdc_state_mutex);
  }

  (void)tx_event_flags_set(&usb_cdc_worker_flags,
                           ~USB_CDC_FLAG_ACTIVE, TX_AND);

  if (tx_mutex_get(&usb_cdc_io_mutex, TX_WAIT_FOREVER) == TX_SUCCESS)
  {
    if (instance != UX_NULL)
    {
      /* This is also safe after USBX class deactivation: in that case USBX
       * already stopped both callback threads and returns UX_ERROR here. */
      (void)USB_CDC_LL_StopCallbacks(instance);
    }
    usb_cdc_signal_tx_completion(UX_ABORTED, 0U);
    (void)tx_mutex_put(&usb_cdc_io_mutex);
  }

  usb_cdc_flush_tx_queue();
  usb_cdc_flush_rx_queue(&usb_cdc_rx_ingress_queue);
  usb_cdc_flush_rx_queue(&usb_cdc_rx_delivery_queue);
  usb_cdc_release_consumer_slot();

  (void)tx_queue_send(&usb_cdc_tx_queue, &wake_message, TX_NO_WAIT);
  (void)tx_queue_send(&usb_cdc_rx_ingress_queue, &wake_message, TX_NO_WAIT);
}

UINT USB_CDC_Transport_WaitStopped(ULONG wait_option)
{
  ULONG actual_flags = 0U;
  UINT status;

  if (usb_cdc_initialized == 0U)
  {
    return TX_SUCCESS;
  }

  status = tx_event_flags_get(&usb_cdc_worker_flags,
                              USB_CDC_FLAG_WORKERS_IDLE, TX_AND,
                              &actual_flags, wait_option);
  usb_cdc_flush_tx_queue();
  usb_cdc_flush_rx_queue(&usb_cdc_rx_ingress_queue);
  usb_cdc_flush_rx_queue(&usb_cdc_rx_delivery_queue);
  usb_cdc_release_consumer_slot();
  return status;
}

UINT USB_CDC_Transport_IsReady(void)
{
  UX_SLAVE_CLASS_CDC_ACM *instance = UX_NULL;
  ULONG session = 0U;

  if (usb_cdc_snapshot(&instance, &session) == 0U)
  {
    return UX_FALSE;
  }
  (void)session;
  return USB_CDC_LL_IsConfigured(instance);
}

UINT USB_CDC_Transport_Send(const void *buffer, ULONG length,
                            ULONG wait_option)
{
  const UCHAR *source = (const UCHAR *)buffer;
  ULONG remaining = length;

  if ((buffer == UX_NULL) || (length == 0U))
  {
    return UX_INVALID_PARAMETER;
  }

  while (remaining != 0U)
  {
    USB_CDC_TxSlot_t *slot = UX_NULL;
    ULONG chunk = (remaining < USB_CDC_TX_CONTROL_SLOT_SIZE) ?
                  remaining : USB_CDC_TX_CONTROL_SLOT_SIZE;
    UINT status = usb_cdc_tx_slot_acquire(USB_CDC_TX_CONTROL,
                                          wait_option, &slot);
    if (status != TX_SUCCESS)
    {
      usb_cdc_counter_add(&usb_cdc_tx_slot_exhaustions, 1U);
      usb_cdc_counter_add(&usb_cdc_tx_packets_dropped, 1U);
      return status;
    }

    (void)memcpy(slot->data, source, (size_t)chunk);
    status = usb_cdc_tx_slot_commit(slot, chunk, wait_option);
    if (status != TX_SUCCESS)
    {
      usb_cdc_counter_add(&usb_cdc_tx_packets_dropped, 1U);
      return status;
    }
    source += chunk;
    remaining -= chunk;
  }
  return TX_SUCCESS;
}

UINT USB_CDC_Transport_AcquireMapBuffer(USB_CDC_TxBuffer_t *buffer)
{
  USB_CDC_TxSlot_t *slot = UX_NULL;
  UINT status;

  if (buffer == UX_NULL)
  {
    return TX_PTR_ERROR;
  }
  buffer->data = UX_NULL;
  buffer->capacity = 0U;
  buffer->handle = UX_NULL;

  status = usb_cdc_tx_slot_acquire(USB_CDC_TX_MAP, TX_NO_WAIT, &slot);
  if (status != TX_SUCCESS)
  {
    usb_cdc_counter_add(&usb_cdc_tx_slot_exhaustions, 1U);
    return status;
  }

  buffer->data = slot->data;
  buffer->capacity = slot->capacity;
  buffer->handle = slot;
  return TX_SUCCESS;
}

UINT USB_CDC_Transport_CommitMapBuffer(USB_CDC_TxBuffer_t *buffer,
                                       ULONG length)
{
  USB_CDC_TxSlot_t *slot;
  UINT status;

  if ((buffer == UX_NULL) || (buffer->handle == UX_NULL))
  {
    return TX_PTR_ERROR;
  }
  slot = (USB_CDC_TxSlot_t *)buffer->handle;
  if ((slot->kind != USB_CDC_TX_MAP) || (slot->data != buffer->data) ||
      (length == 0U) || (length > slot->capacity))
  {
    usb_cdc_tx_slot_release(slot);
    return UX_INVALID_PARAMETER;
  }

  status = usb_cdc_tx_slot_commit(slot, length, TX_NO_WAIT);
  if (status != TX_SUCCESS)
  {
    usb_cdc_counter_add(&usb_cdc_tx_packets_dropped, 1U);
  }
  buffer->data = UX_NULL;
  buffer->capacity = 0U;
  buffer->handle = UX_NULL;
  return status;
}

void USB_CDC_Transport_CancelMapBuffer(USB_CDC_TxBuffer_t *buffer)
{
  USB_CDC_TxSlot_t *slot;

  if ((buffer == UX_NULL) || (buffer->handle == UX_NULL))
  {
    return;
  }
  slot = (USB_CDC_TxSlot_t *)buffer->handle;
  if ((slot->kind == USB_CDC_TX_MAP) && (slot->data == buffer->data))
  {
    usb_cdc_tx_slot_release(slot);
  }
  buffer->data = UX_NULL;
  buffer->capacity = 0U;
  buffer->handle = UX_NULL;
}

UINT USB_CDC_Transport_Receive(void *buffer, ULONG requested_length,
                               ULONG *actual_length, ULONG wait_option)
{
  ULONG queue_message = 0U;
  ULONG available;
  ULONG copy_length;
  UINT status;

  if (actual_length != UX_NULL)
  {
    *actual_length = 0U;
  }
  if ((buffer == UX_NULL) || (actual_length == UX_NULL) ||
      (requested_length == 0U))
  {
    return UX_INVALID_PARAMETER;
  }
  if (usb_cdc_initialized == 0U)
  {
    return UX_ERROR;
  }

  status = tx_mutex_get(&usb_cdc_rx_consumer_mutex, wait_option);
  if (status != TX_SUCCESS)
  {
    return status;
  }

  for (;;)
  {
    if (usb_cdc_rx_consumer_slot == UX_NULL)
    {
      status = tx_queue_receive(&usb_cdc_rx_delivery_queue, &queue_message,
                                wait_option);
      if (status != TX_SUCCESS)
      {
        (void)tx_mutex_put(&usb_cdc_rx_consumer_mutex);
        return status;
      }
      usb_cdc_rx_consumer_slot =
          (USB_CDC_RxSlot_t *)(uintptr_t)queue_message;
      usb_cdc_rx_consumer_offset = 0U;
    }

    if (usb_cdc_rx_slot_is_current(usb_cdc_rx_consumer_slot) == 0U)
    {
      usb_cdc_rx_slot_release(usb_cdc_rx_consumer_slot);
      usb_cdc_rx_consumer_slot = UX_NULL;
      usb_cdc_rx_consumer_offset = 0U;
      wait_option = TX_NO_WAIT;
      continue;
    }
    break;
  }

  available = usb_cdc_rx_consumer_slot->length - usb_cdc_rx_consumer_offset;
  copy_length = (available < requested_length) ? available : requested_length;
  (void)memcpy(buffer,
               &usb_cdc_rx_consumer_slot->data[usb_cdc_rx_consumer_offset],
               (size_t)copy_length);
  usb_cdc_rx_consumer_offset += copy_length;
  *actual_length = copy_length;

  if (usb_cdc_rx_consumer_offset >= usb_cdc_rx_consumer_slot->length)
  {
    usb_cdc_rx_slot_release(usb_cdc_rx_consumer_slot);
    usb_cdc_rx_consumer_slot = UX_NULL;
    usb_cdc_rx_consumer_offset = 0U;
    usb_cdc_counter_add(&usb_cdc_rx_packets_delivered, 1U);
  }

  (void)tx_mutex_put(&usb_cdc_rx_consumer_mutex);
  return TX_SUCCESS;
}

void USB_CDC_Transport_GetStatus(USB_CDC_TransportStatus_t *status)
{
  CHAR *name;
  ULONG count = 0U;
  ULONG enqueued = 0U;
  ULONG ingress = 0U;

  if (status == UX_NULL)
  {
    return;
  }
  (void)memset(status, 0, sizeof(*status));
  status->initialized = usb_cdc_initialized;
  if (usb_cdc_initialized == 0U)
  {
    return;
  }

  if (tx_mutex_get(&usb_cdc_state_mutex, TX_WAIT_FOREVER) == TX_SUCCESS)
  {
    status->active = usb_cdc_active;
    status->session = usb_cdc_session;
    (void)tx_mutex_put(&usb_cdc_state_mutex);
  }

  (void)tx_semaphore_info_get(&usb_cdc_control_free, &name, &count,
                              UX_NULL, UX_NULL, UX_NULL);
  status->tx_control_slots_free = count;
  (void)tx_semaphore_info_get(&usb_cdc_map_free, &name, &count,
                              UX_NULL, UX_NULL, UX_NULL);
  status->tx_map_slots_free = count;
  (void)tx_semaphore_info_get(&usb_cdc_rx_free, &name, &count,
                              UX_NULL, UX_NULL, UX_NULL);
  status->rx_slots_free = count;

  (void)tx_queue_info_get(&usb_cdc_tx_queue, &name, &enqueued, UX_NULL,
                          UX_NULL, UX_NULL, UX_NULL);
  status->tx_queue_depth = enqueued;
  (void)tx_queue_info_get(&usb_cdc_rx_ingress_queue, &name, &ingress,
                          UX_NULL, UX_NULL, UX_NULL, UX_NULL);
  (void)tx_queue_info_get(&usb_cdc_rx_delivery_queue, &name, &enqueued,
                          UX_NULL, UX_NULL, UX_NULL, UX_NULL);
  status->rx_queue_depth = ingress + enqueued;

  TX_INTERRUPT_SAVE_AREA
  TX_DISABLE
  status->tx_in_flight = (usb_cdc_inflight_slot != UX_NULL) ? 1U : 0U;
  status->tx_packets_queued = usb_cdc_tx_packets_queued;
  status->tx_packets_completed = usb_cdc_tx_packets_completed;
  status->tx_bytes_completed = usb_cdc_tx_bytes_completed;
  status->tx_packets_dropped = usb_cdc_tx_packets_dropped;
  status->tx_slot_exhaustions = usb_cdc_tx_slot_exhaustions;
  status->tx_callback_completions = usb_cdc_tx_callback_completions;
  status->tx_errors = usb_cdc_tx_errors;
  status->tx_last_error = usb_cdc_tx_last_error;
  status->rx_packets_received = usb_cdc_rx_packets_received;
  status->rx_packets_delivered = usb_cdc_rx_packets_delivered;
  status->rx_bytes_received = usb_cdc_rx_bytes_received;
  status->rx_packets_dropped = usb_cdc_rx_packets_dropped;
  status->rx_slot_exhaustions = usb_cdc_rx_slot_exhaustions;
  status->rx_errors = usb_cdc_rx_errors;
  status->rx_last_error = usb_cdc_rx_last_error;
  TX_RESTORE
}

static void usb_cdc_tx_thread_entry(ULONG thread_input)
{
  ULONG queue_message;
  ULONG actual_flags;
  ULONG expected_sequence;
  ULONG completed_length;
  ULONG sent_length;
  UINT completion_status;
  UINT transfer_status;
  UINT attempt;
  UX_SLAVE_CLASS_CDC_ACM *instance;
  USB_CDC_TxSlot_t *slot;

  (void)thread_input;
  Debug_UART_Log("CDC", "USB TX callback scheduler started");

  for (;;)
  {
    (void)tx_event_flags_set(&usb_cdc_worker_flags,
                             USB_CDC_FLAG_TX_IDLE, TX_OR);
    (void)tx_event_flags_get(&usb_cdc_worker_flags, USB_CDC_FLAG_ACTIVE,
                             TX_AND, &actual_flags, TX_WAIT_FOREVER);
    (void)tx_event_flags_set(&usb_cdc_worker_flags,
                             ~USB_CDC_FLAG_TX_IDLE, TX_AND);

    if (tx_queue_receive(&usb_cdc_tx_queue, &queue_message,
                         TX_WAIT_FOREVER) != TX_SUCCESS)
    {
      continue;
    }
    if (queue_message == 0U)
    {
      continue;
    }

    slot = (USB_CDC_TxSlot_t *)(uintptr_t)queue_message;
    if ((slot == UX_NULL) || (usb_cdc_tx_slot_is_current(slot) == 0U) ||
        (usb_cdc_snapshot(&instance, &actual_flags) == 0U))
    {
      usb_cdc_tx_slot_release(slot);
      usb_cdc_counter_add(&usb_cdc_tx_packets_dropped, 1U);
      continue;
    }

    sent_length = 0U;
    attempt = 0U;
    transfer_status = UX_ERROR;
    while ((sent_length < slot->length) &&
           (usb_cdc_tx_slot_is_current(slot) != 0U) &&
           (attempt < USB_CDC_MAX_TX_ATTEMPTS))
    {
      while (tx_semaphore_get(&usb_cdc_tx_completion,
                              TX_NO_WAIT) == TX_SUCCESS)
      {
      }

      if (tx_mutex_get(&usb_cdc_io_mutex, TX_WAIT_FOREVER) != TX_SUCCESS)
      {
        transfer_status = TX_MUTEX_ERROR;
        break;
      }

      if ((usb_cdc_snapshot(&instance, &actual_flags) == 0U) ||
          (slot->session != actual_flags))
      {
        (void)tx_mutex_put(&usb_cdc_io_mutex);
        transfer_status = UX_ABORTED;
        break;
      }

      TX_INTERRUPT_SAVE_AREA
      TX_DISABLE
      slot->state = USB_CDC_SLOT_IN_FLIGHT;
      usb_cdc_inflight_slot = slot;
      expected_sequence = ++usb_cdc_submit_sequence;
      usb_cdc_completion_sequence = 0U;
      TX_RESTORE

      transfer_status = USB_CDC_LL_WriteAsync(
          instance, &slot->data[sent_length], slot->length - sent_length);
      (void)tx_mutex_put(&usb_cdc_io_mutex);

      if (transfer_status != UX_SUCCESS)
      {
        usb_cdc_signal_tx_completion(transfer_status, 0U);
      }

      do
      {
        (void)tx_semaphore_get(&usb_cdc_tx_completion, TX_WAIT_FOREVER);
        TX_DISABLE
        completion_status = usb_cdc_completion_status;
        completed_length = usb_cdc_completion_length;
        actual_flags = usb_cdc_completion_sequence;
        TX_RESTORE
      } while (actual_flags != expected_sequence);

      transfer_status = completion_status;
      if (completed_length > (slot->length - sent_length))
      {
        transfer_status = UX_TRANSFER_ERROR;
        completed_length = 0U;
      }
      sent_length += completed_length;

      if ((transfer_status == UX_SUCCESS) &&
          (sent_length < slot->length) && (completed_length != 0U))
      {
        attempt = 0U;
      }
      else if (sent_length < slot->length)
      {
        ++attempt;
        if (usb_cdc_tx_slot_is_current(slot) != 0U)
        {
          tx_thread_sleep(USB_CDC_ERROR_BACKOFF_TICKS);
        }
      }
    }

    TX_INTERRUPT_SAVE_AREA
    TX_DISABLE
    usb_cdc_inflight_slot = UX_NULL;
    TX_RESTORE

    if ((sent_length == slot->length) &&
        (transfer_status == UX_SUCCESS))
    {
      usb_cdc_counter_add(&usb_cdc_tx_packets_completed, 1U);
      usb_cdc_counter_add(&usb_cdc_tx_bytes_completed, sent_length);
    }
    else if (usb_cdc_tx_slot_is_current(slot) != 0U)
    {
      if (transfer_status == UX_SUCCESS)
      {
        transfer_status = UX_TRANSFER_ERROR;
      }
      usb_cdc_set_last_error(&usb_cdc_tx_errors,
                             &usb_cdc_tx_last_error, transfer_status);
      (void)App_USBX_Device_ReportTxError(transfer_status);
    }
    usb_cdc_tx_slot_release(slot);
  }
}

static void usb_cdc_rx_thread_entry(ULONG thread_input)
{
  ULONG queue_message;
  ULONG actual_flags;
  USB_CDC_RxSlot_t *slot;

  (void)thread_input;
  Debug_UART_Log("CDC", "USB RX callback dispatcher started");

  for (;;)
  {
    (void)tx_event_flags_set(&usb_cdc_worker_flags,
                             USB_CDC_FLAG_RX_IDLE, TX_OR);
    (void)tx_event_flags_get(&usb_cdc_worker_flags, USB_CDC_FLAG_ACTIVE,
                             TX_AND, &actual_flags, TX_WAIT_FOREVER);
    (void)tx_event_flags_set(&usb_cdc_worker_flags,
                             ~USB_CDC_FLAG_RX_IDLE, TX_AND);

    if (tx_queue_receive(&usb_cdc_rx_ingress_queue, &queue_message,
                         TX_WAIT_FOREVER) != TX_SUCCESS)
    {
      continue;
    }
    if (queue_message == 0U)
    {
      continue;
    }

    slot = (USB_CDC_RxSlot_t *)(uintptr_t)queue_message;
    if ((slot == UX_NULL) || (usb_cdc_rx_slot_is_current(slot) == 0U))
    {
      usb_cdc_rx_slot_release(slot);
      usb_cdc_counter_add(&usb_cdc_rx_packets_dropped, 1U);
      continue;
    }

    slot->state = USB_CDC_SLOT_DELIVERY;
    if (tx_queue_send(&usb_cdc_rx_delivery_queue, &queue_message,
                      TX_NO_WAIT) != TX_SUCCESS)
    {
      usb_cdc_rx_slot_release(slot);
      usb_cdc_counter_add(&usb_cdc_rx_packets_dropped, 1U);
    }
  }
}

static UINT usb_cdc_write_callback(UX_SLAVE_CLASS_CDC_ACM *cdc_acm,
                                   UINT status, ULONG length)
{
  (void)cdc_acm;
  usb_cdc_counter_add(&usb_cdc_tx_callback_completions, 1U);
  usb_cdc_signal_tx_completion(status, length);
  return UX_SUCCESS;
}

static UINT usb_cdc_read_callback(UX_SLAVE_CLASS_CDC_ACM *cdc_acm,
                                  UINT status, UCHAR *data, ULONG length)
{
  UX_SLAVE_CLASS_CDC_ACM *instance = UX_NULL;
  USB_CDC_RxSlot_t *slot = UX_NULL;
  ULONG queue_message;
  ULONG session = 0U;

  (void)cdc_acm;
  if (status != UX_SUCCESS)
  {
    usb_cdc_set_last_error(&usb_cdc_rx_errors,
                           &usb_cdc_rx_last_error, status);
    (void)App_USBX_Device_ReportRxError(status);
    return UX_SUCCESS;
  }
  if ((data == UX_NULL) || (length == 0U))
  {
    return UX_SUCCESS;
  }
  if ((length > USB_CDC_RX_SLOT_SIZE) ||
      (usb_cdc_snapshot(&instance, &session) == 0U))
  {
    usb_cdc_counter_add(&usb_cdc_rx_packets_dropped, 1U);
    return UX_SUCCESS;
  }
  (void)instance;

  if (usb_cdc_rx_slot_acquire(session, &slot) != TX_SUCCESS)
  {
    usb_cdc_counter_add(&usb_cdc_rx_slot_exhaustions, 1U);
    usb_cdc_counter_add(&usb_cdc_rx_packets_dropped, 1U);
    return UX_SUCCESS;
  }

  (void)memcpy(slot->data, data, (size_t)length);
  slot->length = length;
  slot->state = USB_CDC_SLOT_QUEUED;
  queue_message = (ULONG)(uintptr_t)slot;
  if (tx_queue_send(&usb_cdc_rx_ingress_queue, &queue_message,
                    TX_NO_WAIT) != TX_SUCCESS)
  {
    usb_cdc_rx_slot_release(slot);
    usb_cdc_counter_add(&usb_cdc_rx_packets_dropped, 1U);
    return UX_SUCCESS;
  }

  usb_cdc_counter_add(&usb_cdc_rx_packets_received, 1U);
  usb_cdc_counter_add(&usb_cdc_rx_bytes_received, length);
  return UX_SUCCESS;
}

static UINT usb_cdc_snapshot(UX_SLAVE_CLASS_CDC_ACM **instance,
                             ULONG *session)
{
  UINT active = 0U;

  if ((usb_cdc_initialized == 0U) || (instance == UX_NULL) ||
      (session == UX_NULL))
  {
    return 0U;
  }

  if (tx_mutex_get(&usb_cdc_state_mutex, TX_WAIT_FOREVER) == TX_SUCCESS)
  {
    if ((usb_cdc_active != 0U) && (usb_cdc_instance != UX_NULL))
    {
      *instance = usb_cdc_instance;
      *session = usb_cdc_session;
      active = 1U;
    }
    (void)tx_mutex_put(&usb_cdc_state_mutex);
  }
  return active;
}

static UINT usb_cdc_tx_slot_acquire(USB_CDC_TxKind_t kind,
                                    ULONG wait_option,
                                    USB_CDC_TxSlot_t **slot)
{
  TX_SEMAPHORE *semaphore = (kind == USB_CDC_TX_MAP) ?
                            &usb_cdc_map_free : &usb_cdc_control_free;
  UX_SLAVE_CLASS_CDC_ACM *instance = UX_NULL;
  ULONG session = 0U;
  UINT index;

  if (slot == UX_NULL)
  {
    return UX_ERROR;
  }
  *slot = UX_NULL;
  if (usb_cdc_snapshot(&instance, &session) == 0U)
  {
    return UX_ERROR;
  }
  (void)instance;

  if (tx_semaphore_get(semaphore, wait_option) != TX_SUCCESS)
  {
    return TX_NO_INSTANCE;
  }

  TX_INTERRUPT_SAVE_AREA
  TX_DISABLE
  for (index = 0U; index < USB_CDC_TX_QUEUE_DEPTH; ++index)
  {
    if ((usb_cdc_tx_slots[index].kind == kind) &&
        (usb_cdc_tx_slots[index].state == USB_CDC_SLOT_FREE))
    {
      usb_cdc_tx_slots[index].state = USB_CDC_SLOT_RESERVED;
      usb_cdc_tx_slots[index].session = session;
      usb_cdc_tx_slots[index].length = 0U;
      *slot = &usb_cdc_tx_slots[index];
      break;
    }
  }
  TX_RESTORE

  if (*slot == UX_NULL)
  {
    (void)tx_semaphore_put(semaphore);
    return TX_NO_INSTANCE;
  }
  if (usb_cdc_tx_slot_is_current(*slot) == 0U)
  {
    usb_cdc_tx_slot_release(*slot);
    *slot = UX_NULL;
    return UX_ERROR;
  }
  return TX_SUCCESS;
}

static UINT usb_cdc_tx_slot_commit(USB_CDC_TxSlot_t *slot, ULONG length,
                                   ULONG wait_option)
{
  ULONG queue_message;
  UINT valid = 0U;
  UINT status;

  if ((slot == UX_NULL) || (length == 0U) || (length > slot->capacity) ||
      (usb_cdc_tx_slot_is_current(slot) == 0U))
  {
    usb_cdc_tx_slot_release(slot);
    return UX_INVALID_PARAMETER;
  }

  TX_INTERRUPT_SAVE_AREA
  TX_DISABLE
  if (slot->state == USB_CDC_SLOT_RESERVED)
  {
    slot->length = length;
    slot->state = USB_CDC_SLOT_QUEUED;
    valid = 1U;
  }
  TX_RESTORE
  if (valid == 0U)
  {
    usb_cdc_tx_slot_release(slot);
    return UX_ERROR;
  }

  queue_message = (ULONG)(uintptr_t)slot;
  status = tx_queue_send(&usb_cdc_tx_queue, &queue_message, wait_option);
  if (status != TX_SUCCESS)
  {
    usb_cdc_tx_slot_release(slot);
    return status;
  }
  usb_cdc_counter_add(&usb_cdc_tx_packets_queued, 1U);
  return TX_SUCCESS;
}

static void usb_cdc_tx_slot_release(USB_CDC_TxSlot_t *slot)
{
  UINT release = 0U;
  USB_CDC_TxKind_t kind = USB_CDC_TX_CONTROL;

  if (slot == UX_NULL)
  {
    return;
  }

  TX_INTERRUPT_SAVE_AREA
  TX_DISABLE
  if (slot->state != USB_CDC_SLOT_FREE)
  {
    kind = slot->kind;
    slot->state = USB_CDC_SLOT_FREE;
    slot->length = 0U;
    slot->session = 0U;
    release = 1U;
  }
  TX_RESTORE

  if (release != 0U)
  {
    (void)tx_semaphore_put((kind == USB_CDC_TX_MAP) ?
                           &usb_cdc_map_free : &usb_cdc_control_free);
  }
}

static UINT usb_cdc_tx_slot_is_current(const USB_CDC_TxSlot_t *slot)
{
  UX_SLAVE_CLASS_CDC_ACM *instance = UX_NULL;
  ULONG session = 0U;

  if ((slot == UX_NULL) ||
      (usb_cdc_snapshot(&instance, &session) == 0U))
  {
    return 0U;
  }
  (void)instance;
  return (slot->session == session) ? 1U : 0U;
}

static UINT usb_cdc_rx_slot_acquire(ULONG session, USB_CDC_RxSlot_t **slot)
{
  UINT index;

  if ((slot == UX_NULL) ||
      (tx_semaphore_get(&usb_cdc_rx_free, TX_NO_WAIT) != TX_SUCCESS))
  {
    return TX_NO_INSTANCE;
  }
  *slot = UX_NULL;

  TX_INTERRUPT_SAVE_AREA
  TX_DISABLE
  for (index = 0U; index < USB_CDC_RX_SLOT_COUNT; ++index)
  {
    if (usb_cdc_rx_slots[index].state == USB_CDC_SLOT_FREE)
    {
      usb_cdc_rx_slots[index].state = USB_CDC_SLOT_RESERVED;
      usb_cdc_rx_slots[index].session = session;
      usb_cdc_rx_slots[index].length = 0U;
      *slot = &usb_cdc_rx_slots[index];
      break;
    }
  }
  TX_RESTORE

  if (*slot == UX_NULL)
  {
    (void)tx_semaphore_put(&usb_cdc_rx_free);
    return TX_NO_INSTANCE;
  }
  return TX_SUCCESS;
}

static void usb_cdc_rx_slot_release(USB_CDC_RxSlot_t *slot)
{
  UINT release = 0U;

  if (slot == UX_NULL)
  {
    return;
  }
  TX_INTERRUPT_SAVE_AREA
  TX_DISABLE
  if (slot->state != USB_CDC_SLOT_FREE)
  {
    slot->state = USB_CDC_SLOT_FREE;
    slot->length = 0U;
    slot->session = 0U;
    release = 1U;
  }
  TX_RESTORE
  if (release != 0U)
  {
    (void)tx_semaphore_put(&usb_cdc_rx_free);
  }
}

static UINT usb_cdc_rx_slot_is_current(const USB_CDC_RxSlot_t *slot)
{
  UX_SLAVE_CLASS_CDC_ACM *instance = UX_NULL;
  ULONG session = 0U;

  if ((slot == UX_NULL) ||
      (usb_cdc_snapshot(&instance, &session) == 0U))
  {
    return 0U;
  }
  (void)instance;
  return (slot->session == session) ? 1U : 0U;
}

static void usb_cdc_flush_tx_queue(void)
{
  ULONG queue_message;

  while (tx_queue_receive(&usb_cdc_tx_queue, &queue_message,
                          TX_NO_WAIT) == TX_SUCCESS)
  {
    if (queue_message != 0U)
    {
      usb_cdc_tx_slot_release(
          (USB_CDC_TxSlot_t *)(uintptr_t)queue_message);
    }
  }
}

static void usb_cdc_flush_rx_queue(TX_QUEUE *queue)
{
  ULONG queue_message;

  while (tx_queue_receive(queue, &queue_message, TX_NO_WAIT) == TX_SUCCESS)
  {
    if (queue_message != 0U)
    {
      usb_cdc_rx_slot_release(
          (USB_CDC_RxSlot_t *)(uintptr_t)queue_message);
    }
  }
}

static void usb_cdc_release_consumer_slot(void)
{
  if ((usb_cdc_initialized != 0U) &&
      (tx_mutex_get(&usb_cdc_rx_consumer_mutex,
                    TX_WAIT_FOREVER) == TX_SUCCESS))
  {
    usb_cdc_rx_slot_release(usb_cdc_rx_consumer_slot);
    usb_cdc_rx_consumer_slot = UX_NULL;
    usb_cdc_rx_consumer_offset = 0U;
    (void)tx_mutex_put(&usb_cdc_rx_consumer_mutex);
  }
}

static void usb_cdc_signal_tx_completion(UINT status, ULONG length)
{
  UINT signal = 0U;

  TX_INTERRUPT_SAVE_AREA
  TX_DISABLE
  if (usb_cdc_inflight_slot != UX_NULL)
  {
    usb_cdc_completion_status = status;
    usb_cdc_completion_length = length;
    usb_cdc_completion_sequence = usb_cdc_submit_sequence;
    signal = 1U;
  }
  TX_RESTORE
  if (signal != 0U)
  {
    (void)tx_semaphore_put(&usb_cdc_tx_completion);
  }
}

static void usb_cdc_counter_add(ULONG *counter, ULONG value)
{
  TX_INTERRUPT_SAVE_AREA
  TX_DISABLE
  *counter += value;
  TX_RESTORE
}

static void usb_cdc_set_last_error(ULONG *counter, ULONG *last_error,
                                   UINT status)
{
  TX_INTERRUPT_SAVE_AREA
  TX_DISABLE
  ++(*counter);
  *last_error = (ULONG)status;
  TX_RESTORE
}
