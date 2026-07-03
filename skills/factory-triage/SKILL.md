---
name: factory-triage
description: Use when a factory item is at stage idea or triage - council decides build/priority/scope and writes the roadmap
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

## Contract

- **Entry stage:** `idea` (or `triage`, if resuming a run that stopped mid-stage).
- **Artifacts produced:** `items/<id>/triage.md`, updated `item.md` frontmatter (`priority`, and `kind` if corrected), an updated `docs/factory/roadmap.md` line.
- **Exit — build:** `factory advance ITEM spec`. The gate requires `triage.md` to exist and be non-empty, and `priority` to be set in frontmatter; both are produced below before this call.
- **Exit — don't build:** `factory advance ITEM blocked --reason "triage: rejected - <why>"`, then `factory packet ITEM`.

## Steps

1. If the item is at `idea`, advance it first: `factory advance ITEM triage`. (This is a sequential move with no gate — the item must simply be at `idea`.)
2. Run the `council-review` skill in **triage mode**: should this be built, at what priority, with what scope cuts. The council also proposes new items from brain surfaces (open questions, decisions, scan findings) during this pass — file each proposal with `factory add "title" --kind ...`.
3. From the council's `reviews/synthesis.md`, write `items/<id>/triage.md`: the build/don't-build decision, the chosen priority number, any scope cuts, and confirmation of the item's `kind`.
4. Set priority: edit `item.md` frontmatter to add or update `priority: N` (integer; lower runs first, matching roadmap order).
5. If the council disagrees with the item's `kind` (`ui`/`backend`/`mixed`), fix it directly in `item.md` frontmatter — `kind` is a plain frontmatter field, not CLI-settable.
6. Update `docs/factory/roadmap.md`: one line per item, in priority order, following the file's existing format (`- [priority] <item-id> <title> (stage)`).
7. File bids for any durable learning worth remembering past this item (market read, scope rationale, a newly confirmed constraint) via the `council-judgement` skill. Triage findings about this item alone don't need a bid — only findings that should outlive it.
8. Exit per the Contract above: `spec` if building, `blocked` + packet if not.
