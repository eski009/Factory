# Assure attribution: gate only on regressions this item caused

- id: 0013-assure-attribution-gate-only-on-regressi
- stage: done
- kind: backend
- priority: 2

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/0013-assure-attribution-gate-only-on-regressi.html)

## Artifacts
- triage.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0013-assure-attribution-gate-only-on-regressi/triage.md)
- spec.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0013-assure-attribution-gate-only-on-regressi/spec.md)
- plan.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0013-assure-attribution-gate-only-on-regressi/plan.md)
- design/choice.md: no
- reviews/synthesis.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0013-assure-attribution-gate-only-on-regressi/reviews/synthesis.md)
- assurance/impact.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0013-assure-attribution-gate-only-on-regressi/assurance/impact.json)
- assurance/verdicts.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0013-assure-attribution-gate-only-on-regressi/assurance/verdicts.json)

## Recent events
- 2026-08-02T19:23:28Z spend {'dispatches': 1, 'provenance': 'measured', 'source': 'factory-assure', 'stage': 'assure', 'tokens': {'total': 128970}}
- 2026-08-02T19:23:28Z assure.passed {'non_blocking_fails': 2, 'note': 'both pre-existing with fairness controls in transcripts; 9/9 required scenarios pass', 'owners': ['0025-round-scope-all-rework-gates-implement-c', '0023-packet-furniture-and-readout-polish-drop'], 'round': 2}
- 2026-08-02T19:23:28Z stage.advance {'from': 'assure', 'to': 'ship'}
- 2026-08-02T19:27:13Z ship.merged {'mode': 'auto', 'ref': '3596906373abc71427f1506d2127d1ba7be41a5f'}
- 2026-08-02T19:27:13Z stage.advance {'from': 'ship', 'to': 'done'}

## Spend
- [proxy] active 04h 15m (waiting 07h 52m), 15 advances, 41 dispatches, 1 rework edges
- [measured] tokens: total 1835156 (18 events)
- [unmeasured] UNMEASURED: orchestrator main-loop tokens
- [measured] stage triage: total 87877 (1 events)
- [measured] stage spec: total 119266 (1 events)
- [measured] stage implement: total 790990 (9 events)
- [measured] stage review: total 486984 (4 events)
- [measured] stage verify: total 86726 (1 events)
- [measured] stage assure: total 263313 (2 events)

## Respond
Reply in session, or use the factory CLI to record your decision.

- `/factory:run` — resume the pipeline.
