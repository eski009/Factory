"""Design-gate support: the single writer of design/choice.md. Spec §5."""

import re

from . import items, logs, paths
from .machine import GateError

OPTION_RE = re.compile(r"^[a-d]$")


def record_choice(repo, item_id, option, notes=None):
    meta, _body = items.load_item(repo, item_id)
    if meta["kind"] not in ("ui", "mixed"):
        raise GateError(f"item kind {meta['kind']!r} has no design stage")
    stage = meta["stage"]
    at_design = stage == "design"
    paused_at_design = stage == "waiting-human" and meta.get("paused-from") == "design"
    if not (at_design or paused_at_design):
        raise GateError(f"choice requires stage design (or paused from it); item is at {stage!r}")
    if not OPTION_RE.match(option):
        raise GateError(f"option must be one of a-d, got {option!r}")
    path = paths.item_dir(repo, item_id) / "design" / "choice.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = notes if notes else "(no notes)"
    path.write_text(
        f"# Design choice\n\n- option: {option}\n- ts: {logs.now_stamp()}\n\n{body}\n",
        encoding="utf-8",
    )
    logs.append_event(repo, item_id, "design.choice", {"option": option})
    return path
