---
name: factory-bug
description: Use when a human reports a bug - understand it, replicate it BEFORE any fix work, and file a bug work item the existing pipeline carries to a proven fix
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

## Contract

- **Input:** the human's bug report, verbatim (from /factory:bug or direct invocation). The human is present — intake runs synchronously in this session.
- **Artifacts produced:** a new work item with `bug: true` frontmatter, `items/<id>/repro.md`, a `repro.confirmed` event (replication success path only), `items/<id>/triage.md`, and the two seeded acceptance criteria in the item body.
- **Exit — replicated:** item advanced to `spec`; /factory:run carries it from there. The engine's plan gate independently requires `repro.md` + `repro.confirmed` for bug items — this skill cannot bypass it.
- **Exit — cannot replicate or still ambiguous:** item paused `waiting-human` with a packet; never proceed to fix an unreplicated bug.

The core promise: **we never claim a bug is fixed when it isn't.** The recorded repro is the analogue of TDD's red test — it exists before any fix work, and verify re-runs it before anything ships.

## Steps

1. **Understand.** Restate the bug in one or two sentences: what the user did, what happened, what they expected. If the report is ambiguous on any point needed to attempt replication, ask **at most one round** of clarification questions now, synchronously (the cap is skill policy, never engine state). If ambiguity survives that round — or no answer is available (non-interactive invocation) — do not guess: file the item (step 3, skipping replication), then `factory advance ITEM waiting-human --reason "bug: needs clarification - <question>"`, `factory packet ITEM`, and stop.

2. **Decide kind.** `ui` or `mixed` **only when the fix changes the intended design**; restore-to-spec visual bugs stay `backend` — a padding nit must not become a human design-gate stop. `kind` stays the design-routing axis; bug-ness is the separate `bug` flag.

3. **File the item.** `factory add "<short bug title>" --kind <kind>`. Then edit `items/<id>/item.md` directly: set the body to the verbatim bug report (plus any clarification answers, marked as such), and add `bug: true` to the frontmatter — a plain frontmatter field, not CLI-settable, same convention as triage's `kind` correction. Also set the item's tier to bug: `factory tier ITEM bug` (a defect gets the light correctness-only review and skips market research — see the tier profiles in the capabilities/`factory doctor` readout). `tier: bug` is the materiality axis; the separate `bug: true` flag still drives the repro gate.

4. **Replicate — before any fix work.** Actually run the failing path. **A prose description is not a repro.**
   - On success, write `items/<id>/repro.md`:

     ```markdown
     # Repro — <item-id>
     ## Command
     (fenced code block: the exact command; for human-confirmed visual repros, exact observation steps)
     ## Expected
     One line: the correct behavior.
     ## Observed (verbatim)
     (fenced code block: verbatim failing output, trimmed with elisions marked)
     ## Environment
     Commit SHA, date, anything needed to re-run.
     ```

   - Then log the evidence event: `factory log ITEM repro.confirmed --data '{"command": "<exact command>", "exit": <code>, "mode": "command"}'`.
   - Visual bugs with no runnable command: the repro is a human-confirmable note — exact steps to observe the failure — confirmed by the present human now, logged with `"mode": "human-confirmed"` and no `exit` key. The design gate still applies via kind as usual.

5. **Cannot replicate → hard stop.** Record every attempted command and its actual output in `items/<id>/repro.md` under an `## Attempts (unconfirmed)` heading. Do **not** log `repro.confirmed`. Then `factory advance ITEM waiting-human --reason "bug: cannot replicate - <what was tried>"` and `factory packet ITEM`. Append a house-style section to the packet: one-sentence recommendation, capped evidence bullets (what was run, verbatim output), exactly one copy-pasteable next action. This is the cheapest failure point — it halts before any plan/implement spend.

6. **Seed the mandatory acceptance criteria.** Append to the item body a section titled exactly `## Acceptance criteria (seeded at bug intake — carry into spec.md verbatim)` containing:
   1. The recorded repro in `items/<id>/repro.md` now passes: running its `## Command` produces the `## Expected` behavior, and the `## Observed` failure no longer occurs.
   2. A regression test exists in the project's test suite that failed on pre-fix code (red-run evidence from the implement stage's TDD discipline).

   These two criteria are non-optional. The spec stage carries them verbatim into `spec.md`, where the verify stage's Iron Law enforces them with fresh evidence.

7. **Write the intake triage record and enter the pipeline.** Write `items/<id>/triage.md`: decision (build — confirmed replicated bug), the kind rationale from step 2, and priority. Set priority with `factory priority ITEM N` — ask the human while they are present; default 1 (front of queue) if they don't say. Then `factory advance ITEM triage` and `factory advance ITEM spec`. No council runs at intake; the council still reviews the fix at the review stage. From spec onward this is ordinary pipeline work — implement branches per item with TDD, ui/mixed items pass the design gate, ship merges per policy.

8. **Spend.** If replication dispatches subagents, log spend per the dispatch convention: `factory log ITEM spend --data '{"provenance":"measured","stage":"triage","source":"factory-bug","dispatches":<n>,"tokens":{"total":<n>}}'` with harness-reported counts, or `"provenance":"proxy"` and no `tokens` key when the harness reports none. Never estimate; main-loop burn is never logged as measured.

## Sequencing note

The clarification / cannot-replicate `waiting-human` stops are natural consumers of item 0005's generalized interactive decisions when it unblocks; this skill builds no new interactive page — plain house-style markdown packets only.
