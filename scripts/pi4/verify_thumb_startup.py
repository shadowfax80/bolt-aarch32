#!/usr/bin/env python3
"""Verify actual BOLT runtime to Thumb startup on Pi, with bound ELF/raw bytes."""
import argparse
import json
import re
from pathlib import Path
import struct
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'scripts/pi4')]
from profile_identity import elf_metadata, sha256
from build_thumb_startup import address_offset, check_image, require
from verify_counter_state import Capture
from pi4_serial_boot import reboot_to_chainloader, resolve_port, send_image
import serial


def check_artifacts(out, build):
    require(build['schema']==1 and build['kind']=='pi-thumb-startup', 'wrong build')
    require(set(build['variants'])=={'baseline','normal','reverse'}, 'wrong variants')
    for name, digest in build['files'].items():
        require(sha256(out/name)==digest, 'changed artifact '+name)
    for name, row in build['variants'].items():
        sections, _ = check_image(out/(name+'.elf'), out/(name+'.bin'), row)
        original=(out/(name+'.unpatched.elf')).read_bytes()
        require(sha256(out/(name+'.unpatched.elf'))==row['unmodified_bolt_sha256'], 'changed source ELF')
        expected=bytearray(original)
        require(len(row['patches'])==2, 'extra postprocessing patches')
        for patch in row['patches']:
            offset=address_offset(sections,patch['address'])
            require(struct.unpack_from('<I',expected,offset)[0]==patch['before'], 'wrong patch preimage')
            struct.pack_into('<I',expected,offset,patch['after'])
        require(bytes(expected)==(out/(name+'.elf')).read_bytes(), 'postprocessing changed code or ELF entry')
        if name!='baseline':
            # A wrong interworking destination must fail the structural gate.
            fault=bytearray(expected)
            offset=address_offset(sections,row['trampoline'])
            fault[offset]^=1
            from build_thumb_startup import trampoline
            require(trampoline(fault,sections,row['trampoline'])!=row['thumb_entry'], 'ISA-bit fault not detected')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--port',default='auto')
    args=parser.parse_args()
    out=args.build.resolve()
    build=json.loads((out/'build.json').read_text())
    check_artifacts(out,build)
    evidence=Path(tempfile.mkdtemp(prefix='pi-verify-',dir=out))
    print('Evidence:',evidence,flush=True)
    port_name=resolve_port(args.port)
    results={}
    for name in build['variants']:
        console=Capture(evidence/(name+'.log'))
        try:
            with serial.Serial(port_name,115200,timeout=0.1,write_timeout=20) as port:
                port.reset_input_buffer()
                reboot_to_chainloader(port,console,3_000_000)
                send_image(port,console,(ROOT/'tools/pi4-serialboot-fast/kernel7l_fast.img').read_bytes(),30)
                send_image(port,console,(out/(name+'.bin')).read_bytes(),30,fast=True)
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    data=port.read(port.in_waiting or 1)
                    if data:console.write(data)
                    text=console.data.decode('ascii','replace')
                    result=text.rfind('BOLT_THUMB_START')
                    if result>=0 and text.rfind('SBOOT?')>result:break
                text=console.data.decode('ascii','replace')
                marker='BOLT_THUMB_START PASS\r\n'
                require(text.count(marker)==1 and text.count('BOLT_THUMB_START')==1, 'missing/duplicate/wrong startup result')
                require(text.rfind('SBOOT?')>text.index(marker), 'did not return to loader')
                states=re.findall(r'^START_STATE ((?:[0-9a-f]{8} ){6}[0-9a-f]{8})\r?$',text,re.M)
                require(len(states)==1, 'missing/duplicate state report')
                value=[int(x,16) for x in states[0].split()]
                register,cpsr,stack,mpidr,count,high,link=value
                row=build['variants'][name]
                entry=row.get('thumb_entry',row['original_thumb_entry']) & ~1
                require(register==0x12345678 and cpsr&0xf00000c0==0xa00000c0
                        and cpsr&31 in (0x13,0x1a,0x1f) and stack==0x00800000
                        and mpidr&0xffffff==0 and count==1 and high==0
                        and link&1 and entry<=link&~1<entry+row['thumb_size'], 'startup state/counter/return-link mismatch')
                results[name]=dict(passed=True,actual_runtime_entry=build['variants'][name]['instrumented'],
                                   counter_checked=row['instrumented'],
                                   exact_counter=1 if row['instrumented'] else None,
                                   thumb_return_link=link,state=value,
                                   thumb_state=True,sentinels_and_quiet_contract=True)
        finally:
            if console.log:console.log.close()
    check_artifacts(out,build)
    report=dict(schema=1,verified=True,scope=build['scope'],port=port_name,results=results,
                build_manifest_sha256=sha256(out/'build.json'),verifier_sha256=sha256(Path(__file__)),
                artifact_checker_sha256=sha256(ROOT/'scripts/pi4/build_thumb_startup.py'),
                loader_sha256=sha256(ROOT/'tools/pi4-serialboot-fast/kernel7l_fast.img'),
                log_sha256={name:sha256(evidence/(name+'.log')) for name in results})
    (evidence/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(evidence/'verification.json')


if __name__=='__main__':main()
