# Isolated ATFE source replay

Use `verify-atfe-overlays.py` to compare the complete ATFE patch series against
live source without changing the checkout. Use a fresh output directory:

```sh
python3 scripts/verify-atfe-overlays.py \
  --source /home/user/bolt-aarch32/third_party/llvm-project-atfe \
  --patch-dir overlay/llvm/patches/atfe --out out/atfe-replay
```

The verifier exports patch-touched files from the pinned ATFE commit into an
isolated Git directory, applies every patch in order, and compares the resulting
bytes with the live tree. It rejects additional uncovered source changes, changed
patch contents or live source mutations during verification. It preserves all
replayed files and `replay.json`; an existing output directory is never overwritten.
The two known untracked source-bookkeeping markers are excluded from the source
change set, and their contents do not establish verification.

This verifies a pinned base plus patch source contents. It does not perform a clean
full build, compare POSIX file modes across Windows/WSL, or prove an existing binary
was built from those sources. Successful replay is a prerequisite for replacing
legacy filename-only patch stamps with content identity, not proof supplied by
those legacy stamps.

The 2026-10-02 replay applied all 24 patches, found no uncovered source files and
preserved the dirty WSL checkout. It failed source equality in four files:

- `bolt/include/bolt/Rewrite/RewriteInstance.h`
- `bolt/lib/Core/BinaryContext.cpp`
- `bolt/lib/Core/BinaryFunction.cpp`
- `bolt/lib/Rewrite/RewriteInstance.cpp`

Live code includes ARM build-attribute feature propagation and kept-function/
branch handling for `-use-old-text` that is absent from the GitHub overlay series.
The diff is preserved in `out/correctness/atfe-clean-replay-20261002/unexported-source.diff`.
It requires review, focused regressions and export; it has not been overwritten or
published as a verified backend fix. The source-replay/content-stamp task remains
open. See [compact evidence](results/correctness_atfe_replay_20261002.json).
