---
name: factory-dispatch
description: Use when running the factory pipeline (via /factory:run or autonomously) - picks the next actionable item, executes its current stage, advances
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

You are the dispatcher: work selection, stage execution, stopping rules. Stage skills own the thinking for their stage; you own getting the right item to the right skill and knowing when to stop.

## Modes

- **step** — run one stage of one item, then stop.
- **item** — track one item by ID, stage after stage, until *that item* reaches `done`, `blocked`, or `waiting-human` — not until `factory next` happens to hand back a different item.
- **loop** — repeat item-mode across the backlog until `factory next` returns nothing actionable.

## The loop

Run these steps in order, every stage transition, in every mode:

0. **Resume check.** Before pulling any new work, look for answered pauses: `factory status --json`, filter to `stage == "waiting-human"`. For each, check whether the artifact it's waiting on now exists — today that means items paused from `design` (`meta["paused-from"] == "design"`) whose `.factory/items/<id>/design/choice.md` is now present and non-empty. If so, `factory advance ITEM <paused-from>` (the stage read from that item's own status JSON) and treat that item as the current one for this pass instead of calling `factory next`. On a successful resume advance, delete that item's answered packets — `docs/factory/packets/<id>.md` and `docs/factory/packets/<id>-design.md`, whichever exist — the log is the durable record, and a stale packet left behind misleads the hook's "awaiting review" listing. Do this in every mode, not just loop. In item mode, apply the resume-advance only when the resumed item is the currently tracked item; resumed answers on other items are left for a later pass (loop mode picks them up naturally).

1. **`factory validate`** — on any error, STOP. Write or refresh packets for the user; never guess at corrupt state.
2. **Pick the item**, unless step 0 already set one for this pass. In item mode, past the first iteration: skip `factory next`, and instead read the tracked item's own current stage from `factory status --json` — that item stays in hand until it reaches `done`, `blocked`, or `waiting-human`. Otherwise (step mode, loop mode, or item mode's first iteration): run `factory next --json`; if it returns null, invoke the `council-memory-health` skill — it runs `factory health` itself and routes any `prune` recommendation on to `council-pruning` — report its outcome to the user, and stop.
3. **Map stage to skill** and invoke it for the item in hand:

   | Stage | Skill |
   |---|---|
   | idea | factory-triage (covers the idea → triage → spec transitions) |
   | spec | factory-spec |
   | design | factory-design |
   | plan | factory-plan |
   | implement | factory-implement |
   | review | factory-review |
   | verify | factory-verify |
   | ship | factory-ship |

   If the mapped skill is unavailable for any reason, don't guess at the stage's work yourself: pause the item — `factory advance ITEM waiting-human --reason "<stage> stage requires the <skill> skill, which is unavailable"` — then follow the waiting-human rule below. When that branch fires, skip step 4 and return to step 0 — the pause substitutes for invoking a stage skill this iteration.
4. **Invoke the mapped skill** for the item. Let it do the stage's work and its own `factory advance` on success.
5. **Re-check mode:**
   - step: stop here.
   - item: continue with the same tracked item ID at its new stage — go back to step 0. Stop only when that item itself reaches `done`, `blocked`, or `waiting-human`; never switch to a different item mid-run just because `factory next` would now return one.
   - loop: continue with the backlog — go back to step 0.

## Stopping rules

- If a stage skill fails twice on the same item, stop retrying it: `factory advance ITEM blocked --reason "<what failed>"`, then `factory packet ITEM`. In loop mode, move on to the next item; in step or item mode, stop.
- Any item that enters `waiting-human` — whether via a stage skill's own gate or the mapped-skill-unavailable case above — always gets `factory packet ITEM` before you continue or stop.

## Capabilities

For any fan-out or design rendering, follow the capabilities skill.

## Context hygiene

Stage skills dispatch subagents for the heavy work (reading specs, writing code, reviewing diffs). The dispatcher itself never reads item artifacts beyond metas and skill results — keep this session's context to routing decisions, not item content.
