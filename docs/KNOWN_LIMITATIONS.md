# Known limitations

Current ATFE limitations. Open work is in
[HANDOFF.md](HANDOFF.md#claims-consolidated-todo); the latest reviews are the
[deep review at 0069](reviews/CORRECTNESS_REVIEW_CLAUDE_0069.md) and the
[reconciled review](reviews/CORRECTNESS_REVIEW_ASTRA_0057.md).
Candidate no-FPU scanning, clean provenance and broader runtime/entry/pass
matrices remain bounded by their current work items.

## Current ATFE backend limitations (re-baselined 2026-10-05)

State: overlays 0001–0071, full LK `424606a8` 401/417 functions (126164 of
126834 code bytes, 99.5%), edge image `ce8dd005` 561 rewritten, A55 `47c73bc0`
400 rewritten. Verified on the Pi 4B (Cortex-A72, AArch32, Non-secure SVC);
the real target is a Cortex-A55, also in Non-secure SVC. Sources:
[deep review 0069](reviews/CORRECTNESS_REVIEW_CLAUDE_0069.md), [HANDOFF](HANDOFF.md),
[LK coverage](LK_COVERAGE.md). Everything below fails safe (BOLT rejects the
function, or the limit is in verification scope) unless marked otherwise.

### Declared scope

| ID | Limitation | Consequence |
|---|---|---|
| S1 | Static, non-PIC, LLD-linked AArch32 images (`--emit-relocs`), little-endian, ARMv7-A/ARMv8-A AArch32, A32 + T32 | Other inputs are untested; PIC/TLS/GOT forms are not modelled (L2) |
| S2 | No FPU/NEON anywhere (`-mfpu=none`), including the BOLT runtime | VFP/NEON code is outside the verified set; `scripts/check-no-fpu.sh` guards inputs |
| S3 | No `.ARM.exidx`/`.ARM.extab` handling (U3) | `-fno-exceptions`, no unwinding through rewritten code; unwind sections are rejected, not rewritten |
| S4 | Instrumentation contract `privileged-smp-no-fiq`: SVC, counters via injected LDREXD/STREXD helper (0060), no FIQ handlers in rewritten code | Instrumented code must not run from FIQ or user mode |
| S5 | Full-image pipeline restores `.data`, `.rodata`, `lk_init`, `commands` from the input and redirects original entries | Data never points at rewritten code directly; original entries stay as redirect stubs (address-taken functions still work, at one extra branch) |

### Rejected shapes (coverage loss, not wrong code)

| ID | Shape | Where seen |
|---|---|---|
| N1 | Callee whose noreturn property is not provable (e.g. `svc` exit followed by a loop): a terminal `bl` to it reads as fall-through | probe `noreturn_call_at_end`; LK's `bcopy`/`bzero` are real fall-through and must stay rejected |
| N2 | PC-writing control transfers other than modelled tables/returns: exception returns (`movs pc, lr`, `ldm …^` with pc, `rfe`), `add pc, pc, rI` switches, computed `mov pc` | LK vectors (`arm_irq`, `arm_fiq`, aborts, `arm_syscall`, `arm_undefined`), `arm_secondary_setup`; edge `a_add_pc_switch` |
| N3 | Position-dependent PC reads as data (other than modelled literal pools and table bases) | startup (`arm_reset`, skipped), edge `a_pcread` |
| N4 | Inline-table base register read in a case block, or a callee-saved base not restored before return (R26) | probes `t32_tbh_adr_base`, `a32_table_base_read_in_case` |
| N5 | `-O0` load-then-jump tables whose case reads the jump register, non-adjacent load/jump, or clobbered base (R21) | lit only |

### Assumptions the rewrite relies on

| ID | Assumption | If violated |
|---|---|---|
| A1 | AAPCS at calls and returns (R26): a call-clobbered register last written as a table base is not consumed by a callee or caller | Hand-written assembly that passes a jump-table address in r0–r3 through a call/return would be admitted and see the new table address. Compilers never do this (inline tables are not address-taken) |
| A2 | A data word holding an odd value inside a Thumb function is a Thumb code pointer (R25) | An odd byte pointer into Thumb code used as data (not as a code pointer) would be re-pointed to the matching instruction with bit 0 set, which is the same bytes only if the code is unchanged; no such use is known |
| A3 | The ICF/reorder passes see the whole relocation set (`--emit-relocs`) | Missing relocations leave stale references; LLD with `--emit-relocs` is required |

### Verification gaps

| ID | Gap | Status |
|---|---|---|
| V1 | Security state | None: the target runs Non-secure SVC like the Pi; Secure-SVC parity (T3) closed as not needed 2026-10-05 |
| V2 | Real Cortex-A55 hardware (T4) | User, office environment; A72 timing gains do not transfer |
| V3 | R25's rewritten data pointers are not exercised by the LK pipeline (S5 restores data) | Covered by lit and the qemu-user probe only |
| V4 | IRQ PC sampling cannot see code that runs with IRQs masked | Execution evidence for such code needs other means (counters) |
| V5 | QEMU twin image has no protected BOLT window (`__bolt_reserved_*`); BOLT code after `_end` is overwritten by the heap | QEMU rewrite routes are diagnostics only and refuse such images |
| V6 | `check-no-fpu.sh` on BOLT outputs misreads the original `.text`, which keeps no input `$t` mapping symbols | Run the guard on inputs and on the new `.text`; tracked in HANDOFF item 18 |
| V7 | Split functions with tables (including a 1.1 MB hot/cold gap), instrumentation of table functions, ICF folding of Thumb and ARM twins behind data pointers, and Thumb narrow-branch relaxation are now probed (R27, `edge_probe_r27_20261005.json`: 158 OK, 24 known rejections, 0 wrong) | Resolved 2026-10-05 for qemu-user; not on the Pi (the certified LK pipeline does not split functions) |
| V8 | Upstream (non-ATFE) series still has U2–U4, U8/U9, L1–L12 ([upstream audit](upstream/UPSTREAM_AUDIT.md)) | Deferred TODO (user, 2026-09-30) |
| V9 | `--pad-funcs-before` combined with `--split-functions` aborts in JITLink for distant fragments: the emitter pads every fragment, LongJmp's tentative layout pads only the first | Debug option only; fails safe (no output). Use a real filler, as the probe does |
| V10 | Cross-fragment Thumb `b.w`/`bl` beyond +-16 MB (hot and cold more than 16 MB apart) is not probed; the 1.1 MB case (beyond `b<cond>.w`) passes | Needs a 16 MB+ image; LK is far below that |

### Superseded index entries

- **U1** (7% full-image coverage, non-determinism): superseded for ATFE by the
  401/417 (99.5%) full-image coverage and certified Pi gates. The upstream base
  measurement remains historical.
- **U5** (TBB/TBH unrecoverable): superseded for ATFE. TBB/TBH tables are
  modelled and re-emitted (0024), including an `adr` base (0066, guarded by
  R26). Upstream base unchanged.

### Historical audit

The upstream and early-ATFE audit (U1–U9, D3–D5, L1–L12; IDs still cited in overlay comments) is in [upstream/UPSTREAM_AUDIT.md](upstream/UPSTREAM_AUDIT.md).
