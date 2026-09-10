# Reliable evidence capture preflight plan

> **Execution:** direct engineering only; do not invoke the Factory harness.
> This implements retrospective candidate FH-04 as a machine gate, not as a
> prose reminder.

## Goal

Before `verify.green` can exist, prove that the evidence captured for the
current implementation round matches a previously frozen requirements
contract. The engine must detect missing tests, discovery-count drift,
purpose mismatch, wrong visual route/state, failed actions, missing/tampered
artifacts and warnings hidden by a passing summary.

## Durable contract

Each item has:

```text
.factory/items/<item>/evidence/
  requirements.json
  captures/<capture-id>/
    capture.json
    artifacts/...
  preflights/<preflight-id>.json
```

`requirements.json` is an immutable revision frozen before the first
`plan -> implement` transition. Its SHA-256 is logged by the engine as
`evidence.requirements.frozen`. Every non-SPECIAL transition into `implement`
(`plan`, `review`, `verify` or `assure` rework) publishes an immutable
`evidence/rounds/<implementation-entry>.json` binding that entry to the current
requirements revision before any later evidence is accepted. Rework carries
the unchanged revision forward; changing requirements requires returning
through plan and freezing a new revision. A `waiting-human`/`blocked` resume is
not a new implementation round and keeps the prior binding. Generic logging
cannot write either authority event.

The closed version-1 requirements schema contains:

- `item`, immutable `revision_id`, `spec_sha256` and
  `plan_contract_sha256`. The plan contract hash normalizes only task checkbox
  markers (`- [ ]` and `- [x]`) to `- [*]`; all other bytes, including added,
  removed or reordered tasks, remain significant;
- non-empty `required_purposes`, each one of `component`, `integrated`,
  `production`; purposes are exact labels, never a widening hierarchy;
- `suites`: stable id, purpose, frozen discovery/execution command identities,
  exact expected test ids, optional exact expected discovered count, whether
  skips are allowed, warning patterns and warning-failure policy;
- `checks`: stable acceptance-criterion id, purpose and kind
  (`command` or `screenshot`), frozen action/probe command identities and a
  machine-evaluable expected result. Command expected results are exact JSON
  values. Screenshot checks freeze expected route, expected state and required
  action id/status.

The supported version-1 adapter artifacts are also closed JSON. Discovery
contains `{version, suite, tests}`. Execution contains
`{version, suite, tests:[{id,outcome}], warnings}` with outcome exactly one of
`passed|failed|skipped`. Command checks contain
`{version, check, action, exit_code, actual}`. Screen probes contain
`{version, check, route, state, action:{id,status}}`. The engine parses these
raw artifacts itself and requires every duplicated capture field to agree;
exit zero or caller-supplied IDs cannot stand in for the expected JSON value.

A capture is current only when it binds the exact requirements/spec/plan
contract hashes, latest non-resume `implement` entry, implementation branch
HEAD plus content-sensitive state digest, tool/adapter identity and capture
timestamp. The canonical checkout is resolved through
`ownership.canonical_worktree`; control-checkout aliases and any other worktree
refuse. State is captured twice and must match: HEAD, porcelain-v1 `-z` status,
binary staged/unstaged diffs, untracked paths and each untracked regular-file
byte hash or symlink-target hash. Factory control state is outside that checkout
and does not self-invalidate the digest. A capture contains:

- per suite: discovery/execution adapter paths and hashes, their frozen command
  identities, sorted discovered ids, passed/failed/skipped ids, exit code, raw
  stdout/stderr artifact paths and hashes, and every warning occurrence derived
  from the frozen patterns across all adapter and transcript outputs;
- per command check: action, exit code, observed result, raw transcript path
  and hash;
- per screenshot check: required action and its outcome, observed route/state,
  screenshot path/hash and a route/state probe artifact path/hash.

The engine derives all counts and verdicts. It never accepts caller-supplied
totals or a top-level `passed` flag. Suite/check ids and test ids are unique.
Execution outcomes are a disjoint, complete partition of discovered ids. Exact
expected ids must be discovered and passed; exact discovered count must match
when declared. Failed ids, disallowed skips, nonzero commands, wrong exact JSON
results, broken/missing actions, probe/capture disagreement, route/state
mismatch, wrong purpose, missing criteria or artifact/hash mismatch fail. Every
required purpose must have at least one passing declared suite or check;
component evidence cannot satisfy an integrated or production purpose.

Warnings fail only when the frozen requirement's policy says `fail`; otherwise
they remain visible. Preflight re-scans every raw adapter/stdout/stderr/
transcript artifact using the frozen patterns, preserves duplicate occurrences
in stable source/line order, requires the capture list to match exactly, stores
all warning text and count in its immutable receipt, and the CLI prints them
even on success.

`preflight` publishes canonical JSON by fully writing and fsyncing a temporary
file, exclusive-linking the final receipt, fsyncing the directory, then
reopening and checking bytes, inode and parent identity. A matching retry
adopts the existing receipt; a conflicting receipt refuses. All paths are
repository-relative, contained beneath the item, opened no-follow and required
to be regular files. Symlink, traversal, replacement or read race fails closed.

Authority operations (`requirements.frozen`, implementation-round binding and
`verify.green`) use a shared engine writer: acquire an item-log lock; strict-read
the complete log with no skipped/malformed records; publish an immutable
operation receipt keyed by stable operation id; append one canonical event with
that id using a single `O_APPEND` write; fsync the log; strict-read and verify
exactly one matching event; then release. A crash after the receipt but before
the append is repaired by the matching retry. Matching receipt/event retries
adopt; duplicate or conflicting history refuses. Generic `factory log` rejects
`stage.advance`, `verify.green` and all `evidence.*` authoritative events.

`factory verify-green ITEM --preflight ID` is the only public writer of
`verify.green`. It revalidates the receipt against live requirements, spec,
plan contract, implementation-round binding, canonical checkout identity and
every artifact, then uses the authority writer to append `verify.green` with
`preflight_id`, receipt hash, derived suite/criterion counts and warning count.

Both the `verify -> assure` and verify-substituted `verify -> ship` gates
require the fresh `verify.green` event and independently revalidate its bound
preflight. Later artifact mutation therefore invalidates the gate.

## Migration

Safety is the default, including existing repositories. The first upgraded
`factory init` publishes one immutable `.factory/evidence-migration.json`
snapshot containing every existing item id, effective stage (`paused-from` for
SPECIAL items), latest implementation-entry identity and item/log prefix hash.
It fabricates no requirements or passing evidence.

An item already before `implement` must receive requirements normally. Only a
round named in that one-time snapshot at effective stage `implement`, `review`
or `verify` may use
`factory evidence requirements ITEM --adopt-current-round`, and it may do so
once; the adoption receipt binds the snapshot and exact round. Newly created
items and later implementation entries can never use it. Paused items inherit
the eligibility of their snapshotted `paused-from` round. Items snapshotted at
`assure`, `ship` or `done`, plus an already-recorded human waiver, retain their
historical gate result only for that round; every later implementation entry
requires the new contract.

## Task 1 — Requirements, capture and preflight engine

**Files:** create `scripts/factory/lib/evidence.py`,
`schemas/evidence-requirements.schema.json`, `schemas/evidence-capture.schema.json`,
`schemas/evidence-preflight.schema.json`, and `tests/test_evidence.py`.

- [ ] Implement strict schemas, safe canonical paths, live implementation
  identity, current-round calculation, requirements freeze/read, capture read,
  deterministic validation and durable/idempotent preflight publication.
- [ ] Resolve only the registered `factory/ITEM` checkout and snapshot its
  exact content-sensitive state twice. Prove control-checkout invocation,
  wrong/ambiguous worktree refusal, source mutation during capture and that
  Factory-state publication does not change the implementation digest.
- [ ] Derive suite discovery/pass/fail/skip counts and criterion coverage.
  Reject missing expected ids, exact-count drift, hidden failures, disallowed
  skips, purpose substitution and caller totals/pass flags.
- [ ] Re-scan exact raw stdout/stderr warning lines and preserve them in the
  result. Reject omissions or invented warning lines.
- [ ] Parse the closed discovery, execution, command and screen-probe adapters;
  cross-check every capture field. Reject exit-zero wrong output, fabricated
  passing ids, contradictory probe metadata, wrong screen/state, broken action,
  empty/missing screenshot and all path/hash/type races.
- [ ] Test metadata-only changes outside bound inputs, source/HEAD/dirty-state
  changes, missing/stale/corrupt evidence, symlink/rename replacement,
  concurrent matching/conflicting publication and every acceptance case above.

Run `python3 -m unittest tests.test_evidence -v`.

## Task 2 — CLI, event firewall and machine gates

**Files:** modify `scripts/factory/factory.py`, `scripts/factory/lib/machine.py`,
`scripts/factory/lib/initrepo.py`, `scripts/factory/lib/logs.py`; create
`tests/test_cli_evidence.py`; extend
`tests/test_machine.py`, `tests/test_round_scope.py`, `tests/test_cli.py`,
`tests/test_pipeline_walk.py`, and default-path fixtures where behavior changes.

- [ ] Add `factory evidence requirements ITEM [--adopt-current-round]`,
  `factory evidence preflight ITEM --capture ID`, and
  `factory verify-green ITEM --preflight ID`, all with JSON output options and
  stable refusal exit `2` versus malformed/internal exit `1`.
- [ ] Reserve authoritative evidence and `verify.green` events from generic
  logging, and reserve `stage.advance` from generic logging. Implement the
  locked, fsynced, strict-history authority writer and make machine-owned
  stage/event appends share that serialization boundary. Requirements freeze,
  round binding and verify-green publication are idempotent; lost responses
  never duplicate authority events.
- [ ] Require frozen requirements at the first `plan -> implement`, bind that
  revision on every review/verify/assure rework entry, and require a live
  validated preflight at both verification forward gates. SPECIAL resumes do
  not create a round. Preserve historical completed items and human assurance
  waivers exactly as described in Migration.
- [ ] Extend whole-tree validation and status JSON with requirements/preflight
  state and warning counts. Passing text cannot suppress warnings.
- [ ] Prove component-only receipts cannot cross a production requirement,
  missing purpose coverage, duplicate/omitted test outcomes, hidden warnings,
  missing tests/wrong screen/broken action refuse the actual stage advance, and
  tampering after `verify.green` re-closes the gate. Cover concurrent retries,
  conflicting authority writers and receipt-before-event crash repair.

Run:

```bash
python3 -m unittest tests.test_cli_evidence tests.test_machine \
  tests.test_round_scope tests.test_cli tests.test_pipeline_walk -v
```

## Task 3 — Producer and skill integration

**Files:** modify `skills/factory-plan/SKILL.md`,
`skills/factory-verify/SKILL.md`, `skills/factory-assure/SKILL.md`,
`skills/factory-ship/SKILL.md`; add
`skills/capabilities/references/evidence-capture.md`; extend
`tests/test_plugin_coherence.py`, `tests/test_plugin_structure.py`, and
`tests/test_default_path_invariance.py`.

- [ ] Plan writes the compact requirements file from spec acceptance criteria,
  named tests and declared runtime purpose, then freezes it before implement.
- [ ] Verify captures raw outputs and structured discovery/results through the
  documented adapter contract, writes command or blind-visual observations,
  runs preflight, surfaces every warning, and uses `verify-green`; it never
  calls generic log for that event.
- [ ] Visual capture records the neutral action, driver-observed route/state and
  screenshot/probe artifacts. Capability absence still parks for human rather
  than inventing evidence.
- [ ] Assure and ship treat the verified preflight as prerequisite evidence,
  not as a substitute for journey assurance, integrated/full-wave policy or
  human confirmation.
- [ ] Validate skill/engine command parity and preserve unrelated existing
  review, assurance and release semantics.

Run:

```bash
python3 -m unittest tests.test_plugin_coherence \
  tests.test_plugin_structure tests.test_default_path_invariance -v
python3 -m unittest discover -s tests -v
git diff --check
```

## Out of scope

- Evidence reuse across identities (FH-03), risk-based stage reduction (FH-02),
  image-semantic truth beyond the captured driver route/state, and automatic
  project-specific test-output parsers. Producers must emit the closed capture
  schema and preserve raw artifacts; the engine validates identity and
  consistency, not whether an arbitrary external tool lies.
