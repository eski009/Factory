# Scope spend events: a leaf-vs-fork discriminator so measured token totals are trustworthy

- id: 0029-scope-spend-events-a-leaf-vs-fork-discri
- stage: blocked
- kind: backend
- priority: 5
- waiting on you: implement: Task 6 recovery failed twice; cost assertions can still false-pass when primary total or primary zero-leaf readout is corrupted at c6f7062

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/0029-scope-spend-events-a-leaf-vs-fork-discri.html)

## Artifacts
- triage.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0029-scope-spend-events-a-leaf-vs-fork-discri/triage.md)
- spec.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0029-scope-spend-events-a-leaf-vs-fork-discri/spec.md)
- plan.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0029-scope-spend-events-a-leaf-vs-fork-discri/plan.md)
- design/choice.md: n/a (not in this item's sequence)
- reviews/synthesis.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0029-scope-spend-events-a-leaf-vs-fork-discri/reviews/synthesis.md)
- assurance/impact.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0029-scope-spend-events-a-leaf-vs-fork-discri/assurance/impact.json)
- assurance/verdicts.json: no

## Recent events
- 2026-09-07T17:05:24Z spend {'dispatches': 1, 'provenance': 'measured', 'scope': 'leaf', 'source': 'factory-implement', 'stage': 'implement', 'tokens': {'input': 1951832, 'output': 17408}}
- 2026-09-07T17:17:09Z spend {'dispatches': 1, 'provenance': 'measured', 'scope': 'leaf', 'source': 'factory-implement', 'stage': 'implement', 'tokens': {'input': 1422825, 'output': 17387}}
- 2026-09-07T17:17:09Z implement.failed {'attempts': 2, 'task': 'Prove fresh initialization and append-only mixed-ledger compatibility'}
- 2026-09-07T17:17:42Z spend {'dispatches': 1, 'note': 'dispatcher wrapper; collaboration token usage unavailable', 'provenance': 'proxy', 'source': 'factory-dispatch', 'stage': 'implement'}
- 2026-09-07T17:17:42Z stage.advance {'from': 'implement', 'reason': 'implement: Task 6 recovery failed twice; cost assertions can still false-pass when primary total or primary zero-leaf readout is corrupted at c6f7062', 'to': 'blocked'}

## Spend
- [proxy] active 35d 08h 26m (waiting 00h 00m), 5 advances, 38 dispatches, 0 rework edges
- [measured] tokens: input 15954405, output 194434, total 774086 (20 events)
- [unmeasured] UNMEASURED: orchestrator main-loop tokens
- [measured] stage triage: input 754348, output 19738, total 774086 (4 events)
- [measured] stage implement: input 15200057, output 174696 (16 events)

## Respond
Reply in session, or use the factory CLI to record your decision.

- `/factory:run` — resume the pipeline.
