import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, validate, work


def _init_repo():
    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    initrepo.init(repo)
    return tmp, repo


def _set_workers(repo, workers):
    cfg_path = repo / ".factory" / "config.json"
    data = json.loads(cfg_path.read_text())
    data["workers"] = workers
    cfg_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")


class WorkerConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.repo = _init_repo()

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_when_absent(self):
        cfg = work.worker_config(self.repo)
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["backend"], "claude")
        self.assertEqual(cfg["max_parallel"], 2)
        self.assertEqual(cfg["network"], "off")
        self.assertEqual(cfg["retry"]["max_attempts"], 3)
        self.assertEqual(cfg["codex"]["sandbox"], "workspace-write")

    def test_overrides_merge_over_defaults(self):
        _set_workers(self.repo, {"enabled": True, "backend": "codex",
                                 "retry": {"max_attempts": 5}})
        cfg = work.worker_config(self.repo)
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["backend"], "codex")
        self.assertEqual(cfg["retry"]["max_attempts"], 5)
        # unspecified nested key keeps its default
        self.assertEqual(cfg["retry"]["base_delay_seconds"], 20)

    def test_valid_workers_block_passes_validation(self):
        _set_workers(self.repo, {"enabled": True, "backend": "claude",
                                 "max_parallel": 3, "network": "off",
                                 "models": {"claude": "claude-sonnet-5"}})
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_bad_backend_enum_rejected(self):
        _set_workers(self.repo, {"backend": "gpt"})
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("backend" in e for e in errors), errors)


class BriefTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.repo = _init_repo()
        meta = {"id": "0001-thing", "title": "Thing", "stage": "implement",
                "kind": "backend", "created": "2026-07-03T00:00:00Z",
                "updated": "2026-07-03T00:00:00Z"}
        items.save_item(self.repo, meta, "")
        d = self.repo / ".factory" / "items" / "0001-thing"
        (d / "plan.md").write_text(
            "# Plan\n- [ ] Add the widget\n- [x] Already done\n- [ ] Wire it up\n",
            encoding="utf-8")
        (d / "spec.md").write_text("Acceptance: widget renders.\n",
                                   encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_unticked_tasks_extracts_only_open(self):
        text = "- [ ] one\n- [x] two\n  - [ ] three\nnot a task\n"
        self.assertEqual(work.unticked_tasks(text), ["one", "three"])

    def test_build_brief_includes_open_tasks_and_spec(self):
        brief = work.build_brief(self.repo, "0001-thing", "/tmp/wt")
        self.assertIn("Add the widget", brief)
        self.assertIn("Wire it up", brief)
        self.assertNotIn("Already done", brief)
        self.assertIn("Acceptance: widget renders.", brief)
        self.assertIn("/tmp/wt", brief)

    def test_build_brief_missing_plan_raises(self):
        (self.repo / ".factory/items/0001-thing/plan.md").unlink()
        with self.assertRaises(work.WorkError):
            work.build_brief(self.repo, "0001-thing", "/tmp/wt")


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


class GitStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_head_returns_sha(self):
        self.assertRegex(work.git_head(self.repo), r"^[0-9a-f]{7,40}$")

    def test_state_reports_new_commit_and_files(self):
        base = work.git_head(self.repo)
        (self.repo / "new.txt").write_text("x\n", encoding="utf-8")
        _git(self.repo, "add", "new.txt")
        _git(self.repo, "commit", "-q", "-m", "add new")
        state = work.git_state(self.repo, base)
        self.assertEqual(len(state["commits"]), 1)
        self.assertIn({"path": "new.txt", "change": "A"},
                      state["files_changed"])
        self.assertTrue(state["clean"])

    def test_state_detects_dirty_tree(self):
        base = work.git_head(self.repo)
        (self.repo / "seed.txt").write_text("changed\n", encoding="utf-8")
        state = work.git_state(self.repo, base)
        self.assertFalse(state["clean"])
        self.assertEqual(state["commits"], [])


class NormalizeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)

    def tearDown(self):
        os.environ.pop("FACTORY_WORK_STUB", None)
        self.tmp.cleanup()

    def test_stub_success_normalizes_to_done(self):
        base = work.git_head(self.repo)
        raw = work.BACKENDS["stub"]("brief", self.repo, None, 60, "off",
                                    "workspace-write", dict(os.environ))
        parsed = work._parse_output("stub", raw)
        gstate = work.git_state(self.repo, base)
        result = work.normalize("0001-thing", "stub", None,
                                "factory/0001-thing", gstate, parsed, None,
                                "items/0001-thing/worker/worker.log")
        self.assertEqual(result["status"], "done")
        self.assertEqual(len(result["commits"]), 1)
        self.assertEqual(result["usage"]["provenance"], "measured")
        # produced result must validate against the schema
        errors = validate.validate(result, initrepo.load_schema("result"),
                                   "result")
        self.assertEqual(errors, [])

    def test_stub_failure_normalizes_to_failed(self):
        os.environ["FACTORY_WORK_STUB"] = json.dumps(
            {"exit_code": 1, "commit": False, "reason": "crash"})
        base = work.git_head(self.repo)
        raw = work.BACKENDS["stub"]("brief", self.repo, None, 60, "off",
                                    "workspace-write", dict(os.environ))
        parsed = work._parse_output("stub", raw)
        gstate = work.git_state(self.repo, base)
        result = work.normalize("0001-thing", "stub", None,
                                "factory/0001-thing", gstate, parsed, None,
                                "items/0001-thing/worker/worker.log")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "crash")

    def test_done_without_commit_becomes_no_changes(self):
        os.environ["FACTORY_WORK_STUB"] = json.dumps(
            {"exit_code": 0, "commit": False})
        base = work.git_head(self.repo)
        raw = work.BACKENDS["stub"]("brief", self.repo, None, 60, "off",
                                    "workspace-write", dict(os.environ))
        parsed = work._parse_output("stub", raw)
        gstate = work.git_state(self.repo, base)
        result = work.normalize("0001-thing", "stub", None,
                                "factory/0001-thing", gstate, parsed, None,
                                "items/0001-thing/worker/worker.log")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "no_changes")


if __name__ == "__main__":
    unittest.main()
