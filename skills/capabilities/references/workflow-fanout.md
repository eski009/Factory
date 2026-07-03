# Workflow-based fan-out

Only useful if you have the Workflow tool; the degraded path — parallel Task subagent dispatches in one message — is always sufficient and is what every stage skill is written against by default.

## Council rounds

Round 1 of the `council-review` protocol dispatches six independent seats (`council-product`, `council-ui-taste`, `council-architecture`, `council-engineering-quality`, `council-customer`, `council-commercial`). With Workflow available, run this round as a parallel fan-out: one stage per seat, each stage's structured output being that seat's findings — the same three-claims-with-evidence report a Task subagent would return, just produced as a workflow stage instead of a subagent turn. Feed all six outputs into a single reduce stage that performs the orchestrator synthesis: dedupe, group by topic, flag conflicts, decide which seats need Round 2. That reduce stage is still the orchestrating session's own reasoning, not a seventh seat — Workflow gives it a place to run as a stage, not a new participant.

Round 2 is a second, conditional fan-out: a new stage per seat, but only over the seats the synthesis selected, each fed `synthesis-1.md` and nothing else. Seats not selected simply have no Round 2 stage — there is no fan-out branch to skip.

## Plan tasks

`factory-implement` walks a plan's tasks one at a time, each followed by its own review before the next task starts. With Workflow available, run this as a pipeline: one stage per task (implementer, then that task's verify/review step) feeding into the next task's stage, rather than the orchestrator manually looping dispatch calls. This is still a sequential pipeline, not parallel implementation — tasks still land one at a time with a clean review gate between them; Workflow only automates the loop's bookkeeping, it does not license running independent-looking tasks concurrently.

## What does not change

Map every fan-out stage back to the degraded path one-for-one, so a session with Workflow and a session without it produce indistinguishable results, just at different speed:

- **Same artifacts.** Each seat's stage still gets its report persisted to `reviews/round-1/<role>.md` (and `reviews/round-2/<role>.md` for the delta round) exactly as the degraded path writes it — the orchestrator persists after each stage returns, same as after each subagent call returns.
- **Same firewall.** The orchestrating session — not a workflow stage, not a seat — is still the only thing that writes `reviews/*.md`, judges which seats advance to Round 2, and produces the final `synthesis.md`. No stage gets write access to another seat's memory file or to `docs/factory/brain/`; that boundary doesn't move just because dispatch got faster.
- **Same protocol.** Round 1 stays independent (no seat's stage sees another seat's output), Round 2 stays delta-only and selected-seats-only, the two-round hard stop still applies, and severities still get tagged in the final synthesis. Workflow changes execution speed and parallelism — never the protocol, and never the memory rules.

If Workflow is absent, or a probe for it comes back negative, fall straight through to parallel Task subagent dispatches in one message per round: identical seats, identical files, identical firewall, just issued as one message of concurrent subagent calls instead of workflow stages.
