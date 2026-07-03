import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import items, logs, machine, paths


def make_item(repo, kind="ui", stage="idea", priority=None):
    meta = {
        "id": "0001-thing", "title": "Thing", "stage": stage, "kind": kind,
        "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z",
    }
    if priority:
        meta["priority"] = priority
    items.save_item(repo, meta, "# Thing\n")
    return meta


def write(repo, rel, text="content\n"):
    p = paths.item_dir(repo, "0001-thing") / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


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


class TestLegality(MachineTest):
    def test_skipping_ahead_refused(self):
        make_item(self.repo)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")

    def test_advance_idea_to_triage(self):
        make_item(self.repo)
        meta = machine.advance(self.repo, "0001-thing", "triage")
        self.assertEqual(meta["stage"], "triage")
        self.assertEqual(logs.count_events(self.repo, "0001-thing", "stage.advance"), 1)

    def test_pause_and_resume_only_to_paused_from(self):
        make_item(self.repo, stage="design")
        machine.advance(self.repo, "0001-thing", "waiting-human", reason="pick a design")
        meta, _ = items.load_item(self.repo, "0001-thing")
        self.assertEqual(meta["paused-from"], "design")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")
        meta = machine.advance(self.repo, "0001-thing", "design")
        self.assertNotIn("paused-from", meta)


class TestGates(MachineTest):
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
        meta = machine.advance(self.repo, "0001-thing", "spec")
        self.assertEqual(meta["stage"], "spec")

    def test_plan_requires_design_choice_for_ui(self):
        make_item(self.repo, stage="design", priority=1)
        write(self.repo, "spec.md")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")
        write(self.repo, "design/choice.md", "choice: option-b\n")
        meta = machine.advance(self.repo, "0001-thing", "plan")
        self.assertEqual(meta["stage"], "plan")

    def test_implement_requires_plan_with_task(self):
        make_item(self.repo, stage="plan", priority=1)
        write(self.repo, "plan.md", "no tasks here\n")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "implement")
        write(self.repo, "plan.md", "- [ ] Task 1\n")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "implement")["stage"], "implement")

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
        self.assertEqual(machine.advance(self.repo, "0001-thing", "review")["stage"], "review")

    def test_verify_requires_synthesis_and_approval(self):
        make_item(self.repo, stage="review", priority=1)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "verify")
        write(self.repo, "reviews/synthesis.md")
        logs.append_event(self.repo, "0001-thing", "review.approved")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "verify")["stage"], "verify")

    def test_ship_and_done_require_evidence_events(self):
        make_item(self.repo, stage="verify", priority=1)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")
        logs.append_event(self.repo, "0001-thing", "verify.green")
        machine.advance(self.repo, "0001-thing", "ship")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "done")
        logs.append_event(self.repo, "0001-thing", "ship.merged")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "done")["stage"], "done")

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


if __name__ == "__main__":
    unittest.main()
