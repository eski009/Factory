# Assurance report — 0033-bugs-run-less-pipeline-make-stage-member

**Verdict: all 9 declared scenarios pass. Item proceeds to ship.**

Walked 2026-08-04 by two sequential fresh-context journey reviewers with no
implementation, review, or verification inputs. J-001 is approved; J-004 is a
draft contract and should be confirmed as intent before its eventual approval.

## Journeys walked

| Journey | Surface | Scenarios | Verdict |
|---|---|---|---|
| J-004 — bug door intake | CLI + filesystem | S1–S6 | 6/6 pass after recorded scope reconciliation |
| J-001 — assure outcome readout | CLI + filesystem | S7–S9 | 3/3 pass |

Evidence lives under
`.factory/items/0033-bugs-run-less-pipeline-make-stage-member/assurance/`:
pre-action expectations, typed transcripts, `run-manifest.json`,
`verdicts.json`, and `reconciliation.md`. Each reviewer independently ran the
contract entry point; both runs reported 940 tests and `OK`.

## Scenario summary

- **J-004/S1:** the source-tagged immutable declaration retains the journey,
  derives `assurance: verify`, and fresh verification admits direct ship.
- **J-004/S2:** absence retains the ordinary `verify → assure → ship` route.
- **J-004/S3:** missing verification refuses ship with the existing message.
- **J-004/S4:** verification from before the current implementation round is
  refused as stale.
- **J-004/S5:** a hostile valid event injected at `assure` does not strand the
  item; the real engine advances to ship while the supported writers remain
  correctly closed.
- **J-004/S6:** fresh verification recovers a prior refusal without creating an
  assurance verdict.
- **J-001/S7:** verdict applicability is n/a on the shortened route and remains
  applicable on a control that runs assure, in both packet formats.
- **J-001/S8:** backend design and assure verdict are n/a; spec-owned impact
  remains applicable.
- **J-001/S9:** existing artifacts remain visible links even when their former
  owning stage is omitted.

## Reconciliation

The J-004 reviewer originally returned a journey-level fail despite all S1–S6
engine behavior passing. The impact map had copied J-004 N5's draft
tier/depth/intake packet receipt into this item. Binding triage finding F4 says
0033 owns only the engine-derived `n/a` artifact state and explicitly defers the
generic sequence receipt; F5 and the spec leave tier/depth/intake receipts to
0026. J-001 S7–S9 own and pass 0033's actual packet change.

The over-broad J-004 N5 declaration was removed. The original fail, its packet
evidence, and the orchestrator rescore are preserved in `run-manifest.json` and
`reconciliation.md`; nothing was silently discarded. No unresolved judgement
call remains.

## Polish

- J-001/N3: applicable-but-absent artifacts say `no` in Markdown and `(not
  yet)` in HTML. The meaning agrees, but the terminology differs.
- J-004/N2: the declaration command's success line does not repeat its source
  provenance; the immutable log event and status expose it.
- Out of 0033 scope: the draft J-004 N5 contract still awaits 0026's
  tier/depth/intake packet receipts and a later generic sequence receipt.
- Backend packets retain generic options/respond furniture when no design
  options exist.

## Recommended confirmation walkthrough

Create one confirmed bug fixture with an affected journey, record
`bug-assurance` at intake, and observe that missing verification refuses while
fresh current-round verification advances directly to ship. Render the packet
and confirm `assurance/verdicts.json` reads
`n/a (not in this item's sequence)` rather than pending.
