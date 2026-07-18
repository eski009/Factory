---
name: factory-verify
description: Use when a factory item is at stage verify - proves the change works end-to-end before shipping
context: fork
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

This skill runs in a forked context (`context: fork`): nothing from the invoking session is visible here. The item id arrives as the skill argument; everything else is read from disk — `factory status --json`, `.factory/items/<id>/...`, and the brain surfaces this skill names below. Your final message is the report the dispatcher acts on: state the outcome (the stage advanced to, or the failure/pause reason, verbatim where a gate refused), name the key artifact paths written, and keep it to a few lines — never paste file contents into it.

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
3. **Exercise the changed behavior directly**, not just through tests: run the actual app or CLI path each acceptance criterion names — the real command a user or caller would run, observing real output. **For any criterion that is checked by looking at the screen rather than by a runnable command — a visual bug, or any repro whose `repro.confirmed` event logged `mode: "human-confirmed"` — do not eyeball it yourself: route it through the blind observer protocol in the capabilities skill's `references/visual-verify.md`.** You hold the acceptance criteria (the answer key); a fresh observer subagent drives the app and reports what it factually sees without ever seeing the diagnosis, the diff, or the expected outcome, and you judge that independent report. This is the one path that stops a forked, unattended verify from reading the diff and rubber-stamping a visual "done."
4. For **every** acceptance criterion, write one line: the criterion, the exact command run to check it (or, for a visual criterion, the neutral navigation steps sent to the observer and the saved screenshot path), and the observed result (verbatim output, or the observer's verbatim factual description — not "looks right"). Write all of this to `items/<id>/verify.md`.
5. Only if the suite is fully green **and** every criterion's line shows a pass: log `verify.green` with the real test counts and `criteria` as `"<passed>/<total>"` (adding the `visual` evidence key from the capabilities skill's `references/visual-verify.md` when any criterion was visual), then advance to `ship` per the Contract.
6. If the suite has any failure, or any criterion's observed result doesn't match its expectation, or a visual criterion cannot be observed because the **App visual capture** capability is absent (see the capabilities skill's `references/visual-verify.md`): stop here. Do not log `verify.green` for the ones that did pass — the event is whole-item evidence, not partial credit. Report the specific failing criteria/tests to the dispatcher (for the capability-absent case, report that the item needs human confirmation so the dispatcher pauses it `waiting-human`).

## Notes

- "Ran it once and it seemed fine" is not evidence for a line in `verify.md` — the observed result must come from a command actually run, or a blind observation actually captured, in this stage's session, matching the sub-skill's Gate Function.
- A criterion checked by inspection rather than a runnable command still gets a line, but "inspection" here means the blind observer protocol produced a fresh screenshot and a factual description you judged — never the verify agent reading the diff and asserting the fix landed. Prefer a runnable check wherever the criterion admits one; where it does not, blind observation is the floor and human confirmation (capability-absent path) is the fallback.
