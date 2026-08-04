# J-004 — Bug door intake

_status: draft — drafted at the spec stage of
`0026-complexity-scored-bug-flow-bugs-run-a-su`, the item that introduces this
journey. Item tier is `feature`, so the assure profile is `affected`: depth
covers the touched nodes and their immediate neighbours, not the whole pipeline.
This is a **minimal** draft — it covers the five nodes the introducing item
declares and nothing more. Later items touching this journey extend it; a
`status: approved` promotion goes through a `council-judgement` bid._

- **Persona:** The Overnight Operator (`docs/factory/brain/personas.md`) — pays
  the token bill personally, was not watching the run, is skeptical by default,
  and arrives pre-burned by AI tooling that claims more than it proves.
- **Trigger:** a human reports a defect at any intake door — `/factory:bug`,
  `/factory:add` (`factory add`), `/factory:do`, or a `/factory:roadmap` batch.
- **Outcome:** the defect is filed with its **materiality** claim (`tier`) and
  its **evidence** claim (`bug: true`) recorded separately and honestly, a
  confirmed repro exists before any fix work, the item is visible in
  `docs/factory/roadmap.md` and in `factory status`, and its packet prints the
  depth profile its tier selects and the intake path it took.
- **Surface:** CLI + filesystem + generated packet files. **No browser drive, no
  viewports.** Evidence is typed transcripts of real commands plus the produced
  artifact files (`item.md`, `repro.md`, `log.jsonl`, `docs/factory/roadmap.md`,
  the rendered packet markdown and HTML, `status --json`). The packet HTML is
  read as a produced artifact file, exactly as J-001/J-002/J-003 read it.

## Nodes

| node | what the customer knows here | what they expect next |
|---|---|---|
| N1 defect reported at a door | they typed a defect report in their own words at whichever door they reached for; they have made no claim about tier, evidence, or pipeline depth | the product routes them — they should not have to know that `/factory:bug` exists to get a replicated fix |
| N2 door routes — bug door, or the generic door warns/refuses | `/factory:bug` and `/factory:do` hand the report to the `factory-bug` skill. `factory add --tier bug` on the default `warn` setting exits **0**, prints the id on stdout and a warning on stderr naming `/factory:bug` and the phrase `bug tier, repro unverified`; on `refuse` it exits **2** and creates nothing, naming both `/factory:bug` and the `warn` escape hatch; on `off` it is byte-identical to the pre-change engine | the two axes stay separate: filing at `--tier bug` records materiality only and does **not** arm the plan gate's repro requirement |
| N3 repro recorded and confirmed before any fix | on the bug door, `repro.md` exists with Command / Expected / Observed / Environment, and a `repro.confirmed` event carries the exact command and exit code; `bug: true` is in frontmatter. On cannot-replicate, the item is parked `waiting-human` with the attempts recorded and **no** `repro.confirmed` | no fix work is reachable past `_gate_plan` without both artefacts — the recorded repro is the analogue of TDD's red test |
| N4 item visible on the roadmap and in factory status | a `- [priority] <item-id> <title> (stage)` line exists in `docs/factory/roadmap.md`, written by `factory-bug` step 7; the item appears in `factory status --json`; a `triage.intake` event and a `stage: "triage"` spend event are logged | a bug-door item is never invisible to the operator scanning the backlog — the failure mode `roadmap.md:67-80` records for seven items, five of them `tier: bug` |
| **N5 packet names the selected depth profile and the intake path** | the packet's metadata block names `tier` (with `(declared)` or `(default — no tier declared)`), the effective `depth` profile as named enum levels with a `source` provenance, the `repro` evidence state, and — when a `triage.intake` event with `council: none` exists — the intake receipt distinguishing `repro-confirmed` from `repro UNVERIFIED` | the depth profile the item's tier selects and its source are visible on the packet; a narrowing that shipped invisibly is the thing this journey exists to prevent |

## Trust and reassurance requirements

The commitment point is **N2 → N3**: the operator is handing the pipeline a
defect and, from there on, trusting an unwatched run not to claim a fix it
cannot prove. The core promise inherited from `skills/factory-bug/SKILL.md` is
**we never claim a bug is fixed when it isn't.**

- **The two claims are never conflated.** `tier` is a materiality claim; `bug`
  is an evidence claim. No surface may derive one from the other, at read time
  or by backfill (`constraints.md`, judgement on bid-0149). A packet that shows
  `tier: bug` without a confirmed repro must say `bug tier, repro unverified` in
  those words — a silent omission would let a materiality claim read as evidence.
- **A narrowing is never invisible.** No arm that reduces effective depth ships
  without an operator-visible receipt on the packet (bid-0054 has no terminus
  otherwise). The receipt names its own provenance source.
- **Named enum levels, never a bare integer** (bid-0018/0066/0077 and the
  ui-taste rider): `research off, review light, assure node (tier bug profile,
  source defaults)`, never `complexity: 3`.
- **No token or saving figure appears anywhere on this journey** — not on the
  packet, not in code comments, not in the ship record. The measured evidence
  says depth is not the cost driver (bid-0153); a saving claim here would be
  unfounded and is refused by contract.
- **Any cost-bearing line still carries a `measured | proxy | unmeasured` tag**,
  and an absent triage spend renders as a loud `UNMEASURED`, never as zero or a
  dash (bid-0018/0152).
- **The refusal path names the verb and the alternative** — never a bare
  "refused" (bid-0054). The `refuse` setting must name both `/factory:bug` and
  how to get the old behaviour back.
- **Forward-only.** The seven pre-existing `tier: bug` items are never
  retro-armed or migrated; they surface the `repro unverified` marker instead. A
  fail-closed retro-arm would strand an omnibus like 0023 permanently behind
  `_gate_plan`, which has no waiver path.
- **The bug door must not be harder to walk than the generic door.** If it is,
  operators file defects as features to escape the gate — the incentive that
  produced the 0-for-9 record this journey exists to fix.

## Deterministic oracles

| scenario | oracle |
|---|---|
| door routing documented | `commands/add.md` contains `factory:bug`, `--tier`, and a sentence stating `tier: bug` does not arm the repro gate; asserted in `tests/test_plugin_coherence.py` |
| stale assumption removed | `skills/factory-triage/SKILL.md` no longer contains "usually filed via `/factory:bug` already carrying `tier: bug`" |
| roadmap write | `grep -c roadmap skills/factory-bug/SKILL.md` ≥ 1, and after a bug-door intake a line matching `^- \[.+\] <item-id> ` exists in `docs/factory/roadmap.md` |
| add-door warn | `factory add "T" --tier bug` exits `0`, stdout is the id alone, stderr contains `/factory:bug` and `bug tier, repro unverified`, and `item.md` contains `tier: bug` and no `bug:` line |
| add-door refuse | with `intake.bug_route: "refuse"`, exit is `2`, no directory is created under `.factory/items/`, stderr names `/factory:bug` and `warn` |
| add-door off / invariance | with `"off"`, and for every `factory add` without `--tier bug` on every setting, stdout, stderr, exit code and `item.md` bytes are identical to the pre-change engine |
| config degradation | an absent, unreadable, malformed or out-of-enum `intake.bug_route` produces the `warn` behaviour and no traceback; `factory validate` reports the out-of-enum value as a config schema error |
| no derivation | `grep -rn 'item_tier' scripts/factory/lib/machine.py` returns no match; `meta.get("bug")` occurrences in `machine.py` are exactly the pre-change set |
| repro gate unchanged | the five repro-gate tests at `tests/test_machine.py:188-222` pass unchanged; a `tier: bug` item with no `bug` key advances `spec → plan` |
| repro gate armed | with `bug: true` and no `repro.md`, `spec → plan` is refused naming the artefact; with `repro.md` but no `repro.confirmed`, refused naming the event |
| depth recorded | advances into `review` and `assure` each append a `stage.advance` whose `data.depth` carries exactly `{tier, tier_declared, research, review, assure, source}`, every level a member of the corresponding `tiers.DEFAULTS` enum, equal to `factory doctor --json` → `tiers[<tier>]` |
| depth provenance | `source` is `defaults` on stock config, `config` under a `tiers.<tier>` override, `fallback` for a tier absent from `DEFAULTS`; `tier_declared` is `false` exactly when `item.md` carries no `tier:` line |
| depth off-switch | with `depth.record: false` no `stage.advance` carries a `depth` key and event bytes match the pre-change engine; with `depth.stages: ["review"]` the advance into `assure` carries none and into `review` does |
| engine never raises | an unreadable or malformed `.factory/config.json` still permits every `machine.advance`, recording `source: "defaults"` |
| one receipt builder | both renderers derive receipt lines from the single `packet.receipt_lines`; the label/value pairs are equal as a set across the two renderers |
| repro marker | `tier: bug` without `bug` renders exactly `bug tier, repro unverified`; with `bug: true` renders the `bug flag set` variant; a non-bug item renders no `repro` line |
| intake receipt | a log with `triage.intake` `council: none` renders `no council triage — bug intake, repro-confirmed` when `repro.confirmed` exists and `no council triage — bug intake, repro UNVERIFIED` when it does not; no `triage.intake` renders no `triage` line |
| no figures | every line produced by `receipt_lines` fails a `\d{3,}` match and contains none of `saved`, `saving`, `token` |
| provenance | every cost-bearing line matches `^\s*[-•]?\s*\[(measured\|proxy\|unmeasured)\]`; `- [unmeasured] stage triage: tokens UNMEASURED (no spend events logged)` renders exactly when the summary has a `triage` bucket whose `measured` is `None` |
| stage sequence untouched | `machine.STAGES` and `machine.stage_sequence` are byte-identical; `schemas/work-item.schema.json` is byte-identical |
| no triage dial | `tiers.DEFAULTS` has exactly `research`, `review`, `assure` per tier — no `triage` key |

No oracle reads free text for meaning. **Named residual:** the `no council
triage` receipt derives from a **skill-logged** `triage.intake` event, not an
engine-written one — `reviews/synthesis.md` is written by both the triage and
review councils, so council absence is not engine-observable. The receipt names
its own source in the rendered text, and no engine decision reads it; the
residual is stated, not hidden.

## Required scenarios

The authoritative list is
`.factory/items/0026-complexity-scored-bug-flow-bugs-run-a-su/assurance/impact.json`
(J-004 S9–S14: happy ×1, empty ×1, error ×2, interruption ×1, recovery ×1). Any
later item touching this journey re-declares its own subset in its own
impact.json.

## Required evidence per surface

- **cli/api:** a typed transcript per scenario — the exact command, its exit
  status, and its stdout **and stderr separately** (the warn/refuse arms turn on
  the stream and the exit code, so a merged capture cannot discharge them) —
  plus the produced artifact files (`item.md`, `repro.md`, `log.jsonl` excerpt,
  the `docs/factory/roadmap.md` line, the rendered packet markdown and HTML,
  `status --json`, `doctor --json`).
- **browser:** not applicable. No viewports are declared and none are required.

## Run & fixtures

- Engine under test:
  `python3 scripts/factory/factory.py --repo <fixture-repo> …` (Python 3 stdlib
  only, no install step — `brain/constraints.md`).
- Fixtures: a temp git repo per scenario, seeded via `factory init`, with items
  advanced through the production `machine.advance()` path (never
  `items.save_item` — bid-0082). The grandfathering arm needs a `tier: bug` item
  with **no** `bug` key created before the change; the armed arm hand-edits
  `bug: true` onto it.
- Config arms: stock `DEFAULT_CONFIG`; `intake.bug_route` at each of
  `off | warn | refuse`; `depth.record: false`; `depth.stages: ["review"]`; a
  deliberately malformed `config.json`.
- Test entry point: `python3 -m unittest discover -s tests`.
- Credentials: none. This journey touches no network and no secrets; nothing on
  it may require any.

## Empty / error / interruption / recovery

- **Empty:** `intake.bug_route: "off"`, and any `factory add` without
  `--tier bug`: stdout, stderr, exit code and `item.md` bytes identical to the
  pre-change engine (S12).
- **Error:** the add-door `warn` arm (exit 0 with a stderr warning, S10) and the
  `refuse` arm (exit 2, nothing created, S11); malformed config degrades to the
  stated default without a traceback.
- **Interruption:** `factory-bug`'s cannot-replicate hard stop — the item is
  parked `waiting-human` with the attempts recorded, the packet renders the
  repro-UNVERIFIED receipt and exactly one copy-pasteable action, and no fix work
  is reachable past the plan gate (S14).
- **Recovery:** forward-only grandfathering — a pre-existing `tier: bug` item
  with no `bug` key advances `spec → plan` with no `repro.md` and renders
  `bug tier, repro unverified`; after the operator writes `repro.md`, logs
  `repro.confirmed` and hand-edits `bug: true`, the armed gate passes too (S13).

## Polish battery (AI judgement, seeded on every touched node)

Asked at N1, N2, N3, N4, N5:

- **density:** what on this screen is not needed for what the customer is doing
  at this node?
- **craft:** what would a first-time customer visually notice as unfinished?
- **consistency:** does this screen read as the same product as the previous
  node (type, wording, structure — against `brain/design-system.md` and
  `brain/design-principles.md`)? In particular: does the bug-door packet read as
  the same product as the cost-breaker and redesign-cap packets, differing only
  where the subject differs?
- **trust:** would a first-time customer trust this screen with their data or
  money — here, with an unwatched pipeline's claim that a defect was actually
  replicated and actually fixed, and with the depth the run was allowed to skip?

Contract authors may add questions, never remove them.
