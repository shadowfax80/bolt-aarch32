# Deep edge-case review of the AArch32 backend (Claude, 2026-10-05, overlays 0001–0069)

Scope: the ATFE AArch32 BOLT backend after group C (R22, R11, R23, R24, R12,
R21). The review looked for shapes the per-item lit tests do not combine:
re-pointed table bases, Thumb state in data, interworking under layout
changes, IT predication, exclusives, ICF on table functions, and far layouts.
Two P0 defects were found and fixed (R25, R26). The remaining findings are
recorded as limitations in [KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md#current-atfe-backend-limitations-re-baselined-2026-10-05).

## Method

`scripts/review/edge_probe.py` is a differential harness: each case is a small
program (A32 `_start` driver calling `t(i)` for a range of inputs, hashing the
results, writing the hash with `svc`). It runs the original and BOLT outputs
under qemu-arm user mode and compares the outputs, for four option sets:

| Option set | BOLT options (all with `-lite=0`) |
|---|---|
| default | none |
| reverse | `--reorder-blocks=reverse` |
| icf | `-icf=all --reorder-functions=random` |
| far | `--pad-funcs-before=t:0x1100000` (pushes code beyond branch range so veneers/stubs are used) |

Verdicts: OK (same output), REJECTED (BOLT refused with a fatal admission
error, the safe outcome), WRONG (different output), BOLT-CRASH/HANG,
RUN-HANG. qemu-user is a diagnostic oracle only; hardware claims below come
from the Pi.

Usage: `python3 scripts/review/edge_probe.py <toolchain bin> <out dir> [case substring]`.
Final run: `docs/results/edge_probe_r26_20261005.json`.

## Results

First run (0067 toolchain): 74 OK, 6 WRONG, 4 REJECTED, plus two cases added
during diagnosis. Final run (0069): **80 OK, 12 REJECTED, 0 WRONG** over 23
cases × 4 option sets.

| Case | Shape | 0067 | 0069 |
|---|---|---|---|
| t32_tbb_8way | Thumb TBB, 8 targets | OK | OK |
| t32_tbh_adr_base | `adr.w r2` + TBH, a case reads r2 as data | WRONG (reverse) | REJECTED (R26) |
| a32_ldr_pc_table | `add r3, pc` + `ldr pc, [r3, …]` | OK | OK |
| a32_load_jump_O0 | `-O0` load-then-jump (R21) | OK | OK |
| a32_table_base_read_in_case | A32 table, a case reads r3 | WRONG (reverse) | REJECTED (R26) |
| t32_it_pred_return_call | `itt lo; poplo {…, pc}`, `it eq; bleq` | OK | OK |
| t32_it_cond_tail_call | `it hi; bhi.w helper` | OK | OK |
| a32_cond_return_call | conditional return and call | OK | OK |
| interwork_blx_both_ways | ARM↔Thumb `blx` | OK | OK |
| interwork_tail_bx_reg | tail `bx rN` into the other ISA | OK | OK |
| thumb_literal_pool / arm_literal_pool_mid_function | literal pools | OK | OK |
| fnptr_table_in_data | `.data` table of ARM and Thumb function pointers | WRONG (all) | OK (R25) |
| movw_movt_thumb_fnptr / literal_pool_thumb_fnptr | Thumb pointer formed in code | OK | OK |
| data_ptr_thumb_interior_entry | `.data` pointer to a Thumb interior entry | WRONG (reverse/icf/far) | OK (R25) |
| a32_mov_lr_pc_call | `mov lr, pc; b f` | OK | OK |
| noreturn_call_at_end | Thumb `bl die` last, `die` = `svc` exit + loop | REJECTED | REJECTED (limitation N1) |
| t32_cbz_cbnz | CBZ/CBNZ | OK | OK |
| ldrex_strex_local_loop | exclusive loop | OK | OK |
| recursion_thumb | Thumb recursion | OK | OK |
| icf_twin_tables | two identical A32 table functions under ICF | OK | OK |
| thumb_conditional_tail_other_mode | conditional tail call into ARM code | OK | OK |

## Defects found and fixed

### R25 (P0) — Thumb code pointers in data lost the Thumb bit → overlay 0068

A data word `.word thumb_func` (or a Thumb interior entry) holds the address
with bit 0 set. `handleRelocation` resolved the symbol to its even address and
the emitted data word came out even. For a function start the addend was 0,
so the output word was even. For an interior entry the low bit was treated as
a byte offset. A call through the word then entered ARM state on Thumb code
(SIGSEGV/SIGBUS under qemu). The relocation-flush path already set bit 0 for
Thumb function symbols, but data sections re-emitted through
`BinarySection::emitAsData` used `Symbol + Addend` directly.

Fix: for a non-code `R_ARM_ABS32`/`R_ARM_TARGET1` relocation whose extracted
value is odd and whose target is a Thumb function, reference the even code
address and carry the Thumb bit as addend 1. The word keeps the bit on every
emission path. Test: `arm-thumb-data-pointer.test`, which checks ARM pointers
stay even and Thumb start and interior pointers are odd and point at the
right instruction. It runs in default, reversed-block and padded layouts and
fails on the 0067 build.

Why it was invisible on the Pi: the LK full-image pipeline restores `.data`,
`.rodata`, `lk_init` and `commands` from the input and redirects the original
entries. Data pointers keep pointing at the original code, which jumps to the
rewritten code. Any workflow that keeps BOLT's own data sections (including
plain user-mode use) was exposed.

### R26 (P0) — inline-table base register read as data in a case → overlay 0069

0057 (A32 `ldr pc` tables), 0066 (Thumb `adr` + TBB/TBH) and 0067 (`-O0`
load-then-jump) re-point the table base `rB` at the re-emitted table. After the
table branch, `rB` therefore holds the *new* table address. If a case block
reads `rB` (for example `ldrh r0, [r2]` to load table data, or arithmetic on
`r3`), the result depends on layout. Under reversed blocks the probes produced
wrong values. Only R21 had a liveness check, and only for the jump register
`rX`.

Fix: `BinaryFunction::isTableBaseDeadAtCases` walks every path from every case
target (branches by label, nested inline tables, fall-through) and admits the
table only if `rB` is redefined unconditionally before any read. Register-list
loads (`pop {r4}`, user-bank `ldm ^`) count as definitions, which reuses R22's
helper, now `listLoadDefinesARM`. Predicated definitions do not end the live
range. At calls and returns the AAPCS rule applies: a call-clobbered `rB`
(r0–r3, r12) is dead. A callee-saved `rB` (r4–r11) survives calls and must be
restored before a return, otherwise the table is rejected. Unresolved branches,
data, or the end of the function on a live path also reject. Test:
`arm-table-base-liveness.test` (11 cases, A32 and Thumb). The 0067 build
wrongly admits all 6 must-reject cases.

Coverage cost: none. Full LK stays at 401/417 functions and 126164 code bytes;
`vsnprintf`'s Thumb table stays admitted. The edge image stays at 561 rewritten.

## Verification

- ARM lit 58/58 in both assertion modes; full BOLT lit has only the known
  AArch64 `constant_island_pie_update.s` failure. 0001–0069 replay exactly
  (`verify-atfe-overlays.py`, source identity `f47e50ee…`).
- Coverage receipts: `lk_coverage_r26_20261005.json`,
  `bolt_edge_coverage_r26_20261005.json`. A55 `47c73bc0` was re-measured and is
  unchanged at 400 rewritten.
- Pi (A72, Non-secure SVC): certified full-image gate on `424606a8` with the
  0069 toolchain, 10 repetitions, 18/18 results, PC evidence in both redirected
  functions — `docs/results/r26_certified_20261005.json`.

## Addendum: R27 probe extension (2026-10-05)

R27 widened the probe to 26 cases × 7 option sets
(`docs/results/edge_probe_r27_20261005.json`): **158 OK, 24 rejected, 0 wrong**.
No backend change was needed.

| New option set or case | What it exercises | Result |
|---|---|---|
| `split` | A profile samples only `t`'s entry, so every other block moves to `t.cold`: tables and their cases sit in different fragments | OK on every admitted case |
| `split-fill` | As `split`, with a profiled 1.1 MB filler between `t` and `t.cold`: cross-fragment `b<cond>` exceeds Thumb's ±1 MB and needs LongJmp stubs | OK on every admitted case |
| `instrument` | Baremetal instrumentation runtime (`privileged-single-core-no-fiq`), output must still compute the same results | OK; conditional returns and exclusives rejected by the instrumentation contract, as documented |
| `t32_narrow_branch_range` | `cbz` near its 126-byte limit, `beq.n`, `b.n` over 200-byte blocks | OK; under reversed layout a backward `cbz` became `cbnz` + `b.w` |
| `icf_twins_via_data_table` | Identical Thumb twins and identical ARM twins reached only through `.data` pointers | OK; ICF folds each pair, and the data words keep the Thumb bit (odd) or stay even (ARM) |
| `t32_tbh_cold_cases_split` | Hot TBH whose cases are all cold | OK in all option sets |

The first attempt used `--pad-funcs-before` to separate the fragments. It
aborted in JITLink because the emitter pads every fragment but LongJmp's
tentative layout pads only the first. That is a limitation of the debug
option (KNOWN_LIMITATIONS V9), so the probe uses a real filler function
instead.

## Limitations recorded (not fixed)

These are listed in [KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md#current-atfe-backend-limitations-re-baselined-2026-10-05):
the AAPCS assumption in R26; R25 not observable in the LK pipeline; the svc-exit
noreturn rejection; QEMU twin images without a protected BOLT window; the no-FPU
guard misreading BOLT outputs; and the review's uncovered areas (split
functions, instrumentation of table functions, user-mode runtime).
