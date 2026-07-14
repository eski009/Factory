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


class CliWorkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(self.repo, "add", "seed.txt")
        _git(self.repo, "commit", "-q", "-m", "seed")
        _git(self.repo, "checkout", "-q", "-b", "factory/0001-thing")
        self.run_cli("init")
        meta = {"id": "0001-thing", "title": "Thing", "stage": "implement",
                "kind": "backend", "created": "2026-07-03T00:00:00Z",
                "updated": "2026-07-03T00:00:00Z"}
        items.save_item(self.repo, meta, "")
        (self.repo / ".factory/items/0001-thing/plan.md").write_text(
            "- [ ] Do the thing\n", encoding="utf-8")
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(self.repo), *args])
        return code, out.getvalue(), err.getvalue()

    def test_work_stub_success_exit_zero(self):
        code, out, err = self.run_cli("work", "0001-thing", "--backend",
                                      "stub", "--worktree", str(self.repo))
        self.assertEqual(code, 0, err)
        self.assertIn("done", out)

    def test_work_json_emits_result(self):
        code, out, err = self.run_cli("work", "0001-thing", "--backend",
                                      "stub", "--worktree", str(self.repo),
                                      "--json")
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["backend"], "stub")

    def test_work_wrong_stage_exit_two(self):
        item_md = self.repo / ".factory/items/0001-thing/item.md"
        item_md.write_text(item_md.read_text().replace(
            "stage: implement", "stage: plan"), encoding="utf-8")
        code, out, err = self.run_cli("work", "0001-thing", "--backend",
                                      "stub", "--worktree", str(self.repo))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
