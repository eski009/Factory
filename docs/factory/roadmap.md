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

- [-] 0019-shared-scratchpad-message-clobber-concur Concurrent agents in one session reuse stale commit-message files (idea, bug — observed on 0016's rework: reflog ae205c4 → f609d24 shipped the wrong commit body)
- [-] 0020-concurrent-implementers-violate-the-one- Concurrent implementers violate the one-at-a-time contract in a shared checkout (idea, bug — factory-implement's own sub-dispatches broke its contract on 0016)
- [-] 0021-parent-agents-block-on-child-replies-tha Parent agents block on child replies that never arrive though the work is done on disk (idea, bug — **five occurrences across three skills on 2026-08-02/03**, one of which caused a duplicated council; the best-evidenced item in the backlog)
- [-] 0022-gitignored-factory-state-is-invisible-to Gitignored .factory state is invisible to clones (idea, bug — a fresh clone gets the code and none of the decisions; also why suite skip counts differ between checkouts)
- [-] 0023-packet-furniture-and-readout-polish-drop Packet furniture and readout polish (idea, bug — owns the J-002 one-job-per-screen ruling, the status-table overflow on engine-filed ids, and the shipped packet's dead self-link)
- [-] 0024-assure-readout-periphery-known-fails-fir Assure readout periphery: known-fails first screen, owner-priority Respond branch, status --json surface (idea, feature — shed from 0013 at its plan re-judgement; owns J-001 nodes N3/N4)
- [-] 0026-complexity-scored-bug-flow-bugs-run-a-su Complexity-scored bug flow: bugs run a subset of the pipeline chosen by a 1–5 score (idea, feature — **human-filed**; bid-0125 records the supporting evidence that review depth keys on tier, not change class)
