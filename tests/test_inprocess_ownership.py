import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory
from scripts.factory.lib import ownership


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


if __name__ == "__main__":
    unittest.main()
