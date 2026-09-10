# approach.rejected: a redesign loop back to spec with forbidden approaches recorded

- id: 0015-approach-rejected-a-redesign-loop-back-t
- stage: done
- kind: backend
- priority: 3

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/reports/0015-approach-rejected-a-redesign-loop-back-t-shipped.html)

## Artifacts
- triage.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0015-approach-rejected-a-redesign-loop-back-t/triage.md)
- spec.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0015-approach-rejected-a-redesign-loop-back-t/spec.md)
- plan.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0015-approach-rejected-a-redesign-loop-back-t/plan.md)
- design/choice.md: no
- reviews/synthesis.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0015-approach-rejected-a-redesign-loop-back-t/reviews/synthesis.md)
- assurance/impact.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0015-approach-rejected-a-redesign-loop-back-t/assurance/impact.json)
- assurance/verdicts.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0015-approach-rejected-a-redesign-loop-back-t/assurance/verdicts.json)

## Recent events
- 2026-08-03T08:22:57Z spend {'dispatches': 2, 'provenance': 'measured', 'source': 'factory-assure-round-2', 'stage': 'assure', 'tokens': {'total': 320418}}
- 2026-08-03T08:22:57Z assure.passed {'non_blocking_fails': 0, 'note': 'two reviewer fail verdicts re-scored by the orchestrator and disclosed in the packet, manifest and verdict notes; findings routed to 0027 (p2) and 0028', 'round': 2, 'scenarios': 13}
- 2026-08-03T08:22:57Z stage.advance {'from': 'assure', 'to': 'ship'}
- 2026-08-03T08:27:23Z ship.merged {'mode': 'auto', 'ref': '9cd4190f765ce2e7a89bead3d98cc5168b0e596e'}
- 2026-08-03T08:27:29Z stage.advance {'from': 'ship', 'to': 'done'}

## Spend
- [proxy] active 1d 01h 08m (waiting 00h 00m), 13 advances, 60 dispatches, 1 rework edges
- [measured] tokens: total 4011314 (17 events)
- [unmeasured] UNMEASURED: orchestrator main-loop tokens
- [measured] stage implement: total 1040083 (10 events)
- [measured] stage review: total 2178549 (3 events)
- [measured] stage verify: total 169204 (2 events)
- [measured] stage assure: total 623478 (2 events)

## Respond
Reply in session, or use the factory CLI to record your decision.

- `/factory:run` — resume the pipeline.
