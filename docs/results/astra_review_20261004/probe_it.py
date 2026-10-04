from pathlib import Path
import hashlib,json,subprocess,tempfile
root=Path('/home/user/bolt-aarch32');out=Path(tempfile.mkdtemp(prefix='astra-review-it-',dir=root/'out'))
tools={'on':root/'build-atfe/bin','off':root/'out/correctness/build-atfe-noasserts-20261002/bin'}
header='''.syntax unified
.arch armv7-a
.text
.arm
.global _start
.type _start,%function
_start:
push {r4,lr}
bl good_thumb
pop {r4,pc}
.size _start,.-_start
'''
def fn(name,body,isa='thumb'):
    return f'.balign 4\n.{isa}\n.global {name}\n.type {name},%function\n'+('.thumb_func\n' if isa=='thumb' else '')+f'{name}:\n{body}\n.size {name},.-{name}\n'
record={'scope':'isolated diagnostic host probe; no hardware or source mutation','tools':{},'cases':[]}
for mode,tc in tools.items():
    record['tools'][mode]={'llvm_bolt_sha256':hashlib.sha256((tc/'llvm-bolt').read_bytes()).hexdigest()}
    for name,bad in [('control',''),('truncated_itt',fn('bad_it','.hword 0xbf04\n.hword 0x2001')),('truncated_ite',fn('bad_it','.hword 0xbf0c\n.hword 0x2001'))]:
        d=out/(mode+'-'+name);d.mkdir();src=d/'input.s';src.write_text(header+bad+fn('good_thumb','bx lr')+fn('another_good','bx lr')+fn('last_arm','bx lr','arm'))
        ld=d/'layout.ld';ld.write_text('ENTRY(_start)\nSECTIONS { . = 0x8000; .text : { *(.text*) } }\n')
        subprocess.run([str(tc/'llvm-mc'),'-triple=armv7-none-eabi','-arm-add-build-attributes','-filetype=obj',str(src),'-o',str(d/'input.o')],check=True,capture_output=True)
        subprocess.run([str(root/'build-atfe/bin/ld.lld'),'--emit-relocs','-T',str(ld),str(d/'input.o'),'-o',str(d/'input.elf')],check=True,capture_output=True)
        cmd=[str(tc/'llvm-bolt'),str(d/'input.elf'),'-o','/dev/null','--no-huge-pages','-lite=0','--arm-admission-report='+str(d/'report.json')]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=30);(d/'run.log').write_text(p.stdout+p.stderr)
        report=json.loads((d/'report.json').read_text()) if (d/'report.json').exists() else None
        row={'mode':mode,'case':name,'exit':p.returncode,'input_sha256':hashlib.sha256((d/'input.elf').read_bytes()).hexdigest(),'functions':report['functions'] if report else None,'command':cmd}
        record['cases'].append(row);print(mode,name,p.returncode,[(f['name'],f['status'],f.get('reason')) for f in row['functions']] if row['functions'] else (p.stdout+p.stderr)[-500:])
(out/'probe.json').write_text(json.dumps(record,indent=2)+'\n');print('EVIDENCE',out)
