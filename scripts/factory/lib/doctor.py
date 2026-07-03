"""Deterministic readout of a repo's factory integration state. Spec §8.

Reports REPO-side configuration only (design tokens, linked DesignSync
project, schedule, gates, item counts) — never model tool availability,
which the engine cannot observe. A readout, never a gate.
"""

import json

from . import dispatch, initrepo, items, paths

REPORT_KEYS = ("tree_valid", "design_system_present", "designsync_project",
               "schedule_configured", "merge_policy", "gates",
               "open_items", "pending_human")
_PLACEHOLDER = "_Not yet written."


def _config(repo):
    path = paths.config_path(repo)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def report(repo):
    config = _config(repo)
    ds_path = paths.docs_root(repo) / "brain" / "design-system.md"
    ds_present = ds_path.exists() and _PLACEHOLDER not in ds_path.read_text(encoding="utf-8")
    metas, _errors = items.list_items_safe(repo)
    return {
        "tree_valid": initrepo.validate_tree(repo) == [],
        "design_system_present": ds_present,
        "designsync_project": config.get("designsync_project"),
        "schedule_configured": bool(config.get("autopilot", {}).get("schedule")),
        "merge_policy": config.get("merge", "auto"),
        "gates": config.get("gates", []),
        "open_items": sum(1 for m in metas if m["stage"] not in ("done", "blocked")),
        "pending_human": len(dispatch.pending_human(repo)),
    }


def render(report_dict):
    return "\n".join(f"{key}: {report_dict[key]}" for key in REPORT_KEYS)
