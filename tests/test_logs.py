import fcntl
import json
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from scripts.factory.lib import logs


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

    def test_shared_supplied_descriptor_preserves_intervening_append(self):
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


if __name__ == "__main__":
    unittest.main()
