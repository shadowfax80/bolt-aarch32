# Isolated ATFE source replay

The fresh 0038 review replay applies all 38 overlays with no uncovered or
mismatched source files and preserves the live dirty tree. Source identity:
`d2e9272859daa806082419c5c9e8522bdc8233693659c81453538e42c31f2b56`.
See [review evidence](results/correctness_0038_review_20261002.json). This updates
source equality only; #12 has been reactivated and clean full-build/binary
provenance is not established. Earlier replay checkpoints below are retained as history.

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
That initial failed audit is retained in
[compact evidence](results/correctness_atfe_replay_20261002.json).

Overlay 0025 exports the reviewed additions and hardens the kept A32 path. The
new linked-ELF regression checks exact emitted UDIV/ERET bytes, ARM/Thumb calls,
predicated BL/B, input BLX H=1 and a late kept caller. Malformed or unaligned A32
relocations, wrong target ISA, hot-at-end, insufficient text and an unmappable
interior reference fail with diagnostics; failed outputs are not published.
The twelve probes and all 37 focused lit tests pass. ERET is host emission
coverage only, and kept-code hardware execution is not claimed.

Overlay 0035 supersedes the historical ERET emission check with explicit
rejection when ELF attributes enable its decoding. Supported ARM/Thumb UDIV
emission checks remain. Exception-return rewriting is unsupported; this change
does not update the older full-series replay or resume #12's provenance work.

The final 2026-10-02 replay applies all 25 patches and reports no mismatched or
uncovered source files. Its evidence is preserved in
`out/correctness/atfe-clean-replay-0025-final-20261002/replay.json`, source identity
`c390d7d0acdd17910df67833227e55ed40898cf2cb229611a2c7326ce12660ed`.
Content-stamp migration and clean full-build provenance remain open under #12.
The replay-verified tool's regular full-image candidate passes the scoped Pi
workload/execution gate. [Compact evidence](results/correctness_atfe_0025_20261002.json)
records source/patch/tool identities, probes, artifact hashes and complete log hashes.
