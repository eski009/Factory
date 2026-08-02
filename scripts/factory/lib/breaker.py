"""Cost circuit breaker. Item spec 0016 §5.

The verdict is computed on every advance, gate-independent, from the
backward stage.advance edges machine.advance() appends itself — the one
substrate no skill can forget to log. `fired` additionally requires the
"cost" gate, an implement destination, and no recorded answer covering
the current edge count.

The breaker is advisory: it parks, it never refuses on its own
initiative. The one refusal it owns is the resume precondition, which
exists only so a park with no recorded answer cannot ping-pong forever
(machine.py:274-278 applies no gate to a waiting-human resume).
"""

import re

from . import cost, dispatch, items, logs, paths
from .machine import GateError, _config_gates

REWORK_THRESHOLD = 2
# Aliased, not re-declared: one definition of the substrate, in cost.py.
REWORK_FROM = cost.REWORK_FROM
ANSWERS = ("continue", "narrow", "defer")
PAUSE_PREFIX = "cost breaker:"

_ANSWER_RE = re.compile(r"^-\s*answer:\s*(\S+)\s*$", re.MULTILINE)
_EDGES_RE = re.compile(r"^-\s*rework-edges:\s*(\d+)\s*$", re.MULTILINE)


def answer_path(repo, item_id):
    return paths.item_dir(repo, item_id) / "cost" / "answer.md"


def read_answer(repo, item_id):
    """Parse cost/answer.md. Returns None when it is absent, empty or
    unreadable; otherwise the two recorded fields, each None when the
    line is missing. This function never judges — the precondition
    decides what to refuse, so every refusal message lives in one place."""
    try:
        text = answer_path(repo, item_id).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.strip():
        return None
    answer = _ANSWER_RE.search(text)
    edges = _EDGES_RE.search(text)
    return {"answer": answer.group(1) if answer else None,
            "rework_edges": int(edges.group(1)) if edges else None}


def rework_edges(repo, item_id):
    return cost.summarize(repo, item_id)["rework_edges"]


def backlog_counts(repo, meta):
    """What this item is blocking. Actionable means dispatch's own
    definition (everything except done/blocked/waiting-human); the item
    itself is excluded — it does not block itself. Items with no numeric
    priority count only in actionable_total."""
    metas, _errors = items.list_items_safe(repo)
    actionable = [m for m in metas
                  if m["stage"] not in dispatch.NOT_ACTIONABLE
                  and m["id"] != meta["id"]]
    mine = meta.get("priority")
    at_or_above = 0
    if isinstance(mine, int):
        at_or_above = sum(1 for m in actionable
                          if isinstance(m.get("priority"), int)
                          and m["priority"] <= mine)
    return {"at_or_above": at_or_above, "actionable_total": len(actionable)}


def verdict(repo, item_id, meta, to):
    """A plain dict, always, for every advance. Never raises for a
    missing or malformed answer artifact: the verdict reports, the
    precondition refuses."""
    edges = rework_edges(repo, item_id)
    gates = _config_gates(repo)
    answer = read_answer(repo, item_id)
    answered_at = answer["rework_edges"] if answer else None
    over = edges >= REWORK_THRESHOLD
    covered = isinstance(answered_at, int) and answered_at >= edges
    return {
        "over_threshold": over,
        "fired": bool(over and "cost" in gates and to == "implement"
                      and not covered),
        "reason": "rework-threshold",
        "rework_edges": edges,
        "threshold": REWORK_THRESHOLD,
        "gate": "cost" in gates,
        "answered_at": answered_at,
        "priority": meta.get("priority"),
        "backlog": backlog_counts(repo, meta),
        "stage": to,
    }
