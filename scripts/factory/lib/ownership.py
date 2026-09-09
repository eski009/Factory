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
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import paths, safeio


class OwnershipError(Exception):
    pass


class OwnershipRefusal(OwnershipError):
    pass


class NoRegisteredWorktree(OwnershipRefusal):
    """The item branch has no checkout in Git's worktree registry."""


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
_OWNER_STATE_LIMIT = 4096
_OWNER_STATE_NAME = "implementation-owner.json"
_RELEASE_GUARD_NAME = "implementation-owner.release-pending"
_RELEASE_GUARD_BYTES = b"release-pending\n"


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


@dataclass(frozen=True)
class OwnerVerification:
    """A read-only proof of the currently registered implementation owner."""

    repo: Path
    item_id: str
    checkout: Path
    owner_sha256: str


def owner_state_path(repo, item_id):
    return paths.item_dir(repo, item_id) / "implementation-owner.json"


def _release_guard_path(state):
    return state.with_name("implementation-owner.release-pending")


def _open_item_chain(repo, item_id, checkout):
    if (type(item_id) is not str or not item_id or item_id in (".", "..") or
            "/" in item_id or "\\" in item_id or "\0" in item_id):
        raise _invalid_state(item_id, checkout)
    chain = None
    try:
        canonical = safeio._resolve_root(repo)
        chain = safeio._open_root_chain(canonical)
        for component in (".factory", "items", item_id):
            safeio._append_directory(chain, component)
        safeio._validate_chain(chain)
        return chain
    except (OSError, safeio.SafeIOError):
        if chain is not None:
            safeio._close_chain(chain)
        raise _invalid_state(item_id, checkout) from None


def _secure_entry_exists(chain, name):
    safeio._validate_chain(chain)
    try:
        os.stat(name, dir_fd=chain[-1].fd, follow_symlinks=False)
    except FileNotFoundError:
        safeio._validate_chain(chain)
        return False
    safeio._validate_chain(chain)
    return True


def _secure_read_owner(chain):
    raw, identity = safeio._read_regular_file(
        chain[-1].fd, _OWNER_STATE_NAME, _OWNER_STATE_LIMIT)
    safeio._validate_chain(chain)
    return raw, identity


def _write_all(fd, payload):
    remaining = memoryview(payload)
    while remaining:
        written = os.write(fd, remaining)
        if written <= 0:
            raise OSError("short write while creating ownership state")
        remaining = remaining[written:]


def _write_exclusive_at(directory_fd, name, payload):
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL |
             getattr(os, "O_NOFOLLOW", 0) |
             getattr(os, "O_NONBLOCK", 0))
    fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode):
            raise OSError("ownership state is not a regular file")
        inode = (details.st_dev, details.st_ino)
        _write_all(fd, payload)
        os.fsync(fd)
        final = os.fstat(fd)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        identity = safeio._file_identity(final)
        if (not stat.S_ISREG(final.st_mode) or
                not stat.S_ISREG(named.st_mode) or
                (final.st_dev, final.st_ino) != inode or
                safeio._file_identity(named) != identity):
            raise OSError("ownership state identity changed")
        return identity
    finally:
        os.close(fd)


def _digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def owner_digest(token):
    """Return the persistable identity of a non-empty opaque owner token."""
    if type(token) is not str or not token:
        raise OwnershipRefusal("ownership verification refused")
    return _digest(token)


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


def _read_valid_record(state, item_id, checkout, ops=DEFAULT_OPS, chain=None,
                       with_identity=False, with_snapshot=False):
    try:
        identity = None
        if ops is DEFAULT_OPS:
            if chain is None:
                owned_chain = _open_item_chain(
                    state.parents[3], item_id, checkout)
                try:
                    raw, identity = _secure_read_owner(owned_chain)
                finally:
                    safeio._close_chain(owned_chain)
            else:
                raw, identity = _secure_read_owner(chain)
        else:
            raw = ops.read_bytes(state)
        record = json.loads(raw.decode("utf-8"),
                            object_pairs_hook=_strict_json_object)
    except (OSError, safeio.SafeIOError, UnicodeDecodeError, ValueError):
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
    if with_snapshot:
        return record, raw, identity
    return (record, identity) if with_identity else record


def _write_exclusive(path, payload):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def _create_exclusive(state, record, item_id, checkout, ops=DEFAULT_OPS,
                      chain=None):
    payload = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    try:
        if ops is DEFAULT_OPS and chain is not None:
            _write_exclusive_at(chain[-1].fd, _OWNER_STATE_NAME, payload)
            safeio._validate_chain(chain)
        else:
            _write_exclusive(state, payload)
    except FileExistsError:
        _read_valid_record(
            state, item_id, checkout, ops=ops, chain=chain)
        raise _contended(item_id, checkout)


def _guard_exists(state, item_id, checkout, ops=DEFAULT_OPS, chain=None):
    try:
        if ops is DEFAULT_OPS and chain is not None:
            exists = _secure_entry_exists(chain, _RELEASE_GUARD_NAME)
        else:
            exists = ops.exists(_release_guard_path(state))
    except (OSError, safeio.SafeIOError):
        raise _invalid_state(item_id, checkout) from None
    if exists:
        raise _invalid_state(item_id, checkout)


def _create_release_guard(state, item_id):
    guard = _release_guard_path(state)
    try:
        _write_exclusive(guard, _RELEASE_GUARD_BYTES)
        directory_fd = os.open(guard.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise _release_failed(item_id) from exc
    return guard


def _secure_release(repo, item_id, checkout, token, state):
    chain = _open_item_chain(repo, item_id, checkout)
    try:
        record, state_bytes, state_identity = _read_valid_record(
            state, item_id, checkout, chain=chain, with_snapshot=True)
        if not hmac.compare_digest(record["owner_sha256"], _digest(token)):
            raise OwnershipRefusal(f"{item_id}: ownership release refused")
        try:
            guard_identity = _write_exclusive_at(
                chain[-1].fd, _RELEASE_GUARD_NAME, _RELEASE_GUARD_BYTES)
            os.fsync(chain[-1].fd)
            safeio._validate_chain(chain)
        except OSError as exc:
            raise _release_failed(item_id) from exc
        try:
            safeio._require_exact_regular_file(
                chain[-1].fd, _OWNER_STATE_NAME, state_bytes,
                state_identity, "owner state changed before unlink")
            safeio._validate_chain(chain)
            if not safeio._unlink_if_identity(
                    chain[-1].fd, _OWNER_STATE_NAME, state_identity[:2]):
                raise OSError("owner state identity changed before unlink")
            if _secure_entry_exists(chain, _OWNER_STATE_NAME):
                raise OSError("owner state still exists after unlink")
            os.fsync(chain[-1].fd)
            safeio._validate_chain(chain)
        except (OSError, safeio.SafeIOError) as exc:
            raise _release_failed(item_id) from exc
        try:
            safeio._require_exact_regular_file(
                chain[-1].fd, _RELEASE_GUARD_NAME,
                _RELEASE_GUARD_BYTES, guard_identity,
                "release guard changed before unlink")
            safeio._validate_chain(chain)
            if not safeio._unlink_if_identity(
                    chain[-1].fd, _RELEASE_GUARD_NAME,
                    guard_identity[:2]):
                raise OSError("release guard identity changed before unlink")
            os.fsync(chain[-1].fd)
            safeio._validate_chain(chain)
        except (OSError, safeio.SafeIOError) as exc:
            raise _release_failed(item_id) from exc
    finally:
        safeio._close_chain(chain)


def _registered_branch_worktrees(repo, branch):
    failure = f"{branch}: git worktree lookup failed"
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain", "-z"], cwd=repo,
            capture_output=True)
    except (OSError, UnicodeError) as exc:
        raise OwnershipRefusal(failure) from exc
    if result.returncode != 0:
        raise OwnershipRefusal(failure)
    registered = []
    current = None
    worktree_prefix = b"worktree "
    branch_field = b"branch refs/heads/" + os.fsencode(branch)
    for field in (result.stdout or b"").split(b"\0"):
        if field.startswith(worktree_prefix):
            current = field[len(worktree_prefix):]
        elif field == branch_field and current is not None:
            registered.append(os.fsdecode(current))
        elif not field:
            current = None
    return registered


def canonical_worktree(repo, item_id, supplied=None):
    repo = Path(repo)
    registered = _registered_branch_worktrees(repo, f"factory/{item_id}")
    if not registered:
        raise NoRegisteredWorktree(
            f"{item_id}: no registered checkout for factory/{item_id}")
    if len(registered) > 1:
        raise OwnershipRefusal(
            f"{item_id}: registered checkout for factory/{item_id} is "
            "ambiguous")
    try:
        checkout = Path(registered[0]).resolve(strict=True)
    except (OSError, RuntimeError):
        raise OwnershipRefusal(
            f"{item_id}: registered checkout for factory/{item_id} cannot "
            "be resolved") from None
    if supplied is not None:
        given = Path(supplied)
        if not given.is_absolute():
            given = repo / given
        try:
            supplied_checkout = given.resolve(strict=True)
        except (OSError, RuntimeError):
            raise OwnershipRefusal(
                f"{item_id}: supplied checkout cannot be resolved") from None
        if supplied_checkout != checkout:
            raise OwnershipRefusal(
                f"{item_id}: supplied checkout is not the registered "
                f"checkout {checkout}")
    return checkout


def acquire(repo, item_id, supplied=None, owner_token=None, ops=DEFAULT_OPS):
    repo = Path(repo)
    checkout = canonical_worktree(repo, item_id, supplied)
    state = owner_state_path(repo, item_id)
    if owner_token is not None and (
            type(owner_token) is not str or not owner_token):
        raise _contended(item_id, checkout)
    if ops is DEFAULT_OPS:
        chain = _open_item_chain(repo, item_id, checkout)
        try:
            _guard_exists(
                state, item_id, checkout, ops=ops, chain=chain)
            try:
                state_exists = _secure_entry_exists(chain, _OWNER_STATE_NAME)
            except (OSError, safeio.SafeIOError):
                raise _invalid_state(item_id, checkout) from None
            if state_exists:
                record = _read_valid_record(
                    state, item_id, checkout, ops=ops, chain=chain)
                if owner_token is not None and hmac.compare_digest(
                        record["owner_sha256"], _digest(owner_token)):
                    _guard_exists(
                        state, item_id, checkout, ops=ops, chain=chain)
                    return OwnerClaim(
                        repo, item_id, checkout, owner_token, inherited=True)
                raise _contended(item_id, checkout)
            if owner_token is not None:
                raise _contended(item_id, checkout)
            token = secrets.token_urlsafe(32)
            _create_exclusive(
                state, _record(item_id, checkout, token), item_id, checkout,
                ops=ops, chain=chain)
            _guard_exists(
                state, item_id, checkout, ops=ops, chain=chain)
            safeio._validate_chain(chain)
            return OwnerClaim(repo, item_id, checkout, token)
        finally:
            safeio._close_chain(chain)
    _guard_exists(state, item_id, checkout, ops=ops)
    try:
        state_exists = ops.exists(state)
    except OSError:
        raise _invalid_state(item_id, checkout) from None
    if state_exists:
        record = _read_valid_record(state, item_id, checkout, ops=ops)
        if owner_token is not None and hmac.compare_digest(
                record["owner_sha256"], _digest(owner_token)):
            _guard_exists(state, item_id, checkout, ops=ops)
            return OwnerClaim(repo, item_id, checkout, owner_token,
                              inherited=True)
        raise _contended(item_id, checkout)
    if owner_token is not None:
        raise _contended(item_id, checkout)
    token = secrets.token_urlsafe(32)
    _create_exclusive(state, _record(item_id, checkout, token), item_id,
                      checkout, ops=ops)
    _guard_exists(state, item_id, checkout, ops=ops)
    return OwnerClaim(repo, item_id, checkout, token)


def verify(repo, item_id, token, supplied=None, ops=DEFAULT_OPS):
    """Verify live ownership without creating, deleting, or rewriting state."""
    digest = owner_digest(token)
    checkout = canonical_worktree(repo, item_id, supplied)
    state = owner_state_path(repo, item_id)
    chain = (_open_item_chain(repo, item_id, checkout)
             if ops is DEFAULT_OPS else None)
    try:
        _guard_exists(
            state, item_id, checkout, ops=ops, chain=chain)
        record = _read_valid_record(
            state, item_id, checkout, ops=ops, chain=chain)
        if not hmac.compare_digest(record["owner_sha256"], digest):
            raise OwnershipRefusal(
                f"{item_id}: ownership verification refused")
        _guard_exists(
            state, item_id, checkout, ops=ops, chain=chain)
        if chain is not None:
            safeio._validate_chain(chain)
        return OwnerVerification(repo=Path(repo), item_id=item_id,
                                 checkout=checkout, owner_sha256=digest)
    finally:
        if chain is not None:
            safeio._close_chain(chain)


def revalidate(verification, ops=DEFAULT_OPS):
    """Recheck a prior read-only verification without retaining its token."""
    if not isinstance(verification, OwnerVerification):
        raise OwnershipRefusal("ownership verification is invalid")
    checkout = canonical_worktree(
        verification.repo, verification.item_id, verification.checkout)
    state = owner_state_path(verification.repo, verification.item_id)
    chain = (_open_item_chain(
        verification.repo, verification.item_id, checkout)
        if ops is DEFAULT_OPS else None)
    try:
        _guard_exists(
            state, verification.item_id, checkout, ops=ops, chain=chain)
        record = _read_valid_record(
            state, verification.item_id, checkout, ops=ops, chain=chain)
        if not hmac.compare_digest(
                record["owner_sha256"], verification.owner_sha256):
            raise OwnershipRefusal(
                f"{verification.item_id}: ownership verification refused")
        _guard_exists(
            state, verification.item_id, checkout, ops=ops, chain=chain)
        if chain is not None:
            safeio._validate_chain(chain)
        return verification
    finally:
        if chain is not None:
            safeio._close_chain(chain)


def release(repo, item_id, checkout, token, ops=DEFAULT_OPS):
    repo = Path(repo)
    state = owner_state_path(repo, item_id)
    if type(token) is not str or not token:
        raise OwnershipRefusal(f"{item_id}: ownership release refused")
    if ops is DEFAULT_OPS:
        _secure_release(repo, item_id, checkout, token, state)
        return
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
