# DesignSync Journeys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Journey-model visibility and enrichment through the existing DesignSync capability: a pushed visual journey map, a greenfield frame-pull inventory collector, and node-annotated design-gate pushes.

**Architecture:** Prose-only (skill/reference/command edits + structure pins). Everything inherits DesignSync's existing doctrine verbatim: interactive-only, probe-don't-ask, degrade-never-block, proxy spend, repo-canonical.

**Tech Stack:** Markdown. Tests: stdlib unittest structure pins.

**Spec:** `docs/superpowers/specs/2026-07-16-designsync-journeys-design.md` — read it first.

## Global Constraints

- No engine, schema, or agent changes. No new capability row — extend `references/designsync.md` and cite it; never re-derive degradation logic in stage skills.
- Every push: only when any `mcp__claude-design__*` tool is present AND `designsync_project` is configured; best-effort, never blocks or fails a stage; one proxy spend event per round-trip (`"provenance":"proxy"`, no `tokens` key).
- The map file is `factory-journeys.html` — one self-contained HTML flow view regenerated (replaced) per push, built from `graph.json` only.
- Greenfield pull emits inventory entries cited `(source: claude-design <project>/<file>)` with `(assumption)` criticality, `status: inventory`, never contracts/ — inside intake's existing journeys write-license.
- Draft-contract expectation refresh: DRAFT contracts only; approved contracts amend only via the council-judgement firewall (state this where the refresh is described).
- The interview needs zero changes (it already harvests `(assumption)` tags and placeholders from journeys/inventory.md) — do not touch it.
- FULL suite before every commit; commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: designsync.md Journeys section + intake (pull + push)

**Files:**
- Modify: `skills/capabilities/references/designsync.md`, `skills/factory-intake/SKILL.md`
- Test: `tests/test_plugin_structure.py`

- [ ] **Step 1: failing pins**

```python
    def test_designsync_journeys_section(self):
        ref = (ROOT / "skills/capabilities/references/designsync.md").read_text()
        self.assertIn("## Journeys", ref)
        self.assertIn("factory-journeys.html", ref)
        self.assertIn("(source: claude-design", ref)
        self.assertIn("never contracts/", ref)
        self.assertIn("never a second source of truth", ref)

    def test_intake_greenfield_frame_pull(self):
        text = (ROOT / "skills/factory-intake/SKILL.md").read_text()
        self.assertIn("designsync_project", text)
        self.assertIn("(source: claude-design", text)
        self.assertIn("factory-journeys.html", text)
```

Run `python3 -m unittest tests.test_plugin_structure -v` → both FAIL.

- [ ] **Step 2: edits.** Read both files fully first.

In `skills/capabilities/references/designsync.md`, append a `## Journeys` section:

```markdown
## Journeys

The journey model (`docs/factory/journeys/`) gets the same convenience-mirror
treatment as design tokens — repo files canonical, the linked project never a
second source of truth:

- **Visual map (push).** The three surfaces that mutate the journey model —
  factory-intake at the end of seeding, factory-spec when it registers a
  journey or drafts a contract, and `/factory:escape` after a `contract:`
  promotion — regenerate `factory-journeys.html` in the linked project via
  `mcp__claude-design__write_files`: one self-contained HTML flow view built
  from `graph.json` (nodes, transitions, criticality, contract status),
  replacing the previous file. Strictly best-effort: a failed push never
  blocks the stage, and each round-trip logs one proxy spend event.
- **Greenfield frame-pull (intake only).** A greenfield repo has no routes to
  mine, but a linked design project often holds the product's screens before
  any code exists. When the tool family is present and `designsync_project`
  is set, factory-intake reads the project's frame/flow structure
  (`mcp__claude-design__list_files` + `read_file`) and emits journey-inventory
  entries from screen sequences — each cited
  `(source: claude-design <project>/<file>)`, criticality tagged
  `(assumption)`, `status: inventory`, never contracts/. Frames are
  hypotheses, not evidence: the init interview's normal assumption-harvest
  puts every inferred journey in front of the human. Without the capability,
  greenfield intake is unchanged.
- **What never happens here:** no pull ever touches `contracts/` (drafts are
  the spec stage's job; approved contracts amend only through the
  council-judgement firewall), and no design artifact ever substitutes for
  the assure stage's running-product evidence.
```

In `skills/factory-intake/SKILL.md`: (a) in the greenfield note inside the journey-inventory collector bullet ("Greenfield repos skip this collector: the templates stay placeholder and the init interview asks the owner."), extend it:

```markdown
  Greenfield repos skip the repo-mining half — but when any
  `mcp__claude-design__*` tool is present and `.factory/config.json` sets
  `designsync_project` (see the capabilities skill's references/designsync.md
  `## Journeys`), pull the linked project's frame/flow structure instead and
  emit inventory entries from screen sequences, each cited
  `(source: claude-design <project>/<file>)` with `(assumption)`-tagged
  criticality and `status: inventory` — frames are hypotheses the init
  interview puts in front of the owner. Otherwise the templates stay
  placeholder and the interview asks unaided.
```

(b) In the skill's finish/exit section, add one sentence: `When the DesignSync capability is present and the journey inventory was seeded or changed, regenerate the linked project's factory-journeys.html map per references/designsync.md ## Journeys — best-effort, never blocking, one proxy spend event.`

- [ ] **Step 3: GREEN → FULL suite → commit** `feat(designsync): journeys section — greenfield frame-pull + map push at intake`.

---

### Task 2: spec + escape push points, design-gate annotations

**Files:**
- Modify: `skills/factory-spec/SKILL.md`, `commands/escape.md`, `skills/factory-design/SKILL.md`
- Test: `tests/test_plugin_structure.py`

- [ ] **Step 1: failing pins**

```python
    def test_spec_and_escape_push_journey_map(self):
        spec = (ROOT / "skills/factory-spec/SKILL.md").read_text()
        self.assertIn("factory-journeys.html", spec)
        esc = (ROOT / "commands/escape.md").read_text()
        self.assertIn("factory-journeys.html", esc)

    def test_design_gate_journey_annotations(self):
        text = (ROOT / "skills/factory-design/SKILL.md").read_text()
        self.assertIn("impact.json", text)
        self.assertIn("journey node", text)
        self.assertIn("still-draft contract", text)
        self.assertIn("never an approved contract", text)
```

Run → FAIL.

- [ ] **Step 2: edits.** Read each file first.

1. `skills/factory-spec/SKILL.md`, end of duty 1 (Map) in the Journey impact section, append: `When any mcp__claude-design__* tool is present and designsync_project is configured, regenerate the linked project's factory-journeys.html map after registering a journey or drafting a contract (references/designsync.md ## Journeys) — best-effort, never blocking, one proxy spend event.`
2. `commands/escape.md`, after the promotion sentence, append: `After a contract: promotion, if any mcp__claude-design__* tool is present and designsync_project is configured, regenerate the linked project's factory-journeys.html map (references/designsync.md ## Journeys) — best-effort, never blocking.`
3. `skills/factory-design/SKILL.md` — two additions, placed by reading the existing DesignSync push prose (the options push and the chosen-direction push): (a) where mockup options are pushed to the linked project, add: `Annotate each pushed option with the journey nodes its screens serve, read from the item's impact.json (e.g. "J-004/N3 — invitation accepted"); the chosen-direction note carries the same node mapping.` (b) after the choice-recording/entry-check prose (where the recorded pick advances the item), add: `With a recorded pick, refresh the touched nodes' "what the customer expects" text in any affected still-draft contract, citing the chosen option — never an approved contract (those amend only through the council-judgement firewall), and never blocking the advance to plan.`

- [ ] **Step 3: GREEN → FULL suite → commit** `feat(designsync): journey-map pushes at spec/escape + node-annotated design gate`.

---

### Task 3: CHANGELOG 0.9.0 + version bump

**Files:**
- Modify: `CHANGELOG.md`, `.claude-plugin/plugin.json`

- [ ] **Step 1:** `[0.9.0]` dated entry, house style, one bold-titled paragraph covering the three seams + the doctrine inheritance (interactive-only, degrade-never-block, canonical-repo) + "no engine changes"; Suite line with the real count (run the suite). Bump plugin.json to `0.9.0`.
- [ ] **Step 2: FULL suite → commit** `docs: v0.9.0 — designsync journeys (changelog, version bump)`.

---

## Plan self-review notes

- Spec Decisions 2/3/4 map to T1(push@intake, pull), T2(push@spec/escape, annotations, draft refresh), doctrine statements pinned in T1's reference section; Decision 5 enforced by touching neither assure surface.
- Pins quote strings that the prescribed prose actually contains, on single lines.
