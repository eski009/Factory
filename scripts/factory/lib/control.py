"""Owner-bound tickets and crash-recoverable Factory control operations.

The module is intentionally a substrate, not a public command.  Tickets carry
strict snapshots between implementation processes without carrying the owner
token.  Operations are a small write-ahead log: immutable intent and blobs are
made durable before ``active.json``; recovery then only rolls that exact intent
forward until its immutable commit receipt exists.

All namespace traversal is descriptor-relative and no-follow.  The advisory
item lock serializes cooperating legacy log writers with control operations.
As with :mod:`safeio`, a hostile same-user process can ignore ``flock``; every
boundary is rechecked and detected interference is refused.
"""

import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import config_state, initrepo, ownership, safeio
from .validate import validate


class ControlError(Exception):
    """The control namespace or an operation could not be used safely."""


class ControlRefusal(ControlError):
    """A valid request was refused because authority or state did not match."""


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_NONCE = re.compile(r"^[0-9a-f]{32}$")
_READ_LIMIT = 64 * 1024 * 1024
# Ticket manifests and their content-addressed blobs have explicit, shared
# construction/publication/reload ceilings.  Keep these distinct from the
# operation WAL ceilings below so either compatibility contract can evolve
# independently.
_TICKET_MANIFEST_LIMIT = _READ_LIMIT
_TICKET_BLOB_LIMIT = _READ_LIMIT
# Every reader and writer of the cumulative authoritative item log must share
# one ceiling.  Tests patch this deliberately small to exercise exact edges.
_LOG_IMAGE_LIMIT = 64 * 1024 * 1024
# The immutable operation record needs one construction/read contract of its
# own: bounded blobs do not bound request/event metadata embedded in intent.
# Commit and active artifacts retain the generic ceiling above.
_INTENT_RECORD_LIMIT = 64 * 1024 * 1024
# Operation WAL blobs likewise have their own compatibility ceiling because
# recovery must be able to load every blob it is asked to settle.
_OPERATION_BLOB_LIMIT = 64 * 1024 * 1024
_DIRECTORY_FLAGS = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                    getattr(os, "O_NOFOLLOW", 0))
_FILE_READ_FLAGS = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                    getattr(os, "O_NONBLOCK", 0))


@dataclass(frozen=True)
class JSONSnapshot:
    file: safeio.FileSnapshot
    value: dict


@dataclass(frozen=True)
class DurableTicket:
    repo: Path
    item_id: str
    ticket_id: str
    kind: str
    key: str
    owner_sha256: str
    checkout: Path
    checkout_identity: tuple[int, int]
    config: config_state.ConfigSnapshot
    inputs: tuple
    metadata: dict
    manifest: JSONSnapshot
    _owner: ownership.OwnerVerification
    _artifacts: tuple[safeio.FileSnapshot, ...]


@dataclass(frozen=True)
class CommitReceipt:
    operation_id: str
    item: str
    kind: str
    key: str
    request_sha256: str
    replacements: tuple[tuple[str, str, str], ...]
    events: tuple[str, ...]


@dataclass(frozen=True)
class RecoveryResult:
    recovered: bool
    receipt: CommitReceipt | None = None


@dataclass
class _ItemLock:
    repo: Path
    item_id: str
    _chain: list
    _item_fd: int
    _control_fd: int
    _control_identity: tuple[int, int]
    _lock_fd: int
    _lock_identity: tuple[int, int]
    _active: bool = True


@dataclass
class _DirectoryPin:
    parent_fd: int
    name: str
    fd: int
    identity: tuple[int, int]


def _component(value, label):
    if (type(value) is not str or not value or value in (".", "..") or
            "/" in value or "\\" in value or "\0" in value):
        raise ControlRefusal(f"invalid {label}")
    return value


def _directory_identity(details):
    return (details.st_dev, details.st_ino)


def _file_identity(details):
    return (details.st_dev, details.st_ino, details.st_size,
            details.st_mtime_ns, details.st_ctime_ns)


def _open_directory(parent_fd, name, *, create=False):
    _component(name, "control namespace component")
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        except OSError as exc:
            raise ControlError("cannot create control namespace") from exc
    try:
        fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise ControlError("cannot safely open control namespace") from exc
    try:
        opened = os.fstat(fd)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (not stat.S_ISDIR(opened.st_mode) or
                not stat.S_ISDIR(named.st_mode) or
                _directory_identity(opened) != _directory_identity(named)):
            raise ControlError("control namespace identity changed")
        if create:
            try:
                os.fsync(fd)
                os.fsync(parent_fd)
                synced = os.fstat(fd)
                synced_named = os.stat(
                    name, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc:
                raise ControlError(
                    "control namespace could not be made durable") from exc
            if (not stat.S_ISDIR(synced.st_mode) or
                    not stat.S_ISDIR(synced_named.st_mode) or
                    _directory_identity(synced) !=
                    _directory_identity(opened) or
                    _directory_identity(synced_named) !=
                    _directory_identity(opened)):
                raise ControlError("control namespace identity changed")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _pin_directory(parent_fd, name, *, create=False):
    fd = _open_directory(parent_fd, name, create=create)
    return _DirectoryPin(
        parent_fd=parent_fd, name=name, fd=fd,
        identity=_directory_identity(os.fstat(fd)))


def _optional_pin_directory(parent_fd, name):
    """Open an existing directory without creating any namespace entry."""
    _component(name, "control namespace component")
    try:
        details = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ControlError("cannot inspect control namespace") from exc
    if not stat.S_ISDIR(details.st_mode):
        raise ControlError("control namespace component is unsafe")
    return _pin_directory(parent_fd, name)


def _close_pin(pin):
    if pin is not None and pin.fd is not None:
        os.close(pin.fd)
        pin.fd = None


def _validate_pins(lock, *pins):
    _validate_item_lock(lock)
    for pin in pins:
        if not isinstance(pin, _DirectoryPin) or pin.fd is None:
            raise ControlError("control namespace pin is not active")
        _validate_named_directory(
            pin.parent_fd, pin.name, pin.fd, pin.identity)


def _sync_pins(lock, *pins):
    _validate_pins(lock, *pins)
    try:
        for pin in reversed(pins):
            os.fsync(pin.fd)
            os.fsync(pin.parent_fd)
    except OSError as exc:
        raise ControlError("control namespace could not be made durable") from exc
    _validate_pins(lock, *pins)


def _validate_named_directory(parent_fd, name, fd, identity):
    try:
        opened = os.fstat(fd)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise ControlError("control namespace was detached") from exc
    if (not stat.S_ISDIR(opened.st_mode) or
            not stat.S_ISDIR(named.st_mode) or
            _directory_identity(opened) != identity or
            _directory_identity(named) != identity):
        raise ControlError("control namespace identity changed")


def _open_lock_file(control_fd):
    flags = (os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) |
             getattr(os, "O_NONBLOCK", 0))
    existed = True
    try:
        os.stat("lock", dir_fd=control_fd, follow_symlinks=False)
    except FileNotFoundError:
        existed = False
    except OSError as exc:
        raise ControlError("cannot inspect control lock") from exc
    try:
        fd = os.open("lock", flags, 0o600, dir_fd=control_fd)
    except OSError as exc:
        raise ControlError("cannot safely open control lock") from exc
    try:
        opened = os.fstat(fd)
        named = os.stat("lock", dir_fd=control_fd, follow_symlinks=False)
        if (not stat.S_ISREG(opened.st_mode) or
                not stat.S_ISREG(named.st_mode) or
                (opened.st_dev, opened.st_ino) !=
                (named.st_dev, named.st_ino)):
            raise ControlError("control lock identity changed")
        if not existed:
            os.fsync(fd)
            os.fsync(control_fd)
        return fd, (opened.st_dev, opened.st_ino)
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def item_lock(repo, item_id, *, create_item=False):
    """Hold the shared, descriptor-validated per-item advisory lock."""
    item_id = _component(item_id, "item id")
    chain = None
    control_fd = None
    lock_fd = None
    lock = None
    try:
        try:
            canonical = safeio._resolve_root(repo)
            chain = safeio._open_root_chain(canonical)
            for component in (".factory", "items", item_id):
                if create_item:
                    fd = _open_directory(
                        chain[-1].fd, component, create=True)
                    chain.append(safeio._make_directory_handle(fd, component))
                else:
                    safeio._append_directory(chain, component)
                safeio._validate_chain(chain)
            safeio._validate_chain(chain)
        except (OSError, safeio.SafeIOError) as exc:
            raise ControlError("cannot safely open item namespace") from exc

        control_fd = _open_directory(chain[-1].fd, "control", create=True)
        control_identity = _directory_identity(os.fstat(control_fd))
        try:
            safeio._validate_chain(chain)
        except (OSError, safeio.SafeIOError) as exc:
            raise ControlError(
                "item namespace changed before lock creation") from exc
        _validate_named_directory(
            chain[-1].fd, "control", control_fd, control_identity)
        lock_fd, lock_identity = _open_lock_file(control_fd)
        safeio._validate_chain(chain)
        _validate_named_directory(
            chain[-1].fd, "control", control_fd, control_identity)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        except OSError as exc:
            raise ControlError("cannot acquire item control lock") from exc
        lock = _ItemLock(
            repo=canonical,
            item_id=item_id,
            _chain=chain,
            _item_fd=chain[-1].fd,
            _control_fd=control_fd,
            _control_identity=control_identity,
            _lock_fd=lock_fd,
            _lock_identity=lock_identity,
        )
        _validate_item_lock(lock)
        yield lock
        _validate_item_lock(lock)
    finally:
        if lock is not None:
            lock._active = False
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        if control_fd is not None:
            os.close(control_fd)
        if chain is not None:
            safeio._close_chain(chain)


def _validate_item_lock(lock, repo=None, item_id=None):
    if not isinstance(lock, _ItemLock) or not lock._active:
        raise ControlError("item control lock is not active")
    if repo is not None:
        try:
            canonical = safeio._resolve_root(repo)
        except safeio.SafeIOError as exc:
            raise ControlError("item control lock repository is invalid") from exc
        if canonical != lock.repo:
            raise ControlError("item control lock repository does not match")
    if item_id is not None and item_id != lock.item_id:
        raise ControlError("item control lock item does not match")
    try:
        safeio._validate_chain(lock._chain)
        _validate_named_directory(
            lock._item_fd, "control", lock._control_fd,
            lock._control_identity)
        opened = os.fstat(lock._lock_fd)
        named = os.stat(
            "lock", dir_fd=lock._control_fd, follow_symlinks=False)
    except (OSError, safeio.SafeIOError) as exc:
        raise ControlError("item control lock was detached") from exc
    if (not stat.S_ISREG(opened.st_mode) or
            not stat.S_ISREG(named.st_mode) or
            (opened.st_dev, opened.st_ino) != lock._lock_identity or
            (named.st_dev, named.st_ino) != lock._lock_identity):
        raise ControlError("item control lock identity changed")
    return lock


def _preflight_namespace_component(repo, item_id, component):
    """Read-only fast refusal for an already-hostile top-level namespace.

    The same component is reopened and validated after the item lock is held;
    this check exists so an obvious pre-existing symlink does not cause the
    otherwise-empty control directory to gain a lock artifact on refusal.
    """
    chain = None
    control_fd = None
    try:
        chain = safeio._open_root_chain(repo)
        for name in (".factory", "items", item_id):
            safeio._append_directory(chain, name)
        try:
            control_fd = os.open(
                "control", _DIRECTORY_FLAGS, dir_fd=chain[-1].fd)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise ControlError("cannot safely open control namespace") from exc
        try:
            details = os.stat(
                component, dir_fd=control_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise ControlError("cannot inspect control namespace") from exc
        if not stat.S_ISDIR(details.st_mode):
            raise ControlError("control namespace component is unsafe")
    except safeio.SafeIOError as exc:
        raise ControlError("cannot safely open item namespace") from exc
    finally:
        if control_fd is not None:
            os.close(control_fd)
        if chain is not None:
            safeio._close_chain(chain)


def _strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate object key")
        value[key] = item
    return value


def _reject_constant(_value):
    raise ValueError("invalid JSON constant")


def _canonical(value):
    try:
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False)
        # Round-trip to reject non-string mapping keys and non-JSON values and
        # to detach caller-owned mutable containers.
        parsed = json.loads(
            payload, object_pairs_hook=_strict_object,
            parse_constant=_reject_constant)
    except (TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ControlRefusal("control request is not canonical JSON") from exc
    return (payload + "\n").encode("utf-8"), parsed


def _digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _valid_digest(value):
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _read_bytes_at(directory_fd, name, *, limit=_READ_LIMIT, sync=False):
    _component(name, "control filename")
    try:
        fd = os.open(name, _FILE_READ_FLAGS, dir_fd=directory_fd)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ControlError("cannot safely open control artifact") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ControlError("control artifact is not a regular file")
        if limit is not None and before.st_size > limit:
            raise ControlError("control artifact exceeds its read limit")
        remaining = before.st_size
        chunks = []
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                raise ControlError("short read from control artifact")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise ControlError("control artifact grew while being read")
        if sync:
            os.fsync(fd)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        identity = _file_identity(before)
        if (not stat.S_ISREG(after.st_mode) or
                not stat.S_ISREG(named.st_mode) or
                _file_identity(after) != identity or
                _file_identity(named) != identity):
            raise ControlError("control artifact identity changed")
        if sync:
            os.fsync(directory_fd)
            final = os.fstat(fd)
            final_named = os.stat(
                name, dir_fd=directory_fd, follow_symlinks=False)
            if (_file_identity(final) != identity or
                    _file_identity(final_named) != identity):
                raise ControlError("control artifact identity changed")
        return b"".join(chunks), identity
    except FileNotFoundError as exc:
        raise ControlError("control artifact was detached") from exc
    except OSError as exc:
        raise ControlError("control artifact could not be made durable") from exc
    finally:
        os.close(fd)


def _read_optional_bytes(directory_fd, name, *, limit=_READ_LIMIT, sync=False):
    try:
        return _read_bytes_at(directory_fd, name, limit=limit, sync=sync)
    except FileNotFoundError:
        return None


def _decode_canonical_object(data, label):
    try:
        value = json.loads(
            data.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant)
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ControlRefusal(f"{label} is invalid") from exc
    if type(value) is not dict:
        raise ControlRefusal(f"{label} is invalid")
    try:
        canonical, _ = _canonical(value)
    except ControlRefusal as exc:
        raise ControlRefusal(f"{label} is invalid") from exc
    if data != canonical:
        raise ControlRefusal(f"{label} is not canonical")
    return value


def _publish_immutable(directory_fd, name, data, *, read_limit=None):
    if read_limit is None:
        read_limit = len(data)
    if len(data) > read_limit:
        raise ControlRefusal(
            "immutable control artifact exceeds its read limit")
    existing = _read_optional_bytes(
        directory_fd, name, limit=read_limit, sync=True)
    if existing is not None:
        if existing[0] != data:
            raise ControlRefusal("immutable control artifact conflicts")
        return existing[1]
    try:
        inode = safeio._publish_bound(directory_fd, name, data)
    except safeio.SafeIOError:
        existing = _read_optional_bytes(
            directory_fd, name, limit=read_limit, sync=True)
        if existing is None or existing[0] != data:
            raise ControlRefusal("immutable control artifact conflicts") from None
        return existing[1]
    reread, identity = _read_bytes_at(
        directory_fd, name, limit=read_limit, sync=True)
    if reread != data or identity[:2] != inode:
        raise ControlError("published control artifact changed")
    return identity


def _remove_exact(directory_fd, name, identity):
    try:
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as exc:
        raise ControlError("control marker was detached") from exc
    if _file_identity(named) != identity:
        raise ControlError("control marker identity changed")
    try:
        os.unlink(name, dir_fd=directory_fd)
        os.fsync(directory_fd)
    except OSError as exc:
        raise ControlError("cannot durably remove control marker") from exc


def _snapshot_record(snapshot):
    if isinstance(snapshot, safeio.FileSnapshot):
        return {
            "state": "file",
            "root": str(snapshot.root),
            "relative": snapshot.relative.as_posix(),
            "sha256": snapshot.sha256,
            "blob": snapshot.sha256,
            "file_identity": list(snapshot.file_identity),
            "directory_identities": [list(value)
                                     for value in snapshot.directory_identities],
        }
    if isinstance(snapshot, safeio.MissingSnapshot):
        return {
            "state": "missing",
            "root": str(snapshot.root),
            "relative": snapshot.relative.as_posix(),
            "parent_identities": [list(value)
                                  for value in snapshot.parent_identities],
            "transaction_nonce": snapshot.transaction_nonce,
        }
    raise ControlRefusal("control request contains an invalid snapshot")


def _integer_tuple(value, length, label):
    if (type(value) is not list or len(value) != length or
            any(type(item) is not int for item in value)):
        raise ControlRefusal(f"{label} is invalid")
    return tuple(value)


def _directory_tuples(value, label):
    if type(value) is not list or not value:
        raise ControlRefusal(f"{label} is invalid")
    return tuple(_integer_tuple(item, 2, label) for item in value)


def _validate_snapshot_record(record, *, expected_repo=None):
    if type(record) is not dict or record.get("state") not in ("file", "missing"):
        raise ControlRefusal("snapshot record is invalid")
    common = {"state", "root", "relative"}
    if record["state"] == "file":
        expected = common | {"sha256", "blob", "file_identity",
                             "directory_identities"}
    else:
        expected = common | {"parent_identities", "transaction_nonce"}
    if set(record) != expected:
        raise ControlRefusal("snapshot record is invalid")
    if type(record.get("root")) is not str or type(record.get("relative")) is not str:
        raise ControlRefusal("snapshot record is invalid")
    try:
        root = safeio._resolve_root(record["root"])
        relative = safeio._relative_path(record["relative"])
    except safeio.SafeIOError as exc:
        raise ControlRefusal("snapshot record is invalid") from exc
    if str(root) != record["root"]:
        raise ControlRefusal("snapshot root is not canonical")
    if expected_repo is not None and root != expected_repo:
        raise ControlRefusal("snapshot is outside the operation repository")
    if record["state"] == "file":
        if (not _valid_digest(record.get("sha256")) or
                record.get("blob") != record.get("sha256")):
            raise ControlRefusal("snapshot record is invalid")
        _integer_tuple(record["file_identity"], 5, "file identity")
        _directory_tuples(
            record["directory_identities"], "directory identity")
    else:
        _directory_tuples(record["parent_identities"], "directory identity")
        if (type(record.get("transaction_nonce")) is not str or
                _NONCE.fullmatch(record["transaction_nonce"]) is None):
            raise ControlRefusal("snapshot record is invalid")
    return root, relative


def _snapshot_from_record(record, blobs, *, expected_repo):
    root, relative = _validate_snapshot_record(
        record, expected_repo=expected_repo)
    if record["state"] == "file":
        digest = record["blob"]
        try:
            data = blobs[digest]
        except KeyError as exc:
            raise ControlRefusal("snapshot blob is missing") from exc
        if _digest_bytes(data) != digest:
            raise ControlRefusal("snapshot blob does not match its name")
        return safeio.FileSnapshot(
            root=root,
            relative=relative,
            data=data,
            sha256=digest,
            file_identity=_integer_tuple(
                record["file_identity"], 5, "file identity"),
            directory_identities=_directory_tuples(
                record["directory_identities"], "directory identity"),
        )
    return safeio.MissingSnapshot(
        root=root,
        relative=relative,
        parent_identities=_directory_tuples(
            record["parent_identities"], "directory identity"),
        transaction_nonce=record["transaction_nonce"],
    )


def _snapshot_key(record):
    return record["root"], record["relative"]


def _collect_snapshot_blob(snapshot, blobs):
    if isinstance(snapshot, safeio.FileSnapshot):
        if _digest_bytes(snapshot.data) != snapshot.sha256:
            raise ControlRefusal("snapshot bytes do not match their digest")
        previous = blobs.setdefault(snapshot.sha256, snapshot.data)
        if previous != snapshot.data:
            raise ControlRefusal("snapshot digest collision")


def _validate_operation_blobs(blobs):
    for data in blobs.values():
        if len(data) > _OPERATION_BLOB_LIMIT:
            raise ControlRefusal("operation blob exceeds its read limit")


def _checkout_identity(checkout):
    try:
        fd = os.open(checkout, _DIRECTORY_FLAGS)
    except OSError as exc:
        raise ControlRefusal("canonical checkout is unavailable") from exc
    try:
        details = os.fstat(fd)
        if not stat.S_ISDIR(details.st_mode):
            raise ControlRefusal("canonical checkout is unavailable")
        return _directory_identity(details)
    finally:
        os.close(fd)


def _require_clean_checkout(checkout):
    """Refuse dispatch from code state Git cannot reproduce exactly."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all",
             "--", ".", ":(exclude).factory/**"],
            cwd=checkout, capture_output=True)
    except (OSError, UnicodeError) as exc:
        raise ControlRefusal(
            "canonical implementation checkout cannot be inspected") from exc
    if result.returncode != 0:
        raise ControlRefusal(
            "canonical implementation checkout cannot be inspected")
    if result.stdout:
        raise ControlRefusal(
            "canonical implementation checkout is dirty")


def _owner_token(owner_token):
    if owner_token is None:
        owner_token = os.environ.get("FACTORY_IMPLEMENTATION_OWNER")
    if type(owner_token) is not str or not owner_token:
        raise ControlRefusal("ownership token is required")
    return owner_token


def _reject_token_bytes(token, artifacts):
    encoded = token.encode("utf-8")
    if any(encoded in artifact for artifact in artifacts):
        raise ControlRefusal("ownership token cannot be persisted")


def _operation_token_bytes(artifacts):
    token = os.environ.get("FACTORY_IMPLEMENTATION_OWNER")
    if type(token) is str and token:
        _reject_token_bytes(token, artifacts)


def _verify_owner(repo, item_id, owner_token):
    token = _owner_token(owner_token)
    try:
        verified = ownership.verify(repo, item_id, token)
    except ownership.OwnershipError as exc:
        raise ControlRefusal("implementation ownership does not match") from exc
    return token, verified


def _config_from_snapshot(snapshot):
    try:
        value = json.loads(
            snapshot.data.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant)
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ControlRefusal("ticket configuration is invalid") from exc
    errors = validate(value, initrepo.load_schema("config"), "config")
    if type(value) is not dict or errors:
        raise ControlRefusal("ticket configuration is invalid")
    return config_state.ConfigSnapshot(file=snapshot, value=value)


def _ticket_identity(manifest):
    identity = dict(manifest)
    identity.pop("ticket_id", None)
    return _digest_bytes(_canonical(identity)[0])


def _require_ticket_manifest_limit(data):
    if len(data) > _TICKET_MANIFEST_LIMIT:
        raise ControlRefusal("ticket manifest exceeds its read limit")


def _require_ticket_blob_limits(blobs):
    if any(len(data) > _TICKET_BLOB_LIMIT for data in blobs):
        raise ControlRefusal("ticket blob exceeds its read limit")


def _validate_ticket_manifest(manifest, *, expected_repo=None):
    errors = validate(
        manifest, initrepo.load_schema("control-ticket"), "ticket")
    if errors:
        raise ControlRefusal("ticket manifest is invalid")
    expected = {"version", "ticket_id", "item", "kind", "key",
                "owner_sha256", "checkout", "checkout_identity", "config",
                "inputs", "metadata"}
    if (set(manifest) != expected or manifest.get("version") != 1 or
            not _valid_digest(manifest.get("ticket_id")) or
            not _valid_digest(manifest.get("owner_sha256")) or
            type(manifest.get("item")) is not str or
            type(manifest.get("kind")) is not str or not manifest["kind"] or
            type(manifest.get("key")) is not str or not manifest["key"] or
            type(manifest.get("checkout")) is not str or
            type(manifest.get("inputs")) is not list or
            type(manifest.get("metadata")) is not dict):
        raise ControlRefusal("ticket manifest is invalid")
    _component(manifest["item"], "ticket item")
    _integer_tuple(manifest["checkout_identity"], 2, "checkout identity")
    _validate_snapshot_record(manifest["config"], expected_repo=expected_repo)
    if manifest["config"].get("state") != "file":
        raise ControlRefusal("ticket configuration snapshot is invalid")
    for record in manifest["inputs"]:
        _validate_snapshot_record(record, expected_repo=expected_repo)
    if manifest["ticket_id"] != _ticket_identity(manifest):
        raise ControlRefusal("ticket identity does not match its manifest")


def _artifact_snapshot(
        repo, relative, expected=None, *, read_limit=_READ_LIMIT):
    try:
        snapshot = safeio.snapshot_path(repo, relative, limit=read_limit)
    except safeio.SafeIOError as exc:
        raise ControlError("control artifact is unsafe") from exc
    if expected is not None and snapshot.data != expected:
        raise ControlRefusal("control artifact conflicts")
    return snapshot


def _open_ticket_directory(tickets_fd, ticket_id, *, create=False):
    if not _valid_digest(ticket_id):
        raise ControlRefusal("ticket id is invalid")
    return _open_directory(tickets_fd, ticket_id, create=create)


def _ticket_manifest_from_dir(ticket_fd):
    result = _read_optional_bytes(
        ticket_fd, "manifest.json", limit=_TICKET_MANIFEST_LIMIT)
    if result is None:
        return None
    return _decode_canonical_object(result[0], "ticket manifest")


def _scan_ticket_conflicts(tickets_fd, own_id, kind, key, repo):
    try:
        names = os.listdir(tickets_fd)
    except OSError as exc:
        raise ControlError("cannot inspect ticket namespace") from exc
    for name in names:
        if not _valid_digest(name):
            raise ControlError("ticket namespace contains an invalid entry")
        directory_fd = _open_ticket_directory(tickets_fd, name)
        try:
            manifest = _ticket_manifest_from_dir(directory_fd)
            if manifest is None:
                if name == own_id:
                    continue
                raise ControlRefusal("ticket namespace contains an incomplete ticket")
            _validate_ticket_manifest(manifest, expected_repo=repo)
            if manifest["ticket_id"] != name:
                raise ControlRefusal("ticket directory identity conflicts")
            if (manifest["kind"], manifest["key"]) == (kind, key) and name != own_id:
                raise ControlRefusal("ticket request conflicts with an existing ticket")
        finally:
            os.close(directory_fd)


def issue_ticket(repo, item_id, *, kind, key, owner_token,
                 config, inputs, metadata):
    """Durably bind strict snapshots to the live implementation owner."""
    item_id = _component(item_id, "item id")
    if not isinstance(config, config_state.ConfigSnapshot):
        raise ControlRefusal("ticket requires a strict configuration snapshot")
    if type(kind) is not str or not kind or type(key) is not str or not key:
        raise ControlRefusal("ticket kind and key are required")
    try:
        inputs = tuple(inputs)
    except TypeError as exc:
        raise ControlRefusal("ticket inputs are invalid") from exc
    metadata_bytes, metadata = _canonical(metadata)
    if type(metadata) is not dict:
        raise ControlRefusal("ticket metadata must be an object")

    token, verified = _verify_owner(repo, item_id, owner_token)
    canonical_repo = safeio._resolve_root(repo)
    _require_clean_checkout(verified.checkout)
    try:
        config_state.revalidate(config)
        safeio.revalidate(inputs)
    except (config_state.ConfigStateError, safeio.SafeIOError) as exc:
        raise ControlRefusal("ticket snapshot changed before issue") from exc

    blobs = {}
    _collect_snapshot_blob(config.file, blobs)
    input_records = []
    input_keys = set()
    for snapshot in inputs:
        record = _snapshot_record(snapshot)
        _validate_snapshot_record(record, expected_repo=canonical_repo)
        snapshot_key = _snapshot_key(record)
        if snapshot_key in input_keys:
            raise ControlRefusal("ticket has a duplicate input snapshot")
        input_keys.add(snapshot_key)
        input_records.append(record)
        _collect_snapshot_blob(snapshot, blobs)
    config_record = _snapshot_record(config.file)
    _validate_snapshot_record(config_record, expected_repo=canonical_repo)
    _require_ticket_blob_limits(blobs.values())
    manifest = {
        "version": 1,
        "item": item_id,
        "kind": kind,
        "key": key,
        "owner_sha256": verified.owner_sha256,
        "checkout": str(verified.checkout),
        "checkout_identity": list(_checkout_identity(verified.checkout)),
        "config": config_record,
        "inputs": input_records,
        "metadata": metadata,
    }
    manifest["ticket_id"] = _ticket_identity(manifest)
    manifest_bytes, manifest = _canonical(manifest)
    _require_ticket_manifest_limit(manifest_bytes)
    _reject_token_bytes(
        token, [metadata_bytes, manifest_bytes, *blobs.values()])
    _validate_ticket_manifest(manifest, expected_repo=canonical_repo)

    _preflight_namespace_component(canonical_repo, item_id, "tickets")
    with item_lock(canonical_repo, item_id) as lock:
        try:
            ownership.revalidate(verified)
        except ownership.OwnershipError as exc:
            raise ControlRefusal(
                "implementation ownership changed during ticket issue") from exc
        _require_clean_checkout(verified.checkout)
        tickets_pin = _pin_directory(
            lock._control_fd, "tickets", create=True)
        ticket_pin = None
        blobs_pin = None
        try:
            _scan_ticket_conflicts(
                tickets_pin.fd, manifest["ticket_id"], kind, key,
                canonical_repo)
            ticket_pin = _pin_directory(
                tickets_pin.fd, manifest["ticket_id"], create=True)
            blobs_pin = _pin_directory(
                ticket_pin.fd, "blobs", create=True)
            _validate_pins(lock, tickets_pin, ticket_pin, blobs_pin)
            for digest, data in blobs.items():
                _publish_immutable(
                    blobs_pin.fd, digest, data,
                    read_limit=_TICKET_BLOB_LIMIT)
                _validate_pins(lock, tickets_pin, ticket_pin, blobs_pin)
            _publish_immutable(
                ticket_pin.fd, "manifest.json", manifest_bytes,
                read_limit=_TICKET_MANIFEST_LIMIT)
            _validate_pins(lock, tickets_pin, ticket_pin, blobs_pin)
            try:
                ownership.revalidate(verified)
            except ownership.OwnershipError as exc:
                raise ControlRefusal(
                    "implementation ownership changed during ticket issue") from exc
            try:
                config_state.revalidate(config)
                safeio.revalidate(inputs)
            except (config_state.ConfigStateError, safeio.SafeIOError) as exc:
                raise ControlRefusal(
                    "ticket snapshot changed during issue") from exc
            _sync_pins(lock, tickets_pin, ticket_pin, blobs_pin)
        finally:
            _close_pin(blobs_pin)
            _close_pin(ticket_pin)
            _close_pin(tickets_pin)
    return load_ticket(
        canonical_repo, item_id, manifest["ticket_id"], owner_token=token)


def _load_ticket_blobs(repo, item_id, ticket_id, manifest, blobs_fd=None):
    records = [manifest["config"], *manifest["inputs"]]
    snapshots = []
    values = {}
    for record in records:
        if record["state"] != "file":
            continue
        digest = record["blob"]
        if digest in values:
            continue
        relative = (f".factory/items/{item_id}/control/tickets/"
                    f"{ticket_id}/blobs/{digest}")
        pinned = None
        if blobs_fd is not None:
            pinned = _read_bytes_at(
                blobs_fd, digest, limit=_TICKET_BLOB_LIMIT, sync=True)
        snapshot = _artifact_snapshot(
            repo, relative, read_limit=_TICKET_BLOB_LIMIT)
        if (snapshot.sha256 != digest or
                (pinned is not None and
                 (pinned[0] != snapshot.data or
                  pinned[1] != snapshot.file_identity))):
            raise ControlRefusal("ticket blob does not match its name")
        values[digest] = snapshot.data
        snapshots.append(snapshot)
    return values, tuple(snapshots)


def load_ticket(repo, item_id, ticket_id, *, owner_token=None,
                revalidate_inputs=True):
    item_id = _component(item_id, "item id")
    token, verified = _verify_owner(repo, item_id, owner_token)
    canonical_repo = safeio._resolve_root(repo)
    if not _valid_digest(ticket_id):
        raise ControlRefusal("ticket id is invalid")
    with item_lock(canonical_repo, item_id) as lock:
        tickets_pin = _pin_directory(lock._control_fd, "tickets")
        ticket_pin = None
        blobs_pin = None
        try:
            ticket_pin = _pin_directory(tickets_pin.fd, ticket_id)
            blobs_pin = _pin_directory(ticket_pin.fd, "blobs")
            _validate_pins(lock, tickets_pin, ticket_pin, blobs_pin)
            raw, manifest_identity = _read_bytes_at(
                ticket_pin.fd, "manifest.json",
                limit=_TICKET_MANIFEST_LIMIT, sync=True)
            manifest = _decode_canonical_object(raw, "ticket manifest")
            _validate_ticket_manifest(manifest, expected_repo=canonical_repo)
            if manifest["ticket_id"] != ticket_id:
                raise ControlRefusal("ticket directory identity conflicts")
            if (manifest["item"] != item_id or
                    manifest["owner_sha256"] != verified.owner_sha256 or
                    manifest["checkout"] != str(verified.checkout) or
                    tuple(manifest["checkout_identity"]) !=
                    _checkout_identity(verified.checkout)):
                raise ControlRefusal(
                    "ticket ownership or checkout does not match")
            _reject_token_bytes(token, [raw])
            blobs, blob_snapshots = _load_ticket_blobs(
                canonical_repo, item_id, ticket_id, manifest,
                blobs_fd=blobs_pin.fd)
            _reject_token_bytes(token, [*blobs.values()])
            config_file = _snapshot_from_record(
                manifest["config"], blobs, expected_repo=canonical_repo)
            config = _config_from_snapshot(config_file)
            input_snapshots = tuple(
                _snapshot_from_record(record, blobs,
                                      expected_repo=canonical_repo)
                for record in manifest["inputs"])
            manifest_snapshot = _artifact_snapshot(
                canonical_repo,
                (f".factory/items/{item_id}/control/tickets/"
                 f"{ticket_id}/manifest.json"),
                expected=raw, read_limit=_TICKET_MANIFEST_LIMIT)
            if manifest_snapshot.file_identity != manifest_identity:
                raise ControlRefusal("ticket manifest identity changed")
            ticket = DurableTicket(
                repo=canonical_repo,
                item_id=item_id,
                ticket_id=ticket_id,
                kind=manifest["kind"],
                key=manifest["key"],
                owner_sha256=manifest["owner_sha256"],
                checkout=Path(manifest["checkout"]),
                checkout_identity=tuple(manifest["checkout_identity"]),
                config=config,
                inputs=input_snapshots,
                metadata=manifest["metadata"],
                manifest=JSONSnapshot(file=manifest_snapshot, value=manifest),
                _owner=verified,
                _artifacts=(manifest_snapshot, *blob_snapshots),
            )
            if revalidate_inputs:
                revalidate_ticket(ticket)
            else:
                revalidate_ticket_authority(ticket)
            _sync_pins(lock, tickets_pin, ticket_pin, blobs_pin)
            return ticket
        finally:
            _close_pin(blobs_pin)
            _close_pin(ticket_pin)
            _close_pin(tickets_pin)


def revalidate_ticket_authority(ticket) -> None:
    """Revalidate durable ticket/owner authority, excluding source inputs."""
    if not isinstance(ticket, DurableTicket):
        raise ControlRefusal("durable ticket is invalid")
    _require_ticket_manifest_limit(ticket.manifest.file.data)
    _require_ticket_blob_limits(
        snapshot.data for snapshot in ticket._artifacts[1:])
    try:
        ownership.revalidate(ticket._owner)
        if _checkout_identity(ticket.checkout) != ticket.checkout_identity:
            raise ControlRefusal("ticket checkout identity changed")
        safeio.revalidate(ticket._artifacts)
    except (ownership.OwnershipError, safeio.SafeIOError) as exc:
        raise ControlRefusal("durable ticket authority changed") from exc


def revalidate_ticket(ticket) -> None:
    revalidate_ticket_authority(ticket)
    try:
        config_state.revalidate(ticket.config)
        safeio.revalidate(ticket.inputs)
    except (config_state.ConfigStateError, safeio.SafeIOError) as exc:
        raise ControlRefusal("durable ticket no longer matches live state") from exc


def _normalize_events(events):
    try:
        events = tuple(events)
    except TypeError as exc:
        raise ControlRefusal("operation events are invalid") from exc
    normalized = []
    for event in events:
        _raw, value = _canonical(event)
        if (type(value) is not dict or
                set(value) not in ({"event", "ts"},
                                   {"event", "ts", "data"}) or
                type(value.get("event")) is not str or not value["event"] or
                type(value.get("ts")) is not str or not value["ts"]):
            raise ControlRefusal("operation event is invalid")
        normalized.append(value)
    encodings = [_canonical(value)[0] for value in normalized]
    if len(set(encodings)) != len(encodings):
        raise ControlRefusal("operation contains a duplicate event")
    return normalized


def _operation_identity(intent):
    events = []
    for event in intent["events"]:
        value = dict(event)
        value.pop("operation_id", None)
        events.append(value)
    identity = {
        "version": 1,
        "item": intent["item"],
        "kind": intent["kind"],
        "key": intent["key"],
        "request_sha256": intent["request_sha256"],
        "prerequisites": intent["prerequisites"],
        "replacements": intent["replacements"],
        "events": events,
    }
    if "log_snapshot" in intent:
        identity["log_snapshot"] = intent["log_snapshot"]
    return _digest_bytes(_canonical(identity)[0])


def _require_intent_record_limit(data):
    if len(data) > _INTENT_RECORD_LIMIT:
        raise ControlRefusal("operation intent exceeds its read limit")


def _build_intent(repo, item_id, kind, key, request, prerequisites,
                  replacements, events, log_snapshot=None):
    canonical_repo = safeio._resolve_root(repo)
    if type(kind) is not str or not kind or type(key) is not str or not key:
        raise ControlRefusal("operation kind and key are required")
    request_bytes, _request = _canonical(request)
    try:
        prerequisites = tuple(prerequisites)
        replacements = tuple(replacements)
    except TypeError as exc:
        raise ControlRefusal("operation snapshots are invalid") from exc
    events = _normalize_events(events)
    blobs = {}
    prerequisite_records = []
    replacement_records = []
    prerequisite_keys = set()
    replacement_keys = set()
    log_record = None
    if log_snapshot is not None:
        if not isinstance(
                log_snapshot, (safeio.FileSnapshot, safeio.MissingSnapshot)):
            raise ControlRefusal("operation log snapshot is invalid")
        log_record = _snapshot_record(log_snapshot)
        _validate_snapshot_record(log_record, expected_repo=canonical_repo)
        expected_log = f".factory/items/{item_id}/log.jsonl"
        if (log_record["root"] != str(canonical_repo) or
                log_record["relative"] != expected_log):
            raise ControlRefusal("operation log snapshot path is invalid")
        _collect_snapshot_blob(log_snapshot, blobs)
    for snapshot in prerequisites:
        record = _snapshot_record(snapshot)
        _validate_snapshot_record(record, expected_repo=canonical_repo)
        key_tuple = _snapshot_key(record)
        if key_tuple in prerequisite_keys:
            raise ControlRefusal("operation has a duplicate prerequisite")
        prerequisite_keys.add(key_tuple)
        prerequisite_records.append(record)
        _collect_snapshot_blob(snapshot, blobs)
    for replacement in replacements:
        if (type(replacement) not in (tuple, list) or len(replacement) != 2 or
                not isinstance(replacement[1], bytes)):
            raise ControlRefusal("operation replacement is invalid")
        before, after = replacement
        before_record = _snapshot_record(before)
        _validate_snapshot_record(before_record, expected_repo=canonical_repo)
        key_tuple = _snapshot_key(before_record)
        if key_tuple in replacement_keys:
            raise ControlRefusal("operation has a duplicate replacement")
        if key_tuple in prerequisite_keys:
            raise ControlRefusal(
                "operation prerequisite cannot also be a replacement")
        replacement_keys.add(key_tuple)
        if isinstance(before, safeio.MissingSnapshot):
            try:
                safeio.preflight_publication(before, after)
            except safeio.SafeIOError as exc:
                raise ControlRefusal(str(exc)) from exc
        _collect_snapshot_blob(before, blobs)
        after_digest = _digest_bytes(after)
        previous = blobs.setdefault(after_digest, after)
        if previous != after:
            raise ControlRefusal("operation blob digest collision")
        replacement_records.append({
            "before": before_record,
            "after_sha256": after_digest,
            "after_blob": after_digest,
        })
    if log_record is not None:
        log_key = _snapshot_key(log_record)
        if log_key in prerequisite_keys or log_key in replacement_keys:
            raise ControlRefusal(
                "operation log snapshot overlaps another snapshot")
    _validate_operation_blobs(blobs)
    intent = {
        "version": 1,
        "operation_id": "0" * 64,
        "item": item_id,
        "kind": kind,
        "key": key,
        "request_sha256": _digest_bytes(request_bytes),
        "prerequisites": prerequisite_records,
        "replacements": replacement_records,
        "events": events,
    }
    if log_record is not None:
        intent["log_snapshot"] = log_record
    operation_id = _operation_identity(intent)
    intent["operation_id"] = operation_id
    intent["events"] = [
        {**event, "operation_id": operation_id} for event in events]
    intent_bytes, intent = _canonical(intent)
    # This refusal precedes namespace preflight, item_lock, and every effect.
    # The same ceiling is used by conflict, retry, and recovery reads below.
    _require_intent_record_limit(intent_bytes)
    _validate_intent(intent, expected_repo=canonical_repo)
    _operation_token_bytes(
        [request_bytes, intent_bytes, *blobs.values()])
    return intent, intent_bytes, blobs


def _validate_intent(intent, *, expected_repo=None):
    errors = validate(
        intent, initrepo.load_schema("control-intent"), "intent")
    required = {"version", "operation_id", "item", "kind", "key",
                "request_sha256", "prerequisites", "replacements", "events"}
    if (errors or type(intent) is not dict or
            set(intent) not in (required, required | {"log_snapshot"}) or
            intent.get("version") != 1 or
            not _valid_digest(intent.get("operation_id")) or
            not _valid_digest(intent.get("request_sha256")) or
            type(intent.get("item")) is not str or
            type(intent.get("kind")) is not str or not intent["kind"] or
            type(intent.get("key")) is not str or not intent["key"] or
            type(intent.get("prerequisites")) is not list or
            type(intent.get("replacements")) is not list or
            type(intent.get("events")) is not list):
        raise ControlRefusal("operation intent is invalid")
    _component(intent["item"], "intent item")
    prerequisite_keys = set()
    for record in intent["prerequisites"]:
        _validate_snapshot_record(record, expected_repo=expected_repo)
        key_tuple = _snapshot_key(record)
        if key_tuple in prerequisite_keys:
            raise ControlRefusal("operation intent is invalid")
        prerequisite_keys.add(key_tuple)
    replacement_keys = set()
    for replacement in intent["replacements"]:
        if (type(replacement) is not dict or
                set(replacement) != {"before", "after_sha256", "after_blob"} or
                not _valid_digest(replacement.get("after_sha256")) or
                replacement.get("after_blob") !=
                replacement.get("after_sha256")):
            raise ControlRefusal("operation intent is invalid")
        _validate_snapshot_record(
            replacement["before"], expected_repo=expected_repo)
        key_tuple = _snapshot_key(replacement["before"])
        if key_tuple in replacement_keys or key_tuple in prerequisite_keys:
            raise ControlRefusal("operation intent is invalid")
        replacement_keys.add(key_tuple)
    if "log_snapshot" in intent:
        record = intent["log_snapshot"]
        _validate_snapshot_record(record, expected_repo=expected_repo)
        expected_log = f".factory/items/{intent['item']}/log.jsonl"
        key_tuple = _snapshot_key(record)
        if (record["relative"] != expected_log or
                key_tuple in prerequisite_keys or
                key_tuple in replacement_keys):
            raise ControlRefusal("operation intent is invalid")
    event_encodings = set()
    for event in intent["events"]:
        if (type(event) is not dict or
                set(event) not in ({"event", "ts", "operation_id"},
                                   {"event", "ts", "operation_id", "data"}) or
                type(event.get("event")) is not str or not event["event"] or
                type(event.get("ts")) is not str or not event["ts"] or
                event.get("operation_id") != intent["operation_id"]):
            raise ControlRefusal("operation intent is invalid")
        encoded = _canonical(event)[0]
        if encoded in event_encodings:
            raise ControlRefusal("operation intent has a duplicate event")
        event_encodings.add(encoded)
    if intent["operation_id"] != _operation_identity(intent):
        raise ControlRefusal("operation identity does not match its intent")


def _open_operation_directory(operations_fd, operation_id, *, create=False):
    if not _valid_digest(operation_id):
        raise ControlRefusal("operation id is invalid")
    return _open_directory(operations_fd, operation_id, create=create)


def _intent_from_directory(operation_fd, repo):
    result = _read_optional_bytes(
        operation_fd, "intent.json", limit=_INTENT_RECORD_LIMIT)
    if result is None:
        return None, None, None
    intent = _decode_canonical_object(result[0], "operation intent")
    _validate_intent(intent, expected_repo=repo)
    return intent, result[0], result[1]


def _scan_operation_conflicts(operations_fd, expected, repo):
    try:
        names = os.listdir(operations_fd)
    except OSError as exc:
        raise ControlError("cannot inspect operation namespace") from exc
    own_found = False
    for name in names:
        if not _valid_digest(name):
            raise ControlError("operation namespace contains an invalid entry")
        operation_fd = _open_operation_directory(operations_fd, name)
        try:
            intent, raw, _identity = _intent_from_directory(operation_fd, repo)
            if intent is None:
                if name == expected["operation_id"]:
                    own_found = True
                    continue
                raise ControlRefusal(
                    "operation namespace contains an incomplete operation")
            if intent["operation_id"] != name:
                raise ControlRefusal("operation directory identity conflicts")
            if name == expected["operation_id"]:
                own_found = True
                if raw != _canonical(expected)[0]:
                    raise ControlRefusal("operation intent conflicts")
            elif ((intent["kind"], intent["key"]) ==
                  (expected["kind"], expected["key"])):
                raise ControlRefusal(
                    "operation request conflicts with an existing operation")
        finally:
            os.close(operation_fd)
    return own_found


def _parse_strict_log(raw):
    """Parse one already captured, complete authoritative log image."""
    if raw and not raw.endswith(b"\n"):
        raise ControlRefusal("item log is missing its final newline")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ControlRefusal("item log is invalid UTF-8") from exc
    events = []
    seen = set()
    for line in text.splitlines():
        if not line:
            raise ControlRefusal("item log contains an empty record")
        try:
            event = json.loads(
                line, object_pairs_hook=_strict_object,
                parse_constant=_reject_constant)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ControlRefusal("item log contains invalid JSON") from exc
        if (type(event) is not dict or
                type(event.get("event")) is not str or not event["event"] or
                type(event.get("ts")) is not str or not event["ts"]):
            raise ControlRefusal("item log contains an invalid event")
        operation_id = event.get("operation_id")
        if operation_id is not None:
            if not _valid_digest(operation_id):
                raise ControlRefusal("item log contains an invalid operation id")
            identity = (operation_id, _digest_bytes(_canonical(event)[0]))
            if identity in seen:
                raise ControlRefusal("item log contains a duplicate operation event")
            seen.add(identity)
        events.append(event)
    return events


def _strict_log_bytes_at(item_fd, *, sync=False):
    """Return one fully validated, descriptor-relative log byte image."""
    result = _read_optional_bytes(
        item_fd, "log.jsonl", limit=_LOG_IMAGE_LIMIT, sync=sync)
    raw = b"" if result is None else result[0]
    _parse_strict_log(raw)
    return raw


def _strict_log_image_at(item_fd, *, sync=False):
    """Return the fully validated authoritative log and its exact byte size."""
    raw = _strict_log_bytes_at(item_fd, sync=sync)
    events = _parse_strict_log(raw)
    return events, len(raw)


def _strict_log_image(lock, *, sync=False):
    return _strict_log_image_at(lock._item_fd, sync=sync)


def _strict_log(lock, *, sync=False):
    return _strict_log_image(lock, sync=sync)[0]


def _event_prefix(events, intended, operation_id):
    existing = [event for event in events
                if event.get("operation_id") == operation_id]
    existing_bytes = [_canonical(event)[0] for event in existing]
    intended_bytes = [
        _canonical(event)[0] for event in intended[:len(existing)]]
    if (len(existing) > len(intended) or
            existing_bytes != intended_bytes):
        raise ControlRefusal("item log conflicts with operation events")
    return len(existing)


def _log_authority_name(index):
    return f"log-{index:08d}.authority"


def _require_log_authority(operation_pin, index, expected, identity, *,
                           sync=False):
    if operation_pin is None:
        return
    try:
        authority, authority_identity = _read_bytes_at(
            operation_pin.fd, _log_authority_name(index),
            limit=max(len(expected), 1), sync=sync)
    except FileNotFoundError as exc:
        raise ControlRefusal(
            "operation log identity authority is missing") from exc
    if (authority != expected or
            authority_identity[:2] != identity[:2]):
        raise ControlRefusal("operation log identity authority conflicts")


def _authorized_log_prefix_at(item_fd, intent, blobs, *, sync=False,
                              operation_pin=None):
    """Validate the exact captured log plus this operation's event prefix."""
    record = intent.get("log_snapshot")
    if record is None:
        events, size = _strict_log_image_at(item_fd, sync=sync)
        return _event_prefix(
            events, intent["events"], intent["operation_id"]), size

    if record["state"] == "file":
        try:
            captured = blobs[record["blob"]]
        except KeyError as exc:
            raise ControlRefusal("operation log snapshot blob is missing") from exc
    else:
        captured = b""
    current = _read_optional_bytes(
        item_fd, "log.jsonl", limit=_LOG_IMAGE_LIMIT, sync=sync)
    raw = b"" if current is None else current[0]
    if captured and not captured.endswith(b"\n"):
        raise ControlRefusal("item log is missing its final newline")
    candidate = captured
    if raw == candidate:
        if record["state"] == "file":
            expected_identity = _integer_tuple(
                record.get("file_identity"), 5, "log file identity")
            if current is None or current[1] != expected_identity:
                raise ControlRefusal("operation log snapshot identity changed")
        elif current is not None:
            raise ControlRefusal("operation missing log was created")
        return 0, len(raw)
    from . import logs
    for index, event in enumerate(intent["events"]):
        candidate += logs._entry_bytes(event)
        if raw == candidate:
            if current is None:
                raise ControlRefusal("operation log event identity is missing")
            _require_log_authority(
                operation_pin, index, candidate, current[1], sync=sync)
            return index + 1, len(raw)
        if len(candidate) > len(raw):
            break
    raise ControlRefusal("item log changed outside the prepared operation")


def _preflight_log_capacity_at(item_fd, intended, operation_id):
    """Refuse before effects when all missing event lines cannot fit."""
    events, current_size = _strict_log_image_at(item_fd)
    prefix = _event_prefix(events, intended, operation_id)
    from . import logs
    missing_size = sum(
        len(logs._entry_bytes(event)) for event in intended[prefix:])
    if current_size + missing_size > _LOG_IMAGE_LIMIT:
        raise ControlRefusal("item log image exceeds its read limit")
    return prefix


def _preflight_log_capacity(lock, intended, operation_id):
    return _preflight_log_capacity_at(
        lock._item_fd, intended, operation_id)


def _preflight_intent_log_capacity_at(item_fd, intent, blobs, *, sync=False,
                                      operation_pin=None):
    prefix, current_size = _authorized_log_prefix_at(
        item_fd, intent, blobs, sync=sync, operation_pin=operation_pin)
    from . import logs
    missing_size = sum(
        len(logs._entry_bytes(event))
        for event in intent["events"][prefix:])
    if current_size + missing_size > _LOG_IMAGE_LIMIT:
        raise ControlRefusal("item log image exceeds its read limit")
    return prefix


def _preflight_intent_log_capacity(lock, intent, blobs, *, sync=False,
                                   operation_pin=None):
    return _preflight_intent_log_capacity_at(
        lock._item_fd, intent, blobs, sync=sync,
        operation_pin=operation_pin)


def _load_blobs(blobs_pin, intent, *, sync=False):
    digests = []
    log_record = intent.get("log_snapshot")
    if log_record is not None and log_record["state"] == "file":
        digests.append(log_record["blob"])
    for record in intent["prerequisites"]:
        if record["state"] == "file":
            digests.append(record["blob"])
    for replacement in intent["replacements"]:
        before = replacement["before"]
        if before["state"] == "file":
            digests.append(before["blob"])
        digests.append(replacement["after_blob"])
    values = {}
    identities = {}
    for digest in dict.fromkeys(digests):
        data, identity = _read_bytes_at(
            blobs_pin.fd, digest, limit=_OPERATION_BLOB_LIMIT, sync=sync)
        if _digest_bytes(data) != digest:
            raise ControlRefusal("operation blob does not match its name")
        values[digest] = data
        identities[digest] = identity
    _operation_token_bytes(values.values())
    return values, identities


def _revalidate_snapshot(snapshot, message, *, sync=False):
    try:
        if not sync:
            safeio.revalidate(snapshot)
            return
        chain = safeio._open_expected_parent(snapshot)
        try:
            if isinstance(snapshot, safeio.FileSnapshot):
                data, identity = _read_bytes_at(
                    chain[-1].fd, snapshot.relative.name,
                    limit=max(len(snapshot.data), 1), sync=True)
                if (data != snapshot.data or identity != snapshot.file_identity or
                        _digest_bytes(data) != snapshot.sha256):
                    raise ControlRefusal(message)
            else:
                relative_count = safeio._relative_parent_count(snapshot)
                missing_component = snapshot.relative.parts[relative_count]
                safeio._require_absent(chain[-1].fd, missing_component)
            _sync_bound_chain(chain)
        finally:
            safeio._close_chain(chain)
    except (safeio.SafeIOError, ControlError) as exc:
        raise ControlRefusal(message) from exc


def _sync_bound_chain(chain):
    try:
        for handle in reversed(chain):
            os.fsync(handle.fd)
    except OSError as exc:
        raise ControlError(
            "operation effect namespace could not be made durable") from exc
    try:
        safeio._validate_chain(chain)
    except safeio.SafeIOError as exc:
        raise ControlRefusal(
            "operation effect namespace identity changed") from exc


def _replacement_state(replacement, blobs, repo, *, sync=False):
    before_record = replacement["before"]
    before = _snapshot_from_record(
        before_record, blobs, expected_repo=repo)
    after = blobs[replacement["after_blob"]]
    chain = None
    try:
        chain = safeio._open_expected_parent(before)
        if isinstance(before, safeio.MissingSnapshot):
            relative_count = safeio._relative_parent_count(before)
            for component in before.relative.parts[relative_count:-1]:
                try:
                    safeio._append_directory(chain, component)
                except safeio.SafeIOError as exc:
                    if isinstance(exc.__cause__, FileNotFoundError):
                        return "incomplete"
                    raise
        try:
            data, identity = _read_bytes_at(
                chain[-1].fd, before.relative.name,
                limit=max(len(before.data)
                          if isinstance(before, safeio.FileSnapshot) else 0,
                          len(after), 1),
                sync=sync)
        except FileNotFoundError:
            return "before" if isinstance(
                before, safeio.MissingSnapshot) else "third"
        safeio._validate_chain(chain)
        if sync:
            _sync_bound_chain(chain)
        if isinstance(before, safeio.FileSnapshot):
            if data == before.data:
                if (identity == before.file_identity and
                        _digest_bytes(data) == before.sha256):
                    return "before"
                # When before and after bytes are equal, a replacement inode
                # is still an unprovable same-byte substitution, not adoption.
                if after == before.data:
                    return "third"
        if (data == after and
                _digest_bytes(data) == replacement["after_sha256"]):
            return "after"
        return "third"
    except (safeio.SafeIOError, ControlError) as exc:
        raise ControlRefusal(
            "operation replacement namespace changed") from exc
    finally:
        if chain is not None:
            safeio._close_chain(chain)


def _missing_journal_present(snapshot):
    chain = None
    try:
        safeio._refuse_recovery_conflict(
            snapshot, include_snapshot_parent=False)
        chain = safeio._open_expected_parent(snapshot)
        try:
            os.stat(safeio._journal_name(snapshot.relative),
                    dir_fd=chain[-1].fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise ControlRefusal(
                "cannot inspect missing publication recovery state") from exc
        return True
    except safeio.SafeIOError as exc:
        raise ControlRefusal(
            "missing publication recovery state conflicts") from exc
    finally:
        if chain is not None:
            safeio._close_chain(chain)


def _replacement_authority_name(index):
    return f"replacement-{index:08d}.authority.json"


def _authority_record(intent, index, replacement, snapshot):
    return {
        "version": 1,
        "operation_id": intent["operation_id"],
        "replacement_index": index,
        "root": replacement["before"]["root"],
        "relative": replacement["before"]["relative"],
        "after_sha256": replacement["after_sha256"],
        "file_identity": list(snapshot.file_identity),
        "directory_identities": [
            list(value) for value in snapshot.directory_identities
        ],
    }


def _authority_snapshot(record, intent, index, replacement, blobs, repo):
    expected_keys = {
        "version", "operation_id", "replacement_index", "root", "relative",
        "after_sha256", "file_identity", "directory_identities",
    }
    before = replacement["before"]
    if (type(record) is not dict or set(record) != expected_keys or
            record.get("version") != 1 or
            record.get("operation_id") != intent["operation_id"] or
            record.get("replacement_index") != index or
            record.get("root") != before["root"] or
            record.get("relative") != before["relative"] or
            record.get("after_sha256") != replacement["after_sha256"]):
        raise ControlRefusal("operation replacement authority is invalid")
    root, relative = _validate_snapshot_record(before, expected_repo=repo)
    file_identity = _integer_tuple(
        record.get("file_identity"), 5, "file identity")
    directory_identities = _directory_tuples(
        record.get("directory_identities"), "directory identity")
    if (len(directory_identities) != len(root.parts) + len(relative.parts) - 1 or
            file_identity[2] != len(blobs[replacement["after_blob"]])):
        raise ControlRefusal("operation replacement authority is invalid")
    return safeio.FileSnapshot(
        root=root,
        relative=relative,
        data=blobs[replacement["after_blob"]],
        sha256=replacement["after_sha256"],
        file_identity=file_identity,
        directory_identities=directory_identities,
    )


def _load_replacement_authority(operation_pin, intent, index, replacement,
                                blobs, repo, *, sync=False):
    result = _read_optional_bytes(
        operation_pin.fd, _replacement_authority_name(index), sync=sync)
    if result is None:
        return None
    record = _decode_canonical_object(
        result[0], "operation replacement authority")
    return _authority_snapshot(
        record, intent, index, replacement, blobs, repo)


def _persist_replacement_authority(operation_pin, intent, index, replacement,
                                   blobs, repo, snapshot):
    expected = _authority_snapshot(
        _authority_record(intent, index, replacement, snapshot),
        intent, index, replacement, blobs, repo)
    if expected != snapshot:
        raise ControlRefusal("operation replacement authority conflicts")
    raw, _record = _canonical(
        _authority_record(intent, index, replacement, snapshot))
    identity = _publish_immutable(
        operation_pin.fd, _replacement_authority_name(index), raw)
    return expected, raw, identity


def _validate_persisted_replacement_authority(
        lock, pins, operation_pin, index, raw, identity):
    """Require the exact durable authority inode in the canonical WAL pin."""
    _validate_pins(lock, *pins)
    persisted, persisted_identity = _read_bytes_at(
        operation_pin.fd, _replacement_authority_name(index),
        limit=len(raw), sync=True)
    if persisted != raw or persisted_identity != identity:
        raise ControlRefusal(
            "operation replacement authority identity changed")
    _validate_pins(lock, *pins)


def _revalidate_replacement_authority(snapshot, message, *, sync=False):
    try:
        if not sync:
            safeio.revalidate(snapshot)
            return
        chain = safeio._open_expected_parent(snapshot)
        try:
            data, identity = _read_bytes_at(
                chain[-1].fd, snapshot.relative.name,
                limit=max(len(snapshot.data), 1), sync=True)
            if (data != snapshot.data or identity != snapshot.file_identity or
                    _digest_bytes(data) != snapshot.sha256):
                raise ControlRefusal(message)
            _sync_bound_chain(chain)
        finally:
            safeio._close_chain(chain)
    except (safeio.SafeIOError, ControlError) as exc:
        raise ControlRefusal(message) from exc


def _apply_replacement(replacement, blobs, repo):
    before_record = replacement["before"]
    before = _snapshot_from_record(
        before_record, blobs, expected_repo=repo)
    after = blobs[replacement["after_blob"]]
    if _digest_bytes(after) != replacement["after_sha256"]:
        raise ControlRefusal("operation replacement blob is invalid")
    state = _replacement_state(replacement, blobs, repo)
    published = None
    try:
        if isinstance(before, safeio.FileSnapshot):
            if state == "after":
                pass
            elif state == "before" and after == before.data:
                pass
            elif state == "before":
                safeio.replace_if_unchanged(before, after)
            else:
                raise safeio.SafeIOError(
                    "replacement is not at its original before state")
        else:
            if state == "after" and _missing_journal_present(before):
                # A retained journal must validate against the exact WAL
                # MissingSnapshot; bytes alone never suppress its refusal.
                published = safeio.publish_exclusive(
                    before, after, retain_authority=True)
            elif state == "after":
                # A completed publication whose journal was already removed is
                # adoptable only through the original ancestor descriptors.
                if _replacement_state(replacement, blobs, repo) != "after":
                    raise safeio.SafeIOError(
                        "published destination left its bound namespace")
            else:
                published = safeio.publish_exclusive(
                    before, after, retain_authority=True)
    except safeio.SafeIOError as exc:
        raise ControlRefusal("operation replacement is in a third state") from exc
    final_state = _replacement_state(replacement, blobs, repo, sync=True)
    if (final_state != "after" and not (
            isinstance(before, safeio.FileSnapshot) and
            after == before.data and final_state == "before")):
        raise ControlRefusal("operation replacement could not be verified")
    return published


def _expected_commit(intent):
    return {
        "version": 1,
        "operation_id": intent["operation_id"],
        "item": intent["item"],
        "kind": intent["kind"],
        "key": intent["key"],
        "request_sha256": intent["request_sha256"],
        "replacements": [
            {
                "root": replacement["before"]["root"],
                "relative": replacement["before"]["relative"],
                "sha256": replacement["after_sha256"],
            }
            for replacement in intent["replacements"]
        ],
        "events": [
            _digest_bytes(_canonical(event)[0]) for event in intent["events"]
        ],
    }


def _validate_commit(commit, intent):
    errors = validate(
        commit, initrepo.load_schema("control-commit"), "commit")
    if errors or commit != _expected_commit(intent):
        raise ControlRefusal("operation commit receipt is invalid")


def _receipt(commit):
    return CommitReceipt(
        operation_id=commit["operation_id"],
        item=commit["item"],
        kind=commit["kind"],
        key=commit["key"],
        request_sha256=commit["request_sha256"],
        replacements=tuple(
            (entry["root"], entry["relative"], entry["sha256"])
            for entry in commit["replacements"]),
        events=tuple(commit["events"]),
    )


def _active_record(lock):
    result = _read_optional_bytes(lock._control_fd, "active.json")
    if result is None:
        return None
    value = _decode_canonical_object(result[0], "active operation marker")
    if (set(value) != {"version", "operation_id"} or
            value.get("version") != 1 or
            not _valid_digest(value.get("operation_id"))):
        raise ControlRefusal("active operation marker is invalid")
    return value, result[1]


def _verify_effects(lock, operation_pin, intent, blobs, repo, *, sync=False):
    for record in intent["prerequisites"]:
        snapshot = _snapshot_from_record(record, blobs, expected_repo=repo)
        _revalidate_snapshot(
            snapshot, "operation prerequisite changed", sync=sync)
    for index, replacement in enumerate(intent["replacements"]):
        state = _replacement_state(
            replacement, blobs, repo, sync=sync)
        before = _snapshot_from_record(
            replacement["before"], blobs, expected_repo=repo)
        after = blobs[replacement["after_blob"]]
        if isinstance(before, safeio.MissingSnapshot):
            authority = _load_replacement_authority(
                operation_pin, intent, index, replacement, blobs, repo,
                sync=sync)
            if authority is None:
                raise ControlRefusal(
                    "committed replacement authority is missing")
            _revalidate_replacement_authority(
                authority, "committed replacement identity changed",
                sync=sync)
        if (state != "after" and not (
                isinstance(before, safeio.FileSnapshot) and
                after == before.data and state == "before")):
            raise ControlRefusal("committed replacement no longer matches")
    prefix, _size = _authorized_log_prefix_at(
        lock._item_fd, intent, blobs, sync=sync,
        operation_pin=operation_pin)
    if prefix != len(intent["events"]):
        raise ControlRefusal("committed operation event is missing")


def _sync_operation_artifacts(lock, pins, intent, intent_identity,
                              blobs, blob_identities, active_identity):
    operations_pin, operation_pin, blobs_pin = pins
    _validate_pins(lock, *pins)
    intent_bytes = _canonical(intent)[0]
    _require_intent_record_limit(intent_bytes)
    persisted_intent, persisted_identity = _read_bytes_at(
        operation_pin.fd, "intent.json", limit=_INTENT_RECORD_LIMIT,
        sync=True)
    if (persisted_intent != intent_bytes or
            persisted_identity != intent_identity):
        raise ControlRefusal("operation intent identity changed")
    for digest, expected in blobs.items():
        data, identity = _read_bytes_at(
            blobs_pin.fd, digest, limit=len(expected), sync=True)
        if data != expected or identity != blob_identities[digest]:
            raise ControlRefusal("operation blob identity changed")
    if active_identity is not None:
        active_bytes = _canonical({
            "version": 1,
            "operation_id": intent["operation_id"],
        })[0]
        persisted_active, persisted_active_identity = _read_bytes_at(
            lock._control_fd, "active.json", limit=len(active_bytes), sync=True)
        if (persisted_active != active_bytes or
                persisted_active_identity != active_identity):
            raise ControlRefusal("active operation marker identity changed")
    _sync_pins(lock, *pins)


def _settle_locked(lock, pins, intent, intent_identity, active_identity):
    repo = lock.repo
    operations_pin, operation_pin, blobs_pin = pins
    _validate_pins(lock, *pins)
    blobs, blob_identities = _load_blobs(blobs_pin, intent, sync=True)
    _validate_pins(lock, *pins)
    # Recovery must durably adopt the complete WAL namespace before it can
    # cause any effect.  Initial commits cross the same validation boundary
    # after publishing active.json, preserving one settle path for both cases.
    _sync_operation_artifacts(
        lock, pins, intent, intent_identity, blobs, blob_identities,
        active_identity)
    commit_result = _read_optional_bytes(
        operation_pin.fd, "commit.json", sync=True)
    if commit_result is not None:
        commit = _decode_canonical_object(
            commit_result[0], "operation commit receipt")
        _validate_commit(commit, intent)
        _sync_operation_artifacts(
            lock, pins, intent, intent_identity, blobs, blob_identities,
            active_identity)
        _verify_effects(
            lock, operation_pin, intent, blobs, repo, sync=True)
        _validate_pins(lock, *pins)
    else:
        # A malformed or unterminated authoritative log refuses before any
        # replacement effect, including during active recovery.
        _preflight_intent_log_capacity(
            lock, intent, blobs, operation_pin=operation_pin)
        for record in intent["prerequisites"]:
            snapshot = _snapshot_from_record(
                record, blobs, expected_repo=repo)
            _revalidate_snapshot(snapshot, "operation prerequisite changed")
        for index, replacement in enumerate(intent["replacements"]):
            before = _snapshot_from_record(
                replacement["before"], blobs, expected_repo=repo)
            authority = None
            if isinstance(before, safeio.MissingSnapshot):
                authority = _load_replacement_authority(
                    operation_pin, intent, index, replacement, blobs, repo,
                    sync=True)
                if authority is not None:
                    _revalidate_replacement_authority(
                        authority, "operation replacement identity changed",
                        sync=True)
                elif (_replacement_state(replacement, blobs, repo) == "after" and
                      not _missing_journal_present(before)):
                    raise ControlRefusal(
                        "operation replacement authority is missing")
            published = _apply_replacement(replacement, blobs, repo)
            if (isinstance(before, safeio.MissingSnapshot) and
                    published is not None):
                persisted_authority = _persist_replacement_authority(
                    operation_pin, intent, index, replacement, blobs, repo,
                    published)
                authority, authority_raw, authority_identity = (
                    persisted_authority)

                def validate_authority():
                    _validate_persisted_replacement_authority(
                        lock, pins, operation_pin, index, authority_raw,
                        authority_identity)

                # Do not surrender the source journal until the exact authority
                # bytes and inode have been synced and found through the still-
                # canonical item/operations/operation/blob pins.  The callback
                # repeats that check at safeio's final pre-unlink boundary.
                validate_authority()
                try:
                    safeio.release_publication_authority(
                        before, blobs[replacement["after_blob"]], authority,
                        before_release=validate_authority)
                except safeio.SafeIOError as exc:
                    raise ControlRefusal(
                        "operation replacement authority transfer failed") from exc
            if isinstance(before, safeio.MissingSnapshot) and authority is None:
                raise ControlRefusal(
                    "operation replacement authority is missing")
            _after_replacement(index)
            _validate_pins(lock, *pins)
        prefix = _preflight_intent_log_capacity(
            lock, intent, blobs, operation_pin=operation_pin)
        from . import logs
        for index in range(prefix, len(intent["events"])):
            logs._append_entry_locked(
                lock, intent["events"][index],
                _operation_id=intent["operation_id"],
                _authority_fd=operation_pin.fd,
                _authority_name=_log_authority_name(index))
            _after_event(index)
            _validate_pins(lock, *pins)
        completed, _size = _authorized_log_prefix_at(
            lock._item_fd, intent, blobs, operation_pin=operation_pin)
        if completed != len(intent["events"]):
            raise ControlRefusal("operation events could not be verified")
        commit = _expected_commit(intent)
        commit_bytes, commit = _canonical(commit)
        _validate_commit(commit, intent)
        _before_commit_validation()
        _sync_operation_artifacts(
            lock, pins, intent, intent_identity, blobs, blob_identities,
            active_identity)
        _verify_effects(
            lock, operation_pin, intent, blobs, repo, sync=True)
        # Recheck the complete set after durability calls and immediately
        # before the receipt boundary.
        _verify_effects(lock, operation_pin, intent, blobs, repo)
        _validate_pins(lock, *pins)
        commit_identity = _publish_immutable(
            operation_pin.fd, "commit.json", commit_bytes)
        try:
            _validate_pins(lock, *pins)
        except BaseException:
            try:
                _remove_exact(
                    operation_pin.fd, "commit.json", commit_identity)
            except ControlError:
                pass
            raise
        _after_commit()
        _validate_pins(lock, *pins)
    if active_identity is not None:
        _verify_effects(lock, operation_pin, intent, blobs, repo)
        _validate_pins(lock, *pins)
        _remove_exact(lock._control_fd, "active.json", active_identity)
        _after_active_removal()
    return _receipt(commit)


def _publish_operation(lock, pins, intent, intent_bytes, blobs):
    operations_pin, operation_pin, blobs_pin = pins
    _require_intent_record_limit(intent_bytes)
    _validate_pins(lock, *pins)
    intent_identity = _publish_immutable(
        operation_pin.fd, "intent.json", intent_bytes,
        read_limit=_INTENT_RECORD_LIMIT)
    _after_intent()
    _validate_pins(lock, *pins)
    for index, (digest, data) in enumerate(blobs.items()):
        _publish_immutable(blobs_pin.fd, digest, data)
        _after_blob(index, digest)
        _validate_pins(lock, *pins)
    _sync_pins(lock, *pins)
    active_bytes, active = _canonical({
        "version": 1,
        "operation_id": intent["operation_id"],
    })
    _publish_immutable(lock._control_fd, "active.json", active_bytes)
    active_result = _read_bytes_at(
        lock._control_fd, "active.json", sync=True)
    if active_result[0] != active_bytes:
        raise ControlError("active operation marker changed")
    _after_active()
    _validate_pins(lock, *pins)
    return intent_identity, active_result[1]


def _reject_overlapping_missing_tails(intent, blobs, repo):
    claimed_prefixes = set()
    for record in intent["prerequisites"]:
        snapshot = _snapshot_from_record(
            record, blobs, expected_repo=repo)
        if not isinstance(snapshot, safeio.MissingSnapshot):
            continue
        relative_count = safeio._relative_parent_count(snapshot)
        parts = snapshot.relative.parts
        claimed_prefixes.update({
            (str(snapshot.root), parts[:end])
            for end in range(relative_count + 1, len(parts) + 1)
        })
    for replacement in intent["replacements"]:
        snapshot = _snapshot_from_record(
            replacement["before"], blobs, expected_repo=repo)
        if not isinstance(snapshot, safeio.MissingSnapshot):
            continue
        relative_count = safeio._relative_parent_count(snapshot)
        parts = snapshot.relative.parts
        prefixes = {
            (str(snapshot.root), parts[:end])
            for end in range(relative_count + 1, len(parts) + 1)
        }
        if claimed_prefixes.intersection(prefixes):
            raise ControlRefusal(
                "operation has overlapping missing prerequisite/replacement "
                "tails")
        claimed_prefixes.update(prefixes)


def _preflight_snapshots(intent, blobs, repo):
    for record in intent["prerequisites"]:
        snapshot = _snapshot_from_record(
            record, blobs, expected_repo=repo)
        _revalidate_snapshot(snapshot, "operation prerequisite changed")
    for replacement in intent["replacements"]:
        snapshot = _snapshot_from_record(
            replacement["before"], blobs, expected_repo=repo)
        _revalidate_snapshot(snapshot, "operation replacement changed")


def _read_only_operation_preflight(repo, item_id, intent, blobs):
    """Refuse predictable new-operation failures without creating controls.

    A pre-existing operations directory may contain retry/recovery authority, so
    stale before-snapshots are then interpreted only under the item lock.  Log
    capacity is safe to check for every request because operation-event prefix
    adoption is part of that calculation.  Every filesystem read here is
    descriptor-relative, bounded, and no-follow; the locked path repeats the
    applicable checks to close the cooperative race window.
    """
    chain = None
    control_pin = None
    operations_pin = None
    try:
        chain = safeio._open_root_chain(repo)
        for component in (".factory", "items", item_id):
            safeio._append_directory(chain, component)
        safeio._validate_chain(chain)
        _preflight_intent_log_capacity_at(chain[-1].fd, intent, blobs)

        control_pin = _optional_pin_directory(chain[-1].fd, "control")
        if control_pin is not None:
            operations_pin = _optional_pin_directory(
                control_pin.fd, "operations")
        if operations_pin is None:
            _preflight_snapshots(intent, blobs, repo)

        safeio._validate_chain(chain)
        if control_pin is not None:
            _validate_named_directory(
                control_pin.parent_fd, control_pin.name, control_pin.fd,
                control_pin.identity)
        if operations_pin is not None:
            _validate_named_directory(
                operations_pin.parent_fd, operations_pin.name,
                operations_pin.fd, operations_pin.identity)
    except safeio.SafeIOError as exc:
        raise ControlError("cannot safely preflight item namespace") from exc
    finally:
        _close_pin(operations_pin)
        _close_pin(control_pin)
        if chain is not None:
            safeio._close_chain(chain)


def _initial_preflight(lock, intent, blobs):
    _reject_overlapping_missing_tails(intent, blobs, lock.repo)
    _preflight_snapshots(intent, blobs, lock.repo)
    _preflight_intent_log_capacity(lock, intent, blobs)


def commit_operation(repo, item_id, *, kind, key, request,
                     prerequisites=(), replacements=(), events=(),
                     log_snapshot=None):
    """Commit, resume, or adopt one canonical crash-recoverable operation."""
    item_id = _component(item_id, "item id")
    intent, intent_bytes, blobs = _build_intent(
        repo, item_id, kind, key, request, prerequisites, replacements, events,
        log_snapshot)
    canonical_repo = safeio._resolve_root(repo)
    # This is a request-structural refusal: evaluate it before the read-only
    # namespace preflight and, critically, before item_lock can create
    # control/ and control/lock.
    _reject_overlapping_missing_tails(intent, blobs, canonical_repo)
    _read_only_operation_preflight(
        canonical_repo, item_id, intent, blobs)
    with item_lock(canonical_repo, item_id) as lock:
        operations_pin = None
        operation_pin = None
        blobs_pin = None
        try:
            active = _active_record(lock)
            if (active is not None and
                    active[0]["operation_id"] != intent["operation_id"]):
                raise ControlRefusal(
                    "a different control operation is pending recovery")
            # This is the first stable point shared with every cooperative log
            # append.  Refuse predictable capacity failure before creating the
            # operations namespace, publishing WAL intent/active, or applying
            # any replacement effect.
            _preflight_intent_log_capacity(lock, intent, blobs)
            if active is not None:
                active_value, active_identity = active
                operations_pin = _optional_pin_directory(
                    lock._control_fd, "operations")
                if operations_pin is None:
                    raise ControlRefusal(
                        "pending operation namespace is missing")
                operation_pin = _pin_directory(
                    operations_pin.fd, intent["operation_id"])
                blobs_pin = _pin_directory(operation_pin.fd, "blobs")
                _validate_pins(
                    lock, operations_pin, operation_pin, blobs_pin)
                persisted, raw, intent_identity = _intent_from_directory(
                    operation_pin.fd, canonical_repo)
                if persisted is None or raw != intent_bytes:
                    raise ControlRefusal("pending operation intent conflicts")
                return _settle_locked(
                    lock, (operations_pin, operation_pin, blobs_pin),
                    persisted, intent_identity, active_identity)

            operations_pin = _optional_pin_directory(
                lock._control_fd, "operations")
            if operations_pin is None:
                # With no possible retry authority, stale snapshots are a
                # predictable refusal and must be checked before this call
                # creates the operations namespace.
                _initial_preflight(lock, intent, blobs)
                operations_pin = _pin_directory(
                    lock._control_fd, "operations", create=True)
            own_found = _scan_operation_conflicts(
                operations_pin.fd, intent, canonical_repo)
            if not own_found:
                # Refuse stale caller snapshots before creating a directory
                # named for this request.  Otherwise an intent-less directory
                # would poison every later, unrelated operation.
                _initial_preflight(lock, intent, blobs)
            operation_pin = _pin_directory(
                operations_pin.fd, intent["operation_id"],
                create=not own_found)
            blobs_pin = _pin_directory(
                operation_pin.fd, "blobs", create=True)
            _validate_pins(lock, operations_pin, operation_pin, blobs_pin)
            persisted, raw, intent_identity = _intent_from_directory(
                operation_pin.fd, canonical_repo)
            if persisted is not None:
                if raw != intent_bytes:
                    raise ControlRefusal("operation intent conflicts")
                commit_result = _read_optional_bytes(
                    operation_pin.fd, "commit.json", sync=True)
                if commit_result is not None:
                    commit = _decode_canonical_object(
                        commit_result[0], "operation commit receipt")
                    _validate_commit(commit, persisted)
                    stored_blobs, stored_identities = _load_blobs(
                        blobs_pin, persisted, sync=True)
                    pins = (operations_pin, operation_pin, blobs_pin)
                    _sync_operation_artifacts(
                        lock, pins, persisted, intent_identity,
                        stored_blobs, stored_identities, None)
                    _verify_effects(
                        lock, operation_pin, persisted, stored_blobs,
                        canonical_repo,
                        sync=True)
                    _validate_pins(lock, *pins)
                    return _receipt(commit)
            if own_found:
                _initial_preflight(lock, intent, blobs)
            pins = (operations_pin, operation_pin, blobs_pin)
            intent_identity, active_identity = _publish_operation(
                lock, pins, intent, intent_bytes, blobs)
            return _settle_locked(
                lock, pins, intent, intent_identity, active_identity)
        finally:
            _close_pin(blobs_pin)
            _close_pin(operation_pin)
            _close_pin(operations_pin)


def recover_pending(repo, item_id):
    """Roll the exact durably active operation forward, if one exists."""
    item_id = _component(item_id, "item id")
    canonical_repo = safeio._resolve_root(repo)
    with item_lock(canonical_repo, item_id) as lock:
        active = _active_record(lock)
        if active is None:
            return RecoveryResult(False)
        active_value, active_identity = active
        operations_pin = _pin_directory(lock._control_fd, "operations")
        operation_pin = None
        blobs_pin = None
        try:
            operation_pin = _pin_directory(
                operations_pin.fd, active_value["operation_id"])
            blobs_pin = _pin_directory(operation_pin.fd, "blobs")
            _validate_pins(lock, operations_pin, operation_pin, blobs_pin)
            intent, _raw, intent_identity = _intent_from_directory(
                operation_pin.fd, canonical_repo)
            if (intent is None or intent["operation_id"] !=
                    active_value["operation_id"] or
                    intent["item"] != item_id):
                raise ControlRefusal("pending operation intent is invalid")
            receipt = _settle_locked(
                lock, (operations_pin, operation_pin, blobs_pin), intent,
                intent_identity, active_identity)
            return RecoveryResult(True, receipt)
        finally:
            _close_pin(blobs_pin)
            _close_pin(operation_pin)
            _close_pin(operations_pin)


def adopt_operation(repo, item_id, *, kind, key):
    """Adopt a settled or active operation by its stable semantic key.

    An intent that never reached activation is deliberately not adopted: its
    caller must reproduce the exact request so conflict checks still bind all
    bytes.  This helper exists for lost replies after the durable boundary.
    """
    item_id = _component(item_id, "item id")
    if type(kind) is not str or not kind or type(key) is not str or not key:
        raise ControlRefusal("operation kind and key are required")
    canonical_repo = safeio._resolve_root(repo)
    with item_lock(canonical_repo, item_id) as lock:
        operations_pin = _optional_pin_directory(
            lock._control_fd, "operations")
        if operations_pin is None:
            return None
        active = _active_record(lock)
        found = None
        try:
            try:
                names = os.listdir(operations_pin.fd)
            except OSError as exc:
                raise ControlError("cannot inspect operation namespace") from exc
            for name in names:
                if not _valid_digest(name):
                    raise ControlRefusal(
                        "operation namespace contains an invalid entry")
                operation_pin = _pin_directory(operations_pin.fd, name)
                blobs_pin = None
                try:
                    intent, _raw, intent_identity = _intent_from_directory(
                        operation_pin.fd, canonical_repo)
                    if intent is None or (intent["kind"], intent["key"]) != (
                            kind, key):
                        continue
                    if found is not None:
                        raise ControlRefusal(
                            "operation key matches multiple requests")
                    blobs_pin = _pin_directory(operation_pin.fd, "blobs")
                    _validate_pins(
                        lock, operations_pin, operation_pin, blobs_pin)
                    commit_result = _read_optional_bytes(
                        operation_pin.fd, "commit.json", sync=True)
                    found = (operation_pin, blobs_pin, intent,
                             intent_identity, commit_result)
                    operation_pin = None
                    blobs_pin = None
                finally:
                    _close_pin(blobs_pin)
                    _close_pin(operation_pin)
            if found is None:
                return None
            operation_pin, blobs_pin, intent, intent_identity, commit_result = found
            found = None
            try:
                if commit_result is not None:
                    commit = _decode_canonical_object(
                        commit_result[0], "operation commit receipt")
                    _validate_commit(commit, intent)
                    stored_blobs, stored_identities = _load_blobs(
                        blobs_pin, intent, sync=True)
                    pins = (operations_pin, operation_pin, blobs_pin)
                    _sync_operation_artifacts(
                        lock, pins, intent, intent_identity,
                        stored_blobs, stored_identities, None)
                    _verify_effects(
                        lock, operation_pin, intent, stored_blobs,
                        canonical_repo, sync=True)
                    return _receipt(commit)
                if (active is not None and
                        active[0]["operation_id"] == intent["operation_id"]):
                    return _settle_locked(
                        lock, (operations_pin, operation_pin, blobs_pin),
                        intent, intent_identity, active[1])
                return None
            finally:
                _close_pin(blobs_pin)
                _close_pin(operation_pin)
        finally:
            if found is not None:
                _close_pin(found[1])
                _close_pin(found[0])
            _close_pin(operations_pin)


def operation_intent(repo, item_id, *, kind, key):
    """Return a sealed copy of an existing semantic operation intent.

    This read supports reconstruction after a crash that published an intent
    but did not activate it.  It never treats the returned mutable dictionary
    as authority; callers must still reproduce the request and pass the normal
    conflict checks in ``commit_operation``.
    """
    item_id = _component(item_id, "item id")
    if type(kind) is not str or not kind or type(key) is not str or not key:
        raise ControlRefusal("operation kind and key are required")
    canonical_repo = safeio._resolve_root(repo)
    if not _operation_namespace_present(canonical_repo, item_id):
        return None
    with item_lock(canonical_repo, item_id) as lock:
        operations_pin = _optional_pin_directory(
            lock._control_fd, "operations")
        if operations_pin is None:
            return None
        found = None
        try:
            try:
                names = os.listdir(operations_pin.fd)
            except OSError as exc:
                raise ControlError(
                    "cannot inspect operation namespace") from exc
            for name in names:
                if not _valid_digest(name):
                    raise ControlRefusal(
                        "operation namespace contains an invalid entry")
                operation_pin = _pin_directory(operations_pin.fd, name)
                try:
                    intent, raw, identity = _intent_from_directory(
                        operation_pin.fd, canonical_repo)
                    if intent is None or (intent["kind"], intent["key"]) != (
                            kind, key):
                        continue
                    if found is not None:
                        raise ControlRefusal(
                            "operation key matches multiple requests")
                    _validate_pins(lock, operations_pin, operation_pin)
                    persisted, persisted_identity = _read_bytes_at(
                        operation_pin.fd, "intent.json",
                        limit=_INTENT_RECORD_LIMIT, sync=True)
                    if persisted != raw or persisted_identity != identity:
                        raise ControlRefusal(
                            "operation intent identity changed")
                    found = raw
                finally:
                    _close_pin(operation_pin)
            if found is None:
                return None
            return _decode_canonical_object(found, "operation intent")
        finally:
            _close_pin(operations_pin)


def _operation_namespace_present(repo, item_id):
    """Check for an operations directory without creating control state."""
    chain = None
    control_fd = None
    operations_fd = None
    try:
        chain = safeio._open_root_chain(repo)
        for component in (".factory", "items", item_id):
            safeio._append_directory(chain, component)
            safeio._validate_chain(chain)
        try:
            control_fd = os.open(
                "control", _DIRECTORY_FLAGS, dir_fd=chain[-1].fd)
        except FileNotFoundError:
            safeio._require_absent(chain[-1].fd, "control")
            safeio._validate_chain(chain)
            return False
        control_identity = _directory_identity(os.fstat(control_fd))
        _validate_named_directory(
            chain[-1].fd, "control", control_fd, control_identity)
        try:
            operations_fd = os.open(
                "operations", _DIRECTORY_FLAGS, dir_fd=control_fd)
        except FileNotFoundError:
            try:
                os.stat("operations", dir_fd=control_fd,
                        follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ControlError(
                    "operation namespace changed during inspection")
            safeio._validate_chain(chain)
            _validate_named_directory(
                chain[-1].fd, "control", control_fd, control_identity)
            return False
        operations_identity = _directory_identity(os.fstat(operations_fd))
        _validate_named_directory(
            control_fd, "operations", operations_fd,
            operations_identity)
        safeio._validate_chain(chain)
        _validate_named_directory(
            chain[-1].fd, "control", control_fd, control_identity)
        return True
    except (OSError, safeio.SafeIOError) as exc:
        raise ControlError(
            "cannot safely inspect operation namespace") from exc
    finally:
        if operations_fd is not None:
            os.close(operations_fd)
        if control_fd is not None:
            os.close(control_fd)
        safeio._close_chain(chain or [])


def require_settled(repo, item_id) -> None:
    """Refuse while a durable operation marker still requires recovery."""
    item_id = _component(item_id, "item id")
    with item_lock(repo, item_id) as lock:
        if _active_record(lock) is not None:
            raise ControlRefusal("a control operation is pending recovery")


# Fault-injection seams.  They deliberately do no work in production.
def _after_intent():
    pass


def _after_blob(index, digest):
    pass


def _after_active():
    pass


def _after_replacement(index):
    pass


def _after_event(index):
    pass


def _before_commit_validation():
    """Test seam before the final complete-set receipt validation."""
    pass


def _after_commit():
    pass


def _after_active_removal():
    pass
