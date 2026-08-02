import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import breaker, cost, initrepo, items, logs, paths
from scripts.factory.lib.machine import GateError as GateErrorAlias

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/parksnap-2026-08-02/log.jsonl"
ITEM = "0001-parksnap"


class BreakerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-08-02T06:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def put(self, item_id=ITEM, stage="implement", priority=1):
        meta = {"id": item_id, "title": item_id, "stage": stage,
                "kind": "backend", "priority": priority,
                "created": "2026-08-02T00:00:00Z",
                "updated": "2026-08-02T06:00:00Z"}
        items.save_item(self.repo, meta, "")
        return meta

    def install_fixture(self, item_id=ITEM, lines=None):
        """Copy the reconstructed ParkSnap log into an item."""
        path = paths.item_dir(self.repo, item_id) / "log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        if lines is None:
            shutil.copyfile(FIXTURE, path)
        else:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def set_gates(self, *gates):
        config = json.loads(paths.config_path(self.repo).read_text(
            encoding="utf-8"))
        config["gates"] = list(gates)
        paths.config_path(self.repo).write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")


class FixtureShapeTest(BreakerTestCase):
    def test_fixture_is_21_states_and_20_advances(self):
        events = [json.loads(line)
                  for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
        advances = [e for e in events if e["event"] == "stage.advance"]
        self.assertEqual(len(advances), 20)
        self.assertEqual(advances[0]["data"], {"from": "idea", "to": "triage"})
        self.assertEqual(advances[-1]["data"],
                         {"from": "assure", "to": "implement"})

    def test_fixture_readme_names_its_provenance_and_status(self):
        readme = (FIXTURE.parent / "README.md").read_text(encoding="utf-8")
        self.assertIn("reconstruction, not the original log", readme)
        self.assertIn(
            "docs/factory/field-reports/"
            "2026-08-02-parksnap-p1-nonconvergence.md", readme)

    def test_fixture_carries_four_rework_edges_and_no_spend_events(self):
        self.put()
        self.install_fixture()
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["rework_edges"], 4)
        self.assertIsNone(summary["measured"])


class VerdictTest(BreakerTestCase):
    def test_verdict_key_set_is_the_contract(self):
        meta = self.put()
        self.install_fixture()
        v = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertEqual(
            set(v),
            {"over_threshold", "fired", "reason", "rework_edges", "threshold",
             "gate", "answered_at", "priority", "backlog", "stage"})
        self.assertEqual(v["reason"], "rework-threshold")
        self.assertEqual(v["threshold"], 2)
        self.assertEqual(v["stage"], "implement")
        self.assertEqual(v["priority"], 1)

    def test_fires_with_no_spend_events_at_all(self):
        """AC13: the trigger does not depend on convention-quality data."""
        self.set_gates("design", "cost")
        meta = self.put()
        self.install_fixture()
        v = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertTrue(v["over_threshold"])
        self.assertTrue(v["fired"])
        self.assertEqual(v["rework_edges"], 4)

    def test_over_threshold_is_computed_gate_independent(self):
        self.set_gates("design")
        meta = self.put()
        self.install_fixture()
        v = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertTrue(v["over_threshold"])
        self.assertFalse(v["fired"])
        self.assertFalse(v["gate"])

    def test_does_not_fire_when_destination_is_not_implement(self):
        self.set_gates("design", "cost")
        meta = self.put()
        self.install_fixture()
        v = breaker.verdict(self.repo, ITEM, meta, "review")
        self.assertTrue(v["over_threshold"])
        self.assertFalse(v["fired"])
        self.assertEqual(v["stage"], "review")

    def test_does_not_fire_below_threshold(self):
        self.set_gates("design", "cost")
        meta = self.put()
        self.install_fixture(lines=[
            json.dumps({"data": {"from": "review", "to": "implement"},
                        "event": "stage.advance",
                        "ts": "2026-08-02T01:00:00Z"}, sort_keys=True)])
        v = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertEqual(v["rework_edges"], 1)
        self.assertFalse(v["over_threshold"])
        self.assertFalse(v["fired"])

    def test_backlog_counts_priority_at_or_above_excluding_self(self):
        meta = self.put(priority=2)
        self.install_fixture()
        self.put("0002-p1", stage="plan", priority=1)
        self.put("0003-p5", stage="plan", priority=5)
        self.put("0004-done", stage="done", priority=1)
        self.put("0005-parked", stage="waiting-human", priority=1)
        v = breaker.verdict(self.repo, ITEM, meta, "implement")
        # actionable, excluding self, done and waiting-human: 0002 and 0003.
        self.assertEqual(v["backlog"]["actionable_total"], 2)
        self.assertEqual(v["backlog"]["at_or_above"], 1)

    def test_item_without_priority_counts_only_in_actionable_total(self):
        meta = self.put(priority=1)
        self.install_fixture()
        no_priority = {"id": "0002-none", "title": "none", "stage": "plan",
                       "kind": "backend", "created": "2026-08-02T00:00:00Z",
                       "updated": "2026-08-02T00:00:00Z"}
        items.save_item(self.repo, no_priority, "")
        v = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertEqual(v["backlog"]["actionable_total"], 1)
        self.assertEqual(v["backlog"]["at_or_above"], 0)


class InvarianceTest(BreakerTestCase):
    """AC17 / M5: the verdict is a function of the engine-written edges
    and nothing else. Arm (c) — a full, malformed and double-counted
    spend set with the rejection events stripped — is the forgetful-skill
    case this item exists to survive."""

    REJECTIONS = [
        {"data": {"round": 1}, "event": "review.rejected",
         "ts": "2026-08-02T01:40:00Z"},
        {"data": {"round": 2}, "event": "review.rejected",
         "ts": "2026-08-02T04:05:00Z"},
        {"data": {"round": 1}, "event": "assure.rejected",
         "ts": "2026-08-02T03:30:00Z"},
        {"data": {"round": 2}, "event": "assure.rejected",
         "ts": "2026-08-02T05:55:00Z"},
    ]
    SPEND = [
        {"data": {"provenance": "measured", "stage": "implement",
                  "dispatches": 6, "tokens": {"total": 98841}},
         "event": "spend", "ts": "2026-08-02T01:45:00Z"},
        {"data": {"provenance": "measured", "stage": "implement",
                  "dispatches": 9, "tokens": {"total": 119266}},
         "event": "spend", "ts": "2026-08-02T01:46:00Z"},
        {"data": {"provenance": "estimated"}, "event": "spend",
         "ts": "2026-08-02T01:47:00Z"},
        {"data": {"provenance": "proxy", "dispatches": 3,
                  "tokens": {"input": 5}}, "event": "spend",
         "ts": "2026-08-02T01:48:30Z"},
    ]

    def arm(self, extra):
        self.set_gates("design", "cost")
        meta = self.put()
        base = FIXTURE.read_text(encoding="utf-8").splitlines()
        lines = base + [json.dumps(e, sort_keys=True) for e in extra]
        self.install_fixture(lines=lines)
        return json.dumps(
            breaker.verdict(self.repo, ITEM, meta, "implement"),
            sort_keys=True)

    def test_four_arms_are_byte_identical(self):
        arms = {
            "a-edges-only": [],
            "b-edges-plus-rejections": self.REJECTIONS,
            "c-edges-plus-spend-no-rejections": self.SPEND,
            "d-edges-plus-everything": self.REJECTIONS + self.SPEND,
        }
        rendered = {}
        for name, extra in arms.items():
            self.tearDown()
            self.setUp()
            rendered[name] = self.arm(extra)
        values = list(rendered.values())
        for name, value in rendered.items():
            self.assertEqual(value, values[0], name)
        self.assertIn('"rework_edges": 4', values[0])
        self.assertIn('"fired": true', values[0])


class RecordAnswerTest(BreakerTestCase):
    def test_writes_artifact_logs_event_and_returns_path(self):
        self.put()
        self.install_fixture()
        path = breaker.record_answer(self.repo, ITEM, "continue")
        self.assertEqual(path, breaker.answer_path(self.repo, ITEM))
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text, "# Cost breaker answer\n\n"
                               "- answer: continue\n"
                               "- rework-edges: 4\n"
                               "- ts: 2026-08-02T06:00:00Z\n\n"
                               "(no notes)\n")
        events = logs.read_events(self.repo, ITEM)
        self.assertEqual(events[-1]["event"], "cost.answered")
        self.assertEqual(events[-1]["data"],
                         {"answer": "continue", "rework_edges": 4})

    def test_notes_are_written_verbatim(self):
        self.put()
        self.install_fixture()
        path = breaker.record_answer(self.repo, ITEM, "narrow",
                                     notes="drop the regex approach")
        self.assertIn("drop the regex approach",
                      path.read_text(encoding="utf-8"))

    def test_option_outside_answers_is_refused(self):
        self.put()
        self.install_fixture()
        with self.assertRaises(GateErrorAlias) as ctx:
            breaker.record_answer(self.repo, ITEM, "abandon")
        self.assertIn("continue, narrow, defer", str(ctx.exception))

    def test_below_threshold_is_refused(self):
        self.put()
        self.install_fixture(lines=[
            json.dumps({"data": {"from": "review", "to": "implement"},
                        "event": "stage.advance",
                        "ts": "2026-08-02T01:00:00Z"}, sort_keys=True)])
        with self.assertRaises(GateErrorAlias) as ctx:
            breaker.record_answer(self.repo, ITEM, "continue")
        self.assertIn("nothing to answer: 1 rework edges, threshold 2",
                      str(ctx.exception))

    def test_unknown_item_raises(self):
        with self.assertRaises(items.ItemError):
            breaker.record_answer(self.repo, "0999-nope", "continue")


class AnswerCoversThenLapsesTest(BreakerTestCase):
    """The anti-ping-pong core: an answer recorded at N edges covers the
    verdict at N and stops covering it at N+1."""

    EDGE_TS = ("2026-08-02T01:00:00Z", "2026-08-02T02:00:00Z",
               "2026-08-02T03:00:00Z")

    def edge(self, ts):
        return json.dumps({"data": {"from": "review", "to": "implement"},
                           "event": "stage.advance", "ts": ts},
                          sort_keys=True)

    def test_answer_at_n_edges_covers_n_and_lapses_at_n_plus_one(self):
        self.set_gates("design", "cost")
        meta = self.put()
        log = self.install_fixture(
            lines=[self.edge(ts) for ts in self.EDGE_TS[:2]])

        before = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertEqual(before["rework_edges"], breaker.REWORK_THRESHOLD)
        self.assertTrue(before["fired"])
        self.assertIsNone(before["answered_at"])

        breaker.record_answer(self.repo, ITEM, "continue")

        covered = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertEqual(covered["rework_edges"], breaker.REWORK_THRESHOLD)
        self.assertEqual(covered["answered_at"], breaker.REWORK_THRESHOLD)
        self.assertTrue(covered["over_threshold"])
        self.assertFalse(covered["fired"])

        with log.open("a", encoding="utf-8") as handle:
            handle.write(self.edge(self.EDGE_TS[2]) + "\n")

        lapsed = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertEqual(lapsed["rework_edges"], breaker.REWORK_THRESHOLD + 1)
        self.assertEqual(lapsed["answered_at"], breaker.REWORK_THRESHOLD)
        self.assertTrue(lapsed["fired"])


class VerdictIsReadOnlyTest(BreakerTestCase):
    """breaker.verdict never writes and never logs — record_answer is the
    only writer in this module."""

    def test_verdict_leaves_log_and_item_byte_identical(self):
        meta = self.put()
        log = self.install_fixture()
        item_md = paths.item_dir(self.repo, ITEM) / "item.md"
        before_log = log.read_bytes()
        before_item = item_md.read_bytes()
        breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertEqual(log.read_bytes(), before_log)
        self.assertEqual(item_md.read_bytes(), before_item)


if __name__ == "__main__":
    unittest.main()
