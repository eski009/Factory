"""Council memory firewall: bids -> judgements -> derived reputation.

Specialists never mutate canonical memory. They file schema-validated
escalation bids; the orchestrator records exactly one judgement per bid;
only accept/merge authorize a canonical edit naming surface + anchor.
Reputation is derived from judgements (wolf tax), never hand-authored.
Spec §6.

Appends are O_APPEND-safe, but ID generation assumes a single writer per
repo; concurrent sessions should not file bids simultaneously.
"""

import json

from . import logs, paths
from .initrepo import load_schema
from .validate import validate

ROLES = ("product", "ui-taste", "architecture", "engineering-quality",
         "customer", "commercial")
DECISIONS = ("accept", "reject", "defer", "merge", "downgrade")
AUTHORIZING = ("accept", "merge")
DECISION_DELTAS = {"accept": 0.05, "merge": 0.05, "defer": 0.0,
                   "downgrade": -0.05, "reject": -0.10}


class CouncilError(Exception):
    """Business-rule refusal: the ledger stays untouched."""


def _ledger_path(repo, name):
    return paths.ledgers_dir(repo) / f"{name}.jsonl"


def read_ledger_with_stats(repo, name):
    """Tolerant read: returns (entries, skipped); a line is corrupt when
    it fails json.loads or parses to a non-dict. Corrupt lines are never
    repaired or removed here — factory validate flags them for the
    human. Item spec 0007 §4."""
    path = _ledger_path(repo, name)
    if not path.exists():
        return [], 0
    entries = []
    skipped = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if not isinstance(entry, dict):
            skipped += 1
            continue
        entries.append(entry)
    return entries, skipped


def read_ledger(repo, name):
    return read_ledger_with_stats(repo, name)[0]


def append_ledger(repo, name, entry):
    path = _ledger_path(repo, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def next_ledger_id(repo, name, prefix):
    entries, skipped = read_ledger_with_stats(repo, name)
    nums = []
    for entry in entries:
        entry_id = entry.get("id")
        if not entry_id:
            continue
        suffix = entry_id.rsplit("-", 1)[-1]
        if suffix.isdigit():
            nums.append(int(suffix))
    # Corruption-safe floor (item spec 0007 §4): append_ledger writes
    # exactly one line per issued sequential id, so the raw non-blank
    # line count (parsed + skipped) bounds the highest id ever issued.
    # A corrupt line must never cause its id to be reissued.
    floor = len(entries) + skipped
    return f"{prefix}-{max(max(nums, default=0), floor) + 1:04d}"


def _check(entry, schema_name, label):
    errors = validate(entry, load_schema(schema_name), label)
    if errors:
        raise CouncilError("; ".join(errors))


def file_bid(repo, agent, topic, claim, evidence, surface, severity, item=""):
    if not evidence:
        raise CouncilError("bid requires at least one evidence entry")
    bid = {
        "id": next_ledger_id(repo, "bids", "bid"),
        "ts": logs.now_stamp(),
        "agent": agent, "topic": topic, "item": item, "claim": claim,
        "evidence": list(evidence), "surface": surface, "severity": severity,
    }
    _check(bid, "escalation-bid", "bid")
    append_ledger(repo, "bids", bid)
    return bid


def _find_bid(repo, bid_id):
    for bid in read_ledger(repo, "bids"):
        if bid["id"] == bid_id:
            return bid
    raise CouncilError(f"no such bid: {bid_id}")


def _judgement_for(repo, bid_id):
    for jdg in read_ledger(repo, "judgements"):
        if jdg["bid"] == bid_id:
            return jdg
    return None


def record_judgement(repo, bid_id, decision, reason, surface=None, anchor=None):
    bid = _find_bid(repo, bid_id)
    if decision not in DECISIONS:
        raise CouncilError(f"unknown decision {decision!r}; one of {DECISIONS}")
    if _judgement_for(repo, bid_id) is not None:
        raise CouncilError(f"{bid_id} already judged; judgements are final")
    if decision in AUTHORIZING and not (surface and anchor):
        raise CouncilError(f"{decision} requires --surface and --anchor naming the edit")
    jdg = {
        "id": next_ledger_id(repo, "judgements", "jdg"),
        "ts": logs.now_stamp(),
        "bid": bid_id, "decision": decision, "reason": reason,
    }
    if surface:
        jdg["surface"] = surface
    if anchor:
        jdg["anchor"] = anchor
    _check(jdg, "orchestrator-judgement", "judgement")
    rep = {
        "ts": logs.now_stamp(),
        "agent": bid["agent"], "topic": bid["topic"],
        "delta": DECISION_DELTAS[decision], "judgement": jdg["id"],
    }
    _check(rep, "reputation-event", "reputation")
    append_ledger(repo, "judgements", jdg)
    append_ledger(repo, "reputation", rep)
    return jdg, rep


def reputation_table(repo):
    table = {}
    for event in read_ledger(repo, "reputation"):
        key = f"{event['agent']}/{event['topic']}"
        table[key] = round(table.get(key, 0.0) + event["delta"], 2)
    return table


def is_change_authorized(repo, bid_id, surface):
    jdg = _judgement_for(repo, bid_id)
    return bool(jdg and jdg["decision"] in AUTHORIZING
                and jdg.get("surface") == surface)
