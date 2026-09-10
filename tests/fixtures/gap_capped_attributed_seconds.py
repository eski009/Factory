#!/usr/bin/env python3
"""Replay frozen gap-capped stage-entry timing evidence for Factory item 0030.

The checked-in fixture is the default input. Live `.factory` state is read only
by the explicit `snapshot` subcommand; no runtime Factory module imports this.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
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


ITEM_0015 = "0015-approach-rejected-a-redesign-loop-back-t"
ITEM_0016 = "0016-cost-circuit-breaker-on-engine-authorita"
CAP_MAX = 43727
REPRESENTATIVE_CAPS = (1, 30, 60, 120, 300, 600, 900, 1800, 3600,
                       5000, 6000, 6204, 6205, 7200)


def build_snapshot(source_root):
    items = {item_id: read_source_item(source_root, item_id)
             for item_id in SECONDARY_IDS}
    document = {
        "provenance": {
            "snapshot_date": SNAPSHOT_DATE,
            "source_revision": SNAPSHOT_SHA,
            "source_label": SNAPSHOT_LABEL,
            "source": "gitignored .factory/items/<declared-id>/log.jsonl",
            "park_snap": "external, absent, and not reconstructed",
        },
        "cohorts": {
            "primary": {
                "machine_label": "primary",
                "human_label": "n=13",
                "ids": list(PRIMARY_IDS),
            },
            "secondary": {
                "machine_label": "secondary",
                "human_label": "n=16@a1c04a5",
                "ids": list(SECONDARY_IDS),
            },
        },
        "items": items,
    }
    validate_fixture(document)
    return document


def validate_fixture(document):
    if not isinstance(document, dict):
        raise EvidenceError("fixture root must be an object")
    provenance = document.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("source_revision") != SNAPSHOT_SHA:
        raise EvidenceError("fixture source revision is not a1c04a5")
    expected_cohorts = {
        "primary": {"machine_label": "primary", "human_label": "n=13",
                    "ids": list(PRIMARY_IDS)},
        "secondary": {"machine_label": "secondary",
                      "human_label": "n=16@a1c04a5",
                      "ids": list(SECONDARY_IDS)},
    }
    if document.get("cohorts") != expected_cohorts:
        raise EvidenceError("frozen cohort manifests or labels do not match")
    items = document.get("items")
    if not isinstance(items, dict) or set(items) != set(SECONDARY_IDS):
        raise EvidenceError("frozen item keys do not match the secondary manifest")
    for item_id, frozen in items.items():
        if not isinstance(frozen, dict):
            raise EvidenceError(f"{item_id}: frozen item must be an object")
        records = frozen.get("records")
        if not isinstance(records, list):
            raise EvidenceError(f"{item_id}: records must be a list")
        if frozen.get("record_count") != len(records):
            raise EvidenceError(f"{item_id}: record_count mismatch")
        if frozen.get("records_sha256") != records_digest(records):
            raise EvidenceError(f"{item_id}: frozen record digest mismatch")
        disclosure = frozen.get("disclosure")
        required = {"present", "parseable_timestamped_records", *DISCLOSURE_KEYS}
        if not isinstance(disclosure, dict) or set(disclosure) != required:
            raise EvidenceError(f"{item_id}: disclosure shape mismatch")
        if disclosure["present"] is not True:
            raise EvidenceError(f"{item_id}: declared source log was unavailable")
        if disclosure["parseable_timestamped_records"] != len(records):
            raise EvidenceError(f"{item_id}: parseable record count mismatch")
        if any(type(disclosure[key]) is not int or disclosure[key] < 0
               for key in ("parseable_timestamped_records", *DISCLOSURE_KEYS)):
            raise EvidenceError(f"{item_id}: disclosure counts must be non-negative integers")
        if not records or any(not isinstance(row, dict) for row in records):
            raise EvidenceError(f"{item_id}: records must be nonempty objects")
        _validate_required_records(item_id, records)
        stage_entries(records)
    return document


def load_fixture(path=DEFAULT_FIXTURE):
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read frozen fixture {path}: {exc}") from exc
    return validate_fixture(document)


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.",
                                              dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def write_snapshot(source_root, output):
    document = build_snapshot(source_root)
    content = json.dumps(document, indent=2, ensure_ascii=True) + "\n"
    atomic_write(output, content)


def build_profiles(document):
    validate_fixture(document)
    return {item_id: [entry_gaps(entry)
                      for entry in stage_entries(frozen["records"])]
            for item_id, frozen in document["items"].items()}


def _profile_score(profile, cap):
    _check_cap(cap)
    return max((sum(min(max(0, gap), cap) for gap in gaps)
                for gaps in profile), default=0)


def _first_implement_gaps(document, item_id):
    entries = stage_entries(document["items"][item_id]["records"])
    for entry in entries:
        if entry["stage"] == "implement":
            return entry_gaps(entry)
    raise EvidenceError(f"{item_id}: first implement entry missing")


def comparison_facts(document):
    facts = {}
    for short, item_id in (("0015", ITEM_0015), ("0016", ITEM_0016)):
        gaps = _first_implement_gaps(document, item_id)
        facts[short] = {
            "adjacent_gaps": len(gaps),
            "positive_gaps": sum(gap > 0 for gap in gaps),
            "uncapped_seconds": sum(max(0, gap) for gap in gaps),
            "cap_1_score": sum(min(max(0, gap), 1) for gap in gaps),
        }
    return facts


def sweep_row(profiles, cap, include_parked=True):
    scores = {item_id: _profile_score(profile, cap)
              for item_id, profile in profiles.items()}
    score_0015 = scores[ITEM_0015]
    score_0016 = scores[ITEM_0016]
    threshold = math.floor(score_0015) + 1 if math.floor(score_0015) + 1 <= score_0016 else None
    return {
        "cap": cap,
        "score_0015": score_0015,
        "score_0016": score_0016,
        "threshold": threshold,
        "primary_parked": (parked_ids(PRIMARY_IDS, scores, threshold)
                           if threshold is not None and include_parked else None),
        "secondary_parked": (parked_ids(SECONDARY_IDS, scores, threshold)
                             if threshold is not None and include_parked else None),
    }


def analyse(document):
    profiles = build_profiles(document)
    facts = comparison_facts(document)
    expected = {
        "0015": {"adjacent_gaps": 11, "positive_gaps": 10,
                 "uncapped_seconds": 10046, "cap_1_score": 10},
        "0016": {"adjacent_gaps": 15, "positive_gaps": 13,
                 "uncapped_seconds": 9499, "cap_1_score": 13},
    }
    if facts != expected:
        raise EvidenceError(f"frozen comparison facts changed: {facts!r}")
    for cap in range(1, CAP_MAX + 1):
        row = sweep_row({key: profiles[key] for key in (ITEM_0015, ITEM_0016)}, cap,
                        include_parked=False)
        should_separate = cap <= 6204
        if (row["threshold"] is not None) != should_separate:
            raise EvidenceError(f"unexpected separator state at CAP={cap}")
        if cap == 6205 and (row["score_0015"], row["score_0016"]) != (9499, 9499):
            raise EvidenceError("CAP=6205 comparison no longer ties at 9,499")
        if cap > 6205 and row["score_0015"] <= row["score_0016"]:
            raise EvidenceError(f"comparison does not reverse at CAP={cap}")
    return {
        "comparison_facts": facts,
        "separating_caps": [1, 6204],
        "tie_cap": 6205,
        "cap_max": CAP_MAX,
        "representative_rows": [sweep_row(profiles, cap)
                                for cap in REPRESENTATIVE_CAPS],
    }


def _number(value):
    return f"{value:,.0f}" if value == int(value) else f"{value:,}"


def _parked(value):
    return ("no separating threshold" if value is None
            else ", ".join(value) if value
            else "none parked")


def _table(rows, parked_key):
    lines = [
        "| CAP | 0015 score | 0016 score | lowest separating T | items parked |",
        "|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        threshold = "none" if row["threshold"] is None else _number(row["threshold"])
        lines.append(
            f'| {_number(row["cap"])} | {_number(row["score_0015"])} | '
            f'{_number(row["score_0016"])} | {threshold} | '
            f'{_parked(row[parked_key])} |')
    return "\n".join(lines)


def _disclosure_table(document):
    lines = [
        "| item | present | parseable records | blank | corrupt JSON | missing timestamp | unparseable timestamp |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item_id in SECONDARY_IDS:
        disclosure = document["items"][item_id]["disclosure"]
        lines.append(
            f'| {item_id} | yes | '
            f'{disclosure["parseable_timestamped_records"]} | '
            f'{disclosure["blank_lines"]} | '
            f'{disclosure["corrupt_json_lines"]} | '
            f'{disclosure["missing_timestamps"]} | '
            f'{disclosure["unparseable_timestamps"]} |')
    return "\n".join(lines)


def render_report(document):
    validate_fixture(document)
    result = analyse(document)
    rows = result["representative_rows"]
    return f"""# Within-corpus separation exists; no runaway threshold is calibrated or recommended

This report is an offline arithmetic replay for Factory item 0030. It is not a
production control and grants no authority to alter item 0018.

## Provenance and populations

- Command: `python3 tests/fixtures/gap_capped_attributed_seconds.py replay --fixture tests/fixtures/gap-capped-attributed-seconds-a1c04a5.json`
- Cohort selection revision: `{SNAPSHOT_SHA}`.
- Primary cohort: n=13, the immutable population filed at 0030 creation.
- Secondary snapshot: n=16@a1c04a5, evaluated separately and never pooled with the primary cohort.
- The motivating external ParkSnap run is absent and not reconstructed.

Neither cohort contains a labelled positive runaway. Item 0016 completed and
shipped. The uncapped first-implement values are 10,046 seconds for healthy
0015 and 9,499 seconds for 0016: the difference is 547 seconds (5.4% of the 0015 duration). At CAP=1 the scores are 10 and 13, so the low-CAP ordering is materially
event-cadence-driven rather than a validated measurement of work.

## Exhaustive boundary

Every integer CAP from 1 through 6,204 admits the lowest separating threshold
`T = score(0015) + 1`. CAP 6,205 ties both scores at 9,499. Every integer CAP
from 6,206 through 43,727 makes 0015 larger. A row without separation carries
no threshold and is never rendered as zero or as an empty parked set.

## Primary representative rows — n=13

{_table(rows, "primary_parked")}

## Secondary representative rows — n=16@a1c04a5

{_table(rows, "secondary_parked")}

## Source-input disclosure

All 16 declared logs are present. Per-item parseable record counts and every
exclusion count remain visible below. Log bytes were recovered from the
2026-09-10 archive; the revision identifies cohort selection, not versioned logs.

{_disclosure_table(document)}

## Finding

The frozen traces contain literal pairwise separators, but those separators do
not calibrate a runaway discriminator: 0016 shipped, the cohorts are unlabelled
for runaway outcomes, the apparent low-CAP advantage is materially
event-cadence-driven, and the external ParkSnap evidence is unavailable.

Conclusion: within-corpus separation exists; no runaway threshold is calibrated or recommended.
"""


def parser():
    command = argparse.ArgumentParser(description=__doc__)
    subcommands = command.add_subparsers(dest="command", required=True)
    snapshot = subcommands.add_parser("snapshot")
    snapshot.add_argument("--source-root", required=True, type=Path)
    snapshot.add_argument("--output", required=True, type=Path)
    replay_command = subcommands.add_parser("replay")
    replay_command.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    replay_command.add_argument("--output", type=Path)
    verify = subcommands.add_parser("verify")
    verify.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    verify.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return command


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            write_snapshot(args.source_root, args.output)
            print(f"wrote {args.output} (primary n=13; secondary n=16@a1c04a5)")
            return 0
        if args.command == "replay":
            rendered = render_report(load_fixture(args.fixture))
            if args.output is None:
                sys.stdout.write(rendered)
            else:
                atomic_write(args.output, rendered)
                print(f"wrote {args.output}")
            return 0
        if args.command == "verify":
            rendered = render_report(load_fixture(args.fixture)).encode("utf-8")
            try:
                accepted = args.report.read_bytes()
            except OSError as exc:
                raise EvidenceError(f"cannot read accepted report {args.report}: {exc}") from exc
            if accepted != rendered:
                raise EvidenceError(f"accepted report differs from replay: {args.report}")
            print("verified frozen replay and accepted report")
            return 0
        raise AssertionError(args.command)
    except (EvidenceError, OSError, ValueError, TypeError) as exc:
        print(f"evidence error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
