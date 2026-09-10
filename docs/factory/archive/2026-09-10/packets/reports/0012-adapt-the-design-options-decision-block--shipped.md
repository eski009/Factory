# Adapt the design-options decision block to the viewing surface (Artifact vs local file)

- id: 0012-adapt-the-design-options-decision-block-
- stage: done
- kind: mixed
- priority: 2

## Artifacts
- triage.md: yes
- spec.md: yes
- plan.md: yes
- design/choice.md: yes
- reviews/synthesis.md: yes

## Recent events
- 2026-07-13T12:45:13Z stage.advance {'from': 'review', 'to': 'verify'}
- 2026-07-13T12:47:13Z verify.green {'criteria': '9/9', 'tests': '334/334 unittest pass'}
- 2026-07-13T12:47:13Z stage.advance {'from': 'verify', 'to': 'ship'}
- 2026-07-13T12:48:18Z ship.merged {'mode': 'auto', 'ref': 'a98876a'}
- 2026-07-13T12:48:18Z stage.advance {'from': 'ship', 'to': 'done'}

## Spend
- [proxy] active 03h 08m (waiting 00h 09m), 11 advances, 16 dispatches, 0 retries
- [measured] tokens: total 372739 (5 events)
- [unmeasured] UNMEASURED: orchestrator main-loop tokens

## Respond
Reply in session, or use the factory CLI to record your
decision (for a design pause: `factory choice <id> <option>`),
then run `/factory:run` to resume.
