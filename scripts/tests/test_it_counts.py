from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pi4'))
from verify_it_counts import check_groups,check_result,check_reset_fault,check_contract

BEGIN='BOLT_IT_COUNTS BEGIN instrumented=00000001 counters=00000051\n'
PASS='BOLT_IT_COUNTS PASS cases=300\n'
GROUP='''00010000 <it_tt>:
 10000: bf04       itt eq
 10002: f101 0101  addeq.w r1, r1, #0x1
 10006: f101 0102  addeq.w r1, r1, #0x2
 1000a: 4770       bx lr
'''

class ITCountsTest(unittest.TestCase):
    def test_operating_contract(self):
        line='BOLT_IT_COUNTS CONTRACT cpsr=000001da mpidr=80000000 sp=007fff80\n'
        self.assertEqual(check_contract(line)['cpsr']&31,0x1a)
        for bad in (line.replace('000001da','000001d0'),line.replace('000001da','0000011a'),
                    line.replace('80000000','80000001'),line.replace('007fff80','007fff84'),line+line,''):
            with self.assertRaises(ValueError):check_contract(bad)

    def test_reset_fault_expected_failure(self):
        text='BOLT_IT_COUNTS BEGIN instrumented=00000001 counters=00000055\nBOLT_IT_COUNTS FAIL case=00000000 seed=00000000 field=000007d0 expected=00000000 actual=12345678\n'
        self.assertTrue(check_reset_fault(text,85)['fault_detected'])
        with self.assertRaises(ValueError):check_reset_fault(text.replace('12345678','00000001'),85)
        with self.assertRaises(ValueError):check_reset_fault(text+PASS,85)

    def test_runtime_reset_marker(self):
        text='BOLT_IT_COUNTS BEGIN instrumented=00000001 counters=00000055\r\nBOLT_IT_COUNTS RESET runtime=00000001\r\nBOLT_IT_COUNTS PASS cases=372\r\n'
        self.assertTrue(check_result(text,1,85,372,True)['runtime_clear_checked'])
        with self.assertRaises(ValueError):check_result(text.replace('RESET runtime=00000001','RESET runtime=00000000'),1,85,372,True)
        with self.assertRaises(ValueError):check_result(text.replace('BOLT_IT_COUNTS RESET runtime=00000001\r\n',''),1,85,372,True)

    def test_nested_completion_requires_full_matrix(self):
        text='BOLT_IT_COUNTS BEGIN instrumented=00000001 counters=00000055\r\nBOLT_IT_COUNTS PASS cases=372\r\n'
        self.assertEqual(check_result(text,1,85,372)['cases'],372)
        with self.assertRaises(ValueError):check_result(text,1,85,300)
        with self.assertRaises(ValueError):check_result(text.replace('372','369'),1,85,372)

    def test_complete(self):
        self.assertEqual(check_result(BEGIN+PASS,1,81)['cases'],300)

    def test_partial_conflicting_and_wrong_begin(self):
        for text in (BEGIN,BEGIN+PASS.replace('300','299'),BEGIN+PASS+PASS,BEGIN+PASS+'BOLT_IT_COUNTS FAIL broken\n',
                     BEGIN.replace('00000051','00000050')+PASS,BEGIN+BEGIN+PASS):
            with self.assertRaises(ValueError):check_result(text,1,81)

    def test_complete_group(self):
        check_groups(GROUP,['it_tt'])

    def test_probe_inside_it(self):
        with self.assertRaises(ValueError):check_groups(GROUP.replace('addeq.w r1, r1, #0x2','subeq sp, #0x10'),['it_tt'])

    def test_short_or_wrong_predicate(self):
        for text in (GROUP.replace(' 10006: f101 0102  addeq.w r1, r1, #0x2\n',''),GROUP.replace('addeq.w r1, r1, #0x2','addne.w r1, r1, #0x2')):
            with self.assertRaises(ValueError):check_groups(text,['it_tt'])

if __name__=='__main__':unittest.main()
