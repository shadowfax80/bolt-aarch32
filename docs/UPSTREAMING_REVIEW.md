# Upstreaming review — submission readiness

**Date:** 2026-09-17. **Scope:** `overlay/llvm/patches/upstream/` (10 patches,
~3,000 lines), reviewed statically as an LLVM/BOLT maintainer would on first
open. This is a different question from "is the backend complete" — that is
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md). This asks: *what happens when
the PR is opened?* Every open item below is also tracked there (U7–U9, L5–L6);
this doc keeps the reasoning and the positives.

---

## The finding that reframes the rest

**The ARM backend has no commits.** `scripts/export-llvm-arm-patches.sh`
line 22 is the entire mechanism:

```sh
git -C "$LLVM" diff HEAD -- "$@" > "$DEST/$name"
```

Each "patch" is a slice of one uncommitted working tree on the pod volume,
partitioned by file list. Consequences a reviewer hits immediately:

- No commit messages — none of the ten patches has a rationale, because there
  is nothing to attach one to. All ten begin with `diff --git`.
- The split is by **file**, not by **logical change**. Patch 0003 means "these
  nine core files," not "the ELF32 reader." A file needed by two rungs lands
  wherever its name is listed.
- `git format-patch` is impossible; there is nothing to format.
- If the volume is lost, the backend exists only as these snapshots.

The P1–P10 rung structure the docs describe does not exist in source control,
only in prose. Reconstructing a real commit series — carving ~3,000 lines into
logically coherent commits with messages — is the first task, ahead of any
code gap, and it is not mechanical.

---

## What is upstream-ready — do not rework these

- **Lit tests have the right shape.** `llvm-mc -filetype=obj` →
  `ld.lld --emit-relocs -T Inputs/arm32.ld` → `llvm-bolt` → `FileCheck`, with
  real check prefixes. This is exactly the pattern in `bolt/test/AArch64/`.
  7 `llvm-mc` inputs, 10 `ld.lld` links, 1 `yaml2obj`. Four tests use `%clang`,
  which upstream buildbots without clang will skip — acceptable, but worth
  knowing.
- **Target registration is textbook.** `bolt/lib/Target/ARM/CMakeLists.txt`
  is the RISCV/AArch64 template verbatim: `LLVM_LINK_COMPONENTS` with
  `ARMDesc`, the `BOLT_BUILT_STANDALONE` tablegen block, `add_llvm_library`
  with `NO_EXPORT` / `DISABLE_LLVM_LINK_LLVM_DYLIB`, `DEPENDS
  ARMCommonTableGen`. `BOLT_TARGETS_TO_BUILD_all` gains `ARM` in the right
  place.
- **No copy-paste from AArch64.** Four "AArch64" mentions in 1,490 lines of
  `ARMMCPlusBuilder.cpp`, all comments explaining a deliberate divergence
  ("mirrors AArch64MCPlusBuilder's non-LSE helper", "AArch64 solves this by
  …"). That is the good kind of reference.
- **The instrumentation hook surface is complete.** All ten target hooks are
  implemented: `createInstrIncMemory`, `createInstrCounterIncrFunc`,
  `createInstrumentedIndirectCall`, the ind-call handler entry/exit basic
  blocks, the ind-tail-call exit block, and the four table/counter getters.
  The previous review implied this was thinner than it is.

---

## The core-API finding a reviewer will block on

`BinaryContext::getMIBFor(bool IsThumb)` is the change that touches every
target and therefore needs the Discourse RFC — and its signature is wrong.

Eleven core call sites. **Ten re-derive the predicate inline:**

```cpp
MCPlusBuilder *MIB = BC.getMIBFor(BC.isARM() && Function.isARMThumb());
```

**One omits the guard** (`LongJmp.cpp`, patch 0009 line 155):

```cpp
MCPlusBuilder *MIB = BC.getMIBFor(BF.isARMThumb());
```

It works on non-ARM targets only because `isARMThumb()` happens to be false
there. The API shape makes the inconsistency possible: every caller in core
must know the words "ARM" and "Thumb." The fix is

```cpp
MCPlusBuilder *getMIBFor(const BinaryFunction &BF) const;
```

with the target check inside. Core then never spells either word, the
`LongJmp.cpp` variant cannot exist, and the RFC has something clean to
propose. As written it would be sent back.

Related, and the same review comment in a different form: **41 `isARM()`
conditionals across 13 core files, 33 of them standalone forks** rather than
`isARM() || isAArch64()` shared paths. `RewriteInstance.cpp` carries 9,
`BinaryFunction.cpp` 7. Some are legitimate ELF32-vs-ELF64 branches. Many are
target behavior that belongs behind an `MCPlusBuilder` virtual. This is what
makes the 22-hunk `RewriteInstance.cpp` diff 22 hunks.

Core blast radius overall: ~95 hunks across 19 core files.

---

## A dead flag

`--no-lse-atomics` appears in **zero patches** — only in
`scripts/instrument-lk-bolt.sh:81` and `scripts/optimize-lk-bolt.sh:44`. It is
the AArch64 `cl::opt`; BOLT accepts it globally and the ARM target never reads
it. The ARM counter path uses `ldrex`/`strex` unconditionally.

Two problems. To a reviewer it looks like a copy-paste error. And it means
there is **no** ARM-side atomics option at all — so the question of opting into
`stadd` on ARMv8.2-A hardware (Cortex-A55) has nothing to opt into.

---

## One that static review cannot settle

BOLT reports `Number of indirect call site descriptors: 0` when instrumenting
`bolt_bench_indirect_call`, which contains a real function-pointer call.

This is **not** a missing hook (see above) and **not** a classification gap:
`isIndirectCall` accepts `ARM::BLX`, `ARM::BLX_pred`, and `ARM::tBLXr` — the
register forms in both ISA modes. The zero is unexplained by the code. It
needs a runtime repro: `llvm-bolt --print-cfg` on that function in the
instrumented build. Recorded as *unexplained*, not as a bug.

---

## Ranked

1. **Reconstruct a real commit series.** The backend has to exist in git before
   it can exist in a PR.
2. **Fix `getMIBFor`'s signature, then post the RFC** the plan required before
   P4 — seven rungs ago.
3. **Push the 33 standalone `isARM()` forks toward virtual dispatch.** This is
   what shrinks the core diff.
4. **Remove `--no-lse-atomics` from the ARM scripts**; decide whether ARM gets
   its own atomics option.
5. **Everything in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)**, in its
   existing order — relocation matrix, `.ARM.exidx`, TBB/TBH, P9/P10 lit
   coverage, the two tests missing from the upstream set.

Nothing in this pass contradicts that doc's earlier findings.
