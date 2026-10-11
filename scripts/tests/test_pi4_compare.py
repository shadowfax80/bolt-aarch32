import sys
import unittest
from pathlib import Path

# Add the scripts/pi4 directory to sys.path so we can import pi4_compare
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pi4"))
from pi4_compare import fmt

class Pi4CompareTests(unittest.TestCase):
    def test_fmt_empty_list(self):
        """Test formatting an empty list."""
        self.assertEqual(fmt([]), "n/a")

    def test_fmt_single_value(self):
        """Test formatting a list with a single value."""
        # Output should have mean 5.0, min 5, max 5, and sd 0.0
        self.assertEqual(fmt([5.0]), f"{5.0:>13,.1f}  [5 .. 5]  sd 0.0")

    def test_fmt_multiple_values(self):
        """Test formatting a list with multiple values."""
        # Mean of [2.0, 4.0, 6.0] is 4.0
        # Min is 2, Max is 6
        # pstdev of [2.0, 4.0, 6.0] is sqrt(((2-4)^2 + (4-4)^2 + (6-4)^2)/3) = sqrt(8/3) = 1.63299...
        # Formatted sd to 1 decimal place is 1.6
        self.assertEqual(fmt([2.0, 4.0, 6.0]), f"{4.0:>13,.1f}  [2 .. 6]  sd 1.6")

if __name__ == '__main__':
    unittest.main()
