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
