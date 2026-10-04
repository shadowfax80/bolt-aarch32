from pathlib import Path
import hashlib,json,subprocess,tempfile,resource
root=Path('/home/user/bolt-aarch32');tc=root/'build-atfe/bin'
out=Path(tempfile.mkdtemp(prefix='astra-review-extra-',dir=root/'out'))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def fn(n,b): return f'.balign 4\n.global {n}\n.type {n},%function\n{n}:\n{b}\n.size {n},.-{n}\n'
head='.syntax unified\n.arch armv7-a\n.text\n.arm\n'
thunk=lambda target: f'movw r12,:lower16:{target}\nmovt r12,:upper16:{target}\nbx r12'
cases={}
for name,target in [('cycle','thunk_b'),('self','thunk_a'),('acyclic','stop')]:
    cases['thunk_'+name]=(head+fn('_start','bl thunk_a')+fn('thunk_a',thunk(target))+fn('thunk_b',thunk('thunk_a'))+fn('stop','b stop'),'_start')
for name,ins in [('normal_ldm','ldmia r4,{r3,r5}'),('sys_ldm','ldmia r4,{r3,r5}^'),('safe','mov r0,#77')]:
    body='and r2,r0,#3\nadd r3,pc,#8\nmov r1,r0\n'+ins+'\nldr pc,[r3,r2,lsl#2]\n.word c1,c2,c3,c4\n'+''.join(f'c{i}: add r0,r1,#{i}\nbx lr\n' for i in range(1,5))
    cases['table_'+name]=(head+fn('_start','bl sw\nb _start')+fn('sw',body),'sw')
for val in [8,256]:
    padding='nop\n'*(val//4)
    body=f'and r2,r0,#3\nadd r3,pc,#{val}\n'+padding+'ldr pc,[r3,r2,lsl#2]\n.word c1,c2,c3,c4\n'+''.join(f'c{i}: mov r0,#{i}\nbx lr\n' for i in range(1,5))
    cases['table_imm_'+str(val)]=(head+fn('_start','bl sw\nb _start')+fn('sw',body),'sw')
rec={'scope':'isolated host probes, assertion-enabled installed toolchain; no hardware or source mutation','tools':{n:hashlib.sha256((tc/n).read_bytes()).hexdigest() for n in ['llvm-bolt','llvm-mc','ld.lld']},'cases':[]}
for name,(asm,func) in cases.items():
    d=out/name;d.mkdir();(d/'input.s').write_text(asm);(d/'layout.ld').write_text('ENTRY(_start)\nSECTIONS { . = 0x8000; .text : { *(.text*) } }\n')
    subprocess.run([str(tc/'llvm-mc'),'-triple=armv7-none-eabi','-arm-add-build-attributes','-filetype=obj',str(d/'input.s'),'-o',str(d/'input.o')],check=True,capture_output=True)
    subprocess.run([str(tc/'ld.lld'),'--emit-relocs','-T',str(d/'layout.ld'),str(d/'input.o'),'-o',str(d/'input.elf')],check=True,capture_output=True)
    cmd=[str(tc/'llvm-bolt'),str(d/'input.elf'),'-o',str(d/'output.elf'),'--no-huge-pages','-lite=0','--funcs='+func]
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=8);log=p.stdout+p.stderr;status=p.returncode
    except subprocess.TimeoutExpired as e:
        status='timeout_8s';log=(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace')
    (d/'run.log').write_text(log)
    rec['cases'].append({'case':name,'command':cmd,'exit':status,'input_sha256':hashlib.sha256((d/'input.elf').read_bytes()).hexdigest(),'output_exists':(d/'output.elf').exists()})
    print(name,status,log[-450:])
(out/'probe.json').write_text(json.dumps(rec,indent=2)+'\n');print('EVIDENCE',out)
