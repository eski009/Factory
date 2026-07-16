---
name: factory-assure
description: Use when a factory item is at stage assure - a fresh-context journey reviewer walks the affected journeys against the running product and the engine-validated evidence decides ship
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

## Contract

- **Entry stage:** `assure` (the engine's gate already required `verify.green`).
- **Artifacts produced:** `items/<id>/assurance/` — `run-manifest.json`, `expectations.md`, `verdicts.json`, evidence files (`screenshots/`, `console.ndjson`, `network.ndjson`, transcripts), `blockers.md` when blocked.
- **Exit:** all scenarios pass → `factory log ITEM assure.passed`, then if `"assure"` is in the config `gates` list, `factory advance ITEM waiting-human --reason "assurance passed - awaiting human confirmation (factory confirm ITEM)"` + `factory packet ITEM`; otherwise `factory advance ITEM ship`. Any objective fail → `factory log ITEM assure.rejected --data '{"round": <n>}'` + `factory advance ITEM implement` (the engine caps rework at 2, then blocked). Ambiguity or blocker → park: `factory advance ITEM waiting-human --reason "<what needs a human>"` + `factory packet ITEM` — never a silent pass, never a self-answered judgement call.

Review asked "is the code sound"; verify asked "do the checks pass"; this stage asks **"can the customer get through it"** — against the running product, in a context that has never seen the implementation.

## Read first

`items/<id>/spec.md` (`## Journey impact`), `items/<id>/assurance/impact.json`, `docs/factory/journeys/graph.json`, and each affected journey's contract under `docs/factory/journeys/contracts/`. Read the item's tier from `factory status --json` and the assure depth from `factory doctor --json` → `tiers` → `assure`: `node` = the changed node plus its immediate transition (bug), `affected` = every affected journey's required scenarios including interruption paths (feature), `full` = affected plus core journeys the item touches, including adjacent journeys where state carries across (epic).

## Dispatch — one fresh journey-reviewer subagent per affected journey

Dispatch `agents/journey-reviewer.md` once per affected journey, sequentially, at the most-capable model tier (references/model-tiering.md) — and on a different model from the one that ran implement when the session supports model overrides. Compose each reviewer's prompt ONLY from this input allowlist:

- `docs/factory/brain/personas.md` and `users.md` (who the customer is)
- that journey's contract (draft or approved — note which)
- the item's `impact.json` (nodes, transitions, new states, required scenarios)
- the contract's Run & fixtures section (exact launch commands, fixture setup, credentials through the contract's fixture mechanisms)

Structurally excluded — never the implementer transcript, never review/verify conclusions or diffs, never any claim that the feature is "complete" or "ready": the reviewer must discover what the product does, not confirm what the pipeline hopes. If a required input is missing (no contract, no Run & fixtures, no fixture credentials), that journey is a **blocker** — record it and park; do not improvise a launch path.

## What the reviewer does (its walk, enforced by its agent file)

For every node in scope it: (1) states what the customer currently knows, (2) predicts what the customer expects next — written to `assurance/expectations.md` BEFORE acting, (3) performs the action, (4) compares expected vs actual, (5) captures screenshot/DOM evidence, (6) inspects console errors, (7) inspects network failures or unexpected requests, (8) records `pass | fail | ambiguity | blocker` per scenario with typed evidence refs. Material console errors and unexpected 4xx/5xx responses are fails unless the journey contract explicitly whitelists them as known noise.

**Surface drivers.** Browser-borne journeys require the **Browser drive** capability (capabilities skill; references/browser-drive.md — Playwright MCP, chrome-devtools MCP, or Claude-in-Chrome, matched behaviorally). Capability absent → the journey is a blocker → park; the parked packet names `factory waive ITEM --reason "..."` as the human's override. CLI/API journeys need no browser: the reviewer runs the real commands a customer or caller would run and captures typed transcript evidence instead of screenshots.

## Orchestrator composes the gate artifacts

The reviewer returns a structured report and writes ONLY evidence files under `items/<id>/assurance/`. This session (the orchestrator) then writes:

- `run-manifest.json` — what was launched and driven, per journey (commands, urls, fixture state, reviewer model).
- `verdicts.json` — per journey, per scenario: verdict, expected, actual, typed evidence refs (`screenshot | dom | console | network | transcript`, paths relative to the item dir). Shape: `schemas/assurance-verdicts.schema.json`; every declared journey and every impact.json scenario must be covered — the ship gate refuses gaps, missing evidence files, and any non-pass verdict.

Then take the Exit branch that matches the verdicts. A draft contract never blocks assurance, but flag it in the packet: "contract is draft — confirm it reflects intent." This skill **never runs `factory waive` or `factory confirm`** — those are the human's verbs, exactly like `factory choice`; an unattended run leaves parked items parked.

## Failure discipline

- **fail** = the product objectively did not meet the contract's expectation at a node (wrong outcome, dead end, material console/network error). Rework: `assure.rejected` + back to implement with the failing scenario named in the log data.
- **ambiguity** = the walk completed but a judgement call the contract doesn't settle remains (is this copy clear enough? is this next action obvious?). Park for the human with the reviewer's question quoted verbatim in the packet.
- **blocker** = the walk could not run (app won't launch, fixture missing, browser capability absent). Record in `assurance/blockers.md`, park. Environment fixed → the stage simply re-runs; blockers are never converted to passes by inspection.

## Spend

Log one spend event per reviewer dispatch batch, per the dispatch convention: `factory log ITEM spend --data '{"provenance":"measured","stage":"assure","source":"factory-assure","dispatches":<n>,"tokens":{"total":<n>}}'` with harness-reported counts, or `"provenance":"proxy"` and no `tokens` key when the harness reports none. Never estimate.
