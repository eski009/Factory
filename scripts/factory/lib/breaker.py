"""Cost circuit breaker. Item spec 0016 §5.

The verdict is computed on every advance, gate-independent, from the
backward stage.advance edges machine.advance() appends itself — the one
substrate no skill can forget to log. `fired` additionally requires the
"cost" gate, an implement destination, and no recorded answer covering
the current edge count.

The breaker is advisory: it parks, it never refuses on its own
initiative. The one refusal it owns is the resume precondition, which
exists only so a park with no recorded answer cannot ping-pong forever
(machine.py:287-291 applies no gate to a waiting-human resume).
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
    priority count only in actionable_total.

    `at_or_above` is None — never 0 — when this item carries no numeric
    priority: the comparison is not empty, it is impossible, and
    brain/constraints.md forbids rendering an incomparable population as
    a number. `unreadable` carries list_items_safe's dropped items so no
    caller can present the survivors as an unqualified denominator.
    `unpriced` carries the actionable siblings with no numeric priority,
    for the same reason on the other side of the comparison (F6): they
    fall out of `at_or_above` because they cannot be compared, not
    because they are not waiting, so a caller that reports `at_or_above`
    without them would state an emptiness it has not established."""
    metas, errors = items.list_items_safe(repo)
    actionable = [m for m in metas
                  if m["stage"] not in dispatch.NOT_ACTIONABLE
                  and m["id"] != meta["id"]]
    mine = meta.get("priority")
    at_or_above = None
    if isinstance(mine, int):
        at_or_above = sum(1 for m in actionable
                          if isinstance(m.get("priority"), int)
                          and m["priority"] <= mine)
    return {"at_or_above": at_or_above,
            "actionable_total": len(actionable),
            "unreadable": len(errors),
            "unpriced": sum(1 for m in actionable
                            if not isinstance(m.get("priority"), int))}


def verdict(repo, item_id, meta, to, summary=None):
    """A plain dict, always, for every advance. Never raises for a
    missing or malformed answer artifact: the verdict reports, the
    precondition refuses.

    `summary` lets a caller that has already aggregated the log hand that
    one aggregation in, so every figure it renders comes from a single
    read of the clock (packet.py renders two proxy figures from it)."""
    edges = (summary["rework_edges"] if summary is not None
             else rework_edges(repo, item_id))
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


def record_answer(repo, item_id, answer, notes=None):
    """The single writer of cost/answer.md, modelled on
    design.record_choice. The engine treats all three answers
    identically — any recorded answer satisfies the precondition;
    routing on which one was recorded belongs to factory-dispatch, never
    here (gap G3)."""
    items.load_item(repo, item_id)
    if answer not in ANSWERS:
        raise GateError(
            f"answer must be one of {', '.join(ANSWERS)}, got {answer!r}")
    edges = rework_edges(repo, item_id)
    if edges < REWORK_THRESHOLD:
        raise GateError(f"nothing to answer: {edges} rework edges, "
                        f"threshold {REWORK_THRESHOLD}")
    path = answer_path(repo, item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = notes if notes else "(no notes)"
    path.write_text(
        f"# Cost breaker answer\n\n- answer: {answer}\n"
        f"- rework-edges: {edges}\n- ts: {logs.now_stamp()}\n\n{body}\n",
        encoding="utf-8")
    logs.append_event(repo, item_id, "cost.answered",
                      {"answer": answer, "rework_edges": edges})
    return path


def precondition(repo, item_id, meta, to):
    """One ordered rule, run before the branch dispatch in
    machine.advance(). An implement entry past the threshold requires a
    recorded answer covering the *pre-transition* edge count.

    Consequences, deliberate: the transition that fires the breaker is
    always admitted (its pre-count is below threshold), so the engine
    hands back the stage it was asked for; the next entry into implement
    is refused until answered; and the rule reads only edge counts and
    the artifact, never paused-reason, so a mistyped reason string
    degrades packet copy and never the gate. `meta` is accepted for
    symmetry with verdict() and deliberately unread."""
    if to != "implement" or "cost" not in _config_gates(repo):
        return
    edges = rework_edges(repo, item_id)
    if edges < REWORK_THRESHOLD:
        return
    retry = (f"re-record with factory cost-answer {item_id} "
             "<continue|narrow|defer>")
    answer = read_answer(repo, item_id)
    if answer is None:
        raise GateError(
            f"cost breaker unanswered: {edges} rework edges "
            f"(threshold {REWORK_THRESHOLD}); record an answer with "
            f"factory cost-answer {item_id} <continue|narrow|defer>")
    if answer["answer"] not in ANSWERS:
        raise GateError(
            f"cost breaker answer malformed: recorded option "
            f"{answer['answer']!r} is not one of {', '.join(ANSWERS)}; "
            + retry)
    if not isinstance(answer["rework_edges"], int):
        raise GateError(
            "cost breaker answer malformed: no '- rework-edges: N' line; "
            + retry)
    if answer["rework_edges"] < edges:
        raise GateError(
            f"cost breaker answer stale: recorded at "
            f"{answer['rework_edges']} rework edges, now {edges}; " + retry)
