#!/usr/bin/env python3
"""Prove a bounded rewritten A32 far-call route with an independent QEMU oracle."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

from profile_identity import elf_metadata, sha256, write_json

ROOT = Path(__file__).resolve().parents[1]
SEEDS = [0, 1, 17, 0x7fffffff, 0xffffffff]
ASM = '''.syntax unified
.arch armv7-a
.arm
.section .text.start,"ax",%progbits
.global _start
.type _start,%function
_start:
movw r4,#:lower16:memory_result
movt r4,#:upper16:memory_result
movw r5,#:lower16:cases
movt r5,#:upper16:cases
mov r6,#5
mov r8,sp
.Lcase:
ldr r0,[r5],#4
mov r1,#0
str r1,[r4]
cmp r0,#1
mrs r9,cpsr
bl __ARMv5LongLdrPcThunk_far_away
mrs r10,cpsr
eor r10,r10,r9
tst r10,#0xf0000000
bne .Lflags
cmp sp,r8
bne .Lstack
ldr r2,[r5],#4
cmp r0,r2
bne .Lresult
ldr r3,[r4]
cmp r3,r2
bne .Lmemory
subs r6,r6,#1
bne .Lcase
mov r0,#42
b .Lexit
.Lresult: mov r0,#71
b .Lexit
.Lmemory: mov r0,#72
b .Lexit
.Lflags: mov r0,#73
b .Lexit
.Lstack: mov r0,#74
.Lexit:
mov r7,#1
svc #0
.Lhalt: b .Lhalt
.size _start,.-_start
.global __ARMv5LongLdrPcThunk_far_away
.type __ARMv5LongLdrPcThunk_far_away,%function
__ARMv5LongLdrPcThunk_far_away:
ldr pc,[pc,#-4]
.word far_away
.size __ARMv5LongLdrPcThunk_far_away,.-__ARMv5LongLdrPcThunk_far_away
.section .text.far,"ax",%progbits
.global far_away
.type far_away,%function
far_away:
add r0,r0,#7
str r0,[r4]
bx lr
.size far_away,.-far_away
.data
.balign 4
memory_result: .word 0
cases:
'''
LAYOUT = '''ENTRY(_start)
SECTIONS { . = 0x10000; .text : { *(.text.start) . = . + 0x2100000; *(.text.far) }
. = ALIGN(0x10000); .data : { *(.data) } }
'''


def require(ok, message):
    if not ok:
        raise ValueError(message)


def offset(blob, address, size):
    sections, _ = elf_metadata(blob)
    matches = [s for s in sections if s['kind'] != 8 and s['flags'] & 2
               and s['address'] <= address < address + size <= s['address'] + s['size']]
    require(len(matches) == 1, 'ambiguous/unmapped instruction extent')
    return matches[0]['offset'] + address - matches[0]['address']


def trace_pcs(text):
    # QEMU exec lines describe executed translation blocks, not just decoded bytes.
    return {int(pc, 16) for pc in re.findall(r'^Trace \d+: .*?\[[0-9a-f]+/([0-9a-f]+)/', text, re.M)}


def check_certificate(outcome, required, repeated):
    check_execution(outcome['returncode'], outcome['timed_out'], set(outcome['pcs']), required)
    for address in repeated:
        require(outcome['visits'].get(hex(address)) == len(SEEDS), 'missing/extra seed execution at '+hex(address))


def check_execution(returncode, timed_out, pcs, required):
    require(not timed_out, 'execution timed out')
    require(returncode == 42, 'independent oracle failed: exit ' + str(returncode))
    require(set(required) <= pcs, 'missing rewritten caller/veneer/callee execution')


def route(blob, mapping):
    require(set(mapping) == {'_start', 'far_away'}, 'wrong emitted selection')
    old_start, start, size = mapping['_start']
    old_far, far, far_size = mapping['far_away']
    require(not (start | far) & 3, 'unaligned A32 function')
    require(start != old_start and far != old_far and far_size == 12, 'functions did not move as expected')
    require(struct.unpack_from('<I', blob, 24)[0] == start, 'entry does not select rewritten caller')
    found = []
    for address in range(start, start + size - 3, 4):
        word = struct.unpack_from('<I', blob, offset(blob, address, 4))[0]
        if word >> 24 != 0xeb:
            continue
        delta = (word & 0xffffff) << 2
        if delta & 0x2000000:
            delta -= 0x4000000
        stub = address + 8 + delta
        pos = offset(blob, stub, 12)
        lo, hi, bx = struct.unpack_from('<III', blob, pos)
        require(lo & 0xfff0f000 == 0xe300c000 and hi & 0xfff0f000 == 0xe340c000
                and bx == 0xe12fff1c, 'call does not reach expected MOVW/MOVT/BX veneer')
        immediate = lambda w: (w & 0xfff) | ((w >> 4) & 0xf000)
        require(immediate(lo) | (immediate(hi) << 16) == far, 'veneer names retained/incorrect callee')
        displacement = far - address - 8
        require(not -0x2000000 <= displacement <= 0x1fffffc, 'callee is not beyond direct BL range')
        found.append(dict(call=address, veneer=stub, caller=start, callee=far,
                          original_caller=old_start, original_callee=old_far))
    require(len(found) == 1, 'expected exactly one far call')
    return found[0]


def execute(qemu, image, evidence, name, timeout, tracing=True, cpu_trace=False):
    image_hash = sha256(image)
    trace = evidence / (name + '.trace')
    command = [str(qemu), '-cpu', 'cortex-a15']
    if tracing:
        command += ['-d', 'cpu,exec,nochain' if cpu_trace else 'exec,nochain', '-D', str(trace)]
    command += [str(image)]
    timed_out = False
    try:
        process = subprocess.run(command, capture_output=True, timeout=timeout)
        code, output = process.returncode, process.stdout + process.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out, code = True, None
        output = (exc.stdout or b'') + (exc.stderr or b'')
    (evidence / (name + '.log')).write_bytes(output)
    require(sha256(image) == image_hash, 'executed image changed during run')
    text = trace.read_text() if tracing and trace.exists() else ''
    visits = Counter(int(pc,16) for pc in re.findall(r'^Trace \d+: .*?\[[0-9a-f]+/([0-9a-f]+)/', text, re.M))
    return dict(returncode=code, timed_out=timed_out,
                image_sha256=image_hash, command=command,
                pcs=sorted(trace_pcs(text)), visits={hex(pc):count for pc,count in sorted(visits.items())})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'out/far-execution')
    parser.add_argument('--qemu', default='qemu-arm')
    args = parser.parse_args()
    qemu_path = shutil.which(args.qemu)
    require(qemu_path is not None, 'qemu-arm required; structural checks alone cannot PASS execution')
    qemu, tc = Path(qemu_path).resolve(), args.toolchain.resolve()
    tools = {n: sha256(tc / n) for n in ('llvm-mc', 'ld.lld', 'llvm-bolt')}
    scripts = {str(p.relative_to(ROOT)): sha256(p) for p in (Path(__file__), ROOT / 'scripts/profile_identity.py',
                ROOT / 'scripts/verify-bolt-arm32-veneer.sh')}
    qemu_hash = sha256(qemu)
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    args.out.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
    print('Evidence:', out, flush=True)
    def run(name, command):
        p = subprocess.run([str(x) for x in command], capture_output=True, text=True, timeout=60)
        (out / (name + '.log')).write_text(p.stdout + p.stderr)
        require(p.returncode == 0, name + ' failed: ' + (p.stdout + p.stderr)[-2500:])
        return p.stdout
    (out / 'fixture.s').write_text(ASM + ''.join(f'.word {n},{(n+7)&0xffffffff}\n' for n in SEEDS))
    (out / 'link.ld').write_text(LAYOUT)
    run('assemble', [tc/'llvm-mc', '-triple=armv7-none-eabi', '-arm-add-build-attributes', '-filetype=obj', out/'fixture.s', '-o', out/'fixture.o'])
    run('link', [tc/'ld.lld', '--emit-relocs', '-T', out/'link.ld', out/'fixture.o', '-o', out/'baseline.elf'])
    original = (out/'baseline.elf').read_bytes()
    artifact_hashes = {'baseline.elf': hashlib.sha256(original).hexdigest()}
    original_sections, symbols = elf_metadata(original)
    original_data = next(s for s in original_sections if s['name'] == '.data')
    baseline_entries = [next(s['address'] for s in symbols if s['name'] == n) for n in ('_start','far_away')]
    baseline = execute(qemu, out/'baseline.elf', out, 'baseline', 5)
    check_certificate(baseline, baseline_entries, baseline_entries[1:])
    results = {}
    for mode, extra in [('normal', []), ('reverse', ['--reorder-blocks=reverse'])]:
        image, mapfile = out/(mode+'.elf'), out/(mode+'.map')
        options = ['--no-huge-pages', '-lite=0', '--pad-funcs-before=far_away:0x2100000', '--emit-function-map='+str(mapfile), *extra]
        log = run(mode+'-bolt', [tc/'llvm-bolt', out/'baseline.elf', '-o', image, *options])
        require(re.search(r'removed linker-inserted veneers: [1-9]', log) and re.search(r'Inserted [1-9][0-9]* stubs', log), 'far route was not rewritten')
        mapping = {}
        for line in mapfile.read_text().splitlines():
            name, *values = line.split()
            require(name not in mapping and len(values) == 3, 'duplicate/malformed function map')
            mapping[name] = [int(v, 16) for v in values]
        blob = image.read_bytes()
        sections, _ = elf_metadata(blob)
        data = next(s for s in sections if s['name'] == '.data')
        require((data['address'], data['size']) == (original_data['address'], original_data['size'])
                and blob[data['offset']:data['offset']+data['size']]
                == original[original_data['offset']:original_data['offset']+original_data['size']],
                'independent seed/expected table or memory layout changed')
        artifact_hashes[image.name] = hashlib.sha256(blob).hexdigest()
        artifact_hashes[mapfile.name] = sha256(mapfile)
        witness = route(blob, mapping)
        required = [witness[k] for k in ('caller', 'veneer', 'callee')]
        observed = execute(qemu, image, out, mode, 5)
        require(observed['image_sha256'] == artifact_hashes[image.name], 'route and executed image differ')
        check_certificate(observed, required, required[1:])
        require(witness['original_callee'] not in observed['pcs'], 'original callee also executed')
        faults = {}
        # Independent oracle and timeout admission must reject real executable faults.
        for fault, address, instruction, expected in [
            ('result', witness['callee'], 0xe2800008, 71),
            ('memory', witness['callee']+4, 0xe320f000, 72),
            ('flags', witness['callee'], 0xe2900007, 73),
            ('stack', witness['callee']+4, 0xe24dd008, 74),
            ('bypass', witness['call'], 0xe320f000, 71),
            ('truncated-repetitions', witness['caller']+16, 0xe3a06001, 42),
            ('timeout', witness['callee'], 0xeafffffe, None),
        ]:
            damaged = bytearray(blob)
            position = offset(blob, address, 4)
            original_word = struct.unpack_from('<I', damaged, position)[0]
            expected_word = (0xe5840000 if fault in ('memory','stack') else 0xe3a06005
                             if fault == 'truncated-repetitions' else 0xe2800007)
            require(original_word >> 24 == 0xeb if fault == 'bypass' else original_word == expected_word,
                    'unexpected fault-site instruction '+fault)
            struct.pack_into('<I', damaged, position, instruction)
            path = out/(mode+'-'+fault+'.elf')
            path.write_bytes(damaged)
            artifact_hashes[path.name] = hashlib.sha256(damaged).hexdigest()
            outcome = execute(qemu, path, out, mode+'-'+fault, 0.3 if fault == 'timeout' else 5,
                              tracing=fault == 'truncated-repetitions')
            require(outcome['timed_out'] if expected is None else not outcome['timed_out'] and outcome['returncode'] == expected, 'wrong fault outcome '+mode+'/'+fault)
            try:
                check_certificate(outcome, required, required[1:])
            except ValueError:
                pass
            else:
                raise ValueError('fault accepted '+fault)
            faults[fault] = outcome
        results[mode] = dict(selected=['_start', 'far_away', '__ARMv5LongLdrPcThunk_far_away'],
                             eliminated=['__ARMv5LongLdrPcThunk_far_away'], emitted=mapping,
                             entry_selected=['_start'],
                             route=witness, executed=required, expected_exit=42, observed=observed,
                             options=options, faults=faults)
        print(mode + ': 5 input/result/memory/flags/stack cases; veneer/callee witnessed; 7 faults rejected', flush=True)
    require(tools == {n: sha256(tc/n) for n in tools}, 'tools changed during run')
    require(artifact_hashes == {n: sha256(out/n) for n in artifact_hashes}, 'artifacts changed during verification')
    require(scripts == {n: sha256(ROOT/n) for n in scripts} and sha256(qemu) == qemu_hash, 'verifier/QEMU changed during run')
    require(revision == subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(), 'repository revision changed')
    report = dict(schema=1, verified=True, kind='a32-far-execution', seeds=SEEDS, baseline=baseline,
                  scope='QEMU cortex-a15 Linux user-mode; A32 explicit legacy literal veneer removed and MOVW/MOVT/BX emitted; result, memory, NZCV and SP; no Pi/Thumb/automatic-v7-thunk or whole-kernel claim',
                  repository_revision=revision, tools=tools, scripts=scripts, qemu_sha256=qemu_hash,
                  qemu_version=subprocess.check_output([str(qemu), '--version'], text=True).splitlines()[0],
                  results=results, files={p.name:sha256(p) for p in out.iterdir() if p.is_file()})
    write_json(out/'verification.json', report)
    print('PASS: bounded rewritten far-call execution:', out, flush=True)


if __name__ == '__main__':
    main()
