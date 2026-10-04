#!/usr/bin/env python3
"""Compare R17 bolt_edge runs and BOLT admission against docs/bolt_edge/manifest.json.

  check.py results <serial.log> [--repeat N]
      Every case's `bolt_edge: <case> sink=...` line must equal the manifest's
      model-computed expected_sink (N complete `bolt_edge all` runs).
  check.py admission <coverage.json>
      Each manifest function's admission (from scripts/lk_coverage_report.py
      --json) must match its expectation: "rewrite", "reject:<class>" or
      "alias" (any non-rejected status). Known gaps are reported, not hidden.

Exit status 1 on any mismatch.
"""
import argparse
import json
import re
import sys
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[2] / 'docs/bolt_edge/manifest.json'  # --manifest overrides


def results(log, repeat):
    m = json.loads(MANIFEST.read_text(encoding='utf-8'))
    text = Path(log).read_text(encoding='utf-8', errors='replace')
    runs = re.findall(r'bolt_edge: done (\d+) cases', text)
    if len(runs) != repeat or any(int(n) != len(m['cases']) for n in runs):
        print(f'FAIL: expected {repeat} complete runs of {len(m["cases"])} cases, got {runs}')
        return 1
    seen = {}
    for name, value in re.findall(r'bolt_edge: (\w+) sink=(0x[0-9a-f]{8})', text):
        seen.setdefault(name, []).append(value)
    bad = [(c['name'], c['expected_sink'], seen.get(c['name']))
           for c in m['cases']
           if seen.get(c['name']) != [c['expected_sink']] * repeat]
    print(f'{len(m["cases"])} cases x {repeat}: {len(bad)} mismatches')
    for row in bad:
        print('  MISMATCH', row)
    return 1 if bad else 0


def admission(coverage):
    m = json.loads(MANIFEST.read_text(encoding='utf-8'))
    rows = {r['name']: r for r in json.loads(Path(coverage).read_text())['rows']}
    want = dict(m['helpers'])
    for c in m['cases']:
        want.update(c['functions'])
    bad = []
    for name, expected in want.items():
        row = rows.get(name)
        if not row:
            bad.append((name, expected, 'missing'))
            continue
        status = row['status']
        if status == 'rejected':
            got = 'reject:' + row.get('reason_class', '?')
        else:
            # Rewritten, folded or an alias of a rewritten body all count as
            # admitted; which alias name carries the body is incidental.
            got = 'rewrite'
        ok = got == expected or (expected == 'alias' and got == 'rewrite')
        if not ok:
            bad.append((name, expected, got, row.get('reason', '')[:80]))
    print(f'{len(want)} functions: {len(bad)} admission mismatches')
    for row in bad:
        print('  MISMATCH', row)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('results')
    r.add_argument('log')
    r.add_argument('--repeat', type=int, default=1)
    a = sub.add_parser('admission')
    a.add_argument('coverage')
    ap.add_argument('--manifest', type=Path, help='default: docs/bolt_edge/manifest.json')
    args = ap.parse_args()
    if args.manifest:
        global MANIFEST
        MANIFEST = args.manifest
    return results(args.log, args.repeat) if args.cmd == 'results' else admission(args.coverage)


if __name__ == '__main__':
    sys.exit(main())
