#!/usr/bin/env python3
"""T2 certified SMP gate on the Pi: rewritten code on every core.

Input: a candidate directory from full_image_build.py whose input image has an
approved `pi4` contract marked `smp` (the image carries `bolt_bench smp`).

1. Original image: `bolt_bench smp <reps>`; every per-core sink, sequential and
   concurrent, equals the independent oracle (scripts/bolt_bench_smp_check.py).
2. Rewritten image: PC sampling on all cores with a watch range per required
   redirected function, then `bolt_bench smp <reps>`. Every sink equals the
   oracle AND every active core has samples inside every required rewritten
   function: the rewritten copies ran on each core, concurrently.

Writes <dir>/smp-verify-*/smp_verification.json (hashes of inputs, logs,
scripts, revision) on success; exits non-zero otherwise.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from bolt_bench_smp_check import CONC_SET, check as smp_check  # noqa: E402
from qemu_bench_oracle import check_contract  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pi_run(image, commands, log, a):
    cmd = [sys.executable, str(HERE / 'pi4_run.py'), str(image), *commands, '--port', a.port,
           '--reboot', '--wait', '30', '--max-wait', str(a.max_wait), '--wdog', str(a.max_wait),
           '--fast-loader', str(a.fast_loader)]
    with open(log, 'w', encoding='utf-8', errors='replace') as out:
        p = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT, timeout=a.max_wait * 3)
    text = Path(log).read_text(errors='replace')
    if p.returncode:
        raise SystemExit(f'error: pi4_run failed ({p.returncode}); see {log}')
    if re.search(r'abort|fault|panic|undefined instr', text, re.I):
        raise SystemExit(f'error: fault reported; see {log}')
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('dir', type=Path, help='full_image_build.py output directory')
    ap.add_argument('--require-executed', required=True,
                    help='comma-separated redirected functions to observe on every core')
    ap.add_argument('--reps', type=int, default=8)
    ap.add_argument('--period', type=int, default=20000)
    ap.add_argument('--port', default='COM5')
    ap.add_argument('--fast-loader', type=Path, required=True)
    ap.add_argument('--max-wait', type=int, default=600)
    a = ap.parse_args()

    manifest = json.loads((a.dir / 'full_manifest.json').read_text())
    contract = check_contract(manifest['input_sha256'], 'pi4')
    if not contract.get('smp'):
        raise SystemExit('error: the approved contract does not cover the SMP harness')
    required = [n for n in a.require_executed.split(',') if n]
    redirected = {r['name']: r for r in manifest['redirected']}
    if not required or len(set(required)) != len(required) or set(required) != set(redirected):
        raise SystemExit('error: require distinct names covering every selected redirect')
    for n in required:
        if n.removeprefix('bolt_bench_') not in CONC_SET:
            raise SystemExit(f'error: {n} is not in the concurrent set; it would not run on every core')
    if len(required) > 8:
        raise SystemExit('error: at most 8 watched functions')
    baseline, candidate = a.dir / 'baseline.bin', a.dir / 'baseline_full.bin'
    if sha(baseline) != manifest['baseline_binary_sha256'] or sha(candidate) != manifest['binary_sha256']:
        raise SystemExit('error: images do not match the build manifest')

    out = Path(tempfile.mkdtemp(prefix='smp-verify-', dir=a.dir))
    print('Evidence:', out, flush=True)
    base_log = pi_run(baseline, [f'bolt_bench smp {a.reps}'], out / 'baseline.log', a)
    errors, base_summary = smp_check(base_log, 4)
    if errors:
        raise SystemExit('error: baseline: ' + '; '.join(errors[:5]))

    cmds = [f"bolt_sample watch {redirected[n]['output']:x} "
            f"{redirected[n]['output'] + redirected[n]['output_size']:x}" for n in required]
    cmds += [f'bolt_sample start {a.period}', f'bolt_bench smp {a.reps}', 'bolt_sample stop']
    cand_log = pi_run(candidate, cmds, out / 'candidate.log', a)
    errors, cand_summary = smp_check(cand_log, 4)
    if errors:
        raise SystemExit('error: candidate: ' + '; '.join(errors[:5]))
    hits = {int(w): list(map(int, h.split()))
            for w, h in re.findall(r'bolt_sample: watch (\d+) hits per core: ([\d ]+)', cand_log)}
    ncpu = cand_summary['cpus']
    coverage = {}
    for w, name in enumerate(required):
        per_core = hits.get(w, [0] * 4)[:ncpu]
        coverage[name] = per_core
        if len(per_core) < ncpu or min(per_core) == 0:
            raise SystemExit(f'error: no rewritten execution observed on every core for {name}: {per_core}')

    scripts = {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for p in (
        Path(__file__), HERE / 'pi4_run.py', ROOT / 'scripts/bolt_bench_smp_check.py',
        ROOT / 'scripts/qemu_bench_oracle.py')}
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    receipt = dict(schema=1, verified_at=datetime.now(timezone.utc).isoformat(),
                   scope='every active core: oracle-equal sinks (sequential and concurrent) on original and rewritten images; PC samples inside every required rewritten function on every core',
                   input_sha256=manifest['input_sha256'], contract=contract['name'],
                   images=dict(baseline=sha(baseline), candidate=sha(candidate)),
                   required=required, per_core_samples=coverage, reps=a.reps, period=a.period,
                   baseline=base_summary, candidate=cand_summary,
                   logs=dict(baseline=sha(out / 'baseline.log'), candidate=sha(out / 'candidate.log')),
                   scripts=scripts, repository_revision=revision)
    (out / 'smp_verification.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'PASS: {ncpu} cores; baseline seq {base_summary["seq_results"]} + conc {base_summary["conc_results"]}; '
          f'rewritten seq {cand_summary["seq_results"]} + conc {cand_summary["conc_results"]}; '
          f'per-core samples {coverage}')
    print(out / 'smp_verification.json')


if __name__ == '__main__':
    main()
