# ATFE correctness re-evaluation through overlay 0038

Reviewed 2026-10-02: Windows base `5049da5` plus overlay 0038, against the live
ATFE tree at `bcc08884995ff3cbee70749524621803b9bd258a`. The previously local
0038 overlay is included unchanged with this review so the assessed source can
be reproduced. This review makes no backend implementation changes. Upstream
remains excluded. The user reactivated #12; all its remaining validation and
provenance work is included in the consolidated priority queue.

## Assessment

Follow-up 2026-10-03: overlay 0039 closes F1 for decoded original function code
without relying on discovered entry roots. The original eight bypass inputs now
reject in both builds; expanded tests pass. Overlay 0040 also fixes F2's Thumb
startup crash, with 40 cases and fresh runtime-to-Thumb Pi checks in both builds.
Static finalization remains a dummy return; dynamic hooks/PIE policy and F3-F5
remain open. See [0040 evidence](results/correctness_thumb_startup_20261003.json).
See [follow-up evidence](results/correctness_interior_reservations_20261003.json)
and [current status table](CORRECTNESS_PRIORITY_TODO.md). Findings below retain
their original 0038 observations.

The backend has substantial verification for a selected, static little-endian
ARM/Thumb bare-metal subset. It now has working splitting and inline Thumb tables,
restricted inlining, flag-preserving CBZ/CBNZ expansion, full-width counters,
quiet state preservation, IT/nested-count coverage, runtime clears and several
explicit rejection boundaries. These are real improvements over the previous
review and should not be described as absent or wholly untested.

**General AArch32 ELF or whole-firmware correctness is still not established.**
Fresh probes expose a skipped interior-entry reservation bypass, Thumb-entry
instrumentation crashes, synthesized instructions exceeding an ARMv6 input's
features, and a static-PIE admission/rebasing gap. Passing the current tests does
not cover these inputs. Three original items remain complete within their stated
scope (#2/#8/#10); nine remain open. See the new
[priority queue](CORRECTNESS_PRIORITY_TODO.md).

This review covers the major edge-case classes below, not every possible binary,
instruction stream or option combination. Unsupported behavior must have an
enforced rejection boundary before the backend can claim a bounded contract.

## Fresh evidence and its limits

| Check | Assertions on | Assertions off |
|---|---:|---:|
| Focused BOLT ARM + LLVM JITLink AArch32 tests | 48 passed | 47 passed, 1 expected debug-only skip |
| CoreTests | 58 passed, 31 expected skips | 58 passed, 31 expected skips |
| New review boundary observations | 17 | 17 |
| Confirmed admitted interior-entry routes to counter stores | 4 | 4 |

All 60 existing Python script tests pass; serial/tool observations in those tests
are mocked. All **38 overlays replay to the exact live source bytes**, with no
uncovered or mismatched files. Source identity is
`d2e9272859daa806082419c5c9e8522bdc8233693659c81453538e42c31f2b56`.
The dirty ATFE/LK trees were preserved. This source replay does not prove a clean
full build or that a binary's version banner identifies its overlay contents.

No new Pi execution occurred. Previously recorded hardware checks remain useful:
the quiet leaf register/CPSR/carry/wrap matrix, nested Thumb/recursion/IT counts,
quiescent runtime clear, inlining/CBZ results and required rewritten-body samples.
Supported 0038 fixture payloads match previously executed 0036 bytes. That equality
supports those exact payloads, not new edge cases or arbitrary firmware. The
2,976-case conditional-boundary matrix, 840-case inlining matrix and other fixture
counts overlap in scope; they are not an exhaustive coverage percentage.

Compact evidence, tool/source/patch identities and observations:
[review results](results/correctness_0038_review_20261002.json). Raw logs, assembly,
ELFs and snapshots remain under `out/correctness/review-0038-20261002/`.

## Confirmed findings

### F1. Skipped unnamed interior entries bypass the reservation gate — P0 (#6/#9)

Overlay 0038 rejects known multiple-entry exclusive functions, but does not
establish that all entry routes have been discovered. The new fixture has a
skipped `reservation` function whose main entry completes a local LDREX/STREX
pair and returns. Another caller enters **`reservation + 12`**, where the code
saves LR, performs LDREX, calls the selected `callee`, performs STREX and returns.
The interior entry has no separate STT_FUNC symbol. Both a direct BL with an
addend and a MOVW/MOVT/BLX pointer route are accepted.

All eight combinations pass admission: direct/pointer, unselected/explicitly
skipped, assertions on/off. Original-code bytes retain the interior route. The
existing supported callee-entry redirect then branches into the generated
counter body. Independent A32 branch decoding verifies the chain and counter
stores inside the outstanding reservation window. This is host admission and
loaded-byte evidence; no Pi reservation failure was measured.

The validator starts its worklist at the first decoded instruction. Its
`BF.isMultiEntry()` check misses this undiscovered root. Skipped functions use
`scanExternalRefs()`; references to a target that will not be emitted can be
discarded before establishing a secondary entry. Moving the gate after discovery
does not solve incomplete discovery. Discover entry roots across kept/skipped
code and pointer/addend references, or reject uncertain exclusive functions.
The 133 existing cases still pass and remain valid for their tested scope;
they do not close this gap. Until fixed, do not certify exclusive code with
unnamed interior-entry routes for instrumentation.

### F2. Thumb ELF-entry instrumentation crashes in both modes — P0 (#9/#3)

A valid Thumb `_start` with odd ELF entry rewrites successfully without
instrumentation in both builds. Instrumentation aborts with assertions enabled
at `Instrumentation.cpp:803`, `Entry point function not found`; assertions off
segfaults at the same auxiliary-function path. Neither produces an output ELF.

`createAuxiliaryFunctions()` looks up the raw entry address and dereferences the
result after a debug-only assertion. Overlay 0021 fixed the separate output ELF
entry relocation; it did not fix this startup lookup. Normalize the lookup,
preserve instruction-set state in the generated route, and diagnose absent
functions safely in both builds. Disabling assertions is not a workaround.

### F3. ARMv6 instrumentation emits instructions outside the input ISA — P0 (#7/#6)

Fresh ARMv6 input declares ARMv6/Thumb-1 attributes. Both builds accept it for
instrumentation and emit MOVW/MOVT in counter bodies, for example bytes
`e30c0000 e3400000` at the first counter-address materialization. The independent
assembler rejects these instructions under `.arch armv6` with
`instruction requires: armv6t2`.

Reading attributes for decoding does not constrain synthesized instructions.
The context also substitutes an `armv7` triple for generic ARM naming. Enforce
an initial ISA/profile/ABI contract and check emitted instrumentation/stubs
against it, or reject the ARMv6 input. This is a confirmed feature-boundary
violation from input attributes and output bytes; no ARMv6 hardware was run.

### F4. Static PIE is admitted with absolute instrumentation pointers — P0 (#7/#11/#6)

Both builds accept an ET_DYN static PIE carrying DF_1_PIE without PT_INTERP,
including instrumentation. `IsStaticExecutable` becomes true for that input,
so the bare-metal gate admits it. The output still has ET_DYN, but contains
absolute counter-address MOVW/MOVT materializations (`0xc000`, etc.) and **no
relocations** in the reproduced output.

With a nonzero load bias, the counter section moves while those instruction
constants remain unchanged. Wrong addressing follows from the emitted bytes;
rebased execution was not measured on hardware. A successful fixed-address
emission is not PIE support. Require a verified fixed-load contract/ET_EXEC
boundary or implement and verify rebasing for generated code and runtime.
The previous statement that all shared/dynamic inputs reject was too broad:
the existing shared-object regression passes, but static PIE is a separate hole.

### F5. Missing attributes and BE8 flags lack an explicit exclusion — P1 (#7)

Inputs with `.ARM.attributes` removed, and LE ELF inputs carrying EF_ARM_BE8,
are accepted in ordinary rewriting and instrumentation in both builds. These
are admission observations, not hardware corruption proofs. Attribute absence,
conflicts and unsupported profiles/features need explicit policy. LE-only
ELF class admission already exists; do not confuse this with accepting ELF32BE
or claim the existing endian check is absent. BE8/BE32, M-profile, FP/SIMD,
ThumbEE/Jazelle and ABI variants remain outside the verified contract until
rejected or separately validated.

## Edge-case coverage and outstanding caveats

| Area | Credited boundary/evidence | Remaining edge cases and consequence |
|---|---|---|
| Relocations/literals (#1) | A32/Thumb literal hooks, BLX fix, THM_JUMP19, Thumb split-state marking and linked-ELF probes | Full signed endpoint/overflow/alignment/addend/PC-bias/state-bit matrix; conditional calls, BLX H bit, optional writes and kept code. Declaration sets disagree across layers. |
| EHABI (#2) | Genuine unwind tables/descriptors reject; documented CANTUNWIND case admitted | No general exidx/extab rewriting or arbitrary unwinder certification. Completion is scoped rejection. |
| CFG/pseudos (#3) | Stale counts, fallthrough and invalid postprocessing reject in both builds; joined-worker fatal exit | Wider mutation invariants, target-builder selection and safe fallback still need audit. F2 demonstrates a remaining release-build crash. |
| Control transfers (#4) | POP/LDM return forms, CBZ flags, restricted forced inlining, unsupported PC writes/exception returns reject | General predicated-return exit modeling, traps/system transfers, unusual indirect/tail routes and broader pass consumers. Instrumentation rejection does not implement a general exit graph. |
| State/counters (#5) | Full uint64 carry/wrap, quiet R0-R12/LR/SP/CPSR matrix, IT groups, nested Thumb counts and quiescent clear on Pi | Mixed-ISA nested complete state, active ISR, zero/multi-entry CFGs and live snapshots. GE/NZCV tests do not exhaust every independent combination. |
| Runtime scope (#6) | Privileged single-core/no-FIQ acknowledgement; unsupported call/process profiling rejects; selected exclusive functions reject | F1. Active IRQ/exception entry is not covered by the quiet hardware fixture. The flag cannot prove privilege, parked cores or quiescence. User-space/SMP/FIQ and concurrent reset/read remain unsupported. A relocated skipped SVC with a live reservation rejects in the review control. |
| ISA/ABI/endian (#7) | LE ELF class gate, attribute-guided decoder features | F3/F5; supported target whitelist and synthesized-feature checks absent. Instrumentation and ordinary optimization have different privilege requirements. |
| ELF32 data width (#8) | Resolved eight-byte data writes; unresolved symbolic 64-bit relocations reject | Other relocation semantics and counter-source identity remain separate. |
| Entries/symbols (#9) | Ordinary Thumb entry relocation, mapping addresses, function state bits and supported fragment/redirect checks | F1/F2; aliases, unnamed interior entries, data-to-code/function pointers, missing mapping symbols and short/overwritten entry routes. |
| Stub determinism (#10) | Stable visitation/layout and mixed-stub alignment tested | Completion covers tested generated code; branch endpoint correctness is still #1. ELF notes/invocations can differ. |
| Tables/inline data (#11) | Restricted PC-based TBB/TBH, reverse-layout stubs and mapped islands | Table reach limits, malformed/ambiguous islands, shared cases, ARM tables and splitting/instrumentation interactions. Other indirect forms can remain unoptimized. |
| ELF/runtime constructs (#7/#11) | Static bare-metal fixtures, genuine shared-object instrumentation rejection | F4; GOT/TLS/PIC/PLT/dynamic support is not proved by returning false from ARM classifiers. Fixed-load/in-place rewriting needs its own execution boundary. |
| Pass combinations (#4/#11) | Selected reorder/inlining/peephole-option/splitting configurations | Profile-driven combinations, tail duplication, ICF/address-identity and debug/DWARF need actual transformed/executed evidence. A pass that makes no change supplies no transformation proof. |
| Validation/provenance (#12, active) | Truncated metadata/counters reject, graph validation, atomic profile publication, sampled-image identity, complete named results, scoped rewritten PC evidence; fresh source replay | Counter locations still need exact original-image binding; PMU/core ownership and other gate execution proofs remain incomplete. Filename stamps and version banners are not content identity; clean full-build provenance remains open. |
| Whole firmware (#11/#12) | Scoped required rewritten-body execution and independent workload checks | Emitted symbol counts and a boot do not prove execution of all rewritten functions, preserved reference integrity, far-call coverage or general interrupt-driven kernel correctness. |

The source declaration difference is concrete: BOLT core recognizes PC24,
PLT32, TARGET2, ALU_PC_G0 and V4BX without matching JITLink translations; JITLink
recognizes GOT_PREL, LDR_PC_G0, THM_PC12 and Thumb MOVW/MOVT PREL without matching
core recognition. NONE/V4BX/ALU_PC_G0 have explicit skip paths. Some differences
can be intentional, but each needs an end-to-end support or rejection argument.
These declarations alone are not newly reproduced silent-corruption cases.

## Reproduce the fresh admission findings

Run once per current build, using a fresh output directory each time:

```sh
python3 scripts/review_aarch32_boundaries.py \
  --toolchain /home/user/bolt-aarch32/build-atfe/bin \
  --out out/correctness/review-0038-on
python3 scripts/review_aarch32_boundaries.py \
  --toolchain /home/user/bolt-aarch32/out/correctness/build-atfe-noasserts-20261002/bin \
  --out out/correctness/review-0038-off
```

The script changes generated scratch ELFs only. It records 17 observations per
build, assembly/link/BOLT logs, attributes, output disassembly, map/redirect
evidence and hashes. Exit zero means the audit ran; it is not a correctness pass.
No source reset, overlay reapplication in the live tree, hardware run or backend
fix is part of this review. See the prioritized closure tasks in
[CORRECTNESS_PRIORITY_TODO.md](CORRECTNESS_PRIORITY_TODO.md).
