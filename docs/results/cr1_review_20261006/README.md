# CR1 offline review evidence — 2026-10-06

Assessment and closure criteria:
[0072 review](../../reviews/CORRECTNESS_REVIEW_CODEX_0072_20261006.md).
Joint lk-perf source baseline: `a547f94`; BOLT baseline: `d6aa4bb`.

| Artifact | Content |
|---|---|
| [probe_contracts.py](probe_contracts.py) | Replayable adversarial probes with disposable ELF/log inputs and a synthetic serial transport |
| [probe-results.json](probe-results.json) | Observed scheduler/input-overwrite, mixed-source/count, incomplete collector and false suite-gain defects |
| [verification.json](verification.json) | Used tool hashes, 72-overlay digest, identity comparison with item 14, test counts and optional consumer failure |
| [edge-on.json](edge-on.json), [edge-off.json](edge-off.json) | All 182 per-mode differential outcomes; QEMU diagnostics only |
| [bolt-host-tests.txt](bolt-host-tests.txt) | Host suite: 167 tests, 12 skipped, OK |
| [perfetto-consumer.txt](perfetto-consumer.txt) | Real consumer failure: stale leaf-only expectation after K3 |
| [archive-audit.json](archive-audit.json) | B1/B2 published CSV shape and capture-manifest audit; does not certify raw command/result frames |

Replay the probes in WSL (Python/pyelftools, ARM GNU assembler/linker):

```bash
python3 docs/results/cr1_review_20261006/probe_contracts.py \
  --bolt "$PWD" --lkperf /path/to/independent/lk-perf \
  --toolchain /path/to/current/bolt/bin > /path/to/fresh/probe-results.json
```

The script imports both repositories' current parsers, assembles real fixtures,
checks ELF/image and sealed identities, and replaces only serial transport.
The deliberately overwritten ELF lives in a `TemporaryDirectory`; no project
input is damaged. It reports current behavior rather than asserting future
fixes. Move the relevant cases into regression tests while closing the items.

Differential replay, each assertion mode with its own fresh output directory:

```bash
python3 scripts/review/edge_probe.py /path/to/current/bolt/bin /path/to/fresh/edge-out
```

The focused 0070–0072 checkers were also executed from the read-only shared
source with the appropriate tool directory on PATH and fresh `/tmp` outputs.
They all returned 0; temporary outputs were subsequently unavailable, so
`verification.json` explicitly distinguishes these tool-output observations
from the retained differential JSON. No shared source/build mutation or Pi
use. The optional consumer ran against the installed real Perfetto wrapper
and retained its failure log. No hardware, broad clean build or fresh full
lit certification is claimed by this evidence bundle.
