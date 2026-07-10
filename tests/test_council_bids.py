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

    def test_next_ledger_id_does_not_reuse_id_after_delete(self):
        # I1: a count-based id would reuse bid-0001 after the first line is
        # deleted; the id must be derived from the max existing suffix.
        self.bid()
        self.bid()
        path = self.repo / ".factory/ledgers/bids.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text(lines[1] + "\n", encoding="utf-8")  # delete bid-0001's line
        self.assertEqual(council.next_ledger_id(self.repo, "bids", "bid"), "bid-0003")


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


class TestTolerantLedger(CouncilTest):
    """Item spec 0007 §4: ledger reads tolerant, ids never reissued."""

    def corrupt_line(self, text='{"id": "bid-9999", "ts": '):
        path = self.repo / ".factory/ledgers/bids.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")

    def test_read_ledger_skips_corrupt_lines(self):
        self.bid()
        self.corrupt_line()
        entries = council.read_ledger(self.repo, "bids")
        self.assertEqual([e["id"] for e in entries], ["bid-0001"])

    def test_read_ledger_with_stats_counts_skipped(self):
        self.bid()
        self.corrupt_line()
        entries, skipped = council.read_ledger_with_stats(self.repo, "bids")
        self.assertEqual(len(entries), 1)
        self.assertEqual(skipped, 1)

    def test_non_dict_ledger_line_is_corrupt(self):
        self.corrupt_line(text='["not", "a", "dict"]')
        entries, skipped = council.read_ledger_with_stats(self.repo, "bids")
        self.assertEqual(entries, [])
        self.assertEqual(skipped, 1)

    def test_read_ledger_with_stats_missing_file(self):
        self.assertEqual(
            council.read_ledger_with_stats(self.repo, "nonexistent"), ([], 0))

    def test_next_ledger_id_floors_on_raw_line_count(self):
        # bid-0001 and bid-0002 issued, then bid-0003's line is corrupted
        # in place: parsed max is 2 but 3 non-blank lines exist, so the
        # next id is bid-0004 — bid-0003 is never reissued.
        self.bid()
        self.bid()
        self.corrupt_line(text='{"id": "bid-0003", "ts": ')
        self.assertEqual(council.next_ledger_id(self.repo, "bids", "bid"),
                         "bid-0004")


if __name__ == "__main__":
    unittest.main()
