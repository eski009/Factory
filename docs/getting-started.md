# Getting started

A first-time walkthrough of Factory: install it, point it at a repo, run one
work item through the pipeline, and learn where to look when something needs
your attention. Every command below is real — copy-paste it.

## 1. Install

Factory is a Claude Code plugin. Add a marketplace pointed at this repo's git
URL, then install the plugin:

```
/plugin marketplace add <git-url-for-this-repo>
/plugin install factory
```

For local development, skip the marketplace and point Claude Code at a
checkout directly:

```bash
claude --plugin-dir /path/to/Factory
```

**Superpowers is a required companion plugin.** Factory's stage skills invoke
Superpowers skills — `test-driven-development`, `systematic-debugging`,
`verification-before-completion`, `using-git-worktrees`,
`finishing-a-development-branch` — for execution discipline rather than
vendoring that logic itself. Install Superpowers alongside Factory before
running anything.

## 2. Initialize a target repo

In the repo you want Factory to work on, run:

```
/factory:init your-product
```

This runs `factory.py init --product your-product` followed by `validate`,
which scaffolds two trees (only filling gaps — it never overwrites an
existing file, and never touches your product code or `CLAUDE.md`):

- `.factory/` — `items/`, `ledgers/{bids,judgements,reputation}.jsonl`,
  `runs/`, and `config.json` (defaults: `{"version": 1, "merge": "auto", "gates": ["design"]}`).
- `docs/factory/` — `packets/` and the product brain scaffolding under
  `brain/` (`vision.md`, `users.md`, `constraints.md`, `design-system.md`,
  `decisions.md`, `open-questions.md`) plus council role docs under
  `council/` and a `roadmap.md`.

`/factory:init` then invokes the **factory-intake** skill, which inventories
real sources in your repo (README, package metadata, git log, a linked issue
tracker) and fills the brain surfaces with claims cited back to those
sources — never invented product lore. Anything unanswerable from a real
source goes into `open-questions.md` instead of being guessed. Next,
**factory-research** seeds `personas.md` and `market.md` the same
evidence-only way. Finally, because you're sitting at the init,
**factory-interview** walks the outstanding questions — open questions,
`(assumption)` claims, placeholder surfaces, the brownfield taste packet —
one at a time in the native question UI: every question is skippable, "park
the rest" stops it, and each answer lands in the brain cited
`(source: intake interview, <date>)`. (Unattended runs never interview;
anything unasked stays parked in files, exactly as before.)

**Hard gate:** init always closes with this, verbatim — "A human reviews
the seeded brain before the first council run treats it as ground truth —
say so when you finish." Read `docs/factory/brain/*.md` before you add any
work items; the council reasons from whatever is there, thin or not.

## 3. Add a work item and run the pipeline

```
/factory:add "Dark mode"
/factory:run
```

`/factory:add` creates a work item at stage `idea` (kind defaults to
`mixed`; pass `kind:ui` or `kind:backend` in the title to be explicit) and
reports its id — it does not start work.

`/factory:run` (default mode: `item`) invokes the **factory-dispatch**
skill, which drives one item stage by stage:

```
idea → triage → spec → design → plan → implement → review → verify → assure → ship → done
```

Each stage maps to its own skill (`factory-triage` covers idea→triage→spec,
then `factory-spec`, `factory-design`, `factory-plan`, `factory-implement`,
`factory-review`, `factory-verify`, `factory-assure`, `factory-ship`). The
dispatcher runs
`factory validate` before every transition and stops immediately on any
validation error rather than guessing at corrupt state.

**The design gate.** For `kind: ui` or `kind: mixed` items, the `design`
stage generates 2-4 genuinely distinct mockup directions to a
self-contained `items/<id>/design/options.html`, writes a review packet to
`docs/factory/packets/<id>-design.md` recommending one, and pauses the item
at `waiting-human`. Read the packet (`/factory:packet <id>`), then answer:

```
factory choice 0001-dark-mode b --notes "wizard flow reads clearer"
```

The next `/factory:run` notices the recorded choice and auto-resumes the
item back through `design`, which advances it straight to `plan`. `backend`
items skip the design stage entirely — there's nothing to render.

**The assurance stage.** Between verify and ship, journey-affecting items
get a fresh-context walk of the affected customer journeys against the
running product (browser journeys need a browser-automation tool — absent,
the item parks for you rather than silently passing). Failures route back
to implement; judgement calls park with a packet. Your two verbs:
`factory waive <id> --reason "..."` (override with a recorded reason) and
`factory confirm <id>` (when you've configured `"assure"` in the config
`gates` list, items pause for your confirmation after passing). Anything
you still find after shipping: `/factory:escape` files it, and it stays
open until promoted into a contract, test, oracle, or review rule.

## 4. The autonomy dial

Factory doesn't require babysitting one item at a time. Three levers control
how much it does unattended:

- **`gates` in `.factory/config.json`** — which stages must pause for a
  human (`design` by default). An empty list means no stage-level human
  gate at all, though `waiting-human` can still happen if a mapped stage
  skill is unavailable.
- **`merge` in `.factory/config.json`** — the merge policy (`"auto"` by
  default) that the `ship` stage respects; autopilot never merges outside
  whatever this says.
- **`/factory:autopilot [budget hint]`** — invokes the `factory-autopilot`
  skill, a bounded wrapper around `factory-dispatch`'s `loop` mode. It runs
  `factory doctor` first and refuses to touch the backlog if `tree_valid` is
  false; otherwise it drains the backlog (or stops when the optional budget
  hint runs out), never answers its own human gates (no auto `choice`, no
  auto merge past the configured policy, no direct edits to
  `docs/factory/brain/`), and writes a run-summary packet to
  `docs/factory/packets/reports/` before exiting.

Autopilot only ever does what the loop and the configured gates already
permit — it's a bigger wrapper, not a bigger hammer.

## 5. Where state lives, and how to inspect it

- **`.factory/`** — the machine's own state: work items (`items/<id>/`),
  the three council ledgers, run history, and `config.json`. Treat it as
  generated/authoritative machine state, not something to hand-edit.
- **`docs/factory/`** — the human-readable side: the product brain
  (`brain/*.md`), council role docs, `roadmap.md`, and review `packets/`
  waiting for a decision.

Not sure which command you want? `/factory:do "…what you want, in your own
words…"` reads the pipeline state and routes to the right one — bug intake,
add, roadmap, run, an answer to a waiting packet — asking one clarifying
question when your intent genuinely fits two. With no arguments it does the
next right thing (surfaces a waiting packet, or dispatches the next item).

To check in on a running factory from any session:

```
/factory:status
```

which reports items by priority, the next actionable item, memory health,
and any packets waiting under `docs/factory/packets/`. The CLI's
`factory status` also prints the open-escape count and the journey
coverage debt — how many registered journeys are still inventory-only or
hold only draft contracts. Shallow coverage is legitimate (deep contracts
exist only where they earn their keep); unnamed shallow coverage is not.

For a lower-level readout of the repo's integration state (whether the
state tree validates, whether design-system tokens and a DesignSync
project are configured, the merge policy and gates, and open/pending
item counts), run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo . doctor
```

(or `factory doctor --json` for machine-readable output). This is the same
check autopilot runs as its own preflight gate.
