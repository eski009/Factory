# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.9.2] - 2026-07-17

### Added

- **`/factory:do` — one entry point, your words.** A router command that
  takes free-form intent ("dark mode is broken", "keep going", "go with
  option b", a PRD path, or nothing at all for "do the next right thing"),
  reads the pipeline state first, and hands the intent to the surface that
  already owns it — bug intake, add, roadmap, research, dispatch,
  autopilot, status, or the escape flow. It is a relay, not a new
  pipeline: it never advances stages itself, only runs the human verbs
  (`choice`/`waive`/`confirm`) when the human's own words carry the
  decision (a waiver reason is never invented), asks one clarifying
  question when two intents genuinely fit, and is never invoked by
  unattended runs.

### Changed

- **README gains a command reference** — all eleven slash commands with
  one-line descriptions, plus the four human-only CLI verbs (`choice`,
  `confirm`, `waive`, `promote`) and where the rest of the engine CLI
  lives.

## [0.9.1] - 2026-07-17

### Added

- **Journey traceability closes its declared-shape gaps.** The
  machine-readable impact declaration (`assurance-impact.schema.json`) now
  carries what the spec prose already promised: scenario kinds gain
  `empty` and `error` alongside happy/recovery/interruption; browser-borne
  journeys declare their required `viewports`; and every journey answers
  the adjacency question explicitly — `adjacent.upstream` /
  `adjacent.downstream` name the surrounding nodes that need inspection
  because expectations or state carry across (empty lists are a considered
  no; an omitted key is not a no). factory-spec's Declare duty writes all
  of it; factory-assure and the journey-reviewer walk it — every declared
  viewport, every declared adjacent node. All additions are
  schema-optional, so mid-flight items validate unchanged.
- **Journey coverage debt is explicit.** `factory status` now prints the
  honest remainder of the progressive-depth registry: how many journeys
  are inventory-only (no contract) and how many hold only draft contracts.
  Shallow coverage was always legitimate; silent shallow coverage no
  longer is.
- **DOM/a11y snapshots as first-class evidence.** The reviewer captures a
  DOM or accessibility-tree snapshot into `assurance/dom/` where semantics
  carry the evidence (labels, roles, focus order, announced state), typed
  `dom` in verdicts — pixels alone can look right while the semantics are
  wrong. Draft contracts now also record trust-and-reassurance
  requirements at commitment nodes and the required evidence per surface.
- **Cross-screen coherence named as the verdict rule.** The walk judges
  the journey as a whole: an expectation created on one screen that a
  later screen contradicts or abandons is a fail at the later node, citing
  the earlier node's evidence — isolated per-screen passes can no longer
  compose into a passing journey.

## [0.9.0] - 2026-07-16

### Added

- **DesignSync journeys — the journey model meets the linked design
  project.** Three additions riding the existing `mcp__claude-design__*`
  capability, inheriting its doctrine unchanged (interactive sessions only,
  probe-don't-ask, degrade-never-block, proxy spend, repo files canonical —
  never a second source of truth). (1) **Visual journey map:** the three
  surfaces that mutate `docs/factory/journeys/` — intake at seeding end,
  factory-spec on registering a journey or drafting a contract, and
  `/factory:escape` after a `contract:` promotion — regenerate a
  self-contained `factory-journeys.html` flow view (nodes, transitions,
  criticality, contract status) in the linked project, best-effort and
  never blocking. (2) **Greenfield frame-pull:** a greenfield repo has no
  routes to mine, but a linked design project often holds the screens
  before code exists — intake now pulls its frame/flow structure and emits
  journey-inventory entries cited `(source: claude-design
  <project>/<file>)` with `(assumption)`-tagged criticality, which the init
  interview then puts in front of the owner automatically. (3)
  **Node-annotated design gate:** pushed mockup options and the
  chosen-direction note carry the journey nodes their screens serve (from
  `impact.json`), and a recorded pick may refresh the touched nodes'
  expectation text in still-draft contracts — never approved ones, which
  amend only through the council-judgement firewall. No engine changes; the
  assure stage is untouched (design artifacts never substitute for
  running-product evidence). Suite: 532 → 536 tests.

## [0.8.0] - 2026-07-16

### Added

- **Parallel Codex workers on the ChatGPT subscription, not just API keys.**
  A new `workers.codex.auth` key in `.factory/config.json` — `"key"`
  (default, unchanged: `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` in the
  environment) or `"chatgpt"`: `factory provision` copies
  `~/.codex/auth.json` into each worker's isolated `CODEX_HOME` with the
  refresh token stripped, so no worker can rotate the login — the pool fans
  out on one subscription token at any parallelism without racing it, and
  the engine never writes the real `~/.codex`. Provision fail-closes when
  the access token wouldn't outlive the run (`timeout_seconds` + margin),
  naming the fix (log in with `codex` interactively, then retry); mid-run
  expiry is classified `reason: auth` → exit 1, the same honest pool-stop a
  bad key already triggers, never a silent retry loop. Chatgpt-mode worker
  environments have `OPENAI_API_KEY` popped so billing can't silently flip
  to the API mid-run. `factory doctor --json` → `workers` gains `codex_auth`
  (the configured mode) and `codex_login` (remaining access-token TTL in
  seconds). Default mode is `"key"` — existing configs are unaffected.

Suite: 505 → 532 tests.

## [0.7.0] - 2026-07-16

### Added

- **Journey assurance — a first-class `assure` stage between verify and
  ship.** The pipeline is now `idea → triage → spec → design → plan →
  implement → review → verify → assure → ship → done`. Review asks "is the
  code sound," verify asks "do the checks pass" — assure asks "can the
  customer get through it." Every spec must now declare journey impact: a
  `## Journey impact` section in `spec.md` plus a `journeys` frontmatter
  field set via the new `factory journeys <id> <none|J-004,...>` verb — the
  hardened spec-exit gates (design and plan) refuse to advance an item
  without both. `journeys: none` is a valid, explicit answer that skips
  assure through the engine's `stage_sequence` (the same mechanism backend
  items use to skip design); an *absent* declaration never is. An assurance
  failure routes back to implement on a second bounded rework edge
  (`assure.rejected`, lifetime cap 2, then blocked with a packet).

- **A round-scoped ship gate over schema-validated evidence.** For
  journey-affecting items, ship requires
  `.factory/items/<id>/assurance/verdicts.json` that schema-validates,
  covers every declared journey and every scenario `impact.json` requires,
  references evidence files that actually exist under the item dir, and
  contains no fail or unresolved ambiguity — plus an `assure.passed` (or
  `assure.waived`) event logged *after* the latest `implement.completed`:
  the engine's first round-scoped evidence check, so after a rework bounce
  stale assurance no longer satisfies ship. When the config `gates` list
  includes `"assure"`, ship additionally requires an equally round-scoped
  `assure.confirmed` — a recorded waiver is authoritative and satisfies the
  gate on its own.

- **A durable journey model.** `docs/factory/journeys/`, sibling to the
  brain: `inventory.md` + `graph.json` are roadmap-like — stage skills
  maintain them directly — while `contracts/` are brain-like: a stage skill
  may author a *draft* contract directly, but amending an *approved* one
  goes through the council-judgement firewall. Brownfield `factory-intake`
  infers inventory entries from the routes/screens/tests mining it already
  performs (every entry cited, criticality tagged `(assumption)`), and the
  init interview harvests the placeholder and those assumptions
  automatically — zero interview changes. `factory-spec` gains three
  mechanical duties: **map** the item's behavior onto journey nodes
  (drafting a contract where an affected journey lacks one), **declare**
  the impact in `spec.md` and its machine-readable twin `impact.json`, and
  **set** `factory journeys` — and `factory-bug` seeds `## Journey impact`
  at intake from the replicated broken node, carried into spec verbatim.

- **A fresh-context journey reviewer + the Browser drive capability.** The
  assure stage dispatches one fresh journey-reviewer subagent per affected
  journey — no implementer transcript, no review/verify conclusions, no
  "this is complete" framing — which walks the journey node by node against
  the *running product*, writing expectations before acting and capturing
  screenshot, console, and network evidence. Browser journeys need a
  browser-automation tool (Playwright MCP, chrome-devtools MCP, or
  Claude-in-Chrome — a behavioral probe, not tool-pinned); absent, the item
  parks `waiting-human` with a blocker packet, never a silent pass. CLI/API
  journeys are driven through the real commands a caller would run, with
  typed transcripts in place of screenshots. Depth scales with materiality
  via the tier profiles' new `assure` key: a bug re-walks the broken node,
  a feature the affected journeys, an epic the full journey surface
  (`node | affected | full`).

- **Two human-only verbs, engine-enforced.** `factory waive <id> --reason
  "..."` records a waiver (writes `assurance/waiver.md`, refuses an empty
  reason); `factory confirm <id>` records the confirmation
  (`assurance/human-confirmation.md`) when the assure gate is configured.
  Both are single-writer at the engine level — `factory log` refuses to
  record `assure.waived`/`assure.confirmed` events, so no skill or
  autopilot path can fake them — and dispatch auto-resumes a parked item
  when the waiver or confirmation file appears, exactly like a design
  choice.

- **The escape register.** A fourth append-only ledger
  (`.factory/ledgers/escapes.jsonl`, schema-validated per line) for
  anything a human still finds after assurance: `/factory:escape`
  classifies the miss conversationally and files it via `factory escape`;
  the record stays **open** until `factory promote` links it to a contract
  amendment, regression test, acceptance oracle, council review rule, or
  brain decision — and `factory status` surfaces the open count until then.
  That's the compounding loop: escape → improved contract or check → future
  assurance catches it → fewer human discoveries.

**Migration note.** Items already past spec never hit the hardened
spec-exit gates, but any pre-existing item reaching assure without a
journeys declaration parks `waiting-human` with a packet. Unblock it with
`factory journeys <id> none` — valid even while parked; the engine falls
back to the unfiltered stage sequence so the item can advance out — or
with `factory waive <id> --reason "..."`.

Suite: 434 → 505 tests.

## [0.6.0] - 2026-07-14

### Added

- **Interactive intake interview at `/factory:init`.** A new
  `factory-interview` skill runs as init's final seeding step: because a
  human is present at `/factory:init`, the outstanding questions that
  intake and research park in files — `open-questions.md` entries,
  `(assumption)` claims in `personas.md`/`market.md`, brain surfaces still
  on their `_Not yet written.` placeholder, and the brownfield taste
  packet — are asked
  right there, one at a time in the native question UI, highest-impact
  first (vision → users → hard constraints). Research's guesses become
  one-tap confirmations (the assumption is the lead option), every
  question is skippable, and "park the rest" stops the interview with
  everything remaining filed exactly as before. Answers land in the
  correct brain surface cited `(source: intake interview, <date>)`,
  confirmed assumptions get their tag upgraded, and the matching
  open-questions entry moves to a `## Resolved` section — an audit trail,
  not a deletion. Operational notes are never asked, validation-required
  entries (the focus group's "Persona validation") are never resolved by
  the interview, and the brain hard gate still fires — once, after the
  interview. The skill is reachable only through the human-invoked
  `/factory:init` flow; autopilot and dispatch never run it (a coherence
  test guards this), so unattended runs keep the parked-files path
  unchanged. Suite: 431 → 434 tests.

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
