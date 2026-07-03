# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.0] - 2026-07-03

### Added

- **Engine** — zero-dependency Python CLI (`scripts/factory/factory.py`) implementing
  the work-item state machine (`idea → triage → spec → design → plan → implement →
  review → verify → ship → done`, plus `blocked`/`waiting-human`), gate-checked
  `advance` transitions, JSON-schema-validated items and ledgers, target-repo `init`
  and whole-tree `validate`, the bid/judgement/reputation council ledgers, memory
  `health` scoring, provenance-preserving `prune`, and `doctor` repo-integration
  readout.
- **Plugin** — the `factory-dispatch` skill (work selection, per-stage execution,
  resume/stop rules) driving the eight pipeline-stage skills
  (`factory-triage`/`-spec`/`-design`/`-plan`/`-implement`/`-review`/`-verify`/`-ship`),
  the bounded council protocol (bids, judgements, reputation) with a memory firewall
  around `docs/factory/brain/`, the `factory-design` UI design gate (mockup options,
  review packet, human `choice`), and `factory-autopilot` for bounded autonomous runs.
- **Install** — Claude Code plugin packaging (`.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`), the slash commands
  (`/factory:init`, `/factory:add`, `/factory:status`, `/factory:run`,
  `/factory:packet`, `/factory:autopilot`), and Superpowers as a required companion
  plugin for execution discipline.
