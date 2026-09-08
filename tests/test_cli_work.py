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


if __name__ == "__main__":
    unittest.main()
