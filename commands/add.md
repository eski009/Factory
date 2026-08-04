---
description: Add a work item to the factory backlog ($ARGUMENTS = title, optionally "kind:ui|backend|mixed" and "tier:epic|feature|bug")
---
**Route first.** If $ARGUMENTS describes a defect — something that used to work,
crashes, or produces wrong output — hand it verbatim to the `factory-bug` skill,
exactly as /factory:bug does, and do **not** run `factory add`. That door
replicates the defect before any fix work and sets the `bug` flag the plan gate
reads.

Otherwise parse $ARGUMENTS into TITLE, an optional kind (`kind:ui|backend|mixed`,
default `mixed`; use ui/mixed when the work touches user-facing interface), and an
optional tier (`tier:epic|feature|bug`). Run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo . add "TITLE" --kind KIND`,
adding `--tier TIER` only when a tier was given.

The two are different claims. `tier` is a **materiality** claim — how much of the
expensive machinery the change is worth. `bug: true` is an **evidence** claim — a
repro was confirmed — and only /factory:bug sets it. Filing here with `tier: bug`
records materiality only and does **not** arm the plan gate's repro requirement;
the engine prints a warning saying so and files the item as
"bug tier, repro unverified".

Report the new item id. Do not start work on it — /factory:run does that.
