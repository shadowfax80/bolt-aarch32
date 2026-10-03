# AArch32 ISA and ABI admission contract

Overlay 0041 establishes the initial supported metadata boundary. Ordinary
rewriting and instrumentation both require little-endian ELF32, EABI5, ELF OSABI
NONE/version zero, explicit ARMv7-A and permission for ARM plus Thumb-2 (including
the derived Thumb permission). This deliberately excludes ARMv6, M/R profiles,
newer architectures, BE8/BE32, legacy flags and missing attributes.

Exactly one correctly typed `.ARM.attributes` section and one AEABI file scope
are required. Malformed lengths/values, duplicate tags/scopes, unknown AEABI tags,
section/symbol overrides and conflicting permissions reject before output.
Bounded non-AEABI vendor records may coexist without defining compatibility.

Base AAPCS VFP argument convention is required. Hard-float, WMMX and custom PCS
are unsupported. VFP argument value 3 (compatible with both conventions) is a
conservative exclusion, not an assertion that the ABI forbids it. Optional input
FP through VFPv4/D16 and NEON through v2 may be declared with base arguments;
this does not certify every FP/SIMD transformation. Unsupported MVE, T2EE,
explicit DSP, PAC/BTI and alternate/default-free contracts reject. MP aliases
must agree; optional divide and TrustZone/virtualization permissions are carried
into feature selection. See the implementation and matrix for exact tag limits.

Instrumentation additionally requires the existing
`privileged-single-core-no-fiq` acknowledgement and excludes call/indirect-call
profiling and process options. Its supplied runtime must be ARM ELF ET_REL,
meet the same metadata/ABI boundary, declare no FP/SIMD/half-precision extension,
and require no optional divide/MP/TrustZone/virtualization feature absent from
the input. Every archive object is checked; malformed/non-object members reject.
ARM hugify is unsupported and now diagnoses explicitly.

The default bare-metal runtime build now uses generic ARMv7-A and integer-only
soft-float code. Named CPU overrides remain possible but their declared runtime
requirements are checked against the input. Rebuild older Cortex-A15 archives;
they may declare optional features a minimal input does not permit.

Both builds pass 358 cases (32 admissions, 326 rejections). Minimum-profile MC
checks cover MOVW/MOVT/BX, ARM/Thumb branches and CBZ forms, reassembly of all 24
actual baseline runtime instructions, and the independent complete counter-body
byte oracle. Focused suites pass 50/49 with one expected release skip; CoreTests
pass 58 with 31 expected skips. Fresh Pi startup and 372-case IT/nested/reset
matrices pass in both builds, including the deliberate reset fault.

## Remaining limits

Attributes cannot prove the truth of an instruction stream or the actual CPU,
privilege, quiescence or core ownership. These checks establish a conservative
admission boundary and selected generated-code verification, not general ELF or
whole-firmware correctness. Static PIE is still admitted; fixed-load policy is
next in queue item 4. Active interrupt/reentrancy, arbitrary FP/SIMD/pass
combinations, dynamic finalization and clean-build provenance remain open.

A separate automatic ARMv7 linker-thunk probe removes zero veneers in both
builds. The retained MOVW/MOVT thunk still targets old `far_away` at `0x2110020`,
while its emitted copy is at `0x4500030`. The tested direct caller uses a correct
new stub to the emitted copy, so this is not a demonstrated runtime failure.
Other routes into the retained thunk remain unverified under queue items 7/11.
The legacy literal-veneer regression now uses an explicit legacy veneer with
valid v7-A attributes; it does not certify automatic v7 thunk handling.

Evidence: [0041 results](results/correctness_isa_contract_20261003.json) and
[current queue](CORRECTNESS_PRIORITY_TODO.md). All 41 overlays replay exactly to
live source; this is source identity, not clean full-build certification.

ABI references: [ARM build attributes](https://github.com/ARM-software/abi-aa/blob/main/addenda32/addenda32.rst)
and [ELF for the Arm architecture](https://github.com/ARM-software/abi-aa/blob/main/aaelf32/aaelf32.rst).
