# Instructions for Codex and future agents

Read this file and [README.md](README.md) before modifying the project. Do not
read [CHANGELOG.md](CHANGELOG.md) during normal discovery or implementation.
Open it only when the user explicitly requests history or when the task itself
requires historical investigation. When merely adding a new dated entry,
inspect only the small insertion area at the top rather than loading the file.

This file is the engineering contract for future work. It records the current state, safety rules, CubeMX boundaries, known deviations from vendor code, verification requirements, and how to communicate changes to the user.

## 1. Project objective

Continue developing the STM32N657 firmware that combines:

- External-NOR boot through an FSBL.
- TrustZone with Secure and Non-Secure applications.
- VL53L9CX through I3C1 and DMA.
- USB CDC through USBX, UCPD1, and TCPP0203.
- ST67W611M1 through SPI5, Wi-Fi, and BLE.
- A GC9A01 240x240 round TFT through a dedicated SPI4 TX-DMA path, leaving
  SPI5 reserved for ST67.
- Signed BLE XMODEM firmware delivery through the existing authenticated Secure
  A/B installer.

Work must be technically correct and educational. Explain in Hebrew what changed, why it changed, how it was verified, and what risk remains.

## 2. Current state that must be preserved

- Platform upgrade M1-M7 package-only acceptance completed2026-10-21. USB20,
  BLE20+5/reconnect1, approved Cloud20/no-browser/reopen/cursor20 PASS. No
  additional Cloud collection. RPS4 and spatial2 each pass100 real NPU frames,
  50.235/50.219s, exact tensors100/100, score delta0, unchanged gates.40 host/
  native tests plus actual BAT/Tk selection-label-continuation PASS. Exact v12
  package498400bytes SHA98da723524f82f23e2c91a3cbbdc0442a729cb6b3bd3a81fc097a6a04aa18525
  contains the HIL BIN; package-only uses existing signing and does not rebuild
  or install. Proposed new persistent-install path was auto-review DENIED before
  process start; never created/retried. Approved package-only alternative passed,
  original persistent-installer body unchanged. No Flash/OTP/XIP/Pair/cache/new
  credentials. Original demo model59f72382.../contract5137ed48... restored with154
  exact integration files. Current guarded BLE-only RAM ELF6a6a5d1fcd70be9ed1826624b4e3bf97d5ec35758c9f1915772e1fa4b5c8d781,
  firmware11/heap369136 (min369072 preserves baseline432); NCPpreserve1/settings
  writes0. Live audit: four classes/NPUerrors0, ToFadvancing, WiFiIP0/CloudHTTP0,
  datasetoff/imageNONE/SPI0; handles and leases released. Ordinary Debug hashes
  unchanged; never substitute it for guarded RAM. RAM loses demo on power loss.
  Saved test-model deployment becomes stale after intentional demo restoration;
  retain immutable candidates/HIL reports and re-integrate/reload before reuse.
  Existing HTTP device demo mode remains insecure; host downloads verify HTTPS.
  Static scene proves computation, not all-class field recognition. Server5905a7d,
  deployment39641798300 SUCCESS; N6 has no Actions checks. See platform-upgrade
  engineering record, sanitized results and training/README_HE.md. Original
  untracked training/PLATFORM_UPGRADE_PLAN_HE.md is user work: do not stage it.


- Morning BLE-only readiness (2026-10-12): corrected nonblocking host hour
  PASS3600.545552s/6920 actual NPU/3673 CRC images/5971 CLI finals;
  p50/p95/p99/max93.40/111.79/126.39/219.73ms,1500ms gate unchanged.
  Direct NPU/image gaps0.570112/1.023138s/loop lag19.755ms/errors0;
  gen25/frame+run advance/age253ms/1765 matching sensorframe IDs;11 USB snapshots
  NCP/SPI0/WiFiIP0/CloudHTTP0/pairing preserved. Earlier hour CLI/CRC passed but
  receive continuity NOT_ACCEPTED4.79/5.18s; callback backlog and synchronous
  4.7MB report writes exposed weak host watchdog, exact old I/O cause unrecorded.
  Host logging/gap/timing fix only, focused120.624s with4.503s writer delay PASS;
  reusable hil_tests/run_ble_npu_soak.py. No new firmware build/load/reset/deploy.
  Final immutable5689348E.../gen1/31/705/CRC72B6B9AF/writes0/calls4 match;
  ToF123106->123223/BLE adv-disconnected/imageNONE/all owned handles+lease released.
  Same MAIN18cff... Azure/static/health verified; independent production browser
  E2E NOT RUN (fresh CUA apps[]/browsers[]). RAM loses demo on power loss;
  guarded reload only, never normalDebug8234... or Wi-Fi-restoring fallback.
  Hour !=overnight/fulltask4 acceptance. No Flash/header/sign/settings/Pair/cache/
  security/FAE change. See recovery doc and morning checklist.


- Actual BLE-only NPU/image + deployment checkpoint (2026-10-12): explicit human
  browser disconnect/lease reacquisition; hook-free RAM5689348E... unchanged.
  Three nonbonded cycles PASS297 CLI finals/max189.49ms/388 actual NPU Notify/
  187 CRC images/errors0/age252ms; RPS-only routeNONE, reconnect generations
  11/13/15 advance,92 matching frame IDs. PairFalse/OSpairedfalse throughout.
  NCP/SPI0, WiFiIP0/CloudHTTP0/images0/pairing preserved.600.483s soak PASS
  1171 NPU/615 CRC images/976 finals/max165.36ms/errors0/age252ms;
  first host premature-image assertion FAILED, retained; corrected retry no reset.
  Final immutable568.../slot0/gen1/31/705/CRC72B6B9AF/writes0/calls4 unchanged;
  ToF40840->40921/BLE adv-disconnected/imageNONE/fence-drain-notify-recovery0.
  All owned hardware handles/lease released; normal Debug8234... not substituted.
  User-authorized N6 PR1 merged MAIN18cff111...; Actions38303887605 build+deploy
  SUCCESS, Azure public routes+health200/staticSHA dce21722... exactlocal match.
  Production browser rendering independently NOT RUN; localhost receipt user-
  observed. Earlier user-owned pause superseded by explicit release. Older failed
  latency/Cloud/endurance/fulltask4 causes remain open. No firmware Flash/header/
  sign/persistent write/FAE change. See latest recovery documentation.


- User-observed NPU browser receipt (2026-10-12): scissors98.8%, frame20615/
  inference8943, explicitly separate from displayed image. User says working;
  end-to-end receipt is USER-OBSERVED, not independent packet/alignment/soak
  acceptance. Prior Windows failures retained; cause unproven. NEVER PAIR the
  N6 BLE device in Windows: no OS Pair/Pair APIs/forced bonding/cache erasure;
  automated clients pair=False, browser chooser/GATT connect only, cancel system
  pairing prompt. Preserve Cloud pairing/settings. Browser currently user-owned;
  wait for parent confirmation of explicit מנותק before ANY hardware/serial/BLE/
  debugger acquisition or test/reset/load. No elapsed-time assumption. Only docs/
  retained-log review performed now; live5689348E... and BLE-only state untouched.
  Three actual image+NPU runs/soak/deployed verification still pending. Evidence
  ignored coordinated-user-npu-receipt-20261012/report.json; recovery doc.


- Resumed GATT/latency checkpoint (2026-10-12): live hook-free5689348E... protected
  BLE-only RAM/bin493212/heap373064/margin4424/writesOFF/preserve1/header9.
  UUID0005 now DEBUG service0101/index2 appended, legacy handles/order retained.
  NCP readback confirms new UUID/Notify; transient REGISTER0/1 ACK0/0 and
  central-negotiation prototype did not solve Windows discovery; hooks removed.
  ServiceChanged2a05 manual subscribe AccessDenied, not retried/worked around;
  no cache/bond/identity/security mutation. Exact fresh UUID query empty.
  120.388s existing-channel BLE-only PASS188 finals/123 CRC images/max131.81ms;
  prior1515.03ms FAIL retained/causeuncaptured, not endurance acceptance.
  New NPU Notify0/three new integrated+soak NOT RUN. Final immutable+storegen1/
  flags31/705/CRC72B6B9AF/writes0/calls4 match; WiFiIP0/intent0/CloudHTTP0,
  paired/ToF advancing/BLE adv-disconnected/NCP+SPI0/imageNONE. Handles/lease
  released. Chrome/IAB tools explicitly unavailable; tested local preview
  localhost4173/terminal remains running for human Chrome device selection.
  Website draft PR1 latest0b30c802... CI38299648238 PASS/deploySKIP. No firmware
  Flash/header/signing/persistent write/FAE edit. See latest recovery section.


- BLE-only NPU follow-up (2026-10-12) NOT ACCEPTED: protected RAM7CAB8F5A...
  bin493212/heap373064/margin4424, writesOFF/preserve1/BLE-only1/header9.
  Fresh immutable/store slot0/gen1/31/705/CRC72B6B9AF/writes0/calls4 unchanged;
  WiFiIP0/intent0, Cloud paired/waiting/no requests. New UUID0005/index3 publishes
  actual timestamped Neural-ART class/scores/confidence; CCCD does not select images.
  46 native/5 feature/default+protected builds and16 website tests pass. Physical
  new Notify BLOCKED: Windows uncached E_UNEXPECTED/BAD_COMMAND, cached old UUIDs;
  no OS cache/pairing/credential mutation. Three new integrated runs NOT RUN.
  Cached old CLI/ToF receives5 CRC images/5 PONG finals but FAIL1515.03ms>1500.
  NPU actual USB4228runs/errors0; final20 USB PONG/max308.58ms/LCD35 renders pass,
  ToF advancing, NCP/SPI faults0, BLE adv/disconnected, handles/lease released.
  N6 website draft PR1/SHA7e637509... pushed; CI build/tests/packagePASS/deploySKIP;
  no available browser, actual end-to-end/deployment/endurance still open. FAE
  untouched. Prior wired/Cloud hour alsoFAILED1186.5s/1401 USB/new request errors.
  No firmware Flash/header/signing/persistence write. See recovery doc/checklist.


- Classroom recovery follow-up (2026-10-12): live protected hook-free RAM is
  304CC6F723881BD3E8DA50219858F6BBED317D15F394701B0368B239F136389D,
  writesOFF/config-preserve1/header9/bin492124/heap374360/margin5720. Normal
  Debug49E3F634... config-preserveOFF must not replace it. Saved slot0/gen1/
  flags31/705/CRC72B6B9AF/writes0/calls4 unchanged in fresh guarded audits.
  Source adds8 static bytes: same UNKNOWN sequence repeats once after fresh
  application input, before that input executes; no old command/output/final
  replay, raw updater exclusion intact.45 native/5 changed-unit feature modes,
  default+protected NS builds pass; no Generate Code required. Host runner
  preserves image CCCDs and continuous UART between profiles; exclusive lease
  status/marker must be honored, never stolen. Three final bounded profiles
  PASS19819/20533/20519ms,39 BLE finals/32 USB pings; actual UNKNOWN before new
  PONG, ToF/CLOUD continuity, attempts0->3/ready3/failed0/no extra recovery.
  Current-fix temporary DMA probe FEDAC2E8... PASS: real252-byte transfer,
  RX251 remaining at abort, both DMA/SPI READY, actual UNKNOWN,12 BLE finals/
  14 USB pings, AT_FENCED16877ms; hook disarmed and absent from live304CC6F7...
  Initial DMA probe passed cleanup but missed remote UNKNOWN; retain qualifier.
  Strict combined soak FAILED BLE3193.5ms vs1500ms; bounded diagnostic also
  FAILED2906.82/2543.51ms, GATT writes45/50ms, fast firmware PONG, AT BUSY peak
  3060ms/Cloud worker4501ms. Do not relax/promote the latency gate or reset a
  healthy NCP for contention. Natural SPI1/pre-HAL IRQ/RX OVR error4/len520/
  tick431538 observed before soak, no new NCP recovery; cause and audit-window
  association unproven. Older plus one earlier old-reader-startup extra recovery
  remain UNCLASSIFIED. Wired USB/LCD/Cloud one-hour demo soak RUNNING; exact
  live progress in ignored coordinated-owner-progress.json, reports/docs in
  docs/radio-coordinated-recovery.md. Protected primary/fallback05FD9EFD...
  ELF/bin/map preserved in ignored demo-ready-20261013; reproducible startup
  in docs/demo-start-20261013.md. Browser rendering/optical LCD/active handler/
  unattended reconnect/fulltask4/physical power-loss remain open. No Flash/
  signing/header/pairing/settings-record/credentials/push/deploy change.

- Active Cloud/BLE campaign (2026-10-12): three bounded profiles remain FAILED.
  Radio/Wi-Fi17619/17984/16219ms;84 USB pings/24 BLE finals/ToF continuity pass.
  First two keep old Windows client across NCP reinit and lose CLOUD->BLE route.
  Third retires old host before reinit: Cloud frames7859->7869 auto-return, then
  fresh BLE finds ToF CCCD0100. Harness clearing it to0000 itself requests BLE
  then releases toNONE; final route assertion FAILED, not proof pure CLI steals
  route. Sequence5 UNKNOWN/tx4/active0 plus6 clean new finals/no HELP banner prove
  queued-reply interruption only; executing handler/physical DMA abort unproven.
  NCP1/1->5/5/failed0 includes one uncaptured extra recovery between profiles2/3;
  keep UNCLASSIFIED. Errors0->2/drop1 unchanged/SPI+alloc0. Fresh pre/post reader
  05FD... immutable SRAM and store slot0/gen1/31/705/CRC72B6B9AF/writes0/calls4
  unchanged; final fence/drain/notify/recovery0. Hardware handles closed, IAB
  existing workspace retained/Cloud MAP ON restored. No firmware edit/build/load/
  MCU reset/Flash/credentials/pair/deploy. Windows/GATT restoration is hypothesis,
  no proven firmware defect. Fulltask4/DMA/executing-handler/unattended reconnect
  remain open. See latest docs/radio-coordinated-recovery.md; retain3 FAILED reports.

- Existing Cloud workspace restored (2026-10-12): matching downloaded workspace
  had devices[]. User-approved ignored copy adds only already-paired N6-MAINT-B8FB,
  preserves all other fields/token/original file. Browser tool root limitation
  prevented automatic opening; user opened copy in IAB. RELAY CONNECTED/online,
  Cloud ping PONG+complete, MAP ON complete and independently rendered LIVE
  Depth54x42 frames/CRCs306373->306880 pass. Cloud status polling/paired/HTTP200/
  transport0/backoff0, uploads6060->6190/drop1 unchanged/request errors0. Cloud
  MAP ON restored publication; USB DTR-close releases only USB, not selected Cloud.
  No new pair/code/
  token rotation/workspace or firmware/build/reset/Flash/deployment. Keep existing
  IAB workspace open. No new immutable-SRAM audit or fault test here; combined
  BLE CLI/DMA fault/fulltask4 still NOT RUN. Earlier403/409 blocker below is
  superseded for this session; failures stay evidence. See current section in
  docs/radio-coordinated-recovery.md and ignored workspace-restore-20261012 summary.

- Combined-load preflight BLOCKED (2026-10-12): exact protected live reader05FD...
  verified; settingsOK/gen1/705/CRC72B6B9AF/writes0/reference1, no fence/drain/
  recovery. Cloud still paired but ERROR/HTTP403; uploads stopped6060. One runtime
  reconnect with existing pairing did not restore frames; drop0->1 while retiring
  pending frame. Server source maps403 to device_not_allowed (live body not read);
  user must check correct updated existing workspace/device membership. No new
  pair/code/token/workspace payload read or credential mutation. Sandbox BLE saw
  advertisement but all3 connection variants FAILED before commands; normal
  Windows transient pair=False connection PASS MTU247,6/6 PONG+final/max125ms,
  OS paired flag observed, no Pair API requested. Link closed; CLI RX6/120bytes,
  TX9/1195bytes, drops/retries/errors0. SPI5 data>8 bytes uses GPDMA1 TX10/RX11 by
  verified code path, but no in-flight DMA/cancellation HIL claimed. Combined
  fault NOT RUN until active Cloud is proven. Final ToF58337->58348/ready,
  Wi-Fi/radio ready, BLE disconnected/adv, NCP1/1/0 unchanged, Cloud403/paired,
  USB ping PASS, handles released/no active test. No firmware/build/Flash/reset/
  power-cut/HTTP-TLS/commit/push/deploy. No proven firmware defect to fix; combined
  BLE/Cloud/DMA fault and fulltask4 open. Evidence: ignored combined-preflight-
  20261012 and combined-recovery-20261012; docs/radio-coordinated-recovery.md.

- User pairing/managed startup/connected recovery verified (2026-10-12): user
  submitted pair locally; agent never read/replayed the code or workspace/token
  payload. ExactA8077FB8... initially paired/storeOK0/arm0/writes0, slot0/gen1/
  flags31/length705/CRC72B6B9AF/password length0. Original save UART line unavailable;
  paired publication plus actual committed metadata proven, then independent
  guarded startup loads the same full schema/CRC. Candidate genuine-fence test
  status3/fence1 PASS22152ms, Wi-Fi2766ms, ToF355039->355306, Cloud1136->1145,
  14 USB pings max328ms. Preexisting NCP3/3/0/request errors3/dropped2/SPI fault1
  unchanged by this test; natural SPI cause unproven. First host literal matcher
  FAIL corrected on retained genuine_fence1 evidence, no hardware rerun.
  Supported SRAM startup of read-only/config-preserve1 reader05FD9EFD... PASS;
  managed load4 commands/gen1/705/CRC72B6B9AF, writes0, saved Wi-Fi restored3431ms,
  pairing/Cloud route/images auto-return. Reader genuine-fence PASS19841ms,
  ToF2088->2316, Cloud603->608, 12 pings max328ms; errors/drops/SPI/alloc0.
  Live RAM is now reader05FD..., not candidate; normal Debug remains57FB502F...
  config-preserveOFF, must not be substituted under guarded-load contract.
  Final Reader storeOK/gen1/flags31/705/CRC72B6B9AF/writes0/fence-drain0, Wi-Fi IP,
  ToF advancing/Cloud paired and streamCLOUD/BLE disconnected. Heap374496,
  arena357412/tail17084/margin5856, not malloc-free/fragmentation proof. COM6/COM8/
  debugger released. Host report-write and optimized-out reader symbol failures
  retained/corrected with read-only inspection, no extra reset/pairing. No firmware
  change/build/Flash/header/sign/package/HTTP/TLS/commit/push/deploy or old-file/
  CWCRED mutation. Legacy integrity UNKNOWN; physical power loss/independent
  receiver CRC/rendering/in-flight BLE CLI-DMA/fulltask4 remain open. Evidence:
  ignored settings-user-pair-check-20261012; docs/settings-repairing-transition.md.

- Local non-authentication preparation completed (2026-10-11): exactA8077FB8...
  read-only SRAM vector/text/rodata/ARM sections match. Saved Wi-Fi reference and
  confirmed SSID, idle unpaired Cloud/no recovery/fence/drain/notify owner verified.
  One COM8 `cloud prepare yes` passes; UART at1636348ms result0/RAM_only1/
  legacy_preserved1. Fresh complete inventory: calls1/present0, no managed files.
  RAM arm1/writes1 permits only first user pairing save; seed flags19/gen0,
  password/token lengths0, epoch1/cancel1. No actual FS/credential write or pairing
  exchange. Wi-Fi IP/ToF/radio ready/Cloud unpaired/BLE disconnected; COM6/COM8
  released, no active process. Do not repeat preparation/reset; user opens existing
  workspace, presses + and sends displayed pair locally. Prior unarmed states
  below are historical. Initial host enum assertion3 vs production READY2 failed
  before submission; corrected, retained. No firmware/build/NOR/header/sign/
  package/HTTP/TLS/commit/push/deploy. Evidence: ignored settings-bootguard-20261011/
  prepare-only-summary.json; see docs/settings-repairing-transition.md.

- RAM transition boot blocker resolved (2026-10-11): opt-in
  W61_CONFIG_PRESERVE queries existing CWAUTOCONN0/CWMODE1/CWDHCP1, AP/clock/antenna;
  matched settings skip persistent-capable setters, mismatch stops. Actual recovery
  still powers off/reinitializes NCP.44 actual-C native/91 feature/default+reader+
  candidate builds pass; Secure/FSBL build-only pass. Two supported SRAM startups
  of exactA8077FB8... candidate pass, writes0/unarmed0; genuine legacy-fence recovery
  16262/15913ms, retained-reference Wi-Fi IP restored without password write.
  bin495612/heap370872/margin2232; reserved arena357412/tail13460, not malloc free.
  ToF1198->1238 and2274->2313/USB/radio ready/BLE adv-disconnected/imageNONE;
  Cloud unpaired, UART253/253 zero drops/errors,30 USB pings max329ms. Handles
  released. Guarded read-only reader05FD9EFD... not loaded; normal Debug output
  restored57FB502F... writesOFF/config-preserveOFF, differs from live candidate.
  User preparation/authentication/pairing and real managed readback/Cloud recovery
  remain NOT RUN. Board approval already granted. No original FS/CWCRED mutation,
  firmware Flash/header/sign/package/HTTP/TLS/commit/push/deploy; legacy integrity
  UNKNOWN. See [exact evidence and ready Hebrew user steps](docs/settings-repairing-transition.md).

- Historical RAM transition readiness audit (2026-10-11): board approval now granted;
  explicit user stop rule blocks load/reset because existing Wi-Fi init sends
  unconditional CWAUTOCONN=0, ST NCP2.0.106 documents EasyFlash persistence.
  No SYSSTORE=0 host setter found; actual unchanged-value write NOT proven.
  AppSettings boot stays unarmed, but generic NCP init is outside that guard.
  Prior7EE45958... RAM remains healthy; new2A076C3A.../43A897C2... NOT loaded,
  runtime heap/restart/pairing NOT RUN. No source/binary/FS/credential change.
  Resolve boot/recovery persistence contract before ready/user pairing; do not
  re-ask already granted board availability. See docs/settings-repairing-transition.md
  and ignored settings-ready-20261011 evidence.

- Approved re-pairing transition preparation (2026-10-11): explicit USB/cloud
  owner RAM seed only, preserves n6cloud.cfg/CWCRED/current Wi-Fi via reference
  flag16/Secured=1, no password export. Candidate compilewrites1/transition1,
  runtime0 until preparation/one first verified pair commit/then0; load never
  re-arms. Fresh inventory before create shares original13250ms/15-command scope.
  No paired publication or volatile new access after failed persistence.
  42 native+five final affected suites/60 feature/default+candidate builds PASS.
  Exact2A076C3A... candidate bin495324/heap371160/margin2520, reader43A897C2...
  writesOFF/bin491772/heap374720. New images NOT RAM-loaded, user NOT paired,
  no exchange or actual settings write; prior7EE45958... live RAM remains healthy.
  Original legacy integrity UNKNOWN; prior reader rejects flag as UNSUPPORTED,
  rollback cannot promise old Cloud auth/server state. Board availability and
  user-owned authentication/code entry pending; no raw credentials/tokens in chat.
  No firmware Flash/header/sign/package/commit/push/deploy/HTTP/TLS change;
  real readback/managed startup/Cloud recovery/physical power-loss/fulltask4 open.
  See [workflow and exact evidence](docs/settings-repairing-transition.md).

- Settings memory/controlled synthetic startup (2026-10-11): shared CRC/HEX/lock
  helpers at unchanged -O3; writesON host-only heap373280/margin4640 (+1984),
  default heap375360/bin491108.40 native/50 feature/build checks pass. Two
  read-only normal startup RAM loads select exact gen2/2561/CRC5A51424C,
  including partial inactive512-byte write cancelled after SDK scope retirement.
  Host15 command boundaries pass; physical power loss/in-flight AT reset/active
  managed Wi-Fi/Cloud restore NOT tested.158 USB pings max16ms, ToF advancing;
  owned synthetic files cleaned/absence proven, existing30 files retained.
  Exact unsigned7EE45958... final clean RAM, writesOFF/header9; runtime arena
  reserved357412/tail17948 (not live malloc/free-fragmentation proof). NCP recovery
  14.301s/retained-reference Wi-Fi2.584s, ToF387->429/UART165/165 zero errors;
  handles released, Cloud unpaired/legacy integrity UNKNOWN. No real migration/
  credentials/NOR/header/sign/package/HTTP/TLS/commit/push/deploy. Prior failures
  retained; real source/migration/physical durability/fulltask4 still open.
  See [contract and exact evidence](docs/unified-ncp-settings.md).

- Bounded settings actual-path follow-up (2026-10-11): immutable13250ms/15-command
  transaction, each SDK command<=2000ms with retired scope/yield/cancellation;
  complete32-file inventory accepts, overflow33 still rejects.39 native/50 feature/
  build checks pass. Synthetic-only RAM PASS: three2561-byte commits, exact CRCs,
  two-slot reload, cancelled partial blocks retry/keeps old active exact;143 USB
  pings max16ms, ToF advancing, owned cleanup/absence proven. Three prior reload
  FAILs and two temporary heap-guard FAILs retained; no existing30 files removed.
  Final clean unsigned4A33C963... RAM restored, writesOFF/header9, bin492452/
  heap374016; host-only writesON heap371296 (2656 margin). Legacy read still fails;
  NCP recovery14.362s/Wi-Fi retained-reference restore2.580s pass; Cloud unpaired.
  Final ToF386->428/UART165/165 zero errors, owned handles released. No real
  migration/credential/config/NOR/header/sign/package/commit/push/deploy or
  HTTP/TLS protocol change. Real cold managed-state/power-loss/connected Cloud/
  BLE hardware and task4 acceptance remain open. See [contract and exact evidence](docs/unified-ncp-settings.md).

- Synthetic NCP ASCII/HEX follow-up (2026-10-11): user-approved absent-name
  n6s_probe.cfg created/read/owned-cleaned; exact2561 bytes/CRC8D391A60,
  decoded1280/CRC1E7A6D24/five NULs,13 boundary reads PASS with independent
  original2s SDK operations. Three whole-budget variants FAILED (write896,
  read1024 after fullwrite,write2560); all cleanup absent verified/no probe fence.
  Product whole2s/128-slice maximum-record commit remains NOT accepted; no budget
  change. Temporary hooks removed and exact default3575B8A7... source/ELF restored
  and RAM-loaded, writesOFF/bin491732/heap373776/header9. Normal legacy1172 read
  still malformed2000ms/fence1; coordinated recovery14404ms PASS, public-only
  retained Wi-Fi intent restored/IP2855ms, no password/CWCRED/config write.
  Final ToF391->430/ready0/0/0/gen0, Wi-Fi IP/USB/radio ready/BLE adv-disconnected/
  imageNONE/Cloud unpaired; NCP1/1/0/SPI0/alloc0/UART165/165 zero drops/errors.
  Four native probe variants/builds +exact clean build pass; earlier38 native/
  50 feature unaffected, not rerun. Managed-record restoration/power-loss/Cloud/
  fulltask4 remain NOT RUN/BLOCKED; legacy integrity UNKNOWN. Separate validated
  complete-source/migration approval and budget acceptance still required.
  All handles released/no active test; no NOR/header/sign/package/commit/push/
  deployment. See docs/unified-ncp-settings.md and ignored ncp-ascii-probe-20261011.

- Unified NCP settings extension (2026-10-11): SSID/password (no enterprise
  username) +existing Cloud fields in static bounded schema; printable HEX/CRC,
  two alternating managed files, exact readback before publish, single2s scope.
  Existing owners/generations/fences/capacities retained; list lifetime/complete
  inventory proof tightened, blocked restore does not consume retries. Writes
  defaultOFF; no implicit CWCRED/legacy Cloud mutation or migration. Legacy-only/
  corrupt/unknown/future storage blocks writes; prior missing pairing bytes and
  integrity UNKNOWN remain. All38 native/50 feature/build pass; unsigned
  ELF3575B8A745AD42A62EC6B5B0E7284A94FB267C1764218BCF27660EC242035576,
  bin491732/heap373776/header9. Separate host-only write-enabled link heap371048
  (2408 above minimum); neither ELF RAM-loaded. Harness/sandbox failures retained
  and affected checks corrected. No active test/build or device operation. No
  actual FS fixture/credential/token write, provisioning/Flash/header/sign/package/
  HTTP/TLS/commit/push/deploy; hardware settings HIL NOT RUN. See
  docs/unified-ncp-settings.md and ignored unified-settings-20261011 evidence.

- Saved-pairing follow-up (2026-10-11): actual SPI framing passes158 synthetic
  cases plus three strict FS/parser/pairing regressions. No new proven host
  defect or firmware/RAM reload. Missing public payload upstream of host
  parser persists; integrity UNKNOWN. Need validated binary-safe NCP2.0.106
  logical read; independent CRC alone cannot load absent pairing bytes.
  No raw Flash/address guess/unlock/metadata AT query/credential exposure/
  re-pairing/config mutation/ST contact/separate FAE project change. Connected
  Cloud fault/restoration HIL BLOCKED/NOT RUN, not accepted. Final4D953D64...
  exact ELF unchanged: ToF114793->114834/ready/counters8/8/0/gen8, Wi-Fi IP,
  USB/radio ready/BLE adv-disconnected/imageNONE/Cloud unpaired;
  NCP3/3/0/SPI faults0/alloc0/UART7085/7085 zero drops/errors. Handles released,
  no test/build process. Initial native-harness newline failure retained then
  corrected. No new feature/build/fulltask4; header9/Flash/sign/package/HTTP/
  TLS/commit/push/deploy unchanged. See latest recovery doc and ignored
  cloud-fs-resume-20261011 evidence.

- Longer RAM campaign (2026-10-11): original7AC39D92... FAILED3807.187s,
  second profile final Wi-Fi gate;11324 CRC records/eight ToF recoveries/six
  pause gates passed. RF/AP/NCP disconnect cause unproven, no new NCP/SPI fault.
  Existing control owner now restores ordinary confirmed link loss with retained
  saved desired intent, max3 attempts/10s completion cooldown; user work/DHCP/
  unconfirmed state/true fence/DNS/BLE ownership defer. Explicit disconnect
  cancels intent. No healthy-NCP reset/new task/capacity/steady allocation;
  eight static bytes. Unsigned4D953D64... bin487952/heap383792/header9;
  33 native/24 feature/build-only pass, warm30CRC and ordinary restore143CRC
  pass without ToF/NCP counter changes. Host bare-data write failure retained;
  corrected hex RAM fixture requires scalar readback. Serial continuation of
  failed/remaining three30min blocks PASS5446.735s/16993CRC. With original
  first old-candidate profile: mixed7263.641s/22653CRC,16 ToF faults/12 pauses,
  four genuine NCP probes20011/19968/20000/20792ms, four USB reopens, three
  warm SRAM loads. Two no-reset ordinary Wi-Fi gates pass; unsolicited
  disconnect2174577 restored in2687ms association call without NCP reset,
  root cause unproven. Final ToF ready/advancing8/8/0/gen8, Wi-Fi IP,
  BLE adv/disconnected/imageNONE/Cloud unpaired, UART2021/2021 zero drops/errors;
  radio alloc/SPI faults0, Radio max gap269/BLEpump20820ms includes recovery.
  All owned COM6/COM8/debugger/supervisor/UART handles released; no active
  campaign. Ignored tof-endurance-20261011/continuation-1 verified-terminal-
  summary.json and audit-final.log. No full task4/active BLE CLI-DMA/Cloud return
  acceptance; no Flash/config/auth/header/sign/package/HTTP/TLS/commit/push/
  deployment. See current ToF recovery doc for terminal status.

- Bounded longer RAM validation (2026-10-11): unchanged exact7AC39D92... ELF,
  binary487440/heap384312/header9; prior32 native/24 feature/three build-only
  checks retained, not rerun without code changes. Three warm loads pass30 CRC
  records each. ToF734.938s/2100 CRC records passes Median/Box radius2, three20s
  pause gates (one latent XSHUT fault resumes into recovery) and four one-attempt
  recoveries344/272/272/380ms; counters4/4/0/gen4. NCP counters unchanged in profile.
  Separate genuine-fence NCP fault-test passes19749ms, Wi-Fi IP restored2652ms,
  143 CRC records/seven USB pings with no ToF recovery. Controlled fault != natural
  root-cause proof; active BLE CLI/DMA and Cloud return remain open. Official ST
  FLASH-R-HEX lead has unknown safe file mapping/lock permission/credential exclusion;
  no raw Flash/AT metadata query. P67W61-738 causal relevance unproven; storage
  integrity UNKNOWN, strict original bytes/CRC/2s/fence retained. Final ToF ready
  advancing1952->1991, Wi-Fi IP/USB/radio ready/BLE adv-disconnected/imageNONE/
  Cloud unpaired; UART615/615 zero drops/errors, all handles released. No firmware
  change/new steady allocation/Flash/config/auth/header/sign/package/HTTP/TLS/
  commit/push/deploy/full task4 endurance. Evidence ignored tof-longer-20261011;
  see latest ToF recovery doc and official FS lead in radio-coordinated-recovery.

- ToF warm startup/recovery follow-up (2026-10-10): acquisition owner quiesces
  I3C1/DMA0/1/2 before initial XSHUT; failed sensor boot uses existing max3
  recovery tries, first-fresh-frame proof, cached calibration/latest settings.
  Pause-timeout is intentional cancellation; real transfer failures recover.
  Verified PD8 XSHUT low50/high50ms through expansion level shifter, not rail
  power control. Initial readback candidate37733751 failed because IDR sampled
  immediately after BSRR; corrected settled readback/test, failed evidence kept.
  Final unsigned ELF7AC39D925C371A7B774A5CCA55E9EDAF41394739E95DC500E2C5FEC43252A8AA,
  binary487440/heap384312/header9;32 native/24 feature/all3 build-only pass.
  Two warm RAM boots pass; pause/resume/map-off no-reset gate and two real XSHUT
  fault recoveries316/267ms preserve Median/USB/depth. Corrected collector10
  baseline+40 fresh CRC records passes; first cross-counter-reset host assertion
  FAIL retained (40 valid records,4 draining+36 fresh). No new capacity/task/
  steady-state allocation;4-byte calibration flag. Original electrical/controller
  cause not isolated, broad endurance/persistent-fault/Stage11/BLE/Cloud HIL open.
  Cloud FS inquiry paused, no stored-corruption inference. No Flash/config/header/
  sign/package/HTTP/TLS/commit/push/deploy. See docs/tof-desired-state-recovery.md
  and ignored tof-warm-init-20261010 evidence. Final board ToF ready/advancing,
  Wi-Fi IP/USB/radio ready/BLE adv/imageNONE/Cloud unpaired; UART319/319 zero
  drops/errors. Existing approved volatile Wi-Fi intent restored in18703ms
  with21 USB pings and ToF continuity, no password or saved-data write. All
  COM6/COM8/debugger handles released; no physical power approval pending.

- Task3 FS boundary diagnosis (2026-10-10), supersedes stored-corruption claims:
  public offset5 (expected NUL0x00 in v1) received SPI peer_len13 = metadata11+
  CRLF2, no payload; copy_equal1, parser19 adds terminalOK6, no NUL removed by
  host parser. Upstream binary FS reply malformed; actual stored byte/CRC and
  NCP formatter/internal/electrical cause cannot be proven by this read channel.
  Prior inferred-NUL/full-tail audit CRC is NOT independent storage evidence.
  Removed empty-to-zero/string-tail/padding reconstruction. Strict exact binary
  read/original2s/full CRC, borrowed-pointer retirement, no fence clearing;
  empty+OK untouched output/error/fence, 32-bit length no65544-to8 wrap.
  Native SPI copy/collector tests all256 bytes/33 room boundaries; all31 files,
  feature16/build pass. ELF31010048FB2DCA41377E34FC702E6836F69EE8659C127B30F6A455BA07BB0B70,
  bin486632/heap385112/header9. Public probe recovery15977ms/advancing ToF passes;
  temporary probe removed. Final clean warm RAM ToF I3C startup FAIL/frame0;
  USB/radio ready/Wi-Fi IP/BLE adv/imageNONE/Cloud unpaired, handles released.
  Full physical power removal confirmation pending; RAM approval valid. Need
  independent NCP-local CRC/binary-safe read or ST FS2.0.106 implementation/
  validated encoding to distinguish storage/read, without credential disclosure.
  Do not infer stored corruption, repair config/re-pair or weaken CRC. No Flash,
  credential/config/auth write, HTTP/TLS, sign/package/commit/push/deploy/endurance.
  See latest recovery doc and ignored task3-fs-boundary-20261010 evidence.

- Task3 final legacy RAM follow-up (2026-10-10): second power cycle confirmed;
  NUL means value0x00 at file offset5, not offset0. Legacy reads complete330
  within original2s, valid magic/version/length/strings but CRC FAIL; actual ABI
  padding read does not fix it. Temporary on-device audit reads all842 tails:
  143 nonzero, full1172-byte CRC stillFAIL; values never exposed to host. File as
  returned by FS is invalid; original corruption/NCP internal cause unproven.
  Audit removed; exact final unsigned ELF
  39116974A8322069A7D0939EFBEC9171127BA09FE8CD0FA342F637E8A85B573F,
  binary486808/heap384952/header9; all30 native/16 feature/build pass.
  Focused genuine missing-response recovery19969ms passes, automatic saved-cred
  Wi-Fi IP,23 USB pings/38 BLE finals p95/max156ms/13 CRC images/UNKNOWN notice,
  advancing ToF. Notice active0; in-flight/DMA HIL open. Radio gap21ms but BLEpump
  gap19537ms includes recovery; SetConnParam status2 retained, allocations0.
  Cloud pairing FAIL; server images/restoration blocked, not accepted. No config,
  credentials/auth write/re-pair/Flash/header/sign/package/HTTP/TLS/commit/push/
  deployment or endurance. Final-board/handle evidence in recovery doc and ignored
  task3-cloud-legacy-20261010. Earlier not-loaded/blocked checkpoints historical.
  Final exact39116974... RAM reload healthy: ToF ready/advancing, Wi-Fi IP,
  BLE advertising/disconnected, imageNONE, Cloud unpaired; UART195/195 zero drops.
  COM6/COM8/BLE/debugger handles released; no board-availability approval pending.

- Task3 cold Cloud follow-up (2026-10-10): physical power removal restored ST-LINK
  and healthy ToF. The 256-byte sliced RAM read still failed (declared256,
  assembly26/copied0/2000ms/fence1); automatic AT_FENCED recovery15199ms passed
  with ToF continuing. Public magic/version probe proves omitted NUL in FS output;
  no host credential/payload inspection. Probe removed, failed evidence retained.
  Read-only legacy candidate reconstructs canonical zero tails/padding using
  one-byte reads; only complete empty+OK can decode NUL, original whole-record CRC
  and schema required, one original2s budget, no saved file/format/write change.
  Build binary486464/heap385304/header9, unsigned ELF
  1E4B968FE2A3EDAB913529EAD62A350B4042ABDBB21EB5573FCB1BD520997A47.
  All30 native files/16 feature compiles/build pass; candidate NOT RAM-loaded.
  Last probe warm reload ToF
  I3C error/frame0, Wi-Fi disconnected/Cloud unpaired, USB/radio ready/BLE adv,
  imageNONE. Host handles released. Second physical power-off/reconnect confirmation
  pending; existing RAM permission valid. ST-LINK enumeration currently works.
  Transient environment disconnect interrupted no active HIL/build. No Flash,
  credential/config/authentication write, re-pairing, HTTP/TLS change/sign/package/
  commit/push/deploy. See recovery doc and ignored task3-cloud-cold-20261010.

- Task 3 Cloud-startup investigation (2026-10-10): initial FS read TIMEOUT
  reproduced on diagnostic RAM ELF B6C38878DCC0A75D0AF4519E3F0EA5FDE03A04155FFC98AABE61E9046F180974.
  Scalar-only evidence: requested/declared 1172, two callbacks, assembly 27,
  copied 0, elapsed 2000 ms, fence 0. No credential values read by host or logged.
  Candidate uses 256-byte read slices under one original 2s budget, bounds
  payloads and retires borrowed FS output; unanswered submitted FS read fences,
  pre-write timeout does not. 30 native files/16 feature compiles/build pass.
  Candidate binary486216/heap385528/header9, ELF
  75525ECB0DC9D084CBE5F5BE756CF85977102114093BDD401B6A8A2F5F02FE69.
  Candidate NOT RAM-tested: next loader failed DEV_USB_COMM_ERR, also reproduced
  by read-only normal-access ST-LINK enumeration. Need full physical power-off
  and ST-LINK USB reconnect; existing focused RAM permission remains valid.
  No verified Cloud restoration or diagnosed cause of payload truncation yet.
  Board final diagnostic RAM: USB/radio ready, BLE advertising/disconnected,
  Wi-Fi disconnected, Cloud not paired, ToF I3C dynamic-address error after warm
  reload. All host handles released. Saved pairing/credentials and Flash/header
  unchanged; no provisioning, HTTP/TLS change, signing, commit/push/deploy.
  Current RAM also reports9 because the header was preserved, not because the
  changed candidate was installed into Flash. See recovery doc and ignored
  task3-cloud-20261010 evidence; do not override prior successful RAM checkpoint.

- Task 3 host follow-up (2026-10-10): existing uncommitted recovery reconciled
  against `ble`/d89a510. Old-parser BLE callbacks cannot resurrect link/CCCD/
  image route after the barrier; fresh init reconnect observations retained,
  RX/TX/reply admission closed until restoration completes. Slot-acquisition
  recovery/generation races roll back ownership; no old output relabeling.
  Uptime 0 uses lifecycle stage, not a timestamp sentinel, for one barrier and
  the original 35 s deadline. All 28 native files/16 feature compiles/build pass.
  Binary 485504/heap 386280/header 9; ELF
  DC3BC6DD3539E1BE51C4C2C42E5BC137321A604B858F75B5812BECC9D12E5928.
  User-approved focused RAM HIL now passes on this exact ELF: genuine missing
  AT response/fence, automatic Wi-Fi restore in 2665 ms, recovery 21104 ms,
  38 BLE finals (p95 172/max 203 ms), 25 USB pings, advancing ToF and actual
  UNKNOWN notice. BLE/USB/BLE route gate passes 5/5/5 CRC frames. Volatile RAM
  SSID/connection intent seeded after MCU reload, existing NCP credentials used;
  no password or credential write. Cloud started unpaired after FS read TIMEOUT,
  so current Cloud restoration is NOT validated. Notice had active_reply=0;
  in-flight CLI/DMA failure HIL remains open. WinRT sandbox failures retained;
  normal device access passes. UART 481/481, CLI RX/TX drops and allocations 0;
  SetConnParam status=2 observations retained, not zero-driver-error acceptance.
  Handles released, Wi-Fi IP/BLE advertising/image NONE. Not signed or installed.
  No capacity/budget/HTTP/TLS/IOC change, no new endurance run or Flash write.
  See docs/radio-coordinated-recovery.md for limitations and ignored evidence.

- Candidate F (2026-10-10): pre-HAL SPI5 IRQ/worker failure scalar snapshots,
  deferred Radio UART reporting and retained radio-status evidence. No ISR
  formatting, speed/DMA-priority change or capacity growth. Shared recovery
  retires BLE generation with UNKNOWN/no replay; next subscribed CLI receives
  an event through existing TX slots, with new input held through terminal
  drain. Binary updater excluded.27 native files/16 feature compiles pass.
  RAM F ELF4E18B7AA28B6C1E6B6CB80A6C0CC512EB37C583CF3C6AB9356440DE388363B14,
  package486496/NS485192/heap386568, Flash/header9. Focused F2 passes36 BLE
  finals/25 USB pings/five new Cloud frames and actual UNKNOWN notice after
  automatic Wi-Fi restore. F1 observer missed the notice on automatic Windows
  reconnection; failed report retained, both sessions observed in F2. Full-hour
  F profile started; raw checkpoints, received failed-command bytes/duration
  retained. No arbitrary100 Hz Radio CPU assertion. Natural SPI cause remains
  open; see docs/radio-coordinated-recovery.md. Older E checkpoints below retained.

- Shared-NCP recovery tasks3–4 (2026-10-10) IN_PROGRESS. See
  docs/radio-coordinated-recovery.md for current contract/evidence; older notes
  saying "not started" or "UI unpublished" are historical. Browser source pushed
  main, deployment unverified. Existing Radio/Cloud owners acknowledge; existing
  Wi-Fi/BLE control worker owns reset. Genuine fence/expired DNS only, not ordinary
  wait/BLE-only failure. Fail-closed stop proof before parser/context/buffer frees;
  no foreign mutex release, shared DMA reset, MCU reset or automatic partial-init
  retry. Cloud socket retired only after power-off/fresh-init proof. Pairing/output
  lease retained; old commands not replayed. User explicitly authorized ST67
  credential persistence: successful connection stores CWCREDADD, app password
  cleared, CWJAPS/Secured=1 restores desired SSID after NCP reset. Disconnect cancels
  intent; forget deletes credential. No password logging/history/app retention.
  No new task or payload capacity growth.25 regression files/feature16 pass.
  RAM E v10 package483904/NS482608/heap389344, Flash/header9. Missing-response
  injection restores Wi-Fi/Cloud automatically while USB/ToF live, ~21.8 s;
  Windows immediate GATT discovery failed and later57/57 BLE p95 1531 ms failed
  latency. Focused E4 subsequently passes with neutral WinRT address discovery:
  36 BLE finals/20 after reset,28 USB pings,5 Cloud frames in1719 ms; p95 219/max265.
  E3 failure was local Node receiver reading partial JSON and closing Hub (409);
  fixed host reader/atomic producer. These failures and C/D checkpoints remain;
  full acceptance not closed.30-minute combined profile now PASS:7726 BLE finals,
  1243 USB pings, p95 203/max3734,10 reconnects,3264 new CRC Cloud images,
  37 matching completions,300 ordered UART burst lines; no new reset or
  allocation/delivery drop. Clean/sign pass; exactly8 model compile-datetime
  bytes differ, instruction bytes unchanged (see both exact hashes in doc).
  One-hour failure profile first host run interrupted at743 s with no final
  report (INCOMPLETE, not PASS). Second run FAILED near48 minutes: SPI HAL
  transaction error, unresolved BLE notify, genuine AT fence; automatic NCP
  recovery15840 ms succeeded but one BLE PONG/final absent.12525 preceding BLE
  replies/2107 USB pings,10 connections/46 bursts. USB/ToF live; allocations and
  CLI RX/TX drops0. Host restored Wi-Fi/IP afterward. Next priority: capture SPI
  fault cause and explicit in-flight CLI failure across recovery, then rerun
  full hour. Raw checkpoints retained. No whole-chip CPU/worst-stack claim.

- Service availability / bounded CLI ownership (2026-10-10): tasks1–2 implemented.
  Public read-only available/waiting/fault plus timing/reason; UART/USB transitions,
  radio-dependent pre-dispatch rejection including password. Existing BLE8x768 /
  Cloud8x384 TX slots reserved before execution, print calls packed,128-byte final
  reserved, RX remainder retained, sticky write/format/encoding failure explicit.
  Cloud lease return/ACK/hold/publication retry/generation retirement preserved.
  Raw XMODEM excluded; initial BLE C proved single-byte; no firmware payload sent.
  Queue/pool/stack capacities unchanged; small metadata/code overhead documented.
  Native29 +two audits, driver regressions, feature16, browser6 +XMODEM8/build/lint
  pass. Initial451/451 +102 CRC BLE frames/max2500 ms; exact final149/149 +39 CRC
  frames, p95 187/max2797 ms, two warm Wi-Fi cycles. No RX/TX drops; Radio gap23 ms,
  UART180/180 zero drops/errors in concurrent snapshot. Full latency/endurance and
  older missing-reply failures remain OPEN. User explicitly approved saved-token
  use against the existing project Cloud endpoint; earlier approval block resolved.
  Live acceptance reproduced a real SPI RX allocation failure twice (including
  clean boot):1560-byte contiguous allocation failed with1820 total free; retained
  MTU TX followed by genuinely missing raw response/fence. Cloud now sends at most
  512 bytes per W6X_Net_Send, without changing pool/queue/stack or request budget.
  Also fixed ordinary input.completed retiring async Cloud Wi-Fi before its result:
  updater completion branch now requires update_was_active.37 actual-C +two audits
  and final feature16 pass. Final RAM139/139 BLE finals, p95 360/max2297 ms;
  Cloud6/6 matching server completions including async scan,414 CRC-valid received
  frames; two reconnects restore three frames in1406/4218 ms after IP. Zero radio
  allocations/RX-TX drops; UART416/416,12 service START/END pairs; final Radio gap88 ms.
  Cloud sample max9937 ms; earlier queued command13890 ms; full latency still OPEN.
  UI local, unpublished. Exact RAM10 ELF
  ECB783DA020BACC4D3E4AC55A97A22D34F9708AD4BDF4DC6EF411132D83D9769;
  ignored cli-service/candidate-cloud-final.elf, package478688/NS477392/heap394712.
  Previous candidate-exact.elf and failed live checkpoints retained. Final HIL
  test-workspace polling disabled/image route NONE; Wi-Fi remains connected,
  BLE advertising. Browser/COM/UART test handles released; no Flash installation.
  Exact follow-up: USB scan rejected before dispatch during WIFI_CONNECT at577 ms,
  local ping succeeded, service available after IP. UART257/257 no drops/errors,
  ToF ready/results7 routed no write errors;8 service START/END pairs. Whole-run
  Radio gap later266 ms after BLE teardown/control, not23 ms. Preserve this limit.
  Flash/header9. Tasks3 coordinated genuine-NCP recovery /4 endurance NOT STARTED.
  See docs/cli-service-backpressure.md; preserve all previous checkpoints below.

- UART debugging follow-up (2026-10-10): RX preemption reproduced END before
  queued PENDING; retain notice as captured request-timeout snapshot, not current
  ownership. DNS END adds explicit outcome=complete/failed/fenced; result=0 alone
  cannot imply recovery. No protocol/budget/capacity change or diagnostic RX lock.
  Native10 +Wi-Fi audit, notification13/raw21/admission13/budget/lifetime checks,
  feature16 pass; pre-fix failure retained. Trace-off follow-up14 paired waits,
  four reconnects actual images return1.1--1.7 s after IP. BLE411/411 then409/409,
  p95 187.5/203 ms, max2828/2672 ms; full latency/earlier reply-loss gates OPEN.
  RAM ELF10F8C7550385B9734362901FC328F7F3965A144EAD67A759A42988E34467268B;
  ignored radio-wait/debug-final/candidate.elf; package471744/NS470464/heap401688.
  RAM10, Flash/header9. Final UART257/257 zero drops/errors; Radio gap31 ms,
  allocations0; pool3440/37, fence/drainfalse, scan absent in live sample.
  No late/fault terminal induced on hardware; native evidence only. Metadata is
  non-atomic with active Cloud sockets, not quiescent retirement proof. Observed
  stacks Radio1652, control1500, Cloud3584, SPI308, parser916, not worst-case.
  Initial409 workspace inactive resolved by reopening saved Hub; final receiver
  closed after357 actual frames, workspace will back off until opened again.
  COM6/COM8/BLE released. Service-state/backpressure/reinit remain OPEN.

- UART wait diagnostics (2026-10-09), user requested: RADIO-WAIT START/END for
  DNS, Wi-Fi connect/disconnect and late BLE terminal drain. Elapsed milliseconds,
  result/fence/cancel; pending DNS diagnostic preserved. Formatting outside IRQ
  exclusion/SPI, via existing async UART. No per-retry flood; DNS diagnostic flag
  fits existing struct padding, deadlines/protocol fences/capacities unchanged.
  Native8 diagnostic +Wi-Fi audit, notification13 with duplicate-retirement checks,
  raw21/admission13/budget14+epoch/audits and feature16 pass. Trace-off target10
  paired transitions across2 RAM boots; final2 reconnects actual Cloud frames,
  USB responsive/ToF ready. Late/expiry diagnostic faults tested natively only.
  Exact final ELF EEB943E97AF4126833B48DE6D57962B8638A9A2A70446C97BD73FF2EE166E0F3;
  ignored radio-wait/candidate-v10-wait-final.elf, package471584/NS470296/heap401848.
  RAM10, Flash/header9; pool3440/37 fragments, no fence/drain/scratch in capture.
  Debug prefix HAL uptime; don't print RTOS ticks as the same absolute ms clock.
  User-approved public service states, CLI admission/reply backpressure and UI
  wait/error reporting are NEXT/OPEN. Diagnostics do not close those tasks or
  erase earlier failed latency/missing-reply/endurance/coordinated-reinit gates.

- Preceding 2026-10-09 RAM checkpoint: DNS replies at 6.610/6.744 seconds exceeded
  the 4500 ms request budget. Only scoped ordinary CIPDOMAIN may retain a
  read-only terminal drain up to the SDK's 20 s from write; no new AT until its
  terminal, drain expiry fences, true fences never clear on late replies.
  Persistent DNS descriptor/lifetime guard retires borrowed output pointers.
  Wi-Fi refresh defers during drain and retries once per second on every worker
  wake, preserving the last confirmed shadow. Connect call blocks fresh BLE
  announcements, while existing owners drain; original 100 ms budget unchanged.
  Guard candidate's phase-1 CIPSEND fence was FALSE: CWQAP advanced the Cloud
  epoch while it waited for AT, so no CIPSEND byte was written. An explicit
  TX-owner-only bus-attempt outcome now separates pre-write cancellation from
  ambiguous transmission. Never infer wire submission merely from TIMEOUT.
  Zero-byte bus BUSY is safe; partial writes/missing replies keep true fences.
  Latest six reconnects restored actual Cloud frames in 1.7--5.0 s, Radio gap
  23 ms, allocations zero; trace-on BLE FAILED 621/622, p95 312/max 9188 ms.
  Exclusive 20 BLE ->25 USB ->20 BLE CRC route PASS. Native raw21, admission13,
  budget/drain14, DNS lifetime/refresh4 plus audits and feature16 pass.
  Trace-off six further reconnects restored actual images in1.1--4.0 s, but BLE
  FAILED614/615, p95 297/max9219 ms. DNS shared-AT wait fills CLI8/8 slots, one
  output drop each run; don't enlarge queues/pool or admit text into an owned
  drain. Quiescent Cloud-disabled snapshot: all6 socketsFREE, invalidNCPid6,
  no OpenAttempted/credentials, fence/drainfalse, pool3440/fragments38. Observed
  stacks Radio1844/8192, control1732/6144, Cloud3592/8192, SPI308/768, parser1288/2048;
  not worst-case proof. Exact RAM ELF SHA DD1188A91DEC41A5CB8FE8BBF515B011E3D8A2C325061DD746652ED39452E0EE;
  ignored candidate-v10-cancel.elf, package471008/NS469704/heap402424. Pool/stacks/
  queues unchanged; Flash/source9. Full gates remain OPEN/FAILED. Preserve all older failed attempts;
  coordinated shared-NCP missing-reply recovery remains unimplemented.

- Earlier 2026-10-09 target checkpoint: the asynchronous candidate's three reassociation
  cycles delivered BLE 381/381, USB 115/115, 92 CRC images and Radio/BLE max
  22 ms, zero allocations; BLE p95 1469 ms/max 1610 ms FAIL remains. Cloud
  received 170 real images then warm reconnect FAILED: scoped DNS timeout
  4500 ms fenced AT, while USB/ToF stayed alive. Do not clear that fence or
  equate IP events with restored Cloud. Expected Begin/Poll/Cancel BUSY had
  flooded UART/fault counters; all four notification APIs now exclude BUSY
  only, with an actual-C regression preserving real errors/control BUSY.
  Corrected signed-only v10: package 470240, NS 468960, heap 403200, capacities
  unchanged. Native route/diagnostic 5 plus audit, feature 16 pass. Warm RAM
  reload reached radio/USB but ToF initial dynamic-address assignment failed;
  full power removal requested for image acceptance. Corrected ELF SHA-256
  C94B88C4C46F8DB8A1240E2CF4E145B56349944EC31544FA323F2D5C27927F20;
  preserved ignored candidate-v10-quiet.elf. Expired pairing-code 404 on that
  follow-up is host setup failure. Flash/source v9; all full gates remain open.

- User-prioritized AT transaction/Cloud recovery candidate (2026-10-08): Radio
  owns one asynchronous SDK 2.0.106 notification across Begin/Poll/Cancel, using
  existing source slots/snapshot and a distinct bit in the existing event group.
  The 100 ms execution budget remains; only a fully submitted payload can enter
  a bounded read-only 1000 ms terminal drain. This still-owned state is not an
  abandoned raw fence. Never clear a real fence on late replies/retries. Source
  generation/route cancellation precedes purge; packet length survives MTU change.
  Cloud loss epochs invalidate old requests even across a quick reconnect.
  Preserve failed-close descriptor ownership; retry CLOSING and prove remote
  absence before reuse. Confirm matching NCP receive-buffer size before skipping
  configuration; do not ignore genuine ERROR. Owner-specific 4500 ms request
  scope includes real DNS/open/send waits; cleanup has its separate 500 ms scope.
  New transaction/route/socket/budget checks and 16 feature compiles pass. Signed
  candidate v10 package 470112 bytes, NS 468808, C heap 403328, pool unchanged.
  Target HIL is pending DEV-boot preparation. No hardware programmed; Flash/
  tracked source v9. True missing-response coordinated reinit, all prior failed
  target gates and worst-stack/endurance remain open. See
  `docs/radio-transaction-cloud-recovery.md`; no Generate Code required.

- M5.3 association admission candidate (2026-10-08): the vendor CONNECTED
  callback slept 100 ms in Modem_Process, starving pending BLE raw replies.
  Keep RX runnable: publish the same settling interval as AT admission state.
  Ordinary commands consume their original budget; BLE returns BUSY before
  writing. A raced guarded admission cannot create a false raw fence. Never
  change the 100 ms BLE budget or clear a genuinely unfinished raw fence.
  Association checks 11, raw checks 20, scan checks 16, ownership checks 13 and
  feature-mode checks 16 passed. Final RAM binary 464824 bytes, C heap 407392;
  radio pool/queues/stacks unchanged, Flash/source v9. Four target association
  cycles across 70 s trace-on and 150 s trace-off probes: 325/325 +694/694 BLE
  replies, 68 +155 CRC frames; USB 57/57 +112/112, p95/max 16 ms, Radio maxima
  31/60 ms. BLE maxima 4234/2125 ms remain recorded, not a worst-latency PASS.
  Earlier candidate FAIL persists: 55 missing replies after a terminal SEND OK
  arrived ~136 ms after payload, beyond the 100 ms budget, before reassociation.
  Moving the callback delay is not proof that all late-reply faults are fixed.
  Cloud return also FAILED after repeated reassociation: NCP accepts DNS/TCP
  options then rejects CIPRECVBUF; Cloud transport -14, worker max 7158 ms.
  Do not equate IP readiness or continued BLE/USB with restored Cloud images.
  Final exclusive route repeat FAILED too: 12 CRC-valid BLE frames, then raw
  phase 4 timed out at HAL 164817, bytes 132/132, 10 ticks, without reassociation.
  HOTPLUG: fence=true, pool free 3448/fragments 39, no scan scratch, allocations
  zero. The older route PASS does not override this failure; safe late/missing
  terminal completion is the immediate next M5.3 requirement.
  SPI terminal diagnostics capture two atomic scalars only on exact fixed
  terminal records; formatting stays in the parser. An initial formatted SPI
  trace caused STKOF on the 768-byte SPI stack and was removed; preserve that
  failed attempt. Capture helper compiler frame is 8 bytes; observed sentinel
  use SPI 308/768, parser 1288/2048, control 1740/6144, Cloud 3436/8192, not
  worst-case guarantees. Next: safe late/missing raw completion and Cloud
  socket/opening recovery; full M5.3/M5.4 remains OPEN/FAILED. Evidence uses
  `assoc-*` and `prompt-wire-*` in the ignored radio-stability directory.
  Final proper RAM reload of the same byte-identical tested candidate restored
  Wi-Fi/Cloud images: seven newly received frames verified, ToF ready, Radio/BLE
  maxima 21/21 ms, zero allocations; HOTPLUG fence=false, pool 3448/fragments 38,
  no scan scratch. This clean restart does not accept warm recovery or the failed
  route gate. Release host handles after final captures; Flash remains v9.

- M5.3 async BLE control candidate (2026-10-08): existing Wi-Fi control worker
  executes runtime BLE MTU/connparam/disconnect/ADV/probe/recovery through one
  by-value mailbox. Shared existing event, same 6144-byte stack, no queue/pool
  increase. Generation and advertising revision reject stale jobs/results; GATT
  recovery publishes local output for atomic Radio application. Wi-Fi result
  backpressure services BLE work in one-tick wait slices. BUSY preserves intent.
  Ownership 13 and feature-mode 16 checks passed. Connected Cloud toggles: BLE
  532/532, p95 203 ms, max 2485 ms, Radio/BLE gap 50/51 ms; USB 94/94. Exclusive
  20 BLE +25 USB +20 BLE CRC route passed. Forced Wi-Fi reconnect FAILED: BLE
  163/247 (84 missing), USB 108/108 p95 16 ms, Radio/BLE gap 120/115 ms,
  allocation failures zero. Raw prompt missing at HAL 572010 (phase 2, 0/244
  bytes, 10 ticks) retained AT fence. Exact-ELF HOTPLUG free=3448/fragments=39,
  no scan scratch, fence=true. Do not clear fence, resize pool/increase timeout
  or claim whole M5.3/M5.4 acceptance. Next investigate association/raw-prompt
  cause and safe recovery; bound Cloud opening work separately. Flash/source v9.
  `radio status` shows queue/call timing; vendor queries log scalar AT wait/held
  ticks. Ignored evidence uses `control-*`. Older checkpoints remain historical.

- Diagnostic RAM validation on 2026-10-08 captured `TX_NO_MEMORY` (0x10): RX
  requested 1560 bytes with only 916 available. Exact-ELF HOTPLUG metadata found
  retained TX len/cap 1528, empty SPI queues, seven copied AP results and the
  driver's retained 920-byte scan scratch. Cleanup alone failed because scan
  allocation occurred while a raw Cloud sender held AT. `w61_at_wifi.c` now
  acquires budgeted AT admission before scratch allocation, holds it through
  terminal response and SCAN_DONE delivery, then returns storage to the same
  64 KiB pool. Borrowed result lifetime is documented in W61/W6X headers; the
  application callback already copies all required fields. Parser-locked
  ambiguous-failure cleanup preserves an AT fence; if the parser cannot be
  acquired within the deadline, do not free its buffer. `w6x_wifi.c` initializes
  callback status before dispatch rather than exposing a previous failure.
  Sixteen native scan checks passed. After full power cycle, ten successful scans
  accompanied 120 actual Cloud frames; three bounded Cloud off/on transitions
  restored reception, allocation failures stayed zero and HOTPLUG metadata
  confirmed scratch release. Preserve the earlier zero-image warm-init failure
  as a failed attempt, not PASS. Flash/source v9.
  Do not enlarge queues/stacks/pool or clear a raw fence to make the test pass.

- Redacted NCP traces then exposed BLE's actual OK -> prompt -> Recv -> SEND OK
  protocol. Initial OK must not release raw ownership or count as payload
  completion. `w61_at_common.c/.h` and `w61_at_api.h` preserve fast ERROR before
  submission returns, wake prompt wait on rejection, track payload phase, and
  register SEND OK/SEND FAIL only for BLE's terminal-response flow. Preserve
  Recv-length error through SEND OK; retain true missing-response fences and
  the existing 100 ms BLE execution budget. Sixteen actual-C raw checks pass.
  Initial target repeat received 33 CRC-valid images and 138/138 replies; scan
  response pause (~3 s) remains. Signed-only v10 is 463968 bytes, not installed.
  Trace-off combined 120 s received 101 images and 367/367 replies, but p95
  391 ms failed the 250 ms gate. Two route repeats passed BLE->USB->BLE plus
  stopped Cloud counter; retain the first intermittent callback-silence FAIL.
  The HIL route collector now retains IDs/counts before assertions without
  weakening acceptance. Final HOTPLUG pool=3412, scan scratch absent, fence=false.
  Final Cloud re-enable missed 20 s after FS/DNS/query timeouts, then recovered
  without RESET. Radio/BLE lifetime max=2020 ms, Cloud max step=20234 ms. Preserve
  this FAIL; bounded health-probe admission and FS/DNS recovery remain open.
  The task plan now has a current status table and explicit next M5.3 substep:
  remove shared-AT waiting from BLE health/reconcile calls, preserving transaction
  ownership and generation; audit other synchronous Radio calls as well. Source
  confirms 2000 ms query waits and DNS's 20000 ms opening budget preceding the
  4500 ms HTTP deadline. BUSY is deferred work, not a false mode/link failure.
  M5.4 latency remains FAILED; M5.5 end-to-end request budget is not implemented.
  Detailed evidence: `docs/radio-stability-20261008.md`. No global acceptance.

- The 2026-10-08 Flash-v9 radio probes received all BLE PONGs and complete
  CRC-valid images, but repeated 3.1--3.4 s BLE response pauses around Wi-Fi
  scanning. Expected notification BUSY is now excluded from generic fault
  logging/counting; existing stream contention counters/retry ownership remain.
  The generic modem command path logs scan-only TX-lock wait/held ticks without
  AT arguments. Initial package-only v10 preceded RAM validation; the later
  full-cycle and BLE checkpoints above supersede that pending state. Flash/
  tracked version remains 9. No IOC/capacity change.
  Post-probe Cloud disable/enable then reproduced `No mem for rxbuf`, retained
  TX retry exhaustion and raw terminal-response timeout/fence. The candidate
  records only scalar allocation-failure metadata in `freertos_compat.c/.h`,
  printed by `radio status`; no formatting is added to the SPI allocator path.
  Prioritize packet ownership/budget and failure-time counts, not pool resizing.
  See `docs/radio-stability-20261008.md`; do not claim global radio acceptance.

- The 2026-10-07 Cloud OTA recovery candidate adds `inputSequence` to binary
  output slots and a bounded output-drain callback before Cloud update reset
  (one-second grace plus at most 30 seconds). USB/BLE keep their original reset
  timing. Do not resize queues/stacks or change the Secure A/B installer for
  this fix. `hil_tests/test_firmware_update_drain.py` runs the actual updater/
  XMODEM parser with mocked Secure/HAL boundaries. The deployed browser/server
  retries timed-out blocks, deduplicates re-broadcast output and cancels cleanly.
  Two partial hardware uploads passed cancellation and lost-ACK recovery; one
  also recovered from an ST67 SPI RX HAL error. On 2026-10-08, BOOT1 was confirmed
  at 1-2 and fixed v8 was installed/boot-confirmed via USB. Full Cloud v8-to-v9
  then passed: 452 blocks, EOT ACK, automatic Flash boot and USB version 9 plus
  Secure boot confirmation; zero sender timeouts. The board/source now use v9.
  Wi-Fi/pairing were manually restored after reset; fresh Cloud frames and CLI
  version 9 were verified. This OTA PASS does not close Stage 11/ToF endurance
  or BLE gates. See `docs/cloud-update-20261007.md` before continuing.

- FSBL, Secure, and Non-Secure boot from external NOR.
- The ST-LINK diagnostic UART works on USART1, PE5/PE6, at 115200 baud.
- The VL53L9CX initializes and returns complete 54×42 frames.
- The CDC sensor-map explorer exposes five numbered VL53L9 transform outputs:
  1 depth, 2 amplitude, 3 ambient, 4 reflectance, and 5 confidence. During
  `MAP ON`, keys `1..5` independently toggle channels; enabled channels rotate
  one complete identified image per sensor frame. The downstream map envelope
  carries frame ID and channel ID. Depth is retained every frame for the NPU,
  while all non-depth outputs reuse the depth-processing 54x42 float workspace
  and are copied only when selected. An auxiliary CDC map must be rendered
  before that workspace is reused for an SPI depth filter. Preserve this
  bounded-memory design and the
  existing N6DF v3 format until a synchronized multi-channel dataset revision
  is designed explicitly. This channel explorer is build-verified but not yet
  validated on hardware.
- The VL53L9CX runs as a 100 ms autonomous stream. A priority-7 acquisition
  task and priority-10 processing task exchange pointers to three fixed
  14,842-byte raw-frame objects from a static DMA-safe pool, so the next DMA
  acquisition overlaps transform/rendering without copying raw frames between
  tasks.
- The displayed depth map has an allocation-free, table-driven processing
  stage with Off, Box, Median, Gaussian, Sharpen, Min, Max, cumulative
  `OBJECT 1..7` teaching views, and `NPU`. OBJECT 7 is an adjustable
  normalized-depth binary threshold (0..255, default 210) used to inspect arm
  removal. Hardware testing promoted 210 to the fixed NPU and host preprocessing
  contract; later interactive OBJECT 7 changes must not alter production until
  explicitly promoted in both implementations. The final NPU path accepts only a
  non-trivial nearest component in 100..600 mm, produces black when none exists,
  grows the near seed through 8-neighbors whose local depth jump is at most
  120 mm, adds a four-source-pixel crop margin and guarantees another
  four-pixel border in the 64x50 model canvas even at a sensor edge,
  resizes the normalized crop to a centered 64x50 image, then maps every
  non-zero pixel to 255 and applies one 3x3 dilation to repair thin sensor
  dropout stripes. The empty image remains completely black.
  CDC preserves only the requested teaching snapshot plus the exact NPU input
  before Neural-ART reuses its activation arena; resize, binary dilation, and
  the NPU-input copy use Cortex-M55 Helium/MVE. The SPI display intentionally stays on its 54x42
  depth path in these modes.
  One fixed 54x42 float workspace supports filtering; settings are changed
  through `MAP PROCESSING` and are snapshotted before each displayed frame.
- `DATASET STREAM ON` emits N6DF v3 records. Each record contains raw 54x42
  uint16 millimetres plus the exact frame-matched 64x50 uint8 tensor preserved
  before NPU inference, with independent raw/model CRC32 values and a header
  CRC. Capture must compare all 3,200 device bytes with Python before saving;
  Stage 04 normally trains from the stored device tensor and refuses samples
  without it unless `--allow-host-preprocessing` is explicit.
- `training/VIEW_LIVE.bat` is the full-rate diagnostic display. It decodes the
  raw and model width/height fields already carried by N6DF v3, validates the
  complete record and CRCs, then atomically swaps complete Tk bitmaps. It may
  discard older complete frames for latency but must never display a partial
  frame. ANSI `MAP ON` remains useful for a terminal but cannot offer atomic
  row rendering.
- Before every Neural-ART inference, clean the 3,200-byte preallocated SRAM5
  input range from the Cortex-M55 D-cache. STEdgeAI's first CPU epoch
  invalidates that range; omitting the preceding clean discards the newly
  copied tensor and makes every inference observe the old all-zero image.
- The Keras reference model must expose a float32 input in the original 0..255
  pixel domain. Stage 06 must turn it into a genuine uint8 TFLite boundary with
  scale 1 and zero-point 0 and must reject any input CAST. A Keras uint8 input
  leaves an internal UINT8-to-FLOAT Cast which STEdgeAI 4.0 expands in-place
  from 3,200 to 12,800 bytes; zero input appears correct, while non-zero pixels
  are overwritten and Neural-ART diverges completely from host TFLite.
- Stage 11 HIL must exercise a moving hand, require non-empty and distinct model
  tensors, and compare their frame-matched raw scores. An all-black stream is
  not sufficient evidence even when host and Neural-ART agree exactly.
- The final Cloud-integrated SRAM image passed Stage 11 on 2026-09-19 with 100
  CRC-valid distinct frames, 100/100 frame-matched NPU results, bit-exact host
  preprocessing, 30 distinct model tensors, 100% class/decision agreement, a
  maximum raw-score delta of 6, and zero NPU errors. Radio preflight also found
  SDK 2.0.106, 11 Wi-Fi networks, and the expected BLE advertisement. External
  Flash was not changed.
- The USB CDC CLI has allocation-free Tab completion generated from command and
  filter descriptor tables plus a fixed 16-entry Up/Down command history.
- The steady-state sensor path uses PD9 falling-edge EXTI and I3C TX/RX DMA.
  Tasks wait on ThreadX event flags posted from HAL callbacks; initialization
  remains allowed to use blocking vendor calls.
- The 2026-07-31 signed build was programmed and verified in external NOR. The
  user confirmed successful external-Flash boot, VL53L9CX operation, USB CDC,
  and terminal output with the hardened static RX/TX and diagnostic paths.
- Treat that result as a functional hardware checkpoint, not as proof of a
  multi-hour soak, repeated attach/detach endurance, or deliberate fault
  injection into every recovery branch.
- Non-Secure Debug C and C++ use `-O3` with `-g3` debug information.
- The ToF processing task uses a 96 KiB stack, acquisition uses 16 KiB, and the
  ThreadX application pool is 134 KiB in the current Wi-Fi/Cloud build (151 KiB
  for radio/BLE only and 159 KiB with radio disabled).
  The largest visible active optimized chain is about 34 KiB; the much larger
  slow rate-normalization and resize functions shown in `.su` are bypassed by
  `fast_mode` and native 54×42 operation.
- The USBX device-control task currently uses a conservative 16 KiB stack. Its
  parent ThreadX byte pool is 56 KiB and contains the 32 KiB USBX system arena,
  the control-task stack, bookkeeping, and about 8 KiB of free headroom.
- The demonstrated USB stack overflow was in the USB-PD CAD task, not the USBX task.
- The USB-PD CAD task uses an 8 KiB stack and a 16 KiB pool.
- CN8 Type-C attachment is now detected correctly on CC2 and reaches the USB Device START notification path.
- The generated PCD MSP code is supplemented, inside USER CODE, by the reset/PHY sequence from ST's official NUCLEO-N657X0-Q CDC example.
- The FSBL enables VDDA, VDDIO2 through VDDIO5, and VDDUSB before `HAL_Init()`, matching the official CDC example.
- USBX now waits for a real CAD attach notification. The earlier CAD-independent fixed START is no longer active.
- USB CDC works: Windows creates a separate host-assigned COM port and complete
  ANSI-map transfers have been observed. Never assume a fixed COM number.
- USB CDC uses one priority-8 lifecycle manager and priority-9 RX/TX workers.
  USBX callback transmission mode owns bulk OUT reception; the RX callback
  publishes fixed 512-byte slots. Only the TX scheduler submits
  `write_with_callback`, and it waits for a completion semaphore before the
  next submission.
- The CDC steady-state path performs no allocation. Storage is fixed: eight
  768-byte control TX slots, two 48 KiB map TX slots, and sixteen 512-byte RX
  slots. All slots are session-tagged and passed through bounded pointer queues.
- The user has confirmed the ST67 shield and SPI/AT identity path on hardware.
  `APP_ST67W6X_ENABLED=1U` and `APP_ST67W6X_BLE_GATT_ENABLED=1U` now register
  and advertise separate CLI and DEBUG UART-like GATT services.
  `APP_ST67W6X_WIFI_SERVICES_ENABLED=1U` enables the Wi-Fi station and DHCP/IP
  query path. USB CDC, BLE and Cloud use the same command table, including
  bounded network scan, hidden password entry, connect/disconnect, update and
  reboot. This equality is an intentional demo policy. BLE maintenance remains
  in the Radio Manager, while high-level Wi-Fi scan/connect/disconnect calls are
  serialized by the dedicated priority-11 Wi-Fi control worker. `wifi scan`,
  `wifi connect`, and `wifi disconnect [forget]` are submission-only and return
  a routed request ID. M3.9 routes bounded result snapshots only to a matching
  live transport/generation, counts stale results, and suppresses text during
  XMODEM. M3.8 was explicitly authorized despite the open M3.7 BLE
  repeatability failure, so
  neither M3.7 nor the Milestone 3 gate is accepted. Physical
  SRAM HIL on 2026-09-19 passed scan, hidden-password association, DHCP/IP
  reporting, and a connected rescan while ToF/NPU and BLE advertising remained
  healthy; the SRAM4 radio pool retained 21,056 bytes. `help`, `menu`, and `?`
  print the complete shared CLI in bounded sections and document BLE/Cloud
  Write/Notify/text/binary modes.
  Physical SRAM HIL received all 1,840 explicit help bytes over USB and repeated
  the command over BLE at MTU 247; 16 BLE CLI messages/4,044 bytes (initial menu
  plus explicit help) completed with zero drops, retries, stale generations, or
  errors. The
  bounded stream layer now queues CLI RX, provides CLI/DEBUG TX queues and
  fragments notifications to `MTU-3`; DEBUG RX is still rejected by policy.
  Treat malformed direct-event input and SPI handshake loss as scheduling-
  safety boundaries. The vendored direct parser now drops/scrubs malformed
  records, partial `+BLE:GATTWRITE` numeric fields return `-EAGAIN`, and a raw
  bus write that cannot advance exits through the common transmit-lock release
  path. Repeated HIL observed clean boots where BLE connected but an initial
  reply was lost, with intermittent SPI transaction-ready/I/O faults while
  application threads remained alive. Targeted SPI recovery now bounds retries
  and handles a lost ready edge, but five consecutive clean-boot BLE/USB probes
  did not pass; do not claim M3.7 BLE acceptance.
  BLE CLI RX/TX is attached to its own SRAM4 parser/editor/history/output
  session, allocated only after the vendor radio reaches READY. Signed XMODEM
  may enter raw mode on that session and must reuse the Secure A/B installer.
  Stage 11 now disconnects stale BLE clients and explicitly restarts advertising
  before the external UUID scan. VL53L9 runtime command completion uses a DMA
  one-byte status read with a persistent destination and a 100 ms command
  bound. Never reuse the single async descriptor until I3C and every DMA
  handle are idle, even if the I3C TX event has already been posted.
  The CLI service also owns one Notify-only ToF image characteristic with a
  20-byte frame/offset/dimensions/channel/format/CRC header and a single 9,072-
  byte snapshot. DEBUG RX remains detached. ToF pixels alone use a dedicated
  media channel; command parsing and signed update remain shared.
- The ST67 transport uses an unusual active-high PA3 chip select; its safe idle
  level is LOW. CHIP_EN and BOOT also remain LOW until deliberate bring-up.
  When the radio build is enabled, PE9/SPI_RDY owns both edges of EXTI9 and the
  ToF acquisition task uses bounded one-tick polling of PD9. When disabled,
  PD9 remains the event-driven falling-edge EXTI source.
- The GC9A01 display is enabled. `N6.ioc` now reserves a dedicated SPI4 path:
  PE12 SCK, PE14 MOSI, PE13 CS, PE1 DC, and PE2 RST. SPI4 TX uses
  GPDMA1 channel 5 at an initial 12.5 Mbit/s. The generated initialization and
  hand-written display port use this mapping. User hardware validation on
  2026-09-13 confirmed that the display still operates after the SPI4
  migration. VCC is 3.3 V and no MISO connection is required.
- The priority-8 GC9A01 task uses SPI TX DMA and waits on callback-posted
  ThreadX event flags. It clears the panel, renders `SYSTEM IS LOADING`, and
  then consumes numbered ToF frames through one shared 404-byte DMA row
  buffer. Every submitted frame includes the frame-matched RPS status snapshot;
  the task renders `NOTHING`, `ROCK`, `PAPER`, or `SCISSORS` below the map and
  records both rendered frame IDs in `Display_App_Status_t`. Non-visual SRAM
  HIL on 2026-08-23 observed ToF/display frame 356, `NOTHING` at 921/1000,
  38 submitted/38 rendered, and zero errors.
- `MAP ON` identifies the active sensor channel, lists the enabled channel IDs,
  and appends the current frame's prominent NPU summary and all four raw int8
  scores to the CDC ANSI map. `MAP ON SCREEN` and `MAP ON DISPLAY` are
  aliases for the SPI display path; `MAP OFF SCREEN|DISPLAY` clears its map and
  result area. Preserve the single status snapshot shared by both consumers so
  neither UI can accidentally label a newer or older frame.
- Authenticated Non-Secure firmware installation is implemented and build-
  verified: CN8 USB CDC and BLE CLI XMODEM feed the same transport-independent
  Secure byte-array service, which writes the inactive A/B slot and uses
  pending/trial/confirmed metadata with rollback. CDC has completed one physical
  signed installation; physical BLE transfer and fault testing remain pending.
- Use `Tools/Debug-NonSecureRam.ps1 -Run` as the default agent loop for RAM
  development. With BOOT0=1-2 and BOOT1=2-3 (DEV boot), it incrementally builds
  Secure and Non-Secure (unchanged targets remain no-ops), loads the existing
  FSBL ELF into SRAM, lets that FSBL reach Secure from Flash, replaces Secure
  with the local SRAM1 binary, then replaces Non-Secure through the SRAM2 Secure
  alias before vectors are cached. Both vector tables are checked. It does not
  sign, program Flash, or change the firmware version. The local-Secure/NPU
  form is hardware-verified through ThreadX, VL53L9 acquisition, and
  Neural-ART initialization from SRAM.
- Use `Tools/Install-NonSecureUpdate.ps1 -FirmwareVersion <current+1>` only
  after RAM debugging is complete and a persistent final Non-Secure candidate
  is intended. It signs only Non-Secure, creates `.n6fw`, sends XMODEM over the
  auto-detected CN8 CDC port, and checks the running version after reset. It
  never chooses a version automatically. Physical automated transfer testing
  is still pending.
- `training/08_INTEGRATE_MODEL.bat` embeds the exact STEdgeAI raw weights in the
  signed Non-Secure image and copies them to NPU SRAM6 at runtime. Do not split
  weights into an unversioned external blob: `.n6fw` v1 A/B atomicity depends
  on code and weights remaining one signed image.
- The 2026-08-28 preprocessing contract changed the NPU input to a 100..600 mm
  locally grown, aggressively filled binary silhouette and invalidated the
  currently embedded model's accuracy
  claim. Do not call a regenerated classifier matched until stages 04 through
  08 prepare, train, quantize, generate and integrate it, followed by a passing
  frame-exact Stage 11 HIL on the new weights.
- When relocating STEdgeAI's default xSPI2 initializer pool to NPU SRAM6, Stage
  08 must also change every weight DMA descriptor from cacheable to
  non-cacheable. Address-only relocation causes a BUSIF1 fault on the first
  inference and can masquerade as a CN8 USB enumeration failure because the
  LL_ATON assertion stops the complete firmware.
- Run `training/09_BOOTSTRAP_NPU_SWD.bat` once per board before a persistent
  NPU release. It programs only FSBL + Secure and preserves both app slots and
  boot metadata. The guided Stage 12 release refuses to proceed until that
  bootstrap and a matching frame-exact Stage 11 HIL are recorded.
- Use `training/13_FACTORY_PROVISION.bat` only for a blank board or an explicit
  factory reset. It requires `ERASE ALL`, destroys both A/B slots and metadata,
  programs/verifies the complete boot chain, and verifies the running version
  over CN8. Ordinary releases must keep using the inactive-slot Stage 12 lane.
- Factory builds must produce `FlashImages/factory-manifest.json`. Preserve the
  `-SkipBuild` pre-erase checks that require the source version and SHA-256 of
  all four factory images to match that manifest. Never bypass this stale-image
  guard. CN8 discovery intentionally falls back to the Windows USB registry
  when WMI/CIM device enumeration is denied.
- A blank board that also needs ST67 NCP provisioning must run
  `radio_firmware/01_UPDATE_MODULE.bat` before factory provisioning. The ST67
  updater temporarily replaces the external-NOR FSBL and must complete its
  restore path before any other programming action.
- The upper SRAM3 window `0x24244000..0x2426FFFF` is reserved by the Non-Secure
  linker for CDC/RPS transient storage. Current Neural-ART activations are in
  SRAM5 and weights are in SRAM6. Stage 08 must reject generated networks that
  use SRAM3; never remove this collision check to make a model fit.
- The application ThreadX pool and Cloud CLI session are linked as NOLOAD data
  at `0x24280000..0x242BFFFF` in otherwise-unused SRAM4. This preserves the
  contiguous SRAM2 C heap for VL53L9 as Cloud code grows. A radio-enabled build
  also reserves a separate 64 KiB ThreadX byte pool at
  `0x242D0000..0x242DFFFF` in SRAM4 and reduces the general application pool
  from 159 KiB to 134 KiB with Wi-Fi enabled (151 KiB for radio/BLE only). The
  fixed application stacks consume 130 KiB, leaving about 4 KiB before allocator
  overhead in the Wi-Fi build. The Cloud worker's static 8 KiB stack is outside
  both byte pools. Radio Manager and ST compatibility allocations use the
  separate radio pool. Stage 08 rejects all SRAM4 model placement, the linker asserts
  the pool bounds, and the build-map preflight validates the address and size.
  The 2026-10-04 M5/SPI-recovery build leaves 420,368 bytes of C heap.
  Both transient 9,072-byte ToF float frames are now in the
  explicitly cleared SRAM3 workspace, which uses its complete 180,224 bytes.
  BLE queues, its CLI session and its additional single 9,072-byte ToF snapshot
  belong in the SRAM4 radio pool; runtime high-water validation remains
  mandatory.
- Secure update `Begin` must not erase the complete inactive slot synchronously:
  XMODEM cannot ACK the manifest block while that long operation is in progress.
  The writer erases authenticated image storage lazily in 64 KiB sectors before
  first use; interrupted transfers must still leave the active slot and metadata
  untouched.
- Keep the initial XMODEM CRC-request window long enough for manual file
  selection. It is 120 one-second `C` requests; a short 16-second window was not
  usable for a terminal-driven update flow.
- Secure SysTick stays suspended while NonSecure owns the CPU. Every firmware
  update NSC wrapper must resume it before calling crypto/ExtMem HAL operations
  and suspend it again before returning; otherwise HAL timeout loops become
  unbounded when PKA or XSPI does not complete.
- LRun must leave XSPI2 memory-mapped mode before jumping to Secure. Secure owns
  the controller afterward and reinitializes it for indirect update writes.
  If updater initialization fails, update APIs stay unavailable but normal boot
  continues with a stage code on COM6.
- BLE XMODEM must continue to reuse the Secure installer and must not access
  XSPI2 or boot metadata directly. Wi-Fi delivery is not implemented.

## 3. CubeMX rules

1. project/N6.ioc is the source of truth for CubeMX configuration.
2. An agent may edit the IOC when required.
3. Do not pretend to operate the CubeMX GUI for the user. After changing the IOC, ask the user to run Generate Code.
4. State clearly whether Generate Code is required.
5. After generation, inspect relevant files because CubeMX may overwrite manual changes.
6. Prefer USER CODE blocks whenever possible.
7. KeepUserCode does not protect assembly files, arbitrary middleware files, or manual edits outside protected blocks.
8. Do not run Generate Code merely because a C source file changed.
9. Verify that the AppliNonSecure `.cproject` include paths and `.project`
   linked resources still point to `ThirdParty/ST67W6X_Network_Driver` after
   generation. Do not restore references to an ignored local SDK package.

### 3.1 Known CubeMX-managed changes outside USER CODE

These require explicit review after every Generate Code:

| File | Manual change |
|---|---|
| AppliNonSecure/USBPD/App/usbpd_dpm_core.c | OS_CAD_STACK_SIZE maps to N6_USBPD_CAD_STACK_SIZE |
| AppliNonSecure/USBPD/App/usbpd_dpm_core.c | UCPD register diagnostics, wake counter, and 250 ms polling fallback |
| AppliNonSecure/Core/Startup/startup_stm32n657x0hxq.s | Early Debug_UART_StartupTrace calls |
| FSBL/Core/Src/extmem.c | Exact image-size and dynamic Non-Secure source hooks |
| FSBL/Middlewares/ST/STM32_ExtMem_Manager/boot/stm32_boot_lrun.c/.h | Dynamic A/B source and pre-jump XSPI handover hook; functional vendor edits outside USER blocks |
| AppliSecure/Core/Src/main.c | Diagnostic trace plus Neural-ART clocks, RIF/RISAF, CACHEAXI, and NPU interrupt ownership |
| AppliSecure/Core/Inc/partition_stm32n657xx.h | SAU region 1 extends through `0x243FFFFF` so Non-Secure can access SRAM2, NPU SRAM3-6, and CACHEAXI RAM |
| ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.c | The high-priority SPI worker sleeps one tick after each eight-packet continuous burst so a stuck-high SPI_RDY cannot starve ThreadX; re-importing X-CUBE can overwrite it |
| Drivers/STM32N6xx_HAL_Driver/Inc/stm32n6xx_hal_i3c.h and Src/stm32n6xx_hal_i3c.c | Per-handle frame-complete marker; multiple DMA completion waits for every channel, and TC/abort races finish once. Header layout affects both S/NS builds; preserve on HAL refresh |
| ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_ble.c, w61_at_common.c/.h, w61_at_api.h, modem_cmd_handler.c/.h | Notification waits for prompt before payload and terminal response afterward; immediate AT-lock admission returns BUSY before announcing raw data, preserving the admitted execution budget. Short command writes and unfinished raw transactions fence further AT text until module restart. Preserve on SDK refresh |
| ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c | Scan-only asynchronous diagnostics separate TX-lock wait/held ticks, without logging AT arguments; preserve when refreshing vendor code |
| ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c, w61_at_api.h, w61_at_ble.c | BLE initial OK/prompt/Recv/SEND OK and earlier payload OK ownership; preserve fast rejection, payload phase and actual missing-response fence on SDK refresh |
| ThirdParty/ST67W6X_Network_Driver/Core/w6x_wifi.c, Driver/W61_at/modem_cmd_handler.c/.h, w61_at_common.c, Driver/W61_bus/spi_iface.c; debug_uart.c/.h | CONNECTED settling uses budgeted AT admission, never parser sleep; raw guarded admission is BUSY with no write/fence. SPI terminal capture is scalar only, no formatter on its 768-byte stack. Preserve on SDK refresh |
| ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_wifi.c, w61_at_api.h; Api/w6x_types.h; Core/w6x_wifi.c | Scan scratch allocation under AT ownership, callback-borrowed lifetime/release, bounded parser-locked failure cleanup and pre-dispatch status initialization; preserve on vendor refresh |
| Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_pcd.c | Temporary Non-Secure-only USB initialization stage logs |
| Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_ll_usb.c | Temporary Non-Secure-only core-reset register and timeout logs |

The CAD stack macro currently lives in a preserved USER block in usbpd_dpm_conf.h, but the line that consumes it is outside a protected block. CubeMX may restore:

~~~c
#define OS_CAD_STACK_SIZE 1024
~~~

If this happens, restore the N6-specific mapping before building.

### 3.2 Imported files without USER blocks

Files imported from X-CUBE packages are not necessarily CubeMX-owned. The VL53L9 platform layer has no useful USER blocks but is intentionally ported to STM32N6 and ThreadX. Do not replace it blindly with the original H563 demo file.

## 4. Important files

| File or directory | Responsibility |
|---|---|
| PLAN_WIFI_MODULE.md | Approved T01 radio architecture, implementation order, memory/security gates, and validation plan |
| hil_tests | Non-destructive host-side HIL automation, BLE discovery reports, and hardware-free utility self-tests |
| N6.ioc | Pins, clocks, contexts, interrupts, and middleware configuration |
| FSBL/Core/Src/main.c | External-NOR mapping and boot flow |
| FSBL/Core/Src/extmem.c | Exact signed-image size calculation and STM32 image-header inspection |
| FSBL/Core/Src/firmware_boot.c | Redundant metadata, candidate verification, A/B trial selection, confirmation fallback, and rollback |
| FSBL/Middlewares/ST/STM32_ExtMem_Manager/boot/stm32_boot_lrun.c | LRun copy/jump middleware with local diagnostics |
| Common/Update | Shared manifest, A/B metadata format, SHA-256, ECDSA-P256 verifier, and tracked public key |
| AppliSecure/Core/Src/main.c | TrustZone, RIF/RISAF, cached vectors, Non-Secure handover |
| AppliSecure/Core/Src/secure_firmware_update.c | Secure inactive-slot writer, read-back authentication, version policy, and atomic metadata |
| Secure_nsclib/secure_nsc.h | CMSE-checked Begin/Write/Finalize/Abort/Confirm interface |
| AppliNonSecure/Core/Src/main.c | HAL and peripheral initialization |
| AppliNonSecure/Core/Src/stm32n6xx_hal_msp.c | USB HS clocks, VDDUSB, and the N6-specific PHY reset/release sequence |
| AppliNonSecure/Core/Src/app_threadx.c | Application task creation |
| AppliNonSecure/Core/Inc/app_features.h | Feature flags, especially ST67 |
| AppliNonSecure/Core/Src/gc9a01.c and Core/Inc/gc9a01.h | Asynchronous GC9A01 SPI TX primitive, GPIO control, cache maintenance, and ISR completion bridge |
| AppliNonSecure/Core/Src/display_app.c and Core/Inc/display_app.h | Dedicated display task logic, controller initialization, DMA/event waits, clear, and startup text |
| AppliNonSecure/Core/Src/tof_app.c | Separate acquisition/processing loops, static raw slots, transform, status, and rendering |
| AppliNonSecure/Core/Src/tof_image_processing.c | Table-driven, allocation-free depth-map filters and parameter validation |
| AppliNonSecure/Core/Src/rps_ai.c and Core/Inc/rps_ai.h | Frozen preprocessing, STAI initialization, synchronous Neural-ART run, and result/status contract |
| AppliNonSecure/Core/Src/npu_shared_memory.c and STM32N657X0HXQ_LRUN.ld | Explicitly cleared upper-SRAM3 workspace that preserves the VL53L9 SRAM2 heap |
| AppliNonSecure/AI | Stage-08-installed generated network, embedded weights, matched STAI/LL_ATON runtime, device cache layer, and vendor licenses |
| AppliNonSecure/Utilities/vl53l9-common/platform/platform_utils.c | STM32N6 GPIO/I3C DMA callbacks and ThreadX event bridge |
| AppliNonSecure/Utilities/vl53l9-common/vl53l9/vl53l9_platform.c | Persistent combined-transfer and TX-DMA contexts |
| AppliNonSecure/Drivers/BSP/Components/vl53l9/vl53l9.c | Sensor driver plus local stage-level asynchronous frame API |
| AppliNonSecure/Core/Src/debug_uart.c | Independent ST-LINK diagnostics |
| AppliNonSecure/Core/Inc/menu.h and Core/Src/menu.c | Allocation-free chunked line parser, prefix table, handler dispatch, and CRLF reply API |
| AppliNonSecure/Core/Src/debug_cli.c | USB CDC command table, handlers, echo, and console-mode behavior |
| AppliNonSecure/Core/Src/xmodem_receiver.c | Allocation-free XMODEM-CRC state machine |
| AppliNonSecure/Core/Src/firmware_update.c | Transport-to-Secure byte-stream adapter and five-second boot confirmation |
| AppliNonSecure/Core/Src/usb_cdc_transport.c | Static CDC slots, RX/TX queues, callbacks, sessions, flow/error counters |
| AppliNonSecure/Core/Src/wifi_ble_app.c | Optional ST67 application task |
| AppliNonSecure/USBX/App/app_usbx_device.c | USB Device state machine and USBX initialization |
| AppliNonSecure/USBPD/App/usbpd_dpm_core.c | Type-C CAD task |
| Tools/build_and_sign.ps1 | Full build, STM32 image signing, default metadata, and versioned update package |
| Tools/Build-NonSecureIncremental.ps1 | Fast incremental Non-Secure ELF/map/bin build without the disassembly listing |
| Tools/Debug-NonSecureRam.ps1 | DEV-boot FSBL handoff, verified local Secure SRAM1 replacement, verified Non-Secure SRAM2 replacement, and GDB handoff |
| Tools/Install-NonSecureUpdate.ps1 | Explicit next-version Non-Secure build/sign/package/XMODEM/install/boot verification |
| Tools/Send-Xmodem.ps1 | Auto-detected CN8 XMODEM-CRC 1K sender with CRC self-test, retries, and finalization timeout |
| Tools/N6-DevCommon.ps1 | Shared STM32 tool discovery, build guards, heap check, version transaction, and CDC discovery |
| Tools/New-FirmwareSigningKey.ps1 | One-time educational P-256 key generation; the designated development private blob is tracked so the complete teaching project can be shared |
| Tools/New-FirmwareUpdatePackage.ps1 | Signed `.n6fw` manifest plus trusted Non-Secure image |
| training/README_HE.md | Educational, resumable ToF rock-paper-scissors capture/training/Neural-ART architecture and safety gates |
| training/scripts | One Python entry point per capture, validation, training, quantization, N6 generation, HIL, and upload stage |
| training/*.bat | Guided Windows entry points plus resumable model-build orchestration |
| Tools/program_flash.ps1 | External-NOR programming including both default metadata sectors |
| Tools/Factory-Provision.ps1 | Explicit full-NOR erase, complete image programming/verification, and CN8 boot-version verification |
| FlashImages | Signed programming artifacts |
| ThirdParty/ST67W6X_Network_Driver | Git-tracked ST67 source subset used by CubeIDE, with license files |
| radio_firmware | Self-contained ST67 mission-T01 2.0.106 updater, QConn dependencies, binary licenses, hashes, and Hebrew guide |
| .local-dependencies | Local SDK archives, PDFs, examples, backups, and diagnostics remain ignored; only the explicitly designated educational update-signing key is tracked |

The Git repository root is `project`. Do not restore build references to the
ignored full X-CUBE-ST67W61 package. CubeIDE include paths and linked resources
must resolve through `ThirdParty/ST67W6X_Network_Driver` so a clean clone can
build without local downloads.

## 5. Build and signing rules

After a source change, build at least the context that changed. Build every context if a change affects:

- FSBL or Secure.
- Linker scripts or memory layout.
- Image addresses or maximum sizes.
- Secure/Non-Secure interfaces.
- Startup behavior.
- TrustZone ownership.

Preferred command:

~~~powershell
powershell.exe -ExecutionPolicy Bypass -File .\project\Tools\build_and_sign.ps1 -FirmwareVersion 1
~~~

For an ordinary change confined to Non-Secure, prefer the fast lane while
iterating:

~~~powershell
powershell.exe -ExecutionPolicy Bypass -File .\project\Tools\Debug-NonSecureRam.ps1 -Run
~~~

This lane must not edit `firmware_build_version.h`, sign an image, or touch
external Flash. A reset returns to the DEV-boot ROM; restore BOOT1=1-2 and
press Reset to run the installed Flash image. When final persistent validation
is explicitly intended, use
`Install-NonSecureUpdate.ps1` with a user/changelog-selected version exactly
one greater than the tracked current version. Do not invoke that command merely
to test compilation; use its `-PackageOnly` mode, which restores the tracked
version, when build/sign/package verification alone is required.

The fast incremental lane is not valid after changing `ux_user.h` unless
`-Clean` is supplied. It is never valid as a substitute for the full build when
FSBL, Secure, startup, linker layout, image addresses, TrustZone ownership, or
the Secure/Non-Secure interface changed.

Firmware versions are positive and strictly increasing relative to the confirmed
image. Never reuse a released version number. This is an explicitly educational
project: `.local-dependencies/keys/firmware-update-p256-private.blob` is a shared
development key and is intentionally tracked so another learner can reproduce
the update flow. It must never be treated as a production secret or production
root of trust. Do not print its contents in logs or normal user-facing output.

If the headless IDE hangs, a direct make.exe build from the Debug directory is acceptable. The resulting binary must still be passed through STM32_SigningTool_CLI and the new trusted image must be written to project/FlashImages.

After CubeMX Generate Code, explicitly audit these known multi-context losses:

- FSBL must keep `HAL_BSEC_MODULE_ENABLED` and `HAL_XSPI_MODULE_ENABLED`.
- FSBL and AppliSecure must keep `HAL_PKA_MODULE_ENABLED` and
  `HAL_RNG_MODULE_ENABLED`; AppliSecure must also keep
  `HAL_XSPI_MODULE_ENABLED`.
- AppliSecure must claim `RIF_RISC_PERIPH_INDEX_PKA` as Secure/non-privileged
  before `SecureFirmwareUpdate_Init()`; the generated system isolation table
  must preserve the same ownership. PKA MSP initialization must perform a
  clock-enable followed by a reset/release sequence.
- The shared crypto initializer must initialize and keep the RNG AHB clock
  running before enabling PKA. RNG remains Secure/non-privileged and both FSBL
  and AppliSecure `.project` files must retain `stm32n6xx_hal_rng.c`.
- FSBL and AppliSecure `.project` / `.cproject` files must retain the shared
  `Common/Update` sources and includes. AppliSecure must retain its linked
  ExtMem manager and HAL XSPI/PKA sources.
- The shared HAL `Inc` and `Src` directories must contain the union of the
  modules required by all contexts. Restore unchanged vendor files only from
  STM32Cube FW N6 V1.4.0.
- AppliNonSecure `.cproject` must include
  `../../Drivers/BSP/STM32N6xx_Nucleo`.
- AppliNonSecure Debug C and C++ optimization must remain `-O3`; restoring
  `-O0` makes the measured transform take about 264 ms and prevents 10 fps.
- AppliNonSecure `.project` must link `stm32n6xx_hal_uart.c` and
  `stm32n6xx_hal_uart_ex.c` for the custom ST-LINK VCP logger.
- FSBL `SystemClock_Config()` must use `RCC_HSE_BYPASS_DIGITAL`; USB cannot run
  when Generate Code returns it to `RCC_HSE_OFF`.
- `Tools/build_and_sign.ps1` intentionally rejects a generated
  `OS_CAD_STACK_SIZE` that is not mapped to `N6_USBPD_CAD_STACK_SIZE`; do not
  bypass this guard. The 1 KiB default has been reproduced as `STKOF` in the
  TCPP0203 ADC/RCC initialization path.
- `N6.ioc` must retain CDC ACM transmission mode enabled
  (`USBX.UX_DEVICE_CLASS_CDC_ACM_TRANSMISSION_DISABLE=0`). Generated
  `ux_user.h` must not define `UX_DEVICE_CLASS_CDC_ACM_TRANSMISSION_DISABLE`.
- With the current enabled radio build, PE9/SPI_RDY owns both edges of EXTI9
  and ToF polls PD9 with a bounded wait. If the radio feature is disabled,
  generated GPIO configuration must instead route PD9 as falling-edge EXTI9
  and leave PE9 as a plain input. Verify the shared handler and callbacks keep
  matching the selected owner.
- The Secure RIF USER block must keep both
  `HAL_EXTI_ConfigLineAttributes(EXTI_LINE_9, EXTI_LINE_NSEC | EXTI_LINE_NPRIV)`
  and `NVIC_SetTargetState(EXTI9_IRQn)`. The line attribute does not change the
  Secure NVIC target; omitting the latter makes the Non-Secure ToF task time
  out even though PD9 reaches its active-low state.

Never ask the user to program an image until:

- Compilation succeeded.
- Linking succeeded.
- The correct binary was signed again.
- The signing tool reported success.

Do not accidentally deliver an older trusted image after rebuilding an ELF.

## 6. Programming and hardware safety

- Do not program hardware unless the user requested it or the current workflow explicitly reached the programming step.
- Do not use -FullErase without a clear reason and explicit awareness that it erases all external NOR contents.
- Programming mode: BOOT0=1-2, BOOT1=2-3.
- External-Flash boot mode: BOOT0=1-2, BOOT1=1-2.
- Image addresses are fixed:
  - FSBL: 0x70000000.
  - Secure: 0x70100000.
  - Non-Secure Slot A: 0x70180000, 1 MiB.
  - Non-Secure Slot B: 0x70280000, 1 MiB.
  - Boot metadata sectors: 0x703E0000 and 0x703F0000, 64 KiB each.
- Do not change an address or region size without updating the FSBL, linker scripts, signing limits, programming script, and documentation together.

## 7. TrustZone rules

Every peripheral used by Non-Secure must pass three checks:

1. The SAU/partition configuration marks the target region Non-Secure.
2. RIF/RISC does not block the peripheral.
3. GPIO and interrupt attributes target Non-Secure.

Preserve Non-Secure access for:

- USART1 and GPIOE pins 5/6 for diagnostics.
- I3C1, GPDMA1, and ToF GPIOs.
- USB1_OTG_HS and UCPD1.
- I2C2 and ADC12 for TCPP0203.
- SPI5, GPIO, DMA, and EXTI for ST67 when the feature is enabled.

Do not read Non-Secure vectors through an alias that becomes inaccessible after RISAF. The current code caches MSP and Reset_Handler before isolation. Preserve this behavior until the underlying alias behavior is fully resolved.

## 8. RTOS and memory rules

- In ThreadX, a smaller numeric priority means a higher priority.
- Do not reduce stack sizes based on intuition.
- Use GCC .su data, ThreadX stack analysis, or measured high-water marks.
- Optimization can change both speed and individual stack-frame sizes. The
  current `-O3` transform is faster but GCC reports very large automatic arrays
  in its optimized call tree; never infer stack safety from `-O0` results.
- 0xEFEFEFEF is the ThreadX stack-fill pattern.
- CFSR_NS bit 0x00100000 is STKOF on Cortex-M55.
- Match PSP to a byte-pool address before changing a task's stack.
- Leave room for alignment, exception stacking, and possible floating-point context.
- Current large stacks are safe bring-up values, not final memory optimization.
- The linked Non-Secure image must leave at least 360 KiB between `_end` and
  `_sstack` for the VL53L9 first-frame allocation set and malloc metadata.
  `build_and_sign.ps1` enforces this before signing.

Current task sizing:

| Task | Priority | Stack |
|---|---:|---:|
| USB-PD CAD | 1 | 8 KiB |
| Firmware confirmation | 6 | 2 KiB; one-shot after a five-second trial window |
| ToF Acquisition | 7 | 16 KiB |
| GC9A01 display | 8 | 4 KiB; suspends after the startup screen |
| ToF Main Thread (processing) | 10 | 96 KiB |
| USBX Device App Main Thread | 8 | 16 KiB |
| USB CDC RX worker | 9 | 12 KiB, statically allocated |
| USB CDC TX worker | 9 | 12 KiB, statically allocated |
| ST67 Radio Manager | 9 | 8 KiB, active in dedicated SRAM4 pool |
| ST67 Wi-Fi control | 11 | 6 KiB, active in dedicated SRAM4 pool |
| ST67 Cloud Relay | 9 | 8 KiB, fixed lower SRAM4 storage outside the byte pools; M5.3/M5.4 RAM HIL pending |
| USB debug CLI | 9 | 6 KiB |

## 9. Known ST defects and non-defects

### SPI5 abort recovery contract

SPI5 master RX automatic suspension remains disabled. The 2026-10-04 MASRX
experiment passed two live-register BLE probes but failed after a fresh boot
with SUSP/timeouts and lost replies. Its IOC/initializer changes were reverted;
do not promote the two transient PASS results to configuration acceptance.
Generate Code is not required for the C-only recovery change alone.
The 2026-10-06 candidate sets GPDMA1 SPI5 RX channel 11 to DMA_HIGH_PRIORITY
in N6.ioc and its MSP initializer; TX channel 10 stays LOW/HIGH_WEIGHT. Do not
raise every channel to HIGH. Two fresh MTU-247 RAM probes received 300/300
pings with ToF active and zero SPI errors/timeouts/recoveries. The source build
booted normally and passed 100-frame CRC/NPU/bit-exact preprocessing HIL with
radio scan preflight. Generate Code is REQUIRED/PENDING for the IOC change.
The ordinary source build also received 150/150 idle BLE replies (p95 141 ms,
max 172 ms). Later Wi-Fi association and paired Cloud CLI remained live, with
zero SPI errors/timeouts, but ToF stopped at frame 2687 before Cloud pairing.
I3C retained HAL_I3C_ERROR_SIZE/BUSY_TX_RX while RX DMA was READY with its
abort callback still armed; the event wait timed out without an error callback.
The initial trigger is not established: the preceding GDB halt could affect
timing. This is not a Cloud image PASS or a ToF recovery fix. Cloud stack
sentinel high-water was 3504/8192 bytes for this HTTP/CLI phase, excluding ToF
send validation. The precise competing DMA/bus actor, boot repeatability and
Cloud/MAP load remain unverified. No clock/port/burst/stack/pool capacity change
was made. Keep investigating bounded local recovery under the existing plan.

`spi_port_abort()` must clean both SPI5 normal-mode DMA channels even when
HAL SPI abort has already cleared the DMA-request bits or returns an error.
Local DMA deinit/init preserves the parent link. A failed SPI abort may require
an SPI5 peripheral reset after the channels stop. Reuse the READY handle for
HAL_SPI_Init; setting it RESET reruns the generated MSP initializer (480-byte
GCC frame) on the 768-byte SPI worker stack. Do not reset the shared DMA
controller or NCP to hide this local failure. GDB counters distinguish DMA/SPI
reinitializations and failures. On 2026-10-04 RAM recovery was exercised with
zero reinitialization failures and 660/768 observed stack bytes used. The
108-byte untouched prefix is a narrow measured margin, not worst-case proof.
SPI RX overrun's precise DMA/bus cause and full-load validation remain open;
this is not Cloud-contention acceptance or evidence of heap exhaustion.

The 2026-10-08 board-local `spi_port.c` CS-low interval wait compares elapsed
SysTick ticks modulo LOAD+1 and has a bounded software fallback. Do not restore
the vendor WAIT_FROM absolute-endpoint loop: when its computed endpoint is
zero, it requires sampling VAL==0 and can starve the SPI worker. Non-reset raw
CPU inspection observed that zero-endpoint loop during loss of USB/UART
responses; this does not establish the initiating cause of the separate SPI
RX HAL error. `hil_tests/test_spi_cs_hold.py` checks skipped-zero reload,
normal/reloaded intervals and frozen/disabled timers against the actual wait
function. The microsecond conversion rounds up using SystemCoreClock/1e6.

### 9.1 Strong bug candidate: 1 KiB CAD stack

The official STM32Cube FW_N6 V1.4.0 USB CDC example uses a 1024-byte CAD stack.

Measured Debug frames include:

- USBPD_CAD_Task: 104 bytes.
- BSP_USBPD_PWR_VBUSInit: 24 bytes.
- PWR_TCPP0203_Configure_ADC: 440 bytes.
- HAL_RCCEx_PeriphCLKConfig: 488 bytes.

The visible total already exceeds 1024 bytes. Hardware reported STKOF during cable attachment, with PC and LR in this exact path and PSP in the USB-PD pool.

Treat the 1024-byte default as unsafe for this Debug configuration.

### 9.2 Confirmed X-CUBE-53L9A1 V1.0.0 bug

The original platform_acknowledge_event function is missing a break after PLATFORM_I3C_IBI_EVT. The local port adds the break. Do not reintroduce the original fall-through.

### 9.3 Confirmed X-CUBE-53L9A1 asynchronous lifetime bug

The original `vl53l9_read_async()` passes pointers to automatic descriptor,
transfer, address, control, and status objects into an asynchronous HAL path
and then returns. HAL retains `pXferData` while DMA is active, so those objects
must outlive the call. The local port uses one persistent context containing a
combined address-write/repeated-start/read transfer. Do not restore the
stack-local version or split the address phase back into a blocking transfer.

### 9.4 Do not mislabel these as ST bugs

- The 96 KiB ToF stack balances the measured active `-O3` path with the large
  dynamic heap required by the transform. Do not size it from `.su` entries
  without proving that those functions execute in the selected profile.
- The 16 KiB USBX stack is conservative. The proven overflow was in CAD.
- Fixed CDC startup independent of CAD was a diagnostic workaround and is no longer active.
- The ST67 FreeRTOS compatibility layer is a project integration requirement.
- The FSBL weak size hook is designed for application override.
- Earlier all-zero CC readings were resolved by fixing the CAD task stack; attachment is now proven on CC2.
- The H563 VL53L9 demo requiring a port to N657 is expected.

## 10. ToF rules

- The 2026-10-07 candidate keeps map/dataset, selected channels/processing,
  pause and exclusive destination in `TOF_DesiredState_t`. Recovery must not
  replay a stale copy over a newer command. Only acquisition may reset I3C1,
  DMA 0/1/2 and XSHUT. Retain failed DMA destinations until reset succeeds;
  never flush/reseed processing/display-owned raw slots. Reject old raw
  generations. Three attempts are capped until thirty complete healthy
  acquisitions; running success requires a fresh complete acquisition.
  Native C fault/state tests and signing passed. SRAM XSHUT injection restored
  USB/Cloud intent and a fresh frame in 310--381 ms: 40 CRC-valid USB records
  and 20 further accepted Cloud frames. An uninjected Cloud-phase fault also
  recovered. BLE delivered 15 further CRC-valid images after non-halting
  injection, then an AT prompt failure fenced the radio; retain all failed
  BLE reports and do not claim BLE acceptance. Physical persistent-fault and
  newer-command tests, current-candidate Stage 11/image-route and endurance
  remain open. See docs/tof-desired-state-recovery.md.

- Do not change the transform pipeline without testing a complete frame and metadata.
- Preserve timeouts so a missing sensor cannot block the complete system forever.
- PD9 and PE9 share EXTI line 9; do not enable both paths blindly.
- While APP_ST67W6X_ENABLED is 0U, PD9 owns falling-edge EXTI9 and PE9 is a
  plain input. Enabling the radio requires an explicit new ownership strategy,
  preferably I3C IBI for ToF or a deliberate interrupt-routing policy.
- Send the ANSI map as a complete terminal frame to avoid tearing.
- CLI map-off should hide output while acquisition continues.
- Preserve autonomous synchronization and the 100 ms frame period unless a
  deliberately slower profile is requested; 10 fps is the current sensor
  maximum.
- Only `tof pause` should stop the autonomous ranging stream.
- Preserve the local missing-break fix in platform_acknowledge_event.
- Preserve the persistent `g_async_i3c_context`; asynchronous HAL descriptors
  and every buffer they reference must remain valid until DMA completion.
- A VL53L9 register read is one two-descriptor HAL frame. Call
  `HAL_I3C_AddDescToFrame()` once with both the register-address TX descriptor
  and payload RX descriptor (`NbFrames == 2`). A second call does not append;
  it resets the HAL frame state and causes an asynchronous I3C error.
- Preserve the single I3C owner: only the ToF acquisition task may start a
  steady-state sensor transaction. Each start must acknowledge stale RX/TX and
  error flags, then wait for the matching callback event before reusing the
  persistent context.
- `HAL_I3C_Ctrl_MultipleTransfer_DMA()` completes through
  `HAL_I3C_CtrlMultipleXferCpltCallback()`, not the ordinary RX callback. Both
  are intentionally bridged to the RX event because the local multiple
  transfer is a register read.
- Never print from an I3C/GPIO callback or ISR. Preserve the platform
  diagnostic snapshot (HAL error/state, EVR, DMA states, completion/IRQ
  counters, and event-post failures), then format it from the ToF task after a
  failed wait.
- Preserve synchronous I3C-start diagnostics. Descriptor construction and DMA
  start may return `HAL_BUSY`/`HAL_ERROR` without invoking the HAL error
  callback; record the start stage, HAL status, and peripheral/DMA snapshot
  before returning the platform error.
- Preserve `g_platform_evt` as a sticky fallback. If a callback ran but
  ThreadX rejected its event-flags post, `platform_wait_for_event()` must still
  consume the acknowledged transaction's sticky completion/error bit.
- Never silently retry a ThreadX queue-object error. Normal ToF backpressure may
  evict an unprocessed ready frame, but an impossible empty free+ready state or
  a failed blocking processing receive must be counted, rate-limited on UART,
  and moved to the explicit ToF fatal state.

## 11. USB and USB-PD rules

- ST-LINK VCP and CN8 USB CDC are two different COM ports.
- UART diagnostics must remain operational even if USBX faults.
- Non-Secure ST-LINK UART accepts one-key read-only status snapshots and one
  periodic watch at a time (`?`, `a`, `r/t/c/u`, `R/T/C/U`, `0`). RX ISR only
  queues bytes; formatting and status getters run in the UART diagnostic
  thread. Keep it separate from the USB/BLE command broker, redact secrets,
  and do not make a status getter wait indefinitely on another subsystem.
- Initialize PCD, USBX Device stack, and HAL_PCD_Start from task context after ThreadX starts.
- Preserve the N6 USB1 HS-PHY reset/configuration/release sequence in the MSP USER block. CubeMX's generated clock and VDDUSB setup is not the complete sequence used by ST's board example.
- Preserve the explicit `RCC_PERIPHCLK_USBPHY1` configuration in the MSP USER block. The generated code fills `UsbPhy1ClockSelection` but requests only `RCC_PERIPHCLK_USBOTGHS1`, so the HAL otherwise skips the PHY mux field.
- Preserve the corrected CDC FIFO sizing after HAL_PCD_Init: Rx 0x200 words,
  Tx EP0 0x10, Tx EP1 0x100, and Tx EP2 0x20. EP1 carries 512-byte High-Speed
  bulk packets; ST's 0x10-word reference value is too small for the HAL
  non-DMA transmit loop and causes the first CDC write to wait forever.
- Preserve the PCD-handle clear before every attach-cycle initialization.
- Start the PCD only from the USB-PD CAD attach notification. Do not restore the earlier unconditional START unless deliberately isolating the CAD path again.
- Preserve USBX CDC callback transmission mode. Do not re-enable
  `UX_DEVICE_CLASS_CDC_ACM_TRANSMISSION_DISABLE`.
- Preserve `UX_THREAD_PRIORITY_CLASS == 8` and the 8 KiB generic USBX thread
  stack. Callback mode runs Bulk-IN/Bulk-OUT in USBX-owned class threads; the
  USBX default priority 20 is starved by the continuous priority-10 ToF
  processing task, leaving a submitted TX packet permanently in flight.
- Always clean-build NonSecure after changing `ux_user.h`. CubeIDE can retain
  stale USBX middleware objects during an incremental build; the local
  `Tools/build_and_sign.ps1` script deliberately enforces the clean build.
- All TX allocation is gated by an active CDC session, `UX_DEVICE_CONFIGURED`,
  and host DTR. Windows may leave a CDC class configured after closing the COM
  handle; no application producer may enqueue until DTR establishes the host
  session. A close must stop high-rate producers, and a physical detach must
  flush and release every queued or reserved static slot.
- The USBX read callback must remain short: acquire a static RX slot, copy the
  completed payload, post one pointer, and return. Parsing belongs to the RX
  dispatcher/CLI, never the callback.
- Preserve single TX submission ownership: only the TX scheduler may call
  `USB_CDC_LL_WriteAsync`. It must not submit the next buffer before the write
  callback posts the completion semaphore for the current sequence.
- The TX completion wait is bounded to five seconds. On timeout, never reuse
  the in-flight buffer or resubmit into USBX. Latch diagnostics, let the worker
  quiesce, and have the USB manager abort/restart the data plane. Recovery is
  capped at three attempts per physical CDC activation.
- Preserve the periodic USB health event. Timer context may only post the
  manager event; it must not allocate, format, log, or call USBX. The manager
  atomically consumes sticky rare-event flags and prints cumulative counters.
- Queue/slot backpressure is not an ISR logging site. Counters retain full
  history; diagnostics report the latched category once per health pass.
- Check USB worker event-flag, blocking queue-receive, and completion-semaphore
  results. Preserve the worker-synchronization counter/sticky flag and manager
  recovery path; a rejected callback wakeup must not become an invisible
  infinite wait.
- Coalesce CDC line-parameter notifications into a counter. Host setup bursts
  carry no application payload and must not fill the lifecycle/error queue.
- Keep USBX class callbacks free of UART formatting. Manager-queue failures
  must retain total, per-event-type, last-type, and last-ThreadX-status data for
  later manager-thread reporting.
- All application TX text must pass through `USB_CDC_Transport_Send`. Complete
  maps must use Acquire/Commit/Cancel so the renderer writes directly into a
  static 48 KiB map slot. All RX data must be consumed through
  `USB_CDC_Transport_Receive`.
- Keep `menu.c/.h` platform-independent and allocation-free. The CLI task is
  the sole owner of each `Menu_t`; do not invoke `Menu_Process()` concurrently
  from USBX callbacks or another task.
- Keep the USB CLI at a higher scheduling priority than the priority-10 ToF
  processing task. The processor may remain continuously ready while dropping
  stale raw frames; a lower-priority CLI can therefore starve even after the
  CDC RX callback has accepted Enter.
- Command entries are prefix/handler pairs. Preserve delimiter-aware
  longest-prefix matching, full-line dispatch only after CR/LF/CRLF, and
  discard-until-Enter behavior after input overflow.
- Menu handlers receive the complete normalized command line in task context.
  Static textual responses should use `Menu_Reply()`, which builds one
  CRLF-terminated response in the caller-owned reply buffer and submits it
  through `App_Console_Write()` without allocation.
- Preserve the static slot counts and sizes (control TX 8×768, map TX 2×48 KiB,
  RX 16×512), bounded pointer queues, semaphores, and session tags unless a
  measured redesign updates code and documentation together. ToF map enqueue
  must remain non-blocking.
- Do not introduce packet allocation, a CDC byte pool, or a full-map copy into
  the steady-state path.
- On detach, invalidate the transport session and quiesce both workers before
  deinitializing PCD/USBX. Do not leave a worker blocked on an instance that is
  being destroyed.
- TCPP component type 0x00 is valid for TCPP03 and is not automatically an error.
- Green LD2 with a CN8 cable indicates VBUS/power presence, not successful CC detection or USB enumeration.
- Record PID, product string, serial string, and endpoint changes.
- Test repeated start/stop before treating detach handling as production-ready.

## 12. ST67W6X rules

- M5.2–M5.4 source now isolates the Cloud pump in its own priority-9 worker.
  Radio Manager publishes scalar network readiness; it must never run Cloud
  DNS/socket/protocol processing. Runtime pair/enable/disable/reconnect/unpair
  use a four-entry fixed by-value control queue and return admission status;
  socket close and pairing filesystem operations belong to the worker.
  Cloud status getters return an atomic cached snapshot without waiting.
  RAM startup and connected Cloud browser images/exclusive BLE/USB handovers
  passed on 2026-10-06. Full network stack high-water, BLE-under-Cloud failure
  latency and endurance gates remain open; do not accept Milestone 5 globally.
- User-authorized 2026-10-06 contract: exactly one remote image destination,
  last request wins (USB, BLE or Cloud). The processing task advances the
  active route only after all USB MAP slots and the wireless snapshot idle.
  A requested/active mismatch disables new publications. Cloud-only snapshots
  enter WAIT_CLOUD directly; BLE-only snapshots enter READY. Release only
  after the old consumer stops reading, including socket close/cancellation.
  CLI sessions and the local display remain independent. Do not restore
  simultaneous BLE+Cloud fanout or add another image buffer for switching.
- BLE notification protocol is prompt -> payload -> terminal OK/ERROR.
  Notification AT admission must be nonblocking: return BUSY before any raw
  announcement when the mutex is held. The existing pump retains its pending
  fragment and retries; do not consume the execution deadline waiting for a
  Cloud/Wi-Fi AT owner or increase buffers to hide contention.
  Do not wait for an initial OK. Do not release protocol ownership on an
  incomplete raw transfer and then send another AT command: the modem can
  consume that command as binary payload. The bounded fail-closed fence must
  survive ordinary retries; module restart/reinitialization clears it.

- APP_ST67W6X_ENABLED is 1U for the current attached-shield phase-1 test.
- APP_ST67W6X_BLE_GATT_ENABLED is 1U; two logical UART services and their
  bounded transport queues are implemented. The CLI service owns an independent
  5,176-byte session in SRAM4 and is attached to the shared command definitions;
  the DEBUG output producer remains detached.
  RAM HIL on 2026-09-14 found `N6-MAINT-B8FB`, connected at MTU 247, validated
  both services/four characteristics and CCCDs, and confirmed advertising
  restart after disconnect. Keep the vendor-baseline advertising sequence;
  explicit advertising-parameter plus scan-response overrides made
  `W6X_Ble_AdvStart()` return `W6X_STATUS_ERROR` and remain deferred.
- APP_ST67W6X_WIFI_SERVICES_ENABLED is 1U. Keep scan/connect/disconnect and IP
  queries serialized in the dedicated Wi-Fi control worker; callbacks may only
  snapshot bounded results/state and signal completion. Never print or issue
  W6X control calls from a Wi-Fi callback.
- Accept Wi-Fi credentials on USB CDC, BLE and Cloud by explicit demo policy.
  Password entry must remain hidden, absent from command history, and cleared
  from CLI/manager buffers immediately after use.
- `radio_firmware/contract.json` is the host/target NCP version contract. Stage
  11 must compare the running `radio info` SDK with it and scan the BLE
  CLI-service advertisement when BLE is enabled. If Wi-Fi is enabled later,
  the same stage must also require station status plus a successful scan.
- Preserve mission profile T01 and SDK 2.0.106 until the driver and contract
  are deliberately upgraded together. Any vendor-binary replacement requires
  updated SHA-256 entries, retained ST binary/QConn notices, and an end-to-end
  Stage 10/11 hardware run.
- BLE callbacks may only snapshot event metadata and enqueue/signal bounded
  work. Runtime W6X BLE control and advertising recovery execute in the existing
  control worker through the generation/revision-checked mailbox; Radio submits
  and consumes results and owns the bounded notification pump.
- The Radio Manager now reconciles BLE desired state against command ACKs and
  periodic BLEINIT?/BLECONN? observations. ADV has no AT state query: keep
  `UNKNOWN` distinct from last acknowledged state, cap retries, and never
  claim command ACK proves RF advertising. Do not reset the whole ST67 NCP
  from a BLE-only fault while Wi-Fi/Cloud may be active; external HIL scanning
  is the RF-level check.
- Preserve the item-9 stream contract: CLI RX 8x512 bytes, CLI TX 8x768 bytes,
  DEBUG RX 2x512 bytes but disabled by policy, and DEBUG TX 8x256 bytes. All
  storage is allocated from the SRAM4 radio byte pool. Every connect and
  disconnect advances the generation; stale slots are purged. CLI producer
  waits are capped at 50 ms, DEBUG TX is non-blocking, notification calls use
  a 100 ms timeout with at most three attempts, and the manager services one
  `MTU-3` fragment per stream per cycle.
- Preserve the item-10 broker contract: CDC, BLE and Cloud never share line,
  history, prompt, CR/LF, or output state. Shared command handlers execute
  serially in the priority-9 CLI thread. BLE RX is drained in bounded bursts;
  Cloud records use explicit ACK, sequence and CRC. Signed XMODEM raw mode
  belongs only to the requesting session and feeds the existing Secure
  installer. Do not add transport-specific command allowlists.
- Platform training extension (2026-10-21 M4/M5): legacy display formats1-4
  retain sender-side encoding. Training format5 is a complete lossless N6DF4
  record packed by the ToF producer while the exact same-frame NPU tensor is
  still live; raw u16 depth plus tensor/header fits the existing9072-byte
  snapshot. USB and wireless use one encoder. Do not re-encode it as a display
  image or allocate a second payload buffer. Existing generation/route fencing,
  GATT fragmentation and bounded queues remain. M5 Cloud retains that snapshot
  until a matching post-storage ACK; unknown replies retry identical bytes.
  Control sessions are time/rate/count/volume bounded and use existing tokens.
  M4 final25-record reconnect HIL passed; M5 Wi-Fi acceptance is recorded in
  docs/platform-upgrade-20261021.md only after its real check completes.
- Preserve the BLE ToF image contract: Notify UUID `7a1e0004-b5a3-f393-e0a9-
  e50e24dcca9e`, version-3 56-byte little-endian header, selectable RAW/UINT16/UINT8/JPEG,
  header and payload CRC32, and one SRAM4 snapshot. Capture the matching NPU
  status with pixels; never fetch the latest inference in a transmitting worker. See docs/wireless-image-codec.md.
  For legacy display formats1-4, only the transmitting Radio/Cloud worker encodes; the producer snapshots float32. Snapshot the selected transformed channel
  before `tof_processing_workspace` is reused. While a frame is in flight, drop
  new frames; never queue partial sensor-frame state. Service at most one image
  fragment per Radio Manager cycle so CLI/XMODEM cannot be starved.
- The current No-Input/No-Output BLE setting and capability-token Cloud relay
  are development-only. The demo intentionally exposes the same commands on
  every CLI transport; do not present this as a production authorization model.
- In disabled mode, do not create its task, initialize the compatibility layer, or call W6X initialization.
- Enabling the radio requires verification of SPI5, CS, CHIP_EN, BOOT, SPI_RDY, DMA, and NCP firmware.
- The SPI transfer worker waits for EXTI-ready or host-TX events while idle;
  do not restore the 20 ms idle `SPI_RDY` level poll without an explicit
  architecture decision. Active-transaction handshake level checks remain.
- Keep the AT modem's queued SPI packet alive until every byte is consumed.
  A short destination read must never free and discard the packet tail;
  incomplete AT records stay in the parser's bounded assembly buffer. Keep
  that fixed buffer in the modem object/application SRAM, not the constrained
  64 KiB radio byte pool: SRAM HIL showed the pool nearly exhausted when the
  two-MTU assembly buffer was dynamically allocated there.
- Never implement OTA by overwriting the active image in place.
- BLE XMODEM and any future Wi-Fi delivery must feed the existing Secure
  Begin/Write/Finalize byte interface. Preserve inactive-slot writes, CMSE range checks and Secure copies,
  SHA-256 plus ECDSA-P256, strictly increasing versions, atomic alternating
  metadata, trial confirmation, and rollback.
- XSPI2, PKA, boot metadata, and key-policy decisions remain Secure. A transport
  task may deliver bytes and report status; it may not weaken or duplicate the
  installer in Non-Secure code.
- The current update signature protects remote package authenticity, but the
  development `-nk` image flow and replaceable compiled public key are not a
  production physical root of trust. Production requires authenticated BootROM
  images, protected key provisioning, and protected anti-rollback state.

## 13. Debugging method

1. Request a complete log from Reset rather than only the final fault line.
2. Identify the last completed stage: FSBL, Secure, startup, HAL, ThreadX, or a task.
3. Map PC and LR against the exact ELF that was programmed.
4. Decode status-register bits; HardFault alone is not a diagnosis.
5. Match PSP to its memory pool.
6. Change one important variable per iteration.
7. Add a breadcrumb immediately before and after the suspected call.
8. Build, sign, and confirm that the user programmed the new image.
9. Remove or reduce noisy polling only after the underlying issue is understood.

## 14. Communication style

- Communicate with the user in clear Hebrew, retaining useful English technical terms.
- Lead with the conclusion from the evidence.
- Explain why the evidence supports the conclusion.
- When a physical action is required, give one precise instruction involving the jumper, Reset button, cable, or terminal.
- Do not request Generate Code for a C-only change.
- Do not request programming before build and signing succeed.
- State what the next log is expected to contain.
- Be explicit about confidence: confirmed bug, strong candidate, suspected issue, adaptation, or workaround.
- Update the operational README and append a concise entry to `CHANGELOG.md`
  after architectural changes, boot/fault fixes, interface changes, or
  programming-flow changes. Do not read the historical body just to append.

## 15. Definition of done

A firmware change is complete only when:

- The relevant context builds without errors.
- The correct image is signed again.
- It is documented whether Generate Code is required.
- The user receives short, precise verification instructions.
- Work on USB does not intentionally break ToF, and vice versa.
- Features without attached hardware remain disabled.
- Outside-USER changes are recorded.
- README and `CHANGELOG.md` are updated when the change is significant, without
  loading the historical body unless that history is required.
