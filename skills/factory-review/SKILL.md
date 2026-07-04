---
name: factory-review
description: Use when a factory item is at stage review - council reviews the diff against spec and brain before verification
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

## Contract

- **Entry stage:** `review`. The gate into `review` already required branch `factory/<item-id>` to exist and `implement.completed` to be logged.
- **Artifacts produced:** `items/<id>/reviews/synthesis.md` (via the council-review protocol), a `review.rejected` or `review.approved` event.
- **Exit — clean:** `factory log ITEM review.approved` then `factory advance ITEM verify`. The `verify` gate checks exactly these two: `reviews/synthesis.md` non-empty and `review.approved` logged.
- **Exit — blocking findings:** `factory log ITEM review.rejected --data '{"round": N}'`, then `factory advance ITEM implement` for rework. The engine caps rework at 2: it counts lifetime `review.rejected` events and refuses (`GateError`) the `review -> implement` move once that count exceeds 2. If the advance is refused, do not retry it — instead `factory advance ITEM blocked --reason "review: rejected too many times"` and `factory packet ITEM`. Either outcome hands back to the dispatcher.

## Steps

1. **Diff.** Compute the branch diff: `git diff <default-branch>...factory/<item-id>` (or against the merge-base) plus `git log --oneline` for the commit list. Summarize it — the council seed carries a summary, not the raw diff dump.
2. **Run the council.** Use the `council-review` skill in **review mode**: seed = the diff summary + `items/<id>/spec.md` + its `## Acceptance criteria`. Don't restate that skill's two-round protocol here — follow it as written, through to its own `reviews/synthesis.md` output.
   - **Beyond council findings, WALK the change end-to-end.** Council seats review in parallel and each sees the diff, not the running system — that structurally cannot catch an integration failure that only shows up when one real flow crosses multiple layers. Before writing the final synthesis, trace the item's primary flow through the actual change — entry point → data → output — across every layer it touches (engine and prose both, where relevant), and record in `reviews/synthesis.md` what was traced. Never skip this because every council finding came back clean; that's exactly when a whole-branch seam is most likely to be the only thing left uncaught. See `skills/capabilities/references/orchestration-patterns.md` pattern 4.
3. **Judge blocking vs. clean.** A finding is blocking only if the council marked it severity **high** *and* it contradicts the spec, a brain surface, or the test evidence — taste disagreements and low/medium findings never block.
4. **If blocking:** determine the rework round `N` as the count of prior `review.rejected` events on this item plus one (round 1 the first time, round 2 the second). Log `review.rejected` with that round, make sure the blocking findings are written into `reviews/synthesis.md` (the council-review protocol already writes this as its final synthesis — confirm it names the specific blocking items, not just a verdict), then attempt the `implement` advance per the Contract. Catch a `GateError` refusal as the 2-rework-cap signal, not a bug — follow the blocked path above instead of re-attempting.
5. **If clean:** confirm `reviews/synthesis.md` exists and is non-empty (it will, from step 2), log `review.approved`, and advance to `verify` per the Contract.
6. **File durable learnings.** Anything from the council's synthesis worth remembering past this item (a recurring pattern, a spec ambiguity worth closing) goes through the `council-judgement` skill as a bid — do not edit `docs/factory/brain/` directly from here, matching council-review's own rule.

## Notes

- Rounds are lifetime-scoped, not scoped to this stage entry — a rejection from an earlier pass through `review` still counts toward the cap even if the item cycled through `implement` since.
- Hand back to the dispatcher either way; this skill never loops itself back into another council pass.
