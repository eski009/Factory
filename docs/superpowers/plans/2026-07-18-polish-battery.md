# Polish Battery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seed a default per-node polish battery into journey contracts, make the reviewer answer it against a written world-class bar, and route findings: objective craft → fail; subjective → packet `## Polish` advisories the human adjudicates.

**Architecture:** Prose-only, three files + pins. No engine changes; exit semantics extended only by a non-blocking advisory channel (packet prose).

**Spec:** `docs/superpowers/specs/2026-07-18-polish-battery-design.md` — read it first.

## Global Constraints

- Advisories NEVER fail the gate, NEVER park the item, and are produced every run (gated or not) into the assure packet's `## Polish` section.
- Objective craft defects (clipping/overflow, broken images, unstyled error/empty states, placeholder/lorem content, layout collapse at a declared viewport) are ordinary `fail` verdicts — name them as examples where fails are described, do not invent a new verdict kind.
- The four default questions are seeded by factory-spec's contract drafting for EVERY touched node; authors add, never remove.
- `ambiguity` semantics unchanged (blocks-the-walk judgement calls still park).
- Do not disturb any pinned sentence (grep tests/test_plugin_structure.py for existing factory-assure/journey-reviewer/factory-spec pins before editing).
- FULL suite before commit; commit ends with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1 (single task): all three prose surfaces + pins

**Files:**
- Modify: `skills/factory-spec/SKILL.md`, `agents/journey-reviewer.md`, `skills/factory-assure/SKILL.md`
- Test: `tests/test_plugin_structure.py`

- [ ] **Step 1: failing pins**

```python
    def test_contract_drafting_seeds_polish_battery(self):
        text = (ROOT / "skills/factory-spec/SKILL.md").read_text()
        self.assertIn("polish battery", text)
        self.assertIn("not needed for what the customer is doing", text)
        self.assertIn("read as the same product", text)
        self.assertIn("trust this screen", text)
        self.assertIn("add more, never fewer", text)

    def test_reviewer_bar_and_advisory_split(self):
        text = (ROOT / "agents/journey-reviewer.md").read_text()
        self.assertIn("demanding first-time customer of a world-class product", text)
        self.assertIn("judgement question", text)
        self.assertIn("advisory", text)
        self.assertIn("never soften", text)

    def test_assure_packet_polish_section(self):
        text = (ROOT / "skills/factory-assure/SKILL.md").read_text()
        self.assertIn("## Polish", text)
        self.assertIn("never fail the gate and never park the item", text)
        self.assertIn("promote", text)
```

Run `python3 -m unittest tests.test_plugin_structure -v` → all three FAIL.

- [ ] **Step 2: edits** (read each file first; place by its structure)

1. `skills/factory-spec/SKILL.md`, in duty 1 (Map) where the minimal draft contract's contents are listed (the sentence naming touched nodes, oracles, Run & fixtures, interruption/recovery), extend the list with:

```markdown
   and a default **polish battery** of AI judgement questions seeded on every
   touched node — density: "what on this screen is not needed for what the
   customer is doing at this node?"; craft: "what would a first-time customer
   visually notice as unfinished?"; consistency: "does this screen read as the
   same product as the previous node (type, color, spacing rhythm — against
   `design-system.md` where seeded)?"; trust: "would a first-time customer
   trust this screen with their data or money?". Contract authors may add
   more, never fewer.
```

2. `agents/journey-reviewer.md`: (a) in the walk section, after step 8, add:

```markdown
9. Answer every AI judgement question the contract carries for this node.
   Your bar is a demanding first-time customer of a world-class product:
   name what such a customer would notice or distrust, and never soften
   because the product "mostly works." An objective craft defect anyone
   would see — clipping or overflow, broken images, unstyled error or empty
   states, placeholder text, layout collapse at a declared viewport — is a
   **fail**, no contract needed. A nameable but subjective finding is an
   **advisory**: report it with the question it answers; the orchestrator
   collects advisories for the human — they never block, and you never
   resolve taste yourself.
```

   (b) in the Report format paragraph, add `per-node judgement-question answers (advisories)` to the returned-fields list.

3. `skills/factory-assure/SKILL.md`: (a) in the orchestrator/packet section (where the confirmation packet's contents are listed), extend the packet contents with a `## Polish` section:

```markdown
   The packet always carries a `## Polish` section: every advisory the
   reviewers returned (the contract's judgement-question answers), grouped
   by journey and node. Advisories never fail the gate and never park the
   item — they are the world-class punch list the human adjudicates at
   confirmation: ratify one by promoting it (an escape promotion or a
   contract amendment), and it binds the next run; a question the contract
   now settles stops being advisory.
```

   (b) where fail verdicts are described (Failure discipline), extend the objective examples: `(wrong outcome, dead end, material console/network error, or an objective craft defect — clipping, broken imagery, unstyled error/empty states, placeholder content, viewport collapse)`.

- [ ] **Step 3: GREEN → FULL suite → commit** `feat(assure): polish battery — world-class bar, craft fails, packet advisories` (+ trailer).

---

## Plan self-review notes

- Decision 1 → journey-reviewer step 9 + factory-assure failure-discipline extension; Decision 2 → factory-spec seeding; Decision 3 → factory-assure packet section (pins quote the exact never-fail/never-park phrase); Decision 4 → the bar sentence (pinned).
- Pins quote single-line-safe substrings of the prescribed prose.
