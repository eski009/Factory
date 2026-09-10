"""Durable, fail-closed recovery for a lost child-agent reply."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import items, machine, ownership


_ATTEMPT_RE = re.compile(r"^[0-9a-f]{32}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
    os, "O_NOFOLLOW", 0)
_FILE_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_FILE_READ_FLAGS = os.O_RDONLY | _FILE_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)


class ReconciliationError(ValueError):
    """The checkpoint cannot safely authorize recovery."""


class PublicationUncertain(ReconciliationError):
    """A publication failed at a known side of its durability boundary."""

    def __init__(self, message, attempt_id, committed):
        super().__init__(message)
        self.attempt_id = attempt_id
        self.committed = committed


class _ManifestDurabilityError(ReconciliationError):
    """A visible manifest could not be durably adopted and revalidated."""


class FilesystemOps:
    """Injectable filesystem boundary used by adversarial tests."""

    @staticmethod
    def open(path, flags, mode=0o777, *, dir_fd=None):
        return os.open(path, flags, mode, dir_fd=dir_fd)

    @staticmethod
    def close(fd):
        return os.close(fd)

    @staticmethod
    def read(fd, size):
        return os.read(fd, size)

    @staticmethod
    def write(fd, data):
        return os.write(fd, data)

    @staticmethod
    def fsync(fd):
        return os.fsync(fd)

    @staticmethod
    def sync_observation(fd):
        """Make already-visible recovery evidence durable before adoption."""
        return os.fsync(fd)

    @staticmethod
    def mkdir(path, mode=0o777, *, dir_fd=None):
        return os.mkdir(path, mode, dir_fd=dir_fd)

    @staticmethod
    def stat(path, *, dir_fd=None, follow_symlinks=True):
        return os.stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    @staticmethod
    def fstat(fd):
        return os.fstat(fd)

    @staticmethod
    def link(src, dst, *, src_dir_fd=None, dst_dir_fd=None,
             follow_symlinks=True):
        return os.link(src, dst, src_dir_fd=src_dir_fd,
                       dst_dir_fd=dst_dir_fd,
                       follow_symlinks=follow_symlinks)

    @staticmethod
    def unlink(path, *, dir_fd=None):
        return os.unlink(path, dir_fd=dir_fd)

    @staticmethod
    def listdir(path):
        return os.listdir(path)

    @staticmethod
    def readlink(path, *, dir_fd=None):
        return os.readlink(path, dir_fd=dir_fd)


DEFAULT_OPS = FilesystemOps()


@dataclass(frozen=True)
class _Handle:
    fd: int
    name: str | None
    identity: tuple[int, int]


def _identity(details):
    return details.st_dev, details.st_ino


def _file_state(details):
    return (_identity(details), details.st_size,
            details.st_mtime_ns, details.st_ctime_ns)


def _close_chain(chain, ops=DEFAULT_OPS):
    for handle in reversed(chain):
        try:
            ops.close(handle.fd)
        except OSError:
            pass


def _handle(fd, name, ops=DEFAULT_OPS):
    try:
        details = ops.fstat(fd)
        if not stat.S_ISDIR(details.st_mode):
            raise ReconciliationError(f"unsafe reconciliation directory: {name}")
        return _Handle(fd, name, _identity(details))
    except BaseException:
        ops.close(fd)
        raise


def _append_directory(chain, name, ops=DEFAULT_OPS):
    try:
        fd = ops.open(name, _DIRECTORY_FLAGS, dir_fd=chain[-1].fd)
    except OSError as exc:
        raise ReconciliationError(
            f"unsafe reconciliation directory: {name}") from exc
    chain.append(_handle(fd, name, ops))


def _canonical_repo(repo):
    try:
        return Path(repo).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ReconciliationError("repository path cannot be resolved") from exc


def _safe_component(value, label):
    if (type(value) is not str or not value or value in (".", "..")
            or "/" in value or "\x00" in value):
        raise ReconciliationError(f"unsafe {label}")
    return value


def _validate_chain(chain, repo_path, repo_index, ops=DEFAULT_OPS):
    for index in range(len(chain) - 1, -1, -1):
        handle = chain[index]
        try:
            details = ops.fstat(handle.fd)
        except OSError as exc:
            raise ReconciliationError("reconciliation directory chain is closed") from exc
        if not stat.S_ISDIR(details.st_mode) or _identity(details) != handle.identity:
            raise ReconciliationError("reconciliation directory identity changed")
        if index:
            parent = chain[index - 1]
            try:
                entry = ops.stat(handle.name, dir_fd=parent.fd,
                                 follow_symlinks=False)
            except OSError as exc:
                raise ReconciliationError(
                    f"reconciliation directory was relocated: {handle.name}") from exc
            if (not stat.S_ISDIR(entry.st_mode)
                    or _identity(entry) != handle.identity):
                raise ReconciliationError(
                    f"reconciliation directory was replaced: {handle.name}")
    try:
        current = ops.stat(str(repo_path), follow_symlinks=False)
    except OSError as exc:
        raise ReconciliationError("repository path cannot be revalidated") from exc
    if _identity(current) != chain[repo_index].identity:
        raise ReconciliationError("repository path identity changed")


def _open_item_chain(repo, item_id, ops=DEFAULT_OPS):
    repo_path = _canonical_repo(repo)
    _safe_component(item_id, "item id")
    root = Path(repo_path.anchor)
    relative = repo_path.relative_to(root)
    if any(part in ("", ".", "..") for part in relative.parts):
        raise ReconciliationError("unsafe repository path")
    chain = []
    try:
        chain.append(_handle(ops.open(str(root), _DIRECTORY_FLAGS), None, ops))
        for part in relative.parts:
            _append_directory(chain, part, ops)
        repo_index = len(chain) - 1
        for part in (".factory", "items", item_id):
            _append_directory(chain, part, ops)
        _validate_chain(chain, repo_path, repo_index, ops)
        return repo_path, repo_index, chain
    except BaseException:
        _close_chain(chain, ops)
        raise


def _ensure_directory(chain, name, repo_path, repo_index, attempt_id,
                      ops=DEFAULT_OPS):
    created = False
    try:
        ops.mkdir(name, 0o700, dir_fd=chain[-1].fd)
        created = True
    except FileExistsError:
        pass
    except OSError as exc:
        raise PublicationUncertain(
            f"could not create reconciliation directory {name}",
            attempt_id, False) from exc
    _append_directory(chain, name, ops)
    try:
        # An existing entry may be residue from an earlier parent-directory
        # fsync failure. Re-establish its durability before it can authorize
        # either a dispatch checkpoint or a continuation.
        ops.fsync(chain[-2].fd)
        _validate_chain(chain, repo_path, repo_index, ops)
    except (OSError, ReconciliationError) as exc:
        raise PublicationUncertain(
            f"directory publication is uncertain: {name}",
            attempt_id, False) from exc
    return created


def _normalize_relative(path):
    if type(path) is not str or not path or "\x00" in path or "\\" in path:
        raise ReconciliationError("evidence paths must be repository-relative")
    value = PurePosixPath(path)
    if value.is_absolute() or str(value) != path:
        raise ReconciliationError(f"unsafe repository-relative path: {path!r}")
    if any(part in ("", ".", "..") for part in value.parts):
        raise ReconciliationError(f"unsafe repository-relative path: {path!r}")
    return tuple(value.parts)


def _normalize_paths(values, label):
    if isinstance(values, dict):
        values = list(values)
    if isinstance(values, (str, bytes)):
        raise ReconciliationError(f"{label} must be a non-empty path collection")
    try:
        raw = list(values)
    except TypeError as exc:
        raise ReconciliationError(f"{label} must be a non-empty path collection") from exc
    if not raw:
        raise ReconciliationError(f"{label} must be non-empty")
    normalized = {"/".join(_normalize_relative(value)) for value in raw}
    if len(normalized) != len(raw):
        raise ReconciliationError("duplicate reconciliation path")
    return sorted(normalized)


def _reject_overlapping_paths(inputs, evidence):
    all_paths = sorted(inputs + evidence)
    if len(set(all_paths)) != len(all_paths):
        raise ReconciliationError("input and evidence paths overlap")
    parts = [tuple(PurePosixPath(path).parts) for path in all_paths]
    for index, left in enumerate(parts):
        for right in parts[index + 1:]:
            if right[:len(left)] == left:
                raise ReconciliationError("ancestor and descendant paths are not allowed")


def _read_fd(fd, ops=DEFAULT_OPS):
    output = bytearray()
    while True:
        chunk = ops.read(fd, 65536)
        if not chunk:
            return bytes(output)
        output.extend(chunk)


def _validate_opened_directories(opened, ops=DEFAULT_OPS):
    for ancestor_fd, ancestor_identity, handle in reversed(opened):
        current = ops.stat(handle.name, dir_fd=ancestor_fd,
                           follow_symlinks=False)
        if (not stat.S_ISDIR(current.st_mode)
                or _identity(current) != handle.identity
                or _identity(ops.fstat(ancestor_fd)) != ancestor_identity):
            raise ReconciliationError("file directory chain was replaced")


def _sync_directories(opened, parent_fd, root_fd, ops=DEFAULT_OPS):
    directory_fds = [parent_fd]
    directory_fds.extend(
        ancestor_fd for ancestor_fd, _identity_value, _handle_value
        in reversed(opened))
    directory_fds.append(root_fd)
    seen = set()
    for directory_fd in directory_fds:
        if directory_fd not in seen:
            ops.sync_observation(directory_fd)
            seen.add(directory_fd)


def _secure_read_from(chain, repo_path, repo_index, relative,
                      missing_ok=False, durable=False, ops=DEFAULT_OPS):
    parts = _normalize_relative(relative) if isinstance(relative, str) else relative
    opened = []
    leaf_fd = -1
    try:
        parent_fd = chain[repo_index].fd
        parent_identity = chain[repo_index].identity
        for part in parts[:-1]:
            try:
                fd = ops.open(part, _DIRECTORY_FLAGS, dir_fd=parent_fd)
            except FileNotFoundError:
                if missing_ok:
                    if durable:
                        _sync_directories(
                            opened, parent_fd, chain[repo_index].fd, ops)
                        try:
                            ops.stat(part, dir_fd=parent_fd,
                                     follow_symlinks=False)
                        except FileNotFoundError:
                            pass
                        else:
                            raise ReconciliationError(
                                "missing path appeared while making durable")
                    _validate_opened_directories(opened, ops)
                    _validate_chain(chain, repo_path, repo_index, ops)
                    return None
                raise
            handle = _handle(fd, part, ops)
            opened.append((parent_fd, parent_identity, handle))
            parent_fd = handle.fd
            parent_identity = handle.identity
        try:
            leaf_fd = ops.open(parts[-1], _FILE_READ_FLAGS,
                               dir_fd=parent_fd)
        except FileNotFoundError:
            if missing_ok:
                if durable:
                    _sync_directories(
                        opened, parent_fd, chain[repo_index].fd, ops)
                    try:
                        ops.stat(parts[-1], dir_fd=parent_fd,
                                 follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        raise ReconciliationError(
                            "missing file appeared while making durable")
                _validate_opened_directories(opened, ops)
                _validate_chain(chain, repo_path, repo_index, ops)
                return None
            raise
        before = ops.fstat(leaf_fd)
        if not stat.S_ISREG(before.st_mode):
            raise ReconciliationError(f"evidence is not a regular file: {'/'.join(parts)}")
        raw = _read_fd(leaf_fd, ops)
        after = ops.fstat(leaf_fd)
        if (len(raw) != before.st_size
                or _file_state(before) != _file_state(after)):
            raise ReconciliationError(f"file changed while reading: {'/'.join(parts)}")
        entry = ops.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        if (not stat.S_ISREG(entry.st_mode)
                or _file_state(entry) != _file_state(before)):
            raise ReconciliationError(f"file was replaced while reading: {'/'.join(parts)}")
        if durable:
            # A child may die after installing a complete file but before its
            # namespace fsync. Adopt that visible state by syncing the leaf,
            # then every directory entry from the leaf back to the repo root.
            ops.sync_observation(leaf_fd)
            _sync_directories(
                opened, parent_fd, chain[repo_index].fd, ops)
            synced = ops.fstat(leaf_fd)
            synced_entry = ops.stat(
                parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            if (not stat.S_ISREG(synced.st_mode)
                    or _identity(synced) != _identity(before)
                    or synced.st_size != before.st_size
                    or synced.st_mtime_ns != before.st_mtime_ns
                    or synced.st_ctime_ns != before.st_ctime_ns
                    or not stat.S_ISREG(synced_entry.st_mode)
                    or _file_state(synced_entry) != _file_state(before)):
                raise ReconciliationError(
                    f"file changed while making durable: {'/'.join(parts)}")
        _validate_opened_directories(opened, ops)
        _validate_chain(chain, repo_path, repo_index, ops)
        return raw, _identity(before)
    except FileNotFoundError as exc:
        raise ReconciliationError(f"missing required file: {'/'.join(parts)}") from exc
    except OSError as exc:
        raise ReconciliationError(f"unsafe or unreadable file: {'/'.join(parts)}") from exc
    finally:
        if leaf_fd >= 0:
            try:
                ops.close(leaf_fd)
            except OSError:
                pass
        for _parent_fd, _parent_identity, handle in reversed(opened):
            try:
                ops.close(handle.fd)
            except OSError:
                pass


def _strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _decode_json(raw, label):
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ReconciliationError(f"malformed {label}") from exc


def _canonical_json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8")


def _secure_read_named(chain, repo_path, repo_index, name, ops=DEFAULT_OPS,
                       *, durable=False):
    fd = -1
    try:
        fd = ops.open(name, _FILE_READ_FLAGS,
                      dir_fd=chain[-1].fd)
        before = ops.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ReconciliationError(f"unsafe reconciliation file: {name}")
        raw = _read_fd(fd, ops)
        after = ops.fstat(fd)
        entry = ops.stat(name, dir_fd=chain[-1].fd, follow_symlinks=False)
        if (len(raw) != before.st_size
                or _file_state(before) != _file_state(after)
                or not stat.S_ISREG(entry.st_mode)
                or _file_state(entry) != _file_state(before)):
            raise ReconciliationError(f"reconciliation file was replaced: {name}")
        if durable:
            ops.sync_observation(fd)
            ops.sync_observation(chain[-1].fd)
            synced = ops.fstat(fd)
            synced_entry = ops.stat(
                name, dir_fd=chain[-1].fd, follow_symlinks=False)
            if (_file_state(synced) != _file_state(before)
                    or not stat.S_ISREG(synced_entry.st_mode)
                    or _file_state(synced_entry) != _file_state(before)):
                raise ReconciliationError(
                    f"reconciliation file changed while making durable: {name}")
        _validate_chain(chain, repo_path, repo_index, ops)
        return raw, _identity(before)
    except OSError as exc:
        raise ReconciliationError(f"unsafe reconciliation file: {name}") from exc
    finally:
        if fd >= 0:
            try:
                ops.close(fd)
            except OSError:
                pass


def _publish_json(chain, repo_path, repo_index, final_name, payload_factory,
                  attempt_id, ops=DEFAULT_OPS):
    directory_fd = chain[-1].fd
    temp_name = f".{final_name}.tmp-{secrets.token_hex(16)}"
    fd = -1
    linked = False
    committed = False
    payload = None
    raw = None
    temp_identity = None
    try:
        fd = ops.open(temp_name,
                      os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_NOFOLLOW,
                      0o600, dir_fd=directory_fd)
        details = ops.fstat(fd)
        if not stat.S_ISREG(details.st_mode):
            raise OSError("temporary publication leaf is not regular")
        temp_identity = _identity(details)
        payload = payload_factory(temp_identity)
        raw = _canonical_json(payload)
        remaining = memoryview(raw)
        while remaining:
            written = ops.write(fd, remaining)
            if written <= 0:
                raise OSError("short write while publishing reconciliation state")
            remaining = remaining[written:]
        ops.fsync(fd)
        ops.close(fd)
        fd = -1
        _validate_chain(chain, repo_path, repo_index, ops)
        ops.link(temp_name, final_name, src_dir_fd=directory_fd,
                 dst_dir_fd=directory_fd, follow_symlinks=False)
        linked = True
        ops.fsync(directory_fd)
        committed = True
    except FileExistsError:
        raise
    except (OSError, ReconciliationError) as exc:
        raise PublicationUncertain(
            f"reconciliation publication is uncertain: {final_name}",
            attempt_id, committed) from exc
    finally:
        if fd >= 0:
            try:
                ops.close(fd)
            except OSError:
                pass
        if not linked:
            try:
                ops.unlink(temp_name, dir_fd=directory_fd)
            except OSError:
                pass

    cleanup_pending = False
    try:
        ops.unlink(temp_name, dir_fd=directory_fd)
        ops.fsync(directory_fd)
    except OSError:
        cleanup_pending = True
    try:
        opened_raw, opened_identity = _secure_read_named(
            chain, repo_path, repo_index, final_name, ops)
        if opened_raw != raw or opened_identity != temp_identity:
            raise ReconciliationError("published reconciliation state changed")
        _validate_chain(chain, repo_path, repo_index, ops)
    except (OSError, ReconciliationError) as exc:
        raise PublicationUncertain(
            f"committed reconciliation publication cannot be verified: {final_name}",
            attempt_id, True) from exc
    return payload, cleanup_pending


def _pin_log_prefix(chain, repo_path, repo_index, expected, attempt_id,
                    ops=DEFAULT_OPS):
    """Retain the checkpoint log inode so COW generations cannot recycle it."""
    item_chain = chain[:-2]
    if (len(item_chain) <= repo_index or item_chain[-1].name is None
            or chain[-1].name != attempt_id):
        raise ReconciliationError("invalid checkpoint directory chain")
    try:
        source = _secure_read_named(
            item_chain, repo_path, repo_index, "log.jsonl", ops)
        if source != expected:
            raise ReconciliationError(
                "event log changed before prefix pinning")
        ops.link(
            "log.jsonl", "log-prefix.jsonl",
            src_dir_fd=item_chain[-1].fd, dst_dir_fd=chain[-1].fd,
            follow_symlinks=False)
        ops.fsync(chain[-1].fd)
        pinned = _secure_read_named(
            chain, repo_path, repo_index, "log-prefix.jsonl", ops)
        current = _secure_read_named(
            item_chain, repo_path, repo_index, "log.jsonl", ops)
        if pinned != expected or current != expected:
            raise ReconciliationError(
                "event log changed while pinning its prefix")
        _validate_chain(chain, repo_path, repo_index, ops)
    except (OSError, ReconciliationError) as exc:
        raise PublicationUncertain(
            "event log prefix pinning is uncertain",
            attempt_id, False) from exc


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity_record(identity):
    return {"dev": identity[0], "ino": identity[1]}


def _parse_log(raw, label="event log"):
    if raw and not raw.endswith(b"\n"):
        raise ReconciliationError(f"{label} has an incomplete trailing record")
    events = []
    for line in raw.splitlines():
        if not line:
            raise ReconciliationError(f"{label} contains a blank record")
        value = _decode_json(line, label)
        if (type(value) is not dict or type(value.get("event")) is not str
                or type(value.get("ts")) is not str):
            raise ReconciliationError(f"{label} contains a malformed event")
        events.append(value)
    return events


def _semantic_snapshot(repo_path, item_id, chain, repo_index,
                       ops=DEFAULT_OPS, *, durable=False):
    item_path = f".factory/items/{item_id}/item.md"
    log_path = f".factory/items/{item_id}/log.jsonl"
    item_state = _secure_read_from(
        chain, repo_path, repo_index, item_path,
        durable=durable, ops=ops)
    try:
        meta, _body = items.parse_item(item_state[0].decode("utf-8"))
    except (items.ItemError, UnicodeDecodeError) as exc:
        raise ReconciliationError(f"invalid item metadata: {item_id}") from exc
    if meta.get("id") != item_id:
        raise ReconciliationError(
            f"item metadata identity does not match: {item_id}")

    log_state = _secure_read_from(
        chain, repo_path, repo_index, log_path,
        durable=durable, ops=ops)
    events = _parse_log(log_state[0])
    return meta, item_state, events, log_state


def _run_git(checkout, *args):
    env = dict(os.environ)
    env.update({"LC_ALL": "C", "LANG": "C"})
    try:
        result = subprocess.run(
            ["git", *args], cwd=checkout, env=env, capture_output=True)
    except (OSError, UnicodeError) as exc:
        raise ReconciliationError("git checkout inspection failed") from exc
    if result.returncode != 0:
        raise ReconciliationError("git checkout inspection failed")
    return result.stdout


def _open_absolute_chain(path, ops=DEFAULT_OPS):
    canonical = Path(path).resolve(strict=True)
    root = Path(canonical.anchor)
    relative = canonical.relative_to(root)
    chain = []
    try:
        chain.append(_handle(ops.open(str(root), _DIRECTORY_FLAGS), None, ops))
        for part in relative.parts:
            _append_directory(chain, part, ops)
        _validate_chain(chain, canonical, len(chain) - 1, ops)
        return canonical, len(chain) - 1, chain
    except BaseException:
        _close_chain(chain, ops)
        raise


def _untracked_record(chain, root_path, root_index, relative, ops=DEFAULT_OPS):
    parts = _normalize_relative(relative)
    opened = []
    try:
        parent_fd = chain[root_index].fd
        parent_identity = chain[root_index].identity
        for part in parts[:-1]:
            fd = ops.open(part, _DIRECTORY_FLAGS, dir_fd=parent_fd)
            handle = _handle(fd, part, ops)
            opened.append((parent_fd, parent_identity, handle))
            parent_fd = handle.fd
            parent_identity = handle.identity
        details = ops.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        mode = details.st_mode
        if stat.S_ISREG(mode):
            raw, identity = _secure_read_from(
                chain, root_path, root_index, parts, ops=ops)
            if identity != _identity(details):
                raise ReconciliationError("untracked file was replaced")
            kind = "regular"
        elif stat.S_ISLNK(mode):
            before = _identity(details)
            target = ops.readlink(parts[-1], dir_fd=parent_fd)
            after = ops.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            if before != _identity(after):
                raise ReconciliationError("untracked symlink changed while reading")
            raw = os.fsencode(target)
            identity = before
            _validate_opened_directories(opened, ops)
            _validate_chain(chain, root_path, root_index, ops)
            kind = "symlink"
        else:
            raise ReconciliationError("unsupported untracked checkout entry")
        return {
            "path": relative,
            "kind": kind,
            "mode": stat.S_IMODE(mode),
            "identity": [identity[0], identity[1]],
            "sha256": _sha(raw),
        }
    except OSError as exc:
        raise ReconciliationError("unsafe untracked checkout entry") from exc
    finally:
        for _parent_fd, _parent_identity, handle in reversed(opened):
            try:
                ops.close(handle.fd)
            except OSError:
                pass


def _sync_checkout_entry(chain, checkout, checkout_index, relative,
                         ops=DEFAULT_OPS):
    parts = _normalize_relative(relative)
    opened = []
    try:
        parent_fd = chain[checkout_index].fd
        parent_identity = chain[checkout_index].identity
        for part in parts[:-1]:
            try:
                fd = ops.open(part, _DIRECTORY_FLAGS, dir_fd=parent_fd)
            except FileNotFoundError:
                _sync_directories(
                    opened, parent_fd, chain[checkout_index].fd, ops)
                try:
                    ops.stat(part, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    return
                raise ReconciliationError(
                    "checkout path appeared while making durable")
            handle = _handle(fd, part, ops)
            opened.append((parent_fd, parent_identity, handle))
            parent_fd = handle.fd
            parent_identity = handle.identity
        try:
            details = ops.stat(
                parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            _sync_directories(
                opened, parent_fd, chain[checkout_index].fd, ops)
            try:
                ops.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return
            raise ReconciliationError(
                "checkout path appeared while making durable")
        if stat.S_ISREG(details.st_mode):
            _secure_read_from(
                chain, checkout, checkout_index, parts,
                durable=True, ops=ops)
            return
        if stat.S_ISLNK(details.st_mode):
            before = (_file_state(details),
                      ops.readlink(parts[-1], dir_fd=parent_fd))
            _sync_directories(
                opened, parent_fd, chain[checkout_index].fd, ops)
            after_details = ops.stat(
                parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            after = (_file_state(after_details),
                     ops.readlink(parts[-1], dir_fd=parent_fd))
            if not stat.S_ISLNK(after_details.st_mode) or after != before:
                raise ReconciliationError(
                    "checkout symlink changed while making durable")
            _validate_opened_directories(opened, ops)
            _validate_chain(chain, checkout, checkout_index, ops)
            return
        raise ReconciliationError(
            f"unsupported changed checkout entry: {relative}")
    except OSError as exc:
        raise ReconciliationError(
            f"checkout observation could not be made durable: {relative}") from exc
    finally:
        for _parent_fd, _parent_identity, handle in reversed(opened):
            try:
                ops.close(handle.fd)
            except OSError:
                pass


def _feed_record(digest, label, raw):
    name = label.encode("utf-8")
    digest.update(len(name).to_bytes(8, "big"))
    digest.update(name)
    digest.update(len(raw).to_bytes(8, "big"))
    digest.update(raw)


def _capture_checkout_state(checkout, chain, checkout_index, ops=DEFAULT_OPS):
    head = _run_git(checkout, "rev-parse", "--verify", "HEAD").strip()
    if not re.fullmatch(rb"[0-9a-f]{40}", head):
        raise ReconciliationError("checkout HEAD is invalid")
    status_raw = _run_git(
        checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    unstaged = _run_git(
        checkout, "diff", "--no-ext-diff", "--no-textconv", "--binary",
        "HEAD", "--")
    staged = _run_git(
        checkout, "diff", "--cached", "--no-ext-diff", "--no-textconv",
        "--binary", "HEAD", "--")
    untracked_raw = _run_git(
        checkout, "ls-files", "--others", "--exclude-standard", "-z")
    tracked_raw = _run_git(
        checkout, "diff", "--name-only", "--no-renames", "-z", "HEAD", "--")
    untracked_paths = [
        os.fsdecode(value) for value in untracked_raw.split(b"\0") if value]
    records = [
        _untracked_record(chain, checkout, checkout_index, value, ops)
        for value in sorted(untracked_paths)
    ]
    _validate_chain(chain, checkout, checkout_index, ops)
    return (head, status_raw, unstaged, staged, untracked_raw, tracked_raw,
            records)


def _checkout_snapshot(repo_path, item_id, supplied, ops=DEFAULT_OPS,
                       *, durable=False, baseline_head=None):
    try:
        checkout = ownership.canonical_worktree(repo_path, item_id, supplied)
    except ownership.OwnershipError as exc:
        raise ReconciliationError("checkout is not the canonical item worktree") from exc
    checkout, checkout_index, chain = _open_absolute_chain(checkout, ops)
    try:
        captured = _capture_checkout_state(
            checkout, chain, checkout_index, ops)
        if durable:
            if (type(baseline_head) is not str
                    or re.fullmatch(r"[0-9a-f]{40}", baseline_head) is None):
                raise ReconciliationError(
                    "checkout baseline HEAD is invalid")
            changed_paths = set(
                os.fsdecode(value) for value in captured[4].split(b"\0")
                if value)
            changed_paths.update(
                os.fsdecode(value) for value in captured[5].split(b"\0")
                if value)
            current_head = captured[0].decode("ascii")
            committed_paths = _run_git(
                checkout, "diff", "--name-only", "--no-renames", "-z",
                baseline_head, current_head, "--")
            changed_paths.update(
                os.fsdecode(value) for value in committed_paths.split(b"\0")
                if value)
            try:
                for relative in sorted(changed_paths):
                    _sync_checkout_entry(
                        chain, checkout, checkout_index, relative, ops)
                ops.sync_observation(chain[checkout_index].fd)
            except ReconciliationError as exc:
                raise ReconciliationError(
                    f"checkout observation could not be made durable: {exc}") from exc
            except OSError as exc:
                raise ReconciliationError(
                    "checkout observation could not be made durable") from exc
        if _capture_checkout_state(
                checkout, chain, checkout_index, ops) != captured:
            raise ReconciliationError("checkout changed while snapshotting")
        (head, status_raw, unstaged, staged, untracked_raw, tracked_raw,
         records) = captured
        digest = hashlib.sha256()
        for label, raw in (
                ("status", status_raw), ("unstaged", unstaged),
                ("staged", staged), ("untracked-paths", untracked_raw),
                ("tracked-paths", tracked_raw),
                ("untracked-records", _canonical_json(records))):
            _feed_record(digest, label, raw)
        _validate_chain(chain, checkout, checkout_index, ops)
        return {
            "path": str(checkout),
            "head": head.decode("ascii"),
            "dev": chain[-1].identity[0],
            "ino": chain[-1].identity[1],
            "state_sha256": digest.hexdigest(),
        }
    finally:
        _close_chain(chain, ops)


def _snapshot_paths(chain, repo_path, repo_index, names, missing_ok,
                    ops=DEFAULT_OPS, *, durable=False):
    output = {}
    for name in names:
        value = _secure_read_from(
            chain, repo_path, repo_index, name,
            missing_ok=missing_ok, durable=durable, ops=ops)
        output[name] = None if value is None else _sha(value[0])
    return output


_MANIFEST_KEYS = {
    "version", "attempt_id", "item", "stage", "stage_entry", "obligation",
    "inputs", "evidence", "item_file", "log_prefix", "attempt_dir",
    "manifest_file", "checkout",
}


def _valid_digest(value):
    return type(value) is str and _DIGEST_RE.fullmatch(value) is not None


def _valid_identity(value):
    return (type(value) is dict and set(value) == {"dev", "ino"}
            and type(value["dev"]) is int and not isinstance(value["dev"], bool)
            and value["dev"] >= 0
            and type(value["ino"]) is int and not isinstance(value["ino"], bool)
            and value["ino"] >= 0)


def _manifest_problem(value, item_id, attempt_id, file_identity,
                      directory_identity):
    if type(value) is not dict or set(value) != _MANIFEST_KEYS:
        return "manifest has an invalid closed schema"
    if value.get("version") != 1 or type(value.get("version")) is not int:
        return "manifest version is invalid"
    if value.get("item") != item_id or value.get("attempt_id") != attempt_id:
        return "manifest identity does not match its path"
    if (type(value.get("stage")) is not str or not value["stage"]
            or type(value.get("obligation")) is not str
            or not value["obligation"]):
        return "manifest stage or obligation is invalid"
    if (type(value.get("stage_entry")) is not int
            or isinstance(value["stage_entry"], bool)
            or value["stage_entry"] < 0):
        return "manifest stage entry is invalid"
    item_file = value.get("item_file")
    if (type(item_file) is not dict
            or set(item_file) != {"sha256", "dev", "ino"}
            or not _valid_digest(item_file.get("sha256"))
            or not _valid_identity({"dev": item_file.get("dev"),
                                    "ino": item_file.get("ino")})
            or not _valid_identity(value.get("attempt_dir"))
            or not _valid_identity(value.get("manifest_file"))):
        return "manifest file identity is invalid"
    if value["attempt_dir"] != _identity_record(directory_identity):
        return "attempt directory identity changed"
    if value["manifest_file"] != _identity_record(file_identity):
        return "manifest file identity changed"
    log_prefix = value.get("log_prefix")
    if (type(log_prefix) is not dict
            or set(log_prefix) != {"bytes", "sha256", "events", "dev", "ino"}
            or type(log_prefix["bytes"]) is not int
            or isinstance(log_prefix["bytes"], bool) or log_prefix["bytes"] < 0
            or type(log_prefix["events"]) is not int
            or isinstance(log_prefix["events"], bool) or log_prefix["events"] < 0
            or not _valid_digest(log_prefix["sha256"])
            or type(log_prefix["dev"]) is not int
            or isinstance(log_prefix["dev"], bool)
            or log_prefix["dev"] < 0
            or type(log_prefix["ino"]) is not int
            or isinstance(log_prefix["ino"], bool)
            or log_prefix["ino"] < 0):
        return "log prefix is invalid"
    for label in ("inputs", "evidence"):
        mapping = value.get(label)
        if type(mapping) is not dict or not mapping:
            return f"manifest {label} are invalid"
        try:
            normalized = _normalize_paths(mapping, label)
        except ReconciliationError:
            return f"manifest {label} are invalid"
        if normalized != sorted(mapping):
            return f"manifest {label} paths are not canonical"
        for digest in mapping.values():
            if label == "inputs":
                if not _valid_digest(digest):
                    return "manifest input digest is invalid"
            elif digest is not None and not _valid_digest(digest):
                return "manifest evidence digest is invalid"
    try:
        _reject_overlapping_paths(sorted(value["inputs"]),
                                  sorted(value["evidence"]))
    except ReconciliationError:
        return "manifest paths overlap"
    checkout = value.get("checkout")
    if checkout is not None:
        if (type(checkout) is not dict
                or set(checkout) != {
                    "path", "head", "dev", "ino", "state_sha256"}
                or type(checkout["path"]) is not str
                or type(checkout["head"]) is not str
                or re.fullmatch(r"[0-9a-f]{40}", checkout["head"]) is None
                or not _valid_digest(checkout["state_sha256"])
                or type(checkout["dev"]) is not int
                or isinstance(checkout["dev"], bool)
                or checkout["dev"] < 0
                or type(checkout["ino"]) is not int
                or isinstance(checkout["ino"], bool)
                or checkout["ino"] < 0):
            return "manifest checkout is invalid"
    return None


def _open_attempt_chain(repo, item_id, attempt_id, ops=DEFAULT_OPS):
    if (type(attempt_id) is not str or
            _ATTEMPT_RE.fullmatch(attempt_id) is None):
        raise ReconciliationError("invalid reconciliation attempt id")
    repo_path, repo_index, chain = _open_item_chain(repo, item_id, ops)
    try:
        _append_directory(chain, "reconciliation", ops)
        _append_directory(chain, attempt_id, ops)
        _validate_chain(chain, repo_path, repo_index, ops)
        return repo_path, repo_index, chain
    except BaseException:
        _close_chain(chain, ops)
        raise


def _load_manifest(chain, repo_path, repo_index, item_id, attempt_id,
                   ops=DEFAULT_OPS, *, durable=False):
    raw, file_identity = _secure_read_named(
        chain, repo_path, repo_index, "manifest.json", ops)
    try:
        value = _decode_json(raw, "reconciliation manifest")
    except ReconciliationError as exc:
        return None, raw, file_identity, str(exc)
    problem = _manifest_problem(
        value, item_id, attempt_id, file_identity, chain[-1].identity)
    if problem is not None:
        return None, raw, file_identity, problem
    if raw != _canonical_json(value):
        return None, raw, file_identity, "manifest is not canonical JSON"
    if durable:
        try:
            durable_raw, durable_identity = _secure_read_named(
                chain, repo_path, repo_index, "manifest.json", ops,
                durable=True)
        except ReconciliationError as exc:
            raise _ManifestDurabilityError(
                "manifest and attempt namespace could not be made durable") from exc
        if durable_raw != raw or durable_identity != file_identity:
            raise _ManifestDurabilityError(
                "manifest changed while making its publication durable")
    return value, raw, file_identity, None


def _read_pinned_log(chain, repo_path, repo_index, manifest,
                     ops=DEFAULT_OPS):
    log_prefix = manifest["log_prefix"]
    raw, identity = _secure_read_named(
        chain, repo_path, repo_index, "log-prefix.jsonl", ops)
    if (identity != (log_prefix["dev"], log_prefix["ino"])
            or len(raw) != log_prefix["bytes"]
            or _sha(raw) != log_prefix["sha256"]):
        raise ReconciliationError(
            "pinned event log prefix changed or was replaced")
    events = _parse_log(raw, "pinned event log prefix")
    if len(events) != log_prefix["events"]:
        raise ReconciliationError("pinned event log count changed")
    stage_entries = sum(
        1 for event in events
        if (event.get("event") == "stage.advance"
            and type(event.get("data")) is dict
            and event["data"].get("to") == manifest["stage"]))
    if stage_entries != manifest["stage_entry"]:
        raise ReconciliationError(
            "pinned event log stage identity changed")
    return raw, events


def _fingerprint(observation):
    return _sha(_canonical_json(observation))


def _result(classification, action, attempt_id, writer_state, observation,
            changed_evidence, reason):
    return {
        "classification": classification,
        "action": action,
        "attempt_id": attempt_id,
        "writer_state": writer_state,
        "fingerprint": _fingerprint(observation),
        "changed_evidence": sorted(changed_evidence),
        "reason": reason,
    }


def begin(repo, item_id, stage, obligation, inputs, evidence, worktree=None,
          *, _ops=DEFAULT_OPS):
    """Create and durably publish an immutable pre-dispatch checkpoint."""
    _safe_component(item_id, "item id")
    if type(stage) is not str or not stage.strip() or stage != stage.strip():
        raise ReconciliationError("stage must be a non-empty trimmed string")
    if (type(obligation) is not str or not obligation.strip()
            or obligation != obligation.strip()):
        raise ReconciliationError("obligation must be a non-empty trimmed string")
    input_names = _normalize_paths(inputs, "inputs")
    evidence_names = _normalize_paths(evidence, "evidence")
    _reject_overlapping_paths(input_names, evidence_names)
    attempt_id = secrets.token_hex(16)
    repo_path, repo_index, chain = _open_item_chain(repo, item_id, _ops)
    try:
        meta, item_state, events, log_state = _semantic_snapshot(
            repo_path, item_id, chain, repo_index, _ops)
        if meta.get("stage") != stage:
            raise ReconciliationError(
                f"item stage is {meta.get('stage')!r}, not {stage!r}")
        input_hashes = _snapshot_paths(
            chain, repo_path, repo_index, input_names, False, _ops)
        evidence_hashes = _snapshot_paths(
            chain, repo_path, repo_index, evidence_names, True, _ops)
        checkout = (None if worktree is None else
                    _checkout_snapshot(repo_path, item_id, worktree, _ops))

        _ensure_directory(
            chain, "reconciliation", repo_path, repo_index, attempt_id, _ops)
        _ensure_directory(
            chain, attempt_id, repo_path, repo_index, attempt_id, _ops)

        # The directory work above is not allowed to hide a concurrent input,
        # item, log, or checkout change before the manifest publication point.
        meta_again, item_again, events_again, log_again = _semantic_snapshot(
            repo_path, item_id, chain, repo_index, _ops)
        if (meta_again != meta or item_again != item_state
                or events_again != events or log_again != log_state):
            raise ReconciliationError("checkpoint inputs changed before publication")
        if (_snapshot_paths(chain, repo_path, repo_index,
                            input_names, False, _ops) != input_hashes
                or _snapshot_paths(chain, repo_path, repo_index,
                                   evidence_names, True, _ops) != evidence_hashes):
            raise ReconciliationError("checkpoint evidence changed before publication")
        if checkout is not None:
            if _checkout_snapshot(repo_path, item_id, worktree, _ops) != checkout:
                raise ReconciliationError("checkout changed before publication")

        # Keep a hard link to the exact baseline log generation. The current
        # logger replaces log.jsonl on every append, so this pin both proves
        # the original inode and prevents its number from being recycled into
        # a later generation while the checkpoint remains live.
        _pin_log_prefix(
            chain, repo_path, repo_index, log_state, attempt_id, _ops)

        stage_entry = sum(
            1 for event in events
            if (event.get("event") == "stage.advance"
                and type(event.get("data")) is dict
                and event["data"].get("to") == stage))
        attempt_identity = chain[-1].identity

        def payload(file_identity):
            return {
                "version": 1,
                "attempt_id": attempt_id,
                "item": item_id,
                "stage": stage,
                "stage_entry": stage_entry,
                "obligation": obligation,
                "inputs": input_hashes,
                "evidence": evidence_hashes,
                "item_file": {
                    "sha256": _sha(item_state[0]),
                    "dev": item_state[1][0],
                    "ino": item_state[1][1],
                },
                "log_prefix": {
                    "bytes": len(log_state[0]),
                    "sha256": _sha(log_state[0]),
                    "events": len(events),
                    "dev": log_state[1][0],
                    "ino": log_state[1][1],
                },
                "attempt_dir": _identity_record(attempt_identity),
                "manifest_file": _identity_record(file_identity),
                "checkout": checkout,
            }

        _manifest, cleanup_pending = _publish_json(
            chain, repo_path, repo_index, "manifest.json", payload,
            attempt_id, _ops)
        return {"attempt_id": attempt_id,
                "cleanup_pending": cleanup_pending}
    finally:
        _close_chain(chain, _ops)


def _matching_checkout(repo_path, item_id, manifest_checkout, supplied,
                       ops=DEFAULT_OPS):
    if manifest_checkout is None:
        return supplied is None
    try:
        canonical = ownership.canonical_worktree(repo_path, item_id, supplied)
        details = ops.stat(str(canonical), follow_symlinks=False)
    except (ownership.OwnershipError, OSError):
        return False
    return (str(canonical) == manifest_checkout["path"]
            and _identity(details) == (
                manifest_checkout["dev"], manifest_checkout["ino"]))


def discover(repo, item_id, stage, obligation, inputs, worktree=None,
             *, _ops=DEFAULT_OPS):
    """Return every safely bound attempt matching a fresh parent invocation."""
    _safe_component(item_id, "item id")
    if type(stage) is not str or type(obligation) is not str:
        raise ReconciliationError("stage and obligation must be strings")
    input_names = _normalize_paths(inputs, "inputs")
    repo_path, repo_index, chain = _open_item_chain(repo, item_id, _ops)
    try:
        try:
            fd = _ops.open("reconciliation", _DIRECTORY_FLAGS,
                           dir_fd=chain[-1].fd)
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise ReconciliationError("unsafe reconciliation directory") from exc
        chain.append(_handle(fd, "reconciliation", _ops))
        _validate_chain(chain, repo_path, repo_index, _ops)
        try:
            names = sorted(_ops.listdir(chain[-1].fd))
        except OSError as exc:
            raise ReconciliationError("cannot enumerate reconciliation attempts") from exc
        matches = []
        for attempt_id in names:
            if _ATTEMPT_RE.fullmatch(attempt_id) is None:
                continue
            _append_directory(chain, attempt_id, _ops)
            try:
                manifest, _raw, _file_identity, problem = _load_manifest(
                    chain, repo_path, repo_index, item_id, attempt_id, _ops,
                    durable=True)
                if problem is not None:
                    raise ReconciliationError(problem)
                _read_pinned_log(
                    chain, repo_path, repo_index, manifest, _ops)
                if (manifest["stage"] != stage
                        or manifest["obligation"] != obligation
                        or sorted(manifest["inputs"]) != input_names):
                    continue
                current_inputs = _snapshot_paths(
                    chain, repo_path, repo_index, input_names, False, _ops)
                if current_inputs != manifest["inputs"]:
                    continue
                if not _matching_checkout(
                        repo_path, item_id, manifest["checkout"], worktree, _ops):
                    continue
                matches.append(attempt_id)
            finally:
                handle = chain.pop()
                try:
                    _ops.close(handle.fd)
                except OSError:
                    pass
        return matches
    finally:
        _close_chain(chain, _ops)


def _contradictory(attempt_id, writer_state, reason, detail=None):
    observation = {"error": reason}
    if detail is not None:
        observation["detail_sha256"] = _sha(detail)
    return _result("contradictory", "stop", attempt_id, writer_state,
                   observation, [], reason)


def _suffix_events(raw):
    try:
        return _parse_log(raw, "post-checkpoint event log"), None
    except ReconciliationError as exc:
        return [], str(exc)


_NORMAL_TRANSITIONS = {
    "idea": frozenset({"triage"}),
    "triage": frozenset({"spec"}),
    # Backend items omit design; items with no journey assurance omit assure.
    "spec": frozenset({"design", "plan"}),
    "design": frozenset({"plan"}),
    "plan": frozenset({"implement"}),
    "implement": frozenset({"review"}),
    "review": frozenset({"verify"}),
    "verify": frozenset({"assure", "ship"}),
    "assure": frozenset({"ship"}),
    "ship": frozenset({"done"}),
    "done": frozenset(),
}
_REWORK_SOURCES = frozenset({"review", "verify", "assure"})


def _transition_step(source, destination, pause_origin):
    """Validate one engine-shaped edge and return the active pause origin."""
    normal = frozenset(machine.STAGES)
    special = frozenset(machine.SPECIAL)
    if source not in normal | special or destination not in normal | special:
        raise ReconciliationError(
            "post-checkpoint stage transition is illegitimate")
    if source in special:
        # A checkpoint taken while already paused lacks the pre-checkpoint
        # origin needed to prove a later resume. Fail closed rather than infer.
        if pause_origin is None or destination != pause_origin:
            raise ReconciliationError(
                "post-checkpoint pause/resume transition is illegitimate")
        return None
    if destination in special:
        if source == "done":
            raise ReconciliationError(
                "post-checkpoint stage transition is illegitimate")
        return source
    if pause_origin is not None:
        raise ReconciliationError(
            "post-checkpoint pause/resume transition is illegitimate")
    if (destination not in _NORMAL_TRANSITIONS[source]
            and not (source in _REWORK_SOURCES
                     and destination in {"implement", "spec"})):
        raise ReconciliationError(
            "post-checkpoint stage transition is illegitimate")
    return None


def inspect(repo, item_id, attempt_id, writer_state, worktree=None,
            *, _ops=DEFAULT_OPS):
    """Classify durable change since one exact dispatch checkpoint."""
    if writer_state not in ("active", "terminal"):
        raise ReconciliationError("writer_state must be active or terminal")
    repo_path, repo_index, chain = _open_attempt_chain(
        repo, item_id, attempt_id, _ops)
    try:
        try:
            manifest, raw_manifest, _manifest_identity, problem = _load_manifest(
                chain, repo_path, repo_index, item_id, attempt_id, _ops,
                durable=True)
        except _ManifestDurabilityError as exc:
            return _contradictory(attempt_id, writer_state, str(exc))
        if problem is not None:
            return _contradictory(
                attempt_id, writer_state, problem, raw_manifest)

        log_prefix = manifest["log_prefix"]
        try:
            pinned_raw, pinned_events = _read_pinned_log(
                chain, repo_path, repo_index, manifest, _ops)
            meta, item_state, current_events, log_state = _semantic_snapshot(
                repo_path, item_id, chain, repo_index, _ops,
                durable=True)
        except ReconciliationError as exc:
            return _contradictory(attempt_id, writer_state, str(exc))

        baseline_item_identity = (
            manifest["item_file"]["dev"], manifest["item_file"]["ino"])
        if (item_state[1] != baseline_item_identity
                and _sha(item_state[0]) ==
                manifest["item_file"]["sha256"]):
            return _contradictory(
                attempt_id, writer_state,
                "item file identity changed without content change")
        current_log, current_log_identity = log_state
        baseline_log_identity = (log_prefix["dev"], log_prefix["ino"])
        log_generation_changed = current_log_identity != baseline_log_identity
        prefix_length = log_prefix["bytes"]
        if (len(current_log) < prefix_length
                or _sha(current_log[:prefix_length]) != log_prefix["sha256"]):
            return _contradictory(
                attempt_id, writer_state, "event log prefix changed")
        prefix_events = pinned_events
        if current_log[:prefix_length] != pinned_raw:
            return _contradictory(
                attempt_id, writer_state, "event log prefix changed")
        prefix_stage_entry = sum(
            1 for event in prefix_events
            if (event.get("event") == "stage.advance"
                and type(event.get("data")) is dict
                and event["data"].get("to") == manifest["stage"]))
        if (len(prefix_events) != log_prefix["events"]
                or prefix_stage_entry != manifest["stage_entry"]):
            return _contradictory(
                attempt_id, writer_state, "manifest stage/log identity changed")
        if current_events[:len(prefix_events)] != prefix_events:
            return _contradictory(
                attempt_id, writer_state,
                "event log semantic validation disagrees")
        suffix, suffix_problem = _suffix_events(current_log[prefix_length:])
        if (suffix_problem is None
                and prefix_events + suffix != current_events):
            return _contradictory(
                attempt_id, writer_state,
                "event log semantic validation disagrees")

        # logs.append_event publishes a complete old+new image by atomic
        # replacement.  Therefore a legitimate append has a new inode, the
        # exact checkpoint prefix, and at least one complete valid suffix
        # event.  An equal-byte replacement, an in-place append, or a new
        # malformed image cannot be a publication made by the current logger.
        # Keeping this check after prefix validation preserves a precise
        # prefix-corruption diagnosis while admitting the logger's COW lineage.
        if log_generation_changed and len(current_log) == prefix_length:
            return _contradictory(
                attempt_id, writer_state,
                "event log identity changed without an append")
        if not log_generation_changed and len(current_log) != prefix_length:
            return _contradictory(
                attempt_id, writer_state, "event log changed in place")
        if log_generation_changed and suffix_problem is not None:
            return _contradictory(
                attempt_id, writer_state,
                "replacement event log has an invalid appended record")

        try:
            current_inputs = _snapshot_paths(
                chain, repo_path, repo_index, sorted(manifest["inputs"]),
                False, _ops, durable=True)
            current_evidence = _snapshot_paths(
                chain, repo_path, repo_index, sorted(manifest["evidence"]),
                True, _ops, durable=True)
        except ReconciliationError as exc:
            return _contradictory(attempt_id, writer_state, str(exc))
        if current_inputs != manifest["inputs"]:
            return _contradictory(
                attempt_id, writer_state, "checkpoint input changed")
        for path, baseline in manifest["evidence"].items():
            if baseline is not None and current_evidence[path] is None:
                return _contradictory(
                    attempt_id, writer_state,
                    f"checkpoint evidence was deleted: {path}")

        if manifest["checkout"] is None:
            if worktree is not None:
                return _contradictory(
                    attempt_id, writer_state, "unexpected worktree supplied")
            current_checkout = None
        else:
            try:
                expected = manifest["checkout"]
                current_checkout = _checkout_snapshot(
                    repo_path, item_id, worktree, _ops, durable=True,
                    baseline_head=expected["head"])
            except ReconciliationError as exc:
                return _contradictory(attempt_id, writer_state, str(exc))
            if (current_checkout["path"] != expected["path"]
                    or current_checkout["dev"] != expected["dev"]
                    or current_checkout["ino"] != expected["ino"]):
                return _contradictory(
                    attempt_id, writer_state, "wrong or replaced worktree")

        changed_evidence = [
            name for name, digest in current_evidence.items()
            if digest != manifest["evidence"][name]]
        observation = {
            "item": {"sha256": _sha(item_state[0]),
                     "stage": meta.get("stage")},
            "log": {"bytes": len(current_log),
                    "sha256": _sha(current_log)},
            "inputs": {
                name: {"state": "regular", "sha256": digest}
                for name, digest in sorted(current_inputs.items())},
            "evidence": {
                name: ({"state": "absent"} if digest is None else
                       {"state": "regular", "sha256": digest})
                for name, digest in sorted(current_evidence.items())},
            "checkout": current_checkout,
        }
        if suffix_problem is not None:
            if writer_state == "active":
                return _result(
                    "partial", "wait-active", attempt_id, writer_state,
                    observation, changed_evidence, suffix_problem)
            return _result(
                "contradictory", "stop", attempt_id, writer_state,
                observation, changed_evidence, suffix_problem)

        last_transition = None
        eligible = None
        expected_source = manifest["stage"]
        pause_origin = None
        for event in suffix:
            if event.get("event") != "stage.advance":
                continue
            data = event.get("data")
            if (type(data) is not dict or type(data.get("from")) is not str
                    or type(data.get("to")) is not str):
                reason = "post-checkpoint stage transition is malformed"
                if writer_state == "active":
                    return _result(
                        "partial", "wait-active", attempt_id, writer_state,
                        observation, changed_evidence, reason)
                return _result(
                    "contradictory", "stop", attempt_id, writer_state,
                    observation, changed_evidence, reason)
            if data["from"] != expected_source:
                return _result(
                    "contradictory", "stop", attempt_id, writer_state,
                    observation, changed_evidence,
                    "post-checkpoint stage transition history is disconnected")
            try:
                pause_origin = _transition_step(
                    data["from"], data["to"], pause_origin)
            except ReconciliationError as exc:
                return _result(
                    "contradictory", "stop", attempt_id, writer_state,
                    observation, changed_evidence, str(exc))
            if eligible is None:
                eligible = event
            expected_source = data["to"]
            last_transition = event
        if last_transition is not None:
            expected_stage = last_transition["data"]["to"]
            if meta.get("stage") != expected_stage:
                return _result(
                    "contradictory", "stop", attempt_id, writer_state,
                    observation, changed_evidence,
                    "item stage disagrees with the latest transition")

        if writer_state == "active":
            return _result(
                "partial", "wait-active", attempt_id, writer_state,
                observation, changed_evidence, "writer is still active")
        if eligible is not None:
            return _result(
                "complete", "adopt", attempt_id, writer_state,
                observation, changed_evidence,
                "engine-recorded stage transition completed the handoff")
        if (_sha(item_state[0]) != manifest["item_file"]["sha256"]
                or meta.get("stage") != manifest["stage"]):
            return _result(
                "contradictory", "stop", attempt_id, writer_state,
                observation, changed_evidence,
                "item metadata changed without a stage transition")
        if len(changed_evidence) == len(manifest["evidence"]):
            return _result(
                "complete", "adopt", attempt_id, writer_state,
                observation, changed_evidence,
                "all declared transport evidence changed")
        checkout_changed = (
            current_checkout is not None
            and (current_checkout["head"] != manifest["checkout"]["head"]
                 or current_checkout["state_sha256"]
                 != manifest["checkout"]["state_sha256"]))
        if changed_evidence or checkout_changed:
            return _result(
                "partial", "continue", attempt_id, writer_state,
                observation, changed_evidence,
                "durable partial progress exists")
        return _result(
            "absent", "count-failure", attempt_id, writer_state,
            observation, [], "no durable progress exists")
    finally:
        _close_chain(chain, _ops)


def _claim_problem(value, item_id, attempt_id, file_identity):
    if (type(value) is not dict
            or set(value) != {
                "version", "attempt_id", "fingerprint", "obligation",
                "marker_file"}
            or value.get("version") != 1
            or type(value.get("version")) is not int
            or value.get("attempt_id") != attempt_id
            or not _valid_digest(value.get("fingerprint"))
            or type(value.get("obligation")) is not str
            or not value["obligation"]
            or not _valid_identity(value.get("marker_file"))
            or value["marker_file"] != _identity_record(file_identity)):
        return "continuation claim is malformed or replaced"
    return None


_CONTINUATION_BINDING_KEYS = {
    "version", "attempt_id", "continuations_dir", "binding_file",
}


def _continuation_binding_problem(value, attempt_id, file_identity,
                                  directory_identity):
    if (type(value) is not dict
            or set(value) != _CONTINUATION_BINDING_KEYS
            or value.get("version") != 1
            or type(value.get("version")) is not int
            or value.get("attempt_id") != attempt_id
            or not _valid_identity(value.get("continuations_dir"))
            or value["continuations_dir"] !=
            _identity_record(directory_identity)
            or not _valid_identity(value.get("binding_file"))
            or value["binding_file"] != _identity_record(file_identity)):
        return "continuation directory binding is malformed or replaced"
    return None


def _load_continuation_binding(chain, repo_path, repo_index, attempt_id,
                               ops=DEFAULT_OPS):
    parent_chain = chain[:-1]
    try:
        details = ops.stat(
            "continuations.json", dir_fd=parent_chain[-1].fd,
            follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ReconciliationError(
            "continuation directory binding cannot be inspected") from exc
    if not stat.S_ISREG(details.st_mode):
        raise ReconciliationError("continuation directory binding is unsafe")
    raw, file_identity = _secure_read_named(
        parent_chain, repo_path, repo_index, "continuations.json", ops)
    value = _decode_json(raw, "continuation directory binding")
    problem = _continuation_binding_problem(
        value, attempt_id, file_identity, chain[-1].identity)
    if problem is not None or raw != _canonical_json(value):
        raise ReconciliationError(
            problem or "continuation directory binding is not canonical")
    return value


def _bind_continuation_directory(chain, repo_path, repo_index, attempt_id,
                                 ops=DEFAULT_OPS):
    existing = _load_continuation_binding(
        chain, repo_path, repo_index, attempt_id, ops)
    if existing is not None:
        _validate_chain(chain, repo_path, repo_index, ops)
        return existing
    directory_identity = chain[-1].identity

    def payload(file_identity):
        return {
            "version": 1,
            "attempt_id": attempt_id,
            "continuations_dir": _identity_record(directory_identity),
            "binding_file": _identity_record(file_identity),
        }

    try:
        _publish_json(
            chain[:-1], repo_path, repo_index, "continuations.json", payload,
            attempt_id, ops)
    except FileExistsError:
        # A concurrent parent may have published the one immutable binding.
        # It is authority only after the exact self-bound record is reloaded.
        pass
    existing = _load_continuation_binding(
        chain, repo_path, repo_index, attempt_id, ops)
    if existing is None:
        raise ReconciliationError("continuation directory binding is missing")
    _validate_chain(chain, repo_path, repo_index, ops)
    return existing


def _existing_claim(chain, repo_path, repo_index, item_id, attempt_id,
                    ops=DEFAULT_OPS):
    try:
        details = ops.stat("claim.json", dir_fd=chain[-1].fd,
                           follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ReconciliationError("continuation claim cannot be inspected") from exc
    if not stat.S_ISREG(details.st_mode):
        raise ReconciliationError("continuation claim is unsafe")
    raw, file_identity = _secure_read_named(
        chain, repo_path, repo_index, "claim.json", ops)
    value = _decode_json(raw, "continuation claim")
    problem = _claim_problem(value, item_id, attempt_id, file_identity)
    if problem is not None or raw != _canonical_json(value):
        raise ReconciliationError(problem or "continuation claim is not canonical")
    return value


def _same_claimable_result(left, right):
    keys = ("classification", "action", "attempt_id", "writer_state",
            "fingerprint")
    return (type(left) is dict and all(left.get(key) == right.get(key)
                                      for key in keys))


def claim_continuation(repo, item_id, attempt_id, result, *, _ops=DEFAULT_OPS):
    """Atomically authorize the sole continuation for a partial attempt."""
    if (type(result) is not dict or result.get("writer_state") != "terminal"
            or result.get("classification") != "partial"
            or result.get("action") != "continue"
            or result.get("attempt_id") != attempt_id):
        raise ReconciliationError("result is not a terminal partial continuation")
    repo_path, repo_index, chain = _open_attempt_chain(
        repo, item_id, attempt_id, _ops)
    try:
        manifest, raw_manifest, _identity_value, problem = _load_manifest(
            chain, repo_path, repo_index, item_id, attempt_id, _ops)
        if problem is not None:
            raise ReconciliationError(problem)
        supplied = (None if manifest["checkout"] is None
                    else manifest["checkout"]["path"])
        current = inspect(
            repo_path, item_id, attempt_id, "terminal", supplied, _ops=_ops)
        if not _same_claimable_result(result, current):
            return {"action": "stop", "reason": "observation-changed",
                    "cleanup_pending": False}
        _ensure_directory(
            chain, "continuations", repo_path, repo_index, attempt_id, _ops)
        _bind_continuation_directory(
            chain, repo_path, repo_index, attempt_id, _ops)
        if _existing_claim(
                chain, repo_path, repo_index, item_id, attempt_id, _ops) is not None:
            return {"action": "stop", "reason": "already-claimed",
                    "cleanup_pending": False}

        # Close the inspect-to-publish window as far as the local filesystem
        # permits. Any post-commit change consumes the one claim but returns no
        # dispatch authorization.
        current = inspect(
            repo_path, item_id, attempt_id, "terminal", supplied, _ops=_ops)
        if not _same_claimable_result(result, current):
            return {"action": "stop", "reason": "observation-changed",
                    "cleanup_pending": False}

        def payload(file_identity):
            return {
                "version": 1,
                "attempt_id": attempt_id,
                "fingerprint": result["fingerprint"],
                "obligation": manifest["obligation"],
                "marker_file": _identity_record(file_identity),
            }

        try:
            _marker, cleanup_pending = _publish_json(
                chain, repo_path, repo_index, "claim.json", payload,
                attempt_id, _ops)
        except FileExistsError:
            if _existing_claim(
                    chain, repo_path, repo_index, item_id,
                    attempt_id, _ops) is None:
                raise ReconciliationError("continuation claim race is unresolved")
            return {"action": "stop", "reason": "already-claimed",
                    "cleanup_pending": False}

        after = inspect(
            repo_path, item_id, attempt_id, "terminal", supplied, _ops=_ops)
        if not _same_claimable_result(result, after):
            return {"action": "stop", "reason": "observation-changed",
                    "cleanup_pending": cleanup_pending}
        try:
            _validate_chain(chain, repo_path, repo_index, _ops)
        except ReconciliationError as exc:
            raise PublicationUncertain(
                "continuation claim chain changed after publication",
                attempt_id, True) from exc
        return {"action": "continue", "reason": "claimed",
                "cleanup_pending": cleanup_pending}
    finally:
        _close_chain(chain, _ops)
