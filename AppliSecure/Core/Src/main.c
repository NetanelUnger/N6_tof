/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

#define VECT_TAB_NS_OFFSET  0x00400
#define VTOR_TABLE_NS_START_ADDR (SRAM2_AXI_BASE_NS|VECT_TAB_NS_OFFSET)
#define VTOR_TABLE_S_START_ADDR  (SRAM2_AXI_BASE_S|VECT_TAB_NS_OFFSET)

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */

static uint32_t cached_non_secure_msp;
static uint32_t cached_non_secure_reset_handler;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
static void NonSecure_Init(void);
static void MX_GPDMA1_Init(void);
static void SystemIsolation_Config(void);
/* USER CODE BEGIN PFP */

static void NonSecure_StartCached(void);

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

static void Secure_Trace(const char *message)
{
  uint32_t timeout;

  if (message == NULL)
  {
    return;
  }

  while (*message != '\0')
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

static void Secure_TraceHex(const char *label, uint32_t value)
{
  static const char hex_digits[] = "0123456789ABCDEF";
  char value_text[] = "0x00000000\r\n";
  uint32_t index;

  for (index = 0U; index < 8U; index++)
  {
    value_text[2U + index] = hex_digits[(value >> (28U - (index * 4U))) & 0xFU];
  }

  Secure_Trace(label);
  Secure_Trace(value_text);
}

static void Secure_RedLedOn(void)
{
  GPIO_InitTypeDef gpio_init = {0};

  __HAL_RCC_GPIOG_CLK_ENABLE();
  gpio_init.Pin = GPIO_PIN_10;
  gpio_init.Mode = GPIO_MODE_OUTPUT_PP;
  gpio_init.Pull = GPIO_NOPULL;
  gpio_init.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOG, &gpio_init);
  HAL_GPIO_WritePin(GPIOG, GPIO_PIN_10, GPIO_PIN_RESET);
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/
  HAL_Init();

  /* USER CODE BEGIN Init */

  Secure_Trace("[SECURE] application entered\r\n");
  Secure_TraceHex("[SECURE] pre-RISAF Secure-alias NS MSP = ",
                  *(const uint32_t *)VTOR_TABLE_S_START_ADDR);
  Secure_TraceHex("[SECURE] pre-RISAF Secure-alias NS Reset_Handler = ",
                  *(const uint32_t *)(VTOR_TABLE_S_START_ADDR + 4U));
  Secure_TraceHex("[SECURE] pre-RISAF NonSecure-alias NS MSP = ",
                  *(const uint32_t *)VTOR_TABLE_NS_START_ADDR);
  Secure_TraceHex("[SECURE] pre-RISAF NonSecure-alias NS Reset_Handler = ",
                  *(const uint32_t *)(VTOR_TABLE_NS_START_ADDR + 4U));

  /*
   * At this point the SAU already marks SRAM2 as NonSecure, while RISAF still
   * protects it as Secure. Read the vectors through the Secure alias, then use
   * their original NonSecure values after SystemIsolation_Config opens SRAM2.
   */
  cached_non_secure_msp = *(const uint32_t *)VTOR_TABLE_S_START_ADDR;
  cached_non_secure_reset_handler =
      *(const uint32_t *)(VTOR_TABLE_S_START_ADDR + 4U);
  Secure_RedLedOn();

  /* USER CODE END Init */

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPDMA1_Init();
  SystemIsolation_Config();
  /* USER CODE BEGIN 2 */

  Secure_Trace("[SECURE] TrustZone isolation configured\r\n");
  NonSecure_StartCached();

  /* USER CODE END 2 */

  /* We should never get here as control is now taken by the scheduler */

  /* Secure SysTick should rather be suspended before calling non-secure  */
  /* in order to avoid wake-up from sleep mode entered by non-secure      */
  /* The Secure SysTick shall be resumed on non-secure callable functions */
  HAL_SuspendTick();

  /*************** Setup and jump to non-secure *******************************/

  NonSecure_Init();

  /* Non-secure software does not return, this code is not executed */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief  Non-secure call function
  *         This function is responsible for Non-secure initialization and switch
  *         to non-secure state
  * @retval None
  */
static void NonSecure_Init(void)
{
  funcptr_NS NonSecure_ResetHandler;

  SCB_NS->VTOR = VTOR_TABLE_NS_START_ADDR;

  /* Set non-secure main stack (MSP_NS) */
  __TZ_set_MSP_NS((*(uint32_t *)VTOR_TABLE_NS_START_ADDR));

  /* Get non-secure reset handler */
  NonSecure_ResetHandler = (funcptr_NS)(*((uint32_t *)((VTOR_TABLE_NS_START_ADDR) + 4U)));

  /* Start non-secure state software application */
  NonSecure_ResetHandler();
}

/**
  * @brief GPDMA1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPDMA1_Init(void)
{

  /* USER CODE BEGIN GPDMA1_Init 0 */

  /* USER CODE END GPDMA1_Init 0 */

  /* Peripheral clock enable */
  __HAL_RCC_GPDMA1_CLK_ENABLE();

  /* USER CODE BEGIN GPDMA1_Init 1 */

  /* USER CODE END GPDMA1_Init 1 */
  /* USER CODE BEGIN GPDMA1_Init 2 */

  /* USER CODE END GPDMA1_Init 2 */

}

/**
  * @brief RIF Initialization Function
  * @param None
  * @retval None
  */
  static void SystemIsolation_Config(void)
{

  /* USER CODE BEGIN RIF_Init 0 */

  DMA_HandleTypeDef wifi_dma_tx = {0};
  DMA_HandleTypeDef wifi_dma_rx = {0};

  /* USER CODE END RIF_Init 0 */

  /* set all required IPs as secure privileged */
  __HAL_RCC_RIFSC_CLK_ENABLE();

  /*RIMC configuration*/
  RIMC_MasterConfig_t RIMC_master = {0};
  RIMC_master.MasterCID = RIF_CID_1;
  RIMC_master.SecPriv = RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_NPRIV;
  HAL_RIF_RIMC_ConfigMasterAttributes(RIF_MASTER_INDEX_ETH1, &RIMC_master);

  /*RISUP configuration*/
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_I2C2 , RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_NPRIV);
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_LPUART1 , RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_NPRIV);
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_ETH1 , RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_NPRIV);
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_ADC12 , RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_NPRIV);
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_XSPI2 , RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_NPRIV);
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_XSPIM , RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_NPRIV);
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_CSI , RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_NPRIV);

  /* RISAF Config */
  RISAF_BaseRegionConfig_t risaf_base_config;
  __HAL_RCC_RISAF_CLK_ENABLE();

  /* set up base region configuration for CPUAXI_RAM1*/
  /* region 1 is non-secure */
  risaf_base_config.EndAddress = 0xfffff;
  risaf_base_config.Filtering = RISAF_FILTER_ENABLE;
  risaf_base_config.ReadWhitelist = 255;
  risaf_base_config.WriteWhitelist = 255;
  risaf_base_config.Secure = RIF_ATTRIBUTE_NSEC;
  risaf_base_config.PrivWhitelist = RIF_CID_NONE;
  risaf_base_config.StartAddress = 0x0000;
  HAL_RIF_RISAF_ConfigBaseRegion(RISAF3, RISAF_REGION_1, &risaf_base_config);

  /* set up base region configuration for CPUAXI_RAM0*/
  /* region 1 is secure */
  risaf_base_config.EndAddress = 0x9bfff;
  risaf_base_config.Secure = RIF_ATTRIBUTE_SEC;
  HAL_RIF_RISAF_ConfigBaseRegion(RISAF2, RISAF_REGION_1, &risaf_base_config);

  /* set up base region configuration for FLEXRAM*/
  /* region 1 is secure */
  risaf_base_config.EndAddress = 0x63fff;
  HAL_RIF_RISAF_ConfigBaseRegion(RISAF7, RISAF_REGION_1, &risaf_base_config);

  /* RIF-Aware IPs Config */

  /* set up GPDMA configuration */

  /* set up GPIO configuration */
  /* GPIOA Non Secure Ports Clock Enable */
  __HAL_RCC_GPIOA_CLK_ENABLE();
  HAL_GPIO_ConfigPinAttributes(GPIOA,GPIO_PIN_3,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOA,GPIO_PIN_10,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOA,GPIO_PIN_11,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  /* GPIOB Non Secure Ports Clock Enable */
  __HAL_RCC_GPIOB_CLK_ENABLE();
  HAL_GPIO_ConfigPinAttributes(GPIOB,GPIO_PIN_0,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOB,GPIO_PIN_3,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOB,GPIO_PIN_6,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOB,GPIO_PIN_7,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOB,GPIO_PIN_10,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOB,GPIO_PIN_11,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  /* GPIOC Non Secure Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  HAL_GPIO_ConfigPinAttributes(GPIOC,GPIO_PIN_1,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  /* GPIOD Non Secure Ports Clock Enable */
  __HAL_RCC_GPIOD_CLK_ENABLE();
  HAL_GPIO_ConfigPinAttributes(GPIOD,GPIO_PIN_5,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOD,GPIO_PIN_8,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOD,GPIO_PIN_9,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  /* GPIOE Non Secure Ports Clock Enable */
  __HAL_RCC_GPIOE_CLK_ENABLE();
  HAL_GPIO_ConfigPinAttributes(GPIOE,GPIO_PIN_3,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOE,GPIO_PIN_9,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOE,GPIO_PIN_10,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOE,GPIO_PIN_15,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  /* GPIOG Non Secure Ports Clock Enable */
  __HAL_RCC_GPIOG_CLK_ENABLE();
  HAL_GPIO_ConfigPinAttributes(GPIOG,GPIO_PIN_1,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOG,GPIO_PIN_2,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);
  /* GPIOH Non Secure Ports Clock Enable */
  __HAL_RCC_GPIOH_CLK_ENABLE();
  HAL_GPIO_ConfigPinAttributes(GPIOH,GPIO_PIN_9,GPIO_PIN_NSEC|GPIO_PIN_NPRIV);

  /* USER CODE BEGIN RIF_Init 1 */

  /* CN8 USB-C is controlled by the NonSecure USB-PD/USBX application. */
  RIMC_master.MasterCID = RIF_CID_1;
  RIMC_master.SecPriv = RIF_ATTRIBUTE_NSEC | RIF_ATTRIBUTE_NPRIV;
  HAL_RIF_RIMC_ConfigMasterAttributes(RIF_MASTER_INDEX_OTG1, &RIMC_master);

  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_UCPD1,
                                        RIF_ATTRIBUTE_NSEC | RIF_ATTRIBUTE_NPRIV);
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_OTG1HS,
                                        RIF_ATTRIBUTE_NSEC | RIF_ATTRIBUTE_NPRIV);
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_I2C2,
                                        RIF_ATTRIBUTE_NSEC | RIF_ATTRIBUTE_NPRIV);
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_ADC12,
                                        RIF_ATTRIBUTE_NSEC | RIF_ATTRIBUTE_NPRIV);

  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  HAL_GPIO_ConfigPinAttributes(GPIOA, GPIO_PIN_5 | GPIO_PIN_7 | GPIO_PIN_11,
                               GPIO_PIN_NSEC | GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOB, GPIO_PIN_10 | GPIO_PIN_11,
                               GPIO_PIN_NSEC | GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOD, GPIO_PIN_2,
                               GPIO_PIN_NSEC | GPIO_PIN_NPRIV);
  HAL_EXTI_ConfigLineAttributes(EXTI_LINE_2, EXTI_LINE_NSEC | EXTI_LINE_NPRIV);
  (void)NVIC_SetTargetState(EXTI2_IRQn);

  /* The ST67W6X transport is owned by the non-secure application. */
  HAL_GPIO_ConfigPinAttributes(GPIOA, GPIO_PIN_3, GPIO_PIN_NSEC | GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOD, GPIO_PIN_5, GPIO_PIN_NSEC | GPIO_PIN_NPRIV);
  __HAL_RCC_GPIOE_CLK_ENABLE();
  HAL_GPIO_ConfigPinAttributes(GPIOE, GPIO_PIN_9 | GPIO_PIN_10 | GPIO_PIN_15,
                               GPIO_PIN_NSEC | GPIO_PIN_NPRIV);
  __HAL_RCC_GPIOG_CLK_ENABLE();
  HAL_GPIO_ConfigPinAttributes(GPIOG, GPIO_PIN_1 | GPIO_PIN_2,
                               GPIO_PIN_NSEC | GPIO_PIN_NPRIV);
  HAL_EXTI_ConfigLineAttributes(EXTI_LINE_9, EXTI_LINE_NSEC | EXTI_LINE_NPRIV);

  wifi_dma_tx.Instance = GPDMA1_Channel10;
  wifi_dma_rx.Instance = GPDMA1_Channel11;
  (void)HAL_DMA_ConfigChannelAttributes(&wifi_dma_tx,
      DMA_CHANNEL_NSEC | DMA_CHANNEL_PRIV | DMA_CHANNEL_SRC_NSEC | DMA_CHANNEL_DEST_NSEC);
  (void)HAL_DMA_ConfigChannelAttributes(&wifi_dma_rx,
      DMA_CHANNEL_NSEC | DMA_CHANNEL_PRIV | DMA_CHANNEL_SRC_NSEC | DMA_CHANNEL_DEST_NSEC);

  /* USER CODE END RIF_Init 1 */
  /* USER CODE BEGIN RIF_Init 2 */

  /* Hand the ST-LINK VCP peripheral and pins to the non-secure application. */
  Secure_Trace("[SECURE] releasing USART1 and PE5/PE6 to NonSecure\r\n");
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_USART1,
                                        RIF_ATTRIBUTE_NSEC | RIF_ATTRIBUTE_NPRIV);
  __HAL_RCC_GPIOE_CLK_ENABLE();
  HAL_GPIO_ConfigPinAttributes(GPIOE, GPIO_PIN_5 | GPIO_PIN_6,
                               GPIO_PIN_NSEC | GPIO_PIN_NPRIV);

  /* USER CODE END RIF_Init 2 */

}

/* USER CODE BEGIN 4 */

static void NonSecure_StartCached(void)
{
  funcptr_NS non_secure_reset_handler;

  Secure_TraceHex("[SECURE] cached NonSecure MSP = ",
                  cached_non_secure_msp);
  Secure_TraceHex("[SECURE] cached NonSecure Reset_Handler = ",
                  cached_non_secure_reset_handler);

  SCB_NS->VTOR = VTOR_TABLE_NS_START_ADDR;
  __TZ_set_MSP_NS(cached_non_secure_msp);
  non_secure_reset_handler =
      (funcptr_NS)cached_non_secure_reset_handler;

  /* The secure SysTick must not interrupt while NonSecure owns the CPU. */
  HAL_SuspendTick();
  Secure_Trace("[SECURE] jumping with cached NonSecure vectors\r\n");
  non_secure_reset_handler();

  /* A Reset_Handler is not allowed to return. */
  Secure_Trace("[SECURE] ERROR: NonSecure returned unexpectedly\r\n");
  Error_Handler();
}

void Secure_FaultTrace(const char *fault_name)
{
  uint32_t msp_ns;
  uint32_t psp_ns;
  const uint32_t *stack_ns;

  Secure_Trace("[SECURE-FAULT] ");
  Secure_Trace(fault_name);
  Secure_Trace("\r\n");
  Secure_TraceHex("[SECURE-FAULT] CFSR = ", SCB->CFSR);
  Secure_TraceHex("[SECURE-FAULT] HFSR = ", SCB->HFSR);
  Secure_TraceHex("[SECURE-FAULT] SFSR = ", SCB->SFSR);
  Secure_TraceHex("[SECURE-FAULT] SFAR = ", SCB->SFAR);

  /* A NonSecure configurable fault is escalated here while BFHFNMINS is 0. */
  Secure_TraceHex("[NS-FAULT] CFSR_NS = ", SCB_NS->CFSR);
  Secure_TraceHex("[NS-FAULT] HFSR_NS = ", SCB_NS->HFSR);
  Secure_TraceHex("[NS-FAULT] MMFAR_NS = ", SCB_NS->MMFAR);
  Secure_TraceHex("[NS-FAULT] BFAR_NS = ", SCB_NS->BFAR);
  Secure_TraceHex("[NS-FAULT] SHCSR_NS = ", SCB_NS->SHCSR);

  msp_ns = __TZ_get_MSP_NS();
  psp_ns = __TZ_get_PSP_NS();
  Secure_TraceHex("[NS-FAULT] MSP_NS = ", msp_ns);
  Secure_TraceHex("[NS-FAULT] PSP_NS = ", psp_ns);

  /* ThreadX threads run on PSP_NS. Dump both possible Cortex-M stack layouts:
   * basic frame PC/LR at words 6/5, extended FP frame PC/LR at words 24/23. */
  if ((psp_ns >= SRAM2_AXI_BASE_NS) &&
      (psp_ns <= ((SRAM2_AXI_BASE_NS + 0x00100000U) - (26U * sizeof(uint32_t)))))
  {
    stack_ns = (const uint32_t *)psp_ns;
    Secure_TraceHex("[NS-FAULT] basic LR = ", stack_ns[5]);
    Secure_TraceHex("[NS-FAULT] basic PC = ", stack_ns[6]);
    Secure_TraceHex("[NS-FAULT] basic xPSR = ", stack_ns[7]);
    Secure_TraceHex("[NS-FAULT] FP-frame LR = ", stack_ns[23]);
    Secure_TraceHex("[NS-FAULT] FP-frame PC = ", stack_ns[24]);
    Secure_TraceHex("[NS-FAULT] FP-frame xPSR = ", stack_ns[25]);
  }
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @param None
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
