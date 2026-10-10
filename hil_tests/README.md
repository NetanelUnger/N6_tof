# N6 Hardware-in-the-Loop tests

This directory contains host-side Python tools that exercise the real N6
hardware and its external interfaces.  The tools must report observations; they
must not silently program firmware, change NCP provisioning, or run destructive
commands. Generated reports are written under `results/` and are not committed.

## Files

- `test_cloud_send_slices.py` executes the actual bounded socket-send loop:
  exact byte order/partial sends, empty/short bodies, failed send and invalid
  driver acceptance (five cases). Its RX headroom model is not an allocator/RF
  test; live reception evidence is in the CLI service document.
- `test_cloud_async_completion.py` executes production post-dispatch branches:
  ordinary end-of-line cannot complete pending Wi-Fi work; bounded completion
  retry retains ownership; XMODEM terminal completion remains valid (three cases).

- `test_cli_reply_ownership.py`, `test_cli_cloud_reply.py`,
  `test_cli_reply_failure.py` and `test_radio_service_status.py` execute actual
  bounded reply/status functions:29 native cases +two audits. Existing TX slot
  reservation, RX remainder, generation cancellation, Cloud lease/ACK/hold,
  explicit size/write/format/JSON failure, timing/fence immutability and raw
  XMODEM isolation. Focused target reports and limits:
  [CLI service/backpressure](../docs/cli-service-backpressure.md).

- `test_radio_wait_diagnostics.py` executes actual DNS command/drain paths with
  captured UART reports: START/pending/END ordering, single retirement, elapsed
  milliseconds, expiry/partial-write fences, pre-write rejection and tick wrap.
  Reproduces RX preemption before PENDING queue admission: the retained message
  describes a timeout snapshot even after END. Expiry explicitly reports fenced
  outcome regardless of terminal error code (10 actual-C cases plus source audit).
  Checks logging occurs outside interrupt exclusion and brackets Wi-Fi calls.
  `test_notify_transaction.py` also checks no duplicate drain END when parser
  retirement is busy. Hardware wait timing and fault injection remain separate.

- `test_notify_transaction.py`, `test_notify_route_owner.py`,
  `test_cloud_socket_recovery.py` and `test_cloud_request_budget.py` compile and
  execute the production C state/ownership paths with mocked RTOS/NCP replies.
  Cover late/missing terminals, cancellation, task/parser ownership, MTU/route
  changes, socket-close retry/proof, receive-size reuse, total-budget admission
  and warm network epochs. Run with `training/.venv/Scripts/python.exe`.
  See `docs/radio-transaction-cloud-recovery.md`; hardware gates remain separate.

- `test_dns_reply_lifetime.py` executes production DNS callbacks and Wi-Fi
  refresh paths. Late DNS replies cannot write to retired caller storage;
  refresh defers during owned terminal drain and retries on active worker wakes.
  `test_raw_send_response.py`, `test_wifi_assoc_admission.py` and the request
  budget checks distinguish pre-write Cloud epoch cancellation, guaranteed
  zero-byte BUSY, partial command writes and genuinely missing raw replies.

- `test_ble_control_worker.py` executes actual C mailbox/completion/GATT setup
  with mocked modem/RTOS boundaries. Covers by-value ownership, generation and
  advertising-revision races, BUSY deferral, retry policy and timing wrap, plus
  source audit for blocking BLE controls in Radio. Run with
  `training/.venv/Scripts/python.exe hil_tests/test_ble_control_worker.py`.
  Actual radio latency, missing responses and CRC routes still require HIL.

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

## Native radio ownership checks

```powershell
.\training\.venv\Scripts\python.exe .\hil_tests\test_wifi_scan_lifetime.py
.\training\.venv\Scripts\python.exe .\hil_tests\test_wifi_scan_admission.py
.\training\.venv\Scripts\python.exe .\hil_tests\test_raw_send_response.py
.\training\.venv\Scripts\python.exe .\hil_tests\test_wifi_assoc_admission.py
```

These compile and execute the actual C functions with mocked RTOS/bus boundaries
using MSVC or an available C compiler. Seven scan-lifetime, nine admission and
twenty raw-send checks verify borrowed storage release, allocation after AT
admission, bounded failure cleanup and the observed BLE OK/prompt/Recv/SEND OK
sequence. Raw checks cover fast ERROR, earlier payload OK, SEND FAIL, bad length
and genuine missing-response fencing. Eleven association checks cover the
original settling interval at admission, unchanged total deadlines, tick wrap,
nonblocking BUSY and SPI scalar capture without formatting on its 768-byte stack.
They do not prove hardware DMA, latency,
worst-case stack bounds or long-run stability.

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
