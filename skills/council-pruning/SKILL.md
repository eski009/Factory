---
name: council-pruning
description: Use when memory-health recommends pruning - runs the provenance-preserving prune per role
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

## Entry

Only run this after `council-memory-health` returned a `prune` recommendation
and handed you its `reasons`. Don't self-invoke on a hunch.

## Which roles

Parse the role name out of each per-role reason (the ones shaped like
`"<role>: N lines exceeds ..."` or `"<role>: N duplicate claims exceeds
..."`). A reason like `"N unjudged bids exceeds ..."` names no role — it's a
ledger-wide signal, not something `factory prune` acts on; skip it here (it's
still worth surfacing to the user, but judging bids is the `council-judgement`
skill's job, not this one's). Dedupe the resulting role list before pruning.

## Per role

For each role in that list, in order:

1. `factory prune ROLE` (dry-run — no flag). This reports proposed `kept`
   and `archived` counts without touching any file.
2. Show those counts to the user before applying anything.
3. `factory prune ROLE --apply`. This is the only step that writes: it
   rewrites `docs/factory/council/<role>.md` to the kept lines, and appends
   the archived lines to `.factory/pruning/<role>.md` under a timestamped
   heading.

## Invariant

The prune only ever removes *exact-duplicate* claim lines (`- ...` lines
that repeat verbatim) — free-text prose is never touched, and `kept +
archived` always equals the role file's original line count. Archived lines
live permanently in `.factory/pruning/<role>.md`: never delete that file or
edit out its contents. It's the provenance trail proving what was pruned and
when, and later work (or a human) may need to recover a claim from it.

## Report

Once every targeted role is done, report kept/archived counts per role and
the `.factory/pruning/<role>.md` path each one archived to.
