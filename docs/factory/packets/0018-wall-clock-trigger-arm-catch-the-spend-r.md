# Wall-clock trigger arm: catch the spend runaways the churn breaker misses

- id: 0018-wall-clock-trigger-arm-catch-the-spend-r
- stage: blocked
- kind: backend
- priority: 8
- waiting on you: triage: rejected - mechanism refused 6/6 unanimous, problem statement stands. The AC4 calibration replay was run at triage over every real log.jsonl and refutes the item's own ACs arithmetically: AC2 requires firing at 9,499s (0016's first implement pass) but 0015's first implement pass is 10,046s and 0015 shipped clean, so every AC2-satisfying threshold parks healthy work; 0015 also out-spends 0016 on measured tokens (4.01M vs 3.95M), so re-denominating to tokens does not separate them either. active_seconds is calendar dwell not work (WAITING_STAGES excludes only blocked/waiting-human; the top eleven items by active_seconds are unstarted idea filings). The arm has no firing site - breaker.verdict runs only after an accepted transition and a single-pass runaway makes zero transitions while it burns. Priority 5 -> 8. Unblocks only if 0030's measurement spike finds a separating threshold, and requires 0027 (hard dependency) first. See items/0018-wall-clock-trigger-arm-catch-the-spend-r/triage.md

## View the options
- [Open this packet as a page](file:///Users/anthony/development/projects/factory/docs/factory/packets/0018-wall-clock-trigger-arm-catch-the-spend-r.html)

## Artifacts
- triage.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0018-wall-clock-trigger-arm-catch-the-spend-r/triage.md)
- spec.md: no
- plan.md: no
- design/choice.md: no
- reviews/synthesis.md: yes — [open](file:///Users/anthony/development/projects/factory/.factory/items/0018-wall-clock-trigger-arm-catch-the-spend-r/reviews/synthesis.md)
- assurance/impact.json: no
- assurance/verdicts.json: no

## Recent events
- 2026-08-02T12:22:47Z priority.set {'priority': 5}
- 2026-08-03T08:30:43Z stage.advance {'from': 'idea', 'to': 'triage'}
- 2026-08-03T08:50:53Z priority.set {'priority': 8}
- 2026-08-03T08:50:53Z tier.set {'tier': 'feature'}
- 2026-08-03T08:56:07Z stage.advance {'from': 'triage', 'reason': "triage: rejected - mechanism refused 6/6 unanimous, problem statement stands. The AC4 calibration replay was run at triage over every real log.jsonl and refutes the item's own ACs arithmetically: AC2 requires firing at 9,499s (0016's first implement pass) but 0015's first implement pass is 10,046s and 0015 shipped clean, so every AC2-satisfying threshold parks healthy work; 0015 also out-spends 0016 on measured tokens (4.01M vs 3.95M), so re-denominating to tokens does not separate them either. active_seconds is calendar dwell not work (WAITING_STAGES excludes only blocked/waiting-human; the top eleven items by active_seconds are unstarted idea filings). The arm has no firing site - breaker.verdict runs only after an accepted transition and a single-pass runaway makes zero transitions while it burns. Priority 5 -> 8. Unblocks only if 0030's measurement spike finds a separating threshold, and requires 0027 (hard dependency) first. See items/0018-wall-clock-trigger-arm-catch-the-spend-r/triage.md", 'to': 'blocked'}

## Spend
- [proxy] active 20h 33m (waiting 00h 00m), 2 advances, 0 dispatches, 0 rework edges
- [measured] tokens: none logged
- [unmeasured] UNMEASURED: orchestrator main-loop tokens

## Respond
Reply in session, or use the factory CLI to record your decision.

- `/factory:run` — resume the pipeline.
