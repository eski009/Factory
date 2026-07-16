---
name: factory-intake
description: Use when initializing a factory target or refreshing the product brain - seeds brain surfaces from real sources, evidence only
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

## Purpose

`docs/factory/brain/` is the product brain the council reasons from. Right
after `factory init` it's placeholder text ("_Not yet written._"). This skill
replaces those placeholders with claims that trace back to something real —
never with invented plausible-sounding product lore.

## Inventory real sources first

Before writing anything, gather what actually exists in the target repo:

- `README.md` and any `docs/` directory prose
- package metadata (`package.json`, `pyproject.toml`, `Cargo.toml`, etc.) —
  name, description, dependencies
- recent `git log` (subject lines and touched paths tell you what's actively
  worked on and by whom)
- a linked issue tracker, if one is discoverable (issue templates, a linked
  repo URL, references in the README)

## Fill each surface, cited

The six brain surfaces: `vision.md`, `users.md`, `constraints.md`,
`design-system.md`, `decisions.md`, `open-questions.md`.

For each, write only claims you can point at a source, with an inline
citation on the claim: `(source: <path-or-url>)`. A git log commit counts as
a source — cite it by short SHA or subject. If a surface has nothing
traceable to say, leave it as-is rather than inventing filler; don't pad a
thin surface with generic industry-standard boilerplate to make it look
complete.

## No source, no claim

When a surface's natural content is unanswerable from real sources (e.g. no
docs describe the target users), don't guess a plausible answer — add a
matching entry to `open-questions.md` naming what's unknown and what would
resolve it, instead of writing invented content into that surface.

## Never

Never touch product code or `CLAUDE.md`. This skill only writes to
`docs/factory/brain/*.md`, `docs/factory/journeys/` (inventory.md and
graph.json only — never contracts/, which belong to the spec stage and the
council firewall), and, in brownfield mode, `docs/factory/packets/taste.md`;
it has no license to change anything else in the target repo, however
tempting a fix looks along the way.

## Brownfield mode

Brownfield means the target repo already contains product code — routes,
components, business logic — rather than a fresh scaffold with placeholder
files. If the inventory above turns up real application code (not just
tooling config), treat this as a brownfield seed and run three collectors in
addition to the inventory:

**1. Repo mining (all cited).** Read structure, don't invent it:

- lint/format configs and observed naming/structure conventions → `constraints.md`
- theme files, CSS variables, design tokens, component library → `design-system.md`
- routes, screens, navigation surface → `users.md`
- `git log`, ADRs, PR titles → `decisions.md`
- the test suite, read as a behavior spec, feeding `constraints.md` and `users.md`

Same citation rule as above: every claim needs `(source: <path>)`.

- **Journey inventory (brownfield):** the same routes/screens/navigation
  mining and test-suite reading also emit a first journey inventory —
  `docs/factory/journeys/inventory.md` entries plus matching `graph.json`
  records (stable id `J-NNN` starting at J-001, slug, title, persona when
  `users.md` names one, trigger, intended outcome, `status: inventory`,
  links to the routes/screens/tests that evidence it). Criticality is a
  guess at intake — tag it `(assumption)`; every entry cites its source
  like any other claim. Never invent a journey the code doesn't evidence —
  an uncertain flow goes to `open-questions.md` instead. Greenfield repos
  skip this collector: the templates stay placeholder and the init
  interview asks the owner.

**2. Taste packet.** Write `docs/factory/packets/taste.md`, a questionnaire
for the human covering: 3 products whose UI they admire and why; hard
non-negotiables; what "done" or "quality" means here; voice and tone;
anti-references (what to avoid). Tell them their answers get edited directly
into the packet, and the next intake or roadmap run folds those answers into
the brain with `(source: docs/factory/packets/taste.md)` citations. The
packet is optional — leaving it unanswered blocks nothing downstream. The
SessionStart hook lists any file under `docs/factory/packets/` as "awaiting
human review"; `taste.md` showing up there unanswered is expected in
brownfield mode, not a defect to clean up.

**3. Ongoing accrual.** Collectors only bootstrap the brain once. The
compounding channel for taste going forward is the existing mechanism:
council bids get filed, an orchestrator turns them into judgements, and
judgements accrue into each role's memory — that loop, not another intake
pass, is how taste keeps sharpening after seeding.

## Finish

End by listing which surfaces are still thin (little or no real content) —
this tells the user what the triage council will treat as open questions
rather than settled ground.

## Hard gate

Always say this to the user when you finish, verbatim: "A human reviews the
seeded brain before the first council run treats it as ground truth — say so
when you finish."
