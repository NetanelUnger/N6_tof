#ifndef USB_CDC_TRANSPORT_H
#define USB_CDC_TRANSPORT_H

#include "tx_api.h"
#include "ux_api.h"
#include "ux_device_class_cdc_acm.h"

#ifdef __cplusplus
extern "C" {
#endif

#define USB_CDC_DIAG_TX_UNAVAILABLE       (1UL << 0)
#define USB_CDC_DIAG_TX_SLOT_EXHAUSTED    (1UL << 1)
#define USB_CDC_DIAG_TX_QUEUE_FULL        (1UL << 2)
#define USB_CDC_DIAG_TX_CALLBACK_TIMEOUT  (1UL << 3)
#define USB_CDC_DIAG_TX_TRANSFER_ERROR    (1UL << 4)
#define USB_CDC_DIAG_RX_SLOT_EXHAUSTED    (1UL << 5)
#define USB_CDC_DIAG_RX_QUEUE_FULL        (1UL << 6)
#define USB_CDC_DIAG_RX_TRANSFER_ERROR    (1UL << 7)
#define USB_CDC_DIAG_WORKER_SYNC_FAILURE  (1UL << 8)

typedef struct
{
  UINT initialized;
  UINT active;
  ULONG session;
  ULONG tx_control_slots_free;
  ULONG tx_map_slots_free;
  ULONG rx_slots_free;
  ULONG tx_queue_depth;
  ULONG rx_queue_depth;
  ULONG tx_in_flight;
  ULONG tx_packets_queued;
  ULONG tx_packets_completed;
  ULONG tx_bytes_completed;
  ULONG tx_packets_dropped;
  ULONG tx_slot_exhaustions;
  ULONG tx_unavailable_drops;
  ULONG tx_queue_failures;
  ULONG tx_callback_timeouts;
  ULONG tx_callback_completions;
  ULONG tx_errors;
  ULONG tx_last_error;
  ULONG rx_packets_received;
  ULONG rx_packets_delivered;
  ULONG rx_bytes_received;
  ULONG rx_packets_dropped;
  ULONG rx_slot_exhaustions;
  ULONG rx_queue_failures;
  ULONG rx_errors;
  ULONG rx_last_error;
  ULONG worker_sync_failures;
} USB_CDC_TransportStatus_t;

typedef struct
{
  UCHAR *data;
  ULONG capacity;
  VOID *handle;
} USB_CDC_TxBuffer_t;

UINT USB_CDC_Transport_Init(void);
UINT USB_CDC_Transport_Start(UX_SLAVE_CLASS_CDC_ACM *instance);
void USB_CDC_Transport_BeginStop(void);
UINT USB_CDC_Transport_WaitStopped(ULONG wait_option);
UINT USB_CDC_Transport_IsReady(void);

/* Copy a short control/CLI message into one or more fixed-size static slots.
 * No byte-pool or heap allocation occurs. */
UINT USB_CDC_Transport_Send(const void *buffer, ULONG length,
                            ULONG wait_option);

/* Reserve one of the two static 48 KiB map buffers.  The producer renders
 * directly into the returned buffer and commits it without another copy. */
UINT USB_CDC_Transport_AcquireMapBuffer(USB_CDC_TxBuffer_t *buffer);
UINT USB_CDC_Transport_CommitMapBuffer(USB_CDC_TxBuffer_t *buffer,
                                       ULONG length);
void USB_CDC_Transport_CancelMapBuffer(USB_CDC_TxBuffer_t *buffer);

/* Receive data already copied by the USBX read callback into a fixed static
 * RX slot and validated by the application RX worker. */
UINT USB_CDC_Transport_Receive(void *buffer, ULONG requested_length,
                               ULONG *actual_length, ULONG wait_option);

void USB_CDC_Transport_GetStatus(USB_CDC_TransportStatus_t *status);

/* Atomically return and clear rare-event flags. Counters in GetStatus retain
 * the full history; flags merely wake concise, thread-context diagnostics. */
ULONG USB_CDC_Transport_TakeDiagnosticFlags(void);

#ifdef __cplusplus
}
#endif

#endif /* USB_CDC_TRANSPORT_H */
