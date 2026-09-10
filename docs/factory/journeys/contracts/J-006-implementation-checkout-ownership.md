# J-006 — Implementation checkout ownership

_status: draft — drafted at the spec stage of
`0020-concurrent-implementers-violate-the-one-`. The item is tier `bug`, whose
assure profile is `node`; assurance is limited to the changed acquisition,
contention, finalization, and crash-refusal nodes. This contract does not define
cross-item scheduling or an ownership-recovery product._

- **Persona:** The Overnight Operator (`docs/factory/brain/personas.md`) — an
  expert who runs agents unattended and needs the resulting code, commits, and
  review evidence to have one trustworthy producer.
- **Trigger:** Factory is about to dispatch an in-process implementer for an
  item or begin a direct headless `factory work` run against that item's
  registered implementation checkout.
- **Outcome:** exactly one same-item owner is admitted to the mutable checkout
  and evidence window; a distinct contender is refused before mutation, while
  explicitly nested work inherits the admitted owner without self-deadlock.
- **Surface:** CLI + filesystem + Git. No browser surface or viewports. Evidence
  is typed command output, ownership-state snapshots, Git index/tree/commit
  transcripts, and task/worker evidence files from temporary fixture repos.

## Nodes

| node | what the customer knows here | what they expect next |
|---|---|---|
| N1 implementation requested | the item is at `implement`, its `factory/<item-id>` checkout resolves through Git, and no implementer has been admitted yet | Factory decides ownership before any task or worker can mutate checkout or transient evidence |
| **N2 owner acquired — commitment point** | one atomic Factory-owned claim binds the item to its canonical registered checkout and an opaque owner identity | only this owner, or work explicitly inheriting its identity, can enter the mutable window |
| **N3 implementation and review window active — commitment point** | the owner remains exclusive through implementer mutation, commit construction, the associated independent task review, and checkout/task-evidence finalization; a direct `factory work` owner remains exclusive for its whole run | no second same-item actor can change working files, the index, committed paths, commit subject/body, or transient evidence |
| **N4 contender refused** | a distinct owner receives a stable actionable contention diagnostic before its backend/callback or worker artifact writers run | the admitted owner's state is byte-for-byte unchanged and the contender may retry only after clean release |
| **N5 owner finalized and released** | success or a handled worker failure/timeout has written its terminal evidence before the outer owner releases the claim | a later owner can acquire; nested release never clears the outer claim |
| **N6 interrupted owner remains fail-closed** | a process crash, malformed owner record, path-identity mismatch, or failed release does not look free and is never expired or taken over automatically | the next attempt refuses specifically, preserves existing code/evidence, and leaves recovery to a separately owned operator decision |

## Trust and reassurance requirements

The commitment is N2 through N5: during that interval, every mutable artifact
must have one admitted producer.

- Acquisition is atomic Factory-owned state. A prose instruction, filename
  convention, process-local mutex, or generic `factory log` event has no
  authority to acquire, inherit, release, or bypass it.
- The domain is item-scoped and binds the canonical physical path reported for
  the registered `factory/<item-id>` worktree. Symlink/relative aliases resolve
  to the same identity; an alternate or changed path cannot create a second
  domain while ownership exists.
- Inheritance requires the current opaque owner identity explicitly propagated
  by Factory. Item id, PID, elapsed time, or an asserted log payload alone is
  not ownership. Nested completion cannot release the outer owner.
- Contention is visible and conservative: name the item and checkout, say that
  another implementation owner exists, and state that automatic takeover is
  unsupported. Do not leak the owner's credential.
- A clean success, handled failure, or timeout finalizes its evidence before
  release. A crash or release failure may leave ownership behind; no age/PID
  heuristic declares it stale, no automatic deletion occurs, and no new owner
  is admitted.
- Failures never claim that ownership was cleared when the atomic state could
  not be verified or released. Completed code/evidence is retained rather than
  rolled back by this boundary.

## Deterministic oracles

| scenario | oracle |
|---|---|
| atomic race | two separately identified contenders wait on a barrier and attempt the same free item domain; exactly one acquires, one is refused, and no observation admits two owners |
| in-process lifetime | the first owner remains held before implementer callback entry, throughout commit construction, across reviewer execution, and until checkout/task-evidence finalization completes |
| direct-work lifetime | the claim exists before `worker/brief.md` or a backend runs and remains through `worker.log`, `result.json`, spend, plan ticking, and the terminal implement event |
| inherited nesting | a nested acquisition carrying the exact owner identity succeeds without waiting; its release leaves a distinct contender refused until the outermost release |
| contaminating contender | the refused callback/backend is instrumented to modify a working file, stage an extra path, replace subject/body input, and overwrite transient evidence; it is never invoked, and all first-owner snapshots remain unchanged |
| path aliases | relative, absolute, and symlink spellings of the registered checkout map to the same domain; an explicit path not registered on `factory/<item-id>` refuses before worker artifacts |
| handled failure | backend failure and timeout each produce their existing terminal result/log/spend evidence while held, then release so one later acquisition succeeds |
| crash/stale state | simulated abrupt termination leaves owner state; repeated attempts after arbitrary elapsed time and dead-PID fixtures refuse identically without mutation or takeover |
| malformed/release failure | unreadable, malformed, wrong-type, path-mismatched, or unverified owner state fails closed; a non-owner release changes no bytes; failed owner release never presents the domain as free |
| cross-item invariance | simultaneous claims for two different item ids and registered worktrees both succeed; no cross-item pool or scheduling policy is introduced |

## Required scenarios

The authoritative list is
`.factory/items/0020-concurrent-implementers-violate-the-one-/assurance/impact.json`
(J-006 S1–S9).

## Required evidence per surface

- **cli/api:** typed command/API transcripts with exact exit status and
  stdout/stderr for acquisition, inherited acquisition, contention, non-owner
  release, handled failure, timeout, and crash/stale retry.
- **filesystem/Git:** before/after hashes or byte snapshots for the ownership
  record, working files, task/worker evidence, pending commit subject/body
  input, `git diff --cached`, `git status --porcelain`, and `git show` of the
  first owner's committed path set and full commit message.
- **browser:** not applicable; no screenshot, DOM/a11y, console, network, or
  viewport evidence is required.

## Run & fixtures

- Engine command:
  `python3 scripts/factory/factory.py --repo <fixture-repo> ...`.
- Authoritative suite: `python3 -m unittest discover -s tests -v`.
- Create temporary Git repositories with two items and registered
  `factory/<item-id>` worktrees through production helpers/commands. Do not
  mutate this repository's checkout to stage the overlap.
- Use deterministic barriers/hooks, never sleeps, to stop owner A inside the
  mutable window while owner B attempts entry. B's payload must be executable
  if invoked so a missing guard would visibly contaminate every named surface.
- Exercise the production `run_work`/CLI route with the stub backend and the
  production in-process claim used by `factory-implement`; test-only helpers may
  coordinate barriers but may not replace acquisition or refusal.
- Credentials and network access: none.

## Empty / error / interruption / recovery

- **Empty:** a free, valid item domain admits one owner atomically; different
  item domains remain independent.
- **Error:** contention and invalid/malformed ownership state refuse before
  the contender's mutable payload. An invalid explicit checkout identity also
  refuses before worker artifacts.
- **Interruption:** abrupt termination can leave ownership state. Its age or
  recorded PID never authorizes takeover; the next attempt fails closed and
  preserves the first owner's Git and evidence state.
- **Recovery:** clean handled outcomes release after finalization and permit a
  later owner. Automatic stale-owner recovery, forced unlock, lease expiry, and
  crash cleanup are explicitly outside this contract.

## Polish battery (AI judgement, seeded on every touched node)

Ask at N1, N2, N3, N4, N5, and N6:

- **density:** what on this screen is not needed for what the customer is doing
  at this node?
- **craft:** what would a first-time customer visually notice as unfinished?
- **consistency:** does this screen read as the same product as the previous
  node (type, color, spacing rhythm — against `design-system.md` and
  `brain/design-principles.md` where present)? For this CLI/filesystem journey,
  apply the same question to terminology, field order, and refusal shape.
- **trust:** would a first-time customer trust this screen with their data or
  money — specifically, trust that their code, commit, and evidence have one
  producer?

Contract authors may add questions, never remove them.
