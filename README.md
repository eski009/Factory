# Factory

An autonomous software factory for Claude Code: a product brain that
maintains a roadmap, then specs, designs, plans, implements, reviews,
verifies, and ships work items — with UI design choices as the only
default human gate.

Works on any Claude model; Fable-only features are opportunistic
upgrades, never requirements. See
[`docs/superpowers/specs/2026-07-03-software-factory-design.md`](docs/superpowers/specs/2026-07-03-software-factory-design.md)
for the full design, and [`docs/getting-started.md`](docs/getting-started.md)
for a first-time walkthrough.

## How it works

```
idea → triage[1] → spec → design[2] → plan → implement → review[3] → verify → ship → done
```

*(`backend` items skip `design` entirely — `plan` follows `spec` directly.)*

- **[1] council, triage mode** — before `spec` is written: bounded council
  bids plus an orchestrator judgement decide build/priority/scope.
- **[2] THE human gate** — `ui`/`mixed` items only. `factory-design` writes
  2-4 mockup options and a review packet, then pauses the item at
  `waiting-human`. A human answers `factory choice <id> <a-d>`; the next
  `/factory:run` notices the recorded pick and resumes the item straight
  into `plan`.
- **[3] council, review mode** — after `implement`: the council reviews the
  diff against spec and brain before the item can reach `verify`.

### 60 seconds from idea to shipped

```
$ /factory:add "Dark mode"          # files a work item at stage idea
$ /factory:run                      # idea → triage[1] → spec → design;
                                     #   pauses at waiting-human with
                                     #   docs/factory/packets/0001-dark-mode-design.md
$ factory choice 0001-dark-mode b   # records the human's pick of option b
$ /factory:run                      # resumes design → plan → implement →
                                     #   review[3] → verify → ship → done
```

See [`docs/getting-started.md`](docs/getting-started.md) for the full
first-time walkthrough, including the autonomy dial.

## Status

Phases 1-6 complete: engine, council, plugin skills layer, design gate,
capability upgrades, and release scaffolding.

- **Product-brain pipeline** — a gate-checked state machine (see "How it
  works" above) refuses any transition whose preconditions aren't met.
- **Bounded council with a memory firewall** — agents file evidence-backed
  bids, an orchestrator judges them, reputation accrues per agent/topic,
  and the product brain (`docs/factory/brain/`) can only change through
  that judgement path, never a direct edit.
- **Autopilot** — a bounded autonomous loop (`/factory:autopilot`) that
  preflights repo health, drains the backlog or a budget, and never
  answers its own human gates.
- **Works on any Claude model** — Fable-only features are opportunistic
  upgrades, never requirements.

## Install as plugin

Factory is a Claude Code plugin. Add it from a marketplace pointed at this
repo's git URL, then install it:

```
/plugin marketplace add <git-url-for-this-repo>
/plugin install factory
```

For local development, point Claude Code at a checkout directly instead:

```bash
claude --plugin-dir /path/to/Factory
```

**Superpowers is a required companion plugin** — Factory invokes Superpowers
skills (test-driven-development, systematic-debugging,
verification-before-completion, using-git-worktrees,
finishing-a-development-branch) for execution discipline rather than
vendoring them. Install it alongside Factory. This requirement is not
machine-enforced — plugin manifests don't support dependency
declarations — so install Superpowers yourself alongside Factory.

## Quickstart

Once both plugins are installed in a target repo:

```
/factory:init your-product    # scaffold .factory/ and docs/factory/, seed the brain
/factory:add "Dark mode"      # add a work item to the backlog
/factory:run                  # run the pipeline (default mode: item)
/factory:status               # items by priority, next actionable item, packets, health
/factory:packet <id>          # render a review packet for an item
/factory:autopilot [budget]   # run the loop unattended until drained or budget spent
```

`/factory:init` also invokes the `factory-intake` skill to seed
`docs/factory/brain/` from real sources in the target repo — a human should
review that seeded brain before the first council run treats it as ground
truth. See [`docs/getting-started.md`](docs/getting-started.md) for the full
walkthrough, including the design gate and the autonomy dial.

## Install into a target repo (engine only, no plugin)

```bash
python3 scripts/factory/factory.py --repo /path/to/your/repo init --product your-product
python3 scripts/factory/factory.py --repo /path/to/your/repo validate
```

## Engine CLI

The plugin's skills drive this CLI; it's also usable standalone. Subcommands:
`init`, `validate`, `add`, `status`, `next`, `advance`, `log`, `packet`,
`choice`, `bid`, `judge`, `reputation`, `health`, `prune`, `doctor`.

```bash
factory.py add "Dark mode" --kind ui        # create a work item
factory.py status                           # list items by priority
factory.py next                             # get the next actionable item
factory.py advance 0001-dark-mode triage    # move an item to a stage (gate-checked)
factory.py log 0001-dark-mode verify.green --data '{"tests":"12 passed"}'
factory.py packet 0001-dark-mode            # write/render a review packet
factory.py choice 0001-dark-mode b          # record the human's design-option pick
factory.py reputation                       # derived reputation per agent/topic
factory.py health                           # memory-health score and recommendation
factory.py doctor                           # readout of repo integration state
```

`advance` is the deterministic gatekeeper: it refuses any transition
whose preconditions (files and logged evidence) are unmet.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
