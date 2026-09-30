# Correctness fixes

## A32 literal loads (2026-09-30)

The upstream 0008 and ATFE 0014 overlays correct backward literal-load
offsets, subtract-zero decoding, and symbolic MC operands. JITLink now handles
R_ARM_LDR_PC_G0 with signed imm12 range checks while preserving predicate and
register bits. Regression tests cover forward/backward loads, nonzero addends,
ordinary register-based loads, and positive/negative range boundaries.

Validation on the ATFE assertions-enabled Release build:

- BOLT ARM suite passed (13/13 before the separate unwind change).
- LLVM JITLink AArch32 suite passed (13/13).
- Full LK image emission passed, replacing the previous unsupported-fixup errors.
- Postprocessed QEMU image completed four workloads. Postprocessing restores
  original sections, so this does not prove that every rewritten function ran.

The upstream overlay applied cleanly to its pinned base plus patches 0001-0007;
the upstream build has not been tested. The Pi passed baseline serial/upload,
checksum, and benchmark sanity checks, but the modified BOLT output has not yet
been verified on hardware. These fixes do not close the full relocation audit.
