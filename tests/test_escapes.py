import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory import factory
from scripts.factory.lib import escapes, initrepo


class EscapeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-15T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_file_escape_assigns_sequential_ids(self):
        one = escapes.file_escape(self.repo, "J-001", "no next action visible",
                                  "missing-oracle")
        two = escapes.file_escape(self.repo, "J-002", "dead end after save",
                                  "missing-node")
        self.assertEqual(one["id"], "esc-0001")
        self.assertEqual(two["id"], "esc-0002")
        self.assertEqual([e["id"] for e in escapes.open_escapes(self.repo)],
                         ["esc-0001", "esc-0002"])

    def test_file_escape_rejects_bad_miss_type_and_journey(self):
        with self.assertRaises(escapes.EscapeError):
            escapes.file_escape(self.repo, "J-001", "x", "vibes")
        with self.assertRaises(escapes.EscapeError):
            escapes.file_escape(self.repo, "journey-4", "x", "missing-oracle")

    def test_promotion_closes_escape(self):
        escapes.file_escape(self.repo, "J-001", "confusing", "missing-oracle")
        entry = escapes.promote(self.repo, "esc-0001", "test:tests/test_onboarding.py")
        self.assertEqual(entry["status"], "promoted")
        self.assertEqual(escapes.open_escapes(self.repo), [])

    def test_promotion_ref_validated_and_double_promotion_refused(self):
        escapes.file_escape(self.repo, "J-001", "confusing", "missing-oracle")
        with self.assertRaises(escapes.EscapeError):
            escapes.promote(self.repo, "esc-0001", "fixed it lol")
        escapes.promote(self.repo, "esc-0001", "contract:docs/factory/journeys/contracts/J-001-x.md")
        with self.assertRaises(escapes.EscapeError):
            escapes.promote(self.repo, "esc-0001", "jdg-0001")

    def test_cli_escape_and_promote(self):
        code = factory.main(["--repo", str(self.repo), "escape", "J-001",
                             "user cannot tell what to do next",
                             "--miss-type", "missing-oracle",
                             "--item", "0017-invite-flow", "--node", "N4"])
        self.assertEqual(code, 0)
        self.assertEqual(len(escapes.open_escapes(self.repo)), 1)
        code = factory.main(["--repo", str(self.repo), "promote", "esc-0001",
                             "--via", "jdg-0004"])
        self.assertEqual(code, 0)
        self.assertEqual(escapes.open_escapes(self.repo), [])

    def test_validate_flags_bad_escape_lines(self):
        escapes.file_escape(self.repo, "J-001", "x", "missing-oracle")
        ledger = self.repo / ".factory" / "ledgers" / "escapes.jsonl"
        with ledger.open("a", encoding="utf-8") as f:
            f.write('{"id": "esc-0002", "status": "promoted"}\n')
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("escapes.jsonl" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
