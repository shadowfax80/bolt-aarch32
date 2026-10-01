#!/usr/bin/env python3
"""Emit the whole LK image with explicit, scoped original-entry redirection.

Emission is not a hardware correctness result. Run full_image_verify.py afterward.
Profiles are intentionally not discovered automatically from a variants directory.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('redirect_entries', ROOT / 'scripts/redirect-bolt-entries.py')
redirect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(redirect)


def check_restoration(original, output, toolchain):
    before = redirect.fix.sections(str(toolchain / 'llvm-readelf'), str(original))
    after = redirect.fix.sections(str(toolchain / 'llvm-readelf'), str(output))
    input_bytes, output_bytes = original.read_bytes(), output.read_bytes()
    names = list(redirect.fix.RESTORE_RENAME)
    names += [(name, name) for name in redirect.fix.RESTORE_SAME_NAME]
    restored = []
    for output_name, input_name in names:
        if input_name not in before:
            continue
        if output_name not in after:
            raise ValueError(f'missing restored section {output_name}')
        ia, io, iz = before[input_name]
        oa, oo, oz = after[output_name]
        if (ia, iz) != (oa, oz) or io + iz > len(input_bytes) or oo + oz > len(output_bytes):
            raise ValueError(f'restored section {output_name} address/size differs or is truncated')
        if input_bytes[io:io + iz] != output_bytes[oo:oo + oz]:
            raise ValueError(f'restored section {output_name} bytes differ')
        restored.append(output_name)
    return restored


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('outdir', type=Path)
    workspace = Path(os.environ.get('BOLT_WORKSPACE', str(Path.home() / 'bolt-aarch32')))
    parser.add_argument('--input', type=Path, default=workspace / 'build-atfe/variants/baseline.elf')
    parser.add_argument('--toolchain', type=Path, default=workspace / 'build-atfe/bin')
    parser.add_argument('--redirect-functions', required=True,
                        help='exact comma-separated emitted names whose original entries will branch to new code')
    raw = sys.argv[1:]
    split = raw.index('--') if '--' in raw else len(raw)
    args = parser.parse_args(raw[:split])
    extra = raw[split + 1:]
    keys = [a.lstrip('-').split('=')[0] for a in extra]
    if any(k.startswith('funcs') or k in ('data', 'o', 'emit-function-map', 'instrument', 'instrument-calls') for k in keys):
        parser.error('selection/profile/output/instrumentation overrides are not supported by this builder')
    if os.environ.get('FDATA') or os.environ.get('BOLT_FDATA'):
        parser.error('profiles require explicit image binding; this builder currently runs without a profile')
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    names = ('baseline.elf', 'baseline.bin', 'baseline_full.elf', 'baseline_full.bin', 'full.funcmap', 'full_manifest.json')
    if any((out / name).exists() for name in names):
        parser.error('use a fresh output directory; existing verification artifacts are preserved')
    tc = args.toolchain.resolve()
    original = args.input.resolve()
    elf, mapping, report = out / 'baseline_full.elf', out / 'full.funcmap', out / 'full_manifest.json'
    baseline = out / 'baseline.elf'
    shutil.copy2(original, baseline)

    def run(name, command):
        process = subprocess.run([str(x) for x in command], capture_output=True, text=True)
        (out / f'{name}.log').write_text(process.stdout + process.stderr, encoding='utf-8')
        if process.returncode:
            raise ValueError(f'{name} failed ({process.returncode}); see {out / (name + ".log")}')
        return process.stdout

    bolt_options = ['--no-huge-pages', '-lite=0', '-reorder-blocks=ext-tsp', '-reorder-functions=hfsort+', '-icf=all', *extra]
    run('full', [tc / 'llvm-bolt', baseline, '-o', elf, *bolt_options, f'--emit-function-map={mapping}'])
    run('fix-paddr', [sys.executable, ROOT / 'scripts/fix-kernel-elf-paddr.py', elf])
    run('fix-entry', [sys.executable, ROOT / 'scripts/fix-kernel-elf-entry.py', elf, '--original', baseline, '--readelf', tc / 'llvm-readelf'])
    run('fix-sections', [sys.executable, ROOT / 'scripts/fix-kernel-elf-sections.py', elf, '--original', baseline, '--readelf', tc / 'llvm-readelf'])
    restored = check_restoration(baseline, elf, tc)
    run('redirect', [sys.executable, ROOT / 'scripts/redirect-bolt-entries.py', elf,
                     '--original', baseline, '--map', mapping, '--func', args.redirect_functions,
                     '--select-emitted', '--toolchain', tc, '--report', report])
    run('baseline-objcopy', [tc / 'llvm-objcopy', '-O', 'binary', baseline, out / 'baseline.bin'])
    run('objcopy', [tc / 'llvm-objcopy', '-O', 'binary', elf, out / 'baseline_full.bin'])
    functions = redirect.function_symbols(str(tc / 'llvm-readelf'), str(baseline))
    symbols = redirect.nm_symbols(str(tc / 'llvm-nm'), str(baseline))
    if 'bolt_sample_buf' not in symbols or symbols['bolt_sample_buf'][1] != 0x80000:
        raise ValueError('missing or unexpected LK sample buffer')
    manifest = json.loads(report.read_text())
    manifest.update(binary_sha256=redirect.sha256(out / 'baseline_full.bin'),
                    baseline_binary_sha256=redirect.sha256(out / 'baseline.bin'),
                    sample_buffer=dict(address=symbols['bolt_sample_buf'][0], size=symbols['bolt_sample_buf'][1]),
                    restored_sections=restored, bolt_options=bolt_options,
                    tool_sha256={name: redirect.sha256(tc / name) for name in ('llvm-bolt', 'llvm-objcopy', 'llvm-readelf')},
                    patch_sha256={p.name: redirect.sha256(p) for p in sorted((ROOT / 'overlay/llvm/patches/atfe').glob('*.patch'))},
                    input_functions=[dict(name=name, address=a, size=s, thumb=t)
                                     for name, definitions in functions.items() for a, s, t in sorted(set(definitions))])
    emitted_names = {redirect.symbol_name(row['name']) for row in manifest['emitted']}
    manifest['not_emitted'] = sorted(set(functions) - emitted_names)
    report.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    stats = (f'input functions: {len(manifest["input_functions"])}; emitted: {len(manifest["emitted"])}; '
             f'original entries redirected: {len(manifest["redirected"])}; execution verified: no\n'
             'Run full_image_verify.py to check results and observed execution.\n')
    (out / 'full_stats.txt').write_text(stats)
    print(stats, end='')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f'error: {error}')
