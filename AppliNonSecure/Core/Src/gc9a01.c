#include "gc9a01.h"

#include <string.h>

static void GC9A01_SetChipSelect(GC9A01_Handle_t *display, bool selected)
{
  HAL_GPIO_WritePin(display->config.cs_port, display->config.cs_pin,
                    selected ? GPIO_PIN_RESET : GPIO_PIN_SET);
}

HAL_StatusTypeDef GC9A01_Open(GC9A01_Handle_t *display,
                              const GC9A01_Config_t *config)
{
  if ((display == NULL) || (config == NULL) || (config->spi == NULL) ||
      (config->cs_port == NULL) || (config->dc_port == NULL) ||
      (config->reset_port == NULL) ||
      (config->spi->State == HAL_SPI_STATE_RESET))
  {
    return HAL_ERROR;
  }

  memset(display, 0, sizeof(*display));
  display->config = *config;
  GC9A01_SetChipSelect(display, false);
  GC9A01_SetReset(display, false);
  return HAL_OK;
}

HAL_StatusTypeDef GC9A01_TransmitAsync(GC9A01_Handle_t *display,
                                       bool data_mode,
                                       const uint8_t *data,
                                       uint16_t length,
                                       bool release_cs)
{
  HAL_StatusTypeDef status;

  if ((display == NULL) || (data == NULL) || (length == 0U) ||
      display->transfer_active || (display->config.spi->hdmatx == NULL))
  {
    return HAL_ERROR;
  }

  display->transfer_active = true;
  display->release_cs_on_complete = release_cs;
  GC9A01_SetChipSelect(display, true);
  HAL_GPIO_WritePin(display->config.dc_port, display->config.dc_pin,
                    data_mode ? GPIO_PIN_SET : GPIO_PIN_RESET);

#if defined(__DCACHE_PRESENT) && (__DCACHE_PRESENT == 1U)
  SCB_CleanDCache_by_Addr((void *)data, length);
#endif

  status = HAL_SPI_Transmit_DMA(display->config.spi, (uint8_t *)data, length);
  if (status != HAL_OK)
  {
    display->transfer_active = false;
    GC9A01_SetChipSelect(display, false);
  }
  return status;
}

HAL_StatusTypeDef GC9A01_Abort(GC9A01_Handle_t *display)
{
  HAL_StatusTypeDef status;

  if (display == NULL)
  {
    return HAL_ERROR;
  }

  status = HAL_SPI_Abort(display->config.spi);
  display->transfer_active = false;
  display->release_cs_on_complete = false;
  GC9A01_SetChipSelect(display, false);
  return status;
}

void GC9A01_SetReset(GC9A01_Handle_t *display, bool released)
{
  if (display != NULL)
  {
    HAL_GPIO_WritePin(display->config.reset_port, display->config.reset_pin,
                      released ? GPIO_PIN_SET : GPIO_PIN_RESET);
  }
}

void GC9A01_SPI_TxCompleteFromISR(GC9A01_Handle_t *display,
                                  SPI_HandleTypeDef *spi)
{
  if ((display == NULL) || (spi != display->config.spi) ||
      !display->transfer_active)
  {
    return;
  }

  display->transfer_active = false;
  if (display->release_cs_on_complete)
  {
    GC9A01_SetChipSelect(display, false);
  }
  if (display->config.transfer_callback != NULL)
  {
    display->config.transfer_callback(GC9A01_TRANSFER_OK,
                                      display->config.callback_context);
  }
}

void GC9A01_SPI_ErrorFromISR(GC9A01_Handle_t *display,
                             SPI_HandleTypeDef *spi)
{
  if ((display == NULL) || (spi != display->config.spi) ||
      !display->transfer_active)
  {
    return;
  }

  display->transfer_active = false;
  display->release_cs_on_complete = false;
  GC9A01_SetChipSelect(display, false);
  if (display->config.transfer_callback != NULL)
  {
    display->config.transfer_callback(GC9A01_TRANSFER_ERROR,
                                      display->config.callback_context);
  }
}
