# Design principles — a seeded, overridable UI baseline

- **Date:** 2026-07-19
- **Status:** Approved design
- **Topic:** Ship a curated set of universal UI principles (KISS, progressive
  disclosure, hierarchy, consistency, feedback, error prevention, accessibility) as a
  brain surface — defaults the product can strike or amend — and wire the three
  consumers that currently judge against nothing-in-particular: design generation, the
  polish battery, and the ui-taste council seat.

## Decisions

1. **A brain surface, shipped WITH content.** `templates/docs-factory/brain/
   design-principles.md` carries the seven defaults plus a header declaring them
   "defaults, not dogma — strike or amend for this product," tagged `(assumption)` so
   the init interview automatically asks the owner to confirm/strike them (its
   existing assumption-harvest; one enumeration edit adds the surface). Post-seed
   amendments go through the council-judgement firewall like any brain edit; the
   human hard gate covers first review. Unlike other brain templates it ships
   content-bearing (principles are defaults, not product claims — no evidence-
   discipline violation), so doctor/placeholder machinery is untouched.
2. **Three consumers, three one-line wirings.** factory-design generates mockup
   directions *against* the principles (read-first + generation guidance);
   the polish battery's density/consistency questions anchor to the file
   ("against `design-system.md` and `brain/design-principles.md` where present");
   the ui-taste council seat reads it alongside design-system.md and may cite
   principles in bids until product-specific taste accumulates.
3. **Principles lose to the product.** Where design-principles.md and the product's
   own design-system.md or recorded decisions conflict, the product wins — state
   this in the template header and in factory-design's wiring. An advisory citing a
   struck principle is a reviewer error.
4. **No engine changes.** Template copy rides `factory init` fill-gaps-only;
   validate/doctor/gates untouched.

## Files touched

- **New:** `templates/docs-factory/brain/design-principles.md`.
- **Edit:** `skills/factory-design/SKILL.md` (read-first + generate-against),
  `skills/factory-spec/SKILL.md` (battery anchor), `agents/journey-reviewer.md`
  (judge-against anchor in step 9's bar), `agents/council-ui-taste.md` (read
  alongside design-system), `skills/factory-interview/SKILL.md` (source-2
  enumeration gains the surface).
- **Tests:** structure pins (template exists + key principles + defaults-not-dogma
  header; wiring pins per consumer).
- **Docs:** CHANGELOG 0.11.0 + plugin.json bump.

## Non-goals

- No new engine surface, no doctor readout, no enforcement gate — principles bind
  through generation, advisories, and bids, never through `machine.py`.
- No principle inventing beyond the curated seven; no product-specific content in
  the template.
