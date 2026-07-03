# Factory

An autonomous software factory for Claude Code: a product brain that
maintains a roadmap, then specs, designs, plans, implements, reviews,
verifies, and ships work items — with UI design choices as the only
default human gate.

Works on any Claude model; Fable-only features are opportunistic
upgrades, never requirements. See
`docs/superpowers/specs/2026-07-03-software-factory-design.md`.

## Status

Phase 1 (engine core) — the zero-dependency Python engine: work-item
state machine with enforced gates, schemas, target-repo init, CLI.
Skills, agents, council, and the design gate arrive in later phases.

## Install into a target repo

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
