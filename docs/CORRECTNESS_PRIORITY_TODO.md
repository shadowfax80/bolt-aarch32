# Correctness priority queue after the 0038 review

Updated 2026-10-03 from [the fresh review](CORRECTNESS_REVIEW_0038.md) and
[recorded evidence](results/correctness_0038_review_20261002.json).
Queue positions below are new priorities; the original twelve workstream IDs
remain stable in [CORRECTNESS_TODO.md](CORRECTNESS_TODO.md).

ATFE only. Item 1 now has a verified scoped fix in overlay 0039; the remaining
queue is not yet started in this resumed session. The user
reactivated #12 on 2026-10-02; all its remaining work is included below. Nothing
is paused in this correctness queue. Three original
items are complete in their bounded scope (#2/#8/#10); nine remain open.

## Status table

| Queue priority | Work item | Current status |
|---|---|---|
| 1 · P0 | Skipped interior-entry reservation bypass | Verified for decoded original function code; 0039 |
| 2 · P0 | Thumb instrumentation startup crash | Pending; next |
| 3 · P0 | ISA/profile/ABI admission | Pending |
| 4 · P0 | Fixed-load ELF/PIE boundary | Pending |
| 5 · P0 | Exact profile/artifact identity | Remaining work pending |
| 6 · P0 | Execution/result gate integrity | Remaining work pending |
| 7 · P1 | Relocation/literal matrix | Partial; remaining work pending |
| 8 · P1 | Control-flow/mutation invariants | Partial; remaining work pending |
| 9 · P1 | Interrupt/reentrancy boundaries | Partial; remaining work pending |
| 10 · P1 | Sampling/PMU ownership | Partial; remaining work pending |
| 11 · P1 | Entries/symbols/reference routes | Partial; remaining work pending |
| 12 · P1 | Tables/inline data | Partial; remaining work pending |
| 13 · P1 | Pass transformations/combinations | Partial; remaining work pending |
| 14 · P1 | Clean build/content provenance | Partial; remaining work pending |

Item 1: both assertion builds pass 171 cases (132 rejections, 39 admissions),
including ARM/Thumb/mixed pairs and direct/addend, pointer, alias and data-pointer
routes. All eight original review bypasses now reject before output. Fresh
supported Pi payloads match previously executed bytes; no new runtime reservation
outcome is claimed. See [0039 evidence](results/correctness_interior_reservations_20261003.json).
General ISA/entry/symbol discovery remains in items 3/11. Work stopped at this
milestone under the user's previous next-milestone instruction; nothing in the
queue is marked paused.

## P0: confirmed defects and unsafe admission

1. **Close skipped interior-entry reservation bypass — F1, #6/#9.**
   - [x] Remove the gate's dependence on complete entry metadata: analyze every
     decoded exclusive load, including acquisitions outside main-entry reachability,
     and reject stores without an analyzed local reservation. General entry
     discovery stays under item 11; unknown ISA admission stays under item 3.
   - [x] Add the eight reproduced admissions as negative regressions in both
     assertion builds; extend to ARM/Thumb/mixed modes, aliases and data pointers.
   - [x] Recheck the review's raw/redirected inputs: rejection occurs before any
     output/redirect can be published. Keep local-pair/retry-loop admissions,
     including unreachable closed pairs. Supported generated Pi bytes match
     executed payloads. This is a decoded-code admission proof, not a fresh
     hardware reservation-failure reproduction.

2. **Fix Thumb instrumentation startup lookup and release crash — F2, #9/#3.**
   - [ ] Normalize the entry lookup and preserve Thumb state in the trampoline.
   - [ ] Replace assertion-only/null-dereference handling with diagnostics.
   - [ ] Test valid ARM/Thumb entry, missing/zero/interior entry and finalization
     variants in both builds, including the reproduced SIGABRT/SIGSEGV fixture.
   - [ ] Execute the corrected Thumb startup/instrumented route on Pi and verify
     state, counters and return/loader behavior.

3. **Enforce the ISA/profile/ABI contract for generated instructions — F3/F5, #7/#6.**
   - [ ] Define the initial LE ARMv7-A/Thumb-2 contract separately for ordinary
     rewriting and privileged instrumentation.
   - [ ] Reject or separately support ARMv6, M-profile, missing/conflicting
     attributes, BE8/BE32 and other excluded features/ABI variants.
   - [ ] Validate generated MOVW/MOVT, branches, counter bodies and stubs against
     admitted features. Attribute-guided decoding alone is insufficient.
   - [ ] Add the ARMv6 feature violation and missing-attribute/BE8 admissions as
     explicit negative or supported-contract cases in both builds.

4. **Enforce fixed-load ELF admission or implement rebasing — F4, #7/#11/#6.**
   - [ ] Close static PIE's `IsStaticExecutable` exception for unsupported
     instrumentation; define ELF type, interpreter and dynamic-tag policy.
   - [ ] Reject ET_DYN/PIC where generated code/runtime uses unrelocated absolute
     pointers, or implement the required relocation model.
   - [ ] Test fixed-address and nonzero load bias, including counter/runtime
     pointers, entry routes and output dynamic relocations in both builds.
   - [ ] Distinguish genuine shared-object rejection from static-PIE admission in
     documentation and tests; do not treat them as one case.

5. **Bind counter profiles and every artifact to exact inputs — #12.**
   - [ ] Validate every named counter location/offset against the exact original
     ELF/function/map before fdata publication; string consistency alone is insufficient.
   - [ ] Bind dumps, counters, metadata, maps, profiles and tools to image and
     patch digests; reject stale/mismatched artifacts and ambiguous source identity.
   - [ ] Extend deliberate wrong-image/wrong-map/wrong-offset tests and verify
     atomic publication leaves existing profiles intact after late failures.

6. **Make every execution/result gate prove its claimed coverage — #12/#11.**
   - [ ] Require selected/emitted/redirected/executed coverage and independent
     results in every optimization gate, not only the scoped full-image gate.
   - [ ] Extend ARM/Thumb/mixed inputs, flags, memory and return-value checks over
     multiple seeds, faults and timeouts; add observed rewritten far-call coverage.
   - [ ] Validate legacy/manual section hooks: bounded scratch, whole instructions,
     PC-relative prologues, exact restoration sizes and hard failure propagation.
   - [ ] Record durable Pi manifests with revisions/options, tool/image/profile
     hashes, functions selected/emitted/executed, expected/observed outputs and logs.

## P1: required boundaries and wider correctness proof

7. **Complete the relocation and literal-load matrix — #1.**
   - [ ] Publish each relocation's recognition, addend extraction, MC emission,
     JITLink application, pending-write and kept-code behavior.
   - [ ] Resolve the core/JITLink declaration differences and justify skips;
     unsupported paths must diagnose rather than truncate or silently change bits.
   - [ ] Cover signed endpoints/overflow, alignment, PC bias, Thumb bits,
     BLX H=0/H=1, predicates, MOVW/MOVT addends, narrow/wide branches and far stubs.
   - [ ] Execute representative same/mixed-ISA call, literal and split paths on Pi.

8. **Finish control-flow and mutation invariants — #3/#4.**
   - [ ] Model predicated return exits/fallthrough, or reject every pass requiring
     the missing edge; the instrumentation-only gate is not general CFG support.
   - [ ] Audit indirect/tail/system/trap transfers and per-function ARM/Thumb
     builder selection across mutation, repair and emission.
   - [ ] Reject unsafe fallback before publishing partial transformations;
     verify debug/release behavior and live flags/LR/SP/results independently.

9. **Establish interrupt and reentrancy boundaries — #5/#6.**
   - [ ] Validate active IRQ/exception entry and monitor interactions, or require
     and enforce a narrower documented quiet-execution contract.
   - [ ] Extend full nested state checks to ARM/Thumb interworking and recursion,
     including register/flag state around interrupts and insertion sites.
   - [ ] Keep FIQ/SMP/userspace excluded unless separately supported. Runtime
     acknowledgement cannot prove privilege or other cores' inactivity.
   - [ ] Specify/reset/read quiescence; reject or validate concurrent reset/live
     snapshots and multi-entry/zero-edge exact-count models.

10. **Establish sampling/PMU ownership and statistical integrity — #12.**
    - [ ] Restrict or verify participating core/PMU ownership; the runtime currently
      arms all cores and IRQ totals do not prove per-PC core ownership.
    - [ ] Verify buffer identity, kept/taken counts, loss/saturation, workload
      completion and unbounded assembly exclusions for each profile scope.
    - [ ] Record IRQ-masked blind spots; PC samples must not be presented as exact
      edge counts. Cover deliberately wrong ownership/count/completion cases.

11. **Preserve entries, symbols and all reference routes — #9/#11.**
   - [ ] Cover aliases, secondary/unnamed entries, function/data pointers, missing
     mapping symbols, literals, code/data transitions and kept callees.
   - [ ] Harden redirects for short functions, overwritten interior targets,
     exact maps/input identity and ISA; verify indirect/original-entry execution.
   - [ ] Establish safe behavior for in-place/kept-code and section restoration
     separately from the relocated supported fixture path.

12. **Bound table and inline-data rewriting — #11/#1.**
   - [ ] Test TBB/TBH reach limits, malformed/ambiguous islands, shared cases,
     reverse layout and splitting/instrumentation interactions.
   - [ ] Support or reject ARM tables, alternate indirect forms and unresolved
     data-to-code references; skipped code must retain correct references.

13. **Verify actual pass transformations and combinations — #4/#11.**
    - [ ] Extend profile-driven reorder/split/peephole/inlining combinations with
      adversarial predicates, flags, stack, calls and return paths.
    - [ ] Audit ICF/address identity, tail duplication and remaining generic pass
      hooks; record which passes actually changed code.
    - [ ] Reject or validate GOT/TLS/PLT/PIC and debug/DWARF behavior; command
      success or a no-op pass is not semantic verification.

14. **Prove clean build provenance and content identity — #12.**
    - [ ] Replace filename-only stamps with base/patch/source content identity
      and prove clean full-build provenance. The fresh 38-patch source replay
      passes; it does not close the clean-build or binary-provenance requirement.
    - [ ] Reproduce the assessed overlays in an isolated clean build, compare
      source/tool identities and preserve the live dirty ATFE/LK trees.
    - [ ] Preserve current sync protection for `.git/` and `out/`, audit file
      modes and export coverage, and bind the exact tested tools to manifests.

Keep #2 EHABI rejection, #8 data-width handling and #10 deterministic mixed stubs
green throughout. For each task, require a small reproducer, an enforced support
or rejection boundary, assertions-on/off checks and scoped hardware execution
when claiming runtime behavior. Do not mark a full original item complete from
one additional fixture.
