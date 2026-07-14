# factory:bug command: understand, replicate, branch, fix, regression-test, and prove-fixed bug pipeline

- id: 0010-factory-bug-command-understand-replicate
- stage: done
- kind: backend
- priority: 8

## Artifacts
- triage.md: yes
- spec.md: yes
- plan.md: yes
- design/choice.md: no
- reviews/synthesis.md: yes

## Recent events
- 2026-07-11T09:40:20Z stage.advance {'from': 'review', 'to': 'verify'}
- 2026-07-11T09:43:02Z verify.green {'criteria': '12/12', 'tests': '332/332 unittest OK'}
- 2026-07-11T09:43:02Z stage.advance {'from': 'verify', 'to': 'ship'}
- 2026-07-11T09:43:57Z ship.merged {'mode': 'auto', 'ref': '4703ba78a56ea973a99a71c1c126c7aa49abd59d'}
- 2026-07-11T09:43:57Z stage.advance {'from': 'ship', 'to': 'done'}

## Spend
- [proxy] active 00h 55m (waiting 00h 00m), 8 advances, 24 dispatches, 0 retries
- [measured] tokens: total 760180 (8 events)
- [unmeasured] UNMEASURED: orchestrator main-loop tokens

## Respond
Reply in session, or use the factory CLI to record your
decision (for a design pause: `factory choice <id> <option>`),
then run `/factory:run` to resume.
