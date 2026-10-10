# Radio stability investigation â€” 2026-10-08

## Running image and scope

The physical board ran the confirmed Flash v9, with Wi-Fi associated and the
existing isolated Cloud workspace paired. No reset, Flash write or NCP
reprovisioning occurred during the probes. The retained `running-v9.elf`
corresponds to the raw application bytes in the installed v9 package: SHA256
`1b06b2b888143ce67b5587263761af254f33fec61a3db7d0ddfa02fb353ee1d8`.

COM8 was discovered by VID/PID; COM6 captured ST-LINK diagnostics. Those names
are observations, not fixed port assignments. Local evidence is retained under
`Tools/.n6-debug/radio-stability-20261008/` (ignored).

## Physical observations

| Probe | Observation | Acceptance limit |
| --- | --- | --- |
| BLE CLI, 30 seconds, Wi-Fi/Cloud active | 147/147 PONG replies; p95 151.5 ms; maximum 282 ms; no reconnect | Targeted latency PASS; not endurance |
| Exclusive route, Cloud â†’ BLE â†’ USB â†’ BLE | 20 + 20 complete BLE images and 25 distinct USB N6DF records, all CRCs valid; Cloud accepted-image counter stopped during BLE/USB ownership; BLE image fragments stopped during USB ownership | Targeted route PASS on Flash v9; no new browser rendering assertion |
| Combined BLE images/CLI, USB pings, Cloud polling; one Wi-Fi scan; 300 seconds | 1480/1480 BLE replies, p95 156 ms, maximum 3391 ms; 296 complete CRC-valid images; no reconnect; Wi-Fi scan returned nine networks; USB commands continued | Collector's p95/no-loss test PASS; multi-second response pause remains unresolved |
| Repeat combined probe, 90 seconds | 435/435 BLE replies, p95 145.5 ms, maximum 3140 ms; 88 complete CRC-valid images; no reconnect | Reproduces the pause; not a global stability PASS |

The first combined report was preserved as `combined-5min.json` and
`combined-5min-ble.json`; the repeat uses `combined.json` and `combined-ble.json`.
`image-route.json` contains the complete route/CRC observations. The combined
probe's `idle` label comes from the reused latency collector: its actual
workload included BLE images, Cloud polling and a scan. USB `wall_ms` includes
the host reader's prompt-settling time, so it is not an exact wire RTT.

The slow BLE replies clustered around the Wi-Fi scan. The device generated
their PONG ticks before the host received them; USB kept replying. CLI/image
contention counters recorded BUSY intervals of 326/328 ThreadX ticks
(approximately 3.26/3.28 seconds). This supports a shared AT admission bottleneck,
rather than a complete Radio Manager or sensor stop. The Radio/BLE lifetime
maximum loop gaps remained 1131/1132 ms, already present in the preflight; they
cannot be attributed to this probe or treated as its interval maximum.

Source inspection shows `W61_WiFi_Scan` sends `AT+CWLAP` through
`W61_AT_Common_SetExecute`/`modem_cmd_send_ext`, which holds `sem_tx_lock` while
awaiting the terminal response. BLE notification admission deliberately returns
BUSY before announcing any raw payload when that lock is occupied. Measuring
the scan's actual ownership time is the next hardware step. Do not release the
lock prematurely: unlabelled terminal responses could then satisfy another AT
command and corrupt protocol ownership.

There was no observed SPI RX HAL failure, raw-protocol fence, ToF I3C failure,
acquisition stop or spontaneous reset during these probes. The repeat's cleanup
recorded one ToF notification timeout after the BLE session closed; Cloud/USB
remained live and no raw fence was logged. This cleanup event is preserved, not
erased or counted as proof that every notification branch is healthy.

An initial HTTP 409/backoff resolved without a firmware change and accepted
Cloud images subsequently advanced. The server has several 409 paths, including
`workspace_inactive`; the status alone does not establish which was returned.
Cloud disable/enable cleanup also raised cancellation/transport counters, which
remain in the captured status. The subsequent complete UART review revealed
the separate concrete radio failure below; those counters must not be dismissed
as harmless cleanup.

### Post-probe Cloud transition reproduced RX allocation failure

After requesting Cloud disable/enable to restore image ownership, the captured
sequence was:

1. Two `W6X_FS_ReadFile: 3` timeouts.
2. Three `spi_iface.c:662: No mem for rxbuf` failures, then
   `spi transaction retries exhausted; tx buffer retained`.
3. `raw TX response missing; AT traffic fenced until module restart
   (phase=4 bytes=1520/1520 ticks=600)` at HAL tick 2984380.
4. DNS, BLE queries and station queries subsequently failed, while ToF
   acquisition continued. The fence explains the later loss of AT operations.

This is a reproduced **radio byte-pool allocation failure**, not a stack
overflow. `spi_xfer_one` allocates a full-MTU RX packet before every transaction,
including a TX-only one. Its aligned payload/header plus descriptor requests
1560 bytes through `pvPortMalloc`, which uses `tx_byte_allocate(TX_NO_WAIT)` on
the fixed radio pool. A full-MTU TX packet needs another 1560-byte allocation;
the prior observed 2484 free bytes cannot accommodate both simultaneously.
That is a concrete budget conflict, but the exact failure-time free count,
fragmentation and outstanding packet owners were not captured in v9. Do not
claim a leak or a specific TX owner solely from those observations.

The exhausted SPI activation retains its TX packet and returns to the event
wait. Consequently the NCP's raw terminal response may not be serviced before
its deadline. The protective AT fence is necessary; clearing it without
reestablishing protocol ownership would send AT text into an uncertain raw
transaction. The sequence does not establish the root cause of an earlier
SPI RX HAL overrun or an earlier ToF I3C fault.

## Observed stack usage

CubeProgrammer HOTPLUG reads inspected the ThreadX registry and initial 0xEF
stack-fill prefix without halting/resetting the MCU. One four-byte registry
pointer read occurred during the five-minute probe; full stack inspection
occurred afterward. Raw stack words and credentials were not saved; only names,
addresses, sizes and prefix counts were retained. These are SWD-observed fill
counts, not cache-coherent proof of worst-case bounds or exception-path safety.

| Thread | Capacity | Observed used | Untouched prefix |
| --- | ---: | ---: | ---: |
| Radio Manager | 8192 | 1596 | 6596 |
| Wi-Fi control | 6144 | 1116 | 5028 |
| Cloud Relay | 8192 | 3600 | 4592 |
| SPI transfer worker | 768 | 596 | 172 |
| Modem parser | 2048 | 732 | 1316 |

The radio byte pool had 2484 bytes available after the scan. No allocation
failure was observed during those earlier probe snapshots. These measurements do not justify enlarging stacks,
queues or the pool as a fix for the measured AT wait. The post-probe allocation
failure instead requires explicit packet-budget/ownership analysis. SPI error-path headroom
still needs assessment; the small remaining prefix is not an overflow proof.

## Prepared diagnostic candidate

- `wifi_ble_app.c` excludes only `W6X_Ble_ServerNotify` with `W6X_STATUS_BUSY`
  from the generic driver-error counter/log. Existing per-stream BUSY counters,
  retained fragments and retry behavior remain active. TIMEOUT/ERROR and BUSY
  from other control functions remain visible.
- `modem_cmd_handler.c` adds one asynchronous scan completion breadcrumb with
  separate TX-lock wait ticks, lock-held ticks and result. It records the fixed
  scan opcode only, never AT arguments, SSIDs, passwords or tokens.
- `freertos_compat.c/.h` retain 24 bytes of scalar allocation-failure metadata:
  count, requested size, available pool bytes, fragment count, ThreadX result
  and tick. `radio status` prints the snapshot from the CLI. No formatting,
  diagnostic queue operation or retry was added to the allocating SPI worker.
  The observed compiled allocator frame is 48 bytes (formerly 16); stack
  capacities were not changed and physical error-path headroom is still open.
- Non-Secure compilation/linking and explicit package-only v10 signing passed;
  the final `FlashImages/N6-Firmware-v10.n6fw` is 462912 bytes. This package is **not
  installed**. The tracked version remains 9 and Flash v9 is unchanged.
- No capacity, scheduler, installer, AT response-ownership or IOC change was
  made. CubeMX Generate Code is not required for these C-only edits.
- The compiled `modem_cmd_send_ext` frame is 56 bytes. Existing linker RWX
  warning remains; compilation produced no new C error.

Diagnostic RAM validation was performed after the user confirmed DEV boot.
The loader rebuilds RAM with tracked version 9; the version number alone does
not identify the candidate. Exact ELFs and boot logs are retained locally.

## Failure-time RAM evidence and correction

The first diagnostic RAM run initialized USB/radio/ToF, associated Wi-Fi and
paired a fresh isolated SignalR workspace. The host received 553 actual Cloud
frames before the failure. A Wi-Fi scan completed with 26 held ticks. Shortly
afterward, three allocations failed and the raw-response fence engaged:

| Failure scalar | Observed value |
| --- | ---: |
| Requested allocation | 1560 bytes |
| Available pool bytes | 916 |
| Pool fragments | 36 |
| ThreadX status | 16 / `TX_NO_MEMORY` |
| Last failure ThreadX tick | 55877 |
| Retained engine TX length/capacity | 1528 / 1528 bytes |
| SPI TX/RX queue occupancy | zero (only control RX queue bound) |
| Scan entries | seven, driver AP pointer still present |
| Scan list allocation | 20 Ã— sizeof(AP=46) = 920 bytes, plus pool metadata |
| Total radio pool | unchanged, 65536 bytes |

Non-halting HOTPLUG reads used `diagnostic-ram-v9.elf` offsets. Only scalar
lengths, ownership, queue/pool metadata were saved in `ram-failure-owners.json`;
no packet data, credentials or stack words were retained. The 928-byte drop
from 3412 to 2484 free bytes matched the scan allocation plus allocator metadata.
With the full TX allocated, only 916 remained for the mandatory full RX. This
is an actual insufficient-total-space failure, without needing fragmentation
or a growing leak to explain it. The capture does not exclude other failures.

A first scratch-release candidate failed on the first image-loaded scan:
`lifetime-only-overlap-failure.json`. Scan allocated its list **before** waiting
for the AT owner, stealing RX space from an admitted Cloud raw transfer. The
scan breadcrumb recorded 599 waiting ticks and zero held ticks; the raw sender
timed out first. Therefore callback cleanup alone is insufficient.

The revised `w61_at_wifi.c` candidate obtains the existing AT mutex before
allocating scratch, with the existing six-second Wi-Fi operation budget shared
by admission, command response and SCAN_DONE. It prevents a new large raw sender
until the callback has copied/printed results and returned the list to the same
pool. Duplicate completion with no list does not republish stale data. On an
ambiguous failure, cleanup takes the parser mutex within the remaining budget;
the AT fence remains set. If the parser is still active at the deadline, its
buffer is retained rather than freed under it. No pool, queue, stack or SPI MTU
increased; no SPI packet is dropped to make room. Callback pointers are now
explicitly borrowed until callback return in the W61/W6X headers. Current
application/shell consumers copy or print synchronously. `w6x_wifi.c` sets fresh
status before dispatch so a callback cannot inherit the previous scan's error.

`hil_tests/test_wifi_scan_lifetime.py` and `test_wifi_scan_admission.py` execute
the actual C event/admission functions with mocked hardware/RTOS boundaries.
Seven lifetime and nine admission tests pass, including raw ownership,
late SCAN_DONE, failed admission/allocation, bounded completion and parser-busy
cleanup. The compiled scan frame is 304 bytes, on the existing 6144-byte Wi-Fi
worker stack; scan event frame is 48 bytes. These tests do not prove target DMA
or worst-case stack safety. Revised NS build/signing produced package-only v10,
463296 bytes. The package has not been installed; tracked/Flash version is 9.

The next warm RAM restart failed **initial** ToF I3C dynamic address assignment,
before any valid frame, and a two-second scan candidate timed out. Ten requests
and three Cloud off/on transitions kept allocation count zero, but the receiver
got zero frames and later scan requests failed; `fixed-scan-stress.json` is **not
an acceptance PASS**. Its allocation-only result is retained separately and
the top-level acceptance boolean has been corrected to false. The
six-second revised candidate is built/signed, pending the requested full power
cycle and renewed image-loaded scan/route probe. Do not call radio stability or
image recovery fixed until that gate passes. This separate warm-init problem
is not evidence of runtime ToF recovery failure and was not patched here.

## Full-cycle and BLE wire-protocol validation

After the requested full power cycle, the six-second scan candidate booted with
healthy ToF. Ten scans each produced matching accepted/completed request IDs and
9--10 copied networks. Cloud received 120 additional actual images across those
scan windows; allocations stayed zero and the radio pool returned to 3412 bytes
after every scan. `cold-postscan-owners.json` confirmed AP=NULL, Count=More=0.
Scan ownership lasted 343--345 ticks (about 3.43--3.45 seconds), not the short
completion interval measured by the earlier generic breadcrumb. Admission waited
0--7 ticks. Holding AT through scan completion is a deliberate safety boundary;
it does not resolve BLE latency during a scan.

`cold-scan-stress.json` retains its overall failure because its separate Cloud
disable check waited only two seconds. Do not promote that collector to PASS.
The corrected bounded-poll `cold-cloud-transitions.json` separately passed all
three off/on transitions and observed new real frames after each enable.

Combined BLE then reproduced another fence with zero allocations and zero
recorded SPI transport errors. The first run completed eight host images and
only 43/151 PONGs before the prompt fence. Preserving a fast ERROR across command
submission was proved by actual-C tests, but the first correction still failed
on hardware. Its assumption that notification mode has no initial OK was wrong.
Redacted trace established the actual sequence for this NCP:

```text
43141 ms  TX AT+BLEGATTSNTFY (arguments hidden)
43142 ms  RX OK
43142 ms  RX >
43143 ms  TX 244 payload bytes (contents hidden)
43143 ms  RX Recv (length acknowledgement)
43144 ms  RX SEND OK
43241 ms  old terminal interpretation timed out and fenced AT
```

The initial correction could exit on initial OK without sending payload, leaving
the NCP waiting for raw bytes; the next AT text would then be consumed as payload.
After distinguishing the initial acknowledgement, the target sent the payload
but still timed out because SEND OK had no registered handler. These failed
attempts are retained as `raw-response-combined-120s.json`,
`phase-owner-ble-only.json` and `terminal-trace-ble-only.json`.

The final raw sender initializes response ownership before command submission,
ignores initial BLE OK until payload starts, wakes the prompt waiter on ERROR,
and registers SEND OK/SEND FAIL for this BLE flow. The earlier prompt/payload-OK
variant remains supported. Recv validates length but does not end BLE ownership;
a mismatch survives SEND OK. The existing AT mutex remains held through payload
completion. Truly missing prompt/terminal, partial submission and an existing
fence remain failures. No reset/timeout extension or automatic fence clearing
was used. A phase boolean changes modem state layout; no queue, pool or stack
capacity changed. `debug_uart.c` recognizes only fixed SEND OK/SEND FAIL/Recv
labels; it still hides arguments and arbitrary payloads.

Sixteen actual-C raw-send checks pass in `test_raw_send_response.py`, including
the registered handler table and the measured sequence, early ERROR, both OK
variants, SEND FAIL, bad Recv length and real missing-response fencing. Together
with the sixteen scan checks, 32 checks pass. Target build/link and package-only
v10 signing passed: final package 463968 bytes. It is not installed; Flash and
tracked version remain 9. RAM identity is `wire-contract-ram-v9.elf`, not just
the printed version number.

The first target repeat, with redacted trace on and Wi-Fi unassociated, received
33 CRC-valid BLE images and 138/138 PONGs: p95 141 ms, maximum 2937 ms. The helper
also schedules a Wi-Fi scan after thirty seconds; its name `ble-only` does not
mean scan-free. Trace generated UART queue drops, so use the subsequent trace-off
run for performance conclusions, not absence of errors in dropped trace lines.

The trace-off two-minute run with associated Wi-Fi, paired Cloud polling, BLE
images/CLI, USB pings and a Wi-Fi scan received 101 complete CRC-valid BLE images
and 367/367 PONGs, with no reconnect. However, p95 was 391 ms against a 250 ms
limit and maximum 3594 ms. `wire-contract-combined-120s.json` therefore remains
**FAIL**. Allocation failures remained zero, ToF/I3C counters stayed healthy and
subsequent AT status queries succeeded; it is evidence of functional recovery,
not full latency/stability acceptance. The scan held AT for 345 ticks. The NCP
still rejects connection-parameter negotiation, and a pre-pair FS read timeout
was retained in the diagnostic log. Neither was suppressed as expected BUSY.

Three more scans on the final raw-response candidate completed with 10/10/9
networks while Cloud received 10/14/13 additional images. Exact-image HOTPLUG
`wire-final-owners.json` found AP=NULL, Count=More=0, pool 3412/65536 bytes free
with 36 fragments, and AT fence=false.

The first final-image route probe (`wire-route/image-route.json`) failed because
BLE callbacks still arrived beyond its 200 ms settle interval during USB. Its
collector did not retain USB IDs before that assertion, so late delivery versus
new double publication cannot be determined retrospectively. Do not discard it.
Added observational USB IDs, BLE callback IDs/timestamps and before/after counts
to `run_image_route_gate.py`; its acceptance conditions were **not weakened**.
Two subsequent gates passed with 10+10 and then 20+20 CRC-valid BLE images,
25 unique CRC-valid USB records each, and unchanged Cloud accepted-image counter
through BLE/USB ownership. In the first observed repeat, a single BLE callback
after requesting USB carried old frame 6558, before USB's first frame 6572;
the callback count was unchanged after the existing settle interval.
Evidence: `wire-route-observed/image-route.json` and
`wire-route-repeat/image-route.json`. This supports the route on those runs;
the initial intermittent gate failure remains an open observation.

A final Cloud off/on probe (`wire-cloud-transitions.json`) failed its 20-second
image-return bound on the first re-enable. FS read/write, station query and DNS
timeouts were recorded, followed by a BLE health-query timeout. Images later
resumed without RESET (receiver advanced to 994 frames, latest ID 11473).
`wire-toggle-failure.json` records healthy ToF, allocations=0 and eventual
successful radio queries; exact-image HOTPLUG still found pool=3412, AP=NULL and
AT fence=false. This is a different unresolved recovery/latency failure, not a
recurrence of the diagnosed allocation shortage or BLE missing-SEND-OK fence.
The Radio/BLE lifetime maximum rose to 2020 ms; Cloud worker maximum step rose
to 20234 ms. Three earlier Cloud transitions passed, but this final-image
transition remains FAIL and prevents overall acceptance.

Post-recovery fifteen-second idle BLE CLI verification passed 73/73 PONGs,
p95 178.4 ms, maximum 266 ms, no reconnect (`wire-final-idle.json`). Final USB
snapshot reports ToF ready, Wi-Fi IP ready, radio ready, allocation failures=0;
Cloud had accepted 948 images on this RAM boot. The host receiver closed after
1262 cumulative images across the diagnostic boots. CN8/COM6 and BLE were
released; the running RAM candidate and its paired diagnostic workspace remain.
`diagnostic.n6workspace.json` was corrected to the actual CloudRelay.tsx import
schema (`n6-workspace-v1`, devices with id/name); token contents were not printed.
No persistent NOR installation or IOC generation occurred.

## Current open-task source audit, 2026-10-08

The task-plan summary is now reconciled with the physical results rather than
still labeling startup, network stack observations or all image routes pending.
M5.3 remains the sole active task; its next remediation item is shared-AT control
blocking. M5.4 isolation is implemented but its latency acceptance failed.

Confirmed source path: WIFI_BLE_App_Run -> ble_process_pending_events ->
ble_probe_shadow -> W6X_Ble_GetInitMode / W6X_Ble_GetConn -> W61 query ->
W61_AT_Common_Query_Parse. Both queries use W61_BLE_TIMEOUT=2000 ms. Query_Parse
waits on the shared AT mutex, then synchronously waits for a reply within the
remaining budget. The probe skips a Wi-Fi worker operation but does not skip
Cloud FS/DNS ownership. Radio MTU/connection-parameter, advertising and recovery
branches also contain synchronous W6X calls and require the same audit before
calling the loop non-blocking. A non-blocking mutex attempt alone does not make
an admitted query's response wait asynchronous. Defer work/results with owned
state and generation checks; BUSY must not mean a dead link.

Cloud source ownership is already separate: Radio only publishes network state,
and private cloud_process has one call site in CloudRelay_Run. Yet
cloud_begin_request sets its 4500 ms HTTP deadline after DNS, socket creation/
options/connect and sending; DNS's vendor budget is 20000 ms. Thus the current
receive deadline does not bound the entire request. Existing stepped backoff
must be retained rather than described as absent. This supports the architectural
blocking risk and is consistent with the recorded 2020/20234 ms gaps; it does
not prove admission versus response duration for that individual failure, or
explain the initiating FS/DNS errors. Scalar timing at those boundaries and
Cloud-failure HIL are the next verification steps. This audit changed documents
only; no new firmware build, RAM reload or Flash write was performed.

## Remaining gates

Missing-response/SPI fault recovery beyond the corrected cases, scan admission
latency, failed-association latency, five repeated clean boots,
SPI RX HAL fault reproduction/error-path stack bounds, matching Stage 11, ToF
recovery under BLE and the 30-minute/one-hour soak gates remain open. The
diagnostic classification fix is not a fix for scan latency or the previously
reported initiating SPI/I3C failures. No global M3/M4/M5 acceptance is claimed.

### 2026-10-08 async BLE control checkpoint (RAM v9 candidate)

- Radio only submits/consumes one fixed by-value BLE control job; existing
  Wi-Fi control worker executes MTU, connection parameters, disconnect,
  advertising, mode/link query and BLE-only recovery. No new thread or increased
  stack/queue/pool; the existing event object is shared. In BLE-only feature mode
  this same service owner is enabled. Wi-Fi result backpressure waits in one-tick
  slices so an unpublished Wi-Fi result cannot strand pending BLE control.
- Every job/result carries session generation; advertising also carries desired
  state revision. Cancel stale work before/between commands and discard stale
  completion. GATT recovery builds local name/address/stage, then Radio applies
  the result atomically; advertising follows current intent in a separate job.
  No W6X call runs under interrupt exclusion. BUSY preserves confirmed state and
  retry intent. `radio status` reports submitted/completed/deferred/stale counts,
  maximum queue/worker duration. Query boundary logs AT wait/held ticks separately.
- Ownership checks: 13 PASS (12 actual-C + source audit); enabled/Cloud-off/Radio-off/BLE-only/Wi-Fi-only
  compilation: 16 feature-mode checks PASS. Existing raw response 16 and scan
  admission 9 checks passed. Target build has 464464 bytes, heap 407752 bytes,
  radio pool remains 65536, source/Flash version remains 9.
- Connected Cloud contention, 120 seconds, six off/on requests: 532/532 BLE
  PONGs, p95 203 ms, maximum 2485 ms, zero reconnects; 94/94 USB PONGs; 21 actual
  CRC-valid BLE frames. Radio/BLE gaps 50/51 ms, worker call max 1780 ms, zero
  allocations. USB wall time includes host flush/settle and is not USB latency.
  Query admission waited 158 ticks (~1580 ms) without delaying Radio.
- Exclusive route PASS: 20 + 20 CRC-valid BLE frames, 25 distinct CRC-valid USB
  frames; Cloud counter stopped during BLE/USB ownership. Not browser rendering
  or endurance acceptance.
- Forced Wi-Fi disconnect -> Cloud reconnect -> Wi-Fi association, 120 seconds:
  FAIL, BLE 163/247 PONGs (84 missing), p95 157 ms among received replies,
  maximum 891 ms. USB 108/108, directly measured p95/max 16 ms; Radio/BLE gaps
  120/115 ms, 33 CRC-valid BLE frames before failure. At HAL 572010 ms the BLE
  sender missed its prompt (phase 2, bytes 0/244, 10 scheduler ticks), retained
  protective AT fence; subsequent commands failed. Wi-Fi connected/GOT_IP events
  arrived after the fence. HOTPLUG confirmed fenced=true, no scan scratch,
  pool free 3448 / 65536 bytes, 39 fragments; allocations stayed zero. Initiating
  missing prompt remains unproven; do not infer memory exhaustion or clear fence.
- After retaining the failed run, RAM reloaded the same tested binary; byte
  comparison against exact retained ELF output passed after comment-only edits.
  Wi-Fi reassociated and the isolated Cloud workspace received new frames;
  final snapshot: ToF ready, Cloud sent 298, Radio/BLE gap 22/22 ms, zero
  allocation failures. All host UART/USB/BLE handles were released afterwards.
  Sentinel-based observed stack use: control 1500/6144, Cloud 2844/8192 bytes,
  not a worst-case guarantee. Invalid first high-pointer reading was discarded;
  `control-stacks.json` now contains the corrected sentinel measurement.
- Full M5.3/M5.4 gate stays OPEN/FAILED. Next: diagnose raw prompt absence during
  association and define safe recovery without resetting unrelated peripherals;
  separately bound Cloud DNS/opening work (M5.5). Preserve scan contention gate.
  Ignored evidence: `control-contention*`, `control-route/image-route.json`,
  `control-reconnect*`, `control-uart.log`, exact `control-ram-v9.elf` under
  `Tools/.n6-debug/radio-stability-20261008/`.


## 2026-10-08 association settling and late-terminal checkpoint

The vendor W6X_WiFi_Station_cb executes from the shared Modem_Process parser.
Its CONNECTED branch slept 100 ms, exactly the BLE admitted execution budget.
The candidate moves that existing settling period to new AT-command admission.
RX stays runnable; ordinary AT waits consume their original budget, and BLE
returns BUSY before command bytes or response-handler changes. A raced quiet
interval is checked again at raw announcement and cannot create a false fence.
There is no added task, image buffer, queue capacity, stack capacity or pool
capacity. Handler settling adds scalar state only. The 100 ms BLE budget and
true unfinished-transaction fence remain unchanged.

Native admission checks: 11 PASS (nine actual-C timing/admission cases plus
callback/status and small-stack capture audits). Actual raw checks: 20 PASS,
including fast ERROR, initial OK, Recv/SEND OK, real missing responses and raced
quiet admission. Existing scan checks 16, BLE control checks 13 and feature-mode
compiles 16 passed. Final binary 464824 bytes, C heap 407392 bytes; SRAM4 radio
pool 65536. Flash/tracked version remains 9; this candidate is RAM only.

### Retained failed attempts

- The aged-board setup did not receive a BLE prompt; the first host script also
  scheduled Wi-Fi disconnect before a real BLE PONG. This is a setup failure,
  not a valid reassociation success. A revised collector starts transitions
  only after the first real BLE reply. The revised old-binary run then lost
  62 replies after a raw terminal timeout before reassociation.
- First association candidate, full trace, 70 s: FAIL, BLE 54/109 (55 missing),
  10 CRC-valid frames, USB 57/57, p95/max 16 ms, Radio max 120 ms. At HAL 124833
  the 15-byte payload was followed immediately by Recv. Deadline/fence at
  124931; SEND OK was read at 124969, about 136 ms after payload. This predates
  planned Wi-Fi disconnect, so the CONNECTED sleep cannot explain every failure.
  Its SPI-versus-parser arrival timing was not measured in this attempt.
  HOTPLUG confirmed fence=true, free 3448, fragments 39, no scan scratch;
  allocation failures zero. Do not call this memory exhaustion.
- Initial SPI-arrival instrumentation called the UART formatter on the SPI
  owner. Trace enable during Cloud traffic caused STKOF (CFSR_NS 0x00100000),
  PSP 0x242DACA8 in the exact-ELF SPI stack 0x242DAC90..0x242DAF90 (768 bytes).
  This was introduced by the diagnostic, not proof of the original fault's
  cause. It was removed. SPI now captures only timestamp/sequence atomically
  for exact fixed SEND OK/SEND FAIL records; parser formatting reports the age.
  The capture helper's compiler frame is 8 bytes. Its initial failure log/ELF
  are retained, and that run did not reach a valid BLE HIL setup.

### Focused passes, with practical limits

Corrected scalar diagnostic candidate, 70 s trace-on: BLE 325/325, p95 157 ms,
max 4234 ms, no reconnects, 68 CRC-valid frames. USB 57/57, p95/max 16 ms;
Radio gap max 31 ms. Terminal samples measured approximately 1 ms between
SPI receipt and parser consumption. This does not identify where an unobserved
late reply would spend its time.

Trace-off 150 s, three Wi-Fi disconnect/reconnect cycles with Cloud control:
BLE 694/694, p95 156 ms, max 2125 ms; 155 CRC-valid frames. USB 112/112,
p95/max 16 ms, Radio/BLE max gaps 60/58 ms. Maximum response delays remain
recorded even though the focused p95/continuity gates passed. Sentinel-only
observations during this run: SPI 308/768, parser 1288/2048, control 1740/6144,
Cloud 3436/8192 used bytes. These are not worst-case guarantees. Pool free
3448, fragments 39, scan scratch absent, fence=false at the observed checkpoint.

Cloud did not return normally after reassociation. With station GOT_IP and
BLE/USB still responsive, Cloud entered backoff with transport -14. Redacted
wire trace confirms DNS and CIPTCPOPT succeed, then CIPRECVBUF returns ERROR
immediately, before HTTP. Disable/enable and another Wi-Fi association did not
clear it. Worker max step reached 7158 ms; host allocation failures remained
zero. NCP resource state has not been proven. This is a retained warm-return
failure, not an accepted Cloud recovery. An incidental long idle period with
ToF/USB alive is not controlled BLE/endurance acceptance.

After preserving that failure, clean RAM reload and fresh diagnostic pairing
restored actual SignalR images. The exclusive-route repeat then FAILED after
12 CRC-valid BLE frames (IDs 1460..1578), before the required first 20 frames
and before USB/handover. At HAL 164817, raw phase 4 timed out: bytes 132/132,
10 ticks. No reassociation was in progress. HOTPLUG again confirmed fence=true,
free 3448/fragments 39, no scan scratch and zero host allocations. Earlier
route passes and the successful reconnect probes do not override this failure.

Full M5.3/M5.4 remains OPEN/FAILED. The immediate next item is safe ownership
and completion of late/missing raw terminal replies, including an independently
reproduced route failure. Keep the protective fence; do not enlarge the timeout
or clear it on an ordinary retry. Cloud socket/resource recovery and the total
opening/DNS request budget remain separate outstanding work.

Evidence is ignored under Tools/.n6-debug/radio-stability-20261008:
prompt-wire-* (setup/retry), assoc-wire-1* (late reply), assoc-spi-* (diagnostic
stack failure), assoc-scalar-wire-1*, assoc-scalar-off-1*, assoc-route/*,
assoc-route-failure-owners-stacks.json, assoc-cloud-* and prompt-wire-uart.log.
The exact final candidate is assoc-scalar-ram-v9.elf/.bin.

Final restoration after the route failure used a proper RAM reload of the same
byte-identical tested candidate, followed by Wi-Fi association and a fresh code
in the diagnostic workspace. Seven new actual SignalR frames were explicitly
verified; final snapshot reported Cloud polling/sent 224, ToF ready and Radio/
BLE maxima 21/21 ms, zero host allocations. One transient Cloud request error
remains in its lifetime count. Final HOTPLUG fence=false, pool available 3448,
fragments 38, no scan scratch. Host cumulative frame totals span multiple RAM
boots and are not a single-boot count. No Flash write or NCP firmware change.

SPI trace age uses the most recently observed exact terminal record, not an
added per-packet FIFO. Coalesced records are not sampled; several queued terminal
records can make correlation ambiguous. It must not be promoted to proof of an
individual late reply's arrival time without matching surrounding wire/queue
observations. The first measured late BLE reply predates this diagnostic.
