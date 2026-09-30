import importlib.util
import pathlib
import subprocess
import tempfile
import os
import sys

repo = pathlib.Path(__file__).resolve().parents[2]
# Exercise the whole aggregate wrapper with passing/failing child gates.
with tempfile.TemporaryDirectory() as td:
 home=pathlib.Path(td); scripts=home/'bolt-aarch32/scripts'; scripts.mkdir(parents=True)
 names=['build-lk-aarch32','verify-bolt-arm32-harness','verify-bolt-arm32-milestones','verify-bolt-arm32-identity','verify-bolt-arm32-veneer','verify-bolt-workloads']
 for n in names:
  p=scripts/(n+'.sh'); p.write_text('#!/bin/sh\necho '+n+'\nexit 0\n'); p.chmod(0o755)
 env=dict(os.environ, HOME=td)
 wrapper=repo/'scripts/verify-all-wsl.sh'
 result=subprocess.run(['bash',str(wrapper)],env=env,capture_output=True,text=True)
 assert result.returncode==0, result
 (scripts/'verify-bolt-arm32-identity.sh').write_text('#!/bin/sh\nexit 7\n')
 result=subprocess.run(['bash',str(wrapper)],env=env,capture_output=True,text=True)
 assert result.returncode==1, result
 assert 'FAIL  identity' in result.stdout and 'exit 7' in result.stdout, result.stdout
 assert 'PASS  workloads' in result.stdout, result.stdout
 print('aggregate wrapper: all-pass=0; failed child=1; later gates still ran')
# Exercise comparison entry point with mocked serial observations.
sys.path.insert(0,str(repo/'scripts/pi4'))
import pi4_compare as compare
with tempfile.TemporaryDirectory() as td:
 image=pathlib.Path(td)/'image.bin'; image.write_bytes(b'fixture')
 for expected, checksum in [(0,'0x01'),(1,'0x02'),(1,'')]:
  compare.boot_and_run=lambda path,port,workload,runs: [{'cycles':10,'acc':'0x01' if path.endswith('a.bin') else checksum}]
  a=pathlib.Path(td)/'a.bin'; a.write_bytes(b'fixture')
  sys.argv=['pi4_compare','--out',str(pathlib.Path(td)/'result.csv'),'--rounds','1','--runs','1',f'a={a}',f'b={image}']
  assert compare.main()==expected
 print('Pi comparison: matching checksum=0; mismatch/missing checksum=1')
