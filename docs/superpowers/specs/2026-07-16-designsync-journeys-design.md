# DesignSync journeys — visual maps, greenfield frame-pull, node-annotated mockups

- **Date:** 2026-07-16
- **Status:** Approved design
- **Topic:** Extend the existing DesignSync capability (`mcp__claude-design__*`) so the
  journey model becomes visible in the linked Claude Design project, greenfield repos get
  a journey-inventory head start from design frames, and the design gate carries journey
  context. Prose-only; no engine changes.

## Decisions

1. **Same capability, same doctrine.** No new capability row: everything rides the
   existing DesignSync probe, its interactive-only constraint, degrade-never-block,
   proxy spend logging, and "never a second source of truth" (repo files canonical).
   Unattended runs simply lack the tools and fall through.
2. **Visual journey map — push-only convenience view.** The three surfaces that mutate
   `docs/factory/journeys/` regenerate a single self-contained HTML flow view
   (`factory-journeys.html`, built from `graph.json`: nodes, transitions, criticality,
   contract status) in the linked project via `mcp__claude-design__write_files`:
   factory-intake at the end of seeding, factory-spec when it registers a journey or
   drafts a contract, and `/factory:escape` after a promotion amends a contract. Each
   push replaces the previous file, is strictly best-effort/non-blocking, and logs one
   proxy spend event.
3. **Greenfield frame-pull at intake.** In greenfield mode (nothing to mine), when the
   capability is present AND `designsync_project` is configured, factory-intake pulls the
   linked project's frame/flow structure (`list_files` + `read_file`) and emits
   journey-inventory entries from screen sequences: cited
   `(source: claude-design <project>/<file>)`, criticality tagged `(assumption)`,
   `status: inventory`, never contracts. The init interview then harvests those
   assumptions automatically — zero interview changes. Without the capability, greenfield
   behavior is unchanged (templates stay placeholder; the interview asks).
4. **Node-annotated design gate.** factory-design's existing DesignSync pushes gain
   journey context from the item's `impact.json`: each pushed mockup option is annotated
   with the journey nodes its screens serve, and the chosen-direction note includes the
   node mapping. After the human's pick, factory-design MAY refresh the touched nodes'
   "what the customer expects" text in any affected **draft** contract, citing the chosen
   option — never an approved contract (those amend only through the judgement firewall).
5. **Assure stays out.** No design-project artifact ever substitutes for running-product
   evidence; the assure stage and journey-reviewer are untouched.

## Files touched

- **Edit:** `skills/capabilities/references/designsync.md` — new `## Journeys` section
  documenting the three pushes + the greenfield pull + the constraints above.
- **Edit:** `skills/factory-intake/SKILL.md` — greenfield frame-pull collector +
  journey-map push at seeding end.
- **Edit:** `skills/factory-spec/SKILL.md` — map push on register/draft (one sentence in
  duty 1).
- **Edit:** `commands/escape.md` — map push after a `contract:` promotion.
- **Edit:** `skills/factory-design/SKILL.md` — option/choice node annotations +
  draft-contract expectation refresh.
- **Tests:** structure pins for each surface.
- **Docs:** CHANGELOG 0.9.0 + plugin.json bump.

## Non-goals

- No engine changes, no new schemas, no new capability row, no assure-stage involvement,
  no pulls into approved contracts, no headless behavior change.
