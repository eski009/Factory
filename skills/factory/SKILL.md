---
name: factory
description: Use when the user asks Factory to handle work, continue the pipeline, inspect status, initialize a repository, or route an ambiguous Factory request.
---

Read the capabilities skill's `references/host-adapter.md`. Inspect
`.factory/config.json` and run Factory status when initialized. Route explicit
requests to the matching `factory-*` skill. For a plain request such as "use
Factory" or "continue", read `commands/do.md` from the plugin root and follow
its routing contract. Never advance a stage directly when a stage skill owns it.
