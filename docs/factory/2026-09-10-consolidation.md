# Project consolidation — 2026-09-10

## Outcome and scope

Direct engineering consolidated the accepted implementation work on main.
Factory was not invoked as this repository's development harness. The root
runtime remains absent. The roadmap now separates delivered work, rejected
mechanisms, and explicitly deferred proposals; deferred ideas are not built.

The parked 0026 recorder was not blindly merged: its tier-based review-depth
receipt conflicts with current adaptive review semantics. Its useful defect
routing and roadmap visibility were ported. The older 0020 implementation is
superseded by main's checkout-ownership work; the old 0021 recovery commits are
patch-equivalent to integrated work.

## Work integrated or finished

- 0014 convergence judgement: 739b115.
- 0029 origin-known leaf/fork accounting: b51ca1e.
- 0030 timing source/metric: e50614a; completed frozen dataset, exhaustive replay,
  factual report and corruption checks: ecca6ed / 0c1dac5.
- FH-07 ledger core, structured evidence and completed CLI: 2e0d721.
- 0034 adaptive independent review: 48caf76. Concrete fixes cover static-only
  degraded execution, synthesis/receipt escalation mismatch, historical
  optional Round 2 handling, causal Round 2 triggers, diff-visible signals,
  and atomic rework preserving the reviewed commit.
- 0026's useful routing subset and 0038 proxy visibility: 8762de2.
- 0020, 0021, 0036, transactional handoffs and worker-attempt capture were
  already integrated before this consolidation and retained.

Degraded execution records contain a command, exit code, observed result and
digest-bound contained output file. This validates recorded evidence; it is
not host execution attestation and cannot prove an arbitrary prose claim true.

## Verification

- Initial whole-tree run: 1,565 tests; two integration failures identified
  (CLI refusal wording and pre-0029 golden spend snapshots), then corrected.
- Follow-up affected suites: 222 tests passed.
- Adaptive review / feasibility / validation / coherence: 247 tests passed.
- Intake / proxy visibility / snapshot checks: 110 tests passed, one skipped.
- Frozen replay: 31 tests passed; fixture-generated report matches the recorded
  6,204/6,205/6,206 cap boundary. No population-level calibration claim.
- Final local whole-tree run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
  discover -s tests -q` — 1,566 tests, OK, 8 skipped (1,558 passed), 196.617s.
- Standalone frozen replay `verify` passed; `git diff --check` passed.
- Remote CI is separate from these local results; no marketplace publication
  or installed-host end-to-end execution is implied by the test suite.

## Workspace cleanup

Removed 14 redundant worktrees and 19 local development branches after exact
status checks, archive-tag creation and bundle verification. Only the main
worktree and local `main` branch remain. Removed five non-main branches from
the origin remote using exact-SHA leases; the upstream repository was untouched.
Four historical contribution tips also have existing origin archive tags.
The 0026 tip is recoverable from the local archive tag and verified bundles.
No source changes or proposal drafts were discarded, and no root `.factory/`
runtime was restored.

## Recoverability

Before consolidation, all refs and uncommitted worktree files were backed up
to this local directory (not part of the repository):

`/Users/anthony/development/projects/factory-consolidation-backup-hEQAHd`

- `branches.bundle`: pre-consolidation refs and full history.
- `working-files.tar.gz`: original docs and all worktrees, including dirty files.
- `consolidated-branches.bundle`: integrated history plus branch archive tags,
  verified with `git bundle verify` before branch removal.

The older retired runtime remains at
`/Users/anthony/development/projects/factory-self-hosting-archive-2026-09-10`.
This runtime is not required to run the product test suite.

The following local annotated tags preserve every removed development-branch
tip. Tags and bundles retain the exact old code; they are not active branches
or an instruction to resume their plans. Original untracked 0032 and FH-04
drafts are also versioned in [the proposal archive](archive/2026-09-10/proposals/).

| Original branch | Preserved commit | Ancestor of integrated main |
|---|---|---|
| codex/review-fixes-0013-0025 | 1437095455f5ff62f18ea1e5915b53b19cd6ef3b | yes |
| engineering/0014-convergence-current | f27385e09b9b74daed51c2ad1d5c84abc569bc79 | yes |
| engineering/0020-checkout-ownership | 78d4930b0404d5ebc30f30ed8e92c720ce0013cc | yes |
| engineering/0021-child-reply-timeouts-direct | c535fafd5cd9e7bdbd9abb556ac04e0ecac7d5aa | yes |
| engineering/0021-lost-reply-recovery | edd47d7885f098a03971f632a863b0a3e034b1a3 | no — superseded/parked, preserved |
| engineering/0032-dispatch-resilience | 78d4930b0404d5ebc30f30ed8e92c720ce0013cc | yes |
| engineering/0036-plan-acceptance | 72443111b89892a906be3b27d7e35bbe413fa240 | yes |
| engineering/fh04-evidence-preflight | 78d4930b0404d5ebc30f30ed8e92c720ce0013cc | yes |
| engineering/fh07-derived-ledger | f99dd7651dad73c352915e25772f1af6329fcaca | yes |
| engineering/transactional-handoffs | 90a048422b18af4c3c88f3969d097aa705f8d6dd | yes |
| engineering/worker-attempt-capture | 1387ea241b30d940c72b21781f291a0e14855f51 | yes |
| factory/0014-approach-gate-at-plan-judge-convergence- | 66168bfd60018dfb7fa4f45310d85a161848372b | yes |
| factory/0020-concurrent-implementers-violate-the-one- | 4a85973334a944be4b74bda129fca245a5567c42 | no — superseded/parked, preserved |
| factory/0026-complexity-scored-bug-flow-bugs-run-a-su | 687c1a115e7256d900998be62e5dd00505e91c48 | no — superseded/parked, preserved |
| factory/0029-scope-spend-events-a-leaf-vs-fork-discri | c6f70624f5e6394a4d6654d224b896bb5cee99f9 | yes |
| factory/0030-measurement-spike-gap-capped-per-pass-at | ac13ce5eb1c46c0674b1925893cd22abd9673299 | yes |
| factory/0034-independent-council-review-defaults-to-t | 2514efa6ed7aadf11c15e4c07315876489f4e84e | yes |
| factory/codex-native-plugin | a8d2fc8d2a64c8f35eb81fe0f154792dd1e2b3d1 | yes |
| factory/codex-portability | a1c04a5564124fdd9078c6d051085570a32bbd6e | yes |

Tag names are `archive/2026-09-10/<original-branch>`. Local recovery example:

```sh
git switch -c recover-0026 archive/2026-09-10/factory/0026-complexity-scored-bug-flow-bugs-run-a-su
```

Do not extract the runtime archive into this repository. Restore any historical
self-hosted state only into a separate inspection directory.
