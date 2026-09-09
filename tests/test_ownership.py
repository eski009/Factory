import json
import os
import shutil
import stat
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from scripts.factory.lib import initrepo, items, logs, ownership, safeio


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True)


class OwnershipFixture(unittest.TestCase):
    item = "0001-thing"
    other_item = "0002-other"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name).resolve()
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@example.test")
        _git(self.repo, "config", "user.name", "Ownership Test")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(self.repo, "add", "seed.txt")
        _git(self.repo, "commit", "-q", "-m", "seed")
        _git(self.repo, "checkout", "-q", "-b", f"factory/{self.item}")
        initrepo.init(self.repo)
        for item_id in (self.item, self.other_item):
            items.save_item(self.repo, {
                "id": item_id,
                "title": item_id,
                "stage": "implement",
                "kind": "backend",
                "created": "2026-09-07T00:00:00Z",
                "updated": "2026-09-07T00:00:00Z",
            }, "")
        self.other_worktree = self.repo / ".factory/worktrees" / self.other_item
        self.other_worktree.parent.mkdir(parents=True, exist_ok=True)
        _git(self.repo, "worktree", "add", "-q", "-b",
             f"factory/{self.other_item}", str(self.other_worktree))
        self.state_path = ownership.owner_state_path(self.repo, self.item)

    def tearDown(self):
        self.tmp.cleanup()


class CanonicalWorktreeTest(OwnershipFixture):
    def test_relative_absolute_and_symlink_spellings_share_identity(self):
        alias = self.repo / "checkout-alias"
        alias.symlink_to(self.repo, target_is_directory=True)

        expected = self.repo.resolve(strict=True)
        spellings = (Path("."), self.repo, alias, Path("checkout-alias"))
        resolved = [ownership.canonical_worktree(
            self.repo, self.item, supplied) for supplied in spellings]

        self.assertTrue(all(isinstance(path, Path) for path in resolved))
        self.assertEqual(resolved, [expected] * len(spellings))

    def test_mismatched_and_unregistered_supplied_checkouts_refuse(self):
        unregistered = self.repo / "unregistered-checkout"
        unregistered.mkdir()
        for supplied in (self.other_worktree, unregistered):
            with self.subTest(supplied=supplied):
                with self.assertRaisesRegex(
                        ownership.OwnershipRefusal,
                        "supplied checkout is not the registered checkout"):
                    ownership.canonical_worktree(
                        self.repo, self.item, supplied)

    def test_duplicate_registration_refuses_before_resolving_aliases(self):
        alias = self.repo / "checkout-alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        listing = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=(
                b"worktree " + os.fsencode(self.repo) + b"\0"
                b"branch refs/heads/factory/" + self.item.encode() + b"\0\0"
                b"worktree " + os.fsencode(alias) + b"\0"
                b"branch refs/heads/factory/" + self.item.encode() + b"\0\0"),
            stderr=b"")

        with mock.patch.object(ownership.subprocess, "run",
                               return_value=listing), \
                mock.patch.object(
                    Path, "resolve",
                    side_effect=AssertionError("aliases were resolved")) \
                as resolve:
            with self.assertRaisesRegex(ownership.OwnershipRefusal,
                                        "ambiguous"):
                ownership.canonical_worktree(self.repo, self.item)
        resolve.assert_not_called()

    def test_zero_registration_has_typed_refusal(self):
        with self.assertRaises(ownership.NoRegisteredWorktree) as context:
            ownership.canonical_worktree(self.repo, "0099-unregistered")
        self.assertIsInstance(context.exception, ownership.OwnershipRefusal)
        self.assertIn("no registered checkout", str(context.exception))

    def test_git_lookup_failures_refuse_instead_of_looking_unregistered(self):
        failures = (
            subprocess.CompletedProcess(
                args=[], returncode=128, stdout=b"", stderr=b"not a repo"),
            OSError("git unavailable"),
        )
        for failure in failures:
            with self.subTest(failure=failure):
                effect = ({"return_value": failure}
                          if isinstance(failure, subprocess.CompletedProcess)
                          else {"side_effect": failure})
                with mock.patch.object(ownership.subprocess, "run", **effect):
                    with self.assertRaisesRegex(
                            ownership.OwnershipRefusal,
                            "git worktree lookup failed") as context:
                        ownership.canonical_worktree(self.repo, self.item)
                self.assertNotIsInstance(
                    context.exception, ownership.NoRegisteredWorktree)

    def test_registered_checkout_resolution_failure_refuses(self):
        missing = self.repo / "missing-checkout"
        listing = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=(b"worktree " + os.fsencode(missing) + b"\0"
                    b"branch refs/heads/factory/" + self.item.encode()
                    + b"\0\0"),
            stderr=b"")
        with mock.patch.object(ownership.subprocess, "run",
                               return_value=listing):
            with self.assertRaisesRegex(
                    ownership.OwnershipRefusal,
                    "registered checkout.*cannot be resolved") as context:
                ownership.canonical_worktree(self.repo, self.item)
        self.assertNotIsInstance(context.exception,
                                 ownership.NoRegisteredWorktree)


class OwnershipPrimitiveTest(OwnershipFixture):
    def test_public_read_only_verifier_returns_canonical_owner_identity(self):
        claim = ownership.acquire(self.repo, self.item)
        try:
            before = self.state_path.read_bytes()
            verified = ownership.verify(
                self.repo, self.item, claim.token, supplied=self.repo)
            self.assertEqual(verified.checkout, claim.checkout)
            self.assertEqual(verified.owner_sha256,
                             ownership.owner_digest(claim.token))
            self.assertEqual(self.state_path.read_bytes(), before)
            with self.assertRaises(ownership.OwnershipRefusal):
                ownership.verify(self.repo, self.item, "wrong")
            self.assertEqual(self.state_path.read_bytes(), before)
        finally:
            claim.release()

    def test_owner_state_symlink_is_never_followed_by_any_public_operation(self):
        claim = ownership.acquire(self.repo, self.item)
        backing = self.state_path.with_name("owner-state-backing.json")
        verified = ownership.verify(self.repo, self.item, claim.token)
        try:
            operations = {
                "acquire": lambda: ownership.acquire(
                    self.repo, self.item, owner_token=claim.token),
                "verify": lambda: ownership.verify(
                    self.repo, self.item, claim.token),
                "revalidate": lambda: ownership.revalidate(verified),
                "release": lambda: ownership.release(
                    self.repo, self.item, claim.checkout, claim.token),
            }
            for label, operation in operations.items():
                with self.subTest(operation=label):
                    self.state_path.rename(backing)
                    self.state_path.symlink_to(backing.name)
                    try:
                        with self.assertRaisesRegex(
                                ownership.OwnershipRefusal, "owner state"):
                            operation()
                    finally:
                        self.state_path.unlink()
                        backing.rename(self.state_path)
        finally:
            if self.state_path.is_symlink():
                self.state_path.unlink()
            if backing.exists():
                backing.rename(self.state_path)
            claim.release()

    def test_owner_state_fifo_refuses_without_blocking(self):
        os.mkfifo(self.state_path)
        source = r'''
import sys
from pathlib import Path
from scripts.factory.lib import ownership
try:
    ownership.acquire(Path(sys.argv[1]), sys.argv[2])
except ownership.OwnershipRefusal:
    raise SystemExit(0)
raise SystemExit(2)
'''
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        try:
            completed = subprocess.run(
                ["python3", "-c", source, str(self.repo), self.item],
                cwd=Path(__file__).resolve().parents[1], env=environment,
                capture_output=True, text=True, timeout=1)
        except subprocess.TimeoutExpired:
            self.fail("owner-state FIFO inspection blocked")
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_dangling_release_guard_refuses_acquire(self):
        guard = ownership._release_guard_path(self.state_path)
        guard.symlink_to("missing-release-guard-target")
        try:
            with self.assertRaisesRegex(
                    ownership.OwnershipRefusal, "owner state"):
                ownership.acquire(self.repo, self.item)
            self.assertFalse(self.state_path.exists())
        finally:
            if self.state_path.exists():
                self.state_path.unlink()
            guard.unlink()

    def test_release_guard_fifo_refuses_without_opening_payload(self):
        guard = ownership._release_guard_path(self.state_path)
        os.mkfifo(guard)
        real_open = ownership.os.open

        def reject_guard_open(path, *args, **kwargs):
            if path == "implementation-owner.release-pending":
                raise AssertionError("release guard payload was opened")
            return real_open(path, *args, **kwargs)

        with (mock.patch.object(
                ownership.os, "open", side_effect=reject_guard_open),
              self.assertRaisesRegex(
                  ownership.OwnershipRefusal, "owner state")):
            ownership.acquire(self.repo, self.item)
        self.assertFalse(self.state_path.exists())

    def test_owner_state_read_is_bounded_before_any_payload_read(self):
        self.state_path.write_bytes(b"{" + b" " * 65536)
        checkout = ownership.canonical_worktree(self.repo, self.item)
        with (mock.patch.object(
                ownership, "canonical_worktree", return_value=checkout),
              mock.patch.object(
                Path, "read_bytes",
                side_effect=AssertionError("unbounded pathname read")),
              mock.patch.object(
                  ownership.os, "read",
                  side_effect=AssertionError("oversized record was read")) as read,
              self.assertRaisesRegex(
                  ownership.OwnershipRefusal, "owner state")):
            ownership.acquire(self.repo, self.item)
        read.assert_not_called()

    def test_owner_state_leaf_and_ancestor_replacement_refuse(self):
        for attack in ("leaf", "ancestor"):
            with self.subTest(attack=attack):
                claim = ownership.acquire(self.repo, self.item)
                raw = self.state_path.read_bytes()
                item_dir = self.state_path.parent
                detached = item_dir.with_name(item_dir.name + "-detached")
                replacement = self.state_path.with_name("owner-copy.json")
                if attack == "leaf":
                    replacement.write_bytes(raw)
                owner_inode = self.state_path.stat().st_ino
                real_read = ownership.os.read
                attacked = False

                def substitute(fd, size):
                    nonlocal attacked
                    if (not attacked and
                            os.fstat(fd).st_ino == owner_inode):
                        attacked = True
                        if attack == "leaf":
                            os.replace(replacement, self.state_path)
                        else:
                            item_dir.rename(detached)
                            shutil.copytree(detached, item_dir)
                    return real_read(fd, size)

                try:
                    with (mock.patch.object(
                            ownership.os, "read", side_effect=substitute),
                          self.assertRaisesRegex(
                              ownership.OwnershipRefusal, "owner state")):
                        ownership.verify(self.repo, self.item, claim.token)
                    self.assertTrue(attacked)
                finally:
                    if attack == "ancestor" and detached.exists():
                        shutil.rmtree(item_dir)
                        detached.rename(item_dir)
                    claim.release()

    def test_owner_namespace_open_failure_closes_every_acquired_fd_once(self):
        claim = ownership.acquire(self.repo, self.item)
        real_append = ownership.safeio._append_directory
        real_close = ownership.os.close
        acquired = []
        closed = []

        def append_then_refuse(chain, name):
            real_append(chain, name)
            if name == "items":
                closed.clear()
                acquired.extend(handle.fd for handle in chain)
                raise ownership.safeio.SafeIOError("simulated refusal")

        def record_close(fd):
            closed.append(fd)
            return real_close(fd)

        try:
            with (mock.patch.object(
                    ownership.safeio, "_append_directory",
                    side_effect=append_then_refuse),
                  mock.patch.object(
                      ownership.os, "close", side_effect=record_close),
                  self.assertRaisesRegex(
                      ownership.OwnershipRefusal, "owner state")):
                ownership.verify(self.repo, self.item, claim.token)
            self.assertTrue(acquired)
            for fd in acquired:
                self.assertEqual(closed.count(fd), 1)
                with self.assertRaises(OSError):
                    os.fstat(fd)
        finally:
            claim.release()

    def test_repeated_short_writes_persist_exact_canonical_record(self):
        real_write = ownership.os.write
        write_sizes = []

        def write_seven_bytes(fd, buffer):
            written = real_write(fd, memoryview(buffer)[:7])
            write_sizes.append(written)
            return written

        with mock.patch.object(ownership.os, "write",
                               side_effect=write_seven_bytes), \
                mock.patch.object(ownership.os, "fsync",
                                  wraps=ownership.os.fsync) as fsync:
            claim = ownership.acquire(self.repo, self.item)
        try:
            expected = (json.dumps(
                ownership._record(self.item, claim.checkout, claim.token),
                sort_keys=True) + "\n").encode("utf-8")
            self.assertGreater(len(write_sizes), 1)
            self.assertEqual(sum(write_sizes), len(expected))
            self.assertEqual(self.state_path.read_bytes(), expected)
            fsync.assert_called_once()
        finally:
            claim.release()

    def test_zero_byte_write_retains_fail_closed_owner_state(self):
        with mock.patch.object(ownership.os, "write", return_value=0), \
                mock.patch.object(ownership.os, "fsync",
                                  wraps=ownership.os.fsync) as fsync:
            with self.assertRaisesRegex(OSError, "short write"):
                ownership.acquire(self.repo, self.item)
        self.assertEqual(self.state_path.read_bytes(), b"")
        fsync.assert_not_called()
        with self.assertRaises(ownership.OwnershipRefusal):
            ownership.acquire(self.repo, self.item)
        self.assertEqual(self.state_path.read_bytes(), b"")

    def test_two_distinct_owners_have_one_atomic_winner(self):
        gate = threading.Barrier(2)
        outcomes = []

        def attempt(label):
            gate.wait()
            try:
                outcomes.append((label, ownership.acquire(self.repo, self.item)))
            except ownership.OwnershipRefusal as exc:
                outcomes.append((label, str(exc)))

        threads = [threading.Thread(target=attempt, args=(name,))
                   for name in ("a", "b")]
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]
        claims = [value for _, value in outcomes
                  if isinstance(value, ownership.OwnerClaim)]
        refusals = [value for _, value in outcomes if isinstance(value, str)]
        self.assertEqual(len(claims), 1)
        self.assertEqual(len(refusals), 1)
        self.assertIn("automatic takeover is unsupported", refusals[0])
        claims[0].release()

    def test_matching_nested_claim_inherits_and_only_outer_release_frees(self):
        outer = ownership.acquire(self.repo, self.item)
        nested = ownership.acquire(self.repo, self.item, owner_token=outer.token)
        self.assertTrue(nested.inherited)
        nested.release()
        with self.assertRaises(ownership.OwnershipRefusal):
            ownership.acquire(self.repo, self.item)
        outer.release()
        ownership.acquire(self.repo, self.item).release()

    def test_owner_record_contains_digest_not_token(self):
        outer = ownership.acquire(self.repo, self.item)
        try:
            record = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.assertEqual(record["owner_sha256"],
                             ownership._digest(outer.token))
            self.assertNotIn(outer.token,
                             self.state_path.read_text(encoding="utf-8"))
            self.assertEqual(record["checkout"], str(outer.checkout))
        finally:
            outer.release()

    def test_wrong_or_missing_token_cannot_inherit_or_release(self):
        outer = ownership.acquire(self.repo, self.item)
        try:
            with self.assertRaises(ownership.OwnershipRefusal):
                ownership.acquire(self.repo, self.item, owner_token="wrong")
            with self.assertRaises(ownership.OwnershipRefusal):
                ownership.acquire(self.repo, self.item)
            with self.assertRaises(ownership.OwnershipRefusal) as context:
                ownership.release(self.repo, self.item, outer.checkout,
                                  "not-the-owner")
            self.assertNotIn(outer.token, str(context.exception))
        finally:
            outer.release()

    def test_non_owner_refusal_preserves_record_bytes(self):
        outer = ownership.acquire(self.repo, self.item)
        try:
            before = self.state_path.read_bytes()
            with self.assertRaises(ownership.OwnershipRefusal) as context:
                ownership.release(self.repo, self.item, outer.checkout,
                                  "not-the-owner")
            self.assertEqual(self.state_path.read_bytes(), before)
            self.assertNotIn(outer.token, str(context.exception))
        finally:
            outer.release()

    def test_generic_log_event_cannot_acquire_or_release(self):
        logs.append_event(self.repo, self.item, "ownership.acquired",
                          {"item": self.item})
        self.assertFalse(self.state_path.exists())
        outer = ownership.acquire(self.repo, self.item)
        try:
            before = self.state_path.read_bytes()
            logs.append_event(self.repo, self.item, "ownership.released",
                              {"item": self.item})
            self.assertEqual(self.state_path.read_bytes(), before)
            with self.assertRaises(ownership.OwnershipRefusal):
                ownership.acquire(self.repo, self.item, owner_token="other")
        finally:
            outer.release()

    def test_different_registered_items_acquire_concurrently(self):
        gate = threading.Barrier(2)
        claims = []

        def attempt(item_id):
            gate.wait()
            claims.append(ownership.acquire(self.repo, item_id))

        threads = [threading.Thread(target=attempt, args=(item_id,))
                   for item_id in (self.item, self.other_item)]
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]
        try:
            self.assertEqual(len(claims), 2)
            self.assertNotEqual(claims[0].checkout, claims[1].checkout)
            self.assertTrue(ownership.owner_state_path(
                self.repo, self.other_item).exists())
        finally:
            for claim in claims:
                claim.release()


class InvalidStateTest(OwnershipFixture):
    def _valid_record(self, **updates):
        record = {
            "version": 1,
            "item": self.item,
            "checkout": str(ownership.canonical_worktree(
                self.repo, self.item)),
            "owner_sha256": "a" * 64,
        }
        record.update(updates)
        return record

    @staticmethod
    def _encoded(record):
        return (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")

    def test_invalid_owner_state_refuses_without_mutation(self):
        missing_digest = self._valid_record()
        del missing_digest["owner_sha256"]
        extra_key = self._valid_record(pid=999999999)
        duplicate_key = self._encoded(self._valid_record()).replace(
            b'"version": 1', b'"version": 1, "version": 1')
        cases = {
            "invalid UTF-8": b"\xff\xfe",
            "malformed JSON": b"{",
            "array": b"[]\n",
            "missing key": self._encoded(missing_digest),
            "extra key": self._encoded(extra_key),
            "duplicate key": duplicate_key,
            "unsupported version": self._encoded(
                self._valid_record(version=2)),
            "string version": self._encoded(
                self._valid_record(version="1")),
            "bool version": self._encoded(
                self._valid_record(version=True)),
            "float version": self._encoded(
                self._valid_record(version=1.0)),
            "wrong item type": self._encoded(
                self._valid_record(item=7)),
            "wrong checkout type": self._encoded(
                self._valid_record(checkout=[str(self.repo)])),
            "wrong digest type": self._encoded(
                self._valid_record(owner_sha256=7)),
            "other item": self._encoded(
                self._valid_record(item=self.other_item)),
            "other canonical checkout": self._encoded(self._valid_record(
                checkout=str(self.other_worktree.resolve()))),
            "short digest": self._encoded(
                self._valid_record(owner_sha256="a" * 63)),
            "long digest": self._encoded(
                self._valid_record(owner_sha256="a" * 65)),
            "uppercase digest": self._encoded(
                self._valid_record(owner_sha256="A" * 64)),
            "non-hex digest": self._encoded(
                self._valid_record(owner_sha256="g" * 64)),
        }
        for label, raw in cases.items():
            with self.subTest(label=label):
                self.state_path.write_bytes(raw)
                before = self.state_path.read_bytes()
                with self.assertRaisesRegex(ownership.OwnershipRefusal,
                                            "owner state"):
                    ownership.acquire(self.repo, self.item)
                self.assertEqual(self.state_path.read_bytes(), before)
                self.assertFalse(ownership._release_guard_path(
                    self.state_path).exists())
                self.assertFalse((self.repo / "contender-ran").exists())

    def test_unreadable_owner_state_refuses_without_mutation(self):
        raw = self._encoded(self._valid_record())
        self.state_path.write_bytes(raw)

        class UnreadableOps:
            @staticmethod
            def exists(path):
                return path.exists()

            @staticmethod
            def read_bytes(path):
                raise OSError("simulated read failure")

        with self.assertRaisesRegex(ownership.OwnershipRefusal,
                                    "owner state"):
            ownership.acquire(self.repo, self.item, ops=UnreadableOps())
        self.assertEqual(self.state_path.read_bytes(), raw)

    def test_dead_pid_and_old_timestamp_never_authorize_takeover(self):
        fixtures = {
            "dead PID": self._valid_record(pid=999999999),
            "old timestamp": self._valid_record(
                created_at="1970-01-01T00:00:00Z"),
            "dead and old": self._valid_record(
                pid=-1, created_at="1900-01-01T00:00:00Z"),
        }
        for label, record in fixtures.items():
            with self.subTest(label=label):
                raw = self._encoded(record)
                self.state_path.write_bytes(raw)
                with self.assertRaisesRegex(ownership.OwnershipRefusal,
                                            "automatic takeover"):
                    ownership.acquire(self.repo, self.item)
                self.assertEqual(self.state_path.read_bytes(), raw)


class ReleaseFailureTest(OwnershipFixture):
    def _assert_later_acquire_refuses_without_mutation(self, expected):
        with self.assertRaises(ownership.OwnershipRefusal):
            ownership.acquire(self.repo, self.item)
        self.assertEqual(self.state_path.read_bytes(), expected)

    def test_missing_or_non_string_tokens_refuse_before_hashing(self):
        outer = ownership.acquire(self.repo, self.item)
        before = self.state_path.read_bytes()
        current_digest = ownership._digest(outer.token)
        attempts = {
            "inherit missing": lambda: ownership.acquire(
                self.repo, self.item),
            "inherit empty": lambda: ownership.acquire(
                self.repo, self.item, owner_token=""),
            "inherit non-string": lambda: ownership.acquire(
                self.repo, self.item, owner_token=7),
            "release missing": lambda: ownership.release(
                self.repo, self.item, outer.checkout, None),
            "release empty": lambda: ownership.release(
                self.repo, self.item, outer.checkout, ""),
            "release non-string": lambda: ownership.release(
                self.repo, self.item, outer.checkout, False),
        }
        try:
            with mock.patch.object(
                    ownership, "_digest",
                    side_effect=AssertionError("token was hashed")) as digest:
                for label, attempt in attempts.items():
                    with self.subTest(label=label):
                        with self.assertRaises(ownership.OwnershipRefusal) as ctx:
                            attempt()
                        self.assertNotIn(outer.token, str(ctx.exception))
                        self.assertNotIn(current_digest, str(ctx.exception))
                        self.assertEqual(self.state_path.read_bytes(), before)
                digest.assert_not_called()
        finally:
            outer.release()

    def test_clean_outer_release_unlinks_once_and_allows_later_acquire(self):
        outer = ownership.acquire(self.repo, self.item)
        nested = ownership.acquire(
            self.repo, self.item, owner_token=outer.token)
        before = self.state_path.read_bytes()
        events = []
        guard = ownership._release_guard_path(self.state_path)

        class RecordingOps:
            @staticmethod
            def read_bytes(path):
                events.append(("read", path))
                return path.read_bytes()

            @staticmethod
            def unlink(path):
                events.append(("unlink", path))
                if not guard.exists():
                    raise AssertionError("release guard missing before unlink")
                path.unlink()

            @staticmethod
            def exists(path):
                events.append(("exists", path))
                if not guard.exists():
                    raise AssertionError(
                        "release guard missing during absence verification")
                return path.exists()

        nested.release()
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual(events, [])
        ownership.release(self.repo, self.item, outer.checkout, outer.token,
                          ops=RecordingOps())
        self.assertEqual(events, [
            ("read", self.state_path),
            ("unlink", self.state_path),
            ("exists", self.state_path),
        ])
        self.assertFalse(self.state_path.exists())
        self.assertFalse(guard.exists())
        ownership.acquire(self.repo, self.item).release()

    def test_later_acquire_refuses_after_simulated_crash(self):
        abandoned = ownership.acquire(self.repo, self.item)
        before = self.state_path.read_bytes()
        del abandoned
        self._assert_later_acquire_refuses_without_mutation(before)

    def test_release_unlink_failure_retains_refusal(self):
        outer = ownership.acquire(self.repo, self.item)
        before = self.state_path.read_bytes()
        evidence = self.repo / "completed-evidence.txt"
        evidence.write_bytes(b"completed\n")
        unlink_calls = []

        class UnlinkFailureOps:
            @staticmethod
            def read_bytes(path):
                return path.read_bytes()

            @staticmethod
            def unlink(path):
                unlink_calls.append(path)
                raise OSError("simulated unlink failure")

            @staticmethod
            def exists(path):
                return path.exists()

        with self.assertRaisesRegex(ownership.OwnershipReleaseError,
                                    "could not be verified"):
            ownership.release(self.repo, self.item, outer.checkout,
                              outer.token, ops=UnlinkFailureOps())
        self.assertEqual(unlink_calls, [self.state_path])
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertTrue(ownership._release_guard_path(
            self.state_path).is_file())
        self.assertEqual(evidence.read_bytes(), b"completed\n")
        self._assert_later_acquire_refuses_without_mutation(before)

    def test_release_preserves_owner_mutated_during_guard_creation(self):
        outer = ownership.acquire(self.repo, self.item)
        foreign = b"foreign owner evidence after guard creation\n"
        owner_inode = self.state_path.stat().st_ino
        guard = ownership._release_guard_path(self.state_path)
        real_write_exclusive = ownership._write_exclusive_at

        def create_guard_then_mutate(directory_fd, name, payload):
            identity = real_write_exclusive(directory_fd, name, payload)
            if name == ownership._RELEASE_GUARD_NAME:
                self.state_path.write_bytes(foreign)
            return identity

        with (mock.patch.object(
                ownership, "_write_exclusive_at",
                side_effect=create_guard_then_mutate),
              self.assertRaisesRegex(
                  ownership.OwnershipReleaseError,
                  "release could not be verified")):
            ownership.release(
                self.repo, self.item, outer.checkout, outer.token)

        self.assertEqual(self.state_path.read_bytes(), foreign)
        self.assertEqual(self.state_path.stat().st_ino, owner_inode)
        self.assertEqual(guard.read_bytes(), b"release-pending\n")

    def test_release_preserves_owner_mutated_during_guard_directory_fsync(self):
        outer = ownership.acquire(self.repo, self.item)
        foreign = b"foreign owner evidence during guard sync\n"
        owner_inode = self.state_path.stat().st_ino
        item_identity = (
            self.state_path.parent.stat().st_dev,
            self.state_path.parent.stat().st_ino,
        )
        guard = ownership._release_guard_path(self.state_path)
        real_fsync = ownership.os.fsync
        mutated = False

        def sync_guard_then_mutate(fd):
            nonlocal mutated
            details = os.fstat(fd)
            result = real_fsync(fd)
            if (not mutated and stat.S_ISDIR(details.st_mode) and
                    (details.st_dev, details.st_ino) == item_identity and
                    guard.is_file()):
                self.state_path.write_bytes(foreign)
                mutated = True
            return result

        with (mock.patch.object(
                ownership.os, "fsync", side_effect=sync_guard_then_mutate),
              self.assertRaisesRegex(
                  ownership.OwnershipReleaseError,
                  "release could not be verified")):
            ownership.release(
                self.repo, self.item, outer.checkout, outer.token)

        self.assertTrue(mutated)
        self.assertEqual(self.state_path.read_bytes(), foreign)
        self.assertEqual(self.state_path.stat().st_ino, owner_inode)
        self.assertEqual(guard.read_bytes(), b"release-pending\n")

    def test_release_preserves_guard_mutated_before_guard_unlink(self):
        outer = ownership.acquire(self.repo, self.item)
        foreign = b"foreign release guard evidence\n"
        guard = ownership._release_guard_path(self.state_path)
        observed = {}
        real_unlink_if_identity = safeio._unlink_if_identity

        def unlink_owner_then_mutate_guard(directory_fd, name, identity):
            removed = real_unlink_if_identity(directory_fd, name, identity)
            if name == ownership._OWNER_STATE_NAME and removed:
                observed["inode"] = guard.stat().st_ino
                guard.write_bytes(foreign)
            return removed

        with (mock.patch.object(
                safeio, "_unlink_if_identity",
                side_effect=unlink_owner_then_mutate_guard),
              self.assertRaisesRegex(
                  ownership.OwnershipReleaseError,
                  "release could not be verified")):
            ownership.release(
                self.repo, self.item, outer.checkout, outer.token)

        self.assertFalse(self.state_path.exists())
        self.assertEqual(guard.read_bytes(), foreign)
        self.assertEqual(guard.stat().st_ino, observed["inode"])

    def test_release_post_delete_verification_failure_is_retained_fail_closed(
            self):
        outer = ownership.acquire(self.repo, self.item)
        evidence = self.repo / "completed-evidence.txt"
        evidence.write_bytes(b"completed\n")
        guard = ownership._release_guard_path(self.state_path)
        events = []

        class VerificationFailureOps:
            @staticmethod
            def read_bytes(path):
                events.append("read")
                return path.read_bytes()

            @staticmethod
            def unlink(path):
                if not guard.is_file():
                    raise AssertionError("release guard missing before unlink")
                events.append("unlink")
                path.unlink()

            @staticmethod
            def exists(path):
                events.append("verify")
                if path.exists():
                    raise AssertionError("owner state was not deleted")
                if not guard.is_file():
                    raise AssertionError(
                        "release guard missing after owner deletion")
                with self.assertRaises(ownership.OwnershipRefusal):
                    ownership.acquire(self.repo, self.item)
                raise OSError("simulated verification failure")

        with self.assertRaisesRegex(ownership.OwnershipReleaseError,
                                    "could not be verified"):
            ownership.release(self.repo, self.item, outer.checkout,
                              outer.token, ops=VerificationFailureOps())
        self.assertEqual(events, ["read", "unlink", "verify"])
        self.assertFalse(self.state_path.exists())
        self.assertEqual(guard.read_bytes(), b"release-pending\n")
        marker_before = guard.read_bytes()
        with self.assertRaises(ownership.OwnershipRefusal):
            ownership.acquire(self.repo, self.item)
        self.assertEqual(guard.read_bytes(), marker_before)
        self.assertEqual(events.count("unlink"), 1)
        self.assertEqual(evidence.read_bytes(), b"completed\n")

    def test_post_delete_verification_does_not_overwrite_contender(self):
        outer = ownership.acquire(self.repo, self.item)
        contender = b"contender-owned-state\n"
        guard = ownership._release_guard_path(self.state_path)

        class ContenderDuringVerificationOps:
            @staticmethod
            def read_bytes(path):
                return path.read_bytes()

            @staticmethod
            def unlink(path):
                if not guard.is_file():
                    raise AssertionError("release guard missing before unlink")
                path.unlink()

            @staticmethod
            def exists(path):
                path.write_bytes(contender)
                return path.exists()

        with self.assertRaises(ownership.OwnershipReleaseError):
            ownership.release(
                self.repo, self.item, outer.checkout, outer.token,
                ops=ContenderDuringVerificationOps())
        self.assertEqual(self.state_path.read_bytes(), contender)
        self.assertTrue(guard.is_file())
        self._assert_later_acquire_refuses_without_mutation(contender)

    def test_partial_write_failure_retains_fail_closed_state(self):
        checkout = ownership.canonical_worktree(self.repo, self.item)
        real_write = ownership.os.write
        writes = 0

        def partial_then_zero(fd, buffer):
            nonlocal writes
            writes += 1
            if writes == 1:
                return real_write(fd, memoryview(buffer)[:7])
            return 0

        with mock.patch.object(ownership, "canonical_worktree",
                               return_value=checkout), \
                mock.patch.object(ownership.os, "write",
                                  side_effect=partial_then_zero):
            with self.assertRaisesRegex(OSError, "short write"):
                ownership.acquire(self.repo, self.item)
        before = self.state_path.read_bytes()
        self.assertEqual(len(before), 7)
        self._assert_later_acquire_refuses_without_mutation(before)

    def test_fsync_failure_retains_fail_closed_state(self):
        checkout = ownership.canonical_worktree(self.repo, self.item)
        with mock.patch.object(ownership, "canonical_worktree",
                               return_value=checkout), \
                mock.patch.object(ownership.os, "fsync",
                                  side_effect=OSError("fsync failed")):
            with self.assertRaisesRegex(OSError, "fsync failed"):
                ownership.acquire(self.repo, self.item)
        before = self.state_path.read_bytes()
        self.assertGreater(len(before), 0)
        self._assert_later_acquire_refuses_without_mutation(before)

    def test_close_failure_retains_fail_closed_state(self):
        checkout = ownership.canonical_worktree(self.repo, self.item)
        real_close = ownership.os.close

        def close_then_fail(fd):
            real_close(fd)
            raise OSError("close failed")

        with mock.patch.object(ownership, "canonical_worktree",
                               return_value=checkout), \
                mock.patch.object(ownership.os, "close",
                                  side_effect=close_then_fail):
            with self.assertRaisesRegex(OSError, "close failed"):
                ownership.acquire(self.repo, self.item)
        before = self.state_path.read_bytes()
        self.assertGreater(len(before), 0)
        self._assert_later_acquire_refuses_without_mutation(before)
