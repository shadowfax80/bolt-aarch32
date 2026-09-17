# Known limitations and improvement items

This doc exists so gaps stay visible instead of getting lost once the verify
scripts go green. Where something is fixed, that's stated; where it isn't, the
repro or the evidence is given rather than a vague caveat.

**Verification status is marked per item**, because it matters for how much to
trust each entry:

- **[verified]** — confirmed by direct code inspection or an executed repro
- **[reasoned]** — the gap is confirmed present, but its runtime consequence is
  inferred from the architecture rather than observed
- **[carried]** — inherited from the pre-merge review, not re-tested since

Current status (2026-09-17): **P0–P10 QEMU gates green on both bases**;
**P11 (upstream landing) in progress** — the upstream base now carries a real
7-commit series (U7), each commit building and passing its own lit tests, and
the RFC is drafted ([RFC_BOLT_AARCH32.md](RFC_BOLT_AARCH32.md), not yet
posted). The `atfe` base still uses the legacy file-slice patches.

---

## Index

IDs are stable, not ordered by priority. **Next, in order:** post the RFC (U8)
→ U2 → U3 → U4 → L7 → remaining U9 sites → U5.

| ID | Item | Severity | Status |
|----|------|----------|--------|
| U1 | Full-image rewrite boots but moves only 7% of functions; output non-deterministic (8/8 runs differ) | Blocker | Open — narrowed 2026-09-17 |
| U2 | Relocation matrix incomplete, and BOLT-core / JITLink disagree | Blocker | Open |
| U3 | No `.ARM.exidx` / `.ARM.extab` unwind-table handling | Blocker | Open |
| U4 | No lit coverage for P9 (instrumentation) or P10 (optimization) | Blocker | Open |
| U5 | TBB/TBH jump-table targets unrecoverable | High | Open (intentional boundary) |
| U6 | `upstream` patch set missing 2 lit tests the `atfe` set has | High | **Resolved** 2026-09-17 |
| D3 | `isTerminator()` for POP/LDM corrupts emission | High | Open (fix reverted) |
| D5 | Function symbols dropped from rewritten output | Low | Open, not root-caused |
| L1 | Veneer detection is an LLD-specific naming heuristic | Medium | Open |
| L2 | `isTLS()` / `isGOT()` hard-return false for ARM | Medium | Open (fails safe) |
| L3 | `$t` mapping symbols emitted at odd addresses | Low | Open (ABI violation) |
| L4 | No arch-revision gating; `.ARM.attributes` recorded but not enforced | Medium | Open |
| U7 | No commit history — patches are `git diff HEAD` file-slices | Blocker | **Resolved** 2026-09-17 (upstream base) |
| U8 | `getMIBFor(bool)` leaks the ARM/Thumb predicate into 11 core call sites | Blocker (RFC gate) | **Code resolved**; RFC drafted, not posted |
| U9 | 33 standalone `isARM()` forks in core, ~95 hunks across 19 files | High | **Partly resolved** — 41→31 uses, 8 design calls left |
| L5 | `--no-lse-atomics` is dead on ARM; no ARM atomics option exists | Medium | **Resolved** (flag); no ARM atomics option yet |
| L6 | Indirect-call site descriptors = 0 despite correct classification | Medium | Unexplained |
| L7 | ARM swallows core invariant violations (pseudo count, invalid CFG) | High | Open — new |
| L8 | `FK_Data_8` → `R_ARM_ABS32` with no range check | Medium | Open — new |
| L9 | `apply-overlays.sh` silently skipped failing patches; patches stored CRLF | Blocker | **Resolved** 2026-09-17 |
| L10 | CRLF line endings in six new LLVM source/test files | High | **Resolved** 2026-09-17 |
| L11 | Quadratic symbol scans in BOLT's ARM JITLink pass | Medium | Open — new |
| L12 | `atfe` base not yet converted to a commit series | Medium | Open — new |
| D1, D2, D6 | — | — | **Resolved**, see history below |
| D4 | Non-deterministic output — reopened, now tracked under U1 | — | Open |

---

## Upstream blockers

### U1 — Full-image rewrite coverage, and non-deterministic output **[re-measured 2026-09-17]**

Two separate problems that the old entry merged.

**Full-image rewrite no longer breaks, but covers little.** An identity
rewrite of all of `lk.elf` with no allowlist (`llvm-bolt lk.elf -o out.elf`),
post-processed as usual, **boots and runs all 16 benchmarks**. So the old
"full-image layout breaks" statement no longer holds at the current series tip.
However only **100 of 1,398** code symbols were actually moved into the new
`.text` (about 7%); BOLT skips the rest. The dominant skip reason is
`unable to disassemble instruction` (37 warnings, e.g. `psci_call` at offset
0, `arm_generic_timer_init`, `ext2_mount`), plus 2 `internal call detected`.
Next step: classify those 37 instructions — likely system/coprocessor
instructions (`smc`, `mrc`/`mcr`) or ARM-mode assembly decoded with the wrong
disassembler — and decide which the backend should handle.

**D4 non-determinism is worse than recorded, and not thread-related.**
- 8 identical runs (fixed `-o`) → **8 distinct outputs**, both for the bench
  allowlist and for the full image. The old "10–20%" figure came from a 2-vCPU
  pod.
- `--thread-count=1` → still 8/8 distinct, so thread scheduling is not the
  cause.
- `setarch -R` (to disable ASLR) is blocked by the container
  (`Operation not permitted`), so the ASLR hypothesis can still only be tested
  indirectly.
- A byte diff of two runs localizes it: 130 bytes, **98 in
  `__llvm_jitlink_aarch32_STUBS_v7`** and 32 in `.text` (the branches into those
  stubs). The varying part is the layout of JITLink's aarch32 stubs, which
  BOLT's ARM path creates in a post-prune pass in `JITLinkLinker.cpp`.

Two fixes were tried and **neither made output deterministic** (lit 13/13 and
the QEMU pipeline still passed with each, so they are safe, just
insufficient):
1. Visit blocks sorted by (section ordinal, address) instead of JITLink's
   pointer-keyed set order.
2. Additionally give each new stub block a distinct placeholder address in
   creation order, because stubs are created at address 0 and JITLink's
   `BasicLayout` sorts same-section blocks only by address, then size.

Both are saved on the volume as `/workspace/d4-attempt-jitlinklinker.diff`
and are **not** in the series. The remaining difference has not been located
yet: a byte diff after fix 2 was started but lost when the pod was
terminated. Next step: re-run that diff, then check whether stub *contents*
(targets) rather than stub *order* differ, and whether another pointer-ordered
container (e.g. symbol or section iteration during emission) feeds it.

**Why it still blocks:** upstream CI treats non-reproducible output as a
failure even when every variant is correct, and 7% coverage on a real image is
not a general-purpose target yet.

### U2 — Relocation matrix is incomplete, and the two halves disagree **[verified]**

`bolt/lib/Core/Relocation.cpp` (patch 0005) handles 20 `R_ARM_*` types. The
JITLink aarch32 patch (0008) handles 11. **The sets are nearly disjoint.**

Present in BOLT-core only: `THM_CALL`, `THM_JUMP24`, `PREL31`, `PC24`,
`PLT32`, `V4BX`, `TARGET1`, `TARGET2`, `IRELATIVE`, `RELATIVE`, `ALU_PC_G0`.
Present in JITLink only: `THM_PC12`, `MOVW_BREL_NC`, `MOVT_BREL`,
`THM_MOVW_PREL_NC`, `THM_MOVT_PREL`, `ABS64`.

Absent from both: `THM_JUMP19` (Thumb conditional `B<cond>.W`), `THM_JUMP11`,
`THM_JUMP8`, the entire `GOT` family, the entire `TLS` family, `ABS16`/`ABS8`,
`LDR_PC_G0`.

The `R_ARM_THM_JUMP19` failure that blocks `-split-functions`
(`BOLT-ERROR: JITLink failed: Unsupported aarch32 relocation 51`) is a
**symptom of this structural gap, not an isolated bug** — BOLT records a
relocation, hands the emitted object to JITLink, and JITLink doesn't know the
kind. There is no single source of truth and no consistency check between the
two tables.

**Fix entails:** a documented, cross-checked relocation matrix with a test per
supported type and an explicit, diagnosed rejection for unsupported ones —
rather than adding kinds one at a time as failures surface.

### U3 — No `.ARM.exidx` / `.ARM.extab` unwind-table handling **[verified absent; consequence reasoned]**

Grep across all ten patches finds **zero** mentions of `exidx`, `extab`, or
`unwind`.

ARM32's unwind format is not AArch64's `.eh_frame`: it is an index table that
must remain **sorted by address**, because the unwinder binary-searches it.
BOLT reorders functions; `R_ARM_PREL31` *is* in `shouldRecordCodeRelocation`,
so individual entries get their offsets fixed up — but nothing re-sorts or
merges the table. A `.ARM.exidx.bolt.extra.1` section was observed in the
rewritten output, which suggests BOLT is appending rather than maintaining the
index.

**Consequence (reasoned, not yet observed):** unwinding silently resolves to
the wrong entry or fails. LK is `-fno-exceptions` C, so this has never
surfaced here — but it would affect any C++ binary, and any panic/fault
handler that walks a backtrace.

**Fix entails:** either implement exidx rewriting (relocate + re-sort + merge),
or detect the section's presence and refuse to rewrite with a clear diagnostic.
The second is a legitimate first-backend position if documented as such.

### U4 — No lit tests for P9 (instrumentation) or P10 (optimization) **[verified]**

The 12 lit tests cover P1–P8 only. P9 and P10 — the two most defect-prone
rungs, where D6 lived — have **none**, yet both are marked Done with upstream
PR titles drafted.

This directly contradicts the project's own stated principle ("one PR per rung;
each PR has lit tests and a clear pass gate"), so those two PRs cannot be
opened as specified. `docs/aarch32-bolt.md` also still records that
`check-bolt` was never confirmed green.

Also missing: any negative/diagnostic test (malformed ELF, unsupported
architecture → clean error rather than crash or silent mis-decode).

### U5 — TBB/TBH jump-table targets are unrecoverable **[verified]**

`analyzeIndirectBranch` returns `IndirectBranchType::UNKNOWN` for `t2TBB` /
`t2TBH`. This is deliberate and correctly documented in-code: it stops
disassembly walking into the jump-table data, but declines to decode entries.

**Consequence:** no Thumb function containing a table-branch switch receives
switch-aware layout. Switch statements are ubiquitous in real firmware, so this
degrades a large class of functions — safely, but visibly.

**Fix entails:** BOLT-core work — `BinaryFunction::analyzeJumpTable` assumes a
fixed-width pointer/delta array and needs support for TBB/TBH's 1- and 2-byte
entry format. Good self-contained follow-up; keeping the conservative bail-out
and documenting it as an intentional boundary is a defensible interim position.

### U6 — The `upstream` patch set is missing two lit tests the `atfe` set has **[verified]**

Patch-set drift, found 2026-09-17:

| Test | `atfe` | `upstream` |
|------|--------|-----------|
| `arm32-thumb-switch.test` (pins the U5 TBB/TBH bail-out) | present | **missing** |
| `arm32-thumb-pop-return.test` (pins POP/LDM-return recognition, D3-adjacent) | present | **missing** |

`atfe` has 12 tests, `upstream` has 10. This is precisely the drift the
single-repo merge was meant to end — and it is on the **actual upstreaming
target**, which therefore has weaker coverage than the arm-toolchain branch.

**Resolved 2026-09-17.** Both tests (and their inputs) were ported into the
upstream series, in the `[BOLT][ARM] Add AArch32 target` commit, and pass on
the upstream base. The upstream base now has 12 ARM tests, the same as `atfe`.

---

### U7 — No commit history; patches are `git diff HEAD` file-slices **[resolved 2026-09-17, upstream base]**

*Was:* `export-llvm-arm-patches.sh` emitted `git diff HEAD` slices of one
uncommitted working tree, split by file list — no commit messages, no logical
split, nothing `format-patch` could act on.

*Now:* the upstream LLVM checkout carries a real series on branch
`bolt-arm-backend`, and `overlay/llvm/patches/upstream/` stores it as
`git format-patch` output:

| # | Commit | Size |
|---|--------|------|
| 1 | `[BOLT] Emit __bolt_instr_tables on ELF` | +12 |
| 2 | `[BOLT] Warn instead of asserting on out-of-section secondary entry` | +14/−5 |
| 3 | `[JITLink][AArch32] Support Thumb literal loads, Thumb-bit absolutes, generic triples` | +101/−8 |
| 4 | `[ARM][MC] Accept BOLT's MOVW/MOVT and 8-byte data fixups in ELF` | +12 |
| 5 | `[BOLT][ARM] Add AArch32 target` (core, target, relocations, 12 tests) | ~+2400 |
| 6 | `[BOLT][ARM] Support long-branch veneers` (+ veneer test) | ~+130 |
| 7 | `[BOLT][ARM] Support instrumentation` | ~+35 |

Verified: commits 5 and 6 each build alone and pass their own tests (12/12,
13/13); the tip builds, passes 13/13, and passes the full QEMU pipeline.
`apply-overlays.sh` replays the series with `git am` onto a clean checkout,
reproducing the tip **tree and commit messages exactly**, and is idempotent.

Things fixed on the way, each worth knowing: the old `0001`/`0002` patches
were corrupt and their hunks duplicated inside `0006`/`0010`; the old export
diffed whole files, so overlapping files appeared in several patches; `git am`
strips `[BOLT]`-style subject tags unless run with `--keep-non-patch`; and the
LLVM root held six untracked scratch scripts (`port_*.py`, `fix_comment.py`),
now excluded. Two orphan test inputs referenced by no test
(`arm32-thumb-exit.s`, `elf32-arm-empty.yaml`) were left out of the series and
set aside on the volume under `/workspace/u7-orphans/`.

Still to do: the `atfe` base (L12). Commit messages carry `Co-Authored-By` /
`Claude-Session` trailers; strip them before submission if you prefer.

### U8 — `getMIBFor(bool IsThumb)` leaked the predicate into core **[code resolved 2026-09-17; RFC not posted]**

*Was:* eleven core call sites; ten re-derived
`BC.getMIBFor(BC.isARM() && Function.isARMThumb())` inline, and one
(`VeneerElimination.cpp`) spelled it `getMIBFor(BF.isARMThumb())` inside an
enclosing `if (BC.isARM())`. (An earlier version of this entry placed that
call in `LongJmp.cpp` and called it accidental; both were wrong.)

*Now:* `BinaryContext::getMIBFor(const BinaryFunction &)` and
`getSTIFor(const BinaryFunction &)`, defined out of line with the target check
inside; all eleven call sites pass the function. It is folded into commit 5,
so the series introduces the final API directly. Also removed: the
now-unused `MCPlusBuilder::setSTI()`/`getSTI()` this series had added,
comments narrating the removed `setSTI()` pattern, and **five references in
LLVM source and tests to `docs/KNOWN_LIMITATIONS.md`** — a file that exists
only in this overlay repo.

The RFC is drafted in [RFC_BOLT_AARCH32.md](RFC_BOLT_AARCH32.md). Posting it is
the remaining step and needs a person.

### U9 — Standalone `isARM()` forks in core **[partly resolved 2026-09-17]**

*Was:* 41 `isARM()` uses in core, 33 of them standalone forks.

*Now:* **31 uses.** The ten `getMIBFor` predicates are gone (U8), and a new
`BinaryContext::getCodeAddress(uint64_t)` replaces the inline Thumb-bit strips
in `BinaryContext.cpp`, `BinaryFunction.cpp` and `RewriteInstance.cpp`.
Classification of the 20 standalone uses left:

- **4 intended** — the `isARM()` definition, and inside `getMIBFor`,
  `getSTIFor`, `getCodeAddress`.
- **6 idiomatic, keep** — constructor arch dispatch, `$a`/`$t`/`$d` markers,
  the JITLink triple check, `ThumbMIB` construction, and ELF Thumb-symbol
  discovery (two sites). These match how RISC-V was added.
- **2 are defects, not refactors** — see L7.
- **8 need a design decision each:**
  - `BinaryEmitter::emitFunctions` rewrites veneer calls at emit time — a
    transformation inside the emitter that `VeneerElimination` duplicates
    ("BinaryEmitter repeats this late"); should become one pass.
  - `BinaryEmitter::emitFunctionBody` strips annotations only on ARM before
    encoding.
  - `BinaryFunction::getDisassembler` — acceptable encapsulation; keep.
  - `BinaryFunction::disassemble` resolves a symbolized branch operand when
    evaluation fails, on ARM only.
  - `BinaryFunction::isAArch64Veneer` holds the ARM (LLD) veneer names — an
    ARM clause in a function named for AArch64; rename or move to a hook
    (see also L1).
  - `BinarySection::flushPendingRelocations` sets the Thumb bit on absolute
    references to Thumb functions.
  - `VeneerElimination::runOnFunctions` ARM block.
  - `RewriteInstance` special case for `EntryOffset == 0`.

---

## Open defects carried forward

### D3 — `isTerminator()` for POP/LDM corrupts emission **[carried]**

Making `isTerminator()` report true for `POP {pc}` / `LDM`-based returns
corrupts emission; the change was **found and reverted**, so the underlying
core issue remains. `isReturn()` / `isIndirectBranch()` recognition for these
forms is in place and fine — it is specifically the terminator classification
that breaks.

### D5 — Function symbols dropped from the rewritten output **[carried]**

After rewrite, some functions are absent from the output symbol table
entirely, so `llvm-objdump` misattributes their code to the nearest preceding
symbol. Cosmetic for execution, actively misleading when reading a
disassembly. Not root-caused.

### L1 — Veneer detection is an LLD-specific naming heuristic **[carried]**

`isPossibleVeneer` matches LLD's `__ARMv7…` / `__Thumb…` symbol naming, so it
will not fire against GNU-ld or gold-linked binaries. Fails open (veneers go
unrecognized) rather than corrupting.

### L2 — `isTLS()` / `isGOT()` hard-return false for ARM **[carried]**

Fails safe — skips optimization rather than corrupting — but is a real gap for
any TLS- or GOT-using binary. Related to the missing relocation families in U2.

### L3 — `$t` mapping symbols emitted at odd addresses **[verified]**

Observed at `0x80400001`, `0x80400081`, `0x80400101` in instrumented output.
Per the ARM ELF ABI, mapping symbols carry **no** Thumb bit — their `st_value`
is the plain address of the first byte of the sequence. The CPU is unaffected,
but disassemblers are: this is what made `llvm-objdump` output for the stub
region unreadable during the 2026-09-16 investigation.

### L4 — No architecture-revision gating **[verified]**

`.ARM.attributes` is recorded but explicitly not enforced (P1, by design at the
time). `isSafeToEncodeARM` is a *structural* operand-shape guard — it checks
that register operands really are registers and that variadic register lists
round-trip — not an ISA-feature check. Consequence: an ARMv6, M-profile,
MVE/Helium, or ThumbEE input is *attempted* rather than cleanly rejected.

The documented out-of-scope list (Cortex-M / Thumb-only M-profile, ThumbEE,
Jazelle, ARMv8 AArch32 BTI/PAC, shared libraries / PLT) is a doc statement, not
something the code enforces. Big-endian (`armeb` / `thumbeb`) appears in the
JITLink triple fallback and is entirely untested.

---

### L5 — `--no-lse-atomics` was dead on ARM **[flag resolved 2026-09-17]**

It is the AArch64 `cl::opt`; the ARM target never reads it and always uses an
`ldrex`/`strex` loop. Both driver scripts now pass it only when `ARCH` is not
`arm32`. Verified from the command line BOLT records in `.note.bolt_info`:
absent from both the instrumented and the optimized ARM images.

Still open: there is **no** ARM-side atomics option, so nothing lets ARMv8.2-A
hardware such as Cortex-A55 opt into `stadd`.

### L6 — Indirect-call site descriptors = 0 **[explained 2026-09-17]**

Not a backend bug. `Instrumentation.cpp` instruments indirect calls only
`if (opts::InstrumentCalls && MIB->isIndirectCall(*I))`, and
`instrument-lk-bolt.sh` passes `--instrument-calls=false`, so no call site is
ever instrumented.

The residual that matters: **the ARM indirect-call instrumentation hooks
(`createInstrumentedIndirectCall` and the handler entry/exit blocks) have never
been exercised** — not by lit, not by QEMU. They are compiled, untested code.
Enabling `--instrument-calls` needs the bare-metal runtime to provide the
indirect-call handler first.

### L7 — ARM swallows core invariant violations **[verified]**

Two places turn a core invariant failure into "quietly ignore the function",
on ARM only:

- `BinaryBasicBlock::getNumPseudos()` — on a pseudo-instruction count
  mismatch, ARM overwrites the cached count, marks the function ignored and
  returns. **This code is inside `#ifndef NDEBUG`.** In a release
  (no-assertions) build it compiles out and the wrong count is returned. This
  project only builds with assertions, so ARM release-build behaviour has
  never run. The mismatch is the one behind the `-peepholes` failure.
- `BinaryFunction::postProcessBranches()` — where core asserts on an invalid
  CFG, ARM warns and ignores the function, in all builds.

A reviewer will ask why ARM produces bad pseudo counts and invalid CFGs at
all. Fix the causes and drop both special cases; at minimum make the first
behave the same with and without assertions.

### L8 — `FK_Data_8` mapped to `R_ARM_ABS32` without a range check **[verified]**

`ARMELFObjectWriter` (series commit 4) maps 8-byte data fixups, which BOLT emits
for padded functions, to `R_ARM_ABS32`, assuming the value fits in 32 bits.
Nothing checks that. Recorded as a `FIXME` in the commit message. Fix with a
range check, or stop BOLT emitting 8-byte data on 32-bit targets.

### L9 — Overlay could silently fail to apply its own patches **[resolved 2026-09-17]**

`apply-overlays.sh` printed a warning and **skipped** any patch that failed to
apply, and the patch files were committed with CRLF bytes inside their git
blobs (1,534 CR lines in one patch). A fresh checkout could therefore produce
an LLVM tree missing patches while reporting only warnings. Now: patches are
applied as a series with `git am` and any failure is fatal;
`.gitattributes` marks `*.patch` as `-text`; the exported series has zero CR
bytes.

### L10 — CRLF line endings in LLVM sources **[resolved 2026-09-17]**

Six new files in the LLVM tree had CRLF endings throughout
(`ARMMCSymbolizer.h`, `Target/ARM/CMakeLists.txt`, three test inputs,
`bolt/test/ARM/lit.local.cfg`) — the result of the CRLF patch round trip in
L9. Converted to LF before the series was committed.

### L11 — Quadratic symbol scans in BOLT's ARM JITLink pass **[verified]**

`JITLinkLinker.cpp`'s ARM pre-prune pass scans every `BinaryFunction` for each
symbol to decide Thumb-ness, then compares every defined symbol against every
other to propagate the flag within a block. Cost is O(symbols × functions) +
O(symbols²). Harmless at LK's size (about 1,400 functions); a problem on real
application binaries. Use a name→function map and a per-block pass.

### L12 — `atfe` base not yet converted to a commit series **[verified]**

U7 was done for the upstream base only. `overlay/llvm/patches/atfe/` still
holds the old file-slice patches, applied by the legacy path in
`apply-overlays.sh`, and the `atfe` LLVM tree likely has the same CRLF files
as L10. Upstream submission does not need `atfe`, but cross-base verification
does: replay the upstream series onto `arm-software` (expect conflicts — the
branches have diverged) and export it the same way.

---

## Deferred scope — name it, don't half-implement it

A first backend that declares **"static, `-fno-exceptions`, non-TLS,
LLD-linked, ARMv7-A / little-endian binaries"** and holds that line reviews
better than one claiming general support with gaps found during review. The
items above marked *fails safe* are candidates for that declared boundary
rather than for implementation before submission.

## Process prerequisite

The project's own plan requires an **RFC on LLVM Discourse before opening P4**,
because `MCPlusBuilder` is shared infrastructure and the `getMIBFor()`
dual-builder change touches every target. P4 through P10 are complete and the
RFC has still not been posted — it is now seven rungs overdue and is a hard
gate for landing any of this. It should propose the U8 signature,
`getMIBFor(const BinaryFunction &)`, not the current `getMIBFor(bool)` — the
latter would be sent back on first review.

## Historical record

The pre-merge defect catalogue (D1–D6 with full repros, the `setSTI()` race
investigation referenced from patch 0003's code comments, and the original
completeness review of 2026-09-15) lived in the `atfe-bolt-aarch32` repo, which
has since been deleted from GitHub. It is preserved as a git bundle —
`atfe-bolt-aarch32-legacy.bundle`, 22 commits, restore with
`git clone atfe-bolt-aarch32-legacy.bundle` — and that doc is at
`docs/KNOWN_LIMITATIONS.md` inside it.

Resolved there and still resolved: **D1** (literal pools / constant islands),
**D2** (instrumented boot crash — `fix-kernel-elf-sections.py` ARM/Thumb hook
dispatch), **D6** (`Thumb_MovwAbsNC` JITLink failure —
`createInstrumentationSnippet` using the ARM-mode builder unconditionally).
**D4** is resolved-as-characterised, and is folded into U1 above.
