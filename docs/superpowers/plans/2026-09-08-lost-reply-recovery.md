# Lost child-reply recovery implementation plan

> **Execution:** direct engineering only; do not invoke the Factory harness.
> Implement in the three bounded tasks below, with one fresh independent review
> after each task and one whole-branch review before integration.

## Goal and boundary

After one unanswered child wait, classify what changed durably since that exact
dispatch. Adopt a complete result, preserve and continue a partial result once,
count an absent result as a transport failure, and stop on contradictory
evidence. Never launch overlapping replacement work or infer a substantive
pass from file existence.

0021 covers one parent-child handoff and recovery from its already-durable
outputs, including recovery by a fresh parent session. 0032 still owns pool
exhaustion, no-synthesis/degraded-council policy, coordination of a whole
fan-out across attempts, and resuming arbitrary prior council runs.

## Durable contract

`scripts/factory/lib/reconciliation.py` owns immutable dispatch checkpoints at:

```text
.factory/items/<item>/reconciliation/<attempt-id>/manifest.json
.factory/items/<item>/reconciliation/<attempt-id>/continuations.json
.factory/items/<item>/reconciliation/<attempt-id>/continuations/claim.json
```

`manifest.json` is created before dispatch with this closed shape (the
`dev`/`ino` values are JSON integers from `fstat`):

```json
{
  "version": 1,
  "attempt_id": "<32 lowercase hex>",
  "item": "<canonical item id>",
  "stage": "<current stage>",
  "stage_entry": 3,
  "obligation": "implement:task-4",
  "inputs": {".factory/items/<item>/plan.md": "<sha256>"},
  "evidence": {".factory/items/<item>/reviews/task-4.md": null},
  "item_file": {"sha256": "<sha256>", "dev": 1, "ino": 2},
  "log_prefix": {
    "bytes": 1234,
    "sha256": "<sha256>",
    "events": 27,
    "dev": 1,
    "ino": 3
  },
  "attempt_dir": {"dev": 1, "ino": 4},
  "manifest_file": {"dev": 1, "ino": 6},
  "checkout": {
    "path": "<canonical absolute worktree>",
    "head": "<40 hex sha>",
    "dev": 1,
    "ino": 5,
    "state_sha256": "<content-sensitive worktree digest>"
  }
}
```

`inputs` and `evidence` must each be non-empty mappings. `checkout` is `null`
outside implementation. Evidence values are the baseline SHA-256 or `null`
when absent. Duplicate or ancestor/descendant paths are refused. All paths are
normalized repository-relative POSIX paths and reject empty components, `.`,
`..`, NUL, absolute paths, and escape from the opened repository directory.

All reads and writes use an opened repository directory and component-by-
component `openat` traversal (`dir_fd` in Python) with `O_NOFOLLOW`; directories
also use `O_DIRECTORY`. A leaf is accepted only when `fstat` reports a regular
file. After each read, compare every opened child descriptor's `(dev, ino)` to
a no-follow `stat` of its name from its still-open parent, bottom-up. A mismatch
is a rename-replacement refusal. `items.load_item` and `logs.read_events` are
still called for their semantic validation, but their result is accepted only
when secure reads immediately before and after return the same bytes and inode;
the checkpoint hashes those securely read bytes. Baseline logs with skipped or
malformed events are refused.

The stage entry is the number of valid `stage.advance` events whose `data.to`
equals the current stage. The log prefix stores the exact byte length, hash,
valid-event count, and inode; inspection requires that the same log inode still
starts with those exact bytes, not merely that it has the same event count.
Input and evidence bytes are snapshotted only after item metadata, the log, and
the optional canonical Factory worktree have passed those checks.

### Publication and identity binding

`begin` generates a 32-character lowercase `secrets.token_hex(16)` attempt id,
creates its directory mode `0700` through anchored descriptors, and retains the
repository, `.factory`, `items`, item, reconciliation, attempt, and (for a
claim) continuations descriptors until the operation finishes. Every newly
created directory is opened no-follow, then its entry is made durable by
fsyncing its still-open parent and revalidating the complete descriptor chain;
failure is durability-uncertain, leaves the directory in place, and returns no
authorization. This applies separately to reconciliation, attempt, and
continuations directory creation. Publication is the same for a manifest and a
continuation marker:

The repository descriptor is also revalidated against the canonical repository
path; every "complete chain" check includes that root check.

1. Create a random hidden temporary leaf in the destination directory with
   `O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW`, mode `0600`.
   Obtain its `(dev, ino)` with `fstat` and include that identity in the closed
   manifest/marker payload before encoding it.
2. Write the complete canonical JSON (`sort_keys=True`, separators `(',', ':')`,
   UTF-8, one trailing newline), handling short writes; `fsync` and close it.
3. Revalidate every descriptor from the repository root through the
   destination directory, bottom-up, against its name in its open parent.
   Atomically publish without clobber using `link` with source and destination
   directory descriptors and `follow_symlinks=False`, then fsync the
   destination directory. A concurrent final leaf makes the operation a
   refusal.
4. The successful directory fsync is the commit point. Unlink the temporary
   alias and fsync the directory again on a best-effort cleanup path, then
   reopen and validate the final leaf, then revalidate the complete ancestor
   chain again before returning authorization.

No observer can see a partial final leaf. Failure before the link removes the
temporary leaf best-effort and leaves no final leaf. Failure after link but
before its directory fsync returns `publication durability uncertain` and no
dispatch authorization; it may leave only complete, same-inode final/temp
names. After the commit point, cleanup failure is reported in the returned
result as `cleanup_pending: true` but does not revoke the durable checkpoint;
the complete temporary hard-link is harmless and may be removed by a later
inspection. A post-commit directory-identity mismatch still returns an error
and no dispatch authorization. Tests assert these explicit states instead of
requiring impossible rollback after an injected filesystem failure.

The manifest binds itself without mutating the item log: its closed payload
contains both the attempt-directory identity and the temporary manifest-file
identity; atomic hard-link publication preserves the latter for
`manifest.json`. Inspection opens the final leaf no-follow and requires both
identities to match. Combined with the stored log inode and exact prefix hash,
this rejects an equal-length rewritten log, a copied/replaced manifest, or an
identically copied/relocated attempt directory in a fresh session.

The first continuation attempt also publishes a self-bound
`continuations.json` beside the directory, recording both the directory inode
and the binding file inode. Later or concurrent claims validate that external
binding before inspecting or publishing `claim.json`; replacing the
continuations directory therefore cannot reset the one-continuation limit.

Public publication outcomes are exact:

```python
class ReconciliationError(ValueError): ...

class PublicationUncertain(ReconciliationError):
    attempt_id: str
    committed: bool

begin(...) -> {"attempt_id": str, "cleanup_pending": bool}
claim_continuation(...) -> {
    "action": "continue|stop",
    "reason": "claimed|already-claimed|observation-changed",
    "cleanup_pending": bool
}
```

Invalid arguments, unsafe state, and schema/identity refusal raise
`ReconciliationError`. A concurrent existing final claim returns the `stop`
shape. An I/O failure before the destination-directory commit fsync raises
`PublicationUncertain(committed=False)` even if a complete linked leaf is
visible. An identity or final-leaf reopen/validation failure after commit raises
`PublicationUncertain(committed=True)` and returns no authorization. After the
commit and successful final validation, temp unlink or cleanup fsync failure
returns success with `cleanup_pending: true`; otherwise it is false. A later
inspection may remove only a verified complete same-inode temporary alias.

The worktree snapshot stores the canonical path and root `(dev, ino)`, HEAD,
and `state_sha256`. The latter hashes canonical length-prefixed records for:
`git status --porcelain=v1 -z --untracked-files=all`, binary unstaged and staged
diffs against HEAD, and every `git ls-files --others --exclude-standard -z`
path plus its no-follow type/mode and either regular-file bytes or symlink
target bytes. Git is invoked with argument arrays, `--no-ext-diff`,
`--no-textconv`, and a fixed locale. This detects further edits to an
already-dirty file even under a lossy textconv driver, as well as new untracked
content. Inspection revalidates both `ownership.canonical_worktree` and the
stored root identity.

Inspection takes an observed writer state, `active` or `terminal`, and the same
worktree path when the manifest carries one. It returns:

```json
{
  "classification": "complete|partial|absent|contradictory",
  "action": "adopt|continue|count-failure|stop|wait-active",
  "attempt_id": "...",
  "writer_state": "active|terminal",
  "fingerprint": "<sha256 of canonical current evidence state>",
  "changed_evidence": ["..."],
  "reason": "<specific obligation or mismatch>"
}
```

The fingerprint is SHA-256 of the same canonical JSON encoding of the current
item hash/stage, current full-log hash/length, sorted input and evidence states
(`absent` or `regular` plus SHA-256), and checkout path/HEAD/root identity/
`state_sha256`. It is an observation identifier, not proof of success.

Inspection rules, in order:

1. Validate the stored/requested item and attempt ids, closed manifest schema,
   manifest/binding/directory/log-prefix identity, current input hashes, safe
   evidence types, and the supplied/canonical checkout path and root identity.
   Any mismatch, input deletion/change, evidence deletion after a non-null
   baseline, or unreadable/symlinked/nonregular path is
   `contradictory/stop`, even when the caller reports an active writer.
2. Parse every complete event after the recorded byte prefix. A non-empty
   suffix without a trailing newline, invalid UTF-8/JSON, non-object event, or
   event without `event` and `ts` is treated as a write in progress only while
   writer state is active and returns `partial/wait-active`; with a terminal
   writer it is `contradictory/stop` and cannot fall through to evidence-based
   adoption. Otherwise the eligible
   completion edge is the first valid `stage.advance` after that prefix whose
   `data.from` equals the manifest stage. If any such edge exists, current item
   metadata must
   equal the `data.to` of the last subsequent `stage.advance`; otherwise state
   is contradictory. Leaving and later re-entering the baseline stage remains
   complete because the first eligible edge is retained.
3. If writer state is `active`, return `partial/wait-active` after the safety
   checks, even if evidence or a transition appears complete. A metadata stage
   change with no eligible edge is treated as an in-progress `machine.advance`
   only here; no result is adopted while its writer is active.
4. With a terminal writer, an eligible transition is `complete/adopt`. A
   changed item file or stage without that event is the terminal-crash case and
   returns `contradictory/stop` (machine writes metadata before its event).
5. If every evidence path changed from its baseline and is now a safe regular
   file, return `complete/adopt`. The parent reads the artifact and follows its
   normal PASS/BLOCK/reject/fail semantics; transport completeness is not a
   substantive verdict.
6. If a strict subset of evidence changed, or checkout HEAD/state changed,
   return `partial/continue`. Otherwise return `absent/count-failure`.

`claim_continuation` accepts only the exact terminal `partial/continue` result
returned by `inspect`. The host's terminal observation is the trust boundary;
the result carries it explicitly. Claim reloads and validates the checkpoint,
reruns terminal inspection, and requires equality of classification, action,
attempt, writer state, and fingerprint before publishing one; a changed
observation returns `stop` without creating a marker. It publishes
`continuations/claim.json` using the protocol above. The marker contains
version, attempt id, fingerprint, obligation, and its own temporary-file
`(dev, ino)` identity. `O_EXCL` makes exactly one
continuation possible for the entire dispatch attempt: repeated, concurrent,
or later changed-fingerprint claims return `stop`. A continued child always
gets a fresh `begin` checkpoint before dispatch; this prevents two parents from
authorizing overlapping continuations of one handoff.

Legacy work with no checkpoint is unbound and cannot be adopted automatically;
the skill preserves it and stops with the missing binding instead of deleting
or redispatching over it.

Fresh-session recovery uses `discover`: safely enumerate only 32-lowercase-hex
attempt directories beneath the opened reconciliation directory, validate each
self-bound manifest, and return the sorted attempt ids whose item, stage,
obligation, current input hashes, and optional canonical checkout match. Zero
matches is unbound; exactly one may be inspected; more than one is ambiguous
and the parent stops. Discovery never chooses "latest", mutates an attempt, or
turns a stale/unsafe candidate into authorization.
Any 32-hex candidate with an unsafe path, malformed schema, or failed
self-binding raises `ReconciliationError`; a safely read but nonmatching stale
candidate is ignored.

## Task 1 — Engine-owned checkpoint and classifier

- [x] Add `scripts/factory/lib/reconciliation.py` implementing:

```python
class ReconciliationError(ValueError): ...

class PublicationUncertain(ReconciliationError): ...

def begin(repo, item_id, stage, obligation, inputs, evidence,
          worktree=None) -> dict: ...

def discover(repo, item_id, stage, obligation, inputs,
             worktree=None) -> list[str]: ...

def inspect(repo, item_id, attempt_id, writer_state,
            worktree=None) -> dict: ...

def claim_continuation(repo, item_id, attempt_id, result) -> dict: ...
```

- [x] Reuse `items.load_item`, `logs.read_events`, and
  `ownership.canonical_worktree`; execute git with argument arrays only. Keep
  all checkpoint/marker filesystem operations descriptor-anchored and
  fail-closed under directory/leaf symlinks and rename replacement.
- [x] Add `tests/test_reconciliation.py` with real temporary repositories and
  git worktrees. Required tests:
  - begin writes the exact closed manifest before any simulated dispatch;
  - a fresh process discovers exactly one matching attempt; zero remains
    unbound and multiple matching attempts return all ids so the caller stops;
  - a post-checkpoint engine transition is complete while a metadata-only
    transition is contradictory;
  - all changed evidence is complete; a subset or checkout delta is partial;
  - unchanged terminal evidence is absent; active writer is wait-active;
  - stale input, wrong worktree, malformed manifest, symlinked evidence, and
    relocated/replaced attempt directories return `contradictory/stop` when a
    bound manifest can be read, while unsafe/unbound manifest paths raise
    `ReconciliationError`;
  - first continuation claim succeeds, a concurrent/repeated unchanged claim
    stops, and a changed fingerprint on the same attempt also stops;
  - use a private `FilesystemOps` object (accepted as a keyword-only `_ops`
    test seam by all four public functions) to inject failure
    at temp open, first/short write, file fsync, pre-link identity check, link,
    each directory fsync, temp unlink, post-link identity check, and final-leaf
    reopen. Pre-link failures leave no final;
    pre-commit link/fsync failures leave at most complete same-inode residue
    and no authorization; post-commit cleanup failures return
    `cleanup_pending`; all paths close every descriptor;
  - deterministically replace the attempt directory during manifest
    publication, replace the continuations directory and then the attempt directory during
    claim publication, fail each parent-directory fsync after newly creating
    reconciliation/attempt/continuations, and assert no authorization plus
    `PublicationUncertain.committed` at the precise commit boundary;
  - replace the log with an equal-length copy, truncate its prefix, interrupt
    after item save but before `stage.advance`, and mutate evidence between
    inspect and claim. Assert the exact refusal/result and filesystem state in
    each case.
- [x] Run `python3 -m unittest tests.test_reconciliation -v`; expect all tests
  green. Run `git diff --check`.

## Task 2 — Public CLI and bounded parent protocol

- [ ] Import `reconciliation` in both import branches of
  `scripts/factory/factory.py` and add:

```text
factory reconcile begin ITEM --stage STAGE --obligation NAME
  --input PATH... --evidence PATH... [--worktree PATH] --json
factory reconcile discover ITEM --stage STAGE --obligation NAME
  --input PATH... [--worktree PATH] --json
factory reconcile inspect ITEM ATTEMPT --writer-state active|terminal
  [--worktree PATH] [--claim-continuation] --json
```

  CLI exit codes: `0` for a valid result including `stop`; `1` for malformed
  arguments/internal errors; `2` for untrusted, stale, or contradictory state.
  `--claim-continuation` calls the append-only claim only after inspection and
  rewrites `action` to `stop` when already claimed.
- [ ] Add CLI cases to `tests/test_reconciliation.py`: direct-script and module
  invocation parity, exact JSON, refusal exit codes, active-writer claim
  refusal, and repeated claim idempotency.
- [ ] Add `skills/capabilities/references/disk-first-reconciliation.md` with
  the exact commands, result matrix, one host-native wait capped at 60 seconds,
  and this required order: begin checkpoint → dispatch → wait once → establish
  writer `active|terminal` using the host adapter → inspect → adopt, claim one
  continuation, count a genuine absence, or stop. An active writer causes the
  current stage invocation to return “still running”; it never waits again,
  fails the work, or dispatches a replacement.
- [ ] State that a complete artifact may encode PASS, BLOCK, rejection, or red
  tests; `complete` means transport completion only. Before finalization the
  parent re-reads current item stage and existing events, then performs only the
  missing normal side effects. If an earlier transition already landed, adopt
  it; never replay post-transition bids/learning as if they were pre-transition
  obligations.
- [ ] Run `python3 -m unittest tests.test_reconciliation -v` and both
  `python3 scripts/factory/factory.py --help` and
  `python3 -m scripts.factory.factory --help`.

## Task 3 — Wire every observed seam and prove integration

- [ ] Update `skills/factory-dispatch/SKILL.md`: create a stage checkpoint
  before step-4 dispatch; after one 60-second unanswered wait or on a returned
  “still running” re-entry, inspect before failure accounting or replacement.
  Remove “returned report is the only thing” as an authority claim.
- [ ] Update `skills/factory-implement/SKILL.md`: checkpoint each implementer
  and reviewer separately using plan/spec hashes, canonical worktree, and the
  task evidence path. A partial implementation preserves committed and
  uncommitted changes; after a terminal writer it claims one continuation for
  only missing implementation/test work. A complete implementation with no
  review dispatches the reviewer, not another implementer. Both verdicts remain
  required; commits, tests, or checkboxes alone never mean pass.
- [ ] Update `skills/council-review/SKILL.md`: checkpoint each selected seat
  against seed hash and its exact round file, then checkpoint synthesis. Reuse
  only current-attempt files. Dispatch only missing seats within that same
  attempt; do not add pool/no-synthesis recovery or reconstruct a report that
  the read-only seat never returned.
- [ ] Update `skills/factory-review/SKILL.md` and
  `skills/factory-triage/SKILL.md`: checkpoint their council child and adopt a
  current synthesis before continuing the existing walk/judgement/triage
  finalization. Re-read stage/events so review outcomes, transitions, roadmap
  edits, and bids are not duplicated. Post-transition learning remains a named
  missing obligation rather than being silently skipped.
- [ ] Update `skills/factory-assure/SKILL.md`: checkpoint every journey against
  impact/contract/base-SHA inputs and its exact structured report/evidence
  paths. Inspect before deleting a prior round; preserve current-attempt
  evidence and continue only missing scenario coverage. Do not infer verdicts
  from screenshots or weaken blindness/human gates.
- [ ] Cross-link the protocol from `skills/capabilities/SKILL.md` and
  `skills/capabilities/references/orchestration-patterns.md`.
- [ ] Extend `tests/test_plugin_coherence.py` to assert every parent skill
  names the begin-before-dispatch and inspect-before-retry order, the 60-second
  single wait, active-writer stop, exact evidence binding, and the 0032 scope
  exclusions. These are static contract checks; behavioral classification and
  continuation proofs stay in `tests/test_reconciliation.py`.
- [ ] Add an integration test in `tests/test_reconciliation.py` that replays:
  committed and uncommitted implementation deltas, missing reviewer evidence,
  complete council seats, completed synthesis, partial assurance evidence,
  interrupted finalization with an already-recorded transition, stale input,
  wrong checkout, active writer, and repeated unchanged partial evidence.
  Assert classifications, continuation counts, unchanged worktree bytes,
  unchanged existing events, and zero authorization for duplicate dispatch.
- [ ] Run `python3 -m unittest tests.test_reconciliation tests.test_plugin_coherence -v`.
- [ ] Run `python3 -m unittest discover -s tests -v`.
- [ ] Run `git diff --check` and verify only this plan, the new engine/tests/
  reference, `factory.py`, the six named parent skills, and the two capability
  references changed.

## Acceptance

1. Every covered parent waits at most once for 60 seconds before producing a
   durable, inspectable routing result.
2. Complete durable work is adopted without duplicate dispatch or side effects,
   irrespective of its substantive verdict.
3. Partial work is preserved and the same unchanged snapshot can continue only
   once; concurrent parents cannot both claim it.
4. Active, stale, unbound, contradictory, symlinked, or wrong-checkout evidence
   cannot authorize replacement or success.
5. Existing failure caps count established failures and genuinely absent
   results, never a lost reply with bound durable progress.
6. Pool exhaustion and whole-fan-out resumption remain explicitly deferred to
   0032.
