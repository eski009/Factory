---
name: factory-implement
description: Use when a factory item is at stage implement - executes the plan task-by-task in an isolated branch
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

## Contract

- **Entry stage:** `implement`. The gate into `implement` already required `plan.md` with at least one `- [ ]` task.
- **Artifacts produced:** branch `factory/<item-id>`, checkboxes ticked in `plan.md` as tasks land, the implementation commits themselves.
- **Exit — success:** `factory log ITEM implement.completed --data '{"tasks": N, "tests": "<summary>"}'` then `factory advance ITEM review`. The `review` gate mechanically checks for both: the branch ref `refs/heads/factory/<item-id>` and the `implement.completed` event — this is why the branch name is exact and the log call precedes the advance.
- **Exit — task failure:** leave the branch intact (never delete work), `factory log ITEM implement.failed --data '{"task": "<name>", "attempts": 2}'`, and report the failure to the dispatcher. Do not call `advance` — the dispatcher owns the blocked transition after repeated failures.

## Steps

1. **Isolated branch.** Use `superpowers:using-git-worktrees` to get an isolated workspace when its native-tool path is available; otherwise create a plain branch. Either way the branch must be named exactly `factory/<item-id>`, cut from the repo's default branch — `using-git-worktrees`' `git worktree add -b` (or a plain `git branch` + checkout) creates this ref in the shared `.git`, which is what the `review` gate inspects. Don't rename or prefix it differently.
2. Read `items/<id>/plan.md` — this is the task list; do not re-derive it from the spec.
3. Execute the plan with `superpowers:subagent-driven-development`: a fresh implementer subagent per task, dispatched with `agents/implementer.md`, followed by a task review per `agents/reviewer.md` before the task is marked done. Follow that skill's fan-out guidance from the `capabilities` skill for any concurrent-safe tasks; implementation tasks themselves stay one-at-a-time per that skill's own red flag against parallel implementer dispatches.
4. As each task's review comes back clean, tick its `- [ ]` to `- [x]` in `plan.md` and commit that edit alongside (or immediately after) the task's own commits.
5. **On a task failing twice** (implementer + fix dispatch still can't clear task review after a second attempt): stop working this item. Leave the branch as-is — do not discard partial progress — log `implement.failed` per the Contract, and report to the dispatcher, which will apply its own two-strikes-then-blocked rule.
6. When every task is ticked, run the item's full test suite (the commands named in each plan task, plus the project's overall suite if broader than per-task commands). Only when it's green: log `implement.completed` with the real task count and a short test summary, then advance to `review` per the Contract.

## Notes

- Never advance past a red suite — a false `implement.completed` would let a broken branch reach `review` looking finished.
- The branch is never deleted here even on success; `ship` is the only stage that removes it (and only under the `auto` merge policy).
