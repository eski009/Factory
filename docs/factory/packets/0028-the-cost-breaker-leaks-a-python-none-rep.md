# The cost breaker leaks a Python None repr in its malformed-answer refusal (twin of the approach.py defect)

- id: 0028-the-cost-breaker-leaks-a-python-none-rep
- stage: blocked
- kind: backend
- priority: 3
- waiting on you: triage: absorbed into 0027 - 0027's triage council ruled 6/6 to bundle (same operator trip, same pause, same two files; conformant arm already at breaker.py:174-177). Scope item 4 of 0027 carries the missing-field arm and its exact-message test. Reopen only if 0027 ships without it.

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/0028-the-cost-breaker-leaks-a-python-none-rep.html)

## Artifacts
- triage.md: no
- spec.md: no
- plan.md: no
- design/choice.md: no
- reviews/synthesis.md: no
- assurance/impact.json: no
- assurance/verdicts.json: no

## Recent events
- 2026-08-03T07:32:44Z item.created
- 2026-08-03T08:56:35Z priority.set {'priority': 3}
- 2026-08-03T09:18:33Z stage.advance {'from': 'idea', 'reason': "triage: absorbed into 0027 - 0027's triage council ruled 6/6 to bundle (same operator trip, same pause, same two files; conformant arm already at breaker.py:174-177). Scope item 4 of 0027 carries the missing-field arm and its exact-message test. Reopen only if 0027 ships without it.", 'to': 'blocked'}

## Spend
- [proxy] active 01h 45m (waiting 00h 03m), 1 advances, 0 dispatches, 0 rework edges
- [measured] tokens: none logged
- [unmeasured] UNMEASURED: orchestrator main-loop tokens

## Respond
Reply in session, or use the factory CLI to record your decision.

- `/factory:run` — resume the pipeline.
