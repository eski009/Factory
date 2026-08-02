# Polish battery — the journey reviewer's world-class bar

- **Date:** 2026-07-18
- **Status:** Approved design
- **Topic:** Operationalize journey-contract "AI judgement questions" with a default
  per-node polish battery, split polish findings into blocking craft defects vs
  non-blocking advisories, and write the reviewer's quality bar down. Goal: the assure
  stage actively drives brownfield toward a production-ready product that looks the
  part — while taste authority stays with the human.

## Decisions

1. **Objective craft defects are fails, not taste.** Clipping/overflow, broken images,
   unstyled error/empty states, placeholder or lorem content, layout collapse at a
   scenario's declared viewport: a customer sees these, no contract needed to settle
   them. They take the existing `fail` path (assure.rejected → rework), so the rework
   loop itself raises the floor.
2. **A default polish battery per touched node.** factory-spec's contract drafting
   seeds four AI judgement questions on every touched node (authors may add more,
   never fewer): density — "what on this screen is not needed for what the customer is
   doing at this node?"; craft — "what would a first-time customer visually notice as
   unfinished?"; consistency — "does this screen read as the same product as the
   previous node (type, color, spacing rhythm — against `design-system.md` where
   seeded)?"; trust — "would a first-time customer trust this screen with their data
   or money?".
3. **Subjective findings are advisories, not parks.** Judgement-question answers that
   name something (anything non-empty) are collected into a `## Polish` section of the
   assure packet — every run, gated or not. They do NOT fail the gate and do NOT park
   the item (a per-nit park would halt every ui item forever). The human adjudicates
   at confirmation: a ratified finding becomes an escape promotion or a contract
   amendment, at which point it binds future runs (a settled question stops being
   advisory). `ambiguity` keeps its existing meaning — a judgement call that blocks
   the walk itself.
4. **The bar is written down.** `agents/journey-reviewer.md` gains an explicit
   standard: judge as a demanding first-time customer of a world-class product; name
   what such a customer would notice or distrust; never soften because the pipeline
   "worked hard." Bounded by the same discipline: objective → fail; nameable-but-
   subjective → advisory; never self-resolve taste.
5. **No engine changes.** verdicts.json already carries `notes`; the Polish section is
   packet prose composed by the orchestrator from reviewer reports. Gates unchanged.

## Files touched

- `skills/factory-spec/SKILL.md` — drafting duty seeds the default battery.
- `agents/journey-reviewer.md` — answer every contract judgement question per node;
  the bar; the objective/advisory split.
- `skills/factory-assure/SKILL.md` — orchestrator collects answers into the packet's
  `## Polish` section; advisories never park or fail; ratified findings promote.
- Structure pins for all three.

## Non-goals

- No engine/schema changes; no mockup-resemblance checking (taste stays human); no
  change to ambiguity/blocker semantics; no new stage or verbs.
