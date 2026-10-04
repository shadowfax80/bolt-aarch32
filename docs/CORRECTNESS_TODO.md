# ATFE correctness TODO

## Latest: item 6 PC-read admission fix and four-entry integer fixture verified

Overlay 0045 closes a reproduced position-dependent PC-read defect. Eight ARM/
Thumb normal/reverse candidates previously faulted after moving a PC-derived
address; both builds now reject before output/map publication while originals
still exit 42. Each build passes 189 admission cases (145 rejections, 44
admissions). ARM/JITLink suites pass 53/52 with one expected release skip;
CoreTests pass 58/31 skips per build. All 45 overlays replay exactly.

A separate explicitly integer-only LK fixture emits, redirects and executes
all four selected ARM entries, including memcpy, in both builds. All eighteen
outputs match fresh baselines. The original NEON memcpy remains excluded;
independent oracles and whole-LK rewriting are not certified. The historical
Pi far-safety fixture uses MOV-PC witnesses now excluded by 0045; compatible
live witnesses and fresh hardware verification are pending. See
[contract](AARCH32_PC_READ_ADMISSION.md) and
[evidence](results/correctness_pc_reads_20261004.json).

Item 6 and original #12 remain active. The latest user instruction is to stop
when all P0 items are complete, before starting P1 work; it supersedes the
historical milestone-stop instructions below. Continue the remaining P0 oracle,
execution-gate, manual-hook and durable-evidence requirements. Do not weaken
whole-LK admission, close #12 prematurely or advance to priority 7.

## Latest: item 6 scoped QEMU rewrite execution verified

Both assertion-mode builds emit, redirect and execute three explicitly selected
ARM benchmark entries inside a linked 64 KiB kernel reservation. Live CPU frames
check original/emitted PCs, ISA, SVC mode and unchanged redirect input state.
All eighteen candidate outputs match fresh baselines in each build. Six artifact/
selection faults reject before boot without receipts. The identity wrapper passes
the valid three-function scope and rejects the default skipped-memcpy selection,
unreserved input and disabled boot. All 130 WSL tests pass; Windows passes with
four Linux process-ownership skips. Identity/P4 use strict artifacts and execution
instead of an overwrite banner.

The caveat is published: retained original entries can match outputs without
executing emitted code. The explicitly redirected unreserved image reaches its
emitted entry then aborts; its code is beyond the retained kernel allocation
boundary. This stage supports protected linked reservations only. The fourth
requested function, memcpy, is not emitted in this fixture and cannot be certified.
No independent eighteen-output oracle, whole-LK, Thumb kernel fixture, interrupts,
new Pi run or clean provenance is claimed. LLVM remains at 0044; item 6 and
original #12 remain active. See [contract](AARCH32_QEMU_REWRITE_COVERAGE.md) and
[evidence](results/correctness_rewrite_coverage_20261004.json).

## Latest: item 6 QEMU workload/output consistency stage verified

Legacy runtime banner checks now require all eighteen ordered sink results and
fresh baseline/candidate equality. QEMU errors, timeout, malformed/duplicate
results and explicit failures reject without a success receipt. Fresh directories,
image snapshots and stable image/QEMU/script/revision hashes are required.
Both assertion-mode hot-loop candidates match their baselines: 36 candidate and
36 baseline results overall. Five simulated bad-child cases reject, while the
complete control passes. All 118 WSL Python tests pass; Windows passes with
three Linux process-ownership skips. Shell syntax checks pass for all four gates.

This proves complete workloads/output consistency only. Selected rewritten
execution and independent correctness remain separate open requirements. No
LLVM source change beyond 0044 or new Pi run is claimed. Item 6 and original
#12 stay active. See [contract](AARCH32_QEMU_WORKLOAD_GATES.md) and
[evidence](results/correctness_qemu_gates_20261004.json).

## Latest: item 6 measurement association stage verified

Two preserved admissions now reject: missing PMU output cannot shift the next
run's counters onto an earlier run, and PGO-lab checksum mismatches cannot exit
successfully. Both measurement tools require exact command-framed ordered
cycle/PMU/checksum triples, valid widths and complete kernel/repetition coverage.
Failures retain upload snapshots and child logs and propagate without retry.
All 111 Python tests pass, including thirteen new association/failure tests.

This is parser/measurement and output-consistency evidence, with no new Pi run
or LLVM change beyond 0044. It does not prove rewritten execution or independent
correctness. Item 6 and original #12 remain active; raw-grep gates, manual hooks,
wider oracle coverage, PMU and provenance remain open. See
[contract](AARCH32_MEASUREMENT_GATES.md) and
[evidence](results/correctness_measurement_gates_20261003.json).

## Latest: item 6 Pi far-call milestone verified

Both assertion modes pass all four caller/callee ISA pairs on Pi 4 in normal
and reverse layouts: 80 transformed cases and 40 baseline cases overall.
Six deliberate faults fail at the expected fields, including a retained original
callee that returns correct arithmetic but fails the live callee-PC witness.
All twelve images return through the watchdog to the resident loader. Exact
packed-byte reconstruction, live caller/callee/return PCs, R12 stub targets,
independent result/memory values, NZCV and SP checks are required. All 98 Python
tests pass. No LLVM source change was needed beyond 0044.

This is bounded core-0 HYP execution with IRQ/FIQ masked and MMU/caches off.
It covers explicit supported ARM literal veneers, not automatic v7 thunks,
whole-LK, interrupts or clean compiler provenance. Item 6 and original #12
remain active. See [contract](AARCH32_PI_FAR_SAFETY.md) and
[evidence](results/correctness_pi_far_20261003.json).

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

## Follow-up: execution gate hardening, item 6 active (2026-10-03)

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

## Follow-up: exact profile/artifact identity (2026-10-03)

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

## Follow-up: fixed-load ELF boundary (2026-10-03)

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

## Follow-up: ISA/ABI boundary (2026-10-03)

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

Re-evaluated 2026-10-02 at `5049da5` plus ATFE overlay 0038. **3 of the original
12 items are complete within their stated scope; 9 remain open.** IDs are stable.
See [current review](CORRECTNESS_REVIEW_0038.md),
[fresh priority queue](CORRECTNESS_PRIORITY_TODO.md), [status](CORRECTNESS_STATUS.md), and
[previous fixes](CORRECTNESS_FIXES.md).

Follow-up 2026-10-03: consolidated item 1 has a scoped fix in overlay 0039.
Every decoded exclusive acquisition is analyzed independently of entry metadata;
unmatched/unanalyzed stores reject. The eight F1 bypasses now reject; both builds
pass 171 expanded cases. Overlay 0040 also fixes Thumb startup and passes 40 host
cases plus actual Pi runtime-to-Thumb execution in both builds. Static finalization is a dummy return;
dynamic hooks remain open. Next is ISA/profile/ABI admission. General entry/symbol
scope and active ISR remain open; #12 stays active. See the
[status table](CORRECTNESS_PRIORITY_TODO.md).

The user requested a new review and publication of prioritized work items. The
fresh queue supersedes the earlier order below: skipped interior-entry reservation
bypass, Thumb startup crash, ISA/ABI admission and fixed-load/PIE policy come first.
No implementation fixes began during the review. The user reactivated #12;
all its remaining work is included in the consolidated active queue. Earlier
pause/order notes below are historical and superseded.

Earlier milestone: work stopped at the next verified milestone on 2026-10-02. Local
overlay 0038 verifies #6's decoded cross-function reservation boundary in both
build modes and preserves supported Pi payload bytes; it is not committed or
pushed. Active ISR coverage remains open. Resume only when requested; #12 stays
paused. See CORRECTNESS_RESUME.md.

Earlier checkpoints: the #5 IT/nested/reset matrix and #6 operating
admission boundary now pass Pi and focused host checks. #3's CFG/assertion
boundaries are verified; #4's inlining/return/pass audit has verified boundaries
with wider coverage still open. Broader #5/#6 coverage remains open;
#12 remains paused. See CORRECTNESS_RESUME.md.

Active development is **ATFE only**. Set `BASE=atfe` explicitly: generic scripts
still default to upstream. Raspberry Pi 4 has priority for execution verification;
host tests check encodings/diagnostics and QEMU is supplemental.

## Recommended order

Use [CORRECTNESS_PRIORITY_TODO.md](CORRECTNESS_PRIORITY_TODO.md) for the current
ordered queue and closure checks. The list below records the earlier order.

User revised the order on 2026-10-02: pause #12 and return to it after the next
correctness items. Its remaining validation gaps still limit completion claims.

1. #5 counter carry/registers/flags/IT and #6 admission boundary verified;
   broader ISR/mixed-ISA/snapshot/exclusive-memory coverage remains open.
2. #3 pseudo/CFG boundaries now verified in both build modes;
   #4 conditional-return/PC-write/inlining boundaries verified; broader pass safety
   and wider #3 audit stay open. Next #6 scope: active ISR boundaries.
3. #1 relocation boundaries, then #9 aliases, secondary entries and pointer targets.
4. #7 ISA/ABI admission and #11 inline-table/pass/unsupported-input coverage.
5. **#12 paused by user:** resume counter binding, core ownership, other gates,
   content stamps/clean provenance and the complete Pi validation matrix afterward.

Keep #2/#8/#10 regressions green throughout. P0 means a confirmed semantic defect
or a validation gap that can hide one. P1 means a required boundary or missing
coverage. A boot or passing lit suite alone does not close an item.

## 1. Relocations and literal loads — partial, P0

- [x] A32 literal encoding/JITLink support and BLX-to-BL link-bit fix.
- [ ] Publish a matrix covering input recognition, code-relocation recording,
  addend decoding, MC emission, JITLink application and final data writes. Refresh
  the declaration sets after overlay 0022; declarations are not end-to-end support.
- [x] Implement THM_JUMP19 and Thumb split-fragment state marking (overlay 0022).
- [ ] Test THM_JUMP19 range/alignment/interworking boundaries. Audit narrow Thumb
  branches grouped with THM_JUMP24 in `createRelocation()`.
- [ ] Resolve core-only PC24/PLT32/TARGET2/ALU_PC_G0 and JITLink-only
  LDR_PC_G0/THM_PC12/MOVW-MOVT PREL paths. Justify intentional NONE/V4BX skips.
- [ ] Test PC bias, signed addends/limits, alignment, Thumb state bits, BLX H=0/H=1,
  conditional ARM calls and same/cross-state stubs.
- [ ] Audit pending-relocation writes for preserved opcode/predicate/register bits,
  missing overflow checks, truncation and silently skipped relocations.

**Done:** every accepted matrix row has boundary/negative tests; unsupported rows
fail clearly; ARM/Thumb call and literal cases execute correctly on Pi.

## 2. EHABI unwind boundary — complete via rejection

- [x] Reject nonempty `.ARM.extab`, malformed exidx record lengths and genuine
  unwind descriptors; permit the documented all-CANTUNWIND bare-metal case.
- [x] Maintain the rejection regressions.

Completion is a rejection boundary, not unwind-table rewriting. Full EHABI remains
deferred. Endianness admission is #7; arbitrary unwind consumers are not certified.

## 3. Pseudo counts and CFG invariants - partial, P0

- [x] Fix the reported ARM `B` pseudo emitted by peepholes; generate `Bcc AL`
  instead (overlay 0023). Current pass regressions pass.
- [ ] Reduce any remaining invalid CFGs to tests.
- [ ] Repair bookkeeping at the mutation that causes the mismatch.
  Overlay 0029 removes debug-only repair/ignore and rejects stale ARM counts in
  both modes. Units, focused tests and the 372-case Pi matrix pass with assertions
  on and off. Other invariant recovery paths remain under review.
- [ ] Audit per-function ARM/Thumb builder selection in CFG repair and synthesized
  instructions, including `postProcessBranches()`.
  Overlay 0030 selects the function builder in buildCFG/postProcessBranches and
  rejects residual function fallthrough before repair. Twenty ARM/Thumb negative
  admissions reject without output; eighteen safe return/tail/padding/POP cases
  pass. Main-thread exit after worker join avoids fatal-CFG shutdown crashes.
- [ ] Reject unsupported functions before partial transformations, or prove fallback
  preserves original code/references. Remove silent invariant recovery.
- [x] Run current focused fixtures in a separate assertions-disabled ATFE build:
  52 unit passes/31 expected skips in both modes; 40 focused lit passes with
  assertions on, 39 with one debug-only skip off. The skipped alignment case's
  ARM/Thumb semantic checks pass separately. The Pi matrix and reset-fault
  detection pass in both modes with byte-identical payloads.

**Done:** no swallowed invariant failures; assertions-on/off behavior is consistently
safe; unsupported cases cannot return a successful partially corrupted output.

## 4. Control flow, returns and branch flags — partial, P0

- [x] Recognize unconditional POP/updated-LDM PC returns as terminators.
- [x] Recognize decoded single-register POP-to-PC (ARM LDR_POST_IMM and Thumb
  t2LDR_POST, exact SP/+4 form). Nine decoded host cases cover predicate,
  destination, base and offset distinctions. Both build modes pass 512 baseline
  plus 512 instrumented Pi state cases and all three fault checks.
- [x] Fix ARM Bcc target operands and branch-based tail calls; add restricted
  same-ISA leaf inlining and literal materialization hooks (overlay 0023).
- [x] **Fix CBZ/CBNZ expansion:** replace the flag-clobbering `CMP; Bcc` with an
  inverted CBZ/CBNZ over a wide branch. Test both opcodes with flags consumed on
  both successor paths; Pi dispatcher/argument-parser workloads matched baseline.
- [x] Add a dedicated Pi result check for both flag-consuming successor paths.
  Overlay 0032's fixture executes CBZ and CBNZ expansions in normal/reverse
  layouts with zero/nonzero inputs. The caller consumes the preserved flags
  after either path. Both assertion builds pass; ADD-to-ADDS corruption fails
  at the expected nonzero CBZ case. Wider flags/pass combinations remain open.
- [ ] Model conditional returns with taken exits and fallthrough, or exclude
  transformations requiring that model.
- [x] Exclude unmodeled conditional returns from instrumentation. Overlay 0036
  rejects them before publishing an incomplete profile. Twelve rejection cases
  cover normal/reverse/conservative/forced-inline instrumentation; six ordinary
  relocation cases remain supported. Both host builds pass. Fresh supported
  nested/IT Pi images pass 2,976 cases, all exact counter/reset checks and two
  reset faults. The general exit-edge model and other pass boundaries remain open.
- [ ] Audit non-updating LDM, LDR-to-PC, MOV-to-PC, BX, predicated variants,
  interworking and tail calls; distinguish returns from other computed branches.
  Overlay 0033 rejects unsupported PC writes before transformation, including
  MOV-to-PC, arbitrary LDR-to-PC and noncanonical LDM dispatch. Only updated-SP
  IA pops are load-multiple returns. Thirty-six negative admissions, sixteen
  supported admissions and eighteen decoded cases pass in both modes; exact
  A32 veneers remain admitted. Pi confirms the pre-fix ARM MOV PC,PC corruption;
  both new builds reject that input, and supported firmware stays byte-identical
  to executed 0032 images. Special/privileged transfers and wider variants remain.
- [x] Reject decoded exception returns before the ordinary-return/PC-definition
  exemptions. Overlay 0035 rejects all ARM/Thumb RFE variants, decoded ERET and
  Thumb exception SUBS PC,LR. ARM RFE descriptors omit PC/terminator effects;
  Thumb/ERET descriptors label these ordinary returns. Both modes pass 56
  rejection cases, attribute-decoded ERET rejection, fourteen actual decoder
  cases and the ERET descriptor gate. Supported Pi firmware rebuilds match
  the eight executed 0034 images exactly in both modes. Undecodable instructions
  and other special/trap transfers still need the broader #7/#11 boundary.
- [ ] Check flag-writing self-move/no-op recognition and branch reversal under
  reordering, peepholes and splitting.
  Overlay 0031 preserves CPSR/PC-writing self-moves and removes pure self-moves.
  Nine decoder cases and twelve mixed-mode normal/reverse emission cases pass;
  both Pi builds pass 512 baseline/512 generated state cases and four expected
  faults. Pi uses a negative R0 sentinel (N=1/Z=0); broader flags/pass coverage
  remain open. The dedicated both-path CBZ/CBNZ hardware matrix now passes.
- [x] Enforce the inlining safety boundary even under `--force-inline`.
  Overlay 0032 removes that override and rejects stack/LR/PC-dependent,
  nested-call, literal, multi-entry and CFI callees even when forced. Forty
  ARM/Thumb normal/reverse emission cases and seven decoded return cases pass
  in both modes; safe same-ISA leaves still inline. Both Pi modes pass 55
  baseline/normal/reverse cases each, including LR/stack behavior and both
  paths of an ARM conditional return; result and flag faults are detected.
- [ ] Cover IT call-site and broader inlining/pass combinations with negatives.
  Overlay 0034 covers 92 emitted cases and four IT-call rejections per host build.
  Both Pi builds execute seventy cases each in baseline, forced normal/reverse,
  automatic, size-based and reverse-plus-peepholes configurations: 840 positive
  cases, four detected faults and sixteen watchdog returns. Predicated, indirect
  and mixed-ISA calls retain their calls; safe same-ISA leaves inline. All eight
  payloads match across builds. Wider/profile-driven combinations remain open;
  the peepholes option run does not prove every peephole transformed code.
- [x] Reject unmodeled symbol-boundary fallthrough (entry, ordinary, final-call,
  conditional and fake-thunk-name cases) before transforming it; preserve one
  exact existing A32 absolute veneer pending its removal pass.

**Done:** host CFG/encoding tests and Pi results cover ARM/Thumb, predication,
live flags, return values, LR/SP and fallthrough.

## 5. Instrumentation semantics and counts — partial, P0

- [x] Stair edge collection and optimized/no-reorder checksum comparisons on Pi.
- [x] **Resolve counter width:** overlay 0026 increments the full 8-byte slot with
  low-word ADDS/high-word ADC, saves R0-R3 in a 16-byte frame and restores CPSR_fc.
  Independent ARM/Thumb assembly-byte checks and 38 focused lit tests pass.
  Pi zero/seeded images match all 18 outputs; seeding `0x00000007fffffff0` proves
  carry in both Thumb IT and ARM interwork counters. Dedicated leaf state tests
  below now pass; this does not close #5 or its operating contract under #6.
- [x] Verify quiet single-core leaf insertion state on Pi: 512 ARM/Thumb cases
  preserve R0-R12, LR/SP, the complete CPSR, NZCV/Q/GE and both IRQ-mask states.
  Counter seeds exercise low carry and uint64 wrap; three deliberately broken
  images fail at the expected checks. The eight-byte entry alignment and emitted
  sixteen-byte frame are checked. See PI_COUNTER_STATE.md and recorded evidence.
- [x] Verify quiet nested Thumb calls and recursion counts/returns on Pi: two
  caller levels, eight inputs and recursion through 65 frames. The expanded
  50-function fixture passes 372 cases in each of baseline/normal/reverse/
  conservative modes; all 85/85/73 slots match independent path counts.
- [ ] Extend nested state to mixed ISA and active interrupt behavior; neither
  fixture invokes an ISR or verifies a complete nested register/flags matrix.
- [x] Preserve supported IT header/body groups through insertion and reverse
  layout: all fifteen data masks, narrow/wide terminal branches and loops pass
  300 Pi cases in each of baseline/normal/reverse/conservative modes. Seven
  unsupported/malformed IT admission tests reject before creating output.
- [ ] Extend IT/pass coverage to other predicates and pass combinations; calls,
  returns and branches into IT bodies currently have an explicit rejection boundary.
- [ ] Compare exact counts against known CFGs: zero edges, loops, multiple entries,
  reset and snapshot behavior.
  Leaf/IT/terminal-branch/loop paths and per-case reset pass; multiple entries and
  live snapshots remain. See PI_IT_COUNTS.md.
- [x] Execute the real linked runtime clear routine at quiescent boundaries:
  all low/high words clear before each of 372 cases per mode. A deliberate BX-LR
  replacement fails at the expected first uncleared word. Concurrent resets or
  live snapshots are unverified and require quiescence in the supported contract.
- [ ] Enforce conservative edge counting when required call counts are disabled;
  prevent entry-hook counts from being treated as measured edge profiles.

**Done:** original/instrumented/optimized/no-reorder Pi outputs agree independently,
and measured counts match the expected model, including carry tests.

## 6. Instrumentation operating scope - partial, P0

- [x] Require a privileged, single-core bare-metal contract. ELF metadata cannot prove
  privilege/concurrency: require an explicit operating contract plus harness checks.
- [x] Reject unsupported `--instrument-calls`/indirect-call profiling, including
  the default true setting. Placeholder ARM handlers remain inaccessible to
  accepted profiling invocations.
- [x] Define IRQ/FIQ/reentrancy boundary: updates mask IRQ only; FIQ must stay
  disabled and only one core may participate. Quiet nested calls pass; reset
  and snapshot callers must establish quiescence.
- [x] Reject excluded contract/call/process/shared combinations before output, including
  direct llvm-bolt invocations that bypass wrappers.
- [ ] Audit exclusive-memory sequences and reservations across insertion sites.
- [x] Reject instrumentation of functions containing exclusive instructions
  or CLREX. Overlay 0037 covers all ARM/Thumb LDREX/STREX/LDAEX/STLEX widths.
  Both builds pass 104 rejections, 52 ordinary relocation admissions and 38
  actual decoder cases. Fresh supported Pi payloads match the five executed
  0036 images in both modes.
- [x] Contain reservations beginning at every decoded original-code acquisition.
  Overlay 0039 seeds every exclusive load and rejects stores without an analyzed
  local reservation, removing the entry-metadata dependency. Both builds pass
  171 cases, including all eight review bypasses. General ISA/entry/symbol
  admission remains under #7/#9 and active ISR remains open.
  Historical finding: overlay 0038's scoped gate covered skipped/unselected callers, but the
  fresh F1 review admits unnamed interior entries through both direct addends
  and MOVW/MOVT/BLX pointers: eight verified redirected routes in both builds.
  First-entry traversal and known-multiple-entry rejection are insufficient.
  See [priority item 1](CORRECTNESS_PRIORITY_TODO.md).
  The existing gate rejects live calls,
  exits, unmatched stores, incomplete streams, unmodeled transfers and known
  secondary entries. ARM/Thumb direct/indirect and predicated/IT cases pass in
  both builds: 98 rejections, 35 admissions. Closed local pairs/retry loops and
  calls before acquiring/after clearing remain supported. Supported Pi payloads
  match executed bytes; no new reservation runtime outcome is claimed. General
  ISA/entry/symbol admission remains under #7/#9. See
  [evidence](results/correctness_cross_function_exclusive_20261002.json).
- [ ] Extend active ISR/mixed-ISA reentrancy coverage; compile-time contract
  acknowledgement cannot prove runtime concurrency. MPIDR checks the executing
  core, while the fixture's loader parks secondary cores.

Overlay 0028: eight rejection combinations, 40 focused host tests and nine
hardware-result gate tests pass. Pi baseline/normal/reverse/conservative each
pass 372 IT/nested/reset cases with mode/core/stack checks; bad-reset fails as
expected. See PI_INSTRUMENTATION_SCOPE.md and recorded evidence.

**Done:** accepted modes have execution evidence; excluded modes have diagnostics
and negative tests. General userspace/SMP instrumentation remains deferred.

## 7. ISA, ABI, profile and endianness — open, P0

Fresh review F3/F4/F5: both builds admit ARMv6 input while emitting MOVW/MOVT,
static PIE while emitting absolute pointers without output relocations, and
missing-attribute/BE8-flag inputs without explicit supported-contract exclusion.
See priority items 3/4; these are now concrete admission gaps.

- [ ] Define the initial static little-endian ARMv7-A/Thumb-2 input contract and
  tested AArch32 Pi subset. Distinguish optimization from privileged instrumentation.
- [ ] Enforce ELF class/machine/type/endianness, `.ARM.attributes`, CPU profile and
  features; specify absent/conflicting-attribute handling.
- [ ] Reject or separately validate ARMv6, M-profile, BE8/BE32, ThumbEE/Jazelle,
  FP/SIMD and newer instruction features. The harness soft-float policy does not
  mean the Pi CPU lacks floating-point hardware.
- [ ] Validate synthesized instructions/stubs against admitted features. A fallback
  `armv7` triple is not input validation.

**Done:** excluded inputs fail early; accepted fixtures and generated instructions
obey the documented contract. Broader ISA support remains deferred.

## 8. FK_Data_8 and ELF32 metadata width — complete for tested contract

- [x] Reject unresolved symbolic 64-bit ARM ELF data relocations.
- [x] Write all eight bytes for resolved values, including the high word.
- [x] Retain 64-bit address-map records with target-width relocations/zero extension.

Keep MC/metadata regressions. This does not close counter carry (#5) or other
relocations (#1).

## 9. Entry points, mapping symbols and preserved functions — partial, P0

- [ ] Normalize the Thumb ELF-entry bit before instrumentation startup lookup.
  The fresh pure-Thumb probe aborts at `Entry point function not found` with
  assertions on and segfaults in createAuxiliaryFunctions with assertions off.
  Ordinary optimization passes in both modes. No fix applied. Fresh F2 evidence:
  out/correctness/review-0038-20261002; see priority item 2. Preserve the earlier
  exclusive-instrumentation/probe-yozkp1rs evidence too.

- [x] **Fix odd Thumb `e_entry`:** normalize the ARM function lookup and preserve
  the Thumb state bit in the moved entry. The previously asserting fixture passes.
- [x] Keep a moved `$t` at its even byte address and carry the Thumb state bit
  on moved `STT_FUNC` symbols. Preserve marker size zero.
- [x] Mark split fragments Thumb, use `$a/$t` after constant islands, mark inline
  tables, and preserve ARM call targets in mixed JITLink blocks (0022/0024).
- [ ] Preserve moved/skipped function symbols, aliases, sizes, secondary entries
  and pointer targets. The missing moved `probe` symbol is fixed in the fixture;
  the other cases still need regression coverage.
- [ ] Test code/data transitions, literals, mixed modes, missing mapping symbols,
  function pointers and disassembler interpretation.
- [ ] Harden redirect maps: exact input matching, source/destination bounds, ISA
  detection, short functions, aliases and branches into overwritten entries.

**Done:** metadata/disassembly agree with bytes; Pi tests cover direct, indirect,
original-entry and secondary-entry routes.

## 10. Stub determinism and mixed alignment — complete for tested code output

- [x] Stable block visitation and unique ordering addresses.
- [x] Preserve section/block alignment for mixed ARM/Thumb stubs.
- [x] Repeated-link code comparisons and redirected Pi workload validation.

Keep the mixed-stub gate. Completion covers generated code/stubs, not identical
whole ELF files with different invocation notes or every branch case under #1.

## 11. Rewrite coverage and unsupported constructs - partial, P1

- [ ] Enumerate selected/emitted/redirected/skipped/executed functions with skip
  reasons. The reported 403/411 full-image figure measures emitted symbols;
  prove actual execution after correcting the restoration/redirection gate.
- [x] Implement inline PC-relative TBB/TBH, CFG edges, TBH emission and reverse-layout
  stubs (0024); normal and reversed layout regressions pass.
- [ ] Cover table reach limits, malformed/ambiguous data islands, shared cases,
  instrumentation/splitting interactions, ARM tables and unresolved indirect branches.
- [ ] Prove safe handling or reject GOT/TLS/PLT/PIC/shared-library constructs.
  `isGOT()`/`isTLS()` returning false does not establish safe exclusion.
- [ ] Audit veneers beyond LLD names, PC-relative addresses, constant islands,
  system/exception instructions, data-to-code references and ignored callees.
- [x] Publish a functionality/pass matrix with scoped Pi results.
- [ ] Enforce safe pass boundaries and combinations while #1/#3/#4 remain open;
  a pass doing no work is not tested transformation coverage.

**Done:** the supported subset preserves references and reports actual coverage;
unsupported inputs cannot masquerade as successful optimization. General kernel
rewriting need not be implemented to close an explicitly bounded scope.

## 12. Validation, profile integrity and reproducibility — active, partial, P0

The user reactivated this item on 2026-10-02. Its remaining work is consolidated
into priority queue items 5, 6, 10 and 14; nothing in #12 remains paused.

- [x] Propagate failed child gates and missing/mismatched Pi checksums.
- [x] Re-run all 30 focused ARM tests and failure-path tests after WSL restoration.
- [x] Re-evaluate bbae817: 36/36 focused host tests pass; full-image emission and
  isolated negative probes recorded in CORRECTNESS_REVIEW_BBAE817.md.
- [x] Reject truncated counter arrays, invalid counter addresses/indices and
  truncated metadata; buffer conversion and publish only after it succeeds.
  Ten validation tests pass; real ATFE metadata with 61 counters converts.
- [x] Validate CFG/inferred-forest structure, missing/duplicate counter coverage,
  negative inferred flows and string boundaries. Reject leaf-only metadata without
  a verifiable name. Cold descriptors are validated too; node IDs cannot force huge allocations.
- [ ] Bind named locations and offsets to the exact original function/image when
  publishing fdata; string-table consistency alone does not establish source identity.
  Sampling conversion now checks source ELF functions/ranges; counter locations
  still need source-image/map binding. Ambiguous duplicate local symbols are rejected.
- [ ] Bind dumps/metadata/maps/profiles to exact images and toolchain/patch digests;
  reject stale or mismatched artifacts.
  The sampling path now seals ELF/binary/buffer identity before capture, preserves
  full logs and carries hashes into fdata sidecars. Bound host conversion tests and
  real ATFE ELF/perf2bolt checks pass. After power cycling, Windows reassigned
  the adapter to COM6. Fresh capture passed with 6,772 samples and two complete
  workload repetitions. A candidate built from the explicitly scoped profile
  passed all 18 outputs and sampled rewritten execution (see the 2026-10-02 manifest).
- [x] Correct the full-image path: explicit redirects, strict section restoration,
  artifact hashes, decoded branch checks and required rewritten PC evidence on Pi.
- [ ] Require execution/redirection evidence in every other optimization gate.
  Full-image verification certifies only its explicitly required rewritten bodies.
- [x] Require all 18 named workloads in `passes_check.py`; reject missing/extra
  results, conflicting duplicates, reported workload failures and nonzero child exits.
- [x] Add independent memcpy/far_call/it_cond/interwork results. On Pi, all 18
  baseline/redirected results agree; the four new values match independent calculations.
  PC samples observe rewritten memcpy, Thumb IT and ARM interworking code.
- [ ] Extend independent checks across ARM/Thumb/mixed modes, flags, memory,
  returns, multiple inputs/seeds, faults and timeouts. Far-call has a correct result
  and a static redirect, but no sampled execution PC in this short fixture.
- [ ] Validate section restoration and manual hooks: bounded scratch allocation,
  whole instructions, PC-relative prologues, section-size mismatches and warning-only
  failures. Prefer one documented execution path.
- [ ] Replay ATFE overlays in an isolated clean tree and compare provenance.
  Filename-only patch stamps do not detect changed patch contents. Preserve dirty
  WSL source; do not reset it to make a check pass.
  The new isolated verifier applies all 24 patches and compares live contents.
  The first audit detected four unexported ARM attribute/kept-code files and
  preserved their diff. Overlay 0025 now exports the reviewed changes, hardens
  kept-branch writes/rejection and adds twelve linked-ELF probes. All 25 overlays
  reproduce live source exactly; 37 focused lit tests pass. Source equality is
  verified; content stamps and clean build provenance remain open. See ATFE_OVERLAY_REPLAY.md.
- [x] Export the four unrecorded ATFE source changes with byte/negative regressions
  and achieve isolated source-content equality without resetting the live tree.
- [ ] Replace ATFE filename-only stamps with base/patch/source content identity;
  prove clean build provenance separately from successful source replay.
- [x] Protect `.git/` and `out/` during WSL build/sync (fixed in current GitHub scripts).
- [x] Reject empty/partial PC sample words; failed perf2bolt conversion leaves an
  existing profile intact. Real ATFE perf2bolt smoke test passes.
- [ ] Harden sampled profiles: validate image/buffer identity,
  kept/taken counts, saturation, core/PMU ownership and workload completion. Record
  IRQ-masked blind spots and avoid presenting PC samples as exact edge counts.
  Image/buffer/count/saturation/repetition gates are implemented and host-tested.
  The runtime still arms all cores; IRQ counts are recorded without claiming
  per-PC ownership. Fresh hardware capture/conversion/execution now pass;
  single-core ownership remains open. Unbounded assembly locations are rejected
  unless excluded by an explicit profile scope with recorded counts.
- [ ] Record durable Pi manifests: revisions/options, image/profile hashes,
  selected/emitted/executed functions, expected/observed outputs and complete logs.

**Done:** gates fail on deliberately wrong artifacts/results; clean ATFE replay
reproduces tested source; every completed item has scoped host/hardware evidence.

## Deferred

- Upstream changes/builds, RFC posting and PR submission remain stopped.
- Full EHABI rewriting, general userspace/SMP instrumentation and broader ISA/ELF
  support remain outside the initial boundary; rejection tests are still required.
- Permanent SD-card chainloader reflash remains owner-deferred; temporary fast-loader
  upload already avoids needing a reflash for correctness work.
- Performance tuning, quadratic symbol-scan cleanup and cosmetic refactors follow
  correctness unless they block reliable validation.
