# Shared-scratchpad message clobber: concurrent agents in one session reuse stale commit-message files

- id: 0019-shared-scratchpad-message-clobber-concur
- stage: blocked
- kind: backend
- priority: 4
- waiting on you: triage: rejected - no live Factory-owned scratch-message seam; historical regression absorbed into 0020's shared-checkout concurrency boundary

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/0019-shared-scratchpad-message-clobber-concur.html)

## Artifacts
- triage.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0019-shared-scratchpad-message-clobber-concur/triage.md)
- spec.md: no
- plan.md: no
- design/choice.md: n/a (not in this item's sequence)
- reviews/synthesis.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0019-shared-scratchpad-message-clobber-concur/reviews/synthesis.md)
- assurance/impact.json: no
- assurance/verdicts.json: no

## Recent events
- 2026-09-07T19:20:01Z stage.advance {'from': 'idea', 'to': 'triage'}
- 2026-09-07T19:29:13Z priority.set {'priority': 4}
- 2026-09-07T19:29:13Z tier.set {'tier': 'bug'}
- 2026-09-07T19:29:13Z spend {'dispatches': 6, 'provenance': 'measured', 'source': 'factory-triage', 'stage': 'triage', 'tokens': {'input': 469714, 'output': 11499, 'total': 481213}}
- 2026-09-07T19:29:13Z stage.advance {'from': 'triage', 'reason': "triage: rejected - no live Factory-owned scratch-message seam; historical regression absorbed into 0020's shared-checkout concurrency boundary", 'to': 'blocked'}

## Spend
- [proxy] active 36d 03h 03m (waiting 00h 00m), 2 advances, 6 dispatches, 0 rework edges
- [measured] tokens: input 469714, output 11499, total 481213 (1 events)
- [unmeasured] UNMEASURED: orchestrator main-loop tokens
- [measured] stage triage: input 469714, output 11499, total 481213 (1 events)

## Respond
Reply in session, or use the factory CLI to record your decision.

- `/factory:run` — resume the pipeline.
