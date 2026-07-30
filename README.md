# STM32N657 ToF, USB CDC, and ST67W611M1 Project

This document explains the architecture, STM32CubeMX configuration, post-generation changes, RTOS tasks, build and programming flow, debugging strategy, and current engineering status of the project.

The goal is not only to describe how to run the firmware, but also to explain why it is structured this way and how to reason about failures.

## 1. Hardware and project goals

The project combines:

- NUCLEO-N657X0-Q with an STM32N657X0H3Q MCU.
- X-NUCLEO-53L9A1 with a VL53L9CX Time-of-Flight sensor.
- X-NUCLEO-67W61M1 with an ST67W611M1 Wi-Fi + BLE network coprocessor.
- USB Device CDC ACM for a fast terminal, an ANSI color depth map, and a command-line interface.
- USART1 through the on-board ST-LINK Virtual COM Port for boot and fault diagnostics that remain available even when USB fails.

Current status:

| Feature | Status |
|---|---|
| Boot from external NOR Flash | Working |
| BootROM → FSBL → Secure → Non-Secure | Working |
| VL53L9CX initialization | Working |
| Full 54×42 depth frames | Working |
| I3C DMA acquisition | Implemented as a callback/event-driven steady-state pipeline; awaiting post-Generate hardware verification |
| ANSI color-map renderer | Implemented |
| ST-LINK UART at 115200 baud | Working |
| USB CDC | Working; COM7 with a manager task, independent RX/TX workers, callback-driven TX, and fixed static slots |
| ST67 Wi-Fi/BLE | Driver and dedicated task are present, but intentionally disabled because the shield is not currently installed |
| BLE OTA | Not implemented yet |

### 1.1 Repository layout and local reference material

The `project` directory is the intended Git repository root. Generated Debug
and Release directories, signed Flash images, downloaded SDK archives, PDFs,
and local backups are excluded by `.gitignore`.

The complete downloaded packages and reference files are retained locally
under `.local-dependencies`:

- `sdk` — complete extracted X-CUBE packages.
- `downloads` — original ZIP archives.
- `reference` — datasheets and the official CDC comparison project.
- `backups` — local project archives such as `backup1.zip`.
- `diagnostics` — temporary investigation files and build logs.

That directory is not required after cloning. The exact ST67 network-driver
source used by the build is vendored under `ThirdParty/ST67W6X_Network_Driver`
together with its license, so the repository remains self-contained even
while the radio feature is disabled.

## 2. Four execution contexts and TrustZone

This is not a single binary that runs directly after Reset. The CubeMX project is a Secure/Non-Secure project with four contexts:

1. FSBL — First Stage Boot Loader.
2. AppliSecure — configures TrustZone, RIF, and RISAF.
3. AppliNonSecure — runs ThreadX, ToF, USBX, USB-PD, the CLI, and eventually the ST67 application.
4. ExtMemLoader — allows STM32CubeProgrammer to access the external NOR device.

~~~mermaid
flowchart TD
    A["Reset / BootROM"] --> B["FSBL @ 0x70000000"]
    B --> C["Initialize XSPI2 and map external NOR"]
    C --> D["Load Secure image @ 0x70100000"]
    C --> E["Load Non-Secure image @ 0x70180000"]
    D --> F["AppliSecure: TrustZone, RIF, RISAF"]
    F --> G["Jump to the Non-Secure Reset_Handler"]
    G --> H["HAL, GPIO, DMA, I3C, SPI, and UCPD initialization"]
    H --> I["ThreadX scheduler"]
    I --> J["ToF, USBX, USB-PD, CLI, optional ST67"]
~~~

### 2.1 Why an FSBL is required

The application images are stored in external NOR Flash. The FSBL:

- Initializes XSPI2.
- Maps the external NOR into the STM32 address space.
- Reads the STM32 signed-image headers.
- Copies the Secure and Non-Secure images into their execution regions.
- Synchronizes and disables caches before handing over control.
- Starts the Secure application.

### 2.2 Why AppliSecure is required

TrustZone divides the MCU into Secure and Non-Secure worlds. AppliSecure:

- Defines which SRAM regions are accessible from Non-Secure state.
- Programs RISAF and RIF access control.
- Releases required peripherals and GPIOs to Non-Secure.
- Preserves the Non-Secure MSP and Reset_Handler values before RISAF changes make the normal alias unreadable in this configuration.
- Performs the final state transition into the Non-Secure Reset_Handler.

A mistake in these permissions may look like an ordinary HardFault even though the real cause is a TrustZone access violation.

## 3. External Flash image map

| Image | Programming address | Purpose |
|---|---:|---|
| N6_FSBL-trusted.bin | 0x70000000 | Boot loader and external-memory setup |
| N6_AppliSecure-trusted.bin | 0x70100000 | TrustZone and system isolation |
| N6_AppliNonSecure-trusted.bin | 0x70180000 | Main application |

Each image receives an STM32 image header version 2.3 through STM32_SigningTool_CLI. The current development flow uses the -nk option, which creates the required FSBL image format without a private signing key. This is appropriate for bring-up, but it is not a production secure-boot chain.

## 4. Important N6.ioc settings

The CubeMX source of truth is [N6.ioc](N6.ioc).

### 4.1 MCU and project structure

- MCU: STM32N657X0H3Q in a VFBGA264 package.
- STM32Cube package: STM32Cube FW_N6 V1.4.0.
- Toolchain: STM32CubeIDE with GCC.
- Project type: SecureNSecure.
- Contexts: FSBL, AppliSecure, AppliNonSecure, and ExtMemLoader.
- KeepUserCode is enabled.
- Main ThreadX application pool: 192 KiB.

### 4.2 Clock configuration

- CPU clock calculation: up to 600 MHz.
- AXI clock: 400 MHz.
- I3C1 kernel clock: 200 MHz.
- USB OTG HS1 receives an accurate 48 MHz clock directly from HSE.
- SPI5 receives a 60 MHz kernel clock.
- Configured SPI5 transfer rate: approximately 30 Mbit/s.

USB requires a precise 48 MHz reference. A running CPU does not imply that the USB clock is correct.

### 4.3 VL53L9CX through I3C1

| Signal | Pin | Configuration |
|---|---|---|
| TOF_SDA | PC1 | I3C1_SDA, Controller |
| TOF_SCL | PH9 | I3C1_SCL, Controller |
| TOF_XSHUT | PD8 | GPIO output, initially High |
| TOF_INT | PD9 | Falling-edge EXTI, no pull |

I3C is configured for approximately 12.5 MHz push-pull operation and 2.5 MHz open-drain operation.

Relevant GPDMA1 channels:

- Channel 0 — I3C1 Transfer Control.
- Channel 1 — I3C1 RX.
- Channel 2 — I3C1 TX.

The ToF interrupt on PD9 and the ST67 SPI_RDY signal on PE9 share EXTI line 9,
so the STM32 cannot route both pins through EXTI at the same time. In the
current hardware state the radio is absent and disabled: PD9 owns EXTI9 with a
falling-edge trigger, PE9 is a plain input, and the ToF ISR only posts a
ThreadX event. If the radio is enabled later, this ownership must be redesigned
or the sensor must use I3C IBI; simply enabling both interrupt paths is invalid.

### 4.4 ST67W611M1 through SPI5

| Signal | Pin | Configuration |
|---|---|---|
| SPI_CLK | PE15 | SPI5_SCK |
| SPI_MISO | PG1 | SPI5_MISO |
| SPI_MOSI | PG2 | SPI5_MOSI |
| SPI_CS | PA3 | GPIO output |
| CHIP_EN | PE10 | GPIO output |
| BOOT | PD5 | GPIO output |
| SPI_RDY | PE9 | Rising/falling EXTI |

SPI5 remains generated by CubeMX, but when APP_ST67W6X_ENABLED is 0:

- The ST67 task is not created.
- The FreeRTOS compatibility layer is not initialized.
- W6X_Init and all radio hardware initialization are skipped.
- The unused PE9 interrupt source is disabled.

### 4.5 USB CDC and USB-PD

- PH0/PH1 are assigned to the FSBL as the 48 MHz HSE digital-bypass input.
- The FSBL must leave HSE running because USBPHY1 uses HSE/2 and OTGHS1 uses
  the direct HSE reference.
- USB1_OTG_HS is configured as a High-Speed Device with the embedded PHY.
- OTG1_HSDP and OTG1_HSDM belong to the Non-Secure context.
- USBX includes Device Core, Device Controller, and CDC ACM.
- Product string: STM32N6 VL53L9CX ToF.
- Serial string: N6TOF001.
- CDC data endpoint: EP1.
- CDC command endpoint: EP2.
- UX_SLAVE_REQUEST_DATA_MAX_LENGTH: 512 bytes.
- USBX byte pool in the IOC: 32 KiB.
- CDC ACM transmission mode is enabled (`UX_DEVICE_CLASS_CDC_ACM_TRANSMISSION_DISABLE=0`), allowing USBX read/write completion callbacks.
- UCPD1 and USB-PD are configured as a Type-C Sink on CN8.
- The build uses USBPDCORE_LIB_NO_PD: Type-C cable detection is present, but a full USB Power Delivery protocol engine is not enabled.

The board's TCPP0203 protects the Type-C path and measures VBUS. It requires I2C2, ADC12, UCPD1, and several GPIOs to be accessible from the Non-Secure application.

### 4.6 CubeMX warnings seen during generation

Warnings about free pins that are not assigned to a context, and GPIO pins changed into EXTI mode, are related to the multi-context project and shared pins. They are not automatically fatal.

After every Generate Code operation, verify:

- FSBL `SystemClock_Config()` contains `RCC_HSE_BYPASS_DIGITAL`, not
  `RCC_HSE_OFF`.
- ToF pins still belong to AppliNonSecure.
- USB1 and UCPD1 interrupts still target Non-Secure.
- USER CODE blocks were preserved.
- Custom stack sizes did not return to their small defaults.
- The manual OS_CAD_STACK_SIZE mapping described later was not overwritten.
- The shared HAL directory still contains the modules needed by every context,
  especially BSEC, XSPI, ADC, UART, and USB.
- The Non-Secure STM32CubeIDE project still links `stm32n6xx_hal_uart.c` and
  `stm32n6xx_hal_uart_ex.c` and includes the STM32N6xx_Nucleo BSP directory.

## 5. What was added after Generate Code

CubeMX generated the hardware and middleware skeleton. Most application behavior was added afterward.

### 5.1 VL53L9CX integration

Components imported from X-CUBE-53L9A1 include:

- The sensor driver under AppliNonSecure/Drivers/BSP/Components/vl53l9.
- The interface and platform utilities under AppliNonSecure/Utilities/vl53l9-common.
- media-object and vl53l9-transform-c under AppliNonSecure/Middlewares/ST.
- A custom STM32N6 platform layer for I3C1, DMA, XSHUT, and INT.
- tof_app.c and tof_app.h for initialization, acquisition, transform, metadata parsing, status, and ANSI rendering.

The current profile is VL53L9_USECASE_AR_PRECISION. The sensor is explicitly
configured for autonomous synchronization with a 100,000 microsecond frame
period, which is the VL53L9CX maximum of 10 fps at the reported 54×42
resolution. I3C1 already runs at its configured 12.5 MHz push-pull limit and
the CPU remains at 600 MHz; neither interface is overclocked.

The steady-state pipeline has no frame allocation and no I3C polling loop.
Three fixed 14,842-byte raw slots move between a free queue and a ready queue.
The acquisition task owns the sensor and I3C bus; the processing task owns the
transform and renderer. If processing falls behind, the oldest unclaimed raw
frame is discarded so the displayed image remains recent.

~~~mermaid
sequenceDiagram
    participant S as VL53L9CX
    participant A as ToF acquisition task
    participant D as I3C1 + GPDMA1
    participant Q as Static raw-slot queues
    participant P as ToF processing task
    participant U as Static USB map slot
    S-->>A: PD9 falling-edge INT
    A->>Q: Take free 14,842-byte slot
    A->>D: Start combined register-address + frame DMA
    D-->>A: Multiple-transfer completion callback / event flag
    A->>D: DMA command writes and DSS/status reads
    D-->>A: TX/RX completion callbacks / event flags
    A->>Q: Publish slot index
    Q-->>P: Ready slot index
    P->>P: Transform, parse metadata, render ANSI map
    P->>U: Render directly into one 48 KiB TX slot
    P->>Q: Return raw slot
~~~

### 5.2 ThreadX and memory sizing

Additional tasks are created in app_threadx.c and controlled by feature flags in app_features.h.

The Non-Secure Debug C and C++ code is compiled with `-O3` while retaining
debug symbols. At `-O0`, one complete VL53L9 transform took about 264 ms in the
measured UART trace, so a sequential loop could not reach 10 fps even though
the sensor profile requested it. Autonomous ranging overlaps the next sensor
acquisition with the current CPU transform, and `-O3` removes the dominant
software bottleneck.

The processing task stack is 96 KiB. The separate acquisition task has a
16 KiB stack and priority 7, so DMA completion and frame acknowledgement are
not delayed by the transform. GCC `-fstack-usage` reports very large frames in two
library functions, but control-flow analysis is essential: `compute_norm_maps`
is bypassed because this configuration enables rate-normalization `fast_mode`,
and the bicubic-resize calibration path is skipped at the native 54×42
resolution. The largest visible active chain is the optimized sharpener at
about 34 KiB, before its callers and exception/FPU context. A 96 KiB stack
therefore retains generous margin.

The ThreadX application pool remains 192 KiB. An attempted 320 KiB ToF stack
inside a 384 KiB pool consumed so much static SRAM that the transform's first
frame could not complete its dynamic allocations and returned
`MEDIA_ERROR_UNKNOWN` (`-14`). Stack and heap requirements must be budgeted
together; a larger task stack is not automatically safer for the whole system.

The USBX device-control stack is currently 16 KiB and the USBX pool is 32 KiB. The 16 KiB value was introduced as a conservative bring-up value during the initial fault investigation. Later address mapping proved that the observed STKOF was in the USB-PD CAD task, not the USBX task. Therefore, this larger USBX stack is not evidence of an ST USBX defect.

The USB-PD CAD stack was increased from 1 KiB to 8 KiB and its pool from 5000 bytes to 16 KiB. On cable attachment the CAD path executes:

~~~text
BSP_USBPD_PWR_VBUSInit
  → PWR_TCPP0203_Configure_ADC
    → HAL_RCCEx_PeriphCLKConfig
~~~

In the Debug build, this call chain exceeds the original 1 KiB stack.

### 5.3 USB CDC console and CLI

The CDC application is split into a control plane and a data plane:

- `app_usbx_device.c` owns the USB lifecycle. Its manager task receives Type-C
  START/STOP, CDC activate/deactivate, line-parameter, RX-error, and TX-error
  events through a two-word ThreadX queue.
- `usb_cdc_transport.c/.h` owns the CDC data plane, including a dedicated RX
  dispatcher, a dedicated TX callback scheduler, separate pointer queues,
  session control, counters, and fixed statically allocated slots.
- `app_console.c/.h` is a thin producer/consumer facade. It never executes a
  USBX transfer directly.
- `debug_cli.c/.h` parses terminal input received from the RX delivery queue
  and writes responses through the static control-message slots.

USBX owns the physical bulk-OUT receive loop in callback transmission mode.
The USBX read callback copies each completed transfer into one static RX slot
and only posts its pointer to the ingress queue. The RX dispatcher moves valid,
session-matching slots to the application delivery queue. The TX scheduler is
the only application task that submits `write_with_callback`; it waits on a
completion semaphore and cannot submit the next buffer until the USBX callback
reports the previous transfer's status and actual length.

~~~mermaid
flowchart LR
    PD["USB-PD CAD"] -->|START / STOP| M["USB manager task"]
    C["USBX CDC callbacks"] -->|activate / deactivate / error| M
    M -->|session active / idle| RXW["USB RX worker"]
    M -->|session active / idle| TXW["USB TX worker"]
    H["USB host OUT"] -->|USBX read callback| RS["16 static RX slots, 512 B each"]
    RS --> RXW
    RXW --> RQ["RX delivery queue: 16 pointers"]
    RQ --> CLI["CLI consumer"]
    TOF["ToF map producer"] -->|render in place| MS["2 static map slots, 48 KiB each"]
    CLI --> CS["8 static control slots, 768 B each"]
    MS --> TQ["TX queue: 10 pointers"]
    CS --> TQ
    TQ --> TXW
    TXW -->|write_with_callback| H2["USB host IN"]
    H2 -->|completion callback + semaphore| TXW
~~~

There is no CDC packet byte pool, heap allocation, or variable-size allocation
in the data path. TX has eight 768-byte control slots and two 48 KiB map slots;
RX has sixteen 512-byte slots. Semaphore counts provide backpressure and the
bounded pointer queues transfer ownership. The ToF renderer writes directly
into a reserved map slot, eliminating the previous full-frame copy. Each slot
also carries a session number, so detach/reconnect invalidates old work safely.
Queue-full, slot-exhaustion, callback-completion, partial-transfer, byte, and
error counters are visible through `usb status`.

The worker ThreadX objects are created once during RTOS initialization. The USB
manager starts and stops their data plane with event flags instead of repeatedly
creating and deleting RTOS objects. During disconnect both workers become idle,
all queued packets are released, the CDC instance is invalidated, and only then
is the PCD/USBX stack torn down. This avoids heap fragmentation and eliminates
use-after-deinit races.

The USBX device-control task now follows the event ordering in ST's official example: it waits on its queue until the USB-PD CAD path reports a real Type-C attachment. Only then does it initialize the PCD, initialize the USBX Device stack, and start the peripheral. The earlier CAD-independent fixed START was useful while cable detection was under investigation, but it was removed after CC2 attachment was proven to work.

The latest hardware trace confirmed that UCPD detects CN8 attachment on CC2 and delivers the expected Device START event. The next failure was localized to `HAL_PCD_Init`: the generated clock/VDDUSB setup alone did not release the STM32N6 USB HS core from its complete reset and PHY configuration sequence.

The project now carries the additional board-specific sequence used by ST's official NUCLEO-N657X0-Q `Ux_Device_CDC_ACM` application. It:

- Resets the OTG1 PHY controller, OTG1 core, and OTGPHY1 blocks.
- Selects HSE/2 for the PHY reference path.
- Programs `USB1_HS_PHYC->USBPHYC_CR` for the 24 MHz input used on this board.
- Releases PHY reset, waits for stabilization, and then releases the USB core reset.
- Configures the Rx and endpoint Tx FIFOs. EP1 is deliberately enlarged from
  the official example's 0x10 words to 0x100 words so it can hold complete
  512-byte High-Speed CDC packets in non-DMA mode.

These additions live in CubeMX `USER CODE` blocks. The reset, clock, PHY, and
power sequence is a direct port of the initialization that ST itself adds
manually to its board example. The EP1 Tx FIFO is the documented exception:
its size is corrected for the example's 512-byte High-Speed packet descriptor.

The FSBL also enables VDDA, VDDIO2 through VDDIO5, and VDDUSB before `HAL_Init()`, matching the power-domain ordering in the official CDC example. These system supply-valid settings remain active through the Secure and Non-Secure handovers. The Non-Secure PCD handle is cleared before every attach-cycle initialization, matching the official example and preventing stale HAL state from surviving a USB STOP/START cycle.

Available CLI commands:

| Command | Action |
|---|---|
| help, menu, ? | Show help |
| status | Show a system summary |
| usb status | Show CDC session, static-slot usage, queues, callback completions, flow control, and errors |
| map on / map off | Show or hide the depth map |
| tof status | Show ToF state, rate, and range |
| tof pause / tof resume | Stop or restart the autonomous ranging stream |
| debug off/error/warn/info/debug | Change ST67 log verbosity |
| clear | Clear the terminal |
| reboot yes | Reset the MCU |

Pressing Enter while the map is visible switches to console mode and hides the map without stopping acquisition.

### 5.4 ST67 Wi-Fi and BLE

The x-cube-st67w61 driver was integrated together with:

- wifi_ble_app.c/.h — dedicated application task.
- spi_port.c and board-specific transport configuration.
- A small FreeRTOS-to-ThreadX compatibility layer required by the vendor driver.
- Wi-Fi, IP, BLE connection, and error callbacks.
- Future CLI commands for scan, connect, and BLE advertising.

The module is currently disabled in AppliNonSecure/Core/Inc/app_features.h:

~~~c
#define APP_ST67W6X_ENABLED  (0U)
~~~

Do not set it to 1 until the shield is physically attached and the SPI, boot, and shared EXTI wiring have been verified.

BLE OTA is not implemented. A safe design will require an inactive image slot, chunk bounds checking, a cryptographic hash/signature, version policy, atomic activation, and rollback.

### 5.5 Independent ST-LINK UART diagnostics

debug_uart.c/.h initializes USART1 on PE5/PE6 at 115200, 8-N-1.

The UART does not depend on USBX and therefore reports:

- FSBL progress.
- Secure and TrustZone progress.
- Non-Secure startup milestones.
- Peripheral and RTOS initialization.
- ToF, USBX, USB-PD, and radio messages.
- Fault status registers and saved processor state.

Example:

~~~text
[0000000742][TOF] VL53L9CX ready: 54x42, target=10 fps
~~~

The first field is HAL_GetTick in milliseconds since Non-Secure startup.

### 5.6 Boot and fault diagnostics

Added diagnostics include:

- Image magic, signed size, and vectors in the FSBL.
- The exact number of copied Non-Secure bytes.
- Secure and Non-Secure vector reads before isolation.
- Cached Non-Secure vectors before RISAF changes.
- Non-Secure startup messages around SystemInit, data initialization, BSS initialization, and main.
- CFSR, HFSR, SFSR, SFAR, MSP, PSP, LR, PC, and xPSR fault output.

CFSR_NS = 0x00100000 means STKOF on Cortex-M55. The value 0xEFEFEFEF is the ThreadX stack-fill pattern. Seeing PC or LR become 0xEFEFEFEF strongly suggests that a stack boundary was crossed.

### 5.7 Build and programming tools

- Tools/build_and_sign.ps1 builds FSBL, Secure, and Non-Secure, then creates version 2.3 trusted images.
- Tools/program_flash.ps1 programs and verifies the three images in external NOR.

## 6. Changes outside CubeMX USER CODE

Not every edit outside USER CODE is automatically dangerous. There are three categories:

1. A CubeMX-managed file edited outside a USER block — Generate Code may overwrite it.
2. A manually imported vendor/demo file — CubeMX normally does not own it, even though it has no USER blocks.
3. Vendor middleware copied into the project and modified locally — CubeMX may replace it if middleware is regenerated or recopied.

### 6.1 Confirmed CubeMX-managed edits outside USER CODE

| File | Change | Reason | Generate risk |
|---|---|---|---|
| AppliNonSecure/USBPD/App/usbpd_dpm_core.c | OS_CAD_STACK_SIZE uses N6_USBPD_CAD_STACK_SIZE | Fix demonstrated CAD stack overflow | High: CubeMX may restore 1024 |
| AppliNonSecure/USBPD/App/usbpd_dpm_core.c | UCPD register logs, wake counter, 250 ms fallback polling | Cable-detection bring-up | High |
| AppliNonSecure/Core/Startup/startup_stm32n657x0hxq.s | Calls Debug_UART_StartupTrace | Earliest possible Non-Secure breadcrumbs | High |
| FSBL/Core/Src/extmem.c | BOOT_GetApplicationSize override | Copy the exact header + payload size | High |
| AppliSecure/Core/Src/main.c | One trace call between generated initialization calls | Diagnostic only | Medium |
| FSBL/Core/Inc/stm32n6xx_hal_conf.h | Re-enable BSEC and XSPI modules | Multi-context Generate removed modules still required by the custom FSBL | High |
| AppliNonSecure/.cproject | Add STM32N6xx_Nucleo BSP include path | Generated `main.h` includes the USB-PD BSP header, but CubeMX omitted its directory | High |
| AppliNonSecure/.cproject | Set Debug C/C++ optimization to `-O3` | Make the 54×42 transform fast enough for the 10 fps pipeline while keeping debug symbols | High: CubeMX/IDE configuration changes can restore `-O0` |
| AppliNonSecure/.project | Link HAL UART and UART-extended sources | The custom ST-LINK VCP logger uses HAL UART although USART1 is not a generated Non-Secure peripheral | High |

Most functional Secure changes, RIF releases, cached-vector logic, USBX task changes, stack overrides, and additional ThreadX tasks are inside USER CODE blocks.

### 6.2 Imported/demo files intentionally changed outside USER CODE

The X-CUBE-53L9A1 platform files are not CubeMX-generated project files. They were ported from the H563 demo to N657:

- STM32H5 HAL headers changed to STM32N6 headers.
- H563 pin names changed to this project's ToF pins.
- I3C timing values changed for the N657 clock tree.
- EXTI line 9 handling changed for PD9/PE9 sharing. PD9 currently owns the
  falling-edge interrupt because the radio is disabled.
- Bare-metal event polling changed to ThreadX event flags posted directly by
  GPIO, I3C TX, I3C RX, multiple-transfer, and error callbacks.
- Asynchronous I3C descriptors and control/status buffers were moved from
  automatic stack storage to a persistent single-transfer context.
- Register reads now use one combined address-write/repeated-start/read DMA
  transaction, and command writes use I3C TX DMA.
- The vendor's two-part frame API was supplemented with stage-level asynchronous
  entry points so DSS mapping, DSS data, status, and acknowledgement no longer
  execute blocking HAL calls inside the acquisition loop.
- The board name and debug GPIO assumptions were changed.

These are required platform adaptations, not evidence that the original H563 demo is wrong.

### 6.3 Vendor files changed only for diagnostics

- FSBL/Middlewares/ST/STM32_ExtMem_Manager/boot/stm32_boot_lrun.c contains additional copy/cache logs.
- Drivers/BSP/STM32N6xx_Nucleo/stm32n6xx_nucleo_usbpd_pwr.c contains additional TCPP0203/I2C logs.
- Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_pcd.c contains temporary stage logs around MSP, core reset, Device-mode selection, and device initialization.
- Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_ll_usb.c contains temporary `USB_CoreReset` register and timeout logs. These are compiled only for the Non-Secure ThreadX application.

The copy algorithm, TCPP0203 component driver, ADC logic, and STM32 USB-PD CAD hardware layer were not otherwise changed.

## 7. Assessment of possible ST bugs

This section deliberately separates demonstrated defects from adaptations and suspicions.

### 7.1 Strong ST bug candidate: USB-PD CAD stack is too small in Debug

The official STM32Cube FW_N6 V1.4.0 CDC example defines:

~~~c
#define OS_CAD_STACK_SIZE 1024
~~~

The measured GCC Debug stack frames in our build are:

| Function | Static frame |
|---|---:|
| USBPD_CAD_Task | 104 bytes |
| BSP_USBPD_PWR_VBUSInit | 24 bytes |
| PWR_TCPP0203_Configure_ADC | 440 bytes |
| HAL_RCCEx_PeriphCLKConfig | 488 bytes |

The visible total is already 1056 bytes, before hidden USB-PD library calls, alignment, interrupt stacking, and possible floating-point context.

Hardware evidence:

- No crash while detached.
- Cable attachment enters the VBUS/ADC path.
- CFSR_NS reports STKOF.
- PC maps to HAL_RCCEx_PeriphCLKConfig.
- LR maps back to PWR_TCPP0203_Configure_ADC.
- PSP belongs to the USB-PD byte pool.

Conclusion: 1024 bytes is not safe for the official Debug path. This is a strong ST configuration/template bug candidate. It may remain hidden in optimized Release builds.

### 7.2 Confirmed configuration bug: High-Speed CDC EP1 Tx FIFO is too small

ST's NUCLEO-N657X0-Q `Ux_Device_CDC_ACM` example configures the High-Speed CDC
bulk-IN endpoint with a 512-byte maximum packet, but assigns EP1 only 0x10
32-bit FIFO words, or 64 bytes. In non-DMA mode, `PCD_WriteEmptyTxFifo()` writes
only when `DTXFSTS` reports enough free words for one complete packet. It needs
128 words for a 512-byte packet, so the 16-word FIFO can never start a bulk-IN
transfer. Control endpoint traffic still works, which explains successful COM
enumeration followed by a permanently blocked first CDC write.

The project assigns EP1 0x100 words, or 1024 bytes, enough for two complete
High-Speed packets. Rx remains 0x200 words, EP0 Tx remains 0x10 words, and the
CDC notification EP2 Tx FIFO remains 0x20 words.

### 7.3 Confirmed source bug: missing break in X-CUBE-53L9A1 V1.0.0

The original platform_acknowledge_event function contains:

~~~c
case PLATFORM_I3C_IBI_EVT:
    g_platform_evt &= ~PLATFORM_I3C_IBI_EVT;
default:
    res = -1;
    break;
~~~

The missing break causes a successful IBI acknowledgement to fall into default and return an error. The local port adds the missing break.

This is a genuine C control-flow bug in X-CUBE-53L9A1 V1.0.0. It is not the
cause of the current acquisition path because the project uses the GPIO INT
signal to detect autonomous frames rather than I3C IBI.

### 7.4 Confirmed source bug: asynchronous I3C objects have insufficient lifetime

X-CUBE-53L9A1 V1.0.0 creates the descriptor array, `I3C_XferTypeDef` array,
control buffers, status buffers, and two-byte register-address buffer as local
variables inside `vl53l9_read_async()`. It then passes their addresses to
`HAL_I3C_Ctrl_Receive_DMA()` and returns immediately.

The STM32 HAL stores `pXferData` in `I3C_HandleTypeDef`, while the DMA transfer
continues after the caller has returned. The stack objects are therefore no
longer guaranteed to exist and may be overwritten by the ToF task's event wait
or later processing. Hardware showed the characteristic symptom: several good
frames followed by `VL53L9_ERROR_PLATFORM` while starting a later frame DMA.

The local port now uses one persistent asynchronous context because this
application deliberately permits only one in-flight ToF DMA read. Failure
logging also records the exact HAL stage, I3C state/error, both DMA states, and
the I3C event register on COM6.

### 7.5 Suspected integration issue: generated Secure handover

The generated Secure flow reads the Non-Secure vector table after SystemIsolation_Config. In this configuration, the Non-Secure alias read returned zeros after the RISAF transition, while the Secure alias contained valid vectors before isolation.

The current application caches the valid MSP and Reset_Handler before changing RISAF and then uses the cached values.

This solved a real boot failure, but it is not yet enough evidence to call it a general CubeMX defect. It may be a generator issue specific to LRun + TrustZone + this memory layout, or a mismatch in our isolation configuration.

### 7.6 Not proven to be ST bugs

- The 96 KiB ToF stack: based on the measured active `-O3` transform path plus
  margin. Unused slow rate-normalization and non-native resize paths contain
  much larger automatic arrays, but they are not executed by this profile.
- The current 16 KiB USBX control stack: conservative bring-up sizing. The demonstrated STKOF belonged to CAD, not USBX.
- The earlier fixed CDC startup independent of CAD was a temporary diagnostic workaround and has now been removed.
- The FreeRTOS compatibility layer for ST67: required because this application uses ThreadX.
- The FSBL image-size override: ST deliberately provides a weak hook; our placement should be improved, but the hook itself is not a bug.
- The earlier all-zero CC readings were not evidence of a hardware failure. After correcting the CAD task stack and allowing the complete CAD path to run, attachment is detected correctly on CC2.

## 8. RTOS tasks

In ThreadX, a smaller priority number means a higher scheduling priority.

| Task | Priority | Stack | Pool | Responsibility |
|---|---:|---:|---|---|
| USB-PD CAD | 1 | 8 KiB | USB-PD pool | CC attach/detach detection, TCPP0203 VBUS setup, USB notifications |
| ToF Acquisition | 7 | 16 KiB | TX application pool | Sensor ownership, PD9 event wait, fully asynchronous I3C DMA sequence, raw-slot publication |
| ToF Main Thread | 10 | 96 KiB | TX application pool | Raw-frame transform, metadata parsing, ANSI rendering, and raw-slot release |
| USBX Device App Main Thread | 8 | 16 KiB | USBX pool | USB lifecycle manager: PCD/USBX, CDC callbacks, worker start/stop, error events |
| USB CDC RX worker | 9 | 12 KiB | Static BSS | Dispatches callback-filled static RX slots into the application delivery queue |
| USB CDC TX worker | 9 | 12 KiB | Static BSS | Submits one static TX slot and waits for the USBX completion callback before advancing |
| ST67 WiFi BLE | 11 | 8 KiB | TX application pool | W6X, Wi-Fi station, and BLE server; currently not created |
| USB debug CLI | 12 | 6 KiB | TX application pool | CDC input, line editing, and commands |

Additional internal ThreadX and USBX tasks may be created by the middleware, such as the ThreadX timer task and USBX class tasks.

### 8.1 Byte pools

| Pool | Size | Main use |
|---|---:|---|
| tx_app_byte_pool | 192 KiB | ToF, CLI, optional ST67, compatibility objects |
| ux_device_app_byte_pool | 32 KiB | USBX system memory and USB Device task |
| usbpd_app_byte_pool | 16 KiB | CAD queue, CAD task, and USB-PD objects |

The CDC data plane does not have a byte pool. Its memory is fixed in BSS:

| Static storage | Count × size | Purpose |
|---|---:|---|
| ToF raw slots | 3 × 14,842 bytes | DMA destinations exchanged between acquisition and processing |
| CDC control TX slots | 8 × 768 bytes | CLI text and short diagnostic messages |
| CDC map TX slots | 2 × 48 KiB | Complete ANSI frames rendered in place |
| CDC RX slots | 16 × 512 bytes | Completed USB bulk-OUT payloads |

Separate pools help diagnose failures. A PSP address can be matched to a pool to identify which task was actually running.

## 9. Build, sign, and program

### 9.1 After changing N6.ioc

1. Open N6.ioc in STM32CubeMX.
2. Run Generate Code.
3. Review all warnings.
4. Inspect CubeMX-managed files that contain known outside-USER modifications.
5. Verify stack sizes, TrustZone ownership, callbacks, and feature flags.
6. Rebuild all affected contexts.

### 9.2 Build and sign

From the workspace root:

~~~powershell
powershell.exe -ExecutionPolicy Bypass -File .\project\Tools\build_and_sign.ps1
~~~

Signed images are placed in project/FlashImages.

### 9.3 Jumper positions

For programming:

- BOOT0 = 1-2.
- BOOT1 = 2-3.
- Press RESET before programming if the SWD connection fails.

For normal boot from external Flash:

- BOOT0 = 1-2.
- BOOT1 = 1-2.
- Press RESET.

### 9.4 Program external Flash

~~~powershell
powershell.exe -ExecutionPolicy Bypass -File .\project\Tools\program_flash.ps1
~~~

Full erase, only when intentionally required:

~~~powershell
powershell.exe -ExecutionPolicy Bypass -File .\project\Tools\program_flash.ps1 -FullErase
~~~

FullErase erases the entire external NOR and must not be the default action.

## 10. Terminals

### 10.1 ST-LINK UART

- Port: ST-LINK COM port; currently observed as COM6.
- Baud: 115200.
- Data: 8 bits.
- Parity: None.
- Stop: 1.
- Flow control: None.

Open this terminal before Reset. It is the primary diagnostic channel.

### 10.2 USB CDC on CN8

After successful enumeration, Windows should create a second COM port. It is not the ST-LINK COM port. The color map and CLI use this second port.

## 11. Recommended debugging order

1. Did [FSBL] entered from BootROM appear?
2. Did the FSBL find image magic 0x324D5453?
3. Did [SECURE] application entered appear?
4. Are the cached Non-Secure vectors non-zero?
5. Did [NS-STARTUP] calling main appear?
6. Did ThreadX create all byte pools and tasks?
7. Did ToF reach ready and finish its first frame?
8. Did USBX reach HAL_PCD_Start?
9. Only then investigate Windows descriptors, enumeration, and CDC.

Map valid PC and LR values against the exact ELF that was programmed:

~~~powershell
arm-none-eabi-addr2line.exe -a -f -C -e .\project\AppliNonSecure\Debug\N6_AppliNonSecure.elf 0xADDRESS
~~~

## 12. Change log

### 2026-07-30

- Added the repository-root `.gitignore` for STM32CubeIDE build output, signed
  images, local downloads, reference material, backups, and operating-system
  files.
- Moved complete X-CUBE packages, ZIP archives, PDFs, the official CDC test,
  diagnostics, and `backup1.zip` into ignored `.local-dependencies` folders.
- Vendored the 1.24 MB ST67W6X source subset actually referenced by the build
  under `ThirdParty`, retained the ST license files, and repointed the
  Non-Secure CubeIDE links/include paths. A forced full Non-Secure rebuild
  succeeded without the original extracted SDK at its old path.
- Replaced the CDC packet byte pool with deterministic static storage: eight
  768-byte control TX slots, two 48 KiB map TX slots, and sixteen 512-byte RX
  slots. Steady-state USB traffic now performs no allocation.
- Enabled USBX CDC callback transmission mode. The TX scheduler submits one
  `write_with_callback` request and waits for its completion semaphore before
  advancing; partial completions are resumed and errors are reported to the
  USB manager.
- Changed the ToF renderer to write directly into a reserved USB map slot,
  eliminating the full ANSI-frame copy.
- Split ToF into priority-7 acquisition and priority-10 processing tasks with
  three fixed 14,842-byte raw-frame slots and free/ready queues. When processing
  lags, the oldest unclaimed frame is dropped to preserve live-display latency.
- Converted the complete steady-state sensor transaction chain to asynchronous
  I3C DMA: main frame read, DSS map command, DSS read, DSS unmap, status read,
  and frame acknowledgement. Task waits use ThreadX event flags posted from TX,
  RX, multiple-transfer, GPIO, and error callbacks.
- Assigned PD9 to falling-edge EXTI in the IOC while the absent ST67 radio is
  disabled; PE9 is a plain input because both pins share EXTI line 9.
- Created and verified `backup1.zip` before modifying the USB architecture.
  The archive contains 12,353 entries and its SHA-256 is
  `3BA7A701F1E7219D1188F160A13479AB71989162C7AB5FFABC68A22C642A6A21`.
  It is now retained locally under `.local-dependencies/backups/backup1.zip`.
- Replaced the earlier CDC single-frame mailbox with a control-plane/data-plane
  architecture: one USB manager task and independent RX/TX workers.
- Expanded the manager event queue to carry Device START/STOP, CDC lifecycle,
  parameter-change, and worker-error events.
- Initially added bounded packet queues and a 64 KiB byte pool; this interim
  design was superseded the same day by the deterministic static-slot design
  described above.
- Added session-tagged packet ownership so detach/reconnect cannot deliver a
  stale packet through a newly activated CDC instance.
- Made the RX worker the only low-level CDC reader and the TX worker the only
  low-level CDC writer. Application code now interacts only through
  allocation-and-enqueue APIs.
- Changed `app_console.c` into a thin asynchronous transport facade and removed
  its old 48 KiB static mailbox, mutex set, semaphore, and 32 KiB TX task.
- Added disconnect quiescing: invalidate the CDC session, abort through USBX,
  wait for both workers to become idle, release queued packets, then deinitialize
  the USB peripheral.
- Added flow-control and diagnostic counters plus the `usb status` CLI command.
- Fixed the X-CUBE asynchronous I3C lifetime defect: DMA descriptors and their
  referenced address/control/status buffers now live in a persistent context
  rather than in a returned function's stack frame.
- Added stage-specific COM6 diagnostics for I3C asynchronous-start failures,
  including HAL status, I3C state/error, control/RX DMA states, and EVR.
- Built the Non-Secure application successfully with 0 compile errors and 0
  compile warnings. The linked image is 575,896 bytes of text, data, and BSS;
  worker stack-usage reports show 576 bytes for RX and 72 bytes for TX before
  library call depth, versus 12 KiB reserved for each worker.

### 2026-07-29

- Changed the VL53L9CX from one-shot manual triggering to autonomous ranging
  with a 100 ms frame period. Sensor acquisition now overlaps the transform and
  terminal-rendering work for the previous frame.
- Changed the Non-Secure Debug C and C++ optimization from `-O0` to `-O3`
  while retaining `-g3` debug information. The measured `-O0` transform time
  of about 264 ms was the main reason the application could not approach the
  sensor's 10 fps maximum.
- Kept I3C1 at 12.5 MHz and the STM32N657 at 600 MHz. These were already at the
  intended project limits; no bus or MCU overclock was introduced.
- Initially interpreted the largest GCC `.su` entries as one active call path
  and raised the ToF stack to 320 KiB and its pool to 384 KiB. Hardware then
  returned transform error `-14`: the oversized static allocation had starved
  the transform's dynamic heap.
- Re-audited the actual control flow. Rate-normalization `fast_mode` bypasses
  the 146,784-byte slow function, and native 54×42 calibration bypasses the
  55,400-byte resize function. The active sharpener chain is about 34 KiB, so
  the ToF stack is now 96 KiB and the application pool is again 192 KiB. This
  restores roughly 192 KiB to the C heap while retaining substantial active
  stack margin. The IOC was updated to match.
- Replaced the generic "check shield jumpers and wiring" fatal text. Transform
  error `-14` now identifies a memory/resource failure and explicitly notes
  that sensor communication had already succeeded.
- Completed a full FSBL/Secure/Non-Secure build and regenerated all three
  version 2.3 trusted images. After correcting the stack/heap balance, the
  optimized Non-Secure image links at 560,576 bytes of text, data, and BSS,
  leaving roughly 476 KiB in its 1023 KiB RAM region for the C heap and runtime
  margin.
- Confirmed successful CDC ACM enumeration as COM7 in the integrated
  Secure/Non-Secure application.
- Moved full ANSI-map transmission to a dedicated CDC TX task, following the
  official ST example's separation of USB writes from the producer task.
  USBX's direct CDC write is blocking; a slow or unopened host terminal can no
  longer stop I3C acquisition and depth transformation.
- Added a single-frame asynchronous mailbox: at most one complete 48 KiB map
  buffer is pending or in flight. New maps are dropped while USB is busy rather
  than accumulating stale frames or exhausting RAM.
- Added first-transfer UART breadcrumbs and a periodic ToF heartbeat every ten
  processed frames, making a quiet COM6 log distinguishable from a stalled
  task.
- Increased the dedicated USB CDC TX stack from 4 KiB to 32 KiB for generous
  bring-up headroom. The stack is statically allocated and does not consume the
  ThreadX application byte pool.
- Located the blocked first bulk-IN transfer in the official FIFO sizing: CDC
  EP1 advertises 512-byte High-Speed packets but was assigned only a 64-byte Tx
  FIFO. Increased EP1 from 0x10 to 0x100 words (1024 bytes), sufficient for two
  complete packets in the HAL's non-DMA transmit path.
- Confirmed ST's unmodified NUCLEO-N657X0-Q ThreadX/USBX CDC ACM example
  enumerates as COM7 on the same board, cable, connector, and PC.
- Found the decisive clock mismatch: USB selected HSE while the project FSBL
  generated `RCC_HSE_OFF`.
- Added PH0/PH1 HSE digital-bypass ownership to the FSBL in `N6.ioc`; generated
  FSBL now uses `RCC_HSE_BYPASS_DIGITAL` like ST's working example.
- Repaired post-Generate multi-context project damage: restored the official
  STM32Cube FW N6 V1.4.0 HAL driver set, re-enabled FSBL BSEC/XSPI, restored the
  Non-Secure Nucleo BSP include path, and restored HAL UART source links.
- Removed the temporary HAL/LL USB instrumentation when CubeMX regenerated the
  vendor drivers; the local HAL source tree is again the official V1.4.0 code.
- Rebuilt all three contexts successfully and regenerated all version 2.3
  trusted images.
- Programmed and verified the corrected FSBL, Secure, and Non-Secure images in
  external NOR at 0x70000000, 0x70100000, and 0x70180000 respectively.
- The first post-Generate boot reproduced `CFSR_NS.STKOF`; exact ELF mapping
  placed PC in `HAL_RCCEx_PeriphCLKConfig` and LR in
  `PWR_TCPP0203_Configure_ADC`. CubeMX had restored the CAD stack to 1 KiB.
- Restored `OS_CAD_STACK_SIZE` to `N6_USBPD_CAD_STACK_SIZE` (8 KiB) and added
  a build-and-sign preflight that refuses to sign if this mapping regresses.
- Explicitly applied the USBPHY1 kernel-clock mux in an MSP USER block. CubeMX populated `UsbPhy1ClockSelection` but requested only `RCC_PERIPHCLK_USBOTGHS1`, so HAL did not consume the PHY selection field.
- Added UART reporting for the effective USBPHY1/OTGHS1 frequencies and the RCC clock/reset registers after PHY bring-up.
- Aligned USB startup with ST's official event flow: the PCD now starts only after a real USB-PD CAD attach notification.
- Enabled VDDA, VDDIO2 through VDDIO5, and VDDUSB in the FSBL before `HAL_Init()`, as done by ST's official CDC example.
- Added a PCD-handle clear before each attach-cycle initialization, matching the official example's initialization discipline.
- Ported the explicit USB1 HS-PHY reset, clock-reference, control-register, and reset-release sequence from ST's official NUCLEO-N657X0-Q CDC ACM example.
- Initially copied the official CDC Rx/Tx FIFO sizing after `HAL_PCD_Init`, then
  corrected its undersized High-Speed EP1 Tx FIFO after the first real bulk-IN
  transfer exposed the deterministic deadlock.
- Added UART breadcrumbs around PCD MSP, PHY reset/release, HAL PCD return, and FIFO configuration.
- Added temporary HAL/LL USB stage diagnostics to identify the exact wait inside `HAL_PCD_Init`.
- Confirmed through UART that CN8 Type-C attachment is detected on CC2 and reaches the Device START notification path.
- Converted README and AGENTS documentation to English.
- Added a detailed outside-USER CODE inventory and ST bug assessment.
- Documented the confirmed missing-break bug in X-CUBE-53L9A1 V1.0.0.
- Corrected the USBX stack narrative: the demonstrated STKOF was in the USB-PD CAD task.
- Mapped the cable-attachment crash to the TCPP0203 ADC/RCC path.
- Increased the CAD stack from 1 KiB to 8 KiB.
- Increased the USB-PD pool from 5000 bytes to 16 KiB.
- Increased the USBX control stack to a conservative 16 KiB bring-up value.
- Increased the USBX pool to 32 KiB and updated the IOC value.
- Added, then removed after CAD validation, a temporary fixed-device CDC startup independent of cable detection.
- Added the initial English project documentation.

### Earlier bring-up work

- Added external-NOR FSBL loading and version 2.3 image signing.
- Added build/sign/program scripts.
- Corrected TrustZone/RISAF handover to Non-Secure.
- Added UART diagnostics to FSBL, Secure, startup, and Non-Secure.
- Added detailed fault register and processor-state dumps.
- Integrated X-CUBE-53L9A1 and ported its platform layer to STM32N6/I3C DMA.
- Increased the ToF stack to 64 KiB after the original transform-stack
  overflow; the later 10 fps optimized build uses 96 KiB after combining GCC
  stack-usage data with actual control-flow analysis.
- Completed full 54×42 acquisition and ANSI rendering.
- Integrated the ST67W6X driver in a separate optional task.
- Added a feature flag that completely suppresses radio initialization.
- Added the USB CDC console, CLI, TCPP0203 BSP, and Type-C diagnostics.

## 13. Known limitations and next steps

1. Measure the processed 54×42 frame rate on hardware and confirm that the CLI
   reports approximately 10.0 fps after the autonomous/`-O3` change.
2. Watch the periodic ToF heartbeat and CDC TX logs while the terminal is open;
   USB backpressure must not stop sensor acquisition.
3. Test repeated CN8 attach/detach and verify that initialization is idempotent.
4. Move CubeMX-managed outside-USER changes into custom files or a reproducible patch process.
5. Physically install X-NUCLEO-67W61M1 before enabling its feature flag.
6. Verify ST67 SPI handshaking and NCP firmware before enabling Wi-Fi/BLE.
7. Design BLE OTA with an inactive slot, signature verification, atomic activation, and rollback.
8. Replace -nk with a protected production signing chain before treating the device as secure.

## 14. The project's golden rule

The IOC describes hardware ownership and the generated skeleton. The hand-written code describes product behavior. After every Generate Code operation, verify that both still agree about pins, TrustZone, interrupts, memory regions, task stacks, middleware callbacks, and feature flags.
