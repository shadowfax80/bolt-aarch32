# Claude ↔ Codex handoff

Two agents work on this repo: **Claude** (Claude Code) and **Codex**. This file
is the single source of truth for who owns what. Read it before starting work,
and update it before stopping. `AGENTS.md` and `CLAUDE.md` point here.

## Rules

1. **One writer per live tree.** The WSL ATFE source
   (`/home/user/bolt-aarch32/third_party/llvm-project-atfe`) and its build
   (`build-atfe`) are shared. Only the agent named in *Live-tree lock* may edit
   or rebuild them. Take the lock by committing a change to this file first;
   release it the same way.
2. **Claim before work.** Every work item has one owner in *Claims*. Do not
   start an item owned by the other agent. To take one over, record it in the
   *Handoff log* with the reason.
3. **One overlay per item.** Each source change is exported as the next
   `overlay/llvm/patches/atfe/NNNN-*.patch` with its own lit/unit test. Before
   pushing, `scripts/verify-atfe-overlays.py` must replay the full series with
   no mismatched or uncovered files.
4. **Evidence, not claims.** A *done* status names the patch, the tests and the
   before/after measurement. Hardware claims come from the Pi only (watchdog
   armed); QEMU is for debugging.
5. **Hand off on stop.** Append a *Handoff log* entry (newest first) and push.
   The entry says what changed, what was verified, the live-tree state, and
   what the other agent should do next.
6. **Project rules still apply:** no FPU/NEON (`-mfpu=none`,
   `scripts/check-no-fpu.sh`); no oracle contract derived from Pi output
   without the user's review; keep admission guards conservative.

## Live-tree lock

| Holder | Since | Purpose |
|---|---|---|
| Claude | 2026-10-04 | Review items R1, R2, R3, R7, R9, R10 (overlays 0046+) |

## Claims

Review items come from the 2026-10-04 Claude review of `0e616eb`
([details](CORRECTNESS_REVIEW_CLAUDE_0E616EB.md)). Items 6a–14 are Codex's
existing queue in [CORRECTNESS_PRIORITY_TODO.md](CORRECTNESS_PRIORITY_TODO.md).

| ID | Item | Priority | Owner | Status | Patch / evidence |
|---|---|---|---|---|---|
| R1 | Thumb `blx` re-patched as `bl` to ARM targets (61 LK sites) | P0 | Claude | In progress | |
| R2 | ARM `B`/`BL`/`BLX` re-patch drops condition and opcode | P0 | Claude | In progress | |
| R3 | Thumb narrow/conditional fixup → relocation mapping | P1 | Claude | In progress | |
| R4 | IT-predicated conditional tail call crashes (`LLVM ERROR`) | P1 | Codex | Open | |
| R5 | Noreturn calls at function end (~80 LK rejections) | P1 | Codex | Open | |
| R6 | Predicated returns in IT blocks (~45 LK rejections; item 8) | P1 | Codex | Open | |
| R7 | Far tail call through LongJmp stub becomes `BL` | P1 | Claude | In progress | |
| R8 | r12 clobber in local-branch LongJmp stubs | P1 | Codex | Open | |
| R9 | PatchEntries emits ARM patches into Thumb entries | P1 | Claude | In progress | |
| R10 | Global ARM builder used in Thumb functions; NOP as trap fill | P2 | Claude | In progress | |
| R11 | Skip-and-report admission mode | P2 | Codex | Open | |
| R12 | ADR to inline TBB/TBH table (`vsnprintf`) | P2 | Codex | Open | |
| R13 | Redirect functions starting with a 16-bit instruction | P2 | Codex | Open | |
| 6a–14 | Existing correctness queue | P0/P1 | Codex | See its table | |

## Handoff log

### 2026-10-04 — Claude takes the live-tree lock

- Synced Windows and WSL repos to `0e616eb`; the live ATFE tree replays
  exactly from overlays 0001–0045 (`out/atfe-replay-sync-20261004/replay.json`).
- Review published; items split as in *Claims*. Codex: start with R4 once
  Claude releases the lock; R5/R6 are the main coverage wins.
