# J-005 — Plan approach convergence gate

_status: draft — drafted at the spec stage of
`0014-approach-gate-at-plan-judge-convergence-`. The item is tier `feature`,
whose assure profile is `affected`, so this contract covers every changed node,
its immediate upstream/downstream expectations, and the handoff into J-003._

- **Persona:** The Overnight Operator (`docs/factory/brain/personas.md`) — an
  expert unattended-run operator who pays the token bill and expects terse,
  cited evidence rather than reviewer ceremony.
- **Trigger:** with approach convergence explicitly enabled, an item attempts
  to leave `plan` and its current-round screen carries at least one named
  convergence-risk signal.
- **Outcome:** the operator can audit why the exact plan entered implementation
  or was refused from one current-round cited record; the autonomous run admits
  `implement` only on a pass and otherwise uses the existing 0015 redesign
  route.
- **Surface:** CLI + filesystem + engine event history. No browser surface or
  viewports. Required evidence is typed command transcripts and produced JSON,
  Markdown, and JSONL files.

## Nodes

| node | what the customer knows here | what they expect next |
|---|---|---|
| N1 plan exit requested | the item remains at `plan`; the explicit feature setting and current engine-derived planning round are knowable; no implementation edge has been admitted | the exact plan is screened before spend starts |
| N2 screen resolved | the current-plan record names zero or more stable signals with bounded plan citations and the exact plan SHA-256 | zero signals cost no reviewer pass; any named signal gets one fresh independent judgement |
| N3 judgement recorded | one closed-schema record identifies the planner and reviewer invocation(s), citations, current round/hash, verdict, disposition, and bounded escalation | a valid pass advances; uncertainty consumes at most its resolved budget; rejection cannot enter implementation |
| **N4 pass admitted — commitment point** | the record says `pass + advance` for the exact plan bytes, and the production advance writes one `plan -> implement` edge | implementation spends only against the plan that was judged |
| **N5 rejection handed off — commitment point** | no implementation edge exists; the cited forbidden entry is appended before the existing 0015 `approach.rejected` request | the redesign route owns the edge, cap, pause, answer, packet, and eventual return; no alternate `blocked` route appears |
| N6 retry after interruption | a missing, partial, malformed, or stale record has no authority and leaves the item at `plan` | a fresh dispatch resumes evidence production for the same round/hash without duplicate advancement |

## Trust and reassurance requirements

The commitment points are N3 → N4 (authorise implementation spend) and N3 →
N5 (discard the approach and buy a redesign). At both points:

- show the exact item, planning round, plan hash, signal ids, cited line ranges,
  reviewer invocation identity, final verdict, and disposition in the record;
- distinguish planner-produced screening from independent reviewer judgement;
- never render missing or incomparable evidence as a pass, an empty citation,
  or a numeric zero;
- name a distinct actionable refusal for each envelope defect; preserve old
  records for audit while denying them authority;
- say plainly that the engine validates proof shape and freshness, not the
  truth of the semantic conclusion;
- never claim measured savings where the product brain records them as
  unmeasured;
- on rejection, cite the record in the appended forbidden entry before
  requesting 0015's route, and never create a second cap, answer, or packet.

## Deterministic oracles

| scenario | oracle |
|---|---|
| disabled | explicit default disabled; unsolicited recording is refused; the engine neither requires nor consults a record; no reviewer runs; `plan -> implement` event sequence is unchanged apart from timestamps |
| no signal | enabled, current record has zero signals/attempts and coherent `not-triggered + advance`; exactly one implementation edge and zero reviewer invocations |
| signalled pass | one or more known signals with bounded citations plus one fresh independent cited `pass + advance`; exactly one implementation edge for the recorded SHA-256 |
| signalled reject | valid cited `reject + approach.rejected`; zero implementation edges; forbidden entry appended first; one shared `APPROACH_FROM -> spec` request and no direct `blocked` edge |
| bounded uncertainty | `uncertain + escalate` only while the resolved zero-or-one budget remains; a fresh second pass advances, while exhausted uncertainty or reject uses `approach.rejected` |
| envelope fail-closed | missing, malformed, wrong-item, stale-round, stale-hash, bad citation, same-producer, reused-reviewer, unknown enum, over-bound, or incoherent record exits 2 with a pairwise-distinct actionable reason and no stage event |
| current round | the round key is derived from the latest non-special engine-written entry into `plan`; a special-state resume creates no round; a plan-byte edit changes the hash and invalidates prior authority |
| 0015 reuse | plan is a member of the one shared approach firing set; every existing artifact/cap/watermark oracle runs from plan without a plan-only implementation; previous firing origins remain green |

No deterministic oracle parses free-form plan or reviewer prose to decide its
truth. The plan-stage producer supplies the structured signal screen and the
reviewer supplies the semantic judgement; engine oracles cover their envelope.

## Required scenarios

The authoritative list is
`.factory/items/0014-approach-gate-at-plan-judge-convergence-/assurance/impact.json`
(J-005 S1–S8 and J-003 S9–S13). Later items touching this journey re-declare
their own subset.

## Required evidence per surface

- **cli/api:** one typed transcript per scenario with exact command, exit
  status, stdout/stderr, relevant `factory status --json`, and the matching
  `log.jsonl` excerpt; include the approach record, plan bytes/hash, and any
  appended `approaches/forbidden.md` entry.
- **filesystem:** schema-validation output and immutable copies of the exact
  current/stale/malformed artifacts used by each arm.
- **browser:** not applicable; no screenshots, DOM/a11y snapshots, console,
  network trace, or viewport matrix is required.

## Run & fixtures

- Engine command:
  `python3 scripts/factory/factory.py --repo <fixture-repo> ...`.
- Tests: `python3 -m unittest discover -s tests -v`.
- Seed each scenario in a temporary repository using `factory init` and the
  production advance path. Reach `plan` through engine transitions; do not
  hand-edit stage frontmatter or use `items.save_item` as proof.
- Fixture corpus: for every signal id, one motivating positive and one
  near-neighbour negative plan with expected structured output; plus no-signal
  and multiple-signal plans.
- Configuration arms: explicit disabled default and enabled setting; tier arms
  cover the zero-or-one escalation policy without changing initial-review
  membership.
- Interruption fixtures stop after screening, after an incomplete first review,
  and between forbidden-entry append and transition request; each fresh run
  resumes without duplicate implementation or redesign edges.
- Credentials: none. The journey uses local files, subprocess workers through
  existing safe capability machinery, and no network secrets.

## Empty / error / interruption / recovery

- **Empty:** explicit feature-off configuration requires and consults no record;
  behavior is compatible with the pre-item plan exit.
- **Error:** every missing/malformed/stale/provenance/citation/enum/bound/
  disposition defect fails closed at `plan` with no stage event.
- **Interruption:** incomplete evidence retains no authority; a fresh dispatch
  resumes the same round/hash rather than treating partial bytes as a verdict.
- **Recovery:** replacing stale evidence with a fresh record for the current
  hash permits exactly one edge; a permitted fresh second reviewer resolves
  uncertainty, otherwise the existing redesign route receives the refusal.

## Polish battery (AI judgement, seeded on every touched node)

Ask at N1, N2, N3, N4, N5, and N6:

- **density:** what on this screen is not needed for what the customer is doing
  at this node?
- **craft:** what would a first-time customer visually notice as unfinished?
- **consistency:** does this screen read as the same product as the previous
  node (type, color, spacing rhythm — against `design-system.md` and
  `brain/design-principles.md` where present)? For this CLI/filesystem journey,
  apply the same question to terminology, field order, and refusal structure.
- **trust:** would a first-time customer trust this screen with their data or
  money — specifically, with authorising implementation spend or buying a
  redesign from this evidence?

Contract authors may add questions, never remove them.
