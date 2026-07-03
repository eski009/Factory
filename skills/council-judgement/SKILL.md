---
name: council-judgement
description: Use when council findings need to become durable product memory - files bids and records orchestrator judgements through the ledger firewall
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

Memory firewall (spec §6, ported from `pblib.py`): specialists never edit `docs/factory/brain/` directly. Every durable claim passes through a schema-validated bid, then exactly one orchestrator judgement, before any brain surface changes.

## Filing bids

For each material finding from a council synthesis, file one bid:

```
factory bid ROLE TOPIC "CLAIM" --evidence PATH --surface brain/<file>.md --severity low|medium|high
```

- `ROLE` is one of the six council roles: `product`, `ui-taste`, `architecture`, `engineering-quality`, `customer`, `commercial`.
- `--evidence` may repeat; every value must be a real path or URL already cited in the round notes — never invent evidence to satisfy the CLI.
- A claim with no real evidence still gets filed, but targets `--surface brain/open-questions.md` rather than a fabricated citation. For a claim marked UNSOURCED in the round notes, pass the round-note file that raised it as the evidence pointer (provenance of the claim, not proof of its truth), e.g. `--evidence .factory/items/<id>/reviews/round-1/<role>.md`.
- `factory bid` exits 2 on business-rule violations (unknown agent, bad severity, schema violations); omitting a required flag like `--evidence` is a usage error (exit 1). The ledger is untouched on refusal.

## Recording judgements

The orchestrator (the main session, never a specialist subagent) judges each bid:

```
factory judge BID_ID DECISION --reason "..." [--surface brain/<file>.md --anchor "<heading>"]
```

- `DECISION` is one of: `accept`, `reject`, `defer`, `merge`, `downgrade`.
- `accept` and `merge` require both `--surface` and `--anchor` naming exactly where the edit goes — the CLI refuses (exit 2) otherwise.
- A bid can be judged exactly once; judgements are final.
- Never judge your own just-filed bid without re-reading the original evidence first. Rubber-stamping defeats the firewall.

## After judgement

Only an `accept` or `merge` judgement authorizes editing the brain — and only the surface and anchor named in that judgement, nowhere else. Edit before judgement, or edit a different surface/anchor than the one named, and the change has no authorization behind it: don't do it.

After making the authorized edit, add a line to `docs/factory/brain/decisions.md` recording what changed and citing the judgement id.

`defer` and `downgrade`/`reject` authorize no edit at all — the claim stays in the ledger as history, unmerged.

## Reputation deltas (derived, never hand-edit `ledgers/reputation.jsonl`)

| Decision | Delta |
|---|---|
| accept | +0.05 |
| merge | +0.05 |
| defer | 0.0 |
| downgrade | −0.05 |
| reject | −0.10 |

`factory judge` computes and appends the reputation event automatically. `factory reputation --json` reads the derived table.
