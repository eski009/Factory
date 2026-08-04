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
- **A pause's decision screen and its answer verb must come from one
  predicate.** Two renderers reading two copies of the same condition is how
  the screen and the verb come to disagree — and it fails in *both* directions:
  a decision screen with no verb under it, or a verb rendered under a suppressed
  screen. `packet.py:95-98` computes the cost-screen predicate from `meta`
  alone while `:331` recomputes an overlapping condition for the verb, and both
  are called from `:376` and `:559`. Enforce the coupling in code where the
  predicate can be extracted; assert it in tests where it cannot (authorized:
  judgement on bid-0138).
- **A suite whose fixtures all seed one value of a branch key cannot see a
  branch-key defect.** `tests/test_packet.py:113-137` hardcodes
  `"stage": "implement"` for every cost-breaker fixture, so ~25 assertions plus
  the HTML twin exercise a single value of the key the defect lives on: the fix
  is green-to-green and "the suite passes" carries no signal. The falsifier must
  be a **coupling invariant over rendered output**, not an enumeration of the
  stages someone happened to list — and it must be checked in both directions
  and on the rendered artifact the operator actually reads (authorized:
  judgement on bid-0141).

## Learned from item 0027 review (2026-08-03)

- **A RECOMMENDED remedy in a spec can be unsound; an implementer declining it
  is a finding, not an omission.** 0027's spec §3 recommended that the
  cost-decision screen predicate and the answer-verb arm consume one shared
  `is_cost_pause(meta)` helper, "so the section and its verb cannot disagree by
  construction". Applied literally, that helper carries the `waiting-human`
  conjunct into the verb arm and returns a `blocked` cost pause to the generic
  `/factory:run` line — the re-dispatch loop triage identified. Review must test
  a SHOULD for **soundness**, not for compliance; a compliance-only review would
  have demanded the regression (source:
  .factory/items/0027-…/reviews/round-1/architecture.md,
  .factory/items/0027-…/spec.md, scripts/factory/lib/packet.py; authorized:
  judgement on bid-0145).
- **Red-first is verifiable after the fact, and review should verify it.**
  Running the branch's tests against the **base commit's** production code
  (branch tests, `main` `scripts/factory/lib/*`) turns "the new tests are a
  falsifier" from an implementer's assertion into a reviewed number. On 0027 it
  returned 21 of 27 red, and 7 of 11 against a reconstruction of the specific
  forbidden variant (the `paused_from == "implement"` conjunct deleted in place,
  leaving the cost arm below the `assure` arm). It also identifies precisely
  which assertions are vacuous: 0027's AC11 distinctness **count** and its AC6
  bullet⇒section direction pass unchanged on head, while the `assertNotIn("None",
  …)` and the anti-shadowing test are what actually go red. Extends bid-0141
  (source: .factory/items/0027-…/reviews/round-1/engineering-quality.md,
  .factory/items/0027-…/reviews/synthesis.md; authorized: judgement on
  bid-0146).
- **A discharge sweeps the mechanism, not the cited instance.** When a finding
  names one surface of a mechanism, the fix enumerates every surface that
  mechanism reaches, and the discharge record states which were checked.
  Demonstrated by its own violation on 0027: review round 1 named scenario S5
  as asserting a false universal, the amendment closed S5, and the
  structurally identical claim in S11 survived one scenario below it — the
  divergence was never cost-specific (`blocked` + `approach cap:` shows the
  same section/verb split as `blocked` + `cost breaker:`). Both are now
  scoped. This is the documentation-side twin of the cloned-defect-class rule
  (judgement on bid-0121, a walk that finds a defect must bid its known twin)
  (source: .factory/items/0027-…/reviews/synthesis.md; authorized: judgement
  on bid-0148).

## Learned from item 0026 review (2026-08-04)

- **A receipt that recomputes its subject is not a receipt.** A rendered claim
  about what *happened* must read the engine's record of it, or must be worded
  as a claim about what the configuration *selects*. 0026's packet `depth` line
  calls `tiers.record()` live from the item's current tier and the repo's
  current config at render time and never reads the `data.depth` record
  `machine.advance` writes in the same commit — a reader sweep of every
  `stage.advance` consumer (`machine.py:125,152,181`; `cost.py:108,339`;
  `initrepo.py:174`) found all six key on `data.from`/`data.to` only, so the
  record is write-only. README:96 nonetheless shipped "Every packet prints the
  depth the item **actually ran at**, so the promise is auditable". The item's
  own motivating case is the disproof: 0027 was `tier: bug`, paid a two-round
  six-seat triage council, and would still print `review light`. Note the
  seats' further finding — reading the record would *not* have fixed it either,
  since the record holds the declared profile at advance time; the honest fix
  is to word the line as a profile claim (source:
  .factory/items/0026-…/reviews/round-1/architecture.md,
  .factory/items/0026-…/reviews/round-2/customer.md,
  .factory/items/0026-…/reviews/synthesis.md; authorized: judgement on
  bid-0164).
- **A prose fix that leaves the journey contract saying the same thing
  relocates the overclaim into the layer that gets certified.** A journey
  contract's `Outcome` line *is* the assure oracle, so shipping it unamended
  means a walk is asked to certify the false claim — and once certified the
  brain carries it as proven. README prose and the contract must move to the
  same verb in the same commit; deferring the contract to the assure walk burns
  a walk and discovers the problem in the wrong order. This names which layer
  bid-0148's sweep must reach, and why the ordering is not free (source:
  .factory/items/0026-…/reviews/round-1/architecture.md,
  docs/factory/journeys/contracts/J-004-bug-door-intake.md; authorized:
  judgement on bid-0168).
- **The ship record is a claim surface with the same honesty duty as the code.**
  Where a review's clusters resolve to "say less on the record" rather than "do
  more in the product", the record must state the remainder rather than let a
  partial discharge read as closed. Three of 0026's eight review clusters
  resolved that way, and written loosely the item would ship having *added*
  unfalsifiable claims while discharging bids that read as closed — bid-0152
  only partially (the receipt marks one stage of six), bid-0155 only on its
  second disjunct and only once the prose fix lands, bid-0157 not at all
  (`intake.bug_route` guards `factory add` alone, while every skill that sets
  `tier: bug` goes through the unguarded `items.set_tier`). A bid names the
  remainder or it is not discharged (source:
  .factory/items/0026-…/reviews/round-2/customer.md,
  .factory/items/0026-…/reviews/round-1/product.md; authorized: judgement on
  bid-0167).
