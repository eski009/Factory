"""Work-item storage: .factory/items/<id>/item.md = frontmatter + body.

Frontmatter is a strict scalar subset of YAML: `key: value` lines between
`---` fences. `priority` is an integer; everything else is a string.
Writes are deterministic: fixed field order, LF endings, trailing newline.
"""

import re

from . import paths

FIELD_ORDER = (
    "id", "title", "stage", "kind", "priority",
    "created", "updated", "paused-from", "paused-reason",
)
REQUIRED_FIELDS = ("id", "title", "stage", "kind", "created", "updated")
INT_FIELDS = ("priority",)
KINDS = ("ui", "backend", "mixed")


class ItemError(ValueError):
    pass


def parse_item(text):
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        raise ItemError("item.md must start with '---'")
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        raise ItemError("unterminated frontmatter")
    meta = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        m = re.match(r"^([a-z][a-z-]*):\s*(.*)$", line)
        if not m:
            raise ItemError(f"bad frontmatter line: {line!r}")
        key, value = m.group(1), m.group(2).strip()
        if key not in FIELD_ORDER:
            raise ItemError(f"unknown field: {key}")
        if key in meta:
            raise ItemError(f"duplicate field: {key}")
        if key in INT_FIELDS:
            try:
                value = int(value)
            except ValueError:
                raise ItemError(f"{key} must be an integer, got {value!r}")
        meta[key] = value
    missing = [f for f in REQUIRED_FIELDS if f not in meta]
    if missing:
        raise ItemError("missing fields: " + ", ".join(missing))
    body = "\n".join(lines[end + 1:]).lstrip("\n")
    return meta, body


def render_item(meta, body):
    for key, value in meta.items():
        if key not in FIELD_ORDER:
            raise ItemError(f"unknown field: {key}")
        text = str(value)
        if "\n" in text or "\r" in text:
            raise ItemError(f"{key} must be a single-line value")
        if isinstance(value, str) and value != value.strip():
            raise ItemError(f"{key} must not have leading/trailing whitespace")
    out = ["---"]
    for key in FIELD_ORDER:
        if key in meta:
            out.append(f"{key}: {meta[key]}")
    out.append("---")
    out.append("")
    out.append(body.rstrip("\n"))
    return "\n".join(out).rstrip("\n") + "\n"


def load_item(repo, item_id):
    path = paths.item_dir(repo, item_id) / "item.md"
    if not path.exists():
        raise ItemError(f"no such item: {item_id}")
    meta, body = parse_item(path.read_text(encoding="utf-8"))
    if meta["id"] != item_id:
        raise ItemError(
            f"item dir {item_id!r} contains id {meta['id']!r} - "
            "dir name and id must match")
    return meta, body


def save_item(repo, meta, body=""):
    text = render_item(meta, body)
    d = paths.item_dir(repo, meta["id"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(text, encoding="utf-8")


def list_items(repo):
    d = paths.items_dir(repo)
    if not d.exists():
        return []
    out = []
    for sub in sorted(d.iterdir()):
        if (sub / "item.md").exists():
            meta, _ = parse_item((sub / "item.md").read_text(encoding="utf-8"))
            out.append(meta)
    return out


def list_items_safe(repo):
    """Like list_items, but tolerates corrupt item.md files.

    Returns (metas, errors) where errors are human-readable strings
    naming the unreadable item; the offending item is simply omitted
    from metas rather than raising.
    """
    d = paths.items_dir(repo)
    if not d.exists():
        return [], []
    metas, errors = [], []
    for sub in sorted(d.iterdir()):
        item_md = sub / "item.md"
        if not item_md.exists():
            continue
        try:
            meta, _ = parse_item(item_md.read_text(encoding="utf-8"))
            metas.append(meta)
        except ItemError as exc:
            errors.append(f"{sub.name}: {exc}")
    return metas, errors


def slugify(title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:40] or "item"


def new_item_id(repo, title):
    d = paths.items_dir(repo)
    nums = []
    if d.exists():
        for sub in d.iterdir():
            m = re.match(r"^(\d{4})-", sub.name)
            if m:
                nums.append(int(m.group(1)))
    return f"{max(nums, default=0) + 1:04d}-{slugify(title)}"
