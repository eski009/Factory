# Factory process feedback — from a real p1 bug run that did not converge

You are working on the Factory codebase (`/Users/anthony/development/projects/Factory`).
This is field feedback from running the pipeline end-to-end on a single p1 bug in a real
product repo (ParkSnap). Treat the evidence as the primary input; the proposals at the
end are suggestions, not instructions.

## What happened

One p1 bug: a UK parking sign with a nested exception window (`No waiting Mon-Sat
8am-7pm` with `Except 8am-4pm 1 hour` inside it). The app told a driver "yes, park for
1 hour" at 4:30pm, when waiting is prohibited outright. Small, well-understood, one
country's rules.

The run so far:

```
21 stage transitions:
idea→triage→spec→plan→implement→review→implement→review→verify→waiting-human→
verify→assure→implement→review→implement→review→verify→assure→waiting-human→
assure→implement

4,914,081 subagent tokens logged (excludes the orchestrator's own main loop)
~6 hours wall clock
4 implement rounds · 4 review passes · 3 verify runs · 2 assure walks
2 review.rejected · 2 assure.rejected (both caps now exhausted)
0 lines merged
```

The originally reported bug is still live in production. Five further live defects were
discovered during the run and none of them were fixed, because the pipeline was fully
occupied with this one item.

**Do not read this as "the gates were too strict."** The gates were mostly right — they
caught two regressions the fix itself introduced that would otherwise have shipped, both
in the dangerous direction (telling a driver they may park when they may not). The
problem is structural, not that the bar was too high.

## What is genuinely working — preserve these

Before changing anything, know what earned its cost:

1. **The repro gate** (`repro.md` + `repro.confirmed` required before plan). This is the
   single highest-value mechanism in the system. It caught a "fix" that passed 588/588
   unit tests and was completely inert against the real defect, because the live model
   emits newline-separated text and the fix only handled the punctuated form. Without a
   live repro that fix ships green.
2. **The fresh-context journey reviewer with a strict input allowlist.** Denying it the
   implementer transcript, review/verify conclusions, diffs and git history made it find
   driver-facing defects no code review could see. On the second walk I also added the
   *previous walk's findings and the human's scope decision* to its deny-list, so it
   formed its own expectations instead of re-testing a prior reviewer's conclusions.
   That change improved the walk. Consider making it the default.
3. **Execution over reports.** Council seats withdrew blocking votes when a command was
   actually run and refuted their premise. One implementer pushed back on a reviewer
   finding with an isolating experiment and was right. That culture is working.
4. **Red-run proof at the true pre-item baseline.** Verify copied current tests into a
   detached worktree at the original pre-fix commit and confirmed 7 failures there. That
   is real evidence, not ceremony.

## Defect 1 — `verify` has no backward edge, so a verify failure strands the item

`scripts/factory/lib/machine.py:264-296`. The only backward transitions are:

```python
elif frm == "review" and to == "implement":     # :279
elif frm == "assure" and to == "implement":     # :282
else:
    expected = next_stage(meta)                  # :286
    if to != expected:
        raise GateError(f"illegal transition {frm} -> {to} ...")
```

There is no `verify → implement`. When verify failed (a real failure — the explanation
prose contradicted the refusal), the item could not legally go anywhere: forward to
`assure` is gated on `verify.green`, and backward is refused. The orchestrator had to
park it at `waiting-human` and ask a human how to route a fix, for a defect the verify
stage had already diagnosed precisely and handed over a remedy for.

`review` and `assure` both have rework edges. `verify` should too, capped the same way.

## Defect 2 — there is no "this approach is wrong" exit, only "polish it more"

The engine's entire vocabulary for a failing gate is reject → rework → cap → `blocked`.
And `blocked` is not a redirect: `SPECIAL` items may only resume to their own
`paused-from` (`machine.py:274-277`), so a blocked-at-assure item can only return to
`assure`. **There is no edge from any late stage back to `spec` or `plan`.**

That matters because the failure here was not a bad implementation of a good design. It
was a good implementation of a design that cannot converge. The chosen approach was
"deterministic post-processing invariants that parse and rewrite the LLM's own free
text." Over four rounds that accumulated:

```
detectNestedExceptionWindow, findNestedExceptionStructures, Invariants 0i / 0j / 0k,
PROHIBITION_LINE, ALLOWANCE_LINE, RESTRICTION_SCOPE_PROSE, allowanceGovernsRange,
permissionGovernsAnaphora, day-token gate, SEGMENT_BOUNDARY, trailingWhitespace
```

Every new rule is a regex over natural language, and every one has its own failure modes
that the next round finds. Natural language has unbounded phrasing, so the rule set has
an unbounded tail. By the last two rounds the implementers were writing *deliberate
coverage losses* and a `KNOWN WRONG` section into their own residual notes — honest, and
also the sound of an approach admitting it cannot finish.

The pipeline had no way to say so. It could only keep spending rework rounds, and the
caps decided when polishing stopped rather than whether the design was right.

**Suggestion:** a stage skill (or the orchestrator) should be able to return
`approach.rejected` — distinct from `review.rejected` — routing the item back to `spec`
with the accumulated evidence, and resetting the rework counters because it is a new
design. Cap that too (once or twice), so it cannot loop either. Without this, a wrong
approach is structurally indistinguishable from a sloppy implementation.

## Defect 3 — `assure` gates an item on defects it did not cause

The journey reviewer walks the whole journey. The journey contains pre-existing defects
the item never touched. So the item cannot pass.

Concretely: of the seven required scenarios, the item's own change was correct in all of
them. It failed assure twice on stale `nextRestrictionAt` values rendering "Move by
16:00" at 8pm — a *different, already-filed item's* defect — and on render code that
gates a card on `restrictions.length` rather than `hasRestrictions`, which predates the
item entirely.

The human had to intervene twice with scope decisions to stop the item absorbing
unrelated work. Both times the correct answer was "that failure is real, and it is not
this item's."

**Suggestion:** `verdicts.json` should carry a per-scenario attribution — `regression`
(this change caused it), `pre-existing` (reproducible on the base commit),
`out-of-scope` (owned by a named item). The ship gate should block only on `regression`.
The engine can determine `pre-existing` mechanically: re-run the failing scenario against
the merge base. That single check would have removed both human interventions and both
assure rework rounds.

## Defect 4 — scope narrowing is an unsupported convention

When the human narrowed scope after an assure rejection, there was no engine artifact for
it. The orchestrator invented `assurance/rework-scope.md` by hand and hoped the implement
skill would read it. It did, but only because the file happened to be in the item
directory and the skill happened to look.

**Suggestion:** make scope a first-class, engine-validated artifact — something like
`factory scope ITEM --in S2 --waive S3,S4,S7 --reason "..."` — that stage skills receive
as structured input and the assure gate honours automatically, rather than a markdown
file passed by convention and goodwill.

## Defect 5 — nothing notices cost

4.9M tokens on one p1 bug with nothing merged, while five worse defects sat live in
production. The spend data was being logged correctly the whole time (`factory log ITEM
spend`), and `factory cost` exists to read it. Nothing acts on it.

The target repo's own `CLAUDE.md` carries a "polish gate" rule — *do not start a polish
pass while known user-facing bugs remain* — and the pipeline violated it for six hours
without noticing, because no stage compares an item's marginal spend against the backlog
it is starving.

**Suggestion:** a soft circuit breaker. When an item's logged spend crosses a multiple of
the median for its tier, or when its rework count exceeds N, park it and surface the
tradeoff: *"this item has consumed X; the backlog contains Y items at p1; continue,
narrow, or defer?"* Advisory, not a hard stop. Note `factory cost` currently requires an
item argument and has no aggregate mode — a backlog-wide view would help here.

## Defect 6 — unverified behavioural claims propagate freely

Eight separate instances in this one item of a claim about runtime behaviour being
written into a docstring, spec, or review artifact **without ever being executed**, then
inherited by the next reader as established fact. At least three different agents did it,
including the orchestrator.

The sharpest instance: a false sentence entered a docstring in one commit, was copied
into spec prose in the next, and was only caught because copying it put it in front of a
fresh reader. Code review reviews the code; nothing re-derives the prose describing it.
A wrong claim in a docstring can survive indefinitely.

Related: a corpus figure ("12 of the 36") was wrong, propagated into the council
synthesis, the code comments, and the test comments, and had to be corrected in four
places after being independently recomputed three times.

**Suggestion:** require that any behavioural claim in a review/spec artifact cite the
command that produced it, the way `repro.md` already requires for the repro. The repro
gate proves the pattern works — extend it to claims, not just repros.

## Defect 7 — bids accumulate unjudged, and stale ones are dangerous

27 bids filed, 12 still unjudged at the point this feedback was written, including three
at severity `high`. Worse, `bid-0003` (high) asserts that `shared/post-processing.ts` is
"442 lines BEHIND its supabase copy" — that was true when filed, and was fixed and
shipped by a *different item* in the same repo. Merging it now would inject a false fact
into `constraints.md` and mislead every future item into hand-editing generated files.

Nothing re-checks a bid's premise before it is merged into the brain, and nothing expires
bids whose claims have been overtaken.

**Suggestion:** bids should carry a verifiable premise (a command, a file:line assertion)
re-checked at judgement time, and judgement should be a gate on `ship` rather than a
background chore that silently accumulates.

## Smaller things

- `factory cost` requires an item argument; no aggregate/backlog view exists.
- The journey contract's documented launch command
  (`set -a && source .env.global && set +a`) fails on a malformed line and echoes a
  secret fragment to stdout. Two separate reviewers hit it and worked around it. Nothing
  validates that a contract's `Run & fixtures` block actually runs.
- Stage skills lose sub-agent replies when a skill name is re-bound to a newer agent
  mid-run; several sub-agents reported "the original sender may never see this."
- Fresh-round evidence handling: the assure skill says to *delete* the prior round's
  evidence. Archiving it to `round-N/` preserved provenance and cost nothing — worth
  making the documented behaviour.

## The one-line version

The Factory is good at proving a change is wrong and bad at noticing when the *approach*
is wrong. It has rework loops but no redesign loop, it gates items on defects they did
not cause, and nothing watches the cost of an item against the backlog it is blocking.
Fix those three and the same run finishes in a fraction of the spend.
