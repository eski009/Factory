"""End-to-end gate walk for one ui item, engine-level (spec §3, §5).

Simulates exactly what the stage skills do: create artifacts, log
evidence events, advance. Proves the pause -> choice -> resume -> plan
path and every gate refusal/pass in order.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import design, dispatch, initrepo, items, logs, machine, paths


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
                                    "stage": "idea", "kind": "ui", "journeys": "none",
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
        # spec -> design (gate: spec.md with Journey impact section)
        self.art("spec.md", "# Spec\n\n## Journey impact\nNone - no customer journey affected.\n")
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
        # verify -> ship -> done
        logs.append_event(self.repo, self.item, "verify.green")
        machine.advance(self.repo, self.item, "ship")
        logs.append_event(self.repo, self.item, "ship.merged")
        meta = machine.advance(self.repo, self.item, "done")
        self.assertEqual(meta["stage"], "done")
        # tree still validates cleanly after the whole journey
        self.assertEqual(initrepo.validate_tree(self.repo), [])
        self.assertIsNone(dispatch.next_item(self.repo))


if __name__ == "__main__":
    unittest.main()
