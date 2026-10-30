# STM32N6 ToF, Wi-Fi and BLE

Firmware for the NUCLEO-N657X0-Q: acquire 54×42 VL53L9CX depth images,
run Neural-ART inference, and view images or issue CLI commands over USB,
BLE or the Cloud relay. ThreadX runs the application; an FSBL and Secure
application provide external-NOR boot and signed Non-Secure A/B updates.

## Hardware and connections

- **NUCLEO-N657X0-Q**, **X-NUCLEO-53L9A1** (VL53L9CX), and
  **X-NUCLEO-67W61M1** (ST67W611M1).
- A data-capable USB cable on **CN8** for the application console and updates.
  ST-LINK's separate USB/VCP connection provides boot and UART diagnostics
  at **115200 baud, 8N1**. COM numbers vary by computer.
- Optional GC9A01 240×240 SPI display; disabled by default in
  [config.h](AppliNonSecure/Core/Inc/config.h).

| Interface | Connections |
|---|---|
| ToF / I3C1 | SDA PC1, SCL PH9, XSHUT PD8, INT PD9 |
| ST67 / SPI5 | SCK PE15, MISO PG1, MOSI PG2, active-high CS PA3, CHIP_EN PE10, BOOT PD5, SPI_RDY PE9 |
| Optional display / SPI4 | SCL PE12, SDA PE14, DC PE1, CS PE13, RST PE2; **3.3 V** and common GND |

The display's SDA/SCL labels mean SPI, not I2C. ToF PD9 and radio PE9 share
EXTI9: the radio-enabled build uses PE9 interrupts and polls ToF readiness.
Check shield power, JP1/JP2 and SB31/SB34 against the intended wiring before
first use; software cannot validate solder bridges. Pin configuration lives in
[N6.ioc](N6.ioc). Do not change jumpers or power-cycle an already working board
for a routine USB update.

## Build

Use Windows PowerShell and **STM32CubeIDE 2.2.0**, including its GCC, make,
CubeProgrammer and signing tools. The scripts default to
`C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE`. Open/import the `FSBL`, `AppliSecure`
and `AppliNonSecure` projects if working in the IDE. Vendor radio sources are
tracked in `ThirdParty`; do not redirect builds to an external SDK copy.

Run commands below from the repository root, **`N6/project`**, on `main`.
For an existing generated build, compile Non-Secure changes without flashing:

```powershell
.\Tools\Build-NonSecureIncremental.ps1
```

For the persistent **XIP** application, first establish the board's confirmed
version and inactive slot. Enter those verified values; do not infer them from
an old README or the source version header:

```powershell
$nextVersion = [uint32](Read-Host 'Confirmed firmware version + 1')
$slot = Read-Host 'Verified inactive slot: A or B'
.\Tools\Build-Xip.ps1 -Slot $slot -FirmwareVersion $nextVersion -Label release
$package = ".local-dependencies\xip\v$nextVersion-$slot-release\N6-XIP-$slot-v$nextVersion.n6fw"
.\Tools\Test-XipPackage.ps1 -Package $package -ExpectedSlot $slot -ExpectedVersion $nextVersion
```

`Build-Xip` builds/signs the slot-specific package without programming hardware;
its output directory also contains build metadata and hashes. Keep the normal
watchdog, diagnostics and settings-preservation defaults. Output directories
are immutable: do not overwrite an earlier release to reuse its version.

Only regenerate code after changing `N6.ioc`. Review the
[CubeMX preservation rules](AGENTS.md#3-cubemx-rules) afterward. FSBL, Secure,
linker, startup or TrustZone changes need their corresponding build/validation;
a Non-Secure USB package cannot install a replacement boot chain.

## Run and update over USB

On an already provisioned board, keep the existing Flash-boot configuration
(BOOT0 and BOOT1 at 1–2), connect CN8 and open its CDC terminal. Start with
`version`, `status`, `tof status` and `rps status`.

To install the verified XIP package above, close any terminal using CN8 and run:

```powershell
.\Tools\Send-Xmodem.ps1 -File $package
```

The sender discovers CN8; use its `-Port` option only with the actual port.
The board finalizes the signed update and reboots automatically. Verify the
expected `version` and successful trial confirmation in the boot/update
diagnostics before declaring installation complete. An EOT ACK alone is not
proof of a confirmed boot; if verification fails, inspect the outcome before
retrying or selecting another version.

**Preserve the active slot and a known recovery package.** Updates must retain
signature/hash checks, strictly increasing versions, inactive-slot writes and
rollback. Do not erase NOR, bypass verification, or use the RAM-image update
lane as a substitute for a slot-specific XIP package. First provisioning or
boot-chain repair is a separate procedure: see the
[training/build guide](training/README_HE.md) and
[factory provisioning tool](Tools/Factory-Provision.ps1); it can erase Flash
and is not the routine USB update path.

## Everyday commands

| Command | Purpose |
|---|---|
| `help`, `version`, `status` | Command list, running version and overall state |
| `tof status`, `rps status` | Sensor pipeline and NPU status |
| `radio status`, `wifi status`, `ble status`, `cloud status` | Radio health, recovery and transport counters |
| `MAP ON`, `MAP OFF` | Start/stop sensor images for the requesting transport |
| `MAP ENCODING UINT8` | Compact wireless images; RAW, UINT16 and JPEG are also supported |
| `DEMO MAP ON 1000`, `DEMO MAP ON 300` | Synthetic moving-pixel images every 1000 or 300 **milliseconds** |
| `DEMO MAP STATUS`, `DEMO MAP OFF` | Demo interval/admission/drop counters; stop the demo |

Demo intervals are 100–60000ms; legacy `ON 1`/`ON 2` operands are rejected.
Source IDs advance even when publication is skipped; `accepted` means queued,
not received by a browser. There is one remote image destination at a time
(USB, BLE or Cloud); switching transport can move the image stream.

## Detailed documentation and limits

- [Training, model build and BLE console](training/README_HE.md)
- [Wireless image formats and CRC contract](docs/wireless-image-codec.md)
- [Wi-Fi/settings persistence](docs/product-settings49_HE.md)
- [UART/USB diagnostic controls](docs/full-diagnostics57_HE.md)
- [Radio recovery ownership and limits](docs/radio-coordinated-recovery.md)
- [BLE/Cloud validation results and remaining limits](docs/ble-console-20261029.md)
- [Engineering constraints and Flash map](AGENTS.md), [change history](CHANGELOG.md)

This is a development platform, not a production security configuration.
The demo Cloud transport uses plaintext HTTP; do not transmit secrets or
sensitive captures through it. The shared development signing key and `-nk`
boot-image flow are not a production physical root of trust. Image backpressure
can drop frames, and verbose UART output can overflow its bounded queue;
neither continuous image delivery nor lossless diagnostic logging is guaranteed.
