"""Deterministic work selection for the dispatcher skill. Spec §4.

Selection is priority+id only; spec §4's "dependencies satisfied" clause
is deferred and not implemented here.
"""

from . import items, machine

NOT_ACTIONABLE = ("done",) + machine.SPECIAL


def _by_priority(metas):
    return sorted(metas, key=lambda m: (m.get("priority", 9999), m["id"]))


def next_item(repo):
    metas, _errors = items.list_items_safe(repo)
    actionable = [m for m in metas if m["stage"] not in NOT_ACTIONABLE]
    ordered = _by_priority(actionable)
    return ordered[0] if ordered else None


def pending_human(repo):
    metas, _errors = items.list_items_safe(repo)
    return _by_priority([m for m in metas if m["stage"] == "waiting-human"])
