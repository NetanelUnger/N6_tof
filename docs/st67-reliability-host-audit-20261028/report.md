# ST67 reliability: checkpoint CP2

2026-10-28, Codex. This checkpoint is host-only; no serial/BLE handle, hardware
lease, firmware build/sign/install or reset was used. The latest live-board
evidence remains CP1 (confirmed 51, functioning CN8, open SPI faults).

## What is blocked, and what can proceed

The earlier statement that all P1 work had to wait was too broad. Section 5 P0
requires a reproducible baseline tied to exact artifacts; P1 and P2 have explicit
dependencies, and section 7 freezes numerical workload limits before firmware
implementation. These requirements prevent treating an unidentified running
image as a validated candidate or attributing its faults to the current source.
They do **not** prevent source audits, offline tests, test-harness repairs or
package/build preparation which does not select a delivery version or touch the
board. The plan also explicitly separates a completed code task from its open
hardware validation. The parent requested this independent work be continued.

Accordingly P1-01's source observability audit is complete for the exact local
revision below, as preparatory work. P1 is IN_PROGRESS for that audit only;
P0's live-artifact/profile/acceptance exit remains open. Firmware instrumentation,
behavior changes, timing acceptance and physical recovery acceptance are not
claimed. P2-P7 retain their dependency gates.

The plan does not literally demand that a file named v51.n6fw exist before **any**
software edit. The unresolved installation prerequisites are narrower: establish
what source/configuration the board is running, the active slot/execution mode,
and a verified recovery baseline before overwriting an inactive slot. An exact
equivalent immutable build/install record could resolve provenance without that
particular filename. The v51 number by itself supplies none of those hashes or
slot facts. Known A49/B50 host files do not prove either is currently the board's
fallback. CP1's authenticated old-manifest rejection exposed confirmed51 only.
The current CLI has no firmware-image/hash/slot readback command; using SWD or
replacing Secure just to obtain a dump is outside this USB-only campaign.

## Extended artifact search

The exact inventory, paths, timestamps, package versions and search exclusions
are in artifact-search.json and binary-version-search.json. No keys, secret
files, credentials or unrelated conversation bodies were inspected.

- Walked the N6 project tree (both Git worktrees, build/FlashImages, local xip,
  factory-builds, diagnostics, tmp/workspace outputs) and the specifically related
  `Web_N6_ST67W611M1_VL53L9CX` project. Excluded .git contents, key/secret directories,
  virtualenvs and node_modules. 64694 filenames inventoried; 143 recent project
  output/document text files searched. No filesystem read errors were reported.
- Read the first 256 bytes of **86 .n6fw packages**, independent of filename.
  Maximum manifest version: **50**. The only textual v51 hits were this campaign's
  own CP1 records and updated plan.
- Identified 77 recent build artifacts and examined 62 ELF/BIN/package files for
  the compiled `Firmware version:` string. Values found: 11, 48, 49, 50; no 51.
  CLI `version` is a compiled string (debug_cli.c:1666-1670), not merely a display
  of Secure metadata. The latest retained application artifacts are B50 from
  2026-10-27. File dates alone were not used to identify a firmware version.
- Git worktree inventory lists only `project` (main b9ad960) and
  `n6-xip-ota-usb` (feature HEAD5432d4a). Read feature Git refs/history/reflog;
  latest commits are 38d384f, 6948f70 and 5432d4a, with no later local ref or
  reflog install/build51 evidence. Did not retry the older checkout's ownership
  rejection, add safe.directory or change ACLs.
- Local Codex memories directory is empty. Searched assistant text (not tool
  outputs, hidden reasoning or authentication data) from **nine N6 sessions**
  dated October26-28, including auxiliary sessions absent from the sidebar.
  No prior assistant v51 mention or artifact path was found. The accessible
  archived N6 task summaries predate this XIP campaign. The recent boot-screen
  conversation records the B50 demo-map build, not a subsequent v51 installation.

This establishes absence within the searched scope, not absence on another
computer or in a different output directory. Minimal remaining question for the
user: **From which computer or build/output folder was version51 installed?**
A location or the task that installed it is enough to resume tracing; the user
does not need to compute hashes or diagnose the fault. The previously requested
artifact-location clarification is still pending. No approval was denied.

## P1-01: existing measurements and actual gaps

Revision: `5432d4ae2b10ef7ecdfaedad586038792f0a4db5`. source-audit.json hashes the
files below. This is a source audit of that revision, not a claim that all its
build switches or implementations match running51.

| Delay/resource layer | Existing evidence in source | Limitation / smallest missing measurement |
|---|---|---|
| BLE control admission and execution | wifi_ble_app.c:4257-4338 snapshots job generation/revision/submission tick; deferred/stale/completed counts and max_queue_ms/max_call_ms. debug_cli.c:2461 exposes these. | Maxima aggregate operations. They do not locate a specific host request or distinguish lock wait from NCP work. Reuse these counters; correlate an operation identifier/class and scalar phase times only where the baseline cannot explain a delay. |
| AT lock admission versus held time | w61_at_common.c:658-737 emits wait_ticks/held_ticks for BLEINIT?/BLECONN?; TakeTxLockBudget and modem budget already subtract time spent waiting. | Only these BLE queries get split timing; scan/connect/DNS/socket/notify lack a uniform, durable per-class owner/phase/outcome record. A zero-byte local BUSY must remain separate from NCP text busy p. |
| Long-operation lifecycle | RADIO-WAIT START/END for Wi-Fi connect/disconnect; DNS 20 s retained terminal ownership and timeout snapshots; BLE terminal drain capped at1000 ms. modem_cmd_handler.h retains dns flags/budget owner/generation; w61_at_api.h retains notify phase/owner/started/budget/result. | These are real existing lifecycles, not justification to introduce a second manager. A uniform generation/transaction identifier would resolve ambiguous cross-log correlation; do not use a log END as proof that a separately declared request timeout cancelled the NCP. |
| SPI receive versus parser delay | debug_uart.c:1268 records terminal SPI tick/sequence atomically; w61_at_common.c:1297 formats parser-side trace and parser_age_ms. spi_iface.c:851 publishes the scalar hook. | This is terminal-detection/last-seen evidence, not complete per-packet timing or an RF/NCP execution clock. Existing matching/fragmentation limits and lack of transaction identity can prevent unique attribution. Reuse the hook before adding a broader recorder. |
| SPI/DMA transport faults | SpiPortFault_t includes transfer/phase/length/registers/DMA state; ISR/SPI capture stores scalars, Radio task reports. Collapsed count retains overflow evidence. Transfer-start tick exists under RX-backpressure profile. | No continuous per-class SPI service-time distribution. CLI snapshot alone cannot correlate the two CP1 faults to one AT request; it omits much of the extended register record. Capture the existing deferred fault record first. |
| Queues, pools and stacks | resource_diag_impl.inc keeps bounded 8-pool/32-queue/24-stack usage tables with minimum free/peak/observation counts; wrappers retain allocation/enqueue failures. Deferred fixed96-byte reports attempt at most once/second; no sink in ISR capture. CLI exposes stream queue/high-water and instantaneous free bytes/fragments. | Observed stack-pointer usage is not a full stack watermark; total free bytes/fragments do not prove largest allocatable block. Capture existing resource reports across the defined workload before proposing capacity changes. |
| Host delivery | CP1 harness records monotonic request-to-final latency, direct BLE notification arrivals and an independent50 ms host-loop monitor; USB checks distinguish whole-system stall. | CP1 images were NONE: no frame/NPU receive-gap evidence. Clock domains and USB helper settle time must be documented. Use existing image/NPU collectors with buffered output and receive timestamps. |

Observability caveats matter: config.h currently sets N6_DEBUG_OUTPUT_ENABLED=0
and N6_CLI_DIAGNOSTICS_ENABLED=0. Debug_UART_Log returns early at debug_uart.c:1180,
and NcpTraceEnabled returns0 at1242. Thus the mere presence of RADIO-WAIT source
does not prove those logs exist on a candidate. Resource counters remain separate,
but Debug_UART_Write's disabled branch returns the positive length without output.
The N6R_QueuedBytes adapter accepts only status0; it therefore treats those
disabled writes as failures and keeps a pending row eligible for bounded retry.
This is an open source-level return-contract mismatch, not proof of the cause of
CP1 SPI faults. No firmware fix is included in this checkpoint. Deferred resource
rows cannot be inferred from a silent UART. Running51 emitted
debug output in CP1, another reason to identify its exact build flags.

When enabled, NcpTrace formatting is performed on the calling parser read path,
though the SPI hook is scalar-only and UART transport is queued. This is not
proof of zero observer overhead. P1-03 still needs enabled/disabled measurements
on identified builds. Additional formatting must not be added to that receive
path. A small existing-owner scalar record drained by the existing reporting
worker is the bounded direction for P1-02 if baseline correlation needs it;
do not print payloads, AT arguments, passwords, tokens or arbitrary pointers.

No instrumentation, timeout, memory capacity, ownership policy or recovery
behavior was changed. P1-02/03/04/05 remain open, including symptom reproduction
and classification. CP1 SPI failure cause remains UNRESOLVED.

## Native regressions and test repair

All commands used `C:/Python314/python.exe -B` with the named repository test.
Compiler: the existing MSVC native harness. Initial commands/timestamps/hashes
and their complete output are in native-tests.json and individual logs.

| Suite | Initial outcome | Final outcome / scope |
|---|---|---|
| test_wifi_assoc_admission.py | PASS | 11 actual-C groups plus2 source audits; admission deadline, wrap, no-byte BUSY and partial-write fence |
| test_ble_recovery_barrier.py | PASS | 6 actual-C groups; old/fresh event epochs, input quiescence, exclusive image route |
| test_cloud_socket_recovery.py | PASS | 9 actual-C groups; ambiguous opens, uncertain query, CLOSING identity and exactly-once retirement |
| test_wifi_link_restore.py | PASS | 6 actual-C groups plus1 source audit; desired intent, three-attempt cap, delay and cancellation |
| test_ble_recovery_notice.py | PASS | 9 actual-C groups plus1 source audit; backpressure, UNKNOWN event, terminal drain and generations |
| test_cloud_radio_barrier.py | FAIL before assertions: N6H_CLOUD undefined / N6H_Beat missing in fixture | Repaired fixture PASS, 8 actual-C groups; original seven recovery assertions retained and watchdog progress checked across normal/paused worker iterations |
| test_resource_diagnostics.py | PASS | 3 actual-C groups plus startup-order source assertion; dirty NOLOAD initialization, failure retention, finite reporting, pool/queue/stack accounting |

The Cloud fixture now includes the real n6_watchdog_policy.h enum and mocks only
the watchdog reporting boundary, asserting the Cloud owner and one beat per
bounded worker iteration. It does not remove the production watchdog call,
simulate a hardware reset, weaken any recovery assertion or alter firmware.
Before/fixed fixture, patch, failed log and successful rerun are retained. The
five unaffected passing suites were not rerun after this isolated fixture edit.
`git diff --check` passes. No firmware build is required for a Python/native test
fixture change; the actual extracted Cloud C was compiled by the repaired test.
These host cases support later P2/P5/P7 gates but do not satisfy physical HIL.

Conclusions after this group:

1. The v51 gap blocks candidate attribution and the next installation preflight,
   not independent software audit/testing. No guessed build or slot is selected.
2. Existing counters already cover much of the requested diagnostics. The gaps
   are class/transaction correlation, transport timing coverage and measured
   observer effects, not a reason to add another owner or expand buffers.
3. A real test-fixture regression was found and repaired. Seven relevant suites
   now pass in their native scope, with the original failure preserved.
4. Remaining board-dependent P0/P1 work still needs exact artifact/configuration
   identity and frozen workloads; no physical manipulation is currently requested.
