"""Approach-convergence evidence for the plan -> implement boundary.

The planner and fresh reviewers make semantic claims. This module proves only
the closed envelope, exact plan bytes, engine-derived planning round, bounded
citations, independent invocation identities, and coherent disposition.
"""

import fcntl
import hashlib
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from . import initrepo, items, logs, paths
from .validate import validate as validate_schema

SIGNAL_IDS = (
    "natural-language-rule-tail",
    "input-variety-task-growth",
    "unconstrained-output-postprocess",
)
FINAL_VERDICTS = ("not-triggered", "pass", "reject", "uncertain")
DISPOSITIONS = ("advance", "escalate", "approach.rejected")
SPECIAL = frozenset(("blocked", "waiting-human"))
IMMUTABLE_FIELDS = (
    "version", "item", "planning_round", "plan_sha256", "configuration",
    "tier", "planner_invocation", "signals", "escalation_bound",
)


class ConvergenceError(ValueError):
    """A judgement cannot be recorded or cannot authorize advancement."""


def _config(repo):
    try:
        value = json.loads(paths.config_path(repo).read_text(
            encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def enabled(repo):
    value = _config(repo).get("approach_convergence")
    return isinstance(value, dict) and value.get("enabled") is True


def escalation_bound(tier):
    if tier == "bug":
        return 0
    if tier in ("feature", "epic"):
        return 1
    raise ConvergenceError(f"unknown tier for approach convergence: {tier!r}")


def planning_round(repo, item_id):
    count = 0
    for event in logs.read_events(repo, item_id):
        if event.get("event") != "stage.advance":
            continue
        data = event.get("data")
        if (isinstance(data, dict) and data.get("to") == "plan"
                and data.get("from") in ("spec", "design")):
            count += 1
    if count == 0:
        raise ConvergenceError(
            "approach convergence has no non-special engine entry into plan; "
            "re-enter plan through factory advance before recording evidence")
    return f"plan-{count:04d}"


def judgement_path(repo, item_id, round_key, plan_sha256):
    return (paths.item_dir(repo, item_id) / "approach-judgements" /
            f"{round_key}-{plan_sha256}.json")


def _repo_relative(repo, path):
    return Path(path).relative_to(Path(repo)).as_posix()


def current_context(repo, item_id):
    meta, _body = items.load_item(repo, item_id)
    if meta.get("stage") != "plan":
        raise ConvergenceError(
            f"approach convergence requires stage 'plan', got {meta.get('stage')!r}")
    plan = paths.item_dir(repo, item_id) / "plan.md"
    try:
        plan_bytes = plan.read_bytes()
    except OSError as exc:
        raise ConvergenceError("plan.md missing or unreadable") from exc
    if not plan_bytes:
        raise ConvergenceError("plan.md missing or empty")
    round_key = planning_round(repo, item_id)
    digest = hashlib.sha256(plan_bytes).hexdigest()
    tier = items.item_tier(meta)
    record = judgement_path(repo, item_id, round_key, digest)
    return {
        "item": item_id,
        "planning_round": round_key,
        "plan_sha256": digest,
        "tier": tier,
        "escalation_bound": escalation_bound(tier),
        "enabled": enabled(repo),
        "record": _repo_relative(repo, record),
    }


def _schema_errors(record, label="judgement"):
    return validate_schema(
        record, initrepo.load_schema("approach-judgement"), label)


def _citation_error(repo, citation, label, required_path=None):
    rel = citation["path"]
    pure = PurePosixPath(rel)
    if pure.is_absolute() or ".." in pure.parts:
        return f"{label}: citation escapes the repository: {rel}"
    if required_path is not None and rel != required_path:
        return (f"{label}: signal must cite the current plan "
                f"{required_path}, got {rel}")
    path = Path(repo) / rel
    if not path.is_file():
        return f"{label}: citation path missing: {rel}"
    repo_root = Path(repo).resolve()
    target = path.resolve()
    try:
        target.relative_to(repo_root)
    except ValueError:
        return f"{label}: citation escapes the repository: {rel}"
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return f"{label}: citation path unreadable: {rel}"
    start = citation["start_line"]
    end = citation["end_line"]
    if start > end:
        return f"{label}: citation start exceeds end: {rel}:{start}-{end}"
    if end > len(lines):
        return (f"{label}: citation range out of range: "
                f"{rel}:{start}-{end} has {len(lines)} line(s)")
    if not any(line.strip() for line in lines[start - 1:end]):
        return f"{label}: citation range is empty: {rel}:{start}-{end}"
    return None


def _expected_resolution(record):
    signals = record["signals"]
    attempts = record["attempts"]
    bound = record["escalation_bound"]
    if not signals:
        return "not-triggered", "advance"
    last = attempts[-1]
    unresolved = last["verdict"] == "uncertain" or last["evidence_conflict"]
    if unresolved:
        if len(attempts) - 1 < bound:
            return "uncertain", "escalate"
        return "uncertain", "approach.rejected"
    if last["verdict"] == "pass":
        return "pass", "advance"
    return "reject", "approach.rejected"


def validate_current(repo, meta, record):
    errors = _schema_errors(record)
    if errors:
        raise ConvergenceError(
            "approach judgement schema invalid: " + "; ".join(errors))
    context = current_context(repo, meta["id"])
    if record["item"] != meta["id"]:
        raise ConvergenceError(
            f"approach judgement wrong item: expected {meta['id']}, "
            f"got {record['item']}")
    if record["planning_round"] != context["planning_round"]:
        raise ConvergenceError(
            f"approach judgement stale planning round: expected "
            f"{context['planning_round']}, got {record['planning_round']}")
    if record["plan_sha256"] != context["plan_sha256"]:
        raise ConvergenceError(
            f"approach judgement stale plan hash: expected "
            f"{context['plan_sha256']}, got {record['plan_sha256']}")
    if record["tier"] != context["tier"]:
        raise ConvergenceError(
            f"approach judgement tier context stale: expected "
            f"{context['tier']}, got {record['tier']}")
    if record["escalation_bound"] != context["escalation_bound"]:
        raise ConvergenceError(
            f"approach judgement escalation bound stale: expected "
            f"{context['escalation_bound']}, got "
            f"{record['escalation_bound']}")

    ids = [signal["id"] for signal in record["signals"]]
    if len(ids) != len(set(ids)):
        raise ConvergenceError(
            "approach judgement signal ids must be unique")
    plan_rel = f".factory/items/{meta['id']}/plan.md"
    for signal in record["signals"]:
        if not signal["evidence"]:
            raise ConvergenceError(
                f"approach judgement signal {signal['id']} has no plan citations")
        for index, citation in enumerate(signal["evidence"], 1):
            problem = _citation_error(
                repo, citation,
                f"approach judgement signal {signal['id']} citation {index}",
                required_path=plan_rel)
            if problem:
                raise ConvergenceError(problem)

    attempts = record["attempts"]
    if record["signals"] and not attempts:
        raise ConvergenceError(
            "approach judgement incoherent: named signals require a reviewer attempt")
    if not record["signals"] and attempts:
        raise ConvergenceError(
            "approach judgement incoherent: no-signal screen requires zero attempts")
    maximum = 1 + record["escalation_bound"]
    if len(attempts) > maximum:
        raise ConvergenceError(
            f"approach judgement attempt count {len(attempts)} exceeds "
            f"resolved maximum {maximum}")
    numbers = [attempt["attempt"] for attempt in attempts]
    expected_numbers = list(range(1, len(attempts) + 1))
    if numbers != expected_numbers:
        raise ConvergenceError(
            f"approach judgement attempt numbers must be {expected_numbers}, "
            f"got {numbers}")
    reviewers = []
    for attempt in attempts:
        if attempt["invocation"] == record["planner_invocation"]:
            raise ConvergenceError(
                f"approach judgement reviewer attempt {attempt['attempt']} "
                "matches planner invocation")
        if attempt["invocation"] in reviewers:
            raise ConvergenceError(
                f"approach judgement reviewer invocation reused: "
                f"{attempt['invocation']}")
        reviewers.append(attempt["invocation"])
        if not attempt["findings"]:
            raise ConvergenceError(
                f"approach judgement reviewer attempt {attempt['attempt']} "
                "has no cited findings")
        for index, finding in enumerate(attempt["findings"], 1):
            problem = _citation_error(
                repo, finding,
                f"approach judgement reviewer attempt "
                f"{attempt['attempt']} finding {index}")
            if problem:
                raise ConvergenceError(problem)
    if len(attempts) == 2:
        first = attempts[0]
        if first["verdict"] != "uncertain" and not first["evidence_conflict"]:
            raise ConvergenceError(
                "approach judgement first attempt did not authorize escalation")
    actual_count = max(0, len(attempts) - 1)
    if record["escalation_count"] != actual_count:
        raise ConvergenceError(
            f"approach judgement escalation_count "
            f"{record['escalation_count']} does not match {actual_count}")
    expected_verdict, expected_disposition = _expected_resolution(record)
    if (record["final_verdict"], record["disposition"]) != (
            expected_verdict, expected_disposition):
        raise ConvergenceError(
            "approach judgement incoherent: expected "
            f"{expected_verdict} + {expected_disposition}, got "
            f"{record['final_verdict']} + {record['disposition']}")
    return record


def _load_record(path):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConvergenceError(
            f"approach judgement unreadable: {path.name}") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConvergenceError(
            f"approach judgement malformed JSON: {path.name} ({exc})") from exc
    return value


@contextmanager
def _record_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _event_data(repo, path, record):
    return {
        "path": _repo_relative(repo, path),
        "planning_round": record["planning_round"],
        "plan_sha256": record["plan_sha256"],
        "tier": record["tier"],
        "escalation_bound": record["escalation_bound"],
        "signals": [signal["id"] for signal in record["signals"]],
        "attempts": len(record["attempts"]),
        "final_verdict": record["final_verdict"],
        "disposition": record["disposition"],
    }


def _append_recorded_event_if_missing(repo, item_id, data):
    if any(event.get("event") == "approach.judgement.recorded"
           and event.get("data") == data
           for event in logs.read_events(repo, item_id)):
        return
    logs.append_event(repo, item_id, "approach.judgement.recorded", data)


def _write_record(path, record):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            f.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _validate_existing_structure(record):
    errors = _schema_errors(record, "existing approach judgement")
    if errors:
        raise ConvergenceError(
            "existing approach judgement schema invalid: " + "; ".join(errors))


def _is_prior_tier_context(existing, record):
    """True only for a valid old tier at the current round/hash door."""
    same_door = all(existing[key] == record[key]
                    for key in ("item", "planning_round", "plan_sha256"))
    if not same_door or existing["tier"] == record["tier"]:
        return False
    return existing["escalation_bound"] == escalation_bound(existing["tier"])


def record_judgement(repo, item_id, record):
    meta, _body = items.load_item(repo, item_id)
    if not enabled(repo):
        raise ConvergenceError(
            "unsolicited approach judgement: approach_convergence.enabled "
            "is not true")
    context = current_context(repo, item_id)
    path = Path(repo) / context["record"]
    with _record_lock(path):
        attempts = record.get("attempts") if isinstance(record, dict) else None
        if (not path.exists() and isinstance(attempts, list)
                and len(attempts) > 1):
            raise ConvergenceError(
                "approach judgement initial write may contain at most one "
                "reviewer attempt")
        validate_current(repo, meta, record)
        data = _event_data(repo, path, record)
        if path.exists():
            existing = _load_record(path)
            _validate_existing_structure(existing)
            existing_data = _event_data(repo, path, existing)
            if _is_prior_tier_context(existing, record):
                # Tier/bound are mutable context but do not participate in the
                # canonical round/hash path. Reconcile the accepted historical
                # state before replacing it with the freshly validated current
                # tier, so an interruption cannot erase its audit event.
                _append_recorded_event_if_missing(
                    repo, item_id, existing_data)
                if isinstance(attempts, list) and len(attempts) > 1:
                    raise ConvergenceError(
                        "approach judgement fresh tier context initial write "
                        "may contain at most one reviewer attempt")
                _write_record(path, record)
                _append_recorded_event_if_missing(repo, item_id, data)
                return path
            validate_current(repo, meta, existing)
            _append_recorded_event_if_missing(repo, item_id, existing_data)
            if existing == record:
                return path
            changed = [key for key in IMMUTABLE_FIELDS
                       if existing.get(key) != record.get(key)]
            if changed:
                raise ConvergenceError(
                    "approach judgement immutable judgement fields changed: "
                    + ", ".join(changed))
            if existing["disposition"] != "escalate":
                raise ConvergenceError(
                    "approach judgement is final; only an escalate record may "
                    "append a reviewer attempt")
            if (len(record["attempts"]) != len(existing["attempts"]) + 1
                    or record["attempts"][:-1] != existing["attempts"]):
                raise ConvergenceError(
                    "approach judgement update must append exactly one reviewer "
                    "attempt and preserve prior attempts byte-for-byte")
        _write_record(path, record)
        _append_recorded_event_if_missing(repo, item_id, data)
        return path
