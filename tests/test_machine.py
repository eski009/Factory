import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import breaker, initrepo, items, logs, machine, paths


def make_item(repo, kind="ui", stage="idea", priority=None, bug=False, journeys=None):
    meta = {
        "id": "0001-thing", "title": "Thing", "stage": stage, "kind": kind,
        "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z",
    }
    if priority:
        meta["priority"] = priority
    if bug:
        meta["bug"] = True
    if journeys:
        meta["journeys"] = journeys
    items.save_item(repo, meta, "# Thing\n")
    return meta


def write(repo, rel, text="content\n"):
    p = paths.item_dir(repo, "0001-thing") / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


SPEC_MD = "# Spec\n\n## Journey impact\nNone - no customer journey affected.\n"


class MachineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()


class TestSequence(MachineTest):
    def test_backend_skips_design(self):
        self.assertNotIn("design", machine.stage_sequence("backend"))
        self.assertIn("design", machine.stage_sequence("ui"))

    def test_next_stage_for_backend_spec_is_plan(self):
        meta = make_item(self.repo, kind="backend", stage="spec")
        self.assertEqual(machine.next_stage(meta), "plan")

    def test_done_has_no_next(self):
        meta = make_item(self.repo, stage="done")
        self.assertIsNone(machine.next_stage(meta))

    def test_assure_sits_between_verify_and_ship(self):
        seq = machine.stage_sequence("ui")
        self.assertEqual(seq.index("assure"), seq.index("verify") + 1)
        self.assertEqual(seq.index("ship"), seq.index("assure") + 1)

    def test_journeys_none_skips_assure(self):
        self.assertNotIn("assure", machine.stage_sequence("ui", "none"))
        self.assertNotIn("assure", machine.stage_sequence("backend", "none"))
        self.assertIn("assure", machine.stage_sequence("ui", "J-001"))
        self.assertIn("assure", machine.stage_sequence("ui", None))

    def test_next_stage_verify_routes_by_journeys(self):
        meta = make_item(self.repo, stage="verify")
        self.assertEqual(machine.next_stage(meta), "assure")
        meta["journeys"] = "none"
        self.assertEqual(machine.next_stage(meta), "ship")


class TestLegality(MachineTest):
    def test_skipping_ahead_refused(self):
        make_item(self.repo)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")

    def test_advance_idea_to_triage(self):
        make_item(self.repo)
        meta, _verdict = machine.advance(self.repo, "0001-thing", "triage")
        self.assertEqual(meta["stage"], "triage")
        self.assertEqual(logs.count_events(self.repo, "0001-thing", "stage.advance"), 1)

    def test_done_items_cannot_be_paused(self):
        make_item(self.repo, stage="done")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "waiting-human", reason="oops")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "blocked", reason="oops")

    def test_pause_and_resume_only_to_paused_from(self):
        make_item(self.repo, stage="design")
        machine.advance(self.repo, "0001-thing", "waiting-human", reason="pick a design")
        meta, _ = items.load_item(self.repo, "0001-thing")
        self.assertEqual(meta["paused-from"], "design")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")
        meta, _verdict = machine.advance(self.repo, "0001-thing", "design")
        self.assertNotIn("paused-from", meta)

    def test_advance_on_copied_dir_with_stale_id_raises_item_error(self):
        # C1: a copied/renamed item dir whose item.md still carries the
        # original id must not silently write into the original item's
        # files. load_item (called by advance) refuses it.
        make_item(self.repo)
        copy_dir = paths.item_dir(self.repo, "0002-thing-copy")
        shutil.copytree(paths.item_dir(self.repo, "0001-thing"), copy_dir)
        with self.assertRaises(items.ItemError):
            machine.advance(self.repo, "0002-thing-copy", "triage")
        # the original item's file must be untouched
        original, _ = items.load_item(self.repo, "0001-thing")
        self.assertEqual(original["stage"], "idea")

    def test_unknown_stage_raises_gate_error(self):
        make_item(self.repo, stage="idea")
        item_md = paths.item_dir(self.repo, "0001-thing") / "item.md"
        item_md.write_text(item_md.read_text().replace("stage: idea", "stage: bogus"),
                           encoding="utf-8")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "triage")


class TestGates(MachineTest):
    def test_design_requires_journey_impact_section_and_declaration(self):
        meta = make_item(self.repo, stage="spec", priority=1)
        write(self.repo, "spec.md", "# Spec without the section\n")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "design")
        write(self.repo, "spec.md", SPEC_MD)
        # section present but journeys never declared -> still refused
        meta, body = items.load_item(self.repo, "0001-thing")
        meta.pop("journeys", None)
        items.save_item(self.repo, meta, body)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "design")
        items.set_journeys(self.repo, "0001-thing", "none")
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "design")[0]["stage"], "design")

    def test_plan_requires_journey_impact_for_backend(self):
        make_item(self.repo, kind="backend", stage="spec", priority=1)
        write(self.repo, "spec.md", "# Spec without the section\n")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")

    def test_spec_requires_triage_record_and_priority(self):
        make_item(self.repo, stage="triage")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "spec")
        write(self.repo, "triage.md")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "spec")

    def test_spec_allowed_with_triage_and_priority(self):
        make_item(self.repo, stage="triage", priority=1)
        write(self.repo, "triage.md")
        meta, _verdict = machine.advance(self.repo, "0001-thing", "spec")
        self.assertEqual(meta["stage"], "spec")

    def test_plan_requires_design_choice_for_ui(self):
        make_item(self.repo, stage="design", priority=1, journeys="none")
        write(self.repo, "spec.md", SPEC_MD)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")
        write(self.repo, "design/choice.md", "choice: option-b\n")
        meta, _verdict = machine.advance(self.repo, "0001-thing", "plan")
        self.assertEqual(meta["stage"], "plan")

    def test_plan_requires_repro_for_bug(self):
        make_item(self.repo, kind="backend", stage="spec", priority=1, bug=True,
                   journeys="none")
        write(self.repo, "spec.md", SPEC_MD)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")
        write(self.repo, "repro.md", "# Repro\n## Command\nfoo\n")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")
        logs.append_event(self.repo, "0001-thing", "repro.confirmed",
                          {"command": "foo", "exit": 1, "mode": "command"})
        self.assertEqual(machine.advance(self.repo, "0001-thing", "plan")[0]["stage"], "plan")

    def test_plan_requires_repro_event_even_with_file(self):
        make_item(self.repo, kind="backend", stage="spec", priority=1, bug=True,
                   journeys="none")
        write(self.repo, "spec.md", SPEC_MD)
        write(self.repo, "repro.md", "")  # empty file also refused
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")

    def test_plan_without_bug_flag_needs_no_repro(self):
        make_item(self.repo, kind="backend", stage="spec", priority=1, journeys="none")
        write(self.repo, "spec.md", SPEC_MD)
        self.assertEqual(machine.advance(self.repo, "0001-thing", "plan")[0]["stage"], "plan")

    def test_plan_bug_ui_item_needs_both_choice_and_repro(self):
        make_item(self.repo, kind="ui", stage="design", priority=1, bug=True,
                   journeys="none")
        write(self.repo, "spec.md", SPEC_MD)
        write(self.repo, "design/choice.md", "choice: option-b\n")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")
        write(self.repo, "repro.md", "# Repro\n")
        logs.append_event(self.repo, "0001-thing", "repro.confirmed")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "plan")[0]["stage"], "plan")

    def test_implement_requires_plan_with_task(self):
        make_item(self.repo, stage="plan", priority=1)
        write(self.repo, "plan.md", "no tasks here\n")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "implement")
        write(self.repo, "plan.md", "- [ ] Task 1\n")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "implement")[0]["stage"], "implement")

    def test_review_requires_branch_and_completion_event(self):
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        make_item(self.repo, stage="implement", priority=1)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "review")
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"], cwd=self.repo, check=True,
                       env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                                GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
        subprocess.run(["git", "branch", "factory/0001-thing"], cwd=self.repo, check=True)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "review")
        logs.append_event(self.repo, "0001-thing", "implement.completed")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "review")[0]["stage"], "review")

    def test_verify_requires_synthesis_and_approval(self):
        make_item(self.repo, stage="review", priority=1)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "verify")
        write(self.repo, "reviews/synthesis.md")
        logs.append_event(self.repo, "0001-thing", "review.approved")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "verify")[0]["stage"], "verify")

    def test_ship_and_done_require_evidence_events(self):
        make_item(self.repo, stage="verify", priority=1, journeys="none")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")
        logs.append_event(self.repo, "0001-thing", "verify.green")
        machine.advance(self.repo, "0001-thing", "ship")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "done")
        logs.append_event(self.repo, "0001-thing", "ship.merged")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "done")[0]["stage"], "done")

    def test_review_rework_capped(self):
        make_item(self.repo, stage="review", priority=1)
        write(self.repo, "plan.md", "- [ ] Task 1\n")
        for i in range(2):
            logs.append_event(self.repo, "0001-thing", "review.rejected")
            machine.advance(self.repo, "0001-thing", "implement")
            meta, body = items.load_item(self.repo, "0001-thing")
            meta["stage"] = "review"
            items.save_item(self.repo, meta, body)
        logs.append_event(self.repo, "0001-thing", "review.rejected")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "implement")

    def test_assure_requires_verify_green(self):
        make_item(self.repo, stage="verify", priority=1)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "assure")
        logs.append_event(self.repo, "0001-thing", "verify.green")
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "assure")[0]["stage"], "assure")

    def test_assure_rework_capped(self):
        make_item(self.repo, stage="assure", priority=1)
        write(self.repo, "plan.md", "- [ ] Task 1\n")
        for _ in range(2):
            logs.append_event(self.repo, "0001-thing", "assure.rejected")
            machine.advance(self.repo, "0001-thing", "implement")
            meta, body = items.load_item(self.repo, "0001-thing")
            meta["stage"] = "assure"
            items.save_item(self.repo, meta, body)
        logs.append_event(self.repo, "0001-thing", "assure.rejected")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "implement")

    def test_declaring_none_at_assure_still_advances_to_ship(self):
        make_item(self.repo, stage="assure", priority=1)
        items.set_journeys(self.repo, "0001-thing", "none")
        meta, _ = items.load_item(self.repo, "0001-thing")
        self.assertEqual(machine.next_stage(meta), "ship")
        logs.append_event(self.repo, "0001-thing", "verify.green")
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "ship")[0]["stage"], "ship")


class TestGateCorruption(MachineTest):
    """Item spec 0007 §3: gates fail closed on corrupt evidence lines."""

    def corrupt_line(self, text='{"event": "review.approved", "ts": '):
        log = paths.item_dir(self.repo, "0001-thing") / "log.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(text + "\n")

    def test_corrupt_approval_line_fails_closed(self):
        # The only review.approved "evidence" is a corrupt line: the gate
        # must refuse exactly as if the event were never logged.
        make_item(self.repo, stage="review", priority=1)
        write(self.repo, "reviews/synthesis.md")
        self.corrupt_line()
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "verify")

    def test_valid_approval_beside_corrupt_line_advances(self):
        make_item(self.repo, stage="review", priority=1)
        write(self.repo, "reviews/synthesis.md")
        self.corrupt_line('{"event": "spend", "ts": ')
        logs.append_event(self.repo, "0001-thing", "review.approved")
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "verify")[0]["stage"],
            "verify")

    def test_rejection_cap_counts_parsed_events_only(self):
        # 2 parsed rejections + 1 corrupt rejection line: count is 2, not
        # 3, so review -> implement is still allowed (cap is > 2).
        make_item(self.repo, stage="review", priority=1)
        write(self.repo, "plan.md", "- [ ] Task 1\n")
        logs.append_event(self.repo, "0001-thing", "review.rejected")
        logs.append_event(self.repo, "0001-thing", "review.rejected")
        self.corrupt_line('{"event": "review.rejected", "ts": ')
        meta, _verdict = machine.advance(self.repo, "0001-thing", "implement")
        self.assertEqual(meta["stage"], "implement")

    def test_undecodable_evidence_file_fails_closed(self):
        # Item spec 0009 §1: an undecodable required evidence file is
        # treated exactly like a missing one — GateError, fail closed.
        make_item(self.repo, stage="spec", priority=1)
        spec_md = paths.item_dir(self.repo, "0001-thing") / "spec.md"
        spec_md.write_bytes(b"\xff\xfe binary spec \x80")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "design")

    def test_undecodable_plan_md_fails_closed(self):
        # Same read boundary in _gate_implement: a byte-corrupt plan.md
        # cannot satisfy the '- [ ]' task requirement.
        make_item(self.repo, stage="plan", priority=1)
        plan_md = paths.item_dir(self.repo, "0001-thing") / "plan.md"
        plan_md.write_bytes(b"\xff\xfe- [ ] Task 1\n")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "implement")


def _write_assurance(repo, verdict="pass", journey="J-001", scenario="happy-1",
                     evidence=True, item_id="0001-thing"):
    item_dir = paths.item_dir(repo, item_id)
    ev = []
    if evidence:
        shot = item_dir / "assurance" / "screenshots" / "s1.txt"
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_text("evidence\n", encoding="utf-8")
        ev = [{"type": "screenshot", "path": "assurance/screenshots/s1.txt"}]
    verdicts = {"item": item_id, "journeys": [{
        "id": journey, "surface": "browser",
        "scenarios": [{"id": scenario, "verdict": verdict,
                       "expected": "welcome screen", "actual": "welcome screen",
                       "evidence": ev}]}]}
    vp = item_dir / "assurance" / "verdicts.json"
    vp.parent.mkdir(parents=True, exist_ok=True)
    vp.write_text(json.dumps(verdicts, indent=2), encoding="utf-8")


class TestShipGateAssurance(MachineTest):
    def _to_assure(self, journeys="J-001"):
        meta = make_item(self.repo, stage="assure", priority=1)
        meta, body = items.load_item(self.repo, "0001-thing")
        meta["journeys"] = journeys
        items.save_item(self.repo, meta, body)
        logs.append_event(self.repo, "0001-thing", "implement.completed")
        logs.append_event(self.repo, "0001-thing", "verify.green")

    def test_ship_requires_assure_passed_after_latest_implement(self):
        self._to_assure()
        _write_assurance(self.repo)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "ship")[0]["stage"], "ship")

    def test_stale_assure_passed_from_before_rework_refused(self):
        self._to_assure()
        _write_assurance(self.repo)
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        logs.append_event(self.repo, "0001-thing", "implement.completed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")

    def test_waiver_bypasses_artifact_checks(self):
        self._to_assure()
        logs.append_event(self.repo, "0001-thing", "assure.waived",
                          {"reason": "browser unavailable in CI"})
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "ship")[0]["stage"], "ship")

    def test_failing_verdict_refused(self):
        self._to_assure()
        _write_assurance(self.repo, verdict="fail")
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")

    def test_verdicts_must_cover_declared_journeys(self):
        self._to_assure(journeys="J-001,J-002")
        _write_assurance(self.repo)  # only covers J-001
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")

    def test_missing_evidence_file_refused(self):
        self._to_assure()
        _write_assurance(self.repo)
        shot = paths.item_dir(self.repo, "0001-thing") / "assurance" / "screenshots" / "s1.txt"
        shot.unlink()
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")

    def test_verdicts_must_cover_impact_scenarios(self):
        self._to_assure()
        impact = {"item": "0001-thing", "journeys": [{
            "id": "J-001", "scenarios": [
                {"id": "happy-1", "kind": "happy", "description": "d"},
                {"id": "recovery-1", "kind": "recovery", "description": "d"}]}]}
        ip = paths.item_dir(self.repo, "0001-thing") / "assurance" / "impact.json"
        ip.parent.mkdir(parents=True, exist_ok=True)
        ip.write_text(json.dumps(impact), encoding="utf-8")
        _write_assurance(self.repo)  # only scenario happy-1
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")

    def test_full_shape_impact_with_new_kinds_ships_when_covered(self):
        # empty/error scenario kinds, viewports, and the explicit adjacent
        # declaration are legal impact shapes; coverage stays id-based.
        self._to_assure()
        item_dir = paths.item_dir(self.repo, "0001-thing")
        impact = {"item": "0001-thing", "journeys": [{
            "id": "J-001",
            "nodes_changed": ["N2"], "transitions_changed": ["N2->N3"],
            "new_states": ["saved-empty"],
            "viewports": ["desktop-1280", "mobile-390"],
            "adjacent": {"upstream": ["N1"], "downstream": ["N3"]},
            "scenarios": [
                {"id": "happy-1", "kind": "happy", "description": "d"},
                {"id": "empty-1", "kind": "empty", "description": "d"},
                {"id": "error-1", "kind": "error", "description": "d"}]}]}
        ip = item_dir / "assurance" / "impact.json"
        ip.parent.mkdir(parents=True, exist_ok=True)
        ip.write_text(json.dumps(impact), encoding="utf-8")
        shot = item_dir / "assurance" / "screenshots" / "s1.txt"
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_text("evidence\n", encoding="utf-8")
        ev = [{"type": "screenshot", "path": "assurance/screenshots/s1.txt"}]
        verdicts = {"item": "0001-thing", "journeys": [{
            "id": "J-001", "surface": "browser",
            "scenarios": [
                {"id": s, "verdict": "pass", "expected": "e", "actual": "e",
                 "evidence": ev}
                for s in ("happy-1", "empty-1", "error-1")]}]}
        (item_dir / "assurance" / "verdicts.json").write_text(
            json.dumps(verdicts), encoding="utf-8")
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "ship")[0]["stage"], "ship")

    def test_config_assure_gate_requires_confirmation(self):
        cfg = paths.config_path(self.repo)
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"version": 1, "merge": "auto",
                                   "gates": ["design", "assure"]}), encoding="utf-8")
        self._to_assure()
        _write_assurance(self.repo)
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")
        logs.append_event(self.repo, "0001-thing", "assure.confirmed")
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "ship")[0]["stage"], "ship")

    def test_journeys_none_ship_gate_unchanged(self):
        meta = make_item(self.repo, stage="verify", priority=1)
        meta, body = items.load_item(self.repo, "0001-thing")
        meta["journeys"] = "none"
        items.save_item(self.repo, meta, body)
        logs.append_event(self.repo, "0001-thing", "verify.green")
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "ship")[0]["stage"], "ship")

    def test_absolute_evidence_path_refused(self):
        self._to_assure()
        _write_assurance(self.repo)
        vp = paths.item_dir(self.repo, "0001-thing") / "assurance" / "verdicts.json"
        data = json.loads(vp.read_text(encoding="utf-8"))
        data["journeys"][0]["scenarios"][0]["evidence"] = [
            {"type": "screenshot", "path": "/etc/hosts"}]
        vp.write_text(json.dumps(data), encoding="utf-8")
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")

    def test_dotdot_evidence_path_refused(self):
        self._to_assure()
        _write_assurance(self.repo)
        outside = paths.items_dir(self.repo) / "smuggled.txt"
        outside.write_text("x", encoding="utf-8")
        vp = paths.item_dir(self.repo, "0001-thing") / "assurance" / "verdicts.json"
        data = json.loads(vp.read_text(encoding="utf-8"))
        data["journeys"][0]["scenarios"][0]["evidence"] = [
            {"type": "screenshot", "path": "../smuggled.txt"}]
        vp.write_text(json.dumps(data), encoding="utf-8")
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")

    def test_malformed_impact_shapes_fail_closed(self):
        for payload in ('{"item": "0001-thing", "journeys": "nope"}',
                        '{"item": "0001-thing", "journeys": [42]}',
                        '{"item": "0001-thing", "journeys": [{"id": "J-001", "scenarios": 7}]}'):
            with self.subTest(payload=payload):
                self.tearDown(); self.setUp()
                self._to_assure()
                _write_assurance(self.repo)
                ip = paths.item_dir(self.repo, "0001-thing") / "assurance" / "impact.json"
                ip.parent.mkdir(parents=True, exist_ok=True)
                ip.write_text(payload, encoding="utf-8")
                logs.append_event(self.repo, "0001-thing", "assure.passed")
                with self.assertRaises(machine.GateError):
                    machine.advance(self.repo, "0001-thing", "ship")

    def test_empty_scenarios_refused(self):
        self._to_assure()
        item_dir = paths.item_dir(self.repo, "0001-thing")
        verdicts = {"item": "0001-thing", "journeys": [
            {"id": "J-001", "surface": "browser", "scenarios": []}]}
        vp = item_dir / "assurance" / "verdicts.json"
        vp.parent.mkdir(parents=True, exist_ok=True)
        vp.write_text(json.dumps(verdicts), encoding="utf-8")
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")

    def test_waiver_overrides_failing_artifacts_even_with_passed(self):
        self._to_assure()
        _write_assurance(self.repo, verdict="fail")
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        logs.append_event(self.repo, "0001-thing", "assure.waived",
                          {"reason": "known cosmetic fail; shipping anyway"})
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "ship")[0]["stage"], "ship")

    def test_config_gates_scalar_string_treated_as_no_gates(self):
        cfg = paths.config_path(self.repo)
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"version": 1, "merge": "auto",
                                   "gates": "assure"}), encoding="utf-8")
        self.assertEqual(machine._config_gates(self.repo), [])


class TestCostBreakerSeam(MachineTest):
    """AC20/AC21/AC25: the engine/caller seam, the gate enum, and the
    untouched rejection caps."""

    def seed(self, gates=("design", "cost"), edges=2):
        initrepo.init(self.repo)
        config = json.loads(paths.config_path(self.repo).read_text(
            encoding="utf-8"))
        config["gates"] = list(gates)
        paths.config_path(self.repo).write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        make_item(self.repo, kind="backend", stage="implement", priority=1)
        for i in range(edges):
            logs.append_event(self.repo, "0001-thing", "stage.advance",
                              {"from": "review", "to": "implement"})
        write(self.repo, "plan.md", "- [ ] task\n")

    def test_advance_returns_meta_and_verdict(self):
        self.seed(edges=0)
        # Deviation from the plan's snippet, which omits this: the
        # implement -> review gate needs a factory/<id> branch and an
        # implement.completed event (see
        # test_review_requires_branch_and_completion_event).
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "commit", "-q", "--allow-empty", "-m", "x"],
            cwd=self.repo, check=True,
            env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                     GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
        subprocess.run(["git", "branch", "factory/0001-thing"],
                       cwd=self.repo, check=True)
        logs.append_event(self.repo, "0001-thing", "implement.completed")
        meta, verdict = machine.advance(self.repo, "0001-thing", "review")
        self.assertEqual(meta["stage"], "review")
        self.assertEqual(verdict["stage"], "review")
        self.assertFalse(verdict["fired"])

    def test_firing_transition_is_admitted_and_logs_one_event(self):
        # one pre-existing edge: the pre-count is 1 (< 2), so this
        # transition is admitted and the verdict fires afterwards at 2.
        self.seed(edges=1)
        meta = items.load_item(self.repo, "0001-thing")[0]
        meta["stage"] = "review"
        items.save_item(self.repo, meta, "# Thing\n")
        write(self.repo, "plan.md", "- [ ] task\n")
        meta, verdict = machine.advance(self.repo, "0001-thing", "implement")
        self.assertEqual(meta["stage"], "implement")
        self.assertTrue(verdict["fired"])
        self.assertEqual(verdict["rework_edges"], 2)
        events = logs.read_events(self.repo, "0001-thing")
        self.assertEqual(events[-1]["event"], "cost.breaker")
        self.assertEqual(events[-1]["data"],
                         {"rework_edges": 2, "threshold": 2})
        self.assertEqual(events[-2]["event"], "stage.advance")

    def test_second_entry_past_threshold_is_refused_without_an_answer(self):
        self.seed(edges=2)
        meta = items.load_item(self.repo, "0001-thing")[0]
        meta["stage"] = "waiting-human"
        meta["paused-from"] = "implement"
        meta["paused-reason"] = "cost breaker: 2 rework edges (threshold 2)"
        items.save_item(self.repo, meta, "# Thing\n")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, "0001-thing", "implement")
        self.assertIn("factory cost-answer", str(ctx.exception))
        # the item stays parked: no infinite park/resume loop
        self.assertEqual(
            items.load_item(self.repo, "0001-thing")[0]["stage"],
            "waiting-human")

    def test_gate_off_applies_no_precondition(self):
        self.seed(gates=("design",), edges=2)
        meta = items.load_item(self.repo, "0001-thing")[0]
        meta["stage"] = "waiting-human"
        meta["paused-from"] = "implement"
        items.save_item(self.repo, meta, "# Thing\n")
        meta, verdict = machine.advance(self.repo, "0001-thing", "implement")
        self.assertEqual(meta["stage"], "implement")
        self.assertTrue(verdict["over_threshold"])
        self.assertFalse(verdict["fired"])
        self.assertFalse(verdict["gate"])
        self.assertNotIn(
            "cost.breaker",
            [e["event"] for e in logs.read_events(self.repo, "0001-thing")])

    def test_cost_is_in_the_gates_enum(self):
        schema = json.loads(
            (Path(__file__).resolve().parents[1]
             / "schemas/config.schema.json").read_text(encoding="utf-8"))
        self.assertIn("cost", schema["properties"]["gates"]["items"]["enum"])

    def test_default_config_still_has_exactly_the_design_gate(self):
        self.assertEqual(initrepo.DEFAULT_CONFIG["gates"], ["design"])

    def test_validate_passes_on_a_config_containing_cost(self):
        # Deviation from the plan's `edges=0`: validate_tree also
        # cross-checks the item's stage against its log, and an item
        # seeded at implement with an empty log fails that unrelated
        # check. The two seeded edges are what put it at implement.
        self.seed(edges=2)
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_validate_still_refuses_a_gate_outside_the_enum(self):
        """The enum change must be proven through the real validation
        path, not a raw config write: _config_gates does no schema
        validation, so only validate_tree distinguishes an enum that
        contains "cost" from one that does not."""
        self.seed(gates=("design", "bogus"), edges=2)
        errors = initrepo.validate_tree(self.repo)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("config.gates[1]: 'bogus' not one of", errors[0])
        # the enum the validator actually consulted is the shipped one
        self.assertIn("'cost'", errors[0])

    def test_rejection_caps_are_byte_unchanged(self):
        src = (Path(__file__).resolve().parents[1]
               / "scripts/factory/lib/machine.py").read_text(encoding="utf-8")
        self.assertIn("MAX_REVIEW_REJECTIONS = 2", src)
        self.assertIn("MAX_ASSURE_REJECTIONS = 2", src)
        self.assertIn(
            '    elif frm == "review" and to == "implement":\n'
            '        if logs.count_events(repo, item_id, "review.rejected") '
            '> MAX_REVIEW_REJECTIONS:\n'
            '            raise GateError("review rejected too many times; '
            'move item to blocked")\n'
            '    elif frm == "assure" and to == "implement":\n'
            '        if logs.count_events(repo, item_id, "assure.rejected") '
            '> MAX_ASSURE_REJECTIONS:\n'
            '            raise GateError("assurance rejected too many times; '
            'move item to blocked")\n', src)

    def test_cap_still_refuses_on_a_fourth_rejection_event(self):
        self.seed(gates=("design",), edges=0)
        meta = items.load_item(self.repo, "0001-thing")[0]
        meta["stage"] = "review"
        items.save_item(self.repo, meta, "# Thing\n")
        for _ in range(4):
            logs.append_event(self.repo, "0001-thing", "review.rejected")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, "0001-thing", "implement")
        self.assertIn("review rejected too many times", str(ctx.exception))

    def test_breaker_reaches_the_operator_before_any_cap_could(self):
        """AC25 dominance: the breaker fires at 2 rework edges while the
        cap can only refuse past 2 rejection events — and the fixture run
        logged none, so no cap was ever going to fire on it."""
        self.seed(gates=("design", "cost"), edges=2)
        self.assertEqual(
            logs.count_events(self.repo, "0001-thing", "review.rejected"), 0)
        self.assertEqual(
            logs.count_events(self.repo, "0001-thing", "assure.rejected"), 0)
        meta = items.load_item(self.repo, "0001-thing")[0]
        verdict = breaker.verdict(self.repo, "0001-thing", meta, "implement")
        self.assertTrue(verdict["fired"])
        self.assertLess(verdict["threshold"], machine.MAX_REVIEW_REJECTIONS + 2)

    def test_every_advance_call_site_unpacks_two_values(self):
        root = Path(__file__).resolve().parents[1]
        found = 0
        # Deviation from the plan's literal `"machine.advance(" not in line`:
        # that substring also matches the bare prose form `machine.advance()`
        # in breaker.py's and machine.py's docstrings, which are not call
        # sites. Requiring a first argument keeps every real call site in
        # scope and drops the prose.
        call_site = re.compile(r"machine\.advance\(\s*\w")
        for path in sorted((root / "scripts").rglob("*.py")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not call_site.search(line):
                    continue
                found += 1
                self.assertRegex(
                    line.strip(), r"^\w+,\s*\w+\s*=\s*machine\.advance\(",
                    f"{path}: advance() returns (meta, verdict); this call "
                    "site drops the verdict")
        self.assertGreaterEqual(found, 1)


if __name__ == "__main__":
    unittest.main()
