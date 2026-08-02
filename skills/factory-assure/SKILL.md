---
name: factory-assure
description: Use when a factory item is at stage assure - a fresh-context journey reviewer walks the affected journeys against the running product and the engine-validated evidence decides ship
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

## Contract

- **Entry stage:** `assure` (the engine's gate already required `verify.green`).
- **Artifacts produced:** `items/<id>/assurance/` — `run-manifest.json`, `expectations.md`, `verdicts.json`, evidence files (`screenshots/`, `console.ndjson`, `network.ndjson`, transcripts), `blockers.md` when blocked.
- **Exit:** **no blocking verdicts** — all `pass`, or non-`pass` only where the scenario is `pre-existing` with validated base evidence and a filed open owner → `factory log ITEM assure.passed --data '{"non_blocking_fails": <n>}'`, then always write a confirmation packet `docs/factory/packets/<id>-assure.md` (journeys walked, per-scenario verdict summary, evidence links, draft-contract flags, unresolved judgement calls, the `## Polish` advisory section, and a recommended confirmation walkthrough). If `"assure"` is in the config `gates` list, the packet stays in `docs/factory/packets/` and `factory advance ITEM waiting-human --reason "assurance passed - awaiting human confirmation (factory confirm ITEM)"` — the item parks for `factory confirm`; otherwise, on an **all-pass** run move the packet to `docs/factory/packets/reports/<id>-assure.md` (the non-nagging home) and `factory advance ITEM ship`. A **mixed-verdict** run's packet **stays in top-level `docs/factory/packets/`** and never moves to `packets/reports/` — it carries known fails a human should see. Any `regression`, or any fail on a repo where attribution is off → `factory log ITEM assure.rejected --data '{"round": <n>}'` + `factory advance ITEM implement` (the engine caps rework at 2, then blocked). Ambiguity or blocker → park: `factory advance ITEM waiting-human --reason "<what needs a human>"` + `factory packet ITEM` — never a silent pass, never a self-answered judgement call.

## Entry check

Before dispatching any reviewer, check for an already-answered stage: if
`items/<id>/assurance/waiver.md` exists (a human ran `factory waive`), or
`human-confirmation.md` exists with `assure.confirmed` logged, and the
recorded answer postdates the latest implementation round, do not re-walk —
take the matching Exit branch directly (`factory advance ITEM ship`; the
engine's round-scoped gate is the authority and will refuse a stale answer).
This mirrors factory-design's entry check: the stage never re-asks a
question a human already answered.

An item that arrives here with no `journeys` declaration (pre-upgrade work), or
a declared item missing `assurance/impact.json`, parks the same way: `factory
advance ITEM waiting-human --reason "journey impact undeclared - factory
journeys ITEM <none|J-...> (or factory waive)"` + `factory packet ITEM`. Never
guess an impact on the item's behalf.

Review asked "is the code sound"; verify asked "do the checks pass"; this stage asks **"can the customer get through it"** — against the running product, in a context that has never seen the implementation.

## Read first

`items/<id>/spec.md` (`## Journey impact`), `items/<id>/assurance/impact.json`, `docs/factory/journeys/graph.json`, and each affected journey's contract under `docs/factory/journeys/contracts/`. Read the item's tier from `factory status --json` and the assure depth from `factory doctor --json` → `tiers` → `assure`: `node` = the changed node plus its immediate transition (bug), `affected` = every affected journey's required scenarios including interruption paths (feature), `full` = affected plus core journeys the item touches, including adjacent journeys where state carries across (epic). Whatever the depth, `impact.json`'s explicit declarations extend it: nodes listed under `adjacent.upstream`/`adjacent.downstream` are in scope for the walk, and browser journeys are walked at every declared viewport (material nodes re-inspected per viewport, not just the happy path re-run).

## Dispatch — one fresh journey-reviewer subagent per affected journey

**Fresh round:** delete the prior round's assurance outputs first —
`run-manifest.json`, `expectations.md`, `verdicts.json`, `screenshots/`,
`console.ndjson`, `network.ndjson`, `blockers.md` (keep `impact.json`; only
the spec stage rewrites it) — so no stale evidence can satisfy this round's
gate. `assurance/base/<sha>/` is also kept, but
**conditional on `<sha>` still equalling the current merge base**
(`git merge-base <integration branch> factory/<id>`): a base directory
whose sha no longer matches is deleted at the start of a fresh round,
because without that condition the "keep" becomes the staleness hazard
instead of a saving.

Dispatch `agents/journey-reviewer.md` once per affected journey, sequentially, at the most-capable model tier (references/model-tiering.md) — and on a different model from the one that ran implement when the session supports model overrides. Compose each reviewer's prompt ONLY from this input allowlist:

- `docs/factory/brain/personas.md` and `users.md` (who the customer is)
- that journey's contract (draft or approved — note which)
- the item's `impact.json` (nodes, transitions, new states, required scenarios)
- the contract's Run & fixtures section (exact launch commands, fixture setup, credentials through the contract's fixture mechanisms)

Structurally excluded — never the implementer transcript, never review/verify conclusions or diffs, never any claim that the feature is "complete" or "ready": the reviewer must discover what the product does, not confirm what the pipeline hopes. If a required input is missing (no contract, no Run & fixtures, no fixture credentials), that journey is a **blocker** — record it and park; do not improvise a launch path.

## What the reviewer does (its walk, enforced by its agent file)

For every node in scope it: (1) states what the customer currently knows, (2) predicts what the customer expects next — written to `assurance/expectations.md` BEFORE acting, (3) performs the action, (4) compares expected vs actual, (5) captures screenshot evidence — plus a DOM/a11y snapshot where the semantics matter more than the pixels (form labels, focus order, announced state), (6) inspects console errors, (7) inspects network failures or unexpected requests, (8) records `pass | fail | ambiguity | blocker` per scenario with typed evidence refs, and (9) answers every AI judgement question the contract carries for the node (the polish battery) — objective craft defects fail, nameable-but-subjective findings return as advisories. Material console errors and unexpected 4xx/5xx responses are fails unless the journey contract explicitly whitelists them as known noise. The verdict for a journey is drawn across its screens, not per screen in isolation: an expectation created at one node that a later node contradicts or abandons is a **fail at the later node**, with the earlier node's evidence cited alongside.

**Surface drivers.** Browser-borne journeys require the **Browser drive** capability (capabilities skill; references/browser-drive.md — Playwright MCP, chrome-devtools MCP, or Claude-in-Chrome, matched behaviorally). Capability absent → the journey is a blocker → park; the parked packet names `factory waive ITEM --reason "..."` as the human's override. CLI/API journeys need no browser: the reviewer runs the real commands a customer or caller would run and captures typed transcript evidence instead of screenshots.

## The base walk — attribution, when the repo opted in

An item must not be gated on a defect it never caused. After the branch walk, if any journey has ≥1 `fail` **and** `factory doctor --json` reports `assure_attribution: true`, run exactly **one** base walk per assure round — journey-scoped, never per retry, never per scenario.

- **Journey-scoped.** For each journey that had ≥1 fail, the same required scenarios are walked at the merge base. A per-scenario base replay is exactly the delta-scoping this stage forbids: a verdict is drawn across a journey's screens, not per screen. Honest cost is roughly one extra full assure walk per assure round that has any fail — **UNMEASURED**: no surface in the engine attributes tokens per stage, so no saving claimed for this mechanism is measured.
- **Mechanics.** Check the merge base out into a Superpowers-managed worktree and launch the app there (execution discipline — worktrees, verification — comes from the companion plugin). The engine owns no worktree lifecycle.
- **Blindness.** The base walk uses a fresh `agents/journey-reviewer.md` subagent under the same input allowlist as the branch walk, plus one explicit exclusion: **never the branch walk's verdicts, expectations, evidence, or any attribution**. Attribution is an orchestrator/engine reconciliation performed *after* both walks, and is never an input to either.
- **Reconciliation.** For each branch `fail`: the base walk also fails that scenario ⇒ `pre-existing`; the base walk passes it ⇒ `regression`; the base walk returns `ambiguity`, `blocker`, or did not cover it ⇒ `regression` (fail closed).
- **Evidence layout.** Base evidence goes under `items/<id>/assurance/base/<merge_base-sha>/` (evidence files plus the base walk's own `verdicts.json`), and `run-manifest.json` records the resolved integration branch and the merge-base sha.
- **Re-routing.** Before writing `verdicts.json`, every `pre-existing` fail is filed: `factory file-base-defect ITEM --journey J-NNN --scenario <sid> --fingerprint <hex> --title "..." --expected "..." --actual "..."`, where `<hex>` is the lowercase sha256 of `"<journey id>\n<scenario id>"` — the stable pair (one scenario carries one verdict per round); never fold in the free-text failing expectation, which fresh-context reviewers re-phrase between rounds and would hash the same defect to a new fingerprint. The verb is idempotent — it prints the owning item's id whether it created one or deduped to an existing open one. Write that id into the scenario's `owner`. **Factory never ignores a failure; it files it.**
- **Spend.** The base walk logs its own spend event: `factory log ITEM spend --data '{"provenance":"measured","stage":"assure","source":"factory-assure-base","dispatches":<n>,"tokens":{"total":<n>}}'`, or `"provenance":"proxy"` with no `tokens` key when the harness reports none.

The engine validates shape, presence, path-containment, existence, non-emptiness, sha-match and owner-resolution — never the truth of a walk. It re-computes the merge base at ship, so base evidence recorded against a merge base that has since moved is refused as stale.

## Orchestrator composes the gate artifacts

The reviewer returns a structured report and writes ONLY evidence files under `items/<id>/assurance/`. This session (the orchestrator) then writes:

- `run-manifest.json` — what was launched and driven, per journey (commands, urls, fixture state, reviewer model).
- `verdicts.json` — per journey, per scenario: verdict, expected, actual, typed evidence refs (`screenshot | dom | console | network | transcript`, paths relative to the item dir). Shape: `schemas/assurance-verdicts.schema.json`; every declared journey and every impact.json scenario must be covered — the ship gate refuses gaps and missing evidence files, and refuses any non-pass verdict that is not a validated `pre-existing` (attribution, sha-matched `base` evidence under `assurance/base/<sha>/`, and an `owner` naming an open item).
- On any no-blocking-verdicts exit (all-pass or mixed with validated pre-existing fails), `docs/factory/packets/<id>-assure.md` — the confirmation packet from the Contract Exit (journeys walked, per-scenario verdict summary, evidence links, draft-contract flags, unresolved judgement calls, the `## Polish` advisory section, and a recommended confirmation walkthrough), always produced, never skipped.

The packet always carries a `## Polish` section: every advisory the
reviewers returned (the contract's judgement-question answers), grouped
by journey and node. Advisories never fail the gate and never park the item
— they are the world-class punch list the human adjudicates at
confirmation: ratify one — promote it (an escape promotion or a
contract amendment) — and it binds the next run; a question the contract
now settles stops being advisory.

Then take the Exit branch that matches the verdicts. A draft contract never blocks assurance, but flag it in the packet: "contract is draft — confirm it reflects intent." This skill **never runs `factory waive` or `factory confirm`** — those are the human's verbs, exactly like `factory choice`; an unattended run leaves parked items parked.

## Failure discipline

- **fail** = the product objectively did not meet the contract's expectation at a node (wrong outcome, dead end, material console/network error, or an objective craft defect — clipping, broken imagery, unstyled error/empty states, placeholder content, viewport collapse). Rework: `assure.rejected` + back to implement with the failing scenario named in the log data.
- **ambiguity** = the walk completed but a judgement call the contract doesn't settle remains (is this copy clear enough? is this next action obvious?). Park for the human with the reviewer's question quoted verbatim in the packet.
- **blocker** = the walk could not run (app won't launch, fixture missing, browser capability absent). Record in `assurance/blockers.md`, park. Environment fixed → the stage simply re-runs; blockers are never converted to passes by inspection.

## Spend

Log one spend event per reviewer dispatch batch, per the dispatch convention: `factory log ITEM spend --data '{"provenance":"measured","stage":"assure","source":"factory-assure","dispatches":<n>,"tokens":{"total":<n>}}'` with harness-reported counts, or `"provenance":"proxy"` and no `tokens` key when the harness reports none. Never estimate.
