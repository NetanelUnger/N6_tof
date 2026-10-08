# Cloud update attempt, 2026-10-07

The user attempted browser Cloud installation of the signed version-8 package
while the version-7 development image was running in SRAM. The first attempt
selected `N6_AppliNonSecure-v8-trusted.bin`; that STM2 image has no N6UP update
manifest and is incompatible with the updater. The user then selected the
correct 461280-byte `N6-Firmware-v8.n6fw` package and reported progress.

The corrected attempt is **not an installation PASS**. The browser displayed
an XMODEM response timeout. Non-reset debugger inspection of the live updater
observed:

- `update_active=1`, `update_success=0`, `update_reboot_at=0`.
- Manifest bytes 256, firmware version 8, 450 accepted 1 KiB blocks.
- Received 463050 transport bytes / 450 chunks; image bytes written 460544.
- The package requires 451 blocks; the final block and EOT/finalization were
  absent at inspection. No automatic update reset was scheduled.
- Cloud remained polling/paired with lifetime generation 1 and uptime over
  3.68 million ms. It had no pending input, ACK or output at the second snapshot;
  the receiver was incrementing timeout errors while waiting for more input.

The active/confirmed installation must not be called version 8 on the basis
of browser percentage or its ONLINE label. Inactive-slot payload writes have
occurred, unlike the preceding RAM-only recovery checks, but successful Secure
finalization and trial boot have not been established. Both USB status probes
returned no text while Cloud owned update mode; the CLI explicitly skips CDC
reads during a Cloud/BLE transfer, so this is not evidence of a frozen MCU.

The browser sender has a confirmed retry limitation: an elapsed 15-second
block-control wait throws out of the whole transfer rather than retrying that
block. It also does not send CAN on that catch path. The target then remains in
receive mode until its bounded timeout policy cancels. This does not prove why
the specific block's response was delayed/lost. Receiver idle NAKs or delayed
control records must also be considered when implementing retries; do not
claim that simply increasing a timeout fixes transport reliability.

Successful installation must include finalization/EOT acknowledgment, actual
reset, the running version and boot confirmation. Separately, Cloud pairing
is persistent: a CRC-protected device token/workspace record is saved and loaded
from `n6cloud.cfg` on the NCP filesystem. The six-digit pairing code is used
once and need not be remembered by the MCU. Wi-Fi credential restoration after
a full board boot has not been demonstrated in this attempt; retained Cloud
connectivity here is consistent with the absence of reset.

Evidence is retained locally under
`Tools/.n6-debug/tof-recovery-20261007/cloud-update-*.log` and the associated
status JSON files. Debugger snapshots briefly halted and detached/resumed the
MCU without reset, register mutation or further Flash programming. No sender
or firmware fix was applied during this verification.

## Follow-up: distinguish timeout from DEV-boot reset

The user reported BOOT1 still at 2-3 and proposed a reset into RAM mode. That
jumper would select DEV boot on a real reset; it does not reload the debug RAM
application. A later non-reset inspection instead found application ToF
processing executing at 0x2413267E, continuously increasing `uwTick`, the same
450 accepted blocks and update success=0/reboot deadline=0. Timeout errors had
reached 11 and the receiver had cancelled automatically (`update_active=0`).
USB then replied with firmware version 7, uptime 3848428 ms, ToF ready at
4.0 fps and Cloud polling/paired, generation 1. No reset or version-8 boot is
established; the continuous application state disproves DEV-boot ROM as the
explanation for this attempt. The receiver's temporary ownership of the CLI
explains skipped USB command reads during reception. These results do not
independently prove that the browser CLI has recovered its command session.
Evidence: `cloud-update-inspect-followup.log`,
`cloud-update-after-cancel.json`.

## Authorized diagnostic follow-up and recovery candidate

The user authorized additional diagnostic builds, flashing and website/server
deployment. A diagnostic-only version-7 runtime was loaded into SRAM through
DEV boot. The UART capture remained open throughout the physical tests. Initial
Cloud status referred to an inactive workspace (HTTP 409); a new isolated
browser workspace was paired instead. The user's earlier browser was left open.

The browser/server changes were built and deployed to `natilab-n6`:

- A timed-out block wait now retries the same XMODEM block, with a new Cloud
  record sequence, at most ten times. Cancellation/error sends CAN twice.
- Current firmware output includes `inputSequence`, captured when an output
  slot is published. The sender discards controls from different input records
  and filters idle CRC requests during block waits. Legacy firmware without
  this field still works, but cannot provide this correlation guarantee.
- HTTP output retries are re-broadcast even when already accepted. The browser
  deduplicates by device, command and output sequence with a bounded cache.
  Completed-output retry state is retained on the server. SignalR publication
  is independent of the original HTTP cancellation token and bounded to 10 s.
  This fixes a code-observable loss path; it does not prove that this was the
  initiating cause of the user's original failure.
- The browser validates the N6UP header and declared package size before
  entering receive mode. Progress is capped at 99% until EOT is acknowledged.
  A cancellation button and stage/sequence/control diagnostics are available.

The firmware candidate retains the existing authenticated Secure A/B installer.
Only Cloud updates acquire a nonblocking output-drain callback: after the
original one-second grace period, reset waits for queued output and the input
ACK to drain, with a further 30-second maximum. USB/BLE timing remains the
original one second. Cloud output gains 32 bytes of fixed metadata; payload
queue capacity, task stacks and heap capacity were not increased. Secure,
FSBL and the boot metadata layout are unchanged.

Host verification passed eight sender fault tests, actual SignalR/API smoke
tests locally and against Azure, frontend build/lint and .NET build/publish.
Five native C cases execute the actual updater and XMODEM parser with mocked
Secure/hardware boundaries: duplicate blocks do not cause a second Flash
write; Cloud reset waits for delivery, remains bounded, preserves USB/BLE
timing, handles timer wrap to zero, and never resets a cancelled transfer.
These checks do not establish physical Flash integrity or successful boot.

### Physical partial upload tests

The running version-7 SRAM image contains diagnostics only; the correlation
and drain changes are in the newly signed version-8 package, not yet executing
on the board. Two partial Cloud uploads were intentionally cancelled at 2%,
before EOT/finalization. Both authenticated the manifest and wrote inactive-slot
payload; neither committed an update or reset the board.

1. Normal partial upload: eleven 1 KiB blocks were acknowledged. CAN/CAN reached
   the receiver; USB and ToF resumed and USB reported firmware version 7.
2. Lost-ACK test: the browser's test decoder deliberately omitted the fifth ACK
   (and was configured to omit idle NAKs). A 15-second sender timeout retried
   block 5. UART showed `duplicate seq=5; ACK without redelivery` and the upload
   continued. Subsequently an uninjected ST67 SPI RX HAL error at
   `spi_iface.c:599`, followed by `Failed to receive the remaining bytes`, caused
   two further sender timeouts on block 8. Attempts 2/3 and queued duplicates
   were acknowledged after recovery, without redelivering the payload. The
   upload reached the planned cancellation point, CAN/CAN succeeded, and Cloud
   returned to polling with input/output queues empty. The original initiating
   SPI cause is not established by these two messages. No radio change was made.

The browser console records the wall-clock timeout stages; UART/MCU tick gaps
must not be treated as equivalent to wall-clock elapsed time. Debug UART itself
reported five transport timeouts/dropped messages in this session, so the
capture is useful evidence but not a guaranteed complete trace.

Evidence: `Tools/.n6-debug/cloud-update-20261007/instrumented-ram.log`,
`after-partial-cancel.json`, `after-loss-test.json`, build/sign and deployment
logs. The final website asset is `index-D6ZQKUex.js`; the signed fixed-receiver
package is `FlashImages/N6-Firmware-v8.n6fw`.

### Physical acceptance still open at the end of 2026-10-07

No complete Cloud OTA or version-8 Flash boot is claimed. BOOT1 was last
reported at 2-3; moving it to 1-2 without RESET was requested and still awaits
the user's physical confirmation. After that, install the fixed receiver
through USB, verify version 8 and boot confirmation, then create the next signed
version and exercise a complete Cloud update including EOT, reset, running
version and Secure confirmation. Existing Stage 11/ToF endurance and BLE gates
remain open independently of this OTA verification.

## 2026-10-08: confirmed USB installation and CS timing boundary

The user confirmed moving BOOT1 to 1-2 without RESET. The overnight SRAM
application initially gave a CDC write timeout and no UART output. Two raw
non-reset CPU snapshots showed an application loop loading SysTick VAL and
branching while it was greater than an endpoint of zero. Fault registers were
zero. The locally rebuilt ELF no longer matched that SRAM image, so its symbolic
backtrace/function labels were not used as evidence. The raw instructions match
the board-local `spi_port_set_cs`/vendor WAIT_FROM absolute-endpoint calculation.
The application subsequently progressed before the recovery reset; this is a
pathological wait/worker starvation boundary, not proof of a permanent fault.

The CS-low minimum interval now uses elapsed ticks modulo LOAD+1, a rounded-up
SystemCoreClock/1e6 conversion and a bounded core-cycle software fallback if the
timer stops. It cannot require observing exactly VAL==0. Five native tests run
the actual wait against skipped-zero, ordinary, reload, frozen and disabled
timer samples. The compiled `spi_port_set_cs` stack frame remains 8 bytes.
This fix is separate from the unproven initiating cause of SPI RX HAL errors.

After a ST-LINK system reset, existing Flash version 7 booted. Signed fixed
version 8 (462176 bytes, including the CS fix) was installed via USB XMODEM.
EOT/finalization succeeded, the automatic reset booted version 8, and the normal
confirmation task logged `boot confirmed; rollback window closed`. The installer
independently verified USB version 8 after the confirmation window. Version 8
was then connected to test Wi-Fi and paired again to the isolated Cloud workspace:
pairing had not restored at this boot. Version 9 was built/signed package-only
from the same fixes to exercise the next Cloud installation.

Evidence is appended to `flash-cloud-20261008.log`; USB install/build/Wi-Fi/pair
logs and the exact running-v8 ELF are retained in the same ignored diagnostic
directory. Version-9 Cloud OTA finalization/boot is recorded below.

### Full Cloud v8-to-v9 installation PASS

The 462176-byte signed v9 package (SHA256
`917A11B97CE334C3707A620EEE644E6952959E754B9CF1416484285131328518`) was uploaded
through the deployed browser UI to the physical v8 receiver over Wi-Fi/Cloud.
All 452 XMODEM-1K blocks and one EOT attempt were acknowledged. Browser controls
carried matching `inputSequence`; there were zero sender timeouts/retries in
this full run. First block transmission to EOT ACK took 352.898 seconds
(approximately 1.28 KiB/s of signed-package data).

UART showed all 461920 signed image bytes stored, the candidate committed and
input 453 acknowledged. HTTP output sequence 454 delivered the final binary
ACK; output sequences 455 and 456 delivered the result and completion marker
before the automatic reset. The reset-boundary UART message itself was not
captured; asynchronous diagnostics are not guaranteed to flush before reset.
The boot banner identified application version 9 and the confirmation task
logged `boot confirmed; rollback window closed`. An independent USB probe after
that window returned firmware version 9, low new uptime, ready ToF and radio.
The tracked build version was then advanced from 8 to 9.

Wi-Fi and pairing had not restored after this boot: the device was disconnected
and unpaired, while the browser still displayed its previous ONLINE/version-8
state. That label is not boot/installation evidence. The test reconnected Wi-Fi
and paired again to the existing isolated workspace, then verified Cloud CLI
`version` returned 9 and fresh ToF frames arrived. USB status counted 54 Cloud
frames sent with zero drops/request errors at the post-connection snapshot.
The workspace file was saved through the UI and the already-installed firmware
file cleared from the upload input. No automatic credential/pairing persistence
claim is made. Debug UART after the v9 boot reported zero dropped messages,
timeouts and HAL errors at that snapshot.

Evidence: `full-ota-browser-20261008.json` (complete bounded browser trace),
`flash-cloud-20261008.log`, `verified-v9-20261008.json`,
`final-v9-cloud-20261008.json` and USB install/build/Wi-Fi/pair logs in the ignored
diagnostic folder. This is a physical Cloud OTA/Flash boot PASS for this run;
it does not prove repeated-update endurance, BLE acceptance or frame-exact NPU
Stage 11. Those existing gates remain open.
