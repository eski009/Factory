# Assurance packet — 0027-packet-respond-falls-through-to-factory-

**Packet Respond falls through to /factory:run when a decision pause is parked from an unexpected stage**

- stage: `assure` → parked `waiting-human`
- tier: `bug` · depth: `node`, extended by impact.json's declared adjacent nodes
- build under test: `factory/0027-packet-respond-falls-through-to-factory-` @ `c01eac8`
- round: **2** (blind re-walk)
- declared scenarios: **11 of 11 pass. No fails. No blockers.**

## Waiting on you

The declared gate is clean. I have **not** auto-advanced to ship, because one reviewer
returned a formal **ambiguity** with a verbatim unresolved question, and two independent
reviewers flagged a **leaked internal representation** on customer-facing packets. Deciding
those are out of scope is a judgement call this stage is not allowed to answer for you.

Both findings sit **outside** the declared scenarios and neither reviewer attached them to a
scenario verdict. If you judge them out of scope for this item, one command ships it:

```
factory confirm 0027-packet-respond-falls-through-to-factory-
```

`factory confirm` and `factory waive` are yours; this stage never runs them.

## Why round 1 was thrown away, and what is different now

Round 1 drove 11/11 to pass, but the walk was driven by an implementation-aware
orchestrator — no fresh-context reviewer could be dispatched. You rejected it as
non-independent and archived it to `assurance/degraded-round-1/`. Round 2 reused **none** of
that evidence.

Blindness enforced this round, per reviewer:

- **Input allowlist, and nothing else:** `brain/personas.md`, `brain/users.md`, that
  reviewer's own journey contract, and the item's `assurance/impact.json` — staged outside
  the worktree.
- **Structurally excluded:** any `git diff`/`log`/`show`/`blame` of the branch; everything
  under `.factory/items/0027-*/` including spec, plan, reviews, `log.jsonl` and
  `degraded-round-1/`; any prior review, verify or assure conclusion; any comparison against
  `main`.
- **Source code is never evidence.** Every verdict rests on a command the reviewer actually
  ran plus its captured output.
- The build-under-test worktree was verified to contain **zero** `.factory/items/0027-*`
  state before dispatch, so a reviewer inside it could not stumble onto the spec or plan.
- Three reviewers, one per journey, dispatched sequentially at Opus tier.

Two reviewers independently reported the same defect (raw Python dict reprs in
`## Recent events`) without either seeing the other's work — an incidental corroboration that
the isolation held.

## Journeys walked

| Journey | Contract | Surface | Scenarios | Result |
|---|---|---|---|---|
| J-002 Cost breaker decision — **the changed journey** | approved | cli | S1–S9 | 9/9 pass |
| J-001 Assure outcome readout — regression | approved | cli | S10 | pass |
| J-003 Redesign cap decision — regression | **DRAFT** | cli | S11 | pass |

⚠️ **J-003's contract is `draft`.** A draft contract does not block assurance, but please
confirm it reflects intent — S11's verdict is only as good as the draft's oracle.

Attribution is **off** for this repo (`assure_attribution: false`), so no base walk was owed
and no verdict may be recorded as pre-existing. Any fail would have routed straight back to
implement.

### J-002 — S1–S9, all pass

- **S1** plan-origin park renders `## Cost decision` and exactly one Respond bullet leading
  `factory cost-answer …` in both renderers; `/factory:run` count **0**.
- **S2** assure-origin park (B1 guard) renders the same single bullet; `factory confirm` and
  `factory waive` count **0** — the assure arm did not shadow the reason-prefix arm.
- **S3** canonical implement-origin fire: breaker line printed, `cost.breaker` logged, Respond
  block diffs empty against S1's.
- **S4** the narrow command is *real*: names `factory advance … plan`, the `implement` form
  appears **nowhere**, the rendered command exits 0, and the `implement` form is refused
  (`waiting-human item may only resume to 'plan'`, exit 2).
- **S5** unknown-prefix parks over {plan, implement, assure}: no decision section, no orphan
  verb bullet, exactly one action each.
- **S6** missing-field refusal is verbatim and exits 2; `None` count **0**, `Traceback` count **0**.
- **S7** four refusal arms over one fixture set are pairwise distinct; out-of-enum names the
  recorded value.
- **S8** recovery: `cost-answer continue` admits exactly one advance, then re-fires at the
  higher count and refuses as stale.
- **S9** interruption: fresh session finds the pause, no answer, packet still names
  `cost-answer`; operator never routed back to `/factory:run`.

### J-001 — S10 pass · J-003 — S11 pass

- **S10** three non-cost packets each render exactly one Respond bullet in both renderers, no
  cost/redesign material, unchanged `<h2>` set; the parked packet's command is real; the
  default-path golden suite is green (**903 tests, OK, 7 skipped**).
- **S11** all ten `paused-from` values the engine accepts, both config arms, 17 packets: exactly
  one `factory approach-answer` bullet each; `/factory:run`, `cost-answer`, `confirm`, `waive`
  all count **0**; bidirectional section↔bullet invariant **0 violations**; hostile assure arm
  (a `fail` verdict on disk) still resolved to `approach-answer` only.

## Unresolved judgement calls — these are why the item is parked

### ① J-001 N3/N4 — the shipped-with-known-fails readout did not render (ambiguity)

Two independently built items shipped (exit 0) carrying an attributed, owned, base-evidenced
J-001 fail with `assure.attribution: true`. Neither packet contains
`- shipped with known fails: <n>` nor a `## Shipped with known fails` section
(`grep -rn -i "known fail" docs/factory/packets/` → no matches), and `status --json` carries no
`assurance` key on any row. `advance … ship` writes no packet of its own.

> An item that shipped with a known fail is, on its packet's first screen, indistinguishable
> from an item that shipped clean, and the owning item id appears nowhere except inside a raw
> Python dict literal.

The reviewer's question, verbatim and deliberately unanswered:

> *Does the shipped-with-known-fails readout (`- shipped with known fails: <n>`,
> `## Shipped with known fails`, `assurance.non_blocking_fails` in `status --json`) require a
> state a customer cannot reach through the `factory` CLI verbs — and if not, is J-001's N3/N4
> oracle currently unmet?*

They declined to answer it from source, correctly. **Note this is J-001 territory, whose
`nodes_changed` is empty — this may well predate 0027 entirely.** With attribution off there is
no base walk to settle it, which is exactly why it comes to you rather than routing to implement.

### ② Leaked internal representation on every packet (craft, corroborated ×2)

`## Recent events` prints raw Python dict reprs into customer-facing copy — single-quoted keys,
Python-cased `False`:

```
- 2026-08-03T15:58:01Z assure.filed {'deduped': False, 'journey': 'J-001', 'owner': '0002-past-the-end-page-renders-a-stack-trace', 'scenario': 'S2'}
```

The J-001 reviewer classed this a **craft fail at N3, outside S10's claim**. The J-003 reviewer
independently logged it as advisory A1 and observed it on **all** packet types including
negative controls — which suggests pre-existing rather than 0027 collateral, but neither
reviewer could confirm that without a diff, and neither was permitted one.

Compounding: on the shipped-with-known-fails packet this dict literal is the **only** place the
owning item id appears anywhere.

## Polish

Advisories never fail the gate and never park an item. Ratify one and it binds the next run.

**J-002**

- **A1 (N3, craft)** — the narrow **command** is origin-aware but the **sentence** is not.
  Assure-origin renders `edit plan.md, then factory advance <id> assure`, which cannot do what
  it says: resuming at `assure` never re-executes the edited plan. Command is real; copy is the
  seam where the fix stopped.
- **A2 (N3/N4, trust)** — `continue` is the only option with no command. On the widened
  non-implement park the obvious guess is refused; the operator must borrow `narrow`'s command
  or eat one refusal. The refusal names the right stage, so nobody is stranded. *The option you
  are most likely to pick is the one the screen tells you least about.*
- **A3 (N4)** — after `cost-answer` and after the item resumed to `plan`, both packet files were
  still on disk still reading `waiting on you: cost breaker …` / `stage: waiting-human`. No
  record-time deletion observed, though impact.json describes it as existing and untouched.
- **A4 (N3, trust)** — one fact, two provenance tags on one page: `## Cost decision` says
  `[unmeasured] tokens: UNMEASURED`, `## Spend` says `[measured] tokens: none logged`.
- **A5 (N5)** — the session-start hook's only imperative is `Use /factory:run to advance the
  pipeline`, one line after `Next actionable: nothing actionable`. The packet itself is right;
  this is the shell around it.
- **A6 (N3, density)** — `## View the options` and `## Artifacts` render on every cost packet.
  Recorded as confirmation only; the 2026-08-02 ruling makes it non-gating.

**J-001**

- **Misleading stale-base refusal** — `base evidence is stale: recorded afb2ef85… on branch
  'factory/0001-…', merge base is now afb2ef85… on branch 'main'` prints the *same* sha on both
  sides; the real mismatch (the branch) is never named. An operator reading this at 7am
  concludes the gate is broken.
- `design/choice.md: no` renders on a backend item with no design gate.
- `"measured": null` in JSON vs `[measured] tokens: none logged` in prose.
- `factory next` did not surface a freshly filed owner item until prioritised by hand.

**J-003**

- **A3 (density)** — `## View the options` on a screen with no options; in HTML it duplicates
  the `Artifacts` list immediately below.
- **A4 (consistency)** — renderers diverge in Respond intro copy and in `View the options`
  contents. The *command* is byte-identical, which is what S11 asks.
- **A6 (craft)** — `factory advance <id> waiting-human` with no `--reason` exits 0 and writes
  `paused-reason: ` (empty, trailing space).
- **A5 (positive)** — cost-breaker and redesign-cap packets read as one surface; both
  reason-keyed arms hoist above the stage-keyed assure arm.

## Stated limits — clauses that were not discharged

Recorded so the pass is not read as broader than it is. None was softened into a pass; each is
scoped in `verdicts.json`.

1. **S3 "byte-identical to the shipped engine"** — requires inspecting another build. Out of
   bounds for a blind walk. The verdict rests on the customer-observable render.
2. **S10 "byte-identical to main"** — requires a branch comparison. Not attempted; the pass does
   **not** cover it. Discharged instead via the contract's own amended evidence class
   (`Empty section`, bid-0093): the checked-in default-path golden suite, green. That pins the
   renderers to the goldens; it cannot prove the goldens were not themselves edited.
3. **S5's literal wording** — "exactly one `/factory:run` bullet" is false for the assure origin,
   which correctly renders one `confirm`/`waive` bullet instead. The reviewer passed the
   substantive invariant rather than fail correct behaviour. **S5's wording wants narrowing to
   origins with no keyed arm of their own.**
4. **S11 draft gaps** — the contract is silent on who *creates* the packet at N2; "the coupling
   matrix" is never enumerated (the reviewer resolved it empirically and walked all ten accepted
   stages, a strict superset).
5. **Not exercised** — the `LOWER BOUND` suffix on measured figures inside `## Cost decision`
   (no fixture logged spend events) and the `Recommended:` arm for an item with no priority
   (priority is a hard gate at triage). Both outside S1–S9.
6. **Reported, not scored** — a `blocked` park carrying an identical `approach cap:` reason
   renders the `approach-answer` bullet with **no** `## Redesign decision` section, in both
   renderers: exactly the split S11's SWEPT note predicts, and the S5 residual one scenario up.

## Recommended confirmation walkthrough

About five minutes, in a throwaway repo — this is the spine of the fix:

1. Park an item from **plan** with a `cost breaker:` reason. Render the packet both ways.
   Confirm one `factory cost-answer` bullet and **zero** `/factory:run`.
2. Read the narrow line. Confirm it names `factory advance <id> plan`, run it (exits 0), then
   try the `implement` form and watch it be refused. *This is the bug that was filed.*
3. Repeat step 1 parked from **assure**. Confirm `confirm`/`waive` do not shadow the
   cost-answer bullet.
4. Write a `cost/answer.md` with `- rework-edges:` and no `- answer:`. Advance into implement.
   Confirm the refusal is the exact sentence and that `None` appears nowhere.
5. Then adjudicate the two calls above: scroll any packet's `## Recent events` and decide
   whether the raw dict repr is 0027's problem or its own item.

## Evidence

All under `.factory/items/0027-packet-respond-falls-through-to-factory-/assurance/`:

- `verdicts.json` — per journey, per scenario: verdict, expected, actual, typed evidence refs
- `run-manifest.json` — build under test, blindness allowlist, fixtures, reviewer models, spend
- `expectations.md` — merged before-the-fact predictions, written **before** each action
- `transcripts/J-002/transcript-S1.txt` … `transcript-S9.txt`
- `transcripts/J-001/transcript-S10.txt`, `transcript-S10-setup.txt`
- `transcripts/J-003/transcript-S11.txt`
- `transcripts/<J>/advisories.md`, `transcripts/<J>/expectations.md` — per reviewer, as returned
- `degraded-round-1/` — the rejected round, retained for provenance, excluded from every
  reviewer's input

Spend: 3 dispatches, measured, 403,895 tokens total (136,649 J-002 · 118,606 J-001 · 148,640 J-003).
