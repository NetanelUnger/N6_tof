#include "app_console.h"

#include "usb_cdc_transport.h"

#define CONSOLE_TX_FLOW_CONTROL_TICKS  (TX_TIMER_TICKS_PER_SECOND / 50U)
#define CONSOLE_RX_WAIT_TICKS          (TX_TIMER_TICKS_PER_SECOND / 10U)

static UINT console_initialized;

UINT App_Console_Init(void)
{
  /* The USB manager creates the transport pool, queues, and workers.  The
   * console is deliberately only a producer/consumer facade. */
  console_initialized = 1U;
  return TX_SUCCESS;
}

UINT App_Console_IsReady(void)
{
  if (console_initialized == 0U)
  {
    return UX_FALSE;
  }

  return USB_CDC_Transport_IsReady();
}

UINT App_Console_Write(const void *buffer, ULONG length)
{
  if ((buffer == TX_NULL) || (length == 0U))
  {
    return TX_SUCCESS;
  }

  if (console_initialized == 0U)
  {
    return UX_ERROR;
  }

  /* Wait only for queue/pool backpressure.  The caller never waits for the
   * physical USB transfer; the TX worker owns that operation. */
  return USB_CDC_Transport_Send(buffer, length,
                                CONSOLE_TX_FLOW_CONTROL_TICKS);
}

UINT App_Console_WriteAsync(const void *buffer, ULONG length)
{
  if ((buffer == TX_NULL) || (length == 0U))
  {
    return TX_SUCCESS;
  }

  if (console_initialized == 0U)
  {
    return UX_ERROR;
  }

  return USB_CDC_Transport_Send(buffer, length, TX_NO_WAIT);
}

UINT App_Console_Read(void *buffer, ULONG requested_length,
                      ULONG *actual_length)
{
  if (console_initialized == 0U)
  {
    if (actual_length != TX_NULL)
    {
      *actual_length = 0U;
    }
    return UX_ERROR;
  }

  /* The USB RX worker already performed the USBX read.  This call consumes
   * only pool-backed data from the RX queue. */
  return USB_CDC_Transport_Receive(buffer, requested_length, actual_length,
                                   CONSOLE_RX_WAIT_TICKS);
}

UINT App_Console_AcquireFrameBuffer(App_Console_FrameBuffer_t *buffer)
{
  USB_CDC_TxBuffer_t transport_buffer;
  UINT status;

  if ((console_initialized == 0U) || (buffer == TX_NULL))
  {
    return UX_ERROR;
  }

  status = USB_CDC_Transport_AcquireMapBuffer(&transport_buffer);
  if (status == TX_SUCCESS)
  {
    buffer->data = (CHAR *)transport_buffer.data;
    buffer->capacity = transport_buffer.capacity;
    buffer->handle = transport_buffer.handle;
  }
  return status;
}

UINT App_Console_CommitFrameBuffer(App_Console_FrameBuffer_t *buffer,
                                   ULONG length)
{
  USB_CDC_TxBuffer_t transport_buffer;
  UINT status;

  if ((console_initialized == 0U) || (buffer == TX_NULL))
  {
    return UX_ERROR;
  }

  transport_buffer.data = (UCHAR *)buffer->data;
  transport_buffer.capacity = buffer->capacity;
  transport_buffer.handle = buffer->handle;
  status = USB_CDC_Transport_CommitMapBuffer(&transport_buffer, length);
  buffer->data = TX_NULL;
  buffer->capacity = 0U;
  buffer->handle = TX_NULL;
  return status;
}

void App_Console_CancelFrameBuffer(App_Console_FrameBuffer_t *buffer)
{
  USB_CDC_TxBuffer_t transport_buffer;

  if (buffer == TX_NULL)
  {
    return;
  }

  transport_buffer.data = (UCHAR *)buffer->data;
  transport_buffer.capacity = buffer->capacity;
  transport_buffer.handle = buffer->handle;
  USB_CDC_Transport_CancelMapBuffer(&transport_buffer);
  buffer->data = TX_NULL;
  buffer->capacity = 0U;
  buffer->handle = TX_NULL;
}
