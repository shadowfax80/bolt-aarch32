#!/usr/bin/env python3
"""Run the isolated inlining/branch fixture and its result fault on Pi 4."""
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


def check_result(text, negative=None, cases=55):
    begins = re.findall(r'^BOLT_INLINE_STATE BEGIN mode=([0-9a-f]{8}) core=([0-9a-f]{8})\r?$',text,re.M)
    require(begins == [('0000001a','00000000')] and text.count('BOLT_INLINE_STATE BEGIN') == 1, 'missing/duplicate/wrong fixture entry')
    failures = re.findall(r'^BOLT_INLINE_STATE FAIL case=([0-9a-f]{8}) field=([0-9a-f]{8}) expected=([0-9a-f]{8}) actual=([0-9a-f]{8})\r?$',text,re.M)
    passes = re.findall(r'^BOLT_INLINE_STATE PASS cases=(\d+)\r?$',text,re.M)
    require(len(failures) == text.count('BOLT_INLINE_STATE FAIL') and len(passes) == text.count('BOLT_INLINE_STATE PASS'), 'malformed result marker')
    if negative is not None:
        require(not passes and len(failures) == 1, 'fault did not fail exactly once')
        case, field, expected, actual = (int(x,16) for x in failures[0])
        require(case == negative['case_id'] and field == negative['field'] and expected != actual, 'wrong fault location')
        return dict(expected_failure=True,case_id=case,field=field,expected=expected,actual=actual)
    require(not failures and passes == [str(cases)], 'missing complete fixture pass')
    return dict(passed=True,cases=cases)


def check_artifacts(out, build):
    pass_matrix = build.get('pass_matrix',False)
    cases, wrappers = (70,14) if pass_matrix else (55,11)
    require(build['schema'] == 1 and build['kind'] == 'pi-inline-safety' and build['cases'] == cases, 'wrong build')
    variants = {'normal','reverse','inline_all','inline_small','peepholes'} if build.get('pass_matrix',False) else {'normal','reverse'}
    require(set(build['variants']) == variants and set(build['faults']) == {'bad-result','bad-cbz-flags'}, 'wrong variant/fault matrix')
    for name,digest in build['files'].items():
        require(sha256(out/name) == digest, 'changed artifact '+name)
    redirects = json.loads((out/'redirects.json').read_text())
    for name in ('baseline',*build['variants'],*build['faults']):
        elf,raw = (out/(name+'.elf')).read_bytes(),(out/(name+'.bin')).read_bytes()
        sections,_ = elf_metadata(elf)
        loaded = [s for s in sections if 'physical' in s]
        base = min(s['physical'] for s in loaded)
        require(base == 0x8000 and struct.unpack_from('<I',elf,24)[0] == 0x8000, 'wrong boot entry/base')
        require(len(raw) == max(s['physical']+s['size'] for s in loaded)-base < 0x700000-0x8000, 'wrong image size')
        for s in loaded:
            require(s['physical'] == s['address'], 'MMU-off physical mismatch')
            offset = s['physical']-base
            require(raw[offset:offset+s['size']] == elf[s['offset']:s['offset']+s['size']], 'ELF/raw mismatch')
        if name != 'baseline':
            rows = redirects['normal' if name in build['faults'] else name]
            require(len(rows) == wrappers and len({r['name'] for r in rows}) == wrappers and sum(r['thumb'] for r in rows) == 6, 'wrong redirect matrix')
            for r in rows:
                s = next(s for s in loaded if s['address'] <= r['input'] < r['input']+4 <= s['address']+s['size'])
                pos = s['offset']+r['input']-s['address']
                branch = elf[pos:pos+4]
                require(branch.hex() == r['branch_hex'] and branch_target(branch,r['input'],r['thumb']) == r['output'], 'wrong redirect')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--port', default='auto')
    args = parser.parse_args()
    out = args.build.resolve()
    build = json.loads((out/'build.json').read_text())
    check_artifacts(out,build)
    evidence = Path(tempfile.mkdtemp(prefix='pi-verify-',dir=out))
    print('Evidence:',evidence,flush=True)
    port_name = resolve_port(args.port)
    results = {}
    for name in ('baseline',*build['variants'],*build['faults']):
        console = Capture(evidence/(name+'.log'))
        try:
            with serial.Serial(port_name,115200,timeout=0.1,write_timeout=20) as port:
                port.reset_input_buffer()
                reboot_to_chainloader(port,console,3_000_000)
                send_image(port,console,(ROOT/'tools/pi4-serialboot-fast/kernel7l_fast.img').read_bytes(),30)
                send_image(port,console,(out/(name+'.bin')).read_bytes(),30,fast=True)
                deadline = time.monotonic()+30
                while time.monotonic() < deadline:
                    console.write(port.read(port.in_waiting or 1))
                    text = console.data.decode('ascii','replace')
                    last = max(text.rfind('BOLT_INLINE_STATE PASS'),text.rfind('BOLT_INLINE_STATE FAIL'))
                    if last >= 0 and text.rfind('SBOOT?') > last:
                        break
                text = console.data.decode('ascii','replace')
                last = max(text.rfind('BOLT_INLINE_STATE PASS'),text.rfind('BOLT_INLINE_STATE FAIL'))
                require(last >= 0 and text.rfind('SBOOT?') > last, name+': did not return to loader with a result')
                results[name] = check_result(text,build['faults'].get(name),build['cases'])
                print(name,results[name],flush=True)
        finally:
            if console.log:
                console.log.close()
    check_artifacts(out,build)
    report = dict(schema=1,verified=True,port=port_name,scope=build['scope'],results=results,
                  build_manifest_sha256=sha256(out/'build.json'),verifier_sha256=sha256(Path(__file__)),
                  loader_sha256=sha256(ROOT/'tools/pi4-serialboot-fast/kernel7l_fast.img'),
                  logs={p.name:sha256(p) for p in evidence.glob('*.log')})
    (evidence/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Verified all images and watchdog returns:',evidence)


if __name__ == '__main__':
    main()
