"""Deterministic work selection for the dispatcher skill. Spec §4.

Selection is priority+id only; spec §4's "dependencies satisfied" clause
is deferred and not implemented here.
"""

from . import items, machine

NOT_ACTIONABLE = ("done",) + machine.SPECIAL


def _by_priority(metas):
    return sorted(metas, key=lambda m: (m.get("priority", 9999), m["id"]))


def next_items(repo, n):
    """Top-N actionable items by (priority, id). n <= 0 → []. Fewer than n
    are returned when the backlog is smaller. Actionability matches
    next_item: everything except done/blocked/waiting-human. D1 assumes the
    top-N are independent; worktree isolation makes a wrong guess a merge
    conflict at ship, not corruption."""
    if n <= 0:
        return []
    metas, _errors = items.list_items_safe(repo)
    actionable = [m for m in metas if m["stage"] not in NOT_ACTIONABLE]
    return _by_priority(actionable)[:n]


def next_item(repo):
    got = next_items(repo, 1)
    return got[0] if got else None


def pending_human(repo):
    metas, _errors = items.list_items_safe(repo)
    return _by_priority([m for m in metas if m["stage"] == "waiting-human"])
