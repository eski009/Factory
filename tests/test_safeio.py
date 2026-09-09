import hashlib
import json
import os
import stat
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock

from scripts.factory.lib import safeio


class SafeIOTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "state").mkdir()
        (self.root / "state" / "value.bin").write_bytes(b"before")

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_records_canonical_bytes_hash_and_identities(self):
        snapshot = safeio.snapshot_path(self.root, "state/value.bin")

        self.assertEqual(snapshot.root, self.root)
        self.assertEqual(snapshot.relative, PurePosixPath("state/value.bin"))
        self.assertEqual(snapshot.data, b"before")
        self.assertEqual(snapshot.sha256, hashlib.sha256(b"before").hexdigest())
        self.assertEqual(len(snapshot.file_identity), 5)
        self.assertGreaterEqual(len(snapshot.directory_identities), 2)
        safeio.revalidate(snapshot)

    def test_unsafe_and_duplicate_paths_are_rejected(self):
        unsafe = ("/absolute", "../escape", "state/../escape", "./value",
                  "state\\value", "state//value", "state/./value", "nul\0x")
        for relative in unsafe:
            with self.subTest(relative=relative):
                with self.assertRaises(safeio.SafeIOError):
                    safeio.snapshot_path(self.root, relative)

        with self.assertRaises(safeio.SafeIOError):
            safeio.snapshot_many(
                self.root, ["state/value.bin", PurePosixPath("state/value.bin")])

    def test_symlink_and_non_regular_leaves_are_rejected(self):
        (self.root / "state" / "link").symlink_to("value.bin")
        with self.assertRaises(safeio.SafeIOError):
            safeio.snapshot_path(self.root, "state/link")

        fifo = self.root / "state" / "pipe"
        if hasattr(os, "mkfifo"):
            os.mkfifo(fifo)
            with self.assertRaises(safeio.SafeIOError):
                safeio.snapshot_path(self.root, "state/pipe")

    def test_bounded_read_rejects_oversize_and_short_read(self):
        with self.assertRaises(safeio.SafeIOError):
            safeio.snapshot_path(self.root, "state/value.bin", limit=5)

        real_read = safeio.os.read
        shortened = False

        def short_read(fd, amount):
            nonlocal shortened
            data = real_read(fd, amount)
            if data and not shortened:
                shortened = True
                return data[:-1]
            return data

        with mock.patch.object(safeio.os, "read", side_effect=short_read):
            with self.assertRaises(safeio.SafeIOError):
                safeio.snapshot_path(self.root, "state/value.bin")

        with self.assertRaises(safeio.SafeIOError):
            safeio.snapshot_path(
                self.root, "missing", limit=-1, allow_missing=True)

    def test_in_place_mutation_and_leaf_replacement_are_rejected(self):
        snapshot = safeio.snapshot_path(self.root, "state/value.bin")
        (self.root / "state" / "value.bin").write_bytes(b"changed")
        with self.assertRaises(safeio.SafeIOError):
            safeio.revalidate(snapshot)

        (self.root / "state" / "value.bin").write_bytes(b"before")
        replacement_snapshot = safeio.snapshot_path(
            self.root, "state/value.bin")
        replacement = self.root / "state" / "replacement"
        replacement.write_bytes(b"before")
        replacement.replace(self.root / "state" / "value.bin")
        with self.assertRaises(safeio.SafeIOError):
            safeio.revalidate(replacement_snapshot)

    def test_leaf_replacement_during_read_is_rejected(self):
        real_stat = safeio.os.stat
        replaced = False

        def replace_before_entry_check(path, *args, **kwargs):
            nonlocal replaced
            if (path == "value.bin" and kwargs.get("dir_fd") is not None and
                    kwargs.get("follow_symlinks") is False and not replaced):
                replacement = self.root / "state" / "replacement"
                replacement.write_bytes(b"before")
                replacement.replace(self.root / "state" / "value.bin")
                replaced = True
            return real_stat(path, *args, **kwargs)

        with mock.patch.object(
                safeio.os, "stat", side_effect=replace_before_entry_check):
            with self.assertRaises(safeio.SafeIOError):
                safeio.snapshot_path(self.root, "state/value.bin")

    def test_every_supported_ancestor_replacement_is_rejected(self):
        for level in ("root", "outer", "inner"):
            with self.subTest(level=level):
                nested = self.root / "outer" / "inner"
                nested.mkdir(parents=True, exist_ok=True)
                target = nested / "value"
                target.write_bytes(b"data")
                snapshot = safeio.snapshot_path(
                    self.root, "outer/inner/value")
                targets = {
                    "root": self.root,
                    "outer": self.root / "outer",
                    "inner": nested,
                }
                original = targets[level]
                moved = original.with_name(original.name + "-moved")
                original.rename(moved)
                original.mkdir()
                try:
                    with self.assertRaises(safeio.SafeIOError):
                        safeio.revalidate(snapshot)
                finally:
                    original.rmdir()
                    moved.rename(original)

    def test_snapshot_many_revalidates_earlier_files_after_all_reads(self):
        other = self.root / "state" / "other.bin"
        other.write_bytes(b"other")
        real_snapshot = safeio._snapshot_from_chain
        calls = 0

        def mutate_after_second(*args, **kwargs):
            nonlocal calls
            result = real_snapshot(*args, **kwargs)
            calls += 1
            if calls == 2:
                (self.root / "state" / "value.bin").write_bytes(b"changed")
            return result

        with mock.patch.object(
                safeio, "_snapshot_from_chain", side_effect=mutate_after_second):
            with self.assertRaises(safeio.SafeIOError):
                safeio.snapshot_many(
                    self.root, ("state/value.bin", "state/other.bin"))

    def test_missing_snapshot_revalidates_absence_and_parent_chain(self):
        snapshot = safeio.snapshot_path(
            self.root, "state/new/answer.md", allow_missing=True)
        self.assertIsInstance(snapshot, safeio.MissingSnapshot)
        safeio.revalidate(snapshot)

        (self.root / "state" / "new").mkdir()
        with self.assertRaises(safeio.SafeIOError):
            safeio.revalidate(snapshot)

    def test_publication_journal_preflight_honours_exact_byte_boundary(self):
        data = b"answer\n"
        relative = "state/a/b/c/answer.md"
        missing = safeio.snapshot_path(
            self.root, relative, allow_missing=True)
        required = safeio._publication_journal_upper_bound(missing, data)

        with mock.patch.object(
                safeio, "_PUBLICATION_JOURNAL_LIMIT", required):
            self.assertEqual(
                safeio.preflight_publication(missing, data), required)
            result = safeio.publish_exclusive(missing, data)

        self.assertEqual(result.data, data)
        self.assertEqual((self.root / relative).read_bytes(), data)

        refused_relative = "state/d/e/f/refused.md"
        refused = safeio.snapshot_path(
            self.root, refused_relative, allow_missing=True)
        refused_required = safeio._publication_journal_upper_bound(
            refused, data)
        journal = self.root / "state" / safeio._journal_name(refused.relative)
        with (mock.patch.object(
                safeio, "_PUBLICATION_JOURNAL_LIMIT",
                refused_required - 1),
              self.assertRaisesRegex(
                  safeio.SafeIOError, "publication journal.*limit")):
            safeio.publish_exclusive(refused, data)

        self.assertFalse(journal.exists())
        self.assertFalse((self.root / "state" / "d").exists())

    def test_journal_writers_reject_oversize_before_publication(self):
        state = {"payload": "x" * 32}
        payload = safeio._journal_bytes(state)
        directory = self.root / "state"
        journal = directory / "journal.json"
        journal.write_bytes(b"old\n")
        original_identity = (journal.stat().st_dev, journal.stat().st_ino)
        chain = safeio._open_root_chain(directory)
        directory_fd = chain[-1].fd
        try:
            with (mock.patch.object(
                    safeio, "_PUBLICATION_JOURNAL_LIMIT",
                    len(payload) - 1),
                  self.assertRaisesRegex(
                      safeio.SafeIOError, "publication journal.*limit")):
                safeio._update_journal(directory_fd, journal.name, state)
        finally:
            safeio._close_chain(chain)

        self.assertEqual(journal.read_bytes(), b"old\n")
        self.assertEqual(
            (journal.stat().st_dev, journal.stat().st_ino),
            original_identity)

        chain = safeio._open_root_chain(directory)
        directory_fd = chain[-1].fd
        try:
            with mock.patch.object(
                    safeio, "_PUBLICATION_JOURNAL_LIMIT", len(payload)):
                safeio._update_journal(
                    directory_fd, journal.name, state,
                    expected_bytes=b"old\n",
                    expected_inode=original_identity,
                    chain=chain)
        finally:
            safeio._close_chain(chain)
        self.assertEqual(journal.read_bytes(), payload)

        missing = safeio.snapshot_path(
            self.root, "new.bin", allow_missing=True)
        initial_state = {
            **safeio._expected_journal(missing, b"new\n"),
            "directories": [],
            "leaf": {"attempts": [safeio._new_leaf_attempt(
                missing.transaction_nonce, 0)]},
        }
        initial_payload = safeio._journal_bytes(initial_state)
        chain = safeio._open_expected_parent(missing)
        try:
            with mock.patch.object(
                    safeio, "_PUBLICATION_JOURNAL_LIMIT",
                    len(initial_payload)):
                name, _state, _identity, _payload = \
                    safeio._load_or_create_journal(
                        chain, missing, b"new\n", missing.relative.name)
        finally:
            safeio._close_chain(chain)
        created_journal = self.root / name
        self.assertEqual(created_journal.read_bytes(), initial_payload)

    def test_atomic_write_refuses_in_place_temp_mutation_before_install(self):
        directory = self.root / "state"
        journal = directory / "journal.json"
        original = b"original journal\n"
        replacement = b"authorized journal\n"
        foreign = b"foreign-modified temporary\n"
        journal.write_bytes(original)
        original_inode = journal.stat().st_ino
        observed = {}
        chain = safeio._open_root_chain(directory)

        def mutate_temporary():
            temporary, = directory.glob(".journal.json.tmp-*")
            before_inode = temporary.stat().st_ino
            temporary.write_bytes(foreign)
            observed["path"] = temporary
            observed["inode"] = before_inode

        try:
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "replacement temporary changed"):
                safeio._atomic_write(
                    chain[-1].fd, journal.name, replacement,
                    before_install=mutate_temporary)
        finally:
            safeio._close_chain(chain)

        self.assertEqual(journal.read_bytes(), original)
        self.assertEqual(journal.stat().st_ino, original_inode)
        temporary = observed["path"]
        self.assertEqual(temporary.read_bytes(), foreign)
        self.assertEqual(temporary.stat().st_ino, observed["inode"])

    def test_atomic_write_preserves_mutated_temp_when_callback_raises(self):
        directory = self.root / "state"
        journal = directory / "journal.json"
        original = b"original journal\n"
        foreign = b"foreign-modified temporary\n"
        journal.write_bytes(original)
        original_inode = journal.stat().st_ino
        observed = {}
        chain = safeio._open_root_chain(directory)

        def mutate_then_raise():
            temporary, = directory.glob(".journal.json.tmp-*")
            before_inode = temporary.stat().st_ino
            temporary.write_bytes(foreign)
            observed["path"] = temporary
            observed["inode"] = before_inode
            raise RuntimeError("callback failed after mutation")

        try:
            with self.assertRaisesRegex(
                    RuntimeError, "callback failed after mutation"):
                safeio._atomic_write(
                    chain[-1].fd, journal.name, b"authorized journal\n",
                    before_install=mutate_then_raise)
        finally:
            safeio._close_chain(chain)

        self.assertEqual(journal.read_bytes(), original)
        self.assertEqual(journal.stat().st_ino, original_inode)
        temporary = observed["path"]
        self.assertEqual(temporary.read_bytes(), foreign)
        self.assertEqual(temporary.stat().st_ino, observed["inode"])

    def test_atomic_write_preserves_temp_mutated_during_initial_fsync_failure(self):
        directory = self.root / "state"
        journal = directory / "journal.json"
        original = b"original journal\n"
        replacement = b"authorized journal\n"
        foreign = b"foreign-modified temporary\n"
        journal.write_bytes(original)
        original_identity = (journal.stat().st_dev, journal.stat().st_ino)
        observed = {}
        real_fsync = safeio.os.fsync
        chain = safeio._open_root_chain(directory)

        def mutate_then_fail(fd):
            details = os.fstat(fd)
            if stat.S_ISREG(details.st_mode) and not observed:
                temporary, = directory.glob(".journal.json.tmp-*")
                observed["path"] = temporary
                observed["inode"] = temporary.stat().st_ino
                temporary.write_bytes(foreign)
                raise OSError("injected initial fsync failure")
            return real_fsync(fd)

        try:
            with (mock.patch.object(
                    safeio.os, "fsync", side_effect=mutate_then_fail),
                  self.assertRaisesRegex(
                      OSError, "injected initial fsync failure")):
                safeio._atomic_write(
                    chain[-1].fd, journal.name, replacement)
        finally:
            safeio._close_chain(chain)

        self.assertEqual(journal.read_bytes(), original)
        self.assertEqual(
            (journal.stat().st_dev, journal.stat().st_ino), original_identity)
        temporary = observed["path"]
        self.assertEqual(temporary.read_bytes(), foreign)
        self.assertEqual(temporary.stat().st_ino, observed["inode"])

    def test_atomic_write_never_cleans_same_byte_replacement_on_fsync_failure(self):
        directory = self.root / "state"
        journal = directory / "journal.json"
        original = b"original journal\n"
        replacement = b"authorized journal\n"
        journal.write_bytes(original)
        observed = {}
        real_write_all = safeio._write_all
        real_fsync = safeio.os.fsync
        chain = safeio._open_root_chain(directory)

        def replace_after_write(fd, data):
            real_write_all(fd, data)
            temporary, = directory.glob(".journal.json.tmp-*")
            opened = os.fstat(fd)
            observed["opened_inode"] = (opened.st_dev, opened.st_ino)
            foreign = directory / "same-byte-foreign.tmp"
            foreign.write_bytes(data)
            os.replace(foreign, temporary)
            observed["path"] = temporary
            observed["identity"] = safeio._file_identity(temporary.stat())

        def fail_opened_fsync(fd):
            details = os.fstat(fd)
            if (details.st_dev, details.st_ino) == observed["opened_inode"]:
                raise OSError("injected original-inode fsync failure")
            return real_fsync(fd)

        try:
            with (mock.patch.object(
                    safeio, "_write_all", side_effect=replace_after_write),
                  mock.patch.object(
                      safeio.os, "fsync", side_effect=fail_opened_fsync),
                  self.assertRaises((safeio.SafeIOError, OSError))):
                safeio._atomic_write(
                    chain[-1].fd, journal.name, replacement)
        finally:
            safeio._close_chain(chain)

        self.assertEqual(journal.read_bytes(), original)
        temporary = observed["path"]
        self.assertTrue(temporary.is_file())
        self.assertEqual(temporary.read_bytes(), replacement)
        self.assertEqual(
            safeio._file_identity(temporary.stat()), observed["identity"])

    def test_publish_bound_refuses_in_place_temp_mutation_before_install(self):
        directory = self.root / "state"
        destination = directory / "journal.json"
        intended = b"authorized journal\n"
        foreign = b"foreign-modified temporary\n"
        observed = {}
        chain = safeio._open_root_chain(directory)

        def mutate_temporary():
            temporary, = directory.glob(".safeio-*.tmp")
            observed["path"] = temporary
            observed["inode"] = temporary.stat().st_ino
            temporary.write_bytes(foreign)

        try:
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "publication temporary changed"):
                safeio._publish_bound(
                    chain[-1].fd, destination.name, intended,
                    before_install=mutate_temporary)
        finally:
            safeio._close_chain(chain)

        self.assertFalse(destination.exists())
        temporary = observed["path"]
        self.assertEqual(temporary.read_bytes(), foreign)
        self.assertEqual(temporary.stat().st_ino, observed["inode"])

    def test_publish_bound_preserves_temp_mutated_during_initial_fsync_failure(self):
        directory = self.root / "state"
        destination = directory / "journal.json"
        foreign = b"foreign-modified temporary\n"
        observed = {}
        real_fsync = safeio.os.fsync
        chain = safeio._open_root_chain(directory)

        def mutate_then_fail(fd):
            details = os.fstat(fd)
            if stat.S_ISREG(details.st_mode) and not observed:
                temporary, = directory.glob(".safeio-*.tmp")
                observed["path"] = temporary
                observed["inode"] = temporary.stat().st_ino
                temporary.write_bytes(foreign)
                raise OSError("injected publication fsync failure")
            return real_fsync(fd)

        try:
            with (mock.patch.object(
                    safeio.os, "fsync", side_effect=mutate_then_fail),
                  self.assertRaisesRegex(
                      OSError, "injected publication fsync failure")):
                safeio._publish_bound(
                    chain[-1].fd, destination.name, b"authorized journal\n")
        finally:
            safeio._close_chain(chain)

        self.assertFalse(destination.exists())
        temporary = observed["path"]
        self.assertEqual(temporary.read_bytes(), foreign)
        self.assertEqual(temporary.stat().st_ino, observed["inode"])

    def test_publish_bound_never_cleans_same_byte_replacement_on_fsync_failure(self):
        directory = self.root / "state"
        destination = directory / "journal.json"
        intended = b"authorized journal\n"
        observed = {}
        real_write_all = safeio._write_all
        real_fsync = safeio.os.fsync
        chain = safeio._open_root_chain(directory)

        def replace_after_write(fd, data):
            real_write_all(fd, data)
            temporary, = directory.glob(".safeio-*.tmp")
            opened = os.fstat(fd)
            observed["opened_inode"] = (opened.st_dev, opened.st_ino)
            foreign = directory / "same-byte-foreign.tmp"
            foreign.write_bytes(data)
            os.replace(foreign, temporary)
            observed["path"] = temporary
            observed["identity"] = safeio._file_identity(temporary.stat())

        def fail_opened_fsync(fd):
            details = os.fstat(fd)
            if (details.st_dev, details.st_ino) == observed["opened_inode"]:
                raise OSError("injected original-inode fsync failure")
            return real_fsync(fd)

        try:
            with (mock.patch.object(
                    safeio, "_write_all", side_effect=replace_after_write),
                  mock.patch.object(
                      safeio.os, "fsync", side_effect=fail_opened_fsync),
                  self.assertRaises((safeio.SafeIOError, OSError))):
                safeio._publish_bound(
                    chain[-1].fd, destination.name, intended)
        finally:
            safeio._close_chain(chain)

        self.assertFalse(destination.exists())
        temporary = observed["path"]
        self.assertTrue(temporary.is_file())
        self.assertEqual(temporary.read_bytes(), intended)
        self.assertEqual(
            safeio._file_identity(temporary.stat()), observed["identity"])

    def test_existing_journal_at_limit_is_adopted_and_oversize_fails_closed(self):
        data = b"answer\n"
        missing = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)
        journal = self._leave_journal_installed_before_directory_fsync(
            missing, data)
        exact = safeio._publication_journal_upper_bound(missing, data)
        journal.write_bytes(
            journal.read_bytes().rstrip(b"\n") +
            (b" " * (exact - len(journal.read_bytes()))) + b"\n")
        self.assertEqual(len(journal.read_bytes()), exact)
        observed_limits = []
        real_read = safeio._read_regular_file

        def record_read(directory_fd, name, limit):
            if name == journal.name:
                observed_limits.append(limit)
            return real_read(directory_fd, name, limit)

        with (mock.patch.object(
                safeio, "_PUBLICATION_JOURNAL_LIMIT", exact),
              mock.patch.object(
                  safeio, "_read_regular_file", side_effect=record_read)):
            result = safeio.publish_exclusive(missing, data)

        self.assertEqual(result.data, data)
        self.assertGreaterEqual(len(observed_limits), 2)
        self.assertEqual(set(observed_limits), {exact})
        self.assertFalse(journal.exists())

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            refused = safeio.snapshot_path(
                root, "rounds/one/answer.md", allow_missing=True)
            limit = safeio._publication_journal_upper_bound(refused, data)
            state = {
                **safeio._expected_journal(refused, data),
                "directories": [],
                "leaf": {"attempts": [safeio._new_leaf_attempt(
                    refused.transaction_nonce, 0)]},
            }
            refused_journal = root / safeio._journal_name(refused.relative)
            encoded = safeio._journal_bytes(state).rstrip(b"\n")
            refused_journal.write_bytes(
                encoded + (b" " * (limit - len(encoded))) + b"\n")
            self.assertEqual(len(refused_journal.read_bytes()), limit + 1)
            original = refused_journal.read_bytes()
            original_inode = refused_journal.stat().st_ino
            for _retry in range(2):
                with (mock.patch.object(
                        safeio, "_PUBLICATION_JOURNAL_LIMIT", limit),
                      self.assertRaisesRegex(
                          safeio.SafeIOError, "file exceeds read limit")):
                    safeio.publish_exclusive(refused, data)
                self.assertEqual(refused_journal.read_bytes(), original)
                self.assertEqual(refused_journal.stat().st_ino, original_inode)
                self.assertFalse((root / "rounds").exists())

    def test_publish_exclusive_builds_safe_tail_and_never_overwrites(self):
        snapshot = safeio.publish_exclusive(
            self.root, "rounds/one/answer.md", b"answer\n")

        self.assertEqual(snapshot.data, b"answer\n")
        self.assertEqual(
            (self.root / "rounds" / "one" / "answer.md").read_bytes(),
            b"answer\n")
        self.assertEqual((self.root / "rounds").stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / "rounds" / "one").stat().st_mode & 0o777,
                         0o700)
        with self.assertRaises(safeio.SafeIOError):
            safeio.publish_exclusive(
                self.root, "rounds/one/answer.md", b"replacement\n")
        self.assertEqual(
            (self.root / "rounds" / "one" / "answer.md").read_bytes(),
            b"answer\n")

    def test_interrupted_missing_tail_retry_adopts_only_recorded_identities(self):
        missing = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)
        interrupted = False

        def interrupt_after_first(component, identity):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise OSError("injected interruption")

        with mock.patch.object(
                safeio, "_after_directory_install",
                side_effect=interrupt_after_first, create=True):
            with self.assertRaisesRegex(OSError, "injected interruption"):
                safeio.publish_exclusive(missing, b"answer\n")

        result = safeio.publish_exclusive(missing, b"answer\n")
        self.assertEqual(result.data, b"answer\n")
        self.assertEqual(
            (self.root / "rounds" / "one" / "answer.md").read_bytes(),
            b"answer\n")

    def _leave_journal_installed_before_directory_fsync(self, missing, data):
        real_publish = safeio._publish_bound

        def die_after_install():
            raise OSError("injected journal install interruption")

        def publish_with_interruption(directory_fd, name, payload, **kwargs):
            return real_publish(
                directory_fd, name, payload,
                before_install=kwargs.get("before_install"),
                after_install=die_after_install)

        with mock.patch.object(
                safeio, "_publish_bound",
                side_effect=publish_with_interruption):
            with self.assertRaisesRegex(
                    OSError, "journal install interruption"):
                safeio.publish_exclusive(missing, data)

        journal = self.root / safeio._journal_name(missing.relative)
        self.assertTrue(journal.is_file())
        state = safeio.json.loads(journal.read_text(encoding="utf-8"))
        self.assertEqual(state["directories"], [])
        self.assertEqual(
            state["leaf"]["attempts"],
            [safeio._new_leaf_attempt(missing.transaction_nonce, 0)])
        self.assertFalse((self.root / "rounds").exists())
        return journal

    def test_existing_journal_adoption_failure_precedes_missing_tail_mutation(self):
        missing = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)
        journal = self._leave_journal_installed_before_directory_fsync(
            missing, b"answer\n")
        journal_bytes = journal.read_bytes()
        journal_identity = (journal.stat().st_dev, journal.stat().st_ino)
        parent_identity = (self.root.stat().st_dev, self.root.stat().st_ino)
        journal_synced = False
        real_fsync = safeio.os.fsync

        def refuse_adoption_directory_sync(fd):
            nonlocal journal_synced
            details = os.fstat(fd)
            identity = (details.st_dev, details.st_ino)
            if stat.S_ISREG(details.st_mode) and identity == journal_identity:
                journal_synced = True
            if (stat.S_ISDIR(details.st_mode) and
                    identity == parent_identity and journal_synced):
                raise OSError("injected journal directory sync failure")
            return real_fsync(fd)

        with (mock.patch.object(
                safeio.os, "fsync",
                side_effect=refuse_adoption_directory_sync),
              self.assertRaisesRegex(
                  safeio.SafeIOError, "journal.*durable")):
            safeio.publish_exclusive(missing, b"answer\n")

        self.assertTrue(journal_synced)
        self.assertEqual(journal.read_bytes(), journal_bytes)
        self.assertEqual(
            (journal.stat().st_dev, journal.stat().st_ino), journal_identity)
        self.assertFalse((self.root / "rounds").exists())

        result = safeio.publish_exclusive(missing, b"answer\n")
        self.assertEqual(result.data, b"answer\n")
        self.assertFalse(journal.exists())

    def test_existing_journal_is_rechecked_before_any_recovery_mutation(self):
        missing = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)
        journal = self._leave_journal_installed_before_directory_fsync(
            missing, b"answer\n")
        journal_identity = (journal.stat().st_dev, journal.stat().st_ino)
        parent_identity = (self.root.stat().st_dev, self.root.stat().st_ino)
        real_read = safeio._read_regular_file
        real_validate = safeio._validate_chain
        real_fsync = safeio.os.fsync
        real_open = safeio.os.open
        mutations = {
            "mkdir": safeio.os.mkdir,
            "rename": safeio.os.rename,
            "replace": safeio.os.replace,
            "link": safeio.os.link,
            "unlink": safeio.os.unlink,
        }
        events = []

        def record_read(directory_fd, name, limit):
            result = real_read(directory_fd, name, limit)
            if name == journal.name:
                events.append("journal-read")
            return result

        def record_fsync(fd):
            details = os.fstat(fd)
            identity = (details.st_dev, details.st_ino)
            if stat.S_ISREG(details.st_mode) and identity == journal_identity:
                events.append("journal-file-sync")
            elif (stat.S_ISDIR(details.st_mode) and
                  identity == parent_identity):
                events.append("journal-directory-sync")
            return real_fsync(fd)

        def record_validate(chain):
            result = real_validate(chain)
            events.append("ancestor-recheck")
            return result

        def record_open(*args, **kwargs):
            flags = args[1] if len(args) > 1 else kwargs.get("flags", 0)
            if flags & os.O_CREAT:
                events.append("mutation:open-create")
            return real_open(*args, **kwargs)

        def mutation_recorder(name):
            def record(*args, **kwargs):
                events.append(f"mutation:{name}")
                return mutations[name](*args, **kwargs)
            return record

        with (mock.patch.object(
                safeio, "_read_regular_file", side_effect=record_read),
              mock.patch.object(
                  safeio, "_validate_chain", side_effect=record_validate),
              mock.patch.object(
                  safeio.os, "fsync", side_effect=record_fsync),
              mock.patch.object(
                  safeio.os, "open", side_effect=record_open),
              mock.patch.object(
                  safeio.os, "mkdir", side_effect=mutation_recorder("mkdir")),
              mock.patch.object(
                  safeio.os, "rename", side_effect=mutation_recorder("rename")),
              mock.patch.object(
                  safeio.os, "replace", side_effect=mutation_recorder("replace")),
              mock.patch.object(
                  safeio.os, "link", side_effect=mutation_recorder("link")),
              mock.patch.object(
                  safeio.os, "unlink", side_effect=mutation_recorder("unlink"))):
            result = safeio.publish_exclusive(missing, b"answer\n")

        mutation_index = next(
            index for index, event in enumerate(events)
            if event.startswith("mutation:"))
        file_sync_index = events.index("journal-file-sync")
        directory_sync_index = events.index(
            "journal-directory-sync", file_sync_index + 1)
        recheck_read_index = events.index(
            "journal-read", directory_sync_index + 1)
        ancestor_recheck_index = events.index(
            "ancestor-recheck", recheck_read_index + 1)
        self.assertLess(file_sync_index, directory_sync_index)
        self.assertLess(directory_sync_index, recheck_read_index)
        self.assertLess(recheck_read_index, ancestor_recheck_index)
        self.assertLess(ancestor_recheck_index, mutation_index)
        self.assertEqual(result.data, b"answer\n")
        self.assertFalse(journal.exists())

    def test_existing_journal_same_byte_inode_swap_refuses_before_mutation(self):
        missing = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)
        journal = self._leave_journal_installed_before_directory_fsync(
            missing, b"answer\n")
        original_bytes = journal.read_bytes()
        original_identity = (journal.stat().st_dev, journal.stat().st_ino)
        parent_identity = (self.root.stat().st_dev, self.root.stat().st_ino)
        real_fsync = safeio.os.fsync
        journal_synced = False
        substituted = False

        def substitute_after_directory_sync(fd):
            nonlocal journal_synced, substituted
            details = os.fstat(fd)
            identity = (details.st_dev, details.st_ino)
            if stat.S_ISREG(details.st_mode) and identity == original_identity:
                journal_synced = True
            result = real_fsync(fd)
            if (not substituted and journal_synced and
                    stat.S_ISDIR(details.st_mode) and
                    identity == parent_identity):
                replacement = self.root / "replacement-journal.json"
                replacement.write_bytes(original_bytes)
                os.replace(replacement, journal)
                substituted = True
            return result

        with (mock.patch.object(
                safeio.os, "fsync", side_effect=substitute_after_directory_sync),
              self.assertRaisesRegex(
                  safeio.SafeIOError, "journal.*changed")):
            safeio.publish_exclusive(missing, b"answer\n")

        self.assertTrue(substituted)
        self.assertEqual(journal.read_bytes(), original_bytes)
        self.assertNotEqual(
            (journal.stat().st_dev, journal.stat().st_ino), original_identity)
        self.assertFalse((self.root / "rounds").exists())

    def test_unbound_staging_inode_is_abandoned_before_retry_rolls_forward(self):
        missing = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)

        with mock.patch.object(
                safeio, "_after_staging_mkdir",
                side_effect=OSError("injected mkdir interruption"),
                create=True):
            with self.assertRaisesRegex(OSError, "mkdir interruption"):
                safeio.publish_exclusive(missing, b"answer\n")

        journal = next(self.root.glob(".safeio-publish-*.json"))
        first_state = safeio.json.loads(journal.read_text(encoding="utf-8"))
        first_attempt = first_state["directories"][0]["attempts"][0]
        self.assertEqual(first_attempt["status"], "planned")
        self.assertIsNone(first_attempt["identity"])
        first_staging = self.root / first_attempt["staging"]
        first_identity = (first_staging.stat().st_dev,
                          first_staging.stat().st_ino)

        with mock.patch.object(
                safeio, "_after_staging_mkdir",
                side_effect=OSError("injected second mkdir interruption")):
            with self.assertRaisesRegex(OSError, "second mkdir interruption"):
                safeio.publish_exclusive(missing, b"answer\n")

        second_state = safeio.json.loads(journal.read_text(encoding="utf-8"))
        attempts = second_state["directories"][0]["attempts"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["status"], "abandoned")
        self.assertEqual(tuple(attempts[0]["identity"]), first_identity)
        self.assertEqual(attempts[1]["status"], "planned")
        self.assertIsNone(attempts[1]["identity"])
        self.assertNotEqual(attempts[0]["staging"], attempts[1]["staging"])
        second_staging = self.root / attempts[1]["staging"]
        second_identity = (second_staging.stat().st_dev,
                           second_staging.stat().st_ino)

        result = safeio.publish_exclusive(missing, b"answer\n")

        destination = self.root / "rounds"
        destination_identity = (destination.stat().st_dev,
                                destination.stat().st_ino)
        self.assertEqual(result.data, b"answer\n")
        self.assertNotEqual(destination_identity, first_identity)
        self.assertNotEqual(destination_identity, second_identity)
        self.assertEqual((first_staging.stat().st_dev,
                          first_staging.stat().st_ino), first_identity)
        self.assertEqual((second_staging.stat().st_dev,
                          second_staging.stat().st_ino), second_identity)
        self.assertEqual(list(first_staging.iterdir()), [])
        self.assertEqual(list(second_staging.iterdir()), [])

    def test_nested_leaf_staging_directory_is_synced_before_bound_journal(self):
        missing = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)
        real_fsync = safeio.os.fsync
        real_update_journal = safeio._update_journal
        events = []
        leaf_directory_identity = None

        def record_leaf_write(staging, identity):
            nonlocal leaf_directory_identity
            leaf_directory = self.root / "rounds" / "one"
            details = leaf_directory.stat()
            leaf_directory_identity = (details.st_dev, details.st_ino)
            self.assertTrue((leaf_directory / staging).is_file())
            events.append(("leaf-write", identity))

        def record_fsync(fd):
            details = os.fstat(fd)
            if leaf_directory_identity is not None and stat.S_ISDIR(
                    details.st_mode):
                events.append(("directory-fsync",
                               (details.st_dev, details.st_ino)))
            return real_fsync(fd)

        def record_journal_update(directory_fd, name, state, **kwargs):
            if state["leaf"]["attempts"][-1]["status"] == "bound":
                events.append(("bound-journal", None))
            return real_update_journal(
                directory_fd, name, state, **kwargs)

        with mock.patch.object(
                safeio, "_after_leaf_staging_write",
                side_effect=record_leaf_write), mock.patch.object(
                    safeio.os, "fsync", side_effect=record_fsync), \
                mock.patch.object(
                    safeio, "_update_journal",
                    side_effect=record_journal_update):
            result = safeio.publish_exclusive(missing, b"answer\n")

        leaf_write_index = events.index(
            next(event for event in events if event[0] == "leaf-write"))
        bound_journal_index = events.index(
            next(event for event in events if event[0] == "bound-journal"))
        matching_fsyncs = [
            index for index, event in enumerate(events)
            if (event == ("directory-fsync", leaf_directory_identity) and
                leaf_write_index < index < bound_journal_index)
        ]
        self.assertTrue(
            matching_fsyncs,
            "the exact leaf staging directory was not fsynced before binding")
        self.assertEqual(result.data, b"answer\n")

    def test_prelink_cleanup_interruption_leaves_retryable_planned_attempt(self):
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)
        journal_removals = []

        def interrupt_vulnerable_journal_removal(journal):
            journal_removals.append(journal[1])
            raise OSError("injected cleanup interruption")

        with mock.patch.object(
                safeio, "_before_publish",
                side_effect=OSError("injected pre-link interruption")), \
                mock.patch.object(
                    safeio, "_remove_publication_journal",
                    side_effect=interrupt_vulnerable_journal_removal):
            with self.assertRaisesRegex(OSError, "pre-link interruption"):
                safeio.publish_exclusive(missing, b"published\n")

        self.assertEqual(len(journal_removals), 1)
        journal = next((self.root / "state").glob(".safeio-publish-*.json"))
        recorded = safeio.json.loads(journal.read_text(encoding="utf-8"))
        attempts = recorded["leaf"]["attempts"]
        self.assertEqual(
            [attempt["status"] for attempt in attempts],
            ["abandoned", "planned"])
        self.assertFalse(
            (self.root / "state" / attempts[0]["staging"]).exists())
        self.assertFalse(
            (self.root / "state" / attempts[1]["staging"]).exists())
        self.assertFalse((self.root / "state" / "published.bin").exists())

        result = safeio.publish_exclusive(missing, b"published\n")

        self.assertEqual(result.data, b"published\n")
        self.assertFalse(journal.exists())
        self.assertEqual(
            list((self.root / "state").glob(".safeio-leaf-*.tmp")), [])

    def test_repeated_leaf_interruptions_compact_retry_history(self):
        state = self.root / "state"
        data = b"published\n"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)
        limit = safeio._publication_journal_upper_bound(missing, data)

        def refuse_journal_removal(_journal):
            raise OSError("injected cleanup interruption")

        for attempt_number in range(12):
            with self.subTest(attempt=attempt_number), \
                    mock.patch.object(
                        safeio, "_PUBLICATION_JOURNAL_LIMIT", limit), \
                    mock.patch.object(
                        safeio, "_before_publish",
                        side_effect=OSError("injected pre-link interruption")), \
                    mock.patch.object(
                        safeio, "_remove_publication_journal",
                        side_effect=refuse_journal_removal):
                with self.assertRaisesRegex(OSError, "pre-link interruption"):
                    safeio.publish_exclusive(missing, data)

            journal = next(state.glob(".safeio-publish-*.json"))
            payload = journal.read_bytes()
            recorded = json.loads(payload)
            self.assertLessEqual(len(payload), limit)
            self.assertEqual(len(recorded["leaf"]["attempts"]), 2)
            self.assertEqual(
                [entry["status"] for entry in recorded["leaf"]["attempts"]],
                ["abandoned", "planned"])

        with mock.patch.object(
                safeio, "_PUBLICATION_JOURNAL_LIMIT", limit):
            result = safeio.publish_exclusive(missing, data)
        self.assertEqual(result.data, data)
        self.assertFalse(journal.exists())

    def test_planned_leaf_collision_is_preserved_while_publication_advances(self):
        state = self.root / "state"
        data = b"published\n"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)
        substituted = state / safeio._leaf_staging_name(
            missing.transaction_nonce, 0)
        substituted.write_bytes(b"not ours\n")
        identity = (substituted.stat().st_dev, substituted.stat().st_ino)

        result = safeio.publish_exclusive(missing, data)

        self.assertEqual(result.data, data)
        self.assertEqual(substituted.read_bytes(), b"not ours\n")
        self.assertEqual(
            (substituted.stat().st_dev, substituted.stat().st_ino), identity)

    def test_process_death_around_leaf_compaction_keeps_readable_recovery(self):
        for hook, exit_code in (
                ("_before_leaf_attempt_compaction", 171),
                ("_after_leaf_attempt_compaction_install", 172),
                ("_after_leaf_attempt_compaction", 173)):
            with self.subTest(hook=hook), tempfile.TemporaryDirectory() as raw:
                root = Path(raw).resolve()
                state = root / "state"
                state.mkdir()
                data = b"published\n"
                missing = safeio.snapshot_path(
                    root, "state/published.bin", allow_missing=True)

                with (mock.patch.object(
                        safeio, "_before_publish",
                        side_effect=OSError("injected pre-link interruption")),
                      mock.patch.object(
                          safeio, "_remove_publication_journal",
                          side_effect=OSError("injected cleanup interruption"))):
                    with self.assertRaisesRegex(OSError, "pre-link interruption"):
                        safeio.publish_exclusive(missing, data)

                source = f'''\
import os
import sys
from pathlib import Path, PurePosixPath
from scripts.factory.lib import safeio
missing = safeio.MissingSnapshot(
    root=Path(sys.argv[1]),
    relative=PurePosixPath(sys.argv[2]),
    parent_identities=tuple(tuple(value) for value in {list(map(list, missing.parent_identities))!r}),
    transaction_nonce={missing.transaction_nonce!r},
)
setattr(safeio, {hook!r}, lambda *_args: os._exit({exit_code}))
safeio.publish_exclusive(missing, b"published\\n")
'''
                environment = os.environ.copy()
                environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
                crashed = subprocess.run(
                    ["python3", "-c", source, str(root),
                     missing.relative.as_posix()],
                    cwd=Path(__file__).resolve().parents[1],
                    env=environment, capture_output=True, text=True)
                self.assertEqual(crashed.returncode, exit_code, crashed.stderr)

                journal = next(state.glob(".safeio-publish-*.json"))
                json.loads(journal.read_bytes())
                result = safeio.publish_exclusive(missing, data)
                self.assertEqual(result.data, data)
                self.assertFalse(journal.exists())

    def test_process_death_before_journal_update_install_keeps_old_authority(self):
        state = self.root / "state"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)
        source = f'''\
import os
import sys
from pathlib import Path, PurePosixPath
from scripts.factory.lib import safeio
missing = safeio.MissingSnapshot(
    root=Path(sys.argv[1]),
    relative=PurePosixPath(sys.argv[2]),
    parent_identities=tuple(tuple(value) for value in {list(map(list, missing.parent_identities))!r}),
    transaction_nonce={missing.transaction_nonce!r},
)
safeio._before_publication_journal_install = lambda: os._exit(174)
safeio.publish_exclusive(missing, b"published\\n")
'''
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        crashed = subprocess.run(
            ["python3", "-c", source, str(self.root),
             missing.relative.as_posix()],
            cwd=Path(__file__).resolve().parents[1],
            env=environment, capture_output=True, text=True)

        self.assertEqual(crashed.returncode, 174, crashed.stderr)
        journal = next(state.glob(".safeio-publish-*.json"))
        recorded = json.loads(journal.read_bytes())
        self.assertEqual(recorded["leaf"]["attempts"][0]["status"], "planned")
        result = safeio.publish_exclusive(missing, b"published\n")
        self.assertEqual(result.data, b"published\n")
        self.assertFalse(journal.exists())

    def test_journal_update_refuses_temp_substitution_at_install_seam(self):
        state = self.root / "state"
        destination = state / "published.bin"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)
        observed = {}

        def substitute_update_temporary():
            journal = state / safeio._journal_name(missing.relative)
            temporaries = list(state.glob(f".{journal.name}.tmp-*"))
            self.assertEqual(len(temporaries), 1)
            temporary = temporaries[0]
            observed["journal_bytes"] = journal.read_bytes()
            observed["journal_identity"] = (
                journal.stat().st_dev, journal.stat().st_ino)
            foreign = state / "foreign-update-temporary"
            foreign.write_bytes(b"foreign journal update\n")
            os.replace(foreign, temporary)
            observed["temporary"] = temporary
            observed["temporary_identity"] = (
                temporary.stat().st_dev, temporary.stat().st_ino)

        with mock.patch.object(
                safeio, "_before_publication_journal_install",
                side_effect=substitute_update_temporary):
            with self.assertRaisesRegex(
                    safeio.SafeIOError,
                    "replacement temporary|filesystem entry identity changed"):
                safeio.publish_exclusive(missing, b"published\n")

        journal = state / safeio._journal_name(missing.relative)
        self.assertEqual(journal.read_bytes(), observed["journal_bytes"])
        self.assertEqual(
            (journal.stat().st_dev, journal.stat().st_ino),
            observed["journal_identity"])
        temporary = observed["temporary"]
        self.assertEqual(temporary.read_bytes(), b"foreign journal update\n")
        self.assertEqual(
            (temporary.stat().st_dev, temporary.stat().st_ino),
            observed["temporary_identity"])
        self.assertFalse(destination.exists())

    def test_journal_parent_chain_is_revalidated_at_update_install(self):
        state = self.root / "state"
        detached = self.root / "state-detached"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)
        observed = {}

        def detach_parent():
            journal = next(state.glob(".safeio-publish-*.json"))
            observed["bytes"] = journal.read_bytes()
            observed["identity"] = (journal.stat().st_dev, journal.stat().st_ino)
            state.rename(detached)
            state.mkdir()

        with mock.patch.object(
                safeio, "_before_publication_journal_install",
                side_effect=detach_parent, create=True):
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "directory chain.*replaced"):
                safeio.publish_exclusive(missing, b"published\n")

        journal = next(detached.glob(".safeio-publish-*.json"))
        self.assertEqual(journal.read_bytes(), observed["bytes"])
        self.assertEqual(
            (journal.stat().st_dev, journal.stat().st_ino),
            observed["identity"])
        self.assertFalse((state / "published.bin").exists())

    def test_journal_substitution_after_leaf_bind_is_not_overwritten(self):
        state = self.root / "state"
        destination = state / "published.bin"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)
        substitution = {}

        def substitute_journal(_staging, _identity):
            journal = next(state.glob(".safeio-publish-*.json"))
            replacement = state / "foreign-journal.json"
            replacement.write_bytes(journal.read_bytes())
            os.replace(replacement, journal)
            substitution["bytes"] = journal.read_bytes()
            substitution["identity"] = (
                journal.stat().st_dev, journal.stat().st_ino)

        with mock.patch.object(
                safeio, "_after_leaf_bind",
                side_effect=substitute_journal):
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "journal.*changed"):
                safeio.publish_exclusive(missing, b"published\n")

        journal = next(state.glob(".safeio-publish-*.json"))
        self.assertEqual(journal.read_bytes(), substitution["bytes"])
        self.assertEqual(
            (journal.stat().st_dev, journal.stat().st_ino),
            substitution["identity"])
        self.assertFalse(destination.exists())
        recorded = json.loads(journal.read_bytes())
        staging = state / recorded["leaf"]["attempts"][-1]["staging"]
        self.assertEqual(staging.read_bytes(), b"published\n")

    def test_journal_substitution_before_leaf_compaction_is_not_overwritten(self):
        state = self.root / "state"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)

        with (mock.patch.object(
                safeio, "_before_publish",
                side_effect=OSError("injected pre-link interruption")),
              mock.patch.object(
                  safeio, "_remove_publication_journal",
                  side_effect=OSError("injected cleanup interruption"))):
            with self.assertRaisesRegex(OSError, "pre-link interruption"):
                safeio.publish_exclusive(missing, b"published\n")

        journal = next(state.glob(".safeio-publish-*.json"))
        foreign = b"foreign journal evidence\n"
        substitution = {}

        def substitute_journal():
            replacement = state / "foreign-journal.json"
            replacement.write_bytes(foreign)
            os.replace(replacement, journal)
            substitution["identity"] = (
                journal.stat().st_dev, journal.stat().st_ino)

        with mock.patch.object(
                safeio, "_before_leaf_attempt_compaction",
                side_effect=substitute_journal):
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "journal.*changed"):
                safeio.publish_exclusive(missing, b"published\n")

        self.assertEqual(journal.read_bytes(), foreign)
        self.assertEqual(
            (journal.stat().st_dev, journal.stat().st_ino),
            substitution["identity"])
        self.assertFalse((state / "published.bin").exists())

    def test_journal_substitution_during_leaf_compaction_is_preserved(self):
        state = self.root / "state"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)

        with (mock.patch.object(
                safeio, "_before_publish",
                side_effect=OSError("injected pre-link interruption")),
              mock.patch.object(
                  safeio, "_remove_publication_journal",
                  side_effect=OSError("injected cleanup interruption"))):
            with self.assertRaisesRegex(OSError, "pre-link interruption"):
                safeio.publish_exclusive(missing, b"published\n")

        journal = next(state.glob(".safeio-publish-*.json"))
        foreign = b"foreign journal evidence\n"
        substitution = {}

        def substitute_journal():
            replacement = state / "foreign-journal.json"
            replacement.write_bytes(foreign)
            os.replace(replacement, journal)
            substitution["identity"] = (
                journal.stat().st_dev, journal.stat().st_ino)

        with mock.patch.object(
                safeio, "_after_leaf_attempt_compaction_install",
                side_effect=substitute_journal):
            with self.assertRaises(safeio.SafeIOError):
                safeio.publish_exclusive(missing, b"published\n")

        self.assertEqual(journal.read_bytes(), foreign)
        self.assertEqual(
            (journal.stat().st_dev, journal.stat().st_ino),
            substitution["identity"])
        self.assertFalse((state / "published.bin").exists())

    def test_journal_substitution_after_directory_install_is_not_overwritten(self):
        journal_parent = self.root
        missing = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)
        substitution = {}

        def substitute_journal(component, _identity):
            if component != "rounds" or substitution:
                return
            journal = next(journal_parent.glob(".safeio-publish-*.json"))
            replacement = journal_parent / "foreign-journal.json"
            replacement.write_bytes(b"foreign journal evidence\n")
            os.replace(replacement, journal)
            substitution["path"] = journal
            substitution["identity"] = (
                journal.stat().st_dev, journal.stat().st_ino)

        with mock.patch.object(
                safeio, "_after_directory_install",
                side_effect=substitute_journal):
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "journal.*changed"):
                safeio.publish_exclusive(missing, b"answer\n")

        journal = substitution["path"]
        self.assertEqual(journal.read_bytes(), b"foreign journal evidence\n")
        self.assertEqual(
            (journal.stat().st_dev, journal.stat().st_ino),
            substitution["identity"])
        self.assertTrue((self.root / "rounds").is_dir())
        self.assertFalse((self.root / "rounds" / "one").exists())

    def test_in_place_journal_mutation_after_leaf_install_is_not_deleted(self):
        state = self.root / "state"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)
        foreign = b"foreign journal evidence\n"
        observed = {}

        def mutate_journal(_staging, _identity):
            journal = next(state.glob(".safeio-publish-*.json"))
            journal.write_bytes(foreign)
            observed["path"] = journal
            observed["identity"] = (
                journal.stat().st_dev, journal.stat().st_ino)

        with mock.patch.object(
                safeio, "_after_leaf_install",
                side_effect=mutate_journal):
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "journal.*changed"):
                safeio.publish_exclusive(missing, b"published\n")

        journal = observed["path"]
        self.assertEqual(journal.read_bytes(), foreign)
        self.assertEqual(
            (journal.stat().st_dev, journal.stat().st_ino),
            observed["identity"])
        self.assertEqual(
            (state / "published.bin").read_bytes(), b"published\n")

    def test_leaf_publication_recovers_at_every_identity_transfer_boundary(self):
        boundaries = (
            ("_after_leaf_staging_write", "preparing", False, True),
            ("_after_leaf_bind", "bound", False, True),
            ("_after_leaf_link", "bound", True, True),
            ("_after_leaf_unlink", "bound", True, False),
            ("_after_leaf_install", "installed", True, False),
        )
        for hook, status, destination_exists, staging_exists in boundaries:
            with self.subTest(hook=hook), tempfile.TemporaryDirectory() as raw:
                root = Path(raw).resolve()
                state = root / "state"
                state.mkdir()
                missing = safeio.snapshot_path(
                    root, "state/published.bin", allow_missing=True)

                with mock.patch.object(
                        safeio, hook,
                        side_effect=OSError("injected leaf interruption"),
                        create=True):
                    with self.assertRaisesRegex(
                            OSError, "leaf interruption"):
                        safeio.publish_exclusive(missing, b"published\n")

                journal = next(state.glob(".safeio-publish-*.json"))
                recorded = safeio.json.loads(
                    journal.read_text(encoding="utf-8"))
                attempt = recorded["leaf"]["attempts"][-1]
                self.assertEqual(attempt["status"], status)
                self.assertEqual(
                    (state / "published.bin").exists(), destination_exists)
                self.assertEqual(
                    (state / attempt["staging"]).exists(), staging_exists)

                result = safeio.publish_exclusive(missing, b"published\n")

                self.assertEqual(result.data, b"published\n")
                self.assertFalse(journal.exists())
                remaining = list(state.glob(".safeio-leaf-*.tmp"))
                self.assertEqual(remaining, [])

    def test_leaf_staging_same_byte_fsync_replacement_is_never_authorized(self):
        state = self.root / "state"
        destination = state / "published.bin"
        data = b"published\n"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)
        real_fsync = safeio.os.fsync
        substitution = {}

        def replace_during_leaf_fsync(fd):
            details = os.fstat(fd)
            staging_files = list(state.glob(".safeio-leaf-*.tmp"))
            if staging_files and not substitution:
                staging = staging_files[0]
                named = staging.stat()
                if (details.st_dev, details.st_ino) == (
                        named.st_dev, named.st_ino):
                    real_fsync(fd)
                    substitution["opened"] = safeio._file_identity(details)
                    foreign = state / "same-byte-foreign.tmp"
                    foreign.write_bytes(data)
                    os.replace(foreign, staging)
                    substitution["path"] = staging
                    substitution["identity"] = safeio._file_identity(
                        staging.stat())
                    return None
            return real_fsync(fd)

        with mock.patch.object(
                safeio.os, "fsync", side_effect=replace_during_leaf_fsync):
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "staging.*identity|staging.*changed"):
                safeio.publish_exclusive(missing, data)

        staging = substitution["path"]
        journal = state / safeio._journal_name(missing.relative)
        recorded = json.loads(journal.read_bytes())
        attempt = recorded["leaf"]["attempts"][-1]
        self.assertEqual(attempt["status"], "preparing")
        self.assertEqual(tuple(attempt["identity"]), substitution["opened"])
        self.assertNotEqual(
            tuple(attempt["identity"]), substitution["identity"])

        for _retry in range(2):
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "staging identity conflicts"):
                safeio.publish_exclusive(missing, data)
            self.assertFalse(destination.exists())
            self.assertEqual(staging.read_bytes(), data)
            self.assertEqual(
                safeio._file_identity(staging.stat()),
                substitution["identity"])

    def test_leaf_link_interval_requires_exact_five_field_identity(self):
        state = self.root / "state"
        destination = state / "published.bin"
        data = b"published\n"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)

        def rewrite_same_bytes(_staging, linked_identity):
            before = destination.stat()
            destination.write_bytes(data)
            os.utime(
                destination,
                ns=(before.st_atime_ns, before.st_mtime_ns))
            os.chmod(destination, 0o640)
            changed = safeio._file_identity(destination.stat())
            self.assertEqual(changed[:4], linked_identity[:4])
            self.assertNotEqual(changed, linked_identity)

        with mock.patch.object(
                safeio, "_after_leaf_link", side_effect=rewrite_same_bytes):
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "destination identity conflicts"):
                safeio.publish_exclusive(missing, data)

        self.assertEqual(destination.read_bytes(), data)
        self.assertEqual(len(list(state.glob(".safeio-leaf-*.tmp"))), 1)
        self.assertEqual(len(list(state.glob(".safeio-publish-*.json"))), 1)

    def test_leaf_unlink_interval_requires_exact_five_field_identity(self):
        state = self.root / "state"
        destination = state / "published.bin"
        data = b"published\n"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)

        def rewrite_same_bytes(_staging, pre_unlink_identity):
            before = destination.stat()
            destination.write_bytes(data)
            os.utime(
                destination,
                ns=(before.st_atime_ns, before.st_mtime_ns))
            os.chmod(destination, 0o640)
            changed = safeio._file_identity(destination.stat())
            self.assertEqual(changed[:4], pre_unlink_identity[:4])
            self.assertNotEqual(changed, pre_unlink_identity)

        with mock.patch.object(
                safeio, "_after_leaf_unlink", side_effect=rewrite_same_bytes):
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "destination identity conflicts"):
                safeio.publish_exclusive(missing, data)

        self.assertEqual(destination.read_bytes(), data)
        self.assertEqual(list(state.glob(".safeio-leaf-*.tmp")), [])
        self.assertEqual(len(list(state.glob(".safeio-publish-*.json"))), 1)

    def test_leaf_link_adoption_fsyncs_before_staging_unlink(self):
        for path in ("new-link", "already-linked-recovery"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as raw:
                root = Path(raw).resolve()
                state = root / "state"
                state.mkdir()
                missing = safeio.snapshot_path(
                    root, "state/published.bin", allow_missing=True)

                if path == "already-linked-recovery":
                    with mock.patch.object(
                            safeio, "_after_leaf_link",
                            side_effect=OSError("injected after-link crash")):
                        with self.assertRaisesRegex(OSError, "after-link"):
                            safeio.publish_exclusive(missing, b"published\n")

                journal = state / safeio._journal_name(missing.relative)
                staging = safeio._leaf_staging_name(
                    missing.transaction_nonce, 0)
                directory_identity = (state.stat().st_dev, state.stat().st_ino)
                events = []
                real_destination_state = safeio._destination_leaf_state
                real_fsync = safeio.os.fsync
                real_unlink = safeio._unlink_if_identity

                def record_destination(directory_fd, name, expected_identity):
                    result = real_destination_state(
                        directory_fd, name, expected_identity)
                    if name == "published.bin" and result == "exact":
                        events.append("exact-destination")
                    return result

                def record_fsync(fd):
                    details = os.fstat(fd)
                    if (stat.S_ISDIR(details.st_mode) and
                            (details.st_dev, details.st_ino) ==
                            directory_identity):
                        events.append("directory-fsync")
                    return real_fsync(fd)

                def record_unlink(directory_fd, name, expected_identity):
                    if name == staging:
                        events.append("staging-unlink")
                    return real_unlink(directory_fd, name, expected_identity)

                with mock.patch.object(
                        safeio, "_destination_leaf_state",
                        side_effect=record_destination), mock.patch.object(
                            safeio.os, "fsync", side_effect=record_fsync), \
                        mock.patch.object(
                            safeio, "_unlink_if_identity",
                            side_effect=record_unlink), mock.patch.object(
                            safeio, "_after_leaf_unlink",
                            side_effect=OSError("injected after-unlink crash")):
                    with self.assertRaisesRegex(OSError, "after-unlink"):
                        safeio.publish_exclusive(missing, b"published\n")

                exact_index = events.index("exact-destination")
                unlink_index = events.index("staging-unlink")
                self.assertIn(
                    "directory-fsync", events[exact_index + 1:unlink_index],
                    events)
                self.assertTrue((state / "published.bin").is_file())
                self.assertFalse((state / staging).exists())

                result = safeio.publish_exclusive(missing, b"published\n")

                self.assertEqual(result.data, b"published\n")
                self.assertFalse(journal.exists())

    def test_substituted_abandoned_leaf_refuses_cleanup_and_retries(self):
        state = self.root / "state"
        destination = state / "published.bin"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)

        with mock.patch.object(
                safeio, "_after_leaf_staging_write",
                side_effect=OSError("injected staging interruption")):
            with self.assertRaisesRegex(OSError, "staging interruption"):
                safeio.publish_exclusive(missing, b"published\n")

        journal = next(state.glob(".safeio-publish-*.json"))
        recorded = safeio.json.loads(journal.read_text(encoding="utf-8"))
        abandoned = recorded["leaf"]["attempts"][0]
        abandoned_path = state / abandoned["staging"]
        abandoned["identity"] = list(safeio._file_identity(
            abandoned_path.stat()))
        abandoned["status"] = "abandoned"
        recorded["leaf"]["attempts"].append(
            safeio._new_leaf_attempt(recorded["nonce"], 1))
        journal.write_bytes(safeio._journal_bytes(recorded))

        substitute = state / "substitute.bin"
        substitute.write_bytes(b"do not delete\n")
        os.replace(substitute, abandoned_path)
        substitute_identity = (
            abandoned_path.stat().st_dev, abandoned_path.stat().st_ino)
        planned_path = state / recorded["leaf"]["attempts"][1]["staging"]

        for _retry in range(2):
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "staging identity conflicts"):
                safeio.publish_exclusive(missing, b"published\n")
            self.assertTrue(journal.is_file())
            self.assertEqual(
                (abandoned_path.stat().st_dev,
                 abandoned_path.stat().st_ino),
                substitute_identity)
            self.assertEqual(abandoned_path.read_bytes(), b"do not delete\n")
            self.assertFalse(planned_path.exists())
            self.assertFalse(destination.exists())

        abandoned_path.unlink()
        result = safeio.publish_exclusive(missing, b"published\n")
        self.assertEqual(result.data, b"published\n")
        self.assertFalse(journal.exists())

    def test_prelink_cleanup_substitution_retains_authority_on_retry(self):
        state = self.root / "state"
        destination = state / "published.bin"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)
        real_refresh = safeio._refresh_publication_journal
        substitution = {}

        def substitute_after_abandon(journal):
            result = real_refresh(journal)
            attempts = journal[3]["leaf"]["attempts"]
            if (not substitution and len(attempts) == 2 and
                    attempts[0]["status"] == "abandoned" and
                    attempts[1]["status"] == "planned"):
                staging = state / attempts[0]["staging"]
                substitute = state / "substitute.bin"
                substitute.write_bytes(b"do not delete\n")
                os.replace(substitute, staging)
                substitution["path"] = staging
                substitution["identity"] = (
                    staging.stat().st_dev, staging.stat().st_ino)
            return result

        with mock.patch.object(
                safeio, "_before_publish",
                side_effect=OSError("injected pre-link interruption")), \
                mock.patch.object(
                    safeio, "_refresh_publication_journal",
                    side_effect=substitute_after_abandon):
            with self.assertRaisesRegex(OSError, "pre-link interruption"):
                safeio.publish_exclusive(missing, b"published\n")

        journal = state / safeio._journal_name(missing.relative)
        self.assertTrue(journal.is_file())
        substituted_path = substitution["path"]
        with self.assertRaisesRegex(
                safeio.SafeIOError, "staging identity conflicts"):
            safeio.publish_exclusive(missing, b"published\n")

        self.assertTrue(journal.is_file())
        self.assertEqual(
            (substituted_path.stat().st_dev,
             substituted_path.stat().st_ino),
            substitution["identity"])
        self.assertEqual(substituted_path.read_bytes(), b"do not delete\n")
        self.assertFalse(destination.exists())

    def test_leaf_publication_refuses_same_byte_destination_substitution(self):
        for hook in ("_after_leaf_link", "_after_leaf_unlink"):
            with self.subTest(hook=hook), tempfile.TemporaryDirectory() as raw:
                root = Path(raw).resolve()
                state = root / "state"
                state.mkdir()
                destination = state / "published.bin"
                missing = safeio.snapshot_path(
                    root, "state/published.bin", allow_missing=True)

                with mock.patch.object(
                        safeio, hook,
                        side_effect=OSError("injected leaf interruption"),
                        create=True):
                    with self.assertRaisesRegex(
                            OSError, "leaf interruption"):
                        safeio.publish_exclusive(missing, b"published\n")

                substitute = state / "substitute.bin"
                substitute.write_bytes(b"published\n")
                os.replace(substitute, destination)

                with self.assertRaisesRegex(
                        safeio.SafeIOError, "identity|conflict"):
                    safeio.publish_exclusive(missing, b"published\n")
                self.assertEqual(destination.read_bytes(), b"published\n")

    def test_leaf_link_foreign_destination_substitution_is_preserved(self):
        state = self.root / "state"
        destination = state / "published.bin"
        missing = safeio.snapshot_path(
            self.root, "state/published.bin", allow_missing=True)
        foreign = b"foreign destination\n"
        substitution = {}

        def substitute_destination(_staging, _identity):
            replacement = state / "foreign.bin"
            replacement.write_bytes(foreign)
            os.replace(replacement, destination)
            substitution["identity"] = (
                destination.stat().st_dev, destination.stat().st_ino)

        with mock.patch.object(
                safeio, "_after_leaf_link",
                side_effect=substitute_destination):
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "destination identity conflicts"):
                safeio.publish_exclusive(missing, b"published\n")

        self.assertEqual(destination.read_bytes(), foreign)
        self.assertEqual(
            (destination.stat().st_dev, destination.stat().st_ino),
            substitution["identity"])
        journal = next(state.glob(".safeio-publish-*.json"))
        recorded = json.loads(journal.read_bytes())
        self.assertEqual(recorded["leaf"]["attempts"][-1]["status"], "bound")

    def test_malformed_recovery_staging_names_cannot_escape_or_mutate(self):
        cases = ("absolute", "traversal", "backslash", "dot", "symlink")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as base:
                base_path = Path(base)
                root = base_path / "root"
                outside = base_path / "outside"
                root.mkdir()
                outside.mkdir()
                sentinel = outside / "sentinel"
                sentinel.write_bytes(b"unchanged")
                missing = safeio.snapshot_path(
                    root, "rounds/one/answer.md", allow_missing=True)

                with mock.patch.object(
                        safeio, "_after_staging_mkdir",
                        side_effect=OSError("injected mkdir interruption"),
                        create=True):
                    with self.assertRaisesRegex(OSError, "mkdir interruption"):
                        safeio.publish_exclusive(missing, b"answer\n")

                journal = next(root.glob(".safeio-publish-*.json"))
                state = safeio.json.loads(journal.read_text(encoding="utf-8"))
                attempt = state["directories"][0]["attempts"][0]
                if case == "absolute":
                    attempt["staging"] = str(outside)
                elif case == "traversal":
                    attempt["staging"] = f"../{outside.name}"
                elif case == "backslash":
                    attempt["staging"] = f"..\\{outside.name}"
                elif case == "dot":
                    attempt["staging"] = "."
                else:
                    redirect = root / "redirect"
                    redirect.symlink_to(outside, target_is_directory=True)
                    attempt["staging"] = redirect.name
                journal.write_bytes(safeio._journal_bytes(state))

                with self.assertRaises(safeio.SafeIOError):
                    safeio.publish_exclusive(missing, b"answer\n")

                self.assertTrue(outside.is_dir())
                self.assertEqual(sentinel.read_bytes(), b"unchanged")
                self.assertFalse((outside / "one" / "answer.md").exists())
                self.assertFalse((root / "rounds" / "one" / "answer.md").exists())

    def test_missing_tail_retry_refuses_replaced_created_directory(self):
        missing = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)

        with mock.patch.object(
                safeio, "_after_directory_install",
                side_effect=OSError("injected interruption"), create=True):
            with self.assertRaisesRegex(OSError, "injected interruption"):
                safeio.publish_exclusive(missing, b"answer\n")

        created = self.root / "rounds"
        created.rename(self.root / "rounds-created")
        created.mkdir()
        with self.assertRaises(safeio.SafeIOError):
            safeio.publish_exclusive(missing, b"answer\n")
        self.assertFalse((created / "one" / "answer.md").exists())

    def test_interrupted_tail_fresh_observation_cannot_bypass_identity_retry(self):
        missing = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)
        with mock.patch.object(
                safeio, "_after_directory_install",
                side_effect=OSError("injected interruption")):
            with self.assertRaisesRegex(OSError, "injected interruption"):
                safeio.publish_exclusive(missing, b"answer\n")

        with self.assertRaises(safeio.SafeIOError):
            safeio.publish_exclusive(
                self.root, "rounds/one/answer.md", b"answer\n")
        self.assertFalse(
            (self.root / "rounds" / "one" / "answer.md").exists())

    def test_interrupted_tail_fresh_missing_snapshot_cannot_bypass_recovery(self):
        original = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)
        with mock.patch.object(
                safeio, "_after_directory_install",
                side_effect=OSError("injected interruption")):
            with self.assertRaisesRegex(OSError, "injected interruption"):
                safeio.publish_exclusive(original, b"answer\n")

        fresh = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)
        self.assertIsInstance(fresh, safeio.MissingSnapshot)
        self.assertNotEqual(fresh.parent_identities,
                            original.parent_identities)

        with self.assertRaisesRegex(
                safeio.SafeIOError,
                "interrupted publication requires its original MissingSnapshot"):
            safeio.publish_exclusive(fresh, b"answer\n")

        self.assertFalse(
            (self.root / "rounds" / "one" / "answer.md").exists())

    def test_fresh_missing_snapshot_cannot_adopt_same_parent_recovery(self):
        original = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)
        with mock.patch.object(
                safeio.os, "mkdir",
                side_effect=OSError("injected pre-mkdir interruption")):
            with self.assertRaisesRegex(
                    safeio.SafeIOError, "could not create publication directory"):
                safeio.publish_exclusive(original, b"answer\n")

        fresh = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)
        self.assertEqual(fresh.parent_identities,
                         original.parent_identities)
        self.assertNotEqual(fresh.transaction_nonce,
                            original.transaction_nonce)

        with self.assertRaisesRegex(
                safeio.SafeIOError, "publication recovery record conflicts"):
            safeio.publish_exclusive(fresh, b"answer\n")

        self.assertFalse((self.root / "rounds").exists())

    def test_missing_snapshot_refuses_unexpected_tail_without_artifacts(self):
        missing = safeio.snapshot_path(
            self.root, "rounds/one/answer.md", allow_missing=True)
        (self.root / "rounds").mkdir()

        with self.assertRaises(safeio.SafeIOError):
            safeio.publish_exclusive(missing, b"answer\n")

        self.assertEqual(list(self.root.glob(".safeio-*")), [])
        self.assertEqual(list((self.root / "rounds").iterdir()), [])

    def test_sibling_publication_does_not_invalidate_directory_identity(self):
        snapshot = safeio.snapshot_path(self.root, "state/value.bin")
        safeio.publish_exclusive(self.root, "state/sibling.bin", b"sibling")
        safeio.revalidate(snapshot)

    def test_publish_exclusive_refuses_symlink_in_missing_tail(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "state" / "redirect").symlink_to(
            outside, target_is_directory=True)

        with self.assertRaises(safeio.SafeIOError):
            safeio.publish_exclusive(
                self.root, "state/redirect/answer.md", b"answer")
        self.assertEqual(list(outside.iterdir()), [])

    def test_publish_rejects_parent_replacement_before_final_verification(self):
        def swap_parent():
            original = self.root / "published"
            original.rename(self.root / "published-detached")
            original.mkdir()

        with mock.patch.object(
                safeio, "_before_publish", side_effect=swap_parent):
            with self.assertRaises(safeio.SafeIOError):
                safeio.publish_exclusive(
                    self.root, "published/value", b"data")
        self.assertFalse(
            (self.root / "published-detached" / "value").exists())

    def test_publish_refuses_every_ancestor_at_final_install_seam(self):
        for level in ("root", "outer", "inner"):
            with self.subTest(level=level), tempfile.TemporaryDirectory() as raw:
                root = Path(raw).resolve()
                inner = root / "outer" / "inner"
                inner.mkdir(parents=True, exist_ok=True)
                targets = {
                    "root": root,
                    "outer": root / "outer",
                    "inner": inner,
                }
                original = targets[level]
                moved = original.with_name(original.name + "-detached")

                def detach():
                    original.rename(moved)
                    original.mkdir()

                try:
                    with mock.patch.object(
                            safeio, "_before_publish", side_effect=detach):
                        with self.assertRaises(safeio.SafeIOError):
                            safeio.publish_exclusive(
                                root, "outer/inner/value", b"data")
                    moved_value = (moved / "outer" / "inner" / "value"
                                   if level == "root" else
                                   moved / "inner" / "value"
                                   if level == "outer" else moved / "value")
                    self.assertFalse(moved_value.exists())
                finally:
                    original.rmdir()
                    moved.rename(original)

    def test_publish_temp_substitution_is_not_left_at_destination(self):
        outside = self.root / "outside.bin"
        outside.write_bytes(b"outside")

        def substitute_temp():
            temp = next((self.root / "state").glob(".safeio-*.tmp"))
            temp.unlink()
            temp.symlink_to(outside)

        with mock.patch.object(
                safeio, "_before_publish", side_effect=substitute_temp):
            with self.assertRaises(safeio.SafeIOError):
                safeio.publish_exclusive(
                    self.root, "state/published.bin", b"published")

        self.assertFalse((self.root / "state" / "published.bin").exists())

    def test_publish_post_install_substitution_is_preserved(self):
        outside = self.root / "outside.bin"
        outside.write_bytes(b"outside")
        real_link = safeio.os.link

        def link_then_substitute(source, destination, **kwargs):
            result = real_link(source, destination, **kwargs)
            if destination == "published.bin":
                parent_fd = kwargs["dst_dir_fd"]
                os.unlink(destination, dir_fd=parent_fd)
                os.symlink(str(outside), destination, dir_fd=parent_fd)
            return result

        with mock.patch.object(safeio.os, "link",
                               side_effect=link_then_substitute):
            with self.assertRaises(safeio.SafeIOError):
                safeio.publish_exclusive(
                    self.root, "state/published.bin", b"published")

        destination = self.root / "state" / "published.bin"
        self.assertTrue(destination.is_symlink())
        self.assertEqual(destination.read_bytes(), b"outside")

    def test_replace_if_unchanged_is_atomic_and_refuses_mismatch(self):
        snapshot = safeio.snapshot_path(self.root, "state/value.bin")
        replaced = safeio.replace_if_unchanged(snapshot, b"after")
        self.assertEqual(replaced.data, b"after")
        self.assertEqual(
            (self.root / "state" / "value.bin").read_bytes(), b"after")

        with self.assertRaises(safeio.SafeIOError):
            safeio.replace_if_unchanged(snapshot, b"must-not-win")
        self.assertEqual(
            (self.root / "state" / "value.bin").read_bytes(), b"after")

    def test_replace_if_unchanged_checks_again_after_temp_write(self):
        snapshot = safeio.snapshot_path(self.root, "state/value.bin")

        def mutate():
            (self.root / "state" / "value.bin").write_bytes(b"racer")

        with mock.patch.object(safeio, "_before_replace", side_effect=mutate):
            with self.assertRaises(safeio.SafeIOError):
                safeio.replace_if_unchanged(snapshot, b"after")
        self.assertEqual(
            (self.root / "state" / "value.bin").read_bytes(), b"racer")

    def test_replace_serializes_cooperative_writers_through_install(self):
        first_snapshot = safeio.snapshot_path(self.root, "state/value.bin")
        second_snapshot = safeio.snapshot_path(self.root, "state/value.bin")
        first_at_install = threading.Event()
        release_first = threading.Event()
        calls = []
        outcomes = []

        def pause_first_install():
            calls.append(threading.current_thread().name)
            if len(calls) == 1:
                first_at_install.set()
                self.assertTrue(release_first.wait(2))

        def replace(snapshot, data):
            try:
                outcomes.append(safeio.replace_if_unchanged(snapshot, data))
            except BaseException as exc:
                outcomes.append(exc)

        with mock.patch.object(
                safeio, "_before_replace_install",
                side_effect=pause_first_install, create=True):
            first = threading.Thread(
                target=replace, args=(first_snapshot, b"first"), name="first")
            second = threading.Thread(
                target=replace, args=(second_snapshot, b"second"), name="second")
            first.start()
            self.assertTrue(first_at_install.wait(2))
            second.start()
            second.join(0.05)
            self.assertTrue(second.is_alive())
            self.assertEqual(calls, ["first"])
            release_first.set()
            first.join(2)
            second.join(2)

        self.assertEqual(len(outcomes), 2)
        self.assertEqual(sum(isinstance(value, safeio.FileSnapshot)
                             for value in outcomes), 1)
        self.assertEqual(sum(isinstance(value, safeio.SafeIOError)
                             for value in outcomes), 1)
        self.assertEqual(
            (self.root / "state" / "value.bin").read_bytes(), b"first")

    def test_replace_refuses_leaf_change_at_final_install_seam(self):
        snapshot = safeio.snapshot_path(self.root, "state/value.bin")

        def mutate_at_install():
            (self.root / "state" / "value.bin").write_bytes(b"racer")

        with mock.patch.object(
                safeio, "_before_replace_install",
                side_effect=mutate_at_install, create=True):
            with self.assertRaises(safeio.SafeIOError):
                safeio.replace_if_unchanged(snapshot, b"after")
        self.assertEqual(
            (self.root / "state" / "value.bin").read_bytes(), b"racer")

    def test_replace_refuses_detached_parent_at_final_install_seam(self):
        snapshot = safeio.snapshot_path(self.root, "state/value.bin")

        def detach_at_install():
            state = self.root / "state"
            state.rename(self.root / "state-detached")
            state.mkdir()
            (state / "value.bin").write_bytes(b"current")

        with mock.patch.object(
                safeio, "_before_replace_install",
                side_effect=detach_at_install, create=True):
            with self.assertRaises(safeio.SafeIOError):
                safeio.replace_if_unchanged(snapshot, b"after")
        self.assertEqual(
            (self.root / "state-detached" / "value.bin").read_bytes(),
            b"before")
        self.assertEqual(
            (self.root / "state" / "value.bin").read_bytes(), b"current")

    def test_replace_refuses_every_ancestor_at_final_install_seam(self):
        for level in ("root", "outer", "inner"):
            with self.subTest(level=level):
                inner = self.root / "outer" / "inner"
                inner.mkdir(parents=True, exist_ok=True)
                value = inner / "value"
                value.write_bytes(b"before")
                snapshot = safeio.snapshot_path(
                    self.root, "outer/inner/value")
                targets = {
                    "root": self.root,
                    "outer": self.root / "outer",
                    "inner": inner,
                }
                original = targets[level]
                moved = original.with_name(original.name + "-detached")

                def detach():
                    original.rename(moved)
                    original.mkdir()

                try:
                    with mock.patch.object(
                            safeio, "_before_replace_install",
                            side_effect=detach):
                        with self.assertRaises(safeio.SafeIOError):
                            safeio.replace_if_unchanged(snapshot, b"after")
                    moved_value = (moved / "outer" / "inner" / "value"
                                   if level == "root" else
                                   moved / "inner" / "value"
                                   if level == "outer" else moved / "value")
                    self.assertEqual(moved_value.read_bytes(), b"before")
                finally:
                    original.rmdir()
                    moved.rename(original)

    def test_replace_temp_substitution_is_not_left_at_destination(self):
        snapshot = safeio.snapshot_path(self.root, "state/value.bin")
        outside = self.root / "outside.bin"
        outside.write_bytes(b"outside")

        def substitute_temp():
            temp = next((self.root / "state").glob(".value.bin.tmp-*"))
            temp.unlink()
            temp.symlink_to(outside)

        with mock.patch.object(
                safeio, "_before_replace", side_effect=substitute_temp):
            with self.assertRaises(safeio.SafeIOError):
                safeio.replace_if_unchanged(snapshot, b"after")

        destination = self.root / "state" / "value.bin"
        self.assertFalse(destination.is_symlink())
        self.assertEqual(destination.read_bytes(), b"before")

    def test_replace_post_install_substitution_is_preserved(self):
        snapshot = safeio.snapshot_path(self.root, "state/value.bin")
        outside = self.root / "outside.bin"
        outside.write_bytes(b"outside")
        real_replace = safeio.os.replace

        def replace_then_substitute(source, destination, **kwargs):
            result = real_replace(source, destination, **kwargs)
            if (isinstance(source, str) and
                    source.startswith(".value.bin.tmp-")):
                parent_fd = kwargs["dst_dir_fd"]
                os.unlink(destination, dir_fd=parent_fd)
                os.symlink(str(outside), destination, dir_fd=parent_fd)
            return result

        with mock.patch.object(safeio.os, "replace",
                               side_effect=replace_then_substitute):
            with self.assertRaises(safeio.SafeIOError):
                safeio.replace_if_unchanged(snapshot, b"after")

        destination = self.root / "state" / "value.bin"
        self.assertTrue(destination.is_symlink())
        self.assertEqual(destination.read_bytes(), b"outside")

    def test_replace_rejects_parent_replacement_before_final_verification(self):
        snapshot = safeio.snapshot_path(self.root, "state/value.bin")
        real_replace = safeio.os.replace

        def replace_then_swap_parent(source, destination, **kwargs):
            result = real_replace(source, destination, **kwargs)
            if (isinstance(source, str) and
                    source.startswith(".value.bin.tmp-")):
                state = self.root / "state"
                state.rename(self.root / "state-detached")
                state.mkdir()
                (state / "value.bin").write_bytes(b"after")
            return result

        with mock.patch.object(safeio.os, "replace",
                               side_effect=replace_then_swap_parent):
            with self.assertRaises(safeio.SafeIOError):
                safeio.replace_if_unchanged(snapshot, b"after")


if __name__ == "__main__":
    unittest.main()
