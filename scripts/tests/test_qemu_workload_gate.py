"""Complete results, child status, timeout and final cleanup must agree."""
from pathlib import Path
import os,sys,tempfile,unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qemu_workload_gate as gate


def complete():
    return 'bolt_bench: running all from cmdline\nentering main console loop\n'+''.join(f'bolt_bench: {k} sink=0x00000007\n' for k in gate.EXPECTED_WORKLOADS)


class QemuGateTests(unittest.TestCase):
    def test_complete_and_prompt_prefix(self):
        self.assertEqual(len(gate.parse_boot(complete())),18)
        self.assertEqual(len(gate.parse_boot(complete().replace('bolt_bench: hot_loop sink','] bolt_bench: hot_loop sink'))),18)

    def test_banners_without_results_cannot_pass(self):
        old='bolt_bench: running all from cmdline\nentering main console loop\n'+''.join('bolt_bench: '+k+' done\n' for k in gate.EXPECTED_WORKLOADS)
        with self.assertRaises(ValueError): gate.parse_boot(old)

    def test_missing_duplicate_reordered_and_bad_results(self):
        text=complete(); lines=text.splitlines(True)
        for bad in [text+lines[2],''.join(lines[:-1]),''.join(lines[:2]+lines[2:][::-1]),text.replace('0x00000007','0x100000007'),text.replace('hot_loop sink','unexpected sink'),text.replace('hot_loop sink=0x00000007','hot_loop sink=0x00000007 trailing')]:
            with self.assertRaises(ValueError): gate.parse_boot(bad)

    def test_failure_conflicting_acc_and_start_records(self):
        text=complete()
        for bad in [text+'bolt_bench: hot_loop FAIL bad\n',text+'bolt_bench: composite acc=0x8\n',text+'bolt_bench: running all from cmdline\n',text+'entering main console loop\n',text+'bolt_bench: composite acc=0x7\nbolt_bench: composite acc=0x7\n']:
            with self.assertRaises(ValueError): gate.parse_boot(bad)

    def test_guest_crash_rejects_even_after_complete_results(self):
        for failure in ('undefined abort, halting','CRASH: software panic','prefetch abort','data abort','unhandled exception'):
            with self.subTest(failure=failure),self.assertRaisesRegex(ValueError,'fatal guest'):
                gate.parse_boot(complete()+failure+'\n')

    @unittest.skipIf(os.name=='nt','process ownership is a WSL/Linux contract')
    def test_guest_crash_rejects_without_waiting_for_deadline(self):
        with tempfile.TemporaryDirectory() as d:
            log=Path(d)/'serial.log'
            cmd=[getattr(sys,'_base_executable',sys.executable),'-c','import time; print("undefined abort, halting",flush=True); time.sleep(30)']
            with self.assertRaisesRegex(ValueError,'fatal guest'): gate.boot(cmd,log,3)
            self.assertIn('undefined abort',log.read_text())

    @unittest.skipIf(os.name=='nt','process ownership is a WSL/Linux contract')
    def test_successful_live_child_is_deliberately_stopped(self):
        with tempfile.TemporaryDirectory() as d:
            log=Path(d)/'serial.log'
            cmd=[getattr(sys,"_base_executable",sys.executable),'-c',f'import time; print({complete()!r},flush=True); time.sleep(30)']
            result=gate.boot(cmd,log,3)
            self.assertEqual(result['stop'],'completed-then-stopped')
            self.assertEqual(len(result['results']),18)

    @unittest.skipIf(os.name=='nt','process ownership is a WSL/Linux contract')
    def test_child_error_rejects_even_with_complete_output(self):
        with tempfile.TemporaryDirectory() as d:
            log=Path(d)/'serial.log'
            cmd=[getattr(sys,"_base_executable",sys.executable),'-c',f'import sys; print({complete()!r},flush=True); sys.exit(17)']
            with self.assertRaises(ValueError): gate.boot(cmd,log,3)
            self.assertIn('sink=',log.read_text())

    @unittest.skipIf(os.name=='nt','process ownership is a WSL/Linux contract')
    def test_timeout_preserves_partial_output(self):
        with tempfile.TemporaryDirectory() as d:
            log=Path(d)/'serial.log'
            cmd=[getattr(sys,"_base_executable",sys.executable),'-c','import time; print("bolt_bench: hot_loop done",flush=True); time.sleep(30)']
            with self.assertRaisesRegex(ValueError,'deadline'): gate.boot(cmd,log,.5)
            self.assertIn('hot_loop done',log.read_text())


if __name__=='__main__': unittest.main()
