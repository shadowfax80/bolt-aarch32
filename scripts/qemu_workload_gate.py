#!/usr/bin/env python3
"""Complete LK workload/output consistency; no rewritten execution certificate."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/pi4')]
from profile_identity import sha256,write_json
from passes_check import EXPECTED_WORKLOADS


def check_guest_failure(text):
    if re.search(r'(?im)\b(?:panic|undefined (?:instruction|abort)|prefetch abort|data abort|unhandled exception)\b',text):
        raise ValueError('fatal guest exception/panic')
    if re.search(r'bolt_bench: \w+ FAIL\b',text):
        raise ValueError('workload correctness failure')


def parse_boot(text):
    text=text.replace('\r\n','\n').replace('\r','\n')
    check_guest_failure(text)
    if text.count('bolt_bench: running all from cmdline')!=1 or text.count('entering main console loop')!=1:
        raise ValueError('missing/duplicate workload start or console completion')
    results={}; completed=[]; accs=set()
    for line in text.splitlines():
        line=line.removeprefix('] ')
        if re.search(r'bolt_bench: \w+ FAIL\b',line): raise ValueError('workload correctness failure')
        if re.search(r'bolt_bench: \w+ (sink=|acc=)',line):
            m=re.fullmatch(r'bolt_bench: (\w+) (sink|acc)=(0x[0-9a-fA-F]{1,8})',line)
            if m:
                name,kind,value=m.groups(); value=f'0x{int(value,16):08x}'
                if name not in EXPECTED_WORKLOADS: raise ValueError('unexpected result workload')
                if name in results and results[name]!=value: raise ValueError('conflicting result')
                results[name]=value
                if kind=='sink': completed.append(name)
                else:
                    if name in accs: raise ValueError('duplicate accumulator result')
                    accs.add(name)
                continue
            raise ValueError('malformed result record')
    if completed!=list(EXPECTED_WORKLOADS):
        raise ValueError('incomplete/duplicate/reordered workload completion')
    return results


def boot(command,log,timeout,observe=None):
    """Own the QEMU lifetime; deliberate stop after complete output is recorded."""
    if os.name=='nt':
        raise ValueError('QEMU capture requires WSL/Linux for direct process ownership')
    status=''; process=None; stopped=False; complete_since=None
    # Concurrent DrvFS reads can fail with ENODATA; spool locally and copy the
    # closed log into the durable evidence directory on every outcome.
    with tempfile.TemporaryDirectory(prefix='qemu-serial-') as temporary:
      spool=Path(temporary)/'serial.log'
      with spool.open('wb') as output:
        try:
            process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                if observe is not None: observe()
                if spool.stat().st_size>32*1024*1024: raise ValueError('serial output exceeds bound')
                text=spool.read_bytes().decode('utf-8','replace')
                check_guest_failure(text)
                rc=process.poll()
                if rc is not None and rc!=0: raise ValueError(f'QEMU exited unsuccessfully ({rc})')
                try: results=parse_boot(text)
                except ValueError:
                    complete_since=None
                    if rc is not None: raise ValueError('QEMU exited before complete valid workload output')
                    time.sleep(.1); continue
                # Observe immediate post-output failures before deliberately
                # stopping a kernel that is expected to remain at its console.
                if rc is None:
                    if complete_since is None: complete_since=time.monotonic()
                    if time.monotonic()-complete_since<.25:
                        time.sleep(.05); continue
                status='completed-then-stopped' if rc is None else 'completed-normal-exit'
                break
            else: raise ValueError('QEMU deadline without complete valid workload output')
        finally:
            if process is not None and process.poll() is None:
                stopped=True
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
            output.flush()
            log.write_bytes(spool.read_bytes())
    # Validate the complete final log too; shutdown cannot append a hidden FAIL.
    results=parse_boot(log.read_bytes().decode('utf-8','replace'))
    allowed={-15,-9}
    if process.returncode!=0 and not (stopped and process.returncode in allowed):
        raise ValueError(f'QEMU failed during completion/cleanup ({process.returncode})')
    return dict(results=results,stop=status,returncode=process.returncode)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path); p.add_argument('--candidate',type=Path)
    p.add_argument('--check-log',type=Path)
    p.add_argument('--qemu',default='qemu-system-arm'); p.add_argument('--out',type=Path)
    p.add_argument('--cpu',default='cortex-a15'); p.add_argument('--machine',default='virt')
    p.add_argument('--memory',default='512'); p.add_argument('--smp',default='1')
    p.add_argument('--append',default='lk.bolt_bench=all'); p.add_argument('--timeout',type=float,default=120)
    a=p.parse_args()
    if a.check_log:
        parse_boot(a.check_log.read_text(errors='replace'))
        print('COMPLETE WORKLOAD LOG (no execution certificate)')
        return
    if a.elf is None or a.out is None: p.error('--elf and --out required for boot capture')
    if not 0<a.timeout<=600 or a.append!='lk.bolt_bench=all': p.error('bounded timeout and exact all-workload cmdline required')
    qemu=shutil.which(a.qemu)
    if not qemu: raise ValueError('QEMU is mandatory')
    a.out.mkdir(parents=True,exist_ok=True); out=Path(tempfile.mkdtemp(prefix='run-',dir=a.out.resolve()))
    print('Evidence:',out,flush=True)
    scripts={str(x.relative_to(ROOT)):sha256(x) for x in [Path(__file__),ROOT/'scripts/profile_identity.py',ROOT/'scripts/pi4/passes_check.py']}
    revision=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    tool_hash=sha256(qemu); sources={}; images={}; results={}; commands={}
    for name,source in [('baseline',a.elf),('candidate',a.candidate)]:
        if source is None: continue
        sources[name]=source.resolve(); data=source.read_bytes()
        if not data.startswith(b'\x7fELF'): raise ValueError('expected ELF image')
        image=out/(name+'.elf'); image.write_bytes(data); images[name]=sha256(image)
        command=[qemu,'-machine',a.machine,'-cpu',a.cpu,'-m',a.memory,'-smp',a.smp,'-display','none','-monitor','none','-serial','stdio','-append',a.append,'-kernel',str(image)]
        commands[name]=command
        results[name]=boot(command,out/(name+'.log'),a.timeout)
        if sha256(image)!=images[name] or sha256(source)!=images[name]: raise ValueError('image changed during boot')
    if 'candidate' in results and results['candidate']['results']!=results['baseline']['results']:
        raise ValueError('candidate results differ from baseline')
    if scripts!={n:sha256(ROOT/n) for n in scripts} or sha256(qemu)!=tool_hash: raise ValueError('verifier/QEMU changed')
    if revision!=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(): raise ValueError('revision changed')
    if any(sha256(sources[n])!=h or sha256(out/(n+'.elf'))!=h for n,h in images.items()): raise ValueError('image changed before receipt')
    write_json(out/'workload.json',dict(schema=1,scope='complete workload/output consistency only; no independent oracle or selected rewritten execution proof',
        output_consistent='candidate' in results,complete_workload=True,results=results,commands=commands,images=images,
        qemu_sha256=tool_hash,scripts=scripts,repository_revision=revision,logs={n:sha256(out/(n+'.log')) for n in results}))
    print('COMPLETE WORKLOAD'+(' / OUTPUT CONSISTENCY' if a.candidate else '')+': '+str(out/'workload.json'),flush=True)


if __name__=='__main__':
    try: main()
    except (ValueError,OSError) as error: sys.exit('error: '+str(error))
