# AArch32 correctness review through overlay 0045

Reviewed 2026-10-04 against the live ATFE source at
`bcc08884995ff3cbee70749524621803b9bd258a` with overlays 0001–0045,
and the current verification scripts. Upstream is outside this assessment.
The prioritized follow-up table is [CORRECTNESS_PRIORITY_TODO.md](CORRECTNESS_PRIORITY_TODO.md).

## Assessment

The supported fixed-address, little-endian ARMv7-A/Thumb-2 subset has substantial
verification and explicit admission boundaries. General AArch32 ELF rewriting,
whole-LK correctness, arbitrary pass combinations, and concurrent instrumentation
are **not established**. The next milestone improves verification of selected
code; it does not close consolidated P0 item 6 or original workstream #12.

This review reads the current target builder, disassembly/CFG admission,
reservation analysis, instrumentation, entry redirection, profile/measurement
tools, and QEMU/Pi verification paths. It compares their contracts with the
recorded regression and execution evidence. This is a review of major edge-case
classes, not an exhaustive proof over all binaries or an independently clean
compiler build. New observations below distinguish source risks from reproduced
failures. No new backend failure is claimed solely from reading source.

## What is verified or conservatively excluded

| Area | Current evidence / boundary | Limit |
|---|---|---|
| Exclusive reservations | 0039 analyzes decoded acquisitions in skipped code, including unnamed interior routes; cross-function live reservations reject | Does not discover arbitrary executable bytes outside function/data metadata or prove concurrent monitor behavior |
| Startup / ISA / ABI | 0040–0041 repair Thumb startup and enforce LE v7-A/Thumb-2, EABI5/base-AAPCS and runtime feature admission | Quiet privilege acknowledgement is not evidence of physical core/interrupt inactivity; dynamic finalization is unsupported |
| ELF addressing | 0042 enforces fixed-load ET_EXEC and rejects PIE/dynamic/TLS/GOT/PLT machinery | No rebasing or generic loader support |
| Profile identity | 0043 binds sealed profiles to input/source/map/tool identities and checks counter offsets | Synthetic capture coverage is not end-to-end hardware training; caught-error rollback is not power-loss atomicity |
| Calls / interworking | 0044 verifies four ISA pairs and correct Thumb-caller stub/link construction | Explicit supported literal veneers; automatic v7 thunks and broader reference routes remain open |
| Position dependence | 0045 rejects unmodeled explicit/implicit PC reads and ADR, preserving modeled word literals, returns, calls and inline tables | Original NEON memcpy and arm_reset remain outside admitted whole-LK transformation |
| QEMU selected execution | Four integer-only ARM entries in a linked protected reservation have exact-map redirection and live entry witnesses | Entry execution does not prove every internal block, alias, callee, or memory/register effect |
| Independent sinks | A source-derived uint32 model checks all eighteen results for one exact approved QEMU ELF | No approved whole-LK Pi contract or general source/config/variant oracle |
| Pi far calls | BL/LR witnesses replace the excluded MOV-PC fixture; four ISA pairs, normal/reverse layouts, arithmetic/memory/NZCV/SP and fault checks | Core 0 HYP, masked IRQ/FIQ, MMU/caches off; selected state only |

See the [0045 PC-read evidence](results/correctness_pc_reads_20261004.json)
and the [milestone contract](AARCH32_ORACLE_MILESTONE.md) for exact scope and results.
All 45 overlays replay to the assessed source contents. That is source identity,
not proof of clean compilation or the provenance of every installed tool.

## Remaining findings and caveats

### R1. Every verification entry point needs a consistent certification boundary — P0

`qemu_rewrite_gate.py` now requires the approved input contract, exact selection,
redirects and entry witnesses, and independent baseline/candidate sink results.
`qemu_workload_gate.py` requires the oracle on ARM, but its non-ARM and log-only
paths remain explicitly output-consistency/parser diagnostics. The legacy workload
wrapper now routes its final ARM stage to the exact rewrite gate, but the complete
profile → optimization → redirect → execution pipeline has not been validated
end to end with those changes. A passing route-helper/unit test is insufficient.

Pi whole-image verification now rejects inputs without a reviewed Pi oracle
contract before upload. There is currently **no approved Pi whole-LK contract**.
That rejection is an enforced exclusion, not completed hardware coverage.
Measurement/stair/PGO tools validate framing and checksum consistency but cannot
be substituted for a selected-execution certificate. Review each wrapper's
claims, disabled-boot paths, late errors, and artifact publication behavior.

### R2. Independent expected values are intentionally narrow — P0

The approved integer-only QEMU input differs from the ordinary NEON fixture.
Its compiler configuration also defines `__thumb__` while emitting ARM code;
the oracle models the actual source/configuration rather than inferring it from
ISA. Unknown input hashes/platforms reject. New workload seeds/configurations,
Thumb kernels, other memcpy implementations, and profile-driven transformations
need reviewed contracts and actual selected execution. Shared wrong baseline and
candidate values must continue to fail. Sink equality cannot certify all GPRs,
SIMD/VFP state, memory safety, exception behavior, or internal branch coverage.

### R3. Manual and legacy routes still need an end-to-end audit — P0

`redirect-bolt-entries.py` checks exact symbol/mode/section bounds, original bytes,
overlapping known entries, and now rejects a four-byte Thumb patch that splits a
following wide instruction. It still offers a legacy single-function route
without a map, and symbol checks do not discover unnamed targets into overwritten
bytes. Manual entry-counter hooks are explicitly rejected; section restoration
has bounded/atomic checks. Keep these exclusions unless scratch capacity,
PC-relative prologue relocation, whole instruction boundaries, and exact count
semantics are implemented and validated. Exercise both host and real wrapper
failure paths before calling this audit complete.

### R4. Durable evidence and #12 remain broader than this milestone — P0 / P1

Fresh receipts record upload/image/loader/script/tool/patch identities, options,
selected/emitted/eliminated functions, executed ISA pairs and complete logs.
The milestone uses no training profile. It therefore does not certify profile
capture or every legacy measurement path. Receipt publication itself needs a
full fixture/CLI test: the first wider Pi run passed execution checks but failed
late receipt construction; preserve it as a failed run, not a success certificate.
Identity hashes detect stale/changed artifacts within the workflow; they are not
signed attestations or protection against malicious producers.

### R5. Predicated returns still lack general CFG edges — P1, admission-sensitive

`ARMMCPlusBuilder.cpp:300` keeps predicated returns inside a block because their
taken exit and fallthrough are not modeled as two CFG edges.
`Instrumentation.cpp:669` explicitly rejects such selected functions for
spanning-tree profiling. That instrumentation gate is not a general guard for
every optimization pass. Audit generic passes that consume successor/execution
information; model both edges or reject the affected pass/input combinations.
This is a confirmed modeling gap in source, not a newly reproduced runtime bug.

### R6. Relocation and veneer recognition need a complete route matrix — P1

The recorded-code relocation list in `ARMMCPlusBuilder.cpp:170` is narrower
than the full AArch32 relocation family. Establish each route through extraction,
MC emission, JITLink, pending writes, and kept code before interpreting declaration
differences as defects. Test signed range endpoints, addends, alignment, BLX H
bits, Thumb mode bits, narrow/wide branches, predicates and split/cold paths.

`matchAbsLongVeneer` at line 976 probes candidate words at known offsets and
resolves them to functions. Inspect its caller's recognition preconditions and
add malformed-name/opcode/size/data controls: the word probe alone does not prove
the instruction pattern. Automatic retained MOVW/MOVT thunks still have an old
target caveat from prior review; a correct tested new stub does not certify every
retained-thunk route. No new runtime failure is asserted here.

### R7. Entries, inline tables and ignored code are wider than selected fixtures — P1

PC-read rejection occurs on decoded function instructions; undecodable functions
can become ignored, and inline data/mapping symbols affect which bytes decode.
Exact selected gates reject missing emission, but broader correctness requires
preserving all kept references, aliases, secondary/unnamed entries and data-to-code
pointers. Cover short functions, mixed mapping transitions, table reach bounds,
shared/ambiguous islands, reverse layout and split/instrumentation interactions.
The conservative TBB/TBH model does not establish support for arbitrary ARM
tables or indirect transfers.

### R8. Interrupt, exclusive-monitor, PMU and reset ownership remain unproved — P1

The reservation preflight in `RewriteInstance.cpp:974` checks local decoded paths
and rejects unmodeled live exits. Quiet fixture execution does not validate
active IRQ/exception entry, exclusive-monitor disruption, concurrent reset or
snapshots, FIQ, SMP, or userspace. `pi4_sample_profile.py:79` explicitly records
that the runtime arms all cores and IRQ-masked code is invisible. IRQ totals and
training-core affinity do not attribute every sample to that workload/core.
Keep original #12 open for ownership, loss/saturation, completion and statistical
interpretation, as well as source/tool provenance.

### R9. Actual pass combinations and clean build provenance remain open — P1

Prove which passes changed code, including profile-driven reorder/split/inlining,
ICF address identity, tail duplication and repair across per-function ISA builders.
Successful no-op passes are not coverage. Preserve the dirty live trees while
building the exact overlay set in isolation; record source/build/tool identities
and compare both assertion modes. Debug/DWARF and unsupported dynamic/PIC forms
must have explicit support or rejection contracts.

## Stop and later resume

Stop at the verified oracle/wider-Pi milestone after publishing this review and
the fresh table. This supersedes the earlier instruction to finish all P0 work
before stopping. P0 item 6 and original #12 remain open. A later explicitly
requested resume starts with table item 6a and its end-to-end acceptance criteria;
do not weaken admission boundaries merely to obtain another passing image.
