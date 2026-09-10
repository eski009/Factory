# Within-corpus separation exists; no runaway threshold is calibrated or recommended

This report is an offline arithmetic replay for Factory item 0030. It is not a
production control and grants no authority to alter item 0018.

## Provenance and populations

- Command: `python3 tests/fixtures/gap_capped_attributed_seconds.py replay --fixture tests/fixtures/gap-capped-attributed-seconds-a1c04a5.json`
- Cohort selection revision: `a1c04a5564124fdd9078c6d051085570a32bbd6e`.
- Primary cohort: n=13, the immutable population filed at 0030 creation.
- Secondary snapshot: n=16@a1c04a5, evaluated separately and never pooled with the primary cohort.
- The motivating external ParkSnap run is absent and not reconstructed.

Neither cohort contains a labelled positive runaway. Item 0016 completed and
shipped. The uncapped first-implement values are 10,046 seconds for healthy
0015 and 9,499 seconds for 0016: the difference is 547 seconds (5.4% of the 0015 duration). At CAP=1 the scores are 10 and 13, so the low-CAP ordering is materially
event-cadence-driven rather than a validated measurement of work.

## Exhaustive boundary

Every integer CAP from 1 through 6,204 admits the lowest separating threshold
`T = score(0015) + 1`. CAP 6,205 ties both scores at 9,499. Every integer CAP
from 6,206 through 43,727 makes 0015 larger. A row without separation carries
no threshold and is never rendered as zero or as an empty parked set.

## Primary representative rows — n=13

| CAP | 0015 score | 0016 score | lowest separating T | items parked |
|---:|---:|---:|---:|---|
| 1 | 10 | 13 | 11 | 0016-cost-circuit-breaker-on-engine-authorita |
| 30 | 300 | 390 | 301 | 0016-cost-circuit-breaker-on-engine-authorita |
| 60 | 600 | 770 | 601 | 0016-cost-circuit-breaker-on-engine-authorita |
| 120 | 1,200 | 1,490 | 1,201 | 0016-cost-circuit-breaker-on-engine-authorita |
| 300 | 2,708 | 3,650 | 2,709 | 0016-cost-circuit-breaker-on-engine-authorita |
| 600 | 3,688 | 6,396 | 3,689 | 0016-cost-circuit-breaker-on-engine-authorita |
| 900 | 4,194 | 7,682 | 4,195 | 0016-cost-circuit-breaker-on-engine-authorita |
| 1,800 | 5,094 | 9,499 | 5,095 | 0016-cost-circuit-breaker-on-engine-authorita |
| 3,600 | 6,894 | 9,499 | 6,895 | 0002-claude-design-mcp-as-the-single-source-o, 0003-interactive-decision-pages-clickable-cho, 0016-cost-circuit-breaker-on-engine-authorita |
| 5,000 | 8,294 | 9,499 | 8,295 | 0002-claude-design-mcp-as-the-single-source-o, 0003-interactive-decision-pages-clickable-cho, 0016-cost-circuit-breaker-on-engine-authorita |
| 6,000 | 9,294 | 9,499 | 9,295 | 0002-claude-design-mcp-as-the-single-source-o, 0003-interactive-decision-pages-clickable-cho, 0016-cost-circuit-breaker-on-engine-authorita |
| 6,204 | 9,498 | 9,499 | 9,499 | 0002-claude-design-mcp-as-the-single-source-o, 0003-interactive-decision-pages-clickable-cho, 0016-cost-circuit-breaker-on-engine-authorita |
| 6,205 | 9,499 | 9,499 | none | no separating threshold |
| 7,200 | 10,046 | 9,499 | none | no separating threshold |

## Secondary representative rows — n=16@a1c04a5

| CAP | 0015 score | 0016 score | lowest separating T | items parked |
|---:|---:|---:|---:|---|
| 1 | 10 | 13 | 11 | 0016-cost-circuit-breaker-on-engine-authorita |
| 30 | 300 | 390 | 301 | 0016-cost-circuit-breaker-on-engine-authorita |
| 60 | 600 | 770 | 601 | 0016-cost-circuit-breaker-on-engine-authorita |
| 120 | 1,200 | 1,490 | 1,201 | 0016-cost-circuit-breaker-on-engine-authorita |
| 300 | 2,708 | 3,650 | 2,709 | 0016-cost-circuit-breaker-on-engine-authorita |
| 600 | 3,688 | 6,396 | 3,689 | 0016-cost-circuit-breaker-on-engine-authorita |
| 900 | 4,194 | 7,682 | 4,195 | 0016-cost-circuit-breaker-on-engine-authorita |
| 1,800 | 5,094 | 9,499 | 5,095 | 0016-cost-circuit-breaker-on-engine-authorita |
| 3,600 | 6,894 | 9,499 | 6,895 | 0002-claude-design-mcp-as-the-single-source-o, 0003-interactive-decision-pages-clickable-cho, 0016-cost-circuit-breaker-on-engine-authorita, 0031-the-cost-packet-s-decision-copy-is-churn |
| 5,000 | 8,294 | 9,499 | 8,295 | 0002-claude-design-mcp-as-the-single-source-o, 0003-interactive-decision-pages-clickable-cho, 0016-cost-circuit-breaker-on-engine-authorita, 0031-the-cost-packet-s-decision-copy-is-churn |
| 6,000 | 9,294 | 9,499 | 9,295 | 0002-claude-design-mcp-as-the-single-source-o, 0003-interactive-decision-pages-clickable-cho, 0016-cost-circuit-breaker-on-engine-authorita, 0031-the-cost-packet-s-decision-copy-is-churn |
| 6,204 | 9,498 | 9,499 | 9,499 | 0002-claude-design-mcp-as-the-single-source-o, 0003-interactive-decision-pages-clickable-cho, 0016-cost-circuit-breaker-on-engine-authorita, 0031-the-cost-packet-s-decision-copy-is-churn |
| 6,205 | 9,499 | 9,499 | none | no separating threshold |
| 7,200 | 10,046 | 9,499 | none | no separating threshold |

## Source-input disclosure

All 16 declared logs are present. Per-item parseable record counts and every
exclusion count remain visible below. Log bytes were recovered from the
2026-09-10 archive; the revision identifies cohort selection, not versioned logs.

| item | present | parseable records | blank | corrupt JSON | missing timestamp | unparseable timestamp |
|---|---:|---:|---:|---:|---:|---:|
| 0001-focus-group-research-structured-intervie | yes | 14 | 0 | 0 | 0 | 0 |
| 0002-claude-design-mcp-as-the-single-source-o | yes | 21 | 0 | 0 | 0 | 0 |
| 0003-interactive-decision-pages-clickable-cho | yes | 23 | 0 | 0 | 0 | 0 |
| 0004-per-item-cost-meter-measure-and-report-t | yes | 29 | 0 | 0 | 0 | 0 |
| 0007-tolerant-log-reading-corrupt-log-jsonl-l | yes | 22 | 0 | 0 | 0 | 0 |
| 0008-design-mirror-refinements-pull-bid-diver | yes | 16 | 0 | 0 | 0 | 0 |
| 0009-finish-the-never-bricks-promise-crash-pr | yes | 27 | 0 | 0 | 0 | 0 |
| 0010-factory-bug-command-understand-replicate | yes | 22 | 0 | 0 | 0 | 0 |
| 0012-adapt-the-design-options-decision-block- | yes | 22 | 0 | 0 | 0 | 0 |
| 0013-assure-attribution-gate-only-on-regressi | yes | 51 | 0 | 0 | 0 | 0 |
| 0015-approach-rejected-a-redesign-loop-back-t | yes | 46 | 0 | 0 | 0 | 0 |
| 0016-cost-circuit-breaker-on-engine-authorita | yes | 56 | 0 | 0 | 0 | 0 |
| 0025-round-scope-all-rework-gates-implement-c | yes | 26 | 0 | 0 | 0 | 0 |
| 0027-packet-respond-falls-through-to-factory- | yes | 48 | 0 | 0 | 0 | 0 |
| 0031-the-cost-packet-s-decision-copy-is-churn | yes | 34 | 0 | 0 | 0 | 0 |
| 0033-bugs-run-less-pipeline-make-stage-member | yes | 18 | 0 | 0 | 0 | 0 |

## Finding

The frozen traces contain literal pairwise separators, but those separators do
not calibrate a runaway discriminator: 0016 shipped, the cohorts are unlabelled
for runaway outcomes, the apparent low-CAP advantage is materially
event-cadence-driven, and the external ParkSnap evidence is unavailable.

Conclusion: within-corpus separation exists; no runaway threshold is calibrated or recommended.
