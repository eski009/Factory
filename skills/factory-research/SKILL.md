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
- `deep` — `web` plus a persona set (primary + secondaries) and a fuller competitive teardown; fan out the gather step per competitor/segment (see the `capabilities` skill).

If the depth needs the web and this run has no web access, **degrade to `inputs-only`** and add an entry to `docs/factory/brain/open-questions.md` naming the gap ("market/user web research not run — no web access this run; re-run with web for deeper grounding"). A missing capability degrades output, never blocks the run.

## 2. Assemble the research seed

Gather the grounding: the intake-mined surfaces (`constraints.md`, `design-system.md`, `users.md`), the PRD/design file if given, and the repo's outward surface (`README`, routes/screens). This is the seed for the council.

## 3. Council research mode

Run the `council-review` skill in **research mode** with review root `.factory/runs/research/` and the seed from step 2. Research mode dispatches only the outward-facing seats — `customer` (jobs-to-be-done, real user pains/voice), `commercial` (market, competitors, positioning), `product` (segments, use cases, differentiation), `ui-taste` (category design conventions). Each researches its lens (web at `web`/`deep`, inputs-only otherwise); every claim carries a citation or is marked UNSOURCED. The synthesis drafts the persona(s) + market read into `.factory/runs/research/synthesis.md`.

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

Report the persona label(s), competitor count, and number of assumptions logged, and remind that human review precedes `/factory:run` or `/factory:roadmap`.
