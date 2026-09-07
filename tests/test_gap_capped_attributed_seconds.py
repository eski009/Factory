import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests/fixtures/gap_capped_attributed_seconds.py"
FIXTURE = ROOT / "tests/fixtures/gap-capped-attributed-seconds-a1c04a5.json"
REPORT = ROOT / "docs/factory/field-reports/2026-09-07-gap-capped-attributed-seconds.md"


def load_replay():
    spec = importlib.util.spec_from_file_location("gap_capped_replay", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


replay = load_replay()


def event(ts, name="spend", data=None):
    row = {"event": name, "ts": ts}
    if data is not None:
        row["data"] = data
    return row


class StageEntryMetricTest(unittest.TestCase):
    def records(self):
        return [
            event("2026-01-01T00:00:00Z", "item.created"),
            event("2026-01-01T00:00:03Z", "priority.set"),
            event("2026-01-01T00:00:08Z", "stage.advance",
                  {"from": "idea", "to": "implement"}),
            event("2026-01-01T00:00:18Z"),
            event("2026-01-01T00:00:18Z"),
            event("2026-01-01T00:00:16Z"),
            event("2026-01-01T00:00:31Z", "stage.advance",
                  {"from": "implement", "to": "review"}),
            event("2026-01-01T00:00:34Z", "stage.advance",
                  {"from": "review", "to": "implement"}),
            event("2026-01-01T00:00:38Z"),
            event("2026-01-01T00:00:45Z", "stage.advance",
                  {"from": "implement", "to": "done"}),
        ]

    def test_boundaries_close_one_entry_and_open_the_next(self):
        entries = replay.stage_entries(self.records())
        self.assertEqual([entry["stage"] for entry in entries],
                         ["idea", "implement", "review", "implement", "done"])
        self.assertEqual(entries[0]["timestamps"][0].isoformat(),
                         "2026-01-01T00:00:00+00:00")
        self.assertEqual(entries[0]["timestamps"][-1],
                         entries[1]["timestamps"][0])
        self.assertEqual(entries[1]["timestamps"][-1],
                         entries[2]["timestamps"][0])

    def test_re_entries_remain_separate_and_item_uses_the_maximum(self):
        entries = replay.stage_entries(self.records())
        implement = [entry for entry in entries if entry["stage"] == "implement"]
        self.assertEqual(len(implement), 2)
        self.assertEqual([replay.entry_score(entry, 6) for entry in implement],
                         [12, 10])
        self.assertEqual(replay.item_score(entries, 6), 12)
        self.assertNotEqual(replay.item_score(entries, 6), 22)

    def test_gap_formula_caps_positive_and_clamps_zero_and_negative(self):
        entries = replay.stage_entries(self.records())
        first = [entry for entry in entries if entry["stage"] == "implement"][0]
        self.assertEqual(replay.entry_gaps(first), [10, 0, -2, 15])
        self.assertEqual(replay.entry_score(first, 6), 12)
        self.assertEqual(replay.entry_score(first, 99), 25)

    def test_one_event_entry_scores_zero(self):
        entries = replay.stage_entries(self.records())
        self.assertEqual(entries[-1]["stage"], "done")
        self.assertEqual(replay.entry_score(entries[-1], 10), 0)

    def test_cap_must_be_a_positive_integer(self):
        entry = replay.stage_entries(self.records())[0]
        for bad in (0, -1, 1.5, True):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError,
                                            "CAP must be a positive integer"):
                    replay.entry_score(entry, bad)

    def test_threshold_is_inclusive_and_preserves_manifest_order(self):
        scores = {"a": 9, "b": 10, "c": 11}
        self.assertEqual(replay.parked_ids(("c", "a", "b"), scores, 10),
                         ["c", "b"])
        self.assertEqual(replay.parked_ids(("a", "b", "c"), scores, 12), [])

    def test_source_order_is_not_timestamp_sorted(self):
        first = [entry for entry in replay.stage_entries(self.records())
                 if entry["stage"] == "implement"][0]
        self.assertEqual(replay.entry_gaps(first)[2], -2)

    def test_missing_created_event_is_refused(self):
        with self.assertRaisesRegex(replay.EvidenceError,
                                    "exactly one item.created"):
            replay.stage_entries([event("2026-01-01T00:00:00Z")])
