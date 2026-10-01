# BOLT AArch32 (ATFE) functionality review — 2026-10-01

Scope: what BOLT can actually *do* on AArch32 with the ATFE toolchain, as a complement to
the correctness audit in [CORRECTNESS_TODO.md](CORRECTNESS_TODO.md). ATFE only; upstream work
is deferred.

**Method.** `llvm-bolt` as built in WSL on 2026-10-01 (ATFE bcc088849, overlays 0001–0021,
repo at ff7d544). Every major pass, instrumentation mode and profile input was run against
the real LK image `pgo_thinlto.elf` (stair, 432 sites) with its Pi edge profile
(`pgo_thinlto.fdata`). "Works" means `llvm-bolt` completed cleanly; outputs were **not
booted** unless marked **Pi-proven**.

## What works

| Area | Result |
|---|---|
| Rewrite target | Static bare-metal ELF, selected functions, ARM and Thumb. **Pi-proven** (one and six functions, one ARM-mode). |
| Block reordering | `ext-tsp`, `cache`, `normal`, `branch-predictor` all run. **Pi-proven**: `ext-tsp`. |
| Function reordering | `hfsort`, `hfsort+`, `cdsort`, `pettis-hansen` and `-hot-text` run. **Pi-proven**: contiguous placement, −44% on six functions. |
| Other passes that run | `-icf=all` (folded 5 of 414), `-simplify-conditional-tail-calls`, `-tail-duplication` (modified 0 functions), `-align-blocks`, `-eliminate-unreachable`, `-plt` (no-op on a static image), `-split-eh` (no EH, no-op), `-lite=0`, `-enable-bat`, `-update-debug-sections` (DWARF correctness untested). |
| Instrumentation | Edge counting with `--instrument-calls=false --conservative-instrumentation` is **Pi-proven**. `--instrument-calls=true`, `--instrument-hot-only` and whole-image (`--funcs=.*`) builds complete. Bare-metal runtime only. |
| Profile input | Instrumentation counters from the Pi: **Pi-proven**. `perf2bolt -pa` (pre-aggregated text) accepts branch records (`B`), and PC samples (`S`) with `-nl`. `merge-fdata` is available. |
| Unwind tables | Refused with a clear diagnostic unless all entries are CANTUNWIND (overlay 0015). |
| Stubs | Deterministic output (overlay 0019). |

## Gaps, worst first

1. **Hot/cold splitting fails.** `-split-functions` (and `-split-all-cold`):
   `JITLink failed: Unsupported aarch32 relocation 51: R_ARM_THM_JUMP19`. The most valuable
   missing optimization for firmware with cold error paths. Overlaps CORRECTNESS #1.
2. **Switch statements get no layout benefit.** Thumb TBB/TBH dispatch is classified UNKNOWN;
   ICF reports "0 functions had jump tables". Switch-heavy code is skipped, not optimized.
3. **Missing ARM target hooks crash two passes** (abort, not a diagnostic). Not yet in the
   correctness list.
   - `-inline-small-functions` / `-inline-all`: `UNREACHABLE` at `MCPlusBuilder.h:832`
     (`isPush`; `getPopSize` likewise unimplemented).
   - `-simplify-rodata-loads`: `UNREACHABLE` at `MCPlusBuilder.h:1971` (`materializeConstant`).
   - The ARM builder overrides 60 hooks vs AArch64's 124; other notable absences:
     `isPop`, `getCalleeSavedRegs`, `mayLoad`/`mayStore`, `isRegToRegMove`,
     `createLoadImmediate`, `matchLinkerVeneer`. Each should be implemented or the pass
     using it refused with an error.
4. **Peepholes fail.** `-peepholes=all`: "calculated pseudos 1, set pseudos 0" in
   `arch_disable_cache`. CORRECTNESS #3.
5. **Code cannot stay in the original `.text`.** `-use-old-text`: "cannot ignore non-empty
   function arm_generic_timer_init in current mode". For fixed bare-metal memory maps this
   would replace the `fix-kernel-elf-sections.py` / `redirect-bolt-entries.py` workarounds.
6. **Indirect calls are not profiled.** "Number of indirect call site descriptors: 0"; the ARM
   hook returns the original call (CORRECTNESS #6). Indirect-call promotion therefore has no
   input, and is also code-gated to X86/AArch64.
7. **X86-only by upstream design** (not ARM bugs; keep excluded): `-frame-opt`
   (shrink-wrapping), `-reg-reassign`, `-three-way-branch`, `-cmov-conversion`,
   `-jt-footprint-reduction`, `-hugify` (x86 runtime object).
8. **Narrow supported scope.** Static images only (no GOT/TLS/PLT/PIC; CORRECTNESS #11); no
   Linux user-space runtime; EH tables refused rather than rewritten; full-image coverage
   needs re-measuring (the old 7% figure is historical, CORRECTNESS #11).
9. **32-bit counter increments, no carry** into the 64-bit slot (CORRECTNESS #5).

## Suggested order (ATFE only)

1. `R_ARM_THM_JUMP19` support end to end (BOLT core + JITLink) → enables `-split-functions`.
2. Missing hooks: `isPush`/`isPop`/`getPopSize`, `materializeConstant`; then the peephole
   pseudo-count fix. Until done, refuse those passes with a diagnostic instead of aborting.
3. TBB/TBH and ARM-mode jump tables.
4. Sampling profile path from lk-perf PC samples into `perf2bolt -pa -nl` (format accepted):
   no instrumented image needed, suits the Secure SVC target.
5. In-place layout for fixed memory maps (`-use-old-text`), retiring the post-processing scripts.
6. Indirect-call profiling, then indirect-call promotion for ARM.

CORRECTNESS #1, #3, #5, #9 and #12 should land alongside; splitting and peepholes depend on them.

## Reproduce

Pass matrix: run `llvm-bolt pgo_thinlto.elf -data=pgo_thinlto.fdata -o out.elf <pass flags>`
in `~/bolt-aarch32/build-atfe/variants` and check the log for `BOLT-ERROR`/`UNREACHABLE`.
Instrumentation: add `-instrument --instrumentation-sleep-time=1
--runtime-instrumentation-lib=build-atfe/bolt-rt-baremetal-arm/libbolt_rt_baremetal.a`.
