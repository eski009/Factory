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

# Publication recovery must never write bytes that its own recovery reads
# refuse.  Keep this single constant patchable so boundary behavior can be
# exercised without constructing filesystem-limit-sized paths in tests.
_PUBLICATION_JOURNAL_LIMIT = 65_536

# Persisted stat identity fields are represented within unsigned 64-bit width
# on the supported POSIX filesystems.  Publication preflight uses the full
# decimal width rather than the usually shorter values observed at runtime.
_MAX_STAT_IDENTITY_VALUE = (1 << 64) - 1


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


def _require_exact_regular_file(directory_fd, name, expected_data,
                                expected_identity, error, *, read_limit=None):
    if read_limit is None:
        read_limit = len(expected_data)
    try:
        data, identity = _read_regular_file(
            directory_fd, name, read_limit)
    except SafeIOError as exc:
        raise SafeIOError(error) from exc
    if data != expected_data or identity != expected_identity:
        raise SafeIOError(error)
    return identity


def _capture_exact_regular_file(
        directory_fd, name, expected_data, error, *, read_limit=None):
    if read_limit is None:
        read_limit = len(expected_data)
    try:
        data, identity = _read_regular_file(
            directory_fd, name, read_limit)
    except SafeIOError as exc:
        raise SafeIOError(error) from exc
    if data != expected_data:
        raise SafeIOError(error)
    return identity


def _capture_opened_exact_regular_file(
        directory_fd, name, fd, expected_data, error, *, read_limit=None):
    """Grant authority only when ``name`` is the exact opened file.

    Reading through the name proves its bytes, while ``fstat`` binds that
    observation to the descriptor returned by the exclusive create.  Neither
    proof is sufficient on its own: a same-byte replacement can satisfy the
    former, and a detached original descriptor can satisfy the latter.
    """
    identity = _capture_exact_regular_file(
        directory_fd, name, expected_data, error, read_limit=read_limit)
    try:
        opened = os.fstat(fd)
    except OSError as exc:
        raise SafeIOError(error) from exc
    if (not stat.S_ISREG(opened.st_mode) or
            _file_identity(opened) != identity):
        raise SafeIOError(error)
    return identity


def _unlink_if_exact_regular_file(directory_fd, name, expected_data,
                                  expected_identity):
    try:
        _require_exact_regular_file(
            directory_fd, name, expected_data, expected_identity,
            f"filesystem entry changed before cleanup: {name}")
    except SafeIOError:
        return False
    return _unlink_if_identity(directory_fd, name, expected_identity[:2])


def _atomic_write(directory_fd, name, data, before_replace=None,
                  before_install=None, after_install=None, read_limit=None):
    """Worker-compatible atomic replacement with exact temp authorization."""
    if read_limit is None:
        read_limit = len(data)
    temp_name = f".{name}.tmp-{uuid.uuid4().hex}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | FILE_NOFOLLOW
    fd = os.open(temp_name, flags, 0o600, dir_fd=directory_fd)
    opened_identity = None
    cleanup_identity = None
    authorized_identity = None
    try:
        initial = os.fstat(fd)
        if not stat.S_ISREG(initial.st_mode):
            raise SafeIOError("replacement temporary is not a regular file")
        opened_identity = _inode_identity(initial)
        _write_all(fd, data)
        cleanup_identity = _capture_opened_exact_regular_file(
            directory_fd, temp_name, fd, data,
            "replacement temporary changed while being written",
            read_limit=read_limit)
        os.fsync(fd)
        authorized_identity = _capture_opened_exact_regular_file(
            directory_fd, temp_name, fd, data,
            "replacement temporary changed during fsync",
            read_limit=read_limit)
        if authorized_identity != cleanup_identity:
            raise SafeIOError("replacement temporary changed during fsync")
        cleanup_identity = authorized_identity
        if before_replace is not None:
            before_replace()
        _require_named_inode(
            directory_fd, temp_name, opened_identity, regular=True)
        if before_install is not None:
            before_install()
        if (_capture_opened_exact_regular_file(
                directory_fd, temp_name, fd, data,
                "replacement temporary changed before install",
                read_limit=read_limit) != authorized_identity):
            raise SafeIOError(
                "replacement temporary changed before install")
        os.replace(temp_name, name, src_dir_fd=directory_fd,
                   dst_dir_fd=directory_fd)
        if after_install is not None:
            after_install()
        try:
            installed_identity = _capture_opened_exact_regular_file(
                directory_fd, name, fd, data,
                "installed replacement temporary changed",
                read_limit=read_limit)
            if _inode_identity_from_file(installed_identity) != opened_identity:
                raise SafeIOError("installed replacement identity changed")
        except BaseException:
            try:
                cleanup_installed_identity = _capture_exact_regular_file(
                    directory_fd, name, data,
                    "installed replacement temporary changed",
                    read_limit=read_limit)
            except SafeIOError:
                cleanup_installed_identity = None
            if (cleanup_installed_identity is not None and
                    _inode_identity_from_file(cleanup_installed_identity) ==
                    opened_identity and
                    _unlink_if_exact_regular_file(
                        directory_fd, name, data,
                        cleanup_installed_identity)):
                os.fsync(directory_fd)
            raise
        os.fsync(directory_fd)
        return opened_identity
    finally:
        os.close(fd)
        if cleanup_identity is not None:
            _unlink_if_exact_regular_file(
                directory_fd, temp_name, data, cleanup_identity)


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
    opened_identity = None
    cleanup_identity = None
    published_identity = None
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode):
            raise SafeIOError("publication temporary is not a regular file")
        opened_identity = _inode_identity(details)
        _write_all(fd, data)
        cleanup_identity = _capture_opened_exact_regular_file(
            directory_fd, temp_name, fd, data,
            "publication temporary changed while being written")
        os.fsync(fd)
        authorized_identity = _capture_opened_exact_regular_file(
            directory_fd, temp_name, fd, data,
            "publication temporary changed during fsync")
        if authorized_identity != cleanup_identity:
            raise SafeIOError("publication temporary changed during fsync")
        cleanup_identity = authorized_identity
        if before_install is not None:
            before_install()
        if (_capture_opened_exact_regular_file(
                directory_fd, temp_name, fd, data,
                "publication temporary changed before install") !=
                authorized_identity):
            raise SafeIOError("publication temporary changed before install")
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
        published_identity = _capture_opened_exact_regular_file(
            directory_fd, temp_name, fd, data,
            "publication temporary changed during install")
        destination_identity = _capture_exact_regular_file(
            directory_fd, name, data,
            "published destination changed during install")
        if (destination_identity != published_identity or
                _inode_identity_from_file(published_identity) !=
                opened_identity):
            raise SafeIOError("publication temporary changed during install")
        _require_ctime_only_identity_transition(
            authorized_identity, published_identity,
            "publication temporary changed during install")
        cleanup_identity = published_identity
        if after_install is not None:
            after_install()
        try:
            _require_exact_regular_file(
                directory_fd, temp_name, data, published_identity,
                "publication temporary changed after install")
            _require_exact_regular_file(
                directory_fd, name, data, published_identity,
                "published destination changed after install")
        except BaseException:
            if _unlink_if_exact_regular_file(
                    directory_fd, name, data, published_identity):
                os.fsync(directory_fd)
            raise
        if not _unlink_if_exact_regular_file(
                directory_fd, temp_name, data, published_identity):
            if _unlink_if_exact_regular_file(
                    directory_fd, name, data, published_identity):
                os.fsync(directory_fd)
            raise SafeIOError("publication temporary identity changed")
        os.fsync(directory_fd)
        return opened_identity
    finally:
        os.close(fd)
        if cleanup_identity is not None:
            _unlink_if_exact_regular_file(
                directory_fd, temp_name, data, cleanup_identity)
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


def _after_leaf_staging_write(staging, identity):
    """Test seam after staging data fsync, before publication binding."""


def _after_leaf_bind(staging, identity):
    """Test seam after the staging inode is durably journal-bound."""


def _after_leaf_link(staging, identity):
    """Test seam after destination link, before its directory fsync."""


def _after_leaf_unlink(staging, identity):
    """Test seam after staging unlink, before its directory fsync."""


def _after_leaf_install(staging, identity):
    """Test seam after the installed state is durably journaled."""


def _before_leaf_attempt_compaction():
    """Test seam after durable absence proof, before compact journal write."""


def _after_leaf_attempt_compaction():
    """Test seam after compact journal publication."""


def _after_leaf_attempt_compaction_install():
    """Test seam after compact journal install, before directory fsync."""


def _before_publication_journal_install():
    """Test seam before final journal authority and chain revalidation."""


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


def _leaf_staging_name(nonce, attempt_index):
    return f".safeio-leaf-{nonce}-{attempt_index}.tmp"


def _new_leaf_attempt(nonce, attempt_index):
    return {
        "staging": _leaf_staging_name(nonce, attempt_index),
        "identity": None,
        "status": "planned",
    }


def _require_publication_journal_size(size):
    if (isinstance(_PUBLICATION_JOURNAL_LIMIT, bool) or
            not isinstance(_PUBLICATION_JOURNAL_LIMIT, int) or
            _PUBLICATION_JOURNAL_LIMIT < 0):
        raise SafeIOError("publication journal limit is invalid")
    if size > _PUBLICATION_JOURNAL_LIMIT:
        raise SafeIOError("publication journal exceeds its read limit")


def _require_publication_journal_bytes(payload):
    _require_publication_journal_size(len(payload))
    return payload


def _checked_journal_bytes(state):
    return _require_publication_journal_bytes(_journal_bytes(state))


def _journal_size(state):
    return len(_journal_bytes(state))


def _publication_journal_upper_bound(snapshot, data):
    """Return a conservative byte bound for normal journal transitions.

    This is deliberately filesystem-free.  Every future directory and leaf
    identity is encoded at the maximum supported stat integer width, and each
    structural transition is measured with the canonical journal encoder.
    Interference can add abandoned attempts, but those observations occur
    before effects and every resulting write is independently capped.
    """
    if not isinstance(snapshot, MissingSnapshot):
        raise SafeIOError("publication preflight requires a MissingSnapshot")
    data = _publication_data(data)
    _validate_transaction_nonce(snapshot.transaction_nonce)
    relative_count = _relative_parent_count(snapshot)
    tail = snapshot.relative.parts[relative_count:-1]
    maximum_directory_identity = [
        _MAX_STAT_IDENTITY_VALUE, _MAX_STAT_IDENTITY_VALUE]
    maximum_file_identity = [
        _MAX_STAT_IDENTITY_VALUE, _MAX_STAT_IDENTITY_VALUE,
        _MAX_STAT_IDENTITY_VALUE, _MAX_STAT_IDENTITY_VALUE,
        _MAX_STAT_IDENTITY_VALUE]
    state = {
        **_expected_journal(snapshot, data),
        "directories": [],
        "leaf": {"attempts": [
            _new_leaf_attempt(snapshot.transaction_nonce, 0)]},
    }
    sizes = [_journal_size(state)]

    for directory_index, component in enumerate(tail):
        entry = {
            "component": component,
            "attempts": [_new_staging_attempt(
                snapshot.transaction_nonce, directory_index, 0)],
        }
        state["directories"].append(entry)
        sizes.append(_journal_size(state))

        entry["attempts"] = [{
            **_new_staging_attempt(
                snapshot.transaction_nonce, directory_index, 0),
            "identity": maximum_directory_identity,
            "status": "abandoned",
        }, _new_staging_attempt(
            snapshot.transaction_nonce, directory_index, 1)]
        sizes.append(_journal_size(state))

        entry["attempts"][1]["identity"] = maximum_directory_identity
        entry["attempts"][1]["status"] = "bound"
        sizes.append(_journal_size(state))
        entry["attempts"][1]["status"] = "installed"
        sizes.append(_journal_size(state))

    state["leaf"]["attempts"] = [{
        **_new_leaf_attempt(snapshot.transaction_nonce, 0),
        "identity": maximum_file_identity,
        "status": "abandoned",
    }, _new_leaf_attempt(snapshot.transaction_nonce, 1)]
    sizes.append(_journal_size(state))
    for status in ("preparing", "bound", "installed"):
        state["leaf"]["attempts"][1]["identity"] = maximum_file_identity
        state["leaf"]["attempts"][1]["status"] = status
        sizes.append(_journal_size(state))
    return max(sizes)


def preflight_publication(snapshot, data):
    """Prove predictable journal states fit before publication effects."""
    required = _publication_journal_upper_bound(snapshot, data)
    _require_publication_journal_size(required)
    return required


def _validate_transaction_nonce(nonce):
    if (not isinstance(nonce, str) or len(nonce) != 32 or
            any(character not in "0123456789abcdef" for character in nonce)):
        raise SafeIOError("publication recovery nonce is invalid")


def _validate_journal(state, expected, snapshot):
    if not isinstance(state, dict):
        raise SafeIOError("publication recovery record is not an object")
    if set(state) != set(expected) | {"directories", "leaf"}:
        raise SafeIOError("publication recovery record has invalid fields")
    nonce = state.get("nonce")
    directories = state.get("directories")
    _validate_transaction_nonce(nonce)
    for key, value in expected.items():
        if state.get(key) != value:
            raise SafeIOError("publication recovery record conflicts")
    if not isinstance(directories, list):
        raise SafeIOError("publication recovery directories are invalid")
    leaf = state.get("leaf")
    if not isinstance(leaf, dict) or set(leaf) != {"attempts"}:
        raise SafeIOError("publication recovery leaf is invalid")
    leaf_attempts = leaf.get("attempts")
    if not isinstance(leaf_attempts, list) or not leaf_attempts:
        raise SafeIOError("publication recovery leaf attempts are invalid")
    for attempt_index, attempt in enumerate(leaf_attempts):
        if not isinstance(attempt, dict):
            raise SafeIOError("publication recovery leaf attempt is invalid")
        if set(attempt) != {"staging", "identity", "status"}:
            raise SafeIOError(
                "publication recovery leaf attempt has invalid fields")
        if attempt["staging"] != _leaf_staging_name(nonce, attempt_index):
            raise SafeIOError(
                "publication recovery leaf staging name is invalid")
        status = attempt["status"]
        if status not in (
                "planned", "preparing", "abandoned", "bound", "installed"):
            raise SafeIOError("publication recovery leaf status is invalid")
        identity = attempt["identity"]
        if status == "planned":
            if identity is not None:
                raise SafeIOError(
                    "planned publication leaf already has an identity")
        elif (not isinstance(identity, list) or len(identity) != 5 or
              not all(isinstance(value, int) and not isinstance(value, bool)
                      for value in identity)):
            raise SafeIOError(
                "publication recovery leaf identity is invalid")
        if attempt_index < len(leaf_attempts) - 1 and status != "abandoned":
            raise SafeIOError(
                "publication recovery leaf attempt history is invalid")
    if leaf_attempts[-1]["status"] == "abandoned":
        raise SafeIOError(
            "publication recovery leaf has no current staging attempt")
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


def _adopt_existing_journal(chain, name, payload, identity):
    """Make a visible journal durable before trusting it for recovery."""
    directory_fd = chain[-1].fd
    try:
        fd = os.open(name, _FILE_READ_FLAGS, dir_fd=directory_fd)
    except OSError as exc:
        raise SafeIOError(
            "publication recovery journal changed during adoption") from exc
    try:
        try:
            opened = os.fstat(fd)
            named = os.stat(
                name, dir_fd=directory_fd, follow_symlinks=False)
            if (not stat.S_ISREG(opened.st_mode) or
                    not stat.S_ISREG(named.st_mode) or
                    _file_identity(opened) != identity or
                    _file_identity(named) != identity):
                raise SafeIOError(
                    "publication recovery journal changed during adoption")
            os.fsync(fd)
            synced = os.fstat(fd)
            synced_named = os.stat(
                name, dir_fd=directory_fd, follow_symlinks=False)
            if (_file_identity(synced) != identity or
                    _file_identity(synced_named) != identity):
                raise SafeIOError(
                    "publication recovery journal changed during adoption")
            os.fsync(directory_fd)
        except SafeIOError:
            raise
        except OSError as exc:
            raise SafeIOError(
                "publication recovery journal could not be made durable") from exc
    finally:
        os.close(fd)

    confirmed_payload, confirmed_identity = _read_regular_file(
        directory_fd, name, _PUBLICATION_JOURNAL_LIMIT)
    if confirmed_identity != identity or confirmed_payload != payload:
        raise SafeIOError(
            "publication recovery journal changed during adoption")
    _validate_chain(chain)
    return confirmed_payload, confirmed_identity


def _load_or_create_journal(chain, snapshot, data, first_component):
    directory_fd = chain[-1].fd
    name = _journal_name(snapshot.relative)
    expected = _expected_journal(snapshot, data)
    try:
        payload, identity = _read_regular_file(
            directory_fd, name, _PUBLICATION_JOURNAL_LIMIT)
    except SafeIOError as exc:
        if not isinstance(exc.__cause__, FileNotFoundError):
            raise
        _require_absent(directory_fd, first_component)
        state = {
            **expected,
            "directories": [],
            "leaf": {"attempts": [_new_leaf_attempt(
                snapshot.transaction_nonce, 0)]},
        }
        journal_bytes = _checked_journal_bytes(state)
        inode = _publish_bound(directory_fd, name, journal_bytes)
        return name, state, inode, journal_bytes
    payload, identity = _adopt_existing_journal(
        chain, name, payload, identity)
    try:
        state = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SafeIOError("publication recovery record is invalid") from exc
    _validate_journal(state, expected, snapshot)
    return name, state, _inode_identity_from_file(identity), payload


def _require_publication_journal_current(
        directory_fd, name, expected_bytes, expected_inode, chain):
    try:
        payload, identity = _read_regular_file(
            directory_fd, name, _PUBLICATION_JOURNAL_LIMIT)
    except SafeIOError as exc:
        raise SafeIOError(
            "publication recovery journal changed") from exc
    if (payload != expected_bytes or
            _inode_identity_from_file(identity) != expected_inode):
        raise SafeIOError("publication recovery journal changed")
    _validate_chain(chain)


def _update_journal(
        directory_fd, name, state, *, expected_bytes=None,
        expected_inode=None, chain=None, after_install=None):
    payload = _checked_journal_bytes(state)
    if expected_bytes is None or expected_inode is None or chain is None:
        raise SafeIOError(
            "publication recovery journal update lacks authority")

    def revalidate_authority():
        _before_publication_journal_install()
        _require_publication_journal_current(
            directory_fd, name, expected_bytes, expected_inode, chain)

    return _atomic_write(
        directory_fd, name, payload,
        before_install=revalidate_authority,
        after_install=after_install,
        read_limit=_PUBLICATION_JOURNAL_LIMIT)


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
            journal_fd = chain[-1].fd
            loaded = _load_or_create_journal(
                chain, snapshot, data, snapshot.relative.name)
            journal_name, state, journal_inode, journal_bytes = loaded
            return chain, [journal_fd, journal_name, journal_inode, state,
                           journal_bytes, chain]

        journal_fd = chain[-1].fd
        loaded = _load_or_create_journal(chain, snapshot, data, tail[0])
        journal_name, state, journal_inode, journal_bytes = loaded
        journal = [journal_fd, journal_name, journal_inode, state,
                   journal_bytes, chain]
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
                journal = _refresh_publication_journal(journal)
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
                _require_attempt_transition_fits(
                    state, current, "bound",
                    (_MAX_STAT_IDENTITY_VALUE,
                     _MAX_STAT_IDENTITY_VALUE))
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
                    journal = _refresh_publication_journal(journal)
                    staging = current["staging"]
                    _require_attempt_transition_fits(
                        state, current, "bound",
                        (_MAX_STAT_IDENTITY_VALUE,
                         _MAX_STAT_IDENTITY_VALUE))
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
                journal = _refresh_publication_journal(journal)

            expected_identity = tuple(current["identity"])
            staging = current["staging"]
            if current["status"] == "bound":
                _require_attempt_transition_fits(
                    state, current, "installed", expected_identity)
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
                journal = _refresh_publication_journal(journal)

            _require_named_inode(
                chain[-1].fd, component, expected_identity, directory=True)
            _append_directory(chain, component)
            if chain[-1].identity != expected_identity:
                raise SafeIOError(
                    f"created directory was replaced: {component}")
            os.fsync(chain[-1].fd)
            _validate_chain(chain)
            _after_directory_install(component, expected_identity)
        return chain, journal
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


def _validate_publication_leaf(state, result):
    attempt = state["leaf"]["attempts"][-1]
    if (attempt["status"] != "installed" or
            tuple(attempt["identity"]) != result.file_identity):
        raise SafeIOError("published destination identity conflicts")


def _refresh_publication_journal(journal, *, after_install=None):
    (journal_fd, journal_name, journal_inode, state,
     expected_bytes, chain) = journal
    payload = _checked_journal_bytes(state)
    new_inode = _update_journal(
        journal_fd, journal_name, state,
        expected_bytes=expected_bytes,
        expected_inode=journal_inode,
        chain=chain,
        after_install=after_install)
    journal[2] = new_inode
    journal[4] = payload
    return journal


def _revalidate_publication_journal(journal):
    (journal_fd, journal_name, journal_inode, _state,
     expected_bytes, chain) = journal
    _require_publication_journal_current(
        journal_fd, journal_name, expected_bytes, journal_inode, chain)


def _optional_regular_identity(directory_fd, name):
    try:
        details = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SafeIOError(
            f"cannot inspect publication staging file: {name}") from exc
    if not stat.S_ISREG(details.st_mode):
        raise SafeIOError(
            f"publication staging entry is not a regular file: {name}")
    return _file_identity(details)


def _create_leaf_staging(directory_fd, staging, data, prepare):
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | FILE_NOFOLLOW |
             getattr(os, "O_NONBLOCK", 0))
    try:
        fd = os.open(staging, flags, 0o600, dir_fd=directory_fd)
    except FileExistsError:
        return None
    except OSError as exc:
        raise SafeIOError(
            "could not create publication staging file") from exc
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode):
            raise SafeIOError(
                "publication staging entry is not a regular file")
        _write_all(fd, data)
        identity = _capture_opened_exact_regular_file(
            directory_fd, staging, fd, data,
            "publication staging changed while being written")
        prepare(identity)
        if (_capture_opened_exact_regular_file(
                directory_fd, staging, fd, data,
                "publication staging changed before fsync") != identity):
            raise SafeIOError(
                "publication staging identity changed before fsync")
        os.fsync(fd)
        if (_capture_opened_exact_regular_file(
                directory_fd, staging, fd, data,
                "publication staging changed during fsync") != identity):
            raise SafeIOError(
                "publication staging identity changed during fsync")
        _after_leaf_staging_write(staging, identity)
        _require_exact_regular_file(
            directory_fd, staging, data, identity,
            "publication staging changed before journal binding")
        # The staging name must survive power loss before a durable journal
        # is allowed to claim that its inode is bound.  This is distinct from
        # fsyncing the file contents above, especially inside a newly-created
        # missing tail.
        os.fsync(directory_fd)
        return identity
    finally:
        os.close(fd)


def _resume_preparing_leaf_staging(directory_fd, staging, data, identity):
    try:
        fd = os.open(staging, _FILE_READ_FLAGS, dir_fd=directory_fd)
    except OSError as exc:
        raise SafeIOError("publication staging identity conflicts") from exc
    try:
        if (_capture_opened_exact_regular_file(
                directory_fd, staging, fd, data,
                "publication staging identity conflicts") != identity):
            raise SafeIOError("publication staging identity conflicts")
        os.fsync(fd)
        if (_capture_opened_exact_regular_file(
                directory_fd, staging, fd, data,
                "publication staging identity conflicts") != identity):
            raise SafeIOError("publication staging identity conflicts")
        os.fsync(directory_fd)
    finally:
        os.close(fd)


def _require_attempt_transition_fits(state, attempt, status, identity):
    previous_status = attempt["status"]
    previous_identity = attempt["identity"]
    try:
        attempt["status"] = status
        attempt["identity"] = list(identity) if identity is not None else None
        _checked_journal_bytes(state)
    finally:
        attempt["status"] = previous_status
        attempt["identity"] = previous_identity


def _cleanup_abandoned_leaf_staging(directory_fd, state):
    for attempt in state["leaf"]["attempts"][:-1]:
        if attempt["status"] != "abandoned":
            continue
        observed = _optional_regular_identity(
            directory_fd, attempt["staging"])
        if observed is None:
            continue
        expected = tuple(attempt["identity"])
        if observed != expected:
            raise SafeIOError("publication staging identity conflicts")
        # An abandoned record may describe an unbound planned-name collision.
        # Its bytes and matching inode are not publication authority, so
        # recovery observes it but never deletes it.


def _compact_leaf_attempts(chain, journal):
    directory_fd = chain[-1].fd
    state = journal[3]
    _cleanup_abandoned_leaf_staging(directory_fd, state)
    attempts = state["leaf"]["attempts"]
    if len(attempts) == 1:
        return journal
    current = attempts[-1]
    if current["status"] != "planned" or current["identity"] is not None:
        return journal

    for historical in attempts[:-1]:
        observed = _optional_regular_identity(
            directory_fd, historical["staging"])
        if observed is not None:
            if observed != tuple(historical["identity"]):
                raise SafeIOError("publication staging identity conflicts")
            return journal
    if _optional_regular_identity(
            directory_fd, current["staging"]) is not None:
        return journal

    compacted = _new_leaf_attempt(state["nonce"], 0)
    # The parent fsync makes every absence proof above durable, including the
    # staging name that will be reused by the compacted journal.
    os.fsync(directory_fd)
    _before_leaf_attempt_compaction()
    previous = list(attempts)
    attempts[:] = [compacted]
    try:
        journal = _refresh_publication_journal(
            journal,
            after_install=_after_leaf_attempt_compaction_install)
    except BaseException:
        attempts[:] = previous
        raise
    _after_leaf_attempt_compaction()
    return journal


def _unlink_recorded_leaf_staging(
        directory_fd, staging, data, expected_identity):
    observed_identity = _optional_regular_identity(directory_fd, staging)
    if observed_identity is None:
        return False
    if observed_identity != expected_identity:
        raise SafeIOError("publication staging identity conflicts")
    if not _unlink_if_exact_regular_file(
            directory_fd, staging, data, expected_identity):
        raise SafeIOError("publication staging identity conflicts")
    return True


def _bind_publication_leaf(chain, journal, data):
    directory_fd = chain[-1].fd
    state = journal[3]
    journal = _compact_leaf_attempts(chain, journal)
    while True:
        attempts = state["leaf"]["attempts"]
        current = attempts[-1]
        if current["status"] == "preparing":
            prepared_identity = tuple(current["identity"])
            observed_identity = _optional_regular_identity(
                directory_fd, current["staging"])
            if observed_identity != prepared_identity:
                raise SafeIOError("publication staging identity conflicts")
            _resume_preparing_leaf_staging(
                directory_fd, current["staging"], data,
                prepared_identity)
            current["status"] = "bound"
            journal = _refresh_publication_journal(journal)
            _after_leaf_bind(current["staging"], prepared_identity)
            _cleanup_abandoned_leaf_staging(directory_fd, state)
            return journal, current
        if current["status"] != "planned":
            return journal, current
        staging = current["staging"]
        existing_identity = _optional_regular_identity(directory_fd, staging)
        if existing_identity is not None:
            # Its inode was never durably bound, so bytes and a predictable
            # name are insufficient authority to adopt it.
            current["identity"] = list(existing_identity)
            current["status"] = "abandoned"
            current = _new_leaf_attempt(state["nonce"], len(attempts))
            attempts.append(current)
            try:
                journal = _refresh_publication_journal(journal)
            except BaseException:
                attempts.pop()
                attempts[-1]["identity"] = None
                attempts[-1]["status"] = "planned"
                raise
            continue
        _require_attempt_transition_fits(
            state, current, "preparing",
            (_MAX_STAT_IDENTITY_VALUE, _MAX_STAT_IDENTITY_VALUE,
             _MAX_STAT_IDENTITY_VALUE, _MAX_STAT_IDENTITY_VALUE,
             _MAX_STAT_IDENTITY_VALUE))

        def prepare(created_identity):
            nonlocal journal
            current["identity"] = list(created_identity)
            current["status"] = "preparing"
            try:
                journal = _refresh_publication_journal(journal)
            except BaseException:
                current["identity"] = None
                current["status"] = "planned"
                raise

        created_identity = _create_leaf_staging(
            directory_fd, staging, data, prepare)
        if created_identity is None:
            continue
        if (current["status"] != "preparing" or
                tuple(current["identity"]) != created_identity):
            raise SafeIOError("publication staging identity conflicts")
        current["status"] = "bound"
        journal = _refresh_publication_journal(journal)
        _after_leaf_bind(staging, created_identity)
        _cleanup_abandoned_leaf_staging(directory_fd, state)
        return journal, current


def _destination_leaf_state(directory_fd, name, expected_identity):
    try:
        details = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return "missing"
    except OSError as exc:
        raise SafeIOError(
            f"cannot inspect publication destination: {name}") from exc
    if (not stat.S_ISREG(details.st_mode) or
            _inode_identity(details) !=
            _inode_identity_from_file(expected_identity)):
        return "substituted"
    return "exact"


def _require_ctime_only_identity_transition(previous, current, error):
    """Allow only the metadata transition caused at a link/unlink boundary.

    Callers use this immediately after the namespace operation, or while
    recovering a namespace shape that proves the operation happened.  Every
    subsequent interval requires all five identity fields to remain exact.
    """
    if previous[:4] != current[:4]:
        raise SafeIOError(error)


def _reset_effectless_prelink_leaf(chain, journal, leaf, current, data):
    if journal[3]["directories"]:
        # Created directory identities still depend on this journal, so their
        # bound leaf must remain intact for retry.
        return
    try:
        _require_absent(chain[-1].fd, leaf)
        attempts = journal[3]["leaf"]["attempts"]
        if current is not attempts[-1] or current["status"] != "bound":
            raise SafeIOError("publication recovery leaf state changed")
        _require_exact_regular_file(
            chain[-1].fd, current["staging"], data,
            tuple(current["identity"]),
            "publication staging changed before cleanup")

        # Make deletion recoverable first.  If cleanup stops after this
        # durable journal update, retry can remove the abandoned exact inode
        # (if it survived) and create the new planned staging attempt.
        current["status"] = "abandoned"
        attempts.append(_new_leaf_attempt(
            journal[3]["nonce"], len(attempts)))
        journal = _refresh_publication_journal(journal)

        if _unlink_recorded_leaf_staging(
                chain[-1].fd, current["staging"], data,
                tuple(current["identity"])):
            os.fsync(chain[-1].fd)
        _remove_publication_journal(journal)
    except BaseException:
        # This is best-effort cleanup while another exception is active.  The
        # durable state is recoverable whether it is still bound or has moved
        # to abandoned-plus-planned, so preserve the original refusal.
        pass


def _publish_journaled_leaf(chain, journal, snapshot, data):
    journal, current = _bind_publication_leaf(chain, journal, data)
    _revalidate_publication_journal(journal)
    directory_fd = chain[-1].fd
    leaf = snapshot.relative.name
    staging = current["staging"]
    expected_identity = tuple(current["identity"])

    destination_state = _destination_leaf_state(
        directory_fd, leaf, expected_identity)
    if destination_state == "substituted":
        raise SafeIOError("published destination identity conflicts")
    if current["status"] == "installed":
        if destination_state != "exact":
            raise SafeIOError("installed publication destination is missing")
        _require_exact_regular_file(
            directory_fd, leaf, data, expected_identity,
            "installed publication destination changed")
    elif current["status"] == "bound":
        _require_attempt_transition_fits(
            journal[3], current, "installed", expected_identity)
        staging_identity = _optional_regular_identity(directory_fd, staging)
        if destination_state == "missing":
            if staging_identity != expected_identity:
                raise SafeIOError(
                    "bound publication staging file is missing")
            try:
                _before_publish()
                _revalidate_publication_journal(journal)
                _require_exact_regular_file(
                    directory_fd, staging, data, expected_identity,
                    "publication staging changed before install")
                _require_absent(directory_fd, leaf)
                try:
                    os.link(staging, leaf,
                            src_dir_fd=directory_fd,
                            dst_dir_fd=directory_fd,
                            follow_symlinks=False)
                except FileExistsError as exc:
                    raise SafeIOError(
                        f"destination already exists: {leaf}") from exc
                except OSError as exc:
                    raise SafeIOError(
                        f"could not publish destination: {leaf}") from exc
            except BaseException:
                _reset_effectless_prelink_leaf(
                    chain, journal, leaf, current, data)
                raise
            linked_identity = _capture_exact_regular_file(
                directory_fd, leaf, data,
                "published destination changed during install")
            _require_ctime_only_identity_transition(
                expected_identity, linked_identity,
                "published destination identity conflicts")
            _require_exact_regular_file(
                directory_fd, staging, data, linked_identity,
                "publication staging changed during install")
            _after_leaf_link(staging, linked_identity)
            _require_exact_regular_file(
                directory_fd, leaf, data, linked_identity,
                "published destination identity conflicts")
            _require_exact_regular_file(
                directory_fd, staging, data, linked_identity,
                "publication staging identity conflicts")
            if _destination_leaf_state(
                    directory_fd, leaf, expected_identity) != "exact":
                raise SafeIOError(
                    "published destination identity conflicts")
            _revalidate_publication_journal(journal)
            destination_identity = linked_identity
        else:
            destination_identity = _capture_exact_regular_file(
                directory_fd, leaf, data,
                "published destination changed before adoption")
            if staging_identity is not None:
                _require_exact_regular_file(
                    directory_fd, staging, data, destination_identity,
                    "publication staging identity conflicts")
            # A bound journal plus the destination namespace proves that a
            # previous call crossed the hard-link boundary.  A missing staging
            # name additionally proves it crossed the unlink boundary.  This
            # is the only recovery interval in which ctime may continue.
            _require_ctime_only_identity_transition(
                expected_identity, destination_identity,
                "published destination identity conflicts")
        if _destination_leaf_state(
                directory_fd, leaf, expected_identity) != "exact":
            raise SafeIOError("published destination identity conflicts")
        _require_exact_regular_file(
            directory_fd, leaf, data, destination_identity,
            "published destination identity conflicts")
        staging_identity = _optional_regular_identity(directory_fd, staging)
        if staging_identity is not None:
            _require_exact_regular_file(
                directory_fd, staging, data, destination_identity,
                "publication staging identity conflicts")
        # Whether this call created the link or is adopting one left by an
        # interrupted call, its exact containing directory must be durable
        # before removing the only other name for the bound inode.
        os.fsync(directory_fd)
        _revalidate_publication_journal(journal)
        _require_exact_regular_file(
            directory_fd, leaf, data, destination_identity,
            "published destination identity conflicts")
        staging_identity = _optional_regular_identity(directory_fd, staging)
        if staging_identity is not None:
            _require_exact_regular_file(
                directory_fd, staging, data, destination_identity,
                "publication staging identity conflicts")
            if not _unlink_if_exact_regular_file(
                    directory_fd, staging, data, destination_identity):
                raise SafeIOError("publication staging identity changed")
            unlinked_identity = _capture_exact_regular_file(
                directory_fd, leaf, data,
                "published destination changed during staging unlink")
            _require_ctime_only_identity_transition(
                destination_identity, unlinked_identity,
                "published destination identity conflicts")
            _after_leaf_unlink(staging, unlinked_identity)
            _require_exact_regular_file(
                directory_fd, leaf, data, unlinked_identity,
                "published destination identity conflicts")
            os.fsync(directory_fd)
            _require_exact_regular_file(
                directory_fd, leaf, data, unlinked_identity,
                "published destination identity conflicts")
            destination_identity = unlinked_identity
        if _destination_leaf_state(
                directory_fd, leaf, expected_identity) != "exact":
            raise SafeIOError("published destination identity conflicts")
        installed_identity = _capture_exact_regular_file(
            directory_fd, leaf, data,
            "published destination changed before journal install")
        if installed_identity != destination_identity:
            raise SafeIOError("published destination identity conflicts")
        _validate_chain(chain)
        current["status"] = "installed"
        current["identity"] = list(installed_identity)
        journal = _refresh_publication_journal(journal)
        expected_identity = installed_identity
        _after_leaf_install(staging, installed_identity)
    else:
        raise SafeIOError("publication recovery leaf state is invalid")

    staging_identity = _optional_regular_identity(directory_fd, staging)
    if staging_identity is not None:
        if staging_identity != expected_identity:
            raise SafeIOError("publication staging identity conflicts")
        if not _unlink_if_exact_regular_file(
                directory_fd, staging, data, expected_identity):
            raise SafeIOError("publication staging identity changed")
        os.fsync(directory_fd)
    result = _snapshot_result(
        chain, snapshot.root, snapshot.relative, data,
        _inode_identity_from_file(expected_identity))
    _validate_publication_leaf(journal[3], result)
    return result, journal


def _remove_publication_journal(journal):
    journal_fd, journal_name, journal_inode, _state = journal[:4]
    _revalidate_publication_journal(journal)
    if not _unlink_if_identity(
            journal_fd, journal_name, journal_inode):
        raise SafeIOError("publication recovery record identity changed")
    os.fsync(journal_fd)


def _discard_effectless_publication(chain, journal, leaf):
    if journal is None:
        return
    state = journal[3]
    attempts = state["leaf"]["attempts"]
    if (state["directories"] or len(attempts) != 1 or
            attempts[-1]["status"] != "planned"):
        return
    try:
        _require_absent(chain[-1].fd, leaf)
        for attempt in attempts:
            _require_absent(chain[-1].fd, attempt["staging"])
        _remove_publication_journal(journal)
    except BaseException:
        # Preserve the exception that caused this best-effort cleanup.  The
        # untouched initial planned journal remains safe to retry.
        pass


def publish_exclusive(root, relative, data=None, *, retain_authority=False
                      ) -> FileSnapshot:
    """Publish once, or resume a directory-tail creation by MissingSnapshot.

    Callers that may retry after interruption must retain and reuse the
    original ``MissingSnapshot``: ``publish_exclusive(missing, data)``.  A
    fresh absence observation cannot prove that partially created directories
    belong to the interrupted request.
    """
    snapshot, data = _publication_request(root, relative, data)
    preflight_publication(snapshot, data)
    chain, journal = _prepare_publication_parent(snapshot, data)
    try:
        if journal is None:
            raise SafeIOError("publication recovery authority is missing")
        result, journal = _publish_journaled_leaf(
            chain, journal, snapshot, data)
        if not retain_authority:
            _remove_publication_journal(journal)
        return result
    except BaseException:
        _discard_effectless_publication(
            chain, journal, snapshot.relative.name)
        raise
    finally:
        _close_chain(chain)


def release_publication_authority(
        snapshot, data, authority, *, before_release=None):
    """Remove a publication journal after durable authority was transferred."""
    if not isinstance(snapshot, MissingSnapshot):
        raise SafeIOError("publication authority requires a MissingSnapshot")
    if not isinstance(authority, FileSnapshot):
        raise SafeIOError("publication authority is invalid")
    data = _publication_data(data)
    preflight_publication(snapshot, data)
    chain, journal = _prepare_publication_parent(snapshot, data)
    try:
        if journal is None:
            raise SafeIOError("publication recovery authority is missing")
        result = _snapshot_result(
            chain, snapshot.root, snapshot.relative, data,
            _inode_identity_from_file(authority.file_identity))
        if (result.file_identity != authority.file_identity or
                result.directory_identities != authority.directory_identities or
                result.sha256 != authority.sha256):
            raise SafeIOError("publication authority conflicts")
        _validate_publication_leaf(journal[3], result)
        if before_release is not None:
            before_release()
        _remove_publication_journal(journal)
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
