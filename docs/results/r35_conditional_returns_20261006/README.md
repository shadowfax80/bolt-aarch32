# R35: conditional-return counter support

Overlay **0073-arm-conditional-return-flow.patch** fixes the current CSPGO
stair kernel's exact-counter limitation. Before 0073, guard 0036 safely
refused this exact C1 input (`c02862f04da795f3…`). After 0073, BOLT instruments
it, the Pi records both return outcomes correctly, and the bound profile
optimizes the original compiler ELF. The earlier C1 refusal and sampled
measurements remain historical receipts; this is a separate counter run.

## Design and guarded scope

- Uniform Thumb IT groups ending in a return become an inverse conditional
  branch around an unconditional body and return. The predicate is evaluated
  before any body work, including stack adjustment. Earlier body instructions
  must preserve flags. Narrow instructions that suppress flags inside IT but
  set them outside IT remain refused.
- A32 conditional returns get an inverse guard after an ordinary predecessor
  and a separate unconditional return block. Entry returns, targeted/labeled
  returns and returns after a control transfer remain refused because the
  predecessor is not a safe shared profile site.
- Lowering runs before CFG construction and profile matching for both
  collection and consumption. Return/continuation block offsets remain
  original instruction boundaries; the added A32 guard uses its predecessor's
  input offset. Shared MCContext label/expression allocation is locked during
  parallel CFG construction. Guard 0036 remains active for unsupported shapes.

Mixed IT predicates and earlier flag changes cannot be replaced by a single
guard without changing semantics. **R36** in [HANDOFF](../../HANDOFF.md) tracks
extending those shapes. R35 is closed for this implemented subset and the
requested C1 compiler output; it is not universal conditional-return support.

## Verification

| Check | Result |
|---|---|
| Full ARM lit suite | **62/62 ON and 62/62 OFF** |
| New return-flow fixture | **115 outcomes per mode**: 17 admitted A32/Thumb cases and six safe refusals, each across five option sets |
| State/semantic diagnostics | Each mode executes 17 originals and 34 default/reversed rewrites under user QEMU; input 0/1/2 results, APSR NZCV and SP checks pass. Privileged probes are built here, not executed under user QEMU |
| Assertion-mode output parity | CS instrumentation, counter optimization and certified-image binaries match exactly; ELFs match after removing command-line `.note.bolt_info` only |
| Overlay replay | 0001–0073, no uncovered/mismatched source files; live source preserved |
| No FPU/NEON | Instrumented/optimized CS and full-image candidates pass in both assertion modes |
| Repository / publication | [Offline health](repo-health.log) passes; [staged-byte audit](staged-byte-audit.log) checks archive, patch, CSVs, PC logs, replay and both outcome reports against their recorded hashes |
| Certified fixture coverage | Unchanged: **401/417 functions, 126164/126834 code bytes (99.5%)**; instrumentation scan succeeds |
| Certified full-image Pi gate | Approved `424606a8` oracle passes all 18 workloads; ten candidate repetitions and PC evidence for both selected redirects (`interwork`, `memcpy`) |
| CS image result consistency | Original, instrumented and counter-optimized images agree on the complete 18-workload set; this is agreement, not a new algorithmic oracle |
| Rewritten-PC evidence | Core 2: **40,431** hits inside instrumented `[0x800e6000,0x80128ea4)` and **1,495** inside optimized `[0x800e6000,0x800f7ef6)` |

This is incremental ON/OFF verification plus complete source replay. The
item-14 **clean-build** receipt remains for 0001–0072; no new clean-build
binary-provenance claim is made. The ARM lit run emits the existing missing
`psutil` timeout warning; all 62 ARM tests execute and pass. No whole LLVM/BOLT
suite rerun is claimed. A32 return variants have build and user-QEMU evidence;
the new instrumented hardware path is the Thumb C1 kernel. Broader A32/IRQ/SMP
state certification and actual Cortex-A55 hardware remain outside this receipt.

## Exact flow on the Pi

The unchanged C1 input is `STAIR_M=8`, Cortex-A72 AArch32 Non-secure SVC,
no FPU/NEON. Instrumentation declares `privileged-single-core-no-fiq`, no
call instrumentation and conservative edge counters. Runs are sequential,
with a watchdog; snapshots occur after workload completion. Each capture has
2,559 counters in a 96,281-byte sealed section. The normal workload performs
100 warmups plus 1,500 measured calls, independently specifying 1,600 calls.

| Input | Guard `0x9e10` → return `0x9e12` | Guard → continuation `0x9e1a` | Entry / exit totals | Checksum |
|---|---|---|---|---|
| 0, training selectors | 1600 | 0 | 1600 / 1600 | `0x2f744325` |
| 2, shifted selectors | 0 | 1600 | 1600 / 1600 | `0x5806b01f` |

[Counter audit](counter-flow.json) also checks every internal node's flow,
capture/dump/log hashes and complete command-framed measurement records.
The exact-counter profile gives BOLT **0% CFG flow-conservation gap**. Its
100% call-graph gap is expected for this single selected function with call
instrumentation disabled; it does not mean complete interprocedural profiling.
The generic counter collector binds artifacts and validates the dump but
does not independently validate workload semantics; R32 remains open.

## Performance caveat

Profile training uses input 0. Timed runs stop profiling, use the normal
workload IRQ masking, and interleave the original compiler image and the
counter-optimized image for three rounds, two runs per image per round.
All 36 measured records have complete metrics and matching per-input checksums.

| Input | Compiler mean cycles | Counter-BOLT mean cycles | Change |
|---|---|---|---|
| 0 | 9,243,351 | 9,249,138 | **+0.063%** |
| 1 | 9,247,347 | 9,251,130 | **+0.041%** |
| 2 | 14,740,096 | 16,351,861 | **+10.935%** |

The limitation fix provides correct feedback, **not an incremental speedup**.
Training-input performance is nearly unchanged; the shifted-input regression
remains substantial. C1's sampled comparison had +20.253% on input 2, but
the runs use different backend/profile/layout choices and were taken separately;
this is not a controlled counter-versus-sampling performance comparison.
Within-boot repetitions share cache/predictor state; intervals in
[summary.json](summary.json) describe repeatability, not independent population
samples. No representative-application or Cortex-A55 gain follows.

## Portable evidence and pickup

[Archive audit](archive-audit.json) verifies every member of
[evidence.tar.xz](evidence.tar.xz) against its retained original bytes. Extract
into a fresh directory. `run/` contains exact inputs, counter dumps/seals,
maps, profiles, rewritten images, full-image gate and serial/measurement
receipts, raw logs, orchestration helpers and retained failed attempts.
`host-fixtures/on` and `off` contain assemblies, binaries, diagnostics and
115-outcome reports. `measurements-v0/` retains the earlier six timing boots.
Tool binaries are omitted; their hashes, source pin and full replay identify
the builds. Recorded absolute paths are historical locations, not portable
lookup paths; use extracted relative paths and hashes.
The archived helpers assume the repository's `out/r35` layout; use the primary
pipeline recipe for a fresh run with different paths.

Readable adjacent files include [lit ON](arm-lit-on-final.log),
[lit OFF](arm-lit-off-verified.log), [parity](assertion-parity.log),
[certified gate](certified-gate.json), [result consistency](result-consistency.json),
[PC watch](rewritten-pc.json), [source replay](replay-final.json),
CSVs and [summary](summary.json). The
[pipeline recipe](../../verification/CSPGO_PIPELINE.md#exact-counter-alternative-0073-and-later)
describes reproducing the sealed counter route from a fresh directory.

The shared ATFE source and both builds are on 0001–0073. Preserve the dirty
source; do not reapply overlays or trust old apply stamps as identity proof.
Isolated compiler inputs stay in `/home/user/bolt-cspgo/build-atfe/cspgo-runs/c148c605589f7b94`;
R35 outputs are `build-atfe/r35-counter-stair`. Windows evidence is `out/r35`.
Last Pi state: counter-BOLT CS image at the shell, sampler stopped, watch
ranges cleared, watchdog off, COM5 closed. These are last observations; use
the current shared resource tables before doing new work. Next normal queue
item is R32; the remaining conditional-return feature work is R36.
