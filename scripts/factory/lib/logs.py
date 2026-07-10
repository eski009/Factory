"""Append-only per-item event log: .factory/items/<id>/log.jsonl.

One sorted-keys JSON object per line. Timestamps are UTC and can be
frozen for tests via the FACTORY_NOW environment variable.
"""

import json
import os
from datetime import datetime, timezone

from . import paths


def now_stamp():
    override = os.environ.get("FACTORY_NOW")
    if override:
        return override
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_path(repo, item_id):
    return paths.item_dir(repo, item_id) / "log.jsonl"


def append_event(repo, item_id, event, data=None):
    entry = {"event": event, "ts": now_stamp()}
    if data is not None:
        entry["data"] = data
    path = _log_path(repo, item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


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
