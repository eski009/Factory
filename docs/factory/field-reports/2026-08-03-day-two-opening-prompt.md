# Day-two opening prompt — Factory hardening batch

> Paste this file as the opening prompt (or point the session at it):
> `docs/factory/field-reports/2026-08-03-day-two-opening-prompt.md`
> It is self-contained; yesterday's session context is not required.

You are continuing work on the Factory repo
(`/Users/anthony/development/projects/factory`). Yesterday's session is
summarized below with exact state. Read this whole file before running
anything, then follow **The sequence**. Do not re-derive the plan.

## Why this batch exists (one paragraph)

A real p1 bug run in ParkSnap (a target repo) consumed 4.9M subagent tokens
over ~6h across 4 implement rounds and merged nothing — full report at
`docs/factory/field-reports/2026-08-02-parksnap-p1-nonconvergence.md`. Its
one-line diagnosis: the Factory has no redesign loop, gates items on defects
they did not cause, and nothing watches cost. Items 0013–0018 are the fix
batch. **The ultimate acceptance test is that same ParkSnap bug, re-run
through the improved pipeline, merging a fix at a fraction of 4.9M. That bug
is still live in production.**

## Scorecard after day one (2026-08-02)

| Objective | State |
|---|---|
| Nothing watches cost | **SHIPPED** — 0016 merged to `main` at `45652c7` (33 files, +4609/−89, suite 738 green): per-stage token attribution, `factory cost --all`, engine-authoritative rework counter (backward `stage.advance` edges), churn breaker + park/answer/resume protocol |
| Assure gates on others' defects | **NOT MET** — 0013 at `implement`, plan needs re-judging first (see sequence step 1) |
| No redesign loop / no `verify→implement` edge | **NOT MET** — 0015 at `idea`, p3 |
| Approach gate at plan | **NOT MET** — 0014 at `idea`, p4 (deliberately last: 0015 is the cure that makes prevention affordable) |
| Breaker catches spend runaways | **HALF MET** — churn arm shipped; 0018 (wall-clock arm, `idea`, p5) exists because day one proved the churn arm is blind to the no-churn/high-spend shape: 0016 itself hit ~4M measured tokens with only 2 rework edges |
| The ParkSnap p1 bug | **UNTOUCHED — still live**, plus five further defects found beside it |

Day one's honest cost: ~4M measured tokens on 0016 alone (upper bound — the
spend convention double-counts nested dispatches, bid-0063). The instrument
shipped; the savings are not yet demonstrated.

## Current pipeline state (verified at close of day one)

- `main` at `693b23f`; branch `factory/0016-…` merged and deleted.
- **0016 done.** Breaker is LIVE in this repo: `.factory/config.json` has
  `gates: ["design","cost"]` — a third rework edge on any item will require
  `factory cost-answer` before re-entering implement. Note `.factory/` is
  gitignored, so this opt-in exists only in the working tree.
- **0013 at `implement`, p2** — unparked by hand at 0016's ship. Its 2,609-line
  11-task plan (Task 9 struck at 0016's triage) predates the instrument.
- 0015 p3, 0014 p4, 0018 p5 at `idea`. **0017 has NO priority** — `factory
  next` will never return it; give it one or park it explicitly.
- 0005 / 0006 / 0011 blocked (pre-date this batch); packets outstanding.
- Assure report with 3 unresolved judgement calls + 11 advisories:
  `docs/factory/packets/reports/0016-cost-circuit-breaker-on-engine-authorita-assure.md`.
  Both journey contracts (J-001, J-002) are DRAFT and unratified.

## The sequence (do in order; get human sign-off at each ▲)

1. **Re-judge and narrow 0013's plan — in STEP MODE, before any implement
   dispatch.** ▲
   The deal recorded when 0013 was parked: its plan is re-judged against
   measured numbers now that the instrument exists. Implement measured at
   57–77% of item cost on comparable items, so cut the plan to the
   attribution core — verdicts schema (`attribution: regression|pre-existing`),
   merge-base re-run primitives, ship-gate rule ladder — and shed the readout/
   CLI periphery (packet readout, `status --json` surface, `file-base-defect`)
   into a follow-up item. Present the narrowed plan to the human before
   dispatching implement. Do NOT run item mode on 0013 — day one's death-loop
   feeling was item-mode momentum meeting a growing item; every stage
   continuation is the human's call today.
2. **Ship 0013** (narrowed) through the normal gates.
3. **Ship 0015** — `verify → implement` capped rework edge + `approach.rejected`
   redesign loop back to spec with a forbidden-approaches artifact. Item body
   already carries the design constraints.
4. **Ship 0018** — wall-clock arm on `active_seconds` (already engine-computed
   in `cost.summarize`; excludes `waiting_seconds`). Its item body carries the
   calibration protocol: replay all real logs, record which items each
   candidate threshold would have parked. AC2: replaying 0016's own log fires
   at the end of its first implement pass (02h40m, 1.99M tokens, 0 edges).
5. **The acceptance test** ▲ — re-run the ParkSnap p1 bug (nested exception
   window, `No waiting Mon-Sat 8am-7pm` / `Except 8am-4pm 1 hour`) through the
   improved pipeline in the ParkSnap repo. Pass = fix merged AND
   `factory cost` shows a small fraction of 4.9M. This is the only step that
   proves the batch met its objective.
6. 0014 (approach gate) afterward, if the acceptance test still shows
   implement rounds being spent on doomed designs.

## Hygiene before new work (30–60 min, do first in the session)

1. **Judge the ~14 unjudged bids** (bid-0058 … bid-0090, `factory judge`).
   Highest-leverage: **bid-0063** (spend convention double-counts nested
   dispatches — inner fork logged 119,266 while the harness reported the whole
   fork at 98,841; no aggregate is trustworthy) and **bid-0084**
   (`ship.obligation` events are decorative — nothing reads them; 0013's
   unpark had to be done by hand). **bid-0090**: the breaker has no ungated
   advisory mode — `fired` requires the `cost` gate, so default installs get
   nothing on a firing edge; item prose says "soft/advisory" and is wrong.
2. **File four pipeline-defect items** (evidence lives only in day one's run;
   file from these notes):
   - **Shared-scratchpad message clobber:** two agents in one session share a
     scratchpad path; a concurrent `git commit --amend` reused a stale
     commit-message file and shipped the wrong commit body (observed on 0016
     rework, reflog `ae205c4 → f609d24`; fixed by a second amend `439d083`).
   - **Concurrent implementers in one checkout:** Task 13's agent was
     committing while Task 14's dispatch edited `tests/test_packet.py` in the
     same working tree — factory-implement's own one-at-a-time contract was
     violated by its own sub-dispatches; the Task 13 agent had to verify
     against a `git archive` export because the shared tree was deliberately
     red.
   - **Parent agents block on child replies that never arrive:** the implement
     skill stalled twice ("waiting on the Task N follow-up") with the work
     already complete and committed on disk; recovery required an orchestrator
     resume. Same class as the field report's "lost sub-agent replies". The
     dispatcher's fail-twice-then-block rule cannot distinguish "can't do the
     work" from "can't hear the answer" and would have blocked a green item.
   - **Gitignored `.factory/` state is invisible to clones:** ticked plans,
     spec amendments, the `cost`-gate opt-in, and every `cost/answer.md` exist
     only in the working tree; a fresh clone gets the code and none of the
     decisions.
3. **Answer the 3 judgement calls in the 0016 assure report** (one-job-per-
   screen furniture, LOWER BOUND suffix scope, one-action oracle wording) and
   ratify or edit the two DRAFT contracts — each answer binds every future run.
4. Give **0017** a priority or park it.

## Operating guardrails for today

- **Step mode, not item mode**, for 0013 until its narrowed plan is approved.
- The cost breaker is live in this repo — if it fires, park and put the
  continue/narrow/defer question to the human; never answer it yourself.
- Mutation/verification runs: use `PYTHONDONTWRITEBYTECODE=1` (same-second
  same-length edits produce stale-but-valid `.pyc`; bit day one twice).
- Any suite count read while subagents are writing is provisional — require
  two identical consecutive runs before reporting it.
- Never revert or clean up working-tree changes you did not author.
- Spend logging: log per the convention, but do not add a dispatcher-level
  fork event on top of a stage skill's own events until bid-0063 is resolved —
  note the omission instead.

## Where everything is

| Thing | Path |
|---|---|
| ParkSnap field report (the origin) | `docs/factory/field-reports/2026-08-02-parksnap-p1-nonconvergence.md` |
| 0016 assure report (judgement calls + polish) | `docs/factory/packets/reports/0016-…-assure.md` |
| 0016 shipped packet | `docs/factory/packets/reports/0016-…-shipped.md` |
| 0013 item + plan | `.factory/items/0013-assure-attribution-gate-only-on-regressi/` |
| Journey contracts (both DRAFT) | `docs/factory/journeys/contracts/J-001…, J-002…` |
| Breaker engine | `scripts/factory/lib/breaker.py` (threshold 2, `REWORK_FROM`) |
| Cost instrument | `scripts/factory/lib/cost.py` (`summarize`, `summarize_all`) |
