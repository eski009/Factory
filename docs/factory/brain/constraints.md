# Constraints

<!-- Technical, business, and regulatory constraints that bound what can be
     built. Every claim should cite a source: (source: <path-or-url>) -->

- The engine is Python 3 stdlib only — zero third-party dependencies. It lives
  in `scripts/factory/` (a thin `factory.py` CLI over `lib/` modules: machine,
  items, council, dispatch, validate, health, prune, doctor, packet, design,
  initrepo, logs, paths)
  (source: docs/superpowers/specs/2026-07-03-software-factory-design.md §2; scripts/factory/lib/).
- The deterministic engine owns all state and gate checks; AI skills drive it
  but cannot bypass a gate. "Done" requires proof on disk — a spec, a plan
  with tasks, green tests (source: README.md "Under the hood").
- State is strictly split: `.factory/` is machine-owned (work items, council
  ledgers, runs), `docs/factory/` is human-readable (brain, roadmap, packets)
  (source: README.md "Under the hood"; .factory/; docs/factory/).
- No specialist may edit `docs/factory/brain/` directly — every change must
  pass the bid → orchestrator-judgement firewall and is logged with the
  judgement that authorized it (source: README.md "It learns your taste";
  schemas/escalation-bid.schema.json; schemas/orchestrator-judgement.schema.json).
- Work items and ledgers are JSON-schema-validated (`schemas/*.schema.json`);
  `factory validate` audits tree integrity — dir/id match, stage-vs-log,
  ledger id uniqueness, judgement/reputation cross-links
  (source: schemas/; CHANGELOG.md 0.2.0; commit 7ebcbdf).
- Must run on any Claude model; Fable-only features (Workflow tool, forks)
  are opportunistic upgrades, never requirements
  (source: docs/superpowers/specs/2026-07-03-software-factory-design.md §1 Goals; skills/capabilities/).
- `init` is idempotent and only fills gaps — it never overwrites existing
  files, and never modifies product code, CLAUDE.md, or existing docs
  (source: docs/getting-started.md §2; docs/superpowers/specs/2026-07-03-software-factory-design.md §1 Goals).
- Superpowers is a hard companion-plugin requirement; plugin manifests cannot
  yet declare dependencies, so installation of it is on the user
  (source: README.md "Install").
- Testing is `unittest` (216 tests green as of 2026-07-10, post-item-0001;
  updated from 212 per judgement on bid-0012), run via
  `python3 -m unittest discover -s tests`, with CI in
  `.github/workflows/test.yml` (source: tests/; .github/workflows/test.yml;
  docs/factory/brain/decisions.md).
- License: MIT-style single-file LICENSE, author Steve Coulson
  (source: LICENSE; .claude-plugin/plugin.json).
- Simulated/AI-roleplayed output (focus-group interviews, persona
  simulations) is assumption-grade by construction: it must carry a distinct
  citation class (e.g. `(simulated: focus-group run <date>)`), may never be
  written as fact-grade `(source:)`, must be mirrored to open-questions.md,
  and can never resolve the persona-validation open question — otherwise
  circular sourcing corrupts the evidence-firewalled brain
  (source: .factory/items/0001-focus-group-research-structured-intervie/reviews/round-1/engineering-quality.md;
  docs/superpowers/specs/2026-07-06-factory-research-stage-design.md;
  authorized: judgement on bid-0001).
- The item's `log.jsonl` is the single canonical spend record: skills log
  spend events via `factory log`; run-scoped spend.md files derive from it,
  never compete — otherwise spend data forks per skill and aggregation
  undercounts (source: .factory/items/0004-per-item-cost-meter-measure-and-report-t/reviews/round-1/architecture.md;
  scripts/factory/lib/logs.py; authorized: judgement on bid-0017).
- Every reported cost figure carries structural provenance
  (measured | proxy | unmeasured); renderers never merge classes into one
  unlabeled total; UNMEASURED is a loud literal, never zero, a dash, or
  estimated dollars (source: .factory/items/0004-per-item-cost-meter-measure-and-report-t/reviews/round-1/engineering-quality.md;
  skills/factory-research/references/focus-group.md; authorized: judgement on bid-0018).
- External design services (Claude Design MCP, DesignSync) are preferred
  interactive mirrors, never sources of truth: repo files (design-system.md,
  `items/<id>/design/`) stay canonical and cold-resumable; interactive pulls
  mirror tokens into design-system.md through the brain firewall; the
  headless path is always sufficient
  (source: .factory/items/0002-claude-design-mcp-as-the-single-source-o/reviews/round-1/architecture.md;
  skills/capabilities/references/designsync.md; authorized: judgement on bid-0016).
- Every capture path for a design-gate decision (page button, browser-read,
  CLI) must terminate in `factory choice` / `design.record_choice` — nothing
  else may write `design/choice.md`. A second writer would bypass the stage
  and option gates and fork the audit trail
  (source: .factory/items/0003-interactive-decision-pages-clickable-cho/reviews/round-1/engineering-quality.md;
  scripts/factory/lib/design.py; authorized: judgement on bid-0011).
- `kind` (`ui|backend|mixed`) encodes design-gate routing only and must not
  grow new values for orthogonal item traits; traits like `bug` enter
  work-item.schema.json as OPTIONAL boolean fields (absent = falsy), which
  keeps the closed `additionalProperties: false` schema migration-free, and
  their gates use the file+event dual-check pattern existing gates already
  use (source: .factory/items/0010-factory-bug-command-understand-replicate/reviews/round-2/architecture.md;
  .factory/items/0010-factory-bug-command-understand-replicate/reviews/round-2/engineering-quality.md;
  schemas/work-item.schema.json; authorized: judgement on bid-0040).
- Any new multi-agent fan-out step must be opt-in — never added silently to
  a default path or autopilot — and must log its own token/effort spend:
  cost metering is category table stakes, cost-per-item is the brain's top
  open question, and the target persona personally pays the bill
  (source: .factory/items/0001-focus-group-research-structured-intervie/reviews/round-1/commercial.md;
  .factory/runs/research/synthesis.md; authorized: judgement on bid-0002).
