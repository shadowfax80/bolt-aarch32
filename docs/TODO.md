# Project TODO

The active work is the **ATFE correctness audit**. The original twelve-item list
has **3 scoped completions and 9 open items**; the earlier statement that all
other work was done was incorrect.

- [Correctness TODO and acceptance criteria](CORRECTNESS_TODO.md)
- [Current source review and reproduced defects through 0038](CORRECTNESS_REVIEW_0038.md)
- [Consolidated correctness work items in priority order](CORRECTNESS_PRIORITY_TODO.md)
- [Twelve-item status tracker](CORRECTNESS_STATUS.md)
- [Completed fixes and verification evidence](CORRECTNESS_FIXES.md)

The current 14-task queue starts with skipped interior-entry reservation bypass,
Thumb instrumentation startup, ISA/ABI admission and fixed-load/PIE policy.
Exact profile/artifact binding and execution-gate integrity follow as P0 tasks.
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
