import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory
from scripts.factory.lib import items


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True)


def _put(repo, item_id, stage, priority):
    meta = {"id": item_id, "title": item_id, "stage": stage, "kind": "backend",
            "created": "2026-07-03T00:00:00Z", "updated": "2026-07-03T00:00:00Z",
            "priority": priority}
    items.save_item(repo, meta, "")


class CliNextCountTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        self.run_cli("init")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(self.repo), *args])
        return code, out.getvalue(), err.getvalue()

    def test_next_count_emits_json_array(self):
        _put(self.repo, "0001-a", "idea", 1)
        _put(self.repo, "0002-b", "spec", 2)
        _put(self.repo, "0003-done", "done", 1)
        code, out, err = self.run_cli("next", "-n", "5", "--json")
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertIsInstance(data, list)
        self.assertEqual([m["id"] for m in data], ["0001-a", "0002-b"])

    def test_next_without_count_stays_single_object(self):
        _put(self.repo, "0001-a", "idea", 1)
        code, out, err = self.run_cli("next", "--json")
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertIsInstance(data, dict)
        self.assertEqual(data["id"], "0001-a")


class CliProvisionCleanupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(self.repo, "add", "seed.txt")
        _git(self.repo, "commit", "-q", "-m", "seed")
        self.run_cli("init")
        meta = {"id": "0001-thing", "title": "Thing", "stage": "implement",
                "kind": "backend", "created": "2026-07-03T00:00:00Z",
                "updated": "2026-07-03T00:00:00Z"}
        items.save_item(self.repo, meta, "")

    def tearDown(self):
        subprocess.run(["git", "worktree", "prune"], cwd=self.repo,
                       capture_output=True, text=True)
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(self.repo), *args])
        return code, out.getvalue(), err.getvalue()

    def test_provision_then_cleanup(self):
        code, out, err = self.run_cli("provision", "0001-thing",
                                      "--backend", "claude", "--json")
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        self.assertTrue(report["prepared"])
        self.assertIn("CLAUDE_CONFIG_DIR", report["config_env"])

        code, out, err = self.run_cli("cleanup", "0001-thing", "--json")
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        self.assertTrue(report["removed"])
        self.assertTrue(report["branch_kept"])

    def test_provision_missing_item_exits_one(self):
        code, out, err = self.run_cli("provision", "9999-nope", "--json")
        self.assertEqual(code, 1)
        report = json.loads(out)
        self.assertFalse(report["prepared"])
        self.assertEqual(report["item"], "9999-nope")


if __name__ == "__main__":
    unittest.main()
