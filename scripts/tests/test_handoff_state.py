import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from handoff_state import read_items


class HandoffStateTests(unittest.TestCase):
    def parse(self, body):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "HANDOFF.md"
            path.write_text("## Claims (consolidated TODO)\n" + body + "\n## Coverage goal\n"
                            "## Handoff log\n| OLD | historical | P0 | Agent | Open |\n", encoding="utf-8")
            return read_items(path)

    def test_mixed_ids_reopened_deferred_and_done(self):
        items = self.parse("""### Remaining shared work
| ID | Item | Priority | Owner | Status | Notes |
|---|---|---|---|---|---|
| R11 | Decoder | P1 | — | Partial (reopened) | diagnostic |
| T3 | Deferred example | P2 | — | Deferred | user decision |
| 14 | Provenance | P1 | — | Partial | receipts |
### Done
| ID | Item | Priority | Owner | Patch / evidence |
|---|---|---|---|---|
| R8 | Liveness | P1 | Claude | 0061 |
""")
        self.assertEqual([i["number"] for i in items], ["R11", "T3", "14", "R8"])
        self.assertEqual(items[0]["status"], "Partial (reopened)")
        self.assertEqual(items[-1]["status"], "Done")
        self.assertEqual(items[-1]["remaining"], "0061")

    def test_duplicate_claim_and_done_refused(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.parse("""| ID | Item | Status |
| R1 | first | Open |
### Done
| ID | Item |
| R1 | stale duplicate |
""")

    def test_malformed_row_refused(self):
        with self.assertRaisesRegex(ValueError, "Malformed"):
            self.parse("| ID | Item | Status |\n| R1 | omitted status |")

    def test_statusless_live_table_refused(self):
        with self.assertRaisesRegex(ValueError, "Status"):
            self.parse("| ID | Item |\n| R1 | omitted status |")


if __name__ == "__main__":
    unittest.main()
