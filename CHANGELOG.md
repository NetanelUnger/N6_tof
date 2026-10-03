# Project change history

This file contains the dated engineering record extracted from `README.md`.
Do not load it during normal project work; consult it only when a task
explicitly requires historical context.

### 2026-10-03

- Diagnosed v7 trial rollback to v5 as a Secure gateway ABI mismatch: the new
  application called `SECURE_SystemCoreClockUpdate` at 0x3400F610, outside the
  installed Secure gateway range. Reproduced the startup INVEP fault while
  retaining installed Secure, then verified startup with the matching Secure.
  The XMODEM release gate now checks FSBL/Secure raw hashes recorded by Stage 09,
  rather than accepting an old complete state after Secure changed. Boot-chain
  SWD recovery preserves both application slots and A/B metadata.
  Recovery completed with 100-frame HIL PASS, authenticated v7 XMODEM install,
  trial confirmation, and a second Flash boot selecting confirmed slot B/v7
  (metadata sequence 15). CDC reported version 7; ToF and NPU were ready with
  zero I3C/inference errors. Five hardware-free compatibility checks passed.

- Fixed Stage 12 accepting disconnected CDC identities from CIM/the persistent
  USB enumeration registry. Only currently present serial ports are accepted;
  initial discovery waits up to 30 seconds, auto selection is repeated before
  XMODEM and after reset, and explicit port selection stays fixed. Six
  hardware-free checks passed, including registry fallback under denied CIM.
  The reported v6 attempt stopped at SerialPort.Open before any firmware byte
  was sent and restored the tracked version to 5. The user had pressed Reset
  with external-Flash boot jumpers after RAM HIL, discarding that live image.
- Diagnosed Stage 10 startup failure from the retained ST-LINK log: target
  initialization succeeded, then binding host TCP port 61234 failed. RAM
  loading had not begun; the exact port owner/reservation was no longer
  observable. RAM debug now preflights a three-port range, selects a fallback
  when the default is unavailable, honors explicit port selection, rejects
  unrelated listeners as readiness evidence, and includes startup logs in
  errors. Five hardware-free regression checks passed, and the unchanged
  Secure/Non-Secure builds loaded through ThreadX on hardware. External NOR
  and the firmware version were not changed.
- A subsequent Stage 11 run passed 100 CRC-valid frames, 100 frame-matched NPU
  results, 100 bit-exact device/Python tensors, 100% class/decision agreement,
  and maximum raw-score delta 1. Host BLE discovery found N6-MAINT-B8FB and
  Wi-Fi scanning passed. Observed output rate was 4.10 fps; this is not 10 fps
  throughput acceptance. The preceding RAM boot reported zeroed component
  versions and failed radio preflight; another RAM boot reported SDK 2.0.106.
  That intermittent information/initialization failure remains uncharacterized.
  The FSBL authenticated the existing confirmed Flash slot A/v5 during handoff.

### 2026-09-26

- Stage 11 now treats low raw/model-input diversity and an empty/static scene
  as advisory `HIL NOTE` evidence instead of requiring a person to move a hand
  for unattended runs. CRC, frame progression, sensor rate, exact device/host
  preprocessing, NPU coverage/counter progression and TFLite score comparison
  remain gates. The JSON retains the measured diversity and notes separately.
- Fixed Stage 11 Wi-Fi radio preflight after the CLI became asynchronous:
  it now waits for scan acceptance and a matching request-ID result within a
  bounded timeout, rejects stale/failed results, and preserves the USB
  transcript on failure. The previous `Wi-Fi scan complete (status 0)` parser
  caused a false HIL RADIO FAIL. Synthetic tests and live COM8 radio/BLE/Wi-Fi
  preflight passed; the full 100-frame Stage 11 gate was not rerun.
- Added a diagnostic GC9A01 boot screen: blue `SYSTEM IS LOADING`, then
  green `SYSTEM ON` after the ToF pipeline-ready event. `MAP ON DISPLAY`
  switches to a black map canvas with `WAITING` until a frame arrives, and
  `MAP OFF DISPLAY` restores the ready screen. `tof status` now reports the
  last screen submitted through SPI DMA, not proof that the panel lit. The
  change is for RAM-only hardware diagnosis; the external-NOR image is unchanged.
- Added focused VL53L9CX DSS-command diagnostics: separate TX-start,
  TX-completion, command-status-read and command-status-timeout counters in
  `tof status`; blocking I3C reads now capture the exact failing HAL step and
  bound the formerly infinite post-TX state wait. Incremental build and
  hardware-free checks passed. The first RAM-only baseline ran 3,785 acquired
  frames plus one Wi-Fi scan without a ToF fault; the exact prior `DSS map
  command (-1)` cause is still unproven, and local sensor recovery is not yet
  implemented. No external-NOR write was made.
- Switched the demonstration Cloud Relay transport from failing T01 HTTPS to
  plaintext HTTP/1.1 on TCP port 80, preserving T01 offload and the same Azure
  host/API. The HTTP build skips CA/TLS socket options and the TLS-only SNTP
  prerequisite, labels the endpoint and security state accurately, and warns
  on COM6. TLS verification now defaults to enabled whenever TLS is restored.
  Incremental Non-Secure build and RAM-only boot passed; the user subsequently
  reported a successful pairing. The first deliberately invalid-code probe
  timed out before an HTTP response, and post-pair status was not captured.
  The same RAM run later stopped ToF after 1,507 acquired frames with a
  `DSS map command (-1)` fault; M8.4a/M8.5 recovery remains open. This is an
  insecure experiment, not a customer-ready T01 TLS resolution or a passing
  Cloud/ToF end-to-end HIL result.

### 2026-09-25

- Added an explicitly insecure Cloud TLS demo switch. The current RAM test
  build skips server-certificate verification but keeps TLS 1.2 and SNI;
  `cloud status` and COM6 warn about this. Incremental build and hardware-free
  checks passed, and SRAM-only boot reached Radio Manager/Cloud after one
  transient `W6X_Init` startup failure. A dummy-code Cloud handshake test is
  pending Wi-Fi reconnection. Never treat this mode as a secure release.
- Fixed a vendor socket-lifetime leak exposed by failed Cloud TLS connects:
  closing an allocated-but-not-connected socket now releases its slot and
  copied TLS credentials. Cloud status distinguishes allocation, option,
  connect and send failures. Build, Python utility tests and SRAM-only load
  passed; ten subsequent attempts reached `CIPSTART` without slot exhaustion.
  The NCP still rejects it, so paired Cloud is not verified. A read-only host
  TLS test measured a 6603-byte Azure handshake record, above ST's documented
  6144-byte T01 limit; Azure did not honor a 4096-byte MFL request. This is a
  high-confidence cause candidate, not a captured NCP error code.
- Fixed the Cloud TLS tag-list count mismatch found by dual-COM HIL:
  `TLS_SEC_TAG_LIST` consumed four byte-sized tags from one `int32_t` and
  rejected the undefined zero tag before HTTP. The caller now passes one tag
  while retaining safe 32-bit backing. Incremental build, RAM load, Python
  HIL utility checks and diff check passed. Post-fix RAM HIL passed the old
  credential failure but failed later at NCP `AT+CIPSTART`, before HTTP; Cloud
  stayed unpaired and Radio Manager max gap reached 7150 ms. The Cloud gate
  remains open; no external NOR was written.
- Added `training/DUAL_COM_DEBUG.bat` and a dual-port Python capture tool with
  USB-ID discovery, automatic COM reconnection, separate per-run live logs,
  diagnostic CLI/Debug-UART commands, and an optional existing BLE GATT probe.
  Hardware smoke capture confirmed COM6/COM8, a USB PONG and BLE status, and
  a Debug-UART one-key reply; no firmware was changed for this utility.
- Investigated a persistent BLE notification stall also accompanied by Wi-Fi
  state-query timeouts. A queued TX slot could suppress BLE link probes
  indefinitely; sustained contention now permits bounded link probing and
  emits a one-time SPI/pin snapshot on COM6. Build and RAM load passed; root
  cause and physical recovery remain unverified. No automatic NCP reset was
  added.
- Under an explicit user-approved gate exception, completed M5.1 only:
  Cloud output and completion admission now use `TX_NO_WAIT`, eight fixed
  384-byte slots, and all-or-none record publication. A startup forced-full
  self-test passed on the RAM image; the slots moved to application SRAM to
  preserve 4,472 bytes of radio-pool headroom. Non-Secure build and RAM boot
  passed. Paired Cloud HIL and all earlier milestone gates remain open.
- Reproduced the post-GOTIP Secure HardFault with browser BLE. Valid SFAR
  `0x00000EBC` and SWD-recovered PSP_NS frame gave PC `0x2413FE8E`
  (`W61_AT_Common_SetExecute`, `w61_at_common.c:492`) and LR `0x24140CE1`
  (`W61_Net_SNTP_SetConfiguration`, `w61_at_net.c:1126`). Both vendor Net
  pointers were NULL: Cloud Relay reached SNTP without `W6X_Net_Init()`.
  Initialize Net before Cloud, disable only Cloud if that fails, skip SNTP
  while Cloud is unpaired, and inspect both NS stack candidates in fault reports. Both incremental builds
  pass and the new images run from SRAM with USB/advertising alive. The
  20-cycle Wi-Fi/BLE and negative-path HIL gate remains open.
- Extended Secure fault diagnostics to decode an EXC_RETURN-selected
  Non-Secure exception frame in SRAM2..6, including SRAM4 ThreadX stacks,
  after range, stacking-status and CMSE checks. The handler now prints the
  stacked PC/LR/xPSR and flags an invalid SFAR. Secure and Non-Secure builds,
  Python HIL utility checks, and diff check pass. The reported post-GOTIP
  fault is not yet reproduced or root-caused: COM6 is occupied and ST-LINK
  returns a USB communication error, so no RAM load or 20-cycle HIL is claimed.
  After reconnecting ST-LINK, the diagnostic Secure and current Non-Secure
  images loaded into SRAM only. Radio/BLE initialized and five minutes of idle
  USB pings passed 1040/1040 (p95 32.5 ms, max 52.1 ms); ToF DSS-unmap failed
  before any Wi-Fi request. The GOTIP fault was not reproduced in this run, so
  root cause and the 20-cycle acceptance remain open.

### 2026-09-24

- Fixed silent AT-byte truncation when a queued SPI packet exceeded the modem
  parser's remaining buffer space. The modem retains the full packet and
  consumption offset until all bytes are copied; the assembly buffer now holds
  two SPI MTUs in fixed application SRAM rather than the near-exhausted radio
  pool. A full unparseable record is counted and reported rather than spinning.
  Non-Secure build and HIL utility self-test passed. The final SRAM image
  passed USB radio/ToF preflight and three NCP Wi-Fi scans (11/13/11 networks)
  with stable 3,784-byte radio-pool headroom. BLE host HIL failed before any
  GATT write: WinRT returned E_FAIL while creating the device, with or without
  pairing. Its report records zero pings sent; BLE repeatability remains open.
  External NOR was not changed.
- Removed the SPI worker's idle 20 ms `SPI_RDY` level poll. It now waits for
  EXTI-ready or host-TX events; transaction-time handshake reads remain. A
  missed RX-only ready edge can stall until another event, so physical HIL
  validation of the edge-only path remains open. No Flash was changed.
- Added single-key `n` ST-LINK UART NCP trace with bounded, credential-safe
  AT/event summaries and safe `debug ping` checkpoints from the NCP direct
  event parser through BLE RX, CLI parser and reply queue. Built and loaded
  the initial trace image to SRAM only;
  physical UART toggle and BLE trace worked. An idle trace run failed 23/28,
  with 23 matching ping inputs observed at every CLI checkpoint, so the
  missing inputs remain unlocalized. The final trace image was rebuilt and
  loaded to SRAM; a five-second probe failed 12/15, with 12 matching tokens
  at the NCP direct-event parser and every CLI checkpoint, and zero UART
  diagnostic drops. The missing three were not seen as complete direct
  events, so this run does not implicate the CLI command parser. One earlier
  RAM boot logged an intermittent ToF DSS-unmap error. No Flash was changed.
- Reconnected ST-LINK and loaded the latest Secure/Non-Secure image to SRAM;
  external NOR remained unchanged. COM6 proved the new one-key UART snapshots
  (`a`), five-second Radio watch (`R`) and stop (`0`) while ordinary logs
  continued. Fixed a mixed HAL-milliseconds/ThreadX-ticks calculation exposed
  by that test, and corrected the Milestone-4 host gate to parse both old and
  new gap labels in milliseconds. Rebuilt/reloaded and retested. The elevated
  45-second BLE/Wi-Fi probe failed 117/137 (20 missing), while concurrent USB
  passed 24/24; a separate 20-second BLE idle probe failed 71/77 (6 missing).
  BLE TX drops and RX drops remained zero, but the HIL gate stays open. The ToF
  status remained READY at roughly 4.0 fps with substantial frame drops; no
  claim of a healthy 10 fps pipeline is made.

- Added one-key ST-LINK UART status snapshots for Radio, ToF, CLI and USB,
  plus a selectable five-second watch of one mechanism. UART RX interrupt
  only queues a byte; the diagnostic thread formats output. Exposed safe
  thread progress fields through status APIs and made USB status observation
  non-blocking when its state mutex is occupied. Incremental Non-Secure build
  and memory preflight pass; hardware runtime remains unverified while
  ST-LINK reports `DEV_USB_COMM_ERR`. No external NOR was changed.

- Added BLE desired/observed reconciliation in the Radio Manager: explicit
  UNKNOWN evidence after failed commands, bounded ADV retries, alternating
  idle-time BLE mode/link queries, two-observation link correction and bounded
  BLE-only reinitialization on confirmed mode loss. `ble status` exposes probe,
  repair and retry diagnostics. The Wi-Fi worker also checks station state
  every 30 seconds when idle and discards observations superseded by an event.
  Whole-NCP reset and RF-verification claims remain out of scope; build and
  physical HIL evidence are recorded separately. Final Non-Secure incremental
  build, memory preflight, diff check and HIL utility self-test passed. A
  RAM-only hardware load was attempted but ST-LINK GDB startup failed with
  `DEV_USB_COMM_ERR` before loading the image; no external NOR was written,
  so the new runtime behavior is not yet hardware-verified.

- Grouped ToF, CLI, USB lifecycle and CDC transport mutable state into
  debugger-visible root contexts, with individual thread heartbeats. Preserved
  SRAM3 payload and SRAM4 Cloud-session placements; Non-Secure build and
  memory preflight pass. `app_usbx_device.c` generated globals outside USER
  CODE were consolidated and need review after any CubeMX regeneration.

- Consolidated Radio Manager state, pending work, SRAM4 queue ownership and
  diagnostics under one context. Added desired/observed BLE advertising and
  manager fault counters to `ble status`; reconnect advertising now respects
  an explicit `ble adv off`. No general NCP self-healing policy is added yet.

- Added an automatic five-consecutive-RAM-boot M3.7/M4 HIL gate with BLE,
  concurrent USB, radio, Wi-Fi and ToF observations. The BLE probe now keeps
  measuring after a missing reply while preserving FAIL; the aggregate retries
  transient Dropbox file locks and stops when five passes become unreachable.
  Shortened the BLE startup banner and reserved a sentinel byte in the W61 RX
  allocation. NonSecure build and host self-test passed. Physical gate failed:
  BLE 148/162 then 222/222, USB 24/24 on both, ToF DSS unmap error on both,
  followed by an ST-LINK GDB startup failure. M3.7/M4 remain open.

### 2026-09-23

- Implemented M4.4–M4.6: all remaining manual Wi-Fi/Network/System AT TX-lock
  waits are finite, and BLE TX retains active packets/frames on transient
  BUSY/TIMEOUT with visible streak/duration/recovery counters. Build, global
  lock search, diff check and host self-tests passed. A RAM BLE/Wi-Fi probe
  failed early at 14/15 replies (one missing) despite zero BLE TX drops; a
  repeat passed the full 45 seconds at 222/222. USB passed 24/24 in each run.
  One radio-init boot failed and ToF later faulted separately. Milestone 4,
  M3.7 five-boot and Cloud HIL remain open; no NOR write, commit or push.
  A final rebuild recomputed each AT caller's remaining budget after command
  preparation; its fresh RAM probe passed 222/222 BLE replies (p95 149.209 ms)
  and 24/24 USB pings, with three transient timeout attempts and zero TX
  drops. The earlier missing reply remains unresolved.

- Completed M4.3's three manual BLE AT TX-lock bounds and made the
  notification's 100 ms deadline include lock acquisition and subsequent
  response waits in the shared send-data path. Incremental build and one full
  45-second BLE/Wi-Fi RAM probe passed: 223/223 PONGs, zero missing, p95
  152.095 ms, zero reconnects; parallel USB passed 24/24. BLE TX recorded
  zero drops and one retry/error; radio max gap was 50 ticks. A separate ToF
  fault (-5/-1) persists on that boot. M4.1 HIL, M3.7 five-boot, Cloud HIL,
  and the Milestone 3 gate remain open. M4.4 was not started.

- Completed M4.2's two manual common-command TX-lock bounds. Lock acquisition
  uses the operation timeout and returns `W61_STATUS_TIMEOUT` on failure;
  Query/Parse subtracts acquisition time before its response wait. Build and
  one full 45-second concurrent BLE/Wi-Fi RAM probe passed (221/221 PONGs,
  zero missing, p95 169.995 ms; 24/24 USB pings). BLE CLI RX/TX drops were
  zero. The same boot had a separate ToF initialization error (-5), and this
  one probe does not erase M4.1's failed probes or close M3.7's five-boot gate.
  M4.3 remains unstarted.

- Implemented M4.1 in `modem_cmd_send_ext()`: finite TX-lock acquisition now
  uses the supplied operation timeout, lock failure returns `-ETIMEDOUT`, only
  an acquired lock is released, and elapsed lock/write time reduces the modem
  reply budget. Build and RAM load passed. Two concurrent BLE/Wi-Fi probes
  failed (18/19 and 15/16 replies, p95 263.543/262.771 ms), while both
  24-ping USB series passed. M4.1 HIL acceptance, M3.7, Cloud HIL and the
  Milestone 3 gate remain open; M4.2 was not started.

- Completed the focused M3.9 Cloud/per-session result follow-up and M3.10 API
  removal. A Cloud Wi-Fi request retains its originating Relay command until
  its matching result is queued. The Cloud result is one nonblocking, atomic
  output record, avoiding the Relay writer's 15-second queue wait. A Relay
  command hold prevents a later poll from replacing the ACKed command ID
  before its asynchronous result is accepted; password/
  XMODEM deferral is scoped to the
  owning CLI session, with a bounded four-result mailbox and visible overflow
  counter. Removed the three blocking application Wi-Fi APIs and their legacy
  pending/done state. Incremental build, Python checks, RAM load, six USB slot-
  reuse requests, and bidirectional USB/BLE isolation during password prompts
  passed. Cloud HIL was unavailable because the board was unpaired/off Wi-Fi;
  M3.7 and the Milestone 3 gate remain open.

- Routed M3.9 Wi-Fi result snapshots in bounded CLI batches to only the live
  matching transport/generation. USB/BLE HIL separated concurrent IDs 7/8,
  recycled result slots across six USB requests, counted stale BLE/USB results
  after reconnect/close, and kept a completed scan out of XMODEM until CAN-CAN
  cancellation. Deliberate BLE disconnect during scan output caused one write
  error and expected stale stream drops; M3.7 and the Milestone 3 gate remain
  open. M3.10 has not started.

- With explicit approval to proceed past the open M3.7 BLE repeatability gate,
  made `wifi disconnect [forget]` submission-only. It sends the active CLI
  route and forget bit in an owned request, returns an ID immediately, and no
  longer waits ten seconds or prints a final result. RAM HIL accepted USB IDs
  1/2 and BLE IDs 3/4; immediate BLE pings and 24/24 concurrent USB pings
  passed with zero BLE stream drops. M3.7 and the Milestone 3 gate remain
  unapproved; final result delivery awaits M3.9.

### 2026-09-22

- Hardened the M3.7 BLE/AT failure paths found by repeated physical HIL. The
  direct parser now leaves malformed input with bounded progress, partial BLE
  numeric fields request more data, and a raw SPI write that cannot advance
  releases the shared AT transmit lock instead of spinning forever. Two fresh
  45-second invalid-Wi-Fi probes passed 222/222 with zero missing replies and
  p95 148.352/152.370 ms; the latter ran alongside 24/24 USB PONGs at p95
  30.6 ms, with radio/BLE maximum loop gap 390 ticks and no stream drops,
  retries, or errors. An intervening clean run connected but failed to publish
  the initial BLE prompt and logged repeated SPI transaction-ready timeouts
  before any Wi-Fi request. M3.7 therefore remains implemented but not accepted
  pending bounded SPI handshake recovery and a repeatable clean-boot gate.

### 2026-09-21

- Made `wifi connect` submission-only. The hidden-password path now copies the
  session route and credentials into a zeroed owned request, submits it, scrubs
  the complete stack request immediately, and returns the request ID without
  waiting for association or DHCP; the caller still scrubs the complete
  session credential buffers on every outcome. USB RAM HIL returned the prompt
  in 12.6 ms, answered 8/8 concurrent pings within 14.2–30.6 ms, held the radio
  loop maximum gap at 21 ticks, and left 3,188 SRAM4 radio-pool bytes available.
  Manual BLE GATT discovery subsequently passed, and one exact 45-second probe
  passed with 225/225 replies, zero missing and p95 162.088 ms while 18/18 USB
  pings remained responsive. A fresh-boot repeat was not reliable: it delivered
  21/75 replies before a malformed/truncated `+BLE:GATTWRITE` event exposed a
  vendor direct-parser livelock in priority-2 `Modem_Process`, starving Radio
  Manager and USB without a Cortex fault. M3.7 therefore remains implemented
  but not accepted pending a targeted parser fix and repeat BLE HIL.
- Made `wifi scan` submission-only. The CLI now submits one routed, fully owned
  SCAN request, prints its monotonic request ID, and returns in milliseconds;
  six live pings during the worker scan all returned within 8–30 ms. Result
  display remains M3.9. The change adds no SRAM4 storage. The first scan still
  triggers the vendor driver's existing one-time 928-byte lazy result buffer;
  a repeated scan held the pool stable at 2,260 bytes.
- Created the dedicated priority-11 Wi-Fi control worker with a 6 KiB stack in
  the SRAM4 radio pool. Its entry calls only the radio-ready-gated control loop.
  RAM HIL and a live connect breakpoint proved that W6X connect runs on this
  worker rather than the priority-9 Radio Manager; the exercised stack retained
  3,936 bytes, while the fully initialized radio pool retained a narrow 3,188
  bytes that remains a later soak-test watch item.
- Added the staged Wi-Fi control loop. It waits for radio readiness, exclusively
  owns runtime scan/connect/disconnect calls, turns every dequeued owned request
  into an independent routed result (including scan timeout/failure), and
  scrubs connect credentials around the vendor call. The existing radio/BLE
  loop no longer executes high-level Wi-Fi work. Thread creation remains M3.5,
  so the loop is compiled but not started yet and the CLI source is unchanged.
- Exposed non-blocking Wi-Fi submit/result APIs over the fixed slot queues.
  Submit validates routed owned input, assigns a non-zero monotonic request ID,
  copies only operation-relevant fields, and rolls publish failure back;
  receive copies and immediately scrubs/releases a result. The APIs have no
  wait, sleep, polling, or retry path and are not yet used by the CLI.
- Added four fixed Wi-Fi request slots, four result slots, and four one-pointer
  ThreadX free/ready queues in the one-time SRAM4 control allocation. A startup
  self-test verifies immediate fifth-acquire saturation, unique slots, complete
  release scrubbing, ready-queue traversal, restored pool counts, and clean
  initialization rollback. The legacy blocking path remains active until its
  later worker/API migration.
- Defined public, fully owned Wi-Fi request/result message values with routed
  request identity, fixed credential storage, final status, and independent
  status/scan snapshots. The types contain no caller-owned pointers and are not
  yet connected to queues, a worker, or a non-blocking submit API.
- Added transport-independent USB/BLE/Cloud/System routes and numeric request
  IDs. Every CLI session now owns a fixed transport plus non-zero generation;
  reset advances with wrap protection, BLE follows its existing radio epoch,
  and Cloud follows successful pair, explicit reconnect/test, and unpair.
- Moved pending Wi-Fi SSID, hidden password storage, and prompt state into each
  CLI session. Submission, cancellation, input failure, disconnect, and reset
  scrub complete credential buffers without changing another session. Added
  `debug route` with focused generation, stale-route, isolation, and cleanup
  diagnostics. The Wi-Fi worker/queue remains intentionally deferred to M3.

### 2026-09-19

- Passed the final Cloud-integrated Stage 11 SRAM HIL: SDK 2.0.106, 11 Wi-Fi
  networks, the expected BLE advertisement at -68 dBm, 100 CRC-valid distinct
  ToF frames, 100/100 frame-matched Neural-ART results, bit-exact preprocessing,
  30 distinct model tensors, 100% class and decision agreement, maximum raw
  delta 6, and zero NPU errors. Stage 11 now disconnects stale BLE clients and
  explicitly restarts advertising before its real external UUID scan.
- Fixed intermittent VL53L9 DSS map/start timeouts by polling the one-byte
  command register with the blocking I3C helper after asynchronous TX completes.
  This avoids immediately reusing the single persistent async descriptor while
  the HAL/DMA completion path may still reference the TX context. The bounded
  completion budget is now 100 ms. External Flash was not changed by the HIL.
- Added the HTTPS Cloud CLI relay for the Azure App Service: six-digit pairing
  is callable through USB or BLE, the CRC-protected capability token persists
  in the ST67 NCP filesystem, commands use leased typed text/binary records with
  explicit ACKs, signed XMODEM OTA uses the same Secure A/B installer, and ToF
  frames use an independent BLE-compatible media channel. Removed transport
  command allowlists by explicit demo policy. Moved the 134 KiB application
  ThreadX pool plus Cloud session into reserved SRAM4; the Non-Secure build is
  420,432 bytes and retains 481,520 bytes of contiguous C heap.
- Reworked `help`/`menu`/`?` into bounded sections so the 768-byte CLI print
  buffer no longer truncates the Wi-Fi/BLE commands. The complete command set
  now carries `[B]` (USB+BLE)/`[U]` (USB-only) labels and documents BLE CLI,
  ToF-image and DEBUG characteristic modes plus the remote security boundary.
  Physical SRAM HIL received the complete 1,840-byte response over USB and
  repeated it over BLE at MTU 247; the BLE stream sent 16 messages/4,044 bytes
  for the initial menu plus explicit help with zero drops, retries, stale
  generations, or errors.
- Enabled the ST67 Wi-Fi station and added bounded `wifi scan`, hidden-password
  `wifi connect "SSID"`, `wifi status`/`wifi ip`, and disconnect commands. All
  W6X operations are serialized by the Radio Manager, callbacks only snapshot
  state/results, credentials are rejected over unauthenticated BLE, and a
  successful connection returns the DHCP IPv4 address.
- Kept the VL53L9 360 KiB heap guard by sizing the startup-only application
  ThreadX pool to 134 KiB in Wi-Fi builds; the incremental Non-Secure build
  passes with 369,472 bytes of C heap.
- Passed physical SRAM Wi-Fi HIL: bounded scan, hidden-password WPA2
  association, DHCP IPv4/gateway/netmask reporting, and a second scan without
  losing the link. ToF continued at 6.4 fps, Neural-ART reached 1,294 runs with
  zero errors, BLE remained ready/advertising, and the SRAM4 radio pool retained
  21,056 bytes. External Flash and the persistent firmware version were not
  changed.

### 2026-09-18

- Added a bounded BLE ToF soak command and passed 10/10 physical cycles. Every
  cycle revalidated the GATT contract at MTU 247, received one complete
  CRC-valid 54x42 frame, confirmed a quiet second after CCCD disable, and
  disconnected before the next successful reconnect. Nine first-frame waits
  were 1.21..1.34 seconds; one was 3.864 seconds.
- Extracted the dated engineering record from `README.md` into this dedicated
  file. Normal project work now reads only the operational README; this history
  is loaded only for an explicit historical question or investigation.
- Added a dedicated Notify-only ToF image characteristic to the BLE CLI service.
  One exact transformed 54x42 float channel is snapshotted before the shared ToF
  workspace is reused, framed with dimensions/channel/frame ID/offset/CRC32, and
  reassembled atomically by the web client. Firmware holds one 9,072-byte SRAM4
  snapshot and drops newer frames while it is busy, preserving bounded memory
  and live latency; CLI and DEBUG retain independent per-cycle service slots.
- Enabled signed XMODEM-CRC over BLE CLI RX/TX. CDC and BLE now select a session-
  scoped output callback but feed the same allocation-free receiver and Secure
  ECDSA/SHA-256 A/B installer. The web client implements XMODEM-1K upload with
  ACK/NAK/CAN handling, retries and progress reporting.
- Extended the browser UI with independent ToF CCCD control, a CRC-gated raw-map
  canvas, frame/drop/error counters and `.n6fw` upload. Extended the BLE HIL tool
  with the third-characteristic contract and deterministic image reassembly/CRC
  tests. Web build/lint, HIL self-test and the incremental firmware build pass;
  end-to-end radio transfer and image-rate measurements remain hardware tests.

### 2026-09-17

- Completed a physical factory-new test on the NUCLEO-N657X0-Q: full external
  NOR mass erase, verified programming of FSBL, Secure, Slot A, and both boot
  metadata copies, external-Flash boot, and CN8 confirmation of firmware
  version 3 all passed.
- Added a versioned SHA-256 factory manifest. `Factory-Provision.ps1
  -SkipBuild` now refuses stale, missing, or modified artifacts before any
  destructive erase. CN8 auto-detection now has a registry fallback for hosts
  where WMI/CIM enumeration is denied.
- Re-ran Stage 11 on the final factory image: the ST67 manager and SDK 2.0.106,
  live `N6-MAINT-B8FB` BLE advertisement, 100 CRC-valid sensor frames, bit-exact
  preprocessing, and 100/100 frame-matched Neural-ART decisions all passed.

### 2026-09-16

- Fixed the Stage 12 pre-transfer CDC failure. USBX may remain configured when
  no Windows COM handle is open, but application RX/TX now also requires DTR.
  An unopened CN8 therefore remains idle instead of timing out three menu
  writes, exhausting data-plane recovery, and causing the later XMODEM sender
  to fail with a host write timeout.
- Extended Stage 11 to derive the radio/BLE/Wi-Fi expectations from
  `app_features.h`, compare those flags with the running image, validate the
  ST67 manager and SDK against `radio_firmware/contract.json`, scan the live
  BLE advertisement and CLI service UUID, and conditionally execute a Wi-Fi
  station/scan check. The same run passed 100 CRC-valid frame-exact Neural-ART
  comparisons. Near-equal argmax results now use a mathematically bounded
  decision-consistency gate while the raw int8 delta limit remains strict.
- Added `radio_firmware`, including the licensed ST mission-T01 SDK 2.0.106
  binaries, QConn Windows dependencies, hash verification, guided jumper flow,
  bounded retry, and fail-safe FSBL restoration. Added the destructive
  `training/13_FACTORY_PROVISION.bat` lane for build/sign, full NOR erase,
  verified complete image programming, and CN8 boot-version verification.
- Removed version-specific CubeProgrammer plugin paths from the signing and
  flash scripts; both now discover the installed CubeIDE plugin dynamically.
- Diagnosed the apparent ST67 initialization hang as a target-power collapse:
  the ST-LINK reported only 0.12 V after the combined Nucleo, ToF, display and
  radio load was powered through a busy USB hub. Moving CN10 to a capable USB
  port restored 3.28 V. The RAM image then completed `W6X_Init`, read the NCP
  identity and 3.324 V module supply, registered both UART-like GATT services,
  advertised `N6-MAINT-B8FB`, allocated the independent BLE CLI session from
  SRAM4, and kept the ToF pipeline alive. Host scanning found the advertisement
  at approximately -61 dBm. Windows still returned WinRT `0x80004005` before a
  link reached the module, so characteristic write/notification HIL remains
  pending on a working central; this is not evidence of a GATT-side rejection.
- Hardened the vendored ST67 SPI worker against a permanently asserted
  `SPI_RDY`: after each eight-packet burst it sleeps for one ThreadX tick. This
  preserves pending multi-packet work while preventing the vendor priority-3
  compatibility task from starving diagnostics, modem-init timeouts and the
  rest of the application during a wiring, boot-mode or protocol fault. Added
  one pre-`W6X_Init` pin snapshot. The incremental build passes with a
  375,908-byte binary and 371,520-byte C heap, 2,880 bytes above the enforced
  360 KiB floor.
- Implemented plan item 10 in software: the CLI broker now owns independent
  CDC and BLE parser, line editor, CR/LF, history, prompt, and output state.
  BLE writes are consumed in bounded bursts and replies are queued for
  MTU-aware notification fragmentation. Session generation changes reset only
  BLE parser state and do not tear down the CDC session. `MAP DISPLAY ON|OFF`
  is accepted as an alias for `MAP ON|OFF DISPLAY`. BLE explicitly rejects
  binary map/dataset streaming, firmware update, and reboot until the required
  authenticated control/update protocol exists. Concurrent CDC/BLE command
  exchange, reconnect, and slow-subscriber phone HIL remain to be recorded.

### 2026-09-14

- Implemented plan item 9: the Radio Manager now owns bounded CLI/DEBUG BLE
  stream queues allocated from its SRAM4 byte pool. Slots carry a connection
  generation, reconnect purges stale work, TX is fragmented to negotiated
  `MTU-3`, CLI backpressure is capped at 50 ms, DEBUG TX is best-effort, and
  notification calls use a 100 ms timeout with three attempts. `ble status`
  reports queue depth/high-water, accepted/sent/dropped bytes, retry/error
  counts, generation, ATT payload and live radio-pool availability. DEBUG RX,
  the CLI parser, debug mirroring, XMODEM and privileged commands remain
  detached.
- Extended `hil_tests/ble_inspector.py` with unique-N6 selection, explicit
  UTF-8/hex writes, independent CLI/DEBUG subscriptions and fragment capture.
  The RAM image reached Non-Secure/ThreadX and advertised `N6-MAINT-B8FB` after
  integration. Two Windows connection attempts returned an unspecified WinRT
  error before GATT access, so the new stream path is build-verified but its
  final write/notify HIL remains pending a board/adapter reset. The current
  binary is 372,380 bytes and leaves 375,072 bytes of C heap, 6,432 bytes above
  the enforced floor.
- Hardened `Debug-NonSecureRam.ps1` startup detection for Windows systems where
  `Get-NetTCPConnection` does not attribute the listener to the launcher PID;
  it now also accepts the GDB server's explicit ready message. RAM loading then
  completed through FSBL, local Secure, Non-Secure `main`, SRAM3 clear and
  ThreadX without modifying external NOR.
- Raised the ST67 Radio Manager from priority 11 to priority 9 so initialization
  and its short event loop cannot be starved by the continuously-ready
  priority-10 ToF processor. An attempted post-run SWD state probe was rejected
  as HIL evidence because the GDB-server attachment reset the MCU into DEV
  BootROM; BLE validation therefore uses external scanning without reattaching.
- Added the `hil_tests` host-automation directory. Its first non-destructive
  Python utility scans all nearby BLE devices, connects only to a result chosen
  by index or exact address, reports connection/MTU and enumerates services,
  characteristics, properties, descriptors and handles. Each command writes an
  atomic machine-readable `results/ble_last.json`; a hardware-free self-test
  covers the deterministic parsing and serialization layer.
- RAM HIL established the ST67 BLE baseline: host overrides for advertising
  parameters plus scan-response data caused `W6X_Ble_AdvStart()` to return
  `W6X_STATUS_ERROR`. Following the vendor p2pServer sequence and retaining
  only device name, TX power, UUID advertising data, GATT registration and
  security produced `N6-MAINT-B8FB`; Windows connected at MTU 247 and the
  automated two-service/four-characteristic contract passed.

### 2026-09-13

- Enabled the BLE maintenance discovery layer without enabling Wi-Fi. The
  ST67 now registers separate CLI and DEBUG UART-like 128-bit GATT services,
  advertises the CLI UUID as `N6-MAINT-xxxx`, tracks independent TX CCCDs and
  negotiated MTU, requests 15--30 ms connection timing, and restarts
  advertising from the Radio Manager after disconnect. RX endpoints are
  intentionally counted/discarded until bounded session queues and framing are
  implemented; no CLI, debug, XMODEM, or privileged operation is exposed yet.
- Split the radio service guard into
  `APP_ST67W6X_BLE_GATT_ENABLED=1` and
  `APP_ST67W6X_WIFI_SERVICES_ENABLED=0`. The Non-Secure incremental build
  passes. Linking BLE reduced contiguous SRAM2 headroom, so the transient
  two 9,072-byte ToF float frames moved to the already-cleared upper-SRAM3
  workspace. The verified map reports 180,224 bytes in SRAM3, a 65,536-byte
  SRAM4 radio pool, a 367,884-byte binary, and 379,584 bytes of C heap versus the enforced
  368,640-byte minimum.
- Reserved a dedicated GC9A01 SPI4 transmit-only path in `N6.ioc`: PE12 SCK,
  PE14 MOSI, PE13 CS, PE1 DC, and PE2 RST. The fitted display has no separate
  software-controlled backlight signal. Added SPI4 TX on
  GPDMA1 channel 5 with a conservative initial 12.5 Mbit/s clock and priority-5
  SPI/DMA interrupts. SPI5 and all ST67 pins remain unchanged, the radio
  feature remains disabled, and PD9 continues to own EXTI9 for ToF. Generate
  Code, generated-file audit, source-port update, and the full three-image build
  are complete; display HIL on the new pins remains pending.
- Restored the missing CubeMX virtual-channel and NVIC records for the existing
  UCPD1 RX/TX requests on GPDMA1 channels 3 and 4. The requests were already
  present in `N6.ioc`, but without their virtual pins CubeMX reported that
  USBPD had no UCPD1 DMA channels and omitted them from generated code.

### 2026-09-12

- Diagnosed a misleading Neural-ART failure in which black input matched host
  TFLite exactly, while every non-empty live tensor produced the same
  `NOTHING` result. The sensor stream and device preprocessing were bit-exact;
  the mismatch began at the generated network input.
- Changed the Keras boundary from uint8 to float32 in the original 0..255 pixel
  domain. Stage 06 now emits and enforces a genuine uint8 TFLite input with
  scale 1 and zero-point 0 and rejects any input CAST. This prevents STEdgeAI
  4.0 from generating the former in-place UINT8-to-FLOAT expansion from 3,200
  to 12,800 bytes, which corrupted non-zero input while allowing all-zero input
  to appear correct.
- Regenerated and integrated the Neural-ART network. The generated input is
  QLinear(1, 0, uint8), its first conversion is an NPU byte-sized quantization
  stage rather than a CPU float Cast, and the Non-Secure incremental build
  passes. Final confirmation remains the Stage 10 RAM load followed by Stage 11
  HIL with a moving hand.

### 2026-09-03

- Added a five-channel educational ToF map explorer. `MAP ON` accepts keys
  `1`..`5` as independent toggles for depth, amplitude, ambient, reflectance,
  and confidence; multiple selections rotate one identified image per sensor
  frame. `MAP CHANNELS [1..5]`, `status`, and `tof status` expose the same
  selection state. Every internal map message now includes a frame ID and
  channel ID. Depth remains the only input to the current RPS model, and the
  N6DF v3 training record is deliberately unchanged in this first integration.
- Kept the implementation within the VL53L9 transform's memory budget by
  retaining depth and reusing the existing processing workspace for one
  auxiliary output instead of keeping five simultaneous float images.

### 2026-08-29

- Added `MAP PROCESSING OBJECT 7 <threshold>`. It thresholds the
  normalized OBJECT 5 depth image before producing a repaired 0/255 silhouette;
  higher values retain only surfaces nearer the palm and can suppress the arm.
  The parameter range is 0..255 with a default of 210, and the named form
  `MAP PROCESSING OBJECT 7 threshold <value>` remains available. This teaching
  experiment selected 210 on hardware; that value is now fixed in the NPU
  tensor and host bit-exact preprocessing contract. Further interactive OBJECT
  7 changes remain display-only until promoted in both implementations.

### 2026-08-28

- Extended the training stream to N6DF v3. Every record now contains both the
  raw 54x42 millimetre map and the exact frame-matched 64x50 pre-inference
  tensor preserved by the MCU, with independent payload CRCs and a header CRC.
  Capture recomputes Python preprocessing and stops before saving if any of the
  3,200 bytes differs. The verified device tensor is stored in the sample NPZ;
  Stage 04 uses it as the training input, rechecks Python equality, and refuses
  legacy/host-only samples unless `--allow-host-preprocessing` is explicit.
- Replaced the single object view with cumulative `MAP PROCESSING OBJECT 1..6`
  teaching views and `MAP PROCESSING NPU` for the exact model input. The final
  production path now ignores all depth beyond 600 mm, produces an all-black
  image when no nearby non-trivial component exists, grows its near seed across
  locally continuous depth so tilted sheets are not sliced into bands, uses a
  four-source-pixel crop margin plus a four-pixel model-canvas border, and flattens the selected
  object to a 0/255 silhouette after resize. Every non-zero pixel becomes 255,
  then one MVE-accelerated 3x3 dilation repairs thin sensor dropout stripes so
  internal hand relief cannot become model noise. Python preprocessing and augmentation use
  the same binary contract; this configuration change invalidates prepared
  tensors and requires stages 04 through 08 plus a passing Stage 11 HIL before
  the embedded classifier can be considered matched again.
- The firmware preserves one requested teaching snapshot plus the final NPU
  snapshot because the Neural-ART activation schedule overwrites its input
  arena. Nearest-neighbor resize and the snapshot-to-NPU copy use Cortex-M55
  MVE vector operations with a scalar build fallback; the binary dilation does
  too, and inference continues on
  Neural-ART. The SPI screen path remains a 54x42 depth visualization.

### 2026-08-25

- Changed the live ToF terminal's four NPU outputs from raw signed INT8 scores
  to decoded percentages with one decimal place. The displayed class list and
  winning-class confidence now share the model's `scale=1/256`,
  `zero_point=-128` conversion and nearest-tenth rounding.
- Made `training/07_GENERATE_N6.bat` ask whether to regenerate with `--force`
  when its Neural-ART output is already current, while keeping direct pipeline
  script calls non-interactive.
- Added a guided `01_CAPTURE.bat` menu for new sessions, numbered resume with
  per-class counts, all advanced capture settings, and read-only session
  listing; explicit command-line arguments still bypass the menu.
- Added non-destructive `02_REVIEW_DATASET.bat`: it prioritizes technically
  suspicious/model-disagreement frames for human Accept/Reject/Relabel,
  persists reversible SHA-keyed decisions outside raw metadata, supports a
  whole-burst action when useful, and feeds the same reviewed labels into
  Capture, Validate, Prepare and HTML analysis. Stage 04 now supports corrected
  mixed-label bursts by grouping on physical session+burst identity and finding
  a global class-balanced split, so adjacent frames never leak across splits.

### 2026-08-24

- Added `training/ANALYZE_TRAINING.bat` and a read-only Python analysis stage.
  Each invocation creates a timestamped offline HTML snapshot with a dashboard,
  dataset/session/burst and split analysis, training accuracy/loss curves,
  explained confusion matrix and per-class metrics, an interactive saved-frame
  gallery with Keras/TFLite inference, quantization details, HIL interpretation,
  and traceable source-file hashes. `reports/html/latest.html` points only to
  the newest snapshot; no raw/prepared data, model, state, generated NPU code,
  firmware, or hardware is changed.

### 2026-08-23

- Diagnosed the apparent CN8 USB descriptor hang as a Neural-ART BUSIF1 fault,
  not a USB PHY failure. Stage 08 had relocated the xSPI2 weight addresses to
  NPU SRAM6 but retained `cacheable=1`, so the first weight fetch selected the
  xSPI/cache bus path and the LL_ATON interrupt assertion stopped the complete
  firmware. Stage 08 now converts every initializer DMA descriptor to the
  non-cacheable SRAM6 contract and rejects any cacheable descriptor left after
  relocation.
- Rebuilt and loaded Secure + Non-Secure from SRAM without changing external
  Flash. Hardware reached the first completed ToF transform, CN8 enumerated as
  `VID_0483&PID_5740`, and Windows created the board CDC port.
- Stage 09 passed 100 CRC-valid, distinct frames with 100/100 frame-matched NPU
  results, monotonic run counters, zero NPU errors, 100% class agreement, and a
  maximum raw int8 delta of 10. The learning profile now documents a configurable
  raw-score tolerance of 16 (0.0625 at the model's 1/256 output scale), while
  retaining 95% minimum class agreement and 80% minimum NPU coverage.
- Stage 11 now checks the one-time 08B bootstrap and exact-model HIL before
  prompting for a new firmware version. The signed 08B build-only path passed;
  persistent SWD/XMODEM writes still require the explicit `BOOTCHAIN`/`FLASH`
  confirmations.

### 2026-08-23

- Reworked RPS preprocessing after HIL proved that the deployed PC and NPU
  models agreed exactly but both collapsed to `none`. The shared Python/C
  contract now selects the nearest non-trivial connected depth component,
  rejects isolated speckles, crops it, and encodes relative rather than
  absolute depth. Capture shows and stores the exact 64x50 model input.
- Replaced global-average classification with a compact spatial CNN, added
  deterministic train-only translation/mirror/intensity augmentation, eight
  burst groups per class, session-diversity warnings, per-class test gates and
  a confusion matrix. `training/RESET_TRAINING_DATA.bat` provides an explicitly
  confirmed, scoped reset while preserving tools and capture-capable firmware.
- Capped embedded Neural-ART RPS weights at 64 KiB and compacted the spatial
  head after a 94,769-byte model reduced the VL53L9 heap below its hard gate.
  The replacement is 55,441 bytes, improves held-out macro accuracy to 75%,
  and leaves 387,816 bytes of Non-Secure C heap. Stage 08 now rejects an
  oversized model before the later Secure bootstrap/build step.

### 2026-08-22

- Fixed Stage 10 RAM boot after hardware diagnosis showed Non-Secure resetting
  in the first SRAM3 clear. RISAF6 was already open, but SAU region 1 ended at
  `0x241FFFFF`; it now extends through `0x243FFFFF`, covering SRAM2, NPU
  SRAM3-6, and CACHEAXI RAM. The RAM helper now incrementally rebuilds Secure
  as well as Non-Secure, uses the local FSBL handoff to replace both images,
  verifies vectors, and confirms progress through SRAM3 clear, peripheral init,
  and ThreadX before detaching. Hardware UART logs reached VL53L9 ready and
  `Neural-ART ready`; external Flash was not modified.
- Completed Stage 08 for the ToF rock/paper/scissors model. STEdgeAI 4.0 output,
  its matched STAI/LL_ATON/ThreadX runtime, and the 49,809-byte raw weight blob
  now compile into the Non-Secure image. Boot copies the embedded weights to
  NPU SRAM6, preserving atomic `.n6fw` v1 A/B update and rollback semantics.
- Added the Secure Neural-ART bootstrap for clocks, CACHEAXI, RIF/RISAF and NPU
  interrupt targeting, plus a one-time SWD boot-chain installer that preserves
  application slots. The RAM debug helper now replaces and verifies both local
  Secure and Non-Secure binaries without writing external Flash.
- Ported the frozen 54x42-mm to 64x50-uint8 preprocessing contract to firmware,
  runs Neural-ART synchronously in the ToF processing task, and added `RPS
  ON|OFF|STATUS`. N6DF v3 carries the exact NPU frame ID, four raw int8 scores,
  class, confidence and monotonic run count under header CRC.
- Added HIL gates for frame-matched NPU coverage, advancing run counter, at
  least 95% host/device class agreement and raw-score delta <=3. Large CDC/RPS
  scratch buffers moved to reserved SRAM3; the clean linked image retains
  396,264 bytes of VL53L9 heap. Firmware and Python synthetic builds pass;
  physical NPU HIL and persistent XMODEM installation remain pending.
- Stage 09 now performs an `RPS ON`/`RPS STATUS` preflight before importing
  TensorFlow or collecting frames. It rejects stale SRAM images and NPU init
  failures immediately and records the diagnostic in `hil_validation.log`.

### 2026-08-21

- Added a fast Non-Secure development lane. It invokes the generated makefile
  incrementally without producing the large disassembly listing, preserves the
  firmware version, and can load the raw image into SRAM2 through its Secure
  alias while retaining ELF symbols for interactive GDB. The loader reaches
  Secure `main()` by loading the known-good FSBL ELF in DEV boot and letting it
  load Secure from external Flash before replacing the Non-Secure RAM image, so
  TrustZone and board initialization remain representative. Reset intentionally
  returns to the DEV-boot ROM without touching external Flash.
- Added an automated final Non-Secure release lane. It accepts an explicit
  `current + 1` version, builds and signs only Non-Secure, creates the signed
  `.n6fw`, auto-detects CN8, sends XMODEM-CRC 1K blocks with bounded retries,
  waits through trial confirmation, and verifies the running `version` command.
  `PackageOnly` restores the tracked version and does not modify hardware.
- Verified the incremental build, heap/image guards, version transaction,
  STM32 v2.3 signing, `.n6fw` generation, and XMODEM CRC self-test. Hardware
  probing confirmed that Flash boot closes N6 debug access as designed. The
  corrected DEV-boot helper then loaded the FSBL, stopped at Secure `main()`,
  replaced and verified Non-Secure in SRAM, reached Non-Secure `main()`, and
  detached in 13.4 seconds without a rebuild. CN8 returned `Firmware version:
  8`, confirming that the new RAM image was running. Physical XMODEM transfer
  and rollback validation remain pending. CubeMX Generate Code is not required.

### 2026-08-18

- Fixed the reintroduced VL53L9 first-frame transform error `-14`. The exact
  programmed ELF left only 353,512 bytes between `_end` and `_sstack`, below
  the transform's measured 356,688-byte allocation set even before malloc
  metadata. Sensor initialization and the complete first I3C DMA frame had
  already succeeded, confirming that this was SRAM pressure rather than a
  VL53L9CX communication or wiring fault.
- Replaced the GC9A01 startup screen's separate 4,096-byte clear buffer and
  5,656-byte text bitmap with one shared 404-byte DMA row buffer. Reduced the
  USBX parent ThreadX pool from 64 KiB to 56 KiB while preserving its 32 KiB
  system arena and 16 KiB control-task stack. The clean-linked image now leaves
  371,240 bytes for the C heap.
- Added a pre-signing build guard requiring at least 360 KiB between `_end` and
  `_sstack`. Clean-built all three contexts as firmware version 8, regenerated
  the trusted images and signed update package, and programmed and verified all
  five external-NOR regions without a full erase. Post-reset ToF/CDC validation
  still requires returning BOOT1 to external-Flash boot position.

### 2026-08-01

- Added 50-column by 50-row, five-second NATI LAB identification screens to the
  FSBL, Secure runtime, and Non-Secure application. The application banner uses
  the version generated by `build_and_sign.ps1`. Added `-BootChainOnly` to
  install the FSBL and Secure banners without touching application slots or A/B
  metadata.
- Made USART1/ST-LINK the exclusive diagnostic output. CN8 CDC now contains
  only the control menu, command replies, XMODEM traffic, and the explicitly
  requested depth map. The map starts disabled, is enabled by `MAP ON`, and
  remains visible until Enter returns to the menu.
- Fixed the FSBL stopping immediately after printing pending metadata. Its
  1 KiB boot-record work item was on the 2 KiB MSP while the nested manifest,
  SHA-256, and PKA verification path was active. The work item now uses static
  FSBL storage, and stage-by-stage signature, header, and image-hash diagnostics
  make candidate validation observable. `program_flash.ps1 -FsblOnly` can
  install this recovery without overwriting either application slot or update
  metadata.
- Fixed the VL53L9 first-frame transform returning `-14` after the firmware
  update additions. The linked image left 356,872 bytes for the C heap while
  the transform's measured allocation set needs about 356,688 bytes before
  malloc metadata. Reducing the ThreadX application pool from 192 to 160 KiB
  retains roughly 40 KiB beyond its active stacks and adds 32 KiB of transform
  heap headroom; the IOC and generated configuration now agree.
- Fixed the authenticated manifest path exceeding the 2 KiB Secure MSP limit.
  GCC stack reports showed a 1304-byte `SecureFirmwareUpdate_Begin` frame;
  together with the nested SHA-256 final/update/transform path and the NSC
  wrapper, worst-case static usage exceeded MSPLIM before the PKA operation
  could start. The 1 KiB boot-record work item now lives in Secure static
  storage, reducing the measured `Begin`, `Finalize`, and `ConfirmBoot` frames
  to 288, 224, and 280 bytes respectively.
- Fixed the first physical XMODEM transfer stalling at the start. A valid
  manifest previously caused Secure `Begin` to erase the entire 1 MiB inactive
  slot synchronously before XMODEM could ACK that block. Secure now authenticates
  and opens the session immediately, then erases the inactive slot lazily in
  64 KiB sectors during bounded writes. Added COM6 breadcrumbs for the first raw
  XMODEM bytes, manifest entry, write progress/failures, and repeated CRC
  handshakes, plus a raw-mode handoff for bytes sharing the command's CDC chunk.
  The initial CRC request window is now two minutes, so choosing the package in
  a desktop file dialog does not expire the receiver after only 16 seconds.
- Fixed a second manifest-stage stall in the Secure NSC boundary. Secure
  intentionally suspends its SysTick while NonSecure runs, but the updater
  wrappers did not resume it before entering PKA and XSPI HAL calls. Their
  timeout loops could therefore never expire. Every update NSC entry now resumes
  the Secure HAL timebase for the bounded operation and suspends it again before
  returning to NonSecure.
- Fixed Secure updater initialization stopping at PKA stage 4. The Secure
  application now assigns the PKA Secure/non-privileged RIF attributes before
  starting the updater, keeps that ownership in the system isolation table,
  and resets/releases the accelerator after enabling its clock. If PKA startup
  still fails, COM6 reports its RIF attributes, RCC enable/reset registers,
  CR/SR, and CPU CONTROL value before normal Non-Secure boot continues.
- On-hardware diagnostics then showed PKA `CR.EN=1` with `SR.INITOK=0`.
  STM32N6 requires the RNG to be initialized and AHB-clocked before PKA can
  operate, including ECDSA verification. The shared crypto initialization now
  starts a Secure-owned RNG before PKA in both FSBL and AppliSecure, and reports
  a distinct RNG stage with RIF/RCC/CR/SR diagnostics if that prerequisite fails.

### 2026-07-31

- Fixed the first on-hardware update-branch boot failure. The FSBL log proved
  that both images copied correctly, but Secure stopped while initializing the
  update service. LRun had left XSPI2 in memory-mapped mode, while the Secure
  writer needs indirect-command mode. The FSBL now aborts mapping through the
  ExtMem driver before the Secure jump and reports that handover on COM6.
- Split Secure updater initialization into explicit XSPI, XSPIM, ExtMem/SFDP,
  and PKA stage codes. A failed updater now remains fail-closed and unavailable
  without bricking the normal authenticated application boot.
- Added an authenticated, transport-independent firmware-update architecture.
  CN8 USB CDC enters raw XMODEM-CRC mode through the exact
  `Start UART Firmware Update` command (or `update`), pauses map/ToF traffic,
  and streams byte arrays without dynamic allocation.
- Added 1 MiB Non-Secure A/B slots, two alternating CRC-protected metadata
  sectors, ECDSA-P256 manifest verification with the STM32 PKA, streaming and
  read-back SHA-256, strict bounds/header/vector checks, increasing-version
  enforcement, pending/trial state, five-second application confirmation, and
  automatic rollback after an unconfirmed reset.
- Kept XSPI2, PKA, update policy, flash writes, and metadata activation in the
  Secure context behind CMSE-checked NSC calls. The FSBL independently verifies
  every signed candidate before selecting it.
- Added development signing-key/package tools and automatic `.n6fw` creation to
  the full build. Factory programming now resets both metadata copies to Slot A
  so stale update state cannot survive a normal reflash.
- Build-verified FSBL, Secure, and Non-Secure with zero errors, generated fresh
  STM32 trusted images and a versioned update package, and documented that
  hardware XMODEM/trial/rollback validation is still pending. The existing
  `-nk` BootROM image flow remains a documented production-security limitation.
- Raised the USB CLI task from priority 12 to priority 9. When transform
  throughput is below the 10 fps acquisition rate, the priority-10 ToF
  processor can remain continuously ready and previously starved the CLI even
  though the CDC RX callback had accepted Enter. The CLI now runs at the CDC
  worker priority, handles the short input burst, and blocks again while the
  ToF processor continues. Added one-shot COM6 breadcrumbs for the first CDC
  input and the transition into console mode.
- Added a documented, allocation-free `menu.c/.h` command engine. It accepts
  fragmented input, waits for Enter, performs longest-prefix dispatch through
  a constant function-pointer table, passes the complete line to the handler,
  and emits one normalized CRLF-terminated reply through an application
  callback. The existing USB CLI now uses this table instead of its previous
  monolithic command dispatcher.
- Added static 192-byte command and 768-byte reply buffers, CR/LF/CRLF and
  backspace handling, discard-until-Enter overflow behavior, and a documented
  unknown-command handler. No packet or parser allocation was introduced.
- Clean-built FSBL, Secure, and Non-Secure after the menu integration and
  generated fresh version-2.3 trusted images successfully.
- Added [GUIDE.md](GUIDE.md), a from-scratch learning path covering the
  NUCLEO-N657X0-Q CubeMX setup, all four security/boot contexts, VL53L9CX
  driver import and N6 port, asynchronous I3C/ThreadX architecture, USB CDC
  integration, signing, programming, post-generation audits, and staged
  troubleshooting.
- Clean-built and signed FSBL, Secure, and Non-Secure after the rare-event
  hardening changes, then programmed and verified all three external-NOR
  regions successfully.
- Confirmed on real NUCLEO-N657X0-Q hardware that the resulting image boots from
  external Flash and that the integrated VL53L9CX I3C-DMA pipeline, USB CDC,
  and terminal output work correctly.
- Reclassified I3C DMA and the ANSI USB renderer from “awaiting verification”
  to working-on-hardware status.
- Recorded the remaining validation boundary: long-duration load, repeated USB
  attach/detach, and deliberate queue/callback/I3C fault injection have not yet
  been claimed as completed.

### 2026-07-30

- Added bounded rare-event handling for USB and ToF/I3C. USB TX callback waits
  now time out after five seconds and trigger manager-owned, capped data-plane
  recovery without reusing the in-flight static slot.
- Added sticky USB diagnostic flags and cumulative counters for unavailable
  sends, slot exhaustion, queue-full, callback timeout, transfer errors, and
  ThreadX worker-synchronization failures. A periodic manager health event
  reports them outside callback context, while `usb status` exposes the complete
  history.
- Checked USB worker event-flag, queue-receive, and completion-semaphore return
  values. CDC line-parameter bursts are now coalesced into a counter so they
  cannot consume the manager queue needed by lifecycle and error events.
- Added an ISR-safe I3C/GPIO diagnostic snapshot with HAL error/state, EVR,
  control/RX/TX DMA states, completion/IRQ counts, and ThreadX event-post
  failures. Synchronous descriptor/DMA-start failures and ThreadX event
  wait/clear failures are now retained separately. Failed ToF waits print the
  complete snapshot before stopping.
- Added sticky platform-event fallback and separately counted/rate-limited ToF
  raw-slot queue invariant failures. An invalid processing-queue receive can no
  longer spin silently.
- Fixed callback-mode CDC starvation. USBX creates additional internal
  Bulk-IN and Bulk-OUT class threads; their default ThreadX priority was 20,
  below the continuously runnable priority-10 ToF processor. Live RAM counters
  showed two queued maps, one submitted transfer, zero completed bytes, and
  zero callbacks. The class workers now run at priority 8 with 8 KiB stacks;
  the USBX system pool and its parent byte pool were enlarged accordingly.
- Added a one-shot CDC diagnostic message scheduled three seconds after each
  successful class activation. A ThreadX timer only posts an event; the USB
  manager performs the readiness check and static-slot enqueue in thread
  context. The message is discarded when CDC is no longer configured.
- Gated every TX slot allocation on both the active session and the USBX
  `UX_DEVICE_CONFIGURED` state. Disconnect still invalidates the session and
  flushes all queues, so producers cannot accumulate stale output while the
  host is absent.
- Changed the build/sign helper to clean-build NonSecure every time. This is
  required because CubeIDE can retain stale linked USBX middleware objects
  after `ux_user.h` changes; an earlier incremental image therefore kept the
  old priority-20 class threads even though the header had been corrected.
- Fixed the combined asynchronous VL53L9 register read. Two separate calls to
  `HAL_I3C_AddDescToFrame()` do not append descriptors: the second call resets
  the first frame. The address-write and repeated-start payload-read
  descriptors are now prepared together in one two-descriptor HAL frame.
- Routed `EXTI9_IRQn` explicitly from Secure to the Non-Secure vector table.
  The EXTI line had already been marked Non-Secure, but its NVIC target was
  still Secure, so the new event-driven ToF acquisition task could miss every
  PD9 falling edge and report `sensor interrupt timeout`.
- Added the repository-root `.gitignore` for STM32CubeIDE build output, signed
  images, local downloads, reference material, backups, and operating-system
  files.
- Moved complete X-CUBE packages, ZIP archives, PDFs, the official CDC test,
  diagnostics, and `backup1.zip` into ignored `.local-dependencies` folders.
- Vendored the 1.24 MB ST67W6X source subset actually referenced by the build
  under `ThirdParty`, retained the ST license files, and repointed the
  Non-Secure CubeIDE links/include paths. A forced full Non-Secure rebuild
  succeeded without the original extracted SDK at its old path.
- Replaced the CDC packet byte pool with deterministic static storage: eight
  768-byte control TX slots, two 48 KiB map TX slots, and sixteen 512-byte RX
  slots. Steady-state USB traffic now performs no allocation.
- Enabled USBX CDC callback transmission mode. The TX scheduler submits one
  `write_with_callback` request and waits for its completion semaphore before
  advancing; partial completions are resumed and errors are reported to the
  USB manager.
- Changed the ToF renderer to write directly into a reserved USB map slot,
  eliminating the full ANSI-frame copy.
- Split ToF into priority-7 acquisition and priority-10 processing tasks with
  three fixed 14,842-byte raw-frame slots and free/ready queues. When processing
  lags, the oldest unclaimed frame is dropped to preserve live-display latency.
- Converted the complete steady-state sensor transaction chain to asynchronous
  I3C DMA: main frame read, DSS map command, DSS read, DSS unmap, status read,
  and frame acknowledgement. Task waits use ThreadX event flags posted from TX,
  RX, multiple-transfer, GPIO, and error callbacks.
- Assigned PD9 to falling-edge EXTI in the IOC while the absent ST67 radio is
  disabled; PE9 is a plain input because both pins share EXTI line 9.
- Created and verified `backup1.zip` before modifying the USB architecture.
  The archive contains 12,353 entries and its SHA-256 is
  `3BA7A701F1E7219D1188F160A13479AB71989162C7AB5FFABC68A22C642A6A21`.
  It is now retained locally under `.local-dependencies/backups/backup1.zip`.
- Replaced the earlier CDC single-frame mailbox with a control-plane/data-plane
  architecture: one USB manager task and independent RX/TX workers.
- Expanded the manager event queue to carry Device START/STOP, CDC lifecycle,
  parameter-change, and worker-error events.
- Initially added bounded packet queues and a 64 KiB byte pool; this interim
  design was superseded the same day by the deterministic static-slot design
  described above.
- Added session-tagged packet ownership so detach/reconnect cannot deliver a
  stale packet through a newly activated CDC instance.
- Made the RX worker the only low-level CDC reader and the TX worker the only
  low-level CDC writer. Application code now interacts only through
  allocation-and-enqueue APIs.
- Changed `app_console.c` into a thin asynchronous transport facade and removed
  its old 48 KiB static mailbox, mutex set, semaphore, and 32 KiB TX task.
- Added disconnect quiescing: invalidate the CDC session, abort through USBX,
  wait for both workers to become idle, release queued packets, then deinitialize
  the USB peripheral.
- Added flow-control and diagnostic counters plus the `usb status` CLI command.
- Fixed the X-CUBE asynchronous I3C lifetime defect: DMA descriptors and their
  referenced address/control/status buffers now live in a persistent context
  rather than in a returned function's stack frame.
- Added stage-specific COM6 diagnostics for I3C asynchronous-start failures,
  including HAL status, I3C state/error, control/RX DMA states, and EVR.
- Built the Non-Secure application successfully with 0 compile errors and 0
  compile warnings. The linked image is 575,896 bytes of text, data, and BSS;
  worker stack-usage reports show 576 bytes for RX and 72 bytes for TX before
  library call depth, versus 12 KiB reserved for each worker.

### 2026-07-29

- Changed the VL53L9CX from one-shot manual triggering to autonomous ranging
  with a 100 ms frame period. Sensor acquisition now overlaps the transform and
  terminal-rendering work for the previous frame.
- Changed the Non-Secure Debug C and C++ optimization from `-O0` to `-O3`
  while retaining `-g3` debug information. The measured `-O0` transform time
  of about 264 ms was the main reason the application could not approach the
  sensor's 10 fps maximum.
- Kept I3C1 at 12.5 MHz and the STM32N657 at 600 MHz. These were already at the
  intended project limits; no bus or MCU overclock was introduced.
- Initially interpreted the largest GCC `.su` entries as one active call path
  and raised the ToF stack to 320 KiB and its pool to 384 KiB. Hardware then
  returned transform error `-14`: the oversized static allocation had starved
  the transform's dynamic heap.
- Re-audited the actual control flow. Rate-normalization `fast_mode` bypasses
  the 146,784-byte slow function, and native 54×42 calibration bypasses the
  55,400-byte resize function. The active sharpener chain is about 34 KiB, so
  the ToF stack is now 96 KiB and the application pool is again 192 KiB. This
  restores roughly 192 KiB to the C heap while retaining substantial active
  stack margin. The IOC was updated to match.
- Replaced the generic "check shield jumpers and wiring" fatal text. Transform
  error `-14` now identifies a memory/resource failure and explicitly notes
  that sensor communication had already succeeded.
- Completed a full FSBL/Secure/Non-Secure build and regenerated all three
  version 2.3 trusted images. After correcting the stack/heap balance, the
  optimized Non-Secure image links at 560,576 bytes of text, data, and BSS,
  leaving roughly 476 KiB in its 1023 KiB RAM region for the C heap and runtime
  margin.
- Confirmed successful CDC ACM enumeration as COM7 in the integrated
  Secure/Non-Secure application.
- Moved full ANSI-map transmission to a dedicated CDC TX task, following the
  official ST example's separation of USB writes from the producer task.
  USBX's direct CDC write is blocking; a slow or unopened host terminal can no
  longer stop I3C acquisition and depth transformation.
- Added a single-frame asynchronous mailbox: at most one complete 48 KiB map
  buffer is pending or in flight. New maps are dropped while USB is busy rather
  than accumulating stale frames or exhausting RAM.
- Added first-transfer UART breadcrumbs and a periodic ToF heartbeat every ten
  processed frames, making a quiet COM6 log distinguishable from a stalled
  task.
- Increased the dedicated USB CDC TX stack from 4 KiB to 32 KiB for generous
  bring-up headroom. The stack is statically allocated and does not consume the
  ThreadX application byte pool.
- Located the blocked first bulk-IN transfer in the official FIFO sizing: CDC
  EP1 advertises 512-byte High-Speed packets but was assigned only a 64-byte Tx
  FIFO. Increased EP1 from 0x10 to 0x100 words (1024 bytes), sufficient for two
  complete packets in the HAL's non-DMA transmit path.
- Confirmed ST's unmodified NUCLEO-N657X0-Q ThreadX/USBX CDC ACM example
  enumerates as COM7 on the same board, cable, connector, and PC.
- Found the decisive clock mismatch: USB selected HSE while the project FSBL
  generated `RCC_HSE_OFF`.
- Added PH0/PH1 HSE digital-bypass ownership to the FSBL in `N6.ioc`; generated
  FSBL now uses `RCC_HSE_BYPASS_DIGITAL` like ST's working example.
- Repaired post-Generate multi-context project damage: restored the official
  STM32Cube FW N6 V1.4.0 HAL driver set, re-enabled FSBL BSEC/XSPI, restored the
  Non-Secure Nucleo BSP include path, and restored HAL UART source links.
- Removed the temporary HAL/LL USB instrumentation when CubeMX regenerated the
  vendor drivers; the local HAL source tree is again the official V1.4.0 code.
- Rebuilt all three contexts successfully and regenerated all version 2.3
  trusted images.
- Programmed and verified the corrected FSBL, Secure, and Non-Secure images in
  external NOR at 0x70000000, 0x70100000, and 0x70180000 respectively.
- The first post-Generate boot reproduced `CFSR_NS.STKOF`; exact ELF mapping
  placed PC in `HAL_RCCEx_PeriphCLKConfig` and LR in
  `PWR_TCPP0203_Configure_ADC`. CubeMX had restored the CAD stack to 1 KiB.
- Restored `OS_CAD_STACK_SIZE` to `N6_USBPD_CAD_STACK_SIZE` (8 KiB) and added
  a build-and-sign preflight that refuses to sign if this mapping regresses.
- Explicitly applied the USBPHY1 kernel-clock mux in an MSP USER block. CubeMX populated `UsbPhy1ClockSelection` but requested only `RCC_PERIPHCLK_USBOTGHS1`, so HAL did not consume the PHY selection field.
- Added UART reporting for the effective USBPHY1/OTGHS1 frequencies and the RCC clock/reset registers after PHY bring-up.
- Aligned USB startup with ST's official event flow: the PCD now starts only after a real USB-PD CAD attach notification.
- Enabled VDDA, VDDIO2 through VDDIO5, and VDDUSB in the FSBL before `HAL_Init()`, as done by ST's official CDC example.
- Added a PCD-handle clear before each attach-cycle initialization, matching the official example's initialization discipline.
- Ported the explicit USB1 HS-PHY reset, clock-reference, control-register, and reset-release sequence from ST's official NUCLEO-N657X0-Q CDC ACM example.
- Initially copied the official CDC Rx/Tx FIFO sizing after `HAL_PCD_Init`, then
  corrected its undersized High-Speed EP1 Tx FIFO after the first real bulk-IN
  transfer exposed the deterministic deadlock.
- Added UART breadcrumbs around PCD MSP, PHY reset/release, HAL PCD return, and FIFO configuration.
- Added temporary HAL/LL USB stage diagnostics to identify the exact wait inside `HAL_PCD_Init`.
- Confirmed through UART that CN8 Type-C attachment is detected on CC2 and reaches the Device START notification path.
- Converted README and AGENTS documentation to English.
- Added a detailed outside-USER CODE inventory and ST bug assessment.
- Documented the confirmed missing-break bug in X-CUBE-53L9A1 V1.0.0.
- Corrected the USBX stack narrative: the demonstrated STKOF was in the USB-PD CAD task.
- Mapped the cable-attachment crash to the TCPP0203 ADC/RCC path.
- Increased the CAD stack from 1 KiB to 8 KiB.
- Increased the USB-PD pool from 5000 bytes to 16 KiB.
- Increased the USBX control stack to a conservative 16 KiB bring-up value.
- Increased the USBX pool to 32 KiB and updated the IOC value.
- Added, then removed after CAD validation, a temporary fixed-device CDC startup independent of cable detection.
- Added the initial English project documentation.

### Earlier bring-up work

- Added external-NOR FSBL loading and version 2.3 image signing.
- Added build/sign/program scripts.
- Corrected TrustZone/RISAF handover to Non-Secure.
- Added UART diagnostics to FSBL, Secure, startup, and Non-Secure.
- Added detailed fault register and processor-state dumps.
- Integrated X-CUBE-53L9A1 and ported its platform layer to STM32N6/I3C DMA.
- Increased the ToF stack to 64 KiB after the original transform-stack
  overflow; the later 10 fps optimized build uses 96 KiB after combining GCC
  stack-usage data with actual control-flow analysis.
- Completed full 54×42 acquisition and ANSI rendering.
- Integrated the ST67W6X driver in a separate optional task.
- Added a feature flag that completely suppresses radio initialization.
- Added the USB CDC console, CLI, TCPP0203 BSP, and Type-C diagnostics.
