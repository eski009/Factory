# Factory Phase 7 Implementation Plan — PRD Intake, Brownfield, Roadmap, Patterns

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Phase 7 spec (`docs/superpowers/specs/2026-07-03-factory-phase7-prd-brownfield.md`): PRD → tickets + roadmap, brownfield taste collection, an intuitive README, and the orchestration-pattern references that make outcomes model-portable.

**Architecture:** One small engine addition (`factory priority`) removes the last excuse for skills to hand-edit frontmatter. Everything else is prose: a new `factory-roadmap` skill orchestrating extract → seed → batch-triage; a brownfield mode inside `factory-intake`; two pattern references; README surgery. Structural/coherence tests grow to cover the new surface.

**Tech Stack:** Python 3.11+ stdlib (engine + tests); plugin prose.

## Global Constraints

- Engine: stdlib only; deterministic; exit codes 0/1/2; TDD.
- Skills: CLI-shorthand convention; frontmatter rules; ≤150 lines; evidence-only seeding with inline `(source: …)` citations; the intake hard gate is never weakened.
- Pattern references open with what they are (process guidance, model-agnostic) — they are NOT capability-gated like the tool references, so no "only if you have X" line; instead: "These patterns assume nothing about the orchestrating model — they are how the factory gets strong-model outcomes from any model."
- Run tests from repo root with: `python3 -m unittest discover -s tests -v`
- Commit after every task; `feat:`/`test:`/`docs:` prefixes.

---

### Task 1: Engine — `factory priority`

**Files:**
- Create: `scripts/factory/lib/priority.py` (or add to items.py — implementer's call: a `set_priority(repo, item_id, priority)` function; keep it where the codebase would naturally put it, `items.py` is acceptable if under ~15 lines)
- Modify: `scripts/factory/factory.py` (subcommand `priority ITEM N`)
- Test: `tests/test_priority.py` + CLI cases in the established style

**Binding contract:**
- `set_priority(repo, item_id, priority)`: item must exist (`ItemError` otherwise); `priority` must be an integer ≥ 1 (`ItemError` otherwise — message names the constraint); updates frontmatter `priority`, refreshes `updated` via `logs.now_stamp()`, preserves body; appends event `priority.set {"priority": N}`; returns the updated meta.
- CLI: `priority ITEM N` — prints `ITEM priority N`; refusals → stderr `refused: …`, exit 2 (both ItemError cases). N parsed as int; non-integer N is an argparse-level type error (exit 1) via `type=int`.
- Works at any stage including waiting-human (priority is metadata, not a transition — no gate).
- Tests: set on fresh item; re-set overwrites; non-existent item exit 2; `priority ITEM 0` exit 2; `priority ITEM x` exit 1; stage unchanged; `validate` still clean after (stage-vs-log consistency unaffected since no stage.advance logged).

- [ ] TDD steps as established; full suite green; commit `feat: factory priority - engine-managed priority setting`

---

### Task 2: factory-roadmap skill + command

**Files:**
- Create: `skills/factory-roadmap/SKILL.md`
- Create: `commands/roadmap.md`
- Modify: `tests/test_plugin_structure.py` (+`roadmap` in expected commands; assertion the skill mentions both `factory add` and `factory priority`), `tests/test_plugin_coherence.py` if command-pattern test needs the new file (check)

**Binding contract (skill body):**
1. **Inputs:** `$ARGUMENTS` = PRD path (required) + optional design-file path. Refuse politely (no side effects) if the PRD path doesn't exist.
2. **Extract:** enumerate candidate items from the PRD — one per feature/epic/story; each candidate records title, provisional kind (ui if it names user-facing surface, backend if purely internal, mixed otherwise), and the PRD section cited. A design file seeds `brain/design-system.md` in the same pass (tokens/components/patterns it defines, cited).
3. **Seed the brain before triage:** vision/users/constraints from the PRD with inline citations; evidence-only (uninferable → `open-questions.md`). State the intake hard gate verbatim: the human reviews the seeded brain before the first council run treats it as ground truth.
4. **Batch triage:** run the council-review skill in triage mode ONCE over the full candidate list (single seed-context listing all candidates); the orchestrator then, per accepted candidate: `factory add "TITLE" --kind KIND` → `factory priority ITEM N` (N from the council's relative ranking) → write `items/<id>/triage.md` citing the council synthesis. Rejected candidates → `brain/open-questions.md` with the council's reason. Write `docs/factory/roadmap.md` in priority order (the flat one-line-per-item convention from factory-triage).
5. **Idempotency:** before adding, check `factory status --json` for an existing open item with the same title — skip duplicates and say so.
6. **Exit:** report counts (candidates found / added / rejected / skipped) and remind that `/factory:run` starts execution.

`commands/roadmap.md`: description `Create tickets and a prioritized roadmap from a PRD (and optional design file) - $ARGUMENTS = <prd-path> [<design-path>]`; body invokes the factory-roadmap skill.

- [ ] Author; structural tests updated; full suite green; commit `feat: factory-roadmap - PRD to tickets and prioritized roadmap`

---

### Task 3: Brownfield intake mode

**Files:**
- Modify: `skills/factory-intake/SKILL.md`
- Modify: `tests/test_plugin_structure.py` (assertion: intake mentions `taste.md` and "brownfield")

**Binding contract (added section, keep the skill ≤150 lines — tighten existing prose if needed):**
1. **Mode detection:** brownfield = the target repo already contains product code (not a fresh scaffold). In brownfield mode, run three collectors IN ADDITION to the existing source inventory:
   - **Repo mining** (all cited): lint/format configs + observed naming/structure conventions → `constraints.md`; theme files/CSS variables/design tokens/component library → `design-system.md`; routes/screens/navigation surface → `users.md`; git log + ADRs + PR titles → `decisions.md`; test suite read as behavior spec (feeds `constraints.md`/`users.md`).
   - **Taste packet:** write `docs/factory/packets/taste.md` — questionnaire covering: 3 products whose UI you admire and why; hard non-negotiables; what "done/quality" means here; voice & tone; anti-references (what to avoid). Instruct: answers are edited into the packet by the human; on the next intake/roadmap run, fold answers into the brain with `(source: docs/factory/packets/taste.md)` citations. The packet is optional — an unanswered packet blocks nothing.
   - **Ongoing accrual note:** one paragraph naming the existing mechanism (bids → judgements → role memory/brain) as the compounding taste channel; collectors only bootstrap.
2. The existing hard gate sentence stays verbatim and applies to brownfield seeding too.

- [ ] Author; structural test; full suite green; commit `feat: brownfield intake - repo mining and taste packet`

---

### Task 4: Orchestration pattern references + skill strengthenings

**Files:**
- Create: `skills/capabilities/references/orchestration-patterns.md`
- Create: `skills/capabilities/references/model-tiering.md`
- Modify: `skills/factory-plan/SKILL.md`, `skills/factory-review/SKILL.md`, `skills/capabilities/SKILL.md` (a "Process patterns" line under the table linking both)
- Modify: `tests/test_plugin_structure.py` (the reference-link test already asserts links resolve — ensure new refs are linked; add both to the existing reference-existence assertion list)

**Binding contract:**

`orchestration-patterns.md` — opens: "These patterns assume nothing about the orchestrating model — they are how the factory gets strong-model outcomes from any model." Then, each with a one-line why:
1. **Plans carry complete code.** A plan task is done when implementation is transcription — exact code, exact tests, exact commands, expected outputs. Implementer model quality stops mattering when there is nothing left to invent.
2. **Fresh subagent per task; report files over pasted context.** Each task gets exactly its brief + interfaces; no session history.
3. **Independent task review with two verdicts** (spec compliance AND quality), then fix → re-review; never skip the re-review.
4. **Adversarial whole-branch review before ship.** After all tasks pass their gates, one most-capable review WALKS the change end-to-end (trace one real flow across all layers). This catches integration failures that per-task review structurally cannot see. Never skip it because task reviews were clean — that's when it matters most.
5. **Batch fix waves.** One fixer gets the complete findings list; per-finding fixers rebuild context and cost more than the tasks.
6. **Controller verification for small fixes.** A one-line fix with test evidence can be verified by reading the diff — spend review capacity where judgment is needed.
7. **Evidence before assertion.** Nothing is "done" without command output; refusals must name what's missing.

`model-tiering.md` — opens with the same model-agnostic line; then the tiering table: cheapest tier = transcription (plan contains the code), single-file mechanical fixes; mid tier = floor for ALL reviewers, prose-authoring implementers, multi-file fixes; most capable tier = whole-branch walks, architecture decisions, final audits. Signals for upgrading: implementer reports BLOCKED, task needs invention not transcription, review must trace across layers. Rule: an omitted model choice silently inherits the most expensive — always choose explicitly.

`factory-plan` strengthening: add to the adaptations list — plan tasks must carry the complete code/tests/commands so implementation is transcription (link orchestration-patterns.md pattern 1).
`factory-review` strengthening: add to the review instructions — beyond council findings, the synthesis must include an end-to-end WALK: trace the item's primary flow through the actual change (entry point → data → output) and record what was traced (link pattern 4).

- [ ] Author; links + structural tests; full suite green; commit `feat: orchestration-patterns and model-tiering references; plan/review strengthenings`

---

### Task 5: README "How it works" + CHANGELOG

**Files:**
- Modify: `README.md`, `CHANGELOG.md`

**Binding contract:**
- README gains a `## How it works` section directly after the intro: an ASCII diagram of the pipeline showing the stages left-to-right, the design gate as the human stop, the two council moments (triage, review), and where packets/choice fit. Under it, a "60 seconds from idea to shipped" annotated example: the exact commands a user types (`/factory:add "Dark mode"`, `/factory:run`, `factory choice 0001-dark-mode b`, `/factory:run`) with one line each of what the factory does in between. Then a one-line pointer to getting-started. Existing sections stay; trim anything the new section makes redundant.
- The diagram must be accurate: stages exactly as the engine has them; design skipped for backend; gates named as they are.
- CHANGELOG: add `### Added` entries under a new `## [0.2.0] - 2026-07-03` heading for: integrity audit in validate (from the fix wave), factory priority, factory-roadmap, brownfield intake, pattern references, README rework. Factual, one line each.
- Full suite green (docs only); commit `docs: How-it-works README, 0.2.0 changelog`

---

## Plan Self-Review (completed)

- **Spec coverage:** roadmap flow incl. `factory priority`, idempotency, rejected-candidates rule (Tasks 1-2); brownfield collectors + taste packet + accrual note + hard gate (Task 3); patterns + tiering + the two strengthenings (Task 4); README diagram + example + 0.2.0 changelog (Task 5). Non-goals (Figma API, PRD re-sync, dependencies) untouched.
- **Placeholder scan:** Task 1 contract is complete enough for TDD without ambiguity (exact messages/exit codes/event name); prose tasks carry binding contracts.
- **Consistency:** `priority.set` event is gate-neutral (no gate consumes it); `factory priority` referenced by factory-roadmap matches Task 1's CLI shape; reference filenames match the existing references/ dir and the link-resolution coherence test; roadmap command name doesn't collide with existing commands.
