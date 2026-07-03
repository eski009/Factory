---
name: factory-verify
description: Use when a factory item is at stage verify - proves the change works end-to-end before shipping
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

## Contract

- **Entry stage:** `verify`. The gate into `verify` already required `reviews/synthesis.md` non-empty and `review.approved` logged.
- **Artifacts produced:** `items/<id>/verify.md`.
- **Exit — all pass:** `factory log ITEM verify.green --data '{"tests": "<counts>", "criteria": "<n>/<n>"}'` then `factory advance ITEM ship`. The `ship` gate checks only for the `verify.green` event — which is exactly why it must never be logged on partial evidence.
- **Exit — any failure:** no log call, no advance. Report to the dispatcher as a stage failure; it applies its own two-strikes-then-blocked rule.

## REQUIRED SUB-SKILL: superpowers:verification-before-completion

This whole stage *is* that skill's Iron Law applied to a pipeline gate: no `verify.green` without fresh, full evidence. Read it before running anything below and hold yourself to it literally — "tests probably pass" or "should work now" are exactly the claims it forbids, and this is the one stage whose entire job is to refuse them.

## Steps

1. Read `items/<id>/spec.md`'s `## Acceptance criteria` — this is the checklist, not a paraphrase of it.
2. Run the full test suite (the project's whole suite, not just the tests the plan named) and capture the pass/fail counts.
3. **Exercise the changed behavior directly**, not just through tests: run the actual app or CLI path each acceptance criterion names — the real command a user or caller would run, observing real output.
4. For **every** acceptance criterion, write one line: the criterion, the exact command run to check it, and the observed result (verbatim output or a precise summary of it — not "looks right"). Write all of this to `items/<id>/verify.md`.
5. Only if the suite is fully green **and** every criterion's line shows a pass: log `verify.green` with the real test counts and `criteria` as `"<passed>/<total>"`, then advance to `ship` per the Contract.
6. If the suite has any failure, or any criterion's observed result doesn't match its expectation: stop here. Do not log `verify.green` for the ones that did pass — the event is whole-item evidence, not partial credit. Report the specific failing criteria/tests to the dispatcher.

## Notes

- "Ran it once and it seemed fine" is not evidence for a line in `verify.md` — the observed result must come from a command actually run in this stage's session, matching the sub-skill's Gate Function.
- A criterion that can only be checked by inspection (not a runnable command) still gets a line — name what was inspected and what was found, but prefer a runnable check wherever the criterion admits one.
