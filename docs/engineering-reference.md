# Detailed engineering constraints

Read the relevant section before changing its subsystem. [AGENTS.md](../AGENTS.md)
is the current task contract. Dated measurements and pending tests below are
historical evidence, not a fresh board-status check or a request to resume work.

## 3. CubeMX rules

1. N6.ioc is the source of truth for CubeMX configuration.
2. An agent may edit the IOC when required.
3. Do not pretend to operate the CubeMX GUI for the user. After changing the IOC, ask the user to run Generate Code.
4. State clearly whether Generate Code is required.
5. After generation, inspect relevant files because CubeMX may overwrite manual changes.
6. Prefer USER CODE blocks whenever possible.
7. KeepUserCode does not protect assembly files, arbitrary middleware files, or manual edits outside protected blocks.
8. Do not run Generate Code merely because a C source file changed.
9. Verify that the AppliNonSecure `.cproject` include paths and `.project`
   linked resources still point to `ThirdParty/ST67W6X_Network_Driver` after
   generation. Do not restore references to an ignored local SDK package.

### 3.1 Known CubeMX-managed changes outside USER CODE

These require explicit review after every Generate Code:

| File | Manual change |
|---|---|
| AppliNonSecure/Core/Src/main.c, stm32n6xx_hal_msp.c, stm32n6xx_it.c | APP_GC9A01_DISPLAY_ENABLED guards SPI4 handles/init/MSP, LCD GPIO, DMA channel5 and IRQ handlers. Switch lives in config.h and defaults undefined. Preserve guards after Generate Code; SPI5/radio and shared GPIOE/GPDMA clocks stay active. |
| AppliNonSecure/Core/Src/stm32n6xx_hal_timebase_tim.c | TIM6 sleep clock, effective IRQ priority at most14 above ThreadX PendSV15, unused RCC getter removed, cold HAL_InitTick Os. IOC remains unchanged; explicitly audit these project timebase deviations after Generate Code. A34/B35 controls and A36+ hardware wall-time/timeout evidence are in docs/xip-hal-timebase-root-cause_HE.md |
| AppliNonSecure/USBPD/App/usbpd_dpm_core.c | OS_CAD_STACK_SIZE maps to N6_USBPD_CAD_STACK_SIZE |
| AppliNonSecure/USBPD/App/usbpd_dpm_core.c | UCPD register diagnostics, wake counter, and 250 ms polling fallback |
| AppliNonSecure/Core/Startup/startup_stm32n657x0hxq.s | Early Debug_UART_StartupTrace calls |
| AppliNonSecure/STM32N657X0HXQ_XIP.ld | Alternative physical-slot linker selected only by Build-Xip. Secure cached handoff configures XIP SAU/RISAF12/MPU/NS instruction cache; ordinary RAM startup remains unchanged |
| FSBL/Core/Src/extmem.c | Exact image-size and dynamic Non-Secure source hooks |
| FSBL/Middlewares/ST/STM32_ExtMem_Manager/boot/stm32_boot_lrun.c/.h | Dynamic A/B source and pre-jump XSPI handover hook; functional vendor edits outside USER blocks |
| AppliSecure/Core/Src/main.c | Diagnostic trace plus Neural-ART clocks, RIF/RISAF, CACHEAXI, and NPU interrupt ownership |
| AppliSecure/Core/Inc/partition_stm32n657xx.h | SAU region 1 extends through `0x243FFFFF` so Non-Secure can access SRAM2, NPU SRAM3-6, and CACHEAXI RAM |
| ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.c | The high-priority SPI worker sleeps one tick after each eight-packet continuous burst so a stuck-high SPI_RDY cannot starve ThreadX; re-importing X-CUBE can overwrite it |
| Drivers/STM32N6xx_HAL_Driver/Inc/stm32n6xx_hal_i3c.h and Src/stm32n6xx_hal_i3c.c | Per-handle frame-complete marker; multiple DMA completion waits for every channel, and TC/abort races finish once. Header layout affects both S/NS builds; preserve on HAL refresh |
| ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_ble.c, w61_at_common.c/.h, w61_at_api.h, modem_cmd_handler.c/.h | Notification waits for prompt before payload and terminal response afterward; immediate AT-lock admission returns BUSY before announcing raw data, preserving the admitted execution budget. Short command writes and unfinished raw transactions fence further AT text until module restart. Preserve on SDK refresh |
| ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c | Scan-only asynchronous diagnostics separate TX-lock wait/held ticks, without logging AT arguments; preserve when refreshing vendor code |
| ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c, w61_at_api.h, w61_at_ble.c | BLE initial OK/prompt/Recv/SEND OK and earlier payload OK ownership; preserve fast rejection, payload phase and actual missing-response fence on SDK refresh |
| ThirdParty/ST67W6X_Network_Driver/Core/w6x_wifi.c, Driver/W61_at/modem_cmd_handler.c/.h, w61_at_common.c, Driver/W61_bus/spi_iface.c; debug_uart.c/.h | CONNECTED settling uses budgeted AT admission, never parser sleep; raw guarded admission is BUSY with no write/fence. SPI terminal capture is scalar only, no formatter on its 768-byte stack. Preserve on SDK refresh |
| ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_wifi.c, w61_at_api.h; Api/w6x_types.h; Core/w6x_wifi.c | Scan scratch allocation under AT ownership, callback-borrowed lifetime/release, bounded parser-locked failure cleanup and pre-dispatch status initialization; preserve on vendor refresh |
| Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_pcd.c | Temporary Non-Secure-only USB initialization stage logs |
| Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_ll_usb.c | Temporary Non-Secure-only core-reset register and timeout logs |

The CAD stack macro currently lives in a preserved USER block in usbpd_dpm_conf.h, but the line that consumes it is outside a protected block. CubeMX may restore:

~~~c
#define OS_CAD_STACK_SIZE 1024
~~~

If this happens, restore the N6-specific mapping before building.

### 3.2 Imported files without USER blocks

Files imported from X-CUBE packages are not necessarily CubeMX-owned. The VL53L9 platform layer has no useful USER blocks but is intentionally ported to STM32N6 and ThreadX. Do not replace it blindly with the original H563 demo file.

## 4. Important files

| File or directory | Responsibility |
|---|---|
| PLAN_WIFI_MODULE.md | Approved T01 radio architecture, implementation order, memory/security gates, and validation plan |
| hil_tests | Non-destructive host-side HIL automation, BLE discovery reports, and hardware-free utility self-tests |
| N6.ioc | Pins, clocks, contexts, interrupts, and middleware configuration |
| FSBL/Core/Src/main.c | External-NOR mapping and boot flow |
| FSBL/Core/Src/extmem.c | Exact signed-image size calculation and STM32 image-header inspection |
| FSBL/Core/Src/firmware_boot.c | Redundant metadata, candidate verification, A/B trial selection, confirmation fallback, and rollback |
| FSBL/Middlewares/ST/STM32_ExtMem_Manager/boot/stm32_boot_lrun.c | LRun copy/jump middleware with local diagnostics |
| Common/Update | Shared manifest, A/B metadata format, SHA-256, ECDSA-P256 verifier, and tracked public key |
| AppliSecure/Core/Src/main.c | TrustZone, RIF/RISAF, cached vectors, Non-Secure handover |
| AppliSecure/Core/Src/secure_firmware_update.c | Secure inactive-slot writer, read-back authentication, version policy, and atomic metadata |
| Secure_nsclib/secure_nsc.h | CMSE-checked Begin/Write/Finalize/Abort/Confirm interface |
| AppliNonSecure/Core/Src/main.c | HAL and peripheral initialization |
| AppliNonSecure/Core/Src/stm32n6xx_hal_msp.c | USB HS clocks, VDDUSB, and the N6-specific PHY reset/release sequence |
| AppliNonSecure/Core/Src/app_threadx.c | Application task creation |
| AppliNonSecure/Core/Inc/app_features.h | Feature flags, especially ST67 |
| AppliNonSecure/Core/Src/gc9a01.c and Core/Inc/gc9a01.h | Asynchronous GC9A01 SPI TX primitive, GPIO control, cache maintenance, and ISR completion bridge |
| AppliNonSecure/Core/Src/display_app.c and Core/Inc/display_app.h | Dedicated display task logic, controller initialization, DMA/event waits, clear, and startup text |
| AppliNonSecure/Core/Src/tof_app.c | Separate acquisition/processing loops, static raw slots, transform, status, and rendering |
| AppliNonSecure/Core/Src/tof_image_processing.c | Table-driven, allocation-free depth-map filters and parameter validation |
| AppliNonSecure/Core/Src/rps_ai.c and Core/Inc/rps_ai.h | Frozen preprocessing, STAI initialization, synchronous Neural-ART run, and result/status contract |
| AppliNonSecure/Core/Src/npu_shared_memory.c and STM32N657X0HXQ_LRUN.ld | Explicitly cleared upper-SRAM3 workspace that preserves the VL53L9 SRAM2 heap |
| AppliNonSecure/AI | Stage-08-installed generated network, embedded weights, matched STAI/LL_ATON runtime, device cache layer, and vendor licenses |
| AppliNonSecure/Utilities/vl53l9-common/platform/platform_utils.c | STM32N6 GPIO/I3C DMA callbacks and ThreadX event bridge |
| AppliNonSecure/Utilities/vl53l9-common/vl53l9/vl53l9_platform.c | Persistent combined-transfer and TX-DMA contexts |
| AppliNonSecure/Drivers/BSP/Components/vl53l9/vl53l9.c | Sensor driver plus local stage-level asynchronous frame API |
| AppliNonSecure/Core/Src/debug_uart.c | Independent ST-LINK diagnostics |
| AppliNonSecure/Core/Inc/menu.h and Core/Src/menu.c | Allocation-free chunked line parser, prefix table, handler dispatch, and CRLF reply API |
| AppliNonSecure/Core/Src/debug_cli.c | USB CDC command table, handlers, echo, and console-mode behavior |
| AppliNonSecure/Core/Src/xmodem_receiver.c | Allocation-free XMODEM-CRC state machine |
| AppliNonSecure/Core/Src/firmware_update.c | Transport-to-Secure byte-stream adapter and five-second boot confirmation |
| AppliNonSecure/Core/Src/usb_cdc_transport.c | Static CDC slots, RX/TX queues, callbacks, sessions, flow/error counters |
| AppliNonSecure/Core/Src/wifi_ble_app.c | Optional ST67 application task |
| AppliNonSecure/USBX/App/app_usbx_device.c | USB Device state machine and USBX initialization |
| AppliNonSecure/USBPD/App/usbpd_dpm_core.c | Type-C CAD task |
| Tools/build_and_sign.ps1 | Full build, STM32 image signing, default metadata, and versioned update package |
| Tools/Build-NonSecureIncremental.ps1 | Fast incremental Non-Secure ELF/map/bin build without the disassembly listing |
| Tools/Debug-NonSecureRam.ps1 | DEV-boot FSBL handoff, verified local Secure SRAM1 replacement, verified Non-Secure SRAM2 replacement, and GDB handoff |
| Tools/Install-NonSecureUpdate.ps1 | Explicit next-version Non-Secure build/sign/package/XMODEM/install/boot verification |
| Tools/Send-Xmodem.ps1 | Auto-detected CN8 XMODEM-CRC 1K sender with CRC self-test, retries, and finalization timeout |
| Tools/N6-DevCommon.ps1 | Shared STM32 tool discovery, build guards, heap check, version transaction, and CDC discovery |
| Tools/New-FirmwareSigningKey.ps1 | One-time educational P-256 key generation; the designated development private blob is tracked so the complete teaching project can be shared |
| Tools/New-FirmwareUpdatePackage.ps1 | Signed `.n6fw` manifest plus trusted Non-Secure image |
| training/README_HE.md | Educational, resumable ToF rock-paper-scissors capture/training/Neural-ART architecture and safety gates |
| training/scripts | One Python entry point per capture, validation, training, quantization, N6 generation, HIL, and upload stage |
| training/*.bat | Guided Windows entry points plus resumable model-build orchestration |
| Tools/program_flash.ps1 | External-NOR programming including both default metadata sectors |
| Tools/Factory-Provision.ps1 | Explicit full-NOR erase, complete image programming/verification, and CN8 boot-version verification |
| FlashImages | Signed programming artifacts |
| ThirdParty/ST67W6X_Network_Driver | Git-tracked ST67 source subset used by CubeIDE, with license files |
| radio_firmware | Self-contained ST67 mission-T01 2.0.106 updater, QConn dependencies, binary licenses, hashes, and Hebrew guide |
| .local-dependencies | Local SDK archives, PDFs, examples, backups, and diagnostics remain ignored; only the explicitly designated educational update-signing key is tracked |

Run tools from the current repository root, `N6/project`. Do not restore build references to the
ignored full X-CUBE-ST67W61 package. CubeIDE include paths and linked resources
must resolve through `ThirdParty/ST67W6X_Network_Driver` so a clean clone can
build without local downloads.

## 5. Build and signing rules

After a source change, build at least the context that changed. Build every context if a change affects:

- FSBL or Secure.
- Linker scripts or memory layout.
- Image addresses or maximum sizes.
- Secure/Non-Secure interfaces.
- Startup behavior.
- TrustZone ownership.

Preferred command:

~~~powershell
powershell.exe -ExecutionPolicy Bypass -File .\Tools\build_and_sign.ps1 -FirmwareVersion 1
~~~

For compilation confined to Non-Secure, use:

~~~powershell
powershell.exe -ExecutionPolicy Bypass -File .\Tools\Build-NonSecureIncremental.ps1
~~~

This builds without hardware access. RAM startup is a separate operation:
use [the checked demo loader](ram-demo-loader_HE.md) when persistent writes
must be avoided. The legacy `Debug-NonSecureRam.ps1` executes FSBL selection
without the metadata-writer guard and is not that protected route.
A persistent release still requires a verified next version, signing and
an explicitly intended installation; never use installation to test compilation.

The fast incremental lane is not valid after changing `ux_user.h` unless
`-Clean` is supplied. It is never valid as a substitute for the full build when
FSBL, Secure, startup, linker layout, image addresses, TrustZone ownership, or
the Secure/Non-Secure interface changed.

Firmware versions are positive and strictly increasing relative to the confirmed
image. Never reuse a released version number. This is an explicitly educational
project: `.local-dependencies/keys/firmware-update-p256-private.blob` is a shared
development key and is intentionally tracked so another learner can reproduce
the update flow. It must never be treated as a production secret or production
root of trust. Do not print its contents in logs or normal user-facing output.

If the headless IDE hangs, a direct make.exe build from the Debug directory is acceptable. The resulting binary must still be passed through STM32_SigningTool_CLI and the new trusted image must be written to project/FlashImages.

After CubeMX Generate Code, explicitly audit these known multi-context losses:

- FSBL must keep `HAL_BSEC_MODULE_ENABLED` and `HAL_XSPI_MODULE_ENABLED`.
- FSBL and AppliSecure must keep `HAL_PKA_MODULE_ENABLED` and
  `HAL_RNG_MODULE_ENABLED`; AppliSecure must also keep
  `HAL_XSPI_MODULE_ENABLED`.
- AppliSecure must claim `RIF_RISC_PERIPH_INDEX_PKA` as Secure/non-privileged
  before `SecureFirmwareUpdate_Init()`; the generated system isolation table
  must preserve the same ownership. PKA MSP initialization must perform a
  clock-enable followed by a reset/release sequence.
- The shared crypto initializer must initialize and keep the RNG AHB clock
  running before enabling PKA. RNG remains Secure/non-privileged and both FSBL
  and AppliSecure `.project` files must retain `stm32n6xx_hal_rng.c`.
- FSBL and AppliSecure `.project` / `.cproject` files must retain the shared
  `Common/Update` sources and includes. AppliSecure must retain its linked
  ExtMem manager and HAL XSPI/PKA sources.
- The shared HAL `Inc` and `Src` directories must contain the union of the
  modules required by all contexts. Restore unchanged vendor files only from
  STM32Cube FW N6 V1.4.0.
- AppliNonSecure `.cproject` must include
  `../../Drivers/BSP/STM32N6xx_Nucleo`.
- AppliNonSecure Debug C and C++ optimization must remain `-O3`; restoring
  `-O0` makes the measured transform take about 264 ms and prevents 10 fps.
- AppliNonSecure `.project` must link `stm32n6xx_hal_uart.c` and
  `stm32n6xx_hal_uart_ex.c` for the custom ST-LINK VCP logger.
- FSBL `SystemClock_Config()` must use `RCC_HSE_BYPASS_DIGITAL`; USB cannot run
  when Generate Code returns it to `RCC_HSE_OFF`.
- `Tools/build_and_sign.ps1` intentionally rejects a generated
  `OS_CAD_STACK_SIZE` that is not mapped to `N6_USBPD_CAD_STACK_SIZE`; do not
  bypass this guard. The 1 KiB default has been reproduced as `STKOF` in the
  TCPP0203 ADC/RCC initialization path.
- `N6.ioc` must retain CDC ACM transmission mode enabled
  (`USBX.UX_DEVICE_CLASS_CDC_ACM_TRANSMISSION_DISABLE=0`). Generated
  `ux_user.h` must not define `UX_DEVICE_CLASS_CDC_ACM_TRANSMISSION_DISABLE`.
- With the current enabled radio build, PE9/SPI_RDY owns both edges of EXTI9
  and ToF polls PD9 with a bounded wait. If the radio feature is disabled,
  generated GPIO configuration must instead route PD9 as falling-edge EXTI9
  and leave PE9 as a plain input. Verify the shared handler and callbacks keep
  matching the selected owner.
- The Secure RIF USER block must keep both
  `HAL_EXTI_ConfigLineAttributes(EXTI_LINE_9, EXTI_LINE_NSEC | EXTI_LINE_NPRIV)`
  and `NVIC_SetTargetState(EXTI9_IRQn)`. The line attribute does not change the
  Secure NVIC target; omitting the latter makes the Non-Secure ToF task time
  out even though PD9 reaches its active-low state.

Never ask the user to program an image until:

- Compilation succeeded.
- Linking succeeded.
- The correct binary was signed again.
- The signing tool reported success.

Do not accidentally deliver an older trusted image after rebuilding an ELF.

## 6. Programming and hardware safety

- Do not program hardware unless the user requested it or the current workflow explicitly reached the programming step.
- Do not use -FullErase without a clear reason and explicit awareness that it erases all external NOR contents.
- Programming mode: BOOT0=1-2, BOOT1=2-3.
- External-Flash boot mode: BOOT0=1-2, BOOT1=1-2.
- Image addresses are fixed:
  - FSBL: 0x70000000.
  - Secure: 0x70100000.
  - Non-Secure Slot A: 0x70180000, 1 MiB.
  - Non-Secure Slot B: 0x70280000, 1 MiB.
  - Boot metadata sectors: 0x703E0000 and 0x703F0000, 64 KiB each.
- Do not change an address or region size without updating the FSBL, linker scripts, signing limits, programming script, and documentation together.

## 7. TrustZone rules

Every peripheral used by Non-Secure must pass three checks:

1. The SAU/partition configuration marks the target region Non-Secure.
2. RIF/RISC does not block the peripheral.
3. GPIO and interrupt attributes target Non-Secure.

Preserve Non-Secure access for:

- USART1 and GPIOE pins 5/6 for diagnostics.
- I3C1, GPDMA1, and ToF GPIOs.
- USB1_OTG_HS and UCPD1.
- I2C2 and ADC12 for TCPP0203.
- SPI5, GPIO, DMA, and EXTI for ST67 when the feature is enabled.

Do not read Non-Secure vectors through an alias that becomes inaccessible after RISAF. The current code caches MSP and Reset_Handler before isolation. Preserve this behavior until the underlying alias behavior is fully resolved.

## 8. RTOS and memory rules

- In ThreadX, a smaller numeric priority means a higher priority.
- Do not reduce stack sizes based on intuition.
- Use GCC .su data, ThreadX stack analysis, or measured high-water marks.
- Optimization can change both speed and individual stack-frame sizes. The
  current `-O3` transform is faster but GCC reports very large automatic arrays
  in its optimized call tree; never infer stack safety from `-O0` results.
- 0xEFEFEFEF is the ThreadX stack-fill pattern.
- CFSR_NS bit 0x00100000 is STKOF on Cortex-M55.
- Match PSP to a byte-pool address before changing a task's stack.
- Leave room for alignment, exception stacking, and possible floating-point context.
- Current large stacks are safe bring-up values, not final memory optimization.
- The linked Non-Secure image must leave at least 360 KiB between `_end` and
  `_sstack` for the VL53L9 first-frame allocation set and malloc metadata.
  `build_and_sign.ps1` enforces this before signing.

Current task sizing:

| Task | Priority | Stack |
|---|---:|---:|
| USB-PD CAD | 1 | 8 KiB |
| Firmware confirmation | 6 | 2 KiB; one-shot after a five-second trial window |
| ToF Acquisition | 7 | 16 KiB |
| GC9A01 display | 8 | 4 KiB; suspends after the startup screen |
| ToF Main Thread (processing) | 10 | 96 KiB |
| USBX Device App Main Thread | 8 | 16 KiB |
| USB CDC RX worker | 9 | 12 KiB, statically allocated |
| USB CDC TX worker | 9 | 12 KiB, statically allocated |
| ST67 Radio Manager | 9 | 8 KiB, active in dedicated SRAM4 pool |
| ST67 Wi-Fi control | 11 | 6 KiB, active in dedicated SRAM4 pool |
| ST67 Cloud Relay | 9 | 8 KiB, fixed lower SRAM4 storage outside the byte pools; M5.3/M5.4 RAM HIL pending |
| USB debug CLI | 9 | 6 KiB |

## 9. Known ST defects and non-defects

### SPI5 abort recovery contract

SPI5 master RX automatic suspension remains disabled. The 2026-10-04 MASRX
experiment passed two live-register BLE probes but failed after a fresh boot
with SUSP/timeouts and lost replies. Its IOC/initializer changes were reverted;
do not promote the two transient PASS results to configuration acceptance.
Generate Code is not required for the C-only recovery change alone.
The 2026-10-06 candidate sets GPDMA1 SPI5 RX channel 11 to DMA_HIGH_PRIORITY
in N6.ioc and its MSP initializer; TX channel 10 stays LOW/HIGH_WEIGHT. Do not
raise every channel to HIGH. Two fresh MTU-247 RAM probes received 300/300
pings with ToF active and zero SPI errors/timeouts/recoveries. The source build
booted normally and passed 100-frame CRC/NPU/bit-exact preprocessing HIL with
radio scan preflight. Generate Code is REQUIRED/PENDING for the IOC change.
The ordinary source build also received 150/150 idle BLE replies (p95 141 ms,
max 172 ms). Later Wi-Fi association and paired Cloud CLI remained live, with
zero SPI errors/timeouts, but ToF stopped at frame 2687 before Cloud pairing.
I3C retained HAL_I3C_ERROR_SIZE/BUSY_TX_RX while RX DMA was READY with its
abort callback still armed; the event wait timed out without an error callback.
The initial trigger is not established: the preceding GDB halt could affect
timing. This is not a Cloud image PASS or a ToF recovery fix. Cloud stack
sentinel high-water was 3504/8192 bytes for this HTTP/CLI phase, excluding ToF
send validation. The precise competing DMA/bus actor, boot repeatability and
Cloud/MAP load remain unverified. No clock/port/burst/stack/pool capacity change
was made. Keep investigating bounded local recovery under the existing plan.

`spi_port_abort()` must clean both SPI5 normal-mode DMA channels even when
HAL SPI abort has already cleared the DMA-request bits or returns an error.
Local DMA deinit/init preserves the parent link. A failed SPI abort may require
an SPI5 peripheral reset after the channels stop. Reuse the READY handle for
HAL_SPI_Init; setting it RESET reruns the generated MSP initializer (480-byte
GCC frame) on the 768-byte SPI worker stack. Do not reset the shared DMA
controller or NCP to hide this local failure. GDB counters distinguish DMA/SPI
reinitializations and failures. On 2026-10-04 RAM recovery was exercised with
zero reinitialization failures and 660/768 observed stack bytes used. The
108-byte untouched prefix is a narrow measured margin, not worst-case proof.
SPI RX overrun's precise DMA/bus cause and full-load validation remain open;
this is not Cloud-contention acceptance or evidence of heap exhaustion.

The 2026-10-08 board-local `spi_port.c` CS-low interval wait compares elapsed
SysTick ticks modulo LOAD+1 and has a bounded software fallback. Do not restore
the vendor WAIT_FROM absolute-endpoint loop: when its computed endpoint is
zero, it requires sampling VAL==0 and can starve the SPI worker. Non-reset raw
CPU inspection observed that zero-endpoint loop during loss of USB/UART
responses; this does not establish the initiating cause of the separate SPI
RX HAL error. `hil_tests/test_spi_cs_hold.py` checks skipped-zero reload,
normal/reloaded intervals and frozen/disabled timers against the actual wait
function. The microsecond conversion rounds up using SystemCoreClock/1e6.

### 9.1 Strong bug candidate: 1 KiB CAD stack

The official STM32Cube FW_N6 V1.4.0 USB CDC example uses a 1024-byte CAD stack.

Measured Debug frames include:

- USBPD_CAD_Task: 104 bytes.
- BSP_USBPD_PWR_VBUSInit: 24 bytes.
- PWR_TCPP0203_Configure_ADC: 440 bytes.
- HAL_RCCEx_PeriphCLKConfig: 488 bytes.

The visible total already exceeds 1024 bytes. Hardware reported STKOF during cable attachment, with PC and LR in this exact path and PSP in the USB-PD pool.

Treat the 1024-byte default as unsafe for this Debug configuration.

### 9.2 Confirmed X-CUBE-53L9A1 V1.0.0 bug

The original platform_acknowledge_event function is missing a break after PLATFORM_I3C_IBI_EVT. The local port adds the break. Do not reintroduce the original fall-through.

### 9.3 Confirmed X-CUBE-53L9A1 asynchronous lifetime bug

The original `vl53l9_read_async()` passes pointers to automatic descriptor,
transfer, address, control, and status objects into an asynchronous HAL path
and then returns. HAL retains `pXferData` while DMA is active, so those objects
must outlive the call. The local port uses one persistent context containing a
combined address-write/repeated-start/read transfer. Do not restore the
stack-local version or split the address phase back into a blocking transfer.

### 9.4 Do not mislabel these as ST bugs

- The 96 KiB ToF stack balances the measured active `-O3` path with the large
  dynamic heap required by the transform. Do not size it from `.su` entries
  without proving that those functions execute in the selected profile.
- The 16 KiB USBX stack is conservative. The proven overflow was in CAD.
- Fixed CDC startup independent of CAD was a diagnostic workaround and is no longer active.
- The ST67 FreeRTOS compatibility layer is a project integration requirement.
- The FSBL weak size hook is designed for application override.
- Earlier all-zero CC readings were resolved by fixing the CAD task stack; attachment is now proven on CC2.
- The H563 VL53L9 demo requiring a port to N657 is expected.

## 10. ToF rules

- The 2026-10-07 candidate keeps map/dataset, selected channels/processing,
  pause and exclusive destination in `TOF_DesiredState_t`. Recovery must not
  replay a stale copy over a newer command. Only acquisition may reset I3C1,
  DMA 0/1/2 and XSHUT. Retain failed DMA destinations until reset succeeds;
  never flush/reseed processing/display-owned raw slots. Reject old raw
  generations. Three attempts are capped until thirty complete healthy
  acquisitions; running success requires a fresh complete acquisition.
  Native C fault/state tests and signing passed. SRAM XSHUT injection restored
  USB/Cloud intent and a fresh frame in 310--381 ms: 40 CRC-valid USB records
  and 20 further accepted Cloud frames. An uninjected Cloud-phase fault also
  recovered. BLE delivered 15 further CRC-valid images after non-halting
  injection, then an AT prompt failure fenced the radio; retain all failed
  BLE reports and do not claim BLE acceptance. Physical persistent-fault and
  newer-command tests, current-candidate Stage 11/image-route and endurance
  remain open. See docs/tof-desired-state-recovery.md.

- Do not change the transform pipeline without testing a complete frame and metadata.
- Preserve timeouts so a missing sensor cannot block the complete system forever.
- PD9 and PE9 share EXTI line 9; do not enable both paths blindly.
- While APP_ST67W6X_ENABLED is 0U, PD9 owns falling-edge EXTI9 and PE9 is a
  plain input. Enabling the radio requires an explicit new ownership strategy,
  preferably I3C IBI for ToF or a deliberate interrupt-routing policy.
- Send the ANSI map as a complete terminal frame to avoid tearing.
- CLI map-off should hide output while acquisition continues.
- Preserve autonomous synchronization and the 100 ms frame period unless a
  deliberately slower profile is requested; 10 fps is the current sensor
  maximum.
- Only `tof pause` should stop the autonomous ranging stream.
- Preserve the local missing-break fix in platform_acknowledge_event.
- Preserve the persistent `g_async_i3c_context`; asynchronous HAL descriptors
  and every buffer they reference must remain valid until DMA completion.
- A VL53L9 register read is one two-descriptor HAL frame. Call
  `HAL_I3C_AddDescToFrame()` once with both the register-address TX descriptor
  and payload RX descriptor (`NbFrames == 2`). A second call does not append;
  it resets the HAL frame state and causes an asynchronous I3C error.
- Preserve the single I3C owner: only the ToF acquisition task may start a
  steady-state sensor transaction. Each start must acknowledge stale RX/TX and
  error flags, then wait for the matching callback event before reusing the
  persistent context.
- `HAL_I3C_Ctrl_MultipleTransfer_DMA()` completes through
  `HAL_I3C_CtrlMultipleXferCpltCallback()`, not the ordinary RX callback. Both
  are intentionally bridged to the RX event because the local multiple
  transfer is a register read.
- Never print from an I3C/GPIO callback or ISR. Preserve the platform
  diagnostic snapshot (HAL error/state, EVR, DMA states, completion/IRQ
  counters, and event-post failures), then format it from the ToF task after a
  failed wait.
- Preserve synchronous I3C-start diagnostics. Descriptor construction and DMA
  start may return `HAL_BUSY`/`HAL_ERROR` without invoking the HAL error
  callback; record the start stage, HAL status, and peripheral/DMA snapshot
  before returning the platform error.
- Preserve `g_platform_evt` as a sticky fallback. If a callback ran but
  ThreadX rejected its event-flags post, `platform_wait_for_event()` must still
  consume the acknowledged transaction's sticky completion/error bit.
- Never silently retry a ThreadX queue-object error. Normal ToF backpressure may
  evict an unprocessed ready frame, but an impossible empty free+ready state or
  a failed blocking processing receive must be counted, rate-limited on UART,
  and moved to the explicit ToF fatal state.

## 11. USB and USB-PD rules

- ST-LINK VCP and CN8 USB CDC are two different COM ports.
- UART diagnostics must remain operational even if USBX faults.
- Non-Secure ST-LINK UART accepts one-key read-only status snapshots and one
  periodic watch at a time (`?`, `a`, `r/t/c/u`, `R/T/C/U`, `0`). RX ISR only
  queues bytes; formatting and status getters run in the UART diagnostic
  thread. Keep it separate from the USB/BLE command broker, redact secrets,
  and do not make a status getter wait indefinitely on another subsystem.
- Initialize PCD, USBX Device stack, and HAL_PCD_Start from task context after ThreadX starts.
- Preserve the N6 USB1 HS-PHY reset/configuration/release sequence in the MSP USER block. CubeMX's generated clock and VDDUSB setup is not the complete sequence used by ST's board example.
- Preserve the explicit `RCC_PERIPHCLK_USBPHY1` configuration in the MSP USER block. The generated code fills `UsbPhy1ClockSelection` but requests only `RCC_PERIPHCLK_USBOTGHS1`, so the HAL otherwise skips the PHY mux field.
- Preserve the corrected CDC FIFO sizing after HAL_PCD_Init: Rx 0x200 words,
  Tx EP0 0x10, Tx EP1 0x100, and Tx EP2 0x20. EP1 carries 512-byte High-Speed
  bulk packets; ST's 0x10-word reference value is too small for the HAL
  non-DMA transmit loop and causes the first CDC write to wait forever.
- Preserve the PCD-handle clear before every attach-cycle initialization.
- Start the PCD only from the USB-PD CAD attach notification. Do not restore the earlier unconditional START unless deliberately isolating the CAD path again.
- Preserve USBX CDC callback transmission mode. Do not re-enable
  `UX_DEVICE_CLASS_CDC_ACM_TRANSMISSION_DISABLE`.
- Preserve `UX_THREAD_PRIORITY_CLASS == 8` and the 8 KiB generic USBX thread
  stack. Callback mode runs Bulk-IN/Bulk-OUT in USBX-owned class threads; the
  USBX default priority 20 is starved by the continuous priority-10 ToF
  processing task, leaving a submitted TX packet permanently in flight.
- Always clean-build NonSecure after changing `ux_user.h`. CubeIDE can retain
  stale USBX middleware objects during an incremental build; the local
  `Tools/build_and_sign.ps1` script deliberately enforces the clean build.
- All TX allocation is gated by an active CDC session, `UX_DEVICE_CONFIGURED`,
  and host DTR. Windows may leave a CDC class configured after closing the COM
  handle; no application producer may enqueue until DTR establishes the host
  session. A close must stop high-rate producers, and a physical detach must
  flush and release every queued or reserved static slot.
- The USBX read callback must remain short: acquire a static RX slot, copy the
  completed payload, post one pointer, and return. Parsing belongs to the RX
  dispatcher/CLI, never the callback.
- Preserve single TX submission ownership: only the TX scheduler may call
  `USB_CDC_LL_WriteAsync`. It must not submit the next buffer before the write
  callback posts the completion semaphore for the current sequence.
- The TX completion wait is bounded to five seconds. On timeout, never reuse
  the in-flight buffer or resubmit into USBX. Latch diagnostics, let the worker
  quiesce, and have the USB manager abort/restart the data plane. Recovery is
  capped at three attempts per physical CDC activation.
- Preserve the periodic USB health event. Timer context may only post the
  manager event; it must not allocate, format, log, or call USBX. The manager
  atomically consumes sticky rare-event flags and prints cumulative counters.
- Queue/slot backpressure is not an ISR logging site. Counters retain full
  history; diagnostics report the latched category once per health pass.
- Check USB worker event-flag, blocking queue-receive, and completion-semaphore
  results. Preserve the worker-synchronization counter/sticky flag and manager
  recovery path; a rejected callback wakeup must not become an invisible
  infinite wait.
- Coalesce CDC line-parameter notifications into a counter. Host setup bursts
  carry no application payload and must not fill the lifecycle/error queue.
- Keep USBX class callbacks free of UART formatting. Manager-queue failures
  must retain total, per-event-type, last-type, and last-ThreadX-status data for
  later manager-thread reporting.
- All application TX text must pass through `USB_CDC_Transport_Send`. Complete
  maps must use Acquire/Commit/Cancel so the renderer writes directly into a
  static 48 KiB map slot. All RX data must be consumed through
  `USB_CDC_Transport_Receive`.
- Keep `menu.c/.h` platform-independent and allocation-free. The CLI task is
  the sole owner of each `Menu_t`; do not invoke `Menu_Process()` concurrently
  from USBX callbacks or another task.
- Keep the USB CLI at a higher scheduling priority than the priority-10 ToF
  processing task. The processor may remain continuously ready while dropping
  stale raw frames; a lower-priority CLI can therefore starve even after the
  CDC RX callback has accepted Enter.
- Command entries are prefix/handler pairs. Preserve delimiter-aware
  longest-prefix matching, full-line dispatch only after CR/LF/CRLF, and
  discard-until-Enter behavior after input overflow.
- Menu handlers receive the complete normalized command line in task context.
  Static textual responses should use `Menu_Reply()`, which builds one
  CRLF-terminated response in the caller-owned reply buffer and submits it
  through `App_Console_Write()` without allocation.
- Preserve the static slot counts and sizes (control TX 8×768, map TX 2×48 KiB,
  RX 16×512), bounded pointer queues, semaphores, and session tags unless a
  measured redesign updates code and documentation together. ToF map enqueue
  must remain non-blocking.
- Do not introduce packet allocation, a CDC byte pool, or a full-map copy into
  the steady-state path.
- On detach, invalidate the transport session and quiesce both workers before
  deinitializing PCD/USBX. Do not leave a worker blocked on an instance that is
  being destroyed.
- TCPP component type 0x00 is valid for TCPP03 and is not automatically an error.
- Green LD2 with a CN8 cable indicates VBUS/power presence, not successful CC detection or USB enumeration.
- Record PID, product string, serial string, and endpoint changes.
- Test repeated start/stop before treating detach handling as production-ready.

## 12. ST67W6X rules

- M5.2–M5.4 source now isolates the Cloud pump in its own priority-9 worker.
  Radio Manager publishes scalar network readiness; it must never run Cloud
  DNS/socket/protocol processing. Runtime pair/enable/disable/reconnect/unpair
  use a four-entry fixed by-value control queue and return admission status;
  socket close and pairing filesystem operations belong to the worker.
  Cloud status getters return an atomic cached snapshot without waiting.
  RAM startup and connected Cloud browser images/exclusive BLE/USB handovers
  passed on 2026-10-06. Full network stack high-water, BLE-under-Cloud failure
  latency and endurance gates remain open; do not accept Milestone 5 globally.
- User-authorized 2026-10-06 contract: exactly one remote image destination,
  last request wins (USB, BLE or Cloud). The processing task advances the
  active route only after all USB MAP slots and the wireless snapshot idle.
  A requested/active mismatch disables new publications. Cloud-only snapshots
  enter WAIT_CLOUD directly; BLE-only snapshots enter READY. Release only
  after the old consumer stops reading, including socket close/cancellation.
  CLI sessions and the local display remain independent. Do not restore
  simultaneous BLE+Cloud fanout or add another image buffer for switching.
- BLE notification protocol is prompt -> payload -> terminal OK/ERROR.
  Notification AT admission must be nonblocking: return BUSY before any raw
  announcement when the mutex is held. The existing pump retains its pending
  fragment and retries; do not consume the execution deadline waiting for a
  Cloud/Wi-Fi AT owner or increase buffers to hide contention.
  Do not wait for an initial OK. Do not release protocol ownership on an
  incomplete raw transfer and then send another AT command: the modem can
  consume that command as binary payload. The bounded fail-closed fence must
  survive ordinary retries; module restart/reinitialization clears it.

- APP_ST67W6X_ENABLED is 1U for the current attached-shield phase-1 test.
- APP_ST67W6X_BLE_GATT_ENABLED is 1U; two logical UART services and their
  bounded transport queues are implemented. The CLI service owns an independent
  5,176-byte session in SRAM4 and is attached to the shared command definitions;
  the DEBUG output producer remains detached.
  RAM HIL on 2026-09-14 found `N6-MAINT-B8FB`, connected at MTU 247, validated
  both services/four characteristics and CCCDs, and confirmed advertising
  restart after disconnect. Keep the vendor-baseline advertising sequence;
  explicit advertising-parameter plus scan-response overrides made
  `W6X_Ble_AdvStart()` return `W6X_STATUS_ERROR` and remain deferred.
- APP_ST67W6X_WIFI_SERVICES_ENABLED is 1U. Keep scan/connect/disconnect and IP
  queries serialized in the dedicated Wi-Fi control worker; callbacks may only
  snapshot bounded results/state and signal completion. Never print or issue
  W6X control calls from a Wi-Fi callback.
- Accept Wi-Fi credentials on USB CDC, BLE and Cloud by explicit demo policy.
  Password entry must remain hidden, absent from command history, and cleared
  from CLI/manager buffers immediately after use.
- `radio_firmware/contract.json` is the host/target NCP version contract. Stage
  11 must compare the running `radio info` SDK with it and scan the BLE
  CLI-service advertisement when BLE is enabled. If Wi-Fi is enabled later,
  the same stage must also require station status plus a successful scan.
- Preserve mission profile T01 and SDK 2.0.106 until the driver and contract
  are deliberately upgraded together. Any vendor-binary replacement requires
  updated SHA-256 entries, retained ST binary/QConn notices, and an end-to-end
  Stage 10/11 hardware run.
- BLE callbacks may only snapshot event metadata and enqueue/signal bounded
  work. Runtime W6X BLE control and advertising recovery execute in the existing
  control worker through the generation/revision-checked mailbox; Radio submits
  and consumes results and owns the bounded notification pump.
- The Radio Manager now reconciles BLE desired state against command ACKs and
  periodic BLEINIT?/BLECONN? observations. ADV has no AT state query: keep
  `UNKNOWN` distinct from last acknowledged state, cap retries, and never
  claim command ACK proves RF advertising. Do not reset the whole ST67 NCP
  from a BLE-only fault while Wi-Fi/Cloud may be active; external HIL scanning
  is the RF-level check.
- Preserve the item-9 stream contract: CLI RX 8x512 bytes, CLI TX 8x768 bytes,
  DEBUG RX 2x512 bytes but disabled by policy, and DEBUG TX 8x256 bytes. All
  storage is allocated from the SRAM4 radio byte pool. Every connect and
  disconnect advances the generation; stale slots are purged. CLI producer
  waits are capped at 50 ms, DEBUG TX is non-blocking, notification calls use
  a 100 ms timeout with at most three attempts, and the manager services one
  `MTU-3` fragment per stream per cycle.
- Preserve the item-10 broker contract: CDC, BLE and Cloud never share line,
  history, prompt, CR/LF, or output state. Shared command handlers execute
  serially in the priority-9 CLI thread. BLE RX is drained in bounded bursts;
  Cloud records use explicit ACK, sequence and CRC. Signed XMODEM raw mode
  belongs only to the requesting session and feeds the existing Secure
  installer. Do not add transport-specific command allowlists.
- Platform training extension (2026-10-21 M4/M5): legacy display formats1-4
  retain sender-side encoding. Training format5 is a complete lossless N6DF4
  record packed by the ToF producer while the exact same-frame NPU tensor is
  still live; raw u16 depth plus tensor/header fits the existing9072-byte
  snapshot. USB and wireless use one encoder. Do not re-encode it as a display
  image or allocate a second payload buffer. Existing generation/route fencing,
  GATT fragmentation and bounded queues remain. M5 Cloud retains that snapshot
  until a matching post-storage ACK; unknown replies retry identical bytes.
  Control sessions are time/rate/count/volume bounded and use existing tokens.
  M4 final25-record reconnect HIL passed; M5 Wi-Fi acceptance is recorded in
  docs/platform-upgrade-20261021.md only after its real check completes.
- Preserve the BLE ToF image contract: Notify UUID `7a1e0004-b5a3-f393-e0a9-
  e50e24dcca9e`, version-3 56-byte little-endian header, selectable RAW/UINT16/UINT8/JPEG,
  header and payload CRC32, and one SRAM4 snapshot. Capture the matching NPU
  status with pixels; never fetch the latest inference in a transmitting worker. See docs/wireless-image-codec.md.
  For legacy display formats1-4, only the transmitting Radio/Cloud worker encodes; the producer snapshots float32. Snapshot the selected transformed channel
  before `tof_processing_workspace` is reused. While a frame is in flight, drop
  new frames; never queue partial sensor-frame state. Service at most one image
  fragment per Radio Manager cycle so CLI/XMODEM cannot be starved.
- The current No-Input/No-Output BLE setting and capability-token Cloud relay
  are development-only. The demo intentionally exposes the same commands on
  every CLI transport; do not present this as a production authorization model.
- In disabled mode, do not create its task, initialize the compatibility layer, or call W6X initialization.
- Enabling the radio requires verification of SPI5, CS, CHIP_EN, BOOT, SPI_RDY, DMA, and NCP firmware.
- The SPI transfer worker waits for EXTI-ready or host-TX events while idle;
  do not restore the 20 ms idle `SPI_RDY` level poll without an explicit
  architecture decision. Active-transaction handshake level checks remain.
- Keep the AT modem's queued SPI packet alive until every byte is consumed.
  A short destination read must never free and discard the packet tail;
  incomplete AT records stay in the parser's bounded assembly buffer. Keep
  that fixed buffer in the modem object/application SRAM, not the constrained
  64 KiB radio byte pool: SRAM HIL showed the pool nearly exhausted when the
  two-MTU assembly buffer was dynamically allocated there.
- Never implement OTA by overwriting the active image in place.
- BLE XMODEM and any future Wi-Fi delivery must feed the existing Secure
  Begin/Write/Finalize byte interface. Preserve inactive-slot writes, CMSE range checks and Secure copies,
  SHA-256 plus ECDSA-P256, strictly increasing versions, atomic alternating
  metadata, trial confirmation, and rollback.
- XSPI2, PKA, boot metadata, and key-policy decisions remain Secure. A transport
  task may deliver bytes and report status; it may not weaken or duplicate the
  installer in Non-Secure code.
- The current update signature protects remote package authenticity, but the
  development `-nk` image flow and replaceable compiled public key are not a
  production physical root of trust. Production requires authenticated BootROM
  images, protected key provisioning, and protected anti-rollback state.

## 13. Debugging method

1. Request a complete log from Reset rather than only the final fault line.
2. Identify the last completed stage: FSBL, Secure, startup, HAL, ThreadX, or a task.
3. Map PC and LR against the exact ELF that was programmed.
4. Decode status-register bits; HardFault alone is not a diagnosis.
5. Match PSP to its memory pool.
6. Change one important variable per iteration.
7. Add a breadcrumb immediately before and after the suspected call.
8. Build, sign, and confirm that the user programmed the new image.
9. Remove or reduce noisy polling only after the underlying issue is understood.

## 14. Communication style

- Code, comments, docstrings, identifiers, generated runtime labels, diagnostics,
  errors, CLI/terminal output and code examples must be English only. Hebrew
  belongs in user-facing explanations and prose documentation, not code/output.

- Communicate with the user in clear Hebrew, retaining useful English technical terms.
- Lead with the conclusion from the evidence.
- Explain why the evidence supports the conclusion.
- When a physical action is required, give one precise instruction involving the jumper, Reset button, cable, or terminal.
- Do not request Generate Code for a C-only change.
- Do not request programming before build and signing succeed.
- State what the next log is expected to contain.
- Be explicit about confidence: confirmed bug, strong candidate, suspected issue, adaptation, or workaround.
- Update the operational README and append a concise entry to `CHANGELOG.md`
  after architectural changes, boot/fault fixes, interface changes, or
  programming-flow changes. Do not read the historical body just to append.

## 15. Definition of done

A firmware change is complete only when:

- The relevant context builds without errors.
- The correct image is signed again.
- It is documented whether Generate Code is required.
- The user receives short, precise verification instructions.
- Work on USB does not intentionally break ToF, and vice versa.
- Features without attached hardware remain disabled.
- Outside-USER changes are recorded.
- README and `CHANGELOG.md` are updated when the change is significant, without
  loading the historical body unless that history is required.
