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


if __name__ == "__main__":
    unittest.main()
