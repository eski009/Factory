# Measurement spike: gap-capped per-pass attributed_seconds, and whether any threshold separates a runaway from healthy work

- id: 0030-measurement-spike-gap-capped-per-pass-at
- stage: blocked
- kind: backend
- priority: 6
- waiting on you: implement: Task 2 recovery failed twice; splitlines treats U+0085/U+2028/U+2029 inside valid JSON strings as ledger delimiters, dropping valid records at ac13ce5

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/0030-measurement-spike-gap-capped-per-pass-at.html)

## Artifacts
- triage.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0030-measurement-spike-gap-capped-per-pass-at/triage.md)
- spec.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0030-measurement-spike-gap-capped-per-pass-at/spec.md)
- plan.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0030-measurement-spike-gap-capped-per-pass-at/plan.md)
- design/choice.md: n/a (not in this item's sequence)
- reviews/synthesis.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0030-measurement-spike-gap-capped-per-pass-at/reviews/synthesis.md)
- assurance/impact.json: no
- assurance/verdicts.json: n/a (not in this item's sequence)

## Recent events
- 2026-09-07T19:08:33Z spend {'dispatches': 1, 'provenance': 'measured', 'source': 'factory-implement', 'stage': 'implement', 'tokens': {'input': 487501, 'output': 4724}}
- 2026-09-07T19:16:04Z spend {'dispatches': 1, 'provenance': 'measured', 'source': 'factory-implement', 'stage': 'implement', 'tokens': {'input': 336941, 'output': 12156}}
- 2026-09-07T19:16:04Z implement.failed {'attempts': 2, 'task': 'Task 2: Pin immutable cohorts and the tolerant source-snapshot boundary'}
- 2026-09-07T19:16:35Z spend {'dispatches': 1, 'note': 'dispatcher wrapper; collaboration token usage unavailable', 'provenance': 'proxy', 'source': 'factory-dispatch', 'stage': 'implement'}
- 2026-09-07T19:16:35Z stage.advance {'from': 'implement', 'reason': 'implement: Task 2 recovery failed twice; splitlines treats U+0085/U+2028/U+2029 inside valid JSON strings as ledger delimiters, dropping valid records at ac13ce5', 'to': 'blocked'}

## Spend
- [proxy] active 35d 10h 25m (waiting 00h 00m), 5 advances, 22 dispatches, 0 rework edges
- [measured] tokens: input 4140859, output 84466 (10 events)
- [unmeasured] UNMEASURED: orchestrator main-loop tokens
- [measured] stage triage: input 557966, output 17254 (2 events)
- [measured] stage implement: input 3582893, output 67212 (8 events)

## Respond
Reply in session, or use the factory CLI to record your decision.

- `/factory:run` — resume the pipeline.
