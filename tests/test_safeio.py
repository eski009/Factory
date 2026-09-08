import hashlib
import os
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
            with self.subTest(level=level):
                inner = self.root / "outer" / "inner"
                inner.mkdir(parents=True, exist_ok=True)
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
                            safeio, "_before_publish", side_effect=detach):
                        with self.assertRaises(safeio.SafeIOError):
                            safeio.publish_exclusive(
                                self.root, "outer/inner/value", b"data")
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

    def test_publish_post_install_substitution_is_removed(self):
        outside = self.root / "outside.bin"
        outside.write_bytes(b"outside")
        real_link = safeio.os.link

        def link_then_substitute(source, destination, **kwargs):
            result = real_link(source, destination, **kwargs)
            parent_fd = kwargs["dst_dir_fd"]
            os.unlink(destination, dir_fd=parent_fd)
            os.symlink(str(outside), destination, dir_fd=parent_fd)
            return result

        with mock.patch.object(safeio.os, "link",
                               side_effect=link_then_substitute):
            with self.assertRaises(safeio.SafeIOError):
                safeio.publish_exclusive(
                    self.root, "state/published.bin", b"published")

        self.assertFalse((self.root / "state" / "published.bin").exists())

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

    def test_replace_post_install_substitution_is_removed(self):
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
        self.assertFalse(destination.exists())

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
