import json,re,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'scripts'),str(root/'scripts/pi4')]
from profile_identity import elf_metadata,sha256
out=root/'out/r35'; rows=[]
for label,stem in [('instrumented','cspgo_thinlto.instr'),('optimized','cspgo_thinlto_bolt')]:
    elf=out/'counter'/(stem+'.elf'); image=out/'counter'/(stem+'.bin')
    _,symbols=elf_metadata(elf.read_bytes())
    symbol=next(s for s in symbols if s['name']=='bolt_bench_stair_kernel' and s['kind']==2)
    lo=symbol['address']; hi=lo+symbol['size']
    cmd=[sys.executable,str(root/'scripts/pi4/pi4_run.py'),str(image),'--port','COM5','--reboot','--wait','30','--max-wait','120','--wdog','180',f'bolt_sample watch {lo:x} {hi:x}','bolt_sample start 20000',*(['bolt_bench stair 0 0']*3),'bolt_sample stop']
    result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=420)
    log=out/('watch-'+label+'.log');log.write_bytes(result.stdout)
    assert result.returncode==0,(label,result.returncode)
    text=result.stdout.decode('utf-8','replace'); hits=re.findall(r'bolt_sample: watch 0 hits per core: (\d+) (\d+) (\d+) (\d+)',text)
    assert len(hits)==1 and sum(map(int,hits[0]))>0,(label,hits)
    reports=re.findall(r'bolt_bench: stair acc=(0x[0-9a-f]+)',text)
    assert reports==['0x2f744325']*3,reports
    assert '$ wdog 0' in text and 'bolt_sample: watch 0 ' in text
    rows.append(dict(image=stem,image_sha256=sha256(image),elf_sha256=sha256(elf),range=[hex(lo),hex(hi)],hits_per_core=list(map(int,hits[0])),log_sha256=sha256(log),sampler_stopped=True,watch_ranges_cleared=True,watchdog_disabled=True))
(out/'rewritten-pc.json').write_text(json.dumps(dict(passed=True,scope='PCs observed inside each mapped rewritten body on Pi A72; three training-input runs. Sampling alters training visibility and is not a timing or edge-count measurement.',rows=rows),indent=2)+'\n')
print(json.dumps(rows,indent=2))
