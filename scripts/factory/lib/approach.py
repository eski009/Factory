"""Redesign-loop pause contract. Item spec 0015 SS2/SS7.

The approach cap (machine.MAX_APPROACH_REJECTIONS) counts engine-written
approach.rejected-shaped edges - stage.advance with from in APPROACH_FROM
and to == "spec" - over the item's whole life, lifetime-scoped, never
reset. This module owns the artifact side of cap exhaustion on the 0016
breaker precedent: the answer verb's single writer, the artifact reader,
and the admission check the engine calls on an over-cap request. The
engine treats all three answers identically - routing on WHICH answer
was recorded belongs to factory-dispatch, never here (the 0016 G3 seam).
"""

import re

from . import items, logs, paths
from .machine import GateError, MAX_APPROACH_REJECTIONS, _approach_edges

ANSWERS = ("continue", "narrow", "defer")
PAUSE_PREFIX = "approach cap:"

_ANSWER_RE = re.compile(r"^-\s*answer:\s*(\S+)\s*$", re.MULTILINE)
_REDESIGNS_RE = re.compile(r"^-\s*redesigns:\s*(\d+)\s*$", re.MULTILINE)


def forbidden_path(repo, item_id):
    return paths.item_dir(repo, item_id) / "approaches" / "forbidden.md"


def answer_path(repo, item_id):
    return paths.item_dir(repo, item_id) / "approaches" / "answer.md"


def read_answer(repo, item_id):
    """Parse approaches/answer.md. None when absent, empty or
    unreadable; otherwise the two recorded fields, each None when its
    line is missing. This function never judges - admit_over_cap
    decides what to refuse, so every refusal message lives in one
    place (the breaker.read_answer pattern)."""
    try:
        text = answer_path(repo, item_id).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.strip():
        return None
    answer = _ANSWER_RE.search(text)
    redesigns = _REDESIGNS_RE.search(text)
    return {"answer": answer.group(1) if answer else None,
            "redesigns": int(redesigns.group(1)) if redesigns else None}


def approach_edges(repo, item_id):
    """Engine-counted approach.rejected edges, by shape."""
    return _approach_edges(logs.read_events(repo, item_id))[0]


def admit_over_cap(repo, item_id, edges):
    """The SS2 cap check, called by machine.advance on a firing-set ->
    spec request at or past the cap. Raises GateError unless a recorded
    answer's watermark covers the current edge count; after the
    admitted edge the count exceeds the watermark, so the next request
    is refused again - monotone, exactly the breaker's model (gap G6).
    Distinct refusals for absent, out-of-enum, missing watermark, and
    stale watermark (item 0015 AC18)."""
    retry = (f"re-record with factory approach-answer {item_id} "
             "<continue|narrow|defer>")
    answer = read_answer(repo, item_id)
    if answer is None:
        raise GateError(
            f"approach cap: {edges} redesign(s) used "
            f"(cap {MAX_APPROACH_REJECTIONS}); record an answer with "
            f"factory approach-answer {item_id} <continue|narrow|defer>")
    if answer["answer"] is None:
        # A missing field is named like its sibling watermark line, not
        # by interpolating the parsed value - an absent '- answer:' line
        # otherwise leaks a Python None repr to the operator (assure
        # round 1, J-003/S6 arm A). Distinct from the out-of-enum arm
        # below, which still names what was actually recorded.
        #
        # The metavar is the house `<option>` (bid-0127), not a second
        # copy of the enum `retry` already spells out ~20 chars later.
        # It is not the bare `- answer:` either: a literal paste of that
        # fails the value regex and re-fires this same arm with a
        # byte-identical message, an unbreaking loop - `<option>` reads
        # as a placeholder and moves the operator to a distinct arm.
        raise GateError(
            "approach answer malformed: no '- answer: <option>' line; "
            + retry)
    if answer["answer"] not in ANSWERS:
        raise GateError(
            f"approach answer malformed: recorded option "
            f"{answer['answer']!r} is not one of {', '.join(ANSWERS)}; "
            + retry)
    if not isinstance(answer["redesigns"], int):
        raise GateError(
            "approach answer malformed: no '- redesigns: N' line; " + retry)
    if answer["redesigns"] < edges:
        raise GateError(
            f"approach answer stale: recorded at {answer['redesigns']} "
            f"redesign(s), now {edges}; " + retry)


def record_answer(repo, item_id, answer, notes=None):
    """The single writer of approaches/answer.md (B5 part 2), modelled
    on breaker.record_answer. The watermark `- redesigns: N` is the
    engine-counted edge count at answer time - monotone: after the
    admitted edge the count exceeds it, so the next request is refused
    again.

    bid-0078: `narrow` and `defer` deliberately leave the item parked,
    so this function deletes the item's packet at answer-record time -
    never keyed on "no longer waiting-human"."""
    items.load_item(repo, item_id)
    if answer not in ANSWERS:
        raise GateError(
            f"answer must be one of {', '.join(ANSWERS)}, got {answer!r}")
    edges = approach_edges(repo, item_id)
    if edges < MAX_APPROACH_REJECTIONS:
        raise GateError(
            f"nothing to answer: {edges} redesign(s), cap "
            f"{MAX_APPROACH_REJECTIONS}")
    path = answer_path(repo, item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = notes if notes else "(no notes)"
    path.write_text(
        f"# Approach cap answer\n\n- answer: {answer}\n"
        f"- redesigns: {edges}\n- ts: {logs.now_stamp()}\n\n{body}\n",
        encoding="utf-8")
    logs.append_event(repo, item_id, "approach.answered",
                      {"answer": answer, "redesigns": edges})
    if answer in ("narrow", "defer"):
        from . import packet
        packet.delete_packets(repo, item_id)
    return path
