# STM32N657 ToF, USB CDC, and ST67W611M1 Project

The guided, resumable ToF rock-paper-scissors pipeline is documented in
[training/README_HE.md](training/README_HE.md). It includes the
`DATASET STREAM ON|OFF|STATUS` binary CDC protocol, capture/validation/model
BAT stages, atomic embedded-weight deployment, frame-exact Neural-ART HIL, and
`VIEW_LIVE.bat`, which atomically swaps complete CRC-validated raw/model frames
at full stream rate without relying on progressive ANSI terminal rendering,
`DUAL_COM_DEBUG.bat`, which captures USB CDC and ST-LINK UART in separate live
text files while accepting CLI and BLE-probe commands, plus
`ANALYZE_TRAINING.bat`, which creates an offline Hebrew HTML explanation of
the dataset, learning curves, confusion matrix, saved-frame Keras/TFLite
predictions, quantization contract, and current HIL report without modifying
the model or firmware.

General host-driven hardware validation tools live in
[hil_tests/README.md](hil_tests/README.md). The first tool provides an
interactive BLE scan, selected-device connection, and complete GATT discovery
report without writing characteristics or changing firmware.

The 2026-10-07 ToF recovery candidate preserves explicit in-RAM desired state:
pause, map/dataset mode, image channels, processing and the exclusive destination.
Runtime sensor/I3C faults now trigger acquisition-owned I3C/DMA and XSHUT
reinitialization, with three bounded attempts and diagnostic logs. The failed
DMA slot is retained until reset succeeds; queued old generations are discarded
without reseeding processing/display-owned buffers. Running recovery is confirmed
only after a fresh complete acquisition; paused recovery keeps ranging off.
Thirty healthy frames replenish the retry budget. See
[docs/tof-desired-state-recovery.md](docs/tof-desired-state-recovery.md) for the
policy, native regression checks and hardware acceptance requirements. Build,
signing and ten native C fault/state tests pass. Physical SRAM sensor-reset
injection restored the selected USB/Cloud settings and fresh frames in 310--381 ms;
USB received 40 CRC-valid records and Cloud accepted another 20 frames. A real
uninjected Cloud-phase fault also recovered. BLE resumed 15 complete CRC-valid
images after a non-halting injection, then lost an AT prompt; BLE acceptance,
physical persistent-fault/new-command tests, frame-exact Stage 11 and endurance
remain open. This change is now included in the confirmed v9 Flash application;
the Cloud OTA evidence below does not close those separate acceptance gates.

The subsequent user-run Cloud v8 upload is not an installation PASS: the browser
timed out and live inspection found 450 of 451 blocks received, update still
active, no finalization and no reset scheduled. Inactive-slot payload writes
occurred; the active version was not verified as v8. See
[docs/cloud-update-20261007.md](docs/cloud-update-20261007.md) for evidence and
the sender's timeout/retry limitation.

The authorized OTA follow-up has a deployed browser/server retry fix,
correlated control metadata and a bounded Cloud output-drain barrier before
reset. Two partial uploads recovered from lost ACK/transient SPI errors. On
2026-10-08, the SysTick-zero CS-wait boundary was corrected, fixed v8 installed
via USB, and full Cloud v8-to-v9 verified: 452 blocks, EOT ACK, automatic Flash
boot, USB version 9 and Secure confirmation. The Cloud transfer took 352.898 s
from first block to EOT ACK, with zero sender timeouts. Wi-Fi/pairing needed
manual restoration; Cloud CLI/version and fresh ToF frames then worked.
See the same diagnostic report for evidence and the separate open acceptance gates.

The 2026-10-06 RAM repair uses one image destination: USB, BLE or Cloud.
The last `MAP ON`, USB dataset request, BLE ToF subscription, or Cloud pairing/
enable request wins. `tof status` shows requested/active destinations and drain
counters. Before changing the active destination, the ToF producer stops new
publications and waits for the old USB slots/wireless snapshot to be released.
CLI traffic remains available on all transports; the local SPI display is
independent. Turning the current destination off does not resume an older one.
Connected RAM HIL passed Cloud→BLE→USB→BLE→Cloud: twenty complete CRC-valid
BLE frames, twenty-five USB records with header/raw/model CRCs, no BLE images
during USB ownership, and no additional accepted Cloud images while BLE/USB
owned the route. The actual Cloud page rendered advancing 54×42 images before
and after the handovers. The first connected gate failed after AT-lock waiting
consumed the BLE notification deadline; notification admission now returns
BUSY immediately when another AT owner is active, retaining the fragment for
retry without announcing raw data. An admitted transfer keeps its execution
budget. The raw-transaction fence remains enforced. No buffer/stack/pool grew.
Build passed: NS binary 456632 bytes, C heap 415864 bytes (minimum 368640).
A prior offline USB capture passed 100 distinct raw/model CRC-valid records
and reached 6255 acquisitions with zero command/I3C failures. Network soak,
failure-latency/stack gates and CubeMX generation remain open. The tested
candidate is running in RAM with Wi-Fi and Cloud connected; Flash is unchanged.

Release-preflight update: the user requested version 8 in Flash. Its package
build/sign passed, but Stage 11 stopped at Wi-Fi-scan preflight (timeout then
error even after disabling Cloud); other AT queries failed while sensor/USB
remained live. This is an additional open radio fault, not a completed release.
Cloud is currently disabled. Fresh RAM startup and matching HIL are pending
physical BOOT selection; no v8 bytes have been installed in Flash.

Cloud pairing, CLI commands and actual ToF browser rendering were captured on
2026-10-06; see the connected image-route checkpoint above. An earlier paired
capture had no images because the sensor had already stopped before pairing.
The earlier HTTPS/T01 path failed at
`CIPSTART`; the Azure endpoint sent a 6603-byte TLS record, larger than ST's
documented 6144-byte T01 fragment limit. That is a strong compatibility
candidate, not a confirmed NCP error code. The current demonstration RAM build
instead uses **plaintext HTTP on port 80** to the same Azure host, without TLS
or the TLS-only SNTP prerequisite. It booted from RAM and displayed the HTTP
endpoint; subsequent connected RAM HIL verified pairing, Cloud CLI and ToF
images. Security validation remains open. See the execution history in
[docs/async-architecture-recovery-plan.md](docs/async-architecture-recovery-plan.md).
A [draft ST FAE requirement](docs/st67-t01-tls-interoperability-fae.md) records
the requested T01 TLS interoperability change and acceptance tests. It has not
been submitted to ST; the measured record-size mismatch remains a strong
hypothesis rather than an NCP-confirmed root cause.

ToF fault diagnosis is in progress. A prior RAM capture stopped after 1,507
acquired frames at `DSS map command (-1)`; the exact I3C/HAL substep was not
captured. The current RAM diagnostic build records command-phase counters in
`tof status`, detailed blocking-read HAL failures on COM6, and bounds the
previously unbounded post-TX HAL-state wait. A first sensor-only run passed
3,785 acquired frames and one Wi-Fi scan without reproducing the fault;
this is not a ToF recovery fix or Cloud image acceptance. On 2026-10-06,
acquisition stopped at frame 2687 during the 100-byte status DMA read.
Attach-only inspection found HAL_I3C_ERROR_SIZE, I3C BUSY_TX_RX, RX DMA READY
with an unconsumed abort callback/suspend request, and one event timeout with
no application error callback. This supports a completion/abort race; the
initial size-error trigger is unproven, and the preceding debugger halt may
have influenced timing. The earlier fatal loop stopped acquisition permanently.
The current repair defers multiple-transfer completion until I3C frame
completion AND all DMA channels finish, and reconciles DMA completion winning
an abort race. A later UART-only run characterized a separate blocking
register-address TX failure at frame 5103: HAL error `0x40` (FIFO overrun/
underrun), with no debugger halt. Runtime command-status reads now use DMA
and a persistent one-byte destination; the shared descriptor is not reused
until I3C and all DMA handles are idle. Initialization retains the blocking
vendor path. The 2026-10-07 candidate implements bounded local sensor recovery;
physical acceptance under M8.4a/M8.5 remains pending.

The BLE repair corrects notification ordering: wait for `>` before raw data,
then the terminal `OK`; there is no initial `OK`. Earlier host captures
contained AT command text on the image characteristic. An unfinished raw
transaction now fences further AT command writes until module restart, rather
than feeding the next command into that payload. These repairs add no task,
stack/pool enlargement, or second image snapshot.

The current demonstration source sets `APP_ST67W6X_CLOUD_USE_TLS=0` in
`AppliNonSecure/Core/Inc/app_features.h`. It transmits the pairing code,
bearer token, CLI commands/output, and ToF data without encryption or server
authentication; `cloud status` and COM6 warn about this. The TLS verification
flag now defaults to 1 so that a later TLS build is secure by default, but it
has no effect while HTTP is selected. Restore TLS and verify the certificate
before any security/customer-readiness claim or use of real secrets on an
untrusted network. A future signed build would inherit this unsafe HTTP flag
unless it is deliberately changed.

The self-contained ST67W611M1 NCP update lane is documented in
[radio_firmware/README_HE.md](radio_firmware/README_HE.md). It bundles the
licensed ST mission-T01 SDK 2.0.106 image, QConn Windows tool, integrity
contract, and a guided BAT that always attempts to restore the STM32 FSBL.

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
| Rock/paper/scissors Neural-ART | Working on hardware; Stage 11 validates frame-exact results, bit-exact preprocessing, bounded raw-score error, and tolerance-aware decision consistency |
| ST67 Wi-Fi/BLE/Cloud | Connected RAM HIL verified Cloud browser images and exclusive BLE/USB handovers. The demonstration relay uses plaintext HTTP. USB, BLE and Cloud share the CLI command table; Wi-Fi connect returns DHCP IPv4 and ToF uses an independent media channel. Endurance/failure-latency gates remain open |
| BLE XMODEM firmware update | Implemented over the CLI RX/TX characteristics and reuses the authenticated Secure A/B installer; physical CLI/GATT/ToF transport and repeated reconnect HIL pass, while a complete physical BLE firmware transfer is still pending |

### 1.1 Latest hardware validation

On 2026-09-25, a browser-driven BLE/Wi-Fi test reported a Secure fault after
`GOTIP` (`SFAR=0x00000EBC`). This is an open firmware diagnosis, not evidence
of failed STM32 silicon; a separate Python/WinRT BLE failure has not been
correlated. The Secure fault reporter now builds with Non-Secure SRAM4 stack
decoding and prints `EXC_RETURN`, stacked PC/LR/xPSR and fault registers, but
the diagnostic image has not yet been loaded because ST-LINK communication
failed initially. After reconnecting the ST-LINK USB cable it was loaded into
RAM, with external NOR unchanged. Radio/BLE initialized and five minutes of
idle USB pings passed 1040/1040; a separate ToF DSS-unmap error appeared before
any Wi-Fi request. The browser Wi-Fi/GOTIP scenario was not reproduced in that
run, so the PC/root cause and 20-cycle Wi-Fi/BLE acceptance test remain open.

A later long-running Wi-Fi/BLE session exposed a persistent notification
timeout: 4,138 consecutive BLE CLI TX timeouts, four queued messages, no
recovery, and a failed Wi-Fi state query. Its COM6 capture began after the
failure, so the initiating event remains unknown. The BLE link probe was
found to be suppressed by any queued TX, indefinitely in this failure mode.
It now permits a bounded probe after sustained TX contention and emits a
one-time SPI/pin snapshot to COM6. The image was loaded into RAM and the USB
CLI rebooted, but the fault path has not been physically retested; this is
not proof that the NCP or SPI transport recovered. No automatic
whole-NCP reset is enabled while Wi-Fi and Cloud workers share the driver.

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

On 2026-09-19, the Wi-Fi CLI passed physical SRAM HIL. A bounded scan found
the target WPA2 network, hidden password entry connected successfully, DHCP
returned a non-zero IPv4 address plus gateway and netmask, and a second scan
while connected preserved the link and address. During the repeat scan, ToF
continued at 6.4 fps, the Neural-ART classifier reported 1,294 runs with zero
errors, the display task remained ready, and BLE GATT remained ready and
advertising. The dedicated SRAM4 radio pool retained 21,056 bytes after the
test. External Flash and the persistent firmware version were not changed.

Later on 2026-09-19, the final Cloud-integrated SRAM image passed the complete
Stage 11 regression after a physical power cycle. The radio preflight found the
ST67 SDK 2.0.106, scanned 11 Wi-Fi networks, and rediscovered the
`N6-MAINT-B8FB` BLE service at -68 dBm. Stage 11 then captured 100 CRC-valid,
distinct ToF frames, matched 100/100 Neural-ART results, reproduced all 100
device input tensors bit-exactly in Python, and observed 30 distinct model
tensors. Class agreement and decision consistency were 100%, the maximum raw
score delta was 6, and the NPU reported zero errors. The VL53L9 command-status
poll is now a blocking one-byte I3C read after asynchronous command TX, avoiding
reuse of the shared async descriptor while its completion path may still refer
to the TX context; the bounded completion budget is 100 ms. External Flash was
not modified by this RAM HIL run.

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

On 2026-09-16, the RAM workflow was repeated after hardening CDC against the
Windows configured-but-closed state. Application TX/RX is now gated by DTR, so
leaving CN8 unopened no longer consumes all three data-plane recovery attempts
before Stage 12. Stage 10 reached ThreadX, and the extended Stage 11 passed 100
CRC-valid frames, 100/100 frame-matched Neural-ART results, bit-exact device/
Python preprocessing, NCP SDK 2.0.106 validation, and an external scan of the
`N6-MAINT-B8FB` CLI-service advertisement. A separate guided factory lane now
full-erases and verifies the entire external NOR before checking the booted
version through CN8.

On 2026-09-18, the physical BLE maintenance service passed a ten-cycle
connect/subscribe/unsubscribe/disconnect soak. Every connection negotiated MTU
247 and exposed the complete expected GATT contract; every enabled interval
delivered one complete CRC-valid 54x42 ToF frame, with zero assembler drops or
CRC errors, and no frame arrived during the one-second quiet check after each
unsubscribe. All ten disconnects were followed by a successful reconnect. Nine
first frames arrived in 1.21..1.34 seconds; one scheduling outlier took 3.864
seconds. This validates bounded repeated operation, not a multi-hour endurance
run or the still-pending physical BLE XMODEM installation.

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
source used by the build is vendored under `ThirdParty/ST67W6X_Network_Driver`.
The separate `radio_firmware` directory contains the licensed NCP/QConn binary
update set and SHA-256 contract. Together they keep both compilation and NCP
provisioning reproducible without the ignored local X-CUBE download.

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
- Main ThreadX application pool: 134 KiB when Wi-Fi/Cloud is enabled, 151 KiB
  for radio/BLE-only builds, and 159 KiB when radio support is disabled.

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
so the STM32 cannot route both pins through EXTI at the same time. In the safe
default build the radio is disabled: PD9 owns EXTI9 with a falling-edge trigger,
PE9 is a plain input, and the ToF ISR only posts a ThreadX event. In a radio
build, PE9 owns rising/falling EXTI9 for the ST transport and the ToF wait polls
the active-low PD9 level at a bounded one-tick cadence. Both modes are now
build-verified; the radio mode still requires hardware timing validation.

### 4.4 ST67W611M1 through SPI5

| Signal | Pin | Configuration |
|---|---|---|
| SPI_CLK | PE15 | SPI5_SCK |
| SPI_MISO | PG1 | SPI5_MISO |
| SPI_MOSI | PG2 | SPI5_MOSI |
| SPI_CS | PA3 | Active-high GPIO output; LOW while idle |
| CHIP_EN | PE10 | GPIO output |
| BOOT | PD5 | GPIO output |
| SPI_RDY | PE9 | Rising/falling EXTI |

The rising `SPI_RDY` interrupt posts `SPI_EVT_TXN_RDY`; host TX posts
`SPI_EVT_TXN_PENDING`. Both wake the dedicated `spi_xfer_engine` task. That
task owns CS and the SPI transaction, waits for the SPI DMA completion event,
then puts the received buffer into the typed RX queue. The modem parser task
dequeues and interprets the AT data; neither the EXTI nor DMA interrupt parses
or queues the received payload. The idle SPI worker now waits indefinitely for
one of those events: it does not read `SPI_RDY` every 20 ms. It still samples
the pin at initialization and during an active transaction to close handshake
races. A missed rising edge on an otherwise idle RX-only transaction can now
leave that transaction pending until another real event occurs; hardware HIL
must verify this edge-only policy.

The SPI worker queues a pointer to each complete SPI packet, not individual
DMA bytes. The DMA completion ISR only signals transfer completion because a
single NCP packet may need separate header and remainder transfers. The modem
task now takes ownership of each queued packet and retains its pointer plus an
offset until every byte has entered the AT assembly buffer; a short destination
read cannot silently discard the packet tail. The assembly buffer holds two
maximum-size SPI packets and retains incomplete AT records between reads. It
is fixed storage inside the modem object in application SRAM, not an allocation
from the 64 KiB radio byte pool; SRAM HIL showed that placing it in the radio
pool left too little headroom for subsequent NCP traffic.
If an invalid or oversized record fills it without a parse boundary, the
parser counts and reports an overflow before resynchronizing. Finite storage
cannot guarantee zero loss under unlimited input or a malformed length;
hardware HIL still needs to validate sustained BLE traffic and recovery.
An experimental master RX automatic-suspension (MASRX) setting passed two
live-register BLE probes but failed after a fresh RAM boot with SUSP/timeouts
and lost replies. That configuration experiment was reverted in both IOC and
the initializer; automatic suspension remains disabled. Generate Code is not
required for the C-only DMA recovery change alone.
The 2026-10-06 SPI5 RX-DMA candidate gives GPDMA1 channel 11 HIGH priority;
TX channel 10 remains LOW/HIGH_WEIGHT. RX/TX previously had the same priority.
A power cycle did not prevent baseline SPI overrun. A RAM-only RX-priority
comparison then received 300/300 BLE pings with ToF active and no SPI errors,
timeouts or recoveries. The matching IOC/MSP build booted normally and passed
100-frame CRC/NPU/preprocessing HIL plus BLE/Wi-Fi scan preflight. This supports
RX DMA arbitration as a cause of the observed overrun, without identifying the
specific competing bus transfer or accepting Cloud/MAP load or boot endurance.
The ordinary source build also passed 150/150 BLE idle replies (p95 141 ms,
max 172 ms). Wi-Fi association and paired Cloud CLI remained live after the
later ToF failure, with SPI error/timeout counters zero. Cloud stack sentinel
inspection observed 3504/8192 bytes used in this HTTP/CLI phase; ToF-send peak
usage and the Cloud frame/lease gate remain unmeasured.
`N6.ioc` is updated; CubeMX Generate Code is REQUIRED/PENDING for this DMA
configuration change. Review managed deviations afterward. Stack/pool sizes,
SPI clock/ports/bursts and master RX automatic suspension were not changed.
The SPI5 abort path also verifies both owned normal-mode DMA channels before
claiming recovery. It locally deinitializes/reinitializes a stranded channel
with the HAL's bounded disable wait and restores its SPI parent link. If SPI
abort fails after DMA cleanup, it resets SPI5 and restores the existing register
configuration without rerunning the generated MSP initializer on the 768-byte
worker stack. It does not reset the shared DMA controller or the NCP.
The 2026-10-04 RAM fault test exercised both recovery paths with zero
reinitialization failures. Stack fill showed 660/768 bytes used (108 untouched);
this narrow observed margin is not full-load stack acceptance. BLE still lost
replies after recovery; initial overrun and full-load validation remain open. No
memory-pool or stack capacity was increased.
The SRAM candidate passed USB radio/ToF preflight and three NCP Wi-Fi scans
(11, 13 and 11 networks) with 3,784 radio-pool bytes remaining and no failed
BLE state probes. BLE host HIL could not start: Windows WinRT returned E_FAIL
while creating the GATT device, before any ping was sent. This is not evidence
that the BLE parser fix passes or fails; see the saved HIL JSON report.

SPI5 remains generated by CubeMX, but when APP_ST67W6X_ENABLED is 0:

- The ST67 task is not created.
- The FreeRTOS compatibility layer is not initialized.
- W6X_Init and all radio hardware initialization are skipped.
- The unused PE9 interrupt source is disabled.

The CDC command `radio hardware` is available in both builds and reports the
SPI5/DMA state, CHIP_EN, BOOT, active-high CS, SPI_RDY, feature guards, and the
selected EXTI9 owner. It also reminds the operator that VDDIO, JP1/JP2, and
SB31/SB34 are physical checks that software cannot prove.

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
initialization sequence, fills the panel blue, and centers `SYSTEM IS LOADING`.
Once the ToF acquisition pipeline is ready, it signals the display task to
replace that screen with a green `SYSTEM ON` screen. This means sensor-pipeline
readiness, not Wi-Fi/Cloud readiness. `MAP ON DISPLAY` replaces the idle screen
with the depth map; `MAP OFF DISPLAY` restores `SYSTEM ON`. Before the first map
frame, `WAITING` is shown. The `tof status` display line reports the last
screen successfully submitted through SPI DMA; it cannot prove optical output.
Commands, clear chunks, and text pixels all use `HAL_SPI_Transmit_DMA`; the task
waits on ThreadX event flags posted by the SPI completion/error callback, so it
does not poll while DMA is active. Panel filling and the centered 14-pixel-high
text are streamed through one shared, cache-cleaned DMA row buffer instead of
reserving two large static buffers.

The task is intentionally the only display/SPI owner. Idle screens and map
frames are serialized by its event loop and use one owned frame slot; the tiny
private glyph subset is not intended to be a general graphics library.

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
| Upper NPU SRAM3 | `0x24244000..0x2426FFFF`, 176 KiB reserved for CPU-side CDC/RPS/ToF transient workspaces; all 180,224 bytes are currently linked |
| NPU SRAM4 | Current model does not use it; `0x24280000..0x242BFFFF` holds the application pool/Cloud CLI and `0x242D0000..0x242DFFFF` holds the radio pool |
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

The ThreadX application pool is 134 KiB in the current Wi-Fi/Cloud build. Its
active pool-backed stacks reserve 130 KiB, including the display and both UART
tasks, leaving about 4 KiB before allocator overhead. The Cloud worker's fixed
8 KiB stack is outside the application and radio pools. The USBX parent byte pool is
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

For debugger inspection, the mutable application state is grouped under
`tof_context` (acquisition/processing thread heartbeat, state, queues and
counters), `cli_context` (broker heartbeat, sessions, pending work and
counters), `app_usb_context` (USB lifecycle thread, event queue and counters),
and `usb_cdc_context` (separate RX/TX worker heartbeats, queues, state and
counters). The large ToF/CDC buffers and Cloud CLI session remain in dedicated
linker sections as `tof_workspace`, `usb_cdc_workspace` and
`cli_cloud_storage`; the corresponding root contexts point to them. These
are debugger-oriented groupings, not extra copies of the payload buffers.

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
| RPS on / off / status | Enable, disable, or inspect Neural-ART inference and raw int8 scores |
| debug off/error/warn/info/debug | Change ST67 log verbosity |
| debug route | Show USB/BLE/Cloud route generations, session-isolation diagnostic, and routed/stale Wi-Fi result counters |
| radio hardware / status / info | Inspect the ST67 hardware baseline, manager state, and module identity/versions |
| wifi scan | Submit a routed scan request and return its request ID immediately; the completed result lists up to 15 networks in the same live session |
| wifi connect `"SSID"` | Request the password without echo/history, submit a routed connect request, and return its request ID immediately; report the final association/IP result to the same live session |
| wifi status / wifi ip | Show station/link information plus IPv4, gateway, and netmask |
| wifi disconnect `[forget]` | Submit a routed disconnect/forget request and return its ID immediately; report the final status to the same live session |
| cloud status / endpoint | Inspect pairing, HTTPS, command/output and ToF relay counters |
| cloud pair `<code>` | Claim the six-digit code shown by the web app; available through USB or BLE |
| cloud enable / disable / reconnect / test | Control the HTTPS relay without changing Wi-Fi credentials |
| cloud unpair yes | Remove the persisted device capability token from the NCP filesystem |
| ble status | Show GATT readiness, connection, advertising, MTU, queues, counters, and SRAM4 pool |
| ble adv on / ble adv off | Start or stop BLE advertising through the Radio Manager |
| ble disconnect | Disconnect the current BLE peer |
| clear | Clear the terminal |
| Start UART Firmware Update / update | Enter signed raw XMODEM-CRC receive mode on either USB CDC or BLE CLI |
| reboot yes | Reset the MCU |

`help`, `menu`, and `?` now emit the complete list in bounded sections instead
of one oversized print that could be truncated before the radio commands. The
same command handlers are intentionally available on USB CDC, BLE and Cloud.
The help text also describes BLE Write/Notify, typed Cloud text/binary records,
the dedicated ToF media channels, the TX-only DEBUG service and advertising.
Physical SRAM HIL on 2026-09-19 received the complete 1,840-byte explicit help
response over USB CDC and then repeated `help` through BLE CLI Write/Notify at
MTU 247. BLE transmitted the initial menu plus the explicit help as 16 bounded
messages/4,044 bytes with zero drops, retries, stale generations, or errors.

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
over either the CN8 USB CDC console or the BLE CLI RX/TX characteristics, not the
independent ST-LINK diagnostic UART. After entering `Start UART Firmware Update`
(or `update`), the selected CLI session stops line parsing and terminal echo and
passes raw transport byte arrays into an allocation-free XMODEM-CRC receiver.
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

Both CDC and BLE use the same byte-array `Begin` / `Write` / `Finalize` boundary.
The radio transport therefore cannot bypass the Secure service or write external
flash directly; package signature, version, inactive-slot and rollback rules are
identical on both links.

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

- wifi_ble_app.c/.h — project-owned Radio Manager task and safe hardware
  routing.
- spi_port.c and board-specific transport configuration.
- A small FreeRTOS-to-ThreadX compatibility layer required by the vendor driver.
- Wi-Fi, IP, BLE connection, and error callbacks.
- A non-destructive `radio hardware` diagnostic plus Radio-Manager-owned
  scan/connect/disconnect requests and BLE advertising control.

The Radio Manager now owns one `WifiBle_RadioManagerContext_t`: its `shadow`
records observed NCP/Wi-Fi/BLE state (including link, advertising, MTU and
notification subscriptions) and the requested advertising policy; `work`
holds pending commands/events; `counters` holds loop/RX and manager-failure
diagnostics; and `queues` references the existing bounded BLE, ToF-image and
Wi-Fi queue contexts in SRAM4. `ble status` shows desired advertising,
last acknowledged/inferred state, evidence quality and manager failure counts.
An `OK` from `AT+BLEADVSTART/STOP` is command acceptance, not proof of RF.
An error or timeout marks ADV evidence `UNKNOWN`; the Radio Manager retries
at most three times with bounded backoff, then reports exhaustion. Every 15 s
when BLE/Wi-Fi traffic permits, it alternates `BLEINIT?` and `BLECONN?`;
mode/link discrepancies require two consecutive observations before the
local state is corrected. A confirmed lost BLE mode triggers at most
three BLE-only reinitialization/GATT-registration attempts, without resetting
the shared NCP or Wi-Fi/Cloud. The ST67 AT contract has no ADV-state query,
so the only RF-level proof remains an external BLE scan/HIL; the manager never
labels a command ACK as RF verification. Whole-module reset after persistent
faults is deliberately deferred because it would invalidate Wi-Fi/Cloud state.
The Wi-Fi control worker independently refreshes station state every 30 s
when idle, marks its shadow `UNKNOWN` on query failure, and discards a query
result superseded by a newer Wi-Fi event. This does not add stored credentials
or an automatic reconnect policy.

The module and BLE discovery layer are enabled independently from Wi-Fi in
AppliNonSecure/Core/Inc/app_features.h:

~~~c
#define APP_ST67W6X_ENABLED  (1U)
#define APP_ST67W6X_BLE_GATT_ENABLED  (1U)
#define APP_ST67W6X_WIFI_SERVICES_ENABLED (1U)
#define APP_ST67W6X_CLOUD_RELAY_ENABLED (1U)
~~~

BLE advertises as `N6-MAINT-xxxx` with separate CLI and DEBUG services. CLI and
DEBUG each retain their UART-like RX/TX characteristics. The CLI service also
contains a dedicated Notify-only ToF image characteristic:

| Endpoint | UUID | Properties |
|---|---|---|
| CLI RX | `7a1e0002-b5a3-f393-e0a9-e50e24dcca9e` | Write, Write Without Response |
| CLI TX | `7a1e0003-b5a3-f393-e0a9-e50e24dcca9e` | Notify |
| ToF image TX | `7a1e0004-b5a3-f393-e0a9-e50e24dcca9e` | Notify |
| DEBUG RX | `7a1e0102-b5a3-f393-e0a9-e50e24dcca9e` | Write, Write Without Response; rejected by policy |
| DEBUG TX | `7a1e0103-b5a3-f393-e0a9-e50e24dcca9e` | Notify |

CLI RX is copied into an 8x512-byte bounded queue; CLI TX uses 8x768-byte
slots. DEBUG TX is an independent best-effort 8x256-byte queue. Every slot
carries the connection generation, and the Radio Manager fragments TX to
`MTU-3`, caps retries, and drops stale work after reconnect. BLE has an
independent 5,176-byte parser/editor/history/output session allocated from SRAM4
only after the vendor radio initialization reaches READY. The single priority-9
CLI broker services CDC, BLE and Cloud without sharing partial-line or history state;
command backends remain serialized. Signed XMODEM enters raw mode only for the
session that requested it and feeds the same authenticated Secure A/B installer
as CDC. DEBUG RX remains blocked; every actual CLI command is shared by design.
Each CLI session now also owns a transport-independent route containing its
fixed USB, BLE or Cloud transport and a non-zero generation. USB advances the
generation when its parser session resets at detach; BLE follows the radio
runtime's existing connect/disconnect generation without a second reset; Cloud
follows the relay's logical capability epoch (successful pair, explicit
reconnect/test, or unpair), not each short-lived HTTP socket or backoff retry.
A saved route is current only while both its transport and generation still
match, so later asynchronous work can reject replies from an older session.
`debug route` reports those generations and a startup diagnostic that exercises
generation advance, stale-route detection, two-session SSID isolation, and
session-scoped cancel/reset cleanup.

Pending Wi-Fi SSID, hidden password buffer, and password-prompt state are owned
by the requesting CLI session. Submission, Ctrl-C, prompt failure, transport
reset/disconnect, and input overflow scrub the complete fixed SSID/password
arrays. The SSID-bearing `wifi connect` command is not retained in command
history. One USB, BLE or Cloud prompt therefore cannot overwrite or clear
another session's credentials. Scan, connect, and disconnect submission are
asynchronous. `wifi disconnect [forget]` returns a request ID immediately;
M3.9 now routes the final outcome only to the matching live session. The public Wi-Fi interface now defines fully owned, routed
request and result value types for the next architecture stage: requests carry
fixed SSID/password buffers, while results carry independent status and bounded
scan snapshots. Wi-Fi initialization now owns exactly four slots of each type
and four fixed `TX_1_ULONG` pointer queues for their free/ready lifecycles. A
startup self-test exhausts both pools, requires immediate `TX_QUEUE_FULL` on
the fifth acquire, traverses the ready queues, verifies complete release
scrubbing, and restores `free=4, ready=0`; initialization rolls back every
created object and its SRAM4 allocation on failure. The 5,648-byte context is
within its 6 KiB budget and is 4,576 bytes larger than the previous context,
projecting 16,480 bytes free from the last 21,056-byte physical radio-pool
baseline. This is a computed margin pending later runtime observation.
Two public non-blocking APIs expose the staged path: submit validates and copies
a routed request into an owned slot while assigning a non-zero monotonic ID,
and receive copies then releases one complete result snapshot. Both return
immediately on empty/full queues. `WIFI_BLE_App_WifiControlRun()` now waits for
radio readiness, drains owned requests, performs every runtime high-level
scan/connect/disconnect operation, and publishes routed status/scan snapshots,
including bounded scan timeout and failure results. Connect credentials are
removed from the queued request before the blocking vendor call and from the
stack-local vendor options immediately afterward. `WIFI_BLE_App_Run()` only
signals radio readiness and maintains radio/BLE events; it no longer executes
high-level Wi-Fi requests. A dedicated priority-11 ThreadX worker now runs this
loop on a 6 KiB stack allocated from the SRAM4 radio pool. Live SWD inspection
during a failed connect proved that `W6X_WiFi_Connect` ran on this worker rather
than the priority-9 Radio Manager; the worker retained 3,936 stack bytes after
that path. `wifi scan` and the hidden-password `wifi connect` path now create
zeroed stack requests, copy the active session route, submit them, print the
request ID, and return to the prompt without waiting. The connect path scrubs
its complete stack request immediately after submission, and the caller then
scrubs the complete session-owned SSID/password storage on both acceptance and
rejection. The CLI now polls at most two completed results per cycle, prints
final association/DHCP status and bounded scan lists only to the matching
transport/generation, and counts stale results without leaking them to new
sessions. It defers result text during XMODEM and hidden password input. The old blocking application APIs remain a
transitional adapter with no CLI caller; M3.10 removes the adapter.
The DEBUG mirror is not attached yet. Wi-Fi initializes the station service,
enables station DHCP, and the dedicated Wi-Fi control worker owns high-level
scan/connect/disconnect calls. `wifi connect "SSID"` accepts the password in a
second hidden prompt so it is neither echoed nor stored in CLI history, submits
the owned request, and returns its request ID immediately. Association/DHCP
completion is now reported by M3.9 only to the initiating live session. The demo
intentionally permits credentials, disconnect, reboot, pairing and signed
update through BLE as well as USB and Cloud.

The current Cloud demonstration transport connects directly to
`natilab-n6-h6bjh2ffbadtfyaw.israelcentral-01.azurewebsites.net` over
plaintext HTTP/1.1 on TCP port 80. It does not install a CA, send TLS options,
or run the former TLS-only SNTP prerequisite. This avoids the T01/Azure TLS
interoperability issue but provides **no confidentiality or server identity**.
The preserved TLS code path uses TLS 1.2, SNTP, SNI and DigiCert Global Root G2
when `APP_ST67W6X_CLOUD_USE_TLS=1`; it has not passed the Azure endpoint test.
`cloud pair <code>` exchanges
the browser's six-digit code for a device capability token, stores a
CRC-protected record in `n6cloud.cfg` on the NCP filesystem and reconnects
automatically after reboot. Commands are leased and explicitly acknowledged;
typed text and CRC32-protected binary records keep XMODEM OTA on the same CLI.
Cloud ToF frames are posted separately with the BLE-compatible 20-byte header,
so a live terminal and map can run concurrently.

The ToF characteristic transports one logical frame across as many ATT
notifications as required. Each notification begins with the same 20-byte
little-endian header:

| Offset | Field | Meaning |
|---:|---|---|
| 0 | `u16 magic` | `0x364E` (`N6` in byte order) |
| 2 | `u8 version` | Protocol version 1 |
| 3 | `u8 flags` | bit 0 START, bit 1 END |
| 4 | `u32 frame_id` | Sensor frame identity |
| 8 | `u16 offset` | Byte offset in the image payload |
| 10 | `u16 total` | Complete payload length |
| 12, 13 | `u8 width`, `u8 height` | Image dimensions |
| 14 | `u8 channel` | 1 depth, 2 amplitude, 3 ambient, 4 reflectance, 5 confidence |
| 15 | `u8 pixel_format` | 1 = float32 little-endian |
| 16 | `u32 crc32` | CRC32 of the complete image payload |

The current maximum payload is `54 * 42 * 4 = 9,072` bytes. At the negotiated
MTU 247, 224 image bytes follow the header, so a full frame requires about 41
notifications. The web receiver publishes a frame only after ordered contiguous
reassembly and CRC validation. A missing, stale, reordered, or corrupted
fragment discards the complete partial frame; it can never display a mixture of
two sensor frames.

Firmware owns only one SRAM4 ToF snapshot. A new transformed frame is copied
only when that slot is free; while it is queued or transmitting, subsequent
frames are deliberately dropped rather than accumulated. CLI, DEBUG and image
each receive at most one fragment per Radio Manager cycle, so a slow image
subscriber cannot starve XMODEM. The image producer waits for an ATT payload
larger than its 20-byte header; with MTU 247 the expected ceiling is about one
complete frame per second.

The 134 KiB application ThreadX pool and Cloud CLI session are NOLOAD data in
the reserved SRAM4 window at `0x24280000..0x242BFFFF`. This recovers contiguous
SRAM2 heap without changing task capacity. The radio build uses a dedicated 64 KiB ThreadX byte pool at
`0x242D0000..0x242DFFFF` in currently unused SRAM4. Its general SRAM2 pool is
134 KiB when Wi-Fi services are enabled (151 KiB for a BLE/radio-only build,
159 KiB with the radio disabled). The fixed startup stacks consume about
130 KiB, leaving about 4 KiB before application-pool allocator overhead. The
Cloud worker uses a separate static 8 KiB stack in the same lower-SRAM4 reservation.
The BLE stream
contexts, Wi-Fi request/result context, independent CLI session, vendor Wi-Fi
objects, and single 9,072-byte ToF image snapshot are allocated from the radio pool. The
linker and build preflight enforce the pool bounds; runtime `ble status` exposes
remaining radio-pool bytes and image accepted/completed/dropped/error counters.
The current M3.8 incremental build preserves 449,792 bytes of C heap, above the
enforced 360 KiB transform floor. M3.5 RAM HIL reached full radio/Cloud/BLE CLI
initialization plus a failed connect with 3,188 radio-pool bytes available.
The first Wi-Fi scan performs the vendor driver's existing lazy allocation of
20 scan entries (920 bytes plus an 8-byte ThreadX block header), leaving 2,260
bytes in 30 fragments; a second scan leaves the same value. M3.6 and the
stack-only M3.7 connect submission add no SRAM4 storage. A fresh M3.7 failed
connect held the pre-scan pool at 3,188 available bytes before and after the
operation, but the reserve remains narrow, so later BLE/Cloud and soak gates must
continue to inspect it. Stage 08 continues to reject generated NPU networks
that select SRAM4.

M3.7 BLE latency is not yet accepted. Targeted review-fixes now give malformed
direct records, partial `+BLE:GATTWRITE` numeric fields, and failed raw SPI
writes bounded forward progress. Two post-fix fresh-RAM 45-second probes passed
222/222 with p95 148.352 and 152.370 ms; the latter also passed 24/24 concurrent
USB PONGs at p95 30.6 ms and held the radio/BLE maximum loop gap to 390 ticks.
An intervening clean run connected but failed to publish the initial BLE prompt
and logged repeated SPI transaction-ready timeouts before any Wi-Fi request was
submitted. The Cortex, ToF processing, and radio loop remained alive. The
targeted SPI handshake recovery is now bounded, but the clean-boot probe must
be made repeatable before M3.7 or the Milestone 3 gate is closed.

The user explicitly authorized M3.8 while that M3.7 gate remains open. `wifi
disconnect [forget]` now submits a zeroed, route-tagged request and returns its
ID immediately; at that checkpoint the final status was deferred to M3.9. One RAM HIL boot accepted
USB IDs 1/2 and BLE IDs 3/4, answered immediate BLE pings after both disconnect
variants, and answered 24/24 concurrent USB pings with zero BLE stream drops.
This verifies the M3.8 CLI path only. The intermittent M3.7 BLE first-reply/SPI
fault, its 5/5 boot requirement, and the Milestone 3 gate remain open. Because
M3.9 did not yet drain results at that checkpoint, four submissions required
a RAM reload. The subsequent M3.9 implementation now releases each received
result slot: six sequential USB requests yielded six matching results, and a
concurrent USB/BLE test kept request IDs 7 and 8 on their originating sessions.
BLE reconnect and USB-close tests counted three stale results without showing
them in successor sessions. A scan completed during XMODEM but its text appeared
only after two CAN bytes cancelled the receiver. The M3.7 five-boot BLE gate
and the Milestone 3 gate remain open; Cloud asynchronous output has not been
exercised on hardware. The M3.9 follow-up now keeps a Cloud Wi-Fi request bound
to its leased Relay command until the matching result is queued. It uses one
nonblocking, bounded Cloud output record with the operation, request ID, final
status, scan count and IPv4; USB/BLE retain the full scan list.
The Relay ACK also arms a command hold: the server releases its lease on ACK,
so the firmware must not poll another command until the pending result and
completion marker have been accepted. The CLI defers
result text only for the session in hidden-password or XMODEM mode. Four fixed
CLI-owned deferred snapshots release the worker's result slots promptly;
`debug route` reports any deferral overflow. RAM HIL confirmed six sequential
USB results across the four-slot pool, USB/BLE route isolation, and delivery to
one transport while the other was at a hidden password prompt. The three old
caller-facing blocking Wi-Fi APIs and their transitional state were removed in
M3.10; the worker still uses its bounded internal scan-completion event. Cloud
hardware verification remains deferred because the tested board reported
`waiting for Wi-Fi, not paired`. M3.7's five-boot BLE gate and the Milestone 3
gate remain open; no external NOR write was made.

M4.1 now bounds the generic modem command TX-lock wait by the caller's timeout
and subtracts elapsed lock/write time from the modem-response wait. Its
incremental build and RAM load passed. Two concurrent 45-second BLE/Wi-Fi
probes failed, however: 18/19 and 15/16 replies, with p95 263.543 and
262.771 ms; concurrent USB pings passed 24/24 in each run. These results do
not close M4.1 HIL acceptance, M3.7's five-boot gate, or the Milestone 3 gate.
The manual-lock work of M4.2 had not started at that checkpoint.

M4.2 now bounds both manual common-command TX-lock acquisitions using the
caller's timeout and returns `W61_STATUS_TIMEOUT` if the lock is unavailable.
Query/Parse also subtracts lock-wait time from its reply budget. One complete
45-second RAM BLE probe during a failed Wi-Fi connection passed 221/221 replies
with zero missing, p95 169.995 ms and no reconnects; USB passed 24/24 parallel
pings. This does not retroactively pass M4.1's two failed probes or the M3.7
five-boot gate. The same RAM boot reported a separate ToF sensor-init error
(-5), so the probe is not a full-system load/soak result.

M4.3 now bounds all three manual BLE AT TX-lock acquisitions to the 2000 ms
NCP budget and counts lock time in the notification caller's 100 ms budget.
One full 45-second RAM BLE probe during failed Wi-Fi association passed
223/223 replies (zero missing, p95 152.095 ms, zero reconnects), alongside
24/24 USB pings. BLE TX had zero drops but one retry/error; the radio loop
maximum gap was 50 ticks. A separate ToF fault (-5/-1) remained on that boot.
This focused probe does not close M4.1's prior failed probes, M3.7's five-boot
gate, or full-system soak. M4.4 has not started; external NOR was unchanged.

M4.4–M4.5 now bound all remaining manual Wi-Fi, Network and System AT TX-lock
waits; the driver-wide search finds no `sem_tx_lock` wait using
`portMAX_DELAY`. M4.6 retains BLE CLI/DEBUG packets and ToF image frames when
notification returns BUSY or TIMEOUT, retrying on the next Radio Manager
cycle. `ble status` exposes separate transient counts, streaks, durations and
recoveries. The final incremental build passed. A RAM contention probe failed
early with 14/15 BLE replies (one missing) despite zero BLE TX drops and two
recorded transient timeouts; a repeat on the same boot completed 45 seconds
with 222/222 replies and zero missing. USB pings passed 24/24 in both runs.
An earlier boot failed radio initialization, and a later ToF error was also
observed. These mixed results do not close the Milestone 4 or M3.7 gates;
Cloud contention and ToF image notification recovery still need hardware
validation. No external NOR write was made.
After a final budget-accounting refinement, the rebuilt RAM image completed
another 45-second Wi-Fi/BLE probe with 222/222 replies, zero missing,
p95 149.209 ms, three recovered/cleared transient timeout attempts and zero
BLE TX drops; USB again passed 24/24. The earlier missing reply remains an
open repeatability failure, so this pass does not close Milestone 4.
The repeated-boot gate can now be run without manual resets through
`hil_tests/run_milestone4_gate.py` (see `hil_tests/README.md`). A 2026-09-24
RAM run on the updated BLE startup banner and guarded W61 RX allocation failed
the full gate: BLE/USB were 148/162 and 24/24 on boot 1, then 222/222 and
24/24 on boot 2; ToF entered `DSS unmap command (-1)` on both. Boot 3 could not
start because the ST-LINK GDB server exited before connection. The raw and
aggregate reports are in `hil_tests/results/milestone4_gate_rx_guard*.json`.
The parser now continues measuring after one missing PONG, so this result
confirms intermittent loss with later BLE recovery. M3.7 and Milestone 4
repeatability gates remain open.

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
  signs `N6-Firmware-v<n>.n6fw` with the shared educational update key, and
  records the version plus SHA-256 of every factory image in
  `FlashImages/factory-manifest.json`.
- `Tools/New-FirmwareSigningKey.ps1` creates a development P-256 key once. The
  designated private blob and generated public-key header are both tracked for
  this reproducible educational project; neither is suitable for production.
- `Tools/New-FirmwareUpdatePackage.ps1` can package an already-built trusted
  Non-Secure image with an explicit increasing firmware version.
- `Tools/program_flash.ps1` programs and verifies FSBL, Secure, factory Slot A,
  and both default metadata copies in external NOR.
- `training/13_FACTORY_PROVISION.bat` wraps a complete build/sign plus
  `program_flash.ps1 -FullErase`, requires `ERASE ALL`, and verifies the
  running version through CN8. Use it for a blank board or an intentional
  factory reset, never as the ordinary release lane. `-BuildOnly` validates
  every generated factory artifact without touching hardware. `-SkipBuild`
  is accepted only when the manifest version still equals the source version
  and every recorded image hash matches, so stale artifacts are rejected
  before the erase begins.
- `radio_firmware/01_UPDATE_MODULE.bat` programs the bundled ST67 mission-T01
  SDK 2.0.106 NCP image through the ST-LINK VCP. It verifies all inputs by
  SHA-256, retries QConn once, and restores the project or ST reference FSBL in
  a `finally` path.

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
| AppliNonSecure/USBX/App/app_usbx_device.c | Consolidate generated CDC class parameters and thread control block into `app_usb_context` | One debugger-visible USB lifecycle context | Medium: Generate Code may restore separate generated globals |
| AppliNonSecure/.cproject | Set Debug C/C++ optimization to `-O3` | Make the 54×42 transform fast enough for the 10 fps pipeline while keeping debug symbols | High: CubeMX/IDE configuration changes can restore `-O0` |
| AppliNonSecure/.project | Link HAL UART and UART-extended sources | The custom ST-LINK VCP logger uses HAL UART although USART1 is not a generated Non-Secure peripheral | High |

Most functional Secure changes, RIF releases, cached-vector logic, USBX task changes, stack overrides, and additional ThreadX tasks are inside USER CODE blocks.

### 6.2 Imported/demo files intentionally changed outside USER CODE

The vendored ST67 driver is intentionally patched in
`ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.c`. Its transfer
worker yields for one ThreadX tick after every eight continuously serviceable
packets. This bounds CPU monopolization if `SPI_RDY` is stuck HIGH without
discarding pending work. Re-importing the X-CUBE driver can overwrite this
hardening and must be followed by a diff review and HIL rebuild.

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
| System Timer Thread | 0 | 1 KiB | ThreadX static storage | Executes ThreadX timer callbacks; the ISR-processing define is commented out |
| Debug UART TX | 5 | 3 KiB | TX application pool | Drains the diagnostic queue through UART interrupts; producers submit without waiting |
| Debug UART test | 9 | 3 KiB | TX application pool | Periodic heartbeat and diagnostic test commands |
| Firmware confirmation | 6 | 2 KiB | TX application pool | Sleeps five seconds, commits a TRIAL image, then exits; priority prevents ToF starvation |
| ToF Acquisition | 7 | 16 KiB | TX application pool | Sensor ownership, PD9 event wait, fully asynchronous I3C DMA sequence, raw-slot publication |
| ToF Main Thread | 10 | 96 KiB | TX application pool | Raw-frame transform, RPS preprocessing/Neural-ART inference, metadata parsing, ANSI rendering, and raw-slot release |
| USBX Device App Main Thread | 8 | 16 KiB | USBX pool | USB lifecycle manager: PCD/USBX, CDC callbacks, worker start/stop, error events |
| USB CDC RX worker | 9 | 12 KiB | Static BSS | Dispatches callback-filled static RX slots into the application delivery queue |
| USB CDC TX worker | 9 | 12 KiB | Static BSS | Submits one static TX slot and waits for the USBX completion callback before advancing |
| GC9A01 display | 8 | 4 KiB | TX application pool | Owns display SPI DMA and consumes the latest published frame |
| ST67 Radio Manager | 9 | 8 KiB | Dedicated SRAM4 radio pool | W6X initialization, BLE GATT/advertising, connection events, and recovery; active |
| ST67 Wi-Fi control | 11 | 6 KiB | Dedicated SRAM4 radio pool | Waits for radio-ready, owns high-level Wi-Fi scan/connect/disconnect, and publishes routed results |
| ST67 Cloud Relay | 9 | 8 KiB | Static lower-SRAM4 BSS | Owns runtime HTTP/socket/pairing operations; fixed control queue and shared ToF-buffer lease; RAM HIL pending |
| USB debug CLI | 9 | 6 KiB | TX application pool | CDC input, line editing, and commands; runs above the continuously ready ToF processor |

USBX also creates separate CDC Bulk-IN and Bulk-OUT callback threads, each at
priority 8 with an 8 KiB stack in its system arena. The ST67 middleware creates
its modem-processing and SPI-transfer tasks through the FreeRTOS compatibility
layer. The `TX_TIMER_PROCESS_IN_ISR` define appears only inside a comment in
this build. A RAM GDB snapshot on 2026-10-03 confirmed 19 created threads,
including the priority-0, 1 KiB System Timer Thread and the completed firmware
confirmation task; 18 had not completed at that checkpoint.

### 8.1 Byte pools

| Pool | Size | Main use |
|---|---:|---|
| tx_app_byte_pool | 134 KiB with Wi-Fi enabled; linked in SRAM4 | ToF, CLI, and application stacks/objects |
| ux_device_app_byte_pool | 56 KiB | 32 KiB USBX system arena, 16 KiB USB Device task stack, bookkeeping, and headroom |
| usbpd_app_byte_pool | 16 KiB | CAD queue, CAD task, and USB-PD objects |
| tx_radio_byte_pool | 64 KiB | Radio/Wi-Fi stacks, ST SPI/AT objects, BLE/Cloud contexts and receive packets |

The CDC data plane does not have a byte pool. Its memory is fixed in BSS:

| Static storage | Count × size | Purpose |
|---|---:|---|
| ToF raw slots | 3 × 14,842 bytes | DMA destinations exchanged between acquisition and processing |
| CDC control TX slots | 8 × 768 bytes | CLI text and short diagnostic messages |
| CDC map TX slots | 2 × 48 KiB | Complete ANSI frames rendered in place |
| CDC RX slots | 16 × 512 bytes | Completed USB bulk-OUT payloads |

Separate pools help diagnose failures. A PSP address can be matched to a pool to identify which task was actually running.

The upper 176 KiB of NPU SRAM3 (`0x24244000..0x2426FFFF`) holds the CDC worker
stacks/slots, RPS preprocessing scratch, and the transient ToF depth frame. The
current `.npu_shared_bss` uses all 180,224 bytes of that reservation. Moving
these deterministic large objects out of SRAM2 leaves 420,368 bytes between the
2026-10-04 M5/SPI-recovery build's `_end` symbol and the reserved MSP stack, above the 360 KiB VL53L9
guard. The generated network uses 17,408
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

Before building or opening ST-LINK, the helper checks that the GDB TCP port
and its two adjacent server ports can be bound. If the default range
`61234..61236` is occupied or reserved by Windows, it automatically selects
an available range starting at `61300` and prints the chosen port. An explicit
`-GdbPort` is honored or rejected with a clear error. Readiness checks require
the listener to belong to the newly launched server; they never connect a
test TCP client, which would consume ST-LINK's debugger session. Startup
failures include stdout/stderr and the paths under `Tools/.n6-debug`, so a
host port conflict is distinguishable from a target/SWD connection failure.
Run `Tools/Test-RamDebugStartup.ps1` for hardware-free startup regression checks.

On 2026-10-03 the corrected host startup passed RAM loading and Stage 11:
100 CRC-valid frames, 100 frame-matched NPU results, bit-exact host/device
tensors, 100% class/decision agreement, maximum raw-score delta 1, and live
BLE advertisement/Wi-Fi scan checks. The observed output rate was 4.10 fps.
A preceding RAM boot reported zeroed NCP component versions; another boot
reported the expected SDK 2.0.106. That intermittent failure remains open.
The FSBL also authenticated the existing confirmed Flash slot A/version 5;
this session did not reprogram NOR or validate a fresh external-Flash boot.

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

After RAM HIL, set BOOT0 and BOOT1 to `1-2` **without pressing Reset**.
Keep CN8 connected and the validated RAM application running until the
XMODEM updater completes and resets the device itself. Resetting beforehand
discards that RAM application and may remove its CDC endpoint. Port discovery
filters historical CIM/USB-registry identities against currently present COM
ports, waits up to 30 seconds for enumeration, and repeats auto discovery
immediately before transfer and after reset. Explicit `-Port` remains fixed.
`Tools/Test-UsbCdcDiscovery.ps1` checks disconnected identities, the registry
fallback, and bounded enumeration waiting without opening serial endpoints.

Run `training\09_BOOTSTRAP_NPU_SWD.bat` first, and again after changing FSBL or
Secure: it programs only signed FSBL + Secure and preserves both application
slots/metadata. The XMODEM installer requires their current raw-image hashes
to match the recorded SWD installation. A historical Stage 09 PASS is insufficient:
Secure gateway addresses move when Secure is rebuilt, while Non-Secure links
against those addresses. RAM HIL replaces Secure in SRAM and can pass even when
the installed Secure is incompatible. Such a Flash trial can fault in the first
`SystemCoreClockUpdate` call and roll back before CDC enumerates.
`Tools/Test-BootChainCompatibility.ps1` checks this release gate without hardware.
On 2026-10-03, this recovery completed 100-frame HIL, installed v7 through
authenticated XMODEM, and verified a second Flash boot with confirmed slot B/v7
(metadata sequence 15), CDC version 7, streaming ToF, and a ready Neural-ART
runtime with zero inference/I3C errors. The board was left in Flash boot with
BOOT0/BOOT1 at `1-2`.
The guided release
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
The guided and verified factory-new equivalent is:

~~~text
training\13_FACTORY_PROVISION.bat
~~~

It requires the exact phrase `ERASE ALL`, builds/signs before erasing, writes
FSBL, Secure, Slot A, and both metadata copies with programmer verification,
then asks for external-Flash boot jumpers and verifies the running firmware
version over CN8. CN8 discovery falls back to the Windows USB-enumeration
registry when WMI/CIM access is restricted. A new board whose ST67 NCP must also be provisioned should
first run `radio_firmware\01_UPDATE_MODULE.bat`; see its Hebrew README for the
temporary-host/FSBL restore sequence.

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

The Non-Secure image also accepts single-key, read-only diagnostics on this
same ST-LINK UART. No Enter is required (CR/LF is ignored): `?` prints the
keys; `a` prints one snapshot of Radio, ToF, CLI and USB; lowercase `r`, `t`,
`c`, `u` prints only the selected mechanism; uppercase `R`, `T`, `C`, `U`
selects one mechanism for a snapshot every five seconds; `0` stops periodic
snapshots. Ordinary boot/fault logs continue while a watch is active. Status
output is produced in the UART diagnostic thread, not the receive interrupt,
and contains only state, progress and counters (not Wi-Fi credentials or CLI
payloads). The Radio snapshot distinguishes desired ADV from command-ACK
evidence; it does not claim RF advertising was observed. `age` values for
ToF/CLI/Radio are milliseconds; the USB manager event age is in ThreadX ticks
(100 ticks/second). A USB state snapshot reports `state_snapshot_busy=1` if
its mutex is occupied instead of blocking the diagnostic thread. This facility
was exercised from RAM on 2026-09-24 after reconnecting ST-LINK: `a` printed
all four snapshots, `R` printed Radio immediately and again after five
seconds, and `0` stopped only the periodic snapshots. No external NOR was
written. The same RAM session still failed BLE HIL: 117/137 replies during a
failed Wi-Fi connection and 71/77 replies in a separate idle probe; USB
passed 24/24 concurrent pings. These failures do not close the M3.7/M4 gates.

Press `n` on the ST-LINK UART to toggle an optional NCP trace; press `n`
again to turn it off. `?` lists this key. `[NCP]` lines show each SPI/AT
transport chunk in order, with a sequence number, direction, byte count and
transport result. They decode AT command names, `OK`/`ERROR`, BLE event names
and the raw-data prompt into readable English. Arguments and arbitrary data
are deliberately hidden because they can carry Wi-Fi passwords, cloud tokens
or firmware bytes. For one-character hexadecimal `debug ping` probes only,
`[NCP-CLI]` shows the token at five safe checkpoints: NCP direct-event
parser, BLE RX queue, CLI dequeue, CLI parser, and reply queue. `TX queued`
means the SPI transport
accepted the write, not that the NCP or remote BLE client received it.
The trace uses the existing bounded asynchronous UART queue; high output
volume can affect timing or drop diagnostic lines, so compare `debug uart`
drop counters and repeat suspect results with trace disabled. In a RAM test,
`n` toggled correctly and an idle BLE probe produced 23/28 replies; the 23
recognized ping inputs appeared at all four CLI checkpoints. This does not
locate the five absent inputs and does not prove an NCP or CLI-parser fault.
After adding the NCP direct-event checkpoint, a final five-second RAM smoke
probe received 12/15 replies. Exactly 12 ping tokens appeared at the direct
event, BLE queue, CLI dequeue, parser and reply-queue checkpoints; UART
diagnostics reported zero dropped trace messages. This run therefore does
not support a failure in the CLI command parser: the three missing pings were
not observed as complete direct events. It still cannot distinguish a host
write that never reached the NCP from an NCP event omission or an earlier
vendor direct-event parsing failure. A separate RAM boot briefly logged a ToF
`DSS unmap` error; the subsequent run continued acquiring ToF frames.

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

## 12. Change history

The dated engineering history lives in [CHANGELOG.md](CHANGELOG.md). It is
intentionally separate from the operational README and should be opened only
when historical context is explicitly required.

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
6. Extend the passing ten-cycle BLE reconnect/ToF CCCD soak to a multi-hour
   endurance run while ToF/display/CDC continue operating, and record SRAM4
   high-water behavior over that longer window.
7. Complete the remaining BLE stream fault HIL: concurrent CDC/BLE commands,
   intentional missing-fragment rejection, and sustained image-rate
   measurement. CRC-valid complete frames and CCCD stop/start already pass.
8. Repeat CN8 XMODEM installation across both A/B directions and validate
   interruption during transfer, invalid signature/version rejection, and
   reset-before-confirm rollback on hardware. One signed installation and
   confirmed trial boot have passed.
9. Transfer a signed `.n6fw` over BLE in both A/B directions and repeat the same
   interruption, invalid signature/version and rollback fault cases required for
   CDC. BLE must continue to use the Secure byte-array interface and must never
   own flash or boot metadata.
10. Replace `-nk` and the workstation development key with a protected,
    provisioned production signing/root-of-trust and anti-rollback chain before
    treating physical update security as production-ready.
11. Follow the numbered release sequence: Stage 09 installs the matching Secure
    boot chain (repeat after FSBL/Secure changes), Stage 10 loads the exact integrated model into SRAM, Stage 11
    runs HIL against that live SRAM image, and Stage 12 installs the persistent
    update only after the HIL fingerprint passes.
### Post-GOTIP Secure fault diagnosis (2026-09-25)

A browser BLE Wi-Fi connection reproduced a Secure HardFault after Wi-Fi
connection. The valid fault address `0x00000EBC` and the actual Non-Secure
PSP frame mapped PC `0x2413FE8E` to `W61_AT_Common_SetExecute` at
`w61_at_common.c:492`, called by SNTP. Both vendor Net context pointers were
NULL: Cloud Relay used the Net API after GOTIP without `W6X_Net_Init()`.
Radio startup now initializes Net before enabling Cloud processing; failed
Net initialization disables Cloud without taking Wi-Fi/BLE down. Unpaired
Cloud also skips its unnecessary post-GOTIP SNTP command. The Secure
fault trace also checks both Non-Secure stack candidates. Both images build
and run from SRAM, but 20 successful Wi-Fi/BLE cycles and negative-path HIL
are still required before this issue can be closed. The separate ToF DSS
error is not assigned as the cause of this fault.

### Cloud output admission (M5.1, 2026-09-25)

With the user's explicit sequencing exception, Cloud output now uses eight
fixed 384-byte slots in application SRAM. Each API call admits its complete
record immediately or returns `TX_QUEUE_FULL`; neither output nor completion
waits for queue space or sleeps. A one-time startup self-test checks a forced
full queue, rejection without partial publication, and successful multi-slot
admission. The Non-Secure build and SRAM boot passed, with 4,472 bytes free
in the radio pool. This does not close the Milestone 3/4 gates, prove paired
Cloud delivery, or complete the dedicated Cloud task planned for M5.2–M5.4.

### Cloud worker ownership handoff (M5.2–M5.4, 2026-10-03)

The current source moves Cloud DNS/socket/HTTP progression out of Radio Manager
into one priority-9 worker. Runtime Cloud controls enqueue copied requests into
four fixed slots; the CLI does not close sockets or perform pairing-file work.
Event wakeups and a bounded 20 ms wait drive the worker. `cloud status` exposes
worker loop count/last tick/max step time and control queue high-water/rejections;
status readers use a cached snapshot without waiting on network work.

The worker uses a fixed 8 KiB stack at `0x242A1800` in the existing lower SRAM4
region. The application/radio pool sizes remain 134/64 KiB. Priority 12 from
the original plan was replaced with 9 to avoid starvation behind the continuously
ready priority-10 ToF processor. The shared ToF image now has exactly one
network consumer under the last-request-wins route contract above. Cloud
admission occurs while FILLING and enters WAIT_CLOUD directly; it never enters
BLE READY. Route changes stop/cancel the old consumer before another frame
can be published. No extra frame copy or runtime allocation was introduced.

Incremental and clean Non-Secure builds, eight disabled-feature syntax checks
and the HIL utility self-test passed. RAM startup confirmed the separate worker,
and an offline stack-fill scan measured 356 of 8192 bytes used. Network stack
high-water, BLE latency during Cloud failures and simultaneous frame CRC/lifetime
HIL remain pending. The PC saw the BLE advertisement but two WinRT connection
attempts failed before GATT discovery, so no BLE latency result was obtained.
This is an implementation checkpoint,
not a passed Milestone 5 gate or a fix for the earlier radio-pool starvation and
ToF permanent-fault findings. No Generate Code is required.

### Cloud TLS credential-list correction (2026-09-25)

A live dual-COM pairing probe reached `W6X_Net_Setsockopt()` but reported
`Invalid TLS credential` before any HTTP response. The Relay passed a single
32-bit certificate tag with `optlen=sizeof(tags)` (four bytes), while the ST67
driver interprets `TLS_SEC_TAG_LIST` as a byte-sized tag list of `optlen`
entries. It therefore tried tag 7 followed by three zero tags. The caller
now passes a count of one while keeping 32-bit storage for the vendor API's
initial 32-bit read. The corrected Non-Secure image builds and runs from SRAM.
On hardware the credential error disappeared, but the NCP then rejected
`AT+CIPSTART` before any HTTP response and Cloud remained unpaired. Cloud
retry attempts still run in the Radio Manager and raised its observed maximum
loop gap to 7150 ms. Paired delivery and the Milestone 5 gate remain open.

## 14. The project's golden rule

The IOC describes hardware ownership and the generated skeleton. The hand-written code describes product behavior. After every Generate Code operation, verify that both still agree about pins, TrustZone, interrupts, memory regions, task stacks, middleware callbacks, and feature flags.
