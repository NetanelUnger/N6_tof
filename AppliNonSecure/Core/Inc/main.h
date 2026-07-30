/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.h
  * @brief          : Header for main.c file.
  *                   This file contains the common defines of the application.
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

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "stm32n6xx_hal.h"

#include "stm32n6xx_ll_ucpd.h"
#include "stm32n6xx_ll_bus.h"
#include "stm32n6xx_ll_cortex.h"
#include "stm32n6xx_ll_rcc.h"
#include "stm32n6xx_ll_system.h"
#include "stm32n6xx_ll_utils.h"
#include "stm32n6xx_ll_pwr.h"
#include "stm32n6xx_ll_gpio.h"
#include "stm32n6xx_ll_dma.h"

#include "secure_nsc.h" /* For export Non-secure callable APIs */
#include "stm32n6xx_ll_exti.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

#include "stm32n6xx_nucleo_usbpd_pwr.h"

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* USER CODE BEGIN EC */

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

/* Exported functions prototypes ---------------------------------------------*/
void Error_Handler(void);
void MX_USB1_OTG_HS_PCD_Init(void);

/* USER CODE BEGIN EFP */

/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/
#define TOF_SDA_Pin GPIO_PIN_1
#define TOF_SDA_GPIO_Port GPIOC
#define SPI_CLK_Pin GPIO_PIN_15
#define SPI_CLK_GPIO_Port GPIOE
#define SPI_RDY_Pin GPIO_PIN_9
#define SPI_RDY_GPIO_Port GPIOE
#define CHIP_EN_Pin GPIO_PIN_10
#define CHIP_EN_GPIO_Port GPIOE
#define TOF_SCL_Pin GPIO_PIN_9
#define TOF_SCL_GPIO_Port GPIOH
#define BOOT_Pin GPIO_PIN_5
#define BOOT_GPIO_Port GPIOD
#define TOF_XSHUT_Pin GPIO_PIN_8
#define TOF_XSHUT_GPIO_Port GPIOD
#define TOF_INT_Pin GPIO_PIN_9
#define TOF_INT_GPIO_Port GPIOD
#define SPI_MISO_Pin GPIO_PIN_1
#define SPI_MISO_GPIO_Port GPIOG
#define SPI_CS_Pin GPIO_PIN_3
#define SPI_CS_GPIO_Port GPIOA
#define SPI_MOSI_Pin GPIO_PIN_2
#define SPI_MOSI_GPIO_Port GPIOG

/* USER CODE BEGIN Private defines */

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
