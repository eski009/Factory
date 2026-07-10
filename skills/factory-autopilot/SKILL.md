---
name: factory-autopilot
description: Use when running the factory continuously or on a schedule - a bounded autonomous loop with explicit safety stops
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

You are the bounded autonomous wrapper around `factory-dispatch`'s loop mode: one invocation drives the backlog until it drains or a budget runs out, then stops and reports. Autopilot adds safety bounds on top of the loop; it never replaces the loop's own judgment.

## 1. Preflight

Before touching the backlog, run `factory doctor` (or `factory doctor --json`) and read `tree_valid`. If `tree_valid` is `false`, STOP immediately — do not invoke `factory-dispatch`, do not advance or touch any item. Write a packet describing the corrupt-tree finding and exit. Never operate on a tree the doctor can't validate.

## 2. Run the loop

Once the preflight passes, invoke `factory-dispatch` in `loop` mode. That skill's own rules — `factory validate` on every pass, stop on any validation error, pause items at `waiting-human`, block items that fail a stage twice — are the safety net for this run. Autopilot does not duplicate or second-guess them; it trusts the loop to do its own stopping when something goes wrong mid-item.

## 3. Gate respect

Autopilot is a wrapper, not a bigger hammer. It never gains authority the loop and its stage skills don't already have:

- It never records a design `choice` on an item's behalf — `design/choice.md` is written only by a human via `factory choice`, never by autopilot itself.
- It never merges outside the repo's configured `merge` policy (`merge`/`gates` in the factory config) — ship still stops wherever that policy says it must.
- It never edits `docs/factory/brain/` directly — brain changes flow only through the judgement firewall (`council-judgement`).
- Most importantly: **autopilot never answers its own human gates.** Any item that lands at `waiting-human` — whether from a design pause, a merge gate, or a mapped-skill-unavailable pause — stays parked exactly where the loop left it, with its packet written for a person to read. Autopilot never simulates a human, never picks a design option, never approves a merge, and never resumes a paused item itself. Only a real human action (e.g. `factory choice`) moves a parked item forward — the loop's own resume check picks that up on a later invocation.

## 4. Budget and termination

Stop the run when either condition is met:

- **Backlog drained** — `factory-dispatch` in loop mode returns nothing actionable (`factory next` comes back null and nothing is waiting on a resumable answer).
- **Budget exhausted** — a caller-provided budget (from `$ARGUMENTS` on `/factory:autopilot`, e.g. a time or item-count hint) runs out. Autopilot doesn't invent a budget when none is given — treat an absent budget as "run until drained." Check the budget at each loop-iteration boundary — between items, at `factory-dispatch`'s step 5 (re-check mode / pick next). When the budget is spent, stop advancing new items, finish any half-done stage safely, and go straight to writing the run-summary packet.

Either way, before exiting, write a run-summary packet to `docs/factory/packets/reports/` (a bespoke packet, not a per-item one) covering: items advanced this run, items parked at gates (with their stage and reason), and any items blocked. This is autopilot's own exit report, separate from any per-item packets the loop already wrote along the way — it lives under `reports/` so it doesn't linger in the top-level packets listing the SessionStart hook treats as "awaiting human review."

The run-summary packet also carries a `## Spend` section: one line per item touched this run, in the form `- <id>: [proxy] active <dur>, <n> dispatches; [measured] tokens <observed keys, e.g. total <n>>` (render only the token keys that were actually logged nonzero for that item — never fabricate `input 0`/`output 0` for a split nobody reported — or `; [measured] tokens: none logged` when that item has no measured spend events) — read each item's figures from `factory cost <id> --json` — plus exactly one run-total line that sums **within** each provenance class across items, e.g. `- run total: [proxy] <n> dispatches; [measured] tokens <observed keys, e.g. total <n>>`. Never collapse the run into a single blended number that mixes provenance classes, and never render the orchestrator's own unmeasured main-loop burn as zero or a dollar figure.

## 5. Scheduling

This skill is schedule-agnostic: one invocation is one drain-or-budget run, nothing more. It does not schedule itself, re-invoke itself, or wait for a future run. For how to put `/factory:autopilot` on a recurring schedule — and why to schedule the command rather than a bare loop — see `skills/capabilities/references/scheduling.md`. Without scheduling tooling, the degraded path — a human running `/factory:autopilot` (or `/factory:run loop`) whenever they want the factory to advance — is what this skill is written against by default.
