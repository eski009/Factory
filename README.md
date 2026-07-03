# Factory

An autonomous software factory for Claude Code: a product brain that
maintains a roadmap, then specs, designs, plans, implements, reviews,
verifies, and ships work items — with UI design choices as the only
default human gate.

Works on any Claude model; Fable-only features are opportunistic
upgrades, never requirements. See
`docs/superpowers/specs/2026-07-03-software-factory-design.md`.

## Status

Phases 1-4: engine, council, plugin skills layer, and the design gate —
the zero-dependency Python engine (work-item state machine with enforced
gates, schemas, target-repo init, CLI), the memory-firewalled council
(bids, judgements, reputation, health, pruning), the full
skills/commands/agents layer that runs the pipeline end to end, and the
design gate itself.

**Design gate:** for `ui`/`mixed` items, the `design` stage generates 2-4
mockup options to a self-contained options page, writes a review packet
recommending one, and pauses the item at `waiting-human`. A human answers
with `factory choice <id> <option>` (or in-session); the next
`/factory:run` auto-resumes the item back through `design`, which detects
the recorded choice and advances it to `plan`. `backend` items skip this
stage entirely.

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
vendoring them. Install it alongside Factory.

## Quickstart

Once both plugins are installed in a target repo:

```
/factory:init your-product   # scaffold .factory/ and docs/factory/, seed the brain
/factory:add "Dark mode"     # add a work item to the backlog
/factory:run                 # run the pipeline (default mode: item)
```

`/factory:init` also invokes the `factory-intake` skill to seed
`docs/factory/brain/` from real sources in the target repo — a human should
review that seeded brain before the first council run treats it as ground
truth.

## Install into a target repo (engine only, no plugin)

```bash
python3 scripts/factory/factory.py --repo /path/to/your/repo init --product your-product
python3 scripts/factory/factory.py --repo /path/to/your/repo validate
```

## Engine CLI

```bash
factory.py add "Dark mode" --kind ui   # create a work item
factory.py status                      # list items by priority
factory.py advance 0001-dark-mode triage
factory.py log 0001-dark-mode verify.green --data '{"tests":"12 passed"}'
```

`advance` is the deterministic gatekeeper: it refuses any transition
whose preconditions (files and logged evidence) are unmet.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
