import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from scripts.factory.lib import initrepo, items, logs, ownership


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


class OwnershipPrimitiveTest(OwnershipFixture):
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
