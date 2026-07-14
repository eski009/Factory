---
name: council-review
description: Use when a factory stage needs the council's bounded multi-agent review (triage or code review) - runs the two-round protocol without group-chat drift
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

Bounded two-round council protocol (spec §6), ported from superpowers-council. Runs identically for both council moments — triage and review — only the seed content differs. No group chat: agents never see each other's notes, only the seed and the synthesis.

For Workflow-based fan-out of the rounds, see the capabilities skill's `references/workflow-fanout.md` (degraded path — parallel subagents — is the default).

## Attention, not suppression

Before Round 1, run `factory reputation --json`. Use scores to order which agents' output you read and weigh first. Reputation ranks attention — it never suppresses or skips a claim, no matter how low an agent's score.

## Protocol

1. **Seed context.** Every artifact below lives under a **review root**: `items/<id>/reviews/` for a single item (the default), or a caller-supplied root such as `.factory/runs/roadmap/` (batch triage) or `.factory/runs/research/` (initiation research) when no item exists yet. Below, `reviews/` denotes that root. Write `reviews/seed-context.md`:
   - Triage mode (single item): the item body + relevant brain surfaces (roadmap, open-questions, decisions, constraints, personas, market).
   - Triage mode (batch, e.g. from factory-roadmap): the full candidate list — one block per candidate (title, provisional kind, cited PRD section) — plus the same brain surfaces. The council ranks the candidates relative to each other in this one pass.
   - Research mode (initiation, e.g. from factory-research): the research seed — the intake-mined surfaces (constraints, design-system, users), the PRD/design file if provided, and the repo's outward surface (README, routes) — under review root `.factory/runs/research/`. Only the outward-facing seats are dispatched (see step 2); each researches its lens (web where available, inputs-only otherwise), every claim cited or marked UNSOURCED. Synthesis drafts the persona(s) + market read.
   - Review mode: a diff summary + the item's spec.md + the persona surfaces (personas.md, market.md).

2. **Round 1 — independent.** Dispatch the six council agents (`agents/council-product.md`, `council-ui-taste.md`, `council-architecture.md`, `council-engineering-quality.md`, `council-customer.md`, `council-commercial.md`) as parallel Task subagent calls in one message — the degraded baseline; see the `capabilities` skill for fan-out upgrades. (In **research mode** only the four outward-facing seats are dispatched: `agents/council-customer.md`, `council-commercial.md`, `council-product.md`, `council-ui-taste.md`.) (In **review mode** with a **light** review depth — a `bug`-tier item, per factory-review — dispatch only the inward correctness seats: `agents/council-architecture.md`, `council-engineering-quality.md`, `council-product.md`, plus `council-ui-taste.md` when the item's `kind` is `ui` or `mixed`; skip `customer` and `commercial` — a defect fix needs a correctness read, not a market/persona one. A `full` review dispatches all six as above.) Each agent receives ONLY `seed-context.md` and its own `docs/factory/council/<role>.md` — never another agent's memory file or round notes. Each agent:
   - Raises at most 3 new claims.
   - Cites evidence (file path, line, or URL) for each claim, or marks it explicitly unsourced.
   - Returns its findings as its final report — seats hold Read/Grep/Glob only and never write files. The orchestrator (the invoking session, not a subagent) persists each returned report to `reviews/round-1/<role>.md` before moving on.

3. **Orchestrator synthesis.** The invoking session (not a subagent) reads all six round-1 files it just wrote, dedupes overlapping claims, groups by topic, flags conflicts between roles, and decides which agents (if any) need Round 2. Writes `reviews/synthesis-1.md`.

4. **Round 2 — delta-only.** Dispatch only the selected agents. Each receives `synthesis-1.md` only — never another agent's raw Round 1 notes — and may answer only: agree, disagree, withdraw, or refine. No restatement of Round 1. Each agent returns its delta-only response as its final report; the orchestrator persists it to `reviews/round-2/<role>.md`.

5. **Hard stop.** Maximum 2 rounds. If a 3rd round seems warranted, do not run it — instead write a line in the synthesis stating the reason a 3rd round was needed but skipped. Tag every finding in the synthesis **low**, **medium**, or **high** severity. Write the final combined synthesis, with severities included, to `reviews/synthesis.md`.

## After synthesis

Material findings (anything that should change durable product memory, not just this item) go to the `council-judgement` skill to be filed as bids. Do not edit `docs/factory/brain/` directly from this skill.
