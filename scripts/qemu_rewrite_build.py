#!/usr/bin/env python3
"""Produce a fresh scoped LK rewrite and verify its redirected entry execution."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

from profile_identity import sha256,write_json,read_json
from qemu_rewrite_gate import selection,read_map,layout,one,ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True); p.add_argument('--toolchain',type=Path,required=True)
    p.add_argument('--funcs',required=True); p.add_argument('--out',type=Path,required=True)
    p.add_argument('--qemu',default='qemu-system-arm'); p.add_argument('--timeout',type=float,default=120)
    a=p.parse_args(); names=selection(a.funcs)
    if not 0<a.timeout<=600: p.error('bounded timeout required')
    a.out.mkdir(parents=True,exist_ok=True); out=Path(tempfile.mkdtemp(prefix='build-',dir=a.out.resolve()))
    print('Build evidence:',out,flush=True)
    original=out/'original.elf'; original.write_bytes(a.elf.read_bytes()); source_hash=sha256(original)
    # No automatic extension of LK's heap/boot allocator boundary is supported.
    _,_,_,symbols=layout(original.read_bytes())
    start=one(symbols,'__bolt_reserved_start')['value']; end=one(symbols,'__bolt_reserved_end')['value']
    if not start<end<=one(symbols,'_end')['value']: raise ValueError('linked protected reservation required')
    tools={n:sha256(a.toolchain/n) for n in ('llvm-bolt','llvm-nm','llvm-readelf')}
    scripts={n:sha256(ROOT/'scripts'/n) for n in ('qemu_rewrite_build.py','qemu_rewrite_gate.py','qemu_workload_gate.py','profile_identity.py','pi4/passes_check.py','redirect-bolt-entries.py','fix-kernel-elf-sections.py')}
    candidate=out/'candidate.elf'; mapping=out/'functions.map'
    commands=[
        [str(a.toolchain/'llvm-bolt'),str(original),'--funcs='+a.funcs,'--no-huge-pages','--emit-function-map='+str(mapping),'-o',str(candidate)],
        [sys.executable,str(ROOT/'scripts/fix-kernel-elf-sections.py'),str(candidate),'--original',str(original),'--readelf',str(a.toolchain/'llvm-readelf')],
        [sys.executable,str(ROOT/'scripts/redirect-bolt-entries.py'),str(candidate),'--original',str(original),'--map',str(mapping),'--func',a.funcs,'--toolchain',str(a.toolchain),'--report',str(out/'redirect.json')],
        [sys.executable,str(ROOT/'scripts/qemu_rewrite_gate.py'),'--elf',str(original),'--candidate',str(candidate),'--map',str(mapping),'--funcs',a.funcs,'--out',str(out/'verification'),'--qemu',a.qemu,'--timeout',str(a.timeout)],
    ]
    for i,command in enumerate(commands):
        with (out/f'step-{i}.log').open('wb') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=2*a.timeout+60 if i==3 else 180)
        if result.returncode: raise ValueError(f'step {i} failed ({result.returncode}); see {out}/step-{i}.log')
        if i==0: read_map(mapping.read_text(encoding='utf-8'),names)
    receipts=list((out/'verification').glob('rewrite-*/rewrite.json'))
    if len(receipts)!=1: raise ValueError('missing/ambiguous live verification receipt')
    verified=read_json(receipts[0])
    for name,path in [('baseline.elf',original),('candidate.elf',candidate),('functions.map',mapping)]:
        if sha256(path)!=verified['artifacts'][name] or sha256(receipts[0].parent/name)!=verified['artifacts'][name]:
            raise ValueError('artifact changed after verification')
    if source_hash!=sha256(original) or source_hash!=sha256(a.elf): raise ValueError('source changed during build')
    if tools!={n:sha256(a.toolchain/n) for n in tools} or scripts!={n:sha256(ROOT/'scripts'/n) for n in scripts}: raise ValueError('tool/verifier changed')
    write_json(out/'build.json',dict(schema=1,scope='scoped selected-entry QEMU execution/output consistency; dirty source and compiler provenance not certified',
        selected=names,commands=commands,tools=tools,scripts=scripts,verification=str(receipts[0].relative_to(out)),
        artifacts={n:sha256(out/n) for n in ('original.elf','candidate.elf','functions.map','redirect.json','step-0.log','step-1.log','step-2.log','step-3.log')},
        verification_sha256=sha256(receipts[0])))
    print('SCOPED REWRITE VERIFIED: '+str(out/'build.json'),flush=True)


if __name__=='__main__':
    try: main()
    except (ValueError,OSError,subprocess.TimeoutExpired) as error: raise SystemExit('error: '+str(error))
