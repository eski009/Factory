"""Item 0013 - assure attribution: merge-base primitives and the ship
gate's ordered attribution rules."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, machine, paths

ITEM = "0001-thing"
OWNER = "0002-stale-restriction-values"
GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, env=GIT_ENV,
                          capture_output=True, text=True).stdout.strip()


class AttributionTest(unittest.TestCase):
    """A factory repo on a real git repo whose integration branch is
    `main` and whose item branch is `factory/0001-thing`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        initrepo.init(self.repo, product="demo")
        git(self.repo, "init", "-q")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "root")
        git(self.repo, "branch", "-M", "main")
        git(self.repo, "branch", f"factory/{ITEM}")
        self.base_sha = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def move_merge_base(self):
        """Advance main AND the item branch so the merge base moves."""
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "second")
        head = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "branch", "-f", f"factory/{ITEM}", head)
        return head


class TestMergeBasePrimitives(AttributionTest):
    def test_default_branch_prefers_origin_head(self):
        git(self.repo, "update-ref", "refs/remotes/origin/main", self.base_sha)
        git(self.repo, "symbolic-ref", "refs/remotes/origin/HEAD",
            "refs/remotes/origin/main")
        self.assertEqual(machine._default_branch(self.repo), "main")

    def test_default_branch_falls_back_to_main(self):
        self.assertEqual(machine._default_branch(self.repo), "main")

    def test_default_branch_falls_back_to_master(self):
        git(self.repo, "branch", "-M", "master")
        self.assertEqual(machine._default_branch(self.repo), "master")

    def test_default_branch_none_when_unresolvable(self):
        git(self.repo, "branch", "-M", "trunk")
        git(self.repo, "branch", "-D", f"factory/{ITEM}")
        self.assertIsNone(machine._default_branch(self.repo))

    def test_default_branch_none_outside_a_git_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(machine._default_branch(Path(tmp)))

    def test_merge_base_returns_forty_hex(self):
        sha = machine._merge_base(self.repo, "main", ITEM)
        self.assertEqual(sha, self.base_sha)
        self.assertRegex(sha, r"^[0-9a-f]{40}$")

    def test_merge_base_none_for_missing_item_branch(self):
        self.assertIsNone(machine._merge_base(self.repo, "main", "0099-nope"))

    def test_merge_base_none_for_missing_branch_argument(self):
        self.assertIsNone(machine._merge_base(self.repo, None, ITEM))

    def test_merge_base_moves_when_both_branches_advance(self):
        moved = self.move_merge_base()
        self.assertNotEqual(moved, self.base_sha)
        self.assertEqual(machine._merge_base(self.repo, "main", ITEM), moved)


if __name__ == "__main__":
    unittest.main()
