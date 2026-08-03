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

## Learned from item 0015's review (2026-08-03)

- **A walk that finds a defect must bid its known twin in the same pass.**
  0015 fixed a leaked Python `None` repr in `approach.py`'s malformed-answer
  refusal while the module it names as its own precedent (`breaker.py:169-172`)
  emits the identical leak on the live cost-breaker operator path. A fix that
  leaves its declared twin broken is half a fix: when a module cites another as
  its model, a defect found in one is a finding against both (authorized:
  judgement on bid-0121).
- **Every human-answer pause artifact needs a present-but-unparseable branch.**
  Dispatch resumes an answered pause only when the artifact records a valid
  option; a present-but-corrupt artifact matches no branch, so the item stays
  silently parked with the operator believing it was answered. The five-part
  pause contract (bid-0065) covers absent and valid, never malformed
  (authorized: judgement on bid-0123).
- **A record correction rides with the fix that caused it.** When a walk
  finding changes shipped behaviour, the acceptance criterion, the journey
  oracle, the verify record and the assurance verdict are amended in the same
  pass — otherwise the ship record asserts things the code no longer does.
  0015's fifth refusal arm left four surfaces stale, and the treatment was
  uneven: S5 got a dated correction, S6 did not (authorized: judgement on
  bid-0126).
