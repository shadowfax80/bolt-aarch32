# bolt-lk-overlay

Overlay repository for **BOLT on bare-metal Little Kernel (LK)**.

Upstream sources are **not forked** — they are tracked as git submodules and we apply local patches from `overlay/`.

## Upstream dependencies

| Submodule | Repository | Purpose |
|-----------|------------|---------|
| `third_party/llvm-project` | [llvm/llvm-project](https://github.com/llvm/llvm-project) | LLVM, Clang, LLD, BOLT |
| `third_party/lk` | [littlekernel/lk](https://github.com/littlekernel/lk) | Little Kernel OS |

## Project phases

1. **Toolchain** — Build LLVM + Clang + LLD + BOLT (RunPod CPU pod or local Linux)
2. **AArch64 PoC** — LK on QEMU `virt`, BOLT instrumentation, profile counters in RAM (linker script), dump → `.fdata`, re-optimize
3. **AArch32 design** — Step-by-step plan for ARM/Thumb BOLT (interworking, IT blocks, range, veneers)

## Quick start

```bash
# Clone with submodules
git clone --recurse-submodules https://github.com/somraj80/bolt-lk-overlay.git
cd bolt-lk-overlay

# Or init submodules after clone
git submodule update --init --recursive

# Apply overlay patches (when present)
./scripts/apply-overlays.sh

# Build LLVM/BOLT (on Linux)
./scripts/install-deps.sh
./scripts/build-llvm-bolt.sh

# Build LK for QEMU AArch64
./scripts/build-lk-aarch64.sh
```

Copy `.env.example` to `.env` and fill in RunPod/SSH settings if using remote builds.

## Repository layout

```
bolt-lk-overlay/
├── .gitmodules
├── cmake/llvm-bolt.cmake      # Shared LLVM/BOLT CMake cache
├── overlay/
│   ├── llvm/patches/          # Patches on llvm-project
│   └── lk/patches/            # Patches on LK (linker script, RAM dump)
├── scripts/                   # Build, RunPod, QEMU helpers
├── docs/                      # Phase docs and AArch32 design
└── third_party/               # Submodule mount points
    ├── llvm-project/
    └── lk/
```

## License

Overlay scripts and docs: MIT. Upstream LLVM and LK retain their respective licenses.
