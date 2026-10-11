import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pi4'))
from build_thumb_startup import address_offset

class AddressOffsetTests(unittest.TestCase):
    def test_valid_address(self):
        sections = [
            {'name': '.text', 'physical': 0x8000, 'address': 0x8000, 'size': 0x1000, 'offset': 0x10000},
            {'name': '.data', 'physical': 0x9000, 'address': 0x9000, 'size': 0x100, 'offset': 0x11000}
        ]

        # Test start of section
        self.assertEqual(address_offset(sections, 0x8000), 0x10000)

        # Test middle of section
        self.assertEqual(address_offset(sections, 0x8010), 0x10010)

        # Test exact end of section with size=4
        self.assertEqual(address_offset(sections, 0x8ffc, size=4), 0x10ffc)

        # Test different section
        self.assertEqual(address_offset(sections, 0x9004), 0x11004)

    def test_unloaded_section(self):
        # Section missing 'physical' key
        sections = [
            {'name': '.bss', 'address': 0xA000, 'size': 0x1000, 'offset': 0x12000}
        ]
        with self.assertRaisesRegex(ValueError, 'ambiguous/unloaded address'):
            address_offset(sections, 0xA000)

    def test_address_out_of_bounds(self):
        sections = [
            {'name': '.text', 'physical': 0x8000, 'address': 0x8000, 'size': 0x1000, 'offset': 0x10000}
        ]
        # Address too low
        with self.assertRaisesRegex(ValueError, 'ambiguous/unloaded address'):
            address_offset(sections, 0x7fff)

        # Address too high
        with self.assertRaisesRegex(ValueError, 'ambiguous/unloaded address'):
            address_offset(sections, 0x9000)

    def test_size_exceeds_bounds(self):
        sections = [
            {'name': '.text', 'physical': 0x8000, 'address': 0x8000, 'size': 0x1000, 'offset': 0x10000}
        ]
        # Address is within bounds but size pushes it out
        with self.assertRaisesRegex(ValueError, 'ambiguous/unloaded address'):
            address_offset(sections, 0x8ffc, size=8)

    def test_ambiguous_address(self):
        sections = [
            {'name': '.text', 'physical': 0x8000, 'address': 0x8000, 'size': 0x1000, 'offset': 0x10000},
            {'name': '.text2', 'physical': 0x8000, 'address': 0x8000, 'size': 0x1000, 'offset': 0x20000}
        ]
        with self.assertRaisesRegex(ValueError, 'ambiguous/unloaded address'):
            address_offset(sections, 0x8000)

if __name__ == '__main__':
    unittest.main()
