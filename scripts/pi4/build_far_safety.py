#!/usr/bin/env python3
"""Build sparse Pi images that execute unmodified BOLT ARM/Thumb far-call code."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'scripts/pi4')]
from profile_identity import elf_metadata,sha256,write_json
from verify_far_execution import offset,require
from verify_far_interwork import decode_thumb_bl,decode_stub

PAIRS = [('arm','arm'),('arm','thumb'),('thumb','arm'),('thumb','thumb')]
SEEDS = [0,1,2,17,0x7fffffff,0x80000000,0x80000001,0xfffffff9,0xffffffff]
FIELDS = ['caller_pc','callee_pc','return_pc','ip','flags_before','flags_after','sp_before','sp_after','memory']


def cmp_flags(value):
    result=(value-1)&0xffffffff
    n=result>>31;z=int(result==0);c=int(value>=1)
    v=(((value^1)&(value^result))>>31)&1
    return (n<<31)|(z<<30)|(c<<29)|(v<<28)


def validate_chunks(chunks):
    previous = 0
    for row in sorted(chunks,key=lambda r:r['address']):
        address,size = row['address'],row['size']
        require(0x100000 <= address < address+size <= 0x10000000 and 0 < size <= 4096,'invalid staged extent')
        require(address >= previous,'overlapping staged extents')
        for start,end in [(0x700000,0x900000),(0x2000000,0x2100000)]:
            require(address+size <= start or address >= end,'staging touches stack/loader reserve')
        previous = address+size


def instructions(blob,address,size,thumb):
    end = address+size
    sections,_=elf_metadata(blob)
    matches=[s for s in sections if s['kind']!=8 and s['flags']&2 and address<s['address']+s['size'] and s['address']<end]
    require(len(matches)==1 and matches[0]['address']<=address<end<=matches[0]['address']+matches[0]['size'],
            'ambiguous/unmapped instruction extent')
    section=matches[0]
    while address < end:
        position=section['offset']+address-section['address']
        if thumb:
            require(address+2<=end,'truncated instruction')
            half = struct.unpack_from('<H',blob,position)[0]
            length = 4 if half & 0xf800 in (0xe800,0xf000,0xf800) else 2
        else:
            length = 4
        require(address+length <= end,'truncated instruction')
        yield address,blob[position:position+length]
        address += length


def witnesses(blob,caller,callee):
    sections,symbols = elf_metadata(blob)
    def symbol(name):
        rows = [s for s in symbols if s['name'] == name and s['kind'] == 2]
        require(len(rows) == 1,'ambiguous function '+name)
        return rows[0]
    source,target = symbol(caller),symbol(callee)
    caller_pcs = link_witnesses(list(instructions(blob,source['address'],source['size'],source['thumb'])),source['thumb'],fields=[0,8])
    callee_pcs = link_witnesses(list(instructions(blob,target['address'],target['size'],target['thumb'])),target['thumb'],save_link=True,fields=[4])
    require(len(caller_pcs) == 2 and len(callee_pcs) == 1,'missing live link witness instructions')
    return dict(caller=source,callee=target,caller_pc=caller_pcs[0],callee_pc=callee_pcs[0],return_pc=caller_pcs[1])


def direct_call(address,data,thumb):
    if thumb and len(data) == 4:
        first,second = struct.unpack('<HH',data)
        if first & 0xf800 == 0xf000 and second & 0xd000 == 0xd000:
            return decode_thumb_bl(first,second,address)
    elif not thumb:
        word = struct.unpack('<I',data)[0]
        if word >> 24 == 0xeb:
            delta = (word & 0xffffff) << 2
            return address+8+delta-(0x4000000 if delta & 0x2000000 else 0)
    return None


def link_witnesses(code,thumb,save_link=False,fields=None):
    """Bind each MOV r3,LR to its actual incoming BL and optional output field.

    Block reordering may separate the capture from the call continuation.
    The observed LR is call+4 (with ISA bit), rather than the capture's address.
    """
    move = bytes.fromhex('7346' if thumb else '0e30a0e1')
    save = bytes.fromhex('7246' if thumb else '0e20a0e1')
    restore = bytes.fromhex('9646' if thumb else '02e0a0e1')
    result=[];values={}
    calls=[(i,address,direct_call(address,data,thumb)) for i,(address,data) in enumerate(code)
           if direct_call(address,data,thumb) is not None]
    for i,(address,data) in enumerate(code):
        if data != move:
            continue
        incoming=[(j,call) for j,call,target in calls if target==address]
        require(len(incoming)==1,'link witness lacks unique same-ISA call')
        call_index,call=incoming[0]
        if save_link:
            require(call_index>0 and code[call_index-1][1]==save and i+1<len(code) and code[i+1][1]==restore,
                    'callee witness does not preserve return link')
        value=(call+4) | int(thumb);result.append(value)
        if fields is not None:
            store_index=i+1+int(save_link)
            require(store_index<len(code),'missing witness store')
            stores={bytes.fromhex('c1f8'+f'{field:02x}'+'30') if thumb else struct.pack('<I',0xe5813000|field):field for field in fields}
            field=stores.get(code[store_index][1])
            require(field is not None and field not in values,'missing/duplicate witness field')
            values[field]=value
    if fields is not None:
        require(set(values)==set(fields),'incomplete witness fields')
        return [values[field] for field in fields]
    return result


def emitted_route(blob,row):
    source,target = row['caller'],row['callee']
    calls = []
    captures={address for address,data in instructions(blob,source['address'],source['size'],source['thumb'])
              if data==bytes.fromhex('7346' if source['thumb'] else '0e30a0e1')}
    for address,data in instructions(blob,source['address'],source['size'],source['thumb']):
        target_address=direct_call(address,data,source['thumb'])
        if target_address is not None and target_address not in captures:
            calls.append((address,target_address))
    require(len(calls) == 1,'wrong generated call count')
    call,stub = calls[0]
    absolute = decode_stub(blob,stub,source['thumb'])
    require(absolute == target['address'] | int(target['thumb']),'wrong stub target/ISA')
    displacement = target['address']-call-(4 if source['thumb'] else 8)
    lower,upper = (-0x1000000,0xfffffe) if source['thumb'] else (-0x2000000,0x1fffffc)
    require(not lower <= displacement <= upper,'not a far call')
    return dict(call=call,stub=stub,absolute_target=absolute,stub_thumb=source['thumb'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='build-',dir=args.out.resolve()))
    tc = args.toolchain.resolve()
    tools = {name:sha256(tc/name) for name in ['llvm-mc','ld.lld','clang','llvm-bolt','llvm-objcopy']}
    script_paths = [Path(__file__),ROOT/'scripts/profile_identity.py',ROOT/'scripts/verify_far_execution.py',ROOT/'scripts/verify_far_interwork.py',ROOT/'scripts/pi4/fixtures/counter-state/main.c']
    scripts = {p.relative_to(ROOT).as_posix():sha256(p) for p in script_paths}
    revision = subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    def run(name,command):
        p = subprocess.run([str(x) for x in command],capture_output=True,text=True,timeout=60)
        (out/(name+'.log')).write_text(p.stdout+p.stderr)
        require(p.returncode == 0,name+': '+(p.stdout+p.stderr)[-2500:])
        return p.stdout
    asm = '.syntax unified\n.arch armv7-a\n.arm\n.section .text.start,"ax",%progbits\n.global _start\n.type _start,%function\n_start:\ncpsid if\nldr sp,=0x00800000\nbl state_main\n.Lhalt: wfe\nb .Lhalt\n.size _start,.-_start\n.ltorg\n.text\n'
    functions = []
    def function(name,isa,body):
        return '.'+isa+'\n.balign 4\n.global '+name+'\n.type '+name+',%function\n'+('.thumb_func\n' if isa == 'thumb' else '')+name+':\n'+body+'\n.size '+name+',.-'+name+'\n'
    for caller_isa,callee_isa in PAIRS:
        tag = caller_isa+'_'+callee_isa
        caller,callee,veneer = 'caller_'+tag,'far_'+tag,'__ARMv5LongLdrPcThunk_far_'+tag
        wide = '.w' if caller_isa == 'thumb' else ''
        body = ('push {r4,lr}\nmov r2,sp\nstr'+wide+' r2,[r1,#24]\nbl .Lcapture0_'+tag+'\n.Lcapture0_'+tag+':\nmov r3,lr\nstr'+wide+' r3,[r1]\n'
                'movw r12,#0xa5a5\nmovt r12,#0xa5a5\ncmp r0,#1\nmrs r2,cpsr\nstr'+wide+' r2,[r1,#16]\n'
                +('blx' if caller_isa == 'thumb' else 'bl')+' '+veneer+'\nmrs r2,cpsr\nstr'+wide+' r2,[r1,#20]\n'
                'mov r2,sp\nstr'+wide+' r2,[r1,#28]\nbl .Lcapture1_'+tag+'\n.Lcapture1_'+tag+':\nmov r3,lr\nstr'+wide+' r3,[r1,#8]\npop {r4,pc}')
        asm += function(caller,caller_isa,body)
        asm += function(veneer,'arm','ldr pc,[pc,#-4]\n.word '+callee)
        wide = '.w' if callee_isa == 'thumb' else ''
        asm += function(callee,callee_isa,'mov r2,lr\nbl .Lcapture2_'+tag+'\n.Lcapture2_'+tag+':\nmov r3,lr\nmov lr,r2\nstr'+wide+' r3,[r1,#4]\nstr'+wide+' r12,[r1,#12]\nadd'+wide+' r0,r0,#7\nstr'+wide+' r0,[r1,#32]\nbx lr')
        functions += [caller,callee,veneer]
    asm += '.data\n.balign 4\n.global case_entries\n.type case_entries,%object\ncase_entries:\n'
    for a,b in PAIRS:
        for seed in SEEDS:
            asm += f'.word caller_{a}_{b},{seed},{(seed+7)&0xffffffff},0,0,0,0\n'
    asm += '.size case_entries,.-case_entries\n'
    (out/'fixture.s').write_text(asm)
    support = (ROOT/'scripts/pi4/fixtures/counter-state/main.c').read_text()
    support = support[support.index('#define REG'):support.index('void state_main(void)')].replace('BOLT_COUNTER_STATE','BOLT_FAR_PI')
    c = '''#include <stdint.h>
struct Case { uint32_t (*fn)(uint32_t, volatile uint32_t*); uint32_t arg,expected,cpc,fpc,rpc,ip; };
extern const struct Case case_entries[];
'''+support+'''void state_main(void) {
    watchdog(10);
    uint32_t mode,core,sctlr;
    __asm__ volatile("mrs %0,cpsr":"=r"(mode));
    __asm__ volatile("mrc p15,0,%0,c0,c0,5":"=r"(core));
    __asm__ volatile("mrc p15,0,%0,c1,c0,0":"=r"(sctlr));
    puts_uart("BOLT_FAR_PI BEGIN mode=");hex(mode & 31);puts_uart(" core=");hex(core & 255);puts_uart(" sctlr=");hex(sctlr);puts_uart("\\r\\n");
    if ((mode & 31)!=0x1a || !(mode & 0x80) || !(mode & 0x40)) fail(0,100,0x1a,mode);
    if (core & 255) fail(0,101,0,core & 255);
    if (sctlr & 0x1005) fail(0,102,0,sctlr & 0x1005);
    for (unsigned i=0;i<20;++i) {
        volatile uint32_t o[9]; for (unsigned k=0;k<9;++k) o[k]=0;
        const struct Case *c=&case_entries[i];
        uint32_t result=c->fn(c->arg,o);
        if (result!=c->expected) fail(i,0,c->expected,result);
        if (o[8]!=c->expected) fail(i,8,c->expected,o[8]);
        if (o[0]!=c->cpc) fail(i,10,c->cpc,o[0]);
        if (o[1]!=c->fpc) fail(i,11,c->fpc,o[1]);
        if (o[2]!=c->rpc) fail(i,12,c->rpc,o[2]);
        if (o[3]!=c->ip) fail(i,13,c->ip,o[3]);
        if ((o[4]^o[5]) & 0xf0000000u) fail(i,14,o[4],o[5]);
        if (o[6]!=o[7] || (o[7]&7)) fail(i,16,o[6],o[7]);
        puts_uart("BOLT_FAR_PI CASE id=");hex(i);puts_uart(" input=");hex(c->arg);puts_uart(" result=");hex(result);
        const char *keys[9]={" cpc="," fpc="," rpc="," ip="," fb="," fa="," sb="," sa="," mem="};
        for (unsigned k=0;k<9;++k) {puts_uart(keys[k]);hex(o[k]);} puts_uart("\\r\\n");
    }
    puts_uart("BOLT_FAR_PI PASS cases=20\\r\\n");finish();
}
'''
    c=c.replace('i<20','i<'+str(len(PAIRS)*len(SEEDS))).replace('cases=20','cases='+str(len(PAIRS)*len(SEEDS)))
    (out/'main.c').write_text(c)
    (out/'link.ld').write_text('ENTRY(_start)\nSECTIONS { . = 0x100000; .text : { *(.text.start) *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) } .bss : { *(.bss*) *(COMMON) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) } }\n')
    run('mc',[tc/'llvm-mc','-triple=armv7-none-eabi','-arm-add-build-attributes','-filetype=obj',out/'fixture.s','-o',out/'fixture.o'])
    run('cc',[tc/'clang','--target=arm-none-eabi','-march=armv7-a','-marm','-mfloat-abi=soft','-mno-unaligned-access','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-O2','-c',out/'main.c','-o',out/'main.o'])
    run('ld',[tc/'ld.lld','--emit-relocs','-T',out/'link.ld',out/'fixture.o',out/'main.o','-o',out/'baseline.elf'])
    original = (out/'baseline.elf').read_bytes()
    original_sections,original_symbols = elf_metadata(original)
    case_table = next(s for s in original_symbols if s['name'] == 'case_entries')
    layouts = {}
    for layout,extra in [('normal',[]),('reverse',['--reorder-blocks=reverse'])]:
        options = ['--no-huge-pages','-lite=0','--funcs='+','.join(functions),'--emit-function-map='+str(out/(layout+'.map'))]
        options += ['--pad-funcs-before=far_'+a+'_'+b+':0x2100000' for a,b in PAIRS]+extra
        log = run(layout+'-bolt',[tc/'llvm-bolt',out/'baseline.elf','-o',out/(layout+'.elf'),*options])
        require('removed linker-inserted veneers: 4' in log,'literal veneers not removed')
        mapping={parts[0]:[int(x,16) for x in parts[1:]] for line in (out/(layout+'.map')).read_text().splitlines() if (parts:=line.split())}
        emitted=[n for n in functions if not n.startswith('__ARMv5LongLdrPcThunk_')]
        require(set(mapping)==set(emitted),'missing/extra emitted function')
        layouts[layout] = dict(options=options,selected=functions,emitted=mapping,
                              eliminated=[n for n in functions if n not in mapping],profile=None)
    variants = {}
    for name in ['baseline','normal','reverse','bad-result','bad-flags','retained-callee','timeout']:
        code_name = 'normal' if name.startswith('bad-') or name in ['retained-callee','timeout'] else name
        code = (out/(code_name+'.elf')).read_bytes()
        rows = [witnesses(code,'caller_'+a+'_'+b,'far_'+a+'_'+b) for a,b in PAIRS]
        routes = [emitted_route(code,r) for r in rows] if code_name != 'baseline' else []
        if name in ['bad-result','bad-flags']:
            row = rows[0]['callee']; data = bytearray(code)
            additions = [(address,raw) for address,raw in instructions(code,row['address'],row['size'],False) if raw == bytes.fromhex('070080e2')]
            require(len(additions) == 1,'ambiguous arithmetic fault site')
            struct.pack_into('<I',data,offset(data,additions[0][0],4),0xe2800008 if name == 'bad-result' else 0xe2900007)
            code = bytes(data)
        elif name == 'timeout':
            data=bytearray(code)
            struct.pack_into('<I',data,offset(data,rows[0]['callee']['address'],4),0xeafffffe)
            code=bytes(data)
        elif name == 'retained-callee':
            data = bytearray(code); stub = routes[0]['stub']
            old = witnesses(original,'caller_arm_arm','far_arm_arm')['callee']['address']
            lo,hi = old & 0xffff,old >> 16
            struct.pack_into('<II',data,offset(data,stub,8),0xe300c000 | (lo & 0xfff) | ((lo & 0xf000)<<4),0xe340c000 | (hi & 0xfff) | ((hi & 0xf000)<<4))
            code = bytes(data)
        baseline = bytearray(original)
        expectations = []
        for index,(a,b) in enumerate(PAIRS):
            row = rows[index]; fn = row['caller']['address'] | int(row['caller']['thumb'])
            ip = 0xa5a5a5a5 if code_name == 'baseline' else routes[index]['absolute_target']
            for seed_index,seed in enumerate(SEEDS):
                values = [fn,seed,(seed+7)&0xffffffff,row['caller_pc'],row['callee_pc'],row['return_pc'],ip]
                struct.pack_into('<7I',baseline,offset(baseline,case_table['address']+(index*len(SEEDS)+seed_index)*28,28),*values)
                expectations.append(dict(pair=a+'-'+b,id=index*len(SEEDS)+seed_index,input=seed,result=values[2],cpc=values[3],fpc=values[4],rpc=values[5],ip=ip,nzcv=cmp_flags(seed)))
        chunks = []
        for section in original_sections:
            if not section['flags'] & 2 or not section['size']:
                continue
            body = bytes(section['size']) if section['kind'] == 8 else bytes(baseline[section['offset']:section['offset']+section['size']])
            for relative in range(0,len(body),4096):
                chunks.append(dict(address=section['address']+relative,data=body[relative:relative+4096]))
        if code_name != 'baseline':
            sections,_ = elf_metadata(code)
            text = next(s for s in sections if s['name'] == '.text')
            body = code[text['offset']:text['offset']+text['size']]
            for relative in range(0,len(body),4096):
                page = body[relative:relative+4096]
                if any(page): chunks.append(dict(address=text['address']+relative,data=page))
        plan = [dict(address=r['address'],size=len(r['data'])) for r in chunks]
        validate_chunks(plan)
        d = out/'stage'/name; d.mkdir(parents=True)
        boot = '''.syntax unified
.arch armv7-a
.arm
.section .text.start,"ax",%progbits
.global _loader_start
.type _loader_start,%function
_loader_start:
cpsid if
ldr sp,=0x00800000
ldr r0,=0xfe100024
ldr r1,=0x5a0a0000
str r1,[r0]
ldr r0,=0xfe10001c
ldr r1,[r0]
bic r1,r1,#0xff000000
bic r1,r1,#0x30
orr r1,r1,#0x5a000000
orr r1,r1,#0x20
str r1,[r0]
mrc p15,0,r0,c1,c0,0
ldr r1,=0x1005
tst r0,r1
bne .Lstop
ldr r4,=chunk_table
ldr r5,=CHUNK_COUNT
.Lchunk:
ldmia r4!,{r0,r1,r2}
.Lbyte:
ldrb r3,[r2],#1
strb r3,[r0],#1
subs r1,r1,#1
bne .Lbyte
subs r5,r5,#1
bne .Lchunk
dsb sy
mov r0,#0
mcr p15,0,r0,c7,c5,0
dsb sy
isb sy
ldr r0,=0x00100000
bx r0
.Lstop: wfe
b .Lstop
.size _loader_start,.-_loader_start
.ltorg
.data
.balign 4
.global chunk_table
.type chunk_table,%object
chunk_table:
'''.replace('CHUNK_COUNT',str(len(chunks)))
        for i,row in enumerate(chunks):
            payload = d/f'chunk-{i:03d}.bin'; payload.write_bytes(row['data'])
            boot += f'.word {row["address"]},{len(row["data"])},packed_{i}\n'
        boot += '.size chunk_table,.-chunk_table\n'
        for i,row in enumerate(chunks):
            boot += f'.global packed_{i}\n.type packed_{i},%object\npacked_{i}:\n.incbin "{d/f"chunk-{i:03d}.bin"}"\n.size packed_{i},.-packed_{i}\n'
        (d/'boot.s').write_text(boot)
        (d/'boot.ld').write_text('ENTRY(_loader_start)\nSECTIONS { . = 0x8000; .text : { *(.text.start) *(.text*) } .data : { *(.data*) } }\n')
        run(name+'-boot-mc',[tc/'llvm-mc','-triple=armv7-none-eabi','-arm-add-build-attributes','-filetype=obj',d/'boot.s','-o',d/'boot.o'])
        run(name+'-boot-ld',[tc/'ld.lld','-T',d/'boot.ld',d/'boot.o','-o',out/(name+'.stage.elf')])
        run(name+'-raw',[tc/'llvm-objcopy','-O','binary',out/(name+'.stage.elf'),out/(name+'.bin')])
        require((out/(name+'.bin')).stat().st_size < 0x100000-0x8000,'upload overlaps staged memory')
        stage = (out/(name+'.stage.elf')).read_bytes(); _,symbols = elf_metadata(stage)
        for i,row in enumerate(plan):
            packed = next(s for s in symbols if s['name'] == 'packed_'+str(i))
            row.update(source_address=packed['address'],file=(d/f'chunk-{i:03d}.bin').relative_to(out).as_posix(),sha256=sha256(d/f'chunk-{i:03d}.bin'))
        write_json(d/'plan.json',dict(schema=1,chunks=plan))
        variants[name] = dict(code=code_name,code_sha256=hashlib.sha256(code).hexdigest(),expectations=expectations,routes=routes,plan=(d/'plan.json').relative_to(out).as_posix(),image_sha256=sha256(out/(name+'.bin')))
        print(name,'packed',len(chunks),'chunks,', (out/(name+'.bin')).stat().st_size,'upload bytes',flush=True)
    require(tools == {name:sha256(tc/name) for name in tools} and scripts == {name:sha256(ROOT/name) for name in scripts},'producer inputs changed')
    require(revision == subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),'revision changed')
    write_json(out/'build.json',dict(schema=2,kind='pi-far-safety',witness_kind='same-ISA BL return link including Thumb bit',scope='HYP core 0, MMU/caches off, masked IRQ/FIQ; sparse staging of original harness and unmodified emitted four-ISA far-call code; live BL/LR position witnesses; no whole-kernel/ISR claim',
        variants=variants,layouts=layouts,tools=tools,scripts=scripts,repository_revision=revision,
        seeds=SEEDS,patch_sha256={p.name:sha256(p) for p in sorted((ROOT/'overlay/llvm/patches/atfe').glob('*.patch'))},
        faults={'bad-result':dict(case_id=0,field=0),'bad-flags':dict(case_id=0,field=14),'retained-callee':dict(case_id=0,field=11),'timeout':dict(case_id=0,kind='missing-completion')},
        files={p.relative_to(out).as_posix():sha256(p) for p in out.rglob('*') if p.is_file()}))
    print('Built sparse Pi far-call fixture:',out,flush=True)


if __name__ == '__main__': main()
