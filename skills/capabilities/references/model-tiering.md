# Model tiering

These patterns assume nothing about the orchestrating model — they are how the factory gets strong-model outcomes from any model. Tiering is the other half of `references/orchestration-patterns.md`: the patterns describe *how* to structure work so weaker models can execute it; this doc says *which* tier to point at which task shape, and it applies to every model choice a stage skill or dispatch makes, not just the orchestrator's own.

## The table

| Tier | Use it for | Never use it for |
|---|---|---|
| Cheapest (fast/small) | Transcription implementers executing a plan whose tasks already carry complete code, tests, and commands (pattern 1) — implementation is copying, not designing. Single-file mechanical fixes: rename, apply a one-line patch a review already specified verbatim. | Anything a plan leaves to invent. Any reviewer seat, at any stage. |
| Mid (the floor) | The floor for every reviewer seat — task review, council seats, re-review — regardless of what tier implemented the code under review. Prose-authoring implementers: specs, plans, docs, skill files, anywhere the "plan" is itself the deliverable and there's no lower-tier transcription step beneath it. Multi-file fixes that touch more than one seam. | Whole-branch walks. Architecture decisions. Final pre-ship audits. |
| Most capable | Whole-branch review that walks a flow end-to-end before ship (pattern 4). Architecture and design-gate decisions. Final audits, especially adversarial ones that re-run exploits rather than trust a report. | Routine transcription — burns budget a cheap tier would have handled identically. |

Reviewing is never delegated below the mid tier, full stop — even when the code under review came out of the cheapest tier. A cheap-tier implementer is only safe because a mid-or-higher reviewer is the backstop; drop the reviewer to the cheap tier too and the backstop is gone.

## Signals for upgrading

Start a task at the tier the table above assigns, but move up mid-task on any of these signals rather than waiting for a downstream failure to force the issue:

- **The implementer reports BLOCKED.** A cheap-tier implementer that can't proceed is telling you the task stopped being transcription — it needs a decision the plan didn't make. Upgrading the model on the same task rarely helps; upgrading the *plan* (or handing the task to a mid-tier model that can make the call and document it) does.
- **The task needs invention, not transcription.** If mid-task you notice yourself telling the implementer "use your judgment here," the task shape has silently changed out from under the tier you picked for it.
- **Review must trace across layers.** A reviewer that starts needing to check how a change in one file affects behavior in another has left task-review shape and entered whole-branch-walk shape (pattern 4) — that's a most-capable-tier job even if it surfaced mid-review on what looked like an ordinary task.

## The omitted-model rule

An omitted model choice silently inherits the most expensive tier available, not the cheapest, not a "reasonable default." That's a safe failure mode for cost but not for one it can mask: if the reason a stage is passing is that it silently escalated a task's tier rather than that the process actually works at the tier you intended, you won't find out until someone deliberately runs it on a cheap tier and it fails. Always choose the tier explicitly, per task, rather than leaving it to inherit — an explicit choice is a claim you can check; an inherited one is a guess wearing a default.
