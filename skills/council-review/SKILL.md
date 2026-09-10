---
name: council-review
description: Use when a factory stage needs the council's bounded multi-agent review (triage or code review) - runs the two-round protocol without group-chat drift
---

First read the capabilities skill's `references/host-adapter.md` and resolve the plugin root for this host. Below, `factory` means `python3 "${FACTORY_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/scripts/factory/factory.py" --repo .`.

Run this skill in a fresh context using the capabilities skill's `references/host-adapter.md`; nothing from the invoking session may be treated as input. For review, the distinct `selection_mode` is `adaptive` or `full`. The stage `mode` is `triage`, `review`, or `research`. The skill argument names that mode and the item id (or, for research mode, the research root); every other input is read from disk per the mode list below. Your final message is the report the invoking stage acts on: the synthesis file path, the headline verdict, and the blocking-finding count — a few lines, never the report bodies.

Bounded two-round council protocol (spec §6), ported from superpowers-council. Triage and research retain fixed seat sets; review uses deterministic adaptive selection unless its caller explicitly requests `selection_mode: full`. No group chat: agents never see each other's notes, only the seed and the synthesis.

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
   - In review mode, default `selection_mode` to `adaptive` unless the caller explicitly passed `selection_mode: full`, then call `review_selection.select_roles` with `mode=selection_mode`. The ordinary no-signal fallback is `fallback.general-backend`. `reviews/selection-round-N.json` is the receipt naming convention for every review round.

   Dispatch every selected role exactly once, using its `agents/council-<role>.md` agent, in a distinct fresh context with ONLY `seed-context.md` and its own `docs/factory/council/<role>.md` role memory — never another agent's memory file or round notes. Each seat raises at most three new claims, cites a file path, line, or URL for each claim or marks it `UNSOURCED`, and returns its findings without writing files. Reputation orders attention only and never suppresses a claim. The orchestrator alone writes reports, receipts, and synthesis.

   In review mode, record every selected outcome as returned, missing, or unavailable. Persist a report at `reviews/round-1/<role>.md` only for a returned output; never manufacture a report for a missing or unavailable outcome. The closed Round 1 receipt contains exactly these top-level fields: `item`, `round`, `mode`, `diff`, `signals`, `selected`, `omitted`, `escalation`, `outcomes`, `independence`. Set `item` to the item id, `round` to 1, and `mode` to the selection mode; record diff base/head/changed paths, normalized signals/evidence, selector-returned selected/omitted roles and reasons, empty Round 1 escalation inputs, every seat outcome/report, and independence. Persist this provisional receipt to `reviews/selection-round-1.json` before synthesis. It is not final until step 3 updates its escalation.

   Successful independent execution records `independence.requested=true`, `independence.achieved=true`, and an empty `independence.degradation`. Any lost independence or output sets `independence.achieved` to false, records the exact loss in `independence.degradation`, and requires a matching `## Degradation` section in synthesis. For any degraded review, actually execute a command or probe that reproduces the reviewed behavior and ground the verdict in that evidence; static inspection alone is insufficient. Never describe degraded execution as equivalent to an independent council.

3. **Orchestrator synthesis.** The invoking session (not a subagent) reads the returned round-1 reports it wrote, dedupes overlapping claims, groups by topic, flags conflicts between roles, and decides whether Round 2 is required. Write `reviews/synthesis-1.md`. In review mode, finalize `selection-round-1.json` after synthesis: update `escalation.blocking_roles` and `escalation.conflicts` with every synthesis-discovered blocker or conflict; keep `prior_roles=[]` and `added_role=""`. Persist this update before selecting Round 2. The final branch walk must also update these fields if it discovers new escalation.

4. **Round 2 — delta-only.** Only review mode limits Round 2 to a blocking finding or conflict. In review mode, call `review_selection.select_roles` with `round_number=2`, the Round 1 `prior_roles`, `blocking_roles`, normalized `conflicts`, and at most one next relevant omitted role for a conflict. Build the closed Round 2 receipt from the unchanged diff identity and signals, the returned selection plan, and its escalation inputs, then persist it to `reviews/selection-round-2.json` before dispatch. Recall only roles needed for the blocker or conflict; the extra omitted role is allowed only for a conflict. Across both rounds, select at most four distinct adaptive roles and never exceed that cap.

   Triage and research may select Round 2 for any synthesis-driven follow-up under the existing bounded protocol. Dispatch only agents selected after synthesis from that mode's fixed Round 1 seat set; do not apply review's blocking/conflict trigger, adaptive role cap, selector, or receipt contract to triage or research.

   Each Round 2 seat receives `synthesis-1.md` only — never another agent's raw Round 1 notes — and may only agree, disagree, withdraw, or refine. No restatement of Round 1. The orchestrator persists each returned delta to `reviews/round-2/<role>.md`. In review mode, it also records returned, missing, or unavailable outcomes plus any independence degradation in the Round 2 receipt.

5. **Hard stop and final synthesis.** Maximum two rounds: never run Round 3. If another round seems warranted, write why it was needed but skipped. Tag every finding **low**, **medium**, or **high** severity. Write the final combined synthesis to `reviews/synthesis.md`; it retains the rule that a finding blocks only when severity is high and it contradicts the spec, a brain surface, or the test evidence.

   For review mode, include `## Selection` with diff identity, signals and evidence, selected and omitted roles with reasons, escalation, outcomes, and independence, all consistent with the JSON receipts. Include `## Degradation` whenever a receipt records degraded independence, naming exactly what was lost. Every degraded final synthesis also includes a non-empty `## Execution` section using the evidence format below.

## After synthesis

Material findings (anything that should change durable product memory, not just this item) go to the `council-judgement` skill to be filed as bids. Do not edit `docs/factory/brain/` directly from this skill.

## Lost-reply reconciliation

Read the capabilities skill's
`references/disk-first-reconciliation.md`. Checkpoint each selected seat
separately, then checkpoint each orchestrator synthesis separately. Run
`factory reconcile begin` before dispatching this child: a Round N seat uses
obligation `council:round-N:ROLE`, exact inputs `reviews/seed-context.md`, the
seat's `docs/factory/council/ROLE.md`, and (for Round 2) the current-attempt
`reviews/synthesis-1.md`, plus exact evidence
`reviews/round-N/ROLE.md`. Synthesis uses obligation
`council:synthesis-N`, the current-attempt seed and exact selected-seat files
as inputs, and exact evidence `reviews/synthesis-1.md` or final
`reviews/synthesis.md`. These children are repository-only, so omit
`--worktree` consistently; if a future child is checkout-bound, begin,
discover, and inspect must all use its same canonical `--worktree CHECKOUT`.

After every dispatch, perform exactly one host-native wait, capped at 60
seconds. On an unanswered wait, or a `still running` re-entry, use the host
adapter to establish that exact child's writer state as `active` or `terminal`,
then run `factory reconcile inspect` before any failure accounting, retry, or
replacement. If state cannot be established, stop. An active writer returns
`still running` and causes no second wait, failure count, retry, or replacement.

Only files bound to the current attempt may be adopted. For a terminal partial
round, claim one continuation and dispatch only missing selected seats from
that same attempt. Never reuse arbitrary prior council files and never
reconstruct a report that a read-only seat did not return. A complete set of
current-attempt seats permits the separately checkpointed synthesis; a complete
current-attempt synthesis is adopted under its substantive verdict, not
regenerated.

Before finalization, re-read the current item stage and complete current event
log and perform only the normal side effects still missing. This recovery does
not cover 0032's pool exhaustion, `no-synthesis` policy, whole-fan-out
coordination across attempts, or arbitrary prior council runs.

## Current-attempt evidence format

Record the observed result verbatim or as an explicitly labeled summary of the saved output.

Before a new review pass, archive previous selection receipts, `round-1/`, `round-2/`, and syntheses together under `reviews/history/<previous-head>/`; never present historical reports as current outcomes. A stale Round 2 receipt cannot satisfy current escalation. The gate ignores an old-delta optional receipt on a clean re-review; malformed current evidence still refuses.

Finalize `## Adjudication` after synthesis and the branch walk, with exactly one JSON block containing `verdict` (`approved` or `rejected`), `blocking_roles`, `conflicts`, and `remaining_blockers` (stable finding IDs). The middle two fields must exactly match the finalized Round 1 escalation, including resolved triggers. Round 2 must carry those same triggers. Verify requires `verdict: approved` and an empty `remaining_blockers` list. A prose verdict alone is not authoritative.

For degraded review, run a relevant command/probe and save its actual output beneath the current review root. Under `## Execution`, put exactly one JSON block containing a non-empty array of records with `command`, integer `exit_code`, `observed_result`, review-root-relative `output_file`, and the output's `sha256`. Static-only prose is insufficient. The validator checks the record and digest-bound contained output without executing the command. This is recorded evidence, not host execution attestation; never fabricate output or claim the digest proves a command was run.
