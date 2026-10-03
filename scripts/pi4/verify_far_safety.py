#!/usr/bin/env python3
"""Verify sparse staging artifacts, then certify live far-call witnesses on Pi 4."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import time
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'scripts/pi4')]
from profile_identity import elf_metadata,sha256,write_json,check_load_image
from verify_far_execution import offset,require,SEEDS
from build_far_safety import PAIRS,validate_chunks,witnesses,emitted_route,instructions
from verify_counter_state import Capture
from pi4_serial_boot import reboot_to_chainloader,resolve_port,send_image
import serial

NAMES = ['baseline','normal','reverse','bad-result','bad-flags','retained-callee']
CASE_RE = re.compile(r'^BOLT_FAR_PI CASE id=([0-9a-f]{8}) input=([0-9a-f]{8}) result=([0-9a-f]{8}) cpc=([0-9a-f]{8}) fpc=([0-9a-f]{8}) rpc=([0-9a-f]{8}) ip=([0-9a-f]{8}) fb=([0-9a-f]{8}) fa=([0-9a-f]{8}) sb=([0-9a-f]{8}) sa=([0-9a-f]{8}) mem=([0-9a-f]{8})\r?$',re.M)


def read_staged(chunks,address,size):
    result = bytearray()
    while size:
        matches = [r for r in chunks if r['address'] <= address < r['address']+len(r['data'])]
        require(len(matches) == 1,'missing/ambiguous staged bytes')
        row = matches[0]; relative = address-row['address']
        length = min(size,len(row['data'])-relative)
        result.extend(row['data'][relative:relative+length]); address += length; size -= length
    return bytes(result)


def check_artifacts(out,build):
    require(build['schema'] == 1 and build['kind'] == 'pi-far-safety' and list(build['variants']) == NAMES,'wrong fixture matrix')
    require(build['faults'] == {'bad-result':{'case_id':0,'field':0},'bad-flags':{'case_id':0,'field':14},'retained-callee':{'case_id':0,'field':11}},'wrong faults')
    for name,digest in build['files'].items():
        path = out/name
        require(path.resolve().is_relative_to(out.resolve()) and sha256(path) == digest,'changed/unsafe artifact '+name)
    original = (out/'baseline.elf').read_bytes()
    sections,symbols = elf_metadata(original)
    table = next(s for s in symbols if s['name'] == 'case_entries')
    require(table['size'] == 20*28,'wrong independent table extent')
    for name in NAMES:
        variant = build['variants'][name]
        code_name = 'normal' if name in build['faults'] else name
        require(variant['code'] == code_name,'wrong source code')
        code = (out/(code_name+'.elf')).read_bytes()
        rows = [witnesses(code,'caller_'+a+'_'+b,'far_'+a+'_'+b) for a,b in PAIRS]
        routes = [emitted_route(code,r) for r in rows] if code_name != 'baseline' else []
        require(routes == variant['routes'],'route mismatch')
        if name in ['bad-result','bad-flags']:
            callee = rows[0]['callee']; data = bytearray(code)
            adds = [address for address,raw in instructions(code,callee['address'],callee['size'],False) if raw == bytes.fromhex('070080e2')]
            require(len(adds) == 1,'wrong fault instruction')
            struct.pack_into('<I',data,offset(data,adds[0],4),0xe2800008 if name == 'bad-result' else 0xe2900007)
            code = bytes(data)
        elif name == 'retained-callee':
            data = bytearray(code); old = witnesses(original,'caller_arm_arm','far_arm_arm')['callee']['address']
            lo,hi = old & 0xffff,old >> 16
            struct.pack_into('<II',data,offset(data,routes[0]['stub'],8),0xe300c000 | (lo & 0xfff) | ((lo & 0xf000)<<4),0xe340c000 | (hi & 0xfff) | ((hi & 0xf000)<<4))
            code = bytes(data)
        require(hashlib.sha256(code).hexdigest() == variant['code_sha256'],'wrong executed code identity')
        expected_original = bytearray(original)
        expectations = []
        for i,(a,b) in enumerate(PAIRS):
            row = rows[i]; fn = row['caller']['address'] | int(row['caller']['thumb'])
            ip = 0xa5a5a5a5 if name == 'baseline' else routes[i]['absolute_target']
            for j,seed in enumerate(SEEDS):
                values = [fn,seed,(seed+7)&0xffffffff,row['caller_pc'],row['callee_pc'],row['return_pc'],ip]
                struct.pack_into('<7I',expected_original,offset(expected_original,table['address']+(i*5+j)*28,28),*values)
                expectations.append(dict(pair=a+'-'+b,id=i*5+j,input=seed,result=values[2],cpc=values[3],fpc=values[4],rpc=values[5],ip=ip))
        require(expectations == variant['expectations'],'wrong independent expectations')
        check_load_image(out/(name+'.stage.elf'),out/(name+'.bin'))
        image = (out/(name+'.bin')).read_bytes()
        require(len(image) < 0x100000-0x8000 and hashlib.sha256(image).hexdigest() == variant['image_sha256'],'wrong upload size/identity')
        stage = (out/(name+'.stage.elf')).read_bytes(); _,stage_symbols = elf_metadata(stage)
        require(struct.unpack_from('<I',stage,24)[0] == 0x8000,'wrong bootstrap entry')
        plans = json.loads((out/variant['plan']).read_text())['chunks']; validate_chunks(plans)
        tables = [s for s in stage_symbols if s['name'] == 'chunk_table']
        require(len(tables) == 1 and tables[0]['size'] == len(plans)*12,'wrong copy table')
        chunks = []
        for i,row in enumerate(plans):
            address,size,source = struct.unpack_from('<III',image,tables[0]['address']-0x8000+i*12)
            require((address,size,source) == (row['address'],row['size'],row['source_address']),'copy-table mismatch')
            require(0x8000 <= source < source+size <= 0x8000+len(image),'source outside upload')
            data = image[source-0x8000:source-0x8000+size]
            require(data == (out/row['file']).read_bytes() and hashlib.sha256(data).hexdigest() == row['sha256'],'packed bytes mismatch')
            chunks.append(dict(address=address,data=data))
        # Verify every original allocated byte (with only allowed case metadata edits)
        # and every emitted nonzero page, including complete instructions and stubs.
        known = []
        for s in sections:
            if not s['flags'] & 2 or not s['size']: continue
            body = bytes(s['size']) if s['kind'] == 8 else expected_original[s['offset']:s['offset']+s['size']]
            require(read_staged(chunks,s['address'],s['size']) == body,'original harness/table staging mismatch')
            known.append((s['address'],s['address']+s['size']))
        if name != 'baseline':
            emitted,_ = elf_metadata(code); text = next(s for s in emitted if s['name'] == '.text')
            body = code[text['offset']:text['offset']+text['size']]
            for relative in range(0,len(body),4096):
                page = body[relative:relative+4096]
                if any(page):
                    require(read_staged(chunks,text['address']+relative,len(page)) == page,'emitted code staging mismatch')
                    known.append((text['address']+relative,text['address']+relative+len(page)))
        require(all(any(start <= r['address'] and r['address']+len(r['data']) <= end for start,end in known) for r in chunks),'unexplained staged extent')


def check_result(text,expectations,negative=None):
    begin = re.findall(r'^BOLT_FAR_PI BEGIN mode=([0-9a-f]{8}) core=([0-9a-f]{8}) sctlr=([0-9a-f]{8})\r?$',text,re.M)
    require(len(begin) == text.count('BOLT_FAR_PI BEGIN') == 1 and begin[0][:2] == ('0000001a','00000000') and not int(begin[0][2],16) & 0x1005,'wrong fixture entry')
    failures = re.findall(r'^BOLT_FAR_PI FAIL case=([0-9a-f]{8}) field=([0-9a-f]{8}) expected=([0-9a-f]{8}) actual=([0-9a-f]{8})\r?$',text,re.M)
    passes = re.findall(r'^BOLT_FAR_PI PASS cases=(\d+)\r?$',text,re.M)
    cases = [dict(zip(['id','input','result','cpc','fpc','rpc','ip','fb','fa','sb','sa','mem'],map(lambda x:int(x,16),match))) for match in CASE_RE.findall(text)]
    require(len(cases) == text.count('BOLT_FAR_PI CASE') and len(failures) == text.count('BOLT_FAR_PI FAIL') and len(passes) == text.count('BOLT_FAR_PI PASS'),'malformed result record')
    if negative:
        require(not passes and len(failures) == 1 and len(cases) == negative['case_id'],'fault did not fail at expected completion')
        case,field,expected,actual = map(lambda x:int(x,16),failures[0])
        require(case == negative['case_id'] and field == negative['field'] and expected != actual,'wrong fault outcome')
        return dict(expected_failure=True,case_id=case,field=field,expected=expected,actual=actual)
    require(not failures and passes == ['20'] and len(cases) == len(expectations) == 20,'incomplete/duplicate pass')
    for actual,expected in zip(cases,expectations):
        require(all(actual[key] == expected[key] for key in ['id','input','result','cpc','fpc','rpc','ip']),'wrong ordered execution witness')
        require(actual['mem'] == expected['result'] and not (actual['fb'] ^ actual['fa']) & 0xf0000000 and actual['sb'] == actual['sa'] and not actual['sa'] & 7,'wrong memory/flags/stack')
    return dict(passed=True,cases=cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True); parser.add_argument('--port',default='auto')
    args = parser.parse_args(); out = args.build.resolve()
    manifest_bytes = (out/'build.json').read_bytes(); build = json.loads(manifest_bytes)
    check_artifacts(out,build)
    evidence = Path(tempfile.mkdtemp(prefix='pi-verify-',dir=out)); print('Evidence:',evidence,flush=True)
    (evidence/'build.json').write_bytes(manifest_bytes)
    loader_path = ROOT/'tools/pi4-serialboot-fast/kernel7l_fast.img'; loader = loader_path.read_bytes()
    (evidence/'loader.img').write_bytes(loader)
    scripts = {p.relative_to(ROOT).as_posix():sha256(p) for p in [Path(__file__),ROOT/'scripts/pi4/build_far_safety.py',ROOT/'scripts/pi4/pi4_serial_boot.py',ROOT/'scripts/pi4/verify_counter_state.py',ROOT/'scripts/profile_identity.py',ROOT/'scripts/verify_far_execution.py',ROOT/'scripts/verify_far_interwork.py']}
    revision = subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    port_name = resolve_port(args.port); results = {}; upload_hashes = {}
    for name in NAMES:
        image = (out/(name+'.bin')).read_bytes(); digest = hashlib.sha256(image).hexdigest()
        require(digest == build['variants'][name]['image_sha256'],'changed upload')
        upload = evidence/(name+'.bin'); upload.write_bytes(image); upload_hashes[name] = digest
        console = Capture(evidence/(name+'.log'))
        try:
            with serial.Serial(port_name,115200,timeout=.1,write_timeout=20) as port:
                port.reset_input_buffer(); reboot_to_chainloader(port,console,3_000_000)
                send_image(port,console,loader,30); send_image(port,console,image,30,fast=True)
                deadline = time.monotonic()+30
                while time.monotonic() < deadline:
                    console.write(port.read(port.in_waiting or 1)); text = console.data.decode('ascii','replace')
                    last = max(text.rfind('BOLT_FAR_PI PASS'),text.rfind('BOLT_FAR_PI FAIL'))
                    if last >= 0 and text.rfind('SBOOT?') > last: break
                text = console.data.decode('ascii','replace'); last = max(text.rfind('BOLT_FAR_PI PASS'),text.rfind('BOLT_FAR_PI FAIL'))
                require(last >= 0 and text.rfind('SBOOT?') > last,'missing result/watchdog return '+name)
                results[name] = check_result(text,build['variants'][name]['expectations'],build['faults'].get(name))
                print(name,'passed' if name not in build['faults'] else results[name],flush=True)
        finally:
            if console.log: console.log.close()
    check_artifacts(out,build)
    require((out/'build.json').read_bytes() == manifest_bytes,'manifest changed')
    require((evidence/'build.json').read_bytes() == manifest_bytes and (evidence/'loader.img').read_bytes() == loader,'manifest/loader snapshots changed')
    require(scripts == {name:sha256(ROOT/name) for name in scripts} and hashlib.sha256(loader).hexdigest() == sha256(loader_path),'scripts/loader changed')
    require(upload_hashes == {name:sha256(evidence/(name+'.bin')) for name in upload_hashes},'upload snapshots changed')
    require(revision == subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),'revision changed')
    write_json(evidence/'verification.json',dict(schema=1,verified=True,kind='pi-far-safety',results=results,port=port_name,scope=build['scope'],repository_revision=revision,
        build_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),uploaded_sha256=upload_hashes,loader_sha256=hashlib.sha256(loader).hexdigest(),scripts=scripts,
        logs={p.name:sha256(p) for p in evidence.glob('*.log')},routes={name:build['variants'][name]['routes'] for name in ['normal','reverse']}))
    print('Verified all sparse far-call images and watchdog returns:',evidence,flush=True)


if __name__ == '__main__': main()
