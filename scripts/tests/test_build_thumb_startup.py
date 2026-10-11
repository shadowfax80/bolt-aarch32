import sys
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'pi4'))
import build_thumb_startup

class TestTrampoline(unittest.TestCase):
    def setUp(self):
        self.sections = [
            {'physical': 0, 'address': 0x1000, 'size': 0x1000, 'offset': 0x0}
        ]

    def test_trampoline_success(self):
        # We want to encode address 0x12345678
        # lower 16 bits = 0x5678 -> imm4=5, imm12=0x678
        # MOVW r12, #0x5678 -> 0xe305c678
        # upper 16 bits = 0x1234 -> imm4=1, imm12=0x234
        # MOVT r12, #0x1234 -> 0xe341c234
        # BX r12 -> 0xe12fff1c

        blob = bytearray(0x1000)
        struct.pack_into('<III', blob, 0x10, 0xe305c678, 0xe341c234, 0xe12fff1c)

        result = build_thumb_startup.trampoline(blob, self.sections, 0x1010)
        self.assertEqual(result, 0x12345678)

    def test_trampoline_invalid_movw(self):
        blob = bytearray(0x1000)
        # Invalid MOVW (changed a bit in the opcode)
        struct.pack_into('<III', blob, 0x10, 0xe305c678 ^ 0x00100000, 0xe341c234, 0xe12fff1c)

        with self.assertRaisesRegex(ValueError, 'expected ARM MOVW/MOVT/BX startup route'):
            build_thumb_startup.trampoline(blob, self.sections, 0x1010)

    def test_trampoline_invalid_movt(self):
        blob = bytearray(0x1000)
        # Invalid MOVT (changed a bit in the opcode)
        struct.pack_into('<III', blob, 0x10, 0xe305c678, 0xe341c234 ^ 0x00100000, 0xe12fff1c)

        with self.assertRaisesRegex(ValueError, 'expected ARM MOVW/MOVT/BX startup route'):
            build_thumb_startup.trampoline(blob, self.sections, 0x1010)

    def test_trampoline_invalid_bx(self):
        blob = bytearray(0x1000)
        # Invalid BX (changed destination register)
        struct.pack_into('<III', blob, 0x10, 0xe305c678, 0xe341c234, 0xe12fff10)

        with self.assertRaisesRegex(ValueError, 'expected ARM MOVW/MOVT/BX startup route'):
            build_thumb_startup.trampoline(blob, self.sections, 0x1010)

if __name__ == '__main__':
    unittest.main()
