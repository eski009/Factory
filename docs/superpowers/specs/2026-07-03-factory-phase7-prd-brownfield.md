# Factory Phase 7 — PRD Intake, Brownfield Taste, Roadmap, Patterns: Design Spec

- **Date:** 2026-07-03
- **Owner:** Steve
- **Status:** Approved (in-session), extends the main spec (`2026-07-03-software-factory-design.md`)

## Purpose

Close the gap between "a backlog exists" and "where does the backlog come from": the factory must be able to start from a **PRD and/or design file** (greenfield) or from an **existing codebase** (brownfield), producing a seeded brain, tickets, and a prioritized roadmap. Additionally: make the README show how the factory works at a glance, and codify the orchestration patterns that produced this repo's quality so the outcomes replicate on less capable orchestrating models (explicit goal: Opus achieves Fable-grade results by following the encoded process).

## 1. Tickets & roadmap from a PRD / design file

New skill **`factory-roadmap`** + command **`/factory:roadmap <prd-path> [<design-file>]`**:

1. **Extract:** parse the PRD into candidate work items — one per feature/epic/user story — each carrying: title, provisional kind (ui/backend/mixed), and the PRD section cited as evidence. A design file (design doc, token export, redlines) seeds `brain/design-system.md` in the same pass.
2. **Seed the brain first:** vision/users/constraints filled from the PRD with inline citations (`(source: <prd-path>#<section>)`) — same evidence-only rule as intake. The council must judge against the PRD, never invention.
3. **Batch triage:** one council triage run over the entire candidate set (single seed context; priorities assigned relative to each other). Accepted candidates: `factory add` + `factory priority` + `triage.md` per item; `roadmap.md` written in priority order. Rejected candidates: recorded in `brain/open-questions.md` with the council's reason — never silently dropped.
4. The per-item pipeline (spec/design-gate/plan/…) is unchanged downstream.

Engine support: **`factory priority ITEM N`** — sets `priority` in item frontmatter through the engine (validated integer ≥ 1, `updated` refreshed, `priority.set` event logged) so skills stop hand-editing frontmatter.

## 2. Brownfield taste & context collection

**`factory-intake`** gains a brownfield mode with three collectors:

1. **Repo mining (automated, cited):** lint/format configs and naming patterns → `constraints.md`; theme/CSS variables/design tokens/component library → `design-system.md`; routes/screens/navigation → `users.md`; git history, ADRs, PR titles → `decisions.md`; the test suite read as a behavior spec. Every claim carries a `(source: <path>)` citation; anything uninferable goes to `open-questions.md`.
2. **One-time taste packet:** intake writes `docs/factory/packets/taste.md` — a short questionnaire (products whose UI the owner admires and why; non-negotiables; what "done" feels like; voice/tone; references to avoid). The human answers in place; intake folds the answers into the brain with the packet as citation. The intake hard gate (human reviews the seeded brain) still applies after.
3. **Ongoing accrual (already built, now named):** council bids from real diffs, filtered through judgements, accumulate taste in role memory and brain surfaces. Taste compounds through the firewall; the collectors only bootstrap it.

## 3. README: show how it works

A **"How it works"** section near the top: an ASCII pipeline diagram (stages, the design gate, both council moments, what the human sees and when), followed by a 60-second annotated example run (`/factory:add` → `/factory:run` → design packet arrives → `factory choice` → shipped report). Show first, reference after.

## 4. Orchestration patterns (Fable → any model)

Two new reference docs under `skills/capabilities/references/`, cited from the stage skills:

- **`orchestration-patterns.md`** — the session-proven playbook: plans carry complete code (implementers transcribe — implementer model quality stops mattering); fresh subagent per task; independent task reviewer with two verdicts; fix → re-review loop; **adversarial whole-branch review that walks the change end-to-end before ship** (the step that catches what task reviews miss); controller verifies small fixes directly; batch fix waves (one fixer, complete findings list); evidence-before-assertion everywhere.
- **`model-tiering.md`** — choosing models by task shape: cheapest tier when the plan contains the complete code (transcription); mid tier as the floor for reviewers and prose-authoring implementers; most capable tier only for whole-branch walks and architecture judgment; the signals for each.

Plus two skill strengthenings: `factory-plan` requires plan tasks complete enough that implementation is transcription; `factory-review` instructs the reviewer to *walk* the change end-to-end (trace one real flow across engine and prose) rather than skim the diff.

## Non-goals (Phase 7)

- Figma API integration (a design *file* means a doc/export the model can read; live design-tool APIs are future work).
- Automatic PRD change detection / re-sync (re-running `/factory:roadmap` is manual; idempotency = don't duplicate existing items with the same title).
- Item dependencies (still deferred, documented in §12 of the main spec).
