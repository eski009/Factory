import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory


class CouncilCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        self.run_cli("init")

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", self.repo, *args])
        return code, out.getvalue(), err.getvalue()

    def file_bid(self):
        return self.run_cli("bid", "ui-taste", "spacing", "Cards misaligned",
                            "--evidence", "src/cards.css", "--surface",
                            "brain/design-system.md", "--severity", "medium")

    def test_bid_prints_id(self):
        code, out, _ = self.file_bid()
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "bid-0001")

    def test_bid_business_refusal_exit_2(self):
        code, _, err = self.run_cli("bid", "intern", "t", "c", "--evidence", "e",
                                    "--surface", "s", "--severity", "low")
        self.assertEqual(code, 2)
        self.assertIn("intern", err)

    def test_judge_accept_and_reputation(self):
        self.file_bid()
        code, out, _ = self.run_cli("judge", "bid-0001", "accept", "--reason", "ok",
                                    "--surface", "brain/design-system.md",
                                    "--anchor", "## Spacing")
        self.assertEqual(code, 0)
        self.assertIn("bid-0001 -> accept", out)
        code, out, _ = self.run_cli("reputation", "--json")
        self.assertEqual(json.loads(out), {"ui-taste/spacing": 0.05})

    def test_judge_missing_anchor_exit_2(self):
        self.file_bid()
        code, _, err = self.run_cli("judge", "bid-0001", "accept", "--reason", "ok")
        self.assertEqual(code, 2)
        self.assertIn("anchor", err)

    def test_health_command(self):
        code, out, _ = self.run_cli("health")
        self.assertEqual(code, 0)
        self.assertIn("recommendation: ok", out)
        self.assertTrue(Path(self.repo, ".factory/memory-health.json").exists())

    def test_prune_command(self):
        role = Path(self.repo, "docs/factory/council/customer.md")
        role.write_text(role.read_text() + "- d\n- d\n", encoding="utf-8")
        code, out, _ = self.run_cli("prune", "customer")
        self.assertEqual(code, 0)
        self.assertIn("archived: 1", out)
        self.assertIn("- d\n- d", role.read_text())
        code, out, _ = self.run_cli("prune", "customer", "--apply")
        self.assertEqual(code, 0)
        self.assertNotIn("- d\n- d", role.read_text())

    def test_prune_unknown_role_exit_2(self):
        code, _, _ = self.run_cli("prune", "intern")
        self.assertEqual(code, 2)

    def judge_first_bid(self):
        self.file_bid()
        self.run_cli("judge", "bid-0001", "accept", "--reason", "ok",
                     "--surface", "brain/design-system.md",
                     "--anchor", "## Spacing")

    def test_reputation_warns_on_corrupt_ledger_line(self):
        self.judge_first_bid()
        rep = Path(self.repo, ".factory/ledgers/reputation.jsonl")
        with rep.open("a", encoding="utf-8") as f:
            f.write('{"agent": "ui-taste", "delta": \n')
        code, out, err = self.run_cli("reputation")
        self.assertEqual(code, 0)
        self.assertIn("ui-taste/spacing", out)
        self.assertIn("+0.05", out)
        self.assertEqual(
            err.strip(),
            "ledgers/reputation.jsonl: 1 corrupt lines skipped "
            "(run factory validate)")

    def test_reputation_clean_ledger_empty_stderr(self):
        self.judge_first_bid()
        code, out, err = self.run_cli("reputation")
        self.assertEqual(code, 0)
        self.assertIn("ui-taste/spacing", out)
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
