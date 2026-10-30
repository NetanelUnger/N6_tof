# CP10: isolated SPI ambiguity fence and manual Cloud result

Recorded UTC: 2026-10-29T08:49:49.283425+00:00. Source: `5432d4ae2b10ef7ecdfaedad586038792f0a4db5`,
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
