#include "spi_port.h"

#include <stdint.h>
#include <string.h>

#include "bsp_conf.h"
#include "app_features.h"
#ifdef APP_GC9A01_DISPLAY_ENABLED
#include "display_app.h"
#endif
#include "main.h"
#include "debug_uart.h"
#include "stm32n6xx_ll_dma.h"
#include "stm32n6xx_hal_dma_ex.h"
#include "firmware_update.h"
#include "tx_api.h"
#if defined(N6_XIP_FAULT_PROBE) && (N6_XIP_FAULT_PROBE == 1)
#include "xip_fault_probe.h"
#else
#define XipProbe_CaptureFault(source, prior) ((void)0)
#define XipProbe_ReportFault() ((void)0)
#endif

#define SYSTICK_LOAD   (*(volatile uint32_t *)0xE000E014UL)
#define SYSTICK_VALUE  (*(volatile uint32_t *)0xE000E018UL)
#define MICROSECOND_TO_TICK(us) ((us) * ((SystemCoreClock + 999999U) / 1000000U))

static spi_transaction_complete_t transaction_complete_callback;
static volatile int32_t transaction_failed;
static uint32_t dma_reinitializations;
static uint32_t dma_reinitialization_failures;
static uint32_t spi_reinitializations;
static uint32_t spi_reinitialization_failures;
static uint32_t cs_hold_timer_fallbacks;
static volatile SpiPortFault_t spi_fault;
static volatile uint32_t transfer_id, transfer_phase, transfer_length, transfer_rx_only;
static volatile uint32_t fault_reported; /* Radio writes; IRQ capture reads. */
#if defined(N6_SPI_RX_FLOW_CONTROL) && (N6_SPI_RX_FLOW_CONTROL == 1)
static volatile uint32_t rx_flow_resumes;
static uint32_t rx_flow_reported;
static volatile uint32_t transfer_started_tick;
uint32_t spi_port_transfer_started_tick(void){return transfer_started_tick;}
#else
uint32_t spi_port_transfer_started_tick(void){return 0;}
#endif
#if defined(N6_XIP_RX_BACKPRESSURE) && (N6_XIP_RX_BACKPRESSURE == 1)
#include "spi_flow_probe_impl.inc"
#else
int32_t spi_port_arm_rx_flow_test(void){return -1;}
int32_t spi_port_cancel_rx_flow_test(void){return -1;}
#endif

void spi_port_set_phase(uint32_t phase) { transfer_phase = phase; }

void spi_port_capture_failure(uint32_t source)
{
  uint32_t posture = __get_PRIMASK();
  __disable_irq();
  /* HAL can call the error callback once for each DMA abort. Preserve the
   * first register snapshot, enriching only the later HAL error code. */
  if (spi_fault.count && spi_fault.transfer == transfer_id)
  {
    spi_fault.spi_error |= NCP_SPI_HANDLE.ErrorCode;
    __set_PRIMASK(posture);
    return;
  }
  if (spi_fault.count != fault_reported)
  {
    ++spi_fault.collapsed; /* retain the first fault until Radio can print it */
    __set_PRIMASK(posture);
    return;
  }
  spi_fault.count++;
  spi_fault.collapsed = 0U;
  spi_fault.tick = HAL_GetTick();
  spi_fault.transfer = transfer_id;
  spi_fault.phase = transfer_phase;
  spi_fault.length = transfer_length;
  spi_fault.rx_only = transfer_rx_only;
  spi_fault.source = source;
  spi_fault.spi_error = NCP_SPI_HANDLE.ErrorCode;
  spi_fault.spi_state = NCP_SPI_HANDLE.State;
  spi_fault.sr = NCP_SPI_HANDLE.Instance->SR;
  spi_fault.cr1 = NCP_SPI_HANDLE.Instance->CR1;
  spi_fault.cr2 = NCP_SPI_HANDLE.Instance->CR2;
  spi_fault.cfg1 = NCP_SPI_HANDLE.Instance->CFG1;
  spi_fault.cfg2 = NCP_SPI_HANDLE.Instance->CFG2;
  spi_fault.ier = NCP_SPI_HANDLE.Instance->IER;
  spi_fault.pins = ((SPI_CS_GPIO_Port->IDR & SPI_CS_Pin) ? 1U : 0U) |
      ((SPI_RDY_GPIO_Port->IDR & SPI_RDY_Pin) ? 2U : 0U) |
      ((CHIP_EN_GPIO_Port->IDR & CHIP_EN_Pin) ? 4U : 0U);
  DMA_HandleTypeDef *tx = NCP_SPI_HANDLE.hdmatx, *rx = NCP_SPI_HANDLE.hdmarx;
  if (tx && tx->Instance)
  {
    spi_fault.tx_state = tx->State; spi_fault.tx_error = tx->ErrorCode;
    spi_fault.tx_ccr = tx->Instance->CCR; spi_fault.tx_csr = tx->Instance->CSR;
    spi_fault.tx_remaining = tx->Instance->CBR1;
    spi_fault.tx_ctr1 = tx->Instance->CTR1; spi_fault.tx_ctr2 = tx->Instance->CTR2;
  }
  if (rx && rx->Instance)
  {
    spi_fault.rx_state = rx->State; spi_fault.rx_error = rx->ErrorCode;
    spi_fault.rx_ccr = rx->Instance->CCR; spi_fault.rx_csr = rx->Instance->CSR;
    spi_fault.rx_remaining = rx->Instance->CBR1;
    spi_fault.rx_ctr1 = rx->Instance->CTR1; spi_fault.rx_ctr2 = rx->Instance->CTR2;
  }
  XipProbe_CaptureFault(source,posture);
  __set_PRIMASK(posture);
}

void spi_port_capture_irq(void)
{
  /* Capture before HAL clears OVR/MODF/FRE/UDR and starts DMA aborts. */
  if (NCP_SPI_HANDLE.Instance->SR & NCP_SPI_HANDLE.Instance->IER &
      (SPI_FLAG_OVR | SPI_FLAG_MODF | SPI_FLAG_FRE | SPI_FLAG_UDR))
    spi_port_capture_failure(1U);
}

void spi_port_get_fault(SpiPortFault_t *fault)
{
  if (!fault) return;
  uint32_t posture = __get_PRIMASK(); __disable_irq();
  *fault = spi_fault;
  __set_PRIMASK(posture);
}

void spi_port_report_fault(void)
{
#if defined(N6_XIP_RX_BACKPRESSURE) && (N6_XIP_RX_BACKPRESSURE == 1)
  spi_port_report_flow_test();
#endif
#if defined(N6_SPI_RX_FLOW_CONTROL) && (N6_SPI_RX_FLOW_CONTROL == 1)
  uint32_t resumed=rx_flow_resumes;
  if (resumed!=rx_flow_reported)
  {
    rx_flow_reported=resumed;
    Debug_UART_Log("SPI-FLOW","drained RX automatic suspensions resumed=%lu",
        (unsigned long)resumed);
  }
#endif
  SpiPortFault_t f;
  spi_port_get_fault(&f);
  if (f.count == fault_reported) return;
  fault_reported = f.count;
  Debug_UART_Log("SPI-FAULT", "count=%lu tick=%lu transfer=%lu phase=%lu len=%lu rx_only=%lu source=%lu HAL_error=0x%08lx state=%lu collapsed=%lu",
      (unsigned long)f.count, (unsigned long)f.tick, (unsigned long)f.transfer,
      (unsigned long)f.phase, (unsigned long)f.length, (unsigned long)f.rx_only,
      (unsigned long)f.source, (unsigned long)f.spi_error, (unsigned long)f.spi_state,
      (unsigned long)f.collapsed);
  Debug_UART_Log("SPI-FAULT", "SR=%08lx CR1=%08lx CR2=%08lx CFG1=%08lx CFG2=%08lx IER=%08lx pins(CS/RDY/EN)=%lx",
      (unsigned long)f.sr, (unsigned long)f.cr1, (unsigned long)f.cr2,
      (unsigned long)f.cfg1, (unsigned long)f.cfg2, (unsigned long)f.ier, (unsigned long)f.pins);
  Debug_UART_Log("SPI-FAULT", "TX state=%lu error=%08lx CCR=%08lx CSR=%08lx CBR1=%08lx CTR1=%08lx CTR2=%08lx",
      (unsigned long)f.tx_state, (unsigned long)f.tx_error, (unsigned long)f.tx_ccr,
      (unsigned long)f.tx_csr, (unsigned long)f.tx_remaining,
      (unsigned long)f.tx_ctr1, (unsigned long)f.tx_ctr2);
  Debug_UART_Log("SPI-FAULT", "RX state=%lu error=%08lx CCR=%08lx CSR=%08lx CBR1=%08lx CTR1=%08lx CTR2=%08lx",
      (unsigned long)f.rx_state, (unsigned long)f.rx_error, (unsigned long)f.rx_ccr,
      (unsigned long)f.rx_csr, (unsigned long)f.rx_remaining,
      (unsigned long)f.rx_ctr1, (unsigned long)f.rx_ctr2);
  XipProbe_ReportFault();
}

static void spi_port_wait_cs_hold(uint32_t start, uint32_t count)
{
  uint32_t period = SYSTICK_LOAD + 1U;
  /* Compare elapsed down-counter ticks, including reload. The old absolute
   * endpoint comparison could require sampling VAL == 0 and spin for seconds
   * when the endpoint was zero. Missing zero must never prolong the hold. */
  for (uint32_t remaining = count + 64U; remaining != 0U; --remaining)
  {
    uint32_t current = SYSTICK_VALUE;
    uint32_t elapsed = (start >= current) ?
        start - current : start + period - current;
    if (elapsed >= count) return;
  }
  /* A stopped/reconfigured SysTick cannot strand the SPI owner. At least one
   * volatile read per core-cycle budget supplies a conservative software
   * minimum hold even when the timer is unavailable; no IRQ masking needed. */
  cs_hold_timer_fallbacks++;
}

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

#if defined(N6_SPI_RX_FLOW_CONTROL) && (N6_SPI_RX_FLOW_CONTROL == 1)
  /* Production RX flow control. ST AN5543 Rev5 section4.1.1 describes
   * MASRX flow control when the receive FIFO cannot drain promptly. The N6
   * HAL supports it for master >=8bit transfers, including two-line mode.
   * Configure only while disabled, before the NCP is powered. Keep Init in
   * sync so the local error-recovery HAL_SPI_Init preserves this setting.
   * No baud rate, IRQ priority, DMA priority, CS or timeout changes.
   */
  if ((NCP_SPI_HANDLE.State != HAL_SPI_STATE_READY) ||
      ((NCP_SPI_HANDLE.Instance->CR1 & SPI_CR1_SPE) != 0U) ||
      (NCP_SPI_HANDLE.Init.Mode != SPI_MODE_MASTER) ||
      (NCP_SPI_HANDLE.Init.Direction != SPI_DIRECTION_2LINES) ||
      (NCP_SPI_HANDLE.Init.DataSize != SPI_DATASIZE_8BIT)) return -1;
  NCP_SPI_HANDLE.Init.MasterReceiverAutoSusp=SPI_MASTER_RX_AUTOSUSP_ENABLE;
  SET_BIT(NCP_SPI_HANDLE.Instance->CR1,SPI_CR1_MASRX);
  Debug_UART_Log("SPI-FLOW","MASRX enabled; CR1=%08lX",
      (unsigned long)NCP_SPI_HANDLE.Instance->CR1);
#endif

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
  ++transfer_id; transfer_length = len; transfer_rx_only = tx_buf == NULL;

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
  if (status != HAL_OK) spi_port_capture_failure(4U);
  return (status == HAL_OK) ? 0 : -1;
}

int32_t spi_port_transfer_dma(void *tx_buf, void *rx_buf, uint16_t len)
{
  static uint8_t tx_dummy;
  HAL_StatusTypeDef status;
  ++transfer_id; transfer_length = len; transfer_rx_only = tx_buf == NULL;

  if ((NCP_SPI_HANDLE.State == HAL_SPI_STATE_RESET) ||
      (NCP_SPI_HANDLE.hdmatx == NULL) || (NCP_SPI_HANDLE.hdmarx == NULL))
  {
    return -1;
  }

#if defined(__DCACHE_PRESENT) && (__DCACHE_PRESENT == 1U)
  SCB_CleanInvalidateDCache_by_Addr(rx_buf, len);
#endif

  transaction_failed = 0;
#if defined(N6_SPI_RX_FLOW_CONTROL) && (N6_SPI_RX_FLOW_CONTROL == 1)
  transfer_started_tick=tx_time_get();
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
  if (status != HAL_OK)
  {
    transaction_failed = 1;
    spi_port_capture_failure(3U);
    return -1;
  }
#if defined(N6_XIP_RX_BACKPRESSURE) && (N6_XIP_RX_BACKPRESSURE == 1)
  if(spi_port_maybe_test_rx_flow(len)!=0){
    transaction_failed=1;spi_port_capture_failure(8U);return -1;
  }
#endif
  return 0;
}

int32_t spi_port_transfer_dma_status(void)
{
  return ((transaction_failed == 0) &&
          (NCP_SPI_HANDLE.State == HAL_SPI_STATE_READY) &&
          (NCP_SPI_HANDLE.ErrorCode == HAL_SPI_ERROR_NONE)) ? 0 : -1;
}

void spi_port_service_rx_flow(void)
{
#if defined(N6_SPI_RX_FLOW_CONTROL) && (N6_SPI_RX_FLOW_CONTROL == 1)
  uint32_t saved=__get_PRIMASK();
  __disable_irq();
  uint32_t sr=NCP_SPI_HANDLE.Instance->SR;
  /* DMA mode enables EOTIE only after RX completion. An earlier automatic
   * suspend therefore needs task-side service. Never drain RXDR in software
   * or restart DMA: it owns all packet bytes. Resume only a nonempty active
   * transaction after DMA has emptied RX FIFO and no hardware error exists.
   */
  if ((NCP_SPI_HANDLE.State==HAL_SPI_STATE_BUSY_TX_RX) &&
      (NCP_SPI_HANDLE.ErrorCode==HAL_SPI_ERROR_NONE) &&
      ((NCP_SPI_HANDLE.Instance->CR1 & (SPI_CR1_MASRX|SPI_CR1_CSTART|SPI_CR1_SPE))==
        (SPI_CR1_MASRX|SPI_CR1_CSTART|SPI_CR1_SPE)) &&
      ((NCP_SPI_HANDLE.Instance->CFG1 & SPI_CFG1_RXDMAEN)!=0U) &&
      ((sr & SPI_SR_CTSIZE)!=0U) && ((sr & SPI_SR_SUSP)!=0U) &&
      ((sr & (SPI_SR_RXP|SPI_SR_RXWNE|SPI_SR_RXPLVL|SPI_SR_OVR|SPI_SR_UDR|SPI_SR_MODF|SPI_SR_TIFRE))==0U) &&
      (NCP_SPI_HANDLE.hdmarx!=NULL) && (NCP_SPI_HANDLE.hdmarx->Instance!=NULL) &&
      (NCP_SPI_HANDLE.hdmarx->State==HAL_DMA_STATE_BUSY) &&
      (NCP_SPI_HANDLE.hdmarx->ErrorCode==HAL_DMA_ERROR_NONE) &&
      ((NCP_SPI_HANDLE.hdmarx->Instance->CCR & DMA_CCR_EN)!=0U) &&
      ((NCP_SPI_HANDLE.hdmarx->Instance->CSR & (DMA_CSR_DTEF|DMA_CSR_ULEF|DMA_CSR_USEF|DMA_CSR_TOF|DMA_CSR_SUSPF))==0U))
  {
    WRITE_REG(NCP_SPI_HANDLE.Instance->IFCR,SPI_IFCR_SUSPC);
    ++rx_flow_resumes;
    __DMB();
    __set_PRIMASK(saved);
    /* SPI worker stack is768bytes. Defer all formatting to Radio's reporter. */
    return;
  }
  __set_PRIMASK(saved);
#endif
}

static HAL_StatusTypeDef spi_port_restore_dma(DMA_HandleTypeDef *dma)
{
  if ((dma == NULL) || (dma->Init.Mode != DMA_NORMAL))
  {
    return HAL_ERROR;
  }
  if ((dma->State == HAL_DMA_STATE_READY) &&
      ((dma->Instance->CCR & DMA_CCR_EN) == 0U))
  {
    return HAL_OK;
  }

  /* SPI error callbacks can wake the owner after only one DMA abort completes.
   * HAL_SPI_Abort subsequently reports READY even when the other DMA handle is
   * still ABORT/SUSPEND: it only aborts channels whose SPI DMA-request bit is
   * set. Those bits were already cleared by the SPI error ISR. Restore only
   * the two normal-mode channels owned by SPI5, with HAL's bounded disable
   * waits; never reset the shared DMA controller or the NCP. */
  void *parent = dma->Parent;
  HAL_StatusTypeDef status = HAL_DMA_DeInit(dma);
  if (status == HAL_OK)
  {
    status = HAL_DMA_Init(dma);
    dma->Parent = parent;
  }
  if (status == HAL_OK)
  {
    dma_reinitializations++;
  }
  else
  {
    dma_reinitialization_failures++;
  }
  return status;
}

int32_t spi_port_abort(void)
{
  if (NCP_SPI_HANDLE.State == HAL_SPI_STATE_RESET)
  {
    return -1;
  }

  HAL_StatusTypeDef spi_status = HAL_SPI_Abort(&NCP_SPI_HANDLE);
  /* CS is already deasserted by the sole SPI worker. Quiesce both DMA handles
   * even if SPI abort failed, and do not claim recovery from SPI state alone. */
  HAL_StatusTypeDef tx_status = spi_port_restore_dma(NCP_SPI_HANDLE.hdmatx);
  HAL_StatusTypeDef rx_status = spi_port_restore_dma(NCP_SPI_HANDLE.hdmarx);
  if ((tx_status != HAL_OK) || (rx_status != HAL_OK))
  {
    return -1;
  }
  if (spi_status != HAL_OK)
  {
    /* A failed SPI abort can leave residual FIFO/transfer state even after
     * both DMA handles are clean. Reset this peripheral only after the owned
     * channels have stopped; the retained packet still belongs to the worker.
     * Reuse the existing register configuration. Keep the handle READY so
     * HAL_SPI_Init does not rerun the large generated MSP initializer on the
     * 768-byte transfer-worker stack; GPIO/IRQ and DMA parent links remain set. */
    __HAL_RCC_SPI5_FORCE_RESET();
    __HAL_RCC_SPI5_RELEASE_RESET();
    if (HAL_SPI_Init(&NCP_SPI_HANDLE) != HAL_OK)
    {
      spi_reinitialization_failures++;
      return -1;
    }
    spi_reinitializations++;
  }
  NCP_SPI_HANDLE.ErrorCode = HAL_SPI_ERROR_NONE;
  transaction_failed = 0;
  return 0;
}

int32_t spi_port_is_ready(void)
{
  return (int32_t)HAL_GPIO_ReadPin(SPI_RDY_GPIO_Port, SPI_RDY_Pin);
}

int32_t spi_port_set_cs(int32_t state)
{
  static uint32_t last_falling_tick;
  if (state == 1)
  {
    spi_port_wait_cs_hold(last_falling_tick, MICROSECOND_TO_TICK(2U));
    HAL_GPIO_WritePin(SPI_CS_GPIO_Port, SPI_CS_Pin, GPIO_PIN_SET);
  }
  else
  {
    HAL_GPIO_WritePin(SPI_CS_GPIO_Port, SPI_CS_Pin, GPIO_PIN_RESET);
    last_falling_tick = SYSTICK_VALUE;
  }
  return 0;
}

static void spi_port_complete(SPI_HandleTypeDef *hspi)
{
#if defined(N6_XIP_RX_BACKPRESSURE) && (N6_XIP_RX_BACKPRESSURE == 1)
  if(hspi==&NCP_SPI_HANDLE)spi_port_flow_test_complete();
#endif
  if ((hspi == &NCP_SPI_HANDLE) && (transaction_complete_callback != NULL))
  {
    transaction_complete_callback();
  }
}

void HAL_SPI_TxCpltCallback(SPI_HandleTypeDef *hspi)
{
#ifdef APP_GC9A01_DISPLAY_ENABLED
  Display_App_SPI_TxCompleteFromISR(hspi);
#endif
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
#ifdef APP_GC9A01_DISPLAY_ENABLED
  Display_App_SPI_ErrorFromISR(hspi);
#endif
  if (hspi == &NCP_SPI_HANDLE)
  {
    transaction_failed = 1;
    spi_port_capture_failure(2U);
    spi_port_complete(hspi);
  }
}
