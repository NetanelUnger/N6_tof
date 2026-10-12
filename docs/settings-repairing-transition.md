# Approved RAM settings transition and user re-pairing (2026-10-11)

Prepared on local `ble` / `d89a5108a458e2adafcb1fc30c1976bbe5e3abb5`, preserving
the preceding uncommitted recovery/settings work. The boot-write blocker is now
resolved for the explicit preservation mode: query the existing public settings,
require the configured values and skip persistent-capable setters. Mismatch fails
closed. Board availability was already approved; two supported SRAM startups of
the exact rebuilt candidate pass. The user has now paired locally, and the
verified record passed independent guarded startup and connected recovery below.
Live RAM is the exact read-only reader05FD9EFD... with writes0/preserve1,
Wi-Fi IP ready, ToF/USB/radio ready and paired Cloud streaming.

The user opened his existing workspace file and performed pairing himself. The
agent executed only `cloud prepare yes`, never `cloud pair`, and has not initiated
a pairing exchange, opened a workspace credential file, created a real
settings file, exported a password or transmitted credentials. Original
`n6cloud.cfg` and retained NCP Wi-Fi credentials were not mutated by this work.
Legacy integrity remains UNKNOWN. No firmware NOR/header/sign/package,
commit/push/deployment or HTTP/TLS change occurred. Flash/header remains9.

## User pairing, managed startup and connected recovery (2026-10-12)

The user submitted the pairing command himself. A queued/completed local CLI
response was not treated as success. First read-only inspection proved the live
candidate's four immutable SRAM sections match exactA8077FB8..., Wi-Fi IP/radio/
ToF ready and paired Cloud uploading frames. Named metadata: storeOK0, loaded1,
arm0/writes0, selected slot0, generation1, flags31, encoded length705 and
CRC72B6B9AF. Password length0 confirms retained-reference storage; no password,
token, record payload, workspace file or pairing-code value was read by the host.

The historical `unified save result=0 verified=1` UART line was not available to
the new observer. Exact production code admits paired state only after HTTP200,
valid response parsing and verified AppSettings commit; current committed state
and consumed arm independently agree. This is a state/code inference, not a
claim that the original UART line or HTTP response body was captured. Subsequent
fresh managed startup below provides independent filesystem/schema/CRC evidence.

Before testing, the board already had NCP attempts3/ready3/fail0 and request
errors3. A captured earlier SPI fault was count1/tick35213518/source1/phase1/
length520/HAL_error00000004/SR01E94047 with zero DMA errors; its natural cause is
unproven. Cloud dropped frames moved from1 at initial inspection to2 before the
fault-test baseline. These observations are retained, not attributed to the new
test or erased by the later MCU startup.

One authorized `radio fault-test` on the candidate produced START
TEST_MISSING_RESPONSE and status3/genuine_fence1, then coordinated recovery
PASS22152ms. Saved-reference Wi-Fi returned2766ms, counters3/3/0->4/4/0,
ToF355039->355306, Cloud accepted-frame count1136->1145 (HTTP202),14 USB pings
max328ms. CLOUD route, DEPTH channel, Off filter and running acquisition were
preserved. Request errors3/dropped2/SPI1 and allocation failures0 stayed at
baseline. The first checker expected the wrong literal `fault-test`; its failed
report remains. Corrected offline checks on already captured genuine_fence1
evidence pass (`cloud-recovery-reviewed.json`), without rerunning the fault.

After verified pairing/persistence, the supported
`Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` performed one controlled fresh SRAM
startup of exact read-only/config-preserve1 reader
05FD9EFDAA0C825C81F30751C8DE3A1245F074007B96110EFE77E21BE25F7E12.
Guarded CWAUTOCONN0/CWMODE1/CWDHCP1 readbacks match; UART reports settings
load result0/writes0 and automatic saved-reference Wi-Fi restore3431ms. The
ordinary loader touches no firmware NOR, version header, signing or package.
Normal generated Debug ELF/bin/map were restored afterwards to exact57FB502F...
and differ from the live guarded reader. Use the reader's isolated symbols for
live metadata; never substitute normal unguarded-init output for this mode.

Fresh reader metadata proves full StoreLoad succeeded in4 commands with the same
slot0/gen1/flags31/705/CRC72B6B9AF. Managed Wi-Fi owner now reports unified_wifi1,
saved reference1 and desired connection1. Cloud pairing and CLOUD image route
return automatically through the existing paired/enabled publication; no user
MAP ON, re-pairing or agent credential exchange was required. The transition arm
is compiled out and writes are0. This is actual managed startup, not a host media
model. After the earlier NCP power-off/reinit and MCU RAM startup it also proves
the record survived those controlled operations; it is not physical power-loss
durability evidence.

A second fault-test is a distinct managed-startup case: reference restoration
comes from the loaded record, rather than the candidate's prior volatile intent.
Reader status3/genuine_fence1 recovers in19841ms, counters0/0/0->1/1/0,
ToF2088->2316, accepted Cloud frames603->608,12 USB pings max328ms. CLOUD/DEPTH/
Off/running desired state is preserved and request errors/drops/SPI/allocations
remain0. Final named metadata still matches gen1/705/CRC72B6B9AF, writes0,
fence/drain/recovery0, paired Cloud and Wi-Fi IP. No file/credential mutation or
implicit re-arm/retry happened in these tests.

Reader heap capacity374496, sbrk arena357412, uncommitted tail17084, linker
margin5856. This is not malloc-free/fragmentation or worst-stack evidence.
COM6/COM8/UART collector/debugger handles are released. No active test/build
remains. A transient host report-write failure and a reader symbol removed by
-O3 (`settings_present`, a write-only cache) are retained; read-only inspection
was corrected without another RAM startup, fault injection or pairing. Firmware
code was unchanged, so prior44 native/91 feature/build passes were not rerun.
Final health capture: ToF6840->6848, requested/active CLOUD, UART519/519 with
zero drops/HAL errors and a successful local ping. Final metadata still has
storeOK/gen1/flags31/705/CRC72B6B9AF, writes0/fence0/drain0, saved-reference
Wi-Fi IP and paired Cloud with accepted uploads advancing. Current exact outcome
is recorded in settings-user-pair-check-20261012/`terminal-summary.json`.

Ignored evidence: settings-user-pair-check-20261012/`inspection.json`,
`cloud-recovery-once.json` (initial checker failure), `cloud-recovery-reviewed.json`,
`guarded-reader-load.json`, `managed-readback-proof.json`,
`reader-cloud-recovery-once.json` and terminal summary. Reader startup/final
metadata are in sibling reader-managed-startup-20261012 and reader-final-state-
20261012 directories. Historical pairing payloads remain inside the firmware;
no raw credential/log/workspace data was exported.

This closes the focused real pairing/readback/managed startup/connected recovery
checkpoint. HTTP202/counts prove accepted uploads; independently received CRCs
and rendered browser frames were not captured by this observer. Active BLE
CLI/DMA in-flight failure HIL, natural SPI causality, physical power-loss tests,
fulltask4 endurance and whole-chip CPU/stack/fragmentation acceptance remain open.
Legacy `n6cloud.cfg` integrity stays UNKNOWN; it and CWCRED were not altered.
No firmware Flash/header/sign/package/HTTP/TLS/commit/push/deployment change.
Do not prepare or pair again. Earlier unarmed/unpaired checkpoints are historical.

## Local preparation terminal and user handoff (2026-10-11)

The already-authorized preparation was executed once on CN8 COM8 without reset,
load or memory writes. A HOTPLUG read-only upload of the candidate's SRAM
`.isr_vector`, `.text`, `.rodata` and `.ARM` sections matches every immutable byte
of the exactA8077FB8... ELF. No Flash region, settings payload, password/token
array or generic heap contents were read. Public metadata verifies the saved
reference and matching desired/confirmed SSID, Wi-Fi IP, idle unpaired Cloud,
empty control/work queues and no recovery/fence/DNS drain/notification owner.

The command's existing Cloud owner performs fresh complete FS inventory before
arming. No managed file exists; legacy is present. Exact captured UART terminal:

```text
[0001636348][SETTINGS-TRANSITION] prepare result=0 RAM_only=1 legacy_preserved=1
```

Independent named-metadata readback after completion: resultABSENT1, loaded1,
arm1/writes1, busy0/io0/present0, calls1, transition epoch1/cancel epoch1. RAM seed
flags19 (Wi-Fi present+desired+reference), generation0, password length0 and token
length0. This is an explicit one-shot future pairing-save permission, not a
persistent write or a completed pairing. The only NCP operation on this path is
the read-only inventory; create/write/delete and authenticated exchange were
not invoked. Final public status: Wi-Fi IP/ToF/radio ready, BLE disconnected,
Cloud unpaired. COM6/COM8 closed, UART collector stopped, no active test/debugger.

The first host check incorrectly assumed production READY=3 instead of2 and
stopped before submission. It was corrected against `wifi_ble_app.h`; the failed
report remains `prepare-only-initial-harness-failure.json`. Exact immutable SRAM
proof was retained across the same no-reset session, and no second code upload
or second preparation occurred. Firmware/source/builds were unchanged, so the
prior44 native/91 feature/build results were not rerun.

Evidence: ignored settings-bootguard-20261011/`prepare-only-summary.json`,
public scalar logs and immutable section readback files. The earlier unarmed
readiness reports below are historical. No firmware NOR/header/sign/package,
HTTP/TLS, provisioning, commit/push/deployment or credential exchange occurred.
User pairing, actual first commit/readback/managed startup, connected Cloud
recovery and physical durability remain NOT RUN. Do not repeat preparation or
reset the board before the user's local handoff.

## Resolved boot guard and exact RAM readiness (2026-10-11)

`W61_CONFIG_PRESERVE` defaults0 and is enabled only in the isolated transition
candidate and its subsequent read-only validation reader. The ordinary build
retains vendor configuration behavior; its settings writes still defaultOFF.
Guarded Wi-Fi startup queries CWAUTOCONN=0 and CWMODE=1, and requires the existing
antenna setting. Network startup and desired-state restoration query CWDHCP=1;
startup also reads and requires the configured AP IP/mask instead of sending
CIPAP. Clock initialization retains the existing query/same-value skip, but a
different clock now fails before SET_CLOCK/restart in preservation mode.

Guarded Wi-Fi deinit skips CWMODE=0. This does not disable coordinated recovery:
the existing owner still quiesces Cloud/Wi-Fi/BLE/SPI, retires the old parser and
resources, powers the NCP off and performs fresh initialization. Both actual RAM
recoveries pass. The common SET wrapper rejects the audited persistent-capable
configuration/credential/Flash command families before transmission in this
mode. Managed FS commit remains owned by the existing explicit one-shot gate.
Country/hostname and required volatile network/BLE commands remain unchanged;
SYSSTORE is neither changed nor assumed disabled. Readback matches, rather than
an assumption about same-value setters, permit startup.

The new scalar readback accepts only the three public queries, strictly checks
one decimal value, rejects malformed/duplicate/missing responses and uses the
original2000ms lock-plus-command budget. Immutable response handlers outlive
timeouts; the typed stack destination is retired under the critical section
before releasing the TX lock. No retry or late terminal clears a true fence.
There is no new task, capacity increase or steady-state allocation. Modified
vendor boundaries are `Core/w6x_wifi.c`, `Core/w6x_net.c` and
`Driver/W61_at/w61_at_common.{c,h}`/`w61_at_sys.c`; app DHCP restoration shares
the same check. No CubeMX regeneration is needed.

Ignored evidence: `.local-dependencies/diagnostics/settings-bootguard-20261011/`.

| Exact unsigned image | SHA-256 | Binary / C heap capacity |
|---|---|---|
| `candidate.elf` (earlier RAM candidate, now unloaded; compile writes1/transition1/preserve1) | `A8077FB8B314B09C305D4EA0227343F6B8EE9B5519DBF2FF346241D9030AA8E9` |495612 /370872 bytes;2232 above368640 guard |
| `reader.elf` (current live RAM; writes0/transition0/preserve1) | `05FD9EFDAA0C825C81F30751C8DE3A1245F074007B96110EFE77E21BE25F7E12` |491996 /374496 bytes;5856 above guard |
| Restored normal Debug ELF (not RAM-loaded; all three macros0) | `57FB502FE87E411501195B7C82DF1B2BAA81D02BCC80143D0A9D0CC3762D9C80` |491772 /374720 bytes |

The normal generated Debug ELF/bin/map were rebuilt from normal objects after
the RAM tests. They differ from the live candidate. Use the isolated candidate
symbols for live metadata; future no-persistent-config readback/restart must
explicitly stage the guarded reader, not use normal Debug output by accident.
Neither the normal nor guarded reader image was loaded in this follow-up.

All44 actual-C native files pass, including two new preservation/boot suites.
The boot suite was repeated with actual clock-source code and passes both modes.
All91 feature syntax checks pass (13 units across seven modes, including guarded
reader/candidate and disabled radio/Wi-Fi/BLE/Cloud combinations). The supported
Non-Secure incremental build, isolated reader/candidate links and final normal
relink pass. Secure and FSBL build-only checks are up-to-date/pass; no signing
ran. Linked candidate disassembly confirms the guarded initialization paths
omit the audited setters. Individual compiler frames: scalar helper80,
callback24, network init96, Wi-Fi init48 bytes; not a worst-stack proof.

Two `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` loads pass. These are controlled
fresh SRAM startups, not physical power-loss tests. UART confirms old/required
public values CWAUTOCONN0/CWMODE1/CWDHCP1 on startup and fresh NCP recovery.
Strict malformed legacy reads still trigger genuine AT_FENCED recovery;
attempts1/ready1/fail0, elapsed16262ms then15913ms. The malformed read channel
does not prove stored corruption. Both named-metadata captures prove unarmed0,
writes0, legacy-only, idle settings/no I/O/no managed state. Only the saved
public SSID/reference/connection-intent RAM fields were restored, with scalar
readback; existing Secured=1/CWJAPS reconnects without password export/write.

Both heap samples show370872-byte capacity,357412-byte reserved sbrk arena and
13460-byte uncommitted tail. This is not live malloc free/fragmentation evidence.
First readiness ToF1198->1238 and second2274->2313 pass, with Wi-Fi IP, USB/radio
ready, BLE advertising/disconnected, imageNONE and Cloud unpaired. Thirty final
USB pings pass, maximum host-observed329ms (not full latency acceptance).
Stable second snapshot UART253/253, zero UART drops/errors, SPI faults and radio
allocation failures. The boot logs retain early Wi-Fi result-queue notices;
startup is not claimed free of every diagnostic. Owned COM6/COM8/debugger handles
are released; no test/build remains active at handoff.
The final capture after the USB checks shows ToF3050->3092, UART296/296 with
zero drops/errors and the same healthy unpaired state (`board-final.json`).
`terminal-summary.json` records the live/generated image distinction and all
remaining acceptance limits.

Initial compiler-temp hang, harness quoting/type errors, feature-command lookup
failure and disassembly-checker false match are retained with corrected passing
results. A denied edit to `w6x_sys.c` was avoided by guarding the clock setter in
the existing writable AT driver; no remaining permission blocker or change to
that core file. No firmware change followed the passing builds/RAM tests.

Real preparation/first pairing commit/managed readback/startup/connected Cloud
recovery are NOT RUN until the user's steps below. Physical power-loss durability,
in-flight BLE/CLI/DMA failure HIL and fulltask4 endurance remain open. The narrow
2232-byte linker margin requires continued memory review; current readiness is
not a whole-chip CPU, worst-stack or Flash-installation acceptance.

## Historical readiness audit: stop before RAM loading (2026-10-11)

The following checkpoint records the earlier stopped audit. Its pending/load
statements were superseded by the guarded-image readiness result above.

The user explicitly approved continued board tests, RAM loading and controlled
restart, but required a stop before any unexpected persistent boot writes.
The unchanged vendor `W6X_WiFi_Init` calls `W61_WiFi_SetAutoConnect`
unconditionally at `ThirdParty/ST67W6X_Network_Driver/Core/w6x_wifi.c:264`.
The project defines `W6X_WIFI_AUTOCONNECT=0`; the driver formats and sends
`AT+CWAUTOCONN=0` (`Driver/W61_at/w61_at_wifi.c:157`). The official
[ST NCP 2.0.106 command reference](https://applist67.github.io/Web_AT_Documentation_ST67/v2.0.106/index.html#at-cwautoconn)
documents this command as saving configuration in EasyFlash. No production
`SYSSTORE=0` setter was found in the host application or driver; the reference
also describes SYSSTORE's default as1 and DHCP settings as conditional on it.
Country-code configuration is separately documented as nonpersistent.

This proves an existing persistent-capable command is on the boot path, not
that a new physical write occurred in this follow-up or that an unchanged
stored value necessarily causes one. The exact candidate's AppSettings runtime
write gate remains unarmed/read-only before explicit preparation. That narrower
guard does not establish that all NCP initialization is nonpersistent.

No RAM loader, reset, pairing exchange, `cloud prepare`, credential operation,
filesystem mutation or raw NCP query was performed in this follow-up. No source
or generated executable was changed. The prepared candidate and updated reader
hashes still match the table below; the existing7EE45958... RAM stays live.
Read-only USB captures before and after the audit show ToF advancing, Wi-Fi IP,
radio/USB ready, BLE advertising/disconnected, image NONE and Cloud unpaired.
USB ownership is closed by the collector's `finally`; no debugger/UART handle
was opened. Evidence: ignored
`.local-dependencies/diagnostics/settings-ready-20261011/board-before.json`,
`board-final.json`, `boot-persistence-audit.json`, and `terminal-summary.json`.

Candidate RAM readiness, runtime heap measurement and controlled candidate
restart are NOT RUN. Prior42 native/five final affected suites,60 feature checks
and builds remain retained evidence; no code changed to justify a rerun. Before
continuing, resolve the no-persistent-boot contract across initialization and
recovery, including autoconnect and SYSSTORE-dependent setters, with applicable
host regressions and a rebuilt exact image. Do not request or enter a pairing
code until that image passes readiness. Prior claims about preserving the
legacy file and credential reference describe the settings transition; they
must not be read as a proof that the entire vendor boot path never persists
generic NCP configuration. Earlier RAM loads did not measure that behavior.

## Scope and ownership

The normal build keeps `APP_SETTINGS_WRITES_ENABLED=0` and
`APP_SETTINGS_TRANSITION_ENABLED=0`. The separate unsigned candidate compiles
both as1, but runtime writes remain0 until explicit `cloud prepare yes`.
Only USB can enqueue this preparation. The existing four-slot Cloud control
queue and Cloud worker execute it outside the reply gate. Preparation requires
unpaired/idle Cloud, no pending pair/HTTP/input/output/reply, and an idle confirmed
Wi-Fi connection whose retained NCP credential reference and desired SSID are
already valid. The public snapshot copies only SSID/intent, never a password.
Fresh full inventory must prove legacy present and both managed names absent.
Preparation seeds RAM only, with no FS create/write/delete or authentication.
It cannot overwrite a previously present managed file or silently re-arm.
The worker rechecks pairing admission when dequeuing, so a queued stale request
cannot replace a completed pair or start another exchange after the arm is used.
Accepted user Wi-Fi connect/disconnect requests atomically cancel the candidate
seed; a changed network intent cannot be persisted from an earlier preparation.

The reserved flag `APP_SETTINGS_WIFI_REFERENCE=16` explicitly distinguishes a
saved NCP reference from an open network with an empty password. Reference
records require Wi-Fi presence and an empty password field. Normal v1 records
with flags0..15 are unchanged; the schema and2561-byte capacity are unchanged.
The prior exact reader rejects the new flag as UNSUPPORTED. Updated readers use
the existing Secured=1/CWJAPS path for a reference, preserving the existing NCP
credential values. No CWCREDADD/delete, password export or enterprise username
was added. This preserves Wi-Fi through a reference; it does not copy an unknown
password into the managed record.

The user's successful pairing response supplies new device/workspace/token
fields through the existing firmware path. The first save combines them with
the retained Wi-Fi reference/intent. Inside the original immutable13250ms
operation, inventory is rechecked before create; the retired inventory union is
then re-encoded. The maximum reference record is2435 bytes and13 commands
(list/create/five writes/size/five reads), within the existing15-command limit.
Each SDK operation remains<=2000ms. Exact full readback, CRC/schema and final
cancellation proof precede RAM publication. No true fence is cleared.

Wi-Fi saves/disconnect persistence/forget and Cloud clear cannot consume the RAM
seed. Cancellation or unknown outcome blocks further writes. The arm is consumed
after the first commit attempt; successful completion locks every mutation, and
a fresh load never re-arms it. The general read-only image is used for subsequent
reset/recovery validation. Cloud is marked paired only after verified persistence;
failure clears the new volatile pairing, prevents authenticated continuation and
requires explicit readback/arbitration. Pair-code history is suppressed, and
parsed working arrays plus the response/code are scrubbed. HTTP/TLS request
format, endpoint, deadlines and protocol are unchanged.

## Historical prepared images and host evidence

These earlier images are retained evidence; use the rebuilt guarded images above
for the current preparation and subsequent validation.

Ignored directory: `.local-dependencies/diagnostics/settings-transition-20261011/`.

| Image | SHA-256 | Binary / C heap capacity |
|---|---|---|
| `candidate-awaiting-user.elf` | `2A076C3A475EC3745853D86C3DD5825C3B1E3754D7D0F765E0A019B23CE75EB5` |495324 /371160 bytes;2520 above368640 guard |
| `default-final.elf` (read-only reader) | `43A897C217EA36CEE28A5FED3606D8D78F14A7B575CA88A69E06EC0376B3EFBF` |491772 /374720 bytes;6080 above guard |
| `default-before.elf` (prior clean RAM) | `7EE459582765C6174B36EC698B9FE7948D84B1DD106C42D89B4D446946F5BE9D` |491108 /375360 bytes |

All42 actual-C native files pass; five affected suites were repeated after the
one-shot policy change and pass. All60 feature syntax checks pass, including
the transition candidate and disabled modes. Default guarded incremental build
and the isolated candidate link pass. Candidate object overrides are separate;
the generated Debug ELF remains the default read-only image. Individual compiler
frames: preparation56, admission16 and finish-request72 bytes; these are not a
worst-stack/fragmentation/runtime-heap proof. The candidate has only2520 bytes
above the existing linker guard, so RAM runtime readiness must be measured before
asking the user to pair. The existing RWX warning remains.

New native checks cover all four compile-policy combinations, legacy-only
preparation, intervening-file rejection, cancellation/true fences, partial first
save/no implicit retry, all13 retired-command interruption boundaries, exact
prior-reader flag rejection, ten stale Wi-Fi snapshot states, Cloud owner
admission and failed pairing persistence. Host media/reset models do not prove
physical NCP Flash durability. Initial host environment failures (missing serial
module/default temporary path/compiler response file) were corrected using the
existing training venv and writable local temporary directory. Two test
expectation errors (pre-pair flags19 and2435-byte/13-command count) were corrected;
failed logs are retained. The first build was interrupted after a default-temp
hang; the final supported build with writable temp passes.

## Historical user steps - pairing is now completed and verified

The following steps record the completed user handoff. Do not repeat them.
Current board: guarded read-only reader, Wi-Fi IP, paired Cloud streaming and
ToF ready. Keep the existing Cloud workspace tab open; no new code is needed.

1. ההכנה כבר הושלמה. השאר את הלוח מופעל ואל תשלח שוב `cloud prepare yes` או
   תבצע Reset. פתח [CLI via Web](https://natilab-n6-h6bjh2ffbadtfyaw.israelcentral-01.azurewebsites.net/cloud),
   לחץ **פתיחת קובץ קיים**, בחר בעצמך את קובץ ה־`.n6workspace.json` הקיים
   והמתן ל־**RELAY CONNECTED**. אין כניסה לחשבון; הקובץ מספק את ההרשאה.
2. לחץ בעצמך **＋ — הוספת מכשיר**. בכרטיס PAIRING CODE תוצג פקודת צימוד.
   אל תשלח את הקוד, קובץ ההרשאה, סיסמה או token בצ'אט.
3. שלח בעצמך את פקודת `cloud pair ...` המוצגת, במסוף USB של CN8
   ‏(COM8 בבדיקה). המתן ב־UART ‏(COM6, ‏115200) ל־
   `CLOUD-CONFIG ... unified save result=0 verified=1`, ובדוק `cloud status`:
   נדרש paired. הודעת queued לבדה אינה אישור. אם השמירה נכשלת, עצור ללא
   ניסיון צימוד נוסף ודווח רק את השגיאה הציבורית.
4. השאר את כרטיסיית הענן והלוח פתוחים ומופעלים. אם קובץ ה־workspace מסומן
   בכוכבית, לחץ **שמירת הקובץ** בעצמך. השב רק **הצימוד הושלם**; בדיקות
   readback, אתחול עם הקורא המוגן והתאוששות Cloud יבוצעו בהמשך.

חלופת GUI לפקודת הלוח: פתח **BLE Terminal בכרטיסייה נוספת** בדפדפן התומך
Web Bluetooth, התחבר בעצמך ושלח שם את פקודת הצימוד. השאר את כרטיסיית הענן
פתוחה: ניווט ממנה סוגר את חיבור ה־workspace. באתר אין מסוף Web USB פעיל.

The navigation/button labels are verified against the companion source and the
anonymously fetched public static bundle; no credential workspace file was read
and no pairing-code/authentication operation was performed by the agent.
Connected Cloud recovery, real first managed commit/readback/startup and physical
durability remain NOT RUN. The RAM-only preparation cannot survive an MCU reset;
do not reset or repeat preparation during the user handoff. Full task4 is outside
this checkpoint. See `pairing-route-inspection.json` and
`prepare-only-summary.json` in the ignored evidence directory.

## Rollback and stop rules

Before pairing, supported reload of the exact guarded read-only reader05FD9EFD...
discards the uncommitted seed; the captured public retained-reference intent can
be restored without any password write. The earlier7EE45958... clean image and
normal Debug output retain vendor boot setters, so they are not substitutes for
this guarded reload under the present no-unexpected-persistence instruction.
After a commit/unknown outcome, retain every new file
and load the read-only reader to arbitrate complete bytes/CRC/generation before
any action. A damaged first slot does not fall back to an inferred old token.
No old file is deleted or altered by this path, and the candidate performs no
automatic cleanup. Original `n6cloud.cfg` integrity remains UNKNOWN, so retaining
it does not prove old Cloud authentication can be restored. Re-pairing can change
server state; a firmware reload cannot undo that state. Never promise otherwise.
The prior reader fails closed on the reference flag; rollback to it requires
restoring public Wi-Fi RAM intent and leaves Cloud unpaired as at the baseline.
These rollback properties are host-tested; actual RAM rollback after real
pairing has NOT RUN. No raw Flash read/write, old-file deletion, firmware NOR,
header/sign/package, commit/push, deployment or HTTP/TLS change was performed.
