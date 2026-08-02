# Assurance report — 0013-assure-attribution-gate-only-on-regressi

**Verdict: all 9 required scenarios pass (round 2). Item proceeds to ship,
carrying 2 pre-existing adjacent-node findings — each re-routed to a real,
open owner, per this item's own doctrine.**
Walked 2026-08-02 by a fresh-context journey reviewer (round 2, independent of
round 1, no implementation inputs). Contract J-001 is **approved**; two
amendments landed through the firewall during this item's assurance
(bid-0093 evidence classes, bid-0095 trust-bullet scoping).

## Journeys walked

| Journey | Surface | Scenarios | Verdict |
|---|---|---|---|
| J-001 assure-outcome-readout | CLI | S1–S9 + adjacent A1–A4/N5 | 9/9 required pass; 2 adjacent pre-existing, filed |

Evidence: `.factory/items/0013-…/assurance/` — `expectations.md` (predictions
recorded before acting), `transcripts/J-001/S1–S9.txt`, `adjacent.txt`,
`run-manifest.json`, `verdicts.json`.

Round history: round 1 failed J-001/S5 (owner refusals lacked
journey/scenario/rule naming on two arms) → `assure.rejected`, one scoped fix
(6552144: schema owner pattern removed; rule 10 owns owner semantics), council
re-review (unanimous SHIP), verify green (815 × 2), round-2 walk all-pass.
Highlights proven live: the engine refused a ship despite `assure.passed` on
the log (S1 — "the engine, not a skill, decides"); a mistyped `attributon` key
cannot silently ship a regression; 18 refusal arms all name journey, scenario
and cause; path-traversal owners and base paths refused on shape; stale base
evidence refused with both shas named; ship→done held end-to-end with the
owner still open.

## Shipped with known fails (pre-existing — owners filed)

- **verify→assure round-scoping gap** — a rework round re-enters assurance on
  prior-round `implement.completed`/`review.approved`/`verify.green`; only
  `assure.passed` is round-scoped. Reproduces with attribution off
  (pre-existing). Owned by **0025-round-scope-all-rework-gates-implement-c**
  (open, `idea`). Transcript: `adjacent.txt` §A1.
- **`factory status` table breaks on engine-filed 45-char ids** (no title
  column, mid-word slug truncation, unexplained `p-`). Formatter weakness
  pre-existing (fairness control: hand-added long titles overflow
  identically); 0013 makes long ids the norm. Owned by
  **0023-packet-furniture-and-readout-polish-drop** (open, `idea`, scope
  extended). Transcript: `adjacent.txt` §A2/§N5.

## Judgement calls — resolved during this round (veto reverts them)

1. **S5 binds all five owner arms** — settled by round 1's fail verdict; the
   fix moved owner semantics wholly into gate rule 10.
2. **S9's evidence class** — fresh-round deletion is skill-side; discharged by
   the AC11 coherence test + driven enforced outcome (contract amended,
   bid-0093).
3. **Trust-bullet vs default-path conflict** — Trust's "never a bare
   not-pass" now explicitly scoped to the attribution-enabled path (contract
   amended, bid-0095).
4. **Status-table finding reclassified** to 0023 as owner (the reviewer left
   attribution to the orchestrator; fairness control proved pre-existing).

## Polish (advisories — never gating; ratify any to bind the next run)

- `file-base-defect --help` documents no `--fingerprint` format (64-hex is
  discoverable only by refusal).
- `factory doctor` (human form) prints Python reprs (`True`, `None`,
  `['design']`) and omits `assure_attribution` while `--json` carries it — the
  S4 refusal says "enable the config key" but the obvious next command cannot
  show it (folded into 0023's scope; also the bid-0091 discoverability
  question).
- Round-scoping refusal message names neither journey nor scenario
  (defensible — not a per-scenario condition).
- `factory status` prints no title column (folded into 0023).

## Recommended confirmation walkthrough (10 minutes)

1. `git log --oneline main..factory/0013-assure-attribution-gate-only-on-regressi` — 10 commits.
2. Read `assurance/transcripts/J-001/S1.txt` (engine overrules a logged
   assure.passed) and `S5.txt` (all five owner arms).
3. Read `adjacent.txt` §A1 — the round-scoping gap 0025 now owns.
4. `factory cost 0013-assure-attribution-gate-only-on-regressi` — the full
   provenance-tagged spend readout.
