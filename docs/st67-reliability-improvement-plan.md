# ST67 Reliability Improvement Plan

Created: 2026-10-28 (Asia/Jerusalem)  
Last updated: 2026-10-29 (Asia/Jerusalem)  
Status: **CP12A: acceptance worksheet frozen; existing settings-preserving BLE-only profile identified; P0 baseline variants/Cloud receiver measurements pending; reliability repairs still unapplied**  
Target: STM32N657 + ST67W611M1, existing T01 architecture

## 1. Objective and scope

Keep BLE control responsive during Wi-Fi/Cloud activity, prevent receive-memory
exhaustion, and recover from failures at the smallest appropriate scope. A slow
operation must not automatically become a module reset. Genuine protocol
desynchronization must still fail closed and use coordinated recovery.

This is a work and implementation tracker based on the ST documentation review,
the current source, and retained project test reports. It is not a claim about
the firmware currently running on the board. Creating this plan does not run
tests, change firmware, load hardware, or accept historical failures as resolved.

Extend the existing owners, queues, transaction handling, and recovery mechanisms.
Do not create a second radio manager or replace the driver without evidence.
This plan complements the existing engineering records; it does not supersede
[AGENTS.md](../AGENTS.md) or erase their acceptance limits.

## 2. How to track progress

- Use `- [ ]` for open tasks and change it to `- [x]` when the stated work is done.
- Keep task IDs stable. Add new IDs rather than renumbering completed work.
- Every completed task needs a dated execution-log entry with evidence.
- A code change can be complete while its hardware validation remains open.
- Use `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `DONE`, or `REOPENED` in the phase table.
- Use `PASS`, `FAIL`, `INCOMPLETE`, `NOT_RUN`, or `NOT_APPLICABLE` for test results.
- Record failures and interrupted runs before retrying. Do not overwrite them.
- If later evidence invalidates completion, reopen the checkbox and append the reason.
- If an audit proves a change unnecessary, record `NO_CHANGE_REQUIRED` with evidence;
  do not implement redundant code merely to check a box.

| Phase | Focus | Status | Owner | Evidence / last update |
|---|---|---|---|---|
| P0 | Establish the exact baseline | IN_PROGRESS | Codex | CP12A: P0-05 worksheet frozen; existing APP_DEMO_BLE_ONLY profile supports a non-circular USB-only V01 path. Exact baseline builds and V02-V04 receiver windows pending. |
| P1 | Measure contention and classify failures | IN_PROGRESS | Codex | CP5: shared-error attribution audit and quiet-logger defect reproduced; exact B52 SPI OVR observed. Runtime cause/observer overhead unresolved; implementation still depends on P0. [Evidence](../../n6-xip-ota-usb/docs/st67-reliability-fault-audit-20261028/report.md) |
| P2 | Audit and repair AT transaction lifecycle | NOT_STARTED | TBD | — |
| P3 | Reduce shared-channel blocking | NOT_STARTED | TBD | — |
| P4 | Protect SPI receive resources | NOT_STARTED | TBD | — |
| P5 | Refine recovery and reconnect policy | NOT_STARTED | TBD | — |
| P6 | Validate firmware/configuration compatibility | NOT_STARTED | TBD | — |
| P7 | Integrated acceptance and delivery | NOT_STARTED | TBD | — |

## 3. Evidence baseline: what is already known

| Area | Current evidence | Remaining question |
|---|---|---|
| Recovery | Coordinated NCP recovery, owner barriers, attempt limits, and ordinary Wi-Fi restoration already exist. | Are all escalation decisions correct for the exact candidate under combined load? |
| AT contention | October 8 tests recorded BLE delays around 3.1–3.4 s during Wi-Fi scans while USB continued. The evidence supports contention on the shared AT channel. | How much delay comes from queueing, command ownership, NCP execution, RF, or the host receiver? |
| Receive memory | A historical run reproduced SPI RX allocation failures followed by a missing raw-transfer response and an AT fence. | Can the failure recur in the current source/build and under which resource conditions? |
| BLE-only operation | A corrected October 12 one-hour test passed with maximum CLI latency about 220 ms on that exact protected RAM image. | Does the target candidate meet the same responsiveness requirement with Wi-Fi/Cloud active? |
| SPI | SPI5 is dedicated to ST67. Existing code contains handshake, timing, DMA cleanup, and packet-lifetime fixes. | Are stall, partial-read, DMA-error, and resource-pressure paths all covered? |
| Firmware | The project contract preserves T01 / SDK 2.0.106. The local vendor package includes that binary. | Does the running module match the contract and the host driver? |
| Later functionality | October 21 platform records include focused BLE and Wi-Fi capture acceptance. | Focused capture results do not establish this plan's combined-load/endurance acceptance. |

Evidence references:

- [Radio stability investigation](radio-stability-20261008.md)
- [Transaction ownership and Cloud recovery](radio-transaction-cloud-recovery.md)
- [Coordinated recovery and BLE-only results](radio-coordinated-recovery.md)
- [Existing asynchronous recovery plan](async-architecture-recovery-plan.md)
- [CLI admission and backpressure](cli-service-backpressure.md)
- [October 21 platform results](platform-upgrade-20261021.md)

## 4. Implementation constraints

- Preserve exclusive AT transaction ownership until the protocol is complete or
  fenced. An application timeout does not cancel execution in the NCP.
- Do not clear a genuine AT fence merely to retry. Do not replay a command with
  an unknown side effect. Preserve the existing UNKNOWN outcome mechanism.
- Keep callbacks bounded: snapshot/enqueue/signal only. No blocking W6X calls,
  sleeps, or diagnostic formatting in parser callbacks or interrupt context.
- Reuse the Wi-Fi control worker, Cloud worker, Radio Manager, and notification pump.
- Preserve dedicated SPI5, event-driven idle waiting, and existing DMA abort fixes.
- Preserve partial packet tails and parser assembly lifetime. Do not allocate the
  assembly buffer from the constrained radio byte pool.
- Keep current queue, pool, stack, and image-buffer capacities unless measurements
  justify an explicitly documented architecture change. Preserve the minimum
  360 KiB linked heap reservation and measure actual stack/resource margins.
- Preserve one active remote image destination. Test BLE CLI while Cloud images
  are active, and Cloud control while BLE images are active; do not add image fanout.
- Preserve ToF/NPU/USB continuity, credentials, saved settings, and Cloud pairing.
  Do not pair the device in Windows or erase bonds/caches as a troubleshooting step.
- Use the current hardware-ownership and guarded RAM workflow when execution reaches
  HIL. This document is not authorization to interrupt an active user session,
  perform persistent installation, or update the NCP firmware.

## 5. Work packages and completion checklists

### P0 — Establish the exact baseline

Depends on: none.

- [x] **P0-01** Record source revision, local changes, build configuration, ELF/BIN hashes, enabled features, and host test-tool versions for the baseline.
- [x] **P0-02** When hardware access is available, read running module information and compare it with `radio_firmware/contract.json`; record SDK, AT, middleware versions, and T01 profile without changing settings.
- [x] **P0-03** Capture the existing recovery states, retry limits, transaction deadlines, memory capacities, and connection-intent behavior in a baseline report.
- [ ] **P0-04** Run bounded baseline profiles: BLE-only, Wi-Fi/Cloud-only, and combined control traffic with one image route. Capture exact counts, latency distributions, receive gaps, and errors.
- [x] **P0-05** Freeze the acceptance worksheet in section 7 before implementation; assign numeric limits to all TBD entries and record the workload/rate/MTU/image format.

Exit: a reproducible baseline tied to exact artifacts, with unknowns explicitly listed.

### P1 — Measure contention and classify failures

Depends on: P0. Reuse existing RADIO-WAIT diagnostics before adding instrumentation.

- [x] **P1-01** Audit existing counters and logs; identify only the missing measurements needed to separate admission wait, AT ownership, NCP response time, SPI transfer time, and host receive delay.
- [ ] **P1-02** Add bounded scalar timing/counters where needed: command class, owner, transaction phase, generation, completion outcome, queue occupancy, and memory low-water marks. Exclude passwords, tokens, and payloads.
- [ ] **P1-03** Keep formatting/output outside SPI/parser critical paths; compare diagnostics-enabled and disabled runs to quantify observer overhead.
- [ ] **P1-04** Reproduce a delay under the recorded workload and correlate firmware timestamps with host timestamps. Distinguish local admission BUSY from the NCP text response `busy p`.
- [ ] **P1-05** Produce a failure classification for each reproduced case: contention, RF/link loss, remote endpoint, resource shortage, SPI/DMA fault, AT desynchronization, or unresolved.

Exit: at least one reproducible symptom has evidence locating its delay/failure,
or the investigation explicitly remains unresolved; no guessed cause is marked fixed.

### P2 — Audit and repair AT transaction lifecycle

Depends on: P0–P1.

- [ ] **P2-01** Document the actual response sequence for scan, connect, DNS, socket send, and BLE notify on the contracted firmware. Separate acknowledgement, prompt, payload, terminal response, and unsolicited report.
- [ ] **P2-02** Verify `busy p` handling against the ST protocol: continue receiving within a bounded operation budget; do not treat it as permission to send a second command or restart the module.
- [ ] **P2-03** Audit separate budgets for admission, admitted execution, application waiting, and bounded late-response drain. Preserve existing per-operation limits unless measurements justify a change.
- [ ] **P2-04** Repair any path that frees command ownership, parser context, borrowed scan storage, or payload buffers before the protocol lifecycle ends. Preserve fencing on ambiguous partial raw transfers.
- [ ] **P2-05** Test delayed/missing/duplicate terminal responses, interleaved events, response fragmentation, cancellation, and generation changes. Prove no stale response completes a later command.
- [ ] **P2-06** Verify exactly one application outcome per accepted request: completion, explicit failure, or unknown outcome after interruption. Do not silently replay side-effecting operations.

Exit: transaction-lifetime tests pass, and timeout handling cannot mix command responses.

### P3 — Reduce shared AT-channel blocking

Depends on: P1–P2.

- [ ] **P3-01** Rank command classes by measured maximum ownership time and their impact on BLE control latency.
- [ ] **P3-02** Define admission rules for long scans/connect operations during latency-sensitive traffic: bounded deferral or explicit rejection, with a visible reason and a maximum wait to avoid starvation.
- [ ] **P3-03** Audit existing bounded Cloud send slices and cooperative pumps. Adjust only where measurements show excessive hold time; allow pending control work between complete transactions.
- [ ] **P3-04** Preserve immediate nonblocking BLE admission when another owner holds AT. Retain the pending fragment, and use bounded retry scheduling without busy-wait loops.
- [ ] **P3-05** Verify fairness under sustained traffic: CLI replies complete, Cloud makes progress, and best-effort images cannot starve control or signed-update traffic.
- [ ] **P3-06** Repeat the baseline workload and record before/after maximum and p95/p99 latency, AT hold time, throughput, drops, and application admission failures.

Exit: measured improvement satisfies the frozen service limits without premature
lock release. Do not preempt an in-flight AT transaction. If an uninterruptible
NCP operation makes a requirement infeasible, document that limitation and the
service/admission decision instead of claiming priority scheduling solved it.

### P4 — Protect SPI receive resources and flow control

Depends on: P1–P2; implement independently of P3 where changes do not overlap.

- [ ] **P4-01** Audit `SPI_RDY`/`SPI_CS` sequencing, full-duplex operation, startup readiness, and `rx_stall` handling against ST's interface specification.
- [ ] **P4-02** Verify that `rx_stall` completes the current bus transaction and retains/retransmits only the unaccepted data in a separate transaction; do not replay an already accepted application command.
- [ ] **P4-03** Calculate worst-case simultaneous RX/TX/parser/scan memory demand and compare it with measured free bytes, fragmentation, and allocation failures.
- [ ] **P4-04** Add or refine bounded admission/backpressure before resource exhaustion, preserving RX progress. Prefer existing fixed storage and lifetime repairs over increasing memory capacities.
- [ ] **P4-05** Test partial reads, retained packet tails, RX allocation failure, a full queue, and prolonged ready/busy conditions. Prove bounded failure and correct buffer release without double free or data truncation.
- [ ] **P4-06** Verify local SPI/DMA abort cleanup and retained fault evidence. Escalate only when transport/protocol state cannot be safely restored; do not reset the shared DMA controller.

Exit: focused transport/resource tests pass, the target workload has no unexplained
allocation failures, and injected pressure cannot corrupt protocol ownership.

### P5 — Refine recovery and reconnect policy

Depends on: P2–P4.

- [ ] **P5-01** Map every recovery trigger to the decision table below; identify existing compliant paths and only implement missing behavior.
- [ ] **P5-02** Keep request/socket recovery local while NCP health and AT synchronization remain valid. Classify remote errors before retrying; retain existing idempotent sequence/ACK semantics where applicable.
- [ ] **P5-03** Coordinate module reconnect settings and host desired-state restoration so they cannot create competing reconnect loops. Honor explicit user disconnect/cancellation.
- [ ] **P5-04** Define bounded retry counts and capped increasing delays, with jitter where appropriate; avoid retry storms and preserve current operation deadlines unless explicitly revised.
- [ ] **P5-05** Verify genuine-fence recovery: stop admissions, quiesce every owner and DMA, retire old contexts, restart the module, wait for readiness, and restore desired services without stale events.
- [ ] **P5-06** Test reset-loop prevention, unsuccessful recovery, and the user-visible unavailable/unknown state. Keep USB/ToF responsive and report the reason rather than retrying forever.

| Condition | Intended action | Escalation condition |
|---|---|---|
| Local AT admission BUSY | Defer/reject before sending bytes; preserve pending work | Persistent deadline violation requires contention diagnosis, not an automatic reset |
| NCP `busy p` or expected progress | Receive events and wait within the operation budget | Expired budget enters the applicable drain/fence path |
| Server/socket error with valid AT state | Recover the request/socket with bounded, safe retries | Evidence of a broader transport or protocol failure |
| Wi-Fi loss with responsive NCP | Use reason-aware desired-state reconnection | Confirmed NCP/transport fault; ordinary retry exhaustion alone is not proof |
| BLE-only state mismatch | Reconcile through existing BLE control owner | Do not reset healthy Wi-Fi/Cloud for a BLE-only fault |
| Application timeout, command still outstanding | Report timeout while preserving protocol ownership | Bounded drain fails or the protocol becomes ambiguous |
| SPI/DMA fault | Capture evidence and perform supported local cleanup | Unsafe protocol state or unsuccessful local cleanup |
| Genuine AT desynchronization | Fence traffic and use coordinated NCP recovery | Recovery limit reached: remain unavailable with explicit diagnostics |

Exit: each failure class has a tested bounded response; ordinary network failures
do not cause unrelated service resets.

### P6 — Validate firmware and configuration compatibility

Depends on: P0 and relevant P1 findings. This phase does not presume an upgrade.

- [ ] **P6-01** Compare exact running and packaged versions with the applicable ST release notes and retain a dated compatibility report.
- [ ] **P6-02** Audit power-save, BLE clock requirements, DHCP/static-IP behavior, and TLS limitations against the actual workload and hardware.
- [ ] **P6-03** If a setting is implicated, design a reversible one-variable comparison and record its latency, throughput, power, and reconnect effects. Preserve saved settings.
- [ ] **P6-04** Record the evidence-based decision: retain T01/2.0.106, change a runtime configuration, or propose a coordinated host/NCP upgrade. An upgrade needs its own contract/hash updates and Stage 10/11 validation.

Exit: a documented compatibility decision; no speculative firmware replacement
or migration to T02 is required to complete this plan.

### P7 — Integrated validation and delivery

Depends on: P2–P6 and the completed acceptance worksheet.

- [ ] **P7-01** Run the focused actual-C/native regressions affected by each change, relevant feature builds, and required build/link/memory checks; retain exact commands and results.
- [ ] **P7-02** Run the matrix in section 7 on the exact candidate, including delayed responses, ordinary link loss, resource pressure, and a genuine coordinated recovery.
- [ ] **P7-03** Run a supervised one-hour combined profile with the frozen workload. Check direct receive gaps and host event-loop lag; keep log writing off the receive path.
- [ ] **P7-04** After the one-hour profile passes, run the longer endurance duration selected in P0. Preserve every failed or incomplete run and repeat only after a relevant change or justified diagnostic correction.
- [ ] **P7-05** Validate recovery after a fresh startup in the agreed hardware workflow; distinguish it from a warm reconnect or RAM reload and identify exactly which image starts.
- [ ] **P7-06** Remove temporary fault hooks, restore intended runtime configuration, and verify the final artifact. If removal changes the binary, repeat affected validation on that final binary.
- [ ] **P7-07** Update operational documentation and the changelog for implemented changes; record vendor-code deviations, rollback artifact, Generate Code requirements, remaining limitations, and release/package status.
- [ ] **P7-08** Review all evidence and sign off only when required gates pass. Record package-only/signing verification separately from persistent installation; do not infer delivery acceptance from compilation alone.

Exit: reproducible acceptance for a specified artifact, workload, and duration,
with an explicit final decision and any remaining limitations.

## 6. Implementation map and reusable tests

Paths below are relative to the project root. Modify the imported project driver,
not the separate reference SDK checkout. Inspect each test's setup before running it;
its presence does not imply it is hardware-free or that it currently passes.

| Work | Main implementation locations | Existing tests to inspect/reuse |
|---|---|---|
| AT ownership and parsing | `ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c/.h`, `w61_at_common.c/.h`, `w61_at_ble.c`, `w61_at_wifi.c` | `test_dns_reply_lifetime.py`, `test_wifi_scan_lifetime.py`, `test_wifi_assoc_admission.py`, `test_ble_recovery_barrier.py` |
| Scheduling / service admission | `AppliNonSecure/Core/Src/wifi_ble_app.c`, `cloud_relay.c`; driver `Core/w6x_wifi.c` | `test_wifi_scan_admission.py`, `test_cloud_send_slices.py`, `test_cloud_request_budget.py`, `test_radio_service_status.py` |
| SPI / resource lifetime | Driver `Driver/W61_bus/spi_iface.c`; `AppliNonSecure/Core/Src/spi_port.c` | `test_spi_fs_framing.py`, `test_spi_cs_hold.py`, `test_spi_fault_snapshot.py`, `test_radio_spi_shutdown.py` |
| Recovery | `wifi_ble_app.c`, `cloud_relay.c`, AT and SPI shutdown paths | `test_radio_coordinated_recovery.py`, `test_radio_modem_shutdown.py`, `test_cloud_radio_barrier.py`, `test_cloud_socket_recovery.py`, `test_wifi_link_restore.py`, `test_ble_recovery_notice.py` |
| Diagnostics / endurance | Existing UART diagnostics and `hil_tests` collectors | `test_radio_wait_diagnostics.py`, `run_radio_failure_soak.py`, `run_radio_recovery_soak.py`, `run_ble_npu_soak.py` |

Test filenames in the last column are under `hil_tests/`. Extend meaningful
behavioral tests; do not substitute source-text assertions for protocol or hardware proof.

## 7. Acceptance worksheet and test matrix

Freeze TBD values in P0 before the campaign. Preserve stricter applicable project
contracts. Never relax a limit after a failure just to obtain a PASS.

| Metric / campaign parameter | Required value | Evidence / origin |
|---|---|---|
| Accepted ordinary BLE CLI request to matching final response | **<1500ms**, p50/p95/p99/max | Existing strict receiver gate; CP8 FAIL1953ms retained |
| Lost/duplicate ordinary CLI outcomes | **0**, one explicit failure/UNKNOWN for interruption | Existing plan; unique tokens and frozen window |
| Unrelated reset during ordinary server error or Wi-Fi loss | **0** | Existing plan; planned fault outages separately timed |
| CRC corruption / stale-generation delivery | **0** | Existing plan; receiver evidence required |
| RX allocation failure / unexplained SPI fault in normal workload | **0** | Existing allocation gate; SPI zero selected for normal campaign acceptance |
| Linked heap / runtime resource reporting | **>=369072 bytes** linked heap; free stack/pool **>0 bytes** in measured samples, report minima/largest-block/worst-case limitations | Stronger build guard retained; samples are not worst-case proof |
| ToF/USB responsiveness and continuity | USB unique ping **<1000ms**, offered1Hz; ToF frame progress gap **<=3s**, NPU errors **0** | Selected campaign limits; compare with existing passing USB~65ms baseline |
| Wi-Fi/socket restore deadline | Got-IP **<=45s** after AP available; **3 CRC-valid Cloud frames within30s** after IP | Existing recovery harness; current settings-mutating harness will not be run unchanged |
| Coordinated NCP recovery deadline | Ready or explicit failed/unavailable **<=90s**; successful readiness **<=90s**; max3 attempts/60s; retain35s owner barrier/2s SPI quiesce | 90s selected end-to-end target, not inferred from35s barrier; CP7 observed24.556s is not acceptance |
| BLE/NPU/image maximum receive gaps | NPU **<3s**, image **<5s**, including combined ordinary profiles; floors **6000 NPU/h**, **3000 images/h**, prorated with existing integer rule | Existing BLE gates retained; extended to target combined routes; CP4 FAIL99/100 unchanged |
| Cloud ordinary command / host validity | Cloud unique final **<10000ms**, offered1/10s; host event-loop lag **<=100ms** for a valid measurement | Selected targets before implementation; manual2.5s is not a measured PASS |
| Traffic rates / MTU / image route / format | MTU247; BLE ping next0.5s after final; USB1Hz; Cloud0.1Hz; actual ToF10Hz/NPU; BLE DEPTH54x42 RAW float32; Cloud DEPTH54x42 UINT8 affine; one image route | Exact workload and profile mapping in [CP12 worksheet](../../n6-xip-ota-usb/docs/st67-reliability-baseline-fixture-20261029/acceptance-worksheet.json); record actual offered/admitted counts |
| Baseline / endurance durations | **120s** bounded profiles, then **3600s** combined gate, then **14400s** longer endurance | One hour required by plan; four hours selected for this campaign |

Worksheet frozen at CP12 before baseline-profile builds or reliability integration.
Numeric targets selected here are requirements to test, not guarantees or
retrospective reclassification of old runs. No limit may be relaxed after failure.
Each newly frozen profile remains NOT_RUN until its exact receiver window exists.

| ID | Profile / stimulus | Required observation | Result | Evidence |
|---|---|---|---|---|
| V01 | BLE CLI + BLE images/NPU, Wi-Fi inactive | Latency and direct receive continuity; baseline comparison | NOT_RUN | — |
| V02 | Wi-Fi/Cloud active, BLE control idle | Cloud progress, socket health, memory stability | FAIL scoped transport observation; full metrics INCOMPLETE | CP9: existing UINT8 Cloud stream120s, sender150->269, SPI122->123, errors109->110; no controlled Cloud command/receive-window acceptance |
| V03 | BLE CLI + Cloud images + USB/ToF | BLE latency and independent USB/ToF progress | NOT_RUN | — |
| V04 | BLE images/CLI + Cloud control | Fairness with exactly one image destination | NOT_RUN | — |
| V05 | Scan/connect requested under BLE load | Explicit bounded admission and progress; no hidden multi-second ordinary CLI stall | NOT_RUN | — |
| V06 | AP loss and return | Desired-state restoration without NCP reset; explicit disconnect stays disconnected | NOT_RUN | — |
| V07 | Slow/unavailable DNS or server | Bounded local failure/retry, no unrelated BLE reset | NOT_RUN | — |
| V08 | Late response, `busy p`, fragmented/interleaved reports | Correct transaction ownership and no cross-command completion | NOT_RUN | — |
| V09 | RX shortage / queue saturation / `rx_stall` | Retained data, bounded pressure handling, no corruption | NOT_RUN | — |
| V10 | SPI/DMA fault and genuine AT desynchronization | Local cleanup where safe; otherwise coordinated recovery, no stale work replay | NOT_RUN | — |
| V11 | One-hour combined workload | All frozen profile limits hold for the full measured interval | NOT_RUN | — |
| V12 | Longer endurance and fresh-start repeat | No progressive resource loss; correct final artifact and startup behavior | NOT_RUN | — |

For V08–V10, record native fault-model evidence separately from physical HIL.
Do not deliberately corrupt hardware traffic before a bounded injection and
cleanup procedure is defined. A native PASS alone does not prove physical recovery.

## 8. Execution history — append only

| Date / time (Asia/Jerusalem) | Task / run ID | Change or observation | Result | Artifact / evidence | Next action |
|---|---|---|---|---|---|
| 2026-10-28 | DOC-01 | Created this plan from the reviewed ST sources and retained project evidence. No firmware changes or new hardware tests. | Documentation created; implementation NOT_STARTED | This file; references in sections 3 and 10 | Start P0 |

### CP0 - 2026-10-28 22:45 Asia/Jerusalem (20:45 UTC), Codex

| Task / run ID | Change or observation | Result | Evidence | Next action |
|---|---|---|---|---|
| P0-01 | Recorded clean feature/n6-xip-ota-usb at 5432d4ae2b10ef7ecdfaedad586038792f0a4db5, source/build flags, current host tools, recomputed exact A49/B50 ELF/BIN/MAP/package hashes and source differences | PASS for host baseline; live firmware UNKNOWN | [CP0 baseline](../../n6-xip-ota-usb/docs/st67-reliability-baseline-20261028/report.md); adjacent baseline.json | P0-02 live identity over CN8 |
| P0-03 | Recorded existing recovery states, owner barriers, retry/deadline scopes, fixed capacities and persistent connection intent from current source | PASS for source audit; runtime margins/timing NOT_RUN | Same report, recovery/budget/resource table | Use this baseline in P1-P5 after P0 exit |
| P0-NATIVE-01 | Four existing host suites, 26 native actual-C cases plus 3 source audits | PASS; compiler fixture warnings retained; no HIL | Four adjacent .py.log files; baseline.json commands/hashes | Preserve limits; run relevant candidate regressions later |
| P0-PACKAGES-01 | Existing A49/B50 signatures, slot vectors, payload hashes and all recorded artifact hashes verified offline | PASS offline only; no new signing/build/install | baseline.json artifact_sets | Retain both artifacts; identify actual confirmed/pending versions first |
| P0-USB-01 | Present-only PnP and CIM show ST-LINK/COM6 only; no application CDC or second COM | BLOCKED; P0-02/P0-04/P0-05 NOT_RUN | adjacent usb-presence.json, 20:42:34 UTC | Verify PC-to-CN8 data cable; no reset/jumper/power change |

Conclusions after this group:

1. Existing T01 owners, terminal drains and coordinated recovery are the baseline;
   there is no measured reason yet to replace them or duplicate a manager.
2. Native checks and offline package integrity pass, but combined-load latency,
   memory pressure, recovery timing and endurance have not been measured here.
3. Tracked version 11 differs from saved XIP B50; neither establishes the running
   version. No next firmware version has been selected or consumed.
4. Section 7 limits remain unfrozen where P0 requires live measurements. P1-P7
   remain NOT_STARTED; no acceptance checkbox or HIL result is inferred from
   compilation or historical reports.

The original plan is preserved as plan-before.md in the task evidence workspace.
The current user requires every software update through the existing signed USB
path. That instruction supersedes this document's general guarded-RAM workflow
for this campaign. No SWD/RAM load, bootloader/Secure/NCP replacement, security or
ACL change is authorized as a workaround. Hardware handles opened: zero; firmware
writes: zero; resets: zero. No source implementation, push or deployment occurred.
Generate Code is not required for this documentation checkpoint.

### CP1 - 2026-10-28 23:05 Asia/Jerusalem (21:05 UTC), Codex

| Task / run ID | Change or observation | Result | Evidence | Next action |
|---|---|---|---|---|
| P0-USB-02 | CN8 COM8 restored; 120-second USB stability, 58 exact pings; max 65.949 ms | PASS scoped USB continuity; prior D04 resolved | [CP1 report](../../n6-xip-ota-usb/docs/st67-reliability-usb-resume-20261028/report.md), usb-resume result.json | Preserve USB-only path |
| P0-01 / P0-02 | Live application 51; authenticated old-manifest rejection reports Secure confirmed 51; SDK 2.0.106.0 / AT 1.0.0.0 | P0-01 REOPENED: host baseline retained but exact live source/build/package missing; P0-02 INCOMPLETE | CP1 live identity and uart.log; 256 manifest bytes, zero image bytes/EOT/reset | Locate v51 artifact/build and recovery record |
| P0-CONTROL-01 | 120 s, 120 BLE CLI pings at 1 Hz, MTU247, 52 simultaneous USB pings, existing Wi-Fi/Cloud polling, images NONE | PASS scoped controls: BLE max/p99 203 ms, p95 156 ms; zero missing/duplicate outcomes; loop lag max44 ms | control result.json; pair=False, no settings commands | P0-04 image/Cloud/BLE-only profiles remain open |
| P0-SETTLED-01 | 30-second USB check; BLE disconnected/advertising on, notifications off, empty queues; handles/lease released | PASS cleanup/USB; SPI fault count now3 versus1 earlier, cause UNRESOLVED; NCP recovery0/allocfail0/NPUerrors0 | settled result.json; last SPI tick813425, HAL_error4/SR00be0040 | Retain fault and correlate on identified build |

Conclusions after this group:

1. CN8 works again and no cable, jumper or power action is currently required.
   Short-run stability does not establish endurance acceptance.
2. BLE control passed its existing 1500 ms gate under background Cloud polling.
   This is not an image-load/Cloud delivery gate; V01-V12 remain NOT_RUN.
3. Two additional SPI faults were observed between snapshots, without module
   reset; ToF/NPU/USB remained available. Their cause is unresolved. The immediate
   post-test BLE connected state later settled naturally to disconnected.
4. The exact running/confirmed v51 artifacts were not found in the searched
   locations. P0-01 is reopened; P0-02/P0-04/P0-05 remain incomplete and P1-P7
   NOT_STARTED. Source/build/package location was requested from the user.
5. No firmware payload, new version, reboot, persistent settings, bond/cache,
   bootloader/security/ACL change, commit or push occurred. The old signed
   manifest was rejected before flash-session creation. No uncertain install
   exists. Every owned hardware handle and lease was released.

### CP2 - 2026-10-28, Codex: expanded provenance search and independent host work

| Task / run ID | Change or observation | Result | Evidence | Next action |
|---|---|---|---|---|
| P0-01 / SEARCH-51 | Read86 signed-package headers,62 recent binaries,143 output/docs files; N6 worktrees/refs/reflog and9 recent N6 assistant histories | INCOMPLETE provenance: max package50, no compiled51 or prior51 build/install evidence; no read errors | [CP2 report](../../n6-xip-ota-usb/docs/st67-reliability-host-audit-20261028/report.md), artifact-search.json, binary-version-search.json | Minimal user detail: installing computer or build/output folder |
| P1-01 | Audited existing RADIO-WAIT, BLE queue/call timing, terminal SPI/parser age, fault snapshots, resource lows/highs and host latency collectors | DONE for exact source5432d4a as preparation; live build correlation remains open | CP2 observability table and source-audit.json hashes | Reuse counters; P1-02/03 wait for identified/frozen baseline |
| HOST-REGRESSION-02 | Five relevant native suites passed; Cloud barrier fixture failed to compile because watchdog boundary was absent | FAIL preserved, firmware fault not inferred | native-tests.json and original test_cloud_radio_barrier.py.log | Repair only fixture |
| HOST-FIXTURE-01 | Added actual watchdog policy enum and a bounded mock/owner-progress assertion to existing Cloud worker fixture | PASS8 actual-C groups; existing recovery assertions retained; git diff --check PASS | before/fixed fixture, patch and fixed.log | No firmware build/install required |
| HOST-RESOURCE-01 | Existing bounded resource capture/reporter regression | PASS3 native groups plus startup-order assertion; no hardware | test_resource_diagnostics.py.log | Measure runtime margins later on exact candidate |

Conclusions after this group:

1. CP1's blanket wait was too broad: independent audits and native test repairs
   can proceed. This does not waive P0 or the implementation/acceptance dependencies.
2. P1-01 source audit is complete; P1-02 through P1-05 remain open. Known debug
   compile switches can suppress RADIO-WAIT output, and parser-side formatting
   still requires observer-overhead measurement. No new firmware instrumentation.
3. Seven host suites pass after the isolated fixture repair. The initial failure
   is retained. Native evidence does not prove physical SPI/NCP recovery.
4. No v51 installation provenance was recovered in the expanded scope. Ask only
   which computer/output folder installed51, or obtain an equivalent exact build
   record. No hardware handles, reset, firmware bytes, security/ACL changes,
   commit, push or deployment occurred in CP2.

Copy this record for each meaningful implementation or validation step:

```text
Date/time and owner:
Task IDs / run ID:
Source revision and local diff:
ELF/BIN/package hash and feature configuration:
Running NCP/host versions (if hardware was used):
Change and reason:
Exact test command / workload / start-end time:
Expected result and frozen limits:
Actual counts, latency, receive gaps, memory, errors, recovery counters:
Result: PASS / FAIL / INCOMPLETE / NOT_RUN / NOT_APPLICABLE
Evidence path (sanitized logs/report):
Configuration restored / hardware handles released:
Remaining uncertainty or regression:
Checkboxes completed/reopened:
Next action / rollback reference:
```

### CP3 - 2026-10-29 00:22 Asia/Jerusalem (2026-10-28 22:22 UTC), Codex

| Task / run ID | Change or observation | Result | Evidence | Next action |
|---|---|---|---|---|
| P0-SEARCH-03 | NATISFLOW13 verified; all1451 N6 binaries/all timestamps scanned,3.55GB; no compiled51, no read errors | Exact51 provenance still NOT_FOUND | [CP3 report](../../n6-xip-ota-usb/docs/st67-reliability-known-baseline-20261028/report.md), all-binary-versions.json | Preserve historical limitation |
| P0-SLOT-03 | Native whole-modeled-NOR Begin/Abort proof; USB signed A rejected/B accepted+canceled; separate Secure confirmed51 read | Native PASS; USB diagnostic runner FAIL/INCOMPLETE on absent redundant NS log; direct slot evidence plus post-confirmation retained | slot-probe, post-probe-confirmation, manifest-probe-native.log | A confirmed/B inactive established by existing policy |
| P0-01 | Fresh B52 from5432d4a; exact source/build/ELF/BIN/MAP/package hashes, unchanged CP0 source inventory, ABI/heap/signature/vector guards | DONE for new known baseline52, not recovered51 | baseline52-build.json, build log, source-preservation.json | Measure profiles on52 |
| P0-USB-INSTALL52 | Existing signed CN8 sender;485472bytes/18.854s, automatic reboot; FSBL signature/hash/trialB52 with A51 retained, Secure confirmed52 | PASS installation/first health; not reliability acceptance | install52/result.json, sender.log, uart.log | HIL100 and bounded baseline workloads |

Conclusions after this group:

1. Missing artifact51 no longer blocks measurement on knownB52. The current
   source and installed package are reproducible; historical51 remains unknown.
2. A51 was protected throughout the B52 update and is retained as previous image;
   physical rollback/cold power/current whole-NOR backup were not tested. Do not
   silently overwriteA51 on the next update without resolving recovery retention.
3. SPI count8 on old51 and UART80 dropped logs remain recorded. New52 starts with
   counters0; no root-cause fix or before/after improvement is claimed. Debug
   output differs from51 (tracked quiet52); observer effects need later measurement.
4. P0-02/04/05 remain open; P1 audit/native work is separate from implementation.
   No physical action is required; all hardware handles/leases were released.

### CP4 - 2026-10-29 00:38 Asia/Jerusalem (2026-10-28 22:38 UTC), Codex

| Task / run ID | Change or observation | Result | Evidence | Next action |
|---|---|---|---|---|
| P0-02 | RuntimeSDK2.0.106.0/AT1.0.0.0, driver1.3.0; exact packagedT01 hash matches contract | DONE identity comparison; P6 not accepted | [CP4 report](../../n6-xip-ota-usb/docs/st67-reliability-baseline-tests-20261028/report.md), ncp-compatibility-baseline.json | RetainT01; no NCP update |
| P0-HIL52 |100 exact tensors/NPU100/delta0/CRC0,27.078s | PASS computation regression | hil100-wrapper.json/log | Known52 rollback artifact available for future planned update |
| P0-CONTROL52 |120s/120BLE/52USB, BLEmax203ms/p95=156/p99=203 | PASS scoped latency/outcomes; BLE driver counter0->1 unresolved | control52/result.json | Correlate driver event; no full radio acceptance |
| P0-IMAGE52 |120.141s,199CLI/99images/230NPU; max219ms; imagegap1.406s/NPUgap0.641s; CRC0 | **FAIL corrected99<100 image reference floor**; latency/gaps PASS; notV01/fullV04 | image120-corrected-assessment.json; raw PASS retained | Attribute throughput after baseline completion; no relaxed threshold |
| TEST-WINDOW-01 |End-state query allowed post-window images into acceptance; now uses frozen window counts | FIXED host harness;4 boundary tests PASS | run_ble_npu_soak.py, test_ble_soak_measurement_window.py/log | Use corrected gate on subsequent relevant runs |
| P0-FINAL52 |30sUSB max64.333ms; sensor/NPU healthy, SPI/NCP/alloc0; imageNONE/mapOFF/datasetOFF, handles/lease closed | PASS cleanup/short stability; no endurance claim | final-usb/result.json | No physical action needed |
| P0-CLOUD-01 |HTTP409; browser has no loaded workspace; no acceptedCloudCLI/images | BLOCKED; P0-04/05 incomplete | cloud-workspace-inspection.json | User opens existing workspace containingN6-MAINT-B8FB and keeps it open |

Conclusions after this group:

1. KnownB52 passes computation and control tests; image latency/gaps pass, but
   exact measured image count misses the reused reference floor by one. The
   original falsePASS remains visible alongside the correctedFAIL.
2. Host fixture/runtime failures were corrected and retained separately. Native
   no-write manifest proof is now portable; firmware reliability code is unchanged.
3. Cloud activation is the current external prerequisite, not missing51 artifacts.
   No credentials/workspace file were read or uploaded and no pairing was changed.
4. BLE-only still needs a reversible profile: existing Wi-Fi disconnect persists
   autoconnect=false, so it was not used. P0 worksheet and later phase gates remain
   open. No cable, power or jumper operation is required; all hardware is released.

## 9. Decisions, blockers, and final sign-off

| ID | Date | Decision / blocker | Reason and evidence | Owner / resolution |
|---|---|---|---|---|
| D01 | 2026-10-28 | Extend the existing T01 architecture and recovery owners | Existing implementation already has lifecycle, admission, and recovery mechanisms | Review in P0 |
| D02 | 2026-10-28 | Keep manufacturer requirements separate from project recommendations | ST protocol guidance does not constitute a complete application recovery policy | Applies throughout |
| D03 | 2026-10-28 | Treat all hardware results referenced here as historical | No new running-version or baseline measurement was made for this plan | Resolve current baseline in P0 |
| D04 | 2026-10-28 | USB-only campaign; initial CN8 absence | CP0 saw only COM6; user reported cable repair; CP1 sees exact COM8/CN8 and bounded USB continuity PASS | RESOLVED at CP1 for current connectivity; no further physical action requested; endurance stability not yet proved |
| D05 | 2026-10-28 | Keep source defaults, saved build and live identity separate | Tracked header11; offline A49/B50 verified; saved XIP overrides differ from restored headers | Read live version/confirmed slot/pending state before selecting the next version; never use AllowVersionJump or SkipBootVerification |
| D06 | 2026-10-28 | Preserve existing work and security boundaries | Feature worktree initially clean. Older project Git status refused by ownership check; no trust/ACL change. Sandbox CIM read failed, formal read-only escalation succeeded | No Git retry/bypass. Original plan updated in place; [CP0 evidence](../../n6-xip-ota-usb/docs/st67-reliability-baseline-20261028/report.md) in feature worktree |
| D07 | 2026-10-28 | Historical51 provenance and retained recovery | No51 in1451 binary files on NATISFLOW13. CP3 identifiesA51 and installs knownB52 only inB through signed USB | RESOLVED for continuing P0 on52;51 source/host artifact still UNKNOWN, A51 retained. Resolve retention before next update targetsA. [CP3](../../n6-xip-ota-usb/docs/st67-reliability-known-baseline-20261028/report.md) |
| D08 | 2026-10-28 | Two new SPI fault observations on unchanged running 51 | Count 1 during control run, count 3 at settled read; last tick813425, HAL_error4/SR00be0040; NCP reset0, allocfail0, services continue | OPEN, cause unresolved; preserve evidence and correlate only on an identified build; no physical action indicated |
| D09 | 2026-10-28 | Continue independent host work while installation provenance is unresolved | Plan separates source work from HIL; parent requested audit/test continuation; P1-01 and fixture repair completed without changing firmware | No acceptance/dependency waiver; implementation, boot/fallback preflight and workload gates remain open; [CP2](../../n6-xip-ota-usb/docs/st67-reliability-host-audit-20261028/report.md) |

| D10 | 2026-10-29 | Frozen-window test acceptance | Existing soak counted one post-window image:101 final includingwarmup versus99 measured; originalPASS superseded | FIXED host test; correctedFAIL retained,4 boundary testsPASS; no threshold change. CP4 |
| D11 | 2026-10-29 | Cloud workspace prerequisite | DeviceHTTP409; accessible browser has no loaded workspace, existing file carries authentication | BLOCKED for activeCloud profiles; user opens existing workspace containingN6-MAINT-B8FB; no new pairing/file upload/credential read. CP4 |
| D12 | 2026-10-29 | Preserve Wi-Fi connection intent | Existing disconnect persists autoconnectfalse; reconnect requests password | BLE-only profile not run; design reversible in-memory/build profile, no silent settings change. CP4 |


- [ ] **A01** Required implementation/audit tasks have dated evidence or a justified no-change decision.
- [ ] **A02** The exact final candidate passes all required validation profiles and numeric gates.
- [ ] **A03** Failed/incomplete historical and current runs remain accessible; limitations are explicit.
- [ ] **A04** Final configuration, rollback artifact, package status, and operational instructions are recorded.
- [ ] **A05** Final acceptance decision, reviewer, date, artifact hash, and workload scope are entered below.

Final decision: **PENDING**  
Reviewer/date: TBD  
Accepted artifact and NCP version: TBD  
Accepted workload and duration: TBD  
Remaining limitations: TBD

## 10. Manufacturer sources and interpretation

Sources reviewed on 2026-10-28; recheck the exact applicable revision during P6.

| Source | Manufacturer guidance used in this plan |
|---|---|
| [ST67W611M1 SPI interface](https://wiki.st.com/stm32mcu/wiki/Connectivity:ST67W611M1_spi) | Dedicated SPI, handshake/flow control, `rx_stall`, startup readiness, response sequencing, `busy p`, and asynchronous reports |
| [ST67W6X CLI application](https://wiki.st.com/stm32mcu/wiki/Connectivity:Wi-Fi_ST67W6X_CLI_Application) | Connection states, disconnect reasons, reconnect controls, and power/clock configuration |
| [X-CUBE-ST67W61 architecture](https://wiki.st.com/stm32mcu/wiki/Connectivity:X-CUBE-ST67W61_Architecture) | Service APIs, callbacks, driver layers, and configurable timeouts |
| [ST67W6X HTTPS client](https://wiki.st.com/stm32mcu/wiki/Connectivity:Wi-Fi_ST67W6X_HTTPS_Client_Application) | Example configuration explicitly accounting for NCP receive delays of a second or more |
| [X-CUBE-ST67W61 release notes](https://github.com/STMicroelectronics/x-cube-st67w61/blob/main/Release_Notes.html) | Version-dependent fixes and known DHCP, static-IP/power-save, and TLS limitations |

The priority policy, staged recovery table, resource-pressure strategy, and test
campaign are project engineering recommendations derived from these sources and
local evidence. They are not presented as a verbatim ST recovery procedure or a
guarantee that wireless communication cannot fail.


### CP5 - 2026-10-29 00:57 Asia/Jerusalem (22:57 UTC), Codex

- [x] **CP5-PREP-01** Characterize shared ST67 error callback and quiet UART reporter using actual-C native harnesses; record tested proposed patch without applying firmware changes.
- [x] **CP5-PREP-02** Run14 focused SPI/AT/BLE/Cloud/recovery suites; preserve initial failure, repair stale Cloud budget fixture and verify added training retirement boundaries.
- [x] **CP5-PREP-03** Execute actual SPI worker rx_stall/pressure/failure models and classify failures separately from native process success and physical HIL.
- [x] **CP5-PREP-04** Read current B52/CN8 over USB and record fresh overrun evidence and final cleanup.

These completed preparation items do not close P0/P1 or dependent phase exits.
See [CP5 report and conclusions](../../n6-xip-ota-usb/docs/st67-reliability-fault-audit-20261028/report.md).

| Task / run | Result | Evidence / next action |
|---|---|---|
| Native14 suites | PASS after host-only fixture repair; initial compilation FAIL preserved | native-tests.json, fixed-fixture-result.json;120 printed native groups/source audits, no HIL claim |
| Shared error counter | PASS characterization; actual last2 provenance unresolved | diagnostic-contracts-v2.log; future bounded operation ID required |
| Quiet UART contract | FAIL baseline bookkeeping; isolated candidate PASS, NOT_APPLIED | same log and PROPOSED-NOT-APPLIED-quiet-logger.patch; implement only after P0/P1 gate |
| SPI rx_stall/alloc/stop ownership | PASS native scoped cases | spi-pressure-model.log; no wire/fragmentation acceptance |
| SPI ambiguous remaining-RX failure | **FAIL no-replay criterion in native model**: identical TX transmitted twice after possible acceptance | same log; coordinate transport/AT fencing and UNKNOWN outcome, do not blindly retry |
| SPI header ACK / queue | Aggregate wait lacks local deadline; cooperative stop modeled | same log; define bounded safe policy without freeing live DMA/context |
| Fresh B52 USB30s | USB PASSmax65.400ms; **SPI count2 vsCP4count0**, same2 before/after sample; source1/phase2/len332/HAL4/SR00b60040 | usb-after-host-audit/result.json, closing-summary.json; root cause unresolved |
| Closing state | ToF/NPU advance/errors0; NCPreset0/allocfail0; shared drivererrors2; Cloud409/commands0/images0; settingsgeneration2; handles/lease closed | No firmware/reset/settings/physical changes; no cable action required |

Conclusions after this group:

1. B52 also records real SPI OVR, so unknown51 source does not excuse delaying
   source diagnosis. The cause and workload correlation remain unresolved.
2. The error count printed under BLE is shared across ST67; it cannot identify
   the failing operation. Native models expose diagnostic bookkeeping and
   ambiguous packet-replay issues without deliberately faulting the board.
3. The initial Cloud fixture failure and first logger enabled-variant coverage
   gap are preserved. Corrected host results do not erase physical failures.
4. Production C and B52 remain unchanged. Only the host fixture was repaired;
   a small logger patch is prepared and tested in isolation. No53 build/install,
   signing, Secure/NCP/ACL change, commit or push occurred.
5. Existing Cloud workspace activation remains pending. BLE-only baseline needs
   a reversible path preserving saved Wi-Fi intent; P0-05 numeric freeze and
   P1 correlation remain prerequisites for the dependent firmware changes and
   integrated/endurance campaign. No approval was denied or install left uncertain.


### CP6 - 2026-10-29 Asia/Jerusalem / 2026-10-28 UTC, Codex: independent compatibility review

- [x] **CP6-PREP-01** Compare packaged T01 hash, running reported versions and imported host version with dated direct ST component releases.
- [x] **CP6-PREP-02** Audit power/clock, DHCP and TLS configuration and record a retain-current decision with measurement limitations.

Evidence: [CP6 compatibility report](../../n6-xip-ota-usb/docs/st67-reliability-compatibility-20261028/report.md)
and adjacent compatibility.json with source hashes. These preparation items do
not close dependent P6 acceptance while P0/P1 remain incomplete.

Conclusions after this group:

1. Fresh local T01 hash matches both contract and official2.0.106 release;
   direct host component release/header identify1.3.0. Live radio binary was not
   hashed. Top-level release table inconsistency is not proof of a local mismatch.
2. Configured awake/internalRC/DHCP policy is consistent with the hardware use;
   cached GetPowerMode is not fresh NCP state evidence. No clock/power change is
   justified as an SPI fix, and no one-variable experiment was run speculatively.
3. Retain existing T01 and settings. Cloud still requires the existing workspace;
   no NCP/firmware/security/endpoint/physical change, package repair, commit or push.


### CP7 - 2026-10-29 09:44 Asia/Jerusalem (07:44 UTC), Codex: Cloud resume and browser restriction

- [x] **CP7-PREFLIGHT-01** Recheck exact B52/CN8 and existing Cloud identity without settings changes; USB30s PASSmax63.254ms, handles/lease closed.
- [x] **CP7-PREFLIGHT-02** Preserve overnight SPI/recovery counters and the precise browser-tool blocker; no new Cloud load/install accepted.

Evidence: [CP7 report](../../n6-xip-ota-usb/docs/st67-reliability-cloud-resume-20261029/report.md),
summary.json and raw USB result. Existing Cloud polling now204 with2 commands
received/acked: previous inactive-workspace blocker resolved. Actual new test
commands, image profile and worksheet freeze remain NOT_RUN/INCOMPLETE.

Conclusions after this group:

1. SPI captured faults2->117 since CP5;2 automatic NCP recoveries both reached
   ready. Last recovery24556ms; lifetime BLE pump gap24580ms. Neither attribution
   nor supervised endurance acceptance follows from cumulative snapshots.
2. No physical intervention is required by current USB evidence. Settingsgeneration2
   and B52 persist; no update, reset, credential, pairing, Secure or ACL changes.
3. Computer Use blocked selecting Chrome window25299644 because Windows URL
   identity could not be determined confidently for policy enforcement. The tool
   stopped UI work for this turn; no retry or workaround. This is not a shell
   approval rejection. Parent can request foregrounding the existing N6 tab and
   reassess later; do not ask for a new workspace or re-pairing.
4. Already-running USB observation completed safely, all owned handles released.
   P0/P1 dependencies still gate firmware changes. No53, commit, push or deploy.

### CP8 - 2026-10-29 09:59 Asia/Jerusalem (07:59 UTC), Codex: active Cloud baseline

- [x] **CP8-CLOUD-01** Verify existing N6 workspace/PAIR from browser and device without re-pairing; distinguish successful read access from Windows input denial.
- [x] **CP8-BASELINE-01** Execute bounded BLE images/NPU/CLI with active Cloud204 polling and preserve FAIL1953ms against unchanged1500ms gate; stop and clean up.
- [x] **CP8-CLEANUP-01** Verify B52/USB/ToF/NPU and naturally disconnected BLE after failure; all handles/lease closed.

Evidence: [CP8 report](../../n6-xip-ota-usb/docs/st67-reliability-cloud-profile-20261029/report.md),
summary.json, exact collector, failure log, before/after/settled records.
These checkmarks complete observations and failure recording, not acceptance.

Conclusions after this group:

1. RELAY CONNECTED/N6-MAINT-B8FB ONLINE confirmed; no new pairing needed.
   Clicking Cloud CLI input was denied by Windows GetCursorPos0x80070005;
   paste/send did not run, confirmed unchanged UI and device command counters.
   No retry/bypass. User should make existing desktop input accessible before
   a new check. This is not a shell auto-approval rejection or a cable problem.
2. BLE1953ms on the16th measured reply fails1500ms; p50=109ms; host-loop max13ms.
   Planned120s profile aborted early;9.469s is the last successful checkpoint,
   not duration. No frozen end window: total9images/38NPU includes setup/cleanup.
3. SPI117->121 since CP7, but121 unchanged across this test/cleanup; NCP2/2/0,
   allocationfail0 and Clouderrors108 unchanged. Latency cause remains unresolved;
   do not attribute it to SPI or claim a recovery occurred during this profile.
4. USB30s before/after PASSmax64.328/65.074ms. B52/settingsgeneration2 preserved;
   imageNONE/datasetOFF/ToFready/NPUerrors0/BLEdisconnected+advertisingON.
   No firmware/reset/security/ACL/settings changes, no53, commit/push/deploy.
5. P0-04/05 remain incomplete. Actual Cloud traffic and safe BLE-only isolation
   are still required; no dependent firmware gate is waived. Next: restore UI
   input access, finish baseline/frozen workload, then implement and validate
   the measured diagnostic/transaction/SPI repairs via signed USB only.

### CP9 - 2026-10-29 10:13 Asia/Jerusalem (08:13 UTC), Codex: Cloud stream observation

- [x] **CP9-CLOUD-01** Observe existing live Cloud UINT8 stream without changing the user's route/encoding; retain sender/counter observations and new SPI fault.
- [x] **CP9-UI-01** Perform new input check after user's open-desktop confirmation; record repeated Windows denial and read-only session diagnosis; no blocked command sent.
- [x] **CP9-ISOLATION-01** Recheck exact Wi-Fi disconnect/restore semantics before BLE-only testing; persistent desired flag would change, so no unsafe disconnect executed.

Evidence: [CP9 report](../../n6-xip-ota-usb/docs/st67-reliability-cloud-observation-20261029/report.md),
summary.json, raw120s USB result and source hashes. Checkmarks record completed
observations/audit, not acceptance or implemented reliability fixes.

Conclusions after this group:

1. Cloud-only existing stream: sent150->269, requesterrors109->110, SPI122->123;
   NCP recovery2/2/0 and allocationfail0 unchanged. V02 scoped transport FAIL;
   complete browser counts/gaps/command latencies INCOMPLETE. BLE was idle.
2. USB120s PASSmax65.476ms, B52/ToF/NPU healthy. User-started CLOUD route and
   UINT8 format preserved, settingsgeneration2, all owned handles/leases closed.
3. After screenshot/geometry refresh and user-input guard/state refresh, the
   focus click again failed GetCursorPos0x80070005 before paste/send. No further
   input retry/bypass. Console and observed app processes are session1 Active;
   exact helper-desktop/rights cause unresolved. Next specific user action:
   restart ChatGPT/Codex desktop app normally while keeping Chrome and N6 open,
   then reassess; this is proposed, not performed or guaranteed.
4. Existing wifi disconnect commits desired=false; saved reconnect requires
   desired=true. No reversible existing CLI-only BLE isolation established.
   No credentials read, settings changes, reset, new firmware, push or cables.
5. P0-04/05 remain incomplete. CP8 BLE1953ms and CP4 image99/100 failures retained;
   no gate waived and no claim of complete implementation. Future installs USB only.


### CP10 - 2026-10-29, Codex: isolated transport candidate and manual Cloud result

- [x] **CP10-PREP-01** Reproduce unsafe ambiguous SPI retry in actual production C; preserve expected failing assertion and prepare a four-file candidate without applying it.
- [x] **CP10-PREP-02** Retain v1 parser race failure, repair candidate, and pass seven actual-C native suites; distinguish fixture failures, modeled behavior and absent physical proof.
- [x] **CP10-CLOUD-01** Record user-reported Cloud version52 response and approximate2.5s; keep image state, instrumented timing and full profile acceptance unconfirmed.

Evidence: [CP10 report and conclusions](../../n6-xip-ota-usb/docs/st67-reliability-transport-candidate-20261029/report.md),
summary.json, candidate-manifest.json, saved actual-C inputs/logs, and
PROPOSED-NOT-APPLIED-spi-fence.patch. No main P0-P7 checkbox was changed.

Conclusions after this group:

1. Local DMA cleanup cannot establish whether the peer accepted earlier TX.
   Candidate stops ambiguous replay, preserves ownership, and uses existing
   coordinated recovery. Explicit rx_stall/zero-wire retry stays distinct.
2. The first candidate published bytes when a fault raced queued receive. The
   retained failing test now passes after a post-receive guard. Seven native
   suites pass; no full scheduler/ISR, ARM/link/runtime or physical acceptance.
3. Existing aggregate RX-queue/header-ACK bounds, underlying OVR cause, full AT
   exactly-once/generation coverage and workload latency remain open. This
   integrity candidate may increase declared recovery outages; no performance
   improvement is claimed. Source unchanged and patch applicability check PASS.
4. User Cloud command/reply and version52 are confirmed as user evidence only;
   about2.5s is not an instrumented sample. Image activity was not separately
   confirmed. Do not repeat version without a specific new diagnostic purpose.
5. P0-04/05 remain incomplete; 4 of46 main tasks checked,42 unchecked. Independent
   next work: AT lifetime/budget inventory and reversible baseline isolation.
   No candidate install before applicable gates. CP4/CP8/CP9 failures retained.
6. No browser action/hardware handle, reset, version53, firmware/security/Wi-Fi/
   pairing change, commit or push. Last verifiedB52/A51 preserved. No new cable
   action or approval block. Generate Code not required for the prepared C patch.


### CP11 - 2026-10-29, Codex: AT timeout and late-response regression

- [x] **CP11-PREP-01** Reproduce a late old OK completing a replacement unscoped command using actual sender/await/callback C; retain failing baseline.
- [x] **CP11-PREP-02** Prepare a one-file ambiguity fence, preserving scoped DNS drain and zero-byte BUSY; pass three native suites and combined CP10/CP11 patch applicability check.
- [x] **CP11-AUDIT-01** Record source lifecycle/budget inventory and reversible baseline-isolation design with remaining physical/collector dependencies.

Evidence: [CP11 report and conclusions](../../n6-xip-ota-usb/docs/st67-reliability-at-timeout-candidate-20261029/report.md),
summary.json, saved actual-C inputs/logs and PROPOSED-NOT-APPLIED-at-timeout-fence.patch.
These preparation checks do not complete main P2 tasks or any hardware gate.

Conclusions after this group:

1. Production generic timeout fences only scoped callers. Native late-response
   model accepted a second command with an old OK (result0, writes2, fence0).
   Candidate rejects it before transmission (result-5, writes1, fence1).
2. Three actual-C suites PASS, including original admission/DNS/epoch/wrap
   boundaries. Candidate does not change budgets or clear genuine fences.
   Full fragmentation, successful-command duplicate terminal ambiguity,
   application exactly-once outcomes and HIL remain open.
3. Source inventory and ST revision86022 support continued receive on busy p;
   no resend/reset is added. Current driver does not treat it as completion;
   a dedicated full-parser/physical test remains required.
4. Settings-preserving BLE-only measurement needs a bounded volatile pause in
   the existing owner or another proven reversible fixture. Current disconnect
   commits desired=false; reconnect soak would need password/settings changes.
   Baseline-test support must be planned explicitly before any installation;
   no gate exception or settings modification was silently made.
5. P0-04/05 and integrated repairs remain incomplete,4/46 main tasks checked.
   No further isolated manual version test is requested; prepare coordinated
   instrumented windows first. B52/A51 is last verified state; no53/build/sign/
   USB install, browser action, hardware handle, cable request, commit or push.


### CP12A - 2026-10-29, Codex: frozen worksheet and existing BLE-only fixture

- [x] **CP12-WORKSHEET-01** Complete P0-05: freeze all numeric workload/acceptance entries before reliability implementation; distinguish retained limits from selected new targets. Full measurements remain open.
- [x] **CP12-DISCOVERY-01** Locate existing APP_DEMO_BLE_ONLY startup profile and settings-preserve guards; no new pause manager is needed.

The CP11 proposed new volatile-pause mechanism is superseded by the existing
APP_DEMO_BLE_ONLY=1 profile. It changes only volatile startup restore intent;
saved Wi-Fi and Cloud settings remain loaded and untouched. Preserve mode queries
NCP auto-connect0 and rejects mismatch without setting it. Native/profile build
and exact post-boot disconnected-state verification are required before V01.

The path is not circular: P0 establishes exact baseline configurations, and this
already-implemented compile-time profile is a P0-01/P0-04 fixture, not a P1 timing
change or P2-P5 repair. P0 exit calls for reproducible measurements with unknowns,
not an already passing reliability fix. Existing CP5/CP10/CP11 repairs remain
unapplied. USB-only installation remains conditional on normal signature, slot,
version, boot/rollback, ownership, configuration and post-install checks; this
record does not bypass any of them. No new NCP/bootloader/Secure installation.

Proposed sequence after preflight: known normal B52 -> inactive-slot BLE-only
baseline variant -> bounded V01 -> next normal-profile signed USB version ->
V02-V04. Build both profile/return artifacts first. Confirm B52 as current before
selecting53/54; verify rollback retention and never reuse a consumed version.
Replacing old inactiveA51 must be explicit: current knownB52 remains protected
during the first update, with exact B52 artifacts retained. Do not claim an old
host package can be reinstalled against anti-rollback after confirmation.

Conclusions: use existing test configuration instead of adding runtime state;
criteria are now concrete,5/46 main tasks checked. The manual version result need
not be repeated by the user. Full Cloud receiver windows remain a separate access
dependency; neither sender counters nor manual estimates replace them.
