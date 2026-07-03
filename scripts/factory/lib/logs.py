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


def read_events(repo, item_id):
    path = _log_path(repo, item_id)
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def count_events(repo, item_id, event):
    return sum(1 for e in read_events(repo, item_id) if e["event"] == event)
