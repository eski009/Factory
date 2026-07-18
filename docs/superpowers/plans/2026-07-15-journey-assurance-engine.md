# Journey Assurance — Plan 1: Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The deterministic engine layer of Journey Assurance: an `assure` stage between `verify` and `ship`, a `journeys` frontmatter declaration with engine-enforced spec-exit gates, a round-scoped ship gate over schema-validated assurance artifacts, human-only `waive`/`confirm` verbs, and an append-only Escape Register.

**Architecture:** Pure additive changes to the existing zero-dependency Python engine (`scripts/factory/`). Skills stay untouched in this plan — an item reaching `assure` in a live repo parks via dispatch's existing skill-unavailable path until Plan 3 adds the skill. Gates check artifact shape/presence/coverage and event ordering, never journey coherence.

**Tech Stack:** Python 3.11 stdlib only. Tests: `unittest` (`python3 -m unittest discover -s tests`). Schemas: draft-07 SUBSET validator (`scripts/factory/lib/validate.py` — no `$ref`/`oneOf`/`null` type/`maximum`; `pattern` uses `re.search`, so anchor with `^...$`).

**Spec:** `docs/superpowers/specs/2026-07-15-journey-assurance-design.md` (read the Engine + Edge cases sections before starting).

## Global Constraints

- Python stdlib only; no new dependencies.
- Exit codes: 0 ok, 1 usage/internal error, 2 gate refusal or validation errors.
- Event shape: `{"event": ..., "ts": ..., "data"?: ...}` via `logs.append_event`; timestamps freezable via `FACTORY_NOW`.
- Frontmatter is a strict whitelist (`items.FIELD_ORDER`); values single-line; unknown fields are parse errors.
- Gates fail closed on unreadable/undecodable evidence (`machine._read_text_or_empty`).
- `config.schema.json` is `additionalProperties: false` at every level — every new key needs a schema change in the same task.
- Journey IDs match `^J-[0-9]{3}$`; the `journeys` frontmatter value matches `^(none|J-[0-9]{3}(,J-[0-9]{3})*)$` (no spaces).
- Run the FULL suite (`python3 -m unittest discover -s tests`) before every commit; fix any fixture the change legitimately breaks in the same commit.
- Commit messages: conventional style, ending with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: `journeys` frontmatter field, stage insertion, sequence skip, `factory journeys` verb

**Files:**
- Modify: `scripts/factory/lib/items.py` (FIELD_ORDER, new helpers at end)
- Modify: `scripts/factory/lib/machine.py:16-17` (STAGES), `:26-38` (stage_sequence/next_stage)
- Modify: `schemas/work-item.schema.json` (stage enum, journeys property)
- Modify: `scripts/factory/factory.py` (cmd_journeys + subparser, after the `tier` block)
- Test: `tests/test_items.py`, `tests/test_machine.py`, create `tests/test_cli_journeys.py`

**Interfaces:**
- Produces: `items.JOURNEYS_RE`, `items.set_journeys(repo, item_id, value) -> meta` (logs `journeys.set` event, raises `items.ItemError` on bad value), `machine.stage_sequence(kind, journeys=None) -> list`, STAGES containing `"assure"` between `"verify"` and `"ship"`, CLI `factory journeys <id> <value>` (exit 2 + `refused:` on stderr for bad values).

- [ ] **Step 1: Write the failing tests**

In `tests/test_items.py` add:

```python
class TestJourneys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _make(self):
        meta = {"id": "0001-a", "title": "A", "stage": "idea", "kind": "ui",
                "created": "2026-07-15T10:00:00Z", "updated": "2026-07-15T10:00:00Z"}
        items.save_item(self.repo, meta, "# A\n")

    def test_set_journeys_accepts_none_and_id_lists(self):
        self._make()
        for value in ("none", "J-001", "J-001,J-042"):
            meta = items.set_journeys(self.repo, "0001-a", value)
            self.assertEqual(meta["journeys"], value)

    def test_set_journeys_logs_event(self):
        self._make()
        items.set_journeys(self.repo, "0001-a", "J-001")
        from scripts.factory.lib import logs
        self.assertEqual(logs.count_events(self.repo, "0001-a", "journeys.set"), 1)

    def test_set_journeys_rejects_bad_values(self):
        self._make()
        for bad in ("", "J-1", "J-001,", "nope", "J-001, J-002", "NONE"):
            with self.assertRaises(items.ItemError):
                items.set_journeys(self.repo, "0001-a", bad)

    def test_journeys_field_round_trips(self):
        meta = {"id": "0001-a", "title": "A", "stage": "idea", "kind": "ui",
                "journeys": "J-001,J-002",
                "created": "2026-07-15T10:00:00Z", "updated": "2026-07-15T10:00:00Z"}
        parsed, _ = items.parse_item(items.render_item(meta, "body"))
        self.assertEqual(parsed["journeys"], "J-001,J-002")
```

(Use the existing imports at the top of test_items.py; add `import tempfile` / `from pathlib import Path` only if not already present.)

In `tests/test_machine.py`, class `TestSequence`, add:

```python
    def test_assure_sits_between_verify_and_ship(self):
        seq = machine.stage_sequence("ui")
        self.assertEqual(seq.index("assure"), seq.index("verify") + 1)
        self.assertEqual(seq.index("ship"), seq.index("assure") + 1)

    def test_journeys_none_skips_assure(self):
        self.assertNotIn("assure", machine.stage_sequence("ui", "none"))
        self.assertNotIn("assure", machine.stage_sequence("backend", "none"))
        self.assertIn("assure", machine.stage_sequence("ui", "J-001"))
        self.assertIn("assure", machine.stage_sequence("ui", None))

    def test_next_stage_verify_routes_by_journeys(self):
        meta = make_item(self.repo, stage="verify")
        self.assertEqual(machine.next_stage(meta), "assure")
        meta["journeys"] = "none"
        self.assertEqual(machine.next_stage(meta), "ship")
```

Create `tests/test_cli_journeys.py` (mirror `tests/test_cli_tier.py`'s structure — read it first and copy its harness for invoking `factory.main` with a temp repo):

```python
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.factory import factory
from scripts.factory.lib import initrepo, items, logs


class TestCliJourneys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-15T12:00:00Z"
        factory.main(["--repo", str(self.repo), "add", "Thing"])

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_journeys_sets_frontmatter_and_event(self):
        code = factory.main(["--repo", str(self.repo), "journeys", "0001-thing", "J-001,J-002"])
        self.assertEqual(code, 0)
        meta, _ = items.load_item(self.repo, "0001-thing")
        self.assertEqual(meta["journeys"], "J-001,J-002")
        self.assertEqual(logs.count_events(self.repo, "0001-thing", "journeys.set"), 1)

    def test_journeys_rejects_bad_value_exit_2(self):
        with patch("sys.stderr", new_callable=StringIO) as err:
            code = factory.main(["--repo", str(self.repo), "journeys", "0001-thing", "J-1"])
        self.assertEqual(code, 2)
        self.assertIn("refused", err.getvalue())

    def test_item_with_journeys_passes_validate(self):
        factory.main(["--repo", str(self.repo), "journeys", "0001-thing", "none"])
        self.assertEqual(factory.main(["--repo", str(self.repo), "validate"]), 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_items.TestJourneys tests.test_cli_journeys -v` and `python3 -m unittest tests.test_machine.TestSequence -v`
Expected: FAIL/ERROR (`AttributeError: ... set_journeys`, `TypeError: stage_sequence() takes 1 positional argument`, etc.)

- [ ] **Step 3: Implement**

`scripts/factory/lib/items.py` — change `FIELD_ORDER` to:

```python
FIELD_ORDER = (
    "id", "title", "stage", "kind", "tier", "bug", "journeys", "priority",
    "created", "updated", "paused-from", "paused-reason",
)
```

and append at the end of the file:

```python
JOURNEYS_RE = re.compile(r"^(none|J-\d{3}(,J-\d{3})*)$")


def set_journeys(repo, item_id, value):
    """Record the item's declared journey impact: 'none' or a comma-
    separated list of journey ids (J-004,J-011). Absent means undeclared —
    the spec-exit gates refuse to advance until this is set."""
    if not JOURNEYS_RE.match(value or ""):
        raise ItemError(
            "journeys must be 'none' or comma-separated ids like J-004,J-011")
    meta, body = load_item(repo, item_id)
    meta["journeys"] = value
    meta["updated"] = logs.now_stamp()
    save_item(repo, meta, body)
    logs.append_event(repo, item_id, "journeys.set", {"journeys": value})
    return meta
```

`scripts/factory/lib/machine.py` — STAGES and sequence:

```python
STAGES = ["idea", "triage", "spec", "design", "plan",
          "implement", "review", "verify", "assure", "ship", "done"]
```

```python
def stage_sequence(kind, journeys=None):
    seq = list(STAGES)
    if kind == "backend":
        seq = [s for s in seq if s != "design"]
    if journeys == "none":
        seq = [s for s in seq if s != "assure"]
    return seq


def next_stage(meta):
    seq = stage_sequence(meta["kind"], meta.get("journeys"))
    try:
        idx = seq.index(meta["stage"])
    except ValueError:
        raise GateError(f"unknown stage {meta['stage']!r} for kind {meta['kind']!r}")
    return seq[idx + 1] if idx + 1 < len(seq) else None
```

`schemas/work-item.schema.json` — stage enum gains `"assure"` (after `"verify"`), and properties gain:

```json
    "journeys": {"type": "string", "pattern": "^(none|J-[0-9]{3}(,J-[0-9]{3})*)$"},
```

`scripts/factory/factory.py` — after `cmd_tier` add:

```python
def cmd_journeys(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        items.set_journeys(args.repo, args.item, args.value)
    except items.ItemError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.item} journeys {args.value}")
    return 0
```

and after the `tier` subparser block:

```python
    p = sub.add_parser("journeys",
                       help="declare an item's journey impact (none or J-ids)")
    p.add_argument("item")
    p.add_argument("value")
    p.set_defaults(func=cmd_journeys)
```

- [ ] **Step 4: Run the full suite**

Run: `python3 -m unittest discover -s tests`
Expected: the new tests PASS. `grep -rn "stage_sequence" scripts/ tests/` and fix any caller assuming the 1-arg signature (the new arg is optional, so existing calls stay valid). Some existing tests WILL fail because verify's next stage is now `assure` (e.g. `test_machine.TestGates.test_ship_and_done_require_evidence_events`, `tests/test_pipeline_walk.py`, `tests/test_e2e_cli.py`, possibly `tests/test_dispatch.py`/`tests/test_cli.py`). For THIS task only, make the minimal legitimate fixture fix: give those items `journeys: none` (add `"journeys": "none"` to the fixture meta, or run the new verb in CLI-driven tests) so they keep their old verify→ship path. Do NOT touch gate logic to accommodate tests.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(engine): assure stage, journeys frontmatter + factory journeys verb

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Spec-exit gates require recorded journey impact

**Files:**
- Modify: `scripts/factory/lib/machine.py` (`_gate_design`, `_gate_plan`, new `_require_journey_impact`)
- Test: `tests/test_machine.py`

**Interfaces:**
- Consumes: Task 1's `journeys` field.
- Produces: `_gate_design`/`_gate_plan` refuse unless `spec.md` contains the literal heading `## Journey impact` AND `"journeys" in meta`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_machine.py`, add a module-level constant after the `write` helper and new tests in `TestGates`:

```python
SPEC_MD = "# Spec\n\n## Journey impact\nNone - no customer journey affected.\n"
```

```python
    def test_design_requires_journey_impact_section_and_declaration(self):
        meta = make_item(self.repo, stage="spec", priority=1)
        write(self.repo, "spec.md", "# Spec without the section\n")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "design")
        write(self.repo, "spec.md", SPEC_MD)
        # section present but journeys never declared -> still refused
        meta, body = items.load_item(self.repo, "0001-thing")
        meta.pop("journeys", None)
        items.save_item(self.repo, meta, body)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "design")
        items.set_journeys(self.repo, "0001-thing", "none")
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "design")["stage"], "design")

    def test_plan_requires_journey_impact_for_backend(self):
        make_item(self.repo, kind="backend", stage="spec", priority=1)
        write(self.repo, "spec.md", "# Spec without the section\n")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_machine.TestGates -v`
Expected: the two new tests FAIL (gates currently pass with a bare spec.md).

- [ ] **Step 3: Implement**

In `scripts/factory/lib/machine.py`, after `_require_event` add:

```python
def _require_journey_impact(repo, meta):
    """Journey-assurance spec: the engine refuses to leave spec until the
    impact is recorded. 'none' is a valid answer; an omitted one is not."""
    path = _artifact(repo, meta, "spec.md")
    if "## Journey impact" not in _read_text_or_empty(path):
        raise GateError("spec.md must contain a '## Journey impact' section")
    if "journeys" not in meta:
        raise GateError(
            "journey impact must be declared: factory journeys <id> <none|J-...>")
```

and call it from both spec-exit gates:

```python
def _gate_design(repo, meta):
    _require_file(repo, meta, "spec.md", "spec required before design")
    _require_journey_impact(repo, meta)
```

In `_gate_plan`, add `_require_journey_impact(repo, meta)` immediately after the existing `_require_file(repo, meta, "spec.md", ...)` line.

- [ ] **Step 4: Run the full suite; migrate fixtures**

Run: `python3 -m unittest discover -s tests`
Every existing test that advances into design or plan with a bare `spec.md` now fails. Fix fixtures — never the gates: change those `write(self.repo, "spec.md")` calls to `write(self.repo, "spec.md", SPEC_MD)` and ensure the fixture meta carries `"journeys": "none"` (Task 1 already set most). The same applies in `tests/test_pipeline_walk.py`, `tests/test_e2e_cli.py`, `tests/test_dispatch.py`, `tests/test_cli.py`, `tests/test_design.py` wherever spec.md fixtures feed a design/plan advance (grep for `spec.md`).
Expected: full suite PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(engine): spec-exit gates require recorded journey impact

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Assure entry gate + assure→implement rework edge

**Files:**
- Modify: `scripts/factory/lib/machine.py` (`MAX_ASSURE_REJECTIONS`, `_gate_assure`, GATES, `advance` backward edge, module docstring)
- Test: `tests/test_machine.py`

**Interfaces:**
- Produces: entering `assure` requires the `verify.green` event; `advance(repo, id, "implement")` from `assure` allowed while `count(assure.rejected) <= 2`; docstring documents that the assure/ship gates are round-scoped (Task 4) while all other gates stay lifetime-count.

- [ ] **Step 1: Write the failing tests**

In `tests/test_machine.py` `TestGates`:

```python
    def test_assure_requires_verify_green(self):
        make_item(self.repo, stage="verify", priority=1)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "assure")
        logs.append_event(self.repo, "0001-thing", "verify.green")
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "assure")["stage"], "assure")

    def test_assure_rework_capped(self):
        make_item(self.repo, stage="assure", priority=1)
        write(self.repo, "plan.md", "- [ ] Task 1\n")
        for _ in range(2):
            logs.append_event(self.repo, "0001-thing", "assure.rejected")
            machine.advance(self.repo, "0001-thing", "implement")
            meta, body = items.load_item(self.repo, "0001-thing")
            meta["stage"] = "assure"
            items.save_item(self.repo, meta, body)
        logs.append_event(self.repo, "0001-thing", "assure.rejected")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "implement")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_machine.TestGates.test_assure_requires_verify_green tests.test_machine.TestGates.test_assure_rework_capped -v`
Expected: FAIL (`illegal transition verify -> assure`? No — Task 1 made assure the next stage, so the first fails because no gate refuses yet: `advance` succeeds without verify.green. The second fails with `illegal transition assure -> implement`.)

- [ ] **Step 3: Implement**

In `machine.py`: add `MAX_ASSURE_REJECTIONS = 2` next to `MAX_REVIEW_REJECTIONS`; add the gate after `_gate_verify`:

```python
def _gate_assure(repo, meta):
    _require_event(repo, meta, "verify.green",
                   "verification evidence required before assurance")
```

register `"assure": _gate_assure,` in `GATES`; and in `advance()` insert after the `review -> implement` branch:

```python
    elif frm == "assure" and to == "implement":
        if logs.count_events(repo, item_id, "assure.rejected") > MAX_ASSURE_REJECTIONS:
            raise GateError("assurance rejected too many times; move item to blocked")
```

Update the module docstring's round-scoping note: evidence events are lifetime counts EXCEPT the ship gate's assurance events, which are round-scoped (see `_gate_ship`, Task 4).

- [ ] **Step 4: Run the full suite**

Run: `python3 -m unittest discover -s tests`
Expected: PASS (fixtures that advance verify→assure→ship don't exist yet outside these tests).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(engine): assure entry gate + bounded assure->implement rework edge

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Assurance schemas + round-scoped ship gate over validated artifacts

**Files:**
- Create: `schemas/assurance-impact.schema.json`, `schemas/assurance-verdicts.schema.json`
- Modify: `scripts/factory/lib/machine.py` (`_last_index`, `_config_gates`, `_validate_assurance_artifacts`, new `_gate_ship`)
- Test: `tests/test_machine.py` (new class `TestShipGateAssurance`)

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `_gate_ship` semantics — `journeys == "none"` → `verify.green` only; otherwise requires latest `assure.passed`-or-`assure.waived` after latest `implement.completed`; when `"assure"` is in config `gates`, additionally latest `assure.confirmed`-or-waived after latest `implement.completed`; when passed (not waived), `assurance/verdicts.json` must schema-validate, cover all declared journey ids and all `impact.json` scenario ids, contain only `pass` verdicts, and every evidence path must exist under the item dir.

- [ ] **Step 1: Create the schemas**

`schemas/assurance-verdicts.schema.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "assurance-verdicts",
  "type": "object",
  "required": ["item", "journeys"],
  "additionalProperties": false,
  "properties": {
    "item": {"type": "string", "minLength": 1},
    "ts": {"type": "string"},
    "journeys": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "surface", "scenarios"],
        "additionalProperties": false,
        "properties": {
          "id": {"type": "string", "pattern": "^J-[0-9]{3}$"},
          "surface": {"type": "string", "enum": ["browser", "cli", "api"]},
          "contract_status": {"type": "string", "enum": ["draft", "approved"]},
          "scenarios": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["id", "verdict", "expected", "actual"],
              "additionalProperties": false,
              "properties": {
                "id": {"type": "string", "minLength": 1},
                "verdict": {"type": "string",
                            "enum": ["pass", "fail", "ambiguity", "blocker"]},
                "expected": {"type": "string", "minLength": 1},
                "actual": {"type": "string", "minLength": 1},
                "notes": {"type": "string"},
                "evidence": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "required": ["type", "path"],
                    "additionalProperties": false,
                    "properties": {
                      "type": {"type": "string",
                               "enum": ["screenshot", "dom", "console",
                                        "network", "transcript"]},
                      "path": {"type": "string", "minLength": 1}
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

`schemas/assurance-impact.schema.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "assurance-impact",
  "type": "object",
  "required": ["item", "journeys"],
  "additionalProperties": false,
  "properties": {
    "item": {"type": "string", "minLength": 1},
    "ts": {"type": "string"},
    "journeys": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "scenarios"],
        "additionalProperties": false,
        "properties": {
          "id": {"type": "string", "pattern": "^J-[0-9]{3}$"},
          "nodes_changed": {"type": "array", "items": {"type": "string"}},
          "transitions_changed": {"type": "array", "items": {"type": "string"}},
          "new_states": {"type": "array", "items": {"type": "string"}},
          "scenarios": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["id", "kind", "description"],
              "additionalProperties": false,
              "properties": {
                "id": {"type": "string", "minLength": 1},
                "kind": {"type": "string",
                         "enum": ["happy", "recovery", "interruption"]},
                "description": {"type": "string", "minLength": 1}
              }
            }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_machine.py`:

```python
import json


def _write_assurance(repo, verdict="pass", journey="J-001", scenario="happy-1",
                     evidence=True, item_id="0001-thing"):
    item_dir = paths.item_dir(repo, item_id)
    ev = []
    if evidence:
        shot = item_dir / "assurance" / "screenshots" / "s1.txt"
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_text("evidence\n", encoding="utf-8")
        ev = [{"type": "screenshot", "path": "assurance/screenshots/s1.txt"}]
    verdicts = {"item": item_id, "journeys": [{
        "id": journey, "surface": "browser",
        "scenarios": [{"id": scenario, "verdict": verdict,
                       "expected": "welcome screen", "actual": "welcome screen",
                       "evidence": ev}]}]}
    vp = item_dir / "assurance" / "verdicts.json"
    vp.parent.mkdir(parents=True, exist_ok=True)
    vp.write_text(json.dumps(verdicts, indent=2), encoding="utf-8")


class TestShipGateAssurance(MachineTest):
    def _to_assure(self, journeys="J-001"):
        meta = make_item(self.repo, stage="assure", priority=1)
        meta, body = items.load_item(self.repo, "0001-thing")
        meta["journeys"] = journeys
        items.save_item(self.repo, meta, body)
        logs.append_event(self.repo, "0001-thing", "implement.completed")
        logs.append_event(self.repo, "0001-thing", "verify.green")

    def test_ship_requires_assure_passed_after_latest_implement(self):
        self._to_assure()
        _write_assurance(self.repo)
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "ship")["stage"], "ship")

    def test_stale_assure_passed_from_before_rework_refused(self):
        self._to_assure()
        _write_assurance(self.repo)
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        logs.append_event(self.repo, "0001-thing", "implement.completed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")

    def test_waiver_bypasses_artifact_checks(self):
        self._to_assure()
        logs.append_event(self.repo, "0001-thing", "assure.waived",
                          {"reason": "browser unavailable in CI"})
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "ship")["stage"], "ship")

    def test_failing_verdict_refused(self):
        self._to_assure()
        _write_assurance(self.repo, verdict="fail")
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")

    def test_verdicts_must_cover_declared_journeys(self):
        self._to_assure(journeys="J-001,J-002")
        _write_assurance(self.repo)  # only covers J-001
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")

    def test_missing_evidence_file_refused(self):
        self._to_assure()
        _write_assurance(self.repo)
        shot = paths.item_dir(self.repo, "0001-thing") / "assurance" / "screenshots" / "s1.txt"
        shot.unlink()
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")

    def test_verdicts_must_cover_impact_scenarios(self):
        self._to_assure()
        impact = {"item": "0001-thing", "journeys": [{
            "id": "J-001", "scenarios": [
                {"id": "happy-1", "kind": "happy", "description": "d"},
                {"id": "recovery-1", "kind": "recovery", "description": "d"}]}]}
        ip = paths.item_dir(self.repo, "0001-thing") / "assurance" / "impact.json"
        ip.parent.mkdir(parents=True, exist_ok=True)
        ip.write_text(json.dumps(impact), encoding="utf-8")
        _write_assurance(self.repo)  # only scenario happy-1
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")

    def test_config_assure_gate_requires_confirmation(self):
        cfg = paths.config_path(self.repo)
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"version": 1, "merge": "auto",
                                   "gates": ["design", "assure"]}), encoding="utf-8")
        self._to_assure()
        _write_assurance(self.repo)
        logs.append_event(self.repo, "0001-thing", "assure.passed")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "ship")
        logs.append_event(self.repo, "0001-thing", "assure.confirmed")
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "ship")["stage"], "ship")

    def test_journeys_none_ship_gate_unchanged(self):
        meta = make_item(self.repo, stage="verify", priority=1)
        meta, body = items.load_item(self.repo, "0001-thing")
        meta["journeys"] = "none"
        items.save_item(self.repo, meta, body)
        logs.append_event(self.repo, "0001-thing", "verify.green")
        self.assertEqual(
            machine.advance(self.repo, "0001-thing", "ship")["stage"], "ship")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_machine.TestShipGateAssurance -v`
Expected: most FAIL — current `_gate_ship` only checks `verify.green`.

- [ ] **Step 4: Implement**

In `machine.py` add `import json` at the top, then after `_require_event`:

```python
def _last_index(events, name):
    idx = -1
    for i, event in enumerate(events):
        if event["event"] == name:
            idx = i
    return idx


def _config_gates(repo):
    try:
        raw = json.loads(paths.config_path(repo).read_text(
            encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    gates = raw.get("gates", []) if isinstance(raw, dict) else []
    return [g for g in gates if isinstance(g, str)]


def _validate_assurance_artifacts(repo, meta):
    from .initrepo import load_schema
    from .validate import validate as validate_schema

    vpath = _artifact(repo, meta, "assurance/verdicts.json")
    text = _read_text_or_empty(vpath)
    if not text.strip():
        raise GateError("assurance/verdicts.json missing or empty "
                        "(assurance evidence required)")
    try:
        verdicts = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GateError(f"assurance/verdicts.json invalid JSON ({exc})")
    errors = validate_schema(verdicts, load_schema("assurance-verdicts"), "verdicts")
    if errors:
        raise GateError("assurance/verdicts.json: " + "; ".join(errors))
    declared = [j for j in (meta.get("journeys") or "").split(",")
                if j and j != "none"]
    covered = {j.get("id"): j for j in verdicts.get("journeys", [])}
    missing = [j for j in declared if j not in covered]
    if missing:
        raise GateError("assurance verdicts missing journeys: " + ", ".join(missing))
    item_dir = paths.item_dir(repo, meta["id"])
    for j in verdicts.get("journeys", []):
        for s in j.get("scenarios", []):
            if s.get("verdict") != "pass":
                raise GateError(
                    f"journey {j.get('id')} scenario {s.get('id')}: "
                    f"verdict {s.get('verdict')!r} is not pass")
            for ev in s.get("evidence", []):
                if not (item_dir / ev.get("path", "")).exists():
                    raise GateError(
                        "assurance evidence missing on disk: " + ev.get("path", ""))
    itext = _read_text_or_empty(_artifact(repo, meta, "assurance/impact.json"))
    if itext.strip():
        try:
            impact = json.loads(itext)
        except json.JSONDecodeError as exc:
            raise GateError(f"assurance/impact.json invalid JSON ({exc})")
        for j in impact.get("journeys", []) if isinstance(impact, dict) else []:
            have = {s.get("id") for s in covered.get(j.get("id"), {}).get("scenarios", [])}
            want = {s.get("id") for s in j.get("scenarios", []) if isinstance(s, dict)}
            unmet = sorted(want - have)
            if unmet:
                raise GateError(
                    f"journey {j.get('id')}: required scenarios without verdicts: "
                    + ", ".join(str(u) for u in unmet))
```

Replace `_gate_ship`:

```python
def _gate_ship(repo, meta):
    if meta.get("journeys") == "none":
        _require_event(repo, meta, "verify.green", "verification evidence required")
        return
    events = logs.read_events(repo, meta["id"])
    impl = _last_index(events, "implement.completed")
    passed = _last_index(events, "assure.passed") > impl
    waived = _last_index(events, "assure.waived") > impl
    if not (passed or waived):
        raise GateError("assure.passed (or a recorded human waiver) after the "
                        "latest implementation round required")
    if "assure" in _config_gates(repo) and not (
            waived or _last_index(events, "assure.confirmed") > impl):
        raise GateError("human confirmation required: factory confirm <id> "
                        "(the assure gate is configured)")
    if waived and not passed:
        return
    _validate_assurance_artifacts(repo, meta)
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests`
Expected: PASS. (Legacy fixtures set `journeys: none` in Tasks 1–2, so they take the unchanged branch. Any remaining test advancing an undeclared item to ship must gain `journeys: none` — same fixture rule as before.)

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(engine): round-scoped ship gate over schema-validated assurance artifacts

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `lib/assure.py` — human-only waive and confirm verbs

**Files:**
- Create: `scripts/factory/lib/assure.py`
- Modify: `scripts/factory/factory.py` (import, `cmd_waive`, `cmd_confirm`, subparsers)
- Test: create `tests/test_assure_verbs.py`

**Interfaces:**
- Consumes: Task 3's stage semantics.
- Produces: `assure.record_waiver(repo, item_id, reason) -> meta` (logs `assure.waived {"reason": ...}`), `assure.record_confirmation(repo, item_id) -> path` (requires a logged `assure.passed`; writes `assurance/human-confirmation.md`; logs `assure.confirmed`). Both raise `machine.GateError` unless the item is at `assure`, or `waiting-human`/`blocked` with `paused-from: assure`. CLI: `factory waive <id> --reason "..."`, `factory confirm <id>` (exit 2 + `refused:` on stderr on refusal).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_assure_verbs.py`:

```python
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.factory import factory
from scripts.factory.lib import assure, items, logs, machine, paths


def make_item(repo, stage="assure", paused_from=None):
    meta = {"id": "0001-a", "title": "A", "stage": stage, "kind": "ui",
            "journeys": "J-001",
            "created": "2026-07-15T10:00:00Z", "updated": "2026-07-15T10:00:00Z"}
    if paused_from:
        meta["paused-from"] = paused_from
        meta["paused-reason"] = "test"
    items.save_item(repo, meta, "# A\n")
    return meta


class AssureVerbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = "2026-07-15T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_waiver_requires_reason(self):
        make_item(self.repo)
        with self.assertRaises(machine.GateError):
            assure.record_waiver(self.repo, "0001-a", "")
        with self.assertRaises(machine.GateError):
            assure.record_waiver(self.repo, "0001-a", "   ")

    def test_waiver_logs_event_with_reason(self):
        make_item(self.repo)
        assure.record_waiver(self.repo, "0001-a", "no browser in this env")
        events = logs.read_events(self.repo, "0001-a")
        waived = [e for e in events if e["event"] == "assure.waived"]
        self.assertEqual(len(waived), 1)
        self.assertEqual(waived[0]["data"]["reason"], "no browser in this env")

    def test_waiver_refused_outside_assure_context(self):
        make_item(self.repo, stage="verify")
        with self.assertRaises(machine.GateError):
            assure.record_waiver(self.repo, "0001-a", "why not")

    def test_waiver_allowed_when_paused_from_assure(self):
        make_item(self.repo, stage="waiting-human", paused_from="assure")
        assure.record_waiver(self.repo, "0001-a", "fixture impossible here")
        self.assertEqual(logs.count_events(self.repo, "0001-a", "assure.waived"), 1)

    def test_confirm_requires_assure_passed(self):
        make_item(self.repo, stage="waiting-human", paused_from="assure")
        with self.assertRaises(machine.GateError):
            assure.record_confirmation(self.repo, "0001-a")
        logs.append_event(self.repo, "0001-a", "assure.passed")
        path = assure.record_confirmation(self.repo, "0001-a")
        self.assertTrue(path.exists())
        self.assertEqual(logs.count_events(self.repo, "0001-a", "assure.confirmed"), 1)

    def test_cli_waive_and_confirm(self):
        from scripts.factory.lib import initrepo
        initrepo.init(self.repo)
        make_item(self.repo)
        code = factory.main(["--repo", str(self.repo), "waive", "0001-a",
                             "--reason", "env blocker"])
        self.assertEqual(code, 0)
        logs.append_event(self.repo, "0001-a", "assure.passed")
        self.assertEqual(factory.main(["--repo", str(self.repo), "confirm", "0001-a"]), 0)
        with patch("sys.stderr", new_callable=StringIO) as err:
            code = factory.main(["--repo", str(self.repo), "waive", "0001-a",
                                 "--reason", "   "])
        self.assertEqual(code, 2)
        self.assertIn("refused", err.getvalue())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_assure_verbs -v`
Expected: ERROR — `scripts.factory.lib.assure` does not exist.

- [ ] **Step 3: Implement**

Create `scripts/factory/lib/assure.py`:

```python
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
```

In `factory.py`: add `assure as assure_mod` to BOTH import lines (the `if __package__` branch and the `else` branch). Add:

```python
def cmd_waive(args):
    try:
        assure_mod.record_waiver(args.repo, args.item, args.reason)
    except (machine.GateError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.item} assurance waived")
    return 0


def cmd_confirm(args):
    try:
        path = assure_mod.record_confirmation(args.repo, args.item)
    except (machine.GateError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(path)
    return 0
```

and subparsers (after `choice`):

```python
    p = sub.add_parser("waive",
                       help="record a human assurance waiver (requires a reason)")
    p.add_argument("item")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_waive)

    p = sub.add_parser("confirm",
                       help="record human confirmation of a passed assurance")
    p.add_argument("item")
    p.set_defaults(func=cmd_confirm)
```

- [ ] **Step 4: Run the full suite**

Run: `python3 -m unittest discover -s tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(engine): human-only factory waive / factory confirm verbs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Escape Register — `lib/escapes.py`, schema, CLI, validate integration

**Files:**
- Create: `scripts/factory/lib/escapes.py`, `schemas/escape.schema.json`
- Modify: `scripts/factory/lib/initrepo.py` (LEDGERS, LEDGER_SCHEMAS, escape line checks + `_check_escape_consistency`), `scripts/factory/factory.py` (cmd_escape, cmd_promote, subparsers; open-escape count in `cmd_status` text mode)
- Test: create `tests/test_escapes.py`; extend `tests/test_initrepo.py`

**Interfaces:**
- Produces: `escapes.file_escape(repo, journey, finding, miss_type, item="", node="", evidence=None) -> entry` (id `esc-NNNN`, status `open`), `escapes.promote(repo, escape_id, via) -> entry` (appends a superseding line with status `promoted` + `promotion`), `escapes.open_escapes(repo) -> list`, `escapes.MISS_TYPES`, `escapes.EscapeError`. Ledger file `.factory/ledgers/escapes.jsonl` created at init. Promotion refs match `^(jdg-\d{4}|test:.+|contract:.+|oracle:.+|decision:.+)$`. CLI: `factory escape <journey> <finding> --miss-type T [--item I] [--node N] [--evidence P ...]` prints the new id; `factory promote <escape-id> --via <ref>`.

- [ ] **Step 1: Create the schema**

`schemas/escape.schema.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "escape",
  "type": "object",
  "required": ["id", "ts", "journey", "finding", "miss_type", "status"],
  "additionalProperties": false,
  "properties": {
    "id": {"type": "string", "pattern": "^esc-[0-9]{4}$"},
    "ts": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"},
    "item": {"type": "string"},
    "journey": {"type": "string", "pattern": "^J-[0-9]{3}$"},
    "node": {"type": "string"},
    "finding": {"type": "string", "minLength": 1},
    "miss_type": {"type": "string",
                  "enum": ["missing-journey", "missing-node", "missing-oracle",
                           "missing-contract-detail", "review-rule-gap"]},
    "evidence": {"type": "array", "items": {"type": "string", "minLength": 1}},
    "status": {"type": "string", "enum": ["open", "promoted"]},
    "promotion": {"type": "string", "minLength": 1}
  }
}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_escapes.py`:

```python
import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory import factory
from scripts.factory.lib import escapes, initrepo


class EscapeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-15T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_file_escape_assigns_sequential_ids(self):
        one = escapes.file_escape(self.repo, "J-001", "no next action visible",
                                  "missing-oracle")
        two = escapes.file_escape(self.repo, "J-002", "dead end after save",
                                  "missing-node")
        self.assertEqual(one["id"], "esc-0001")
        self.assertEqual(two["id"], "esc-0002")
        self.assertEqual([e["id"] for e in escapes.open_escapes(self.repo)],
                         ["esc-0001", "esc-0002"])

    def test_file_escape_rejects_bad_miss_type_and_journey(self):
        with self.assertRaises(escapes.EscapeError):
            escapes.file_escape(self.repo, "J-001", "x", "vibes")
        with self.assertRaises(escapes.EscapeError):
            escapes.file_escape(self.repo, "journey-4", "x", "missing-oracle")

    def test_promotion_closes_escape(self):
        escapes.file_escape(self.repo, "J-001", "confusing", "missing-oracle")
        entry = escapes.promote(self.repo, "esc-0001", "test:tests/test_onboarding.py")
        self.assertEqual(entry["status"], "promoted")
        self.assertEqual(escapes.open_escapes(self.repo), [])

    def test_promotion_ref_validated_and_double_promotion_refused(self):
        escapes.file_escape(self.repo, "J-001", "confusing", "missing-oracle")
        with self.assertRaises(escapes.EscapeError):
            escapes.promote(self.repo, "esc-0001", "fixed it lol")
        escapes.promote(self.repo, "esc-0001", "contract:docs/factory/journeys/contracts/J-001-x.md")
        with self.assertRaises(escapes.EscapeError):
            escapes.promote(self.repo, "esc-0001", "jdg-0001")

    def test_cli_escape_and_promote(self):
        code = factory.main(["--repo", str(self.repo), "escape", "J-001",
                             "user cannot tell what to do next",
                             "--miss-type", "missing-oracle",
                             "--item", "0017-invite-flow", "--node", "N4"])
        self.assertEqual(code, 0)
        self.assertEqual(len(escapes.open_escapes(self.repo)), 1)
        code = factory.main(["--repo", str(self.repo), "promote", "esc-0001",
                             "--via", "jdg-0004"])
        self.assertEqual(code, 0)
        self.assertEqual(escapes.open_escapes(self.repo), [])

    def test_validate_flags_bad_escape_lines(self):
        escapes.file_escape(self.repo, "J-001", "x", "missing-oracle")
        ledger = self.repo / ".factory" / "ledgers" / "escapes.jsonl"
        with ledger.open("a", encoding="utf-8") as f:
            f.write('{"id": "esc-0002", "status": "promoted"}\n')
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("escapes.jsonl" in e for e in errors))
```

In `tests/test_initrepo.py`, add to the init test class (find the test asserting ledgers are created, and extend it or add):

```python
    def test_init_creates_escapes_ledger(self):
        initrepo.init(self.repo)
        self.assertTrue((self.repo / ".factory" / "ledgers" / "escapes.jsonl").exists())
```

(Match the surrounding class's setUp fixture names — read the file first.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_escapes -v`
Expected: ERROR — `scripts.factory.lib.escapes` does not exist.

- [ ] **Step 4: Implement**

Create `scripts/factory/lib/escapes.py`:

```python
"""Append-only Escape Register: what a human still found after assurance.
An escape stays open until promoted into a durable check (contract
amendment via judgement, regression test, oracle, review rule, or brain
decision). Journey-assurance spec."""

import json
import re

from . import logs, paths
from .initrepo import load_schema
from .validate import validate

MISS_TYPES = ("missing-journey", "missing-node", "missing-oracle",
              "missing-contract-detail", "review-rule-gap")
PROMOTION_RE = re.compile(
    r"^(jdg-\d{4}|test:.+|contract:.+|oracle:.+|decision:.+)$")
ID_RE = re.compile(r"^esc-(\d{4})$")


class EscapeError(ValueError):
    pass


def _ledger_path(repo):
    return paths.ledgers_dir(repo) / "escapes.jsonl"


def read_escapes(repo):
    path = _ledger_path(repo)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def current_escapes(repo):
    """Latest entry per id — a promotion line supersedes its open record."""
    out = {}
    for entry in read_escapes(repo):
        if entry.get("id"):
            out[entry["id"]] = entry
    return out


def open_escapes(repo):
    return sorted((e for e in current_escapes(repo).values()
                   if e.get("status") == "open"), key=lambda e: e["id"])


def _append(repo, entry):
    errors = validate(entry, load_schema("escape"), "escape")
    if errors:
        raise EscapeError("; ".join(errors))
    path = _ledger_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def file_escape(repo, journey, finding, miss_type, item="", node="",
                evidence=None):
    if miss_type not in MISS_TYPES:
        raise EscapeError("miss_type must be one of " + ", ".join(MISS_TYPES))
    nums = [int(m.group(1)) for e in read_escapes(repo)
            if (m := ID_RE.match(e.get("id", "")))]
    entry = {"id": f"esc-{max(nums, default=0) + 1:04d}",
             "ts": logs.now_stamp(), "item": item, "journey": journey,
             "node": node, "finding": finding, "miss_type": miss_type,
             "evidence": list(evidence or []), "status": "open"}
    return _append(repo, entry)


def promote(repo, escape_id, via):
    if not PROMOTION_RE.match(via or ""):
        raise EscapeError(
            "promotion --via must be jdg-NNNN, test:<path>, contract:<path>, "
            "oracle:<ref>, or decision:<ref>")
    current = current_escapes(repo)
    if escape_id not in current:
        raise EscapeError(f"no such escape: {escape_id}")
    if current[escape_id].get("status") == "promoted":
        raise EscapeError(f"{escape_id} is already promoted")
    entry = dict(current[escape_id])
    entry["ts"] = logs.now_stamp()
    entry["status"] = "promoted"
    entry["promotion"] = via
    return _append(repo, entry)
```

`scripts/factory/lib/initrepo.py`:
- `LEDGERS = ("bids", "judgements", "reputation", "escapes")`
- `LEDGER_SCHEMAS = {..., "escapes": "escape"}`
- In the ledger validation loop, after a schema-valid entry is appended to `parsed`, add escape-specific conditional checks:

```python
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
```

- The `_check_ledger_consistency` duplicate-id loop iterates `("bids", "judgements")` — leave it. Add an escapes sequence rule inside `_check_ledger_consistency` (it receives `entries`, which now includes `"escapes"`):

```python
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
```

`scripts/factory/factory.py`: import `escapes as escapes_mod` in both import branches; add:

```python
def cmd_escape(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        entry = escapes_mod.file_escape(
            args.repo, args.journey, args.finding, args.miss_type,
            item=args.item or "", node=args.node or "",
            evidence=args.evidence or [])
    except escapes_mod.EscapeError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(entry["id"])
    return 0


def cmd_promote(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        escapes_mod.promote(args.repo, args.escape, args.via)
    except escapes_mod.EscapeError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.escape} promoted -> {args.via}")
    return 0
```

subparsers:

```python
    p = sub.add_parser("escape", help="file a post-assurance human discovery")
    p.add_argument("journey")
    p.add_argument("finding")
    p.add_argument("--miss-type", required=True, dest="miss_type",
                   choices=list(escapes_mod.MISS_TYPES))
    p.add_argument("--item", default="")
    p.add_argument("--node", default="")
    p.add_argument("--evidence", action="append")
    p.set_defaults(func=cmd_escape)

    p = sub.add_parser("promote",
                       help="close an escape by naming its durable promotion")
    p.add_argument("escape")
    p.add_argument("--via", required=True)
    p.set_defaults(func=cmd_promote)
```

In `cmd_status`, in the non-JSON branch after the corrupt-lines notice, add:

```python
        open_esc = escapes_mod.open_escapes(args.repo)
        if open_esc:
            print(f"open escapes: {len(open_esc)} "
                  "(promote each into a contract/test/oracle/rule/decision)")
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests`
Expected: PASS. Note: adding `escapes` to LEDGERS means `initrepo.init` now creates the file — any test asserting the exact created-paths list from `init()` must gain `.factory/ledgers/escapes.jsonl`.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(engine): escape register — factory escape / factory promote + ledger validation

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Tiers `assure` profile, config schema, packet artifacts + respond footer, validate_tree assurance/graph checks

**Files:**
- Modify: `scripts/factory/lib/tiers.py`, `schemas/config.schema.json`, `scripts/factory/lib/packet.py`, `scripts/factory/lib/initrepo.py` (validate_tree item-artifact + journeys graph checks)
- Create: `schemas/journey-graph.schema.json`
- Test: `tests/test_tiers.py`, `tests/test_packet.py`, `tests/test_initrepo.py`, `tests/test_doctor.py`

**Interfaces:**
- Produces: `tiers.profile(repo, tier)` returns `{"research", "review", "assure"}` with defaults epic=`full`, feature=`affected`, bug=`node`; config accepts `tiers.<tier>.assure` and `"assure"` in `gates`; packet lists `assurance/impact.json` + `assurance/verdicts.json` and names `factory confirm` / `factory waive` in Respond; `validate_tree` schema-validates `assurance/impact.json`, `assurance/verdicts.json` per item and `docs/factory/journeys/graph.json` when present.

- [ ] **Step 1: Write the failing tests**

`tests/test_tiers.py` (match existing class style):

```python
    def test_assure_defaults_per_tier(self):
        self.assertEqual(tiers.profile(self.repo, "epic")["assure"], "full")
        self.assertEqual(tiers.profile(self.repo, "feature")["assure"], "affected")
        self.assertEqual(tiers.profile(self.repo, "bug")["assure"], "node")

    def test_assure_config_override(self):
        cfg = {"version": 1, "merge": "auto", "gates": ["design"],
               "tiers": {"bug": {"assure": "affected"}}}
        paths.config_path(self.repo).parent.mkdir(parents=True, exist_ok=True)
        paths.config_path(self.repo).write_text(json.dumps(cfg), encoding="utf-8")
        self.assertEqual(tiers.profile(self.repo, "bug")["assure"], "affected")
```

`tests/test_packet.py`:

```python
    def test_packet_lists_assurance_artifacts_and_verbs(self):
        text = packet.render_packet(self.repo, self.item_id)
        self.assertIn("assurance/verdicts.json", text)
        self.assertIn("assurance/impact.json", text)
        self.assertIn("factory confirm", text)
        self.assertIn("factory waive", text)
```

(adapt `self.item_id`/fixtures to the file's existing setUp.)

`tests/test_initrepo.py`:

```python
    def test_validate_flags_bad_assurance_artifacts(self):
        initrepo.init(self.repo)
        meta = {"id": "0001-a", "title": "A", "stage": "assure", "kind": "ui",
                "journeys": "J-001",
                "created": "2026-07-15T10:00:00Z", "updated": "2026-07-15T10:00:00Z"}
        items.save_item(self.repo, meta, "# A\n")
        adir = self.repo / ".factory" / "items" / "0001-a" / "assurance"
        adir.mkdir(parents=True)
        (adir / "verdicts.json").write_text('{"nope": true}', encoding="utf-8")
        (adir / "impact.json").write_text('not json', encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("verdicts.json" in e for e in errors))
        self.assertTrue(any("impact.json" in e for e in errors))

    def test_validate_flags_bad_journey_graph(self):
        initrepo.init(self.repo)
        graph = self.repo / "docs" / "factory" / "journeys" / "graph.json"
        graph.parent.mkdir(parents=True, exist_ok=True)
        graph.write_text('{"journeys": [{"id": "banana"}]}', encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("graph.json" in e for e in errors))
```

`tests/test_doctor.py`:

```python
    def test_doctor_tiers_include_assure(self):
        report = doctor.report(self.repo)
        self.assertEqual(report["tiers"]["bug"]["assure"], "node")
```

(adapt to the file's fixtures; `doctor.report` may need an initialized repo.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_tiers tests.test_packet tests.test_initrepo tests.test_doctor -v`
Expected: new tests FAIL.

- [ ] **Step 3: Implement**

`tiers.py`: DEFAULTS become

```python
DEFAULTS = {
    "epic": {"research": "deep", "review": "full", "assure": "full"},
    "feature": {"research": "web", "review": "full", "assure": "affected"},
    "bug": {"research": "off", "review": "light", "assure": "node"},
}
```

and the whitelist line becomes `if k in ("research", "review", "assure")`. Extend the module docstring: `assure: node | affected | full — how much of the journey surface the assure stage walks (changed node only / all affected journeys / affected plus core)`.

`schemas/config.schema.json`: `gates` items enum becomes `["design", "spec", "merge", "assure"]`; each tier block (`epic`, `feature`, `bug`) gains:

```json
            "assure": {"type": "string", "enum": ["node", "affected", "full"]}
```

`packet.py`: `ARTIFACTS` becomes:

```python
ARTIFACTS = ("triage.md", "spec.md", "plan.md", "design/choice.md",
             "reviews/synthesis.md", "assurance/impact.json",
             "assurance/verdicts.json")
```

and the Respond block becomes:

```python
    lines += ["", "## Respond",
              "Reply in session, or use the factory CLI to record your",
              "decision (design pause: `factory choice <id> <option>`;",
              "assurance pause: `factory confirm <id>` or",
              '`factory waive <id> --reason "..."`),',
              "then run `/factory:run` to resume.", ""]
```

Create `schemas/journey-graph.schema.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "journey-graph",
  "type": "object",
  "required": ["version", "journeys"],
  "additionalProperties": false,
  "properties": {
    "version": {"type": "integer", "enum": [1]},
    "journeys": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "slug", "title", "criticality", "status"],
        "additionalProperties": false,
        "properties": {
          "id": {"type": "string", "pattern": "^J-[0-9]{3}$"},
          "slug": {"type": "string", "pattern": "^[a-z0-9-]+$"},
          "title": {"type": "string", "minLength": 1},
          "persona": {"type": "string"},
          "trigger": {"type": "string"},
          "outcome": {"type": "string"},
          "criticality": {"type": "string", "enum": ["core", "high", "standard"]},
          "status": {"type": "string", "enum": ["inventory", "draft", "approved"]},
          "links": {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "routes": {"type": "array", "items": {"type": "string"}},
              "screens": {"type": "array", "items": {"type": "string"}},
              "apis": {"type": "array", "items": {"type": "string"}},
              "tests": {"type": "array", "items": {"type": "string"}}
            }
          },
          "contract": {"type": "string", "minLength": 1}
        }
      }
    }
  }
}
```

`initrepo.py` `validate_tree`: inside the per-item loop (after the log processing), add:

```python
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
```

and near the end (before the ledger section), add:

```python
    graph_path = paths.docs_root(repo) / "journeys" / "graph.json"
    if graph_path.exists():
        try:
            graph = json.loads(graph_path.read_text(
                encoding="utf-8", errors="replace"))
            errors.extend(validate(graph, load_schema("journey-graph"),
                                   "journeys/graph.json"))
        except json.JSONDecodeError as exc:
            errors.append(f"journeys/graph.json: invalid JSON ({exc})")
```

- [ ] **Step 4: Run the full suite**

Run: `python3 -m unittest discover -s tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(engine): assure tier profile, config gate, packet + validate coverage

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Pipeline walk + e2e + migration coverage

**Files:**
- Modify: `tests/test_pipeline_walk.py`, `tests/test_e2e_cli.py`
- Test: this task IS tests.

**Interfaces:**
- Consumes: everything above.
- Produces: the end-to-end walk exercises verify→assure→ship with real stub evidence; an explicit `journeys: none` path skips assure; a migration test proves a legacy undeclared item parks at the ship gate until waived.

- [ ] **Step 1: Read both test files fully**, then extend:

1. In the main pipeline walk (wherever it advances verify→ship today): declare `journeys` as `J-001` at/before the design-gate step (`factory journeys <id> J-001` in e2e; `items.set_journeys` in the unit walk), ensure the spec.md fixture contains `## Journey impact`, and at the assure step write the stub artifacts exactly as Task 4's `_write_assurance` helper does (copy that helper or import-share via a small local duplicate — tests may not import from each other), log `assure.passed`, then advance assure→ship.
2. Add a second walk (or parametrized branch) with `journeys: none` proving verify→ship directly and that `"assure"` never appears in that item's `stage.advance` events.
3. Add a migration test: build an item dict WITHOUT `journeys` at stage `verify` with `verify.green` logged; `advance` must route it to `assure` (engine forces the stage), the ship gate must refuse, and after `factory waive <id> --reason "pre-assurance item"` (via `assure.record_waiver`) ship must succeed.
4. Keep the existing "tree still validates cleanly after the whole journey" assertion — it now also covers the assurance artifacts.

- [ ] **Step 2: Run the full suite**

Run: `python3 -m unittest discover -s tests`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "test(engine): pipeline walk through assure, none-skip path, migration waiver

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Plan self-review notes (kept for the executor)

- Spec coverage: stage+routing (T1), spec-exit gates (T2), assure gate + rework edge (T3), round-scoped ship gate + artifact validation + confirm-when-gated (T4), waive/confirm verbs (T5), escapes + promotion + validate (T6), tiers/config/packet/graph-schema/validate (T7), e2e + migration (T8). Dispatch resume types, templates, and skills are Plans 2–4 by design.
- The `journeys: none` fixture rule is the migration strategy for the existing suite — legitimate because `none` reproduces exactly the pre-assurance semantics.
- `_check_ledger_consistency` runs only when all ledger files are line-clean — escapes consistency therefore lives there too (same guard as bids/judgements).
