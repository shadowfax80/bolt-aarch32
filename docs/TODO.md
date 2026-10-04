# Project TODO

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
