from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pi4'))
from verify_it_counts import check_groups,check_result

BEGIN='BOLT_IT_COUNTS BEGIN instrumented=00000001 counters=00000051\n'
PASS='BOLT_IT_COUNTS PASS cases=300\n'
GROUP='''00010000 <it_tt>:
 10000: bf04       itt eq
 10002: f101 0101  addeq.w r1, r1, #0x1
 10006: f101 0102  addeq.w r1, r1, #0x2
 1000a: 4770       bx lr
'''

class ITCountsTest(unittest.TestCase):
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
