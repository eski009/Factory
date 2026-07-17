---
description: Tell the factory what you want in your own words - it figures out which command, skill, or verb that is ($ARGUMENTS = anything, or empty for "do the next right thing")
---
Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

You are a router, not a new pipeline: read the intent, hand it to the one
surface that already owns it, and follow that surface exactly. Never invent
a new flow here, never run `factory advance` yourself (stage skills own
transitions), and never widen what the matched surface is allowed to do.

**Read state first** — intent depends on it: `factory status` and a listing
of `docs/factory/packets/*.md` (what's waiting on the human). If the repo
isn't a factory repo yet (`status` says "not a factory repo"), the only
route is to tell the human to run `/factory:init` — nothing else works
before that.

**Route $ARGUMENTS to the most specific match:**

- **Something is broken or misbehaving** (a bug report, "X crashes",
  "Y looks wrong since the last change") → pass it verbatim to the
  `factory-bug` skill, exactly as /factory:bug does.
- **A new idea or feature** ("add dark mode", "we should support CSV
  export") → `factory add "TITLE" --kind KIND` (kind ui/mixed when it
  touches interface, else backend), report the id, do not start work —
  offer /factory:run.
- **A document or list of many wants** (a PRD path, a pasted backlog) →
  the `factory-roadmap` skill.
- **Research intent** ("what would users think of X", "size the market
  for Y") → the `factory-research` skill, as /factory:research does.
- **Keep going / continue / next** → the `factory-dispatch` skill, mode
  from their words (step | item | loop; default item).
- **Drain everything unattended** → the `factory-autopilot` skill.
- **Where are we / what's waiting on me** → the /factory:status readout
  (status, next, health, packets).
- **An answer to a parked question** — route by what the packet asked,
  and ONLY when the human's own words carry the decision:
  - a design pick ("go with option b") → `factory choice ITEM OPT`
  - a post-assurance confirmation ("looks good, ship it") →
    `factory confirm ITEM`
  - a waiver ("ship anyway because REASON") →
    `factory waive ITEM --reason "REASON"` — the reason must be theirs,
    verbatim or tightened, never invented; no reason in their words →
    ask for one.
- **Something they found after the factory said done** → follow
  commands/escape.md as if /factory:escape had been invoked.
- **Empty $ARGUMENTS** ("just do the next right thing"): a packet waiting
  on the human → surface it and ask for their answer; otherwise actionable
  items in the backlog → `factory-dispatch` (item mode); otherwise say the
  backlog is empty and ask what they want to add.

**When two intents genuinely fit, ask ONE clarifying question** — the human
is present; that is this command's whole advantage over guessing. When
nothing fits, say what the factory can do (add, bug, roadmap, research,
run, autopilot, status, escape, init) and ask — never force the nearest
match.

**Human verbs stay human.** `factory choice`, `factory waive`,
`factory confirm`, and escape promotion run here only as relays of a
decision the human just expressed — this command never decides for them,
and unattended runs (autopilot, scheduled) never invoke it at all.
