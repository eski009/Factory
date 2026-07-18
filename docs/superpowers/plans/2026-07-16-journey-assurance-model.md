# Journey Assurance — Plan 2: Journey Model + Spec Impact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The journey model's seed surfaces (templates), brownfield inventory inference at intake, and the spec stage's three journey-impact duties (map, declare, set) — including bug-intake seeding.

**Architecture:** Prose-skill and template changes only; the engine (Plan 1, merged into this branch) already enforces everything these skills produce. Tests are structural pins in `tests/test_plugin_structure.py` / `tests/test_plugin_coherence.py` plus one initrepo behavior test.

**Tech Stack:** Markdown skill prose + JSON template. Tests: stdlib unittest.

**Spec:** `docs/superpowers/specs/2026-07-15-journey-assurance-design.md` (Journey model + Feature journey-impact contract sections).

## Global Constraints

- Journey IDs `J-NNN` (`^J-[0-9]{3}$`); graph entries must satisfy `schemas/journey-graph.schema.json` (criticality `core|high|standard`, status `inventory|draft|approved`).
- The inventory template MUST carry the exact `_Not yet written.` placeholder prefix (the init interview and doctor key on it).
- Evidence discipline: every seeded claim cites `(source: <path-or-url>)` or is tagged `(assumption)`; never invent journeys; unanswerables go to `open-questions.md`.
- factory-intake's write-license (its `## Never` section) is a hard contract — widening it must be explicit prose, and it must NOT license `contracts/` writes to intake.
- The spec.md section order is defined in TWO synced places (`skills/factory-spec/SKILL.md` and `agents/spec-writer.md`); `## Journey impact` sits between `## Behavior` and `## Non-goals` in both.
- The valid empty declaration is `None — no customer journey affected.` plus a one-line justification; a `none` item writes NO impact.json.
- `impact.json` lives at `.factory/items/<id>/assurance/impact.json` and must satisfy `schemas/assurance-impact.schema.json`.
- Do NOT link any file as `references/<name>.md` from a skill unless it lives in `skills/capabilities/references/` (test_plugin_coherence.py resolves all such links there).
- Run the FULL suite before every commit. Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: journeys templates + scaffold pins

**Files:**
- Create: `templates/docs-factory/journeys/inventory.md`, `templates/docs-factory/journeys/graph.json`
- Test: `tests/test_plugin_structure.py`, `tests/test_initrepo.py`

**Interfaces:**
- Produces: `factory init` scaffolds `docs/factory/journeys/{inventory.md,graph.json}` (fill-gaps-only, via the existing template rglob copy); the skeleton graph schema-validates; the inventory carries the interview-harvestable marker.

- [ ] **Step 1: Write the failing tests**

`tests/test_plugin_structure.py`:

```python
    def test_journeys_templates_exist_and_validate(self):
        inv = ROOT / "templates/docs-factory/journeys/inventory.md"
        graph = ROOT / "templates/docs-factory/journeys/graph.json"
        self.assertTrue(inv.exists())
        self.assertTrue(graph.exists())
        self.assertIn("_Not yet written.", inv.read_text())
        import json as _json
        from scripts.factory.lib.initrepo import load_schema
        from scripts.factory.lib.validate import validate
        data = _json.loads(graph.read_text())
        self.assertEqual(validate(data, load_schema("journey-graph"), "graph"), [])
```

`tests/test_initrepo.py` (adapt to the file's init-test fixture style):

```python
    def test_init_scaffolds_journeys_and_tree_validates(self):
        initrepo.init(self.repo)
        self.assertTrue((self.repo / "docs" / "factory" / "journeys" / "inventory.md").exists())
        self.assertTrue((self.repo / "docs" / "factory" / "journeys" / "graph.json").exists())
        self.assertEqual(initrepo.validate_tree(self.repo), [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_plugin_structure tests.test_initrepo -v` — the two new tests FAIL (templates missing).

- [ ] **Step 3: Create the templates**

`templates/docs-factory/journeys/inventory.md`:

```markdown
# Journey inventory

<!-- Every known customer journey, one entry per journey: id (J-NNN), title,
     persona, trigger, intended outcome, criticality (core|high|standard).
     graph.json is the machine-readable index of this list; deep contracts
     live in contracts/ and exist only where they earn their keep (core,
     high-risk, touched by current work, implicated by an escape). Every
     claim cites a source: (source: <path-or-url>) or is tagged (assumption). -->

_Not yet written. Brownfield intake infers an inventory from routes, screens,
navigation, and the test suite; the init interview asks the owner about the
gaps; the spec stage registers new journeys as work introduces them._
```

`templates/docs-factory/journeys/graph.json`:

```json
{
  "version": 1,
  "journeys": []
}
```

- [ ] **Step 4: Run the full suite** — `python3 -m unittest discover -s tests` → all green (init copies land automatically; validate_tree already knows the graph schema from Plan 1).

- [ ] **Step 5: Commit**

```bash
git add templates/docs-factory/journeys tests/test_plugin_structure.py tests/test_initrepo.py
git commit -m "feat(journeys): inventory + graph templates scaffolded at init

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: factory-intake journeys collector + widened write-license

**Files:**
- Modify: `skills/factory-intake/SKILL.md`
- Test: `tests/test_plugin_structure.py`

**Interfaces:**
- Produces: brownfield intake emits an inferred journey inventory (cited, assumption-tagged criticality, `status: inventory`, never contracts); the `## Never` write-license adds `docs/factory/journeys/` (inventory.md + graph.json only).

- [ ] **Step 1: Write the failing test**

```python
    def test_intake_journeys_collector_and_license(self):
        text = (ROOT / "skills/factory-intake/SKILL.md").read_text()
        self.assertIn("journeys/inventory.md", text)
        self.assertIn("graph.json", text)
        self.assertIn("(assumption)", text)
        self.assertIn("never contracts/", text)
        self.assertIn("docs/factory/journeys/", text)
```

Run: `python3 -m unittest tests.test_plugin_structure -v` → FAIL.

- [ ] **Step 2: Edit the skill**

In `skills/factory-intake/SKILL.md`, in the brownfield collectors block (the list containing `routes, screens, navigation surface → users.md`), add one collector bullet after the test-suite bullet:

```markdown
- **Journey inventory (brownfield):** the same routes/screens/navigation
  mining and test-suite reading also emit a first journey inventory —
  `docs/factory/journeys/inventory.md` entries plus matching `graph.json`
  records (stable id `J-NNN` starting at J-001, slug, title, persona when
  `users.md` names one, trigger, intended outcome, `status: inventory`,
  links to the routes/screens/tests that evidence it). Criticality is a
  guess at intake — tag it `(assumption)`; every entry cites its source
  like any other claim. Never invent a journey the code doesn't evidence —
  an uncertain flow goes to `open-questions.md` instead. Greenfield repos
  skip this collector: the templates stay placeholder and the init
  interview asks the owner.
```

And replace the `## Never` paragraph's write-license sentence:

```markdown
Never touch product code or `CLAUDE.md`. This skill only writes to
`docs/factory/brain/*.md`, `docs/factory/journeys/` (inventory.md and
graph.json only — never contracts/, which belong to the spec stage and the
council firewall), and, in brownfield mode, `docs/factory/packets/taste.md`;
it has no license to change anything else in the target repo, however
tempting a fix looks along the way.
```

- [ ] **Step 3: Full suite green; commit**

```bash
git add skills/factory-intake/SKILL.md tests/test_plugin_structure.py
git commit -m "feat(intake): brownfield journey-inventory collector + journeys write-license

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: factory-spec + spec-writer journey-impact duties

**Files:**
- Modify: `skills/factory-spec/SKILL.md`, `agents/spec-writer.md`
- Test: `tests/test_plugin_structure.py`, `tests/test_plugin_coherence.py`

**Interfaces:**
- Produces: spec.md gains `## Journey impact` between `## Behavior` and `## Non-goals` in BOTH synced section lists; factory-spec's three duties (Map → Declare → Set) including inventory-entry registration, minimal draft contracts for any affected journey lacking one (tier-scaled), the machine twin `impact.json`, and the `factory journeys` verb; spec-writer produces the section but the ORCHESTRATOR persists impact.json and runs the verb (agent is read-only).

- [ ] **Step 1: Write the failing tests**

`tests/test_plugin_structure.py`:

```python
    def test_spec_skill_journey_impact_duties(self):
        text = (ROOT / "skills/factory-spec/SKILL.md").read_text()
        self.assertIn("## Journey impact", text)
        self.assertIn("assurance/impact.json", text)
        self.assertIn("factory journeys", text)
        self.assertIn("None — no customer journey affected.", text)
        self.assertIn("status: draft", text)
        self.assertIn("Run & fixtures", text)
```

`tests/test_plugin_coherence.py`:

```python
    def test_spec_section_lists_stay_synced(self):
        # the spec.md section order is defined in two places; Journey impact
        # must sit between Behavior and Non-goals in BOTH.
        for rel in ("skills/factory-spec/SKILL.md", "agents/spec-writer.md"):
            text = read(ROOT / rel)
            b = text.index("## Behavior`")
            j = text.index("## Journey impact`")
            n = text.index("## Non-goals`")
            self.assertTrue(b < j < n, f"{rel}: Journey impact must sit between Behavior and Non-goals")
```

(Note the backtick in the search keys — both files name sections as `` `## Behavior` `` in backticks; anchor on that form.)

Run both files' tests → FAIL.

- [ ] **Step 2: Edit `skills/factory-spec/SKILL.md`**

1. **Read first** paragraph: append `docs/factory/journeys/graph.json` and `inventory.md` to the read list.
2. After the `## Large items: dispatch spec-writer` section, insert a new section:

```markdown
## Journey impact — map, declare, set (mandatory)

The engine refuses to leave spec until journey impact is recorded; these
three duties run for every item, in order:

1. **Map.** Read `docs/factory/journeys/graph.json` and `inventory.md`; map
   the item's `## Behavior` onto journey nodes. An item that introduces a
   new journey registers it directly as an inventory-only entry (next free
   `J-NNN` id, `status: inventory`, cited to this item's spec) — the same
   direct-write license triage has for `roadmap.md`. Any affected journey
   that has no contract yet gets a **minimal draft contract** at
   `docs/factory/journeys/contracts/J-NNN-<slug>.md` with `status: draft`
   recorded in `graph.json`: cover at least the touched nodes (what the
   customer knows at each, what they expect next), deterministic oracles
   for the required scenarios, a Run & fixtures section (exact launch
   commands, fixture setup, credentials through safe fixture mechanisms),
   and interruption/recovery paths — depth scaled by the tier's `assure`
   profile (`factory doctor --json` → tiers: bug `node`, feature
   `affected`, epic `full`). Amending a `status: approved` contract is
   NEVER done directly — that goes through a `council-judgement` bid with
   `--surface journeys/contracts/<file>`.
2. **Declare.** Write the `## Journey impact` spec section (see structure
   below) AND its machine twin `.factory/items/<id>/assurance/impact.json`
   (shape: `schemas/assurance-impact.schema.json` — per journey: id,
   nodes_changed, transitions_changed, new_states, and the required
   scenarios, each `{id, kind: happy|recovery|interruption, description}`).
   The assure stage cross-checks verdicts against this file scenario by
   scenario. For a no-impact item the section reads exactly
   `None — no customer journey affected.` plus a one-line justification,
   and NO impact.json is written.
3. **Set.** Run `factory journeys ITEM <none|J-004,...>` — exactly how
   triage runs `factory tier`. The spec-exit gate checks both the section
   heading and this declaration.
```

3. **Spec structure** list: insert between the `## Behavior` and `## Non-goals` bullets:

```markdown
- `## Journey impact` — affected journey ids (from `graph.json`), nodes
  changed, transitions changed, new states introduced, and required
  assurance scenarios (happy path, recovery paths, viewport requirements
  where the surface is a browser) — or exactly
  `None — no customer journey affected.` plus a one-line justification.
  If the item body contains a section titled
  `## Journey impact (seeded at bug intake — carry into spec.md verbatim)`,
  its content MUST appear verbatim here — it may be extended, never
  replaced or reworded.
```

4. In `## Large items: dispatch spec-writer`, append one sentence: `The subagent is read-only, so after persisting its spec text the orchestrator also writes impact.json from the report's ## Journey impact section and runs the factory journeys verb (duty 3), exactly as it files the bids.`

- [ ] **Step 3: Edit `agents/spec-writer.md`**

1. **Inputs**: append journey excerpts: `..., and excerpts from docs/factory/journeys/graph.json + inventory.md for the journeys the item plausibly touches.`
2. **Spec structure** list: insert between the Behavior and Non-goals bullets:

```markdown
- `## Journey impact` — affected journey ids, nodes changed, transitions
  changed, new states introduced, and required assurance scenarios — or
  exactly `None — no customer journey affected.` plus a one-line
  justification. Name any affected journey that lacks a contract so the
  orchestrator can draft it.
```

- [ ] **Step 4: Full suite green; commit**

```bash
git add skills/factory-spec/SKILL.md agents/spec-writer.md tests/test_plugin_structure.py tests/test_plugin_coherence.py
git commit -m "feat(spec): journey impact duties — map, declare, set + synced section lists

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: factory-bug journey-impact seeding

**Files:**
- Modify: `skills/factory-bug/SKILL.md`
- Test: `tests/test_plugin_structure.py`

**Interfaces:**
- Produces: bug intake seeds `## Journey impact (seeded at bug intake — carry into spec.md verbatim)` in the item body (replication names the broken node; bug-tier assure depth = changed node + immediate transition); factory-spec (Task 3) already carries it verbatim.

- [ ] **Step 1: Write the failing test**

```python
    def test_bug_intake_seeds_journey_impact(self):
        text = (ROOT / "skills/factory-bug/SKILL.md").read_text()
        self.assertIn("## Journey impact (seeded at bug intake — carry into spec.md verbatim)", text)
        self.assertIn("immediate transition", text)
```

Run → FAIL.

- [ ] **Step 2: Edit the skill**

In `skills/factory-bug/SKILL.md`, extend step 6 (the seeded-criteria step). After the two mandatory criteria and their closing paragraph, append:

```markdown
   Replication almost always identifies the broken journey node precisely,
   so seed the impact too: append a section titled exactly
   `## Journey impact (seeded at bug intake — carry into spec.md verbatim)`
   naming the affected journey id from `docs/factory/journeys/graph.json`,
   the changed node, and the immediate transition — the bug tier's assure
   depth (`node`) walks exactly that. If the graph has no matching journey,
   name the flow in prose and flag it for the spec stage to register. Only
   a bug with genuinely no customer-visible surface seeds
   `None — no customer journey affected.` plus the justification.
```

- [ ] **Step 3: Full suite green; commit**

```bash
git add skills/factory-bug/SKILL.md tests/test_plugin_structure.py
git commit -m "feat(bug): seed journey impact at intake — carried verbatim into spec

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Plan self-review notes

- Spec coverage: templates+scaffold (T1), inventory inference + license (T2), the three duties + both synced lists + draft contracts + verbatim-carry rule (T3), bug seeding (T4). The interview harvests the inventory placeholder automatically via its `_Not yet written.` prefix rule — zero interview changes, by design.
- The coherence sync test anchors on the backticked section-name form both files actually use.
- Intake never writes contracts/ — stated in both the collector bullet and the license.
