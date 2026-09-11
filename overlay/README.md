# Overlay patches

Incremental changes on top of upstream — **not forks**.

```
overlay/
├── llvm/patches/     # bolt/runtime, bolt/lib (AArch32 backend slices)
└── lk/patches/       # linker script, bolt_bench app, profile dump
```

Apply with `scripts/apply-overlays.sh`, which runs `git apply` inside each
`third_party/` checkout. One patch per logical change.

**When a patch lands in llvm-project, delete it here.** The overlay should shrink
over the life of the project.

The planned patch list lives in [docs/PROJECT_PLAN.md](../docs/PROJECT_PLAN.md);
what each layer is responsible for is in [docs/architecture.md](../docs/architecture.md).
