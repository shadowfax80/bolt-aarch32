# Fixtures

| File | sha256 | Use |
|---|---|---|
| `lk-rpi4-bolt-edge-439dfd7c.elf` | `439dfd7c8dc660b1b4b8d4bae967750fe87485647460c791e2b7e385304e7bb9` | R17 stage 1b: 98 cases, adds whole-module `-marm`/`-mthumb` C builds (O2/Os/O0). Manifest: `docs/bolt_edge/manifest.json`. No contract yet (needs user review). |
| `lk-rpi4-bolt-edge-0895d7bc.elf` | `0895d7bc1b0dcaa7b60869fd0e3182b6c8cb9a32aebb742c6e5336dd468208dd` | R17 stage-1 edge-case image: `rpi4-bolt-edge` project (bolt_bench + generated `app/bolt_edge`, `scripts/bolt_edge/gen.py`). Expected sinks: `docs/bolt_edge/stage1/manifest.json` (frozen). Approved `pi4` contract. |
| `lk-rpi4-bolt-test-424606a8.elf` | `424606a869c34b5be5f3c97f66a9cec8ea16844ac788c14c77839edcfef2459b` | Full LK test binary for the Pi (`rpi4-bolt-test`). Input of the approved `pi4` oracle contract (`scripts/qemu_bench_oracle.py`), the coverage report (`docs/LK_COVERAGE.md`) and the certified full-image runs. |

Build provenance: LK project `rpi4-bolt-test` (ARM_CPU_CORTEX_A15, Thumb-2
kernel) with the bolt_bench overlay from `overlay/lk/files/app/bolt_bench/`
(content-identical at the time of approval), `-marm` module, `WITH_BOLT_PGO`
off, `STAIR_M=10`, `STAIR_X=0`, no FPU/NEON. A rebuild is not guaranteed to be
bit-identical, so this copy is the reference; certify only against its hash.
The original lives in WSL at
`/home/user/bolt-aarch32/out/correctness/lk-oracles/build-rpi4-bolt-test/lk.elf`.
