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


class FailClosedCliTest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                              capture_output=True, text=True)

    def test_corrupt_fixture_json_preserves_accepted_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad = root / "bad.json"
            bad.write_text("{broken", encoding="utf-8")
            output = root / "report.md"
            output.write_bytes(b"accepted report\n")
            result = self.run_cli("replay", "--fixture", bad,
                                  "--output", output)
            self.assertEqual(result.returncode, 2)
            self.assertIn("cannot read frozen fixture", result.stderr)
            self.assertEqual(output.read_bytes(), b"accepted report\n")

    def test_missing_required_record_with_recomputed_digest_still_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            document = json.loads(FIXTURE.read_text(encoding="utf-8"))
            frozen = document["items"][replay.ITEM_0015]
            frozen["records"] = [row for row in frozen["records"]
                                 if row["event"] != "item.created"]
            frozen["record_count"] = len(frozen["records"])
            frozen["disclosure"]["parseable_timestamped_records"] = len(frozen["records"])
            frozen["records_sha256"] = replay.records_digest(frozen["records"])
            bad = root / "missing-record.json"
            bad.write_text(json.dumps(document), encoding="utf-8")
            output = root / "report.md"
            output.write_bytes(b"accepted report\n")
            result = self.run_cli("replay", "--fixture", bad,
                                  "--output", output)
            self.assertEqual(result.returncode, 2)
            self.assertIn("exactly one item.created", result.stderr)
            self.assertEqual(output.read_bytes(), b"accepted report\n")

    def test_changed_manifest_refuses_instead_of_changing_denominator(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "changed.json"
            document = json.loads(FIXTURE.read_text(encoding="utf-8"))
            document["cohorts"]["primary"]["ids"].append("9999-future-done")
            bad.write_text(json.dumps(document), encoding="utf-8")
            result = self.run_cli("replay", "--fixture", bad)
            self.assertEqual(result.returncode, 2)
            self.assertIn("cohort manifests or labels", result.stderr)
            self.assertEqual(result.stdout, "")

    def test_verify_detects_report_drift(self):
        with tempfile.TemporaryDirectory() as td:
            bad_report = Path(td) / "report.md"
            bad_report.write_text("misleading replacement\n", encoding="utf-8")
            result = self.run_cli("verify", "--fixture", FIXTURE,
                                  "--report", bad_report)
            self.assertEqual(result.returncode, 2)
            self.assertIn("accepted report differs from replay", result.stderr)

    def test_replay_succeeds_without_factory_directory_or_network(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            copied_fixture = root / FIXTURE.name
            copied_fixture.write_bytes(FIXTURE.read_bytes())
            first = self.run_cli("replay", "--fixture", copied_fixture)
            second = self.run_cli("replay", "--fixture", copied_fixture)
            self.assertEqual(first.returncode, 0)
            self.assertEqual(first.stdout, second.stdout)
            self.assertNotIn(str(ROOT / ".factory"), first.stdout)



class AcceptedSweepTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = replay.load_fixture(FIXTURE)
        cls.profiles = replay.build_profiles(cls.document)

    def test_first_implement_comparison_facts_are_exact(self):
        facts = replay.comparison_facts(self.document)
        self.assertEqual(facts["0015"], {
            "adjacent_gaps": 11, "positive_gaps": 10,
            "uncapped_seconds": 10046, "cap_1_score": 10,
        })
        self.assertEqual(facts["0016"], {
            "adjacent_gaps": 15, "positive_gaps": 13,
            "uncapped_seconds": 9499, "cap_1_score": 13,
        })

    def test_every_integer_cap_has_the_exact_separator_state(self):
        for cap in range(1, 43728):
            row = replay.sweep_row(self.profiles, cap)
            with self.subTest(cap=cap):
                if cap <= 6204:
                    self.assertEqual(row["threshold"], row["score_0015"] + 1)
                    self.assertGreater(row["score_0016"], row["score_0015"])
                elif cap == 6205:
                    self.assertEqual((row["score_0015"], row["score_0016"]),
                                     (9499, 9499))
                    self.assertIsNone(row["threshold"])
                else:
                    self.assertGreater(row["score_0015"], row["score_0016"])
                    self.assertIsNone(row["threshold"])

    def test_representative_caps_are_exact_and_stable(self):
        analysis = replay.analyse(self.document)
        self.assertEqual([row["cap"] for row in analysis["representative_rows"]],
                         [1, 30, 60, 120, 300, 600, 900, 1800, 3600,
                          5000, 6000, 6204, 6205, 7200])

    def test_through_1800_only_0016_is_parked_in_both_cohorts(self):
        for cap in (1, 30, 60, 120, 300, 600, 900, 1800):
            row = replay.sweep_row(self.profiles, cap)
            self.assertEqual(row["primary_parked"], [replay.ITEM_0016])
            self.assertEqual(row["secondary_parked"], [replay.ITEM_0016])

    def test_6204_has_exact_independent_parked_sets(self):
        row = replay.sweep_row(self.profiles, 6204)
        self.assertEqual(row["threshold"], 9499)
        self.assertEqual(row["primary_parked"], [
            "0002-claude-design-mcp-as-the-single-source-o",
            "0003-interactive-decision-pages-clickable-cho",
            replay.ITEM_0016,
        ])
        self.assertEqual(row["secondary_parked"], [
            "0002-claude-design-mcp-as-the-single-source-o",
            "0003-interactive-decision-pages-clickable-cho",
            replay.ITEM_0016,
            "0031-the-cost-packet-s-decision-copy-is-churn",
        ])

    def test_no_separator_has_no_threshold_and_no_parked_set(self):
        for cap in (6205, 7200):
            row = replay.sweep_row(self.profiles, cap)
            self.assertIsNone(row["threshold"])
            self.assertIsNone(row["primary_parked"])
            self.assertIsNone(row["secondary_parked"])


class ReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = replay.load_fixture(FIXTURE)
        cls.rendered = replay.render_report(cls.document)

    def test_headline_conclusion_and_limits_are_plain(self):
        required = (
            "# Within-corpus separation exists; no runaway threshold is calibrated or recommended",
            "Primary cohort: n=13",
            "Secondary snapshot: n=16@a1c04a5",
            "the difference is 547 seconds",
            "0016 completed and shipped",
            "Neither cohort contains a labelled positive runaway",
            "materially event-cadence-driven",
            "external ParkSnap run is absent and not reconstructed",
            "Conclusion: within-corpus separation exists; no runaway threshold is calibrated or recommended.",
        )
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, " ".join(self.rendered.split()))

    def test_report_has_separate_tables_and_exact_boundary_rows(self):
        self.assertIn("## Primary representative rows — n=13", self.rendered)
        self.assertIn("## Secondary representative rows — n=16@a1c04a5", self.rendered)
        self.assertEqual(self.rendered.count("| 6,204 | 9,498 | 9,499 | 9,499 |"), 2)
        self.assertEqual(self.rendered.count(
            "| 6,205 | 9,499 | 9,499 | none | no separating threshold |"), 2)
        self.assertEqual(self.rendered.count(
            "| 7,200 | 10,046 | 9,499 | none | no separating threshold |"), 2)

    def test_report_discloses_each_of_the_sixteen_sources(self):
        section = self.rendered.split("## Source-input disclosure", 1)[1]
        for item_id in replay.SECONDARY_IDS:
            self.assertEqual(section.count(f"| {item_id} |"), 1)
        self.assertIn("All 16 declared logs are present", section)
        self.assertTrue(all(not frozen["disclosure"][key]
                            for frozen in self.document["items"].values()
                            for key in replay.DISCLOSURE_KEYS))

    def test_replay_stdout_is_byte_identical_twice(self):
        command = [sys.executable, str(SCRIPT), "replay", "--fixture", str(FIXTURE)]
        first = subprocess.run(command, check=True, capture_output=True).stdout
        second = subprocess.run(command, check=True, capture_output=True).stdout
        self.assertEqual(first, second)
        self.assertEqual(first, self.rendered.encode("utf-8"))

    def test_checked_in_report_is_exact_generated_output(self):
        self.assertEqual(REPORT.read_bytes(), self.rendered.encode("utf-8"))



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

    def test_fractional_positive_gaps_are_not_truncated(self):
        entry = {"timestamps": [
            replay.parse_timestamp("2026-01-01T00:00:00Z"),
            replay.parse_timestamp("2026-01-01T00:00:00.8Z"),
            replay.parse_timestamp("2026-01-01T00:00:01.3Z"),
        ]}
        self.assertEqual(replay.entry_gaps(entry), [0.8, 0.5])
        self.assertEqual(replay.entry_score(entry, 6), 1.3)

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


class SourceBoundaryTest(unittest.TestCase):
    def test_reader_parses_and_hashes_one_byte_buffer(self):
        raw = ("{\"event\":\"item.created\",\"ts\":\"2026-01-01T00:00:00Z\"}\n"
               "{\"event\":\"stage.advance\",\"ts\":\"2026-01-01T00:00:01Z\","
               "\"data\":{\"from\":\"idea\",\"to\":\"done\"}}\n").encode("utf-8")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            item_dir = root / "x"
            item_dir.mkdir()
            path = item_dir / "log.jsonl"
            path.write_bytes(b"separate on-disk version")
            with mock.patch.object(Path, "read_bytes", autospec=True,
                                   return_value=raw) as read_bytes, \
                 mock.patch.object(Path, "read_text", autospec=True,
                                   side_effect=AssertionError(
                                       "reader must not use read_text")) as read_text:
                frozen = replay.read_source_item(root, "x")
        read_bytes.assert_called_once_with(path)
        read_text.assert_not_called()
        self.assertEqual([row["event"] for row in frozen["records"]],
                         ["item.created", "stage.advance"])
        self.assertEqual(frozen["source_log_sha256"],
                         replay.hashlib.sha256(raw).hexdigest())

    def test_manifests_are_exact_immutable_tuples(self):
        self.assertEqual(replay.PRIMARY_IDS, (
            "0001-focus-group-research-structured-intervie",
            "0002-claude-design-mcp-as-the-single-source-o",
            "0003-interactive-decision-pages-clickable-cho",
            "0004-per-item-cost-meter-measure-and-report-t",
            "0007-tolerant-log-reading-corrupt-log-jsonl-l",
            "0008-design-mirror-refinements-pull-bid-diver",
            "0009-finish-the-never-bricks-promise-crash-pr",
            "0010-factory-bug-command-understand-replicate",
            "0012-adapt-the-design-options-decision-block-",
            "0013-assure-attribution-gate-only-on-regressi",
            "0015-approach-rejected-a-redesign-loop-back-t",
            "0016-cost-circuit-breaker-on-engine-authorita",
            "0025-round-scope-all-rework-gates-implement-c",
        ))
        self.assertEqual(replay.SECONDARY_IDS,
                         replay.PRIMARY_IDS + (
                             "0027-packet-respond-falls-through-to-factory-",
                             "0031-the-cost-packet-s-decision-copy-is-churn",
                             "0033-bugs-run-less-pipeline-make-stage-member",
                         ))
        self.assertEqual(len(replay.PRIMARY_IDS), 13)
        self.assertEqual(len(replay.SECONDARY_IDS), 16)

    def test_reader_counts_every_exclusion_class_without_inventing_time(self):
        with tempfile.TemporaryDirectory() as td:
            item_dir = Path(td) / "x"
            item_dir.mkdir()
            (item_dir / "log.jsonl").write_text(
                '\n'.join([
                    json.dumps(event("2026-01-01T00:00:00Z", "item.created")),
                    "",
                    "{broken",
                    json.dumps({"event": "spend"}),
                    json.dumps({"event": "spend", "ts": "yesterday"}),
                    json.dumps(event("2026-01-01T00:00:01Z")),
                    json.dumps(event("2026-01-01T00:00:02Z", "stage.advance",
                                     {"from": "idea", "to": "done"})),
                ]) + "\n", encoding="utf-8")
            frozen = replay.read_source_item(Path(td), "x")
        self.assertEqual([row["event"] for row in frozen["records"]],
                         ["item.created", "spend", "stage.advance"])
        self.assertEqual(frozen["disclosure"], {
            "present": True,
            "parseable_timestamped_records": 3,
            "blank_lines": 1,
            "corrupt_json_lines": 1,
            "missing_timestamps": 1,
            "unparseable_timestamps": 1,
        })

    def test_missing_log_is_disclosed_and_refused(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(replay.EvidenceError,
                                        "missing declared log: x"):
                replay.read_source_item(Path(td), "x")

    def test_missing_created_or_done_record_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for item_id, rows, message in (
                ("no-created", [event("2026-01-01T00:00:01Z")],
                 "exactly one item.created"),
                ("no-done", [event("2026-01-01T00:00:00Z", "item.created")],
                 "stage.advance to done"),
            ):
                path = root / item_id
                path.mkdir()
                (path / "log.jsonl").write_text(
                    "\n".join(json.dumps(row) for row in rows) + "\n",
                    encoding="utf-8")
                with self.subTest(item_id=item_id):
                    with self.assertRaisesRegex(replay.EvidenceError, message):
                        replay.read_source_item(root, item_id)

    def test_record_digest_detects_removed_frozen_record(self):
        rows = [event("2026-01-01T00:00:00Z", "item.created"),
                event("2026-01-01T00:00:01Z", "stage.advance",
                      {"from": "idea", "to": "done"})]
        digest = replay.records_digest(rows)
        self.assertNotEqual(digest, replay.records_digest(rows[:-1]))
