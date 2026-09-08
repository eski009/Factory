"""Strict, descriptor-relative snapshots and durable file publication.

Mutations take an advisory exclusive lock on the opened ``root`` directory.
Every cooperating writer for that root must use these mutation APIs (or hold
the later shared item lock) for the compare/install interval to be closed.
POSIX has no stdlib primitive that makes a pathname comparison and rename one
indivisible operation, and advisory locks cannot stop a hostile same-user
process.  Descriptor-relative rechecks narrow that unavoidable boundary and
refuse detected interference; they do not claim to sandbox such a process.
"""

import fcntl
import hashlib
import json
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class SafeIOError(Exception):
    """A path was unsafe, unstable, or did not match its snapshot."""


DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
DIRECTORY_FLAGS |= getattr(os, "O_NOFOLLOW", 0)
FILE_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_FILE_READ_FLAGS = os.O_RDONLY | FILE_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)


@dataclass(frozen=True)
class FileSnapshot:
    root: Path
    relative: PurePosixPath
    data: bytes
    sha256: str
    file_identity: tuple[int, int, int, int, int]
    directory_identities: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class MissingSnapshot:
    root: Path
    relative: PurePosixPath
    parent_identities: tuple[tuple[int, int], ...]
    transaction_nonce: str


@dataclass(frozen=True)
class _DirectoryHandle:
    fd: int
    entry_name: str | None
    identity: tuple[int, int]


def _directory_identity(details):
    return (details.st_dev, details.st_ino)


def _file_identity(details):
    return (details.st_dev, details.st_ino, details.st_size,
            details.st_mtime_ns, details.st_ctime_ns)


def _close_chain(chain):
    first_error = None
    for handle in reversed(chain):
        try:
            os.close(handle.fd)
        except BaseException as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


def _make_directory_handle(fd, entry_name):
    try:
        details = os.fstat(fd)
        if not stat.S_ISDIR(details.st_mode):
            raise SafeIOError(
                f"path component is not a directory: {entry_name or '/'}")
        return _DirectoryHandle(
            fd=fd,
            entry_name=entry_name,
            identity=_directory_identity(details),
        )
    except BaseException:
        os.close(fd)
        raise


def _append_directory(chain, name):
    try:
        fd = os.open(name, DIRECTORY_FLAGS, dir_fd=chain[-1].fd)
    except OSError as exc:
        raise SafeIOError(f"unsafe directory component: {name}") from exc
    chain.append(_make_directory_handle(fd, name))


def _validate_chain(chain):
    for index, handle in enumerate(chain):
        try:
            details = os.fstat(handle.fd)
        except OSError as exc:
            raise SafeIOError("directory chain is closed") from exc
        if (not stat.S_ISDIR(details.st_mode) or
                _directory_identity(details) != handle.identity):
            raise SafeIOError("directory identity changed")
        if index == 0:
            continue
        parent = chain[index - 1]
        try:
            entry = os.stat(handle.entry_name, dir_fd=parent.fd,
                            follow_symlinks=False)
        except OSError as exc:
            raise SafeIOError(
                f"directory chain was detached: {handle.entry_name}") from exc
        if (not stat.S_ISDIR(entry.st_mode) or
                _directory_identity(entry) != handle.identity):
            raise SafeIOError(
                f"directory chain was replaced: {handle.entry_name}")


def _resolve_root(root):
    try:
        canonical = Path(root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise SafeIOError("root is missing or cannot be resolved") from exc
    if not canonical.is_absolute():
        raise SafeIOError("root must resolve to an absolute path")
    return canonical


def _relative_path(relative):
    try:
        raw = os.fspath(relative)
    except TypeError as exc:
        raise SafeIOError("relative path must be path-like") from exc
    if not isinstance(raw, str):
        raise SafeIOError("relative path must be text")
    if (not raw or "\0" in raw or "\\" in raw or raw.startswith("/") or
            raw.endswith("/") or "//" in raw):
        raise SafeIOError(f"unsafe relative path: {raw!r}")
    parts = raw.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise SafeIOError(f"unsafe relative path: {raw!r}")
    path = PurePosixPath(*parts)
    if path.is_absolute() or not path.parts:
        raise SafeIOError(f"unsafe relative path: {raw!r}")
    return path


def _open_root_chain(root):
    chain = []
    try:
        fd = os.open(root.anchor, DIRECTORY_FLAGS)
        chain.append(_make_directory_handle(fd, None))
        for component in root.parts[1:]:
            _append_directory(chain, component)
        _validate_chain(chain)
        return chain
    except BaseException:
        _close_chain(chain)
        raise


def _identities(chain):
    return tuple(handle.identity for handle in chain)


def _require_absent(directory_fd, name):
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise SafeIOError(f"cannot prove path component absent: {name}") from exc
    raise SafeIOError(f"path component unexpectedly exists: {name}")


def _read_regular_file(directory_fd, name, limit):
    if (isinstance(limit, bool) or not isinstance(limit, int) or limit < 0):
        raise SafeIOError("read limit must be a non-negative integer")
    try:
        fd = os.open(name, _FILE_READ_FLAGS, dir_fd=directory_fd)
    except OSError as exc:
        raise SafeIOError(f"unsafe or missing regular file: {name}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise SafeIOError(f"path is not a regular file: {name}")
        identity = _file_identity(before)
        if before.st_size > limit:
            raise SafeIOError(f"file exceeds read limit: {name}")

        remaining = before.st_size
        chunks = []
        while remaining:
            try:
                chunk = os.read(fd, min(65536, remaining))
            except OSError as exc:
                raise SafeIOError(f"file read failed: {name}") from exc
            if not chunk:
                raise SafeIOError(f"short read from file: {name}")
            chunks.append(chunk)
            remaining -= len(chunk)
        try:
            extra = os.read(fd, 1)
        except OSError as exc:
            raise SafeIOError(f"file read failed: {name}") from exc
        if extra:
            raise SafeIOError(f"file grew while being read: {name}")

        after = os.fstat(fd)
        if (not stat.S_ISREG(after.st_mode) or
                _file_identity(after) != identity):
            raise SafeIOError(f"file changed while being read: {name}")
        try:
            entry = os.stat(name, dir_fd=directory_fd,
                            follow_symlinks=False)
        except OSError as exc:
            raise SafeIOError(f"file was detached while being read: {name}") from exc
        if (not stat.S_ISREG(entry.st_mode) or
                _file_identity(entry) != identity):
            raise SafeIOError(f"file was replaced while being read: {name}")
        data = b"".join(chunks)
        if len(data) != identity[2]:
            raise SafeIOError(f"short read from file: {name}")
        return data, identity
    finally:
        os.close(fd)


def _missing_snapshot(root, relative, chain):
    return MissingSnapshot(
        root=root,
        relative=relative,
        parent_identities=_identities(chain),
        transaction_nonce=uuid.uuid4().hex,
    )


def _snapshot_from_chain(root, relative, limit, allow_missing):
    chain = _open_root_chain(root)
    try:
        for component in relative.parts[:-1]:
            try:
                _append_directory(chain, component)
            except SafeIOError as exc:
                if not allow_missing or not isinstance(exc.__cause__, FileNotFoundError):
                    raise
                _require_absent(chain[-1].fd, component)
                _validate_chain(chain)
                return _missing_snapshot(root, relative, chain)

        leaf = relative.name
        try:
            data, identity = _read_regular_file(chain[-1].fd, leaf, limit)
        except SafeIOError as exc:
            if not allow_missing or not isinstance(exc.__cause__, FileNotFoundError):
                raise
            _require_absent(chain[-1].fd, leaf)
            _validate_chain(chain)
            return _missing_snapshot(root, relative, chain)
        _validate_chain(chain)
        return FileSnapshot(
            root=root,
            relative=relative,
            data=data,
            sha256=hashlib.sha256(data).hexdigest(),
            file_identity=identity,
            directory_identities=_identities(chain),
        )
    finally:
        _close_chain(chain)


def _relative_parent_count(snapshot):
    identities = (snapshot.directory_identities
                  if isinstance(snapshot, FileSnapshot)
                  else snapshot.parent_identities)
    count = len(identities) - len(snapshot.root.parts)
    if count < 0 or count > len(snapshot.relative.parts) - 1:
        raise SafeIOError("snapshot contains an invalid directory chain")
    return count


def _open_expected_parent(snapshot):
    expected = (snapshot.directory_identities
                if isinstance(snapshot, FileSnapshot)
                else snapshot.parent_identities)
    relative_count = _relative_parent_count(snapshot)
    chain = _open_root_chain(snapshot.root)
    try:
        for component in snapshot.relative.parts[:relative_count]:
            _append_directory(chain, component)
        if _identities(chain) != expected:
            raise SafeIOError("snapshot directory identity changed")
        _validate_chain(chain)
        return chain
    except BaseException:
        _close_chain(chain)
        raise


def _assert_file_snapshot(snapshot, limit=None):
    if not isinstance(snapshot, FileSnapshot):
        raise SafeIOError("expected a file snapshot")
    chain = _open_expected_parent(snapshot)
    try:
        effective_limit = len(snapshot.data) if limit is None else limit
        data, identity = _read_regular_file(
            chain[-1].fd, snapshot.relative.name, effective_limit)
        _validate_chain(chain)
        if (identity != snapshot.file_identity or data != snapshot.data or
                hashlib.sha256(data).hexdigest() != snapshot.sha256):
            raise SafeIOError(f"file no longer matches snapshot: {snapshot.relative}")
    finally:
        _close_chain(chain)


def _assert_missing_snapshot(snapshot):
    if not isinstance(snapshot, MissingSnapshot):
        raise SafeIOError("expected a missing snapshot")
    _validate_transaction_nonce(snapshot.transaction_nonce)
    relative_count = _relative_parent_count(snapshot)
    chain = _open_expected_parent(snapshot)
    try:
        missing_component = snapshot.relative.parts[relative_count]
        _require_absent(chain[-1].fd, missing_component)
        _validate_chain(chain)
    finally:
        _close_chain(chain)


def snapshot_path(root, relative, *, limit=1_048_576,
                  allow_missing=False) -> FileSnapshot | MissingSnapshot:
    canonical = _resolve_root(root)
    path = _relative_path(relative)
    snapshot = _snapshot_from_chain(canonical, path, limit, allow_missing)
    revalidate(snapshot)
    return snapshot


def snapshot_many(root, relatives, *, limit=1_048_576,
                  allow_missing=False) -> tuple[
                      FileSnapshot | MissingSnapshot, ...]:
    canonical = _resolve_root(root)
    paths = tuple(_relative_path(relative) for relative in relatives)
    if len(set(paths)) != len(paths):
        raise SafeIOError("duplicate relative paths are not allowed")
    snapshots = tuple(
        _snapshot_from_chain(canonical, path, limit, allow_missing)
        for path in paths
    )
    revalidate(snapshots)
    return snapshots


def revalidate(snapshot_or_many) -> None:
    if isinstance(snapshot_or_many, FileSnapshot):
        _assert_file_snapshot(snapshot_or_many)
        return
    if isinstance(snapshot_or_many, MissingSnapshot):
        _assert_missing_snapshot(snapshot_or_many)
        return
    try:
        snapshots = tuple(snapshot_or_many)
    except TypeError as exc:
        raise SafeIOError("expected a snapshot or iterable of snapshots") from exc
    for snapshot in snapshots:
        if isinstance(snapshot, FileSnapshot):
            _assert_file_snapshot(snapshot)
        elif isinstance(snapshot, MissingSnapshot):
            _assert_missing_snapshot(snapshot)
        else:
            raise SafeIOError("snapshot iterable contains an invalid value")


def _write_all(fd, data):
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = os.write(fd, view[written:])
        if count <= 0:
            raise SafeIOError("short write to temporary file")
        written += count


def _inode_identity(details):
    return (details.st_dev, details.st_ino)


def _named_details(directory_fd, name):
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as exc:
        raise SafeIOError(f"filesystem entry disappeared: {name}") from exc


def _require_named_inode(directory_fd, name, expected, *, regular=False,
                         directory=False):
    details = _named_details(directory_fd, name)
    if _inode_identity(details) != expected:
        raise SafeIOError(f"filesystem entry identity changed: {name}")
    if regular and not stat.S_ISREG(details.st_mode):
        raise SafeIOError(f"filesystem entry is not a regular file: {name}")
    if directory and not stat.S_ISDIR(details.st_mode):
        raise SafeIOError(f"filesystem entry is not a directory: {name}")
    return details


def _unlink_if_identity(directory_fd, name, expected):
    """Unlink only the exact entry observed by the caller.

    The final stat-to-unlink step is governed by the same cooperative advisory
    lock as installation.  A hostile process can still race this POSIX
    boundary; there is no portable Python stdlib unlink-by-inode operation.
    """
    try:
        details = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    if _inode_identity(details) != expected:
        return False
    os.unlink(name, dir_fd=directory_fd)
    return True


def _cleanup_named_entry(directory_fd, name):
    try:
        details = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    _unlink_if_identity(directory_fd, name, _inode_identity(details))


def _atomic_write(directory_fd, name, data, before_replace=None,
                  before_install=None, after_install=None):
    """Worker-compatible atomic replacement with inode-bound installation."""
    temp_name = f".{name}.tmp-{uuid.uuid4().hex}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | FILE_NOFOLLOW
    fd = os.open(temp_name, flags, 0o600, dir_fd=directory_fd)
    try:
        with os.fdopen(os.dup(fd), "wb", closefd=True) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise SafeIOError("replacement temporary is not a regular file")
        opened_identity = _inode_identity(opened)
        if before_replace is not None:
            before_replace()
        if before_install is not None:
            before_install()
        _require_named_inode(
            directory_fd, temp_name, opened_identity, regular=True)
        os.replace(temp_name, name, src_dir_fd=directory_fd,
                   dst_dir_fd=directory_fd)
        if after_install is not None:
            after_install()
        try:
            _require_named_inode(
                directory_fd, name, opened_identity, regular=True)
        except BaseException:
            _cleanup_named_entry(directory_fd, name)
            os.fsync(directory_fd)
            raise
        os.fsync(directory_fd)
        return opened_identity
    finally:
        os.close(fd)
        _cleanup_named_entry(directory_fd, temp_name)


def _publish_bound(directory_fd, name, data, *, before_install=None,
                   after_install=None):
    temp_name = f".safeio-{uuid.uuid4().hex}.tmp"
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | FILE_NOFOLLOW |
             getattr(os, "O_NONBLOCK", 0))
    try:
        fd = os.open(temp_name, flags, 0o600, dir_fd=directory_fd)
    except OSError as exc:
        raise SafeIOError("could not create publication temporary file") from exc
    published = False
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode):
            raise SafeIOError("publication temporary is not a regular file")
        _write_all(fd, data)
        os.fsync(fd)
        opened_identity = _inode_identity(os.fstat(fd))
        if before_install is not None:
            before_install()
        _require_named_inode(
            directory_fd, temp_name, opened_identity, regular=True)
        _require_absent(directory_fd, name)
        try:
            os.link(temp_name, name,
                    src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                    follow_symlinks=False)
        except FileExistsError as exc:
            raise SafeIOError(f"destination already exists: {name}") from exc
        except OSError as exc:
            raise SafeIOError(f"could not publish destination: {name}") from exc
        published = True
        if after_install is not None:
            after_install()
        try:
            _require_named_inode(
                directory_fd, name, opened_identity, regular=True)
        except BaseException:
            _cleanup_named_entry(directory_fd, name)
            os.fsync(directory_fd)
            raise
        if not _unlink_if_identity(directory_fd, temp_name, opened_identity):
            _cleanup_named_entry(directory_fd, name)
            os.fsync(directory_fd)
            raise SafeIOError("publication temporary identity changed")
        os.fsync(directory_fd)
        return opened_identity
    finally:
        os.close(fd)
        _cleanup_named_entry(directory_fd, temp_name)
        if published:
            # A failed verification path removes the exact observed
            # destination above.  Successful publication remains installed.
            pass


def _publication_data(data):
    if not isinstance(data, bytes):
        raise SafeIOError("published data must be bytes")
    return data


def _before_publish():
    """Test seam immediately before the exclusive install boundary."""


def _before_replace():
    """Test seam immediately before the final compare-and-replace boundary."""


def _before_replace_install():
    """Test seam after comparison, immediately before replacement install."""


def _after_directory_install(component, identity):
    """Test seam after durable directory identity progress is recorded."""


def _after_staging_mkdir(component, staging):
    """Test seam after durable mkdir, before its inode is journal-bound."""


def _lock_root(chain, root):
    root_index = len(root.parts) - 1
    if root_index < 0 or root_index >= len(chain):
        raise SafeIOError("directory chain does not contain its root")
    try:
        fcntl.flock(chain[root_index].fd, fcntl.LOCK_EX)
    except OSError as exc:
        raise SafeIOError("could not acquire root mutation lock") from exc
    _validate_chain(chain)


def _snapshot_result(chain, root, relative, expected_data,
                     expected_inode=None):
    data, identity = _read_regular_file(
        chain[-1].fd, relative.name, len(expected_data))
    _validate_chain(chain)
    if data != expected_data:
        raise SafeIOError("installed file does not contain expected bytes")
    if (expected_inode is not None and
            _inode_identity_from_file(identity) != expected_inode):
        raise SafeIOError("installed file identity changed")
    return FileSnapshot(
        root=root,
        relative=relative,
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
        file_identity=identity,
        directory_identities=_identities(chain),
    )


def _inode_identity_from_file(identity):
    return identity[:2]


def _journal_bytes(state):
    return (json.dumps(state, sort_keys=True, separators=(",", ":")) +
            "\n").encode("utf-8")


def _journal_name(relative):
    digest = hashlib.sha256(relative.as_posix().encode("utf-8")).hexdigest()
    return f".safeio-publish-{digest}.json"


def _expected_journal(snapshot, data):
    return {
        "version": 1,
        "relative": snapshot.relative.as_posix(),
        "data_sha256": hashlib.sha256(data).hexdigest(),
        "parent_identities": [list(value)
                              for value in snapshot.parent_identities],
        "nonce": snapshot.transaction_nonce,
    }


def _staging_name(nonce, directory_index, attempt_index):
    return (f".safeio-dir-{nonce}-{directory_index}-"
            f"{attempt_index}")


def _new_staging_attempt(nonce, directory_index, attempt_index):
    return {
        "staging": _staging_name(nonce, directory_index, attempt_index),
        "identity": None,
        "status": "planned",
    }


def _validate_transaction_nonce(nonce):
    if (not isinstance(nonce, str) or len(nonce) != 32 or
            any(character not in "0123456789abcdef" for character in nonce)):
        raise SafeIOError("publication recovery nonce is invalid")


def _validate_journal(state, expected, snapshot):
    if not isinstance(state, dict):
        raise SafeIOError("publication recovery record is not an object")
    if set(state) != set(expected) | {"directories"}:
        raise SafeIOError("publication recovery record has invalid fields")
    nonce = state.get("nonce")
    directories = state.get("directories")
    _validate_transaction_nonce(nonce)
    for key, value in expected.items():
        if state.get(key) != value:
            raise SafeIOError("publication recovery record conflicts")
    if not isinstance(directories, list):
        raise SafeIOError("publication recovery directories are invalid")
    relative_count = _relative_parent_count(snapshot)
    tail = snapshot.relative.parts[relative_count:-1]
    if len(directories) > len(tail):
        raise SafeIOError("publication recovery has too many directories")
    for directory_index, entry in enumerate(directories):
        if not isinstance(entry, dict):
            raise SafeIOError("publication recovery directory is invalid")
        if set(entry) != {"component", "attempts"}:
            raise SafeIOError("publication recovery directory has invalid fields")
        if entry["component"] != tail[directory_index]:
            raise SafeIOError("publication recovery component is invalid")
        attempts = entry["attempts"]
        if not isinstance(attempts, list) or not attempts:
            raise SafeIOError("publication recovery attempts are invalid")
        for attempt_index, attempt in enumerate(attempts):
            if not isinstance(attempt, dict):
                raise SafeIOError("publication recovery attempt is invalid")
            if set(attempt) != {"staging", "identity", "status"}:
                raise SafeIOError(
                    "publication recovery attempt has invalid fields")
            expected_staging = _staging_name(
                nonce, directory_index, attempt_index)
            if attempt["staging"] != expected_staging:
                raise SafeIOError(
                    "publication recovery staging name is invalid")
            status = attempt["status"]
            if status not in ("planned", "abandoned", "bound", "installed"):
                raise SafeIOError("publication recovery status is invalid")
            identity = attempt["identity"]
            if status == "planned":
                if identity is not None:
                    raise SafeIOError(
                        "planned directory already has an identity")
            elif (not isinstance(identity, list) or len(identity) != 2 or
                  not all(isinstance(value, int) and not isinstance(value, bool)
                          for value in identity)):
                raise SafeIOError("publication recovery identity is invalid")
            if attempt_index < len(attempts) - 1 and status != "abandoned":
                raise SafeIOError(
                    "publication recovery attempt history is invalid")
        current_status = attempts[-1]["status"]
        if current_status == "abandoned":
            raise SafeIOError(
                "publication recovery has no current staging attempt")
        if (directory_index < len(directories) - 1 and
                current_status != "installed"):
            raise SafeIOError(
                "publication recovery directory order is invalid")


def _load_or_create_journal(directory_fd, snapshot, data, first_component):
    name = _journal_name(snapshot.relative)
    expected = _expected_journal(snapshot, data)
    try:
        payload, identity = _read_regular_file(directory_fd, name, 65_536)
    except SafeIOError as exc:
        if not isinstance(exc.__cause__, FileNotFoundError):
            raise
        _require_absent(directory_fd, first_component)
        state = {
            **expected,
            "directories": [],
        }
        inode = _publish_bound(directory_fd, name, _journal_bytes(state))
        return name, state, inode
    try:
        state = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SafeIOError("publication recovery record is invalid") from exc
    _validate_journal(state, expected, snapshot)
    return name, state, _inode_identity_from_file(identity)


def _update_journal(directory_fd, name, state):
    return _atomic_write(directory_fd, name, _journal_bytes(state))


def _directory_entry_identity(directory_fd, name):
    details = _named_details(directory_fd, name)
    if not stat.S_ISDIR(details.st_mode):
        raise SafeIOError(f"publication path is not a directory: {name}")
    return _directory_identity(details)


def _prepare_publication_parent(snapshot, data):
    chain = _open_expected_parent(snapshot)
    try:
        _lock_root(chain, snapshot.root)
        relative_count = _relative_parent_count(snapshot)
        tail = snapshot.relative.parts[relative_count:-1]
        if not tail:
            _require_absent(chain[-1].fd, snapshot.relative.name)
            return chain, None

        journal_fd = chain[-1].fd
        journal_name, state, journal_inode = _load_or_create_journal(
            journal_fd, snapshot, data, tail[0])
        if len(state["directories"]) > len(tail):
            raise SafeIOError("publication recovery has too many directories")

        for index, component in enumerate(tail):
            if index == len(state["directories"]):
                state["directories"].append({
                    "component": component,
                    "attempts": [
                        _new_staging_attempt(state["nonce"], index, 0),
                    ],
                })
                journal_inode = _update_journal(
                    journal_fd, journal_name, state)
            entry = state["directories"][index]
            if entry["component"] != component:
                raise SafeIOError("publication recovery component conflicts")

            attempts = entry["attempts"]
            for abandoned in attempts[:-1]:
                _require_named_inode(
                    chain[-1].fd, abandoned["staging"],
                    tuple(abandoned["identity"]), directory=True)
            current = attempts[-1]

            if current["status"] == "planned":
                staging = current["staging"]
                try:
                    os.mkdir(staging, 0o700, dir_fd=chain[-1].fd)
                    os.fsync(chain[-1].fd)
                except FileExistsError:
                    abandoned_identity = _directory_entry_identity(
                        chain[-1].fd, staging)
                    current["identity"] = list(abandoned_identity)
                    current["status"] = "abandoned"
                    current = _new_staging_attempt(
                        state["nonce"], index, len(attempts))
                    attempts.append(current)
                    journal_inode = _update_journal(
                        journal_fd, journal_name, state)
                    staging = current["staging"]
                    try:
                        os.mkdir(staging, 0o700, dir_fd=chain[-1].fd)
                        os.fsync(chain[-1].fd)
                    except OSError as exc:
                        raise SafeIOError(
                            "could not create a new publication staging "
                            f"directory: {component}") from exc
                except OSError as exc:
                    raise SafeIOError(
                        f"could not create publication directory: {component}") from exc
                _after_staging_mkdir(component, staging)
                created_identity = _directory_entry_identity(
                    chain[-1].fd, staging)
                current["identity"] = list(created_identity)
                current["status"] = "bound"
                journal_inode = _update_journal(
                    journal_fd, journal_name, state)

            expected_identity = tuple(current["identity"])
            staging = current["staging"]
            if current["status"] == "bound":
                try:
                    _require_named_inode(
                        chain[-1].fd, staging, expected_identity,
                        directory=True)
                    _require_absent(chain[-1].fd, component)
                    os.rename(staging, component,
                              src_dir_fd=chain[-1].fd,
                              dst_dir_fd=chain[-1].fd)
                    os.fsync(chain[-1].fd)
                except SafeIOError:
                    try:
                        _require_named_inode(
                            chain[-1].fd, component, expected_identity,
                            directory=True)
                    except SafeIOError:
                        raise
                current["status"] = "installed"
                journal_inode = _update_journal(
                    journal_fd, journal_name, state)

            _require_named_inode(
                chain[-1].fd, component, expected_identity, directory=True)
            _append_directory(chain, component)
            if chain[-1].identity != expected_identity:
                raise SafeIOError(
                    f"created directory was replaced: {component}")
            os.fsync(chain[-1].fd)
            _validate_chain(chain)
            _after_directory_install(component, expected_identity)
        return chain, (journal_fd, journal_name, journal_inode)
    except BaseException:
        _close_chain(chain)
        raise


def _refuse_recovery_conflict(snapshot, *, include_snapshot_parent):
    chain = _open_expected_parent(snapshot)
    try:
        recovery_name = _journal_name(snapshot.relative)
        root_index = len(snapshot.root.parts) - 1
        stop = len(chain) if include_snapshot_parent else len(chain) - 1
        for handle in chain[root_index:stop]:
            try:
                os.stat(recovery_name, dir_fd=handle.fd,
                        follow_symlinks=False)
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise SafeIOError(
                    "cannot inspect publication recovery state") from exc
            raise SafeIOError(
                "interrupted publication requires its original MissingSnapshot")
    finally:
        _close_chain(chain)


def _publication_request(root_or_snapshot, relative_or_data, data):
    if isinstance(root_or_snapshot, MissingSnapshot):
        if data is not None:
            raise SafeIOError(
                "MissingSnapshot publication accepts exactly snapshot and data")
        snapshot = root_or_snapshot
        payload = _publication_data(relative_or_data)
        _refuse_recovery_conflict(
            snapshot, include_snapshot_parent=False)
        return snapshot, payload
    payload = _publication_data(data)
    canonical = _resolve_root(root_or_snapshot)
    relative = _relative_path(relative_or_data)
    snapshot = _snapshot_from_chain(
        canonical, relative, len(payload), allow_missing=True)
    if not isinstance(snapshot, MissingSnapshot):
        raise SafeIOError(f"destination already exists: {relative}")
    _refuse_recovery_conflict(snapshot, include_snapshot_parent=True)
    return snapshot, payload


def publish_exclusive(root, relative, data=None) -> FileSnapshot:
    """Publish once, or resume a directory-tail creation by MissingSnapshot.

    Callers that may retry after interruption must retain and reuse the
    original ``MissingSnapshot``: ``publish_exclusive(missing, data)``.  A
    fresh absence observation cannot prove that partially created directories
    belong to the interrupted request.
    """
    snapshot, data = _publication_request(root, relative, data)
    chain, journal = _prepare_publication_parent(snapshot, data)
    try:
        leaf = snapshot.relative.name
        if journal is not None:
            try:
                existing_data, existing_identity = _read_regular_file(
                    chain[-1].fd, leaf, len(data))
            except SafeIOError as exc:
                if not isinstance(exc.__cause__, FileNotFoundError):
                    raise
            else:
                if existing_data != data:
                    raise SafeIOError("published destination conflicts")
                result = _snapshot_result(
                    chain, snapshot.root, snapshot.relative, data,
                    _inode_identity_from_file(existing_identity))
                journal_fd, journal_name, journal_inode = journal
                if not _unlink_if_identity(
                        journal_fd, journal_name, journal_inode):
                    raise SafeIOError(
                        "publication recovery record identity changed")
                os.fsync(journal_fd)
                return result

        def before_install():
            _before_publish()
            _validate_chain(chain)
            _require_absent(chain[-1].fd, leaf)

        installed_inode = _publish_bound(
            chain[-1].fd, leaf, data, before_install=before_install,
            after_install=lambda: _validate_chain(chain))
        result = _snapshot_result(
            chain, snapshot.root, snapshot.relative, data, installed_inode)
        if journal is not None:
            journal_fd, journal_name, journal_inode = journal
            if not _unlink_if_identity(
                    journal_fd, journal_name, journal_inode):
                raise SafeIOError("publication recovery record identity changed")
            os.fsync(journal_fd)
        return result
    finally:
        _close_chain(chain)


def replace_if_unchanged(snapshot, data) -> FileSnapshot:
    if not isinstance(snapshot, FileSnapshot):
        raise SafeIOError("replace_if_unchanged requires a file snapshot")
    data = _publication_data(data)
    chain = _open_expected_parent(snapshot)
    try:
        _lock_root(chain, snapshot.root)

        def assert_original():
            data_now, identity_now = _read_regular_file(
                chain[-1].fd, snapshot.relative.name, len(snapshot.data))
            _validate_chain(chain)
            if (identity_now != snapshot.file_identity or
                    data_now != snapshot.data or
                    hashlib.sha256(data_now).hexdigest() != snapshot.sha256):
                raise SafeIOError(
                    f"file no longer matches snapshot: {snapshot.relative}")

        def compare_before_replace():
            _before_replace()
            assert_original()

        def compare_at_install():
            _before_replace_install()
            assert_original()

        replacement_inode = _atomic_write(
            chain[-1].fd, snapshot.relative.name, data,
            before_replace=compare_before_replace,
            before_install=compare_at_install,
            after_install=lambda: _validate_chain(chain),
        )
        return _snapshot_result(
            chain, snapshot.root, snapshot.relative, data,
            replacement_inode)
    finally:
        _close_chain(chain)
