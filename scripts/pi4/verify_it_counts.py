#!/usr/bin/env python3
"""Verify the bounded IT-mask/branch/loop counter fixture on Raspberry Pi 4."""
import argparse
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'scripts/pi4')]
from profile_identity import elf_metadata, sha256
from full_image_verify import branch_target
from verify_counter_state import Capture, require
from pi4_serial_boot import reboot_to_chainloader, resolve_port, send_image
import serial


def check_groups(text, names):
    """Counters/branches must not replace any instruction inside a residual IT."""
    functions = {}
    current = None
    for line in text.splitlines():
        label = re.match(r'^[0-9a-f]+ <([^>]+)>:', line)
        if label:
            current = label[1]
            functions[current] = []
            continue
        instruction = re.match(r'\s*[0-9a-f]+:\s+(?:[0-9a-f]{2,8}\s+)+(\S+)\s*(.*)', line)
        if current in names and instruction:
            functions[current].append((instruction[1], instruction[2]))
    for name in names:
        require(functions.get(name), 'missing disassembled function ' + name)
        instructions = functions[name]
        groups = 0
        for index, (opcode, operands) in enumerate(instructions):
            if not re.fullmatch(r'it[te]{0,3}', opcode):
                continue
            groups += 1
            require(operands.strip() == 'eq', 'unexpected IT condition in ' + name)
            length = len(opcode)-1
            body = instructions[index+1:index+1+length]
            require(len(body) == length, 'truncated emitted IT in ' + name)
            senses = 't'+opcode[2:]
            for (body_op, args), sense in zip(body,senses):
                require(body_op == ('addeq.w' if sense=='t' else 'addne.w')
                        and re.match(r'r1,\s*r1,\s*#',args), 'foreign instruction inside IT in ' + name)
        expected = 0 if name.startswith(('it_loop','nested_')) or name in ('it_branch_t_n','it_branch_t_w') else 1
        require(groups == expected, 'missing/extra IT groups in ' + name)


def check_artifacts(out, build):
    require(build['schema']==1 and build['kind'] in ('pi-it-counts','pi-it-nested-counts'), 'wrong IT build')
    nested=build['kind']=='pi-it-nested-counts'
    require(build['cases']==(372 if nested else 300) and len(build['functions'])==(50 if nested else 47)
            and set(build['variants'])=={'normal','reverse','conservative'}, 'wrong IT matrix')
    for name,digest in build['files'].items():
        require(sha256(out/name)==digest,'changed artifact '+name)
    faults=build.get('faults',{})
    require(not faults or set(faults)=={'bad-reset'},'unknown fault fixture')
    for name in ('baseline',*build['variants'],*faults):
        elf,raw=(out/(name+'.elf')).read_bytes(),(out/(name+'.bin')).read_bytes()
        sections,symbols=elf_metadata(elf)
        loaded=[s for s in sections if 'physical' in s]
        base=min(s['physical'] for s in loaded)
        require(base==0x8000 and struct.unpack_from('<I',elf,24)[0]==0x8000,'wrong boot entry/base')
        end=max(s['physical']+s['size'] for s in loaded)
        require(end<0x700000 and len(raw)==end-base,'wrong firmware size')
        for section in loaded:
            require(section['physical']==section['address'],'requires MMU-off V=P')
            position=section['physical']-base
            require(raw[position:position+section['size']]==elf[section['offset']:section['offset']+section['size']], 'ELF/raw mismatch')
        if name=='baseline':
            continue
        selected=faults[name]['base_variant'] if name in faults else name
        if build.get('runtime_clear_checked',False):
            objects=[s for s in symbols if s['name']=='reset_runtime' and s['kind']==1 and s['size']==4]
            require(len(objects)==1,'missing/ambiguous runtime reset pointer')
            address=objects[0]['address']
            section=next(s for s in loaded if s['address']<=address<address+4<=s['address']+s['size'])
            position=section['offset']+address-section['address']
            target=struct.unpack_from('<I',elf,position)[0]
            reports=re.findall(r'^BOLT-INFO: clear procedure is 0x([0-9a-f]+)$',
                               (out/(selected+'-instrument.log')).read_text(encoding='utf-8'),re.M)
            require(len(reports)==1 and target==int(reports[0],16)==build['variants'][selected]['runtime_clear_address'],
                    'runtime reset pointer/linker mismatch')
            require(any(s['flags']&4 and s['address']<=(target&~1)<s['address']+s['size'] for s in loaded),
                    'runtime reset points outside loaded executable code')
            if name in faults:
                require(target%4==0,'reset fault requires aligned ARM code')
                section=next(s for s in loaded if s['address']<=target<target+4<=s['address']+s['size'])
                position=section['offset']+target-section['address']
                expected=bytearray((out/(selected+'.elf')).read_bytes())
                expected[position:position+4]=struct.pack('<I',0xe12fff1e)
                require(elf==expected,'fault image changes more than the reset entry')
        report=json.loads((out/(selected+'-redirects.json')).read_text(encoding='utf-8'))
        require({r['name'] for r in report['redirected']}==set(build['functions'])
                and len(report['redirected'])==len(build['functions']),'incomplete redirects')
        for row in report['redirected']:
            require(row['thumb'],'fixture function must be Thumb')
            section=next(s for s in loaded if s['address']<=row['input']<row['input']+4<=s['address']+s['size'])
            position=section['offset']+row['input']-section['address']
            branch=elf[position:position+4]
            require(branch.hex()==row['branch_hex'] and branch_target(branch,row['input'],True)==row['output'],'wrong generated-code redirect')
        check_groups((out/(selected+'-disassembly.log')).read_text(encoding='utf-8'),build['functions'])


def check_result(text, instrumented, counters, cases=300, runtime_clear=False):
    begins=re.findall(r'^BOLT_IT_COUNTS BEGIN instrumented=([0-9a-f]{8}) counters=([0-9a-f]{8})\r?$',text,re.M)
    require(len(begins)==1 and tuple(int(x,16) for x in begins[0])==(instrumented,counters),'wrong/missing IT begin')
    require('BOLT_IT_COUNTS FAIL' not in text,'Pi reported a result/counter mismatch')
    if runtime_clear:
        resets=re.findall(r'^BOLT_IT_COUNTS RESET runtime=([0-9a-f]{8})\r?$',text,re.M)
        require(len(resets)==1 and int(resets[0],16)==instrumented,'missing/wrong runtime reset marker')
    passes=re.findall(r'^BOLT_IT_COUNTS PASS cases=(\d+)\r?$',text,re.M)
    require(passes==[str(cases)] and text.count('BOLT_IT_COUNTS PASS')==1,'missing/malformed/duplicate IT pass')
    return dict(passed=True,cases=cases,counters=counters,instrumented=bool(instrumented),runtime_clear_checked=runtime_clear)


def check_reset_fault(text, counters):
    begins=re.findall(r'^BOLT_IT_COUNTS BEGIN instrumented=([0-9a-f]{8}) counters=([0-9a-f]{8})\r?$',text,re.M)
    require(len(begins)==1 and tuple(int(x,16) for x in begins[0])==(1,counters),'wrong fault begin')
    failures=re.findall(r'^BOLT_IT_COUNTS FAIL case=([0-9a-f]{8}) seed=([0-9a-f]{8}) field=([0-9a-f]{8}) expected=([0-9a-f]{8}) actual=([0-9a-f]{8})\r?$',text,re.M)
    require(len(failures)==1 and tuple(int(x,16) for x in failures[0])==(0,0,2000,0,0x12345678),'wrong/missing reset-fault detection')
    require('BOLT_IT_COUNTS PASS' not in text,'fault incorrectly passed')
    return dict(fault_detected=True,case=0,seed=0,field=2000,actual=0x12345678)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--port',default='auto')
    args=parser.parse_args()
    out=args.build.resolve()
    build=json.loads((out/'build.json').read_text(encoding='utf-8'))
    check_artifacts(out,build)
    evidence=Path(tempfile.mkdtemp(prefix='pi-verify-',dir=out))
    print('Evidence:',evidence,flush=True)
    port_name=resolve_port(args.port)
    results={}
    for name in ('baseline',*build['variants'],*build.get('faults',{})):
        console=Capture(evidence/(name+'.log'))
        try:
            with serial.Serial(port_name,115200,timeout=0.1,write_timeout=20) as port:
                port.reset_input_buffer()
                reboot_to_chainloader(port,console,3_000_000)
                send_image(port,console,(ROOT/'tools/pi4-serialboot-fast/kernel7l_fast.img').read_bytes(),30)
                send_image(port,console,(out/(name+'.bin')).read_bytes(),30,fast=True)
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    data=port.read(port.in_waiting or 1)
                    if data:console.write(data)
                    text=console.data.decode('ascii','replace')
                    result=max(text.rfind('BOLT_IT_COUNTS PASS'),text.rfind('BOLT_IT_COUNTS FAIL'))
                    if result>=0 and text.rfind('SBOOT?')>result:break
                text=console.data.decode('ascii','replace')
                result=max(text.rfind('BOLT_IT_COUNTS PASS'),text.rfind('BOLT_IT_COUNTS FAIL'))
                require(result>=0 and text.rfind('SBOOT?')>result,'payload did not report and return to loader')
                if name in build.get('faults',{}):
                    results[name]=check_reset_fault(text,build['faults'][name]['counters'])
                else:
                    results[name]=check_result(text,0 if name=='baseline' else 1,1 if name=='baseline' else build['variants'][name]['counters'],build['cases'],build.get('runtime_clear_checked',False))
        finally:
            if console.log:console.log.close()
    check_artifacts(out,build)
    result=dict(schema=1,verified=True,scope=build['scope'],port=port_name,results=results,
                build_manifest_sha256=sha256(out/'build.json'),verifier_sha256=sha256(Path(__file__)),
                loader_sha256=sha256(ROOT/'tools/pi4-serialboot-fast/kernel7l_fast.img'),
                log_sha256={name:sha256(evidence/(name+'.log')) for name in results})
    (evidence/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(evidence/'verification.json')


if __name__=='__main__':main()
