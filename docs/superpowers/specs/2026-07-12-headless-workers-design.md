# Factory Headless Workers — Design Spec

**Date:** 2026-07-12
**Status:** Design (approved architecture; pending written-spec review)
**Topic:** Out-of-process headless coding-agent workers (OpenAI Codex CLI + headless Claude) for Factory's execution stages, with a scheduler above them for parallel throughput.

---

## 1. Summary

Today Factory's `implement` station is executed by **in-process Claude subagents** dispatched from the orchestrating session (`superpowers:subagent-driven-development` + `agents/implementer.md`). The orchestrator's context window pays for that work: briefs, tool calls, transcripts, and iteration all accrete in the session that is also supervising the whole pipeline.

This spec adds a second way to execute the mechanical coding work: **headless worker processes** that run *outside* the orchestrator's context, own their own window, and hand back only a compact result. It ships in two layers:

- **Layer 1 — the executor.** A new deterministic engine command, `factory work <id>`, runs **one** headless coding agent (backend `claude` or `codex`) inside the item's isolated worktree and captures a normalized `result.json`. This alone buys **context economy**: the worker's transcript never enters the orchestrator.
- **Layer 2 — the scheduler.** A bounded pool that keeps **K** workers busy across **independent items**, each in its own worktree, collecting results and advancing each item through the *existing* gates. This buys **parallel throughput** — the "high-level orchestration above it."

The engine is already agent-agnostic (all Python does is gate transitions, store state, aggregate cost); the coupling to Claude subagents lives entirely in skill prose. The 2026-07-03 design spec explicitly listed "running on non-Claude agents (Codex, Gemini CLI, Cursor)" as a deliberately-unbuilt future. **This spec realizes that future.** It is additive: when no headless backend is available or enabled, every stage falls through to today's in-process path unchanged.

### Goals

1. **Context economy** — the orchestrator supervises execution without holding the worker's transcript.
2. **Parallel throughput** — multiple independent items build concurrently, bounded by a shared rate-limit budget, not by CPU.
3. **Two backends behind one interface** — `codex exec` and `claude -p`, same task packet in, same result packet out.
4. **No regression in trust** — worker output is untrusted until it clears Factory's existing review + verify + green-tests gates.
5. **Portability preserved** — the feature is a probe-and-upgrade capability; absence degrades to the in-process subagent path.

### Non-goals (this spec)

- Real inter-item dependency metadata (Decision D1 defers this; see §6).
- Headless execution of *review*/council seats (future; see §14).
- Container/VM isolation as the default boundary (worktree is the boundary; containers are a documented escape hatch).
- Additional backends beyond Codex and Claude (Gemini, Cursor — future).

---

## 2. Locked decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| Approach | How to build it | **C — Python primitive + LLM policy** | Python owns the mechanical, testable "run one worker, capture result, measure cost"; the LLM owns which/how-many/is-it-good. Preserves Factory's Python=gatekeeper / LLM=judgment split. |
| Scope | Spec breadth | **Both layers** (executor + scheduler) | Designed together; may be *implemented* in two phases (see §13). |
| Worker type | Backends | **Headless Codex + headless Claude** | Behind one adapter interface. |
| Wins | Priorities | **Context economy + parallel throughput** | Cost/isolation are secondary benefits that come along. |
| D1 | Parallel-safety model | **Assume top-K actionable items are independent; rely on worktree isolation** | Worktrees make a wrong guess non-destructive — worst case is a merge conflict surfaced at ship, not corruption. Real dependency metadata is a later refinement. |
| D4 | Worker autonomy | **Fully autonomous within the worktree** | The isolated `factory/<id>` worktree is the blast radius; everything the worker produces is gated downstream. |

---

## 3. Ground-truth constraints (research pass, 2026-07-12)

These facts from primary vendor docs and verified issues shape the design. They are load-bearing; the spec's components exist to satisfy them.

**Result capture**
- `claude -p --output-format json` → one JSON object: `result`, `session_id`, `subtype` (success | error_max_turns | error_during_execution | error_max_budget_usd), `is_error`, `duration_ms`, `num_turns`, `total_cost_usd`, `usage` (input/output/cache tokens), `modelUsage`. Docs say branch on `subtype`, not `is_error`. Cost fields are "client-side estimates, not authoritative billing data."
- `codex exec` reserves **stdout for the final agent message only** (progress → stderr). `--json` emits JSONL events including `turn.completed.usage` (input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens); `-o/--output-last-message <file>` writes the final message; `--output-schema` forces schema-conforming output; `-C/--cd <dir>` sets the working dir.
- **The worktree's git state (commits, diff, files-changed) is identical across backends.** This is the primary, backend-independent result; the CLI JSON supplies status/usage/summary only.

**Autonomy / sandbox / network**
- Codex `workspace-write` (the autonomous file-editing mode) defaults **network OFF**; unattended `npm/pip/curl` simply fail. Unattended runs need `-a never` (approval never); `--full-auto`/`on-failure` are deprecated; `--dangerously-bypass-approvals-and-sandbox`/`--yolo` are scoped to "inside a container." Enabling network is a documented prompt-injection risk. macOS Seatbelt has a bug that silently ignores `network_access=true`.
- Claude Code has no OS sandbox; `--dangerously-skip-permissions` shows a **one-time TTY accept dialog that parks headless runs**. Truly non-interactive autonomy needs a permission mode plus a pre-accepted trust state (`~/.claude.json`: `hasCompletedOnboarding: true`, `projects["<worktree path>"].hasTrustDialogAccepted: true`). `--bare` skips config discovery (reproducible) but also skips OAuth/keychain → API-key auth required.

**Auth (headless/fleet)**
- Both vendors: **API keys are the recommended default for automation.** Subscription/OAuth tokens race under parallelism ("refresh token already used" 401s when a fleet shares `~/.codex`) and expire mid-run in `claude -p` with no headless refresh.

**Concurrency / shared state**
- Rate limits are enforced at the **organization level** (shared RPM/ITPM/OTPM token bucket) — N parallel workers drain **one** bucket. Separate "acceleration limits" return 429 on sharp usage ramps even below tier limits. HTTP 529 `overloaded_error` reportedly hard-fails parallel Claude subagents **without backoff**.
- `~/.claude.json` has a documented **corruption race at 5+ concurrent instances** (concurrent writes, no file locking).
- `git worktree add` refuses a branch already checked out elsewhere → **per-worker branches are mandatory** (Factory already uses `factory/<id>`).
- Worktrees carry **neither gitignored files** (`.env` — needs a `.worktreeinclude` copy) **nor installed deps** (node_modules/venv are per-checkout). Cleanup: `git worktree remove` refuses unclean trees without `--force`; deleting a worktree dir without `remove` leaves stale admin entries until `git worktree prune`; a crashed run can leave a locked worktree.

---

## 4. Architecture

```
                 ┌───────────────────────────────────────────────────┐
                 │  Orchestrator (Claude Code session) — LLM policy   │
                 │  factory-dispatch / factory-autopilot              │
                 │  decides: which items, how many, is-it-good        │
                 └───────────────┬───────────────────────────────────┘
                                 │  (Layer 2: scheduler — §8)
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
   ┌────▼─────┐            ┌─────▼────┐             ┌─────▼────┐
   │ slot 1   │            │ slot 2   │             │ slot K   │   ← bounded pool
   │ item A   │            │ item B   │             │ item C   │
   └────┬─────┘            └─────┬────┘             └─────┬────┘
        │ factory work A         │ factory work B         │ factory work C   (Layer 1: executor — §5)
   ┌────▼──────────────┐    ┌────▼──────────────┐    ┌────▼──────────────┐
   │ worktree factory/A│    │ worktree factory/B│    │ worktree factory/C│
   │  ├ prep (deps)    │    │  ├ prep (deps)    │    │  ├ prep (deps)    │
   │  ├ headless worker│    │  ├ headless worker│    │  ├ headless worker│  ← codex exec / claude -p
   │  └ result.json    │    │  └ result.json    │    │  └ result.json    │
   └───────────────────┘    └───────────────────┘    └───────────────────┘
```

Each worker's transcript stays inside its own process. The orchestrator only ever reads `result.json` (a few hundred tokens) and the item's git branch — never the worker's window.

**Data flow for one item (happy path):**
1. Scheduler selects an actionable item, creates worktree `factory/<id>`, runs prep (copy `.worktreeinclude` files, install deps — network on, no model).
2. Scheduler launches `factory work <id> --backend <b> --model <m>` as a background process.
3. `factory work` builds the task brief from `plan.md` + `spec.md`, spawns the headless worker in the worktree (network off by default), waits.
4. Worker edits code, runs tests, commits to `factory/<id>`.
5. `factory work` reads git (commits/diff/files) + parses the worker's JSON (status/usage/summary) → writes `items/<id>/worker/result.json`; on success logs a **measured** `spend` event and `implement.completed`; returns a one-line status.
6. Scheduler ingests `result.json`, advances the item to `review` (or marks it blocked), frees the slot, pulls the next item.
7. Downstream (`review` → `verify` → `ship`) is unchanged — worker output is gated exactly like subagent output.

---

## 5. Component: `factory work` (Layer 1 executor)

New engine subcommand, registered in `scripts/factory/factory.py` alongside the existing `cmd_*` handlers, implemented in a new `scripts/factory/lib/work.py`.

**Signature**
```
factory work <id> --backend claude|codex [--model <m>] [--timeout <s>]
                   [--network on|off] [--worktree <path>] [--dry-run]
```
Flags default from `.factory/config.json` `workers` block (§11) when omitted; explicit flags win.

**Execution granularity.** By default one `factory work` run executes the item's *entire* remaining plan (all unticked `plan.md` tasks) in a single worker process — this maximizes context economy and minimizes orchestrator round-trips. The tradeoff: the in-process path's *per-task* review (an LLM reviewer between each task) is not present inside a single worker pass; on the headless path it is subsumed by the worker's own iterate-and-test loop plus Factory's existing **whole-branch `review` stage + green-suite gate** (§9). A `--task <n>` mode (one worker per plan task, with Factory's per-task reviewer between) is a documented alternative that preserves per-task review at the cost of N round-trips per item. **Whole-plan is the recommended default;** `--task` is the escape hatch when an item is risky enough to want review between tasks.

**Preconditions (checked, fail fast if unmet):**
- Item exists and is at stage `implement` (or a rework re-entry — see `factory-implement` Rework entry).
- Worktree/branch `factory/<id>` exists (the scheduler or the implement skill creates it; `factory work` does **not** create it — separation of concerns). The worktree's filesystem path is taken from `--worktree` if given, else resolved by matching branch `factory/<id>` in `git worktree list --porcelain`; if the branch exists only as a plain checkout (no separate worktree), the repo root is used.
- `plan.md` has at least one unticked `- [ ]` task.
- The selected backend CLI is on `PATH` and auth is configured (see §11 auth).

**Steps:**
1. **Build the task brief.** Render the same material `agents/implementer.md` receives today into a single prompt string: the unticked `plan.md` task(s), the `spec.md` acceptance criteria those tasks touch, the worktree path, and the standing contract (TDD, run the named test commands, commit as you go, do not touch files outside the worktree). The brief is written to `items/<id>/worker/brief.md` for auditability.
2. **Spawn the headless worker** in the worktree (`cwd = worktree`) via the backend adapter (§6), with the resolved autonomy/network posture (§7). Capture stdout (and stderr to `items/<id>/worker/worker.log`). Enforce `--timeout`.
3. **Capture the result — git first.** After the worker exits, read the worktree's git state: new commits on `factory/<id>` since the branch point, `git diff --name-status`, and whether the working tree is clean. This is backend-independent.
4. **Parse the backend JSON** for status (`subtype`/`turn.failed`), usage (tokens), and a short summary (final agent message, truncated).
5. **Normalize** into `items/<id>/worker/result.json` (schema below).
6. **On success** (worker exited clean, ≥1 commit, tests reported green): tick every `- [ ]` plan task the worker completed to `- [x]` in `plan.md` and commit that edit (the branch is green and headed to review) — leaving the same end state as the in-process path. Then log a **measured** `spend` event (`provenance: "measured"`, tokens from the worker JSON, `source: "factory-work"`, `backend`, `model`) and `implement.completed` with the real task count + test summary. Leave the branch/commits in place. **Do not** call `advance` — the caller (scheduler or dispatch skill) owns the transition, consistent with the current implement contract.
7. **On failure** (non-zero exit, timeout, no commits, red tests, or an `error_*` subtype): log `implement.failed` with a typed `reason` (`crash|timeout|no_changes|red_tests|rate_limited|auth|blocked`), leave the branch intact for inspection, and return a non-zero exit with that reason on stdout as a one-line status.

**`result.json` schema** (`schemas/result.json`, backend-independent):
```json
{
  "id": "0012-dark-mode",
  "status": "done | blocked | failed",
  "reason": null,
  "backend": "claude | codex",
  "model": "<model id>",
  "branch": "factory/0012-dark-mode",
  "commits": ["<sha>", "..."],
  "files_changed": [{ "path": "src/theme.ts", "change": "A | M | D" }],
  "test": { "command": "npm test", "passed": true, "summary": "142 passed" },
  "usage": { "input": 0, "output": 0, "total": 0, "provenance": "measured | proxy" },
  "cost_usd_estimate": 0.0,
  "duration_s": 0,
  "summary": "<truncated final agent message>",
  "worker_log": "items/0012-dark-mode/worker/worker.log"
}
```
- `status` is `done` only when the worker exited clean, made ≥1 commit, and reported green tests. Otherwise `failed` (or `blocked` for a worker that self-reported it cannot proceed), with `reason` one of `crash|timeout|no_changes|red_tests|rate_limited|auth|blocked|prep_failed`.
- `commits`/`files_changed`/`test` are read from the worktree git state (backend-independent); `usage`/`cost_usd_estimate`/`summary`/`duration_s` come from the backend JSON.
- `cost_usd_estimate` is the CLI's client-side estimate — recorded for visibility, not treated as authoritative billing.

**Exit codes:** `0` success; `1` worker failed (reason in result.json + stdout); `2` precondition/usage error (bad stage, missing worktree, backend unavailable); `3` retryable (rate-limited/overloaded — the scheduler backs off).

**Cost provenance:** if the backend exposes no usage (should not happen for either supported CLI, but a defensive path), log the `spend` event with `provenance: "proxy"` and no `tokens` key — never invent numbers (matches the existing convention in `factory-implement` §Spend logging).

---

## 6. Component: backend adapter

One interface, two implementations, plus a normalizer. Lives in `scripts/factory/lib/work.py` (or a `lib/backends/` package if it grows).

**Interface** (conceptual):
```
run(brief: str, worktree: Path, model: str|None, timeout: int,
    network: bool, config_dir: Path, env: dict) -> RawRun
# RawRun = {exit_code, stdout, stderr, session_id?, raw_events?}
normalize(raw: RawRun, git_after: GitState) -> ResultPacket
```

**claude backend** — approximately:
```
CLAUDE_CONFIG_DIR=<per-worker dir>  ANTHROPIC_API_KEY=<key> \
claude -p "<brief>" \
  --output-format json \
  --permission-mode <autonomous mode> \
  --add-dir <worktree> \
  [--model <m>] [--max-turns N] [--max-budget-usd X]
```
- Auth via `ANTHROPIC_API_KEY` (§11). Per-worker `CLAUDE_CONFIG_DIR` avoids the `~/.claude.json` corruption race; the config dir is pre-seeded with `hasCompletedOnboarding: true` and `hasTrustDialogAccepted: true` for the worktree path so no TTY trust dialog parks the run.
- Parse the single JSON object; branch on `subtype`. Tokens from `usage`; cost from `total_cost_usd` (recorded but tagged client-side estimate).

**codex backend** — approximately:
```
CODEX_HOME=<per-worker dir>  OPENAI_API_KEY=<key> \
codex exec "<brief>" \
  --json \
  -C <worktree> \
  -a never \
  --sandbox <workspace-write | danger-full-access> \
  [-m <model>] [--output-last-message <file>]
```
- Auth via `OPENAI_API_KEY` (§11). Per-worker `CODEX_HOME` isolates `auth.json`/sessions and (with API-key auth) sidesteps the single-use-refresh-token fleet race.
- `--sandbox workspace-write` for network-off (default); `danger-full-access` only when network is required (§7), with the macOS Seatbelt caveat documented.
- Parse `--json` JSONL: sum `turn.completed.usage` for tokens; final `agent_message` (or `--output-last-message` file) for the summary; `turn.failed`/`error` for failure.

**Normalizer** maps either RawRun + the post-run git state to the single `ResultPacket` schema, so everything downstream is backend-blind.

---

## 7. Component: worktree prep + autonomy/network posture

This resolves the D4 tension (fully-autonomous-in-worktree vs. workers needing network to install deps).

**Two distinct phases per worktree:**
1. **Prep (deterministic, network ON, no model).** Run by the scheduler before the worker starts: copy gitignored files listed in `.worktreeinclude` (vendor convention) into the worktree, then run the configured `workers.prep` command (e.g. `npm ci`, `pip install -e .`). Network is fine here — it's a fixed command, not model-driven. Prep failure → the item is marked blocked with reason `prep_failed` and never dispatched to a worker.
2. **Worker (model-driven, network OFF by default).** With deps already present, the worker can build and run tests offline. Its blast radius is the worktree; it has no network, so prompt-injection-to-exfiltrate and dependency-confusion pulls are off the table by default.

**Network posture:**
- **Default: worker network OFF.** Codex: `--sandbox workspace-write`. Claude: best-effort via an `allowedTools` allowlist that excludes network tools (documented asymmetry — Claude has no OS sandbox, so Claude's network-off is not OS-enforced; a container is the escape hatch for hard isolation).
- **Per-item override `network: true`** for tasks whose *tests* need runtime network (integration tests hitting a service). Codex: `--sandbox danger-full-access` (macOS: recommend running under a container because Seatbelt ignores `network_access=true`). This override is a conscious per-item choice, logged.

**Known asymmetry to state plainly:** Codex enforces the sandbox at the OS level; Claude does not. For workloads that require *hard* network/file isolation on the worker, the honest boundary is a container (future escape hatch, §14), not the process sandbox. For the default posture (worktree blast radius, deps pre-installed, gated downstream), the process-level boundary is acceptable and matches D4.

---

## 8. Component: the scheduler (Layer 2)

The "high-level orchestration above it." It is driven from skill prose (`factory-dispatch` / a new `factory-workers` skill), using the engine primitives — **not** a long-running Python daemon (that would be Approach B). Python gains only the selection helper and the per-worker mechanics; the loop/policy stays in the orchestrating session.

**Responsibilities:**
1. **Select up to K actionable items.** Extend work selection (`lib/dispatch.py`) with `next_items(n)` returning the top-N actionable items by priority (D1: assumed independent). Existing `next_item` stays as `next_items(1)`.
2. **Provision each item:** create worktree `factory/<id>`, run prep (§7), assign an isolated per-worker config/home dir.
3. **Launch** `factory work <id>` per item as a background process (or a `Workflow` stage where the Workflow tool is present — capabilities upgrade; parallel background processes are the degraded default).
4. **Pace the pool** to respect the shared org rate-limit bucket:
   - **Stagger launches** (ramp, don't burst — acceleration-limit 429s fire on sharp ramps).
   - **Small default K** (2–3; §11) — well under the `~/.claude.json` 5+ corruption threshold and tier limits.
   - **Backoff + retry** on exit code 3 (rate-limited/overloaded): exponential backoff, capped retries (config), because Claude Code itself does not back off 529s under parallel load.
5. **Collect + advance.** As each `result.json` lands: on success advance the item to `review`; on failure apply the dispatcher's existing two-strikes-then-blocked rule. Free the slot, pull the next item.
6. **Clean up** finished worktrees per §12.

**Isolation invariant:** one branch ↔ one worktree ↔ one worker ↔ one isolated config dir. No two workers share a branch, a working tree, or a config/auth dir.

---

## 9. Trust & gates (unchanged)

Headless execution changes *who types the code*, not *what is allowed to advance*.

- The `implement → review` gate still mechanically checks the branch ref `refs/heads/factory/<id>` **and** the `implement.completed` event (`machine.py:_gate_review`). `factory work` satisfies both exactly as the in-process path does.
- **Review stays an LLM subagent — judgment is never delegated to the executor.** On the in-process path that is per-task *and* whole-branch review. On the headless whole-plan path (§5 granularity), per-task review is subsumed by the worker's own iterate-and-test loop; Factory's **whole-branch `review` stage** (council + adversarial walk) and the green-suite gate remain the authoritative check. A worker (Codex- or Claude-written) diff is reviewed identically to a subagent-written one. Items wanting per-task review use `factory work --task <n>` (§5).
- `verify`, green-suite, and `ship` gates are untouched.
- The review-rejection loop (`MAX_REVIEW_REJECTIONS`) is unchanged; rework re-enters via the existing `factory-implement` Rework path (which can itself run headlessly).

**Consequence:** a low-quality or subtly-wrong worker output is caught by the same net that catches a low-quality subagent output. The feature cannot lower the trust bar because it does not touch the gates.

---

## 10. Cost

Net improvement over today, where the orchestrator's own execution is `UNMEASURED`.

- `factory work` logs a **measured** `spend` event per worker run, tokens taken from the worker's own JSON usage (Claude `usage`; Codex summed `turn.completed.usage`), tagged `provenance: "measured"`, `source: "factory-work"`, plus `backend`/`model`. `lib/cost.py` already sums measured `spend` events — no aggregation change needed, only a new well-formed source.
- Client-side cost estimates (`total_cost_usd`) are recorded in `result.json` for visibility but not treated as authoritative billing (per vendor caveat).
- The orchestrator's own supervising burn remains `UNMEASURED` (honest — it's the main loop). The *execution* burn moves from unmeasured to measured. This is a headline benefit worth stating in `README`/docs when shipped.

---

## 11. Config

Add a `workers` block to `.factory/config.json`, validated by an extended `schemas/config.json`. Defaults chosen for safety and portability.

```json
{
  "workers": {
    "enabled": false,
    "backend": "claude",
    "max_parallel": 2,
    "timeout_seconds": 1800,
    "network": "off",
    "prep": null,
    "retry": { "max_attempts": 3, "base_delay_seconds": 20 },
    "models": { "claude": null, "codex": null },
    "codex": { "sandbox": "workspace-write" }
  }
}
```

- **`enabled`** — master switch; **off by default** (opt-in). Off → in-process subagent path (§12 probe).
- **`backend`** — default backend (`claude`); Codex is opt-in per config or per-item override.
- **`max_parallel`** — K; default **2** (small, under the 5+ `.claude.json` race threshold and shared-bucket limits). Raising it is a conscious choice with rate-limit implications.
- **`network`** — default worker network posture (`off`); per-item override allowed.
- **`prep`** — worktree prep command (string/array), run network-on before the worker; `null` = skip.
- **`models`** — explicit model per backend; **never inherited** (matches `model-tiering.md`: "always choose the tier explicitly").
- **`retry`** — backoff policy for rate-limit/overload.

**Auth (not stored in config — environment only):**
- `ANTHROPIC_API_KEY` for the claude backend; `OPENAI_API_KEY` for codex. **API-key auth is required for fleet/unattended mode** (subscription/OAuth tokens race and expire mid-run). `factory doctor` reports whether each configured backend's CLI is present and whether its key env var is set (without printing the key).
- Per-worker isolated config dirs (`CLAUDE_CONFIG_DIR` / `CODEX_HOME`) are created by the scheduler, seeded with pre-accepted trust/onboarding for the worktree path.

---

## 12. Capability probe (portability)

Add one row to the `capabilities` skill's probe-and-upgrade table:

| Capability | Probe | With it | Without it |
|---|---|---|---|
| Headless worker | `workers.enabled` true in `config.json` **and** the configured backend CLI resolvable on `PATH` with its key env var set | `factory-implement` dispatches the item's execution via `factory work` (out-of-process); `factory-dispatch` may run the Layer-2 pool | Today's in-process `superpowers:subagent-driven-development` path, unchanged |

This keeps the "degraded baseline works on any Claude model" contract: the headless path is an opportunistic upgrade, never a requirement. `factory-implement` gains a single branch at step 3 — "if the headless-worker capability is present, execute via `factory work <id>`; otherwise the current in-process subagent path" — everything else in the skill (contract, rework entry, completion, spend logging) is unchanged because `factory work` produces the same artifacts and events.

---

## 13. Affected surfaces & phasing

**Engine (Python):**
- `scripts/factory/factory.py` — register `work` subcommand.
- `scripts/factory/lib/work.py` (new) — `factory work`, backend adapter, normalizer.
- `scripts/factory/lib/dispatch.py` — add `next_items(n)`.
- `scripts/factory/lib/doctor.py` — report headless-worker readiness (CLIs present, keys set, `workers` config).
- `schemas/config.json` — `workers` block; `schemas/result.json` (new) — `result.json` shape.
- `scripts/factory/lib/cost.py` — no change (new `spend` source is already handled); add a test that a `factory-work` measured event rolls up.

**Skills (prose):**
- `capabilities/SKILL.md` — new probe row (§12); a new `references/headless-workers.md` documenting flags/auth/gotchas.
- `factory-implement/SKILL.md` — one branch at step 3 for the headless path.
- `factory-dispatch/SKILL.md` (and/or a new `factory-workers` skill) — the Layer-2 pool loop, pacing, backoff, cleanup.
- `factory-autopilot/SKILL.md` — allow the bounded loop to use the pool within its budget checkpoints.

**Phasing (implementation, even though one spec):** Phase A = Layer 1 (`factory work` + adapter + config + probe + `factory-implement` branch) delivers context economy and measured cost on its own. Phase B = Layer 2 (scheduler: `next_items`, pool, pacing, cleanup) delivers parallel throughput on top. The writing-plans step may split these into two plans.

---

## 14. Failure modes & edge cases

| Situation | Handling |
|---|---|
| Worker crash / non-zero exit | `implement.failed` reason `crash`; branch left intact; slot freed; dispatcher two-strikes rule. |
| Timeout | Kill process tree; `implement.failed` reason `timeout`; branch left for inspection. |
| Worker made no commits | `implement.failed` reason `no_changes` (distinguish "did nothing" from "did work"). |
| Red tests | `implement.failed` reason `red_tests` — never log `implement.completed` on a red suite (existing invariant). |
| Rate-limited / 529 overloaded | Exit code 3; scheduler backs off (exponential, capped) and retries; if exhausted, item marked blocked `rate_limited`. |
| Auth failure (missing/expired key) | Exit code 1 reason `auth`; `factory doctor` guidance surfaced; do not silently fall back mid-run. |
| Prep failure (deps won't install) | Item blocked `prep_failed`; never dispatched to a worker (a worker can't fix a broken prep offline). |
| Locked/unclean worktree from a crashed prior run | Scheduler detects, attempts `git worktree remove --force` + `prune`; if it can't, blocks the item with a clear pointer rather than reusing a dirty tree. |
| Wrong independence guess (D1) → merge conflict at ship | Surfaced at `ship` exactly as any conflict is today; non-destructive (worktrees isolated the work). Motivates future dependency metadata. |
| Backend CLI absent though `enabled` | Probe fails → in-process path (no crash). |
| Two items with a hidden dependency co-run | Both build in isolation on separate branches; per-item review can't see across branches, so the backstop is **ship** — a merge conflict, or ship's post-merge test suite (which must be green before the branch is deleted) catches an integration break. Non-destructive; worktrees kept the work isolated. |

---

## 15. Security considerations

- **Autonomous code execution.** Workers run model-authored commands unattended. Mitigations: worktree blast radius (D4), network-off by default (§7), everything gated downstream (§9), and per-worker isolated config/auth dirs.
- **API key handling.** Keys are environment-only, never written to `config.json`, `result.json`, logs, or the brief. `factory doctor` reports presence without printing values. Per-worker config dirs avoid leaking one worker's auth into another.
- **Prompt injection.** Network-off default means an injected instruction has no exfiltration channel and cannot pull untrusted deps. `network: true` is a conscious per-item opt-in that widens this; documented as such.
- **Shared-state corruption.** Per-worker `CLAUDE_CONFIG_DIR`/`CODEX_HOME` + API-key auth avoid the `~/.claude.json` corruption race and the Codex single-use-refresh-token fleet race.

---

## 16. Testing strategy

- **Stub backend.** A `backend=stub` (test-only) writes a canned `result.json` and makes a canned commit in the worktree — no real CLI, no network, deterministic. The bulk of the suite runs against it: `factory work` preconditions, git-first capture, normalizer, event logging (`implement.completed`/`implement.failed`, measured `spend`), exit codes.
- **Scheduler unit tests.** `next_items(n)` selection/ordering; slot management; backoff on exit-code-3; cleanup of finished/locked worktrees — all against the stub.
- **Cost rollup test.** A `factory-work` measured `spend` event sums correctly in `lib/cost.py`.
- **Config schema tests.** `workers` block validates; bad values rejected (matching existing config-validation tests).
- **Coherence guard.** Extend `tests/test_plugin_coherence.py` so the new capability row, the `factory-implement` branch, and the `factory work` command/skill references don't drift.
- **Integration smoke (manual, documented, not CI).** Real `claude -p` and `codex exec` against a fixture repo, one item each, verifying a real worktree run produces a green branch + measured cost. Gated behind env keys; never in the default suite (no network/keys in CI).

---

## 17. Open questions (resolve during planning)

1. **Claude autonomous permission mode** — exact flag combination for "edit + run tests, no prompts, no parked TTY dialog." Primary approach: a non-interactive permission mode (e.g. `--permission-mode` set to the auto-approving mode) **plus** a per-worker `CLAUDE_CONFIG_DIR` pre-seeded with `hasCompletedOnboarding: true` and the worktree path's `hasTrustDialogAccepted: true` — deliberately *not* `--dangerously-skip-permissions` (its one-time TTY accept dialog parks headless runs). Confirm the exact mode name against the installed CLI in Phase A; the `allowedTools` allowlist is the fallback if a blanket auto-approve mode is unavailable.
2. **Where the Layer-2 loop lives** — extend `factory-dispatch` vs. a dedicated `factory-workers` skill. Lean: dedicated skill, cited by dispatch/autopilot, to keep each skill focused.
3. **Prep command discovery** — explicit `workers.prep` only (chosen default), or optional auto-detect (`package.json` → `npm ci`)? Lean explicit-only for v1 (predictable), auto-detect later.

---

## 18. Future work (out of scope)

- Real inter-item dependency metadata so the scheduler never co-runs dependent items (upgrades D1 from "assume" to "know").
- Headless execution of read-only stages (review/council seats) — the reviewer seam is structurally identical (fresh context, returns a verdict).
- Container/VM isolation as an opt-in hard boundary (OS-enforced network/file isolation for both backends, resolving the §7 Claude asymmetry).
- Additional backends (Gemini CLI, Cursor) behind the same adapter.
- Dev-server port allocation across worktrees (a `$PORT`/range convention) if workers ever need to run servers, not just test suites.
```
