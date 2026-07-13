import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, paths, pool


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True)


def _init_git_repo(repo):
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-q", "-m", "seed")


def _set_workers(repo, workers):
    cfg_path = repo / ".factory" / "config.json"
    data = json.loads(cfg_path.read_text())
    data["workers"] = workers
    cfg_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")


def _make_item(repo, item_id="0001-thing", stage="implement"):
    meta = {"id": item_id, "title": "Thing", "stage": stage, "kind": "backend",
            "created": "2026-07-03T00:00:00Z", "updated": "2026-07-03T00:00:00Z"}
    items.save_item(repo, meta, "")


class EnsureWorktreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)
        initrepo.init(self.repo)
        # Commit files created by initrepo.init() to keep git status clean
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "init")
        _make_item(self.repo)

    def tearDown(self):
        # remove any worktrees this test created before the dir is torn down
        pool._git(self.repo, "worktree", "prune")
        self.tmp.cleanup()

    def test_creates_worktree_on_factory_branch(self):
        path, created = pool.ensure_worktree(self.repo, "0001-thing")
        self.assertTrue(created)
        self.assertEqual(Path(path),
                         paths.worktree_dir(self.repo, "0001-thing"))
        self.assertTrue(Path(path).is_dir())
        head = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                              cwd=path, capture_output=True, text=True)
        self.assertEqual(head.stdout.strip(), "factory/0001-thing")

    def test_reuses_existing_worktree(self):
        first, _ = pool.ensure_worktree(self.repo, "0001-thing")
        second, created = pool.ensure_worktree(self.repo, "0001-thing")
        self.assertFalse(created)
        self.assertEqual(first, second)

    def test_main_tree_stays_clean(self):
        # .factory/ is gitignored so the nested worktree is invisible
        (self.repo / ".gitignore").write_text(".factory/\n", encoding="utf-8")
        _git(self.repo, "add", ".gitignore")
        _git(self.repo, "commit", "-q", "-m", "ignore factory")
        pool.ensure_worktree(self.repo, "0001-thing")
        status = subprocess.run(["git", "status", "--porcelain"],
                                cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(status.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
