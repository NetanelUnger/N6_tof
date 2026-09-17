# ST67W61 Wi-Fi/BLE Integration Plan

## 1. Purpose and fixed design decisions

This document defines the staged integration of the X-NUCLEO-67W61M1 board
with the existing STM32N657 application. The hardware/SPI baseline and the
BLE GATT discovery and bounded payload layers are implemented. The BLE CLI
producer/consumer is now attached; DEBUG mirroring and Wi-Fi payloads remain
staged behind the interfaces described below.

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
- Keep three independent CLI sessions: USB CDC, BLE, and Wi-Fi. They share
  commands and backend services, but never share parser/session state.
- USB CDC remains enabled as the recovery and diagnostic path, regardless of
  the selected radio CLI mode.
- Wi-Fi CLI can be configured as TCP, UDP, or disabled. BLE CLI can be enabled
  or disabled independently. Wi-Fi and BLE may operate at the same time.
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
- `APP_ST67W6X_WIFI_SERVICES_ENABLED=0` keeps Wi-Fi initialization disabled;
- CHIP_EN and BOOT remain low until deliberate initialization;
- the ST transport's unusual active-high SPI chip select remains low while
  idle;
- the radio build routes EXTI9 to PE9/SPI_RDY on both edges and changes the
  ToF wait to bounded one-tick polling of PD9;
- a 64 KiB ST67 ThreadX pool is isolated at `0x242D0000` in SRAM4;
- `radio hardware`, `radio status`, and `ble status` report the transport,
  GATT, advertising, link, MTU, subscription, and pre-routing RX-drop state.

The module now advertises as `N6-MAINT-xxxx` with two independent logical UART
services. Both services are discoverable over one BLE connection and use
separate notification subscriptions:

| Endpoint | 128-bit UUID | Properties | Current stage |
|---|---|---|---|
| CLI service | `7a1e0001-b5a3-f393-e0a9-e50e24dcca9e` | Primary service | Registered |
| CLI RX | `7a1e0002-b5a3-f393-e0a9-e50e24dcca9e` | Write / Write Without Response | 8×512-byte generation queue feeding an independent BLE parser session |
| CLI TX | `7a1e0003-b5a3-f393-e0a9-e50e24dcca9e` | Notify | BLE-session replies through an 8×768-byte queue and MTU fragmenter |
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
capability and is not an authenticated maintenance channel. Firmware update,
XMODEM, reset, credential, and privileged CLI operations must not be routed to
it until application authentication and authorization are added.

The GATT implementation performs no NCP firmware write and no eFuse, OTP,
anti-rollback, key, or permanent security operation.

## 2. Scope and non-goals

The first release will provide:

- module power/reset/boot control and SPI transport diagnostics;
- module identity and firmware-version reporting;
- Wi-Fi scan, connect, disconnect, DHCP, address, RSSI, and status reporting;
- one remote Wi-Fi CLI client using either TCP or UDP;
- one BLE GATT CLI connection;
- simultaneous CDC, BLE, and Wi-Fi CLI sessions;
- a controlled ST67W61M1 firmware-update service;
- a later Wi-Fi/BLE transport feeding the existing signed STM32 A/B updater.

The first release will not provide:

- host-side LwIP or NetX Duo networking;
- a general-purpose multi-client network server;
- transparent sharing of one `Menu_t` object across transports;
- unrestricted remote access to destructive/debug commands;
- production security provisioning or permanent NCP locking;
- automatic selection or flashing of the newest available NCP image.

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

## 5. Three independent CLI sessions

### 5.1 Session model

The current USB CLI task should evolve into one transport-neutral CLI broker.
The broker owns three separate session objects:

- `CLI_SESSION_CDC`;
- `CLI_SESSION_BLE`;
- `CLI_SESSION_WIFI`.

Each session owns its own `Menu_t`, line input buffer, reply buffer, editing and
history state, authentication/privilege state, transport generation, and TX
queue. `Menu_t` is single-task-owned and must never be shared concurrently.

All sessions may use the same immutable command table and backend service
functions. A command that needs the radio posts an asynchronous request to the
Radio Manager. The response carries the origin token and is routed only to the
session that issued it.

RX producers enqueue chunks such as:

```text
{ transport, session_generation, byte_count, bytes[] }
```

They do not assume that a received chunk is one command line. The CLI broker
feeds chunks to the correct parser and recognizes CR, LF, and CRLF across chunk
boundaries.

Long commands such as scan, connect, and firmware update return an immediate
"accepted" response and later deliver completion to the originating session.

### 5.2 Transport policy

Recommended persistent settings are:

```text
radio.enabled           = false by default
cli.cdc.enabled         = true and not remotely disableable
cli.ble.enabled         = false by default
cli.wifi.mode           = disabled | tcp | udp
cli.wifi.tcp_port       = project-defined lab port
cli.wifi.udp_port       = project-defined lab port
radio.wifi_ble_parallel = allowed
```

Configuration changes that could disconnect the issuing session require a
confirmation and take effect after a controlled restart. CDC must remain
available for recovery.

## 6. Wi-Fi CLI using the module stack

The host uses the T01 BSD-like W6X socket API (`socket`, `bind`, `listen`,
`accept`, `connect`, `send`, `recv`, `sendto`, and `recvfrom`). It does not call
host LwIP APIs.

### 6.1 TCP mode

- One listening socket and one active CLI client in the first release.
- A new accepted connection creates a new Wi-Fi session generation.
- TCP reads are arbitrary stream fragments; they can contain a partial line,
  multiple lines, or only part of a UTF-8 sequence.
- Disconnect closes the session, invalidates pending TX data, and clears its
  parser/authentication state.
- Use short finite receive/send timeouts. The Radio Manager must never block
  forever inside the module socket API.

TCP is the recommended default because it supplies ordered, reliable delivery.

### 6.2 UDP mode

- One active peer lease in the first release.
- The first authorized datagram binds the CLI session to its source address and
  port until timeout/logout.
- Datagrams from other peers are rejected while the lease is active.
- Datagram boundaries are not CLI line boundaries; the normal incremental line
  parser is still used.
- Replies are sent only to the recorded peer and are capped to a configured
  datagram size.
- Application sequence numbers and optional acknowledgement are recommended
  for commands that must not be repeated.

## 7. BLE maintenance GATT

The maintenance layer implements two project-specific UART-like services:
CLI RX/TX and DEBUG RX/TX. The independent services and CCCDs prevent a slow
debug subscriber from becoming the CLI's flow-control state. RX supports both
Write With Response and Write Without Response; TX uses Notify. The transport
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
- Do not transmit the large ANSI ToF map over BLE in version 1.

This design prevents long CLI replies from overrunning the BLE link and keeps
slow or disconnected peers from consuming unbounded RAM.

## 8. Memory budget

### 8.1 Current measured constraint

With the BLE CLI session and SPI starvation hardening linked, the general SRAM2
region still begins at `0x24100400` and provides 1,023 KiB. The 2026-09-16 build
leaves 371,520 bytes for the C heap. The build enforces 360 KiB because the
first VL53L9 transform has a measured peak near 356,688 bytes, leaving 2,880
bytes above that guard.

The device has substantial total SRAM, but contiguous SRAM2 heap headroom is
tight. To preserve the transform contract, the two 9,072-byte transient ToF
float frames were moved into the already-cleared upper-SRAM3 CPU workspace.
That workspace now uses its complete 180,224-byte reservation. Future BLE
fragmentation/session queues must therefore use the guarded SRAM4 radio pool,
not ad-hoc SRAM2 or SRAM3 statics.

The radio build's ThreadX application byte pool is 151 KiB. Existing pool-backed
thread stacks account for roughly 124 KiB, leaving about 27 KiB before allocator
bookkeeping and other runtime allocations.

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
- BLE GATT, connection, and fragmentation queues;
- recovery and diagnostic headroom.

A 64 KiB dedicated radio byte pool is now reserved for the radio workers,
transport, and future simultaneous Wi-Fi, BLE, and remote CLI operation. It is
a budget ceiling, not permission for unbounded dynamic allocation.

### 8.3 Allocation strategy

1. The radio-disabled build retains the existing 159 KiB application pool.
2. A radio-enabled build reduces the general application pool to 151 KiB and
   puts the Radio Manager stack, ST compatibility allocations, internal radio
   worker stacks, and transport buffers in a dedicated 64 KiB SRAM4 pool.
3. The pool occupies `0x242D0000..0x242DFFFF`, is 64-byte aligned and NOLOAD,
   and has a linker `ASSERT` plus map-file validation.
4. Stage 08 rejects any Neural-ART model that selects SRAM4, preventing a
   generated model from silently colliding with the pool. If SRAM4 becomes
   necessary for a later model, relocate the radio pool deliberately and
   update both guards.
5. The BLE-CLI build leaves 371,520 bytes for the C heap, 2,880 bytes above
   the enforced 360 KiB floor. Its 5,272-byte BLE session object is allocated
   from SRAM4 only after radio initialization instead of becoming another
   SRAM2 static or perturbing vendor startup allocation order. This passes
   the current contract but leaves no
   room for casual SRAM2 growth; strict map checking remains mandatory.
6. Hardware validation must confirm CPU and SPI DMA access to the SRAM4 pool,
   followed by pool/stack high-water measurement.

Do not increase `W61_MAX_SPI_XFER` during functional bring-up. Each increase can
have an approximately five-times effect on worst-case transport allocation.
Tune it only after correctness and memory telemetry are stable.

Required runtime telemetry:

- available bytes, fragments, allocation failures, and minimum available bytes
  for both ThreadX pools;
- high-water/remaining space for all three radio stacks;
- maximum CLI RX/TX queue occupancy per session;
- socket and BLE buffer drops/timeouts;
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
finalization, and boot-confirmation rules. Use backpressure so BLE/TCP input is
accepted only as fast as the Secure installer can safely commit it.

## 10. Security model

For initial lab testing, a plaintext CLI is acceptable only on an isolated
network and with physical control of the BLE range. Before field use:

- add command-level authentication and authorization per CLI session;
- require BLE pairing/bonding and an appropriate security level;
- use WPA2/WPA3 for Wi-Fi, but do not treat link encryption as CLI
  authorization;
- disable firmware, memory-write, reset, credential, and raw-radio commands for
  unauthenticated remote sessions;
- add login throttling, idle timeout, peer/session audit events, and credential
  redaction;
- consider an application-secure protocol above TCP if remote operation crosses
  a trusted LAN boundary.

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
9. **Attach BLE streams to the Radio Manager (software complete; final stream
   HIL pending).** Generation-tagged bounded RX/TX queues, MTU-aware
   fragmentation, finite backpressure, per-stream counters, stale-session
   purging and independent CLI/DEBUG policies are implemented in SRAM4. The
   RAM image advertised successfully after integration; Windows then returned
   a generic connection error, so write/subscribe/fragment HIL must be repeated
   after the board and host adapter are reset. XMODEM and privileged commands
   remain disabled.
10. **Integrate the BLE CLI session (software complete; final phone HIL
    pending).** BLE owns a separate 5,272-byte parser/editor/history/output
    session in SRAM4 after the radio reaches READY. A single priority-9 broker serializes shared command
    backends while polling CDC and BLE independently. BLE RX is drained in
    bounded bursts and replies use the item-9 backpressure/fragmenter path.
    Binary map/dataset traffic, XMODEM and unauthenticated remote reboot remain
    USB-only. Verify CDC and BLE concurrently, then reconnect and exercise a
    deliberately slow notification subscriber.
11. **Implement Wi-Fi control.** Scan, join, DHCP, RSSI/status, disconnect,
    credential handling, reconnect policy, and error recovery.
12. **Implement T01 TCP and optional UDP CLI transports.** Start with one TCP
    client; use finite timeouts, backpressure, and a single-peer UDP lease.
13. **Complete the three-session CLI broker.** Verify CDC, BLE, and Wi-Fi have
    independent parser, privilege, error, and output state while sharing the
    same command definitions and backend services.
14. **Run simultaneous Wi-Fi + BLE coexistence tests.** Measure ToF timing,
    display updates, radio throughput/latency, queue pressure, and recovery
    during concurrent traffic.
15. **Add the NCP firmware-update service.** Use the W6X FWU streaming API only
    with a pinned, verified, unlocked-development-compatible image and retain
    UART recovery.
16. **Add STM32 OTA transports.** Feed received data into the existing signed
    Secure A/B installer and run power-loss/rollback tests over both Wi-Fi and
    BLE.
17. **Perform production hardening.** Add remote authentication, authorization,
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

- CDC, BLE, and Wi-Fi can each hold a partial command without affecting the
  others.
- Replies and asynchronous completions return only to the originating session.
- Disconnect/reconnect invalidates stale buffers and authentication state.
- BLE passes tests with minimum and expanded MTU, split UTF-8, multi-packet
  replies, slow acknowledgements, queue overflow, and mid-reply disconnect.
- TCP passes arbitrary segmentation and abrupt-close tests.
- UDP rejects a second peer during an active lease and handles duplicates per
  command policy.

### 12.4 Wi-Fi/BLE coexistence

- Concurrent BLE CLI and Wi-Fi TCP/UDP traffic work while USB CDC remains usable.
- Throughput reduction on the shared 2.4 GHz radio is characterized and does
  not cause application starvation.
- Wi-Fi reconnect does not destroy an active BLE session unless the module
  itself requires reset; such a reset is reported to every affected session.

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
cli sessions
```

Mutating commands should be asynchronous and privilege-gated:

```text
radio enable|disable
wifi scan
wifi join <profile>
wifi leave
cli wifi mode disabled|tcp|udp
cli ble enable|disable
ncp update <approved-image-id>
```

Do not accept raw filesystem paths, arbitrary AT commands, eFuse operations, or
unreviewed image URLs from a remote CLI in the first implementation.

## 14. Project integration points

- `N6.ioc`: SPI5, GPDMA, GPIO, EXTI9, NVIC, and clock source of truth.
- `AppliNonSecure/Core/Src/app_threadx.c`: project-owned Radio Manager creation
  and pool selection.
- `AppliNonSecure/Core/Src/wifi_ble_app.c`: Radio Manager initialization,
  GATT registration, callback snapshots, connection tuning, and advertising
  recovery. Future payload queues and all W6X sends remain owned here.
- `AppliNonSecure/Core/Src/debug_cli.c`: transport-neutral commands and
  asynchronous service requests.
- `AppliNonSecure/USBX/App/ux_device_cdc_acm.c`: CDC transport adapter only;
  it must not own the shared command implementation.
- X-CUBE `Middlewares/ST/`: W6X driver and FreeRTOS-to-ThreadX compatibility
  layer.
- Secure update client/service: sole route for STM32 executable image install.
- Stage 08 memory/collision checks: must include any reserved radio SRAM region.

The user has confirmed the shield and SPI/AT identity path. The current split
flags enable BLE GATT discovery while leaving Wi-Fi services disabled. Do not
enable Wi-Fi or attach application byte streams merely to bypass the staged
queue, framing, authentication, and coexistence work.

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
