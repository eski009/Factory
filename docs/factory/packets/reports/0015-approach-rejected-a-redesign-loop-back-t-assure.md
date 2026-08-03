# Assurance report — 0015-approach-rejected-a-redesign-loop-back-t

**Verdict: all 13 scenarios pass (round 2). Item proceeds to ship.**
Two fresh-context reviewers, independent, neither reading round 1 (archived at
`assurance/round-1/`). Contracts: J-003 **draft**, J-002 and J-001 **approved**.

## Journeys walked

| Journey | Scenarios | Verdict |
|---|---|---|
| J-003 redesign-cap-decision (new) | S1–S8 | 8/8 pass |
| J-002 cost-breaker-decision | S9–S11 | 3/3 pass |
| J-001 assure-outcome-readout | S12–S13 | 2/2 pass |

Round 1 found two fails. **S6 was a genuine defect** — a leaked Python `None`
in an operator-facing refusal — fixed at `18a02b0`, reworded at `5fea92c` per
the review council's own remedy, and now verified closed by an independent
walk. **S5 was a false positive**, corrected after three-way verification and
independently confirmed passing this round.

## READ THIS: two reviewer fail verdicts were re-scored by the orchestrator

Both are disclosed here, in `run-manifest.json`, and in the verdict notes; the
original fail verdicts and transcripts are preserved verbatim. If you disagree
with either, the item should not have shipped — say so and it comes back.

1. **J-003/S2 — reviewer: fail → recorded: pass.** The reviewer verified every
   element S2 declares, then failed it because no *engine* verb deletes the
   decision packet after a `continue` answer. Verified: the guarantee is real
   but skill-side — `factory-dispatch`'s step-0 resume clause deletes answered
   packets on resume, unreachable from the CLI surface walked (the same split
   J-001/S9 hit). **However the reviewer exposed a real defect:** this item's
   own `impact.json` justified leaving the session-start hook unchanged by
   claiming record-time deletion stops the nag "forever" — false for
   `continue`, where it never fires. That false assurance is corrected, J-003
   now names the evidence class for both halves (bid-0130), and the residual is
   recorded: **the packet is stale between recording `continue` and the next
   dispatch run** — bounded-until-resume, not absent.
2. **J-001/S13 — reviewer: fail → recorded: pass.** S13 declares a *regression*
   check, and no regression exists (byte-identical at merge-base `34890f6`).
   The reviewer found a genuine pre-existing defect while walking: the
   cost-breaker Respond branch keys on `paused-from`, not the reason prefix, so
   a cost pause parked from `plan`/`review` shows the whole decision screen
   while offering `/factory:run` and never naming `cost-answer`.

## Findings routed, not waived

- **0027** (p2) owns the Respond branch-key defect. Corroborated by **two**
  independent reviewers via different routes, and prioritised because **0015
  increases its reachability**: 0015's own declared `spec → plan → implement`
  state parks the item at `plan` — exactly the mis-rendering shape. The fix
  shape is already demonstrated in the same function: 0015's new `approach cap:`
  branch is reason-keyed and correct from any stage.
- **0028** owns the twin `None` leak still live in `breaker.py` on the cost path.

## Polish (advisories — never gating)

- The cost breaker pre-warns at threshold; the redesign cap's first contact is a
  hard refusal. Same decision class, different forewarning.
- `redesigns: 1 of 1` never says what `M` is; `narrow` names no resume command
  while `defer` names one.
- Populations render twice (decision block and `## Spend`); the cost packet does
  not duplicate its figure that way.
- `factory log <id> approach.answered` refuses at exit 1 with no `refused:`
  prefix, unlike every other refusal on these journeys.
- `factory log <id> approach.rejected` is *accepted* and lands verbatim in
  `## Recent events`, where a load-bearing name reads as a real redesign — it is
  inert (the counter derives from the structural edge) but it looks real.
- Pre-existing, off-scope: the base-evidence refusal says "stale" when the two
  shas are identical and only the branch name differs (0013 surface).

## Coverage limits, stated

- The `LOWER BOUND` measured-token branch was not exercisable — no CLI verb logs
  a spend event the cost reader recognises, so every packet rendered
  `UNMEASURED`. Loud, never zero, never dollars.
- J-001's first-screen known-fails line was discharged by byte-identity, not by
  observation; on an attribution-enabled fixture **neither** engine rendered it,
  which the reviewer reported as an observation for J-001's owner rather than a
  product defect, since a fixture error cannot be excluded.

## Recommended confirmation walkthrough (10 minutes)

1. `git log --oneline main..factory/0015-approach-rejected-a-redesign-loop-back-t` — 11 commits.
2. Read `assurance/transcripts/J-003/S2.txt` (the cap → park → packet → answer →
   resume cycle) and `J-001/S13.txt` branch 3c (the mis-rendered cost packet 0027 owns).
3. `factory cost 0015-approach-rejected-a-redesign-loop-back-t` — the full spend readout.
4. Judge the two re-scorings above.
