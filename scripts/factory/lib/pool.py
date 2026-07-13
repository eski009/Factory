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
    # target is already resolved (paths.worktrees_dir resolves); str() only.
    target_str = str(target)
    if branch_exists:
        added = _git(repo, "worktree", "add", target_str, branch)
    else:
        added = _git(repo, "worktree", "add", target_str, "-b", branch,
                     _default_base(repo))
    if added.returncode != 0:
        raise PoolError(
            f"git worktree add failed for {branch}: {added.stderr.strip()}")
    return target_str, True


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
        # gitignore-style root anchor: treat "/path" as repo-relative "path"
        # (a leading slash would otherwise make Path(worktree)/entry absolute
        # and collapse src==dst -> SameFileError).
        entry = entry.lstrip("/")
        if not entry:
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
