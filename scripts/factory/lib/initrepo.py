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
LEDGERS = ("bids", "judgements", "reputation")
LEDGER_SCHEMAS = {"bids": "escalation-bid", "judgements": "orchestrator-judgement",
                  "reputation": "reputation-event"}
DEFAULT_CONFIG = {"version": 1, "merge": "auto", "gates": ["design"]}


def load_schema(name):
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


def init(repo, product=None):
    repo = Path(repo)
    created = []
    for d in (paths.items_dir(repo), paths.ledgers_dir(repo),
              paths.factory_root(repo) / "runs", paths.docs_root(repo) / "packets"):
        if not d.exists():
            d.mkdir(parents=True)
            created.append(str(d.relative_to(repo)))
    config_path = paths.config_path(repo)
    if not config_path.exists():
        config = dict(DEFAULT_CONFIG)
        if product:
            config["product"] = product
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        created.append(str(config_path.relative_to(repo)))
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
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        errors.extend(validate(config, load_schema("config"), "config"))
    except json.JSONDecodeError as exc:
        errors.append(f"config.json: invalid JSON ({exc})")
    schema = load_schema("work-item")
    items_root = paths.items_dir(repo)
    if items_root.exists():
        for sub in sorted(items_root.iterdir()):
            item_md = sub / "item.md"
            if item_md.exists():
                try:
                    meta, _ = items.parse_item(item_md.read_text(encoding="utf-8"))
                    errors.extend(validate(meta, schema, sub.name))
                except items.ItemError as exc:
                    errors.append(f"{sub.name}/item.md: {exc}")
            log_path = sub / "log.jsonl"
            if log_path.exists():
                for lineno, line in enumerate(
                        log_path.read_text(encoding="utf-8").splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        json.loads(line)
                    except json.JSONDecodeError:
                        errors.append(f"{sub.name}/log.jsonl:{lineno}: invalid JSON")
    entries = {}
    clean = {}
    for name in LEDGERS:
        ledger = paths.ledgers_dir(repo) / f"{name}.jsonl"
        parsed = []
        line_errors = False
        if ledger.exists():
            for lineno, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
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
    return errors
