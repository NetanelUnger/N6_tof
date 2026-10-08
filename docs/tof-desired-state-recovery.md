# ToF desired state and local recovery

The acquisition task owns the VL53L9CX, I3C1 and its three DMA channels. A
runtime sensor interrupt timeout, transfer-start/completion error, command
failure, or corrupt parsed frame requests local recovery. The processing task
can request recovery but never touches the sensor or I3C controller.

`TOF_DesiredState_t` is the authoritative in-RAM command intent: pause, USB map
versus dataset mode, selected image-channel mask, image processing parameters,
and the exclusive USB/BLE/Cloud destination. Commands update it atomically and
advance a revision. Recovery never overwrites it with an older snapshot. A
command arriving during initialization takes effect on the restored sensor.
The local display retains its independent selection. This state survives a
**local sensor reset**, not a board reset or power loss.

## Recovery sequence

1. Latch the original error, enter `recovering`, block new image publications,
   and advance the raw-frame generation.
2. Disable only I3C1 and DMA-channel 0/1/2 IRQs, reset I3C1, and perform bounded
   per-channel DMA suspend/reset/deinitialization. Rebuild the bus/DMA handles,
   controller configuration and transaction flags; keep diagnostics cumulative.
   SPI5, display DMA, USB and EXTI9 keep their existing ownership.
3. Release the failed raw slot only after the bus/DMA reset succeeds. Drain
   queued old raw frames without flushing/reseeding the free pool. A processing
   or display-owned slot stays owned until its existing consumer releases it.
4. Toggle sensor XSHUT, assign the dynamic I3C address, reload the sensor patch,
   and apply the existing autonomous 100 ms profile. Dynamic address assignment
   now bounds HAL_BUSY responses and reports errors rather than entering the
   global Error_Handler.
5. Apply the latest desired pause state. Reuse the original calibration and
   transform for the same sensor; recovery does not create another transform
   or repeat its lazy first-frame allocations.
6. In running mode, stay `recovering` until acquisition finishes a fresh full
   frame and its acknowledge command. Then allow image publications again.
   In paused mode, successful configuration is sufficient and ranging stays off.
   Processing rejects blocked/error/old-generation frames before transforming
   and before publishing. Existing complete transport snapshots finish through
   their normal consumers; exclusive-route draining remains in force.

Recovery has three attempts, with a 200 ms yield after a failed attempt. A
restart without a complete fresh frame does not replenish the budget. Thirty
consecutive complete acquired frames replenish it. Exhaustion leaves ToF in
`error`, with the desired state retained and any unquiesced DMA slot quarantined;
it does not reboot the MCU or reset the radio. A board reset is required after
exhaustion. Initial transform/boot initialization failures and software/ThreadX
object failures remain fatal: resetting a peripheral cannot repair corrupted
queue objects or transform allocation errors.

## Diagnostics and validation

COM6 emits `FAULT detected ... RECOVERY starting from desired state`, the
revision/destination/mode/channel/filter snapshot, each attempt and failing
substep, then either `RECOVERY complete` or a recovery-exhausted fatal message.
`tof status` and UART `t`/`T` watch show attempts, successes, failures, budget,
generation and the latest recovery substep/error. The original fault remains
visible after successful recovery.

```powershell
training\.venv\Scripts\python.exe hil_tests\test_tof_recovery.py
```

The native harness compiles the actual desired-state/recovery functions
extracted unchanged from `tof_app.c`, mocks ThreadX/HAL boundaries, and checks
ten scenarios: running/paused preservation, a newer command during
initialization, DMA reset failure and retained ownership, initialization retry
without double release, three-attempt exhaustion, restarts without a fresh
frame, confirmation and thirty-frame budget replenishment, stale-generation rejection, and exclusive route/map/dataset intent.
Visual Studio C tools or a native `cc` are required. These tests do not emulate
DMA registers or establish physical sensor recovery.

Hardware acceptance must capture COM6 from boot, select the map channel/filter
and USB/BLE/Cloud destination, induce a single sensor or DMA failure, and require
the first fresh frame, continued CRC-valid frames, unchanged intent and live
USB/radio. Repeat with a newer command during recovery and a persistent failure;
require bounded exhaustion and no raw-slot reuse. Then repeat the frame-exact
Stage 11 NPU and exclusive image-route gates. Build/sign and native checks alone
do not establish demo endurance or fix the initiating I3C fault.

## Connected SRAM verification, 2026-10-07

The user prepared DEV boot (BOOT0 1-2, BOOT1 2-3), connected both USB cables,
closed terminals and reset. The RAM loader replaced local Secure and Non-Secure
images, verified vectors and reached ThreadX. The debug application reports
version 7; the separately signed v8 release package contains the same recovery
source. External NOR was not written and no MCU reset was used inside any
recovery check. Fresh RAM loads between transport checks cleared prior radio
faults; they are not evidence of local radio recovery.

Evidence is retained in the ignored local directory
`Tools/.n6-debug/tof-recovery-20261007/`, including the full `uart.log`, each
RAM-load log and separate JSON/log reports. Fault injection drives sensor
XSHUT (PD8) low through its GPIO BSRR register, inducing an actual I3C runtime
failure. The first checks briefly halted the MCU through GDB. The later BLE
and Cloud checks use CubeProgrammer SWD `mode=HOTPLUG`, writing only the
self-clearing GPIO register without halting or resetting the MCU. This tests
sensor/bus restart after a transfer fault, not every possible DMA failure.

| Check | Result and limits |
| --- | --- |
| USB dataset, depth, Median | PASS. First fresh complete frame 371 ms after the fault; 40 subsequent distinct N6DF v3 records with valid header/raw/model CRCs. Dataset, USB, channel mask 0x01 and Median were retained; PONG replied; zero raw-queue failures. `usb-gate.json`. |
| BLE baseline, first boot | FAIL before injection: seven complete amplitude images, then notification/AT failures. Retained in `ble-gate.json`; it cannot establish recovery acceptance. |
| BLE fresh boot, GDB injection | Ten baseline frames; sensor recovered, but the twenty-post-frame transport gate failed. `ble-gate-clean-boot.json`. |
| BLE fresh boot, non-halting injection | Ten baseline frames followed by 15 complete CRC-valid amplitude images after recovery, preserving BLE, mask 0x02 and Median. First fresh acquisition at 381 ms. About 16 s later the AT raw prompt failed and protocol traffic was fenced; the full gate failed. `ble-gate-hotplug.json`. |
| Real Cloud-phase fault | No deliberate injection: frame acknowledge command failed at tick 157707, reinitialized at 157953 and first fresh acquisition at 158017 (310 ms). Acquisition resumed automatically; intent and original error remained visible. |
| Cloud, Ambient, Median, non-halting injection | PASS in `cloud-gate-relative.json`: exactly one added attempt/success/generation, no added recovery failures, 20 further accepted Cloud frames, same CLOUD/mask 0x04/Median intent, Wi-Fi GOT IP, USB PONG and zero raw-queue failures. Fresh acquisition took 380 ms. |

The first Cloud report (`cloud-gate.json`) retained a failed assertion: its test
incorrectly expected lifetime counters of one despite the earlier real fault.
It had already observed 21 further accepted frames and two successful
recoveries. The corrected test compares before/after counter deltas and writes
a separate report; it does not overwrite that failed evidence. A separate
isolated browser workspace displayed LIVE Ambient 54x42 after recovery with
advancing frame IDs and changing CRCs (e.g. frame 436 / CCFC7376, then
452 / 49639E33). The user's original browser workspace was left untouched.

The final Cloud boot observed three attempts, three successes and zero
recovery failures. Thirty complete frames replenished the consecutive retry
budget between the faults. This is targeted recovery evidence, not a multi-hour
soak. BLE transport/endurance and the exact initiating I3C size error remain
unresolved; an AT failure approximately 16 s after recovery does not establish
that the ToF reset caused it. No radio capacity or scheduler change was made.
Physical persistent-fault exhaustion, a newer command arriving during reset,
the full exclusive-route gate and a matching moving-hand Stage 11 remain OPEN.
The native tests cover exhaustion/latest-command ownership at mocked boundaries.
