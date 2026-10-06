#!/usr/bin/env python3
"""CR1 review reproductions. Run in WSL with --bolt/--lkperf/--toolchain.

Uses real parsers, bindings and fresh temporary ELF/image files. Only the Pi
transport is replaced with a writer of synthetic, checksummed console output.
Expected observations describe defects at the review baseline, not fixes.
"""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ap = argparse.ArgumentParser()
ap.add_argument('--bolt', required=True)
ap.add_argument('--lkperf', required=True)
ap.add_argument('--toolchain', required=True)
a = ap.parse_args()
bolt, lk = Path(a.bolt), Path(a.lkperf)
sys.path[:0] = [str(lk / 'scripts'), str(bolt / 'scripts')]
from test_sched_report import build_elf, dump, NAME, SWITCH, READY, BLOCKED
from test_irqmask_report import dump_text, sample_line
from pi4_pc_histogram import image_hash, _fnv
from pi4_sched_report import parse_sched, analyse
from pi4_perf_export import read_capture, export_capture
import profile_identity

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

suite = load('review_suite', bolt / 'scripts/pi4/pi4_suite_measure.py')
collector = load('review_collector', bolt / 'scripts/pi4/pi4_lkperf_profile.py')
results = {}
with tempfile.TemporaryDirectory(prefix='codex-cr1-contracts-') as directory:
    tmp = Path(directory)
    elf, sym = build_elf(tmp)
    assembly = (tmp / 'f.S').read_text().replace('_start:', '_start:\n    .cfi_startproc').replace('bx lr', 'bx lr\n    .cfi_endproc')
    (tmp / 'f.S').write_text('.cfi_sections .debug_frame\n' + assembly)
    subprocess.run(['arm-none-eabi-as', '-g', str(tmp / 'f.S'), '-o', str(tmp / 'f.o')], check=True)
    subprocess.run(['arm-none-eabi-ld', '-Ttext=0x8000', '-Tdata=0x9000', str(tmp / 'f.o'), '-o', str(elf)], check=True)
    build = image_hash(str(elf), 0x8000, 0x8004)
    A, B = 0x80001000, 0x80001100
    events = [(0, 9000, SWITCH, READY, A, B, 0, 0)]
    lines = dump(events, {A: ('a', 16, 0), B: ('b', 16, 0)}, build=build, cpus=1)
    # This is a retained suffix: earlier switches have been overwritten.
    lines[1] = f'SCHEDCPU cpu=0 total=0000000a retained=00000001 crc={_fnv([0, 10, 1]):08x}\n'
    d = parse_sched(lines)
    report = analyse(d)
    results['scheduler_overwritten_prefix'] = dict(
        overwritten=9, first_retained_tick=9000, start=1000,
        inferred_a_oncpu_ticks=report['oncpu'][(A, 0)],
        observed='assigns entire unobserved 8000-tick prefix to a')
    # Valid line checksums are not sufficient to bind a footer to a header.
    mismatch = list(lines)
    mismatch[-1] = f'SCHEDEND run=0000000000009999 events=00000001 crc={_fnv([0x9999, 0, 1]):08x}\n'
    md = parse_sched(mismatch)
    results['scheduler_mismatched_footer'] = dict(
        header_run=md['header']['run'], footer_run=md['footer']['run'],
        rejected=dict(md['rejected']), analysis_completed=bool(analyse(md)))
    duplicate = lines[:-1] + [lines[-2]] + lines[-1:]
    dd = parse_sched(duplicate)
    results['scheduler_duplicate_event'] = dict(
        footer_events=dd['footer']['events'], accepted_events=len(dd['events']),
        rejected=dict(dd['rejected']))
    # Real CLI, fresh disposable inputs; no repository ELF/log is overwritten.
    log = tmp / 'sched.log'
    log.write_text(''.join(dump(events, {}, build=build, cpus=1)))
    original = elf.read_bytes()
    proc = subprocess.run([sys.executable, str(lk / 'scripts/pi4_sched_report.py'),
                           str(log), str(elf), '--systrace', str(elf)],
                          text=True, capture_output=True)
    results['scheduler_output_overwrites_elf'] = dict(
        exit_code=proc.returncode, input_changed=elf.read_bytes() != original,
        output_prefix=elf.read_bytes()[:20].decode(errors='replace'))
    elf.write_bytes(original)
    close_events = [(0, 1100, NAME, 0, A, 16, 0, 0, 'first'),
                    (0, 1200, NAME, 0, B, 16, 0, 0, 'second'),
                    (0, 2000, SWITCH, BLOCKED, A, B, B + 0x20, 0)]
    cd = parse_sched(dump(close_events, {}, build=build, cpus=1))
    analyse(cd)
    results['scheduler_overlapping_thread_bounds'] = dict(
        first_thread=hex(A), second_thread=hex(B), wait_queue=hex(B + 0x20),
        reported_owner=hex(cd['events'][-1]['wq_owner'][0]), expected_owner=hex(B))

    text = dump_text(build=build, hi=0x8004)
    # Keep header/CPU/footer at 1, append a distinct valid sequence-1 sample.
    excess = text.replace('DUMPEND', sample_line(seq=1) + 'DUMPEND', 1)
    cap = tmp / 'sample.log'
    cap.write_text(excess)
    samples, quality = read_capture(cap)
    results['sample_count_underflow'] = dict(
        accepted=len(samples), expected=quality['expected_samples'],
        lost=quality['lost_or_rejected_samples'])
    mixed = dump_text(build=build, hi=0x8004, modes=3, mixed=1, timer=(50, 1, 0),
                      samples=((0, 0x8000), (0, 0x8000)))
    records = [line for line in mixed.splitlines(True) if line.startswith('SAMPLE seq=')]
    mixed = mixed.replace(records[0], sample_line(seq=0, k6=('t', 0, 0, 0xffffffff), slen=128))
    cap.write_text(mixed)
    out = tmp / 'mixed.perf'
    meta = export_capture(cap, elf, out, mode='pmu', event='cpu-cycles', period=1000000)
    results['mixed_capture_weighted_as_pmu'] = dict(
        timer_record_present='src=t' in mixed,
        output_headers=[l for l in out.read_text().splitlines() if 'cpu-cycles:' in l],
        target=meta['capture']['target'])

    # Exercise collector main with real ELF/load-image/build-manifest checks.
    (tmp / 'sealed.S').write_text('''
.text
.global _start
.type _start,%function
_start: bx lr
.size _start,.-_start
.bss
.global bolt_sample_buf
.type bolt_sample_buf,%object
bolt_sample_buf: .space 0x80000
.size bolt_sample_buf,.-bolt_sample_buf
''')
    subprocess.run(['arm-none-eabi-as', str(tmp / 'sealed.S'), '-o', str(tmp / 'sealed.o')], check=True)
    se = tmp / 'sealed.elf'
    image = tmp / 'sealed.bin'
    subprocess.run(['arm-none-eabi-ld', '-Ttext=0x8000', str(tmp / 'sealed.o'), '-o', str(se)], check=True)
    subprocess.run(['arm-none-eabi-objcopy', '-O', 'binary', str(se), str(image)], check=True)
    seal = profile_identity.seal_samples(se, image, a.toolchain, bolt / 'overlay/llvm/patches/atfe')
    Path(str(image) + '.manifest.json').write_text(json.dumps(seal))
    raw = dump_text(build=image_hash(str(se), 0x8000, 0x8004), hi=0x8004,
                    modes=1, event=0, period=0, timer=(50, 0, 0))
    raw = '\n'.join(l for l in raw.splitlines() if not l.startswith('DUMPEND')) + '\n'
    pcfile = tmp / 'profile.samples'
    def capture_transport(cmd, **kw):
        Path(cmd[cmd.index('--log') + 1]).write_text(raw)
        return subprocess.CompletedProcess(cmd, 0, '', '')
    argv = ['collector', str(image), str(se), str(pcfile), '--cycles', '1',
            '--lkperf-scripts', str(lk / 'scripts'), '--', 'profiler bench 1']
    stdout = io.StringIO()
    with patch.object(sys, 'argv', argv), patch.object(collector.subprocess, 'run', capture_transport), contextlib.redirect_stdout(stdout):
        rc = collector.main()
    capture = json.loads(Path(str(pcfile) + '.manifest.json').read_text())
    profile_identity.check_capture(str(pcfile) + '.manifest.json', pcfile, se, 'pi-pc-capture')
    results['bolt_collector_missing_footer'] = dict(
        exit_code=rc, verified_binding=capture['verified_binding'], dumps=capture['dumps'],
        downstream_identity_accepted=True, summary=stdout.getvalue().splitlines()[0])

    results['suite_duplicate_metric'] = suite.parse(
        '$ __SUITE_START__\nbolt_bench: x done (100 cycles)\nbolt_bench: x done (1 cycles)\n')[0]
    csvfile = tmp / 'suite.csv'
    def suite_transport(cmd, **kw):
        # Image 2 loses metric y; both images lose all result checksums.
        path = Path(cmd[cmd.index('--log') + 1])
        text = '$ __SUITE_START__\nbolt_bench: x done (100 cycles)\n'
        if 'base' in path.name:
            text += 'bolt_bench: y done (100 cycles)\n'
        path.write_text(text)
        return subprocess.CompletedProcess(cmd, 0, '', '')
    argv = ['suite', '--out', str(csvfile), '--rounds', '1', '--runs', '2',
            'base=unused1.bin', 'candidate=unused2.bin', '--', 'bolt_bench composite']
    stdout = io.StringIO()
    with patch.object(sys, 'argv', argv), patch.object(suite.subprocess, 'run', suite_transport), contextlib.redirect_stdout(stdout):
        rc = suite.main()
    results['suite_missing_metrics_and_results'] = dict(
        exit_code=rc, requested_passes_per_image=2, recorded_passes_per_image=1,
        summary=[l for l in stdout.getvalue().splitlines() if 'results identical' in l or l.startswith('total')],
        csv=csvfile.read_text())
print(json.dumps(results, indent=2))
