"""Command-framed measurement records; output consistency is not execution proof."""
import re
import os
import sys
import hashlib
import tempfile
from pathlib import Path

from proc_util import run_bounded

CYCLE = re.compile(r'bolt_bench: (\w+) done \((\d+) cycles\)')
PMU = re.compile(r'bolt_bench: (\w+) pmu inst=(\d+) l1i_refill=(\d+) l1d_refill=(\d+) br_mispred=(\d+)(?: taken=(\d+))?')
ACC = re.compile(r'bolt_bench: (\w+) acc=(0x[0-9a-fA-F]+)')
FIELDS = ['inst','l1i_refill','l1d_refill','br_mispred','taken']


def parse_measurements(text,command,kernels,runs):
    if not 1 <= runs <= 32 or not kernels or len(set(kernels)) != len(kernels):
        raise ValueError('invalid requested measurement matrix')
    text = text.replace('\r\n','\n').replace('\r','\n')
    frames = list(re.finditer(r'^\$ ([^\n]*)$',text,re.M))
    chosen = [i for i,m in enumerate(frames) if m[1] == command]
    if len(chosen) != runs:
        raise ValueError('missing/extra measurement command frames')
    def records(body):
        found=[]
        for line in body.splitlines():
            related = re.search(r'bolt_bench: (\w+) (done\b|pmu\b|pmu2\b|pmucustom\b|acc=|FAIL\b)',line)
            if not related: continue
            if related[1] not in kernels:
                raise ValueError('unexpected measured workload')
            match = CYCLE.fullmatch(line) or PMU.fullmatch(line) or ACC.fullmatch(line)
            if not match:
                raise ValueError('invalid/unsupported measurement record: '+line)
            kind = 'cycle' if CYCLE.fullmatch(line) else 'pmu' if PMU.fullmatch(line) else 'acc'
            found.append((kind,match))
        return found
    rows=[]; consumed=0
    for repetition,i in enumerate(chosen,1):
        stop=frames[i+1].start() if i+1 < len(frames) else len(text)
        found=records(text[frames[i].end():stop]); consumed+=len(found)
        expected=[(kind,k) for k in kernels for kind in ['cycle','pmu','acc']]
        if [(kind,m[1]) for kind,m in found] != expected:
            raise ValueError('incomplete/duplicate/reordered measurement records')
        for k,index in zip(kernels,range(0,len(found),3)):
            cycle=int(found[index][1][2]); pmu=found[index+1][1]; acc=int(found[index+2][1][2],16)
            counters=[int(v) for v in pmu.groups()[1:] if v is not None]
            if not 0 < cycle < 2**64 or not 0 <= acc < 2**32 or any(v >= 2**32 for v in counters):
                raise ValueError('measurement value outside hardware width')
            rows.append(dict(kernel=k,run=repetition,cycles=cycle,acc=f'0x{acc:08x}',**dict(zip(FIELDS,counters))))
    if len(records(text)) != consumed:
        raise ValueError('measurement records outside requested commands')
    return rows


def consistent(records,kernels):
    for k in kernels:
        values={r['acc'] for r in records if r.get('kernel',k)==k}
        if len(values)!=1 or not next(iter(values),''):
            raise ValueError('checksum mismatch/missing result for '+k)


def capture_measurements(image,port,command,kernels,runs,wait,max_wait):
    """Save exact upload and child output even when parsing or child execution fails."""
    here=Path(__file__).resolve().parent
    parent=Path(os.environ.get('PI4_EVIDENCE_DIR', str(here.parents[1]/'out/pi4')))
    parent.mkdir(parents=True,exist_ok=True)
    evidence=Path(tempfile.mkdtemp(prefix='measure-',dir=parent))
    source=Path(image); payload=source.read_bytes()
    if not payload: raise ValueError('empty image')
    snapshot=evidence/'image.bin'; snapshot.write_bytes(payload)
    cmd=[sys.executable,str(here/'pi4_run.py'),str(snapshot),'--port',port,'--reboot','--wait',str(wait),'--max-wait',str(max_wait)]
    loader=os.environ.get('PI4_FAST_LOADER')
    if loader:
        loader_bytes=Path(loader).read_bytes(); loader_snapshot=evidence/'loader.img'
        loader_snapshot.write_bytes(loader_bytes); cmd+=['--fast-loader',str(loader_snapshot)]
    cmd += [command]*runs
    result=run_bounded(cmd,150)
    (evidence/'serial.log').write_bytes(result.stdout)
    print('Measurement evidence:',evidence,flush=True)
    if result.returncode!=0:
        raise RuntimeError(f'pi4_run failed ({result.returncode}); see {evidence}/serial.log')
    if source.read_bytes()!=payload or snapshot.read_bytes()!=payload:
        raise ValueError('measurement image changed')
    if loader and (Path(loader).read_bytes()!=loader_bytes or loader_snapshot.read_bytes()!=loader_bytes):
        raise ValueError('measurement loader changed')
    rows=parse_measurements(result.stdout.decode('utf-8','replace'),command,kernels,runs)
    # This is an identity/association receipt, not a correctness certificate.
    import json
    (evidence/'measurement.json').write_text(json.dumps(dict(scope='measurement association and output consistency only',
        image_sha256=hashlib.sha256(payload).hexdigest(),serial_sha256=hashlib.sha256(result.stdout).hexdigest(),
        command=command,rows=rows),indent=2)+'\n')
    return rows
