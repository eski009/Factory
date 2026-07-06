# Factory Research Stage (Persona & Market) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an initiation research stage (`factory-research`) that runs the council outward to seed a cited persona + market read behind the existing brain hard gate, then reasoned against downstream.

**Architecture:** One thin engine addition — a `research.depth` config knob — plus two new brain-surface templates (`personas.md`, `market.md`) that `init()` already auto-scaffolds. Everything else is prose reusing `council-review`, the brain, the hard gate, and the capability layer: a new `factory-research` skill orchestrates gather → council **research mode** → seed the two surfaces → existing hard gate; `factory-init` calls it; the persona surfaces are added to `council-review`'s seed so every downstream triage/review reasons against them.

**Tech Stack:** Python 3.11+ stdlib (engine + tests, `unittest`); plugin prose (skills / commands / templates, Markdown).

## Global Constraints

- Engine: stdlib only; deterministic; configs are JSON Schema **draft-07 subset** (no `$ref`/`oneOf`); every schema object keeps `additionalProperties: false`.
- Run tests from repo root: `python3 -m unittest discover -s tests` (whole suite) — **NOT pytest** (not installed). Single test: `python3 -m unittest tests.<module>.<Class>.<test> -v`.
- Skills: open with the CLI-shorthand preamble; frontmatter has `name: <dir>` and `description: Use when …`; keep each skill ≤150 lines.
- Evidence discipline (personas/market): every claim is cited `(source: …)` or marked `(assumption)`; anything unsourced goes to `open-questions.md`; confidence is proportional to evidence.
- The intake hard-gate sentence is reproduced **verbatim** and never weakened: `A human reviews the seeded brain before the first council run treats it as ground truth — say so when you finish.`
- Commit after every task; `feat:` / `test:` / `docs:` prefixes. Work happens on the `factory-phase8` branch (already created; the spec is committed there).

---

### Task 1: Engine — `research.depth` config knob

**Files:**
- Modify: `schemas/config.schema.json` (add a `research` object property)
- Modify: `scripts/factory/lib/initrepo.py:20` (`DEFAULT_CONFIG`)
- Test: `tests/test_initrepo.py` (three new cases in `InitTest`)

**Interfaces:**
- Consumes: `initrepo.validate_tree(repo)` (existing) validates `config.json` against `schemas/config.schema.json`.
- Produces: a valid `config.json` may carry `research: {"depth": "inputs-only"|"web"|"deep"}`; `initrepo.DEFAULT_CONFIG` includes `"research": {"depth": "web"}`, so fresh repos carry it. Later tasks/skills read `config.research.depth`.

- [ ] **Step 1: Write the failing tests.** Add these three methods to the `InitTest` class in `tests/test_initrepo.py` (it already imports `json`, `initrepo`):

```python
    def test_default_config_has_research_depth_web(self):
        initrepo.init(self.repo, product="demo")
        config = json.loads((self.repo / ".factory/config.json").read_text())
        self.assertEqual(config["research"], {"depth": "web"})

    def test_validate_accepts_valid_research_depth(self):
        initrepo.init(self.repo)
        cfg = self.repo / ".factory/config.json"
        data = json.loads(cfg.read_text())
        data["research"] = {"depth": "deep"}
        cfg.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_validate_rejects_bad_research_depth(self):
        initrepo.init(self.repo)
        cfg = self.repo / ".factory/config.json"
        data = json.loads(cfg.read_text())
        data["research"] = {"depth": "exhaustive"}
        cfg.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("research" in e for e in errors))
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `python3 -m unittest tests.test_initrepo.InitTest.test_default_config_has_research_depth_web tests.test_initrepo.InitTest.test_validate_rejects_bad_research_depth -v`
Expected: FAIL — `test_default_config_has_research_depth_web` KeyErrors on `config["research"]`; `test_validate_rejects_bad_research_depth` fails because `research` is currently rejected as an unexpected property (so the error text is `unexpected property`, not one mentioning `research`'s enum) — actually it will *pass* accidentally on the `"research" in e` substring, so rely primarily on the first and third: `test_validate_accepts_valid_research_depth` will FAIL with `config.research: unexpected property`.

- [ ] **Step 3: Add the `research` property to the schema.** In `schemas/config.schema.json`, inside `"properties"`, add this entry after the `"autopilot"` block (keep valid JSON — add a comma after the `autopilot` object):

```json
    "research": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "depth": {"type": "string", "enum": ["inputs-only", "web", "deep"]}
      }
    }
```

- [ ] **Step 4: Add the default.** In `scripts/factory/lib/initrepo.py`, change line 20:

```python
DEFAULT_CONFIG = {"version": 1, "merge": "auto", "gates": ["design"],
                  "research": {"depth": "web"}}
```

- [ ] **Step 5: Run the three tests to verify they pass.**

Run: `python3 -m unittest tests.test_initrepo.InitTest.test_default_config_has_research_depth_web tests.test_initrepo.InitTest.test_validate_accepts_valid_research_depth tests.test_initrepo.InitTest.test_validate_rejects_bad_research_depth -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the full suite** to confirm no regression (e.g. `doctor`, existing init/validate tests).

Run: `python3 -m unittest discover -s tests`
Expected: OK, all tests pass.

- [ ] **Step 7: Commit.**

```bash
git add schemas/config.schema.json scripts/factory/lib/initrepo.py tests/test_initrepo.py
git commit -m "feat: research.depth config knob (inputs-only|web|deep, default web)"
```

---

### Task 2: Templates — `personas.md` + `market.md` brain surfaces

**Files:**
- Create: `templates/docs-factory/brain/personas.md`
- Create: `templates/docs-factory/brain/market.md`
- Test: `tests/test_initrepo.py` (one new case in `InitTest`)

**Interfaces:**
- Consumes: `initrepo.init()` copies every file under `templates/docs-factory/` into `docs/factory/` via `rglob` (initrepo.py:49-56) — no engine change needed; the two new files scaffold automatically.
- Produces: `docs/factory/brain/personas.md` and `docs/factory/brain/market.md` exist after `init`.

- [ ] **Step 1: Write the failing test.** Add to `InitTest` in `tests/test_initrepo.py`:

```python
    def test_init_scaffolds_personas_and_market(self):
        initrepo.init(self.repo)
        self.assertTrue((self.repo / "docs/factory/brain/personas.md").exists())
        self.assertTrue((self.repo / "docs/factory/brain/market.md").exists())
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `python3 -m unittest tests.test_initrepo.InitTest.test_init_scaffolds_personas_and_market -v`
Expected: FAIL — the two files don't exist yet.

- [ ] **Step 3: Create `templates/docs-factory/brain/personas.md`** (mirror the `_Not yet written._` placeholder convention of the sibling brain templates):

```markdown
# Personas

_Seeded by `factory-research`. Every claim is cited `(source: …)` or marked `(assumption)`; unsourced traits belong in `open-questions.md`, not here._

## Primary persona

- **Label:** _Not yet written._
- **Summary:** _Not yet written._
- **Context:** _Not yet written._
- **Goals:** _Not yet written._
- **Jobs-to-be-done:** _Not yet written._
- **Pains:** _Not yet written._
- **Behaviors / drivers:** _Not yet written._
- **Voice:** _Not yet written._
- **Not for:** _Not yet written._
- **Confidence & assumptions:** _Not yet written._
```

- [ ] **Step 4: Create `templates/docs-factory/brain/market.md`:**

```markdown
# Market

_Seeded by `factory-research`. Every claim is cited `(source: …)` or marked `(assumption)`; unsourced findings belong in `open-questions.md`._

- **Category:** _Not yet written._
- **Competitors:** _Not yet written._
- **Table-stakes / conventions:** _Not yet written._
- **Gaps & differentiation:** _Not yet written._
- **Positioning notes:** _Not yet written._
- **Assumptions:** _Not yet written._
```

- [ ] **Step 5: Run the test + the idempotency test** (adding templates must not break "second init returns `[]`").

Run: `python3 -m unittest tests.test_initrepo.InitTest.test_init_scaffolds_personas_and_market tests.test_initrepo.InitTest.test_init_is_idempotent_and_never_clobbers -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the full suite.**

Run: `python3 -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 7: Commit.**

```bash
git add templates/docs-factory/brain/personas.md templates/docs-factory/brain/market.md tests/test_initrepo.py
git commit -m "feat: personas.md + market.md brain-surface templates"
```

---

### Task 3: `council-review` research mode + persona seed surfaces

**Files:**
- Modify: `skills/council-review/SKILL.md` (step 1 seed variants; step 2 seat note)
- Test: `tests/test_plugin_coherence.py` (one new case)

**Interfaces:**
- Consumes: the review-root mechanism already in `council-review` step 1 (default `items/<id>/reviews/`, caller may supply another root).
- Produces: a documented **research mode** (review root `.factory/runs/research/`, outward-facing seats) that `factory-research` (Task 4) invokes; `personas`/`market` added to the triage and review seeds (the downstream "reasoned-against" hook).

- [ ] **Step 1: Write the failing coherence test.** Add to `TestPluginCoherence` in `tests/test_plugin_coherence.py`:

```python
    def test_council_review_seed_consumes_persona_surfaces(self):
        # the persona/market surfaces factory-research writes must be pulled
        # into council-review's seed (the downstream reasoned-against hook),
        # and research mode must be documented.
        text = read(ROOT / "skills/council-review/SKILL.md")
        self.assertIn("personas", text)
        self.assertIn("market", text)
        self.assertIn("research mode", text.lower())
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `python3 -m unittest tests.test_plugin_coherence.TestPluginCoherence.test_council_review_seed_consumes_persona_surfaces -v`
Expected: FAIL — none of `personas` / `market` / `research mode` are present yet.

- [ ] **Step 3: Replace step 1 of `skills/council-review/SKILL.md`.** Find this block:

```
1. **Seed context.** Every artifact below lives under a **review root**: `items/<id>/reviews/` for a single item (the default), or a caller-supplied root such as `.factory/runs/roadmap/` when no item exists yet (batch triage). Below, `reviews/` denotes that root. Write `reviews/seed-context.md`:
   - Triage mode (single item): the item body + relevant brain surfaces (roadmap, open-questions, decisions, constraints).
   - Triage mode (batch, e.g. from factory-roadmap): the full candidate list — one block per candidate (title, provisional kind, cited PRD section) — plus the same brain surfaces. The council ranks the candidates relative to each other in this one pass.
   - Review mode: a diff summary + the item's spec.md.
```

Replace it with:

```
1. **Seed context.** Every artifact below lives under a **review root**: `items/<id>/reviews/` for a single item (the default), or a caller-supplied root such as `.factory/runs/roadmap/` (batch triage) or `.factory/runs/research/` (initiation research) when no item exists yet. Below, `reviews/` denotes that root. Write `reviews/seed-context.md`:
   - Triage mode (single item): the item body + relevant brain surfaces (roadmap, open-questions, decisions, constraints, personas, market).
   - Triage mode (batch, e.g. from factory-roadmap): the full candidate list — one block per candidate (title, provisional kind, cited PRD section) — plus the same brain surfaces. The council ranks the candidates relative to each other in this one pass.
   - Research mode (initiation, e.g. from factory-research): the research seed — the intake-mined surfaces (constraints, design-system, users), the PRD/design file if provided, and the repo's outward surface (README, routes) — under review root `.factory/runs/research/`. Only the outward-facing seats are dispatched (see step 2); each researches its lens (web where available, inputs-only otherwise), every claim cited or marked UNSOURCED. Synthesis drafts the persona(s) + market read.
   - Review mode: a diff summary + the item's spec.md + the persona surfaces (personas.md, market.md).
```

- [ ] **Step 4: Add the research-mode seat note to step 2.** In the same file, find:

```
as parallel Task subagent calls in one message — the degraded baseline; see the `capabilities` skill for fan-out upgrades.
```

Replace it with:

```
as parallel Task subagent calls in one message — the degraded baseline; see the `capabilities` skill for fan-out upgrades. (In **research mode** only the four outward-facing seats are dispatched: `agents/council-customer.md`, `council-commercial.md`, `council-product.md`, `council-ui-taste.md`.)
```

- [ ] **Step 5: Run the coherence test to verify it passes.**

Run: `python3 -m unittest tests.test_plugin_coherence.TestPluginCoherence.test_council_review_seed_consumes_persona_surfaces -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite** (the `test_every_referenced_agent_exists` coherence guard checks the four `agents/council-*.md` you just referenced — they all already exist).

Run: `python3 -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 7: Commit.**

```bash
git add skills/council-review/SKILL.md tests/test_plugin_coherence.py
git commit -m "feat: council-review research mode; persona surfaces in triage/review seeds"
```

---

### Task 4: `factory-research` skill + `/factory:research` command

**Files:**
- Create: `skills/factory-research/SKILL.md`
- Create: `commands/research.md`
- Test: `tests/test_plugin_structure.py` (update expected-commands list; two new cases)

**Interfaces:**
- Consumes: `config.research.depth` (Task 1); `personas.md`/`market.md` surfaces (Task 2); `council-review` research mode (Task 3).
- Produces: a `factory-research` skill invoked by `commands/research.md` and (Task 5) by `factory-init`.

- [ ] **Step 1: Write the failing structural tests.** In `tests/test_plugin_structure.py`:

(a) update the expected-commands assertion in `test_commands_have_frontmatter` — the sorted list gains `"research"` (it sorts before `"roadmap"`):

```python
        self.assertEqual([p.stem for p in commands],
                         ["add", "autopilot", "init", "packet", "research", "roadmap", "run", "status"])
```

(b) add two methods to `TestPluginStructure`:

```python
    def test_research_command_names_its_skill(self):
        cmd = ROOT / "commands/research.md"
        self.assertTrue(cmd.exists())
        text = cmd.read_text()
        self.assertRegex(text, FRONTMATTER, str(cmd))
        self.assertIn("factory-research", text)

    def test_research_skill_covers_persona_market_depth_and_gate(self):
        skill = ROOT / "skills/factory-research/SKILL.md"
        self.assertTrue(skill.exists())
        text = skill.read_text()
        self.assertRegex(text, FRONTMATTER, str(skill))
        self.assertIn("personas.md", text)
        self.assertIn("market.md", text)
        self.assertIn("research.depth", text)
        self.assertIn("research mode", text.lower())
        self.assertIn(
            "A human reviews the seeded brain before the first council run "
            "treats it as ground truth", text)
```

- [ ] **Step 2: Run the new tests to verify they fail.**

Run: `python3 -m unittest tests.test_plugin_structure.TestPluginStructure.test_commands_have_frontmatter tests.test_plugin_structure.TestPluginStructure.test_research_command_names_its_skill tests.test_plugin_structure.TestPluginStructure.test_research_skill_covers_persona_market_depth_and_gate -v`
Expected: FAIL — command/skill files don't exist and the expected-commands list no longer matches the filesystem.

- [ ] **Step 3: Create `skills/factory-research/SKILL.md`** (≤150 lines):

```markdown
---
name: factory-research
description: Use at project initiation to research the product, market, and user and seed a cited persona - runs the council outward, evidence only, behind the hard gate
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

## Purpose

Seed two product-brain surfaces the council reasons from — `docs/factory/brain/personas.md` (who the product is for) and `docs/factory/brain/market.md` (where it sits) — by researching the product, its market, and its users. Runs once at initiation, a sibling of `factory-intake`/`factory-roadmap`. A persona is where products invent a confident fictional user; here it is always a **cited hypothesis** the human reviews at the brain hard gate, never authored fact.

## Inputs

`$ARGUMENTS` may name a PRD path and/or a design-file path (greenfield), plus an optional `--depth inputs-only|web|deep` override. A named-but-missing file is just absent context, not a refusal. With no arguments, research the target repo as-is (brownfield), building on whatever `factory-intake` already mined.

## 1. Depth

Read `research.depth` from `.factory/config.json` (`inputs-only | web | deep`, default `web`); a `--depth` argument overrides it for this run.

- `inputs-only` — reason only from the PRD/repo already on hand; no web.
- `web` (default) — research the open web (competitors, category conventions, real user voice in reviews/forums), citing URLs; produce one primary persona + a market read.
- `deep` — `web` plus a persona set (primary + secondaries) and a fuller competitive teardown; fan out the gather step per competitor/segment (see the `capabilities` skill).

If the depth needs the web and this run has no web access, **degrade to `inputs-only`** and add an entry to `docs/factory/brain/open-questions.md` naming the gap ("market/user web research not run — no web access this run; re-run with web for deeper grounding"). A missing capability degrades output, never blocks the run.

## 2. Assemble the research seed

Gather the grounding: the intake-mined surfaces (`constraints.md`, `design-system.md`, `users.md`), the PRD/design file if given, and the repo's outward surface (`README`, routes/screens). This is the seed for the council.

## 3. Council research mode

Run the `council-review` skill in **research mode** with review root `.factory/runs/research/` and the seed from step 2. Research mode dispatches only the outward-facing seats — `customer` (jobs-to-be-done, real user pains/voice), `commercial` (market, competitors, positioning), `product` (segments, use cases, differentiation), `ui-taste` (category design conventions). Each researches its lens (web at `web`/`deep`, inputs-only otherwise); every claim carries a citation or is marked UNSOURCED. The synthesis drafts the persona(s) + market read into `.factory/runs/research/synthesis.md`.

## 4. Seed the surfaces (evidence only)

From the synthesis, write:

- `docs/factory/brain/personas.md` — the primary persona (a set at `deep`): Label, Summary, Context, Goals, Jobs-to-be-done, Pains, Behaviors/drivers, Voice (cited quotes), Not-for, Confidence & assumptions. Every claim carries `(source: <url-or-path>)` or `(assumption)`.
- `docs/factory/brain/market.md` — category, competitors (cited), table-stakes/conventions, gaps & differentiation, positioning, assumptions.

Same discipline as intake: nothing invented into a surface; every unsourced trait or open unknown is mirrored into `open-questions.md`; confidence is proportional to evidence — a thin honest persona is the right output when sources are thin. `users.md` stays the broader user-notes surface; `personas.md` is the sharpened, addressable persona.

This is a *seed*, exactly like intake seeding `users.md`: the bid→judge firewall governs ongoing brain changes after the gate, not this initial write.

## 5. Idempotency

On a re-run, if `personas.md`/`market.md` already carry real content, refresh and augment with new citations rather than clobbering; report what changed.

## Hard gate

Always say this to the user when you finish, verbatim: "A human reviews the seeded brain before the first council run treats it as ground truth — say so when you finish." Present `personas.md`, `market.md`, and the intake surfaces for review, then stop. Running unattended (autopilot), write a packet summarizing the seeded research and stop — never self-approve, never proceed to triage.

## Exit

Report the persona label(s), competitor count, and number of assumptions logged, and remind that human review precedes `/factory:run` or `/factory:roadmap`.
```

- [ ] **Step 4: Create `commands/research.md`:**

```markdown
---
description: Research the product, market, and user and seed a cited persona - $ARGUMENTS = [<prd-path>] [<design-path>] [--depth inputs-only|web|deep]
---
Parse $ARGUMENTS into an optional PRD path, an optional design-file path, and an
optional --depth override. Invoke the factory-research skill with them. Follow it
exactly; it owns depth handling, the council research mode, seeding
docs/factory/brain/personas.md and market.md, and stating the hard gate.
```

- [ ] **Step 5: Run the three structural tests to verify they pass.**

Run: `python3 -m unittest tests.test_plugin_structure.TestPluginStructure.test_commands_have_frontmatter tests.test_plugin_structure.TestPluginStructure.test_research_command_names_its_skill tests.test_plugin_structure.TestPluginStructure.test_research_skill_covers_persona_market_depth_and_gate -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the full suite** (the generic `test_every_command_names_a_real_skill_or_cli` coherence guard now also covers `research.md`, which names `factory-research`).

Run: `python3 -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 7: Commit.**

```bash
git add skills/factory-research/SKILL.md commands/research.md tests/test_plugin_structure.py
git commit -m "feat: factory-research skill and /factory:research command"
```

---

### Task 5: Wire research into init + downstream persona checks

**Files:**
- Modify: `commands/init.md` (invoke `factory-research` after intake)
- Modify: `skills/factory-spec/SKILL.md` (read `personas.md`; check the persona)
- Modify: `skills/factory-design/SKILL.md` (options must serve the persona)
- Test: `tests/test_plugin_structure.py` (two new cases)

**Interfaces:**
- Consumes: the `factory-research` skill (Task 4) and `personas.md` (Task 2).
- Produces: `factory-init` runs research before the hard gate; `factory-spec`/`factory-design` reason against the persona.

- [ ] **Step 1: Write the failing structural tests.** Add to `TestPluginStructure` in `tests/test_plugin_structure.py`:

```python
    def test_init_command_invokes_research(self):
        text = (ROOT / "commands/init.md").read_text()
        self.assertIn("factory-research", text)

    def test_spec_and_design_reason_against_persona(self):
        self.assertIn("personas.md", (ROOT / "skills/factory-spec/SKILL.md").read_text())
        self.assertIn("personas.md", (ROOT / "skills/factory-design/SKILL.md").read_text())
```

- [ ] **Step 2: Run them to verify they fail.**

Run: `python3 -m unittest tests.test_plugin_structure.TestPluginStructure.test_init_command_invokes_research tests.test_plugin_structure.TestPluginStructure.test_spec_and_design_reason_against_persona -v`
Expected: FAIL — none of the three files mention `factory-research` / `personas.md` yet.

- [ ] **Step 3: Wire research into `commands/init.md`.** Replace:

```
Show the created paths. Then invoke the factory-intake skill to seed
docs/factory/brain/ from real sources ($ARGUMENTS names the product if given).
If the brain templates are still placeholders, tell the user triage will treat
empty surfaces as open questions.
```

with:

```
Show the created paths. Then invoke the factory-intake skill to seed
docs/factory/brain/ from real sources ($ARGUMENTS names the product if given).
Then invoke the factory-research skill (persona + market research, at the
configured research.depth) so personas.md and market.md are seeded before the
human reviews the brain. If the brain templates are still placeholders, tell the
user triage will treat empty surfaces as open questions.
```

- [ ] **Step 4: Add the persona to `skills/factory-spec/SKILL.md`.** In the `## Read first` section, replace:

```
Read the item body, `items/<id>/triage.md`, and the brain surfaces: `docs/factory/brain/vision.md`, `users.md`, `constraints.md`, and (for `ui`/`mixed` items) `design-system.md`.
```

with:

```
Read the item body, `items/<id>/triage.md`, and the brain surfaces: `docs/factory/brain/vision.md`, `users.md`, `personas.md`, `constraints.md`, and (for `ui`/`mixed` items) `design-system.md`.
```

Then in step 2 of "The autonomous substitute for brainstorming", replace:

```
2. **Answer each question from the brain.** For every question, check vision.md, users.md, constraints.md, and design-system.md for a real answer.
```

with:

```
2. **Answer each question from the brain.** For every question, check vision.md, users.md, personas.md, constraints.md, and design-system.md for a real answer — including whether the choice serves the primary persona.
```

- [ ] **Step 5: Add the persona to `skills/factory-design/SKILL.md`.** In "## The options page", replace:

```
- Each option renders the item's actual UI surface from `spec.md` — real content and controls for this item, not lorem-ipsum or generic placeholder abstractions.
```

with:

```
- Each option renders the item's actual UI surface from `spec.md` — real content and controls for this item, not lorem-ipsum or generic placeholder abstractions — and serves the primary persona in `docs/factory/brain/personas.md` (their goals and context, not a generic user).
```

- [ ] **Step 6: Run the two tests to verify they pass.**

Run: `python3 -m unittest tests.test_plugin_structure.TestPluginStructure.test_init_command_invokes_research tests.test_plugin_structure.TestPluginStructure.test_spec_and_design_reason_against_persona -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Run the full suite** — final green for the whole feature.

Run: `python3 -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 8: Commit.**

```bash
git add commands/init.md skills/factory-spec/SKILL.md skills/factory-design/SKILL.md tests/test_plugin_structure.py
git commit -m "feat: init runs research; spec/design reason against the persona"
```

---

## Plan Self-Review (completed)

- **Spec coverage:** §1 stage/skill/command + both on-ramps → Tasks 4 (skill/command) & 5 (init wiring; greenfield uses the same command). §2 depth knob + degradation → Task 1 (knob) + the degrade prose in Task 4 step 3. §3 council research mode (outward seats, `.factory/runs/research/`) → Task 3. §4 `personas.md`/`market.md` schemas + evidence discipline + hard gate → Tasks 2 (templates) & 4 (seeding prose + verbatim gate). §5 downstream reasoned-against hook → Task 3 (council seeds) + Task 5 (spec/design). §6 engine footprint → Tasks 1–2. §7 testing → the structural/coherence/engine tests distributed across Tasks 1–5. Non-goals untouched (no run-ledger, no new subcommands, no auto re-research).
- **Placeholder scan:** every code/prose step carries the exact content; no TBD/"similar to"/"add error handling".
- **Type/name consistency:** `research.depth` enum values (`inputs-only|web|deep`) are identical in the schema (Task 1), `DEFAULT_CONFIG` (Task 1), the skill (Task 4), and the command (Task 4). Surface filenames `personas.md`/`market.md` match across templates (Task 2), council-review seed (Task 3), the skill (Task 4), tests, and spec/design (Task 5). Review root `.factory/runs/research/` matches between council-review (Task 3) and the skill (Task 4). The four research seats (`customer`, `commercial`, `product`, `ui-taste`) match between council-review step 2 (Task 3) and the skill step 3 (Task 4).
- **Ordering:** Task 4's expected-commands test edit and `commands/research.md` creation land in the same task, so `test_commands_have_frontmatter` is never left red across a commit boundary.
```
