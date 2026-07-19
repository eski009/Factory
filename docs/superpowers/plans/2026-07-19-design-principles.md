# Design Principles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `brain/design-principles.md` as a seeded, overridable baseline and wire its three consumers (design generation, polish battery, ui-taste seat) plus interview harvest.

**Architecture:** Prose + one content-bearing template. No engine changes.

**Spec:** `docs/superpowers/specs/2026-07-19-design-principles-design.md` — read it first.

## Global Constraints

- The template ships content-bearing with the `(assumption)`-tagged defaults-not-dogma header; the product-wins rule appears in BOTH the template header and factory-design's wiring.
- Do not disturb pinned sentences (grep tests/test_plugin_structure.py for pins on every file you touch — factory-spec's polish-battery pins, journey-reviewer's discipline pins, interview's pins are all live).
- The battery/reviewer anchors say "where present" — a repo whose owner deleted the file must not break anything.
- FULL suite before commit; commit ends with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1 (single task): template + five wirings + pins

**Files:**
- Create: `templates/docs-factory/brain/design-principles.md`
- Modify: `skills/factory-design/SKILL.md`, `skills/factory-spec/SKILL.md`, `agents/journey-reviewer.md`, `agents/council-ui-taste.md`, `skills/factory-interview/SKILL.md`
- Test: `tests/test_plugin_structure.py`

- [ ] **Step 1: failing pins**

```python
    def test_design_principles_template(self):
        t = ROOT / "templates/docs-factory/brain/design-principles.md"
        self.assertTrue(t.exists())
        text = t.read_text()
        self.assertIn("Defaults, not dogma", text)
        self.assertIn("(assumption)", text)
        self.assertIn("one job per screen", text)
        self.assertIn("Progressive disclosure", text)
        self.assertIn("Error prevention over error messages", text)
        self.assertIn("Accessible by default", text)
        self.assertIn("the product wins", text)

    def test_design_principles_consumers_wired(self):
        design = (ROOT / "skills/factory-design/SKILL.md").read_text()
        self.assertIn("design-principles.md", design)
        spec = (ROOT / "skills/factory-spec/SKILL.md").read_text()
        self.assertIn("design-principles.md", spec)
        reviewer = (ROOT / "agents/journey-reviewer.md").read_text()
        self.assertIn("design-principles.md", reviewer)
        seat = (ROOT / "agents/council-ui-taste.md").read_text()
        self.assertIn("design-principles.md", seat)
        interview = (ROOT / "skills/factory-interview/SKILL.md").read_text()
        self.assertIn("design-principles.md", interview)
```

Run `python3 -m unittest tests.test_plugin_structure -v` → both FAIL.

- [ ] **Step 2: create the template**

`templates/docs-factory/brain/design-principles.md`:

```markdown
# Design principles

> **Defaults, not dogma (assumption).** These ship with the factory as the
> baseline the design stage generates against, the polish battery judges
> against, and the ui-taste seat cites until this product's own taste
> accumulates past them. Strike or amend any of them for this product —
> where a principle conflicts with this product's `design-system.md` or a
> recorded decision, the product wins. The init interview asks you to
> confirm or strike these; an edit here is a product decision like any
> other brain claim.

- **KISS — one job per screen.** Every screen has one primary action; every
  other element earns its place by serving it. If you cannot name the
  screen's job in one sentence, split the screen.
- **Progressive disclosure.** Complexity is available, never ambient:
  advanced options live behind an explicit step; defaults carry the common
  case.
- **Visual hierarchy.** The eye lands where the journey needs it next —
  size, weight, contrast, and position agree about what matters most.
- **Consistency, twice.** Internal: the same intent always looks and acts
  the same across screens. Platform: respect the conventions of the web or
  OS the customer already knows.
- **Feedback and visible state.** Every action is acknowledged where it
  happened; the system never leaves the customer guessing whether
  something worked or is still working.
- **Error prevention over error messages.** Make the wrong action hard to
  take before making its failure polite.
- **Accessible by default.** Real labels, sane focus order, sufficient
  contrast, announced state — semantics first, pixels second.
```

- [ ] **Step 3: the five wirings** (read each file for anchors; keep pinned strings intact)

1. `skills/factory-design/SKILL.md` — add `docs/factory/brain/design-principles.md` to its read-first/brain inputs, and one sentence where directions are generated: `Generate every direction against brain/design-principles.md where present — the defaults-not-dogma baseline; where a principle conflicts with this product's design-system.md or a recorded decision, the product wins.`
2. `skills/factory-spec/SKILL.md` — in the polish-battery consistency question's parenthetical, extend `against \`design-system.md\` where seeded` to `against \`design-system.md\` and \`brain/design-principles.md\` where present`.
3. `agents/journey-reviewer.md` — in step 9's bar text, after "name what such a customer would notice or distrust", insert: `judging against \`docs/factory/brain/design-principles.md\` where present (a struck principle binds you too — never cite one the product removed),`.
4. `agents/council-ui-taste.md` — where it reads design-system.md (find the anchor), add design-principles.md alongside, with: `cite principles from it in bids until this product's own accumulated taste supersedes them; the product's recorded choices always win.` (Adapt phrasing to the file's voice; the pin only requires the filename.)
5. `skills/factory-interview/SKILL.md` — harvest source 2: extend the surface enumeration with `\`docs/factory/brain/design-principles.md\` (the defaults-not-dogma header — one confirm-or-strike question for the set, not one per principle)`.

- [ ] **Step 4: GREEN → FULL suite → commit** `feat(brain): design-principles baseline — seeded defaults, three consumers wired` (+ trailer).

---

## Plan self-review notes

- Decision 1 → template + interview wiring; Decision 2 → wirings 1-3 + 4; Decision 3 → template header + wiring 1 + reviewer's struck-principle clause. Pins cover template content and all five consumers.
- The interview asks ONE question for the set (the header carries the single (assumption) tag) — avoids seven nag questions at init.
