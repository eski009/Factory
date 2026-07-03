---
name: factory-ship
description: Use when a factory item is at stage ship - merges per policy and closes the loop on the brain
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

## Contract

- **Entry stage:** `ship`. The gate into `ship` already required `verify.green` to be logged.
- **Artifacts produced:** the merge or PR itself, a `ship.merged` (or `ship.failed`) event, an updated `docs/factory/roadmap.md` line, an appended line in `docs/factory/brain/decisions.md`, `items/<id>/verify.md`'s companion shipped packet.
- **Exit — success:** `factory log ITEM ship.merged --data '{"mode": "<auto|queue|tiered>", "ref": "<sha-or-pr>"}'` then `factory advance ITEM done`. The `done` gate checks only for `ship.merged`.
- **Exit — merge or post-merge failure:** revert the merge, `factory log ITEM ship.failed --data '{"mode": "<auto|queue|tiered>", "reason": "<what failed>"}'`, no advance, report to the dispatcher.

## Merge policy

Read `merge` from `.factory/config.json` (`auto`, `queue`, or `tiered`):

- **`auto`:** merge `factory/<item-id>` into the repo's default branch, run the merged result's full suite, and only once green delete the branch. `ref` in the log call is the merge commit SHA.
- **`queue`:** push `factory/<item-id>` and open a PR (`gh pr create`) targeting the default branch; leave the branch in place — nothing is merged here. `ref` is the PR URL or number.
- **`tiered`:** decide per item — `auto` when `kind` is `backend` **and** the change itself is low severity (docs, straightforward fixes, refactors with no behavior change); `queue` for everything else (any `ui`/`mixed` item, or a `backend` item with real behavior change). This is a judgment call on the diff, not a stored field — read the diff before deciding, don't default to auto to save a step.

## Steps

1. Read `.factory/config.json`, take the branch above matching `merge`.
2. Execute that branch. For `auto`/tiered-auto: merge, run the full suite on the merged tree, delete `factory/<item-id>` only after the suite is confirmed green (per `superpowers:verification-before-completion` — don't delete on an assumed-clean merge). For `queue`/tiered-queue: push and open the PR; the branch stays.
3. Log `ship.merged` per the Contract, immediately followed by `factory advance ITEM done`.
4. Update `docs/factory/roadmap.md`: move this item's line to reflect stage `done` (the file is one line per item with `(stage)` — update that parenthetical; there is no separate "Shipped" section to move it into unless the file already has one).
5. Append one line to `docs/factory/brain/decisions.md` recording what shipped and how (mode, ref, item id). This is the one ship-log exception to the council-judgement bid firewall: a factual record of what happened, not a judgement — it still doesn't authorize any other brain edit, and durable *judgements* about the item still need their own bid/judge cycle.
6. `factory packet ITEM` and hand its path back as the shipped report.

## On failure

If the merge conflicts, or the merged-result suite fails: revert the merge (leave the branch and the pre-merge default branch state intact), log `ship.failed` with the reason, do not advance, and report to the dispatcher — do not attempt a second merge strategy unprompted.
