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


def profile(repo, tier):
    """The effective {research, review} profile for a tier: the repo config
    `tiers.<tier>` block merged over DEFAULTS[tier]. An unknown tier falls
    back to the feature profile (matches items.DEFAULT_TIER)."""
    base = dict(DEFAULTS.get(tier, DEFAULTS["feature"]))
    block = {}
    p = paths.config_path(repo)
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            if isinstance(raw, dict) and isinstance(raw.get("tiers"), dict):
                override = raw["tiers"].get(tier)
                if isinstance(override, dict):
                    block = override
        except json.JSONDecodeError:
            block = {}
    base.update({k: v for k, v in block.items()
                if k in ("research", "review", "assure")})
    return base
