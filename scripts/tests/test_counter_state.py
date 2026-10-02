"""The hardware state oracle must reject incomplete or contradictory results."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pi4'))
from verify_counter_state import check_result

BEGIN = 'BOLT_COUNTER_STATE BEGIN mode=0000001a delta=00000001\n'
ARM = 'BOLT_COUNTER_STATE ARM cases=256\n'
THUMB = 'BOLT_COUNTER_STATE Thumb cases=256\n'
PASS = 'BOLT_COUNTER_STATE PASS cases=512\n'
FAIL = 'BOLT_COUNTER_STATE FAIL case=00000001 field=00000015 expected=00000008 actual=00000007\n'


class StateResultTest(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(check_result(BEGIN+ARM+THUMB+PASS,1)['cases'],512)

    def test_missing_or_partial_mode(self):
        for text in (BEGIN+ARM+PASS, BEGIN+ARM+THUMB.replace('256','255')+PASS, BEGIN+ARM+THUMB):
            with self.assertRaises(ValueError): check_result(text,1)

    def test_duplicates_or_wrong_begin(self):
        for text in (BEGIN+BEGIN+ARM+THUMB+PASS,BEGIN+ARM+THUMB+PASS+PASS,
                     BEGIN.replace('00000001','00000000')+ARM+THUMB+PASS,
                     BEGIN.replace('0000001a','00000010')+ARM+THUMB+PASS):
            with self.assertRaises(ValueError): check_result(text,1)

    def test_failure_cannot_pass(self):
        for fail in (FAIL,'BOLT_COUNTER_STATE FAIL corrupt\n'):
            with self.assertRaises(ValueError): check_result(BEGIN+ARM+THUMB+PASS+fail,1)

    def test_expected_negative(self):
        self.assertTrue(check_result(BEGIN+FAIL,1,dict(case_id=1,field=21))['expected_failure'])

    def test_wrong_negative(self):
        for text in (BEGIN+FAIL.replace('00000015','00000014'),
                     BEGIN+FAIL.replace('actual=00000007','actual=00000008'),
                     BEGIN+ARM+THUMB+PASS,BEGIN+FAIL+FAIL):
            with self.assertRaises(ValueError): check_result(text,1,dict(case_id=1,field=21))


if __name__ == '__main__': unittest.main()
