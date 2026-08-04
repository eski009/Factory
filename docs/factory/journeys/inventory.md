# Journey inventory

<!-- Every known customer journey, one entry per journey: id (J-NNN), title,
     persona, trigger, intended outcome, criticality (core|high|standard).
     graph.json is the machine-readable index of this list; deep contracts
     live in contracts/ and exist only where they earn their keep (core,
     high-risk, touched by current work, implicated by an escape). Every
     claim cites a source: (source: <path-or-url>) or is tagged (assumption). -->

_Brownfield intake infers an inventory from routes, screens, navigation, and the
test suite; the init interview asks the owner about the gaps; the spec stage
registers new journeys as work introduces them. This list is not yet complete —
entries below were registered by the work that touched them._

- **J-001 — Assure outcome readout** (`assure-outcome-readout`, criticality
  `high`, status `draft`, contract `contracts/J-001-assure-outcome-readout.md`).
  Persona: The Overnight Operator (source: docs/factory/brain/personas.md).
  Trigger: an item's assure walk produces at least one non-`pass` scenario
  verdict. Outcome: the operator can tell from the packet's first screen and
  `factory status --json` whether the item shipped with known non-blocking fails
  — each terminating in an open owning item — or was blocked and reworked, and
  has exactly one next action (source:
  .factory/items/0013-assure-attribution-gate-only-on-regressi/spec.md).
- **J-002 — Cost breaker decision** (`cost-breaker-decision`, criticality
  `high`, status `draft`, contract `contracts/J-002-cost-breaker-decision.md`).
  Persona: The Overnight Operator (source: docs/factory/brain/personas.md).
  Trigger: an item enters an implement round with rework edges at or above the
  threshold while `"cost"` is in the configured gates. Outcome: the operator
  learns from the packet alone what the item has consumed, what it is blocking,
  and the consequence of each of continue / narrow / defer, and records one with
  a single command that provably unblocks the item exactly once (source:
  .factory/items/0016-cost-circuit-breaker-on-engine-authorita/spec.md).
- **J-003 — Redesign cap decision** (`redesign-cap-decision`, criticality
  `high`, status `draft`, contract `contracts/J-003-redesign-cap-decision.md`).
  Persona: The Overnight Operator (source: docs/factory/brain/personas.md).
  Trigger: an `approach.rejected` request arrives when the item's
  engine-counted approach.rejected edges already equal
  `MAX_APPROACH_REJECTIONS`. Outcome: the operator learns from the packet alone
  what redesigns and rework the item consumed, what the forbidden-approaches
  record says cannot converge, and records continue/narrow/defer with a single
  command that provably unblocks exactly once (source:
  .factory/items/0015-approach-rejected-a-redesign-loop-back-t/spec.md).
- **J-004 — Bug door intake** (`bug-door-intake`, criticality `high`, status
  `draft`, contract `contracts/J-004-bug-door-intake.md`). Persona: The Overnight
  Operator (source: docs/factory/brain/personas.md). Trigger: a human reports a
  defect at any intake door (`/factory:bug`, `/factory:add`, `/factory:do`, or a
  roadmap batch). Outcome: the defect is filed with its materiality tier
  (`tier`) and its evidence claim (`bug: true`) recorded separately, a confirmed
  repro exists before any fix work, the item is visible in
  `docs/factory/roadmap.md` and `factory status`, and its packet prints the depth
  profile its tier selects and the intake path it took (source:
  .factory/items/0026-complexity-scored-bug-flow-bugs-run-a-su/spec.md).
