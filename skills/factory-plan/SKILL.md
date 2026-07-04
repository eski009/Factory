---
name: factory-plan
description: Use when a factory item is at stage plan - produces the TDD implementation plan the implement stage executes
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

## Contract

- **Entry stage:** `plan`. The gate into `plan` already required `spec.md` non-empty, and (for `ui`/`mixed` items) `design/choice.md` — both are readable inputs here.
- **Artifacts produced:** `items/<id>/plan.md`.
- **Exit:** `factory advance ITEM implement`. The gate requires `plan.md` to exist and contain at least one `- [ ]` checkbox — a plan with no checkbox tasks cannot advance.

## REQUIRED SUB-SKILL: superpowers:writing-plans

Use `superpowers:writing-plans` to build the plan. Read `items/<id>/spec.md` (and `items/<id>/design/choice.md` for `ui`/`mixed` items) as the spec input it expects, then follow its file structure, task right-sizing, and no-placeholders discipline in full. Adapt it to this factory as follows:

- **Location:** save the plan to `items/<id>/plan.md` — not the skill's default `docs/superpowers/plans/` path.
- **Checkbox tasks:** every task step uses `- [ ]` markdown checkbox syntax, exactly as writing-plans already specifies. This isn't optional dressing here — the `implement` gate mechanically greps `plan.md` for `- [ ]` and refuses to advance without one.
- **Test commands:** every task must name the exact files it touches, the exact tests it adds or runs, and the exact test command to run them (e.g. `python3 -m unittest tests.test_foo -v`) — no "run the tests" without the command.
- **Acceptance-criteria references:** every task cites which numbered item in the spec's `## Acceptance criteria` it satisfies, so a reviewer can trace task back to requirement without re-reading the whole spec.
- **One-subagent-sized tasks:** size each task so a single subagent dispatch can complete it standalone (the writing-plans skill's "Task Right-Sizing" section) — this factory always executes plans one task per subagent, never inline batches.
- **Complete code, not descriptions:** every task carries the exact code, exact tests, and exact commands (with expected output) it needs — a task is done when the implementer's job is transcription, never invention. This is what makes implementer output correct-by-construction rather than correct-by-judgment: see the capabilities skill's `references/orchestration-patterns.md`, pattern 1. A task that says "add appropriate handling for X" instead of showing the handling is not plan-complete.
- Skip writing-plans' "Execution Handoff" section — this factory has one execution path (the `implement` stage skill), not a choice between subagent-driven and inline execution.
- **Plan header "For agentic workers" line:** replace the REQUIRED SUB-SKILL boilerplate with `> **For agentic workers:** Executed by the factory-implement skill — one fresh subagent per task. Steps use checkbox (- [ ]) syntax for tracking.`

## Steps

1. Read `items/<id>/spec.md` and, for `ui`/`mixed` items, `items/<id>/design/choice.md`.
2. Follow `superpowers:writing-plans` with the adaptations above to produce `items/<id>/plan.md`.
3. Self-review the plan against the spec's acceptance criteria (writing-plans' own self-review step): every criterion should trace to at least one task; every task should cite the criteria it covers.
4. Confirm `plan.md` contains at least one `- [ ]` line before exiting — the gate will refuse otherwise.

## Exit

`factory advance ITEM implement`. If the gate refuses (no checkbox task found, wrong current stage), report the refusal message verbatim rather than re-attempting with edits guessed on the fly — fix the actual missing checkbox first, then retry.
