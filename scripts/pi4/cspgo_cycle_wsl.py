#!/usr/bin/env python3
"""Two-round bare-metal IR/CSPGO training using WSL builds and Windows Pi UART.

Claim the HANDOFF live-tree lock and Pi before running. Use an isolated, synced
WSL repo/LK tree. All run outputs are fresh; failures preserve their evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mounted(path):
    path = Path(path).resolve()
    if not re.fullmatch(r"[A-Za-z]:", path.drive):
        raise ValueError("output must be on a local Windows drive mounted in WSL")
    return f"/mnt/{path.drive[0].lower()}/{path.as_posix()[3:]}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wsl-root', required=True, help='isolated synced Linux repo path')
    parser.add_argument('--toolchain', default='/home/user/bolt-aarch32/build-atfe/bin')
    parser.add_argument('--pgo-rt', default='/home/user/bolt-aarch32/build-atfe/pgo-rt-baremetal-arm/libpgo_rt_baremetal.a')
    parser.add_argument('--distro', default='Ubuntu')
    parser.add_argument('--out', required=True, type=Path, help='fresh Windows output directory')
    parser.add_argument('--workload', choices=('stair', 'composite', 'pgo_lab', 'multi'), default='stair')
    parser.add_argument('--make-args', default='STAIR_M=8', help='same LK_MAKE_ARGS for every stage')
    parser.add_argument('--port', default='COM5')
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--runs', type=int, default=2)
    parser.add_argument('--jobs', type=int, default=8)
    parser.add_argument('--fast-loader', type=Path, default=ROOT / 'tools/pi4-serialboot-fast/kernel7l_fast.img')
    args = parser.parse_args()
    if args.rounds < 1 or not 1 <= args.runs <= 32 or args.jobs < 1:
        parser.error('rounds/jobs must be positive; runs must be 1..32')
    for value in (args.wsl_root, args.toolchain, args.pgo_rt):
        if not PurePosixPath(value).is_absolute() or '..' in PurePosixPath(value).parts:
            parser.error('WSL paths must be absolute without parent traversal')
    out = args.out.resolve()
    win_mount = mounted(out)
    out.mkdir(parents=True, exist_ok=False)
    token = hashlib.sha256(str(out).encode()).hexdigest()[:16]
    wout = args.wsl_root + '/build-atfe/cspgo-runs/' + token
    env = dict(os.environ, PI4_WDOG='120', PI4_FAST_LOADER=str(args.fast_loader.resolve()),
               PI4_EVIDENCE_DIR=str(out / 'measurements'))
    def run(argv, name):
        print(name, flush=True)
        result = subprocess.run(list(map(str, argv)), capture_output=True, env=env, timeout=900)
        (out / (name + '.log')).write_bytes(result.stdout)
        (out / (name + '.stderr')).write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f'{name} failed ({result.returncode}); see {out}/{name}.log and .stderr')
        return result.stdout.decode('utf-8', 'replace')
    def wsl(argv, name):
        return run(['wsl', '-d', args.distro, '--cd', args.wsl_root, '--exec', *argv], name)
    wsl(['mkdir', '-p', args.wsl_root + '/build-atfe/cspgo-runs'], 'prepare-parent')
    wsl(['mkdir', wout], 'prepare-run')
    build_env = ['env', 'BASE=atfe', 'LK_PROJECT=rpi4-bolt-test', 'CLANG_BINDIR=' + args.toolchain,
                 'PGO_RT_LIB=' + args.pgo_rt, 'IR_PROFDATA=' + wout + '/ir.profdata',
                 'CS_PROFDATA=' + wout + '/merged.profdata', 'VARIANTS_DIR=' + wout,
                 'LK_MAKE_ARGS=' + args.make_args, 'JOBS=' + str(args.jobs)]
    tools = wsl(['sha256sum', *[args.toolchain + '/' + t for t in ('clang', 'ld.lld', 'llvm-profdata')], args.pgo_rt], 'tool-identity')
    lk_commit = wsl(['git', '-C', 'third_party/lk', 'rev-parse', 'HEAD'], 'lk-identity').strip()
    if lk_commit != '79d2f56096fa32365846ceaba8b4a9d1c6b75cf0':
        raise ValueError('LK source is not at the supported pin; preserve it and use a separate pinned checkout')
    source_paths = [p for folder in ('overlay/lk',) for p in (ROOT / folder).rglob('*') if p.is_file()]
    source_paths += [ROOT / 'scripts' / name for name in ('build-lk-aarch32.sh', 'build-variants.sh',
                     'pgo-build-config.sh', 'pgo_profile.py', 'apply-overlays.sh')]
    source_hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                     for p in source_paths}
    # Compare normalized source files; CRLF normalization is expected in WSL.
    code = "import hashlib,json,pathlib,sys; print(json.dumps({p:hashlib.sha256(pathlib.Path(p).read_bytes().replace(b'\\r\\n',b'\\n')).hexdigest() for p in sys.argv[1:]}))"
    observed = json.loads(wsl(['python3', '-c', code, *source_hashes], 'source-identity'))
    if observed != source_hashes:
        raise ValueError('WSL source differs from this checkout; sync the isolated tree first')
    local_tools = [ROOT / ('scripts/pi4/' + name) for name in
                   ('cspgo_cycle_wsl.py', 'pi4_pgo_collect.py', 'pi4_run.py', 'pi4_serial_boot.py',
                    'pi4_compare.py', 'pgo_lab_measure.py', 'measurement_records.py', 'passes_check.py',
                    'proc_util.py', 'stats_util.py')]
    local_tools += [ROOT / 'scripts/bolt_dump_reassemble.py']
    local_hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in local_tools}
    def build(variant):
        wsl([*build_env, 'bash', 'scripts/build-variants.sh', variant], 'build-' + variant)
        wsl(['cp', *[wout + '/' + variant + ext for ext in ('.bin', '.elf', '.build.log', '.nofpu.log')], win_mount + '/'], 'copy-' + variant)
    def collect(variant, level):
        run([sys.executable, ROOT / 'scripts/pi4/pi4_pgo_collect.py', out / (variant + '.bin'),
             out / (level + '.profraw'), '--workload', args.workload, '--port', args.port,
             '--log-dir', out / (level + '-training')], 'train-' + level)
        wsl(['cp', win_mount + '/' + level + '.profraw', wout + '/'], 'copy-profile-' + level)
        wsl([args.toolchain + '/llvm-profdata', 'merge', wout + '/' + level + '.profraw',
             '-o', wout + '/' + level + '.profdata'], 'index-' + level)
        wsl(['python3', 'scripts/pgo_profile.py', 'validate', wout + '/' + level + '.profdata',
             '--kind', 'ir-only' if level == 'ir' else level, '--profdata', args.toolchain + '/llvm-profdata'], 'validate-' + level)
    build('irpgo-collect')
    collect('irpgo-collect', 'ir')
    build('irpgo_thinlto')
    build('cspgo-collect')
    collect('cspgo-collect', 'cs')
    wsl(['python3', 'scripts/pgo_profile.py', 'merge', wout + '/merged.profdata', '--ir', wout + '/ir.profdata',
         '--cs', wout + '/cs.profdata', '--profdata', args.toolchain + '/llvm-profdata'], 'merge-profiles')
    build('cspgo_thinlto')
    wsl(['cp', wout + '/ir.profdata', wout + '/cs.profdata', wout + '/merged.profdata', win_mount + '/'], 'copy-indexed-profiles')
    measure = 'pgo_lab_measure.py' if args.workload == 'pgo_lab' else 'pi4_compare.py'
    for variant in range(3):
        argv = [sys.executable, ROOT / 'scripts/pi4' / measure, '--out', out / f'variant-{variant}.csv',
                '--rounds', args.rounds, '--runs', args.runs, '--port', args.port, '--args', f'0 {variant}']
        if measure == 'pi4_compare.py':
            argv += ['--workload', args.workload]
        argv += [name + '=' + str(out / (name + '.bin')) for name in ('irpgo_thinlto', 'cspgo_thinlto')]
        run(argv, f'measure-variant-{variant}')
    final_sources = json.loads(wsl(['python3', '-c', code, *source_hashes], 'source-identity-final'))
    if final_sources != observed:
        raise ValueError('WSL sources changed during the cycle')
    if local_hashes != {p.relative_to(ROOT).as_posix(): digest(p) for p in local_tools}:
        raise ValueError('Windows workflow tools changed during the cycle')
    receipt = dict(schema=1, status='PASS', scope='IR/CS profile transport, build and measurement association/output consistency; not backend certification',
                   workload=args.workload, training_variant=0, measured_variants=[0, 1, 2],
                   make_args=args.make_args, wsl_root=args.wsl_root, wsl_output=wout,
                   tool_identity=tools, lk_commit=lk_commit, source_sha256=source_hashes,
                   windows_tool_sha256=local_hashes,
                   artifact_sha256={p.relative_to(out).as_posix(): digest(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: complete cycle and evidence in {out}', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f'error: {error}')
