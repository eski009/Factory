import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory
from scripts.factory.lib import breaker, cost, initrepo, items, logs, paths
from scripts.factory.lib.machine import GateError as GateErrorAlias

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/parksnap-2026-08-02/log.jsonl"
CALIBRATION = ROOT / "tests/fixtures/calibration-2026-08-02.json"
REGEN = ROOT / "tests/fixtures/calibration_2026_08_02_regen.py"
ITEM = "0001-parksnap"


def has_live_items():
    """True only when this checkout carries real live factory state.

    `.factory/` is gitignored (`.gitignore:6`), so it is absent on CI and
    in a fresh clone — except that one stray file under it
    (`.factory/items/0012-.../plan.md`) is tracked, which makes
    `.factory/items` *exist* in a clone while holding no item at all.
    Testing for the directory alone therefore admits an empty, vacuous
    run on CI; the guard tests for an actual `item.md`.
    """
    return any((ROOT / ".factory/items").glob("*/item.md"))


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
        # N2: the sub-dict is contract too. Pinned the same way
        # `test_cost.py`'s `coverage` key set is, so a fourth key cannot
        # be dropped or renamed without this test saying so.
        self.assertEqual(
            set(v["backlog"]),
            {"at_or_above", "actionable_total", "unreadable", "unpriced"})
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

    def test_backlog_counts_is_none_not_zero_when_priority_unset(self):
        meta = self.put()
        meta.pop("priority", None)
        items.save_item(self.repo, meta, "")
        meta, _ = items.load_item(self.repo, ITEM)
        self.install_fixture()
        self.put("0002-p1", stage="plan", priority=1)
        self.put("0003-p5", stage="plan", priority=5)
        v = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertIsNone(v["backlog"]["at_or_above"])
        self.assertEqual(v["backlog"]["actionable_total"], 2)
        # The subject is itself unpriced here, and `unpriced` counts what
        # this item is blocking — never the item doing the blocking.
        self.assertEqual(v["backlog"]["unpriced"], 0)

    def test_backlog_counts_reports_unreadable_items_it_dropped(self):
        # N4: list_items_safe's error list is no longer discarded.
        meta = self.put(priority=1)
        self.install_fixture()
        self.put("0002-p1", stage="plan", priority=1)
        bad = paths.items_dir(self.repo) / "0009-corrupt"
        bad.mkdir(parents=True, exist_ok=True)
        (bad / "item.md").write_bytes(b"\xff\xfe not utf-8")
        v = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertEqual(v["backlog"]["unreadable"], 1)

    def test_backlog_counts_reports_unpriced_actionable_siblings(self):
        """F6: an actionable sibling carrying no numeric priority is not
        'not waiting' — it is incomparable, the same population B1 forbids
        rendering as a `0`. `at_or_above` cannot carry it, so the count
        gets its own key rather than being silently dropped."""
        meta = self.put(priority=2)
        self.install_fixture()
        self.put("0002-p1", stage="plan", priority=1)
        for item_id in ("0003-none", "0004-none", "0005-none"):
            items.save_item(self.repo, {
                "id": item_id, "title": item_id, "stage": "plan",
                "kind": "backend", "created": "2026-08-02T00:00:00Z",
                "updated": "2026-08-02T00:00:00Z"}, "")
        # Not actionable, and unpriced: it must not be counted either.
        items.save_item(self.repo, {
            "id": "0006-done", "title": "0006-done", "stage": "done",
            "kind": "backend", "created": "2026-08-02T00:00:00Z",
            "updated": "2026-08-02T00:00:00Z"}, "")
        v = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertEqual(v["backlog"]["unpriced"], 3)
        self.assertEqual(v["backlog"]["at_or_above"], 1)
        self.assertEqual(v["backlog"]["actionable_total"], 4)

    def test_backlog_counts_unpriced_is_zero_when_every_sibling_is_priced(self):
        meta = self.put(priority=2)
        self.install_fixture()
        self.put("0002-p1", stage="plan", priority=1)
        v = breaker.verdict(self.repo, ITEM, meta, "implement")
        self.assertEqual(v["backlog"]["unpriced"], 0)


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

    def test_artifact_without_answer_line_is_refused_distinctly(self):
        """AC10 (item 0028, absorbed by 0027). `read_answer` returns
        `{"answer": None, ...}` for an artifact with no `- answer:` line,
        and before this arm the out-of-enum arm below rendered that to
        the operator as `recorded option None is not one of continue,
        narrow, defer` on the live cost-breaker decision path. The
        wording mirrors the conformant sibling watermark arm and
        `approach.py:86`."""
        self.parked()
        breaker.answer_path(self.repo, ITEM).parent.mkdir(
            parents=True, exist_ok=True)
        breaker.answer_path(self.repo, ITEM).write_text(
            "# Cost breaker answer\n\n- rework-edges: 9\n"
            "- ts: 2026-08-02T05:00:00Z\n\nx\n", encoding="utf-8")
        with self.assertRaises(GateErrorAlias) as ctx:
            breaker.precondition(self.repo, ITEM, None, "implement")
        message = str(ctx.exception)
        self.assertEqual(
            message,
            "cost breaker answer malformed: no '- answer: <option>' line; "
            f"re-record with factory cost-answer {ITEM} "
            "<continue|narrow|defer>")
        self.assertNotIn("None", message)

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

    def test_four_refusals_have_four_distinct_messages(self):
        """AC11: the four malformed/stale arms are pairwise-distinct over
        one fixture set. An operator who hits one must be moved to a
        different arm by fixing what it names — two arms sharing a
        message is an unbreaking loop.

        The distinctness count alone passes on the pre-fix engine, and
        vacuously: the missing-`- answer:` body and the out-of-enum body
        fall into the *same* arm and are told apart only by the leaked
        `None` repr. The `assertNotIn` below is what makes this test
        binding — four distinct messages, none of them a Python repr.
        """
        messages = set()
        for body, in (
            ("# Cost breaker answer\n\n- answer: continue\n\nx\n",),
            ("# Cost breaker answer\n\n- rework-edges: 9\n\nx\n",),
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
        self.assertEqual(len(messages), 4, messages)
        self.assertNotIn("None", " ".join(sorted(messages)))

    def test_the_out_of_enum_arm_still_names_the_recorded_value(self):
        """AC11: the new missing-field arm must not swallow the arm that
        reports what was actually written."""
        self.parked()
        path = breaker.answer_path(self.repo, ITEM)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Cost breaker answer\n\n- answer: bogus\n"
                        "- rework-edges: 9\n\nx\n", encoding="utf-8")
        with self.assertRaises(GateErrorAlias) as ctx:
            breaker.precondition(self.repo, ITEM, None, "implement")
        self.assertIn(
            "recorded option 'bogus' is not one of continue, narrow, defer",
            str(ctx.exception))


class MissingAnswerFieldCliTest(BreakerTestCase):
    """AC10, end to end through the CLI the packet tells the operator to
    run. The unit test above pins the message; this pins what the
    operator actually sees on their terminal — exit code, stream, and the
    absence of a Python repr."""

    def test_cli_refusal_is_the_exact_message_and_carries_no_none(self):
        self.set_gates("design", "cost")
        meta = self.put(stage="waiting-human")
        meta["paused-from"] = "implement"
        meta["paused-reason"] = "cost breaker: 4 rework edges (threshold 2)"
        items.save_item(self.repo, meta, "")
        self.install_fixture()
        path = breaker.answer_path(self.repo, ITEM)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Cost breaker answer\n\n- rework-edges: 9\n"
                        "- ts: 2026-08-02T05:00:00Z\n\nx\n",
                        encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(self.repo), "advance", ITEM,
                                 "implement"])
        self.assertEqual(code, 2, err.getvalue())
        self.assertEqual(
            err.getvalue().strip(),
            "refused: cost breaker answer malformed: no '- answer: "
            f"<option>' line; re-record with factory cost-answer {ITEM} "
            "<continue|narrow|defer>")
        self.assertNotIn("None", out.getvalue() + err.getvalue())


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
        self.assertIsNotNone(got, "the breaker never fired on the replay")
        # The replay returns at the fire, so the 4th and 5th implement
        # entries in the fixture are never reached.
        self.assertEqual(got["implement_entries"], 3)
        events = logs.read_events(self.repo, ITEM)
        entered = sum(1 for e in events
                      if e["event"] == "stage.advance"
                      and e["data"]["to"] == "implement")
        self.assertEqual(entered, 3)
        # Exactly the prefix up to and including the firing edge: the
        # fixture's 1 item.created + its first 12 stage.advance events
        # (fixture line 13 is the assure -> implement edge that fires).
        # The full fixture is 21 events, so 8 never reached disk.
        self.assertEqual(len(events), 13)
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

    def full_replay_with_park_and_resume(self, answer):
        """Replay the whole fixture, modelling what actually happens at a
        fire: the firing transition is admitted, the caller parks the
        item, and the operator resumes it. The park/resume pair the
        engine writes (`implement -> waiting-human`, then
        `waiting-human -> implement`) adds no rework edge by design
        (`cost.REWORK_FROM`), so the resume re-enters implement at the
        *same* count — which is the only place a re-fire can happen and
        the only place `record_answer` can suppress one.

        `answer=False` is the same replay with the remedy withheld.
        """
        self.set_gates("design", "cost")
        meta = self.put(stage="idea")
        path = paths.item_dir(self.repo, ITEM) / "log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        advances = 0
        fires = []
        refusals = []
        for raw in FIXTURE.read_text(encoding="utf-8").splitlines():
            # One open() per line: record_answer and append_event write to
            # this same log, so the replay must not hold a buffered handle
            # open across them.
            with path.open("a", encoding="utf-8") as handle:
                handle.write(raw + "\n")
            event = json.loads(raw)
            if event["event"] != "stage.advance":
                continue
            advances += 1
            to = event["data"]["to"]
            meta["stage"] = to
            verdict = breaker.verdict(self.repo, ITEM, meta, to)
            if not verdict["fired"]:
                continue
            fires.append((event["data"], verdict["rework_edges"]))
            if answer:
                breaker.record_answer(self.repo, ITEM, "continue")
            logs.append_event(self.repo, ITEM, "stage.advance",
                              {"from": "implement", "to": "waiting-human"})
            logs.append_event(self.repo, ITEM, "stage.advance",
                              {"from": "waiting-human", "to": "implement"})
            meta["stage"] = "implement"
            resumed = breaker.verdict(self.repo, ITEM, meta, "implement")
            if resumed["fired"]:
                fires.append(("re-fire on resume", resumed["rework_edges"]))
            try:
                breaker.precondition(self.repo, ITEM, meta, "implement")
            except GateErrorAlias as exc:
                refusals.append(str(exc))
        return {"advances": advances, "fires": fires, "refusals": refusals}

    def test_fires_once_per_edge_count_under_real_suppression(self):
        """AC16/AC18 proved through the real mechanism rather than a local
        flag. `answered` in the test above only gates list-appending, so
        that test would pass even if the breaker fired on every implement
        entry. Here every fire is followed by breaker.record_answer and a
        real park/resume back into implement at the same count; a re-fire
        would land in `fires` and break the assertion."""
        got = self.full_replay_with_park_and_resume(answer=True)
        self.assertEqual(got["advances"], 20)
        # Exactly one fire per distinct edge count at or above the
        # threshold, in order, never twice at the same count. The first is
        # the AC16 fire: the assure -> implement edge at 2.
        self.assertEqual(got["fires"], [
            ({"from": "assure", "to": "implement"}, 2),
            ({"from": "review", "to": "implement"}, 3),
            ({"from": "assure", "to": "implement"}, 4),
        ])
        self.assertEqual(len(got["fires"]), 3)
        # The answered resume is admitted, every time (B3: no park loop).
        self.assertEqual(got["refusals"], [])

    def test_withholding_the_answer_re_fires_on_every_resume(self):
        """The control arm that gives the test above its teeth: the same
        replay with record_answer withheld doubles the fire count, because
        each resume re-enters implement at an uncovered count, and the
        resume precondition refuses each time naming the remedy."""
        got = self.full_replay_with_park_and_resume(answer=False)
        self.assertEqual(got["advances"], 20)
        self.assertEqual(got["fires"], [
            ({"from": "assure", "to": "implement"}, 2),
            ("re-fire on resume", 2),
            ({"from": "review", "to": "implement"}, 3),
            ("re-fire on resume", 3),
            ({"from": "assure", "to": "implement"}, 4),
            ("re-fire on resume", 4),
        ])
        self.assertEqual(len(got["refusals"]), 3)
        for message in got["refusals"]:
            self.assertIn("cost breaker unanswered", message)
            self.assertIn(f"factory cost-answer {ITEM}", message)

    def test_the_fixture_carries_four_rework_edges(self):
        """Pins what the two replays above are counting against."""
        rework = 0
        for line in FIXTURE.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event["event"] != "stage.advance":
                continue
            data = event["data"]
            if data["from"] in breaker.REWORK_FROM and data["to"] == "implement":
                rework += 1
        # Four edges, of which the first sits below the threshold — hence
        # three fires, not four.
        self.assertEqual(rework, 4)


class CalibrationEvidenceTest(unittest.TestCase):
    """AC16, against versioned evidence.

    The calibration that justifies REWORK_THRESHOLD = 2 was measured on
    this repo's own `.factory/items/*/log.jsonl`, which is gitignored
    (`.gitignore:6`) and so does not exist on CI or in a fresh clone.
    The measurement is therefore frozen into a checked-in fixture, whose
    provenance block names the date, the repo and the derivation. This
    class runs everywhere; `LiveDogfoodCalibrationTest` below is the
    part that needs live state.
    """

    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(
            CALIBRATION.read_text(encoding="utf-8"))
        cls.rows = cls.doc["rework_edges_by_item"]

    def test_threshold_is_two(self):
        self.assertEqual(breaker.REWORK_THRESHOLD, 2)

    def test_evidence_names_its_provenance(self):
        provenance = self.doc["provenance"]
        self.assertEqual(provenance["generated"], "2026-08-02")
        self.assertIn("factory", provenance["repo"])
        self.assertIn(".factory/items/*/log.jsonl", provenance["method"])
        self.assertIn("gitignored", provenance["method"])
        self.assertIn("calibration_2026_08_02_regen.py",
                      provenance["regenerate"])

    def test_threshold_two_fires_on_zero_of_the_measured_population(self):
        over = sorted((name, edges) for name, edges in self.rows.items()
                      if edges >= breaker.REWORK_THRESHOLD)
        self.assertEqual(over, [], f"items at or over threshold: {over}")

    def test_threshold_of_one_would_fire_on_two_named_items(self):
        """Stated, not implied: 1 also satisfies AC14 but fires on runs
        nobody considered pathological. Pinned by name and by count, not
        by a loose lower bound — a bound of `>= 1` would pass on an empty
        population."""
        would_fire = sorted(name for name, edges in self.rows.items()
                            if edges >= 1)
        self.assertEqual(would_fire, [
            "0004-per-item-cost-meter-measure-and-report-t",
            "0009-finish-the-never-bricks-promise-crash-pr",
        ])
        self.assertEqual(len(would_fire), 2)
        self.assertTrue(all(self.rows[name] == 1 for name in would_fire))

    def test_measured_population_is_the_one_the_spec_describes(self):
        """Spec AC16: "2 items have one rework edge each, 15 have none"."""
        self.assertEqual(len(self.rows), 17)
        self.assertEqual(sum(1 for n in self.rows.values() if n == 1), 2)
        self.assertEqual(sum(1 for n in self.rows.values() if n == 0), 15)
        self.assertEqual(max(self.rows.values()), 1)

    def test_regenerator_is_not_collected_as_a_test(self):
        """The derivation ships beside the evidence so anyone can rerun
        it, but it must never be picked up by `unittest discover`."""
        self.assertTrue(REGEN.exists())
        self.assertFalse(REGEN.name.startswith("test"))


@unittest.skipUnless(
    has_live_items(),
    ".factory/ is gitignored: live dogfood state is absent on CI and in a "
    "fresh clone (the versioned evidence is CalibrationEvidenceTest)")
class LiveDogfoodCalibrationTest(unittest.TestCase):
    """The live half of AC16: this repo eats its own breaker.

    The assertion is deliberately "nothing is over the threshold
    *unanswered*", not "nothing is over the threshold". An item reaching
    two rework edges is the breaker working, not a regression, and
    `factory cost-answer` is the honest remedy — which only greens a test
    that reads the answer artifact. A test asserting the raw count could
    never be greened by the remedy its own comment prescribes.
    """

    def live_rows(self):
        """items.list_items_safe, as breaker.py:60 does, so one malformed
        real item.md is reported rather than exploding the suite."""
        metas, errors = items.list_items_safe(ROOT)
        rows = [(m["id"], cost.summarize(ROOT, m["id"])["rework_edges"])
                for m in sorted(metas, key=lambda m: m["id"])]
        return rows, errors

    def test_no_live_item_is_over_the_threshold_without_an_answer(self):
        rows, errors = self.live_rows()
        unanswered = []
        for item_id, edges in rows:
            if edges < breaker.REWORK_THRESHOLD:
                continue
            answer = breaker.read_answer(ROOT, item_id)
            covered = (answer is not None
                       and isinstance(answer["rework_edges"], int)
                       and answer["rework_edges"] >= edges
                       and answer["answer"] in breaker.ANSWERS)
            if not covered:
                unanswered.append((item_id, edges, answer))
        self.assertEqual(
            unanswered, [],
            "items at or over the threshold with no answer covering the "
            f"current count: {unanswered}. This is the breaker doing its "
            "job. Record an answer with `factory cost-answer <id> "
            "<continue|narrow|defer>` — never loosen this assertion. "
            f"(unreadable items, omitted: {errors})")

    def test_the_guard_and_the_reader_agree(self):
        """Non-vacuity: the skip guard globs for item.md, the assertion
        reads through items.list_items_safe. If those two ever disagree
        the class could run and assert over nothing.

        The invariant is read-or-reported, not read: an unreadable real
        item.md must land in `errors`, never be silently dropped."""
        rows, errors = self.live_rows()
        self.assertGreater(len(rows), 0)
        on_disk = list((ROOT / ".factory/items").glob("*/item.md"))
        self.assertEqual(len(rows) + len(errors), len(on_disk))


if __name__ == "__main__":
    unittest.main()
