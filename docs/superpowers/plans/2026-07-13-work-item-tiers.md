# Work-Item Materiality Tiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a materiality **tier** (`epic | feature | bug`) to work items so the expensive layers scale to how much a change is worth — the focus group runs only for material epics, a bug gets a light (correctness-only) review, and features keep today's behavior — set by an agent at triage and tunable via config presets.

**Architecture:** A new `tier` frontmatter field (orthogonal to `kind`), a `tiers` config block mapping each tier to a `{research, review}` profile (with defaults, read by `lib/tiers.py`), a `factory tier` CLI setter (mirroring `factory priority`), a `tiers` readout in `factory doctor --json`, and skill wiring: triage/bug/roadmap **set** the tier; review/council-review/research **consume** it (bug → inward seats only; focus group → requires `tier: epic`). Additive and back-compat: an absent tier reads as `feature`, which maps to today's full review + `web` research.

**Tech Stack:** Python 3.11 standard library only. Tests: `unittest`.

**Design source:** the 2026-07-13 product discussion (Anthony Eskinazi + Stephen Coulson): "guard rails around the focus group — you only need it for material features"; three levels — epics/UI-heavy, features, bugs. Refined here: tier is a **materiality** axis kept orthogonal to `kind` (which already drives the design gate). The bug reproduce→regression→fix→validate loop **already exists** (`factory-bug` skill + `machine.py` repro gates) and is not rebuilt; `tier: bug` formalizes it as tier 3 and routes it to the light review. The focus group **already** only fires at `research.depth: deep`; this adds the missing per-item materiality guard.

## Global Constraints

- **Python 3.11, standard library only.** Imports limited to `argparse json os re shutil subprocess pathlib datetime` or internal `scripts.factory.lib.*`.
- **Test runner:** `python3 -m unittest discover -s tests -v` from repo root; `unittest.TestCase` + `tempfile.TemporaryDirectory()`. Run the FULL suite after every task.
- **Schemas** in `schemas/<name>.schema.json`, loaded via `initrepo.load_schema`, validated by the DRAFT-07 SUBSET validator: only `type, enum, required, properties, additionalProperties:false, items, pattern, minLength, minimum`. No `maximum`/`maxLength`/`$ref`/`oneOf`/`anyOf`/null.
- **`config.schema.json` top-level `additionalProperties:false`** — a new `tiers` key MUST be added to its `properties`.
- **Item frontmatter** is a strict scalar subset: `key: value` lines. `tier` is a plain **string** field (like `kind`) — enum-validated by the schema, not by `items.parse_item`. It goes in `FIELD_ORDER` so it round-trips.
- **Event shape** `{"event","ts","data?}` via `logs.append_event`. `tier.set` is a free-form audit event (like `priority.set`); no gate reads it.
- **CLI exit codes:** 0 ok, 1 usage/internal, 2 gate/precondition refusal. `cmd_*` return an int, errors to stderr.
- **Back-compat:** absent `tier` ⇒ `feature`. Existing items and tests (which never set `tier`) must be unaffected. `DEFAULT_CONFIG` is NOT modified (the `tiers` block is optional, defaults live in `lib/tiers.py`).
- **Do NOT stage `README.md`** (pre-existing unstaged mod). Each commit stages only its named files.
- **NEVER run tree-wide git commands** (`git add -A`/`.`, `git restore .`, `git checkout .`/`-- .`, `git stash`, `git clean`, `git reset --hard`) — they would revert unrelated working-tree changes. Only `git add <exact files>` + `git commit <exact files>`.

## File Structure

- **Modify** `scripts/factory/lib/items.py` — add `tier` to `FIELD_ORDER`; `TIERS`, `DEFAULT_TIER`, `item_tier(meta)`, `set_tier(repo, id, tier)`.
- **Modify** `schemas/work-item.schema.json` — add the optional `tier` enum.
- **Create** `scripts/factory/lib/tiers.py` — `DEFAULTS` + `profile(repo, tier)` (config `tiers` over defaults).
- **Modify** `schemas/config.schema.json` — add the optional `tiers` block.
- **Modify** `scripts/factory/factory.py` — `cmd_tier`, `tier` subparser, `add --tier`, tier in `status`.
- **Modify** `scripts/factory/lib/doctor.py` — add a resolved `tiers` key to the readout.
- **Modify** skills: `factory-triage`, `factory-bug`, `factory-roadmap` (set); `factory-review`, `council-review`, `factory-research` (consume).
- **Modify** `tests/`: `test_items.py`, `test_cli*` , `test_doctor.py`, `test_plugin_coherence.py`; **Create** `tests/test_tiers.py`.

---

### Task 1: `tier` frontmatter field

**Files:**
- Modify: `scripts/factory/lib/items.py`
- Modify: `schemas/work-item.schema.json`
- Test: `tests/test_items.py`

**Interfaces:**
- Produces: `items.TIERS = ("epic","feature","bug")`, `items.DEFAULT_TIER = "feature"`, `items.item_tier(meta) -> str` (meta's tier or the default), `items.set_tier(repo, item_id, tier) -> meta` (validates against TIERS, writes frontmatter, logs `tier.set`). `"tier"` added to `FIELD_ORDER`.

- [ ] **Step 1: Write the failing test**

First open `tests/test_items.py` and match its existing style (it constructs metas and round-trips via `parse_item`/`render_item`, and uses a temp repo for `set_*`). Append these tests (adapt the repo fixture to the file's existing pattern — many item tests build a meta dict inline):

```python
class TierTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        meta = {"id": "0001-thing", "title": "Thing", "stage": "triage",
                "kind": "backend", "created": "2026-07-03T00:00:00Z",
                "updated": "2026-07-03T00:00:00Z"}
        items.save_item(self.repo, meta, "")

    def tearDown(self):
        self.tmp.cleanup()

    def test_item_tier_defaults_to_feature(self):
        meta, _ = items.load_item(self.repo, "0001-thing")
        self.assertEqual(items.item_tier(meta), "feature")

    def test_tier_round_trips_in_frontmatter(self):
        meta, body = items.load_item(self.repo, "0001-thing")
        meta["tier"] = "epic"
        items.save_item(self.repo, meta, body)
        reloaded, _ = items.load_item(self.repo, "0001-thing")
        self.assertEqual(items.item_tier(reloaded), "epic")

    def test_set_tier_validates_and_logs(self):
        items.set_tier(self.repo, "0001-thing", "bug")
        meta, _ = items.load_item(self.repo, "0001-thing")
        self.assertEqual(meta["tier"], "bug")
        events = [e["event"] for e in logs.read_events(self.repo, "0001-thing")]
        self.assertIn("tier.set", events)

    def test_set_tier_rejects_bad_value(self):
        with self.assertRaises(items.ItemError):
            items.set_tier(self.repo, "0001-thing", "mega")

    def test_bad_tier_enum_rejected_by_validate(self):
        meta, body = items.load_item(self.repo, "0001-thing")
        meta["tier"] = "mega"
        items.save_item(self.repo, meta, body)
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("tier" in e for e in errors), errors)
```

Ensure the test file imports `tempfile`, `Path`, and `initrepo`, `items`, `logs` (add to the existing import line if missing).

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_items.TierTest -v`
Expected: FAIL — `AttributeError: module 'scripts.factory.lib.items' has no attribute 'item_tier'`.

- [ ] **Step 3: Add `tier` to `items.py`**

In `scripts/factory/lib/items.py`, add `"tier"` to `FIELD_ORDER` right after `"kind"`:

```python
FIELD_ORDER = (
    "id", "title", "stage", "kind", "tier", "bug", "priority",
    "created", "updated", "paused-from", "paused-reason",
)
```

Add the constants near `KINDS`:

```python
TIERS = ("epic", "feature", "bug")
DEFAULT_TIER = "feature"
```

Add these functions (e.g. after `set_priority`):

```python
def item_tier(meta):
    """The item's materiality tier, defaulting to feature when unset.
    Orthogonal to kind (ui/backend/mixed) — tier scales research/review
    depth; kind drives the design gate."""
    return meta.get("tier") or DEFAULT_TIER


def set_tier(repo, item_id, tier):
    if tier not in TIERS:
        raise ItemError("tier must be one of " + ", ".join(TIERS))
    meta, body = load_item(repo, item_id)
    meta["tier"] = tier
    meta["updated"] = logs.now_stamp()
    save_item(repo, meta, body)
    logs.append_event(repo, item_id, "tier.set", {"tier": tier})
    return meta
```

- [ ] **Step 4: Add the schema enum**

In `schemas/work-item.schema.json`, add inside `"properties"` (after `"kind"`):

```json
    "tier": {"type": "string", "enum": ["epic", "feature", "bug"]},
```

- [ ] **Step 5: Run the test + full suite**

Run: `python3 -m unittest tests.test_items.TierTest -v` → PASS (5 tests).
Run: `python3 -m unittest discover -s tests -v` → all green (existing item tests unaffected — none set `tier`, and `item_tier` defaults).

- [ ] **Step 6: Commit**

```bash
git add scripts/factory/lib/items.py schemas/work-item.schema.json tests/test_items.py
git commit -m "feat(tiers): tier frontmatter field (epic|feature|bug, default feature)"
```

---

### Task 2: `tiers` config block + `lib/tiers.py` profile reader

**Files:**
- Modify: `schemas/config.schema.json`
- Create: `scripts/factory/lib/tiers.py`
- Test: `tests/test_tiers.py`

**Interfaces:**
- Produces: `tiers.DEFAULTS` (dict per tier), `tiers.profile(repo, tier) -> {"research": str, "review": str}` — the repo config `tiers.<tier>` merged over `DEFAULTS[tier]`; an unknown tier falls back to the `feature` profile.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tiers.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, tiers


def _set_tiers(repo, block):
    p = repo / ".factory" / "config.json"
    data = json.loads(p.read_text())
    data["tiers"] = block
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                 encoding="utf-8")


class TierProfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults(self):
        self.assertEqual(tiers.profile(self.repo, "epic"),
                         {"research": "deep", "review": "full"})
        self.assertEqual(tiers.profile(self.repo, "feature"),
                         {"research": "web", "review": "full"})
        self.assertEqual(tiers.profile(self.repo, "bug"),
                         {"research": "off", "review": "light"})

    def test_unknown_tier_falls_back_to_feature(self):
        self.assertEqual(tiers.profile(self.repo, "mystery"),
                         tiers.profile(self.repo, "feature"))

    def test_config_overrides_merge_over_defaults(self):
        _set_tiers(self.repo, {"feature": {"research": "deep"}})
        prof = tiers.profile(self.repo, "feature")
        self.assertEqual(prof["research"], "deep")
        self.assertEqual(prof["review"], "full")   # unspecified key kept

    def test_config_validates(self):
        _set_tiers(self.repo, {"bug": {"research": "off", "review": "light"}})
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_bad_review_enum_rejected(self):
        _set_tiers(self.repo, {"bug": {"review": "medium"}})
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("review" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_tiers -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.factory.lib.tiers'`.

- [ ] **Step 3: Add the `tiers` config block to the schema**

In `schemas/config.schema.json`, add to the top-level `"properties"` (after `"research"`):

```json
    "tiers": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "epic": {"$tier_profile": true},
        "feature": {"$tier_profile": true},
        "bug": {"$tier_profile": true}
      }
    }
```

Replace each `{"$tier_profile": true}` placeholder above with this exact object (the validator has no `$ref`, so it is written out three times):

```json
        {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "research": {"type": "string",
                         "enum": ["off", "inputs-only", "web", "deep"]},
            "review": {"type": "string", "enum": ["light", "full"]}
          }
        }
```

So the final `tiers` block has `epic`/`feature`/`bug`, each the full profile object above. No `$ref`, no placeholder keys.

- [ ] **Step 4: Create `lib/tiers.py`**

```python
"""Work-item materiality tiers: how much of the expensive machinery a change
is worth. tier (epic|feature|bug) is an item's frontmatter field (see
items.py); this module maps a tier to its {research, review} profile, config-
overridable per repo. Python stdlib only.

research: off | inputs-only | web | deep  — the ceiling on focus-group/market
research (deep = the focus group runs; features/bugs never trigger it).
review:  light | full — full = the six-seat council; light = the inward
correctness seats only (a bug fix needs correctness review, not a market read).
"""

import json

from . import paths

DEFAULTS = {
    "epic": {"research": "deep", "review": "full"},
    "feature": {"research": "web", "review": "full"},
    "bug": {"research": "off", "review": "light"},
}


def profile(repo, tier):
    """The effective {research, review} profile for a tier: the repo config
    `tiers.<tier>` block merged over DEFAULTS[tier]. An unknown tier falls
    back to the feature profile (matches items.DEFAULT_TIER)."""
    base = dict(DEFAULTS.get(tier, DEFAULTS["feature"]))
    block = {}
    p = paths.config_path(repo)
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            if isinstance(raw, dict) and isinstance(raw.get("tiers"), dict):
                override = raw["tiers"].get(tier)
                if isinstance(override, dict):
                    block = override
        except json.JSONDecodeError:
            block = {}
    base.update({k: v for k, v in block.items() if k in ("research", "review")})
    return base
```

- [ ] **Step 5: Run the test + full suite**

Run: `python3 -m unittest tests.test_tiers -v` → PASS (5 tests).
Run: `python3 -m unittest discover -s tests -v` → all green.

- [ ] **Step 6: Commit**

```bash
git add schemas/config.schema.json scripts/factory/lib/tiers.py tests/test_tiers.py
git commit -m "feat(tiers): tiers config block + profile reader (research/review per tier)"
```

---

### Task 3: `factory tier` CLI, `factory add --tier`, tier in `status`

**Files:**
- Modify: `scripts/factory/factory.py`
- Test: `tests/test_cli.py` (or the file that already drives `factory.main` for `add`/`priority`/`status` — match the existing CLI test file; if none, create `tests/test_cli_tier.py`)

**Interfaces:**
- Produces: `factory tier <id> <epic|feature|bug>` (validated set; exit 2 not-a-repo, 2 refusal on bad value/missing item, 0 ok); `factory add ... [--tier epic|feature|bug]` (sets tier at creation when given); `factory status` prints each item's tier.

- [ ] **Step 1: Write the failing test**

Find the existing CLI test that exercises `factory.main(["add", ...])` / `["priority", ...]` (grep `tests/` for `"priority"`). Append a TestCase there (or create `tests/test_cli_tier.py` with the same `run_cli` helper pattern used elsewhere, e.g. from `tests/test_cli_pool.py`):

```python
class CliTierTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.run_cli("init")
        self.run_cli("add", "A thing", "--kind", "backend")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(self.repo), *args])
        return code, out.getvalue(), err.getvalue()

    def _only_id(self):
        from scripts.factory.lib import items
        return items.list_items(self.repo)[0]["id"]

    def test_add_with_tier(self):
        code, out, err = self.run_cli("add", "Big thing", "--kind", "mixed",
                                      "--tier", "epic")
        self.assertEqual(code, 0, err)

    def test_tier_set_and_reject(self):
        item_id = self._only_id()
        code, out, err = self.run_cli("tier", item_id, "bug")
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli("tier", item_id, "mega")
        self.assertEqual(code, 2)

    def test_status_shows_tier(self):
        item_id = self._only_id()
        self.run_cli("tier", item_id, "epic")
        code, out, err = self.run_cli("status")
        self.assertEqual(code, 0, err)
        self.assertIn("epic", out)
```

Import `factory`, `tempfile`, `Path` at the top if creating a new file.

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_cli_tier -v` (or the file you appended to)
Expected: FAIL — argparse `invalid choice: 'tier'` / `unrecognized arguments: --tier`.

- [ ] **Step 3: Wire the command into `factory.py`**

Add `cmd_tier` (near `cmd_priority`):

```python
def cmd_tier(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        items.set_tier(args.repo, args.item, args.tier)
    except items.ItemError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.item} tier {args.tier}")
    return 0
```

In `cmd_add`, after building `meta` and before `items.save_item`, set the tier when given:

```python
    if getattr(args, "tier", None):
        meta["tier"] = args.tier
```

In `cmd_status`'s plain-text row (the `print(f"{m['id']:<40} ...")` line), include the tier. Change that line to:

```python
            print(f"{m['id']:<40} {m['stage']:<14} p{priority:<4} "
                  f"{items.item_tier(m)}/{m['kind']}")
```

Register the subparser (near `priority`):

```python
    p = sub.add_parser("tier", help="set an item's materiality tier")
    p.add_argument("item")
    p.add_argument("tier", choices=list(items.TIERS))
    p.set_defaults(func=cmd_tier)
```

And add `--tier` to the `add` subparser:

```python
    p.add_argument("--tier", choices=list(items.TIERS))
```

(Add it to the existing `add` parser block, alongside `--kind`.)

- [ ] **Step 4: Run the test + full suite**

Run: `python3 -m unittest tests.test_cli_tier -v` → PASS.
Run: `python3 -m unittest discover -s tests -v` → all green (existing `status` tests: confirm none assert the exact row string — if one does, update it to include the new `tier/kind` segment, since this deliberately changes the plain-text row; the `--json` path is unchanged).

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/factory.py tests/test_cli_tier.py
git commit -m "feat(tiers): factory tier CLI + add --tier + tier in status"
```

---

### Task 4: `factory doctor` exposes resolved tier profiles

**Files:**
- Modify: `scripts/factory/lib/doctor.py`
- Test: `tests/test_doctor.py`

**Interfaces:**
- Produces: a `"tiers"` key in `doctor.report(repo)` = `{tier: profile}` for each of `epic|feature|bug` (from `tiers.profile`), so a skill reads the effective policy in one `factory doctor --json`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_doctor.py`'s `TestDoctor`:

```python
    def test_reports_tier_profiles(self):
        r = doctor.report(self.repo)
        self.assertIn("tiers", r)
        self.assertEqual(r["tiers"]["bug"]["review"], "light")
        self.assertEqual(r["tiers"]["epic"]["research"], "deep")
        self.assertEqual(r["tiers"]["feature"]["review"], "full")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_doctor.TestDoctor.test_reports_tier_profiles -v`
Expected: FAIL — `KeyError: 'tiers'`.

- [ ] **Step 3: Add tier profiles to the doctor readout**

In `scripts/factory/lib/doctor.py`, add `tiers` to the imports:

```python
from . import dispatch, initrepo, items, paths, tiers, work
```

Add a helper:

```python
def tier_profiles(repo):
    return {tier: tiers.profile(repo, tier) for tier in items.TIERS}
```

In `report(...)`, add one key alongside `"workers"`:

```python
        "tiers": tier_profiles(repo),
```

(Note: `report`'s `REPORT_KEYS` render tuple in `render()` is unchanged — `tiers`, like `workers`, surfaces in `--json` only, matching the existing convention.)

- [ ] **Step 4: Run the test + full suite**

Run: `python3 -m unittest tests.test_doctor -v` → PASS.
Run: `python3 -m unittest discover -s tests -v` → all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/doctor.py tests/test_doctor.py
git commit -m "feat(tiers): factory doctor reports resolved tier profiles"
```

---

### Task 5: skills SET the tier (triage, bug, roadmap) + coherence guard

**Files:**
- Modify: `skills/factory-triage/SKILL.md`
- Modify: `skills/factory-bug/SKILL.md`
- Modify: `skills/factory-roadmap/SKILL.md`
- Modify: `tests/test_plugin_coherence.py`

**Interfaces:** none (prose + a drift guard).

- [ ] **Step 1: Write the failing coherence test**

Append to `TestPluginCoherence` in `tests/test_plugin_coherence.py`:

```python
    def test_tier_wiring_present(self):
        triage = read(ROOT / "skills/factory-triage/SKILL.md")
        self.assertIn("factory tier", triage)
        bug = read(ROOT / "skills/factory-bug/SKILL.md")
        self.assertIn("factory tier", bug)
        review = read(ROOT / "skills/factory-review/SKILL.md")
        self.assertIn("tier", review)
        research = read(ROOT / "skills/factory-research/SKILL.md")
        self.assertIn("epic", research)
```

(This method also guards Task 6's `factory-review`/`factory-research` edits — both tasks must land for it to pass; run it green only after Task 6. For Task 5, run the three set-side assertions by temporarily checking `triage`/`bug` — but the committed test includes all four; it goes green at the end of Task 6. Sequence: add the test now (RED), make the triage/bug/roadmap edits in this task, and expect this specific method to stay RED on the review/research lines until Task 6. Keep the rest of the suite green.)

To keep this task's suite green, split the guard: put ONLY the set-side assertions in this task, and add the consume-side ones in Task 6. Use this method body for Task 5:

```python
    def test_tier_set_wiring_present(self):
        triage = read(ROOT / "skills/factory-triage/SKILL.md")
        self.assertIn("factory tier", triage)
        bug = read(ROOT / "skills/factory-bug/SKILL.md")
        self.assertIn("factory tier", bug)
        roadmap = read(ROOT / "skills/factory-roadmap/SKILL.md")
        self.assertIn("tier", roadmap)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_plugin_coherence.TestPluginCoherence.test_tier_set_wiring_present -v`
Expected: FAIL — `'factory tier' not found` in factory-triage.

- [ ] **Step 3: factory-triage — the agent sets the tier**

In `skills/factory-triage/SKILL.md`, add a step after step 5 (the `kind` correction), renumbering the following steps:

```
6. **Set the materiality tier.** Decide the item's tier from its scope — `epic` (a material feature or UI-heavy initiative that warrants the focus group and full review), `feature` (a normal change: full review, standard research), or `bug` (a defect fix: light correctness review, no market research; usually filed via `/factory:bug` already carrying `tier: bug`). Set it with `factory tier ITEM <epic|feature|bug>`. The council's scope read informs this; when a human is present and the call is close, ask. Tier is a materiality axis, **orthogonal to `kind`** — a `backend` epic and a `ui` feature are both normal. Default when genuinely unsure: `feature`.
```

- [ ] **Step 4: factory-bug — file as `tier: bug`**

In `skills/factory-bug/SKILL.md`, step 3 ("File the item"), after the `bug: true` frontmatter sentence, add:

```
   Also set the item's tier to bug: `factory tier ITEM bug` (a defect gets the light correctness-only review and skips market research — see the tier profiles in the capabilities/`factory doctor` readout). `tier: bug` is the materiality axis; the separate `bug: true` flag still drives the repro gate.
```

- [ ] **Step 5: factory-roadmap — tag candidates with a tier**

In `skills/factory-roadmap/SKILL.md`, find where accepted candidates are filed as items (the `factory add` + advance sequence) and add, right after each item is created/advanced:

```
   Set each accepted item's materiality tier with `factory tier <id> <epic|feature|bug>`: `epic` for a material or UI-heavy initiative (gets the focus group + full review), `feature` for a normal roadmap item, `bug` only if the candidate is a defect. The batch council's scope read informs the call; default `feature` when unsure. Tier is orthogonal to `kind`.
```

(If factory-roadmap files items via a helper or loop, add the `factory tier` call at the same point the priority/stage advance happens for each accepted candidate.)

- [ ] **Step 6: Run the coherence test + full suite**

Run: `python3 -m unittest tests.test_plugin_coherence.TestPluginCoherence.test_tier_set_wiring_present -v` → PASS.
Run: `python3 -m unittest discover -s tests -v` → all green.

- [ ] **Step 7: Commit**

```bash
git add skills/factory-triage/SKILL.md skills/factory-bug/SKILL.md skills/factory-roadmap/SKILL.md tests/test_plugin_coherence.py
git commit -m "feat(tiers): triage/bug/roadmap set the materiality tier"
```

---

### Task 6: skills CONSUME the tier (review depth, focus-group guard) + coherence guard

**Files:**
- Modify: `skills/factory-review/SKILL.md`
- Modify: `skills/council-review/SKILL.md`
- Modify: `skills/factory-research/SKILL.md`
- Modify: `tests/test_plugin_coherence.py`

**Interfaces:** none (prose + a drift guard).

- [ ] **Step 1: Write the failing coherence test**

Append to `TestPluginCoherence`:

```python
    def test_tier_consume_wiring_present(self):
        review = read(ROOT / "skills/factory-review/SKILL.md")
        self.assertIn("tier", review)
        council = read(ROOT / "skills/council-review/SKILL.md")
        self.assertIn("light", council)
        research = read(ROOT / "skills/factory-research/SKILL.md")
        self.assertIn("epic", research)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_plugin_coherence.TestPluginCoherence.test_tier_consume_wiring_present -v`
Expected: FAIL — `'tier' not found` in factory-review (before the edit).

- [ ] **Step 3: factory-review — pass the tier's review depth to the council**

In `skills/factory-review/SKILL.md`, in step 2 ("Run the council"), after the "seed = ..." sentence, add:

```
   **Review depth by tier.** Read the item's `tier` (from `factory status --json`) and the tier profiles (from `factory doctor --json` → `tiers`). If the tier's `review` is `light` (default for `bug`), tell `council-review` to run its **light review** seat set — the inward correctness seats only — instead of the full six. `full` (features and epics) runs the whole council as today. The end-to-end walk in this step is NOT skipped for a light review — a bug fix still gets its flow walked; only the market/persona seats drop.
```

- [ ] **Step 4: council-review — light-review seat set**

In `skills/council-review/SKILL.md`, step 2 ("Round 1 — independent"), after the research-mode parenthetical about the four outward seats, add:

```
   (In **review mode** with a **light** review depth — a `bug`-tier item, per factory-review — dispatch only the inward correctness seats: `agents/council-architecture.md`, `council-engineering-quality.md`, `council-product.md`, plus `council-ui-taste.md` when the item's `kind` is `ui` or `mixed`; skip `customer` and `commercial` — a defect fix needs a correctness read, not a market/persona one. A `full` review dispatches all six as above.)
```

- [ ] **Step 5: factory-research — focus group requires `tier: epic`**

In `skills/factory-research/SKILL.md`, §3b ("Focus group (opt-in)"), extend the **Trigger** sentence so the focus group additionally requires an epic-tier context. Replace the Trigger sentence:

```
**Trigger:** runs only when the resolved depth is `deep`
or the run was passed an explicit `--focus-group` argument; `--no-focus-group`
suppresses it at `deep`.
```

with:

```
**Trigger:** runs only when the resolved depth is `deep` **and** the work is
material — i.e. the item or roadmap candidate driving this research is
`tier: epic` (or, at bare product initiation with no specific item, the
product itself is the material undertaking). A `feature`- or `bug`-tier
context never triggers the focus group, even under a global `deep` — the
focus group is for material epics only (guard rail). An explicit
`--focus-group` argument still forces it at any depth; `--no-focus-group`
suppresses it. When the trigger is off, this section is skipped entirely.
```

Also, in §1 ("Depth"), after the sentence about the `--depth` override, add:

```
When this research run is scoped to a specific work item or roadmap candidate,
cap the effective depth at that item's tier `research` profile (`factory doctor
--json` → `tiers`): a `feature` caps at `web` (no focus group), a `bug` at
`off` (no research), an `epic` may go to `deep`. The `research.depth` config is
the global ceiling; the tier caps it further for non-material work.
```

- [ ] **Step 6: Run the coherence test + full suite**

Run: `python3 -m unittest tests.test_plugin_coherence -v` → PASS (both tier guards).
Run: `python3 -m unittest discover -s tests -v` → all green.

- [ ] **Step 7: Commit**

```bash
git add skills/factory-review/SKILL.md skills/council-review/SKILL.md skills/factory-research/SKILL.md tests/test_plugin_coherence.py
git commit -m "feat(tiers): review depth + focus-group guard by materiality tier"
```

---

## Notes for the executor

- **Run the full suite after every task.** Tasks 1–4 touch schemas/config that other tests read.
- **`tier` is orthogonal to `kind` and to the `bug` flag.** Do not couple them in the engine: `item_tier` defaults to `feature`; the `bug: true` repro gate is untouched (only `factory-bug` additionally sets `tier: bug`).
- **Additive + back-compat.** No existing test sets `tier`; all must stay green via the `feature` default. `DEFAULT_CONFIG` is NOT modified — tier defaults live in `lib/tiers.py`, the config block is optional.
- **The bug loop already exists** (`factory-bug` + `machine.py` repro gates + seeded regression acceptance criteria + verify Iron Law). This plan does NOT rebuild it; `tier: bug` only routes bugs to the light review and no-research profile.
- **Prose-edit fidelity:** the coherence guards grep for `factory tier` (triage/bug), `tier` (roadmap/review/research), `light` (council-review), `epic` (research). Keep those exact tokens.
- **Never run tree-wide git commands** (`git restore .`/`checkout .`/`stash`/`clean`/`add -A`); stage only each task's named files; never `README.md`.

## Self-Review

- **Tier field + default + validation:** Task 1 (items.py + schema + tests). **Config presets:** Task 2 (`tiers.py` + config schema). **Agent-settable:** Task 3 (`factory tier` CLI, `add --tier`). **Readable policy:** Task 4 (doctor). **Set by triage/bug/roadmap:** Task 5. **Focus-group guard + light review:** Task 6. Covers the design.
- **Back-compat:** absent tier → `feature` (Task 1 helper); feature profile = full review + web research ≈ today (Task 2 defaults). No `DEFAULT_CONFIG` change.
- **Placeholder scan:** the schema `$tier_profile` marker in Task 2 Step 3 is explicitly expanded to the literal object in the same step — no placeholder ships.
- **Type consistency:** `item_tier(meta)->str`, `set_tier(repo,id,tier)->meta`, `tiers.profile(repo,tier)->{research,review}`, `doctor.report[...]["tiers"][tier]` — used consistently across CLI (Task 3), doctor (Task 4), and the skills (Tasks 5–6).
