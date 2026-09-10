---
name: factory-triage
description: Use when a factory item is at stage idea or triage - council decides build/priority/scope and writes the roadmap
---

First read the capabilities skill's `references/host-adapter.md` and resolve the plugin root for this host. Below, `factory` means `python3 "${FACTORY_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

Run this skill in a fresh context using the capabilities skill's `references/host-adapter.md`; nothing from the invoking session may be treated as input. The item id arrives as the skill argument; everything else is read from disk — `factory status --json`, `.factory/items/<id>/...`, and the brain surfaces this skill names below. Your final message is the report the dispatcher acts on: state the outcome (the stage advanced to, or the failure/pause reason, verbatim where a gate refused), name the key artifact paths written, and keep it to a few lines — never paste file contents into it.

## Contract

- **Entry stage:** `idea` (or `triage`, if resuming a run that stopped mid-stage).
- **Artifacts produced:** `items/<id>/triage.md`, updated `item.md` frontmatter (`priority`, and `kind` if corrected), an updated `docs/factory/roadmap.md` line.
- **Exit — build:** `factory advance ITEM spec`. The gate requires `triage.md` to exist and be non-empty, and `priority` to be set in frontmatter; both are produced below before this call.
- **Exit — don't build:** `factory advance ITEM blocked --reason "triage: rejected - <why>"`, then `factory packet ITEM`.

## Steps

1. If the item is at `idea`, advance it first: `factory advance ITEM triage`. (This is a sequential move with no gate — the item must simply be at `idea`.)
2. Run the `council-review` skill in **triage mode** (pass `mode: triage` and the item id as the skill argument): should this be built, at what priority, with what scope cuts. The council also proposes new items from brain surfaces (open questions, decisions, scan findings) during this pass — file each proposal with `factory add "title" --kind ...`.
3. From the council's `reviews/synthesis.md`, write `items/<id>/triage.md`: the build/don't-build decision, the chosen priority number, any scope cuts, and confirmation of the item's `kind`.
4. Set priority: edit `item.md` frontmatter to add or update `priority: N` (integer; lower runs first, matching roadmap order).
5. If the council disagrees with the item's `kind` (`ui`/`backend`/`mixed`), fix it directly in `item.md` frontmatter — `kind` is a plain frontmatter field, not CLI-settable.
6. **Set the materiality tier.** Decide the item's tier from its scope — `epic` (a material feature or UI-heavy initiative that warrants the focus group and full review), `feature` (a normal change: full review, standard research), or `bug` (a defect fix: light correctness review, no market research; usually filed via `/factory:bug` already carrying `tier: bug`). Set it with `factory tier ITEM <epic|feature|bug>`. The council's scope read informs this; when a human is present and the call is close, ask. Tier is a materiality axis, **orthogonal to `kind`** — a `backend` epic and a `ui` feature are both normal. Default when genuinely unsure: `feature`.
7. Update `docs/factory/roadmap.md`: one line per item, in priority order, following the file's existing format (`- [priority] <item-id> <title> (stage)`).
8. File bids for any durable learning worth remembering past this item (market read, scope rationale, a newly confirmed constraint) via the `council-judgement` skill. Triage findings about this item alone don't need a bid — only findings that should outlive it.
9. Exit per the Contract above: `spec` if building, `blocked` + packet if not.

## Lost-reply reconciliation

Read the capabilities skill's
`references/disk-first-reconciliation.md`. Run `factory reconcile begin`
before dispatching this child, treating the council invocation as
`triage:council-synthesis`, with exact input
`.factory/items/ITEM/reviews/seed-context.md`, exact evidence
`.factory/items/ITEM/reviews/synthesis.md`, and no `--worktree` because the
council is repository-only. Use that same exact input/evidence binding for
discovery and inspection; any future checkout-bound child must use the same
canonical `--worktree CHECKOUT` at begin, discovery, and inspection.

After dispatch, perform exactly one host-native wait, capped at 60 seconds. On
an unanswered wait, or a `still running` re-entry, use the host adapter to
establish that exact child's writer state as `active` or `terminal`, then run
`factory reconcile inspect` before any failure accounting, retry, or
replacement. If state cannot be established, stop. An active writer returns
`still running` and causes no second wait, failure count, retry, or replacement.

Adopt a terminal complete current-attempt synthesis, then continue the existing
triage judgement and finalization; transport completion is not a build verdict.
Before writing triage, editing item metadata or roadmap, advancing, creating a
packet, or filing bids, re-read the current item stage and complete current
event log and perform only the normal side effects still missing. If the
transition already landed, adopt it; retain `triage:post-transition-learning`
as a named missing obligation and file only learnings not already recorded.
This recovery does not cover 0032's pool exhaustion, `no-synthesis` policy,
whole-fan-out coordination, or arbitrary prior council runs.
