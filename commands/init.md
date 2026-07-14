---
description: Initialize this repo as a Factory target (scaffolds .factory/ and docs/factory/)
---
Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo . init --product "$ARGUMENTS"` when arguments are given, otherwise drop `--product "$ARGUMENTS"`; then `... validate`.
Show the created paths. Then invoke the factory-intake skill to seed
docs/factory/brain/ from real sources ($ARGUMENTS names the product if given).
Then invoke the factory-research skill (persona + market research, at the
configured research.depth) so personas.md and market.md are seeded before the
human reviews the brain. Then, because a human is present at `/factory:init`,
invoke the factory-interview skill to walk the outstanding questions
interactively — open questions, `(assumption)` claims, `_Not yet written._`
surfaces, and any brownfield taste packet — folding cited answers into the brain
one at a time. (factory-interview never runs unattended; autopilot leaves those
questions parked in files.) factory-intake, factory-research, and
factory-interview each close with the same verbatim brain hard-gate sentence when
run alone; running them together here, state that sentence once after the
interview rather than repeating it. If the brain
templates are still placeholders, tell the
user triage will treat empty surfaces as open questions.
