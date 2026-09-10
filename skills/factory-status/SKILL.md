---
name: factory-status
description: Use when the user asks for Factory pipeline, backlog, item, or integration status.
---

Read the capabilities skill's `references/host-adapter.md`,
`references/derived-ledger.md`, and `commands/status.md` from the plugin root,
then follow that status contract.
Resolve the plugin root before executing anything. Never invoke a bare
`factory` executable; translate every command to the adapter's explicit Python
entry point.

When the user asks about a specific completed run and supplies or has already
pinned its base/head commits, offer or run `factory ledger` for the evidence
breakdown. Keep the ordinary cumulative status response unchanged. The ledger
is a read-only accounting view, not a delivery gate or a speed claim; do not
add its separate inventories or overlapping timing categories together.
