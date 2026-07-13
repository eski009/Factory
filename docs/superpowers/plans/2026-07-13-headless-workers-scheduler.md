# Headless Workers — Phase B (Scheduler) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Layer-2 scheduler for headless workers — a bounded parallel pool that keeps K workers busy across independent items, each in its own `factory/<id>` worktree — by giving the engine the deterministic primitives (top-N selection, worktree provisioning + prep + per-worker config-dir seeding, cleanup, backoff) that a skill-driven pool loop orchestrates, and folding in the four Phase-A deferrals.

**Architecture:** The loop/pacing/collect-advance *policy* lives in a new `factory-workers` skill (prose), exactly as the design spec's Approach C dictates (Python = mechanical + testable, LLM = judgment). Python gains only: `dispatch.next_items(n)` (top-N actionable), a new `scripts/factory/lib/pool.py` (create/reuse a nested gitignored worktree under `.factory/worktrees/<id>`, copy `.worktreeinclude` files, run the `workers.prep` command, seed an isolated `CLAUDE_CONFIG_DIR`/`CODEX_HOME` with pre-accepted trust, clean up worktrees, compute capped exponential backoff), and two new CLI verbs (`factory provision`, `factory cleanup`) plus `factory next -n`. Everything is testable against real temp git repos with `prep` set to `true`/`false` — no live CLI, no network. Trust is unchanged: the pool advances items through the *existing* gates (`factory advance <id> review`, the dispatcher's two-strikes-then-blocked rule); nothing bypasses review/verify/green-tests.

**Tech Stack:** Python 3.11 standard library only (`argparse json os re shutil subprocess time pathlib datetime`). No third-party dependencies. Tests: `unittest`.

**Design source:** `docs/superpowers/specs/2026-07-12-headless-workers-design.md` (Approach C, Layer 2 = §8; worktree prep + network posture = §7; ground-truth constraints = §3; failure modes = §14). This is **Phase B** (the scheduler). Phase A (the `factory work` executor) is merged to `main` (`scripts/factory/lib/work.py`, `factory work`, 375 tests green).

## Global Constraints

- **Python 3.11, standard library only.** No new third-party imports, no `requirements` file. Every import must be one of `argparse json os re shutil subprocess time pathlib datetime` or an internal `scripts.factory.lib.*` module. (`time` is new to Phase B — used only for `time.monotonic()` duration measurement; it is stdlib.)
- **Test runner:** `python3 -m unittest discover -s tests -v`, run from the repo root. Tests are `unittest.TestCase` subclasses using `tempfile.TemporaryDirectory()` in `setUp`/`tearDown`. There is no pytest, no `conftest.py`, no fixtures. **Run the full suite after every task**, not just the task's own tests — schema/config changes can ripple.
- **Schemas** live in `schemas/` named `<name>.schema.json`, loaded via `initrepo.load_schema("<name>")`. The validator (`scripts/factory/lib/validate.py`) supports **only** `type, enum, required, properties, additionalProperties:false, items, pattern, minLength, minimum`. **Do not use** `maximum`, `maxLength`, `$ref`, `oneOf`, `anyOf`, or `null` types.
- **Event shape is `{"event": <str>, "ts": <str>, "data": <obj?>}`.** Always append via `logs.append_event(repo, item_id, event, data)`. Never write `type`/`timestamp`. A line is well-formed only if it is a dict with both `event` and `ts`.
- **A measured `spend` event must satisfy `initrepo.spend_event_errors`:** top-level `event:"spend"`, `data.provenance == "measured"`, and `data.tokens` present with at least one of `input`/`output`/`total`. A proxy event omits `tokens` entirely. Phase B adds **no** new spend events (prep runs no model); it only adds inert audit events (`prep.completed`, `prep.failed`) that gates and cost never read.
- **`.factory/` runtime state is gitignored in the target repo** (the existing convention). Per-worker worktrees live at `.factory/worktrees/<id>` — nested inside the repo but invisible to its index because `.factory/` is ignored. This is verified to work: `git worktree add`, commit, `git worktree remove --force` + `prune` all succeed, and the main tree's `git status --porcelain` stays empty. `git worktree remove` keeps the branch ref, so `review`/`verify`/`ship` still operate on `factory/<id>` after the worktree dir is gone.
- **Python never advances stages.** The engine primitives (`pool.provision`, `pool.cleanup`, `work.run_work`) produce artifacts + log events and return status; the **caller** (the `factory-workers` skill) owns every `factory advance`. This mirrors the locked `factory work` contract.
- **CLI exit-code convention:** `0` ok, `1` usage/internal error, `2` gate/precondition refusal, `3` worker attempted-but-failed. CLI command functions **return an int** and print errors to `sys.stderr` — they never call `sys.exit` or raise to the top.
- **Do not stage `README.md`.** It carries a pre-existing unstaged modification; every commit in this plan stages only its named files.

## File Structure

- **Create** `scripts/factory/lib/pool.py` — the scheduler's per-worker mechanics: `PoolError`, `_git`, `_default_base`, `ensure_worktree`, `copy_worktree_includes`, `seed_config_dir`, `run_prep`, `provision`, `cleanup`, `backoff_delay`. One focused module; grows task-by-task (Tasks 6–9).
- **Create** `tests/test_pool.py` — unit tests for `lib/pool.py` against real temp git repos (prep = `true`/`false`).
- **Create** `tests/test_cli_pool.py` — in-process `factory.main([...])` for `next -n`, `provision`, `cleanup`.
- **Create** `skills/factory-workers/SKILL.md` — the Layer-2 pool loop (prose scheduler).
- **Modify** `scripts/factory/lib/dispatch.py` — add `next_items(repo, n)`; rewire `next_item`.
- **Modify** `scripts/factory/lib/paths.py` — add `worktrees_dir`, `worktree_dir`.
- **Modify** `scripts/factory/lib/work.py` — fold deferrals: `worker_config` isinstance guard, `duration_s` population, `_looks_auth` + auth-reason classification + exit-1 mapping.
- **Modify** `schemas/result.schema.json` — widen `files_changed.change` enum with `U`, `X`, `B` (deferral d).
- **Modify** `scripts/factory/lib/doctor.py` — add `max_parallel` + `retry` to `worker_readiness`.
- **Modify** `scripts/factory/factory.py` — `factory next -n/--count`; register `provision` + `cleanup`.
- **Modify** `skills/factory-dispatch/SKILL.md` — cite `factory-workers` for the parallel implement pool.
- **Modify** `skills/factory-autopilot/SKILL.md` — allow the pool within budget checkpoints.
- **Modify** `skills/capabilities/SKILL.md` — extend the "Headless worker" row to mention the Layer-2 pool.
- **Modify** `skills/capabilities/references/headless-workers.md` — add a scheduler / provision / cleanup / `next -n` section.
- **Modify** `tests/test_dispatch.py` — `next_items` tests.
- **Modify** `tests/test_work.py` — isinstance guard, `duration_s`, auth→exit-1 tests.
- **Modify** `tests/test_work_backends.py` — auth-reason parse tests.
- **Modify** `tests/test_doctor.py` — assert `max_parallel` + `retry`.
- **Modify** `tests/test_plugin_coherence.py` — scheduler-wiring drift guard.

---

### Task 1: `next_items(n)` selection + `factory next -n`

**Files:**
- Modify: `scripts/factory/lib/dispatch.py`
- Modify: `scripts/factory/factory.py` (`cmd_next`, the `next` subparser)
- Test: `tests/test_dispatch.py`, `tests/test_cli_pool.py` (create)

**Interfaces:**
- Consumes: `items.list_items_safe`, `dispatch.NOT_ACTIONABLE`, `dispatch._by_priority`.
- Produces: `dispatch.next_items(repo, n) -> list[dict]` (top-N actionable metas by `(priority, id)`; `n <= 0` → `[]`); `dispatch.next_item(repo)` unchanged in behavior (now `next_items(repo, 1)[0] or None`). CLI `factory next [-n/--count N] [--json]`: with `--count` present, prints a JSON **array** (or N lines) of the top-N; without it, the legacy single-object / `"nothing actionable"` behavior is preserved.

- [ ] **Step 1: Write the failing unit test**

Append to `tests/test_dispatch.py` (a new TestCase before the `if __name__` line):

```python
class TestNextItems(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_repo_returns_empty_list(self):
        self.assertEqual(dispatch.next_items(self.repo, 3), [])

    def test_returns_top_n_in_priority_order(self):
        put(self.repo, "0001-c", "spec", priority=3)
        put(self.repo, "0002-a", "idea", priority=1)
        put(self.repo, "0003-b", "plan", priority=2)
        got = [m["id"] for m in dispatch.next_items(self.repo, 2)]
        self.assertEqual(got, ["0002-a", "0003-b"])

    def test_n_larger_than_backlog_returns_all_actionable(self):
        put(self.repo, "0001-a", "idea", priority=1)
        put(self.repo, "0002-done", "done", priority=1)
        got = [m["id"] for m in dispatch.next_items(self.repo, 10)]
        self.assertEqual(got, ["0001-a"])

    def test_non_positive_n_returns_empty(self):
        put(self.repo, "0001-a", "idea", priority=1)
        self.assertEqual(dispatch.next_items(self.repo, 0), [])
        self.assertEqual(dispatch.next_items(self.repo, -1), [])

    def test_next_item_still_matches_first_of_next_items(self):
        put(self.repo, "0001-a", "idea", priority=2)
        put(self.repo, "0002-b", "idea", priority=1)
        self.assertEqual(dispatch.next_item(self.repo)["id"],
                         dispatch.next_items(self.repo, 1)[0]["id"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_dispatch.TestNextItems -v`
Expected: FAIL — `AttributeError: module 'scripts.factory.lib.dispatch' has no attribute 'next_items'`.

- [ ] **Step 3: Add `next_items` and rewire `next_item` in `dispatch.py`**

Replace the `next_item` function in `scripts/factory/lib/dispatch.py` with:

```python
def next_items(repo, n):
    """Top-N actionable items by (priority, id). n <= 0 → []. Fewer than n
    are returned when the backlog is smaller. Actionability matches
    next_item: everything except done/blocked/waiting-human. D1 assumes the
    top-N are independent; worktree isolation makes a wrong guess a merge
    conflict at ship, not corruption."""
    if n <= 0:
        return []
    metas, _errors = items.list_items_safe(repo)
    actionable = [m for m in metas if m["stage"] not in NOT_ACTIONABLE]
    return _by_priority(actionable)[:n]


def next_item(repo):
    got = next_items(repo, 1)
    return got[0] if got else None
```

- [ ] **Step 4: Run the unit test to verify it passes**

Run: `python3 -m unittest tests.test_dispatch -v`
Expected: PASS (existing `TestNextItem` + new `TestNextItems`, all green).

- [ ] **Step 5: Write the failing CLI test**

Create `tests/test_cli_pool.py`:

```python
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory
from scripts.factory.lib import items


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True)


def _put(repo, item_id, stage, priority):
    meta = {"id": item_id, "title": item_id, "stage": stage, "kind": "backend",
            "created": "2026-07-03T00:00:00Z", "updated": "2026-07-03T00:00:00Z",
            "priority": priority}
    items.save_item(repo, meta, "")


class CliNextCountTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        self.run_cli("init")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(self.repo), *args])
        return code, out.getvalue(), err.getvalue()

    def test_next_count_emits_json_array(self):
        _put(self.repo, "0001-a", "idea", 1)
        _put(self.repo, "0002-b", "spec", 2)
        _put(self.repo, "0003-done", "done", 1)
        code, out, err = self.run_cli("next", "-n", "5", "--json")
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertIsInstance(data, list)
        self.assertEqual([m["id"] for m in data], ["0001-a", "0002-b"])

    def test_next_without_count_stays_single_object(self):
        _put(self.repo, "0001-a", "idea", 1)
        code, out, err = self.run_cli("next", "--json")
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertIsInstance(data, dict)
        self.assertEqual(data["id"], "0001-a")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6: Run the CLI test to verify it fails**

Run: `python3 -m unittest tests.test_cli_pool.CliNextCountTest -v`
Expected: FAIL — `factory next -n` is not recognized (argparse error → exit 1), or `--json` still prints a dict for the `-n` case.

- [ ] **Step 7: Add `--count` to `cmd_next` and the `next` subparser in `factory.py`**

Replace `cmd_next` in `scripts/factory/factory.py` with:

```python
def cmd_next(args):
    if not _require_factory_repo(args.repo):
        return 2
    metas, errors = items.list_items_safe(args.repo)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 2
    if args.count is not None:
        rows = dispatch.next_items(args.repo, args.count)
        if args.json:
            print(json.dumps(rows, indent=2, sort_keys=True))
        elif not rows:
            print("nothing actionable")
        else:
            for m in rows:
                print(f"{m['id']} {m['stage']}")
        return 0
    meta = dispatch.next_item(args.repo)
    if args.json:
        print(json.dumps(meta, indent=2, sort_keys=True))
    elif meta is None:
        print("nothing actionable")
    else:
        print(f"{meta['id']} {meta['stage']}")
    return 0
```

In `main()`, find the `next` subparser and add the `--count` argument (leave `--json` as-is):

```python
    p = sub.add_parser("next", help="get the next actionable work item(s)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--count", "-n", type=int,
                   help="return up to N top actionable items (as a list)")
    p.set_defaults(func=cmd_next)
```

- [ ] **Step 8: Run the CLI test + full suite to verify green**

Run: `python3 -m unittest tests.test_cli_pool.CliNextCountTest -v`
Expected: PASS (2 tests).
Run: `python3 -m unittest discover -s tests -v`
Expected: all green (376 baseline tests + the new ones).

- [ ] **Step 9: Commit**

```bash
git add scripts/factory/lib/dispatch.py scripts/factory/factory.py tests/test_dispatch.py tests/test_cli_pool.py
git commit -m "feat(pool): next_items(n) top-N selection + factory next -n"
```

---

### Task 2: widen `result.json` `files_changed.change` enum (deferral d)

**Files:**
- Modify: `schemas/result.schema.json`
- Test: `tests/test_work.py`

**Interfaces:** none new — `work.normalize` already sets `change` to `git diff --name-status`'s first character; this widens the schema so an unusual status (`U` unmerged, `X` unknown, `B` broken-pairing) validates instead of failing `run_work` with an internal schema error.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_work.py` (new TestCase before the `if __name__` line):

```python
class ChangeEnumTest(unittest.TestCase):
    def test_unusual_git_status_chars_validate(self):
        gstate = {"commits": ["abc123"], "clean": True,
                  "files_changed": [{"path": "a.txt", "change": "U"},
                                    {"path": "b.txt", "change": "X"},
                                    {"path": "c.txt", "change": "B"}]}
        parsed = {"status": "done", "reason": None,
                  "usage": {"input": 1, "output": 1, "total": 2},
                  "summary": "s", "cost_usd": None}
        result = work.normalize("0001-thing", "stub", None,
                                "factory/0001-thing", gstate, parsed, None,
                                "items/0001-thing/worker/worker.log")
        errors = validate.validate(result, initrepo.load_schema("result"),
                                   "result")
        self.assertEqual(errors, [])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_work.ChangeEnumTest -v`
Expected: FAIL — validation error naming `change` (value `"U"` not in the current `["A","M","D","R","C","T"]` enum).

- [ ] **Step 3: Widen the enum in `schemas/result.schema.json`**

In `schemas/result.schema.json`, find the `files_changed` → `items` → `properties` → `change` enum and add `U`, `X`, `B`:

```json
          "change": {"type": "string",
                     "enum": ["A", "M", "D", "R", "C", "T", "U", "X", "B"]}
```

- [ ] **Step 4: Run the test + full suite to verify green**

Run: `python3 -m unittest tests.test_work.ChangeEnumTest -v`
Expected: PASS.
Run: `python3 -m unittest discover -s tests -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add schemas/result.schema.json tests/test_work.py
git commit -m "harden(work): widen files_changed enum (U/X/B) so odd git status is safe-fail"
```

---

### Task 3: `worker_config` isinstance guard for malformed nested config (deferral b)

**Files:**
- Modify: `scripts/factory/lib/work.py` (`worker_config`)
- Test: `tests/test_work.py`

**Interfaces:** none new — `worker_config` still returns the merged dict, but a non-dict `retry`/`codex` in a hand-corrupted `config.json` is now **ignored** (defaults kept) instead of overwriting the default dict with a scalar. Phase B dereferences `cfg["retry"]["max_attempts"]` in backoff, so this must not be a string.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_work.py` (inside the existing `WorkerConfigTest` class — it already has `_set_workers`/`_init_repo` helpers via the module):

```python
    def test_non_dict_retry_is_ignored_keeps_defaults(self):
        _set_workers(self.repo, {"retry": "oops", "codex": 5})
        cfg = work.worker_config(self.repo)
        self.assertEqual(cfg["retry"]["max_attempts"], 3)
        self.assertEqual(cfg["retry"]["base_delay_seconds"], 20)
        self.assertEqual(cfg["codex"]["sandbox"], "workspace-write")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_work.WorkerConfigTest.test_non_dict_retry_is_ignored_keeps_defaults -v`
Expected: FAIL — `TypeError: string indices must be integers` (or `KeyError`), because the current merge sets `merged["retry"] = "oops"`.

- [ ] **Step 3: Fix the merge in `worker_config`**

In `scripts/factory/lib/work.py`, replace the merge loop at the end of `worker_config` with:

```python
    for key, value in block.items():
        if key in ("retry", "codex"):
            # Malformed nested config (non-dict) is ignored so the merged
            # defaults survive — Phase B dereferences retry.* for backoff.
            if isinstance(value, dict):
                merged[key].update(value)
        else:
            merged[key] = value
    return merged
```

- [ ] **Step 4: Run the test + full suite to verify green**

Run: `python3 -m unittest tests.test_work.WorkerConfigTest -v`
Expected: PASS (all `WorkerConfigTest` methods).
Run: `python3 -m unittest discover -s tests -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/work.py tests/test_work.py
git commit -m "harden(work): worker_config ignores non-dict retry/codex (keeps defaults)"
```

---

### Task 4: populate `duration_s` (deferral c)

**Files:**
- Modify: `scripts/factory/lib/work.py` (`normalize`, `run_work`)
- Test: `tests/test_work.py`

**Interfaces:**
- `work.normalize(..., worker_log, duration_s=0)` — gains a trailing keyword arg; always writes `result["duration_s"] = int(max(0, duration_s))`. Existing positional callers are unaffected (default 0).
- `work.run_work` measures wall-clock around the backend call with `time.monotonic()` and passes it through.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_work.py` inside the existing `RunWorkTest` class (it has `setUp` creating item `0001-thing` at implement on branch `factory/0001-thing`):

```python
    def test_result_has_duration_s(self):
        code, result = work.run_work(self.repo, "0001-thing", backend="stub",
                                     worktree=str(self.repo))
        self.assertEqual(code, 0)
        self.assertIn("duration_s", result)
        self.assertIsInstance(result["duration_s"], int)
        self.assertGreaterEqual(result["duration_s"], 0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_work.RunWorkTest.test_result_has_duration_s -v`
Expected: FAIL — `AssertionError: 'duration_s' not found` in the result.

- [ ] **Step 3: Add the `time` import and thread duration through `normalize` + `run_work`**

In `scripts/factory/lib/work.py`, add `import time` to the import block (with the other stdlib imports):

```python
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
```

Change the `normalize` signature and add the field. Replace the `def normalize(...)` line and the `result = {` block header so it reads:

```python
def normalize(item_id, backend, model, branch, gstate, parsed, test_result,
              worker_log, duration_s=0):
    """Backend-independent result packet. Git-first correctness (commits +
    tests) overrides a backend's optimistic self-report."""
    status = parsed["status"]
    reason = parsed.get("reason")
    if status == "done":
        if not gstate["commits"]:
            status, reason = "failed", "no_changes"
        elif test_result is not None and not test_result["passed"]:
            status, reason = "failed", "red_tests"
    usage = parsed.get("usage") or {}
    measured = any(usage.get(k) for k in ("input", "output", "total"))
    result = {
        "id": item_id,
        "status": status,
        "backend": backend,
        "branch": branch,
        "commits": gstate["commits"],
        "files_changed": gstate["files_changed"],
        "duration_s": int(max(0, duration_s)),
        "summary": (parsed.get("summary") or "")[:2000],
        "worker_log": worker_log,
    }
```

(Leave the rest of `normalize` — the `if model` / `if reason` / `if measured` / `test` / `cost_usd_estimate` tail — unchanged.)

In `run_work`, wrap the backend call with `time.monotonic()` and pass the elapsed seconds to `normalize`. Replace the block from `base_sha = git_head(work_tree)` through the `raw = BACKENDS[...]` call, and the later `normalize(...)` call:

```python
    base_sha = git_head(work_tree)
    started = time.monotonic()
    raw = BACKENDS[backend](brief, work_tree, model, timeout, network,
                            sandbox, env)
    duration_s = int(time.monotonic() - started)
```

```python
    gstate = git_state(work_tree, base_sha)
    result = normalize(item_id, backend, model, f"factory/{item_id}", gstate,
                       parsed, test_result,
                       f"items/{item_id}/worker/worker.log",
                       duration_s=duration_s)
```

- [ ] **Step 4: Run the test + full suite to verify green**

Run: `python3 -m unittest tests.test_work.RunWorkTest -v`
Expected: PASS (existing RunWork tests + the new duration test).
Run: `python3 -m unittest discover -s tests -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/work.py tests/test_work.py
git commit -m "feat(work): populate result.duration_s from wall-clock"
```

---

### Task 5: auth-reason classification + exit-1 mapping (deferral a)

**Files:**
- Modify: `scripts/factory/lib/work.py` (`_looks_auth`, `_claude_parse`, `_codex_parse`, `run_work`)
- Test: `tests/test_work_backends.py`, `tests/test_work.py`

**Interfaces:**
- Produces: `work._looks_auth(obj, raw) -> bool`. The claude/codex parsers set `reason == "auth"` when a failure looks like a 401/403/invalid-key/unauthorized/authentication error (checked **before** rate-limit, since they never co-occur). `run_work` maps a result whose `reason == "auth"` to **exit code 1** (a setup/usage error the scheduler must surface, not a retryable worker attempt) while still logging `implement.failed`.

- [ ] **Step 1: Write the failing backend-parser tests**

Append to `tests/test_work_backends.py` (a new TestCase before the `if __name__` line):

```python
class AuthReasonTest(unittest.TestCase):
    def test_claude_401_is_auth(self):
        raw = {"exit_code": 1, "timed_out": False,
               "stderr": "API Error: 401 authentication_error invalid x-api-key",
               "stdout": "{}"}
        self.assertEqual(work._claude_parse(raw)["reason"], "auth")

    def test_codex_invalid_api_key_is_auth(self):
        raw = {"exit_code": 1, "timed_out": False,
               "stderr": "stream error: 401 Unauthorized (invalid_api_key)",
               "stdout": ""}
        self.assertEqual(work._codex_parse(raw)["reason"], "auth")

    def test_auth_beats_rate_limited_when_both_absent_conflict(self):
        # a plain 401 with no rate-limit tokens is auth, not crash
        raw = {"exit_code": 1, "timed_out": False,
               "stderr": "403 Forbidden", "stdout": "{}"}
        self.assertEqual(work._claude_parse(raw)["reason"], "auth")

    def test_ordinary_crash_is_not_auth(self):
        raw = {"exit_code": 1, "timed_out": False,
               "stderr": "TypeError: undefined is not a function", "stdout": "{}"}
        self.assertEqual(work._claude_parse(raw)["reason"], "crash")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_work_backends.AuthReasonTest -v`
Expected: FAIL — `_claude_parse` returns `"crash"` for the 401 case (no auth classification yet), and `_looks_auth` is undefined.

- [ ] **Step 3: Add `_looks_auth` and wire it into both parsers**

In `scripts/factory/lib/work.py`, add `_looks_auth` next to `_looks_rate_limited`:

```python
def _looks_auth(obj, raw):
    # Narrow, high-signal auth markers only (avoid matching the bare word
    # "auth" which appears in unrelated messages). 401/403 + invalid-key +
    # unauthorized + authentication error are the vendor failure strings.
    blob = (json.dumps(obj) + " " + (raw.get("stderr") or "")).lower()
    return any(term in blob for term in
               ("401", "403", "invalid api key", "invalid_api_key",
                "unauthorized", "authentication"))
```

In `_claude_parse`, replace the failure-reason line:

```python
    reason = "rate_limited" if _looks_rate_limited(obj, raw) else "crash"
```

with:

```python
    if _looks_auth(obj, raw):
        reason = "auth"
    elif _looks_rate_limited(obj, raw):
        reason = "rate_limited"
    else:
        reason = "crash"
```

In `_codex_parse`, replace the failure-reason line:

```python
        reason = "rate_limited" if _looks_rate_limited({}, raw) else "crash"
```

with:

```python
        if _looks_auth({}, raw):
            reason = "auth"
        elif _looks_rate_limited({}, raw):
            reason = "rate_limited"
        else:
            reason = "crash"
```

- [ ] **Step 4: Run the backend-parser tests to verify they pass**

Run: `python3 -m unittest tests.test_work_backends.AuthReasonTest -v`
Expected: PASS (4 tests). Run `python3 -m unittest tests.test_work_backends -v` — all green (existing claude/codex tests still pass; an ordinary crash stays `crash`).

- [ ] **Step 5: Write the failing `run_work` exit-code test**

Append to `tests/test_work.py` inside the existing `RunWorkTest` class:

```python
    def test_auth_failure_exits_one_and_logs_failed(self):
        os.environ["FACTORY_WORK_STUB"] = json.dumps(
            {"exit_code": 1, "commit": False, "reason": "auth"})
        code, result = work.run_work(self.repo, "0001-thing", backend="stub",
                                     worktree=str(self.repo))
        self.assertEqual(code, 1)
        self.assertEqual(result["reason"], "auth")
        self.assertIn("implement.failed", self._events())
        self.assertNotIn("implement.completed", self._events())
```

- [ ] **Step 6: Run to verify it fails**

Run: `python3 -m unittest tests.test_work.RunWorkTest.test_auth_failure_exits_one_and_logs_failed -v`
Expected: FAIL — `run_work` currently returns exit code `3` for any failed status (including `auth`).

- [ ] **Step 7: Map `reason == "auth"` to exit 1 in `run_work`**

In `scripts/factory/lib/work.py`, replace the tail of `run_work` (the failure branch after `implement.completed`) so it reads:

```python
    logs.append_event(repo, item_id, "implement.failed",
                      {"reason": result.get("reason"), "backend": backend})
    if result.get("reason") == "auth":
        # A bad/expired key is a setup error, not a retryable worker attempt:
        # exit 1 so the scheduler surfaces it (and never burns the pool on it).
        return 1, result
    return 3, result
```

- [ ] **Step 8: Run the test + full suite to verify green**

Run: `python3 -m unittest tests.test_work.RunWorkTest -v`
Expected: PASS.
Run: `python3 -m unittest discover -s tests -v`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add scripts/factory/lib/work.py tests/test_work.py tests/test_work_backends.py
git commit -m "feat(work): classify auth failures (401/403/invalid-key) as reason auth, exit 1"
```

---

### Task 6: `paths.worktree_dir` + `pool.ensure_worktree`

**Files:**
- Modify: `scripts/factory/lib/paths.py`
- Create: `scripts/factory/lib/pool.py`
- Test: `tests/test_pool.py` (create)

**Interfaces:**
- Produces: `paths.worktrees_dir(repo) -> Path` (`.factory/worktrees`), `paths.worktree_dir(repo, item_id) -> Path` (`.factory/worktrees/<id>`).
- Produces: `pool.PoolError` (Exception); `pool._git(cwd, *args)` (returns a `CompletedProcess`); `pool._default_base(repo) -> str`; `pool.ensure_worktree(repo, item_id) -> (path:str, created:bool)` — creates a worktree on `factory/<id>` at `worktree_dir` (reusing it if already registered, clearing a stale dir first), raising `PoolError` if `git worktree add` fails.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pool.py`:

```python
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, paths, pool


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True)


def _init_git_repo(repo):
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-q", "-m", "seed")


def _set_workers(repo, workers):
    cfg_path = repo / ".factory" / "config.json"
    data = json.loads(cfg_path.read_text())
    data["workers"] = workers
    cfg_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")


def _make_item(repo, item_id="0001-thing", stage="implement"):
    meta = {"id": item_id, "title": "Thing", "stage": stage, "kind": "backend",
            "created": "2026-07-03T00:00:00Z", "updated": "2026-07-03T00:00:00Z"}
    items.save_item(repo, meta, "")


class EnsureWorktreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)
        initrepo.init(self.repo)
        _make_item(self.repo)

    def tearDown(self):
        # remove any worktrees this test created before the dir is torn down
        pool._git(self.repo, "worktree", "prune")
        self.tmp.cleanup()

    def test_creates_worktree_on_factory_branch(self):
        path, created = pool.ensure_worktree(self.repo, "0001-thing")
        self.assertTrue(created)
        self.assertEqual(Path(path),
                         paths.worktree_dir(self.repo, "0001-thing"))
        self.assertTrue(Path(path).is_dir())
        head = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                              cwd=path, capture_output=True, text=True)
        self.assertEqual(head.stdout.strip(), "factory/0001-thing")

    def test_reuses_existing_worktree(self):
        first, _ = pool.ensure_worktree(self.repo, "0001-thing")
        second, created = pool.ensure_worktree(self.repo, "0001-thing")
        self.assertFalse(created)
        self.assertEqual(first, second)

    def test_main_tree_stays_clean(self):
        # .factory/ is gitignored so the nested worktree is invisible
        (self.repo / ".gitignore").write_text(".factory/\n", encoding="utf-8")
        _git(self.repo, "add", ".gitignore")
        _git(self.repo, "commit", "-q", "-m", "ignore factory")
        pool.ensure_worktree(self.repo, "0001-thing")
        status = subprocess.run(["git", "status", "--porcelain"],
                                cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(status.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_pool -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.factory.lib.pool'`.

- [ ] **Step 3: Add the paths helpers**

In `scripts/factory/lib/paths.py`, add after `item_dir`:

```python
def worktrees_dir(repo):
    return factory_root(repo) / "worktrees"


def worktree_dir(repo, item_id):
    return worktrees_dir(repo) / item_id
```

- [ ] **Step 4: Create `lib/pool.py` with `ensure_worktree`**

Create `scripts/factory/lib/pool.py`:

```python
"""factory scheduler primitives (Layer 2). The bounded parallel pool's
per-worker MECHANICS live here; the loop/pacing/collect-advance POLICY lives
in the factory-workers skill (design spec Approach C, §8). Python stdlib only.

Each worker runs in its own git worktree on branch factory/<id>, checked out
under .factory/worktrees/<id> — nested inside the repo but invisible to its
index because .factory/ is gitignored. `git worktree remove` keeps the branch
ref, so review/verify/ship still see factory/<id> after the worktree is gone.

Nothing here advances an item's stage — the caller (factory-workers) owns
every `factory advance`, consistent with the factory work contract.
"""

import json
import shutil
import subprocess
from pathlib import Path

from . import items, logs, paths, work


class PoolError(Exception):
    pass


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd,
                          capture_output=True, text=True)


def _default_base(repo):
    """The branch new worktrees are cut from: the remote's default HEAD when
    known, else the repo's current branch, else 'HEAD' (detached is fine for
    `git worktree add -b`)."""
    ref = _git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if ref.returncode == 0 and ref.stdout.strip():
        return ref.stdout.strip().split("/", 1)[-1]
    cur = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    return cur.stdout.strip() if cur.returncode == 0 and cur.stdout.strip() \
        else "HEAD"


def _registered_worktree(repo, branch):
    """The filesystem path already checked out on `branch`, else None."""
    listing = _git(repo, "worktree", "list", "--porcelain")
    if listing.returncode != 0:
        return None
    current = None
    for line in listing.stdout.splitlines():
        if line.startswith("worktree "):
            current = line[len("worktree "):]
        elif line.strip() == f"branch refs/heads/{branch}" and current:
            return current
    return None


def ensure_worktree(repo, item_id):
    """Create (or reuse) the worktree on factory/<id> at worktree_dir.
    Returns (path, created). Raises PoolError if git refuses to add it."""
    branch = f"factory/{item_id}"
    existing = _registered_worktree(repo, branch)
    if existing:
        return existing, False
    target = paths.worktree_dir(repo, item_id)
    if target.exists():
        # a stale dir from a crashed run: clear admin entries then the dir
        _git(repo, "worktree", "prune")
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    branch_exists = _git(repo, "rev-parse", "--verify", "--quiet",
                         "refs/heads/" + branch).returncode == 0
    if branch_exists:
        added = _git(repo, "worktree", "add", str(target), branch)
    else:
        added = _git(repo, "worktree", "add", str(target), "-b", branch,
                     _default_base(repo))
    if added.returncode != 0:
        raise PoolError(
            f"git worktree add failed for {branch}: {added.stderr.strip()}")
    return str(target), True
```

- [ ] **Step 5: Run the test + full suite to verify green**

Run: `python3 -m unittest tests.test_pool -v`
Expected: PASS (3 tests).
Run: `python3 -m unittest discover -s tests -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add scripts/factory/lib/paths.py scripts/factory/lib/pool.py tests/test_pool.py
git commit -m "feat(pool): worktree_dir path + ensure_worktree (nested, reuse, stale-clear)"
```

---

### Task 7: `pool.seed_config_dir` + `pool.copy_worktree_includes`

**Files:**
- Modify: `scripts/factory/lib/pool.py`
- Test: `tests/test_pool.py`

**Interfaces:**
- Produces: `pool.seed_config_dir(repo, item_id, backend, worktree) -> dict` — creates `.factory/items/<id>/worker/home`; for `claude` writes `<home>/.claude.json` pre-accepting onboarding + the worktree path's trust dialog and returns `{"CLAUDE_CONFIG_DIR": <home>}`; for `codex` returns `{"CODEX_HOME": <home>}`; otherwise `{}`.
- Produces: `pool.copy_worktree_includes(repo, worktree) -> list[str]` — copies each existing path listed in `<repo>/.worktreeinclude` (blank/`#` lines skipped) into the worktree, returning the copied entries.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pool.py` (new TestCases before the `if __name__` line):

```python
class SeedConfigDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)
        initrepo.init(self.repo)
        _make_item(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_claude_seed_writes_trust_state(self):
        wt = str(self.repo / "wt")
        env = pool.seed_config_dir(self.repo, "0001-thing", "claude", wt)
        self.assertIn("CLAUDE_CONFIG_DIR", env)
        cfg = json.loads((Path(env["CLAUDE_CONFIG_DIR"]) / ".claude.json")
                         .read_text())
        self.assertTrue(cfg["hasCompletedOnboarding"])
        key = str(Path(wt).resolve())
        self.assertTrue(cfg["projects"][key]["hasTrustDialogAccepted"])

    def test_codex_seed_sets_codex_home(self):
        env = pool.seed_config_dir(self.repo, "0001-thing", "codex", "/wt")
        self.assertIn("CODEX_HOME", env)
        self.assertTrue(Path(env["CODEX_HOME"]).is_dir())

    def test_stub_backend_has_no_config_env(self):
        self.assertEqual(
            pool.seed_config_dir(self.repo, "0001-thing", "stub", "/wt"), {})


class WorktreeIncludeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)
        initrepo.init(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_copies_listed_files_skips_missing(self):
        (self.repo / ".worktreeinclude").write_text(
            "# secrets\n.env\nmissing.txt\n", encoding="utf-8")
        (self.repo / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
        wt = self.repo / "wt"
        wt.mkdir()
        copied = pool.copy_worktree_includes(self.repo, str(wt))
        self.assertEqual(copied, [".env"])
        self.assertEqual((wt / ".env").read_text(), "TOKEN=abc\n")

    def test_no_include_file_returns_empty(self):
        wt = self.repo / "wt"
        wt.mkdir()
        self.assertEqual(pool.copy_worktree_includes(self.repo, str(wt)), [])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_pool.SeedConfigDirTest tests.test_pool.WorktreeIncludeTest -v`
Expected: FAIL — `AttributeError: module 'scripts.factory.lib.pool' has no attribute 'seed_config_dir'`.

- [ ] **Step 3: Add the two helpers to `lib/pool.py`**

Append to `scripts/factory/lib/pool.py`:

```python
def _worker_home(repo, item_id):
    return paths.item_dir(repo, item_id) / "worker" / "home"


def seed_config_dir(repo, item_id, backend, worktree):
    """Create an isolated per-worker config/home dir and return the env var
    that points a backend CLI at it. This avoids the ~/.claude.json 5+-
    concurrent corruption race and the Codex single-use-refresh-token fleet
    race (design spec §3). For claude, pre-accept onboarding + the worktree
    path's trust dialog so a headless run is never parked by a TTY prompt."""
    home = _worker_home(repo, item_id)
    home.mkdir(parents=True, exist_ok=True)
    if backend == "claude":
        cfg = {
            "hasCompletedOnboarding": True,
            "projects": {
                str(Path(worktree).resolve()): {
                    "hasTrustDialogAccepted": True,
                    "hasCompletedProjectOnboarding": True,
                }
            },
        }
        (home / ".claude.json").write_text(
            json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"CLAUDE_CONFIG_DIR": str(home)}
    if backend == "codex":
        return {"CODEX_HOME": str(home)}
    return {}


def copy_worktree_includes(repo, worktree):
    """Copy gitignored files a worktree needs (e.g. .env) from the repo into
    the worktree, per the .worktreeinclude convention (design spec §7). Blank
    and #-comment lines are skipped; a listed path that does not exist in the
    repo is silently skipped. Returns the entries actually copied."""
    include = Path(repo) / ".worktreeinclude"
    copied = []
    if not include.exists():
        return copied
    for line in include.read_text(encoding="utf-8",
                                  errors="replace").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        src = Path(repo) / entry
        dst = Path(worktree) / entry
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
            copied.append(entry)
        elif src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(entry)
    return copied
```

- [ ] **Step 4: Run the test + full suite to verify green**

Run: `python3 -m unittest tests.test_pool -v`
Expected: PASS (EnsureWorktree + SeedConfigDir + WorktreeInclude).
Run: `python3 -m unittest discover -s tests -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/pool.py tests/test_pool.py
git commit -m "feat(pool): seed isolated config dir (trust pre-accept) + .worktreeinclude copy"
```

---

### Task 8: `pool.provision` + `pool.run_prep` (prep phase + audit events)

**Files:**
- Modify: `scripts/factory/lib/pool.py`
- Test: `tests/test_pool.py`

**Interfaces:**
- Produces: `pool.run_prep(worktree, prep) -> (ok:bool, detail:str)` — runs the prep shell command in the worktree (network on; it is a fixed command, not model-driven), returning success + a truncated output tail.
- Produces: `pool.provision(repo, item_id, backend=None, cfg=None) -> dict` — the §7 prep phase end to end: `ensure_worktree` → `copy_worktree_includes` → `run_prep` (if `workers.prep` set) → `seed_config_dir`. Returns `{"item","backend","prepared":bool,"worktree","created","config_env","includes","reason"?,"detail"?}`. On worktree-create or prep failure: `prepared=False`, `reason="prep_failed"`, and a `prep.failed` audit event is logged; on success a `prep.completed` event is logged. **Never advances the item** — a blocked transition is the caller's job.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pool.py` (new TestCase):

```python
class ProvisionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)
        initrepo.init(self.repo)
        _make_item(self.repo)

    def tearDown(self):
        pool._git(self.repo, "worktree", "prune")
        self.tmp.cleanup()

    def _events(self):
        return [e["event"] for e in logs.read_events(self.repo, "0001-thing")]

    def test_success_prepares_worktree_config_and_logs(self):
        result = pool.provision(self.repo, "0001-thing", backend="claude")
        self.assertTrue(result["prepared"], result)
        self.assertTrue(Path(result["worktree"]).is_dir())
        self.assertIn("CLAUDE_CONFIG_DIR", result["config_env"])
        self.assertIn("prep.completed", self._events())

    def test_worktreeinclude_copied_into_worktree(self):
        (self.repo / ".worktreeinclude").write_text(".env\n", encoding="utf-8")
        (self.repo / ".env").write_text("K=v\n", encoding="utf-8")
        result = pool.provision(self.repo, "0001-thing", backend="claude")
        self.assertIn(".env", result["includes"])
        self.assertTrue((Path(result["worktree"]) / ".env").exists())

    def test_prep_command_runs(self):
        _set_workers(self.repo, {"prep": "echo hi > prepped.txt"})
        result = pool.provision(self.repo, "0001-thing", backend="claude")
        self.assertTrue(result["prepared"])
        self.assertTrue((Path(result["worktree"]) / "prepped.txt").exists())

    def test_prep_failure_reports_prep_failed_and_logs(self):
        _set_workers(self.repo, {"prep": "exit 7"})
        result = pool.provision(self.repo, "0001-thing", backend="claude")
        self.assertFalse(result["prepared"])
        self.assertEqual(result["reason"], "prep_failed")
        self.assertIn("prep.failed", self._events())
        self.assertNotIn("prep.completed", self._events())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_pool.ProvisionTest -v`
Expected: FAIL — `AttributeError: module 'scripts.factory.lib.pool' has no attribute 'provision'`.

- [ ] **Step 3: Add `run_prep` + `provision` to `lib/pool.py`**

Append to `scripts/factory/lib/pool.py`:

```python
def run_prep(worktree, prep):
    """Run the deterministic prep command (deps install, etc.) in the
    worktree. Network is intentionally NOT restricted here — prep is a fixed
    command, not model-driven (design spec §7). Returns (ok, detail-tail)."""
    proc = subprocess.run(prep, cwd=worktree, shell=True,
                          capture_output=True, text=True)
    ok = proc.returncode == 0
    tail = (proc.stdout if ok else (proc.stderr or proc.stdout)) or ""
    return ok, tail[-500:].strip()


def provision(repo, item_id, backend=None, cfg=None):
    """Prepare an item's worktree for a headless worker (design spec §7 prep
    phase): create/reuse the factory/<id> worktree, copy .worktreeinclude
    files, run the configured prep command, and seed an isolated config dir.
    Returns a provisioning report; on failure prepared=False with
    reason='prep_failed'. Does NOT advance the item — the caller blocks it."""
    cfg = cfg or work.worker_config(repo)
    backend = backend or cfg.get("backend") or "claude"
    result = {"item": item_id, "backend": backend, "prepared": False,
              "worktree": None, "created": False, "config_env": {},
              "includes": []}
    try:
        wt, created = ensure_worktree(repo, item_id)
    except PoolError as exc:
        result["reason"] = "prep_failed"
        result["detail"] = str(exc)
        logs.append_event(repo, item_id, "prep.failed",
                          {"reason": "prep_failed", "stage": "implement",
                           "detail": str(exc)[:500]})
        return result
    result["worktree"] = wt
    result["created"] = created
    result["includes"] = copy_worktree_includes(repo, wt)
    prep = cfg.get("prep")
    if prep:
        ok, detail = run_prep(wt, prep)
        if not ok:
            result["reason"] = "prep_failed"
            result["detail"] = detail
            logs.append_event(repo, item_id, "prep.failed",
                              {"reason": "prep_failed", "stage": "implement",
                               "detail": detail[:500]})
            return result
    result["config_env"] = seed_config_dir(repo, item_id, backend, wt)
    result["prepared"] = True
    logs.append_event(repo, item_id, "prep.completed",
                      {"worktree": wt, "prep": prep,
                       "includes": result["includes"]})
    return result
```

- [ ] **Step 4: Run the test + full suite to verify green**

Run: `python3 -m unittest tests.test_pool.ProvisionTest -v`
Expected: PASS (4 tests).
Run: `python3 -m unittest discover -s tests -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/pool.py tests/test_pool.py
git commit -m "feat(pool): provision (worktree + includes + prep + config seed) with audit events"
```

---

### Task 9: `pool.cleanup` + `pool.backoff_delay` + doctor pool params

**Files:**
- Modify: `scripts/factory/lib/pool.py`
- Modify: `scripts/factory/lib/doctor.py` (`worker_readiness`)
- Test: `tests/test_pool.py`, `tests/test_doctor.py`

**Interfaces:**
- Produces: `pool.cleanup(repo, item_id) -> dict` — `git worktree remove --force` + `prune`, then removes the per-worker config home; returns `{"item","removed":bool,"branch_kept":bool,"detail":str}`. The branch ref is intentionally kept (review/verify/ship need it). Idempotent when nothing is there.
- Produces: `pool.backoff_delay(attempt, base_delay, cap=300) -> int` — capped exponential backoff `min(base_delay * 2**attempt, cap)`, `attempt` 0-indexed.
- Extends: `doctor.worker_readiness` gains `"max_parallel"` and `"retry"` so the scheduler skill reads K + backoff params from one `factory doctor --json`.

- [ ] **Step 1: Write the failing pool test**

Append to `tests/test_pool.py` (new TestCase):

```python
class CleanupBackoffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)
        initrepo.init(self.repo)
        _make_item(self.repo)

    def tearDown(self):
        pool._git(self.repo, "worktree", "prune")
        self.tmp.cleanup()

    def test_cleanup_removes_worktree_keeps_branch(self):
        result = pool.provision(self.repo, "0001-thing", backend="claude")
        wt = Path(result["worktree"])
        home = Path(result["config_env"]["CLAUDE_CONFIG_DIR"])
        out = pool.cleanup(self.repo, "0001-thing")
        self.assertTrue(out["removed"])
        self.assertFalse(wt.exists())
        self.assertFalse(home.exists())
        self.assertTrue(out["branch_kept"])
        branch = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet",
             "refs/heads/factory/0001-thing"],
            cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(branch.returncode, 0)

    def test_cleanup_idempotent_when_nothing_to_remove(self):
        out = pool.cleanup(self.repo, "0001-thing")
        self.assertFalse(out["removed"])

    def test_backoff_delay_exponential_and_capped(self):
        self.assertEqual(pool.backoff_delay(0, 20), 20)
        self.assertEqual(pool.backoff_delay(1, 20), 40)
        self.assertEqual(pool.backoff_delay(2, 20), 80)
        self.assertEqual(pool.backoff_delay(10, 20), 300)   # capped
        self.assertEqual(pool.backoff_delay(3, 10, cap=50), 50)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_pool.CleanupBackoffTest -v`
Expected: FAIL — `AttributeError: ... has no attribute 'cleanup'`.

- [ ] **Step 3: Add `cleanup` + `backoff_delay` to `lib/pool.py`**

Append to `scripts/factory/lib/pool.py`:

```python
def cleanup(repo, item_id):
    """Remove an item's headless-worker worktree and per-worker config home.
    The branch ref factory/<id> is KEPT (review/verify/ship operate on it).
    Best-effort + idempotent: a missing/locked worktree yields removed=False
    with the git message in detail, so the caller can decide (design spec
    §14). Never deletes the branch — ship owns that."""
    branch = f"factory/{item_id}"
    target = _registered_worktree(repo, branch) \
        or str(paths.worktree_dir(repo, item_id))
    detail = []
    removed = False
    rm = _git(repo, "worktree", "remove", "--force", target)
    if rm.returncode == 0:
        removed = True
    elif rm.stderr.strip():
        detail.append(rm.stderr.strip())
    _git(repo, "worktree", "prune")
    home = _worker_home(repo, item_id)
    if home.exists():
        shutil.rmtree(home, ignore_errors=True)
    branch_kept = _git(repo, "rev-parse", "--verify", "--quiet",
                       "refs/heads/" + branch).returncode == 0
    return {"item": item_id, "removed": removed, "branch_kept": branch_kept,
            "detail": " ".join(detail)}


def backoff_delay(attempt, base_delay, cap=300):
    """Capped exponential backoff for rate-limit/overload retries (design
    spec §8.4). attempt is 0-indexed: 0→base, 1→2·base, 2→4·base, … ≤ cap."""
    return min(int(base_delay) * (2 ** max(0, int(attempt))), int(cap))
```

- [ ] **Step 4: Run the pool test to verify it passes**

Run: `python3 -m unittest tests.test_pool.CleanupBackoffTest -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Write the failing doctor test**

In `tests/test_doctor.py`, extend `test_worker_readiness_reported` — add these assertions at the end of that method:

```python
        self.assertIn("max_parallel", workers)
        self.assertIn("retry", workers)
        self.assertEqual(workers["max_parallel"], 2)
        self.assertEqual(workers["retry"]["max_attempts"], 3)
```

- [ ] **Step 6: Run to verify it fails**

Run: `python3 -m unittest tests.test_doctor.TestDoctor.test_worker_readiness_reported -v`
Expected: FAIL — `AssertionError: 'max_parallel' not found` in the workers readout.

- [ ] **Step 7: Add the pool params to `doctor.worker_readiness`**

In `scripts/factory/lib/doctor.py`, extend the dict returned by `worker_readiness`:

```python
def worker_readiness(repo):
    cfg = work.worker_config(repo)
    return {
        "enabled": bool(cfg.get("enabled")),
        "backend": cfg.get("backend"),
        "max_parallel": cfg.get("max_parallel"),
        "retry": cfg.get("retry"),
        "claude_cli": shutil.which("claude") is not None,
        "codex_cli": shutil.which("codex") is not None,
        "anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openai_key": bool(os.environ.get("OPENAI_API_KEY")),
    }
```

- [ ] **Step 8: Run the doctor test + full suite to verify green**

Run: `python3 -m unittest tests.test_doctor -v`
Expected: PASS.
Run: `python3 -m unittest discover -s tests -v`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add scripts/factory/lib/pool.py scripts/factory/lib/doctor.py tests/test_pool.py tests/test_doctor.py
git commit -m "feat(pool): cleanup (branch-kept) + backoff_delay; doctor reports max_parallel/retry"
```

---

### Task 10: CLI — `factory provision` + `factory cleanup`

**Files:**
- Modify: `scripts/factory/factory.py` (import `pool`, `cmd_provision`, `cmd_cleanup`, two subparsers)
- Test: `tests/test_cli_pool.py`

**Interfaces:**
- Produces: `factory provision <id> [--backend claude|codex|stub] [--json]` (exit 0 prepared / 1 prep failed or missing item / 2 not a factory repo); `factory cleanup <id> [--json]` (exit 0). Both call `pool` and print a short line or the JSON report.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_pool.py` (new TestCase before the `if __name__` line):

```python
class CliProvisionCleanupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(self.repo, "add", "seed.txt")
        _git(self.repo, "commit", "-q", "-m", "seed")
        self.run_cli("init")
        meta = {"id": "0001-thing", "title": "Thing", "stage": "implement",
                "kind": "backend", "created": "2026-07-03T00:00:00Z",
                "updated": "2026-07-03T00:00:00Z"}
        items.save_item(self.repo, meta, "")

    def tearDown(self):
        subprocess.run(["git", "worktree", "prune"], cwd=self.repo,
                       capture_output=True, text=True)
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(self.repo), *args])
        return code, out.getvalue(), err.getvalue()

    def test_provision_then_cleanup(self):
        code, out, err = self.run_cli("provision", "0001-thing",
                                      "--backend", "claude", "--json")
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        self.assertTrue(report["prepared"])
        self.assertIn("CLAUDE_CONFIG_DIR", report["config_env"])

        code, out, err = self.run_cli("cleanup", "0001-thing", "--json")
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        self.assertTrue(report["removed"])
        self.assertTrue(report["branch_kept"])

    def test_provision_missing_item_exits_one(self):
        code, out, err = self.run_cli("provision", "9999-nope", "--json")
        self.assertEqual(code, 1)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_cli_pool.CliProvisionCleanupTest -v`
Expected: FAIL — argparse `invalid choice: 'provision'` (exit 1) — the subcommands are not registered.

- [ ] **Step 3: Wire `pool` into `factory.py`**

Add `pool` to BOTH import lines (the `sys.path` branch and the relative branch) so each ends `..., paths, cost, work, pool`:

```python
    from scripts.factory.lib import initrepo, items, logs, machine, council, health as health_mod, prune as prune_mod, dispatch, packet as packet_mod, design as design_mod, doctor as doctor_mod, paths, cost, work, pool
```

```python
    from .lib import initrepo, items, logs, machine, council, health as health_mod, prune as prune_mod, dispatch, packet as packet_mod, design as design_mod, doctor as doctor_mod, paths, cost, work, pool
```

Add the two command functions (near `cmd_work`):

```python
def cmd_provision(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        items.load_item(args.repo, args.item)
    except items.ItemError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    result = pool.provision(args.repo, args.item, backend=args.backend)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result.get("prepared"):
        print(f"{args.item} provisioned: {result['worktree']}")
    else:
        print(f"{args.item} prep failed: {result.get('detail', '')}",
              file=sys.stderr)
    return 0 if result.get("prepared") else 1


def cmd_cleanup(args):
    if not _require_factory_repo(args.repo):
        return 2
    result = pool.cleanup(args.repo, args.item)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        state = "cleaned" if result["removed"] else "nothing to remove"
        kept = " (branch kept)" if result["branch_kept"] else ""
        print(f"{args.item} {state}{kept}")
    return 0
```

Register the subparsers in `main()` (near the `work` subparser):

```python
    p = sub.add_parser("provision",
                       help="prepare an item's worktree for a headless worker")
    p.add_argument("item")
    p.add_argument("--backend", choices=["claude", "codex", "stub"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_provision)

    p = sub.add_parser("cleanup",
                       help="remove an item's worker worktree (branch kept)")
    p.add_argument("item")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cleanup)
```

- [ ] **Step 4: Run the test + full suite to verify green**

Run: `python3 -m unittest tests.test_cli_pool -v`
Expected: PASS (CliNextCount + CliProvisionCleanup).
Run: `python3 -m unittest discover -s tests -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/factory.py tests/test_cli_pool.py
git commit -m "feat(pool): factory provision + factory cleanup CLI"
```

---

### Task 11: scheduler skill + wiring + coherence guard

**Files:**
- Create: `skills/factory-workers/SKILL.md`
- Modify: `skills/factory-dispatch/SKILL.md`
- Modify: `skills/factory-autopilot/SKILL.md`
- Modify: `skills/capabilities/SKILL.md`
- Modify: `skills/capabilities/references/headless-workers.md`
- Modify: `tests/test_plugin_coherence.py`

**Interfaces:** none (prose + a drift-guard test).

- [ ] **Step 1: Write the failing coherence test**

Append a method to `TestPluginCoherence` in `tests/test_plugin_coherence.py`:

```python
    def test_headless_scheduler_wiring_present(self):
        # the Layer-2 pool skill exists, the dispatcher cites it, and the
        # reference doc documents the provisioning verbs.
        self.assertIn("factory-workers", skill_names())
        disp = read(ROOT / "skills/factory-dispatch/SKILL.md")
        self.assertIn("factory-workers", disp)
        ref = read(ROOT / "skills/capabilities/references/headless-workers.md")
        self.assertIn("factory provision", ref)
        self.assertIn("factory cleanup", ref)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_plugin_coherence.TestPluginCoherence.test_headless_scheduler_wiring_present -v`
Expected: FAIL — `AssertionError: 'factory-workers' not found` (the skill does not exist yet).

- [ ] **Step 3: Create the `factory-workers` skill**

Create `skills/factory-workers/SKILL.md`:

```markdown
---
name: factory-workers
description: Use when the headless-worker capability is present and several independent items are ready to implement - runs a bounded parallel pool of out-of-process workers, one per worktree, then advances each through the existing gates
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

You are the Layer-2 scheduler: a bounded pool that keeps **K** headless workers busy across **independent** items, each in its own `factory/<id>` worktree, then advances each result through Factory's *existing* gates. You do the loop/pacing/collect-advance; the engine primitives (`factory next -n`, `factory provision`, `factory work`, `factory cleanup`) do the mechanics. You never type code and never lower a gate — worker output is untrusted until it clears `review` + `verify` + green tests exactly like a subagent's.

Only run this when the **Headless worker** capability (capabilities skill) is present: `workers.enabled` true and the backend CLI + key are ready (`factory doctor --json` → `workers`). Without it, implementation stays on factory-implement's in-process path — do not run a pool.

## Read the pool budget

`factory doctor --json` → `workers`: `max_parallel` (**K**), `backend`, and `retry` (`max_attempts`, `base_delay_seconds`). Keep K small (default 2) — every worker drains **one** shared org rate-limit bucket (design spec §3), so this is a rate budget, not a CPU budget.

## The loop

1. **Reclaim stale worktrees.** For any item already at `done` or `blocked` that still has a worktree, `factory cleanup <id>`. This also clears a locked/dirty tree from a crashed prior run before it is reused.
2. **Select.** `factory next -n K --json`. Keep only items whose `stage == "implement"` — the pool builds implementation in parallel; items at other stages flow through factory-dispatch's normal one-at-a-time path. If none are at implement, there is no pool work this pass — return to the dispatcher.
3. **Provision, staggered.** For each selected item, `factory provision <id> --backend <backend> --json`. Launch them a few seconds apart — **ramp, don't burst** (acceleration-limit 429s fire on sharp usage ramps). Read `worktree` and `config_env` from each report.
   - If `prepared` is false (`reason: prep_failed`): `factory advance <id> blocked --reason "prep failed: <detail>"` then `factory packet <id>`. A worker cannot fix a broken prep offline — never dispatch one. Do not count this against a retry budget.
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
```

- [ ] **Step 4: Cite `factory-workers` from factory-dispatch**

In `skills/factory-dispatch/SKILL.md`, replace the `## Capabilities` section (currently one line) with:

```markdown
## Capabilities

For any fan-out or design rendering, follow the capabilities skill.

**Parallel implement pool.** When the **Headless worker** capability is present (capabilities skill) and more than one actionable item is at `implement`, you MAY hand implementation to the `factory-workers` skill instead of running factory-implement one item at a time: it runs a bounded pool of out-of-process workers (one worktree each) and advances each through the same `review` gate. It is an opportunistic throughput upgrade — the top-K items are assumed independent (worktree isolation makes a wrong guess a merge conflict at `ship`, not corruption). Without the capability, or with only one item at `implement`, stay on the normal per-item path.
```

- [ ] **Step 5: Allow the pool in factory-autopilot**

In `skills/factory-autopilot/SKILL.md`, at the end of the `## 2. Run the loop` section, append:

```markdown

When the **Headless worker** capability is present and several items sit at `implement`, the loop MAY use the `factory-workers` pool to build them in parallel within this run's budget — the same budget checkpoints (§4) and gate-respect rules (§3) apply to pooled work, and the pool's own `auth`-stop and two-strikes-then-blocked rules fold into autopilot's existing safety net. Autopilot gains no new authority from the pool; it still never answers a human gate.
```

- [ ] **Step 6: Extend the capabilities "Headless worker" row**

In `skills/capabilities/SKILL.md`, replace the `Headless worker` table row's "With it" cell so the row reads:

```
| Headless worker | `workers.enabled` true in `.factory/config.json` and the configured backend CLI (`claude`/`codex`) resolvable on `PATH` with its key env var set (`factory doctor` reports this) | Dispatch an item's implementation out-of-process via `factory work <id>`; with several independent items at `implement`, run the bounded parallel pool (the `factory-workers` skill) → see references/headless-workers.md | Today's in-process `superpowers:subagent-driven-development` path, unchanged |
```

- [ ] **Step 7: Document the scheduler in the reference doc**

Append to `skills/capabilities/references/headless-workers.md`:

```markdown

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
  so `review`/`verify`/`ship` still operate on `factory/<id>`.

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
```

- [ ] **Step 8: Run the coherence test + full suite to verify green**

Run: `python3 -m unittest tests.test_plugin_coherence -v`
Expected: PASS (existing guards + `test_headless_scheduler_wiring_present`). The `test_every_reference_doc_link_resolves` guard still passes (the reference doc `factory-workers` links, `references/workflow-fanout.md`, already exists).
Run: `python3 -m unittest discover -s tests -v`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add skills/factory-workers/SKILL.md skills/factory-dispatch/SKILL.md skills/factory-autopilot/SKILL.md skills/capabilities/SKILL.md skills/capabilities/references/headless-workers.md tests/test_plugin_coherence.py
git commit -m "feat(pool): factory-workers scheduler skill + dispatch/autopilot/capabilities wiring"
```

---

## Notes for the executor

- **Run the full suite after every task**, not just the task's own tests: `python3 -m unittest discover -s tests -v` from the repo root.
- **The pool is skill-driven, not a daemon.** No Python loop schedules workers; `pool.py` only exposes mechanics (select/provision/cleanup/backoff) that `factory-workers` (prose) orchestrates. Do not add a long-running scheduler process — that would be the rejected Approach B.
- **Never advance a stage from Python.** `pool.provision`/`pool.cleanup` log audit events and return status; the skill owns every `factory advance` (blocked, review). This mirrors `factory work`.
- **`.factory/worktrees/<id>` nesting is verified.** `git worktree add` under a gitignored `.factory/` works, the main tree stays clean, and `git worktree remove --force` + `prune` keeps the branch. Tests that create worktrees must `git worktree prune` in `tearDown` before `TemporaryDirectory.cleanup()` (the porcelain admin entries otherwise point at a deleted temp dir; prune is harmless if already clean).
- **Prep is deterministic + offline-testable.** Tests set `workers.prep` to `true`/`echo`/`exit N` — no network, no real dep install. The real prep command (`npm ci`, `pip install -e .`) runs network-on only in live use.
- **Auth exit-code split:** `run_work` returns exit 1 for `reason == "auth"` and exit 3 for every other worker failure. The scheduler treats exit 1/auth as a pool-wide stop, exit 3 as per-item retry/backoff/block. Keep this split — it is why a fleet does not burn K workers on one bad key.
- **Do not stage `README.md`** in any commit (pre-existing unstaged modification).

## Self-Review

- **Spec §8 (scheduler responsibilities):** select K → Task 1 (`next_items`) + Task 10 (`next -n`); provision worktree + prep + isolated config dir → Tasks 6–8, 10; launch `factory work` per item → Phase A + skill (Task 11); pace/stagger/backoff → Task 9 (`backoff_delay`) + Task 11 (skill); collect + advance (review / two-strikes-blocked) → Task 11 (skill, using existing `factory advance`); cleanup → Task 9 (`cleanup`) + Task 10 (CLI) + Task 11 (skill). Covered.
- **Spec §7 (prep + network posture):** prep phase (copy `.worktreeinclude`, run prep, network on) → Tasks 7–8; worker network-off is Phase A's backend argv (unchanged); per-worker config dir with pre-accepted trust → Task 7. Covered.
- **Phase-A tracked deferrals:** (a) auth-reason + exit 1 → Task 5; (b) `worker_config` isinstance guard → Task 3; (c) `duration_s` → Task 4; (d) git-status enum widening → Task 2. All covered.
- **Spec §12 (probe) / §13 (surfaces):** capabilities row extended + reference doc + factory-workers skill + dispatch/autopilot wiring + coherence guard → Task 11. Covered.
- **Trust invariant (§9):** no task touches a gate; the pool only calls the existing `factory advance <id> review` and the existing two-strikes `factory advance <id> blocked`. Worker output flows through review/verify/green-tests unchanged. Covered.
- **Placeholder scan:** every code/test/prose step carries its full content; no TBD/TODO. OK.
- **Type consistency:** `provision` returns `{prepared, worktree, config_env, includes, reason?, detail?}` — the CLI (Task 10) and the skill (Task 11) both read exactly those keys; `cleanup` returns `{removed, branch_kept, detail}` — matched by CLI + tests; `next_items(repo, n)` list return — matched by CLI array output + tests; `backoff_delay(attempt, base_delay, cap=300)` — matched by test + skill prose. OK.
