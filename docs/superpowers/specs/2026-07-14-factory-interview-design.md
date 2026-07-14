# Interactive intake interview for `/factory:init`

- **Date:** 2026-07-14
- **Status:** Approved design, pending spec review
- **Topic:** A human-present interview stage that resolves outstanding init questions one at a time, natively, instead of leaving them all parked in files.

## Problem

After `/factory:init` runs `factory-intake` and `factory-research`, everything those
skills couldn't ground in a real source is **parked in files**: entries in
`docs/factory/brain/open-questions.md`, `(assumption)`-tagged claims in
`personas.md`/`market.md`, brain surfaces still on `_Not yet written._`, and (brownfield)
the `docs/factory/packets/taste.md` questionnaire. That parking is deliberate — init can
also run unattended, where nothing may block on input — but it means a human who *is*
sitting at the init has to go read files afterward to answer questions they could have
answered on the spot.

We want: **when a human is present, ask those outstanding questions interactively — one at
a time, in Claude's native question UI — and fold the answers straight into the brain.**

## Decisions (locked during brainstorming)

1. **Model — supplement, human-present.** When a human is at the init, ask outstanding
   questions and fold answers into the brain. Anything skipped or unanswered still lands in
   `open-questions.md`. The unattended (autopilot) path is unchanged and stays file-only.
2. **Scope — everything askable.** Harvest questions from all four sources below, not just
   `open-questions.md`.
3. **Pacing — prioritized + bail anytime.** Highest-impact questions first; every question
   skippable; an explicit "park the rest" exit at any point that ends the interview and
   leaves remaining questions filed exactly as today.
4. **Recording — into surface, cited, resolved.** Each answer is written directly into the
   correct brain surface as a claim cited `(source: intake interview, <YYYY-MM-DD>)`, and the
   matching `open-questions.md` entry is moved to a Resolved section. The existing brain
   hard-gate still applies to the whole assembled brain.

## Why a new skill, not a change to intake/research

`factory-research` (and, on refresh, `factory-intake`) can run **unattended** inside the
autopilot dispatch loop — e.g. a work item's research stage at `deep` depth. The factory's
strongest invariant is *"autopilot never simulates a human / never answers its own gates."*

Therefore the interview must **not** live inside intake or research — it would eventually
fire in an unattended context. It is a **separate stage that only the human-invoked
`/factory:init` command runs**, after intake and research have finished seeding and parking.
Because the interview is reachable only through the init command's path, it is structurally
impossible for autopilot to reach it. Intake and research stay byte-for-byte unchanged,
preserving their safe dual attended/unattended behavior.

Alternatives considered and rejected:

- **Bake asking into intake/research behind an "attended" flag.** Fragments the prioritized
  pass across two skills, duplicates the asking logic, and leans a fragile guard against the
  factory's strongest invariant — one missed guard interviews a robot.
- **Inline the interview as prose in `init.md`.** Real logic (prioritize, cite, resolve,
  bail) does not belong as untestable command prose, and is not reusable.

## Architecture

### New skill: `factory-interview`

- **Home:** `skills/factory-interview/SKILL.md`, following the existing `factory-*` skill
  convention (prose-driven, like `factory-intake`/`factory-research`).
- **Invoked by:** the `/factory:init` command flow only, as its final seeding step.
- **Never invoked by:** autopilot, dispatch, or any unattended path.

### Revised init flow

`/factory:init` becomes:

1. `factory.py init` (+ `validate`) — unchanged
2. `factory-intake` — unchanged (seeds + parks)
3. `factory-research` — unchanged (seeds + parks)
4. **`factory-interview`** — new; runs the interview described below
5. The single verbatim brain hard-gate sentence, stated **once after the interview** (it
   currently comes after research; it moves to after the interview, which is now the last
   seeding step).

`commands/init.md` is edited to add step 4 and move the hard-gate sentence to after it.

## The interview lifecycle

### 1. Harvest (scope = everything askable)

Build one **deduplicated** question set from four sources:

1. `open-questions.md` entries — the gaps intake/research couldn't source.
2. `(assumption)`-tagged claims in `personas.md` / `market.md` — research's guesses, each
   turned into a confirm-or-correct question.
3. Brain surfaces still showing the `_Not yet written.` placeholder (reliable detection;
   every brain template's placeholder text begins with that prefix — whole-surface
   placeholders continue with a sentence, personas/market field stubs end at the period).
4. `docs/factory/packets/taste.md` questionnaire items (brownfield only; absent greenfield).

**Dedup rule:** if a placeholder surface already has a corresponding `open-questions.md`
entry (both point at the same unknown), ask it once, preferring the `open-questions.md`
framing. Never double-ask the same unknown from two sources.

**Classification rule — only ask what a human can answer.** Split harvested items into:

- **Owner-answerable** — vision, users, hard constraints, non-negotiables, taste, and
  research assumptions the product owner can confirm/correct. These are asked.
- **Operational notes** — e.g. "market/user web research not run — re-run with web access."
  Not a knowledge question. Left parked untouched; never surfaced as an interview question.
- **Validation-required** — entries that specifically require *external* evidence, notably
  the focus group's "Persona validation" entry (resolved only by interviewing real target
  users with the guides). The interview may seed/confirm persona *hypotheses* but **must not
  mark "Persona validation" resolved**, mirroring the existing focus-group firewall
  (`factory-research` §3b.4, which may never edit, resolve, or mark progress against that
  entry). Left parked.

### 2. Prioritize

Order owner-answerable questions by downstream impact — what the council leans on earliest:
**vision → users/personas → hard constraints**, before finer detail (design-system nuance,
secondary taste). The goal is that if the human bails after three questions, those three
were the most decision-shaping ones.

### 3. Ask (native, one at a time)

Open with a one-line preamble: approximate count, "skip any question," and "say *park the
rest* to stop." Then, for each question, use the native `AskUserQuestion` tool, one at a
time:

- Where intake/research produced a **cited hypothesis or `(assumption)`**, it becomes the
  **lead option** — e.g. *"Research inferred your primary user is X — right?"* — with 1–2
  alternatives (the tool's 4-option cap must leave room for the "Skip / not sure" option
  below). This turns research's guesses into one-tap confirmations.
- For genuinely **open** questions, offer the best 2–3 candidate framings.
- The tool's auto "Other" option always captures free-text, so no answer is ever forced
  into the presented choices.
- **Escape affordances:** every question includes a native **"Skip / not sure"** option
  (the common case, one tap → stays parked). A **"Stop — park the rest"** option is included
  as well when the option budget allows (content options ≤ 2, since the tool permits 2–4
  options); regardless, the preamble tells the human they can type "park the rest" at any
  point, and the skill treats that intent (from an "Other" free-text answer or a chat
  message) as the bail signal.

On **"park the rest"**: stop immediately; every not-yet-asked question stays filed exactly
as it is today. Proceed to the hard gate.

### 4. Record & resolve (per answer)

When the human gives a real answer:

- **Write it into the correct brain surface** as a claim cited
  `(source: intake interview, <YYYY-MM-DD>)` (the run date). For a placeholder surface, this
  replaces the `_Not yet written.` placeholder text with the answer.
- **Upgrade confirmed assumptions:** an `(assumption)` claim the human confirms has its tag
  replaced with `(source: intake interview, <YYYY-MM-DD>)`; a corrected claim has both its
  text and tag replaced.
- **Resolve the open-questions entry:** move the matching entry to a `## Resolved` section at
  the bottom of `open-questions.md`, noting the answer summary, where it landed, and the
  citation. (Moved, not deleted — preserves an audit trail. The skill creates the `## Resolved`
  section on first use; no template change required.)
- **Taste packet:** taste answers are folded into the brain the same way (cited
  `(source: intake interview, <date>)`) and also recorded back into `taste.md` as the verbatim
  record. If the interview fully consumes the packet, move it to
  `docs/factory/packets/answered/taste.md` so the SessionStart hook (which globs
  `docs/factory/packets/*.md`, non-recursively) stops listing it as "awaiting review." When
  the packet moves, brain citations of `docs/factory/packets/taste.md` are updated to the
  `answered/` path so they don't dangle. (On a later re-run, intake regenerates a blank
  questionnaire; the harvest treats questions already answered in `answered/taste.md` as
  resolved — the recorded answer is copied in rather than re-asked.) A partially answered
  packet stays in place.

Skipped / "not sure" answers change nothing — the item stays parked.

### 5. Hard gate (unchanged)

After the interview, state the existing verbatim sentence once: *"A human reviews the seeded
brain before the first council run treats it as ground truth — say so when you finish."* The
human still reviews the whole assembled brain (interview answers + scraped claims) before the
first council run. The interview does not bypass or shortcut this gate.

## Edge cases

- **No questions at all.** If harvesting yields zero owner-answerable questions (brain fully
  sourced, no assumptions, no placeholders, no taste packet), the skill says so and skips
  straight to the hard gate. It never opens an empty `AskUserQuestion`.
- **Greenfield.** Source 4 (taste packet) is empty; the other three still apply.
- **Degraded research (no web).** The "re-run with web" note is an *operational note*, not
  asked; it stays parked.
- **Re-run of `/factory:init`.** Idempotent: the skill re-harvests only what is currently
  open (still-parked entries, still-`_Not yet written.` surfaces, still-`(assumption)`
  claims). Already-resolved items are not re-asked — including taste questions whose
  answers are already recorded in `answered/taste.md` (see above).
- **Human answers "I don't know."** Treated as a skip — item stays parked.

## Files touched

- **New:** `skills/factory-interview/SKILL.md`.
- **Edit:** `commands/init.md` — add the interview as step 4; move the single hard-gate
  sentence to after it.
- **Edit:** `README.md` and `CHANGELOG.md` — document the new interactive init behavior
  (the repo maintains both diligently).
- **No change:** `factory.py` (no CLI support needed — the skill reads/edits brain markdown
  directly, like intake/research), `factory-intake`, `factory-research`, `factory-autopilot`,
  `factory-dispatch`, and the brain templates.

## Testing

- **Structural:** the new skill must pass the existing plugin-structure checks
  (`tests/test_plugin_structure.py` — frontmatter, and registration in `.claude-plugin/` if
  the manifest enumerates skills; the implementation plan verifies whether it does and updates
  it if so).
- **Behavioral (manual dogfood, since the stage is interactive and prose-driven):** run
  `/factory:init` on a scratch repo and confirm the interview (a) asks prioritized questions
  one at a time, (b) offers research assumptions as lead options, (c) writes cited answers into
  the right surfaces and moves resolved entries to `## Resolved`, (d) honors skip and
  "park the rest", and (e) still fires the hard-gate sentence. Confirm an autopilot run
  (`/factory:autopilot`) never triggers the interview.

## Non-goals / out of scope

- No standalone `/factory:interview` command. The skill is directly invocable if wanted
  later, but no new command is added now.
- No changes to `factory.py`, autopilot, dispatch, or intake/research seeding logic.
- The interview does not resolve validation-required questions (e.g. "Persona validation").
- The interview does not bypass the brain hard gate.
