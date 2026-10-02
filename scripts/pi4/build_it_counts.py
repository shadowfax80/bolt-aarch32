#!/usr/bin/env python3
"""Build the isolated IT-mask/branch/loop exact-count Pi fixture in WSL."""
from pathlib import Path
import argparse
import importlib.util
import itertools
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
win = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--toolchain', type=Path, default=Path('/home/user/bolt-aarch32/build-atfe/bin'))
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
tc = args.toolchain.resolve()
parent = args.out.resolve()
parent.mkdir(parents=True, exist_ok=True)
out = Path(tempfile.mkdtemp(prefix='build-', dir=parent))
sys.path.insert(0, str(win / 'scripts'))
from profile_identity import elf_metadata, sha256
spec = importlib.util.spec_from_file_location('counter_metadata', win / 'scripts/ram-dump-to-fdata.py')
metadata = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = metadata
spec.loader.exec_module(metadata)
spec = importlib.util.spec_from_file_location('sections', win / 'scripts/fix-kernel-elf-sections.py')
helpers = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helpers
spec.loader.exec_module(helpers)

def run(name, command):
    p = subprocess.run([str(x) for x in command], capture_output=True, text=True)
    (out / (name + '.log')).write_text(p.stdout + p.stderr, encoding='utf-8')
    if not p.returncode == 0:
        raise ValueError((name, p.returncode, (p.stdout + p.stderr)[-3000:]))
    return p.stdout
asm = '.syntax unified\n.arch armv7-a\n.section .text.start,"ax",%progbits\n.arm\n.global _start\n.type _start,%function\n_start:\n cpsid if\n ldr sp,=0x00800000\n bl state_main\n1: wfe\n b 1b\n.size _start,.-_start\n.ltorg\n.text\n.thumb\n'
models = {}
cases = []
names = []

def begin(name):
    global asm
    names.append(name)
    asm += f'.balign 4\n.global {name}\n.type {name},%function\n.thumb_func\n{name}:\n'

def label(name):
    global asm
    asm += f'.Lmodel_{name}:\n'

def end(name):
    global asm
    asm += f'.size {name},.-{name}\n'
for size in range(1, 5):
    for tail in itertools.product('TE', repeat=size - 1):
        mask = 'T' + ''.join(tail)
        name = 'it_' + mask.lower()
        begin(name)
        asm += f'movw r1,#0\ncmp r0,#0\nit{mask[1:].lower()} eq\n'
        for i, sense in enumerate(mask):
            asm += f"add{('eq' if sense == 'T' else 'ne')}.w r1,r1,#{1 << i}\n"
        asm += 'mov r0,r1\nbx lr\n'
        end(name)
        models[name] = [name]
        for arg in (0, 1):
            result = sum((1 << i for i, sense in enumerate(mask) if (sense == 'T') == (arg == 0)))
            cases.append(dict(function=name, arg=arg, result=result, visits={name: 1}, edges={}))
        for width in ('n', 'w'):
            name = 'it_branch_' + mask.lower() + '_' + width
            begin(name)
            asm += 'movw r1,#0\ncmp r0,#0\n' + f'it{mask[1:].lower()} eq\n'
            for i, sense in enumerate(mask[:-1]):
                asm += f"add{('eq' if sense == 'T' else 'ne')}.w r1,r1,#{1 << i}\n"
            label(name + '_branch')
            asm += f"b{('eq' if mask[-1] == 'T' else 'ne')}.w .Lmodel_{name}_taken\n"
            label(name + '_fall')
            asm += 'add.w r0,r1,#0x33\nbx lr\n'
            label(name + '_taken')
            asm += 'add.w r0,r1,#0x77\nbx lr\n'
            end(name)
            models[name] = [name, name + '_fall', name + '_taken']
            for arg in (0, 1):
                taken = (mask[-1] == 'T') == (arg == 0)
                target = name + ('_taken' if taken else '_fall')
                result = sum((1 << i for i, sense in enumerate(mask[:-1]) if (sense == 'T') == (arg == 0))) + (119 if taken else 51)
                cases.append(dict(function=name, arg=arg, result=result, visits={name: 1, target: 1}, edges={name + '>' + target: 1}))
for width in ('n', 'w'):
    name = 'it_loop_' + width
    begin(name)
    asm += 'movw r1,#0\n'
    label(name + '_head')
    asm += 'cmp r0,#0\nit eq\n'
    label(name + '_headbranch')
    asm += f'beq.w .Lmodel_{name}_done\n'
    label(name + '_body')
    asm += 'add.w r1,r1,#3\nsubs.w r0,r0,#1\nit ne\n'
    label(name + '_backbranch')
    asm += f'bne.w .Lmodel_{name}_head\n'
    label(name + '_done')
    asm += 'mov r0,r1\nbx lr\n'
    end(name)
    models[name] = [name, name + '_head', name + '_body', name + '_done']
    for arg in (0, 1, 2, 17, 33):
        visits = {name: 1, name + '_head': max(arg, 1), name + '_body': arg, name + '_done': 1}
        edges = {name + '>' + name + '_head': 1, name + '_head>' + name + '_body': arg, name + '_head>' + name + '_done': int(arg == 0), name + '_body>' + name + '_head': max(arg - 1, 0), name + '_body>' + name + '_done': int(arg > 0)}
        cases.append(dict(function=name, arg=arg, result=3 * arg, visits=visits, edges=edges))
if not (len(names) == 47 and len(cases) == 100):
    raise ValueError('fixture invariant failed')
asm += '\n.data\n.balign 8\n'

def object_decl(name, body):
    return f'.global {name}\n.type {name},%object\n{name}:\n{body}\n.size {name},.-{name}\n'
asm += object_decl('cases', '\n'.join((f".word {c['function']},{c['arg']},{c['result']}" for c in cases)))
asm += object_decl('expected_counts', '.zero ' + str(100 * 128 * 4))
asm += object_decl('counter_base', '.word dummy_counters')
asm += object_decl('counter_count', '.word 1')
asm += object_decl('instrumented', '.word 0')
asm += 'dummy_counters: .zero 8\n'
(out / 'fixture.s').write_text(asm, encoding='utf-8')
(out / 'models.json').write_text(json.dumps(dict(blocks=models, cases=cases), indent=2) + '\n', encoding='utf-8')
run('assembly', [tc / 'llvm-mc', '-triple=armv7-none-eabi', '-arm-add-build-attributes', '--save-temp-labels', '-filetype=obj', out / 'fixture.s', '-o', out / 'fixture.o'])
run('compile', [tc / 'clang', '--target=arm-none-eabi', '-march=armv7-a', '-marm', '-mfloat-abi=soft', '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-O2', '-c', win / 'scripts/pi4/fixtures/it-counts/main.c', '-o', out / 'main.o'])
original = out / 'baseline.elf'
run('link', [tc / 'ld.lld', '--emit-relocs', '--discard-locals', '-T', win / 'scripts/pi4/fixtures/counter-state/link.ld', out / 'fixture.o', out / 'main.o', '-o', original])
original_blob = original.read_bytes()
original_sections, symbols = elf_metadata(original_blob)
symbol_text = run('symbols', [tc / 'llvm-nm', '-a', original])
labels = {p[2]: int(p[0], 16) for line in symbol_text.splitlines() if len((p := line.split())) == 3}
object_text = run('object-symbols', [tc / 'llvm-nm', '-a', out / 'fixture.o'])
text_base = labels['it_t']
labels.update({p[2].removeprefix('.Lmodel_'): text_base + int(p[0], 16) for line in object_text.splitlines() if len((p := line.split())) == 3 and p[2].startswith('.Lmodel_')})
patched = bytearray(original_blob)
patches = []
for name in names:
    if not name.endswith('_n'):
        continue
    sites = [(name + '_branch', name + '_taken', name + '_fall')] if name.startswith('it_branch') else [(name + '_headbranch', name + '_done', name + '_body'), (name + '_backbranch', name + '_head', name + '_done')]
    for site, target, fall in sites:
        address, dest = (labels[site], labels[target])
        section = next((s for s in original_sections if s['name'] == '.text' and s['address'] <= address < address + 4 <= s['address'] + s['size']))
        position = section['offset'] + address - section['address']
        displacement = dest - address - 4
        if not (displacement % 2 == 0 and -(1 << 11) <= displacement < 1 << 11):
            raise ValueError('fixture invariant failed')
        replacement = struct.pack('<HH', 57344 | displacement // 2 & 2047, 48896)
        patches.append(dict(site=site, address=address, target=dest, before_hex=patched[position:position + 4].hex(), after_hex=replacement.hex()))
        patched[position:position + 4] = replacement
        if name.startswith('it_loop') and fall == name + '_done':
            pad = name + '_done_pad'
            labels[pad] = labels[fall] - 2
            models[name].insert(-1, pad)
            for case in cases:
                if case['function'] != name:
                    continue
                count = int(case['arg'] > 0)
                case['visits'][pad] = count
                del case['edges'][name + '_body>' + name + '_done']
                case['edges'][name + '_body>' + pad] = count
                case['edges'][pad + '>' + name + '_done'] = count
        else:
            labels[fall] -= 2
original_blob = bytes(patched)
original.write_bytes(original_blob)
(out / 'narrow-branches.json').write_text(json.dumps(patches, indent=2) + '\n', encoding='utf-8')
(out / 'models.json').write_text(json.dumps(dict(blocks=models, cases=cases, addresses=labels), indent=2) + '\n', encoding='utf-8')
report = {}
for variant, extra in [('normal', []), ('reverse', ['--reorder-blocks=reverse']), ('conservative', ['--conservative-instrumentation'])]:
    print('Building', variant, flush=True)
    candidate = out / (variant + '.elf')
    mapping = out / (variant + '.funcmap')
    log = run(variant + '-instrument', [tc / 'llvm-bolt', original, '-o', candidate, '--no-huge-pages', '-lite=0', '--instrument', '--instrument-calls=false', '--instrumentation-sleep-time=1', '--runtime-instrumentation-lib=' + str(tc.parent / 'bolt-rt-baremetal-arm/libbolt_rt_baremetal.a'), '--funcs=' + ','.join(names), '--emit-function-map=' + str(mapping), *extra])
    counts = re.findall('Total number of counters: (\\d+)', log)
    if not len(counts) == 1:
        raise ValueError('fixture invariant failed')
    n = int(counts[0])
    if not 0 < n <= 128:
        raise ValueError('fixture invariant failed')
    blob = bytearray(candidate.read_bytes())
    sections, _ = elf_metadata(blob)
    counters = next((s for s in sections if s['name'] == '.bolt.instr.counters'))
    for src in original_sections:
        if not src['flags'] & 2 or not src['size']:
            continue
        destname = '.bolt.org.text' if src['name'] == '.text' else src['name']
        dst = next((s for s in sections if s['name'] == destname))
        if not (src['address'], src['size'], src['kind']) == (dst['address'], dst['size'], dst['kind']):
            raise ValueError('fixture invariant failed')
        if src['kind'] != 8:
            blob[dst['offset']:dst['offset'] + dst['size']] = original_blob[src['offset']:src['offset'] + src['size']]
    blob[24:28] = original_blob[24:28]
    rows = {p[0]: tuple((int(x, 16) for x in p[1:])) for line in mapping.read_text(encoding='utf-8').splitlines() if (p := line.split())}
    if not set(rows) == set(names):
        raise ValueError('fixture invariant failed')
    run(variant + '-reference-mc', [tc / 'llvm-mc', '-triple=armv7-none-eabi', '-filetype=obj', '--defsym=counter_arm_address=0', '--defsym=counter_thumb_address=' + str(counters['address']), win / 'scripts/pi4/fixtures/counter-state/reference.s', '-o', out / (variant + '-reference.o')])
    run(variant + '-reference-bytes', [tc / 'llvm-objcopy', '--dump-section=.text.thumb=' + str(out / (variant + '-reference.bin')), out / (variant + '-reference.o')])
    prefix = (out / (variant + '-reference.bin')).read_bytes()[:-4]
    emitted_slots = {}
    for name, (_, address, size) in rows.items():
        sec = next((s for s in sections if 'physical' in s and s['address'] <= address < address + size <= s['address'] + s['size']))
        start = sec['offset'] + address - sec['address']
        body = blob[start:start + size]
        slots = []
        for index in range(n):
            expected = bytearray(prefix)
            target = counters['address'] + index * 8
            expected[18:22] = helpers.encode_thumb_movw(0, target & 65535)
            expected[22:26] = helpers.encode_thumb_movt(0, target >> 16)
            hits = bytes(body).count(expected)
            if not hits <= 1:
                raise ValueError((name, index, 'duplicate snippet'))
            if hits:
                slots.append(index)
        emitted_slots[name] = slots
    tables = next((s for s in sections if s['name'] == '.bolt.instr.tables'))
    ctx = metadata.parse_tables_note(blob, tables['offset'], tables['size'])
    off = 0
    assignments = {}
    seen = set()
    while off < len(ctx.func_descriptions):
        func, nextoff = metadata.FunctionDescription.parse(ctx.func_descriptions, off)
        off = nextoff
        references = [l.counter for l in func.leaf_nodes] + [e.counter for e in func.edges if e.counter != metadata.INFERRED]
        if not (not func.calls and (not seen.intersection(references))):
            raise ValueError('fixture invariant failed')
        seen.update(references)
        if func.edges:
            name = metadata.serialize_loc(ctx.strings, func.edges[0].from_loc).split()[1]
        elif references:
            matches = [name for name, slots in emitted_slots.items() if set(slots) == set(references)]
            if not len(matches) == 1:
                raise ValueError(matches)
            name = matches[0]
        else:
            continue
        if not set(references) == set(emitted_slots[name]):
            raise ValueError((name, references, emitted_slots[name]))
        node_blocks = {}
        blocks = models[name]
        base = labels[name]

        def block_for(offset):
            matches = [b for b in blocks if labels[b] - base <= offset]
            if not matches:
                raise ValueError((name, offset))
            return max(matches, key=lambda b: labels[b])
        for e in func.edges:
            if not metadata.serialize_loc(ctx.strings, e.from_loc).split()[1] == name:
                raise ValueError('fixture invariant failed')
            if not metadata.serialize_loc(ctx.strings, e.to_loc).split()[1] == name:
                raise ValueError('fixture invariant failed')
            sourceblock, targetblock = (block_for(e.from_loc.offset), block_for(e.to_loc.offset))
            if not labels[targetblock] - base == e.to_loc.offset:
                raise ValueError((name, 'target not modeled', e.to_loc.offset))
            for node, block in [(e.from_node, sourceblock), (e.to_node, targetblock)]:
                if not (node not in node_blocks or node_blocks[node] == block):
                    raise ValueError('fixture invariant failed')
                node_blocks[node] = block
            if e.counter != metadata.INFERRED:
                assignments[e.counter] = dict(function=name, edge=sourceblock + '>' + targetblock)
        for leaf in func.leaf_nodes:
            block = node_blocks.get(leaf.node)
            if len(blocks) == 1:
                block = name
            if not block is not None:
                raise ValueError((name, 'unmapped leaf', leaf.node))
            assignments[leaf.counter] = dict(function=name, block=block)
    if not (seen == set(range(n)) and set(assignments) == seen):
        raise ValueError('fixture invariant failed')
    vectors = []
    for case in cases:
        vector = []
        for index in range(n):
            row = assignments[index]
            value = 0 if row['function'] != case['function'] else case['edges'].get(row['edge'], 0) if 'edge' in row else case['visits'].get(row['block'], 0)
            vector.append(value)
        vectors.append(vector)

    def patch_object(name, data):
        obj = next((s for s in symbols if s['name'] == name and s['kind'] == 1))
        if not obj['size'] == len(data):
            raise ValueError('fixture invariant failed')
        sec = next((s for s in sections if s['name'] == '.data' and s['address'] <= obj['address'] < obj['address'] + obj['size'] <= s['address'] + s['size']))
        pos = sec['offset'] + obj['address'] - sec['address']
        blob[pos:pos + len(data)] = data
    patch_object('counter_base', struct.pack('<I', counters['address']))
    patch_object('counter_count', struct.pack('<I', n))
    patch_object('instrumented', struct.pack('<I', 1))
    padded = [value for vector in vectors for value in vector + [0] * (128 - n)]
    patch_object('expected_counts', struct.pack('<' + str(len(padded)) + 'I', *padded))
    candidate.write_bytes(blob)
    run(variant + '-redirect', [sys.executable, win / 'scripts/redirect-bolt-entries.py', candidate, '--original', original, '--map', mapping, '--func', ','.join(names), '--instrumented', '--toolchain', tc, '--report', out / (variant + '-redirects.json')])
    disasm = run(variant + '-disassembly', [tc / 'llvm-objdump', '-d', candidate])
    report[variant] = dict(counters=n, assignments=assignments, expected_counts=vectors)
    print(variant, 'host exact-count model passed, counters', n, flush=True)
for name in ('baseline', *report):
    run(name + '-objcopy', [tc / 'llvm-objcopy', '-O', 'binary', out / (name + '.elf'), out / (name + '.bin')])
files = [p.name for p in out.iterdir() if p.suffix in ('.elf', '.bin', '.funcmap') or p.name.endswith('-redirects.json') or p.name.endswith('-disassembly.log') or (p.name in ('fixture.s', 'models.json', 'narrow-branches.json'))]
manifest = dict(schema=1, kind='pi-it-counts', cases=300, functions=names, variants=report, files={name: sha256(out / name) for name in sorted(files)}, tools={name: sha256(tc / name) for name in ('llvm-bolt', 'llvm-mc', 'clang', 'ld.lld', 'llvm-objcopy')}, main_sha256=sha256(win / 'scripts/pi4/fixtures/it-counts/main.c'), builder_sha256=sha256(Path(__file__)), runtime_sha256=sha256(tc.parent / 'bolt-rt-baremetal-arm/libbolt_rt_baremetal.a'), scope='15 IT masks; narrow/wide terminal IT branches and loops; single-core privileged quiet firmware; no active IRQ/FIQ/SMP')
(out / 'build.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(out / 'build.json')
