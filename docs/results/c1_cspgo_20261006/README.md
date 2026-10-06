# C1: IR-PGO, CSPGO, ThinLTO and optional BOLT

C1 adds and verifies the two-round compiler profiling pipeline. It does not
change the LLVM backend or certify a new image contract. See the
[build and collection recipe](../../verification/CSPGO_PIPELINE.md).

## Measured results

Pi 4B Cortex-A72, AArch32 bare-metal LK, no FPU/NEON, `STAIR_M=8`.
Train on `stair 0 0`; measure variants 0, 1 and 2 separately with the sampler
stopped and the workload's normal IRQ masking. Each primary comparison uses
three interleaved rounds, two runs per image per round. Negative cycle change
means faster. Intervals describe repeatability on this board; runs within a
boot share cache and predictor state and are not independent population samples.

| Comparison | Input variant | Mean cycles before → after | Cycle change | 95% interval half-width |
|---|---|---|---|---|
| IR-PGO+ThinLTO → CSPGO+ThinLTO | 0, training input | 16,353,197 → 9,243,530 | -43.476% | 0.004 pp |
| IR-PGO+ThinLTO → CSPGO+ThinLTO | 1 | 16,353,978 → 9,246,085 | -43.463% | 0.011 pp |
| IR-PGO+ThinLTO → CSPGO+ThinLTO | 2 | 14,745,327 → 14,743,739 | -0.011%, interval includes zero | 0.044 pp |
| IR-PGO+ThinLTO → same + sampled BOLT | 0 | 16,352,670 → 9,317,272 | -43.023% | 0.003 pp |
| CSPGO+ThinLTO → same + sampled BOLT | 0 | 9,243,054 → 9,286,405 | +0.469% | 0.015 pp |
| CSPGO+ThinLTO → same + sampled BOLT | 1 | 9,247,199 → 9,287,328 | +0.434% | 0.004 pp |
| CSPGO+ThinLTO → same + sampled BOLT | 2 | 14,745,602 → 17,731,994 | **+20.253%** | 0.046 pp |

The compiler and BOLT rows come from separate interleaved comparisons, hence
small differences in the repeated compiler means. A smaller sanity comparison
(one round, two runs per image) measured plain O2 baseline 10,495,386 cycles
versus CSPGO+ThinLTO 9,243,646 (-11.927%). The 43.5% gain is against IR-PGO+
ThinLTO, whose layout is poor for this synthetic kernel, not against plain O2.

The BOLT result is a significant shifted-input regression, not an incremental
CSPGO speedup. It applies to this sample-trained kernel and these BOLT options;
neither exact counters nor all pass/profile choices were evaluated. These
measurements do not predict Cortex-A55 performance or representative application
performance. Compiler and binary profile optimizations overlap; additive gains
from every stage are not guaranteed.

## What was verified

- Ordinary IR collection, IR profile use with module ThinLTO, late CS collection,
  merged ordinary+CS profile use, and final optimized builds. The indexed merge
  has 75 ordinary and 75 CS records; raw dumps are 11,208 and 13,184 bytes.
  Only trained/nonzero counters are required, not that every record is executed.
- Primary compiler run: 36 measured records. Final current-workflow replay:
  12 records, with source/tool/runtime identity checks and strict training frames.
  Both manifests are PASS and every recorded artifact hash was checked before
  packaging. BOLT comparisons: 48 records; plain-baseline sanity: four records.
- Five final images (baseline, IR, CS, IR+BOLT, CS+BOLT) give identical complete
  18-workload result sets. Timing sinks match within each input variant:
  `0x2f744325`, `0xce57eab7`, `0x5806b01f`. This is output consistency against
  baseline, not an independent algorithmic oracle.
- CS+BOLT PC watch: 501 samples inside rewritten kernel
  `[0x800e6000,0x800f7f42)`, on core 2; all 521 samples retained. Static redirects
  and no-FPU scans pass for both BOLT images. No new backend certification claim.
- Full host suite: **177 tests run, 12 skipped, no failures** (165 executed).
  Ten new tests cover profile kinds, trained levels, transport and workload frames.
  After promoting CSPGO to the main flow, the no-argument final build was
  rerun with the merged profile: ELF and binary are byte-identical to the
  measured CS image, no-FPU scan passes, and the shell cycle's default dispatch
  reaches the two-round workflow. This normalization only changes entry-point
  defaults/docs; the archived run manifests retain their original source hashes.
  Changed shell scripts pass syntax checks. Baseline and legacy frontend
  collection still build and pass the no-FPU scan; an existing frontend indexed
  profile validates. A fresh legacy frontend optimized cycle was not run.
- ATFE overlays 0001–0072 replay exactly with no uncovered/mismatched files;
  shared source preserved. Certified fixture coverage remains **401/417 functions,
  126164/126834 code bytes (99.5%)**. Compiler candidates each emit 407/423
  functions (nine rejected rows, five ICF rows, two aliases), not additional
  certified coverage. Their generic instrumentation scans do not select the stair
  kernel and therefore do not establish its instrumentation support.

## Counter limitation and sampling scope

Exact BOLT counter instrumentation of the CS stair kernel safely refuses:
`AArch32 instrumentation does not support conditional returns in bolt_bench_stair_kernel`.
This is the existing 0036 guard, not a CSPGO incompatibility. R35 in the
[shared queue](../../HANDOFF.md) tracks predicated function-exit/continuation
counting with A32/T32, IT/flags/register/stack preservation and both assertion
modes plus Pi validation. R35 is open; this change does not remove the guard.

The optional comparison uses fresh sealed PC samples for each exact compiler
ELF, period 20,000 cycles and 32 repetitions: IR 28,790 accepted samples,
CS 16,429. Sampling enables IRQ visibility during training; it infers edge
frequencies and rewrites/redirects only `bolt_bench_stair_kernel`. The rest of
LK stays original. A failed IR UART capture was rejected and retained before
the accepted retry. BOLT images are about 983 KB versus 260,096-byte compiler
images because the original code and reserved gap remain in the image.

Compiler profiling is module-scoped, value profiling disabled, sequential
training with non-atomic counters; concurrent/SMP/FIQ workload training is
unsupported. See [limitations](../../KNOWN_LIMITATIONS.md) and the recipe.

## Portable evidence

[default-build.log](default-build.log), `cspgo_thinlto.build.log`,
`cspgo_thinlto.nofpu.log` and `normalization.json` retain the later default-build
verification separately from the immutable measured-run archive.

[Archive audit](archive-audit.json) verifies all 457 retained files are readable,
the two compiler manifests' 158/112 bound artifact hashes match, and staged
default-build log bytes match their receipt. The
[frontend/IR probe](frontend-ir-probe.json) confirms that the pinned driver
rejects frontend-profile use plus ordinary IR collection in one build. The
profdata tool accepted a historical mixed-kind merge; that file was not used
and does not establish a supported combined frontend/IR optimization route.

[summary.json](summary.json) contains exact means, interval calculations and the
archive SHA-256. Adjacent CSVs, [host tests](host-tests.log),
[overlay replay](overlay-replay.json), [result consistency](result-consistency.json),
[PC watch](rewritten-pc-watch.log), coverage reports and the safe-refusal log
are directly readable.

[evidence.tar.xz](evidence.tar.xz) retains complete `compiler/`, `final-workflow/`
and `bolt/` runs: final and instrumented images, profiles, manifests and seals,
build/no-FPU logs, both boots' training receipts, uploaded measurement snapshots,
serial logs, failed capture and accepted retry, redirects and PC watch. Paths
recorded in old receipts are historical locations; use the extracted relative
paths and hashes for inspection. The archive contains no compiler/runtime
binaries; use the recorded pins and tool hashes to rebuild.

Extract into a fresh directory with `tar -xJf evidence.tar.xz -C <fresh-dir>`.
Replay using the recipe's Windows/WSL compiler cycle and optional sampling
comparison. The isolated working tree is `/home/user/bolt-cspgo`; primary output
is `build-atfe/cspgo-runs/c148c605589f7b94`, and BOLT output is
`build-atfe/c1-bolt-comparison`. Shared ATFE source and assertion-mode builds
remain on 0001–0072, unchanged. After final PC watch: Pi shell on CS+BOLT image,
sampler stopped/watch ranges cleared, watchdog off, COM5 closed.
