---
name: factory-research
description: Use when researching the product, market, and user at project initiation to seed a cited persona - runs the council outward, evidence only, behind the hard gate
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

## Purpose

Seed two product-brain surfaces the council reasons from — `docs/factory/brain/personas.md` (who the product is for) and `docs/factory/brain/market.md` (where it sits) — by researching the product, its market, and its users. Runs once at initiation, a sibling of `factory-intake`/`factory-roadmap`. A persona is where products invent a confident fictional user; here it is always a **cited hypothesis** the human reviews at the brain hard gate, never authored fact.

## Inputs

`$ARGUMENTS` may name a PRD path and/or a design-file path (greenfield), plus an optional `--depth inputs-only|web|deep` override. A named-but-missing file is just absent context, not a refusal. With no arguments, research the target repo as-is (brownfield), building on whatever `factory-intake` already mined.

## 1. Depth

Read `research.depth` from `.factory/config.json` (`inputs-only | web | deep`, default `web`); a `--depth` argument overrides it for this run.

- `inputs-only` — reason only from the PRD/repo already on hand; no web.
- `web` (default) — research the open web (competitors, category conventions, real user voice in reviews/forums), citing URLs; produce one primary persona + a market read.
- `deep` — `web` plus a persona set (primary + secondaries) and a fuller competitive teardown; fan out the gather step per competitor/segment (see the `capabilities` skill). Depth `deep` also runs the focus-group step (§3b) for material (`tier: epic`) work — see its Trigger; a `--focus-group` argument forces it at any depth, `--no-focus-group` suppresses it at `deep`.

When this research run is scoped to a specific work item or roadmap candidate, cap the effective depth at that item's tier `research` profile (`factory doctor --json` → `tiers`): a `feature` caps at `web` (no focus group), a `bug` at `off` (no research), an `epic` may go to `deep`. The `research.depth` config is the global ceiling; the tier caps it further for non-material work.

If the depth needs the web and this run has no web access, **degrade to `inputs-only`** and add an entry to `docs/factory/brain/open-questions.md` naming the gap ("market/user web research not run — no web access this run; re-run with web for deeper grounding"). A missing capability degrades output, never blocks the run.

## 2. Assemble the research seed

Gather the grounding: the intake-mined surfaces (`constraints.md`, `design-system.md`, `users.md`), the PRD/design file if given, and the repo's outward surface (`README`, routes/screens). This is the seed for the council.

## 3. Council research mode

Run the `council-review` skill in **research mode** with review root `.factory/runs/research/` and the seed from step 2. Research mode dispatches only the outward-facing seats — `customer` (jobs-to-be-done, real user pains/voice), `commercial` (market, competitors, positioning), `product` (segments, use cases, differentiation), `ui-taste` (category design conventions). Each researches its lens (web at `web`/`deep`, inputs-only otherwise); every claim carries a citation or is marked UNSOURCED. The synthesis drafts the persona(s) + market read into `.factory/runs/research/synthesis.md`.

## 3b. Focus group (opt-in)

Simulated structured interviews with 4–6 stakeholder personas of the *target
product*. Templates and hard caps live in this skill's `focus-group.md`
reference file (under its own `references/` directory) — follow them exactly. **Trigger:** runs only when the resolved depth is `deep` **and** the work is
material — i.e. the item or roadmap candidate driving this research is
`tier: epic` (or, at bare product initiation with no specific item, the
product itself is the material undertaking). A `feature`- or `bug`-tier
context never triggers the focus group, even under a global `deep` — the
focus group is for material epics only (guard rail). It never runs on the default `web` path or at
`inputs-only` without the explicit flag. An explicit
`--focus-group` argument still forces it at any depth; `--no-focus-group`
suppresses it. When the trigger is off, this section is skipped entirely.

All artifacts live under `.factory/runs/research/focus-group/<YYYY-MM-DD>/`
(same-day re-runs suffix `-2`, `-3`, …): `roster.md`, `guides/`,
`transcripts/`, `findings.md`, `spend.md`.

1. **Roster.** The orchestrator (never a subagent) derives 4–6 personas from
   the research seed and council synthesis — SMEs, potential customers,
   buyers, decision-makers — spanning at least two classes, per the roster
   template. Roster personas are ephemeral: no council memory, no
   reputation entries, no `agents/` files.
2. **Interview guides.** One per persona, tailored to that stakeholder's
   relationship to the product, per the guide template: ≤500 words,
   6–10 open-ended questions, human-usable as-is (a human can read one
   verbatim to a real person). The guides are a first-class artifact — the
   bridge to interviewing real people.
3. **Simulated interviews.** Uses one subagent per persona, one interview round
   each, sequential by default (fan-out per the `capabilities` skill is an
   optional upgrade), 4–6 dispatches maximum, no cross-persona debate — a
   subagent sees only its own roster entry, guide, and the product seed.
   Each transcript opens with the simulation banner from the template.
4. **Findings + firewall.** The orchestrator synthesizes `findings.md` under
   the template caps. Every interview-derived claim carries
   `(simulated: focus-group run <date>)` and never fact-grade `(source:)` —
   in findings, in `synthesis.md`, and in any brain surface it reaches. A
   summary is mirrored into `docs/factory/brain/open-questions.md` naming
   the run directory and stating the findings are unvalidated hypotheses,
   resolved only by interviewing real humans with the guides. This step may
   never edit, resolve, or mark progress against the "Persona validation"
   entry in open-questions.md. (See the synthetic-evidence rule in
   `docs/factory/brain/constraints.md`.)
5. **Spend log.** Write `spend.md` per the template — the run's own
   token/effort record (or the explicit UNMEASURED marker plus effort
   proxies). Quote its summary in the Exit report.

**Autopilot:** never silent — under autopilot the focus group runs only if
the human pre-configured `research.depth: "deep"` **and** the research is for a material (`tier: epic`) context (per the §3b Trigger); autopilot never adds
`--focus-group` on its own, and the packet must name that a simulation ran,
its run directory, and its spend summary.

**Idempotency:** a re-run creates a new dated run directory, augments prior
runs (never clobbers), and appends its open-questions mirror rather than
rewriting prior entries.

## 4. Seed the surfaces (evidence only)

From the synthesis, write:

- `docs/factory/brain/personas.md` — the primary persona (a set at `deep`): Label, Summary, Context, Goals, Jobs-to-be-done, Pains, Behaviors/drivers, Voice (cited quotes), Not-for, Confidence & assumptions. Every claim carries `(source: <url-or-path>)` or `(assumption)`.
- `docs/factory/brain/market.md` — category, competitors (cited), table-stakes/conventions, gaps & differentiation, positioning, assumptions.

Same discipline as intake: nothing invented into a surface; every unsourced trait or open unknown is mirrored into `open-questions.md`; confidence is proportional to evidence — a thin honest persona is the right output when sources are thin. `users.md` stays the broader user-notes surface; `personas.md` is the sharpened, addressable persona.

This is a *seed*, exactly like intake seeding `users.md`: the bid→judge firewall governs ongoing brain changes after the gate, not this initial write.

## 5. Idempotency

On a re-run, if `personas.md`/`market.md` already carry real content, refresh and augment with new citations rather than clobbering; report what changed.

## Hard gate

Always say this to the user when you finish, verbatim: "A human reviews the seeded brain before the first council run treats it as ground truth — say so when you finish." Present `personas.md`, `market.md`, and the intake surfaces for review, then stop. Running unattended (autopilot), write a packet summarizing the seeded research and stop — never self-approve, never proceed to triage.

## Exit

Report the persona label(s), competitor count, and number of assumptions logged, and remind that human review precedes `/factory:run` or `/factory:roadmap`. When the focus-group step ran, also report the roster size, the run directory, and the spend summary from `spend.md`.
