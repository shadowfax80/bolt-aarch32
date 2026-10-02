#!/usr/bin/env python3
"""Build an isolated Pi 4 ARM/Thumb instrumentation-state fixture in WSL."""
import argparse
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from profile_identity import elf_metadata, sha256


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='parent of fresh build directories')
    parser.add_argument('--toolchain', type=Path, default=Path('/home/user/bolt-aarch32/build-atfe/bin'))
    variants = parser.add_mutually_exclusive_group()
    variants.add_argument('--return-pop', action='store_true', help='verify decoded ARM/Thumb single-register POP-to-PC returns')
    variants.add_argument('--flag-self-move', action='store_true', help='verify ARM/Thumb flag-writing self-moves and preservation of the other CPU state')
    args = parser.parse_args()
    parent, tc = args.out.resolve(), args.toolchain.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='build-', dir=parent))
    fixture = ROOT / 'scripts/pi4/fixtures/counter-state'
    assembly, reference_asm = fixture/'start.s', fixture/'reference.s'
    if args.return_pop:
        assembly, reference_asm = out/'start-pop.s', out/'reference-pop.s'
        text = (fixture/'start.s').read_text(encoding='utf-8')
        text = text.replace('counter_arm:\n bx lr', 'counter_arm:\n push {lr}\n pop {pc}')
        text = text.replace('counter_thumb:\n nop // Four bytes allow the original entry to hold an explicit B.W redirect.\n bx lr',
                            'counter_thumb:\n push.w {lr}\n pop.w {pc}')
        assembly.write_text(text, encoding='utf-8')
        arm, thumb = (fixture/'reference.s').read_text(encoding='utf-8').split('.section .text.thumb,')
        arm = arm.replace(' bx lr', ' push {lr}\n pop {pc}')
        thumb = thumb.replace(' nop\n bx lr', ' push.w {lr}\n pop.w {pc}')
        reference_asm.write_text(arm+'.section .text.thumb,'+thumb, encoding='utf-8')
    if args.flag_self_move:
        assembly, reference_asm = out/'start-flags.s', out/'reference-flags.s'
        text = (fixture/'start.s').read_text(encoding='utf-8')
        text = text.replace('counter_arm:\n bx lr', 'counter_arm:\n movs r0,r0\n bx lr')
        text = text.replace('counter_thumb:\n nop // Four bytes allow the original entry to hold an explicit B.W redirect.\n bx lr',
                            'counter_thumb:\n movs.w r0,r0\n bx lr')
        assembly.write_text(text, encoding='utf-8')
        arm, thumb = (fixture/'reference.s').read_text(encoding='utf-8').split('.section .text.thumb,')
        arm = arm.replace(' bx lr', 'arm_self_move:\n movs r0,r0\n bx lr')
        thumb = thumb.replace(' nop\n bx lr', ' movs.w r0,r0\n bx lr')
        reference_asm.write_text(arm+'.section .text.thumb,'+thumb, encoding='utf-8')
    env = dict(os.environ, PATH=str(tc) + ':' + os.environ['PATH'])

    def run(name, command):
        result = subprocess.run([str(x) for x in command], capture_output=True, text=True, env=env)
        (out / (name + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
        require(result.returncode == 0, name + ': ' + (result.stdout + result.stderr)[-2400:])
        return result.stdout

    compiler = tc / 'clang'
    runtime = tc.parent / 'bolt-rt-baremetal-arm/libbolt_rt_baremetal.a'
    run('assembly', [tc/'llvm-mc', '-triple=armv7-none-eabi', '-arm-add-build-attributes',
                     '-filetype=obj', assembly, '-o', out/'start.o'])
    run('compile', [compiler, '--target=arm-none-eabi', '-march=armv7-a', '-marm',
                    '-mfloat-abi=soft', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
                    '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-O2',
                    *(['-DFLAG_SELF_MOVE=1'] if args.flag_self_move else []),
                    '-c', fixture/'main.c', '-o', out/'main.o'])
    original, candidate = out/'baseline.elf', out/'instrumented.elf'
    run('link', [tc/'ld.lld', '--emit-relocs', '-T', fixture/'link.ld',
                 out/'start.o', out/'main.o', '-o', original])
    selected = 'counter_arm,counter_thumb'
    mapping = out/'instrumented.funcmap'
    options = ['--no-huge-pages', '-lite=0', '--instrument', '--instrument-calls=false',
               '--arm-instrumentation-contract=privileged-single-core-no-fiq',
               '--instrumentation-sleep-time=1', '--runtime-instrumentation-lib='+str(runtime),
               '--funcs='+selected, '--emit-function-map='+str(mapping)]
    log = run('instrument', [tc/'llvm-bolt', original, '-o', candidate, *options])
    require(re.findall(r'Total number of counters: (\d+)', log) == ['2'], 'expected two leaf counters')
    original_blob = original.read_bytes()
    original_sections, symbols = elf_metadata(original_blob)
    blob = bytearray(candidate.read_bytes())
    candidate_sections, _ = elf_metadata(blob)
    # Keep the firmware entry and all original caller/data bytes. Only the two
    # explicit redirects below enter generated code; no entry-hook emulation.
    for src in original_sections:
        if not src['flags'] & 2 or not src['size']:
            continue
        name = '.bolt.org.text' if src['name'] == '.text' else src['name']
        matches = [s for s in candidate_sections if s['name'] == name]
        require(len(matches) == 1, 'missing original section ' + name)
        dst = matches[0]
        require((dst['address'],dst['size'],dst['kind']) == (src['address'],src['size'],src['kind']),
                'original section moved/resized: ' + name)
        if src['kind'] != 8:
            blob[dst['offset']:dst['offset']+dst['size']] = original_blob[src['offset']:src['offset']+src['size']]
    blob[24:28] = original_blob[24:28]
    counters = next(s for s in candidate_sections if s['name'] == '.bolt.instr.counters')
    require(counters['size'] >= 16 and counters['address'] % 8 == 0, 'unexpected counter layout')
    require(not any(blob[counters['offset']:counters['offset']+16]), 'counters not initially zero')
    run('reference-mc', [tc/'llvm-mc', '-triple=armv7-none-eabi', '-filetype=obj',
                         '--defsym=counter_arm_address='+str(counters['address']),
                         '--defsym=counter_thumb_address='+str(counters['address']+8),
                         reference_asm, '-o', out/'reference.o'])
    rows = {p[0]:tuple(int(x,16) for x in p[1:]) for line in mapping.read_text(encoding='utf-8').splitlines()
            if (p := line.split())}
    require(set(rows) == {'counter_arm','counter_thumb'}, 'unexpected emitted functions')
    for mode in ('arm','thumb'):
        reference = out/('reference-'+mode+'.bin')
        run('reference-'+mode, [tc/'llvm-objcopy', '--dump-section=.text.'+mode+'='+str(reference), out/'reference.o'])
        _, address, length = rows['counter_'+mode]
        section = next(s for s in candidate_sections if 'physical' in s
                       and s['address'] <= address < address+length <= s['address']+s['size'])
        position = section['offset'] + address - section['address']
        require(blob[position:position+length] == reference.read_bytes(), mode+' generated bytes differ from independent assembly')
    (out/'independent-bytes.log').write_text('PASS: complete ARM/Thumb counter bodies match independent assembly\n', encoding='utf-8')

    def patch_object(name, data):
        objects = [s for s in symbols if s['name'] == name and s['kind'] == 1]
        require(len(objects) == 1 and objects[0]['size'] == len(data), 'unexpected object ' + name)
        obj = objects[0]
        section = next(s for s in candidate_sections
                       if s['name'] == '.data' and s['address'] <= obj['address']
                       and obj['address']+obj['size'] <= s['address']+s['size'])
        position = section['offset'] + obj['address'] - section['address']
        blob[position:position+len(data)] = data

    patch_object('counter_slots', struct.pack('<II', counters['address'], counters['address']+8))
    patch_object('expected_delta', struct.pack('<I', 1))
    candidate.write_bytes(blob)
    run('redirect', [sys.executable, ROOT/'scripts/redirect-bolt-entries.py', candidate,
                     '--original', original, '--map', mapping, '--func', selected, '--instrumented',
                     '--toolchain', tc, '--report', out/'redirects.json'])
    # Deliberately broken counter sequences demonstrate that the Pi oracle
    # detects lost carry, IRQ restoration and a clobbered register.
    reference_symbols = run('reference-symbols', [tc/'llvm-nm', '-a', out/'reference.o'])
    offsets = {p[2]:int(p[0],16) for line in reference_symbols.splitlines()
               if len(p := line.split()) == 3 and p[2].startswith('arm_')}
    _, address, length = rows['counter_arm']
    section = next(s for s in candidate_sections if 'physical' in s
                   and s['address'] <= address < address+length <= s['address']+s['size'])
    base = section['offset'] + address - section['address']
    mutations = {'bad-carry':('arm_carry','nop',1,21),
                 'bad-irq':('arm_restore_cpsr','msr cpsr_f,r2',0,15),
                 'bad-register':('arm_restore_r0','mov r0,#0',0,0)}
    if args.flag_self_move:
        mutations['bad-flags'] = ('arm_self_move', 'nop', 0, 15)
    for name,(label,instruction,_,_) in mutations.items():
        asm = out/(name+'.s')
        asm.write_text('.syntax unified\n.arch armv7-a\n.arm\n.text\n'+instruction+'\n',encoding='utf-8')
        run(name+'-mc', [tc/'llvm-mc','-triple=armv7-none-eabi','-filetype=obj',asm,'-o',out/(name+'.o')])
        run(name+'-bytes', [tc/'llvm-objcopy','--dump-section=.text='+str(out/(name+'-instruction.bin')),out/(name+'.o')])
        replacement = (out/(name+'-instruction.bin')).read_bytes()
        require(len(replacement) == 4, 'expected a single A32 mutation')
        mutant = bytearray(candidate.read_bytes())
        position = base + offsets[label]
        require(mutant[position:position+4] == (out/'reference-arm.bin').read_bytes()[offsets[label]:offsets[label]+4],
                'mutation site does not match reference')
        mutant[position:position+4] = replacement
        (out/(name+'.elf')).write_bytes(mutant)
    names = ('baseline', 'instrumented', *mutations)
    for name in names:
        run(name+'-objcopy', [tc/'llvm-objcopy', '-O', 'binary', out/(name+'.elf'), out/(name+'.bin')])
        sections, _ = elf_metadata((out/(name+'.elf')).read_bytes())
        loaded = [s for s in sections if 'physical' in s]
        require(min(s['physical'] for s in loaded) == 0x8000, 'wrong serial load base')
        require(max(s['physical']+s['size'] for s in loaded) < 0x700000, 'firmware overlaps stack/loader')
        require(all(s['physical'] == s['address'] for s in loaded), 'fixture requires MMU-off V=P')
    run('disassembly', [tc/'llvm-objdump', '-d', candidate])
    files = ['baseline.elf','baseline.bin','instrumented.elf','instrumented.bin',
             'instrumented.funcmap','redirects.json','independent-bytes.log','disassembly.log']
    files += [name+suffix for name in mutations for suffix in ('.elf','.bin')]
    if args.return_pop:
        files += ['start-pop.s', 'reference-pop.s']
    if args.flag_self_move:
        files += ['start-flags.s', 'reference-flags.s']
    manifest = dict(schema=1, kind='pi-counter-state', cases=512, cases_per_mode=256,
                    files={name:sha256(out/name) for name in files},
                    fixture={p.name:sha256(p) for p in sorted(fixture.iterdir()) if p.is_file()},
                    tools={name:sha256(tc/name) for name in ('clang','llvm-mc','ld.lld','llvm-bolt','llvm-objcopy')},
                    runtime_sha256=sha256(runtime), builder_sha256=sha256(Path(__file__)),
                    bolt_options=options, counters=dict(address=counters['address'],count=2),
                    negative_cases={name:dict(case_id=case,field=field) for name,(_,_,case,field) in mutations.items()},
                    scope='privileged MMU-off single-core ARM/Thumb leaf insertion; no active ISR, IT, nested, FIQ or SMP execution')
    manifest['return_pop_checked'] = args.return_pop
    manifest['flag_self_move_checked'] = args.flag_self_move
    (out/'build.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(out/'build.json')


if __name__ == '__main__':
    main()
