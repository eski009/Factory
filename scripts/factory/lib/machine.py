"""Pipeline state machine. Skills do the thinking; advance() is the
deterministic gatekeeper that refuses transitions whose preconditions
(files and logged evidence events) are unmet. Spec §3.

Evidence events are checked as lifetime counts, not scoped to the
item's latest entry into its current stage, so stale evidence (e.g.
an old review.approved after a later rework) satisfies gates.
EXCEPTION: the ship gate's assurance evidence (assure.passed /
assure.waived / assure.confirmed) is round-scoped — it must postdate
the latest implement.completed, so assurance from before a rework
never satisfies the ship gate. All other events (including
assure.rejected, a lifetime count feeding the capped rework edge,
and the assure entry gate's verify.green) are lifetime counts.
"""

import json
import subprocess
from pathlib import PurePosixPath

from . import items, logs, paths

STAGES = ["idea", "triage", "spec", "design", "plan",
          "implement", "review", "verify", "assure", "ship", "done"]
SPECIAL = ("blocked", "waiting-human")
MAX_REVIEW_REJECTIONS = 2
MAX_ASSURE_REJECTIONS = 2


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
    if meta["stage"] not in seq:
        # A declaration can remove the item's CURRENT stage from its own
        # sequence (journeys set to none while parked at assure): fall back
        # to the unfiltered sequence so the item can still advance out.
        seq = stage_sequence(meta["kind"])
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


def _last_index(events, name):
    idx = -1
    for i, event in enumerate(events):
        if event["event"] == name:
            idx = i
    return idx


def _config_gates(repo):
    try:
        raw = json.loads(paths.config_path(repo).read_text(
            encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    gates = raw.get("gates", []) if isinstance(raw, dict) else []
    if not isinstance(gates, list):
        return []
    return [g for g in gates if isinstance(g, str)]


def _validate_assurance_artifacts(repo, meta):
    from .initrepo import load_schema
    from .validate import validate as validate_schema

    vpath = _artifact(repo, meta, "assurance/verdicts.json")
    text = _read_text_or_empty(vpath)
    if not text.strip():
        raise GateError("assurance/verdicts.json missing or empty "
                        "(assurance evidence required)")
    try:
        verdicts = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GateError(f"assurance/verdicts.json invalid JSON ({exc})")
    errors = validate_schema(verdicts, load_schema("assurance-verdicts"), "verdicts")
    if errors:
        raise GateError("assurance/verdicts.json: " + "; ".join(errors))
    declared = [j for j in (meta.get("journeys") or "").split(",")
                if j and j != "none"]
    covered = {j.get("id"): j for j in verdicts.get("journeys", [])}
    missing = [j for j in declared if j not in covered]
    if missing:
        raise GateError("assurance verdicts missing journeys: " + ", ".join(missing))
    item_dir = paths.item_dir(repo, meta["id"])
    for j in verdicts.get("journeys", []):
        if not j.get("scenarios"):
            raise GateError(
                f"journey {j.get('id')}: verdicts contain no scenarios — "
                "nothing was exercised")
        for s in j.get("scenarios", []):
            if s.get("verdict") != "pass":
                raise GateError(
                    f"journey {j.get('id')} scenario {s.get('id')}: "
                    f"verdict {s.get('verdict')!r} is not pass")
            for ev in s.get("evidence", []):
                rel = ev.get("path", "")
                parts = PurePosixPath(rel).parts
                if PurePosixPath(rel).is_absolute() or ".." in parts:
                    raise GateError(
                        f"journey {j.get('id')} scenario {s.get('id')}: "
                        f"evidence path escapes the item dir: {rel}")
                if not (item_dir / rel).exists():
                    raise GateError(
                        f"journey {j.get('id')} scenario {s.get('id')}: "
                        f"assurance evidence missing on disk: {rel}")
    itext = _read_text_or_empty(_artifact(repo, meta, "assurance/impact.json"))
    if itext.strip():
        try:
            impact = json.loads(itext)
        except json.JSONDecodeError as exc:
            raise GateError(f"assurance/impact.json invalid JSON ({exc})")
        journeys_list = impact.get("journeys") if isinstance(impact, dict) else None
        if not isinstance(journeys_list, list):
            raise GateError("assurance/impact.json: journeys must be a list")
        for j in journeys_list:
            if not isinstance(j, dict):
                raise GateError("assurance/impact.json: journey entries must be objects")
            scenarios = j.get("scenarios", [])
            if not isinstance(scenarios, list):
                raise GateError(
                    f"assurance/impact.json: journey {j.get('id')}: scenarios must be a list")
            have = {s.get("id") for s in covered.get(j.get("id"), {}).get("scenarios", [])}
            want = {s.get("id") for s in scenarios if isinstance(s, dict)}
            unmet = sorted(want - have)
            if unmet:
                raise GateError(
                    f"journey {j.get('id')}: required scenarios without verdicts: "
                    + ", ".join(str(u) for u in unmet))


def _require_journey_impact(repo, meta):
    """Journey-assurance spec: the engine refuses to leave spec until the
    impact is recorded. 'none' is a valid answer; an omitted one is not."""
    path = _artifact(repo, meta, "spec.md")
    if "## Journey impact" not in _read_text_or_empty(path):
        raise GateError("spec.md must contain a '## Journey impact' section")
    if "journeys" not in meta:
        raise GateError(
            "journey impact must be declared: factory journeys <id> <none|J-...>")


def _gate_spec(repo, meta):
    _require_file(repo, meta, "triage.md", "triage record required before spec")
    if "priority" not in meta:
        raise GateError("priority must be set at triage")


def _gate_design(repo, meta):
    _require_file(repo, meta, "spec.md", "spec required before design")
    _require_journey_impact(repo, meta)


def _gate_plan(repo, meta):
    _require_file(repo, meta, "spec.md", "spec required before planning")
    _require_journey_impact(repo, meta)
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


def _gate_assure(repo, meta):
    _require_event(repo, meta, "verify.green",
                   "verification evidence required before assurance")


def _gate_ship(repo, meta):
    if meta.get("journeys") == "none":
        _require_event(repo, meta, "verify.green", "verification evidence required")
        return
    events = logs.read_events(repo, meta["id"])
    impl = _last_index(events, "implement.completed")
    passed = _last_index(events, "assure.passed") > impl
    waived = _last_index(events, "assure.waived") > impl
    if not (passed or waived):
        raise GateError("assure.passed (or a recorded human waiver) after the "
                        "latest implementation round required")
    if "assure" in _config_gates(repo) and not (
            waived or _last_index(events, "assure.confirmed") > impl):
        raise GateError("human confirmation required: factory confirm <id> "
                        "(the assure gate is configured)")
    # a recorded human waiver is authoritative — artifact checks are the machine's, not the human's
    if waived:
        return
    _validate_assurance_artifacts(repo, meta)


def _gate_done(repo, meta):
    _require_event(repo, meta, "ship.merged", "merge must be recorded")


GATES = {
    "spec": _gate_spec, "design": _gate_design, "plan": _gate_plan,
    "implement": _gate_implement, "review": _gate_review,
    "verify": _gate_verify, "assure": _gate_assure, "ship": _gate_ship, "done": _gate_done,
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
    elif frm == "assure" and to == "implement":
        if logs.count_events(repo, item_id, "assure.rejected") > MAX_ASSURE_REJECTIONS:
            raise GateError("assurance rejected too many times; move item to blocked")
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
