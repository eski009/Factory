"""Append-only Escape Register: what a human still found after assurance.
An escape stays open until promoted into a durable check (contract
amendment via judgement, regression test, oracle, review rule, or brain
decision). Journey-assurance spec."""

import json
import re

from . import logs, paths
from .initrepo import load_schema
from .validate import validate

MISS_TYPES = ("missing-journey", "missing-node", "missing-oracle",
              "missing-contract-detail", "review-rule-gap")
PROMOTION_RE = re.compile(
    r"^(jdg-[0-9]{4}|test:.+|contract:.+|oracle:.+|decision:.+)$")
ID_RE = re.compile(r"^esc-([0-9]{4})$")


class EscapeError(ValueError):
    pass


def _ledger_path(repo):
    return paths.ledgers_dir(repo) / "escapes.jsonl"


def read_escapes(repo):
    path = _ledger_path(repo)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def current_escapes(repo):
    """Latest entry per id — a promotion line supersedes its open record."""
    out = {}
    for entry in read_escapes(repo):
        if entry.get("id"):
            out[entry["id"]] = entry
    return out


def open_escapes(repo):
    return sorted((e for e in current_escapes(repo).values()
                   if e.get("status") == "open"), key=lambda e: e["id"])


def _append(repo, entry):
    errors = validate(entry, load_schema("escape"), "escape")
    if errors:
        raise EscapeError("; ".join(errors))
    path = _ledger_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def file_escape(repo, journey, finding, miss_type, item="", node="",
                evidence=None):
    if miss_type not in MISS_TYPES:
        raise EscapeError("miss_type must be one of " + ", ".join(MISS_TYPES))
    nums = [int(m.group(1)) for e in read_escapes(repo)
            if (m := ID_RE.match(e.get("id", "")))]
    entry = {"id": f"esc-{max(nums, default=0) + 1:04d}",
             "ts": logs.now_stamp(), "item": item, "journey": journey,
             "node": node, "finding": finding, "miss_type": miss_type,
             "evidence": list(evidence or []), "status": "open"}
    return _append(repo, entry)


def promote(repo, escape_id, via):
    if not PROMOTION_RE.match(via or ""):
        raise EscapeError(
            "promotion --via must be jdg-NNNN, test:<path>, contract:<path>, "
            "oracle:<ref>, or decision:<ref>")
    current = current_escapes(repo)
    if escape_id not in current:
        raise EscapeError(f"no such escape: {escape_id}")
    if current[escape_id].get("status") == "promoted":
        raise EscapeError(f"{escape_id} is already promoted")
    entry = dict(current[escape_id])
    entry["ts"] = logs.now_stamp()
    entry["status"] = "promoted"
    entry["promotion"] = via
    return _append(repo, entry)
