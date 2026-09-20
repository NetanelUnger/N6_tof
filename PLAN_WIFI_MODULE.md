# ST67W61 Wi-Fi/BLE and Cloud Relay Integration Plan

## 1. Purpose and fixed design decisions

This document defines the staged integration of the X-NUCLEO-67W61M1 board
with the existing STM32N657 application. The hardware/SPI baseline, Wi-Fi
station, DHCP/IP path, and BLE GATT bounded payload layers are implemented.
The BLE CLI producer/consumer is attached and the Wi-Fi scan/connect/status
path has passed physical HIL. DEBUG mirroring and the HTTPS Cloud Relay CLI
described below remain staged behind bounded interfaces.

The following decisions are fixed for the first implementation:

- Use the ST67W61M1 T01 mission architecture. The Wi-Fi, TCP/IP (LwIP),
  mbedTLS, Wi-Fi supplicant, and BLE host stacks remain inside the wireless
  module. The STM32 host does not add LwIP or another host TCP/IP stack.
- Use the module SPI mission interface and the ST AT driver supplied by
  X-CUBE-ST67W61.
- Run three radio-related ThreadX threads:
  1. the vendor SPI transfer/synchronization worker;
  2. the vendor AT response/event processing worker;
  3. one project-owned Radio Manager thread.
- Keep three independent CLI sessions: USB CDC, BLE, and Cloud Relay. They share
  commands and backend services, but never share parser/session state.
- Expose the same complete command set on all three CLI sessions. Version 1 has
  no transport-specific allowlist, denylist, or privilege difference: pairing,
  Wi-Fi control, reset, raw/debug operations, XMODEM, and both firmware-update
  paths are intentionally callable from USB, BLE, and Cloud whenever that
  session exists.
- Keep ToF images outside the CLI byte stream. BLE uses its dedicated ToF
  Notify characteristic; Cloud uses a dedicated low-priority ToF upload/event
  path so continuous frames cannot head-of-line block CLI RX or TX.
- USB CDC remains enabled as the recovery and diagnostic path, regardless of
  the selected radio CLI mode.
- The first Internet-facing Wi-Fi CLI uses outbound HTTPS only. It connects to
  `natilab-n6-h6bjh2ffbadtfyaw.israelcentral-01.azurewebsites.net:443` and
  implements the server's small REST device contract. The device does not
  implement SignalR and does not accept an inbound Internet socket.
- Direct LAN TCP/UDP CLI modes are deferred. BLE CLI can be enabled or disabled
  independently, and BLE may operate while the Cloud Relay is active.
- The radio may be compile-time enabled for the current supervised hardware
  validation. Network services remain behind a separate compile-time guard.
- Initial ST67W61M1 development must remain unlocked. No eFuse, OTP, secure
  boot, anti-rollback, production key, or permanent lock operation is allowed.

### 1.1 Implemented baseline and BLE discovery status

The safe software baseline is implemented and build-verified:

- `APP_ST67W6X_ENABLED=1` now enables the phase-1 hardware validation requested
  by the user;
- `APP_ST67W6X_BLE_GATT_ENABLED=1` enables only the BLE maintenance GATT
  discovery/connect layer;
- `APP_ST67W6X_WIFI_SERVICES_ENABLED=1` enables Wi-Fi station, scan, DHCP, and
  IPv4 reporting;
- add `APP_ST67W6X_CLOUD_RELAY_ENABLED` as a separate guard. Its normal default
  remains `0`; enable it deliberately in supervised Cloud HIL builds during
  stages 12--15, and change the normal default only after TLS, pairing, memory,
  and coexistence HIL pass;
- CHIP_EN and BOOT remain low until deliberate initialization;
- the ST transport's unusual active-high SPI chip select remains low while
  idle;
- the radio build routes EXTI9 to PE9/SPI_RDY on both edges and changes the
  ToF wait to bounded one-tick polling of PD9;
- a 64 KiB ST67 ThreadX pool is isolated at `0x242D0000` in SRAM4;
- `radio hardware`, `radio status`, and `ble status` report the transport,
  GATT, advertising, link, MTU, subscription, and pre-routing RX-drop state.
- physical SRAM HIL on 2026-09-19 passed scan, hidden-password association,
  DHCP/IP reporting, and a connected rescan while ToF/NPU and BLE advertising
  remained healthy; the SRAM4 radio pool retained 21,056 bytes.

The module now advertises as `N6-MAINT-xxxx` with two independent logical UART
services. Both services are discoverable over one BLE connection and use
separate notification subscriptions:

| Endpoint | 128-bit UUID | Properties | Current stage |
|---|---|---|---|
| CLI service | `7a1e0001-b5a3-f393-e0a9-e50e24dcca9e` | Primary service | Registered |
| CLI RX | `7a1e0002-b5a3-f393-e0a9-e50e24dcca9e` | Write / Write Without Response | 8×512-byte generation queue feeding an independent BLE parser session |
| CLI TX | `7a1e0003-b5a3-f393-e0a9-e50e24dcca9e` | Notify | BLE-session replies through an 8×768-byte queue and MTU fragmenter |
| ToF image TX | `7a1e0004-b5a3-f393-e0a9-e50e24dcca9e` | Notify | Dedicated versioned/CRC-checked frame fragments; independent CCCD and backpressure |
| DEBUG service | `7a1e0101-b5a3-f393-e0a9-e50e24dcca9e` | Primary service | Registered |
| DEBUG RX | `7a1e0102-b5a3-f393-e0a9-e50e24dcca9e` | Write / Write Without Response | Reserved and explicitly discarded by policy |
| DEBUG TX | `7a1e0103-b5a3-f393-e0a9-e50e24dcca9e` | Notify | 8×256-byte best-effort queue and MTU fragmenter; producer detached |

Advertising uses the module's validated connectable defaults and includes the
CLI service UUID without a host-supplied Flags AD structure. Device name is set
through GAP; explicit advertising-parameter and scan-response overrides remain
deferred until they can be added individually after baseline HIL. On
connection the Radio Manager requests MTU exchange and a 15--30 ms connection
interval with zero slave latency and a 4 s supervision timeout. Advertising
is restarted by the Radio Manager after disconnect.

This lab-stage GATT server uses the module's No-Input/No-Output (Just Works)
capability and is not an authenticated maintenance channel. For this demo that
risk is accepted deliberately: BLE receives the same complete CLI, including
`cloud pair`, Wi-Fi credentials/control, reset, XMODEM, and firmware update.
Production authentication and authorization remain a later hardening step;
they are not a version-1 transport restriction.

The GATT implementation performs no NCP firmware write and no eFuse, OTP,
anti-rollback, key, or permanent security operation.

## 2. Scope and non-goals

The first release will provide:

- module power/reset/boot control and SPI transport diagnostics;
- module identity and firmware-version reporting;
- Wi-Fi scan, connect, disconnect, DHCP, address, RSSI, and status reporting;
- one outbound HTTPS Cloud Relay CLI session using the deployed ASP.NET Core
  service;
- one BLE GATT CLI connection;
- simultaneous CDC, BLE, and Cloud Relay CLI sessions;
- identical command coverage and binary transfer capability on every CLI
  session;
- independent BLE and Cloud ToF image paths that can run concurrently with
  their corresponding CLI session;
- a controlled ST67W61M1 firmware-update service;
- a later Wi-Fi/BLE transport feeding the existing signed STM32 A/B updater.

The first release will not provide:

- host-side LwIP or NetX Duo networking;
- a general-purpose multi-client network server;
- transparent sharing of one `Menu_t` object across transports;
- production security provisioning or permanent NCP locking;
- automatic selection or flashing of the newest available NCP image;
- an inbound public port, a device-side HTTP server, or device-side SignalR;
- general web browsing, arbitrary URLs, redirects, or user-configurable cloud
  hosts in the first demo;
- guaranteed offline command delivery or a server database. The browser must
  keep its workspace open because the relay state is intentionally in RAM.

## 3. Hardware baseline and stacking checks

### 3.1 Current pin allocation

The display migration to SPI4 has been validated on hardware. The intended
radio mission interface is therefore free and remains:

| Function | STM32N657 pin | Notes |
|---|---:|---|
| ST67 SPI SCK | PE15 | SPI5 SCK |
| ST67 SPI MISO | PG1 | SPI5 MISO |
| ST67 SPI MOSI | PG2 | SPI5 MOSI |
| ST67 chip select | PA3 | Software-controlled NSS |
| ST67 CHIP_EN | PE10 | Module enable/reset control |
| ST67 BOOT | PD5 | Boot-mode selection |
| ST67 SPI_RDY | PE9 | Module-to-host handshake/interrupt |
| Display SCK | PE12 | SPI4 SCK |
| Display MOSI | PE14 | SPI4 MOSI |
| Display CS | PE13 | GPIO |
| Display DC | PE1 | GPIO |
| Display reset | PE2 | GPIO |

There is no separate LCD backlight GPIO in the installed display wiring. The
plan must not allocate PE7 or invent an LCD_BL signal.

### 3.2 X-NUCLEO bridge and power checks

Before fitting both expansion boards, verify with power removed:

- VDDIO is configured for 3.3 V. Do not use the special 1.8 V CHIP_EN wiring.
- The shield's normal 5 V input and onboard 3.3 V regulator path match the
  X-NUCLEO-67W61M1 user-manual bridge configuration.
- JP1 and JP2 are closed/bypassed for normal operation, unless an ammeter is
  deliberately installed in their place.
- The optional 32.768 kHz crystal/bridge configuration is recorded before any
  low-power validation. It is not required for initial functional bring-up.
- SPI_RDY is not also configured as the X-NUCLEO LED function.
- All stacked-board pins are checked for continuity and for shorts before
  power is applied.

### 3.3 UART conflict on the stacked boards

The X-NUCLEO default UART-to-Arduino routing conflicts with the ToF board on
this project: Arduino D1/D0 map to PD8/PD9, while PD8 and PD9 are used by the
ToF subsystem.

For the stacked configuration:

- open SB31 and SB34 to isolate the ST67 UART from Arduino D1/D0;
- retain SB30 and SB33 if UART access is wanted through the shield CN7 header;
- do not connect the module UART to PD8 or PD9;
- implement a future CDC-to-module-UART diagnostic bridge only after a new
  spare-USART pin audit. An external 3.3 V USB-UART connected to CN7 is the
  preferred initial recovery/programming path.

The module UART is a maintenance/manufacturing interface. Normal application
traffic uses SPI.

### 3.4 EXTI line 9 conflict

PE9 (radio SPI_RDY) and PD9 (ToF interrupt) share EXTI line 9 in the STM32.
When the radio is enabled, PE9 must own EXTI9 because SPI_RDY timing is part of
the transport handshake.

The initial coexistence policy is:

- radio disabled: PD9 may remain the ToF EXTI source;
- radio enabled: PE9 owns EXTI9, and ToF data-ready is checked by bounded PD9
  polling from the existing acquisition cadence;
- retain I3C DMA for ToF transfers;
- consider I3C IBI only after sensor support and timing have been proven.

This policy must be made explicit in the IOC and in the generated-code audit.
A logic analyzer should observe SPI5 SCK/MOSI/MISO, NSS, and SPI_RDY during
bring-up.

## 4. System architecture

### 4.1 T01 offload model

T01 is selected because it keeps the network and BLE stacks on the ST67W61M1.
The STM32 communicates with the module through AT commands and data/events over
SPI. The host receives socket and BLE events and moves application payloads; it
does not route packets through a local TCP/IP stack.

The project build must explicitly select the T01 architecture and use a
compatible T01 mission image. The expected vendor image family is named like
`st67w611m_mission_t01_v2.x.y.bin`. Exact driver and module firmware versions
must be pinned as a tested pair.

### 4.2 Ownership and thread model

Only the Radio Manager may call public W6X Wi-Fi, network, BLE, or firmware
update APIs. This serializes the AT control plane and avoids accidental command
interleaving from CLI callbacks or other application threads.

| Thread | Owner | Initial role | Stack baseline |
|---|---|---|---:|
| SPI worker | ST compatibility layer | SPI transfer, SPI_RDY synchronization, queues | 768 B |
| AT worker | ST modem layer | Parse responses/events and dispatch callbacks | 2,048 B |
| Radio Manager | Project | State machine, requests, sockets, BLE, recovery | 8 KiB |

The first two threads are created by the vendor driver through the FreeRTOS
compatibility layer, but they run as native ThreadX threads. The Radio Manager
is created by `app_threadx.c`.

The existing vendor priorities map the AT and SPI workers above normal
application threads. That is appropriate for prompt SPI_RDY servicing, but the
mapping must be printed at startup and verified so sustained radio traffic does
not starve the priority-7 ToF acquisition task.

Callbacks must do only bounded work: copy metadata/payload into a fixed queue,
set an event flag, update counters, and return. They must not execute CLI
commands, wait for another W6X command, perform long logging, or write firmware.

### 4.3 Radio Manager state machine

The Radio Manager should use explicit states rather than ad-hoc command calls:

`OFF -> BOOTING -> TRANSPORT_READY -> MODULE_READY -> WIFI_READY/BLE_READY ->
RUNNING -> RECOVERING -> FAILED`

Wi-Fi and BLE are independent sub-states under `MODULE_READY`. A bounded retry
policy resets the module after repeated transport timeouts. Every reset
increments a module-generation counter so stale events and responses can be
discarded safely.

Application requests use a bounded ThreadX queue and include:

- operation type and timeout;
- request/session generation;
- origin CLI session token, if any;
- either a small inline payload or ownership of a fixed buffer slot;
- completion destination for an asynchronous result.

### 4.4 Cloud Relay split

The browser and device deliberately use different transports:

```text
Browser -- HTTPS + SignalR --> N6.CloudRelay <-- HTTPS REST long poll -- ST67/STM32
```

SignalR exists only between the React page and ASP.NET Core. The firmware does
not need a WebSocket or SignalR implementation. It opens outbound TLS sockets,
sends ordinary HTTP/1.1 requests, and closes or reuses them according to the
bounded connection state machine. The server keeps only the active browser
workspace, device command queues, and transient output routing in RAM. The
browser's downloaded JSON file is the durable device list; there is no server
database.

## 5. Three independent CLI sessions

### 5.1 Session model

The current USB CLI task should evolve into one transport-neutral CLI broker.
The broker owns three separate session objects:

- `CLI_SESSION_CDC`;
- `CLI_SESSION_BLE`;
- `CLI_SESSION_CLOUD`.

Each session owns its own `Menu_t`, line input buffer, reply buffer, editing and
history state, binary-transfer state, transport generation, and TX queue.
`Menu_t` is single-task-owned and must never be shared concurrently.

All sessions may use the same immutable command table and backend service
functions. A command that needs the radio posts an asynchronous request to the
Radio Manager. The response carries the origin token and is routed only to the
session that issued it.

CDC and BLE RX producers enqueue chunks such as:

```text
{ transport, session_generation, byte_count, bytes[] }
```

They do not assume that a received chunk is one command line. The CLI broker
feeds chunks to the correct parser and recognizes CR, LF, and CRLF across chunk
boundaries. Cloud commands are already complete JSON string values; after
bounded JSON decoding, the transport submits the command bytes plus one CRLF
to its private `Menu_t`. Version 1 accepts printable ASCII command lines only
and rejects lines longer than the existing 191-byte menu limit even though the
server currently accepts up to 512 characters.

The Cloud transport processes one foreground CLI transaction at a time. Long
asynchronous commands carry both the Cloud session generation and server
`commandId` until their final reply, so output cannot be attached to a newer
command. The logical Cloud CLI stream supports typed text and binary records;
after a command enters XMODEM/update mode, subsequent binary records are fed to
that session exactly as BLE or CDC bytes would be. The dedicated ToF stream is
the sole data stream that does not share the CLI transport.

### 5.2 Transport policy

Recommended persistent settings are:

```text
radio.enabled             = true for the current validated shield build
cli.cdc.enabled           = true
cli.ble.enabled           = independently controlled
cli.cloud.enabled         = false until pairing succeeds, then auto-start
cli.cloud.host            = compile-time fixed Azure hostname
cli.cloud.port            = 443 only
cli.cloud.poll_seconds    = 20
cli.cloud.inactive_backoff = 30
radio.wifi_ble_parallel   = allowed
```

The same command syntax, confirmation prompts, and side effects apply on every
session. A command that intentionally disconnects its own transport first
queues a bounded `accepted`/final reply when technically possible, then applies
the change asynchronously. Loss of the issuing session after `wifi disconnect`,
`radio disable`, `ble disconnect`, reboot, update, or unpair is expected
behavior, not an authorization failure. USB remains the recommended recovery
path, but it has no exclusive commands.

## 6. HTTPS Cloud Relay CLI using the module stack

### 6.1 Fixed endpoint and transport boundary

The version-1 endpoint is deliberately compiled into the firmware:

```text
scheme: https
host:   natilab-n6-h6bjh2ffbadtfyaw.israelcentral-01.azurewebsites.net
port:   443
base:   /api
```

The Radio Manager uses the T01 DNS and BSD-like socket APIs. It resolves the
hostname on each new connection, creates `W6X_Net_Socket(AF_INET, SOCK_STREAM,
IPPROTO_TLS_1_2)`, installs a reviewed CA root, sets `TLS_HOSTNAME` to the exact
hostname for SNI/certificate validation, connects to port 443, and sends
HTTP/1.1. It never pins an Azure IP address and never follows redirects.

Do not use `W6X_HTTP_Client_Request()` for this protocol without first changing
and revalidating it. The current helper cannot add the required `Authorization:
Bearer` header, allocates a request task and buffers dynamically, uses a
one-second receive timeout, and only searches for `Content-Length`. The Cloud
Relay currently may return `Transfer-Encoding: chunked`. A project-owned,
bounded HTTP/1.1 codec over the raw TLS socket is therefore the initial design.

### 6.2 End-to-end conversation

1. The browser creates or opens its local workspace JSON and connects to
   `/hubs/relay` with SignalR.
2. The browser requests a six-digit pairing code. It is single-use and expires
   after five minutes.
3. The operator enters `cloud pair <code>` through USB CDC or the BLE CLI.
4. The device posts its identity/status to `/api/device/pair` and receives a
   `deviceToken` capability bound to the browser workspace and device ID.
5. The device stores the bounded pairing record in the NCP filesystem, starts
   the Cloud state machine, and posts current firmware/IP/RSSI status.
6. The device long-polls `/api/device/commands?waitSeconds=20` with the bearer
   token. A normal browser command returns as
   `{ id, kind: "text", line, sequence, createdAt }`; no pending CLI record
   returns HTTP 204. XMODEM/update mode uses ordered `kind: "binary"` records
   under the same command ID.
7. The Cloud transport submits decoded text or binary bytes to
   `CLI_SESSION_CLOUD`.
8. The broker executes the same shared CLI handler exposed on USB and BLE and
   returns ordered text or binary CLI records to
   `/api/device/commands/{commandId}/output`.
9. ASP.NET Core forwards each output chunk to the browser over SignalR, so the
   page behaves as a per-device terminal.

A cable-free bootstrap is therefore valid: connect to the BLE CLI, run
`wifi connect` and enter the credentials there, wait for `wifi ip`, then run
`cloud pair <code>` on that same BLE session. Once paired, the Cloud CLI exposes
the identical command table.

### 6.3 Device REST contract

| Method and path | Authentication | Device action | Expected results |
|---|---|---|---|
| `GET /api/health` | none | TLS/DNS/server reachability test | 200 JSON |
| `POST /api/device/pair` | six-digit body code | one-time pairing | 200 with `deviceId`, `workspaceId`, `deviceToken`; 404 invalid/expired |
| `POST /api/device/status` | bearer device token | publish firmware, IPv4 and RSSI | 204; 409 workspace inactive; 401/403 token/device rejection |
| `GET /api/device/commands?waitSeconds=20` | bearer device token | wait for one CLI command | 200 JSON command; 204 timeout; 409 inactive |
| `POST /api/device/commands/{id}/output` | bearer device token | publish one ordered text/binary CLI record | 202; 409 inactive; 400 malformed/oversized |
| `POST /api/device/tof/frames` | bearer device token | publish one binary ToF frame on the independent media path | 202; 204 no subscriber; 409 inactive; 400 malformed/oversized |

Pairing request body:

```json
{"code":"123456","deviceId":"n6-b8fb","name":"N6-B8FB","firmwareVersion":"9","ipAddress":"192.0.2.10","rssi":-42}
```

Text output request body:

```json
{"kind":"text","sequence":0,"text":"Firmware version: 9\r\n","completed":true}
```

Binary CLI input/output record shape:

```json
{"kind":"binary","sequence":1,"offset":1024,"dataBase64":"...","crc32":"89abcdef","completed":false}
```

The server contract must be extended before Cloud XMODEM/OTA is enabled. Input
and output records carry `kind: "text" | "binary"`; binary records carry a
bounded base64 field plus sequence/offset/CRC metadata. A decoded record is at
most one supported XMODEM block plus framing. Text replies remain conservative
384-byte chunks. This is one logical CLI byte stream, not a fourth user-facing
channel, and preserves the command/update state machine already used by CDC and
BLE.

JSON parsing and generation must use fixed buffers, explicit length checks, and
correct escaping for quote, backslash, CR, LF, tab, and control bytes. Do not
parse JSON with `strstr` field extraction. Base64 must reject invalid alphabet,
padding, decoded lengths, offsets, and CRC before bytes reach the CLI/update
consumer.

### 6.4 Independent Cloud ToF path

Cloud ToF is deliberately not printed or encoded into CLI replies. The device
uses a second, low-priority Cloud state machine and preferably a second TLS
socket to stream a compact binary frame envelope to
`POST /api/device/tof/frames`. The envelope reuses the BLE image metadata:
version, frame ID, width, height, channel ID, float32-LE pixel format, payload
length, and CRC32, followed by the frame bytes. A 54×42 float frame is 9,072
payload bytes and is sent directly from the owned frame slot without another
full-frame copy.

The ASP.NET service validates the token/envelope and emits a separate
`tofFrame` SignalR event to the device workspace. CLI output continues on its
existing command-output event. The browser maintains separate terminal and ToF
consumers, so a slow renderer cannot block terminal RX/TX.

CLI always has scheduler, socket, and queue priority over ToF. At most one ToF
frame may wait and one may be in flight; when the path is busy, drop/replace a
frame and increment counters rather than delaying a CLI poll or output. Closing
the ToF subscription stops uploads without closing the Cloud CLI. The present
server does not yet expose this endpoint/event; they are required server-side
work in the same implementation stage.

### 6.5 Pairing and persistence

The browser keeps the workspace token and allowed device IDs in its local JSON
file. The server stores no device database. The device stores one versioned
record in the NCP filesystem, for example `n6cloud.cfg`, containing:

- record magic/version and total length;
- fixed device ID, at most 64 UTF-8 bytes;
- workspace ID returned by pairing, at most 64 bytes;
- bearer device token with an explicit 1,024-byte ceiling;
- enabled flag and CRC32 over the record.

Keep the complete version-1 record at or below 1,536 bytes and reject a server
response that exceeds any field or record limit. Do not truncate a token and
then persist an unusable credential.

All file API calls remain Radio-Manager-owned. After writing, read the record
back and verify its bounds, terminators and CRC. A missing, truncated or invalid
record leaves Cloud disabled and requires a new USB or BLE pairing command. The
token is a lab bearer credential stored in plaintext NCP flash: never print it,
include it in status, mirror it to DEBUG, or accept it as a CLI argument.
`cloud disable` preserves the record; `cloud unpair yes` may be issued from any
active CLI session and deletes it after the same confirmation prompt. A factory
NCP restore also removes the record.

The current Wi-Fi credentials continue to live in the NCP credential store and
the NCP auto-connect policy remains responsible for association after reset.
Cloud startup waits for `WIFI_STATE_STA_GOT_IP`; it does not duplicate the
SSID/password in the STM32 application.

### 6.6 TLS, HTTP and bounded ownership

- Configure SNTP after DHCP and confirm usable time before certificate
  validation if the NCP TLS implementation requires wall-clock time.
- Store one reviewed public CA root as a const firmware asset and add it with
  `W6X_Net_TLS_Credential_AddByContent`. Never disable certificate validation.
- Set SNI and the HTTP `Host` header to the exact Azure hostname.
- Accept HTTP/1.1 status lines, case-insensitive headers, `Content-Length`, and
  chunked transfer encoding. Reject obs-fold, oversized headers, invalid chunk
  sizes, trailers beyond the configured ceiling, and bodies above the endpoint
  limit.
- Use short socket receive slices, initially 100--250 ms, inside a 25-second
  overall long-poll deadline. The Radio Manager must return to BLE, callback,
  and recovery work between slices and must never block for the complete poll.
- Only the Radio Manager calls W6X DNS, TLS, socket, filesystem, Wi-Fi, or BLE
  APIs. The CLI broker exchanges fixed ownership-tagged request/reply slots
  with it and never touches the socket.
- Start with `Connection: close` for the first TLS/HTTP HIL if that makes
  framing deterministic. Add keep-alive only after reconnect, heap, latency,
  and NCP socket cleanup are measured.

### 6.7 Cloud state and recovery policy

The Cloud sub-state is explicit:

```text
DISABLED -> WAIT_WIFI -> DNS -> TLS_CONNECT -> HEALTHY ->
UNPAIRED | STATUS_POST -> COMMAND_POLL -> EXECUTE -> OUTPUT_POST
                                      \-> BACKOFF -> DNS/TLS_CONNECT

HEALTHY -> TOF_IDLE -> TOF_POST -> TOF_IDLE
                    \-> TOF_DROP/BACKOFF
```

- DNS/TLS/transport failures use capped exponential backoff with jitter: 2, 5,
  15, 30, then 60 seconds. A successful authenticated request resets it.
- HTTP 204 immediately starts the next long poll.
- HTTP 409 `workspace_inactive` closes the socket and waits the server-provided
  30 seconds. It does not erase pairing and does not hammer an F1 instance
  while the browser is closed.
- HTTP 401 marks the token invalid after three consecutive authenticated
  failures and requires local re-pairing. HTTP 403 means the browser workspace
  no longer allows the device; remain paired but stop command polling until the
  browser re-adds it or the operator unpairs locally.
- Wi-Fi loss cancels the current generation, closes the TLS socket, releases
  every fixed slot, and returns to `WAIT_WIFI`. BLE and CDC sessions remain
  independent unless module recovery requires a full reset.
- Every module reset, Wi-Fi reconnect, Cloud reconnect, and unpair increments
  the Cloud generation. Late socket bytes and asynchronous CLI completions from
  an older generation are discarded.

The current server intentionally offers live-demo semantics, not durable
messaging. A command is removed from its RAM queue before the HTTP response is
acknowledged, and output POSTs are not deduplicated. Because every command,
including destructive commands, is intentionally available through Cloud, the
Cloud implementation gate includes explicit command acknowledgement and
in-RAM `(deviceId, commandId, sequence)` deduplication before the full CLI is
enabled. Firmware executes a received command at most once and exposes
lost/uncertain counters. No database is required for this active-workspace
improvement.

### 6.8 Equal CLI routing policy

Do not add transport permission bits or transport-specific command lists. The
same immutable command table is presented by USB, BLE, and Cloud, and `help`
shows one command inventory without `[U]`, `[B]`, or Cloud-only labels. Feature
availability may still depend on compiled hardware or current state, but never
on which CLI transport issued the command.

This includes Wi-Fi connect/disconnect/forget and credential entry, Cloud
pair/enable/disable/reconnect/unpair, BLE advertising/disconnect control,
reboot, XMODEM/NCP update/STM32 OTA, dataset commands, arbitrary diagnostic
commands, and raw memory/flash commands already present in the common CLI.
Transport-ending commands use the normal confirmation and deferred-action
mechanism; they are not rejected merely because their reply path will close.

The Cloud reply callback attaches the active `commandId`, monotonically
increasing `sequence`, and `completed=false` to intermediate chunks. Exactly
one final post has `completed=true`, including execution errors. The device
does not request another command until the current command
has reached a final local state.

## 7. BLE maintenance GATT

The maintenance layer implements two project-specific UART-like services plus
the dedicated ToF image characteristic: CLI RX/TX, ToF TX, and DEBUG RX/TX.
The independent characteristics and CCCDs prevent a slow image/debug subscriber
from becoming the CLI's flow-control state. RX supports both Write With
Response and Write Without Response; TX uses Notify. The transport
stage copies callback-owned CLI RX data before the vendor callback returns,
uses bounded generation-tagged queues in SRAM4, and lets only the Radio Manager
call `W6X_Ble_ServerNotify`. DEBUG RX remains reserved and is explicitly
discarded rather than becoming a second unauthenticated parser. The CLI
producer is attached through a dedicated parser/editor/history/output session;
the DEBUG output producer is not attached yet.

BLE transport framing is mandatory. A notification is not a complete CLI line
and a CLI line is not guaranteed to fit in one notification.

- The usable ATT value payload is at most negotiated MTU minus 3 bytes.
- RX writes may hold a partial line, multiple lines, or split UTF-8 data.
- TX replies are fragmented into MTU-sized chunks and reassembled by the peer.
- Permit only one outstanding indication until ACK/NACK; notifications use a
  bounded credit/window scheme.
- Write With Response is the reliable default. If Write Without Response is
  enabled, add application credits or an equivalent explicit flow-control
  mechanism.
- Use bounded RX/TX buffer slots and expose overflow, drop, retry, timeout, and
  high-water counters.
- Increment the BLE session generation on every connect/disconnect and discard
  queued data from older generations.
- Never place ToF frame bytes in BLE CLI TX. `map`/ToF CLI commands control or
  inspect the stream, while pixels use only the dedicated ToF characteristic.

This design prevents long CLI replies from overrunning the BLE link and keeps
slow or disconnected peers from consuming unbounded RAM.

## 8. Memory budget

### 8.1 Current measured constraint

With Wi-Fi, BLE CLI, XMODEM, and SPI starvation hardening linked, the general
SRAM2 region still begins at `0x24100400` and provides 1,023 KiB. The current
build leaves 369,472 bytes for the C heap. The build enforces 360 KiB because
the first VL53L9 transform has a measured peak near 356,688 bytes, leaving only
832 bytes above that guard.

The device has substantial total SRAM, but contiguous SRAM2 heap headroom is
tight. To preserve the transform contract, the two 9,072-byte transient ToF
float frames were moved into the already-cleared upper-SRAM3 CPU workspace.
That workspace now uses its complete 180,224-byte reservation. Future BLE
fragmentation/session queues must therefore use the guarded SRAM4 radio pool,
not ad-hoc SRAM2 or SRAM3 statics.

The Wi-Fi-enabled build's general ThreadX application byte pool is 134 KiB.
Existing pool-backed thread stacks account for roughly 124 KiB, leaving about
10 KiB before allocator bookkeeping and other runtime allocations. The 64 KiB
SRAM4 radio pool retained 21,056 bytes after the latest physical Wi-Fi HIL.

Blindly increasing the main pool to 192 KiB would reduce the calculated C heap
to roughly 349.6 KiB before considering additional radio-linked code/data. That
would violate the 360 KiB guard and risks the known transform allocation error.

### 8.2 Radio estimate

At the initial `W61_MAX_SPI_XFER` of 1,520 bytes, the vendor transport can
dynamically require approximately five times that value, about 7.6 KiB. Add:

- 10.75 KiB for the three radio thread stacks;
- ThreadX compatibility control blocks, queues, mutexes, and semaphores;
- AT command/response and event storage;
- Wi-Fi scan results and connection context;
- socket RX/TX buffers;
- the bounded TLS/HTTP codec, pairing record, JSON escape/parser state, and
  independent Cloud CLI session;
- BLE GATT, connection, and fragmentation queues;
- recovery and diagnostic headroom.

A 64 KiB dedicated radio byte pool is now reserved for the radio workers,
transport, and future simultaneous Wi-Fi, BLE, and remote CLI operation. It is
a budget ceiling, not permission for unbounded dynamic allocation.

### 8.3 Allocation strategy

1. The radio-disabled build retains the existing 159 KiB application pool.
2. A Wi-Fi-enabled build uses a 134 KiB general application pool (151 KiB for
   radio/BLE without Wi-Fi) and puts the Radio Manager stack, ST compatibility
   allocations, internal radio worker stacks, and transport buffers in a
   dedicated 64 KiB SRAM4 pool.
3. The pool occupies `0x242D0000..0x242DFFFF`, is 64-byte aligned and NOLOAD,
   and has a linker `ASSERT` plus map-file validation.
4. Stage 08 rejects any Neural-ART model that selects SRAM4, preventing a
   generated model from silently colliding with the pool. If SRAM4 becomes
   necessary for a later model, relocate the radio pool deliberately and
   update both guards.
5. The current Wi-Fi/BLE/XMODEM build leaves 369,472 bytes for the C heap, 832
   bytes above the enforced 360 KiB floor. Its 5,272-byte BLE session object is allocated
   from SRAM4 only after radio initialization instead of becoming another
   SRAM2 static or perturbing vendor startup allocation order. This passes
   the current contract but leaves no
   room for casual SRAM2 growth; strict map checking remains mandatory.
6. The complete Cloud addition, including its independent menu session and all
   HTTP/JSON/output slots, has an initial 12 KiB SRAM4 ceiling. The CA
   certificate remains const in Flash. Do not create another large task stack
   or allocate Cloud state from the already-critical SRAM2 heap.
7. Reject the design at build/HIL review if the Cloud-enabled radio pool keeps
   less than 8 KiB minimum free space under simultaneous HTTPS long polling,
   BLE MTU-247 traffic, ToF image notifications, and Wi-Fi scan.
8. Hardware validation must repeat CPU/SPI DMA, pool/stack high-water, and
   first-frame transform tests after the Cloud buffers are linked.

Do not increase `W61_MAX_SPI_XFER` during functional bring-up. Each increase can
have an approximately five-times effect on worst-case transport allocation.
Tune it only after correctness and memory telemetry are stable.

Required runtime telemetry:

- available bytes, fragments, allocation failures, and minimum available bytes
  for both ThreadX pools;
- high-water/remaining space for all three radio stacks;
- maximum CLI RX/TX queue occupancy per session;
- socket, HTTP parser, JSON, output and BLE buffer drops/timeouts;
- DNS/TLS connects, certificate failures, HTTP codes, backoff state, command
  IDs, output sequence counts, and uncertain-delivery counts without tokens;
- C-heap preflight result and transform peak.

## 9. Firmware lifecycle and irreversible-operation safety

There are two separate firmware-update targets:

1. the ST67W61M1 NCP firmware;
2. the STM32N657 host application firmware.

They must never share an ambiguous `fw update` command or status record.

### 9.1 Initial NCP provisioning: unlocked development only

The supplied X-CUBE binary script
`Projects/ST67W6X_Scripts/Binaries/NCP_update_mission_profile_t01.bat` is not an
approved development path for this project. It states that the signed image can
lock an unlocked ST67W61M and invokes `QConn_Flash_Cmd.exe` with an `--efuse`
file. The X-CUBE binary README also states that the supplied binaries are for a
locked NCP.

**Do not run that BAT/SH script on the development module.**

The initial programming safety gate is:

- never pass `--efuse`;
- never execute an eFuse, OTP, security-write, key-provisioning, secure-boot,
  anti-rollback, or lock operation;
- perform only read-only device-information and security-state queries first;
- record module identity, factory firmware version, security state, and tool
  version before any write;
- keep the factory T01 firmware if it is driver-compatible;
- if a reflash is required, obtain from ST an explicitly supported
  unlocked/development T01 image plus the matching boot2/partition bundle and
  an officially supported no-eFuse programming procedure;
- if ST cannot provide or confirm such a bundle, stop. Do not test a signed
  production bundle by trial on the module;
- pin and hash every binary and tool used. Never auto-select "latest";
- use a separate external 3.3 V UART on the shield CN7 for the first recovery
  path, avoiding PD8/PD9.

Omitting `--efuse` from the supplied production script is not, by itself,
evidence that the delivered signed image will boot on an unlocked module.
Bootability and non-locking behavior must both be confirmed by ST documentation
or on sacrificial hardware.

The vendor N657 loader script may also write a temporary NCP loader and CLI FSBL
into host external NOR. That can overwrite this project's FSBL. It must not be
used on the project board without an explicit backup/restore and address audit.

A future project development flasher, if ST supplies a supported unlocked
bundle, should be separately named (for example,
`NCP_update_t01_unlocked_dev.bat`) and must:

- reject arguments or manifests containing `--efuse` or security writes;
- print module identity, current state, image version, and SHA-256 before write;
- require an explicit human confirmation;
- verify every programmed region and read back the running version;
- preserve an external recovery path;
- contain no production keys or irreversible options.

Production locking, if ever required, is a separate manufacturing project. It
must use documented key custody, a reviewed provisioning record, and
sacrificial-hardware validation. It is not part of normal firmware update.

### 9.2 In-application NCP firmware update

After normal SPI operation is stable, an NCP update service may use
`W6X_FWU_Starts`, `W6X_FWU_Send`, and `W6X_FWU_Finish`. The image can arrive
through TCP/IP, BLE, USB, or local storage, but only the Radio Manager may call
the W6X firmware-update API.

The service must:

- validate target, architecture T01, version policy, length, and image hash
  before starting;
- refuse any image/manifest requiring lock, eFuse, OTP, or security change in
  development builds;
- use fixed-size streaming buffers and report progress asynchronously;
- prevent concurrent socket/BLE CLI traffic from interleaving AT operations;
- provide stable power and a watchdog policy appropriate for the update;
- wait for the module reboot, re-query identity/version, and run a health test;
- retain a UART recovery procedure and test interruption at multiple offsets;
- log the result without storing Wi-Fi credentials or keys.

The exact cryptographic acceptance behavior is ultimately enforced by the NCP
boot chain. The host policy must be stricter, but must not claim to replace NCP
image verification.

### 9.3 STM32 host firmware update over Wi-Fi/BLE

Wireless delivery does not replace the existing signed NonSecure A/B updater.
Wi-Fi or BLE code is only a downloader/transport. It must feed the existing
Secure Begin/Write/Finalize interface and must never write executable flash,
slot metadata, rollback state, or boot-selection records directly.

Preserve the current signature, hash, bounds, anti-rollback, inactive-slot,
finalization, and boot-confirmation rules. Use backpressure so BLE/HTTPS input is
accepted only as fast as the Secure installer can safely commit it.

## 10. Security model

The Cloud CLI is never plaintext: use WPA2/WPA3 on the local link and TLS 1.2
with CA and hostname verification to the fixed Azure host. The demo deliberately
has no user account system. Its six-digit code grants a long-lived bearer
device capability to one browser workspace. This is adequate for the stated
demo, not a production device identity.

Version-1 demo rules are:

- pairing is initiated from the browser and may be completed through USB CDC
  or BLE. If a Cloud session already exists, the same `cloud pair` command is
  not transport-blocked there either; initial bootstrap obviously cannot use a
  Cloud CLI that has not yet been paired;
- never log, print, echo, expose through `status`, or include the bearer token
  in a crash report;
- expose the same full command table through USB, BLE, and Cloud. The lack of
  command restrictions on unauthenticated BLE and bearer-token Cloud access is
  an explicit demo tradeoff, not an accidental security claim;
- validate the Azure certificate chain and exact hostname; DNS success alone
  is not server authentication;
- keep Wi-Fi password entry local and hidden and continue clearing password
  buffers immediately after use;
- treat the plaintext NCP copy of `n6cloud.cfg` as a documented lab compromise.
  Production must move identity material into protected storage and support
  credential rotation/revocation.

Before field use:

- add command-level authentication and authorization per CLI session;
- require BLE pairing/bonding and an appropriate security level;
- use WPA2/WPA3 for Wi-Fi, but do not treat link encryption as CLI
  authorization;
- introduce role/command restrictions only as a separately selectable
  production policy; do not silently change the demo's equal-command contract;
- add login throttling, idle timeout, peer/session audit events, and credential
  redaction;
- replace the workspace capability with per-device provisioning, short-lived
  credentials or certificates, server-side revocation, audit, and rate limits;
- add explicit command acknowledgement/deduplication before any destructive
  remote operation is enabled.

The vendor host/module driver does not provide a SafeLink-like authenticated
SPI channel. SPI and the module maintenance UART are therefore inside the
trusted physical boundary.

## 11. Recommended implementation order

Item 1 - migration of the GC9A01 display to SPI4 and hardware validation - is
complete. Implementation continues at item 2:

2. **Freeze the stacked-hardware baseline (software complete, physical checks
   pending).** Record the successful display
   test; isolate X-NUCLEO UART bridges SB31/SB34; verify 3.3 V VDDIO, JP1/JP2,
   mission SPI/control pins, and the EXTI9 ownership policy.
3. **Inventory the NCP without writing it.** Read module identity, current
   firmware/profile, and security state through an approved read-only method.
   Do not run the supplied locking T01 update script.
4. **Establish the unlocked firmware gate.** Confirm the factory image is a
   compatible T01 image or obtain ST's explicit unlocked-development T01
   bundle and no-eFuse procedure. Stop if this cannot be proven.
5. **Bring up only GPIO and SPI/AT identity.** Enable CHIP_EN/BOOT, SPI5 DMA,
   SPI_RDY/EXTI, timeout/recovery counters, and module-info commands. Keep
   network and BLE services off.
6. **Validate the three ThreadX radio threads.** Confirm actual priority
   mapping, stacks, queues, blocking times, and pool high-water values under
   forced resets and SPI errors.
7. **Validate the guarded 64 KiB radio pool.** The linker reservation and Stage
   08 collision checks are implemented; repeat ToF/NPU memory and SPI DMA tests
   on hardware and record high-water values.
8. **Create the two-channel BLE GATT discovery layer (complete; RAM HIL
   passed).** Advertise CLI and DEBUG services, track
   independent CCCDs and MTU, and restart advertising after disconnect. No
   application bytes are routed in this stage.
9. **Attach BLE streams to the Radio Manager (complete; reconnect/ToF HIL
   passed).** Generation-tagged bounded RX/TX queues, MTU-aware
   fragmentation, finite backpressure, per-stream counters, stale-session
   purging and independent CLI/DEBUG policies are implemented in SRAM4. The
   repeated subscribe/unsubscribe/disconnect cycles pass with CRC-valid ToF
   frames. A complete physical BLE XMODEM installation remains pending.
10. **Integrate the BLE CLI session (core complete; equal-command cleanup
    pending).**
    BLE owns a separate 5,272-byte parser/editor/history/output
    session in SRAM4 after the radio reaches READY. A single priority-9 broker serializes shared command
    backends while polling CDC and BLE independently. BLE RX is drained in
    bounded bursts and replies use the item-9 backpressure/fragmenter path.
    Remove the remaining BLE-only guards around Wi-Fi credentials/control and
    reboot so the complete common command table, XMODEM, and update flows work
    identically. ToF pixels remain on the already implemented dedicated image
    characteristic. Verify CDC and BLE concurrently, then reconnect and
    exercise a deliberately slow notification subscriber.
11. **Implement Wi-Fi control (complete; physical SRAM HIL passed).** Scan,
    hidden-password join, NCP credential persistence/auto-connect, DHCP,
    RSSI/status, IPv4 reporting, disconnect, and connected rescan are working.
12. **Add the bounded HTTPS/TLS foundation.** Pin the hostname/CA, validate
    SNTP/DNS/SNI, implement the raw-socket HTTP/1.1 codec with content-length
    and chunked decoding, then pass `GET /api/health`. No CLI execution in this
    stage.
13. **Add pairing and persistence.** Implement `cloud pair` through both USB
    and BLE using the same command handler, validate/read back `n6cloud.cfg`,
    redact the token, and add disable/unpair behavior. Test reset, corrupt
    record, expired code, invalid code and NCP factory-restore cases.
14. **Complete the three-session CLI broker.** Add the independent Cloud menu,
    typed text/binary records for XMODEM/update, one-command-at-a-time
    correlation, output chunking and final completion. Verify every command is
    reachable through CDC, BLE, and Cloud while each keeps independent parser,
    transfer, error, generation, history, and output state.
15. **Add the independent Cloud ToF path and run coexistence HIL.** Add the
    binary frame endpoint and separate SignalR event, then measure ToF timing,
    display updates, radio throughput/latency, queue pressure, and recovery
    during a 20-second long poll, simultaneous Cloud CLI/ToF upload, BLE
    MTU-247 CLI/ToF traffic, Wi-Fi scan, browser close/reopen, AP loss, server
    restart, and module reset. CLI latency has priority over dropped media
    frames.
16. **Add the NCP firmware-update service.** Use the W6X FWU streaming API only
    with a pinned, verified, unlocked-development-compatible image and retain
    UART recovery.
17. **Add STM32 OTA transports.** Feed received data into the existing signed
    Secure A/B installer and run power-loss/rollback tests over both Wi-Fi and
    BLE.
18. **Perform production hardening.** Add remote authentication, authorization,
    credential protection, rate limiting, logging, and long-duration soak.
    Consider permanent NCP provisioning only as a separately reviewed
    manufacturing step on sacrificial hardware.

## 12. Validation and acceptance criteria

### 12.1 Hardware and transport

- Display continues to operate on SPI4 with both expansion boards stacked.
- ToF acquisition remains within its cadence with PE9 owning EXTI9.
- No activity or contention is observed on PD8/PD9 from the isolated NCP UART.
- SPI5 completes sustained bidirectional transfers without SPI_RDY timeout,
  DMA coherency error, or unbounded recovery loop.
- Module reset, host reset, cable removal, and brownout recover deterministically.

### 12.2 ThreadX and memory

- All three radio threads report expected priorities and bounded stack use.
- No application callback blocks the AT worker or recursively calls W6X APIs.
- Main C heap remains at or above the 360 KiB build guard.
- ToF transform reaches its measured peak without allocation error.
- Both byte pools retain an agreed minimum margin during simultaneous Wi-Fi,
  BLE, display, ToF, and NPU activity.
- Stage 08 rejects any generated model that overlaps a reserved radio SRAM
  region.

### 12.3 CLI behavior

- CDC and BLE can each hold a partial command while Cloud holds one correlated
  complete command without affecting the other sessions.
- Every command listed by `help`, including pairing, Wi-Fi control, reboot,
  XMODEM and firmware update, is accepted from USB, BLE, and an established
  Cloud CLI. There are no transport-only command labels or rejection paths.
- Replies and asynchronous completions return only to the originating session.
- Disconnect/reconnect invalidates stale buffers and authentication state.
- BLE passes tests with minimum and expanded MTU, split UTF-8, multi-packet
  replies, slow acknowledgements, queue overflow, and mid-reply disconnect.
- TLS rejects a wrong CA, wrong hostname/SNI, expired/not-yet-valid certificate,
  truncated handshake, and plaintext response.
- HTTP passes arbitrary TCP segmentation, split CRLF/header terminators,
  content-length, chunked bodies, 204, abrupt close, oversized header/body,
  malformed JSON, and command/output boundary tests.
- Pairing survives an MCU reset through the verified NCP record; a corrupt or
  missing record fails closed without exposing the token.
- Every Cloud output belongs to the received command ID, sequences from zero,
  and ends once. A new command is not polled while an old command is active.
- A command that closes its issuing transport sends its final acknowledgement
  first when possible, performs the action once, and leaves no stale session or
  command state after reconnect.

### 12.4 Cloud/Wi-Fi/BLE coexistence

- Concurrent BLE CLI/ToF notifications and Cloud CLI/ToF uploads work while
  USB CDC remains usable. A congested ToF path drops frames and never blocks
  CLI input, output, XMODEM acknowledgement, or command polling.
- Throughput reduction on the shared 2.4 GHz radio is characterized and does
  not cause application starvation.
- Wi-Fi reconnect does not destroy an active BLE session unless the module
  itself requires reset; such a reset is reported to every affected session.
- Closing the browser produces bounded 409/30-second backoff; reopening the
  same workspace resumes the existing device token without re-pairing.
- F1 cold start, server restart, DNS address change, TLS reconnect and a full
  module reset recover without unbounded loops, leaked sockets or stale output.
- Under the combined test, the SRAM2 heap remains above 360 KiB and the SRAM4
  radio pool retains at least the approved 8 KiB minimum.

### 12.5 Firmware updates

- Development provisioning logs prove no eFuse/OTP/security-write command was
  executed.
- NCP update succeeds, verifies version, and recovers cleanly after controlled
  interruption tests.
- Host OTA never bypasses the Secure installer and passes signature,
  wrong-target, truncated-image, rollback, power-loss, and boot-confirm tests.

## 13. Configuration and diagnostic commands

Initial read-only commands should include:

```text
radio info
radio state
radio stats
radio threads
radio pools
wifi status
ble status
cloud status
cloud endpoint
cloud test
cli sessions
```

Mutating commands should be asynchronous and retain their normal confirmation
and safety checks on every transport:

```text
radio enable|disable
wifi scan
wifi connect "SSID"
wifi disconnect [forget]
cloud pair <6-digit-code>
cloud enable|disable
cloud reconnect
cloud unpair yes
cli ble enable|disable
ncp update <approved-image-id>
```

Every command above is exposed through USB, BLE, and an established Cloud CLI.
Initial Cloud bootstrap can use USB or BLE because no Cloud session exists
before pairing. `cloud status`, `cloud endpoint`, and `cloud test` must redact
the bearer token and expose only state, last HTTP result, backoff, generation,
counters, and the fixed hostname.

The command set remains equal across transports. Existing irreversible-operation
checks, signed-image verification, confirmation prompts, bounds checks, and
eFuse prohibitions still apply inside their handlers; they are command safety
rules, not transport authorization.

## 14. Project integration points

- `N6.ioc`: SPI5, GPDMA, GPIO, EXTI9, NVIC, and clock source of truth.
- `AppliNonSecure/Core/Src/app_threadx.c`: project-owned Radio Manager creation
  and pool selection.
- `AppliNonSecure/Core/Src/wifi_ble_app.c`: Radio Manager initialization,
  GATT registration, callback snapshots, connection tuning, and advertising
  recovery. DNS, NCP filesystem, TLS socket calls, bounded receive slices, and
  all W6X sends remain owned here.
- proposed `AppliNonSecure/Core/Src/cloud_relay.c/.h`: Cloud state machine,
  pairing record validation, typed text/binary CLI contract, command/output
  correlation, independent low-priority ToF uploader, backoff, counters, and
  fixed queue ownership. It must call W6X only through the Radio Manager
  boundary.
- proposed `AppliNonSecure/Core/Src/cloud_http.c/.h`: allocation-free HTTP/1.1
  request builder, response parser, chunked decoder, bounded JSON codec, and
  TLS-independent parser self-tests.
- `AppliNonSecure/Core/Src/debug_cli.c`: transport-neutral commands and
  asynchronous service requests; remove the existing BLE-specific Wi-Fi and
  reboot guards, add Cloud commands, and keep one shared command table without
  transport permission masks.
- `AppliNonSecure/USBX/App/ux_device_cdc_acm.c`: CDC transport adapter only;
  it must not own the shared command implementation.
- X-CUBE `Middlewares/ST/`: W6X driver and FreeRTOS-to-ThreadX compatibility
  layer.
- Secure update client/service: sole route for STM32 executable image install.
- Stage 08 memory/collision checks: must include any reserved radio SRAM region.
- sibling web repository
  `../../Web_N6_ST67W611M1_VL53L9CX/server/N6.CloudRelay/`: authoritative
  REST contracts, bearer-token behavior, in-RAM workspace rules, and SignalR
  browser bridge. Firmware and server contract changes must be versioned and
  tested together.

The user has confirmed the shield, SPI/AT identity path, BLE GATT/CLI, and
Wi-Fi scan/connect/DHCP path. The current split flags enable both BLE GATT and
Wi-Fi services. Do not enable the Cloud command loop merely to bypass the
staged TLS, parser, typed-binary transfer, acknowledgement/deduplication,
memory, pairing, ToF isolation, and coexistence gates above.

## 15. Source basis

This plan treats vendor documents and sample code as technical references, not
as permission to execute their flashing scripts or security operations.

- ST UM3475, *Getting started with X-CUBE-ST67W61 for STM32Cube*:
  `../pdf/um3475-getting-started-with-xcubest67w61-stmicroelectronics.pdf`
- ST UM3449, *X-NUCLEO-67W61M1 expansion board user manual*:
  `../pdf/20_X-NUCLEO-67W61M1_UM3449_User_Manual.pdf`
- Local vendor package: `../x-cube-st67w61-main/`
- Locking script reviewed for the safety gate:
  `../x-cube-st67w61-main/Projects/ST67W6X_Scripts/Binaries/NCP_update_mission_profile_t01.bat`
- Vendor binary warning:
  `../x-cube-st67w61-main/Projects/ST67W6X_Scripts/Binaries/README.md`
- Vendored T01 APIs used by the new design:
  `ThirdParty/ST67W6X_Network_Driver/Api/w6x_api.h`, especially DNS,
  `W6X_Net_*`, TLS credential, socket, and NCP filesystem calls.
- Deployed lab relay:
  `https://natilab-n6-h6bjh2ffbadtfyaw.israelcentral-01.azurewebsites.net`.
  Its HTTP/SignalR smoke test passed on 2026-09-19; the firmware must still
  complete its own TLS/HTTP HIL on the ST67 module.
- Server contract sources:
  `../../Web_N6_ST67W611M1_VL53L9CX/server/N6.CloudRelay/Program.cs` and
  `RelayContracts.cs`.
