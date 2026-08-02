# Assurance report — 0025-round-scope-all-rework-gates-implement-c

**Verdict: all 8 scenarios pass. Item proceeds to ship.**
Walked 2026-08-02 by a fresh-context journey reviewer (no implementation
inputs). Contract J-001 approved; walk at node depth (tier bug): N2 plus the
four gate transitions.

## Journeys walked

| Journey | Surface | Scenarios | Verdict |
|---|---|---|---|
| J-001 (N2 + gate transitions) | CLI | S1–S8 (happy ×2, error ×4, interruption, recovery) | 8/8 pass |

Evidence: `.factory/items/0025-…/assurance/` — expectations.md (predictions
before acting), transcripts/J-001/S1–S8.txt + N2-ship-gate.txt,
run-manifest.json, verdicts.json.

Proven live: the morning's no-new-evidence rework repro is dead (refused at
every gate, naming the event, the round-resetting entry, and the action);
fail-closed on a missing round marker with a SPECIAL-only entry also refused;
frozen-clock tie refused (no timestamp comparator anywhere); SPECIAL
park/resume resets nothing; the refusal's own remedy re-enables the identical
advance; a fresh round-2 waive still satisfies the ship gate.

## Judgement calls — settled by the orchestrator

1. **S4 reachability:** the only path to a journeys==none rework is
   re-declaring journeys mid-rework — acceptable, because the missing
   `verify → implement` edge is exactly item 0015, shipping next by the
   council's build order. Not a gap this item should have closed.
2. **Not-logged vs stale message templates:** the incumbent not-logged
   wording (incl. `_gate_ship`'s divergent form) is protected by the
   default-path byte-identity oracle; unifying it belongs to the recorded
   message-shape pass (bids 0110/0111), not this item.

## Polish (advisories — never gating)

- The four not-logged refusals don't share the stale refusals' single
  template; `_gate_ship`'s variant lacks the `event '…'` prefix (incumbent).
- Ship gate's not-logged variant says "after the latest implementation round"
  even on a single-round item — implies a round problem where there is none.
- The stale message drops the `(or a recorded human waiver)` affordance its
  not-logged sibling advertises (a fresh waive does work — proven).
- The stale sentence states its fact twice in one ~185-char line.
