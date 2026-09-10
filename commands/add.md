---
description: Add a work item to the factory backlog ($ARGUMENTS = title, optionally "kind:ui|backend|mixed")
---
Route reported defects (regressions, crashes, or wrong output) verbatim to the
`factory-bug` skill, exactly as `/factory:bug` does, and do **not** run `factory
add` first. That intake reproduces the defect before filing it and records the
evidence required for the shorter confirmed-bug route. A requested materiality
tier is not proof of a reproduced defect.

For non-defect ideas, parse $ARGUMENTS into TITLE and optional kind (default mixed; use ui/mixed when
the work touches user-facing interface). Run
`python3 "${FACTORY_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/scripts/factory/factory.py" --repo . add "TITLE" --kind KIND`.
Report the new item id. Do not start work on it — /factory:run does that.
