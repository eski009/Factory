import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory
from scripts.factory.lib import ownership
from tests.test_work import (OWNER_BYTES, OWNER_EVIDENCE_BYTES,
                             OWNER_MESSAGE_BYTES, contaminate_payload,
                             contamination_git, init_contamination_repo,
                             run_owner_payload)


class InProcessOwnershipTests(unittest.TestCase):
    def setUp(self):
        self._saved_owner = os.environ.get("FACTORY_IMPLEMENTATION_OWNER")
        self._had_owner = "FACTORY_IMPLEMENTATION_OWNER" in os.environ
        os.environ.pop("FACTORY_IMPLEMENTATION_OWNER", None)
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.worktree = Path(self._temporary_directory.name)
        subprocess.run(["git", "init"], cwd=self.worktree, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "factory@example.invalid"],
            cwd=self.worktree,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Factory Test"],
            cwd=self.worktree,
            check=True,
        )
        (self.worktree / "seed").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "seed"], cwd=self.worktree, check=True)
        subprocess.run(
            ["git", "commit", "-m", "seed"],
            cwd=self.worktree,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "-b", "factory/0001-thing"],
            cwd=self.worktree,
            check=True,
            capture_output=True,
        )
        (self.worktree / ".factory" / "items" / "0001-thing").mkdir(parents=True)
        self.state = ownership.owner_state_path(self.worktree, "0001-thing")

    def tearDown(self):
        if self._had_owner:
            os.environ["FACTORY_IMPLEMENTATION_OWNER"] = self._saved_owner
        else:
            os.environ.pop("FACTORY_IMPLEMENTATION_OWNER", None)
        self._temporary_directory.cleanup()

    def run_cli(self, arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = factory.main(["--repo", str(self.worktree), *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def acquire_outer(self):
        code, stdout, stderr = self.run_cli(
            [
                "ownership",
                "acquire",
                "0001-thing",
                "--worktree",
                str(self.worktree),
                "--json",
            ]
        )
        self.assertEqual(code, 0, stderr)
        token = json.loads(stdout)["owner_token"]
        os.environ["FACTORY_IMPLEMENTATION_OWNER"] = token
        return token

    def observe(self, boundary, token, observations):
        code, stdout, stderr = self.run_cli(
            [
                "ownership",
                "check",
                "0001-thing",
                "--worktree",
                str(self.worktree),
                "--json",
            ]
        )
        self.assertEqual(code, 0, stderr)
        json.loads(stdout)
        self.assertTrue(self.state.exists())
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(state["owner_sha256"], ownership._digest(token))
        observations.append((boundary, ownership._digest(token)))

    def test_owner_survives_all_inprocess_boundaries_until_release(self):
        token = self.acquire_outer()
        observations = []

        def implementer():
            self.observe("implementer", token, observations)

        def reviewer():
            self.observe("reviewer", token, observations)

        def cleanup():
            self.observe("cleanup", token, observations)

        def tick_plan():
            self.observe("tick_plan", token, observations)

        def write_task_evidence():
            self.observe("write_task_evidence", token, observations)

        implementer()
        reviewer()
        cleanup()
        tick_plan()
        write_task_evidence()

        digest = ownership._digest(token)
        self.assertEqual(
            observations,
            [
                ("implementer", digest),
                ("reviewer", digest),
                ("cleanup", digest),
                ("tick_plan", digest),
                ("write_task_evidence", digest),
            ],
        )
        self.assertTrue(self.state.exists())
        code, _, stderr = self.run_cli(
            [
                "ownership",
                "release",
                "0001-thing",
                "--worktree",
                str(self.worktree),
                "--json",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertFalse(self.state.exists())

    def test_nested_completion_does_not_release_outer_claim(self):
        token = self.acquire_outer()
        state_bytes = self.state.read_bytes()

        code, stdout, stderr = self.run_cli(
            [
                "ownership",
                "acquire",
                "0001-thing",
                "--worktree",
                str(self.worktree),
                "--json",
            ]
        )
        self.assertEqual(code, 0, stderr)
        nested_acquisition = json.loads(stdout)
        self.assertTrue(nested_acquisition["inherited"])
        self.assertEqual(nested_acquisition["owner_token"], token)
        self.assertEqual(self.state.read_bytes(), state_bytes)

        def complete_nested(acquisition):
            if not acquisition["inherited"]:
                release_code, _, release_stderr = self.run_cli(
                    [
                        "ownership",
                        "release",
                        "0001-thing",
                        "--worktree",
                        str(self.worktree),
                        "--json",
                    ]
                )
                self.assertEqual(release_code, 0, release_stderr)

        complete_nested(nested_acquisition)
        self.assertEqual(self.state.read_bytes(), state_bytes)

        observations = []
        self.observe("write_task_evidence", token, observations)
        self.assertTrue(self.state.exists())

        code, _, stderr = self.run_cli(
            [
                "ownership",
                "release",
                "0001-thing",
                "--worktree",
                str(self.worktree),
                "--json",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertFalse(self.state.exists())

    def test_contender_cannot_mutate_during_inprocess_boundaries(self):
        token = self.acquire_outer()
        state_bytes = self.state.read_bytes()
        mutation_count = [0]
        observations = []
        paused = threading.Barrier(2)
        resume = threading.Event()
        errors = []

        def implementer():
            self.observe("implementer", token, observations)
            paused.wait(timeout=10)
            if not resume.wait(timeout=10):
                raise AssertionError("timed out waiting to resume")

        def reviewer():
            self.observe("reviewer", token, observations)

        def cleanup():
            self.observe("cleanup", token, observations)

        def tick_plan():
            self.observe("tick_plan", token, observations)

        def write_task_evidence():
            self.observe("write_task_evidence", token, observations)

        def contender():
            mutation_count[0] += 1

        def owner():
            try:
                implementer()
                reviewer()
                cleanup()
                tick_plan()
                write_task_evidence()
                code, _, stderr = self.run_cli(
                    [
                        "ownership",
                        "release",
                        "0001-thing",
                        "--worktree",
                        str(self.worktree),
                        "--json",
                    ]
                )
                self.assertEqual(code, 0, stderr)
                self.assertFalse(self.state.exists())
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=owner)
        thread.start()
        contender_stderr = ""
        try:
            paused.wait(timeout=10)
            os.environ.pop("FACTORY_IMPLEMENTATION_OWNER", None)
            try:
                code, _, contender_stderr = self.run_cli(
                    [
                        "ownership",
                        "acquire",
                        "0001-thing",
                        "--worktree",
                        str(self.worktree),
                        "--json",
                    ]
                )
            finally:
                os.environ["FACTORY_IMPLEMENTATION_OWNER"] = token
            if code == 0:
                contender()
            self.assertEqual(code, 2)
            self.assertEqual(mutation_count, [0])
            self.assertEqual(self.state.read_bytes(), state_bytes)
        finally:
            resume.set()
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        digest = ownership._digest(token)
        self.assertEqual(
            observations,
            [
                ("implementer", digest),
                ("reviewer", digest),
                ("cleanup", digest),
                ("tick_plan", digest),
                ("write_task_evidence", digest),
            ],
        )
        self.assertFalse(self.state.exists())
        self.assertNotIn(token, contender_stderr)
        self.assertNotIn(digest, contender_stderr)


class InProcessContaminationTest(unittest.TestCase):
    def test_inprocess_contender_cannot_contaminate_commit_or_evidence(self):
        owned_tmp, repo = init_contamination_repo()
        oracle_tmp = None
        thread = None
        resume = threading.Event()
        try:
            item = "0001-thing"
            (repo / ".factory" / "items" / item).mkdir(parents=True)
            with (repo / ".git" / "info" / "exclude").open("ab") as exclude:
                exclude.write(b"\n.factory/\n")
            state = ownership.owner_state_path(repo, item)
            canonical_repo = str(repo.resolve())
            factory_cli = (Path(__file__).resolve().parents[1]
                           / "scripts" / "factory" / "factory.py")

            def run_cli(action, owner_token=None):
                environment = os.environ.copy()
                environment.pop("FACTORY_IMPLEMENTATION_OWNER", None)
                if owner_token is not None:
                    environment["FACTORY_IMPLEMENTATION_OWNER"] = owner_token
                return subprocess.run(
                    [
                        sys.executable,
                        str(factory_cli),
                        "--repo",
                        str(repo),
                        "ownership",
                        action,
                        item,
                        "--worktree",
                        str(repo),
                        "--json",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    env=environment,
                )

            acquired = run_cli("acquire")
            self.assertEqual(acquired.returncode, 0, acquired.stderr)
            owner_token = json.loads(acquired.stdout)["owner_token"]
            owner_digest = ownership._digest(owner_token)
            owner_state_bytes = state.read_bytes()

            oracle_tmp, oracle_repo = init_contamination_repo()
            oracle = run_owner_payload(oracle_repo)

            paused = threading.Barrier(2)
            finished = threading.Event()
            errors = []
            final_snapshots = []
            boundary_observations = []

            def pause_owner():
                paused.wait(timeout=10)
                if not resume.wait(timeout=10):
                    raise AssertionError("timed out waiting to resume owner")

            def owner():
                try:
                    final_snapshot = run_owner_payload(repo, pause=pause_owner)
                    for boundary in (
                            "implementer", "reviewer", "cleanup", "plan",
                            "evidence"):
                        checked = run_cli("check", owner_token)
                        self.assertEqual(
                            checked.returncode, 0,
                            f"{boundary}: {checked.stderr}")
                        self.assertTrue(state.exists(), boundary)
                        self.assertEqual(
                            state.read_bytes(), owner_state_bytes, boundary)
                        boundary_observations.append(boundary)
                    final_snapshots.append(final_snapshot)
                    released = run_cli("release", owner_token)
                    self.assertEqual(released.returncode, 0, released.stderr)
                    self.assertFalse(state.exists())
                except BaseException as error:
                    errors.append(error)
                finally:
                    finished.set()

            thread = threading.Thread(target=owner)
            thread.start()
            counters = {}
            try:
                paused.wait(timeout=10)
                owner_path = repo / "owner.txt"
                pending_path = repo / ".git" / "owner-message"
                evidence_path = repo / "evidence" / "transient.json"
                before_contender = {
                    "state": state.read_bytes(),
                    "working": owner_path.read_bytes(),
                    "message": pending_path.read_bytes(),
                    "evidence": evidence_path.read_bytes(),
                    "index": contamination_git(
                        repo, "diff", "--cached", "--binary"),
                }

                contender = run_cli("acquire")
                if contender.returncode == 0:
                    contaminate_payload(repo, counters)

                self.assertEqual(contender.returncode, 2)
                self.assertEqual(counters, {})
                self.assertIn(item, contender.stderr)
                self.assertIn(canonical_repo, contender.stderr)
                self.assertIn(
                    "another implementation owner exists", contender.stderr)
                self.assertIn(
                    "automatic takeover is unsupported", contender.stderr)
                self.assertNotIn(owner_token, contender.stderr)
                self.assertNotIn(owner_digest, contender.stderr)
                self.assertEqual(state.read_bytes(), before_contender["state"])
                self.assertEqual(
                    owner_path.read_bytes(), before_contender["working"])
                self.assertEqual(
                    pending_path.read_bytes(), before_contender["message"])
                self.assertEqual(
                    evidence_path.read_bytes(), before_contender["evidence"])
                self.assertEqual(
                    contamination_git(repo, "diff", "--cached", "--binary"),
                    before_contender["index"])
            finally:
                resume.set()
                thread.join(timeout=10)

            self.assertFalse(thread.is_alive())
            self.assertTrue(finished.is_set())
            self.assertEqual(errors, [])
            self.assertEqual(
                boundary_observations,
                ["implementer", "reviewer", "cleanup", "plan", "evidence"],
            )
            self.assertEqual(len(final_snapshots), 1)
            final = final_snapshots[0]
            for field in (
                    "working", "index", "show", "evidence",
                    "committed_paths"):
                self.assertEqual(final[field], oracle[field], field)
            self.assertEqual(final["working"], OWNER_BYTES)
            self.assertEqual(final["evidence"], OWNER_EVIDENCE_BYTES)
            self.assertIn(OWNER_MESSAGE_BYTES, final["show"])
            self.assertEqual(final["committed_paths"], b"owner.txt\n")
            self.assertFalse((repo / "contender.txt").exists())
            self.assertEqual(
                contamination_git(repo, "ls-files", "--", "contender.txt"),
                b"",
            )
            self.assertNotIn(b"contender.txt", final["index"])
            self.assertNotIn(b"contender.txt", final["show"])
            self.assertNotIn(b"contender.txt", final["committed_paths"])
            self.assertEqual(final["status"], oracle["status"])
            self.assertFalse(state.exists())
        finally:
            resume.set()
            if thread is not None and thread.is_alive():
                thread.join(timeout=10)
            if oracle_tmp is not None:
                oracle_tmp.cleanup()
            owned_tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
