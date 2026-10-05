# B2: BOLT from lk-perf sampling vs instrumentation, rerun on 0001–0071 (2026-10-05)

A rerun of [B1](../b1_sampling_vs_instrumentation_20261005/README.md) after
R28/R29 were fixed ([0070/0071](../r28_r29_20261005/README.md)). What
changed from B1:

- every image is Thumb (LK's default; B1 had to build `bolt_bench` in ARM mode);
- no R28 workaround: `pl_b`, `pl_run` and the other `ldr pc` table functions
  are rewritten and, in R3, redirected;
- lk-perf with K13-K15, so `profiler stat` no longer disables the cycle
  counter: 2 suite passes per boot;
- denser sampling of the whole image: 50 us, one capture cycle per command,
  `composite` listed three times (4,176 samples in `bolt_bench_composite`,
  against 245 in B1).

All numbers are from the Raspberry Pi 4B (A72, AArch32, Non-secure SVC,
600 MHz), watchdog armed, every app result identical in every run of every
image. Measurement only; no certification gate.

## Showcase: Thumb `bolt_bench stair`, ThinLTO, 512 sites (3 rounds x 2 runs)

| Image | Cycles | vs ThinLTO input | L1I refills |
|---|---|---|---|
| -O2 (reference) | 10.496M | | 2 |
| ThinLTO (BOLT input; kernel 120 KB) | 28.529M | | 1,748,598 |
| **BOLT, instrumentation profile** (1,792 edges) | **9.102M** | **-68.1%** | 42,027 |
| **BOLT, lk-perf sampling profile** (44,639 samples) | **9.237M** | **-67.6%** | 77,351 |

Checksum identical in all 24 runs. The sampled profile recovers **99.3%** of
the instrumentation gain (19.29M vs 19.43M cycles saved). B1 (ARM mode):
99.9%.

## Whole LK image, existing apps (3 rounds x 2 passes)

| App | input | R1 instrumentation (11 fns) | R2 lk-perf, same 11 fns | R3 lk-perf, whole image (69 fns) |
|---|---|---|---|---|
| composite | 6.105M | +0.01% | **+0.01%** | 0.00% |
| multi | 43.339M | **-45.21%** | **-45.78%** | **-34.24%** |
| pl_a / pl_d | 25.7 / 14.2M | 0.00 / +0.05% | 0.00 / +0.01% | 0.00 / -0.04% |
| pl_b / pl_c | 30.5 / 18.8M | 0.00% | 0.00% | **+2.59 / +1.41%** |
| stair (640 sites, -O2) | 13.106M | +0.56% | **+10.31%** | **+10.35%** |
| bench / nest / smp | 16.2 / 2.9 / 11.0M | 0.00% | 0.00% | 0.00% |
| memtest / schedtest | 165.8 / 80.8M | within noise | within noise | within noise |
| **suite total** | 428.39M | **-4.45%** | **-4.31%** | **-2.77%** |

Profiles: R1 1,014 exact edges; R2 20,559 samples; R3 68,237 samples over 69
functions (65 entries redirected; 4 left unredirected because BOLT changed
their prologue).

### Why the sampled variants differ (bolt_bench's own PMU counts, `whole/pmu_excerpt_round1.txt`)

| | instructions | taken branches | mispredicts | L1I refills |
|---|---|---|---|---|
| stair, input | 29.27M | 2.64M | 10.5k | 2 |
| stair, R1 instrumentation | 29.27M | 2.64M | 14.1k | 3 |
| stair, R2/R3 lk-perf | 29.41M | 2.80M | **71.4k** | 3 |
| multi, R1 / R2 | 50.09M | 0.11M / 0.10M | 12.0k / 19 | 52k |
| multi, R3 | 50.09M | 0.10M | 24 | **700k** |

- **stair (fits in L1I): the sampled layout gets branch directions wrong.**
  Without branch records BOLT infers edge counts from block counts (54-57%
  CFG flow imbalance in its report); with this function's many two-way
  blocks it picked fall-through sides badly: +5x mispredicts, +152k taken
  branches. Instrumentation knows every edge. In B1's ARM-mode build the same
  effect was +1.4%; in Thumb it is +10.3%.
- **multi in R3: function order, not block order.** `multi`'s gain is the six
  7-11 KB `mf*` functions placed together so they fit the L1I. With a
  whole-image profile, hfsort+ orders 69 hot functions by call density and
  no longer keeps the six together: L1I refills 52k -> 700k, gain -45% ->
  -34%.
- **pl_b/pl_c in R3** (rewritten and run now that R28 is fixed): sampled
  layouts 1.4-2.6% slower than the original; instrumentation cannot profile
  them (not `bolt_bench_*`), so R1/R2 leave them alone.
- **composite**: the dense capture fixed B1's +16.4% regression (+0.01%).

## What this says (B1 + B2)

1. Where BOLT has a real layout problem (code larger than the cache), a
   sampling profile is nearly as good as instrumentation: 99.3-99.9% of the
   gain on the showcase, and `multi` -45.8% vs -45.2%.
2. Sampling needs density per hot function (B1 composite: 245 samples,
   +16%; B2: 4,176, +0.01%).
3. Where the code already fits, BOLT has little to win, and a sample-based
   profile can lose: it cannot tell branch directions as well as edge counts
   (stair -O2 +10% in Thumb). Without LBR-like branch records on this core,
   instrumentation is the safer profile for branch-heavy code.
4. More scope is not automatically better: profiling the whole image
   (kernel, libc, drivers) moved function order and cost `multi` a third of
   its gain; the kernel code itself gained nothing (it fits the caches).
5. Practical recipe on this platform: instrument what the policy allows; use
   lk-perf sampling, densely, for code that cannot be instrumented, and only
   for functions that are actually cache-bound.

## Artifacts

| | SHA-256 |
|---|---|
| stair -O2 / ThinLTO / BOLT instr / BOLT lk-perf | `28a2c2bb…` / `6ec68501…` / `3a126a3e…` / `d714d78a…` |
| whole input / R1 / R2 / R3 | `3c902ecb…` / `36192905…` / `f4742ef2…` / `ceaab479…` |

Profiles and identity manifests, measurement CSVs and summaries, skip and
scope lists, the PMU excerpt, and the two build scripts (`stair.sh`,
`whole.sh`, scratch paths) are in this directory. Sampling and instrumentation
captures used `scripts/pi4/pi4_lkperf_profile.py` and
`scripts/pi4/pi4_bolt_profile.py`; measurements `pi4_compare.py` and
`pi4_suite_measure.py`.
