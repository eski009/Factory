# Open Questions

<!-- Unresolved questions that block confident work; each should name what
     would resolve it. Every claim should cite a source: (source: <path-or-url>) -->

- **Who is Factory for beyond its author?** No docs describe a target market,
  user segments, or adoption goals (README describes usage, not audience).
  Resolved by: the factory-research stage (personas.md, market.md) plus the
  human's answers in docs/factory/packets/taste.md.
- **Version mismatch:** `.claude-plugin/plugin.json` says `0.1.0` while
  CHANGELOG.md documents a released `0.2.0` (source: .claude-plugin/plugin.json;
  CHANGELOG.md). Resolved by: the maintainer confirming which is intended and
  bumping the manifest.
- **Distribution/commercial intent is undocumented** — is this a personal
  tool, an open-source community plugin, or a product? No pricing, telemetry,
  or adoption docs exist (source: repo inventory). Resolved by: taste packet
  answers or a maintainer statement.
- **What "quality/done" means to this fork's owner** is unrecorded — the
  upstream spec defines gates, but the human's own non-negotiables and taste
  are not yet captured. Resolved by: answering
  docs/factory/packets/taste.md.
- **CI scope:** only `.github/workflows/test.yml` exists; whether releases,
  linting, or marketplace publishing should be automated is undefined
  (source: .github/workflows/). Resolved by: a maintainer decision.
- **Deferred v1 non-goals** (non-Claude agents, headless CI operation,
  multi-repo orchestration) have no revisit criteria — when, if ever, do they
  get reconsidered? (source: docs/superpowers/specs/2026-07-03-software-factory-design.md
  §1 Non-goals). Resolved by: a roadmap decision.

## Raised by initiation research (2026-07-10)

- **What does one work item cost end-to-end?** Three research seats
  independently flagged the missing cost story: cost metering is category
  table stakes, the target persona personally pays the token bill, and
  autopilot defaults to run-until-drained with no effort accounting. The
  six-seat council's cost multiplier is inferred, not measured
  (source: .factory/runs/research/synthesis.md). Resolved by: measuring a
  real item's token/effort spend and deciding whether per-run cost estimates
  or budget gates belong on the roadmap. *Mechanism sub-question (merged from
  0001's spec, authorized: judgement on bid-0005):* no mechanism exists to
  measure token spend from inside a skill run — 0001 ships a best-effort
  `spend.md` with an explicit UNMEASURED marker and effort proxies; item 0004
  (per-item cost meter) should define the real mechanism
  (source: .factory/items/0001-focus-group-research-structured-intervie/spec.md).
- **Should skills get a config extension point?**
  `schemas/config.schema.json` sets `additionalProperties: false` on the
  `research` object (and the config root), so skills cannot add opt-in config
  keys (e.g. `research.focus_group`) without an engine schema change; 0001
  works around it with per-run CLI arguments
  (source: schemas/config.schema.json;
  .factory/items/0001-focus-group-research-structured-intervie/spec.md;
  authorized: judgement on bid-0004). Resolved by: a maintainer decision —
  either grow the schema per feature, add a validated `extensions` object, or
  affirm CLI-argument gating as the convention. *Two further instances
  (merged):* 0013 chose the reversible default — grow config.schema.json per
  feature with a first-class explicitly-defaulted key (`assure.attribution:
  false` in DEFAULT_CONFIG) — recorded as an assumption, not a ratified
  convention (authorized: judgement on bid-0058); and 0016 ships
  `breaker.REWORK_THRESHOLD` as a module constant with only `cost in gates`
  as the dial, so per-repo threshold tuning has no home until this question
  is decided or the first operator needs a different number (authorized:
  judgement on bid-0074).
- **Should brownfield repos default to a human ship-gate?** The category
  convention hard-gates the merge (Copilot agents cannot self-approve),
  while Factory defaults `merge: auto` with the sole human gate at design —
  a fit for the expert-solo persona but a plausible brownfield adoption
  blocker (source: .factory/runs/research/synthesis.md;
  https://docs.github.com/en/copilot/concepts/agents/cloud-agent/risks-and-mitigations).
  Resolved by: a maintainer defaults decision, recorded in decisions.md.
- **Persona validation.** The Overnight Operator persona is a cited
  hypothesis assembled from category evidence, not observed Factory users;
  the Ralph-loop-adopter transfer is an assumption
  (source: docs/factory/brain/personas.md). Resolved by: real user feedback
  or telemetry once Factory has users beyond its author; re-run research at
  depth `deep` for secondary personas.
- **Citation-class seam at research §4.** `skills/factory-research/SKILL.md`
  §4 (and the personas.md header) admit only `(source:)`/`(assumption)`,
  while §3b sends `(simulated: focus-group run <date>)` claims into brain
  surfaces — a literal execution of §4 strips or launders the simulation
  label exactly where simulated findings enter the brain
  (source: .factory/items/0001-focus-group-research-structured-intervie/reviews/code-review/round-1/customer.md;
  authorized: judgement on bid-0009). Resolved by: a one-sentence §4/header
  addition admitting the third citation class — before the first `deep` run
  writes to personas.md.
- **Per-skill `references/` dirs vs the coherence test.**
  `tests/test_plugin_coherence.py::test_every_reference_doc_link_resolves`
  resolves every `references/<name>.md` string in any SKILL.md against
  `skills/capabilities/references/` only; the repo now has a second,
  unchecked per-skill references dir (factory-research), passing only via
  careful wording
  (source: .factory/items/0001-focus-group-research-structured-intervie/reviews/code-review/round-1/architecture.md;
  tests/test_plugin_coherence.py; authorized: judgement on bid-0010).
  Resolved by: generalizing the test to check the linking skill's own
  directory first, or standardizing a single references layout.
- **`_gate_plan` cannot distinguish a design rejection from a pick.**
  machine.py's `_gate_plan` (line 69) checks only that `design/choice.md`
  exists and is non-empty — while a fresh `- option: none` rejection sits
  unconsumed, a manual `factory advance <id> plan` would pass. Item 0003
  guards both automated paths (dispatch short-circuit, factory-design entry
  check) and consumption deletes the file, but the engine gate itself stays
  open to manual advances (source: scripts/factory/lib/machine.py;
  .factory/items/0003-interactive-decision-pages-clickable-cho/spec.md;
  authorized: judgement on bid-0013). Resolved by: a one-line `_gate_plan`
  option check in a future engine-scoped item.
- **Focus-group hypotheses (simulated — unvalidated).** A simulated
  focus-group run at `.factory/runs/research/focus-group/2026-07-10/`
  (4 personas: operator, buyer, plugin SME, staff engineer) produced
  convergent hypotheses: cost legibility (per-stage attribution + hard cap)
  and merge/gate defaults are the adoption thresholds; taste memory is
  trusted only as far as it is inspectable/revertible; setup ceremony
  exceeds a ten-minute budget (simulated: focus-group run 2026-07-10).
  These are AI-roleplayed hypotheses, not user evidence. Resolved by:
  interviewing real humans matching the roster, using the guides in that
  run's `guides/` directory.
- **Interactive-gate refinements — mandatory inputs for item 0005.**
  From 0003's review (four seats): dispatch live-lock termination when a
  `none` choice meets an unavailable factory-design; escalation ask-2 reword
  or round-counter reset on spec change; pre-pick sticky-bar state; fixed-bar
  bottom clearance on phones; none-cost cue; OPTION_RE re.fullmatch; the
  bid-0013 `_gate_plan` option check (source:
  .factory/items/0003-interactive-decision-pages-clickable-cho/reviews/synthesis.md;
  authorized: judgement on bid-0038). Added from 0012: **surface-honest
  affordances** — a control that cannot act on the current viewing surface
  (e.g. Record-choice on a hosted Artifact with no session reading its console)
  must not render there; and the **`window.location.protocol` surface-detection
  primitive** 0012 introduces (single canonical page: `file:` = full clickable
  flow incl. Record-choice/console-line/noscript; hosted `https:` = drop
  Record-choice, lead with a tap-to-reply pick that pre-fills the chat relay) is
  a building block 0005 reuses, never a second authored HTML variant (source:
  .factory/items/0012-adapt-the-design-options-decision-block-/reviews/synthesis.md;
  authorized: judgement on bid-0050). Resolved by: 0005's spec treating this
  list as binding inputs when it unblocks.
- **Surface-adaptive behavior is grep-enforced only, not artifact-checked.**
  0012's surface-adaptive decision-block requirement is guarded solely by
  grep-over-skill-prose tests (`tests/test_plugin_coherence.py`); no engine or
  generated-artifact assertion confirms a real `options.html` actually branches
  on `window.location.protocol` and drops Record-choice on the hosted surface,
  so a future skill edit could satisfy the greps while regressing real behavior.
  Same enforcement-gap class as the citation-class seam and the verify
  mandatory-criteria (protected only by a skill sentence). Resolved by: a
  produced-artifact check (a test that renders/greps an actual generated
  options.html) if the gap ever bites (source:
  .factory/items/0012-adapt-the-design-options-decision-block-/reviews/synthesis.md;
  authorized: judgement on bid-0052).
- **Should bug items ever get council triage?** 0010's spec routes bugs
  around council triage: the intake skill writes `triage.md` itself (a
  confirmed repro is the build evidence) and advances idea → triage → spec,
  keeping intake fan-out at zero per the bid-0002 cost constraint; the
  council still reviews the fix at the review stage. Whether some class of
  bug (architectural, cross-cutting, contested priority) warrants the full
  triage council is unresolved
  (source: .factory/items/0010-factory-bug-command-understand-replicate/spec.md;
  authorized: judgement on bid-0042). Resolved by: real bug-intake usage
  showing a misrouted bug, or a maintainer policy decision.
- **Seeded-criteria carry is a skill-sentence seam.** Verify reads
  acceptance criteria only from `spec.md`, but 0010's mandatory bug criteria
  (repro re-run passes; regression test failed pre-fix) are seeded into the
  item body and carried into spec.md only by a one-line verbatim-carry rule
  in factory-spec's SKILL.md — nothing engine-level forces preservation, so
  a careless spec pass could drop the criteria verify depends on
  (source: .factory/items/0010-factory-bug-command-understand-replicate/spec.md;
  authorized: judgement on bid-0046). Resolved by: an engine-level seeded-
  criteria check in a future engine-scoped item, or affirming the skill-rule
  convention after real bug items exercise it.
- **Bug-intake residual seams (from 0010 review, all fail-closed, none
  blocking).** (1) Unowned resume path: a bug item paused waiting-human at
  intake resumes to `idea`, where no skill produces `repro.md` — it stalls
  at the plan gate only after spec/design spend; (2) `mode: human-confirmed`
  repros give unattended verify nothing executable — verify must pause to
  the human, never self-attest; (3) the clarification-stop packet lacks the
  house-style section; (4) add.md kind guidance diverges from the bug kind
  rule (restore-to-spec visual bugs stay backend)
  (source: .factory/items/0010-factory-bug-command-understand-replicate/reviews/synthesis.md;
  authorized: judgement on bid-0048). Resolved by: treating (1)–(3) as
  binding consumer requirements when 0005 unblocks, and a one-line add.md
  wording tweak for (4) in any commands-touching item.
  **Update 2026-07-18: seam (2) closed directly.** The observed failure mode —
  a forked, unattended verify reading a `mode: human-confirmed` bug's diff and
  self-attesting `verify.green` because it can see the expected-after state in
  spec.md — is now structurally prevented in `factory-verify`. Rather than only
  "pause to the human", verify routes any visual / human-confirmed criterion
  through a **blind observer** protocol (capabilities skill's
  `references/visual-verify.md`, gated on a new **App visual capture** capability
  row): a fresh subagent drives the app and reports what it factually sees, blind
  to the diagnosis/diff/expected, and verify judges that independent report
  against the criteria — requiring both original-failure-absent AND
  expected-present. Human confirmation remains the fail-closed fallback when no
  capture driver is available. Separating observation from judgment removes the
  confirmation bias that produced the false "done".
- **Never-bricks residual corners (from 0009 review, none blocking).**
  reputation_table TypeError on wrong-typed delta values; health._role_stats
  strict read of council/*.md; validate quieter than runtime on body-only
  item.md byte corruption; dead strict list_items API; "across 1 items"
  plural (source:
  .factory/items/0009-finish-the-never-bricks-promise-crash-pr/reviews/synthesis.md;
  authorized: judgement on bid-0037). Resolved by: one small hardening item
  when any of these bites, or fold into the next engine-touching item.
- **No cross-item token aggregate is currently trustworthy.** The spend
  convention instructs a stage skill to log its own subagent fan-outs *and*
  `factory-dispatch` to log the forked stage-skill invocation containing them
  (skills/factory-dispatch/SKILL.md §Spend logging), so measured totals are
  inflated by nesting depth. Observed on 0013, not inferred: `factory-spec`
  logged 119,266 for its `spec-writer` dispatch while the harness reported the
  whole containing fork at 98,841 — **the inner figure exceeds the outer one**,
  so the two events are not merely double-counted, they measure different
  quantities. Until this is fixed, the "what does one work item cost end-to-end"
  question above cannot be resolved from logged spend at any scope wider than a
  single item (source:
  .factory/items/0013-assure-attribution-gate-only-on-regressi/log.jsonl;
  skills/factory-dispatch/SKILL.md:59; authorized: judgement on bid-0063).
## Raised by the 0013 spec and 0016 reviews (2026-08-02)

- **Integration-branch resolution is skill prose, not an engine primitive.**
  The brain names no integration branch and factory-ship says "the repo's
  default branch" in prose only. 0013 assumes `origin/HEAD → main → master`
  with unresolvable treated as blocking, recording the resolved branch in
  every dependent artifact (source: .factory/items/0013-…/spec.md;
  authorized: judgement on bid-0059). Resolved by: a helper primitive or a
  ratified convention.
- **Defaults for engine-filed work items are unset.** 0013 assumes stage
  `idea`, kind `backend`, tier `bug`, no priority (sorts last), no bug flag.
  Note the no-priority default interacts with the bid-0087 finding below
  (source: .factory/items/0013-…/spec.md; authorized: judgement on bid-0060).
  Resolved by: a maintainer defaults decision.
- **Dedupe scope for engine-filed defects.** 0013 assumes repo-wide dedupe
  across all not-done items, keyed by (scenario id + failing-step
  fingerprint) stored plain-text in the filed item's body (source:
  .factory/items/0013-…/spec.md; authorized: judgement on bid-0061).
  Resolved by: the recipe surviving or failing real filings.
- **Freshness rule for counterfactual (merge-base) evidence.** 0013
  implements exactly the bound rule (recompute the merge base at ship, refuse
  mismatch) and names the residual it does not close: when the integration
  branch advances without the item's branch changing, a defect fixed on the
  integration branch mid-run can still be cited as pre-existing (source:
  .factory/items/0013-…/spec.md; authorized: judgement on bid-0062).
  Resolved by: a strictly-additional freshness check if the residual bites.
- **Does one recorded answer cover later recurrences of a pause?** 0016 chose
  a monotone watermark: the answer artifact records the engine-observable
  count it answers (`- rework-edges: N`) and suppresses the pause only while
  the current count ≤ N (source: .factory/items/0016-…/spec.md; authorized:
  judgement on bid-0071). Resolved by: ratifying this as the convention for
  every answerable pause, or the second answerable pause choosing otherwise.
- **Answer-verb naming precedent.** 0016 chose `factory cost-answer <id>
  <option>` writing `cost/answer.md` on the design/choice.md model. Is
  `factory <topic>-answer` / `<topic>/answer.md` the naming rule? (source:
  .factory/items/0016-…/spec.md; authorized: judgement on bid-0072).
- **Who enacts a park's options?** 0016's engine treats every recorded answer
  identically; factory-dispatch routes on the recorded option — the same
  skill-owned seam as `- option: none`. Does that seam generalise? (source:
  .factory/items/0016-…/spec.md; authorized: judgement on bid-0073).
- **Backlog-wide readouts: flag or verb?** 0016 chose `factory cost --all` on
  the per-item command (item becomes nargs=?; neither/both refused). Decide
  before the next aggregate surface lands (source:
  .factory/items/0016-…/spec.md; authorized: judgement on bid-0075).
- **The cost breaker's miss-path is worse than its no-op path.** The park
  converting the breaker verdict into an operator decision is skill prose
  with no engine-side obligation and no test. If the session dies between the
  firing advance and the park, the next implement entry is refused, dispatch's
  two-failures rule sends the item to blocked, and the blocked packet's
  fallback Respond line says `/factory:run` — the exact instruction the pause
  forbids, sending the operator back into the spend the breaker just stopped
  (source: .factory/items/0016-…/reviews/synthesis.md; authorized: judgement
  on bid-0079). Resolved by: an engine-side park obligation or a
  breaker-aware blocked packet.
- **Spend-magnitude runaways remain uncovered after 0016, and are now
  unowned.** The field report's Defect 5 proposed a disjunction (spend-multiple
  OR rework count); only the rework disjunct shipped. 0016 itself burned
  1,989,500 measured tokens by its first implement pass (3,949,630 final) with
  zero rework edges — its own breaker scores it 0, and nothing on any surface
  tells the next reader that a non-rework-shaped runaway still burns unnoticed
  (source: .factory/items/0016-…/reviews/synthesis.md; authorized: judgements
  on bid-0080, bid-0089).

  *Amended 2026-08-03 — this entry previously read "Item 0018 is the filed fix…
  Resolved by: 0018 shipping the wall-clock/spend arm." That is false.* 0018's
  triage council was unanimous that it must not be built as specified: no
  threshold satisfies its own ACs without parking healthy work (0016's first
  implement pass is 9,499s, 0015's is 10,046s and 0015 shipped clean, and 0015
  also out-spends 0016 on measured tokens), `active_seconds` measures calendar
  dwell rather than work, and no engine-authoritative in-stage work meter exists
  to rescope onto. 0018 is `blocked` at priority 8. **Resolved by:** 0029
  (`scope-spend-events-a-leaf-vs-fork-discri`) making measured totals
  trustworthy — it finally owns the bid-0063 nested-dispatch double-count that
  both 0016 and 0018 cited as a reason not to build the real thing — and 0030
  (`measurement-spike-gap-capped-per-pass-at`), whose finding determines whether
  0018 ever unblocks or is closed won't-build (source:
  .factory/items/0018-…/triage.md, reviews/synthesis.md; authorized: judgement
  on bid-0136).
- **Verify rework is structurally uncountable until 0014/0015.**
  `REWORK_FROM` includes `verify` but `machine.advance` admits no
  `verify → implement` transition, so a verify failure ping-pongs through
  waiting-human and counts zero rework edges — unbounded burn with the
  breaker permanently dormant. Disclosed in REWORK_SUBSTRATE_NOTE and tested,
  but disclosure is not mitigation: 0016's breaker coverage is conditional on
  0015/0014 landing the backward edge, and the roadmap must not read 0016 as
  closing Defect 5 independently (source: .factory/items/0016-…/reviews/synthesis.md;
  authorized: judgement on bid-0081). Resolved by: 0015.
- **`ship.obligation` is decorative.** "obligation" appears zero times in
  scripts/, skills/ and commands/, and factory-ship never reads log.jsonl —
  so "high severity, non-blocking, with an obligation" is the ship vote with
  better manners, which is why a high finding with a ~30-line fix cost a full
  rejection; 0013's unpark had to be done by hand. Measured on 0016:
  ride-alongs 1-for-3, obligations 0-for-1, rejections 2-for-2 (source:
  grep over scripts/ skills/ commands/;
  .factory/items/0016-…/reviews/round-2/commercial.md; authorized: judgement
  on bid-0084). Resolved by: a mechanism (ship reads obligations, or an
  engine-filed follow-up item per bid-0054's re-routing rule) or removing the
  disposition.
- **`factory add` records no priority**, so the create verb manufactures the
  degraded no-priority class at 100% and the first cost-breaker fire a new
  operator sees is the worst case. Live instance: 0017 was invisible to
  `factory next` until given a priority by hand (source:
  .factory/items/0016-…/reviews/round-1/commercial.md; authorized: judgement
  on bid-0087). Resolved by: a default or required priority at `factory add`.
- **The cost instrument ships dark.** getting-started.md never names the
  cost gate, `cost-answer`, or the threshold; "threshold" appears zero times
  in cost.py. Off by default and unnamed on every operator surface (source:
  docs/getting-started.md; authorized: judgement on bid-0088). Resolved by:
  an operator-docs pass when 0018 lands, or sooner.
- **The breaker has no ungated advisory mode — and 0016's prose says it
  does.** `breaker.py:105` computes `fired` as requiring `cost in gates`, so
  the CLI advisory print is suppressed on default config: the breaker is
  binary (fully off, or advisory AND hard-gated together). Item 0016's body
  describes "a soft circuit breaker — advisory, not a hard stop", which read
  literally is not what ships. Verified by execution: a genuine rework edge 2
  on default config printed only the stage line and exited 0. Deliberate
  (the no-second-default-gate decision, L2) — the defect is prose describing
  behaviour the code does not have (source: scripts/factory/lib/breaker.py:105;
  scripts/factory/factory.py:195-200; authorized: judgement on bid-0090).
  Resolved by: an advisory-only arm, or correcting the item/doc prose.

- **0005 being blocked now has a named cost.** The cost circuit breaker (0016)
  is a second binding consumer of 0005's generalized `waiting-human` decision
  mechanism — its park is exactly the "one real gate use" 0005 is waiting on.
  Until 0005 unblocks, the breaker renders plain packet text where a clickable
  decision belongs, which delays the affordance on the pipeline's only
  cost-control interrupt. Qualifies the 0005 mandatory-inputs entry (judgement
  on bid-0050) rather than opening a new question (source:
  .factory/items/0016-cost-circuit-breaker-on-engine-authorita/reviews/round-2/customer.md;
  docs/factory/roadmap.md; authorized: judgement on bid-0069).

## Raised by 0013's review council (2026-08-02)

- **`assure.attribution` ships behind an undiscoverable switch.** The paying
  persona has no in-product path to learning the key exists at the moment of
  pain: rule 3's refusal message is byte-pinned, the doctor text render is
  unchanged, and init never rewrites an existing config.json. Until an assure
  rejection surfaces "this fail may be pre-existing — assure.attribution is
  off" (0024 readout scope, or a docs item) and README config docs name the
  key, the UNMEASURED "largest token saver" hypothesis cannot become
  measurable because nobody turns the feature on. Same ships-dark class as the
  cost instrument (bid-0088) (source:
  .factory/items/0013-assure-attribution-gate-only-on-regressi/reviews/round-1/customer.md;
  round-1/commercial.md; round-2/product.md; authorized: judgement on
  bid-0091). Resolved by: 0024 carrying the discoverability line, plus an
  operator-docs pass naming both dark switches.
- **Guard-leak cluster from 0013's review** (each a guard that passes today
  while the property it guards can drift): (a) `CLAIM_RE` in
  tests/test_unmeasured_claims.py misses "cheaper"/"reduces spend" phrasings —
  the recorded pattern-too-narrow class; (b) the AC18 boundary test asserts a
  hand-maintained `ATTRIBUTION_CHECKS` constant rather than deriving the check
  set (mitigated by the source-scan and behavioural tests); (c) base-walk
  spend logging is discipline-not-guarantee (convention adherence 9-of-17)
  (source: .factory/items/0013-assure-attribution-gate-only-on-regressi/reviews/round-1/engineering-quality.md;
  authorized: judgement on bid-0092). Resolved by: folding (a)/(b) into the
  next test-touching item; (c) is the bid-0063/engine-substrate question.

## Raised by 0015's spec (2026-08-02) — recorded assumptions, all reversible

- **Forbidden-approaches artifact path:** `.factory/items/<id>/approaches/forbidden.md`,
  mirroring cost/, design/, assurance/ (authorized: judgement on bid-0099).
- **Approach-cap answer verb/artifact:** `factory approach-answer <id>
  <continue|narrow|defer>` writing `approaches/answer.md`, event
  `approach.answered` — second instance of the `<topic>-answer` precedent
  (bid-0072) (authorized: judgement on bid-0100).
- **Edge request path:** skills request the `approach.rejected` edge via the
  existing `factory advance <id> spec --reason` verb; identification by edge
  shape, reason recorded never parsed (bid-0086 discipline) (authorized:
  judgement on bid-0101).
- **Forbidden artifact lifecycle:** append-only, one dated entry per redesign,
  exempt from all fresh-round cleanups (authorized: judgement on bid-0102).
- **Forbidden entry minimum content:** ts + rejecting stage + approach
  paragraph + repo-relative evidence paths; engine asserts non-emptiness only
  (bid-0053 boundary) (authorized: judgement on bid-0103).
- **Continue-at-cap semantics:** 0016's monotone watermark generalised — a
  recorded answer covering the current edge count admits exactly one more
  edge; engine treats all answers identically; dispatch routes on the option
  — third instance of the bid-0071/0073 seams (authorized: judgement on
  bid-0104).
- **Spec-freshness token:** skill-logged `spec.revised` event used
  fail-closed (absence blocks loudly); ui/mixed old-design-choice residual
  named as a non-goal (authorized: judgement on bid-0105).

- **Stale file evidence survives event round-scoping (0025 residual).**
  Round-scoped gates scope EVENT evidence to the latest non-SPECIAL entry into
  implement, but file evidence (e.g. `_gate_verify`'s reviews/synthesis.md)
  stays a presence/non-emptiness check — a rework round can advance past
  review on a fresh `review.approved` while synthesis.md is round-1's bytes
  (source: .factory/items/0025-…/spec.md Assumptions; authorized: judgement on
  bid-0109). Resolved by: file-evidence freshness (mtime/sha keyed to round)
  if the residual ever ships a stale artifact.
- **B2 refusal-shape scope (0025).** The stale-evidence sentence shape binds
  the four rework gates' refusals; `_gate_ship`'s `assure.confirmed` refusal
  and `record_confirmation`'s nothing-to-confirm refusal are out of scope —
  neither asserts "not logged", so neither is provably false under bid-0083
  (source: .factory/items/0025-…/spec.md; authorized: judgement on bid-0110).

- **Stale-waiver refusal has no specific message or test (0025 review F1).**
  A waiver-only round followed by rework refuses at ship with the incumbent
  generic message — the waiving human gets no signal their specific waiver
  went stale. Named extension of the bid-0110 refusal-shape boundary;
  recommended before 0015 ships its pause surfaces (authorized: judgement on
  bid-0111).
- **Red-run evidence should be stored, not just reproducible.** 0025's
  red/green split is structurally reproducible (tests-only first commit) but
  whether the red run was executed is UNSOURCED; store the executed red tail
  as an artifact the way green evidence is stored (authorized: judgement on
  bid-0112).
- **Engine-written markers are honor-system.** The round-marker predicate
  matches `stage.advance` purely by payload and cannot distinguish an
  engine-written marker from a `factory log`-appended one — bid-0064's
  engine-written-never-skill-logged language overpromises what the substrate
  enforces (authorized: judgement on bid-0113). Resolved by: a writer-source
  discriminator if fabricated markers ever bite.

## Raised by 0015's review council (2026-08-03)

- **Second cap exhaustion escapes the pause contract (HIGH; follow-up must be
  filed before 0015 ships).** Only the absent-answer refusal carries the
  `approach cap:` prefix dispatch parks on; the stale/malformed refusals do
  not, so the first rejection after every recorded `continue` lands in bare
  `blocked` with no `## Redesign decision` packet — contradicting 0015 B5.
  Fix is a spec §7 amendment deciding second-exhaustion routing once for BOTH
  watermark artifacts (approach cap and cost breaker): prefix all three
  refusals AND consume `approaches/answer.md` at resume/admit so no stale
  `continue` can thrash dispatch step-0 — never watermark arithmetic in
  dispatch prose. Bundle with the review/assure route prose (the loop is
  prose-reachable only from verify), factory-review's now-false "lifetime"
  sentence, and the step-0 clause restructure (authorized: judgement on
  bid-0114).
- **`redesign_decision_lines` forks the bid-0066/0077 rendering rules.** A
  second hand-maintained copy of `cost_decision_lines`' backlog/recommendation
  logic (already bid-amended once), plus disagreeing zero-edge defaults for
  the `[proxy]` population strings (packet.py:73 `0` vs :221-222 cumulative
  fallback). Shared-helper extraction must land before any further amendment
  to the 0016 rendering rules, folding the degenerate-fallback mislabel; the
  zero-edge default disagreement alone is a pre-merge one-liner (authorized:
  judgement on bid-0115).
- **Watermarks accept any covering value, not exact match.** Both artifacts
  admit a hand-edited high watermark (`- redesigns: 99` / breaker
  `answered_at >= edges`), indefinitely defeating the lifetime cap; an
  exact-match check closes the runaway-spend hole in both — fold into the
  bid-0114 spec amendment's scope (authorized: judgement on bid-0116).
- **Private-helper promotion trigger has fired (0025 F4, second accretion).**
  `approach.py:16` imports underscore-private `machine._approach_edges`
  alongside assure.py's `_postdates_latest_implement` import; answer the
  promote-to-public question (public names or a small machine query surface)
  in a follow-up before a third instance — the bid-0114 fix touches the same
  modules and is the natural carrier (authorized: judgement on bid-0117).

- **The redesign loop is undiscoverable from review and assure (0015 review,
  product seat).** 0015 ships the `approach.rejected` edge, but only
  factory-verify and factory-dispatch prose route to it: factory-review and
  factory-assure SKILL.md mention neither `approach`, `forbidden` nor
  `redesign`, and their over-cap refusals still terminate in "move item to
  blocked". The motivating incident (ParkSnap) burned its tokens in the
  **review** loop, so the loop's primary entry points may never fire —
  spec-compliant, since AC11 bound only the verify refusal (source:
  .factory/items/0015-…/reviews/attempt-1/round-1/product.md; authorized:
  judgement on bid-0118). Resolved by: extending the redesign-route and
  graveyard-authoring prose to factory-review/factory-assure (or the
  dispatcher's generic failure rule) and rewording the two pinned cap
  refusals at their next re-pin — before the ParkSnap acceptance test leans
  on this loop.

## Raised by 0015's rework review (2026-08-03)

- **A corrected assure verdict un-counts nothing.** `factory log` accepts
  `assure.verdict_corrected` unvalidated, no engine code reads it, and
  `MAX_ASSURE_REJECTIONS` never discounts a superseded `assure.rejected` — so a
  false-positive assure fail permanently consumes an irrecoverable rework slot.
  Live instance: 0015's S5 fail was corrected to pass after three-way
  verification, and the rework edge it caused still counts against the cost
  breaker (source: this item's log; authorized: judgement on bid-0124).
  Resolved by: making the correction event consequential, or accepting that
  corrections are documentation-only and saying so.
- **Review depth should key on the round's change class, not only item tier.**
  `council-review` is binary on tier, so 0015's two-file message-only rework
  delta paid the same six-seat council as its nine-commit base. Directly on
  point for item **0026** (complexity-scored bug flow, filed by the human
  2026-08-02) — its triage should read this as evidence (authorized: judgement
  on bid-0125).
- **The spec-exit gate's both-unmet → both-satisfied repair cycle is
  untested.** AC8's claim is an operator outcome (fix both, exit in one
  advance); the delta's new test refutes only the message half (authorized:
  judgement on bid-0128).
- **`approach.read_answer` collapses distinctions its docstring says it never
  judges:** `_ANSWER_RE`'s `(\S+)` silently rejects any whitespace-bearing
  value, so `admit_over_cap` can describe an artifact state that is not the one
  on disk. Not fixed — widening the regex changes which arm fires (authorized:
  judgement on bid-0129).
- **A `GateError`'s text is not a pause prefix — and that is the mechanism
  under bid-0079.** `breaker.PAUSE_PREFIX` is `"cost breaker:"`
  (`breaker.py:24`) while the unanswered refusal reads
  `"cost breaker unanswered: …"` (`breaker.py:164-168`), which does not match
  it. On the 0079 route the session dies before the park, dispatch writes
  `factory advance ITEM blocked` (`skills/factory-dispatch/SKILL.md:48`), and
  the item is `blocked` with a reason no prefix-keyed packet logic can see —
  so it falls through to `/factory:run`, which re-dispatches into the same
  refusal: a loop, not merely a wrong verb. This is why 0027 scoped the 0079
  route **out**: a reason-keyed selector provably cannot reach it, and widening
  the stage gate at `packet.py:95` buys nothing because `:97` independently
  requires the prefix. Merged into the bid-0079 entry as its missing mechanism
  (source: scripts/factory/lib/breaker.py, skills/factory-dispatch/SKILL.md,
  .factory/items/0027-…/reviews/synthesis.md; authorized: judgement on
  bid-0139). Resolved by: the two remedies already recorded for bid-0079 — a
  refusal that names the packet, or an engine-side park obligation — not by a
  blocked-packet arm.

- **Unrecognised `<topic>:` pause prefixes still fall through to
  `/factory:run`.** 0027 fixes the two known answerable prefixes by hoisting
  reason-prefix arms above stage arms, but a future pause whose prefix no arm
  recognises lands on the generic action again. Reversible default chosen:
  status quo — never raise, never guess a verb, since guessing an answer verb
  for an unknown pause is the false-assurance shape bid-0083 forbids (source:
  .factory/items/0027-…/spec.md; authorized: judgement on bid-0142). Resolved
  by: a registry (explicitly ruled out 5/5 at 0027's triage) or a loud
  unknown-prefix branch, whenever a third answerable pause ships.
- **`packet.py`'s `breaker.verdict(..., "implement")` is hardcoded.** 0027
  leaves the argument inert and commented rather than threading the real
  destination, to stay clear of J-002's `invariance` oracle. Correct for a bug
  item; recorded so the dead argument is not mistaken for a live one (source:
  .factory/items/0027-…/spec.md; authorized: judgement on bid-0143).

## Raised by 0027 review council (2026-08-03)

- **What degradation still yields a usable council verdict?** 0027's review
  council ran with the subagent pool exhausted (200/200), so fan-out was
  impossible and one reasoner executed all three light-review lenses; round 2
  was not run. Independence, the delta round and fresh context are all lost that
  way, and correlated blind spots are not ruled out. Reversible default chosen:
  **proceed, disclose, and substitute execution for seat count** — record a
  § Degradation section in the synthesis naming exactly what was lost, and rest
  the verdict on reproduced experiments rather than on the seat count. This is
  the zero-diff option; the alternative (refuse to review until the pool frees)
  stalls the pipeline for a reason unrelated to the work. Resolved by: a
  measured comparison of orchestrator-played seats against real fan-out on the
  same diff, or a hard rule that a degraded council may only approve, never
  reject (source: .factory/items/0027-…/reviews/synthesis.md; authorized:
  judgement on bid-0147).
