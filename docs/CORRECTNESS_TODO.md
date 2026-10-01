# ATFE correctness TODO

Reviewed 2026-10-01 against the restored WSL workspace. **3 of the original
12 items are complete within their stated scope; 9 remain open.** IDs are stable.
See [review evidence](CORRECTNESS_REVIEW.md), [status](CORRECTNESS_STATUS.md), and
[previous fixes](CORRECTNESS_FIXES.md).

Active development is **ATFE only**. Set `BASE=atfe` explicitly: generic scripts
still default to upstream. Raspberry Pi 4 has priority for execution verification;
host tests check encodings/diagnostics and QEMU is supplemental.

## Recommended order

1. #9 Thumb ELF entry translation, then the remaining #4 conditional-return/PC-load cases.
2. #12 profile validation and proof that selected rewritten code executes.
3. #1 relocation contract, then #3 pseudo/CFG invariants.
4. #5 instrumentation semantics and #6 enforced operating scope.
5. #7 ISA/ABI admission and #11 rewrite coverage boundaries.
6. Finish remaining #4/#9 cases and the Pi matrix under #12.

Keep #2/#8/#10 regressions green throughout. P0 means a confirmed semantic defect
or a validation gap that can hide one. P1 means a required boundary or missing
coverage. A boot or passing lit suite alone does not close an item.

## 1. Relocations and literal loads — partial, P0

- [x] A32 literal encoding/JITLink support and BLX-to-BL link-bit fix.
- [ ] Publish a matrix covering input recognition, code-relocation recording,
  addend decoding, MC emission, JITLink application and final data writes. Core and
  JITLink each declare 18 types, with 13 shared; this is not end-to-end support.
- [ ] Implement or reject `THM_JUMP19` correctly. Audit narrow Thumb branches
  currently grouped with `THM_JUMP24` in `createRelocation()`.
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

## 3. Pseudo counts and CFG invariants — open, P0

- [ ] Reduce `-peepholes` pseudo-count failures and invalid CFGs to tests.
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

**Done:** host CFG/encoding tests and Pi results cover ARM/Thumb, predication,
live flags, return values, LR/SP and fallthrough.

## 5. Instrumentation semantics and counts — partial, P0

- [x] Stair edge collection and optimized/no-reorder checksum comparisons on Pi.
- [ ] **Resolve counter width:** ARM increments offset 0 of an 8-byte slot; runtime
  and converter use 64-bit counters. Implement carry or enforce a bounded alternative.
  Seed near `0xffffffff` to test overflow without billions of iterations.
- [ ] Verify GPRs, LR/SP, NZCV, interrupt state and required stack alignment across
  insertion, including pre-disabled IRQ state and nested execution.
- [ ] Preserve IT header/body groups through insertion, edge splitting, reversal
  and reordering; test masks and terminal conditional branches.
- [ ] Compare exact counts against known CFGs: zero edges, loops, multiple entries,
  reset and snapshot behavior.
- [ ] Enforce conservative edge counting when required call counts are disabled;
  prevent entry-hook counts from being treated as measured edge profiles.

**Done:** original/instrumented/optimized/no-reorder Pi outputs agree independently,
and measured counts match the expected model, including carry tests.

## 6. Instrumentation operating scope — open, P0

- [ ] Enforce a privileged, single-core bare-metal mode. ELF metadata cannot prove
  privilege/concurrency: require an explicit operating contract plus harness checks.
- [ ] Reject unsupported `--instrument-calls`/indirect-call profiling. The current
  ARM hook returns the original call; runtime handlers immediately return.
- [ ] Define IRQ/FIQ/reentrancy behavior. The current sequence masks IRQ only and
  is not a multicore atomic increment.
- [ ] Reject excluded combinations before producing a usable output, including
  direct llvm-bolt invocations that bypass wrappers.

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

## 9. Entry points, mapping symbols and preserved functions — open, P0

- [ ] **Fix odd Thumb `e_entry`:** normalize lookup addresses and preserve execution
  state in the output entry. A valid Thumb-entry fixture currently asserts.
- [ ] Emit `$a/$t/$d` at byte addresses; appropriate Thumb function symbols carry
  the state bit. Review reproduced `$t=0x22009` for code beginning at `0x22008`.
- [ ] Preserve moved/skipped function symbols, aliases, sizes, secondary entries
  and pointer targets. Review reproduced a missing moved `probe` symbol.
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

## 11. Rewrite coverage and unsupported constructs — open, P1

- [ ] Enumerate selected/emitted/redirected/skipped/executed functions with skip
  reasons. Re-measure full-image coverage; the old 7% figure is historical.
- [ ] Implement or reject TBB/TBH and unresolved indirect branches. Current default
  workload lists include the known-unsupported switch case.
- [ ] Prove safe handling or reject GOT/TLS/PLT/PIC/shared-library constructs.
  `isGOT()`/`isTLS()` returning false does not establish safe exclusion.
- [ ] Audit veneers beyond LLD names, PC-relative addresses, constant islands,
  system/exception instructions, data-to-code references and ignored callees.
- [ ] Publish a supported pass matrix. Gate unsafe peepholes/splitting until
  #1/#3/#4 close; a pass doing no work is not tested transformation coverage.

**Done:** the supported subset preserves references and reports actual coverage;
unsupported inputs cannot masquerade as successful optimization. General kernel
rewriting need not be implemented to close an explicitly bounded scope.

## 12. Validation, profile integrity and reproducibility — partial, P0

- [x] Propagate failed child gates and missing/mismatched Pi checksums.
- [x] Re-run all 30 focused ARM tests and failure-path tests after WSL restoration.
- [ ] **Reject truncated dumps:** two declared counters with one present currently
  become `[7, 0]`. Validate byte ranges, counts, indices, metadata lengths and graph
  consistency before writing fdata; never publish partial output.
- [ ] Bind dumps/metadata/maps/profiles to exact images and toolchain/patch digests;
  reject stale or mismatched artifacts.
- [ ] Require execution/redirection evidence in every optimization gate. The
  generic workload gate restores original sections without calling the redirect script.
- [ ] Add independent memcpy/interwork output checks; those workloads do not update
  the shared sink used in earlier comparisons. Cover ARM/Thumb/mixed modes, flags,
  memory, returns, multiple inputs/seeds, faults and timeouts.
- [ ] Validate section restoration and manual hooks: bounded scratch allocation,
  whole instructions, PC-relative prologues, section-size mismatches and warning-only
  failures. Prefer one documented execution path.
- [ ] Replay ATFE overlays in an isolated clean tree and compare provenance.
  Filename-only patch stamps do not detect changed patch contents. Preserve dirty
  WSL source; do not reset it to make a check pass.
- [ ] Protect `.git` and evidence during sync: `wsl-setup.sh sync` currently uses
  `rsync --delete` without excluding `.git`/`out`.
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
