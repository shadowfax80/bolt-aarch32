# Claude review of `0e616eb` (ATFE 0001–0045)

2026-10-04. Ownership and status live in [HANDOFF.md](../HANDOFF.md); this file
holds the findings. "Confirmed" means reproduced on the LK image; "code" means
read in source but not triggered on that input.

Raw `llvm-bolt` output for a mixed ARM/Thumb image is not safe today (R1). The
full-image pipeline hides it by restoring the original text afterwards.

## Findings

| ID | Area | Finding | Evidence | Fix |
|---|---|---|---|---|
| R1 | Relocations | Thumb `blx` to an ARM function, in code BOLT does not rewrite, is re-patched as `bl`. | Confirmed: 61 sites (e.g. `thread_yield` → `arch_spin_lock`). `createRelocation` maps `fixup_arm_thumb_blx` to `R_ARM_THM_CALL`; `encodeValueARM` always writes BL. | Choose BLX/BL from the target ISA; word-align the BLX base. |
| R2 | Relocations | ARM `JUMP24`/`PC24`/`PLT32`/`CALL` re-encoding hard-codes `0xea`/`0xeb`: conditions are dropped and ARM `blx` becomes `bl`. `fixup_arm_condbl` maps to `R_ARM_CALL` (MC uses `R_ARM_JUMP24`). | Code: `Relocation.cpp`, `ARMMCPlusBuilder::createRelocation`. | Keep bits 31:24 of the original word; correct the mapping; reject conditional cross-ISA cases. |
| R3 | Relocations | `thumb_br`/`thumb_bcc`/`t2_condbranch` map to `R_ARM_THM_JUMP24`; CBZ has no mapping. | Code: `createRelocation`. | Map to `THM_JUMP11`/`JUMP8`/`JUMP19`, or refuse cleanly. |
| R4 | CFG | Any conditional tail call (found as `it lt; blt.w f; b.w g`) crashes: `LLVM ERROR: invalid AArch32 CFG after branch post-processing`. | Confirmed: `platform_irq`, `platform_fiq`, `arm_gic_init_percpu`. | Model as a conditional tail call or reject with `BOLT-ERROR`. |
| R5 | Admission | A terminal `bl` to a noreturn callee is rejected as fallthrough. | Confirmed: ~80 LK functions (`lk_main`, `thread_exit`, `miniheap_free`). | Infer noreturn callees; keep rejecting real fallthrough (`bzero` → `memset`). |
| R6 | CFG | Predicated returns inside IT blocks are rejected. | Confirmed: ~45 LK functions (`memchr`, `strncmp`, `thread_yield`). | Split the IT group into a conditional branch to a return block. |
| R7 | LongJmp | `isCall` includes tail calls, so `adjustCallForTargetMode` turns a far tail-call `B` into `BL`/`BLX` and clobbers LR. | Code: `LongJmp.cpp` stub insertion. | Skip the call rewrite for tail calls. |
| R8 | LongJmp | Local-branch stubs use `movw/movt r12; bx r12` mid-function without a liveness check. | Code: `createShortJmp`. | Check r12 liveness or reject. |
| R9 | PatchEntries | Entry patches use the global ARM builder for Thumb functions. | Code: `PatchEntries.cpp`; did not fire on LK. | Use the per-ISA builder, or disable on ARM. |
| R10 | Builders | Jump-past-end `createNoop` and `setTrapOnEntry` use the global builder; ARM `createNoop` omits MOVr's `cc_out`; trap fill is an ARM NOP. | Code: `BinaryFunction.cpp`, `ARMMCPlusBuilder.cpp`. | Per-ISA builder; fix operands; `udf` per ISA. |
| R11 | Admission | Every rejection is fatal; the LK skip list needed 57 reruns. | Confirmed. | Skip-and-report mode; fatal stays default for certification. |
| R12 | Admission | `adr.w r2, #4` before `tbh [pc, …]` in `vsnprintf` is rejected as a PC read. | Confirmed. | Model ADR to an inline table as a table-label reference. |
| R13 | Scripts | `redirect-bolt-entries.py` refuses functions starting with a 16-bit instruction. | Confirmed: `bolt_bench_it_cond`, `bolt_bench_far_call`. | Relocate the displaced prefix into the stub. |
| R14 | Relocations | ARM cases were inserted between `riscv64` and `riscv32` in nine `Relocation.cpp` dispatchers, so RISC-V 64 uses the ARM helpers. | Code; hidden because RISC-V is not built here (53 tests unsupported). | Restore upstream order (0047). |
| R15 | Instrumentation | The 0038 cross-function exclusive guard rejects full LK because `arch_spin_trylock` (`ldrex; cmp; strexeq; dmb; bx lr`) can return with an open monitor when the lock is held. That is legal and harmless, but no workload can be instrumented in this image. | Confirmed: `FATAL BOLT-ERROR ... arch_spin_trylock at 0x80009b64: return with a live reservation`. | Accept an exit with a live reservation when no path in a caller pairs a later STREX with it, or model known try-lock primitives; keep rejecting real cross-function pairs. |

| R18 | Admission | ARM-state inline `ldr pc` jump tables rejected as PC reads. | Found by R17 in clang ARM-mode code (8 functions). | Fixed in 0057 (O2/Os `ldr pc` form); `-O0` load-then-jump form is R21. |
| R19 | Admission | `mov lr, pc; b X` call idiom rejected as a PC read. | Found by R17 (4 functions). | Fixed in 0055. |
| R20 | ICF | ICF aborts comparing A32 MOVW/MOVT specifier operands. | Found while testing R19. | Fixed in 0056. |

## LK rejection profile

Input `424606a8…`, full image: 138 of 417 functions rejected. About 80 are R5,
about 45 are R6, 7 are PC-writing exception vectors and `arm_secondary_setup`
(keep out), 3 are PC reads (`arm_reset` and `arm_secondary_entry` must stay;
`vsnprintf` is R12), and 3 are the R4 crash. Counts are ±2.

## Scope

Read in full: `ARMMCPlusBuilder.cpp`, ARM code in `Relocation.cpp`. Read at
call sites: `getMIBFor` users and remaining global-builder uses, external-
reference scanning, `PatchEntries`, LongJmp stubs, the veneer gate. Only
spot-checked: `RewriteInstance.cpp`, JITLink `aarch32`, the runtime and the
emitter's interworking code.
