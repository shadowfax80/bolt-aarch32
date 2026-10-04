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
| — (free) | 2026-10-04 | Released by Claude after overlays 0046–0050 |

## Claims

Review items come from the 2026-10-04 Claude review of `0e616eb`
([details](CORRECTNESS_REVIEW_CLAUDE_0E616EB.md)). Items 6a–14 are Codex's
existing queue in [CORRECTNESS_PRIORITY_TODO.md](CORRECTNESS_PRIORITY_TODO.md).

| ID | Item | Priority | Owner | Status | Patch / evidence |
|---|---|---|---|---|---|
| R1 | Thumb `blx` re-patched as `bl` to ARM targets (61 LK sites) | P0 | Claude | Done | 0046; `arm-external-branch-repatch.test`; LK raw output 61 → 0 bad sites |
| R2 | ARM `B`/`BL`/`BLX` re-patch drops condition and opcode | P0 | Claude | Done | 0046 (also fixes A32 PC+8 and skipped A32 callers) |
| R3 | Thumb narrow/conditional fixup → relocation mapping | P1 | Claude | Done | 0046 (also fixes Thumb-encoded-as-ARM `b.w`/`bne.w`) |
| R4 | IT-predicated conditional tail call crashes (`LLVM ERROR`) | P1 | Codex | Open | |
| R5 | Noreturn calls at function end (~80 LK rejections) | P1 | Codex | Open | |
| R6 | Predicated returns in IT blocks (~45 LK rejections; item 8) | P1 | Codex | Open | |
| R7 | Far tail call through LongJmp stub becomes `BL` | P1 | Claude | Done | 0049; `arm-far-tail-call.test` |
| R8 | r12 clobber in local-branch LongJmp stubs | P1 | Codex | Open | |
| R9 | PatchEntries emits ARM patches into Thumb entries | P1 | Claude | Done | 0048; `arm-patch-entries.test` |
| R10 | Global ARM builder used in Thumb functions; NOP as trap fill | P2 | Claude | Done | 0050; `arm-trap-fill.test` (was an encoder crash) |
| R11 | Skip-and-report admission mode | P2 | Codex | Open | |
| R12 | ADR to inline TBB/TBH table (`vsnprintf`) | P2 | Codex | Open | |
| R13 | Redirect functions starting with a 16-bit instruction | P2 | Codex | Open | |
| R14 | RISC-V 64 relocations dispatched to the ARM helpers | P1 | Claude | Done (untested) | 0047; RISC-V target not built here |
| R15 | Full-LK instrumentation rejected: `arch_spin_trylock` returns with a live reservation (0038 guard false positive) | P1 | Codex | Open | `instrument-lk-bolt.sh` on input `424606a8…` fails before any counter is placed |
| 6a–14 | Existing correctness queue | P0/P1 | Codex | See its table | |

## Handoff log

### 2026-10-04 — Claude releases the lock (overlays 0046–0050)

**Done:** R1–R3 (0046), R14 (0047), R9 (0048), R7 (0049), R10 (0050). Each
has its own lit test, except 0047. Evidence:
[claude_review_fixes_20261004.json](results/claude_review_fixes_20261004.json).

- **0046** goes beyond the review: the external-reference scan used the A32
  builder, disassembler symbolizer and STI for Thumb functions. Thumb `b.w` /
  `bne.w` to moved functions were overwritten with A32 encodings, and A32
  callers were never re-patched (the symbolizer had already replaced the
  operand). Branches are now re-encoded from the original word (condition,
  BL/BLX by target ISA, PC+8/PC+4). An out-of-range branch keeps its original
  target, with a warning (relocation mode only). With `--use-old-text`, A32
  sites are left to `patchKeptARMCodeReferences()` as before.
- **Verified:** ARM lit 42/42; BOLT lit 852/853; CoreTests 58 passed, 31
  skipped; JITLink AArch32 15/15. Overlays 0001–0050 replay exactly
  (`out/atfe-replay-claude-0050`). Pi (fast loader, watchdog): full-image LK
  candidate, all 18 results equal baseline and the reference formulas.
- **Not verified:** the one BOLT lit failure,
  `AArch64/constant_island_pie_update.s`, is not caused by these patches (all
  changes are ARM-gated), but it was not rerun on a pre-0046 binary. 0047
  is untested because RISC-V is not in `LLVM_TARGETS_TO_BUILD`. The Pi gate
  restores the original text, so it cannot exercise 0046 on hardware; that
  needs a pipeline mode that keeps BOLT's patched original code.
- **Live tree:** clean against overlays 0001–0050; `build-atfe` is built from
  it. The lock is free.
- **Next for Codex:** R4, then R5/R6 (coverage), then R8, R11–R13 and the
  existing queue. Re-run the LK skip-list scan after R4–R6 to measure coverage.

### 2026-10-04 — Claude takes the live-tree lock

- Synced Windows and WSL repos to `0e616eb`; the live ATFE tree replays
  exactly from overlays 0001–0045 (`out/atfe-replay-sync-20261004/replay.json`).
- Review published; items split as in *Claims*. Codex: start with R4 once
  Claude releases the lock; R5/R6 are the main coverage wins.
