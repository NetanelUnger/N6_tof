# STM32N657 ToF, USB CDC, and ST67W611M1 Project

The guided, resumable ToF rock-paper-scissors pipeline is documented in
[training/README_HE.md](training/README_HE.md). It includes the
`DATASET STREAM ON|OFF|STATUS` binary CDC protocol, capture/validation/model
BAT stages, atomic embedded-weight deployment, frame-exact Neural-ART HIL, and
`VIEW_LIVE.bat`, which atomically swaps complete CRC-validated raw/model frames
at full stream rate without relying on progressive ANSI terminal rendering, plus
`ANALYZE_TRAINING.bat`, which creates an offline Hebrew HTML explanation of
the dataset, learning curves, confusion matrix, saved-frame Keras/TFLite
predictions, quantization contract, and current HIL report without modifying
the model or firmware.

This document explains the architecture, STM32CubeMX configuration, post-generation changes, RTOS tasks, build and programming flow, debugging strategy, and current engineering status of the project.

The goal is not only to describe how to run the firmware, but also to explain why it is structured this way and how to reason about failures.

To recreate the board project and follow the bring-up in a learning-oriented
order, see [GUIDE.md](GUIDE.md).

## 1. Hardware and project goals

The project combines:

- NUCLEO-N657X0-Q with an STM32N657X0H3Q MCU.
- X-NUCLEO-53L9A1 with a VL53L9CX Time-of-Flight sensor.
- X-NUCLEO-67W61M1 with an ST67W611M1 Wi-Fi + BLE network coprocessor.
- A 1.28-inch, 240x240 round TFT using the GC9A01 controller.
- USB Device CDC ACM for a fast terminal, an ANSI color depth map, and a command-line interface.
- USART1 through the on-board ST-LINK Virtual COM Port for boot and fault diagnostics that remain available even when USB fails.

Current status:

| Feature | Status |
|---|---|
| Boot from external NOR Flash | Working |
| BootROM → FSBL → Secure → Non-Secure | Working |
| VL53L9CX initialization | Working |
| Full 54×42 depth frames | Working |
| Five educational ToF image channels | Working through the CDC map on hardware; enabled channels rotate one identified image per sensor frame |
| I3C DMA acquisition | Working on hardware as a callback/event-driven steady-state pipeline |
| ANSI color-map renderer | Working through USB CDC |
| ST-LINK UART at 115200 baud | Working |
| USB CDC | Working; Windows creates a separate COM port backed by a manager task, independent RX/TX workers, callback-driven TX, and fixed static slots |
| USB CDC XMODEM firmware update | Working for a signed physical CN8 transfer and confirmed trial boot; interruption and deliberate rollback fault-injection tests remain pending |
| GC9A01 round display | Working from SRAM: the DMA-backed task renders the numbered ToF map and its frame-matched NPU summary; 38/38 submitted frames rendered with zero errors in the latest non-visual HIL check |
| Rock/paper/scissors Neural-ART | Working on hardware; the current model passed frame-exact Stage 11 HIL with 100% host/NPU class agreement |
| ST67 Wi-Fi/BLE | Driver and dedicated task are present, but intentionally disabled because the shield is not currently installed |
| Wi-Fi/BLE OTA transport | Not implemented; it can reuse the authenticated byte-stream installer when the radio is enabled |

### 1.1 Latest hardware validation

On 2026-07-31, the hardened build was programmed into external NOR and every
programmed region passed STM32CubeProgrammer verification:

- FSBL at `0x70000000`.
- Secure application at `0x70100000`.
- Non-Secure application at `0x70180000`.

After restoring BOOT0 and BOOT1 to 1-2 and resetting the board, the complete
BootROM -> FSBL -> Secure -> Non-Secure path booted from external Flash. The
user then confirmed that the integrated VL53L9CX acquisition/processing path,
USB CDC connection, and terminal output all work correctly with the new static
RX/TX architecture and rare-event diagnostics enabled.

This is a successful functional hardware checkpoint. It is not yet evidence of
a multi-hour soak test, repeated attach/detach endurance, or deliberate fault
injection into every recovery branch. Those remain separate validation tasks.

On 2026-08-23, the SRAM development image added the inference result to both
live map consumers. `MAP ON` now appends a prominent `NPU RESULT` line plus
the four quantized scores to every CDC ANSI frame. `MAP ON SCREEN` and its
`MAP ON DISPLAY` alias render `NOTHING`, `ROCK`, `PAPER`, or `SCISSORS` below
the centered GC9A01 map. The display task snapshots the NPU result with the
submitted ToF frame and exposes the rendered result through `status`; a
non-visual hardware check observed NPU frame 356 and rendered frame 356,
`NOTHING` at 921/1000 confidence, 38 submitted/38 rendered, and zero display
errors. This validation was performed from SRAM and did not change Flash or
the persistent firmware version. It proves the Neural-ART runtime and
frame-matching path, but its accuracy result predates the 2026-08-28 binary
preprocessing change and is not a validation of the new classifier contract.

On 2026-09-12, the regenerated binary-silhouette model passed repeated
frame-exact Stage 11 HIL runs on hardware. Every compared Neural-ART result was
attached to the same sensor frame as the host TFLite result, class agreement
was 100%, device/Python preprocessing was bit-exact, and the maximum raw int8
score delta was 4-5 against the configured limit of 16. The earlier constant
`NOTHING` result was traced to an unsafe uint8 Keras boundary that caused
STEdgeAI to generate an in-place UINT8-to-FLOAT expansion. The current TFLite
boundary is QLinear uint8 with scale 1 and zero-point 0 and contains no input
CAST.

The authenticated A/B updater has also completed a signed physical CN8 XMODEM
installation and confirmed trial boot. Deliberate interruption during transfer,
invalid-signature/version injection, and reset-before-confirm rollback remain
separate tests; one successful installation does not prove all recovery paths.

### 1.2 Repository layout and local reference material

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
    C --> V["Validate A/B metadata, signature, hash, and version"]
    C --> D["Load Secure image @ 0x70100000"]
    V --> E["Load selected Non-Secure Slot A or B"]
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
- Selects Slot A or B from redundant boot metadata and re-verifies an updated
  image's ECDSA-P256 manifest and SHA-256 before it can execute.
- Converts a pending image into a one-boot trial and rolls back automatically
  if that trial resets before the application confirms it.
- Copies the Secure and selected Non-Secure images into their execution regions.
- Leaves XSPI2 memory-mapped mode after the copies complete, before transferring
  ownership to Secure. The Secure update writer requires indirect-command mode.
- Synchronizes and disables caches before handing over control.
- Starts the Secure application.

### 2.2 Why AppliSecure is required

TrustZone divides the MCU into Secure and Non-Secure worlds. AppliSecure:

- Defines which SRAM regions are accessible from Non-Secure state.
- Programs RISAF and RIF access control.
- Enables Neural-ART/CACHEAXI, opens SRAM3-6 to Non-Secure, and targets NPU
  interrupts to the Non-Secure runtime.
- Owns XSPI2, PKA, signature validation, bounded inactive-slot writes, read-back
  hashing, and atomic update-metadata commits behind narrow NSC entry points.
- Rejects all update calls if XSPI2, XSPIM, ExtMem/SFDP, or PKA initialization
  fails, while allowing the already authenticated normal application to boot.
- Releases required peripherals and GPIOs to Non-Secure.
- Preserves the Non-Secure MSP and Reset_Handler values before RISAF changes make the normal alias unreadable in this configuration.
- Performs the final state transition into the Non-Secure Reset_Handler.

A mistake in these permissions may look like an ordinary HardFault even though the real cause is a TrustZone access violation.

## 3. External Flash image map

| Region or artifact | Address / offset | Purpose |
|---|---:|---|
| N6_FSBL-trusted.bin | 0x70000000 | Boot loader and external-memory setup |
| N6_AppliSecure-trusted.bin | 0x70100000 | TrustZone, isolation, and secure update service |
| Slot A / N6_AppliNonSecure-trusted.bin | 0x70180000 / 0x00180000 | Factory or currently selected Non-Secure image |
| Slot B | 0x70280000 / 0x00280000 | Inactive or alternate Non-Secure image |
| Boot metadata copy 0 | 0x703E0000 / 0x003E0000 | 64 KiB erase sector containing one 1 KiB boot record |
| Boot metadata copy 1 | 0x703F0000 / 0x003F0000 | Alternating atomic boot record |

Each application slot is 1 MiB. `N6-Firmware-v<version>.n6fw` contains a
256-byte signed update manifest followed by the trusted Non-Secure STM32 image.
The generated Neural-ART weights are a const array inside that image and are
copied to NPU SRAM6 at runtime, so the existing single-payload A/B transaction
installs and rolls back application code and its exact weights together.
`N6-BootMetadata.bin` describes the factory Slot-A version and is programmed to
both metadata sectors so a development reflash cannot retain a stale Slot-B
selection.

Each image receives an STM32 image header version 2.3 through STM32_SigningTool_CLI. The current development flow uses the -nk option, which creates the required FSBL image format without a private signing key. This is appropriate for bring-up, but it is not a production secure-boot chain.

The update package has an independent ECDSA-P256 signature and SHA-256 image
digest. This rejects corrupted, unsigned, wrong-target, oversized, and
non-incrementing packages in the current firmware. It does not turn the current
development board into a complete physical root of trust: `-nk` remains in the
BootROM image flow, the update public key is compiled into replaceable firmware,
and the shared development private key is not an HSM-backed production key.
This educational repository intentionally tracks that development key so the
complete signing and update exercise can be transferred to another learner.
Anyone with a copy can sign an update accepted by this development firmware.
Production must therefore use a different key, enable the STM32 authenticated
secure-boot/OTP chain, protect or immutably bind the update public key, protect
the anti-rollback state, and keep its private signing key outside the repository
and developer workstations.

## 4. Important N6.ioc settings

The CubeMX source of truth is [N6.ioc](N6.ioc).

### 4.1 MCU and project structure

- MCU: STM32N657X0H3Q in a VFBGA264 package.
- STM32Cube package: STM32Cube FW_N6 V1.4.0.
- Toolchain: STM32CubeIDE with GCC.
- Project type: SecureNSecure.
- Contexts: FSBL, AppliSecure, AppliNonSecure, and ExtMemLoader.
- KeepUserCode is enabled.
- Main ThreadX application pool: 159 KiB.

### 4.2 Clock configuration

- CPU clock calculation: up to 600 MHz.
- AXI clock: 400 MHz.
- I3C1 kernel clock: 200 MHz.
- USB OTG HS1 receives an accurate 48 MHz clock directly from HSE.
- SPI4 receives a 200 MHz kernel clock and is reserved for the display at an
  initial 12.5 Mbit/s.
- SPI5 receives a 60 MHz kernel clock and remains reserved for ST67 at
  approximately 30 Mbit/s.

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

### 4.5 GC9A01 round display through dedicated SPI4 TX DMA

`N6.ioc` reserves a display-only SPI4 bus so SPI5 and its control pins remain
available to ST67. The generated C initialization and the hand-written display
port are synchronized with this mapping.

| Display pin | STM32 pin | Project signal | Function |
|---|---|---|---|
| SCL | PE12 | LCD_CLK | SPI4_SCK |
| SDA | PE14 | LCD_DIN | SPI4_MOSI |
| DC | PE1 | LCD_DC | GPIO command/data select |
| CS | PE13 | LCD_CS | Active-low chip select |
| RST | PE2 | LCD_RST | Active-low hardware reset |
| VCC | 3.3 V | - | Display power; do not connect to a 5 V GPIO supply |
| GND | GND | - | Common ground |

The module's SDA/SCL labels describe a write-only SPI connection here, not
I2C. Its MISO input is not required. SPI4 is configured as a mode-0,
transmit-only master at an initial 12.5 Mbit/s. GPDMA1 channel 5 is reserved
for SPI4 TX. The dedicated priority-8 display task performs the reset and GC9A01
initialization sequence, clears the panel, and centers `SYSTEM IS LOADING`.
Commands, clear chunks, and text pixels all use `HAL_SPI_Transmit_DMA`; the task
waits on ThreadX event flags posted by the SPI completion/error callback, so it
does not poll while DMA is active. Panel clearing and the 202x14 text bitmap are
streamed through one shared, cache-cleaned 404-byte DMA row buffer instead of
reserving two large static buffers.

The task is intentionally the only display/SPI owner and suspends after the
startup screen. The next display phase will add a bounded queue and explicit
RGB565 buffer-ownership/completion rules at that suspension point. The current
startup text uses only a tiny private glyph subset and is not intended to be
the future graphics library.

The SPI4 migration has been generated and integrated. After any future Generate
Code operation, audit the generated GPIO, SPI4, GPDMA1 channel 5, NVIC, and
Non-Secure RIF ownership, and verify that the display application still uses
`hspi4` and the `LCD_*` control pins.

User hardware validation on 2026-09-13 confirmed that the display operates
correctly on this SPI4 mapping.

### 4.6 USB CDC and USB-PD

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

### 4.7 CubeMX warnings seen during generation

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
  especially BSEC, XSPI, PKA, ADC, UART, and USB.
- FSBL and AppliSecure project links still include `Common/Update`; AppliSecure
  also retains the ExtMem manager sources used by the Secure flash writer.
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

The current linker/map-level RAM ownership is:

| Region | Current range/use |
|---|---|
| Secure SRAM1 | `0x34000400..0x340FFFFF`, 1023 KiB for AppliSecure |
| FSBL staging | `0x34180400..0x341FFFFF`, 511 KiB used transiently during boot/development loading |
| Non-Secure SRAM2 | `0x24100400..0x241FFFFF`, 1023 KiB for the application image, BSS, ThreadX pools, sensor buffers, C heap, and MSP stack |
| Upper NPU SRAM3 | `0x24244000..0x2426FFFF`, 176 KiB reserved for CPU-side CDC/RPS static workspaces; 162,048 bytes are currently linked |
| NPU SRAM4 | `0x24270000..0x242DFFFF`, unused by the current model |
| NPU SRAM5 | input plus Neural-ART activations from `0x242E0000`, currently 17,408 bytes |
| NPU SRAM6 | copied model weights from `0x24350000`, currently 55,425 bytes |

STM32N6 exposes Secure `0x34...` and Non-Secure `0x24...` aliases for these
banks. STEdgeAI initially describes the NPU banks through their Secure alias;
Stage 08 installs the Non-Secure aliases used by the running application. The
generated model is deliberately rejected if it selects SRAM3, because the CPU
already uses a fixed part of that bank and silent overlap would corrupt either
USB/RPS scratch or NPU activations.

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

The ThreadX application pool is 159 KiB. Its active pool-backed stacks reserve
about 124 KiB after adding the 4 KiB display task. The USBX parent byte pool is
56 KiB: it contains the 32 KiB USBX system arena, the 16 KiB device-control
stack, allocator bookkeeping, and about 8 KiB of unused parent-pool headroom.
With the update and static CDC buffers linked, the first-frame transform needs
about 356,688 bytes at peak; a 192 KiB pool left only 356,872 bytes before
allocator overhead and therefore returned `MEDIA_ERROR_UNKNOWN` (`-14`). Stack
and heap requirements must be budgeted together. The current linked image leaves
393,352 bytes between `_end` and the reserved MSP stack. The build helper now
refuses to sign a Non-Secure image with less than 360 KiB of C-heap capacity.

The USBX device-control stack is currently 16 KiB, the USBX system arena is
32 KiB, and their parent ThreadX byte pool is 56 KiB. The 16 KiB stack value was
introduced as a conservative bring-up value during the initial fault
investigation. Later address mapping proved that the observed STKOF was in the
USB-PD CAD task, not the USBX task. Therefore, this larger USBX stack is not
evidence of an ST USBX defect.

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
- `menu.c/.h` is a platform-independent, allocation-free line parser and
  command-prefix dispatcher.
- `debug_cli.c/.h` supplies the command table and handlers, receives terminal
  input from the RX delivery queue, and writes responses through the static
  control-message slots.

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
| version | Report the exact running Non-Secure firmware version |
| status | Show a system summary |
| usb status | Show CDC session, static-slot usage, queues, callback completions, flow control, and errors |
| map on / map off | Show or hide the sensor map; while it is open, keys `1`..`5` toggle channels and Enter returns to the menu |
| map channels `[1..5]` | List the five sensor channels and their current selection, or toggle one channel |
| map processing | Show the depth-filter submenu and current `[V]` selection |
| map processing off/box/median/gaussian/sharpen/min/max/object 1..7/npu | Select a displayed depth filter, one cumulative teaching stage, or the exact NPU input |
| map processing `<filter>` `<parameter>` `<value>` | Configure the selected filter, for example `MAP PROCESSING BOX radius 2` |
| tof status | Show ToF state, rate, and range |
| tof pause / tof resume | Stop or restart the autonomous ranging stream |
| dataset stream on / off / status | Stream N6DF v3 records containing raw 54x42 `uint16` depth and the exact frame-matched 64x50 `uint8` NPU tensor with separate CRCs |
| debug off/error/warn/info/debug | Change ST67 log verbosity |
| clear | Clear the terminal |
| Start UART Firmware Update | Enter raw XMODEM-CRC receive mode on the CN8 USB CDC terminal (`update` is an alias) |
| reboot yes | Reset the MCU |

#### 5.3.1 Table-driven command menu

The CLI no longer uses one growing `if/else` dispatcher. It declares a constant
array of `Menu_Object_t` entries:

~~~c
static const Menu_Object_t cli_menu_objects[] =
{
  MENU_OBJECT("help", cli_command_help),
  MENU_OBJECT("status", cli_command_status),
  MENU_OBJECT("usb", cli_command_usb),
  MENU_OBJECT("map", cli_command_map),
  MENU_OBJECT("tof", cli_command_tof),
  MENU_OBJECT("Start UART Firmware Update", cli_command_firmware_update),
  MENU_OBJECT("reboot", cli_command_reboot)
};
~~~

Each entry contains a command prefix and a function pointer. The selected
handler receives the complete command line, so an entry such as `set tof` can
handle a line such as `set tof 123,123` without changing the parser.

The console keeps the 16 most recent non-empty commands in fixed storage.
Up/Down browse that history and restore the pending draft after the newest
entry. Tab completes commands, subcommands, filter names, and filter parameter
names from the same descriptor tables used for dispatch and map processing.

`Menu_Process()` accepts arbitrary input chunks. It retains a partial line in a
caller-owned 192-byte buffer until CR, LF, or CRLF arrives. Matching is
case-sensitive, requires a word boundary after the registered prefix, and uses
the longest valid prefix when entries overlap. Backspace/Delete edit the
pending line. An overlength line is discarded through its next Enter instead
of dispatching a truncated command.

There is no allocation. The menu instance, command table, input buffer, and
768-byte reply buffer are all static. `Menu_Reply()` normalizes any existing
line ending, adds exactly one CRLF, and submits the complete response through
the application-supplied send callback in one call. In this project that
callback uses `App_Console_Write()`, so the existing CDC TX worker still owns
the physical USB transfer.

To add a command:

1. Write a handler with the signature
   `void handler(Menu_t *menu, const char *full_command)`.
2. Add one `MENU_OBJECT("command prefix", handler)` entry.
3. Parse any arguments from `full_command`.
4. Return textual results with `Menu_Reply()`; every reply will end in Enter.

The generic API and a standalone example are documented directly in
`AppliNonSecure/Core/Inc/menu.h`.

#### 5.3.2 Authenticated XMODEM firmware update

Despite the historical command text saying UART, the implemented transfer runs
over the CN8 USB CDC console, not the independent ST-LINK diagnostic UART. After
entering `Start UART Firmware Update`, the CLI stops line parsing and terminal
echo and passes raw CDC byte arrays into an allocation-free XMODEM-CRC receiver.
It accepts 128-byte SOH and 1 KiB STX blocks, validates the block complement and
CRC16, acknowledges retransmitted blocks without writing them twice, bounds
timeouts and retries, and supports CAN cancellation.

The transport is intentionally separate from installation. XMODEM first
collects the 256-byte manifest, then sends each payload byte array through the
Secure NSC service. The Secure service:

1. Copies Non-Secure inputs into Secure scratch memory to avoid time-of-check /
   time-of-use changes.
2. Validates target, type, size, monotonically increasing version, and the
   ECDSA-P256 manifest signature before erasing anything.
3. Erases only the required sectors in the inactive 1 MiB slot and rejects
   every out-of-bounds chunk.
4. Streams SHA-256 while writing, then hashes the flash read-back and validates
   the STM32 image header and vectors.
5. Writes a CRC-protected PENDING record to the alternate metadata sector only
   after all checks succeed.

The inactive slot is erased lazily in 64 KiB sectors as authenticated image
bytes reach each sector. This avoids holding the first XMODEM ACK behind a
full-slot erase, keeps every protocol pause bounded to one sector erase, and
still leaves the active slot and boot metadata untouched on interruption.

On reset the FSBL independently verifies the candidate and marks it TRIAL before
booting. A one-shot Non-Secure task confirms the boot after five seconds. If the
device resets before confirmation, the next FSBL run restores the previously
confirmed slot. A power loss during reception leaves the active slot and last
valid metadata record untouched.

The same byte-array `Begin` / `Write` / `Finalize` boundary is the integration
point for a future Wi-Fi/BLE downloader; the radio transport must not bypass the
Secure service or write external flash directly.

#### 5.3.3 Rare-event handling and diagnostics

The high-rate paths deliberately separate evidence capture from text output.
USBX and HAL callbacks never format UART strings. They update fixed counters,
save a small snapshot, set a sticky diagnostic bit, and return. The relevant
task later prints the evidence on the independent ST-LINK UART.

USB CDC failure handling includes:

- A five-second bound on the asynchronous Bulk-IN completion callback. A lost
  callback can no longer block the TX scheduler forever.
- No buffer reuse after a callback timeout. The USB manager stops callback
  mode, aborts the USBX transfer, waits for RX/TX workers to become idle,
  flushes static queues, and starts a new session. Recovery is limited to three
  attempts per physical activation.
- Sticky diagnostic categories for unavailable CDC, TX/RX slot exhaustion,
  TX/RX queue-full, callback timeout, USBX transfer error, and internal ThreadX
  worker-synchronization failure. A one-second manager health event consumes
  these flags and prints cumulative counters once, outside callback context.
- Every worker `event_flags`, blocking queue receive, and TX-completion
  semaphore result is checked. A rejected completion wakeup is retained as a
  sticky synchronization failure; the five-second timeout remains the final
  guard against a permanently stranded Bulk-IN transfer.
- Counters for failures to post into the USB manager event queue. The next
  successfully received manager event reports the total, delta, last ThreadX
  status, last failed event type, and per-type counts. USBX class callbacks do
  not print directly even on this rare path.
- CDC line-parameter notifications are deliberately coalesced into a counter.
  Windows may generate a burst while opening the COM port, but those
  notifications contain no application payload and must not crowd lifecycle
  START/STOP or rare ERROR events out of the manager queue.
- `usb status` retains the full history, including unavailable drops, queue
  failures, callback timeouts, transfer errors, synchronization failures, and
  the last USBX status.

The VL53L9CX uses I3C private transfers; these resemble traditional I2C
register accesses. On an asynchronous HAL error, the callback stores the tick,
`ErrorCode`, I3C state, `EVR`, and control/RX/TX DMA states. If descriptor
creation or DMA start fails synchronously, the code also stores the exact start
stage and returned `HAL_StatusTypeDef`; this case does not necessarily produce
an error callback. The snapshot counts GPIO interrupts, I3C completions, HAL
errors, start failures, and failed ThreadX event post/wait/clear operations. The
ToF task prints that complete snapshot before entering its fatal state. A
sticky event bit provides a fallback if the ISR completed but ThreadX rejected
the event-flags post.

ToF raw-slot queue failures are invariant violations rather than normal frame
drops. They are counted separately and logged on the first occurrence and then
at powers of two, preventing a persistent failure from flooding COM6. The
processing task no longer retries an invalid queue silently: a failed blocking
receive is recorded and moves the ToF pipeline to its explicit fatal state.

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

Wi-Fi/BLE download and connectivity are not implemented while the shield is
absent. The transport-independent installer is now present: inactive A/B slots,
chunk bounds checks, SHA-256 plus ECDSA-P256, increasing-version policy, atomic
activation, trial confirmation, and rollback. A future ST67 task should only
download and feed byte arrays into that interface.

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

- `Tools/build_and_sign.ps1 -FirmwareVersion <n>` clean-builds the required
  contexts, creates STM32 version-2.3 trusted images, creates factory metadata,
  and signs `N6-Firmware-v<n>.n6fw` with the shared educational update key.
- `Tools/New-FirmwareSigningKey.ps1` creates a development P-256 key once. The
  designated private blob and generated public-key header are both tracked for
  this reproducible educational project; neither is suitable for production.
- `Tools/New-FirmwareUpdatePackage.ps1` can package an already-built trusted
  Non-Secure image with an explicit increasing firmware version.
- `Tools/program_flash.ps1` programs and verifies FSBL, Secure, factory Slot A,
  and both default metadata copies in external NOR.

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
| FSBL/Core/Src/extmem.c | BOOT_GetApplicationSize and dynamic Non-Secure source hooks | Copy the exact selected A/B image | High |
| FSBL/Middlewares/ST/STM32_ExtMem_Manager/boot/stm32_boot_lrun.c/.h | Use the selected Non-Secure source and call a pre-jump hardware handover hook | Let A/B selection feed LRun and leave XSPI memory-mapped mode before Secure reinitializes it | High: vendor middleware has no USER block around this path |
| AppliSecure/Core/Src/main.c | One trace call between generated initialization calls | Diagnostic only | Medium |
| FSBL/Core/Inc/stm32n6xx_hal_conf.h | Re-enable BSEC, XSPI, and PKA modules | Multi-context Generate removed modules still required by the custom FSBL | High |
| AppliSecure/Core/Inc/stm32n6xx_hal_conf.h | Enable XSPI and PKA modules | Secure flash writer and ECDSA verification | High |
| FSBL and AppliSecure `.project` / `.cproject` | Link shared update, PKA, XSPI, and ExtMem sources and include paths | Build the boot verifier and Secure installer | High: CubeMX/IDE regeneration may remove links |
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

### 6.3 Vendor files changed locally

- `FSBL/Middlewares/ST/STM32_ExtMem_Manager/boot/stm32_boot_lrun.c/.h`
  contains copy/cache logs, a dynamic Non-Secure source-address hook, and a
  pre-jump hook that exits XSPI memory-mapped mode after LRun copying. These
  functional changes are outside USER blocks.
- Drivers/BSP/STM32N6xx_Nucleo/stm32n6xx_nucleo_usbpd_pwr.c contains additional TCPP0203/I2C logs.
- Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_pcd.c contains temporary stage logs around MSP, core reset, Device-mode selection, and device initialization.
- Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_ll_usb.c contains temporary `USB_CoreReset` register and timeout logs. These are compiled only for the Non-Secure ThreadX application.

The LRun copy algorithm itself, TCPP0203 component driver, ADC logic, and STM32
USB-PD CAD hardware layer were not otherwise changed.

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
| Firmware confirmation | 6 | 2 KiB | TX application pool | Sleeps five seconds, commits a TRIAL image, then exits; priority prevents ToF starvation |
| ToF Acquisition | 7 | 16 KiB | TX application pool | Sensor ownership, PD9 event wait, fully asynchronous I3C DMA sequence, raw-slot publication |
| ToF Main Thread | 10 | 96 KiB | TX application pool | Raw-frame transform, RPS preprocessing/Neural-ART inference, metadata parsing, ANSI rendering, and raw-slot release |
| USBX Device App Main Thread | 8 | 16 KiB | USBX pool | USB lifecycle manager: PCD/USBX, CDC callbacks, worker start/stop, error events |
| USB CDC RX worker | 9 | 12 KiB | Static BSS | Dispatches callback-filled static RX slots into the application delivery queue |
| USB CDC TX worker | 9 | 12 KiB | Static BSS | Submits one static TX slot and waits for the USBX completion callback before advancing |
| ST67 WiFi BLE | 11 | 8 KiB | TX application pool | W6X, Wi-Fi station, and BLE server; currently not created |
| USB debug CLI | 9 | 6 KiB | TX application pool | CDC input, line editing, and commands; runs above the continuously ready ToF processor |

Additional internal ThreadX and USBX tasks may be created by the middleware, such as the ThreadX timer task and USBX class tasks.

### 8.1 Byte pools

| Pool | Size | Main use |
|---|---:|---|
| tx_app_byte_pool | 159 KiB | ToF, CLI, optional ST67, compatibility objects |
| ux_device_app_byte_pool | 56 KiB | 32 KiB USBX system arena, 16 KiB USB Device task stack, bookkeeping, and headroom |
| usbpd_app_byte_pool | 16 KiB | CAD queue, CAD task, and USB-PD objects |

The CDC data plane does not have a byte pool. Its memory is fixed in BSS:

| Static storage | Count × size | Purpose |
|---|---:|---|
| ToF raw slots | 3 × 14,842 bytes | DMA destinations exchanged between acquisition and processing |
| CDC control TX slots | 8 × 768 bytes | CLI text and short diagnostic messages |
| CDC map TX slots | 2 × 48 KiB | Complete ANSI frames rendered in place |
| CDC RX slots | 16 × 512 bytes | Completed USB bulk-OUT payloads |

Separate pools help diagnose failures. A PSP address can be matched to a pool to identify which task was actually running.

The upper 176 KiB of NPU SRAM3 (`0x24244000..0x2426FFFF`) holds the CDC worker
stacks/slots and RPS preprocessing scratch. The current `.npu_shared_bss` uses
162,048 bytes of that reservation. Moving these deterministic large objects out
of SRAM2 leaves 393,352 bytes between the current `_end` symbol and the reserved
MSP stack, above the 360 KiB VL53L9 guard. The generated network uses 17,408
bytes in SRAM5 for its input/activations and 55,425 bytes in SRAM6 for its
weight blob; Stage 08 rejects a future network that selects the reserved SRAM3
bank.

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

#### 9.2.1 Fast Non-Secure development loop

Ordinary Non-Secure source iterations do not need a clean build, image
signing, or an external-NOR write. The incremental builder invokes the
generated makefile directly and produces only the ELF, map, and raw binary;
it deliberately skips the large disassembly listing generated by the normal
`all` target. The shared helper also repairs project-local absolute Windows
paths emitted into GCC `.d` dependency files by CubeIDE 2.2/GCC 14.3, before
and after `make`, so a clean build cannot poison the next incremental run:

~~~powershell
powershell.exe -ExecutionPolicy Bypass `
  -File .\project\Tools\Build-NonSecureIncremental.ps1
~~~

For a RAM debug session, put the board in DEV boot mode (`BOOT0=1-2`,
`BOOT1=2-3`) and press Reset. Flash boot closes STM32N6 debug access before the
FSBL runs, while DEV boot deliberately leaves Secure and Non-Secure debug open.
The helper loads the already-built FSBL ELF into SRAM and lets it reach the
signed Secure runtime from external Flash. At Secure `main()` it replaces that
runtime with the locally built Secure binary in SRAM1 and restarts it, then
replaces the incrementally built Non-Secure image through SRAM2's Secure alias.
Both vector tables are verified before execution. This makes Neural-ART clocks,
TrustZone ownership, network code, and weights testable entirely from SRAM:

~~~powershell
powershell.exe -ExecutionPolicy Bypass `
  -File .\project\Tools\Debug-NonSecureRam.ps1
~~~

The default leaves an interactive GDB session. Pass `-Run` when an agent or
script should load the image, run it, and detach. Pass `-NoBuild` to reload an
already-built binary. No external Flash or firmware version is changed. A
Reset discards the RAM image and returns to the DEV-boot ROM, so rerun the
helper after every Reset. To boot the installed persistent image again, return
`BOOT1` to `1-2` and press Reset.

This lane incrementally builds both Secure and Non-Secure; unchanged targets
remain make no-ops. It loads both local binaries so SAU/RISAF and the
Neural-ART bootstrap can be exercised without a Flash write. Persistent Secure,
FSBL, startup, TrustZone ownership, or NSC changes still require the full
build/sign/SWD flow. Use `-Clean` after
changing `ux_user.h`, after CubeMX generation, or when explicitly investigating
stale generated objects.

#### 9.2.2 Final Non-Secure update through USB CDC/XMODEM

When RAM debugging is complete, one command advances the explicitly supplied
release version, incrementally builds only Non-Secure, signs only that image,
creates a signed `.n6fw`, auto-detects the CN8 USB CDC port by VID/PID, sends
XMODEM-CRC 1K blocks, waits through reset and the five-second confirmation
window, and checks the running `version` command:

~~~powershell
powershell.exe -ExecutionPolicy Bypass `
  -File .\project\Tools\Install-NonSecureUpdate.ps1 `
  -FirmwareVersion 9
~~~

The normal policy accepts exactly `current + 1`; the script never chooses or
increments a version automatically. `-PackageOnly` exercises build, signing,
and package generation without modifying hardware or retaining the tentative
version in the tracked header. After the device acknowledges XMODEM EOT, the
new version is retained because the Secure service has committed PENDING boot
metadata. If a defect is discovered after that commit and confirmation, its
replacement must use the next version; reusing a confirmed number would weaken
the anti-rollback policy.

The XMODEM lane changes only the inactive Non-Secure slot. FSBL, Secure, the
active slot, and the last confirmed metadata remain untouched until the package
has been authenticated and finalized. The `version` CLI command reports the
running application version and is also used by the automation after reset.
Run `training\09_BOOTSTRAP_NPU_SWD.bat` once first: it programs only signed
FSBL + Secure and preserves both application slots/metadata. The guided release
BAT also requires a passing N6DF v3 raw-vs-device-tensor-vs-NPU HIL fingerprint before it asks
for the explicit `FLASH` confirmation.

### 9.3 Jumper positions

For the fast SRAM development loop:

- BOOT0 = 1-2.
- BOOT1 = 2-3.
- Press RESET before running `Tools/Debug-NonSecureRam.ps1`.

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

To recover the FSBL while preserving both application slots and the current
pending/trial metadata:

~~~powershell
powershell.exe -ExecutionPolicy Bypass -File .\project\Tools\program_flash.ps1 -FsblOnly
~~~

`FsblOnly` is mutually exclusive with `FullErase`.

To update both visible boot-chain stages while preserving both application
slots and the current A/B metadata:

~~~powershell
powershell.exe -ExecutionPolicy Bypass -File .\project\Tools\program_flash.ps1 -BootChainOnly
~~~

`BootChainOnly` programs the FSBL at `0x70000000` and Secure runtime at
`0x70100000`. It does not touch either Non-Secure slot or either metadata
sector. `FullErase`, `FsblOnly`, and `BootChainOnly` are mutually exclusive.

## 10. Terminals

### 10.1 ST-LINK UART

USART1 on the ST-LINK VCP is the exclusive diagnostic channel. Every boot,
security, USB, ToF, update, and radio debug message is written here. Each of the
three executable stages displays a 50-column by 50-row NATI LAB identification
screen for five seconds before its detailed log begins:

- `N6 SECURE BOOTLOADER` identifies the FSBL and its authenticated A/B work.
- `TRUSTZONE SECURE RUNTIME` identifies isolation and protected update services.
- `N6 NONSECURE APPLICATION` identifies the running signed application version.

Use 115200 baud, 8 data bits, no parity, and one stop bit. A terminal with ANSI
cursor and clear-screen support displays the screens as intended.

- Port: ST-LINK COM port; currently observed as COM6.
- Baud: 115200.
- Data: 8 bits.
- Parity: None.
- Stop: 1.
- Flow control: None.

Open this terminal before Reset. It is the primary diagnostic channel.

### 10.2 USB device CDC on CN8

After successful enumeration, Windows should create a second COM port. It is
not the ST-LINK COM port. CN8 USB CDC is intentionally UI-only. Opening it
displays the NATI LAB control menu; background diagnostics are never mirrored
to this port. The port carries only commands and replies, the XMODEM update
protocol, and a requested sensor map. The map is disabled after boot and after
every disconnect. Enter `MAP ON` to display it. While the map is active, keys
`1` through `5` toggle depth, amplitude, ambient, reflectance, and confidence;
press Enter to stop the display and return to the menu. `MAP CHANNELS` lists
the same numbered submenu and `MAP CHANNELS <number>` toggles an entry before
opening the map. Channel 1 is enabled by default.

Each ANSI frame carries its sensor frame number, numeric channel ID, channel
name, and complete enabled-channel set. When several channels are enabled, the
renderer sends one complete channel image per sensor frame and rotates through
the enabled set. This bounds every CDC map transfer to one image and keeps the
autonomous sensor pipeline non-blocking. The ST transform still produces the
depth image every time for the existing NPU; only the auxiliary image needed
for the current terminal frame is copied into the existing shared 54x42
processing workspace. It is rendered before that workspace is reused for a
filtered depth image on the SPI display.
Depth uses the fixed 200..4000 mm palette and can use `MAP PROCESSING` filters;
the other channels use per-frame auto-scaling and bypass depth filters.

`MAP PROCESSING` opens the filter submenu.
Box and Gaussian blur provide configurable radius and pass count. Median has a
radius and outlier threshold, Sharpen has radius and amount, while Min and Max
select the nearest or farthest valid neighbor. The selected filter is marked
with `[V]` and is applied only to the displayed map.

| Filter | Parameters | Exact intent |
|---|---|---|
| `OFF` | none | Unprocessed depth reference |
| `BOX` | radius 1..3, passes 1..3 | Average valid neighbors; fast smoothing at the cost of blurred edges |
| `MEDIAN` | radius 1..2, threshold 0..1000 mm | Replace an invalid/outlying center with the neighborhood median; threshold 0 always selects the median |
| `GAUSSIAN` | radius 1..2, passes 1..3 | Separable weighted smoothing with less blockiness than Box |
| `SHARPEN` | radius 1..3, amount 0..200% | Unsharp masking that emphasizes depth transitions and can also amplify noise |
| `MIN` | radius 1..3 | Select the nearest valid neighbor, expanding near objects |
| `MAX` | radius 1..3 | Select the farthest valid neighbor, shrinking near objects |

These seven filters do not alter the raw N6DF depth or the production model
tensor. Full Hebrew explanations, examples, and parameter tradeoffs are in
[`training/README_HE.md`](training/README_HE.md).

The cumulative
`MAP PROCESSING OBJECT 1` through `OBJECT 7` views expose the object pipeline
one transformation at a time: valid depth, adaptive candidates, selected
connected component, crop/relative normalization/resize, the 600 mm model
limit plus local surface growth (up to 120 mm between neighbors), a wider
four-source-pixel crop margin, and a guaranteed four-pixel model-canvas border,
and finally an aggressive binary silhouette: every non-zero OBJECT 5
pixel becomes 255 and one MVE-accelerated 3x3 dilation repairs thin sensor
dropout stripes. Experimental OBJECT 7 instead keeps only normalized OBJECT 5
intensities above a configurable threshold, so increasing the value removes
surfaces farther behind the palm. Use `MAP PROCESSING OBJECT 7 210` for the
short form or `MAP PROCESSING OBJECT 7 threshold 210`; the accepted range is
0..255 and the default is 210. Hardware testing selected 210 for production,
so the NPU tensor and Python bit-exact verifier use that fixed threshold.
Changing the OBJECT 7 teaching value remains display-only and cannot silently
alter the production contract. `MAP PROCESSING NPU` shows the exact
64x50 production tensor consumed by Neural-ART for that frame. It is black when
no component of at least 12 connected pixels exists between 100 and 600 mm;
otherwise its selected object is 255 and its background is 0. This deliberately
removes centimetre-scale relief inside a hand while retaining its outline.

The persistent display snapshot is necessary because the generated NPU network
reuses its activation arena, including the input address, during a run. The
aspect-preserving nearest-neighbor resize and copy into the preallocated NPU
input use Cortex-M55 Helium/MVE vector gather/load/store instructions;
inference remains on Neural-ART. Only the requested teaching view is preserved,
so the seven stages do not reserve seven frame buffers. The GC9A01 `MAP ON SCREEN`
path intentionally remains the 54x42 depth map in these modes. The old
`MAP PROCESSING OBJECT` spelling remains an alias for `MAP PROCESSING NPU`.

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

### 2026-09-13

- Reserved a dedicated GC9A01 SPI4 transmit-only path in `N6.ioc`: PE12 SCK,
  PE14 MOSI, PE13 CS, PE1 DC, and PE2 RST. The fitted display has no separate
  software-controlled backlight signal. Added SPI4 TX on
  GPDMA1 channel 5 with a conservative initial 12.5 Mbit/s clock and priority-5
  SPI/DMA interrupts. SPI5 and all ST67 pins remain unchanged, the radio
  feature remains disabled, and PD9 continues to own EXTI9 for ToF. Generate
  Code, generated-file audit, source-port update, and the full three-image build
  are complete; display HIL on the new pins remains pending.
- Restored the missing CubeMX virtual-channel and NVIC records for the existing
  UCPD1 RX/TX requests on GPDMA1 channels 3 and 4. The requests were already
  present in `N6.ioc`, but without their virtual pins CubeMX reported that
  USBPD had no UCPD1 DMA channels and omitted them from generated code.

### 2026-09-12

- Diagnosed a misleading Neural-ART failure in which black input matched host
  TFLite exactly, while every non-empty live tensor produced the same
  `NOTHING` result. The sensor stream and device preprocessing were bit-exact;
  the mismatch began at the generated network input.
- Changed the Keras boundary from uint8 to float32 in the original 0..255 pixel
  domain. Stage 06 now emits and enforces a genuine uint8 TFLite input with
  scale 1 and zero-point 0 and rejects any input CAST. This prevents STEdgeAI
  4.0 from generating the former in-place UINT8-to-FLOAT expansion from 3,200
  to 12,800 bytes, which corrupted non-zero input while allowing all-zero input
  to appear correct.
- Regenerated and integrated the Neural-ART network. The generated input is
  QLinear(1, 0, uint8), its first conversion is an NPU byte-sized quantization
  stage rather than a CPU float Cast, and the Non-Secure incremental build
  passes. Final confirmation remains the Stage 10 RAM load followed by Stage 11
  HIL with a moving hand.

### 2026-09-03

- Added a five-channel educational ToF map explorer. `MAP ON` accepts keys
  `1`..`5` as independent toggles for depth, amplitude, ambient, reflectance,
  and confidence; multiple selections rotate one identified image per sensor
  frame. `MAP CHANNELS [1..5]`, `status`, and `tof status` expose the same
  selection state. Every internal map message now includes a frame ID and
  channel ID. Depth remains the only input to the current RPS model, and the
  N6DF v3 training record is deliberately unchanged in this first integration.
- Kept the implementation within the VL53L9 transform's memory budget by
  retaining depth and reusing the existing processing workspace for one
  auxiliary output instead of keeping five simultaneous float images.

### 2026-08-29

- Added `MAP PROCESSING OBJECT 7 <threshold>`. It thresholds the
  normalized OBJECT 5 depth image before producing a repaired 0/255 silhouette;
  higher values retain only surfaces nearer the palm and can suppress the arm.
  The parameter range is 0..255 with a default of 210, and the named form
  `MAP PROCESSING OBJECT 7 threshold <value>` remains available. This teaching
  experiment selected 210 on hardware; that value is now fixed in the NPU
  tensor and host bit-exact preprocessing contract. Further interactive OBJECT
  7 changes remain display-only until promoted in both implementations.

### 2026-08-28

- Extended the training stream to N6DF v3. Every record now contains both the
  raw 54x42 millimetre map and the exact frame-matched 64x50 pre-inference
  tensor preserved by the MCU, with independent payload CRCs and a header CRC.
  Capture recomputes Python preprocessing and stops before saving if any of the
  3,200 bytes differs. The verified device tensor is stored in the sample NPZ;
  Stage 04 uses it as the training input, rechecks Python equality, and refuses
  legacy/host-only samples unless `--allow-host-preprocessing` is explicit.
- Replaced the single object view with cumulative `MAP PROCESSING OBJECT 1..6`
  teaching views and `MAP PROCESSING NPU` for the exact model input. The final
  production path now ignores all depth beyond 600 mm, produces an all-black
  image when no nearby non-trivial component exists, grows its near seed across
  locally continuous depth so tilted sheets are not sliced into bands, uses a
  four-source-pixel crop margin plus a four-pixel model-canvas border, and flattens the selected
  object to a 0/255 silhouette after resize. Every non-zero pixel becomes 255,
  then one MVE-accelerated 3x3 dilation repairs thin sensor dropout stripes so
  internal hand relief cannot become model noise. Python preprocessing and augmentation use
  the same binary contract; this configuration change invalidates prepared
  tensors and requires stages 04 through 08 plus a passing Stage 11 HIL before
  the embedded classifier can be considered matched again.
- The firmware preserves one requested teaching snapshot plus the final NPU
  snapshot because the Neural-ART activation schedule overwrites its input
  arena. Nearest-neighbor resize and the snapshot-to-NPU copy use Cortex-M55
  MVE vector operations with a scalar build fallback; the binary dilation does
  too, and inference continues on
  Neural-ART. The SPI screen path remains a 54x42 depth visualization.

### 2026-08-25

- Changed the live ToF terminal's four NPU outputs from raw signed INT8 scores
  to decoded percentages with one decimal place. The displayed class list and
  winning-class confidence now share the model's `scale=1/256`,
  `zero_point=-128` conversion and nearest-tenth rounding.
- Made `training/07_GENERATE_N6.bat` ask whether to regenerate with `--force`
  when its Neural-ART output is already current, while keeping direct pipeline
  script calls non-interactive.
- Added a guided `01_CAPTURE.bat` menu for new sessions, numbered resume with
  per-class counts, all advanced capture settings, and read-only session
  listing; explicit command-line arguments still bypass the menu.
- Added non-destructive `02_REVIEW_DATASET.bat`: it prioritizes technically
  suspicious/model-disagreement frames for human Accept/Reject/Relabel,
  persists reversible SHA-keyed decisions outside raw metadata, supports a
  whole-burst action when useful, and feeds the same reviewed labels into
  Capture, Validate, Prepare and HTML analysis. Stage 04 now supports corrected
  mixed-label bursts by grouping on physical session+burst identity and finding
  a global class-balanced split, so adjacent frames never leak across splits.

### 2026-08-24

- Added `training/ANALYZE_TRAINING.bat` and a read-only Python analysis stage.
  Each invocation creates a timestamped offline HTML snapshot with a dashboard,
  dataset/session/burst and split analysis, training accuracy/loss curves,
  explained confusion matrix and per-class metrics, an interactive saved-frame
  gallery with Keras/TFLite inference, quantization details, HIL interpretation,
  and traceable source-file hashes. `reports/html/latest.html` points only to
  the newest snapshot; no raw/prepared data, model, state, generated NPU code,
  firmware, or hardware is changed.

### 2026-08-23

- Diagnosed the apparent CN8 USB descriptor hang as a Neural-ART BUSIF1 fault,
  not a USB PHY failure. Stage 08 had relocated the xSPI2 weight addresses to
  NPU SRAM6 but retained `cacheable=1`, so the first weight fetch selected the
  xSPI/cache bus path and the LL_ATON interrupt assertion stopped the complete
  firmware. Stage 08 now converts every initializer DMA descriptor to the
  non-cacheable SRAM6 contract and rejects any cacheable descriptor left after
  relocation.
- Rebuilt and loaded Secure + Non-Secure from SRAM without changing external
  Flash. Hardware reached the first completed ToF transform, CN8 enumerated as
  `VID_0483&PID_5740`, and Windows created the board CDC port.
- Stage 09 passed 100 CRC-valid, distinct frames with 100/100 frame-matched NPU
  results, monotonic run counters, zero NPU errors, 100% class agreement, and a
  maximum raw int8 delta of 10. The learning profile now documents a configurable
  raw-score tolerance of 16 (0.0625 at the model's 1/256 output scale), while
  retaining 95% minimum class agreement and 80% minimum NPU coverage.
- Stage 11 now checks the one-time 08B bootstrap and exact-model HIL before
  prompting for a new firmware version. The signed 08B build-only path passed;
  persistent SWD/XMODEM writes still require the explicit `BOOTCHAIN`/`FLASH`
  confirmations.

### 2026-08-23

- Reworked RPS preprocessing after HIL proved that the deployed PC and NPU
  models agreed exactly but both collapsed to `none`. The shared Python/C
  contract now selects the nearest non-trivial connected depth component,
  rejects isolated speckles, crops it, and encodes relative rather than
  absolute depth. Capture shows and stores the exact 64x50 model input.
- Replaced global-average classification with a compact spatial CNN, added
  deterministic train-only translation/mirror/intensity augmentation, eight
  burst groups per class, session-diversity warnings, per-class test gates and
  a confusion matrix. `training/RESET_TRAINING_DATA.bat` provides an explicitly
  confirmed, scoped reset while preserving tools and capture-capable firmware.
- Capped embedded Neural-ART RPS weights at 64 KiB and compacted the spatial
  head after a 94,769-byte model reduced the VL53L9 heap below its hard gate.
  The replacement is 55,441 bytes, improves held-out macro accuracy to 75%,
  and leaves 387,816 bytes of Non-Secure C heap. Stage 08 now rejects an
  oversized model before the later Secure bootstrap/build step.

### 2026-08-22

- Fixed Stage 10 RAM boot after hardware diagnosis showed Non-Secure resetting
  in the first SRAM3 clear. RISAF6 was already open, but SAU region 1 ended at
  `0x241FFFFF`; it now extends through `0x243FFFFF`, covering SRAM2, NPU
  SRAM3-6, and CACHEAXI RAM. The RAM helper now incrementally rebuilds Secure
  as well as Non-Secure, uses the local FSBL handoff to replace both images,
  verifies vectors, and confirms progress through SRAM3 clear, peripheral init,
  and ThreadX before detaching. Hardware UART logs reached VL53L9 ready and
  `Neural-ART ready`; external Flash was not modified.
- Completed Stage 08 for the ToF rock/paper/scissors model. STEdgeAI 4.0 output,
  its matched STAI/LL_ATON/ThreadX runtime, and the 49,809-byte raw weight blob
  now compile into the Non-Secure image. Boot copies the embedded weights to
  NPU SRAM6, preserving atomic `.n6fw` v1 A/B update and rollback semantics.
- Added the Secure Neural-ART bootstrap for clocks, CACHEAXI, RIF/RISAF and NPU
  interrupt targeting, plus a one-time SWD boot-chain installer that preserves
  application slots. The RAM debug helper now replaces and verifies both local
  Secure and Non-Secure binaries without writing external Flash.
- Ported the frozen 54x42-mm to 64x50-uint8 preprocessing contract to firmware,
  runs Neural-ART synchronously in the ToF processing task, and added `RPS
  ON|OFF|STATUS`. N6DF v3 carries the exact NPU frame ID, four raw int8 scores,
  class, confidence and monotonic run count under header CRC.
- Added HIL gates for frame-matched NPU coverage, advancing run counter, at
  least 95% host/device class agreement and raw-score delta <=3. Large CDC/RPS
  scratch buffers moved to reserved SRAM3; the clean linked image retains
  396,264 bytes of VL53L9 heap. Firmware and Python synthetic builds pass;
  physical NPU HIL and persistent XMODEM installation remain pending.
- Stage 09 now performs an `RPS ON`/`RPS STATUS` preflight before importing
  TensorFlow or collecting frames. It rejects stale SRAM images and NPU init
  failures immediately and records the diagnostic in `hil_validation.log`.

### 2026-08-21

- Added a fast Non-Secure development lane. It invokes the generated makefile
  incrementally without producing the large disassembly listing, preserves the
  firmware version, and can load the raw image into SRAM2 through its Secure
  alias while retaining ELF symbols for interactive GDB. The loader reaches
  Secure `main()` by loading the known-good FSBL ELF in DEV boot and letting it
  load Secure from external Flash before replacing the Non-Secure RAM image, so
  TrustZone and board initialization remain representative. Reset intentionally
  returns to the DEV-boot ROM without touching external Flash.
- Added an automated final Non-Secure release lane. It accepts an explicit
  `current + 1` version, builds and signs only Non-Secure, creates the signed
  `.n6fw`, auto-detects CN8, sends XMODEM-CRC 1K blocks with bounded retries,
  waits through trial confirmation, and verifies the running `version` command.
  `PackageOnly` restores the tracked version and does not modify hardware.
- Verified the incremental build, heap/image guards, version transaction,
  STM32 v2.3 signing, `.n6fw` generation, and XMODEM CRC self-test. Hardware
  probing confirmed that Flash boot closes N6 debug access as designed. The
  corrected DEV-boot helper then loaded the FSBL, stopped at Secure `main()`,
  replaced and verified Non-Secure in SRAM, reached Non-Secure `main()`, and
  detached in 13.4 seconds without a rebuild. CN8 returned `Firmware version:
  8`, confirming that the new RAM image was running. Physical XMODEM transfer
  and rollback validation remain pending. CubeMX Generate Code is not required.

### 2026-08-18

- Fixed the reintroduced VL53L9 first-frame transform error `-14`. The exact
  programmed ELF left only 353,512 bytes between `_end` and `_sstack`, below
  the transform's measured 356,688-byte allocation set even before malloc
  metadata. Sensor initialization and the complete first I3C DMA frame had
  already succeeded, confirming that this was SRAM pressure rather than a
  VL53L9CX communication or wiring fault.
- Replaced the GC9A01 startup screen's separate 4,096-byte clear buffer and
  5,656-byte text bitmap with one shared 404-byte DMA row buffer. Reduced the
  USBX parent ThreadX pool from 64 KiB to 56 KiB while preserving its 32 KiB
  system arena and 16 KiB control-task stack. The clean-linked image now leaves
  371,240 bytes for the C heap.
- Added a pre-signing build guard requiring at least 360 KiB between `_end` and
  `_sstack`. Clean-built all three contexts as firmware version 8, regenerated
  the trusted images and signed update package, and programmed and verified all
  five external-NOR regions without a full erase. Post-reset ToF/CDC validation
  still requires returning BOOT1 to external-Flash boot position.

### 2026-08-01

- Added 50-column by 50-row, five-second NATI LAB identification screens to the
  FSBL, Secure runtime, and Non-Secure application. The application banner uses
  the version generated by `build_and_sign.ps1`. Added `-BootChainOnly` to
  install the FSBL and Secure banners without touching application slots or A/B
  metadata.
- Made USART1/ST-LINK the exclusive diagnostic output. CN8 CDC now contains
  only the control menu, command replies, XMODEM traffic, and the explicitly
  requested depth map. The map starts disabled, is enabled by `MAP ON`, and
  remains visible until Enter returns to the menu.
- Fixed the FSBL stopping immediately after printing pending metadata. Its
  1 KiB boot-record work item was on the 2 KiB MSP while the nested manifest,
  SHA-256, and PKA verification path was active. The work item now uses static
  FSBL storage, and stage-by-stage signature, header, and image-hash diagnostics
  make candidate validation observable. `program_flash.ps1 -FsblOnly` can
  install this recovery without overwriting either application slot or update
  metadata.
- Fixed the VL53L9 first-frame transform returning `-14` after the firmware
  update additions. The linked image left 356,872 bytes for the C heap while
  the transform's measured allocation set needs about 356,688 bytes before
  malloc metadata. Reducing the ThreadX application pool from 192 to 160 KiB
  retains roughly 40 KiB beyond its active stacks and adds 32 KiB of transform
  heap headroom; the IOC and generated configuration now agree.
- Fixed the authenticated manifest path exceeding the 2 KiB Secure MSP limit.
  GCC stack reports showed a 1304-byte `SecureFirmwareUpdate_Begin` frame;
  together with the nested SHA-256 final/update/transform path and the NSC
  wrapper, worst-case static usage exceeded MSPLIM before the PKA operation
  could start. The 1 KiB boot-record work item now lives in Secure static
  storage, reducing the measured `Begin`, `Finalize`, and `ConfirmBoot` frames
  to 288, 224, and 280 bytes respectively.
- Fixed the first physical XMODEM transfer stalling at the start. A valid
  manifest previously caused Secure `Begin` to erase the entire 1 MiB inactive
  slot synchronously before XMODEM could ACK that block. Secure now authenticates
  and opens the session immediately, then erases the inactive slot lazily in
  64 KiB sectors during bounded writes. Added COM6 breadcrumbs for the first raw
  XMODEM bytes, manifest entry, write progress/failures, and repeated CRC
  handshakes, plus a raw-mode handoff for bytes sharing the command's CDC chunk.
  The initial CRC request window is now two minutes, so choosing the package in
  a desktop file dialog does not expire the receiver after only 16 seconds.
- Fixed a second manifest-stage stall in the Secure NSC boundary. Secure
  intentionally suspends its SysTick while NonSecure runs, but the updater
  wrappers did not resume it before entering PKA and XSPI HAL calls. Their
  timeout loops could therefore never expire. Every update NSC entry now resumes
  the Secure HAL timebase for the bounded operation and suspends it again before
  returning to NonSecure.
- Fixed Secure updater initialization stopping at PKA stage 4. The Secure
  application now assigns the PKA Secure/non-privileged RIF attributes before
  starting the updater, keeps that ownership in the system isolation table,
  and resets/releases the accelerator after enabling its clock. If PKA startup
  still fails, COM6 reports its RIF attributes, RCC enable/reset registers,
  CR/SR, and CPU CONTROL value before normal Non-Secure boot continues.
- On-hardware diagnostics then showed PKA `CR.EN=1` with `SR.INITOK=0`.
  STM32N6 requires the RNG to be initialized and AHB-clocked before PKA can
  operate, including ECDSA verification. The shared crypto initialization now
  starts a Secure-owned RNG before PKA in both FSBL and AppliSecure, and reports
  a distinct RNG stage with RIF/RCC/CR/SR diagnostics if that prerequisite fails.

### 2026-07-31

- Fixed the first on-hardware update-branch boot failure. The FSBL log proved
  that both images copied correctly, but Secure stopped while initializing the
  update service. LRun had left XSPI2 in memory-mapped mode, while the Secure
  writer needs indirect-command mode. The FSBL now aborts mapping through the
  ExtMem driver before the Secure jump and reports that handover on COM6.
- Split Secure updater initialization into explicit XSPI, XSPIM, ExtMem/SFDP,
  and PKA stage codes. A failed updater now remains fail-closed and unavailable
  without bricking the normal authenticated application boot.
- Added an authenticated, transport-independent firmware-update architecture.
  CN8 USB CDC enters raw XMODEM-CRC mode through the exact
  `Start UART Firmware Update` command (or `update`), pauses map/ToF traffic,
  and streams byte arrays without dynamic allocation.
- Added 1 MiB Non-Secure A/B slots, two alternating CRC-protected metadata
  sectors, ECDSA-P256 manifest verification with the STM32 PKA, streaming and
  read-back SHA-256, strict bounds/header/vector checks, increasing-version
  enforcement, pending/trial state, five-second application confirmation, and
  automatic rollback after an unconfirmed reset.
- Kept XSPI2, PKA, update policy, flash writes, and metadata activation in the
  Secure context behind CMSE-checked NSC calls. The FSBL independently verifies
  every signed candidate before selecting it.
- Added development signing-key/package tools and automatic `.n6fw` creation to
  the full build. Factory programming now resets both metadata copies to Slot A
  so stale update state cannot survive a normal reflash.
- Build-verified FSBL, Secure, and Non-Secure with zero errors, generated fresh
  STM32 trusted images and a versioned update package, and documented that
  hardware XMODEM/trial/rollback validation is still pending. The existing
  `-nk` BootROM image flow remains a documented production-security limitation.
- Raised the USB CLI task from priority 12 to priority 9. When transform
  throughput is below the 10 fps acquisition rate, the priority-10 ToF
  processor can remain continuously ready and previously starved the CLI even
  though the CDC RX callback had accepted Enter. The CLI now runs at the CDC
  worker priority, handles the short input burst, and blocks again while the
  ToF processor continues. Added one-shot COM6 breadcrumbs for the first CDC
  input and the transition into console mode.
- Added a documented, allocation-free `menu.c/.h` command engine. It accepts
  fragmented input, waits for Enter, performs longest-prefix dispatch through
  a constant function-pointer table, passes the complete line to the handler,
  and emits one normalized CRLF-terminated reply through an application
  callback. The existing USB CLI now uses this table instead of its previous
  monolithic command dispatcher.
- Added static 192-byte command and 768-byte reply buffers, CR/LF/CRLF and
  backspace handling, discard-until-Enter overflow behavior, and a documented
  unknown-command handler. No packet or parser allocation was introduced.
- Clean-built FSBL, Secure, and Non-Secure after the menu integration and
  generated fresh version-2.3 trusted images successfully.
- Added [GUIDE.md](GUIDE.md), a from-scratch learning path covering the
  NUCLEO-N657X0-Q CubeMX setup, all four security/boot contexts, VL53L9CX
  driver import and N6 port, asynchronous I3C/ThreadX architecture, USB CDC
  integration, signing, programming, post-generation audits, and staged
  troubleshooting.
- Clean-built and signed FSBL, Secure, and Non-Secure after the rare-event
  hardening changes, then programmed and verified all three external-NOR
  regions successfully.
- Confirmed on real NUCLEO-N657X0-Q hardware that the resulting image boots from
  external Flash and that the integrated VL53L9CX I3C-DMA pipeline, USB CDC,
  and terminal output work correctly.
- Reclassified I3C DMA and the ANSI USB renderer from “awaiting verification”
  to working-on-hardware status.
- Recorded the remaining validation boundary: long-duration load, repeated USB
  attach/detach, and deliberate queue/callback/I3C fault injection have not yet
  been claimed as completed.

### 2026-07-30

- Added bounded rare-event handling for USB and ToF/I3C. USB TX callback waits
  now time out after five seconds and trigger manager-owned, capped data-plane
  recovery without reusing the in-flight static slot.
- Added sticky USB diagnostic flags and cumulative counters for unavailable
  sends, slot exhaustion, queue-full, callback timeout, transfer errors, and
  ThreadX worker-synchronization failures. A periodic manager health event
  reports them outside callback context, while `usb status` exposes the complete
  history.
- Checked USB worker event-flag, queue-receive, and completion-semaphore return
  values. CDC line-parameter bursts are now coalesced into a counter so they
  cannot consume the manager queue needed by lifecycle and error events.
- Added an ISR-safe I3C/GPIO diagnostic snapshot with HAL error/state, EVR,
  control/RX/TX DMA states, completion/IRQ counts, and ThreadX event-post
  failures. Synchronous descriptor/DMA-start failures and ThreadX event
  wait/clear failures are now retained separately. Failed ToF waits print the
  complete snapshot before stopping.
- Added sticky platform-event fallback and separately counted/rate-limited ToF
  raw-slot queue invariant failures. An invalid processing-queue receive can no
  longer spin silently.
- Fixed callback-mode CDC starvation. USBX creates additional internal
  Bulk-IN and Bulk-OUT class threads; their default ThreadX priority was 20,
  below the continuously runnable priority-10 ToF processor. Live RAM counters
  showed two queued maps, one submitted transfer, zero completed bytes, and
  zero callbacks. The class workers now run at priority 8 with 8 KiB stacks;
  the USBX system pool and its parent byte pool were enlarged accordingly.
- Added a one-shot CDC diagnostic message scheduled three seconds after each
  successful class activation. A ThreadX timer only posts an event; the USB
  manager performs the readiness check and static-slot enqueue in thread
  context. The message is discarded when CDC is no longer configured.
- Gated every TX slot allocation on both the active session and the USBX
  `UX_DEVICE_CONFIGURED` state. Disconnect still invalidates the session and
  flushes all queues, so producers cannot accumulate stale output while the
  host is absent.
- Changed the build/sign helper to clean-build NonSecure every time. This is
  required because CubeIDE can retain stale linked USBX middleware objects
  after `ux_user.h` changes; an earlier incremental image therefore kept the
  old priority-20 class threads even though the header had been corrected.
- Fixed the combined asynchronous VL53L9 register read. Two separate calls to
  `HAL_I3C_AddDescToFrame()` do not append descriptors: the second call resets
  the first frame. The address-write and repeated-start payload-read
  descriptors are now prepared together in one two-descriptor HAL frame.
- Routed `EXTI9_IRQn` explicitly from Secure to the Non-Secure vector table.
  The EXTI line had already been marked Non-Secure, but its NVIC target was
  still Secure, so the new event-driven ToF acquisition task could miss every
  PD9 falling edge and report `sensor interrupt timeout`.
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

1. Use `tof status` to record an exact long-window processed-frame rate and
   confirm approximately 10.0 fps rather than relying only on smooth visual
   operation.
2. Run a multi-hour soak test with the CDC terminal open and verify that USB
   backpressure never stops sensor acquisition.
3. Test repeated CN8 attach/detach and verify that initialization and data-plane
   recovery are idempotent.
4. Deliberately inject queue-full, lost-callback, and I3C/DMA error conditions
   and verify the new counters, sticky diagnostics, and capped recovery paths.
5. Move CubeMX-managed outside-USER changes into custom files or a reproducible patch process.
6. Physically install X-NUCLEO-67W61M1 before enabling its feature flag.
7. Verify ST67 SPI handshaking and NCP firmware before enabling Wi-Fi/BLE.
8. Repeat CN8 XMODEM installation across both A/B directions and validate
   interruption during transfer, invalid signature/version rejection, and
   reset-before-confirm rollback on hardware. One signed installation and
   confirmed trial boot have passed.
9. Integrate the future Wi-Fi/BLE downloader as another producer for the existing
   Secure byte-array update interface; it must not own flash or boot metadata.
10. Replace `-nk` and the workstation development key with a protected,
    provisioned production signing/root-of-trust and anti-rollback chain before
    treating physical update security as production-ready.
11. Follow the numbered release sequence: Stage 09 installs the one-time Secure
    boot chain, Stage 10 loads the exact integrated model into SRAM, Stage 11
    runs HIL against that live SRAM image, and Stage 12 installs the persistent
    update only after the HIL fingerprint passes.

## 14. The project's golden rule

The IOC describes hardware ownership and the generated skeleton. The hand-written code describes product behavior. After every Generate Code operation, verify that both still agree about pins, TrustZone, interrupts, memory regions, task stacks, middleware callbacks, and feature flags.
