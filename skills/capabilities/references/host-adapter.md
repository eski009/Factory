# Host adapter

Factory's stage contracts are shared by Codex and Claude Code.

## Root and engine

In Claude Code, `${CLAUDE_PLUGIN_ROOT}` resolves the plugin root. In Codex,
resolve the plugin root as the directory two levels above the current
`skills/<skill>/SKILL.md`; call it `FACTORY_PLUGIN_ROOT`. Wherever a contract
says `factory`, use:

```text
python3 "<resolved-plugin-root>/scripts/factory/factory.py" --repo .
```

There is no bare `factory` executable on `PATH`. Never run `factory ...`.
Resolve the plugin root first and use the Python command above, including when
a downstream command contract uses `factory` as shorthand. Never assume
`CLAUDE_PLUGIN_ROOT` exists in Codex.

## Model routing

Before selecting a lead or dispatching a stage, read `model-routing.md` for
Claude-hosted sessions or `model-routing-codex.md` for Codex-hosted sessions
(both beside this file). Apply only the current host's map. Model selection
does not change a stage's fresh-context or independent-review requirements.

## Host translations

- A fresh/forked-context instruction means a Claude task with an isolated
  context or a fresh Codex subagent. Give it only the disk paths and item id
  named by the contract. If the host cannot create a fresh context, disclose
  that and do not claim independent review.
- `AskUserQuestion` means Claude's native question UI or Codex
  `request_user_input` when available; otherwise ask one concise question.
- Claude Read, Glob, and Grep operations map to Codex filesystem reads and
  `rg`. Shell commands map to the terminal with the same safety boundary.
- `mcp__claude-design__*` tools are provider-specific and may be used only for
  `design.provider: claude-design` (or the documented legacy fallback).
- Artifact/browser/MCP capabilities remain capability-gated. Never claim an
  unavailable tool ran.
