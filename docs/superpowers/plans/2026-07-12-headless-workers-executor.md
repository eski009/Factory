# Headless Workers — Phase A (Executor) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `factory work <id>` engine command that runs one headless coding-agent worker (backends: `claude`, `codex`, plus a test-only `stub`) inside an item's worktree, captures a normalized `result.json`, and logs measured cost + `implement.completed` — the out-of-process executor that gives Factory context economy.

**Architecture:** A new stdlib-only `scripts/factory/lib/work.py` holds the backend adapter, a git-first result normalizer, and the `run_work` orchestration; `factory.py` grows a `cmd_work` + `work` subparser. Everything is testable without a live CLI via an in-process `stub` backend that edits a file and commits in a temp git repo. Trust is unchanged — `factory work` produces the same branch + `implement.completed` event the existing `implement→review` gate already checks, so worker output flows through Factory's existing review/verify/tests gates untouched.

**Tech Stack:** Python 3.11 standard library only (`argparse`, `json`, `os`, `re`, `shutil`, `subprocess`, `pathlib`). No third-party dependencies. Tests: `unittest`.

**Design source:** `docs/superpowers/specs/2026-07-12-headless-workers-design.md` (Approach C, Layer 1; D1 assume-independent; D4 autonomous-within-worktree). This plan is **Phase A** (the executor). Phase B (the parallel scheduler) is a separate plan.

## Global Constraints

- **Python 3.11, standard library only.** No new third-party imports, no `requirements` file. (Every import must be one of: `argparse json os re shutil subprocess pathlib datetime` or an internal `scripts.factory.lib.*` module.)
- **Test runner:** `python3 -m unittest discover -s tests -v`, run from the repo root. Tests are `unittest.TestCase` subclasses using `tempfile.TemporaryDirectory()` in `setUp`/`tearDown`. There is no pytest, no `conftest.py`, no fixtures.
- **Schemas** live in `schemas/` named `<name>.schema.json`, loaded via `initrepo.load_schema("<name>")`. The validator (`scripts/factory/lib/validate.py`) supports **only** `type, enum, required, properties, additionalProperties:false, items, pattern, minLength, minimum`. **Do not use** `maximum`, `maxLength`, `$ref`, `oneOf`, `anyOf`, or `null` types — they are silently unsupported.
- **`config.schema.json` has `additionalProperties: false` at the top level** — a new `workers` key MUST be added to its `properties` or config validation rejects it.
- **Event shape is `{"event": <str>, "ts": <str>, "data": <obj?>}`.** Always append via `logs.append_event(repo, item_id, event, data)`. Never write `type`/`timestamp`.
- **Items are `item.md` frontmatter.** Load via `items.load_item(repo, item_id) -> (meta, body)`; the stage is `meta["stage"]`.
- **CLI exit-code convention:** `0` ok, `1` usage/internal error, `2` gate/precondition refusal, `3` worker attempted-but-failed (typed `reason` in the result). CLI command functions **return an int** and print errors to `sys.stderr` — they never call `sys.exit` or raise to the top.
- **`.factory/` runtime state is gitignored.** It does not appear in git worktrees; ticking `plan.md` checkboxes is a plain file write, not a commit.
- **A measured `spend` event must satisfy `initrepo.spend_event_errors`:** top-level `event:"spend"`, `data.provenance == "measured"`, and `data.tokens` present with at least one of `input`/`output`/`total`. A proxy event omits `tokens` entirely.

## File Structure

- **Create** `scripts/factory/lib/work.py` — the entire executor: config reader, brief builder, git-state capture, backend adapter (stub/claude/codex), normalizer, `run_work`. One focused module; grows task-by-task.
- **Create** `schemas/result.schema.json` — the normalized worker-result packet.
- **Create** `skills/capabilities/references/headless-workers.md` — flags/auth/gotchas reference (prose).
- **Create** `tests/test_work.py` — unit tests for `lib/work.py` (config, brief, git, normalize, run_work) via the stub backend.
- **Create** `tests/test_work_backends.py` — unit tests for the claude/codex argv builders + output parsers (no live calls).
- **Create** `tests/test_cli_work.py` — in-process `factory.main(["work", ...])` end-to-end via the stub.
- **Modify** `schemas/config.schema.json` — add the optional `workers` object.
- **Modify** `scripts/factory/factory.py` — import `work`, add `cmd_work`, register the `work` subparser.
- **Modify** `scripts/factory/lib/doctor.py` — add headless-worker readiness to the doctor readout.
- **Modify** `skills/factory-implement/SKILL.md` — one branch at step 3 for the headless path.
- **Modify** `skills/capabilities/SKILL.md` — add the "Headless worker" probe row.
- **Modify** `tests/test_doctor.py` — assert the workers readiness fields.
- **Modify** `tests/test_plugin_coherence.py` — a drift guard for the new skill wiring.

---

### Task 1: `workers` config schema + `worker_config` reader

**Files:**
- Modify: `schemas/config.schema.json` (add `workers` to `properties`)
- Create: `scripts/factory/lib/work.py`
- Test: `tests/test_work.py`

**Interfaces:**
- Produces: `work.DEFAULTS` (dict), `work.REASONS` (tuple), `work.WorkError` (Exception), `work.worker_config(repo) -> dict` (the `workers` config block merged over `DEFAULTS`; nested `retry`/`codex` merged one level deep).

- [ ] **Step 1: Write the failing test**

Create `tests/test_work.py`:

```python
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, work


def _init_repo():
    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    initrepo.init(repo)
    return tmp, repo


def _set_workers(repo, workers):
    cfg_path = repo / ".factory" / "config.json"
    data = json.loads(cfg_path.read_text())
    data["workers"] = workers
    cfg_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")


class WorkerConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.repo = _init_repo()

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_when_absent(self):
        cfg = work.worker_config(self.repo)
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["backend"], "claude")
        self.assertEqual(cfg["max_parallel"], 2)
        self.assertEqual(cfg["network"], "off")
        self.assertEqual(cfg["retry"]["max_attempts"], 3)
        self.assertEqual(cfg["codex"]["sandbox"], "workspace-write")

    def test_overrides_merge_over_defaults(self):
        _set_workers(self.repo, {"enabled": True, "backend": "codex",
                                 "retry": {"max_attempts": 5}})
        cfg = work.worker_config(self.repo)
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["backend"], "codex")
        self.assertEqual(cfg["retry"]["max_attempts"], 5)
        # unspecified nested key keeps its default
        self.assertEqual(cfg["retry"]["base_delay_seconds"], 20)

    def test_valid_workers_block_passes_validation(self):
        _set_workers(self.repo, {"enabled": True, "backend": "claude",
                                 "max_parallel": 3, "network": "off",
                                 "models": {"claude": "claude-sonnet-5"}})
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_bad_backend_enum_rejected(self):
        _set_workers(self.repo, {"backend": "gpt"})
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("backend" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_work -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.factory.lib.work'` (and, once the module exists but the schema doesn't, `test_valid_workers_block_passes_validation` would fail with an "unexpected property workers" error).

- [ ] **Step 3: Add `workers` to the config schema**

In `schemas/config.schema.json`, add this property inside the top-level `"properties"` object (e.g. after the `"research"` block). Keep within the validator subset — no `maximum`, no `null`:

```json
    "workers": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "enabled": {"type": "boolean"},
        "backend": {"type": "string", "enum": ["claude", "codex"]},
        "max_parallel": {"type": "integer", "minimum": 1},
        "timeout_seconds": {"type": "integer", "minimum": 1},
        "network": {"type": "string", "enum": ["on", "off"]},
        "prep": {"type": "string", "minLength": 1},
        "test_command": {"type": "string", "minLength": 1},
        "models": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "claude": {"type": "string", "minLength": 1},
            "codex": {"type": "string", "minLength": 1}
          }
        },
        "codex": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "sandbox": {"type": "string",
                        "enum": ["workspace-write", "danger-full-access"]}
          }
        },
        "retry": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "max_attempts": {"type": "integer", "minimum": 1},
            "base_delay_seconds": {"type": "integer", "minimum": 0}
          }
        }
      }
    }
```

- [ ] **Step 4: Create `lib/work.py` with the config reader**

Create `scripts/factory/lib/work.py`:

```python
"""factory work: run one headless coding-agent worker in an item's git
worktree and capture a normalized result. Backends: claude (headless),
codex (exec), stub (test-only, in-process). Python stdlib only.

run_work / cmd_work exit codes:
  0  worker succeeded (result status=done, implement.completed logged)
  1  usage/internal error (bad args, missing item, unresolvable worktree,
     backend CLI unavailable, invalid result)
  2  precondition refusal (item not at stage implement, or no unticked tasks)
  3  worker attempted but did not succeed (result status=failed|blocked;
     the typed `reason` tells a scheduler whether to retry or block)
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import initrepo, items, logs, paths, validate


class WorkError(Exception):
    pass


DEFAULTS = {
    "enabled": False,
    "backend": "claude",
    "max_parallel": 2,
    "timeout_seconds": 1800,
    "network": "off",
    "retry": {"max_attempts": 3, "base_delay_seconds": 20},
    "codex": {"sandbox": "workspace-write"},
}

REASONS = ("crash", "timeout", "no_changes", "red_tests",
           "rate_limited", "auth", "blocked", "prep_failed")


def worker_config(repo):
    """The effective `workers` config: the repo config.json 'workers' block
    merged over DEFAULTS, with 'retry'/'codex' merged one level deep."""
    block = {}
    p = paths.config_path(repo)
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            if isinstance(raw, dict) and isinstance(raw.get("workers"), dict):
                block = raw["workers"]
        except json.JSONDecodeError:
            block = {}
    merged = dict(DEFAULTS)
    merged["retry"] = dict(DEFAULTS["retry"])
    merged["codex"] = dict(DEFAULTS["codex"])
    for key, value in block.items():
        if key in ("retry", "codex") and isinstance(value, dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_work -v`
Expected: PASS (4 tests). Then run the full suite to confirm no config regression: `python3 -m unittest discover -s tests -v` — expected all green.

- [ ] **Step 6: Commit**

```bash
git add schemas/config.schema.json scripts/factory/lib/work.py tests/test_work.py
git commit -m "feat(work): workers config schema + worker_config reader"
```

---

### Task 2: brief builder

**Files:**
- Modify: `scripts/factory/lib/work.py`
- Test: `tests/test_work.py`

**Interfaces:**
- Consumes: `paths.item_dir`, `work.WorkError`.
- Produces: `work.unticked_tasks(plan_text) -> list[str]`; `work.build_brief(repo, item_id, worktree) -> str` (reads `.factory/items/<id>/plan.md` + optional `spec.md`; raises `WorkError` if `plan.md` is missing).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_work.py` (add a new TestCase class before the `if __name__` line):

```python
class BriefTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.repo = _init_repo()
        meta = {"id": "0001-thing", "title": "Thing", "stage": "implement",
                "kind": "backend", "created": "2026-07-03T00:00:00Z",
                "updated": "2026-07-03T00:00:00Z"}
        items.save_item(self.repo, meta, "")
        d = self.repo / ".factory" / "items" / "0001-thing"
        (d / "plan.md").write_text(
            "# Plan\n- [ ] Add the widget\n- [x] Already done\n- [ ] Wire it up\n",
            encoding="utf-8")
        (d / "spec.md").write_text("Acceptance: widget renders.\n",
                                   encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_unticked_tasks_extracts_only_open(self):
        text = "- [ ] one\n- [x] two\n  - [ ] three\nnot a task\n"
        self.assertEqual(work.unticked_tasks(text), ["one", "three"])

    def test_build_brief_includes_open_tasks_and_spec(self):
        brief = work.build_brief(self.repo, "0001-thing", "/tmp/wt")
        self.assertIn("Add the widget", brief)
        self.assertIn("Wire it up", brief)
        self.assertNotIn("Already done", brief)
        self.assertIn("Acceptance: widget renders.", brief)
        self.assertIn("/tmp/wt", brief)

    def test_build_brief_missing_plan_raises(self):
        (self.repo / ".factory/items/0001-thing/plan.md").unlink()
        with self.assertRaises(work.WorkError):
            work.build_brief(self.repo, "0001-thing", "/tmp/wt")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_work.BriefTest -v`
Expected: FAIL with `AttributeError: module 'scripts.factory.lib.work' has no attribute 'unticked_tasks'`.

- [ ] **Step 3: Add the brief builder to `lib/work.py`**

Append to `scripts/factory/lib/work.py`:

```python
_TASK_RE = re.compile(r"^\s*-\s*\[ \]\s*(.+?)\s*$")


def unticked_tasks(plan_text):
    """Text of each unchecked `- [ ]` task line in a plan (in order)."""
    out = []
    for line in plan_text.splitlines():
        match = _TASK_RE.match(line)
        if match:
            out.append(match.group(1))
    return out


def build_brief(repo, item_id, worktree):
    """Compose the worker prompt from the item's plan.md + spec.md."""
    item_path = paths.item_dir(repo, item_id)
    plan_path = item_path / "plan.md"
    if not plan_path.exists():
        raise WorkError(f"{item_id}: plan.md missing")
    tasks = unticked_tasks(plan_path.read_text(encoding="utf-8"))
    spec_path = item_path / "spec.md"
    spec_text = (spec_path.read_text(encoding="utf-8")
                 if spec_path.exists() else "")
    lines = [
        f"You are a headless implementer for work item {item_id}.",
        f"Working directory (git worktree on branch factory/{item_id}): "
        f"{worktree}",
        "Implement every task below. Follow TDD, run the tests named in the "
        "plan, and commit your work to the current branch as you go. Do not "
        "modify files outside this working directory.",
        "",
        "## Tasks (from plan.md)",
    ]
    for i, task in enumerate(tasks, 1):
        lines.append(f"{i}. {task}")
    if spec_text.strip():
        lines += ["", "## Spec (acceptance criteria)", spec_text.strip()]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_work.BriefTest -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/work.py tests/test_work.py
git commit -m "feat(work): build worker brief from plan + spec"
```

---

### Task 3: git-state capture

**Files:**
- Modify: `scripts/factory/lib/work.py`
- Test: `tests/test_work.py`

**Interfaces:**
- Produces: `work.git_head(worktree) -> str` (current HEAD sha, or `""`); `work.git_state(worktree, base_sha) -> {"commits": list[str], "files_changed": list[{"path","change"}], "clean": bool}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_work.py`:

```python
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


class GitStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_head_returns_sha(self):
        self.assertRegex(work.git_head(self.repo), r"^[0-9a-f]{7,40}$")

    def test_state_reports_new_commit_and_files(self):
        base = work.git_head(self.repo)
        (self.repo / "new.txt").write_text("x\n", encoding="utf-8")
        _git(self.repo, "add", "new.txt")
        _git(self.repo, "commit", "-q", "-m", "add new")
        state = work.git_state(self.repo, base)
        self.assertEqual(len(state["commits"]), 1)
        self.assertIn({"path": "new.txt", "change": "A"},
                      state["files_changed"])
        self.assertTrue(state["clean"])

    def test_state_detects_dirty_tree(self):
        base = work.git_head(self.repo)
        (self.repo / "seed.txt").write_text("changed\n", encoding="utf-8")
        state = work.git_state(self.repo, base)
        self.assertFalse(state["clean"])
        self.assertEqual(state["commits"], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_work.GitStateTest -v`
Expected: FAIL with `AttributeError: module 'scripts.factory.lib.work' has no attribute 'git_head'`.

- [ ] **Step 3: Add git-state helpers to `lib/work.py`**

Append to `scripts/factory/lib/work.py`:

```python
def _git(worktree, *args):
    return subprocess.run(["git", *args], cwd=worktree,
                          capture_output=True, text=True)


def git_head(worktree):
    result = _git(worktree, "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else ""


def git_state(worktree, base_sha):
    """Commits + changed files on the worktree since base_sha, plus whether
    the working tree is clean."""
    commits, files = [], []
    if base_sha:
        rev = _git(worktree, "rev-list", f"{base_sha}..HEAD")
        if rev.returncode == 0:
            commits = [c for c in rev.stdout.split() if c]
        diff = _git(worktree, "diff", "--name-status", base_sha, "HEAD")
        if diff.returncode == 0:
            for line in diff.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    files.append({"change": parts[0][:1], "path": parts[-1]})
    status = _git(worktree, "status", "--porcelain")
    clean = status.returncode == 0 and status.stdout.strip() == ""
    return {"commits": commits, "files_changed": files, "clean": clean}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_work.GitStateTest -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/work.py tests/test_work.py
git commit -m "feat(work): git-first worktree state capture"
```

---

### Task 4: `result.schema.json` + stub backend + normalizer

**Files:**
- Create: `schemas/result.schema.json`
- Modify: `scripts/factory/lib/work.py`
- Test: `tests/test_work.py`

**Interfaces:**
- Consumes: `git_state` output, `initrepo.load_schema`, `validate.validate`.
- Produces:
  - `work.BACKENDS` (dict; `"stub"` registered now, `"claude"`/`"codex"` added in Tasks 7–8).
  - `work._parse_output(backend, raw) -> {"status","reason","usage","summary","cost_usd"}`.
  - `work.normalize(item_id, backend, model, branch, gstate, parsed, test_result, worker_log) -> dict` (validates against `schemas/result.schema.json`).
  - RawRun shape: `{"exit_code": int, "stdout": str, "stderr": str, "timed_out": bool}`.
  - Stub behavior via env `FACTORY_WORK_STUB` (JSON): `{"exit_code","commit","file","content","message","status","reason","usage","payload"}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_work.py`:

```python
class NormalizeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)

    def tearDown(self):
        os.environ.pop("FACTORY_WORK_STUB", None)
        self.tmp.cleanup()

    def test_stub_success_normalizes_to_done(self):
        base = work.git_head(self.repo)
        raw = work.BACKENDS["stub"]("brief", self.repo, None, 60, "off",
                                    "workspace-write", dict(os.environ))
        parsed = work._parse_output("stub", raw)
        gstate = work.git_state(self.repo, base)
        result = work.normalize("0001-thing", "stub", None,
                                "factory/0001-thing", gstate, parsed, None,
                                "items/0001-thing/worker/worker.log")
        self.assertEqual(result["status"], "done")
        self.assertEqual(len(result["commits"]), 1)
        self.assertEqual(result["usage"]["provenance"], "measured")
        # produced result must validate against the schema
        errors = validate.validate(result, initrepo.load_schema("result"),
                                   "result")
        self.assertEqual(errors, [])

    def test_stub_failure_normalizes_to_failed(self):
        os.environ["FACTORY_WORK_STUB"] = json.dumps(
            {"exit_code": 1, "commit": False, "reason": "crash"})
        base = work.git_head(self.repo)
        raw = work.BACKENDS["stub"]("brief", self.repo, None, 60, "off",
                                    "workspace-write", dict(os.environ))
        parsed = work._parse_output("stub", raw)
        gstate = work.git_state(self.repo, base)
        result = work.normalize("0001-thing", "stub", None,
                                "factory/0001-thing", gstate, parsed, None,
                                "items/0001-thing/worker/worker.log")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "crash")

    def test_done_without_commit_becomes_no_changes(self):
        os.environ["FACTORY_WORK_STUB"] = json.dumps(
            {"exit_code": 0, "commit": False})
        base = work.git_head(self.repo)
        raw = work.BACKENDS["stub"]("brief", self.repo, None, 60, "off",
                                    "workspace-write", dict(os.environ))
        parsed = work._parse_output("stub", raw)
        gstate = work.git_state(self.repo, base)
        result = work.normalize("0001-thing", "stub", None,
                                "factory/0001-thing", gstate, parsed, None,
                                "items/0001-thing/worker/worker.log")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "no_changes")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_work.NormalizeTest -v`
Expected: FAIL — `KeyError: 'stub'` (BACKENDS undefined) and a missing `schemas/result.schema.json`.

- [ ] **Step 3: Create `schemas/result.schema.json`**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "work-result",
  "type": "object",
  "required": ["id", "status", "backend", "branch"],
  "additionalProperties": false,
  "properties": {
    "id": {"type": "string", "pattern": "^[0-9]{4}-[a-z0-9-]+$"},
    "status": {"type": "string", "enum": ["done", "blocked", "failed"]},
    "reason": {"type": "string",
               "enum": ["crash", "timeout", "no_changes", "red_tests",
                        "rate_limited", "auth", "blocked", "prep_failed"]},
    "backend": {"type": "string", "enum": ["claude", "codex", "stub"]},
    "model": {"type": "string"},
    "branch": {"type": "string", "minLength": 1},
    "commits": {"type": "array", "items": {"type": "string"}},
    "files_changed": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "path": {"type": "string"},
          "change": {"type": "string",
                     "enum": ["A", "M", "D", "R", "C", "T"]}
        }
      }
    },
    "test": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "command": {"type": "string"},
        "passed": {"type": "boolean"},
        "summary": {"type": "string"}
      }
    },
    "usage": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "input": {"type": "integer", "minimum": 0},
        "output": {"type": "integer", "minimum": 0},
        "total": {"type": "integer", "minimum": 0},
        "provenance": {"type": "string", "enum": ["measured", "proxy"]}
      }
    },
    "cost_usd_estimate": {"type": "number", "minimum": 0},
    "duration_s": {"type": "integer", "minimum": 0},
    "summary": {"type": "string"},
    "worker_log": {"type": "string"}
  }
}
```

- [ ] **Step 4: Add the stub backend, parser dispatch, and normalizer to `lib/work.py`**

Append to `scripts/factory/lib/work.py`:

```python
# ---- backends: a backend is fn(brief, worktree, model, timeout, network,
#      sandbox, env) -> RawRun {exit_code, stdout, stderr, timed_out} ----

def _stub_run(brief, worktree, model, timeout, network, sandbox, env):
    """Test-only in-process backend. Simulates an agent: optionally writes a
    file and commits it, then returns a canned RawRun. Controlled by the
    FACTORY_WORK_STUB env var (JSON); defaults to one successful commit."""
    spec = {}
    if env.get("FACTORY_WORK_STUB"):
        spec = json.loads(env["FACTORY_WORK_STUB"])
    exit_code = spec.get("exit_code", 0)
    if spec.get("commit", exit_code == 0):
        fname = spec.get("file", "worker-change.txt")
        (Path(worktree) / fname).write_text(
            spec.get("content", "stub change\n"), encoding="utf-8")
        _git(worktree, "add", fname)
        _git(worktree, "commit", "-q", "-m",
             spec.get("message", "stub: implement"))
    payload = spec.get("payload", {
        "status": spec.get("status", "done" if exit_code == 0 else "failed"),
        "reason": spec.get("reason"),
        "message": spec.get("message", "stub done"),
        "usage": spec.get("usage", {"input": 100, "output": 50, "total": 150}),
    })
    return {"exit_code": exit_code, "stdout": json.dumps(payload),
            "stderr": spec.get("stderr", ""), "timed_out": False}


def _stub_parse(raw):
    try:
        obj = json.loads(raw.get("stdout") or "{}")
    except json.JSONDecodeError:
        obj = {}
    if raw.get("timed_out"):
        return {"status": "failed", "reason": "timeout", "usage": {},
                "summary": "", "cost_usd": None}
    if raw["exit_code"] != 0:
        return {"status": "failed", "reason": obj.get("reason", "crash"),
                "usage": obj.get("usage", {}),
                "summary": obj.get("message", ""), "cost_usd": None}
    return {"status": obj.get("status", "done"), "reason": obj.get("reason"),
            "usage": obj.get("usage", {}), "summary": obj.get("message", ""),
            "cost_usd": obj.get("cost_usd")}


BACKENDS = {"stub": _stub_run}


def _parse_output(backend, raw):
    if backend == "claude":
        return _claude_parse(raw)
    if backend == "codex":
        return _codex_parse(raw)
    return _stub_parse(raw)


def normalize(item_id, backend, model, branch, gstate, parsed, test_result,
              worker_log):
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
        "summary": (parsed.get("summary") or "")[:2000],
        "worker_log": worker_log,
    }
    if model:
        result["model"] = model
    if reason:
        result["reason"] = reason
    if measured:
        result["usage"] = {k: int(usage.get(k, 0))
                           for k in ("input", "output", "total")}
        result["usage"]["provenance"] = "measured"
    if test_result is not None:
        result["test"] = test_result
    if parsed.get("cost_usd") is not None:
        result["cost_usd_estimate"] = parsed["cost_usd"]
    return result
```

Note: `_parse_output` references `_claude_parse`/`_codex_parse`, added in Tasks 7–8. They are only called when `backend in ("claude","codex")`; the stub path never reaches them, so tests in this task pass.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_work.NormalizeTest -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add schemas/result.schema.json scripts/factory/lib/work.py tests/test_work.py
git commit -m "feat(work): result schema, stub backend, git-first normalizer"
```

---

### Task 5: `run_work` orchestration

**Files:**
- Modify: `scripts/factory/lib/work.py`
- Test: `tests/test_work.py`

**Interfaces:**
- Consumes: everything above, plus `items.load_item`, `logs.append_event`.
- Produces:
  - `work.resolve_worktree(repo, item_id) -> str|None`
  - `work.run_work(repo, item_id, backend=None, model=None, timeout=None, network=None, worktree=None) -> (int, dict)` — returns `(exit_code, result_or_error)`. On success writes `.factory/items/<id>/worker/result.json`, ticks `plan.md`, logs a measured/proxy `spend` event + `implement.completed`. On worker failure logs `spend` + `implement.failed`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_work.py`:

```python
class RunWorkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _init_git_repo(self.repo)
        initrepo.init(self.repo)
        _git(self.repo, "checkout", "-q", "-b", "factory/0001-thing")
        meta = {"id": "0001-thing", "title": "Thing", "stage": "implement",
                "kind": "backend", "created": "2026-07-03T00:00:00Z",
                "updated": "2026-07-03T00:00:00Z"}
        items.save_item(self.repo, meta, "")
        d = self.repo / ".factory/items/0001-thing"
        (d / "plan.md").write_text("- [ ] Do the thing\n", encoding="utf-8")
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        os.environ.pop("FACTORY_WORK_STUB", None)
        self.tmp.cleanup()

    def _events(self):
        return [e["event"] for e in logs.read_events(self.repo, "0001-thing")]

    def test_success_logs_completion_and_measured_spend(self):
        code, result = work.run_work(self.repo, "0001-thing", backend="stub",
                                     worktree=str(self.repo))
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "done")
        self.assertTrue((self.repo / ".factory/items/0001-thing/worker/"
                         "result.json").exists())
        self.assertIn("implement.completed", self._events())
        self.assertIn("spend", self._events())
        # plan checkbox ticked
        plan = (self.repo / ".factory/items/0001-thing/plan.md").read_text()
        self.assertIn("- [x] Do the thing", plan)
        # the spend event is measured and rolls up in cost.summarize
        from scripts.factory.lib import cost
        summary = cost.summarize(self.repo, "0001-thing")
        self.assertEqual(summary["measured"]["events"], 1)

    def test_wrong_stage_refused(self):
        d = self.repo / ".factory/items/0001-thing"
        item_md = d / "item.md"
        item_md.write_text(item_md.read_text().replace(
            "stage: implement", "stage: plan"), encoding="utf-8")
        code, result = work.run_work(self.repo, "0001-thing", backend="stub",
                                     worktree=str(self.repo))
        self.assertEqual(code, 2)
        self.assertNotIn("implement.completed", self._events())

    def test_worker_failure_logs_failed_not_completed(self):
        os.environ["FACTORY_WORK_STUB"] = json.dumps(
            {"exit_code": 1, "commit": False, "reason": "crash"})
        code, result = work.run_work(self.repo, "0001-thing", backend="stub",
                                     worktree=str(self.repo))
        self.assertEqual(code, 3)
        self.assertIn("implement.failed", self._events())
        self.assertNotIn("implement.completed", self._events())

    def test_no_unticked_tasks_refused(self):
        (self.repo / ".factory/items/0001-thing/plan.md").write_text(
            "- [x] done already\n", encoding="utf-8")
        code, result = work.run_work(self.repo, "0001-thing", backend="stub",
                                     worktree=str(self.repo))
        self.assertEqual(code, 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_work.RunWorkTest -v`
Expected: FAIL with `AttributeError: module 'scripts.factory.lib.work' has no attribute 'run_work'`.

- [ ] **Step 3: Add `run_work` + helpers to `lib/work.py`**

Append to `scripts/factory/lib/work.py`:

```python
def resolve_worktree(repo, item_id):
    """The filesystem path of the worktree checked out on factory/<id>,
    else the repo root if that branch exists there, else None."""
    branch = f"factory/{item_id}"
    listing = _git(repo, "worktree", "list", "--porcelain")
    if listing.returncode == 0:
        current = None
        for line in listing.stdout.splitlines():
            if line.startswith("worktree "):
                current = line[len("worktree "):]
            elif line.strip() == f"branch refs/heads/{branch}" and current:
                return current
    check = _git(repo, "rev-parse", "--verify", "--quiet",
                 "refs/heads/" + branch)
    return str(repo) if check.returncode == 0 else None


def _tick_plan(repo, item_id):
    plan = paths.item_dir(repo, item_id) / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace("- [ ]", "- [x]"),
                    encoding="utf-8")


def _test_summary(test_result):
    if test_result is None:
        return "no test_command configured"
    head = "green: " if test_result["passed"] else "RED: "
    return head + (test_result.get("summary") or "")[:120]


def _log_spend(repo, item_id, backend, model, usage):
    data = {"provenance": "proxy", "stage": "implement",
            "source": "factory-work", "dispatches": 1}
    if usage and any(usage.get(k) for k in ("input", "output", "total")):
        data["provenance"] = "measured"
        data["tokens"] = {k: int(usage.get(k, 0))
                          for k in ("input", "output", "total")}
    if model:
        data["model"] = model
    logs.append_event(repo, item_id, "spend", data)


def run_work(repo, item_id, backend=None, model=None, timeout=None,
             network=None, worktree=None):
    cfg = worker_config(repo)
    backend = backend or cfg["backend"]
    timeout = timeout or cfg["timeout_seconds"]
    network = network or cfg["network"]
    if backend not in BACKENDS:
        return 1, {"error": f"unknown or unavailable backend: {backend}"}
    try:
        meta, _ = items.load_item(repo, item_id)
    except items.ItemError as exc:
        return 1, {"error": str(exc)}
    if meta.get("stage") != "implement":
        return 2, {"error": f"{item_id} is at stage "
                            f"{meta.get('stage')!r}, not implement"}
    plan_path = paths.item_dir(repo, item_id) / "plan.md"
    if not plan_path.exists():
        return 1, {"error": f"{item_id}: plan.md missing"}
    tasks = unticked_tasks(plan_path.read_text(encoding="utf-8"))
    if not tasks:
        return 2, {"error": f"{item_id}: no unticked plan tasks"}
    work_tree = worktree or resolve_worktree(repo, item_id)
    if work_tree is None:
        return 1, {"error": f"cannot resolve worktree for factory/{item_id}"}
    brief = build_brief(repo, item_id, work_tree)
    if backend in ("claude", "codex") and shutil.which(backend) is None:
        return 1, {"error": f"backend CLI not found on PATH: {backend}"}

    worker_dir = paths.item_dir(repo, item_id) / "worker"
    worker_dir.mkdir(parents=True, exist_ok=True)
    (worker_dir / "brief.md").write_text(brief, encoding="utf-8")

    env = dict(os.environ)
    model = model or (cfg.get("models") or {}).get(backend)
    sandbox = (cfg.get("codex") or {}).get("sandbox", "workspace-write")
    base_sha = git_head(work_tree)
    raw = BACKENDS[backend](brief, work_tree, model, timeout, network,
                            sandbox, env)
    (worker_dir / "worker.log").write_text(raw.get("stderr") or "",
                                           encoding="utf-8")
    parsed = _parse_output(backend, raw)

    test_result = None
    test_command = cfg.get("test_command")
    if test_command and parsed["status"] == "done":
        proc = subprocess.run(test_command, cwd=work_tree, shell=True,
                              capture_output=True, text=True)
        test_result = {"command": test_command,
                       "passed": proc.returncode == 0,
                       "summary": (proc.stdout or proc.stderr)[-500:].strip()}

    gstate = git_state(work_tree, base_sha)
    result = normalize(item_id, backend, model, f"factory/{item_id}", gstate,
                       parsed, test_result,
                       f"items/{item_id}/worker/worker.log")
    errors = validate.validate(result, initrepo.load_schema("result"),
                               "result")
    if errors:
        return 1, {"error": "internal: result failed schema validation",
                   "detail": errors, "result": result}
    (worker_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    _log_spend(repo, item_id, backend, model, result.get("usage"))
    if result["status"] == "done":
        _tick_plan(repo, item_id)
        logs.append_event(repo, item_id, "implement.completed",
                          {"tasks": len(tasks),
                           "tests": _test_summary(test_result),
                           "backend": backend})
        return 0, result
    logs.append_event(repo, item_id, "implement.failed",
                      {"reason": result.get("reason"), "backend": backend})
    return 3, result
```

Note: `implement.completed`'s `tasks` count is `len(tasks)` — the plan's unticked task list read once up front — matching the existing contract's `{"tasks": N, ...}` data shape. (Do **not** count from `brief`: it renders tasks as `1. …`, not `- [ ]`, so `unticked_tasks(brief)` would be 0.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_work.RunWorkTest -v`
Expected: PASS (4 tests). Then the whole suite: `python3 -m unittest discover -s tests -v` — all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/work.py tests/test_work.py
git commit -m "feat(work): run_work orchestration (events, spend, tick, gates)"
```

---

### Task 6: `factory work` CLI wiring

**Files:**
- Modify: `scripts/factory/factory.py` (import, `cmd_work`, subparser)
- Test: `tests/test_cli_work.py`

**Interfaces:**
- Consumes: `work.run_work`.
- Produces: the `factory work <id> [--backend claude|codex|stub] [--model M] [--timeout S] [--network on|off] [--worktree PATH] [--json]` command; exit codes 0/1/2/3 from `run_work`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_work.py`:

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


class CliWorkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(self.repo, "add", "seed.txt")
        _git(self.repo, "commit", "-q", "-m", "seed")
        _git(self.repo, "checkout", "-q", "-b", "factory/0001-thing")
        self.run_cli("init")
        meta = {"id": "0001-thing", "title": "Thing", "stage": "implement",
                "kind": "backend", "created": "2026-07-03T00:00:00Z",
                "updated": "2026-07-03T00:00:00Z"}
        items.save_item(self.repo, meta, "")
        (self.repo / ".factory/items/0001-thing/plan.md").write_text(
            "- [ ] Do the thing\n", encoding="utf-8")
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(self.repo), *args])
        return code, out.getvalue(), err.getvalue()

    def test_work_stub_success_exit_zero(self):
        code, out, err = self.run_cli("work", "0001-thing", "--backend",
                                      "stub", "--worktree", str(self.repo))
        self.assertEqual(code, 0, err)
        self.assertIn("done", out)

    def test_work_json_emits_result(self):
        code, out, err = self.run_cli("work", "0001-thing", "--backend",
                                      "stub", "--worktree", str(self.repo),
                                      "--json")
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["backend"], "stub")

    def test_work_wrong_stage_exit_two(self):
        item_md = self.repo / ".factory/items/0001-thing/item.md"
        item_md.write_text(item_md.read_text().replace(
            "stage: implement", "stage: plan"), encoding="utf-8")
        code, out, err = self.run_cli("work", "0001-thing", "--backend",
                                      "stub", "--worktree", str(self.repo))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_cli_work -v`
Expected: FAIL — argparse errors with `invalid choice: 'work'` (subcommand not registered), surfaced as exit code 1.

- [ ] **Step 3: Wire the command into `factory.py`**

In `scripts/factory/factory.py`, add `work` to BOTH import lines (the `sys.path` branch and the relative branch) so it reads e.g. `..., paths, cost, work`:

```python
    from scripts.factory.lib import initrepo, items, logs, machine, council, health as health_mod, prune as prune_mod, dispatch, packet as packet_mod, design as design_mod, doctor as doctor_mod, paths, cost, work
```

```python
    from .lib import initrepo, items, logs, machine, council, health as health_mod, prune as prune_mod, dispatch, packet as packet_mod, design as design_mod, doctor as doctor_mod, paths, cost, work
```

Add the command function (near the other `cmd_*` functions, e.g. after `cmd_cost`):

```python
def cmd_work(args):
    if not _require_factory_repo(args.repo):
        return 2
    code, result = work.run_work(
        args.repo, args.item, backend=args.backend, model=args.model,
        timeout=args.timeout, network=args.network, worktree=args.worktree)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif code == 0:
        print(f"{args.item} done ({result.get('backend')}): "
              f"{len(result.get('commits', []))} commit(s)")
    else:
        print(result.get("error")
              or f"{args.item} {result.get('status', 'failed')}: "
                 f"{result.get('reason')}", file=sys.stderr)
    return code
```

Register the subparser inside `main()` (near the other `sub.add_parser` calls, e.g. after `next`):

```python
    p = sub.add_parser("work",
                       help="run one headless worker for an item at implement")
    p.add_argument("item")
    p.add_argument("--backend", choices=["claude", "codex", "stub"])
    p.add_argument("--model")
    p.add_argument("--timeout", type=int)
    p.add_argument("--network", choices=["on", "off"])
    p.add_argument("--worktree")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_work)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_cli_work -v`
Expected: PASS (3 tests). Full suite: `python3 -m unittest discover -s tests -v` — all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/factory.py tests/test_cli_work.py
git commit -m "feat(work): factory work CLI command"
```

---

### Task 7: claude backend (argv + parser)

**Files:**
- Modify: `scripts/factory/lib/work.py`
- Test: `tests/test_work_backends.py`

**Interfaces:**
- Produces: `work._claude_argv(brief, worktree, model, network) -> list[str]`; `work._claude_parse(raw) -> parsed`; registers `work.BACKENDS["claude"]`. Module constant `work.CLAUDE_PERMISSION_MODE`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_work_backends.py`:

```python
import unittest

from scripts.factory.lib import work


class ClaudeBackendTest(unittest.TestCase):
    def test_argv_has_headless_flags(self):
        argv = work._claude_argv("do it", "/wt", "claude-sonnet-5", "off")
        self.assertEqual(argv[0], "claude")
        self.assertIn("-p", argv)
        self.assertIn("--output-format", argv)
        self.assertIn("json", argv)
        self.assertIn("--add-dir", argv)
        self.assertIn("/wt", argv)
        self.assertIn("--model", argv)
        self.assertIn("claude-sonnet-5", argv)
        self.assertIn("--permission-mode", argv)
        self.assertIn(work.CLAUDE_PERMISSION_MODE, argv)

    def test_parse_success(self):
        raw = {"exit_code": 0, "timed_out": False, "stderr": "",
               "stdout": ('{"subtype": "success", "result": "done it", '
                          '"total_cost_usd": 0.012, '
                          '"usage": {"input_tokens": 900, '
                          '"output_tokens": 120}}')}
        parsed = work._claude_parse(raw)
        self.assertEqual(parsed["status"], "done")
        self.assertEqual(parsed["usage"]["input"], 900)
        self.assertEqual(parsed["usage"]["total"], 1020)
        self.assertEqual(parsed["summary"], "done it")
        self.assertEqual(parsed["cost_usd"], 0.012)

    def test_parse_error_subtype_fails(self):
        raw = {"exit_code": 0, "timed_out": False, "stderr": "",
               "stdout": '{"subtype": "error_during_execution", "usage": {}}'}
        parsed = work._claude_parse(raw)
        self.assertEqual(parsed["status"], "failed")

    def test_parse_rate_limit_reason(self):
        raw = {"exit_code": 1, "timed_out": False,
               "stderr": "Error: 429 overloaded_error",
               "stdout": "{}"}
        parsed = work._claude_parse(raw)
        self.assertEqual(parsed["reason"], "rate_limited")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_work_backends -v`
Expected: FAIL with `AttributeError: module 'scripts.factory.lib.work' has no attribute '_claude_argv'`.

- [ ] **Step 3: Add the claude backend to `lib/work.py`**

Append to `scripts/factory/lib/work.py`:

```python
# Spec open-question 1: the exact non-interactive permission mode is confirmed
# against the installed CLI at execution time (see references/headless-workers
# .md). `acceptEdits` auto-applies edits without the one-time TTY accept dialog
# that `--dangerously-skip-permissions` shows (which would park a headless run).
CLAUDE_PERMISSION_MODE = "acceptEdits"


def _looks_rate_limited(obj, raw):
    blob = (json.dumps(obj) + " " + (raw.get("stderr") or "")).lower()
    return any(term in blob for term in
               ("rate limit", "rate_limit", "overloaded", "429", "529"))


def _claude_argv(brief, worktree, model, network):
    argv = ["claude", "-p", brief, "--output-format", "json",
            "--add-dir", str(worktree),
            "--permission-mode", CLAUDE_PERMISSION_MODE]
    if model:
        argv += ["--model", model]
    if network == "off":
        # Best-effort: Claude has no OS sandbox, so this is a tool allowlist,
        # not enforced isolation (design spec §7 asymmetry).
        argv += ["--disallowedTools", "WebFetch,WebSearch"]
    return argv


def _claude_parse(raw):
    if raw.get("timed_out"):
        return {"status": "failed", "reason": "timeout", "usage": {},
                "summary": "", "cost_usd": None}
    try:
        obj = json.loads(raw.get("stdout") or "{}")
    except json.JSONDecodeError:
        obj = {}
    usage = obj.get("usage") or {}
    tokens = {
        "input": usage.get("input_tokens", usage.get("input", 0)),
        "output": usage.get("output_tokens", usage.get("output", 0)),
    }
    tokens["total"] = tokens["input"] + tokens["output"]
    summary = (obj.get("result") or "")[:2000]
    cost = obj.get("total_cost_usd")
    if obj.get("subtype") == "success" and raw["exit_code"] == 0:
        return {"status": "done", "reason": None, "usage": tokens,
                "summary": summary, "cost_usd": cost}
    reason = "rate_limited" if _looks_rate_limited(obj, raw) else "crash"
    return {"status": "failed", "reason": reason, "usage": tokens,
            "summary": summary, "cost_usd": cost}


def _claude_run(brief, worktree, model, timeout, network, sandbox, env):
    return _real_run(_claude_argv(brief, worktree, model, network),
                     worktree, timeout, env)


def _real_run(argv, worktree, timeout, env):
    try:
        proc = subprocess.run(argv, cwd=worktree, capture_output=True,
                              text=True, timeout=timeout, env=env)
        return {"exit_code": proc.returncode, "stdout": proc.stdout,
                "stderr": proc.stderr, "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        return {"exit_code": 124, "stdout": exc.stdout or "",
                "stderr": exc.stderr or "", "timed_out": True}


BACKENDS["claude"] = _claude_run
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_work_backends -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/work.py tests/test_work_backends.py
git commit -m "feat(work): claude headless backend (argv + parser)"
```

---

### Task 8: codex backend (argv + parser)

**Files:**
- Modify: `scripts/factory/lib/work.py`
- Test: `tests/test_work_backends.py`

**Interfaces:**
- Produces: `work._codex_argv(brief, worktree, model, network, sandbox) -> list[str]`; `work._codex_parse(raw) -> parsed`; registers `work.BACKENDS["codex"]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_work_backends.py`:

```python
class CodexBackendTest(unittest.TestCase):
    def test_argv_workspace_write_when_network_off(self):
        argv = work._codex_argv("do it", "/wt", "gpt-x", "off",
                                "workspace-write")
        self.assertEqual(argv[:2], ["codex", "exec"])
        self.assertIn("--json", argv)
        self.assertIn("-C", argv)
        self.assertIn("/wt", argv)
        self.assertIn("-a", argv)
        self.assertIn("never", argv)
        i = argv.index("--sandbox")
        self.assertEqual(argv[i + 1], "workspace-write")

    def test_argv_full_access_when_network_on(self):
        argv = work._codex_argv("do it", "/wt", None, "on", "workspace-write")
        i = argv.index("--sandbox")
        self.assertEqual(argv[i + 1], "danger-full-access")

    def test_parse_sums_usage_and_reads_message(self):
        raw = {"exit_code": 0, "timed_out": False, "stderr": "", "stdout": "\n".join([
            '{"type": "thread.started"}',
            '{"type": "turn.completed", "usage": {"input_tokens": 400, "output_tokens": 60}}',
            '{"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 20}}',
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "all done"}}',
        ])}
        parsed = work._codex_parse(raw)
        self.assertEqual(parsed["status"], "done")
        self.assertEqual(parsed["usage"]["input"], 500)
        self.assertEqual(parsed["usage"]["output"], 80)
        self.assertEqual(parsed["summary"], "all done")

    def test_parse_turn_failed_is_failure(self):
        raw = {"exit_code": 1, "timed_out": False, "stderr": "", "stdout": "\n".join([
            '{"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}',
            '{"type": "turn.failed"}',
        ])}
        parsed = work._codex_parse(raw)
        self.assertEqual(parsed["status"], "failed")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_work_backends.CodexBackendTest -v`
Expected: FAIL with `AttributeError: ... has no attribute '_codex_argv'`.

- [ ] **Step 3: Add the codex backend to `lib/work.py`**

Append to `scripts/factory/lib/work.py`:

```python
def _codex_argv(brief, worktree, model, network, sandbox):
    sbox = "danger-full-access" if network == "on" else sandbox
    argv = ["codex", "exec", brief, "--json", "-C", str(worktree),
            "-a", "never", "--sandbox", sbox]
    if model:
        argv += ["-m", model]
    return argv


def _codex_parse(raw):
    if raw.get("timed_out"):
        return {"status": "failed", "reason": "timeout", "usage": {},
                "summary": "", "cost_usd": None}
    inp = out = 0
    summary = ""
    failed = False
    for line in (raw.get("stdout") or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = event.get("type")
        if etype == "turn.completed":
            usage = event.get("usage") or {}
            inp += usage.get("input_tokens", 0)
            out += usage.get("output_tokens", 0)
        elif etype in ("turn.failed", "error"):
            failed = True
        elif etype == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                summary = (item.get("text") or "")[:2000]
    tokens = {"input": inp, "output": out, "total": inp + out}
    if failed or raw["exit_code"] != 0:
        reason = "rate_limited" if _looks_rate_limited({}, raw) else "crash"
        return {"status": "failed", "reason": reason, "usage": tokens,
                "summary": summary, "cost_usd": None}
    return {"status": "done", "reason": None, "usage": tokens,
            "summary": summary, "cost_usd": None}


def _codex_run(brief, worktree, model, timeout, network, sandbox, env):
    return _real_run(_codex_argv(brief, worktree, model, network, sandbox),
                     worktree, timeout, env)


BACKENDS["codex"] = _codex_run
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_work_backends -v`
Expected: PASS (8 tests total). Full suite green: `python3 -m unittest discover -s tests -v`.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/work.py tests/test_work_backends.py
git commit -m "feat(work): codex exec backend (argv + parser)"
```

---

### Task 9: `factory doctor` headless-worker readout

**Files:**
- Modify: `scripts/factory/lib/doctor.py`
- Test: `tests/test_doctor.py`

**Interfaces:**
- Produces: a `"workers"` key in the doctor readout dict: `{"enabled": bool, "backend": str, "claude_cli": bool, "codex_cli": bool, "anthropic_key": bool, "openai_key": bool}`.

- [ ] **Step 1: Write the failing test**

First open `tests/test_doctor.py` and match its existing fixture style (it constructs a repo via `initrepo.init` and calls the doctor readout — either `doctor.readout(repo)` or the CLI `doctor --json`). Append a test in that file's existing TestCase (adjust the readout call to match what the file already uses):

```python
    def test_readout_reports_worker_readiness(self):
        initrepo.init(self.repo)
        data = doctor.readout(self.repo)   # match the call the file already uses
        self.assertIn("workers", data)
        self.assertIn("enabled", data["workers"])
        self.assertIn("claude_cli", data["workers"])
        self.assertIn("openai_key", data["workers"])
        self.assertIsInstance(data["workers"]["enabled"], bool)
```

If `test_doctor.py` drives the CLI instead of calling `doctor.readout`, write the equivalent assertion against the parsed `--json` output.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_doctor -v`
Expected: FAIL — `KeyError: 'workers'` (or `AssertionError: 'workers' not found`).

- [ ] **Step 3: Add worker readiness to `doctor.py`**

Open `scripts/factory/lib/doctor.py`. It already reads config via a `_config(repo)` helper and builds a readout dict containing keys like `"merge_policy"` and `"gates"`. Add these imports at the top if absent:

```python
import os
import shutil

from . import work
```

Add this helper function:

```python
def worker_readiness(repo):
    cfg = work.worker_config(repo)
    return {
        "enabled": bool(cfg.get("enabled")),
        "backend": cfg.get("backend"),
        "claude_cli": shutil.which("claude") is not None,
        "codex_cli": shutil.which("codex") is not None,
        "anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openai_key": bool(os.environ.get("OPENAI_API_KEY")),
    }
```

Then, in the function that assembles the readout dict, add one key alongside the existing `"merge_policy"` entry:

```python
        "workers": worker_readiness(repo),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_doctor -v`
Expected: PASS. Full suite green.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/doctor.py tests/test_doctor.py
git commit -m "feat(work): factory doctor reports headless-worker readiness"
```

---

### Task 10: skill wiring + coherence guard

**Files:**
- Modify: `skills/factory-implement/SKILL.md`
- Modify: `skills/capabilities/SKILL.md`
- Create: `skills/capabilities/references/headless-workers.md`
- Modify: `tests/test_plugin_coherence.py`

**Interfaces:** none (prose + a drift-guard test).

- [ ] **Step 1: Write the failing test**

Append a test method to the existing TestCase in `tests/test_plugin_coherence.py` (it already computes the repo root; reuse its `ROOT`/`REPO_ROOT` constant — check the file and match the name):

```python
    def test_headless_worker_wiring_present(self):
        root = REPO_ROOT  # match the constant this file already defines
        caps = (root / "skills/capabilities/SKILL.md").read_text()
        self.assertIn("Headless worker", caps)
        impl = (root / "skills/factory-implement/SKILL.md").read_text()
        self.assertIn("factory work", impl)
        self.assertTrue(
            (root / "skills/capabilities/references/"
             "headless-workers.md").exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_plugin_coherence -v`
Expected: FAIL — `AssertionError: 'Headless worker' not found`.

- [ ] **Step 3: Add the capabilities probe row**

In `skills/capabilities/SKILL.md`, add this row to the probe-and-upgrade table (after the `Browser read-back` row):

```
| Headless worker | `workers.enabled` true in `.factory/config.json` and the configured backend CLI (`claude`/`codex`) resolvable on `PATH` with its key env var set (`factory doctor` reports this) | Dispatch an item's implementation out-of-process via `factory work <id>` → see references/headless-workers.md | Today's in-process `superpowers:subagent-driven-development` path, unchanged |
```

- [ ] **Step 4: Add the headless branch to factory-implement**

In `skills/factory-implement/SKILL.md`, at the start of step 3 (the `superpowers:subagent-driven-development` dispatch), insert this sentence:

```
   **Headless path (capabilities skill — "Headless worker" row):** if that capability is present, execute this item's plan out-of-process by running `factory work <item-id>` instead of the in-process dispatch below — it runs a headless worker in the `factory/<item-id>` worktree, writes `items/<item-id>/worker/result.json`, and on success logs the same `implement.completed` event and a measured `spend` event this station otherwise logs. On its non-zero exit, read `result.json`'s `reason` and treat it as this station's failure path (below). Otherwise, fall through to the in-process path:
```

- [ ] **Step 5: Create the reference doc**

Create `skills/capabilities/references/headless-workers.md`:

```markdown
# Headless workers (`factory work`)

`factory work <id>` runs one headless coding-agent worker in an item's
`factory/<id>` worktree and captures a normalized `items/<id>/worker/result
.json`. It is the out-of-process executor: the worker owns its own context,
and the orchestrator only ever reads the result packet.

## Command

```
factory work <id> [--backend claude|codex|stub] [--model M]
                  [--timeout S] [--network on|off] [--worktree PATH] [--json]
```

Exit codes: `0` succeeded (result `done`, `implement.completed` logged);
`1` usage/internal; `2` precondition refusal (not at `implement`, or no
unticked plan tasks); `3` worker attempted but failed — read `result.json`'s
typed `reason` (`crash|timeout|no_changes|red_tests|rate_limited|auth|blocked`).

## Config (`.factory/config.json` → `workers`)

Off by default. Keys: `enabled`, `backend` (default `claude`), `max_parallel`
(default 2), `timeout_seconds`, `network` (default `off`), `prep`,
`test_command`, `models.{claude,codex}`, `codex.sandbox`, `retry`.

## Auth (environment only)

Fleet/unattended mode uses **API keys**, not subscription tokens (which race
and expire mid-run): `ANTHROPIC_API_KEY` for `claude`, `OPENAI_API_KEY` for
`codex`. `factory doctor` reports presence without printing values.

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
verify + green-tests gates. `factory work` only fills the `implement`
station; nothing about the gates changes.

## `stub` backend

`--backend stub` is a test-only in-process backend (writes a file, commits,
returns a canned result); it never spawns a CLI. Used by the engine tests.
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_plugin_coherence -v`
Expected: PASS. Then the FULL suite one final time: `python3 -m unittest discover -s tests -v` — all green.

- [ ] **Step 7: Commit**

```bash
git add skills/factory-implement/SKILL.md skills/capabilities/SKILL.md skills/capabilities/references/headless-workers.md tests/test_plugin_coherence.py
git commit -m "feat(work): wire headless-worker capability into skills"
```

---

## Notes for the executor

- **Run the full suite after every task**, not just the task's own tests: `python3 -m unittest discover -s tests -v` from the repo root. Config/schema changes (Tasks 1, 4) can affect `test_initrepo.py`; if a pre-existing test asserts the exact `DEFAULT_CONFIG` contents, note that this plan deliberately does **not** modify `DEFAULT_CONFIG` (the `workers` block is optional and absent-by-default), so no such test should break — if one does, investigate rather than force-edit.
- **The `stub` backend is the test seam.** No test in this plan invokes a real `claude`/`codex` binary. Live smoke-testing against the real CLIs is a manual step, out of scope here.
- **`.factory/` is gitignored**, so ticking `plan.md` is a file write, not a commit — do not add a `git commit` of `plan.md` inside `factory work`.
- Two module constants intentionally encode design open-questions confirmed at execution time: `CLAUDE_PERMISSION_MODE` (Task 7) and the codex event-type strings in `_codex_parse` (Task 8). They are unit-tested for argv/parse structure, not live behavior.
- **Dependency prep is out of scope for Phase A.** Spec §7's prep step (copy `.worktreeinclude`, install deps with network on before the worker runs) is a *scheduler* responsibility and lands in Phase B. The `workers.prep` config key is defined in the schema now (forward-compat) but `run_work` does **not** execute it — a solo `factory work` run assumes its worktree already has dependencies, or uses a `test_command` that needs none. Do not wire prep into `run_work` in this plan.
