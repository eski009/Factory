# Approach gate at plan: judge convergence before implementation spend

- id: 0014-approach-gate-at-plan-judge-convergence-
- stage: blocked
- kind: backend
- priority: 4
- waiting on you: implement: Task 9 recovery failed twice; interruption after successful prior-record backup unlink can delete the authoritative record and make retry impossible at 66168bf

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/0014-approach-gate-at-plan-judge-convergence-.html)

## Artifacts
- triage.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0014-approach-gate-at-plan-judge-convergence-/triage.md)
- spec.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0014-approach-gate-at-plan-judge-convergence-/spec.md)
- plan.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0014-approach-gate-at-plan-judge-convergence-/plan.md)
- design/choice.md: n/a (not in this item's sequence)
- reviews/synthesis.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0014-approach-gate-at-plan-judge-convergence-/reviews/synthesis.md)
- assurance/impact.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0014-approach-gate-at-plan-judge-convergence-/assurance/impact.json)
- assurance/verdicts.json: no

## Recent events
- 2026-09-07T14:01:04Z spend {'dispatches': 1, 'provenance': 'measured', 'source': 'factory-implement', 'stage': 'implement', 'tokens': {'input': 2232578, 'output': 19972, 'total': 2252550}}
- 2026-09-07T14:16:47Z spend {'dispatches': 1, 'provenance': 'measured', 'source': 'factory-implement', 'stage': 'implement', 'tokens': {'input': 1416563, 'output': 24614, 'total': 1441177}}
- 2026-09-07T14:16:54Z implement.failed {'attempts': 2, 'task': 'Rework Task 9: Keep every judgement-writer mutation inside the repository'}
- 2026-09-07T14:18:00Z spend {'dispatches': 1, 'provenance': 'proxy', 'source': 'factory-dispatch', 'stage': 'implement'}
- 2026-09-07T14:18:00Z stage.advance {'from': 'implement', 'reason': 'implement: Task 9 recovery failed twice; interruption after successful prior-record backup unlink can delete the authoritative record and make retry impossible at 66168bf', 'to': 'blocked'}

## Spend
- [proxy] active 33d 14h 13m (waiting 2d 16h 45m), 17 advances, 91 dispatches, 1 rework edges
- [measured] tokens: input 8310846, output 89834, total 9556072 (20 events)
- [unmeasured] UNMEASURED: orchestrator main-loop tokens
- [measured] stage implement: input 8310846, output 89834, total 9475755 (19 events)
- [measured] stage review: total 80317 (1 events)

## Respond
Reply in session, or use the factory CLI to record your decision.

- `/factory:run` — resume the pipeline.
