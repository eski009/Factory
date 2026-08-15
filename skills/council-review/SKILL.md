---
name: council-review
description: Use when a factory stage needs the council's bounded multi-agent review (triage or code review) - runs the two-round protocol without group-chat drift
context: fork
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

This skill runs in a forked context (`context: fork`): nothing from the invoking session is visible here. The skill argument names the mode (`triage`, `review`, or `research`) and the item id (or, for research mode, the research root); every other input is read from disk per the mode list below. Your final message is the report the invoking stage acts on: the synthesis file path, the headline verdict, and the blocking-finding count — a few lines, never the report bodies.

Bounded two-round council protocol (spec §6), ported from superpowers-council. Triage and research retain fixed seat sets; review uses deterministic adaptive selection unless its caller explicitly requests `full`. No group chat: agents never see each other's notes, only the seed and the synthesis.

For Workflow-based fan-out of the rounds, see the capabilities skill's `references/workflow-fanout.md` (degraded path — parallel subagents — is the default).

## Attention, not suppression

Before Round 1, run `factory reputation --json`. Use scores to order which agents' output you read and weigh first. Reputation ranks attention — it never suppresses or skips a claim, no matter how low an agent's score.

## Protocol

1. **Seed context.** Every artifact below lives under a **review root**: `items/<id>/reviews/` for a single item (the default), or a caller-supplied root such as `.factory/runs/roadmap/` (batch triage) or `.factory/runs/research/` (initiation research) when no item exists yet. Below, `reviews/` denotes that root. Write `reviews/seed-context.md`:
   - Triage mode (single item): the item body + relevant brain surfaces (roadmap, open-questions, decisions, constraints, personas, market).
   - Triage mode (batch, e.g. from factory-roadmap): the full candidate list — one block per candidate (title, provisional kind, cited PRD section) — plus the same brain surfaces. The council ranks the candidates relative to each other in this one pass.
   - Research mode (initiation, e.g. from factory-research): the research seed — the intake-mined surfaces (constraints, design-system, users), the PRD/design file if provided, and the repo's outward surface (README, routes) — under review root `.factory/runs/research/`. Only the outward-facing seats are dispatched (see step 2); each researches its lens (web where available, inputs-only otherwise), every claim cited or marked UNSOURCED. Synthesis drafts the persona(s) + market read.
   - Review mode: a diff summary + the item's spec.md + the persona surfaces (personas.md, market.md).

2. **Round 1 — independent.** Choose the seat set for the mode, then dispatch the chosen roles in parallel — the degraded baseline; see the `capabilities` skill for fan-out upgrades.
   - Triage mode always dispatches all six roles exactly once: `product`, `ui-taste`, `architecture`, `engineering-quality`, `customer`, `commercial`.
   - Research mode dispatches exactly the four outward roles: `customer`, `commercial`, `product`, `ui-taste`.
   - Review mode records the diff base, head, and changed paths before selecting roles. Normalize only concrete diff-visible signals in this precedence order: `security`, `architecture`, `customer-trust`, `ui-taste`, `product-behavior`, `commercial`. Every signal must cite a changed path or hunk observation. The special signals `ambiguous`, `high-blast-radius`, and `irreversible` also require concrete evidence. Tier, kind, priority, and file count are context, never signals.
   - In review mode call `review_selection.select_roles` with `mode="adaptive"` unless the caller explicitly passed `full`; an explicit override calls it with `mode="full"`. The ordinary no-signal fallback is `fallback.general-backend`. Persist the returned plan, diff identity, signals/evidence, and empty per-seat outcomes to `reviews/selection-round-1.json` before dispatch or synthesis. `reviews/selection-round-N.json` is the receipt naming convention for every review round.

   Dispatch every selected role exactly once, using its `agents/council-<role>.md` agent, in a distinct fresh context with ONLY `seed-context.md` and its own `docs/factory/council/<role>.md` role memory — never another agent's memory file or round notes. Each seat raises at most three new claims, cites a file path, line, or URL for each claim or marks it `UNSOURCED`, and returns its findings without writing files. Reputation orders attention only and never suppresses a claim. The orchestrator alone writes reports, receipts, and synthesis.

   In review mode, update the receipt after dispatch to record every selected outcome as returned, missing, or unavailable. Persist a report at `reviews/round-1/<role>.md` only for a returned output; never manufacture a report for a missing or unavailable outcome. Any lost independence or output sets `independence.achieved` to false, records the exact loss in `independence.degradation`, and requires a matching `## Degradation` section in synthesis. Never describe degraded execution as equivalent to an independent council.

3. **Orchestrator synthesis.** The invoking session (not a subagent) reads the returned round-1 reports it wrote, dedupes overlapping claims, groups by topic, flags conflicts between roles, and decides whether Round 2 is required. Write `reviews/synthesis-1.md`. In review mode, keep its selection facts consistent with `selection-round-1.json`.

4. **Round 2 — delta-only.** In review mode, run Round 2 only for a blocking finding or conflict. Call `review_selection.select_roles` with `round_number=2`, the Round 1 `prior_roles`, `blocking_roles`, normalized `conflicts`, and at most one next relevant omitted role for a conflict. Build the closed Round 2 receipt from the unchanged diff identity and signals, the returned selection plan, and its escalation inputs, then persist it to `reviews/selection-round-2.json` before dispatch. Recall only roles needed for the blocker or conflict; the extra omitted role is allowed only for a conflict. Across both rounds, select at most four distinct adaptive roles and never exceed that cap. Triage and research preserve their existing fixed-seat protocol and recall only the agents needed to resolve a conflict.

   Each Round 2 seat receives `synthesis-1.md` only — never another agent's raw Round 1 notes — and may only agree, disagree, withdraw, or refine. No restatement of Round 1. The orchestrator persists each returned delta to `reviews/round-2/<role>.md` and records returned, missing, or unavailable outcomes plus any independence degradation in the Round 2 receipt.

5. **Hard stop and final synthesis.** Maximum two rounds: never run Round 3. If another round seems warranted, write why it was needed but skipped. Tag every finding **low**, **medium**, or **high** severity. Write the final combined synthesis to `reviews/synthesis.md`; it retains the rule that a finding blocks only when severity is high and it contradicts the spec, a brain surface, or the test evidence.

   For review mode, include `## Selection` with diff identity, signals and evidence, selected and omitted roles with reasons, escalation, outcomes, and independence, all consistent with the JSON receipts. Include `## Degradation` whenever a receipt records degraded independence, naming exactly what was lost.

## After synthesis

Material findings (anything that should change durable product memory, not just this item) go to the `council-judgement` skill to be filed as bids. Do not edit `docs/factory/brain/` directly from this skill.
