---
description: Initialize this repo as a Factory target (scaffolds .factory/ and docs/factory/)
---
Before the first init, inspect `.factory/config.json`. If it is absent, or if it
has no `design.provider`, ask the user one question: whether Factory design work
should use **Codex** or **Claude Design via MCP**. Use the native
`AskUserQuestion` UI and do not infer the choice from the current host. Record
the answer by adding exactly one of `--design-provider codex` or
`--design-provider claude-design` to the init command. If a provider is already
recorded, preserve it and do not ask again.

If the user chooses Claude Design, probe the configured Claude Design MCP in
this interactive session and resolve the project with `list_projects` /
`get_project`. If more than one writable project is plausible, ask the user to
pick one; then add `--designsync-project PROJECT_ID`. If the MCP is unavailable,
still record the provider, explain that design will pause until a project is
linked, and do not silently change the answer to Codex.

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo . init --product "$ARGUMENTS" --design-provider PROVIDER [--designsync-project PROJECT_ID]` when arguments are given, otherwise drop `--product "$ARGUMENTS"`; then `... validate`.
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
