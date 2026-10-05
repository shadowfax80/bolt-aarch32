# bolt-aarch32

An **AArch32 (A32 + Thumb-2) backend for LLVM BOLT**, built and verified on a
bare-metal [Little Kernel](https://github.com/littlekernel/lk) image. The
product target is a Cortex-A55 in AArch32 Non-secure SVC mode (SMP, no FPU/NEON).
The proof-of-concept hardware is a Raspberry Pi 4B running in the same state.

Upstream LLVM and LK are not forked: the backend is an overlay series on a
pinned [Arm Toolchain for Embedded (ATFE)](https://github.com/arm/arm-toolchain)
LLVM commit, and the LK changes are overlays too.

## Status (2026-10-05)

| | |
|---|---|
| Backend | Overlays `overlay/llvm/patches/atfe/0001–0069`, ARM lit 58/58 with assertions on and off |
| Full LK image | 401/417 functions rewritten, 99.5% of code bytes; the rest are vectors, startup and real fall-through code |
| Hardware | Certified Pi gates on ARMv7, Cortex-A55-built and SMP images (Non-secure SVC) |
| Open | P1 certification matrices; real A55 validation (user) |

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
