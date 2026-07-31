# Instructions for Codex and future agents

Read this file and [README.md](README.md) before modifying the project.

This file is the engineering contract for future work. It records the current state, safety rules, CubeMX boundaries, known deviations from vendor code, verification requirements, and how to communicate changes to the user.

## 1. Project objective

Continue developing the STM32N657 firmware that combines:

- External-NOR boot through an FSBL.
- TrustZone with Secure and Non-Secure applications.
- VL53L9CX through I3C1 and DMA.
- USB CDC through USBX, UCPD1, and TCPP0203.
- ST67W611M1 through SPI5, Wi-Fi, and BLE.
- A future authenticated BLE OTA mechanism.

Work must be technically correct and educational. Explain in Hebrew what changed, why it changed, how it was verified, and what risk remains.

## 2. Current state that must be preserved

- FSBL, Secure, and Non-Secure boot from external NOR.
- The ST-LINK diagnostic UART works on USART1, PE5/PE6, at 115200 baud.
- The VL53L9CX initializes and returns complete 54×42 frames.
- The VL53L9CX runs as a 100 ms autonomous stream. A priority-7 acquisition
  task and priority-10 processing task exchange three fixed 14,842-byte raw
  slots, so the next DMA acquisition overlaps transform/rendering.
- The steady-state sensor path uses PD9 falling-edge EXTI and I3C TX/RX DMA.
  Tasks wait on ThreadX event flags posted from HAL callbacks; initialization
  remains allowed to use blocking vendor calls.
- The 2026-07-31 signed build was programmed and verified in external NOR. The
  user confirmed successful external-Flash boot, VL53L9CX operation, USB CDC,
  and terminal output with the hardened static RX/TX and diagnostic paths.
- Treat that result as a functional hardware checkpoint, not as proof of a
  multi-hour soak, repeated attach/detach endurance, or deliberate fault
  injection into every recovery branch.
- Non-Secure Debug C and C++ use `-O3` with `-g3` debug information.
- The ToF processing task uses a 96 KiB stack, acquisition uses 16 KiB, and the ThreadX application pool is 192 KiB.
  The largest visible active optimized chain is about 34 KiB; the much larger
  slow rate-normalization and resize functions shown in `.su` are bypassed by
  `fast_mode` and native 54×42 operation.
- The USBX device-control task currently uses a conservative 16 KiB stack and a 32 KiB pool.
- The demonstrated USB stack overflow was in the USB-PD CAD task, not the USBX task.
- The USB-PD CAD task uses an 8 KiB stack and a 16 KiB pool.
- CN8 Type-C attachment is now detected correctly on CC2 and reaches the USB Device START notification path.
- The generated PCD MSP code is supplemented, inside USER CODE, by the reset/PHY sequence from ST's official NUCLEO-N657X0-Q CDC example.
- The FSBL enables VDDA, VDDIO2 through VDDIO5, and VDDUSB before `HAL_Init()`, matching the official CDC example.
- USBX now waits for a real CAD attach notification. The earlier CAD-independent fixed START is no longer active.
- USB CDC works: Windows creates a separate host-assigned COM port and complete
  ANSI-map transfers have been observed. Never assume a fixed COM number.
- USB CDC uses one priority-8 lifecycle manager and priority-9 RX/TX workers.
  USBX callback transmission mode owns bulk OUT reception; the RX callback
  publishes fixed 512-byte slots. Only the TX scheduler submits
  `write_with_callback`, and it waits for a completion semaphore before the
  next submission.
- The CDC steady-state path performs no allocation. Storage is fixed: eight
  768-byte control TX slots, two 48 KiB map TX slots, and sixteen 512-byte RX
  slots. All slots are session-tagged and passed through bounded pointer queues.
- The ST67 shield is not currently installed. APP_ST67W6X_ENABLED must remain 0U unless the user explicitly confirms that the module is attached.
- Authenticated Non-Secure firmware installation is implemented and build-
  verified: CN8 USB CDC XMODEM feeds a transport-independent Secure byte-array
  service, which writes the inactive A/B slot and uses pending/trial/confirmed
  metadata with rollback. Physical transfer and rollback testing are pending.
- Wi-Fi/BLE download transport is not implemented. When added, it must reuse the
  Secure installer and must not access XSPI2 or boot metadata directly.

## 3. CubeMX rules

1. project/N6.ioc is the source of truth for CubeMX configuration.
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
| AppliNonSecure/USBPD/App/usbpd_dpm_core.c | OS_CAD_STACK_SIZE maps to N6_USBPD_CAD_STACK_SIZE |
| AppliNonSecure/USBPD/App/usbpd_dpm_core.c | UCPD register diagnostics, wake counter, and 250 ms polling fallback |
| AppliNonSecure/Core/Startup/startup_stm32n657x0hxq.s | Early Debug_UART_StartupTrace calls |
| FSBL/Core/Src/extmem.c | Exact image-size and dynamic Non-Secure source hooks |
| FSBL/Middlewares/ST/STM32_ExtMem_Manager/boot/stm32_boot_lrun.c/.h | Dynamic authenticated A/B source selection; functional vendor edit outside USER blocks |
| AppliSecure/Core/Src/main.c | A diagnostic trace between generated calls |
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
| AppliNonSecure/Core/Src/tof_app.c | Separate acquisition/processing loops, static raw slots, transform, status, and rendering |
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
| Tools/New-FirmwareSigningKey.ps1 | One-time local development P-256 key generation; private blob stays ignored |
| Tools/New-FirmwareUpdatePackage.ps1 | Signed `.n6fw` manifest plus trusted Non-Secure image |
| Tools/program_flash.ps1 | External-NOR programming including both default metadata sectors |
| FlashImages | Signed programming artifacts |
| ThirdParty/ST67W6X_Network_Driver | Git-tracked ST67 source subset used by CubeIDE, with license files |
| .local-dependencies | Ignored local SDK archives, PDFs, examples, backups, and diagnostics; never required by a clean clone |

The Git repository root is `project`. Do not restore build references to the
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
powershell.exe -ExecutionPolicy Bypass -File .\project\Tools\build_and_sign.ps1 -FirmwareVersion 1
~~~

Firmware versions are positive and strictly increasing relative to the confirmed
image. Never reuse a released version number. The local private update key under
`.local-dependencies/keys` is ignored and must never be committed or printed.

If the headless IDE hangs, a direct make.exe build from the Debug directory is acceptable. The resulting binary must still be passed through STM32_SigningTool_CLI and the new trusted image must be written to project/FlashImages.

After CubeMX Generate Code, explicitly audit these known multi-context losses:

- FSBL must keep `HAL_BSEC_MODULE_ENABLED` and `HAL_XSPI_MODULE_ENABLED`.
- FSBL and AppliSecure must keep `HAL_PKA_MODULE_ENABLED`; AppliSecure must
  also keep `HAL_XSPI_MODULE_ENABLED`.
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
- While the radio feature remains disabled, generated GPIO configuration must
  route PD9 as falling-edge EXTI9 and leave PE9 as a plain input. Verify the
  EXTI9 handler still reaches `HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_9)` and the
  callback routes it to `platform_notify_gpio_interrupt()`.
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

Current task sizing:

| Task | Priority | Stack |
|---|---:|---:|
| USB-PD CAD | 1 | 8 KiB |
| Firmware confirmation | 6 | 2 KiB; one-shot after a five-second trial window |
| ToF Acquisition | 7 | 16 KiB |
| ToF Main Thread (processing) | 10 | 96 KiB |
| USBX Device App Main Thread | 8 | 16 KiB |
| USB CDC RX worker | 9 | 12 KiB, statically allocated |
| USB CDC TX worker | 9 | 12 KiB, statically allocated |
| ST67 WiFi BLE | 11 | 8 KiB, currently disabled |
| USB debug CLI | 9 | 6 KiB |

## 9. Known ST defects and non-defects

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
- All TX allocation is gated by both an active CDC session and
  `UX_DEVICE_CONFIGURED`. No producer may enqueue while CDC is absent, and a
  disconnect must flush and release every queued or reserved static slot.
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

- APP_ST67W6X_ENABLED remains 0U while the shield is absent.
- In disabled mode, do not create its task, initialize the compatibility layer, or call W6X initialization.
- Enabling the radio requires verification of SPI5, CS, CHIP_EN, BOOT, SPI_RDY, DMA, and NCP firmware.
- Never implement OTA by overwriting the active image in place.
- Future Wi-Fi/BLE OTA must feed the existing Secure Begin/Write/Finalize byte
  interface. Preserve inactive-slot writes, CMSE range checks and Secure copies,
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

- Communicate with the user in clear Hebrew, retaining useful English technical terms.
- Lead with the conclusion from the evidence.
- Explain why the evidence supports the conclusion.
- When a physical action is required, give one precise instruction involving the jumper, Reset button, cable, or terminal.
- Do not request Generate Code for a C-only change.
- Do not request programming before build and signing succeed.
- State what the next log is expected to contain.
- Be explicit about confidence: confirmed bug, strong candidate, suspected issue, adaptation, or workaround.
- Update README and its change log after architectural changes, boot/fault fixes, interface changes, or programming-flow changes.

## 15. Definition of done

A firmware change is complete only when:

- The relevant context builds without errors.
- The correct image is signed again.
- It is documented whether Generate Code is required.
- The user receives short, precise verification instructions.
- Work on USB does not intentionally break ToF, and vice versa.
- Features without attached hardware remain disabled.
- Outside-USER changes are recorded.
- README and the change log are updated when the change is significant.
