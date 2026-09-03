# Independent council review defaults to two seats with risk-triggered escalation

- id: 0034-independent-council-review-defaults-to-t
- stage: blocked
- kind: backend
- priority: 1
- waiting on you: review: rejected too many times

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/0034-independent-council-review-defaults-to-t.html)

## Artifacts
- triage.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0034-independent-council-review-defaults-to-t/triage.md)
- spec.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0034-independent-council-review-defaults-to-t/spec.md)
- plan.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0034-independent-council-review-defaults-to-t/plan.md)
- design/choice.md: n/a (not in this item's sequence)
- reviews/synthesis.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0034-independent-council-review-defaults-to-t/reviews/synthesis.md)
- assurance/impact.json: no
- assurance/verdicts.json: n/a (not in this item's sequence)

## Recent events
- 2026-08-15T17:16:30Z spend {'dispatches': 2, 'provenance': 'proxy', 'source': 'factory-review', 'stage': 'review'}
- 2026-08-15T17:18:22Z spend {'dispatches': 1, 'provenance': 'proxy', 'source': 'factory-review', 'stage': 'review'}
- 2026-08-15T17:19:25Z review.rejected {'round': 3}
- 2026-08-15T17:19:34Z stage.advance {'from': 'review', 'reason': 'review: rejected too many times', 'to': 'blocked'}
- 2026-08-15T17:20:18Z spend {'dispatches': 1, 'provenance': 'proxy', 'source': 'factory-dispatch', 'stage': 'review'}

## Spend
- [proxy] active 8d 07h 16m (waiting 19d 12h 43m), 16 advances, 72 dispatches, 2 rework edges
- [measured] tokens: none logged
- [unmeasured] UNMEASURED: orchestrator main-loop tokens

## Respond
Reply in session, or use the factory CLI to record your decision.

- `/factory:run` — resume the pipeline.
