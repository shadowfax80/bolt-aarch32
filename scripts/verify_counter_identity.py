#!/usr/bin/env python3
"""Exercise counter identity against real ARM/Thumb BOLT fixtures, without hardware."""
import argparse
import contextlib
import copy
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
from unittest.mock import patch

import counter_identity as binding
from profile_identity import check_profile, sha256, write_json


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--toolchain', type=Path, required=True)
    ap.add_argument('--source-replay', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--patch-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'overlay/llvm/patches/atfe')
    args = ap.parse_args(); tc = args.toolchain.resolve(); out = args.out.resolve()
    if out.exists():
        ap.error('preserve existing evidence; choose a new output directory')
    out.mkdir(parents=True); rows = []
    def run(d, name, command):
        p = subprocess.run([str(x) for x in command], capture_output=True, text=True)
        (d / (name + '.log')).write_text(p.stdout + p.stderr)
        if p.returncode:
            raise ValueError(name + ': ' + p.stdout[-1000:] + p.stderr[-2000:])
    def reject(d, name, action):
        try:
            action()
        except (ValueError, KeyError, IndexError, struct.error) as error:
            (d / (name + '.rejection.txt')).write_text(str(error))
            rows.append(dict(case=name, rejected=True)); return
        raise AssertionError('wrong artifact admitted: ' + name)
    for isa, other in [('arm', 'arm'), ('thumb', 'thumb'), ('arm', 'thumb'), ('thumb', 'arm')]:
        d = out / (isa + '-' + other); d.mkdir()
        call = 'bl' if isa == other else 'blx'
        asm = '.syntax unified\n.arch armv7-a\n.text\n'
        for name, mode, body in [('_start', isa, 'push {r4,lr}\n' + call + ' helper\npop {r4,pc}'),
                                 ('helper', other, 'cmp r0,#0\nbeq 1f\nadd r0,r0,#1\n1: bx lr')]:
            asm += '.balign 4\n.' + mode + '\n.global ' + name + '\n.type ' + name + ',%function\n'
            asm += ('.thumb_func\n' if mode == 'thumb' else '') + name + ':\n' + body + '\n.size ' + name + ',.-' + name + '\n'
        (d / 'input.s').write_text(asm)
        (d / 'link.ld').write_text('ENTRY(_start)\nSECTIONS { . = 0x8000; .text : { *(.text*) } }\n')
        run(d, 'mc', [tc / 'llvm-mc', '-triple=armv7-none-eabi', '-arm-add-build-attributes', '-filetype=obj', d / 'input.s', '-o', d / 'input.o'])
        original = d / 'original.elf'
        run(d, 'link', [tc / 'ld.lld', '--emit-relocs', '-T', d / 'link.ld', d / 'input.o', '-o', original])
        for mode, options in [('normal', []), ('reverse', ['--reorder-blocks=reverse']), ('conservative', ['--conservative-instrumentation'])]:
            v = d / mode; v.mkdir(); elf, mapping, image = [v / n for n in ('instrumented.elf', 'functions.map', 'image.bin')]
            run(v, 'instrument', [tc / 'llvm-bolt', original, '-o', elf, '--no-huge-pages', '-lite=0', '--instrument',
                '--instrument-calls=false', '--arm-instrumentation-contract=privileged-single-core-no-fiq',
                '--instrumentation-sleep-time=1', '--runtime-instrumentation-lib=' + str(tc.parent / 'bolt-rt-baremetal-arm/libbolt_rt_baremetal.a'),
                '--funcs=.*', '--emit-function-map=' + str(mapping), *options])
            run(v, 'binary', [tc / 'llvm-objcopy', '-O', 'binary', elf, image])
            build = binding.seal(original, elf, mapping, image, tc, args.patch_dir, args.source_replay)
            write_json(v / 'build.json', build)
            binding.check_build(build, original, elf, mapping, image, tc, args.patch_dir, args.source_replay)
            layout = build['metadata']['counter_layout']
            from profile_identity import elf_metadata
            sections, _ = elf_metadata(elf.read_bytes()); section = next(s for s in sections if s['name'] == '.bolt.instr.counters')
            blob = bytearray(elf.read_bytes()[section['offset']:section['offset'] + section['size']])
            for i in range(layout['count']):
                struct.pack_into('<Q', blob, layout['locations'] - layout['address'] + i * 8, 7)
            dump = v / 'dump.bin'; dump.write_bytes(blob)
            capture_path = v / 'dump.bin.manifest.json'
            capture = dict(schema=1, kind='arm-counter-capture', verified_binding=True, build=build,
                payload_sha256=sha256(dump), range={k: layout[k] for k in ('address', 'size')},
                provenance='synthetic host fixture; no execution or hardware capture')
            write_json(capture_path, capture)
            binding.check_capture(capture_path, dump, original, elf, mapping, tc, args.patch_dir, args.source_replay)
            profile = v / 'profile.fdata'
            command = [sys.executable, Path(__file__).with_name('ram-dump-to-fdata.py'), '--elf', elf, '--dump', dump,
                '--original', original, '--function-map', mapping, '--source-replay', args.source_replay,
                '--patch-dir', args.patch_dir, '--toolchain', tc, '-o', profile]
            run(v, 'convert', command); check_profile(original, profile)
            rows.append(dict(case=isa + '-' + other + '-' + mode, admitted=True, counts=layout['count'],
                original_sha256=sha256(original), instrumented_sha256=sha256(elf), profile_sha256=sha256(profile)))
            check = lambda: binding.check_capture(capture_path, dump, original, elf, mapping, tc, args.patch_dir, args.source_replay)
            # Mutations are confined to copies owned by this verifier.
            for artifact, name in [(original, 'wrong-original'), (elf, 'wrong-instrumented'), (mapping, 'wrong-map'), (dump, 'wrong-dump')]:
                previous = artifact.read_bytes(); artifact.write_bytes(previous + b'!')
                try: reject(v, name, check)
                finally: artifact.write_bytes(previous)
            for name, mutate in [('unbound', lambda c: c.update(verified_binding=False)),
                ('wrong-range', lambda c: c['range'].update(address=layout['address'] + 4)),
                ('wrong-tool', lambda c: c['build']['tools'].update({'llvm-bolt': '0' * 64})),
                ('missing-tools', lambda c: c['build'].update(tools={})),
                ('missing-image-identity', lambda c: c['build']['artifacts'].pop('image')),
                ('wrong-patch', lambda c: c['build']['patches'].update({'unknown.patch': '0' * 64})),
                ('wrong-owner', lambda c: c['build']['metadata']['owners'][0].update(size=999)),
                ('wrong-source-identity', lambda c: c['build'].update(source_identity_sha256='0' * 64))]:
                altered = copy.deepcopy(capture); mutate(altered); write_json(capture_path, altered)
                reject(v, name, check); write_json(capture_path, capture)
            previous = image.read_bytes(); image.write_bytes(previous[:-1] + bytes([previous[-1] ^ 1]))
            reject(v, 'wrong-upload-image', lambda: binding.check_build(build, original, elf, mapping, image, tc, args.patch_dir, args.source_replay)); image.write_bytes(previous)
            previous = dump.read_bytes(); altered = bytearray(previous)
            struct.pack_into('<I', altered, layout['count_address'] - layout['address'], layout['count'] + 1)
            dump.write_bytes(altered); changed = copy.deepcopy(capture); changed['payload_sha256'] = sha256(dump); write_json(capture_path, changed)
            reject(v, 'wrong-count-with-matching-dump-hash', check); dump.write_bytes(previous); write_json(capture_path, capture)
            # Map validation is independent of the sealed hash comparison.
            text = mapping.read_text(); fields = text.splitlines()[0].split()
            for index in (1, 2, 3):
                altered = list(fields); altered[index] = f'{int(altered[index], 16) + 4:x}'
                mapping.write_text(text.replace(text.splitlines()[0], ' '.join(altered), 1))
                reject(v, 'wrong-map-field-' + str(index), lambda: binding.inspect(original, elf, mapping))
                mapping.write_text(text)
            # Mutate metadata itself, independently of any recorded artifact hash.
            original_blob = elf.read_bytes()
            def descriptor_start(name):
                s = next(s for s in sections if s['name'] == name)
                namesz = struct.unpack_from('<I', original_blob, s['offset'])[0]
                return s['offset'] + 12 + (namesz + 3) // 4 * 4
            owner_start = descriptor_start('.bolt.arm.profile')
            source_start = descriptor_start('.bolt.arm.source')
            table_start = descriptor_start('.bolt.instr.tables')
            mutations = [('wrong-source-note', source_start, bytes([original_blob[source_start] ^ 1])),
                ('wrong-owner-size', owner_start + 16, struct.pack('<Q', build['metadata']['owners'][0]['size'] + 1)),
                ('wrong-owner-isa', owner_start + 24, bytes([1 - int(build['metadata']['owners'][0]['thumb'])])),
                ('missing-owner-name', owner_start + 25, struct.pack('<I', 0)),
                ('unsupported-indirect-metadata', table_start, struct.pack('<I', 1))]
            ctx = binding.converter().parse_tables_note(original_blob,
                next(s['offset'] for s in sections if s['name'] == '.bolt.instr.tables'),
                next(s['size'] for s in sections if s['name'] == '.bolt.instr.tables'))
            pos = 0
            for owner in build['metadata']['owners']:
                f, end = binding.converter().FunctionDescription.parse(ctx.func_descriptions, pos)
                if f.edges:
                    edge_start = table_start + 12 + pos + 8 + f.num_leaf_nodes * 8
                    mutations.append(('out-of-range-metadata-location', edge_start + 4, struct.pack('<I', owner['size'])))
                    break
                pos = end
            assert any(n == 'out-of-range-metadata-location' for n, _, _ in mutations)
            for name, offset, data in mutations:
                altered = bytearray(original_blob); altered[offset:offset + len(data)] = data; elf.write_bytes(altered)
                reject(v, name, lambda: binding.inspect(original, elf, mapping))
                elf.write_bytes(original_blob)
            # Late artifact changes must not alter an existing profile/sidecar.
            mod = binding.converter(); write = mod.write_function_profile; changed = [False]
            def mutate_dump(*a, **kw):
                write(*a, **kw)
                if not changed[0]:
                    dump.write_bytes(previous + b'!'); changed[0] = True
            old_profile = profile.read_bytes(); sidecar = Path(str(profile) + '.manifest.json'); old_identity = sidecar.read_bytes()
            with patch.object(sys, 'argv', [str(x) for x in command[1:]]), patch.object(mod, 'write_function_profile', side_effect=mutate_dump), contextlib.redirect_stdout(io.StringIO()):
                reject(v, 'late-dump-change', mod.main)
            assert profile.read_bytes() == old_profile and sidecar.read_bytes() == old_identity
            dump.write_bytes(previous)
    report = dict(schema=1, verified=True, scope='host-generated synthetic captures; no hardware execution',
                  tool_sha256=sha256(tc / 'llvm-bolt'), cases=len(rows), admissions=sum(r.get('admitted', False) for r in rows),
                  rejections=sum(r.get('rejected', False) for r in rows), rows=rows)
    write_json(out / 'results.json', report); print(json.dumps({k: v for k, v in report.items() if k != 'rows'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
