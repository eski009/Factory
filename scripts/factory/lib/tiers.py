"""Work-item materiality tiers: how much of the expensive machinery a change
is worth. tier (epic|feature|bug) is an item's frontmatter field (see
items.py); this module maps a tier to its {research, review} profile, config-
overridable per repo. Python stdlib only.

research: off | inputs-only | web | deep  — the ceiling on focus-group/market
research (deep = the focus group runs; features/bugs never trigger it).
review:  light | full — full = the six-seat council; light = the inward
correctness seats only (a bug fix needs correctness review, not a market read).
assure: node | affected | full — how much of the journey surface the assure
stage walks (changed node only / all affected journeys / affected plus core).
"""

import json

from . import paths

DEFAULTS = {
    "epic": {"research": "deep", "review": "full", "assure": "full"},
    "feature": {"research": "web", "review": "full", "assure": "affected"},
    "bug": {"research": "off", "review": "light", "assure": "node"},
}

LEVEL_KEYS = ("research", "review", "assure")


def _override(repo, tier):
    """The repo config's `tiers.<tier>` block, filtered to LEVEL_KEYS.

    An absent, unreadable or malformed config reads as {} — the
    machine._config_dict tolerance pattern. Item 0026 §3 requires that no
    config failure can raise out of machine.advance().
    """
    p = paths.config_path(repo)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict) or not isinstance(raw.get("tiers"), dict):
        return {}
    block = raw["tiers"].get(tier)
    if not isinstance(block, dict):
        return {}
    return {k: v for k, v in block.items() if k in LEVEL_KEYS}


def profile(repo, tier):
    """The effective {research, review} profile for a tier: the repo config
    `tiers.<tier>` block merged over DEFAULTS[tier]. An unknown tier falls
    back to the feature profile (matches items.DEFAULT_TIER)."""
    base = dict(DEFAULTS.get(tier, DEFAULTS["feature"]))
    base.update(_override(repo, tier))
    return base


def record(repo, tier, declared):
    """The engine's depth record: named enum levels with provenance.

    Returns {"tier", "tier_declared", "research", "review", "assure",
    "source"} where source is "config" (a tiers.<tier> block supplied at
    least one of the three keys), "defaults" (no override), or "fallback"
    (tier not in DEFAULTS — profile() serves the feature profile).

    Item 0026 §3: this RECORDS the level the tier table already publishes.
    It never sets, keys or changes a level, and it never raises — every
    failure path degrades to DEFAULTS with source "defaults".
    """
    levels = dict(DEFAULTS.get(tier, DEFAULTS["feature"]))
    try:
        override = _override(repo, tier)
    except Exception:  # pragma: no cover - belt and braces; see docstring
        override = {}
    levels.update(override)
    if tier not in DEFAULTS:
        source = "fallback"
    elif override:
        source = "config"
    else:
        source = "defaults"
    out = {"tier": tier, "tier_declared": bool(declared), "source": source}
    for key in LEVEL_KEYS:
        out[key] = levels[key]
    return out
