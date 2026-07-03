import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import council, initrepo


class JudgementTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        self.bid = council.file_bid(
            self.repo, agent="architecture", topic="boundaries",
            claim="Split module", evidence=["src/big.py"],
            surface="brain/decisions.md", severity="high")

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()


class TestRecordJudgement(JudgementTest):
    def test_accept_requires_surface_and_anchor(self):
        with self.assertRaises(council.CouncilError):
            council.record_judgement(self.repo, "bid-0001", "accept", "good find")

    def test_accept_appends_judgement_and_reputation(self):
        jdg, rep = council.record_judgement(
            self.repo, "bid-0001", "accept", "good find",
            surface="brain/decisions.md", anchor="## Module boundaries")
        self.assertEqual(jdg["id"], "jdg-0001")
        self.assertEqual(rep["delta"], 0.05)
        self.assertEqual(rep["agent"], "architecture")
        self.assertEqual(rep["topic"], "boundaries")
        self.assertEqual(rep["judgement"], "jdg-0001")
        self.assertEqual(len(council.read_ledger(self.repo, "judgements")), 1)
        self.assertEqual(len(council.read_ledger(self.repo, "reputation")), 1)

    def test_reject_wolf_tax(self):
        _, rep = council.record_judgement(self.repo, "bid-0001", "reject", "no evidence")
        self.assertEqual(rep["delta"], -0.10)

    def test_downgrade_overclaim_tax(self):
        _, rep = council.record_judgement(self.repo, "bid-0001", "downgrade", "overstated")
        self.assertEqual(rep["delta"], -0.05)

    def test_defer_neutral(self):
        _, rep = council.record_judgement(self.repo, "bid-0001", "defer", "needs data")
        self.assertEqual(rep["delta"], 0.0)

    def test_unknown_bid_refused(self):
        with self.assertRaises(council.CouncilError):
            council.record_judgement(self.repo, "bid-0999", "reject", "what bid")

    def test_double_judgement_refused(self):
        council.record_judgement(self.repo, "bid-0001", "reject", "no")
        with self.assertRaises(council.CouncilError):
            council.record_judgement(self.repo, "bid-0001", "accept", "changed my mind",
                                     surface="brain/decisions.md", anchor="## X")

    def test_bad_decision_refused(self):
        with self.assertRaises(council.CouncilError):
            council.record_judgement(self.repo, "bid-0001", "maybe", "hmm")


class TestReputationAndAuthorization(JudgementTest):
    def test_reputation_table_sums_per_agent_topic(self):
        council.record_judgement(self.repo, "bid-0001", "accept", "ok",
                                 surface="brain/decisions.md", anchor="## A")
        council.file_bid(self.repo, agent="architecture", topic="boundaries",
                         claim="Another", evidence=["x"], surface="brain/decisions.md",
                         severity="low")
        council.record_judgement(self.repo, "bid-0002", "reject", "no")
        table = council.reputation_table(self.repo)
        self.assertEqual(table["architecture/boundaries"], -0.05)

    def test_is_change_authorized(self):
        self.assertFalse(council.is_change_authorized(
            self.repo, "bid-0001", "brain/decisions.md"))
        council.record_judgement(self.repo, "bid-0001", "accept", "ok",
                                 surface="brain/decisions.md", anchor="## A")
        self.assertTrue(council.is_change_authorized(
            self.repo, "bid-0001", "brain/decisions.md"))
        self.assertFalse(council.is_change_authorized(
            self.repo, "bid-0001", "brain/vision.md"))

    def test_reject_never_authorizes(self):
        council.record_judgement(self.repo, "bid-0001", "reject", "no")
        self.assertFalse(council.is_change_authorized(
            self.repo, "bid-0001", "brain/decisions.md"))


if __name__ == "__main__":
    unittest.main()
