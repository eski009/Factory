"""End-to-end CLI walk: drive the real factory.py via subprocess exactly
as a stage skill would, over a fresh fixture repo. Proves the CLI contract
(exit codes, stdout, resulting files) for a full ui-item lifecycle. Spec §10.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "scripts" / "factory" / "factory.py"


class TestE2ECli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)
        self.env = dict(os.environ, FACTORY_NOW="2026-07-03T12:00:00Z",
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run(["git", "init", "-q"], cwd=self.target, check=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "root"],
                       cwd=self.target, check=True, env=self.env)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, expect=0):
        result = subprocess.run(
            ["python3", str(CLI), "--repo", str(self.target), *args],
            capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, expect,
                         msg=f"args={args}\nstdout={result.stdout}\nstderr={result.stderr}")
        return result

    def art(self, item, rel, text="content\n"):
        p = self.target / ".factory" / "items" / item / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def _write_assurance(self, item, verdict="pass", journey="J-001",
                         scenario="happy-1"):
        """Stub assurance artifacts under the item dir. Duplicated from
        tests/test_machine.py's helper of the same name -- test files
        here do not import from each other."""
        self.art(item, "assurance/screenshots/s1.txt", "evidence\n")
        verdicts = {"item": item, "journeys": [{
            "id": journey, "surface": "browser",
            "scenarios": [{"id": scenario, "verdict": verdict,
                           "expected": "welcome screen", "actual": "welcome screen",
                           "evidence": [{"type": "screenshot",
                                        "path": "assurance/screenshots/s1.txt"}]}]}]}
        self.art(item, "assurance/verdicts.json", json.dumps(verdicts, indent=2))

    def test_full_cli_lifecycle(self):
        # init + validate
        self.cli("init", "--product", "demo")
        self.cli("validate")
        self.assertEqual(self.cli("doctor", "--json").returncode, 0)
        # add a ui item; it becomes 0001-dark-mode
        out = self.cli("add", "Dark mode", "--kind", "ui").stdout.strip()
        self.assertEqual(out, "0001-dark-mode")
        item = "0001-dark-mode"
        # next selects it
        self.assertIn(item, self.cli("next").stdout)
        # idea -> triage
        self.cli("advance", item, "triage")
        # spec gate refuses without triage.md + priority
        self.cli("advance", item, "spec", expect=2)
        self.art(item, "triage.md")
        # set priority through the CLI (Phase 7), then confirm the tree still
        # validates -- priority.set is gate-neutral -- before the spec gate reads it
        self.cli("priority", item, "1")
        self.cli("journeys", item, "J-001")
        self.cli("validate")
        self.cli("advance", item, "spec")
        # spec -> design
        self.art(item, "spec.md", "# Spec\n\n## Journey impact\n"
                 "J-001: affects the onboarding welcome screen.\n")
        self.cli("advance", item, "design")
        # design gate: pause, choice, resume
        self.cli("advance", item, "waiting-human", "--reason", "pick a design")
        self.assertIn(item, self.cli("packet", item).stdout)  # packet path printed
        self.cli("choice", item, "b", "--notes", "darker header")
        self.assertTrue((self.target / ".factory/items" / item / "design/choice.md").exists())
        self.cli("advance", item, "design")   # resume to paused-from
        self.cli("advance", item, "plan")     # gate: choice.md present
        # plan -> implement
        self.art(item, "plan.md", "- [ ] Task 1\n")
        self.cli("advance", item, "implement")
        # implement -> review (branch + event)
        subprocess.run(["git", "branch", f"factory/{item}"], cwd=self.target, check=True)
        self.cli("log", item, "implement.completed")
        self.cli("advance", item, "review")
        # review -> verify
        self.art(item, "reviews/synthesis.md")
        self.cli("log", item, "review.approved")
        self.cli("advance", item, "verify")
        # verify -> assure (declared journey; gate: verify.green)
        self.cli("log", item, "verify.green")
        self.cli("advance", item, "assure")
        # ship gate refuses without assurance evidence yet
        self.cli("advance", item, "ship", expect=2)
        # assure -> ship (gate: verdicts.json covering J-001 with a passing
        # verdict and evidence on disk, plus assure.passed)
        self._write_assurance(item)
        self.cli("log", item, "assure.passed")
        self.cli("advance", item, "ship")
        self.cli("log", item, "ship.merged")
        self.cli("advance", item, "done")
        # final state: done, tree valid, nothing actionable, council usable
        rows = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual(rows[0]["stage"], "done")
        self.cli("validate")
        self.assertIn("nothing actionable", self.cli("next").stdout)
        # council firewall end to end via CLI
        bid = self.cli("bid", "product", "onboarding", "Users drop at step 2",
                       "--evidence", "docs/factory/brain/users.md",
                       "--surface", "brain/vision.md", "--severity", "medium").stdout.strip()
        self.assertEqual(bid, "bid-0001")
        self.cli("bid", "intern", "onboarding", "bad", "--evidence", "x",
                 "--surface", "brain/vision.md", "--severity", "low", expect=2)  # unknown agent -> business-rule refusal
        self.cli("judge", "bid-0001", "accept", "--reason", "clear signal",
                 "--surface", "brain/vision.md", "--anchor", "## Onboarding")
        rep = json.loads(self.cli("reputation", "--json").stdout)
        self.assertEqual(rep["product/onboarding"], 0.05)
        self.cli("validate")   # ledgers consistent after a real bid+judge

    def test_backend_item_skips_design(self):
        self.cli("init")
        item = self.cli("add", "Add index", "--kind", "backend").stdout.strip()
        self.cli("advance", item, "triage")
        self.art(item, "triage.md")
        item_md = self.target / ".factory/items" / item / "item.md"
        item_md.write_text(item_md.read_text().replace(
            "kind: backend", "kind: backend\npriority: 1"), encoding="utf-8")
        self.cli("advance", item, "spec")
        self.art(item, "spec.md", "# Spec\n\n## Journey impact\nNone - no customer journey affected.\n")
        self.cli("journeys", item, "none")
        # backend jumps spec -> plan (no design); design is an illegal transition
        self.cli("advance", item, "design", expect=2)
        self.cli("advance", item, "plan")
        # choice refused for a backend item
        self.cli("choice", item, "a", expect=2)
        # plan -> implement -> review -> verify -> ship -> done: a
        # `journeys: none` item skips assure entirely, verify -> ship direct
        self.art(item, "plan.md", "- [ ] Task 1\n")
        self.cli("advance", item, "implement")
        subprocess.run(["git", "branch", f"factory/{item}"], cwd=self.target, check=True)
        self.cli("log", item, "implement.completed")
        self.cli("advance", item, "review")
        self.art(item, "reviews/synthesis.md")
        self.cli("log", item, "review.approved")
        self.cli("advance", item, "verify")
        self.cli("log", item, "verify.green")
        self.cli("advance", item, "ship")     # verify -> ship directly, no assure
        self.cli("log", item, "ship.merged")
        self.cli("advance", item, "done")
        self.cli("validate")
        log_path = self.target / ".factory/items" / item / "log.jsonl"
        events = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        advances = [e for e in events if e["event"] == "stage.advance"]
        self.assertTrue(advances)
        for event in advances:
            self.assertNotIn("assure", (event["data"]["from"], event["data"]["to"]))

    def test_migration_undeclared_item_waived_via_cli(self):
        # A legacy item that reached verify before journey-assurance
        # existed: no `journeys` frontmatter field at all (distinct from
        # an item that explicitly opted out with "none"). Simulated by
        # hand-editing the fixture the way a pre-existing repo would look,
        # then driving the rest of the walk through the real CLI.
        self.cli("init")
        item = self.cli("add", "Legacy checkout fix", "--kind", "ui").stdout.strip()
        item_md = self.target / ".factory/items" / item / "item.md"
        item_md.write_text(item_md.read_text().replace(
            "stage: idea", "stage: verify"), encoding="utf-8")
        self.cli("log", item, "stage.advance",
                 "--data", json.dumps({"from": "idea", "to": "verify"}))
        self.cli("log", item, "verify.green")
        self.cli("validate")
        # the engine still forces the undeclared item through assure
        self.cli("advance", item, "assure")
        # ship refuses: no assurance evidence at all yet
        self.cli("advance", item, "ship", expect=2)
        self.cli("waive", item, "--reason", "pre-assurance item")
        self.cli("advance", item, "ship")
        self.cli("log", item, "ship.merged")
        self.cli("advance", item, "done")
        self.cli("validate")


if __name__ == "__main__":
    unittest.main()
