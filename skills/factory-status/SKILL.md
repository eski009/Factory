---
name: factory-status
description: Use when the user asks for Factory pipeline, backlog, item, or integration status.
---

Read the capabilities skill's `references/host-adapter.md` and
`commands/status.md` from the plugin root, then follow that status contract.
Resolve the plugin root before executing anything. Never invoke a bare
`factory` executable; translate every command to the adapter's explicit Python
entry point.
