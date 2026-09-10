# Derived evidence and accounting ledger plan

> **Execution:** direct engineering only; do not invoke the Factory harness.
> This implements retrospective candidate FH-07 as a read-only report.

## Goal

Add one run-bounded ledger that presents, without conflation:

- first-parent delivery commits classified by changed paths;
- Factory item inventory and run-local stage completions;
- optional external aliases such as AUD ids, labelled as aliases rather than
  extra delivered work;
- stage-active, waiting, review, test-runtime and admin evidence with explicit
  provenance;
- individual test waves with purpose, green SHA, shipped flows and screenshot
  coverage.

The ledger never adds overlapping inventories, never treats commit count as
speed or proof of delivery, never derives duration from artifact mtimes, and
never sums incomparable token populations. Existing `cost` output remains
unchanged.

## Inputs and boundaries

`factory ledger --base SHA --head SHA` requires two resolved commits with
`base` on `head`'s first-parent chain. The run window is the exclusive
first-parent range `base..head`; `base == head` is a valid empty range. Git
committer epochs (`%ct`) define the observation interval `(base_ts, head_ts]`
for logs. When the endpoint epochs are reversed, commit membership still
exists but time-based observations are `unavailable` with a warning. Repeated
or decreasing intermediate commit times never change commit membership.

Optional repeatable `--product-path PATH` values define product surfaces.
Explicit admin prefixes default to `.factory/` and all `docs/`, with repeatable
`--admin-path` additions. Paths are normalized repository-relative
component-boundary prefixes without traversal; product/admin overlap is
refused. With no product paths, classification is `unavailable` rather than a
guess. For each first-parent commit the engine diffs against its first parent
using NUL-delimited Git output, classifies both old and new names of a rename,
and assigns exactly one exhaustive class:

- `product-only`: every changed path is product;
- `admin-only`: every changed path is admin;
- `mixed`: changed paths span two or more of product, admin and unclassified;
- `other`: every path is unclassified, or the commit has no diff paths.

Merge status and `has_product_path` are orthogonal booleans, not additional
inventories. The headline `product-changing merges` counts merge commits only
when `has_product_path` is true; an admin-plus-unclassified `mixed` merge is not
included. `admin-only commits` counts only that disjoint class. The ledger
emits the commit rows that justify both counts and says explicitly that neither
figure is a speed metric.

The Git endpoint timestamps bound item-log observations only when the interval
is available. Factory item completion observations are unique item ids with at
least one valid `stage.advance` to `done` inside `(base_ts, head_ts]`; repeated
completion events remain visible as event rows but never inflate the unique
count. They are timestamp-selected observations, not proof that the Git run
delivered those items. Current item states are a separate cumulative snapshot.
When the endpoint interval is unavailable, completion observations and all
other timestamp-selected sections are unavailable rather than silently empty.
External aliases come
from optional `.factory/ledger-aliases.json`, a closed mapping from alias id to
one Factory item id plus optional status. Aliases are reported in their own
section, deduplicated by alias id, and never added to Factory item counts.
Multiple distinct aliases may target one item without increasing item totals.
Duplicate JSON keys are rejected during parsing; missing alias status is JSON
`null` and text `UNAVAILABLE`. Unknown/duplicate targets are warnings.

## Structured evidence events

Add a validated `test.wave` event schema. Its closed data shape is:

```json
{
  "wave_id": "wave-001",
  "purpose": "component|integrated|full-wave|release",
  "stage": "verify",
  "command": ["python3", "-m", "unittest"],
  "started_at": "2026-09-04T10:00:00Z",
  "finished_at": "2026-09-04T10:01:00Z",
  "result": "passed|failed|aborted",
  "tests": {"passed": 42, "failed": 0, "skipped": 0},
  "tested_sha": "40 lowercase hex",
  "green_sha": "same 40 lowercase hex when passed, otherwise null",
  "shipping_ref": "in-range 40 lowercase hex commit or null",
  "flows": ["J-001:S1"],
  "shipped_flows": ["J-001:S1"],
  "screenshots": [{
    "path": "repo-relative/path.png",
    "sha256": "capture-time hash",
    "flow": "J-001:S1",
    "state": "checkout"
  }]
}
```

`tested_sha` must resolve. `green_sha` must equal it on a passed wave and be
null otherwise. An integrated/full-wave/release tested SHA is delivery-bound
only when it belongs to `base..head`; an out-of-range reachable candidate SHA
is labelled candidate evidence, never delivered. Component waves are always
non-production. `shipping_ref`, when present, must resolve to an in-range Git
commit, and `shipped_flows` must be empty without such a valid reference;
otherwise flows are labelled tested, not shipped. Screenshot objects bind capture-time hashes
to one flow and state; current bytes are rehashed on reading. Durations derive
only from the two event timestamps. Paths must be contained existing regular
files. Wave ids are scoped per item; every occurrence of a duplicate or
conflicting id is excluded with a visible warning.

Waves belong to a report when their `finished_at` lies in `(base_ts, head_ts]`;
a wave that begins before the window retains its full measured test-runtime and
is visibly labelled boundary-crossing. An optional `activity.span` event
records otherwise invisible admin/test work:
closed fields `span_id`, `category` (`test|review|admin`), start/end and source.
Span ids are scoped per item and every duplicate occurrence is excluded. A
span belongs when its closed interval overlaps `(base_ts, head_ts]`; reported
elapsed time is clipped to that window and labelled when clipped. Stage
active/waiting rows are reconstructed from the last valid transition at or
before the window start, clipped to the interval, stopped at `done`, and marked
`unavailable` for missing boundaries or out-of-order event timestamps. They
remain `[proxy]`. Every wave and span is a separate per-item/per-source row;
explicit boundaries make elapsed interval `[measured]`, not measured active
effort. Review stage proxies, review spans, test waves and test spans may
overlap and are never added in JSON or text. Missing categories are JSON null
with status `unmeasured`, never numeric zero.

Shared schema-plus-semantic validators handle the rules the repository's JSON
schema subset cannot express: nullability, timestamp parsing/order, result
conditionals, hashes, id uniqueness and report-range eligibility. Generic
`factory log`, ledger reading and `initrepo.validate_tree` call the same base
validators; range-only checks run only in the ledger. Invalid intake returns
without appending. Existing spend handling and unrelated historical events are
byte-compatible. The ledger reports corrupt log lines and invalid structured
events instead of silently dropping them.

## Output contract

JSON is the stable interface. It contains separate top-level sections:
`run`, `commits`, `factory_items`, `aliases`, `timing`, `waves`, `warnings`, and
`limits`. There is no `total_work`, `throughput`, `velocity`, combined inventory
or cross-item token total.
Unavailable classification/timing is always `{status: "unavailable",
value: null, reason: "..."}` in JSON and `UNAVAILABLE` in text. Unmeasured is
`{status: "unmeasured", value: null}` and `UNMEASURED`; neither becomes zero.

Text renders one provenance tag per metric line (`[measured]`, `[proxy]`,
`[unmeasured]`, `[inventory]`, `[warning]`). It prints:

- exact product-changing merge and admin-only commit counts plus their SHAs;
- cumulative item states separately from run-local completions;
- cumulative alias states separately, explicitly non-additive;
- stage active/waiting, review, test and admin timing without a combined sum;
- one row per wave naming purpose, result, test counts, green SHA, flows and
  screenshot count/hash coverage;
- all exclusions, corrupt input and unmeasured boundaries.

## Task 1 — Git and item/alias ledger

**Files:** create `scripts/factory/lib/ledger.py` and `tests/test_ledger.py`.

- [x] Resolve and validate the commit range; use argv-array Git calls,
  first-parent order and NUL-delimited path output. Classify each commit once
  and preserve merge/product-path presence as orthogonal fields. Test that an
  admin-plus-unclassified mixed merge is not product-changing.
- [x] Derive current item inventory and run-local completions from valid event
  order/window. Surface unreadable items and corrupt logs.
- [x] Strict-read the optional alias file, validate unique ids/known targets,
  and keep alias counts separate from item counts.
- [x] Derive proxy active/waiting/review timing with window clipping and
  explicit overlap metadata. Never use file mtimes.
- [x] Add a synthetic fixture with product prefix `apps/ios/` and the default
  admin prefixes. Construct six actual first-parent merge commits whose
  first-parent diffs change product paths, plus 117 distinct admin-only
  first-parent commits under `.factory/` or `docs/`. Assert the exact SHA sets,
  their disjointness and the 123-row topology; mutate one commit at a time for
  mixed/other and rename-path cases. Label these numbers synthetic in output.
  Any historical reproduction must instead pass a pinned base/head range.
  Also test non-ancestor and reversed-time ranges, empty ranges, weird
  filenames, cumulative aliases and run-local versus cumulative item counts.

Run `python3 -m unittest tests.test_ledger -v`.

## Task 2 — Test waves and activity spans

**Files:** create `schemas/test-wave.schema.json` and
`schemas/activity-span.schema.json`; modify `scripts/factory/factory.py`,
`scripts/factory/lib/initrepo.py` and `scripts/factory/lib/ledger.py`; extend
`tests/test_ledger.py` and `tests/test_logs.py`.

- [x] Implement one shared schema-plus-semantic validator registry used by
  generic-log intake, ledger reads and `initrepo.validate_tree`. Invalid
  structured intake must return before append. Preserve byte-compatible spend
  validation and acceptance of unrelated historical events; test all three
  entry points and prove a rejected append leaves the log bytes unchanged.
- [x] Require passed waves to bind a resolving `green_sha` equal to
  `tested_sha`. Range membership determines delivery eligibility, not event
  validity: retain out-of-range candidate waves as non-delivered rows and
  label component waves as non-production evidence. Test a candidate SHA and
  a separate merged in-range SHA without conflating their waves.
- [x] Validate counts, chronological boundaries, unique ids, contained regular
  screenshots, hashes, flow ids and exact duration derivation.
- [x] Select waves by finish time and spans by interval overlap as specified;
  test pre-window starts, exact endpoint inclusivity, clipping, empty and
  reversed-time report windows.
- [x] Keep test/review/admin spans separate and mark missing categories
  unmeasured. Surface duplicates, conflicts, corrupt lines and invalid events.
- [x] Test repeated candidate/integrated waves remain separate rows; no renderer
  sums them. Prove screenshot coverage and shipped-flow labels per wave.

Run `python3 -m unittest tests.test_ledger tests.test_logs -v`.

## Task 3 — CLI and documentation integration

**Files:** modify `scripts/factory/factory.py`; add
`skills/capabilities/references/derived-ledger.md`; update
`skills/factory-status/SKILL.md` and `skills/factory-ship/SKILL.md`; create
`tests/test_cli_ledger.py`; extend plugin-coherence tests.

- [ ] Add `factory ledger --base SHA --head SHA [--product-path PATH]
  [--admin-path PATH] [--json]` with stable usage/refusal behavior.
- [ ] Render all sections and provenance tags exactly as above; output is
  deterministic for a fixed repository state and range.
- [ ] Document how verify/ship producers log waves and spans, and how status
  links to the ledger without treating it as a delivery gate or a speed claim.
- [ ] Preserve `factory cost` byte-for-byte and keep ledger read-only.

Run:

```bash
python3 -m unittest tests.test_cli_ledger tests.test_plugin_coherence \
  tests.test_default_path_invariance -v
python3 -m unittest discover -s tests -v
git diff --check
```

## Out of scope

- Inferring AUD aliases from prose, estimating unlogged test/admin time,
  deciding whether repeated waves were necessary, cross-item token totals,
  performance/velocity claims, evidence validity gates (FH-04), or receipt
  reuse (FH-03).
