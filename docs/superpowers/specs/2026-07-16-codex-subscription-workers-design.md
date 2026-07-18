# Codex subscription workers — parallel ChatGPT-plan auth

- **Date:** 2026-07-16
- **Status:** Approved design (option "Both" chosen: subscription mode lands as opt-in
  alongside the API-key default)
- **Topic:** Let the headless-worker pool run multiple parallel `codex` workers
  authenticated by the user's ChatGPT subscription login, without the OAuth
  refresh-token race, without the engine ever performing OAuth, and without touching
  the user's real login.

## Problem

Factory's worker pool supports parallel Codex today only via `OPENAI_API_KEY`. The
pool deliberately seeds each worker an **empty** isolated `CODEX_HOME`
(`pool.seed_config_dir`) to avoid the "Codex single-use-refresh-token fleet race":
ChatGPT-plan auth (`codex login`) stores a rotating refresh token in
`$CODEX_HOME/auth.json`; N parallel workers sharing it race the refresh — one wins,
the rest (and the user's interactive login) hold dead tokens. So subscription users
cannot run workers at all, let alone in parallel.

## Decisions

1. **Access-token-only fan-out — no refresh leader, no parallel cap.** In
   subscription mode the engine copies the user's `auth.json` into each worker home
   **with the refresh token stripped**. Workers cannot refresh, so no rotation race
   exists at any parallelism; the user's real `~/.codex` is never written. The
   engine never performs OAuth.
2. **TTL fail-closed at provision.** The access token is a JWT; the engine decodes
   its `exp` claim (stdlib base64, no signature verification — it is a freshness
   read, not an auth check) and refuses to provision unless
   `exp - now > timeout_seconds + 300`. The refusal message is actionable: run
   `codex` interactively to refresh the login, then retry. Undecodable/missing
   token → same refusal path.
3. **Mid-run expiry is an honest auth fault.** A worker whose token expires mid-run
   fails with reason `auth` → exit 1 → the existing pool-stop + packet behavior.
   Never silently degraded.
4. **Opt-in config:** `workers.codex.auth: "key" | "chatgpt"`, default `"key"` —
   today's behavior is byte-identical unless the user opts in.
5. **Billing is unambiguous per mode.** In `chatgpt` mode the engine removes
   `OPENAI_API_KEY` from the codex worker's environment (env keys outrank
   `auth.json` in the codex CLI); in `key` mode nothing changes.
6. **Plan rate limits are the pool's existing problem.** All workers share the
   subscription's bucket; the pool's staggered launch + capped-exponential backoff
   (built for exactly this shape) applies unchanged.
7. **Direct `factory work` without provision is documented, not blocked.** Without a
   seeded home the process uses the real `~/.codex` exactly like interactive codex —
   fine for one process, and the pool path always provisions.

## Architecture

- `pool.seed_config_dir` (codex branch): read the configured auth mode from
  `work.worker_config(repo)`. `key` → today's empty home. `chatgpt` → locate the
  real Codex home (`$CODEX_HOME` or `~/.codex`), parse `auth.json`, build a stripped
  copy (access token + everything EXCEPT any refresh-token field), TTL-check per
  Decision 2, write it into the worker home. Failures raise the provision-failure
  path (`prepared: false` + detail) — `factory-workers` already skips-and-packets on
  that.
- JWT freshness helper in `pool.py`: `_jwt_exp(token) -> int | None` (split on `.`,
  base64url-decode payload with padding, `json.loads`, `exp` key; `None` on any
  malformed input → fail closed).
- `work.py`: extract the worker-env construction into `_worker_env(cfg, backend)`;
  in `chatgpt` mode for codex it pops `OPENAI_API_KEY`.
- `doctor.worker_readiness`: adds `codex_auth` (configured mode) and `codex_login`
  (real-home `auth.json` present with decodable, unexpired token — reported as
  remaining seconds, 0 when absent/expired) alongside the existing `openai_key`.
- `schemas/config.schema.json`: `workers.codex` gains
  `"auth": {"enum": ["key", "chatgpt"]}`.
- Prose: `skills/capabilities/references/headless-workers.md` gains an Auth section
  (both modes, TTL bound, expiry = pool-stop, shared plan limits, the
  direct-`factory work` caveat); the capabilities Headless-worker probe row and
  `skills/factory-workers/SKILL.md` mention the mode; docs sweep (CHANGELOG 0.8.0,
  version bump).

## Edge cases

- **No `auth.json` / no login** in chatgpt mode → provision refuses with the
  log-in-first message; doctor shows `codex_login: 0`.
- **Token fresher than margin but shorter than a long timeout** — the TTL check uses
  the *effective* per-run `timeout_seconds`, so long-timeout repos are told to
  re-login rather than launched into a guaranteed mid-run auth stop.
- **auth.json shape drift across codex versions** — the engine copies unknown fields
  through verbatim and strips only known refresh-token keys (`refresh_token`, and
  nested `tokens.refresh_token`); TTL check tolerates either flat or nested access
  tokens. Undecodable → fail closed.
- **`key` mode with no key / `chatgpt` mode with a key set** — doctor reports both
  facts; provision in chatgpt mode never requires the env key; the env pop keeps a
  stray key from silently flipping billing.

## Non-goals

- No OAuth/refresh implementation in the engine, ever.
- No write-back to the user's `~/.codex`.
- No change to the claude backend's auth.
- No per-item auth mode (config-level only, like `backend`).
