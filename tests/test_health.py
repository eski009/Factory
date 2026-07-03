import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import council, health, initrepo


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def role_path(self, role):
        return self.repo / "docs/factory/council" / f"{role}.md"

    def test_clean_tree_recommends_ok(self):
        report = health.compute_health(self.repo)
        self.assertEqual(report["recommendation"], "ok")
        self.assertEqual(report["reasons"], [])
        self.assertIn("product", report["roles"])
        self.assertEqual(len(report["roles"]), 6)

    def test_duplicate_claims_counted_and_trigger_prune(self):
        text = self.role_path("customer").read_text() + \
            "- users hate modals\n- users hate modals\n- users hate modals\n"
        self.role_path("customer").write_text(text, encoding="utf-8")
        report = health.compute_health(self.repo)
        self.assertEqual(report["roles"]["customer"]["duplicate_claims"], 2)
        self.assertEqual(report["recommendation"], "ok")
        text += "- users hate modals\n"
        self.role_path("customer").write_text(text, encoding="utf-8")
        report = health.compute_health(self.repo)
        self.assertEqual(report["recommendation"], "prune")
        self.assertTrue(any("duplicate" in r for r in report["reasons"]))

    def test_oversized_role_file_triggers_prune(self):
        self.role_path("product").write_text("x\n" * 201, encoding="utf-8")
        report = health.compute_health(self.repo)
        self.assertEqual(report["recommendation"], "prune")
        self.assertTrue(any("product" in r for r in report["reasons"]))

    def test_unjudged_bids_counted(self):
        for i in range(3):
            council.file_bid(self.repo, agent="product", topic="t",
                             claim=f"claim {i}", evidence=["e"],
                             surface="brain/vision.md", severity="low")
        council.record_judgement(self.repo, "bid-0001", "defer", "later")
        report = health.compute_health(self.repo)
        self.assertEqual(report["ledgers"]["bids"], 3)
        self.assertEqual(report["ledgers"]["judged"], 1)
        self.assertEqual(report["ledgers"]["unjudged"], 2)
        self.assertEqual(report["ledgers"]["deferred"], 1)

    def test_write_health_deterministic(self):
        path = health.write_health(self.repo)
        self.assertEqual(path, self.repo / ".factory/memory-health.json")
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        data = json.loads(text)
        self.assertEqual(data["ts"], "2026-07-03T12:00:00Z")


if __name__ == "__main__":
    unittest.main()
