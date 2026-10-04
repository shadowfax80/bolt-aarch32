#!/usr/bin/env python3
"""T2b: are BOLT instrumentation counters exact when all cores run instrumented code?

On one boot of an image whose 15 concurrent-set bolt_bench workloads are
instrumented (and redirected into their instrumented copies):
  1. run each workload once (one core)        -> dump counters: C1
  2. run `bolt_bench smp R` (4 cores)         -> dump counters: C2
Each workload then ran 1 + 4 (per-core phase) + 4*R (concurrent phase) times,
so every counter that moved must match C2 = 5*C1 + 4R*D (see compare). A lost update
(two cores incrementing the same counter non-atomically) makes C2 smaller.
Words that did not move (descriptor/metadata bytes) are ignored; the run
fails if fewer than --min-counters words scale correctly or any word moved
by a different factor.
"""
import argparse
import re
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from bolt_bench_smp_check import CONC_SET, check as smp_check  # noqa: E402
from bolt_dump_reassemble import parse_dump_stream  # noqa: E402


def dumps(text, address, size):
    # One part per dump (the command line itself is echoed twice).
    parts = text.split('BOLT_DUMP_BEGIN')
    out = []
    for part in parts[1:]:
        res = parse_dump_stream('BOLT_DUMP_BEGIN' + part)
        if res.addr != address or res.size != size:
            raise SystemExit(f'FAIL: unexpected dump range {res.addr:#x}+{res.size:#x}')
        if res.bad_seqs or not res.is_complete():
            raise SystemExit(f'FAIL: corrupt/incomplete counter dump (bad chunks {res.bad_seqs[:5]}, '
                             f'missing {res.missing_ranges()[:3]}); re-run')
        out.append(res.to_bytes())
    return out


def compare(c1, c2, reps):
    """Exact model: C2 = 5*C1 + 4R*D, D = the counter's per-run count in the
    concurrent phase, where banners are suppressed (g_bench_quiet). Valid
    shapes: path unaffected by the flag (C2 = (5+4R)*C1), banner path only
    (C2 = 5*C1), quiet path only (C1 = 0, C2 a multiple of 4R). Lost updates
    break these shapes. Returns (counts per shape, offending words)."""
    q = 4 * reps
    shapes = dict(unaffected=0, banner=0, quiet=0)
    bad = []
    for i in range(len(c1) // 8):
        a, = struct.unpack_from('<Q', c1, 8 * i)
        b, = struct.unpack_from('<Q', c2, 8 * i)
        if a == b:
            continue
        if a and b == a * (5 + q):
            shapes['unaffected'] += 1
        elif a and b == 5 * a:
            shapes['banner'] += 1
        elif a == 0 and b % q == 0:
            shapes['quiet'] += 1
        else:
            bad.append((8 * i, a, b))
    return shapes, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('image', type=Path)
    ap.add_argument('--addr', required=True)
    ap.add_argument('--size', required=True)
    ap.add_argument('--reps', type=int, default=4)
    ap.add_argument('--min-counters', type=int, default=15)
    ap.add_argument('--port', default='COM5')
    ap.add_argument('--fast-loader', type=Path, required=True)
    ap.add_argument('--log', type=Path, required=True)
    a = ap.parse_args()
    addr, size = int(a.addr, 16), int(a.size, 16)
    cmds = [f'bolt_bench {n}' for n in CONC_SET]
    cmds += [f'bolt_dump {addr:x} {size:x}', f'bolt_bench smp {a.reps}', f'bolt_dump {addr:x} {size:x}']
    p = subprocess.run([sys.executable, str(HERE / 'pi4_run.py'), str(a.image), *cmds, '--port', a.port,
                        '--reboot', '--wait', '30', '--max-wait', '900', '--wdog', '900',
                        '--fast-loader', str(a.fast_loader)], capture_output=True, text=True, timeout=3000)
    a.log.write_text(p.stdout + p.stderr, encoding='utf-8', errors='replace')
    text = a.log.read_text(errors='replace')
    if p.returncode or re.search(r'abort|fault|panic|undefined instr', text, re.I):
        sys.exit(f'FAIL: Pi run failed or faulted; see {a.log}')
    errors, summary = smp_check(text, 4)
    if errors:
        sys.exit('FAIL: smp results: ' + '; '.join(errors[:4]))
    got = dumps(text, addr, size)
    if len(got) != 2 or any(len(g) != size for g in got):
        sys.exit(f'FAIL: expected two complete counter dumps, got {[len(g) for g in got]}')
    reps = summary['reps']
    shapes, bad = compare(got[0], got[1], reps)
    print(f'counters by shape: {shapes}; wrong: {len(bad)}')
    for off, x, y in bad[:10]:
        print(f'  +0x{off:x}: C1={x} C2={y} (unaffected would be {x * (5 + 4 * reps)})')
    if bad or shapes['unaffected'] < a.min_counters:
        sys.exit('FAIL: counters are not exact under SMP')
    print('PASS: every moved counter matches the exact SMP model')


if __name__ == '__main__':
    main()
