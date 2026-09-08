# Plan acceptance-feasibility and resumability

> **Execution:** direct engineering only; do not invoke the Factory harness.
> **Review:** each task gets a fresh independent review, with at most three
> review/revise iterations. A third rejection parks the branch unmerged.

## Goal and boundary

Implement item 0036 as the mechanically testable union of retrospective FH-01
and the bounded part of FH-05. Before an enabled item enters implementation,
and immediately before every implementation dispatch, Factory must be able to
answer from a closed artifact:

- which paths the current worker and each joint participant may modify;
- who provides every required path, interface, runtime, device, or route;
- whether an external provider is already delivered or belongs to an explicit
  jointly staged delivery;
- which tests cover each requirement and which integrated gates bind a joint
  delivery;
- which unchecked task is the resume cursor and why the contract changed.

This gate proves declaration completeness and graph consistency. It does not
prove a device is connected, a route works, evidence is fresh, or a technical
strategy is wise. Those remain FH-04 evidence validation and 0014 approach
convergence. It never executes a declared test or preflight command.

The feature is opt-in through `"feasibility"` in `.factory/config.json`'s
`gates` array. Do not add it to `initrepo.DEFAULT_CONFIG`. Every valid config
without that gate retains existing behavior and output. At an implementation
boundary, unreadable, unsafe, duplicate-key, malformed, or concurrently
replaced config is an error, never an implicit disabled result.

## Canonical artifact

An enabled item owns `.factory/items/<id>/acceptance.json`. JSON is strict
UTF-8 with duplicate keys rejected. The root and every nested object are
closed. Arrays that act as sets reject duplicates.

```json
{
  "version": 1,
  "item": "0071-readiness-card",
  "spec_sha256": "64 lowercase hex",
  "plan_structure_sha256": "64 lowercase hex",
  "revision": {
    "reason": "Initial complete contract",
    "changed_sections": ["initial"]
  },
  "resume_cursor": {
    "strategy": "first-unchecked-task"
  },
  "participants": [
    {
      "item": "0071-readiness-card",
      "owned_paths": ["Features/Readiness"]
    },
    {
      "item": "0063-root-composition",
      "owned_paths": ["App/RootView.swift"]
    }
  ],
  "dependencies": [
    {
      "item": "0063-root-composition",
      "relation": "joint",
      "provides": ["root-mount", "home-route"]
    }
  ],
  "resources": [
    {
      "id": "readiness-view",
      "kind": "path",
      "value": "Features/Readiness/Card.swift",
      "access": "modify",
      "provider": "0071-readiness-card",
      "availability": "available"
    },
    {
      "id": "readiness-interface",
      "kind": "interface",
      "value": "readiness-api",
      "access": "use",
      "provider": "0071-readiness-card",
      "availability": "available"
    },
    {
      "id": "root-mount",
      "kind": "path",
      "value": "App/RootView.swift",
      "access": "modify",
      "provider": "0063-root-composition",
      "availability": "available"
    },
    {
      "id": "home-route",
      "kind": "route",
      "value": "signed-in/home",
      "access": "use",
      "provider": "0063-root-composition",
      "availability": "available"
    },
    {
      "id": "ios-simulator",
      "kind": "runtime",
      "value": "iOS simulator",
      "access": "use",
      "provider": "environment",
      "availability": "available"
    }
  ],
  "interfaces": [
    {
      "id": "readiness-api",
      "owner": "0071-readiness-card",
      "consumers": ["0063-root-composition"],
      "contract": "Root composes ReadinessCard(model:)"
    }
  ],
  "criteria": [
    {
      "id": "AC-1",
      "statement": "The real Home route mounts the readiness card",
      "requires": ["readiness-view", "readiness-interface", "root-mount", "home-route", "ios-simulator"],
      "tests": ["component-tests", "integrated-tests"]
    }
  ],
  "tests": [
    {
      "id": "component-tests",
      "purpose": "component",
      "command": ["xcodebuild", "test", "-only-testing:ReadinessTests"],
      "covers": ["readiness-view", "readiness-interface"]
    },
    {
      "id": "integrated-tests",
      "purpose": "integrated",
      "command": ["xcodebuild", "test", "-only-testing:HomeFlowTests"],
      "covers": ["readiness-view", "readiness-interface", "root-mount", "home-route", "ios-simulator"]
    }
  ],
  "delivery": {
    "mode": "joint-staged",
    "participants": ["0071-readiness-card", "0063-root-composition"],
    "merge_order": ["0071-readiness-card", "0063-root-composition"],
    "shared_gates": ["integrated-tests"]
  },
  "out_of_scope": ["physical-device and TestFlight proof"]
}
```

`spec_sha256` hashes exact `spec.md` bytes. `plan_structure_sha256` hashes
exact `plan.md` bytes after normalizing only checkbox markers `[x]` and `[X]`
to `[ ]`; whitespace, prose, task order, commands, and every other byte remain
bound. Normal progress can tick tasks without invalidating the contract.
Appending or rewriting a task changes the structure hash and requires a new
revision reason and changed-section list.

`resume_cursor.strategy` has the single value `first-unchecked-task`. The
validator derives the report and handoff cursor from the first task returned by
the existing `work.unticked_tasks` parser, or `COMPLETE` when none remain. The
sidecar therefore declares how to resume without duplicating mutable progress.
Ticking a task changes no sidecar byte; the next inspection mechanically moves
the cursor. Rework appends new unchecked tasks and refreshes the structure hash
and revision before the rejecting stage returns the item to implementation.
This is a handoff cursor, not worker heartbeat or process-resume state;
0021/0032/FH-06 still own supervision.

## Schema and semantic contract

Create `schemas/acceptance-plan.schema.json`. Factory item ids use
`^[0-9]{4}-[a-z0-9-]+$`; hashes use `^[0-9a-f]{64}$`; `kind` is
`path|interface|runtime|device|route`; `access` is `read|modify|use`;
`availability` is `available|unavailable`; dependency relation is
`delivered|joint`; test purpose is `component|integrated|full-wave|release`;
delivery mode is `solo|component-only|joint-staged`. All displayed keys are
required. `interfaces` and `dependencies` may be empty; every other array and
free-text contract field is non-empty by semantic validation. There is no
arbitrary line, byte, task, or step-count ceiling on the Markdown plan. The
1 MiB safety read limit below is a hostile-input resource bound, not an
acceptance compactness rule; a regular plan below it is judged only by the
declared fields and graph.

Create `scripts/factory/lib/feasibility.py`:

```python
class FeasibilityError(ValueError): ...

@dataclass(frozen=True)
class PlanSnapshot:
    report: dict
    plan_bytes: bytes
    spec_bytes: bytes
    acceptance: dict
    pending_tasks: tuple[str, ...]
    pending_task_markers: tuple
    namespace_identities: tuple
    checkout_baseline: object | None

def inspect(repo, item_id, *, dispatch=False, checkout=None) -> dict: ...
def require(repo, item_id, *, dispatch=False, checkout=None) -> PlanSnapshot | None: ...
def revalidate(snapshot) -> None: ...
def worker_handoff(snapshot, *, tasks=None) -> str: ...
def inspect_worker_scope(snapshot, checkout) -> dict: ...
def finalize_tasks(snapshot, checkout) -> None: ...
```

`require` strict-reads and validates config first. It returns `None` only for a
valid config that omits `feasibility`; otherwise it returns one immutable
snapshot or raises. `inspect` exposes only deterministic JSON-safe report
fields: status (`disabled|pass|fail`), item, hashes, cursor, current-worker
owned paths, delivery graph, task, errors, and handoff. It never exposes bytes
or file descriptors. Errors are stable and sorted.

Validation rules:

1. Securely read config, item metadata, `spec.md`, `plan.md`,
   `acceptance.json`, and referenced dependency metadata from the canonical
   repository namespace. Walk every component using descriptor-relative
   `openat`, `O_NOFOLLOW`, and `O_DIRECTORY`; open leaves with
   `O_NONBLOCK|O_NOFOLLOW`, require regular-file `fstat`, read at most 1 MiB,
   and decode strict UTF-8. Record directory/file
   `(device,inode,size,mtime_ns,ctime_ns)`. Reopen the complete chain by name
   and compare identities after the cross-file snapshot; reject replacement,
   detached/replaced ancestors, in-place mutation, short read, FIFO/device,
   symlink, duplicate JSON keys, or invalid bytes. Reads never create or
   repair. Injected filesystem operations make races deterministic in tests.
2. Validate config against its closed schema. Missing/malformed config,
   invalid gates, duplicate keys, unsafe namespace, or concurrent replacement
   raises; it cannot silently disable feasibility. Compatibility is promised
   for valid disabled configurations only.
3. Validate the closed acceptance schema, requested item id, exact spec hash,
   normalized plan-structure hash, and the fixed resume strategy. Transition
   and dispatch modes both require an unchecked task: a rejecting stage must
   prepare rework before it can return the item to implementation. The report
   derives the first task or `COMPLETE`; no producer stores that value and no
   prose scoring occurs.
4. Reject duplicate participant/dependency/resource/interface/criterion/test
   ids, duplicate set entries, and dangling references. Every resource is
   required by a criterion. Every criterion has resources and tests, and the
   union of its named tests' `covers` sets includes every required resource.
   A test may cover only declared resources.
5. Every non-environment provider is the current item or one dependency. The
   dependency's `provides` set equals exactly the resources naming it. A
   dependency item must exist and parse from the same safe snapshot. A
   `delivered` dependency must currently be `done`, is not a participant, and
   cannot provide a modify resource. A `joint` dependency is a participant.
6. Participants declare ownership only. Delivery participants equal participant
   objects exactly. Solo and component-only contain only the current item,
   merge order `[item]`, and no joint dependency. Joint-staged contains the
   current item plus every and only joint dependency, at least two participants,
   and an exact no-duplicate merge permutation.
7. Normalize repository-relative paths as component-boundary prefixes. Reject
   absolute paths, backslashes, empty/dot/traversal components, NUL, `.git`,
   and overlap between different participants. Every modify path is contained
   by exactly one owned prefix of its provider; external modification requires
   a joint participant. At dispatch, resolve from the actual canonical
   implementation checkout: walk every existing ancestor without following
   symlinks and reject any source path/prefix that escapes or crosses one. A
   not-yet-created tail is allowed only below a safely opened existing parent.
8. `environment` may provide only runtime/device resources. Path/interface/
   route resources require an item provider. Path resources use read/modify;
   other kinds use `use`. Any required resource declared unavailable refuses.
   Every interface is named by exactly one interface resource; that resource's
   value names the `interfaces.id`, its provider equals the interface owner,
   and consumers belong to the current item/dependency graph.
9. Joint shared gates are non-empty integrated/full-wave/release tests. For
   every criterion using a joint provider, at least one criterion test is a
   shared gate and its criterion-local shared gates collectively cover all the
   criterion's resources. An unrelated integrated test cannot launder a
   disconnected graph. Component-only criteria use only component tests and
   require no route/device resources.

The 0071/0063 impossible-solo fixture fails because 0071 acceptance requires
modifying 0063-owned `RootView.swift`. Renaming the mode is insufficient: the
provider must be a joint dependency/participant, owned prefix and provided
resource must agree, merge order must cover both, and a criterion-local shared
gate must cover the joint acceptance. A genuinely component-only fixture with
one owner and component tests passes.

## Dispatch snapshot and scope

For enabled mode, no implementation consumer independently rereads `plan.md`,
`spec.md`, or `acceptance.json` after validation:

- `require(..., dispatch=True, checkout=canonical_worktree)` runs inside the
  held 0020 ownership lifetime and returns exact validated bytes, ordered
  unchecked task texts and marker byte ranges, namespace identities, a clean
  checkout baseline, and a handoff limited to the current item's owned paths.
  `revalidate(snapshot)` immediately precedes attempt creation and backend
  launch. If a pathname changes afterward, the worker still consumes immutable
  snapshot bytes, never the new revision.
- `worker_handoff` includes exact plan/spec, current task(s), current owner's
  paths, provider/interface graph, shared gates, revision, and cursor. Joint
  ownership never grants this worker another participant's paths.
- Enabled dispatch requires the implementation checkout to start at the
  recorded HEAD with a clean index, worktree, and untracked set. After a
  headless backend returns, `inspect_worker_scope` requires the baseline HEAD
  to remain an ancestor and inventories every touched path, including paths
  later reverted. It walks every intervening commit, diffs it against every
  parent with NUL-delimited `--name-status -z -M -C`, and unions both old and
  new names for renames/copies; it also unions the final index diff, worktree
  diff, and untracked files. A merge commit is inspected against every parent.
  Non-zero Git status, malformed records, undecodable paths, history rewrite,
  a dirty final checkout, or a path outside the current participant's owned
  prefixes fails closed. The result records the complete touched-path set and
  one stable non-retryable reason: `scope_inspection_failed`, `history_rewrite`,
  `dirty_checkout`, or `scope_violation`.
- Successful headless completion never calls legacy `_tick_plan`. After the
  backend, tests, result write, and scope inspection pass, `finalize_tasks`
  revalidates every config/spec/plan/acceptance/dependency identity in the
  original snapshot. It constructs replacement bytes only from
  `snapshot.plan_bytes`, changing only the exact `[ ]` markers captured for
  the dispatched tasks. It writes through the already validated item
  directory using a no-follow exclusive temporary regular file, `fsync`s the
  file and directory, checks the canonical plan still has the snapshotted
  identity, atomically replaces it, and verifies the canonical namespace now
  names the expected bytes. Only then may `implement.completed` be logged.
  Any concurrent artifact or ancestor change writes no plan byte and no
  completion event; it preserves worker commits/result evidence and returns
  exit 2 with the non-retryable reason `concurrent_plan_change`.
- The in-process skill runs `factory plan-check ITEM --dispatch --worktree PATH
  --json` immediately before every implementer or fix dispatch while the outer
  claim is held. It passes only that returned handoff/task to the fresh worker.
  After independent review, it performs the same snapshot-guarded marker-only
  finalization for that task. The next check derives its cursor from the next
  unchecked task. A structural contract change between tasks therefore refuses
  before a second dispatch.

The headless pool and worker contract classify all four post-backend safety
reasons above as terminal safety refusals for that attempt: retain the branch,
attempt result, and diagnostics; do not auto-retry and do not advertise the
item as completed. This is deliberately distinct from backend transport
failure. A human or later recovery workflow may reconcile the retained work.

For valid disabled configs, `work.run_work`, `build_brief`, checkbox ticking,
exit codes, logs, and result bytes follow the existing branch byte-for-byte.

## Engine and CLI integration

- Add `"feasibility"` to the config schema enum, not the default.
- In `machine.advance`, for every destination `implement`, strict config
  inspection and enabled `require(..., dispatch=True)` happen before breaker
  actions, metadata writes, or event appends. This covers normal plan exit,
  review/verify/assure re-entry, and special-stage resume. Convert
  `FeasibilityError` to `GateError`; preserve exit 2 and zero mutation.
- Add read-only `factory plan-check ITEM [--dispatch] [--worktree PATH]
  [--json]`. Text failures go to stderr; JSON always emits the report. Return 0
  for disabled/pass and 2 for fail. Snapshot the whole repo to prove no writes.
- Refactor enabled `work.run_work` so it acquires ownership before reading plan
  inputs, calls `require` inside the claim, builds the brief exclusively from
  the snapshot, revalidates immediately before attempt/backend launch, and
  releases on every refusal. Capture the clean checkout baseline before launch;
  perform complete scope inspection and guarded finalization afterward.
  Replacement before parsing or between validation and prompt construction
  launches nothing and writes no attempt, brief, log, result, plan, or event.
  A post-backend safety refusal preserves already-created diagnostic evidence
  but never ticks a task or logs completion. Disabled mode retains existing
  order and legacy `_tick_plan` behavior.
- `initrepo.validate_tree` validates a present acceptance artifact while
  disabled, and requires it for plan/implement-stage items when enabled. It
  uses the shared validator and reports rather than repairs.

## Producer contract and compactness

When feasibility is enabled, `skills/factory-plan/SKILL.md` takes an explicit
contract-first branch instead of its transcription-only “complete code” rule.
The plan freezes interfaces, decisions, task boundaries, commands, and
acceptance links, but does not prescribe every implementation line. It writes
the sidecar, hashes spec and normalized plan structure, declares the derived
cursor strategy, and requires `plan-check --dispatch` before advance. No length
cap or subjective compactness score exists. Disabled mode retains the old
contract.

`skills/factory-implement/SKILL.md` follows the per-dispatch snapshot rules.
It never invents rework on entry. An interrupted implementation resumes its
existing unchecked tasks; a completed plan is not dispatchable.

The stage that rejects an implementation owns rework preparation, in this
strict order, before `advance ... implement`:

1. Persist its authoritative finding artifact: review uses the blocking
   findings in `reviews/synthesis.md`; verify uses the exact failing
   commands/results/remedies in `verify.md`; assure uses only scenarios with a
   final `regression` verdict in `assurance/verdicts.json` (and the evidence
   paths those entries cite).
2. Append one bounded unchecked implementation task per accepted finding to
   `plan.md`, each naming its source artifact and finding/scenario id. Do not
   append for an interrupted implementation, an assurance ambiguity/blocker,
   or a design-level rejection routed to spec.
3. Refresh `plan_structure_sha256` and `revision`: the reason names the source
   stage and SHA-256 of its authoritative artifact; `changed_sections` names
   only the affected contract surfaces. The cursor remains the derived
   strategy and automatically points to the first appended task.
4. Run `factory plan-check ITEM --dispatch --worktree PATH`; only after it
   passes may the stage log its rejection and advance to implementation.

This ordering is added to `factory-review`, `factory-verify`, and
`factory-assure`, with executable fixtures for each re-entry. It ensures both
the normal dispatcher and a direct headless `factory work` invocation receive
fresh tasks, hashes, revision, and derived cursor. The sidecar does not
authorize design reopening, and the gate does not claim to prove semantic
novelty; prior revisions remain in the authoritative finding artifact and Git
history.

## Task 1 — Schema, graph, and secure snapshot

**Files:** create `schemas/acceptance-plan.schema.json`,
`scripts/factory/lib/feasibility.py`, and `tests/test_feasibility.py`.

- [ ] Write red tests for solo, component-only, joint-staged, impossible-solo,
  corrected 0071/0063, and disconnected test/shared-gate graphs.
- [ ] Prove compact and long complete plans pass; missing fields, stale hashes,
  invalid cursor strategy, empty revision, dangling references, unavailable
  resources, invalid permutations, ambiguous ownership, and bad dependencies
  fail. Prove the reported cursor advances solely from checkbox state.
- [ ] Prove config/artifact/dependency symlink, FIFO/device, source-path escape,
  invalid UTF-8, duplicate keys, oversize input, in-place mutation, cross-file
  replacement, ancestor detachment, and safe not-yet-created-tail behavior.
- [ ] Implement deterministic reports, immutable snapshots, revalidation,
  handoff, checkout baselines, complete scope inspection, and guarded task
  finalization. Run
  `python3 -m unittest tests.test_feasibility -v` and `git diff --check`.
- [ ] Fresh independent Task 1 review; at most three iterations. Commit on PASS
  as `feat: add plan feasibility snapshots`.

## Task 2 — Transition, CLI, and headless enforcement

**Files:** modify `schemas/config.schema.json`,
`scripts/factory/lib/initrepo.py`, `scripts/factory/lib/machine.py`,
`scripts/factory/lib/work.py`, and `scripts/factory/factory.py`; create
`tests/test_plan_feasibility_gate.py`; extend `tests/test_work.py`,
`tests/test_cli.py`, `tests/test_initrepo.py`, and
`tests/test_default_path_invariance.py` where needed.

- [ ] Pin valid-disabled byte compatibility for plan exit, rework/resume,
  default captures, and worker results; pin malformed-config refusal separately.
- [ ] Prove valid enabled entry and zero-mutation refusal for ordinary,
  review/verify/assure, and waiting-human implementation entries; enabled entry
  with no unchecked task refuses.
- [ ] Test plan-check text/JSON, dispatch/worktree, not-a-repo, hostile config,
  and read-only behavior; handoff exposes only current owner scope.
- [ ] Instrument headless ownership, snapshot, baseline, revalidation, attempt,
  brief, backend, result, scope check, guarded finalization, events, and release.
  Test both pre-launch replacement windows; post-backend concurrent plan change;
  committed-then-reverted scope escape; rename/copy old and new paths; dirty
  index/worktree/untracked files; history rewrite; Git inspection failure; and
  release. All safety refusals preserve diagnostics, suppress ticks/completion,
  return exit 2, and are classified non-retryable.
- [ ] Run `python3 -m unittest tests.test_plan_feasibility_gate tests.test_work
  tests.test_cli tests.test_initrepo tests.test_default_path_invariance -v`
  and `git diff --check`.
- [ ] Fresh independent Task 2 review; at most three iterations. Commit on PASS
  as `feat: enforce feasible implementation dispatch`.

## Task 3 — Producer and handoff documentation

**Files:** update `skills/factory-plan/SKILL.md`,
`skills/factory-implement/SKILL.md`, `skills/factory-review/SKILL.md`,
`skills/factory-verify/SKILL.md`, `skills/factory-assure/SKILL.md`, and
`skills/factory-workers/SKILL.md`; update the relevant headless worker
reference; add `skills/capabilities/references/plan-feasibility.md`; extend
`tests/test_plugin_coherence.py`.

- [ ] Document the sidecar, opt-in migration, normalized hash/derived-cursor,
  declared-versus-proven boundary, owner-limited handoff, delivery graphs, and
  contract-first compact-plan branch.
- [ ] Pin plan-check immediately before every held-ownership dispatch, guarded
  marker finalization, non-retryable safety refusal handling, and no
  runtime-proof claim.
- [ ] Use executable coherence fixtures to show compact enabled plans reach
  dispatch; review, verify, and assure each prepare source-linked rework before
  advancing; interrupted work resumes without new tasks; direct work rejects a
  completed plan; and disabled behavior stays unchanged.
- [ ] Run `python3 -m unittest tests.test_plugin_coherence
  tests.test_default_path_invariance -v` and `git diff --check`.
- [ ] Fresh independent Task 3 review; at most three iterations. Commit on PASS
  as `docs: integrate plan feasibility handoff`.

## Final verification and integration

- [ ] Run `python3 -m unittest discover -s tests -v` and `git diff --check`.
- [ ] Fresh whole-feature review executes impossible-solo, component-only,
  joint-staged, per-task mutation, completed/rework/resume, hostile namespace,
  committed-then-reverted/rename/dirty/Git-failure scope cases, concurrent
  post-backend mutation, and non-retryable headless refusal journeys. Maximum
  three iterations.
- [ ] Recheck main/origin and dirty files; merge only this branch, rerun the
  full suite on main, and push only after the merged tree is green.

## Non-goals

- Semantic approach judgement/reviewer selection (0014/0034).
- Heartbeat, retry, lost-reply, partial-process resume, or worker supervision
  (0021/0032/FH-06). Snapshot/cursor refusal does not restart a worker.
- Receipt reuse (FH-03), evidence validity or live test/device/route preflight
  (FH-04), or running declared commands at plan time.
- Subjective quality/compactness scores, arbitrary size caps, code generation,
  auto-merging dependencies, expanding a worker beyond its own participant
  paths, or inferring contracts from prose.
