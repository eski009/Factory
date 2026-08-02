# J-001 — Assure outcome readout

_status: approved — ratified 2026-08-02 by the contract owner after the 0016
assure walk (S10–S11 pass, permitted diff (d) amendment reviewed and kept),
with the one-action oracle reworded to intent per that walk's judgement call.
Drafted at the spec stage of
`0013-assure-attribution-gate-only-on-regressi` (assure profile for tier
`feature` is `affected`, so depth covers the touched nodes and their immediate
neighbours, not the whole pipeline). Amending this file now goes through a
`council-judgement` bid with
`--surface journeys/contracts/J-001-assure-outcome-readout.md`._

- **Persona:** The Overnight Operator (`docs/factory/brain/personas.md`) — pays
  the token bill personally, was not watching the run, is skeptical by default.
- **Trigger:** an item's assure walk produces ≥1 non-`pass` scenario verdict.
- **Outcome:** the operator knows, without reading JSON by hand, whether the item
  shipped with known non-blocking fails or was blocked — and every known fail
  that shipped has a real, open, named owning item.
- **Surface:** CLI + filesystem. No browser, no viewports. Evidence is typed
  transcripts of real commands plus the produced artifact files.

## Nodes

| node | what the customer knows here | what they expect next |
|---|---|---|
| N1 assure verdict written | the walk finished; `assurance/verdicts.json` exists with a verdict per required scenario | the engine, not a skill, decides whether this ships |
| N2 ship gate evaluated | whether any verdict blocks, and *why* — the refusal names journey, scenario and cause | a block reworks; no block ships |
| N3 packet rendered | on its **first screen**: whether this packet is a park (action needed) or a ship-with-known-fails (informational), and which items own the known fails | one, and only one, copy-pasteable next action |
| N4 `factory status --json` | a machine-readable count of non-blocking fails and their owner ids | the owners appear in the backlog as real open items |
| N5 owning items exist | each known fail resolves to an existing item that is not `done` | triaging or prioritising that item is possible immediately |

## Trust and reassurance requirements

The commitment point is **N2 → N3**: the operator is being asked to accept a
merge they did not watch, that carried known failures.

- A packet that shipped with known fails must be visually distinguishable from a
  parked packet **on the first screen** — `hooks/session-start.sh` globs
  filenames only, so filename alone cannot carry the distinction.
- Every known fail renders its scenario name **and its owning item id on the same
  line**. A fail without a resolvable open owner is not a known fail; it blocks.
- The refusal messages at N2 name the cause (`regression`, stale base sha,
  unresolvable owner, missing base evidence), never a bare "not pass".
- No cost or saving figure appears anywhere on this journey without a
  `measured | proxy | unmeasured` provenance tag (`brain/constraints.md`).
- Exactly one copy-pasteable next action per packet (`brain/design-system.md`).

## Deterministic oracles

| scenario | oracle |
|---|---|
| block vs ship | exit status and stderr of `factory advance <id> ship` |
| refusal cause | the `GateError` message string contains the journey id, scenario id, and the cause token |
| readout | `docs/factory/packets/<id>.md` contains the first-screen `- shipped with known fails: <n>` line and a `## Shipped with known fails` section |
| one action | exactly one action bullet under `## Respond`, and its leading command is the verb that answers this pause (oracle reworded 2026-08-02 from "count of `factory ` command lines == 1", which scored the generic pause's single `/factory:run` action as 0 and the assure pause's confirm-plus-inline-waive bullet as 2 — both satisfy the intent: one copy-pasteable action, slash commands included, an inline alternative on the same bullet not counted twice) |
| status | `factory status --json` → item row `assurance.non_blocking_fails` |
| owner | the owner id resolves to an item dir whose `stage != "done"` |
| default path | byte comparison of gate outcome, packet markdown, packet HTML and `status --json` against the pre-change engine — **narrowed by item 0016** to byte-identical except (a) the `## Spend` receipt's `retries` → `rework edges` label and its value, (b) `status --json`'s `spend.retries` → `spend.rework_edges`, and (c) the `## Respond` block in both renderers, which now names the one verb that answers this pause instead of listing every verb and closing with `/factory:run` (source: .factory/items/0016-cost-circuit-breaker-on-engine-authorita/spec.md §6 B3 mandates (c) on every packet; its narrowing paragraph names only (a) and (b), so this contract records the third diff the shipped renderers actually make — a two-diff list would make this oracle report a false regression), and (d) the packet HTML head's style rule `.ask { … }` → `.ask, #cost-decision { … }` — two CSS lines emitted on every HTML packet, the styling of the same §6-mandated cost-decision block as (c), visually inert on packets with no cost section (amended 2026-08-02 from the assure walk of item 0016: S11's byte comparison found (d) as a fourth textual diff; same enumeration-omission class as the 2→3 correction above — evidence `.factory/items/0016-cost-circuit-breaker-on-engine-authorita/assurance/transcripts/J-001/S11.txt`) |

No oracle reads the free-text `expected`/`actual` strings; the engine never
judges the truth of a walk (see the spec's §1 boundary).

## Required scenarios

The authoritative list is
`.factory/items/0013-assure-attribution-gate-only-on-regressi/assurance/impact.json`
(S1–S9: happy ×2, empty ×1, error ×4, recovery ×1, interruption ×1). Any later
item touching this journey re-declares its own subset in its own impact.json.

## Required evidence per surface

- **cli/api:** a typed transcript per scenario — the exact command, its exit
  status, and its stdout/stderr — plus the produced artifact file(s)
  (`verdicts.json`, the rendered packet markdown and HTML, `status --json`).
- **browser:** not applicable to this journey.

## Run & fixtures

- Engine under test: `python3 scripts/factory/factory.py --repo <fixture-repo> …`
  (Python 3 stdlib only, no install step — `brain/constraints.md`).
- Fixtures: a temp git repo per scenario, seeded via `factory init`, with an item
  advanced to `assure` and a hand-written `assurance/verdicts.json`. Merge-base
  scenarios need two real commits and a `factory/<item-id>` branch, created with
  plain `git` calls; `git` is the only external binary used.
- Test entry point: `python3 -m unittest discover -s tests`.
- Credentials: none. This journey touches no network and no secrets; nothing on
  it may require any.

## Empty / error / interruption / recovery

- **Empty:** default config, attribution absent — behaviour byte-identical to the
  pre-change engine (S3).
- **Error:** unsolicited attribution (S4), bad owner (S5), bad base evidence
  (S6), stale merge base (S7). Every one blocks; none parks; none crashes.
- **Interruption:** a rework round starts mid-journey — sha-matching base
  evidence survives, non-matching base evidence is deleted (S9).
- **Recovery:** after a stale-sha refusal, a fresh base walk at the recomputed
  merge base unblocks the item (S8).

## Polish battery (AI judgement, seeded on every touched node)

Asked at N2, N3, N4, N5:

- **density:** what on this screen is not needed for what the customer is doing
  at this node?
- **craft:** what would a first-time customer visually notice as unfinished?
- **consistency:** does this screen read as the same product as the previous node
  (type, wording, structure — against `brain/design-system.md` and
  `brain/design-principles.md`)?
- **trust:** would a first-time customer trust this screen with their data or
  money — here, with an unwatched merge that carried known failures?

Contract authors may add questions, never remove them.
