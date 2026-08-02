"""Assurance human verbs: the single writers of assure.waived and
assure.confirmed. Journey-assurance spec. Skills and autopilot never call
these — a real human answers the assure gate (the factory-choice pattern)."""

import json
import re

from . import items, logs, paths
from .machine import GateError, _postdates_latest_implement

FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


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
    path = paths.item_dir(repo, item_id) / "assurance" / "waiver.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Assurance waiver\n\n- ts: {logs.now_stamp()}\n\n{reason.strip()}\n",
        encoding="utf-8")
    logs.append_event(repo, item_id, "assure.waived",
                      {"reason": reason.strip()})
    return meta


def record_confirmation(repo, item_id):
    meta, _body = items.load_item(repo, item_id)
    _require_assure_context(meta)
    events = logs.read_events(repo, item_id)
    if not _postdates_latest_implement(events, "assure.passed"):
        raise GateError("nothing to confirm: no assure.passed after the "
                        "latest implementation round")
    path = paths.item_dir(repo, item_id) / "assurance" / "human-confirmation.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Human confirmation\n\n- ts: {logs.now_stamp()}\n", encoding="utf-8")
    logs.append_event(repo, item_id, "assure.confirmed")
    return path


def file_base_defect(repo, item_id, journey, scenario, fingerprint, title,
                     expected="", actual=""):
    """Item 0013 §7: every pre-existing fail terminates in a real item.

    Idempotent and repo-wide: the lookup scans every item whose stage is
    not 'done' for the body line `- base-defect-fingerprint: <hex>`. A
    match returns that id and creates nothing. Returns (owner_id, deduped).

    The engine treats the fingerprint as an opaque 64-hex token; the caller
    computes it as sha256("<journey>\\n<scenario>\\n<normalised failing
    expectation text>"). Filed items are stage idea, kind backend, tier bug,
    with NO priority (unprioritised sorts last) and NO `bug` flag (setting
    it would engage _gate_plan's repro gate on an item nobody replicated).
    """
    items.load_item(repo, item_id)          # the originating item must exist
    fingerprint = (fingerprint or "").strip().lower()
    if not FINGERPRINT_RE.match(fingerprint):
        raise GateError("--fingerprint must be 64 lowercase hex characters")
    title = (title or "").strip()
    if not title:
        raise GateError("--title must not be empty")
    marker = f"- base-defect-fingerprint: {fingerprint}"
    # Line-anchored, not substring containment: a body that merely QUOTES
    # the fingerprint line inside other text must not dedupe-match.
    marker_re = re.compile(
        r"^- base-defect-fingerprint: " + re.escape(fingerprint) + r"$",
        re.MULTILINE)
    root = paths.items_dir(repo)
    if root.exists():
        for sub in sorted(root.iterdir()):
            if not (sub / "item.md").exists():
                continue
            try:
                meta, body = items.load_item(repo, sub.name)
            except items.ItemError:
                continue
            if meta.get("stage") == "done" or not marker_re.search(body):
                continue
            logs.append_event(repo, item_id, "assure.filed",
                              {"owner": meta["id"], "journey": journey,
                               "scenario": scenario, "deduped": True})
            return meta["id"], True
    owner = items.new_item_id(repo, title)
    now = logs.now_stamp()
    body = "\n".join([
        f"# {title}", "",
        "Filed by the engine from a base (pre-existing) assurance fail. It "
        "reproduced at the merge base, so it did not block the originating "
        "item's ship - it is real, open, and unprioritised until triaged.",
        "", marker,
        f"- filed-from: {item_id}",
        f"- journey: {journey}",
        f"- scenario: {scenario}",
        f"- expected: {expected}",
        f"- actual: {actual}",
        ""])
    items.save_item(repo, {"id": owner, "title": title, "stage": "idea",
                           "kind": "backend", "tier": "bug",
                           "created": now, "updated": now}, body)
    logs.append_event(repo, owner, "item.created")
    logs.append_event(repo, item_id, "assure.filed",
                      {"owner": owner, "journey": journey,
                       "scenario": scenario, "deduped": False})
    return owner, False
