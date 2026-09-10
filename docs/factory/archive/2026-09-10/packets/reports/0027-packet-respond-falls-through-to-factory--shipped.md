# Packet Respond falls through to /factory:run when a decision pause is parked from an unexpected stage

- id: 0027-packet-respond-falls-through-to-factory-
- stage: done
- kind: backend
- priority: 2

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/reports/0027-packet-respond-falls-through-to-factory--shipped.html)

## Artifacts
- triage.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0027-packet-respond-falls-through-to-factory-/triage.md)
- spec.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0027-packet-respond-falls-through-to-factory-/spec.md)
- plan.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0027-packet-respond-falls-through-to-factory-/plan.md)
- design/choice.md: no
- reviews/synthesis.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0027-packet-respond-falls-through-to-factory-/reviews/synthesis.md)
- assurance/impact.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0027-packet-respond-falls-through-to-factory-/assurance/impact.json)
- assurance/verdicts.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0027-packet-respond-falls-through-to-factory-/assurance/verdicts.json)

## Recent events
- 2026-08-03T17:30:46Z assure.confirmed
- 2026-08-03T17:30:56Z stage.advance {'from': 'waiting-human', 'reason': 'human confirmed assurance (factory confirm)', 'to': 'assure'}
- 2026-08-03T17:30:56Z stage.advance {'from': 'assure', 'reason': 'assurance confirmed by human; 11/11 blind pass', 'to': 'ship'}
- 2026-08-03T17:32:41Z ship.merged {'mode': 'auto', 'ref': '0bd2a3636c6ac46cb5ce6d0f2ea70be4d1ef4aec'}
- 2026-08-03T17:32:41Z stage.advance {'from': 'ship', 'to': 'done'}

## Spend
- [proxy] active 08h 29m (waiting 02h 18m), 17 advances, 11 dispatches, 1 rework edges
- [measured] tokens: total 1124239 (11 events)
- [unmeasured] UNMEASURED: orchestrator main-loop tokens
- [measured] stage implement: total 441559 (6 events)
- [measured] stage review: total 126811 (1 events)
- [measured] stage verify: total 151974 (1 events)
- [measured] stage assure: total 403895 (3 events)

## Respond
Reply in session, or use the factory CLI to record your decision.

- `/factory:run` — resume the pipeline.
