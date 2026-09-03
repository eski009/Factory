---
name: factory-init
description: Use when the user asks to initialize or set up Factory in a repository.
---

Read the capabilities skill's `references/host-adapter.md` and
`commands/init.md` from the plugin root. Before first init, or when an existing
config has no `design.provider`, ask whether design work should use **Codex** or
**Claude Design via MCP**. Record the answer with `factory init
--design-provider codex` or `factory init --design-provider claude-design`,
preserving any product argument. When Claude Design is selected, use its MCP to
resolve the writable project, ask the user when more than one is plausible, and
pass `--designsync-project PROJECT_ID`. If the MCP is unavailable, record the
provider and report the missing link; never silently switch to Codex. Follow the
rest of the canonical init flow and never replace a provider or project already
recorded.
