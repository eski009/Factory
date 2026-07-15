"""Pipeline state machine. Skills do the thinking; advance() is the
deterministic gatekeeper that refuses transitions whose preconditions
(files and logged evidence events) are unmet. Spec §3.

Evidence events are checked as lifetime counts, not scoped to the
item's latest entry into its current stage, so stale evidence (e.g.
an old review.approved after a later rework) satisfies gates.
Round-scoped evidence is deliberately deferred to Phase 2, which owns
the review-loop semantics.
"""

import subprocess

from . import items, logs, paths

STAGES = ["idea", "triage", "spec", "design", "plan",
          "implement", "review", "verify", "assure", "ship", "done"]
SPECIAL = ("blocked", "waiting-human")
MAX_REVIEW_REJECTIONS = 2


class GateError(Exception):
    """Transition refused: illegal move or precondition unmet."""


def stage_sequence(kind, journeys=None):
    seq = list(STAGES)
    if kind == "backend":
        seq = [s for s in seq if s != "design"]
    if journeys == "none":
        seq = [s for s in seq if s != "assure"]
    return seq


def next_stage(meta):
    seq = stage_sequence(meta["kind"], meta.get("journeys"))
    try:
        idx = seq.index(meta["stage"])
    except ValueError:
        raise GateError(f"unknown stage {meta['stage']!r} for kind {meta['kind']!r}")
    return seq[idx + 1] if idx + 1 < len(seq) else None


def _artifact(repo, meta, rel):
    return paths.item_dir(repo, meta["id"]) / rel


def _read_text_or_empty(path):
    """Undecodable or unreadable evidence reads as empty, so gates treat
    byte-corrupt files exactly like missing ones and fail closed.
    Item spec 0009 §1."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def _require_file(repo, meta, rel, why):
    path = _artifact(repo, meta, rel)
    if not path.exists() or not _read_text_or_empty(path).strip():
        raise GateError(f"{rel} missing or empty ({why})")


def _require_event(repo, meta, event, why):
    if logs.count_events(repo, meta["id"], event) == 0:
        raise GateError(f"event {event!r} not logged ({why})")


def _gate_spec(repo, meta):
    _require_file(repo, meta, "triage.md", "triage record required before spec")
    if "priority" not in meta:
        raise GateError("priority must be set at triage")


def _gate_design(repo, meta):
    _require_file(repo, meta, "spec.md", "spec required before design")


def _gate_plan(repo, meta):
    _require_file(repo, meta, "spec.md", "spec required before planning")
    if meta["kind"] in ("ui", "mixed"):
        _require_file(repo, meta, "design/choice.md", "recorded design choice required")
    if meta.get("bug"):
        _require_file(repo, meta, "repro.md",
                      "confirmed repro required before planning a bug fix")
        _require_event(repo, meta, "repro.confirmed",
                       "replication must be confirmed before planning a bug fix")


def _gate_implement(repo, meta):
    path = _artifact(repo, meta, "plan.md")
    if not path.exists() or "- [ ]" not in _read_text_or_empty(path):
        raise GateError("plan.md with at least one '- [ ]' task required")


def _gate_review(repo, meta):
    branch = f"factory/{meta['id']}"
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "refs/heads/" + branch],
        cwd=repo, capture_output=True,
    )
    if result.returncode != 0:
        raise GateError(f"implementation branch {branch} required")
    _require_event(repo, meta, "implement.completed", "implementation must be finished")


def _gate_verify(repo, meta):
    _require_file(repo, meta, "reviews/synthesis.md", "council review synthesis required")
    _require_event(repo, meta, "review.approved",
                   "review must be approved with no blocking findings")


def _gate_ship(repo, meta):
    _require_event(repo, meta, "verify.green", "verification evidence required")


def _gate_done(repo, meta):
    _require_event(repo, meta, "ship.merged", "merge must be recorded")


GATES = {
    "spec": _gate_spec, "design": _gate_design, "plan": _gate_plan,
    "implement": _gate_implement, "review": _gate_review,
    "verify": _gate_verify, "ship": _gate_ship, "done": _gate_done,
}


def advance(repo, item_id, to, reason=None):
    meta, body = items.load_item(repo, item_id)
    frm = meta["stage"]
    if to in SPECIAL:
        if frm in SPECIAL:
            raise GateError(f"cannot move {frm} -> {to}")
        if frm == "done":
            raise GateError("done items cannot be paused")
        meta["paused-from"] = frm
        meta["paused-reason"] = reason or ""
    elif frm in SPECIAL:
        if to != meta.get("paused-from"):
            raise GateError(f"{frm} item may only resume to {meta.get('paused-from')!r}")
        meta.pop("paused-from", None)
        meta.pop("paused-reason", None)
    elif frm == "review" and to == "implement":
        if logs.count_events(repo, item_id, "review.rejected") > MAX_REVIEW_REJECTIONS:
            raise GateError("review rejected too many times; move item to blocked")
    else:
        expected = next_stage(meta)
        if to != expected:
            raise GateError(f"illegal transition {frm} -> {to} (next is {expected!r})")
        GATES.get(to, lambda *_: None)(repo, meta)
    meta["stage"] = to
    meta["updated"] = logs.now_stamp()
    items.save_item(repo, meta, body)
    event_data = {"from": frm, "to": to}
    if reason:
        event_data["reason"] = reason
    logs.append_event(repo, item_id, "stage.advance", event_data)
    return meta
