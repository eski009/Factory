"""Append-only per-item event log: .factory/items/<id>/log.jsonl.

One sorted-keys JSON object per line. Timestamps are UTC and can be
frozen for tests via the FACTORY_NOW environment variable.
"""

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

from . import paths


def now_stamp():
    override = os.environ.get("FACTORY_NOW")
    if override:
        return override
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_path(repo, item_id):
    return paths.item_dir(repo, item_id) / "log.jsonl"


@contextmanager
def append_lock(file_fd):
    """Serialize public appends and rollback on the actual log inode."""
    fcntl.flock(file_fd, fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(file_fd, fcntl.LOCK_UN)


def _write_all(file_fd, payload):
    while payload:
        written = os.write(file_fd, payload)
        if written == 0:
            raise OSError("audit log write made no progress")
        payload = payload[written:]


def append_event(repo, item_id, event, data=None, *, file_fd=None,
                 append_span=None):
    entry = {"event": event, "ts": now_stamp()}
    if data is not None:
        entry["data"] = data
    payload = (json.dumps(entry, sort_keys=True) + "\n").encode("utf-8")
    owned_fd = file_fd is None
    if owned_fd:
        path = _log_path(repo, item_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
    flags = None
    try:
        # Append independently of the caller's current descriptor offset.
        flags = fcntl.fcntl(file_fd, fcntl.F_GETFL)
        if not flags & os.O_APPEND:
            fcntl.fcntl(file_fd, fcntl.F_SETFL, flags | os.O_APPEND)
        with append_lock(file_fd):
            start = os.fstat(file_fd).st_size
            try:
                _write_all(file_fd, payload)
            finally:
                # Capture partial writes too, before another public writer can
                # append. The caller may later remove only this byte interval.
                if append_span is not None:
                    append_span[:] = [start, os.fstat(file_fd).st_size]
    finally:
        if owned_fd:
            os.close(file_fd)
        elif flags is not None and not flags & os.O_APPEND:
            # The caller may subsequently use this descriptor for recovery.
            fcntl.fcntl(file_fd, fcntl.F_SETFL, flags)
    return entry


def rollback_append(file_fd, span):
    """Remove one append through a pinned O_APPEND descriptor, retaining suffix.

    Cooperating writers hold the same inode lock. No pathname is reopened.
    This is in-process recovery, not crash-atomic log compaction.
    """
    with append_lock(file_fd):
        start, end = span
        chunks = []
        offset = end
        while chunk := os.pread(file_fd, 65536, offset):
            chunks.append(chunk)
            offset += len(chunk)
        os.ftruncate(file_fd, start)
        for chunk in chunks:
            _write_all(file_fd, chunk)
        os.fsync(file_fd)


def read_events_with_stats(repo, item_id):
    """Tolerant read: returns (events, skipped) where events is the list
    of well-formed events and skipped counts non-blank corrupt lines. A
    line is corrupt when it fails json.loads, parses to a non-dict, or is
    a dict missing the "event" or "ts" key (append_event writes both
    unconditionally). Corrupt lines are never repaired or removed here —
    factory validate flags them for the human. Item spec 0007 §1."""
    path = _log_path(repo, item_id)
    if not path.exists():
        return [], 0
    events = []
    skipped = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if not isinstance(event, dict) or "event" not in event or "ts" not in event:
            skipped += 1
            continue
        events.append(event)
    return events, skipped


def read_events(repo, item_id):
    return read_events_with_stats(repo, item_id)[0]


def count_events(repo, item_id, event):
    return sum(1 for e in read_events(repo, item_id) if e["event"] == event)
