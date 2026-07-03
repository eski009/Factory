---
name: council-review
description: Use when a factory stage needs the council's bounded multi-agent review (triage or code review) - runs the two-round protocol without group-chat drift
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

Bounded two-round council protocol (spec §6), ported from superpowers-council. Runs identically for both council moments — triage and review — only the seed content differs. No group chat: agents never see each other's notes, only the seed and the synthesis.

## Attention, not suppression

Before Round 1, run `factory reputation --json`. Use scores to order which agents' output you read and weigh first. Reputation ranks attention — it never suppresses or skips a claim, no matter how low an agent's score.

## Protocol

1. **Seed context.** Write `items/<id>/reviews/seed-context.md`:
   - Triage mode: the item body + relevant brain surfaces (roadmap, open-questions, decisions, constraints).
   - Review mode: a diff summary + the item's spec.md.

2. **Round 1 — independent.** Dispatch the six council agents (`agents/council-product.md`, `council-ui-taste.md`, `council-architecture.md`, `council-engineering-quality.md`, `council-customer.md`, `council-commercial.md`) as parallel Task subagent calls in one message — the degraded baseline; see the `capabilities` skill for fan-out upgrades. Each agent receives ONLY `seed-context.md` and its own `docs/factory/council/<role>.md` — never another agent's memory file or round notes. Each agent:
   - Raises at most 3 new claims.
   - Cites evidence (file path, line, or URL) for each claim, or marks it explicitly unsourced.
   - Writes `reviews/round-1/<role>.md`.

3. **Orchestrator synthesis.** The invoking session (not a subagent) reads all six round-1 files, dedupes overlapping claims, groups by topic, flags conflicts between roles, and decides which agents (if any) need Round 2. Writes `reviews/synthesis-1.md`.

4. **Round 2 — delta-only.** Dispatch only the selected agents. Each receives `synthesis-1.md` only — never another agent's raw Round 1 notes — and may answer only: agree, disagree, withdraw, or refine. No restatement of Round 1. Writes `reviews/round-2/<role>.md`.

5. **Hard stop.** Maximum 2 rounds. If a 3rd round seems warranted, do not run it — instead write a line in the synthesis stating the reason a 3rd round was needed but skipped. Write the final combined synthesis to `reviews/synthesis.md`.

## After synthesis

Material findings (anything that should change durable product memory, not just this item) go to the `council-judgement` skill to be filed as bids. Do not edit `docs/factory/brain/` directly from this skill.
