# Frontend PGO, ThinLTO and BOLT

Frontend instrumentation PGO is an explicit alternative to the default
IR-PGO/CSPGO route. Its sequence is **FE collection → FE profile use with
ThinLTO → optional sampled or instrumented BOLT**. It does not consume the
IR/CSPGO profile. The [route matrix](CSPGO_PIPELINE.md#two-compiler-paths-two-bolt-profile-modes)
and [C3 evidence](../results/c3_frontend_pgo_20261006/README.md) distinguish
freshly verified scope from historical results.

C3 runs this route with overlays 0001–0073, a fresh LK checkout at
`79d2f56096fa32365846ceaba8b4a9d1c6b75cf0`, `STAIR_M=8` and Thumb workload
code. Compiler profiling/ThinLTO cover `app/bolt_bench`, not all LK. BOLT
rewrites only `bolt_bench_stair_kernel`. Training is sequential on input 0;
timings also cover inputs 1 and 2. Hardware is the Pi 4B A72 in AArch32
Non-secure SVC, no FPU/NEON. This establishes a pipeline and scoped output/
execution checks, not a new whole-image oracle or Cortex-A55 certificate.

## Fresh frontend cycle

First claim work and acquire the live-tree lock and Pi reservation in
[HANDOFF](../HANDOFF.md). Use a fresh isolated repository/LK tree; keep old
builds and profiles. Never reapply overlays to the shared dirty LLVM tree.
Verify its full overlay replay and record tool/runtime hashes. The historical
Windows Git Bash launcher `pgo_cycle_wsl.sh --frontend` remains available;
C3 uses the following low-level stages in an isolated checkout, avoiding its
shared-tree synchronization and fixed output locations.

In the isolated WSL checkout, select explicit frontend variants:

```bash
export BASE=atfe LK_PROJECT=rpi4-bolt-test LK_MAKE_ARGS=STAIR_M=8
export BOLT_BENCH_ISA=thumb JOBS=8
export CLANG_BINDIR=/path/to/pinned/build-atfe/bin
export TOOLCHAIN="$CLANG_BINDIR"
export PGO_RT_LIB=/path/to/pgo-rt-baremetal-arm/libpgo_rt_baremetal.a
export VARIANTS_DIR=/path/to/fresh/frontend-output
export PROFDATA="$VARIANTS_DIR/frontend.profdata"
bash scripts/build-variants.sh baseline pgo-collect
```

These variants choose `BOLT_PGO_KIND=frontend`. Copy the training ELF/image
and no-FPU log to Windows and collect a fresh profile:

```powershell
$env:PI4_WDOG='180'
$env:PI4_FAST_LOADER='/path/to/tools/pi4-serialboot-fast/kernel7l_fast.img'
py -3.12 scripts/pi4/pi4_pgo_collect.py pgo-collect.bin frontend.profraw `
  --workload stair --log-dir /path/to/fresh/training-logs --port COM5
```

The collector boots twice, checks complete dump framing/CRC, requires matching
training results and binds the image/profile hashes. Keep both serial logs
and `collection.json`. Source, ELF, compiler/runtime and build identities are
separate evidence and must also be retained. Counter training does not prove
an algorithmic result by itself.

Copy the raw profile back to `$VARIANTS_DIR`, then in WSL:

```bash
"$TOOLCHAIN/llvm-profdata" merge "$VARIANTS_DIR/frontend.profraw" -o "$PROFDATA"
python3 scripts/pgo_profile.py validate "$PROFDATA" --kind frontend \
  --profdata "$TOOLCHAIN/llvm-profdata"
bash scripts/build-variants.sh pgo pgo_thinlto
```

Validation must show **Front-end** instrumentation and nonzero training
counts. Keep final build/no-FPU logs, the module configuration showing
`-fprofile-instr-use`, and the ThinLTO module's bitcode identity. C3 records
these along with every source and generated compiler artifact's hash.

## Both BOLT profile modes

Use two fresh BOLT directories, each containing the same final
`pgo_thinlto.{elf,bin}`. The profile must bind that exact ELF. Compiler
`.profdata` cannot replace BOLT `.fdata`.

For **instrumented BOLT**, use the
[sealed counter recipe](CSPGO_PIPELINE.md#exact-counter-alternative-0073-and-later)
with variant name **`pgo_thinlto`** instead of `cspgo_thinlto`. Set
`BOLT_FUNC=bolt_bench_stair_kernel`, edge mode, the runtime contract and the
exact successful source replay. Seal after redirection and binary generation,
collect `stair 0 0`, separately validate the command frame/checksum and full
counter flow, then optimize the original frontend ELF with the accepted dump.
Unsupported predication shapes retain their refusal guards (R36).

For **sampled BOLT**, first seal in WSL:

```bash
python3 scripts/profile_identity.py seal-samples --elf pgo_thinlto.elf \
  --image pgo_thinlto.bin --toolchain "$TOOLCHAIN" \
  --patch-dir overlay/llvm/patches/atfe
```

Copy the ELF/image and image manifest to Windows:

```powershell
py -3.12 scripts/pi4/pi4_sample_profile.py pgo_thinlto.bin stair0.samples `
  --elf pgo_thinlto.elf --workload "stair 0 0" --period 20000 --repeat 32 --port COM5
```

Retain the accepted samples, capture manifest and complete serial log. Copy
them back to WSL. Generate an admission report on the exact frontend ELF
using `lk_coverage_report.py`, obtain its `skip_funcs`, then convert and optimize:

```bash
python3 scripts/samples_to_fdata.py pgo_thinlto.elf stair0.samples \
  -o pgo_thinlto.samples.fdata --toolchain "$TOOLCHAIN" \
  --functions bolt_bench_stair_kernel --skip-funcs "$SKIP"
export BOLT_FUNC=bolt_bench_stair_kernel
export BOLT_FDATA=/absolute/path/to/pgo_thinlto.samples.fdata
bash scripts/bolt-variant.sh optimize pgo_thinlto
```

Use a separate source `.samples.fdata` filename: the optimizer copies it to
`$VARIANTS_DIR/pgo_thinlto.fdata`. `VARIANTS_DIR` and `TOOLCHAIN` must identify
this BOLT directory and the same sealed tools. Scan both optimized outputs
for FPU/NEON, compare all 18 workload results and observe PCs inside each
mapped rewritten body before claiming its execution. Assertion-mode parity
compares load binaries and ELFs excluding command-line `.note.bolt_info` only.

Timing runs stop profiling and use the workload's normal IRQ masking.
`pi4_compare.py --workload stair --args "0 INPUT"` interleaves FE+ThinLTO,
counter-BOLT and sampled-BOLT images; measure inputs 0/1/2 separately and
retain every complete metric/checksum record. PC sampling infers edges and
misses IRQ-masked execution; counters change training execution. Neither mode
guarantees a speedup. These are scoped Pi A72 synthetic-workload measurements.
