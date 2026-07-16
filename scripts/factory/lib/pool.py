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

import base64
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from . import logs, paths, work


class PoolError(Exception):
    pass


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
    if isinstance(node, list):
        return [_strip_refresh(value) for value in node]
    return node


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
    try:
        result["config_env"] = seed_config_dir(repo, item_id, backend, wt)
    except CodexAuthError as exc:
        result["reason"] = "prep_failed"
        result["detail"] = str(exc)
        logs.append_event(repo, item_id, "prep.failed",
                          {"reason": "prep_failed", "stage": "implement",
                           "detail": str(exc)[:500]})
        return result
    result["prepared"] = True
    logs.append_event(repo, item_id, "prep.completed",
                      {"worktree": wt, "prep": prep,
                       "includes": result["includes"]})
    return result


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
