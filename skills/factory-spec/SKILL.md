---
name: factory-spec
description: Use when a factory item is at stage spec - writes the item's spec from the product brain without human back-and-forth
context: fork
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

This skill runs in a forked context (`context: fork`): nothing from the invoking session is visible here. The item id arrives as the skill argument; everything else is read from disk — `factory status --json`, `.factory/items/<id>/...`, and the brain surfaces this skill names below. Your final message is the report the dispatcher acts on: state the outcome (the stage advanced to, or the failure/pause reason, verbatim where a gate refused), name the key artifact paths written, and keep it to a few lines — never paste file contents into it.

## Contract

- **Entry stage:** `spec`.
- **Artifacts produced:** `items/<id>/spec.md`.
- **Exit:** for `kind: ui` or `kind: mixed`, attempt `factory advance ITEM design`; for `kind: backend`, attempt `factory advance ITEM plan`. The engine gate is the authority on what's legal — if it refuses, report the gate message verbatim rather than guessing a different stage.

## Read first

Read the item body, `items/<id>/triage.md`, and the brain surfaces: `docs/factory/brain/vision.md`, `users.md`, `personas.md`, `constraints.md`, and (for `ui`/`mixed` items) `design-system.md`.

## The autonomous substitute for brainstorming

There is no human in this loop to argue with, so the dialogue that normally happens in brainstorming has to happen against the brain instead:

1. **Enumerate the 3-5 key design questions** this item raises — the kind of thing a brainstorming partner would ask (scope boundary, key user flow, data shape, failure mode, what's explicitly out).
2. **Answer each question from the brain.** For every question, check vision.md, users.md, personas.md, constraints.md, and design-system.md for a real answer — including whether the choice serves the primary persona. An answer counts only if you can point to the source passage — don't infer one from vibes.
3. **Where the brain has no answer — a brain gap — choose the most reversible option.** Reversible means: cheapest to undo later, narrowest surface area, closest to what a user could reasonably expect. Never pick the option that's hardest to walk back just because it looks more complete.
4. **Record the assumption** in the spec under `## Assumptions (brain gaps)`, naming the question, the choice made, and why it's reversible.
5. **File a bid** for each brain gap via the `council-judgement` skill, targeting `--surface brain/open-questions.md`, so the gap becomes durable memory instead of getting silently re-decided by the next item that hits it:

   ```
   factory bid product TOPIC "CLAIM" --evidence .factory/items/<id>/spec.md --surface brain/open-questions.md --severity low
   ```

   Use the round-note/evidence rules from `council-judgement`: since there's no real citation for a gap, the item's own spec is the provenance pointer, not proof.

This loop — enumerate, answer-from-brain, reversible-default, record, file-bid — is mandatory for every question that the brain doesn't answer. Skipping the bid leaves the gap invisible to future items.

## Large items: dispatch spec-writer

If the spec would run to roughly more than a screen of `## Behavior` bullets, or `items/<id>/triage.md` flags the item as complex, don't author it inline — dispatch `agents/spec-writer.md` with the item body, `triage.md`, and the brain excerpts from Read first. It runs the same enumerate/answer-from-brain/reversible-default loop and returns the spec text as its final report; this session (the orchestrator, not the subagent) persists that report to `items/<id>/spec.md` — the same orchestrator-persists convention council rounds use. `agents/spec-writer.md` is read-only (Read, Grep, Glob), so it cannot file bids itself: after persisting the spec, file a `factory bid` per brain gap its report names, same as step 5 above.

## Spec structure

Write `items/<id>/spec.md` with these sections, in order:

- `## Purpose` — what this item is for and why it matters, one paragraph.
- `## Behavior` — what the system does, described concretely enough to build from.
- `## Non-goals` — what this item explicitly does not cover.
- `## Assumptions (brain gaps)` — one entry per brain gap from the loop above (omit the section only if there were none).
- `## Acceptance criteria` — a numbered list, each criterion testable (a later stage can check it mechanically or by inspection, not by opinion). If the item body contains a section titled `## Acceptance criteria (seeded at bug intake — carry into spec.md verbatim)`, its criteria MUST appear verbatim in this list — they may be joined by further criteria, never replaced or reworded.

## Exit

- `ui` or `mixed`: `factory advance ITEM design`.
- `backend`: `factory advance ITEM plan`.

If the gate refuses (missing spec content, wrong kind, wrong current stage), do not retry with a different stage guess — report the refusal message verbatim and stop.
