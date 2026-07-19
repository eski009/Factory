# Design principles

> **Defaults, not dogma (assumption).** These ship with the factory as the
> baseline the design stage generates against, the polish battery judges
> against, and the ui-taste seat cites until this product's own taste
> accumulates past them. Strike or amend any of them for this product —
> where a principle conflicts with this product's `design-system.md` or a
> recorded decision, the product wins. The init interview asks you to
> confirm or strike these; an edit here is a product decision like any
> other brain claim.

- **KISS — one job per screen.** Every screen has one primary action; every
  other element earns its place by serving it. If you cannot name the
  screen's job in one sentence, split the screen.
- **Progressive disclosure.** Complexity is available, never ambient:
  advanced options live behind an explicit step; defaults carry the common
  case.
- **Visual hierarchy.** The eye lands where the journey needs it next —
  size, weight, contrast, and position agree about what matters most.
- **Consistency, twice.** Internal: the same intent always looks and acts
  the same across screens. Platform: respect the conventions of the web or
  OS the customer already knows.
- **Feedback and visible state.** Every action is acknowledged where it
  happened; the system never leaves the customer guessing whether
  something worked or is still working.
- **Error prevention over error messages.** Make the wrong action hard to
  take before making its failure polite.
- **Accessible by default.** Real labels, sane focus order, sufficient
  contrast, announced state — semantics first, pixels second.
