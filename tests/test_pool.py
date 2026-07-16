import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, paths, pool


def fake_jwt(exp):
    import base64, json as _json
    def seg(obj):
        raw = base64.urlsafe_b64encode(_json.dumps(obj).encode()).decode()
        return raw.rstrip("=")
    return f"{seg({'alg': 'none'})}.{seg({'exp': exp})}.sig"


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


class SeedConfigDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)
        initrepo.init(self.repo)
        _make_item(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_claude_seed_writes_trust_state(self):
        wt = str(self.repo / "wt")
        env = pool.seed_config_dir(self.repo, "0001-thing", "claude", wt)
        self.assertIn("CLAUDE_CONFIG_DIR", env)
        cfg = json.loads((Path(env["CLAUDE_CONFIG_DIR"]) / ".claude.json")
                         .read_text())
        self.assertTrue(cfg["hasCompletedOnboarding"])
        key = str(Path(wt).resolve())
        self.assertTrue(cfg["projects"][key]["hasTrustDialogAccepted"])
        self.assertTrue(cfg["projects"][key]["hasCompletedProjectOnboarding"])

    def test_codex_seed_sets_codex_home(self):
        env = pool.seed_config_dir(self.repo, "0001-thing", "codex", "/wt")
        self.assertIn("CODEX_HOME", env)
        self.assertTrue(Path(env["CODEX_HOME"]).is_dir())

    def test_key_mode_home_stays_empty(self):
        # default config (no workers.codex.auth): byte-identical to today's
        # behavior — bare CODEX_HOME return, no auth.json written.
        env = pool.seed_config_dir(self.repo, "0001-thing", "codex", "/wt")
        expected_home = str(pool._worker_home(self.repo, "0001-thing"))
        self.assertEqual(env, {"CODEX_HOME": expected_home})
        self.assertFalse((Path(env["CODEX_HOME"]) / "auth.json").exists())

    def test_stub_backend_has_no_config_env(self):
        self.assertEqual(
            pool.seed_config_dir(self.repo, "0001-thing", "stub", "/wt"), {})


class ChatGptAuthSeedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)
        initrepo.init(self.repo)
        _make_item(self.repo)
        _set_workers(self.repo, {"codex": {"auth": "chatgpt"}})
        self.login_home = tempfile.TemporaryDirectory()
        self._had_codex_home = "CODEX_HOME" in os.environ
        self._old_codex_home = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = self.login_home.name

    def tearDown(self):
        if self._had_codex_home:
            os.environ["CODEX_HOME"] = self._old_codex_home
        else:
            os.environ.pop("CODEX_HOME", None)
        self.login_home.cleanup()
        self.tmp.cleanup()

    def _write_login_auth(self, data):
        (Path(self.login_home.name) / "auth.json").write_text(
            json.dumps(data), encoding="utf-8")

    def test_chatgpt_seed_strips_refresh_and_preserves_unknown_fields(self):
        self._write_login_auth({
            "tokens": {
                "access_token": fake_jwt(int(time.time()) + 7200),
                "refresh_token": "SECRET",
                "account_id": "acc",
            },
            "custom": 1,
        })
        env = pool.seed_config_dir(self.repo, "0001-thing", "codex", "/wt")
        auth_path = Path(env["CODEX_HOME"]) / "auth.json"
        self.assertTrue(auth_path.exists())
        text = auth_path.read_text(encoding="utf-8")
        self.assertNotIn("SECRET", text)
        self.assertNotIn("refresh_token", text)
        data = json.loads(text)
        self.assertEqual(data["tokens"]["account_id"], "acc")
        self.assertEqual(data["custom"], 1)
        self.assertIn("access_token", data["tokens"])

    def test_chatgpt_seed_strips_refresh_inside_lists(self):
        # future auth.json shape drift: a refresh token nested in a
        # list-of-dicts must not survive into the worker home either.
        self._write_login_auth({
            "access_token": fake_jwt(int(time.time()) + 7200),
            "sessions": [{"refresh_token": "SECRET", "label": "keep"}],
        })
        env = pool.seed_config_dir(self.repo, "0001-thing", "codex", "/wt")
        text = (Path(env["CODEX_HOME"]) / "auth.json").read_text(encoding="utf-8")
        self.assertNotIn("SECRET", text)
        self.assertNotIn("refresh_token", text)
        self.assertIn("keep", text)

    def test_chatgpt_seed_accepts_flat_access_token(self):
        self._write_login_auth({"access_token": fake_jwt(int(time.time()) + 7200)})
        env = pool.seed_config_dir(self.repo, "0001-thing", "codex", "/wt")
        self.assertTrue((Path(env["CODEX_HOME"]) / "auth.json").exists())

    def test_chatgpt_seed_refuses_stale_token(self):
        self._write_login_auth({"access_token": fake_jwt(int(time.time()) + 60)})
        with self.assertRaises(pool.CodexAuthError) as ctx:
            pool.seed_config_dir(self.repo, "0001-thing", "codex", "/wt")
        msg = str(ctx.exception).lower()
        self.assertIn("codex", msg)
        self.assertIn("retry", msg)

    def test_chatgpt_seed_refuses_missing_or_undecodable(self):
        with self.assertRaises(pool.CodexAuthError):
            pool.seed_config_dir(self.repo, "0001-thing", "codex", "/wt")
        self._write_login_auth({"access_token": "garbage"})
        with self.assertRaises(pool.CodexAuthError):
            pool.seed_config_dir(self.repo, "0001-thing", "codex", "/wt")

    def test_provision_reports_auth_failure_as_prep_failure(self):
        result = pool.provision(self.repo, "0001-thing", backend="codex")
        self.assertFalse(result["prepared"])
        self.assertIn("detail", result)
        self.assertTrue(result["detail"])


class WorktreeIncludeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)
        initrepo.init(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_copies_listed_files_skips_missing(self):
        (self.repo / ".worktreeinclude").write_text(
            "# secrets\n.env\nmissing.txt\n", encoding="utf-8")
        (self.repo / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
        wt = self.repo / "wt"
        wt.mkdir()
        copied = pool.copy_worktree_includes(self.repo, str(wt))
        self.assertEqual(copied, [".env"])
        self.assertEqual((wt / ".env").read_text(), "TOKEN=abc\n")

    def test_no_include_file_returns_empty(self):
        wt = self.repo / "wt"
        wt.mkdir()
        self.assertEqual(pool.copy_worktree_includes(self.repo, str(wt)), [])

    def test_root_anchored_entry_copied_as_relative(self):
        (self.repo / ".worktreeinclude").write_text("/.env\n", encoding="utf-8")
        (self.repo / ".env").write_text("K=v\n", encoding="utf-8")
        wt = self.repo / "wt"
        wt.mkdir()
        copied = pool.copy_worktree_includes(self.repo, str(wt))
        self.assertEqual(copied, [".env"])
        self.assertEqual((wt / ".env").read_text(), "K=v\n")

    def test_copies_directory_entry(self):
        (self.repo / ".worktreeinclude").write_text("vendor\n", encoding="utf-8")
        (self.repo / "vendor").mkdir()
        (self.repo / "vendor" / "lib.txt").write_text("x\n", encoding="utf-8")
        wt = self.repo / "wt"
        wt.mkdir()
        copied = pool.copy_worktree_includes(self.repo, str(wt))
        self.assertEqual(copied, ["vendor"])
        self.assertEqual((wt / "vendor" / "lib.txt").read_text(), "x\n")


class ProvisionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)
        initrepo.init(self.repo)
        _make_item(self.repo)

    def tearDown(self):
        pool._git(self.repo, "worktree", "prune")
        self.tmp.cleanup()

    def _events(self):
        return [e["event"] for e in logs.read_events(self.repo, "0001-thing")]

    def test_success_prepares_worktree_config_and_logs(self):
        result = pool.provision(self.repo, "0001-thing", backend="claude")
        self.assertTrue(result["prepared"], result)
        self.assertTrue(Path(result["worktree"]).is_dir())
        self.assertIn("CLAUDE_CONFIG_DIR", result["config_env"])
        self.assertIn("prep.completed", self._events())

    def test_worktreeinclude_copied_into_worktree(self):
        (self.repo / ".worktreeinclude").write_text(".env\n", encoding="utf-8")
        (self.repo / ".env").write_text("K=v\n", encoding="utf-8")
        result = pool.provision(self.repo, "0001-thing", backend="claude")
        self.assertIn(".env", result["includes"])
        self.assertTrue((Path(result["worktree"]) / ".env").exists())

    def test_prep_command_runs(self):
        _set_workers(self.repo, {"prep": "echo hi > prepped.txt"})
        result = pool.provision(self.repo, "0001-thing", backend="claude")
        self.assertTrue(result["prepared"])
        self.assertTrue((Path(result["worktree"]) / "prepped.txt").exists())

    def test_prep_failure_reports_prep_failed_and_logs(self):
        _set_workers(self.repo, {"prep": "exit 7"})
        result = pool.provision(self.repo, "0001-thing", backend="claude")
        self.assertFalse(result["prepared"])
        self.assertEqual(result["reason"], "prep_failed")
        self.assertIn("prep.failed", self._events())
        self.assertNotIn("prep.completed", self._events())


class CleanupBackoffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)
        initrepo.init(self.repo)
        _make_item(self.repo)

    def tearDown(self):
        pool._git(self.repo, "worktree", "prune")
        self.tmp.cleanup()

    def test_cleanup_removes_worktree_keeps_branch(self):
        result = pool.provision(self.repo, "0001-thing", backend="claude")
        wt = Path(result["worktree"])
        home = Path(result["config_env"]["CLAUDE_CONFIG_DIR"])
        out = pool.cleanup(self.repo, "0001-thing")
        self.assertTrue(out["removed"])
        self.assertFalse(wt.exists())
        self.assertFalse(home.exists())
        self.assertTrue(out["branch_kept"])
        branch = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet",
             "refs/heads/factory/0001-thing"],
            cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(branch.returncode, 0)

    def test_cleanup_idempotent_when_nothing_to_remove(self):
        out = pool.cleanup(self.repo, "0001-thing")
        self.assertFalse(out["removed"])

    def test_backoff_delay_exponential_and_capped(self):
        self.assertEqual(pool.backoff_delay(0, 20), 20)
        self.assertEqual(pool.backoff_delay(1, 20), 40)
        self.assertEqual(pool.backoff_delay(2, 20), 80)
        self.assertEqual(pool.backoff_delay(10, 20), 300)   # capped
        self.assertEqual(pool.backoff_delay(3, 10, cap=50), 50)


if __name__ == "__main__":
    unittest.main()
