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


class PreconditionTest(BreakerTestCase):
    """AC18/AC19: a park with no recorded answer must not ping-pong, and
    an answer is a monotone watermark, not a permanent off switch."""

    def parked(self):
        self.set_gates("design", "cost")
        meta = self.put(stage="waiting-human")
        meta["paused-from"] = "implement"
        meta["paused-reason"] = "cost breaker: 4 rework edges (threshold 2)"
        items.save_item(self.repo, meta, "")
        self.install_fixture()
        return meta

    def test_resume_without_answer_is_refused_naming_the_verb(self):
        self.parked()
        with self.assertRaises(GateErrorAlias) as ctx:
            breaker.precondition(self.repo, ITEM, None, "implement")
        message = str(ctx.exception)
        self.assertIn("cost breaker unanswered: 4 rework edges "
                      "(threshold 2)", message)
        self.assertIn(f"factory cost-answer {ITEM} "
                      "<continue|narrow|defer>", message)

    def test_resume_with_covering_answer_is_admitted(self):
        self.parked()
        breaker.record_answer(self.repo, ITEM, "continue")
        self.assertIsNone(
            breaker.precondition(self.repo, ITEM, None, "implement"))

    def test_gate_off_applies_no_precondition(self):
        self.set_gates("design")
        self.put(stage="waiting-human")
        self.install_fixture()
        self.assertIsNone(
            breaker.precondition(self.repo, ITEM, None, "implement"))

    def test_non_implement_destination_applies_no_precondition(self):
        self.parked()
        self.assertIsNone(
            breaker.precondition(self.repo, ITEM, None, "review"))

    def test_stale_answer_at_lower_count_is_refused(self):
        self.parked()
        breaker.answer_path(self.repo, ITEM).parent.mkdir(
            parents=True, exist_ok=True)
        breaker.answer_path(self.repo, ITEM).write_text(
            "# Cost breaker answer\n\n- answer: continue\n"
            "- rework-edges: 2\n- ts: 2026-08-02T05:00:00Z\n\nx\n",
            encoding="utf-8")
        with self.assertRaises(GateErrorAlias) as ctx:
            breaker.precondition(self.repo, ITEM, None, "implement")
        self.assertIn("cost breaker answer stale: recorded at 2 rework "
                      "edges, now 4", str(ctx.exception))

    def test_answer_outside_answers_is_refused_distinctly(self):
        self.parked()
        breaker.answer_path(self.repo, ITEM).parent.mkdir(
            parents=True, exist_ok=True)
        breaker.answer_path(self.repo, ITEM).write_text(
            "# Cost breaker answer\n\n- answer: abandon\n"
            "- rework-edges: 9\n- ts: 2026-08-02T05:00:00Z\n\nx\n",
            encoding="utf-8")
        with self.assertRaises(GateErrorAlias) as ctx:
            breaker.precondition(self.repo, ITEM, None, "implement")
        self.assertIn("cost breaker answer malformed: recorded option "
                      "'abandon'", str(ctx.exception))

    def test_artifact_without_edge_count_is_refused_distinctly(self):
        self.parked()
        breaker.answer_path(self.repo, ITEM).parent.mkdir(
            parents=True, exist_ok=True)
        breaker.answer_path(self.repo, ITEM).write_text(
            "# Cost breaker answer\n\n- answer: continue\n\nx\n",
            encoding="utf-8")
        with self.assertRaises(GateErrorAlias) as ctx:
            breaker.precondition(self.repo, ITEM, None, "implement")
        self.assertIn("no '- rework-edges: N' line", str(ctx.exception))

    def test_three_refusals_have_three_distinct_messages(self):
        messages = set()
        for body, in (
            ("# Cost breaker answer\n\n- answer: continue\n\nx\n",),
            ("# Cost breaker answer\n\n- answer: abandon\n"
             "- rework-edges: 9\n\nx\n",),
            ("# Cost breaker answer\n\n- answer: continue\n"
             "- rework-edges: 2\n\nx\n",),
        ):
            self.tearDown()
            self.setUp()
            self.parked()
            path = breaker.answer_path(self.repo, ITEM)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
            with self.assertRaises(GateErrorAlias) as ctx:
                breaker.precondition(self.repo, ITEM, None, "implement")
            messages.add(str(ctx.exception))
        self.assertEqual(len(messages), 3)


class MonotoneAnswerTest(BreakerTestCase):
    """AC19/S8: continue at 2 admits the resume at 2 and does not
    suppress the fire at 3."""

    def two_edges(self):
        return [json.dumps(
            {"data": {"from": "review", "to": "implement"},
             "event": "stage.advance", "ts": ts}, sort_keys=True)
            for ts in ("2026-08-02T01:00:00Z", "2026-08-02T02:00:00Z")]

    def test_answer_at_two_admits_two_and_does_not_suppress_three(self):
        self.set_gates("design", "cost")
        meta = self.put()
        self.install_fixture(lines=self.two_edges())
        breaker.record_answer(self.repo, ITEM, "continue")
        self.assertIsNone(
            breaker.precondition(self.repo, ITEM, meta, "implement"))
        v = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertEqual(v["answered_at"], 2)
        self.assertFalse(v["fired"])
        # a third edge arrives
        logs.append_event(self.repo, ITEM, "stage.advance",
                          {"from": "assure", "to": "implement"})
        v = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertEqual(v["rework_edges"], 3)
        self.assertEqual(v["answered_at"], 2)
        self.assertTrue(v["fired"])
        with self.assertRaises(GateErrorAlias):
            breaker.precondition(self.repo, ITEM, meta, "implement")


class ReplayTest(BreakerTestCase):
    """AC14/AC15: replaying the reported run's event log fires the
    breaker before the third implement round. The replay appends the
    fixture's events one at a time and asks for a verdict after each
    stage.advance, exactly as machine.advance does."""

    def replay(self):
        self.set_gates("design", "cost")
        meta = self.put(stage="idea")
        path = paths.item_dir(self.repo, ITEM) / "log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        implement_entries = 0
        with path.open("a", encoding="utf-8") as handle:
            for raw in FIXTURE.read_text(encoding="utf-8").splitlines():
                handle.write(raw + "\n")
                handle.flush()
                event = json.loads(raw)
                if event["event"] != "stage.advance":
                    continue
                to = event["data"]["to"]
                if to == "implement":
                    implement_entries += 1
                meta["stage"] = to
                v = breaker.verdict(self.repo, ITEM, meta, to)
                if v["fired"]:
                    # the caller parks here; the implement stage skill
                    # never runs for this entry.
                    return {"edge": event["data"], "verdict": v,
                            "implement_entries": implement_entries}
        return None

    def test_fires_on_the_assure_edge_entering_the_third_round(self):
        got = self.replay()
        self.assertIsNotNone(got, "the breaker never fired on the replay")
        self.assertEqual(got["edge"], {"from": "assure", "to": "implement"})
        self.assertEqual(got["implement_entries"], 3)
        self.assertEqual(got["verdict"]["rework_edges"], 2)
        self.assertTrue(got["verdict"]["fired"])

    def test_no_implement_round_follows_the_fire(self):
        got = self.replay()
        # The replay returns at the fire, so the 4th and 5th implement
        # entries in the fixture are never reached.
        self.assertEqual(got["implement_entries"], 3)
        events = logs.read_events(self.repo, ITEM)
        entered = sum(1 for e in events
                      if e["event"] == "stage.advance"
                      and e["data"]["to"] == "implement")
        self.assertEqual(entered, 3)
        self.assertLess(len(events), 21)

    def test_fires_exactly_once_across_the_replay(self):
        self.set_gates("design", "cost")
        meta = self.put(stage="idea")
        path = paths.item_dir(self.repo, ITEM) / "log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        fires = []
        answered = False
        with path.open("a", encoding="utf-8") as handle:
            for raw in FIXTURE.read_text(encoding="utf-8").splitlines():
                handle.write(raw + "\n")
                handle.flush()
                event = json.loads(raw)
                if event["event"] != "stage.advance":
                    continue
                meta["stage"] = event["data"]["to"]
                v = breaker.verdict(self.repo, ITEM, meta,
                                    event["data"]["to"])
                if v["fired"] and not answered:
                    fires.append(v["rework_edges"])
                    answered = True
        self.assertEqual(fires, [2])


class CalibrationTest(unittest.TestCase):
    """AC16: two is the only threshold that satisfies AC14 and has a zero
    false-fire rate on this repo's real logs."""

    def test_threshold_is_two(self):
        self.assertEqual(breaker.REWORK_THRESHOLD, 2)

    def test_zero_fires_across_every_real_item_log_in_this_repo(self):
        # A failure here means a real item crossed the threshold — that is
        # the breaker doing its job, and the fix is to record an answer
        # with `factory cost-answer`, never to loosen this assertion.
        over = []
        for item_dir in sorted((ROOT / ".factory/items").iterdir()):
            if not (item_dir / "item.md").exists():
                continue
            edges = cost.summarize(ROOT, item_dir.name)["rework_edges"]
            if edges >= breaker.REWORK_THRESHOLD:
                over.append((item_dir.name, edges))
        self.assertEqual(over, [], f"items at or over threshold: {over}")

    def test_threshold_of_one_would_fire_on_historical_items(self):
        """Stated, not implied: 1 also satisfies AC14 but fires on runs
        nobody considered pathological."""
        with_any = [d.name for d in sorted((ROOT / ".factory/items").iterdir())
                    if (d / "item.md").exists()
                    and cost.summarize(ROOT, d.name)["rework_edges"] >= 1]
        self.assertGreaterEqual(len(with_any), 1)


if __name__ == "__main__":
    unittest.main()
