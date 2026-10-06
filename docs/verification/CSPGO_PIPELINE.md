# Bare-metal IR-PGO and CSPGO with ThinLTO

The compiler pipeline supports frontend instrumentation PGO (the historical
route), ordinary IR instrumentation PGO, and context-sensitive IR PGO. Only
`app/bolt_bench/bolt_bench.c` and `composite.c` are profiled/compiled as
ThinLTO bitcode. The rest of LK remains native code. This does not change BOLT
admission or certify a new image against an approved oracle.

This is the **main compiler flow**: ordinary IR-PGO → ThinLTO-guided CSPGO
training → merged IR+CS profile use with ThinLTO → optional BOLT. IR-PGO and
CSPGO are complementary stages; the IR-only optimized build is a comparison
control. [Published Pi results](../results/c1_cspgo_20261006/README.md) include
both the compiler gain and the optional BOLT shifted-input regression.

Frontend PGO and IR-PGO are two instrumentation implementations of PGO, not
the same collection mode. Frontend collection uses `-fprofile-instr-generate`
and favors source correlation; IR collection uses `-fprofile-generate` and is
the baseline for this performance flow. CS collection uses
`-fprofile-use=<ordinary IR profile> -fcs-profile-generate` in a separate build
after inlining. Ordinary and CS generation flags cannot be enabled together
in one build, although their profiles are merged and used together. Both
`-fprofile-use` and `-fprofile-instr-use` can accept indexed frontend or IR
profiles; choosing a flag alone does not prove the profile kind. Our scripts
inspect the actual profile levels. See the
[Clang instrumentation documentation](https://clang.llvm.org/docs/UsersManual.html#profiling-with-instrumentation).

Do not treat frontend-PGO → IR-PGO as another supported cumulative stage.
The pinned compiler rejects frontend profile use plus ordinary IR generation
(`-fprofile-instr-use=... -fprofile-generate`). Keep frontend PGO as a separate
comparison/coverage route; the main performance flow uses IR+CS counts. Mixing
record sets from different instrumentation schemes is not evidence that their
feedback is meaningfully combined. The C1 [probe](../results/c1_cspgo_20261006/frontend-ir-probe.json)
records this driver refusal and a historical frontend/IR merge accepted by
the pinned profdata tool; that merged file was not used for any build or Pi
claim. Format acceptance alone does not validate instrumentation semantics.

## Two training rounds

| Variant | Compile | Direct ld.lld link | Purpose |
|---|---|---|---|
| `irpgo-collect` | `-fprofile-generate -flto=thin -mllvm -disable-vp` | `--mllvm=-disable-vp` | Collect ordinary IR counters on the Pi |
| `irpgo_thinlto` | `-fprofile-use=ir.profdata -flto=thin` | `--lto-cs-profile-file=ir.profdata` | Ordinary IR-PGO + ThinLTO comparison image; profile has no CS records |
| `cspgo-collect` | `-fprofile-use=ir.profdata -fcs-profile-generate -flto=thin -mllvm -disable-vp` | `--lto-cs-profile-generate --lto-cs-profile-file=default.profraw --mllvm=-disable-vp` | Collect CS counters after ThinLTO inlining, using ordinary PGO to guide the earlier passes |
| `cspgo_thinlto` | `-fprofile-use=merged.profdata -flto=thin` | `--lto-cs-profile-file=merged.profdata` | Apply ordinary + post-inline CS counts |

The final profile merges **both** rounds. `scripts/pgo_profile.py` checks the
instrumentation level and trained counts, rejects frontend profiles where IR
is required, requires a CS-free ordinary baseline, and requires both ordinary
and CS records in the final merged profile. It uses the same pinned
`llvm-profdata` as the compiler; do not reuse historical frontend profiles as
IR profiles. Format checks do not establish image identity by themselves.

The LLVM filename `default.profraw` in the CS link flags is metadata, not a
target filesystem destination. The bare-metal runtime writes counters into
RAM with `__llvm_profile_write_buffer`; UART `bolt_dump` retrieves them.
`pi4_pgo_collect.py` checks the announced range on both boots, footer,
sequence/offset/length, chunk checksums, completeness and image stability.
Its optional fresh `--log-dir` retains both boot logs and the collection
image/profile SHA-256 association.

## Reproduce on Windows + WSL + Pi

Read [HANDOFF](../HANDOFF.md), claim the item and publish the live-tree lock
and board-wide Pi reservation before using either resource. Use an isolated
Linux repo/LK tree synced to this checkout. Preserve the shared dirty LLVM
source and existing builds; **do not run the old WSL sync helper against them**.
`build-lk-aarch32.sh` now installs only LK overlays and does not apply LLVM
patches. A pinned existing compiler/runtime can be read from another tree.

Run from the Windows checkout with Python/pyserial:

```powershell
py -3.12 scripts/pi4/cspgo_cycle_wsl.py `
  --wsl-root /home/user/bolt-cspgo `
  --toolchain /home/user/bolt-aarch32/build-atfe/bin `
  --pgo-rt /home/user/bolt-aarch32/build-atfe/pgo-rt-baremetal-arm/libpgo_rt_baremetal.a `
  --out out/my-fresh-cspgo-run `
  --make-args "STAIR_M=8" --rounds 3 --runs 2
```

The script rejects an existing output directory, compares normalized LK
overlay/build-source hashes against WSL, uses one configuration in all four
builds, checks every ELF for FPU/NEON, trains sequential `stair` variant 0 in
both rounds, merges profiles and measures the two final images on variants
0/1/2. Variant 1 changes the seed; variant 2 changes the active sites.
Measurements interleave images over rounds and require matching result
checksums within each variant. Watchdog 120 seconds is armed for every Pi
boot's commands and disarmed by the runner after completion.

Outputs include all four `.elf`/`.bin` images, build and no-FPU logs, raw and
indexed profiles, training logs, every measurement's uploaded image and
serial log, CSVs, tool/runtime/source hashes and `manifest.json`. A failure
keeps its evidence and exits nonzero; it does not publish a PASS manifest.
The receipt establishes association and output consistency, not independent
algorithmic correctness. No oracle contract is derived from these outputs.

## Manual build controls

From a Linux checkout with a pinned compiler/runtime:

```bash
export BASE=atfe CLANG_BINDIR=/path/to/pinned/bin
export PGO_RT_LIB=/path/to/libpgo_rt_baremetal.a
export LK_MAKE_ARGS='STAIR_M=8'
export VARIANTS_DIR=/path/to/fresh/variants
export IR_PROFDATA=/path/to/ir.profdata
export CS_PROFDATA=/path/to/merged.profdata

scripts/build-variants.sh irpgo-collect
# Collect on Pi, then llvm-profdata merge ir.profraw -o "$IR_PROFDATA".
scripts/build-variants.sh irpgo_thinlto cspgo-collect
# Collect CS on Pi, then index cs.profraw into cs.profdata.
python3 scripts/pgo_profile.py merge "$CS_PROFDATA" \
  --ir "$IR_PROFDATA" --cs /path/to/cs.profdata \
  --profdata "$CLANG_BINDIR/llvm-profdata"
scripts/build-variants.sh cspgo_thinlto
```

The low-level make controls are `BOLT_PGO_KIND=frontend|ir`,
`WITH_BOLT_PGO=true` (ordinary collection), `WITH_BOLT_PGO_USE=<profile>`,
`WITH_BOLT_CSPGO=true` (CS collection), and `WITH_BOLT_THINLTO=true`.
CS collection requires ordinary IR profile use and ThinLTO, and cannot be
combined with ordinary collection. Named builds clear inherited stage flags.
Frontend variant names `pgo-collect`, `pgo`, and `pgo_thinlto` remain available.
Profile mismatch warnings are retained rather than globally suppressed.

Without a variant argument, `build-variants.sh` builds `cspgo_thinlto` and
requires trained ordinary+CS counts in `CS_PROFDATA`; it never silently falls
back to IR-only or frontend PGO. Windows Git Bash's `pgo_cycle_wsl.sh` defaults
to the same two-round Python workflow and CLI options. Use its explicit
`--frontend` switch only to replay the historical frontend cycle; old staged
comparison/sweep scripts select that switch to preserve their result labels.

## Scope and limitations

- `-mfpu=none` remains mandatory. Value profiling is disabled because the
  bare-metal runtime excludes its allocation-dependent implementation.
  Indirect-call target and memop-size profiles are therefore absent; this
  route does not enable their corresponding promotion/specialization gains.
- Compiler counters use non-atomic updates. The supported training commands
  run sequentially on one workload thread, even if LK has idle SMP cores.
  Concurrent/SMP/FIQ workload training is unsupported. The all-core IRQ
  sampling hook is excluded from compiler profiling, and the dump rejects
  active PC sampling and masks local IRQs while serializing counters.
- CS collection uses a default 1 MiB RAM dump buffer (legacy frontend uses
  64 KiB). `BOLT_PGO_BUFFER_SIZE=<decimal bytes>` can change it; the runtime
  checks the required size before writing and fails instead of truncating.
  Larger kernels can require a larger buffer. Instrumented timing is not
  the optimized program's performance.
- `stair` exposes opposite branch biases at different inline sites, but is
  synthetic. Sweep `STAIR_M`/`STAIR_X` around the instruction-cache boundary
  and use representative application workloads before generalizing a gain.
  No Cortex-A55 performance conclusion follows from Pi Cortex-A72 results.
- CSPGO can improve opportunities previously handled by BOLT, so BOLT's
  incremental gain may shrink. To compare both pipelines with BOLT, collect
  and seal a **fresh BOLT profile for each final ELF**, then follow the
  [profile identity contract](PI_PROFILE_IDENTITY.md). Compiler `.profdata`
  is not BOLT `.fdata`. Existing sampling/suite follow-ups remain in HANDOFF.
- BOLT's AArch32 exact-counter instrumentation currently refuses conditional
  returns (0036). The C1 CSPGO `stair` output triggers that guard. This is an
  instruction-shape limitation of the present instrumentation implementation,
  not a conflict between CSPGO and BOLT. PC sampling can profile the unchanged
  compiler output; R35 in HANDOFF tracks safe counter support.

## Optional BOLT comparison on these compiler outputs

`scripts/cspgo-bolt.sh` prepares one sealed sampling input per compiler ELF and
optimizes only `bolt_bench_stair_kernel`. It computes the admission skip list
from each full image's coverage report, requires bound PC profiles and checks
the rewritten output for FPU/NEON. It redirects the original kernel entry to
the rewritten copy; the rest of LK stays original in this comparison.

In WSL, using a fresh BOLT directory and the compiler cycle's output:

```bash
export TOOLCHAIN=/path/to/pinned/bin
bash scripts/cspgo-bolt.sh prepare /path/to/fresh/bolt-output /path/to/compiler-output
```

Copy the two `.elf`, `.bin` and `.bin.manifest.json` inputs to Windows. For
**each** of `irpgo_thinlto` and `cspgo_thinlto`, collect from its exact binary:

```powershell
# Set PI4_FAST_LOADER to the repository's kernel7l_fast.img first.
py -3.12 scripts/pi4/pi4_sample_profile.py cspgo_thinlto.bin cspgo_thinlto.samples `
  --elf cspgo_thinlto.elf --workload "stair 0 0" --period 20000 --repeat 32
```

Copy each accepted `.samples` and `.samples.manifest.json` back to the BOLT
directory, then run separately for the two compiler variants:

```bash
bash scripts/cspgo-bolt.sh optimize /path/to/bolt-output irpgo_thinlto
bash scripts/cspgo-bolt.sh optimize /path/to/bolt-output cspgo_thinlto
```

Use `pi4_compare.py --workload stair` to interleave all four final images. Keep
training variant 0 and measure variants 0/1/2 separately. Sampling collection
runs with the workload's IRQ masking disabled, to expose its PCs; timed runs
use their normal IRQ masking with the sampler stopped. PC frequencies do not
provide exact branch-edge counts. The conditional-return counter rejection
and the sampling approximation must accompany these results.

LLVM mechanisms: [Clang PGO options](https://clang.llvm.org/docs/UsersManual.html#cmdoption-fcs-profile-generate).
