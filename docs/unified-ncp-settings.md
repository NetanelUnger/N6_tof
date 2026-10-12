# Unified application settings in NCP storage — 2026-10-11

Latest approved preparation: [RAM transition and user re-pairing workflow](settings-repairing-transition.md).
The explicit approval now permits preparing a first new pairing record while
preserving the old file and Wi-Fi reference. The one-shot candidate has only
host/build evidence; it has NOT been loaded or paired, and no actual new file
was written. This adds explicit reference flag16; the original0..15 record
semantics and capacities remain. Ordinary default writes/transition stayOFF.
Earlier no-migration checkpoints below describe their own completed scope.

Implemented on local `ble` at `d89a5108a458e2adafcb1fc30c1976bbe5e3abb5`,
preserving the preceding dirty recovery/ToF work. The implementation initially
passed host/build checks. The separately authorized synthetic NCP ASCII/HEX
follow-up retained three2000ms budget failures. The later bounded product path
now has actual save/verify/commit/reload and cancellation RAM evidence below.
Real settings writes remain disabled. No real credential/token change, migration,
provisioning, Flash installation, header change, signing, packaging, commit,
push or deployment occurred. HTTP/TLS behavior is unchanged.

## Authentication and record

The actual application supports SSID/password for personal or open Wi-Fi.
There is no separate enterprise username. The new `AppSettings_Record` contains
SSID33/password64, device ID65/workspace ID65/token1025, schema, serialized
length, generation, explicit field lengths, presence/desired/enabled flags and
CRC32. Capacities include the C terminator. Password maximum63 follows the SDK;
token maximum1024 is the existing firmware bound, not a fixed server token size.
The local server issues a variable-length protected payload; no token was fetched.

The disk representation is canonical printable ASCII, without stored NUL:

```
N6S1|generation(8 HEX)|total(4 HEX)|flags(8 HEX)|
length(4 HEX):payload(2 HEX per byte)| ... five ordered fields ... |CRC(8 HEX)!
```

The schematic line break above is absent on disk. Fields are SSID, password,
device ID, workspace ID and token. The record is 67–2561 bytes. CRC uses
IEEE CRC32 and covers every preceding byte, including metadata and separators.
The decoder requires exact total size, uppercase HEX, field bounds, terminators,
consistent presence flags and complete consumption. Embedded NUL in a C string
is invalid. AT quote/backslash/CR/LF bytes in Wi-Fi fields and control bytes in
Cloud fields are rejected before persistence; authentication syntax is unchanged.
HEX is transport encoding, not encryption, and CRC is an integrity check,
not authentication. Diagnostic output contains results/lengths/generations only.

## Commit and recovery boundary

Two managed files, `n6settings0.cfg` and `n6settings1.cfg`, carry alternating
generations. Only the inactive file may be deleted/recreated/written. The old
active file stays untouched until the replacement has exact full readback and
validation. RAM publication occurs only after verification and a final cancellation/deadline
confirmation. Reads/writes now use512-byte slices. A complete load or commit
has one immutable13250ms deadline and at most15 SDK commands; each command
receives min(2000ms, original remaining time). Waiting for existing BLE or a
foreign Cloud scope consumes that same total deadline. Scope retirement and a
one-tick yield occur only after the SDK has returned and retired its borrowed
pointer and AT mutex. No command can reset the whole-operation clock.

The original2000ms whole-operation implementation failed the three retained
hardware probes below. Giving every command2000ms independently established
channel correctness but allowed the total duration to grow unchecked. The new
bound is explicit: load list+2 size+12 read commands; worst replacement delete+
create+6 write+size+6 read commands. Fifteen times750ms plus2000ms scheduling
reserve gives13250ms. The750ms planning allowance exceeds the measured530ms
512-byte read by about40%; this is a finite engineering bound, not a guarantee
against arbitrary NCP latency. A slow sequence can still exhaust it and fail
closed even while individual commands fit within2000ms. No inferred padding
or inferred NUL is permitted.

Loading selects the newest valid generation using serial arithmetic, including
wrap. Conflicting equal generations and half-range ambiguity fail closed.
One damaged slot may fall back to the other valid slot. Future schema/flags,
inventory/read failures and two damaged slots block writes. A lost write or
readback terminal leaves the result unknown and blocks another write until a
complete reload. Old slots contain earlier settings until a later replacement;
forget/unpair are logical removal in the selected record, not secure erasure.
Fallback after damage can therefore return earlier configuration values.

The original `n6cloud.cfg` and NCP CWCRED records are untouched. When inventory
proves legacy-only storage, Cloud may use its original strict binary/whole-record
CRC reader. No migration, zero reconstruction or partial Wi-Fi-only seed is
performed. A validated new tombstone is authoritative; it cannot fall back to
the legacy token. Legacy-only storage blocks new writes, even in a write-enabled
build, until an explicitly approved complete migration is designed and validated.
The previously missing public binary byte remains an unresolved legacy-read
blocker; this format does not recover absent saved pairing bytes.

The static NCP adapter has one nonblocking ThreadX mutex, two record arrays,
one typed union shared by the encoded buffer and the earlier bounded inventory.
The inventory is retired/scrubbed before encoded data occupies that union.
This removes1028 static bytes without moving them to an owner stack. There is no new task, queue,
payload capacity or steady allocation. Initial Radio ownership loads the cache;
the existing Wi-Fi control owner and Cloud owner merge their respective fields.
No FS call holds the Cloud reply gate. An unpair request records its verified
tombstone phase in its existing by-value request while waiting for that gate,
so a temporary gate conflict cannot repeat the write or retire a live lease early.
Busy settings loads do not consume a Wi-Fi association attempt or leave its
active-call flag set. SDK scopes and recovery quiescence/fences remain in force. Settings cancellation
increments an epoch without waiting for the settings mutex. The coordinated
recovery barrier and an admitted explicit disconnect cancel the old epoch.
A rejected disconnect request cannot cancel an unrelated transaction.
Fresh BLE notifications defer only while a settings SDK call owns admission;
an already owned notification can finish. The existing control worker defers
new control jobs while another owner holds settings. Cloud defers its ordinary
network/control loop while settings is busy, while its recovery pause/ack branch
remains runnable. Cloud claims its unchanged request/receive/close scope under
the same short admission critical section, avoiding SDK budget-owner overwrite.
The existing Cloud absolute deadline is not extended by deferral.

Wi-Fi saves after successful explicit association, clears its password working
copy, and restores a validated new record with the existing CWJAP personal/open
authentication. A retained legacy NCP credential reference can still use CWJAPS
without fetching its password. New application CWCREDADD/CWCREDDEL and implicit
`Disconnect(forget)` writes are removed. Explicit disconnect always cancels RAM
intent and runs the RF disconnect; persistence failure is separately reported.
Cloud loads the unified record first, reports save failures, and scrubs parsed
token working arrays on all exits. Pairing admission is rejected before a new
server exchange when writes are disabled or storage is unvalidated.

`W61_FS_ListFiles` now requires the documented `+FS:LIST` header and a complete
terminal, rejects duplicate/missing headers and truncated names/lists, retires
its borrowed output before AT unlock and ignores late callbacks. Only a
submitted unanswered request creates a true fence. The primary framing reference
is [ST67 AT2.0.106, AT+FS](https://applist67.github.io/Web_AT_Documentation_ST67/v2.0.106/index.html#at-fs).
The old binary-read requirements and all genuine fences remain unchanged.

## Initial host/build evidence (preceding implementation)

- All38 actual-C regression files pass: the preceding34 plus codec/store,
  NCP adapter, list lifetime and Cloud settings control suites. These use
  synthetic media/secrets and SDK/RTOS boundary mocks, not a physical NCP.
- Codec/store tests cover maximum/minimum records, all2561 byte mutations and
  truncations, append, schema/flags/field bounds, open network, all2562 partial
  write positions, all2561 readback mutations, lost full-write ACK, generations,
  failed/absent/legacy/future storage and scratch scrubbing. CRC has a known
  independent `123456789` vector. NCP adapter runs both write policies and
  verifies Wi-Fi/Cloud merges, deletion/tombstone intent, busy/invalid/no-write
  behavior and original whole-operation budget. Cloud tests exercise admission,
  verified unpair/reply-gate races, failed save and token scratch cleanup.
- 50 feature-mode syntax checks pass: ten production units across BLE-only,
  Wi-Fi-only, Cloud-disabled, radio-disabled and write-enabled configurations.
- `Tools/Build-NonSecureIncremental.ps1` passes, including linking and memory
  guards. Its build-only lane now includes new Core C units in generated make
  and response-file inputs; source generation and CubeMX settings are unchanged.
- Default write-disabled unsigned ELF SHA256:
  `3575B8A745AD42A62EC6B5B0E7284A94FB267C1764218BCF27660EC242035576`.
  Binary491732; heap373776, above368640 minimum by5136 bytes. Header9 is
  unchanged from HEAD9 after Git line-ending normalization. This was initially build-only; see the subsequent
  clean-default RAM restoration checkpoint below.
- A separate host-only write-enabled object/link passes with heap371048,
  only2408 bytes above the same minimum. It did not replace the default ELF
  or execute on hardware. This is a small remaining margin, not a worst-stack
  or concurrent ToF/endurance acceptance claim. Existing linker RWX warning remains.

First failed attempts are retained: sandbox GCC children stalled, then the
owned process tree was verified/stopped and ordinary compiler access passed;
the list extractor initially used the wrong helper invocation; the new final
scrub assertion inspected a deliberately staged store instead of the returned
reload; the wait diagnostic audit still expected the old implicit-forget call.
The corrected affected tests pass. No firmware defect was inferred from those
harness failures. Ignored evidence is in
`.local-dependencies/diagnostics/unified-settings-20261011/`, including
`native-results-first.json`, `native-results-final.json`, feature/build logs,
separate write-enabled results and `terminal-summary.json`.

## Authorized synthetic NCP channel follow-up

The user explicitly authorized an absent-name synthetic fixture, alternative
verified-unused test names when necessary, and RAM-only instrumentation. Four
RAM test variants used the existing control owner, settings mutex and buffers;
no new task/queue/capacity or steady allocation. Startup real-settings loading
was bypassed in these temporary variants, and a compile assertion required
`APP_SETTINGS_WRITES_ENABLED=0`. No managed/legacy file or CWCRED mutation ran.
Only public retained SSID/credential-reference/desired flags were captured and
restored through verified RAM scalar writes; no password or token was read by
host, sent, logged or stored. Each complete inventory proved `n6s_probe.cfg`
absent before create. Each run deleted only its definitely owned fixture and
completed a new inventory proving that fixture absent. No existing file was
replaced or deleted. No automatic security/credential persistence was enabled.

The fixture was 2561 printable bytes: uppercase HEX of `bytes(range(256))*5`
(1280 raw bytes) followed by `!`. The decoded raw data contains five NUL bytes
and includes CR/LF values; these are HEX characters on disk. This is a synthetic
channel pattern, not a real schema record or a credential migration.

Three failed hardware attempts are retained, not converted to PASS:

- Initial128-byte slices under the original single2000ms create/write/readback
  scope timed out during write after896 bytes; readback was NOT RUN.
- Separate whole-write and whole-read2000ms scopes with512-byte slices wrote
  all2561 bytes, but full readback timed out after1024 matching bytes.
- Independently bounded reads still used one whole-write2000ms scope; this run
  timed out after2560 written bytes, before the final marker. Readback NOT RUN.

Each failure completed owned cleanup, with no fence, SPI fault, allocation
failure or NCP recovery observed. The failures proved that the preceding product
whole-commit/load budget and128-byte strategy could not be accepted for maximum
records. Product budgets and capacities were unchanged at that checkpoint.
Those failures remain FAIL; the later bounded implementation is tested separately.

The final channel-only variant used an independent original2000ms scope for
each create/write/read SDK operation, not a larger product commit budget.
Six writes (512x5+1), exact size2561 and six full-file reads passed; every byte
matched. CRCs computed from actual returned characters/decoded bytes matched
independent Python zlib: ASCII `8D391A60`, raw `1E7A6D24`; raw count1280/NUL5.
Thirteen independent exact boundary reads passed:
`(offset,count) = (0,1),(1,2),(63,127),(127,128),(255,129),(512,255),
(1023,256),(1024,257),(0,511),(511,512),(512,513),(2559,2),(2560,1)`.
Maximum read513 exercises128/256/512 transport boundaries, odd nibble offsets
and the final marker. This operation took about13.8s in the control-owner
service interval; host trigger-to-completion observation was28.234s including
owner scheduling. It therefore does not validate the original whole-operation
2000ms settings path. Cleanup result0/absent1/owned0 and terminal0 were captured.
Final probe ELF SHA256:
`4384582BD5128EC5EE0EF827BC404DEA1EF3D1FD0F7EB81B43237146FE6FC3E4`,
binary491488/heap373984/header9. Radio/SPI allocation/fault counters0,
NCP recovery0/0/0, ToF ready, UART151/151 with zero drops/errors. USB pings
continued during the probe. No BLE-connected, Cloud-connected or endurance
acceptance is inferred. The old pairing storage integrity remains UNKNOWN:
printable HEX success cannot recover its absent binary bytes.

The actual temporary C helper passed four native boundary-mock assertions in
each variant: collision avoidance/whole bytes/CRC/boundaries/owned cleanup;
failed inventory blocks create; submitted read failure retains a true fence and
defers cleanup; only fresh safe driver state permits owned cleanup. These tests
are separate from the preceding38 regression files/50 feature checks, which
were not rerun without production changes. Initial Python lacked pyserial;
the existing training virtual environment corrected the host setup failure.

Both temporary production-source edits were restored to their exact pre-test
bytes. Build-only recheck regenerated the identical default3575B8A7... ELF,
binary491732/heap373776/header9. RAM restoration and terminal board state are
recorded in the checkpoint below. Ignored evidence:
`.local-dependencies/diagnostics/ncp-ascii-probe-20261011/`: `first-*`, `second-*`,
`third-*` failure evidence; final `hardware-result.json`, `probe-uart.log`,
exact probe images, four native/build logs, original source backups and
clean-default restoration logs. No temporary hook remains in production source.

## Real migration remains blocked

The tracked default is `APP_SETTINGS_WRITES_ENABLED=0`; no CLI override exists.
The preceding maximum-size2000ms whole-commit/load timing FAILED, while the
independently bounded synthetic channel PASSED. The later bounded implementation
and its actual-path evidence are recorded separately below. New managed-record boot/restoration, power
interruption, connected Cloud recovery and full task4 endurance remain NOT RUN.
The current write-enabled heap is371296, only2656 bytes over368640; default
heap374016 has5376 bytes margin. The preceding margins2408/5136 remain historical.
This is a small remaining C-heap margin, with no worst-stack/concurrent dynamic
allocation/endurance proof. HEX does not encrypt credentials, CRC does not
authenticate a record, and older alternate records may retain or resurrect
previous desired credentials/pairing after corrupt-newest fallback.

Before a real migration can be proposed for approval, the maximum-size product
path has passed bounded synthetic actual-path validation without capacity
growth or clearing fences. Real migration still needs a
complete validated source: SSID/password for personal/open Wi-Fi plus device ID,
workspace ID, token and desired/enabled flags. SSID is the network name, not an
enterprise account username. The legacy Cloud binary bytes remain unavailable
through the current NCP read channel; an independent CRC cannot supply absent
bytes. The NCP saved credential reference can restore Wi-Fi without revealing
its password, but is not a validated password source for a new unified record.
No partial seed, inferred zero, silent re-pairing or automatic provisioning is
allowed. A separately approved user-supplied replacement would be provisioning,
not proof or recovery of the old saved record.

A subsequent concrete migration implementation and action-time approval must
name the validated complete source and the two destinations
`n6settings0.cfg`/`n6settings1.cfg`, the initial inactive-slot selection, exact
encoded length/generation/CRC and create/write/full-readback/publication steps.
Original `n6cloud.cfg` and CWCRED records stay untouched. The active old managed
slot, when present, stays untouched until replacement validation; an unknown
completion requires quiescence/recovery and full reread, not a blind second
write. After verified commit, desired-state restoration and power-interruption
rollback require separate bounded acceptance. Forget/unpair are logical removal,
not secure erasure; the older-record fallback policy must be explicitly reviewed.
Enabling the compile flag alone does not bypass legacy/unknown-storage refusal,
and no such enablement or real migration was performed here.

## Earlier clean-default terminal board checkpoint

All four temporary variants and the final clean-default restoration were
RAM-only through `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run`; no NOR programming
command, signing/package action or header modification. Exact default ELF
`3575B8A745AD42A62EC6B5B0E7284A94FB267C1764218BCF27660EC242035576`
was running in RAM at this checkpoint, with real settings writes0. Version header9 matches HEAD
after Git line-ending normalization, and its git diff is empty. New managed-record
boot/restoration remains untested because none was created. The terminal clean
build preserves the earlier38 native/50 feature results; exact restored source
and ELF make those unaffected results applicable.

Separate board impact on the clean-default boot: normal legacy-only inventory
returned settings result2, then the unchanged strict1172-byte legacy Cloud read
timed out at2000ms: declared1172/available27/copied0/fence1. Automatic existing
AT_FENCED coordinated recovery completed14404ms, NCP1 attempt/1ready/0failed.
Public saved SSID/credential-reference intent was then restored in volatile RAM,
with exact scalar readback; the existing ordinary Wi-Fi owner restored IP in
2855ms using that saved NCP reference. No password or real persistence was used.
This is a legacy-read failure and successful coordinated recovery checkpoint,
not new-record desired-state acceptance or restored Cloud pairing.

Final `board-final.json`: ToF ready/advancing391->430, recovery0/0/0/gen0 after
MCU RAM restart; Wi-Fi IP/USB/radio ready, BLE advertising/disconnected, image
NONE, Cloud unpaired. Radio allocation failures0/SPI faults0; UART165/165,
zero drops/format/HAL/transport errors. Radio gap32ms/BLEpump21ms in this final
sample does not replace the separate14404ms recovery duration. MCU reloads reset
uptime/counters; compare within each exact boot, not with the pre-test8 ToF
recoveries. COM6/COM8 and debugger/programmer/test handles were closed; no active
build or hardware campaign remains. Real legacy/configuration files and CWCRED
records were not written, deleted or migrated; existing HTTP/TLS behavior,
firmware Flash/header/signing/package/commit/push/deployment remain unchanged.

## Bounded actual product path follow-up (2026-10-11)

The current production path implements the immutable13250ms/15-command contract
above. The corresponding hardware exercise used the actual production
`AppSettings_SaveCloud`, `AppSettings_SaveWifi`, codec/store, exact full readback
and `AppSettings_InitializeAndLoad`, with only a temporary sealed namespace and
cancellation injection. This verifies the maximum product operation; the earlier
channel-only experiment did not execute those save/merge/publication functions.

The complete SDK inventory initially held30 files. Two synthetic files brought
it to exactly32. The SDK returned a complete32-entry list with its documented
header and terminal and no overflow, but the adapter's `>=32` guard rejected
that legitimate full list. Three actual-path runs failed at reload and remain
FAIL, despite six successful commits. Scalar-only diagnostics identified this
boundary; no file content or credential names were logged. The corrected adapter
accepts a complete32-entry SDK success; the SDK still rejects the33rd entry,
missing/duplicate header, malformed/truncated filename and missing terminal.
Native regressions cover both boundaries and use the actual SDK struct layout.
No file-list capacity was increased and none of the30 existing files was deleted.

Final sealed probe ELF:
`7A1D472B5E1924A71FA71B378402B4BBE683E33DD86F0FF196EEDBF98FEF35D5`,
binary497452/heap369000, minimum368640 retained. Two larger temporary helper
builds failed the heap guard (367848/368424), were retained and never RAM-loaded.
Unused temporary persistence APIs were sealed off and the temporary helper alone
used size optimization to fit; production optimization/capacities stayed intact.
This instrumented image permitted internal saves only while the synthetic probe
was active, on complete-inventory-proven unused `n6t00a.cfg`/`n6t00b.cfg`, with
an exact synthetic-content allowlist. Public writes-enabled remained0; automatic
real persistence and startup real-settings loading were blocked. A bitmap acquired
only after definite successful creation restricted cleanup to owned test files.
No real settings, legacy file or CWCRED was modified or read into the host.

- Mode1 PASS: maximum2561-byte Cloud merge/commit generation1 in9818ms/14 commands,
  then Wi-Fi merge/commit generation2 in9560ms/14. The first SSID used32 synthetic
  `s` characters; the second used `r`; other fields were known synthetic values.
  Independent Python CRC32s8041EBA7/2BDA8646 matched the fully verified records.
  Full two-slot reload selected generation2 in9564ms/15 commands, and all2561
  bytes of the old active generation1 still matched independently encoded data.
- Mode2 PASS: generation1 commit10323ms/14. Cancellation after the first confirmed
  generation2 write had returned and its SDK scope/pointers/AT mutex were retired
  returned IO in3096ms/2 commands. RAM kept generation1; a subsequent save issued
  no SDK command. No true fence was created. Full reload6456ms/10 selected the
  intact old generation1 while rejecting the incomplete alternate. Independent
  full2561-byte old-active equality passed again.
- Both runs completed owned-only deletion and a new complete inventory proving
  both names absent (`cleanup=1 absent=1 owned=0`). A subsequent test reused those
  names only after another complete absence check. All143 request-to-PONG USB
  pings passed, maximum16ms; ToF stayed ready and advanced in both runs.
  Radio/BLE pump gaps remained21ms; SPI faults, radio allocations and NCP recovery
  counts stayed0. UART242/242, zero drops/format/HAL/transport errors.

The two host observations48344/42547ms include owner scheduling, three separate
bounded settings operations, old-active comparison and cleanup; they are not
single-operation elapsed times. Every save/load above fits its own original
13250ms deadline, while commands retain their original<=2000ms limit. Native
cases also prove cancellation after final readback prevents publication, foreign
scope retirement, clock wrap and global expiry despite timely individual calls.
The first USB latency method included a150ms drain plus120ms settling delay,
so its390/406ms readings and failed250ms gate were invalid request-latency
measurements. They remain retained. The corrected timer begins at command write
and stops on the exact PONG; drain/settling occur outside that interval.

Final host evidence resolves39 distinct actual-C suites to PASS (including the
new `test_settings_scope_claim.py`), plus50 final feature-mode syntax checks.
Changed affected suites were rerun after the full-inventory correction; earlier
unaffected results were retained rather than unnecessarily repeated. Initial
missing-mock/fixture assertions and a missing compiler environment variable are
retained with corrected results. The separate unrestricted write-enabled link
was host-only and never RAM-loaded: heap371296,2656 bytes above the minimum,
248 bytes more margin than the prior write-enabled candidate. Default binary492452/
heap374016 has5376 bytes margin. Static inventory/text union reuse and guard
code-size reduction saved memory without heap allocation or larger stacks/pools/
queues/tasks. Observed compiler stack frames are not worst-stack proof.

Ignored evidence: `.local-dependencies/diagnostics/settings-budget-20261011/`,
including `native-results-final.json`, `features-final.log`, final build/link
logs, `first-*`/`second-*`/`third-*` failed hardware reports, successful
`hardware-result.json`, `probe-uart.log`, exact probe/default images, temporary
source backups and clean-default restoration evidence. Temporary instrumentation
is removed from production; real writes stay compile-time disabled.

Synthetic managed-record reload is now tested. Real managed-record cold boot/
desired-state restoration, power interruption, connected Cloud recovery, real
migration and task4 endurance remain NOT RUN/BLOCKED as applicable. The legacy
binary pairing channel still omits bytes; CRC alone cannot supply them. The small
write-enabled heap margin, plaintext reversible HEX, unauthenticated CRC and
older-slot rollback of previous values remain limitations. No Flash/header/
sign/package/commit/push/deployment or HTTP/TLS protocol change occurred.


## Bounded-path clean RAM checkpoint (2026-10-11)

Temporary edits to `app_settings_ncp.c` and `wifi_ble_app.c` were restored to
exact final production bytes; scalar-only driver instrumentation was restored
also. The guarded build regenerated byte-identical final clean ELF
`4A33C963AA60C50878220489200199AD80215E6B38A2C877F6BAA768FFB4ACFC`,
binary492452/heap374016. `Tools/Debug-NonSecureRam.ps1 -NoBuild -Run` loaded
this unsigned write-disabled default into RAM. Header9 matches HEAD9 after Git
line-ending normalization and has no git diff. No persistent firmware Flash
installation, new header, signing or package was generated.

The unchanged strict legacy1172-byte read still fails: elapsed2000ms, two
callbacks, declared1172/available27/copied0/fence1. The existing coordinated
AT_FENCED recovery then passed14362ms, NCP1/1/0. Public retained SSID, saved
credential-reference and desired flags were restored only in RAM with exact
scalar readback; existing CWJAPS restored Wi-Fi IP in2580ms without password
read/write or CWCRED mutation. This is legacy-read recovery and retained intent,
not restored pairing or acceptance of real unified-record boot. Cloud remains
unpaired and saved-pairing integrity remains UNKNOWN.

Final board: ToF ready/advancing386->428, recovery0/0/0/gen0 within this new
MCU boot; Wi-Fi IP/USB/radio ready, BLE advertising/disconnected, imageNONE,
Cloud unpaired. SPI faults/radio allocations0; UART165/165, all drop/format/
transport/HAL errors0. Radio31ms/BLEpump22ms in the final sample do not replace
the separately measured14.362s recovery. COM6/COM8 were successfully reopened
and closed after the runner released them; no Python, compiler, make, programmer
or debugger process remained. Terminal evidence is `terminal-summary.json`,
`board-final.json`, `default-uart.log`, `build-clean-final.log` and
`handle-release.json` in the ignored follow-up directory.

The hardware commits here created an unused alternate, rather than deleting
an already occupied inactive file. That worst15-command replacement and
BLE/Cloud-connected admission were covered natively, not exercised on hardware.
Power-interruption, real unified-record cold restoration and connected Cloud
return remain separate acceptance gates. Old failed reports remain intact.

## Settings memory and controlled synthetic startup follow-up (2026-10-11)

Local `ble/d89a510` and preceding dirty work were retained. Initial current-board
read showed ready advancing ToF54848->54887, Wi-Fi IP, Cloud unpaired and no
active test/build/debugger. Pre-task exact source/image backups and every earlier
failed attempt remain in the prior diagnostic directories. The source and ELF
were verified before relying on the old RAM symbol map.

### Product change and measured memory

At unchanged `-O3`, bounded CRC/HEX helpers are shared with `noinline` instead
of duplicated constant-width inline code. Existing nonblocking settings lock,
unlock and field-copy helpers are shared similarly. No schema, decoding rule,
AT budget/fence, cancellation, cache-publication or owner ordering changed.
No pool/queue/stack capacity, task, dynamic settings allocation, linker region,
CubeMX configuration, Secure/FSBL interface or HTTP/TLS behavior changed.
Generate Code is not required for this C-only change.

Default unsigned final ELF:
`7EE459582765C6174B36EC698B9FE7948D84B1DD106C42D89B4D446946F5BE9D`,
binary491108, C-heap capacity375360 (6720 above368640 guard). Previously374016/
5376; default saved1344 bytes. Host-only unrestricted write-enabled ELF:
`ADC5DAB5D7CD34E81C0561D62FFBBB4C49A2F0EC49250D87AA081A6760947C47`,
C-heap capacity373280 (4640 margin), versus371296/2656 previously:1984 bytes
more, about75% larger guard margin. The unrestricted image was not RAM-loaded.
The intermediate codec-only measurement372256/3616 is retained separately.
All guarded builds passed; the existing linker RWX warning remains.

These figures describe linker capacity, not allocator free space. Read-only SWD
snapshots inspected only the named `__sbrk_heap_end` pointer, with exact ELF and
SRAM bounds; no heap payload, password or token was read. Original clean board
reserved357412 arena bytes with16604 uncommitted tail; final clean board reserved
the same357412 with17948 tail. The temporary startup-reader capacity374200 had
357412 arena bytes/16788 tail. `_sbrk` arena reservation can include free blocks
inside malloc; live malloc bytes, internal free space and fragmentation were not
measured. SRAM4 radio pool is separate. None is a worst-case/endurance guarantee.
Compiler frames were inspected (decode176, encode104, shared digit/CRC0-4,
lock8/unlock16 bytes); these are individual frames, not whole-stack bounds.

### Host tests

All40 actual-C regression files and50 feature-mode syntax checks pass, including
both write policies, parser/lifetime/fence/recovery/service/owner and codec/store
regressions. New `test_app_settings_reboot.py` preserves only synthetic mock media
while clearing adapter RAM/mutex/status and modeling a fresh driver after all
SDK calls retire. It cancels at all15 maximum-replacement command boundaries:
inactive delete, create, six writes, size and six verification reads. Old active
bytes remain exact; unknown outcome blocks another write. Fresh load chooses
old generation2 before the final write, or fully CRC-valid generation3 after
all writes completed. Desired/enabled0 survive the cold-cache model. A live true
fence blocks inventory unchanged until separately modeled fresh init. This is
host fault injection, not proof of electrical power loss or NCP Flash durability.
Existing exhaustive2562 partial-byte/lost-full-write-ACK cases remain covered.

Both temporary actual C helpers passed before hardware use. Initial startup-
reader native cleanup failed because its mock equated any SDK delete with public
writes-enabled1. The correction permits only the explicitly owned test cleanup
path in that mock; production public writes stay0. The first failure is retained.

### Supported RAM-only startup evidence

Five controlled MCU/SRAM load operations used only
`Tools/Debug-NonSecureRam.ps1 -NoBuild -Run`: writer, reader, writer, same reader,
then clean default. No bare Reset/NVIC reset, jumper change, board power removal,
NOR programming, signing/package action or unrestricted write-enabled boot ran.
The two reader loads execute the application's existing Radio startup call to
`AppSettings_InitializeAndLoad` and its normal Wi-Fi/Cloud cache consumers. The
only temporary startup differences are two verified-owned synthetic slot names,
a fail-closed known-record allowlist, and namespace isolation from the legacy
file. No RAM cache preload replaces the startup load.

Complete initial inventory proved `n6r00a.cfg`/`n6r00b.cfg` absent with30 existing
files. Only those names and exact known2561-byte fixture fields could be written.
Public write admission remained0 throughout; startup real-settings loading was
blocked in the writer image. The read-only startup image kept the default compile
policy0. Fixtures set flags5 (Wi-Fi/Cloud present, desired0/enabled0), preventing
synthetic association or token use against an endpoint. This tests disabled
desired-state metadata/cache restoration, not a live authenticated connection.
Ownership was journaled from definite create ACKs and retained in a host manifest
across MCU reloads. Only that verified bitmap/names were restored for subsequent
replacement or cleanup, with independent RAM readback; no ownership was inferred
from an existing filename.

- Two maximum actual `AppSettings_SaveCloud(..., enabled=0)` commits passed:
  generation1 in11828ms, CRC8214E87A; generation2 in11308ms/14 commands,
  CRC5A51424C. Independent Python canonical encoding/CRC matched both.
- First read-only fresh RAM startup loaded both full slots, selected generation2,
  exact length2561/CRC5A51424C/flags5/writes0. Normal Wi-Fi cache desired0 and
  normal Cloud cache paired-but-disabled were observed; ToF stayed ready and
  advanced. No legacy credential read or Cloud endpoint request was needed.
- The writer was RAM-loaded again with the journaled ownership restored. It
  reloaded the fixtures, deleted only its own inactive generation1 file, recreated
  it, and confirmed its first512-byte generation3 write. Cancellation occurred
  after that SDK call/scope/pointers/AT mutex retired. ResultIO in4628ms/3 commands;
  RAM stayed generation2, retry issued no command and fence stayed0. The partial
  alternate was deliberately retained across the next controlled RAM startup.
- Second fresh startup using the identical read-only reader ELF again selected
  intact generation2 with length2561/CRC5A51424C/flags5/writes0, rejecting the
  incomplete alternate. This physically covers an occupied inactive replacement
  and warm fresh-cache fallback after a retired-command interruption.
- Read-only reader's separate owned-fixture cleanup removed only those two
  journaled test files. Complete inventory proved both absent/owned0. All158
  concurrent request-to-PONG USB pings passed, maximum16ms; ToF advanced at
  every observed phase. SPI faults/radio allocation failures stayed0; recovery
  was not required during these synthetic phases.

Writer ELF `B4DD2D0BA25CB275CCC4547CDBF36A02B8F5CC4EDA9CEF767B670C65FB1EE712`
had binary495348/heap371112; read-only reader ELF
`1E5C36D8514CC6A0AE1C6B3D78E4C5D28DA47A46155CCF4DF46FECE594B4691E`
had binary492268/heap374200. Both retained the minimum guard. Temporary control
work used the existing owner/buffers; no new firmware task or steady allocation.
Raw snapshots compare frames/counters within each boot, never across MCU resets.

### Clean terminal and remaining limits

Temporary source edits were restored exactly. Build-only recheck regenerated
byte-identical final7EE459... ELF, then restored it to RAM with public writes0.
Header9 matches HEAD9 after line-ending normalization and has empty diff. The
unchanged real legacy1172-byte read still returns declared1172/available27/copied0
and times out2000ms, fence1. Existing coordinated recovery passed14301ms (1/1/0).
Public retained SSID/credential-reference/intent were restored only in RAM with
exact scalar readback; ordinary saved-reference Wi-Fi restore passed2584ms.
No real password/token or credential persistence was fetched, rewritten or migrated.

Final ToF ready/advancing387->429, recovery0/0/0/gen0 in this new boot; Wi-Fi IP,
USB/radio ready, BLE advertising/disconnected, imageNONE, Cloud unpaired.
SPI faults/allocations0; Radio/BLEpump final maxima22/22ms; UART165/165, zero
format/transport/HAL errors or drops. Named heap snapshot is reported above.
COM6/COM8 reopened/closed after runner release; no compiler, test, debugger or
programmer process remains. No firmware Flash/sign/package/header change,
commit/push/deployment or HTTP/TLS change occurred.

Not physically tested: power loss during NCP Flash programming, a reset during
an in-flight AT transaction, full-write-with-missing-terminal durability, actual
cold board power removal, real managed namespace/migration, active managed
Wi-Fi/Cloud restoration, connected BLE/Cloud contention, worst-stack/allocator
fragmentation or full task4 endurance. These cannot be claimed from a retired-
command cancellation followed by the supported SRAM loader. Host models cover
bounded interruptions, while genuine missing replies retain the existing fence/
quiescence contract. Real migration is still blocked by unavailable complete
validated pairing/password source; generic continue does not authorize replacing
or reprovisioning those values. CRC cannot recover bytes absent from the channel.

Ignored evidence `.local-dependencies/diagnostics/settings-reboot-20261011/`:
`native-results.json`, `feature-modes.json`, guarded build and separate link logs,
`reboot-native.log`, writer/reader native logs plus retained first failure,
`hardware-result.json`, `campaign-uart.log`, ownership manifest, exact source/image
snapshots, before/reader1/final heap JSON, `board-final.json`, `handle-release.json`
and `terminal-summary.json`. Previous failed timing/reload/heap reports remain
unchanged in their original directories.
