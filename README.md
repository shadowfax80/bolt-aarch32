# bolt-lk-overlay

Overlay repository for **BOLT on bare-metal Little Kernel (LK)**.

Upstream sources are **not forked** — they are tracked as git submodules and we apply local patches from `overlay/`.

## Upstream dependencies

| Submodule | Repository | Purpose |
|-----------|------------|---------|
| `third_party/llvm-project` | [llvm/llvm-project](https://github.com/llvm/llvm-project) | LLVM, Clang, LLD, BOLT |
| `third_party/lk` | [littlekernel/lk](https://github.com/littlekernel/lk) | Little Kernel OS |

## Project plan

**[docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md)** — step-by-step checklist with current status, RunPod details, and phase breakdown.

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Repo, scripts, RunPod infra | Done |
| 1 | LLVM + Clang + LLD + BOLT toolchain | In progress |
| 2 | AArch64 LK QEMU PoC + in-RAM profiling | Not started |
| 3 | AArch32 BOLT design | Not started |

## Quick start

```bash
# Clone with submodules
git clone --recurse-submodules https://github.com/somraj80/bolt-lk-overlay.git
cd bolt-lk-overlay

# Fetch upstream sources (idempotent — skips if already cloned)
./scripts/init-submodules.sh

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
