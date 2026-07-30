#ifndef USB_CDC_TRANSPORT_H
#define USB_CDC_TRANSPORT_H

#include "tx_api.h"
#include "ux_api.h"
#include "ux_device_class_cdc_acm.h"

#ifdef __cplusplus
extern "C" {
#endif

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
  ULONG tx_callback_completions;
  ULONG tx_errors;
  ULONG tx_last_error;
  ULONG rx_packets_received;
  ULONG rx_packets_delivered;
  ULONG rx_bytes_received;
  ULONG rx_packets_dropped;
  ULONG rx_slot_exhaustions;
  ULONG rx_errors;
  ULONG rx_last_error;
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

#ifdef __cplusplus
}
#endif

#endif /* USB_CDC_TRANSPORT_H */
