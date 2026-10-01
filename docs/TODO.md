# Project TODO

The active work is the **ATFE correctness audit**. The original twelve-item list
has **3 scoped completions and 9 open items**; the earlier statement that all
other work was done was incorrect.

- [Correctness TODO and acceptance criteria](CORRECTNESS_TODO.md)
- [Fresh source review and reproduced defects at bbae817](CORRECTNESS_REVIEW_BBAE817.md)
- [Twelve-item status tracker](CORRECTNESS_STATUS.md)
- [Completed fixes and verification evidence](CORRECTNESS_FIXES.md)

Next is execution/result/profile validation (#12), then instrumentation (#5/#6),
CFG/control-flow safety (#3/#4), relocations (#1), symbols (#9), and supported
input/pass boundaries (#7/#11). THM_JUMP19, splitting, pass hooks and inline
TBB/TBH now have implementations and passing regressions. Pi execution takes
priority over QEMU.

Upstream changes/builds, RFC posting and PR submission remain stopped by owner
request. The old upstream review in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)
is historical context, not the current work order.

Permanent SD-card chainloader reflash also remains owner-deferred. Temporary
fast-loader upload is already available for Pi verification.
