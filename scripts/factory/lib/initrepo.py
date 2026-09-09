"""Idempotent target-repo scaffolding and whole-tree validation.

init() only fills gaps — it never overwrites an existing file — and
never touches product code, CLAUDE.md, or existing docs. Spec §2.
"""

import json
import shutil
from pathlib import Path

from . import items, paths
from .validate import validate

_INSTALL_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = _INSTALL_ROOT / "templates" / "docs-factory"
SCHEMAS = _INSTALL_ROOT / "schemas"
LEDGERS = ("bids", "judgements", "reputation", "escapes")
LEDGER_SCHEMAS = {"bids": "escalation-bid", "judgements": "orchestrator-judgement",
                  "reputation": "reputation-event", "escapes": "escape"}
DEFAULT_CONFIG = {"version": 1, "merge": "auto", "gates": ["design"],
                  "research": {"depth": "web"},
                  "assure": {"attribution": False},
                  "approach_convergence": {"enabled": False}}


def load_schema(name):
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


SPEND_TOKEN_KEYS = ("input", "output", "total")


def spend_event_errors(data, path):
    """Spend-event contract: schema plus the two conditional rules the
    stdlib validator subset cannot express. Item spec 0004 §1, §4."""
    if not isinstance(data, dict):
        return [f"{path}: spend event data must be an object"]
    errors = validate(data, load_schema("spend-event"), path)
    provenance = data.get("provenance")
    tokens = data.get("tokens")
    if tokens is not None and provenance != "measured":
        errors.append(
            f"{path}: tokens present but provenance is not 'measured'")
    if provenance == "measured" and not (
            isinstance(tokens, dict)
            and any(key in tokens for key in SPEND_TOKEN_KEYS)):
        errors.append(
            f"{path}: measured spend event requires tokens with at least "
            "one of input/output/total")
    return errors


def init(repo, product=None, design_provider=None, designsync_project=None):
    repo = Path(repo)
    created = []
    for d in (paths.items_dir(repo), paths.ledgers_dir(repo),
              paths.factory_root(repo) / "runs", paths.docs_root(repo) / "packets",
              paths.docs_root(repo) / "packets" / "reports"):
        if not d.exists():
            d.mkdir(parents=True)
            created.append(str(d.relative_to(repo)))
    config_path = paths.config_path(repo)
    if not config_path.exists():
        config = dict(DEFAULT_CONFIG)
        if product:
            config["product"] = product
        if design_provider:
            config["design"] = {"provider": design_provider}
        if designsync_project:
            config["designsync_project"] = designsync_project
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        created.append(str(config_path.relative_to(repo)))
    elif design_provider or designsync_project:
        # Fill gaps in an older config, but never replace recorded choices.
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = None
        updated = []
        design = config.get("design") if isinstance(config, dict) else None
        if (design_provider and isinstance(config, dict)
                and (design is None or (isinstance(design, dict)
                                        and "provider" not in design))):
            config.setdefault("design", {})["provider"] = design_provider
            updated.append("design.provider")
        if (designsync_project and isinstance(config, dict)
                and "designsync_project" not in config):
            config["designsync_project"] = designsync_project
            updated.append("designsync_project")
        if updated:
            config_path.write_text(
                json.dumps(config, indent=2, sort_keys=True) + "\n",
                encoding="utf-8")
            created.append(
                f"{config_path.relative_to(repo)} (updated {', '.join(updated)})")
    for name in LEDGERS:
        ledger = paths.ledgers_dir(repo) / f"{name}.jsonl"
        if not ledger.exists():
            ledger.touch()
            created.append(str(ledger.relative_to(repo)))
    for src in sorted(TEMPLATES.rglob("*")):
        if not src.is_file():
            continue
        dest = paths.docs_root(repo) / src.relative_to(TEMPLATES)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest)
            created.append(str(dest.relative_to(repo)))
    return sorted(created)


def validate_tree(repo):
    repo = Path(repo)
    errors = []
    config_path = paths.config_path(repo)
    if not config_path.exists():
        return [f"{config_path.relative_to(repo)}: missing (run init)"]
    config_snapshot = None
    config_start_errors = len(errors)
    try:
        # errors="replace" (matching the log/ledger reads below): byte
        # corruption lands in the JSONDecodeError flag path, never a
        # UnicodeDecodeError traceback. Item spec 0009 §1.
        config = json.loads(
            config_path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(config, dict):
            errors.append("config.json: not an object")
        else:
            errors.extend(validate(config, load_schema("config"), "config"))
    except json.JSONDecodeError as exc:
        errors.append(f"config.json: invalid JSON ({exc})")
    if len(errors) == config_start_errors:
        from . import config_state
        try:
            config_snapshot = config_state.capture(repo)
        except config_state.ConfigStateError as exc:
            errors.append(str(exc))
    schema = load_schema("work-item")
    items_root = paths.items_dir(repo)
    if items_root.exists():
        for sub in sorted(items_root.iterdir()):
            item_md = sub / "item.md"
            meta = None
            schema_errors = []
            if item_md.exists():
                try:
                    meta, _ = items.parse_item(
                        item_md.read_text(encoding="utf-8", errors="replace"))
                    item_id = meta.get("id")
                    if not item_id:
                        # Use the .get value throughout — an id-less or
                        # empty-id frontmatter is flagged, never crashed
                        # on. Item spec 0009 §1.
                        errors.append(f"{sub.name}/item.md: missing id")
                    elif item_id != sub.name:
                        errors.append(
                            f"{sub.name}: id {item_id!r} does not match "
                            "directory name")
                    schema_errors = validate(meta, schema, sub.name)
                    errors.extend(schema_errors)
                except items.ItemError as exc:
                    errors.append(f"{sub.name}/item.md: {exc}")
            log_path = sub / "log.jsonl"
            log_events = []
            log_valid = True
            if log_path.exists():
                for lineno, line in enumerate(
                        log_path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        errors.append(f"{sub.name}/log.jsonl:{lineno}: invalid JSON")
                        log_valid = False
                        continue
                    # Mirror logs.read_events_with_stats' well-formed-event
                    # rule (a parseable line is still corrupt when it is
                    # not a dict, or lacks "event"/"ts" — append_event
                    # writes both unconditionally) so the stage-
                    # reconciliation loop below only ever sees well-formed
                    # events. Item spec 0009 rework (review round 1).
                    if not isinstance(event, dict) or "event" not in event \
                            or "ts" not in event:
                        errors.append(f"{sub.name}/log.jsonl:{lineno}: invalid event")
                        log_valid = False
                        continue
                    log_events.append(event)
                    if event.get("event") == "spend":
                        errors.extend(spend_event_errors(
                            event.get("data"), f"{sub.name}/log.jsonl:{lineno}"))
            for rel, schema_name in (("assurance/impact.json", "assurance-impact"),
                                     ("assurance/verdicts.json", "assurance-verdicts")):
                apath = sub / rel
                if apath.exists():
                    try:
                        data = json.loads(apath.read_text(
                            encoding="utf-8", errors="replace"))
                    except json.JSONDecodeError as exc:
                        errors.append(f"{sub.name}/{rel}: invalid JSON ({exc})")
                        continue
                    errors.extend(validate(data, load_schema(schema_name),
                                           f"{sub.name}/{rel}"))
            judgement_dir = sub / "approach-judgements"
            if judgement_dir.exists():
                judgement_schema = load_schema("approach-judgement")
                for judgement_path in sorted(judgement_dir.glob("*.json")):
                    rel = f"{sub.name}/approach-judgements/{judgement_path.name}"
                    try:
                        judgement = json.loads(judgement_path.read_text(
                            encoding="utf-8", errors="replace"))
                    except (OSError, UnicodeDecodeError) as exc:
                        errors.append(f"{rel}: unreadable ({exc})")
                        continue
                    except json.JSONDecodeError as exc:
                        errors.append(f"{rel}: invalid JSON ({exc})")
                        continue
                    errors.extend(validate(judgement, judgement_schema, rel))
            if meta is not None and not schema_errors and log_valid:
                acceptance_path = sub / "acceptance.json"
                acceptance_present = (
                    acceptance_path.exists() or acceptance_path.is_symlink())
                feasibility_enabled = bool(
                    config_snapshot is not None and
                    "feasibility" in config_snapshot.value["gates"])
                if (feasibility_enabled and meta["stage"] in {"plan", "implement"}
                        and not acceptance_present):
                    errors.append(
                        f"{sub.name}/acceptance.json: required while "
                        f"feasibility is enabled at stage {meta['stage']}")
                elif acceptance_present and config_snapshot is not None:
                    from . import feasibility
                    try:
                        feasibility.validate_present(
                            repo, sub.name, config=config_snapshot)
                    except feasibility.FeasibilityError as exc:
                        errors.extend(
                            f"{sub.name}/acceptance.json: {message}"
                            for message in exc.errors)
                expected = "idea"
                for event in log_events:
                    if event.get("event") == "stage.advance":
                        data = event.get("data")
                        if isinstance(data, dict):
                            expected = data.get("to", expected)
                if meta["stage"] != expected:
                    errors.append(
                        f"{sub.name}: stage {meta['stage']!r} does not match "
                        f"log (expected {expected!r})")
    graph_path = paths.docs_root(repo) / "journeys" / "graph.json"
    if graph_path.exists():
        try:
            graph = json.loads(graph_path.read_text(
                encoding="utf-8", errors="replace"))
            errors.extend(validate(graph, load_schema("journey-graph"),
                                   "journeys/graph.json"))
        except json.JSONDecodeError as exc:
            errors.append(f"journeys/graph.json: invalid JSON ({exc})")
    entries = {}
    clean = {}
    for name in LEDGERS:
        ledger = paths.ledgers_dir(repo) / f"{name}.jsonl"
        parsed = []
        line_errors = False
        if ledger.exists():
            for lineno, line in enumerate(ledger.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    errors.append(f"ledgers/{name}.jsonl:{lineno}: invalid JSON")
                    line_errors = True
                    continue
                msgs = validate(entry, load_schema(LEDGER_SCHEMAS[name]),
                                 f"ledgers/{name}.jsonl:{lineno}")
                if msgs:
                    errors.extend(msgs)
                    line_errors = True
                else:
                    parsed.append(entry)
                    if name == "escapes":
                        if entry.get("status") == "promoted" and not entry.get("promotion"):
                            errors.append(
                                f"ledgers/escapes.jsonl:{lineno}: promoted escape "
                                "missing promotion reference")
                            line_errors = True
                        if entry.get("status") == "open" and entry.get("promotion"):
                            errors.append(
                                f"ledgers/escapes.jsonl:{lineno}: open escape must "
                                "not carry a promotion")
                            line_errors = True
        entries[name] = parsed
        clean[name] = not line_errors
    if all(clean.values()):
        errors.extend(_check_ledger_consistency(entries))
    return errors


def _check_ledger_consistency(entries):
    from . import council

    errors = []
    bids_by_id = {bid["id"]: bid for bid in entries["bids"]}
    judgements = entries["judgements"]
    reputation = entries["reputation"]

    for ledger_name in ("bids", "judgements"):
        seen = set()
        for entry in entries[ledger_name]:
            entry_id = entry.get("id")
            if entry_id in seen:
                errors.append(f"ledgers/consistency: duplicate id {entry_id}")
            seen.add(entry_id)

    judgements_by_bid = {}
    for jdg in judgements:
        judgements_by_bid.setdefault(jdg["bid"], []).append(jdg)
    for bid_id, jdgs in judgements_by_bid.items():
        if len(jdgs) > 1:
            errors.append(f"ledgers/consistency: bid {bid_id} judged more than once")

    for jdg in judgements:
        if jdg["bid"] not in bids_by_id:
            errors.append(
                f"ledgers/consistency: judgement {jdg['id']} "
                f"references unknown bid {jdg['bid']}")
        if jdg["decision"] in council.AUTHORIZING and not (
                jdg.get("surface") and jdg.get("anchor")):
            errors.append(
                f"ledgers/consistency: judgement {jdg['id']} "
                f"({jdg['decision']}) missing surface/anchor")

    judgements_by_id = {jdg["id"]: jdg for jdg in judgements}
    reputation_by_judgement = {}
    for rep in reputation:
        reputation_by_judgement.setdefault(rep["judgement"], []).append(rep)
        if rep["judgement"] not in judgements_by_id:
            errors.append(
                f"ledgers/consistency: reputation event references "
                f"unknown judgement {rep['judgement']}")

    for jdg in judgements:
        reps = reputation_by_judgement.get(jdg["id"], [])
        if len(reps) != 1:
            errors.append(
                f"ledgers/consistency: judgement {jdg['id']} has "
                f"{len(reps)} reputation events (expected 1)")
            continue
        rep = reps[0]
        bid = bids_by_id.get(jdg["bid"])
        expected_delta = council.DECISION_DELTAS.get(jdg["decision"])
        if bid is None or rep["delta"] != expected_delta \
                or rep["agent"] != bid["agent"] or rep["topic"] != bid["topic"]:
            errors.append(
                f"ledgers/consistency: reputation for {jdg['id']} "
                f"has wrong delta/agent/topic")

    counts = {}
    for entry in entries.get("escapes", []):
        counts.setdefault(entry.get("id"), []).append(entry.get("status"))
    for esc_id, statuses in counts.items():
        if len(statuses) > 2:
            errors.append(f"ledgers/consistency: escape {esc_id} has "
                          f"{len(statuses)} entries (max 2: open then promoted)")
        elif statuses not in (["open"], ["open", "promoted"]):
            errors.append(f"ledgers/consistency: escape {esc_id} entries must "
                          "be open, then promoted")
    return errors
