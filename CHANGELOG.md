# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Fixed

- **Tolerant log/ledger reading** — one corrupt `log.jsonl` or ledger line
  no longer crashes `factory status --json`, `factory cost`, packet
  rendering, gated advances, or `factory reputation`. Corrupt lines
  (including invalid UTF-8) are skipped at a single read boundary and
  surfaced loudly (`corrupt log lines: N (skipped; run factory validate)`,
  receipt suffix, stderr warnings); `factory validate` flags them per-line
  with exit 2 instead of crashing; `next_ledger_id` never reissues an id
  whose line got corrupted.

### Added

- **Claude Design mirror (DesignSync made concrete)** — the DesignSync
  capability now names the `mcp__claude-design__*` tool family: link a
  project once via `designsync_project`, and interactive design runs pull
  its tokens (mirrored into `design-system.md` only through the brain
  firewall) and push mockups/chosen directions back as convenience views.
  Repo files stay canonical; headless runs are unchanged; every round-trip
  logs proxy spend.
- **Per-item cost meter** — `factory cost <id>` aggregates each item's
  `log.jsonl` into an honest spend report: per-stage active vs waiting
  wall-clock (human gate time never counted as effort), dispatch/retry
  counts, and harness-reported token totals with structural provenance
  (`measured | proxy | unmeasured` — never blended, UNMEASURED always loud).
  Skills log `spend` events at fan-out points via the existing `factory log`;
  `factory validate` checks them; packets gain a three-line `## Spend`
  receipt and `status --json` a `spend` field.

- **Focus-group research step (opt-in)** — `factory-research` §3b: 4–6
  simulated stakeholder interviews with per-persona guides, firewalled
  assumption-grade findings, and a per-run spend log. Depth `deep` now
  includes the focus-group step; suppress with `--no-focus-group`, or force
  it at any depth with `--focus-group` on `/factory:research`.

## [0.2.0] - 2026-07-04

### Added

- **`validate` integrity audit** — `factory validate` now cross-checks the
  bid/judgement/reputation ledgers for duplicate ids, judgements referencing
  unknown bids, missing surface/anchor on authorizing decisions, and
  reputation events with the wrong delta/agent/topic or a missing/duplicate
  judgement link.
- **`factory priority`** — a CLI subcommand to set an item's priority
  (`factory priority <id> <n>`) independent of the triage stage.
- **`factory-roadmap` skill** — turns a PRD (and optional design file) into
  triaged work items and a prioritized `docs/factory/roadmap.md`, invoked
  via `/factory:roadmap <prd-path> [<design-path>]`.
- **Brownfield intake** — `factory-intake` now detects an existing target
  repo (routes, models, tests, tooling config) and runs collectors plus a
  taste packet to seed the product brain from real code rather than a
  blank scaffold.
- **Orchestration and model-tiering pattern references** —
  `skills/capabilities/references/orchestration-patterns.md` and
  `model-tiering.md`, documenting the session-proven orchestration patterns
  and which model tier runs a given task or subagent.
- **README "How it works"** — an ASCII pipeline diagram (stages, the design
  gate, both council moments) plus a 60-seconds-from-idea-to-shipped
  annotated example of the real commands.

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
