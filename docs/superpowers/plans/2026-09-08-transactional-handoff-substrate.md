# Crash-consistent control-operation substrate

> **Execution:** direct engineering only. Do not invoke the Factory harness or
> its workflow skills. Use a fresh `gpt-5.6-sol` xhigh implementation context
> for each code task and a fresh independent review context. Maximum three
> review/revise iterations per task; a third rejection parks this branch.

## Goal

Build the smallest reusable control-plane substrate needed to unblock the
parked 0036 plan-feasibility gate and FH-04 evidence preflight:

- strict, race-detecting snapshots of config and other control files;
- durable owner-bound tickets that carry an exact snapshot across CLI
  processes without persisting an ownership token;
- idempotent, crash-recoverable multi-file replacements plus exactly-once
  authoritative events; and
- a prepared-advance API that can later combine domain changes and a stage
  transition in one operation.

This slice supplies primitives and tests. It does not enable a new gate, add a
public command, migrate existing transitions, create evidence requirements, or
implement the 0036 acceptance graph.

## Decisions and boundaries

- Existing `machine.advance` transition results, default configuration, CLI
  output, event bytes/order, and serialized fixture bytes remain unchanged.
  Existing mutation paths gain one shared item lock and fsync durability; new
  transactional behavior remains an explicitly invoked API.
- POSIX advisory locking (`fcntl.flock`) is the supported baseline. Current CI
  is Ubuntu and active development is macOS. Windows locking is a separate
  portability item if Windows becomes supported.
- Future 0036 scope claims are limited to complete **Git-observable** paths:
  intervening commits, rename/copy old and new names, and final index/worktree/
  untracked state. An uncommitted modify-then-byte-restore before inspection is
  explicitly unobservable and requires a future OS confinement/monitoring
  project if it must be prohibited.
- Recovery always rolls a matching operation forward. It never guesses,
  rolls back, overwrites a third state, deletes diagnostic evidence, or steals
  an implementation owner.
- Python 3 standard library only. No wall-clock ordering or PID liveness is an
  authority boundary.

## Task 1 — Safe snapshots and strict config state

**Files:** create `scripts/factory/lib/safeio.py`,
`scripts/factory/lib/config_state.py`, `tests/test_safeio.py`, and
`tests/test_config_state.py`; minimally refactor
`scripts/factory/lib/worker_attempts.py` to reuse safe I/O without changing its
public API or artifacts.

### API

```python
# safeio.py
@dataclass(frozen=True)
class FileSnapshot:
    root: Path
    relative: PurePosixPath
    data: bytes
    sha256: str
    file_identity: tuple
    directory_identities: tuple

@dataclass(frozen=True)
class MissingSnapshot:
    root: Path
    relative: PurePosixPath
    parent_identities: tuple
    transaction_nonce: str

def snapshot_path(root, relative, *, limit=1_048_576,
                  allow_missing=False) -> FileSnapshot | MissingSnapshot: ...
def snapshot_many(root, relatives, *, limit=1_048_576,
                  allow_missing=False) -> tuple[FileSnapshot | MissingSnapshot, ...]: ...
def revalidate(snapshot_or_many) -> None: ...
def publish_exclusive(root, relative, data) -> FileSnapshot: ...
# Interrupted directory-tail retry form; reuse the original observation.
def publish_exclusive(missing: MissingSnapshot, data) -> FileSnapshot: ...
def replace_if_unchanged(snapshot, data) -> FileSnapshot: ...

# config_state.py
@dataclass(frozen=True)
class ConfigSnapshot:
    file: FileSnapshot
    value: dict

def capture(repo) -> ConfigSnapshot: ...
def enabled(snapshot, gate) -> bool: ...
def revalidate(snapshot) -> None: ...
```

### Invariants and tests

- Resolve the root once, open every path component descriptor-relative with
  `O_DIRECTORY|O_NOFOLLOW`, and open leaves with `O_NOFOLLOW|O_NONBLOCK`.
  Require regular files, strict UTF-8 where decoded, bounded reads, and stable
  `(device,inode)` identities for directories and
  `(device,inode,size,mtime_ns,ctime_ns)` for leaves. Directory timestamps are
  deliberately excluded: publishing a ticket under an item directory must not
  invalidate sibling snapshots. Reopen the complete canonical chain after a
  multi-file read; a replaced/detached ancestor still changes device/inode.
- Reject absolute/backslash/dot/traversal/NUL paths, duplicates, symlinks,
  FIFO/device/socket leaves, oversize input, short reads, invalid UTF-8,
  in-place mutation, leaf replacement, and replacement/detachment of every
  ancestor. Inject filesystem operations at each boundary for deterministic
  race tests.
- With `allow_missing=True`, absence is captured only after safely opening the
  deepest existing parent chain and proving the first missing component absent
  with a descriptor-relative lookup. `MissingSnapshot` records that chain and
  the unresolved safe component tail. Revalidation requires the same existing
  parents and continued absence of the first missing component. Publication may
  create the missing directory tail descriptor-relatively, one component at a
  time with mode `0700`. `MissingSnapshot` carries a fresh transaction nonce;
  the target-bound recovery record binds that nonce and validates every staging
  name as the exact basename derived from it and the entry/attempt indexes
  before using that name in any filesystem call. After mkdir and parent fsync,
  the staging inode is journaled and fsynced before it is eligible for
  installation. A crash in that binding gap leaves an unbound staging directory
  as untouched diagnostic evidence; recovery durably records its identity and
  a new unique attempt before creating that attempt, then continues forward.
  The journal retains the exact attempt history and identities while recovery
  is active. A matching retry reuses the original `MissingSnapshot` and adopts
  only durably bound exact directories; a fresh snapshot cannot adopt even a
  same-parent journal because its nonce differs. Both publication overloads
  reject a recovery record found above the snapshot parent, while a fresh
  root/path call also rejects one at that parent. A symlink, non-directory,
  replacement, fresh absence observation, malformed recovery name, or
  unexpected pre-existing component refuses without outside mutation. This
  supports ordinary absent `cost/answer.md` and new evidence round directories
  without weakening containment.
- `publish_exclusive` uses a no-follow exclusive temporary regular file,
  keeps its descriptor open, writes all bytes, fsyncs it, verifies the temp
  name still denotes that inode, installs the absent final name without
  overwrite, removes any substituted published entry on detected mismatch,
  fsyncs the directory, and verifies the resulting snapshot.
- `replace_if_unchanged` accepts only the exact live snapshot, uses an atomic
  same-directory replacement, fsyncs, and verifies expected bytes and the
  canonical parent chain. Mutation APIs hold an advisory exclusive lock on the
  exact opened root inode across comparison and installation, so a cooperating
  writer cannot enter the compare-to-replace gap. A mismatch writes nothing.
  POSIX does not offer Python stdlib compare-and-rename or unlink-by-inode
  primitives: a hostile same-user process that ignores the advisory lock can
  still mutate in the final syscall boundary, and the API detects/refuses that
  interference without claiming to prevent it.
- `config_state.capture` strict-decodes JSON with duplicate keys rejected and
  validates the complete object using the existing config schema. Missing,
  malformed, invalid, unsafe, or concurrently replaced config raises
  `ConfigStateError`; it never becomes an implicit disabled result.
- `enabled` reads only the captured object. Tests replace enabled with disabled
  and disabled with enabled between capture and revalidation and prove both
  refuse.
- Move only genuinely identical descriptor/atomic helpers out of
  `worker_attempts`; prove its manifests, streams, terminal receipts, errors,
  and default-path captures remain byte-compatible.

Run:

```bash
python3 -m unittest tests.test_safeio tests.test_config_state \
  tests.test_worker_attempts tests.test_default_path_invariance -v
git diff --check
```

Fresh independent Task 1 review. Commit on PASS as
`feat: add strict control snapshots`.

## Task 2 — Owner-bound tickets and recoverable operations

**Files:** create `scripts/factory/lib/control.py`,
`schemas/control-ticket.schema.json`, `schemas/control-intent.schema.json`,
`schemas/control-commit.schema.json`, and `tests/test_control.py`; add a public
read-only ownership verifier to `scripts/factory/lib/ownership.py`; modify
`scripts/factory/lib/logs.py` and `scripts/factory/factory.py`; extend
`tests/test_ownership.py` and `tests/test_cli.py`.

### Storage

```text
.factory/items/<id>/control/
  lock
  active.json
  tickets/<ticket-id>/
    manifest.json
    blobs/<sha256>
  operations/<operation-id>/
    intent.json
    blobs/<sha256>
    commit.json
```

All JSON schemas are closed and versioned. IDs are lowercase SHA-256 digests
of canonical request identities. Blob names equal their content hashes and are
published exclusively. `owner_sha256` is the only ownership value persisted;
the token itself must not occur in any control artifact, error, event, or Git
content.

### API

```python
@contextmanager
def item_lock(repo, item_id): ...

def issue_ticket(repo, item_id, *, kind, key, owner_token,
                 config, inputs, metadata) -> DurableTicket: ...
def load_ticket(repo, item_id, ticket_id, *, owner_token) -> DurableTicket: ...
def revalidate_ticket(ticket) -> None: ...

def commit_operation(repo, item_id, *, kind, key, request,
                     prerequisites=(), replacements=(), events=()) -> CommitReceipt: ...
def recover_pending(repo, item_id) -> RecoveryResult: ...
def require_settled(repo, item_id) -> None: ...
```

### Ticket contract

- Issue only while the supplied token matches the live 0020 ownership record
  and canonical checkout. Bind the ticket to the owner digest, checkout path
  and identity, config snapshot, exact input snapshots/blobs, and caller
  metadata. An identical issue adopts the existing ticket; a conflicting
  request for the same `(kind,key)` refuses.
- A later process must provide the same token through the existing
  `FACTORY_IMPLEMENTATION_OWNER` capability, then `load_ticket` and
  `revalidate_ticket` against the current ownership record, checkout,
  config, and input namespace. This is the cross-process transport 0036 needs.

### Operation contract

- Hold a short-lived per-item `flock` for all inspection/publication. Safely
  open the item/control namespace without following links. A crash releases
  the advisory lock; durable `active.json` supplies recovery state.
- Canonical intent records kind/key/request digest, exact prerequisite before
  identities/hashes, ordered replacements with before and after hashes/blobs,
  and ordered authoritative events. Events carry `operation_id`.
- Publish and fsync the immutable intent and blobs, then publish `active.json`.
  Apply each replacement in declared order. An existing-file prerequisite uses
  `replace_if_unchanged`; a `MissingSnapshot` uses `publish_exclusive`. For each
  step, exact before (matching file or proven absence) means apply, exact after
  means adopt, and any third state refuses. This makes creation of FH-04's new
  immutable round binding a first-class transactional effect. Metadata/stage
  replacement is conventionally last.
- Strict-read the complete log: invalid UTF-8, malformed/non-object lines,
  missing required keys, duplicate operation events, or a conflicting event
  refuses. Append each missing canonical event in one `O_APPEND` write and
  fsync. An exact existing event is adopted.
- After every effect is verified, publish immutable `commit.json`, then remove
  and directory-fsync `active.json`. A matching retry at any crash point rolls
  forward and returns the same receipt. A different operation while active
  refuses until `recover_pending` settles or reports the conflicting state.
- Fault-injection tests cover failure after intent, every blob, active marker,
  every replacement, each event append, commit receipt, and active removal.
  Matching retry yields one replacement effect and one event; conflicting
  retry/third-state mutation/duplicate event fails closed.
- Every existing `logs.append_event` call acquires this same item lock, fsyncs
  its single `O_APPEND` write, and accepts an already-held validated lock from
  engine code to avoid self-deadlock. `machine.advance` will hold the lock
  across its metadata write and event append in Task 3. This serializes legacy
  writers with control operations while preserving event bytes and order.
- Generic `factory log` rejects `stage.advance`, `verify.green`, every
  `evidence.*`, and every `control.*` event. Engine-internal writers retain an
  explicit locked append path. Future domain writers must use a typed command;
  a public event name can no longer impersonate control authority.
- Cross-process tests prove ticket reload, wrong/missing/released owner refusal,
  config/input replacement refusal, original snapshot preservation, and no
  token bytes on disk. Namespace attack tests cover every new file/directory.

Run:

```bash
python3 -m unittest tests.test_control tests.test_ownership \
  tests.test_worker_attempts tests.test_cli -v
git diff --check
```

Fresh independent Task 2 review. Commit on PASS as
`feat: add recoverable control operations`.

## Task 3 — Prepared implementation-entry seam and compatibility proof

**Files:** modify `scripts/factory/lib/machine.py`,
`scripts/factory/lib/breaker.py`, `scripts/factory/lib/cost.py`, and
`scripts/factory/lib/paths.py`; create `tests/test_control_advance.py`; extend
`tests/test_machine.py`, `tests/test_round_scope.py`,
`tests/test_pipeline_walk.py`, and `tests/test_default_path_invariance.py`.

### API and behavior

```python
@dataclass(frozen=True)
class PreparedImplementEntry:
    item_id: str
    source: str
    destination: Literal["implement"]
    operation_key: str
    item_snapshot: FileSnapshot
    log_snapshot: FileSnapshot | MissingSnapshot
    config: ConfigSnapshot
    cost_answer_snapshot: FileSnapshot | MissingSnapshot
    prerequisites: tuple
    replacements: tuple
    events: tuple
    replacement_item: bytes
    stage_event: dict
    breaker_verdict: dict

def prepare_implement_entry(repo, item_id, *, operation_key, reason=None,
                            config=None, prerequisites=(), replacements=(),
                            events=()) -> PreparedImplementEntry: ...
def commit_implement_entry(prepared) -> tuple[dict, dict, CommitReceipt]: ...
```

- This first prepared seam deliberately supports only transitions whose
  destination is `implement`: normal plan exit, review/verify/assure rework,
  and SPECIAL resume to a paused implementation. Those are the entry points
  both blocked features need; other destinations remain future generalization.
- All domain prerequisites, replacement bytes, and extra events are bound at
  **prepare** time, not supplied later. An in-memory prospective view overlays
  those exact replacements and events on the snapshotted item/log. Legality,
  breaker precondition, rejection caps, and `_gate_implement` execute against
  that prospective state without touching disk. Thus a completed plan plus an
  atomically proposed rework task can pass, while a missing proposed task fails.
- It can validate plan-to-implement before any implementation checkout exists.
  Checkout-bound validation happens later when 0036 issues a dispatch ticket.
  One strict config snapshot is supplied or captured; breaker and gate helpers
  in this path may not reread config.
- Capture `cost/answer.md` as an engine-owned `FileSnapshot` or securely proven
  `MissingSnapshot`. Refactor breaker answer parsing so both precondition and
  verdict consume those captured bytes, never reread the path. Bind and
  revalidate the answer snapshot in the committed operation; deletion,
  creation, replacement, or mutation after preparation refuses.
- Factor cost aggregation so it can consume a supplied strict event sequence
  and frozen `now`. Append the proposed `stage.advance` in memory, derive the
  exact post-transition breaker verdict, and bind `cost.breaker` into the same
  operation when it fires. `commit_implement_entry` returns the same
  `(meta, verdict)` values the current CLI needs plus the receipt. A retry
  returns the persisted verdict without a second breaker or stage event.
- Commit revalidates the prepared item/log/config snapshots, then calls
  `control.commit_operation` with the already-bound domain replacements/events,
  followed by `item.md`, `stage.advance`, and conditional `cost.breaker`. This
  ordering lets 0036 append tasks/sidecar and reject+advance once, while FH-04
  binds a requirements revision to the same implementation entry.
- A stable caller operation key is mandatory and part of the prepared request;
  timestamps are generated once during preparation and persisted in intent.
  Matching cross-process retry adopts the receipt. Conflicting content for the
  same key refuses.
- Wrap the current legacy `advance()` body in the shared item lock and pass that
  held lock through its event appends. Do not route legacy calls through the
  new transactional seam yet. Tests prove every existing transition result,
  exception, metadata byte, log byte, event order, CLI rendering, and default
  fixture is unchanged. New seam tests prove prospective rework validation,
  plan-to-implement without a worktree, exact breaker preservation, recovery at
  every boundary, and dispatch-ticket refusal until a canonical owned clean
  checkout exists.
- Document the intended consumers in module docstrings: 0036 will add
  `plan-dispatch begin/finish` on tickets and complete Git-observable scope;
  FH-04 will use operations for requirements freeze, round binding, preflight,
  and exactly-once `verify.green`. No generic `factory log` migration occurs in
  this slice.

Run:

```bash
python3 -m unittest tests.test_control_advance tests.test_machine \
  tests.test_round_scope tests.test_pipeline_walk \
  tests.test_default_path_invariance -v
python3 -m unittest discover -s tests -v
git diff --check
```

Fresh independent Task 3 review. Commit on PASS as
`feat: add prepared implementation transitions`.

## Final review and integration

- Run the authoritative full suite and `git diff --check`.
- A fresh whole-feature reviewer executes cross-process ticket, lost-response,
  every crash boundary, conflict, hostile namespace, pre-checkout transition,
  post-checkout dispatch refusal, and default-invariance journeys. Maximum
  three iterations.
- Merge only this isolated branch after PASS, rerun the full suite on main,
  and push only the green merged main branch. Preserve unrelated dirty files.

## Explicit non-goals

- 0036 acceptance schema, plan-check/dispatch commands, worker scope scanner,
  or task finalizer.
- FH-04 requirements/capture/preflight schemas, evidence adapters, migration,
  or verify-green command.
- FH-03 receipt reuse, FH-06 worker supervision, or FH-07 derived ledger.
- Windows locking, OS-level path confinement, filesystem event monitoring,
  rollback, automatic owner takeover, or automatic conflict repair.
