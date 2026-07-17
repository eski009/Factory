# Journey Assurance — behavioral verification (dogfood run)

- **Date:** 2026-07-17
- **Scope:** the journey-assurance design's "Behavioral (manual dogfood)"
  test: a scratch web app driven end-to-end through the real engine —
  inventory seeding, impact declaration, a real browser assurance run
  producing evidence, a forced fail routing back to implement, and a
  passing re-run — with the fresh-context property enacted by dispatching
  genuinely clean-context reviewer subagents.
- **Verdict:** PASS. The system caught every planted cross-surface defect,
  plus three unplanted ones, refused every dishonest exit, parked its
  genuine judgement calls for a human instead of resolving them, and
  compounded the human's answers back into the journey contract.

## The rig

A scratch product, **ClaimLite** (static three-screen expense-claim app),
with journey **J-001 submit-expense-claim**: N1 landing → N2 details → N3
confirmation. The landing page promises *"Takes 2 minutes. No account
needed."* — a promise the contract declares binding on the whole journey.
v1 planted three defects **no single-screen check would compose into a
journey failure**:

1. N2 renders a login wall ("Sign in to continue") — each screen fine in
   isolation; the *pair* is the incoherence.
2. N3 is a bare "Submitted." — no reference, no next action (dead end).
3. N3 fetches `/api/status`, which 404s, logging a console error.

Factory state was driven by the real CLI (`factory init`, `add`,
`priority`, `tier`, `journeys`, `advance`) through every real gate:
triage → spec (with `## Journey impact` + `impact.json` carrying the
v0.9.1 shape: viewports `desktop-1280`/`mobile-390`, explicit
`adjacent.upstream: ["N1"]`, scenario kinds `happy` and `empty`) →
design → plan → implement → review → verify → assure. `factory validate`
accepted the tree; `factory status` surfaced the new journey-coverage-debt
line ("1 of 2 journeys inventory-only, 1 draft contracts").

## Round 1 — the fresh-context reviewer catches the incoherence

A reviewer subagent was dispatched with ONLY the input allowlist — persona
(Riley), the J-001 draft contract, `impact.json`, and the contract's Run &
fixtures section. No implementer transcript, no diffs, no claim of
readiness. It launched the app per the contract, drove real Chromium at
both declared viewports, appended expectations to `expectations.md`
**before** each action, captured 10 screenshots + 5 DOM/a11y snapshots +
console.ndjson + network.ndjson, and visually inspected the rendered
screens.

Result: **both scenarios fail**, with the cross-screen rule applied as
written — the fail recorded at N2 *citing N1's evidence* ("the landing
promise binds"). It caught all three planted defects **and one unplanted
one**: the login form submitted via GET, leaking the customer's email and
password into the URL query string — discovered, not confirmed. It also
flagged a favicon 404 as a material console error (the contract whitelists
nothing).

## Engine refusals (negative controls, all live)

- `advance ship` with no assurance evidence → refused
  (`assure.passed ... required`).
- `factory log <id> assure.waived` from a non-human path → refused
  (human-verb single-writer).
- A dishonestly logged `assure.passed` over failing `verdicts.json` →
  ship still refused (`verdict 'fail' is not pass`) — the artifact layer
  is independent of the event layer.
- After rework, the round-1 `assure.passed` became stale by round-scoping
  (must postdate the latest `implement.completed`).

The honest path then took the real backward edge: `assure.rejected
{round: 1}` → `advance implement`.

## Round 2 — rework, fresh round, the ambiguity path

v2 replaced the login wall with the claim form (native validation),
gave N3 a reference (`CLM-1042`), a what-happens-next line, a track link,
a working `/api/status`, and a favicon fix. Prior-round assurance
artifacts were deleted (impact.json kept — spec owns it), the item
re-earned review/verify through the real gates, and a **new**
fresh-context reviewer (again, allowlist only, no knowledge of round 1)
walked the journey.

Result: `empty-1` **pass** on both viewports (native validation anchored
to the Amount field, nothing submitted, zero console output). `happy-1`
came back **ambiguity**, not pass — the reviewer met every explicit
oracle, then went further than the oracles: it probed the journey **as a
second fresh customer** with different claim data and found the reference
is a constant (`CLM-1042` for everyone), and it noticed N3 promises an
email although the journey never collected one. Both are judgement calls
the draft contract doesn't settle, and the reviewer refused to resolve
them itself — it reported the questions verbatim, exactly per its agent
contract.

The honest exit then ran end-to-end, live:

1. `advance ship` over the ambiguity verdicts → **refused**
   (`verdict 'ambiguity' is not pass`), even with `assure.passed` logged.
2. The item parked `waiting-human` with a packet quoting the questions.
3. The human verb `factory waive --reason "..."` recorded the operator's
   decision (fixture limitations, gaps accepted as escapes), the item
   resumed to assure and shipped — the round-scoped waiver satisfied the
   gate — then `ship.merged` → `done`.
4. Both discoveries became escapes (`esc-0001` missing-oracle,
   `esc-0002` missing-contract-detail); `factory status` surfaced
   "open escapes: 2"; both were promoted via
   `factory promote --via contract:` into amendments on the J-001
   contract (a uniqueness oracle at N3; a promises-require-collected-data
   trust requirement) and the open-escape line cleared. `factory validate`
   stayed green throughout.

## What this proves

- The assure stage performs a **genuine fresh-context visual inspection of
  a complete customer journey** — conclusions drawn *across* screens
  (N2 failed because of what N1 promised), not per-element.
- Evidence is real and engine-validated: screenshots per node per declared
  viewport, DOM/a11y snapshots where semantics carry the proof, console
  and network transcripts, expectations recorded before acting.
- The deterministic gates hold the line against every dishonest exit
  exercised live: no evidence → no ship; failing verdicts → no ship even
  with `assure.passed` logged; ambiguity verdicts → no ship; a skill
  logging the human-only waiver event → refused. The two honest exits both
  worked: rework via the `assure.rejected` backward edge, and a
  human-recorded, round-scoped waiver. (Acceptance of a complete all-pass
  artifact set, and staleness of pre-rework evidence, are pinned by the
  engine unittests.)
- The declared traceability drives scope: the reviewer walked the
  adjacent upstream node and both declared viewports because
  `impact.json` said so.
- The judgement split holds under pressure: the round-2 reviewer met
  every deterministic oracle, still surfaced two coherence questions, and
  **parked them instead of self-resolving** — the human stayed the last
  word on meaning, and their answers compounded into the contract via the
  escape register.

Evidence for this run lives in the session scratchpad (scratch rig,
disposable); the durable artifacts are the engine tests
(`tests/test_machine.py`, `test_initrepo.py`, `test_cli_journeys.py`)
that pin every gate behavior exercised here.
