# J-002 — Cost breaker decision

_status: draft — minimal contract drafted at the spec stage of
`0016-cost-circuit-breaker-on-engine-authorita` (assure profile for tier
`feature` is `affected`, so depth covers the touched nodes and their immediate
neighbours, not the whole pipeline). Amending this file once it reaches
`status: approved` goes through a `council-judgement` bid with
`--surface journeys/contracts/J-002-cost-breaker-decision.md`._

- **Persona:** The Overnight Operator (`docs/factory/brain/personas.md`) — pays
  the token bill personally, was not watching the run, is skeptical by default.
- **Trigger:** an item enters an implement round with rework edges at or above
  `breaker.REWORK_THRESHOLD` while `"cost"` is in the configured `gates`.
- **Outcome:** the operator learns from the packet alone what the item has
  consumed, what it is blocking, and the consequence of each of continue /
  narrow / defer, and records one with a single command that provably unblocks
  the item exactly once.
- **Surface:** CLI + filesystem + generated packet files. No browser drive, no
  viewports. Evidence is typed transcripts of real commands plus the produced
  artifact files (packet markdown, packet HTML, `cost/answer.md`,
  `status --json`).

## Nodes

| node | what the customer knows here | what they expect next |
|---|---|---|
| N1 threshold crossed | `factory advance <id> implement` printed the **requested** stage and, below it, a `cost breaker:` line naming the rework count, the threshold, and the verb; a `cost.breaker` event is in `log.jsonl` | the run does not silently continue past this |
| N2 item parked, packet written | the item is `waiting-human`, `paused-from: implement`, reason prefixed `cost breaker:`; `docs/factory/packets/<id>.md` and `.html` exist | one packet that answers "what has this cost, what is it blocking, what are my options" without opening another file |
| N3 packet read — the decision screen | the proxy substrate first; exactly one rework figure; measured tokens only as a labelled lower bound or a loud UNMEASURED; the backlog at/above this item's priority; one recommendation with one sentence; a one-line consequence per option | exactly one copy-pasteable command |
| **N4 answer recorded — commitment point** | `factory cost-answer <id> <option>` printed the path to `cost/answer.md`; `cost.answered` is logged with the option and the edge count it answers | the item resumes, or stays parked per the recorded option, without the question being silently re-asked or silently dropped |
| N5 resume | the item is back at `implement` because the recorded answer covers the current edge count; in loop mode the backlog moved while it waited | work continues, and the next rework edge asks again with the new count |

## Trust and reassurance requirements

The commitment point is **N3 → N4**: the operator is being asked to authorise
more spend on an item they did not watch, against a backlog they did not audit.

- No cost figure appears anywhere on this journey without a
  `measured | proxy | unmeasured` provenance tag; UNMEASURED is a loud literal,
  never zero, a dash, or estimated dollars (`brain/constraints.md`, judgement on
  bid-0018). Measured figures on this journey are additionally suffixed
  `LOWER BOUND` — the aggregate is untrustworthy (judgement on bid-0063).
- **Exactly one rework figure** appears at the decision — the one the breaker
  fired on, inside `## Cost decision`. Every echo of it elsewhere on the packet's
  **rendered cost surfaces** (the `- waiting on you:` line, the `## Spend`
  receipt, which is the operator's cross-check) is derived from the same
  aggregation and is numerically identical to it; each is named and counted, so
  an unaccounted fourth digit-bearing rework **line** on a rendered cost surface
  fails. That count is line-granular — a second figure appended to an
  already-counted line is caught by the numbers-agree assertion instead, not by
  the count. The `- waiting on you:`
  line for a cost-breaker pause is **derived from `summary["rework_edges"]`**,
  not echoed from the operator's `paused-reason` free text — that string is
  hand-copied by an agent (`skills/factory-dispatch/SKILL.md:50`) and a typo in
  it must not reach the operator as a rework figure, least of all on the line
  that leads the page. A second, **differently-derived** figure beside it is the
  exact defect this journey exists to remove.
- `## Recent events` is **excluded by name** from that accounting, and this is
  the reason: it is an append-only verbatim audit dump — it records what was
  *written* (including the `reason` string `machine.advance` logged at the park),
  not what is aggregated now, and must **not** be rewritten to agree with a live
  aggregation. The exclusion is one named section and no wider; a test pins that
  it is real and exactly that section.
- The **proxy substrate leads**; no token headline appears above it.
- The recommendation is **never `continue`**: an unpriced choice defaulting to
  "continue" is the behaviour the item exists to stop. Each of continue / narrow
  / defer carries exactly one consequence line; none is omitted.
- No copy promises backlog release in `item`/`step` mode — release is loop-mode
  behaviour (`skills/factory-dispatch/SKILL.md:43-44`).
- Exactly one copy-pasteable next action per packet
  (`brain/design-system.md`), and the Respond block names the **real** verb for
  this pause, never the generic `/factory:run`.
- The refusal at N5 names the verb (`factory cost-answer`) and the recorded vs
  required edge counts — never a bare "refused".
- One job per screen (`brain/design-principles.md` KISS): the packet's job at N3
  is the cost decision; nothing on it serves another job.

## Deterministic oracles

| scenario | oracle |
|---|---|
| fired | `breaker.verdict(...)["fired"]` and the presence of a `cost.breaker` event in `log.jsonl` |
| requested stage preserved | stdout of `factory advance <id> implement` names the **requested** stage and exit status is `0` |
| park | `item.md` frontmatter `stage: waiting-human`, `paused-from: implement`, `paused-reason` starting `cost breaker:` |
| one rework figure | count of digit-bearing rework lines inside `## Cost decision` == 1, **and** every rework number on the packet's **rendered cost surfaces** agrees with it, **and** the only repetitions outside the block are the `- waiting on you:` derived echo and the `## Spend` receipt line; `## Recent events` is excluded by name as an append-only verbatim audit dump — it records what was written, not what is aggregated, and must not be rewritten to agree; the count pattern matches both `rework edges: N` and `N rework edges` |
| derived, not echoed | parking with a mistyped reason (`cost breaker: 7 rework edges` against a 2-edge log) still renders `2` on every rendered cost surface, `- waiting on you:` included, in both renderers — the guard above is falsifiable, and this is what falsifies it |
| provenance | every cost-bearing line in the packet matches `^\s*[-•]?\s*\[(measured\|proxy\|unmeasured)\]` |
| recommendation | the `Recommended:` line names `defer` when `backlog.at_or_above >= 1`, `narrow` when it is `0`, and — when it is `None`, i.e. the item carries no priority so the comparison is impossible — names neither, directing the operator to `factory priority <id> <n>`; never `continue` in any case |
| one action | count of `factory ` command lines under `## Respond` == 1, and that line names `factory cost-answer` |
| answer written | `breaker.record_answer` returns the path; `cost/answer.md` contains `- answer:`, `- rework-edges:`, `- ts:` |
| single writer | `factory log <id> cost.answered` is refused |
| precondition | exit status and `GateError` message of `factory advance <id> implement` with and without a valid `cost/answer.md` |
| monotone | an answer at count N admits resume at N and does not suppress the fire at N+1 |
| gate off | with `"cost"` absent from `gates`: `over_threshold: true`, `fired: false`, no park, and packet/`status --json` byte-identical to the pre-change engine apart from the `rework edges` / `spend.rework_edges` renames |
| invariance | `json.dumps(verdict, sort_keys=True)` byte-identical across the four M5 arms |
| loop release | `dispatch.next_item` returns a different actionable item once the parked item is `waiting-human` |

No oracle reads free text for meaning; the engine never judges whether the
operator's answer was *right*, only that one was recorded and which.

## Required scenarios

The authoritative list is
`.factory/items/0016-cost-circuit-breaker-on-engine-authorita/assurance/impact.json`
(S1–S9: happy ×2, empty ×2, error ×2, interruption ×1, recovery ×1, plus the
invariance arm). Any later item touching this journey re-declares its own subset
in its own impact.json.

## Required evidence per surface

- **cli/api:** a typed transcript per scenario — the exact command, its exit
  status, and its stdout/stderr — plus the produced artifact files
  (`cost/answer.md`, the rendered packet markdown and HTML, `log.jsonl` excerpt,
  `factory cost <id>` and `factory cost --all` output, `status --json`).
- **browser:** not applicable to this journey. The packet HTML is read as a
  produced artifact file, not driven in a browser; no viewports are declared.

## Run & fixtures

- Engine under test:
  `python3 scripts/factory/factory.py --repo <fixture-repo> …` (Python 3 stdlib
  only, no install step — `brain/constraints.md`).
- Fixtures: a temp git repo per scenario, seeded via `factory init`, with an
  item advanced to `implement` and a hand-written `log.jsonl` supplying the
  backward `stage.advance` edges. The replay scenario uses the checked-in
  `tests/fixtures/parksnap-2026-08-02/log.jsonl` (21 states / 20 advances,
  reconstructed from
  `docs/factory/field-reports/2026-08-02-parksnap-p1-nonconvergence.md:18-21`;
  its sibling `README.md` states it is a reconstruction, not the original log).
- Config arms: `gates: ["design"]` (breaker off) and
  `gates: ["design", "cost"]` (breaker on). Both must be exercised.
- Test entry point: `python3 -m unittest discover -s tests`.
- Credentials: none. This journey touches no network and no secrets; nothing on
  it may require any.

## Empty / error / interruption / recovery

- **Empty:** `"cost"` absent from `gates` — the verdict is computed and
  rendered, nothing parks (S3). An item with zero rework edges and zero spend
  events renders `rework edges: 0` and UNMEASURED tokens, and no verdict fires
  (S4).
- **Error:** resume with no answer artifact raises `GateError` naming the verb
  and the item stays parked — no infinite park/resume loop (S5). A malformed
  artifact, one recording an older edge count, or one recording an option
  outside `{continue, narrow, defer}` is refused with the recorded and required
  counts named (S6).
- **Interruption:** the session dies between park and answer; a fresh session's
  step-0 resume check finds the pause, finds no artifact, and changes nothing
  (S7).
- **Recovery:** after `continue` at count 2, a third rework edge fires the
  breaker again at 3 and the stale answer does not suppress it (S8).

## Polish battery (AI judgement, seeded on every touched node)

Asked at N1, N2, N3, N4, N5:

- **density:** what on this screen is not needed for what the customer is doing
  at this node?
- **craft:** what would a first-time customer visually notice as unfinished?
- **consistency:** does this screen read as the same product as the previous
  node (type, wording, structure — against `brain/design-system.md` and
  `brain/design-principles.md`)?
- **trust:** would a first-time customer trust this screen with their data or
  money — here, with authorising further unwatched spend on an item they did not
  watch?

Contract authors may add questions, never remove them.
