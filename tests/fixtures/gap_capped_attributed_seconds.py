#!/usr/bin/env python3
"""Replay frozen gap-capped stage-entry timing evidence for Factory item 0030.

The checked-in fixture is the default input. Live `.factory` state is read only
by the explicit `snapshot` subcommand; no runtime Factory module imports this.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = ROOT / "tests/fixtures/gap-capped-attributed-seconds-a1c04a5.json"
DEFAULT_REPORT = ROOT / "docs/factory/field-reports/2026-09-07-gap-capped-attributed-seconds.md"
SNAPSHOT_SHA = "a1c04a5564124fdd9078c6d051085570a32bbd6e"
SNAPSHOT_LABEL = "a1c04a5"
SNAPSHOT_DATE = "2026-09-07"
PRIMARY_IDS = (
    "0001-focus-group-research-structured-intervie",
    "0002-claude-design-mcp-as-the-single-source-o",
    "0003-interactive-decision-pages-clickable-cho",
    "0004-per-item-cost-meter-measure-and-report-t",
    "0007-tolerant-log-reading-corrupt-log-jsonl-l",
    "0008-design-mirror-refinements-pull-bid-diver",
    "0009-finish-the-never-bricks-promise-crash-pr",
    "0010-factory-bug-command-understand-replicate",
    "0012-adapt-the-design-options-decision-block-",
    "0013-assure-attribution-gate-only-on-regressi",
    "0015-approach-rejected-a-redesign-loop-back-t",
    "0016-cost-circuit-breaker-on-engine-authorita",
    "0025-round-scope-all-rework-gates-implement-c",
)
SECONDARY_IDS = PRIMARY_IDS + (
    "0027-packet-respond-falls-through-to-factory-",
    "0031-the-cost-packet-s-decision-copy-is-churn",
    "0033-bugs-run-less-pipeline-make-stage-member",
)
DISCLOSURE_KEYS = (
    "blank_lines", "corrupt_json_lines", "missing_timestamps",
    "unparseable_timestamps",
)


class EvidenceError(ValueError):
    pass


def parse_timestamp(value):
    if not isinstance(value, str) or not value:
        raise EvidenceError("timestamp must be a non-empty string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"unparseable timestamp: {value!r}") from exc


def stage_entries(records):
    created_indexes = [i for i, row in enumerate(records)
                       if row.get("event") == "item.created"]
    if len(created_indexes) != 1:
        raise EvidenceError("records must contain exactly one item.created")
    created_index = created_indexes[0]
    if created_index != 0:
        raise EvidenceError("item.created must be the first frozen record")
    created = parse_timestamp(records[0].get("ts"))
    current = {"stage": "idea", "timestamps": [created]}
    entries = []
    for row in records[1:]:
        timestamp = parse_timestamp(row.get("ts"))
        current["timestamps"].append(timestamp)
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        if row.get("event") == "stage.advance":
            destination = data.get("to")
            if not isinstance(destination, str) or not destination:
                raise EvidenceError("stage.advance must name data.to")
            entries.append(current)
            current = {"stage": destination, "timestamps": [timestamp]}
    entries.append(current)
    return entries


def entry_gaps(entry):
    timestamps = entry["timestamps"]
    return [(right - left).total_seconds()
            for left, right in zip(timestamps, timestamps[1:])]


def _check_cap(cap):
    if isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0:
        raise ValueError("CAP must be a positive integer")


def entry_score(entry, cap):
    _check_cap(cap)
    return sum(min(max(0, gap), cap) for gap in entry_gaps(entry))


def item_score(entries, cap):
    _check_cap(cap)
    return max((entry_score(entry, cap) for entry in entries), default=0)


def parked_ids(manifest, scores, threshold):
    return [item_id for item_id in manifest if scores[item_id] >= threshold]


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def records_digest(records):
    return hashlib.sha256(canonical_json(records)).hexdigest()


def _validate_required_records(item_id, records):
    created = [row for row in records if row.get("event") == "item.created"]
    if len(created) != 1 or records[0].get("event") != "item.created":
        raise EvidenceError(
            f"{item_id}: records must contain exactly one item.created first")
    done = [row for row in records
            if row.get("event") == "stage.advance"
            and isinstance(row.get("data"), dict)
            and row["data"].get("to") == "done"]
    if not done:
        raise EvidenceError(f"{item_id}: required stage.advance to done missing")


def read_source_item(source_root, item_id):
    path = source_root / item_id / "log.jsonl"
    if not path.is_file():
        raise EvidenceError(f"missing declared log: {item_id}")
    source_bytes = path.read_bytes()
    disclosure = {
        "present": True,
        "parseable_timestamped_records": 0,
        "blank_lines": 0,
        "corrupt_json_lines": 0,
        "missing_timestamps": 0,
        "unparseable_timestamps": 0,
    }
    records = []
    for raw in source_bytes.decode("utf-8").splitlines():
        if not raw.strip():
            disclosure["blank_lines"] += 1
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            disclosure["corrupt_json_lines"] += 1
            continue
        if not isinstance(row, dict) or not isinstance(row.get("ts"), str):
            disclosure["missing_timestamps"] += 1
            continue
        try:
            parse_timestamp(row["ts"])
        except EvidenceError:
            disclosure["unparseable_timestamps"] += 1
            continue
        records.append(row)
        disclosure["parseable_timestamped_records"] += 1
    _validate_required_records(item_id, records)
    return {
        "records": records,
        "record_count": len(records),
        "records_sha256": records_digest(records),
        "source_log_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "disclosure": disclosure,
    }
