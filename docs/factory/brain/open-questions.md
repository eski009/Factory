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
  affirm CLI-argument gating as the convention.
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
