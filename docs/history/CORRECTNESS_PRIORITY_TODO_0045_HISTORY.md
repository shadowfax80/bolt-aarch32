# 0045 certification closure criteria and queue

> Historical material only. Current status, ownership and work order are in
> [HANDOFF.md](../HANDOFF.md). Old continuation/stop statements do not authorize work.

## Historical 0045 certification closure criteria and evidence

The material below preserves the original closure criteria and milestone
references. Its status, resume-order, oracle-availability and stop statements
are historical snapshots, superseded by the current handoff and tables above.
The earlier R1–R9 labels refer to the Codex 0045 review, not Claude's R1–R17 IDs.

### Archived review through 0045

Updated 2026-10-04 after the [deep review](../reviews/CORRECTNESS_REVIEW_0045.md).
ATFE only. This is the fresh prioritized list for later work. Original twelve
workstream IDs remain stable in [CORRECTNESS_TODO.md](../HANDOFF.md#claims-consolidated-todo).
Original #12 is included throughout; it is **open**, not excluded or paused.

**Stop at the next verified milestone and publish this list**, as requested.
That instruction supersedes the earlier requirement to finish all P0 before
stopping. Consolidated P0 item 6 remains open. “Verified scoped” below means the
stated contract, not general backend correctness. See the
[milestone contract](../verification/AARCH32_ORACLE_MILESTONE.md) for final validation evidence.

## Prioritized work-item table

| Order | Priority | Work item / original IDs | Status at stop | Remaining work and closure criteria |
|---|---|---|---|---|
| 1 | P0 | Skipped interior-entry reservation bypass — #6/#9 | Verified scoped, 0039 | Decoded acquisitions and unpaired stores reject unsafe cross-function routes; retain both-mode regressions. General entry discovery is item 11. |
| 2 | P0 | Thumb instrumentation startup — #3/#9 | Verified scoped, 0040 | Static startup/runtime-to-Thumb execution verified; dynamic hooks and real finalization remain excluded. Retain startup/counter tests. |
| 3 | P0 | ISA/profile/ABI admission — #6/#7 | Verified scoped, 0041 | LE v7-A/Thumb-2, EABI5/base-AAPCS and runtime feature admission enforced. Broader ISA/ABI features require implementation or rejection and both-mode tests. |
| 4 | P0 | Fixed-load ELF boundary — #6/#7/#11 | Verified scoped, 0042 | Fixed ET_EXEC enforced; PIE/dynamic/TLS/GOT/PLT excluded. Preserve mapping/extent/zero-address and no-output rejection controls. |
| 5 | P0 | Exact profile/artifact identity — #12 | Verified sealed scope, 0043; #12 open | Sealed input/map/tool/profile identity verified. Actual end-to-end capture and clean compiler provenance remain in 6a/10/14. |
| 6a | P0 | Every optimization gate proves execution — #11/#12; review R1 | **Open; next task** | Validate complete sealed profile → optimize → exact-map redirect → boot pipeline in both modes. Audit identity/P4/workload/milestone/Pi/measurement wrappers and diagnostic modes; disabled boot, omitted functions, stale artifacts and late failures must never produce a certificate. |
| 6b | P0 | Independent output/state oracles — #11/#12; R2 | Partial; one exact QEMU contract verified | Eighteen independent sinks and four integer ARM entries verified. Add reviewed contracts and selected execution for the next declared supported configuration/Thumb/Pi scope, or enforce exclusion. No approved whole-LK Pi contract exists. Shared-wrong baseline/candidate, flags, memory, return and timeout controls must reject. |
| 6c | P0 | Legacy/manual hook admission — #9/#11/#12; R3 | Partial; whole Thumb prefix guarded; manual counter hooks rejected | Exercise real wrapper routes for sections/maps/legacy no-map redirects, short and interior targets, PC-relative prologues, restoration sizes, scratch limits, existing-artifact preservation and hard failure propagation. Support only with full semantics; otherwise reject before publication. |
| 6d | P0 | Durable coverage receipts — #12; R4 | Partial; fresh bounded QEMU/Pi receipts verified | Extend source/tool/profile/options identities, selected/emitted/redirected/executed sets, independent expected/observed results and logs to every certification route. Test complete receipt CLI construction and late publication failures. Bounded fixture receipts do not close #12. |
| 7 | P1 | Relocation/literal/veneer matrix — #1; R6 | Partial | Document extraction → MC → JITLink → pending/kept writes for each admitted relocation. Execute endpoints/addends/alignment/BLX/Thumb/predicates/split-cold routes; validate veneer opcode/name/size controls and automatic retained v7 thunk targets. Original NEON memcpy/ADR remains excluded. |
| 8 | P1 | CFG and mutation invariants — #3/#4; R5 | Partial; predicated-return gap remains | Model taken return + fallthrough, or reject every affected pass/input. Audit indirect/tail/trap/system transfers, per-function ISA builders and failure-before-publication; verify live LR/SP/NZCV/results in both modes. |
| 9 | P1 | Interrupt/reentrancy/reset boundaries — #5/#6; R8 | Partial; quiet fixtures only | Enforce quiet privilege/core contract or validate active IRQ/exception and monitor interactions. Cover nested interworking/recursion, concurrent clear/read and exact counts; FIQ/SMP/userspace remain excluded without proof. |
| 10 | P1 | Sampling/PMU ownership — #12; R8 | Open; parser/association hardened | Runtime arms all cores. Establish sample/core/PMU ownership, loss/saturation, workload completion and exclusions; preserve IRQ-masked blind spots and distinguish samples from exact edge counts. Wrong ownership/count/completion must fail. |
| 11 | P1 | Entries/symbols/reference routes — #9/#11; R7 | Partial; selected main-entry scope verified | Preserve aliases, secondary/unnamed entries, pointers, mapping transitions, kept callees and in-place references. Validate short/overwritten-interior redirects and exact input/map/ISA identity with actual indirect/original-entry execution. |
| 12 | P1 | Tables and inline data — #1/#11; R7 | Partial | Bound TBB/TBH reach, ambiguous/shared islands and reverse/split/instrumentation interactions. Support or reject ARM tables and unresolved data-to-code routes; ignored code must retain correct references. |
| 13 | P1 | Actual pass combinations — #4/#11; R9 | Partial | Prove that profile-driven reorder/split/peephole/inlining changed code safely; audit ICF/address identity, tail duplication, generic hooks and debug/DWARF. Record each real transformation; no-op success is not coverage. |
| 14 | P1 | Clean build/content provenance — #12; R9 | Partial; exact 45-overlay source replay only | Isolate a clean full build of assessed overlays, bind exact source/config/tools, compare both modes, audit export/modes and preserve live dirty ATFE/LK. Source replay and binary version banners are insufficient. |

## Milestone and caveats

The independent QEMU oracle and compatible BL/LR Pi witnesses improve item 6.
The wider Pi matrix uses nine edge seeds per ISA pair, including signed overflow
and wraparound, independent NZCV checks, and result/flag/retained-callee/hang
controls. These proofs remain bounded; consult the milestone evidence for exact
successful run counts and all failed diagnostics.

Whole-LK rewriting, original NEON memcpy, active interrupts/SMP, automatic v7
retained-thunk routes, arbitrary entries and clean compiler provenance are not
certified. Conservative rejection is retained where implemented. A source risk
or missing evidence is not presented as a freshly reproduced backend failure.

Only original #2 (EHABI rejection), #8 (data widths) and #10 (deterministic mixed
stubs) remain complete within their original bounded scope; nine original
workstreams remain open. Keep their tests green. Resume later with **6a**; do not
close #12 from one fixture or advance to P1 while claiming P0 is complete.

The [previous queue and checkpoints](CORRECTNESS_PRIORITY_TODO_0038_HISTORY.md)
are preserved as history; their earlier “continue”/“stop all P0” instructions and
pending-oracle/MOV-PC statements are superseded by this table and milestone.
