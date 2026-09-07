import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from scripts.factory.lib import worker_attempts


class WorkerAttemptsTest(unittest.TestCase):
    ITEM = "0001-thing"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name).resolve()
        self.item_dir = self.repo / ".factory" / "items" / self.ITEM
        self.item_dir.mkdir(parents=True)
        self.plan = self.item_dir / "plan.md"
        self.spec = self.item_dir / "spec.md"
        self.plan.write_bytes(b"- [ ] preserve evidence\n")
        self.spec.write_bytes(b"Evidence is not success.\n")
        self.checkout = self.repo / "checkout"
        self.checkout.mkdir()
        self._attempts = []

    def tearDown(self):
        for attempt in self._attempts:
            attempt.close()
        self.tmp.cleanup()

    def _attempt(self, timeout=2):
        attempt = worker_attempts.create_attempt(
            self.repo, self.ITEM, self.checkout, "a" * 40,
            timeout, "codex", "Do the bounded thing.\n")
        self._attempts.append(attempt)
        return attempt

    def _run_in_thread(self, attempt, script, *args):
        outcome = {}

        def target():
            try:
                outcome["raw"] = worker_attempts.run_process(
                    attempt, [sys.executable, "-c", script, *map(str, args)],
                    cwd=self.checkout, env=dict(os.environ))
            except BaseException as exc:  # make thread failures observable
                outcome["error"] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        return thread, outcome

    def _wait_for_bytes(self, path, expected, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if path.read_bytes() == expected:
                    return
            except FileNotFoundError:
                pass
            threading.Event().wait(0.005)
        self.fail(f"{path} never contained {expected!r}")

    def test_manifest_precedes_launch_and_hashes_inputs(self):
        attempt = self._attempt()
        manifest = json.loads(attempt.manifest_path.read_text())
        self.assertEqual(manifest["attempt_id"], attempt.attempt_id)
        self.assertEqual(manifest["item_id"], self.ITEM)
        self.assertEqual(manifest["checkout"], str(self.checkout.resolve()))
        self.assertEqual(manifest["starting_sha"], "a" * 40)
        self.assertEqual(manifest["timeout_seconds"], 2)
        self.assertIn("deadline", manifest)
        self.assertEqual(manifest["state"], "running")
        self.assertEqual(manifest["transport"], "unterminated")
        self.assertEqual(
            manifest["input_hashes"]["plan.md"],
            hashlib.sha256(self.plan.read_bytes()).hexdigest())
        self.assertEqual(
            manifest["input_hashes"]["spec.md"],
            hashlib.sha256(self.spec.read_bytes()).hexdigest())
        self.assertEqual(attempt.brief_path.read_text(),
                         "Do the bounded thing.\n")
        self.assertEqual(list(attempt.path.glob(".*.tmp-*")), [])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFOs")
    def test_stdout_and_stderr_are_visible_before_exit(self):
        attempt = self._attempt()
        ready = self.repo / "ready.fifo"
        release = self.repo / "release.fifo"
        os.mkfifo(ready)
        os.mkfifo(release)
        script = (
            "import os,sys\n"
            "os.write(1, b'out-before-exit')\n"
            "os.write(2, b'err-before-exit')\n"
            "with open(sys.argv[1], 'wb', buffering=0) as f: f.write(b'1')\n"
            "with open(sys.argv[2], 'rb', buffering=0) as f: f.read(1)\n"
        )
        thread, outcome = self._run_in_thread(
            attempt, script, ready, release)
        with ready.open("rb", buffering=0) as pipe:
            self.assertEqual(pipe.read(1), b"1")
        self._wait_for_bytes(attempt.stdout_path, b"out-before-exit")
        self._wait_for_bytes(attempt.stderr_path, b"err-before-exit")
        self.assertTrue(thread.is_alive())
        with release.open("wb", buffering=0) as pipe:
            pipe.write(b"1")
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertNotIn("error", outcome)
        self.assertEqual(outcome["raw"]["stdout"], "out-before-exit")
        self.assertEqual(outcome["raw"]["stderr"], "err-before-exit")

    def test_timeout_preserves_partial_bytes_and_reaps_child(self):
        attempt = self._attempt(timeout=0.15)
        pid_path = self.repo / "child.pid"
        script = (
            "import os,signal,sys,time\n"
            "open(sys.argv[1], 'w').write(str(os.getpid()))\n"
            "os.write(1, b'partial-out\\xff')\n"
            "os.write(2, b'partial-err')\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "while True: time.sleep(10)\n"
        )
        raw = worker_attempts.run_process(
            attempt, [sys.executable, "-c", script, str(pid_path)],
            cwd=self.checkout, env=dict(os.environ))
        terminal = json.loads(attempt.terminal_path.read_text())
        self.assertTrue(raw["timed_out"])
        self.assertEqual(raw["exit_code"], 124)
        self.assertEqual(terminal["status"], "timed_out")
        self.assertEqual(attempt.stdout_path.read_bytes(), b"partial-out\xff")
        self.assertEqual(attempt.stderr_path.read_bytes(), b"partial-err")
        pid = int(pid_path.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_post_reap_drain_is_bounded_with_writing_descendant(self):
        attempt = self._attempt(timeout=5)
        descendant_pid = self.repo / "descendant.pid"
        descendant_script = (
            "import os,sys\n"
            "os.write(1, b'descendant-started\\n')\n"
            "open(sys.argv[1], 'w').write(str(os.getpid()))\n"
            "payload = b'x' * 65536\n"
            "while True: os.write(1, payload)\n"
        )
        script = (
            "import os,subprocess,sys,time\n"
            "os.write(1, b'direct-child\\n')\n"
            "subprocess.Popen([sys.executable, '-c', sys.argv[1], "
            "sys.argv[2]])\n"
            "while not os.path.exists(sys.argv[2]): time.sleep(0.001)\n"
        )

        started = time.monotonic()
        thread, outcome = self._run_in_thread(
            attempt, script, descendant_script, descendant_pid)
        thread.join(1.5)
        returned_within_bound = not thread.is_alive()
        elapsed = time.monotonic() - started
        try:
            if descendant_pid.exists():
                try:
                    os.kill(int(descendant_pid.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        finally:
            thread.join(2)

        self.assertTrue(returned_within_bound,
                        f"run_process took longer than 1.5s ({elapsed:.3f}s)")
        self.assertNotIn("error", outcome)
        direct_bytes = b"direct-child\n"
        captured = attempt.stdout_path.read_bytes()
        self.assertEqual(captured[:len(direct_bytes)], direct_bytes)
        self.assertTrue(outcome["raw"]["stdout"].startswith(
            direct_bytes.decode("ascii")))

    def test_unterminated_attempt_has_no_terminal_success(self):
        attempt = self._attempt()
        attempt.stdout_path.write_bytes(b"controller vanished")
        rows = worker_attempts.inspect_attempts(self.repo, self.ITEM)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["transport"], "unterminated")
        self.assertIsNone(rows[0]["terminal"])
        self.assertFalse(attempt.terminal_path.exists())

    def test_inspection_rejects_invalid_terminal_records(self):
        attempt = self._attempt()
        valid_manifest = attempt.manifest_path.read_bytes()
        valid = {
            "attempt_id": attempt.attempt_id,
            "exit_code": 0,
            "finished_at": "2026-09-07T12:34:56.123456Z",
            "status": "exited",
        }
        cases = {
            "status only": {"status": "exited"},
            "mismatched attempt": {
                **valid, "attempt_id": "different-attempt"},
            "missing attempt": {
                key: value for key, value in valid.items()
                if key != "attempt_id"},
            "boolean exit": {**valid, "exit_code": False},
            "string exit": {**valid, "exit_code": "0"},
            "missing exit": {
                key: value for key, value in valid.items()
                if key != "exit_code"},
            "empty finished at": {**valid, "finished_at": ""},
            "invalid finished at": {**valid, "finished_at": "not-a-time"},
            "naive finished at": {
                **valid, "finished_at": "2026-09-07T12:34:56"},
            "non-UTC finished at": {
                **valid, "finished_at": "2026-09-07T13:34:56+01:00"},
            "wrong timeout code": {
                **valid, "status": "timed_out", "exit_code": 123},
            "wrong launch failure code": {
                **valid, "status": "launch_failed", "exit_code": 126},
            "unknown status": {**valid, "status": "completed"},
            "non-string status": {**valid, "status": []},
            "invalid terminal UTF-8": b"\xff",
            "invalid manifest UTF-8": None,
        }

        for name, terminal in cases.items():
            with self.subTest(name=name):
                attempt.manifest_path.write_bytes(
                    b"\xff" if terminal is None else valid_manifest)
                if isinstance(terminal, bytes):
                    attempt.terminal_path.write_bytes(terminal)
                else:
                    attempt.terminal_path.write_text(json.dumps(
                        valid if terminal is None else terminal))
                rows = worker_attempts.inspect_attempts(self.repo, self.ITEM)
                if terminal is None:
                    self.assertEqual(rows, [])
                    continue
                row = rows[0]
                self.assertEqual(row["transport"], "unterminated")
                self.assertIsNone(row["terminal"])

    def test_capture_open_failure_closes_first_fd_and_reaps_child(self):
        attempt = self._attempt()
        real_open = os.open
        real_close = os.close
        real_popen = subprocess.Popen
        stdout_fds = []
        children = []

        def open_capture(path, flags, mode=0o777, *, dir_fd=None):
            if path == "stderr.bin" and flags & os.O_APPEND:
                raise OSError("stderr capture open failed")
            fd = real_open(path, flags, mode, dir_fd=dir_fd)
            if path == "stdout.bin" and flags & os.O_APPEND:
                stdout_fds.append(fd)
            return fd

        def popen(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            return child

        with (mock.patch.object(worker_attempts.os, "open",
                                side_effect=open_capture),
              mock.patch.object(worker_attempts.os, "close",
                                wraps=real_close) as close,
              mock.patch.object(worker_attempts.subprocess, "Popen",
                                side_effect=popen)):
            with self.assertRaisesRegex(OSError,
                                        "stderr capture open failed"):
                worker_attempts.run_process(
                    attempt,
                    [sys.executable, "-c", "import time; time.sleep(60)"],
                    cwd=self.checkout, env=dict(os.environ))

        self.assertEqual(len(stdout_fds), 1)
        close.assert_any_call(stdout_fds[0])
        with self.assertRaises(OSError):
            os.fstat(stdout_fds[0])
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)
        with self.assertRaises(ChildProcessError):
            os.waitpid(children[0].pid, os.WNOHANG)

    def test_two_runs_retain_distinct_attempt_directories(self):
        first = self._attempt()
        raw1 = worker_attempts.run_process(
            first, [sys.executable, "-c", "print('first')"],
            cwd=self.checkout, env=dict(os.environ))
        second = self._attempt()
        raw2 = worker_attempts.run_process(
            second, [sys.executable, "-c", "print('second')"],
            cwd=self.checkout, env=dict(os.environ))
        self.assertNotEqual(first.attempt_id, second.attempt_id)
        self.assertEqual(first.stdout_path.read_bytes(), b"first\n")
        self.assertEqual(second.stdout_path.read_bytes(), b"second\n")
        self.assertEqual(raw1["stdout"], "first\n")
        self.assertEqual(raw2["stdout"], "second\n")
        self.assertEqual(len(worker_attempts.inspect_attempts(
            self.repo, self.ITEM)), 2)

    def test_inspection_is_read_only_and_launches_no_process(self):
        attempt = self._attempt()
        before = sorted(p.relative_to(self.repo) for p in self.repo.rglob("*"))
        with mock.patch.object(worker_attempts.subprocess, "Popen") as popen:
            rows = worker_attempts.inspect_attempts(self.repo, self.ITEM)
        after = sorted(p.relative_to(self.repo) for p in self.repo.rglob("*"))
        popen.assert_not_called()
        self.assertEqual(before, after)
        self.assertEqual(rows[0]["attempt_id"], attempt.attempt_id)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFOs")
    def test_split_utf8_is_safe_and_raw_bytes_are_exact(self):
        attempt = self._attempt()
        ready = self.repo / "utf8-ready.fifo"
        release = self.repo / "utf8-release.fifo"
        os.mkfifo(ready)
        os.mkfifo(release)
        script = (
            "import os,sys\n"
            "os.write(1, b'\\xe2')\n"
            "with open(sys.argv[1], 'wb', buffering=0) as f: f.write(b'1')\n"
            "with open(sys.argv[2], 'rb', buffering=0) as f: f.read(1)\n"
            "os.write(1, b'\\x82\\xac')\n"
            "os.write(2, b'bad-utf8-\\xff')\n"
        )
        thread, outcome = self._run_in_thread(
            attempt, script, ready, release)
        with ready.open("rb", buffering=0) as pipe:
            self.assertEqual(pipe.read(1), b"1")
        self._wait_for_bytes(attempt.stdout_path, b"\xe2")
        with release.open("wb", buffering=0) as pipe:
            pipe.write(b"1")
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertNotIn("error", outcome)
        self.assertEqual(attempt.stdout_path.read_bytes(), b"\xe2\x82\xac")
        self.assertEqual(attempt.stderr_path.read_bytes(), b"bad-utf8-\xff")
        self.assertEqual(outcome["raw"]["stdout"], "€")
        self.assertEqual(outcome["raw"]["stderr"], "bad-utf8-�")

    def test_launch_failure_has_terminal_transport_record(self):
        attempt = self._attempt()
        raw = worker_attempts.run_process(
            attempt, [str(self.repo / "definitely-not-an-executable")],
            cwd=self.checkout, env=dict(os.environ))
        terminal = json.loads(attempt.terminal_path.read_text())
        self.assertEqual(terminal["status"], "launch_failed")
        self.assertEqual(raw["exit_code"], 127)
        self.assertFalse(raw["timed_out"])
        self.assertTrue(raw["stderr"])

    def test_attempts_symlink_is_refused(self):
        worker = self.item_dir / "worker"
        worker.mkdir()
        outside = self.repo / "outside"
        outside.mkdir()
        (worker / "attempts").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(worker_attempts.AttemptError):
            self._attempt()
        self.assertEqual(list(outside.iterdir()), [])

    def test_factory_symlink_is_refused_before_artifact_write(self):
        self.item_dir.parents[1].rename(self.repo / "original-factory")
        outside = self.repo / "outside"
        outside.mkdir()
        (self.repo / ".factory").symlink_to(
            outside, target_is_directory=True)

        with self.assertRaises(worker_attempts.AttemptError):
            self._attempt()

        self.assertEqual(list(outside.iterdir()), [])

    def test_items_symlink_is_refused_before_artifact_write(self):
        items = self.item_dir.parent
        items.rename(self.repo / "original-items")
        outside = self.repo / "outside"
        outside.mkdir()
        items.symlink_to(outside, target_is_directory=True)

        with self.assertRaises(worker_attempts.AttemptError):
            self._attempt()

        self.assertEqual(list(outside.iterdir()), [])

    def test_every_chain_entry_replacement_is_rejected_before_launch(self):
        for level in ("repo", "factory", "items", "item", "worker",
                      "attempts", "attempt"):
            with self.subTest(level=level):
                attempt = self._attempt()
                targets = {
                    "repo": self.repo,
                    "factory": self.repo / ".factory",
                    "items": self.item_dir.parent,
                    "item": self.item_dir,
                    "worker": self.item_dir / "worker",
                    "attempts": self.item_dir / "worker" / "attempts",
                    "attempt": attempt.path,
                }
                target = targets[level]
                moved = target.with_name(
                    target.name + "-moved-" + attempt.attempt_id)
                target.rename(moved)
                target.mkdir()
                try:
                    with mock.patch.object(
                            worker_attempts.subprocess, "Popen") as popen:
                        with self.assertRaises(worker_attempts.AttemptError):
                            worker_attempts.run_process(
                                attempt, [sys.executable, "-c", "pass"],
                                cwd=self.checkout, env=dict(os.environ))

                    popen.assert_not_called()
                    self.assertEqual(list(target.rglob("terminal.json")), [])
                    with self.assertRaises(FileNotFoundError):
                        os.stat(
                            "terminal.json",
                            dir_fd=attempt._directory_chain[-1].fd,
                            follow_symlinks=False,
                        )
                finally:
                    target.rmdir()
                    moved.rename(target)

    def test_repository_ancestor_replacement_is_rejected_before_launch(self):
        ancestor = self.repo / "outer" / "ancestor"
        nested_repo = ancestor / "repository"
        nested_item = nested_repo / ".factory" / "items" / self.ITEM
        nested_item.mkdir(parents=True)
        (nested_item / "plan.md").write_text("plan\n")
        (nested_item / "spec.md").write_text("spec\n")
        nested_checkout = nested_repo / "checkout"
        nested_checkout.mkdir()
        attempt = worker_attempts.create_attempt(
            nested_repo, self.ITEM, nested_checkout, "b" * 40,
            2, "codex", "Nested repository attempt.\n")
        self._attempts.append(attempt)

        moved = ancestor.with_name("ancestor-moved")
        ancestor.rename(moved)
        ancestor.mkdir()
        try:
            with mock.patch.object(
                    worker_attempts.subprocess, "Popen") as popen:
                with self.assertRaises(worker_attempts.AttemptError):
                    worker_attempts.run_process(
                        attempt, [sys.executable, "-c", "pass"],
                        cwd=nested_checkout, env=dict(os.environ))

            popen.assert_not_called()
            self.assertEqual(list(ancestor.rglob("terminal.json")), [])
            moved_attempt = (moved / "repository" / ".factory" / "items" /
                             self.ITEM / "worker" / "attempts" /
                             attempt.attempt_id)
            self.assertFalse((moved_attempt / "terminal.json").exists())
            with self.assertRaises(FileNotFoundError):
                os.stat("terminal.json",
                        dir_fd=attempt._directory_chain[-1].fd,
                        follow_symlinks=False)
        finally:
            ancestor.rmdir()
            moved.rename(ancestor)

    def test_retained_chain_descriptors_close_exactly_once(self):
        attempt = self._attempt()
        retained_fds = [handle.fd for handle in attempt._directory_chain]
        real_close = os.close

        with mock.patch.object(worker_attempts.os, "close",
                               wraps=real_close) as close:
            attempt.close()
            attempt.close()

        for fd in retained_fds:
            self.assertEqual(close.call_args_list.count(mock.call(fd)), 1)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFOs")
    def test_relocation_during_run_prevents_terminal_publication(self):
        attempt = self._attempt()
        ready = self.repo / "relocation-ready.fifo"
        release = self.repo / "relocation-release.fifo"
        os.mkfifo(ready)
        os.mkfifo(release)
        script = (
            "import sys\n"
            "with open(sys.argv[1], 'wb', buffering=0) as f: f.write(b'1')\n"
            "with open(sys.argv[2], 'rb', buffering=0) as f: f.read(1)\n"
        )
        thread, outcome = self._run_in_thread(
            attempt, script, ready, release)
        with ready.open("rb", buffering=0) as pipe:
            self.assertEqual(pipe.read(1), b"1")

        moved = attempt.path.with_name(attempt.path.name + "-moved")
        attempt.path.rename(moved)
        attempt.path.mkdir()
        with release.open("wb", buffering=0) as pipe:
            pipe.write(b"1")
        thread.join(2)

        self.assertFalse(thread.is_alive())
        self.assertIsInstance(outcome.get("error"),
                              worker_attempts.AttemptError)
        self.assertNotIn("raw", outcome)
        self.assertFalse((moved / "terminal.json").exists())
        self.assertFalse(attempt.terminal_path.exists())

    def test_created_directory_links_are_fsynced_immediately(self):
        events = []
        real_mkdir = worker_attempts.os.mkdir
        real_fsync = worker_attempts.os.fsync

        def recording_mkdir(name, mode=0o777, *, dir_fd=None):
            result = real_mkdir(name, mode, dir_fd=dir_fd)
            events.append(("mkdir", name, os.fstat(dir_fd).st_ino))
            return result

        def recording_fsync(fd):
            events.append(("fsync", None, os.fstat(fd).st_ino))
            return real_fsync(fd)

        with mock.patch.object(worker_attempts.os, "mkdir",
                               side_effect=recording_mkdir), \
                mock.patch.object(worker_attempts.os, "fsync",
                                  side_effect=recording_fsync):
            attempt = self._attempt()

        created_names = ["worker", "attempts", attempt.attempt_id]
        for name in created_names:
            index = next(i for i, event in enumerate(events)
                         if event[:2] == ("mkdir", name))
            self.assertEqual(events[index + 1][0], "fsync")
            self.assertEqual(events[index + 1][2], events[index][2])


if __name__ == "__main__":
    unittest.main()
