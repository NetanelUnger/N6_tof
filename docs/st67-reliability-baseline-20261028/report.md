# ST67 reliability: checkpoint CP0

2026-10-28, 22:45 Asia/Jerusalem / 20:45 UTC. Owner: Codex.

P0 is **BLOCKED** on missing CN8 application USB CDC. P0-01 and P0-03 are
complete as host/source baseline records. P0-02, P0-04 and P0-05 remain open.
P1-P7 have not started. No reliability firmware fix or hardware acceptance is
claimed. No firmware was built, signed anew, transferred, or installed in this
checkpoint. Generate Code is not required for these documentation-only changes.

## Exact baseline and provenance (P0-01)

- Worktree: `C:/Users/netan/Dropbox/DevelopPersonal/N6/n6-xip-ota-usb`.
- Branch: `feature/n6-xip-ota-usb`.
- Revision: `5432d4ae2b10ef7ecdfaedad586038792f0a4db5` (`FrameTest`).
- Initial `git status --porcelain=v1`: empty. Existing generated and ignored
  artifacts were read and preserved; no checkout/reset/stash was performed.
- Authoritative task plan was found only at
  `N6/project/docs/st67-reliability-improvement-plan.md`. Original SHA-256:
  `ACBA84D41D792A036E25DE63C4F906D09FB59AF799AC3E601A0B6766CB703231`.
  The exact original bytes are retained as `plan-before.md` in the task evidence
  workspace. The plan is updated in place, not replaced by a competing tracker.
- The older `project` checkout's Git status was refused by Git ownership checks.
  No trust exception, ACL/ownership change or retry was made. Its source was not
  chosen as the firmware baseline. Only its explicitly requested plan is edited.
- No `.agents/skills` directory exists in the N6 root, either checkout, or
  checked user/Dropbox ancestors. No missing project skill was invented.
- Host tools used: PowerShell 7.6.5, Git 2.47.1.windows.2, Python 3.14.4,
  MSVC `cl.exe` file version 19.50.35728.0. Python has pyserial 3.5 and numpy
  2.4.4; Bleak/pytest were not found in this interpreter. The actual BLE HIL
  interpreter remains to be selected, without installing anything yet.

`baseline.json` retains exact source, test-tool, ELF/BIN/MAP/package hashes,
artifact sizes, build metadata and source comparison details. It is the machine
readable evidence for this record; hashes were recomputed from local files.

### Configuration distinction

Current tracked defaults enable ST67, BLE GATT, Wi-Fi, Cloud, USB CLI and NPU.
Display and general/CLI diagnostics are disabled; the existing lab Cloud profile
is HTTP. Debug compilation uses `-O3`. Tracked `firmware_build_version.h` is **11**;
tracked resource/watchdog flags are 0 and Cloud auto-map is 1. These defaults do
not describe the final XIP artifact. The existing `Build-Xip.ps1` temporarily
sets the selected version, preserves NCP settings, disables Cloud auto-map and
normally enables resource diagnostics/watchdog, then restores source headers.
Its saved B50 metadata confirms these overrides and settings persistence ON.
No flag, deadline, buffer or security policy was changed here.

Two retained packages were independently verified offline with the existing
`Tools/Test-XipPackage.ps1` (manifest target/size/slot/vectors, SHA-256 and P-256
signature using the tracked public key). Both passed. All artifact hashes in
their build records matched current local files.

| Host artifact | Source recorded at build | Package SHA-256 | Status |
|---|---|---|---|
| A49 `v49-A-product-settings` | `38d384f46eb3144fb673240ca98e7621ddf77cf3` | `753b8cc6c2a4c9c8c393e6d78f0ad2c699787437195e0a3cf519d2486f33e3bc` | VERIFIED_OFFLINE; current board unknown |
| B50 `v50-B-timed-demo-map` | `6948f70475749bf9a7407cd62edc6b69ddeca664` | `2a7aedb4fcd156f8eafa0bd322116452cf8fbd1f1e4aec7989ed7e84b5d9e156` | VERIFIED_OFFLINE; current board unknown |

B50 application ELF SHA-256:
`BDFE25881C791A4BE9CEC81682348C82BFC507D441C2DAB0D1E10B7A20894629`.
B50 raw BIN SHA-256:
`F251B0119F6C94A375E16E360EFA22782962149D9351FF5E3712BE8B0636B318`.
Retained B50 linked heap capacities are 852488 bytes XIP and 395592 bytes RAM,
above the 360 KiB requirement. These are saved linker results, not fresh builds,
runtime free bytes, largest allocatable block or measured stack high-water.

Comparison covered 1044 C/header/linker/project/configuration inputs per saved
build. B50 differs from current source in the three restored headers
`app_features.h`, `w61_driver_config.h`, `firmware_build_version.h`. A49 additionally
differs in `wifi_ble_app.h`, `debug_cli.c`, `wifi_ble_app.c`. Build records cover
their recorded inputs only; for example, B50's historical report says a new demo
header was not yet tracked at build time. Do not promote these comparisons to
complete current-source/binary equivalence or to proof of the installed image.

## Recovery, budgets and resources (P0-03)

This is a source baseline, not a fresh measurement or a declaration that the
existing mechanisms are sufficient. Primary paths are relative to this worktree.

| Area | Current source behavior / capacity | Evidence |
|---|---|---|
| NCP trigger | Genuine `tx_desynchronized`, expired DNS drain or explicit request; ordinary contention/late terminal alone returns without reset | `wifi_ble_app.c:996` recovery pump |
| Recovery states | 0 idle/ready, 1 pending barrier, 2 teardown/reinitialize, 3 failed/closed; success returns 0, failure remains 3 | `wifi_ble_app.c:1070` recovery executor |
| Ownership barrier | Radio retires notify/image work; Cloud acknowledges; actual AT mutex must be available; no forced release | same pump/executor |
| Limits | Owner/mutex wait 35000 ms; at most 3 reset attempts per 60000 ms; SPI quiesce 2000 ms. The 35 s value is not an end-to-end readiness guarantee | same executor |
| Teardown | Fence, stop local SPI/DMA, stop parser, retire BLE/Net/Wi-Fi contexts, prove CHIP_EN off, initialize owners, restore desired services. Failed stop remains closed | same executor; `spi_iface.c` |
| Outcomes | Old BLE generation retired and explicit UNKNOWN notice retained; accepted old Wi-Fi work fails rather than replays | same pump/executor |
| Connection intent | Startup loads saved desired state unless BLE-only profile; successful connect saves settings; disconnect clears desired state, optional forget removes saved network; restore uses existing settings/reference path | `wifi_ble_app.c:749,2832,2844,2890` |
| BLE notification | Immediate AT admission; 100 ms execution; separate bounded 1000 ms terminal drain after full payload; 3 notification attempts; preserve pending fragment and true fence | `wifi_ble_app.c:41`; `w61_at_common.c:1087` |
| BLE repair | Advertising retry base 1000 ms / max 3; BLE recovery cooldown 10000 ms / max 3; state/ACK distinct from RF proof | `wifi_ble_app.c:64` |
| DNS | Application request may return earlier; DNS ownership drains to original 20000 ms from write; expiry fences and a late response cannot clear it | `modem_cmd_handler.c:762,981` |
| General AT defaults | NCP/SYS/BLE 2000 ms; Wi-Fi/Net 6000 ms; connect-command status 3000 ms. These are different scopes, not latency acceptance thresholds | `w61_at_common.h:69`; `w61_at_wifi.c:41` |
| Wi-Fi control | Four request/result slots; 30 s scan completion wait; existing worker only | `wifi_ble_app.c:77` |
| Cloud | 4500 ms HTTP scope, 100 ms receive waits, 512-byte send slices, close retry paced 1000 ms, increasing backoff 2/5/15/30/60 s; no jitter in this array | `cloud_relay.c:38,1223,1236` |
| Cloud fixed storage | 8 x 384-byte output slots; 4 control slots; 2400-byte response, 1200-byte request; 9 KiB context budget | `cloud_relay.c:25` |
| BLE storage | CLI RX 8 x 512, TX 8 x 768; DEBUG RX 2 x 512 disabled by policy, TX 8 x 256; producer wait capped at 50 ms | `wifi_ble_app.c`; AGENTS stream contract |
| Radio / SPI | Radio pool 65536 bytes; SPI RX/TX queues 8 each; maximum transfer 1520; burst 8 packets before yielding; max activation retries 3 | `app_azure_rtos_config.h:69`; `w61_driver_config.h`; `spi_iface.c:48` |
| SPI stack | Base envelope 768 bytes; diagnostic profile changes nominal envelope to 1024 before existing allocation padding. Do not call either a measured worst case | `spi_iface.c:50` |
| Parser | Persistent `rx_assembly[RX_BUF_SIZE+1]` in modem object outside radio pool; retained queued-packet tail ownership | `w61_at_api.h:1172`; engineering contract |
| Images / USB | Exactly one remote image destination and existing 9072-byte wireless snapshot; USB static control 8x768, maps 2x48 KiB, RX 16x512; 5 s TX completion wait and max 3 recoveries per physical activation | AGENTS ToF/ST67/USB contracts |

Full contention attribution, worst-case simultaneous allocations, fragmentation,
runtime high-water, parser lifetime under all faults and recovery end-to-end
timing remain P1-P5/P7 work. No new counters or recovery behavior were added.

## Host checks completed

Runs were 20:39:10.784..20:39:39.720 UTC. Each command used
`C:\Python314\python.exe -B -u <worktree>\hil_tests\<test>.py`.
Temporary compilation/execution remained on the host. Hardware and ThreadX
boundaries are mocked. Python bytecode writes were disabled.

| Test | Exit | Printed PASS checks | Evidence |
|---|---:|---:|---|
| `test_wifi_scan_lifetime.py` | 0 | 7 | corresponding `.py.log` |
| `test_dns_reply_lifetime.py` | 0 | 6 | corresponding `.py.log` |
| `test_radio_wait_diagnostics.py` | 0 | 11 | corresponding `.py.log` |
| `test_spi_cs_hold.py` | 0 | 5 | corresponding `.py.log` |

29 checks total comprise 26 native actual-C cases and 3 source audits. Compiler
warnings in the existing mock fixtures were retained (pointer/integer-width
and CRT-deprecation warnings); there were no compilation/execution failures.
These checks do not complete V08-V10 or the candidate P7 regression campaign.
Offline A49/B50 package checks also passed; they did not create or install packages.

## USB blocker, exact state and continuation

At 20:42:34 UTC, Windows CIM and present-only PnP enumeration found only
ST-LINK VID_0483/PID_3754, diagnostic COM6. No application CDC VID_0483/PID_5740
or second COM port was present. `usb-presence.json` retains exact identities.
The first sandbox CIM read returned Access denied; the formally escalated,
read-only query succeeded. That access issue is resolved. Git's separate older
checkout ownership refusal was not overridden.

**BLOCKED, pending physical connection verification:** P0-02 live application
`version`/`radio info`, P0-04 baseline HIL, P0-05 workload/numeric acceptance
freeze, and consequently dependent implementation/installation. Neither current
MCU boot mode nor running application/NCP state is established. A missing CDC
endpoint alone does not prove a disconnected cable or firmware fault.

Ask the user to check the **PC-to-CN8 USB data connection** and connect that cable
if absent, leaving ST-LINK connected. No power cycling, RESET, jumper or solder
bridge change is requested. If CN8 is already connected, report that fact and
diagnose its enumeration without assuming a reset is safe.

No serial, BLE, debugger or programmer handle was opened; no hardware lease was
acquired; no device command or reset was sent. Credentials, saved settings,
pairing, security policy, bootloader, Secure firmware and NCP firmware are
unchanged by this checkpoint. No network export, push or deployment occurred.
The plan's general RAM-HIL recommendation yields to the current user's USB-only
requirement. Existing signed inactive-slot USB installation is in scope after
verification; SWD/RAM loading, NCP UART preparation and boot-chain replacement
are not fallback paths. No version is selected now: tracked 11 must not be used
to infer next 12, nor historical B50 to infer current 50 or automatically choose 51.

After CN8 is visible: establish exclusive ownership using the existing lease
mechanism; read application/NCP identity and status without settings changes;
identify confirmed slot and any pending/consumed version; capture baseline
profiles and freeze section 7; then proceed to P1. Restore runtime settings and
release handles after every bounded profile. Native passes cannot waive HIL.

## Conclusions after P0-01 / P0-03 and host checks

1. The current branch already contains transaction ownership, bounded late DNS
   drain, coordinated recovery and retained-data mechanisms. Replacing them or
   adding another radio manager would be premature before measured attribution.
2. The focused native baseline is healthy. It says nothing yet about BLE
   latency under Cloud load, RX memory pressure or multi-hour stability.
3. Current source defaults, saved XIP build configuration and live board state
   must stay distinct. Offline verified A49/B50 are retained host recovery
   references, not proof of either on-board slot now.
4. No acceptance limit was relaxed or guessed from old reports. P0 remains
   blocked; section 7 TBD entries remain deliberately unfrozen until the live
   workload and restored-service timing can be established.
