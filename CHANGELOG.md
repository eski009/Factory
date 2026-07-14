# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.6.0] - 2026-07-14

### Added

- **Every decision packet carries a clickable link to a visual HTML options
  page.** Generalises what the design gate already did to every
  `waiting-human` pause: `factory packet` now writes a self-contained,
  mobile-legible `docs/factory/packets/<id>.html` beside the Markdown packet,
  and both renderers gain a **"View the options"** section whose links are
  ordered by preference — a hosted Artifact URL (from the paused reason) →
  the local `design/options.html` → the HTML packet itself — so a Markdown
  file is never the primary view when an HTML page exists. Artifacts render
  as clickable `file://` links, and the Respond block uses the real item id
  (fixing the literal `<id>`/`<option>` placeholders). `factory-dispatch`
  surfaces the HTML link at every pause; see
  `skills/capabilities/references/decision-pages.md`.

## [0.5.0] - 2026-07-13

### Added

- **Headless workers — out-of-process, parallel execution.** A new `factory
  work <id>` engine command runs one headless coding-agent worker (backend
  `claude` or `codex`, plus a test-only `stub`) inside an item's
  `factory/<id>` git worktree and captures a normalized `result.json` — the
  worker owns its own context, so the orchestrator never holds its
  transcript, and the run logs a **measured** spend event (the implement
  station's burn moves from unmeasured to measured). On top of the executor,
  a skill-driven **bounded pool** (`factory-workers`) keeps K workers busy
  across independent items: `factory next -n` selects the top-N, `factory
  provision` prepares each worktree (`.worktreeinclude` copy + a prep command
  + an isolated, trust-seeded `CLAUDE_CONFIG_DIR`/`CODEX_HOME`), workers
  launch staggered with capped-exponential backoff against the shared org
  rate-limit bucket, and `factory cleanup` reclaims worktrees (keeping the
  branch). Off by default (`workers.enabled`); absent or disabled, every
  stage falls through to the in-process subagent path unchanged, and `factory
  doctor` reports readiness. Nothing lowers a gate — worker output stays
  untrusted until it clears the same review + verify + green-tests net.

- **Work-item materiality tiers.** Items gain a `tier` frontmatter field
  (`epic | feature | bug`, default `feature`), orthogonal to `kind`, set by
  an agent at triage (`factory tier <id> <tier>` / `factory add --tier`). A
  `tiers` config block maps each tier to a `{research, review}` profile
  (epic deep/full · feature web/full · bug off/light; `factory doctor --json`
  reports the resolved profiles). The expensive layers now scale to
  materiality: the **focus group runs only for material epics** (a feature or
  a bug can't trigger it even under a global `research.depth: deep`), and a
  **bug gets a light, correctness-only council review** (the customer/
  commercial market seats drop; the end-to-end walk and every gate stay
  intact). Additive and back-compat — an absent tier reads as `feature`, and
  no stage gate reads the tier.

### Fixed

- Result-schema `files_changed` change enum widened so an unusual `git`
  status is safe-fail instead of a schema crash; auth failures
  (401/403/invalid key) are classified as reason `auth` with a distinct exit
  code so a bad key surfaces immediately instead of masquerading as a worker
  crash; `duration_s` is populated; `worker_config` tolerates malformed
  nested config; HTTP-status matching in the auth/rate-limit detectors is
  word-boundary + stderr-scoped so a UUID digit collision can't misclassify
  an ordinary crash.

Suite: 332 → 431 tests.

## [0.4.0] - 2026-07-11

### Added

- **`/factory:bug` — replicate-first bug intake** (item 0010). A ninth
  command + `factory-bug` skill: understand the report (at most one
  synchronous clarification round), replicate the bug BEFORE any fix work
  (`items/<id>/repro.md` with the exact command and verbatim failing output,
  plus a `repro.confirmed` evidence event), and hard-stop to waiting-human
  when replication fails — never fix an unreplicated bug. Intake seeds two
  mandatory acceptance criteria ("the recorded repro now passes", "a
  regression test failed on pre-fix code") that the verify stage's Iron Law
  enforces with fresh evidence. Work items gain an optional `bug: boolean`
  frontmatter/schema field (absent = falsy; zero migration), and the engine's
  plan gate refuses a bug item without both the repro file and the event —
  the discipline is engine-enforced, not prose. factory-spec now carries
  intake-seeded acceptance criteria into `spec.md` verbatim. ui/mixed bugs
  route through the existing design gate via kind; restore-to-spec visual
  bugs stay backend. Suite: 322 → 332 tests.

## [0.3.0] - 2026-07-11

### Fixed

- **Never-bricks completion** — byte-level (non-UTF-8) corruption in
  `item.md`/`config.json` now yields clean refusals and validate flags
  instead of tracebacks; gates fail closed on undecodable evidence; ledger
  lines missing required keys are filtered at the read boundary (id floor
  preserved) so reputation/judge/health survive; plain `factory status`
  prints one aggregated corrupt-log-lines notice; validate flags every
  corrupt shape the tolerant reader skips; corruption copy unified to
  count-after-label.
- **Tolerant log/ledger reading** — one corrupt `log.jsonl` or ledger line
  no longer crashes `factory status --json`, `factory cost`, packet
  rendering, gated advances, or `factory reputation`. Corrupt lines
  (including invalid UTF-8) are skipped at a single read boundary and
  surfaced loudly (`corrupt log lines: N (skipped; run factory validate)`,
  receipt suffix, stderr warnings); `factory validate` flags them per-line
  with exit 2 instead of crashing; `next_ledger_id` never reissues an id
  whose line got corrupted.

### Added

- **Interactive decision pages** — the design gate's options page is now
  interactive: pick buttons for each option plus exactly one "None of
  these", optional per-option commentary (composed into structured
  `--notes`), a sticky bar with the live-composed `factory choice` command
  (the zero-network, phone-friendly baseline), and a Record control a live
  session can read back (browser-read capability) so the pick lands without
  copy-paste. "None of these" routes the item back to design regeneration
  with the commentary as input (capped at two rounds), never forward to
  plan. Every capture path still terminates in `factory choice` — the
  engine's single writer.
- **Design-mirror refinements** — the pull-mirror bid now fires only when
  pulled tokens actually differ (no judge busywork on stable design
  systems); design packets disclose the token source, snapshot path, and
  mirror-bid status (including rejections); the first accepted mirror
  replaces the invented-neutrals fallback tokens rather than accumulating.
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
