"""Measurement association must survive missing/duplicate/reordered serial output."""
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pi4'))
import measurement_records as gate
import pgo_lab_measure as lab
import pi4_compare as compare


def frame(command='bolt_bench composite',kernels=('composite',),value=7):
    return '$ '+command+'\n'+''.join(f'bolt_bench: {k} done (10 cycles)\nbolt_bench: {k} pmu inst=20 l1i_refill=1 l1d_refill=2 br_mispred=3 taken=4\nbolt_bench: {k} acc=0x{value:x}\n' for k in kernels)


class MeasurementTests(unittest.TestCase):
    def parse(self,text,runs=1): return gate.parse_measurements(text,'bolt_bench composite',['composite'],runs)

    def test_complete_ordered_runs(self):
        rows=self.parse(frame()+frame(value=8),2)
        self.assertEqual([r['acc'] for r in rows],['0x00000007','0x00000008'])
        self.assertEqual([r['run'] for r in rows],[1,2])
        self.assertEqual(self.parse(frame().replace('\n','\r\n'))[0]['inst'],20)

    def test_missing_pmu_cannot_shift_later_run(self):
        missing='\n'.join(x for x in frame().split('\n') if ' pmu ' not in x)
        with self.assertRaises(ValueError): self.parse(missing+frame(),2)

    def test_missing_duplicate_reordered_records(self):
        lines=frame().splitlines(True)
        for bad in [lines[:2]+lines[3:],lines+lines[1:2],lines[:1]+[lines[2],lines[1],lines[3]],lines[:-1]]:
            with self.assertRaises(ValueError): self.parse(''.join(bad))

    def test_equal_global_counts_do_not_replace_frames(self):
        for text in [frame().replace('$ bolt_bench composite\n',''),frame()+frame(),frame()+frame().split('\n',1)[1],frame()+frame().replace('bolt_bench composite','bolt_bench stair',1)]:
            with self.assertRaises(ValueError): self.parse(text)

    def test_invalid_pmu_wrong_kernel_and_corrupt_line(self):
        for text in [frame().replace('pmu inst=20 l1i_refill=1 l1d_refill=2 br_mispred=3 taken=4','pmu INVALID (migrated)'),frame().replace('pmu inst=','pmu2 inst='),frame().replace('composite done','stair done'),frame().replace('acc=0x7','acc=0x7 trailing'),frame()+'bolt_bench: composite FAIL bad\n']:
            with self.assertRaises(ValueError): self.parse(text)

    def test_numeric_width_and_zero_cycles(self):
        for text in [frame().replace('(10 cycles)','(0 cycles)'),frame().replace('(10 cycles)',f'({2**64} cycles)'),frame().replace('inst=20',f'inst={2**32}'),frame().replace('0x7','0x100000000')]:
            with self.assertRaises(ValueError): self.parse(text)

    def test_optional_taken_and_checksum_normalization(self):
        row=self.parse(frame().replace(' taken=4','').replace('0x7','0x00000007'))[0]
        self.assertNotIn('taken',row); self.assertEqual(row['acc'],'0x00000007')

    def test_pgo_kernel_order_each_command(self):
        command='bolt_bench pgo_lab'; names=lab.KERNELS
        self.assertEqual(len(gate.parse_measurements(frame(command,names)*2,command,names,2)),8)
        with self.assertRaises(ValueError): gate.parse_measurements(frame(command,names[::-1]),command,names,1)

    def test_checksum_mismatch_rejects_and_missing_kernel(self):
        rows=self.parse(frame()+frame(value=8),2)
        with self.assertRaises(ValueError): gate.consistent(rows,['composite'])
        with self.assertRaises(ValueError): gate.consistent(rows,['pl_a'])

    def test_parse_failure_is_not_retried(self):
        with patch.object(compare,'capture_measurements',side_effect=ValueError('bad records')) as run:
            with self.assertRaises(ValueError): compare.boot_and_run('x','COM5','composite',2)
            self.assertEqual(run.call_count,1)

    def test_failed_child_retains_exact_image_and_log(self):
        with tempfile.TemporaryDirectory() as d:
            image=Path(d)/'input.bin'; image.write_bytes(b'original')
            fake=Path(d)/'scripts/pi4/measurement_records.py'
            with patch.object(gate,'__file__',str(fake)),patch.dict('os.environ',{},clear=True),patch.object(gate,'run_bounded',return_value=SimpleNamespace(returncode=-9,stdout=b'timed out')):
                with self.assertRaises(RuntimeError): gate.capture_measurements(image,'COM5','bolt_bench composite',['composite'],1,30,60)
            evidence=next((Path(d)/'out/pi4').glob('measure-*'))
            self.assertEqual((evidence/'serial.log').read_bytes(),b'timed out')
            self.assertEqual((evidence/'image.bin').read_bytes(),b'original')
            self.assertFalse((evidence/'measurement.json').exists())

    def test_changed_image_rejects_even_with_valid_serial_results(self):
        with tempfile.TemporaryDirectory() as d:
            image=Path(d)/'input.bin'; image.write_bytes(b'original')
            def run(cmd,timeout):
                self.assertEqual(Path(cmd[2]).read_bytes(),b'original')
                image.write_bytes(b'changed')
                return SimpleNamespace(returncode=0,stdout=frame().encode())
            with patch.object(gate,'__file__',str(Path(d)/'scripts/pi4/measurement_records.py')),patch.dict('os.environ',{},clear=True),patch.object(gate,'run_bounded',side_effect=run):
                with self.assertRaisesRegex(ValueError,'image changed'): gate.capture_measurements(image,'COM5','bolt_bench composite',['composite'],1,30,60)

    def test_lab_main_mismatch_cannot_exit_success(self):
        with tempfile.TemporaryDirectory() as d:
            image=Path(d)/'image.bin'; image.write_bytes(b'x')
            rows=[dict(kernel=k,run=1,cycles=10,inst=20,l1i_refill=1,l1d_refill=2,br_mispred=3,acc='0x00000007') for k in lab.KERNELS]
            bad=[{**r,'acc':'0x00000008'} for r in rows]
            with patch.object(sys,'argv',['lab','--out',str(Path(d)/'out.csv'),'--rounds','1','--runs','1','a='+str(image),'b='+str(image)]),patch.object(lab,'boot_and_run',side_effect=[rows,bad]):
                with self.assertRaises(ValueError): lab.main()


if __name__ == '__main__': unittest.main()
