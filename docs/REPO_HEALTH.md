# Repository health check — 2026-10-04

M1 checked the tracked repository and consolidated documentation after overlay
0061. Current backend work and resource ownership remain in
[HANDOFF.md](HANDOFF.md). This was repository hygiene, not a backend correctness
or clean-build certification.

## Changes

- Removed copied current queues from TODO/status pages; HANDOFF is the single
  source. Original acceptance criteria, twelve-row snapshot, checkpoints and
  older session logs are explicitly archived and linked.
- Corrected README entry points, old RunPod resume notices, WSL sync/ownership
  guidance and fixture-specific provenance. Dated reviews/design pages retain
  their original scope and point to current guidance.
- Documented v8-A and SMP contract extensions. R17's original plan is marked
  as historical; each new configuration still needs a reviewed contract.
- Re-rendered LK_COVERAGE from the existing 0059 receipt, correcting the stale
  instrumentation failure and agent-origin labels. Counts and original receipt
  bytes are unchanged; no new BOLT measurement was taken.
- Updated the monitor to read current HANDOFF tables and reject duplicate or
  malformed work rows. Added a repeatable offline health command.

## Verification

The health command passes tracked JSON parsing, Python syntax, local Markdown
file-target checks, current-table parsing, the contiguous 61-overlay inventory,
all seven fixture hashes and all 11 R11-bound artifact hashes. It does not check
external links/anchors or replay/build LLVM. Host tests: **167 run, 12 skipped,
no failures**, using the existing Windows pyserial venv. The four new work-table
regressions cover mixed IDs/reopened/deferred/Done states and malformed/duplicate
rows. The monitor's one-shot run reads the current queue successfully.

The initial system-Python suite could not import pyserial; the configured venv
resolved that environment issue. Platform/toolchain-dependent tests retain their
skips. No Pi port was opened, shared source changed, image rebuilt or hardware
correctness claim made.

Frozen stage-two generator copies and byte-identical ON/OFF receipts are
intentional provenance artifacts; they were retained. Untracked Microsoft/
and local build/evidence trees were left untouched.

## Repeat locally

```powershell
py -3 scripts/repo_health.py --json out/repo-health.json
.\out\correctness\pi-venv\Scripts\python.exe -m unittest discover -s scripts/tests
py -3 scripts/correctness-monitor.py --once
```

The health command checks tracked files, including staged additions. Its report
is a diagnostic; success does not close backend work items or reserve resources.
