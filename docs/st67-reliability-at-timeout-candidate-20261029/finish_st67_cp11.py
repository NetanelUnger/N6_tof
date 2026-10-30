from pathlib import Path
from datetime import datetime, timezone
import difflib, hashlib, json, re, shutil, subprocess
HERE=Path(__file__).parent
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
OUT=HERE/'evidence/st67-cp11-at-timeout-candidate'
PLAN=ROOT.parent/'project/docs/st67-reliability-improvement-plan.md'
EXPECTED='a8223ebe8eaa933aa57a9bb796df9ab69c32a5eabd3369c8fb3634b1dbf41d19'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(PLAN)==EXPECTED
m=json.loads((OUT/'candidate-manifest.json').read_text())
assert sha(ROOT/m['path'])==m['original_sha256']
assert sha(OUT/'candidate'/m['path'])==m['candidate_sha256']
for x in json.loads((HERE/'evidence/st67-cp10-transport-candidate/candidate-manifest.json').read_text()):
    assert sha(ROOT/x['path'])==x['original_sha256']
tests=[]
for suite,label,n in [('timeout','candidate-timeout-v1',8),('admission','candidate-admission-v1',11),('scoped','candidate-scoped-v1',14)]:
    log=(OUT/(label+'.log')).read_text()
    assert len(re.findall(r'^PASS',log,re.M))==n and 'Traceback' not in log
    tests.append({'suite':suite,'generated_c':label+'.c','log':label+'.log','result':'PASS','process_exit_code':0,
                  'printed_assertion_groups':n,'generated_c_sha256':sha(OUT/(label+'.c')),
                  'command':f'C:\\Python314\\python.exe -B .\\test_st67_cp11.py --suite {suite} --label {label}'})
red=(OUT/'production-timeout-red.log').read_text()
assert 'second_result=0 writes=2 late_old_terminal_injected=1 fence=0' in red and 'Assertion failed:' in red
checks=[]
for argv in [['git','apply','--check',str(HERE/'evidence/st67-cp10-transport-candidate/PROPOSED-NOT-APPLIED-spi-fence.patch'),str(OUT/'PROPOSED-NOT-APPLIED-at-timeout-fence.patch')],['git','diff','--check']]:
    p=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True)
    checks.append({'argv':argv,'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr});assert not p.returncode
for name in ('prepare_st67_cp11.py','test_st67_cp11.py','finish_st67_cp11.py'):
    shutil.copy2(HERE/name,OUT/name)
shutil.copy2(HERE/'evidence/st67-cp10-transport-candidate/reproduce_saved_native.py',OUT/'reproduce_saved_native.py')
sources=[m['path'],'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c',
 'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.h',
 'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_wifi.c',
 'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_net.c',
 'AppliNonSecure/Core/Src/wifi_ble_app.c','AppliNonSecure/Core/Src/app_settings_ncp.c',
 'AppliNonSecure/Core/Src/cloud_relay.c','hil_tests/test_wifi_assoc_admission.py','hil_tests/test_cloud_request_budget.py']
now=datetime.now(timezone.utc).isoformat()
summary={'checkpoint':'CP11','recorded_utc':now,'candidate_status':'PROPOSED_NOT_APPLIED',
 'source_revision':'5432d4ae2b10ef7ecdfaedad586038792f0a4db5','native_results':tests,'verification':checks,
 'source_hashes':[{'path':p,'sha256':sha(ROOT/p)} for p in sources],
 'baseline_red':{'result':'EXPECTED_FAIL','log':'production-timeout-red.log','actual':'second_result=0 writes=2 late_old_terminal_injected=1 fence=0'},
 'production_firmware_source_unchanged':True,'hardware_browser_actions':0,'version53_built_signed_installed':False,
 'settings_security_pairing_changed':False,'push':False,'main_plan_tasks':{'completed':4,'unchecked':42,'total':46}}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
report='''# CP11: unscoped AT timeout ambiguity

Recorded UTC: {now}. **PROPOSED / NOT APPLIED**. Main firmware source unchanged.

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
'''.format(now=now)
(OUT/'report.md').write_text(report,newline='\n')
plan=PLAN.read_text(encoding='utf-8')
plan=re.sub(r'^Status: \*\*.*?\*\*  $','Status: **CP11: second AT timeout/stale-response defect reproduced; isolated repair passes three native suites; CP10 SPI candidate also prepared; production firmware unchanged, P0-04/05 and integrated acceptance open**  ',plan,count=1,flags=re.M)
plan=plan.replace('CP10 preparation only: isolated SPI/AT fence, parser race and no-replay native tests; not integrated or accepted.',
 'CP10/CP11 preparation: SPI replay and unscoped AT timeout/stale-response defects reproduced; isolated candidates tested, not integrated or accepted.')
plan += '''

### CP11 - 2026-10-29, Codex: AT timeout and late-response regression

- [x] **CP11-PREP-01** Reproduce a late old OK completing a replacement unscoped command using actual sender/await/callback C; retain failing baseline.
- [x] **CP11-PREP-02** Prepare a one-file ambiguity fence, preserving scoped DNS drain and zero-byte BUSY; pass three native suites and combined CP10/CP11 patch applicability check.
- [x] **CP11-AUDIT-01** Record source lifecycle/budget inventory and reversible baseline-isolation design with remaining physical/collector dependencies.

Evidence: [CP11 report and conclusions](../../n6-xip-ota-usb/docs/st67-reliability-at-timeout-candidate-20261029/report.md),
summary.json, saved actual-C inputs/logs and PROPOSED-NOT-APPLIED-at-timeout-fence.patch.
These preparation checks do not complete main P2 tasks or any hardware gate.

Conclusions after this group:

1. Production generic timeout fences only scoped callers. Native late-response
   model accepted a second command with an old OK (result0, writes2, fence0).
   Candidate rejects it before transmission (result-5, writes1, fence1).
2. Three actual-C suites PASS, including original admission/DNS/epoch/wrap
   boundaries. Candidate does not change budgets or clear genuine fences.
   Full fragmentation, successful-command duplicate terminal ambiguity,
   application exactly-once outcomes and HIL remain open.
3. Source inventory and ST revision86022 support continued receive on busy p;
   no resend/reset is added. Current driver does not treat it as completion;
   a dedicated full-parser/physical test remains required.
4. Settings-preserving BLE-only measurement needs a bounded volatile pause in
   the existing owner or another proven reversible fixture. Current disconnect
   commits desired=false; reconnect soak would need password/settings changes.
   Baseline-test support must be planned explicitly before any installation;
   no gate exception or settings modification was silently made.
5. P0-04/05 and integrated repairs remain incomplete,4/46 main tasks checked.
   No further isolated manual version test is requested; prepare coordinated
   instrumented windows first. B52/A51 is last verified state; no53/build/sign/
   USB install, browser action, hardware handle, cable request, commit or push.
'''
assert len(re.findall(r'^- \[x\] \*\*P[0-7]-\d+',plan,re.M))==4
(HERE/'cp11-plan-after.md').write_text(plan,encoding='utf-8',newline='\n')
(HERE/'cp11-publication.json').write_text(json.dumps({'plan_before_sha256':EXPECTED,
 'plan_after_sha256':sha(HERE/'cp11-plan-after.md'),'destination':str(ROOT/'docs/st67-reliability-at-timeout-candidate-20261029')},indent=2)+'\n')
print(json.dumps({'native_suites':3,'printed_groups':33,'baseline':'EXPECTED_FAIL','candidate':'NOT_APPLIED','plan':'4/46','combined_patch_check':'PASS'}))
