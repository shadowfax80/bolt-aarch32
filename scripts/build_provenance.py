#!/usr/bin/env python3
"""Clean-build provenance and assertion-mode parity for the ATFE BOLT backend.

Run in WSL after scripts/clean-build-atfe.sh <clean-dir> on off:

  python3 scripts/build_provenance.py --clean /home/user/bolt-clean \
      --work <fresh dir> --out docs/results/<name>.json

Binds the clean build to exact source, configuration and tools, and compares
it with the live builds (build-atfe = assertions on, build-atfe-noassert =
off):

- repository: commit; overlay series, CMake cache file and these scripts
  must be unmodified;
- source: the clean tree is the pinned base fetched from its remote plus the
  overlay series; every path's contents must equal the live tree's (git tree
  of the live tree computed in a temporary index, the live tree and its index
  are not touched); file-mode differences, which patches cannot carry, are
  listed;
- configuration: the CMake caches of all four builds, normalised, and the
  keys in which they differ;
- tools: host tool versions; hashes of the built binaries;
- tests: ARM BOLT lit suite in every build;
- parity: the same BOLT jobs on the certified LK input with every build,
  whose outputs must be byte-identical apart from .note.bolt_info (it records
  the llvm-bolt path and command line) and identical when run twice (G1
  full-image layout, SMP and single-core instrumentation, random split +
  ICF), and the no-FPU guard on
  every ELF output.

Binary identity of the tools themselves is recorded, not required: builds
in different directories embed their paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
LIVE_SRC = ROOT / 'third_party' / 'llvm-project-atfe'
FIXTURE = ROOT / 'fixtures' / 'lk-rpi4-bolt-test-424606a8.elf'
RUNTIME = ROOT / 'build-atfe' / 'bolt-rt-baremetal-arm' / 'libbolt_rt_baremetal.a'
G1_REDIRECT = 'bolt_bench_interwork,bolt_bench_memcpy'
G1_SKIP = ('arm_reset,arm_secondary_setup,arm_undefined,arm_syscall,arm_prefetch_abort,'
           'arm_data_abort,arm_irq,arm_fiq,bcopy,bzero')
BOUND_PATHS = ['overlay/llvm/patches/atfe', 'cmake', 'scripts/clean-build-atfe.sh',
               'scripts/build_provenance.py', 'scripts/check-no-fpu.sh',
               'scripts/pi4/full_image_build.py', 'scripts/resolve-base.sh']
TOOLS = ['llvm-bolt', 'merge-fdata', 'ld.lld', 'clang', 'llvm-mc', 'llvm-objcopy',
         'llvm-objdump', 'llvm-readelf', 'llvm-nm']
METADATA = ['.applied-overlay-patches', '.overlay-source-ok']


def run(args, cwd=None, env=None, check=True):
    p = subprocess.run([str(a) for a in args], cwd=cwd, env=env, capture_output=True, text=True)
    if check and p.returncode:
        raise SystemExit(f'{args[0]} failed ({p.returncode}): {p.stderr.strip()[:2000]}')
    return p


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def git(directory, *args, env=None):
    return run(['git', '-C', directory, *args], env=env).stdout.strip()


def repository():
    status = git(ROOT, 'status', '--porcelain', '--', *BOUND_PATHS)
    return {'commit': git(ROOT, 'rev-parse', 'HEAD'), 'bound_paths': BOUND_PATHS,
            'bound_paths_clean': not status, 'status': status.splitlines()}


def base():
    out = run(['bash', '-c', 'BASE=atfe; source scripts/resolve-base.sh; echo "$LLVM_COMMIT $LLVM_REMOTE"'],
              cwd=ROOT).stdout.split()
    return {'pin': out[0], 'remote': out[1]}


def patches():
    items = [{'name': p.name, 'sha256': sha256(p)}
             for p in sorted((ROOT / 'overlay/llvm/patches/atfe').glob('*.patch'))]
    series = hashlib.sha256(''.join(f"{i['name']} {i['sha256']}\n" for i in items).encode()).hexdigest()
    return {'count': len(items), 'first': items[0]['name'], 'last': items[-1]['name'],
            'series_sha256': series, 'patches': items}


def live_tree_hash():
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / 'index'))
        git(LIVE_SRC, 'read-tree', 'HEAD', env=env)
        git(LIVE_SRC, 'add', '-A', '--', '.', *[f':!{m}' for m in METADATA], env=env)
        return git(LIVE_SRC, 'write-tree', env=env)


def source(clean, pin):
    src = clean / 'src'
    head = git(src, 'rev-parse', 'HEAD')
    recorded = (clean / 'source-tree.txt').read_text().strip()
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / 'index'))
        git(src, 'read-tree', 'HEAD', env=env)
        git(src, 'add', '-A', '--', '.', env=env)
        now = git(src, 'write-tree', env=env)
    live = live_tree_hash()

    def listing(directory, tree):
        res = {}
        for line in git(directory, 'ls-tree', '-r', '-z', tree).split('\0'):
            if line:
                meta, path = line.split('\t', 1)
                mode, _, blob = meta.split()
                res[path] = (mode, blob)
        return res
    a, b = listing(src, recorded), listing(LIVE_SRC, live)
    content = {p: v[1] for p, v in a.items()} == {p: v[1] for p, v in b.items()}
    # The file-slice patches carry no file modes; record where they differ.
    modes = sorted(f'{p}: clean {a[p][0]}, live {b[p][0]}'
                   for p in a.keys() & b.keys() if a[p][0] != b[p][0])
    return {'clean_head': head, 'clean_head_is_pin': head == pin, 'clean_tree': recorded,
            'clean_tree_unchanged_since_build': now == recorded, 'live_tree': live,
            'paths': len(a), 'live_equals_clean': live == recorded,
            'live_contents_equal_clean': content, 'mode_only_differences': modes,
            'live_head': git(LIVE_SRC, 'rev-parse', 'HEAD')}


def cmake_cache(build, placeholders):
    entries = {}
    for line in (build / 'CMakeCache.txt').read_text().splitlines():
        m = re.match(r'([^#/][^:=]*):([A-Z]+)=(.*)$', line)
        if not m or m.group(2) in ('INTERNAL', 'STATIC'):
            continue
        value = m.group(3)
        for path, name in placeholders:
            value = value.replace(str(path), name)
        entries[m.group(1)] = value
    return entries


KEY_ENTRIES = ['CMAKE_BUILD_TYPE', 'LLVM_ENABLE_ASSERTIONS', 'LLVM_ABI_BREAKING_CHECKS',
               'LLVM_ENABLE_PROJECTS', 'LLVM_TARGETS_TO_BUILD', 'BOLT_TARGETS_TO_BUILD',
               'BOLT_ENABLE_RUNTIME', 'LLVM_USE_LINKER', 'LLVM_CCACHE_BUILD',
               'CMAKE_C_COMPILER', 'CMAKE_CXX_COMPILER', 'LLVM_PARALLEL_LINK_JOBS',
               'LLVM_ENABLE_IO_SANDBOX', 'CMAKE_CXX_FLAGS', 'CMAKE_CXX_FLAGS_RELEASE']


def configuration(builds, clean):
    caches = {}
    for name, build in builds.items():
        src = clean / 'src' if name.startswith('clean') else LIVE_SRC
        caches[name] = cmake_cache(build, [(build, '<BUILD>'), (src, '<SRC>')])
    pairs = [('clean-on', 'clean-off'), ('clean-on', 'live-on'), ('clean-off', 'live-off'),
             ('live-on', 'live-off')]
    diffs = {}
    for a, b in pairs:
        keys = sorted(set(caches[a]) | set(caches[b]))
        diffs[f'{a} vs {b}'] = {k: [caches[a].get(k), caches[b].get(k)]
                               for k in keys if caches[a].get(k) != caches[b].get(k)}
    return {'cache_file': 'cmake/llvm-bolt.cmake',
            'cache_file_sha256': sha256(ROOT / 'cmake/llvm-bolt.cmake'),
            'clean_overrides': {'on': [], 'off': ['LLVM_ENABLE_ASSERTIONS=OFF'],
                                'both': ['CMAKE_C_COMPILER/CMAKE_CXX_COMPILER = host clang/clang++ '
                                         '(not chosen by the cache file; matches the live builds)',
                                         'LLVM_PARALLEL_LINK_JOBS=2 (scheduling only)',
                                         'environment CCACHE_DISABLE=1 (no cached objects)']},
            'key_entries': {name: {k: c.get(k) for k in KEY_ENTRIES} for name, c in caches.items()},
            'differences': diffs}


def host():
    def version(*cmd):
        p = run(cmd, check=False)
        return (p.stdout or p.stderr).strip().splitlines()[0] if (p.stdout or p.stderr) else None
    osr = dict(re.findall(r'^(\w+)="?([^"\n]*)"?$', Path('/etc/os-release').read_text(), re.M))
    return {'os': osr.get('PRETTY_NAME'), 'kernel': version('uname', '-r'),
            'clang': version('clang', '--version'), 'clang++': version('clang++', '--version'),
            'ld.lld': version('ld.lld', '--version'), 'cmake': version('cmake', '--version'),
            'ninja': version('ninja', '--version'), 'python3': version('python3', '--version'),
            'git': version('git', '--version'), 'ccache': version('ccache', '--version')}


def tools(builds):
    res = {}
    for name, build in builds.items():
        entry = {t: sha256(build / 'bin' / t) if (build / 'bin' / t).exists() else None for t in TOOLS}
        entry['llvm-bolt --version'] = run([build / 'bin/llvm-bolt', '--version']).stdout.strip().splitlines()[:6]
        res[name] = entry
    return res


def lit(builds):
    res = {}
    for name, build in builds.items():
        p = run([build / 'bin/llvm-lit', '-sv', build / 'tools/bolt/test/ARM'], check=False)
        text = p.stdout + p.stderr
        counts = dict((k.lower(), int(v)) for k, v in re.findall(r'^\s*(Passed|Failed|Unsupported|Total Discovered Tests)\w*:\s+(\d+)', text, re.M))
        res[name] = {'exit': p.returncode, 'counts': counts,
                     'failed_tests': re.findall(r'^FAIL: BOLT :: (\S+)', text, re.M)}
    return res


def guard(toolchain, elf):
    env = dict(os.environ, NOFPU_TOOLCHAIN=str(toolchain))
    p = run(['bash', ROOT / 'scripts/check-no-fpu.sh', elf], env=env, check=False)
    return {'exit': p.returncode, 'line': (p.stdout + p.stderr).strip().splitlines()[0][:300]}


def scenarios(work, funcs_file):
    lib = str(RUNTIME)
    instr = ['-instrument', '--instrument-calls=false', '--instrumentation-sleep-time=1',
             f'--runtime-instrumentation-lib={lib}', f'--funcs-file={funcs_file}']
    return {
        'g1_full_image': None,  # full_image_build.py, see run_scenario
        'instr_smp': instr + ['--arm-instrumentation-contract=privileged-smp-no-fiq'],
        'instr_single_core': instr + ['--arm-instrumentation-contract=privileged-single-core-no-fiq'],
        'split_random2_icf': ['-funcs=bolt_bench_.*', '-split-functions', '-split-strategy=random2',
                              '-reorder-blocks=reverse', '-icf=all'],
    }


def run_scenario(name, args, build, out):
    out.mkdir(parents=True)
    tc = build / 'bin'
    if name == 'g1_full_image':
        p = run(['python3', ROOT / 'scripts/pi4/full_image_build.py', out / 'img', '--input', FIXTURE,
                 '--toolchain', tc, '--redirect-functions', G1_REDIRECT, '--', f'-skip-funcs={G1_SKIP}'],
                cwd=ROOT, check=False)
        outputs = [out / 'img' / f for f in ('baseline_full.bin', 'baseline_full.elf', 'full.funcmap')]
        elfs = [out / 'img' / 'baseline_full.elf']
    else:
        p = run([tc / 'llvm-bolt', FIXTURE, '-o', out / 'out.elf', '--no-huge-pages', *args], check=False)
        outputs = [out / 'out.elf']
        elfs = outputs
    (out / 'log.txt').write_text(p.stdout + p.stderr)
    res = {'exit': p.returncode,
           'raw_sha256': {f.name: sha256(f) if f.exists() else None for f in outputs},
           'outputs': {f.name: normalized_sha256(tc, f) if f.exists() else None for f in outputs}}
    if p.returncode == 0:
        res['guard'] = {f.name: guard(tc, f) for f in elfs}
    return res


def normalized_sha256(tc, path):
    """SHA-256 of an output without .note.bolt_info, which records the
    llvm-bolt path and the command line and so differs per build directory."""
    if path.suffix != '.elf':
        return sha256(path)
    stripped = path.with_name(path.name + '.nonote')
    run([tc / 'llvm-objcopy', '--remove-section=.note.bolt_info', path, stripped])
    return sha256(stripped)


def parity(builds, work):
    funcs = work / 'bolt_bench_funcs.txt'
    nm = run([builds['live-on'] / 'bin/llvm-nm', FIXTURE]).stdout
    funcs.write_text('\n'.join(sorted(set(re.findall(r' (bolt_bench_\w+)$', nm, re.M)))) + '\n')
    res = {'input': {'path': str(FIXTURE.relative_to(ROOT)), 'sha256': sha256(FIXTURE)},
           'runtime_library': {'path': str(RUNTIME.relative_to(ROOT)), 'sha256': sha256(RUNTIME)},
           'scenarios': {}}
    for name, args in scenarios(work, funcs).items():
        per_build = {b: run_scenario(name, args, build, work / name / b) for b, build in builds.items()}
        # Determinism: the same job again with the same build.
        again = run_scenario(name, args, builds['clean-on'], work / name / 'clean-on-again')
        ref = per_build['clean-on']
        deterministic = again['exit'] == ref['exit'] and again['outputs'] == ref['outputs']
        same = all(r['exit'] == ref['exit'] and r['outputs'] == ref['outputs'] for r in per_build.values())
        guards_ok = all(g['exit'] == 0 for r in per_build.values() for g in r.get('guard', {}).values())
        res['scenarios'][name] = {'identical_across_builds': same, 'deterministic': deterministic,
                                  'exit': ref['exit'], 'guard_ok': guards_ok, 'builds': per_build}
        print(f'{name}: identical={same} deterministic={deterministic} exit={ref["exit"]} '
              f'guard_ok={guards_ok}', flush=True)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--clean', type=Path, required=True)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    clean = a.clean.resolve()
    if a.work.exists():
        raise SystemExit(f'{a.work} exists; use a fresh directory')
    a.work.mkdir(parents=True)
    builds = {'clean-on': clean / 'build-on', 'clean-off': clean / 'build-off',
              'live-on': ROOT / 'build-atfe', 'live-off': ROOT / 'build-atfe-noassert'}
    r = {'schema': 1, 'repository': repository(), 'base': base()}
    r['patches'] = patches()
    r['source'] = source(clean, r['base']['pin'])
    r['configuration'] = configuration(builds, clean)
    r['host'] = host()
    r['tools'] = tools(builds)
    r['lit'] = lit(builds)
    r['parity'] = parity(builds, a.work.resolve())
    lit_ok = all(v['exit'] == 0 and v['counts'].get('failed', 0) == 0 for v in r['lit'].values())
    only_assert = set(r['configuration']['differences']['clean-on vs clean-off']) <= {
        'LLVM_ENABLE_ASSERTIONS', 'LLVM_ENABLE_IO_SANDBOX'}
    checks = {
        'bound_paths_clean': r['repository']['bound_paths_clean'],
        'clean_head_is_pin': r['source']['clean_head_is_pin'],
        'clean_tree_unchanged_since_build': r['source']['clean_tree_unchanged_since_build'],
        'live_source_contents_equal_clean': r['source']['live_contents_equal_clean'],
        'clean_modes_differ_only_in_assertions': only_assert,
        'lit_all_builds': lit_ok,
        'outputs_identical_across_builds': all(s['identical_across_builds'] for s in r['parity']['scenarios'].values()),
        'outputs_deterministic': all(s['deterministic'] for s in r['parity']['scenarios'].values()),
        'scenarios_succeeded': all(s['exit'] == 0 for s in r['parity']['scenarios'].values()),
        'no_fpu_guard_on_outputs': all(s['guard_ok'] for s in r['parity']['scenarios'].values()),
    }
    r['checks'] = checks
    r['pass'] = all(checks.values())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, 'w', newline='\n') as f:
        json.dump(r, f, indent=1)
        f.write('\n')
    for k, v in checks.items():
        print(f'{"ok  " if v else "FAIL"} {k}')
    print('PASS' if r['pass'] else 'FAIL', a.out)
    return 0 if r['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
