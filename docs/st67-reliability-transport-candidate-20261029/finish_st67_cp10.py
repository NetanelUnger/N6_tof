"""Assemble CP10 evidence locally. No product, board or settings mutations."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, subprocess, re

HERE = Path(__file__).parent
ROOT = Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
PLAN = ROOT.parent/'project/docs/st67-reliability-improvement-plan.md'
OUT = HERE/'evidence/st67-cp10-transport-candidate'
EXPECTED_PLAN = 'ddcd37ff77321ef7149d763f7a4ba9380c6e4f0cc46838da2c022c559e826ff0'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(PLAN) == EXPECTED_PLAN
manifest = json.loads((OUT/'candidate-manifest.json').read_text())
for entry in manifest:
    assert sha(ROOT/entry['path']) == entry['original_sha256'], entry['path']
    assert sha(OUT/'candidate'/entry['path']) == entry['candidate_sha256'], entry['path']

runs = [
    ('spi','candidate-v2-spi',10), ('parser','candidate-v2-parser',5),
    ('coordinator','candidate-v2-coordinator',11),
    ('availability','candidate-v1-availability',9),
    ('framing','candidate-v1-framing',4),
    ('shutdown','candidate-v2-shutdown',4),
    ('write_bridge','candidate-v2-write_bridge',3),
]
results = []
for suite,label,groups in runs:
    log=(OUT/(label+'.log')).read_text()
    assert len(re.findall(r'^PASS',log,re.M)) == groups, label
    assert 'Traceback' not in log and 'Assertion failed' not in log, label
    results.append({'suite':suite,'generated_c':label+'.c','log':label+'.log',
        'result':'PASS','process_exit_code':0,'printed_assertion_groups':groups,
        'generated_c_sha256':sha(OUT/(label+'.c')),'log_sha256':sha(OUT/(label+'.log')),
        'original_command':f'C:\\Python314\\python.exe -B .\\test_st67_cp10.py --suite {suite} --label {label}'})
assert 'Assertion failed: accepted==1' in (OUT/'production-no-replay-red.log').read_text()
assert 'Assertion failed:' in (OUT/'candidate-v1-parser.log').read_text()
for source in ('prepare_st67_cp10.py','refine_st67_cp10.py','test_st67_cp10.py','finish_st67_cp10.py'):
    shutil.copy2(HERE/source,OUT/source)

checks=[]
for args in ([ 'git','apply','--check',str(OUT/'PROPOSED-NOT-APPLIED-spi-fence.patch') ],
             ['git','diff','--check']):
    p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
    checks.append({'argv':args,'cwd':str(ROOT),'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    assert p.returncode == 0, checks[-1]

manual = {
 'reported_utc':'2026-10-29T08:39:00Z','source':'User evidence forwarded by parent thread',
 'device':'N6-MAINT-B8FB','interface':'existing Cloud CLI','command':'version',
 'verbatim_response':'n6> version\nFirmware version: 52\nn6>\nלקח כ2.5 שניות',
 'functional_result':'PASS user-reported command/reply path and reported application version 52',
 'approximate_manual_duration_s':2.5,'instrumented_latency':False,
 'image_route_and_stream_state_at_command':'NOT independently confirmed in user reply',
 'acceptance_result':'INCOMPLETE for P0-04 profile counts/distributions/gaps and frozen workload',
 'repeat_same_command_required':False,
}
(OUT/'manual-cloud-version.json').write_text(json.dumps(manual,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
now=datetime.now(timezone.utc).isoformat()
summary = {
 'recorded_utc':now,'checkpoint':'CP10','source_revision':'5432d4ae2b10ef7ecdfaedad586038792f0a4db5',
 'candidate_status':'PROPOSED_NOT_APPLIED','production_firmware_source_hashes_unchanged':True,
 'native_results':results,'verification':checks,
 'retained_failures':[
  {'label':'production-no-replay-red','result':'EXPECTED_FAIL','kind':'actual production C behavioral no-replay assertion'},
  {'label':'candidate-v1-parser','result':'FAIL','kind':'candidate bug: fault during queued receive published bytes; repaired in v2'},
  {'label':'candidate-v1-spi','result':'FAIL','kind':'fixture compilation: incomplete multiline macro; corrected extractor'},
  {'label':'candidate-v1-coordinator','result':'FAIL','kind':'fixture extraction: public UINT signature unsupported; corrected extractor'},
 ],
 'unchanged_v1_suite_reuse':'Availability uses unchanged wifi_ble_app.c; framing uses unchanged spi_iface.c. Only w61_at_common.c changed between candidate v1/v2.',
 'not_run':['ARM full-context build/link/memory','scheduler/ISR concurrency proof','physical fault injection','candidate installation','endurance'],
 'hardware_handles_opened':0,'browser_actions':0,'firmware_versions_consumed':0,'signed_packages_created':0,
 'production_C_changes':0,'settings_security_pairing_changes':0,'commit_push':False,
 'main_plan_tasks':{'completed':4,'unchecked':42,'total':46},
 'manual_cloud_evidence':'manual-cloud-version.json',
}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

report='''# CP10: isolated SPI ambiguity fence and manual Cloud result

Recorded UTC: {now}. Source: `5432d4ae2b10ef7ecdfaedad586038792f0a4db5`,
`feature/n6-xip-ota-usb`. **PROPOSED / NOT APPLIED**. Production firmware C
hashes are unchanged. Board B52/A51 is the last verified installed state;
this checkpoint opened no hardware handles and did not inspect/change the browser.

## Result and scope

The production SPI worker's actual C fails the no-replay test: a full-duplex
transaction can deliver TX, then fail during the remaining RX, after which the
worker retries the same TX. The model deliberately treats that earlier TX as
accepted; this proves the unsafe retry decision, not that a physical duplicate
application operation was observed on B52.

The isolated four-file candidate closes transport admission after an ambiguous
transfer or invalid peer header and retains TX ownership until the existing
coordinated teardown. Local DMA cleanup alone does not prove that the peer
rejected the command. Explicit `rx_stall` and proven pre-wire allocation/ready
failures keep their existing retry semantics. No memory capacity was increased.

Seven actual-C native suites PASS. The initial candidate failed a newly exercised
race: the transport could fault during queued receive and still publish bytes.
Candidate v2 rechecks after packet ownership transfer, before publishing the
packet, and that regression passes. Original failed tests and v1 patch/hashes are
retained. `git apply --check` and `git diff --check` PASS; neither applies the patch.

## Tests and evidence

| Suite | Result / retained log | Scope |
|---|---|---|
| Production no-replay | Expected behavioral FAIL, production-no-replay-red.log | Runtime assertion, not compile failure |
| SPI worker v2 | PASS, candidate-v2-spi.log | 10 groups: ambiguous remaining/first transfer, RX-only, later RDY, invalid header, DMA retention, explicit stall, zero-wire retry, queue stop, admission |
| Parser v2 | PASS, candidate-v2-parser.log | Existing binary/tail/33 room boundaries plus sticky fault and post-receive race; 64-bit fixture conversion warnings retained |
| Coordinator v2 | PASS, candidate-v2-coordinator.log | 11 groups: original barriers, deadlines, limits, tick wrap, SPI fault delegated to existing owner |
| Availability v1 | PASS, candidate-v1-availability.log | 9 groups; relevant candidate source identical in v2 |
| Framing v1 | PASS, candidate-v1-framing.log | 4 groups, including 132 length/MTU combinations; relevant candidate source identical in v2 |
| Shutdown v2 | PASS, candidate-v2-shutdown.log | Failed acknowledgment/abort retains buffers and fault; only successful teardown clears; repeated cleanup idempotent |
| AT write bridge v2 | PASS, candidate-v2-write_bridge.log | Sticky fault blocks queue writes; only existing zero-byte -3/-5 are notification BUSY; -6 remains hard failure |

See summary.json for exact original commands, test hashes and check outputs.
Saved generated `.c` files are the exact native inputs. `reproduce_saved_native.py`
can rerun them in a new output directory without applying firmware changes.
Preparation/refinement scripts are historical records tied to their workspace
layout; do not run them in place over existing evidence.

Retained failures: candidate-v1-spi was a fixture multiline-macro extraction
compile failure; candidate-v1-coordinator was an unsupported fixture signature;
candidate-v1-parser was a real candidate behavior failure. They are distinct.

## Candidate review boundaries

- Sticky transport state is set before abort. Failed abort preserves the RX
  destination, owned TX and local stack. Existing stop/cleanup barrier remains.
- A parser fault fences AT and yields; a retained packet is freed by teardown.
- The original Radio Manager receives the fault. It still waits for Cloud,
  notification, AT, SPI and parser owners; this patch adds no direct reset path.
- Public service status reports `SPI_FENCED`. A new initialization cannot clear
  the fault without successful teardown. No Secure, signature, rollback, Wi-Fi,
  endpoint, pairing, or NCP firmware change is proposed.
- The prechecks are not an atomic admission/publication proof across every
  scheduler/ISR interleaving. Already admitted buffers remain owned by existing
  queues, and already parsed terminals/exactly-once application outcomes still
  need the wider P2 tests. A raced SPI write hard failure must be handled by its
  existing AT caller; the direct bridge does not silently call it soft BUSY.
- Existing aggregate header-ACK and RX-queue wait bounds remain unresolved.
  The stop test proves cooperative release, not a locally bounded wait.
- Physical OVR cause, reduced latency/throughput, full ARM compile/link/runtime
  margins, and physical recovery are NOT proven. Failing closed can increase
  declared NCP outages versus the unsafe retry. This is an integrity repair
  candidate, not evidence that the underlying SPI error rate is improved.

## Manual Cloud observation

At 08:39 UTC the user reported `version` -> `Firmware version: 52` and about
2.5 seconds. This is PASS evidence for the manual Cloud command/reply path and
reported version. The time is a human estimate, not instrumented latency. The
requested image condition was not separately confirmed in the reply. This does
not complete P0-04/V02/V04, does not satisfy the BLE 1500 ms limit, and does not
erase CP8 BLE1953ms, CP4 image99/100 or CP9 SPI122->123 failures. The same version
test need not be repeated. Exact forwarded content is in manual-cloud-version.json.

## Conclusions and dependencies

1. There is now a reviewable, tested candidate for the demonstrated replay hazard,
   alongside the earlier isolated quiet-logger repair. Neither is integrated or
   installed. No version53 was built, signed, sent, or consumed.
2. P0-04 still needs bounded exact BLE-only, Cloud-only and combined measurement
   windows, with receiver counts/gaps/latency. Existing Wi-Fi disconnect mutates
   saved desired state; an owner-controlled reversible isolation procedure is
   still needed. Manual version removes only command reachability uncertainty.
3. P0-05 still needs a frozen numeric worksheet. P1 correlation/overhead and
   dependent transaction/resource/recovery gates remain. No main P task is checked
   merely for these candidate tests: 4 of 46 checked, 42 unchecked.
4. Independent next work is the AT response/budget/lifetime inventory and the
   reversible baseline-isolation design; neither requires browser input. Do not
   install this candidate before those applicable gates and full-context builds.
5. No physical intervention is needed by this host checkpoint. No new manual
   command is requested until the bounded profile/collector is ready; repeating
   version would add little. No approval denied, pending install, or uncertain
   write occurred. Generate Code is not required for this C-only candidate.
'''.format(now=now)
(OUT/'report.md').write_text(report,newline='\n')

plan=PLAN.read_text(encoding='utf-8')
plan=re.sub(r'^Status: \*\*.*?\*\*  $',
 'Status: **CP10: manual Cloud version52 response confirmed; isolated SPI no-replay candidate passes seven native suites, NOT_APPLIED; P0-04/05 and integrated firmware repairs remain incomplete**  ',plan,count=1,flags=re.M)
old='| P0 | Establish the exact baseline | BLOCKED | Codex |'
line=next(x for x in plan.splitlines() if x.startswith(old))
plan=plan.replace(line,old+' CP10: user reports Cloud version52 in about2.5s (manual estimate; image state unconfirmed). Full P0-04/05 still incomplete; safe BLE-only isolation and instrumented Cloud windows needed. Prior failures retained. [Evidence](../../n6-xip-ota-usb/docs/st67-reliability-transport-candidate-20261029/report.md) |')
plan=plan.replace('| P2 | Audit and repair AT transaction lifecycle | NOT_STARTED | TBD | - |',
 '| P2 | Audit and repair AT transaction lifecycle | NOT_STARTED | Codex | CP10 preparation only: isolated SPI/AT fence, parser race and no-replay native tests; not integrated or accepted. |')
plan=plan.replace('| P4 | Protect SPI receive resources | NOT_STARTED | TBD | - |',
 '| P4 | Protect SPI receive resources | NOT_STARTED | Codex | CP10 preparation only: explicit rx_stall, DMA retention, framing and ambiguous replay tests; aggregate bounds/runtime proof open. |')
plan += '''

### CP10 - 2026-10-29, Codex: isolated transport candidate and manual Cloud result

- [x] **CP10-PREP-01** Reproduce unsafe ambiguous SPI retry in actual production C; preserve expected failing assertion and prepare a four-file candidate without applying it.
- [x] **CP10-PREP-02** Retain v1 parser race failure, repair candidate, and pass seven actual-C native suites; distinguish fixture failures, modeled behavior and absent physical proof.
- [x] **CP10-CLOUD-01** Record user-reported Cloud version52 response and approximate2.5s; keep image state, instrumented timing and full profile acceptance unconfirmed.

Evidence: [CP10 report and conclusions](../../n6-xip-ota-usb/docs/st67-reliability-transport-candidate-20261029/report.md),
summary.json, candidate-manifest.json, saved actual-C inputs/logs, and
PROPOSED-NOT-APPLIED-spi-fence.patch. No main P0-P7 checkbox was changed.

Conclusions after this group:

1. Local DMA cleanup cannot establish whether the peer accepted earlier TX.
   Candidate stops ambiguous replay, preserves ownership, and uses existing
   coordinated recovery. Explicit rx_stall/zero-wire retry stays distinct.
2. The first candidate published bytes when a fault raced queued receive. The
   retained failing test now passes after a post-receive guard. Seven native
   suites pass; no full scheduler/ISR, ARM/link/runtime or physical acceptance.
3. Existing aggregate RX-queue/header-ACK bounds, underlying OVR cause, full AT
   exactly-once/generation coverage and workload latency remain open. This
   integrity candidate may increase declared recovery outages; no performance
   improvement is claimed. Source unchanged and patch applicability check PASS.
4. User Cloud command/reply and version52 are confirmed as user evidence only;
   about2.5s is not an instrumented sample. Image activity was not separately
   confirmed. Do not repeat version without a specific new diagnostic purpose.
5. P0-04/05 remain incomplete; 4 of46 main tasks checked,42 unchecked. Independent
   next work: AT lifetime/budget inventory and reversible baseline isolation.
   No candidate install before applicable gates. CP4/CP8/CP9 failures retained.
6. No browser action/hardware handle, reset, version53, firmware/security/Wi-Fi/
   pairing change, commit or push. Last verifiedB52/A51 preserved. No new cable
   action or approval block. Generate Code not required for the prepared C patch.
'''
assert len(re.findall(r'^- \[x\] \*\*P[0-7]-\d+',plan,re.M))==4
assert len(re.findall(r'^- \[[ x]\] \*\*P[0-7]-\d+',plan,re.M))==46
(HERE/'cp10-plan-after.md').write_text(plan,encoding='utf-8',newline='\n')
(HERE/'cp10-publication.json').write_text(json.dumps({'plan_before_sha256':EXPECTED_PLAN,
    'plan_after_sha256':sha(HERE/'cp10-plan-after.md'),'destination':str(ROOT/'docs/st67-reliability-transport-candidate-20261029'),
    'created_utc':now},indent=2)+'\n')
print(json.dumps({'suites':len(results),'groups':sum(x['printed_assertion_groups'] for x in results),
    'production_source_hashes':'unchanged','patch_apply_check':'PASS','plan_tasks':'4/46',
    'candidate':'NOT_APPLIED','prepared_report':str(OUT/'report.md')}))
