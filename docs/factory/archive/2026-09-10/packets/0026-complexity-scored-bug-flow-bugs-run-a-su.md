# Complexity-scored bug flow: bugs run a subset of the pipeline chosen by a 1-5 complexity/severity score

- id: 0026-complexity-scored-bug-flow-bugs-run-a-su
- stage: waiting-human
- kind: backend
- priority: 3
- waiting on you: parked by human 2026-08-04: measurement deferred. Work is complete through verify and sits on branch factory/0026-... @ 687c1a1 (967 tests green, 28/28 criteria). Not shipped - the ceremony-reduction ask it was filed for is re-filed as its own item.

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/0026-complexity-scored-bug-flow-bugs-run-a-su.html)

## Artifacts
- triage.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0026-complexity-scored-bug-flow-bugs-run-a-su/triage.md)
- spec.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0026-complexity-scored-bug-flow-bugs-run-a-su/spec.md)
- plan.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0026-complexity-scored-bug-flow-bugs-run-a-su/plan.md)
- design/choice.md: no
- reviews/synthesis.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0026-complexity-scored-bug-flow-bugs-run-a-su/reviews/synthesis.md)
- assurance/impact.json: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0026-complexity-scored-bug-flow-bugs-run-a-su/assurance/impact.json)
- assurance/verdicts.json: no

## Recent events
- 2026-08-04T06:22:00Z review.approved
- 2026-08-04T06:22:00Z stage.advance {'from': 'review', 'to': 'verify'}
- 2026-08-04T06:42:25Z verify.green {'criteria': '28/28', 'tests': '967 passed, 0 failed, 7 skipped'}
- 2026-08-04T06:42:25Z stage.advance {'from': 'verify', 'to': 'assure'}
- 2026-08-04T07:02:12Z stage.advance {'from': 'assure', 'reason': 'parked by human 2026-08-04: measurement deferred. Work is complete through verify and sits on branch factory/0026-... @ 687c1a1 (967 tests green, 28/28 criteria). Not shipped - the ceremony-reduction ask it was filed for is re-filed as its own item.', 'to': 'waiting-human'}

## Spend
- [proxy] active 1d 10h 11m (waiting 00h 00m), 10 advances, 12 dispatches, 1 rework edges
- [measured] tokens: total 382425 (2 events)
- [unmeasured] UNMEASURED: orchestrator main-loop tokens
- [measured] stage triage: total 197539 (1 events)
- [measured] stage review: total 184886 (1 events)

## Respond
Reply in session, or use the factory CLI to record your decision.

- `factory confirm 0026-complexity-scored-bug-flow-bugs-run-a-su` — or `factory waive 0026-complexity-scored-bug-flow-bugs-run-a-su --reason "..."` to ship with a recorded waiver.
