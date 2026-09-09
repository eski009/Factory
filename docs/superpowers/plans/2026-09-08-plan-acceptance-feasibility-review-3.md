# Item 0036 architecture review — round 3

Date: 2026-09-08

Verdict: **BLOCK**. This was the third and final architecture review. Park the
branch unmerged; do not begin implementation from this plan.

The canonical item remains at `idea` and has no `spec.md`, so the review used
the item title, current repository architecture, and the proposed direct
engineering plan.

## Material blockers

1. **Plan-to-implement has no checkout to validate.** The plan requires every
   transition into `implement` to validate against the canonical implementation
   checkout, but `factory-implement` creates that checkout only after the item
   enters `implement`. Transition validation and checkout-bound dispatch
   validation must be separated, or checkout provisioning needs explicit
   rollback semantics.
2. **In-process task finalization has no snapshot transport.** The proposed
   read-only `plan-check` CLI intentionally does not expose snapshot bytes or
   descriptors. The implementer/reviewer lifecycle therefore cannot later call
   `finalize_tasks` with the original in-memory snapshot. Revalidation as a new
   snapshot would not protect against ticking a concurrently replaced task.
3. **Enabled/disabled selection has a config race.** Reading enabled state
   before ownership is not the promised enabled boundary; acquiring ownership
   before that read changes disabled behavior. A strict config-only snapshot
   must be carried into and revalidated at the selected boundary.
4. **Git cannot prove every transient touched path.** Commit-parent diffs plus
   final index/worktree/untracked state cannot detect an out-of-scope file that
   was modified and restored without a commit before the backend returned. The
   claim must narrow to Git-observable paths or execution needs active
   enforcement/observation.
5. **Rework preparation is not crash-idempotent.** Appending tasks, updating the
   sidecar, checking, logging rejection, and advancing are separate operations.
   Interruptions can duplicate tasks or consume another capped rejection. An
   engine-owned idempotency receipt keyed by stage, authoritative artifact hash,
   and finding id is required, with resume tests at every boundary.

## Required precursor before resuming 0036

Design and independently approve a smaller engine substrate for transactional,
idempotent stage handoffs: strict config snapshot selection, durable
owner-bound dispatch receipts, guarded completion, and rework idempotency. The
scope-observation claim must also be chosen explicitly: enforce writes while a
worker runs, or guarantee only the complete Git-observable history and final
state.
