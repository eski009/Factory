"""Assurance human verbs: the single writers of assure.waived and
assure.confirmed. Journey-assurance spec. Skills and autopilot never call
these — a real human answers the assure gate (the factory-choice pattern)."""

from . import items, logs, paths
from .machine import GateError


def _require_assure_context(meta):
    stage = meta["stage"]
    paused_here = stage in ("waiting-human", "blocked") \
        and meta.get("paused-from") == "assure"
    if not (stage == "assure" or paused_here):
        raise GateError(
            f"requires stage assure (or paused from it); item is at {stage!r}")


def record_waiver(repo, item_id, reason):
    if not (reason or "").strip():
        raise GateError("a waiver requires a non-empty --reason")
    meta, _body = items.load_item(repo, item_id)
    _require_assure_context(meta)
    logs.append_event(repo, item_id, "assure.waived",
                      {"reason": reason.strip()})
    return meta


def record_confirmation(repo, item_id):
    meta, _body = items.load_item(repo, item_id)
    _require_assure_context(meta)
    if logs.count_events(repo, item_id, "assure.passed") == 0:
        raise GateError("nothing to confirm: assure.passed has not been logged")
    path = paths.item_dir(repo, item_id) / "assurance" / "human-confirmation.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Human confirmation\n\n- ts: {logs.now_stamp()}\n", encoding="utf-8")
    logs.append_event(repo, item_id, "assure.confirmed")
    return path
