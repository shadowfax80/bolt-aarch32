# Overlay patches

Incremental changes on top of upstream — **not forks**. Applied with `scripts/apply-overlays.sh`.

```
overlay/
├── llvm/patches/     # bolt/runtime, bolt/lib (AArch32 backend slices)
└── lk/patches/       # linker script, bolt_bench app, profile dump
```

## Expected patches

| Patch (planned) | Upstream path | Purpose |
|-----------------|---------------|---------|
| `bolt-rt-baremetal.patch` | `bolt/runtime/` | RAM profile; no syscalls |
| `linker-bolt-profile.patch` | LK linker script | `.bolt_profile` section |
| `app-bolt-bench.patch` | LK `app/` | Workload benchmarks |
| `aarch32-*.patch` | `bolt/` | AArch32 backend (until merged to LLVM) |

When a patch lands in llvm-project, **remove it here**.

See [docs/architecture.md](../docs/architecture.md).
