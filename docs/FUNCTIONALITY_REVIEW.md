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

## Out of scope for now — deferred TODO (owner, 2026-10-01: "can be taken up later")

Not part of the six items above; recorded so they are not lost.

- **X86-only passes:** `-frame-opt` (shrink-wrapping), `-reg-reassign`, `-three-way-branch`,
  `-cmov-conversion`, `-jt-footprint-reduction`. Code-gated to X86 upstream; an ARM version
  of shrink-wrapping (`-frame-opt`) is the only one with a clear AArch32 payoff.
- **`-hugify`:** links an x86 runtime object; no AArch32 runtime exists.
- **PIC / dynamic images:** GOT, TLS, PLT, shared libraries (`isGOT()`/`isTLS()` return false).
- **Linux user-space instrumentation runtime** for AArch32 (only the bare-metal one exists).
- **Full EHABI rewriting** of `.ARM.exidx`/`.ARM.extab` (today: refused with a diagnostic).
- **Upstream work:** RFC, upstream patch series, U1–U9 (see [TODO.md](TODO.md)).

## Progress on the six items

### 1. Hot/cold splitting — DONE (overlay 0022, 2026-10-01)

- JITLink: new `Thumb_Jump19` edge kind for `R_ARM_THM_JUMP19` (B<c>.W, T3), read/apply,
  ±1 MiB range check, condition field preserved, interworking stub when the target is ARM.
- BOLT JITLink pass: split-fragment symbols (`foo.cold.0`) are now marked Thumb. Without
  this, every hot→cold conditional branch went through an ARM-state stub and the Pi
  hung/panicked the first time cold code ran (found on the Pi with the shifted input).
- BOLT core: Thumb `BL`/`B.W` relocation values were decoded with the halfwords swapped and no
  PC bias (0 of 1,635 matched their symbol in the LK image; now 1,588, the rest are lld
  veneers); ARM-mode branches lacked the +8 bias and BLX's H bit; `PREL31` used 32 bits.
  ARM now follows AArch64's absolute-target convention in `analyzeRelocation`.
  `THM_JUMP19` is recognized on input.
- Tests: JITLink `ELF_relocations_thumb_jump19.s`, BOLT `arm-thumb-split.test`; all 33 ARM +
  JITLink AArch32 lit tests and 15 JITLink unit tests pass.
- Pi (stair, 432 sites, `-split-functions -split-all-cold`, 2 rounds × 2 runs, checksums
  identical in all runs): training input bolt −10.38%, bolt+split −10.38% vs baseline;
  shifted input (cold code executes) bolt +44.5%, bolt+split +42.9%.
  `docs/results/split_functions_stair_v*.csv`. Enable with `BOLT_SPLIT=1`.
- Not supported: `-split-strategy=cdsplit` (upstream LongJmp limitation, >2 fragments).

### 2. Missing hooks, crashing passes, peepholes — DONE (overlay 0023, 2026-10-01)

Hooks: `isPush`/`isPop`/`getPushSize`/`getPopSize` (SP register lists), `materializeConstant`
(word literal load → MOVW/MOVT, unconditional only, v6T2+). Bugs found and fixed on the way:

- **ARM-mode `Bcc` target was read from operand 2** (the predicate register) instead of 0, so
  ARM-mode conditional branches were never symbolized and kept their input displacement —
  correct only while their blocks did not move. Now symbolized; the emitter's workaround for it
  no longer drops the condition of an ARM→Thumb conditional branch (now a clear error).
- **ARM-mode unconditional branch was built as `ARM::B`**, a codegen pseudo MC cannot encode;
  BOLT counted it as a pseudo, the debug check "recovered" by ignoring the function mid-pass,
  and `-peepholes` crashed. Now `Bcc` AL.
- **Tail calls were built as `BL`** (a call, overwrites LR) instead of a branch; used by the
  double-jump peephole and conditional-tail-call expansion. Now `B`/`B.W` annotated as tail
  call; the CTC expansion also picks the function's ARM/Thumb builder.
- **Inliner on AArch32:** call-site filter could never match a `BL` (predicate operands), and
  `BX LR` was retargeted as a branch. Now inlines only same-ISA, unconditional calls outside IT
  blocks into callees that are leaves touching neither SP, LR (beyond a final `bx lr`) nor PC,
  without constant islands; everything else stays a call.

Now run on the full LK image: `-peepholes=all`, `-simplify-conditional-tail-calls`,
`-inline-small-functions`, `-inline-all`, `-simplify-rodata-loads` (plus all earlier passes).
Tests: `arm-passes.test` (ARM Bcc after reordering, tail call is B, inlining rules, MOVW/MOVT);
34/34 ARM + JITLink lit pass. Pi: `scripts/pi4/passes_stage.sh` — 18 workload results of
`bolt_bench all` identical to baseline for 7 images (plain, inline, rodata, split, peepholes,
SCTC, all combined; `docs/results/passes_pi_check.txt`); multi-function rerun −45.4%, checksums
identical. Inlining here: 2 call sites, 40,000 dynamic calls; rodata: 1 hot load.
`bolt_bench all` now prints each workload's result (`<name> sink=`).

### 3. Switch tables (TBB/TBH) — DONE (overlay 0024, 2026-10-01)

- Thumb `TBB`/`TBH [pc, Rm]` with an inline table: the table (the `$d` island after the
  branch) is decoded into CFG edges; the branch is rewritten as `TBH` with a halfword table
  emitted right after it (`.short (case - table)/2`, as LLVM's own codegen emits it). Case
  blocks laid out before the table are reached through `B.W` stubs after it (TBH is forward
  only). Table branch and cases are kept in one fragment when splitting; instrumentation
  counts the case edges like jump-table edges. Alignment padding after a TBB table is dropped;
  any other undecodable entry leaves the function as before (unknown control flow).
- LK image: all 23 TBB/TBH sites rewritten; a full-image rewrite with no allowlist now covers
  401 of 409 functions (the rest are startup/MMU assembly and three functions with
  undisassemblable instructions). ARM-mode table dispatch (`ldr pc, [pc, rN, lsl #2]`) does
  not occur in this image and is not handled.
- Bugs found and fixed on the way:
  - **Mapping symbols:** after a constant island BOLT wrote AArch64's `$x`; now `$t`/`$a`.
    Inline tables get `$d`/`$t`. (Disassemblers showed the following code as data.)
  - **ARM/Thumb marking in BOLT's JITLink pass:** every symbol in a block that contains a
    Thumb function was marked Thumb, so an ARM→ARM `BL` into a rewritten ARM function sharing
    that block became `BLX` (Pi: undefined-instruction abort). Now only labels inside Thumb
    function ranges, never named ARM functions.
  - Host scripts: static functions are `<name>/1` in BOLT (allowlists silently missed them);
    the redirect script now looks symbols up without that suffix and refuses to guess ARM vs
    Thumb (it wrote a Thumb `B.W` into an ARM function); tiny (<8 byte) functions are not
    redirected; serial noise no longer crashes `pi4_run.py`.
- Infrastructure: `bolt_bench` `wdog <s>` + `pi4_run.py --wdog`/`PI4_WDOG` — a hung test image
  resets the Pi to the chainloader by itself (verified), no manual power cycle.
- Tests: `arm-inline-table.test` (normal and fully reversed layout, stubs), updated
  `arm32-thumb-switch.test`, interwork call-kind check in `arm-passes.test`; 36/36 lit pass.
  Pi: `bolt_bench all`, 18 results identical to baseline for 7 images (plain, inline, rodata,
  split, peepholes, SCTC, all combined) with 29 functions incl. the switch dispatcher and all
  static helpers; inlining now 4 call sites / 240,000 calls.
