# Roadmap

<!-- Prioritized backlog. The triage council maintains this file.
     One line per item: - [priority] <item-id> <title> (stage) -->

- [1] 0001-focus-group-research-structured-intervie Focus-group research: structured interviews with 4-6 key stakeholder personas (done)
- [2] 0003-interactive-decision-pages-clickable-cho Interactive decision pages: clickable choices with feedback listener, per-option commentary, and none-of-these (done)
- [2] 0012-adapt-the-design-options-decision-block- Adapt the design-options decision block to the viewing surface (Artifact vs local file) (done)
- [3] 0004-per-item-cost-meter-measure-and-report-t Per-item cost meter: measure and report token/effort spend per work item (done)
- [4] 0002-claude-design-mcp-as-the-single-source-o Claude Design MCP as the single source of design truth, integrated with design-polish (done — shipped as rescoped: preferred mirror, repo files canonical)
- [-] 0005-generalize-the-interactive-decision-mech Generalize the interactive-decision mechanism to all waiting-human packets (blocked — awaits 0003 shipping + one real gate use)
- [-] 0006-design-polish-integration-as-an-opt-in-c Design-polish integration as an opt-in capability (blocked — awaits a probe-able skill or cited pain)
- [5] 0007-tolerant-log-reading-corrupt-log-jsonl-l Tolerant log reading: corrupt log.jsonl lines must degrade, not crash, cost/status surfaces (done)
- [6] 0008-design-mirror-refinements-pull-bid-diver Design-mirror refinements: pull-bid divergence guard, packet token-provenance disclosure, placeholder supersession (done)
- [-] 0009-finish-the-never-bricks-promise-crash-pr Finish the never-bricks promise: crash-proof validate/items on item.md/config.json corruption, ledger key filter, text-status notice, copy pass (done)
- [8] 0010-factory-bug-command-understand-replicate factory:bug command: understand, replicate, branch, fix, regression-test, and prove-fixed bug pipeline (done)
- [-] 0011-create-factory-bug-command-understand-th Create /factory:bug command (blocked — rejected: duplicate of 0010)

## Field-report batch (ParkSnap p1 non-convergence, 2026-08-02)

<!-- Ranked relative to each other by 0013's triage council: 0016 is the
     measuring instrument for 0013's business case, so it moves ahead of the
     approach-gate pair. 0016's own triage council (6/6) then took it to p1 and
     0013 to p2, matching the human's 2026-08-02 sequencing; 0013 unparks at
     0016's `ship`, through the ordinary gates (amended 2026-08-02 — the
     mid-item merge at Task 5 that this used to name was removed as a gate
     bypass; see 0016's plan.md Task 5). -->

- [1] 0016-cost-circuit-breaker-on-engine-authorita Cost circuit breaker on engine-authoritative rework counts (done)
- [2] 0013-assure-attribution-gate-only-on-regressi Assure attribution: gate only on regressions this item caused (done)
- [2] 0025-round-scope-all-rework-gates-implement-c Round-scope all rework gates: implement.completed, review.approved and verify.green accept prior-round evidence (done)
- [3] 0015-approach-rejected-a-redesign-loop-back-t approach.rejected: a redesign loop back to spec with forbidden approaches recorded (done)
- [4] 0014-approach-gate-at-plan-judge-convergence- Approach gate at plan: judge convergence before implementation spend (idea)
- [-] 0017-factory-scope-engine-validated-scope-nar factory scope: engine-validated scope narrowing as a first-class artifact (idea — split out of 0013; sequence after it ships)

## Cost-control line (0018 triage outcome, 2026-08-03)

<!-- 0018's triage council was unanimous: DON'T BUILD AS SPECIFIED. The AC4
     calibration replay was run at triage rather than deferred, over every real
     log.jsonl, and refuted the item's own acceptance criteria arithmetically —
     AC2 requires firing at 9,499s (0016's first implement pass) while 0015's
     first implement pass is 10,046s and 0015 shipped clean, so every
     AC2-satisfying threshold parks healthy work. 0015 also out-spends 0016 on
     measured tokens (4.01M vs 3.95M), which kills the token re-denomination
     too. active_seconds is calendar dwell, not work. The problem statement
     survives; the mechanism does not. 0018 drops p5 -> p8 behind 0027, 0028 and
     the two replacements below. See .factory/items/0018-*/triage.md. -->

<!-- Amended by 0027's triage council, 2026-08-03: 6/6 BUILD at p2 (unchanged),
     scope extended beyond the filed one-line change — the fix is branch ORDER,
     not the branch key, and acceptance is a bidirectional section-to-bullet
     coupling invariant on rendered HTML. 0028 is ABSORBED into 0027 (6/6);
     0031 is NOT (6/6 — it amends approved J-002 oracles plus J-001's
     permitted-diffs enumeration). 0027's ranking reason was also corrected:
     "HARD dependency of 0018" was a contingent driver (0018's own line below
     records it as unblocking only if 0030 finds a separating threshold), so the
     standalone
     reachability ground now ranks it. See .factory/items/0027-*/triage.md. -->

- [2] 0027-packet-respond-falls-through-to-factory- Packet Respond falls through to /factory:run when a decision pause is parked from an unexpected stage (done — shipped 2026-08-03 as merge 0bd2a36; the Respond verb is now keyed on the pause's reason rather than its stage, absorbing 0028's None-repr refusal; also unblocks 0018 if 0030 revives it)
- [-] 0028-the-cost-breaker-leaks-a-python-none-rep The cost breaker leaks a Python None repr in its malformed-answer refusal (blocked — absorbed into 0027 as its scope item 4; bid-0129's rework-edges regex residual still owed)
- [5] 0029-scope-spend-events-a-leaf-vs-fork-discri Scope spend events: a leaf-vs-fork discriminator so measured token totals are trustworthy (idea — the precursor; finally owns bid-0063, the brain's top open question)
- [6] 0030-measurement-spike-gap-capped-per-pass-at Measurement spike: gap-capped per-pass attributed_seconds, and whether any threshold separates a runaway from healthy work (idea — replaces 0018's build; gates it)
- [3] 0031-the-cost-packet-s-decision-copy-is-churn The cost packet's decision copy is churn-shaped in four places and its recommendation never reads the verdict reason (idea — standing defect, independent of 0018)
- [8] 0018-wall-clock-trigger-arm-catch-the-spend-r Wall-clock trigger arm: catch the spend runaways the churn breaker misses (blocked — triage rejected the mechanism; unblocks only if 0030's spike finds a separating threshold)

## Filed but not yet council-ranked (added 2026-08-03)

Seven live items were absent from this file entirely — invisible here while
open in the backlog, which already cost item 0031 a redundant open question
about ownership 0023 had. Listed at their filed priority (`-` = unprioritised,
sorts last in `factory status`); a council ranks them when each reaches triage.
(0026 was the seventh; its council ran on 2026-08-03 and it now has its own
section below.)

- [-] 0019-shared-scratchpad-message-clobber-concur Concurrent agents in one session reuse stale commit-message files (idea, bug — observed on 0016's rework: reflog ae205c4 → f609d24 shipped the wrong commit body)
- [-] 0020-concurrent-implementers-violate-the-one- Concurrent implementers violate the one-at-a-time contract in a shared checkout (idea, bug — factory-implement's own sub-dispatches broke its contract on 0016)
- [-] 0021-parent-agents-block-on-child-replies-tha Parent agents block on child replies that never arrive though the work is done on disk (idea, bug — **five occurrences across three skills on 2026-08-02/03**, one of which caused a duplicated council; the best-evidenced item in the backlog)
- [-] 0022-gitignored-factory-state-is-invisible-to Gitignored .factory state is invisible to clones (idea, bug — a fresh clone gets the code and none of the decisions; also why suite skip counts differ between checkouts)
- [-] 0023-packet-furniture-and-readout-polish-drop Packet furniture and readout polish (idea, bug — owns the J-002 one-job-per-screen ruling, the status-table overflow on engine-filed ids, and the shipped packet's dead self-link)
- [-] 0024-assure-readout-periphery-known-fails-fir Assure readout periphery: known-fails first screen, owner-priority Respond branch, status --json surface (idea, feature — shed from 0013 at its plan re-judgement; owns J-001 nodes N3/N4)

## Bug-flow line (0026 triage outcome, 2026-08-03)

<!-- 0026's triage council was 6/6 BUILD-RESCOPED: the problem statement is
     affirmed unanimously, the mechanism refused unanimously. The 1-5 complexity
     score and "bugs run a subset of the pipeline" are both CUT — stage
     membership is engine-owned (every drop strands the next gate) and a score
     assigned at intake is a prediction 0027 already falsifies (filed as a
     one-liner, shipped as 66 lines across two files). The item's own headline
     cost datapoint was refuted at triage: 0027's 403,895 assure tokens are 100%
     pool-exhaustion rework at the `node` floor, not tier depth, and a
     malfunctioned council cost 1,499,591 against 135,475 for a complete 9-seat
     fan-out — failure and retry are the cost driver, not seat count. What
     survives is routing (`/factory:bug` is unreachable from `commands/add.md`;
     `bug: true` and `journeys: none` both sit at zero adoption across 32 items)
     shipped with its receipt, then an engine-written depth recorder, then
     bid-0125 third. Assure and verify depth are OUT, binding 5/5. 0029 is NOT
     0026's precursor — the reverse, on the recorder half. See
     .factory/items/0026-*/triage.md. -->

<!-- Amended 2026-08-04 by the human, after reviewing 0026's cost and outcome:
     0026 is PARKED at waiting-human, complete through verify on branch
     factory/0026-... @ 687c1a1 (967 tests green, 28/28 criteria, review
     approved round 2). Not shipped. The measurement half is deferred; the
     ceremony-reduction ask 0026 was filed for is re-filed as 0033 at p1 and
     goes first. 0026 cost ~1.24M tokens of subagent work through verify and
     had not yet run its 14-scenario assure walk — an item about reducing
     ceremony taking the full feature profile.

     0033 also records that this section's stage-membership premise is FALSE:
     machine.stage_sequence already drops stages conditionally (design for
     kind backend, assure for journeys none), and _gate_plan already
     conditions its gate on the same attribute, so a dropped stage strands
     nothing. Conditional membership is a shipped pattern with two working
     instances, not new architecture. -->

- [3] 0026-complexity-scored-bug-flow-bugs-run-a-su Complexity-scored bug flow: bugs run a subset of the pipeline chosen by a 1–5 score (PARKED waiting-human — built through verify on branch @ 687c1a1, deliberately unshipped; score and stage-subset cut 6/6, what remains is bug-door signposting + a depth recorder nothing reads; owns bid-0125 and discharges bid-0042)
- [1] 0033-bugs-run-less-pipeline-make-stage-member Bugs run less pipeline: make stage membership tier-conditional, the way it is already kind-conditional (idea, feature — **human-filed 2026-08-04**, "I want bugs to use less pipeline as a general rule"; carries the intent 0026's council cut, on the evidence that its stage-membership premise is refuted by three lines of machine.stage_sequence; triage decides WHICH stages a bug skips, not whether skipping is possible)
- [-] 0032-dispatch-resilience-pool-exhaustion-and- Dispatch resilience: pool-exhaustion and no-synthesis council runs must fail fast and resume, not silently re-walk (idea, feature — filed by 0026's triage council; a malfunctioned council-review cost 1,499,591 tokens vs 135,475 for a complete fan-out, 11x; ranked second, after 0026's routing branch)
