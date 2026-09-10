# Derived evidence ledger

`factory ledger` is a read-only, run-bounded accounting view. It reports Git
delivery inventory, Factory item observations, timing evidence and test waves
as separate sections. It is not a ship gate, a throughput measure or a speed
claim, and its timing categories can overlap.

## Read a pinned run

Use resolved run endpoints whenever possible:

```sh
factory ledger --base <base-sha> --head <head-sha> \
  --product-path apps/ios --json
```

`--product-path` and `--admin-path` are repeatable. `.factory/` and `docs/`
are always admin prefixes. Without a product path, delivery classification is
reported as `UNAVAILABLE`; it is never guessed. The base must be on the head's
first-parent chain. JSON is the stable machine interface. Text gives every
metric exactly one provenance tag.

The command does not write logs, metadata, aliases or reports. Commit counts
are inventory only. Run-local item completions are timestamp observations,
not claims that those items were delivered by the selected commits. Alias
counts are cumulative and non-additive with item counts. Never add proxy stage
intervals, activity spans or wave runtimes together.

## Record a test wave

Verify and ship producers may append a closed `test.wave` data object through
the normal log command:

```sh
factory log ITEM test.wave --data '{
  "wave_id":"wave-001",
  "purpose":"integrated",
  "stage":"verify",
  "command":["python3","-m","unittest"],
  "started_at":"2026-09-04T10:00:00Z",
  "finished_at":"2026-09-04T10:01:00Z",
  "result":"passed",
  "tests":{"passed":42,"failed":0,"skipped":0},
  "tested_sha":"0123456789012345678901234567890123456789",
  "green_sha":"0123456789012345678901234567890123456789",
  "shipping_ref":null,
  "flows":["J-001:S1"],
  "shipped_flows":[],
  "screenshots":[]
}'
```

Replace the illustrative hashes with resolving 40-character commit ids.
Passed waves require `green_sha` to equal `tested_sha`; failed or aborted
waves require it to be null. Use purpose `component`, `integrated`,
`full-wave`, or `release`. A wave is delivery-bound only when its purpose is
not component and its tested commit is in the selected range. `shipping_ref`
must be an in-range commit before any `shipped_flows` may be named.

Screenshot paths are repository-relative regular files. Record their SHA-256
at capture time; ledger reading rehashes current bytes and excludes a wave if
the evidence moved, changed or became unsafe to read.

## Record otherwise invisible work

An optional `activity.span` records a measured elapsed interval from a named
source. It does not assert uninterrupted active effort:

```sh
factory log ITEM activity.span --data '{
  "span_id":"review-001",
  "category":"review",
  "started_at":"2026-09-04T10:02:00Z",
  "finished_at":"2026-09-04T10:12:00Z",
  "source":"independent-review"
}'
```

Categories are `test`, `review`, or `admin`. Missing categories stay
`UNMEASURED`, not zero. Ids are unique per item; duplicate occurrences are
excluded rather than selected arbitrarily. Invalid structured input is
refused before append.

## Optional aliases

`.factory/ledger-aliases.json` may map external ids to Factory items:

```json
{
  "AUD-007": {"item": "0014-example", "status": "complete"}
}
```

The file is a closed mapping. A missing status renders as `UNAVAILABLE`.
Aliases never increase the Factory-item inventory.
