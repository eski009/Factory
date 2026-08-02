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
