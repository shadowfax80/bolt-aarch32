# Agent instructions

This repo is worked on by two agents, Codex and Claude. Before any work, read
[docs/HANDOFF.md](docs/HANDOFF.md) and follow its rules: respect the live-tree
lock and item ownership, export one overlay per item, and append a handoff log
entry before stopping.

Current Codex priorities (see the consolidated TODO in docs/HANDOFF.md): 6a,
then R8, R11, R12, R13 and R15. Claude finished R4-R6 (0051-0053) and changed
two Codex tests in 0053; the handoff log explains why. Coverage is measured
by scripts/lk_coverage_report.py.
