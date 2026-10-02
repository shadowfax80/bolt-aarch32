# ATFE correctness TODO

Re-evaluated 2026-10-01 at GitHub `bbae817`, with ATFE overlays through 0024. **3 of the original
12 items are complete within their stated scope; 9 remain open.** IDs are stable.
See [review evidence](CORRECTNESS_REVIEW_BBAE817.md), [status](CORRECTNESS_STATUS.md), and
[previous fixes](CORRECTNESS_FIXES.md).

Work resumed by user on 2026-10-02. The #5 IT/nested/reset matrix and #6 operating
admission boundary now pass Pi and focused host checks. Next is #3's CFG/assertion
audit in the order below; broader #5/#6 coverage remains open. WSL is running;
#12 remains paused. See CORRECTNESS_RESUME.md.

Active development is **ATFE only**. Set `BASE=atfe` explicitly: generic scripts
still default to upstream. Raspberry Pi 4 has priority for execution verification;
host tests check encodings/diagnostics and QEMU is supplemental.

## Recommended order

User revised the order on 2026-10-02: pause #12 and return to it after the next
correctness items. Its remaining validation gaps still limit completion claims.

1. #5 counter carry/registers/flags/IT and #6 admission boundary verified;
   broader ISR/mixed-ISA/snapshot/exclusive-memory coverage remains open.
2. **#3 next:** assertions-on/off CFG invariants and #4 conditional returns/PC writes/pass safety.
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
  `getNumPseudos()` currently repairs/ignores ARM only inside `#ifndef NDEBUG`.
- [ ] Audit per-function ARM/Thumb builder selection in CFG repair and synthesized
  instructions, including `postProcessBranches()`.
- [ ] Reject unsupported functions before partial transformations, or prove fallback
  preserves original code/references. Remove silent invariant recovery.
- [ ] Run the same fixtures in a separate assertions-disabled ATFE build.

**Done:** no swallowed invariant failures; assertions-on/off behavior is consistently
safe; unsupported cases cannot return a successful partially corrupted output.

## 4. Control flow, returns and branch flags — partial, P0

- [x] Recognize unconditional POP/updated-LDM PC returns as terminators.
- [x] Fix ARM Bcc target operands and branch-based tail calls; add restricted
  same-ISA leaf inlining and literal materialization hooks (overlay 0023).
- [x] **Fix CBZ/CBNZ expansion:** replace the flag-clobbering `CMP; Bcc` with an
  inverted CBZ/CBNZ over a wide branch. Test both opcodes with flags consumed on
  both successor paths; Pi dispatcher/argument-parser workloads matched baseline.
- [ ] Add a dedicated Pi result check for both flag-consuming successor paths;
  the current Pi workload comparison verifies real rewritten dispatch code but
  does not force both branches of the synthetic fixture.
- [ ] Model conditional returns with taken exits and fallthrough, or exclude
  transformations requiring that model.
- [ ] Audit non-updating LDM, LDR-to-PC, MOV-to-PC, BX, predicated variants,
  interworking and tail calls; distinguish returns from other computed branches.
- [ ] Check flag-writing self-move/no-op recognition and branch reversal under
  reordering, peepholes and splitting.
- [ ] Cover inlining safety overrides (`--force-inline` bypasses the ARM safety
  filter), IT call sites and pass combinations with negative fixtures.

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
- [ ] Extend active ISR/mixed-ISA reentrancy coverage; compile-time contract
  acknowledgement cannot prove runtime concurrency. MPIDR checks the executing
  core, while the fixture's loader parks secondary cores.

Overlay 0028: eight rejection combinations, 40 focused host tests and nine
hardware-result gate tests pass. Pi baseline/normal/reverse/conservative each
pass 372 IT/nested/reset cases with mode/core/stack checks; bad-reset fails as
expected. See PI_INSTRUMENTATION_SCOPE.md and recorded evidence.

**Done:** accepted modes have execution evidence; excluded modes have diagnostics
and negative tests. General userspace/SMP instrumentation remains deferred.

## 7. ISA, ABI, profile and endianness — open, P1

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

## 12. Validation, profile integrity and reproducibility — partial, P0

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
