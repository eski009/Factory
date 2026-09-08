import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.factory import factory
from scripts.factory.lib import ownership


OWNER_ENV = "FACTORY_IMPLEMENTATION_OWNER"


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True)


class CliOwnershipTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.item = "0001-thing"
        self.had_owner_env = OWNER_ENV in os.environ
        self.old_owner_env = os.environ.get(OWNER_ENV)
        os.environ.pop(OWNER_ENV, None)

        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(self.repo, "add", "seed.txt")
        _git(self.repo, "commit", "-q", "-m", "seed")
        _git(self.repo, "checkout", "-q", "-b", f"factory/{self.item}")
        self.item_dir = self.repo / ".factory" / "items" / self.item
        self.item_dir.mkdir(parents=True)
        self.state = ownership.owner_state_path(self.repo, self.item)

    def tearDown(self):
        if self.had_owner_env:
            os.environ[OWNER_ENV] = self.old_owner_env
        else:
            os.environ.pop(OWNER_ENV, None)
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(self.repo), *args])
        return code, out.getvalue(), err.getvalue()

    def acquire_json(self):
        code, out, err = self.run_cli(
            "ownership", "acquire", self.item,
            "--worktree", str(self.repo), "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        return json.loads(out), out

    def test_acquire_json_returns_token_once_and_digest_only_on_disk(self):
        result, out = self.acquire_json()

        self.assertEqual(set(result), {
            "canonical_worktree", "owner_token", "inherited"})
        self.assertEqual(result["canonical_worktree"], str(self.repo.resolve()))
        self.assertFalse(result["inherited"])
        token = result["owner_token"]
        self.assertTrue(token)
        self.assertEqual(out.count(token), 1)

        raw = self.state.read_bytes()
        record = json.loads(raw)
        self.assertNotIn(token.encode("utf-8"), raw)
        self.assertEqual(record["owner_sha256"], ownership._digest(token))
        self.assertNotIn("owner_token", record)

    def test_release_requires_environment_token(self):
        acquired, _out = self.acquire_json()
        token = acquired["owner_token"]
        digest = ownership._digest(token)
        original = self.state.read_bytes()

        for missing_value in (None, ""):
            with self.subTest(missing_value=missing_value):
                if missing_value is None:
                    os.environ.pop(OWNER_ENV, None)
                else:
                    os.environ[OWNER_ENV] = missing_value
                code, out, err = self.run_cli(
                    "ownership", "release", self.item, "--json")
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertNotIn(token, err)
                self.assertNotIn(digest, err)
                self.assertEqual(self.state.read_bytes(), original)

        os.environ[OWNER_ENV] = token
        code, out, err = self.run_cli(
            "ownership", "release", self.item, "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        self.assertEqual(json.loads(out), {
            "canonical_worktree": str(self.repo.resolve()),
            "released": True,
        })
        self.assertNotIn(token, out)
        self.assertNotIn(digest, out)
        self.assertFalse(self.state.exists())

        os.environ.pop(OWNER_ENV)
        acquired, _out = self.acquire_json()
        token = acquired["owner_token"]
        digest = ownership._digest(token)
        os.environ[OWNER_ENV] = token
        code, out, err = self.run_cli(
            "ownership", "release", self.item)
        self.assertEqual(code, 0, err)
        self.assertNotIn(token, out)
        self.assertNotIn(digest, out)
        self.assertFalse(self.state.exists())

    def test_contender_exits_two_without_token_disclosure(self):
        acquired, _out = self.acquire_json()
        token = acquired["owner_token"]
        digest = ownership._digest(token)
        original = self.state.read_bytes()

        code, out, err = self.run_cli(
            "ownership", "acquire", self.item,
            "--worktree", str(self.repo))

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertNotIn(token, err)
        self.assertNotIn(digest, err)
        self.assertEqual(self.state.read_bytes(), original)

    def test_inherit_exits_zero_without_releasing_outer(self):
        acquired, _out = self.acquire_json()
        token = acquired["owner_token"]
        digest = ownership._digest(token)
        original = self.state.read_bytes()
        os.environ[OWNER_ENV] = token

        code, out, err = self.run_cli(
            "ownership", "acquire", self.item,
            "--worktree", str(self.repo))

        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        self.assertNotIn(token, out)
        self.assertNotIn(digest, out)
        self.assertEqual(self.state.read_bytes(), original)

        code, out, err = self.run_cli(
            "ownership", "acquire", self.item, "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {
            "canonical_worktree": str(self.repo.resolve()),
            "inherited": True,
            "owner_token": token,
        })
        self.assertEqual(self.state.read_bytes(), original)

    def test_check_success_is_read_only_and_hides_credentials(self):
        acquired, _out = self.acquire_json()
        token = acquired["owner_token"]
        digest = ownership._digest(token)
        original = self.state.read_bytes()
        os.environ[OWNER_ENV] = token

        code, out, err = self.run_cli(
            "ownership", "check", self.item, "--json")

        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        self.assertEqual(json.loads(out), {
            "canonical_worktree": str(self.repo.resolve()),
            "owned": True,
        })
        self.assertNotIn(token, out)
        self.assertNotIn(digest, out)
        self.assertEqual(self.state.read_bytes(), original)

    def test_check_failures_are_non_mutating_and_preserve_bytes(self):
        code, out, err = self.run_cli(
            "ownership", "check", self.item, "--json")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertFalse(self.state.exists())

        os.environ[OWNER_ENV] = "candidate-token"

        code, out, err = self.run_cli(
            "ownership", "check", self.item, "--json")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertFalse(self.state.exists())

        malformed = b'{"owner_sha256":"secret"}\ntrailing-bytes\n'
        self.state.write_bytes(malformed)
        code, out, err = self.run_cli(
            "ownership", "check", self.item, "--json")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertEqual(self.state.read_bytes(), malformed)

        self.state.unlink()
        os.environ.pop(OWNER_ENV)
        acquired, _out = self.acquire_json()
        token = acquired["owner_token"]
        state_bytes = self.state.read_bytes()
        os.environ[OWNER_ENV] = "wrong-token"
        code, out, err = self.run_cli(
            "ownership", "check", self.item, "--json")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertNotIn(token, err)
        self.assertNotIn(ownership._digest(token), err)
        self.assertEqual(self.state.read_bytes(), state_bytes)

        guard = ownership._release_guard_path(self.state)
        guard_bytes = b"release-pending\n"
        guard.write_bytes(guard_bytes)
        os.environ[OWNER_ENV] = token
        code, out, err = self.run_cli(
            "ownership", "check", self.item, "--json")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertEqual(self.state.read_bytes(), state_bytes)
        self.assertEqual(guard.read_bytes(), guard_bytes)

    def test_inheritance_never_creates_missing_or_disappearing_state(self):
        os.environ[OWNER_ENV] = "inherited-token"

        code, out, err = self.run_cli(
            "ownership", "acquire", self.item, "--json")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertFalse(self.state.exists())

        os.environ.pop(OWNER_ENV)
        acquired, _out = self.acquire_json()
        os.environ[OWNER_ENV] = acquired["owner_token"]
        original = self.state.read_bytes()

        os.environ[OWNER_ENV] = "wrong-inherited-token"
        code, out, err = self.run_cli(
            "ownership", "acquire", self.item, "--json")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertEqual(self.state.read_bytes(), original)

        os.environ[OWNER_ENV] = acquired["owner_token"]

        class DisappearingOwnershipOps(factory._OwnershipInheritanceOps):
            def read_bytes(self, path):
                path.unlink()
                return path.read_bytes()

        with mock.patch.object(
                factory, "_OwnershipInheritanceOps",
                DisappearingOwnershipOps):
            code, out, err = self.run_cli(
                "ownership", "acquire", self.item, "--json")

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
