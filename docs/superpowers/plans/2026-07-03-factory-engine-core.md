# Factory Engine Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 1 of the Factory spec (`docs/superpowers/specs/2026-07-03-software-factory-design.md` §11): the zero-dependency Python engine — work-item storage, pipeline state machine with enforced transition gates, schema validation, idempotent target-repo init, and the `factory.py` CLI — fully unit-tested with CI.

**Architecture:** Work items are directories under `.factory/items/<id>/` holding an `item.md` (frontmatter + body), stage artifacts (spec.md, plan.md, …), and an append-only `log.jsonl`. Skills do the thinking; `factory.py advance` is the deterministic gatekeeper that refuses transitions whose file/event preconditions are unmet. All output is deterministic (fixed key order, sorted JSON keys, `FACTORY_NOW` env override for timestamps).

**Tech Stack:** Python 3.11+ standard library only (pathlib, json, re, argparse, subprocess, unittest). No third-party packages anywhere, including tests.

## Global Constraints

- Python 3 **stdlib only** — zero third-party dependencies in engine, CLI, and tests (spec §2).
- Deterministic output everywhere: `json.dumps(..., sort_keys=True)`, fixed frontmatter field order, LF line endings, trailing newline on written files.
- All timestamps come from `lib/logs.py:now_stamp()`, format `YYYY-MM-DDTHH:MM:SSZ` (UTC), overridable via the `FACTORY_NOW` environment variable (tests rely on this).
- `init` is idempotent: re-running never overwrites an existing file, only fills gaps (spec §2).
- Stage names, exactly: `idea, triage, spec, design, plan, implement, review, verify, ship, done` plus special states `blocked, waiting-human` (spec §3). Item kinds: `ui, backend, mixed`. `backend` items skip `design`.
- CLI exit codes: `0` success, `1` usage/internal error, `2` gate refusal or validation errors.
- Run tests from repo root with: `python3 -m unittest discover -s tests -v`
- Commit after every task; message style `feat:`/`test:`/`chore:` prefixes.

---

### Task 1: Repo skeleton, paths module, and work-item storage

**Files:**
- Create: `.gitignore`
- Create: `scripts/factory/lib/__init__.py` (empty)
- Create: `scripts/factory/lib/paths.py`
- Create: `scripts/factory/lib/items.py`
- Create: `tests/__init__.py` (empty)
- Test: `tests/test_items.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces (used by every later task):
  - `paths.factory_root(repo) -> Path`, `paths.items_dir(repo)`, `paths.item_dir(repo, item_id)`, `paths.ledgers_dir(repo)`, `paths.config_path(repo)`, `paths.docs_root(repo)` — all accept `str | Path`.
  - `items.ItemError(ValueError)`
  - `items.KINDS = ("ui", "backend", "mixed")`
  - `items.parse_item(text) -> (dict, str)` — meta dict + markdown body; raises `ItemError`.
  - `items.render_item(meta, body) -> str`
  - `items.load_item(repo, item_id) -> (dict, str)`; `items.save_item(repo, meta, body="")`
  - `items.list_items(repo) -> list[dict]` (sorted by id)
  - `items.new_item_id(repo, title) -> str` like `"0001-dark-mode"`; `items.slugify(title) -> str`

- [ ] **Step 1: Create skeleton files**

`.gitignore`:
```
__pycache__/
*.pyc
```

Create empty `scripts/factory/lib/__init__.py` and `tests/__init__.py`.

`scripts/factory/lib/paths.py`:
```python
"""Canonical layout of factory state inside a target repo."""

from pathlib import Path


def factory_root(repo):
    return Path(repo) / ".factory"


def items_dir(repo):
    return factory_root(repo) / "items"


def item_dir(repo, item_id):
    return items_dir(repo) / item_id


def ledgers_dir(repo):
    return factory_root(repo) / "ledgers"


def config_path(repo):
    return factory_root(repo) / "config.json"


def docs_root(repo):
    return Path(repo) / "docs" / "factory"
```

- [ ] **Step 2: Write the failing tests**

`tests/test_items.py`:
```python
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import items

VALID = """---
id: 0001-dark-mode
title: Dark mode
stage: idea
kind: ui
created: 2026-07-03T10:00:00Z
updated: 2026-07-03T10:00:00Z
---

# Dark mode
"""


class TestParseRender(unittest.TestCase):
    def test_parse_valid_item(self):
        meta, body = items.parse_item(VALID)
        self.assertEqual(meta["id"], "0001-dark-mode")
        self.assertEqual(meta["stage"], "idea")
        self.assertEqual(body, "# Dark mode\n")

    def test_priority_parsed_as_int(self):
        text = VALID.replace("kind: ui", "kind: ui\npriority: 2")
        meta, _ = items.parse_item(text)
        self.assertEqual(meta["priority"], 2)

    def test_non_integer_priority_rejected(self):
        text = VALID.replace("kind: ui", "kind: ui\npriority: high")
        with self.assertRaises(items.ItemError):
            items.parse_item(text)

    def test_missing_required_field_rejected(self):
        with self.assertRaises(items.ItemError):
            items.parse_item(VALID.replace("stage: idea\n", ""))

    def test_unknown_field_rejected(self):
        with self.assertRaises(items.ItemError):
            items.parse_item(VALID.replace("kind: ui", "kind: ui\ncolour: red"))

    def test_unterminated_frontmatter_rejected(self):
        with self.assertRaises(items.ItemError):
            items.parse_item("---\nid: x\n")

    def test_render_parse_roundtrip(self):
        meta, body = items.parse_item(VALID)
        again, body2 = items.parse_item(items.render_item(meta, body))
        self.assertEqual(meta, again)
        self.assertEqual(body.strip(), body2.strip())

    def test_render_is_deterministic_and_lf_terminated(self):
        meta, body = items.parse_item(VALID)
        out = items.render_item(meta, body)
        self.assertTrue(out.endswith("\n"))
        self.assertNotIn("\r", out)


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_load(self):
        meta, body = items.parse_item(VALID)
        items.save_item(self.repo, meta, body)
        loaded, loaded_body = items.load_item(self.repo, "0001-dark-mode")
        self.assertEqual(loaded, meta)

    def test_load_missing_raises(self):
        with self.assertRaises(items.ItemError):
            items.load_item(self.repo, "0999-nope")

    def test_list_items_sorted(self):
        for i, title in ((2, "b"), (1, "a")):
            meta, _ = items.parse_item(VALID)
            meta["id"] = f"000{i}-{title}"
            items.save_item(self.repo, meta, "")
        ids = [m["id"] for m in items.list_items(self.repo)]
        self.assertEqual(ids, ["0001-a", "0002-b"])

    def test_new_item_id_increments(self):
        self.assertEqual(items.new_item_id(self.repo, "Dark Mode!"), "0001-dark-mode")
        meta, _ = items.parse_item(VALID)
        items.save_item(self.repo, meta, "")
        self.assertEqual(items.new_item_id(self.repo, "Next"), "0002-next")

    def test_slugify(self):
        self.assertEqual(items.slugify("Hello, World! 42"), "hello-world-42")
        self.assertEqual(items.slugify("???"), "item")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_items -v`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError` (items module not implemented). Note: `scripts/` and `scripts/factory/` need empty `__init__.py` files for this import path — create `scripts/__init__.py` and `scripts/factory/__init__.py` now.

- [ ] **Step 4: Implement items.py**

`scripts/factory/lib/items.py`:
```python
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
    return parse_item(path.read_text(encoding="utf-8"))


def save_item(repo, meta, body=""):
    d = paths.item_dir(repo, meta["id"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(render_item(meta, body), encoding="utf-8")


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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_items -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add .gitignore scripts tests
git commit -m "feat: work-item storage with strict frontmatter parsing"
```

---

### Task 2: Event log (log.jsonl)

**Files:**
- Create: `scripts/factory/lib/logs.py`
- Test: `tests/test_logs.py`

**Interfaces:**
- Consumes: `paths.item_dir`.
- Produces (used by machine, CLI, and later phases):
  - `logs.now_stamp() -> str` — `FACTORY_NOW` env override, else current UTC `YYYY-MM-DDTHH:MM:SSZ`.
  - `logs.append_event(repo, item_id, event, data=None) -> dict` — appends one sorted-keys JSON line to `items/<id>/log.jsonl`, creating parents.
  - `logs.read_events(repo, item_id) -> list[dict]`
  - `logs.count_events(repo, item_id, event) -> int`

- [ ] **Step 1: Write the failing tests**

`tests/test_logs.py`:
```python
import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import logs


class TestLogs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_append_and_read(self):
        logs.append_event(self.repo, "0001-x", "item.created")
        logs.append_event(self.repo, "0001-x", "review.rejected", {"round": 1})
        events = logs.read_events(self.repo, "0001-x")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event"], "item.created")
        self.assertEqual(events[0]["ts"], "2026-07-03T12:00:00Z")
        self.assertEqual(events[1]["data"], {"round": 1})

    def test_lines_have_sorted_keys(self):
        logs.append_event(self.repo, "0001-x", "e", {"b": 1, "a": 2})
        line = (self.repo / ".factory/items/0001-x/log.jsonl").read_text().strip()
        self.assertEqual(line, json.dumps(json.loads(line), sort_keys=True))

    def test_read_missing_returns_empty(self):
        self.assertEqual(logs.read_events(self.repo, "0009-none"), [])

    def test_count_events(self):
        for _ in range(3):
            logs.append_event(self.repo, "0001-x", "review.rejected")
        self.assertEqual(logs.count_events(self.repo, "0001-x", "review.rejected"), 3)
        self.assertEqual(logs.count_events(self.repo, "0001-x", "other"), 0)

    def test_now_stamp_env_override(self):
        self.assertEqual(logs.now_stamp(), "2026-07-03T12:00:00Z")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_logs -v`
Expected: FAIL — `logs` module does not exist.

- [ ] **Step 3: Implement logs.py**

`scripts/factory/lib/logs.py`:
```python
"""Append-only per-item event log: .factory/items/<id>/log.jsonl.

One sorted-keys JSON object per line. Timestamps are UTC and can be
frozen for tests via the FACTORY_NOW environment variable.
"""

import json
import os
from datetime import datetime, timezone

from . import paths


def now_stamp():
    override = os.environ.get("FACTORY_NOW")
    if override:
        return override
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_path(repo, item_id):
    return paths.item_dir(repo, item_id) / "log.jsonl"


def append_event(repo, item_id, event, data=None):
    entry = {"event": event, "ts": now_stamp()}
    if data:
        entry["data"] = data
    path = _log_path(repo, item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def read_events(repo, item_id):
    path = _log_path(repo, item_id)
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def count_events(repo, item_id, event):
    return sum(1 for e in read_events(repo, item_id) if e["event"] == event)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_logs -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/logs.py tests/test_logs.py
git commit -m "feat: append-only per-item event log with frozen-time support"
```

---

### Task 3: Schema validator and JSON schemas

**Files:**
- Create: `scripts/factory/lib/validate.py`
- Create: `schemas/work-item.schema.json`
- Create: `schemas/config.schema.json`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `validate.validate(instance, schema, path="$") -> list[str]` — empty list means valid. Supported keywords (deliberate draft-07 subset): `type` (object/array/string/integer/number/boolean), `required`, `properties`, `additionalProperties: false`, `enum`, `pattern`, `minLength`, `minimum`, `items`.
  - `schemas/work-item.schema.json` — validates an item meta dict.
  - `schemas/config.schema.json` — validates `.factory/config.json`.

- [ ] **Step 1: Write the failing tests**

`tests/test_validate.py`:
```python
import json
import unittest
from pathlib import Path

from scripts.factory.lib.validate import validate

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def load(name):
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


GOOD_ITEM = {
    "id": "0001-dark-mode", "title": "Dark mode", "stage": "idea",
    "kind": "ui", "created": "2026-07-03T10:00:00Z",
    "updated": "2026-07-03T10:00:00Z",
}


class TestValidator(unittest.TestCase):
    def test_type_mismatch(self):
        self.assertTrue(validate("hi", {"type": "integer"}))

    def test_bool_is_not_integer(self):
        self.assertTrue(validate(True, {"type": "integer"}))

    def test_required_and_additional(self):
        schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}},
                  "additionalProperties": False}
        self.assertTrue(validate({}, schema))
        self.assertTrue(validate({"a": "x", "b": 1}, schema))
        self.assertEqual(validate({"a": "x"}, schema), [])

    def test_enum_pattern_minimum(self):
        self.assertTrue(validate("z", {"type": "string", "enum": ["a", "b"]}))
        self.assertTrue(validate("nope", {"type": "string", "pattern": "^\\d+$"}))
        self.assertTrue(validate(0, {"type": "integer", "minimum": 1}))

    def test_array_items(self):
        schema = {"type": "array", "items": {"type": "string", "enum": ["design"]}}
        self.assertEqual(validate(["design"], schema), [])
        self.assertTrue(validate(["nope"], schema))


class TestWorkItemSchema(unittest.TestCase):
    def test_good_item(self):
        self.assertEqual(validate(GOOD_ITEM, load("work-item")), [])

    def test_bad_stage_and_id(self):
        bad = dict(GOOD_ITEM, stage="shipping", id="1-x")
        errors = validate(bad, load("work-item"))
        self.assertEqual(len(errors), 2)

    def test_priority_must_be_positive_int(self):
        self.assertTrue(validate(dict(GOOD_ITEM, priority=0), load("work-item")))
        self.assertEqual(validate(dict(GOOD_ITEM, priority=1), load("work-item")), [])


class TestConfigSchema(unittest.TestCase):
    def test_default_config_valid(self):
        cfg = {"version": 1, "merge": "auto", "gates": ["design"]}
        self.assertEqual(validate(cfg, load("config")), [])

    def test_bad_merge_policy(self):
        cfg = {"version": 1, "merge": "yolo", "gates": []}
        self.assertTrue(validate(cfg, load("config")))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_validate -v`
Expected: FAIL — validate module and schema files missing.

- [ ] **Step 3: Implement validator and schemas**

`scripts/factory/lib/validate.py`:
```python
"""Deliberate draft-07 subset validator (stdlib only, no $ref/oneOf).

Returns a list of error strings; empty list means valid.
"""

import re

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


def validate(instance, schema, path="$"):
    errors = []
    expected = schema.get("type")
    if expected and not _TYPE_CHECKS[expected](instance):
        return [f"{path}: expected {expected}"]
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not one of {schema['enum']}")
    if expected == "object":
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}.{key}: required property missing")
        for key, sub in props.items():
            if key in instance:
                errors.extend(validate(instance[key], sub, f"{path}.{key}"))
        if schema.get("additionalProperties") is False:
            for key in sorted(set(instance) - set(props)):
                errors.append(f"{path}.{key}: unexpected property")
    elif expected == "array" and "items" in schema:
        for i, value in enumerate(instance):
            errors.extend(validate(value, schema["items"], f"{path}[{i}]"))
    elif expected == "string":
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match {schema['pattern']}")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
    elif expected in ("integer", "number") and "minimum" in schema:
        if instance < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
    return errors
```

`schemas/work-item.schema.json`:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "work-item",
  "type": "object",
  "required": ["id", "title", "stage", "kind", "created", "updated"],
  "additionalProperties": false,
  "properties": {
    "id": {"type": "string", "pattern": "^[0-9]{4}-[a-z0-9-]+$"},
    "title": {"type": "string", "minLength": 1},
    "stage": {
      "type": "string",
      "enum": ["idea", "triage", "spec", "design", "plan", "implement",
               "review", "verify", "ship", "done", "blocked", "waiting-human"]
    },
    "kind": {"type": "string", "enum": ["ui", "backend", "mixed"]},
    "priority": {"type": "integer", "minimum": 1},
    "created": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"},
    "updated": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"},
    "paused-from": {"type": "string"},
    "paused-reason": {"type": "string"}
  }
}
```

`schemas/config.schema.json`:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "factory-config",
  "type": "object",
  "required": ["version", "merge", "gates"],
  "additionalProperties": false,
  "properties": {
    "version": {"type": "integer", "enum": [1]},
    "merge": {"type": "string", "enum": ["auto", "queue", "tiered"]},
    "gates": {"type": "array", "items": {"type": "string", "enum": ["design", "spec", "merge"]}},
    "product": {"type": "string", "minLength": 1}
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_validate -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/validate.py schemas tests/test_validate.py
git commit -m "feat: subset JSON-schema validator plus work-item and config schemas"
```

---

### Task 4: Pipeline state machine with transition gates

**Files:**
- Create: `scripts/factory/lib/machine.py`
- Test: `tests/test_machine.py`

**Interfaces:**
- Consumes: `items.load_item/save_item`, `logs.append_event/count_events/now_stamp`, `paths.item_dir`.
- Produces (used by the CLI and every stage skill):
  - `machine.STAGES` (ordered list), `machine.SPECIAL = ("blocked", "waiting-human")`, `machine.MAX_REVIEW_REJECTIONS = 2`
  - `machine.GateError(Exception)`
  - `machine.stage_sequence(kind) -> list[str]` — full order; `backend` omits `design`.
  - `machine.next_stage(meta) -> str | None`
  - `machine.advance(repo, item_id, to, reason=None) -> dict` — validates legality + gate, updates `item.md`, appends `stage.advance` event, returns new meta. Raises `GateError` on refusal.
- Gate preconditions implemented exactly as spec §3's table; evidence events: `implement.completed`, `review.approved`, `review.rejected`, `verify.green`, `ship.merged`.

- [ ] **Step 1: Write the failing tests**

`tests/test_machine.py`:
```python
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import items, logs, machine, paths


def make_item(repo, kind="ui", stage="idea", priority=None):
    meta = {
        "id": "0001-thing", "title": "Thing", "stage": stage, "kind": kind,
        "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z",
    }
    if priority:
        meta["priority"] = priority
    items.save_item(repo, meta, "# Thing\n")
    return meta


def write(repo, rel, text="content\n"):
    p = paths.item_dir(repo, "0001-thing") / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class MachineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()


class TestSequence(MachineTest):
    def test_backend_skips_design(self):
        self.assertNotIn("design", machine.stage_sequence("backend"))
        self.assertIn("design", machine.stage_sequence("ui"))

    def test_next_stage_for_backend_spec_is_plan(self):
        meta = make_item(self.repo, kind="backend", stage="spec")
        self.assertEqual(machine.next_stage(meta), "plan")

    def test_done_has_no_next(self):
        meta = make_item(self.repo, stage="done")
        self.assertIsNone(machine.next_stage(meta))


class TestLegality(MachineTest):
    def test_skipping_ahead_refused(self):
        make_item(self.repo)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")

    def test_advance_idea_to_triage(self):
        make_item(self.repo)
        meta = machine.advance(self.repo, "0001-thing", "triage")
        self.assertEqual(meta["stage"], "triage")
        self.assertEqual(logs.count_events(self.repo, "0001-thing", "stage.advance"), 1)

    def test_pause_and_resume_only_to_paused_from(self):
        make_item(self.repo, stage="design")
        machine.advance(self.repo, "0001-thing", "waiting-human", reason="pick a design")
        meta, _ = items.load_item(self.repo, "0001-thing")
        self.assertEqual(meta["paused-from"], "design")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")
        meta = machine.advance(self.repo, "0001-thing", "design")
        self.assertNotIn("paused-from", meta)


class TestGates(MachineTest):
    def test_spec_requires_triage_record_and_priority(self):
        make_item(self.repo, stage="triage")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "spec")
        write(self.repo, "triage.md")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "spec")

    def test_spec_allowed_with_triage_and_priority(self):
        make_item(self.repo, stage="triage", priority=1)
        write(self.repo, "triage.md")
        meta = machine.advance(self.repo, "0001-thing", "spec")
        self.assertEqual(meta["stage"], "spec")

    def test_plan_requires_design_choice_for_ui(self):
        make_item(self.repo, stage="design", priority=1)
        write(self.repo, "spec.md")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")
        write(self.repo, "design/choice.md", "choice: option-b\n")
        meta = machine.advance(self.repo, "0001-thing", "plan")
        self.assertEqual(meta["stage"], "plan")

    def test_implement_requires_plan_with_task(self):
        make_item(self.repo, stage="plan", priority=1)
        write(self.repo, "plan.md", "no tasks here\n")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "implement")
        write(self.repo, "plan.md", "- [ ] Task 1\n")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "implement")["stage"], "implement")

    def test_review_requires_branch_and_completion_event(self):
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        make_item(self.repo, stage="implement", priority=1)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "review")
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"], cwd=self.repo, check=True,
                       env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                                GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
        subprocess.run(["git", "branch", "factory/0001-thing"], cwd=self.repo, check=True)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "review")
        logs.append_event(self.repo, "0001-thing", "implement.completed")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "review")["stage"], "review")

    def test_verify_requires_synthesis_and_approval(self):
        make_item(self.repo, stage="review", priority=1)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "verify")
        write(self.repo, "reviews/synthesis.md")
        logs.append_event(self.repo, "0001-thing", "review.approved")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "verify")["stage"], "verify")

    def test_ship_and_done_require_evidence_events(self):
        make_item(self.repo, stage="verify", priority=1)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")
        logs.append_event(self.repo, "0001-thing", "verify.green")
        machine.advance(self.repo, "0001-thing", "ship")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "done")
        logs.append_event(self.repo, "0001-thing", "ship.merged")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "done")["stage"], "done")

    def test_review_rework_capped(self):
        make_item(self.repo, stage="review", priority=1)
        write(self.repo, "plan.md", "- [ ] Task 1\n")
        for i in range(2):
            logs.append_event(self.repo, "0001-thing", "review.rejected")
            machine.advance(self.repo, "0001-thing", "implement")
            meta, body = items.load_item(self.repo, "0001-thing")
            meta["stage"] = "review"
            items.save_item(self.repo, meta, body)
        logs.append_event(self.repo, "0001-thing", "review.rejected")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "implement")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_machine -v`
Expected: FAIL — machine module missing.

- [ ] **Step 3: Implement machine.py**

`scripts/factory/lib/machine.py`:
```python
"""Pipeline state machine. Skills do the thinking; advance() is the
deterministic gatekeeper that refuses transitions whose preconditions
(files and logged evidence events) are unmet. Spec §3.
"""

import subprocess

from . import items, logs, paths

STAGES = ["idea", "triage", "spec", "design", "plan",
          "implement", "review", "verify", "ship", "done"]
SPECIAL = ("blocked", "waiting-human")
MAX_REVIEW_REJECTIONS = 2


class GateError(Exception):
    """Transition refused: illegal move or precondition unmet."""


def stage_sequence(kind):
    if kind == "backend":
        return [s for s in STAGES if s != "design"]
    return list(STAGES)


def next_stage(meta):
    seq = stage_sequence(meta["kind"])
    idx = seq.index(meta["stage"])
    return seq[idx + 1] if idx + 1 < len(seq) else None


def _artifact(repo, meta, rel):
    return paths.item_dir(repo, meta["id"]) / rel


def _require_file(repo, meta, rel, why):
    path = _artifact(repo, meta, rel)
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        raise GateError(f"{rel} missing or empty ({why})")


def _require_event(repo, meta, event, why):
    if logs.count_events(repo, meta["id"], event) == 0:
        raise GateError(f"event {event!r} not logged ({why})")


def _gate_spec(repo, meta):
    _require_file(repo, meta, "triage.md", "triage record required before spec")
    if "priority" not in meta:
        raise GateError("priority must be set at triage")


def _gate_design(repo, meta):
    _require_file(repo, meta, "spec.md", "spec required before design")


def _gate_plan(repo, meta):
    _require_file(repo, meta, "spec.md", "spec required before planning")
    if meta["kind"] in ("ui", "mixed"):
        _require_file(repo, meta, "design/choice.md", "recorded design choice required")


def _gate_implement(repo, meta):
    path = _artifact(repo, meta, "plan.md")
    if not path.exists() or "- [ ]" not in path.read_text(encoding="utf-8"):
        raise GateError("plan.md with at least one '- [ ]' task required")


def _gate_review(repo, meta):
    branch = f"factory/{meta['id']}"
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "refs/heads/" + branch],
        cwd=repo, capture_output=True,
    )
    if result.returncode != 0:
        raise GateError(f"implementation branch {branch} required")
    _require_event(repo, meta, "implement.completed", "implementation must be finished")


def _gate_verify(repo, meta):
    _require_file(repo, meta, "reviews/synthesis.md", "council review synthesis required")
    _require_event(repo, meta, "review.approved",
                   "review must be approved with no blocking findings")


def _gate_ship(repo, meta):
    _require_event(repo, meta, "verify.green", "verification evidence required")


def _gate_done(repo, meta):
    _require_event(repo, meta, "ship.merged", "merge must be recorded")


GATES = {
    "spec": _gate_spec, "design": _gate_design, "plan": _gate_plan,
    "implement": _gate_implement, "review": _gate_review,
    "verify": _gate_verify, "ship": _gate_ship, "done": _gate_done,
}


def advance(repo, item_id, to, reason=None):
    meta, body = items.load_item(repo, item_id)
    frm = meta["stage"]
    if to in SPECIAL:
        if frm in SPECIAL:
            raise GateError(f"cannot move {frm} -> {to}")
        meta["paused-from"] = frm
        meta["paused-reason"] = reason or ""
    elif frm in SPECIAL:
        if to != meta.get("paused-from"):
            raise GateError(f"{frm} item may only resume to {meta.get('paused-from')!r}")
        meta.pop("paused-from", None)
        meta.pop("paused-reason", None)
    elif frm == "review" and to == "implement":
        if logs.count_events(repo, item_id, "review.rejected") > MAX_REVIEW_REJECTIONS:
            raise GateError("review rejected too many times; move item to blocked")
    else:
        expected = next_stage(meta)
        if to != expected:
            raise GateError(f"illegal transition {frm} -> {to} (next is {expected!r})")
        GATES.get(to, lambda *_: None)(repo, meta)
    meta["stage"] = to
    meta["updated"] = logs.now_stamp()
    items.save_item(repo, meta, body)
    event_data = {"from": frm, "to": to}
    if reason:
        event_data["reason"] = reason
    logs.append_event(repo, item_id, "stage.advance", event_data)
    return meta
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_machine -v`
Expected: all PASS. If `test_pause_and_resume_only_to_paused_from` fails on resume, check that the resume branch does not call `GATES` (returning to a stage the item already occupied re-checks nothing; forward gates still run on the next advance).

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/machine.py tests/test_machine.py
git commit -m "feat: pipeline state machine with enforced transition gates"
```

---

### Task 5: Target-repo init and tree validation

**Files:**
- Create: `scripts/factory/lib/initrepo.py`
- Create: `templates/docs-factory/roadmap.md`
- Create: `templates/docs-factory/brain/vision.md`, `users.md`, `constraints.md`, `design-system.md`, `decisions.md`, `open-questions.md`
- Create: `templates/docs-factory/council/product.md`, `ui-taste.md`, `architecture.md`, `engineering-quality.md`, `customer.md`, `commercial.md`
- Test: `tests/test_initrepo.py`

**Interfaces:**
- Consumes: `paths.*`, `items.parse_item/ItemError`, `validate.validate`.
- Produces (used by the CLI):
  - `initrepo.init(repo, product=None) -> list[str]` — created paths relative to repo, sorted; idempotent (second run returns `[]`).
  - `initrepo.validate_tree(repo) -> list[str]` — error strings; empty means healthy.
  - `initrepo.load_schema(name) -> dict` — reads `schemas/<name>.schema.json` from the factory install.

- [ ] **Step 1: Write template files**

Every brain template follows this shape — `templates/docs-factory/brain/vision.md`:
```markdown
# Vision

<!-- What this product is, who it serves, what winning looks like.
     Every claim should cite a source: (source: <path-or-url>) -->

_Not yet written. The factory-init skill seeds this from real sources;
the triage council treats an empty surface as an open question._
```

Create `users.md` (`# Users`), `constraints.md` (`# Constraints`), `design-system.md` (`# Design System` — add line: `Tokens here are the headless fallback when DesignSync is unavailable.`), `decisions.md` (`# Decisions`), `open-questions.md` (`# Open Questions`) with the same two-part shape (comment describing purpose + not-yet-written placeholder note).

`templates/docs-factory/roadmap.md`:
```markdown
# Roadmap

<!-- Prioritized backlog. The triage council maintains this file.
     One line per item: - [priority] <item-id> <title> (stage) -->

_Empty. Add items with `/factory:add` or let triage propose them._
```

Every council role template follows this shape — `templates/docs-factory/council/product.md`:
```markdown
# Council role: product

## Scope
Product strategy, roadmap coherence, scope cuts, user value.

## Evidence standards
Claims cite brain surfaces, user feedback, or shipped outcomes — never taste alone.

## Escalation criteria
File a bid when a finding changes what should be built next or contradicts a brain surface.

## Known blind spots
Underweights implementation cost; check with architecture.

## Reputation
<!-- Derived from judgement ledger. Do not hand-edit. -->
```

Create the other five roles with role-appropriate Scope/Evidence/Escalation/Blind-spot lines:
- `ui-taste.md` — scope: visual and interaction quality, design-system conformance; blind spot: overweights polish vs shipping.
- `architecture.md` — scope: system boundaries, data flow, dependency choices; blind spot: over-engineering, YAGNI violations.
- `engineering-quality.md` — scope: test coverage, failure modes, maintainability; blind spot: perfectionism blocking merge.
- `customer.md` — scope: user outcomes, onboarding friction, real-world usage; blind spot: cannot see implementation constraints.
- `commercial.md` — scope: pricing, cost of build vs value, go-to-market impact; blind spot: underweights technical debt.

- [ ] **Step 2: Write the failing tests**

`tests/test_initrepo.py`:
```python
import json
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, paths


class InitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_init_creates_expected_tree(self):
        created = initrepo.init(self.repo, product="demo")
        self.assertTrue((self.repo / ".factory/config.json").exists())
        self.assertTrue((self.repo / ".factory/ledgers/bids.jsonl").exists())
        self.assertTrue((self.repo / "docs/factory/roadmap.md").exists())
        self.assertTrue((self.repo / "docs/factory/brain/vision.md").exists())
        self.assertTrue((self.repo / "docs/factory/council/product.md").exists())
        self.assertTrue((self.repo / "docs/factory/packets").is_dir())
        config = json.loads((self.repo / ".factory/config.json").read_text())
        self.assertEqual(config["merge"], "auto")
        self.assertEqual(config["gates"], ["design"])
        self.assertEqual(config["product"], "demo")
        self.assertEqual(created, sorted(created))

    def test_init_is_idempotent_and_never_clobbers(self):
        initrepo.init(self.repo)
        marker = self.repo / "docs/factory/brain/vision.md"
        marker.write_text("MY EDIT\n", encoding="utf-8")
        second = initrepo.init(self.repo)
        self.assertEqual(second, [])
        self.assertEqual(marker.read_text(), "MY EDIT\n")

    def test_validate_missing_config(self):
        errors = initrepo.validate_tree(self.repo)
        self.assertEqual(len(errors), 1)
        self.assertIn("run init", errors[0])

    def test_validate_clean_tree(self):
        initrepo.init(self.repo)
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_validate_flags_bad_item_and_bad_ledger_line(self):
        initrepo.init(self.repo)
        bad = paths.item_dir(self.repo, "0001-bad")
        bad.mkdir(parents=True)
        (bad / "item.md").write_text("not frontmatter\n", encoding="utf-8")
        (paths.ledgers_dir(self.repo) / "bids.jsonl").write_text("{oops\n", encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertEqual(len(errors), 2)

    def test_validate_flags_schema_violation(self):
        initrepo.init(self.repo)
        meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "")
        item_md = paths.item_dir(self.repo, "0001-x") / "item.md"
        item_md.write_text(item_md.read_text().replace("stage: idea", "stage: shipping"))
        self.assertTrue(initrepo.validate_tree(self.repo))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_initrepo -v`
Expected: FAIL — initrepo module missing.

- [ ] **Step 4: Implement initrepo.py**

`scripts/factory/lib/initrepo.py`:
```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_initrepo -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/factory/lib/initrepo.py templates tests/test_initrepo.py
git commit -m "feat: idempotent target-repo init and tree validation with templates"
```

---

### Task 6: factory.py CLI

**Files:**
- Create: `scripts/factory/factory.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces (the surface skills call — treat as stable API):
  - `python3 scripts/factory/factory.py [--repo PATH] <command>`
  - `init [--product NAME]` — prints created paths, one per line.
  - `validate` — prints errors; exit 2 if any.
  - `add TITLE [--kind ui|backend|mixed]` — prints new item id. Default kind `mixed`.
  - `status [--json]` — items sorted by (priority, id); `--json` emits a sorted-keys JSON array of meta dicts.
  - `advance ITEM STAGE [--reason TEXT]` — prints `ITEM -> STAGE`; gate refusal prints the reason to stderr, exit 2.
  - `log ITEM EVENT [--data JSON]` — appends an event (skills log evidence like `verify.green` through this).
  - `main(argv=None) -> int` importable for tests.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", self.repo, *args])
        return code, out.getvalue(), err.getvalue()

    def test_init_then_validate_ok(self):
        code, out, _ = self.run_cli("init", "--product", "demo")
        self.assertEqual(code, 0)
        self.assertIn(".factory/config.json", out)
        code, _, _ = self.run_cli("validate")
        self.assertEqual(code, 0)

    def test_validate_without_init_fails(self):
        code, _, err = self.run_cli("validate")
        self.assertEqual(code, 2)
        self.assertIn("run init", err)

    def test_add_and_status(self):
        self.run_cli("init")
        code, out, _ = self.run_cli("add", "Dark mode", "--kind", "ui")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "0001-dark-mode")
        code, out, _ = self.run_cli("status", "--json")
        rows = json.loads(out)
        self.assertEqual(rows[0]["id"], "0001-dark-mode")
        self.assertEqual(rows[0]["stage"], "idea")

    def test_advance_and_gate_refusal_exit_codes(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        code, out, _ = self.run_cli("advance", "0001-thing", "triage")
        self.assertEqual(code, 0)
        self.assertIn("0001-thing -> triage", out)
        code, _, err = self.run_cli("advance", "0001-thing", "spec")
        self.assertEqual(code, 2)
        self.assertIn("triage.md", err)

    def test_log_event(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        code, _, _ = self.run_cli("log", "0001-thing", "verify.green",
                                  "--data", '{"tests": "12 passed"}')
        self.assertEqual(code, 0)
        log = Path(self.repo, ".factory/items/0001-thing/log.jsonl").read_text()
        self.assertIn("verify.green", log)
        self.assertIn("12 passed", log)

    def test_bad_data_json_is_usage_error(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        code, _, err = self.run_cli("log", "0001-thing", "e", "--data", "{oops")
        self.assertEqual(code, 1)
        self.assertIn("--data", err)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_cli -v`
Expected: FAIL — factory module missing.

- [ ] **Step 3: Implement factory.py**

`scripts/factory/factory.py`:
```python
#!/usr/bin/env python3
"""Factory engine CLI. Exit codes: 0 ok, 1 usage/internal error, 2 gate
refusal or validation errors. Skills call this; humans can too."""

import argparse
import json
import sys

if __package__ in (None, ""):
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.factory.lib import initrepo, items, logs, machine
else:
    from .lib import initrepo, items, logs, machine


def cmd_init(args):
    for path in initrepo.init(args.repo, product=args.product):
        print(path)
    return 0


def cmd_validate(args):
    errors = initrepo.validate_tree(args.repo)
    for error in errors:
        print(error, file=sys.stderr)
    return 2 if errors else 0


def cmd_add(args):
    item_id = items.new_item_id(args.repo, args.title)
    now = logs.now_stamp()
    meta = {"id": item_id, "title": args.title, "stage": "idea",
            "kind": args.kind, "created": now, "updated": now}
    items.save_item(args.repo, meta, f"# {args.title}\n")
    logs.append_event(args.repo, item_id, "item.created")
    print(item_id)
    return 0


def cmd_status(args):
    rows = sorted(items.list_items(args.repo),
                  key=lambda m: (m.get("priority", 9999), m["id"]))
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        for m in rows:
            priority = m.get("priority", "-")
            print(f"{m['id']:<40} {m['stage']:<14} p{priority:<4} {m['kind']}")
    return 0


def cmd_advance(args):
    try:
        machine.advance(args.repo, args.item, args.stage, reason=args.reason)
    except (machine.GateError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.item} -> {args.stage}")
    return 0


def cmd_log(args):
    data = None
    if args.data:
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as exc:
            print(f"--data is not valid JSON: {exc}", file=sys.stderr)
            return 1
    try:
        items.load_item(args.repo, args.item)
    except items.ItemError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    logs.append_event(args.repo, args.item, args.event, data)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="factory")
    parser.add_argument("--repo", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="scaffold .factory/ and docs/factory/")
    p.add_argument("--product")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("validate", help="check the whole state tree")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("add", help="create a work item at stage idea")
    p.add_argument("title")
    p.add_argument("--kind", choices=items.KINDS, default="mixed")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("status", help="list items by priority")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("advance", help="move an item to a stage (gate-checked)")
    p.add_argument("item")
    p.add_argument("stage")
    p.add_argument("--reason")
    p.set_defaults(func=cmd_advance)

    p = sub.add_parser("log", help="append an evidence event to an item's log")
    p.add_argument("item")
    p.add_argument("event")
    p.add_argument("--data")
    p.set_defaults(func=cmd_log)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run: `python3 -m unittest tests.test_cli -v`
Expected: all PASS.
Run: `python3 -m unittest discover -s tests -v`
Expected: every test in the repo PASSES.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/factory.py tests/test_cli.py
git commit -m "feat: factory CLI - init, validate, add, status, advance, log"
```

---

### Task 7: CI workflow and README

**Files:**
- Create: `.github/workflows/test.yml`
- Create: `README.md`

**Interfaces:**
- Consumes: the test suite.
- Produces: green CI on push; a README any later phase extends.

- [ ] **Step 1: Write the workflow**

`.github/workflows/test.yml`:
```yaml
name: tests
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Run engine tests
        run: python3 -m unittest discover -s tests -v
```

- [ ] **Step 2: Write the README**

`README.md`:
```markdown
# Factory

An autonomous software factory for Claude Code: a product brain that
maintains a roadmap, then specs, designs, plans, implements, reviews,
verifies, and ships work items — with UI design choices as the only
default human gate.

Works on any Claude model; Fable-only features are opportunistic
upgrades, never requirements. See
`docs/superpowers/specs/2026-07-03-software-factory-design.md`.

## Status

Phase 1 (engine core) — the zero-dependency Python engine: work-item
state machine with enforced gates, schemas, target-repo init, CLI.
Skills, agents, council, and the design gate arrive in later phases.

## Install into a target repo

```bash
python3 scripts/factory/factory.py --repo /path/to/your/repo init --product your-product
python3 scripts/factory/factory.py --repo /path/to/your/repo validate
```

## Engine CLI

```bash
factory.py add "Dark mode" --kind ui   # create a work item
factory.py status                      # list items by priority
factory.py advance 0001-dark-mode triage
factory.py log 0001-dark-mode verify.green --data '{"tests":"12 passed"}'
```

`advance` is the deterministic gatekeeper: it refuses any transition
whose preconditions (files and logged evidence) are unmet.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
```

- [ ] **Step 3: Run the full suite one more time**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add .github README.md
git commit -m "chore: CI workflow and README"
```

---

## Plan Self-Review (completed)

- **Spec coverage (Phase 1 scope):** item storage + layout (§2 target-repo tree) → Tasks 1, 5; state machine + gate table (§3) → Task 4; evidence logging for audit/resume (§3, §9) → Task 2; schemas + validation (§2, §9 corrupt-tree halt) → Tasks 3, 5; CLI including `add` (§3) and `status` (§4 dispatcher input) → Task 6; CI (§10.4) → Task 7. Deliberately out of scope for Phase 1 (later plans): council ledger business rules, reputation, prune, packet rendering, dispatcher/stage skills, plugin packaging, e2e toy-repo fixture (spec §10.2 — arrives with the skills it exercises).
- **Placeholder scan:** clean — every code step contains complete code; template files whose content is summarized ("create the other five roles with role-appropriate lines") give the exact shape plus per-file content lines.
- **Type consistency:** `advance(repo, item_id, to, reason=None)` matches CLI usage; `initrepo.init` returns sorted relative paths as tested; event names (`implement.completed`, `review.approved`, `review.rejected`, `verify.green`, `ship.merged`) consistent across Task 4 gates, tests, and README.
