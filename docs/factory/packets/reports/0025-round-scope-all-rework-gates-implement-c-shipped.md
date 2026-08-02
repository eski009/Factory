# Round-scope all rework gates: implement.completed, review.approved and verify.green accept prior-round evidence

- id: 0025-round-scope-all-rework-gates-implement-c
- stage: done
- kind: backend
- priority: 2

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/0025-round-scope-all-rework-gates-implement-c.html)

## Artifacts
- triage.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0025-round-scope-all-rework-gates-implement-c/triage.md)
- spec.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0025-round-scope-all-rework-gates-implement-c/spec.md)
- plan.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0025-round-scope-all-rework-gates-implement-c/plan.md)
- design/choice.md: no
- reviews/synthesis.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0025-round-scope-all-rework-gates-implement-c/reviews/synthesis.md)
- assurance/impact.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0025-round-scope-all-rework-gates-implement-c/assurance/impact.json)
- assurance/verdicts.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0025-round-scope-all-rework-gates-implement-c/assurance/verdicts.json)

## Recent events
- 2026-08-02T21:55:47Z spend {'dispatches': 1, 'provenance': 'measured', 'source': 'factory-assure', 'stage': 'assure', 'tokens': {'total': 95908}}
- 2026-08-02T21:55:47Z assure.passed {'non_blocking_fails': 0, 'round': 1}
- 2026-08-02T21:55:47Z stage.advance {'from': 'assure', 'to': 'ship'}
- 2026-08-02T21:58:23Z ship.merged {'mode': 'auto', 'ref': '9e5b014637a92d342b39a51c41eff07af3f08ddd'}
- 2026-08-02T21:58:23Z stage.advance {'from': 'ship', 'to': 'done'}

## Spend
- [proxy] active 02h 36m (waiting 00h 00m), 9 advances, 14 dispatches, 0 rework edges
- [measured] tokens: total 794702 (7 events)
- [unmeasured] UNMEASURED: orchestrator main-loop tokens
- [measured] stage implement: total 528926 (4 events)
- [measured] stage review: total 169868 (2 events)
- [measured] stage assure: total 95908 (1 events)

## Respond
Reply in session, or use the factory CLI to record your decision.

- `/factory:run` — resume the pipeline.
