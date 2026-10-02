#!/usr/bin/env python3
"""Record small AArch32 admission probes without changing source or using hardware.

A successful exit means the audit ran, not that the backend is correct. Inspect
results.json for admissions/crashes and compare with CORRECTNESS_REVIEW_0038.md.
All generated files go in a new output directory; existing output is preserved.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('review_redirect', ROOT / 'scripts/redirect-bolt-entries.py')
redirect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(redirect)


def function(name, isa, body):
    return (f'.balign 4\n.{isa}\n.global {name}\n.type {name},%function\n'
            + ('.thumb_func\n' if isa == 'thumb' else '')
            + f'{name}:\n{body}\n.size {name},.-{name}\n')


def run(directory, label, command):
    process = subprocess.run([str(arg) for arg in command], capture_output=True, text=True)
    (directory / (label + '.log')).write_text(process.stdout + process.stderr)
    return process


def word(data, sections, address):
    for base, offset, size in sections.values():
        if base <= address and address + 4 <= base + size:
            return struct.unpack_from('<I', data, offset + address - base)[0]
    raise ValueError(f'no section contains 0x{address:x}')


def branch_target(instruction, address):
    if instruction & 0x0e000000 != 0x0a000000:
        raise ValueError('expected an A32 direct branch')
    immediate = instruction & 0xffffff
    if immediate & 0x800000:
        immediate -= 1 << 24
    return address + 8 + (immediate << 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    tc, out = args.toolchain.resolve(), args.out.resolve()
    runtime = tc.parent / 'bolt-rt-baremetal-arm/libbolt_rt_baremetal.a'
    if not runtime.is_file():
        parser.error(f'missing bare-metal runtime: {runtime}')
    if out.exists():
        parser.error('output already exists; use a fresh directory')
    out.mkdir(parents=True)
    rows = []
    for case in ('armv7-control', 'thumb-entry', 'armv6', 'missing-attributes',
                 'be8-flag', 'static-pie', 'interior-direct', 'interior-pointer', 'svc-exclusive'):
        directory = out / case
        directory.mkdir()
        isa = 'thumb' if case == 'thumb-entry' else 'arm'
        arch = 'armv6' if case == 'armv6' else 'armv7-a'
        body = 'push {r4,lr}\nbl callee\npop {r4,pc}'
        extra = ''
        if case.startswith('interior-'):
            call = ('bl reservation+12' if case == 'interior-direct' else
                    'movw r7,:lower16:reservation+12\nmovt r7,:upper16:reservation+12\nblx r7')
            body = 'push {r4,lr}\n' + call + '\npop {r4,pc}'
            extra = function('reservation', 'arm',
                'ldrex r4,[r6]\nstrex r5,r4,[r6]\nbx lr\n'
                'push {r4-r8,lr}\nldrex r4,[r6]\nbl callee\nstrex r5,r4,[r6]\npop {r4-r8,pc}')
        if case == 'svc-exclusive':
            body = ('movw r7,:lower16:callee\nmovt r7,:upper16:callee\n'
                    'ldrex r4,[r6]\nsvc #0\nstrex r5,r4,[r6]\nbx lr')
        assembly = ('.syntax unified\n.arch ' + arch + '\n.text\n'
                    + function('_start', isa, body) + extra
                    + function('callee', isa, 'cmp r0,#0\nbeq .Lexit\nadd r0,r0,#1\n.Lexit:\nbx lr'))
        (directory / 'input.s').write_text(assembly)
        (directory / 'layout.ld').write_text('ENTRY(_start)\nSECTIONS { . = 0x8000; .text : { *(.text*) } }\n')
        for name, command in (
            ('mc', [tc / 'llvm-mc', '-triple=' + ('armv6' if case == 'armv6' else 'armv7') + '-none-eabi',
                    '-arm-add-build-attributes', '-filetype=obj', directory / 'input.s', '-o', directory / 'input.o']),
            ('link', [tc / 'ld.lld', '--emit-relocs', '-T', directory / 'layout.ld',
                      *(['-pie'] if case == 'static-pie' else []), directory / 'input.o', '-o', directory / 'input.elf'])):
            process = run(directory, name, command)
            if process.returncode:
                raise RuntimeError(process.stderr)
        image = directory / 'input.elf'
        if case == 'missing-attributes':
            process = run(directory, 'remove-attributes', [tc / 'llvm-objcopy', '--remove-section=.ARM.attributes', image])
            if process.returncode:
                raise RuntimeError(process.stderr)
        if case == 'be8-flag':
            data = bytearray(image.read_bytes())
            struct.pack_into('<I', data, 36, struct.unpack_from('<I', data, 36)[0] | 0x00800000)
            image.write_bytes(data)
        run(directory, 'header', [tc / 'llvm-readelf', '-h', '-A', image])
        modes = [('instrument', 'unselected'), ('instrument', 'explicit-skip')] if extra else (
            [('instrument', 'unselected')] if case == 'svc-exclusive' else [('optimize', 'all'), ('instrument', 'all')])
        for mode, selection in modes:
            name = mode + '-' + selection
            candidate, mapping = directory / (name + '.elf'), directory / (name + '.map')
            command = [tc / 'llvm-bolt', image, '-o', candidate, '--no-huge-pages', '-lite=0',
                       '--emit-function-map=' + str(mapping)]
            command += ['--skip-funcs=_start,reservation'] if selection == 'explicit-skip' else [
                '--funcs=callee' if selection == 'unselected' else '--funcs=.*']
            if mode == 'instrument':
                command += ['--instrument', '--instrument-calls=false',
                            '--arm-instrumentation-contract=privileged-single-core-no-fiq',
                            '--instrumentation-sleep-time=1', '--runtime-instrumentation-lib=' + str(runtime)]
            process = run(directory, name, command)
            row = dict(case=case, mode=mode, selection=selection, returncode=process.returncode,
                       output=candidate.exists(), input_sha256=hashlib.sha256(image.read_bytes()).hexdigest())
            if candidate.exists():
                run(directory, name + '-disasm', [tc / 'llvm-objdump', '-d', '--triple=armv7-none-eabi', candidate])
                run(directory, name + '-elf', [tc / 'llvm-readelf', '-h', '-S', '-r', '-d', candidate])
            if extra and process.returncode == 0:
                symbols = redirect.function_symbols(str(tc / 'llvm-readelf'), str(image))
                base = symbols['reservation'][0][0]
                old = symbols['callee'][0][0]
                sections = redirect.fix.sections(str(tc / 'llvm-readelf'), str(candidate))
                raw = candidate.read_bytes()
                raw_target = branch_target(word(raw, sections, base + 20), base + 20)
                if raw_target != old:
                    raise ValueError('unexpected original callee route; inspect fresh output')
                process = run(directory, name + '-redirect', ['python3', ROOT / 'scripts/redirect-bolt-entries.py',
                    candidate, '--original', image, '--map', mapping, '--func', 'callee', '--select-emitted',
                    '--instrumented', '--toolchain', tc, '--report', directory / (name + '-redirect.json')])
                if process.returncode:
                    raise RuntimeError(process.stdout + process.stderr)
                record = json.loads((directory / (name + '-redirect.json')).read_text())['redirected'][0]
                data = candidate.read_bytes()
                target = branch_target(word(data, sections, old), old)
                stores = [address for address in range(target, target + record['output_size'], 4)
                          if word(data, sections, address) & 0xffff0fff in (0xe5800000, 0xe5800004)]
                row.update(interior_entry=base + 12, live_call=base + 20, original_callee=old,
                           instrumented_callee=target, route_verified=target == record['output'] and len(stores) >= 2,
                           counter_store_addresses=stores)
                run(directory, name + '-redirected-disasm', [tc / 'llvm-objdump', '-d', candidate])
            if candidate.exists():
                row['output_sha256'] = hashlib.sha256(candidate.read_bytes()).hexdigest()
            rows.append(row)
            print(case, mode, selection, row['returncode'], 'output=' + str(row['output']), flush=True)
    result = dict(schema=1, toolchain=str(tc), tool_sha256=hashlib.sha256((tc / 'llvm-bolt').read_bytes()).hexdigest(),
                  runtime_execution_verified=False, audit_ran=True, rows=rows)
    (out / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Audit observations saved to', out / 'results.json')


if __name__ == '__main__':
    main()
