# J-003 — Redesign cap decision

_status: draft — drafted at the spec stage of
`0015-approach-rejected-a-redesign-loop-back-t` (assure profile for tier
`feature` is `affected`, so depth covers the touched nodes and their immediate
neighbours, not the whole pipeline). Modelled on the ratified J-002 contract —
this pause is deliberately the same decision shape as the cost breaker's, so a
divergence between the two packets is a defect unless a bid records why._

- **Persona:** The Overnight Operator (`docs/factory/brain/personas.md`) — pays
  the token bill personally, was not watching the run, is skeptical by default.
- **Trigger:** an `approach.rejected` request (`factory advance <id> spec` from
  a firing-set stage) arrives when the item's engine-counted approach.rejected
  edges already equal `MAX_APPROACH_REJECTIONS`.
- **Outcome:** the operator learns from the packet alone what redesigns and
  rework the item consumed, what the forbidden-approaches record says cannot
  converge, and records continue/narrow/defer with a single command that
  provably unblocks exactly once.
- **Surface:** CLI + filesystem + generated packet files. No browser drive, no
  viewports. Evidence is typed transcripts of real commands plus the produced
  artifact files (packet markdown, packet HTML, `approaches/forbidden.md`,
  `approaches/answer.md`, `status --json`).

## Nodes

| node | what the customer knows here | what they expect next |
|---|---|---|
| N1 threshold crossed | `factory advance <id> spec` was refused, exit 2, stderr `approach cap: <n> redesign(s) used (cap <m>); record an answer with factory approach-answer <id> <continue\|narrow\|defer>` — a validated verb, never bare `blocked` (bid-0054) | the run does not silently continue past this, and does not silently brick the item |
| N2 item parked, packet written | the item is `waiting-human`, `paused-from` names the rejecting stage, reason prefixed `approach cap:`; `docs/factory/packets/<id>.md` and `.html` exist | one packet answering "what did the redesign(s) buy, what cannot converge, what are my options" without opening another file |
| N3 packet read — the tradeoff screen | both labelled populations lead: `[proxy] redesigns: <n> of <cap>` and `[proxy] rework edges since last redesign: <k> (cumulative <t>)`; measured tokens only as labelled LOWER BOUND or a loud UNMEASURED; the backlog at/above this item's priority; a labelled excerpt of the `approaches/forbidden.md` entry headings; one recommendation; one consequence line per option | exactly one copy-pasteable command |
| **N4 answer recorded — commitment point** | `factory approach-answer <id> <option>` printed the path to `approaches/answer.md`; `approach.answered` is logged with the option and the redesign count it answers; `narrow`/`defer` deleted the packet at record time (bid-0078) | the item resumes, or stays parked per the recorded option, without the question being silently re-asked or silently dropped. **Evidence class for packet removal (amended 2026-08-03, judgement on bid-0130):** removal is split by answer and only half of it is engine-side. `narrow`/`defer` are deleted at record time and ARE walkable from the CLI. The **`continue`** path is deleted by `factory-dispatch`'s step-0 resume clause (SKILL.md:20, "On a successful resume advance, delete that item's answered packets") — skill-side, not reachable from the CLI surface this contract names, so a CLI-only walk will correctly observe a surviving packet and must not score it a fail. Discharge `continue` with the dispatch prose plus a driven resume. **Named residual:** between recording `continue` and the next dispatch run the packet is stale on disk, so the nag is bounded-until-resume rather than absent |
| N5 resume | after `continue`, dispatch resumed the item to its `paused-from` stage and the re-issued `factory advance <id> spec` was admitted exactly once — the watermark covers the current count and nothing more | the redesign proceeds, and a further `approach.rejected` request is refused again with the new count |

## Trust and reassurance requirements

The commitment point is **N3 → N4**: the operator is authorising a second full
item's worth of spend (~1.4M measured tokens per 0004's distribution) on a
design the pipeline has twice failed to converge — or choosing to stop.

- No cost figure appears without a `measured | proxy | unmeasured` provenance
  tag; UNMEASURED is a loud literal, never zero, a dash, or estimated dollars
  (bid-0018). Measured figures inside the decision block carry the J-002
  qualifier convention.
- **Both populations, always, labelled** (bid-0066/0077): redesigns used vs
  `MAX_APPROACH_REJECTIONS`, and rework edges since the last redesign with the
  cumulative figure alongside — a redesign never masquerades as a fresh start,
  and the cumulative echo agrees numerically with the breaker/receipt figure.
  Every figure derives from one `cost.summarize` read; nothing is echoed from
  free text (bid-0086).
- The backlog line follows the bid-0066/0077 rules: `at_or_above` `None`
  renders "comparison unavailable", never `0`; unreadable/unpriced populations
  are qualified, never dropped.
- The `approaches/forbidden.md` excerpt is **labelled as authored text** — it is
  skill-authored evidence, not an engine aggregation, and the packet says so.
- The recommendation is **never `continue`**: an unpriced default to "try a
  third design" is the behaviour the cap exists to stop. `Recommended:` names
  `defer` when `at_or_above >= 1`, `narrow` when `0`, neither when `None`.
- Exactly one copy-pasteable next action; the `## Respond` block names
  `factory approach-answer`, never the generic `/factory:run`.
- The refusal at N1/N5 names the verb and the recorded vs required counts —
  never a bare "refused".
- The engine treats all three answers identically — routing on *which* answer
  belongs to factory-dispatch, never the engine; no engine transition ever
  writes `approaches/answer.md` or `cost/answer.md` (bid-0098).

## Deterministic oracles

| scenario | oracle |
|---|---|
| edge admitted | below cap, `factory advance <id> spec` from each firing stage exits 0 and appends a `stage.advance` event with `from` in `{review, verify, assure}` and `to == "spec"` |
| artifact-gated | the same advance with `approaches/forbidden.md` missing or empty exits 2 with the path named |
| cap refusal | at `MAX_APPROACH_REJECTIONS` engine-counted edges with no covering answer, the advance exits 2 and stderr starts `approach cap:` and names `factory approach-answer` |
| edge substrate | the invariance arm: counts equal with and without skill-logged `approach.rejected`/`review.rejected`/`assure.rejected` events, zero with events but no edges |
| park | `item.md` frontmatter `stage: waiting-human`, `paused-from` in the firing set, `paused-reason` starting `approach cap:` |
| dual populations | both labelled population lines present on a redesigned item's packet; cumulative figure equals the `## Spend` receipt figure; zero-approach-edge items render byte-identically to the pre-change engine |
| provenance | every cost-bearing line matches `^\s*[-•]?\s*\[(measured\|proxy\|unmeasured)\]` |
| recommendation | `defer` when `backlog.at_or_above >= 1`, `narrow` when `0`, neither when `None`; never `continue` |
| one action | exactly one action bullet under `## Respond`, leading with `factory approach-answer` |
| answer written | `approach.record_answer` returns the path; `approaches/answer.md` contains `- answer:`, `- redesigns:`, `- ts:` |
| single writer | `factory log <id> approach.answered` is refused |
| packet clearing | recording `narrow` or `defer` deletes the item's packet at answer-record time; a subsequent session-start announces nothing for it |
| monotone watermark | an answer at redesigns N admits exactly one more edge; the next request is refused at N+1; a stale or malformed answer, or an out-of-enum option, is refused with recorded vs required counts named — **amended 2026-08-03, judgement on bid-0126:** the refusal ladder is **five** pairwise-distinct arms and "recorded vs required counts named" is the oracle for the **recorded-value** arms only (out-of-enum names the option, stale names `recorded at N redesign(s), now M`, absent-artifact names `<n> redesign(s) used (cap <m>)`). For the **missing-field** arms the oracle is that the refusal names the absent FIELD and interpolates no parsed value — `no '- answer: <option>' line`, `no '- redesigns: N' line`. A missing field has no recorded count to name, and interpolating one leaks a Python `None` repr to the operator; the walk found exactly that at S6 and it was fixed in commit `18a02b0` (the `<option>` metavar per judgement on bid-0127 — the shared retry clause on the same line already spells the enum out, so the field name must not repeat it) |
| spec-exit gate | after an approach.rejected edge, advance out of `spec` is refused without (a) non-empty `approaches/forbidden.md` and (b) a `spec.revised` event postdating the edge; items with no such edge behave byte-identically |
| append-only | a two-redesign fixture retains forbidden.md entry 1 intact |
| owed pause not consumed | post-redesign `plan -> implement` with cumulative rework edges >= threshold and no covering cost answer is refused naming `factory cost-answer`; no transition auto-wrote an answer |

No oracle reads free text for meaning; the gate proves freshness and existence
of the redesign spec, **not comprehension** (bid-0053/0083) — that residual is
stated, not hidden.

## Required scenarios

The authoritative list is
`.factory/items/0015-approach-rejected-a-redesign-loop-back-t/assurance/impact.json`
(J-003 S1–S8: happy ×3, empty ×1, error ×2, interruption ×1, recovery ×1). Any
later item touching this journey re-declares its own subset in its own
impact.json.

## Required evidence per surface

- **cli/api:** a typed transcript per scenario — the exact command, its exit
  status, and its stdout/stderr — plus the produced artifact files
  (`approaches/forbidden.md`, `approaches/answer.md`, the rendered packet
  markdown and HTML, `log.jsonl` excerpt, `status --json`).
- **browser:** not applicable. The packet HTML is read as a produced artifact
  file, not driven in a browser; no viewports are declared.

## Run & fixtures

- Engine under test:
  `python3 scripts/factory/factory.py --repo <fixture-repo> …` (Python 3 stdlib
  only, no install step — `brain/constraints.md`).
- Fixtures: a temp git repo per scenario, seeded via `factory init`, with an
  item advanced through the production `machine.advance()` path to a firing-set
  stage (never `items.save_item` — bid-0082), a hand-authored non-empty
  `approaches/forbidden.md`, and where needed a `log.jsonl` carrying prior
  backward edges for the breaker arms.
- Config arms: `gates: ["design"]` and `gates: ["design", "cost"]` — the owed
  cost-breaker pause at the post-redesign implement entry must be exercised
  with the cost gate on.
- The AC13 replay uses the checked-in
  `tests/fixtures/parksnap-2026-08-02/log.jsonl` reconstruction.
- Test entry point: `python3 -m unittest discover -s tests`.
- Credentials: none. This journey touches no network and no secrets; nothing on
  it may require any.

## Empty / error / interruption / recovery

- **Empty:** an item with zero approach.rejected edges — the spec-exit gate is
  inert, no population lines render, packets and `status --json` are
  byte-identical to the pre-change engine (S4).
- **Error:** a firing-set→spec advance with the forbidden-approaches artifact
  missing or empty is refused naming the path; a post-redesign spec exit
  without a postdating `spec.revised` event is refused naming both
  requirements (S5); a malformed/stale/out-of-enum answer is refused with
  distinct messages, and `factory log` refuses `approach.answered` (S6).
- **Interruption:** the session dies between park and answer; a fresh session's
  step-0 resume check finds the `approach cap:` pause, finds no answer
  artifact, and changes nothing — no ping-pong (S7).
- **Recovery:** after `continue` at redesign count 1 and the admitted second
  edge, a third request is refused — the watermark at 1 does not cover count 2;
  the answer never becomes a standing waiver (S8).

## Polish battery (AI judgement, seeded on every touched node)

Asked at N1, N2, N3, N4, N5:

- **density:** what on this screen is not needed for what the customer is doing
  at this node?
- **craft:** what would a first-time customer visually notice as unfinished?
- **consistency:** does this screen read as the same product as the previous
  node (type, wording, structure — against `brain/design-system.md` and
  `brain/design-principles.md`)? In particular: does the redesign-cap packet
  read as the same decision surface as the cost-breaker packet, differing only
  where the decisions differ?
- **trust:** would a first-time customer trust this screen with their data or
  money — here, with authorising a second full item's worth of unwatched spend
  on a design that has already failed to converge?

Contract authors may add questions, never remove them.
