"""Logically append-only per-item event log: .factory/items/<id>/log.jsonl.

One sorted-keys JSON object per line. Timestamps are UTC and can be
frozen for tests via the FACTORY_NOW environment variable.

Publication is bounded copy-on-write rather than an in-place ``O_APPEND``:
successful writes atomically replace the authoritative inode while preserving
the exact historical byte prefix.
"""

import fcntl
import json
import os
import stat
import threading
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone

from . import paths


_SUPPLIED_DESCRIPTOR_LOCK = threading.RLock()


def now_stamp():
    override = os.environ.get("FACTORY_NOW")
    if override:
        return override
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_path(repo, item_id):
    return paths.item_dir(repo, item_id) / "log.jsonl"


@contextmanager
def append_lock(file_fd):
    """Serialize supplied-descriptor appends and rollback on its inode."""
    fcntl.flock(file_fd, fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(file_fd, fcntl.LOCK_UN)


def _write_all(file_fd, payload):
    while payload:
        written = os.write(file_fd, payload)
        if written == 0:
            raise OSError("audit log write made no progress")
        payload = payload[written:]


def _append_event_descriptor(event, data, file_fd, append_span):
    entry = _entry(event, data)
    payload = _entry_bytes(entry)
    with _SUPPLIED_DESCRIPTOR_LOCK:
        flags = None
        try:
            flags = fcntl.fcntl(file_fd, fcntl.F_GETFL)
            if not flags & os.O_APPEND:
                fcntl.fcntl(file_fd, fcntl.F_SETFL, flags | os.O_APPEND)
            with append_lock(file_fd):
                start = os.fstat(file_fd).st_size
                try:
                    _write_all(file_fd, payload)
                finally:
                    if append_span is not None:
                        append_span[:] = [start, os.fstat(file_fd).st_size]
        finally:
            if flags is not None and not flags & os.O_APPEND:
                fcntl.fcntl(file_fd, fcntl.F_SETFL, flags)
    return entry


def rollback_append(file_fd, span):
    """Remove one supplied-descriptor append while retaining later bytes."""
    with _SUPPLIED_DESCRIPTOR_LOCK:
        with append_lock(file_fd):
            start, end = span
            chunks = []
            offset = end
            while chunk := os.pread(file_fd, 65536, offset):
                chunks.append(chunk)
                offset += len(chunk)
            os.ftruncate(file_fd, start)
            for chunk in chunks:
                _write_all(file_fd, chunk)
            os.fsync(file_fd)


def _entry(event, data=None):
    entry = {"event": event, "ts": now_stamp()}
    if data is not None:
        entry["data"] = data
    return entry


def _entry_bytes(entry):
    """Encode an event exactly as authoritative publication installs it."""
    return (json.dumps(
        entry, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _file_identity(details):
    return (details.st_dev, details.st_ino, details.st_size,
            details.st_mtime_ns, details.st_ctime_ns)


def _inode_identity(details):
    return (details.st_dev, details.st_ino)


def _write_log_image(fd, data):
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = os.write(fd, view[written:])
        if count <= 0:
            raise OSError("short write to item log staging file")
        written += count


def _sync_log_staging(fd):
    os.fsync(fd)


def _install_log_image(directory_fd, staging_name, existed):
    if existed:
        os.replace(
            staging_name, "log.jsonl", src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd)
        return
    os.link(
        staging_name, "log.jsonl", src_dir_fd=directory_fd,
        dst_dir_fd=directory_fd, follow_symlinks=False)


def _sync_log_directory(directory_fd):
    os.fsync(directory_fd)


def _read_fd_exact(fd, expected_size):
    chunks = []
    offset = 0
    while offset < expected_size:
        chunk = os.pread(fd, min(65536, expected_size - offset), offset)
        if not chunk:
            raise OSError("short read from item log staging file")
        chunks.append(chunk)
        offset += len(chunk)
    if os.pread(fd, 1, expected_size):
        raise OSError("item log staging file grew during verification")
    return b"".join(chunks)


def _named_identity(directory_fd, name):
    details = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    if not stat.S_ISREG(details.st_mode):
        raise OSError("item log namespace entry is not a regular file")
    return details


def _opened_named_exact_identity(directory_fd, name, fd, expected_data):
    opened = os.fstat(fd)
    if (not stat.S_ISREG(opened.st_mode) or
            opened.st_size != len(expected_data) or
            _read_fd_exact(fd, len(expected_data)) != expected_data):
        raise OSError("item log staging image changed")
    identity = _file_identity(opened)
    after = os.fstat(fd)
    named = _named_identity(directory_fd, name)
    if (_file_identity(after) != identity or
            _file_identity(named) != identity):
        raise OSError("item log staging identity changed")
    return identity


def _named_exact_identity(directory_fd, name, expected_data):
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
             getattr(os, "O_NONBLOCK", 0))
    fd = os.open(name, flags, dir_fd=directory_fd)
    try:
        return _opened_named_exact_identity(
            directory_fd, name, fd, expected_data)
    finally:
        os.close(fd)


def _unlink_staging_if_exact(
        directory_fd, name, expected_data, expected_identity):
    try:
        identity = _named_exact_identity(
            directory_fd, name, expected_data)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    if identity != expected_identity:
        return False
    try:
        details = _named_identity(directory_fd, name)
    except OSError:
        return False
    if _file_identity(details) != expected_identity:
        return False
    try:
        os.unlink(name, dir_fd=directory_fd)
    except OSError:
        return False
    return True


def _after_log_staging_write():
    """Test seam after the complete new image has been written."""


def _after_log_staging_sync():
    """Test seam after the staged new image is durable."""


def _after_log_authority_sync():
    """Test seam after transactional log inode authority is durable."""


def _before_log_install():
    """Test seam before the final source and namespace revalidation."""


def _after_log_install():
    """Test seam immediately after the atomic namespace install."""


def _after_log_directory_sync():
    """Test seam after the installed namespace is durable."""


def _append_entry_locked(lock, entry, *, _operation_id=None,
                         _authority_fd=None, _authority_name=None):
    """Publish one full old+new log image under a validated item lock.

    The authoritative inode is never modified in place.  Before installation,
    every failure can affect only a staging inode.  After installation, every
    failure leaves the complete old bytes plus exactly one new record in place;
    recovery detects that record by operation id instead of appending it again.
    """
    from . import control

    control._validate_item_lock(lock)
    if (_authority_fd is None) != (_authority_name is None):
        raise control.ControlRefusal(
            "transactional log authority is incomplete")
    if _authority_name is not None:
        control._component(_authority_name, "log authority name")
    active = control._active_record(lock)
    if _operation_id is None:
        if active is not None:
            raise control.ControlRefusal(
                "legacy log append refused while an active operation is "
                "pending recovery")
    elif (active is None or
          active[0]["operation_id"] != _operation_id or
          entry.get("operation_id") != _operation_id):
        raise control.ControlRefusal(
            "transactional log append is not bound to the active operation")
    payload = _entry_bytes(entry)
    limit = control._LOG_IMAGE_LIMIT

    try:
        original = control._read_optional_bytes(
            lock._item_fd, "log.jsonl", limit=limit, sync=True)
        if original is None:
            old = b""
            old_identity = None
            old_mode = 0o600
            os.fsync(lock._item_fd)
        else:
            old, old_identity = original
            named = _named_identity(lock._item_fd, "log.jsonl")
            if _file_identity(named) != old_identity:
                raise control.ControlError("item log identity changed")
            old_mode = stat.S_IMODE(named.st_mode)
    except OSError as exc:
        raise control.ControlError(
            "item log history could not be made durable") from exc

    if len(old) + len(payload) > limit:
        raise control.ControlRefusal("item log image exceeds its read limit")
    image = old + payload
    staging_name = f".log.jsonl.tmp-{uuid.uuid4().hex}"
    flags = (os.O_RDWR | os.O_CREAT | os.O_EXCL |
             getattr(os, "O_NOFOLLOW", 0) |
             getattr(os, "O_NONBLOCK", 0))
    staging_fd = None
    staging_inode = None
    cleanup_identity = None
    installed = False
    try:
        authority_reused = False
        if _authority_fd is not None:
            try:
                os.link(
                    _authority_name, staging_name,
                    src_dir_fd=_authority_fd, dst_dir_fd=lock._item_fd,
                    follow_symlinks=False)
                authority_reused = True
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise control.ControlError(
                    "transactional log authority could not be staged") from exc
        if authority_reused:
            staging_fd = os.open(
                staging_name,
                os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) |
                getattr(os, "O_NONBLOCK", 0),
                dir_fd=lock._item_fd)
        else:
            staging_fd = os.open(
                staging_name, flags, old_mode, dir_fd=lock._item_fd)
            os.fchmod(staging_fd, old_mode)
        opened = os.fstat(staging_fd)
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("item log staging entry is not a regular file")
        staging_inode = _inode_identity(opened)

        if authority_reused:
            if _read_fd_exact(staging_fd, len(image)) != image:
                raise control.ControlRefusal(
                    "transactional log authority conflicts")
        else:
            _write_log_image(staging_fd, image)
        cleanup_identity = _opened_named_exact_identity(
            lock._item_fd, staging_name, staging_fd, image)
        _after_log_staging_write()

        _sync_log_staging(staging_fd)
        synced_identity = _opened_named_exact_identity(
            lock._item_fd, staging_name, staging_fd, image)
        if synced_identity != cleanup_identity:
            raise OSError("item log staging image changed after sync")
        cleanup_identity = synced_identity
        _after_log_staging_sync()

        if _authority_fd is not None:
            if not authority_reused:
                try:
                    os.link(
                        staging_name, _authority_name,
                        src_dir_fd=lock._item_fd,
                        dst_dir_fd=_authority_fd, follow_symlinks=False)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise control.ControlError(
                        "transactional log authority could not be retained") from exc
                os.fsync(_authority_fd)
            authority_identity = _named_exact_identity(
                _authority_fd, _authority_name, image)
            cleanup_identity = _opened_named_exact_identity(
                lock._item_fd, staging_name, staging_fd, image)
            if authority_identity[:2] != cleanup_identity[:2]:
                raise control.ControlRefusal(
                    "transactional log authority conflicts")
            _after_log_authority_sync()

        control._validate_item_lock(lock)
        _before_log_install()

        # Re-open the authoritative name after the final test seam and require
        # both its complete bytes and its full pre-publication identity.  This
        # catches symlink, FIFO, detach, replacement, and in-place mutation.
        current = control._read_optional_bytes(
            lock._item_fd, "log.jsonl", limit=limit, sync=True)
        if original is None:
            if current is not None:
                raise control.ControlError(
                    "item log namespace changed before install")
        elif (current is None or current[0] != old or
              current[1] != old_identity):
            raise control.ControlError(
                "item log changed before install")
        final_identity = _opened_named_exact_identity(
            lock._item_fd, staging_name, staging_fd, image)
        if (final_identity != cleanup_identity or
                final_identity[:2] != staging_inode):
            raise control.ControlError(
                "item log staging identity changed before install")
        control._validate_item_lock(lock)

        _install_log_image(
            lock._item_fd, staging_name, original is not None)
        installed = True
        installed_name = "log.jsonl"
        installed_identity = _opened_named_exact_identity(
            lock._item_fd, installed_name, staging_fd, image)
        if (installed_identity[:4] != cleanup_identity[:4] or
                installed_identity[:2] != staging_inode):
            raise control.ControlError(
                "item log staging identity changed during install")
        if _authority_fd is not None:
            authority_identity = _named_exact_identity(
                _authority_fd, _authority_name, image)
            if authority_identity[:2] != installed_identity[:2]:
                raise control.ControlRefusal(
                    "transactional log authority conflicts")
        cleanup_identity = installed_identity
        expected_installed_identity = installed_identity
        _after_log_install()

        # Exclusive creation uses a hard link so it cannot replace a raced-in
        # namespace entry.  Once installed, remove only the exact staging link.
        if original is None:
            if not _unlink_staging_if_exact(
                    lock._item_fd, staging_name, image, cleanup_identity):
                raise control.ControlError(
                    "item log staging link could not be removed")
            unlinked_identity = _opened_named_exact_identity(
                lock._item_fd, installed_name, staging_fd, image)
            if unlinked_identity[:4] != expected_installed_identity[:4]:
                raise control.ControlError(
                    "installed item log identity changed during staging "
                    "unlink")
            expected_installed_identity = unlinked_identity
        _sync_log_directory(lock._item_fd)
        _after_log_directory_sync()

        installed_bytes, installed_identity = control._read_bytes_at(
            lock._item_fd, "log.jsonl", limit=limit, sync=True)
        if (installed_bytes != image or
                installed_identity != expected_installed_identity):
            raise control.ControlError(
                "installed item log image changed")
        control._validate_item_lock(lock)
    except OSError as exc:
        state = "after install" if installed else "before install"
        raise control.ControlError(
            f"item log publication failed {state}") from exc
    finally:
        if staging_fd is not None:
            os.close(staging_fd)
        if cleanup_identity is not None:
            _unlink_staging_if_exact(
                lock._item_fd, staging_name, image, cleanup_identity)
    return entry


def append_event_locked(lock, event, data=None):
    """Legacy append path for callers already holding the shared item lock."""
    return _append_entry_locked(lock, _entry(event, data))


def append_event(repo, item_id, event, data=None, *, _lock=None,
                 file_fd=None, append_span=None):
    from . import control

    if file_fd is not None:
        if _lock is not None:
            raise control.ControlRefusal(
                "log append cannot combine item lock and supplied descriptor")
        return _append_event_descriptor(event, data, file_fd, append_span)
    if _lock is not None:
        control._validate_item_lock(_lock, repo=repo, item_id=item_id)
        return append_event_locked(_lock, event, data)
    with control.item_lock(repo, item_id, create_item=True) as lock:
        return append_event_locked(lock, event, data)


def read_events_with_stats(repo, item_id):
    """Tolerant read: returns (events, skipped) where events is the list
    of well-formed events and skipped counts non-blank corrupt lines. A
    line is corrupt when it fails json.loads, parses to a non-dict, or is
    a dict missing the "event" or "ts" key (append_event writes both
    unconditionally). Corrupt lines are never repaired or removed here —
    factory validate flags them for the human. Item spec 0007 §1."""
    path = _log_path(repo, item_id)
    if not path.exists():
        return [], 0
    events = []
    skipped = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if not isinstance(event, dict) or "event" not in event or "ts" not in event:
            skipped += 1
            continue
        events.append(event)
    return events, skipped


def read_events(repo, item_id):
    return read_events_with_stats(repo, item_id)[0]


def count_events(repo, item_id, event):
    return sum(1 for e in read_events(repo, item_id) if e["event"] == event)
