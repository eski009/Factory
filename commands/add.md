---
description: Add a work item to the factory backlog ($ARGUMENTS = title, optionally "kind:ui|backend|mixed")
---
Parse $ARGUMENTS into TITLE and optional kind (default mixed; use ui/mixed when
the work touches user-facing interface). Run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo . add "TITLE" --kind KIND`.
Report the new item id. Do not start work on it — /factory:run does that.
