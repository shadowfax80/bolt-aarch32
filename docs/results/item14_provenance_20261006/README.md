# Item 14: clean build and content provenance (2026-10-06)

Closure criteria ([history](../../history/CORRECTNESS_PRIORITY_TODO_0045_HISTORY.md)):
isolate a clean full build of the assessed overlays, bind exact
source/config/tools, compare both modes, audit export/modes, and preserve the
live dirty ATFE/LK trees. Receipt: [`provenance.json`](provenance.json)
(`scripts/build_provenance.py`, repository 056bf19). **PASS**, all checks.

## How

1. `scripts/clean-build-atfe.sh /home/user/bolt-clean on off`:
   - fetches pin `bcc08884` from `github.com/arm/arm-toolchain` into a fresh
     tree and applies `overlay/llvm/patches/atfe/0001–0072` (series sha256
     `9ee52ea9…`);
   - configures from `cmake/llvm-bolt.cmake` with clang/clang++. The only
     mode override is `LLVM_ENABLE_ASSERTIONS=OFF`; ccache is bypassed;
   - builds clang, lld, BOLT, the binutils and the lit dependencies, plus
     the bare-metal ARM BOLT runtime, from scratch (4,043 steps per mode).
2. `scripts/build_provenance.py` compares the clean builds with the live
   `build-atfe` (ON) and `build-atfe-noassert` (OFF).

## Results

| Check | Result |
|---|---|
| Bound paths (overlays, cmake, scripts) unmodified at 056bf19 | ok |
| Clean HEAD is the pin | ok |
| Source: clean vs live, 184,669 paths | contents identical. The tree hashes differ only in the mode bits of 25 test inputs, which are executable in the live tree; file-slice patches cannot carry modes |
| Live tree untouched | live tree hash taken in a temporary index |
| Clean ON vs OFF configuration | differ only in `LLVM_ENABLE_ASSERTIONS` and the derived `LLVM_ENABLE_IO_SANDBOX` |
| Clean ON vs live ON configuration | identical (normalised CMake cache) |
| ARM BOLT lit, all four builds | 61/61 each |
| Tools | clean OFF `llvm-bolt`, `ld.lld`, `llvm-objcopy` byte-identical to live OFF. ON builds differ (assertion messages embed source paths) |
| Bare-metal runtime object | identical in all builds (`976dd014…`) |

### Output parity on the certified LK input (`424606a8`)

Each job ran with all four builds, plus a second time with clean ON. Outputs
are compared without `.note.bolt_info`, which records the llvm-bolt path and
command line; raw hashes are in the receipt.

| Job | Identical across builds | Deterministic | no-FPU guard |
|---|---|---|---|
| G1 full image (ext-tsp, hfsort+, ICF, 2 redirects) | yes; `.bin` `2181dffe…` = certified G1 | yes | ok |
| Instrumentation, `privileged-smp-no-fiq` (0060) | yes | yes | ok |
| Instrumentation, `privileged-single-core-no-fiq` | yes | yes | ok |
| Random split + reverse blocks + ICF (LongJmp, 0061) | yes | yes | ok |

This establishes OFF parity for 0060 and 0061, and for the whole series, on
these jobs: assertions change neither code nor layout.

## Found and fixed on the way

- **R30 (0072):** the no-FPU guard's 1,943 false hits on the G1 output were
  wrong BOLT mapping symbols. See [R30](../r30_20261006/README.md).
- **0072 nondeterminism:** the first parity run showed the instrumented and
  split outputs differing even run to run. Stub marks were emitted in
  JITLink's pointer-hash order; they are now sorted. The determinism check
  stays in the tool.
- **Guard:** `check-no-fpu.sh` now refuses files whose mapping symbols do not
  give each function its ISA, rather than decoding them anyway. It is POSIX
  awk; addresses are compared as strings, since `800e6600` is a number to
  awk.

## Audit findings (recorded, not changed)

- `cmake/llvm-bolt.cmake` does not choose the host compiler; the live builds
  got clang from the environment. The first clean attempt silently used GCC.
  `clean-build-atfe.sh` now names clang/clang++.
- Live OFF (`build-atfe-noassert`) was configured outside the shared cache:
  `LLVM_ENABLE_PROJECTS=bolt;lld` (no clang project; its `bin/clang` is from
  an earlier configuration). Its BOLT tools are still byte-identical to the
  clean OFF build.
- The ARM lit tests need the bare-metal runtime, which no CMake target
  builds; `clean-build-atfe.sh` builds it.
