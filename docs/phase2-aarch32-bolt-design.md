# Phase 2: AArch32 BOLT design (after Phase 1)

Upstream BOLT has **no ARM32/Thumb backend** today. This document will be expanded once the AArch64 LK PoC succeeds.

## Constraints to address

| Topic | Notes |
|-------|-------|
| ELF32 + Rel | Addends often in-place, not Rela |
| Thumb bit (LSB=1) | State must be tracked per symbol/edge |
| ARM/Thumb interworking | BL, BLX, BX, LDR PC |
| IT blocks | Atomic units; no split or mid-block instrumentation |
| Branch range | Veneers/stubs for ±16/32 MB |
| Mapping symbols | `$a`, `$t`, `$d` for CFG recovery |
| Literal pools | Constant islands in `.text` |
| Bare-metal profile | Reuse Phase 1 in-RAM counter dump |

## Suggested implementation order

1. ELF32 reader + disassemble-only (ARM mode)
2. `ARM MCPlusBuilder` + CFG for ARM-only functions
3. Rewrite with veneers
4. Thumb-2 without IT
5. IT blocks as atomic units
6. Interworking edges
7. LK ARM32 QEMU target
