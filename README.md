# bolt-aarch32

An **AArch32 (A32 + Thumb-2) backend for LLVM BOLT**, built and verified on a
bare-metal [Little Kernel](https://github.com/littlekernel/lk) image. The
product target is a Cortex-A55 in AArch32 Non-secure SVC mode (SMP, no FPU/NEON).
The proof-of-concept hardware is a Raspberry Pi 4B running in the same state.

Upstream LLVM and LK are not forked: the backend is an overlay series on a
pinned [Arm Toolchain for Embedded (ATFE)](https://github.com/arm/arm-toolchain)
LLVM commit, and the LK changes are overlays too.

## Status (2026-10-06)

| | |
|---|---|
| Backend | Overlays `overlay/llvm/patches/atfe/0001–0072`, ARM lit 61/61 with assertions on and off |
| Full LK image | 401/417 functions rewritten, 99.5% of code bytes; the rest are vectors, startup and real fall-through code |
| Hardware | Certified Pi gates on ARMv7, Cortex-A55-built and SMP images (Non-secure SVC) |
| Compiler flow | Ordinary IR-PGO → ThinLTO-guided CSPGO training → merged IR+CS profile use with ThinLTO → optional BOLT |
| Open | Shared handoff follow-ups and P1 certification matrices; real A55 validation (user) |

Live status, ownership and the work queue: **[docs/HANDOFF.md](docs/HANDOFF.md)**.

## Documentation

- [Architecture and design](docs/AARCH32_BACKEND_ARCHITECTURE.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Build in WSL2 and run on the Pi](docs/WSL_BUILD.md)
- [Documentation map](docs/README.md): verification contracts, reviews, upstreaming, history

## Quick start

Builds run in WSL2 (Ubuntu); hardware runs use the Pi on COM5. In a shared
checkout, publish the HANDOFF claim, live-tree lock and Pi reservation first,
and never re-apply overlays to an existing live tree.

```bash
# Fresh setup, from the Windows checkout
wsl -d Ubuntu -u root -- bash scripts/wsl-setup.sh deps
wsl -d Ubuntu          -- bash scripts/wsl-setup.sh build     # ~1 h: ATFE clang/lld/BOLT + runtimes

# Check that the live tree equals the overlay series
python3 scripts/verify-atfe-overlays.py --source third_party/llvm-project-atfe \
  --patch-dir overlay/llvm/patches/atfe --out <fresh dir>

# Coverage of the certified LK image
python3 scripts/lk_coverage_report.py --elf fixtures/lk-rpi4-bolt-test-424606a8.elf \
  --toolchain build-atfe/bin --out <fresh dir>

# Certified Pi gate (build in WSL, verify from Windows Python with pyserial)
python3 scripts/pi4/full_image_build.py out/cand --input fixtures/lk-rpi4-bolt-test-424606a8.elf \
  --toolchain build-atfe/bin --redirect-functions bolt_bench_interwork,bolt_bench_memcpy -- -skip-funcs=...
py -3.12 scripts/pi4/full_image_verify.py out/cand --require-executed bolt_bench_interwork,bolt_bench_memcpy \
  --repeat 10 --port COM5 --fast-loader tools/pi4-serialboot-fast/kernel7l_fast.img
```

The `-skip-funcs` list for the certified image is in
`docs/results/lk_coverage_r15_20261004.json`. QEMU routes are for debugging
only; the Pi is the certifying target.

## Main compiler optimization flow

Two compiler paths are available; each can feed either BOLT profile mode:

| Compiler path | BOLT profile choice |
|---|---|
| FE-PGO + ThinLTO (explicit alternate) | Sampled or instrumented |
| IR-PGO + ThinLTO + CSPGO (default) | Sampled or instrumented, subject to backend admission |

Sampled BOLT collects execution observations; instrumented BOLT collects
counter feedback from a temporary training binary. Both optimize the original
compiler ELF with a fresh bound BOLT profile. The current CSPGO stair binary
is sampled successfully but refuses counter instrumentation for conditional
returns (R35). See the [route/status matrix](docs/verification/CSPGO_PIPELINE.md#two-compiler-paths-two-bolt-profile-modes).

IR-PGO and CSPGO complement each other. Ordinary IR counts guide earlier
optimization and ThinLTO inlining; a second training build collects counts
after inlining. The final build consumes **both** levels from a merged profile.
With a synced isolated WSL/LK checkout and published resource reservations:

```powershell
py -3.12 scripts/pi4/cspgo_cycle_wsl.py --wsl-root /home/user/bolt-cspgo `
  --out out/my-fresh-pgo-run --make-args "STAIR_M=8"
```

The final compiler image is `cspgo_thinlto`; the IR-only image is a comparison
control. `build-variants.sh` with no variant defaults to this final build and
requires its merged profile. In Windows Git Bash, `pgo_cycle_wsl.sh` also
defaults to this two-round flow with the same CLI options. Historical
frontend-PGO variants remain explicitly selectable; its old cycle requires
`--frontend`.

See the [recipe](docs/verification/CSPGO_PIPELINE.md) and
[Pi evidence](docs/results/c1_cspgo_20261006/README.md). Optional BOLT needs a
fresh profile bound to the final ELF. Current conditional-return counter
support is tracked as R35; sealed PC sampling works. Measure its incremental
benefit: on this workload BOLT after CSPGO regressed, including +20.25% cycles
on a shifted input.

## Layout

```
overlay/llvm/patches/atfe/      backend overlay series (current)
overlay/llvm/patches/upstream/  older series for llvm/llvm-project (upstreaming deferred)
overlay/llvm/bolt-rt-baremetal/ bare-metal instrumentation runtime
overlay/lk/                     LK patches and files: Pi 4 port, BOLT window, sampler, bolt_bench
scripts/                        build, coverage, full-image pipeline, Pi/QEMU gates, review probe
fixtures/                       certified input ELFs (hash-indexed in fixtures/README.md)
tools/                          Pi fast serial loader
docs/                           current docs, verification contracts, reviews, history, receipts
third_party/, build-*/          LLVM/LK sources and builds (gitignored, live in WSL)
```

`BASE=atfe` selects the current base in the build scripts (`scripts/resolve-base.sh`);
the generic scripts default to `upstream` when it is unset. This repo absorbed
the former `atfe-bolt-aarch32` repo on 2026-09-15; that repo's pre-merge history
is kept offline as `legacy-archives/atfe-bolt-aarch32-legacy.bundle`.

## License

Overlay scripts and docs: MIT. Upstream LLVM and LK keep their own licenses.
