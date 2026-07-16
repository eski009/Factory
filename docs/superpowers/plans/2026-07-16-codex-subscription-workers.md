# Codex Subscription Workers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parallel Codex workers on ChatGPT-subscription auth via access-token-only fan-out (`workers.codex.auth: "chatgpt"`), opt-in beside the unchanged API-key default.

**Architecture:** All auth handling stays in the deterministic engine (`pool.py` seeding + `work.py` env + `doctor.py` readout); the engine never performs OAuth and never writes the user's real `~/.codex`. Fail-closed TTL check at provision; mid-run expiry rides the existing `auth` → pool-stop path.

**Tech Stack:** Python 3.11 stdlib. Tests: unittest (`python3 -m unittest discover -s tests`).

**Spec:** `docs/superpowers/specs/2026-07-16-codex-subscription-workers-design.md` — read it first.

## Global Constraints

- Default `"key"` keeps today's behavior byte-identical (empty codex worker home, `OPENAI_API_KEY` untouched).
- The stripped copy removes `refresh_token` keys at every nesting level and copies every other field through verbatim; access token located at `auth["tokens"]["access_token"]` or flat `auth["access_token"]`.
- TTL rule: `exp - now > timeout_seconds + 300` using the effective per-run timeout; every failure (missing/unreadable auth.json, undecodable token, insufficient TTL) refuses provision with a message telling the user to run `codex` interactively and retry.
- JWT decode is a freshness read only — stdlib base64url + json, no signature verification, `None` on any malformed input.
- Exit codes and pool semantics unchanged; provision failures surface as the existing `prepared: false` + detail shape.
- Run the FULL suite before every commit; commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: pool seeding — chatgpt mode + config schema

**Files:**
- Modify: `scripts/factory/lib/pool.py` (helpers + codex branch of `seed_config_dir`, `provision` error wrap), `schemas/config.schema.json` (workers.codex.auth)
- Test: `tests/test_pool.py`, `tests/test_initrepo.py` (schema acceptance)

**Interfaces:**
- Produces: `pool.CodexAuthError(ValueError)`; `pool._jwt_exp(token) -> int|None`; `pool._access_token(auth) -> str|None`; `pool._strip_refresh(node)`; `pool._codex_login_home() -> Path` (`$CODEX_HOME` or `~/.codex`); `seed_config_dir` writing the stripped `auth.json` in chatgpt mode; `provision` catching `CodexAuthError` → `{"prepared": False, "detail": str(exc)}`.

- [ ] **Step 1: Write the failing tests** (in `tests/test_pool.py`, matching its fixture style — read it first). Include a module-level fake-token builder:

```python
def fake_jwt(exp):
    import base64, json as _json
    def seg(obj):
        raw = base64.urlsafe_b64encode(_json.dumps(obj).encode()).decode()
        return raw.rstrip("=")
    return f"{seg({'alg': 'none'})}.{seg({'exp': exp})}.sig"
```

Tests (adapt setUp to create a temp repo + config with `workers.codex.auth: "chatgpt"`, and point `CODEX_HOME` at a temp dir via `os.environ` with tearDown restore):

- `test_chatgpt_seed_strips_refresh_and_preserves_unknown_fields` — real-home auth.json `{"tokens": {"access_token": fake_jwt(now+7200), "refresh_token": "SECRET", "account_id": "acc"}, "custom": 1}`; after `seed_config_dir(...)` the worker-home auth.json exists, contains `account_id`/`custom`/the access token, and `"SECRET"`/`"refresh_token"` appear NOWHERE in the file text.
- `test_chatgpt_seed_accepts_flat_access_token` — `{"access_token": fake_jwt(now+7200)}` seeds fine.
- `test_chatgpt_seed_refuses_stale_token` — `fake_jwt(now+60)` (< timeout+300) raises `pool.CodexAuthError` whose message contains `codex` and `retry`.
- `test_chatgpt_seed_refuses_missing_or_undecodable` — no auth.json → CodexAuthError; auth.json with `"access_token": "garbage"` → CodexAuthError.
- `test_key_mode_home_stays_empty` — default config: worker home contains no auth.json (today's behavior).
- `test_provision_reports_auth_failure_as_prep_failure` — chatgpt mode with no login: `pool.provision(...)` returns `prepared: False` with the message in `detail` (no exception escapes).

In `tests/test_initrepo.py`: config with `"workers": {"codex": {"auth": "chatgpt"}}` passes `validate_tree`; `"auth": "bogus"` is flagged.

- [ ] **Step 2: RED**, then implement in `pool.py` (add `import base64`, `import time` as needed):

```python
class CodexAuthError(ValueError):
    """chatgpt-mode provisioning refused: no usable subscription token."""


_REFRESH_KEYS = ("refresh_token",)


def _codex_login_home():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def _jwt_exp(token):
    """The exp claim of a JWT, or None when unreadable. A freshness read
    for TTL checks — never signature verification."""
    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
        exp = claims.get("exp")
        return int(exp) if isinstance(exp, (int, float)) else None
    except (IndexError, ValueError, TypeError, AttributeError):
        return None


def _access_token(auth):
    tokens = auth.get("tokens")
    if isinstance(tokens, dict) and tokens.get("access_token"):
        return tokens["access_token"]
    return auth.get("access_token")


def _strip_refresh(node):
    if isinstance(node, dict):
        return {key: _strip_refresh(value) for key, value in node.items()
                if key not in _REFRESH_KEYS}
    return node
```

and in `seed_config_dir`'s codex branch (replacing the bare return):

```python
    if backend == "codex":
        cfg = work.worker_config(repo)
        if (cfg.get("codex") or {}).get("auth", "key") == "chatgpt":
            src = _codex_login_home() / "auth.json"
            try:
                auth = json.loads(src.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise CodexAuthError(
                    "codex auth 'chatgpt': no readable auth.json at "
                    f"{src} - run `codex` interactively to log in, then retry")
            token = _access_token(auth) if isinstance(auth, dict) else None
            exp = _jwt_exp(token) if token else None
            if exp is None:
                raise CodexAuthError(
                    "codex auth 'chatgpt': no decodable access token - run "
                    "`codex` interactively to refresh the login, then retry")
            remaining = exp - int(time.time())
            needed = int(cfg.get("timeout_seconds") or 1800) + 300
            if remaining < needed:
                raise CodexAuthError(
                    f"codex auth 'chatgpt': access token expires in {remaining}s "
                    f"but the run needs {needed}s - run `codex` interactively to "
                    "refresh the login, then retry")
            (home / "auth.json").write_text(
                json.dumps(_strip_refresh(auth), indent=2, sort_keys=True) + "\n",
                encoding="utf-8")
        return {"CODEX_HOME": str(home)}
```

In `provision`, wrap the `seed_config_dir` call: `except CodexAuthError as exc: return {..., "prepared": False, "detail": str(exc)}` matching the existing prep-failure shape (read the function; mirror how run_prep failures return).

`schemas/config.schema.json` `workers.codex` properties gain:

```json
            "auth": {"type": "string", "enum": ["key", "chatgpt"]}
```

- [ ] **Step 3: GREEN focused → FULL suite → commit** `feat(workers): codex chatgpt auth — stripped-token fan-out with TTL fail-closed`.

---

### Task 2: work.py worker env + doctor readout

**Files:**
- Modify: `scripts/factory/lib/work.py` (`_worker_env`, used by `run_work`), `scripts/factory/lib/doctor.py` (`worker_readiness` + `import time`, `from . import pool`)
- Test: `tests/test_work.py`, `tests/test_doctor.py`

**Interfaces:**
- Produces: `work._worker_env(cfg, backend) -> dict` (pops `OPENAI_API_KEY` only for codex+chatgpt); `worker_readiness` gains `"codex_auth"` (configured mode) and `"codex_login"` (remaining token seconds, 0 when absent/expired/undecodable).

- [ ] **Step 1: failing tests.** `tests/test_work.py`: `_worker_env({"codex": {"auth": "chatgpt"}}, "codex")` lacks `OPENAI_API_KEY` when the env has it (set/restore via `os.environ`); same cfg with backend `claude` keeps it; `{"codex": {"auth": "key"}}` and `{}` keep it. `tests/test_doctor.py`: with `CODEX_HOME` pointed at an empty temp dir, `worker_readiness(repo)["codex_login"] == 0` and `"codex_auth" == "key"` by default; with a fake auth.json (reuse the fake_jwt builder locally, exp now+7200) `codex_login` is > 0; with config auth chatgpt, `codex_auth == "chatgpt"`.

- [ ] **Step 2: RED → implement.**

`work.py`:

```python
def _worker_env(cfg, backend):
    env = dict(os.environ)
    if backend == "codex" and (cfg.get("codex") or {}).get("auth", "key") == "chatgpt":
        env.pop("OPENAI_API_KEY", None)
    return env
```

and in `run_work` replace `env = dict(os.environ)` with `env = _worker_env(cfg, backend)`.

`doctor.py` (`import time`, `from . import pool` — pool does not import doctor, no cycle):

```python
def _codex_login_ttl():
    src = pool._codex_login_home() / "auth.json"
    try:
        auth = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    token = pool._access_token(auth) if isinstance(auth, dict) else None
    exp = pool._jwt_exp(token) if token else None
    return max(0, exp - int(time.time())) if exp else 0
```

and in `worker_readiness`'s dict add:

```python
        "codex_auth": (cfg.get("codex") or {}).get("auth", "key"),
        "codex_login": _codex_login_ttl(),
```

- [ ] **Step 3: GREEN → FULL suite → commit** `feat(workers): chatgpt-mode worker env + doctor login readout`.

---

### Task 3: prose + docs — reference Auth section, capability row, skill mention, CHANGELOG 0.8.0

**Files:**
- Modify: `skills/capabilities/references/headless-workers.md`, `skills/capabilities/SKILL.md` (Headless worker row probe text), `skills/factory-workers/SKILL.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json` (→ 0.8.0)
- Test: `tests/test_plugin_structure.py`

**Interfaces:**
- Produces: documented auth modes; version 0.8.0.

- [ ] **Step 1: failing pins** in `tests/test_plugin_structure.py`:

```python
    def test_headless_workers_reference_documents_auth_modes(self):
        ref = (ROOT / "skills/capabilities/references/headless-workers.md").read_text()
        self.assertIn('workers.codex.auth', ref)
        self.assertIn('"chatgpt"', ref)
        self.assertIn("refresh token", ref)
        self.assertIn("never writes", ref)
        self.assertIn("plan rate limits", ref)
        self.assertIn("factory work` without provisioning", ref)
```

- [ ] **Step 2: RED → edits.** In `headless-workers.md`, add an `## Auth` section (read the file, place after its config/setup section):

```markdown
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
  and retry); mid-run expiry surfaces as reason `auth` → exit 1 → the pool
  stops with a packet, exactly like a bad key. All workers share the plan
  rate limits — the pool's staggered launch and backoff already pace that
  bucket. The engine removes `OPENAI_API_KEY` from chatgpt-mode worker
  environments so billing never silently flips to the API. `factory doctor
  --json` → workers reports `codex_auth` and `codex_login` (remaining token
  seconds). Running `factory work` without provisioning uses your real
  `~/.codex` like an interactive session — fine for one process; the pool
  path always provisions.
```

In `skills/capabilities/SKILL.md`, extend the Headless worker row's probe text: after "with its key env var set", add "(or, for codex, `workers.codex.auth: \"chatgpt\"` plus a fresh `codex` login — `factory doctor` reports both)". In `skills/factory-workers/SKILL.md`, wherever it reads doctor for readiness, add one sentence: "In `chatgpt` auth mode, a provision refusal naming the codex login is a setup fault for the human (re-login, retry) — treat it like the auth pool-stop, not a per-item skip."

CHANGELOG `[0.8.0]` dated entry (house style, one bold-titled paragraph): parallel Codex on ChatGPT-subscription auth — `workers.codex.auth: "chatgpt"`, stripped-token fan-out (no refresh race at any parallelism, real login never written), TTL fail-closed provision, mid-run expiry = honest auth pool-stop, `OPENAI_API_KEY` popped from chatgpt-mode envs, doctor `codex_auth`/`codex_login`, default `"key"` unchanged. Suite line with real numbers. `plugin.json` → `0.8.0`.

- [ ] **Step 3: GREEN → FULL suite → commit** `docs: v0.8.0 — codex subscription workers (reference, capability row, changelog, bump)`.

---

## Plan self-review notes

- Spec coverage: Decisions 1-2 (T1), 3 (existing engine path, documented T3), 4 (T1 schema + defaults), 5 (T2), 6-7 (T3 prose). Doctor readout (T2).
- The `factory-workers` skill needs no flow change — provision failures already skip-and-packet; T3 adds one clarifying sentence only.
- `_codex_login_home` reads `$CODEX_HOME` first so tests (and users with relocated homes) control it without touching `~/.codex`.
