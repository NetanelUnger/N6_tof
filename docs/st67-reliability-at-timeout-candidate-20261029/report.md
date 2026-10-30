# CP11: unscoped AT timeout ambiguity

Recorded UTC: 2026-10-29T08:59:22.285263+00:00. **PROPOSED / NOT APPLIED**. Main firmware source unchanged.

## Confirmed native failure and isolated repair

The actual `modem_cmd_send_ext` only fenced missing terminal responses when
`budget_owner` matched the current task. Unscoped callers, including the existing
connect command path, could return timeout, release AT ownership and allow a new
command. The new test runs the actual sender, await function and OK callback.
Its simulated late terminal from the first command produces this baseline result:

`second_result=0 writes=2 late_old_terminal_injected=1 fence=0`

The no-cross-command acceptance assertion FAILS on production C. This is a
deterministic modeled interleaving, not proof that this particular late response
occurred on the board or caused the observed BLE latency.

The one-file candidate fences every written timed command whose terminal is
missing. Only the pre-existing scoped DNS operation may retain its existing
20-second terminal drain. Pre-write admission expiry and explicit zero-byte BUSY
remain local failures; explicit ERROR remains a completed failure, not a reason
to reset the NCP. No deadline, queue, memory size, security or settings changes.

Three actual-C suites PASS: timeout/terminal8 groups, existing admission11, and
existing scoped-budget/DNS14. The successful candidate observation is
`second_result=-5 writes=1 late_old_terminal_injected=0 fence=1`.
Saved generated C, failed baseline and candidate logs, commands and hashes are
adjacent. The inherited native fixture represents semaphore IDs as integers;
its C4047 NULL/pointer comparison warnings are retained. They are not target ARM
compiler results. No full-context build or HIL was run.

The CP10 SPI candidate and this candidate modify different files. A combined
`git apply --check` PASS proves patch applicability, not integrated execution.
The existing scoped DNS timeout/terminal race, stale epoch, tick wrap and raw
command-ambiguity tests pass against the new actual sender. Arbitrary duplicate
terminals after an already successful command, full parser fragmentation/events,
all application generations and exactly-once outcome delivery remain open.

## AT lifecycle inventory: source evidence, not fresh T01 wire capture

| Operation | Current source boundary/budget | Remaining evidence |
|---|---|---|
| Scan | `W61_WiFi_Scan` holds AT through terminal and SCAN_DONE, one6000ms budget; parser lock protects scratch retirement, missing completion fences | Exact T01 order/fragmentation and physical late-event campaign |
| Connect | `W61_WiFi_Connect` calls generic SetExecute with3000ms status budget, then reconnect options on success; connection/IP events are separate | New native missing-terminal defect reproduced; full association timeline and post-timeout outcome need validation |
| DNS | Query parse uses20000ms vendor budget; Cloud overall request budget4500ms can expire earlier; static callback/borrowed pointers retire while terminal drain holds admission | Reused late/race/wrap native tests pass; measured original operation/host correlation still missing |
| Socket send | Existing request wrapper owns total deadline across DNS/open/send; prompt/raw data/terminal owner must survive interruption; explicit terminal failure is distinct from absent boundary | Cross-layer fault injection and outcome delivery under route/epoch changes |
| BLE notify | Existing owner/pump requires correlated notification flow; pending fragment retained on zero-byte BUSY; existing100ms notification attempt policy remains | B52 combined latency1953ms still FAIL; no claimed timing improvement |

[ST SPI specification, revision86022](https://wiki.st.com/stm32mcu/index.php?title=Connectivity:ST67W611M1_spi&oldid=86022)
was rechecked on2026-10-29. It distinguishes acknowledgement/data/terminal
responses and asynchronous reports, and describes `busy p` as ongoing execution.
Local tables do not map `busy p` to a completion: unmatched complete lines are
consumed while the existing waiter continues within its budget. This source
finding is not a full fragmented/interleaved `busy p` native or physical test.
Do not add a resend or reset on that text.

## Baseline isolation dependency

The exact source confirms why current `wifi disconnect` cannot be used as a
settings-preserving BLE-only fixture. `wifi_forget_connection` cancels volatile
intent and calls `AppSettings_DisconnectWifi`; even forget0 commits desired=false.
`wifi_restore_connection` rejects the saved profile while that flag is false.
No credentials were read. The existing reconnect soak likewise uses disconnect,
password input and connection changes, so it is not run under this campaign's
preservation constraint.

A suitable future fixture must use the existing Wi-Fi control worker and a
bounded **volatile** pause token, not a second owner or persistent disconnect:

1. Reject pause while an update/settings transition, recovery or user operation
   owns resources. Snapshot scalar generation/intent only; no credential copy
   or logging on the host. Quiesce Cloud through its existing owner barrier.
2. Have the Wi-Fi worker issue the supported transient disconnect while retaining
   saved and volatile desired connection. Suppress only host restoration during
   the pause; prove actual NCP remains disconnected before measuring. Do not
   silently change NCP autoconnect or other persistent settings if it reconnects.
3. Bound pause by a lease expiry and explicit resume. Resume via the existing
   internal saved-profile restoration path, with generation checks so a newer
   explicit user disconnect wins. Recovery/host death must not strand a pause.
4. Assert settings generation/content unchanged, original route restored, no
   credential exposure, no competing reconnects, and USB/ToF continuity.

This is a design, not implemented, proven or installed. It needs focused tests
for cancellation/expiry/recovery/stale generation and a **baseline-test-only**
USB candidate before V01 can be completed with unchanged settings. P0 currently
gates production repairs but also requires V01; that fixture dependency must be
recorded explicitly in the plan before a test-support installation is selected.
No gate was bypassed here. No physical cable/jumper action is required.

## Conclusions and next gate

1. Independent work found a second concrete lifecycle defect and produced another
   small reviewable candidate; neither relies on another manual version test.
2. CP10/CP11 are preparation. P0-04/05, measured P1 attribution/overhead and formal
   P2-P7 acceptance stay open; main checklist remains4/46. No ARM build, image53,
   signing, install, browser interaction, hardware lease, settings change or push.
3. Next concrete work is the reversible baseline fixture and instrumented Cloud
   receive/control window. The user version result has already proved reachability.
   Asking for another isolated version command would not supply exact counts,
   receive gaps, distributions or a frozen load. No further manual command is
   necessary until those collectors and a coordinated test window are ready.
4. Candidate timeout fencing can expose more declared protocol outages when a
   terminal is truly missing; preserving data integrity does not itself improve
   ordinary service latency or identify the physical SPI OVR cause.
5. No approval denial or uncertain mutation occurred. Generate Code is not
   required for either prepared C-only repair. All historical failures retained.
