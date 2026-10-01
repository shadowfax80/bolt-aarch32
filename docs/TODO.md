# Project TODO

The active work is the **ATFE correctness audit**. The original twelve-item list
has **3 scoped completions and 9 open items**; the earlier statement that all
other work was done was incorrect.

- [Correctness TODO and acceptance criteria](CORRECTNESS_TODO.md)
- [Fresh source review and reproduced defects](CORRECTNESS_REVIEW.md)
- [Twelve-item status tracker](CORRECTNESS_STATUS.md)
- [Completed fixes and verification evidence](CORRECTNESS_FIXES.md)

Start with CBZ/CBNZ flag preservation (#4), Thumb ELF entry translation (#9),
and profile/execution validation (#12), then the relocation matrix (#1) and
CFG invariants (#3). Pi execution takes priority over QEMU.

Upstream changes/builds, RFC posting and PR submission remain stopped by owner
request. The old upstream review in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)
is historical context, not the current work order.

Permanent SD-card chainloader reflash also remains owner-deferred. Temporary
fast-loader upload is already available for Pi verification.
