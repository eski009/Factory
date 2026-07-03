---
name: factory-dispatch
description: Use when running the factory pipeline (via /factory:run or autonomously) - picks the next actionable item, executes its current stage, advances
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

You are the dispatcher: work selection, stage execution, stopping rules. Stage skills own the thinking for their stage; you own getting the right item to the right skill and knowing when to stop.

## Modes

- **step** — run one stage of one item, then stop.
- **item** — run one item, stage after stage, until it reaches `done`, `blocked`, or `waiting-human`.
- **loop** — repeat item-mode across the backlog until `factory next` returns nothing actionable. Between items, check for an answered packet first: if a `design/choice.md` was newly filled while another item was running, resume that item before pulling a fresh one from `next`.

## The loop

Run these steps in order, every stage transition, in every mode:

1. **`factory validate`** — on any error, STOP. Write or refresh packets for the user; never guess at corrupt state.
2. **`factory next --json`** — if it returns null, run `factory health`, report the recommendation to the user, and stop.
3. **Map stage to skill** and invoke it for the item `next` returned:

   | Stage | Skill |
   |---|---|
   | idea | factory-triage (covers the idea → triage → spec transitions) |
   | spec | factory-spec |
   | design | factory-design (Phase 4 — see below if absent) |
   | plan | factory-plan |
   | implement | factory-implement |
   | review | factory-review |
   | verify | factory-verify |
   | ship | factory-ship |

   If the item's stage is `design` and the factory-design skill isn't present yet, don't run design work yourself — pause the item instead: `factory advance ITEM waiting-human --reason "design stage requires Phase 4 design skill"`, then follow the waiting-human rule below.
4. **Invoke the mapped skill** for the item. Let it do the stage's work and its own `factory advance` on success.
5. **Re-check mode:**
   - step: stop here.
   - item: continue with the same item at its new stage — go back to step 1.
   - loop: continue with the backlog — go back to step 1.

## Stopping rules

- If a stage skill fails twice on the same item, stop retrying it: `factory advance ITEM blocked --reason "<what failed>"`, then `factory packet ITEM`. In loop mode, move on to the next item; in step or item mode, stop.
- Any item that enters `waiting-human` — whether via a stage skill's own gate or the design-skill-absent case above — always gets `factory packet ITEM` before you continue or stop.

## Capabilities

For any fan-out or design rendering, follow the capabilities skill.

## Context hygiene

Stage skills dispatch subagents for the heavy work (reading specs, writing code, reviewing diffs). The dispatcher itself never reads item artifacts beyond metas and skill results — keep this session's context to routing decisions, not item content.
