# N6 Hardware-in-the-Loop tests

This directory contains host-side Python tools that exercise the real N6
hardware and its external interfaces.  The tools must report observations; they
must not silently program firmware, change NCP provisioning, or run destructive
commands. Generated reports are written under `results/` and are not committed.

## Files

- `ble_inspector.py` is an interactive BLE scanner, GATT inspector, and bounded
  stream probe. It scans all nearby advertisers, keeps the discovered `BLEDevice`
  objects, connects to a selected scan result, and reports every service,
  characteristic, property, descriptor, handle, and negotiated MTU. It labels
  the seven known N6 maintenance UUIDs and produces a PASS/NOT MATCHED verdict
  for the expected UUID/property contract. Explicit commands can subscribe to
  CLI, DEBUG, or ToF TX and write UTF-8 or hex bytes to either RX
  characteristic. ToF fragments are reassembled and reported only as complete
  CRC-valid frames. It never starts XMODEM or programs firmware; DEBUG RX is
  expected to be accepted by ATT and discarded by the current firmware policy.
- `self_test.py` tests command parsing, scan-result selection, advertisement and
  GATT serialization, N6 UUID labelling, and atomic JSON report creation. It
  uses synthetic objects and therefore does not require Bluetooth hardware or
  the `bleak` package.
- `requirements.txt` pins the host BLE dependency used by
  `ble_inspector.py`.
- `results/.gitkeep` retains the report directory. `ble_last.json` is replaced
  after every successful or failed inspector command so it can be attached to
  a bug report or reviewed by Codex.

## Setup

From the repository root:

```powershell
python -m venv hil_tests\.venv
hil_tests\.venv\Scripts\python.exe -m pip install -r hil_tests\requirements.txt
```

Bluetooth must be enabled and the Windows account running the terminal must be
allowed to use it. The tool uses Bleak's public cross-platform API; this project
primarily validates it on Windows 11.

## BLE discovery flow

Start the firmware and wait until its UART log says that the BLE maintenance
GATT server is advertising. Then run:

```powershell
hil_tests\.venv\Scripts\python.exe hil_tests\ble_inspector.py
```

If Windows has a stale unpaired cache entry and the normal connect fails before
GATT discovery, retry with `--pair` to request the firmware's Just Works mode.
After changing the firmware GATT layout, add `--uncached-services` to force
Windows to read the current services and characteristics from the board.

At the `ble>` prompt:

```text
scan 8
connect 1
status
services
subscribe cli
subscribe debug
subscribe tof
write-text cli "transport probe"
write-hex debug 01020304
notifications
unsubscribe debug
unsubscribe tof
unsubscribe cli
disconnect
quit
```

For a repeated connection and ToF-notification stability test, scan once and
run the bounded soak command. Every cycle reconnects, validates the complete
N6 GATT contract, enables ToF notifications, requires a complete CRC-valid
frame, disables notifications, verifies one quiet second, and disconnects:

```text
scan 10
soak-tof n6 10 15
```

The final per-cycle timings and failure reason, if any, are saved atomically in
`results/ble_last.json`.

Choose the number actually marked `[N6]`; do not assume that it is device 1.
An exact address from the latest scan can be used instead. Connecting from the
stored scan object avoids a second implicit discovery operation.

Expected N6 device name: `N6-MAINT-xxxx`. Expected custom GATT layout:

| Role | UUID | Required properties |
|---|---|---|
| CLI service | `7a1e0001-b5a3-f393-e0a9-e50e24dcca9e` | Primary service |
| CLI RX | `7a1e0002-b5a3-f393-e0a9-e50e24dcca9e` | Write, Write Without Response |
| CLI TX | `7a1e0003-b5a3-f393-e0a9-e50e24dcca9e` | Notify |
| ToF image TX | `7a1e0004-b5a3-f393-e0a9-e50e24dcca9e` | Notify |
| DEBUG service | `7a1e0101-b5a3-f393-e0a9-e50e24dcca9e` | Primary service |
| DEBUG RX | `7a1e0102-b5a3-f393-e0a9-e50e24dcca9e` | Write, Write Without Response |
| DEBUG TX | `7a1e0103-b5a3-f393-e0a9-e50e24dcca9e` | Notify |

The latest machine-readable observation is saved to
`hil_tests/results/ble_last.json`. Run `services` last when the complete GATT
tree is the evidence you want to preserve. Atomic report replacement retries
transient Dropbox sharing locks with bounded backoff.

The text stream commands intentionally expose ATT fragments rather than
pretending that one notification equals one line. `notifications` preserves
CLI/DEBUG fragments as hexadecimal data. ToF is different: its 20-byte headers
are checked for frame identity, dimensions, channel, contiguous byte offset and
payload CRC32, and only complete frames are retained in the report. The item-10 firmware consumes CLI RX
through an independent BLE parser session and returns echo, replies and prompts
on CLI TX notifications. Subscribe to `cli`, then write a command terminated by
CR (for example `version\r` or `MAP DISPLAY ON\r`). DEBUG RX remains disabled
by policy and the DEBUG TX producer is not attached yet. Signed XMODEM is
available through BLE CLI in the web application; dataset streaming and remote
reboot remain USB-only.

## Hardware-free verification

```powershell
python hil_tests\self_test.py
python -m compileall -q hil_tests
```

The self-test does not prove that the PC adapter can scan or that the ST67 can
advertise. Those are physical HIL results and require the powered board.

## Exclusive image-route gate

With the repaired firmware already running, a free BLE link and CN8 port:

```powershell
.\training\.venv\Scripts\python.exe .\hil_tests\run_image_route_gate.py
```

The gate subscribes to CLI and ToF, receives complete CRC-valid BLE images,
requests USB N6DF records while leaving the BLE subscription enabled, and
requires BLE image fragments to stop during USB ownership. A BLE `MAP ON`
then reclaims the image destination and must deliver CRC-valid frames again.
It records route/status evidence and failures in `results/image-route-gate.json`,
stops subscriptions/dataset streaming, and disconnects BLE afterward. It never
loads RAM or writes Flash. Add `--cloud` with an already paired, actively
sending Cloud image stream to assert that its accepted-image counter stops
through both BLE phases and the USB phase. Verify actual browser rendering
and resumption with a Cloud `MAP ON` separately. On 2026-10-06 this connected
gate passed 10+10 BLE images and 25 USB records; the live Cloud page rendered
advancing images before and afterward. This is not long-run stability or
fault-injection proof.

## Automated Milestone 3/4 repeated-boot gate

`run_milestone4_gate.py` removes the manual five-boot loop. It reloads the
current Secure and Non-Secure images into RAM, checks radio/BLE/ToF through
CN8, runs the 45-second BLE Wi-Fi-contention probe, sends 24 concurrent USB
pings, records the postflight counters, and repeats until five consecutive
boots pass or seven total attempts have been used:

```powershell
.\training\.venv\Scripts\python.exe .\hil_tests\run_milestone4_gate.py
```

The board must already be in DEV boot (`BOOT0=1-2`, `BOOT1=2-3`). The runner
never writes external NOR. A missing first prompt remains a failed boot; a
later diagnostic reconnect is not promoted to PASS. The atomic aggregate is
`results/milestone4_gate.json`, with a separate raw BLE report per attempt.
After a missing PONG, the probe resumes with a new token after one second and
retains the missing reply as a failure. This distinguishes a brief lost GATT
write from a sustained stall. The runner stops as soon as the remaining
attempts cannot reach five consecutive passes; transient Dropbox locks on the
summary file are retried with a finite budget. ToF health is checked separately
at preflight and postflight, and a ToF failure also fails the full gate.
