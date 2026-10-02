#!/usr/bin/env python3
"""Run the bounded counter-state firmware and its deliberate failures on Pi 4."""
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
from pi4_serial_boot import Console, reboot_to_chainloader, resolve_port, send_image
import serial


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_artifacts(out, build):
    require(build['schema'] == 1 and build['kind'] == 'pi-counter-state', 'wrong build manifest')
    require(build['cases'] == 512 and build['cases_per_mode'] == 256, 'wrong case matrix')
    for name, digest in build['files'].items():
        require(sha256(out/name) == digest, 'changed artifact ' + name)
    redirects = json.loads((out/'redirects.json').read_text(encoding='utf-8'))['redirected']
    require(len(redirects) == 2 and {r['thumb'] for r in redirects} == {False,True}, 'missing ISA redirect')
    for name in ('baseline','instrumented',*build['negative_cases']):
        elf, raw = (out/(name+'.elf')).read_bytes(), (out/(name+'.bin')).read_bytes()
        sections, _ = elf_metadata(elf)
        loaded = [s for s in sections if 'physical' in s]
        base = min(s['physical'] for s in loaded)
        require(base == 0x8000 and struct.unpack_from('<I',elf,24)[0] == 0x8000, 'wrong boot base/entry')
        require(len(raw) == max(s['physical']+s['size'] for s in loaded)-base < 0x700000-0x8000, 'wrong raw length')
        for s in loaded:
            require(s['physical'] == s['address'], 'MMU-off physical mismatch')
            position = s['physical']-base
            require(raw[position:position+s['size']] == elf[s['offset']:s['offset']+s['size']], 'ELF/raw mismatch')
        if name != 'baseline':
            for row in redirects:
                s = next(s for s in loaded if s['address'] <= row['input'] < row['input']+4 <= s['address']+s['size'])
                position = s['offset']+row['input']-s['address']
                branch = elf[position:position+4]
                require(branch.hex() == row['branch_hex'] and branch_target(branch,row['input'],row['thumb']) == row['output'],
                        'wrong generated-code redirect')


def check_result(text, delta, negative=None):
    begins = re.findall(r'^BOLT_COUNTER_STATE BEGIN mode=([0-9a-f]{8}) delta=([0-9a-f]{8})\r?$', text, re.M)
    require(len(begins) == 1 and int(begins[0][0],16) in (0x1a,0x13)
            and int(begins[0][1],16) == delta, 'missing/wrong fixture entry')
    failures = re.findall(r'^BOLT_COUNTER_STATE FAIL case=([0-9a-f]{8}) field=([0-9a-f]{8}) expected=([0-9a-f]{8}) actual=([0-9a-f]{8})\r?$',text,re.M)
    passes = re.findall(r'^BOLT_COUNTER_STATE PASS cases=(\d+)\r?$',text,re.M)
    require(len(failures) == text.count('BOLT_COUNTER_STATE FAIL')
            and len(passes) == text.count('BOLT_COUNTER_STATE PASS'), 'malformed result marker')
    if negative is not None:
        require(not passes and len(failures) == 1, 'negative image did not fail exactly once')
        case,field,expected,actual = (int(x,16) for x in failures[0])
        require(case == negative['case_id'] and field == negative['field'] and expected != actual,
                'negative image failed at an unexpected check')
        return dict(expected_failure=True,case_id=case,field=field,expected=expected,actual=actual)
    require(not failures and passes == ['512'], 'missing complete state-test pass')
    modes = re.findall(r'^BOLT_COUNTER_STATE (ARM|Thumb) cases=(\d+)\r?$',text,re.M)
    require(modes == [('ARM','256'),('Thumb','256')], 'missing mode cases')
    return dict(passed=True,cases=512,mode=int(begins[0][0],16),delta=delta)


class Capture(Console):
    def __init__(self,path):
        super().__init__(str(path))
        self.data = bytearray()

    def write(self,data):
        self.data.extend(data)
        super().write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--port',default='auto')
    args = parser.parse_args()
    out = args.build.resolve()
    build = json.loads((out/'build.json').read_text(encoding='utf-8'))
    check_artifacts(out,build)
    evidence = Path(tempfile.mkdtemp(prefix='pi-verify-',dir=out))
    print('Evidence:',evidence,flush=True)
    port_name = resolve_port(args.port)
    results = {}
    for name in ('baseline','instrumented',*build['negative_cases']):
        console = Capture(evidence/(name+'.log'))
        try:
            with serial.Serial(port_name,115200,timeout=0.1,write_timeout=20) as port:
                port.reset_input_buffer()
                reboot_to_chainloader(port,console,3_000_000)
                send_image(port,console,(ROOT/'tools/pi4-serialboot-fast/kernel7l_fast.img').read_bytes(),30)
                send_image(port,console,(out/(name+'.bin')).read_bytes(),30,fast=True)
                deadline = time.monotonic()+30
                while time.monotonic() < deadline:
                    data = port.read(port.in_waiting or 1)
                    if data:
                        console.write(data)
                    text = console.data.decode('ascii','replace')
                    last_result = max(text.rfind('BOLT_COUNTER_STATE PASS'),text.rfind('BOLT_COUNTER_STATE FAIL'))
                    if last_result >= 0 and text.rfind('SBOOT?') > last_result:
                        # A full result plus watchdog return gives a reusable target.
                        # The initial loader prompt is consumed by send_image, so it
                        # cannot satisfy this condition unless rebooted afterward.
                        break
                text = console.data.decode('ascii','replace')
                last_result = max(text.rfind('BOLT_COUNTER_STATE PASS'),text.rfind('BOLT_COUNTER_STATE FAIL'))
                require(last_result >= 0 and text.rfind('SBOOT?') > last_result, name+': fixture did not return to loader')
                results[name] = check_result(text,0 if name=='baseline' else 1,build['negative_cases'].get(name))
        finally:
            if console.log:
                console.log.close()
    check_artifacts(out,build)
    result = dict(schema=1,verified=True,scope=build['scope'],port=port_name,results=results,
                  build_manifest_sha256=sha256(out/'build.json'),
                  verifier_sha256=sha256(Path(__file__)),
                  loader_sha256=sha256(ROOT/'tools/pi4-serialboot-fast/kernel7l_fast.img'),
                  log_sha256={name:sha256(evidence/(name+'.log')) for name in results})
    (evidence/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(evidence/'verification.json')


if __name__ == '__main__':
    main()
