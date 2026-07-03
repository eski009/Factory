"""Council memory firewall: bids -> judgements -> derived reputation.

Specialists never mutate canonical memory. They file schema-validated
escalation bids; the orchestrator records exactly one judgement per bid;
only accept/merge authorize a canonical edit naming surface + anchor.
Reputation is derived from judgements (wolf tax), never hand-authored.
Spec §6.
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


def read_ledger(repo, name):
    path = _ledger_path(repo, name)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def append_ledger(repo, name, entry):
    path = _ledger_path(repo, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def next_ledger_id(repo, name, prefix):
    return f"{prefix}-{len(read_ledger(repo, name)) + 1:04d}"


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
