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


class _FilesystemOps:
    """Injectable owner-state operations used by guarded release tests."""

    @staticmethod
    def read_bytes(path):
        return path.read_bytes()

    @staticmethod
    def unlink(path):
        path.unlink()

    @staticmethod
    def exists(path):
        return path.exists()


DEFAULT_OPS = _FilesystemOps()


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


def _release_guard_path(state):
    return state.with_name("implementation-owner.release-pending")


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


def _release_failed(item_id):
    return OwnershipReleaseError(
        f"{item_id}: ownership release could not be verified; "
        "automatic takeover is unsupported")


def _strict_json_object(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError("duplicate owner-state key")
        record[key] = value
    return record


def _read_valid_record(state, item_id, checkout, ops=DEFAULT_OPS):
    try:
        raw = ops.read_bytes(state)
        record = json.loads(raw.decode("utf-8"),
                            object_pairs_hook=_strict_json_object)
    except (OSError, UnicodeDecodeError, ValueError):
        raise _invalid_state(item_id, checkout) from None
    if (type(record) is not dict
            or set(record) != {"version", "item", "checkout", "owner_sha256"}
            or type(record.get("version")) is not int
            or record["version"] != 1
            or type(record.get("item")) is not str
            or type(record.get("checkout")) is not str
            or type(record.get("owner_sha256")) is not str
            or len(record["owner_sha256"]) != 64
            or any(ch not in "0123456789abcdef"
                   for ch in record["owner_sha256"])
            or record["item"] != item_id
            or record["checkout"] != str(checkout)):
        raise _invalid_state(item_id, checkout)
    return record


def _write_exclusive(path, payload):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
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


def _create_exclusive(state, record, item_id, checkout, ops=DEFAULT_OPS):
    payload = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    try:
        _write_exclusive(state, payload)
    except FileExistsError:
        _read_valid_record(state, item_id, checkout, ops=ops)
        raise _contended(item_id, checkout)


def _guard_exists(state, item_id, checkout, ops=DEFAULT_OPS):
    try:
        exists = ops.exists(_release_guard_path(state))
    except OSError:
        raise _invalid_state(item_id, checkout) from None
    if exists:
        raise _invalid_state(item_id, checkout)


def _create_release_guard(state, item_id):
    guard = _release_guard_path(state)
    try:
        _write_exclusive(guard, b"release-pending\n")
        directory_fd = os.open(guard.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise _release_failed(item_id) from exc
    return guard


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


def acquire(repo, item_id, supplied=None, owner_token=None, ops=DEFAULT_OPS):
    repo = Path(repo)
    checkout = canonical_worktree(repo, item_id, supplied)
    state = owner_state_path(repo, item_id)
    if owner_token is not None and type(owner_token) is not str:
        raise _contended(item_id, checkout)
    _guard_exists(state, item_id, checkout, ops=ops)
    try:
        state_exists = ops.exists(state)
    except OSError:
        raise _invalid_state(item_id, checkout) from None
    if state_exists:
        record = _read_valid_record(state, item_id, checkout, ops=ops)
        if owner_token and hmac.compare_digest(
                record["owner_sha256"], _digest(owner_token)):
            _guard_exists(state, item_id, checkout, ops=ops)
            return OwnerClaim(repo, item_id, checkout, owner_token,
                              inherited=True)
        raise _contended(item_id, checkout)
    token = owner_token or secrets.token_urlsafe(32)
    _create_exclusive(state, _record(item_id, checkout, token), item_id,
                      checkout, ops=ops)
    _guard_exists(state, item_id, checkout, ops=ops)
    return OwnerClaim(repo, item_id, checkout, token)


def release(repo, item_id, checkout, token, ops=DEFAULT_OPS):
    repo = Path(repo)
    state = owner_state_path(repo, item_id)
    if type(token) is not str or not token:
        raise OwnershipRefusal(f"{item_id}: ownership release refused")
    record = _read_valid_record(state, item_id, checkout, ops=ops)
    if not hmac.compare_digest(record["owner_sha256"], _digest(token)):
        raise OwnershipRefusal(f"{item_id}: ownership release refused")
    guard = _create_release_guard(state, item_id)
    try:
        ops.unlink(state)
        if ops.exists(state):
            raise OSError("owner state still exists after unlink")
    except OSError as exc:
        raise _release_failed(item_id) from exc
    try:
        guard.unlink()
    except OSError as exc:
        raise _release_failed(item_id) from exc
