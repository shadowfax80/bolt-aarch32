# Overlay patches

This directory holds **only our changes** on top of upstream `llvm-project` and `lk`.
Upstream sources live in `third_party/` as git submodules (pinned commits).

## Layout

```
overlay/
├── llvm/patches/     # Patches applied to llvm-project (bolt-rt, instrumentation, etc.)
└── lk/patches/       # Patches applied to LK (linker script, RAM profile dump hook)
```

## Applying overlays

From the repo root:

```bash
./scripts/apply-overlays.sh
```

Patches are applied with `git apply` from inside each submodule checkout.
After updating a submodule (`git submodule update --remote`), re-run apply-overlays
and resolve any conflicts.

## What we expect to overlay

### LLVM / BOLT (`overlay/llvm/patches/`)

- Bare-metal instrumentation runtime: profile counters in RAM instead of `/tmp/prof.fdata`
- Optional: `--no-lse-atomics` defaults for QEMU `cortex-a53` targets

### LK (`overlay/lk/patches/`)

- Linker script: dedicated `.bolt.instr` (or similar) section in DRAM
- Small hook to dump counter region over serial or for QEMU `dump-guest-memory`
- Build flags: `--emit-relocs`, Clang/LLD cross-compile for `aarch64-unknown-elf`

Patches are added incrementally as the AArch64 PoC progresses. Empty until first change lands.
