# Blind visual verification

The failure this prevents: a `mode: human-confirmed` (visual) bug reaches `verify` in a
forked, unattended context. The verify agent has no runnable command, but it *can* read
`spec.md` — which carries the seeded acceptance criteria, i.e. the expected-after state.
Handed the answer key and no way to run anything, it reads the diff, decides "the fix
looks applied," and logs `verify.green`. That is confirmation bias wearing a verdict, and
it is exactly the false "done" this reference exists to stop. (Recorded as bug-intake
residual seam #2: *`mode: human-confirmed` repros give unattended verify nothing
executable — verify must pause to the human, never self-attest.*)

The fix is a structural one, not a "try harder" instruction: **separate observation from
judgment, and make the observer blind.** The thing that decides "fixed" (the judge) never
sees the running app; the thing that sees the running app (the observer) never sees the
diagnosis, the diff, or the expected outcome. Confirmation bias needs the observer to know
the answer — deny it that and the bias has nowhere to live. This is factory orchestration
pattern 2 (fresh subagent per task, report files over pasted context) applied to a gate.

## When this branch applies

Key off the **repro mode**, read from the `repro.confirmed` event's `data.mode` (or, if
absent, from `items/<id>/repro.md`'s `## Command` — observation steps rather than an
executable command):

- `mode: "command"` → the ordinary verify path (run it, capture verbatim output). This
  reference does not apply.
- `mode: "human-confirmed"`, or any acceptance criterion whose check is *look at the
  screen* with no runnable command → this reference applies.

## Capability gate — no capture, no self-attestation

This branch requires the **App visual capture** capability (see the capabilities skill:
a screenshot-capable driver for the target app is present — e.g. `mcp__maestro__*` for an
iOS sim, a browser-automation tool for web, Playwright). Probe by checking the tool list;
in a forked context, attempt to load a candidate driver via ToolSearch before concluding
absence.

- **Capability absent** → verify cannot obtain a fresh independent observation. Do **not**
  log `verify.green`. Report the stage as needing human confirmation: the dispatcher pauses
  the item `waiting-human` with a packet carrying the repro's observation steps for a human
  to confirm. This is the brain's original requirement (seam #2) and the fail-closed floor.

## The blind observer dispatch

1. **Prepare neutral navigation steps.** From `repro.md`'s `## Command`, extract *only*
   the steps needed to reach the screen/state under test. Strip everything that states or
   hints at what is right or wrong there: delete `## Expected`, delete `## Observed`, and
   scrub any "should look like…", "the misaligned…", "the broken…" phrasing from the steps
   themselves. The observer must be able to reach the screen without learning what it is
   supposed to look like.

2. **Dispatch a fresh subagent** — its entire brief is the navigation steps plus a
   describe-don't-judge instruction. It receives **no** bug report, **no** diagnosis, **no**
   `spec.md`, **no** acceptance criteria, **no** diff, **no** commit message. Template:

   > Launch the app and perform exactly these steps, in order: `<neutral navigation steps>`.
   > Capture a screenshot of the resulting screen and save it under
   > `.factory/items/<id>/verify-shots/`. Then describe, in plain factual terms, exactly
   > what is on that screen — layout, every visible text string, colors, alignment,
   > spacing, and any visual anomaly you notice — as if describing it to someone who cannot
   > see it. Do **not** judge whether anything is correct, expected, or a bug; do **not**
   > guess at intent. Return the saved screenshot path and your verbatim description.

   If the target app's state matters (fresh-fixed build vs. old build), state which build/
   commit to run in the navigation steps — but never why.

3. **Judge the report against the criteria — you, the verify skill, hold the answer key;
   the observer never did.** Read the observer's factual description and open the
   screenshot. For each visual acceptance criterion, decide from *that evidence alone*
   whether **both** hold:
   - (a) the **original failure state is absent** — the specific defect named in
     `repro.md`'s `## Observed` is no longer present in what the observer described/showed;
     **and**
   - (b) the **expected state is present** — what the criterion requires is affirmatively
     visible in the observer's report, not merely "nothing looks wrong."

   Requiring both is what stops a blank/error screen (failure gone, but expected also gone)
   from passing. Do **not** consult the diff to fill a gap in the observation — if the
   observer's report does not let you affirm both conditions, the evidence is insufficient,
   which is a non-pass, not a "probably fine."

4. **Insufficient or ambiguous observation** → re-dispatch **once** with sharper navigation
   (e.g. the observer reached the wrong screen). Still insufficient → do not log
   `verify.green`; report the stage as needing human confirmation (pause path above).

## Writing verify.md

For each visual criterion, the `verify.md` line records: the criterion; the neutral
navigation steps sent to the observer; the saved screenshot path; the observer's verbatim
description; and your judgment naming which piece of evidence satisfies (a) and which
satisfies (b). "Observer said it looks fixed" is not admissible — the observer was
instructed not to judge, so any evaluative language in its report means the blindness
leaked and the observation must be re-run.

## Logging on pass

Only if every visual criterion clears both (a) and (b) from blind evidence, and the rest of
the suite is green, log:

```
factory log ITEM verify.green --data '{"tests":"<counts>","criteria":"<n>/<n>","visual":{"mode":"blind-observer","shots":["items/<id>/verify-shots/<file>"]}}'
```

then advance per the Contract. The `visual` key is evidence for the audit trail;
its absence on a `human-confirmed` item is itself a red flag that this branch was skipped.
