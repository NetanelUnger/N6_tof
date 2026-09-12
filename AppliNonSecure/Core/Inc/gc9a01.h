#ifndef GC9A01_H
#define GC9A01_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>
#include <stdint.h>

#include "stm32n6xx_hal.h"

#define GC9A01_WIDTH   (240U)
#define GC9A01_HEIGHT  (240U)

typedef enum
{
  GC9A01_TRANSFER_OK = 0,
  GC9A01_TRANSFER_ERROR
} GC9A01_TransferResult_t;

typedef void (*GC9A01_TransferCallback_t)(GC9A01_TransferResult_t result,
                                          void *context);

typedef struct
{
  SPI_HandleTypeDef *spi;
  GPIO_TypeDef *cs_port;
  uint16_t cs_pin;
  GPIO_TypeDef *dc_port;
  uint16_t dc_pin;
  GPIO_TypeDef *reset_port;
  uint16_t reset_pin;
  GC9A01_TransferCallback_t transfer_callback;
  void *callback_context;
} GC9A01_Config_t;

typedef struct
{
  GC9A01_Config_t config;
  volatile bool transfer_active;
  volatile bool release_cs_on_complete;
} GC9A01_Handle_t;

HAL_StatusTypeDef GC9A01_Open(GC9A01_Handle_t *display,
                              const GC9A01_Config_t *config);
HAL_StatusTypeDef GC9A01_TransmitAsync(GC9A01_Handle_t *display,
                                       bool data_mode,
                                       const uint8_t *data,
                                       uint16_t length,
                                       bool release_cs);
HAL_StatusTypeDef GC9A01_Abort(GC9A01_Handle_t *display);
void GC9A01_SetReset(GC9A01_Handle_t *display, bool released);
void GC9A01_SPI_TxCompleteFromISR(GC9A01_Handle_t *display,
                                  SPI_HandleTypeDef *spi);
void GC9A01_SPI_ErrorFromISR(GC9A01_Handle_t *display,
                             SPI_HandleTypeDef *spi);

#ifdef __cplusplus
}
#endif

#endif /* GC9A01_H */
