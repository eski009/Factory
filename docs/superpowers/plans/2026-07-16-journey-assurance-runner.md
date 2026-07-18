# Journey Assurance — Plan 3: Assurance Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The assure stage's execution layer: the `factory-assure` skill (orchestration, exit semantics, evidence composition), the fresh-context `journey-reviewer` agent, the Browser drive capability row + reference, and dispatch wiring.

**Architecture:** Prose skill + agent + capability reference; the engine (Plan 1) enforces everything these produce. The reviewer gets a structurally clean context (input allowlist); the orchestrating session composes `verdicts.json` and logs events; humans answer parks via the Plan-1 verbs.

**Tech Stack:** Markdown prose. Tests: structural pins (stdlib unittest).

**Spec:** `docs/superpowers/specs/2026-07-15-journey-assurance-design.md` (The assure stage + Decisions 2-4).

## Global Constraints

- The reviewer prompt is composed ONLY from the enumerated input allowlist — persona/brain surfaces, that journey's contract, the item's impact.json, the contract's Run & fixtures instructions — and structurally excludes the implementer transcript, review/verify conclusions, and any "this is complete" framing.
- Exit semantics are three-way and exact: all pass → `factory log ITEM assure.passed` (+ park `waiting-human` for confirmation when `"assure"` ∈ config gates, else `factory advance ITEM ship`); any fail → `factory log ITEM assure.rejected --data '{"round": N}'` + `factory advance ITEM implement` (engine caps at 2); ambiguity/blocker → park `waiting-human` + packet — NEVER a silent pass.
- The skill NEVER runs `factory waive` or `factory confirm` — those are the human's verbs (the factory-choice pattern).
- Browser-borne journeys REQUIRE the Browser drive capability; absent → blocker → park. CLI/API journeys are driven through real commands with typed transcript evidence. Parking is not failing — the capabilities doctrine survives.
- Verdicts per scenario: `pass | fail | ambiguity | blocker`; expectations written to `expectations.md` BEFORE acting; material console errors and unexpected 4xx/5xx are fails unless the contract whitelists them.
- Evidence lands under `.factory/items/<id>/assurance/` exactly as the engine validates it (schemas from Plan 1); the ORCHESTRATOR composes/persists `verdicts.json` and `run-manifest.json`; the reviewer writes ONLY evidence files under `assurance/` (screenshots/, console.ndjson, network.ndjson, transcripts) and nothing else anywhere.
- Tier depth from `factory doctor --json` → tiers → `assure` (`node | affected | full`); reviewer at the most-capable model tier per references/model-tiering.md, a different model from the implementer where the session supports overrides.
- Spend logged per fan-out per the dispatch convention (measured or proxy, never estimated).
- Run the FULL suite before every commit. Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: factory-assure skill + dispatch wiring

**Files:**
- Create: `skills/factory-assure/SKILL.md`
- Modify: `skills/factory-dispatch/SKILL.md` (stage-map row), `tests/test_plugin_coherence.py` (dispatcher regex)
- Test: `tests/test_plugin_structure.py`, `tests/test_plugin_coherence.py`

**Interfaces:**
- Produces: the assure stage's skill, mapped in dispatch (`| assure | factory-assure |` between verify and ship rows); the coherence regex alternation gains `assure`.

- [ ] **Step 1: Write the failing tests**

`tests/test_plugin_structure.py`:

```python
    def test_assure_skill_contract_and_discipline(self):
        skill = ROOT / "skills/factory-assure/SKILL.md"
        self.assertTrue(skill.exists())
        text = skill.read_text()
        self.assertRegex(text, FRONTMATTER, str(skill))
        self.assertIn("never the implementer transcript", text)
        self.assertIn("expectations.md", text)
        self.assertIn("run-manifest.json", text)
        self.assertIn("pass | fail | ambiguity | blocker", text)
        self.assertIn("assure.passed", text)
        self.assertIn("assure.rejected", text)
        self.assertIn("never runs `factory waive` or `factory confirm`", text)
        self.assertIn("Browser drive", text)
        self.assertIn("never a silent pass", text)
        self.assertIn("one fresh journey-reviewer subagent per affected journey", text)
        self.assertIn("agents/journey-reviewer.md", text)
```

`tests/test_plugin_coherence.py` — extend the dispatcher-map regex (edit the existing `test_every_dispatcher_mapped_stage_skill_exists`): change the alternation to `factory-(triage|spec|design|plan|implement|review|verify|assure|ship)` and add below it:

```python
    def test_dispatch_maps_assure_between_verify_and_ship(self):
        dispatch = read(ROOT / "skills/factory-dispatch/SKILL.md")
        self.assertIn("| assure | factory-assure |", dispatch)
        self.assertLess(dispatch.index("| verify | factory-verify |"),
                        dispatch.index("| assure | factory-assure |"))
        self.assertLess(dispatch.index("| assure | factory-assure |"),
                        dispatch.index("| ship | factory-ship |"))
```

Run both test modules → the new tests FAIL (skill missing, row missing).

- [ ] **Step 2: Create `skills/factory-assure/SKILL.md`**

```markdown
---
name: factory-assure
description: Use when a factory item is at stage assure - a fresh-context journey reviewer walks the affected journeys against the running product and the engine-validated evidence decides ship
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

## Contract

- **Entry stage:** `assure` (the engine's gate already required `verify.green`).
- **Artifacts produced:** `items/<id>/assurance/` — `run-manifest.json`, `expectations.md`, `verdicts.json`, evidence files (`screenshots/`, `console.ndjson`, `network.ndjson`, transcripts), `blockers.md` when blocked.
- **Exit:** all scenarios pass → `factory log ITEM assure.passed`, then if `"assure"` is in the config `gates` list, `factory advance ITEM waiting-human --reason "assurance passed - awaiting human confirmation (factory confirm ITEM)"` + `factory packet ITEM`; otherwise `factory advance ITEM ship`. Any objective fail → `factory log ITEM assure.rejected --data '{"round": <n>}'` + `factory advance ITEM implement` (the engine caps rework at 2, then blocked). Ambiguity or blocker → park: `factory advance ITEM waiting-human --reason "<what needs a human>"` + `factory packet ITEM` — never a silent pass, never a self-answered judgement call.

Review asked "is the code sound"; verify asked "do the checks pass"; this stage asks **"can the customer get through it"** — against the running product, in a context that has never seen the implementation.

## Read first

`items/<id>/spec.md` (`## Journey impact`), `items/<id>/assurance/impact.json`, `docs/factory/journeys/graph.json`, and each affected journey's contract under `docs/factory/journeys/contracts/`. Read the item's tier from `factory status --json` and the assure depth from `factory doctor --json` → `tiers` → `assure`: `node` = the changed node plus its immediate transition (bug), `affected` = every affected journey's required scenarios including interruption paths (feature), `full` = affected plus core journeys the item touches, including adjacent journeys where state carries across (epic).

## Dispatch — one fresh journey-reviewer subagent per affected journey

Dispatch `agents/journey-reviewer.md` once per affected journey, sequentially, at the most-capable model tier (references/model-tiering.md) — and on a different model from the one that ran implement when the session supports model overrides. Compose each reviewer's prompt ONLY from this input allowlist:

- `docs/factory/brain/personas.md` and `users.md` (who the customer is)
- that journey's contract (draft or approved — note which)
- the item's `impact.json` (nodes, transitions, new states, required scenarios)
- the contract's Run & fixtures section (exact launch commands, fixture setup, credentials through the contract's fixture mechanisms)

Structurally excluded — never the implementer transcript, never review/verify conclusions or diffs, never any claim that the feature is "complete" or "ready": the reviewer must discover what the product does, not confirm what the pipeline hopes. If a required input is missing (no contract, no Run & fixtures, no fixture credentials), that journey is a **blocker** — record it and park; do not improvise a launch path.

## What the reviewer does (its walk, enforced by its agent file)

For every node in scope it: (1) states what the customer currently knows, (2) predicts what the customer expects next — written to `assurance/expectations.md` BEFORE acting, (3) performs the action, (4) compares expected vs actual, (5) captures screenshot/DOM evidence, (6) inspects console errors, (7) inspects network failures or unexpected requests, (8) records `pass | fail | ambiguity | blocker` per scenario with typed evidence refs. Material console errors and unexpected 4xx/5xx responses are fails unless the journey contract explicitly whitelists them as known noise.

**Surface drivers.** Browser-borne journeys require the **Browser drive** capability (capabilities skill; references/browser-drive.md — Playwright MCP, chrome-devtools MCP, or Claude-in-Chrome, matched behaviorally). Capability absent → the journey is a blocker → park; the parked packet names `factory waive ITEM --reason "..."` as the human's override. CLI/API journeys need no browser: the reviewer runs the real commands a customer or caller would run and captures typed transcript evidence instead of screenshots.

## Orchestrator composes the gate artifacts

The reviewer returns a structured report and writes ONLY evidence files under `items/<id>/assurance/`. This session (the orchestrator) then writes:

- `run-manifest.json` — what was launched and driven, per journey (commands, urls, fixture state, reviewer model).
- `verdicts.json` — per journey, per scenario: verdict, expected, actual, typed evidence refs (`screenshot | dom | console | network | transcript`, paths relative to the item dir). Shape: `schemas/assurance-verdicts.schema.json`; every declared journey and every impact.json scenario must be covered — the ship gate refuses gaps, missing evidence files, and any non-pass verdict.

Then take the Exit branch that matches the verdicts. A draft contract never blocks assurance, but flag it in the packet: "contract is draft — confirm it reflects intent." This skill **never runs `factory waive` or `factory confirm`** — those are the human's verbs, exactly like `factory choice`; an unattended run leaves parked items parked.

## Failure discipline

- **fail** = the product objectively did not meet the contract's expectation at a node (wrong outcome, dead end, material console/network error). Rework: `assure.rejected` + back to implement with the failing scenario named in the log data.
- **ambiguity** = the walk completed but a judgement call the contract doesn't settle remains (is this copy clear enough? is this next action obvious?). Park for the human with the reviewer's question quoted verbatim in the packet.
- **blocker** = the walk could not run (app won't launch, fixture missing, browser capability absent). Record in `assurance/blockers.md`, park. Environment fixed → the stage simply re-runs; blockers are never converted to passes by inspection.

## Spend

Log one spend event per reviewer dispatch batch, per the dispatch convention: `factory log ITEM spend --data '{"provenance":"measured","stage":"assure","source":"factory-assure","dispatches":<n>,"tokens":{"total":<n>}}'` with harness-reported counts, or `"provenance":"proxy"` and no `tokens` key when the harness reports none. Never estimate.
```

- [ ] **Step 3: Add the dispatch row**

In `skills/factory-dispatch/SKILL.md`, in the stage-map table, insert between the verify and ship rows:

```markdown
   | assure | factory-assure |
```

And in `tests/test_plugin_coherence.py`, update the regex in `test_every_dispatcher_mapped_stage_skill_exists` to include `assure` in the alternation.

- [ ] **Step 4: Run the full suite** → green. Commit:

```bash
git add skills/factory-assure/SKILL.md skills/factory-dispatch/SKILL.md tests/test_plugin_structure.py tests/test_plugin_coherence.py
git commit -m "feat(assure): factory-assure skill + dispatch wiring

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: journey-reviewer agent + Browser drive capability

**Files:**
- Create: `agents/journey-reviewer.md`, `skills/capabilities/references/browser-drive.md`
- Modify: `skills/capabilities/SKILL.md` (new row)
- Test: `tests/test_plugin_structure.py`

**Interfaces:**
- Produces: the fresh-context reviewer agent factory-assure dispatches; the Browser drive capability row (probe: behavioral tool family) linked to its reference doc.

- [ ] **Step 1: Write the failing tests**

`tests/test_plugin_structure.py` — extend the existing `test_capability_upgrade_references_exist_and_are_linked` name tuple with `"browser-drive"`, and add:

```python
    def test_journey_reviewer_agent_discipline(self):
        agent = ROOT / "agents/journey-reviewer.md"
        self.assertTrue(agent.exists())
        text = agent.read_text()
        self.assertRegex(text, FRONTMATTER, str(agent))
        self.assertIn("pass | fail | ambiguity | blocker", text)
        self.assertIn("before acting", text.lower())
        self.assertIn("only under `.factory/items/<id>/assurance/`", text)
        self.assertIn("never edit product code", text.lower())
        self.assertIn("not told this feature is complete", text.lower())

    def test_browser_drive_capability_row_and_reference(self):
        skill = (ROOT / "skills/capabilities/SKILL.md").read_text()
        self.assertIn("| Browser drive |", skill)
        self.assertIn("references/browser-drive.md", skill)
        ref = (ROOT / "skills/capabilities/references/browser-drive.md").read_text()
        self.assertIn("navigate, click, type, screenshot, and read console/network", ref)
        self.assertIn("park", ref)
        self.assertIn("silent pass", ref)
        self.assertIn("factory waive", ref)
        self.assertIn("Parking is not failing", ref)
```

Run → FAIL.

- [ ] **Step 2: Create `agents/journey-reviewer.md`**

```markdown
---
name: journey-reviewer
description: Fresh-context journey reviewer - walks one journey contract against the running product and reports node-by-node verdicts with evidence, dispatched by factory-assure
---

You walk ONE customer journey against the RUNNING product, as the customer.
You were dispatched with a deliberately clean context: the persona, the
journey contract, the item's impact map, and run/fixture instructions —
nothing else. You have not seen the implementation, the reviews, or any
claim about readiness; you were not told this feature is complete. Your job
is to discover what the product actually does.

## Ground rules

- Never edit product code, factory state, `item.md`, logs, or any file
  outside your evidence directory. You write only under `.factory/items/<id>/assurance/`
  (screenshots/, console.ndjson, network.ndjson, transcript files) — the
  orchestrator composes verdicts.json from your report.
- Launch the product exactly as the contract's Run & fixtures section says.
  If it does not launch, a fixture is missing, or a credential mechanism is
  absent, STOP and report a blocker — never improvise a different launch
  path, never mark anything passed by code inspection.
- Judge against the contract and the persona, not against generosity: you
  are the customer, not the team.

## The walk — per node in scope

1. State what the customer currently knows (from the journey so far only).
2. Predict what the customer expects next — record it BEFORE acting.
3. Perform the action (browser: the Browser drive tools; cli/api: the real
   command a customer or caller would run).
4. Compare expected vs actual.
5. Capture evidence: browser journeys — screenshot (and DOM where it is the
   evidence) into `assurance/screenshots/`; cli/api journeys — the exact
   command + verbatim output as a transcript file.
6. Inspect the console: material errors are fails unless the contract
   whitelists them as known noise.
7. Inspect network traffic: failures and unexpected requests (wrong host,
   unexpected 4xx/5xx) are fails unless whitelisted.
8. Record the verdict per scenario: pass | fail | ambiguity | blocker.

An expectation mismatch you can point at is a **fail** (say exactly what a
customer expected and what happened instead). A judgement call the contract
does not settle is an **ambiguity** — report the question verbatim, do not
resolve it yourself. Anything that stopped the walk is a **blocker**.

## Report format

Return a structured report: journey id; surface; contract status
(draft/approved); per scenario — id, verdict, expected, actual, evidence
paths with types, notes; your pre-recorded expectations (verbatim); console
and network observations; any blocker detail. The orchestrator persists the
gate artifacts — your final message is data for it, not a narrative for a
human.
```

- [ ] **Step 3: Add the capability row + reference**

In `skills/capabilities/SKILL.md`, add a row after the Browser read-back row:

```markdown
| Browser drive | a browser-automation tool family that can navigate, click, type, screenshot, and read console/network is present (Playwright MCP, chrome-devtools MCP, Claude-in-Chrome) | factory-assure's journey-reviewer drives browser-borne journeys and captures screenshot/console/network evidence → see references/browser-drive.md | Browser-borne journeys are a blocker: the item parks waiting-human with a packet naming `factory waive` — never a silent pass; cli/api journeys proceed unaffected |
```

Create `skills/capabilities/references/browser-drive.md`:

```markdown
# Browser drive

The assure stage's driving capability: a browser-automation tool family
that can **navigate, click, type, screenshot, and read console/network**.
The probe is behavioral — match whichever family is present in the tool
list:

- Playwright MCP (`mcp__playwright__*` — e.g. browser_navigate,
  browser_click, browser_type, browser_take_screenshot,
  browser_console_messages, browser_network_requests)
- chrome-devtools MCP (`mcp__chrome-devtools__*` — navigate_page, click,
  fill, take_screenshot, list_console_messages, list_network_requests)
- Claude-in-Chrome browser tools (the `computer`/browser action family)

Any one family satisfies the capability; prefer the one already connected.
Never mix families within one journey walk.

## Evidence conventions

- Screenshots → `.factory/items/<id>/assurance/screenshots/<journey>-<node>-<n>.png`
  (or the family's native format), one per walk step that changed the screen.
- Console → append one JSON line per material message to
  `assurance/console.ndjson`: `{"journey", "node", "level", "text"}`.
- Network → append one JSON line per failure or unexpected request to
  `assurance/network.ndjson`: `{"journey", "node", "method", "url", "status"}`.
- verdicts.json evidence entries reference these files with types
  `screenshot | dom | console | network` (cli/api journeys use `transcript`).

## When the capability is absent

A browser-borne journey without a Browser drive family is a **blocker**:
record it in `assurance/blockers.md`, park the item `waiting-human`, and the
packet names the human's two honest exits — connect a browser family and
re-run the stage, or `factory waive <id> --reason "..."`. **Never a silent
pass; never "inspection passed."** Parking is not failing — the capabilities
doctrine ("never let a missing optional tool fail a stage") survives because
the stage refuses to *lie*, not because it crashes: the degraded contract for
assurance is an explicit human decision, exactly like an unavailable stage
skill in dispatch. cli/api journeys never need this capability.
```

- [ ] **Step 4: Run the full suite** → green (the agents-frontmatter test picks the new agent up automatically). Commit:

```bash
git add agents/journey-reviewer.md skills/capabilities/SKILL.md skills/capabilities/references/browser-drive.md tests/test_plugin_structure.py
git commit -m "feat(assure): journey-reviewer agent + Browser drive capability

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Plan self-review notes

- Spec coverage: orchestration + allowlist + exits + tier depth + spend (T1); the walk + evidence + surface drivers + park-don't-pass (T1+T2); capability behavioral probe (T2). Dispatch resume for assure pauses, autopilot additions, and the confirmation/escape flows are Plan 4.
- The structure pins quote exact strings that appear in the file contents above — if an implementer paraphrases, tests catch it.
- The capabilities preamble sentence ("Never let a missing optional tool fail a stage") is intentionally reconciled in browser-drive.md ("Parking is not failing").
