# Fixtures

| File | sha256 | Use |
|---|---|---|
| `lk-rpi4-bolt-test-a55-smp-e1139981.elf` | `e11399812fca296875435dd2cc9effe5f6405ee11c5b94d2106fc8ae4f830b02` | T2: A55-built full LK with `bolt_bench smp` and `bolt_sample watch`. Approved `pi4` contract (smp); certified (SMP + standard gates). |
| `lk-rpi4-bolt-test-a55-47c73bc0.elf` | `47c73bc08b71f37aa90c4f601305954d860a38abd985d583e7100511dafa5a33` | T1: full LK test image built for the target core (`make rpi4-bolt-test RPI4_ARM_CPU=cortex-a55`, ARMv8-A AArch32, `-mfpu=none`, LK patch 0011). Approved `pi4` contract; certified. |
| `lk-rpi4-bolt-edge-ce8dd005.elf` | `ce8dd005d78de4eb1a627d7b69f77d0f699738baefdf9fecc3d2d11a8050f9f6` | R17 stage 2: 146 cases, adds 48 seeded random A32/T32 functions (`scripts/bolt_edge/rand.py`, seed 17). Expected sinks: `docs/bolt_edge/stage2/manifest.json` (frozen). Approved `pi4` contract. |
| `lk-rpi4-bolt-edge-439dfd7c.elf` | `439dfd7c8dc660b1b4b8d4bae967750fe87485647460c791e2b7e385304e7bb9` | R17 stage 1b: 98 cases, adds whole-module `-marm`/`-mthumb` C builds (O2/Os/O0). Expected sinks: `docs/bolt_edge/stage1b/manifest.json` (frozen). Approved `pi4` contract. |
| `lk-rpi4-bolt-edge-0895d7bc.elf` | `0895d7bc1b0dcaa7b60869fd0e3182b6c8cb9a32aebb742c6e5336dd468208dd` | R17 stage-1 edge-case image: `rpi4-bolt-edge` project (bolt_bench + generated `app/bolt_edge`, `scripts/bolt_edge/gen.py`). Expected sinks: `docs/bolt_edge/stage1/manifest.json` (frozen). Approved `pi4` contract. |
| `lk-rpi4-bolt-test-424606a8.elf` | `424606a869c34b5be5f3c97f66a9cec8ea16844ac788c14c77839edcfef2459b` | Full LK test binary for the Pi (`rpi4-bolt-test`). Input of the approved `pi4` oracle contract (`scripts/qemu_bench_oracle.py`), the coverage report (`docs/LK_COVERAGE.md`) and the certified full-image runs. |

Build provenance: LK project `rpi4-bolt-test` (ARM_CPU_CORTEX_A15, Thumb-2
kernel) with the bolt_bench overlay from `overlay/lk/files/app/bolt_bench/`
(content-identical at the time of approval), `-marm` module, `WITH_BOLT_PGO`
off, `STAIR_M=10`, `STAIR_X=0`, no FPU/NEON. A rebuild is not guaranteed to be
bit-identical, so this copy is the reference; certify only against its hash.
The original lives in WSL at
`/home/user/bolt-aarch32/out/correctness/lk-oracles/build-rpi4-bolt-test/lk.elf`.
