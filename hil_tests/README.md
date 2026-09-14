# N6 Hardware-in-the-Loop tests

This directory contains host-side Python tools that exercise the real N6
hardware and its external interfaces.  The tools must report observations; they
must not silently program firmware, change NCP provisioning, or run destructive
commands. Generated reports are written under `results/` and are not committed.

## Files

- `ble_inspector.py` is an interactive, non-destructive BLE scanner and GATT
  inspector. It scans all nearby advertisers, keeps the discovered `BLEDevice`
  objects, connects to a selected scan result, and reports every service,
  characteristic, property, descriptor, handle, and negotiated MTU. It labels
  the six known N6 maintenance UUIDs and produces a PASS/NOT MATCHED verdict
  for the expected UUID/property contract. It does not read, write, subscribe,
  expose the CLI, or start XMODEM.
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

At the `ble>` prompt:

```text
scan 8
connect 1
status
services
disconnect
quit
```

Choose the number actually marked `[N6]`; do not assume that it is device 1.
An exact address from the latest scan can be used instead. Connecting from the
stored scan object avoids a second implicit discovery operation.

Expected N6 device name: `N6-MAINT-xxxx`. Expected custom GATT layout:

| Role | UUID | Required properties |
|---|---|---|
| CLI service | `7a1e0001-b5a3-f393-e0a9-e50e24dcca9e` | Primary service |
| CLI RX | `7a1e0002-b5a3-f393-e0a9-e50e24dcca9e` | Write, Write Without Response |
| CLI TX | `7a1e0003-b5a3-f393-e0a9-e50e24dcca9e` | Notify |
| DEBUG service | `7a1e0101-b5a3-f393-e0a9-e50e24dcca9e` | Primary service |
| DEBUG RX | `7a1e0102-b5a3-f393-e0a9-e50e24dcca9e` | Write, Write Without Response |
| DEBUG TX | `7a1e0103-b5a3-f393-e0a9-e50e24dcca9e` | Notify |

The latest machine-readable observation is saved to
`hil_tests/results/ble_last.json`. Run `services` last when the complete GATT
tree is the evidence you want to preserve. Atomic report replacement retries
transient Dropbox sharing locks with bounded backoff.

## Hardware-free verification

```powershell
python hil_tests\self_test.py
python -m compileall -q hil_tests
```

The self-test does not prove that the PC adapter can scan or that the ST67 can
advertise. Those are physical HIL results and require the powered board.
