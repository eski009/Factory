# Factory Phase 8 — Initiation Research Stage (Persona & Market): Design Spec

- **Date:** 2026-07-06
- **Owner:** Steve
- **Status:** Approved (in-session), extends the main spec (`2026-07-03-software-factory-design.md`) and the Phase 7 spec (`2026-07-03-factory-phase7-prd-brownfield.md`)

## Purpose

Close the gap between "the brain is seeded from what the PRD/repo literally says" and "the factory understands *who* the product is for and *how it sits in its market*." A new initiation research stage runs the council outward — researching the product, its market, and its users — and proposes a **cited persona** plus a **market read** that the human reviews at the existing brain hard gate. The persona then becomes durable context every downstream decision reasons against ("does this serve our persona?"). Product and UI judgement sharpen from grounded understanding, not invention.

Overriding constraint: this must **strengthen, not dilute**, the evidence discipline. A persona is exactly where products hallucinate a confident fictional user; here it is always a *cited hypothesis behind the human gate*, with every unsourced trait flagged as an assumption and mirrored to `open-questions.md`.

## 1. The `factory-research` stage

New skill **`factory-research`** + command **`/factory:research [<prd-path>] [<design-path>] [--depth inputs-only|web|deep]`**. It runs at project *initiation* — a sibling of intake/roadmap (per-project), **not** a per-item pipeline stage in the work-item state machine.

**Invocation & both on-ramps:**
- **Brownfield:** `/factory:init` runs `factory.py init` + `validate`, invokes `factory-intake` to mine the repo, then invokes **`factory-research`**, then states the single brain hard gate over the whole seeded brain (now including persona + market).
- **Greenfield:** the user runs `/factory:research <prd> [<design>]` (before `/factory:roadmap`), which consumes the PRD/design and produces the same outputs under the same gate.
- **Re-runnable** at any time; **idempotent** — on re-run it refreshes/augments existing `personas.md`/`market.md` with new citations rather than clobbering, and reports what changed.

**The loop (skill body):**
1. **Depth.** Read `research.depth` from `.factory/config.json` (`inputs-only | web | deep`, default `web`); an optional `--depth` argument overrides it for a single run. Detect web availability; if the depth needs web and the run has none, **degrade to `inputs-only`** and record the gap in `open-questions.md` ("market/user web research not run — no web access this run; re-run with web for deeper grounding").
2. **Assemble the research seed.** The intake-mined brain surfaces (`constraints.md`, `design-system.md`, `users.md`), the PRD/design file if provided, and the repo's outward surface (README, routes/screens).
3. **Council research mode** (§3) produces the synthesized persona(s) + market read.
4. **Seed the surfaces** (§4), evidence-only; unsourced → `open-questions.md`.
5. **Hard gate.** State the `factory-intake` hard-gate sentence **verbatim**, present the seeded brain (`personas.md`, `market.md`, and the intake surfaces) for human review, and stop. Running unattended (autopilot context), write a packet summarizing the seeded research and stop — never self-approve, never proceed to triage.
6. **Exit.** Report what was produced (persona label(s), competitor count, number of assumptions logged) and remind that human review precedes `/factory:run` or `/factory:roadmap`.

## 2. Depth knob & graceful degradation

`config.research.depth`:
- **`inputs-only`** — reason only from the PRD/repo already on hand; no web. Fast, cheap; honest but bounded by provided inputs.
- **`web`** (default) — each council seat researches its lens on the web (competitors, category conventions, real user voice from reviews/forums), citing URLs; synthesizes one primary persona + a market read.
- **`deep`** — `web` plus a persona *set* (primary + secondaries) and a fuller competitive teardown; the gather step may fan out (§3).

Degradation is one-directional and logged: a run that cannot reach the web drops to `inputs-only` behaviour and names the gap in `open-questions.md`, consistent with the capability-adapter philosophy — a missing capability degrades output, never blocks the run.

## 3. Council research mode

Add a **research mode** to `council-review` — a third seed variant beside triage and review, running the same bounded two-round, no-group-chat protocol; only the seed content and the participating seats differ:
- **Seats:** the outward-facing seats only — `customer`, `commercial`, `product`, `ui-taste`. (`architecture`/`engineering-quality` have no persona/market lens and are not dispatched in this mode.)
- **Review root:** `.factory/runs/research/` — no item exists yet at initiation, so it uses the caller-supplied review-root mechanism already added for batch triage.
- **Round 1 (research):** each seat investigates its lens and returns cited findings — `customer` → jobs-to-be-done, real user pains/voice; `commercial` → market, competitors, positioning; `product` → segments, use cases, differentiation; `ui-taste` → category design conventions. At `web`/`deep` seats do web research citing URLs; at `inputs-only` they reason only from the seed. Every claim cites evidence or is marked UNSOURCED (→ an assumption downstream).
- **Synthesis:** the orchestrator dedupes/groups and drafts the persona(s) + market read into the run's `synthesis.md`.
- **Fan-out (`deep`):** the gather step may run parallel per-competitor / per-segment research subagents via the capabilities skill's fan-out reference; the sequential per-seat path is the degraded default.

The firewall is untouched. At initiation the research **seeds** the brain (§4), exactly as intake seeds `users.md`; the bid→judge firewall continues to govern only *ongoing* brain changes after the gate.

## 4. Outputs & evidence discipline

Two new first-class brain surfaces under `docs/factory/brain/`:

**`personas.md`** — one primary persona at `web` (a set at `deep`); each field's claims carry `(source: …)` or `(assumption)`:

- **Label** (e.g., "Primary · Solo indie developer") · **One-line summary** · **Context** (environment, tools, constraints) · **Goals** · **Jobs-to-be-done** · **Pains** · **Behaviors / drivers** · **Voice** (cited quotes/paraphrases) · **Not for** (anti-persona) · **Confidence & assumptions**.

**`market.md`** — category/space · competitors (cited one-liners) · table-stakes/conventions users expect · gaps & differentiation opportunities · positioning notes · assumptions.

Discipline (identical to intake/roadmap seeding):
- Every claim is cited to a real source or explicitly marked an assumption; nothing is invented into the surface.
- Unsourced traits and open unknowns are mirrored into `open-questions.md`, never smoothed over.
- Confidence is proportional to evidence — a thin honest persona is the correct output when sources are thin.
- `users.md` remains the broader user-notes surface; `personas.md` is the sharpened, addressable persona.

## 5. Downstream: the persona is reasoned against

The payoff — the persona is not written once and forgotten:
- `personas.md` and `market.md` are added to the brain surfaces `council-review` pulls into its seed in **both** triage and review modes, so every build/priority decision and every code review implicitly asks "does this serve our persona?"
- `factory-spec` and `factory-design` each gain a one-line instruction to check the item against `personas.md`. (Minimal — the council seed-surface addition is the real enforcement.)

## 6. Engine footprint (thin)

- `schemas/config.schema.json`: add a `research` object with a `depth` enum (`inputs-only|web|deep`); `initrepo` writes the default `research: {"depth": "web"}` into `config.json`.
- `templates/docs-factory/brain/personas.md` + `market.md`: two scaffold templates carrying the §4 section headings and a one-line preamble ("seeded by factory-research; every claim cited or marked an assumption"); `initrepo` copies them like the other brain surfaces.
- **No new engine subcommands, no new state-machine stages, no ledger changes.**

## 7. Testing

- **Structural** (`test_plugin_structure.py`): the `research` command exists with frontmatter; the `factory-research` skill exists and mentions `personas.md`, `market.md`, the verbatim hard-gate sentence, "research mode", and `research.depth`.
- **Coherence** (`test_plugin_coherence.py`): `commands/research.md` names the `factory-research` skill; `council-review`'s seed references `personas`/`market` (proving the downstream hook is wired).
- **Engine:** `config.schema.json` accepts each valid `research.depth` and rejects an invalid value; `initrepo` scaffolds `personas.md` + `market.md`; the default `config.json` carries `research.depth`.

## Non-goals (Phase 8)

- **A research run-ledger** (a validated `.factory/runs/research/` provenance record surfaced by `validate`/`doctor`) — deferred; the thin build seeds the brain and relies on in-surface citations.
- **Fan-out as its own architecture** — folded in as a `deep`-depth behaviour via the existing capabilities reference, not a new subsystem.
- **Live design-tool / market-data APIs** — "research" means what the model can read on the open web plus provided files.
- **Automatic re-research on PRD/market change** — re-running `/factory:research` is manual; idempotency prevents duplication.
- **Revealed-preference taste learning from post-ship human diffs** — separately considered and deferred (2026-07-06); orthogonal to this stage.
