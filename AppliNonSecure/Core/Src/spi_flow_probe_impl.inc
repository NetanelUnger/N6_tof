/* Explicit one-shot diagnostic only, compiled with RX-backpressure profile.
 * HAL_DMAEx_Suspend/Resume (DMA, NOT unsupported HAL_SPI_DMAPause) preserve the
 * active DMA descriptor. HAL suspend timeout is5ms; the extra loop is bounded
 * by100000iterations regardless of tick progress. No log/alloc/IRQ mask here.
 * Never inject into a firmware update; use a harmless ordinary radio request.
 */
typedef struct {
  uint32_t stage,transfer,length,suspend_status,resume_status,sr,left,completed,base_resumes,max_seen;
} SpiFlowTest;
static volatile SpiFlowTest flow_test;
static uint32_t flow_test_reported;
static uint32_t flow_test_max_reported;

int32_t spi_port_arm_rx_flow_test(void)
{
  if(Firmware_Update_IsActive() || NCP_SPI_HANDLE.State==HAL_SPI_STATE_RESET ||
      !(NCP_SPI_HANDLE.Instance->CR1&SPI_CR1_MASRX))return -1;
  uint32_t p=__get_PRIMASK();__disable_irq();
  if(flow_test.stage && flow_test.stage<5U){__set_PRIMASK(p);return -2;}
  flow_test=(SpiFlowTest){0};flow_test.base_resumes=rx_flow_resumes;
  flow_test.stage=1;flow_test_reported=flow_test_max_reported=0;__set_PRIMASK(p);return 0;
}

int32_t spi_port_cancel_rx_flow_test(void)
{
  uint32_t p=__get_PRIMASK();__disable_irq();
  if(flow_test.stage!=1U){__set_PRIMASK(p);return -1;}
  flow_test.stage=0;__set_PRIMASK(p);return 0;
}

static int32_t spi_port_maybe_test_rx_flow(uint16_t len)
{
  if(flow_test.stage==1U && !Firmware_Update_IsActive() && len>flow_test.max_seen)flow_test.max_seen=len;
  /* SPI5 uses8byte FIFO at8bit data size.64bytes exceeds FIFO capacity while
   * allowing ordinary short AT replies, unlike the unexercised256byte gate. */
  if(flow_test.stage!=1U || len<64U || Firmware_Update_IsActive() ||
      NCP_SPI_HANDLE.State!=HAL_SPI_STATE_BUSY_TX_RX ||
      !NCP_SPI_HANDLE.hdmarx || NCP_SPI_HANDLE.hdmarx->State!=HAL_DMA_STATE_BUSY ||
      !(NCP_SPI_HANDLE.Instance->CR1&SPI_CR1_MASRX))return 0;
  flow_test.transfer=transfer_id;flow_test.length=len;flow_test.stage=2;
  flow_test.suspend_status=HAL_DMAEx_Suspend(NCP_SPI_HANDLE.hdmarx);
  if(flow_test.suspend_status!=HAL_OK){flow_test.stage=9;return -1;}
  flow_test.stage=3;
  uint32_t spins=0;
  while(!(NCP_SPI_HANDLE.Instance->SR&SPI_SR_SUSP) && spins<100000U)++spins;
  flow_test.sr=NCP_SPI_HANDLE.Instance->SR;
  flow_test.left=NCP_SPI_HANDLE.hdmarx->Instance->CBR1;
  flow_test.stage=4;
  flow_test.resume_status=HAL_DMAEx_Resume(NCP_SPI_HANDLE.hdmarx);
  if(flow_test.resume_status!=HAL_OK){flow_test.stage=9;return -1;}
  /* Ordinary spi_port_service_rx_flow must clear the SPI suspend after DMA
   * drains FIFO. Never clear SPI SUSP, read RXDR or restart DMA in this probe. */
  return 0;
}

static void spi_port_flow_test_complete(void)
{
  if(flow_test.transfer==transfer_id && flow_test.stage>=2U && flow_test.stage<9U){
    flow_test.completed=transaction_failed?2U:1U;flow_test.stage=5;
  }
}

static void spi_port_report_flow_test(void)
{
  SpiFlowTest f;uint32_t p=__get_PRIMASK();__disable_irq();f=flow_test;__set_PRIMASK(p);
  if(!f.stage||(f.stage==flow_test_reported&&f.max_seen==flow_test_max_reported))return;
  flow_test_reported=f.stage;flow_test_max_reported=f.max_seen;
  Debug_UART_Log("SPI-FLOW-TEST","stage=%lu transfer=%lu len=%lu suspend=%lu resume=%lu sr=%08lX rx-left=%lu completed=%lu resumes=%lu max=%lu",
    (unsigned long)f.stage,(unsigned long)f.transfer,(unsigned long)f.length,
    (unsigned long)f.suspend_status,(unsigned long)f.resume_status,(unsigned long)f.sr,
    (unsigned long)f.left,(unsigned long)f.completed,(unsigned long)(rx_flow_resumes-f.base_resumes),(unsigned long)f.max_seen);
}
