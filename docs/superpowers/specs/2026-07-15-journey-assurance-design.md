# Journey Assurance — a first-class `assure` stage

- **Date:** 2026-07-15
- **Status:** Approved design, pending spec review
- **Topic:** Prove that a customer can coherently complete the affected journey — not just
  that tasks were implemented, the council found no blocking issues, and tests passed —
  before an item may ship.

## Problem

Factory currently proves four things: tasks were implemented, the council found no
blocking diff issues, tests passed, and each written acceptance criterion was exercised.
It does **not** prove that a customer can coherently complete the journey the change sits
inside. Concretely, verified against the code:

- The ship gate requires only a `verify.green` event (`machine.py` `_gate_ship`); it never
  reads `verify.md`, and `factory-verify`'s own prose says so.
- `factory-review`'s end-to-end walk is a **static code trace** — entry point → data →
  output through files and functions, following the flow behind the spec's *first*
  acceptance criterion. Council seats hold Read/Grep/Glob only; nobody sees the running
  system.
- `factory-verify` exercises changed behavior with real commands, but it runs **inline in
  the same dispatcher session** that carried the item through implement and review — an
  invested context that can interpret ambiguous acceptance criteria generously.
  (Implementers are fresh subagents; the *evaluator* is not.)
- There is no durable journey inventory, no feature-to-journey impact map, no mandatory
  fresh-context review of the running product with screenshot/console/network evidence,
  and no register that converts the human's post-ship discoveries into permanent
  assurance.

That is why Factory can legitimately say "green" while a human walkthrough still finds
something obviously wrong, missing, or confusing. The human is the *first* person to walk
the journey; they should be the *last*.

## Decisions (locked during brainstorming)

1. **First-class stage.** `assure` is inserted between `verify` and `ship`. Review asks
   "is the code sound"; verify asks "do the checks pass"; assure asks "can the customer
   get through it"; the human confirms meaning and taste. `verify.green` alone no longer
   admits an item to ship.
2. **Scope — all journey-affecting items, surface-appropriate.** Every item whose spec
   declares journey impact enters assure, whatever its kind. The reviewer drives the
   surface the journey declares: a browser for web UI (screenshots, console, network
   mandatory), real CLI/API calls with typed transcripts for backend journeys. Items whose
   spec explicitly declares "no customer journey affected" skip assure through the engine's
   `stage_sequence` mechanism — an enforced skip, never an omission.
3. **Browser capability is behavioral, not tool-pinned.** The capability is "a tool that
   can navigate, click, type, screenshot, and read console/network," matched against known
   families (Playwright MCP, chrome-devtools MCP, Claude-in-Chrome). Whichever is present
   gets used; absent, browser-borne journeys park `waiting-human` with a blocker packet —
   fail-closed to a human, never silently green, and never a stage *failure* (the
   capabilities doctrine survives: parking is not failing).
4. **Fresh subagent now, cross-backend later.** v1 dispatches the journey reviewer as a
   fresh in-process subagent — no implementer transcript, no prior reviewers' conclusions,
   no claim the feature is "complete" — on the most-capable model tier, and on a different
   model from the implementer where the session supports overrides. Running assurance
   under a heterogeneous headless backend (e.g. codex while implement ran claude) is a
   named later phase that reuses the workers executor; it is out of scope for v1.
5. **Two-level journey model.** A lightweight inventory covers every known journey; deep
   contracts exist only for core journeys, high-risk journeys, journeys touched by current
   work, and journeys implicated by an escape.
6. **Split write regime.** `graph.json` + `inventory.md` are roadmap-like (stage skills
   maintain them directly). `contracts/` are brain-like: drafts may be authored directly
   by a stage skill, but amending an *approved* contract goes through the
   council-judgement firewall.
7. **Round-scoped evidence, confined to the new gate.** The ship gate requires the
   assurance event to have been logged *after* the latest `implement.completed` — the
   engine's first round-scoped evidence check. `verify.green` keeps its existing lifetime
   semantics; widening round-scoping is explicitly not this design's job.
8. **Human confirmation rides the existing autonomy dial.** `"assure"` becomes a legal
   member of the config `gates` list. Gated: the item parks after `assure.passed` with a
   confirmation packet and a human-only `factory confirm` resumes it. Ungated: the packet
   is still produced (to `packets/reports/`) and flow continues.
9. **Escapes stay open until promoted.** A human discovery post-assurance becomes an
   append-only escape record, closed only by promotion into a contract amendment,
   deterministic regression test, acceptance oracle, council review rule, or brain
   decision.
10. **No pilot target.** The design is target-agnostic; no product-specific pilot is part
    of this spec.

## Architecture

### Engine (deterministic layer)

**Stage and routing.** `assure` joins `STAGES` between `verify` and `ship`
(`machine.py`). A new optional item frontmatter field `journeys` (strict-whitelist
addition to `items.py` FIELD_ORDER and `schemas/work-item.schema.json`) holds `none` or
comma-separated journey IDs (`J-004,J-011`). `stage_sequence` skips assure when
`journeys: none` — the same mechanism by which backend items skip design. Absent is *not*
`none`: absent means "never declared." A new verb `factory journeys <id> <none|J-004,...>`
sets the field and logs a `journeys.set` event, mirroring `factory tier`.

**Spec-exit gates hardened.** `_gate_design` and `_gate_plan` additionally require (a) the
literal `## Journey impact` heading in `spec.md` (precedent: the plan gate requires
`- [ ]`), and (b) the `journeys` frontmatter to be set. `none` is a valid answer; an
omitted one refuses to advance.

**Gates around the new stage.**

- `_gate_assure` (entering assure): requires the `verify.green` event — ship's old
  requirement moves back one stage.
- `_gate_ship` (entering ship), for `journeys ≠ none`: requires
  `.factory/items/<id>/assurance/verdicts.json` that (1) schema-validates, (2) covers
  every declared journey ID and every scenario `impact.json` requires, (3) references
  evidence files that exist on disk, and (4) contains no `fail` or unresolved `ambiguity`
  verdict — **plus** an `assure.passed` event logged *after* the latest
  `implement.completed` event in `log.jsonl`, **or** an `assure.waived` event similarly
  post-rework. For `journeys: none`, the ship gate remains `verify.green`.
- Gates keep today's division of labor: they check artifact shape, presence, coverage, and
  event ordering — never journey coherence. They fail closed on unreadable evidence, per
  the existing `_read_text_or_empty` semantics.

**Second backward edge.** An assurance failure routes `assure → implement`, mirroring the
review rework loop with its own counter: `assure.rejected {round: N}`, lifetime cap 2
(`MAX_ASSURE_REJECTIONS`), beyond which the item goes `blocked` with a packet.

**Human-only verbs.** `factory waive <id> --reason "..."` logs `assure.waived` with the
rationale and refuses an empty reason. `factory confirm <id>` logs `assure.confirmed` and
resumes a gated item to ship. Both follow the `factory choice` single-writer doctrine:
no skill or autopilot path ever invokes them, enforced by coherence tripwire tests (the
factory-interview reachability pattern).

**Escape Register.** A fourth append-only ledger, `.factory/ledgers/escapes.jsonl`,
schema-validated per line (`schemas/escape.schema.json`): id, item (or none), journey,
node, finding, `miss_type` (`missing-journey | missing-node | missing-oracle |
missing-contract-detail | review-rule-gap`), evidence paths, status
(`open | promoted`), promotion reference. `factory escape` appends;
`factory promote <escape-id> --via <judgement-id | test:path | contract:path |
oracle:ref | decision:ref>` closes one. `factory validate` cross-checks promotion
references (the bid↔judgement integrity pattern); `factory status` surfaces the open
count.

**Peripherals.** `tiers.py` DEFAULTS gain an `assure` key (`epic: full`,
`feature: affected`, `bug: node`), whitelisted in config tier blocks and exposed via
`factory doctor --json`; gates stay tier-blind (consumption is skill prose, consistent
with research/review today). `packet.py` ARTIFACTS gains the assurance artifacts, and the
assure packet's Respond footer names the one CLI answer path (`factory waive` /
`factory confirm`). `validate_tree` learns the new schemas (verdicts, impact, escapes,
and `docs/factory/journeys/graph.json` when present). `config.schema.json`: `"assure"`
joins the `gates` enum; tier blocks accept the `assure` key. Dispatch's step-0 resume
check learns the second answered-pause type (paused-from `assure` with a waiver or
confirmation recorded).

### Journey model

Layout, in the target repo, sibling to the brain:

```text
docs/factory/journeys/
  graph.json        # machine-readable index; schema-validated when present
  inventory.md      # human-readable journey list, cited
  contracts/
    J-004-invite-and-onboard.md
```

**Index.** Every journey gets a `graph.json` entry: stable ID (`J-NNN`), slug, title,
persona, trigger, intended outcome, criticality (`core | high | standard`), status
(`inventory | draft | approved`), links (routes, screens, APIs, tests), and a contract
path or `null`.

**Deep contracts** cover: persona and starting state, customer trigger and desired
outcome, steps and transitions as named nodes (`N1…Nn`), what the customer knows at each
step and expects next, trust and reassurance requirements, interruption/failure/recovery
paths, deterministic oracles, AI judgement questions, required evidence per surface, a
Run & fixtures section (exact launch commands, fixture setup, credentials through safe
fixture mechanisms), and an optional whitelist of known console noise.

**Seeding.** `templates/docs-factory/journeys/` (inventory carrying the exact
`_Not yet written.` marker, a skeleton `graph.json`) is copied by `factory init`
fill-gaps-only — existing init machinery, no new code path. Brownfield `factory-intake`
gains one collector: the routes/screens/navigation mining and test-suite-as-behavior-spec
reading it already performs also emit inferred inventory entries — every entry cited,
criticality tagged `(assumption)`. Intake's write-license (currently brain +
taste packet only) is explicitly widened to include `docs/factory/journeys/`. The init
interview harvests the placeholder and the `(assumption)` criticalities automatically via
its existing `_Not yet written.` and assumption harvesting — zero interview changes. All
seeding sits behind the existing verbatim brain hard gate.

**Write regime.** `graph.json` + `inventory.md`: stage-maintained directly (factory-spec
may register a new journey as an inventory-only entry the way triage writes
`roadmap.md`). `contracts/`: drafts (`status: draft`) may be authored directly by a stage
skill when an item needs one; **amending an approved contract requires a
council-judgement bid** with `--surface journeys/contracts/<file>` — which is also how
escape promotions into contracts land. Assurance may run against a draft contract, but
the confirmation packet flags it ("contract is draft; confirm it reflects intent") so the
human approves contracts on the same pass where they confirm the work. Per-item assurance
state never pollutes `journeys/`; it lives in `.factory/items/<id>/assurance/`.

### Feature journey-impact contract (spec stage)

`## Journey impact` becomes a required `spec.md` section, defined in both synced section
lists (`skills/factory-spec/SKILL.md` and `agents/spec-writer.md`), between Behavior and
Non-goals: affected journey IDs, nodes changed, transitions changed, new states
introduced, and required assurance scenarios (happy path, recovery paths, viewport
requirements where the surface is a browser). The valid empty form is
`None — no customer journey affected.` plus a one-line justification.

factory-spec gains three mechanical duties, in order:

1. **Map** — read `graph.json` + `inventory.md`; map the item's behavior onto journey
   nodes. An item that introduces a journey registers it as an inventory-only entry. Any
   affected journey lacking a contract gets a **draft contract** — minimal (touched nodes
   plus oracles for the required scenarios), with depth scaled by tier. By the time an
   item reaches assure, every affected journey has at least a draft contract.
2. **Declare** — write the section into `spec.md` *and* its machine-readable twin
   `.factory/items/<id>/assurance/impact.json` (schema-validated; the assure gate
   cross-checks verdict coverage against it, node by node and scenario by scenario).
3. **Set** — run `factory journeys <id> <none|J-004,...>`, exactly as triage runs
   `factory tier`.

**Bug symmetry.** `factory-bug` already seeds acceptance criteria at intake under a
"carry into spec.md verbatim" heading; it gains the same for journey impact. Replication
identifies the broken node precisely, so bug intake seeds `## Journey impact` with the
changed node + immediate transition (matching the bug tier's assure depth), and
factory-spec carries it verbatim.

Triage and roadmap stay out of it — they may mention likely journeys in prose, but the
binding declaration happens at spec, where behavior is defined. One declaration point,
one enforcement point.

### The assure stage (skill + fresh-context reviewer)

**Orchestration.** Dispatch maps `assure → factory-assure` and invokes it normally. The
skill dispatches **one fresh journey-reviewer subagent per affected journey**
(sequential), logging spend per fan-out per house convention. The reviewer prompt is
composed *only* from an enumerated input allowlist:

- product brain persona surfaces (`personas.md`, `users.md`)
- that journey's contract (draft or approved)
- the item's `impact.json`
- run + fixture instructions from the contract's Run & fixtures section
- credentials through the contract's fixture mechanisms

— structurally excluding the implementer transcript, review/verify conclusions, and any
"this is complete" framing. The reviewer runs at the most-capable model tier per the
model-tiering reference, on a different model from the implementer where the session
supports overrides. (`agents/journey-reviewer.md`; unlike council seats it holds the
tools needed to run and drive the app, not Read/Grep/Glob only.)

**The walk.** Per node, the reviewer follows the eight-step loop: (1) state what the
customer currently knows, (2) predict what the customer expects next, (3) perform the
action, (4) compare expected vs actual, (5) capture screenshot/DOM evidence, (6) inspect
console errors, (7) inspect network failures or unexpected requests, (8) record
`pass | fail | ambiguity | blocker`. Expectations are written to `expectations.md`
**before** acting — predictions, not rationalizations. Material console errors and
unexpected 4xx/5xx are fails unless the contract whitelists them.

**Surface drivers.** Browser-borne journeys require the browser capability (behavioral
probe over known families, per Decision 3). CLI/API journeys are driven through the real
commands a customer or caller would run, with typed transcript evidence in place of
screenshots. `run-manifest.json` records exactly what was launched and driven.

**Evidence** lands in `.factory/items/<id>/assurance/` (current round; history lives in
git):

```text
.factory/items/<id>/assurance/
  impact.json           # written at spec
  run-manifest.json
  expectations.md
  verdicts.json         # per journey, per scenario, per node; typed evidence refs
  screenshots/
  console.ndjson
  network.ndjson
  blockers.md
  human-confirmation.md # when the assure gate is configured
```

**Exit semantics — three distinct outcomes:**

- **All pass** → log `assure.passed`, advance toward ship (parking first when `"assure"`
  is in config `gates`).
- **Any fail** (objective expectation mismatch) → log `assure.rejected {round: N}`,
  advance back to implement; cap 2, then blocked with a packet.
- **Ambiguity or blocker** — the app cannot be launched, a fixture is missing, the
  browser family is absent for a browser journey, or a judgement call the contract does
  not settle → record in `blockers.md`/`verdicts.json`, park `waiting-human` with a
  packet. **Never** silent degradation to "inspection passed." The human answers with
  `factory waive --reason`, or fixes the environment and the stage re-runs.

Verify and review keep their jobs untouched: verify remains criterion-level evidence,
review remains code-level soundness. The judgement split is deliberate — deterministic
system: routes, state transitions, test results, persistence, console/network failures,
evidence completeness; independent AI: clarity, coherence, next-action obviousness,
trust, expectation mismatch, cross-screen continuity; human: product meaning and taste.
Assurance exists so the human is rarely the first to discover basic incoherence — never
to replace the final human taste decision.

### Human confirmation and the escape loop

**Confirmation packet.** Produced whenever assurance passes: journeys affected,
before/after expectations, verdicts, evidence links, unresolved judgement calls, a
recommended confirmation walkthrough, and any draft-contract flags. Gated
(`"assure"` ∈ `gates`): the item parks `waiting-human` with the packet in
`docs/factory/packets/` and `factory confirm <id>` resumes it; the confirmation is
recorded in `human-confirmation.md`. Ungated: the packet goes to
`docs/factory/packets/reports/` (excluded from the SessionStart "awaiting review"
listing) and flow continues.

**Escapes.** Anything a human still finds becomes an escape via `factory escape`
(classification flow: a thin `/factory:escape` command wraps the CLI — classify the miss
type conversationally, file the record, and when the finding is functional also file a
`/factory:bug` item linked from the escape record; an incoherence escape may promote
without one). An escape stays `open` until `factory promote` links it to at least one of:
amended journey contract (through the firewall), deterministic regression test,
acceptance oracle, council review rule, or product-brain decision. This is the
compounding loop: human escape → classify the missing journey/state/oracle → improve the
contract/check → future assurance catches it → fewer human discoveries.

## Edge cases

- **`journeys: none` items** — skip assure entirely (engine `stage_sequence`); ship gate
  stays `verify.green`. The declaration is explicit and human-visible in `spec.md`.
- **Mid-flight migration** — items already past spec never hit the hardened spec-exit
  gates; an item arriving at assure without a declaration parks with a packet, and one
  `factory journeys <id> none` or a waiver unblocks it. Changelog documents this.
- **Browser family absent** for a browser-borne journey — blocker, park `waiting-human`;
  never a silent pass, never a hard stage failure (parking preserves the capabilities
  doctrine).
- **App cannot be launched / fixture missing** — same blocker path.
- **Draft contract** — assurance runs, packet flags the draft for human approval.
- **Rework staleness** — after an `assure → implement` bounce, the previous
  `assure.passed` no longer satisfies ship (round-scoped event ordering); the item must
  re-earn assurance.
- **Ambiguity vs fail** — objective mismatch reworks; judgement calls park for a human.
  The reviewer never resolves its own ambiguities.
- **Autopilot** — never calls `factory waive`, `factory confirm`, or answers an assure
  packet; parked items stay parked (tripwire-tested, the interview-reachability pattern).
- **Re-runs** — the assure stage overwrites the current round's assurance artifacts;
  `impact.json` is only rewritten at spec.

## Files touched

**Engine (new/edit):** `scripts/factory/lib/machine.py` (stage, gates, second backward
edge, round-scoped check), `items.py` (`journeys` field), `factory.py` (verbs:
`journeys`, `waive`, `confirm`, `escape`, `promote`), `tiers.py` (+`assure` key),
`packet.py`, `initrepo.py`/`validate` additions, new `schemas/`
(`assurance-impact.schema.json`, `assurance-verdicts.schema.json`,
`escape.schema.json`, `journey-graph.schema.json`), `config.schema.json`,
`work-item.schema.json`.

**Templates (new):** `templates/docs-factory/journeys/` (inventory.md, graph.json,
contract template reference).

**Skills/agents (new):** `skills/factory-assure/SKILL.md`, `agents/journey-reviewer.md`,
`skills/capabilities/references/browser-drive.md` (+ capability row).

**Skills (edit):** `factory-dispatch` (stage map row, resume types), `factory-spec` +
`agents/spec-writer.md` (section + duties), `factory-bug` (impact seeding),
`factory-intake` (journeys collector + write-license), `factory-ship` (entry note),
`factory-autopilot` (gate-respect additions), `commands/` (new `/factory:escape`).

**Docs:** README, getting-started, CHANGELOG.

## Testing

- **Engine unittests:** stage routing incl. `journeys: none` skip; hardened spec-exit
  gates; assure-gate artifact validation, coverage cross-check, and round-scoped event
  ordering; ship-gate branch; verb behaviors and tripwires; escapes schema + promotion
  integrity; tiers `assure` key; packet rendering; validate additions; mid-flight
  migration behavior.
- **Structure/coherence:** pins for the new skill, agent, dispatch row and stage-map
  regex, spec section lists staying synced, intake write-license, human-only verb
  tripwires.
- **Pipeline walk:** the existing end-to-end walk test extended through assure with stub
  evidence artifacts.
- **Behavioral (manual dogfood):** a scratch web app driven end-to-end — inventory
  seeding, impact declaration, a real browser assurance run producing evidence, a forced
  fail routing back to implement, a waiver, an escape filed and promoted.

## Implementation sequence — one spec, four plans

1. **Engine** — stage, gates, frontmatter, five verbs, schemas, tiers key, packet,
   validate. Pure Python + tests.
2. **Journey model + spec impact** — templates, intake collector + write-license,
   factory-spec + spec-writer duties, factory-bug seeding.
3. **Assurance runner** — factory-assure skill, journey-reviewer agent, browser-drive
   capability reference, dispatch wiring.
4. **Confirmation + escapes** — gate integration, dispatch resume types,
   `/factory:escape` flow, promotion checks, docs.

## Non-goals / out of scope

- No product-specific pilot (target-agnostic design).
- No slimming of review's end-to-end walk — it keeps its code-level job.
- No round-scoping for `verify.green` or other existing gates — confined to assure.
- No heterogeneous headless backend for the reviewer in v1 — a named later phase reusing
  the workers executor (assure-shaped brief, per-stage backend override).
- No changes to the design gate, council protocol, or memory firewall semantics beyond
  the journeys surface addition.
