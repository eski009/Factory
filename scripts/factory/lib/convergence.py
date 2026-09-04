"""Approach-convergence evidence for the plan -> implement boundary.

The planner and fresh reviewers make semantic claims. This module proves only
the closed envelope, exact plan bytes, engine-derived planning round, bounded
citations, independent invocation identities, and coherent disposition.
"""

import hashlib
import json
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
