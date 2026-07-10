import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import logs


class TestLogs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_append_and_read(self):
        logs.append_event(self.repo, "0001-x", "item.created")
        logs.append_event(self.repo, "0001-x", "review.rejected", {"round": 1})
        events = logs.read_events(self.repo, "0001-x")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event"], "item.created")
        self.assertEqual(events[0]["ts"], "2026-07-03T12:00:00Z")
        self.assertEqual(events[1]["data"], {"round": 1})

    def test_lines_have_sorted_keys(self):
        logs.append_event(self.repo, "0001-x", "e", {"b": 1, "a": 2})
        line = (self.repo / ".factory/items/0001-x/log.jsonl").read_text().strip()
        self.assertEqual(line, json.dumps(json.loads(line), sort_keys=True))

    def test_read_missing_returns_empty(self):
        self.assertEqual(logs.read_events(self.repo, "0009-none"), [])

    def test_count_events(self):
        for _ in range(3):
            logs.append_event(self.repo, "0001-x", "review.rejected")
        self.assertEqual(logs.count_events(self.repo, "0001-x", "review.rejected"), 3)
        self.assertEqual(logs.count_events(self.repo, "0001-x", "other"), 0)

    def test_now_stamp_env_override(self):
        self.assertEqual(logs.now_stamp(), "2026-07-03T12:00:00Z")

    def test_empty_data_dict_is_recorded(self):
        entry = logs.append_event(self.repo, "0001-x", "e", {})
        self.assertIn("data", entry)
        self.assertEqual(entry["data"], {})
        line = (self.repo / ".factory/items/0001-x/log.jsonl").read_text().strip()
        self.assertEqual(json.loads(line)["data"], {})


class TestTolerantRead(unittest.TestCase):
    """Item spec 0007 §1: corrupt lines are skipped at this one boundary."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def append_raw(self, line):
        path = self.repo / ".factory/items/0001-x/log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def corrupt_fixture(self):
        # 3 valid events interleaved with the 3 corrupt shapes (AC 1):
        # unparseable JSON, a JSON array (non-dict), a dict missing "event".
        logs.append_event(self.repo, "0001-x", "item.created")
        self.append_raw('{"event": "stage.advance", "ts":')
        logs.append_event(self.repo, "0001-x", "review.approved")
        self.append_raw('[1, 2, 3]')
        self.append_raw('{"ts": "2026-07-03T12:00:00Z"}')
        logs.append_event(self.repo, "0001-x", "verify.green")

    def test_read_events_with_stats_skips_and_counts(self):
        self.corrupt_fixture()
        events, skipped = logs.read_events_with_stats(self.repo, "0001-x")
        self.assertEqual([e["event"] for e in events],
                         ["item.created", "review.approved", "verify.green"])
        self.assertEqual(skipped, 3)

    def test_read_events_with_stats_missing_file(self):
        self.assertEqual(
            logs.read_events_with_stats(self.repo, "0009-none"), ([], 0))

    def test_dict_missing_ts_is_corrupt(self):
        self.append_raw('{"event": "review.approved"}')
        events, skipped = logs.read_events_with_stats(self.repo, "0001-x")
        self.assertEqual(events, [])
        self.assertEqual(skipped, 1)

    def test_read_events_tolerant_and_missing_file_empty(self):
        self.corrupt_fixture()
        events = logs.read_events(self.repo, "0001-x")
        self.assertEqual([e["event"] for e in events],
                         ["item.created", "review.approved", "verify.green"])
        self.assertEqual(logs.read_events(self.repo, "0009-none"), [])

    def test_count_events_ignores_corrupt_lines(self):
        logs.append_event(self.repo, "0001-x", "review.rejected")
        logs.append_event(self.repo, "0001-x", "review.rejected")
        self.append_raw('{"event": "review.rejected", "ts": oops')
        self.append_raw('"review.rejected"')
        self.assertEqual(
            logs.count_events(self.repo, "0001-x", "review.rejected"), 2)

    def test_clean_log_reports_zero_skipped(self):
        logs.append_event(self.repo, "0001-x", "item.created")
        events, skipped = logs.read_events_with_stats(self.repo, "0001-x")
        self.assertEqual(len(events), 1)
        self.assertEqual(skipped, 0)


if __name__ == "__main__":
    unittest.main()
