import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import council, initrepo


class CouncilTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def bid(self, **kw):
        args = dict(agent="ui-taste", topic="interaction", claim="Buttons inconsistent",
                    evidence=["docs/factory/brain/design-system.md"],
                    surface="brain/design-system.md", severity="medium")
        args.update(kw)
        return council.file_bid(self.repo, **args)


class TestLedgerPlumbing(CouncilTest):
    def test_read_empty_ledger(self):
        self.assertEqual(council.read_ledger(self.repo, "bids"), [])

    def test_append_and_read_sorted_keys(self):
        council.append_ledger(self.repo, "bids", {"b": 1, "a": 2})
        line = (self.repo / ".factory/ledgers/bids.jsonl").read_text().strip()
        self.assertEqual(line, json.dumps({"a": 2, "b": 1}, sort_keys=True))

    def test_next_ledger_id_increments(self):
        self.assertEqual(council.next_ledger_id(self.repo, "bids", "bid"), "bid-0001")
        self.bid()
        self.assertEqual(council.next_ledger_id(self.repo, "bids", "bid"), "bid-0002")


class TestFileBid(CouncilTest):
    def test_valid_bid_appended(self):
        bid = self.bid()
        self.assertEqual(bid["id"], "bid-0001")
        self.assertEqual(bid["ts"], "2026-07-03T12:00:00Z")
        self.assertEqual(len(council.read_ledger(self.repo, "bids")), 1)

    def test_unknown_agent_refused(self):
        with self.assertRaises(council.CouncilError):
            self.bid(agent="intern")
        self.assertEqual(council.read_ledger(self.repo, "bids"), [])

    def test_empty_evidence_refused(self):
        with self.assertRaises(council.CouncilError):
            self.bid(evidence=[])

    def test_bad_severity_refused(self):
        with self.assertRaises(council.CouncilError):
            self.bid(severity="catastrophic")

    def test_item_defaults_empty(self):
        self.assertEqual(self.bid()["item"], "")


if __name__ == "__main__":
    unittest.main()
