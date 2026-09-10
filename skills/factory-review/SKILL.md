---
name: factory-review
description: Use when a factory item is at stage review - council reviews the diff against spec and brain before verification
---

First read the capabilities skill's `references/host-adapter.md` and resolve the plugin root for this host. Below, `factory` means `python3 "${FACTORY_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

Run this skill in a fresh context using the capabilities skill's `references/host-adapter.md`; nothing from the invoking session may be treated as input. The item id arrives as the skill argument; everything else is read from disk — `factory status --json`, `.factory/items/<id>/...`, and the brain surfaces this skill names below. Your final message is the report the dispatcher acts on: state the outcome (the stage advanced to, or the failure/pause reason, verbatim where a gate refused), name the key artifact paths written, and keep it to a few lines — never paste file contents into it.

## Contract

- **Entry stage:** `review`. The gate into `review` already required branch `factory/<item-id>` to exist and `implement.completed` to be logged.
- **Artifacts produced:** `items/<id>/reviews/selection-round-1.json`, `selection-round-2.json` if Round 2 ran, `synthesis.md` and returned seat reports (via the council-review protocol), plus a `review.rejected` or `review.approved` event.
- **Exit — clean:** `factory log ITEM review.approved` then `factory advance ITEM verify`. The `verify` gate validates the item-bound selection Round 1 receipt (and selection Round 2 if run), its returned report artifacts, disclosed degradation, non-empty `reviews/synthesis.md`, and the current-round `review.approved` event.
- **Exit — blocking findings:** with feasibility disabled, retain `factory log ITEM review.rejected --data '{"round": N, "head": "<head>"}'` then `factory advance ITEM implement`. With feasibility enabled, first read `references/plan-feasibility.md`, persist stable finding ids in `reviews/synthesis.md`, prepare non-canonical plan/acceptance proposals, and invoke one `factory plan-rework --source review ...`; it records rejection and implementation entry atomically. The same two-rework cap applies. A cap refusal routes to `factory advance ITEM blocked --reason "review: rejected too many times"` plus `factory packet ITEM`.

## Steps

1. **Current review-round diff.** Resolve the reviewed branch head once with `git rev-parse factory/<item-id>` and retain it as `<head>` throughout this review. Read the item's event log before choosing `<base>`. For the first review, use the default-branch merge base from `git merge-base <default-branch> <head>`. For a re-review, use the `head` from the most recent prior `review.rejected` event; use it as `<base>`. If a prior rejection has no valid `data.head`, stop rather than falling back to the lifetime branch diff. Compute the exact round delta with `git diff <base>..<head>`, its commit list from `git log --oneline <base>..<head>`, and `git diff --name-only <base>..<head>`. The Round 1 receipt `diff.base`, `diff.head`, and `diff.changed_paths` come from this exact comparison: the two resolved commit SHAs and the exact changed-path list, respectively. Summarize that same delta — the council seed carries a summary, not the raw diff dump.
2. **Run the council.** Use the `council-review` skill with stage `mode: review`: seed = the diff summary + `items/<id>/spec.md` + its `## Acceptance criteria`. Pass the separate `selection_mode: adaptive` argument unless this invocation explicitly says `full`; an explicit full override still passes `mode: review` and sets `selection_mode: full`. Follow that skill's two-round protocol through its `reviews/selection-round-1.json`, optional `selection-round-2.json`, returned reports, and final `reviews/synthesis.md` output. The end-to-end walk below is separate from the council and is never selected, reported, or counted as a council seat.
   - **Beyond council findings, WALK the change end-to-end.** Council seats review in parallel and each sees the diff, not the running system — that structurally cannot catch an integration failure that only shows up when one real flow crosses multiple layers. Pick the primary flow to walk as the flow behind the spec's first acceptance criterion; if none fits, walk the user-visible path the diff most changes. Before writing the final synthesis, trace that flow through the actual change — entry point → data → output — across every layer it touches (engine and prose both, where relevant). Only an orchestrator already running on the most-capable tier walks this inline; an orchestrator on any lower tier (mid included) must dispatch the walk to a most-capable-tier subagent — a read-only reviewer — and merge its returned trace into `reviews/synthesis.md` (see the capabilities skill's `references/model-tiering.md`). Record in `reviews/synthesis.md`'s walk section: the flow chosen, the hops taken (file/function at each), what data or state was checked at each hop, and what was actually executed versus statically read. If any review receipt records degradation, actually execute a command or probe that reproduces the reviewed behavior; static inspection alone is insufficient. Record that command or probe and its observed result in a non-empty `## Execution` section of the final synthesis so the verdict is grounded in reproduced execution. Never skip this because every council finding came back clean; that's exactly when a whole-branch seam is most likely to be the only thing left uncaught. See the capabilities skill's `references/orchestration-patterns.md`, pattern 4.
3. **Judge blocking vs. clean.** A finding is blocking only if the council marked it severity **high** *and* it contradicts the spec, a brain surface, or the test evidence — taste disagreements and low/medium findings never block.
4. **If blocking:** determine the rework round `N` as the count of prior `review.rejected` events plus one. Make sure `reviews/synthesis.md` names each blocking finding with a stable id, severity, evidence, and bounded remedy. If feasibility is disabled, log and advance via the legacy Contract. If enabled, preserve the completed canonical plan as the exact proposal prefix; append exactly one unchecked task per blocking id, each naming `reviews/synthesis.md` and that id; produce a proposed acceptance sidecar with the refreshed plan-structure hash and a revision reason naming `review` plus the exact synthesis SHA-256; then call `factory plan-rework ITEM --source review --source-file .factory/items/ITEM/reviews/synthesis.md --finding ID ... --plan-proposal PROPOSAL --acceptance-proposal PROPOSAL --json`. Do not separately log rejection or call advance: the adapter owns both. Only the exact refusal `review rejected too many times; move item to blocked` is the cap signal and takes the blocked path. A malformed proposal, stale hash, invalid finding, or concurrent-input refusal leaves the item at review; correct that named defect and retry the same bounded rework operation rather than misclassifying it as a cap.
5. **If clean:** confirm `reviews/synthesis.md` exists and is non-empty (it will, from step 2), log `review.approved`, and advance to `verify` per the Contract.
6. **File durable learnings.** Anything from the council's synthesis worth remembering past this item (a recurring pattern, a spec ambiguity worth closing) goes through the `council-judgement` skill as a bid — do not edit `docs/factory/brain/` directly from here, matching council-review's own rule.

## Spend logging

At step 2's fan-out points, when each dispatch batch completes, the orchestrating session logs one spend event per council round — `factory log ITEM spend --data '{"provenance":"measured","scope":"leaf","stage":"review","source":"factory-review","dispatches":<n>,"tokens":{"total":<n>}}'` (include `"input"`/`"output"` instead or additionally when the harness reports them) with `dispatches` = selected dispatches that actually completed and returned. Use measured token fields only when the harness reports them; if it surfaces no token usage, log the same event with `"provenance":"proxy","scope":"leaf"` and **no** `tokens` key. Missing or unavailable attempts remain receipt outcomes and do not inflate the completed dispatch count. Never estimate or invent token numbers; the orchestrator's own main-loop burn is never logged as measured. The end-to-end walk's dispatch and spend stay separately logged and are never counted as a council seat. The engine neither requires nor verifies these events at gates.

## Lost-reply reconciliation

Read the capabilities skill's
`references/disk-first-reconciliation.md`. Run `factory reconcile begin`
before dispatching this child, treating the council invocation as
`review:council-synthesis`, with exact inputs
`.factory/items/ITEM/reviews/seed-context.md` and
`.factory/items/ITEM/spec.md`, exact evidence
`.factory/items/ITEM/reviews/synthesis.md`, and no `--worktree` because the
council is repository-only. Use the same exact input/evidence set for discovery
and inspection; any separately dispatched branch walk gets its own checkpoint
with its concrete input, report evidence, and canonical `--worktree CHECKOUT`.

After dispatch, perform exactly one host-native wait, capped at 60 seconds. On
an unanswered wait, or a `still running` re-entry, use the host adapter to
establish that exact child's writer state as `active` or `terminal`, then run
`factory reconcile inspect` before any failure accounting, retry, or
replacement. If state cannot be established, stop. An active writer returns
`still running` and causes no second wait, failure count, retry, or replacement.

Adopt a terminal complete current-attempt synthesis, then continue the existing
end-to-end walk and judgement; do not equate transport completion with
approval. Before logging an outcome, advancing, or filing bids, re-read the
current item stage and complete current event log and perform only the normal
side effects still missing. If the transition already landed, adopt it; retain
`review:post-transition-learning` as a named missing obligation and file only
learnings not already recorded. This recovery does not cover 0032's pool
exhaustion, `no-synthesis` policy, whole-fan-out coordination, or arbitrary
prior council runs.

## Notes

- Rounds are lifetime-scoped, not scoped to this stage entry — a rejection from an earlier pass through `review` still counts toward the cap even if the item cycled through `implement` since.
- Hand back to the dispatcher either way; this skill never loops itself back into another council pass.
