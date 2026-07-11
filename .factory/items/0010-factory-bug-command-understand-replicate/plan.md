# factory:bug Command Implementation Plan

> **For agentic workers:** Executed by the factory-implement skill — one fresh subagent per task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Add a `/factory:bug` intake command + `factory-bug` skill with a replication-first discipline, backed by an engine-level repro gate on an optional `bug` work-item flag.

**Architecture:** Thin intake layer over existing stages. Three surfaces: (1) an optional `bug: boolean` frontmatter field parsed/rendered by `items.py` and declared in the work-item schema; (2) a `_gate_plan` conditional in `machine.py` requiring `repro.md` + a `repro.confirmed` event for bug items (file+event dual-check, same pattern as existing gates); (3) markdown deliverables — `commands/bug.md`, `skills/factory-bug/SKILL.md`, and a one-line seeded-criteria carry rule in `skills/factory-spec/SKILL.md`. No new stages, no changes to factory-verify.

**Tech Stack:** Python 3 stdlib only (engine + tests via `unittest`); markdown plugin surfaces.

## Global Constraints

- Engine is Python 3 stdlib only; zero third-party dependencies (brain constraints.md).
- Deterministic writes in items.py: fixed field order, LF endings, trailing newline.
- `kind` enum (`ui|backend|mixed`) must NOT grow a new value; `bug` is an orthogonal optional boolean, absent = falsy (judgement on bid-0040).
- All tests run via `python3 -m unittest discover -s tests` from the repo root and the full suite must stay green (322 tests before this item).
- `skills/factory-verify/` must not be modified (spec AC 10).
- In new skill/command markdown, never write a literal `references/<name>.md` string unless that file exists under `skills/capabilities/references/` — `tests/test_plugin_coherence.py::test_every_reference_doc_link_resolves` fails otherwise. Same for `agents/<name>.md` strings.
- Commit each task on the item's implementation branch (factory-implement owns branch creation: `factory/0010-factory-bug-command-understand-replicate`).

---

### Task 1: `bug` boolean frontmatter field (items.py + work-item schema)

**Files:**
- Modify: `scripts/factory/lib/items.py:12-18` (FIELD_ORDER, new BOOL_FIELDS), `scripts/factory/lib/items.py:25-55` (parse_item), `scripts/factory/lib/items.py:58-74` (render_item)
- Modify: `schemas/work-item.schema.json`
- Test: `tests/test_items.py`, `tests/test_validate.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `items.parse_item` returns `meta["bug"]` as a Python `bool` when the frontmatter carries `bug: true|false` (key absent otherwise); `items.render_item` renders it back as lowercase `true`/`false`; `items.BOOL_FIELDS == ("bug",)`. Task 2 relies on `meta.get("bug")` being a real bool.

Satisfies spec acceptance criteria **6** and **7**.

- [x] **Step 1: Write the failing tests**

Append to the `TestParseRender` class in `tests/test_items.py` (after `test_render_rejects_untrimmed_value`, keeping class indentation):

```python
    def test_bug_true_parsed_as_bool(self):
        text = VALID.replace("kind: ui", "kind: ui\nbug: true")
        meta, _ = items.parse_item(text)
        self.assertIs(meta["bug"], True)

    def test_bug_false_parsed_as_bool(self):
        text = VALID.replace("kind: ui", "kind: ui\nbug: false")
        meta, _ = items.parse_item(text)
        self.assertIs(meta["bug"], False)

    def test_bug_non_boolean_value_rejected(self):
        for bad in ("yes", "True", "1", ""):
            text = VALID.replace("kind: ui", f"kind: ui\nbug: {bad}")
            with self.assertRaises(items.ItemError):
                items.parse_item(text)

    def test_bug_render_parse_roundtrip_lowercase(self):
        text = VALID.replace("kind: ui", "kind: ui\nbug: true")
        meta, body = items.parse_item(text)
        out = items.render_item(meta, body)
        self.assertIn("\nbug: true\n", out)
        again, _ = items.parse_item(out)
        self.assertIs(again["bug"], True)

    def test_item_without_bug_field_has_no_bug_key(self):
        meta, _ = items.parse_item(VALID)
        self.assertNotIn("bug", meta)
```

Append to `tests/test_validate.py` in the class that contains `test_good_item` (same class, after `test_priority_must_be_positive_int`):

```python
    def test_bug_field_optional_boolean(self):
        schema = load("work-item")
        self.assertEqual(validate(dict(GOOD_ITEM, bug=True), schema), [])
        self.assertEqual(validate(GOOD_ITEM, schema), [])
        self.assertTrue(validate(dict(GOOD_ITEM, bug="yes"), schema))
```

- [x] **Step 2: Run the new tests to verify they fail**

Run: `python3 -m unittest tests.test_items tests.test_validate -v 2>&1 | tail -20`
Expected: FAIL — `test_bug_true_parsed_as_bool` etc. raise `ItemError: unknown field: bug`; `test_bug_field_optional_boolean` reports a validation error for the unknown `bug` property.

- [x] **Step 3: Implement**

In `schemas/work-item.schema.json`, add one property after the `"kind"` line (line 15):

```json
    "kind": {"type": "string", "enum": ["ui", "backend", "mixed"]},
    "bug": {"type": "boolean"},
```

In `scripts/factory/lib/items.py`, replace lines 12–18 (the constants) with:

```python
FIELD_ORDER = (
    "id", "title", "stage", "kind", "bug", "priority",
    "created", "updated", "paused-from", "paused-reason",
)
REQUIRED_FIELDS = ("id", "title", "stage", "kind", "created", "updated")
INT_FIELDS = ("priority",)
BOOL_FIELDS = ("bug",)
KINDS = ("ui", "backend", "mixed")
```

In `parse_item`, insert a boolean coercion branch immediately after the existing `INT_FIELDS` branch (after the `raise ItemError(f"{key} must be an integer, got {value!r}")` line):

```python
        if key in BOOL_FIELDS:
            if value == "true":
                value = True
            elif value == "false":
                value = False
            else:
                raise ItemError(f"{key} must be true or false, got {value!r}")
```

In `render_item`, add a module-level helper above `render_item` and use it for both the validation pass and the output line, so a Python `True` renders as `true` (not `True`) and round-trips:

```python
def _render_value(value):
    return ("true" if value else "false") if isinstance(value, bool) else str(value)
```

Then inside `render_item` change `text = str(value)` to `text = _render_value(value)`, and change the output line `out.append(f"{key}: {meta[key]}")` to `out.append(f"{key}: {_render_value(meta[key])}")`.

- [x] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_items tests.test_validate -v 2>&1 | tail -5`
Expected: `OK` (all tests in both modules pass, including the five new items tests and one new validate test).

- [x] **Step 5: Run the full suite (regression) and commit**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`, test count ≥ 328.

```bash
git add scripts/factory/lib/items.py schemas/work-item.schema.json tests/test_items.py tests/test_validate.py
git commit -m "feat(0010): optional bug boolean on work items - schema, parse, lowercase render"
```

---

### Task 2: `_gate_plan` repro gate for bug items (machine.py)

**Files:**
- Modify: `scripts/factory/lib/machine.py:76-79` (`_gate_plan`)
- Test: `tests/test_machine.py` (helper at lines 11–19, `TestGates` class)

**Interfaces:**
- Consumes: `meta.get("bug")` — the Python bool from Task 1 (absent key = falsy).
- Produces: `machine.advance(repo, item_id, "plan")` raises `machine.GateError` for a `bug: true` item unless BOTH `items/<id>/repro.md` is non-empty AND at least one `repro.confirmed` event is logged. Non-bug items are unaffected. Task 3's skill instructions depend on exactly these gate semantics.

Satisfies spec acceptance criteria **8** (and contributes to **9**).

- [x] **Step 1: Write the failing tests**

In `tests/test_machine.py`, extend the `make_item` helper (lines 11–19) with a `bug` parameter — replace the function with:

```python
def make_item(repo, kind="ui", stage="idea", priority=None, bug=False):
    meta = {
        "id": "0001-thing", "title": "Thing", "stage": stage, "kind": kind,
        "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z",
    }
    if priority:
        meta["priority"] = priority
    if bug:
        meta["bug"] = True
    items.save_item(repo, meta, "# Thing\n")
    return meta
```

Add to the `TestGates` class, directly after `test_plan_requires_design_choice_for_ui` (line 126):

```python
    def test_plan_requires_repro_for_bug(self):
        make_item(self.repo, kind="backend", stage="spec", priority=1, bug=True)
        write(self.repo, "spec.md")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")
        write(self.repo, "repro.md", "# Repro\n## Command\nfoo\n")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")
        logs.append_event(self.repo, "0001-thing", "repro.confirmed",
                          {"command": "foo", "exit": 1, "mode": "command"})
        self.assertEqual(machine.advance(self.repo, "0001-thing", "plan")["stage"], "plan")

    def test_plan_requires_repro_event_even_with_file(self):
        make_item(self.repo, kind="backend", stage="spec", priority=1, bug=True)
        write(self.repo, "spec.md")
        write(self.repo, "repro.md", "")  # empty file also refused
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")

    def test_plan_without_bug_flag_needs_no_repro(self):
        make_item(self.repo, kind="backend", stage="spec", priority=1)
        write(self.repo, "spec.md")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "plan")["stage"], "plan")

    def test_plan_bug_ui_item_needs_both_choice_and_repro(self):
        make_item(self.repo, kind="ui", stage="design", priority=1, bug=True)
        write(self.repo, "spec.md")
        write(self.repo, "design/choice.md", "choice: option-b\n")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, "0001-thing", "plan")
        write(self.repo, "repro.md", "# Repro\n")
        logs.append_event(self.repo, "0001-thing", "repro.confirmed")
        self.assertEqual(machine.advance(self.repo, "0001-thing", "plan")["stage"], "plan")
```

- [x] **Step 2: Run the new tests to verify they fail**

Run: `python3 -m unittest tests.test_machine.TestGates -v 2>&1 | tail -12`
Expected: `test_plan_requires_repro_for_bug`, `test_plan_requires_repro_event_even_with_file`, and `test_plan_bug_ui_item_needs_both_choice_and_repro` FAIL (the advance succeeds where a `GateError` is expected); `test_plan_without_bug_flag_needs_no_repro` passes (current behavior).

- [x] **Step 3: Implement the gate**

In `scripts/factory/lib/machine.py`, replace `_gate_plan` (lines 76–79) with:

```python
def _gate_plan(repo, meta):
    _require_file(repo, meta, "spec.md", "spec required before planning")
    if meta["kind"] in ("ui", "mixed"):
        _require_file(repo, meta, "design/choice.md", "recorded design choice required")
    if meta.get("bug"):
        _require_file(repo, meta, "repro.md",
                      "confirmed repro required before planning a bug fix")
        _require_event(repo, meta, "repro.confirmed",
                       "replication must be confirmed before planning a bug fix")
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_machine -v 2>&1 | tail -5`
Expected: `OK` — all machine tests pass including the four new ones.

- [x] **Step 5: Run the full suite (regression) and commit**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`.

```bash
git add scripts/factory/lib/machine.py tests/test_machine.py
git commit -m "feat(0010): _gate_plan requires repro.md + repro.confirmed for bug items"
```

---

### Task 3: `commands/bug.md` + `skills/factory-bug/SKILL.md`

**Files:**
- Create: `commands/bug.md`
- Create: `skills/factory-bug/SKILL.md`
- Test: `tests/test_plugin_coherence.py` (existing tests must stay green — no new test code)

**Interfaces:**
- Consumes: the Task 2 gate semantics (`repro.md` + `repro.confirmed` before plan) and the Task 1 `bug: true` frontmatter convention.
- Produces: the ninth command and the intake skill; Task 4's carry rule refers to the seeded-criteria section title defined here (exact string: `## Acceptance criteria (seeded at bug intake — carry into spec.md verbatim)`).

Satisfies spec acceptance criteria **1**, **2**, **3**, **4**, **11**, **12** (and the SKILL.md half of **5**).

- [ ] **Step 1: Create `commands/bug.md`** with exactly this content:

```markdown
---
description: Report a bug to the factory ($ARGUMENTS = the bug report, in your own words)
---
Pass $ARGUMENTS verbatim to the factory-bug skill as the bug report and follow
it exactly; it owns understanding, replication, and filing the bug work item.
```

- [ ] **Step 2: Create `skills/factory-bug/SKILL.md`** with exactly this content:

````markdown
---
name: factory-bug
description: Use when a human reports a bug - understand it, replicate it BEFORE any fix work, and file a bug work item the existing pipeline carries to a proven fix
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

## Contract

- **Input:** the human's bug report, verbatim (from /factory:bug or direct invocation). The human is present — intake runs synchronously in this session.
- **Artifacts produced:** a new work item with `bug: true` frontmatter, `items/<id>/repro.md`, a `repro.confirmed` event (replication success path only), `items/<id>/triage.md`, and the two seeded acceptance criteria in the item body.
- **Exit — replicated:** item advanced to `spec`; /factory:run carries it from there. The engine's plan gate independently requires `repro.md` + `repro.confirmed` for bug items — this skill cannot bypass it.
- **Exit — cannot replicate or still ambiguous:** item paused `waiting-human` with a packet; never proceed to fix an unreplicated bug.

The core promise: **we never claim a bug is fixed when it isn't.** The recorded repro is the analogue of TDD's red test — it exists before any fix work, and verify re-runs it before anything ships.

## Steps

1. **Understand.** Restate the bug in one or two sentences: what the user did, what happened, what they expected. If the report is ambiguous on any point needed to attempt replication, ask **at most one round** of clarification questions now, synchronously (the cap is skill policy, never engine state). If ambiguity survives that round — or no answer is available (non-interactive invocation) — do not guess: file the item (step 3, skipping replication), then `factory advance ITEM waiting-human --reason "bug: needs clarification - <question>"`, `factory packet ITEM`, and stop.

2. **Decide kind.** `ui` or `mixed` **only when the fix changes the intended design**; restore-to-spec visual bugs stay `backend` — a padding nit must not become a human design-gate stop. `kind` stays the design-routing axis; bug-ness is the separate `bug` flag.

3. **File the item.** `factory add "<short bug title>" --kind <kind>`. Then edit `items/<id>/item.md` directly: set the body to the verbatim bug report (plus any clarification answers, marked as such), and add `bug: true` to the frontmatter — a plain frontmatter field, not CLI-settable, same convention as triage's `kind` correction.

4. **Replicate — before any fix work.** Actually run the failing path. **A prose description is not a repro.**
   - On success, write `items/<id>/repro.md`:

     ```markdown
     # Repro — <item-id>
     ## Command
     (fenced code block: the exact command; for human-confirmed visual repros, exact observation steps)
     ## Expected
     One line: the correct behavior.
     ## Observed (verbatim)
     (fenced code block: verbatim failing output, trimmed with elisions marked)
     ## Environment
     Commit SHA, date, anything needed to re-run.
     ```

   - Then log the evidence event: `factory log ITEM repro.confirmed --data '{"command": "<exact command>", "exit": <code>, "mode": "command"}'`.
   - Visual bugs with no runnable command: the repro is a human-confirmable note — exact steps to observe the failure — confirmed by the present human now, logged with `"mode": "human-confirmed"` and no `exit` key. The design gate still applies via kind as usual.

5. **Cannot replicate → hard stop.** Record every attempted command and its actual output in `items/<id>/repro.md` under an `## Attempts (unconfirmed)` heading. Do **not** log `repro.confirmed`. Then `factory advance ITEM waiting-human --reason "bug: cannot replicate - <what was tried>"` and `factory packet ITEM`. Append a house-style section to the packet: one-sentence recommendation, capped evidence bullets (what was run, verbatim output), exactly one copy-pasteable next action. This is the cheapest failure point — it halts before any plan/implement spend.

6. **Seed the mandatory acceptance criteria.** Append to the item body a section titled exactly `## Acceptance criteria (seeded at bug intake — carry into spec.md verbatim)` containing:
   1. The recorded repro in `items/<id>/repro.md` now passes: running its `## Command` produces the `## Expected` behavior, and the `## Observed` failure no longer occurs.
   2. A regression test exists in the project's test suite that failed on pre-fix code (red-run evidence from the implement stage's TDD discipline).

   These two criteria are non-optional. The spec stage carries them verbatim into `spec.md`, where the verify stage's Iron Law enforces them with fresh evidence.

7. **Write the intake triage record and enter the pipeline.** Write `items/<id>/triage.md`: decision (build — confirmed replicated bug), the kind rationale from step 2, and priority. Set priority with `factory priority ITEM N` — ask the human while they are present; default 1 (front of queue) if they don't say. Then `factory advance ITEM triage` and `factory advance ITEM spec`. No council runs at intake; the council still reviews the fix at the review stage. From spec onward this is ordinary pipeline work — implement branches per item with TDD, ui/mixed items pass the design gate, ship merges per policy.

8. **Spend.** If replication dispatches subagents, log spend per the dispatch convention: `factory log ITEM spend --data '{"provenance":"measured","stage":"triage","source":"factory-bug","dispatches":<n>,"tokens":{"total":<n>}}'` with harness-reported counts, or `"provenance":"proxy"` and no `tokens` key when the harness reports none. Never estimate; main-loop burn is never logged as measured.

## Sequencing note

The clarification / cannot-replicate `waiting-human` stops are natural consumers of item 0005's generalized interactive decisions when it unblocks; this skill builds no new interactive page — plain house-style markdown packets only.
````

- [ ] **Step 3: Run the coherence tests**

Run: `python3 -m unittest tests.test_plugin_coherence -v 2>&1 | tail -12`
Expected: `OK` — `test_every_command_names_a_real_skill_or_cli` sees `factory-bug` in `commands/bug.md`; no `agents/` or capabilities-`references/` strings were introduced, so those checks stay green.

- [ ] **Step 4: Commit**

```bash
git add commands/bug.md skills/factory-bug/SKILL.md
git commit -m "feat(0010): /factory:bug command + factory-bug intake skill (replicate-first)"
```

---

### Task 4: Seeded-criteria carry rule in factory-spec + full verification pass

**Files:**
- Modify: `skills/factory-spec/SKILL.md` (the `## Spec structure` section)
- Test: full suite + live `factory validate` (no new test code)

**Interfaces:**
- Consumes: the exact section title Task 3 defined: `## Acceptance criteria (seeded at bug intake — carry into spec.md verbatim)`.
- Produces: the carry rule the spec stage obeys for every future bug item.

Satisfies spec acceptance criteria **5** (spec-side half), **6**, **9**, **10**.

- [ ] **Step 1: Edit `skills/factory-spec/SKILL.md`**

In the `## Spec structure` section, the `## Acceptance criteria` bullet currently reads:

```markdown
- `## Acceptance criteria` — a numbered list, each criterion testable (a later stage can check it mechanically or by inspection, not by opinion).
```

Replace it with:

```markdown
- `## Acceptance criteria` — a numbered list, each criterion testable (a later stage can check it mechanically or by inspection, not by opinion). If the item body contains a section titled `## Acceptance criteria (seeded at bug intake — carry into spec.md verbatim)`, its criteria MUST appear verbatim in this list — they may be joined by further criteria, never replaced or reworded.
```

- [ ] **Step 2: Verify factory-verify is untouched**

Run: `git status --porcelain skills/factory-verify/`
Expected: no output (spec AC 10 — zero modifications under `skills/factory-verify/`).

- [ ] **Step 3: Run the full suite**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`, total ≥ 331 tests (322 baseline + ~9 new), zero failures/errors.

- [ ] **Step 4: Live validate on the real tree (zero migration proof)**

Run: `python3 scripts/factory/factory.py --repo . validate && echo VALIDATE-OK`
Expected: `VALIDATE-OK` with no errors — existing items (none carrying `bug`) validate unchanged against the extended schema.

- [ ] **Step 5: Commit**

```bash
git add skills/factory-spec/SKILL.md
git commit -m "feat(0010): factory-spec carries bug-intake seeded acceptance criteria verbatim"
```

---

## Self-review record

- **Spec coverage:** AC 1 → Task 3 step 1; AC 2–4 → Task 3 step 2 (skill steps 1–7); AC 5 → Task 3 step 2 (skill step 6) + Task 4 step 1; AC 6 → Task 1 (schema) + Task 4 step 4 (live validate); AC 7 → Task 1; AC 8 → Task 2; AC 9 → Task 4 step 3; AC 10 → Task 4 step 2; AC 11 → Task 3 step 2 (skill step 8); AC 12 → Task 3 step 2 (sequencing note; also spec Behavior §5).
- **Placeholder scan:** every code/markdown step carries full content; no TBD/"appropriate handling" phrasing.
- **Type consistency:** `bug` is a Python `bool` end-to-end (`parse_item` coercion → `meta.get("bug")` in `_gate_plan` → lowercase render); event name `repro.confirmed` and section title strings match exactly across Tasks 2, 3, and 4.
