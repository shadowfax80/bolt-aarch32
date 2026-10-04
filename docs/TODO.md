# Project TODO

## Current: stopped at verified oracle/Pi milestone and fresh review

2026-10-04: **work is stopped at the requested next milestone**. The latest
instruction to review, publish a new tabular TODO and stop supersedes the earlier
instruction to finish all P0 before stopping. All historical continuation/stop
statements below are checkpoint history. Consolidated P0 item 6 and original
#12 remain open; nothing is certified beyond its stated scope.

Both builds verify four integer-only ARM QEMU entries with eighteen independently
derived baseline/candidate sinks each. Compatible BL/LR Pi witnesses verify nine
edge seeds for all four ISA pairs: 144 transformed and 72 baseline positive cases,
eight expected faults (including two hangs), fourteen final uploads returning to
the loader. WSL passes all 141 host tests; Windows passes 137 with four Linux
process-ownership skips. Changed shell wrappers pass syntax checks. No additional
LLVM source change beyond 0045 or clean compiler-build proof is claimed.

Read the [fresh prioritized table](CORRECTNESS_PRIORITY_TODO.md),
[deep review](CORRECTNESS_REVIEW_0045.md),
[milestone contract](AARCH32_ORACLE_MILESTONE.md) and
[evidence](results/correctness_oracle_milestone_20261004.json).
Later resume starts at **6a: complete end-to-end sealed profile/optimization/
execution gate validation**. Whole-LK/original NEON memcpy, wider entry/CFG/
relocation/pass routes, interrupts/PMU and provenance remain open. The whole-LK
Pi gate now rejects unknown oracles; there is no approved Pi whole-LK contract.

Preserve dirty live ATFE/LK, unrelated Microsoft/, all raw evidence/preimages
under `out/correctness/p0-completion-20261004`, and earlier checkpoints. Final Pi
receipts are `wider-on/build-dqpxie5s/pi-verify-4sas_0wj` and
`wider-off/build-zoyyerjb/pi-verify-lolistaj`. Failed diagnostics (including first
wider ON receipt construction and system Python without pyserial) are retained;
they are not success evidence. Do not rerun one-time publication helpers, reset
trees, overwrite artifacts or reapply already-assessed overlays.

## Historical checkpoints and details

The active work is the **ATFE correctness audit**. The original twelve-item list
has **3 scoped completions and 9 open items**; the earlier statement that all
other work was done was incorrect.

- [Correctness TODO and acceptance criteria](CORRECTNESS_TODO.md)
- [Current source review and reproduced defects through 0038](CORRECTNESS_REVIEW_0038.md)
- [Consolidated correctness work items in priority order](CORRECTNESS_PRIORITY_TODO.md)
- [Twelve-item status tracker](CORRECTNESS_STATUS.md)
- [Completed fixes and verification evidence](CORRECTNESS_FIXES.md)

The current 14-task queue's first five priorities have scoped verified fixes.
Priority 6 remains active: 0045 rejects unmodeled PC reads, and four selected
integer-only reserved ARM entries execute in QEMU in both builds. Original NEON
memcpy, independent oracles and updated Pi live witnesses remain open.
All remaining #12 work is active by the user's latest instruction, including
PMU ownership, durable evidence and clean build provenance. Broader relocation,
CFG/state/symbol/table/pass tasks follow in the published queue. THM_JUMP19,
splitting, pass hooks and inline
TBB/TBH now have implementations and passing regressions. Pi execution takes
priority over QEMU.

Upstream changes/builds, RFC posting and PR submission remain stopped by owner
request. The old upstream review in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)
is historical context, not the current work order.

Permanent SD-card chainloader reflash also remains owner-deferred. Temporary
fast-loader upload is already available for Pi verification.
