---
name: factory-interview
description: Use when a human is present at /factory:init, as its final seeding step - resolves outstanding brain questions interactively, one at a time, folding cited answers into the brain
---

## Purpose

The final seeding step of `/factory:init`, run **only when a human is present**.
`factory-intake` and `factory-research` seed `docs/factory/brain/` and park
everything they can't ground in a real source: entries in `open-questions.md`,
`(assumption)`-tagged claims in `personas.md`/`market.md`, surfaces still on
`_Not yet written._`, and (brownfield) the `docs/factory/packets/taste.md`
questionnaire. This skill asks those outstanding questions one at a time in
Claude's native question UI and folds the human's answers straight into the
brain — so a person sitting at the init resolves them on the spot instead of
reading files afterward.

## Never run this unattended

Invoke this skill **only from the human-invoked `/factory:init` flow**. Never
from autopilot, `factory-dispatch`, or any unattended path — including when
`factory-research` runs for a work item's research stage inside the dispatch
loop. The factory's hard rule is that autopilot never answers its own gates and
never simulates a human. This skill is the inverse: a *real* human answering.
When no human is present, do not run it — the parked files are the unattended
path, unchanged.

## 1. Harvest the questions (deduplicated)

Build one question set from four sources:

1. `docs/factory/brain/open-questions.md` — the gaps intake/research couldn't source.
2. `(assumption)`-tagged claims in `personas.md` / `market.md` and
   `docs/factory/journeys/inventory.md` (e.g. `(assumption)`-tagged
   criticality) — research's guesses, each turned into a confirm-or-correct
   question.
3. Brain surfaces and `docs/factory/journeys/inventory.md` still showing the
   `_Not yet written.` marker (every brain template's placeholder text begins
   with it — whole-surface placeholders continue with a sentence,
   personas/market field stubs end at the period — so the prefix is a
   reliable signal).
4. `docs/factory/packets/taste.md` questionnaire items (brownfield only; absent
   in a greenfield scaffold).

**Dedup:** if a placeholder surface already has a matching `open-questions.md`
entry (both name the same unknown), ask it once, preferring the
`open-questions.md` framing. Never ask the same unknown twice from two sources.

**Classify — only ask what a human can answer.** Sort harvested items into:

- **Owner-answerable** — vision, users, hard constraints, non-negotiables,
  taste, and research assumptions the product owner can confirm or correct.
  These get asked.
- **Operational notes** — e.g. "market/user web research not run — re-run with
  web access." Not a knowledge question. Leave parked, untouched; never surface
  it as an interview question.
- **Validation-required** — entries that specifically need *external* evidence,
  notably the focus group's "Persona validation" entry (resolved only by
  interviewing real target users with the guides). You may seed or confirm
  persona *hypotheses*, but **never mark "Persona validation" resolved** — that
  mirrors the focus-group firewall in `factory-research` §3b.4, which may never
  edit, resolve, or mark progress against that entry. Leave it parked.

## 2. Prioritize

Order owner-answerable questions by downstream impact — what the council leans on
earliest: **vision → users / personas → hard constraints**, then finer detail
(design-system nuance, secondary taste). If the human bails after three
questions, those three should have been the most decision-shaping ones.

## 3. Ask — native, one at a time

Open with a one-line preamble: the approximate count, that any question can be
skipped, and that saying **"park the rest"** stops the interview. Then ask each
question with the native `AskUserQuestion` tool, **one at a time**:

- Where intake/research produced a cited hypothesis or an `(assumption)`, make it
  the **lead option** — *"Research inferred your primary user is X — is that
  right?"* — with 1–2 alternatives (the tool's 4-option cap must leave room for
  the Skip option below). This turns research's guesses into one-tap
  confirmations.
- For genuinely open questions, offer the best 2–3 candidate framings.
- The tool's automatic "Other" option always captures free text, so no answer is
  ever forced into the presented choices.
- Include a native **"Skip / not sure"** option on every question (the common
  case — one tap, stays parked). Include a **"Stop — park the rest"** option too
  when the option budget allows (content options ≤ 2, since the tool permits 2–4
  options); regardless, honor "park the rest" typed into "Other" or said in chat.

On **"park the rest"**: stop immediately. Every not-yet-asked question stays
filed exactly as it is today. Go to the hard gate.

## 4. Record and resolve — per answer

When the human gives a real answer:

- **Write it into the correct brain surface** as a claim cited
  `(source: intake interview, <YYYY-MM-DD>)` (today's date). For a placeholder
  surface, this replaces the `_Not yet written.` placeholder text with the
  answer.
- **Upgrade confirmed assumptions:** an `(assumption)` claim the human confirms
  has its tag replaced with `(source: intake interview, <YYYY-MM-DD>)`; a
  corrected claim has both its text and its tag replaced.
- **Resolve the open-questions entry:** move the matching entry to a `## Resolved`
  section at the bottom of `open-questions.md`, noting the answer summary, where
  it landed, and the citation. Move it — don't delete it — to keep an audit
  trail. Create the `## Resolved` section on first use.
- **Taste packet:** fold taste answers into the brain the same way (cited
  `(source: intake interview, <date>)`) and also record the answer back into
  `taste.md` as the verbatim record. If the interview fully consumes the packet,
  move it to `docs/factory/packets/answered/taste.md` so the SessionStart hook
  (which globs `docs/factory/packets/*.md`, non-recursively) stops listing it as
  "awaiting review," and update any brain citations of
  `docs/factory/packets/taste.md` to the `answered/` path so they don't dangle.
  A partially answered packet stays where it is.
- **Journey answers** land in `docs/factory/journeys/inventory.md` and
  `graph.json` (same citation), the one non-brain surface this interview
  seeds — contracts/ stays untouched.

A skipped / "not sure" answer changes nothing — the item stays parked.

## Edge cases

- **No questions at all** — if harvesting yields zero owner-answerable questions,
  say so and go straight to the hard gate. Never open an empty `AskUserQuestion`.
- **Greenfield** — source 4 (taste packet) is absent; the other three still apply.
- **Degraded research (no web)** — the "re-run with web" note is an operational
  note, not asked; it stays parked.
- **Re-run of `/factory:init`** — idempotent: re-harvest only what is currently
  open (still-parked entries, still-`_Not yet written.` surfaces, still-
  `(assumption)` claims). Never re-ask already-resolved items. Intake
  regenerates a blank `taste.md` on a brownfield re-run — before asking taste
  questions, check `docs/factory/packets/answered/taste.md`: a question already
  answered there is resolved; copy its recorded answer into the fresh packet
  instead of re-asking, and move the packet again once fully consumed.
- **"I don't know"** — treat as a skip; the item stays parked.

## Hard gate

This skill does not shortcut the brain hard gate. When you finish, say this
verbatim, once (the interview is the last seeding step, so the sentence comes
after it rather than after research): "A human reviews the seeded brain before the first council run treats it as ground truth — say so when you finish."

## Exit

Report: how many questions were asked, how many resolved (with where each answer
landed), how many skipped or parked, and whether the taste packet was fully or
partially consumed. If journey answers changed the inventory and any
`mcp__claude-design__*` tool is present with `designsync_project` configured,
regenerate the linked project's `factory-journeys.html` map (capabilities
skill's `references/designsync.md` `## Journeys`) — best-effort, never
blocking. Then present the assembled brain for review and stop.
