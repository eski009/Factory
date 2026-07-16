"""End-to-end gate walk for one ui item, engine-level (spec §3, §5).

Simulates exactly what the stage skills do: create artifacts, log
evidence events, advance. Proves the pause -> choice -> resume -> plan
path and every gate refusal/pass in order.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import assure, design, dispatch, initrepo, items, logs, machine, paths


def _write_assurance(repo, item_id, verdict="pass", journey="J-001",
                     scenario="happy-1", evidence=True):
    """Stub assurance artifacts under the item dir. Duplicated from
    tests/test_machine.py's helper of the same name -- test files here
    do not import from each other."""
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


class TestUiPipelineWalk(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
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

    def test_full_walk(self):
        # add
        self.item = items.new_item_id(self.repo, "Dark mode")
        now = logs.now_stamp()
        items.save_item(self.repo, {"id": self.item, "title": "Dark mode",
                                    "stage": "idea", "kind": "ui",
                                    "created": now, "updated": now}, "")
        # idea -> triage -> spec (gate: triage.md + priority)
        machine.advance(self.repo, self.item, "triage")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, self.item, "spec")
        self.art("triage.md")
        meta, body = items.load_item(self.repo, self.item)
        meta["priority"] = 1
        items.save_item(self.repo, meta, body)
        machine.advance(self.repo, self.item, "spec")
        # spec -> design (gate: spec.md with Journey impact section, and a
        # declared journey -- this item affects a real customer journey)
        self.art("spec.md", "# Spec\n\n## Journey impact\n"
                            "J-001: affects the checkout confirmation screen.\n")
        items.set_journeys(self.repo, self.item, "J-001")
        machine.advance(self.repo, self.item, "design")
        # design pause -> human choice -> resume -> plan
        machine.advance(self.repo, self.item, "waiting-human",
                        reason="pick a design option")
        self.assertIsNone(dispatch.next_item(self.repo))
        self.assertEqual(dispatch.pending_human(self.repo)[0]["id"], self.item)
        design.record_choice(self.repo, self.item, "b")
        machine.advance(self.repo, self.item, "design")   # resume to paused-from
        machine.advance(self.repo, self.item, "plan")     # gate: choice.md present
        # plan -> implement (gate: checkbox)
        self.art("plan.md", "- [ ] Task 1\n")
        machine.advance(self.repo, self.item, "implement")
        # implement -> review (gate: branch + event)
        subprocess.run(["git", "branch", f"factory/{self.item}"],
                       cwd=self.repo, check=True)
        logs.append_event(self.repo, self.item, "implement.completed")
        machine.advance(self.repo, self.item, "review")
        # review -> verify (gate: synthesis + approval)
        self.art("reviews/synthesis.md")
        logs.append_event(self.repo, self.item, "review.approved")
        machine.advance(self.repo, self.item, "verify")
        # verify -> assure (declared journey routes through assure; gate:
        # verify.green)
        logs.append_event(self.repo, self.item, "verify.green")
        machine.advance(self.repo, self.item, "assure")
        # assure -> ship (gate: verdicts.json covering J-001 with a passing
        # verdict and evidence on disk, plus assure.passed after the
        # latest implementation round)
        _write_assurance(self.repo, self.item)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, self.item, "ship")
        logs.append_event(self.repo, self.item, "assure.passed")
        machine.advance(self.repo, self.item, "ship")
        logs.append_event(self.repo, self.item, "ship.merged")
        meta = machine.advance(self.repo, self.item, "done")
        self.assertEqual(meta["stage"], "done")
        # tree still validates cleanly after the whole journey -- including
        # the assurance/verdicts.json artifact validated against its schema
        self.assertEqual(initrepo.validate_tree(self.repo), [])
        self.assertIsNone(dispatch.next_item(self.repo))

    def test_journeys_none_walk_never_visits_assure(self):
        self.item = items.new_item_id(self.repo, "Backend perf tweak")
        now = logs.now_stamp()
        items.save_item(self.repo, {"id": self.item, "title": "Backend perf tweak",
                                    "stage": "idea", "kind": "backend",
                                    "created": now, "updated": now}, "")
        machine.advance(self.repo, self.item, "triage")
        self.art("triage.md")
        meta, body = items.load_item(self.repo, self.item)
        meta["priority"] = 1
        items.save_item(self.repo, meta, body)
        items.set_journeys(self.repo, self.item, "none")
        machine.advance(self.repo, self.item, "spec")
        self.art("spec.md", "# Spec\n\n## Journey impact\n"
                            "None - no customer journey affected.\n")
        machine.advance(self.repo, self.item, "plan")     # backend skips design
        self.art("plan.md", "- [ ] Task 1\n")
        machine.advance(self.repo, self.item, "implement")
        subprocess.run(["git", "branch", f"factory/{self.item}"],
                       cwd=self.repo, check=True)
        logs.append_event(self.repo, self.item, "implement.completed")
        machine.advance(self.repo, self.item, "review")
        self.art("reviews/synthesis.md")
        logs.append_event(self.repo, self.item, "review.approved")
        machine.advance(self.repo, self.item, "verify")
        logs.append_event(self.repo, self.item, "verify.green")
        machine.advance(self.repo, self.item, "ship")     # verify -> ship directly
        logs.append_event(self.repo, self.item, "ship.merged")
        meta = machine.advance(self.repo, self.item, "done")
        self.assertEqual(meta["stage"], "done")
        advances = [e for e in logs.read_events(self.repo, self.item)
                   if e["event"] == "stage.advance"]
        self.assertTrue(advances)
        for event in advances:
            self.assertNotIn("assure", (event["data"]["from"], event["data"]["to"]))
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_migration_undeclared_item_routes_to_assure_then_waived(self):
        # A legacy item that reached verify before journey-assurance
        # existed carries no `journeys` key at all -- distinct from an
        # item that explicitly opted out with "none".
        self.item = items.new_item_id(self.repo, "Legacy checkout fix")
        now = logs.now_stamp()
        items.save_item(self.repo, {"id": self.item, "title": "Legacy checkout fix",
                                    "stage": "verify", "kind": "ui",
                                    "created": now, "updated": now}, "")
        logs.append_event(self.repo, self.item, "verify.green")
        # the engine still forces the undeclared item through assure
        meta = machine.advance(self.repo, self.item, "assure")
        self.assertEqual(meta["stage"], "assure")
        # ship refuses: no assurance evidence at all yet
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, self.item, "ship")
        assure.record_waiver(self.repo, self.item, "pre-assurance item")
        meta = machine.advance(self.repo, self.item, "ship")
        self.assertEqual(meta["stage"], "ship")
        self.assertEqual(initrepo.validate_tree(self.repo), [])


if __name__ == "__main__":
    unittest.main()
