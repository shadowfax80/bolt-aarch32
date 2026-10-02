#!/usr/bin/env python3
"""Build a bounded ARM/Thumb inlining and branch-semantics Pi fixture in WSL."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'scripts/pi4')]
from profile_identity import elf_metadata, sha256
spec = importlib.util.spec_from_file_location('inline_fixture_sections', ROOT/'scripts/fix-kernel-elf-sections.py')
sections_helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sections_helper
spec.loader.exec_module(sections_helper)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--toolchain', type=Path, default=Path('/home/user/bolt-aarch32/build-atfe/bin'))
    parser.add_argument('--pass-matrix', action='store_true', help='also verify automatic/size-based inlining and peepholes with reverse layout')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='build-', dir=args.out.resolve()))
    tc = args.toolchain.resolve()
    env = dict(os.environ, PATH=str(tc)+':'+os.environ['PATH'])

    def run(label, command):
        p = subprocess.run([str(x) for x in command], capture_output=True, text=True, env=env)
        (out/(label+'.log')).write_text(p.stdout+p.stderr)
        require(p.returncode == 0, label+': '+(p.stdout+p.stderr)[-3000:])
        return p.stdout

    asm = '''.syntax unified
.arch armv7-a
.section .text.start,"ax",%progbits
.arm
.global _start
.type _start,%function
_start:
cpsid if
ldr sp,=0x00800000
bl state_main
1: wfe
b 1b
.size _start,.-_start
.ltorg
.text
'''
    cases, functions, wrappers, callees, inline_expected = [], [], [], [], {}
    inputs = [0, 1, 17, 0x7fffffff, 0xffffffff]
    for isa in ('arm', 'thumb'):
        kinds = ['safe', 'stack', 'lr', 'branch', 'conditional'] if isa == 'arm' else ['safe','stack','lr','branch','cbz','cbnz']
        def function(name, body):
            return (f'.{isa}\n.balign 4\n.global {name}\n.type {name},%function\n'
                    + ('.thumb_func\n' if isa == 'thumb' else '') + name+':\n'+body+'\n.size '+name+',.-'+name+'\n')
        for kind in kinds:
            callee = isa+'_'+kind
            caller = 'caller_'+callee
            functions += [caller, callee]
            wrappers.append(caller)
            callees.append(callee)
            inline_expected[caller] = kind in ('safe', 'branch', 'cbz', 'cbnz')
            add = 'add.w' if isa == 'thumb' else 'add'
            move = 'movw' if isa == 'thumb' else 'mov'
            body = {
                'safe': f'{add} r0,r0,#7\nbx lr',
                'stack': f'push {{lr}}\n{add} r0,r0,#7\npop {{pc}}',
                'lr': 'mov r0,lr\nbx lr',
                'branch': f'cmp r0,#0\nbeq .Lzero_{callee}\n{add} r0,r0,#7\nbx lr\n.Lzero_{callee}:\n{move} r0,#23\nbx lr',
                'conditional': 'cmp r0,#0\nbxeq lr\nadd r0,r0,#7\nbx lr',
                'cbz': f'cbz r0,.Lzero_{callee}\n{add} r0,r0,#7\nbx lr\n.Lzero_{callee}:\n{move} r0,#23\nbx lr',
                'cbnz': f'cbnz r0,.Lzero_{callee}\n{add} r0,r0,#7\nbx lr\n.Lzero_{callee}:\n{move} r0,#23\nbx lr',
            }[kind]
            if kind == 'lr':
                continuation = ('cmp r0,r2\nmovw r0,#0\nit ne\nmovne r0,#1' if isa == 'thumb'
                                else 'cmp r0,r2\nmov r0,#0\nmovne r0,#1')
                wrapper = 'push {r4,lr}\nmov r2,lr\nbl '+callee+'\n'+continuation+'\npop {r4,pc}'
            elif kind in ('cbz','cbnz'):
                # CBZ/CBNZ must preserve the flags established by the caller.
                wrapper = ('push {r4,lr}\ncmp r0,#1\nmrs r3,cpsr\nbl '+callee
                           +'\nmrs r1,cpsr\ncmp r1,r3\nit ne\nmovne r0,#0\npop {r4,pc}')
            else:
                wrapper = 'push {r4,lr}\nbl '+callee+f'\n{add} r0,r0,#11\npop {{r4,pc}}'
            asm += function(caller, wrapper)+function(callee, body)
            for value in inputs:
                expected = (1 if kind == 'lr' else (23 if value == 0 else value+7) if kind == 'cbz'
                            else (23 if value != 0 else value+7) if kind == 'cbnz'
                            else 11 if kind == 'conditional' and value == 0
                            else 34 if kind == 'branch' and value == 0 else value+18)
                cases.append(dict(function=caller, arg=value, expected=expected & 0xffffffff))
    if args.pass_matrix:
        # These call-site boundaries must hold even when a safe callee is
        # eligible under force-inline, inline-all or size-based inlining.
        for kind,body in [
            ('predicated','push {r4,lr}\ncmp r0,#0\nbleq arm_safe\nadd r0,r0,#11\npop {r4,pc}'),
            ('indirect','push {r4,lr}\nmovw r3,#:lower16:arm_safe\nmovt r3,#:upper16:arm_safe\nblx r3\nadd r0,r0,#11\npop {r4,pc}'),
            ('cross','push {r4,lr}\nbl thumb_safe\nadd r0,r0,#11\npop {r4,pc}'),
        ]:
            name = 'caller_arm_'+kind
            asm += f'.arm\n.balign 4\n.global {name}\n.type {name},%function\n{name}:\n{body}\n.size {name},.-{name}\n'
            functions.append(name);wrappers.append(name);inline_expected[name] = False
            for value in inputs:
                expected = value+11 if kind == 'predicated' and value else value+18
                cases.append(dict(function=name,arg=value,expected=expected & 0xffffffff))
    asm += '.data\n.balign 4\n.global case_entries\n.type case_entries,%object\ncase_entries:\n'
    asm += ''.join(f'.word {c["function"]},{c["arg"]},{c["expected"]}\n' for c in cases)
    asm += '.size case_entries,.-case_entries\n'
    (out/'start.s').write_text(asm)
    # Reuse only the loader/UART/watchdog support. The oracle is independent
    # of emitted code: arithmetic results plus stack and CBZ flag checks.
    support = (ROOT/'scripts/pi4/fixtures/counter-state/main.c').read_text()
    support = support[support.index('#define REG'):support.index('void state_main(void)')]
    support = support.replace('BOLT_COUNTER_STATE FAIL', 'BOLT_INLINE_STATE FAIL')
    main_c = '''#include <stdint.h>
struct Case { uint32_t (*fn)(uint32_t); uint32_t arg, expected; };
extern const struct Case case_entries[];
'''+support+'''void state_main(void) {
    watchdog(10);
    uint32_t cpsr, core;
    __asm__ volatile("mrs %0,cpsr" : "=r"(cpsr));
    __asm__ volatile("mrc p15,0,%0,c0,c0,5" : "=r"(core));
    puts_uart("BOLT_INLINE_STATE BEGIN mode="); hex(cpsr & 31);
    puts_uart(" core="); hex(core & 0xff); puts_uart("\\r\\n");
    if ((cpsr & 31) != 0x1a) fail(0,100,0x1a,cpsr & 31);
    if (core & 0xff) fail(0,101,0,core & 0xff);
    for (unsigned i=0;i<55;++i) {
        uint32_t before, after;
        __asm__ volatile("mov %0,sp" : "=r"(before) :: "memory");
        uint32_t actual=case_entries[i].fn(case_entries[i].arg);
        __asm__ volatile("mov %0,sp" : "=r"(after) :: "memory");
        if (actual!=case_entries[i].expected) fail(i,0,case_entries[i].expected,actual);
        if (before!=after || (after & 7)) fail(i,1,before,after);
    }
    puts_uart("BOLT_INLINE_STATE PASS cases=55\\r\\n");
    finish();
}
'''
    case_count, wrapper_count = (70,14) if args.pass_matrix else (55,11)
    require(len(cases) == case_count and len(wrappers) == wrapper_count, 'wrong fixture matrix')
    main_c = main_c.replace('i<55','i<'+str(case_count)).replace('PASS cases=55','PASS cases='+str(case_count))
    (out/'main.c').write_text(main_c)
    layout = ROOT/'scripts/pi4/fixtures/counter-state/link.ld'
    run('mc', [tc/'llvm-mc', '-triple=armv7-none-eabi', '-arm-add-build-attributes', '-filetype=obj', out/'start.s', '-o', out/'start.o'])
    run('compile', [tc/'clang', '--target=arm-none-eabi', '-march=armv7-a', '-marm', '-mfloat-abi=soft', '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-O2', '-c', out/'main.c', '-o', out/'main.o'])
    run('link', [tc/'ld.lld', '--emit-relocs', '-T', layout, out/'start.o', out/'main.o', '-o', out/'baseline.elf'])
    original = (out/'baseline.elf').read_bytes()
    original_sections, _ = elf_metadata(original)
    variants, redirects = {}, {}
    configurations = [('normal', []), ('reverse', ['--reorder-blocks=reverse'])]
    if args.pass_matrix:
        configurations += [('inline_all',['--inline-all']),
                           ('inline_small',['--inline-small-functions','--inline-small-functions-bytes=10000']),
                           ('peepholes',['--peepholes=double-jumps','--reorder-blocks=reverse'])]
    for mode, extra in configurations:
        candidate, mapping = out/(mode+'.elf'), out/(mode+'.map')
        inline = [] if mode in ('inline_all','inline_small') else ['--force-inline='+','.join(callees)]
        log = run(mode, [tc/'llvm-bolt', out/'baseline.elf', '-o', candidate, '--no-huge-pages', '-lite=0', '--funcs='+','.join(functions), *inline, '--emit-function-map='+str(mapping), *extra])
        require('inlined' in log and 'call sites' in log, 'inlining pass did not run '+mode)
        rows = {p[0]:[int(x,16) for x in p[1:]] for line in mapping.read_text().splitlines() if (p:=line.split())}
        require(set(rows) == set(functions), 'missing emitted fixture functions')
        dis = run(mode+'-disasm', [tc/'llvm-objdump', '-d', candidate])
        for name in wrappers:
            _, address, size = rows[name]
            ops = []
            for line in dis.splitlines():
                m = re.match(r'\s*([0-9a-f]+):\s+(?:[0-9a-f]{2,8}\s+)+(\S+)\s*(.*)', line)
                if m and address <= int(m[1],16) < address+size:
                    ops.append(m[2])
            calls = sum(bool(re.fullmatch(r'bl(?:x)?(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)?(?:\.w)?',op)) for op in ops)
            require(calls == (0 if inline_expected[name] else 1), 'wrong inlining decision '+name)
            if name.endswith(('cbz','cbnz')):
                require(any(ops[i] in ('cbz','cbnz') and ops[i+1] == 'b.w' for i in range(len(ops)-1)), 'CBZ/CBNZ expansion not exercised '+name)
        blob = bytearray(candidate.read_bytes())
        sections, _ = elf_metadata(blob)
        for src in original_sections:
            if not src['flags'] & 2 or not src['size']:
                continue
            name = '.bolt.org.text' if src['name'] == '.text' else src['name']
            dst = next(s for s in sections if s['name'] == name)
            require((dst['address'],dst['size'],dst['kind']) == (src['address'],src['size'],src['kind']), 'original section changed '+name)
            if src['kind'] != 8:
                blob[dst['offset']:dst['offset']+dst['size']] = original[src['offset']:src['offset']+src['size']]
        blob[24:28] = original[24:28]
        redirects[mode] = []
        for name in wrappers:
            old, new, _ = rows[name]
            thumb = name.startswith('caller_thumb_')
            old &= ~1; new &= ~1
            section = next(s for s in sections if s['address'] <= old < old+4 <= s['address']+s['size'])
            position = section['offset']+old-section['address']
            branch = sections_helper.encode_thumb_bw(old, new) if thumb else sections_helper.encode_arm_b(old, new)
            blob[position:position+4] = branch
            redirects[mode].append(dict(name=name,input=old,output=new,thumb=thumb,branch_hex=branch.hex()))
        candidate.write_bytes(blob)
        variants[mode] = dict(inlined=[n for n,v in inline_expected.items() if v],retained=[n for n,v in inline_expected.items() if not v],options=inline+extra)
    # A return-value fault must be rejected at case zero by the independent oracle.
    fault = bytearray((out/'normal.elf').read_bytes())
    sections, _ = elf_metadata(fault)
    row = next(r for r in redirects['normal'] if r['name'] == 'caller_arm_safe')
    address = row['output']+4 # after PUSH, the inlined ADD r0,r0,#7
    s = next(s for s in sections if s['address'] <= address < address+4 <= s['address']+s['size'])
    pos = s['offset']+address-s['address']
    require(fault[pos:pos+4] == bytes.fromhex('070080e2'), 'wrong fault-site opcode')
    fault[pos:pos+4] = bytes.fromhex('080080e2')
    (out/'bad-result.elf').write_bytes(fault)
    # Preserve branch targets/results but deliberately set flags on CBZ's
    # nonzero path. The caller consumes those flags and must report a failure.
    flag_fault = bytearray((out/'normal.elf').read_bytes())
    row = next(r for r in redirects['normal'] if r['name'] == 'caller_thumb_cbz')
    mapping = {p[0]:[int(x,16) for x in p[1:]] for line in (out/'normal.map').read_text().splitlines() if (p:=line.split())}
    length = mapping[row['name']][2]
    s = next(s for s in sections if s['address'] <= row['output'] < row['output']+length <= s['address']+s['size'])
    base = s['offset']+row['output']-s['address']
    body = flag_fault[base:base+length]
    require(body.count(bytes.fromhex('00f10700')) == 1, 'ambiguous CBZ flag fault site')
    pos = base+body.index(bytes.fromhex('00f10700'))
    flag_fault[pos:pos+4] = bytes.fromhex('10f10700') # ADD.W -> ADDS.W
    (out/'bad-cbz-flags.elf').write_bytes(flag_fault)
    for name in ('baseline', *variants, 'bad-result','bad-cbz-flags'):
        run(name+'-raw', [tc/'llvm-objcopy', '-O', 'binary', out/(name+'.elf'), out/(name+'.bin')])
    (out/'redirects.json').write_text(json.dumps(redirects,indent=2)+'\n')
    (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    manifest = dict(schema=1,kind='pi-inline-safety',cases=case_count,variants=variants,pass_matrix=args.pass_matrix,
                    faults={'bad-result':dict(case_id=0,field=0),'bad-cbz-flags':dict(case_id=46,field=0)},toolchain=str(tc),
                    scope='HYP core 0, masked interrupts; ARM/Thumb leaf, stack, LR, conditional return and both branch paths; Thumb CBZ/CBNZ expansions preserve flags consumed on both paths'+('; predicated, indirect and mixed-ISA call-site exclusions under automatic/size-based inlining and reverse-layout peepholes' if args.pass_matrix else ''),
                    files={p.name:sha256(p) for p in sorted(out.iterdir()) if p.is_file()},
                    tools={name:sha256(tc/name) for name in ('llvm-bolt','llvm-mc','ld.lld','clang','llvm-objcopy')},builder_sha256=sha256(Path(__file__)))
    (out/'build.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Built',case_count,'cases per image plus result and CBZ flag faults:', out)


if __name__ == '__main__':
    main()
