#include "spi_port.h"

#include <stdint.h>
#include <string.h>

#include "bsp_conf.h"
#include "main.h"
#include "stm32n6xx_ll_dma.h"

#define SYSTICK_LOAD   (*(volatile uint32_t *)0xE000E014UL)
#define SYSTICK_VALUE  (*(volatile uint32_t *)0xE000E018UL)
#define MICROSECOND_TO_TICK(us) ((us) * (SystemCoreClock >> 20U))
#define WAIT_FROM(start, count) do {                    \
  int32_t end = (start) - (int32_t)(count);             \
  if (end < 0) { end += (int32_t)SYSTICK_LOAD; }        \
  while ((int32_t)SYSTICK_VALUE > end) { }              \
} while (0)

static spi_transaction_complete_t transaction_complete_callback;

void *spi_port_memcpy(void *dest, const void *src, unsigned int len)
{
  return memcpy(dest, src, len);
}

int32_t spi_port_init(spi_transaction_complete_t callback)
{
  if (NCP_SPI_HANDLE.State == HAL_SPI_STATE_RESET)
  {
    LogError("SPI5 is not initialized\n");
    return -1;
  }

  transaction_complete_callback = callback;
  HAL_GPIO_WritePin(CHIP_EN_GPIO_Port, CHIP_EN_Pin, GPIO_PIN_SET);
  return 0;
}

int32_t spi_port_deinit(void)
{
  HAL_GPIO_WritePin(CHIP_EN_GPIO_Port, CHIP_EN_Pin, GPIO_PIN_RESET);
  transaction_complete_callback = NULL;
  return 0;
}

int32_t spi_port_transfer(void *tx_buf, void *rx_buf, uint16_t len, uint32_t timeout)
{
  HAL_StatusTypeDef status;

  if (NCP_SPI_HANDLE.State == HAL_SPI_STATE_RESET)
  {
    return -1;
  }

#if defined(__DCACHE_PRESENT) && (__DCACHE_PRESENT == 1U)
  SCB_CleanInvalidateDCache_by_Addr(rx_buf, len);
#endif

  if (tx_buf != NULL)
  {
#if defined(__DCACHE_PRESENT) && (__DCACHE_PRESENT == 1U)
    SCB_CleanDCache_by_Addr(tx_buf, len);
#endif
    status = HAL_SPI_TransmitReceive(&NCP_SPI_HANDLE, tx_buf, rx_buf, len, timeout);
  }
  else
  {
    uint8_t dummy[SPI_DMA_XFER_SIZE_THRESHOLD] = {0};
    if (len > sizeof(dummy))
    {
      return -1;
    }
    status = HAL_SPI_TransmitReceive(&NCP_SPI_HANDLE, dummy, rx_buf, len, timeout);
  }
  return (status == HAL_OK) ? 0 : -1;
}

int32_t spi_port_transfer_dma(void *tx_buf, void *rx_buf, uint16_t len)
{
  static uint8_t tx_dummy;
  HAL_StatusTypeDef status;

  if ((NCP_SPI_HANDLE.State == HAL_SPI_STATE_RESET) ||
      (NCP_SPI_HANDLE.hdmatx == NULL) || (NCP_SPI_HANDLE.hdmarx == NULL))
  {
    return -1;
  }

#if defined(__DCACHE_PRESENT) && (__DCACHE_PRESENT == 1U)
  SCB_CleanInvalidateDCache_by_Addr(rx_buf, len);
#endif

  if (tx_buf != NULL)
  {
#if defined(__DCACHE_PRESENT) && (__DCACHE_PRESENT == 1U)
    SCB_CleanDCache_by_Addr(tx_buf, len);
#endif
    LL_DMA_SetSrcIncMode(GET_DMA_INSTANCE(NCP_SPI_HANDLE.hdmatx),
                         GET_DMA_CHANNEL(NCP_SPI_HANDLE.hdmatx), LL_DMA_SRC_INCREMENT);
    status = HAL_SPI_TransmitReceive_DMA(&NCP_SPI_HANDLE, tx_buf, rx_buf, len);
  }
  else
  {
    tx_dummy = 0U;
    LL_DMA_SetSrcIncMode(GET_DMA_INSTANCE(NCP_SPI_HANDLE.hdmatx),
                         GET_DMA_CHANNEL(NCP_SPI_HANDLE.hdmatx), LL_DMA_SRC_FIXED);
    status = HAL_SPI_TransmitReceive_DMA(&NCP_SPI_HANDLE, &tx_dummy, rx_buf, len);
  }
  return (status == HAL_OK) ? 0 : -1;
}

int32_t spi_port_is_ready(void)
{
  return (int32_t)HAL_GPIO_ReadPin(SPI_RDY_GPIO_Port, SPI_RDY_Pin);
}

int32_t spi_port_set_cs(int32_t state)
{
  static int32_t last_falling_tick;
  if (state == 1)
  {
    WAIT_FROM(last_falling_tick, MICROSECOND_TO_TICK(2U));
    HAL_GPIO_WritePin(SPI_CS_GPIO_Port, SPI_CS_Pin, GPIO_PIN_SET);
  }
  else
  {
    HAL_GPIO_WritePin(SPI_CS_GPIO_Port, SPI_CS_Pin, GPIO_PIN_RESET);
    last_falling_tick = (int32_t)SYSTICK_VALUE;
  }
  return 0;
}

static void spi_port_complete(SPI_HandleTypeDef *hspi)
{
  if ((hspi == &NCP_SPI_HANDLE) && (transaction_complete_callback != NULL))
  {
    transaction_complete_callback();
  }
}

void HAL_SPI_TxCpltCallback(SPI_HandleTypeDef *hspi)
{
  spi_port_complete(hspi);
}

void HAL_SPI_RxCpltCallback(SPI_HandleTypeDef *hspi)
{
  spi_port_complete(hspi);
}

void HAL_SPI_TxRxCpltCallback(SPI_HandleTypeDef *hspi)
{
  spi_port_complete(hspi);
}

void HAL_SPI_ErrorCallback(SPI_HandleTypeDef *hspi)
{
  if (hspi == &NCP_SPI_HANDLE)
  {
    LogError("SPI5 transfer error: 0x%08lx\n", (unsigned long)hspi->ErrorCode);
    spi_port_complete(hspi);
  }
}
