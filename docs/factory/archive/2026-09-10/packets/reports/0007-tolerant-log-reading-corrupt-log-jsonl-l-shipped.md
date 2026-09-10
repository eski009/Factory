# Tolerant log reading: corrupt log.jsonl lines must degrade, not crash, cost/status surfaces

- id: 0007-tolerant-log-reading-corrupt-log-jsonl-l
- stage: done
- kind: backend
- priority: 5

## Artifacts
- triage.md: yes
- spec.md: yes
- plan.md: yes
- design/choice.md: no
- reviews/synthesis.md: yes

## Recent events
- 2026-07-10T23:40:55Z stage.advance {'from': 'review', 'to': 'verify'}
- 2026-07-10T23:41:18Z verify.green {'criteria': '15/15', 'tests': '286 unittest OK'}
- 2026-07-10T23:41:18Z stage.advance {'from': 'verify', 'to': 'ship'}
- 2026-07-10T23:41:49Z ship.merged {'mode': 'auto', 'ref': '7fd449f'}
- 2026-07-10T23:41:49Z stage.advance {'from': 'ship', 'to': 'done'}

## Respond
Reply in session, or use the factory CLI to record your
decision (for a design pause: `factory choice <id> <option>`),
then run `/factory:run` to resume.
