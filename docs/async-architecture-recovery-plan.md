# Asynchronous Control-Plane Recovery Plan

Status: `IN_PROGRESS` — resumed 2026-10-03; M5.2 build/source verified,
M5.3 RAM startup and exclusive Cloud/BLE/USB image HIL verified; network
stack high-water, failure latency, endurance and IOC generation remain pending.
Earlier gates remain open.

Repository: `C:\Users\netan\Dropbox\DevelopPersonal\N6\project`

Purpose: restore strict task separation for CLI, BLE, Wi-Fi, Cloud, debug UART,
and recovery handling. This document is the execution source of truth. It does
not authorize unrelated refactoring, commits, pushes, flashing, or provisioning.

## Status convention

- `[ ] PLANNED` — not started.
- `[~] IN_PROGRESS` — currently being implemented.
- `[x] VERIFIED` — implementation and the listed verification both passed.
- `[!] BLOCKED` — cannot continue without a documented external decision or
  hardware state.
- `[-] SKIPPED` — explicitly waived by the user, with a reason recorded here.

For every task:

1. Mark exactly one task `IN_PROGRESS` before editing.
2. Preserve unrelated user changes in the dirty worktree.
3. Make only the changes listed for that task.
4. Run the task's verification.
5. Record the result and only then mark it `VERIFIED`.
6. Do not start the next milestone until the current milestone gate passes.

## Non-negotiable architecture rules

1. A callback or transport producer may copy data to a fixed queue and return;
   it may not execute a long operation.
2. The CLI task parses input and routes messages. It never waits for Wi-Fi,
   Cloud, BLE transmission, USB transmission, or physical UART transmission.
3. Every asynchronous request contains `request_id`, source transport, and
   source session generation. Results are routed only to that exact source.
4. BLE event processing and BLE TX pumping are not performed by a task that can
   wait for Wi-Fi association, DHCP, DNS, TLS, or a socket operation.
5. Debug UART has one TX owner task. Producers never transmit directly after
   asynchronous logging has started.
6. Every queue has fixed capacity, non-blocking producers, high-water and drop
   counters, and a documented full-queue policy.
7. `TX_WAIT_FOREVER` is allowed only for a dedicated consumer waiting for its
   own input queue. It is forbidden in CLI handlers, callbacks, fanout code, and
   transport producer APIs.
8. Task priorities are not a substitute for removing blocking calls.
9. Increasing a timeout or queue size alone is not an architectural fix.
10. A task reports progress and operation deadlines. A separate supervisor,
    followed by the hardware watchdog, detects a task that is stuck.
11. No dynamic allocation is introduced after initialization.
12. Secrets are copied only into owned request storage and are cleared as soon
    as the Wi-Fi operation consumes them.

## Target architecture

```text
USB/BLE/Cloud RX
       |
       v
CLI task -- request + route + generation + request_id --> service queue
   ^                                                        |
   +-- transport TX queue <-- result + exact route ----------+

BLE task        events, advertising and BLE TX/RX only
Wi-Fi task      scan/connect/disconnect only
Cloud task      DNS/TLS/socket/protocol only
Debug UART task sole owner of USART1 TX
System bus task non-blocking system-message fanout
Supervisor task heartbeat validation and reset policy
```

## Global completion criteria

- BLE and USB `debug ping` round-trip latency is `p95 < 250 ms` while idle.
- During a failed Wi-Fi connection attempt, `debug ping`, `help`, and
  `radio status` continue to respond.
- The Radio/BLE loop has no gap over 500 ms; the normal target is below 100 ms.
- A Wi-Fi result is delivered only to the session that submitted it.
- A reconnected BLE/USB/Cloud client cannot receive a stale result from an old
  session generation.
- Debug UART producers do not wait for physical USART transmission.
- Cloud DNS/TLS/socket failures do not stop CLI or the BLE pump.
- A transient VL53L9CX communication failure recovers locally and complete,
  valid ToF frames resume without a whole-system reset.
- Every required task has a heartbeat/deadline contract.
- A deliberately stalled critical task leads to a reset with a preserved
  reason.
- The final clean Secure and NonSecure builds pass.
- The final HIL soak completes with no missing control-plane responses and no
  unexplained reset.

## Standard verification commands

Run commands from the repository root.

```powershell
# Fast source-level build after a NonSecure source change
powershell -ExecutionPolicy Bypass -File .\Tools\Build-NonSecureIncremental.ps1

# HIL/CLI scripts (arguments may be added by the implementing task)
python .\hil_tests\self_test.py
python .\hil_tests\ble_inspector.py --help

# RAM debug/programming is permitted only when the active task explicitly
# reaches a HIL gate and the user has made the board available.
powershell -ExecutionPolicy Bypass -File .\Tools\Debug-NonSecureRam.ps1 -Run
```

After `N6.ioc`, TrustZone, Secure, or generated-project changes, perform the
repository's documented clean Secure and NonSecure build. Do not sign, package,
provision, flash persistent storage, commit, or push unless separately
authorized.

---

# Milestone 0 — Reproduce and measure the failure

Goal: create deterministic latency measurements before changing scheduling.

## [x] VERIFIED M0.1 — Add a transport-only ping command

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
- Functions:
  - `cli_command_debug()`
  - `cli_show_help()`
- Change:
  - Add `debug ping <token>`.
  - Reply exactly once with `PONG <token> <HAL_GetTick()>`.
  - Do not call W6X, Cloud, ToF, display, or USBX control APIs.
  - Keep the command available through USB, BLE, and Cloud CLI sessions.
- Acceptance:
  - The token is returned unchanged through every connected CLI transport.
  - The command has no dependency on radio state beyond the BLE transport
    itself.
- Verification:
  - Run the incremental NonSecure build.
  - Manually issue at least ten sequential pings over an available transport.

## [x] VERIFIED M0.2 — Record Radio/BLE loop gaps

- Files:
  - `AppliNonSecure/Core/Inc/wifi_ble_app.h`
  - `AppliNonSecure/Core/Src/wifi_ble_app.c`
- Functions/types:
  - `WifiBle_RuntimeStatus_t`
  - `WIFI_BLE_App_Run()`
  - `WIFI_BLE_App_GetRuntimeStatus()`
- Change:
  - Add `loop_count`, `last_loop_tick`, `max_loop_gap_ticks`,
    `last_ble_tx_tick`, and `max_ble_tx_gap_ticks`.
  - Update counters without logging from the hot loop.
  - Expose them through the existing radio status command.
- Acceptance:
  - Status output shows whether a Wi-Fi or Cloud operation suspended the BLE
    pump.
- Verification:
  - Incremental NonSecure build.
  - Compare idle gap with the gap during a deliberately failed Wi-Fi connect.

## [x] VERIFIED M0.3 — Add an automated latency probe

- Files:
  - `hil_tests/ble_inspector.py`
- Functions to add:
  - `run_latency_probe()`
  - `run_wifi_blocking_probe()`
- Change:
  - Send numbered pings every 200 ms.
  - Record minimum, p50, p95, maximum, missing replies, and reconnects.
  - Add a scenario that starts an invalid Wi-Fi connection while pings remain
    active.
  - Return a nonzero exit code on a missing reply or `p95 > 250 ms`.
- Acceptance:
  - The current failure can be reproduced and its raw result is saved.
- Verification:
  - `python .\hil_tests\ble_inspector.py --help`
  - Run the probe against available hardware and record the baseline below.
- Result record:
  - Date: 2026-09-20
  - Firmware revision: 5 (RAM-loaded development image)
  - COM8 idle: 50/50 replies, p95 16.4 ms, maximum 27.0 ms
  - COM8 Wi-Fi failure: 225/225 replies, p95 988.5 ms, maximum 3165.8 ms
  - Radio/BLE maximum loop gap: 33 ticks idle, 3151 ticks during the failed
    Wi-Fi connection
  - Deferred BLE check: Windows discovered the connectable
    `N6-MAINT-B8FB` advertisement, but WinRT returned `E_FAIL` before GATT
    discovery. This is not a Milestone 1 blocker; the final BLE acceptance
    conditions remain open and must be revisited before program completion.

### Milestone 0 gate

- [x] Ping command builds and responds.
- [x] Radio/BLE maximum loop gap is visible.
- [x] A baseline latency report is recorded, or the milestone is marked blocked
  specifically because hardware is unavailable.

---

# Milestone 1 — Asynchronous Debug UART

Goal: make physical USART1 transmission owned by one task and keep every log
producer bounded and non-blocking.

## [x] VERIFIED M1.1 — Define the asynchronous UART API

- Files:
  - `AppliNonSecure/Core/Inc/debug_uart.h`
  - `AppliNonSecure/Core/Inc/logging_config.h`
- Functions/types to add:
  - `Debug_UART_AsyncInitialize()`
  - `Debug_UART_TaskRun()`
  - `Debug_UART_TestTaskRun()`
  - `Debug_UART_StartTest()`
  - `Debug_UART_Flush()`
  - `Debug_UART_GetStatus()`
  - `Debug_UART_EmergencyWrite()`
  - `Debug_UART_IRQHandler()`
  - `DebugUart_Status_t`
- Change:
  - Define queue/sent/drop/timeout/HAL-error/high-water counters, separate
    pool-exhaustion/contention/oversize/context/transport/internal counters,
    and asynchronous diagnostic state/results.
  - Retain the synchronous startup/fault API for use before ThreadX is ready.
- Acceptance:
  - Existing callers compile before their implementation is migrated.
- Verification:
  - Incremental NonSecure build.

## [x] VERIFIED M1.2 — Create fixed UART slots and pointer queues

- Files:
  - `AppliNonSecure/Core/Src/debug_uart.c`
- Functions:
  - `Debug_UART_AsyncInitialize()`
  - private queue/slot helpers
- Change:
  - Use 32 fixed slots of 512 bytes. Hardware review showed the original
    16-slot pool reached high-water 16 and dropped nine startup messages.
  - Create free and ready pointer queues during initialization.
  - Producers acquire and enqueue with `TX_NO_WAIT`.
  - A producer owns a linked chain of fixed slots and publishes one message
    head, preserving multi-slot boundaries without a producer mutex.
  - An arbitrary write is either admitted into all required slots or rejected;
    never enqueue a silent partial message.
  - Track high-water, pool-exhaustion, contention, and oversize counters
    separately. The contention counter remains visible and must stay zero
    because the producer mutex was removed.
- Acceptance:
  - No allocation occurs after initialization.
  - A full queue returns immediately.
  - A normal cold boot finishes with zero drops and zero queue-full events.
- Verification:
  - Incremental build and linker-map memory review.
  - Preserve the documented application-pool safety margin.

## [x] VERIFIED M1.3 — Implement the sole UART TX owner

- Files:
  - `AppliNonSecure/Core/Src/debug_uart.c`
- Functions:
  - `Debug_UART_TaskRun()`
  - private TX start/completion helpers
- Change:
  - Wait on the ready queue.
  - Start `HAL_UART_Transmit_IT()`.
  - Wait for a completion/error event with a timeout derived from message
    length, 115200 baud, and a bounded margin.
  - On timeout, abort TX, update counters, release the slot, and continue.
  - Report repeated failures to the health module once that module exists.
- Acceptance:
  - No normal post-RTOS path calls blocking `HAL_UART_Transmit()`.
- Verification:
  - Incremental build.
  - Burst-test at least 100 formatted lines and inspect ordering/counters.

## [x] VERIFIED M1.4 — Wire USART1 interrupt completion

- Files:
  - `AppliNonSecure/Core/Inc/stm32n6xx_it.h`
  - `AppliNonSecure/Core/Src/stm32n6xx_it.c`
  - `AppliNonSecure/Core/Src/debug_uart.c`
- Functions:
  - `USART1_IRQHandler()`
  - `Debug_UART_IRQHandler()`
  - `HAL_UART_TxCpltCallback()`
  - `HAL_UART_ErrorCallback()`
  - `Debug_UART_Init()`
- Change:
  - Enable USART1 NVIC handling.
  - Route the handler to `HAL_UART_IRQHandler()` via the debug UART module.
  - HAL callbacks only signal an event; no formatting or copying in ISR.
  - Do not allocate a GPDMA channel for USART1.
- Acceptance:
  - Interrupt completion advances the queue.
- Verification:
  - Incremental build.
  - HIL burst confirms multiple consecutive lines complete.

## [x] VERIFIED M1.5 — Create the debug UART task early

- Files:
  - `AppliNonSecure/Core/Src/app_threadx.c`
- Functions:
  - `App_ThreadX_Init()`
  - new `DebugUartThread_Entry()`
- Change:
  - Initialize queues before creating application producers.
  - Create the task at initial priority 5 with a 2048–3072 byte stack. This
    keeps its short queue-service work above continuously-ready application
    producers while it sleeps during physical transmission.
  - Keep startup writes synchronous until asynchronous initialization completes.
  - Create a separate 3072-byte priority-9 diagnostic task. CLI commands only
    signal this task; pacing and drain waits never execute in the CLI task.
- Acceptance:
  - Early boot traces remain visible and later traces use the queue.
- Verification:
  - Incremental build.
  - Inspect ThreadX stack high-water after startup and UART stress.

## [x] VERIFIED M1.6 — Migrate all runtime log output

- Files:
  - `AppliNonSecure/Core/Src/debug_uart.c`
  - `AppliNonSecure/Core/Src/st67w6x_logging.c`
  - `AppliNonSecure/Core/Src/wifi_ble_app.c`
- Functions:
  - `Debug_UART_Write()`
  - `Debug_UART_Log()`
  - `log_output()`
- Change:
  - Use polling only before async initialization or through the explicit
    emergency API.
  - After the queue owner activates, queue only.
  - Give concurrent ST67 messages one of four fixed formatting buffers with
    `TX_NO_WAIT`; expose buffer-exhaustion/ISR/format counters and do not use a
    shared formatting mutex.
  - Protect every Debug UART counter update and copy all counters in one
    interrupt-bounded status snapshot.
- Acceptance:
  - Runtime producers return without waiting for USART transmission.
  - ST67 formatting-buffer exhaustion or ISR rejection is visible through a
    dedicated counter rather than silently disappearing.
- Verification:
  - `rg -n "HAL_UART_Transmit\(" AppliNonSecure`
  - Review every remaining match as startup/emergency-only.
  - Incremental build and UART stress.

### Milestone 1 gate

- [x] UART line ordering is preserved.
- [x] Producers do not block on physical TX.
- [x] No drops occur during the agreed burst test.
- [x] Overflow is observable through counters rather than a system stall.

---

# Milestone 2 — Stable source and session identity

Goal: make asynchronous replies independent of the global active CLI session.

## [x] VERIFIED M2.1 — Introduce transport routes and request IDs

- Files:
  - new `AppliNonSecure/Core/Inc/app_route.h`
- Types:
  - `AppTransport_t`
  - `AppRoute_t`
  - `AppRequestId_t`
- Change:
  - Define USB, BLE, Cloud, and System transport identifiers.
  - A route contains transport and session generation, never a session pointer.
- Acceptance:
  - The header has no Menu, USBX, W6X, or ThreadX implementation dependency.
- Verification:
  - Incremental build after inclusion by one compile unit.

## [x] VERIFIED M2.2 — Add generation to every CLI session

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
- Functions/types:
  - `CliSession_t`
  - `cli_session_reset()`
- Change:
  - Add `AppRoute_t route`.
  - Increment generation on reset/reconnect for USB, BLE, and Cloud.
  - Never retain `CliSession_t *` in a cross-task request.
  - USB starts at generation 1 and advances when its CLI session is reset at
    disconnect, so the next host attachment receives a new generation.
  - BLE uses the existing `runtime.ble_session_generation` connect/disconnect
    epoch, normalized so zero is never exposed, and resets the parser only once
    when synchronizing to a changed runtime epoch.
  - Cloud uses `CloudRelay_Status_t.generation + 1` as its non-zero route epoch.
    The existing Cloud implementation advances that source only after a
    successful pair, an explicit reconnect/test request, or unpair. Transient
    HTTP socket close/backoff and enable/disable do not define a new CLI session
    and therefore do not change the CLI route generation.
  - `cli_route_is_current()` compares a saved route with the current route by
    transport and non-zero generation so old asynchronous ownership can be
    rejected after a session reset.
- Acceptance:
  - A stale route is detectable after reconnect.
- Verification:
  - Incremental build and reconnect test.

## [x] VERIFIED M2.3 — Move pending Wi-Fi credentials into the session

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
- Functions/types:
  - `CliSession_t`
  - `cli_command_wifi()`
  - `cli_wifi_connect_password()`
  - `cli_session_reset()`
- Change:
  - Remove global `cli_pending_ssid` and global password-prompt ownership.
  - Store pending SSID and password-input state per session.
  - Clear credentials on cancellation, submission, disconnect, and reset.
  - Full-capacity SSID and password buffers are scrubbed on success, every
    failure return, Ctrl-C, input overflow, prompt-send failure, transport
    reset/disconnect, and an explicit Wi-Fi disconnect command.
  - SSID-bearing `wifi connect` commands are not retained in history.
  - `debug route` exposes a startup diagnostic using the real reset/clear
    helpers to check generation advance, stale-route detection, independent
    USB/Cloud SSIDs, and session-scoped cancel/reset cleanup.
- Acceptance:
  - Simultaneous USB/BLE connect flows cannot overwrite one another.
- Verification:
  - Incremental build.
  - Interleave the SSID/password flow from two transports.

### Milestone 2 gate

- [x] Every asynchronous source has transport plus generation.
- [x] No global pending SSID remains.
- [x] No cross-task message stores a `CliSession_t *`.

Hardware evidence: after a real USB session reset/reconnect, `debug route`
reported `current=USB/2 usb=2 cloud=1`, `ble=1`, and all five focused diagnostic
fields as `pass`. This confirms non-zero generations for USB, BLE, and Cloud,
the observed USB generation change, stale-route rejection, credential
isolation, and session-scoped cancel/reset cleanup.

---

# Milestone 3 — Dedicated Wi-Fi worker and non-blocking CLI

Goal: isolate long Wi-Fi waits in a task whose only responsibility is Wi-Fi
control.

## [x] VERIFIED M3.1 — Define owned Wi-Fi request and result messages

- Files:
  - `AppliNonSecure/Core/Inc/wifi_ble_app.h`
- Types:
  - `WifiBle_WifiOperation_t`
  - `WifiBle_WifiRequest_t`
  - `WifiBle_WifiResult_t`
- Change:
  - Include operation, request ID, route, SSID/password/forget arguments.
  - Include final status, Wi-Fi status snapshot, and bounded scan results.
  - Do not store caller-owned pointers.
- Acceptance:
  - Each message owns all data needed after the caller returns.
- Verification:
  - Incremental build.

## [x] VERIFIED M3.2 — Add fixed Wi-Fi request/result slots and queues

- Files:
  - `AppliNonSecure/Core/Src/wifi_ble_app.c`
- Functions:
  - `wifi_control_initialize()`
  - private request/result slot helpers
- Change:
  - Create exactly four request slots and four result slots in the one-time
    SRAM4 Wi-Fi control allocation.
  - Create request-free/request-ready/result-free/result-ready `TX_1_ULONG`
    pointer queues with four-entry fixed storage.
  - Private acquire/publish/receive/release helpers use `TX_NO_WAIT`; acquire
    maps free-pool exhaustion to `TX_QUEUE_FULL`.
  - Release scrubs the complete owned request or result before returning its
    slot. The M3.4 worker will additionally scrub the request password as soon
    as the W6X connect call consumes it.
  - Retain the original event-based single-operation fields and blocking path
    as explicitly labeled transitional state until M3.4/M3.10.
- Acceptance:
  - The initialization self-test exhausts each four-slot pool, observes
    `TX_QUEUE_FULL` on the fifth acquire, verifies distinct pointers and full
    release scrubbing, traverses both ready queues, and restores
    `free=4, ready=0`; any failure rolls initialization back.
- Verification:
  - Incremental build and build-armed initialization self-test.
  - Static review of all new queue sends/receives and every initialization
    rollback stage.
  - DWARF reports `sizeof(WifiBle_WifiControlContext_t) == 5648`, leaving 496
    bytes inside its explicit 6 KiB budget. The increase over the previous
    1072-byte context is 4576 bytes; against the latest measured 21056-byte
    final radio-pool margin, the unchanged-allocation projection is 16480
    bytes. This projection is not a new HIL measurement; initialization logs
    the live pool value to Debug UART.

## [x] VERIFIED M3.3 — Expose non-blocking submit/result APIs

- Files:
  - `AppliNonSecure/Core/Inc/wifi_ble_app.h`
  - `AppliNonSecure/Core/Src/wifi_ble_app.c`
- Functions:
  - new `WIFI_BLE_App_WifiSubmit()`
  - new `WIFI_BLE_App_WifiReceiveResult()`
- Change:
  - Submit validates operation, transport, non-zero route generation, bounded
    SSID/password termination, non-empty connect SSID, and disconnect `forget`.
  - Submit acquires without waiting, assigns a monotonically increasing
    non-zero request ID with wrap to 1, copies only operation-relevant owned
    fields, publishes, and returns. A failed publish scrubs and releases the
    request slot before returning.
  - Receive returns `TX_QUEUE_EMPTY` without waiting when no result exists;
    otherwise it copies the complete result and immediately scrubs/releases
    its slot.
  - The ID critical section contains only increment, zero-wrap correction, and
    publication of the new counter value.
- Acceptance:
  - Neither public API waits for a Wi-Fi event, sleeps, polls, or retries.
- Verification:
  - Incremental build, declaration/implementation `rg`, and focused source
    review of both functions and their queue helpers.

## [x] VERIFIED M3.4 — Implement the Wi-Fi control task loop

- Files:
  - `AppliNonSecure/Core/Src/wifi_ble_app.c`
- Functions:
  - new `WIFI_BLE_App_WifiControlRun()`
  - replace `wifi_process_pending_request()` with private
    `wifi_execute_request()`
- Change:
  - Wait for radio-ready before receiving requests.
  - Execute scan/connect/disconnect only in this task.
  - Publish a routed result for every accepted request, including timeout and
    failure.
  - The task may block inside the vendor high-level API because it owns no BLE
    or CLI responsibility.
  - Preserve the blocking APIs as a transitional adapter: they signal the same
    control loop, while the owned queue path publishes one independent result
    for every dequeued request.
  - Scrub the queued connect password immediately after copying it into the
    stack-local W6X options, before entering the blocking vendor call; scrub the
    vendor options immediately after that call returns.
- Acceptance:
  - `WIFI_BLE_App_Run()` never performs a high-level Wi-Fi operation.
- Verification:
  - Incremental build.
  - Focused source audit proving that scan/connect/disconnect call sites occur
    only in `wifi_execute_request()`, and that the radio loop neither calls that
    executor nor any of the three high-level W6X operations.
  - Focused source audit of radio-ready/work waits, request/result ownership,
    timeout/failure snapshots, result publication, and password-scrub ordering.

## [x] VERIFIED M3.5 — Create the Wi-Fi worker thread

- Files:
  - `AppliNonSecure/Core/Src/app_threadx.c`
- Functions:
  - `App_ThreadX_Init()`
  - new `WiFiControlThread_Entry()`
- Change:
  - Initial priority 11 and stack size 6144 bytes.
  - Wait for explicit radio-ready signaling before accessing W6X.
  - Allocate the stack from the dedicated SRAM4 radio pool and create the
    worker with `TX_NO_TIME_SLICE` and `TX_AUTO_START`.
  - Keep the entry point limited to `WIFI_BLE_App_WifiControlRun()`; the entry
    contains no direct vendor call.
- Acceptance:
  - Wi-Fi connect runs on a different ThreadX thread from BLE processing.
- Verification:
  - Incremental build, linker-map SRAM4 contract, live thread identity at a
    `W6X_WiFi_Connect` breakpoint, and stack high-water inspection after the
    failed-connect path.

## [x] VERIFIED M3.6 — Make Wi-Fi scan submission-only in CLI

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
- Functions:
  - `cli_wifi_scan()`
- Change:
  - Submit the request and print its request ID.
  - Remove the 30-second wait and local scan-result ownership.
  - Copy the active CLI session route into a zeroed stack-owned request and
    return immediately after `WIFI_BLE_App_WifiSubmit()` accepts or rejects it.
  - Leave result reception and network-list formatting to M3.9.
- Acceptance:
  - The CLI loop returns immediately after accepting the command.
- Verification:
  - Incremental build, focused source audit, RAM execution, prompt timing, and
    continuous ping during scan.
  - Compare the radio-pool baseline with first and repeated scans. Account
    separately for the vendor driver's existing lazy scan-result allocation;
    M3.6 itself must add no SRAM4 storage or allocation.

## [ ] IMPLEMENTED M3.7 — Make connect submission-only in CLI (targeted transport fixes landed; repeatability gate open)

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
- Functions:
  - `cli_wifi_connect_password()`
- Change:
  - Build a zeroed, fully owned CONNECT request on the stack from the current
    session route, SSID, and hidden password.
  - Submit, scrub the complete stack request immediately, report the request ID
    or ThreadX rejection, and return without waiting.
  - Keep the caller's unconditional full-capacity session credential scrub
    after the function returns, including submission failure.
  - Remove the 35-second wait, blocking connect call, status query, and final
    association/DHCP output; M3.9 will present the routed result.
- Acceptance:
  - USB remains interactive during association/DHCP failure: passed on RAM HIL.
  - BLE remains interactive during association/DHCP failure: not accepted yet.
    The direct-parser livelock and an unbounded failed raw-write loop were
    corrected, and two new complete probes passed with 222/222 replies and
    p95 148.352/152.370 ms. An intervening fresh-RAM run connected but did not
    publish its initial CLI prompt; COM6 then showed repeated SPI
    transaction-ready timeouts. Repeatability is required, so successful runs
    on either side of that transport failure do not close the gate.
  - Targeted SPI transaction-ready recovery is implemented, but the required
    five consecutive clean RAM boots have not passed. The latest polling-header
    build had one complete BLE/USB/reconnect pass followed by an intermittent
    BLE first-reply failure on the next clean boot; M3.7 remains unverified.
- Verification:
  - Incremental build, focused source audit, fresh RAM execution, immediate
    prompt timing, concurrent USB pings, radio-loop gap and SRAM4 comparison.
  - Manual `--pair --uncached-services` HIL connected at MTU 247, enumerated the
    N6 CLI/DEBUG/ToF GATT contract, disconnected cleanly, and the firmware
    restarted advertising.
  - The exact 45-second BLE blocking probe then passed once with 225/225
    replies, zero missing replies, p50 131.173 ms, p95 162.088 ms, maximum
    507.848 ms, and no reconnect. Eighteen concurrent USB pings also passed in
    15.2..31.6 ms; the measured radio-loop maximum gap was 430 ticks, far below
    the Milestone-0 blocking value of 3151 ticks.
  - A fresh-RAM repeat connected at MTU 23 but failed after 21/75 replies
    (54 missing, p50 155.136 ms, p95 239.496 ms, maximum 253.811 ms). Hot-plug
    GDB found no Cortex fault and showed the priority-2 `Modem_Process` thread
    repeatedly parsing the same malformed/truncated `+BLE:GATTWRITE` direct
    event. `cmd_handler_process_rx_buf()` does not consume, drop, break, or
    yield when a direct handler returns a negative error other than `-EAGAIN`;
    the radio-loop counter remained unchanged across samples, BLE state stayed
    falsely connected, advertising stayed off, and COM8 timed out. The saved
    report is `hil_tests/results/m37_ble_wifi_blocking_20260921.json` (SHA-256
    `69921952016CF07FDB5BF4B86D2592010BCB256698CC5CE8F4CDFF55471CFCE4`).
  - Early default-mode GDB attaches reset the target into BootROM and are
    discarded as evidence. Only subsequent `--attach`/Hot Plug snapshots are
    used for the live-livelock diagnosis. All firmware reloads were RAM-only;
    external NOR was not changed.
  - Targeted follow-up hardened the vendor direct-command loop to stop and
    scrub malformed input, taught `W61_Ble_Data_Event()` to return `-EAGAIN`
    for partial numeric fields, and made the raw-data send loop abort and
    release `sem_tx_lock` when the SPI write returns zero, a negative error, or
    an impossible over-count. The BLE probe now waits for the real initial
    prompt, uses one short outstanding token at a time, and records a missing
    reply rather than creating an artificial write backlog.
  - Post-fix fresh-RAM report
    `hil_tests/results/m37_final_run20_bus_progress.json` passed 222/222,
    zero missing, p50 115.226 ms, p95 148.352 ms, maximum 508.491 ms, and zero
    reconnects (SHA-256
    `E495CBE3AAF0F12621165EBBE9E4C96E1AE02E7E9B42CC4F67E8F34E97DDCB9D`).
  - The immediately following fresh-RAM report
    `hil_tests/results/m37_final_run21_bus_progress_repeat.json` failed before
    the latency phase because the connected BLE CLI did not publish its
    initial prompt; no Wi-Fi request was submitted. COM6 captured repeated
    `spi_iface.c:606 waiting for spi txn ready timeouted` messages. A Hot Plug
    snapshot found no Cortex fault: application/ToF execution and the radio
    loop were live, and the firmware later received the host disconnect and
    resumed advertising. The report SHA-256 is
    `D5207C87F9A9A3126E40CC93D60706FBCC97C62A9EB458A689402CE41836C9DF`.
  - A third fresh-RAM report
    `hil_tests/results/m37_final_run22_bus_progress_usb.json` passed 222/222,
    zero missing, p50 94.774 ms, p95 152.370 ms, maximum 489.236 ms, and zero
    reconnects while 24/24 concurrent USB probes passed with p95 30.6 ms and
    maximum 31.5 ms. Final status showed zero BLE CLI RX/TX drops, retries, or
    errors, 3,184 radio-pool bytes available, and `max_gap_ticks=390` versus
    the Milestone-0 failure value of 3151. Its SHA-256 is
    `B853D212A264BFA178AA0F5ED9D1CB08568ACD9D8D66100F02FEFC0399C4D843`.

## [x] VERIFIED M3.8 — Make disconnect submission-only in CLI

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
- Functions:
  - `cli_command_wifi()`
- Change:
  - Submit disconnect/forget as a routed request.
  - Remove the 10-second wait.
- Acceptance:
  - CLI input is processed immediately after disconnect submission on USB and
    BLE. The final operation result is intentionally not printed until M3.9.
- Verification:
  - Incremental build and USB/BLE ping/disconnect HIL passed on one clean RAM
    boot; this does not waive the separate open M3.7 5/5 BLE gate.

## [x] IMPLEMENTED M3.9 — Route completed Wi-Fi results (USB/BLE HIL; Cloud HIL deferred)

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
- Functions:
  - `Debug_CLI_Run()`
  - new `cli_poll_wifi_results()`
- Change:
  - Drain a bounded number of results per CLI iteration with `TX_NO_WAIT`.
  - Match transport and generation.
  - Print only to the initiating session.
  - Count and discard stale results.
  - Defer result text only for its owning session during XMODEM or a hidden
    password prompt. Copy up to four blocked results into a fixed CLI mailbox
    so worker result slots are released and other transports keep draining;
    count any mailbox overflow explicitly in `debug route`.
  - Keep an asynchronous Cloud Wi-Fi request ID bound to its leased Relay
    command. The ACK atomically arms a Relay hold, so an ACKed command cannot
    be replaced by another poll before its result. Do not enqueue the Cloud
    completion marker until the matching
    result has been written to that same command; clear the binding on a
    Cloud generation change. Do not read a new Cloud command while pending.
    The result uses one compact, nonblocking Relay output record containing
    operation, request ID, final status, scan count and IPv4; the full AP list
    remains on USB/BLE. Retry that Cloud record in the CLI-owned mailbox when
    its four-slot output queue is full, without stalling other transports.
- Acceptance:
  - USB and BLE requests never receive one another's result: passed on RAM HIL.
  - A result from a disconnected USB/BLE generation is released and counted as
    stale rather than sent to its successor: passed on RAM HIL.
- Verification:
  - Incremental build, simultaneous two-transport test, >4 sequential requests,
    BLE reconnect, USB-close, and XMODEM text-isolation tests passed in the
    original M3.9 run. The focused follow-up repeated USB/BLE isolation and
    confirmed each transport still receives results while the other waits for
    a hidden password. Cloud end-to-end remains unverified: RAM HIL reported
    `waiting for Wi-Fi, not paired`. The M3.7 five-boot BLE gate remains open.

## [x] BUILD/HIL VERIFIED M3.10 — Delete the blocking application API

- Files:
  - `AppliNonSecure/Core/Inc/wifi_ble_app.h`
  - `AppliNonSecure/Core/Src/wifi_ble_app.c`
- Functions to remove after caller migration:
  - `WIFI_BLE_App_WifiScan()`
  - `WIFI_BLE_App_WifiConnect()`
  - `WIFI_BLE_App_WifiDisconnect()`
  - obsolete event-wait completion plumbing
- Acceptance:
  - `rg` finds no application caller of a blocking Wi-Fi control API.
- Verification:
  - Incremental build passed and `rg -n
    "WIFI_BLE_App_Wifi(Scan|Connect|Disconnect)" AppliNonSecure/Core/Inc
    AppliNonSecure/Core/Src` found no blocking API declaration, definition or
    caller. The worker's bounded scan-completion event remains necessary; only
    the obsolete caller-facing done flag/state were removed. RAM HIL exercised
    six sequential USB submissions plus concurrent USB/BLE commands.

### Milestone 3 gate — OPEN (M3.7 BLE repeatability not accepted)

- [x] CLI has no Wi-Fi wait; scan/connect/disconnect now submit and return.
- [ ] BLE loop remains active throughout a failed connection.
- [x] Result origin and generation tests pass for USB/BLE on RAM HIL (M3.9).
- [ ] The blocking probe reaches the latency target or records a remaining
  vendor-lock delay for Milestone 4.

---

# Milestone 4 — Bound W61 command-lock waits

Goal: prevent a BLE notification from waiting forever behind Wi-Fi or Cloud AT
traffic.

## [ ] IMPLEMENTED / HIL FAILED M4.1 — Bound the generic modem command TX lock

- Files:
  - `ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c`
- Functions:
  - `modem_cmd_send_ext()`
- Change:
  - Replace `portMAX_DELAY` when taking `sem_tx_lock` with the supplied timeout.
  - Measure elapsed ThreadX ticks from before lock acquisition through the
    command write; pass only the remaining operation budget to the reply wait.
  - Return `-ETIMEDOUT` when the mutex is unavailable.
  - Track whether the lock was acquired and only then release it.
- Acceptance:
  - A call's timeout includes time waiting for the shared AT channel.
- Verification:
  - Incremental build passed. Two concurrent 45-second BLE/Wi-Fi RAM probes
    failed the BLE latency requirement (18/19 and 15/16 replies; p95 263.543
    and 262.771 ms). Both concurrent USB series passed 24/24. Keep M4.1 HIL
    acceptance open; do not attribute the remaining failures solely to this
    generic lock while M4.2+ manual locks and M3.7 remain unverified.

## [x] IMPLEMENTED / FOCUSED HIL PASS M4.2 — Bound manual common-command locks

- Files:
  - `ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c`
- Functions:
  - `W61_AT_Common_Query_Parse()`
  - `W61_AT_Common_RequestSendData()`
- Change:
  - Convert the operation's `timeout_ms` to ThreadX ticks and use it for both
    manual mutex acquisitions. Query/Parse passes only the remaining budget
    after acquisition to its response wait.
  - Do not modify shared receive pointers until the mutex is held.
  - Return `W61_STATUS_TIMEOUT` on acquisition failure.
  - Release the mutex only on paths that acquired it.
- Acceptance:
  - Neither function waits indefinitely.
- Verification:
  - Incremental build and source review passed. A full 45-second RAM probe
    during failed Wi-Fi connect returned 221/221 BLE replies, zero missing,
    p95 169.995 ms and zero reconnects; concurrent USB pings passed 24/24.
    This is one focused probe, not the open M3.7 five-boot acceptance run.
    ToF initialization was in error (-5) on that RAM boot, so this does not
    establish the full-system load/soak gate.

## [x] IMPLEMENTED / FOCUSED HIL PASS M4.3 — Audit BLE manual locks

- Files:
  - `ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_ble.c`
- Functions:
  - every function that manually takes `sem_tx_lock`
- Change:
  - Use the caller-supplied or explicit bounded operation timeout.
  - Notification timeout includes lock acquisition.
  - The three manual GATT service, characteristic, and bonded-list queries
    use the explicit 2000 ms NCP budget. They check lock acquisition before
    touching modem response state and pass only the remaining ticks to the
    response wait; only an acquired lock is released.
  - The notification no longer raises the caller's 100 ms budget to the
    2000 ms BLE default. The shared request-send path subtracts elapsed time
    from that budget before the command, prompt and final response waits.
    This small common-path change is necessary to make notification lock time
    count toward its actual caller-supplied deadline; it also bounds the
    other users of that shared send path.
- Acceptance:
  - No runtime BLE path uses an infinite TX-lock wait.
- Verification:
  - Incremental build passed; `rg -n "sem_tx_lock.*portMAX_DELAY"` on the BLE
    file returned no match. A complete 45-second RAM BLE/Wi-Fi probe returned
    223/223 replies, zero missing, p95 152.095 ms and zero reconnects; USB
    pings passed 24/24. BLE TX recorded zero drops but one retry/error.
    The same boot reported a separate ToF error (-5/-1); this is not a
    full-system soak or M3.7 five-boot verification.

## [x] IMPLEMENTED / BUILD PASS M4.4 — Audit Wi-Fi manual locks

- Files:
  - `ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_wifi.c`
- Functions:
  - every function that manually takes `sem_tx_lock`
- Change:
  - Use a bounded timeout and verify acquisition before touching shared state.
- Acceptance:
  - No runtime Wi-Fi path uses an infinite TX-lock wait.
- Verification:
  - Incremental build passed. The three manual acquisitions in
    `W61_WiFi_GetCredentials`, `W61_WiFi_AP_ListConnectedStations`, and
    `W61_WiFi_TWT_GetStatus` now use the 2000 ms NCP budget, return timeout
    before mutating response state on acquisition failure, and pass only
    remaining ticks to `modem_cmd_send_ext`.

## [x] IMPLEMENTED / BUILD PASS M4.5 — Audit Network and System manual locks

- Files:
  - `ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_net.c`
  - `ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_sys.c`
- Functions:
  - every function that manually takes `sem_tx_lock`
- Change:
  - Replace unbounded waits with explicit operation timeouts.
  - Initialization may use a longer bound but never infinity.
- Acceptance:
  - No `sem_tx_lock` acquisition in `Driver/W61_at` uses
    `portMAX_DELAY`.
- Verification:
  - Incremental build passed. A small private driver helper returns remaining
    ticks only while the caller owns the lock; zero means timeout/no ownership.
    Network uses the caller's pull-data timeout or the 6000 ms network budget;
    System uses the 2000 ms NCP budget. All six manual acquisitions check it
    before changing `mdm->rx_data` or other shared response state.
  - `rg -n "sem_tx_lock.*portMAX_DELAY" ThirdParty/ST67W6X_Network_Driver/Driver/W61_at`
    returned no matches (exit 1).

## [ ] IMPLEMENTED / HIL MIXED M4.6 — Retry BLE TX without losing the packet

- Files:
  - `AppliNonSecure/Core/Src/wifi_ble_app.c`
  - `AppliNonSecure/Core/Inc/wifi_ble_app.h`
  - `AppliNonSecure/Core/Src/debug_cli.c` (existing `ble status` diagnostic)
- Functions:
  - `ble_stream_process_tx()`
  - `ble_tof_image_process_tx()`
- Change:
  - Treat AT-lock busy/timeout as transient.
  - Keep the active packet and retry on the next loop.
  - Track consecutive busy results and maximum busy duration.
- Acceptance:
  - Short AT contention neither stalls the BLE task nor silently drops the
    active packet.
- Verification:
  - Incremental build, `git diff --check`, Python compileall and HIL utility
    self-test passed. One RAM boot failed W6X_Init before BLE testing; the next
    reached ready. On that image, the first concurrent Wi-Fi/BLE probe failed
    early with 14/15 replies (one missing) despite zero BLE TX drops and two
    transient notification timeouts. A repeat completed 45 seconds with
    222/222 replies, zero missing, while the cumulative timeout counter rose
    to five with two recoveries and still zero drops. USB pings passed 24/24
    in both runs. Cloud contention and ToF image notifications were not
    exercised. Do not mark the Milestone 4 gate as passed.
  - Final deadline refinement was rebuilt and reloaded from RAM: one fresh
    45-second Wi-Fi/BLE probe passed 222/222, p95 149.209 ms, zero missing,
    with three transient timeouts, one recovery and zero TX drops; USB passed
    24/24. The earlier missing reply remains an unresolved repeatability
    failure, so this fresh pass does not close M4.6 acceptance or the gate.
    `cloud status` reported `waiting for Wi-Fi, not paired`, so Cloud
    contention remained unavailable for this run.

### Milestone 4 gate

- [ ] No runtime W61 TX-lock acquisition is infinite.
- [ ] BLE remains responsive during AT contention.
- [ ] No packet is silently removed on a transient busy result.

---

# Milestone 5 — Isolate Cloud work

Goal: remove DNS/TLS/socket processing and output backpressure from Radio/BLE
and CLI tasks.

Sequencing exception (2026-09-25): the user explicitly authorized proceeding
to M5.1 with the Milestone 3 and 4 gates and the post-GOTIP 20-cycle HIL gate
still open. This is not approval of those gates or of M5.2 and later tasks.

Resume instruction (2026-10-03): after reviewing the unfinished plan and the
Cloud/Radio coupling, the user explicitly asked to continue it. Work resumes
at M5.2–M5.4 as one runtime ownership handoff. The M3/M4 and post-GOTIP gates
remain unaccepted; resuming implementation does not turn their failures into
passes. Do not advance to Milestone 6 before the Milestone 5 gate passes.

## [x] VERIFIED M5.1 — Make Cloud output admission non-blocking

- Files:
  - `AppliNonSecure/Core/Src/cloud_relay.c`
- Functions:
  - `CloudRelay_WriteOutput()`
  - `CloudRelay_CompleteCommand()`
- Change:
  - Remove the 15-second retry loop and all sleeps.
  - Compute the number of required slots before writing.
  - Admit the complete output atomically or return `TX_QUEUE_FULL`.
  - Use non-blocking gate acquisition.
  - Start with eight 384-byte output slots and validate memory use.
- Acceptance:
  - The API returns immediately and never leaves a partial response queued.
- Verification:
  - Incremental build and memory-map review passed. A private one-time
    initialization self-test filled seven of eight slots, rejected a two-slot
    record with `TX_QUEUE_FULL` without publishing a partial record, accepted
    one completion marker, rejected another when full, then checked a
    successful two-slot record and completion marker. It clears all test data
    before Cloud becomes available; initialization fails if any check fails.
    The exact RAM image reached `cloud status: waiting for Wi-Fi`, proving that
    this self-test returned success on the board. Paired Cloud end-to-end HIL
    remains deferred and is not implied by this admission test.

## [x] VERIFIED M5.2 — Add a dedicated Cloud run loop (source/build only)

- Files:
  - `AppliNonSecure/Core/Inc/cloud_relay.h`
  - `AppliNonSecure/Core/Src/cloud_relay.c`
- Functions:
  - new `CloudRelay_Run()`
  - private `cloud_process()` (replaces the exported `CloudRelay_Process()`)
- Change:
  - Own all DNS/TLS/socket/protocol progress in the Cloud task.
  - Use event wakeups or a short bounded periodic wait.
- Acceptance:
  - Private `cloud_process()` has one caller, `CloudRelay_Run()`.
- Verification:
  - Incremental build.
  - 2026-10-03: incremental and clean Non-Secure build PASS; one source caller
    confirmed. Cloud commands use a fixed four-entry by-value queue plus event
    wakeup, with forced-full/copy/FIFO startup checks. Public status reads use a
    bounded snapshot; producers/controls do not perform network/filesystem work.
    RAM startup on 2026-10-03 reached the worker after those checks passed.

## [~] IN_PROGRESS M5.3 — Create the Cloud task (built; RAM HIL pending)

Current verification substep (2026-10-06): the SPI5 RX-priority IOC/MSP candidate
passed ordinary RAM boot, 100-frame sensor/NPU HIL and 150/150 idle BLE replies.
Generate Code was requested and remains pending. Wi-Fi and paired Cloud CLI
stayed live, but ToF stopped at frame 2687 before pairing, with a HAL I3C size
error and stranded RX abort completion. Preserve the fault evidence and
characterize the initial trigger before the Cloud frame/lease gate. The earlier
debugger halt may have influenced timing. No later milestone is being started.

User-authorized scope extension (2026-10-06): repair the characterized I3C
completion/abort race and implement last-request-wins exclusive image routing
across USB, BLE and Cloud, retaining fixed buffers and draining the previous
owner before starting the next. Verify actual CRC-valid images on each route
and switching without concurrent image sends. This remains the single M5.3
IN_PROGRESS verification/remediation substep; it does not accept later gates.

Repair checkpoint: normal RAM build/load passed with 455768-byte NS image and
416728-byte C heap (minimum 368640). I3C multiple-transfer completion waits for
FCF and every DMA completion; abort handles TC winning the suspend request.
The next UART-only run failed at frame 5103 in blocking register-address TX
with HAL 0x40 (FIFO overrun/underrun), without debugger interference. Runtime
command status now uses DMA, a persistent byte, and idle-before-descriptor-
reuse checks. BLE notification capture independently exposed AT text being
consumed as image data: the driver incorrectly waited for initial OK before
the prompt. Corrected to prompt/payload/terminal response, and unfinished raw
transfers fence subsequent AT writes until module restart.

Exclusive-route RAM HIL passed BLE→USB→BLE: 5+5 complete CRC-valid BLE images,
20 USB dataset records with independent raw/model CRCs, no BLE images during
USB ownership, and zero BLE image retries/errors. An earlier host gate failed
its final BLE request because it had not enabled CLI Notify; its first five
BLE images and USB phase passed, and it is retained as a failed full gate.
Evidence: Tools/.n6-debug/architecture-m5/20261006_repair[2]/. Added reusable
hil_tests/run_image_route_gate.py; full current-script run, Cloud image proof,
soak and Generate Code still pending. Further current-image USB capture passed
100 distinct raw/model CRC-valid records. Final offline snapshot at 630886 ms:
ToF ready, acquired 6255, zero command/I3C failures, Radio/BLE maximum gaps
50/43 ms. Eight disabled-feature syntax checks, utility self-test, Python
compilation/help and diff checks passed. USB session-close UART captures still
include control-TX callback timeout/slot-drop diagnostics; do not claim every
CDC lifecycle counter is zero or accept the old Milestone 4 gate. The active
RAM image is Wi-Fi disconnected and Cloud unpaired; the user was asked to
connect/pair and confirm the actual browser image. No Cloud ToF frame was
sent in this offline run. No later milestone was accepted.

Connected follow-up (2026-10-06, same authorized substep): actual Cloud UI
rendered advancing 54×42 frames after Wi-Fi association and pairing. The first
Cloud→BLE→USB→BLE gate failed in the last BLE phase after notification timeouts
and a raw-response fence; healthy ToF/USB continued. Source inspection found
the 100 ms notification deadline included waiting behind a Cloud AT owner.
Notification admission now uses an immediate mutex attempt and returns BUSY
before announcing raw data; the existing pump retains its fragment for retry.
Once admitted, it has the execution budget. The fail-closed raw-response fence
is retained and logs only phase/byte/tick metadata. No capacity was increased.

Incremental NS build and normal RAM load PASS: 456632-byte binary, 415864-byte
C heap (minimum 368640). Connected --cloud gate PASS: 10+10 complete BLE
images, 25 USB header/raw/model CRC-valid records, no BLE image traffic during
USB ownership, Cloud accepted-image counter unchanged at 88 during BLE/USB.
Cloud MAP ON afterward resumed browser images (frame 4039, CRC 3A6EA5E7 in
saved viewport proof). Postflight: ToF READY, zero command/I3C failures,
Radio/BLE max gaps 50/43 ms, BLE image timeouts/errors 0; BUSY admissions 117
are deferred work, not lost fragments. Two aborted images/one interrupted
host frame remain recorded during handover, not claimed as zero cancellation.
Evidence: Tools/.n6-debug/architecture-m5/20261006_cloud_verify/ (first failure)
and 20261006_cloud_repair/ (load, UART, gate, postflight, cloud-final-image.jpg).
Pairing was re-established after RAM reload; automatic post-reset restoration
was not demonstrated. Network endurance, failure-latency, worst-case stack,
IOC Generate Code and previous milestone gates remain open. RAM only, no
version change/signing/Flash/commit/push. M5.3 stays IN_PROGRESS.

- Files:
  - `AppliNonSecure/Core/Src/app_threadx.c`
- Functions:
  - `App_ThreadX_Init()`
  - new `CloudRelayThread_Entry()`
- Change:
  - Create only when Cloud Relay is enabled.
  - Priority 9 and stack size 8192 bytes. Priority 12 from the original draft
    was replaced because the priority-10 ToF processor can remain ready; the
    existing CLI/Radio scheduling contract already requires outranking it.
  - Use fixed stack storage in the existing lower SRAM4 `.app_shared_bss`
    region. Neither the 134 KiB application pool nor the 64 KiB radio pool is
    enlarged, and no new stack allocation is taken from the radio pool.
  - Wait for radio-ready and handle loss of Wi-Fi IP without busy looping.
- Acceptance:
  - Cloud processing executes on a distinct task.
- Verification:
  - Incremental build and stack high-water inspection.
  - 2026-10-03: build/map PASS; stack at `0x242A1800`, 8192 bytes. SRAM4 section
    bounds passed. RAM startup and distinct worker execution PASS on 2026-10-03.
    GDB observed priority 9, 8192-byte stack and a sleeping worker with advancing
    run/loop counters. Stack-fill scan: 356 bytes used, 7836 untouched, in the
    offline-only phase. HTTP/pairing/send stack high-water and load tests remain
    PENDING; M5.3 is not yet fully VERIFIED.

## [ ] IMPLEMENTED / HIL PENDING M5.4 — Remove Cloud processing from the BLE loop

- Files:
  - `AppliNonSecure/Core/Src/wifi_ble_app.c`
- Functions:
  - `WIFI_BLE_App_Run()`
- Change:
  - Replace Cloud processing with scalar network-readiness publication.
  - Leave BLE event processing and bounded BLE TX/RX work only.
  - Superseded by the user's 2026-10-06 exclusive-route requirement: publish
    the Cloud lease while FILLING and enter WAIT_CLOUD directly. BLE READY
    belongs only to BLE. On destination change, stop old publications and
    cancel/drain the old consumer before reusing the snapshot. Release on
    Cloud disable/reconnect/unpair, Wi-Fi loss, and completed/failed payload send.
- Acceptance:
  - DNS/TLS failure does not increase the Radio/BLE loop gap.
- Verification:
  - Incremental build and the latency probe during Cloud reconnect failure.
  - 2026-10-03: incremental/clean build and Cloud-disabled/radio-disabled
    compilation checks PASS. Connected BLE/Cloud contention, frame CRC/lifetime,
    Wi-Fi-loss and reconnect HIL are PENDING; M5.4 is not VERIFIED.

## [ ] PLANNED M5.5 — Bound Cloud state transitions and retries

- Files:
  - `AppliNonSecure/Core/Src/cloud_relay.c`
- Functions:
  - `cloud_begin_request()`
  - `cloud_receive_step()`
  - `cloud_backoff()`
  - `cloud_finish_request()`
- Change:
  - Treat W6X busy/timeout as explicit transient outcomes.
  - Add a total request deadline.
  - Close the socket and enter bounded backoff on expiry.
  - Never immediately retry in a tight loop.
- Acceptance:
  - Repeated DNS/TLS failures do not create high CPU use or control-plane
    stalls.
- Verification:
  - Incremental build and a one-hour failure soak when hardware is available.

### Milestone 5 gate

- [ ] Cloud runs on its own task.
- [ ] Cloud output producers never wait.
- [ ] BLE latency remains within target during Cloud failures.

---

# Milestone 6 — Non-blocking CLI output and backpressure

Goal: ensure a slow client cannot suspend the shared CLI parser.

## [ ] PLANNED M6.1 — Use non-blocking transport writes

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
- Functions:
  - `cli_session_write()`
- Change:
  - USB uses `App_Console_WriteAsync()`.
  - BLE uses `WIFI_BLE_App_StreamWrite(..., TX_NO_WAIT)`.
  - Cloud uses the non-blocking all-or-none API from Milestone 5.
  - Record congestion and rejected byte counts per session.
- Acceptance:
  - No transport write from CLI has a wait option greater than zero.
- Verification:
  - Incremental build and source inspection.

## [ ] PLANNED M6.2 — Add explicit session congestion policy

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
- Functions/types:
  - `CliSession_t`
  - `cli_session_write()`
  - transport polling functions
- Change:
  - Mark a session congested when a TX enqueue fails.
  - Do not consume another command from that session until capacity returns.
  - On recovery, report one compact congestion summary.
  - Never retry in the same call.
- Acceptance:
  - A non-reading BLE client cannot delay USB CLI processing.
- Verification:
  - Incremental build and slow-client stress.

### Milestone 6 gate

- [ ] CLI has no transport wait.
- [ ] Congestion is isolated per session.
- [ ] Queue pressure is visible in status counters.

---

# Milestone 7 — System message bus and fanout

Goal: route CLI replies to their source while separately broadcasting system
messages to every currently usable transport.

## [ ] PLANNED M7.1 — Create a fixed system-message bus

- Files:
  - new `AppliNonSecure/Core/Inc/system_message_bus.h`
  - new `AppliNonSecure/Core/Src/system_message_bus.c`
- Functions:
  - `SystemMessage_Initialize()`
  - `SystemMessage_Publish()`
  - `SystemMessage_Run()`
  - `SystemMessage_GetStatus()`
- Change:
  - Start with eight 256-byte slots.
  - Include destination mask and message class.
  - Producers always use `TX_NO_WAIT`.
- Acceptance:
  - Publishers do not call transport APIs.
- Verification:
  - Incremental build and forced-full test.

## [ ] PLANNED M7.2 — Implement transport fanout adapters

- Files:
  - `AppliNonSecure/Core/Src/system_message_bus.c`
- Functions to add:
  - `system_message_send_uart()`
  - `system_message_send_usb()`
  - `system_message_send_ble()`
  - `system_message_send_cloud()`
- Change:
  - Check readiness and enqueue without waiting.
  - A disconnected transport drops the message by policy and increments a
    counter.
  - BLE uses the debug stream.
  - Cloud sends only when its protocol has a valid output channel.
- Acceptance:
  - One system message reaches every ready destination without blocking the
    publisher.
- Verification:
  - Incremental build and multi-transport HIL check.

## [ ] PLANNED M7.3 — Create the system-message task

- Files:
  - `AppliNonSecure/Core/Src/app_threadx.c`
- Functions:
  - `App_ThreadX_Init()`
  - new `SystemMessageThread_Entry()`
- Change:
  - Initial priority 10.
  - Make it the sole consumer and fanout owner.
- Acceptance:
  - Producers only enqueue.
- Verification:
  - Incremental build and stack high-water inspection.

## [ ] PLANNED M7.4 — Enforce message-class routing

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
  - `AppliNonSecure/Core/Src/debug_uart.c`
  - `AppliNonSecure/Core/Src/system_message_bus.c`
- Functions:
  - CLI result dispatch
  - `Debug_UART_Log()`
  - system publish/fanout functions
- Change:
  - CLI response goes only to its exact route.
  - Debug diagnostics go to UART only.
  - System lifecycle/fatal alerts use fanout.
  - Do not broadcast every debug line.
- Acceptance:
  - System events are visible on all ready transports without duplicating CLI
    replies.
- Verification:
  - Incremental build and route matrix test.

### Milestone 7 gate

- [ ] Direct CLI and broadcast system paths are separate.
- [ ] Disconnected destinations are dropped without delay.
- [ ] A slow destination cannot block another destination.

---

# Milestone 8 — Supervisor and deterministic recovery

Goal: detect missing progress externally, attempt only bounded local recovery,
and reset with a preserved reason when recovery is unsafe or exhausted.

## [ ] PLANNED M8.1 — Create the health registry and reset API

- Files:
  - new `AppliNonSecure/Core/Inc/system_health.h`
  - new `AppliNonSecure/Core/Src/system_health.c`
- Functions:
  - `SystemHealth_Initialize()`
  - `SystemHealth_RegisterTask()`
  - `SystemHealth_Heartbeat()`
  - `SystemHealth_OperationBegin()`
  - `SystemHealth_OperationEnd()`
  - `SystemHealth_RequestReset()`
  - `SystemHealth_Run()`
- Change:
  - Store last heartbeat, normal timeout, optional operation deadline, state,
    and last operation for each registered task.
  - Preserve reset reason before calling `NVIC_SystemReset()`.
- Acceptance:
  - A task does not need to detect its own deadlock.
- Verification:
  - Incremental build and module-level fault injection.

## [ ] PLANNED M8.2 — Create the supervisor task

- Files:
  - `AppliNonSecure/Core/Src/app_threadx.c`
- Functions:
  - `App_ThreadX_Init()`
  - new `SystemSupervisorThread_Entry()`
- Change:
  - Initial priority 5 and 250 ms inspection interval.
  - The supervisor performs no W6X, USB, Cloud, display, or ToF operation.
- Acceptance:
  - It can run while lower-priority application tasks are stuck.
- Verification:
  - Incremental build and stack high-water inspection.

## [ ] PLANNED M8.3 — Add control-plane heartbeats

- Files/functions:
  - `debug_cli.c::Debug_CLI_Run()`
  - `wifi_ble_app.c::WIFI_BLE_App_Run()`
  - `wifi_ble_app.c::WIFI_BLE_App_WifiControlRun()`
  - `cloud_relay.c::CloudRelay_Run()`
  - `debug_uart.c::Debug_UART_TaskRun()`
  - `system_message_bus.c::SystemMessage_Run()`
- Change:
  - Heartbeat from each bounded loop.
  - Replace idle infinite queue waits with periodic bounded waits.
  - Wi-Fi opens an operation deadline long enough for documented connect/DHCP
    limits plus margin.
- Acceptance:
  - Idle tasks are healthy and real stalls expire.
- Verification:
  - Incremental build and suppressed-heartbeat test.

## [ ] PLANNED M8.4 — Replace Radio error sleep with recovery/reset

- Files:
  - `AppliNonSecure/Core/Src/wifi_ble_app.c`
- Functions:
  - `WIFI_BLE_App_Run()` error path
- Change:
  - Remove the infinite error sleep.
  - Publish one system alert.
  - Attempt at most one explicitly safe local radio reinitialization.
  - Request a system reset if it fails.
- Acceptance:
  - Radio fatal state cannot leave the rest of the firmware running forever in
    a nonfunctional state.
- Verification:
  - Incremental build and injected radio-init failure.

## [ ] PLANNED M8.4a — Recover transient VL53L9CX failures locally

- Files:
  - `AppliNonSecure/Core/Src/tof_app.c`
  - `AppliNonSecure/Core/Inc/tof_app.h`
  - ToF port code only if required to cancel or reinitialize an in-flight I3C
    transfer safely.
- Functions:
  - `TOF_App_Acquire()` and its sensor initialization/error paths
  - `TOF_App_GetStatus()`
- Change:
  - Treat recoverable sensor/I3C failures, including a failed DSS map command,
    as a reason to discard the incomplete frame and start a bounded local
    recovery in the sole ToF acquisition task.
  - Quiesce any in-flight I3C/DMA transfer, clear stale completion/error events,
    reset the sensor through XSHUT, reassign its dynamic I3C address, restore
    the calibration/profile and autonomous stream, and resume acquisition.
    Reuse existing frame slots and transform resources; do not allocate a new
    pipeline or publish a partial frame.
  - Limit attempts and apply bounded backoff. Expose attempts, successful
    recoveries, exhausted recoveries, last stage/error, and current recovery
    state through `tof status` and Debug UART without logging from an ISR.
  - Keep ThreadX queue invariants and resource failures outside this sensor
    retry path; a sensor reset cannot repair those failures.
- Acceptance:
  - An injected transient DSS/I3C failure automatically returns to complete,
    valid, advancing ToF frames without resetting the MCU. A recovered failure
    counts as success, with its retry recorded.
  - USB/BLE CLI and radio activity remain live during recovery; no incomplete
    frame reaches the display, dataset, BLE image stream, or NPU.
  - Repeated sensor failure exhausts the configured retry budget and reports a
    persistent fault for the M8.5 supervisor/reset fallback. It cannot retry
    forever or repeatedly allocate memory.
- Verification:
  - Incremental build and RAM HIL with controlled transient and persistent
    sensor/I3C fault injection; verify frame IDs, validity, status counters,
    transport responsiveness, memory stability, and the exhausted path.

## [ ] PLANNED M8.5 — Replace exhausted ToF fatal loop with reset policy

- Files:
  - `AppliNonSecure/Core/Src/tof_app.c`
- Functions:
  - `tof_fatal()`
- Change:
  - Log and broadcast once.
  - Preserve stage and error code.
  - After the M8.4a local retry budget is exhausted, request reset rather
    than logging every two seconds forever.
- Acceptance:
  - Unrecoverable ToF failure reaches a deterministic reset; a transient
    recovered sensor fault does not reset the MCU.
- Verification:
  - Incremental build and controlled fault injection.

## [ ] PLANNED M8.6 — Reset after USB recovery exhaustion

- Files:
  - `AppliNonSecure/USBX/App/app_usbx_device.c`
- Functions:
  - `app_usb_device_restart_data_plane()`
- Change:
  - Keep the existing bounded local retry attempts.
  - After the last attempt, publish the failure and request reset.
- Acceptance:
  - USB is not silently left disabled until a power cycle.
- Verification:
  - Incremental build and injected repeated worker failure.

## [ ] PLANNED M8.7 — Handle fatal failures before the scheduler

- Files:
  - `AppliNonSecure/Core/Src/main.c`
  - `AppliNonSecure/AZURE_RTOS/App/app_azure_rtos.c`
- Functions:
  - `Error_Handler()`
  - `tx_application_define()` failure paths
- Change:
  - Use `Debug_UART_EmergencyWrite()` before the async task exists.
  - Store a boot-safe reset record.
  - Reset instead of entering an undocumented infinite loop.
  - Allow an explicit `APP_FATAL_HALT_FOR_DEBUG` build option, default off.
- Acceptance:
  - Initialization failures are visible and recover through reset.
- Verification:
  - Incremental build and one controlled initialization failure.

## [ ] PLANNED M8.8 — Preserve and report the previous reset

- Files:
  - `AppliNonSecure/Core/Src/system_health.c`
  - `AppliNonSecure/Core/Src/main.c`
- Functions:
  - `SystemHealth_RequestReset()`
  - new `SystemHealth_ReportPreviousReset()`
- Change:
  - Store a versioned `.noinit` record with magic, CRC, reason, task, operation,
    and tick.
  - Combine it with RCC reset flags on boot.
  - Print and broadcast a single previous-reset report.
- Acceptance:
  - Every supervisor reset has an attributable cause after reboot.
- Verification:
  - Incremental build and reset-record round trip.

## [ ] PLANNED M8.9 — Add reset-loop safe mode

- Files:
  - `AppliNonSecure/Core/Src/system_health.c`
  - relevant startup gating in `wifi_ble_app.c` and `cloud_relay.c`
- Functions:
  - `SystemHealth_ReportPreviousReset()`
  - startup enable decisions
- Change:
  - Count repeated equivalent watchdog/supervisor resets in retained state.
  - After three consecutive failures enter diagnostic safe mode.
  - Keep UART and USB CLI available; suppress automatic Cloud/radio connection.
  - Allow an explicit CLI recovery attempt.
- Acceptance:
  - A persistent hardware or credential fault does not create an opaque reboot
    loop.
- Verification:
  - Incremental build and three-reset fault sequence.

### Milestone 8 gate

- [ ] All critical tasks have heartbeat contracts.
- [ ] Injected transient ToF communication failure recovers to valid frames;
  persistent failure exhausts local retries and reaches the reset policy.
- [ ] Existing fatal infinite loops are removed from runtime paths.
- [ ] Reset reason survives reboot.
- [ ] Repeated resets enter a debuggable safe mode.

---

# Milestone 9 — Hardware IWDG

Goal: make hardware reset the final authority only after the software health
model is verified.

## [ ] PLANNED M9.1 — Enable IWDG through CubeMX

- Files:
  - `N6.ioc`
  - generated `AppliNonSecure/Core/Src/main.c`
  - generated `AppliNonSecure/Core/Inc/stm32n6xx_hal_conf.h`
  - generated project linkage for `stm32n6xx_hal_iwdg.c`
- Functions:
  - generated `MX_IWDG_Init()`
- Change:
  - Enable the HAL IWDG module.
  - Configure an initial five-second timeout.
  - Do not start it at the beginning of `main()`; expose controlled startup to
    the supervisor.
- Acceptance:
  - Cube regeneration preserves all USER CODE and the project builds cleanly.
- Verification:
  - Review generated diff before accepting it.
  - Clean Secure and NonSecure build.

## [ ] PLANNED M9.2 — Verify TrustZone and RIF ownership

- Files:
  - `N6.ioc`
  - `AppliSecure/Core/Src/main.c`
  - `AppliSecure/Core/Inc/partition_stm32n657xx.h`
- Functions:
  - `SystemIsolation_Config()`
- Change:
  - Confirm whether IWDG and its IRQ are Secure or NonSecure.
  - If Secure-owned, expose a minimal start/refresh secure service instead of
    granting broad peripheral access.
  - Keep generated edits inside USER CODE sections where required.
- Acceptance:
  - Starting and refreshing IWDG causes no SecureFault.
- Verification:
  - Clean Secure and NonSecure build and a boot smoke test.

## [ ] PLANNED M9.3 — Refresh IWDG only from the supervisor

- Files:
  - `AppliNonSecure/Core/Src/system_health.c`
- Functions:
  - `SystemHealth_Run()`
- Change:
  - Start IWDG only after every required task has registered and produced its
    first heartbeat.
  - Refresh only when all required health contracts are valid.
  - On stale health, preserve the reason and deliberately stop refreshing.
- Acceptance:
  - No other application task refreshes the watchdog.
- Verification:
  - Source search, clean build, and suppressed-heartbeat HIL reset.

### Milestone 9 gate

- [ ] IWDG is owned by the intended security domain.
- [ ] Only the supervisor refreshes it.
- [ ] A suppressed heartbeat produces an attributed watchdog reset.

---

# Milestone 10 — Fault injection, soak, and documentation

Goal: prove the control plane stays responsive under the failures that
originally reproduced the problem.

## [ ] PLANNED M10.1 — Add release-disabled fault injection

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
  - `AppliNonSecure/Core/Src/system_health.c`
- Functions:
  - `cli_command_debug()`
  - health fault-injection helpers
- Change:
  - Under `APP_FAULT_INJECTION_ENABLED` only, add commands to suppress a
    heartbeat, fill the UART queue, and stall the radio loop.
  - Ensure the feature is disabled in release builds.
- Acceptance:
  - Every recovery path can be triggered deterministically during HIL testing.
- Verification:
  - Incremental build with the flag both disabled and enabled.

## [ ] PLANNED M10.2 — Add the combined control-plane soak

- Files:
  - `hil_tests/ble_inspector.py`
- Functions:
  - new `run_control_plane_soak()`
- Change:
  - Run BLE pings while cycling Wi-Fi connect/disconnect, Cloud reconnect,
    USB CLI commands, and UART bursts.
  - Collect latency percentiles, missing replies, queue high-water/drops,
    reconnects, reset reasons, and maximum radio-loop gap.
- Acceptance:
  - Thirty-minute run has zero missing control replies, no unexplained reset,
    and BLE `p95 < 250 ms`.
- Verification:
  - Execute the new HIL scenario and save its result.

## [ ] PLANNED M10.3 — Run extended failure soak

- Files:
  - no firmware source change expected
  - result record appended to this document
- Test:
  - One hour with unreachable Wi-Fi/Cloud endpoints and an active BLE client.
  - Include client reconnects and deliberate transport backpressure.
- Acceptance:
  - CLI remains responsive, CPU does not busy-loop, no queue counter grows
    without bound, and no unclassified reset occurs.
- Result record:
  - Date: pending
  - Firmware revision: pending
  - Result artifact: pending

## [ ] PLANNED M10.4 — Update permanent architecture documentation

- Files:
  - `AGENTS.md`
  - `README.md`
- Change:
  - Document task ownership, priorities, stacks, queue capacities, timeouts,
    health contracts, reset policy, and safe mode.
  - Record that USART1 interrupt-driven TX is manually maintained and not a
    CubeMX DMA allocation.
  - Record the bounded W61 command-lock contract.
- Acceptance:
  - Documentation matches the implementation and final HIL evidence.
- Verification:
  - Documentation review against source constants and task creation code.

### Milestone 10 gate

- [ ] Thirty-minute combined soak passes.
- [ ] One-hour failure soak passes.
- [ ] Final incremental and clean builds pass.
- [ ] Documentation matches the measured configuration.
- [ ] All global completion criteria are satisfied.

---

# Execution history

Append one entry after every completed or blocked task. Do not rewrite old
entries.

```text
YYYY-MM-DD HH:MM  TASK_ID  STATUS
Files changed:
Verification:
Result:
Remaining risk/blocker:
```

```text
2026-09-20 16:46  M0.1  VERIFIED
Files changed: AppliNonSecure/Core/Src/debug_cli.c; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS); source inspection confirmed one PONG response path plus help/completion entries.
Result: NonSecure ELF/BIN built successfully; C heap capacity 481392 bytes. Hardware ping checks are intentionally deferred to the Milestone 0 HIL gate.
Remaining risk/blocker: USB/BLE/Cloud token round trips have not yet been measured on hardware.
```

```text
2026-09-20 16:48  M0.2  VERIFIED
Files changed: AppliNonSecure/Core/Inc/wifi_ble_app.h; AppliNonSecure/Core/Src/wifi_ble_app.c; AppliNonSecure/Core/Src/debug_cli.c; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS); source inspection confirmed owner-loop-only counter updates and radio-status exposure.
Result: NonSecure ELF/BIN built successfully; C heap capacity 480992 bytes. No logging was added to the Radio/BLE hot loop.
Remaining risk/blocker: Idle and failed-connect gap values have not yet been compared on hardware.
```

```text
2026-09-20 16:55  M0.3  VERIFIED
Files changed: hil_tests/ble_inspector.py; docs/async-architecture-recovery-plan.md
Verification: ble_inspector.py --help (PASS); compileall (PASS); hil_tests/self_test.py (PASS); synthetic split-PONG/percentile/missing-reply test (PASS).
Result: Noninteractive idle and Wi-Fi-blocking probes send numbered pings at 200 ms cadence, save raw notifications/samples plus min/p50/p95/max/missing/reconnect data, and exit nonzero for a missing reply or p95 above 250 ms.
Remaining risk/blocker: The probes have not yet run against the physical board, so the baseline result fields and Milestone 0 gate remain pending.
```

```text
2026-09-20 16:56  M0.3  VERIFIED
Files changed: hil_tests/ble_inspector.py; docs/async-architecture-recovery-plan.md
Verification: ble_inspector.py --help (PASS); compileall (PASS); hil_tests/self_test.py (PASS); synthetic split-PONG/percentile/missing-reply test (PASS).
Result: Probe cleanup now retains a local BLE client reference, so a disconnect during stop-notify cannot hide the completed report.
Remaining risk/blocker: Physical BLE execution is still required for the Milestone 0 baseline and gate.
```

```text
2026-09-20 18:05  M0-GATE  VERIFIED
Files changed: docs/async-architecture-recovery-plan.md
Verification: User-provided COM8 HIL results: idle 50/50 replies, p95 16.4 ms, maximum 27.0 ms; failed Wi-Fi connect 225/225 replies, p95 988.5 ms, maximum 3165.8 ms; max_loop_gap_ticks increased from 33 to 3151.
Result: Milestone 0 is accepted. The measurements reproduce and quantify control-plane blocking during a Wi-Fi operation.
Remaining risk/blocker: BLE discovery sees a connectable N6 advertisement, but Windows WinRT returns E_FAIL before GATT. BLE final acceptance remains deferred and must be completed before the overall program is marked complete; it does not block Milestone 1.
```

```text
2026-09-20 18:13  M1.1  VERIFIED
Files changed: AppliNonSecure/Core/Inc/debug_uart.h; AppliNonSecure/Core/Inc/logging_config.h; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS).
Result: The asynchronous UART API and status snapshot are defined without exposing ThreadX types; the fixed transport contract is 16 slots of 512 bytes. NonSecure binary is 420936 bytes and C heap capacity is 480992 bytes.
Remaining risk/blocker: Queue storage and runtime behavior are implemented by the following Milestone 1 tasks.
```

```text
2026-09-20 18:16  M1.2  VERIFIED
Files changed: AppliNonSecure/Core/Src/debug_uart.c; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS); linker-map/object review confirmed 16 fixed 512-byte payload slots plus metadata and static ThreadX pointer-queue storage.
Result: Producers reserve every required slot with TX_NO_WAIT before publishing a message, reject oversize/full/contention immediately, and expose queue-full, in-use, and high-water counters. NonSecure binary is 421320 bytes and C heap capacity is 480416 bytes, 111776 bytes above the required minimum.
Remaining risk/blocker: The ready queue is not consumed until the sole TX owner is implemented and started by M1.3/M1.5.
```

```text
2026-09-20 18:18  M1.3  VERIFIED
Files changed: AppliNonSecure/Core/Src/debug_uart.c; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS); source review confirmed HAL_UART_Transmit_IT is called only by the queue owner and its timeout is derived from payload length, 115200 baud, and a fixed 20 ms margin.
Result: The owner drains ready slots in order, waits on completion/error events, aborts timed-out transfers, discards the remainder of a failed multi-slot message, updates counters, and continues. NonSecure binary is 421384 bytes and C heap capacity is 480352 bytes.
Remaining risk/blocker: USART1 IRQ/callback wiring and the hardware burst test remain for M1.4 and the Milestone 1 gate.
```

```text
2026-09-20 18:20  M1.4  VERIFIED
Files changed: AppliNonSecure/Core/Inc/stm32n6xx_it.h; AppliNonSecure/Core/Src/stm32n6xx_it.c; AppliNonSecure/Core/Src/debug_uart.c; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS); source search confirmed USART1 has an IRQ handler and no USART1 GPDMA allocation was added.
Result: USART1 interrupt priority 5 is enabled by Debug_UART_Init, the vector routes through Debug_UART_IRQHandler to HAL_UART_IRQHandler, and TX-complete/error callbacks only set ThreadX event flags. NonSecure binary is 422472 bytes and C heap capacity is 479232 bytes.
Remaining risk/blocker: Consecutive interrupt completions require the Milestone 1 hardware burst test.
```

```text
2026-09-20 18:21  M1.5  VERIFIED
Files changed: AppliNonSecure/Core/Src/app_threadx.c; AppliNonSecure/Core/Src/debug_uart.c; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS); generated stack-usage data shows 48 bytes in Debug_UART_TaskRun itself, excluding callees.
Result: Static UART objects and a 3072-byte priority-10 owner task are created before application producer threads. Pre-ThreadX startup remains synchronous and thread-context writes route to the prepared queue. NonSecure binary is 424056 bytes and C heap capacity is 469088 bytes, 100448 bytes above the required minimum.
Remaining risk/blocker: Runtime migration, hardware stack high-water inspection, and the burst test remain for M1.6 and the Milestone 1 gate.
```

```text
2026-09-20 20:16  M1.6  VERIFIED
Files changed: AppliNonSecure/Core/Inc/debug_uart.h; AppliNonSecure/Core/Src/debug_uart.c; AppliNonSecure/Core/Src/st67w6x_logging.c; AppliNonSecure/Core/Src/wifi_ble_app.c; AppliNonSecure/Core/Src/debug_cli.c; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS); rg HAL_UART_Transmit review (only the pre-async/emergency polling helper remains); USART1 symbol/IRQ review (PASS); git diff --check (PASS, line-ending warnings only); Python compileall and hil_tests/self_test.py (PASS).
Result: Runtime writes are copied into fixed slots with TX_NO_WAIT, the ST67 formatting mutex is nonblocking and never covers physical TX, and `debug uart`/`debug uart burst` expose counters, 100 ordered test lines, and ThreadX stack minimum-free bytes. NonSecure binary is 425304 bytes and C heap capacity is 467840 bytes, 99200 bytes above the required minimum.
Remaining risk/blocker: Milestone 1 hardware verification is pending: capture all 100 USART1 lines in order, confirm zero counter deltas for drops/full/timeouts/HAL errors, and record stack_min_free. The Milestone 1 gate remains unchecked until the user supplies those results.
```

```text
2026-09-20 20:19  M1.6  VERIFIED
Files changed: AppliNonSecure/Core/Src/debug_cli.c; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS); git diff --check (PASS, line-ending warnings only); Python compileall and hil_tests/self_test.py (PASS); HAL UART call-site review (PASS).
Result: Added `debug uart overflow`, a deterministic unpaced 100-message diagnostic that exhausts the 16-slot pool from the higher-priority CLI task and reports queued/sent/dropped/queue-full/timeout/HAL-error deltas after draining. NonSecure binary is 425712 bytes and C heap capacity is 467424 bytes, 98784 bytes above the required minimum.
Remaining risk/blocker: The Milestone 1 gate remains unchecked pending the manual UART burst, overflow, counter, and stack high-water observations. Milestone 2 has not started.
```

```text
2026-09-20 21:15  M1-GATE  BLOCKED
Files changed: none (user-provided HIL observation)
Verification: COM8 `debug uart`: initialized=1, queued=55, sent=0, dropped=107, queue_full=53, timeouts=54, hal_errors=0, in_use=1, high_water=16, stack_min_free=2868; no output was visible on COM6.
Result: Queue production worked but no interrupt-driven transfer completed. Inspection found that Secure RIF released USART1 and PE5/PE6 to NonSecure while the partition default still targeted USART1_IRQn to the Secure vector table.
Remaining risk/blocker: Route USART1_IRQn to NonSecure, then repeat the complete Milestone 1 gate.
```

```text
2026-09-20 21:15  M1.4  VERIFIED
Files changed: AppliSecure/Core/Src/main.c; AppliNonSecure/Core/Src/debug_uart.c; docs/async-architecture-recovery-plan.md
Verification: Secure incremental build (PASS); Tools/Build-NonSecureIncremental.ps1 (PASS); Debug-NonSecureRam.ps1 -NoBuild -Run (PASS); COM6/COM8 HIL showed sent completions increasing with timeouts=0 and hal_errors=0.
Result: Secure now calls NVIC_SetTargetState(USART1_IRQn) when releasing the VCP peripheral, and NonSecure clears a stale pending IRQ before enabling it. USART1 TX-complete interrupts now reach Debug_UART_IRQHandler and the ThreadX event waiter.
Remaining risk/blocker: The first post-fix burst exposed starvation of the priority-10 UART owner behind the continuously-ready priority-10 ToF processor.
```

```text
2026-09-20 21:15  M1.5  VERIFIED
Files changed: AppliNonSecure/Core/Src/app_threadx.c; AppliNonSecure/Core/Src/debug_uart.c; AppliNonSecure/Core/Src/debug_cli.c; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS); Debug-NonSecureRam.ps1 -NoBuild -Run (PASS); COM6/COM8 burst and overflow HIL (PASS).
Result: The short UART owner now runs at priority 5, above CPU-bound application producers, and queued mode becomes active only when the owner task starts. The overflow diagnostic remains deterministic because the producer fills the pool while the owner waits on physical transmission.
Remaining risk/blocker: The bounded 16-slot queue reported nine observable startup-burst drops before the agreed steady-state burst; the agreed burst itself had zero drop/full/error deltas.
```

```text
2026-09-20 21:15  M1-GATE  READY_FOR_USER_HIL
Files changed: docs/async-architecture-recovery-plan.md
Verification: RAM-loaded firmware 5 on COM6/COM8. Baseline: initialized=1, queued=84, sent=84, timeouts=0, hal_errors=0, in_use=0, stack_bytes=3072, stack_min_free=2868. Burst summary: queued_delta=100, sent_delta=100, dropped_delta=0, queue_full_delta=0, timeout_delta=0, hal_error_delta=0, flush=0. COM6 capture contained exactly M1-BURST 001/100 through 100/100 in order, with no missing or duplicate line. Forced overflow: queued_delta=18, sent_delta=18, dropped_delta=82, queue_full_delta=82, timeout_delta=0, hal_error_delta=0, flush=0; `debug ping m1-after-overflow` returned PONG and final in_use=0.
Result: Agent-run HIL now demonstrates ordered delivery, no physical-TX producer wait, no loss in the agreed paced burst, and bounded/observable overflow without a system stall. Per the program evidence policy, this prepares but does not approve the gate.
Remaining risk/blocker: User-provided manual HIL confirmation is still required before checking the Milestone 1 gate. Milestone 2 has not started. The deferred BLE/WinRT E_FAIL and final BLE acceptance conditions remain open for completion before the overall program is finished.
```

```text
2026-09-20 23:24  M1-REVIEW-FIX  READY_FOR_USER_HIL
Files changed: AppliNonSecure/Core/Inc/app_logging.h; AppliNonSecure/Core/Inc/debug_uart.h; AppliNonSecure/Core/Inc/logging_config.h; AppliNonSecure/Core/Src/app_threadx.c; AppliNonSecure/Core/Src/debug_cli.c; AppliNonSecure/Core/Src/debug_uart.c; AppliNonSecure/Core/Src/st67w6x_logging.c; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS; NonSecure binary 427728 bytes, C heap capacity 455072 bytes, 86432-byte margin); source-scoped `cli_command_debug` review found no `tx_thread_sleep` or `Debug_UART_Flush`; `git diff --check` (PASS, line-ending warnings only); Python compileall (PASS); `hil_tests/self_test.py` (PASS); generated stack usage: UART owner 56 bytes, diagnostic task 312 bytes, and CLI command 448 bytes, excluding callees.
Result: Burst and overflow diagnostics now start asynchronously on a dedicated task; the pool is 32 fixed 512-byte slots; message-owned linked slot chains remove producer-mutex contention; pool-exhaustion, producer-contention, oversize, context, transport, and internal-error counters plus a coherent Debug UART status snapshot are exposed. ST67 formatting now uses four fixed message-owned buffers and exposes exhaustion, interrupt-rejection, and format-error counters without unbounded waits.
Remaining risk/blocker: User cold-boot HIL must confirm zero baseline drops and queue-full events, CLI responsiveness during an active asynchronous test, ordered/lossless burst output, observable deliberate overflow, and final `in_use=0`. The Milestone 1 gate remains unchecked, Milestone 2 has not started, and the deferred BLE/WinRT acceptance work remains open.
```

```text
2026-09-21 10:15  M1-GATE  VERIFIED
Files changed: docs/async-architecture-recovery-plan.md
Verification: User-provided final COM8 HIL. Cold baseline: queued=87, sent=87, dropped=0, queue_full=0, pool_full=0, contention=0, oversize=0, context=0, transport=0, internal=0, timeouts=0, hal_errors=0, in_use=0, capacity=32, high_water=24, stack_min_free=2860; ST67 buffer_exhaustions=0, interrupt_rejections=0, format_errors=0. Asynchronous burst run 1 completed with attempted=100, queued_delta=101, sent_delta=101, every drop/full/error delta zero, flush=0, and `debug ping m1-burst-live` returned PONG. Deliberate overflow run 2 completed with attempted=100, queued_delta=34, sent_delta=34, dropped_delta=66, queue_full_delta=66, pool_full_delta=66, no contention/oversize/timeout/HAL-error delta, flush=0, `debug ping m1-overflow-live` returned PONG, and final in_use=0. The extra accepted burst message is concurrent runtime output and not loss. Together with the previously recorded exact ordered COM6 capture of all 100 M1-BURST lines, the evidence satisfies the gate.
Result: Milestone 1 is accepted. Producers remain responsive while the asynchronous diagnostic task owns test pacing and draining; normal cold boot has zero drops/full events; deliberate capacity overflow is bounded and fully visible; the transport returns idle without timeout or HAL error. Command/status timing relative to test completion is not an acceptance criterion because run/completed IDs and result deltas identify the completed asynchronous run.
Remaining risk/blocker: Milestone 2 has not started and requires a separate user instruction. The deferred BLE/WinRT E_FAIL and final BLE acceptance conditions remain open and must be revisited before the overall program is complete.
```

```text
2026-09-21 10:55  M2.1  VERIFIED
Files changed: AppliNonSecure/Core/Inc/app_route.h; AppliNonSecure/Core/Src/debug_cli.c; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS; NonSecure binary 427728 bytes, C heap capacity 455072 bytes, 86432-byte margin).
Result: Added transport-independent `AppTransport_t` identifiers for USB, BLE, Cloud, and System; `AppRoute_t` containing only transport plus session generation; and numeric `AppRequestId_t`. The new header depends only on `stdint.h` and is compiled through `debug_cli.c`.
Remaining risk/blocker: Route ownership, generation lifecycle, stale-route detection, and per-session credentials are implemented by M2.2-M2.3. Milestone 2 gate remains unchecked and Milestone 3 has not started.
```

```text
2026-09-21 10:59  M2.2  VERIFIED
Files changed: AppliNonSecure/Core/Src/debug_cli.c; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS; NonSecure binary 428048 bytes, C heap capacity 454752 bytes, 86112-byte margin); source review confirmed `CliTransport_t` and the local BLE-generation field are removed.
Result: Every USB, BLE, and Cloud CLI session now owns a fixed-transport `AppRoute_t`. `cli_session_reset()` preserves and advances the prior non-zero generation with wraparound to 1. BLE aligns once to the radio runtime generation after each connect/disconnect epoch, while Cloud follows only the existing logical generation boundaries: successful pair, explicit reconnect/test, and unpair. `cli_route_is_current()` detects a saved route that became stale after reset.
Remaining risk/blocker: M2.3 must isolate and clear Wi-Fi credentials per session and add the focused reset/stale-route/credential diagnostic. No new cross-task structure was introduced; the existing CLI-session pointers remain private to the single CLI broker/update state machine and are not placed in a cross-task message. Milestone 2 gate remains unchecked and Milestone 3 has not started.
```

```text
2026-09-21 11:11  M2.3  VERIFIED
Files changed: AppliNonSecure/Core/Src/debug_cli.c; README.md; AGENTS.md; CHANGELOG.md; docs/async-architecture-recovery-plan.md
Verification: Tools/Build-NonSecureIncremental.ps1 (PASS; NonSecure binary 429624 bytes, C heap capacity 453312 bytes, 84672-byte margin); `git diff --check` (PASS, line-ending warnings only); `python -m compileall -q hil_tests` (PASS); `python hil_tests/self_test.py` (PASS); `rg -n "cli_pending_ssid" AppliNonSecure` found no symbol; `app_route.h` include review found only `stdint.h`; all `CliSession_t *` occurrences are private to `debug_cli.c`, a struct-block review found no structure containing a `CliSession_t *`, and Firmware Update Start/Feed/Poll/Cancel callers are confined to the same CLI broker source file.
Result: Pending SSID, password buffer, password length, and explicit password-prompt state are owned by each CLI session. Submission, Ctrl-C, input overflow, prompt failure, Wi-Fi disconnect, transport disconnect/reset, and every connect-result path scrub both complete buffers. `wifi connect` is excluded from command history. The built-in `debug route` startup diagnostic uses the production helpers to test reset generation, stale saved routes, two independent SSIDs, and scoped cancel/reset clearing.
Remaining risk/blocker: The diagnostic has not been executed on the physical firmware, and no live USB/BLE/Cloud reconnect was performed in this task. That hardware evidence is explicitly deferred; the first Milestone 2 gate item remains open. Milestone 3 has not started.
```

```text
2026-09-21 11:11  M2-GATE  DEFERRED_HIL
Files changed: docs/async-architecture-recovery-plan.md
Verification: Source/build/static checks pass for all M2.1-M2.3 changes. The hardware-only `debug route` result and a real generation change across reset/reconnect were not observed.
Result: The structural gate items for removal of global pending SSID and absence of cross-task `CliSession_t *` carriers pass. USB, BLE, and Cloud routes compile with fixed transports and non-zero generation logic, but their runtime diagnostic evidence remains deferred rather than reported as passed.
Remaining risk/blocker: Run `debug route` and one real transport reset/reconnect before checking the first Milestone 2 gate item. Do not start Milestone 3 without additional user approval.
```

```text
2026-09-21  M2-GATE  VERIFIED
Files changed: docs/async-architecture-recovery-plan.md
Verification: User-provided HIL output after the requested USB session reset/reconnect: `current=USB/2 usb=2 cloud=1`, `ble=1`; `available=1 reset_generation=pass stale_route=pass credential_isolation=pass cancel_scoped=pass reset_scoped=pass`.
Result: All Milestone 2 gate conditions pass. USB, BLE, and Cloud expose fixed transports with non-zero generations; the USB route advanced from its initial generation to 2; the production diagnostic confirms generation advancement, stale saved-route detection, per-session credential isolation, and session-scoped cancel/reset clearing.
Remaining risk/blocker: Milestone 2 is closed. Milestone 3 has not started and requires separate user approval. Live BLE/WinRT acceptance remains deferred for the final program criteria and is not claimed by this gate.
```

```text
2026-09-21 12:07  M3.1  VERIFIED
Files changed: AppliNonSecure/Core/Inc/wifi_ble_app.h; README.md; CHANGELOG.md; docs/async-architecture-recovery-plan.md
Verification: `Tools/Build-NonSecureIncremental.ps1` (PASS; NonSecure binary 429624 bytes, C heap capacity 453312 bytes, 84672-byte margin); PowerShell structure review (PASS: no pointer fields in `WifiBle_WifiRequest_t` or `WifiBle_WifiResult_t`, required `AppRoute_t`/`AppRequestId_t` fields present, result follows its status/scan member definitions); public-header dependency review (PASS: no W6X symbol/include); vendor/public size review (PASS: public 64-byte password buffer equals vendor maximum 63 plus NUL); `git diff --check` (PASS, line-ending warnings only).
Result: Added the public NONE/SCAN/CONNECT/DISCONNECT operation type and fully owned request/result message values. Requests own fixed SSID/password buffers, request identity, route, and forget argument; results own the original identity/route, final status, Wi-Fi status snapshot, and bounded scan snapshot. The ownership, zeroing, and M3.4 password-scrubbing contracts are documented beside the types.
Remaining risk/blocker: These message definitions are intentionally not wired into the existing control context or blocking API. M3.2 and all later Milestone 3 tasks remain planned; the Milestone 3 gate remains open.
```

```text
2026-09-21 12:55  M3.2  VERIFIED
Files changed: AppliNonSecure/Core/Src/wifi_ble_app.c; README.md; CHANGELOG.md; docs/async-architecture-recovery-plan.md
Verification: `Tools/Build-NonSecureIncremental.ps1` (PASS; NonSecure binary 431128 bytes, C heap capacity 451808 bytes, 83168-byte margin); source audit (PASS: exactly four request and four result slots, four `TX_1_ULONG` queues with four-entry fixed storage, and all eight new `tx_queue_send`/`tx_queue_receive` call sites use `TX_NO_WAIT`); initialization rollback audit (PASS: success bits cover every queue-creation stage, only created queues/event object are deleted, the complete context is scrubbed, the global pointer is cleared, and the SRAM4 block is released); DWARF size audit (PASS: `sizeof(WifiBle_WifiControlContext_t) == 5648`, 496 bytes below the explicit 6 KiB budget); `git diff --check` (PASS, line-ending warnings only).
Result: Wi-Fi initialization now creates and primes fixed request-free/request-ready/result-free/result-ready pointer queues and runs a private saturation/identity/scrubbing/restore self-test. Empty free pools return `TX_QUEUE_FULL`; request release clears the complete password-bearing message and result release clears the complete snapshot. The self-test emits a short Debug UART PASS/FAIL line and cleanly fails initialization through centralized rollback. The context grew from 1072 to 5648 bytes; applying the 4576-byte increase to the latest measured 21056-byte final radio-pool margin projects 16480 bytes remaining, while the startup log reports the live value after Wi-Fi queue initialization.
Remaining risk/blocker: The self-test is build-armed but was not observed on hardware in this task, as permitted for M3.2. The original event-based blocking scan/connect/disconnect state and `WIFI_BLE_App_Run()` processing remain active transitional code; no public submit/result API, worker, or CLI queue integration exists. M3.3 and later tasks remain planned, and the Milestone 3 gate remains open.
```

```text
2026-09-21 13:48  M3.3  VERIFIED
Files changed: AppliNonSecure/Core/Inc/wifi_ble_app.h; AppliNonSecure/Core/Src/wifi_ble_app.c; README.md; CHANGELOG.md; docs/async-architecture-recovery-plan.md
Verification: `Tools/Build-NonSecureIncremental.ps1` (PASS; NonSecure binary 431128 bytes, C heap capacity 451808 bytes, 83168-byte margin); `rg` declaration/implementation review (PASS: both public symbols are declared and defined); focused source audit (PASS: no `TX_WAIT_FOREVER`, `tx_thread_sleep`, event wait/set, polling loop, or retry loop in either API; the existing slot helpers use `TX_NO_WAIT`; request exhaustion maps to `TX_QUEUE_FULL`; an empty result queue propagates `TX_QUEUE_EMPTY`); `git diff --check` (PASS, line-ending warnings only).
Result: `WIFI_BLE_App_WifiSubmit()` now validates operation/transport/non-zero generation and bounded credential strings, acquires an existing request slot without waiting, assigns a monotonically increasing non-zero ID with wrap to 1 inside a minimal interrupt critical section, copies only operation-relevant owned fields, and publishes. Publish failure scrubs and releases the slot. `WIFI_BLE_App_WifiReceiveResult()` copies one complete ready result and immediately scrubs/releases its slot, or returns `TX_QUEUE_EMPTY` without waiting.
Remaining risk/blocker: No M3.4 consumer exists yet, so submitted requests are intentionally not executed and no results are produced through this path. The CLI still uses the unchanged legacy blocking APIs and `WIFI_BLE_App_Run()` remains unchanged. M3.4 and later tasks remain planned; the Milestone 3 gate remains open.
```

```text
2026-09-21 16:19  M3.4  VERIFIED
Files changed: AppliNonSecure/Core/Inc/wifi_ble_app.h; AppliNonSecure/Core/Src/wifi_ble_app.c; README.md; CHANGELOG.md; docs/async-architecture-recovery-plan.md
Verification: `Tools/Build-NonSecureIncremental.ps1` (PASS; NonSecure binary 427420 bytes, C heap capacity 455520 bytes, 86880-byte margin; existing RWX LOAD-segment warning only); focused source audit (PASS: `WIFI_BLE_App_Run()` contains no scan/connect/disconnect call and never calls the request executor; each of `W6X_WiFi_Scan`, `W6X_WiFi_Connect`, and `W6X_WiFi_Disconnect` occurs exactly once in the source and inside `wifi_execute_request()`); control-loop audit (PASS: waits for radio-ready and work, receives owned request slots, obtains a result slot, executes, scrubs/releases the request, and publishes the independent result); result-path audit (PASS: operation/request ID/original route, final status, Wi-Fi status, bounded scan snapshot, and scan timeout/failure are populated); password audit (PASS: queued password is scrubbed after transfer to stack-local W6X options and before connect, and options are scrubbed after return); scan-callback audit (PASS: callback snapshots bounded data and signals completion without finalizing the request); `git diff --check` (PASS, line-ending warnings only).
Result: Added `WIFI_BLE_App_WifiControlRun()` and private `wifi_execute_request()`. The control loop does not touch W6X until the radio-ready signal, drains the request-ready queue, owns every high-level scan/connect/disconnect execution, and publishes one owned result for every normally dequeued request, including vendor error and bounded scan-timeout results. `WIFI_BLE_App_Run()` now performs radio/BLE maintenance only and signals readiness; it no longer processes high-level Wi-Fi requests. The blocking APIs remain a transitional adapter to the same executor so the CLI source is unchanged.
Remaining risk/blocker: M3.5 has not created or started the dedicated control thread, so this build defines the loop but does not run it yet; queued and legacy operations will not be serviced until M3.5. No CubeMX generation or physical HIL was required or performed. M3.5 and later tasks remain planned, and the Milestone 3 gate remains open.
```

```text
2026-09-21 16:44  M3.5  VERIFIED
Files changed: AppliNonSecure/Core/Src/app_threadx.c; AGENTS.md; README.md; CHANGELOG.md; docs/async-architecture-recovery-plan.md
Verification: `Tools/Build-NonSecureIncremental.ps1` (PASS; NonSecure binary 432672 bytes, C heap capacity 450080 bytes, 81440-byte margin; existing RWX LOAD-segment warning only); linker map/preflight (PASS: dedicated `.radio_shared_bss` remains exactly 65536 bytes at `0x242D0000..0x242DFFFF`, and the linked image contains the Wi-Fi control entry, thread object, and M3.4 loop); focused source audit (PASS: conditional worker uses a 6144-byte `radio_pool` allocation, priority 11, `TX_NO_TIME_SLICE`, `TX_AUTO_START`, `TX_POOL_ERROR`/`TX_THREAD_ERROR`, and its entry calls only `WIFI_BLE_App_WifiControlRun()` with no direct W6X call); `Debug-NonSecureRam.ps1 -NoBuild -Run` (PASS, external NOR unchanged); COM6 startup (PASS: `Wi-Fi control task created in SRAM4`, Wi-Fi queue self-test PASS, radio ready); live SWD inspection after startup (PASS: valid ThreadX ID, priority 11, 6144-byte stack, 4876 bytes minimum free); failed-connect breakpoint (PASS: `W6X_WiFi_Connect` current thread `0x2417C090` equals `tx_wifi_control_thread`, while Radio Manager is `0x2417C140`); post-connect stack inspection (PASS: 3936 bytes minimum free, 2208-byte high-water); `debug ping m35-after` and `wifi status` (PASS: PONG and STA DISCONNECTED); `ble status` (PASS: radio pool 3188 bytes available in 29 fragments); `git diff --check` (PASS, line-ending warnings only).
Result: A dedicated SRAM4-backed Wi-Fi control worker now runs automatically at priority 11 with no time slice. Its only entry call is the M3.4 control loop, whose radio-ready wait makes auto-start safe. Live HIL proves that connect executes on this worker rather than the priority-9 Radio Manager/BLE thread and that the mandated 6 KiB stack retains 3936 bytes after the exercised failure path.
Remaining risk/blocker: The fully initialized radio pool retains only 3188 bytes across 29 fragments after adding the mandated worker stack. All current fixed contexts, BLE CLI session, Cloud context, and the failed-connect path were active without allocation failure, but this is a narrow runtime reserve and must be watched during later BLE/Cloud/soak gates. M3.6 and later tasks remain planned, the CLI is unchanged, and the Milestone 3 gate remains open.
```

```text
2026-09-21 17:56  M3.6  VERIFIED
Files changed: AppliNonSecure/Core/Src/debug_cli.c; AGENTS.md; README.md; CHANGELOG.md; docs/async-architecture-recovery-plan.md
Verification: `Tools/Build-NonSecureIncremental.ps1` (PASS; NonSecure binary 432304 bytes, C heap capacity 450424 bytes, 81784-byte margin; existing RWX LOAD-segment warning only); focused source audit (PASS: `debug_cli.c` contains no `WIFI_BLE_App_WifiScan()` call or `CLI_WIFI_SCAN_WAIT_TICKS`; `cli_wifi_scan()` owns only a zeroed stack request plus request ID, copies `cli_active_session->route`, calls `WIFI_BLE_App_WifiSubmit()`, reports accepted/rejected, and contains no result object, wait, timeout, poll, or loop); `git diff --check` (PASS, line-ending warnings only); `Debug-NonSecureRam.ps1 -NoBuild -Run` (PASS, external NOR unchanged); live USB HIL (PASS: `wifi scan` returned `Wi-Fi scan request accepted: id=1.` and the prompt in 14 ms); six immediate `debug ping m36-live-1..6` probes (PASS: 6/6 PONG, observed within 8..30 ms, no 30-second stall); repeated scan (PASS: IDs 1 then 2 on the fresh run and immediate prompts); SRAM4 audit (PASS for M3.6 ownership: no new static storage or allocator call; linker radio pool remains 65536 bytes). Runtime pool was 3188 bytes before the first scan, then 2260 bytes/30 fragments after both the first and second scans. Source/DWARF review explains the exact one-time 928-byte change as the pre-existing vendor lazy allocation of `20 * sizeof(W61_WiFi_AP_t)` = 920 bytes plus the 8-byte ThreadX block header; the second scan caused no further decrease.
Result: `wifi scan` is now submission-only. It sends a fully owned SCAN request tagged with the active session route, prints the assigned monotonic request ID, and returns immediately to the CLI. Scan execution continues in the priority-11 Wi-Fi worker, so CLI transport pings remain responsive. No scan result or network list is printed yet, as intentionally deferred to M3.9.
Remaining risk/blocker: The vendor's first-scan buffer reduces the already narrow steady-state radio-pool reserve to 2260 bytes, although repeated scans are stable and M3.6 adds no SRAM4 allocation. Result consumption is not implemented until M3.9, so each transitional scan retains one of the four fixed result slots; do not use this intermediate build for repeated production scans. Connect/disconnect remain on the legacy blocking CLI path. M3.7 and later tasks remain planned, and the Milestone 3 gate remains open.
```

```text
2026-09-21 19:40  M3.7  IMPLEMENTED; BLE HIL OPEN
Files changed: AppliNonSecure/Core/Src/debug_cli.c; AGENTS.md; README.md; CHANGELOG.md; docs/async-architecture-recovery-plan.md
Verification: `Tools/Build-NonSecureIncremental.ps1` (PASS; NonSecure binary 431920 bytes, C heap capacity 450808 bytes, 82168-byte margin; existing RWX LOAD-segment warning only); focused source audit (PASS: `debug_cli.c` has no `CLI_WIFI_CONNECT_WAIT_TICKS` or `WIFI_BLE_App_WifiConnect()` call; `cli_wifi_connect_password()` validates the session/secret state and bounded password length, builds a zeroed stack-owned CONNECT request with the active route and NUL-terminated credentials, calls `WIFI_BLE_App_WifiSubmit()`, scrubs the complete stack request immediately after return, reports accepted/rejected, and has no status query, wait, poll, sleep, or retry; `cli_process_byte()` still unconditionally calls `cli_session_clear_credentials()` before returning to the prompt); `git diff --check` (PASS, line-ending warnings only); two fresh `Debug-NonSecureRam.ps1 -NoBuild -Run` loads (PASS, external NOR unchanged). USB boot-A HIL (PASS: hidden-password prompt in 31.0 ms; CONNECT request accepted as ID 1 and prompt returned in 12.6 ms; 8/8 immediate `debug ping m37-usb-1..8` replies observed in 14.2..30.6 ms during the invalid-SSID failure; radio `max_gap_ticks` remained 21 versus the Milestone-0 failure value of 3151; radio-pool availability remained 3188 bytes before and after, with fragment count changing from 26 to 29). BLE boot-B probe using the exact requested `.\hil_tests\.venv\Scripts\python.exe .\hil_tests\ble_inspector.py --probe wifi-blocking --probe-seconds 45` command was attempted twice; both scans found `N6-MAINT-B8FB` at -59 dBm, but automatic/public/random WinRT connection attempts all failed with `E_FAIL` before GATT, before a Wi-Fi request, and before any latency sample. A Python 3.13 isolation attempt found the same advertisement at -58 dBm and failed at the same WinRT boundary. Post-attempt firmware status confirmed link disconnected, generation 0, zero GATT writes, 3188 radio-pool bytes available, and `max_gap_ticks=21`.
Result: The USB, Cloud, and BLE CLI code paths now share submission-only CONNECT behavior because they enter the same route-aware session function. The function returns immediately after request admission, owns no result or wait state, removes the legacy CLI connect/status calls, and scrubs both the stack copy and the session copy on every outcome. M3.7 adds no allocation or SRAM4 storage. The USB acceptance evidence passes, but the BLE p95/missing-reply requirement is not claimed because the Windows central never established GATT.
Remaining risk/blocker: Re-run the 45-second BLE `wifi-blocking` probe from a working Windows BLE central and require zero missing replies plus p95 <=250 ms; concurrently verify USB PONGs and the radio-loop gap. Until that succeeds, M3.7 remains unchecked rather than VERIFIED. Only one CONNECT request was submitted in each firmware boot used for the intermediate result-slot state. M3.8 has not started, disconnect remains on the legacy blocking CLI adapter, routed result presentation remains M3.9, and the Milestone 3 gate remains open.
```

```text
2026-09-21 21:25  M3.7 FOLLOW-UP  REPRODUCED VENDOR BLE PARSER LIVELOCK
Files changed: AGENTS.md; README.md; CHANGELOG.md; docs/async-architecture-recovery-plan.md (documentation only in this follow-up; no firmware source changed)
Verification: User manual HIL first proved host permissions and the GATT path: `--pair --uncached-services` found `N6-MAINT-B8FB`, connected at MTU 247, enumerated the expected CLI/DEBUG/ToF services, reported `N6 GATT contract: PASS`, disconnected, and the firmware restarted advertising. An elevated exact `--probe wifi-blocking --probe-seconds 45` run then passed with 225/225 replies, zero missing, p50 131.173 ms, p95 162.088 ms, maximum 507.848 ms and zero reconnects; 18/18 concurrent USB PONGs arrived in 15.2..31.6 ms and the radio report recorded `max_loop_gap=430` versus the Milestone-0 value of 3151. A fresh-RAM repeat connected at MTU 23 but failed with 21/75 replies, 54 missing, p50 155.136 ms, p95 239.496 ms, maximum 253.811 ms, one disconnect and no reconnect. Its preserved report is `hil_tests/results/m37_ble_wifi_blocking_20260921.json`, SHA-256 `69921952016CF07FDB5BF4B86D2592010BCB256698CC5CE8F4CDFF55471CFCE4`. COM8 remained enumerated but writes failed with a semaphore timeout while COM6 and the CPU remained live. Hot-plug GDB snapshots found no Non-Secure fault and repeatedly stopped the priority-2 `Modem_Process` thread inside `W61_Ble_Data_Event()`/`cmd_handler_process_rx_buf()` on event 25 (`W61_BLE_EVT_WRITE_ID`). The RX buffer began with malformed/truncated `+BLE:GATTWRITE:0,0,` data; the handler returned a negative parse error, and the direct-match branch neither consumed the input nor broke/yielded for a negative result other than `-EAGAIN`. `wifi_ble_loop_count` remained exactly unchanged across snapshots, BLE state remained falsely connected with advertising off, and Radio Manager/USB were starved. Early default-mode GDB attaches reset the target into BootROM and were discarded; only subsequent `--attach`/Hot Plug evidence is relied upon. All reloads were RAM-only and external NOR was unchanged.
Result: The M3.7 submission-only implementation can meet the required BLE latency and keeps USB responsive in a successful run, but the result is not repeatable because malformed BLE write input can livelock the vendor parser. This is a control-plane scheduling failure rather than a Cortex HardFault or evidence that the M3.7 submit call itself blocked.
Remaining risk/blocker: M3.7 remains unchecked and the Milestone 3 gate remains open. A separately authorized, targeted review-fix must give the vendor direct-event parser bounded forward progress for malformed input and add regression coverage, followed by repeat BLE/USB HIL. The board was deliberately left in the reproduced live-livelock state for further inspection. M3.8 has not started.
```

```text
2026-09-22 12:05  M3.7 TARGETED REVIEW-FIX  PARTIAL HIL PASS; REPEATABILITY OPEN
Files changed: AppliNonSecure/Core/Src/debug_cli.c; ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c; ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_ble.c; ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c; hil_tests/ble_inspector.py; AGENTS.md; README.md; CHANGELOG.md; docs/async-architecture-recovery-plan.md
Verification: `Tools/Build-NonSecureIncremental.ps1` (PASS; NonSecure binary 432480 bytes, C heap capacity 450264 bytes, existing RWX LOAD-segment warning only); focused source review (PASS for bounded parser/raw-write progress: partial BLE numeric fields return `-EAGAIN`, malformed direct records are scrubbed and leave the parser loop, and a non-progressing/invalid raw SPI write exits through the common unlock path instead of spinning with `sem_tx_lock` held); repeated `Debug-NonSecureRam.ps1 -NoBuild -Run` loads (PASS, external NOR unchanged). Fresh-RAM BLE report `m37_final_run20_bus_progress.json` passed 222/222 with zero missing, p50 115.226 ms, p95 148.352 ms, maximum 508.491 ms and zero reconnects. The next fresh-RAM report `m37_final_run21_bus_progress_repeat.json` failed before the latency phase because the connected CLI did not publish its initial prompt; no Wi-Fi request was submitted, and COM6 captured repeated `waiting for spi txn ready timeouted` errors. Hot Plug inspection found no Cortex fault or CPU starvation: application/ToF processing and the radio loop remained live, and disconnect restored advertising. A third fresh-RAM report `m37_final_run22_bus_progress_usb.json` passed 222/222 with zero missing, p50 94.774 ms, p95 152.370 ms, maximum 489.236 ms and zero reconnects while 24/24 concurrent USB PONGs passed with p95 30.6 ms and maximum 31.5 ms. Final HIL status showed STA disconnected after the intended failure, BLE advertising restored, 224 accepted GATT writes, zero BLE CLI RX/TX drops/retries/errors, 3,184 radio-pool bytes available, radio/BLE `max_gap_ticks=390`, and Debug UART dropped/queue-full/timeouts all zero.
Result: M3.7 remains submission-only and the original parser livelock plus the raw-write lock-retention defect now have bounded forward progress. The successful runs prove that the architecture can satisfy the required BLE and USB responsiveness while the priority-11 worker owns the failing association. The result is not yet repeatable because one post-fix clean run lost the SPI transaction-ready handshake before the Wi-Fi trigger.
Remaining risk/blocker: Do not mark M3.7 or the Milestone 3 gate complete. The remaining vendor SPI transaction-ready recovery path must be bounded/recovered and the fresh-boot BLE/USB probe repeated without an intervening transport failure. M3.8 has not started; disconnect remains on the legacy blocking adapter, result presentation remains M3.9, and only RAM images were loaded.
```

```text
2026-09-23  M3.7 SPI TRANSACTION-READY FOLLOW-UP  IMPLEMENTED; 5/5 HIL FAILED
Files changed for this follow-up: ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.c, spi_iface.h, spi_port.h; AppliNonSecure/Core/Src/spi_port.c; hil_tests/ble_inspector.py; docs/async-architecture-recovery-plan.md. Prior M3.7 parser/CLI edits remain in the dirty working tree. No M3.8 code or external NOR was changed.
Implementation: spi_xfer_one() samples SPI_RDY before the bounded TXN_RDY wait and again at timeout, accepting a high level as a missed/coalesced edge. spi_do_xfer() now checks the return value, deasserts CS on all outcomes, limits self-driven retries to three, retains the owned TX buffer for a later event, and performs only a local HAL/DMA abort after a transfer error; no NCP reset or deliberate TX discard was introduced. The existing burst yield remains. A 20 ms event wake checks an asserted RX-only ready level. SPI diagnostics expose separate wait_txn_timeouts, recovered_lost_ready, and retry_exhaustions (also transport_recoveries). The BLE probe now uses one in-flight short-token ping and records ordered results so unsolicited modem events cannot be mistaken for replies.
Static verification: `Tools/Build-NonSecureIncremental.ps1` PASS (NonSecure binary 433136 bytes; existing RWX LOAD-segment warning); `python -m compileall -q hil_tests` PASS; `python hil_tests/self_test.py` PASS; `git diff --check` PASS (line-ending warnings only). All firmware loads used `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run`; external NOR was unchanged. A temporary experiment using DMA for the 8-byte SPI header yielded four complete BLE/USB/reconnect passes, but the fifth RAM boot failed W6X_Init with `wait_msg_xfer_timeouts=2` and `transport_recoveries=1`. Because DMA cache maintenance of a short stack header could affect adjacent cache-line data, that experiment was reverted and none of those four passes counts toward the final-build 5/5 gate.
Final polling-header build, clean RAM boot A: pre-test BLE advertising, radio max_gap_ticks=31, SRAM4 3184 bytes/26 fragments. Full 45 s report `hil_tests/results/m37_polling_probe1.json`: 222/222 BLE replies, p95=150.868 ms, no reconnect; concurrent USB 13/13, p95=30 ms. After BLE disconnect, advertising resumed, radio max_gap_ticks=450, SRAM4 3184 bytes/32 fragments. Fresh reconnection report `m37_polling_probe1_reconnect.json` connected but failed its first ping (0/1). Subsequent GDB snapshot: SPI io_err=2, wait_txn_timeouts=0, recovered_lost_ready=0, transport_recoveries=0, retry_exhaustions=0, HAL READY, ErrorCode=0; BLE CLI TX had one 4-byte drop. This boot fails the acceptance sequence.
Final polling-header build, clean RAM boot B: pre-test BLE advertising, SRAM4 3184 bytes/26 fragments. An initial idle BLE connection passed 10/10. Full 45 s report `m37_polling_boot2_full.json`: 220/220 BLE replies, p95=149.635 ms, no reconnect; concurrent USB 13/13, p95=16.3 ms. After disconnect, fresh reconnection report `m37_polling_boot2_reconnect.json` passed 10/10. Final radio max_gap_ticks=50, SRAM4 3184 bytes/30 fragments, BLE CLI RX/TX drops=0. GDB SPI snapshot: wait_txn_timeouts=0, recovered_lost_ready=1, transport_recoveries=0, retry_exhaustions=0, io_err=0, HAL READY. This is an observed lost-ready recovery with continued communication, and counts as only 1/5 consecutive complete boots.
Final polling-header build, next clean RAM boot C: pre-test SPI error/timeout/recovery/exhaustion counters all zero, radio max_gap_ticks=22, SRAM4 3184 bytes/26 fragments. The 45 s `m37_polling_boot3_full.json` connected at MTU 247 but failed its first BLE ping (0/1) before a Wi-Fi request was submitted; concurrent USB was 13/13, p95=16.5 ms. Post-failure GDB: SPI io_err=1, wait_txn_timeouts=0, recovered_lost_ready=0, transport_recoveries=0, retry_exhaustions=0, HAL READY, ErrorCode=0. COM6 also reported `VL53L9CX ERROR: DSS map command` during the same boot; causality versus the BLE first-reply failure is not established. BLE disconnect restored advertising; radio max_gap_ticks=50, SRAM4 3184 bytes/30 fragments. This breaks the consecutive sequence at 1/5.
Result and open risk: M3.7 is not VERIFIED. The targeted TXN_RDY retry path is bounded, and one recovered ready edge was observed with traffic continuing, but intermittent SPI I/O/first-reply failure and a concurrent ToF sensor fault prevent the required five consecutive full boots. No retry exhaustion or NCP reset was observed in the final polling-header boots, but zero missing BLE replies was not achieved across boots. Do not close the Milestone 3 gate or start M3.8.
```

```text
2026-09-23  M3.8  VERIFIED FOR SUBMISSION-ONLY CLI; M3.7/GATE REMAIN OPEN
Decision: The user explicitly authorized M3.8 despite the failed M3.7 five-consecutive-boot HIL. This is a sequencing exception, not acceptance of M3.7 or of the Milestone 3 gate. The intermittent BLE first-reply/SPI I/O failure and the observed ToF DSS fault remain open and are not attributed to M3.8.
Files changed for M3.8: AppliNonSecure/Core/Src/debug_cli.c; docs/async-architecture-recovery-plan.md; AGENTS.md; README.md; CHANGELOG.md. No M3.9 result routing or worker/queue/vendor change was made.
Implementation: `wifi disconnect [forget]` zeroes a stack-owned `WifiBle_WifiRequest_t`, sets DISCONNECT, the active `CliSession_t.route`, and the optional forget bit, then calls `WIFI_BLE_App_WifiSubmit()`. It reports acceptance with a nonzero request ID or rejection with the ThreadX code and returns immediately. The 10-second CLI wait and final W6X status print were removed. The existing blocking application API remains as a transitional adapter until M3.10, but `debug_cli.c` no longer calls it.
Verification: `Tools/Build-NonSecureIncremental.ps1` PASS (432904-byte NonSecure binary; 449792-byte C heap; pre-existing RWX linker warning). `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` PASS; Secure and NonSecure ran from SRAM and external NOR was unchanged. Preflight COM8 `radio status`: manager ready, W6X_Init passed, BLE advertising on, max_gap_ticks=13. USB `wifi disconnect` returned ID 1 and prompt in 30.4 ms; `wifi disconnect forget` returned ID 2 and prompt in 31.0 ms. Four immediate USB pings passed in 30.2–36.3 ms. BLE inspector found `N6-MAINT-B8FB`, connected at MTU 247, and subscribed to CLI TX. BLE `wifi disconnect` returned ID 3 and prompt, followed by `PONG m38-ble-live`; BLE `wifi disconnect forget` returned ID 4 and prompt, followed by `PONG m38-ble-forget`. A concurrent USB ping series completed 24/24 (observed 28.4–47.0 ms). BLE disconnect restarted advertising. Final COM8 status: Wi-Fi STA DISCONNECTED; BLE ready/disconnected/advertising; CLI RX 4 events/89 bytes and TX 16 messages/2912 bytes with zero drops/retries/errors; SRAM4 3184 bytes/31 fragments; radio max_gap_ticks=37 and BLE TX max_gap_ticks=41. No pre-existing BLE first-reply failure appeared in this M3.8 smoke run. The disconnect operation was brief, so these host measurements establish immediate CLI responsiveness after submission but do not time the exact worker execution interval.
Remaining risk: Four owned result slots were consumed by the four requests in this intermediate M3.8 boot because M3.9 result draining does not exist yet; a fresh RAM load is needed before more queued Wi-Fi tests. Final disconnect/forget outcome was not routed to the caller and is not claimed as tested. M3.7 remains unchecked, the five-boot BLE failure remains open, and the Milestone 3 gate remains unchecked. Stop before M3.9.
```

```text
2026-09-23  M3.9  VERIFIED FOR USB/BLE ROUTING; M3.7/GATE REMAIN OPEN
Files changed: AppliNonSecure/Core/Src/debug_cli.c; docs/async-architecture-recovery-plan.md; AGENTS.md; README.md; CHANGELOG.md. No M3.10 blocking-API removal was performed.
Implementation: `Debug_CLI_Run()` polls up to two `WIFI_BLE_App_WifiReceiveResult()` snapshots per iteration after synchronizing the BLE/Cloud lifecycle and the USB ready/reset state. A completed result is rendered only when transport and nonzero session generation match a currently ready session. The BLE check also re-reads connected/transport-ready/CLI-subscription/runtime-generation state. Results with no current matching session are counted as stale and dropped after the receive API has scrubbed/released their slot. The result line includes operation, request ID, final W6X text and numeric status; successful scans print at most 15 bounded AP entries, and successful connects print the snapshotted SSID/IP. `debug route` exposes routed/stale/write-error counters. All result text is deferred while XMODEM or any session's hidden-password prompt is active; CLI-owned result snapshots are zeroed after use. There are no new cross-task session pointers.
Build/source verification: `Tools/Build-NonSecureIncremental.ps1` PASS (434272-byte NonSecure binary; 448448-byte C heap; existing RWX LOAD-segment warning). Focused source review confirms the only result consumer is the CLI task, reception is `TX_NO_WAIT`, the per-iteration bound is two, and result output is guarded by route equality plus live transport state. `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` PASS; Secure/NonSecure ran from SRAM, external NOR unchanged.
RAM HIL, same boot: initial radio manager ready, W6X_Init passed, BLE advertising, max_gap_ticks=21. Six sequential USB `wifi disconnect` submissions returned IDs 1..6 and six matching final `ERROR (2)` outcomes (the station was already disconnected); `debug route` reported routed=6, stale=0, write_errors=0. This exceeds the four result slots and proves release/reuse. With BLE connected at MTU 247, USB disconnect ID 7 produced its result only on USB; BLE scan ID 8 produced an `OK (0)` result and 11 APs only on BLE; routed then reached 8 with no stale/write error. A BLE connect ID 10 to an absent SSID returned `ERROR (2)` to the old BLE session before disconnect; that quick attempt was not used as stale evidence.
Deliberate BLE generation test: three `wifi scan` commands were written over one GATT write, then the BLE central disconnected immediately. The CLI recorded two stale results and one output write error from the in-flight disconnect race. A fresh BLE connection reached generation 7, answered `PONG m39-new`, and `debug route` showed routed=10, stale=2, write_errors=1; none of the old scan results appeared in that new session. The earlier single-scan disconnect attempt completed before disconnect and was not counted as a stale test.
USB-disconnected test: USB scan request ID 14 was accepted, COM8/DTR was closed immediately, then reopened after four seconds. The new USB session showed its menu and `debug route` at generation 8 with stale=3; no result for ID 14 appeared there. XMODEM test: USB scan ID 15 was followed immediately by `update` in the same CLI stream. For four seconds the update stream contained only the update instructions and XMODEM CRC `C` bytes, not the Wi-Fi result. Two CAN bytes safely cancelled the receiver before any package block; only then did scan result ID 15 and 13 APs print. The final result counters were routed=11, stale=3, write_errors=1.
Final hardware status: BLE disconnected and advertising, Wi-Fi services enabled, radio/BLE max_gap_ticks=85, SRAM4 radio pool 2256 bytes/33 fragments after the vendor's lazy scan allocation. BLE stream diagnostics recorded nine TX-message drops, one retry, one error and 15 stale-generation fragment drops during the deliberately interrupted scan-output/disconnect sequence; they are not presented as a clean BLE health pass. There was no observed cross-route result or result text during XMODEM. Cloud generation is checked in source, but asynchronous Cloud output was not exercised on HIL and can fail if no relay command is active; `write_errors` makes that failure visible. M3.7's intermittent BLE first-reply/SPI issue and five-consecutive-boot gate remain open, and so does the Milestone 3 gate. Stop before M3.10.
```

```text
2026-09-23  M3.9 FOCUSED FOLLOW-UP + M3.10  BUILD/RAM HIL VERIFIED; CLOUD HIL DEFERRED; M3.7/GATE OPEN
Files changed: AppliNonSecure/Core/Src/debug_cli.c; AppliNonSecure/Core/Inc/cloud_relay.h; AppliNonSecure/Core/Src/cloud_relay.c; AppliNonSecure/Core/Inc/wifi_ble_app.h; AppliNonSecure/Core/Src/wifi_ble_app.c; docs/async-architecture-recovery-plan.md; README.md; CHANGELOG.md. The earlier M3.9 history above describes its earlier build and is retained as historical evidence, not as a claim about the new code.
M3.9 correction: The CLI records the nonzero request ID for a Wi-Fi request submitted inside the currently leased Cloud text command. It suppresses CloudRelay_CompleteCommand() and next-command reads until that exact ID/route has produced output, so the Relay still has the originating active_command_id. Source review of the local Relay server (`server/N6.CloudRelay/RelayRegistry.cs`) showed that ACK clears its lease, so `CloudRelay_AcknowledgeInput()` now atomically arms a `hold_command` bit for asynchronous Wi-Fi input; the Relay continues ACK/output work but does not poll a different command until the completed output record is accepted. Reconnect/unpair/disable clear the hold. The Cloud result is one compact output record (operation, ID, final status, scan count and IPv4); `CloudRelay_TryWriteOutput()` copies it atomically with TX_NO_WAIT and never enters the existing 15-second output wait. A full Relay queue causes retry from CLI-owned storage, not global CLI blocking. A Cloud generation change clears the binding and makes the old result stale. Each CLI poll first considers four fixed, CLI-owned deferred snapshots, then receives at most two fresh results with TX_NO_WAIT. XMODEM or secret entry defers only the owning session's result. The worker result slot is released immediately; if all four CLI deferral entries are occupied, an explicit deferred_overflow counter records the lost presentation rather than blocking other transports. The `debug route` output exposes that counter and cloud_pending ID. No cross-task CliSession_t pointer was introduced.
M3.10 correction: Removed the three blocking public WifiScan/WifiConnect/WifiDisconnect declarations and definitions, legacy pending-operation/credential/done-event adapter, and the worker's legacy-request branch. The worker still uses a bounded scan-completion event internally, which is not a caller-facing blocking API. `rg -n "WIFI_BLE_App_Wifi(Scan|Connect|Disconnect)" AppliNonSecure/Core/Inc AppliNonSecure/Core/Src` found no matches except unrelated internal SCAN_DONE identifiers when using a broader pattern.
Verification: `Tools/Build-NonSecureIncremental.ps1` PASS (NonSecure binary 434952 bytes; C heap capacity 443904 bytes versus 368640 minimum; pre-existing RWX linker warning only); `git diff --check` PASS (line-ending warnings only); `python -m compileall -q hil_tests` PASS; `python hil_tests/self_test.py` PASS. `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` PASS, both local images running from SRAM; external NOR unchanged. First COM8 read without DTR produced no output, then DTR-enabled COM8 replied normally. Six sequential USB `wifi disconnect` requests returned IDs 1..6 and six matching ERROR (2) results; `debug route` showed routed=6, stale=0, write_errors=0. A sandboxed WinRT BLE attempt saw N6 advertising but failed at connect with E_FAIL before GATT; a second, elevated attempt connected at MTU 247 and subscribed to CLI TX. In that connection BLE `wifi scan` ID 7 returned OK and 13 networks only over BLE while USB `wifi disconnect` ID 8 returned ERROR (2) only over USB. While USB was held at a hidden password prompt, BLE `wifi disconnect` ID 9 returned its result; while BLE was held at a hidden password prompt, USB `wifi disconnect` ID 10 returned its result. Both prompts were cancelled, no password was submitted. `debug route` then showed routed=10, stale=0, write_errors=0, deferred_overflow=0, cloud_pending=0. A later USB `wifi scan` ID 11 was followed by `update`; its scan text was absent from the four-second XMODEM transfer window and appeared only after CAN-CAN cancellation. These are focused HIL checks, not a repeat of M3.7's five-boot latency gate.
Cloud HIL: `cloud status` on the RAM image reported `waiting for Wi-Fi, not paired`, generation 0 and zero received/acked/output records. No Cloud command could be submitted end to end, so the corrected asynchronous Cloud association is source/build verified only and remains hardware-deferred. Cloud Wi-Fi disconnect could also remove the network path needed to upload its own result; that case requires a paired relay/reconnect test and is not claimed as passed. M3.7 remains unverified and the Milestone 3 gate remains open. Stop before M4.
Final Cloud lease-hold revision: rebuilt successfully (NonSecure binary 434832 bytes; C heap capacity 444032 bytes), reloaded Secure/NonSecure from RAM without external NOR writes, and repeated six USB `wifi disconnect` submissions (IDs 1..6, six matching ERROR (2) results, routed=6/stale=0/write_errors=0/deferred_overflow=0). On this exact final image, elevated WinRT BLE connected at MTU 247, BLE `wifi scan` ID 7 returned OK with 15 APs only on BLE while USB `wifi disconnect` ID 8 returned ERROR (2) only on USB. This final-image smoke test did not repeat the earlier password/XMODEM checks, which were run on a preceding build before the Cloud-only output/lease changes. Cloud end-to-end remains unverified; M3.7 and the Milestone 3 gate remain open.
```

```text
2026-09-23  M4.1  IMPLEMENTED / BUILD PASS / CONCURRENT BLE HIL FAILED; STOP BEFORE M4.2
Code scope: ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c, function modem_cmd_send_ext() only. The existing indefinite sem_tx_lock take was replaced with xSemaphoreTake(..., timeout); failure returns -ETIMEDOUT before touching command state, and an acquired-lock flag gates the single unlock path. xTaskGetTickCount() is sampled before acquisition and again just before modem_cmd_handler_await(); elapsed unsigned ticks (including command writes) are subtracted from the supplied timeout, saturating the reply wait at zero. The timeout==0/no-response-semaphore behavior remains nonblocking for lock acquisition. No M4.2 manual-lock change was made.
Build/source: Tools/Build-NonSecureIncremental.ps1 PASS (NonSecure binary 434832 bytes; C heap capacity 444032 bytes, above the 368640-byte floor; existing RWX LOAD-segment warning only). Source review confirmed the FreeRTOS compatibility xSemaphoreTake maps finite TickType_t to tx_mutex_get finite ticks and xTaskGetTickCount maps to tx_time_get. RAM load via Tools/Debug-NonSecureRam.ps1 -NoBuild -Run PASS; Secure/NonSecure executed from SRAM, external NOR unchanged. Initial COM8 baseline: manager ready, BLE advertising, max_gap_ticks=22, BLE TX max gap=22, Debug UART queued/sent=95/95 and drops/timeouts=0.
Concurrent HIL run 1: elevated WinRT BLE probe `ble_inspector.py --pair --uncached-services --probe wifi-blocking --probe-seconds 45 --report hil_tests/results/m41_probe.json` connected at MTU 247, submitted a known-absent SSID at 8.503 s, then FAILED: 18/19 replies, one missing, p50 92.471 ms, p95 263.543 ms, maximum 636.724 ms, zero reconnects. The missing sample was sequence 19; sequence 11 took 636.724 ms. In parallel 24/24 USB debug pings passed in 29..33 ms. After disconnect BLE advertising resumed. Radio max_gap_ticks=520 and BLE TX max_gap_ticks=522; BLE CLI RX drops=0, TX dropped 2 messages/6 bytes, retries/errors=0, stale drops=0; Debug UART drops/timeouts/hal_errors=0. ST67 logging interrupt_rejections=1. SRAM4 radio pool 3280 bytes free/30 fragments after disconnect.
Concurrent HIL run 2 on the same RAM boot: identical 45-second probe using hil_tests/results/m41_probe_repeat.json connected at MTU 247, submitted another absent SSID at 4.300 s, then FAILED: 15/16 replies, one missing, p50 123.116 ms, p95 262.771 ms, maximum 522.525 ms, zero reconnects. The missing sample was sequence 16; sequence 11 took 522.525 ms. In parallel 24/24 USB pings passed in 30..59 ms. Final BLE advertising resumed; radio/BLE max gaps remained 520/522 ticks, BLE CLI RX drops remained 0, TX drops remained 2 messages/6 bytes (no additional TX drops in run 2), retries/errors/stale drops=0, Debug UART queued/sent=224/224 with zero drops/timeouts/hal_errors; ST67 logging interrupt_rejections=3. SRAM4 radio pool 3280 bytes free/30 fragments. No unexpected reconnect or reset was observed in either probe.
Interpretation: The code-level M4.1 timeout budget is implemented and build-verified, but two concurrent probes failed BLE latency/missing-reply acceptance. These failures are not presented as a passing HIL result or proof of a specific remaining lock cause. M3.7, its five-consecutive-boot requirement, Cloud end-to-end HIL, and the Milestone 3 gate stay open. M4.2 was not started.
```

```text
2026-09-23  M4.2  IMPLEMENTED / BUILD PASS / ONE FULL 45-SECOND BLE-WIFI PROBE PASS; STOP BEFORE M4.3
Code scope: ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c only. W61_AT_Common_Query_Parse() and W61_AT_Common_RequestSendData() now acquire sem_tx_lock with pdMS_TO_TICKS(timeout_ms) instead of portMAX_DELAY and return W61_STATUS_TIMEOUT immediately if acquisition fails. Query/Parse does not modify mdm->rx_data/argc/argv until after acquisition and passes only the remaining tick budget to modem_cmd_send_ext(); if acquisition consumed the entire budget, it releases the acquired lock and returns timeout without sending. RequestSendData does not reset its shared semaphores before acquisition; its existing out path is reachable only after a successful acquisition, so it releases only an owned lock. Its later '>' and 'Recv ' waits retain their existing bounds and were not redesigned in M4.2. No M4.3 BLE-lock code was changed.
Verification: Tools/Build-NonSecureIncremental.ps1 PASS (NonSecure binary 434896 bytes, C heap 443968 bytes above the 368640-byte floor; existing RWX linker warning only). Source review/rg shows no sem_tx_lock acquisition with portMAX_DELAY in w61_at_common.c; git diff --check PASS (line-ending warnings only). Tools/Debug-NonSecureRam.ps1 -NoBuild -Run PASS; Secure/NonSecure executed from RAM, external NOR unchanged. Before probe: radio manager/GATT ready, BLE advertising, max_loop_gap_ticks=12 and max_ble_tx_gap_ticks=12, SRAM4 radio pool 3280 bytes/26 fragments; BLE RX/TX accepted/dropped all zero; Debug UART 94 queued/94 sent, zero drops/errors.
Focused concurrent HIL: elevated WinRT `ble_inspector.py --pair --uncached-services --probe wifi-blocking --probe-seconds 45 --report hil_tests/results/m42_probe.json` connected at MTU 247, submitted absent SSID N6-HIL-MISSING-00007908 at 4.123 s, and completed the whole 45-second probe: PASS, 221/221 BLE PONGs, zero missing, zero duplicate replies, zero reconnects, p50 101.965 ms, p95 169.995 ms, maximum 184.771 ms. The JSON report retains raw CLI transcript and 247 raw notification records. Concurrent USB `debug ping m42-1..24` passed 24/24 in 30..46 ms. After disconnect BLE advertising resumed; radio max_loop_gap_ticks=40, BLE TX max_gap_ticks=48, SRAM4 pool 3280 bytes/30 fragments. BLE CLI RX accepted 224 events/2950 bytes with 0 drops; BLE CLI TX accepted 239 messages/6248 bytes, sent 6248, 0 drops/retries/errors/stale drops; total GATT writes 224, discarded bytes 0. Debug UART queued/sent 169/169, 0 drops/timeouts/HAL errors; ST67 logging 0 buffer exhaustions and interrupt rejections. Wi-Fi result routed=1, stale/write_errors/deferred_overflow=0.
COM6 caveat: During this RAM boot, repeated `VL53L9CX ERROR: sensor init (code -5)` appeared; `tof status` confirmed state=error, frame=0 and 0.0 fps. COM6 also logged W6X_Ble_SetConnParam error 2, while the GATT probe continued, and the expected Wi-Fi connect error for the absent SSID. This is a passing targeted BLE/Wi-Fi test with zero missing replies, not a full-system load/soak pass. Because there was no missing PONG, no received/generated/enqueued/notified loss point needed localization in this run. M4.1's two failed HIL probes are retained as failures and M4.1 is not relabeled verified. M3.7, its five-consecutive-boot test, Cloud HIL and the Milestone 3 gate remain open. Stop before M4.3.
```

```text
2026-09-23  M4.3  IMPLEMENTED / BUILD PASS / ONE FULL 45-SECOND BLE-WIFI PROBE PASS; STOP BEFORE M4.4
Code scope: ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_ble.c and the shared W61_AT_Common_RequestSendData() in w61_at_common.c, only as needed for the notification deadline. All three BLE manual sem_tx_lock takes (GetService, GetCharacteristic, SecurityGetBondedDeviceList) now use the 2000 ms NCP budget and test pdPASS. They return W61_STATUS_TIMEOUT without touching shared modem response state if the lock is unavailable; after acquisition they subtract elapsed ticks, skip sending if exhausted, and release only the lock they own. The notification no longer silently enlarges the caller's 100 ms timeout to 2000 ms. RequestSendData now counts lock wait, command response, '>' wait, data-write progress and final 'Recv ' wait against one operation deadline, checking remaining ticks before each wait. Its existing lock-failure path returns without unlocking; the common out path is only reached after acquisition. The shared helper is also used by other transports, so their send-data timing is affected; no M4.4 manual Wi-Fi lock or CLI code was changed.
Static/build: `Tools/Build-NonSecureIncremental.ps1` PASS (NonSecure binary 434960 bytes; C heap capacity 443904 bytes above the 368640-byte floor; existing RWX LOAD-segment warning only). `rg -n "sem_tx_lock.*portMAX_DELAY" ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_ble.c` returned no match (exit 1). `git diff --check`, `python -m compileall -q hil_tests`, and `python hil_tests/self_test.py` PASS (line-ending warnings only from Git). `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` PASS; Secure/NonSecure ran from SRAM, external NOR unchanged. Baseline COM8: radio/GATT ready and BLE advertising; max_loop_gap_ticks=22, BLE TX max_gap_ticks=22, SRAM4 radio pool free=3280 bytes/26 fragments, BLE RX/TX drops=0, Debug UART queued/sent=111/111 with zero drops/timeouts.
Focused HIL: elevated `ble_inspector.py --pair --uncached-services --probe wifi-blocking --probe-seconds 45 --report hil_tests/results/m43_probe.json` connected at MTU 247, submitted absent SSID N6-HIL-MISSING-00006338, and completed the full 45 seconds: PASS, 223/223 PONGs, missing=0, duplicates=0, reconnects=0, p50=113.899 ms, p95=152.095 ms, max=337.894 ms. Parallel COM8 `debug ping m43-1..24` passed 24/24. After BLE disconnect advertising resumed. Final COM8: max_loop_gap_ticks=50, BLE TX max_gap_ticks=42; SRAM4 pool free=3280 bytes/30 fragments. BLE RX accepted 226 events/2976 bytes, drops=0; BLE TX accepted 241 messages/6276 bytes and sent 6276, drops=0, retries=1, errors=1, stale drops=0. Debug UART queued/sent=166/166, drops/timeouts/HAL errors=0; ST67 logging buffer_exhaustions/interrupt_rejections=0. Wi-Fi result routed=1, stale/write_errors/deferred_overflow=0. The one BLE TX retry/error did not cause a missing reply and remains observable; its precise AT failure was not localized in this probe.
Caveat: COM6 repeatedly reported VL53L9CX sensor init (-5), and the final `tof status` showed state=error after 607 acquired frames, with frame-acknowledge command error (-1). Therefore this is one passing targeted BLE/Wi-Fi probe, not a complete full-system soak. M4.1's two early-stopped probes remain failures and M4.1 is not verified. M3.7's five-consecutive-boot test, Cloud HIL and the Milestone 3 gate remain open. M4.4 was not started.
```

```text
2026-09-23  M4.4–M4.6  IMPLEMENTED / BUILD PASS / CONCURRENT HIL MIXED; NO COMMIT OR PUSH
Files changed in this pass: ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/{w61_at_common.c,w61_at_common.h,w61_at_wifi.c,w61_at_net.c,w61_at_sys.c}; AppliNonSecure/Core/{Inc/wifi_ble_app.h,Src/wifi_ble_app.c,Src/debug_cli.c}; README.md; CHANGELOG.md; this plan. Earlier dirty-tree changes were preserved.
M4.4: All three Wi-Fi manual TX-lock sites (GetCredentials, AP_ListConnectedStations, TWT_GetStatus) now call W61_AT_Common_TakeTxLockBudget() with W61_NCP_TIMEOUT=2000 ms. A zero return leaves no lock owned and returns W61_STATUS_TIMEOUT before mdm->rx_data or caller output is touched; the nonzero remaining tick count is the modem command/reply budget. The intermediate incremental build passed (NonSecure 434960 bytes; C heap 443904 bytes).
M4.5: Three Network sites (PullDataFromSocket, SNTP_GetTime, GetSocketInformation) and three System sites (ReadEFuse, FS_ReadFile, FS_ListFiles) use the same bounded helper, release only after a nonzero acquisition result, and pass remaining ticks to modem_cmd_send_ext. PullDataFromSocket uses its caller Timeout; other Network sites use W61_NET_TIMEOUT=6000 ms; System uses W61_NCP_TIMEOUT=2000 ms. The intermediate build passed (NonSecure 435088 bytes; C heap 443776 bytes). `rg -n "sem_tx_lock.*portMAX_DELAY" ThirdParty/ST67W6X_Network_Driver/Driver/W61_at` returned exit 1/no matches.
M4.6: BLE CLI/DEBUG active TX slots and ToF image frames now retain their state and offset on W6X_STATUS_BUSY or W6X_STATUS_TIMEOUT and return to the Radio Manager loop; ordinary errors still use the pre-existing three-attempt retry/drop path. Disconnect, unsubscribe or changed generation still drops stale active data before any later send. Public BLE status snapshots and `ble status` expose per-stream/image busy_count, timeout_count, current/peak streak, current/peak duration in ThreadX ticks, and recoveries after a successful send. Ended/cancelled streaks do not count as recovery. The final incremental build passed (NonSecure 436480 bytes; C heap 442400 bytes above the 368640-byte floor; existing RWX LOAD warning only). `git diff --check` passed (CRLF warnings only), `python -m compileall -q hil_tests` passed, and `python hil_tests/self_test.py` passed. No automated host test exercises the C transient branch directly.
RAM/HIL: `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` loaded Secure/NonSecure to SRAM only, but the first boot reported `W6X_Init: failed` and was not eligible for a BLE probe. A second RAM load reached radio/GATT ready with advertising on; baseline max_loop_gap_ticks=22, BLE TX max_gap_ticks=22, SRAM4 radio pool free=3184 bytes/26 fragments, and all BLE contention/drop counters zero. Elevated `ble_inspector.py --pair --uncached-services --probe wifi-blocking --probe-seconds 45 --report hil_tests/results/m44_m46_probe.json` connected at MTU 247, submitted absent SSID N6-HIL-MISSING-00007768, then FAILED EARLY at 14/15 PONGs, one missing (token F), p50=103.977 ms, p95=241.537 ms, max=430.790 ms, reconnects=0. Its raw transcript contains no PONG F. Parallel USB pings passed 24/24. At that point radio max_loop_gap_ticks=120, BLE TX max_gap_ticks=121; BLE CLI TX dropped=0, ordinary retries/errors=0, contention busy=0/timeouts=2, peak streak=2, peak duration=20 ticks, recoveries=1. BLE CLI RX dropped=0; ST67 logging interrupt_rejections=4. Zero TX drops proves no slot eviction was counted, not where PONG F was lost.
Repeat on the same RAM boot using hil_tests/results/m44_m46_probe_repeat.json completed the full 45 seconds: PASS 222/222 PONGs, zero missing, p50=106.125 ms, p95=150.164 ms, max=500.716 ms, reconnects=0; 24/24 parallel USB pings passed. Post-disconnect advertising resumed; cumulative BLE CLI TX dropped=0, ordinary retries/errors=0, contention busy=0/timeouts=5, peak streak=3, peak duration=29 ticks, recoveries=2; radio/BLE maximum gaps remained 120/121 ticks, SRAM4 radio pool free=3184 bytes/30 fragments. Debug UART queued/sent=219/219, drops/timeouts/HAL errors=0. The first failed probe remains a failure: two probes are not a successful consecutive soak. Cloud Relay contention was not tested because no paired Relay session was available; ToF image notifications were not subscribed/tested. ToF was initially ready during the first probe but later reported a separate DSS unmap command error (-1); causal independence is not proven. M4.1 stays unverified, M3.7 five-boot and Cloud HIL stay open, and neither Milestone 3 nor Milestone 4 gate is closed. No CubeMX, external NOR write, commit or push was performed.
```

```text
2026-09-23  M4.4–M4.6 FINAL DEADLINE REFINEMENT / FRESH RAM PROBE PASS; PRIOR FAILURE OPEN
The private TakeTxLockBudget helper now also returns the lock-wait start tick. All nine Wi-Fi/Network/System manual-lock callers recompute remaining time immediately before modem_cmd_send_ext, after local command preparation, and release an owned lock/return W61_STATUS_TIMEOUT if the budget is exhausted. Shared mdm->rx_data and output fields are assigned only after that second check. `Tools/Build-NonSecureIncremental.ps1` passed again (NonSecure 436608 bytes; C heap 442272 bytes; existing RWX warning). RAM-only load passed; radio/GATT initialized on this boot and initial radio/BLE max gaps were 31/31 ticks.
On this exact final image, elevated WinRT report `hil_tests/results/m44_m46_final_probe.json` completed 45 seconds of BLE pings during absent-SSID Wi-Fi association: PASS 222/222, zero missing, p50=83.241 ms, p95=149.209 ms, max=501.773 ms, reconnects=0; concurrent USB `debug ping m46f-1..24` passed 24/24. After BLE disconnect advertising resumed. Final status: radio max_loop_gap_ticks=120, BLE TX max_gap_ticks=121; CLI RX accepted 225 events/2963 bytes, dropped=0; CLI TX accepted 240 messages/6264 bytes and sent 6264, dropped=0, ordinary retries/errors=0; contention busy=0, timeout=3, peak streak=3, peak duration=30 ticks, recoveries=1, current streak=0. SRAM4 radio pool free=3184 bytes/30 fragments; Debug UART queued/sent=144/144 with zero drops/errors, ST67 logging interrupt rejections=0. ToF remained ready at final snapshot but image notifications were not subscribed. `cloud status` reported `waiting for Wi-Fi, not paired`, generation 0 and zero CLI traffic, so Cloud contention could not be tested. This final pass does not erase the earlier 14/15 failure on the preceding build or prove repeated-boot soak. Milestone 4 gate stays open.
```

```text
2026-09-24  AUTOMATED M3.7/M4 REPEATABILITY GATE / HIL FAIL
Added hil_tests/run_milestone4_gate.py to reload Secure/NonSecure into RAM, check CN8 radio/BLE/ToF/Wi-Fi, run the existing BLE Wi-Fi-blocking probe alongside 24 USB pings, collect counters, and require five consecutive passes within seven attempts. The runner now stops when this becomes mathematically unreachable, rejects stale raw reports, and retries transient Dropbox replacement locks. ble_inspector.py continues after a PONG has been missing for one second while retaining that sample as a failure; this makes subsequent recovery observable. BLE CLI startup sends a short readiness line rather than the multi-kilobyte help banner. The W61 linear RX allocation now reserves one extra byte because direct-event parsers write rx_buf[rx_buf_len] even when the buffer is full. Incremental NonSecure build passed (436512-byte binary; C heap 442368 bytes, existing RWX warning). Python py_compile, hil_tests/self_test.py, and scoped git diff --check passed.
An elevated 20-second short-banner RAM smoke passed 97/97 BLE replies, zero missing, p95 156.2 ms and 8/8 USB pings. The first full 45-second gate had BLE 221/221 on attempt 1 but ToF DSS map error; attempts 2 and 3 lost one PONG each. The initial probe then stopped sending after that miss, so these were not evidence of a sustained 45-second stall. After the probe correction, a three-boot run reported ToF preflight error, then a BLE connection without an initial prompt (GATT writes=1, discarded byte=1), then 207/210 BLE replies with three missing and 24/24 USB pings; ToF later reported frame-acknowledge error. The short-banner and RX guard therefore did not close the gate.
On the final RX-guard image, hil_tests/results/milestone4_gate_rx_guard.json is a complete FAIL report. Attempt 1: BLE 148/162 (14 missing), USB 24/24, ToF DSS unmap error (-1), CLI RX/TX dropped 0/0. Attempt 2: BLE 222/222, p95 156 ms, USB 24/24, ToF DSS unmap error (-1), CLI RX/TX dropped 0/0. Attempt 3: RAM load failed because the ST-LINK GDB server exited before accepting a connection. The runner stopped at 0/5 consecutive passes because five successes were no longer reachable in seven total attempts. Radio/BLE maximum gap on both completed probes was 120 ticks. This verifies that BLE can recover after missed replies but does not locate where GATT writes were lost. Cloud contention and ToF image notifications were not tested. No external NOR write, CubeMX, commit or push was performed.
```

```text
2026-09-25  SECURE-FAULT AFTER WI-FI GOTIP  DIAGNOSTIC BUILD; ROOT CAUSE/HIL OPEN
User-observed browser BLE stream later ended in SECURE-FAULT after Wi-Fi GOTIP, with SFAR reported as 0x00000EBC. The earlier Python/Bleak failure is not assumed to be the same fault. Existing Secure_FaultTrace printed fault status registers but only decoded PSP_NS when it pointed into SRAM2; ThreadX radio stacks can be in SRAM4. No fault PC, LR, xPSR, EXC_RETURN or SFSR validity bit from the failing boot has yet been captured, so 0x00000EBC is not assigned to a source instruction or treated as a proven valid SFAR.
Exact-ELF DWARF inspection gives `offsetof(W61_Object_t, Modem.sem_response) == 0xEBC`; vendor `W61_NULL_ASSERT` checks are compiled out by default (`W61_ASSERT_ENABLE=0`). This is a null-object-dereference candidate only, not a root-cause finding: the actual GOTIP callback does not directly read this field, and a PC/instruction plus valid SFAR is needed to establish the access path. No speculative change was made to GOTIP, modem ownership or ToF.
Diagnostic change: Secure fault handlers now pass their entry EXC_RETURN to Secure_FaultTrace. It selects Non-Secure MSP/PSP and basic/FP frame from EXC_RETURN, accepts aligned complete frames in the configured SRAM2..6 Non-Secure range (including SRAM4), checks stacking-error bits and the CMSE Non-Secure read permission before dereferencing, then prints stacked LR/PC/xPSR. Secure-origin frames are deliberately not decoded from a C-time MSP value. SFSR/SFAR and other existing registers remain visible, with a notice when SFARVALID is clear.
Verification: Secure incremental build PASS; Non-Secure incremental link/build PASS (446952-byte binary, 429328-byte C heap capacity); objdump of SecureFault_Handler confirms LR is captured before the call; Python compileall and hil_tests/self_test.py PASS; git diff --check PASS (line-ending warnings only). The diagnostic image has NOT been loaded to RAM or tested against the fault. COM6 read failed with access denied while Tera Term was running. STM32CubeProgrammer ST-LINK listing returned DEV_USB_COMM_ERR, and ST-LINK GDB server in attach mode returned USB communication error; no reset, Flash write or SWD fault-register read was performed. Need the preserved COM6 fault log and restored ST-LINK communication before same-image reproduction and exact-ELF PC mapping. Root-cause change, ToF causal assessment, 20/20 Wi-Fi+BLE cycles, wrong-network/credential and reconnect tests remain OPEN.
Repeat after the user released COM6: COM6 opened successfully but yielded zero new bytes (past terminal output cannot be replayed); STM32CubeProgrammer `-l stlink` still returned DEV_USB_COMM_ERR, and a read-only SWD HOTPLUG read of SFSR/SFAR also failed with the same USB communication error before any target read. COM8 remained access-denied, presumably held by another client. No reset or reprogramming was attempted in this repeat.
User then explicitly requested reprogramming and retest. A fresh STM32CubeProgrammer `-l stlink` still returned DEV_USB_COMM_ERR; Windows enumerated the exact ST-Link Debug interface `USB\VID_0483&PID_3754&MI_00\7&2d1716e9&0&0000` as Started. A targeted `pnputil /restart-device` for that interface was attempted with tool escalation but Windows returned `Access is denied`. Consequently no RAM image was loaded, no Wi-Fi connection or BLE/ToF HIL ran, and no root cause or PC was claimed. Physical ST-LINK USB re-enumeration or OS administrator action is required before the requested reproduction can resume.
After the cable was disconnected/reconnected, STM32CubeProgrammer detected ST-LINK SN `000C00344142501620353451` (FW V3J17M11). `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` then PASS: local Secure and Non-Secure binaries loaded into SRAM via FSBL handoff; external NOR unchanged. COM6 confirmed Secure handoff, ThreadX startup, W6X SDK 2.0.106, BLE GATT registration/advertising and Wi-Fi station readiness. COM8 baseline: Radio Manager ready, W6X_Init passed, Wi-Fi disconnected, BLE advertising; BLE CLI RX/TX drops 0, Debug UART drops/timeouts 0. The ToF DSS-unmap error (-1) occurred during startup at tick 7311, before any Wi-Fi request; `tof status` subsequently showed state=error after 14 acquired frames. This establishes temporal separation from GOTIP, not independent root cause. A five-minute no-Wi-Fi COM8 `debug ping` run passed 1040/1040 with zero missing, p95 32.5 ms and max 52.1 ms; after it, radio/BLE loop max gap was 22 ms and BLE GATT still advertised with no GATT writes or TX drops. No browser BLE/Wi-Fi connection was performed in this run: the user's external browser tab was not exposed to the available browser-control surface and no test credentials were provided. Therefore GOTIP, fault PC, root-cause fix and 20-cycle acceptance all remain OPEN; idle USB stability is not a substitute.

2026-09-25  POST-GOTIP HARDFAULT REPRODUCED; NULL NETWORK CONTEXT PROVEN; FIX UNDER HIL
With the user initiating a browser BLE Wi-Fi connection against the same RAM image, COM6 recorded `ST67W6X Wi-Fi connected.` immediately before `[SECURE-FAULT] HardFault`, `HFSR=0x40000000`, `SFSR=0x00000048` (AUVIOL and SFARVALID), `SFAR=0x00000EBC`, `EXC_RETURN=0xFFFFFFA9`, `MSP_NS=0x241FFF08`, and `PSP_NS=0x242D1D98`. The EXC_RETURN-only diagnostic wrongly selected MSP_NS and printed a zero PC; read-only SWD Hot Plug inspection of PSP_NS yielded a plausible frame with stacked `PC=0x2413FE8E`, `LR=0x24140CE1`, `xPSR=0x61000000`. The exact failing `N6_AppliNonSecure.elf` SHA-256 was `D3C430FA313A578A2792B0D14EEA4CB15A0FE5B544F2C09885E4F86602A2CB99`. `arm-none-eabi-addr2line` mapped PC to `W61_AT_Common_SetExecute` at `w61_at_common.c:492` and LR to `W61_Net_SNTP_SetConfiguration` at `w61_at_net.c:1126`. Disassembly at PC is `ldr.w r4,[r0,#0xEBC]`, reading `Obj->Modem.sem_response`. SWD confirmed both `W6X_Net_drv_obj` and `p_net_ctx` were NULL in that failing image. Root cause is missing `W6X_Net_Init()` at Radio Manager startup: GOTIP activates `CloudRelay_Process`, which calls `W6X_Net_SNTP_SetConfiguration` through the uninitialized vendor Net object. This is a proved null dereference, not a speculative GOTIP callback or ToF buffer fault. Vendor NULL assertions are disabled in this build.
Focused change: register a Network callback, initialize W6X Net after Wi-Fi initialization and before Cloud Relay startup, and gate all Cloud initialization/processing on successful Net initialization. If Net initialization fails, log it and leave Cloud disabled while retaining Wi-Fi/BLE. Unpaired Cloud with no pending pair request now skips synchronous SNTP after GOTIP, avoiding unnecessary Radio Manager delay; pairing still retains SNTP. Secure fault reporting now checks both NS MSP/PSP and basic/extended frame layouts with complete SRAM2..6 range, CMSE readability, and plausible Thumb xPSR/nonzero PC, labeling any candidate rather than trusting the anomalous EXC_RETURN stack bit. Secure incremental build PASS; final `Tools/Build-NonSecureIncremental.ps1` PASS (449736-byte NonSecure binary, 426544-byte C heap capacity); Python compileall and `hil_tests/self_test.py` PASS; `git diff --check` PASS (CRLF warnings only). `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` loaded both corrected images to SRAM without changing external NOR. COM8 on the first corrected image reported Radio Manager ready, BLE advertising, Cloud Relay waiting for Wi-Fi, `PONG net-init`, 60/60 idle USB pings with maximum 47.6 ms, and SRAM4 radio pool 2924 bytes/33 fragments. The final Cloud guard image has been loaded to SRAM but its Wi-Fi/BLE connection test is pending user browser action; the 20-cycle acceptance and bad-password/reconnect tests remain OPEN. ToF requires independent testing.
Final Cloud-guard RAM image idle observation: 75/75 USB `debug ping` replies, zero missing, maximum 46.5 ms. At radio tick 174751, BLE remained advertising/disconnected, accepted GATT writes 0, SRAM4 free 2924 bytes/33 fragments and radio max loop gap 31 ms. COM6 capture had no new Secure fault or Wi-Fi connect event. Thus these data are *idle baseline only*, not a post-GOTIP or BLE-under-Wi-Fi pass. Browser action was requested but no connection occurred within the capture window; no 20-cycle or negative-path result is claimed.
The user then initiated one browser BLE Wi-Fi connection with the final SRAM image while COM6 and COM8 were captured. COM6 showed `ST67W6X Wi-Fi connected.` followed by `ST67W6X Wi-Fi address acquired.` and no Secure fault. COM8 `wifi status` confirmed STA GOT IP (`192.168.68.58`, gateway `192.168.68.1`, RSSI -42 dBm); `cloud status` was unpaired with HTTP inactive, so the new unpaired guard took effect. 90/90 concurrent USB pings returned (zero missing, maximum 46.9 ms). Final BLE status was connected at MTU 247, CLI TX 5920 bytes sent, zero CLI RX/TX drops, zero CLI TX errors, four transient notification timeouts with one recorded recovery, and SRAM4 free 2924 bytes/36 fragments. Radio max loop gap 40 ms, BLE TX max gap 41 ms. COM6 recorded BLE disconnect/reconnect events; the user confirmed these were intentional and that the browser received IP and BLE command replies after the connection. It also recorded `W6X_Ble_ServerNotify` errors and `W6X_Ble_SetConnParam` failures, despite the final zero CLI TX error/drop counters; keep them as observed diagnostics rather than hiding them. This is one successful *manual* Wi-Fi+BLE cycle of the required 20, not a 20/20 pass. ToF continued to emit DSS-map errors and remains a separate unresolved issue. Bad credentials/network and Wi-Fi disconnect/reconnect acceptance remain open.
The user explicitly chose to stop after this one cycle. COM6 capture was closed without resetting the board; the corrected firmware remains in volatile RAM. The acceptance gate remains OPEN at 1/20; no soak, negative-credential, or Wi-Fi reconnect result is inferred from this run.

2026-09-25  M5.1  VERIFIED UNDER USER-APPROVED SEQUENCING EXCEPTION
Decision: the user authorized proceeding to the next task despite open Milestone 3/4 and post-GOTIP HIL gates. Only M5.1 was implemented; M5.2 was not started. `CloudRelay_WriteOutput()` now calculates required 384-byte slots, acquires its gate with `TX_NO_WAIT`, rejects insufficient capacity with `TX_QUEUE_FULL` before copying, fills every slot while unpublished, then commits tail/count once. `CloudRelay_CompleteCommand()` also acquires without waiting and rejects a full queue immediately. `CloudRelay_TryWriteOutput()` delegates to the same atomic admission path. The output consumer's head/count update uses a short critical section matching the producer commit. The previous 15-second retry/sleep loop was removed. The capacity is eight slots (3072 bytes total); storage is a fixed 3104-byte application-SRAM BSS array, not a radio-pool allocation. The Cloud context shrank from 8160 to 6612 bytes. No allocation is added after initialization.
Verification: final `Tools/Build-NonSecureIncremental.ps1` PASS (449816-byte NonSecure binary; C heap 423376 bytes, 54736 above the 368640-byte minimum). ELF `gdb` reports `sizeof(CloudRelayContext_t)=6612` and `sizeof(cloud_output_slots)=3104`; `nm -S` places the latter at `0x24180990` in application SRAM. The private initialization self-test executes on every Cloud startup: seven slots filled; a 385-byte/two-slot write rejected with unchanged count/tail and untouched eighth slot; one completion marker accepted and a second rejected when full; a 385-byte write and completion then accepted from empty; all test data cleared. `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` PASS on the exact final image, external NOR unchanged. COM8 reported Cloud Relay `waiting for Wi-Fi` with zero output queued (Cloud initialization would have failed if the self-test failed), BLE GATT advertising, `PONG m51-final`, SRAM4 radio-pool free 4472 bytes/31 fragments versus 2924 bytes before M5.1, and radio max gap 22 ms. Python compileall, `hil_tests/self_test.py`, and `git diff --check` passed (CRLF warnings only). No paired Cloud end-to-end transaction was available, so that HIL remains deferred. Milestone 5 gate is OPEN; Milestone 3/4 gates, M3.7 repeatability, and the post-GOTIP 20-cycle gate (1/20) remain OPEN. No CubeMX, external NOR write, commit or push.
```

```text
2026-09-25  POST-M5.1 BLE TX STALL INVESTIGATION — RAM LOADED; ROOT CAUSE OPEN
The user's `ble status` showed an active-but-unusable BLE link: four CLI TX messages queued, 4,138 consecutive notification timeouts, zero recoveries, zero ordinary TX drops, and a probe timestamp approximately 51 minutes old. `wifi status` also showed a failed W6X_WiFi_Station_GetState query (status 3) despite a saved GOTIP/IP shadow. The live `C:\Users\netan\Dropbox\DevelopPersonal\N6\COM_INNER_LOGS.txt` capture began after the initiating failure; it shows ongoing W6X_Ble_ServerNotify timeouts and repeated Wi-Fi query timeouts but cannot establish whether the first failure was AT-lock contention, lost modem response or SPI transport loss. `COM_LOGS.txt` was empty at inspection. Neither log was deleted or truncated. Error timestamps use 100 Hz ThreadX ticks; repeated 12-tick gaps represent approximately 120 ms, consistent with the 100 ms notification budget plus manager cycle.
Confirmed liveness defect: `ble_probe_shadow()` skipped all BLE mode/link probes whenever any CLI/DEBUG TX was queued or a ToF image remained active, making a permanently retained transient-timeout slot suppress the only link reconciliation indefinitely. The focused Non-Secure change retains normal traffic protection but allows a bounded probe at the existing 15-second interval after five seconds of continuous TX contention. It logs one stalled-TX/SPI-counter/pin snapshot to COM6 per sustained episode. It does not drop the active packet, reset the NCP, change Wi-Fi/Cloud state, or assert that a successful recovery occurred. Whole-NCP reset requires coordinated quiescence of the Wi-Fi worker, Cloud and SPI/AT ownership and is not enabled from this evidence alone. Follow-up RAM/HIL must capture COM6 from before reset, reproduce Wi-Fi/BLE traffic, compare SPI TX/RX/error/transaction-ready counters and BLE probe outcomes, and test disconnect/re-advertise; all affected milestone and 20-cycle gates remain OPEN.
Verification: `Tools/Build-NonSecureIncremental.ps1` PASS, 450448-byte binary and 422736-byte C heap (minimum 368640); only the existing RWX LOAD warning. `git diff --check`, `python -m compileall -q hil_tests`, and `python hil_tests/self_test.py` PASS (Git CRLF conversion warnings only). At the user's request, `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` loaded the locally built Secure and Non-Secure images through the verified FSBL handoff, reached Non-Secure main/ThreadX and detached. The Tera Term USB log `COM_LOGS.txt` then captured the fresh version-5 CLI menu at 17:15:18. `COM_INNER_LOGS.txt` remained at 195090 bytes with last write at 17:14:27, before the RAM load, so COM6 logging must be restored before a fault-reproduction run. Neither log was cleared. No post-load Wi-Fi/BLE fault reproduction or recovery HIL has been performed; external NOR was unchanged. No CubeMX, commit or push.
```

```text
2026-09-25  CLOUD TLS TAG-LIST DIAGNOSIS AND FOCUSED FIX — RETEST FAILED LATER AT CIPSTART
The user authorized an independent dual-COM Cloud pairing probe. A RAM image with Wi-Fi GOT IP remained unpaired: `cloud status` request errors rose from 5 to 6, backoff remained 60 seconds, and no HTTP status was received. COM6 captured `[w6x_net.c:1891] Invalid TLS credential` during the pending pairing attempt. Source review located the mismatch: `cloud_relay.c::cloud_begin_request()` stored one tag as `int32_t tags[1]` but passed `sizeof(tags)` (4) to `TLS_SEC_TAG_LIST`; `w6x_net.c::W6X_Net_Setsockopt()` interprets `optlen` as a count of `int8_t` tags, so little-endian tag 7 was read as tags 7,0,0,0 and the undefined tag 0 was rejected. This is a representation/count mismatch, not an out-of-bounds read. The caller now passes one tag while retaining the 32-bit backing required by the vendor function's unconditional `int32_t` load from `optval`. No vendor library or M5.2+ code changed.
Verification: `Tools/Build-NonSecureIncremental.ps1` PASS (450448-byte Non-Secure binary, 422736-byte C heap), `git diff --check` PASS, Python `compileall -q hil_tests` PASS, `hil_tests/self_test.py` PASS. `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` loaded the corrected Secure/Non-Secure image into SRAM and detached; external NOR unchanged. Initial capture `training/reports/dual_com/20260925_213323/` reported BLE advertising, Radio Manager ready, Cloud waiting for Wi-Fi, zero Cloud request errors and 4472 bytes free in the SRAM4 radio pool; `PONG cloud-fix-idle` passed. After the user restored Wi-Fi through BLE, a fresh dual-COM capture `training/reports/dual_com/20260925_214231/` confirmed STA GOT IP and submitted the user's short-lived pairing code (redacted here). The former `Invalid TLS credential` did not recur: NCP trace showed certificate filesystem transfer, `AT+CIPSSLCCONF`, ALPN and SNI accepted. It then showed repeated `AT+CIPSTART` -> `ERROR` and `w6x_net.c:1286 Could not connect`, before any HTTP response. `cloud status` remained unpaired with request errors 8, HTTP status 0, backoff 60 seconds. A read-only workstation check got HTTP 200 from `/api/health`; a TLS 1.2 handshake succeeded, and the server-sent certificate chain terminated at the firmware's DigiCert Global Root G2. Those host checks do not prove ST67 TLS compatibility or locate the NCP rejection. Radio Manager max loop gap increased to 7150 ms during the Cloud retries; BLE was advertising/disconnected at final status, so BLE continuity under Cloud load was not verified. USB `PONG cloud-tls-final` passed, CLI RX/TX drops remained zero, NCP trace was turned off, and COM6/COM8 were released. This is a failed paired-Cloud HIL test, not a gate pass. The Cloud TLS failure and Radio/BLE blocking remain OPEN for focused follow-up; M5.2+ were not started, and earlier milestone/20-cycle gates remain unchanged.
```

```text
2026-09-25  CLOUD PAIR RETEST — FAILED-CONNECT SOCKET LEAK FIXED; TLS CONNECT STILL OPEN
The user supplied a fresh short-lived pairing code (not retained in this plan). In the pre-fix dual-COM capture `training/reports/dual_com/20260925_215029/`, `cloud pair` was queued with STA GOT IP, but Cloud request errors climbed from 11 to 18 and NCP trace showed only one DNS lookup, no later TLS setup or CIPSTART. Source inspection established a deterministic local resource leak: `W6X_Net_Socket()` has six slots (`W61_NET_MAX_CONNECTIONS` 5 plus one), and failed `W6X_Net_Connect()` leaves a socket ALLOCATED; the Cloud error path invokes `W6X_Net_Close()`, but that function previously did nothing for ALLOCATED sockets. Their copied TLS credentials also remained allocated. The observed exhaustion after earlier repeated CIPSTART failures is consistent with this path; it does not explain the NCP's original CIPSTART rejection.
Focused fix: `W6X_Net_Close()` now frees copied TLS credentials, clears an ALLOCATED socket, and restores its invalid connection number without issuing an NCP close for a connection that never formed. Cloud status now distinguishes socket allocation (-12), options (-13), connect (-14), and send (-15) failures. `Tools/Build-NonSecureIncremental.ps1` PASS (450576-byte Non-Secure binary, 422608-byte C heap); `git diff --check`, Python compileall and `hil_tests/self_test.py` PASS. `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` loaded Secure and Non-Secure to SRAM only, external NOR unchanged. Fresh capture `training/reports/dual_com/20260925_215658/`: after browser Wi-Fi reconnection, STA GOT IP, and ten Cloud attempts (including four manual `cloud reconnect` requests) all reached TLS setup/CIPSTART and failed with `Could not connect`; `cloud status` showed transport -14 and request errors 10, never -12. This proves socket slots are reusable past their six-slot capacity, but pairing remains unverified. The final radio/BLE-loop max gap was 254 ms; BLE was advertising/disconnected when measured, so connected BLE continuity was not proved. USB `PONG cloud-socket-7` passed, BLE CLI RX/TX drops were zero, and SRAM4 pool free was 3416 bytes/39 fragments. The pairing attempt was then stopped with `cloud disable` to avoid indefinite retries; this volatile RAM session remains Cloud-disabled until `cloud enable` or a reset.
Read-only workstation TLS 1.2 measurement against the same Azure endpoint with the correct SNI found a valid certificate chain and matching SAN, but the first server handshake record payload was 6603 bytes (`openssl s_client -tls1_2 -servername <host> -connect <host>:443 -debug`). Asking for TLS Maximum Fragment Length 4096 did not change that record length and the server did not advertise that extension (`-maxfraglen 4096 -tlsextdebug`). [ST's T01 HTTPS guidance](https://wiki.st.com/stm32mcu/wiki/Connectivity:Wi-Fi_ST67W6X_HTTPS_Client_Application) documents a 6144-byte maximum plaintext fragment on the ST67W611M1 and warns that servers not honoring MFL can fail. Thus the 6603-byte record is a strong, directly measured explanation for the NCP `CIPSTART` rejection, but the NCP's detailed error code was not captured, so this remains a high-confidence inference rather than a proved NCP failure reason. Do not disable certificate validation to work around it. A smaller-record TLS endpoint/certificate chain or a host-side TLS (T02) architecture would require a separate design decision. The NCP TLS/TCP rejection, Radio Manager blocking during synchronous Cloud calls, BLE continuity under Cloud load, and all prior gates remain OPEN. ToF DSS-unmap errors were also observed independently and are not attributed to Cloud.
```

```text
2026-09-25  CLOUD TLS SERVER-VERIFICATION DEMO SWITCH — RAM HIL IN PROGRESS
At the user's explicit request for a demonstration-only bypass, `APP_ST67W6X_CLOUD_TLS_VERIFY_SERVER` was added to `app_features.h` and set to 0 in the current demo build (set to 1 to restore validation). When 0, Cloud skips CA credential installation and `TLS_SEC_TAG_LIST`, so the vendor socket's auth mode stays 0; the TLS 1.2 socket, SNI hostname, SNTP prerequisite, HTTP path, and all other connection behavior remain unchanged. This is encrypted but *unauthenticated* TLS: a network attacker could impersonate the Cloud server and obtain a pairing code/token. Do not classify it as security-verified or use real secrets on an untrusted network. `cloud status` prints `TLS server verification: DISABLED (insecure demo)`, and COM6 emits a boot warning.
`Tools/Build-NonSecureIncremental.ps1` PASS (448720-byte Non-Secure binary, 424464-byte C heap); `git diff --check`, Python compileall and `hil_tests/self_test.py` PASS. `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` loaded the image to SRAM only; external NOR unchanged. The first post-load observation had `W6X_Init` failed before Cloud initialization, so it is not TLS HIL evidence. A second SRAM load with `training/reports/dual_com/20260925_223215/` already capturing startup showed W6X SDK 2.0.106, BLE advertising, Cloud initialization warning, Radio Manager ready, `W6X_Init` passed, and `cloud status` displaying the insecure setting while Wi-Fi is disconnected.
After the user restored Wi-Fi and supplied a short-lived code, the capture `training/reports/dual_com/20260925_230515/` confirmed STA GOT IP and the insecure TLS setting. The pairing request was queued, but four attempts stopped at NCP `AT+CIPSTART` -> `ERROR` (`w6x_net.c:1306 Could not connect`), before any HTTP response; final Cloud status was unpaired, `last_http_status=0`, `last_transport_status=-14`, `request_errors=4`. Disabling certificate verification therefore did not resolve the connection failure. This observation remains consistent with, but does not independently prove, the previously measured oversized TLS record; the NCP's detailed failure reason is still unknown. BLE was advertising/disconnected at the final status, with CLI RX/TX drops zero, so connected BLE continuity was not tested. Cloud was disabled after the failed retries to avoid continued network requests; NCP trace and dual-COM capture were closed. The local COM log contains the CLI echo of the short-lived pairing code and should not be shared without redaction. Cloud pairing and all related gates remain OPEN.
After a host-PC restart on 2026-09-26, `Tools/Build-NonSecureIncremental.ps1` again passed (`make: N6_AppliNonSecure.bin is up to date`; same 448720-byte binary and 424464-byte C heap). `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` again loaded Secure and Non-Secure into SRAM and detached; external NOR was not modified. Capture `training/reports/dual_com/20260926_114154/` shows COM6 and COM8 online, `W6X_Init: passed`, BLE GATT ready and advertising, Radio Manager loop active (max gap 31 ms at first status), Wi-Fi disconnected after reboot, and Cloud waiting for Wi-Fi with zero request errors. A new pairing/TLS attempt has not yet been made on this boot and requires Wi-Fi reconnection and a fresh pairing code. No Cloud or BLE-under-Cloud HIL pass is claimed.
After the user restored Wi-Fi and provided a new short-lived code, capture `training/reports/dual_com/20260926_114638/` confirmed STA GOT IP (`192.168.68.66`) and queued Cloud pairing. The NCP accepted SNTP time, DNS, `AT+CIPSSLCCONF`, ALPN, SNI, TCP options and receive-buffer setup, then rejected `AT+CIPSTART` with `ERROR` before HTTP. Two attempts produced `last_transport_status=-14`, `last_http_status=0`, `request_errors=2`; Cloud remained unpaired and was explicitly disabled to stop retries. The radio/BLE TX max loop gap reached 7490 ms. Subsequent `ble status` showed advertising/disconnected, CLI RX/TX drops zero, SRAM4 radio-pool free 4472 bytes in 36 fragments; USB `debug ping cloud-after-fail` returned `PONG`. Thus connected BLE continuity was not measured. One SPI RX HAL error and a Wi-Fi state-query error occurred before the first connect attempt; their causal relationship to the repeatable `CIPSTART` rejection is not established. Disabling certificate verification has failed to make this Azure endpoint connect on two separate RAM boots; the oversized TLS record remains a strong candidate, not a proved module error code. The local COM capture contains the short-lived code echoed by CLI and must be redacted before sharing. Cloud pairing, BLE-under-Cloud HIL and prior gates remain OPEN.
The user requested a control experiment against a common HTTPS host and suggested redirects as a possible cause. A *temporary RAM-only* diagnostic build replaced the Cloud host with `www.google.com` and the pending-pair action with `GET /generate_204`, with no body and no pairing code transmitted. The first RAM load had an unrelated pre-request `W6X_Init` failure and was not counted. The second RAM load passed `W6X_Init`; after the user reconnected Wi-Fi, capture `training/reports/dual_com/20260926_120545/` confirmed STA GOT IP and showed DNS, TLS setup, `AT+CIPSTART` -> `+CIP ... CONNECTED`/`OK`, `AT+CIPSEND`, 172 outbound bytes, and 222 inbound bytes via `AT+CIPRECVDATA`. `cloud status` reported HTTP 204, transport 0, unpaired. Its `request_errors=1` is expected because the existing pairing-response parser intentionally rejects Google's non-pairing 204; it is not a transport failure. Radio/BLE TX max loop gaps were 62/60 ms and USB `PONG google-probe` passed. Repeated ToF DSS-unmap errors were visible but were not attributed to TLS. This proves the module and current TLS-without-verification stack can complete HTTPS and HTTP against Google; it does not prove the precise Azure failure mechanism or anything about HTTP redirects at the Azure application, because Azure fails before any HTTP request is sent.
Both temporary source substitutions were then reverted: `CLOUD_RELAY_HOST` again names the Azure endpoint and pairing again uses `POST /api/device/pair`. The final incremental build passed and reproduced the original 448720-byte Non-Secure binary/424464-byte C heap. `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` loaded that restored image to SRAM only; capture `training/reports/dual_com/20260926_121204/` confirmed `W6X_Init: passed`, BLE advertising, Radio Manager ready, Azure endpoint restored, and Cloud waiting for Wi-Fi with zero request errors. External NOR was unchanged. The control result is verified; Cloud pairing, the Azure `CIPSTART` cause, and BLE-under-Cloud acceptance remain OPEN.
2026-09-26 Azure default-host TLS investigation (read-only; no firmware or cloud deployment): an OpenSSL TLS 1.2 handshake to the exact Azure App Service hostname with correct SNI and `-debug` again received a single first server handshake record of `0x19CB = 6603` bytes, carrying the Azure-managed `*.azurewebsites.net` RSA certificate chain; OpenSSL verified the chain. The same command to `www.google.com` received a 63-byte ServerHello record followed by a 3772-byte certificate record, matching the board's successful Google HTTPS probe. Offering TLS Maximum Fragment Length 4096 (`-maxfraglen 4096 -tlsextdebug`) did not alter Azure's 6603-byte record or elicit an MFL extension; omitting SNI also left it at 6603. An ECDSA-only TLS 1.2 cipher offer failed with alert 40, so this endpoint did not offer an alternate ECDSA certificate for that tested cipher. `curl.exe` GET to the Azure `/api/health` path returned HTTP 200 with no redirect. Source review of the separate Web project (`server/N6.CloudRelay/Program.cs`) found the direct `MapPost("/api/device/pair", ...)` route and no `UseHttpsRedirection`; Azure's HTTPS-only redirect applies to HTTP, whereas the device already connects to port 443 and fails before HTTP. The Web project's README records that the Azure app uses Free F1; an existing `n6iot.natilab.net` CNAME lacks an App Service hostname/TLS binding, which requires a supported paid App Service tier.
The 6603-byte unencrypted TLS 1.2 handshake record exceeds ST's documented 6144-byte T01 plaintext-fragment limit by 459 bytes. Together with the successful 3772-byte Google comparison and repeatable Azure `CIPSTART` failures even with certificate verification disabled, this is a high-confidence compatibility explanation, not a module-returned diagnostic code or a claim that the subdomain string itself is invalid. The default Azure hostname's certificate chain is managed by Azure, not by the ASP.NET application. No change to HTTP redirect handling can repair a pre-HTTP handshake failure. DNS lookup confirmed `natilab.net` uses Azure DNS nameservers and `n6iot.natilab.net` is currently a direct CNAME to the App Service default host, not an active alternate TLS endpoint. Proposed shortest demo path: an independently provisioned TLS-terminating reverse proxy with a measured <=6144-byte handshake record (for example a constrained Cloudflare Worker `workers.dev` proxy that needs no DNS-provider migration) forwarding only the device API to the original Azure HTTPS origin; validate its live record size and end-to-end pairing before switching the firmware endpoint, and restore server-certificate verification. Cloudflare Workers Free currently has a 100,000-request/day cap: the present approximately one-second polling alone can reach 86,400/day, before command/output/ToF traffic, so polling must be slowed or a paid tier chosen. An App Service Basic+ custom-domain certificate might also change the record size but requires cost and measurement; ST's T02 host-side LwIP/MbedTLS is the more robust architectural fix but requires NCP mission-firmware and host-stack migration with explicit BLE regression testing. None of these remedies has been deployed or HIL-verified; Cloud and prior gates remain OPEN.
```

```text
2026-09-26  T01 TLS INTEROPERABILITY — FAE REQUIREMENT RECORDED; NO VENDOR SUBMISSION
At the user's request, the requirement for a future ST FAE discussion is recorded in [ST67W611M1 T01 HTTPS interoperability](st67-t01-tls-interoperability-fae.md). The request is to keep TCP/IP and TLS in the ST67 T01 NCP while safely accepting legal TLS 1.2 server records above the documented 6144-byte T01 fragment limit (including the measured 6603-byte Azure handshake record), even when the server does not negotiate MFL. It explicitly requires certificate/hostname verification, bounded operation and meaningful NCP error diagnostics; TLS verification bypass and T02 migration are not proposed as the product fix. The evidence is a strong compatibility hypothesis, not an NCP-confirmed root cause or a demonstrated cryptographic/silicon defect. This documentation-only step made no firmware, cloud, NCP, or hardware change and did not run HIL; Cloud pairing and all existing gates remain OPEN. The draft has not been sent to ST.
```

```text
2026-09-26  PLAINTEXT HTTP CLOUD DEMO — USER-REPORTED PAIR; TOF SENSOR FAULT OPEN
At the user's explicit request for a T01-only insecure demonstration, the Cloud Relay's active transport was switched to ordinary TCP/HTTP 1.1 on port 80 to the unchanged Azure host/API. `APP_ST67W6X_CLOUD_USE_TLS=0` is the build-time switch; the HTTP path does not use a TLS socket, CA, SNI/TLS options or the TLS-only SNTP prerequisite. The former TLS code is retained behind the switch, and `APP_ST67W6X_CLOUD_TLS_VERIFY_SERVER` now defaults to 1 for a future TLS build. CLI `cloud status`/`cloud endpoint` and COM6 explicitly warn that pairing codes, bearer tokens, Cloud CLI and ToF uploads travel in cleartext. This is not a secure release or a fix for T01 TLS interoperability.
Verification: `Tools/Build-NonSecureIncremental.ps1` PASS (447856-byte Non-Secure binary, 425328-byte C heap), `python -m compileall -q hil_tests training/scripts` PASS, `hil_tests/self_test.py` PASS, `git diff --check` PASS (line-ending warnings only). `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` loaded Secure/Non-Secure into SRAM and reached ThreadX; external NOR was unchanged. Capture `training/reports/dual_com/20260926_142533/` showed `cloud status` at `http://...` with a plaintext warning, Wi-Fi STA GOT IP `192.168.68.71`, and no initial Cloud errors. One deliberately invalid `000000` pairing-code probe was queued; its first attempt reached the HTTP receive path but timed out with transport `-21`, HTTP status 0 and one request error, so this probe alone did not prove an HTTP server response. Direct workstation curl attempts to both ports 80 and 443 failed to connect in this environment and are not server-side evidence. The user subsequently reported a successful connection and real pairing code exchange on the RAM image. That is accepted as a user observation, but no post-pair `cloud status`/server evidence was captured here; ongoing Cloud CLI/ToF end-to-end HIL remains OPEN.
The same COM6 capture showed ToF advancing to `acquired=1507`, `processed=640`, `dropped=865`, then `FATAL at 'DSS map command', error=-1` at tick 157382. The failure followed successful frames; it was not a persistent sensor-init failure. No adjacent I3C event-wait or async-start diagnostic was logged, so the exact failing substep (command start, TX completion or blocking command-status read) is not proven. Source review shows the blocking command-status read can return `VL53L9_ERROR_PLATFORM` without the detailed I3C snapshot that the async/event paths emit; this is an observability gap, not yet a root cause. Earlier captures also reported DSS map/unmap and frame-acknowledge failures. `tof_fatal()` currently logs every two seconds forever, and planned M8.4a/M8.5 cover bounded local sensor/I3C recovery and the exhausted-fault policy. Two ST67 SPI RX HAL errors were logged before this ToF fault; any causal relationship is unproven. COM ports were no longer enumerated at the later status attempt, so a contemporaneous `tof status` and post-pair counters were unavailable. No ToF/radio fix, CubeMX operation, external-NOR write, commit or push was made for this review. ToF image delivery and its root cause remain OPEN.
```

```text
2026-09-26  TOF DSS-MAP ROOT-CAUSE INSTRUMENTATION — FIRST RAM BASELINE; RECOVERY NOT STARTED
Source review found that the earlier `DSS map command (-1)` could originate from its async command start, TX completion, or one-byte blocking command-status read. The blocking read previously collapsed descriptor, register-address TX, post-TX HAL-state wait, RX descriptor and data RX failures into one platform error; the post-TX state wait had no timeout. The new diagnostic build records the failing blocking-read stage with HAL status/state/ErrorCode/EVR in COM6 and the existing platform snapshot, bounds that state wait to 100 ms with a one-tick yield, and adds separate command TX-start, TX-completion, status-read and status-timeout counters to `tof status`. This is instrumentation and a bounded-wait safety fix, not proof of root cause or M8.4a recovery.
`Tools/Build-NonSecureIncremental.ps1` PASS (448904-byte Non-Secure binary, 424240-byte C heap; pre-existing RWX linker warning). `python -m compileall -q hil_tests training/scripts`, `hil_tests/self_test.py` and `git diff --check` PASS. Two `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` loads reached Non-Secure main/ThreadX; external NOR unchanged. Capture `training/reports/dual_com/tof_diagnostic_20260926/20260926_174943/` shows 3,785 acquired / 1,590 processed / 2,194 intentionally evicted under bounded processing backpressure, no ToF fatal, command-phase counters zero at the sampled `tof status`, and one successful eight-network Wi-Fi scan. This exceeds the prior 1,507-frame failure point but does not reproduce or disprove an intermittent fault. Capture `training/reports/dual_com/tof_diagnostic_20260926/20260926_175651/` is the final CLI-snapshot build: the later sampled `tof status` showed ready with 1,801 acquired / 781 processed, all four new command counters zero, and I3C HAL/start-read failures zero. USB re-enumerated after RAM load. The contemporaneous `wifi status` was STA DISCONNECTED and `cloud status` was waiting for Wi-Fi/not paired, so Wi-Fi association/Cloud/ToF image and transient/persistent fault injection were not tested in this diagnostic step. M8.4a/M8.5 and the ToF image gate remain OPEN; no ST67 driver, CubeMX, external-NOR, commit or push change was made.
```

```text
2026-10-03  M5.2–M5.4 RESUME — SOURCE/BUILD PASS; RAM HIL PENDING
The user requested continuation after reviewing the 17-thread source diagram and unfinished gates. Implemented one isolated Cloud worker, priority 9, fixed 8 KiB lower-SRAM4 stack. Priority 12 from the draft would be below the continuously-ready priority-10 ToF processor. Cloud control messages copy four ULONGs into four fixed slots; queue-full rejection, FIFO ordering and ownership/copy are checked before scheduler startup, and consumed pairing-code storage is scrubbed. Runtime pair/enable/disable/reconnect/unpair submit without waiting; only the worker closes sockets or saves/deletes pairing. Status snapshots do not acquire another subsystem's mutex. The initial NCP/Cloud initialization remains in Radio startup; the worker waits for completed initialization and scalar network readiness. The Cloud pump is private and has one caller.
The shared ToF snapshot now has an explicit lease before BLE READY. BLE terminal paths defer release in WAIT_CLOUD while Cloud still consumes the payload. No extra frame copy/buffer or dynamic steady-state allocation was added. Cloud input/output gates use TX_NO_WAIT; input ACK is a bounded metadata publication with command/sequence validation. All this requires concurrency HIL, not just compile acceptance.
Incremental and clean Non-Secure builds PASS. Final incremental binary: 451712 bytes; C heap: 420848 bytes, above the 368640-byte floor. Linker asserts pass for SRAM3/SRAM4; radio pool remains 65536 bytes. Eight ARM syntax checks passed across Cloud-disabled/radio-disabled modes; HIL utility self-test passed. GCC .su reports CloudRelay_Run 88 bytes, cloud_parse_command 2928 bytes, cloud_start_next_request 1672 bytes, and pairing parse/save 1192 bytes each; these individual frames are not a runtime high-water measurement.
Requested BOOT0=1-2, BOOT1=2-3 and RESET for RAM loading. No new image has been loaded to the board at this checkpoint. Existing Flash v7, the earlier Radio-pool starvation finding, ToF fatal recovery, M3/M4/post-GOTIP gates, M5.3 high-water and M5.4 latency/frame gates remain OPEN. M5.5 and Milestone 6+ were not started. No CubeMX/Generate Code, firmware version change, package signing, external-NOR write, commit or push.
```

```text
2026-10-03  M5 RAM STARTUP — OFFLINE WORKER PASS; NETWORK HIL PENDING
After the user confirmed BOOT preparation, Debug-NonSecureRam.ps1 -NoBuild -Run reached ThreadX with the locally built Secure and Non-Secure images. No loader external-NOR operation was performed. COM6 records the fixed-stack Cloud worker being created; its prerequisite fixed control-queue full/copy/FIFO self-test therefore passed. COM8 reported Cloud worker loops=3182, max step=0 ms, queue=0/4, Radio/BLE loop max gap=31 ms, radio pool available=4448 bytes/33 fragments, and ToF ready with acquired=671/processed=281 and zero command/I3C errors. The roughly 199-second runtime UART capture reached acquired=1936/processed=810 without a ToF fatal or fault log. This is an offline checkpoint, not a reproduction of Wi-Fi+Cloud+MAP load.
Attach-only GDB inspection (no reset/load) confirmed a distinct sleeping ST67 Cloud Relay thread at priority 9, stack start=0x242A1800, size=8192, loops advancing to 12031. The 0xEF stack-fill scan found 7836 untouched bytes / 356 observed used bytes in this offline phase; pairing, HTTP and ToF-send peak usage remains unmeasured. The kernel's created-thread list contains 19 entries, including the already-completed firmware-confirmation task, so 18 had not completed. The prior 17-entry diagram omitted the System Timer Thread: TX_TIMER_PROCESS_IN_ISR appears only in a comment. README and diagram are corrected; no scheduler/timer configuration was changed.
Two bounded PC BLE connection attempts (ordinary, then pair+uncached services; each with auto/public/random address types) saw N6-MAINT-B8FB at 40:82:7B:03:B8:FB in the RF scan, but WinRT returned no BluetoothLEDevice and Bleak raised DeviceNotFound before GATT discovery. Zero pings were sent; no BLE latency PASS is claimed. Saved ble-idle.json and ble-idle-pair.json preserve these failed host attempts. The exact cause of the host connection failure is unproven. Wi-Fi was disconnected and Cloud not paired; requested network/pairing input or a manual USB connection from the user. Both diagnostic ports were released afterward. M5.3 network stack high-water, M5.4 latency/CRC/lease/fault tests and M5.5 remain OPEN.
Evidence: Tools/.n6-debug/architecture-m5/ram-uart.log, usb-snapshot.json, ble-idle.json, ble-idle-pair.json, ram-startup-summary.json. No firmware-version change, signing, Flash release install, CubeMX generation, commit or push.
```

```text
2026-10-04  M5 RAM RELOAD — SPI RECOVERY SUBSTEP; BASELINE GATE STILL OPEN
The user confirmed RESET with BOOT1=2-3 and authorized RAM loading. Matching
local Secure/Non-Secure images reached ThreadX. USB showed version 7, Wi-Fi
disconnected, Cloud unpaired with zero requests, ToF ready and no I3C errors.
The restricted host environment could scan BLE but could not create the WinRT
device; the same bounded ping tool with approved host Bluetooth access connected
immediately. This access comparison does not prove a Windows cache defect.

Initial idle BLE probe: 3/9 replies, followed by persistent SPI errors. GDB
found SPI READY but TX DMA SUSPEND/EN with BUSY error; SPI transport recoveries
were counted without clearing the stranded channel. Memory-error counter was
zero. On the original build a fresh BLE connection passed 75/75, but the next
connection lost 9/69 replies. A failure-only breakpoint captured first SPI
ErrorCode=0x4 (RX overrun), before cleanup. Initial overrun cause is unproven;
this offline reproduction does not establish the earlier Cloud/MAP root cause.

Implemented bounded local cleanup in spi_port_abort: restore both owned
normal-mode DMA channels/parent links regardless of cleared SPI request bits;
after a failed SPI abort, reset only SPI5 and restore its registers. Keep the
handle READY so HAL_SPI_Init does not rerun the generated 480-byte MSP frame
on the 768-byte transfer-worker stack. No NCP/shared DMA reset or capacity
increase. DMA-only prototype still failed BLE (23/30) and was not accepted.
Final incremental build PASS: 452160-byte binary, 420368-byte C heap, unchanged
version/pools/stacks. One clean run passed 150/150, p95=140 ms, max=156 ms,
but did not exercise recovery and alone is not acceptance.

RAM handle-fault injection at idle set TX DMA handle SUSPEND, then injected
HAL_SPI_ERROR_ABORT at the next abort. Both recovery branches were exercised:
DMA reinitializations=3, SPI reinitializations=9, failures=0; SPI/RX/TX handles
READY, ErrorCode=0, retry exhaustion=0. BLE 88/100 replies during that test
failed; a subsequent probe without injection failed 68/83, p95=94 ms among
received replies. Counters then showed 25 IO errors, 28 transport recoveries,
4 DMA/18 SPI reinitializations, zero reinitialization failures or memory errors.
Thus permanent DMA stall recovery is demonstrated locally; reliable BLE and
initial overrun remain open. SPI stack fill measured 660/768 used, only 108
untouched bytes; no worst-case stack claim. USB remained usable, Radio/BLE max
loop gaps=50/51 ms, radio pool=4448 free bytes, ToF acquired=3536/processed=1474,
all command/I3C failure counters zero. Cloud was still waiting for Wi-Fi/unpaired.

Evidence: Tools/.n6-debug/architecture-m5/20261004_2234/ (initial, reproduce,
spi-cleanup, spi-peripheral-cleanup, spi-final). Attach-only failure breakpoint
before HAL overrun cleanup also captured BUSY_TX_RX, ErrorCode=0, SR=0x105A,
40-byte transfer with both DMA remaining counts zero and completion flags set.
It confirms latched OVR; it does not identify the transient scheduling/bus cause.
The associated breakpoint-run latency is perturbed and not a performance gate.

A subsequent RAM-only MASRX comparison changed only the master RX automatic
suspension configuration while SPI was idle. Two fresh MTU-247 connections
passed 150/150 each (p95=94/109 ms, max=110/125 ms). From the pre-change snapshot
through both runs, SPI IO errors=26, recoveries=31 and message timeouts=5 did
not increase. This motivated a source-build experiment with MASRX enabled
from boot, rather than accepting a transient live-register result. Incremental
build passed with the same size/heap. First boot stopped during
W6X_Ble_GetBDAddress on an SPI RX timeout; second boot reached radio READY but
failed BLE 78/91 (13 lost replies). A pre-abort timeout snapshot showed
SR=0x130800 (SUSP), CR1=0x1301, SPI BUSY, both DMA enabled/BUSY with no error,
RX remaining=19/40 and TX remaining=2/40. No OVR was recorded in this second
boot, but 14 RX completion timeouts occurred. The MASRX experiment is REJECTED
for this integration. N6.ioc and main.c were restored exactly to their prior
configuration; no Generate Code is now needed. ST AN5543's generic flow-control
guidance does not prove compatibility with this full-duplex driver. Precise
initial overrun cause remains open. Evidence also includes autosuspend/ and
autosuspend-startup2/; preserve both failed boots.

The restored configuration rebuilt successfully (same size/heap; git diff for
N6.ioc and main.c empty). Two further RAM loads, restored-final/ and
restored-final2/, both hit an SPI RX HAL error during W6X_Init/Get W61 Info and
left Radio ERROR. At the final snapshot USB/version 7 remained live, ToF was
ready with acquired=609/processed=256 and zero I3C/command failures. SPI and
both DMA handles were READY/ErrorCode=0, IO errors=1, transport recoveries=1,
no memory errors, retries exhausted or completion timeouts. Cloud remained
uninitialized (loops=0), not paired. This shows local transport cleanup cannot
make the failed higher-level initialization complete; initial SPI fault remains
the current blocker. Ports were released, and a full two-USB power cycle was
requested before the next RAM load. No power-cycle result is yet available.
The SPI stack binary was subsequently overwritten by the final startup
inspection and copied to restored-final2/spi-stack.bin; the earlier 660/768
stack observation remains recorded in the tool transcript, not in that latest
raw binary. Do not reclassify the overwritten dump as injection-run evidence.

M5.3 remains IN_PROGRESS; M5.4/network stack/CRC/lease gates and earlier gates
remain OPEN. M5.5 and later milestones not started. No firmware version change,
signing, external-NOR programming, CubeMX/Generate Code, commit or push.
```

```text
2026-10-06  M5 SPI BASELINE — RX DMA PRIORITY CANDIDATE; GENERATION/NETWORK OPEN
User confirmed the requested full two-USB power cycle, BOOT0=1-2/BOOT1=2-3.
Loaded the retained matching Secure/Non-Secure RAM images. The original
configuration again failed at SPI RX completion during W6X_Init/Get W61 Info;
power cycling did not establish a remedy. Git was initially clean at eca5b7e.

A diagnostic RAM loader used the same FSBL handoff and stopped only on an
overrun error branch. That baseline boot reached READY, but a BLE probe exposed
OVR again: SPI BUSY_TX_RX, SR=0x105A, both DMA completion flags set, no prior
IO/memory errors or recoveries. Its 47/52 BLE replies are affected by the
breakpoint and are not a latency gate. Startup intermittency remains open.

Changed only SPI5 RX DMA arbitration priority in RAM before scheduler startup:
channel 11 Init.Priority/CCR PRIO HIGH (0xC00000), TX LOW/HIGH_WEIGHT (0x800000).
First trial boot reached Radio READY but ToF failed sensor init -5; preserve it
as a failed system boot, not evidence that RX priority caused the sensor fault.
Second trial boot reached both READY and passed two fresh MTU-247 connections:
150/150 pings each, p95=141/140 ms, max=157/156 ms. GDB afterward showed SPI,
RX and TX READY/ErrorCode=0; zero IO/header/memory errors, all timeout counters
zero, transport recoveries/retry exhaustion zero, no reinitializations. USB
preflight showed ToF advancing, all I3C/command failure counters zero, radio
pool free=4448 bytes, Radio/BLE max gaps=40/40 ms. Cloud waiting for Wi-Fi,
unpaired, loops advancing, max step=1 ms. No pairing/HTTP load was tested.

Prepared the matching N6.ioc GPDMA1.PRIORITY_GPDMACH11 and MSP initializer.
Incremental Non-Secure build PASS: 452160-byte binary/420368-byte heap; same
fixed stack/pool sizes, SPI frequency/ports/bursts and disabled MASRX setting.
Ordinary Debug-NonSecureRam load (no runtime priority patch) reached radio and
ToF READY. Stage 11 on this source build PASS: 100 CRC-valid distinct frames,
100 frame-matched NPU results and bit-exact Python tensors, 100% class/decision
agreement, max raw-score delta 6, 100 non-empty and 14 distinct model inputs. Effective
output was 3.99 fps; 150/250 sensor IDs were skipped by bounded processing, not
CRC corruption or 10-fps throughput acceptance. Radio SDK 2.0.106, host BLE RF
scan and Wi-Fi station query/scan passed. Three AdvStart status-2 retries were
logged during radio preflight despite the RF scan; do not claim all vendor
control errors vanished. The source build received 150/150 idle BLE replies,
p95=141 ms/max=172 ms. Post-HIL attach found zero SPI IO/header/memory errors,
timeouts/recoveries/reinitializations and READY SPI/RX/TX handles.

The user then connected Wi-Fi over BLE and paired Cloud. At tick 276502,
USB had already observed ToF ERROR/frame 2687 while Cloud was still unpaired.
After pairing, Cloud received/acked two CLI commands and sent eight outputs,
last HTTP 204, zero request errors. Radio/BLE loop gaps=50/51 ms; BLE remained
connected; transport SPI counters stayed zero. No image was submitted or held:
image state FREE, submitted=0, Cloud pending=0, sent/dropped=0. No proof of a
Cloud frame-send or lease failure. MAP ON controls the terminal map flag;
enabled/paired Cloud independently requests images through
WIFI_BLE_App_IsTofImageSubscribed(). Opening the USB inspection session disables
the global terminal map flag, so the observed 'map off' is not evidence that
the user's Cloud command failed.

Post-fault attach-only evidence: I3C BUSY_TX_RX/ErrorCode=0x100000
(HAL_I3C_ERROR_SIZE), CR=0, EVR=3, IER=0, no active descriptor pointer;
persistent async context was register 0x0028, 2-byte address + 100-byte read.
All three DMA handles READY/error=0/remaining=0; RX CCR=0x7D04 retained
SUSP/SUSPIE, CSR=1 (IDLE, no suspension completion), XferAbortCallback still
I3C_DMAAbort, RX destination advanced by all 100 bytes. Platform recorded
8063 RX/8063 TX completions, one wait timeout (TX_NO_EVENTS=7), zero post/clear
failures and zero error callbacks. HAL's multiple-transfer ISR reports SIZE
if frame complete precedes final RX/TX DMA count zero; its error treatment
defers notification to an async DMA abort callback. This retained state
supports an RX completion/abort race that strands upper-layer notification.
It does not prove what caused the initial size mismatch. The first fatal
event was outside the 240-second UART capture, and preceding GDB attachment
may have affected timing. Do not attribute this to MAP ON/Cloud or promote
DMA-priority contention to a confirmed ToF root cause. tof_fatal() then
permanently sleeps/logs instead of acquiring new frames, explaining no map.
No ToF recovery or HAL mutation was performed. Cloud sentinel scan observed
4688 untouched / 3504 used bytes of its fixed 8192-byte stack after pairing/
HTTP/CLI; no stack contents or auth fields were saved. ToF-send peak remains
unmeasured. Follow-up USB PONG and advancing Cloud/Radio loops confirmed live
transport after attachment. UART capture closed; no reset/disconnect performed.

This comparison supports insufficient RX DMA arbitration priority as a cause
of the reproduced overrun; the exact competing bus transfer is not identified.
ST AN5593 describes GPDMA arbitration and SPI FIFO service requirements. The
earlier Radio-pool starvation and ToF fatal findings are not closed by this
offline baseline. M3/M4/M5.3/M5.4 acceptance and M5.5+ remain open.
Generate Code is REQUIRED/PENDING per AGENTS section 3; source candidate is
built/RAM-testable, but regenerated output and boot endurance remain unverified.
Evidence: Tools/.n6-debug/architecture-m5/20261006_power_cycle/ (initial,
baseline-overrun.log, rx-high, rx-high2, source-build, post-tof-fault). The latter
contains inspect_i3c2.log, inspect_routes.log, inspect_stack.log and USB/UART
snapshots. Two exploratory GDB scripts ended on unavailable pointer/Python
operations; subsequent successful detach and USB liveness checks retained the
fault without reset. Prior Stage 11 report
was copied before overwrite; new report/log copied into source-build. No
Flash programming, firmware-version change, signing, commit or push.
```

```text
2026-10-06  CONNECTED IMAGE-ROUTE REPAIR — RAM PASS, GLOBAL GATES OPEN
User authorized direct Wi-Fi association and site pairing/testing. Actual
browser Cloud images rendered before and after Cloud→BLE→USB→BLE handovers.
First connected run failed after raw-response fencing; retained in
Tools/.n6-debug/architecture-m5/20261006_cloud_verify/. BLE AT-lock admission
now returns BUSY immediately before raw announcement; the existing pump keeps
its fragment and retries. Full execution budget is retained upon admission,
with fail-closed raw-response fencing and safe phase/byte/tick diagnostics.
NS incremental build and ordinary RAM load PASS: 456632 bytes, heap 415864
bytes; unchanged capacities/version. --cloud HIL PASS: 20 BLE complete images,
25 USB records, all CRCs valid, no BLE image fragments while USB owns route,
Cloud accepted images fixed at 88 during BLE/USB. One interrupted BLE frame
and two cancelled images remain recorded at handover. Browser MAP ON resumed
Cloud; saved viewport proof frame 4039/CRC 3A6EA5E7. Final USB snapshot at
527516 ms: ToF READY/acquired 5218, zero command/I3C failures, Cloud accepted
468/dropped 0/request errors 0, Radio/BLE max gaps 50/43 ms, BLE disconnected
and advertising. HIL utility self-test, compileall/help and diff check PASS.
Evidence: Tools/.n6-debug/architecture-m5/20261006_cloud_repair/.
Pairing was re-established after RAM reload; persistent restore unverified.
No Flash/signing/version change/commit/push. IOC generation, network soak,
worst-case stack/failure latency and earlier gates remain OPEN; M5.3 remains
the sole IN_PROGRESS substep. Cloud browser tab retained as the live result.
```

# Final result record

Release request checkpoint (2026-10-06): user authorized persistent version 8.
Installed FSBL/Secure hash guard passed. Recorded the successful direct RAM
loader in Stage 10 with the current fingerprint and image hash; prior Stage
10 record was backed up. Stage 11 failed Wi-Fi scan preflight with timeout 3
under connected Cloud load, and error 2 after Cloud disable. No current-run
frame/NPU comparison took place. Retained failures and UART evidence in
Tools/.n6-debug/architecture-m5/20261006_flash_v8/. Sensor/USB remain live,
but other AT queries fail; exact cause is uncharacterized. PackageOnly v8
build/sign PASS (457920 bytes; SHA256 in package-summary.json), source header
restored to 7, no Flash writes. Requested BOOT0=1-2/BOOT1=2-3 without manual
RESET for a fresh RAM load and HIL. This supersedes the initial request to
switch BOOT1 to 1-2. Fresh HIL, subsequent BOOT1=1-2 transfer and confirmed
Flash boot remain outstanding. M5.3 and prior gates stay open.

- Final status: `IN_PROGRESS` — M5.3 IOC generation/boot endurance and ToF fault characterization; M5.4 frame/lease HIL pending; overall acceptance open
- Final revision: pending
- Secure build: pending
- NonSecure build: pending
- BLE idle p95: pending
- BLE Wi-Fi-failure p95/max: pending
- Maximum Radio/BLE loop gap: pending
- Debug UART dropped messages: pending
- Unexpected resets: pending
- Open risks: pending
