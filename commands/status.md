---
description: Show the factory pipeline - items by priority, waiting packets, reputation
---
Run these and summarize compactly (one table, then one line each for packets
and anything needing the user):
- `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo . status`
- `... next`
- `... health`
- list docs/factory/packets/*.md if any exist
