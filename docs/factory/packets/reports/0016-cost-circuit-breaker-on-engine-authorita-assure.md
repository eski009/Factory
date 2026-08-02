# Assurance report — 0016-cost-circuit-breaker-on-engine-authorita

**Verdict: all 11 scenarios pass. Item proceeds to ship.**
Walked 2026-08-02 by two fresh-context journey reviewers (no implementation
inputs — no spec, no diffs, no review conclusions). Both contracts are
**DRAFT** — confirm they reflect intent (`docs/factory/journeys/contracts/`).

## Journeys walked

| Journey | Surface | Scenarios | Verdict |
|---|---|---|---|
| J-002 cost-breaker-decision | CLI | S1–S9 (happy ×2, empty ×2, error ×3, interruption, recovery) | 9/9 pass |
| J-001 assure-outcome-readout | CLI | S10–S11 (regression) | 2/2 pass |

Evidence: `.factory/items/0016-cost-circuit-breaker-on-engine-authorita/assurance/`
— `expectations.md` (predictions recorded before acting), `transcripts/J-002/S1–S9.txt`,
`transcripts/J-001/S10–S11.txt`, `run-manifest.json`, `verdicts.json`.

Highlights of what was proven live, not read: fire at edge 2 → park → packet →
refused resume naming the verb → answer → admitted resume → re-fire at 3 with
stale-answer refusal; both config arms; four-arm verdict invariance
(sha1-identical against spend noise and rejection events); a deliberately
mistyped park reason (`7`) reaching **no** rendered cost surface; interrupted
session leaving state SHA-identical.

## Human decision recorded

The run's human directed on 2026-08-02, mid-assure: **end the run at this
pass** — remaining contract-level findings are filed, not reworked. Two
consequences of that direction, both taken transparently:

1. **J-001 S11**: the walk found a fourth textual diff against the merge-base
   engine — two visually inert CSS head lines styling the spec-mandated
   `#cost-decision` block. The three-diff enumeration in the draft contract had
   omitted it (its own history records an identical 2→3 omission). The contract
   was **amended** to permitted diff (d) citing the walk's evidence, rather than
   spending a rework round. The reviewer's original fail is preserved verbatim
   in `transcripts/J-001/S11.txt` and in `verdicts.json`'s notes.
2. **J-002 N3 contract finding** (below) is filed as a question, not reworked.

## Unresolved judgement calls — for the contract owner (you)

1. **One job per screen (J-002 N3).** The contract says nothing on the cost
   decision screen serves another job; the rendered packet carries the generic
   `## Artifacts` audit block and a `## View the options` heading (a
   design-packet phrase with no options here). Pre-existing generic furniture,
   inherited by the new screen. Should the cost packet drop it? (Interacts with
   J-001's permitted-diffs oracle.)
2. **LOWER BOUND scope (J-002 N3).** The contract suffixes measured figures
   `LOWER BOUND` on this journey; the `## Spend` receipt and per-item
   `factory cost` show the same figure unsuffixed, and J-001's permitted-diffs
   list arguably forbids adding it. Which surface is right?
3. **One-action oracle literalism (J-001).** The contract counts `factory `
   command lines under `## Respond` == 1; the generic-pause packet's single
   action is the slash command `/factory:run` (count 0), and the assure-pause
   bullet carries two commands (confirm + inline waive). All three branches
   satisfy the *intent* ("exactly one copy-pasteable action"). Settle the
   oracle's wording.

## Polish (advisories — never gating; ratify any to bind the next run)

**J-002:**
- `## Recent events` renders raw Python dict reprs in a human-facing page.
- `factory packet` prints only the `.md` path though it also writes `.html`.
- Same zero-spend state renders `[measured] tokens: none logged` on the receipt
  but `UNMEASURED` in `factory cost` — one absence, two labels.
- Singular/plural drift: "(1 spend events)" / "(1 events)".
- Packet HTML accent `#2459a9` vs the brain's headless fallback token `#2f5d3a`.
- `factory cost-answer` acknowledges with only a file path — it never echoes
  the option it recorded.

**J-001:**
- `## View the options` heading on assure/generic packets that have no options.
- `design/choice.md: no` listed on backend items that can never have one.
- Inline `waive` alternative rendered on a *passed* assurance (noise at the
  confirm decision).
- Renderer wording drift in the Respond intro (md vs html).
- `status --json` row keys mix kebab (`paused-from`) and snake
  (`rework_edges`) case (pre-existing).

## Recommended confirmation walkthrough (10 minutes)

1. `git log --oneline main..factory/0016-cost-circuit-breaker-on-engine-authorita` — 18 commits.
2. Read one transcript end-to-end: `assurance/transcripts/J-002/S1.txt` (the
   full fire→park→answer→resume→re-fire cycle).
3. Run the live surfaces on this repo: `factory cost 0016-…`, `factory cost --all`,
   `factory status --json | jq '.items[] | select(.id|startswith("0016")) | .spend'`.
4. Ratify or edit the two draft contracts, and answer the three judgement calls
   above — each answer binds every future run.
