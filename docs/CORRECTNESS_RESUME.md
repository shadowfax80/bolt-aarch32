# ATFE correctness checkpoint - 2026-10-03

## Latest: item 6 ARM/Thumb far-call stage verified in 0044

Overlay 0044 fixes eight reproduced Thumb-caller far-stub link failures by
selecting the owning function's ISA builder, preventing cross-ISA stub sharing,
and using actual instruction lengths. All four caller/callee ISA pairs pass
normal/reverse layouts in both assertion modes: 80 transformed inputs, 40
baseline inputs and 128 rejected faults overall. Actual CPU traces verify the
ordered inputs/returns, SP and caller/stub/callee/return ISA states. Eight
grouping fixtures confirm same-ISA sharing and cross-ISA separation. All 89
Python tests pass; each build passes 37 ARM lit tests and 58 CoreTests/31 skips.
All 44 overlays replay exactly. This is bounded QEMU user-mode evidence, not
new Pi execution or a clean build. Item 6 and original #12 stay active; hardware,
remaining verification paths, automatic v7 thunks, near-range/split/cold matrices,
PMU and provenance remain open. See [scope](AARCH32_FAR_INTERWORK.md) and
[evidence](results/correctness_far_interwork_20261003.json).

Evidence/preimages are under `out/correctness/mixed-far-20261003`: probe and
probe-after, source, checked-on/run-efr9bfxz, checked-off/run-pjxh6sw1,
shared-stubs, replay, Python/ARM-lit/CoreTests logs, and script snapshots.
One-time source mutation, test addition and publication helpers already ran;
do not rerun them or overwrite evidence. Both llvm-bolt builds now contain 0044.
The live source's old marker files are not current provenance; the 44-patch replay
is the content check. Preserve dirty ATFE/LK, unrelated Microsoft/ and evidence.

Stop at this verified milestone under the user's standing instruction. On resume,
continue item 6 with bounded sparse/staged Pi far-call fixtures (padded user-mode
ELFs exceed the contiguous loader boundary), remaining verification-path audits
and broader coverage/oracle receipts. Do not advance to item 7 or weaken whole-LK
admission. Original #12 remains active, including PMU and clean-build work.

## Latest: item 6 A32 far-call execution stage verified

The legacy P5 gate now requires QEMU execution, an independent five-input
result/memory/NZCV/SP oracle, and exactly five observed veneer/callee visits.
Both assertion modes pass normal and reverse layouts: 20 transformed input
cases, ten baseline input cases and 28 rejected executable faults overall.
All 86 Python tests pass. A preserved bypass reproduction still exits 42 under
the former result-only oracle; the new gate rejects bypass and shortened-loop
cases, and missing QEMU cannot PASS. Fresh durable receipts bind options,
selected/emitted/eliminated/executed routes, tool/image/script/QEMU hashes and logs.
LLVM source remains at 0043. Item 6 and original #12 remain active: Pi,
Thumb/mixed far-call routes, the automatic v7 thunk caveat and remaining
verification paths are not closed. See [scope](AARCH32_FAR_EXECUTION.md) and
[evidence](results/correctness_far_execution_20261003.json).

Evidence: `out/correctness/far-execution-20261003` contains the preserved
legacy bypass reproduction, release-on/run-d_n1lrar and release-off/run-nltzaehx
receipts and traces, python-tests-release.log (86 pass), and source preimages/afterimages.
One-time reproduction/publication helpers already ran; do not overwrite evidence.
No Pi work or LLVM rebuild was done in this stage. Preserve dirty ATFE/LK and
unrelated Microsoft/. Stop at this verified milestone under the standing user
instruction. On resume continue item 6 with Thumb/mixed/hardware far-call
witnesses and the remaining verifier audit. Do not advance to item 7 or weaken
the whole-LK arm_reset admission guard; original #12 remains active.

## Latest: item 6 gate hardening verified; item 6 remains active

Item 6's first execution/result gate hardening stage is verified; item 6
remains active. Complete ordered workload repetitions, strict dump framing,
every-selected-redirect PC coverage, immutable upload/manifest/loader snapshots,
stable tool/script/revision receipts and watchdog-cleanup failure propagation are
enforced. Unsafe legacy ARM/Thumb counter hooks reject; section restoration is
exact and bounded. Generic comparisons explicitly claim output consistency only.
All five reproduced admissions reject, 80 Python tests pass, and the transport
matrix passes 7 admissions/80 rejections. Real ARM/Thumb host artifact builds pass
both modes. Fresh Pi pass matrices pass 420 positive cases and two expected faults
per build, with all eight images returning to the loader. The whole-LK attempt
still rejects an unsupported transfer in arm_reset; no whole-LK or rewritten
far-call execution is claimed. No LLVM source changes were made (overlay 0043).
Next is the remaining item 6 execution/oracle/legacy-path work; #12 stays active.
See [gate scope and remaining work](AARCH32_EXECUTION_GATES.md),
[evidence](results/correctness_execution_integrity_20261003.json) and
[status table](CORRECTNESS_PRIORITY_TODO.md).

Evidence/preimages/afterimages are in `out/correctness/execution-integrity-20261003`.
Final tests are `python-tests-release.log` and `python-test-result.json` (80 pass).
`before.json`/`after.json` preserve the five reproduced admissions and rejections;
`dump-boundaries.json` preserves seven valid sizes and 80 malformed cases.
`checked-host-builds` contains the final real ARM/Thumb artifact checks in both
build modes. `inline-on/off` contains fresh eight-image Pi build and verification
manifests; both modes pass 420 positive cases and detect both deliberate faults.
`full-on/full.log` is the rejected whole-LK diagnostic, not execution evidence.

One-time hook removal and source/evidence snapshot helpers already ran; preserve
the evidence and do not rerun fresh-directory builders blindly. LLVM source is
unchanged from 0043. Tool/revision hashes do not certify clean compiler provenance.

Stop at this verified stage under the user's earlier milestone instruction. On
resume, continue item 6 with independent ARM/Thumb/mixed execution witnesses,
additional inputs/state/memory/fault/timeouts, rewritten far-call coverage and
the remaining legacy/comparison-path audit. Do not weaken the arm_reset admission
guard to obtain a whole-LK result. Items 7/11 retain the automatic v7 thunk caveat;
10/14 retain PMU ownership and clean-build provenance. Original #12 stays active.
Preserve dirty ATFE/LK, unrelated Microsoft/ and all evidence.


## Latest: consolidated queue item 5 verified in 0043; milestone stop

Consolidated queue item 5 is scoped verified in overlay 0043 for the sealed
ARM counter and PC-sampling pipelines. Instrumentation records exact source-input
SHA-256 and descriptor owners; seals bind ELFs, map, image, tools and patch/source
identity. Capture, conversion and consumption reject stale artifacts and invalid
source offsets. Publication stages output bundles and rolls back caught errors;
crash/power-loss atomicity is not claimed. Both builds pass 300 cases each
(12 admissions, 288 rejections), focused suites 51/50 and CoreTests 58/31 skips.
All 65 Python tests and four wrapper rejection checks pass. All 43 overlays replay
exactly; fresh supported Pi bytes equal the executed 0041 payloads. Captures in
this milestone are synthetic host fixtures; no fresh hardware execution is claimed.
Legacy unsealed captures are excluded from verified optimization. Item 6 is next;
original #12 remains active, including PMU and clean-build provenance work.
See [the identity contract](AARCH32_PROFILE_IDENTITY.md),
[evidence](results/correctness_profile_identity_20261003.json) and
[status table](CORRECTNESS_PRIORITY_TODO.md).

Source identity: `65688953f330ecf099dea730d22e6bfc810d491bfd79d0152c7c741954204d03`.

Evidence and source preimages/afterimages are under
`out/correctness/profile-identity-20261003`. Final matrices are `checked-host-on/off`,
Python tests `python-tests-checked.log`, boundary reviews `checked-review-on/off`,
and exact source replay `replay/replay.json`. `positive-byte-parity.json` binds
fresh startup and IT payloads to executed 0041 verifications. Wrapper checks are
in `wrappers`. Initial failed test fixtures/logs are diagnostic only.

The one-time C++ mutation/export helpers already ran. Do not rerun them blindly:
`export-profile-identity.py` exported 0043 and preserved the live source. Both
LLVM builds are incremental; replay verifies source contents, not clean build
provenance. Counter seals must be made before capture; never certify an old dump
after the fact. Legacy QEMU/manual paths do not pass the verified pipeline.

Stop at this verified milestone under the user's previous instruction. When
resumed, proceed to queue item 6, execution/result gate integrity, including the
remaining original #12 work. Preserve dirty ATFE/LK, Microsoft/ and all evidence.
Automatic v7 thunk recognition and retained-target routes remain open in 7/11.


## Latest: consolidated queue item 4 verified in 0042; milestone stop

Consolidated queue item 4 is scoped verified in overlay 0042. Both ordinary
rewriting and instrumentation now reject PIE/shared inputs and unsupported
dynamic/TLS/GOT/PLT machinery, validate fixed LOAD/section mappings, and exclude
nonempty loaded sections at zero before the reproduced relocation assertion.
Both builds pass 192 cases (12 admissions, 180 rejections), focused suites 51/50
(one expected skip off) and CoreTests 58/31 skips. The 358-case ISA matrix remains
green. Runtime and counter pointers are checked at three fixed VMAs; nonzero
bias is unsupported. Fresh supported Pi payloads equal the exact executed 0041
bytes; no new Pi execution is claimed. All 42 overlays replay exactly.
Next is queue item 5, profile/artifact identity. Original #12 remains active;
no additional whole original workstream closes. See the
[fixed-load contract](AARCH32_FIXED_LOAD_CONTRACT.md),
[evidence](results/correctness_fixed_load_20261003.json) and
[status table](CORRECTNESS_PRIORITY_TODO.md).

Source identity: `528e9c72c362adef2700a093f11e026ccb2fe86a86f4643f673eea49ecb8ea93`.

Evidence, preimages/afterimages, initial zero-address assertion and final host
logs are in `out/correctness/fixed-load-20261003`. Final full-suite reviews use
`checked-review-on/off`; final replay is `replay-checked`. One-time source
mutation/export helpers already ran; do not rerun them blindly. The final export
helper is `export-fixed-load-checked.py`. Fresh byte-parity manifests use
`pi-final-on/off` and `it-final-on/off`, bound to the executed 0041 verifications.

Stop at this verified milestone under the user's previous instruction. When
resumed, proceed to item 5: exact profile/artifact identity, including all
remaining original #12 tasks. ATFE only. Preserve dirty ATFE/LK, Microsoft/ and
all evidence. Dynamic finalization and nonzero load bias remain unsupported.

## Latest: consolidated queue item 3 verified in 0041; milestone stop

Consolidated queue item 3 is verified within the initial conservative ISA/ABI
contract in overlay 0041. Both builds pass 358 admission cases (32 admitted,
326 rejected), focused suites 50/49 (one expected skip off) and CoreTests 58/31
skips. Generic ARMv7-A integer-only runtime, generated-form minimum-profile checks,
fresh Pi startup and 372-case IT/nested/reset matrices pass in both builds.
Static PIE remains admitted; queue item 4 is next. Automatic v7 thunk recognition
and retained-target routes remain open in items 7/11. #12 remains active;
no additional whole original workstream is closed. See the
[contract](AARCH32_ISA_ABI_CONTRACT.md),
[evidence](results/correctness_isa_contract_20261003.json) and
[status table](CORRECTNESS_PRIORITY_TODO.md).

All 41 overlays replay to exact live source. Identity:
`e8880ef1a0c90c4f027d898fc1c59fcf50b18e0b880d70eacd4d478c142f317c`.
Raw evidence/preimages/afterimages/build logs and Pi verification manifests are
in `out/correctness/isa-contract-20261003`. The runtime archives changed and all
fresh nested/IT payloads were executed, rather than relying on old byte parity.
Both deliberate reset faults were detected; all payloads returned to the loader.

One-time source mutation/export helpers for this milestone already ran. Do not
rerun them blindly. `export-isa-contract.py` produced 0041 and replayed the entire
series. `verify-isa-suites.py` passed both modes after fixing the integer-only
runtime symbol fixture; its review directories now exist, so choose fresh output
if repeating. Initial failed fixture/build logs are diagnostic only.

Stop at this verified milestone under the user's previous instruction. Next,
when resumed: item 4, fixed-load ELF/PIE admission. Preserve dirty ATFE/LK,
unrelated Microsoft/ and durable evidence. ATFE only; original #12 stays active.

## Latest: consolidated queue item 2 verified in 0040; milestone stop

Overlay 0040 fixes odd Thumb startup lookup and assertion/null handling. Both
builds pass 40 startup/static-finalization cases, focused suites pass 49/48 (one
expected skip off), and CoreTests pass 58/31 skips. The original F2 reproducer
instruments successfully in both modes. All 40 overlays replay exactly to live
source; identity fd6b513512ee07800b563b39542dca70e98f94c357cbcdc5a509e2981807409b.

Fresh final Pi baseline/normal/reverse runs pass per build. Actual ELF entry is
retained and followed by the shim into ARM runtime/trampoline/rewritten Thumb.
Checks include bounded odd return link, NZCV/R4/SP, quiet core zero, exact counter
one and watchdog return to the resident loader. Static finalization remains a
dummy return; dynamic user hooks and static-PIE admission are not certified.

Evidence/preimages/afterimages/failed fixture logs are in
out/correctness/thumb-startup-20261003; compact
[evidence](results/correctness_thumb_startup_20261003.json) and
[updated table](CORRECTNESS_PRIORITY_TODO.md) are tracked. One-time mutation/export
helpers already ran: fix-thumb-startup.py, refine-startup-test.py,
scope-startup-test.py, final-startup-test.py and export-startup-final.py. Do not
rerun blindly. verify-startup-suites.py needs fresh review output on another run;
its repeated review call hit the existing-directory guard after tests passed.
Final review runs have separate final-review-on/off directories.

Stop at this verified milestone under the user's previous instruction. Next,
when resumed: queue item 3, ISA/profile/ABI admission. All remaining original #12
work stays active; original #2/#8/#10 remain the only wholly scoped completions.
ATFE only. Preserve dirty ATFE/LK, durable evidence and unrelated Microsoft/.

## Latest: consolidated queue item 1 verified in 0039; milestone stop

Resumed per the consolidated queue. Overlay 0039 closes F1 for decoded original
function code by analyzing every exclusive load independently of entry metadata,
and rejecting stores without an analyzed local reservation. No first-entry-only
or complete-secondary-entry assumption is used to contain reservations.

Both builds pass 171 cases: 132 rejections/39 admissions. The 32 new entry-route
cases cover ARM/Thumb caller/callee pairs, direct/addend, MOVW/MOVT/BLX, aliases
and data pointers with unselected/explicitly skipped functions. Six additional
cases check unreachable stores, closed pairs and calls preceding a local pair.
The eight original F1 review admissions now reject before output. Focused suites
pass 48/47 (one expected debug-only skip off); both CoreTests pass 58/31 skips.
Fresh supported nested/IT payloads match all five previously executed 0036 bytes
per mode. No new Pi execution or runtime reservation failure is claimed.

Overlay/source preimages/afterimages, hashes and logs:
out/correctness/interior-reservations-20261003. Compact
[evidence](results/correctness_interior_reservations_20261003.json), with
[status table](CORRECTNESS_PRIORITY_TODO.md). One-time mutation scripts already
ran: resume-interior-reservations.py, refine-interior-fixtures.py and
finish-interior-fixtures.py. Do not rerun them blindly. The refined Thumb direct
entry uses A32 BLX to permit a halfword-aligned target; alias routes use pointers.

Stop at this verified milestone, respecting the user's previous instruction.
Next, when resumed: queue item 2, Thumb instrumentation startup SIGABRT/SIGSEGV.
All remaining original #12 work stays active in the queue, not paused. Original
#2/#8/#10 remain complete; no additional whole original workstream is closed.
ATFE only. Preserve dirty ATFE/LK, saved evidence and unrelated Microsoft/.

## Earlier: review through 0038 and prioritized work items published

The user requested a fresh correctness re-evaluation and publication of an
ordered work-item list. See [current review](CORRECTNESS_REVIEW_0038.md),
[priority queue](CORRECTNESS_PRIORITY_TODO.md) and
[fresh evidence](results/correctness_0038_review_20261002.json). Overlay 0038 is
included unchanged with this publication to preserve the assessed source.
No backend implementation changed during this review; no new Pi execution.

Fresh focused suites pass 48/47 tests (one expected skip off), both CoreTests
runs pass 58/31 skips, and 60 existing host script tests pass. All 38 overlays
replay to exact live source bytes without changing the dirty ATFE/LK trees.
Thirty-four boundary observations reproduce: unnamed interior-entry reservation
admission in skipped code (eight checked redirected routes), Thumb startup
SIGABRT/SIGSEGV, ARMv6 input receiving MOVW/MOVT, and static PIE with absolute
counter pointers/no output relocations. Missing attributes and BE8 flags are
also admitted without a certified contract. The previous 133-case gate remains
green, but its complete-entry-root assumption is insufficient.

Next implementation order, when requested: close the skipped interior-entry
reservation bypass; fix Thumb startup safely in both builds; enforce ISA/ABI
admission; enforce fixed-load/PIE policy. Then follow the published queue.
The earlier active-ISR-first order is superseded. Three original items remain
complete (#2/#8/#10). The user reactivated #12; all remaining profile identity,
execution-gate, PMU ownership and build-provenance tasks are included in the
consolidated active queue. Earlier pause instructions below are superseded. Review/publication is the
current milestone; no further fixes have begun. Preserve source, evidence,
unrelated Microsoft/ and the historical failed probes.

## Earlier: #6 cross-function reservation boundary verified; work stopped

Stopped at the next verified milestone as requested by the user. Overlay 0038,
`overlay/llvm/patches/atfe/0038-bolt-arm-cross-function-exclusive-reservations.patch`,
is exported locally and reverse-apply checked against the live ATFE source.
It is not committed or pushed; last pushed production checkpoint is 5049da5/0037.

The instrumentation gate now inspects original decoded function bytes, including
skipped/unselected callers, after secondary-entry discovery and before profiling
passes. Selected exclusive functions still reject. Skipped exclusive functions
must contain their reservations locally: live calls/returns/external branches,
unmatched stores, incomplete streams and unmodeled transfers reject. Known
multiple entries reject conservatively. Closed local pairs/retry loops and calls
before acquiring or after clearing a reservation remain admitted. Both states
are retained at CFG joins; ARM predication and Thumb IT are accounted for.

Both assertion modes pass 133 new cases (98 rejections, 35 admissions), all
156 existing exclusive cases (104 rejections, 52 relocation admissions), and
38 real decoder cases. Focused suites pass 48/47 tests, with one expected
debug-only skip off. Both CoreTests runs pass 58 tests with 31 expected skips.
Fresh supported nested/IT Pi builds match all five previously executed 0036
payloads in each mode. This reuses byte-identical hardware evidence; no new Pi
execution or runtime reservation-failure reproduction is claimed. Compact report:
[cross-function evidence](results/correctness_cross_function_exclusive_20261002.json).

Source preimages/afterimages/hashes, final build/lit/unit logs, export checks and
byte-parity evidence are saved under out/correctness/cross-function-exclusive.
The final supported builds are assertions-on-pi-positive/build-zkdad_tu and
assertions-off-pi-positive/build-0zkucepr. One-time mutation scripts already ran:
apply-cross-function-fix.py, classify-cross-function-exclusives.py,
refine-cross-function-fix.py, verify-cross-function-fix.py and
finish-cross-function-entry-boundary.py. Do not rerun them blindly. Preserve
failed intermediate logs as well as final evidence; generic mayLoad/mayStore
flags were insufficient and the final implementation uses explicit monitor kinds.

Resume only when requested. Next #6 scope is active ISR boundaries; #5 mixed-ISA
nested state/snapshots and #7/#9 general ISA/entry/symbol admission remain open.
No entire TODO item closed: three original items remain complete (#2/#8/#10);
#12 stays explicitly paused. ATFE only; upstream work remains stopped. Preserve
dirty WSL ATFE/LK source, this local overlay/docs, and unrelated Microsoft/.
All task builds/tests have finished; no task compiler/test/serial job remains.
WSL is responsive and may stop automatically while idle.

## Earlier: #6 cross-function reservation audit resumed

User selected this resume document; Ubuntu/WSL2 was restarted and responds to
uname. ATFE/LK initial dirty status and audited production-source hashes remain
unchanged. Latest verified production fix remains 5049da5/overlay 0037.

Cross-function host probes admit 96/96 instrumentation candidates in assertions-on
and assertions-off builds: all four ARM/Thumb caller/callee pairs, direct/indirect
calls, unselected/explicitly skipped callers, normal/reverse/conservative modes.
Each caller has LDREX, a call, then STREX; the instrumented callee contains counter
stores. Loaded ELF bytes and call routes were checked: 24 raw outputs already
reach the instrumented callee; 72 reach it after the existing entry-redirection
workflow. Independent branch decoding verifies redirects in both instruction
sets. No Pi runtime reservation failure is claimed; no production fix applied.

Evidence: out/correctness/cross-function-exclusive/probe-y8ygxq13, including
results.json, routes-checked.json, emitted maps, redirect reports and disassembly.
Compact report: results/correctness_cross_function_exclusive_audit_20261002.json.
The initial one-block callee probe emitted no counters; probe-es1klis7 records
counter emission only, before final call-route checking. Preserve these probes.

Next #6: design and implement the cross-function admission boundary covering
skipped/unselected callers, indirect reachability and ISR entry, then verify both
build modes and supported Pi fixtures. Active ISR/mixed-ISA coverage remains open.
#12 stays paused; ATFE only. No compiler/test/serial job remains active at this
checkpoint. WSL was responsive at the health check; it may stop automatically idle.

## Earlier: conversation closed at user request

Correctness work is stopped. Latest verified fix is pushed as 5049da5.
Windows confirmed no running WSL distributions at closure. Preserve all dirty
WSL ATFE/LK source, saved evidence and unrelated Microsoft/ directory.
No compiler, test or serial job was active at the last verified checkpoint.
Resume only when requested: next is #6 cross-function exclusive reservations,
then the remaining priority order in CORRECTNESS_TODO.md. #12 remains paused.
The earlier paragraphs describing WSL as running are historical checkpoints.

## Earlier: #6 exclusive-memory function exclusion verified

0036 is pushed as 127ba9d; its compact evidence/next audit checkpoint is c3a91e5.
Overlay 0037 rejects instrumentation of simple known-CFG ARM functions containing
exclusive accesses or CLREX. All ARM/Thumb LDREX/STREX/LDAEX/STLEX widths are
classified. Both builds pass 104 rejection/52 relocation cases, 38 actual decoder
cases (34 exclusive/monitor forms, four ordinary-memory controls), 47/46 focused
tests (one debug-only skip off), and 58 CoreTests/31 skips per mode.

Before: exclusive-instrumentation/probe-hi6v7oy4; all 24 emitted variants insert
counter store traffic between LDREX/STREX. No Pi runtime corruption reproduction
is claimed. Fresh supported nested/IT images match all five executed 0036 payloads
in each mode: assertions-on-pi-positive/build-lb10bwg1 and
assertions-off-pi-positive/build-asvog53k under exclusive-instrumentation. Hardware
evidence is reused through identical bytes; no new Pi execution for 0037. Report:
results/correctness_exclusive_instrumentation_20261002.json. Reverse-apply checked.

Source before/after/hashes, probes, decoder encodings and logs are saved under
out/correctness/exclusive-instrumentation. One-time scripts already applied:
apply-exclusive-instrumentation-boundary.py, refine-exclusive-decoder-tests.py,
finish-exclusive-decoder-tests.py; do not rerun them. The refinement first tried
to mutate immutable subtargets and failed compilation; the final test uses
feature-enabled copies and independent decoders, then passes both build modes.

This is a function-local exclusion. Next #6: reservations spanning calls into
separately instrumented functions, including skipped/unselected callers, and
active ISR boundaries. #5 mixed-ISA nested state/snapshots also remain. Separate
#9 deferred issue: pure-Thumb ELF-entry lookup asserts in createAuxiliaryFunctions;
probe-yozkp1rs preserves all failures. Equivalent A32-start/Thumb-function probes
pass. Assertions-off behavior is not claimed. No entry-point fix applied yet.

Three original items remain complete (#2/#8/#10); #12 stays explicitly paused.
WSL running, Pi waiting in loader, no active compiler/test/serial job at this
verified checkpoint. Usage-related pause cancelled after the five-hour reset.
ATFE only; no upstream work. Preserve dirty WSL ATFE/LK and unrelated Microsoft/.

## Earlier: #4 conditional-return instrumentation verified

0035 is pushed as 3e0e57c; 0036 is pushed as 127ba9d. Overlay 0036 rejects instrumentation of simple known-CFG
ARM functions with unmodeled conditional returns. Host proof:
conditional-instrumentation/before-probes/conditional-slrd322l; the BXEQ LR path
returns before either leaf counter and has no taken-exit CFG edge. Twelve old
instrumentation candidates were admitted. The new gate passes twelve rejections
and six normal/reverse relocation admissions in both modes. Focused suites pass
46/45 tests (one debug-only skip off) and 57 CoreTests/31 skips per mode.

Fresh nested/IT Pi builds: conditional-instrumentation/assertions-on-pi-positive/
build-d5fv3u4k and assertions-off-pi-positive/build-zg3fm5ln. Hardware evidence:
pi-verify-mg8qz6fj and pi-verify-mexmiqxb respectively. Baseline/normal/reverse/
conservative each pass 372 cases per build, totaling 2,976. Exact counts, real
runtime clears and operating contract pass; two bad-reset images fail as
required. All ten runs watchdog-return to the serial loader. All five payloads
match across modes. Evidence: results/correctness_conditional_instrumentation_20261002.json.

Preimages/afterimages/source hashes, host logs and probes are saved under
out/correctness/conditional-instrumentation. The one-time
apply-conditional-instrumentation-boundary.py is already applied; do not rerun it.
Source/test overlay 0036 reverse-apply checks against live source. Preserve dirty
WSL ATFE/LK and unrelated Windows Microsoft/. General conditional-exit CFG
modeling, other special/trap transfers and broader/profile-driven pass coverage
remain. Three original items complete (#2/#8/#10); #12 remains explicitly paused.
ATFE only. No upstream work. The planned usage-related pause was cancelled
after the five-hour window reset to 99% remaining; WSL stays running for continued
work. No compiler, test or serial job remains active at this verified checkpoint;
the Pi returned to the loader. Next active audit: #6 exclusive-memory boundary.
Source inspection is saved in out/correctness/exclusive-instrumentation/source-audit.log;
no exclusive-memory production fix has been applied. #12 remains paused.

## Earlier: #4 exception-return admission verified

0034 is pushed as a14fc05. Overlay 0035 rejects decoded ARM/Thumb RFE, ERET and
Thumb exception SUBS PC,LR before the ordinary-return/PC-definition exemptions.
Both builds pass 56 negative admissions, attribute-decoded ERET rejection,
fourteen actual decoder cases and the ERET descriptor gate. Focused suites pass
45/44 tests (off has one debug-only skip) and both pass 57 CoreTests/31 skips.
Fresh supported Pi builds match all eight executed 0034 payloads per mode:
exception-returns/assertions-on-pi-positive/build-3q6tmi1q and
exception-returns/assertions-off-pi-positive/build-n8itz8y4. No fresh Pi execution
is claimed for 0035. Evidence: results/correctness_exception_returns_20261002.json.

Preimages/postimages/source hashes, initial failed test logs and final host logs
are in out/correctness/exception-returns. apply-exception-return-boundary.py and
refine-exception-return-tests.py are already applied; do not rerun them. The
refinement preserves supported UDIV byte checks and turns decoded ERET into a
negative feature-admission case. The new patch reverse-apply checks. Preserve
the dirty WSL ATFE/LK source and unrelated Windows Microsoft/ directory.

Next #4: conditional exits under instrumentation/reordering/splitting and other
special/trap transfers. Undecodable ERET still falls under the existing kept/
ignored decoder policy; #7 general ISA/feature admission remains open. Three
original items complete (#2/#8/#10); #12 remains paused. ATFE only, WSL running,
Pi waiting in loader. No upstream work.

## Earlier: #4 expanded pass and call-site matrix verified

0033 is pushed as 796083d. Test-only overlay 0034 expands the inlining gate to
92 emitted cases and four IT-call rejections per host build. Focused suites
pass 44 assertions-on / 43 assertions-off with one expected debug-only skip.
Six parser tests pass. Both Pi builds run seventy cases each in baseline,
forced normal/reverse, automatic, size-based and reverse-plus-peepholes variants:
840 positive cases, four expected faults and sixteen watchdog returns. All
eight payloads match across build modes. Safe same-ISA leaves inline; predicated,
indirect and mixed-ISA calls remain. Unsupported IT calls reject without output.

Builds: inline-safety-passes-pi/build-ij4gfthz and
inline-safety-passes-pi-noasserts/build-c6yymiw8. Hardware evidence directories:
pi-verify-_6pe0j7y and pi-verify-3t9s94ww respectively. Tracked evidence:
results/correctness_inline_passes_20261002.json. Scratch/preimages/source hashes
and host logs: out/correctness/inlining-passes. The one-time
extend-inline-pass-tests.py has already applied both host test edits; do not
rerun it. Overlay 0034 reverse-apply checks against the live source.

Next #4: wider conditional exits and special/privileged control transfers;
profile-driven splitting and broader pass combinations remain. Three original
items remain complete (#2/#8/#10). #12 stays explicitly paused. ATFE only,
WSL running, Pi waiting in loader; no upstream changes. The peepholes option
run does not prove every peephole transformed code. Current fixture is quiet
HYP/core zero with masked interrupts and parked secondary cores.

## Earlier: #4 unsupported PC-write boundary verified

0032 is pushed as 66f1df1. The next audit confirms a PC-relative computed jump
corruption: MOV PC,PC followed by an eliminated MOV r1,r1 changes the jump's
destination. Host probes: pc-write-safety/probe-vt7v4pa8 (ARM and Thumb).
Pi reproduction: pc-write-safety/pi-pre-w9q2ik23/pi-verify-45fa4t2b. Baseline
passes all 55 cases; the pre-fix ARM rewritten body returns 0 instead of 18
at case 0. Both payloads watchdog-return to loader.
Local overlay 0033 rejects unsupported PC-writing transfers during disassembly
and limits load-multiple returns to canonical updated-SP IA pops. Variable
load register lists now report PC definitions. The exact known eight-byte
A32 absolute veneer remains admitted; its shared recognizer is used by both
disassembly and the previous fallthrough guard. Preimages/afterimages/source
hashes and logs are in out/correctness/pc-write-safety. Reverse-apply checked.
Assertions-on passes 44 focused tests and 56 CoreTests/31 expected skips,
including 36 negative admissions, 16 safe admissions and 18 decoder cases.
Assertions-off passes 43 focused tests (one debug-only skip) and the same
56 CoreTests/31 skips. Both builds reject the exact hardware reproduction input
without creating output. Fresh positive/fault payloads are byte-identical to
all five executed 0032 images in both modes: assertions-on-pi-positive/
build-xqw_q3gv and assertions-off-pi-positive/build-q89az817 under pc-write-safety.
This reuses the earlier hardware proof by identical bytes; no new positive Pi
execution is claimed for 0033. Evidence:
results/correctness_pc_write_admission_20261002.json. Overlay 0033 is verified.
Do not rerun apply-pc-write-safety.py: it failed while extracting a two-byte
Thumb instruction after applying the first three files. finish-pc-write-safety.py
completed the decoder fixture and sealed source-change.json. Both are one-time
mutation scripts; source now contains the complete local fix.
#12 remains paused; ATFE only, WSL running, Pi in loader. No upstream changes.
Next #4: wider predicated-exit and pass combinations; special/privileged control
transfers need further admission review. Three original items remain complete.

## Verified checkpoint: mandatory inlining safety and both-path Pi verification

0031 is pushed as 4070942. Local overlay 0032 makes the ARM callee safety
filter mandatory under --force-inline, including function-owned metadata/CFI.
The old override emits unsafe stack/LR/SP/PC/literal/CFI callees and crashes
on nested calls and multiple entries. Before: inlining-safety/inline-t5zplwtd.
The first stricter filter also rejected a safe ARM leaf: BX LR decodes as
BX_RET with implicit LR. A target query now recognizes only unconditional
side-effect-free BX LR forms; seven actual decoder cases guard it.
Both builds pass 43/42 focused tests (off has one debug-only skip), and
55 CoreTests with 31 expected skips. Forty force-inline emission cases pass.
Final Pi builders: inline-safety-pi/build-ja5rnarx and
inline-safety-pi-noasserts/build-zgvlajl5. The verifier passes
55 cases each in baseline/normal/reverse, plus bad-result and bad-cbz-flags.
It checks SP balance, LR dependence, ARM conditional-return paths, safe
multi-block inlining, and CBZ/CBNZ expansions with flags consumed on both paths.
Evidence: pi-verify-tr7mzdeb / pi-verify-j2rhqj7c under the respective builds.
All five payloads are byte-identical between modes. Both faults fail exactly
where expected; all ten firmware runs return to loader. Exported overlay 0032
passes reverse-apply check. Tracked evidence:
results/correctness_inline_safety_20261002.json. Portable workflow:
PI_INLINE_SAFETY.md. Logs/preimages/scripts in out/correctness/inlining-safety.
#12 remains paused; ATFE only, WSL running, Pi waiting in loader.
Next: wider PC writes, predicated exits and transformation admission boundaries.

## Earlier checkpoint: overlays 0030/0031

Overlay 0030 is pushed as 39bd782. #4 self-move audit confirms that the old
no-op classifier deletes flag-writing MOVS before a flag-consuming branch.
Local overlay 0031 preserves CPSR/PC side effects, and fixes a 0030 regression:
Thumb CFG NOP annotations must use the primary builder's worker allocator and
generic annotation index. Semantic queries still use the mode-specific builder.
Assertions-on focused lit passes 42; assertions-off passes 41 with one debug-only
skip. Both modes pass 54 CoreTests with 31 expected skips. New gates cover twelve
mixed-mode emitted self-moves and nine actual decoded flag/PC forms. Hardware
flag-state verification now passes in both modes; 0031 is ready to push.
Use build_counter_state.py --flag-self-move. The negative-R0 sentinel intentionally
sets N=1/Z=0 and preserves C/V/Q/GE/control; bad-flags replaces MOVS with NOP and
must fail at case 0/CPSR field 15. Baseline/generated each run 512 cases. Artifacts:
self-move-state-pi/build-692hq5t8 and self-move-state-pi-noasserts/build-rzet_h4h.
Pi evidence is pi-verify-ce7eip_5 / pi-verify-oyfcewwx under those builds. All six
images match across modes and return to loader. Tracked summary:
results/correctness_self_move_flags_20261002.json. Final build-6lofcngc and POP
build-lf_p8za7 produce byte-identical payloads to their executed fixtures.
Source preimages/postimages/logs are in out/correctness/control-flow. #12 paused.
Next investigate conditional returns, other PC writes and --force-inline safety
(the current override bypasses the ARM callee safety filter). ATFE only.

Overlay 0029 is pushed as bb36795. Overlay 0030 is verified and ready to push:
residual reachable function fallthrough rejects before CFG postprocessing;
CFG construction/branch repair use the function's ARM/Thumb builder; invalid
postprocessed ARM CFG no longer falls back to ignored code. Fatal ARM CFG
admission exits after workers join. Exact SP/+4 single-register POP-to-PC is
recognized from real ARM/Thumb decoder bytes. An exact eight-byte A32 absolute
veneer remains admitted for the later existing removal pass; fake names reject.
Host: 41 lit passes assertions-on, 40 plus one debug-only skip off, 53 unit
passes/31 skips each. Dedicated gates: 20 fallthrough rejections, 18 safe
admissions, nine decoder cases. Both Pi POP-state runs pass 512 baseline plus
512 generated cases and all three faults; all five payloads match across modes
and return to the loader. Evidence: pop-state-pi/build-nzl_pe_m/pi-verify-bu9o58sn
and pop-state-pi-noasserts/build-tcd236d1/pi-verify-m_mgl8xl; tracked summary
results/correctness_cfg_fallthrough_20261002.json. Fresh IT/nested build-ud1tq93u
emits the same five payloads as previously verified build-y4njbgkd.
Next #4: conditional-return exit edges, broader PC writes, live flags and pass
safety. #3 remains partial for wider CFG audits; three original items complete.
#12 remains explicitly paused. WSL running, Pi waiting in loader. ATFE only.
The preparation/build notes below describe earlier stages of this same fix.

Overlay 0028 is pushed as e9cd3b3. Local overlay 0029 removes ARM pseudo-count
repair/ignore and makes mismatches fatal with or without assertions. Three new
unit tests demonstrate that bypassed bookkeeping fails safely; the pre-fix
negative tests fail to die. Assertions-on CoreTests pass 52 with 31 expected
skips, 40 focused lit tests pass, and the Pi matrix passes 372 cases per mode
plus the reset fault (build-y4njbgkd/pi-verify-i5ztmgnx).
The separate Release/assertions-off build is complete under
/home/user/bolt-aarch32/out/correctness/build-atfe-noasserts-20261002; logs and
preimages are in out/correctness/cfg-invariants. Both modes pass 52 unit tests
with 31 expected skips. Release lit passes 39 with one assertion/debug-only
skip; that alignment fixture's ARM/Thumb semantic checks pass separately.
Release Pi evidence is it-counts-pi-noasserts/build-_sc6r4kw/pi-verify-l278wktj:
372 cases in all four modes, reset fault detected, all loader returns. All five
payloads match the assertions-on build byte for byte. Tracked summary:
results/correctness_cfg_pseudos_20261002.json. Overlay 0029 is ready for push.
Live source and dirty WSL/LK state are preserved.

The next linked Thumb probe confirms postProcessBranches synthesizes A32 BX LR
inside Thumb output at 0xa008. Evidence: cfg-invariants/postprocess-nn9ugli2.
A fix selecting the function builder, rejecting unmodeled ARM fallthrough and
failing invalid postprocessed CFG is prepared in cfg-postprocess/{before,after}.
It has not been applied to live source. The broader fallthrough-44jxz10f probe
confirms ARM/Thumb entry, final-call and conditional-boundary cases also emit
unsafe output. Prepared v2 rejects residual fallthrough during buildCFG before
branch postprocessing, covering those paths; v1 is preserved separately.
ATFE only; #12 remains explicitly paused. WSL is running.

Overlay 0028 enforces --arm-instrumentation-contract=privileged-single-core-no-fiq,
rejects default/explicit call profiling, dynamic/shared executables and process/
fork options. All 40 focused tests pass, including eight direct invocation
rejections. The Pi passes 372 cases each in four modes with CPSR privilege/IRQ/
FIQ, MPIDR core-zero and stack-alignment checks before/after measured calls.
Bad-reset fails exactly as expected; all five images return to the loader.
Nine host gate tests pass. Evidence: it-counts-pi/build-zfrqcy51/pi-verify-vptkzc7r
and correctness_instrumentation_scope_20261002.json. The LK wrapper requires
explicit ARM_INSTRUMENTATION_CONTRACT rather than acknowledging it by default.

#6 is partial: exclusive-memory insertion and active ISR boundaries remain.
#5 is partial: mixed-ISA nested state, active interrupts, additional predicate/
pass combinations and live snapshots remain. Three original items are complete.
Next inspect #3's debug-only pseudo recovery and assertion parity; source
preimages are to be saved in out/correctness/cfg-invariants. Then continue #4,
#1, #9, #7 and #11; #12 remains explicitly paused. WSL is running. ATFE only.
The older priority and pause checkpoints below are historical.

Actual linked runtime reset now passes the 372-case matrix in all four modes.
The bad-reset image fails at case 0/seed 0/field 2000, actual 0x12345678, proving
that clear was not replaced by fixture-side zeroing. All five images return to
the loader. Eight host gate tests pass. Evidence: it-counts-pi/build-oxagizx9/
pi-verify-0qqt43k2 and correctness_runtime_clear_20261002.json.
Next enforce the instrumentation operating boundary under #6; #5 remains
partial for live snapshots, active interrupts and mixed-ISA nested state.
Preimages for #6 are preserved in out/correctness/instrumentation-scope/before
and before-manifest.json. No scope source edits have been made at this point.

Overlay 0027 is pushed as be09efb. The expanded fixture adds nested Thumb calls
and recursion (two caller levels; n=0,1,2,3,8,17,33,64, maximum 65 frames).
All four Pi images pass 372 cases each, including original IT cases plus 72
nested/recursive seeded cases. All 85/85/73 slots match independent cross-function
path counts, and all images return to the loader. Six host gate tests pass.
Evidence: it-counts-pi/build-i6hc3l6i/pi-verify-j59k8mxz and the tracked
correctness_nested_counts_20261002.json. Run build_it_counts.py --nested to
reproduce. No backend change was required. Next validate actual runtime clear
and define snapshot/quiescence boundaries, then enforce #6. Active interrupts
and mixed-ISA nested state are still open; #12 remains separately paused.

WSL is running. Overlay 0027 normalizes terminal direct IT branches before CFG
construction and rejects unsupported IT control transfers/interior entries.
All 39 focused ARM/JITLink tests pass; the new lit test covers seven rejection
boundaries. The Pi passes 300 cases each for baseline/normal/reverse/conservative
images (1,200 total), all fifteen IT data masks, narrow/wide terminal branches,
loops, per-case reset, low carry and uint64 wrap. Counts are checked against
independent path models, with 81/81/71 measured slots. All four images returned
automatically to the loader on COM5. Evidence: it-counts-pi/build-9q43m0w3/
pi-verify-0b960t99 and results/correctness_it_counts_20261002.json.
Reusable build/verify scripts are scripts/pi4/build_it_counts.py and
verify_it_counts.py. The tracked builder's fresh build-gqwkbnr0 also passes
host modeling. Exact preimages/postimages remain in it-branch-fix.

Three original items are complete (#2/#8/#10); #5 stays partial. Next: remaining
reset/snapshot/CFG cases and operating contract #6.
#12 stays explicitly paused. Order remains #5, #6, #3, #4, #1, #9, #7, #11, #12.
The host-only test also reproduced the existing odd Thumb entry instrumentation
assertion (Instrumentation::createAuxiliaryFunctions Start lookup); retain that
negative evidence in it-branch-fix/patch-before-test-revision.patch and earlier
logs for #9. Do not infer it is fixed by the IT patch.
ATFE only; preserve dirty WSL source and unrelated Microsoft/. Older stop and
priority instructions below are historical and superseded by this checkpoint.

## Previous: overall work stopped by user

User requested stopping and resuming in a new session. Do not resume until asked.
WSL inspection reports no running distributions; do not restart it merely to
make the pause checkpoint. No build, test or serial process is currently known
to be running. Pi last returned to the serial loader after the state tests.

Latest verified GitHub implementation/tests: `c2b9b5c` (counter-state tests).
Three original items are complete: #2, #8 and #10. #5 is partial and paused with
the overall work; #12 remains separately paused by user. Resume order is
#5, #6, #3, #4, #1, #9, #7, #11, then #12. ATFE only; no upstream work.

Unfinished #5 work found a confirmed terminal-IT branch defect. Before the fix,
IT-predicated `t2B` was treated as unconditional, reachable loop code was removed
and a counter was emitted inside IT. Original evidence is
`out/correctness/it-probe-1ha37uvl`. A local fix normalizes terminal direct IT
branches to explicit conditional branches, shortens/replaces their IT header,
and rejects unsupported IT control transfers and branches into IT bodies.
The assertions-enabled ATFE build passed; the small normal/reverse/conservative
host probe now retains the loop. Evidence: `out/correctness/it-probe-s6enm8m7`.
This fix is **not fully verified, exported, committed or pushed**. No Pi run or
full lit run has been performed for it. Preserve the dirty live ATFE source.

The three changed files are `bolt/include/bolt/Core/MCPlusBuilder.h`,
`bolt/lib/Target/ARM/ARMMCPlusBuilder.cpp` and `bolt/lib/Core/BinaryFunction.cpp`.
Exact preimages/prepared postimages, hashes and successful build log are saved
under `out/correctness/it-branch-fix/{before,after}`, `source-change.json` and
`build.log`. `out/correctness/apply-it-branch-fix.py` already applied the edits;
do not rerun it against modified live files. Audit and probe scripts are retained.

The unfinished wider fixture has 47 functions: all fifteen data IT masks,
fifteen terminal-branch masks in both widths, and narrow/wide loops. Its driver
is `out/correctness/build-it-counts-pi.py`; new untracked firmware source is
`scripts/pi4/fixtures/it-counts/main.c`. Fresh failed attempts are preserved in
`out/correctness/it-counts-pi`. The driver currently stops while constructing
the narrow-loop expected-count model (`target not modeled`, offset 26). Its
post-link narrow branch plus NOP creates a separate fallthrough block before
the original loop exit; model that block explicitly rather than changing the
backend to fit the test. Earlier global trace labels accidentally became
secondary entries; they were replaced with temporary object-only labels.

Next on explicit resumption: repair the fixture path model, validate every
selected emitted function/IT group and exact counter assignment, add negative
IT tests, run focused lit and Pi checks, then export/review/push the verified
fix. Nested execution and wider reset/snapshot/CFG cases still remain under #5.
The Windows unrelated untracked `Microsoft/` directory is untouched. All scratch
evidence and WIP scripts are local and ignored by Git; retain this workspace.

## Active implementation after review

User explicitly paused item #12 on 2026-10-02 and requested moving to the next
items. #5 is now active. Overlay 0026 fixes full-width carry and restores flags
as well as IRQ state; R0-R3 use a 16-byte frame. 38/38 focused host tests pass,
including independent ARM/Thumb assembly-byte checks. Pi baseline/zero/seeded
images match all 18 outputs and all eight counters satisfy seed plus measured
count. Metadata attributes overflow slots to Thumb IT (index 1, 999999) and
ARM interwork (index 4, 9999). Evidence: counter-carry-pi/pi-verify-sj3t6e_m and
docs/results/correctness_counter_carry_20261002.json. Source preimages are in
instrumentation-audit/source and counter-carry-fix/before.cpp; zero-run snippets
before the fix are preserved in counter-carry-before. The dirty LK source was
not changed; hardware images derive from the existing independent baseline ELF.
Dedicated leaf state cases now pass on Pi: 512 baseline and 512 instrumented
ARM/Thumb cases preserve R0-R12, LR/SP and full CPSR, with all NZCV/Q patterns,
sixteen GE patterns, both IRQ masks and four seeds including uint64 wrap.
Three faulty images fail at expected checks; all five images watchdog-return
to the loader. Six host parser tests pass. Evidence is counter-state-pi/
build-ro6zv3x6/pi-verify-haiq1khs and the tracked counter-state result JSON.
The new build/verify scripts and fixtures are in scripts/pi4; no backend changes
were needed beyond 0026. Next: IT, nested execution and wider exact-count
coverage. Continue #6, #3, #4, #1, #9, #7 and #11 before
returning to #12. This supersedes the older instruction to finish #12 first.
Verified #12 work is pushed as 43c9e16. The unfinished content-state prototype is
saved in out/correctness/atfe-content-stamp-wip.py and .patch; it is untested,
not installed in WSL and not committed. The tracked verifier was restored to
the pushed version. Preserve this checkpoint for #12 resumption.

Latest work: overlay 0025 exports the four unrecorded ARM attribute/kept-code
changes and fixes the kept A32 write/rejection boundary. Source preimages are
preserved in out/correctness/kept-arm-fix/before*, and the original audit diff
remains untouched. All 25 patches reproduce live source exactly in
out/correctness/atfe-clean-replay-0025-final-20261002 (source identity c390d7d0...).
37/37 focused lit, twelve linked-ELF probes, 25/25 profile/replay and 14/14 execution
gate tests pass. The final fresh candidate is out/correctness/full-gate-0025-final;
its Pi check passes on COM5 after a physical power cycle: all 18 workload outputs,
ten repetitions, 33,850 kept/taken PCs and rewritten IT/interwork/memcpy samples
(2,507/30/14). The COM6-missing and COM5 reboot-timeout attempts are retained.
Evidence: docs/results/correctness_atfe_0025_20261002.json and
full-gate-0025-final/pi-verify-58wpzrs6. Do not claim Pi execution of
--use-old-text or privileged ERET from the regular full-image gate. The builder
now rejects text-placement overrides. #12 remains active; next finish content
stamps/clean provenance, counter identity, core ownership and the other gates
before advancing to #5. WSL remains running and the dirty parent is preserved.

The paragraphs below retain historical checkpoints and evidence. Their older
priority/pause instructions are superseded by the active checkpoint above.

Sampling identity fixes and bound-profile Pi evidence are pushed as bf69f15.
The next #12 replay audit applies all 24 ATFE patches in an isolated file tree,
but finds source-content differences in RewriteInstance.h, BinaryContext.cpp,
BinaryFunction.cpp and RewriteInstance.cpp. Live additions include ARM attribute
feature propagation and ignored-code/branch handling for -use-old-text; these
are absent from the GitHub overlays. The source was preserved, and the full diff
is saved in out/correctness/atfe-clean-replay-20261002/unexported-source.diff.
No uncovered source files were found. The verifier's changed-content/preservation
regressions pass (25 profile/replay tests total). Review/export those existing
changes with focused tests, then obtain successful replay and migrate content
stamps; do not overwrite live code or infer clean binary provenance from patch hashes.
See ATFE_OVERLAY_REPLAY.md and results/correctness_atfe_replay_20261002.json.

Latest local work adds sampling build/capture/profile identity and a pure ARM
ELF32 parser in scripts/profile_identity.py. The collector uploads isolated
session copies and checks workload repetitions, buffer/count/saturation and
PMU/core reports. Conversion validates source-function offsets and tool identity;
debug-unbound outputs cannot pass the optimization profile gate. The ARM no-LBR
wrapper and explicit full-image --profile path consume sidecars. Counter profiles
remain unbound; do not claim #12 closed or advance to #5 yet.

Twenty-three profile host tests and fourteen execution-gate tests pass. The independent
lk.elf/lk.bin fixture seals against actual ATFE tool/patch hashes. Real perf2bolt
synthetic diagnostics and the 61-counter/3520-byte conversion pass; synthetic
samples are explicitly unbound. Power cycling recovered the Pi on reassigned COM6.
Fresh bound capture passes with 6,772 samples/two workload repetitions. A duplicate
acc/sink repetition bug was fixed; strict conversion rejects unbounded arch_idle,
while explicit benchmark projection records exclusions. Real scoped conversion,
wrong-payload/ELF negative gates and failure preservation pass. Its full-image
candidate (411/417 emitted, four redirects) passes ten repetitions/all 18 outputs;
33,850 PCs observe rewritten IT/interworking/memcpy (2,506/24/16), far-call zero.
Evidence: out/correctness/sampling-bound and full-gate-bound; tracked summary
docs/results/correctness_sampling_bound_pi_20261002.json. WSL is running; dirty
source and unrelated Microsoft/ were preserved. Next finish counter identity,
clean replay/content stamps and the other #12 gates before advancing to #5.

User authorized proceeding in the updated priority order. #12 complete-result and
truncated-profile fixes pass 10/10 host tests plus real ATFE sample/61-counter
conversion checks. See CORRECTNESS_FIXES.md. The independent memcpy/far_call/
it_cond/interwork results have been added and built in an isolated LK snapshot at
WSL `out/correctness/lk-oracles`; original WSL source/images remain untouched.
Pi baseline and redirected images match on all 18 workloads; the four new values
match independent calculations. PC samples observe rewritten IT/interworking/memcpy;
far-call has no sampled PC. Current evidence is Windows
`out/correctness/validation-fix/` and the tracked
`docs/results/correctness_validation_20261001.json`. WSL was restarted for these checks.

The corrected full-image builder emits 411/417 functions and explicitly redirects
four. Its Pi gate passed 18 workload results across ten repetitions and observed
rewritten IT/interworking/memcpy (2,506/27/16 PCs). Far-call remains unobserved.
Thirteen host gate tests pass. Evidence: out/correctness/full-gate and tracked
docs/results/correctness_full_gate_20261001.json. Complete #12 before advancing:
profile/image binding, graph consistency, other execution gates, broader input/pass
coverage and clean overlay replay. User explicitly requested #12 completion first.
The reviewed bbae817 full-image script restored originals without redirects; its
replacement has explicit redirects and scoped hardware verification. Upstream
work remains stopped; preserve dirty WSL checkouts and unrelated Microsoft/ folder.

## Latest checkpoint: GitHub bbae817 re-evaluation

The Windows checkout was fast-forwarded from ff7d544 to bbae817. The current
review is CORRECTNESS_REVIEW_BBAE817.md, and the original twelve-item status/TODO
files have been updated. This task reviewed correctness; it did not implement
new backend fixes. Do not resume from the older priority order below.

Fresh host validation: 36/36 BOLT ARM + JITLink AArch32 tests pass. Overlay 0024
reverse-checks against the live WSL source. The dirty WSL parent still reports
eab1e71 and ATFE base bcc088849; both were preserved. No broad WSL sync/reset was
run. Review source snapshots, isolated ELF output and negative-probe logs are
saved in Windows out/correctness/review-bbae817; compact results are tracked in
docs/results/correctness_bbae817_review.json. No new Pi run was performed.

First work on resumption: #12 execution proof and complete independent results.
Full-image postprocessing reproduces original text, entry and pointer-bearing
sections without redirecting execution; 403/411 emitted symbols is not runtime
coverage. The Pi pass gate accepts a one-workload baseline, and truncated counter
dumps still become [7, 0]. Then follow CORRECTNESS_TODO.md's updated order.

WSL access was obtained through scoped approvals for inspection, tests and
isolated repros. `wsl --shutdown` completed successfully, and `wsl --list --running`
confirmed no running distributions at the end of this review. Restart with `wsl -d Ubuntu --cd
/home/user/bolt-aarch32` when work is resumed.

## Earlier implementation checkpoint (before external work)

The user requested a graceful pause. Do not resume work until asked. Scope is
ATFE only; do not work on upstream LLVM. Hardware has priority over QEMU.

Windows checkout: `C:\Users\User\CURSOR\CodexProjects\BOLT_AARCH32` on `main`.
WSL checkout: Ubuntu `/home/user/bolt-aarch32`; ATFE source at
`third_party/llvm-project-atfe`, build at `build-atfe`. The WSL parent and ATFE
checkouts contain preexisting dirty overlay changes: preserve them and do not
reset or stash. Windows has an unrelated untracked `Microsoft/` directory:
leave it untouched. WSL can be restarted with `wsl -d Ubuntu --cd
/home/user/bolt-aarch32` after the deliberate `wsl --shutdown` at this pause.

Verified changes: overlay 0020 fixes CBZ/CBNZ long branches without changing
NZCV and was pushed as `10afe0c`. Overlay 0021 handles odd Thumb `e_entry`,
moved Thumb function symbols, and even `$t` mapping symbols. Its focused
regression checks entry, moved `_start`/`probe`/`probe_nz`, and `$t`; the 32-test
BOLT ARM + JITLink AArch32 run passed. Full LK emission passed. The rebuilt
Pi image redirected `app_start_by_name` and `strtoul`; both original and
rewritten images booted and ran seven benchmark commands with matching dumps.
The Pi LK image uses an ARM entry, so this does not execute the synthetic odd
Thumb entry. `docs/CORRECTNESS_FIXES.md` has details and coverage limits.

Evidence is in ignored `out/correctness/` and WSL
`/home/user/bolt-aarch32/out/correctness/`: Pi logs/JSON, the fixture ELF and
function map, and the full LK output. The scratch script
`out/correctness/check-review-delivery.py` still expects the old Thumb-entry
assertion and must be updated before using it again. Overlay 0021 was exported
from the live tree and passed `git apply --reverse --check` there.

Next: finish item #9 for aliases, skipped functions, secondary symbols,
code/data transitions and pointer targets. Then #12 artifact/profile integrity,
#1 relocation matrix, and #3 CFG invariants. Item #4 still needs conditional
return/PC-load work and dedicated Pi execution of both flag-sensitive paths.
See `docs/CORRECTNESS_STATUS.md` and `docs/CORRECTNESS_TODO.md` for all 12 items.

Before further WSL shutdowns, allow builds/tests to finish, save patches and
results to durable files, and run `wsl --shutdown` from Windows. Confirm no
distribution remains in `wsl --list --running`.
