#!/usr/bin/env python3
"""Bounded LK selected-entry execution and complete output consistency in QEMU.

Requires linked __bolt_reserved_start/end, an exact function map and explicit
redirects. Owns fresh captures; imported traces cannot issue runtime receipts.
"""
import argparse
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from profile_identity import elf_metadata, sha256, write_json
from qemu_workload_gate import boot, ROOT
from qemu_bench_oracle import CONTRACTS,check_results


def selection(text):
    names=text.split(',')
    if not 1<=len(names)<=32 or len(set(names))!=len(names) or any(not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',n) for n in names):
        raise ValueError('require 1..32 distinct explicit function names')
    return names


def read_map(text,names):
    rows={}
    for line in text.splitlines():
        if not line.strip(): continue
        fields=line.split()
        if len(fields)!=4 or fields[0] in rows: raise ValueError('malformed/duplicate function map')
        if any(not re.fullmatch(r'[0-9a-fA-F]{1,8}',x) for x in fields[1:]): raise ValueError('invalid map address/size')
        old,new,size=map(lambda x:int(x,16),fields[1:])
        if old%2 or new%2 or not size or old+4>2**32 or new+size>2**32: raise ValueError('invalid map range')
        rows[fields[0]]=dict(name=fields[0],input=old,output=new,output_size=size)
    if set(rows)!=set(names): raise ValueError('map does not exactly cover requested selection')
    return [rows[n] for n in names]


def layout(blob):
    sections,functions=elf_metadata(blob)
    phoff,shoff=struct.unpack_from('<II',blob,28)
    phsize,phnum,shsize,shnum,_=struct.unpack_from('<HHHHH',blob,42)
    loads=[struct.unpack_from('<8I',blob,phoff+i*phsize) for i in range(phnum)]
    loads=[p for p in loads if p[0]==1]
    for i,p in enumerate(loads):
        if p[4]>p[5] or p[1]+p[4]>len(blob) or p[2]+p[5]>2**32 or p[3]+p[5]>2**32:
            raise ValueError('invalid LOAD extent')
        for q in loads[:i]:
            if p[2]<q[2]+q[5] and q[2]<p[2]+p[5] or p[3]<q[3]+q[5] and q[3]<p[3]+p[5]:
                raise ValueError('overlapping LOAD extents')
    for s in sections:
        if s['flags']&6==6 and s['size'] and s['kind']!=8:
            if not any(p[6]&1 and p[2]<=s['address'] and s['address']+s['size']<=p[2]+p[4] for p in loads):
                raise ValueError('executable section has no executable LOAD')
    headers=[struct.unpack_from('<10I',blob,shoff+i*shsize) for i in range(shnum)]
    symbols={}
    for h in headers:
        if h[1]!=2: continue
        strings=blob[headers[h[6]][4]:sum(headers[h[6]][4:6])]
        for off in range(h[4],h[4]+h[5],16):
            n,value,size,info,_,index=struct.unpack_from('<IIIBBH',blob,off)
            if not index: continue
            end=strings.find(b'\0',n)
            if n>=len(strings) or end<0: raise ValueError('invalid symbol name')
            name=strings[n:end].decode('utf-8')
            symbols.setdefault(name,[]).append(dict(value=value,size=size,kind=info&15,index=index))
    return sections,functions,loads,symbols


def one(symbols,name):
    rows=symbols.get(name,[])
    if len(rows)!=1: raise ValueError('missing/ambiguous symbol '+name)
    return rows[0]


def section_at(sections,address,size):
    found=[s for s in sections if s['flags']&2 and s['kind']!=8 and s['address']<=address and address+size<=s['address']+s['size']]
    if len(found)!=1: raise ValueError('range has no unique allocated section')
    return found[0]


def bytes_at(blob,sections,address,size):
    s=section_at(sections,address,size); off=s['offset']+address-s['address']
    return blob[off:off+size]


def branch_target(branch,pc,thumb):
    # Decode the unconditional architectural forms independently of the patcher.
    if len(branch)!=4: raise ValueError('redirect must be four bytes')
    if thumb:
        first,second=struct.unpack('<HH',branch)
        if first&0xf800!=0xf000 or second&0xd000!=0x9000 or pc%2: raise ValueError('redirect is not Thumb B.W')
        sign=(first>>10)&1
        i1=1^((second>>13)&1)^sign; i2=1^((second>>11)&1)^sign
        offset=(sign<<24)|(i1<<23)|(i2<<22)|((first&0x3ff)<<12)|((second&0x7ff)<<1)
        if sign: offset-=1<<25
        return pc+4+offset
    word=struct.unpack('<I',branch)[0]
    if word&0xff000000!=0xea000000 or pc%4: raise ValueError('redirect is not unconditional ARM B')
    offset=word&0xffffff
    if offset&0x800000: offset-=1<<24
    return pc+8+(offset<<2)


def check_artifacts(original,candidate,mapping,names):
    ins,inf,inloads,isyms=layout(original); outs,outf,outloads,osyms=layout(candidate)
    start=one(isyms,'__bolt_reserved_start')['value']; end=one(isyms,'__bolt_reserved_end')['value']
    if not start<end or end-start>8*1024*1024: raise ValueError('invalid linked reservation')
    reserve=section_at(ins,start,end-start)
    if not reserve['flags']&4 or any(bytes_at(original,ins,start,end-start)):
        raise ValueError('reservation must be executable zero-filled input space')
    for name in ('__bolt_reserved_start','__bolt_reserved_end','_end'):
        if one(isyms,name)['value']!=one(osyms,name)['value']: raise ValueError('kernel boundary changed')
    kernel_end=one(isyms,'_end')['value']
    if kernel_end!=max(p[2]+p[5] for p in inloads): raise ValueError('kernel end does not match original LOAD boundary')
    if end>kernel_end: raise ValueError('reservation outside kernel allocation boundary')
    if any(f['kind']==2 and start<f['address']+f['size'] and f['address']<end for f in inf):
        raise ValueError('reservation overlaps original function code')
    if struct.unpack_from('<I',original,24)!=struct.unpack_from('<I',candidate,24): raise ValueError('boot entry changed')
    # Preserve the original allocation/load contract, including zero-filled BSS.
    if [p[2:] for p in inloads]!=[p[2:] for p in outloads]: raise ValueError('kernel LOAD layout changed')
    rows=read_map(mapping,names); ranges=[]
    for row in rows:
        name=row['name']; old=row['input']; new=row['output']; size=row['output_size']
        a=[f for f in inf if f['name']==name and f['kind']==2]; b=[f for f in outf if f['name']==name and f['kind']==2]
        if len(a)!=1 or len(b)!=1 or a[0]['address']!=old or b[0]['address']!=new or b[0]['size']!=size or a[0]['thumb']!=b[0]['thumb']:
            raise ValueError('map/function identity mismatch')
        thumb=a[0]['thumb']; align=2 if thumb else 4
        if a[0]['size']<4 or old%align or new%align or old==new or not start<=new<new+size<=end:
            raise ValueError('emitted/redirected range outside contract')
        for lo,hi in ranges:
            if old<hi and lo<old+4 or new<hi and lo<new+size: raise ValueError('overlapping entry/body ranges')
        ranges.extend([(old,old+4),(new,new+size)])
        if any(f['kind']==2 and old<f['address']<old+4 for f in inf): raise ValueError('secondary entry overwritten')
        orig_section=section_at(ins,old,4); old_section=section_at(outs,old,4); new_section=section_at(outs,new,size)
        if not all(s['flags']&4 for s in (orig_section,old_section,new_section)) or not new_section['name'].startswith('.text'):
            raise ValueError('non-executable original/emitted entry')
        if bytes_at(original,ins,old,4)!=bytes_at(candidate,outs,new,4): raise ValueError('emitted prologue mismatch')
        branch=bytes_at(candidate,outs,old,4)
        if branch_target(branch,old,thumb)!=new: raise ValueError('entry does not redirect to emitted function')
        row.update(thumb=thumb,branch_hex=branch.hex())
    # Every loaded byte outside the reservation and selected four-byte branches
    # must remain identical. This also protects boot_alloc pointers and callers.
    allowed=[(start,end)]+[(r['input'],r['input']+4) for r in rows]
    for a,b in zip(inloads,outloads):
        x=bytearray(original[a[1]:a[1]+a[4]]); y=bytearray(candidate[b[1]:b[1]+b[4]])
        for lo,hi in allowed:
            lo=max(lo,a[2]); hi=min(hi,a[2]+a[4])
            if lo<hi: x[lo-a[2]:hi-a[2]]=y[lo-a[2]:hi-a[2]]
        if x!=y: raise ValueError('unselected loaded bytes changed')
    return dict(start=start,end=end,rows=rows)


def cpu_frames(text):
    frames=[]; pending=None; regs=[]
    for line in text.splitlines():
        if not line.strip() or line.startswith('Stopped execution of TB chain'): continue
        if line.startswith('Trace '):
            if pending is not None: raise ValueError('incomplete CPU frame')
            m=re.fullmatch(r'Trace 0: 0x[0-9a-fA-F]+ \[[0-9a-fA-F]+/([0-9a-fA-F]{8,16})/[0-9a-fA-F]+/[0-9a-fA-F]+\](?: .*)?',line)
            if not m or int(m[1],16)>0xffffffff: raise ValueError('unsupported CPU trace header')
            pending=int(m[1],16); regs=[]; continue
        if line.startswith('R'):
            values=re.findall(r'R(\d\d)=([0-9a-fA-F]{8})',line)
            if pending is None or len(values)!=4 or line!=' '.join('R'+n+'='+v for n,v in values) or [int(n) for n,_ in values]!=list(range(len(regs),len(regs)+4)) or len(regs)>=16:
                raise ValueError('malformed CPU registers')
            regs.extend(int(v,16) for _,v in values); continue
        if line.startswith('PSR='):
            m=re.fullmatch(r'PSR=([0-9a-fA-F]{8}) [NZCVnzcv-]{4} ([AT]) svc32',line)
            if pending is None or len(regs)!=16 or not m or regs[15]!=pending: raise ValueError('malformed CPU status/PC')
            psr=int(m[1],16); thumb=m[2]=='T'
            if psr&31!=19 or bool(psr&32)!=thumb: raise ValueError('CPU mode/ISA mismatch')
            frames.append(dict(pc=pending,registers=regs,psr=psr,thumb=thumb)); pending=None
            if len(frames)>4096: raise ValueError('CPU trace exceeds frame bound')
            continue
        raise ValueError('unexpected CPU trace record')
    if pending is not None or not frames: raise ValueError('missing/incomplete CPU trace')
    return frames


def check_execution(text,rows):
    frames=cpu_frames(text); addresses={r[k]:r['thumb'] for r in rows for k in ('input','output')}
    for f in frames:
        if f['pc'] not in addresses or f['thumb']!=addresses[f['pc']]: raise ValueError('unexpected entry PC/ISA')
    coverage=[]
    for row in rows:
        matches=[(a,b) for a,b in zip(frames,frames[1:]) if a['pc']==row['input'] and b['pc']==row['output']
                 and a['registers'][:15]==b['registers'][:15] and a['psr']==b['psr']]
        if not matches: raise ValueError('no unchanged live redirect/entry pair for '+row['name'])
        coverage.append(dict(name=row['name'],pairs=len(matches),input=row['input'],output=row['output'],thumb=row['thumb']))
    return coverage


def trace_bound(trace):
    if trace.exists() and trace.stat().st_size>4*1024*1024:
        raise ValueError('CPU trace exceeds byte bound')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True); p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--map',type=Path,required=True); p.add_argument('--funcs',required=True)
    p.add_argument('--out',type=Path,required=True); p.add_argument('--qemu',default='qemu-system-arm')
    p.add_argument('--timeout',type=float,default=120)
    a=p.parse_args(); names=selection(a.funcs)
    if not 0<a.timeout<=600: p.error('bounded timeout required')
    qemu=shutil.which(a.qemu)
    if not qemu: raise ValueError('QEMU required')
    a.out.mkdir(parents=True,exist_ok=True); out=Path(tempfile.mkdtemp(prefix='rewrite-',dir=a.out.resolve()))
    print('Evidence:',out,flush=True)
    sources={'baseline.elf':a.elf,'candidate.elf':a.candidate,'functions.map':a.map}
    hashes={}
    for n,path in sources.items():
        (out/n).write_bytes(path.read_bytes()); hashes[n]=sha256(out/n)
    if hashes['baseline.elf'] not in CONTRACTS:
        raise ValueError('no reviewed independent oracle contract for input image')
    scripts={n:sha256(ROOT/n) for n in ('scripts/qemu_rewrite_gate.py','scripts/qemu_workload_gate.py','scripts/qemu_bench_oracle.py','scripts/profile_identity.py','scripts/pi4/passes_check.py')}
    revision=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(); tool_hash=sha256(qemu)
    checked=check_artifacts((out/'baseline.elf').read_bytes(),(out/'candidate.elf').read_bytes(),(out/'functions.map').read_text(encoding='utf-8'),names)
    commands={}; results={}; oracles={}
    with tempfile.TemporaryDirectory(prefix='qemu-entry-') as temporary:
        trace=Path(temporary)/'entries.trace'
        for name in ('baseline','candidate'):
            command=[qemu,'-machine','virt','-cpu','cortex-a15','-m','512','-smp','1','-display','none','-monitor','none','-serial','stdio','-append','lk.bolt_bench=all','-kernel',str(out/(name+'.elf'))]
            if name=='candidate':
                filt=','.join(f'0x{r[k]:x}+1' for r in checked['rows'] for k in ('input','output'))
                command+=['-d','exec,cpu,nochain','-dfilter',filt,'-D',str(trace)]
            commands[name]=command
            try: results[name]=boot(command,out/(name+'.log'),a.timeout,lambda:trace_bound(trace))
            finally:
                if trace.exists(): shutil.copyfile(trace,out/'entries.trace')
            oracles[name]=check_results(hashes['baseline.elf'],results[name]['results'])
        if results['baseline']['results']!=results['candidate']['results']: raise ValueError('candidate results differ from baseline')
    if (out/'entries.trace').stat().st_size>4*1024*1024: raise ValueError('CPU trace exceeds byte bound')
    coverage=check_execution((out/'entries.trace').read_text(encoding='utf-8'),checked['rows'])
    for n,path in sources.items():
        if sha256(path)!=hashes[n] or sha256(out/n)!=hashes[n]: raise ValueError('artifact changed during capture')
    if scripts!={n:sha256(ROOT/n) for n in scripts} or sha256(qemu)!=tool_hash: raise ValueError('verifier/QEMU changed')
    if revision!=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(): raise ValueError('revision changed')
    write_json(out/'rewrite.json',dict(schema=2,scope='selected entry TB execution/ISA witnesses and eighteen independent sink oracles for approved input; no whole-LK/state, hardware or clean-build proof',
        selected=names,emitted_redirected=checked,executed=coverage,results=results,commands=commands,artifacts=hashes,scripts=scripts,
        independent_oracles=oracles,repository_revision=revision,qemu_sha256=tool_hash,logs={n:sha256(out/n) for n in ('baseline.log','candidate.log','entries.trace')}))
    print('SELECTED ENTRY EXECUTION / OUTPUT CONSISTENCY: '+str(out/'rewrite.json'),flush=True)


if __name__=='__main__':
    try: main()
    except (ValueError,OSError) as error: raise SystemExit('error: '+str(error))
