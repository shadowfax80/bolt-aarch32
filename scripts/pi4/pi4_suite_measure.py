#!/usr/bin/env python3
"""Measure several images on a suite of existing LK apps (B1 whole-image case).

Each image is booted (--reboot) once per round and runs the suite `--runs`
times; the image order rotates every round. Metrics per app:
  - `bolt_bench X`: the app's own cycle count ("X done (N cycles)"), one per
    kernel (pgo_lab reports pl_a..pl_d);
  - `profiler stat -e EV <cmd>` (lk-perf K7): cycles summed over all cores.
Every app's result value (bolt_bench `acc=`, lk-perf `sink=`) must be the same
in every run of every image, or the measurement is refused.

    pi4_suite_measure.py --out suite.csv --rounds 3 --runs 2 \\
        input=in.bin bolt=out.bin -- "bolt_bench composite" "profiler stat -e 0x11 profiler bench 2000000"
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DONE = re.compile(r"bolt_bench: (\w+) done \((\d+) cycles\)")
ACC = re.compile(r"bolt_bench: (\w+) acc=(0x[0-9a-f]+)")
SINK = re.compile(r"profiler: (\w+) done \(sink=(\d+)")
STAT_CMD = re.compile(r"stat: '(.+)' returned (-?\d+), ([\d.]+) ms")
STAT_ALL = re.compile(r"stat: all\s+(\d+)\s+\d+")


def parse(text: str) -> tuple[list[dict], list[dict]]:
    """Per suite pass: {metric: cycles}; plus result values seen per run."""
    runs, cur, results = [], {}, []
    cur_results = {}
    pending = None
    for line in text.splitlines():
        if line.startswith('$ ') and '__SUITE_START__' in line:
            if cur or cur_results:
                runs.append(cur)
                results.append(cur_results)
            cur = {}
            cur_results = {}
            continue
        if m := DONE.search(line):
            if m[1] in cur:
                raise ValueError(f"duplicate metric in run: {m[1]}")
            cur[m[1]] = int(m[2])
        elif m := ACC.search(line):
            if m[1] in cur_results:
                raise ValueError(f"duplicate result in run: {m[1]}")
            cur_results[m[1]] = m[2]
        elif m := SINK.search(line):
            key = 'profiler_' + m[1]
            if key in cur_results:
                raise ValueError(f"duplicate result in run: {key}")
            cur_results[key] = m[2]
        elif m := STAT_CMD.search(line):
            pending = m[1].split()[1] if m[1].startswith('profiler ') else m[1]
            if int(m[2]) != 0:
                raise ValueError(f'{m[1]} returned {m[2]}')
        elif pending and (m := STAT_ALL.search(line)):
            if pending in cur:
                raise ValueError(f"duplicate metric in run: {pending}")
            cur[pending] = int(m[1])
            pending = None
    if cur or cur_results:
        runs.append(cur)
        results.append(cur_results)
    return runs, results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', required=True)
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--runs', type=int, default=2)
    ap.add_argument('--port', default='COM5')
    ap.add_argument('--max-wait', default='300')
    ap.add_argument('images', nargs='+', help='name=image.bin ... -- suite commands')
    args = ap.parse_args()
    images = [a.split('=', 1) for a in args.images if '=' in a and not a.startswith(('bolt_bench', 'profiler'))]
    suite = [a for a in args.images if a not in {f'{n}={p}' for n, p in images}]
    if not images or not suite:
        ap.error('need name=image arguments and suite commands')
    evidence = Path(tempfile.mkdtemp(prefix='suite-', dir=Path(args.out).resolve().parent))
    rows, values = [], defaultdict(set)

    # We must determine expected_metrics in the first run and enforce it
    expected_metrics = None
    expected_result_keys = None

    for rnd in range(args.rounds):
        order = images[rnd % len(images):] + images[:rnd % len(images)]
        for name, path in order:
            log = evidence / f'r{rnd + 1}_{name}.log'
            commands = []
            for _ in range(args.runs):
                commands += ['__SUITE_START__', *suite]
            cmd = [sys.executable, str(HERE / 'pi4_run.py'), path, '--port', args.port, '--reboot',
                   '--wait', '30', '--max-wait', args.max_wait, '--log', str(log), *commands]
            print(f'round {rnd + 1}/{args.rounds}  {name} ...', flush=True)
            r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if r.returncode:
                raise SystemExit(f'{name}: run failed: {r.stderr[-600:]}')

            log_text = log.read_text(errors='replace')
            # Each run produces results; if a result is missing in one run, `parse` just doesn't add it.
            # To fix R32, we should ensure the *set* of results is exactly identical across all images/runs.
            runs, results = parse(log_text)
            if len(runs) != args.runs:
                raise ValueError(f'{name}: expected {args.runs} runs, got {len(runs)}')

            for i, (run, result_dict) in enumerate(zip(runs, results)):
                run_result_keys = set(result_dict.keys())
                if expected_result_keys is None:
                    expected_result_keys = run_result_keys
                if run_result_keys != expected_result_keys:
                    raise ValueError(f'{name}: results mismatch in run {i+1}. expected {expected_result_keys}, got {run_result_keys}')

                for k, v in result_dict.items():
                    values[k].add(v)

            for i, run in enumerate(runs):
                run_metrics = set(run.keys())
                if expected_metrics is None:
                    expected_metrics = run_metrics
                if run_metrics != expected_metrics:
                    raise ValueError(f'{name}: metrics mismatch in run {i+1}. expected {expected_metrics}, got {run_metrics}')

                for metric, cycles in run.items():
                    rows.append(dict(image=name, round=rnd + 1, run=i + 1, metric=metric, cycles=cycles))

    differing = {k: sorted(v) for k, v in values.items() if len(v) > 1}

    if differing:
        print(f'RESULTS DIFFER between runs/images: {differing}')
        return 1

    with open(args.out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['image', 'round', 'run', 'metric', 'cycles'])
        w.writeheader()
        w.writerows(rows)
    print(f'\n{len(rows)} measurements -> {args.out}; evidence {evidence}')
    if differing:
        print(f'RESULTS DIFFER between runs/images: {differing}')
        return 1
    print(f'results identical in every run of every image ({len(values)} app results checked)')
    data = defaultdict(list)
    for row in rows:
        data[(row['metric'], row['image'])].append(row['cycles'])
    metrics = list(dict.fromkeys(row['metric'] for row in rows))
    base = images[0][0]
    head = f"{'app':<12}" + ''.join(f'{n:>22}' for n, _ in images)
    print('\n' + head)
    totals = defaultdict(float)
    for metric in metrics:
        line = f'{metric:<12}'
        b = data[(metric, base)]
        bm = sum(b) / len(b) if b else float('nan')
        for name, _ in images:
            v = data[(metric, name)]
            if not v:
                line += f"{'-':>22}"
                continue
            m = sum(v) / len(v)
            totals[name] += m
            if name == base:
                line += f'{m / 1e6:>21.3f}M'
            else:
                sd = lambda x: math.sqrt(sum((y - sum(x) / len(x)) ** 2 for y in x) / max(len(x) - 1, 1))
                ci = 1.96 * math.sqrt(sd(v) ** 2 / len(v) + sd(b) ** 2 / len(b)) / bm * 100
                line += f'{m / 1e6:>10.3f}M {100 * (m / bm - 1):+6.2f}%±{ci:.2f}'
        print(line)
    print(f"{'total':<12}" + ''.join(
        f'{totals[n] / 1e6:>21.3f}M' if n == base else
        f'{totals[n] / 1e6:>10.3f}M {100 * (totals[n] / totals[base] - 1):+6.2f}%      '
        for n, _ in images))
    return 0


if __name__ == '__main__':
    sys.exit(main())
