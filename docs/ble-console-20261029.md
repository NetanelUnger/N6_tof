# N6 BLE Console — 2026-10-29

Entry: `training/BLE_CONSOLE.bat`. The default opens a Tk desktop window;
`--scan` and `--run --address ADDRESS --pings 20 --cycles 3` run unattended.
Uses the existing Python3.11/Bleak3 environment and existing CLI framing parser.
No new dependency installation or firmware build is needed; the board remains A57.

The shared engine serializes printable single-line commands, bounds
responses to128KiB, and invalidates a session after timeout, overflow or disconnect.
Late notifications from a previous connection cannot complete a new command.
Normal disconnect asks the owned N6 connection to disconnect while CLI Notify
is still subscribed, then closes the Windows client. Timeout cleanup does not
send another command. No Pair/unpair/cache/reset/settings/firmware operation is
performed by automatic diagnostic profiles. Manual commands are user-selected;
interactive credential entry and raw updater transfer are excluded. A shared
host lease prevents overlapping cooperating hardware tests.

## Sensor viewer and continuous connection test

The viewer uses the existing `TofFrameAssembler` and validates complete payloads
before displaying RAW float32, affine UINT16/UINT8 or JPEG plus exact validity
mask. It supports the existing v1/v2/v3 envelope; v3 carries same-frame NPU
metadata. Training-format5 is not a display image. The UI uses one latest-frame
slot rather than queueing stale images. Invalid pixels are dark and the dynamic
per-frame scale is labeled; old images receive a STALE badge.

Image subscription/start is explicit. An already active image route or demo
stream blocks the viewer rather than silently replacing another destination.
Stop restores the previous encoding. CLI commands remain available while images
arrive. `--soak SECONDS` runs images and pings together and optionally records
independent UART (`--uart COM6`) and USB (`--usb COM8`) health evidence.
The runner distinguishes remote/OS disconnect callbacks from deliberate host
cleanup, retains a passive evidence tail after failure, and does not replay
commands or reset the board. A missing final reply taints the command session;
the soak records its state before cleanup rather than inventing a disconnection.

Decoder tests cover invalid pixels, affine quantization, JPEG masks, header and
payload corruption, missing fragments, reconnect reset and image bounds. Thirty
production-C v3 wire fixtures (24 RAW/Q16/Q8 and6 JPEG) decode successfully.
Actual Tk widget tests include image start/display/stop and stale display state
using simulated GATT; live BLE evidence is recorded separately below.

## Initial command-only verification

- Host fault tests cover fragmented accepted/final replies, failed terminals,
  timeout, stale replies, disconnection, overflow, command serialization,
  unsupported commands, cancellation, latency gates, report preservation,
  disconnect coordination and ownership conflicts.
- Actual Tk widgets with simulated GATT: scan/select/connect/send/run/report/
  stop/disconnect/window close PASS. BLE work runs on a background asyncio loop;
  Tk updates run on its main thread. Mock reports use a temporary directory.
- Actual A57 hardware, three consecutive independent connections: each passed
  six diagnostic commands and20 PONG/final checks. Max ping times156/187/156ms,
  all below the unchanged1500ms gate. Successful reports:
  `training/reports/ble_console/20261029-230148-ce9aa474.json`,
  `20261029-230159-73a7698d.json`, `20261029-230209-19dbf2af.json`.
- Subsequent independent scan found N6-MAINT-B8FB again. All owned GATT/USB
  handles and shared leases were closed. No image subscription or Cloud sensor
  export was requested.

## Retained failures and limits

Sandbox runs discovered advertisements but failed WinRT GATT requester creation
with DeviceNotFound. The supported escalated execution path succeeded; no OS
security/permissions/cache/pairing settings were changed. Ordinary user launches
use Windows normally; this is not an instruction to run as administrator.

Early host-only disconnect and explicit stop-notify variants passed their first
20 pings but failed the second scan. USB evidence showed the previous link still
connected. A later disconnect-command prototype sent the request after disabling
Notify; USB showed one pending CLI RX item. The final order preserves Notify
until the device has processed disconnect. Three actual cycles validate the
final workflow, but do not prove the underlying WinRT link-retention cause.
Earlier failure JSON and USB diagnostic files remain under the report directory.
The owned stuck test links were explicitly disconnected through the existing USB
CLI during investigation; normal final app operation requires BLE only.

Independent Windows UI visual verification was unavailable: computer-use returned
an unusable screenshot and then AccessDenied; no workaround was attempted.
Actual Tk callback/layout workflow was tested programmatically with a fake peer,
and actual BLE was tested via the shared CLI engine. The initial three-cycle
regression above did not cover endurance or image throughput; the subsequent
image/connection measurements are recorded below.
Full diagnostic UART logging in A57 still has the separately documented bounded
queue drops; this tool does not repair firmware defects or change those queues.

## Sustained images plus commands, A57

Actual UINT8 sensor stream, 900.015 seconds: PASS, 2,189 complete images and
1,485 PONG/final replies. Maximum ping281ms, mean97.09ms; maximum complete-image
gap781ms; maximum asyncio scheduling lag91ms. CRC errors, assembly drops and
image callback errors were all0. No unexpected BLE disconnect occurred.
Evidence: `training/reports/ble_console/soak-20261029-232813-95e4a0/result.json`
and its timestamped `uart.jsonl` (9,798,586 raw UART bytes captured).

Independent USB snapshots before/after show NCP recovery attempts0 and SPI
fault count0 throughout. An existing ToF recovery/I3C error count1 remained
unchanged; it did not occur during this measurement. Firmware image busy drops
increased0→405 before transmission, so this is connection/decoder continuity
evidence, not lossless sensor acquisition or a throughput acceptance result.
The host received about2.43fps in this profile.

Full DEBUG output saturated the firmware UART queue: cumulative log drops rose
79,875→450,566, while UART transport/HAL/timeouts stayed0. Raw UART evidence is
therefore incomplete. Socket `+CIP:0,DISCONNECTED` messages in that log refer to
IP sockets; they are not evidence of BLE disconnection. No NCP/SPI/ToF recovery
or BLEDISCONN marker was found in this capture. The cause of earlier reported
BLE failures remains unproven because none reproduced during this run.

The current runner also writes incremental `commands.jsonl` and a decoded final
sensor PNG; those additions were made while the first soak was already running,
so that first directory contains its complete result JSON and UART evidence but
does not contain those two newer artifacts. The subsequent codec runs use them.

### Four codecs on one real connection

Each mode ran for30seconds with actual sensor images plus pings, then stopped
its stream and restored the original encoding before the next mode:

| Mode | Complete images | Pings | Maximum ping | CRC errors |
| --- | ---: | ---: | ---: | ---: |
| RAW | 21 | 50 | 187ms | 0 |
| UINT16 | 41 | 50 | 157ms | 0 |
| UINT8 | 70 | 50 | 156ms | 0 |
| JPEG | 80 | 49 | 204ms | 0 |

All connection/decoder profiles passed; no unexpected disconnect or cleanup
error occurred. These are observed rates, not throughput targets. The historical
reports expose cumulative assembly-drop values0/1/2/3, which include partial
frame resets at stream boundaries; they do not isolate within-window drops.
The runner now reports both cumulative and window-delta counts, with a regression
test proving earlier drops are excluded. Original evidence was not rewritten.

Summary: `training/reports/ble_console/20261029-234558-9206d5f5.json`.
Per-mode directories: `soak-20261029-234343-3c3da9`,
`soak-20261029-234416-d6c938`, `soak-20261029-234450-c959b7`, and
`soak-20261029-234524-b45b1f`, under the same report root. Each contains
result JSON, incremental command JSONL, UART JSONL and a final decoded PNG.
RAW and JPEG PNGs were inspected and show coherent sensor distance maps.
After intentional disconnect an independent scan rediscovered N6-MAINT-B8FB;
the hardware lease was released. No test client is left connected.

Host validation:16 session tests,7 decoder/fragment tests and2 soak evidence
tests pass, plus actual Tk widget workflow with a simulated BLE peer and30
production-C protocol fixtures. Physical BLE validation used the same engine
through CLI; independent visual verification of the Windows window remains
unavailable as documented above.

## DEMO MAP follow-up: USB session teardown stops the BLE stream

User-requested live A57 test used `DEMO MAP ON 1000 BLE`, followed on the same
BLE connection by `DEMO MAP ON 300 BLE`, with UINT8 image notifications and
concurrent pings. The BLE-only measurement passed:

- 1000ms:60seconds,60 images,99 pings, maximum594ms, CRC0, assembly drops0.
- 300ms:120seconds,221 images,198 pings, maximum203ms, CRC0, assembly drops0.
- All received demo frame metadata reported NPU state0 as required.
- At the first final300ms status snapshot the board reported scheduled402,
  accepted221, skipped181; all181 rejections were busy, with late slots0.
  This explains the reduced received rate (~1.84fps), not a BLE disconnect.
- Evidence: `training/reports/ble_console/demo-20261029-234944/summary.json`;
  per-phase results, PNGs and command JSONL are in its subdirectories.

The initial run failed with no images for10seconds despite successful pings
(`demo-20261029-234758`). Its USB status snapshot opened and closed COM8 after
starting the demo. A controlled reproduction (`demo-20261029-235318/summary.json`)
first received10 demo images in10seconds; BLE status then confirmed DEMO ON
(scheduled11). After the same USB snapshot/close and5seconds of observation,
only12 cumulative images existed, DEMO STATUS reported OFF (scheduled12), and
BLE status still reported connected. This reproduces image-stream shutdown,
not a radio-link disconnection.

Code path: USB console becoming unready calls `cli_session_reset(...,1)` in
`debug_cli.c`; that calls `TOF_App_SetDatasetStreamEnabled(0)` in `tof_app.c`,
which also releases the BLE destination when map_enabled is false. Then
`demo_map_process` in `wifi_ble_app.c` disables the demo because its requested
destination no longer matches. The USB cleanup therefore affects a different
transport's stream. This firmware defect is identified but not changed in this
test-only follow-up. USB snapshot open/close is not passive with respect to an
already-running BLE stream; avoid it during continuity measurements until fixed.
Earlier long-run USB snapshots preceded stream startup or followed measurement,
so their completed BLE measurement windows remain valid.

All test sessions ended with DEMO OFF, encoding restored, lease released and
advertising rediscovered. The earlier unexpected BLE link-disconnect cause
remains separate and unproven. No firmware build or installation was performed.

## USB stream isolation fix, B58, 2026-10-30

The previously identified USB teardown defect is now fixed and installed.
`cli_session_reset` calls the existing `TOF_App_StopUsbStreams` helper instead
of unconditionally clearing map/dataset state. The helper checks the requested
destination under interrupt exclusion, stops USB-owned streams, and leaves
BLE/Cloud state untouched. No CubeMX Generate Code is required.

`hil_tests/test_usb_stream_cleanup.py` compiles the actual cleanup block and
ToF state functions. It fails against the old code and passes against the fix,
covering16 combinations of destination/map/dataset state, stop-disabled behavior,
repeated cleanup, and interrupt restoration. `test_demo_map.py` also passes.
Cloud preservation is covered by these host C tests; no live Cloud image test
was performed for this change.

Signed package: `.local-dependencies/xip/v58-B-usb-stream-isolation/N6-XIP-B-v58.n6fw`,
514592bytes, SHA256 `5cd44c902d197021d0891575fc745a6fd2ce9b41927e4d7f092f624157c52dee`.
USB transfer/finalization completed, automatic reboot ran B58, and captured
Secure confirmation at17723ms closed the rollback window; A57 remains fallback.
The update runner subsequently timed out on `rps status`, so its original
`usb-update-usb-stream-isolation58/result.json` remains failed. It was not
rewritten or treated as a complete pass. A fresh read-only session verified
version58 and healthy ToF/NPU/radio state, recorded in
`.local-dependencies/xip/usb-isolation58-postflight.json`; no reflash/reset was
issued. The transient status timeout's cause is not established.

HIL100 passes:100 exact tensors,100 NPU results, maximum raw score difference1,
CRC0; `.local-dependencies/xip/hil-XIP-v58-usb-stream-isolation58-verify.json`.

Actual BLE regression: three USB open/query/close cycles each during demo1000ms,
demo300ms, and real sensor streaming. All nine cycles received new decoded
images after USB close, retained the BLE destination, and passed a PONG check.
Demo stayed ON; demo NPU metadata remained0 and real sensor NPU metadata3.
CRC0, no unexpected disconnect, one partial-frame assembly drop recorded over
the combined run (not a lossless-transition claim). Evidence:
`training/reports/ble_console/usb-isolation-20261030-072836/result.json` and UART
capture. Reusable test: `hil_tests/run_ble_usb_stream_regression.py --address
40:82:7B:03:B8:FB --version 58` with the training Python environment.

Final state: demo OFF, requested/active stream NONE, original RAW encoding
restored, ToF ready, advertising rediscovered and hardware lease released.
Full DEBUG UART queue loss and unrelated historical BLE disconnect causes
remain outside this scoped fix.

## Prepared mixed Cloud/BLE load, 2026-10-30

`hil_tests/run_mixed_ble_cloud.py` coordinates a three-minute profile with
`run_mixed_cloud_worker.mjs`:60seconds each of RAW/300ms, UINT8/100ms and
JPEG/100ms demo source timing, concurrent BLE PONGs, and serialized Cloud
`radio status`, `help`, and unique PONG commands through the existing paired
workspace. Large text replies load the shared radio while image traffic is
active. Only one image destination is requested (BLE); Cloud supplies concurrent
control traffic. Source timing is not a received-throughput guarantee.

The runner preserves command IDs/final replies, per-command timings, UART,
image CRC/assembly metrics and independent USB postflight. BLE retains the
1500ms ping gate; Cloud uses a45s terminal deadline, records all measured latency
and requires real completed load commands. Failures stop subsequent phases and
remain in unique reports. No pairing, firmware update or persistent settings
change is part of this test. Both new scripts passed syntax checks.

Initially, fresh USB snapshots showed an active workspace
(`HTTP last204`). Server `OpenWorkspace` replaces its sole BrowserConnectionId,
so the user was asked to close/disconnect the existing site session before the
test. The worker requires fresh inactive-workspace evidence (`last409`) and will
not replace the currently active browser by default. The user subsequently
authorized running after the replacement consequence was explained. An explicit
`--replace-existing-workspace` option now records that authorization and keeps
the same existing device allowlist and credentials.

### Executed mixed load on B58

Actual run `training/reports/ble_console/mixed-20261030-082352/result.json` PASS:

| BLE format / source interval | Image window | Complete images | BLE pings | Max BLE ping |
| --- | ---: | ---: | ---: | ---: |
| RAW /300ms | 60s | 35 | 99 | 203ms |
| UINT8 /100ms | 60s | 126 | 97 | 500ms |
| JPEG /100ms | 60s | 243 | 98 | 203ms |

Total404 CRC-validated images and294 PONGs, CRC0 and assembly-drop delta0 in
all three measured windows. Cloud concurrently completed81 load commands over
184.57seconds, plus2 startup probes; maximum Cloud reply3619ms. The load rotates
large `help` output, `radio status`, and unique PONGs. No unexpected BLE/Cloud
disconnect or timeout occurred. BLE maximum500ms remains below1500ms gate.
The cumulative maximum image gap across the session was2.516seconds; the runner
currently carries that maximum across phases, so it is not a per-phase maximum.

Final per-phase demo snapshots report busy rejections168/484/366, late slots0.
The source is saturated, especially RAW; source100ms timing is not10fps reception.
NCP recovery attempts and SPI fault counts remain0. UART queued-log drops rose
82320→171778; the raw UART capture is incomplete under full DEBUG. Existing CLI
TX retries/errors1/1 were already present in the prior startup-probe attempt
and remained1/1. Final cumulative BLE driver errors3 include the connection/
cleanup attempts; this result does not claim zero historical driver errors.

Earlier attempts are retained: `mixed-20261030-082214` stopped at the active
workspace guard without a Cloud takeover; `mixed-20261030-082256` received a
valid Cloud PONG but the new worker incorrectly required `n6>`. The worker now
uses server completion plus protocol final LF (PONG legitimately omits the
prompt), rejects failed/rejected terminals, and checks the PONG token. These
were test setup/parser failures, not evidence of firmware disconnection.

Both clients closed, the BLE advertisement was rediscovered and the hardware
lease released. No firmware, credentials, device allowlist or server deployment
was changed. The prior browser Cloud session was replaced as authorized; a new
site connection may be needed. This is a bounded three-minute combined-load
result, not an indefinite endurance guarantee.
