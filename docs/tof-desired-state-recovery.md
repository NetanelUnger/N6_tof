# ToF desired state and local recovery

## Longer campaign terminal continuation, 2026-10-11

The serialized continuation is **PASS**, ended at stored timestamp
`2026-10-11T10:49:08.887522+03:00`, after5794.594s. Original campaign remains
**FAILED3807.187s**; its second profile is not promoted to PASS. The continuation
reran that failed block and the two remaining blocks on unsigned4D953D64...:
5446.735s/16993 CRC records, twelve successful ToF faults and nine pause gates.
Combined with the separately accepted first old7AC39D92... profile, selected
coverage passes7263.641s/22653 CRC records, sixteen faults and twelve20s pause
gates. This is mixed-candidate coverage, not two hours on the new ELF alone.
The failed extra profile retains5664 valid records/four passed ToF sub-gates;
there were twenty physical fault attempts in total, not just the accepted16.

Accepted ToF first-fresh recovery times:380/309/270/346/381/368/270/327/
336/371/270/333/316/375/267/295ms. Median/Box radius2, first40 fresh CRC records
after each running fault, pause cancellation, no unexpected recovery and zero
queue failures pass. Four USB host-session close/reopens and three warm SRAM
loads pass (original warm1 plus current-candidate warm2/warm3,30 records each).
Four genuine missing-response probes have `status=3 genuine_fence=1`, no ToF
recovery,143/143/143/144 CRC records and seven USB pings each. Coordinated NCP
recovery times20011/19968/20000/20792ms include saved-credential IP return.
Two current-candidate ordinary Wi-Fi gates preserve deliberate cancellation
for23.297/23.516s and restore renewed RAM intent in17812/23453ms of host
observation,143/157 CRC records, without NCP/ToF counter changes.

An additional unsolicited Wi-Fi disconnect was observed in the final profile
at HAL2174577. The new ordinary-link helper started at2174829, IP event2176783,
and returned success at2177516 (call2687ms), without NCP reset; ToF/USB and
profile NCP baseline continued. This proves recovery from that observed loss,
not the RF/AP/NCP root cause. No password, persistent credential, saved pairing
or configuration was read/written by the host. Strict FS bytes/CRC/fences remain.

Final verification passes23616 CRC records across accepted profiles and separate
gates. ToF ready/advancing4141->4177,8/8/0/gen8; Wi-Fi IP, Radio ready, BLE
advertising/disconnected, imageNONE, Cloud unpaired. UART2021/2021, zero drops/
errors and no buffers in use; radio allocations/SPI faults0. Radio max gap269ms,
BLE pump20820ms includes NCP recovery and is not active-BLE latency acceptance.
Supervisor/UART children exited0; COM6/COM8 availability open/close passed and
no debugger/programmer/build process remained. All owned handles released.

Unsigned ELF4D953D643096FFF95E7013FEB21E311220C7D0622783EB6A9C4B3CA914B962C6,
binary487952/heap383792 (minimum368640, margin15152), eight static bytes added,
header9 preserved.33 native/24 feature/build-only pass. No new task/capacity/
steady allocation, HTTP/TLS, Flash, sign/package, config/authentication mutation,
commit/push/deploy or full task4 run. Active BLE CLI/DMA failure, full radio/
Cloud endurance, independent FS integrity and electrical root causes remain
open. Ignored evidence: `tof-endurance-20261011/continuation-1/campaign.json`,
`verified-terminal-summary.json`, `audit-final.log`, raw UART and per-gate files.

## Longer campaign stopped on Wi-Fi loss, 2026-10-11

Historical failed checkpoint and fix preparation; terminal coverage is above.
The original7AC39D92... campaign is **FAILED**, not a two-hour acceptance.
It stopped at3807.187s after the second profile's final Wi-Fi gate. Profile1
passed1816.906s/5660 CRC records; profile2 completed all six ToF phases in
1817.235s/5664 CRC records but failed `STA GOT IP`. Combined11324 CRC records
have zero CRC errors; all eight ToF faults and six pause gates passed. One warm
load, USB reopen and genuine-fence NCP probe passed. Wi-Fi initially returned
after the ordinary disconnect/volatile-intent fixture, then an unsolicited
disconnect was logged around HAL2159180, about4.8min after that restoration.
No SPI fault, radio allocation failure or new NCP recovery occurred. The RF/NCP/AP
cause of the disconnect is unproven. ToF remained ready/advancing with8/8/0/gen8;
UART1927/1927 without drops/errors. All owned handles were released; failed
reports/UART remain in ignored `tof-endurance-20261011`, with `terminal-summary.json`.

Code inspection found a distinct desired-state gap: stored-credential association
was restored after NCP initialization only, not ordinary confirmed Wi-Fi loss.
The existing Wi-Fi control worker now tries the same Secured=1/empty-password
association for a confirmed disconnected station with retained desired intent.
It prioritizes queued user work, reports WIFI_CONNECT waiting and atomically
closes fresh BLE notification admission before calling the existing helper.
Explicit disconnect, missing credentials, unconfirmed state, DHCP, reset,
true fences and owned DNS/BLE replies prevent submission. At most three calls
are made per unsuccessful loss episode, at least10s after completion of the
preceding call; the existing worker wake cadence can make this interval longer.
Success or cancellation resets this small retry lifecycle. SDK execution
budgets, shared-NCP reset trigger/proof, generations and capacities are unchanged.
No healthy NCP is reset for ordinary link loss and no credential is written.

Unsigned fix ELF4D953D643096FFF95E7013FEB21E311220C7D0622783EB6A9C4B3CA914B962C6,
binary487952/heap383792/header9:33 actual-C/native files,24 feature compiles and
build-only pass. Eight static bytes added, no new task or steady-state allocation;
new helper compiler frame32 bytes, control entry184 (not worst-stack proof).
Initial native compiler attempts were blocked by temporary-directory errors;
workspace-temp rerun passed. A stalled build was stopped before the final
successful build; these host failures are retained. New RAM warm gate passes
30 CRC records without a ToF retry. Focused cancellation/ordinary restoration
passes: 143 CRC records, deliberate disconnect held23.3s, intent-only RAM
readback1, saved-credential IP return in17812ms of host observation (including
worker wake), association call2642ms, no ToF/NCP recovery counter change.
The first focused host attempt falsely wrote zero using bare programmer data
arguments; its failed report remains, and hex-prefixed writes now require
scalar readback before acceptance. No firmware change was needed for that fix.
Three serialized30-minute profiles reran the failed block and the remaining
coverage under `tof-endurance-20261011/continuation-1`. The original first
profile is a separate old-candidate PASS; eventual aggregate coverage is mixed
candidates, not a fresh two-hour single-ELF acceptance. Continuation completed
PASS as described above; no full task4 or Cloud return is accepted. Evidence: ignored
`tof-wifi-link-20261011` and the continuation directory.

## Two-hour RAM campaign started, 2026-10-11

Historical starting checkpoint; the terminal failure and fix above supersede it.
User explicitly requested a longer local-PC robustness campaign. The serialized
runner was started under ignored `.local-dependencies/diagnostics/tof-endurance-20261011/`;
`campaign.json` holds the owner PID, current step, UTC timestamps and terminal
outcome. Do not open competing COM6/COM8/SWD handles while its steps are running.
The unchanged exact7AC39D92... unsigned ELF/header9 is checked before every step.

Selected coverage: four profiles with six300s phases each (at least7200s sustained
profile time),16 previously tested single PD8-low ToF faults,12 twenty-second
pause gates, four existing genuine missing-NCP-response probes, two warm RAM
loads, two ordinary Wi-Fi disconnect/restore cycles and four five-second USB
host-session close/reopens. USB cable/power is untouched. Wi-Fi restoration uses
only the prior approved volatile saved-credential intent fixture; no password,
new credential or saved record write. Warm initialization legitimately resets
volatile settings; each profile selects Median/Box radius2 again.

Acceptance: exact CRC on every received record, advancing healthy-generation
frame IDs,40 advancing fresh records after each running sensor fault, one
successful recovery per injected fault, no unexpected recovery in healthy/pause
intervals, preserved processing selection/radius, zero queue/radio allocation/
UART delivery errors, USB responsiveness and saved-credential Wi-Fi return.
Known sensor counter restart is allowed only at an observed recovery. Each
NCP probe must preserve ToF counters and publish at least100 CRC-valid records.
Cloud remains unpaired and excluded from restoration acceptance.

Stop condition: first failed gate, child deadline, changed code/artifact hash,
operator `stop-request` file or three-hour wall limit. Further injections stop;
failed evidence stays intact, followed by best-effort safe stream cleanup and
final health capture without reset to conceal the failure. This is IN_PROGRESS,
not PASS. Initial board was ready/advancing45113->45151, with no competing test
process. First warm load/30-record gate and saved-credential Wi-Fi restoration
passed; the first sustained profile started. A requested Codex heartbeat could
not be created because this delegated thread does not support local-thread
automations; campaign checkpoints/stop control continue on the local PC.

## Bounded longer RAM validation, 2026-10-11

Reused the exact unsigned `7AC39D925C371A7B774A5CCA55E9EDAF41394739E95DC500E2C5FEC43252A8AA`
ELF on `ble`/`d89a510`, preserving the existing dirty work. No firmware code,
capacity, budget or steady-state allocation changed in this follow-up. Binary
487440 bytes, heap384312 and header9 remain unchanged. The previous32 native,
24 feature and three build-only checks apply to this unchanged candidate;
they were not rerun. Board tests were serialized with no competing HIL/debugger.
The initial healthy snapshot after several hours is not monitored overnight
endurance evidence.

Three consecutive warm SRAM loads passed without a ToF retry: each produced30
advancing CRC-valid USB records, ready state and a USB ping. Startup still logged
the known incomplete Cloud FS read; it is not evidence of storage corruption.
After the last load, the previously authorized volatile Wi-Fi intent fixture
restored the existing saved-credential connection in18500ms with21 USB pings.
No password was read/sent and no saved credential/configuration was written.

The longer ToF profile passed734.938s (six phases, each122s),2100 CRC-valid
records, CRC errors0 and30 paired ToF/radio/ping checkpoints. Alternating Median
and Box with radius2 preserved both the selected filter in frame metadata and
its parameter through recovery. Three running PD8-low faults each recovered
with40 fresh advancing records; old complete transport records were recorded
separately before the known sensor-counter restart. The two intentional pauses
and one latent fault while paused each held stable frame/recovery counters for
20s. The latent fault caused one recovery only after resume. UART measured
fault-detection to first-fresh-frame publication at344/272/272/380ms, respectively;
the third measurement is the latent `stream resume` error. All four recoveries
used one attempt: attempts/successes4/4, failures0, generation4. These are MCU
timestamps, not optical or host delivery latency. No recovery occurred during
healthy intervals; NCP counters stayed unchanged throughout this ToF profile.
Calibration reuse is covered by the previous actual-C checks, not an independent
calibration accuracy measurement in this hardware run.

One separately serialized existing `radio fault-test` then forced an actual
missing AT reply with NCP CHIP_EN low after owner quiescence. UART confirms
`status=3 genuine_fence=1`; coordinated recovery finished in19749ms, including
2652ms saved-credential Wi-Fi restoration to IP. USB delivered143 CRC-valid,
strictly advancing records and seven pings while ToF stayed ready with unchanged
attempts/successes/failures/generation4/4/0/4. NCP counters advanced exactly once
from2/2/0 to3/3/0. This controlled no-response test does not identify the natural
SPI fault cause, test an executing BLE CLI/DMA failure, or validate Cloud return.
Cloud remains unpaired due to the unresolved malformed FS read boundary.

Final board: ToF ready and advancing1952->1991, processing off/map off, Wi-Fi IP,
USB/radio available, BLE advertising/disconnected, imageNONE and Cloud unpaired.
UART615/615, drops/errors0; radio allocation failures0 and ToF queue failures0.
Bounded processing drops were observed; no zero-drop/full-latency or worst-stack
claim is made. COM6/COM8/debugger/programmer handles were released. No physical
power cycle, Flash/config/authentication write, header change, signing/package,
HTTP/TLS change, commit/push/deployment or full task4 endurance occurred.

Ignored evidence: `.local-dependencies/diagnostics/tof-longer-20261011/` contains
the exact ELF/bin and manifest, three load logs/warm reports, runtime profile,
coordinated-continuity report, UART and final-board snapshots, and reusable host
collectors. See [official ST FS lead and remaining blocker](radio-coordinated-recovery.md#official-read-only-diagnostic-lead-2026-10-11).
Repeated/persistent fault exhaustion, latest-command-during-reset HIL, Stage11,
BLE/Cloud image routes, broad endurance and original electrical cause stay open.

## Warm startup follow-up, 2026-10-10

The acquisition owner now quiesces I3C1 and only DMA channels0/1/2 before the
first XSHUT pulse. A RAM reload can replace C handles while the externally
powered sensor/controller retains prior state; `HAL_I3C_Init` alone does not
force-reset that controller. Startup sensor errors use the existing three
recovery attempts and stop in `error` on exhaustion. A healthy boot performs
one local quiesce/configuration and no recovery retry. Software transform and
ThreadX object failures remain fatal. No healthy-runtime reset loop is added.

Startup and runtime share XSHUT/DAA/init/calibration/profile configuration.
Calibration is read once after a successful boot read, with one four-byte
ready flag; runtime recovery reuses the same calibration and transform. The
latest desired settings and first-fresh-frame publication barrier remain in
force. A pause received during the interrupt wait cancels only its missing-
frame timeout; actual transfer errors still request recovery. Map-off does
not pause ranging. Budgets, tasks, stacks, pools and transport capacities are
unchanged; there is no new steady-state allocation.

Control evidence: project `main.c` configures PD8 as push-pull XSHUT and PD9 as
interrupt input. The X-NUCLEO-53L9A1 schematic uses XSHUT through a level shifter,
with separate regulated rails powered by Nucleo5V; it exposes no verified MCU
rail-enable control. The vendor sample uses low50ms/high50ms. This candidate
keeps those times and reads MCU GPIO **after** each settle interval. It neither
cuts sensor power nor proves the sensor-side waveform. DAA logs the exact HAL
substep/error/state/EVR, requires exactly one assigned target and retains the
original5000ms HAL budget and 1MHz/12MHz timings/address0x52.

The first diagnostic candidate37733751... incorrectly sampled IDR immediately
after BSRR: low0/high0 caused bounded XSHUT failure, three retries, then error.
A later read-only HOTPLUG snapshot showed PD8 IDR/ODR high and output mode.
The candidate was corrected to read after the existing50ms delays; its actual-C
test now rejects an early read. Both failed candidate and report are retained.
Do not infer a stuck wire from the immediate-read result.

Final unsigned ELF SHA-256:
`7AC39D925C371A7B774A5CCA55E9EDAF41394739E95DC500E2C5FEC43252A8AA`.
Non-Secure binary487440 bytes, C heap384312 bytes (minimum368640), header9.
Non-Secure/Secure/FSBL build-only checks passed,32 native files passed, and24
feature-mode checks passed. The final platform test was rerun after moving the
readback; unchanged native files were not needlessly repeated. Compiler frames:
XSHUT32, DAA56, platform recovery120, sensor configuration32, recovery240 and
acquisition72 bytes; these are not worst-stack measurements.

The corrected ELF passed two warm SRAM loads from the prior ToF-error state:
PD8 low0/high1, one DAA target, USB ping and advancing frames123->162 and212->251.
This supports the controller-quiescence fix but does not isolate the original
electrical/controller cause or prove every warm-start condition. No physical
power removal occurred in this follow-up.

The focused USB gate passed deliberate pause for longer than1500ms, stable
frame/recovery counters while paused, resume and continued acquisition with
map-off. Two separate single PD8-low HOTPLUG injections produced actual frame
DMA completion errors and first-fresh-frame recovery in316/267ms, preserving
Median/USB dataset/depth intent. Each used one attempt; no failure-counter growth
or queue failure occurred. The initial host report received40 CRC-valid records
but failed its incorrect cross-reset monotonic frame-ID assertion: four old
complete transport records drained, then36 advancing new-generation records.
Sensor metadata restarts its counter on initialization. The corrected collector
retains draining IDs separately and requires40 advancing new-generation records;
its repeat passed with10 baseline plus40 fresh records and CRC errors0. The
failed report is retained. These two fault probes are not an endurance test.
No repeated hardware fault/exhaustion, new command during hardware recovery,
Stage11 NPU, BLE/Cloud image-route or worst-stack gate was run in this follow-up;
native tests cover bounded exhaustion and latest-command races.

After the RAM reloads, the already authorized volatile Wi-Fi desired-intent
fixture restored the existing NCP saved-credential connection:18703ms observed
host completion,21 USB pings, and ToF continuity. No password was read or sent,
and no credential/configuration file was written. Final board is ToF ready and
advancing1390->1429, Wi-Fi IP, radio/USB available, BLE advertising/disconnected,
image destinationNONE and Cloud unpaired. ToF attempts/successes2/2, failures0,
queue failures0; Radio allocations failed0; UART319/319 with drops/errors0.
Processing drops were observed, as expected with bounded slots and slower
processing; this is not zero-drop or full-latency acceptance. COM6/COM8 and all
test debugger/programmer handles are released. Read-only process enumeration
via CIM was denied by the sandbox; the normal process list and completed owned
tool sessions showed no remaining Python/GDB/programmer test process.

All raw UART, exact ELFs, build/native/feature logs and failed/successful JSON
reports are retained in ignored
`.local-dependencies/diagnostics/tof-warm-init-20261010/`; `summary.json` indexes
the exact final build and failed/successful checkpoints. No Flash, version,
saved configuration, provisioning, HTTP/TLS, signing/package, commit/push,
deployment or endurance change was made. The independent NCP binary-FS/Cloud
blocker remains paused and is not diagnosed as stored corruption.

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
exhaustion. Sensor boot errors now enter the same bounded recovery path.
Initial transform initialization failures and software/ThreadX object failures
remain fatal: resetting a peripheral cannot repair corrupted
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
sixteen scenarios: running/paused preservation, a newer command during
initialization, DMA reset failure and retained ownership, initialization retry
without double release, three-attempt exhaustion, restarts without a fresh
frame, confirmation and thirty-frame budget replenishment, stale-generation
rejection, exclusive route/map/dataset intent, initial quiescence, startup DAA
and calibration retry, cache reuse, startup exhaustion and pause-timeout
cancellation. `test_tof_startup_platform.py` additionally runs actual XSHUT/DAA
functions with mocked GPIO/HAL, checking settled readback, target count, bounded
extra responses and precise substep failures with the original HAL budget.
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
