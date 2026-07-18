# Headless workers (`factory work`)

`factory work <id>` runs one headless coding-agent worker in an item's
`factory/<id>` worktree and captures a normalized `items/<id>/worker/result.json`.
It is the out-of-process executor: the worker owns its own context, and the
orchestrator only ever reads the result packet.

## Command

```
factory work <id> [--backend claude|codex|stub] [--model M]
                  [--timeout S] [--network on|off] [--worktree PATH] [--json]
```

Exit codes: `0` succeeded (result `done`, `implement.completed` logged);
`1` usage/internal — includes `reason: auth` (a bad/expired key or, in
`chatgpt` mode, an expired login); `2` precondition refusal (not at
`implement`, or no unticked plan tasks); `3` worker attempted but failed —
read `result.json`'s typed `reason`:
`crash|timeout|no_changes|red_tests|rate_limited|blocked`. `prep_failed` is a
`factory provision` outcome, not a `factory work` one — see Scheduler below.

## Config (`.factory/config.json` → `workers`)

Off by default. Keys: `enabled`, `backend` (default `claude`), `max_parallel`
(default 2), `timeout_seconds`, `network` (default `off`), `prep`,
`test_command`, `models.{claude,codex}`, `codex.sandbox`, `retry`.

## Auth

Two modes per repo, `workers.codex.auth` in `.factory/config.json`:

- **`"key"` (default):** `OPENAI_API_KEY` in the environment; stateless, safe at
  any parallelism. `ANTHROPIC_API_KEY` for the claude backend, unchanged.
- **`"chatgpt"`:** workers run on the ChatGPT-subscription login. `factory
  provision` copies `~/.codex/auth.json` into each worker's isolated
  `CODEX_HOME` **with the refresh token stripped** — workers cannot rotate the
  token, so parallel runs cannot race the login, and the engine never writes
  the real `~/.codex`. Provision fail-closes unless the access token outlives
  `timeout_seconds` + margin (the message says to run `codex` interactively
  and retry); mid-run expiry is classified `auth` → exit 1 → pool-stop when
  codex reports it recognizably (401/403, "token expired", "not logged in");
  an unrecognized failure shape surfaces as `crash` and burns the two-strikes
  retry instead — either way the run fails loudly, never a silent pass. All
  workers share the plan rate limits — the pool's staggered launch and
  backoff already pace that bucket. The engine removes `OPENAI_API_KEY` from
  chatgpt-mode worker environments so billing never silently flips to the
  API. `factory doctor
  --json` → workers reports `codex_auth` and `codex_login` (remaining token
  seconds). Running `factory work` without provisioning uses your real
  `~/.codex` like an interactive session — fine for one process; the pool
  path always provisions.

## Autonomy / network

The worker runs autonomously **inside the worktree** (Claude
`--permission-mode acceptEdits`; Codex `-a never --sandbox workspace-write`).
Network is **off** by default — install dependencies in a prep step, not in
the worker. Codex enforces its sandbox at the OS level; Claude does not
(the network-off tool allowlist is best-effort — use a container for hard
isolation). `--permission-mode` is confirmed against the installed CLI at
run time (design spec open-question 1).

## Trust

Worker output is untrusted until it clears Factory's existing review +
verify + green-tests gates (plus assure, for journey-affecting items).
`factory work` only fills the `implement`
station; nothing about the gates changes. Set `workers.test_command` so the
implement station has a real green-check: without it, a worker's plan-tick
happens with no independent test gate at this stage, and partial or broken
work is only caught later at the review/verify gates — `verify.green`
remains authoritative.

## `stub` backend

`--backend stub` is a test-only in-process backend (writes a file, commits,
returns a canned result); it never spawns a CLI. Used by the engine tests.

## Scheduler (Layer 2 / parallel pool)

The `factory-workers` skill runs a bounded pool of workers across independent
items — the "high-level orchestration above" `factory work`. It uses three
engine primitives plus `factory work`:

```
factory next -n K --json        # top-K actionable items (a JSON array)
factory provision <id> [--backend claude|codex|stub] [--json]
factory cleanup <id> [--json]
```

- **`factory provision <id>`** prepares one item's worktree (design spec §7
  prep phase): create/reuse the `factory/<id>` worktree under
  `.factory/worktrees/<id>`, copy `.worktreeinclude` files, run the
  `workers.prep` command (network on), and seed an isolated
  `CLAUDE_CONFIG_DIR`/`CODEX_HOME` with pre-accepted trust. It prints
  `{worktree, config_env, prepared, reason?}`. Set each `config_env` key in
  the environment of the `factory work` process you launch for that item.
  `prepared: false` (reason `prep_failed`) means block the item — a worker
  cannot fix a broken prep offline.
- **`factory cleanup <id>`** removes the worktree (`git worktree remove
  --force` + `prune`) and the per-worker config dir. The **branch is kept**,
  so `review`/`verify`/`assure`/`ship` still operate on `factory/<id>`.

**Isolation invariant:** one branch ↔ one worktree ↔ one worker ↔ one config
dir. `factory provision` guarantees it.

**Pacing (design spec §3, §8):** all workers drain one shared org rate-limit
bucket, so keep `max_parallel` small (default 2), stagger launches (ramp, not
burst), and back off on rate-limit/overload — `retry.base_delay_seconds ·
2^attempt`, capped, up to `retry.max_attempts`. `factory doctor --json` →
`workers` reports `max_parallel` and `retry`.

**Auth is a hard stop:** a worker exit code 1 with `reason: auth` means a
bad/expired key — stop the whole pool and surface `factory doctor`; do not
retry or burn the other slots on it.

`.factory/` must be gitignored in the target repo (the standard convention) so
the nested `.factory/worktrees/<id>` checkouts stay out of the main index.
