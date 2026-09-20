# Asynchronous Control-Plane Recovery Plan

Status: `PLANNED`

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

## [ ] PLANNED M0.1 — Add a transport-only ping command

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

## [ ] PLANNED M0.2 — Record Radio/BLE loop gaps

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

## [ ] PLANNED M0.3 — Add an automated latency probe

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
  - Date: pending
  - Firmware revision: pending
  - Idle p95: pending
  - Wi-Fi-failure p95/max: pending

### Milestone 0 gate

- [ ] Ping command builds and responds.
- [ ] Radio/BLE maximum loop gap is visible.
- [ ] A baseline latency report is recorded, or the milestone is marked blocked
  specifically because hardware is unavailable.

---

# Milestone 1 — Asynchronous Debug UART

Goal: make physical USART1 transmission owned by one task and keep every log
producer bounded and non-blocking.

## [ ] PLANNED M1.1 — Define the asynchronous UART API

- Files:
  - `AppliNonSecure/Core/Inc/debug_uart.h`
  - `AppliNonSecure/Core/Inc/logging_config.h`
- Functions/types to add:
  - `Debug_UART_AsyncInitialize()`
  - `Debug_UART_TaskRun()`
  - `Debug_UART_Flush()`
  - `Debug_UART_GetStatus()`
  - `Debug_UART_EmergencyWrite()`
  - `Debug_UART_IRQHandler()`
  - `DebugUart_Status_t`
- Change:
  - Define queue/sent/drop/timeout/HAL-error/high-water counters.
  - Retain the synchronous startup/fault API for use before ThreadX is ready.
- Acceptance:
  - Existing callers compile before their implementation is migrated.
- Verification:
  - Incremental NonSecure build.

## [ ] PLANNED M1.2 — Create fixed UART slots and pointer queues

- Files:
  - `AppliNonSecure/Core/Src/debug_uart.c`
- Functions:
  - `Debug_UART_AsyncInitialize()`
  - private queue/slot helpers
- Change:
  - Start with 16 fixed slots of 512 bytes.
  - Create free and ready pointer queues during initialization.
  - Producers acquire and enqueue with `TX_NO_WAIT`.
  - An arbitrary write longer than one slot is either admitted atomically into
    all required slots or rejected; never enqueue a silent partial message.
  - Track high-water and queue-full counters.
- Acceptance:
  - No allocation occurs after initialization.
  - A full queue returns immediately.
- Verification:
  - Incremental build and linker-map memory review.
  - Preserve the documented application-pool safety margin.

## [ ] PLANNED M1.3 — Implement the sole UART TX owner

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

## [ ] PLANNED M1.4 — Wire USART1 interrupt completion

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

## [ ] PLANNED M1.5 — Create the debug UART task early

- Files:
  - `AppliNonSecure/Core/Src/app_threadx.c`
- Functions:
  - `App_ThreadX_Init()`
  - new `DebugUartThread_Entry()`
- Change:
  - Initialize queues before creating application producers.
  - Create the task at initial priority 10 with a 2048–3072 byte stack.
  - Keep startup writes synchronous until asynchronous initialization completes.
- Acceptance:
  - Early boot traces remain visible and later traces use the queue.
- Verification:
  - Incremental build.
  - Inspect ThreadX stack high-water after startup and UART stress.

## [ ] PLANNED M1.6 — Migrate all runtime log output

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
  - After initialization, queue only.
  - Do not hold the ST67 formatting mutex while physical TX occurs.
- Acceptance:
  - Runtime producers return without waiting for USART transmission.
- Verification:
  - `rg -n "HAL_UART_Transmit\(" AppliNonSecure`
  - Review every remaining match as startup/emergency-only.
  - Incremental build and UART stress.

### Milestone 1 gate

- [ ] UART line ordering is preserved.
- [ ] Producers do not block on physical TX.
- [ ] No drops occur during the agreed burst test.
- [ ] Overflow is observable through counters rather than a system stall.

---

# Milestone 2 — Stable source and session identity

Goal: make asynchronous replies independent of the global active CLI session.

## [ ] PLANNED M2.1 — Introduce transport routes and request IDs

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

## [ ] PLANNED M2.2 — Add generation to every CLI session

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
- Functions/types:
  - `CliSession_t`
  - `cli_session_reset()`
- Change:
  - Add `AppRoute_t route`.
  - Increment generation on reset/reconnect for USB, BLE, and Cloud.
  - Never retain `CliSession_t *` in a cross-task request.
- Acceptance:
  - A stale route is detectable after reconnect.
- Verification:
  - Incremental build and reconnect test.

## [ ] PLANNED M2.3 — Move pending Wi-Fi credentials into the session

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
- Acceptance:
  - Simultaneous USB/BLE connect flows cannot overwrite one another.
- Verification:
  - Incremental build.
  - Interleave the SSID/password flow from two transports.

### Milestone 2 gate

- [ ] Every asynchronous source has transport plus generation.
- [ ] No global pending SSID remains.
- [ ] No cross-task message stores a `CliSession_t *`.

---

# Milestone 3 — Dedicated Wi-Fi worker and non-blocking CLI

Goal: isolate long Wi-Fi waits in a task whose only responsibility is Wi-Fi
control.

## [ ] PLANNED M3.1 — Define owned Wi-Fi request and result messages

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

## [ ] PLANNED M3.2 — Replace the single Wi-Fi control context with slots

- Files:
  - `AppliNonSecure/Core/Src/wifi_ble_app.c`
- Functions:
  - `wifi_control_initialize()`
  - private request/result slot helpers
- Change:
  - Create four request slots and four result slots.
  - Create free/ready pointer queues for requests and results.
  - Producers use `TX_NO_WAIT`; only the dedicated worker waits for requests.
  - Clear the password field immediately after the W6X call consumes it.
- Acceptance:
  - Queue saturation returns `TX_QUEUE_FULL` immediately.
- Verification:
  - Incremental build and forced queue-full unit/debug test.

## [ ] PLANNED M3.3 — Expose non-blocking submit/result APIs

- Files:
  - `AppliNonSecure/Core/Inc/wifi_ble_app.h`
  - `AppliNonSecure/Core/Src/wifi_ble_app.c`
- Functions:
  - new `WIFI_BLE_App_WifiSubmit()`
  - new `WIFI_BLE_App_WifiReceiveResult()`
- Change:
  - Submit assigns a monotonically increasing request ID, copies the request,
    enqueues, and returns.
  - Receive copies a completed result and releases its slot.
- Acceptance:
  - Neither public API waits for a Wi-Fi event.
- Verification:
  - Incremental build.

## [ ] PLANNED M3.4 — Implement the Wi-Fi control task loop

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
- Acceptance:
  - `WIFI_BLE_App_Run()` never performs a high-level Wi-Fi operation.
- Verification:
  - Incremental build.

## [ ] PLANNED M3.5 — Create the Wi-Fi worker thread

- Files:
  - `AppliNonSecure/Core/Src/app_threadx.c`
- Functions:
  - `App_ThreadX_Init()`
  - new `WiFiControlThread_Entry()`
- Change:
  - Initial priority 11 and stack size 6144 bytes.
  - Wait for explicit radio-ready signaling before accessing W6X.
- Acceptance:
  - Wi-Fi connect runs on a different ThreadX thread from BLE processing.
- Verification:
  - Incremental build and stack high-water inspection.

## [ ] PLANNED M3.6 — Make Wi-Fi scan submission-only in CLI

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
- Functions:
  - `cli_wifi_scan()`
- Change:
  - Submit the request and print its request ID.
  - Remove the 30-second wait and local scan-result ownership.
- Acceptance:
  - The CLI loop returns immediately after accepting the command.
- Verification:
  - Incremental build and continuous ping during scan.

## [ ] PLANNED M3.7 — Make connect submission-only in CLI

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
- Functions:
  - `cli_wifi_connect_password()`
- Change:
  - Build a fully owned request from the current session.
  - Submit, report request ID, clear the session password, and return.
  - Remove the 35-second wait.
- Acceptance:
  - Both USB and BLE remain interactive during association/DHCP failure.
- Verification:
  - Incremental build and the Milestone 0 blocking probe.

## [ ] PLANNED M3.8 — Make disconnect submission-only in CLI

- Files:
  - `AppliNonSecure/Core/Src/debug_cli.c`
- Functions:
  - `cli_command_wifi()`
- Change:
  - Submit disconnect/forget as a routed request.
  - Remove the 10-second wait.
- Acceptance:
  - CLI input is processed during disconnect.
- Verification:
  - Incremental build and concurrent ping/disconnect test.

## [ ] PLANNED M3.9 — Route completed Wi-Fi results

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
- Acceptance:
  - USB and BLE requests never receive one another's result.
- Verification:
  - Incremental build and simultaneous two-transport test.

## [ ] PLANNED M3.10 — Delete the blocking application API

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
  - Incremental build.
  - `rg -n "WIFI_BLE_App_Wifi(Scan|Connect|Disconnect)" AppliNonSecure`

### Milestone 3 gate

- [ ] CLI has no Wi-Fi wait.
- [ ] BLE loop remains active throughout a failed connection.
- [ ] Result origin and generation tests pass.
- [ ] The blocking probe reaches the latency target or records a remaining
  vendor-lock delay for Milestone 4.

---

# Milestone 4 — Bound W61 command-lock waits

Goal: prevent a BLE notification from waiting forever behind Wi-Fi or Cloud AT
traffic.

## [ ] PLANNED M4.1 — Bound the generic modem command TX lock

- Files:
  - `ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c`
- Functions:
  - `modem_cmd_send_ext()`
- Change:
  - Replace `portMAX_DELAY` when taking `sem_tx_lock` with the supplied timeout.
  - Return `-ETIMEDOUT` when the mutex is unavailable.
  - Track whether the lock was acquired and only then release it.
- Acceptance:
  - A call's timeout includes time waiting for the shared AT channel.
- Verification:
  - Incremental build and concurrent BLE/Wi-Fi HIL test.

## [ ] PLANNED M4.2 — Bound manual common-command locks

- Files:
  - `ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c`
- Functions:
  - `W61_AT_Common_Query_Parse()`
  - `W61_AT_Common_RequestSendData()`
- Change:
  - Use the operation timeout for mutex acquisition.
  - Do not modify shared receive pointers until the mutex is held.
  - Return `W61_STATUS_TIMEOUT` on acquisition failure.
- Acceptance:
  - Neither function waits indefinitely.
- Verification:
  - Incremental build.

## [ ] PLANNED M4.3 — Audit BLE manual locks

- Files:
  - `ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_ble.c`
- Functions:
  - every function that manually takes `sem_tx_lock`
- Change:
  - Use the caller-supplied or explicit bounded operation timeout.
  - Notification timeout includes lock acquisition.
- Acceptance:
  - No runtime BLE path uses an infinite TX-lock wait.
- Verification:
  - Incremental build.
  - `rg -n "sem_tx_lock.*portMAX_DELAY"` on the file returns no match.

## [ ] PLANNED M4.4 — Audit Wi-Fi manual locks

- Files:
  - `ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_wifi.c`
- Functions:
  - every function that manually takes `sem_tx_lock`
- Change:
  - Use a bounded timeout and verify acquisition before touching shared state.
- Acceptance:
  - No runtime Wi-Fi path uses an infinite TX-lock wait.
- Verification:
  - Incremental build and targeted `rg` check.

## [ ] PLANNED M4.5 — Audit Network and System manual locks

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
  - Incremental build.
  - `rg -n "sem_tx_lock.*portMAX_DELAY" ThirdParty/ST67W6X_Network_Driver/Driver/W61_at`

## [ ] PLANNED M4.6 — Retry BLE TX without losing the packet

- Files:
  - `AppliNonSecure/Core/Src/wifi_ble_app.c`
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
  - Incremental build and concurrent Cloud/Wi-Fi/BLE stress.

### Milestone 4 gate

- [ ] No runtime W61 TX-lock acquisition is infinite.
- [ ] BLE remains responsive during AT contention.
- [ ] No packet is silently removed on a transient busy result.

---

# Milestone 5 — Isolate Cloud work

Goal: remove DNS/TLS/socket processing and output backpressure from Radio/BLE
and CLI tasks.

## [ ] PLANNED M5.1 — Make Cloud output admission non-blocking

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
  - Incremental build, memory-map review, and forced-full test.

## [ ] PLANNED M5.2 — Add a dedicated Cloud run loop

- Files:
  - `AppliNonSecure/Core/Inc/cloud_relay.h`
  - `AppliNonSecure/Core/Src/cloud_relay.c`
- Functions:
  - new `CloudRelay_Run()`
  - existing `CloudRelay_Process()`
- Change:
  - Own all DNS/TLS/socket/protocol progress in the Cloud task.
  - Use event wakeups or a short bounded periodic wait.
- Acceptance:
  - `CloudRelay_Process()` has one caller.
- Verification:
  - Incremental build.

## [ ] PLANNED M5.3 — Create the Cloud task

- Files:
  - `AppliNonSecure/Core/Src/app_threadx.c`
- Functions:
  - `App_ThreadX_Init()`
  - new `CloudRelayThread_Entry()`
- Change:
  - Create only when Cloud Relay is enabled.
  - Initial priority 12 and stack size 8192 bytes.
  - Wait for radio-ready and handle loss of Wi-Fi IP without busy looping.
- Acceptance:
  - Cloud processing executes on a distinct task.
- Verification:
  - Incremental build and stack high-water inspection.

## [ ] PLANNED M5.4 — Remove Cloud processing from the BLE loop

- Files:
  - `AppliNonSecure/Core/Src/wifi_ble_app.c`
- Functions:
  - `WIFI_BLE_App_Run()`
- Change:
  - Remove `CloudRelay_Process(wifi_has_ip)`.
  - Leave BLE event processing and bounded BLE TX/RX work only.
- Acceptance:
  - DNS/TLS failure does not increase the Radio/BLE loop gap.
- Verification:
  - Incremental build and the latency probe during Cloud reconnect failure.

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

## [ ] PLANNED M8.5 — Replace ToF fatal loop with reset policy

- Files:
  - `AppliNonSecure/Core/Src/tof_app.c`
- Functions:
  - `tof_fatal()`
- Change:
  - Log and broadcast once.
  - Preserve stage and error code.
  - Request reset rather than logging every two seconds forever.
- Acceptance:
  - Fatal ToF failure reaches a deterministic reset.
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

# Final result record

- Final status: `NOT STARTED`
- Final revision: pending
- Secure build: pending
- NonSecure build: pending
- BLE idle p95: pending
- BLE Wi-Fi-failure p95/max: pending
- Maximum Radio/BLE loop gap: pending
- Debug UART dropped messages: pending
- Unexpected resets: pending
- Open risks: pending
