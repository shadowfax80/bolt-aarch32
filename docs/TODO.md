# Open TODO items (deferred by the owner)

Everything else that was on the working list is done (see
[RPI4_HARDWARE_VERIFICATION.md](RPI4_HARDWARE_VERIFICATION.md)). These two are **definite
TODOs that were deliberately deferred** ("will take it up later"); do not start them unprompted.

## 1. Reflash the chainloader to a faster upload baud

Image uploads (the serial transfer before LK boots) run at the SD-card chainloader's fixed
115200 baud (~11 KiB/s). The 3M-baud UART patch only speeds up LK's own shell after boot.
Fix: reflash the chainloader itself to transfer at 3M (or 6M) baud. Details and the
measurements behind it: "TODO: reflash chainloader" in
[RPI4_HARDWARE_VERIFICATION.md](RPI4_HARDWARE_VERIFICATION.md). Owner decision 2026-09-29: at
the next opportunity, not yet. Needs the owner (SD card, physical access); it would cut every Pi
run by 40 s or more.

## 2. Upstream blockers for the BOLT AArch32 backend

Goal: reviewable PRs in llvm-project main. The tracker with evidence and repros is
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md); this is the agreed order (2026-09-30).

**Gate (owner)**

1. **Post the RFC on LLVM Discourse** ([RFC_BOLT_AARCH32.md](RFC_BOLT_AARCH32.md), drafted, not
   posted; seven rungs overdue and a hard gate). It must propose `getMIBFor(const BinaryFunction &)`,
   not the old `getMIBFor(bool)`. Only the owner can post it.

**Prerequisite**

2. **Rebuild the upstream base in WSL.** The upstream tree lived on the deleted RunPod volume; only
   the 7-commit series survives (`overlay/llvm/patches/upstream/`). Clone `llvm/llvm-project` at the
   pin, replay the series with `git am` (branch `bolt-arm-backend`), build `llvm-bolt` and the lit
   tools (~1 h), and let `scripts/wsl-setup.sh` take `BASE=upstream` (skip the ATFE-only runtimes).

**Blockers, tracker order**

3. **U2 relocation matrix.** BOLT-core handles 20 `R_ARM_*` types, JITLink 11, nearly disjoint.
   One documented, cross-checked table, a test per supported type, a clean diagnostic for
   unsupported ones (`THM_JUMP19` is the symptom that blocks `-split-functions`).
4. **U3 `.ARM.exidx` / `.ARM.extab`.** Rewrite and re-sort the index, or (proposed first-backend
   position) detect the section and refuse with a clear diagnostic.
5. **U4 lit tests for P9 (instrumentation) and P10 (optimization)**, plus negative/diagnostic tests
   (malformed ELF, unsupported architecture); confirm `check-bolt` is green.
6. **L7** ARM swallowing core invariant violations: `getNumPseudos()` (exists only under
   `#ifndef NDEBUG`) and `postProcessBranches()`. Fix the root causes, drop both special cases.
7. **Remaining U9 sites**: 31 standalone `isARM()` forks in core, 8 design calls left.
8. **U5 TBB/TBH jump tables** unrecoverable (documented boundary; partly a documentation item).
9. **U1 full-image rewrite** moves ~7% of functions and the output differs on every run (D4,
   dominated by instructions BOLT cannot disassemble). Hardest; last.

**Smaller items reviewers would raise**

10. **L8** range check on 8-byte fixups; **L11** quadratic symbol scans in the ARM JITLink pass;
    **D3** `isTerminator()` for POP/LDM; **L12** convert the ATFE patches (incl. 0011-0013) into a
    commit series; lit tests for `--emit-function-map` (0013); the `--print-finalized` assertion
    ("Cannot print this instruction"); a test that ARM edge instrumentation needs
    `--conservative-instrumentation` when call counters are off.

Work on items 2-10 changes the backend, so each fix lands as a commit on the series and is
exported with `scripts/export-llvm-arm-patches.sh`; the Pi measurements are unaffected.
