# R17: synthesized edge-case test image (`bolt_edge`)

Approved by the user 2026-10-04 as open item R17 (P1, shared pool). Depends on
R11 (skip-and-report) so must-reject cases do not need one rerun each.

## Goal

A purpose-built ARMv7-A test image that exercises the AArch32 backend's edge
cases, including cases that must be **rejected**, with expectations computed
independently of BOLT and of the hardware.

## Design

A Python generator emits:

1. **Sources:** assembly and C for an LK app (like `bolt_bench`) or a small
   standalone bare-metal image. No FPU/NEON (`-mfpu=none`,
   `scripts/check-no-fpu.sh`).
2. **Admission manifest:** per function, "rewrite" or "reject: <diagnostic>".
   Compared against `scripts/lk_coverage_report.py` output (or R11's report).
3. **Execution oracle:** each case returns a checksum from fixed inputs; the
   generator's own model computes the expected values. Each generated image
   needs a reviewed oracle contract (6b); reviewing the generator once covers
   its images.

Runs in QEMU for iteration and on the Pi (watchdog armed, fast loader) as the
final check, through the existing gates (`full_image_build.py`,
`full_image_verify.py`).

## Cases (stage 1, about 40, many reusable from `bolt/test/ARM` fixtures)

| Area | Cases | Related |
|---|---|---|
| Interworking | `bl`/`blx`/`b` in every ISA direction; cross-ISA tail calls; calls from non-emitted code | R1–R3 (0046) |
| IT blocks | all 15 masks; predicated return/call/branch; conditional tail calls with and without IT; branch not last in group (must reject) | R4, R6 (0051, 0053) |
| Noreturn | proven chains; may-return callee, indirect, conditional final call, recursion, real fallthrough (must reject) | R5 (0052) |
| Far code | padding past ±1/16/32 MiB; LongJmp stubs; far tail calls; conditional calls via stubs | R7 (0049), R8 |
| Data in code | literal pools; TBB/TBH; ADR to a table; switch tables in both ISAs | R12, item 12 |
| Entries/symbols | 16-bit first instruction; PC-relative first `bl`; static `/1` duplicates; aliases; interior entries; size-0 assembly | R13, item 11 |
| Must-reject guards | PC reads/writes; exception returns; LDREX/STREX across functions | R15, 0033/0035/0038/0045 |
| Register/flags | r12 live across a hot→cold split; flag-sensitive paths; register pressure | R8 |
| Runtime context | functions called from IRQ; recursion; indirect calls | item 9 |
| Compiler variety | the same C cases at `-O0`/`-O2`/`-Os`, ARM and Thumb, clang and gcc | — |

Stage 2: a randomized CFG/IT/predication generator using the same manifest
and oracle format.

## Done means

Generator, sources and manifest committed; a reviewed contract for the stage-1
image; QEMU and Pi runs certified by the gates; each case's admission matches
the manifest; known-open items (R8, R12, R13, R15) appear as expected
failures until fixed.

## Stage 1 result (2026-10-04)

68 cases built into `fixtures/lk-rpi4-bolt-edge-0895d7bc.elf`. Pi baseline
68/68 equal to the models; admission 72/77 as designed (gaps → R18, R19);
BOLT-rewritten image with 25 redirected case entries: 68 × 2 runs, 0
mismatches. Evidence: `docs/results/bolt_edge_stage1_20261004.json`. Far-code
cases were deferred (image size); they remain in the host lit tests.
