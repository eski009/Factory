# Bugs run less pipeline: make stage membership tier-conditional, the way it is already kind-conditional

- id: 0033-bugs-run-less-pipeline-make-stage-member
- stage: done
- kind: backend
- priority: 1

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/0033-bugs-run-less-pipeline-make-stage-member.html)

## Artifacts
- triage.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0033-bugs-run-less-pipeline-make-stage-member/triage.md)
- spec.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0033-bugs-run-less-pipeline-make-stage-member/spec.md)
- plan.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0033-bugs-run-less-pipeline-make-stage-member/plan.md)
- design/choice.md: n/a (not in this item's sequence)
- reviews/synthesis.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0033-bugs-run-less-pipeline-make-stage-member/reviews/synthesis.md)
- assurance/impact.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0033-bugs-run-less-pipeline-make-stage-member/assurance/impact.json)
- assurance/verdicts.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0033-bugs-run-less-pipeline-make-stage-member/assurance/verdicts.json)

## Recent events
- 2026-08-04T16:07:36Z spend {'dispatches': 2, 'provenance': 'proxy', 'source': 'factory-assure', 'stage': 'assure'}
- 2026-08-04T16:07:36Z assure.passed {'non_blocking_fails': 0, 'round': 1}
- 2026-08-04T16:07:43Z stage.advance {'from': 'assure', 'reason': 'fresh-context assurance passed: 9/9 declared scenarios', 'to': 'ship'}
- 2026-08-04T16:09:18Z ship.merged {'mode': 'auto', 'ref': 'c673fd5c0732b0c294c7e01416f7169cde14cf4a'}
- 2026-08-04T16:09:18Z stage.advance {'from': 'ship', 'reason': 'auto merge green: 940 tests', 'to': 'done'}

## Spend
- [proxy] active 09h 07m (waiting 00h 00m), 9 advances, 2 dispatches, 0 rework edges
- [measured] tokens: none logged
- [unmeasured] UNMEASURED: orchestrator main-loop tokens

## Respond
Reply in session, or use the factory CLI to record your decision.

- `/factory:run` — resume the pipeline.
