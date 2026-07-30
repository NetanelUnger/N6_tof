/**
  ******************************************************************************
  * @file    debug_uart.c
  * @brief   Blocking debug output through the NUCLEO ST-LINK VCP.
  ******************************************************************************
  *
  * USART1 TX/RX are connected to the on-board ST-LINK through PE5/PE6.
  * This small logger deliberately owns and initializes those pins itself so
  * that boot and USB failures can be reported without depending on USBX.
  */

#include "debug_uart.h"

#include <stdarg.h>
#include <stdio.h>

#include "main.h"

#define DEBUG_UART_LINE_SIZE    (256U)
#define DEBUG_UART_TIMEOUT_MS   (100U)

static UART_HandleTypeDef debug_uart_handle;
static volatile uint32_t debug_uart_ready;
static volatile uint32_t debug_uart_dropped_messages;

static void Debug_UART_RawString(const char *message)
{
  uint32_t timeout;

  while ((message != NULL) && (*message != '\0'))
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

void Debug_UART_StartupTrace(uint32_t stage)
{
  switch (stage)
  {
    case 1U:
      Debug_UART_RawString("[NS-STARTUP] Reset_Handler entered\r\n");
      break;
    case 2U:
      Debug_UART_RawString("[NS-STARTUP] SystemInit returned\r\n");
      break;
    case 3U:
      Debug_UART_RawString("[NS-STARTUP] .data initialized\r\n");
      break;
    case 4U:
      Debug_UART_RawString("[NS-STARTUP] .bss initialized\r\n");
      break;
    case 5U:
      Debug_UART_RawString("[NS-STARTUP] calling main\r\n");
      break;
    default:
      Debug_UART_RawString("[NS-STARTUP] unknown stage\r\n");
      break;
  }
}

void Debug_UART_StartupFault(uint32_t fault_code)
{
  switch (fault_code)
  {
    case 1U:
      Debug_UART_RawString("[NS-FAULT] HardFault\r\n");
      break;
    case 2U:
      Debug_UART_RawString("[NS-FAULT] MemManage\r\n");
      break;
    case 3U:
      Debug_UART_RawString("[NS-FAULT] BusFault\r\n");
      break;
    case 4U:
      Debug_UART_RawString("[NS-FAULT] UsageFault\r\n");
      break;
    case 5U:
      Debug_UART_RawString("[NS-FAULT] SecureFault\r\n");
      break;
    default:
      Debug_UART_RawString("[NS-FAULT] unknown fault\r\n");
      break;
  }
}

int32_t Debug_UART_Init(void)
{
  GPIO_InitTypeDef gpio_init = {0};
  RCC_PeriphCLKInitTypeDef peripheral_clock = {0};

  if (debug_uart_ready != 0U)
  {
    return 0;
  }

  peripheral_clock.PeriphClockSelection = RCC_PERIPHCLK_USART1;
  /* HSI is kept enabled by the FSBL and avoids relying on an unconfigured IC9. */
  peripheral_clock.Usart1ClockSelection = RCC_USART1CLKSOURCE_HSI;
  if (HAL_RCCEx_PeriphCLKConfig(&peripheral_clock) != HAL_OK)
  {
    return -1;
  }

  __HAL_RCC_GPIOE_CLK_ENABLE();
  __HAL_RCC_USART1_CLK_ENABLE();

  gpio_init.Pin = GPIO_PIN_5 | GPIO_PIN_6;
  gpio_init.Mode = GPIO_MODE_AF_PP;
  gpio_init.Pull = GPIO_PULLUP;
  gpio_init.Speed = GPIO_SPEED_FREQ_HIGH;
  gpio_init.Alternate = GPIO_AF7_USART1;
  HAL_GPIO_Init(GPIOE, &gpio_init);

  debug_uart_handle.Instance = USART1;
  debug_uart_handle.Init.BaudRate = DEBUG_UART_BAUDRATE;
  debug_uart_handle.Init.WordLength = UART_WORDLENGTH_8B;
  debug_uart_handle.Init.StopBits = UART_STOPBITS_1;
  debug_uart_handle.Init.Parity = UART_PARITY_NONE;
  debug_uart_handle.Init.Mode = UART_MODE_TX_RX;
  debug_uart_handle.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  debug_uart_handle.Init.OverSampling = UART_OVERSAMPLING_16;
  debug_uart_handle.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  debug_uart_handle.Init.ClockPrescaler = UART_PRESCALER_DIV1;
  debug_uart_handle.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;

  if (HAL_UART_Init(&debug_uart_handle) != HAL_OK)
  {
    return -2;
  }

  if (HAL_UARTEx_SetTxFifoThreshold(&debug_uart_handle,
                                    UART_TXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    return -3;
  }

  if (HAL_UARTEx_SetRxFifoThreshold(&debug_uart_handle,
                                    UART_RXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    return -4;
  }

  if (HAL_UARTEx_DisableFifoMode(&debug_uart_handle) != HAL_OK)
  {
    return -5;
  }

  debug_uart_ready = 1U;
  return 0;
}

int32_t Debug_UART_Write(const void *buffer, size_t length)
{
  const uint8_t *data = (const uint8_t *)buffer;

  if ((buffer == NULL) || (length == 0U))
  {
    return 0;
  }

  if (debug_uart_ready == 0U)
  {
    return -1;
  }

  while (length != 0U)
  {
    uint16_t chunk = (length > UINT16_MAX) ? UINT16_MAX : (uint16_t)length;

    if (HAL_UART_Transmit(&debug_uart_handle, (uint8_t *)data, chunk,
                          DEBUG_UART_TIMEOUT_MS) != HAL_OK)
    {
      debug_uart_dropped_messages++;
      return -2;
    }

    data += chunk;
    length -= chunk;
  }

  return 0;
}

void Debug_UART_Log(const char *component, const char *format, ...)
{
  char line[DEBUG_UART_LINE_SIZE];
  const char *name = (component != NULL) ? component : "APP";
  int prefix_length;
  int body_length;
  size_t used;
  va_list arguments;

  if ((debug_uart_ready == 0U) || (format == NULL))
  {
    return;
  }

  prefix_length = snprintf(line, sizeof(line), "[%010lu][%s] ",
                           (unsigned long)HAL_GetTick(), name);
  if ((prefix_length < 0) || ((size_t)prefix_length >= sizeof(line)))
  {
    debug_uart_dropped_messages++;
    return;
  }

  va_start(arguments, format);
  body_length = vsnprintf(&line[prefix_length],
                          sizeof(line) - (size_t)prefix_length,
                          format, arguments);
  va_end(arguments);

  if (body_length < 0)
  {
    debug_uart_dropped_messages++;
    return;
  }

  used = (size_t)prefix_length + (size_t)body_length;
  if (used >= (sizeof(line) - 2U))
  {
    used = sizeof(line) - 3U;
  }

  line[used++] = '\r';
  line[used++] = '\n';
  line[used] = '\0';

  (void)Debug_UART_Write(line, used);
}

uint32_t Debug_UART_GetDroppedMessages(void)
{
  return debug_uart_dropped_messages;
}
