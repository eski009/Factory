"""Atomic ownership for an item's implementation checkout.

The state record deliberately contains only a digest of an opaque token.  The
token is an in-memory capability held by the caller which won the exclusive
create race; it is never recoverable from Factory state or logs.
"""

import hashlib
import hmac
import json
import os
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import paths


class OwnershipError(Exception):
    pass


class OwnershipRefusal(OwnershipError):
    pass


class OwnershipReleaseError(OwnershipError):
    pass


@dataclass
class OwnerClaim:
    repo: Path
    item_id: str
    checkout: Path
    token: str
    inherited: bool = False

    def release(self):
        if not self.inherited:
            release(self.repo, self.item_id, self.checkout, self.token)


def owner_state_path(repo, item_id):
    return paths.item_dir(repo, item_id) / "implementation-owner.json"


def _digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _record(item_id, checkout, token):
    return {
        "version": 1,
        "item": item_id,
        "checkout": str(checkout),
        "owner_sha256": _digest(token),
    }


def _contended(item_id, checkout):
    return OwnershipRefusal(
        f"{item_id}: another implementation owner exists for {checkout}; "
        "automatic takeover is unsupported")


def _invalid_state(item_id, checkout):
    return OwnershipRefusal(
        f"{item_id}: owner state is invalid or does not match registered "
        f"checkout {checkout}; automatic takeover is unsupported")


def _read_valid_record(state, item_id, checkout):
    try:
        raw = state.read_bytes()
        record = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise _invalid_state(item_id, checkout) from None
    if (not isinstance(record, dict)
            or set(record) != {"version", "item", "checkout", "owner_sha256"}
            or record.get("version") != 1
            or not isinstance(record.get("item"), str)
            or not isinstance(record.get("checkout"), str)
            or not isinstance(record.get("owner_sha256"), str)
            or len(record["owner_sha256"]) != 64
            or any(ch not in "0123456789abcdef"
                   for ch in record["owner_sha256"])
            or record["item"] != item_id
            or record["checkout"] != str(checkout)):
        raise _invalid_state(item_id, checkout)
    return record


def _create_exclusive(state, record, item_id, checkout):
    payload = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    try:
        fd = os.open(state, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        _read_valid_record(state, item_id, checkout)
        raise _contended(item_id, checkout)
    try:
        remaining = memoryview(payload)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("short write while creating ownership state")
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _registered_branch_worktrees(repo, branch):
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"], cwd=repo,
        capture_output=True, text=True)
    if result.returncode != 0:
        return []
    registered = []
    current = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current = line[len("worktree "):]
        elif line == f"branch refs/heads/{branch}" and current is not None:
            registered.append(current)
    return registered


def canonical_worktree(repo, item_id, supplied=None):
    repo = Path(repo)
    registered = _registered_branch_worktrees(repo, f"factory/{item_id}")
    if len(registered) != 1:
        raise OwnershipRefusal(
            f"{item_id}: registered checkout for factory/{item_id} is "
            "unavailable or ambiguous")
    try:
        checkout = Path(registered[0]).resolve(strict=True)
        if supplied is not None:
            given = Path(supplied)
            if not given.is_absolute():
                given = repo / given
            if given.resolve(strict=True) != checkout:
                raise OwnershipRefusal(
                    f"{item_id}: supplied checkout is not the registered "
                    f"checkout {checkout}")
    except FileNotFoundError:
        raise OwnershipRefusal(
            f"{item_id}: registered checkout for factory/{item_id} is "
            "unavailable or ambiguous") from None
    return checkout


def acquire(repo, item_id, supplied=None, owner_token=None):
    repo = Path(repo)
    checkout = canonical_worktree(repo, item_id, supplied)
    state = owner_state_path(repo, item_id)
    token = owner_token or secrets.token_urlsafe(32)
    if state.exists():
        record = _read_valid_record(state, item_id, checkout)
        if owner_token and hmac.compare_digest(record["owner_sha256"],
                                                _digest(token)):
            return OwnerClaim(repo, item_id, checkout, token, inherited=True)
        raise _contended(item_id, checkout)
    _create_exclusive(state, _record(item_id, checkout, token), item_id,
                      checkout)
    return OwnerClaim(repo, item_id, checkout, token)


def release(repo, item_id, checkout, token):
    repo = Path(repo)
    state = owner_state_path(repo, item_id)
    record = _read_valid_record(state, item_id, checkout)
    if not hmac.compare_digest(record["owner_sha256"], _digest(token)):
        raise OwnershipRefusal(f"{item_id}: ownership release refused")
    try:
        state.unlink()
        if state.exists():
            raise OSError("owner state still exists after unlink")
    except OSError as exc:
        raise OwnershipReleaseError(
            f"{item_id}: ownership release could not be verified; "
            "automatic takeover is unsupported") from exc
