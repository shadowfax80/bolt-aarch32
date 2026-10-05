# Recovered Astra review, reconciled by Sol through 0061

Recovered 2026-10-04. Astra reviewed `b6b68dc` / overlays 0001–0057.
Sol synchronized to `89dd17f` / 0001–0061 and checked the surviving findings
against the current source and intervening overlays. This is a targeted review,
not an exhaustive backend certification. No backend changes, rebuilds or Pi
access were performed during reconciliation.

## Findings and shared work

| Priority | Shared item | Finding | Evidence / consequence |
|---|---|---|---|
| P1 | R22 (new; related to R18) | Privileged LDM can overwrite an inline-table base without rejection | `ldmia r4,{r3,r5}^` between `add r3,pc,#8` and `ldr pc,[r3,r2,lsl#2]` is accepted and produces output. The ordinary LDM control rejects; the non-clobbering control succeeds. The model assumes an unchanged base although r3 is unbanked and loaded by the privileged instruction. |
| P1 | R11 (reopened Partial) | A rejected Thumb IT block contaminates the next function's decoder state | Truncated ITT and ITE are rejected, but the following independent `bx lr` is also falsely rejected for fallthrough. The same function is admitted in the control image. Confirmed with both installed assertion-mode binaries. |
| P1 | R23 (new; related to R19) | Noreturn thunk traversal bypasses the recursion guard | An A32 MOVW/MOVT/BX thunk cycle A → B → A reached by a terminal call times out after eight seconds. A self-cycle rejects and an acyclic thunk to a non-returning function succeeds. |
| P2 | R24 (new; related to R18) | Encoded A32 modified immediates are used as byte displacements | A valid `add r3,pc,#256` inline-table fixture rejects as a PC read, while the corresponding #8 fixture succeeds. This is a conservative rejection; no emitted miscompilation was demonstrated. |

R18 and R19 retain their completed positive milestones; the new IDs track
additional edge cases without rewriting their historical evidence. R11's
diagnostic classification contract needs correction, so its current status is
Partial and unclaimed. R22 should be fixed before relying on the expanded
inline-table admission. These findings do not invalidate unrelated scoped Pi
receipts or demonstrate a hardware failure in the published LK fixtures.

## Source and closure criteria

**R22:** `bolt/lib/Core/BinaryFunction.cpp:1937–1960` uses
`hasDefOfPhysReg` to prove that the table base survives. Ordinary LDM has
`variadicOpsAreDefs`; the privileged `sysLDM` definition in
`llvm/lib/Target/ARM/ARMInstrInfo.td` lacks that property. The accepted
privileged register-list load defeats this check. Reject or correctly model
all register-list definitions, including user-bank loads and writeback.
Add positive and must-reject cases in both modes; preserve the ordinary-LDM
control. The review demonstrated unsound admission, not an executed wrong result.

**R11:** shared Thumb disassemblers retain mutable IT state across independent
decodes. Overlay 0054 clears symbolizers and function containers on local
failure but does not isolate that state. See `BinaryFunction.cpp:175–179,
1564–1569,1927–1928` and `ARMDisassembler.cpp:122,626–655`. Reset or recreate
decoders at independent stream boundaries, covering symbolic and plain decoder
users. Add truncated ITT/ITE followed by clean-function regressions and verify
that function order does not change admission. Overlay 0059 adds another plain
decoder user for its executable-gap scan; include that use in the audit, without
assuming this review proved an instrumentation bypass.

**R23:** `BinaryFunction.cpp:1478–1487` follows recognized absolute thunks
before entering `ARMNoReturnCache`. `F != this` catches only a direct self-cycle.
Put thunk traversal inside the visited/in-progress mechanism and test multi-node
cycles and acyclic A32/T32 chains in both modes. The observed failure is a host
analysis timeout; stack exhaustion was not observed.

**R24:** `ARMMCPlusBuilder.cpp:350–351` reads `ADDri` / `SUBri` operand 2
directly. LLVM's `mod_imm` operand stores an imm8 plus rotation, as documented in
`ARMInstrInfo.td:979–982` and decoded in `ARMInstPrinter.cpp:1431–1446`.
Decode the immediate before computing the table address. Cover ADD and SUB,
rotated values, malformed or mismatched table addresses, and both assertion modes.

Each source fix needs a claimed item, the live-tree lock, its own overlay and
regressions, full overlay replay, refreshed coverage, and execution evidence
appropriate to its changed admission scope under [HANDOFF.md](../HANDOFF.md).

## Recovered evidence and limits

[Evidence bundle](../results/astra_review_20261004/evidence.json) contains the
original manifests, input hashes, commands, assembly, linker scripts, logs and
diagnostic JSON, plus current source hashes/excerpts. Reproducers are
[IT probe](../results/astra_review_20261004/probe_it.py) and
[other probes](../results/astra_review_20261004/probe_extra.py); they create fresh
WSL output directories and need the toolchain paths adjusted for the intended
build. They are diagnostic reproducers, not certification gates.

Original WSL directories remain intact:

- `out/astra-review-it-um54d2cy`: six IT control/rejection cases.
- `out/astra-review-extra-29tt7x0z`: eight thunk/table cases, with corrected
  padding for the large-immediate fixture.
- `out/astra-review-extra-v8wgvnim`: earlier run with incorrect padding in
  the two immediate fixtures; those immediate results are excluded.

The original ON BOLT hash is
`40a1eca3a547f19eed1ec18873a3e301778f1ce965a851eb7de4bda0c777a186`
(0057). The IT probe's older OFF binary is
`765678198fe0cdf4fe2523420a23d4a73efc197a8f054386d2285dfdc5c3b152`
(0054). The extra probes ran ON only. Neither proves both-mode behavior through
0061. Later overlays leave the cited defects in current source; Sol did not
rerun the probes on the current binaries. The initial handoff-only draft is
preserved locally at `out/sync-preserved-astra-review-20261004-173128/` and was
reconciled selectively rather than reapplied over Claude's progress.

## What later work superseded

| Older review caveat | State at 89dd17f |
|---|---|
| A55/v8-A input rejected (T1) | Completed by 0058 and LK patch 0011; approved A55-built fixture and scoped Pi certification. |
| Rewritten SMP execution unverified (T2) | Completed for the declared four-core Pi workloads, with per-core execution evidence and receipts. |
| SMP counters unsupported | T2b completed by 0060; scoped counter model verified on the Pi. |
| Local stubs clobber live r12 (R8) | Completed by 0061's conservative liveness guard. |
| Try-lock instrumentation blocked (R15) | Completed by 0059 for the declared scope. |
| Prefix redirects and certification-route gaps (R13, 6a–6d) | Declared milestones completed. G3 is inapplicable to the user's diagnostic QEMU route. |
| Secure-SVC bring-up approved and next | Latest user decision defers T3's SD-card install and Secure re-runs; prepared armstub remains uninstalled. *(Corrected 2026-10-05: the target runs Non-secure SVC, the same state as the Pi; Secure-SVC parity (T3) was closed as not needed.)* |

Do not reintroduce these completed items as open based on the old review.
The current P0 milestones remain Done in the handoff; that status is bounded
to their declared configurations and routes.

## Overall implementation assessment

The backend has substantial support for fixed-address little-endian ELF32
A32/T32 images within its explicit ISA/ABI and transformation boundaries.
The current repo includes ARMv8-A AArch32 admission, A55-built fixtures,
four-core rewritten workload evidence and an SMP counter path. Pi A72 evidence
does not cover A55-only instructions, timing or the target platform's runtime.
Secure execution remains unverified because T3 is deferred. *(Corrected 2026-10-05: the target runs Non-secure SVC, the same state as the Pi; Secure-SVC parity (T3) was closed as not needed.)*

Published v7 emission coverage remains **400/417 functions**, **124282/126834
function code bytes (98.0%)**. This is emission coverage, not execution coverage.
Do not interchange admitted-function counts, emitted bodies and sampled redirects.
The 146-case edge certificate and the separate 67-redirect, 146 × 2 run have
different scopes. Broader CFG/relocation/entry/pass, active-IRQ, PMU/loss and
clean compiler provenance matrices remain open. Item 14 also retains the
ISA-metadata problem in candidate no-FPU scans; the earlier fail-open checker
defect was already fixed in `000a8a4`.

The targeted Astra inspection found no further concrete defect in 0046 branch
repair, 0048 entry patches, 0049 far tail calls, 0051 conditional-tail conversion,
0053 predicate-preserving calls or 0056 ICF expressions. This statement records
the bounded inspection and grants no general pass-combination approval.
