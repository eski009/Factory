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
