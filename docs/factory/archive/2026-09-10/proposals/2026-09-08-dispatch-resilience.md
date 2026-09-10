# Council dispatch resilience implementation plan

> **Execution:** direct engineering only; do not invoke the Factory harness.
> Work in the bounded tasks below. Each task needs focused tests and a fresh
> independent review; the completed branch needs one final review before merge.

## Goal and delivery boundary

Make item-scoped council fan-out a supervised engine operation. Admission
failure, timeout/crash, or missing synthesis must durably return a resumable
outcome before a review verdict can be recorded. A fresh process resumes the
same run, adopts an already completed run after a lost CLI response, and never
redispatches an engine-committed seat.

This delivers item 0032 for `triage` and `review` councils. It does not infer
that an unacknowledged child secretly completed work (0021). It also does not
claim to fix journey-assurance walks: those have mutable screenshot/browser/
base-attribution evidence and require a separate bundled-evidence design. The
0027 incident remains motivating evidence, not a delivered assurance claim.
Batch roadmap triage and initiation research retain their current transport
and are explicitly outside the resilience guarantee because they have no item
stage identity. Tests must prove the shared skill selects the correct path.

Opaque native host fan-out is never called resilient. Item councils use the
engine-supervised subprocess transport or stop before launching with
`unsupported_transport`.

## Safety invariants

- One logical run spans retries. Matching running work returns `wait`, matching
  failed/incomplete work resumes, and matching completed work is adopted with
  zero backend calls.
- Starts are serialized at item plus council-mode scope before run discovery.
  Concurrent starts with the same inputs converge on one run. Changed-input
  work cannot execute while an older run owns the same canonical outputs.
- One controller generation owns a run. Every launch and publication checks
  that generation. A second controller never launches overlapping work.
- Controller expiry alone does not authorize takeover. Each child is owned by
  a separate bounded supervisor process. Takeover is allowed only after a
  valid terminal supervisor receipt proves its process group was reaped. A
  missing/corrupt receipt is a safe stop, not permission to retry.
- The supervisor runs inside a backend containment adapter whose contract is
  stronger than a POSIX process group: descendants cannot escape the boundary,
  and `terminate_all` plus `prove_empty` covers children that call `setsid`,
  double-fork, close inherited pipes or outlive the direct CLI. Linux cgroup v2
  is the first production adapter; a deterministic fake is used in tests. A
  host without a proven adapter returns `unsupported_transport` before launch.
  The supervisor survives controller EOF, enforces the deadline, terminates
  the containment boundary, proves it empty, fsyncs exact stdout/stderr, and
  only then publishes terminal state. If the supervisor itself dies, the run
  cannot automatically take over.
- Only a terminal attempt plus a validated, immutable run result counts as a
  completed job. Partial output and arbitrary files never do.
- Engine lifecycle records are authoritative. Generic `factory log` cannot
  manufacture dispatch lifecycle events or `review.approved/rejected` for a
  supervised council.
- Input identity binds mode, item stage entry, reviewed checkout HEAD/state,
  seed bytes, role-memory bytes, protocol/depth, required seats, job policy,
  backend/model and output targets. Identity change requires a new run after
  the old scope owner is terminal.
- Council completion alone is not a substantive pass. Existing high-severity
  rules, two-round maximum, review rework cap, machine gates and human-only
  decisions remain authoritative.

## Durable records and publication

```text
.factory/items/<item>/dispatch-runs/
  scope/<mode>/claims/<generation>.json
  indexes/<mode>/<input-fingerprint>.json
  canonical/reviews-synthesis/claims/<generation>.json
  verdicts/<stage-entry>.json
  <run-id>/
    manifest.json
    controllers/<generation>.json
    jobs/<job-id>/
      definition.json
      attempts/<generation>/
        supervisor.json
        stdout.bin
        stderr.bin
        terminal.json
        outcome.json
      result.json
      output.bin
    round-2-selection.json
    completion.json
```

All ids are lowercase 32-hex. JSON has a closed schema and canonical UTF-8
encoding with one trailing newline. Immutable records use: descriptor-anchored
no-follow traversal; fully written and fsynced mode-0600 temporary file;
exclusive hard-link publication; destination-directory fsync as commit point;
temporary-alias cleanup; final byte/inode and ancestor revalidation. Mutable
canonical outputs use a separately written, fsynced temporary copy plus atomic
replace and directory fsync; they never hard-link ledger bytes.

Publication order is explicit:

1. Publish a scope claim generation, then an immutable manifest, then the
   fingerprint index. Discovery of an index without its valid manifest is
   contradictory. An unindexed valid manifest is a pre-index crash tail and is
   recoverable only by the same held scope generation; otherwise stop.
2. Before process creation publish `supervisor.json` with run/job/controller/
   attempt generations, argv hash, policy, deadline and supervisor identity.
3. The surviving supervisor captures bytes. After the process group is reaped,
   publish `terminal.json` with typed status (`exited`, `timed_out`,
   `launch_failed`, `admission_failed`, `supervisor_failed`), exit code and
   exact stream hashes/lengths. `admission_failed` is published even though no
   model process started.
4. The current controller validates supervisor and terminal identity. On
   success it first publishes immutable `output.bin`, then `result.json`
   binding its hash and terminal receipt, and only then publishes the success
   `outcome.json`. A crash before the outcome is recovered by validating the
   terminal/output/result chain and publishing the same outcome without a new
   backend call. Failure publishes only its typed `outcome.json`; failure
   outcomes remain durable and resumable and are never job results.
5. Round 2 selection is published once after validated synthesis 1. Its closed
   seat set and synthesis-1 hash cannot be recalculated on resume.
6. After every required seat, mandatory review walk, synthesis 1 and final
   synthesis is a valid result, publish the next path-scoped canonical-owner
   claim binding run id, stage entry and final hash; atomically copy the final
   synthesis into `reviews/synthesis.md`, verify the copy, then publish
   `completion.json`. A crash after the owner/copy but before completion is a
   recoverable tail only when owner, bytes and final result agree. Historical
   completions validate against their immutable results, not the current
   canonical file. Only the latest valid owner may be adopted or issue a
   verdict. Returning to an older input fingerprint creates a new run unless
   its completion is still the current canonical owner.
7. Verdict publication holds the item/mode scope generation. It exclusively
   publishes `verdicts/<stage-entry>.json` binding run, completion, canonical
   owner, verdict and an event id, then appends the existing review event with
   those ids. Retry repairs the ordinary receipt-before-event crash tail by
   appending the one missing matching event; matching event/receipt is adopted;
   duplicate or conflicting receipts/events refuse. The engine serializes this
   with stage transition calls, so a lost CLI response cannot consume a second
   rejection or race an advance.

Missing records are classified by boundary: no supervisor after a committed
controller claim is `resumable/admission_failed`; supervisor without terminal
before deadline is `running/wait`; supervisor without terminal after deadline
is `contradictory/supervisor_unproven`; terminal without outcome is a
recoverable controller tail; outcome failure is resumable; valid terminal,
output and result without a success outcome is a recoverable controller tail,
while a success outcome without that chain is contradictory; all council seats complete
without the next synthesis definition/result is
`resumable/missing_synthesis`. Corruption of any committed record is always
`contradictory/stop`.

## Council job graph

The engine owns a fixed dependency graph, not a general scheduler:

1. Round 1 independent seat jobs receive only seed bytes plus their own role
   memory. Full review uses six seats; light review uses its existing inward
   subset.
2. A supervised `synthesis-1` orchestrator job receives only committed Round 1
   outputs plus reputation order and must return closed structured JSON:
   Markdown synthesis plus the selected Round 2 seat ids.
3. The engine validates and freezes that selection. Round 2 jobs receive only
   committed `synthesis-1` Markdown plus their own delta-only instruction.
4. In review mode, a supervised most-capable `review-walk` job receives the
   spec/acceptance criteria, diff identity and repository read/execute policy;
   it returns the required entry-to-output trace. It is not a council seat.
5. A supervised `final-synthesis` orchestrator job receives synthesis 1,
   committed Round 2 deltas and the review walk (review mode), and returns the
   severity-tagged final Markdown. The orchestrator job owns deduplication,
   conflict resolution and selection; it is isolated from seat role memory and
   is never counted as another council vote.

The move from inline invoking-session synthesis to a supervised orchestrator
process is intentional and must be reflected consistently in both council and
review skill contracts.

## Dispatch-specific backend policy

Do not reuse the implementation-worker parser or its 2,000-character summary.
Reuse only low-level argv construction/capture where safe.

- Persist full raw stdout/stderr and losslessly extract the complete report.
- Council seats receive a read-only filesystem/shell policy and their explicit
  network setting; they cannot write the repository. Synthesis jobs receive
  only materialized input files in an isolated read-only job directory.
- The review walk is read-only in the repository but may run non-mutating
  commands allowed by its policy. Unsupported browser or other required tools
  refuse before admission.
- Each concurrent job gets a distinct runtime/config home. Never share the
  item-scoped implementation worker home.
- Backend success requires exit zero, a valid provider terminal event, nonempty
  complete output and no provider-reported failure. Model prose cannot turn a
  failed process into success.
- Automatic redispatch after any launched process is enabled only when the
  manifest names a supported containment adapter and its terminal receipt
  proves that boundary empty. Admission failure before launch is resumable on
  every platform. Missing/corrupt containment evidence is a safe stop.

## Task 1 — Run ledger, scope serialization and deterministic resume

**Files:** create `scripts/factory/lib/dispatch_runs.py`,
`schemas/dispatch-run.schema.json`, and `tests/test_dispatch_runs.py`.

- [ ] Implement descriptor-anchored durable publication and strict readers for
  scope claims, index, manifest, controller generations, job definitions,
  attempts, outcomes, results, selection and completion.
- [ ] Implement `start_run`, `inspect_run`, `resume_run`, `commit_outcome`,
  `commit_result`, `select_round_two`, and `complete_run` with the state and
  publication boundaries above.
- [ ] Serialize concurrent starts at item/mode scope. Adopt matching completion,
  wait on matching live work, resume matching terminal work, refuse ambiguous
  duplicates, and keep changed-input runs from sharing canonical targets.
- [ ] Validate item stage entry, all input/output containment and hashes, job
  generation, and canonical synthesis agreement. Return typed state only;
  inspection never repairs.
- [ ] Test every publication boundary, concurrent starts/resumes, lost complete
  response, stale controller with and without proven terminal jobs, late old-
  generation publication, completed-seat reuse, immutable selection, changed
  inputs, triage followed by review, multiple review runs, canonical-owner
  transfer, symlinks/replacements and corrupt committed state.

Run `python3 -m unittest tests.test_dispatch_runs -v`.

## Task 2 — Surviving supervisor and controlled transport

**Files:** create `scripts/factory/lib/dispatch_supervisor.py`,
`scripts/factory/lib/dispatch_transport.py`, `tests/test_dispatch_supervisor.py`
and `tests/test_dispatch_transport.py`; modify `worker_attempts.py` only for a
reviewed reusable low-level primitive.

- [ ] Define a containment-adapter interface and implement Linux cgroup v2 plus
  a deterministic fake. Preflight availability before admission; never treat a
  POSIX process group alone as full containment.
- [ ] Launch a separate supervisor inside that boundary. It survives controller
  EOF, enforces timeout, proves all contained processes gone, captures exact
  bytes and publishes a typed terminal receipt before exiting.
- [ ] Prove controller death, suspended controller, child timeout, descendant
  holding pipes, an escaping `setsid()` child, launch/admission failure,
  supervisor death, unsupported platform, and no terminal publication before
  the containment boundary is proven empty.
- [ ] Implement lossless Codex/Claude result validation, per-job homes and the
  read-only seat/synthesis/walk policies. Unsupported capabilities refuse
  before launch.
- [ ] Run bounded jobs from the fixed council graph and commit only current-
  generation results. Resume makes zero calls for committed jobs and waits or
  stops when prior execution is not proven terminal.
- [ ] Test reports over 2,000 characters, malformed provider streams, forbidden
  policy requests, concurrent isolation, partial Round 1 failure, all seats
  done/missing synthesis, selected-only Round 2 and walk reuse.

Run:

```bash
python3 -m unittest tests.test_dispatch_supervisor \
  tests.test_dispatch_transport tests.test_worker_attempts -v
```

## Task 3 — CLI, validation and verdict firewall

**Files:** modify `scripts/factory/factory.py`, `scripts/factory/lib/initrepo.py`,
`scripts/factory/lib/logs.py`, and the review gate in
`scripts/factory/lib/machine.py`; create `tests/test_cli_dispatch_runs.py` and
extend log/machine/status validation tests.

- [ ] Add `factory dispatch-run start|execute|resume|status` with JSON output
  and stable exits: `0` complete/adopted transition, `2` wait/refusal,
  `3` resumable transport state, `1` invalid/corrupt/usage failure.
- [ ] Mirror lifecycle events only inside owning engine operations after the
  run record commits. Reserve `dispatch.run.*`, `dispatch.job.*`,
  `dispatch.synthesis.*`, `review.approved` and `review.rejected` from generic
  logging for item councils.
- [ ] Add `factory dispatch-run verdict ITEM RUN_ID <approved|rejected>`; it
  validates current-stage identity, completion, current canonical ownership
  and final severity result, then uses one immutable verdict/event identity.
  Matching retries adopt or repair the single append; concurrent/conflicting
  calls refuse and can never consume an extra rejection.
- [ ] Make `status --json` expose run id/state/reason without treating it as a
  stage verdict. Validate historical runs against their immutable results and
  require canonical agreement only for the latest path owner.
- [ ] Prove premature/stale verdict refusal, concurrent verdict calls, crashes
  between verdict receipt/event/response, repeated resumable outcomes do not
  consume the dispatcher fail-twice counter, lost completion response adoption,
  historical completion validation, and unchanged existing gate/rework behavior
  after a valid verdict.

Run:

```bash
python3 -m unittest tests.test_cli_dispatch_runs tests.test_logs \
  tests.test_machine tests.test_assure_verbs -v
```

## Task 4 — Item council and review integration

**Files:** modify `skills/council-review/SKILL.md`,
`skills/factory-review/SKILL.md`, `skills/factory-triage/SKILL.md`,
`skills/factory-dispatch/SKILL.md`,
`skills/capabilities/references/workflow-fanout.md`; add
`skills/capabilities/references/dispatch-resume.md`; extend plugin-coherence and
default-path tests.

- [ ] Item triage/review must discover or resume the matching supervised run
  before starting. They consume only engine-committed outputs and use the
  verdict verb after completion.
- [ ] Exit `2` waits or reports the exact refusal. Exit `3` keeps the item at
  the same stage, reports the run id/resume command, emits no review verdict,
  and consumes no rework/failure retry.
- [ ] Preserve independent Round 1 inputs, reputation attention, light/full
  seat sets, selected delta-only Round 2, two-round stop, severity rules,
  durable-bid routing and the mandatory review walk.
- [ ] For batch roadmap triage and initiation research, explicitly retain the
  existing fan-out path and label it outside the 0032 resilience guarantee.
  Tests prove the item/non-item routing and prevent silent fallback for items.
- [ ] Remove claims that native/workflow item fan-out is an equivalent degraded
  path. Document backend/capability preflight and safe unsupported transport.

Run:

```bash
python3 -m unittest tests.test_plugin_coherence \
  tests.test_default_path_invariance tests.test_round_scope -v
python3 -m unittest discover -s tests -v
git diff --check
```

## Out of scope

- Lost unacknowledged child work (0021).
- Journey assurance and base-attribution evidence resumption; file separately
  before claiming the 0027 case is fixed.
- Degraded councils with fewer seats (bid-0147), global host pool accounting,
  cost breakers, adaptive seat counts or a general workflow scheduler.
- Migrating legacy loose artifacts into resumable receipts.
