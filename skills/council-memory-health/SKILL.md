---
name: council-memory-health
description: Use when a factory loop run ends or /factory:status is invoked - checks memory health and recommends pruning
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

## What this checks

`factory health` recomputes memory health deterministically from the current
council files and ledgers — role file line counts, duplicate claim lines,
and the count of unjudged bids — and writes the result to
`.factory/memory-health.json`. It never mutates council files itself.

## Steps

1. Run `factory health`. It prints a `recommendation` (`ok` or `prune`)
   followed by the `reasons` that produced it.
2. Report the reasons verbatim to the user — don't paraphrase or summarize
   away specific numbers (they're the evidence for the recommendation).
3. If the recommendation is `prune`: invoke the `council-pruning` skill,
   handing it this run's `reasons` list so it knows which roles to target.
4. If the recommendation is `ok`: stop here. Say so and don't invoke pruning.

## Never

Never invoke `council-pruning` — or run `factory prune` yourself — without a
`prune` recommendation from `factory health` in hand. The recommendation is
the gate; don't prune speculatively because a role file "looks big," and
don't skip the health check because a previous run already recommended
pruning (memory changes between runs; re-check every time this skill fires).
