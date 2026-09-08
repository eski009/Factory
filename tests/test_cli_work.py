import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.factory import factory
from scripts.factory.lib import items, ownership, work
from tests.test_work import (OWNER_BYTES, OWNER_MESSAGE_BYTES,
                             OWNER_EVIDENCE_BYTES, contamination_git,
                             contamination_snapshot, init_contamination_repo,
                             run_owner_payload, contaminate_payload)


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


class CliWorkOwnershipTest(CliWorkTest):
    def test_work_cli_contender_cannot_contaminate_git_or_evidence(self):
        item = "0001-thing"
        with (self.repo / ".git" / "info" / "exclude").open("ab") as exclude:
            exclude.write(b"\n.factory/\ndocs/\n")
        state_path = ownership.owner_state_path(self.repo, item)
        worker_dir = self.repo / ".factory" / "items" / item / "worker"
        owner_path = self.repo / "owner.txt"
        message_path = self.repo / ".git" / "owner-message"
        evidence_path = self.repo / "evidence" / "transient.json"
        canonical_repo = str(self.repo.resolve(strict=True))
        paused = threading.Barrier(2)
        resume_owner = threading.Event()
        owner_codes = []
        owner_errors = []
        owner_backend_snapshots = []
        backend_entries = {"owner": 0, "contender": 0}
        operation_counters = {}
        brief_calls = 0
        owner_thread = None
        oracle_tmp = None
        captured_out = io.StringIO()
        captured_err = io.StringIO()
        real_backend = work.BACKENDS["stub"]
        real_build_brief = work.build_brief

        def worker_artifacts():
            if not worker_dir.exists():
                return {}
            return {
                str(path.relative_to(worker_dir)): path.read_bytes()
                for path in sorted(worker_dir.rglob("*"))
                if path.is_file()
            }

        def current_paused_state():
            return {
                "state": state_path.read_bytes(),
                "worker_artifacts": worker_artifacts(),
                "working": owner_path.read_bytes(),
                "message": message_path.read_bytes(),
                "evidence": evidence_path.read_bytes(),
                "index": contamination_git(
                    self.repo, "diff", "--cached", "--binary"),
                "head": contamination_git(
                    self.repo, "rev-parse", "HEAD"),
                "status": contamination_git(
                    self.repo, "status", "--porcelain=v1"),
                "brief_calls": brief_calls,
                "backend_entries": dict(backend_entries),
            }

        def pause_owner():
            paused.wait(timeout=10)
            if not resume_owner.wait(timeout=10):
                raise AssertionError("timed out waiting to resume CLI owner")

        def backend(brief, worktree, model, timeout, network, sandbox, env,
                    reasoning_effort=None):
            if model == "owner":
                backend_entries["owner"] += 1
                owner_backend_snapshots.append(
                    run_owner_payload(Path(worktree), pause=pause_owner))
            elif model == "contender":
                backend_entries["contender"] += 1
                contaminate_payload(Path(worktree), operation_counters)
            else:
                raise AssertionError(f"unexpected backend model: {model}")
            return {
                "exit_code": 0,
                "stdout": json.dumps({
                    "status": "done",
                    "message": f"{model} done",
                    "usage": {"input": 1, "output": 1, "total": 2},
                }),
                "stderr": "",
                "timed_out": False,
            }

        def observe_build_brief(*args, **kwargs):
            nonlocal brief_calls
            brief_calls += 1
            return real_build_brief(*args, **kwargs)

        owner_args = [
            "--repo", str(self.repo), "work", item, "--backend", "stub",
            "--model", "owner", "--worktree", str(self.repo),
        ]
        contender_args = [
            "--repo", str(self.repo), "work", item, "--backend", "stub",
            "--model", "contender", "--worktree", str(self.repo),
        ]

        def run_owner():
            try:
                owner_codes.append(factory.main(owner_args))
            except BaseException as exc:
                owner_errors.append(exc)

        try:
            oracle_tmp, oracle_repo = init_contamination_repo()
            oracle = run_owner_payload(oracle_repo)
            work.BACKENDS["stub"] = backend
            work.build_brief = observe_build_brief

            with redirect_stdout(captured_out), redirect_stderr(captured_err):
                owner_thread = threading.Thread(target=run_owner)
                owner_thread.start()
                try:
                    paused.wait(timeout=10)
                    before_contender = current_paused_state()
                    contender_stderr_start = len(captured_err.getvalue())
                    contender_code = factory.main(contender_args)
                    contender_stderr = captured_err.getvalue()[
                        contender_stderr_start:]
                    after_contender = current_paused_state()

                    self.assertEqual(contender_code, 2, contender_stderr)
                    self.assertIn(item, contender_stderr)
                    self.assertIn(canonical_repo, contender_stderr)
                    self.assertIn("another implementation owner exists",
                                  contender_stderr)
                    self.assertIn("automatic takeover is unsupported",
                                  contender_stderr)
                    self.assertEqual(backend_entries["contender"], 0)
                    self.assertEqual(operation_counters, {})
                    self.assertEqual(after_contender["brief_calls"],
                                     before_contender["brief_calls"])
                    self.assertEqual(after_contender, before_contender)
                finally:
                    resume_owner.set()
                    owner_thread.join(timeout=10)
        finally:
            resume_owner.set()
            if owner_thread is not None and owner_thread.is_alive():
                owner_thread.join(timeout=10)
            work.BACKENDS["stub"] = real_backend
            work.build_brief = real_build_brief
            if oracle_tmp is not None:
                oracle_tmp.cleanup()

        self.assertIsNotNone(owner_thread)
        self.assertFalse(owner_thread.is_alive())
        self.assertEqual(owner_errors, [])
        self.assertEqual(owner_codes, [0], captured_err.getvalue())
        self.assertEqual(backend_entries["owner"], 1)
        self.assertEqual(backend_entries["contender"], 0)
        self.assertEqual(operation_counters, {})
        self.assertEqual(brief_calls, 1)
        self.assertFalse(state_path.exists())

        final = contamination_snapshot(self.repo)
        core_fields = (
            "working", "index", "show", "evidence", "committed_paths",
            "status",
        )
        for field in core_fields:
            self.assertEqual(final[field], oracle[field], field)
        self.assertEqual(len(owner_backend_snapshots), 1)
        for field in core_fields:
            self.assertEqual(owner_backend_snapshots[0][field],
                             oracle[field], field)

        self.assertEqual(final["working"], OWNER_BYTES)
        self.assertEqual(final["evidence"], OWNER_EVIDENCE_BYTES)
        self.assertEqual(final["show"],
                         OWNER_MESSAGE_BYTES + b"\n\nowner.txt\n")
        self.assertEqual(final["committed_paths"], b"owner.txt\n")
        self.assertFalse((self.repo / "contender.txt").exists())
        self.assertEqual(
            contamination_git(self.repo, "ls-files", "--", "contender.txt"),
            b"",
        )
        self.assertNotIn(b"contender.txt", final["index"])
        self.assertNotIn(b"contender.txt", final["show"])
        self.assertNotIn(b"contender.txt", final["committed_paths"])

    def test_contended_work_exits_two(self):
        worker_dir = self.repo / ".factory/items/0001-thing/worker"
        worker_dir.mkdir(parents=True)
        brief_path = worker_dir / "brief.md"
        sentinel = b"pre-existing brief\x00bytes\n"
        brief_path.write_bytes(sentinel)
        state_path = ownership.owner_state_path(self.repo, "0001-thing")
        backend = mock.Mock(side_effect=AssertionError(
            "contended CLI invoked backend"))
        outer_claim = ownership.acquire(
            self.repo, "0001-thing", supplied=self.repo)
        owner_bytes = state_path.read_bytes()

        try:
            with mock.patch.dict(work.BACKENDS, {"stub": backend}):
                code, out, err = self.run_cli(
                    "work", "0001-thing", "--backend", "stub",
                    "--worktree", str(self.repo))

            self.assertEqual(code, 2, (out, err))
            self.assertIn("0001-thing", err)
            self.assertIn(str(self.repo.resolve(strict=True)), err)
            self.assertIn("another implementation owner exists", err)
            self.assertIn("automatic takeover is unsupported", err)
            self.assertEqual(brief_path.read_bytes(), sentinel)
            backend.assert_not_called()
            self.assertEqual(state_path.read_bytes(), owner_bytes)
        finally:
            outer_claim.release()

        self.assertFalse(state_path.exists())

    def test_identical_work_calls_contend_before_brief_or_backend(self):
        worker_dir = self.repo / ".factory/items/0001-thing/worker"
        worker_dir.mkdir(parents=True)
        brief_path = worker_dir / "brief.md"
        sentinel = b"first owner has not rewritten this\n"
        brief_path.write_bytes(sentinel)
        state_path = ownership.owner_state_path(self.repo, "0001-thing")
        acquired = threading.Barrier(2)
        resume_owner = threading.Event()
        owner_result = []
        owner_errors = []
        real_acquire = ownership.acquire
        backend = mock.Mock(wraps=work.BACKENDS["stub"])

        def acquire_and_pause(*args, **kwargs):
            claim = real_acquire(*args, **kwargs)
            acquired.wait(timeout=5)
            if not resume_owner.wait(timeout=5):
                raise AssertionError("first CLI owner was not resumed")
            return claim

        def run_owner():
            try:
                owner_result.append(self.run_cli(
                    "work", "0001-thing", "--backend", "stub",
                    "--worktree", str(self.repo)))
            except BaseException as exc:
                owner_errors.append(exc)

        with (mock.patch.object(work.ownership, "acquire",
                                side_effect=acquire_and_pause),
              mock.patch.dict(work.BACKENDS, {"stub": backend})):
            owner = threading.Thread(target=run_owner)
            owner.start()
            try:
                acquired.wait(timeout=5)
                owner_bytes = state_path.read_bytes()
                code, out, err = self.run_cli(
                    "work", "0001-thing", "--backend", "stub",
                    "--worktree", str(self.repo))

                self.assertEqual(code, 2, (out, err))
                self.assertIn("another implementation owner exists", err)
                self.assertEqual(brief_path.read_bytes(), sentinel)
                backend.assert_not_called()
                self.assertEqual(state_path.read_bytes(), owner_bytes)
            finally:
                # The nested stdout/stderr capture above is restored before
                # the owner can print and restore its process-global capture.
                resume_owner.set()
                owner.join(timeout=5)

        self.assertFalse(owner.is_alive())
        self.assertEqual(owner_errors, [])
        self.assertEqual(len(owner_result), 1)
        self.assertEqual(owner_result[0][0], 0, owner_result[0][2])
        backend.assert_called_once()
        self.assertFalse(state_path.exists())


class CliWorkOwnershipFailureTest(unittest.TestCase):
    run_cli = CliWorkTest.run_cli

    def setUp(self):
        self._had_work_stub = "FACTORY_WORK_STUB" in os.environ
        self._work_stub = os.environ.get("FACTORY_WORK_STUB")
        CliWorkTest.setUp(self)
        self.item = "0001-thing"

    def tearDown(self):
        try:
            CliWorkTest.tearDown(self)
        finally:
            if self._had_work_stub:
                os.environ["FACTORY_WORK_STUB"] = self._work_stub
            else:
                os.environ.pop("FACTORY_WORK_STUB", None)

    def _events(self):
        item_log = self.repo / ".factory/items" / self.item / "log.jsonl"
        if not item_log.exists():
            return []
        return [json.loads(line)["event"]
                for line in item_log.read_text().splitlines()]

    def _status(self):
        return subprocess.run(
            ["git", "status", "--porcelain"], cwd=self.repo,
            capture_output=True, check=True).stdout

    def test_retained_owner_after_simulated_crash_refuses_without_mutation(
            self):
        worker = self.repo / ".factory/items" / self.item / "worker"
        worker.mkdir(parents=True)
        brief = worker / "brief.md"
        sentinel = b"pre-existing brief\x00bytes\n"
        brief.write_bytes(sentinel)
        state = ownership.owner_state_path(self.repo, self.item)
        item_log = self.repo / ".factory/items" / self.item / "log.jsonl"
        claim = ownership.acquire(self.repo, self.item, supplied=self.repo)
        owner_snapshot = state.read_bytes()
        log_snapshot = item_log.read_bytes() if item_log.exists() else None
        events_snapshot = self._events()
        head_snapshot = work.git_head(self.repo)
        status_snapshot = self._status()
        build_brief = mock.Mock(side_effect=AssertionError(
            "contended CLI built a brief"))
        backend = mock.Mock(side_effect=AssertionError(
            "contended CLI invoked backend"))

        try:
            with (mock.patch.object(work, "build_brief", build_brief),
                  mock.patch.dict(work.BACKENDS, {"stub": backend})):
                code, out, err = self.run_cli(
                    "work", self.item, "--backend", "stub",
                    "--worktree", str(self.repo))

            self.assertEqual(code, 2, (out, err))
            self.assertIn(self.item, err)
            self.assertIn(str(self.repo.resolve(strict=True)), err)
            self.assertIn("another implementation owner exists", err)
            self.assertIn("automatic takeover is unsupported", err)
            build_brief.assert_not_called()
            backend.assert_not_called()
            self.assertEqual(brief.read_bytes(), sentinel)
            self.assertEqual(state.read_bytes(), owner_snapshot)
            self.assertEqual(
                item_log.read_bytes() if item_log.exists() else None,
                log_snapshot)
            self.assertEqual(self._events(), events_snapshot)
            self.assertEqual(work.git_head(self.repo), head_snapshot)
            self.assertEqual(self._status(), status_snapshot)
        finally:
            claim.release()

        self.assertFalse(state.exists())

    def test_release_failure_keeps_artifacts_and_future_attempt_refuses(self):
        os.environ.pop("FACTORY_WORK_STUB", None)
        state = ownership.owner_state_path(self.repo, self.item)
        guard = ownership._release_guard_path(state)
        worker = self.repo / ".factory/items" / self.item / "worker"
        result_path = worker / "result.json"
        before_events = self._events()
        before_head = work.git_head(self.repo)
        real_unlink = ownership.DEFAULT_OPS.unlink
        acquired = {}

        def unlink(path):
            if path == state:
                acquired["owner"] = path.read_bytes()
                raise OSError("retain implementation owner")
            return real_unlink(path)

        with mock.patch.object(ownership.DEFAULT_OPS, "unlink",
                               side_effect=unlink):
            code, out, err = self.run_cli(
                "work", self.item, "--backend", "stub",
                "--worktree", str(self.repo))

        self.assertEqual(code, 1, (out, err))
        self.assertIn("ownership release could not be verified", err)
        self.assertIn("automatic takeover is unsupported", err)
        self.assertEqual(json.loads(result_path.read_text())["status"],
                         "done")
        self.assertEqual(self._events()[len(before_events):],
                         ["spend", "implement.completed"])
        self.assertNotEqual(work.git_head(self.repo), before_head)
        worker_change = self.repo / "worker-change.txt"
        self.assertEqual(worker_change.read_text(), "stub change\n")
        self.assertEqual(state.read_bytes(), acquired["owner"])
        self.assertEqual(guard.read_bytes(), b"release-pending\n")

        plan = self.repo / ".factory/items" / self.item / "plan.md"
        self.assertIn("- [x] Do the thing", plan.read_text())
        plan.write_text(plan.read_text() + "- [ ] Retry thing\n",
                        encoding="utf-8")
        item_log = self.repo / ".factory/items" / self.item / "log.jsonl"
        paths = [state, guard, worker / "brief.md", worker / "worker.log",
                 result_path, item_log]
        file_snapshot = {path: path.read_bytes() for path in paths}
        head_snapshot = work.git_head(self.repo)
        status_snapshot = self._status()
        build_brief = mock.Mock(side_effect=AssertionError(
            "refused retry built a brief"))
        backend = mock.Mock(side_effect=AssertionError(
            "refused retry invoked backend"))
        release = mock.Mock(side_effect=AssertionError(
            "refused retry attempted release"))

        with (mock.patch.object(work, "build_brief", build_brief),
              mock.patch.dict(work.BACKENDS, {"stub": backend}),
              mock.patch.object(work.ownership, "release", release)):
            retry_code, retry_out, retry_err = self.run_cli(
                "work", self.item, "--backend", "stub",
                "--worktree", str(self.repo))

        self.assertEqual(retry_code, 2, (retry_out, retry_err))
        self.assertIn("owner state is invalid", retry_err)
        self.assertIn("automatic takeover is unsupported", retry_err)
        build_brief.assert_not_called()
        backend.assert_not_called()
        release.assert_not_called()
        self.assertEqual({path: path.read_bytes() for path in paths},
                         file_snapshot)
        self.assertEqual(work.git_head(self.repo), head_snapshot)
        self.assertEqual(self._status(), status_snapshot)
        self.assertEqual(worker_change.read_text(), "stub change\n")


if __name__ == "__main__":
    unittest.main()
