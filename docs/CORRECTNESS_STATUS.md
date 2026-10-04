# Correctness status

The single current status table is
[HANDOFF.md → Claims](HANDOFF.md#claims-consolidated-todo).
The old twelve-row tracker was a historical snapshot and is retired.

For original IDs and acceptance criteria, see
[CORRECTNESS_WORKSTREAMS_HISTORY.md](CORRECTNESS_WORKSTREAMS_HISTORY.md).
For earlier milestones, see
[CORRECTNESS_CHECKPOINT_HISTORY.md](CORRECTNESS_CHECKPOINT_HISTORY.md).

`python3 scripts/correctness-monitor.py --once` now reads HANDOFF directly.
Without `--once`, it records changes/heartbeats under `out/correctness/`;
running the monitor does not execute fixes or reserve resources.
