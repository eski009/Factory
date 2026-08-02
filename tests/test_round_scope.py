"""Item 0025 — round-scoped rework gates: implement.completed,
review.approved, verify.green and the ship gate's assure.* keys must
postdate the latest engine-written entry into implement.

Fixtures reach every gated state through machine.advance (bid-0076/0082)
— exactly what the stage skills do: create artifacts, log evidence,
advance. The single deliberate exception is TestMissingRoundMarker,
whose whole point is a corrupt log the engine never wrote.

FACTORY_NOW is frozen for every walk, so every event in every fixture
shares one timestamp: only log order can distinguish rounds, and every
stale-refusal test here is red against any timestamp-comparator
implementation (TestFrozenClockTie asserts the tie explicitly)."""

import inspect
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import assure, initrepo, items, logs, machine, paths

FROZEN_NOW = "2026-07-03T12:00:00Z"


class RoundScopeTest(unittest.TestCase):
    """Walk helpers that mirror the stage skills: artifact, evidence
    event, machine.advance — gated states are never reached by editing
    frontmatter."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = FROZEN_NOW
        initrepo.init(self.repo)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "root"],
                       cwd=self.repo, check=True, env=env)

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def art(self, rel, text="content\n"):
        p = paths.item_dir(self.repo, self.item) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def log(self, event, data=None):
        logs.append_event(self.repo, self.item, event, data)

    def make_branch(self):
        subprocess.run(["git", "branch", "-f", f"factory/{self.item}"],
                       cwd=self.repo, check=True)

    def finish_implement(self):
        self.make_branch()
        self.log("implement.completed")

    def write_assurance(self):
        item_dir = paths.item_dir(self.repo, self.item)
        shot = item_dir / "assurance" / "screenshots" / "s1.txt"
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_text("evidence\n", encoding="utf-8")
        verdicts = {"item": self.item, "journeys": [{
            "id": "J-001", "surface": "cli",
            "scenarios": [{"id": "happy-1", "verdict": "pass",
                           "expected": "e", "actual": "e",
                           "evidence": [{"type": "screenshot",
                                         "path": "assurance/screenshots/s1.txt"}]}]}]}
        vp = item_dir / "assurance" / "verdicts.json"
        vp.parent.mkdir(parents=True, exist_ok=True)
        vp.write_text(json.dumps(verdicts, indent=2), encoding="utf-8")

    def walk_to_implement(self, journeys="J-001"):
        """idea -> triage -> spec -> plan -> implement via machine.advance
        only (backend kind: no design stage)."""
        self.item = items.new_item_id(self.repo, "Round scope")
        now = logs.now_stamp()
        items.save_item(self.repo, {
            "id": self.item, "title": "Round scope", "stage": "idea",
            "kind": "backend", "created": now, "updated": now}, "")
        machine.advance(self.repo, self.item, "triage")
        self.art("triage.md")
        meta, body = items.load_item(self.repo, self.item)
        meta["priority"] = 1
        items.save_item(self.repo, meta, body)
        items.set_journeys(self.repo, self.item, journeys)
        machine.advance(self.repo, self.item, "spec")
        self.art("spec.md", "# Spec\n\n## Journey impact\nrecorded.\n")
        machine.advance(self.repo, self.item, "plan")
        self.art("plan.md", "- [ ] Task 1\n")
        machine.advance(self.repo, self.item, "implement")

    def walk_to_review(self, journeys="J-001"):
        self.walk_to_implement(journeys)
        self.finish_implement()
        machine.advance(self.repo, self.item, "review")

    def walk_to_verify(self, journeys="J-001"):
        self.walk_to_review(journeys)
        self.art("reviews/synthesis.md")
        self.log("review.approved")
        machine.advance(self.repo, self.item, "verify")

    def walk_to_assure(self):
        self.walk_to_verify()
        self.log("verify.green")
        machine.advance(self.repo, self.item, "assure")

    def rework(self):
        """The sanctioned backward edge (assure -> implement or
        review -> implement), exactly as /factory:run takes it."""
        machine.advance(self.repo, self.item, "implement")

    def refusal(self, to):
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, self.item, to)
        return str(ctx.exception)


class TestReproDead(RoundScopeTest):
    """AC3/AC9 — the defect's own form (0013 adjacent.txt §A1.1-A1.3):
    from assure, rework to implement, then advance with nothing
    re-logged."""

    def test_rework_round_with_nothing_relogged_refuses_at_review(self):
        # S3: the first forward advance of the empty rework round refuses
        self.walk_to_assure()
        self.rework()
        msg = self.refusal("review")
        self.assertIn("implement.completed", msg)
        self.assertIn("latest entry into implement", msg)
        self.assertIn("re-run implement", msg)
        self.assertNotIn("not logged", msg)
        # the walk to assure/ship on round-1 evidence is impossible: the
        # item is still parked at implement after the refusal
        self.assertEqual(
            items.load_item(self.repo, self.item)[0]["stage"], "implement")

    def test_recovery_after_refusal(self):
        # S8: re-running the refused stage unblocks the same advance
        self.walk_to_assure()
        self.rework()
        self.refusal("review")
        self.finish_implement()          # fresh implement.completed
        meta, _verdict = machine.advance(self.repo, self.item, "review")
        self.assertEqual(meta["stage"], "review")

    def test_full_rework_round_with_fresh_evidence_ships(self):
        # S2: an honest rework round that re-logs everything ships
        self.walk_to_assure()
        self.write_assurance()
        self.log("assure.passed")
        self.rework()
        self.finish_implement()
        machine.advance(self.repo, self.item, "review")
        self.log("review.approved")
        machine.advance(self.repo, self.item, "verify")
        self.log("verify.green")
        machine.advance(self.repo, self.item, "assure")
        self.log("assure.passed")
        meta, _verdict = machine.advance(self.repo, self.item, "ship")
        self.assertEqual(meta["stage"], "ship")

    def test_clean_single_round_walk_unblocked(self):
        # S1/AC9: no gate refuses a first-round item at any stage
        self.walk_to_assure()
        self.write_assurance()
        self.log("assure.passed")
        meta, _verdict = machine.advance(self.repo, self.item, "ship")
        self.assertEqual(meta["stage"], "ship")


class TestStaleRefusalShape(RoundScopeTest):
    """AC4/AC5 — one B2 sentence shape across the four gates; 'not
    logged' only for genuinely absent events (bid-0083)."""

    SHAPE = re.compile(
        r"^event '[a-z.]+' after the latest implementation round required: "
        r"the logged '[a-z.]+' predates the latest entry into implement "
        r"— re-run (implement|review|verify|assure) to log fresh evidence$")

    def test_gate_review_stale_implement_completed(self):
        self.walk_to_assure()
        self.rework()
        msg = self.refusal("review")
        self.assertRegex(msg, self.SHAPE)
        self.assertNotIn("not logged", msg)

    def test_gate_review_absent_event_still_says_not_logged(self):
        self.walk_to_implement()
        self.make_branch()               # branch exists, event never logged
        msg = self.refusal("review")
        self.assertIn("'implement.completed' not logged", msg)
        self.assertNotIn("predates", msg)

    def test_gate_verify_stale_review_approved(self):
        self.walk_to_review()
        self.art("reviews/synthesis.md")
        self.log("review.approved")      # round 1
        machine.advance(self.repo, self.item, "implement")   # rework
        self.finish_implement()
        machine.advance(self.repo, self.item, "review")
        msg = self.refusal("verify")
        self.assertRegex(msg, self.SHAPE)
        self.assertIn("review.approved", msg)

    def test_gate_assure_stale_verify_green(self):
        self.walk_to_assure()
        self.rework()
        self.finish_implement()
        machine.advance(self.repo, self.item, "review")
        self.log("review.approved")
        machine.advance(self.repo, self.item, "verify")
        msg = self.refusal("assure")     # verify.green is round-1's
        self.assertRegex(msg, self.SHAPE)
        self.assertIn("verify.green", msg)

    def test_gate_ship_journeys_none_stale_verify_green_refused(self):
        # S4/AC4: red-first against today's machine.py:403-405 lifetime
        # check. Declaring journeys none mid-rework mirrors the existing
        # test_declaring_none_at_assure_still_advances_to_ship precedent.
        self.walk_to_assure()
        self.rework()                    # assure -> implement
        items.set_journeys(self.repo, self.item, "none")
        self.finish_implement()
        machine.advance(self.repo, self.item, "review")
        self.log("review.approved")
        machine.advance(self.repo, self.item, "verify")
        msg = self.refusal("ship")       # journeys none: verify -> ship
        self.assertRegex(msg, self.SHAPE)
        self.assertIn("verify.green", msg)

    def test_gate_ship_stale_assure_passed(self):
        self.walk_to_assure()
        self.write_assurance()
        self.log("assure.passed")        # round 1
        self.rework()
        self.finish_implement()
        machine.advance(self.repo, self.item, "review")
        self.log("review.approved")
        machine.advance(self.repo, self.item, "verify")
        self.log("verify.green")
        machine.advance(self.repo, self.item, "assure")
        msg = self.refusal("ship")
        self.assertRegex(msg, self.SHAPE)
        self.assertIn("assure.passed", msg)

    def test_gate_ship_absent_assurance_keeps_incumbent_message(self):
        # Assumption 2 boundary: the absent case keeps its incumbent text
        self.walk_to_assure()
        msg = self.refusal("ship")
        self.assertEqual(msg, "assure.passed (or a recorded human waiver) "
                              "after the latest implementation round required")


class TestSpecialResume(RoundScopeTest):
    """AC8 — SPECIAL-from edges never reset the round; real backward
    edges always do (B5, jdg-0107)."""

    def test_park_resume_at_implement_does_not_reset_round(self):
        # AC8(i): red against an include-all predicate — the resume edge
        # waiting-human -> implement postdates implement.completed, so a
        # predicate that counted it would call the evidence stale.
        self.walk_to_implement()
        self.finish_implement()
        machine.advance(self.repo, self.item, "waiting-human", reason="q")
        machine.advance(self.repo, self.item, "implement")   # resume
        meta, _verdict = machine.advance(self.repo, self.item, "review")
        self.assertEqual(meta["stage"], "review")

    def test_rework_after_park_resume_still_resets(self):
        # AC8(ii): review -> park -> resume-to-review -> implement is a
        # real round reset; round-1 implement.completed goes stale.
        self.walk_to_review()
        machine.advance(self.repo, self.item, "waiting-human", reason="q")
        machine.advance(self.repo, self.item, "review")      # resume
        machine.advance(self.repo, self.item, "implement")   # rework edge
        msg = self.refusal("review")
        self.assertIn("predates the latest entry into implement", msg)


class TestFrozenClockTie(RoundScopeTest):
    def test_entire_rework_round_in_one_second_still_refused(self):
        # S6/AC7: every event shares one timestamp — red against any
        # timestamp-comparator implementation of the predicate.
        self.walk_to_assure()
        self.rework()
        stamps = {e["ts"] for e in logs.read_events(self.repo, self.item)}
        self.assertEqual(stamps, {FROZEN_NOW})
        msg = self.refusal("review")
        self.assertIn("predates the latest entry into implement", msg)


class TestMissingRoundMarker(unittest.TestCase):
    """AC6, B4/B5 test iii — a log with no non-SPECIAL entry into
    implement fails closed at every migrated gate, and the corrupt-log
    case gains no new sentinel path. Deliberately hand-built fixtures:
    this is the corrupt/hand-edited-log case machine.advance can never
    produce, the one sanctioned exception to the walk-only fixture rule.
    Each log carries a SPECIAL-from marker (waiting-human -> implement)
    to prove the exclusion holds even when it is the only candidate."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = FROZEN_NOW
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "root"],
                       cwd=self.repo, check=True, env=env)

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def seed(self, stage, journeys="J-001", events=()):
        items.save_item(self.repo, {
            "id": "0001-x", "title": "X", "stage": stage, "kind": "backend",
            "journeys": journeys, "priority": 1,
            "created": FROZEN_NOW, "updated": FROZEN_NOW}, "# X\n")
        logs.append_event(self.repo, "0001-x", "stage.advance",
                          {"from": "waiting-human", "to": "implement"})
        for e in events:
            logs.append_event(self.repo, "0001-x", e)

    def assert_marker_refusal(self, to):
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, "0001-x", to)
        msg = str(ctx.exception)
        self.assertIn("no entry into implement", msg)
        self.assertNotIn("not logged", msg)

    def test_gate_review_fails_closed(self):
        self.seed("implement", events=("implement.completed",))
        subprocess.run(["git", "branch", "factory/0001-x"],
                       cwd=self.repo, check=True)
        self.assert_marker_refusal("review")

    def test_gate_verify_fails_closed(self):
        self.seed("review", events=("review.approved",))
        p = paths.item_dir(self.repo, "0001-x") / "reviews" / "synthesis.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("s\n", encoding="utf-8")
        self.assert_marker_refusal("verify")

    def test_gate_assure_fails_closed(self):
        self.seed("verify", events=("verify.green",))
        self.assert_marker_refusal("assure")

    def test_gate_ship_fails_closed(self):
        self.seed("assure", events=("verify.green", "assure.passed"))
        self.assert_marker_refusal("ship")

    def test_gate_ship_journeys_none_fails_closed(self):
        self.seed("verify", journeys="none", events=("verify.green",))
        self.assert_marker_refusal("ship")

    def test_record_confirmation_fails_closed(self):
        self.seed("assure", events=("assure.passed",))
        with self.assertRaises(machine.GateError) as ctx:
            assure.record_confirmation(self.repo, "0001-x")
        self.assertIn("no entry into implement", str(ctx.exception))


class TestSingleHelperInspection(unittest.TestCase):
    """AC1/AC2 — one predicate, no timestamp comparisons, no private
    postdating copies left anywhere."""

    def _src(self, rel):
        return (Path(__file__).resolve().parents[1] / rel).read_text(
            encoding="utf-8")

    def test_no_postdating_comparison_outside_the_helper(self):
        machine_src = self._src("scripts/factory/lib/machine.py")
        self.assertNotIn(
            'impl = _last_index(events, "implement.completed")', machine_src)
        self.assertNotIn("> impl", machine_src)
        assure_src = self._src("scripts/factory/lib/assure.py")
        self.assertNotIn("_last_index", assure_src)
        self.assertIn("_postdates_latest_implement", assure_src)

    def test_no_timestamp_comparison_in_predicate_or_gates(self):
        for fn in (machine._postdates_latest_implement,
                   machine._require_event_this_round,
                   machine._gate_review, machine._gate_verify,
                   machine._gate_assure, machine._gate_ship):
            self.assertNotIn('"ts"', inspect.getsource(fn))

    def test_all_gates_route_through_the_round_helper(self):
        for fn in (machine._gate_review, machine._gate_verify,
                   machine._gate_assure):
            src = inspect.getsource(fn)
            self.assertIn("_require_event_this_round", src)
            self.assertNotIn("_require_event(", src)
        ship = inspect.getsource(machine._gate_ship)
        self.assertIn("_require_event_this_round", ship)
        self.assertIn("_postdates_latest_implement", ship)
        self.assertNotIn("_require_event(", ship)


if __name__ == "__main__":
    unittest.main()
