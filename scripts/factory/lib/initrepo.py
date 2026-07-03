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
            if not item_md.exists():
                continue
            try:
                meta, _ = items.parse_item(item_md.read_text(encoding="utf-8"))
                errors.extend(validate(meta, schema, sub.name))
            except items.ItemError as exc:
                errors.append(f"{sub.name}/item.md: {exc}")
    for name in LEDGERS:
        ledger = paths.ledgers_dir(repo) / f"{name}.jsonl"
        if not ledger.exists():
            continue
        for lineno, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                errors.append(f"ledgers/{name}.jsonl:{lineno}: invalid JSON")
    return errors
