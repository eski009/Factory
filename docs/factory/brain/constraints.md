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
- **Build order: 0025 lands before 0015, with a binding scoping key.** 0025's
  round-scoping key must be "evidence postdates the most recent `stage.advance`
  into implement — any entry, forward or backward", so 0015's redesign path
  (spec→plan→implement is a fresh entry into implement) inherits full gate
  re-scoping with zero 0015-side mechanism — one shared postdating primitive,
  never two. Bundling round-scoping into 0015 is the fallback only if 0025
  cannot be scheduled ahead; 0015's AC4/AC5 must not be claimed before the
  scoping holds. 0025 pays for itself independently: it already owns two live
  shipped defects from 0013's assure walk. **Refined at 0025 triage
  (jdg-0107): "any entry" means any entry whose `from`-stage is not in
  `SPECIAL`.** A `waiting-human`/`blocked` resume returns only to
  `paused-from` (machine.py:454-455), so a SPECIAL→implement edge exists
  only for items parked at implement and provably resets nothing; counting
  it would falsely invalidate `implement.completed` for unchanged code
  after an advisory pause (the bid-0079/0098 miss-path class) and would
  contradict the breaker's round key — cost.py's `REWORK_FROM` already
  ratifies "resumes must not inflate the count". The exclusion is expressed
  via the existing `SPECIAL` set inside the one shared primitive, never
  per-gate from-stage enumeration (source:
  .factory/items/0015-approach-rejected-a-redesign-loop-back-t/reviews/round-2/architecture.md;
  .factory/items/0015-approach-rejected-a-redesign-loop-back-t/reviews/round-2/engineering-quality.md;
  docs/factory/packets/reports/0013-assure-attribution-gate-only-on-regressi-shipped.md;
  .factory/items/0025-round-scope-all-rework-gates-implement-c/reviews/round-2/engineering-quality.md;
  scripts/factory/lib/machine.py; scripts/factory/lib/cost.py;
  authorized: judgements on bid-0096, bid-0107).
- **New gate caps join the engine-edge substrate** (rule instance of bid-0064,
  bound at 0015 triage): `MAX_APPROACH_REJECTIONS` and the `verify -> implement`
  rework cap count engine-written backward `stage.advance` edges — the substrate
  `cost.summarize` already reads, whose `REWORK_FROM` pre-lists verify — never
  skill-logged events. The existing event-counted caps (machine.py:459,462,
  counting skill-logged `review.rejected`/`assure.rejected`, which never fired
  on the ParkSnap run) remain a named live defect no new spec may copy;
  "mirroring review -> implement" in 0015 AC4 means edge shape, not count
  substrate. Guard tests red-first in the failing form against the production
  advance path (source:
  .factory/items/0015-approach-rejected-a-redesign-loop-back-t/reviews/synthesis.md;
  scripts/factory/lib/machine.py; scripts/factory/lib/cost.py;
  authorized: judgement on bid-0097).
- **An engine-auto-written cost-answer is a pause-consuming miss-path** (refines
  the bid-0065/0079 contracts): breaker coverage is `answered_at >= edges`
  (breaker.py:100-106) and the breaker fires on the next advance into
  implement, so a post-redesign spec→plan→implement entry is exactly where an
  owed uncovered-spend pause surfaces — an auto-answer written by any
  transition (e.g. an `approach.rejected` edge recording its own coverage)
  would silently consume that pause. Redesign cost-answer coverage comes from
  an operator-recorded answer or a bid-0065-contracted pause, never an
  engine-auto-written answer; and breaker `rework_edges` is cumulative spend,
  never reset by a redesign (source:
  .factory/items/0015-approach-rejected-a-redesign-loop-back-t/reviews/round-2/engineering-quality.md;
  .factory/items/0015-approach-rejected-a-redesign-loop-back-t/reviews/round-2/architecture.md;
  scripts/factory/lib/breaker.py;
  authorized: judgement on bid-0098).
- **A postdating migration covers every postdating site, or "one shared
  primitive, never two" ships false** (instance extending bid-0064/0096,
  bound at 0025 triage): the sites are not only the three entry gates —
  `_gate_ship`'s main key is skill-logged `implement.completed`
  (machine.py:407); `_gate_ship`'s `journeys == "none"` early-return
  (machine.py:403-405) checks a lifetime `verify.green`, so left untouched
  a journeys-none item still ships on a prior round's verification of
  different code (silent exclusion is a bid-0054 waiver); and
  `assure.py:42` (`record_confirmation`) independently compares
  `assure.passed` against skill-logged `implement.completed`. 0025's spec
  must enumerate every postdating comparison and route all through the one
  shared helper (source: scripts/factory/lib/machine.py;
  scripts/factory/lib/assure.py;
  .factory/items/0025-round-scope-all-rework-gates-implement-c/reviews/synthesis.md;
  authorized: judgement on bid-0108).
- **A refusal that names an answer verb must also reach the packet.** The
  five-part `waiting-human` pause contract (bid-0065) assumes the park
  happens; it does not require the *refusal* to mention the decision screen.
  Both answerable pauses shipped so far fail that way: the engine refuses and
  names its verb (`factory approach-answer`, `factory cost-answer`) while
  parking and packet rendering are a separate `factory-dispatch`-issued
  advance. An operator who follows the refusal's own instruction literally
  reaches the commitment point — authorising a further item's worth of
  unwatched spend — with the tradeoff screen never rendered. Everything the
  J-003/J-002 contracts build at their decision node hangs on dispatch
  interposing. Second instance of the bid-0079 miss-path shape (a session
  death between firing and park reaches the same place by another route), so
  it is a pattern: any refusal naming an answer verb must name the packet
  too, or the engine must park itself (source:
  .factory/items/0015-approach-rejected-a-redesign-loop-back-t/assurance/transcripts/J-003/S2.txt,
  S7.txt; authorized: judgement on bid-0119).
- **An acceptance criterion that names a repo artifact must be satisfied by
  something the merge carries.** Nothing in the pipeline guarantees that
  journey-registry artifacts required by an item's ACs are committed: 0015's
  AC21 requires a J-003 entry in `graph.json`, its `inventory.md` line and its
  contract file, and at review time the contract was *untracked* on main with
  the other three modified-but-uncommitted — none of them on the branch. Assure
  walked a contract the merge would not carry, and two review seats contradicted
  each other purely because one read the worktree and one read main. Ship must
  verify AC-named artifacts are committed, or the AC ships unmet (source:
  .factory/items/0015-…/reviews/round-3/walk.md; authorized: judgement on
  bid-0122).
- **A trigger must be calibratable on the corpus that motivates it.** If the
  motivating case is external and unlogged, the threshold is fitted to an
  anecdote — asserted, not calibrated. 0018 proposed a wall-clock breaker arm
  whose AC2 required firing at 9,499s (0016's first implement pass) while
  0015's first implement pass is 10,046s and 0015 shipped clean: every
  threshold `T ≤ 9,499` is also `< 10,046`, so AC2 and a zero-false-positive
  threshold are *jointly unsatisfiable*, arithmetically. Re-denominating to
  tokens does not help — 0015's measured 4,011,314 exceeds 0016's 3,949,630,
  so the corpus holds no separable outlier on any dimension, and the ParkSnap
  run that motivated the batch is external and in no log here. Run the
  calibration replay **at triage**, before the ACs are accepted: it is cheap,
  and on this item it converted a unanimous `build-rescoped` into a unanimous
  refusal (source:
  .factory/items/0018-wall-clock-trigger-arm-catch-the-spend-r/triage.md,
  reviews/synthesis.md; authorized: judgement on bid-0131).
- **Engine-authoritative is not the same as meaningful.** bid-0064 governs who
  *writes* the event; bid-0018 governs what the *figure means*. Passing the
  first says nothing about the second, and bid-0064's success has made it read
  as a sufficient test for a trigger substrate when it is only a necessary one.
  `cost.summarize`'s `active_seconds` is impeccable on the first axis and fails
  the second: `WAITING_STAGES` is `frozenset(machine.SPECIAL)` =
  `{blocked, waiting-human}` only, so every other gap — sleep, session death,
  closed laptop, rate limit — books to whichever stage the item was sitting in.
  0015's `review` bucket reads 7.49h from a single 25,145s overnight gap; the
  top eleven items by `active_seconds` are unstarted `idea` filings while 0016,
  the genuinely expensive item, ranks 12th. For the Overnight Operator, "the
  loop is burning money" and "I went to bed" are the same number on this
  substrate (source: scripts/factory/lib/cost.py;
  .factory/items/0018-…/reviews/synthesis.md; authorized: judgement on
  bid-0132).
- **A gate with no per-arm disable is a single gate.** Adding a noisy arm
  degrades the working one and invites a wholesale disable — trading a working
  control for no control. `_config_gates` reads a flat list of strings
  (`machine.py:232-236`) with `"cost"` a single entry, and `REWORK_THRESHOLD`
  is a module constant with no override path, so there is demonstrably no way
  to silence a second arm without removing the first. Any proposal to add an
  arm to an existing gate ships a per-arm off-switch and a per-arm threshold
  override in the same change, or it is not additive (source:
  scripts/factory/lib/machine.py;
  .factory/items/0018-…/reviews/synthesis.md; authorized: judgement on
  bid-0133).
- **Factory has no in-stage work meter, and no engine-authoritative quantity
  can become one.** The engine-authoritative set is exactly the `stage.advance`
  derivations — `advances`, per-stage `entries`, `rework_edges`,
  `approach_edges` — and every one counts *transitions*, so all read zero for a
  stage occupancy that never ends. `dispatches` does measure work but
  accumulates only from skill-logged `spend` events (`cost.py:145-159`, present
  in 12 of 28 logs), failing the bid-0064 substrate test. The corollary bounds
  every future cost control: `breaker.verdict` is computed only *after* an
  accepted transition (`machine.py:668-684`) and no mid-stage hook exists, so a
  single-pass runaway makes **zero transitions while it burns** and the earliest
  any arm can fire is the advance *out of* the stage that already spent the
  money. "Catches the runaway" is unachievable in principle on today's
  substrate; the honest claim is "stops the next stage of an already-expensive
  item" (source: scripts/factory/lib/machine.py, scripts/factory/lib/cost.py;
  .factory/items/0018-…/reviews/synthesis.md; authorized: judgement on
  bid-0134).
- **A mechanically passable AC set is a liability when the mechanism is
  unsound.** A green suite converts an unfounded threshold into recorded
  evidence of correctness — which is exactly what a later item cites to skip
  re-checking the property. This is bid-0083's false-stronger-contract failure
  in its most expensive form, and 0018 carried both halves: AC3 pinned
  `waiting-human`, the one case the code already excludes, so a test written to
  it passes by construction; and AC2 was satisfiable only by a threshold that
  parks healthy work, so *a passing AC2 test would itself be evidence of a
  defect*. Ask at triage whether a wrong implementation could make the AC set
  green, and treat yes as a finding about the mechanism, not about the tests
  (source: .factory/items/0018-…/triage.md, reviews/synthesis.md; authorized:
  judgement on bid-0135).
- **The selector that names a pause's answer verb must be reason-keyed, and
  every reason-prefix arm must precede every stage-keyed arm.** A stage-keyed
  arm that shadows a reason-keyed one does not merely fail to name the verb —
  it names a verb from a *different* pause contract. Live shape:
  `packet.respond_action_lines` orders `paused_from == "assure"`
  (`packet.py:327`) above the cost-breaker arm (`:331`), and `assure` is in
  `cost.REWORK_FROM` (`cost.py:26`), so a cost pause parked from `assure` would
  be answered with `factory waive` — which `assure.py:14-20` admits and
  `machine.py:584-585` treats as authoritative, shipping the item on an
  unanswered spend gate. Extends the five-part pause contract (bid-0065): the
  contract requires the packet to name *the* verb, and ordering is what decides
  *which* verb it names (source: scripts/factory/lib/packet.py,
  scripts/factory/lib/cost.py, scripts/factory/lib/assure.py,
  scripts/factory/lib/machine.py; .factory/items/0027-…/reviews/synthesis.md;
  authorized: judgement on bid-0137).
- **Cross-item token comparisons are not measured evidence.** bid-0063's nested
  double-count means no aggregate is trustworthy in either direction until 0029
  lands, and the one real comparison inverts (0015's 4.01M against 0016's
  3.95M). An item body arguing "a line-sized fix pays a full pipeline
  round-trip" from item totals is citing a number, not evidence; 0027, 0028 and
  0031 carried zero spend events between them when that claim was written. The
  defensible figure is **within-item**: the avoided council fan-out (265,776 of
  0025's 794,702 tokens; 2,178,549 on 0015). Restate such a premise as a proxy
  claim or mark it UNSOURCED. Extends the provenance rule (bid-0018) (source:
  docs/factory/brain/decisions.md:470-475,
  .factory/items/0027-…/reviews/round-1/commercial.md; authorized: judgement on
  bid-0140).
- **A declared assurance scenario is a contract, and inherits the
  false-stronger-contract rule.** An `assurance/impact.json` scenario that
  generalises beyond the population its own fixtures can construct is a false
  assurance in the bid-0083 sense, and it is discovered at **assure** — the most
  expensive place to discover anything. 0027's S5 asserted that "no
  `factory cost-answer` … bullet renders on **any** packet whose corresponding
  decision section is empty, **in either renderer**"; an item advanced
  `plan → blocked` with a `cost breaker:` reason falsifies it in both renderers,
  because `packet.py:96`/`:98` gate the screen on stage **and** prefix while
  `:361` gates the verb on prefix alone, and `park_matrix_fixture` cannot build a
  `blocked` park at all. Scenario wording must name the population the fixtures
  actually establish, and name an uncovered state as uncovered rather than
  asserting over it (source:
  .factory/items/0027-…/reviews/round-1/product.md,
  .factory/items/0027-…/assurance/impact.json, scripts/factory/lib/packet.py,
  tests/test_packet.py; authorized: judgement on bid-0144).
- **`tier` and `bug` are deliberately orthogonal and must never be coupled.**
  `tier` is a **materiality** claim; `bug` is an **evidence** claim. The split is
  documented inline in shipped engine code — `scripts/factory/lib/assure.py:63-65`
  (from 0013 §7): *"Filed items are stage idea, kind backend, tier bug, with NO
  priority … and NO 'bug' flag (setting it would engage `_gate_plan`'s repro gate
  on an item nobody replicated)"* — and restated at `skills/factory-bug/SKILL.md:23`.
  Coupling them, at write time or as a read-time derivation, would give
  `bug: true` two contradictory semantics in one codebase, because engine-filed
  defects (`assure.file_base_defect`) bypass `cmd_add` entirely — so the flag
  would come to mean "arrived via a particular door," the bid-0083
  false-stronger-contract shape pointed the other way. Live counterexample:
  **0023** is `tier: bug` and is an omnibus of ~15 furniture advisories with no
  single failing command; fail-closed arming strands it permanently behind
  `_gate_plan` (`machine.py:529-533`), which has no waiver path. Bound rule:
  `/factory:bug` sets **both** fields (it confirms a repro, which is what makes
  the flag evidence); `factory add --tier bug` sets **tier only** and *routes*
  (source: scripts/factory/lib/assure.py; skills/factory-bug/SKILL.md;
  .factory/items/0026-…/reviews/round-2/architecture.md; authorized: judgement on
  bid-0149).
- **The tier depth table is published, not consumed.** `tiers.profile()`
  (`tiers.py:25-42`) has exactly one non-test caller — `doctor.py:63` — which only
  **prints** it. All three knobs (`research`, `review`, `assure`) are honoured by
  agents on trust, with no receipt: `grep -n depth .factory/items/*/log.jsonl`
  returns **zero matches across all 32 items**. Any depth mechanism this product
  ships is therefore an unenforced promise until an engine-written recorder
  exists, and bid-0131's calibration-replay test is **unsatisfiable**, not merely
  thin-corpus (source: scripts/factory/lib/tiers.py; scripts/factory/lib/doctor.py;
  .factory/items/0026-…/reviews/synthesis.md; authorized: judgement on bid-0150).
- **Triage spend is unlogged, so `factory cost` under-reports by a whole council
  fan-out, unmarked.** 0027's `log.jsonl` carries no `spend` event with
  `"stage": "triage"`, yet 11 reviewer files under `0027/reviews/triage/` prove a
  two-round six-seat council ran; `factory cost 0027 = 1,181,397` silently
  excludes it. A bid-0018 provenance violation on the one readout the bill-payer
  opens, and a **known-direction** bias in the only cost series the product has —
  inherited by 0029, 0030 and every bid-0140 within-item comparison. 0026's
  triage logged the corpus's first `"stage": "triage"` spend event; the general
  fix (log it, or render UNMEASURED) is owed (source:
  .factory/items/0027-…/log.jsonl; .factory/items/0026-…/reviews/round-2/customer.md;
  authorized: judgement on bid-0152).
- **Seat count is not the cost driver; failure and retry are, by ~11x.**
  Within-item only (bid-0140): a `council-review` instance that **malfunctioned
  and produced no synthesis** cost **1,499,591** tokens
  (`0015/log.jsonl` L20 — 68.8% of that item's review stage), while the
  **complete 9-seat fan-out** cost **135,475** (L34, 6.2%). 0027's much-cited
  403,895-token assure is **100% round-2 pool-exhaustion rework at the `node`
  depth floor** (`0027/log.jsonl` L29-30: `provenance: proxy`, `dispatches: 0`,
  `assure.degraded` with `"independence": "NOT MET - subagent pool exhausted
  200/200"`), not a consequence of depth. **Any argument for narrowing depth or
  cutting seats must first show the spend it targets is not retry spend.** 0026
  was filed on the opposite intuition and rescoped when this was measured
  (source: .factory/items/0015-…/log.jsonl; .factory/items/0027-…/log.jsonl;
  .factory/items/0026-…/reviews/synthesis.md; authorized: judgement on bid-0153).
- **Two shipped narrowing mechanisms sit at zero adoption — build no third before
  one of them fires once.** `grep -h "^bug:" .factory/items/*/item.md` = **0** of
  32, so `_gate_plan`'s repro branch (`machine.py:529-533`) has never fired and no
  `repro.md` exists anywhere; `journeys: none` — the only engine-authoritative
  stage-dropping lever (`machine.stage_sequence`, `machine.py:61-68`) — is likewise
  **0**. The gap is documentation-and-door, not engine: `factory add --tier`
  already exists (`factory.py:481`, applied `:47-48`) while `commands/add.md` is
  7 lines mentioning neither `tier` nor `bug`, and `factory-triage/SKILL.md:25`
  asserts bugs are "usually filed via `/factory:bug` already carrying `tier: bug`"
  — an assumption that is **0-for-9** (source: scripts/factory/lib/machine.py;
  commands/add.md; .factory/items/0026-…/reviews/round-1/engineering-quality.md;
  authorized: judgement on bid-0154).
- **An absence marker must key on the event's presence, not on one provenance
  class of it.** `cost.render_receipt` fires `(no spend events logged)` on
  `bucket["measured"] is None`, but `cost.summarize` populates `measured` only
  for `provenance: "measured"` — a proxy event increments `proxy_events` and
  leaves `measured` at `None` (`cost.py:176-177`). So the proxy write that
  0026's own `skills/factory-bug/SKILL.md` step 7.3 mandates unconditionally is
  invisible to the marker, and on an item that never entered the triage *stage*
  that same write is what **creates** the bucket that makes the "no spend events
  logged" line appear: logging causes the line that says you did not log.
  Reproduced by execution on a fixture repo — packet rendered the marker while
  `log.jsonl` held a `provenance: "proxy"`, `stage: "triage"` spend event and the
  bucket read `{'measured': None, 'proxy_events': 1}`. The same sentence carries
  the same flaw at `cost.render_text:262-263`, which predates the branch (source:
  .factory/items/0026-…/reviews/round-1/engineering-quality.md;
  .factory/items/0026-…/reviews/round-2/commercial.md;
  .factory/items/0026-…/reviews/synthesis.md; authorized: judgement on bid-0165).
- **An acceptance criterion that asserts a hand-built fixture's *shape* instead
  of the producing function's *behaviour* will let the next population bug
  through exactly as it let this one through.** 0026's `TriageUnmeasuredLineTest`
  hand-builds the cost summary dict with `"proxy_events": 0` in all four cases
  and never calls `cost.summarize`; AC21 codified the same weaker predicate. The
  suite was 965-green while the promise failed on the default path. No
  dict-level test can catch a bug in how `summarize` *populates* the key, which
  was the entire defect — an AC over a renderer must name the producing function
  in the path under test (source:
  .factory/items/0026-…/reviews/round-1/engineering-quality.md;
  .factory/items/0026-…/reviews/synthesis.md; authorized: judgement on bid-0166).
- **A stage-membership key must be immutable for the item's life, or
  door-keyed — never a mutable frontmatter field.** `tier` fails both tests and
  cannot govern stage membership. Ordering: `factory-triage/SKILL.md` dispatches
  the council at **step 2** and sets `tier` at **step 6**, while `machine.py`
  computes `next_stage(meta)` from current frontmatter — so a tier-conditional
  sequence can only drop stages at or after `spec`, and can never reach the
  triage cost it would be built to cut. Mutability: `next_stage`
  (`machine.py:70-81`) falls back to `stage_sequence(meta["kind"])` alone when
  the current stage is absent from the item's own sequence, discarding the
  `journeys` filter and any new filter identically, and `cmd_tier`
  (`factory.py:433-441`) lets `tier` change at any stage — so an item re-tiered
  at `assure` re-acquires the full sequence, advances to `ship`, and strands
  `_gate_ship`, whose substitution is keyed on `journeys`, not `tier`
  (`machine.py:568`). **Two keys on one gate is the defect shape.** The shipped
  conditional drops (`design` on `kind`, `assure` on `journeys`) are sound
  because both keys are declarations, not depth dials. Amends bid-0042 and
  bid-0151 (source: scripts/factory/lib/machine.py; scripts/factory/factory.py;
  skills/factory-triage/SKILL.md; authorized: judgement on bid-0176).
- **A verified-but-unshipped branch that publishes a claim about system
  behaviour is a live copy dependency of any later item that changes that
  behaviour.** 0026's spec rewrites `README.md:96` to read verbatim "Stage
  membership never changes: a defect still passes review, verify and assure",
  built and green at `687c1a1`, and `0026/spec.md:509-511` makes that sentence a
  **test-asserted** acceptance criterion. 0033 drops `assure` for bugs, which
  falsifies it — so if 0033 ships first, 0026's own green test pins a false
  claim, and neither branch's gates can see the other. **Whichever ships second
  must carry the other's copy edit**, and the check belongs at ship, not in
  either item's review. Separately owed: `0026/spec.md:22-27` states the
  now-disproven "100% pool-exhaustion rework" as fact and builds a prohibition on
  it; a verified-but-unshipped spec should not merge carrying a disproven claim
  (source: .factory/items/0026-…/spec.md; README.md;
  .factory/items/0033-…/reviews/triage/synthesis.md; authorized: judgement on
  bid-0177).
