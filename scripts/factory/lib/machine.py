"""Pipeline state machine. Skills do the thinking; advance() is the
deterministic gatekeeper that refuses transitions whose preconditions
(files and logged evidence events) are unmet. Spec §3.

Rework-gated evidence events are round-scoped (item 0025):
implement.completed, review.approved, verify.green and the ship gate's
assure.passed / assure.waived / assure.confirmed must each postdate
the latest engine-written entry into implement — the last
stage.advance whose data.to == "implement" and whose data.from is not
in SPECIAL — by log-order index over the tolerant-read event list,
never by timestamp. A SPECIAL-from resume returns only to paused-from
and never starts a round; a log with no such marker fails closed.
Non-postdating checks stay lifetime/presence checks: ship.merged,
repro.confirmed, and every file gate; review.rejected and
assure.rejected (the capped rework edges) now count events since the
latest redesign edge (lifetime when none). Item 0015 adds verify->implement
(capped, round-scoped) and the APPROACH_FROM -> spec redesign edge
(lifetime-capped).

advance() returns (meta, verdict): the cost breaker's verdict is computed
on every transition and is advisory — the caller parks, the engine never
does. Item spec 0016 §5.
"""

import json
import re
import subprocess
from pathlib import PurePosixPath

from . import items, logs, paths

STAGES = ["idea", "triage", "spec", "design", "plan",
          "implement", "review", "verify", "assure", "ship", "done"]
SPECIAL = ("blocked", "waiting-human")
MAX_REVIEW_REJECTIONS = 2
MAX_ASSURE_REJECTIONS = 2

# Item 0015: the redesign loop. The firing set is declared ONCE, here;
# cost.py aliases it (the import graph runs cost -> machine, the same
# direction breaker.py aliases cost.REWORK_FROM). An approach.rejected
# edge is identified by SHAPE - an engine-written stage.advance with
# from in APPROACH_FROM and to == APPROACH_TO - never by reason text
# (bid-0086). The cap is LIFETIME-scoped: no transition, resume, or
# redesign resets or re-scopes it.
APPROACH_FROM = frozenset({"review", "verify", "assure"})
APPROACH_TO = "spec"
MAX_APPROACH_REJECTIONS = 1

# Item 0015 SS5: the verify->implement rework cap. Counts engine-
# written verify->implement stage.advance edges POSTDATING the latest
# approach.rejected edge (round-scoped, SS6) - edge substrate, not the
# event substrate the review/assure caps carry (a named live defect
# this cap must not copy, B2).
MAX_VERIFY_REWORKS = 2


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


def _approach_edges(events):
    """(count, last_index) of approach.rejected-shaped edges: engine-
    written stage.advance events with from in APPROACH_FROM and to ==
    APPROACH_TO. Shape only, never reason text (bid-0086). Counts the
    one substrate no skill can forget to log (B2) - skill-logged events
    named 'approach.rejected' are invisible here by design."""
    count, last = 0, -1
    for i, event in enumerate(events):
        if not isinstance(event, dict) or event.get("event") != "stage.advance":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        if data.get("from") in APPROACH_FROM and data.get("to") == APPROACH_TO:
            count += 1
            last = i
    return count, last


def _count_after(events, name, start):
    """Count events named `name` at log positions strictly after
    `start` (item 0015 SS6: rework counts round-scope to the latest
    approach.rejected edge; -1 means the whole log)."""
    return sum(1 for i, e in enumerate(events)
               if i > start and isinstance(e, dict)
               and e.get("event") == name)


def _verify_reworks_after(events, start):
    """Engine-written verify->implement edges after `start` - the
    round-scoped count behind MAX_VERIFY_REWORKS."""
    count = 0
    for i, event in enumerate(events):
        if i <= start or not isinstance(event, dict):
            continue
        if event.get("event") != "stage.advance":
            continue
        data = event.get("data")
        if (isinstance(data, dict) and data.get("from") == "verify"
                and data.get("to") == "implement"):
            count += 1
    return count


def _postdates_latest_implement(events, event):
    """Item 0025 §1 — the one round-scoping predicate (B1/B5): the
    latest occurrence of `event` strictly postdates the latest entry
    into implement, by log-order index over the tolerant-read event
    list. Never timestamps: FACTORY_NOW freezes test clocks and stamps
    are %S-granular, so an entire rework round can share one second.

    The round marker is the engine-written stage.advance appended by
    advance() itself — matched by its data.to/data.from payload, never
    by event name alone (bid-0064). A SPECIAL-from resume returns only
    to paused-from (see advance()), so it never starts a round and is
    excluded via the existing SPECIAL set — item 0015's verify->implement
    edge will count here with no amendment (verify is not SPECIAL).

    Fails closed (B4): no marker raises GateError naming the missing
    entry into implement. Never a -1 sentinel — `index > -1` is true
    for every logged event and would disarm all gates at once on a
    corrupt or hand-edited log."""
    marker = -1
    for i, entry in enumerate(events):
        if entry.get("event") != "stage.advance":
            continue
        data = entry.get("data")
        if not isinstance(data, dict):
            continue
        if data.get("to") == "implement" and data.get("from") not in SPECIAL:
            marker = i
    if marker == -1:
        raise GateError(
            "no entry into implement recorded: the log has no "
            "stage.advance with to 'implement' from a working stage, so "
            "evidence cannot be scoped to an implementation round")
    return _last_index(events, event) > marker


def _stale_evidence_error(event, producer):
    """Item 0025 §3 (B2, bid-0083): the one stale-evidence sentence
    shape, shared by all four rework gates and distinct from
    _require_event's 'not logged' — which would be provably false
    against `factory log` output when the event exists. Names the
    evidence event, the round-resetting entry into implement, and the
    remediation."""
    return GateError(
        f"event {event!r} after the latest implementation round required: "
        f"the logged {event!r} predates the latest entry into implement "
        f"— re-run {producer} to log fresh evidence")


def _require_event_this_round(repo, meta, event, producer, why, events=None):
    """Round-scoped _require_event (item 0025 §2): the event must exist
    AND postdate the latest entry into implement. Three distinct
    refusals: missing round marker (fail closed, first), absent event
    ('not logged'), stale event (the B2 shape)."""
    if events is None:
        events = logs.read_events(repo, meta["id"])
    fresh = _postdates_latest_implement(events, event)
    if _last_index(events, event) == -1:
        raise GateError(f"event {event!r} not logged ({why})")
    if not fresh:
        raise _stale_evidence_error(event, producer)


def _config_dict(repo):
    try:
        raw = json.loads(paths.config_path(repo).read_text(
            encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _config_gates(repo):
    gates = _config_dict(repo).get("gates", [])
    if not isinstance(gates, list):
        return []
    return [g for g in gates if isinstance(g, str)]


def assure_attribution_enabled(repo):
    """Item 0013 §2: the one explicit key that gates the base walk's
    trigger AND the gate's acceptance of attribution fields. An absent
    key, an unreadable or malformed config, or any non-boolean value all
    read as False - the default path is the safe path."""
    assure = _config_dict(repo).get("assure")
    if not isinstance(assure, dict):
        return False
    return assure.get("attribution") is True


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _git(repo, *args):
    """Read-only git call. Returns stripped stdout, or None on a non-zero
    exit, a missing ref, or no git at all. Precedent: _gate_review already
    shells to git via subprocess."""
    try:
        result = subprocess.run(["git", *args], cwd=repo,
                                capture_output=True, text=True)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _default_branch(repo):
    """Resolve the integration branch (item 0013 §4): origin/HEAD with the
    'origin/' prefix stripped, else main, else master, else None. None is a
    blocking condition wherever attribution depends on it."""
    head = _git(repo, "symbolic-ref", "--quiet", "--short",
                "refs/remotes/origin/HEAD")
    if head:
        return head[len("origin/"):] if head.startswith("origin/") else head
    for name in ("main", "master"):
        if _git(repo, "rev-parse", "--verify", "--quiet",
                "refs/heads/" + name) is not None:
            return name
    return None


def _merge_base(repo, branch, item_id):
    """git merge-base <branch> factory/<item_id> -> 40-hex sha, or None on
    any non-zero exit, missing ref, or unparseable output (item 0013 §4)."""
    if not branch:
        return None
    out = _git(repo, "merge-base", branch, f"factory/{item_id}")
    return out if out and _SHA_RE.match(out) else None


# Item 0013 §1/§5: the complete, exhaustive list of what the engine checks
# about an attribution. It never checks the TRUTH of a walk - it reads no
# `expected` or `actual` free-text string anywhere in the ladder below.
ATTRIBUTION_CHECKS = ("shape", "presence", "path-containment", "existence",
                      "non-emptiness", "sha-match", "owner-resolution")

_OWNER_RE = re.compile(r"^[0-9]{4}-[a-z0-9-]+$")


def _path_escape_error(rel):
    """Relative, no '..' - the same containment rule used by
    `_validate_assurance_artifacts`' scenario-evidence loop. Returns a
    message suffix or None."""
    parts = PurePosixPath(rel).parts
    if not rel or PurePosixPath(rel).is_absolute() or ".." in parts:
        return f"evidence path escapes the item dir: {rel}"
    return None


def _attribution_error(repo, meta, item_dir, s, attr_on):
    """The ordered attribution rules of item 0013 §5. Returns a message
    suffix when the scenario BLOCKS the advance to ship, or None when it
    does not block - a pass, or a validated non-blocking pre-existing fail.

    Every inability to classify falls through to a block; there is no path
    from 'unclassifiable' to 'ships', and none to a park."""
    verdict = s.get("verdict")
    attribution = s.get("attribution")
    base = s.get("base")
    tagged = "attribution" in s or "base" in s or "owner" in s

    # 1. attribution recorded on a passing scenario
    if verdict == "pass":
        if tagged:
            return ("attribution recorded on a passing scenario "
                    "(attribution classifies fails only)")
        return None
    # 2. attribution fields present while the config key is off - rejected,
    #    never ignored: a skill cannot emit pre-existing where no base walk
    #    was authorised.
    if not attr_on and tagged:
        return ("unsolicited attribution: `assure.attribution` is not "
                "enabled for this repo (remove the attribution/base fields "
                "or enable the config key)")
    # 3. attribution off: today's refusal, today's wording, byte for byte
    if not attr_on:
        return f"verdict {verdict!r} is not pass"
    # 4. absent attribution is never a pass
    if attribution is None:
        return (f"verdict {verdict!r} is not pass and carries no "
                "attribution (an unclassified fail always blocks)")
    # 5. the one class this item exists to block
    if attribution == "regression":
        return (f"verdict {verdict!r} is attributed 'regression' - a defect "
                "this change caused blocks ship")
    # 6. attribution classifies objective fails only; ambiguity and blocker
    #    keep today's park-or-block semantics untouched
    if verdict != "fail":
        return (f"attribution 'pre-existing' on verdict {verdict!r}: only "
                "an objective 'fail' can be attributed")
    # 7. presence and non-emptiness of base evidence - two distinct
    #    refusals (AC7): absence and emptiness name their own causes
    if not isinstance(base, dict):
        return "pre-existing without base evidence is an ordinary non-pass"
    if not base.get("evidence"):
        return ("pre-existing with an empty base.evidence list: record the "
                "base walk's evidence files under "
                "assurance/base/<merge-base-sha>/ before attributing")
    # 8. sha-match, recomputed here at ship - never trusted from write time
    branch = _default_branch(repo)
    sha = _merge_base(repo, branch, meta["id"])
    recorded = base.get("merge_base")
    if branch is None or sha is None:
        return (f"base evidence is stale: recorded {recorded}, merge base "
                "is now unresolvable (no integration branch, or no merge "
                f"base for factory/{meta['id']})")
    if recorded != sha or base.get("branch") != branch:
        return (f"base evidence is stale: recorded {recorded} on branch "
                f"{base.get('branch')!r}, merge base is now {sha} on branch "
                f"{branch!r}")
    # 9. base evidence is keyed by the sha structurally
    prefix = f"assurance/base/{sha}/"
    for ev in base.get("evidence", []):
        rel = ev.get("path", "")
        escape = _path_escape_error(rel)
        if escape:
            return "base " + escape
        if not rel.startswith(prefix):
            return f"base evidence path is not under {prefix}: {rel}"
        if not (item_dir / rel).exists():
            return f"base evidence missing on disk: {rel}"
    # 10. an unvalidated free-text id is a waiver wearing a filing's clothes
    owner = s.get("owner") or ""
    if not _OWNER_RE.match(owner):
        return ("a pre-existing fail must name an open owning item "
                f"(owner {owner!r} is absent or malformed)")
    try:
        owner_meta, _body = items.load_item(repo, owner)
    except items.ItemError:
        return ("a pre-existing fail must name an open owning item "
                f"(no such item: {owner})")
    if owner_meta.get("stage") == "done":
        return ("a pre-existing fail must name an open owning item "
                f"({owner} is at stage done)")
    # 11. non-blocking: recorded, counted, surfaced - and it ships
    return None


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
    attr_on = assure_attribution_enabled(repo)
    for j in verdicts.get("journeys", []):
        if not j.get("scenarios"):
            raise GateError(
                f"journey {j.get('id')}: verdicts contain no scenarios — "
                "nothing was exercised")
        for s in j.get("scenarios", []):
            problem = _attribution_error(repo, meta, item_dir, s, attr_on)
            if problem:
                raise GateError(
                    f"journey {j.get('id')} scenario {s.get('id')}: {problem}")
            for ev in s.get("evidence", []):
                rel = ev.get("path", "")
                escape = _path_escape_error(rel)
                if escape:
                    raise GateError(
                        f"journey {j.get('id')} scenario {s.get('id')}: "
                        + escape)
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


def _require_fresh_redesign_spec(repo, meta):
    """Round-scoped spec-exit gate (item 0015 SS4, B3). After an
    approach.rejected-shaped edge, any advance out of spec requires
    (a) a non-empty approaches/forbidden.md and (b) a spec.revised
    event at a log position AFTER the latest approach.rejected edge -
    the assure.passed postdating pattern. spec.revised is skill-logged
    (factory-spec, after rewriting spec.md) and used FAIL-CLOSED: a
    forgetful skill blocks the item loudly; the cap/trigger substrate
    stays engine edges only (bid-0064's prohibition binds caps, not
    this freshness token).

    HONEST RESIDUAL (bid-0053/0083): this gate proves freshness and
    existence, not comprehension - a postdated spec that ignores the
    graveyard passes. Nothing engine-side can verify a reading
    happened; factory-spec's required read is skill prose. Items with
    no approach.rejected edge: inert, byte-identical behavior."""
    events = logs.read_events(repo, meta["id"])
    count, last = _approach_edges(events)
    if count == 0:
        return
    problems = []
    path = _artifact(repo, meta, "approaches/forbidden.md")
    if not path.exists() or not _read_text_or_empty(path).strip():
        problems.append("approaches/forbidden.md missing or empty")
    if _last_index(events, "spec.revised") <= last:
        problems.append(
            "no spec.revised event after the latest approach.rejected "
            "edge (factory-spec logs it after rewriting spec.md)")
    if problems:
        raise GateError("redesign spec-exit: " + "; ".join(problems))


def _gate_spec(repo, meta):
    _require_file(repo, meta, "triage.md", "triage record required before spec")
    if "priority" not in meta:
        raise GateError("priority must be set at triage")


def _gate_design(repo, meta):
    _require_file(repo, meta, "spec.md", "spec required before design")
    _require_journey_impact(repo, meta)
    _require_fresh_redesign_spec(repo, meta)


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
    _require_fresh_redesign_spec(repo, meta)


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
    _require_event_this_round(repo, meta, "implement.completed", "implement",
                              "implementation must be finished")


def _gate_verify(repo, meta):
    _require_file(repo, meta, "reviews/synthesis.md", "council review synthesis required")
    _require_event_this_round(repo, meta, "review.approved", "review",
                              "review must be approved with no blocking findings")


def _gate_assure(repo, meta):
    _require_event_this_round(repo, meta, "verify.green", "verify",
                              "verification evidence required before assurance")


def _gate_ship(repo, meta):
    events = logs.read_events(repo, meta["id"])
    if meta.get("journeys") == "none":
        _require_event_this_round(repo, meta, "verify.green", "verify",
                                  "verification evidence required",
                                  events=events)
        return
    passed = _postdates_latest_implement(events, "assure.passed")
    waived = _postdates_latest_implement(events, "assure.waived")
    if not (passed or waived):
        if _last_index(events, "assure.passed") != -1:
            raise _stale_evidence_error("assure.passed", "assure")
        raise GateError("assure.passed (or a recorded human waiver) after the "
                        "latest implementation round required")
    if "assure" in _config_gates(repo) and not (
            waived or _postdates_latest_implement(events, "assure.confirmed")):
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
    # Function-local: breaker imports cost, which imports machine. The
    # precedent is _validate_assurance_artifacts' local imports above.
    from . import breaker
    meta, body = items.load_item(repo, item_id)
    frm = meta["stage"]
    # One ordered rule, before the branch dispatch: the waiting-human
    # resume branch applies no gate of its own (it checks only that the
    # destination equals paused-from), so without this a park with no
    # recorded answer returns the item to the stage that parked it and
    # re-parks immediately.
    breaker.precondition(repo, item_id, meta, to)
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
        # Round-scoped to the latest approach.rejected edge (item 0015
        # SS6): substrate unchanged - skill-logged review.rejected
        # events, the named 0016-L2 defect, deliberately not migrated.
        events = logs.read_events(repo, item_id)
        _n, last = _approach_edges(events)
        if _count_after(events, "review.rejected", last) > MAX_REVIEW_REJECTIONS:
            raise GateError("review rejected too many times; move item to blocked")
    elif frm == "assure" and to == "implement":
        events = logs.read_events(repo, item_id)
        _n, last = _approach_edges(events)
        if _count_after(events, "assure.rejected", last) > MAX_ASSURE_REJECTIONS:
            raise GateError("assurance rejected too many times; move item to blocked")
    elif frm == "verify" and to == "implement":
        # Item 0015 SS5: mirrors review->implement in edge shape, not
        # count substrate (B2). The refusal names the redesign route.
        events = logs.read_events(repo, item_id)
        _n, last = _approach_edges(events)
        if _verify_reworks_after(events, last) >= MAX_VERIFY_REWORKS:
            raise GateError(
                f"verify reworked {MAX_VERIFY_REWORKS} times since the "
                "last redesign; if the design cannot converge, record "
                "approaches/forbidden.md and route factory advance "
                f"{item_id} spec")
    elif frm in APPROACH_FROM and to == APPROACH_TO:
        # Item 0015 SS1/SS2: the redesign edge. The rejecting stage
        # writes the graveyard BEFORE routing, while the evidence is
        # fresh - the edge is refused without it. The cap counts
        # engine-written edges over the item's whole life and is never
        # round-scoped; a recorded answer's watermark admits exactly
        # one more edge (approach.admit_over_cap).
        from . import approach
        _require_file(repo, meta, "approaches/forbidden.md",
                      "the rejecting stage records the forbidden "
                      "approach before requesting a redesign")
        count, _last = _approach_edges(logs.read_events(repo, item_id))
        if count >= MAX_APPROACH_REJECTIONS:
            approach.admit_over_cap(repo, item_id, count)
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
    # Computed after the append so the verdict sees the edge this transition
    # just created. This post-mutation call must remain total: tolerant
    # logs.read_events_with_stats and cost.summarize skip hostile log entries;
    # read_answer catches OSError/UnicodeDecodeError and malformed watermark
    # conversion; _config_gates catches config OSError/JSONDecodeError; and
    # cost.summarize loads the item advance just wrote. Do not add a verdict
    # dependency without preserving that invariant.
    # Backlog is packet-only dead work here. On a cost-gated advance, the two
    # cost.summarize reads are not collapsible: precondition must see the
    # pre-transition edge count and verdict must see the post-append count.
    # Advisory only: the engine never mutates stage on its own initiative.
    verdict = breaker.verdict(repo, item_id, meta, to, backlog=False)
    if verdict["fired"]:
        # Audit trail only — nothing ever counts or gates on this event.
        logs.append_event(repo, item_id, "cost.breaker",
                          {"rework_edges": verdict["rework_edges"],
                           "threshold": verdict["threshold"]})
    return meta, verdict
