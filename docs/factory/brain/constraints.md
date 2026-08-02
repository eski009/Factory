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
- Any gate, cap, or breaker must derive its trigger from events the engine
  writes unconditionally — `stage.advance`, appended by `machine.advance()`
  itself — never from skill-logged evidence events. `review.rejected` and
  `assure.rejected` are written only by convention and merely read by the
  engine, so a check built on them silently does not fire in exactly the runs
  where it matters most. **The existing rework caps are a live instance, not a
  hypothetical:** on the 2026-08-02 ParkSnap run they never fired and the engine
  never noticed (source: scripts/factory/lib/machine.py:279-296;
  skills/factory-review/SKILL.md:16; skills/factory-assure/SKILL.md:12,80;
  .factory/items/0016-cost-circuit-breaker-on-engine-authorita/reviews/round-2/architecture.md;
  authorized: judgement on bid-0064).
- Every `waiting-human` pause ships with five things or it is a trap: a named
  answer verb, the artifact that verb writes, an engine precondition that reads
  the artifact, a `factory-dispatch` resume clause, and a packet naming the
  verb. The resume branch applies no gate — it checks only that the destination
  equals `paused-from` — so a park with no recorded answer returns the item to
  the stage that just parked it and re-parks immediately. `packet.py`'s generic
  "run `/factory:run` to resume" is correct only for pauses that need no answer;
  `design/choice.md` is the working model to copy (source:
  scripts/factory/lib/machine.py:270-278; scripts/factory/lib/packet.py:170-177;
  scripts/factory/lib/machine.py:196;
  .factory/items/0016-cost-circuit-breaker-on-engine-authorita/reviews/round-2/customer.md;
  authorized: judgement on bid-0065).
- The provenance rule extends from reported figures to **derived statistics**: a
  median, baseline, multiplier, or per-tier average is never rendered when its
  population cannot supply it — an empty or unrepresentative population reports
  UNMEASURED, not a number. Verified instances: all nine `done` items predate the
  `tier` field, so every per-tier median bucket is empty; and exactly 2 of 17
  items have ever had a rework edge (one each), so any "typical rework" baseline
  would be fabricated (source:
  .factory/items/0016-cost-circuit-breaker-on-engine-authorita/reviews/round-2/product.md;
  authorized: judgement on bid-0066).
- **Skill produces proof; engine validates proof.** For any evidence produced
  by driving a running product, the engine asserts shape, presence, sha-match
  and non-emptiness only — never the truth of the walk. `machine.py` launches
  nothing (its sole subprocess call is `git rev-parse`, line 216), so any
  acceptance criterion demanding the engine determine a behavioural fact
  "without a human or reviewer asserting it" is unachievable and must be
  restated as this boundary — with the residual hole (evidence copied into the
  proof directory passes every engine check) named in plain words
  (source: scripts/factory/lib/machine.py;
  .factory/items/0013-assure-attribution-gate-only-on-regressi/reviews/round-1/architecture.md;
  authorized: judgement on bid-0053).
- **Re-routing, not waiving:** every failure the system observes but does not
  block on must terminate in a required, validated, deduped, open work-item
  id — never a free-text note, never silence. An unvalidated id is a waiver
  wearing a filing's clothes; an undeduped auto-filing makes the backlog the
  new place nothing surfaces. Neither existing surface fits: packets/reports/
  is assure's non-nagging home, hooks/session-start.sh globs only top-level
  packets, and escapes.py's closed MISS_TYPES enum is scoped to post-assurance
  human finds (source: scripts/factory/lib/escapes.py; hooks/session-start.sh;
  .factory/items/0013-assure-attribution-gate-only-on-regressi/reviews/round-2/customer.md;
  authorized: judgement on bid-0054).
- **Opt-in means trigger-side and engine-observable** (refines the bid-0002
  constraint): an optional output field secures the schema, not the bill. A
  new fan-out step is genuinely opt-in only when the engine rejects
  unsolicited evidence objects and ignores the optional field entirely when
  the feature is off, and the config key carries an explicit stated default in
  `initrepo.py`'s DEFAULT_CONFIG rather than being opt-in by accident of
  nobody setting it (source: scripts/factory/lib/initrepo.py:20;
  .factory/items/0013-assure-attribution-gate-only-on-regressi/reviews/round-2/commercial.md;
  authorized: judgement on bid-0055).
- **A guard test is trusted only when shown red in the form the defect
  actually takes, against the production path.** A pattern that cannot match
  the failing form converts an unverified claim into a claimed-verified one —
  worse than no test (instance: the AC11 `rework edges: \d` filter never
  matched the `2 rework edges` receipt form; fixed by REWORK_FIGURE_RE
  matching both). And red demonstrated against a hand-built fixture is not
  red: pass 1 honoured red-first to the letter and still let B3 through
  because the fixture reached waiting-human via `items.save_item` instead of
  `machine.advance(..., reason=...)` (source: tests/test_packet.py;
  .factory/items/0016-cost-circuit-breaker-on-engine-authorita/reviews/synthesis.md;
  authorized: judgements on bid-0076, bid-0082).
- **Incomparable must not be encoded as zero** (extends the bid-0066
  derived-statistics rule from empty populations to incommensurable ones): a
  population that cannot supply a comparison must not be rendered as the
  number 0. Instances: `breaker.backlog_counts` collapsed "this item has no
  priority, so nothing was compared" into `at_or_above=0` rendered as
  "nothing else is waiting" while items were waiting; `cost.summarize_all`'s
  coverage denominator silently excluded unreadable items; and the
  recommendation sentence read the unqualified population even where the
  backlog line qualified it (fixed at d347434) (source:
  .factory/items/0016-cost-circuit-breaker-on-engine-authorita/reviews/synthesis.md;
  authorized: judgements on bid-0077, bid-0085).
- **A pause whose answer does not change stage needs a packet-clearing rule at
  answer-record time.** The five-part waiting-human contract (bid-0065) misses
  the case where the recorded answer deliberately leaves the item parked:
  `breaker.record_answer` never touches stage and packet deletion happens only
  on a successful resume advance, so a `narrow`/`defer` answer leaves
  session-start announcing an already-answered packet forever. A sweep keyed
  on "no longer waiting-human" cannot fix it; deletion must happen when the
  answer is recorded (source: scripts/factory/lib/breaker.py:118-141;
  .factory/items/0016-cost-circuit-breaker-on-engine-authorita/reviews/synthesis.md;
  authorized: judgement on bid-0078).
- **A contract stronger in form but false in fact is worse than the loose one
  it replaced.** Silence under-promises; a false assurance is load-bearing,
  because it is what a future item cites to skip re-checking the property
  (source: .factory/items/0016-cost-circuit-breaker-on-engine-authorita/reviews/round-2/customer.md;
  authorized: judgement on bid-0083).
- **Free text on a control-flow path needs a guard or a derivation.**
  `packet.py` gates the entire "## Cost decision" block (and the waiting
  line's rework rewrite) on `paused-reason.startswith(PAUSE_PREFIX)`:
  agent-authored free text is load-bearing for control flow, not just for a
  rendered digit, and no fixture varies it
  (source: scripts/factory/lib/packet.py:48-70;
  .factory/items/0016-cost-circuit-breaker-on-engine-authorita/reviews/round-2/engineering-quality.md;
  authorized: judgement on bid-0086).
- The canonical-spend-sink convention is honoured on **9 of 17 items** (0002,
  0003, 0004, 0007, 0008, 0009, 0010, 0012, 0013 have spend events; 0001, 0005,
  0006, 0011, 0014–0017 have none) and on a minority of transitions within them —
  0013 logged 2 events for an entire spec plus triage. This is the empirical case
  for engine-derived triggers: the convention is real, documented, and unevenly
  followed, so anything gating on it inherits the gaps (source:
  .factory/items/0016-cost-circuit-breaker-on-engine-authorita/reviews/round-1/commercial.md;
  recount over .factory/items/*/log.jsonl; authorized: judgement on bid-0068).
