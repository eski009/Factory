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
