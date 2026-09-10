# Cost circuit breaker on engine-authoritative rework counts

- id: 0016-cost-circuit-breaker-on-engine-authorita
- stage: done
- kind: backend
- priority: 1

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/0016-cost-circuit-breaker-on-engine-authorita.html)

## Artifacts
- triage.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0016-cost-circuit-breaker-on-engine-authorita/triage.md)
- spec.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0016-cost-circuit-breaker-on-engine-authorita/spec.md)
- plan.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0016-cost-circuit-breaker-on-engine-authorita/plan.md)
- design/choice.md: no
- reviews/synthesis.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0016-cost-circuit-breaker-on-engine-authorita/reviews/synthesis.md)
- assurance/impact.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0016-cost-circuit-breaker-on-engine-authorita/assurance/impact.json)
- assurance/verdicts.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0016-cost-circuit-breaker-on-engine-authorita/assurance/verdicts.json)

## Recent events
- 2026-08-02T16:01:27Z spend {'dispatches': 2, 'provenance': 'measured', 'source': 'factory-assure', 'stage': 'assure', 'tokens': {'total': 239882}}
- 2026-08-02T16:01:27Z assure.passed {'contract_status': 'both draft', 'human_direction': '2026-08-02 end the run at this pass; contract-level findings filed not reworked; J-001 contract amended 3->4 permitted diffs citing S11 evidence', 'journeys': 'J-001,J-002', 'scenarios': '11/11'}
- 2026-08-02T16:01:27Z stage.advance {'from': 'assure', 'to': 'ship'}
- 2026-08-02T16:03:40Z ship.merged {'mode': 'auto', 'ref': '45652c72e1d5cb3f792ee5d2274b493790857411'}
- 2026-08-02T16:03:40Z stage.advance {'from': 'ship', 'to': 'done'}

## Spend
- [proxy] active 08h 13m (waiting 00h 31m), 15 advances, 63 dispatches, 2 rework edges
- [measured] tokens: total 3949630 (19 events)
- [unmeasured] UNMEASURED: orchestrator main-loop tokens
- [measured] stage implement: total 3124962 (16 events)
- [measured] stage review: total 584786 (2 events)
- [measured] stage assure: total 239882 (1 events)

## Respond
Reply in session, or use the factory CLI to record your decision.

- `/factory:run` — resume the pipeline.
