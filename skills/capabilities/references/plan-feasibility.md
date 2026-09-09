# Plan feasibility and resumable implementation

Use this reference only when `.factory/config.json` contains `"feasibility"`
in its `gates` array. The gate is opt-in and is not part of the default
configuration. A valid configuration without it keeps the legacy plan,
implementation, checkbox, and rework workflows unchanged.

## What the gate proves

The gate proves that the implementation declaration is complete and
internally consistent:

- the exact spec and normalized plan structure are bound by SHA-256;
- the current item and any joint participants have non-overlapping owned path
  prefixes;
- every required path, interface, runtime, device, or route has a provider;
- delivered dependencies are done and joint dependencies have an explicit
  participant, merge order, and shared integrated gate;
- each criterion's named tests cover all of its required resources; and
- the resume cursor is mechanically the first unchecked plan task.

A passing declaration is not runtime proof. It does not prove that a declared
command passes, a runtime/device exists, a
route works, evidence is current, or an implementation approach is sound.
Those claims remain with implementation, review, verification, assurance, and
future evidence-preflight work. Never describe `plan-check` as runtime proof.

## The closed sidecar

The authoritative declaration is
`.factory/items/<id>/acceptance.json`. Its exact closed shape is
`schemas/acceptance-plan.schema.json`; do not add convenience keys. The main
surfaces are:

- `spec_sha256`: SHA-256 of exact `spec.md` bytes.
- `plan_structure_sha256`: SHA-256 of exact `plan.md` bytes after changing only
  checkbox markers `[x]` and `[X]` to `[ ]`. Progress ticks therefore keep the
  contract valid; prose, whitespace, task order, and appended tasks do not.
- `revision`: a non-empty reason and the contract sections changed.
- `resume_cursor.strategy`: exactly `first-unchecked-task`; never store the
  cursor text in the sidecar.
- `participants` and `owned_paths`: ownership declarations, not permission to
  modify another participant's paths.
- `dependencies`, `resources`, `interfaces`, `criteria`, and `tests`: the
  provider and coverage graph.
- `delivery`: `solo`, `component-only`, or `joint-staged`, with exact
  participants, merge order, and shared gates.

Use the plugin's `feasibility.plan_structure_sha256` implementation when
producing the normalized hash; do not approximate it with a Markdown parser.
Run `factory plan-check ITEM --json` after writing both artifacts. It is the
repository-only authority and writes nothing. A compact complete plan is
valid; there is no prose score, generated-code quota, or arbitrary task-count
minimum.

## Dispatch and completion

While holding the item's implementation ownership claim, run immediately
before the initial in-process implementer dispatch for a selected task:

```text
factory plan-dispatch ITEM --task 1 --json
```

The result contains an owner-bound `ticket_id`, the selected task, and an
immutable owner-limited `handoff`. Use that handoff as the worker's only
plan/spec/acceptance input. Wrap it in execution instructions to implement,
test, commit on `factory/<id>`, and stay inside `owned_paths`; do not reread
live plan inputs to rebuild the prompt. Never expose the ownership token in a
prompt or artifact. Retain the original ticket through review and the single
fix attempt for that task; a replacement ticket would reset the Git scope
baseline and is forbidden.

After the implementation and its fresh review pass, run the task tests. Before
finalizing the last unchecked marker, run the full item/project suite while the
plan is still resumable. Then write the normalized
successful `worker/result.json` described by `schemas/result.schema.json`,
including `dispatch_ticket` equal to this ticket, the actual backend/branch,
commits, changed files, and test/review summary. Then run:

```text
factory plan-finalize ITEM --ticket TICKET_ID --json
```

Finalization independently checks the complete Git-observable path set,
requires a clean checkout, binds the successful result to the dispatch, and
atomically ticks only the selected captured marker. It emits
`implement.completed` only when no unchecked task remains. Do not edit an
enabled checkbox directly and do not separately log completion.

`factory work` performs dispatch, result binding, scope inspection, and
finalization itself. Exit 2 with `scope_inspection_failed`, `history_rewrite`,
`dirty_checkout`, `scope_violation`, or `concurrent_plan_change` is a terminal
safety refusal for that attempt: preserve the branch/result diagnostics, do
not retry automatically, and never advertise completion. The declaration is
not active write sandboxing; restored transient uncommitted writes are outside
the Git-observable guarantee.

An interrupted implementation resumes the existing unchecked task. It does
not create rework tasks. A completed plan is not dispatchable.

## Source-linked rework

Only the stage that rejects completed implementation prepares rework. Persist
its authoritative source first:

- review: `reviews/synthesis.md`, with stable blocking finding ids;
- verify: `verify.md`, with ids and exact failing commands/results/remedies;
- assure: `assurance/verdicts.json`, using only final `fail` scenarios whose
  attribution is `regression`.

Write proposal files without changing canonical `plan.md` or
`acceptance.json`. The proposed plan must preserve the complete canonical plan
as an exact prefix and append exactly one unchecked task per accepted finding.
Every task names the source artifact and exactly one finding/scenario id. The
proposed acceptance sidecar refreshes `plan_structure_sha256`; its revision
reason names the rejecting stage and exact source SHA-256, and
`changed_sections` names the affected contract surfaces.

Then invoke one atomic adapter:

```text
factory plan-rework ITEM \
  --source review|verify|assure \
  --source-file .factory/items/ITEM/PATH \
  --finding FINDING_ID [--finding FINDING_ID ...] \
  --plan-proposal PROPOSAL_PLAN \
  --acceptance-proposal PROPOSAL_ACCEPTANCE \
  --json
```

It validates the prospective graph and commits both canonical replacements,
the rejection evidence event, implementation entry, and any breaker event as
one recoverable operation. Repeating the same source digest and ordered ids
adopts the same request; different proposal bytes conflict. Never use this for
an interrupted worker, assurance ambiguity/blocker, pre-existing assurance
failure, or design-level rejection routed to spec.

A `plan-rework` refusal is not automatically a rework-cap refusal. Malformed
proposals, stale hashes, invalid findings, and concurrent changes remain in the
rejecting stage for correction. Take a cap-specific blocked/redesign route only
when the engine's refusal explicitly names that cap.
