#!/usr/bin/env python3
"""Certify the four ARM/Thumb far-call ISA pairs with executable fault controls."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

from profile_identity import elf_metadata, sha256, write_json
from verify_far_execution import ASM, LAYOUT, ROOT, SEEDS, check_certificate, execute, offset, require

VENEER = '__ARMv5LongLdrPcThunk_far_away'


def fixture(caller, callee):
    text = ASM.replace('memory_result: .word 0', 'memory_result: .word 0,0')
    text = text.replace('str r0,[r4]\nbx lr', 'str r0,[r4]\nmov r3,#'+str(32 if callee == 'thumb' else 0)+'\nstr r3,[r4,#4]\nbx lr')
    text = text.replace('subs r6,r6,#1', 'ldr r3,[r4,#4]\nand r3,r3,#0x20\ncmp r3,#'+str(32 if callee == 'thumb' else 0)+'\nbne .Lisa\nsubs r6,r6,#1')
    text = text.replace('.Lstack: mov r0,#74\n.Lexit:', '.Lstack: mov r0,#74\nb .Lexit\n.Lisa: mov r0,#75\n.Lexit:')
    if caller == 'thumb':
        head, tail = text.split('.global '+VENEER, 1)
        head = head.replace('.arm\n', '.thumb\n', 1).replace('_start:\n', '.thumb_func\n_start:\n')
        replacements = {'mov ':'mov.w ', 'ldr ':'ldr.w ', 'str ':'str.w ', 'cmp ':'cmp.w ',
                        'and ':'and.w ', 'eor ':'eor.w ', 'tst ':'tst.w ', 'subs ':'subs.w ', 'bne ':'bne.w ', 'b ':'b.w '}
        head = '\n'.join(next((new+line[len(old):] for old,new in replacements.items() if line.startswith(old)), line) for line in head.split('\n'))
        head = head.replace('bl __ARM', 'blx __ARM').replace('.Lhalt: b .Lhalt', '.Lhalt: b.w .Lhalt')
        text = head+'.arm\n.balign 4\n.global '+VENEER+tail
    if callee == 'thumb':
        text = text.replace('.section .text.far,"ax",%progbits\n', '.section .text.far,"ax",%progbits\n.thumb\n')
        text = text.replace('far_away:\nadd r0,r0,#7\nstr r0,[r4]\nmov r3,#32\nstr r3,[r4,#4]\nbx lr',
                            '.thumb_func\nfar_away:\nadd.w r0,r0,#7\nstr.w r0,[r4]\nmov.w r3,#32\nstr.w r3,[r4,#4]\nbx lr')
    else:
        text = text.replace('.section .text.far,"ax",%progbits\n', '.section .text.far,"ax",%progbits\n.arm\n')
    return text+''.join(f'.word {n},{(n+7)&0xffffffff}\n' for n in SEEDS)


def cpu_states(text):
    states = {}
    pending = None
    for line in text.splitlines():
        match = re.match(r'^Trace \d+: .*?\[[0-9a-f]+/([0-9a-f]+)/',line)
        if match:
            require(pending is None,'CPU trace lacks state for preceding block')
            pending = dict(pc=int(match[1],16))
        elif pending is not None and line.startswith('R00='):
            pending['r0'] = int(line.split()[0].split('=')[1],16)
        elif pending is not None and line.startswith('R12='):
            values = dict(part.split('=') for part in line.split())
            require(int(values['R15'],16) == pending['pc'],'CPU/trace PC mismatch')
            pending['sp'] = int(values['R13'],16)
        elif pending is not None and line.startswith('PSR='):
            match = re.fullmatch(r'PSR=([0-9a-f]{8}) [A-Z-]+ ([AT]) usr32',line)
            require(match is not None and 'r0' in pending and 'sp' in pending,'malformed CPU state')
            psr = int(match[1],16)
            require(psr & 31 == 0x10 and bool(psr & 32) == (match[2] == 'T'),'wrong user mode/ISA tag')
            pending['thumb'] = bool(psr & 32)
            states.setdefault(pending['pc'],[]).append(pending)
            pending = None
    require(pending is None,'truncated CPU state')
    return states


def check_states(states,witness):
    for name,isa,count in [('caller',witness['caller_isa'],1),('veneer',witness['stub_isa'],5),
                            ('callee',witness['callee_isa'],5),('return',witness['caller_isa'],5)]:
        address = witness['call']+4 if name == 'return' else witness[name]
        rows = states.get(address,[])
        require(len(rows) == count and all(r['thumb'] == (isa == 'thumb') for r in rows),'wrong CPU ISA/visits at '+name)
    callee,returned = states[witness['callee']],states[witness['call']+4]
    require([r['r0'] for r in callee] == SEEDS,'wrong executed seed sequence')
    require([r['r0'] for r in returned] == [(n+7)&0xffffffff for n in SEEDS],'wrong observed return values')
    stack = states[witness['caller']][0]['sp']
    require(all(r['sp'] == stack for r in callee+returned),'observed stack changed')
    return {name:states[address] for name,address in [('caller',witness['caller']),('veneer',witness['veneer']),
                    ('callee',witness['callee']),('return',witness['call']+4)]}


def decode_thumb_bl(first, second, address):
    require(first & 0xf800 == 0xf000 and second & 0xd000 == 0xd000, 'expected Thumb BL to same-mode stub')
    sign = (first >> 10) & 1
    i1, i2 = 1 ^ ((second >> 13) & 1) ^ sign, 1 ^ ((second >> 11) & 1) ^ sign
    value = (sign << 24) | (i1 << 23) | (i2 << 22) | ((first & 0x3ff) << 12) | ((second & 0x7ff) << 1)
    return address+4+value-(0x2000000 if sign else 0)


def decode_stub(blob, address, thumb):
    position = offset(blob, address, 10 if thumb else 12)
    if thumb:
        lo1,lo2,hi1,hi2,bx = struct.unpack_from('<5H', blob, position)
        require(lo1 & 0xfbf0 == 0xf240 and hi1 & 0xfbf0 == 0xf2c0
                and lo2 & 0x8f00 == hi2 & 0x8f00 == 0x0c00 and bx == 0x4760,
                'wrong Thumb MOVW/MOVT/BX stub')
        def immediate(first, second):
            return ((first & 15) << 12) | (((first >> 10) & 1) << 11) | (((second >> 12) & 7) << 8) | (second & 255)
        return immediate(lo1,lo2) | (immediate(hi1,hi2) << 16)
    lo,hi,bx = struct.unpack_from('<III', blob, position)
    require(lo & 0xfff0f000 == 0xe300c000 and hi & 0xfff0f000 == 0xe340c000 and bx == 0xe12fff1c, 'wrong ARM stub')
    immediate = lambda word: (word & 0xfff) | ((word >> 4) & 0xf000)
    return immediate(lo) | (immediate(hi) << 16)


def route(blob, mapping, caller, callee):
    require(set(mapping) == {'_start','far_away'}, 'wrong emitted selection')
    old_start,start,size = mapping['_start']; old_far,far,far_size = mapping['far_away']
    old_start &= ~1; start &= ~1; old_far &= ~1; far &= ~1
    thumb, far_thumb = caller == 'thumb', callee == 'thumb'
    require(start != old_start and far != old_far and far_size == (18 if far_thumb else 20), 'wrong moved functions')
    require(struct.unpack_from('<I',blob,24)[0] == start | int(thumb), 'wrong entry ISA/address')
    _,symbols = elf_metadata(blob)
    for name,address,isa in [('_start',start,thumb),('far_away',far,far_thumb)]:
        matches = [s for s in symbols if s['name'] == name and s['address'] == address and s['thumb'] == isa]
        require(len(matches) == 1, 'missing/ambiguous emitted ISA symbol '+name)
    calls = []
    address = start
    while address < start+size:
        if thumb:
            first = struct.unpack_from('<H',blob,offset(blob,address,2))[0]
            length = 4 if first & 0xf800 in (0xe800,0xf000,0xf800) else 2
            require(address+length <= start+size, 'truncated Thumb instruction')
            if length == 4:
                second = struct.unpack_from('<H',blob,offset(blob,address+2,2))[0]
                if first & 0xf800 == 0xf000 and second & 0xd000 == 0xd000:
                    calls.append((address,decode_thumb_bl(first,second,address)))
        else:
            length = 4
            word = struct.unpack_from('<I',blob,offset(blob,address,4))[0]
            if word >> 24 == 0xeb:
                delta = (word & 0xffffff) << 2
                calls.append((address,address+8+delta-(0x4000000 if delta & 0x2000000 else 0)))
        address += length
    require(len(calls) == 1, 'expected exactly one same-mode call to stub')
    call,stub = calls[0]
    target = decode_stub(blob,stub,thumb)
    require(target == far | int(far_thumb), 'incorrect absolute target/ISA bit')
    displacement = far-call-(4 if thumb else 8)
    lower,upper = (-0x1000000,0xfffffe) if thumb else (-0x2000000,0x1fffffc)
    require(not lower <= displacement <= upper, 'direct call is in range')
    return dict(caller=start,callee=far,call=call,veneer=stub,absolute_target=target,
                caller_isa=caller,stub_isa=caller,callee_isa=callee,original_callee=old_far)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=ROOT/'out/far-interwork')
    parser.add_argument('--qemu', default='qemu-arm')
    args = parser.parse_args()
    found = shutil.which(args.qemu)
    require(found is not None, 'QEMU required for the ISA execution matrix')
    qemu,tc = Path(found).resolve(),args.toolchain.resolve()
    tools = {name:sha256(tc/name) for name in ('llvm-mc','llvm-bolt','llvm-objcopy','ld.lld')}
    scripts = {p.relative_to(ROOT).as_posix():sha256(p) for p in [Path(__file__),ROOT/'scripts/verify_far_execution.py',ROOT/'scripts/profile_identity.py']}
    revision = subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    qemu_hash = sha256(qemu)
    args.out.mkdir(parents=True,exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='run-',dir=args.out.resolve()))
    print('Evidence:',out,flush=True)
    files,rows = {},{}
    def freeze(path):
        files[path.relative_to(out).as_posix()] = sha256(path)
    for caller,callee in [('arm','arm'),('arm','thumb'),('thumb','arm'),('thumb','thumb')]:
        pair = caller+'-'+callee
        d = out/pair; d.mkdir()
        def run(name,command):
            p = subprocess.run([str(x) for x in command],capture_output=True,text=True,timeout=60)
            (d/(name+'.log')).write_text(p.stdout+p.stderr)
            require(p.returncode == 0, name+': '+(p.stdout+p.stderr)[-2000:])
            return p.stdout
        def instruction(isa,body):
            (d/'mutation.s').write_text('.syntax unified\n.arch armv7-a\n.'+isa+'\n.text\n'+body+'\n')
            run('mutation-mc',[tc/'llvm-mc','-triple=armv7-none-eabi','-filetype=obj',d/'mutation.s','-o',d/'mutation.o'])
            run('mutation-raw',[tc/'llvm-objcopy','-O','binary','-j','.text',d/'mutation.o',d/'mutation.bin'])
            return (d/'mutation.bin').read_bytes()
        (d/'fixture.s').write_text(fixture(caller,callee)); (d/'link.ld').write_text(LAYOUT)
        run('mc',[tc/'llvm-mc','-triple=armv7-none-eabi','-arm-add-build-attributes','-filetype=obj',d/'fixture.s','-o',d/'fixture.o'])
        run('ld',[tc/'ld.lld','--emit-relocs','-T',d/'link.ld',d/'fixture.o','-o',d/'baseline.elf'])
        freeze(d/'baseline.elf')
        original = (d/'baseline.elf').read_bytes()
        sections,symbols = elf_metadata(original)
        data = next(s for s in sections if s['name'] == '.data')
        baseline_required = [next(s['address'] for s in symbols if s['name'] == name) for name in ['_start','far_away']]
        baseline = execute(qemu,d/'baseline.elf',d,'baseline',5,cpu_trace=True)
        check_certificate(baseline,baseline_required,baseline_required[1:])
        rows[pair] = dict(baseline=baseline,layouts={})
        for layout,extra in [('normal',[]),('reverse',['--reorder-blocks=reverse'])]:
            image,mapfile = d/(layout+'.elf'),d/(layout+'.map')
            options = ['--no-huge-pages','-lite=0','--pad-funcs-before=far_away:0x2100000','--emit-function-map='+str(mapfile),*extra]
            log = run(layout+'-bolt',[tc/'llvm-bolt',d/'baseline.elf','-o',image,*options])
            require(re.search(r'removed linker-inserted veneers: 1\b',log) and re.search(r'Inserted 1 stubs',log),'wrong veneer/stub count')
            mapping = {}
            for line in mapfile.read_text().splitlines():
                name,*values = line.split()
                require(name not in mapping and len(values) == 3,'duplicate/malformed map')
                mapping[name] = [int(v,16) for v in values]
            blob = image.read_bytes()
            new_sections,_ = elf_metadata(blob)
            new_data = next(s for s in new_sections if s['name'] == '.data')
            require((data['address'],data['size']) == (new_data['address'],new_data['size'])
                    and original[data['offset']:data['offset']+data['size']] == blob[new_data['offset']:new_data['offset']+new_data['size']], 'changed independent table')
            freeze(image); freeze(mapfile)
            witness = route(blob,mapping,caller,callee)
            required = [witness[k] for k in ['caller','veneer','callee']]
            observed = execute(qemu,image,d,layout,5,cpu_trace=True)
            require(observed['image_sha256'] == files[image.relative_to(out).as_posix()], 'executed image differs from route')
            check_certificate(observed,required,required[1:])
            observed_states = check_states(cpu_states((d/(layout+'.trace')).read_text()),witness)
            require(witness['original_callee'] not in observed['pcs'],'retained callee executed')
            faults = {}
            wide = '.w' if callee == 'thumb' else ''
            caller_wide = '.w' if caller == 'thumb' else ''
            for fault,address,isa,body,expected in [
                ('result',witness['callee'],callee,'add'+wide+' r0,r0,#8',71),
                ('memory',witness['callee']+4,callee,'nop'+wide,72),
                ('flags',witness['callee'],callee,'adds'+wide+' r0,r0,#7',73),
                ('stack',witness['callee']+4,callee,'sub'+wide+' sp,sp,#8',74),
                ('isa',witness['callee']+8,callee,'mov'+wide+' r3,#'+str(0 if callee == 'thumb' else 32),75),
                ('bypass',witness['call'],caller,'nop'+caller_wide,71),
                ('truncated-repetitions',witness['caller']+16,caller,'mov'+caller_wide+' r6,#1',42),
                ('timeout',witness['callee'],callee,'.Lloop: b .Lloop',None),
            ]:
                replacement = instruction(isa,body)
                require(len(replacement) == (2 if fault == 'timeout' and isa == 'thumb' else 4),'wrong mutation size')
                damaged = bytearray(blob)
                position = offset(blob,address,len(replacement))
                damaged[position:position+len(replacement)] = replacement
                path = d/(layout+'-'+fault+'.elf'); path.write_bytes(damaged); freeze(path)
                result = execute(qemu,path,d,layout+'-'+fault,0.3 if expected is None else 5,tracing=fault == 'truncated-repetitions')
                require(result['timed_out'] if expected is None else not result['timed_out'] and result['returncode'] == expected,'wrong fault outcome '+pair+'/'+fault)
                try:
                    check_certificate(result,required,required[1:])
                except ValueError:
                    pass
                else:
                    raise ValueError('fault accepted '+fault)
                faults[fault] = result
            rows[pair]['layouts'][layout] = dict(selected=['_start','far_away',VENEER],emitted=mapping,eliminated=[VENEER],
                route=witness,observed=observed,cpu_states=observed_states,expected_exit=42,executed=required,options=options,faults=faults)
            print(pair,layout,': five inputs, both ISA states, eight rejected faults',flush=True)
    require(files == {name:sha256(out/name) for name in files},'artifacts changed')
    require(tools == {name:sha256(tc/name) for name in tools} and scripts == {name:sha256(ROOT/name) for name in scripts},'tools/scripts changed')
    require(qemu_hash == sha256(qemu) and revision == subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),'QEMU/revision changed')
    write_json(out/'verification.json',dict(schema=1,verified=True,kind='far-interwork-matrix',rows=rows,seeds=SEEDS,
        expected=[(n+7)&0xffffffff for n in SEEDS],repository_revision=revision,tools=tools,scripts=scripts,qemu_sha256=qemu_hash,
        scope='QEMU cortex-a15 Linux user-mode; explicit A32 literal veneer removed; four caller/callee ISA pairs; checker is rewritten and fault-tested; no Pi/automatic-v7-thunk/whole-kernel claim',
        files={p.relative_to(out).as_posix():sha256(p) for p in out.rglob('*') if p.is_file()}))
    print('PASS: all four far-call ISA pairs:',out,flush=True)


if __name__ == '__main__':
    main()
