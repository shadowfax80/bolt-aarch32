"""Independent ISA and CPU-state admissions for far-call certificates."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import verify_far_interwork as gate


class FarInterworkTests(unittest.TestCase):
    def test_thumb_bl_signed_offsets(self):
        def encode(delta):
            value = delta & 0x1ffffff
            sign,i1,i2 = (value >> 24)&1,(value >> 23)&1,(value >> 22)&1
            return (0xf000 | (sign << 10) | ((value >> 12)&0x3ff),
                    0xd000 | ((1^i1^sign) << 13) | ((1^i2^sign) << 11) | ((value >> 1)&0x7ff))
        for delta in [-0x1000000,-2,0,2,0xfffffe]:
            self.assertEqual(gate.decode_thumb_bl(*encode(delta),0x2000000),0x2000004+delta)
        with self.assertRaises(ValueError):
            gate.decode_thumb_bl(0xf000,0xc000,0x1000) # BLX is not a same-mode stub call.

    def test_cpu_state_association_and_thumb_bit(self):
        text = ('Trace 0: 0x123 [00800480/00001000/00000000/00000200]\n'
                'R00=00000011 R01=00000000 R02=00000000 R03=00000000\n'
                'R12=00000000 R13=00008000 R14=00000000 R15=00001000\n'
                'PSR=80000030 N--- T usr32\n')
        state = gate.cpu_states(text)[0x1000][0]
        self.assertEqual((state['r0'],state['sp'],state['thumb']),(17,0x8000,True))
        for damaged in [text.replace('R15=00001000','R15=00001004'),
                        text.replace('T usr32','A usr32'),text.replace('PSR=80000030 N--- T usr32\n','')]:
            with self.assertRaises(ValueError):
                gate.cpu_states(damaged)

    def test_wrong_inputs_returns_and_isa_cannot_certify(self):
        witness=dict(caller=0x1000,veneer=0x1100,callee=0x2200,call=0x1080,
                     caller_isa='thumb',stub_isa='thumb',callee_isa='arm')
        def row(pc,value,thumb):
            return dict(pc=pc,r0=value,sp=0x8000,thumb=thumb)
        states={0x1000:[row(0x1000,0,True)],0x1100:[row(0x1100,n,True) for n in gate.SEEDS],
                0x2200:[row(0x2200,n,False) for n in gate.SEEDS],
                0x1084:[row(0x1084,(n+7)&0xffffffff,True) for n in gate.SEEDS]}
        gate.check_states(states,witness)
        for address,field,value in [(0x2200,'thumb',True),(0x2200,'r0',12),(0x1084,'r0',8),(0x1084,'sp',0x7ffc)]:
            original = states[address][0][field]
            states[address][0][field] = value
            with self.assertRaises(ValueError):
                gate.check_states(states,witness)
            states[address][0][field] = original


if __name__ == '__main__':
    unittest.main()
