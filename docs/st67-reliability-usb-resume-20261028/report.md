# ST67 reliability: checkpoint CP1

2026-10-28, evidence through 21:05:15 UTC / 23:05:15 Asia/Jerusalem. Owner: Codex.

CN8 is present again and the bounded USB tests pass. The running application and
Secure confirmed version are **51**, not the locally retained B50. P0 remains
**BLOCKED** on identifying and preserving the exact running build and recovery
artifacts. P0-01 is reopened for the live artifact; the completed CP0 host inventory
remains valid. P0-02 and P0-04 have partial measurements, P0-05 remains open,
P0-03 remains complete, and P1-P7 have not started. No reliability fix is claimed.

## Connection, ownership and exact identity

- CN8: COM8, VID 0483, PID 5740, serial N6TOF001; ST-LINK: COM6.
- No existing hardware lease or relevant live serial/debug owner was found before
  acquisition. Every run exclusively acquired the repository's shared OS lock and
  owner JSON, recorded PID creation identity, and released its handles and lease.
  There was no stale-owner takeover, Git trust addition or ACL change.
- Worktree remains `feature/n6-xip-ota-usb` at
  `5432d4ae2b10ef7ecdfaedad586038792f0a4db5`; firmware source was not changed.
- USB `version` repeatedly returns 51. The authenticated **v50 manifest only**
  was rejected by Secure with `confirmed version = 0x00000033`. The current
  Secure source emits this line only after CONFIRMED-state and signature checks,
  and returns before creating a flash session. This establishes confirmed 51;
  it does not disclose the active slot, alternate-slot contents or fallback health.
  None of those is inferred from version parity.
- SDK 2.0.106.0, AT 1.0.0.0, NCP build Mar 20 2026 09:32:19, MAC FW 1.6.44.0,
  BLE controller 1.6.128.0, BLE stack 1.10.83.0. SDK matches the packaged T01 /
  2.0.106 contract. The exact flashed NCP hash/profile and v51 host middleware
  provenance are not established merely by this version string. Packaged host
  driver version is 1.3.0; it is not labelled the measured v51 build version.
- HIL interpreter found without installing packages:
  `N6/project/training/.venv/Scripts/python.exe`, Python 3.11.9,
  Bleak 3.0.2, pyserial 3.5, numpy 2.1.3. USB-only runner uses Python 3.14.4.

## Bounded measurements

| Run | Workload and interval (UTC) | Result and limits |
|---|---|---|
| USB resume | 20:53:59-20:56:01, 120 s measurement, 58 USB pings | PASS USB continuity; p50/p95/p99/max 60.224/65.094/65.949/65.949 ms |
| Control baseline | 20:58:22-21:00:37, 120 s measurement, 120 BLE pings at 1 Hz plus 52 USB pings | PASS scoped controls: BLE p50/p95/p99/max 93/156/203/203 ms, below existing 1500 ms maximum; no missing/duplicate outcomes |
| Secure confirmation | 21:01:29-21:01:30; two 128-byte XMODEM packets containing the signed v50 manifest | PASS expected version rejection: 256 manifest bytes, zero image bytes, no EOT and no reset; returns to CLI |
| Settled state | 21:04:43-21:05:15, 30 s measurement, 15 USB pings | PASS USB continuity; p50/p95/p99/max 55.934/64.518/64.518/64.518 ms; BLE disconnected, advertising on |

BLE connected once, `pair=False`, Windows paired state false, MTU 247. Only CLI
notifications were enabled. Host event-loop maximum lag was 44 ms. USB latency in
the simultaneous BLE run was 312/328/328/328 ms because that existing UsbCli helper
includes a settle interval; it is not directly comparable with the polling runner.
Logs were buffered during measurement. No bond/cache removal or forced disconnect
was used. The immediate post-disconnect status still said connected; the separate
settled read proves disconnected/advertising on, generation 2, notifications off,
CLI queues empty, and pool free 17296 bytes / 32 fragments. Disconnect latency was
not measured, so this does not prove a specific reconciliation deadline.

Existing Wi-Fi/Cloud intent stayed enabled/paired, settings generation 2, image
destination NONE, dataset stream off. Cloud was polling an existing workspace,
with HTTP 204/409 observations and no image or CLI export; this was **not** a
successful Cloud image workload or V02/V03 acceptance. There were no settings,
credentials, Cloud infrastructure, image-route, power-save or NCP changes.

## Faults and practical limits

The first two measured intervals preserved SPI fault count **1** and NCP recovery
attempts **0**, with zero radio allocation failures and NPU errors. ToF/NPU counts
advanced and USB remained available. The SPI fault predated these intervals.

The settled read subsequently showed SPI fault count **3**: two additional faults
occurred between the control snapshot (uptime 745892 ms) and the settled snapshot.
Last fault: uptime 813425 ms, source 1, phase 2, length 332, HAL error 0x00000004,
SPI SR 0x00be0040, TX/RX DMA errors 0. Radio/pump historical max gap rose from 27
to 88 ms. Cloud request errors rose from 1 to 3, with 2 observed immediately after
the manifest-rejection probe. The exact timing of the first new SPI event and its
causal relationship to the probe/Cloud traffic are **UNRESOLVED**; there was no
continuous UART capture over the entire intervening interval. Do not call this a
new firmware regression, blame the cable, or declare the SPI fault fixed.

Within the final 30-second measurement SPI count stayed 3, NCP attempts stayed 0,
allocations failed stayed 0, and ToF/NPU kept advancing. The runner's PASS is for
its USB continuity assertions, **not** fault-free system acceptance. This baseline
contains an open SPI fault observation. No power/cable/jumper action is indicated
by the currently available evidence.

The manifest probe briefly entered the existing update mode, which quiesces and
restores services. It sent no firmware payload, consumed no new version and did
not reboot. Application frame numbering restarted after resuming acquisition;
continuous MCU uptime and cumulative processed counts exclude treating that
frame-number restart as evidence of an MCU reboot.

## Artifact blocker and next step

Local N6 package filenames and parsed manifest versions were searched; retained
packages end at v50. No v51 package/build directory was found in the N6 tree,
Downloads root or current Codex-date artifacts. Two relevant local task histories
also contained B50/plan creation, not v51 provenance. This is the scope of the
search, not a claim that v51 does not exist elsewhere. The user was asked for the
v51 `.n6fw` and build-artifact location. No answer is available at this checkpoint.

Required next action: identify the running v51 source/build/ELF/BIN/package and
its slot/recovery record, verify hashes and signature offline, then finish P0's
BLE-only/Cloud/image profiles and freeze the numerical workload/recovery worksheet.
Only then advance implementation dependencies and choose a signed USB candidate.
Do not rebuild a guessed v51, reinstall v50, jump versions, bypass boot checks,
or use SWD/UART programming to resolve this provenance gap.

This is a missing-information blocker, not an approval denial. No firmware
installation is pending or of uncertain outcome. All four runs completed; all
owned handles and shared leases were released. No build/sign/install, firmware
source edit, commit, push, deployment, security/ACL change, power or jumper action
occurred. No Generate Code is required for this documentation checkpoint.

## Reproduction and evidence

Each run directory contains result.json (commands, responses, timestamps, counters
and cleanup results). The confirmation run additionally contains uart.log. Copies
of the three exact harnesses are adjacent. They use the repository's shared-lease
protocol and ordinary Git reads; they do not add safe.directory or run a loader.

Commands executed from the task workspace:

```powershell
& 'C:\Python314\python.exe' -B -u .\st67_usb_preflight.py --seconds 120 --output .\evidence\st67-p0-usb-resume-20261028
& 'C:\Users\netan\Dropbox\DevelopPersonal\N6\project\training\.venv\Scripts\python.exe' -B -u .\st67_p0_control_baseline.py --seconds 120 --output .\evidence\st67-p0-control-20261028
& 'C:\Python314\python.exe' -B -u .\st67_confirm_existing.py .\evidence\st67-p0-confirm51-20261028
& 'C:\Python314\python.exe' -B -u .\st67_usb_preflight.py --seconds 30 --output .\evidence\st67-p0-settled-20261028
```

Conclusions after this group:

1. The repaired CN8 connection supports bounded USB work; its prior absence is
   resolved, but these short tests do not establish multi-hour cable stability.
2. Short BLE control latency meets the existing gate under background Cloud
   polling. Image fairness, receive gaps, forced recovery and endurance remain
   NOT_RUN; no V01-V12 checkbox is earned by this control-only measurement.
3. The discovered confirmed v51 and two new SPI faults must remain explicit.
   Exact artifact identity is needed before attributing the symptoms to source
   or choosing and preserving an update/recovery baseline.
