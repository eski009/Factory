# Decisions

<!-- Record of decisions made and why, so later work doesn't relitigate them.
     Every claim should cite a source: (source: <path-or-url>) -->

- **Succeed superpowers-council rather than extend it.** Keep the proven
  council/memory layer (bounded protocol, firewall, reputation, packets) and
  add the execution pipeline it lacked
  (source: docs/superpowers/specs/2026-07-03-software-factory-design.md §1).
- **Deterministic Python engine + AI skills split.** A zero-dependency script
  enforces gates and owns state so skills can drive but never bypass checks
  (source: README.md "Under the hood"; docs/superpowers/specs/2026-07-03-software-factory-design.md §2).
- **Exactly one default human gate: design.** Config `gates: ["design"]`;
  the autonomy dial can add or remove gates. Backend-only items skip design
  (source: .factory/config.json; README.md "How it works").
- **Depend on Superpowers instead of vendoring execution discipline** —
  TDD, systematic debugging, verification, worktrees come from the companion
  plugin (source: README.md "Install"; docs/getting-started.md §1).
- **All state as diffable files** (markdown + JSON + JSONL) so any session on
  any model can resume any item cold
  (source: docs/superpowers/specs/2026-07-03-software-factory-design.md §1 Goals).
- **Reputation ranks attention, never censors** — a low score never silences
  a council claim (source: README.md "It learns your taste").
- **Brownfield intake added in 0.2.0**: detect existing product code and mine
  it (routes, tests, tooling config) plus a human taste packet, instead of
  seeding from a blank scaffold (source: CHANGELOG.md 0.2.0; commit 0848883).
- **Research stage added at initiation (Phase 8)**: `factory-research` seeds
  personas.md and market.md at configured depth
  (`research.depth: inputs-only|web|deep`, default `web`); spec and design
  stages reason against the persona
  (source: docs/superpowers/specs/2026-07-06-factory-research-stage.md;
  commits be04151, 92d7990, c692b49).
- **Merge policy defaults to auto** once review/verify pass
  (source: .factory/config.json "merge": "auto").
- **Roadmap flow reconciles with council batch triage** and guards priority
  ints; priority is engine-managed via `factory priority <id> <n>`
  (source: commits 28663dd, 2161cb2; CHANGELOG.md 0.2.0).
- **2026-07-10, triage of 0001:** constraints.md gained the synthetic-evidence
  firewall rule (judgement on bid-0001) and the fan-out cost-containment rule
  (judgement on bid-0002); design-system.md gained the packet house style
  (judgement on bid-0003). Item 0001 approved to build at priority 1 as a
  skill-layer extension of factory-research; 0003 set to priority 2, 0002 to
  priority 3; council proposed item 0004 (per-item cost meter)
  (source: .factory/items/0001-focus-group-research-structured-intervie/triage.md).
- **2026-07-10, spec of 0001:** open-questions.md gained the config
  extension-point question (judgement on bid-0004) and the spend-measurement
  mechanism note merged into the cost entry (judgement on bid-0005); three
  further spec brain-gaps deferred to ledger history (bids 0006–0008). The
  focus-group opt-in is CLI-argument-gated, not config-gated, because the
  config schema is closed (source:
  .factory/items/0001-focus-group-research-structured-intervie/spec.md).
- **2026-07-10, review of 0001:** council approved unanimously (no high
  findings); open-questions.md gained the §4 citation-class seam (judgement
  on bid-0009) and the per-skill references/coherence-test seam (judgement on
  bid-0010). Verify must exercise ACs 15–16 with a real `--focus-group` run;
  ship carries a CHANGELOG note that `deep` now includes the focus group
  (source: .factory/items/0001-focus-group-research-structured-intervie/reviews/synthesis.md).
- **2026-07-10, shipped 0001** (mode: auto, ref: a682d9b): focus-group
  research step merged to main — factory-research §3b, reference templates,
  --focus-group/--no-focus-group flags, 216-test suite green on the merged
  tree; verified 16/16 acceptance criteria including a real 4-persona run
  (source: .factory/items/0001-focus-group-research-structured-intervie/verify.md).
- **2026-07-10, triage of 0003:** council unanimous build at priority 2; kind
  corrected ui → mixed; binding scope: design gate only, single-writer funnel
  through record_choice, none-of-these routes back to regeneration,
  zero-network page stays baseline, browser-read as capability upgrade, no
  local server in v1. constraints.md gained the choice single-writer rule
  (judgement on bid-0011) and the corrected 216-test count (judgement on
  bid-0012); follow-up item 0005 filed (generalize to all waiting-human
  packets) (source: .factory/items/0003-interactive-decision-pages-clickable-cho/triage.md).
- **2026-07-10, triage of 0002:** build rescoped — the "single source of
  design truth" framing rejected unanimously; repo files stay canonical with
  Claude Design MCP as preferred interactive mirror (constraint added,
  judgement on bid-0016). Kind corrected mixed → backend; priorities:
  0004 → 3, 0002 → 4 (build waits behind the cost meter); design-polish
  split to item 0006 (source: .factory/items/0002-claude-design-mcp-as-the-single-source-o/triage.md).
- **2026-07-10, triage of 0004:** unanimous build at priority 3, kind backend.
  constraints.md gained the spend canonical-sink rule (judgement on bid-0017)
  and the spend-provenance rule (judgement on bid-0018). v1 = spend events in
  log.jsonl + read-side aggregation + packet receipts; caps/dollars/estimates
  cut (source: .factory/items/0004-per-item-cost-meter-measure-and-report-t/triage.md).
- **2026-07-10, shipped 0004** (mode: auto, ref: 7bad3fd): per-item cost
  meter merged — factory cost, spend events + schema + validate hook, packet
  receipts, status --json spend, skill spend-logging conventions. Review
  round 1 rejected (receipt zeroed total-only tokens); rework fixed at root
  (_token_segments); round 2 approved 6/6; verify 12/12 with 253 tests and a
  real 1.38M-token measured log on the item itself. Follow-up item 0007
  filed (tolerant log reading)
  (source: .factory/items/0004-per-item-cost-meter-measure-and-report-t/verify.md).
- **2026-07-11, shipped 0002** (mode: auto, ref: edf1f20): claude-design
  mirror merged — DesignSync made concrete (tool family, link flow, firewall
  token mirror, best-effort pushes at options/choice/ship, proxy spend at
  every round-trip); council approved 6/6, verify 12/12 at 258 tests.
  Follow-up 0008 filed (divergence guard, packet provenance disclosure,
  placeholder supersession)
  (source: .factory/items/0002-claude-design-mcp-as-the-single-source-o/verify.md).
- **2026-07-11, batch triage (0005–0008):** 0007 tolerant log reading builds
  now at priority 5 (unanimous; the corrupt-line crash reaches packet
  rendering and the stage machine's gated advances, not just cost/status);
  0008 design-mirror refinements at priority 6 (three one-line prose fixes,
  each with a pinned test); 0005 blocked pending 0003 shipping + one real
  gate use; 0006 blocked pending the design-polish skill being probe-able
  outside the owner's environment
  (source: .factory/runs/triage-batch-2026-07-11/synthesis.md).
- **2026-07-11, shipped 0007** (mode: auto, ref: 7fd449f): tolerant log/ledger
  reading merged — single-boundary skip with loud counts on every surface,
  gates fail closed, corruption-safe ledger ids, validate flags invalid UTF-8
  instead of crashing. Council 6/6; two review-driven addenda folded in
  during implement; verify 15/15 at 286 tests with a live corrupted-repo
  walk. Follow-up 0009 filed (never-bricks completion)
  (source: .factory/items/0007-tolerant-log-reading-corrupt-log-jsonl-l/verify.md).
- **2026-07-11, shipped 0008** (mode: auto, ref: 5f5e9fd): design-mirror
  refinements merged — divergence guard, packet token-provenance disclosure
  (incl. rejected bids), placeholder supersession; 6/6 council (three seats
  confirmed their own 0002 prescriptions resolved); 289 tests. Future-touch
  notes recorded in the synthesis, gated behind the first real designsync
  link (source: .factory/items/0008-design-mirror-refinements-pull-bid-diver/verify.md).
- **2026-07-11, shipped 0009** (mode: auto, ref: fd84dd2): never-bricks
  completion merged — encoding refusals with strict core preserved, ledger
  required-key filter with the id-floor invariant pinned, status corruption
  notice, count-after-label copy. Review round 1 rejected (the item's own
  CTA routed users into validate shapes it mishandled); rework closed the
  loop; round 2 approved by the finding's author; verify 9/9 at 308 tests
  with two live corrupted-repo walks. Residual corners recorded in
  open-questions (judgement on bid-0037)
  (source: .factory/items/0009-finish-the-never-bricks-promise-crash-pr/verify.md).
- **2026-07-11, shipped 0003** (mode: auto, ref: c69298c): interactive
  decision pages merged — engine admits none; three-way design entry branch
  with capped regeneration; Option A (the human's pick) encoded as binding
  template requirements; dispatch guards; browser-read capability. Council
  6/6; verify 22/22 at 322 tests including live-browser runtime checks and
  an executed none round-trip. Refinement list for 0005 recorded (judgement
  on bid-0038). 0005's unblock condition is now half-met (0003 shipped);
  one real gate use remains
  (source: .factory/items/0003-interactive-decision-pages-clickable-cho/verify.md).
- **2026-07-11, triage of 0010:** council unanimous build at priority 8,
  kind backend; binding scope: thin intake layer (`commands/bug.md` +
  `factory-bug` skill) over existing stages, replication-first with
  `repro.md` + `repro.confirmed` and a v1 engine-level `_gate_plan` repro
  gate on an optional `bug` schema flag; replication failure hard-stops;
  intake mandatorily seeds repro-passes + regression-test acceptance
  criteria; visual-repro harness deferred to v2. market.md gained the
  bug-domain wedge corollary (judgement on bid-0039); constraints.md gained
  the kind-vs-flag axis rule (judgement on bid-0040). Item 0011 rejected as
  duplicate of 0010
  (source: .factory/items/0010-factory-bug-command-understand-replicate/triage.md).
- **2026-07-11, spec of 0010:** spec written by spec-writer dispatch; six
  brain gaps recorded — open-questions.md gained the bug-triage-routing
  question (judgement on bid-0042) and the seeded-criteria-carry seam
  (judgement on bid-0046); four further gaps (flag setter, clarification
  cap, bug priority default, repro format) deferred to ledger history
  (bids 0041, 0043–0045). Bug items enter the pipeline at spec with an
  intake-written triage.md; the engine repro gate rides `_gate_plan` on the
  optional `bug` flag
  (source: .factory/items/0010-factory-bug-command-understand-replicate/spec.md).
- **2026-07-11, review of 0010:** council approved 6/6, zero blocking
  findings; the executed end-to-end walk proved the gate chain live
  (bug-flag round-trip through real advances, both refusal branches, then
  admission). market.md's bug-domain wording corrected — "machine-enforced"
  now scoped to the plan gate, verify half attributed to the Iron Law
  (judgement on bid-0047); open-questions.md gained the four bug-intake
  residual seams as 0005 consumer requirements (judgement on bid-0048)
  (source: .factory/items/0010-factory-bug-command-understand-replicate/reviews/synthesis.md).
- **2026-07-11, shipped 0010** (mode: auto, ref: 4703ba7): /factory:bug
  replicate-first intake merged — ninth command + factory-bug skill, optional
  `bug` schema flag, `_gate_plan` repro gate (file+event), factory-spec
  seeded-criteria carry rule; council 6/6, verify 12/12 at 332 tests with a
  live scratch-repo gate walk; residual seams recorded in open-questions
  (judgement on bid-0048); duplicate 0011 rejected at triage
  (source: .factory/items/0010-factory-bug-command-understand-replicate/verify.md).
- **2026-07-11, release 0.4.0:** maintainer-requested release carrying
  shipped item 0010 — plugin.json bumped 0.3.0 → 0.4.0, CHANGELOG 0.4.0
  entry added, README quickstart gained the /factory:bug line, and users.md's
  command count corrected eight → nine (judgement on bid-0049). Installed
  plugin refreshed from the local marketplace via `claude plugin update
  factory` (source: .claude-plugin/plugin.json; CHANGELOG.md).
- **2026-07-11, release 0.3.0:** the fork maintainer released the session's
  work — plugin.json bumped 0.1.0 → 0.3.0 and the CHANGELOG Unreleased
  section dated, resolving the recorded version-mismatch open question for
  this fork (0.2.0 had shipped in the upstream CHANGELOG without a manifest
  bump; this release supersedes it). The local plugin marketplace now points
  at the working checkout (source: .claude-plugin/plugin.json; CHANGELOG.md).
- **2026-07-13, triage of 0012:** council unanimous build at priority 2; kind
  confirmed mixed. 0012 fixes a surface-honesty defect — the design-options
  decision block's "Record choice" control is inert on a hosted Artifact (the
  channel elevated to the standard presentation channel), so the block must
  branch on `window.location.protocol` in one canonical `options.html`
  (`file:` = full clickable flow; hosted `https:` = drop Record-choice, lead
  with a tap-to-reply pick that pre-fills the chat relay), never a second
  authored HTML variant. Binding scope: single-writer/zero-network/no-server
  invariants unchanged; greppable DOM gate required; `file://` path keeps
  Record-choice + `FACTORY_CHOICE` console line + `<noscript>` intact; 0005's
  phone-ergonomics list excluded. open-questions.md's 0005 mandatory-inputs
  list gained the surface-honest-affordance rule + the surface-detection
  primitive (judgement on bid-0050) (source:
  .factory/items/0012-adapt-the-design-options-decision-block-/triage.md).
- **2026-07-13, review of 0012:** council unanimous APPROVE (six seats, one
  round), no blocking findings. One medium finding fixed inline as a micro-fix
  (the hosted reply chip must carry typed per-option commentary per spec AC4)
  plus a low test-tightening. open-questions.md gained the grep-only-enforcement
  gap for surface-adaptive behavior (judgement on bid-0052). End-to-end walk
  confirmed the worked-reference options.html embodies the protocol branch with
  zero external requests and the real factory-choice funnel is intact (source:
  .factory/items/0012-adapt-the-design-options-decision-block-/reviews/synthesis.md).
- **2026-07-13, shipped 0012** (mode: auto, ref: a98876a): surface-adaptive
  design-options decision block merged to main — factory-design's decision block
  now branches on `window.location.protocol` (local `file:` keeps the full
  clickable flow incl. Record-choice; hosted Artifact drops the inert
  Record-choice and leads with a reply-to-record affordance whose chip carries
  per-option commentary), one canonical `options.html`, guarded by two
  grep-over-skill coherence tests; capability references aligned. Also carried
  the earlier-session change making Artifact publishing the standard
  presentation channel for design options. No engine change; 334 tests green
  (source: .factory/items/0012-adapt-the-design-options-decision-block-/verify.md).
- **2026-08-02, triage of 0016:** council unanimous BUILD at priority 1 (6/6,
  every seat promoting it independently from its filed p2), kind confirmed
  `backend` over ui-taste's `mixed` dissent (per bid-0040, `kind` is design-gate
  routing only), tier `feature`. **No seat endorsed the item as written** — all
  six returned "rescope" on one diagnosis: the item's own title claims an
  engine-authoritative counter and the counter it named is skill-logged. Five
  blocking findings bind the spec: the trigger substrate moves to backward
  `stage.advance` edges (B1); the engine computes the verdict and
  `factory-dispatch` performs the park, because `advance()` must never return a
  stage other than the one requested (B2); the answer verb, its precondition
  artifact and the dispatch resume clause ship in v1 or the park ping-pongs
  forever (B3); AC5's ParkSnap replay becomes a checked-in fixture, that log
  not being in this repo (B4); and no cross-item token total and no per-tier
  medians ship at all (B5). **Precedent recorded (judgement on bid-0070): a new
  human pause joins the existing configurable `gates` enum rather than becoming
  a second hardcoded built-in gate** — one enum member in
  `schemas/config.schema.json`, read by `_config_gates` and consumed exactly as
  the assure gate is, which keeps vision.md's "exactly one built-in class of
  human gate, and the gate set is configurable" true. Entanglement resolved
  6/6: 0013's plan Task 9 is **struck, not "marked complete"**, because its grep
  hedge for `assure.rejected` would read "not present" once the counter moves to
  edges and would silently reinstate the convention-dependent counter this item
  exists to remove; 0013 drops to p2 and unparks at 0016's per-stage-attribution
  merge, not at 0016 reaching `done`. constraints.md gained the
  engine-written-substrate rule (with the existing rework caps named as a live
  instance), the five-part `waiting-human` pause contract, the provenance rule
  extended to derived statistics, and the 9-of-17 convention-coverage figure
  (judgements on bid-0064, bid-0065, bid-0066, bid-0068); market.md gained the
  measured 27.2% council share at n=1 (bid-0067); open-questions.md gained the
  untrustworthy-aggregate finding and 0005's now-named blocking cost (bid-0063,
  bid-0069). One question the council could not settle — whether the breaker
  should require a non-empty backlog to fire — is handed to spec with both
  evidence-backed positions recorded rather than resolved by attrition (source:
  .factory/items/0016-cost-circuit-breaker-on-engine-authorita/triage.md;
  .factory/items/0016-cost-circuit-breaker-on-engine-authorita/reviews/synthesis.md).
- **2026-08-02, shipped 0016** (mode: auto, ref: 45652c7): cost circuit breaker
  on engine-authoritative rework counts — breaker fires at 2 rework edges,
  parks to waiting-human with a one-verb cost-decision block in both packet
  renderers; `factory cost-answer` is the single writer of cost/answer.md.
  Assure walked J-001/J-002 11/11; J-001's default-path oracle amended 3->4
  permitted diffs on S11 evidence.
- **2026-08-02, judged the 30 outstanding bids from the 0013 triage and 0016
  reviews** (bid-0053…0062, bid-0071…0090): 26 accepted/merged, 2 deferred as
  overtaken (bid-0056's three-verb Respond block and bid-0057's cost.py
  retries gap were both fixed by 0016's own rework before judgement — verified
  in packet.py:177-193 and the rewritten cost.py). constraints.md gained eight
  entries: the engine-validates-proof-shape boundary (bid-0053), re-routing-
  not-waiving (bid-0054), trigger-side engine-observable opt-in (bid-0055),
  guard-tests-red-in-the-failing-form-against-production (bid-0076+0082),
  incomparable-is-never-zero (bid-0077+0085), packet-clearing-at-answer-record
  (bid-0078), false-contract-worse-than-loose (bid-0083), and free-text-on-
  control-flow (bid-0086). open-questions.md gained a dated section of 15
  entries (bid-0059…0062, 0071…0073, 0075, 0079, 0080+0089, 0081, 0084, 0087,
  0088, 0090) plus two instances merged into the config-extension-point
  question (bid-0058, bid-0074). Highest-leverage now-recorded gaps:
  ship.obligation is decorative (bid-0084), the breaker has no advisory arm
  and 0016's prose overpromises (bid-0090), and spend-magnitude runaways stay
  uncovered until 0018 (bid-0080).
- **2026-08-02, day-two hygiene closed out**: answered the 0016 assure report's
  three judgement calls and ratified both journey contracts to
  `status: approved` (J-001, J-002 — settlements written into the contracts;
  answers recorded in the assure report). Filed the four pipeline-defect items
  the day-one run evidenced (0019 scratchpad clobber, 0020 concurrent
  implementers, 0021 lost child replies, 0022 gitignored .factory state) plus
  0023 as the named owner of the packet-furniture ruling and the walk's polish
  advisories (per the bid-0054 re-routing constraint). 0017 given priority 6 —
  behind the 0013/0015/0014/0018 fix batch, since 0013 consumes its only
  observed trigger and `factory waive` covers the reported run's need.
- **2026-08-02, 0013 plan narrowed at the recorded re-judgement deal** (step
  mode, human sign-off pending before any implement dispatch): plan Tasks 7
  (packet readout) and 8 (`status --json` surface) shed to
  `0024-assure-readout-periphery-known-fails-fir` with ACs 13–15; spec amended
  in place. Deviation from the field-report directive, stated: Task 6
  (`factory file-base-defect`) **stays in the core** because the bid-0054
  re-routing constraint ratified this morning requires auto-filed owners to be
  deduped, the ship gate's owner rule depends on the verb for unattended
  operation, and Task 10's skill prose and coherence test consume it. With
  Task 7 shed, no remaining task regenerates the default-path goldens, so AC1
  byte-identity holds unqualified (0016 already shipped the Respond one-verb
  refactor). Narrowed roster: Tasks 1–6, 10, 11 of the original 11.
- **2026-08-02, 0013 assure round 1: rework on J-001/S5** (7 pass, 1 fail,
  1 ambiguity; `assure.rejected` round 1 logged — rework edge 1 of threshold
  2, breaker armed but under threshold). The fail is objective against the
  approved contract's refusal-cause oracle: empty/malformed owner arms are
  refused by the schema layer with an index-addressed message naming neither
  journey, scenario, nor the owner rule, while rule 10's message falsely
  claims to cover them ("owner '' is absent or malformed") — a live instance
  of the false-contract-worse-than-loose constraint (bid-0083). Judgement
  call 1 settled by the verdict itself: S5 binds all five arms. S9's
  ambiguity and S3's byte-comparison discharge settled by contract amendment
  through the firewall (bid-0093 accepted): fresh-round deletion is
  skill-side, discharged by the AC11 coherence test plus the enforced-outcome
  transcript; S3 discharged by the default-path golden suite.
- **2026-08-02, validation layering rule (bid-0094 accepted, jdg-0094; from
  0013's rework-round review).** JSON-schema layers do shape checks only;
  semantic validation that needs journey/scenario addressing or item-store
  state (owner resolution, open/done status) belongs to the gate ladder,
  whose refusals can name the journey, scenario and rule. Ratified in
  practice by 0013 commit 6552144: the assurance-verdicts `owner` pattern
  moved from the schema (array-index refusals, rejected by the J-001/S5
  assure walk) to ship-gate rule 10 (`machine.py`, `_OWNER_RE` before
  `items.load_item`; traversal closed, call-spy verified). Named open
  corollaries, recorded so a recurrence is a decision, not a surprise:
  (D6) the `attribution` enum still does vocabulary enforcement schema-side —
  the same refusal class S5 rejected for `owner`; (W2-F4) the relaxation cost
  `factory validate` its owner-shape pre-flight signal — `attribution` and
  `merge_base` are caught at validate, `owner` only at the ship gate: a
  stated trade of gate message quality over early feedback.
- **2026-08-02, shipped 0013** (mode: auto, ref: 3596906): assure attribution —
  ship gate blocks on regressions this item caused, validating pre-existing
  attribution behind the opt-in `assure.attribution` config key; owner semantic
  validation lives in ship-gate rule 10, default path byte-identical to the
  pre-change engine (golden suite). Assure passed round 2 with 2 pre-existing
  non-blocking findings re-routed to owners 0025 and 0023. Merged-tree suite:
  815 tests OK.
- **2026-08-02, 0015 triage (BUILD 6/6, p3):** three constraints appended to
  `brain/constraints.md` under `# Constraints`: (1) build order — 0025 lands
  before 0015 with the binding "entry into implement" round-scoping key, and
  0025 was promoted onto the ranked roadmap (priority 2, ahead of 0015)
  (jdg-0096); (2) new gate caps (`MAX_APPROACH_REJECTIONS`, the
  `verify -> implement` cap) count engine-written backward `stage.advance`
  edges, never skill-logged events — the existing event-counted caps remain a
  named live defect no new spec may copy (jdg-0097); (3) engine-auto-written
  cost-answers are a pause-consuming miss-path — redesign coverage comes from
  an operator answer or a bid-0065-contracted pause, and breaker
  `rework_edges` is never reset (jdg-0098). Full triage synthesis:
  `.factory/items/0015-approach-rejected-a-redesign-loop-back-t/reviews/synthesis.md`.
- **2026-08-02, judged 0015's spec-stage bids** (bid-0099…0106, all accepted):
  seven recorded assumptions to open-questions.md (artifact path, answer verb,
  edge request path, append-only lifecycle, minimum content, continue-at-cap
  watermark, spec-freshness token) and the required J-002 amendment landed
  ahead of 0015's assure walk — the one-rework-figure oracle now names the
  labelled `rework edges since last redesign` companion as permitted, derived
  and numerically-agreeing (judgement on bid-0106).
- **2026-08-02, triage of 0025 (BUILD 6/6, priority 2, tier bug, kind
  backend):** council unanimous — the fix shape is one shared postdating
  predicate (evidence log-index strictly after the latest engine-written
  `stage.advance` into implement), the item body's "latest backward edge"
  parenthetical is dropped, and `_gate_ship` migrates to the shared
  primitive. Five blocking findings bind the spec (B1 index-not-timestamp
  comparator with frozen-clock tie test; B2 stale-evidence refusals must
  not say "not logged"; B3 full postdating-site enumeration incl. the
  journeys-none branch and assure.py:42; B4 fail-closed on no findable
  entry-into-implement; B5 SPECIAL-`from` resumes excluded from the round
  key — resolved by orchestrator ruling after the round-2 seats crossed
  positions; a third round was warranted but skipped per the hard stop).
  constraints.md gained the jdg-0107 refinement annotating the bid-0096
  scoping key ("any non-SPECIAL-`from` entry") and the jdg-0108
  postdating-site-enumeration rule. Full synthesis:
  .factory/items/0025-round-scope-all-rework-gates-implement-c/reviews/synthesis.md.
- **2026-08-02, judged 0025's triage bids** (bid-0107, bid-0108, both
  accepted): the bid-0096 round-scoping key wording is refined in place —
  "any entry" means any entry whose `from`-stage is not in `SPECIAL`,
  expressed via the existing `SPECIAL` set inside the one shared primitive
  (jdg-0107); and the postdating migration must cover every site, not only
  the three entry gates — `_gate_ship`'s main key and its journeys-none
  `verify.green` early-return, plus `assure.py:42`'s `record_confirmation`
  comparison, all route through the one shared helper (jdg-0108). Full
  triage synthesis:
  `.factory/items/0025-round-scope-all-rework-gates-implement-c/reviews/synthesis.md`.
- **2026-08-02, shipped 0025-round-scope-all-rework-gates-implement-c** (mode
  auto, merge 9e5b014 into main): all three rework entry gates plus
  `_gate_ship`'s main key, its journeys-none `verify.green` early-return, and
  `assure.py:42`'s `record_confirmation` comparison now route through one
  shared log-index postdating predicate keyed on the latest engine-written
  non-SPECIAL-`from` `stage.advance` into implement, fail-closed with a
  distinct stale-evidence refusal. Assure passed round 1, 0 non-blocking
  fails; merged-tree suite 838 tests OK. Branch deleted.
- **2026-08-03, judged 0015's review-council bids** (bid-0114 accepted HIGH,
  bid-0115, bid-0116, bid-0117 all accepted): four entries added under
  open-questions.md "Raised by 0015's review council (2026-08-03)" — the
  second-exhaustion escape from the B5 pause contract (spec §7 amendment,
  both watermark artifacts, follow-up filed before 0015 ships), the
  cost-decision rendering fork with its extraction trigger, the
  covering-vs-exact watermark hardening, and the fired private-helper
  promotion trigger (0025 F4, second accretion). Review verdict: APPROVE
  WITH FINDINGS, unanimous, 0 blocking. Full synthesis:
  `.factory/items/0015-approach-rejected-a-redesign-loop-back-t/reviews/synthesis.md`.
- **2026-08-03, shipped 0015-approach-rejected-a-redesign-loop-back-t**
  (mode `auto`, merge commit `9cd4190`, branch head `5fea92c`, 11 commits,
  branch deleted): the `approach.rejected` redesign edge back to spec —
  artifact-gated and lifetime-capped on engine-written edges, the
  round-scoped spec-exit gate, `factory approach-answer` with its watermark
  artifact and single-writer log guard, and the packet's Redesign decision
  tradeoff block with dual populations. J-003 registered and J-002's
  one-rework-figure and gate-off oracles amended in the same close-out
  (AC21, commit `e617660`). Merged-tree suite 884 tests OK, exit 0, twice
  consecutively. **Three disclosures.** (1) The shipped head `5fea92c` lands
  one commit after the review council approved `18a02b0`: it implements the
  council's own verbatim converged remedy (judgement on bid-0127, specified
  by three seats) and was not re-adjudicated by them; verify round 2
  exercised all five refusal arms at this head. (2) Assure round 2 passed
  13/13 with **two reviewer fail verdicts re-scored by the orchestrator**
  (J-003/S2 and J-001/S13) — both disclosed in the assure packet, the
  run-manifest and the verdict notes, with the reviewers' originals
  preserved. (3) Findings routed onward to **0027** (p2, newly reachable via
  this item) and **0028**. Assure packet:
  `docs/factory/packets/0015-approach-rejected-a-redesign-loop-back-t-assure.md`;
  shipped packet:
  `docs/factory/packets/reports/0015-approach-rejected-a-redesign-loop-back-t-shipped.md`.
- **2026-08-03, triage of 0018-wall-clock-trigger-arm (DON'T BUILD AS
  SPECIFIED, 6/6 unanimous, priority 5 → 8, tier `feature`, kind `backend`
  confirmed)**: the council's first round returned `build-rescoped` from all six
  seats; the orchestrator then ran the item's own AC4 calibration replay over
  every real `log.jsonl` *at triage* rather than deferring it to
  implementation, and all five recalled seats flipped to don't-build. The replay
  is arithmetic, not judgement: AC2 required firing at 9,499s (0016's first
  implement pass) while 0015's first implement pass is 10,046s and 0015 shipped
  clean, so every AC2-satisfying threshold parks healthy work — and 0015's
  measured 4,011,314 tokens exceed 0016's 3,949,630, killing the token
  re-denomination too. `active_seconds` proved to be calendar dwell (0015 booked
  a single 25,145s overnight gap to active `review`; the top eleven items by
  `active_seconds` are unstarted `idea` filings, 0016 twelfth). The council added
  three findings the replay did not have: the arm has **no firing site**
  (`breaker.verdict` runs only after an accepted transition, and a single-pass
  runaway makes zero transitions while it burns), **no engine-authoritative work
  dimension exists**, and there is **no per-arm gate disable**. Ruled
  unanimously that **0027 is a hard dependency** — the runaway shape never
  re-enters implement, so the arm must park from a non-implement stage, exactly
  the branch `packet.py:331` leaves falling through — and 0028
  adjacent-but-should-precede. The problem statement stays filed; the mechanism,
  dimension and all six ACs do not. Three items filed out of the triage: **0029**
  (spend-event leaf/fork scope discriminator — the precursor, and the first owner
  bid-0063 has had), **0030** (measurement spike that gates 0018), **0031** (the
  cost packet's churn-shaped decision copy, a standing defect independent of
  0018). Triage record:
  `.factory/items/0018-wall-clock-trigger-arm-catch-the-spend-r/triage.md`;
  council: `…/reviews/synthesis.md`.
- **2026-08-03, judged 0018's triage bids** (bid-0131…bid-0136, all six
  accepted): five constraints appended to `brain/constraints.md` — a trigger must
  be calibratable on the corpus that motivates it (jdg bid-0131);
  engine-authoritative ≠ meaningful, bid-0064 governs who writes the event and
  bid-0018 governs what the figure means (bid-0132); a gate with no per-arm
  disable is a single gate (bid-0133); Factory has no in-stage work meter and no
  engine-authoritative quantity can become one, so no control can fire before the
  stage that spent the money ends (bid-0134); a mechanically passable AC set is a
  liability when the mechanism is unsound, since a green suite converts an
  unfounded threshold into recorded evidence of correctness (bid-0135). And one
  correction to `brain/open-questions.md` (bid-0136): the spend-magnitude
  open question no longer claims 0018 resolves it — that entry was false — and is
  re-pointed at 0029 and 0030, with its stale token figures refreshed.
- **2026-08-03, the ParkSnap acceptance test will not be run — human decision.**
  The day-two field report named it "the only step that proves the batch met
  its objective" (re-run the ParkSnap p1 bug through the improved pipeline;
  pass = fix merged AND `factory cost` a small fraction of 4.9M). The human
  declined to test against that repo. Consequences, recorded rather than
  quietly dropped:
  - **The batch's savings claim stays UNMEASURED**, and per the provenance
    constraint (judgement on bid-0018) it must be carried that way on every
    surface. Nothing shipped in this batch is evidenced to reduce spend; what
    is evidenced is that it changes *what the pipeline gates on* (0013), *what
    it counts* (0025), and *what it can do when a design will not converge*
    (0015).
  - **There is no in-repo substitute, and this is now demonstrated rather than
    assumed.** 0018's triage replay over every real log found the corpus has no
    separable runaway: 0015 cost 4,011,314 measured tokens against 0016's
    3,949,630, so the item built *after* the batch outspent the item that
    motivated it, on both the token and the wall-clock axis. Comparing today's
    items against 0016 would therefore produce a number, not evidence — and
    bid-0063's nested double-count means no aggregate is trustworthy in either
    direction until 0029 lands.
  - **The batch closes on shipped mechanism, not on measured saving.** Anyone
    citing these items as a cost win is citing an assumption; the honest claim
    is that the pipeline now stops on causes it previously ignored.

- **2026-08-03 — 0027's triage council: BUILD at p2, scope extended, 0028
  absorbed, 0031 not.** Five material findings became brain edits through the
  ledger firewall:
  - `constraints.md` gained **the answerable-pause selector rule** — reason-key
    the verb, and hoist every reason-prefix arm above every stage-keyed arm,
    because a shadowing stage arm hands over a verb from a *different* pause
    contract (`factory waive` on an unanswered spend gate, which the engine
    accepts and ships). Judgement on **bid-0137**.
  - `constraints.md` gained **"cross-item token comparisons are not measured
    evidence"**, promoting the 0018-batch observation above from a fact about
    that batch to a standing provenance rule, and naming the permitted
    within-item figure (avoided council fan-out). Judgement on **bid-0140**.
  - `design-principles.md` gained **"one predicate for the decision screen and
    its answer verb"** (judgement on **bid-0138**) and **"single-valued
    fixtures cannot see a branch-key defect"**, whose corollary is that
    acceptance here is a bidirectional coupling invariant over *rendered*
    output (judgement on **bid-0141**).
  - `open-questions.md` merged **the mechanism under bid-0079** — a
    `GateError`'s text is not a pause prefix, so the blocked-after-session-death
    route is structurally invisible to prefix-keyed packet logic and stays open
    rather than riding along with 0027. Judgement on **bid-0139**.
  - Also recorded on the items themselves: 0027's bid-0079 "same defect, fix
    them together" claim is **struck as false** (the refusal text does not match
    the prefix), and its "today's measured evidence" bundling premise is
    restated as a proxy claim. See `.factory/items/0027-…/triage.md`.

- **0027's review council (2026-08-03)** — the branch was **rejected for rework
  (round 1)** on one high finding, and four material findings were merged into
  the brain:
  - `constraints.md` gained **"a declared assurance scenario is a contract, and
    inherits the false-stronger-contract rule"** — 0027's `impact.json` S5
    generalised past the population its fixtures can construct, verified false by
    render against the branch. Judgement on **bid-0144**.
  - `design-principles.md` gained **"a RECOMMENDED remedy in a spec can be
    unsound"** — the spec's own §3 `is_cost_pause(meta)` extraction would have
    regressed a `blocked` cost pause to the `/factory:run` loop, so declining it
    was correct (judgement on **bid-0145**) — and **"red-first is verifiable
    after the fact"**, the branch-tests-against-base-production-code check that
    returned 21/27 red here and named the two vacuous assertions (judgement on
    **bid-0146**).
  - `open-questions.md` gained **"what degradation still yields a usable council
    verdict?"** — this council ran with the subagent pool exhausted, one reasoner
    playing three lenses and no round 2; the reversible default is proceed,
    disclose, and rest the verdict on reproduced experiments. Judgement on
    **bid-0147**.

- **2026-08-03, shipped 0027-packet-respond-falls-through-to-factory-**
  (mode `auto`, merge commit `0bd2a36`, branch head `c01eac8`, 3 commits,
  branch deleted): the packet's Respond verb is keyed on the **pause's reason**
  rather than the stage it was parked from, so a decision pause parked from an
  unexpected stage no longer falls through to `/factory:run`; the narrow
  consequence line names the park it must resume to; and the cost breaker's
  missing `- answer:` line gets its own refusal instead of a `None` repr
  (0028's scope item 4, shipped here by absorption — 0028's own line still
  carries bid-0129's rework-edges regex residual). Merged-tree suite 903 tests
  OK, exit 0. Assurance passed **11/11 blind (round 2)** after the human
  rejected a degraded round 1 and required a fresh-context reviewer, then
  confirmed via `factory confirm` over two unresolved judgement calls
  (J-001 N3/N4 shipped-with-known-fails oracle non-render, and raw Python dict
  reprs in packet copy). The hardcoded-`implement` continue-consequence finding
  was routed onward to **0031** (p3). Shipped packet:
  `docs/factory/packets/reports/0027-packet-respond-falls-through-to-factory--shipped.md`.
- **2026-08-03, triage of 0026 (BUILD-RESCOPED 6/6, priority 3, tier `feature`,
  kind `backend`):** the human-filed "complexity-scored bug flow" was affirmed on
  its problem statement and **refused on its mechanism, unanimously**. Both halves
  cut 6/6: the **1–5 numeric complexity score** (every depth axis is a named enum;
  a bare integer beside three provenance-tagged packet figures reads as the most
  authoritative and is the least grounded — bids 0018/0066/0077) and **"bugs run a
  subset of the pipeline"** (`machine.stage_sequence` grows no arms; gates chain on
  the previous stage's event, so every drop strands the next gate, and the sole
  precedent `journeys: none` needed a hand-written `_gate_ship` bypass). The
  score's fatal flaw is that it is a **prediction at intake**: 0027 was filed as a
  one-line change and its own triage found the naive one-liner *strictly worse
  than the defect*; it shipped as 66 lines across two files. The item's headline
  cost premise was **refuted at triage** — 0027's cited 403,895 assure tokens are
  100% pool-exhaustion rework at the `node` floor, and a malfunctioned council
  cost 1,499,591 against 135,475 for a complete 9-seat fan-out (judgement on
  bid-0153). What survives, in order: **routing** (make `/factory:bug` reachable
  from `commands/add.md`, shipped as one unit with the roadmap write and a triage
  receipt), then an **engine-written depth recorder**, then **bid-0125** review
  depth keyed on the round's change class — *computed from the round's diff at the
  review gate, never predicted*. **Assure and verify depth are OUT, binding 5/5**
  (bid-0124: an assure error is irrecoverable where a review error costs a round).
  `factory add --tier bug` must **not** imply `bug: true` (4/5, judgement on
  bid-0149). 0029 is **not** 0026's precursor — the reverse holds on the recorder
  half. constraints.md gained five rules (judgements on bids 0149, 0150, 0152,
  0153, 0154); open-questions.md gained four entries and a re-pointed bid-0042
  (judgements on bids 0151, 0155, 0156, 0157). One item filed:
  **0032-dispatch-resilience-pool-exhaustion-and-**. This triage also logged the
  corpus's **first `"stage": "triage"` spend event** (197,539 measured tokens),
  acting on bid-0152 rather than only recording it
  (source: .factory/items/0026-complexity-scored-bug-flow-bugs-run-a-su/triage.md;
  .factory/items/0026-complexity-scored-bug-flow-bugs-run-a-su/reviews/synthesis.md).
