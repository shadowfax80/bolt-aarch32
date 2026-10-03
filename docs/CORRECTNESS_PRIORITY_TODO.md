# Correctness priority queue after the 0038 review

Updated 2026-10-03 from [the fresh review](CORRECTNESS_REVIEW_0038.md) and
[recorded evidence](results/correctness_0038_review_20261002.json).
Queue positions below are new priorities; the original twelve workstream IDs
remain stable in [CORRECTNESS_TODO.md](CORRECTNESS_TODO.md).

ATFE only. Items 1-5 have verified scoped fixes in overlays 0039-0043.
Item 6 is active; its gate-hardening and bounded A32 far-call stages are verified. The user
reactivated #12 on 2026-10-02; all its remaining work is included below. Nothing
is paused in this correctness queue. Three original
items are complete in their bounded scope (#2/#8/#10); nine remain open.

## Status table

| Queue priority | Work item | Current status |
|---|---|---|
| 1 · P0 | Skipped interior-entry reservation bypass | Verified for decoded original function code; 0039 |
| 2 · P0 | Thumb instrumentation startup crash | Verified for static entry and dummy-fini scope; 0040 + Pi |
| 3 · P0 | ISA/profile/ABI admission | Verified conservative contract; 0041 + Pi |
| 4 · P0 | Fixed-load ELF/PIE boundary | Verified fixed-load admission; 0042 |
| 5 · P0 | Exact profile/artifact identity | Verified sealed pipeline scope; 0043; #12 active |
| 6 · P0 | Execution/result gate integrity | Active; gate hardening + A32 QEMU far-call stages verified; wider proof pending |
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

Item 2: both builds pass 40 startup/static-finalization cases; focused suites
pass 49/48 (one expected skip off), and CoreTests pass 58/31 skips. Fresh Pi
baseline, normal and reverse variants pass per build, including actual ARM
runtime entry to emitted Thumb entry and an exact counter of one. Only the boot
entry-pointer and counter metadata words change after BOLT; emitted code and ELF
entry are retained. See [0040 evidence](results/correctness_thumb_startup_20261003.json).
Static finalization remains a dummy return: DT_FINI variants are not invoked.
Dynamic hooks remain unsupported; item 4 now rejects PIE admission below; general entry/symbol
scope remains in item 11; item 3 is now scoped verified below. Work stops at
this verified milestone under the
user's previous instruction; nothing in the queue is marked paused.

Item 3: scoped ISA/ABI admission verified in 0041. Both builds pass 358 cases
(32 admissions, 326 rejections), focused suites 50/49 and CoreTests 58/31 skips.
Fresh Pi startup and 372-case IT/nested/reset checks pass per build; deliberate
reset faults are detected. See [contract](AARCH32_ISA_ABI_CONTRACT.md) and
[evidence](results/correctness_isa_contract_20261003.json). Static PIE admission from that checkpoint is superseded by 0042 below. Stop at this milestone; no remaining item is paused.

Item 4: scoped fixed-load boundary verified in 0042. Both builds pass 192 cases,
focused suites 51/50 and CoreTests 58/31 skips. Original static PIE now rejects
before output; prior PIE/DT_FINI admissions are superseded. Supported Pi bytes
match the executed 0041 fixtures. See [contract](AARCH32_FIXED_LOAD_CONTRACT.md)
and [evidence](results/correctness_fixed_load_20261003.json). Next is item 5;
all remaining #12 work stays active. Work stops at this verified milestone.

Item 5: scoped sealed-pipeline identity verified in 0043. Both builds pass 300
host cases each; 65 Python tests and four wrapper rejection checks pass.
Captures are synthetic; no fresh hardware execution is claimed. Unsealed
legacy captures are excluded; crash/power-loss atomicity and clean build
provenance are not claimed. See [contract](AARCH32_PROFILE_IDENTITY.md) and
[evidence](results/correctness_profile_identity_20261003.json). Next is item 6;
all remaining #12 work stays active. Work stops at this verified milestone.

Item 6: first gate-hardening stage verified. All five reproduced admissions now
reject; 80 Python tests and 7 valid/80 malformed transport cases pass. Fresh Pi
checks pass 420 positive cases and two expected faults per build. Whole-LK
rewriting still rejects arm_reset; wider independent execution coverage and
Pi/Thumb/mixed far-call witnesses remain open. The second item 6 stage verifies
A32 QEMU far-call execution in both modes/layouts: 20 transformed inputs, ten
baseline inputs, 28 rejected faults and 86 Python tests. See [far-call scope](AARCH32_FAR_EXECUTION.md)
and [far-call evidence](results/correctness_far_execution_20261003.json). See [scope](AARCH32_EXECUTION_GATES.md)
and [evidence](results/correctness_execution_integrity_20261003.json). Item 6
and original #12 remain active; stop at this verified stage.

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
   - [x] Normalize ELF ARM entry lookup and preserve the Thumb target bit.
   - [x] Diagnose missing entry and mismatched ISA bit instead of asserting or
     dereferencing null; resolved ELF finalization lookup also returns errors.
   - [x] Both builds pass valid moved/skipped ARM/Thumb entry and zero/missing/
     interior/ISA-mismatch cases. The original SIGABRT/SIGSEGV input succeeds.
     Static DT_FINI valid/zero/missing/interior/ISA-mismatch variants retain the
     runtime's dummy return; dynamic user-finalization hooks are not certified.
   - [x] Fresh Pi checks execute actual runtime/trampoline/rewritten Thumb entry,
     bounded odd return link, NZCV/R4/SP, exact one counter and watchdog return.
     General dynamic-hook/PIE policy remains in item 4.

3. **Enforce the ISA/profile/ABI contract for generated instructions - F3/F5, #7/#6.**
   - [x] Define/enforce the initial LE ARMv7-A/Thumb-2, EABI5/base-AAPCS contract;
     instrumented inputs additionally require the existing quiet privilege contract.
   - [x] Reject excluded architectures/profiles, malformed/missing/conflicting
     attributes, BE8/BE32 and ABI variants. Validate supplied runtime objects and
     archive members; reject FP/SIMD runtime or optional features exceeding input.
   - [x] Check generated veneer/branch forms, complete counter-body bytes and all
     baseline runtime instructions against minimum ARMv7-A. Rebuild the default
     runtime for generic ARMv7-A; fresh Pi startup and IT/nested/reset pass both modes.
   - [x] Both builds pass 358 admission cases, including original ARMv6/missing-
     attributes/BE8 findings. Conservative exclusions and limits are published in
     [the contract](AARCH32_ISA_ABI_CONTRACT.md); broader code/FP/pass proof stays open.

4. **Enforce fixed-load ELF admission or implement rebasing - F4, #7/#11/#6.**
   - [x] Require fixed-address ET_EXEC before transformation in both ordinary and
     instrumented modes; do not use static-PIE's IsStaticExecutable exception.
   - [x] Reject PIE/shared/relocatable inputs, INTERP/DYNAMIC/TLS and unsupported
     dynamic tags/sections, loaded relocation tables and GOT/PLT machinery.
   - [x] Validate LOAD/section extents and file mappings; reject nonempty loaded
     sections at zero before the reproduced assertion. Both builds pass 192 cases.
   - [x] Check runtime/entry/counter pointers at three fixed VMAs, demonstrate that
     simulated nonzero bias is unsupported, and preserve existing artifacts on
     rejection. Fresh supported Pi bytes match executed 0041 payloads.
   - [x] Publish [the enforced contract](AARCH32_FIXED_LOAD_CONTRACT.md). No rebasing
     or dynamic finalization support is claimed; broader code/reference proof stays open.

5. **Bind counter profiles and every artifact to exact inputs — #12.**
   - [x] Validate every named counter location/offset against the exact original
     ELF/function/map before fdata publication; string consistency alone is insufficient.
   - [x] Bind dumps, counters, metadata, maps, profiles and tools to image and
     patch digests; reject stale/mismatched artifacts and ambiguous source identity.
   - [x] Extend deliberate wrong-image/wrong-map/wrong-offset tests and verify
     staged publication and caught-error rollback leave existing profiles intact after late failures.

6. **Make every execution/result gate prove its claimed coverage — #12/#11.**
   - [x] Close the reproduced repetition/dump admissions; require every selected
     redirect, stable upload/manifest/loader identities and cleanup failure
     propagation. Reject unsafe ARM/Thumb entry-bump hooks; enforce exact
     section restoration. Publish the bounded host/Pi stage and its limits.
   - [x] Replace the legacy P5 exit-only/optional-QEMU gate with bounded A32
     result/memory/NZCV/SP checks, exact veneer/callee visit counts, executable
     faults and durable tool/artifact/route receipts in both modes/layouts.
     Pi/Thumb/mixed routes and automatic v7 thunk scope remain open.
   - [ ] Require selected/emitted/redirected/executed coverage and independent
     results in every optimization gate, not only the scoped full-image gate.
   - [ ] Extend ARM/Thumb/mixed inputs, flags, memory and return-value checks over
     multiple seeds, faults and timeouts; extend the verified A32 QEMU far-call
     route to Thumb/mixed routes and Pi hardware.
   - [ ] Validate legacy/manual section hooks: bounded scratch, whole instructions,
     PC-relative prologues, exact restoration sizes and hard failure propagation.
   - [ ] Record durable Pi manifests with revisions/options, tool/image/profile
     hashes, functions selected/emitted/executed, expected/observed outputs and logs.

## P1: required boundaries and wider correctness proof

7. **Complete the relocation and literal-load matrix — #1.**
   - [ ] Resolve automatic v7 thunk recognition and retained-target routes:
     the reviewed retained MOVW/MOVT thunk names the old target, while the tested
     caller uses a correct new stub. This is an open route caveat; no tested
     runtime failure was demonstrated (also item 11).
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
