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

Current status: **P0–P10 QEMU gates green on both bases** (`BASE=upstream` and
`BASE=atfe`); **P11 (upstream landing) not started**. The items below are what
stands between those two facts.

---

## Index

IDs are stable, not ordered by priority. **Current priority order** (per the
2026-09-17 [UPSTREAMING_REVIEW.md](UPSTREAMING_REVIEW.md)): U7 → U8 → U9 →
L5 → then U1–U6 in listed order.

| ID | Item | Severity | Status |
|----|------|----------|--------|
| U1 | Full-image rewrite unusable; only a function allowlist works | Blocker | Open |
| U2 | Relocation matrix incomplete, and BOLT-core / JITLink disagree | Blocker | Open |
| U3 | No `.ARM.exidx` / `.ARM.extab` unwind-table handling | Blocker | Open |
| U4 | No lit coverage for P9 (instrumentation) or P10 (optimization) | Blocker | Open |
| U5 | TBB/TBH jump-table targets unrecoverable | High | Open (intentional boundary) |
| U6 | `upstream` patch set missing 2 lit tests the `atfe` set has | High | Open |
| D3 | `isTerminator()` for POP/LDM corrupts emission | High | Open (fix reverted) |
| D5 | Function symbols dropped from rewritten output | Low | Open, not root-caused |
| L1 | Veneer detection is an LLD-specific naming heuristic | Medium | Open |
| L2 | `isTLS()` / `isGOT()` hard-return false for ARM | Medium | Open (fails safe) |
| L3 | `$t` mapping symbols emitted at odd addresses | Low | Open (ABI violation) |
| L4 | No arch-revision gating; `.ARM.attributes` recorded but not enforced | Medium | Open |
| U7 | No commit history — patches are `git diff HEAD` file-slices | Blocker | Open |
| U8 | `getMIBFor(bool)` leaks the ARM/Thumb predicate into 11 core call sites | Blocker (RFC gate) | Open |
| U9 | 33 standalone `isARM()` forks in core, ~95 hunks across 19 files | High | Open |
| L5 | `--no-lse-atomics` is dead on ARM; no ARM atomics option exists | Medium | Open |
| L6 | Indirect-call site descriptors = 0 despite correct classification | Medium | Unexplained |
| D1, D2, D4, D6 | — | — | **Resolved**, see history below |

---

## Upstream blockers

### U1 — Full-image rewrite doesn't work; only an explicit function allowlist does **[verified]**

Every driver script defaults to `--funcs-file-no-regex` scoped to
`bolt_bench_*`. Full-image rewrite hits trampoline-leftover and literal-pool
issues outside that set (see `docs/aarch32-bolt.md` P8: *"Full `bolt_bench_*`
rewrite still breaks sequential `all` (trampoline leftover)"*).

Compounding it, **D4 non-determinism is still live**: ~10–20% of byte-identical
invocations produce different output, localized to a JITLink-materialized
absolute address (a `MOVW`/`MOVT` stub picking between two in-range addresses)
plus downstream veneer offset shifts. Both variants boot and run correctly, so
it is harmless in practice — but upstream CI treats non-reproducible output as
a failure regardless of whether the variants are functionally equivalent.

**Why it blocks:** upstream BOLT's entire model is whole-binary optimization. A
target that needs a hand-curated allowlist to avoid breaking is not yet a
target. This gates the credibility of everything else.

**Fix entails:** root-cause the trampoline/literal-pool interaction outside the
bench set, and settle D4 (most likely a pointer-identity-sensitive tie-break
feeding symbol ordering — the ASLR-disabling test to confirm was never run
because the container lacks `CAP_SYS_ADMIN`).

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

**Fix entails:** port both test files into
`overlay/llvm/patches/upstream/0007-bolt-arm-lit-tests.patch`, then add a
check that both patch sets' test inventories match.

---

### U7 — No commit history; patches are `git diff HEAD` file-slices **[verified]**

`scripts/export-llvm-arm-patches.sh:22` is the whole export mechanism:
`git -C "$LLVM" diff HEAD -- "$@" > "$DEST/$name"`. The ARM backend exists as
one uncommitted working tree on the pod volume; each "patch" is a slice of it
partitioned by file list. All ten begin with `diff --git` — no commit
message, no rationale, nothing `format-patch` can act on. The split is by
**file**, not by logical change, so the P1–P10 rung structure exists only in
prose. Reconstructing a real commit series is the first task and is not
mechanical. Detail: [UPSTREAMING_REVIEW.md](UPSTREAMING_REVIEW.md).

### U8 — `getMIBFor(bool IsThumb)` leaks the predicate into core **[verified]**

Eleven core call sites; ten re-derive
`BC.getMIBFor(BC.isARM() && Function.isARMThumb())` inline, and one
(`LongJmp.cpp`, patch 0009 line 155) omits the `isARM()` guard — it works on
non-ARM targets only by accident. Every core caller must know the words
"ARM" and "Thumb." This is the RFC-worthy change, and the signature the RFC
must propose is `getMIBFor(const BinaryFunction &)` with the check inside.

### U9 — 33 standalone `isARM()` forks in core **[verified]**

41 `isARM()` conditionals across 13 core files; 33 are standalone forks
rather than `isARM() || isAArch64()` shared paths. `RewriteInstance.cpp`
carries 9, `BinaryFunction.cpp` 7. Some are legitimate ELF32-vs-ELF64
branches; many are target behavior that belongs behind an `MCPlusBuilder`
virtual. Core blast radius: ~95 hunks across 19 files.

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

### L5 — `--no-lse-atomics` is dead on ARM **[verified]**

Appears in zero patches — only `scripts/instrument-lk-bolt.sh:81` and
`scripts/optimize-lk-bolt.sh:44`. It is the AArch64 `cl::opt`; BOLT accepts
it globally and the ARM target never reads it. The ARM counter path uses
`ldrex`/`strex` unconditionally. Looks like a copy-paste error to a reviewer,
and means there is **no** ARM-side atomics option — nothing to opt into
`stadd` with on ARMv8.2-A hardware such as Cortex-A55.

### L6 — Indirect-call site descriptors = 0, unexplained **[verified absent; cause unknown]**

Instrumenting `bolt_bench_indirect_call` reports `Number of indirect call
site descriptors: 0` despite a real function-pointer call. Not a missing
hook — all ten instrumentation hooks are implemented, including
`createInstrumentedIndirectCall`. Not a classification gap — `isIndirectCall`
accepts `ARM::BLX`, `ARM::BLX_pred`, `ARM::tBLXr`. Static review cannot
explain the zero. Needs `llvm-bolt --print-cfg` on that function in the
instrumented build before it can be called a bug.

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
