# R28 and R29: fixed in overlays 0070 and 0071 (2026-10-05)

Both were found by [B1](../b1_sampling_vs_instrumentation_20261005/README.md).
Hardware checks on the Raspberry Pi 4B (A72, AArch32, Non-secure SVC),
watchdog armed.

## R28 (P0, wrong code): ARM table entries got the Thumb bit

**Symptom.** In a whole-image rewrite, the A32 `pl_b` (an
`add rB, pc; ldr pc, [rB, rI, lsl #2]` jump table, modelled since 0057) was
re-emitted with every table entry odd. `ldr pc` with bit 0 set switches to
Thumb state, so the case blocks ran as Thumb and the core data-aborted.

**Cause.** BOLT's JITLink pre-prune pass (`JITLinkLinker.cpp`) marks every
unnamed graph symbol that lies inside a Thumb function's range as
`ThumbSymbol` (meant for local branch labels). MC refers to local labels
through the section symbol, which sits at offset 0 of `.text`. When the
section starts inside a Thumb function (as in LK, and in any binary whose
first function is Thumb), that symbol was flagged, and `Data_Pointer32` ORs
bit 0 into every absolute word built from it. The emitted object itself was
correct (even addends, correct `$a`/`$d` mapping symbols).

`r28_repro.py` shows it with 4 small programs: an ARM-only binary was fine;
a Thumb caller, or a Thumb function placed before or after the ARM function,
made all four table words odd.

**Fix (0070).** `Data_Pointer32` edges to unnamed symbols get their own
anonymous target at the exact even address, with the parity in the addend
(the Thumb bit of a real Thumb code pointer is already there, as 0068 emits
it), and these targets are excluded from the Thumb-range marking. Test:
`arm-ldr-pc-table-mixed-isa.test` (an ARM table with a Thumb `_start`, a
Thumb function before, and one after, in default and reversed block order;
control: a Thumb function's address in an ARM literal keeps bit 0). It fails
on 0069 (odd entries) and passes on 0070.

**Pi.** A profile-less whole-image rewrite of the B1 input that redirects
`pl_b`, `pl_run`, `bolt_bench_pgo_lab`, `bolt_bench_switch` and
`bolt_bench_switch_pick` (both A32 table functions), 2 rounds x 2 runs
(`r28_pl_b_switch_pi.csv`): results identical to the input in every run (it
data-aborted before the fix). Rewritten `pl_b` -5.08%, `switch` -7.69%.

## R29 (fail-safe refusal): Thumb short branches

**Symptom.** Reordering the 120 KB Thumb ThinLTO stair kernel, and
instrumenting Thumb `bolt_bench_multi` (756 bytes) or `bolt_bench_stair`,
stopped with the R8 refusal "local branch ... needs an r12 stub but r12 is
live there". B1 had to build `bolt_bench` in ARM mode.

**Cause.** `LongJmp` measured each Thumb branch by its current encoding:
16-bit `b`/`b<c>` (`tB`/`tBcc`) at their short range, and `cbz`/`cbnz` at
their 0-126-byte range. When a new layout moved a target beyond that, it
planned an r12 stub. But Thumb-2 has wide forms (`b.w`, `b<c>.w`), and
`prepareForEmission` already emits every `cbz`/`cbnz` as the inverted
`cbz`/`cbnz` over a `b.w` to the target.

**Fix (0071).** `MCPlusBuilder::widenBranch` (ARM: `tB`->`t2B`,
`tBcc`->`t2Bcc`; a predicated `tB` is left alone); `LongJmp` widens a branch
in place when the wide form reaches, before considering a stub; `cbz`/`cbnz`
are measured as the `b.w` actually emitted. The R8 error message now names
the opcode. Test: `arm-thumb-short-branch-range.test` (16-bit `beq`, `b` and
a `cbz`, each separated from an r12-reading target by reordering; checks
0 stubs, the wide forms, and runs the rewritten program under qemu-arm). It
fails on 0070 with the R8 refusal and passes on 0071.

**Pi, Thumb ThinLTO stair showcase** (3 rounds x 2 runs, checksum identical
in all 18 runs, `r29_thumb_stair_pi.csv`):

| Thumb image | Cycles | L1I refills |
|---|---|---|
| -O2 | 10.496M | 1 |
| ThinLTO (BOLT input) | 28.567M | 1,730,774 |
| BOLT, instrumentation profile | **9.101M** (-68.1% vs input, -13.3% vs -O2) | 41,649 |

0 stubs; previously refused.

**Pi, Thumb whole image** (B1's app suite; 11 Thumb `bolt_bench` functions
instrumented, previously refused; BOLT from those counters; 3 rounds x 1
pass, `r29_thumb_whole_image_pi.csv`): all 8 app results identical; `multi`
-45.48%, suite total -4.84%, everything else within noise.

## Gates

- ARM lit 60/60 in both assertion modes (59 + the R29 test after 0070; 58 + 2
  new tests overall).
- Overlay replay 0001-0071 clean (0 uncovered, 0 mismatched files).
- LK coverage unchanged: 401/417 functions, 126164 of 126834 code bytes
  (99.5%), `../lk_coverage_r29_20261005.json`.
- The certified full-image gate was not rerun; R28/R29 change linking and
  long-branch handling, and the Pi evidence above runs the affected shapes.

## Images

| | SHA-256 |
|---|---|
| R28 input / fixed | `c7e9e0d2…` / `6d7e4e36…` |
| Thumb stair -O2 / ThinLTO / BOLT | `47f0db85…` / `f873b3eb…` / `2455ddf7…` |
| Thumb whole image input / BOLT | `d186e4ad…` / `fc442b7f…` |
