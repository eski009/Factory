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
import time
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
        if key in ("retry", "codex"):
            # Malformed nested config (non-dict) is ignored so the merged
            # defaults survive — Phase B dereferences retry.* for backoff.
            if isinstance(value, dict):
                merged[key].update(value)
        else:
            merged[key] = value
    return merged


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
    if not isinstance(obj, dict):
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
    if not isinstance(obj, dict):
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
        if not isinstance(event, dict):
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


def _parse_output(backend, raw):
    if backend == "claude":
        return _claude_parse(raw)
    if backend == "codex":
        return _codex_parse(raw)
    return _stub_parse(raw)


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
    head = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    return (str(repo) if head.returncode == 0 and head.stdout.strip() == branch
            else None)


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
    started = time.monotonic()
    raw = BACKENDS[backend](brief, work_tree, model, timeout, network,
                            sandbox, env)
    duration_s = int(time.monotonic() - started)
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
                       f"items/{item_id}/worker/worker.log",
                       duration_s=duration_s)
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
