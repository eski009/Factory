import fcntl
import io
import json
import os
import stat
import subprocess
import tempfile
import threading
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.factory import factory
from scripts.factory.lib import control, initrepo, items, logs


class TestLogs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_append_and_read(self):
        logs.append_event(self.repo, "0001-x", "item.created")
        logs.append_event(self.repo, "0001-x", "review.rejected", {"round": 1})
        events = logs.read_events(self.repo, "0001-x")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event"], "item.created")
        self.assertEqual(events[0]["ts"], "2026-07-03T12:00:00Z")
        self.assertEqual(events[1]["data"], {"round": 1})

    def test_supplied_descriptor_appends_despite_current_offset(self):
        logs.append_event(self.repo, "0001-x", "item.created")
        path = self.repo / ".factory/items/0001-x/log.jsonl"
        before = path.read_bytes()
        with path.open("r+b") as stream:
            logs.append_event(self.repo, "0001-x", "sentinel",
                              file_fd=stream.fileno())
        self.assertTrue(path.read_bytes().startswith(before))
        self.assertEqual([e["event"] for e in logs.read_events(self.repo, "0001-x")],
                         ["item.created", "sentinel"])

    def legacy_shared_supplied_descriptor_preserves_intervening_append(self):
        logs.append_event(self.repo, "0001-x", "preexisting")
        path = self.repo / ".factory/items/0001-x/log.jsonl"
        hostile = b"\xff preexisting bytes\n"
        path.write_bytes(path.read_bytes() + hostile)
        before = path.read_bytes()

        original_append_lock = logs.append_lock
        a_at_lock = threading.Event()
        b_at_lock = threading.Event()
        resume_b = threading.Event()
        b_observed_append = []
        errors = []

        @contextmanager
        def coordinated_append_lock(file_fd):
            name = threading.current_thread().name
            if name == "shared-a":
                # On the vulnerable path B can reach this point while A owns
                # the same open-file-description flock. With synchronization,
                # A proceeds after the bounded wait and B follows it.
                a_at_lock.set()
                b_at_lock.wait(0.5)
            elif name == "shared-b":
                b_at_lock.set()
                if not resume_b.wait(5):
                    raise AssertionError("timed out waiting to resume B")
                b_observed_append.append(bool(
                    fcntl.fcntl(file_fd, fcntl.F_GETFL) & os.O_APPEND))
            with original_append_lock(file_fd):
                yield

        def append_in_thread(event, file_fd):
            try:
                logs.append_event(self.repo, "0001-x", event, file_fd=file_fd)
            except BaseException as exc:
                errors.append(exc)

        with path.open("r+b") as shared:
            original_flags = fcntl.fcntl(shared.fileno(), fcntl.F_GETFL)
            with mock.patch.object(logs, "append_lock",
                                   side_effect=coordinated_append_lock):
                thread_a = threading.Thread(
                    target=append_in_thread, args=("a", shared.fileno()),
                    name="shared-a")
                thread_b = threading.Thread(
                    target=append_in_thread, args=("b", shared.fileno()),
                    name="shared-b")
                thread_a.start()
                self.assertTrue(a_at_lock.wait(2), "A did not reach append lock")
                thread_b.start()
                thread_a.join(2)
                self.assertFalse(thread_a.is_alive(), "A deadlocked")
                self.assertTrue(b_at_lock.wait(2), "B did not reach append lock")
                try:
                    logs.append_event(self.repo, "0001-x", "c")
                finally:
                    resume_b.set()
                thread_b.join(2)
                self.assertFalse(thread_b.is_alive(), "B deadlocked")
            restored_flags = fcntl.fcntl(shared.fileno(), fcntl.F_GETFL)

        self.assertEqual(errors, [])
        self.assertEqual(b_observed_append, [True])
        # Darwin exposes private flock bookkeeping in F_GETFL after the first
        # lock operation. Compare every caller-controllable status flag.
        restorable_flags = (os.O_ACCMODE | os.O_APPEND | os.O_NONBLOCK
                            | os.O_ASYNC)
        self.assertEqual(restored_flags & restorable_flags,
                         original_flags & restorable_flags)
        event_bytes = lambda event: (json.dumps({
            "event": event,
            "ts": "2026-07-03T12:00:00Z",
        }, sort_keys=True) + "\n").encode("utf-8")
        self.assertEqual(
            path.read_bytes(),
            before + event_bytes("a") + event_bytes("c") + event_bytes("b"))
        self.assertEqual(
            [entry["event"] for entry in logs.read_events(self.repo, "0001-x")],
            ["preexisting", "a", "c", "b"])

    def test_lines_have_sorted_keys(self):
        logs.append_event(self.repo, "0001-x", "e", {"b": 1, "a": 2})
        line = (self.repo / ".factory/items/0001-x/log.jsonl").read_text().strip()
        self.assertEqual(line, json.dumps(json.loads(line), sort_keys=True))

    def test_read_missing_returns_empty(self):
        self.assertEqual(logs.read_events(self.repo, "0009-none"), [])

    def test_count_events(self):
        for _ in range(3):
            logs.append_event(self.repo, "0001-x", "review.rejected")
        self.assertEqual(logs.count_events(self.repo, "0001-x", "review.rejected"), 3)
        self.assertEqual(logs.count_events(self.repo, "0001-x", "other"), 0)

    def test_now_stamp_env_override(self):
        self.assertEqual(logs.now_stamp(), "2026-07-03T12:00:00Z")

    def test_empty_data_dict_is_recorded(self):
        entry = logs.append_event(self.repo, "0001-x", "e", {})
        self.assertIn("data", entry)
        self.assertEqual(entry["data"], {})
        line = (self.repo / ".factory/items/0001-x/log.jsonl").read_text().strip()
        self.assertEqual(json.loads(line)["data"], {})

    def test_staging_mutation_and_sync_failure_preserve_foreign_evidence(self):
        item = self.repo / ".factory/items/0001-x"
        foreign = b"foreign staging evidence\n"
        observed = {}

        def mutate_then_fail(_fd):
            staging, = item.glob(".log.jsonl.tmp-*")
            staging.write_bytes(foreign)
            observed["path"] = staging
            observed["identity"] = logs._file_identity(staging.stat())
            raise OSError("injected log staging sync failure")

        with (mock.patch.object(
                logs, "_sync_log_staging", side_effect=mutate_then_fail),
              self.assertRaisesRegex(
                  control.ControlError, "publication failed before install")):
            logs.append_event(self.repo, "0001-x", "item.created")

        staging = observed["path"]
        self.assertTrue(staging.is_file())
        self.assertEqual(staging.read_bytes(), foreign)
        self.assertEqual(
            logs._file_identity(staging.stat()), observed["identity"])
        self.assertFalse((item / "log.jsonl").exists())

    def test_staging_same_byte_mutation_and_callback_failure_preserve_evidence(self):
        item = self.repo / ".factory/items/0001-x"
        observed = {}

        def mutate_then_fail():
            staging, = item.glob(".log.jsonl.tmp-*")
            before = staging.stat()
            data = staging.read_bytes()
            staging.write_bytes(data)
            os.utime(
                staging,
                ns=(before.st_atime_ns, before.st_mtime_ns))
            os.chmod(staging, 0o640)
            observed["path"] = staging
            observed["identity"] = logs._file_identity(staging.stat())
            self.assertEqual(
                observed["identity"][:4], logs._file_identity(before)[:4])
            self.assertNotEqual(
                observed["identity"], logs._file_identity(before))
            raise RuntimeError("injected log staging callback failure")

        with (mock.patch.object(
                logs, "_after_log_staging_write",
                side_effect=mutate_then_fail),
              self.assertRaisesRegex(
                  RuntimeError, "staging callback failure")):
            logs.append_event(self.repo, "0001-x", "item.created")

        staging = observed["path"]
        self.assertTrue(staging.is_file())
        self.assertEqual(
            logs._file_identity(staging.stat()), observed["identity"])
        self.assertFalse((item / "log.jsonl").exists())

    def test_existing_log_final_validation_requires_exact_identity(self):
        item = self.repo / ".factory/items/0001-x"
        log_path = item / "log.jsonl"
        logs.append_event(self.repo, "0001-x", "item.created")
        hostile = {}

        def rewrite_same_bytes():
            before = log_path.stat()
            data = log_path.read_bytes()
            log_path.write_bytes(data)
            os.utime(
                log_path,
                ns=(before.st_atime_ns, before.st_mtime_ns))
            os.chmod(log_path, 0o640)
            hostile["data"] = data
            hostile["identity"] = logs._file_identity(log_path.stat())
            self.assertEqual(
                hostile["identity"][:4], logs._file_identity(before)[:4])
            self.assertNotEqual(
                hostile["identity"], logs._file_identity(before))

        with mock.patch.object(
                logs, "_after_log_directory_sync",
                side_effect=rewrite_same_bytes):
            with self.assertRaisesRegex(
                    control.ControlError, "installed item log image changed"):
                logs.append_event(self.repo, "0001-x", "stage.advance")

        self.assertEqual(log_path.read_bytes(), hostile["data"])
        self.assertEqual(
            logs._file_identity(log_path.stat()), hostile["identity"])

    def test_append_creates_missing_namespace_before_locking(self):
        observed = []
        synced_directories = set()
        real_open_lock = control._open_lock_file
        real_fsync = os.fsync

        def record_fsync(fd):
            details = os.fstat(fd)
            if stat.S_ISDIR(details.st_mode):
                synced_directories.add((details.st_dev, details.st_ino))
            return real_fsync(fd)

        def inspect_namespace(control_fd):
            item = self.repo / ".factory/items/0001-x"
            observed.append(item)
            self.assertTrue(item.is_dir())
            self.assertFalse(item.is_symlink())
            expected = {
                (path.stat().st_dev, path.stat().st_ino)
                for path in (
                    self.repo,
                    self.repo / ".factory",
                    self.repo / ".factory/items",
                    item,
                    item / "control",
                )
            }
            self.assertTrue(expected.issubset(synced_directories))
            return real_open_lock(control_fd)

        with (mock.patch.object(
                control.os, "fsync", side_effect=record_fsync),
              mock.patch.object(
                  control, "_open_lock_file", side_effect=inspect_namespace)):
            logs.append_event(self.repo, "0001-x", "item.created")

        self.assertEqual(observed, [self.repo / ".factory/items/0001-x"])
        self.assertEqual(
            logs.read_events(self.repo, "0001-x")[0]["event"],
            "item.created")

    def test_append_retry_durably_adopts_each_interrupted_namespace_level(self):
        components = (".factory", "items", "0001-x", "control")
        for interrupted_index, interrupted in enumerate(components):
            with self.subTest(interrupted=interrupted), \
                    tempfile.TemporaryDirectory() as raw:
                repo = Path(raw).resolve()
                paths = [repo]
                for component in components:
                    paths.append(paths[-1] / component)

                child_path = paths[interrupted_index + 1]
                parent_path = paths[interrupted_index]
                child_synced = False

                def interrupt_before_parent_sync(fd):
                    nonlocal child_synced
                    details = os.fstat(fd)
                    identity = (details.st_dev, details.st_ino)
                    if not child_path.exists():
                        return real_fsync(fd)
                    child_identity = (
                        child_path.stat().st_dev, child_path.stat().st_ino)
                    parent_identity = (
                        parent_path.stat().st_dev, parent_path.stat().st_ino)
                    if identity == child_identity:
                        child_synced = True
                    elif child_synced and identity == parent_identity:
                        raise OSError(
                            f"interrupted {interrupted} parent fsync")
                    return real_fsync(fd)

                real_fsync = os.fsync
                with (mock.patch.object(
                        control.os, "fsync",
                        side_effect=interrupt_before_parent_sync),
                      self.assertRaisesRegex(
                          control.ControlError, "made durable")):
                    logs.append_event(repo, "0001-x", "item.created")

                self.assertTrue(child_path.is_dir())
                self.assertFalse(
                    (repo / ".factory/items/0001-x/control/lock").exists())
                self.assertFalse(
                    (repo / ".factory/items/0001-x/log.jsonl").exists())

                child_identity = (
                    child_path.stat().st_dev, child_path.stat().st_ino)
                parent_identity = (
                    parent_path.stat().st_dev, parent_path.stat().st_ino)
                retry_syncs = []
                inspected = []
                real_open_lock = control._open_lock_file

                def record_retry_sync(fd):
                    details = os.fstat(fd)
                    if stat.S_ISDIR(details.st_mode):
                        retry_syncs.append((details.st_dev, details.st_ino))
                    return real_fsync(fd)

                def inspect_before_lock(control_fd):
                    inspected.append(True)
                    child_index = retry_syncs.index(child_identity)
                    parent_index = retry_syncs.index(
                        parent_identity, child_index + 1)
                    self.assertLess(child_index, parent_index)
                    self.assertFalse(
                        (repo / ".factory/items/0001-x/log.jsonl").exists())
                    return real_open_lock(control_fd)

                with (mock.patch.object(
                        control.os, "fsync", side_effect=record_retry_sync),
                      mock.patch.object(
                          control, "_open_lock_file",
                          side_effect=inspect_before_lock)):
                    logs.append_event(repo, "0001-x", "item.created")

                self.assertEqual(inspected, [True])
                self.assertEqual(
                    logs.read_events(repo, "0001-x")[0]["event"],
                    "item.created")

    def test_append_refuses_symlink_in_missing_namespace(self):
        outside = self.repo / "outside"
        outside.mkdir()
        (self.repo / ".factory").symlink_to(
            outside, target_is_directory=True)

        with self.assertRaises(control.ControlError):
            logs.append_event(self.repo, "0001-x", "item.created")

        self.assertEqual(list(outside.iterdir()), [])

    def test_append_refuses_created_item_directory_replacement_before_lock(self):
        real_open_directory = control._open_directory
        detached = self.repo / "detached-item"

        def replace_item_after_open(parent_fd, name, *, create=False):
            fd = real_open_directory(parent_fd, name, create=create)
            if name == "0001-x":
                item = self.repo / ".factory/items/0001-x"
                item.rename(detached)
                item.mkdir()
            return fd

        with mock.patch.object(
                control, "_open_directory",
                side_effect=replace_item_after_open):
            with self.assertRaises(control.ControlError):
                logs.append_event(self.repo, "0001-x", "item.created")

        self.assertFalse((detached / "control").exists())
        self.assertFalse(
            (self.repo / ".factory/items/0001-x/control").exists())


class TestTolerantRead(unittest.TestCase):
    """Item spec 0007 §1: corrupt lines are skipped at this one boundary."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def append_raw(self, line):
        path = self.repo / ".factory/items/0001-x/log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def corrupt_fixture(self):
        # 3 valid events interleaved with the 3 corrupt shapes (AC 1):
        # unparseable JSON, a JSON array (non-dict), a dict missing "event".
        logs.append_event(self.repo, "0001-x", "item.created")
        self.append_raw('{"event": "stage.advance", "ts":')
        logs.append_event(self.repo, "0001-x", "review.approved")
        self.append_raw('[1, 2, 3]')
        self.append_raw('{"ts": "2026-07-03T12:00:00Z"}')
        logs.append_event(self.repo, "0001-x", "verify.green")

    def test_read_events_with_stats_skips_and_counts(self):
        self.corrupt_fixture()
        events, skipped = logs.read_events_with_stats(self.repo, "0001-x")
        self.assertEqual([e["event"] for e in events],
                         ["item.created", "review.approved", "verify.green"])
        self.assertEqual(skipped, 3)

    def test_read_events_with_stats_missing_file(self):
        self.assertEqual(
            logs.read_events_with_stats(self.repo, "0009-none"), ([], 0))

    def test_dict_missing_ts_is_corrupt(self):
        self.append_raw('{"event": "review.approved"}')
        events, skipped = logs.read_events_with_stats(self.repo, "0001-x")
        self.assertEqual(events, [])
        self.assertEqual(skipped, 1)

    def test_read_events_tolerant_and_missing_file_empty(self):
        self.corrupt_fixture()
        events = logs.read_events(self.repo, "0001-x")
        self.assertEqual([e["event"] for e in events],
                         ["item.created", "review.approved", "verify.green"])
        self.assertEqual(logs.read_events(self.repo, "0009-none"), [])

    def test_count_events_ignores_corrupt_lines(self):
        logs.append_event(self.repo, "0001-x", "review.rejected")
        logs.append_event(self.repo, "0001-x", "review.rejected")
        self.append_raw('{"event": "review.rejected", "ts": oops')
        self.append_raw('"review.rejected"')
        self.assertEqual(
            logs.count_events(self.repo, "0001-x", "review.rejected"), 2)

    def test_clean_log_reports_zero_skipped(self):
        logs.append_event(self.repo, "0001-x", "item.created")
        events, skipped = logs.read_events_with_stats(self.repo, "0001-x")
        self.assertEqual(len(events), 1)
        self.assertEqual(skipped, 0)

    def test_invalid_utf8_line_counts_as_corrupt(self):
        logs.append_event(self.repo, "0001-x", "item.created")
        path = self.repo / ".factory/items/0001-x/log.jsonl"
        with path.open("ab") as f:
            f.write(b'\xff\xfe{"event"\n')
        events, skipped = logs.read_events_with_stats(self.repo, "0001-x")
        self.assertEqual([e["event"] for e in events], ["item.created"])
        self.assertEqual(skipped, 1)


def valid_wave(**changes):
    data = {
        "wave_id": "wave-001",
        "purpose": "integrated",
        "stage": "verify",
        "command": ["python3", "-m", "unittest"],
        "started_at": "2026-07-03T12:00:00Z",
        "finished_at": "2026-07-03T12:01:00Z",
        "result": "passed",
        "tests": {"passed": 2, "failed": 0, "skipped": 0},
        "tested_sha": "a" * 40,
        "green_sha": "a" * 40,
        "shipping_ref": None,
        "flows": ["J-001:S1"],
        "shipped_flows": [],
        "screenshots": [],
    }
    data.update(changes)
    return data


class StructuredEvidenceValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.name", "Tests"],
            check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.email",
             "tests@example.test"], check=True)
        (self.repo / "README.md").write_text("test\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "README.md"],
                       check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-q", "-m", "base"],
            check=True)
        self.sha = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"], check=True,
            text=True, stdout=subprocess.PIPE).stdout.strip()
        initrepo.init(self.repo)
        items.save_item(self.repo, {
            "id": "0001-x", "title": "X", "stage": "idea",
            "kind": "backend", "created": "2026-07-03T12:00:00Z",
            "updated": "2026-07-03T12:00:00Z",
        }, "")
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        logs.append_event(self.repo, "0001-x", "item.created")

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(self.repo), *args])
        return code, out.getvalue(), err.getvalue()

    def test_shared_validator_accepts_closed_wave_and_span(self):
        self.assertEqual(initrepo.structured_event_errors(
            "test.wave", valid_wave(), "wave"), [])
        self.assertEqual(initrepo.structured_event_errors(
            "activity.span", {
                "span_id": "span-1", "category": "review",
                "started_at": "2026-07-03T12:00:00Z",
                "finished_at": "2026-07-03T12:01:00Z",
                "source": "reviewer-1",
            }, "span"), [])

    def test_shared_validator_enforces_conditionals_and_boundaries(self):
        bad = valid_wave(
            command=[], finished_at="2026-07-03T11:59:00Z",
            green_sha=None, shipping_ref="b" * 40,
            flows=["J-001:S1"], shipped_flows=["J-002:S1"])
        errors = initrepo.structured_event_errors("test.wave", bad, "wave")
        joined = "\n".join(errors)
        self.assertIn("finished_at precedes", joined)
        self.assertIn("command: must not be empty", joined)
        self.assertIn("passed wave must equal", joined)
        self.assertIn("must be a subset", joined)

    def test_invalid_structured_cli_intake_does_not_append(self):
        log_path = self.repo / ".factory/items/0001-x/log.jsonl"
        before = log_path.read_bytes()
        code, _out, err = self.run_cli(
            "log", "0001-x", "test.wave", "--data",
            json.dumps(valid_wave(green_sha=None)))
        self.assertEqual(code, 1)
        self.assertIn("passed wave must equal", err)
        self.assertEqual(log_path.read_bytes(), before)

    def test_valid_structured_cli_intake_and_tree_validation_share_contract(self):
        wave = valid_wave(tested_sha=self.sha, green_sha=self.sha)
        code, _out, err = self.run_cli(
            "log", "0001-x", "test.wave", "--data",
            json.dumps(wave))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_unresolved_wave_sha_is_rejected_without_append(self):
        log_path = self.repo / ".factory/items/0001-x/log.jsonl"
        before = log_path.read_bytes()
        code, _out, err = self.run_cli(
            "log", "0001-x", "test.wave", "--data",
            json.dumps(valid_wave()))
        self.assertEqual(code, 1)
        self.assertIn("commit does not resolve", err)
        self.assertEqual(log_path.read_bytes(), before)

    def test_duplicate_structured_id_is_rejected_without_append(self):
        wave = valid_wave(tested_sha=self.sha, green_sha=self.sha)
        code, _out, _err = self.run_cli(
            "log", "0001-x", "test.wave", "--data", json.dumps(wave))
        self.assertEqual(code, 0)
        log_path = self.repo / ".factory/items/0001-x/log.jsonl"
        before = log_path.read_bytes()
        code, _out, err = self.run_cli(
            "log", "0001-x", "test.wave", "--data", json.dumps(wave))
        self.assertEqual(code, 1)
        self.assertIn("duplicate test.wave id", err)
        self.assertEqual(log_path.read_bytes(), before)

    def test_missing_screenshot_is_rejected_without_append(self):
        wave = valid_wave(
            tested_sha=self.sha, green_sha=self.sha,
            screenshots=[{"path": "evidence/missing.png", "sha256": "0" * 64,
                          "flow": "J-001:S1", "state": "checkout"}])
        log_path = self.repo / ".factory/items/0001-x/log.jsonl"
        before = log_path.read_bytes()
        code, _out, err = self.run_cli(
            "log", "0001-x", "test.wave", "--data", json.dumps(wave))
        self.assertEqual(code, 1)
        self.assertIn("missing, unreadable, or crosses a symlink", err)
        self.assertEqual(log_path.read_bytes(), before)

    def test_nul_and_fifo_screenshot_paths_are_rejected_without_blocking(self):
        fifo = self.repo / "evidence/fifo.png"
        fifo.parent.mkdir()
        os.mkfifo(fifo)
        for screenshot_path in ("nul\x00.png", "evidence/fifo.png"):
            wave = valid_wave(
                wave_id=f"wave-{len(screenshot_path)}",
                tested_sha=self.sha, green_sha=self.sha,
                screenshots=[{"path": screenshot_path, "sha256": "0" * 64,
                              "flow": "J-001:S1", "state": "checkout"}])
            log_path = self.repo / ".factory/items/0001-x/log.jsonl"
            before = log_path.read_bytes()
            code, _out, err = self.run_cli(
                "log", "0001-x", "test.wave", "--data", json.dumps(wave))
            self.assertEqual(code, 1)
            self.assertTrue("contained repository-relative" in err
                            or "not a regular file" in err, err)
            self.assertEqual(log_path.read_bytes(), before)

    def test_invalid_structured_event_on_disk_is_reported_by_validate(self):
        logs.append_event(
            self.repo, "0001-x", "activity.span",
            {"span_id": "bad", "category": "admin",
             "started_at": "2026-07-03T12:02:00Z",
             "finished_at": "2026-07-03T12:01:00Z", "source": "ops"})
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("finished_at precedes" in error for error in errors))

    def test_duplicate_ids_on_disk_are_reported_on_every_occurrence(self):
        wave = valid_wave(tested_sha=self.sha, green_sha=self.sha)
        logs.append_event(self.repo, "0001-x", "test.wave", wave)
        logs.append_event(self.repo, "0001-x", "test.wave", wave)
        errors = initrepo.validate_tree(self.repo)
        self.assertEqual(sum("duplicate test.wave id" in error
                             for error in errors), 2)

    def test_unresolved_sha_on_disk_is_reported(self):
        logs.append_event(self.repo, "0001-x", "test.wave", valid_wave())
        self.assertTrue(any("commit does not resolve" in error
                            for error in initrepo.validate_tree(self.repo)))

    def test_non_string_historical_event_name_is_reported_not_crashed(self):
        log_path = self.repo / ".factory/items/0001-x/log.jsonl"
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": [],
                                     "ts": "2026-07-03T12:00:00Z"}) + "\n")
        self.assertTrue(any("event: must be a string" in error
                            for error in initrepo.validate_tree(self.repo)))

    def test_invalid_utf8_inside_parseable_event_is_reported_by_validate(self):
        log_path = self.repo / ".factory/items/0001-x/log.jsonl"
        with log_path.open("ab") as stream:
            stream.write(
                b'{"data":{"source":"\xff"},"event":"activity.span",'
                b'"ts":"2026-07-03T12:00:00Z"}\n')
        self.assertTrue(any("invalid UTF-8" in error
                            for error in initrepo.validate_tree(self.repo)))

    def test_unrelated_and_spend_intake_behavior_is_unchanged(self):
        for event, data in (("custom.event", {"anything": True}),
                            ("spend", {"stage": "implement", "scope": "leaf",
                                       "provenance": "proxy"})):
            code, _out, _err = self.run_cli(
                "log", "0001-x", event, "--data", json.dumps(data))
            self.assertEqual(code, 0)
        events = logs.read_events(self.repo, "0001-x")
        self.assertEqual([event["event"] for event in events[-2:]],
                         ["custom.event", "spend"])
        self.assertEqual(initrepo.validate_tree(self.repo), [])


if __name__ == "__main__":
    unittest.main()
