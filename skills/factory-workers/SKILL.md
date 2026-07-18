---
name: factory-workers
description: Use when the headless-worker capability is present and several independent items are ready to implement - runs a bounded parallel pool of out-of-process workers, one per worktree, then advances each through the existing gates
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

You are the Layer-2 scheduler: a bounded pool that keeps **K** headless workers busy across **independent** items, each in its own `factory/<id>` worktree, then advances each result through Factory's *existing* gates. You do the loop/pacing/collect-advance; the engine primitives (`factory next -n`, `factory provision`, `factory work`, `factory cleanup`) do the mechanics. You never type code and never lower a gate — worker output is untrusted until it clears `review` + `verify` + green tests exactly like a subagent's.

Only run this when the **Headless worker** capability (capabilities skill) is present: `workers.enabled` true and the backend CLI + key are ready (`factory doctor --json` → `workers`). Without it, implementation stays on factory-implement's in-process path — do not run a pool. In `chatgpt` auth mode, a provision refusal with reason `auth` (an expired/missing codex login) is a setup fault for the human (re-login, retry) — treat it like the auth pool-stop, not a per-item skip.

## Read the pool budget

`factory doctor --json` → `workers`: `max_parallel` (**K**), `backend`, and `retry` (`max_attempts`, `base_delay_seconds`). Keep K small (default 2) — every worker drains **one** shared org rate-limit bucket (design spec §3), so this is a rate budget, not a CPU budget.

## The loop

1. **Reclaim stale worktrees.** For any item already at `done` or `blocked` that still has a worktree, `factory cleanup <id>`. This also clears a locked/dirty tree from a crashed prior run before it is reused.
2. **Select.** `factory next -n K --json`. Keep only items whose `stage == "implement"` — the pool builds implementation in parallel; items at other stages flow through factory-dispatch's normal one-at-a-time path. If none are at implement, there is no pool work this pass — return to the dispatcher.
3. **Provision, staggered.** For each selected item, `factory provision <id> --backend <backend> --json`. Launch them a few seconds apart — **ramp, don't burst** (acceleration-limit 429s fire on sharp usage ramps). Read `worktree` and `config_env` from each report.
   - If `prepared` is false (`reason: prep_failed`): `factory advance <id> blocked --reason "prep failed: <detail>"` then `factory packet <id>`. A worker cannot fix a broken prep offline — never dispatch one. Do not count this against a retry budget. Unless the result's reason is `auth` (a chatgpt-mode login refusal): that is a setup fault for the whole pool — stop it per step 5's auth rule and write the packet pointing at the provision detail, not a per-item blocked.
4. **Launch a worker per prepared item, up to K concurrent.** Run `factory work <id> --backend <backend> --worktree <worktree>` as a background process, with each key from that item's `config_env` set in the process environment (`CLAUDE_CONFIG_DIR` or `CODEX_HOME`) so no two workers share a config/auth dir. Never exceed K running at once; as a slot frees, fill it from the remaining selection.
5. **Collect by exit code** as each worker finishes (read `items/<id>/worker/result.json` for the typed `reason`):
   - **0 (done):** `factory advance <id> review`. Free the slot. Leave the worktree for the downstream `review`/`verify` stages; step 1 reclaims it once the item reaches a terminal state.
   - **3 (worker failed):**
     - `reason: rate_limited` — back off `base_delay_seconds · 2^attempt` (capped ~300s) and retry, up to `max_attempts`. If still rate-limited after that, `factory advance <id> blocked --reason "rate limited"` + `factory packet <id>`.
     - any other reason (`crash|timeout|no_changes|red_tests|blocked`) — apply the dispatcher's two-strikes rule: retry once; on a second failure `factory advance <id> blocked --reason "<reason>"` + `factory packet <id>`.
   - **1 (usage/setup):**
     - `reason: auth` — a bad/expired key. **Stop the whole pool now.** Do not retry, do not launch more workers, do not block the item (it is a setup fault, not the item's). Write a packet pointing at `factory doctor`, and hand back to the dispatcher/human. One bad key fails every worker; burning K of them helps no one.
     - otherwise (unresolvable worktree, invalid result) — skip that item with a clear packet; continue the pool.
   - **2 (precondition):** the item was not at implement / had no unticked tasks — skip it (step 2 should have filtered these).
6. **Drain.** Repeat from step 2 until `factory next -n K` yields no implement-stage items, then return control to factory-dispatch (which continues advancing the now-`review`-staged items through the pipeline).

## Isolation invariant

One branch ↔ one worktree ↔ one worker ↔ one config dir. `factory provision` guarantees it; never point two workers at one worktree or one `CLAUDE_CONFIG_DIR`/`CODEX_HOME`.

## Capabilities

Where the Workflow tool is present, the pool's fan-out MAY run as Workflow stages (one worker per stage) — see the capabilities skill's `references/workflow-fanout.md`. Parallel background processes are the degraded default. Either way, K and the pacing/backoff rules above are unchanged.

## Spend

`factory work` logs a **measured** `spend` event per worker run itself — you do not log spend for the workers. Log a proxy spend event only for your own orchestration fan-out if you dispatch subagents, per factory-dispatch's Spend logging convention.
