"""Durable, append-only evidence for one real worker process attempt."""

import hashlib
import json
import os
import subprocess
import stat
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import paths
from .safeio import (DIRECTORY_FLAGS as _DIRECTORY_FLAGS,
                     FILE_NOFOLLOW as _FILE_NOFOLLOW,
                     _atomic_write)


class AttemptError(Exception):
    pass


_TERMINATE_GRACE_SECONDS = 0.2
_POST_REAP_DRAIN_SECONDS = 0.1
_TERMINAL_STATUSES = frozenset(("exited", "timed_out", "launch_failed"))


def _stamp(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json(directory_fd, name, value, before_replace=None):
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    _atomic_write(directory_fd, name, payload.encode("utf-8"),
                  before_replace=before_replace)


def _open_child_directory(parent_fd, name, create=False):
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            pass
    try:
        return os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise AttemptError(f"worker attempts path is not a safe directory: {name}") from exc


@dataclass(frozen=True)
class _DirectoryHandle:
    fd: int
    entry_name: str | None
    identity: tuple[int, int]


def _directory_handle(fd, entry_name):
    try:
        details = os.fstat(fd)
        if not stat.S_ISDIR(details.st_mode):
            raise AttemptError(
                f"worker attempts path is not a safe directory: {entry_name}")
        return _DirectoryHandle(
            fd=fd,
            entry_name=entry_name,
            identity=(details.st_dev, details.st_ino),
        )
    except BaseException:
        os.close(fd)
        raise


def _append_child_directory(chain, name, create=False):
    fd = _open_child_directory(chain[-1].fd, name, create=create)
    chain.append(_directory_handle(fd, name))


def _close_directory_chain(chain):
    first_error = None
    for handle in reversed(chain):
        try:
            os.close(handle.fd)
        except BaseException as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


def _duplicate_directory_chain(chain):
    duplicates = []
    try:
        for handle in chain:
            duplicates.append(_DirectoryHandle(
                fd=os.dup(handle.fd),
                entry_name=handle.entry_name,
                identity=handle.identity,
            ))
        return tuple(duplicates)
    except BaseException:
        _close_directory_chain(duplicates)
        raise


def _validate_directory_chain(chain):
    for index, handle in enumerate(chain):
        try:
            details = os.fstat(handle.fd)
        except OSError as exc:
            raise AttemptError("worker attempt directory chain is closed") from exc
        if (not stat.S_ISDIR(details.st_mode) or
                (details.st_dev, details.st_ino) != handle.identity):
            raise AttemptError("worker attempt directory identity changed")
        if index == 0:
            continue
        parent = chain[index - 1]
        try:
            entry = os.stat(handle.entry_name, dir_fd=parent.fd,
                            follow_symlinks=False)
        except OSError as exc:
            raise AttemptError(
                f"worker attempt directory chain was relocated: "
                f"{handle.entry_name}") from exc
        if (not stat.S_ISDIR(entry.st_mode) or
                (entry.st_dev, entry.st_ino) != handle.identity):
            raise AttemptError(
                f"worker attempt directory chain was replaced: "
                f"{handle.entry_name}")


def _open_item_directory_chain(repo, item_path):
    repo_absolute = Path(os.path.abspath(repo))
    item_absolute = Path(os.path.abspath(item_path))
    try:
        relative_item = item_absolute.relative_to(repo_absolute)
    except ValueError as exc:
        raise AttemptError("item directory must be inside the repository") from exc
    root = Path(repo_absolute.anchor)
    relative_repo = repo_absolute.relative_to(root)
    if any(part in ("", ".", "..")
           for part in relative_repo.parts + relative_item.parts):
        raise AttemptError("item directory contains an unsafe path component")

    chain = []
    try:
        root_fd = os.open(repo_absolute.anchor, _DIRECTORY_FLAGS)
        chain.append(_directory_handle(root_fd, None))
        for part in relative_repo.parts:
            _append_child_directory(chain, part)
        for part in relative_item.parts:
            _append_child_directory(chain, part)
        _validate_directory_chain(chain)
        return chain
    except BaseException:
        _close_directory_chain(chain)
        raise


@dataclass
class Attempt:
    attempt_id: str
    path: Path
    timeout_seconds: float
    _directory_chain: tuple[_DirectoryHandle, ...] = field(repr=False)
    _started: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock,
                                  init=False, repr=False)

    @property
    def manifest_path(self):
        return self.path / "manifest.json"

    @property
    def brief_path(self):
        return self.path / "brief.md"

    @property
    def stdout_path(self):
        return self.path / "stdout.bin"

    @property
    def stderr_path(self):
        return self.path / "stderr.bin"

    @property
    def terminal_path(self):
        return self.path / "terminal.json"

    def close(self):
        with self._lock:
            chain = self._directory_chain
            self._directory_chain = ()
        _close_directory_chain(chain)

    def _begin(self):
        with self._lock:
            if not self._directory_chain:
                raise AttemptError("worker attempt is closed")
            if self._started:
                raise AttemptError("worker attempt has already been launched")
            self._started = True
            return _duplicate_directory_chain(self._directory_chain)


def _input_hashes(item_fd):
    hashes = {}
    for name in ("plan.md", "spec.md"):
        try:
            fd = os.open(name, os.O_RDONLY, dir_fd=item_fd)
        except FileNotFoundError:
            continue
        try:
            digest = hashlib.sha256()
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                digest.update(chunk)
            hashes[name] = digest.hexdigest()
        finally:
            os.close(fd)
    return hashes


def create_attempt(repo, item_id, checkout, starting_sha, timeout_seconds,
                   backend, brief):
    """Create and durably describe a fresh attempt before process launch."""
    repo = Path(repo).resolve(strict=True)
    item_path = paths.item_dir(repo, item_id)
    created = datetime.now(timezone.utc)
    chain = _open_item_directory_chain(repo, item_path)
    try:
        item_fd = chain[-1].fd
        hashes = _input_hashes(item_fd)
        _append_child_directory(chain, "worker", create=True)
        # Opening with O_NOFOLLOW rejects an existing attempts symlink before
        # any artifact can be written through it.
        _append_child_directory(chain, "attempts", create=True)
        attempts_fd = chain[-1].fd
        while True:
            attempt_id = (created.strftime("%Y%m%dT%H%M%S%fZ") + "-" +
                          uuid.uuid4().hex)
            try:
                os.mkdir(attempt_id, 0o700, dir_fd=attempts_fd)
                os.fsync(attempts_fd)
                break
            except FileExistsError:
                continue
        _append_child_directory(chain, attempt_id)
        attempt_fd = chain[-1].fd

        for stream_name in ("stdout.bin", "stderr.bin"):
            fd = os.open(stream_name,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_NOFOLLOW,
                         0o600, dir_fd=attempt_fd)
            os.close(fd)
        _atomic_write(attempt_fd, "brief.md", brief.encode("utf-8"))
        manifest = {
            "attempt_id": attempt_id,
            "backend": backend,
            "checkout": str(Path(checkout).resolve()),
            "created_at": _stamp(created),
            "deadline": _stamp(created + timedelta(seconds=timeout_seconds)),
            "input_hashes": hashes,
            "item_id": item_id,
            "starting_sha": starting_sha,
            "state": "running",
            "timeout_seconds": timeout_seconds,
            "transport": "unterminated",
        }
        _atomic_json(attempt_fd, "manifest.json", manifest)
        os.fsync(attempts_fd)
        _validate_directory_chain(chain)
        path = item_path / "worker" / "attempts" / attempt_id
        result = Attempt(attempt_id, path, timeout_seconds, tuple(chain))
        chain = []
        return result
    finally:
        _close_directory_chain(chain)


def _pump(source, destination_fd, stop, errors):
    try:
        source_fd = source.fileno()
        os.set_blocking(source_fd, False)
        drain_deadline = None
        while True:
            if stop.is_set():
                if drain_deadline is None:
                    drain_deadline = (time.monotonic() +
                                      _POST_REAP_DRAIN_SECONDS)
                elif time.monotonic() >= drain_deadline:
                    break
            try:
                chunk = os.read(source_fd, 65536)
            except BlockingIOError:
                if stop.is_set():
                    break
                stop.wait(0.01)
                continue
            if not chunk:
                break
            view = memoryview(chunk)
            while view:
                written = os.write(destination_fd, view)
                view = view[written:]
            if stop.is_set():
                if drain_deadline is None:
                    drain_deadline = (time.monotonic() +
                                      _POST_REAP_DRAIN_SECONDS)
                elif time.monotonic() >= drain_deadline:
                    break
    except BaseException as exc:
        errors.append(exc)
    finally:
        for close_action in (source.close,
                             lambda: os.fsync(destination_fd),
                             lambda: os.close(destination_fd)):
            try:
                close_action()
            except BaseException as exc:
                errors.append(exc)


def _stop_and_reap(proc):
    """Bounded two-phase stop for an interrupted or timed-out process."""
    try:
        proc.terminate()
    except ProcessLookupError:
        pass
    threading.Event().wait(_TERMINATE_GRACE_SECONDS)
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    proc.wait()


def _publish_terminal(directory_fd, attempt_id, status, exit_code,
                      before_replace):
    _atomic_json(directory_fd, "terminal.json", {
        "attempt_id": attempt_id,
        "exit_code": exit_code,
        "finished_at": _stamp(datetime.now(timezone.utc)),
        "status": status,
    }, before_replace=before_replace)


def run_process(attempt, argv, cwd, env):
    """Run argv, stream exact bytes, reap, then publish terminal state."""
    directory_chain = attempt._begin()
    directory_fd = directory_chain[-1].fd
    validate_chain = lambda: _validate_directory_chain(directory_chain)
    proc = None
    try:
        try:
            validate_chain()
            proc = subprocess.Popen(
                argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=False, bufsize=0)
        except OSError as exc:
            validate_chain()
            message = f"{type(exc).__name__}: {exc}\n".encode(
                "utf-8", errors="replace")
            stderr_fd = os.open("stderr.bin", os.O_WRONLY | os.O_APPEND |
                                _FILE_NOFOLLOW, dir_fd=directory_fd)
            try:
                os.write(stderr_fd, message)
                os.fsync(stderr_fd)
            finally:
                os.close(stderr_fd)
            _publish_terminal(directory_fd, attempt.attempt_id,
                              "launch_failed", 127, validate_chain)
            return {"exit_code": 127, "stdout": "",
                    "stderr": message.decode("utf-8", errors="replace"),
                    "timed_out": False}

        errors = []
        stop_readers = threading.Event()
        captures = []
        readers = []
        try:
            captures.append((
                proc.stdout,
                os.open("stdout.bin", os.O_WRONLY | os.O_APPEND |
                        _FILE_NOFOLLOW, dir_fd=directory_fd),
                "stdout"))
            captures.append((
                proc.stderr,
                os.open("stderr.bin", os.O_WRONLY | os.O_APPEND |
                        _FILE_NOFOLLOW, dir_fd=directory_fd),
                "stderr"))
            for source, destination_fd, stream_name in captures:
                reader = threading.Thread(
                    target=_pump,
                    args=(source, destination_fd, stop_readers, errors),
                    name=f"worker-{attempt.attempt_id}-{stream_name}")
                reader.start()
                readers.append(reader)
            timed_out = False
            try:
                proc.wait(timeout=attempt.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _stop_and_reap(proc)
        except BaseException:
            if proc.poll() is None:
                _stop_and_reap(proc)
            raise
        finally:
            # The direct child is reaped first. Readers then drain bytes
            # already present in each nonblocking pipe and close every handle;
            # a descendant retaining a writer cannot park the controller.
            stop_readers.set()
            for reader in readers:
                reader.join()
            for source, destination_fd, _ in captures[len(readers):]:
                try:
                    source.close()
                finally:
                    os.close(destination_fd)
            for source in (proc.stdout, proc.stderr):
                if source is not None and not source.closed:
                    source.close()

        if errors:
            raise AttemptError(f"failed to capture worker output: {errors[0]}")
        os.fsync(directory_fd)
        stdout = os.open("stdout.bin", os.O_RDONLY | _FILE_NOFOLLOW,
                         dir_fd=directory_fd)
        stderr = os.open("stderr.bin", os.O_RDONLY | _FILE_NOFOLLOW,
                         dir_fd=directory_fd)
        try:
            stdout_bytes = bytearray()
            while True:
                chunk = os.read(stdout, 65536)
                if not chunk:
                    break
                stdout_bytes.extend(chunk)
            stderr_bytes = bytearray()
            while True:
                chunk = os.read(stderr, 65536)
                if not chunk:
                    break
                stderr_bytes.extend(chunk)
        finally:
            os.close(stdout)
            os.close(stderr)

        status = "timed_out" if timed_out else "exited"
        exit_code = 124 if timed_out else proc.returncode
        validate_chain()
        _publish_terminal(directory_fd, attempt.attempt_id, status, exit_code,
                          validate_chain)
        return {
            "exit_code": exit_code,
            "stdout": stdout_bytes.decode("utf-8", errors="replace"),
            "stderr": stderr_bytes.decode("utf-8", errors="replace"),
            "timed_out": timed_out,
        }
    except BaseException:
        if proc is not None and proc.poll() is None:
            _stop_and_reap(proc)
        raise
    finally:
        _close_directory_chain(directory_chain)


def _valid_terminal(candidate, attempt_id):
    if not isinstance(candidate, dict):
        return False
    if candidate.get("attempt_id") != attempt_id:
        return False
    status = candidate.get("status")
    if not isinstance(status, str) or status not in _TERMINAL_STATUSES:
        return False
    exit_code = candidate.get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        return False
    finished_at = candidate.get("finished_at")
    if not isinstance(finished_at, str) or not finished_at.strip():
        return False
    normalized = (finished_at[:-1] + "+00:00"
                  if finished_at.endswith("Z") else finished_at)
    try:
        finished = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    if finished.tzinfo is None or finished.utcoffset() != timedelta(0):
        return False
    if status == "timed_out" and exit_code != 124:
        return False
    if status == "launch_failed" and exit_code != 127:
        return False
    return True


def inspect_attempts(repo, item_id):
    """Return recorded attempts without creating or repairing artifacts."""
    root = paths.item_dir(repo, item_id) / "worker" / "attempts"
    try:
        if root.is_symlink():
            raise AttemptError(f"worker attempts path is a symlink: {root}")
        entries = sorted(p for p in root.iterdir()
                         if p.is_dir() and not p.is_symlink())
    except FileNotFoundError:
        return []
    rows = []
    for entry in entries:
        manifest_path = entry / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        terminal = None
        terminal_path = entry / "terminal.json"
        if terminal_path.is_file() and not terminal_path.is_symlink():
            try:
                candidate = json.loads(terminal_path.read_text(
                    encoding="utf-8"))
                if _valid_terminal(candidate, entry.name):
                    terminal = candidate
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass
        row = dict(manifest) if isinstance(manifest, dict) else {}
        row["attempt_id"] = entry.name
        row["terminal"] = terminal
        row["transport"] = (terminal["status"] if terminal is not None
                            else "unterminated")
        rows.append(row)
    return rows
