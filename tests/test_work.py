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

    def test_non_dict_retry_is_ignored_keeps_defaults(self):
        _set_workers(self.repo, {"retry": "oops", "codex": 5})
        cfg = work.worker_config(self.repo)
        self.assertEqual(cfg["retry"]["max_attempts"], 3)
        self.assertEqual(cfg["retry"]["base_delay_seconds"], 20)
        self.assertEqual(cfg["codex"]["sandbox"], "workspace-write")


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


class ResolveWorktreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name).resolve()
        _init_git_repo(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_head_on_branch_returns_repo_path(self):
        _git(self.repo, "checkout", "-q", "-b", "factory/0001-thing")
        self.assertEqual(work.resolve_worktree(self.repo, "0001-thing"),
                         str(self.repo))

    def test_branch_exists_but_head_elsewhere_returns_none(self):
        # branch created but never checked out; HEAD stays on the repo's
        # initial default branch
        _git(self.repo, "branch", "factory/0001-thing")
        self.assertIsNone(work.resolve_worktree(self.repo, "0001-thing"))

    def test_no_such_branch_returns_none(self):
        self.assertIsNone(work.resolve_worktree(self.repo, "0001-thing"))


class RunWorkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)
        initrepo.init(self.repo)
        _git(self.repo, "checkout", "-q", "-b", "factory/0001-thing")
        meta = {"id": "0001-thing", "title": "Thing", "stage": "implement",
                "kind": "backend", "created": "2026-07-03T00:00:00Z",
                "updated": "2026-07-03T00:00:00Z"}
        items.save_item(self.repo, meta, "")
        d = self.repo / ".factory/items/0001-thing"
        (d / "plan.md").write_text("- [ ] Do the thing\n", encoding="utf-8")
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        os.environ.pop("FACTORY_WORK_STUB", None)
        self.tmp.cleanup()

    def _events(self):
        return [e["event"] for e in logs.read_events(self.repo, "0001-thing")]

    def test_success_logs_completion_and_measured_spend(self):
        code, result = work.run_work(self.repo, "0001-thing", backend="stub",
                                     worktree=str(self.repo))
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "done")
        self.assertTrue((self.repo / ".factory/items/0001-thing/worker/"
                         "result.json").exists())
        self.assertIn("implement.completed", self._events())
        self.assertIn("spend", self._events())
        # plan checkbox ticked
        plan = (self.repo / ".factory/items/0001-thing/plan.md").read_text()
        self.assertIn("- [x] Do the thing", plan)
        # the spend event is measured and rolls up in cost.summarize
        from scripts.factory.lib import cost
        summary = cost.summarize(self.repo, "0001-thing")
        self.assertEqual(summary["measured"]["events"], 1)

    def test_wrong_stage_refused(self):
        d = self.repo / ".factory/items/0001-thing"
        item_md = d / "item.md"
        item_md.write_text(item_md.read_text().replace(
            "stage: implement", "stage: plan"), encoding="utf-8")
        code, result = work.run_work(self.repo, "0001-thing", backend="stub",
                                     worktree=str(self.repo))
        self.assertEqual(code, 2)
        self.assertNotIn("implement.completed", self._events())

    def test_worker_failure_logs_failed_not_completed(self):
        os.environ["FACTORY_WORK_STUB"] = json.dumps(
            {"exit_code": 1, "commit": False, "reason": "crash"})
        code, result = work.run_work(self.repo, "0001-thing", backend="stub",
                                     worktree=str(self.repo))
        self.assertEqual(code, 3)
        self.assertIn("implement.failed", self._events())
        self.assertNotIn("implement.completed", self._events())

    def test_no_unticked_tasks_refused(self):
        (self.repo / ".factory/items/0001-thing/plan.md").write_text(
            "- [x] done already\n", encoding="utf-8")
        code, result = work.run_work(self.repo, "0001-thing", backend="stub",
                                     worktree=str(self.repo))
        self.assertEqual(code, 2)

    def test_result_has_duration_s(self):
        code, result = work.run_work(self.repo, "0001-thing", backend="stub",
                                     worktree=str(self.repo))
        self.assertEqual(code, 0)
        self.assertIn("duration_s", result)
        self.assertIsInstance(result["duration_s"], int)
        self.assertGreaterEqual(result["duration_s"], 0)


class ChangeEnumTest(unittest.TestCase):
    def test_unusual_git_status_chars_validate(self):
        gstate = {"commits": ["abc123"], "clean": True,
                  "files_changed": [{"path": "a.txt", "change": "U"},
                                    {"path": "b.txt", "change": "X"},
                                    {"path": "c.txt", "change": "B"}]}
        parsed = {"status": "done", "reason": None,
                  "usage": {"input": 1, "output": 1, "total": 2},
                  "summary": "s", "cost_usd": None}
        result = work.normalize("0001-thing", "stub", None,
                                "factory/0001-thing", gstate, parsed, None,
                                "items/0001-thing/worker/worker.log")
        errors = validate.validate(result, initrepo.load_schema("result"),
                                   "result")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
