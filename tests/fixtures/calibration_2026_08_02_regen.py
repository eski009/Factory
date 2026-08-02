#!/usr/bin/env python3
"""Regenerate tests/fixtures/calibration-2026-08-02.json from live state.

This is the exact derivation of the calibration evidence behind
`breaker.REWORK_THRESHOLD = 2` (item 0016, AC16). It reads this repo's
own `.factory/items/*/log.jsonl` — which is gitignored (`.gitignore:6`)
and therefore absent on CI and on a fresh clone — and freezes the
per-item rework-edge counts into a versioned JSON fixture that
`tests/test_breaker.py::CalibrationEvidenceTest` can assert against
anywhere.

Deliberately NOT named `test_*.py`, so `unittest discover -s tests` does
not collect it.

Running this rewrites the frozen snapshot. Do not run it to make a
failing test pass: a live count that has moved past the frozen snapshot
is `LiveDogfoodCalibrationTest`'s business, and the remedy there is
`factory cost-answer`, not a refreshed fixture.

Usage (from the repo root):  python3 tests/fixtures/calibration_2026_08_02_regen.py
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests/fixtures/calibration-2026-08-02.json"
GENERATED = "2026-08-02"

sys.path.insert(0, str(ROOT))

from scripts.factory.lib import cost, items  # noqa: E402


def _branch():
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main():
    metas, errors = items.list_items_safe(ROOT)
    if errors:
        print("unreadable items (omitted):", errors, file=sys.stderr)
    rows = {meta["id"]: cost.summarize(ROOT, meta["id"])["rework_edges"]
            for meta in sorted(metas, key=lambda m: m["id"])}
    doc = {
        "provenance": {
            "generated": GENERATED,
            "repo": "anthony/factory (this repository)",
            "branch": _branch(),
            "method": (
                "Generated on 2026-08-02 by reading this repo's live, "
                "gitignored .factory/items/*/log.jsonl through "
                "scripts.factory.lib.cost.summarize(...)['rework_edges'] "
                "and freezing the result. .factory/ is gitignored "
                "(.gitignore:6), so the live state is unavailable on CI and "
                "on any fresh clone; this file is the versioned, "
                "reproducible record of the evidence that justifies "
                "breaker.REWORK_THRESHOLD = 2 (item 0016, AC16)."),
            "regenerate": (
                "python3 tests/fixtures/calibration_2026_08_02_regen.py"),
            "note": (
                "A snapshot, deliberately frozen. It is NOT expected to "
                "track the live backlog: live drift is the live dogfood "
                "test's job (tests/test_breaker.py::"
                "LiveDogfoodCalibrationTest). Do not refresh this file to "
                "make a test pass."),
        },
        "rework_edges_by_item": rows,
    }
    OUT.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT} ({len(rows)} items)")


if __name__ == "__main__":
    main()
