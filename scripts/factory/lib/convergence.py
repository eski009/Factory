"""Approach-convergence evidence for the plan -> implement boundary.

The planner and fresh reviewers make semantic claims. This module proves only
the closed envelope, exact plan bytes, engine-derived planning round, bounded
citations, independent invocation identities, and coherent disposition.
"""

import errno
import fcntl
import hashlib
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from . import initrepo, items, logs, paths
from .validate import validate as validate_schema

SIGNAL_IDS = (
    "natural-language-rule-tail",
    "input-variety-task-growth",
    "unconstrained-output-postprocess",
)
FINAL_VERDICTS = ("not-triggered", "pass", "reject", "uncertain")
DISPOSITIONS = ("advance", "escalate", "approach.rejected")
SPECIAL = frozenset(("blocked", "waiting-human"))
IMMUTABLE_FIELDS = (
    "version", "item", "planning_round", "plan_sha256", "configuration",
    "tier", "planner_invocation", "signals", "escalation_bound",
)


class ConvergenceError(ValueError):
    """A judgement cannot be recorded or cannot authorize advancement."""


class _AuthoritativeRecordMissing(ConvergenceError):
    """The canonical record does not exist under the anchored repository."""


def _config(repo):
    try:
        value = json.loads(paths.config_path(repo).read_text(
            encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def enabled(repo):
    value = _config(repo).get("approach_convergence")
    return isinstance(value, dict) and value.get("enabled") is True


def escalation_bound(tier):
    if tier == "bug":
        return 0
    if tier in ("feature", "epic"):
        return 1
    raise ConvergenceError(f"unknown tier for approach convergence: {tier!r}")


def planning_round(repo, item_id):
    count = 0
    for event in logs.read_events(repo, item_id):
        if event.get("event") != "stage.advance":
            continue
        data = event.get("data")
        if (isinstance(data, dict) and data.get("to") == "plan"
                and data.get("from") in ("spec", "design")):
            count += 1
    if count == 0:
        raise ConvergenceError(
            "approach convergence has no non-special engine entry into plan; "
            "re-enter plan through factory advance before recording evidence")
    return f"plan-{count:04d}"


def judgement_path(repo, item_id, round_key, plan_sha256):
    return (paths.item_dir(repo, item_id) / "approach-judgements" /
            f"{round_key}-{plan_sha256}.json")


def _repo_relative(repo, path):
    return Path(path).relative_to(Path(repo)).as_posix()


def _identity(info):
    return info.st_dev, info.st_ino


def _version(info):
    return (_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _anchored_item(repo, item_id):
    """Pin every repository-relative directory; never follow a symlink."""
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ConvergenceError("plan.md secure read requires O_NOFOLLOW")
    flags = os.O_RDONLY | os.O_DIRECTORY | nofollow
    descriptors, links = [], []
    try:
        root = os.path.abspath(os.fspath(repo))
        components = (root, ".factory", "items", item_id)
        for component in components:
            parent = descriptors[-1] if descriptors else None
            fd = os.open(component, flags, dir_fd=parent)
            descriptors.append(fd)
            links.append((parent, component, _identity(os.fstat(fd))))

        def verify():
            for parent, component, identity in links:
                info = os.stat(component, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode) or _identity(info) != identity:
                    raise ConvergenceError("plan.md changed: item path replaced")

        verify()
        yield descriptors[-1], verify
    except OSError as exc:
        raise ConvergenceError(
            "plan.md untrusted symlink or unreadable item path") from exc
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _open_regular(directory_fd, name, writable=False):
    flags = (os.O_RDWR if writable else os.O_RDONLY)
    flags |= os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise ConvergenceError(
            f"{name} untrusted symlink or missing or unreadable") from exc
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ConvergenceError(f"{name} must be a regular file")
    return fd


def _read_descriptor(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []
    while chunk := os.read(fd, 65536):
        chunks.append(chunk)
    return b"".join(chunks)


def _read_plan(directory_fd):
    fd = _open_regular(directory_fd, "plan.md")
    try:
        before = os.fstat(fd)
        content = _read_descriptor(fd)
        after = os.fstat(fd)
        live = os.stat("plan.md", dir_fd=directory_fd, follow_symlinks=False)
        if (_version(before) != _version(after)
                or _version(after) != _version(live)):
            raise ConvergenceError("plan.md changed while reading")
        if not content:
            raise ConvergenceError("plan.md missing or empty")
        return content, _version(after)
    finally:
        os.close(fd)


def plan_bytes(repo, item_id):
    with _anchored_item(repo, item_id) as (directory_fd, verify):
        content, _version_key = _read_plan(directory_fd)
        verify()
        return content


@contextmanager
def authorized_edge(repo, item_id, record):
    """Guard both writes and restore their original bytes on interference.

    The directory lock serializes enabled advances. Descriptor writes remain
    inside the anchored item even if a parent or leaf is replaced. Checks on
    both sides of each write detect non-cooperating plan editors too. The edge
    carries the judged hash: POSIX cannot atomically publish two files or stop
    an arbitrary editor after the final check. This is an in-process rollback
    boundary, not a crash-atomic filesystem transaction.
    """
    with _anchored_item(repo, item_id) as (directory_fd, verify_path):
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
        snapshots = []
        try:
            content, version = _read_plan(directory_fd)
            # The early machine check preserves checkbox-first diagnostics;
            # repeat it on the exact snapshot whose hash admits this edge.
            try:
                plan_text = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ConvergenceError(str(exc)) from exc
            if "- [ ]" not in plan_text:
                raise ConvergenceError(
                    "plan.md with at least one '- [ ]' task required")
            if hashlib.sha256(content).hexdigest() != record["plan_sha256"]:
                raise ConvergenceError("plan.md changed after approach validation")
            for name in ("item.md", "log.jsonl"):
                fd = _open_regular(directory_fd, name, writable=True)
                snapshots.append((name, fd, _read_descriptor(fd)))
            # A second advance may have validated before waiting for our
            # directory lock. Recheck its source and round while holding it.
            live_meta, _body = items.parse_item(snapshots[0][2].decode("utf-8"))
            if (live_meta["stage"] != "plan"
                    or items.item_tier(live_meta) != record["tier"]
                    or planning_round(repo, item_id) != record["planning_round"]):
                raise ConvergenceError("plan stage or judgement context changed")

            def verify():
                verify_path()
                current, current_version = _read_plan(directory_fd)
                if current != content or current_version != version:
                    raise ConvergenceError("plan.md changed during stage persistence")
                for name, fd, _original in snapshots:
                    live = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if _identity(live) != _identity(os.fstat(fd)):
                        raise ConvergenceError(f"plan.md changed: {name} replaced")

            verify()
            try:
                yield snapshots[0][1], snapshots[1][1], verify
                verify()
            except BaseException:
                # Restore only the pinned files we wrote, never a replacement
                # path, and never restore the adversary's edited plan.
                for _name, fd, original in snapshots:
                    with os.fdopen(os.dup(fd), "wb") as stream:
                        stream.seek(0)
                        stream.write(original)
                        stream.truncate()
                raise
        except OSError as exc:
            raise ConvergenceError("plan.md changed or became unreadable") from exc
        finally:
            for _name, fd, _original in snapshots:
                os.close(fd)
            fcntl.flock(directory_fd, fcntl.LOCK_UN)


def current_context(repo, item_id):
    meta, _body = items.load_item(repo, item_id)
    if meta.get("stage") != "plan":
        raise ConvergenceError(
            f"approach convergence requires stage 'plan', got {meta.get('stage')!r}")
    content = plan_bytes(repo, item_id)
    round_key = planning_round(repo, item_id)
    digest = hashlib.sha256(content).hexdigest()
    tier = items.item_tier(meta)
    record = judgement_path(repo, item_id, round_key, digest)
    return {
        "item": item_id,
        "planning_round": round_key,
        "plan_sha256": digest,
        "tier": tier,
        "escalation_bound": escalation_bound(tier),
        "enabled": enabled(repo),
        "record": _repo_relative(repo, record),
    }


def _stale_record_reason(repo, context):
    directory = (Path(repo) / context["record"]).parent
    same_round = None
    same_hash = None
    found_json = False
    try:
        candidates = sorted(directory.glob("*.json"))
    except OSError:
        return None
    for path in candidates:
        try:
            record = _load_record(path)
        except ConvergenceError:
            continue
        found_json = True
        if not isinstance(record, dict):
            continue
        if (record.get("planning_round") == context["planning_round"]
                and record.get("plan_sha256") != context["plan_sha256"]):
            same_round = path
        elif (record.get("planning_round") != context["planning_round"]
              and record.get("plan_sha256") == context["plan_sha256"]):
            same_hash = path
    if same_round is not None:
        return (
            f"stale plan judgement retained at {_repo_relative(repo, same_round)}; "
            "record the edited plan's current hash")
    if same_hash is not None:
        return (
            "stale planning-round judgement retained at "
            f"{_repo_relative(repo, same_hash)}; record the current round "
            f"{context['planning_round']}")
    if found_json:
        return (
            "only stale approach judgements exist; record the current round "
            f"{context['planning_round']} and plan hash {context['plan_sha256']}")
    return None


def require_authoritative(repo, meta):
    if not enabled(repo):
        return None
    context = current_context(repo, meta["id"])
    try:
        record = _load_authoritative_record(repo, context["record"])
    except _AuthoritativeRecordMissing:
        stale = _stale_record_reason(repo, context)
        if stale:
            raise ConvergenceError(stale)
        raise ConvergenceError(
            "current approach judgement missing: run factory approach-context "
            f"{meta['id']} --json, then record through factory "
            "approach-judgement")
    validate_current(repo, meta, record)
    if record["disposition"] == "escalate":
        raise ConvergenceError(
            "approach judgement requires one fresh escalation reviewer")
    if record["disposition"] == "approach.rejected":
        raise ConvergenceError(
            "approach judgement rejected the current plan; append the cited "
            "forbidden approach, then route factory advance "
            f"{meta['id']} spec --reason 'approach.rejected: <one line>'")
    return record


def _schema_errors(record, label="judgement"):
    return validate_schema(
        record, initrepo.load_schema("approach-judgement"), label)


def _citation_error(repo, citation, label, required_path=None):
    rel = citation["path"]
    pure = PurePosixPath(rel)
    if pure.is_absolute() or ".." in pure.parts:
        return f"{label}: citation escapes the repository: {rel}"
    if required_path is not None and rel != required_path:
        return (f"{label}: signal must cite the current plan "
                f"{required_path}, got {rel}")
    path = Path(repo) / rel
    if not path.is_file():
        return f"{label}: citation path missing: {rel}"
    repo_root = Path(repo).resolve()
    target = path.resolve()
    try:
        target.relative_to(repo_root)
    except ValueError:
        return f"{label}: citation escapes the repository: {rel}"
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return f"{label}: citation path unreadable: {rel}"
    start = citation["start_line"]
    end = citation["end_line"]
    if start > end:
        return f"{label}: citation start exceeds end: {rel}:{start}-{end}"
    if end > len(lines):
        return (f"{label}: citation range out of range: "
                f"{rel}:{start}-{end} has {len(lines)} line(s)")
    if not any(line.strip() for line in lines[start - 1:end]):
        return f"{label}: citation range is empty: {rel}:{start}-{end}"
    return None


def _expected_resolution(record):
    signals = record["signals"]
    attempts = record["attempts"]
    bound = record["escalation_bound"]
    if not signals:
        return "not-triggered", "advance"
    last = attempts[-1]
    unresolved = last["verdict"] == "uncertain" or last["evidence_conflict"]
    if unresolved:
        if len(attempts) - 1 < bound:
            return "uncertain", "escalate"
        return "uncertain", "approach.rejected"
    if last["verdict"] == "pass":
        return "pass", "advance"
    return "reject", "approach.rejected"


def validate_current(repo, meta, record):
    errors = _schema_errors(record)
    if errors:
        raise ConvergenceError(
            "approach judgement schema invalid: " + "; ".join(errors))
    context = current_context(repo, meta["id"])
    if record["item"] != meta["id"]:
        raise ConvergenceError(
            f"approach judgement wrong item: expected {meta['id']}, "
            f"got {record['item']}")
    if record["planning_round"] != context["planning_round"]:
        raise ConvergenceError(
            f"approach judgement stale planning round: expected "
            f"{context['planning_round']}, got {record['planning_round']}")
    if record["plan_sha256"] != context["plan_sha256"]:
        raise ConvergenceError(
            f"approach judgement stale plan hash: expected "
            f"{context['plan_sha256']}, got {record['plan_sha256']}")
    if record["tier"] != context["tier"]:
        raise ConvergenceError(
            f"approach judgement tier context stale: expected "
            f"{context['tier']}, got {record['tier']}")
    if record["escalation_bound"] != context["escalation_bound"]:
        raise ConvergenceError(
            f"approach judgement escalation bound stale: expected "
            f"{context['escalation_bound']}, got "
            f"{record['escalation_bound']}")

    ids = [signal["id"] for signal in record["signals"]]
    if len(ids) != len(set(ids)):
        raise ConvergenceError(
            "approach judgement signal ids must be unique")
    plan_rel = f".factory/items/{meta['id']}/plan.md"
    for signal in record["signals"]:
        if not signal["evidence"]:
            raise ConvergenceError(
                f"approach judgement signal {signal['id']} has no plan citations")
        for index, citation in enumerate(signal["evidence"], 1):
            problem = _citation_error(
                repo, citation,
                f"approach judgement signal {signal['id']} citation {index}",
                required_path=plan_rel)
            if problem:
                raise ConvergenceError(problem)

    attempts = record["attempts"]
    if record["signals"] and not attempts:
        raise ConvergenceError(
            "approach judgement incoherent: named signals require a reviewer attempt")
    if not record["signals"] and attempts:
        raise ConvergenceError(
            "approach judgement incoherent: no-signal screen requires zero attempts")
    maximum = 1 + record["escalation_bound"]
    if len(attempts) > maximum:
        raise ConvergenceError(
            f"approach judgement attempt count {len(attempts)} exceeds "
            f"resolved maximum {maximum}")
    numbers = [attempt["attempt"] for attempt in attempts]
    expected_numbers = list(range(1, len(attempts) + 1))
    if numbers != expected_numbers:
        raise ConvergenceError(
            f"approach judgement attempt numbers must be {expected_numbers}, "
            f"got {numbers}")
    reviewers = []
    for attempt in attempts:
        if attempt["invocation"] == record["planner_invocation"]:
            raise ConvergenceError(
                f"approach judgement reviewer attempt {attempt['attempt']} "
                "matches planner invocation")
        if attempt["invocation"] in reviewers:
            raise ConvergenceError(
                f"approach judgement reviewer invocation reused: "
                f"{attempt['invocation']}")
        reviewers.append(attempt["invocation"])
        if not attempt["findings"]:
            raise ConvergenceError(
                f"approach judgement reviewer attempt {attempt['attempt']} "
                "has no cited findings")
        for index, finding in enumerate(attempt["findings"], 1):
            problem = _citation_error(
                repo, finding,
                f"approach judgement reviewer attempt "
                f"{attempt['attempt']} finding {index}")
            if problem:
                raise ConvergenceError(problem)
    if len(attempts) == 2:
        first = attempts[0]
        if first["verdict"] != "uncertain" and not first["evidence_conflict"]:
            raise ConvergenceError(
                "approach judgement first attempt did not authorize escalation")
    actual_count = max(0, len(attempts) - 1)
    if record["escalation_count"] != actual_count:
        raise ConvergenceError(
            f"approach judgement escalation_count "
            f"{record['escalation_count']} does not match {actual_count}")
    expected_verdict, expected_disposition = _expected_resolution(record)
    if (record["final_verdict"], record["disposition"]) != (
            expected_verdict, expected_disposition):
        raise ConvergenceError(
            "approach judgement incoherent: expected "
            f"{expected_verdict} + {expected_disposition}, got "
            f"{record['final_verdict']} + {record['disposition']}")
    return record


def _load_record(path):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConvergenceError(
            f"approach judgement unreadable: {path.name}") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConvergenceError(
            f"approach judgement malformed JSON: {path.name} ({exc})") from exc
    return value


def _load_authoritative_record(repo, relative):
    """Load canonical bytes without following any path component symlink."""
    pure = PurePosixPath(relative)
    if (pure.is_absolute() or not pure.parts
            or any(part in ("", ".", "..") for part in pure.parts)):
        raise ConvergenceError(
            f"approach judgement has an untrusted canonical path: {relative}")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ConvergenceError(
            "approach judgement cannot securely inspect canonical artifact "
            f"{relative}: O_NOFOLLOW is unavailable")
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    repo_root = Path(os.path.abspath(os.fspath(repo)))

    def is_symlink(component, parent_fd=None):
        try:
            if parent_fd is None:
                info = os.lstat(component)
            else:
                info = os.stat(
                    component, dir_fd=parent_fd, follow_symlinks=False)
        except OSError:
            return False
        return stat.S_ISLNK(info.st_mode)

    def open_component(component, parent_fd=None, directory=False):
        component_flags = directory_flags if directory else flags
        try:
            if parent_fd is None:
                descriptor = os.open(component, component_flags)
            else:
                descriptor = os.open(
                    component, component_flags, dir_fd=parent_fd)
        except OSError as exc:
            if is_symlink(component, parent_fd):
                raise ConvergenceError(
                    "approach judgement untrusted symlink in canonical "
                    f"artifact path {relative}: {component}") from exc
            if exc.errno == errno.ENOENT:
                raise _AuthoritativeRecordMissing(relative) from exc
            raise ConvergenceError(
                f"approach judgement unreadable: {pure.name}; canonical "
                f"artifact {relative}: {exc.strerror or exc}") from exc
        expected = stat.S_ISDIR if directory else stat.S_ISREG
        if not expected(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            kind = "directory" if directory else "regular file"
            raise ConvergenceError(
                f"approach judgement unreadable: {pure.name}; canonical "
                f"artifact {relative} component {component} is not a {kind}")
        return descriptor

    directory_fd = open_component(repo_root, directory=True)
    try:
        for component in pure.parts[:-1]:
            next_fd = open_component(
                component, parent_fd=directory_fd, directory=True)
            os.close(directory_fd)
            directory_fd = next_fd
        record_fd = open_component(pure.name, parent_fd=directory_fd)
        try:
            with os.fdopen(record_fd, encoding="utf-8") as record_file:
                record_fd = None
                text = record_file.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise ConvergenceError(
                f"approach judgement unreadable: {pure.name}") from exc
        finally:
            if record_fd is not None:
                os.close(record_fd)
    finally:
        os.close(directory_fd)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConvergenceError(
            f"approach judgement malformed JSON: {pure.name} ({exc})") from exc


@contextmanager
def _record_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _event_data(repo, path, record):
    return {
        "path": _repo_relative(repo, path),
        "planning_round": record["planning_round"],
        "plan_sha256": record["plan_sha256"],
        "tier": record["tier"],
        "escalation_bound": record["escalation_bound"],
        "signals": [signal["id"] for signal in record["signals"]],
        "attempts": len(record["attempts"]),
        "final_verdict": record["final_verdict"],
        "disposition": record["disposition"],
    }


def _append_recorded_event_if_missing(repo, item_id, data):
    if any(event.get("event") == "approach.judgement.recorded"
           and event.get("data") == data
           for event in logs.read_events(repo, item_id)):
        return
    logs.append_event(repo, item_id, "approach.judgement.recorded", data)


def _write_record(path, record):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            f.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _validate_existing_structure(record):
    errors = _schema_errors(record, "existing approach judgement")
    if errors:
        raise ConvergenceError(
            "existing approach judgement schema invalid: " + "; ".join(errors))


def _is_prior_tier_context(existing, record):
    """True only for a valid old tier at the current round/hash door."""
    same_door = all(existing[key] == record[key]
                    for key in ("item", "planning_round", "plan_sha256"))
    if not same_door or existing["tier"] == record["tier"]:
        return False
    return existing["escalation_bound"] == escalation_bound(existing["tier"])


def _validate_prior_tier_replacement(existing, record):
    changed = [key for key in IMMUTABLE_FIELDS
               if key not in ("tier", "escalation_bound")
               and existing[key] != record[key]]
    problems = []
    if changed:
        problems.append(
            "immutable judgement fields changed: " + ", ".join(changed))
    if existing["attempts"] != record["attempts"]:
        problems.append("prior attempts changed")
    expected_count = max(0, len(existing["attempts"]) - 1)
    if existing["escalation_count"] != expected_count:
        problems.append(
            "existing escalation_count does not match prior attempts")
    elif record["escalation_count"] != existing["escalation_count"]:
        problems.append(
            "escalation_count changed despite identical prior attempts")
    if problems:
        raise ConvergenceError(
            "approach judgement tier-context replacement refused: "
            + "; ".join(problems))


def record_judgement(repo, item_id, record):
    meta, _body = items.load_item(repo, item_id)
    if not enabled(repo):
        raise ConvergenceError(
            "unsolicited approach judgement: approach_convergence.enabled "
            "is not true")
    context = current_context(repo, item_id)
    path = Path(repo) / context["record"]
    with _record_lock(path):
        attempts = record.get("attempts") if isinstance(record, dict) else None
        if (not path.exists() and isinstance(attempts, list)
                and len(attempts) > 1):
            raise ConvergenceError(
                "approach judgement initial write may contain at most one "
                "reviewer attempt")
        validate_current(repo, meta, record)
        data = _event_data(repo, path, record)
        if path.exists():
            existing = _load_record(path)
            _validate_existing_structure(existing)
            existing_data = _event_data(repo, path, existing)
            if _is_prior_tier_context(existing, record):
                # Tier/bound are mutable context but do not participate in the
                # canonical round/hash path. Reconcile the accepted historical
                # state before replacing it with the freshly validated current
                # tier, so an interruption cannot erase its audit event.
                _validate_prior_tier_replacement(existing, record)
                _append_recorded_event_if_missing(
                    repo, item_id, existing_data)
                _write_record(path, record)
                _append_recorded_event_if_missing(repo, item_id, data)
                return path
            validate_current(repo, meta, existing)
            _append_recorded_event_if_missing(repo, item_id, existing_data)
            if existing == record:
                return path
            changed = [key for key in IMMUTABLE_FIELDS
                       if existing.get(key) != record.get(key)]
            if changed:
                raise ConvergenceError(
                    "approach judgement immutable judgement fields changed: "
                    + ", ".join(changed))
            if existing["disposition"] != "escalate":
                raise ConvergenceError(
                    "approach judgement is final; only an escalate record may "
                    "append a reviewer attempt")
            if (len(record["attempts"]) != len(existing["attempts"]) + 1
                    or record["attempts"][:-1] != existing["attempts"]):
                raise ConvergenceError(
                    "approach judgement update must append exactly one reviewer "
                    "attempt and preserve prior attempts byte-for-byte")
        _write_record(path, record)
        _append_recorded_event_if_missing(repo, item_id, data)
        return path
