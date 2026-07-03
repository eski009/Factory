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
`docs/factory/brain/*.md`; it has no license to change anything else in the
target repo, however tempting a fix looks along the way.

## Finish

End by listing which surfaces are still thin (little or no real content) —
this tells the user what the triage council will treat as open questions
rather than settled ground.

## Hard gate

Always say this to the user when you finish, verbatim: "A human reviews the
seeded brain before the first council run treats it as ground truth — say so
when you finish."
