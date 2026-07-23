# Model tiering

These patterns assume nothing about the orchestrating model — they are how the factory gets strong-model outcomes from any model. Tiering is the other half of `references/orchestration-patterns.md`: the patterns describe *how* to structure work so weaker models can execute it; this doc says *which* tier to point at which task shape, and it applies to every model choice a stage skill or dispatch makes, not just the orchestrator's own.

The tiers here are abstract on purpose. For the concrete fleet this operator runs — which real model resolves to each tier — see `references/model-routing.md` (fork-local; advisory, not read by the engine).

## The table

| Tier | Use it for | Never use it for |
|---|---|---|
| Cheapest (fast/small) | Transcription implementers executing a plan whose tasks already carry complete code, tests, and commands (pattern 1) — implementation is copying, not designing. Single-file mechanical fixes: rename, apply a one-line patch a review already specified verbatim. | Anything a plan leaves to invent. Any reviewer seat, at any stage. |
| Mid (the floor) | The floor for every reviewer seat — task review, council seats, re-review — regardless of what tier implemented the code under review. Prose-authoring implementers: specs, plans, docs, skill files, anywhere the "plan" is itself the deliverable and there's no lower-tier transcription step beneath it. Multi-file fixes that touch more than one seam. | Whole-branch walks. Architecture decisions. Final pre-ship audits. |
| Most capable | Whole-branch review that walks a flow end-to-end before ship (pattern 4). Architecture and design-gate decisions. Final audits, especially adversarial ones that re-run exploits rather than trust a report. | Routine transcription — burns budget a cheap tier would have handled identically. |

Reviewing is never delegated below the mid tier, full stop — even when the code under review came out of the cheapest tier. A cheap-tier implementer is only safe because a mid-or-higher reviewer is the backstop; drop the reviewer to the cheap tier too and the backstop is gone.

**Who performs the whole-branch walk (pattern 4):** only an orchestrator already running on the most-capable tier may walk the flow inline; an orchestrator running on any lower tier (mid included) must dispatch the walk to a most-capable-tier subagent — a read-only reviewer — and merge its returned trace into the review synthesis rather than attempting the walk itself.

## Signals for upgrading

Start a task at the tier the table above assigns, but move up mid-task on any of these signals rather than waiting for a downstream failure to force the issue:

- **The implementer reports BLOCKED.** A cheap-tier implementer that can't proceed is telling you the task stopped being transcription — it needs a decision the plan didn't make. Upgrading the model on the same task rarely helps; upgrading the *plan* (or handing the task to a mid-tier model that can make the call and document it) does.
- **The task needs invention, not transcription.** If mid-task you notice yourself telling the implementer "use your judgment here," the task shape has silently changed out from under the tier you picked for it.
- **Review must trace across layers.** A reviewer that starts needing to check how a change in one file affects behavior in another has left task-review shape and entered whole-branch-walk shape (pattern 4) — that's a most-capable-tier job even if it surfaced mid-review on what looked like an ordinary task.

## The omitted-model rule

An omitted model choice inherits the parent's model — not the most expensive tier available, not the cheapest, not a "reasonable default." When the orchestrator itself is running on the mid tier, an unspecified dispatch (a walk included) silently inherits mid tier too, one rung below what the table requires for that job. The failure mode is a silent downgrade masquerading as compliance: the stage still reports a pass, and nothing distinguishes "this actually works at the tier the table requires" from "this quietly ran a tier down and got lucky" until someone runs the same stage under a cheaper orchestrator and it breaks. Always choose the tier explicitly, per task, rather than leaving it to inherit — an explicit choice is a claim you can check; an inherited one is a guess wearing a default.
