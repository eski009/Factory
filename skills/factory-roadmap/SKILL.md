---
name: factory-roadmap
description: Use when a PRD (and optionally a design file) needs to become tickets and a prioritized roadmap - extracts candidates, seeds the brain, triages the batch, files items
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

## Inputs

`$ARGUMENTS` = a PRD path (required), optionally followed by a design-file path. If the PRD path doesn't exist, refuse politely and stop — do not create, edit, or advance anything. The optional design file, if given and missing, is just absent context (not a refusal condition).

## 1. Extract candidates

Read the PRD and enumerate one candidate per feature, epic, or story it describes. For each candidate, record:

- **Title**
- **Provisional kind** — `ui` if it names a user-facing surface, `backend` if purely internal, `mixed` otherwise
- **PRD section cited** — `(source: <prd-path>#<section-or-heading>)`

If a design file was given, in this same pass extract the tokens, components, and patterns it defines and write them into `docs/factory/brain/design-system.md`, each claim cited `(source: <design-path>)`.

## 2. Seed the brain first

Before any triage happens, seed `docs/factory/brain/vision.md`, `users.md`, and `constraints.md` from the PRD — evidence-only, with an inline citation on every claim: `(source: <prd-path>#<section>)`. Anything the PRD doesn't settle (users you can't confirm, constraints it doesn't state) goes to `brain/open-questions.md` naming what's unknown, never invented into the surface.

When this seeding is done, say this to the user verbatim: "A human reviews the seeded brain before the first council run treats it as ground truth — say so when you finish."

## 3. Batch triage

Run the `council-review` skill in **triage mode** exactly once over the whole candidate list — one `seed-context.md` listing every candidate from step 1 (title, provisional kind, cited section), not one council run per candidate. The council returns, per candidate, a build/don't-build call, a relative priority ranking, and its reasoning.

For each candidate the council accepts, in order:

1. Before adding, check idempotency (see below) — skip if an equivalent open item already exists.
2. `factory add "TITLE" --kind KIND` — capture the printed item id.
3. `factory priority ITEM N` — N is that candidate's position in the council's relative ranking (1 = highest).
4. Write `items/<id>/triage.md` citing the council synthesis (`reviews/synthesis.md`) for the build call, priority, and any scope notes.

For each candidate the council rejects, append an entry to `brain/open-questions.md` naming the candidate and the council's stated reason — rejected candidates are never silently dropped.

Once all accepted candidates are filed, write `docs/factory/roadmap.md` in priority order, one line per item, following the flat convention from `factory-triage`: `- [priority] <item-id> <title> (stage)`.

## 4. Idempotency

Before running `factory add` for any candidate, run `factory status --json` and check its `title` fields for an existing item with the same title that isn't `done` or `blocked`. If one exists, treat that candidate as a skip, not an add — don't file a duplicate — and note the skip when reporting counts.

## Exit

Report: candidates found, added, rejected, and skipped (as duplicates), plus a reminder that `/factory:run` starts execution on the roadmap just written.
