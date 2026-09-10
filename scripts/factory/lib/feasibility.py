"""Pure acceptance-plan parsing and feasibility graph validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from types import MappingProxyType
from typing import Any

from . import config_state, control, initrepo, items, ownership, safeio
from .validate import validate as validate_schema


class FeasibilityError(ValueError):
    """The declared acceptance contract is malformed or infeasible."""

    def __init__(self, errors):
        if isinstance(errors, str):
            errors = (errors,)
        self.errors = tuple(sorted(set(errors)))
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class PlanTaskMarker:
    text: str
    start: int
    end: int
    checked: bool


@dataclass(frozen=True)
class PlanSnapshot:
    report: dict
    plan_bytes: bytes
    spec_bytes: bytes
    acceptance: dict
    pending_tasks: tuple[str, ...]
    pending_task_markers: tuple[PlanTaskMarker, ...]
    inputs: tuple


@dataclass(frozen=True)
class DispatchSnapshot:
    ticket: control.DurableTicket
    handoff: str
    tasks: tuple[str, ...]
    head: str


_TASK_TEXT = re.compile(r"^\s*-\s*\[([ xX])\]\s*(.+?)\s*$")
_LINE_ENDINGS = "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"
_ITEM = re.compile(r"^[0-9]{4}-[a-z0-9-]+$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_READ_LIMIT = 1_048_576


def parse_json_bytes(data: bytes, *, label: str = "acceptance.json") -> dict:
    """Decode one strict UTF-8 JSON object and reject duplicate keys."""
    try:
        text = data.decode("utf-8", errors="strict")

        def pairs(values):
            result = {}
            for key, value in values:
                if key in result:
                    raise FeasibilityError(f"{label}: duplicate key {key!r}")
                result[key] = value
            return result

        value = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                FeasibilityError(f"{label}: invalid JSON constant {constant}")),
        )
    except FeasibilityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeasibilityError(f"{label}: invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise FeasibilityError(f"{label}: root must be an object")
    return value


def plan_task_markers(plan_bytes: bytes) -> tuple[PlanTaskMarker, ...]:
    """Match work.unticked_tasks semantics and retain exact UTF-8 offsets."""
    try:
        text = plan_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise FeasibilityError(f"plan.md: invalid UTF-8: {exc}") from exc
    markers = []
    byte_offset = 0
    for piece in text.splitlines(keepends=True):
        if piece.endswith("\r\n"):
            line = piece[:-2]
        elif piece and piece[-1] in _LINE_ENDINGS:
            line = piece[:-1]
        else:
            line = piece
        match = _TASK_TEXT.match(line)
        if match:
            start = byte_offset + len(line[:match.start(1)].encode("utf-8"))
            markers.append(PlanTaskMarker(
                match.group(2), start, start + 1,
                match.group(1) in ("x", "X")))
        byte_offset += len(piece.encode("utf-8"))
    return tuple(markers)


def normalize_plan_structure(plan_bytes: bytes) -> bytes:
    """Normalize only the x/X byte of Markdown task checkbox markers."""
    normalized = bytearray(plan_bytes)
    for marker in plan_task_markers(plan_bytes):
        if marker.checked:
            normalized[marker.start:marker.end] = b" "
    return bytes(normalized)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plan_structure_sha256(plan_bytes: bytes) -> str:
    return sha256_bytes(normalize_plan_structure(plan_bytes))


def pending_plan_tasks(plan_bytes: bytes) -> tuple[str, ...]:
    return tuple(marker.text for marker in plan_task_markers(plan_bytes)
                 if not marker.checked)


def derive_resume_cursor(plan_bytes: bytes) -> str:
    pending = pending_plan_tasks(plan_bytes)
    return pending[0] if pending else "COMPLETE"


def validate_acceptance(acceptance: dict, *, item_id: str,
                        spec_bytes: bytes, plan_bytes: bytes,
                        dependency_stages: dict[str, str] | None = None) -> dict:
    """Validate a closed acceptance object and return its derived pure report."""
    errors = []
    try:
        spec_bytes.decode("utf-8", errors="strict")
    except (AttributeError, UnicodeDecodeError) as exc:
        errors.append(f"spec.md: invalid UTF-8: {exc}")
    errors.extend(validate_schema(
        acceptance, initrepo.load_schema("acceptance-plan"), "acceptance")
    )
    errors.extend(_validate_shape(acceptance))
    if isinstance(acceptance, dict) and acceptance.get("item") != item_id:
        errors.append(f"item: expected {item_id!r}")
    if (isinstance(acceptance, dict) and
            acceptance.get("spec_sha256") != sha256_bytes(spec_bytes)):
        errors.append("spec_sha256: does not match exact spec.md bytes")
    if (isinstance(acceptance, dict) and
            acceptance.get("plan_structure_sha256") !=
            plan_structure_sha256(plan_bytes)):
        errors.append("plan_structure_sha256: does not match normalized plan.md bytes")
    if not errors:
        errors.extend(_validate_graph(
            acceptance, item_id, dependency_stages=dependency_stages))
    markers = plan_task_markers(plan_bytes)
    pending = tuple(marker.text for marker in markers if not marker.checked)
    errors = sorted(set(errors))
    if errors:
        raise FeasibilityError(errors)
    participants = {p["item"]: tuple(p["owned_paths"])
                    for p in acceptance["participants"]}
    return {
        "status": "pass", "item": item_id,
        "spec_sha256": acceptance["spec_sha256"],
        "plan_structure_sha256": acceptance["plan_structure_sha256"],
        "cursor": pending[0] if pending else "COMPLETE",
        "task": pending[0] if pending else None,
        "owned_paths": list(participants[item_id]),
        "delivery": acceptance["delivery"],
        "errors": [],
    }


def require(repo, item_id: str, *, config) -> PlanSnapshot | None:
    """Capture and validate one immutable repository-only plan snapshot."""
    return _capture_repository(
        repo, item_id, config=config, force=False, require_pending=True)


def validate_present(repo, item_id: str, *, config) -> PlanSnapshot:
    """Validate a present sidecar even when the opt-in execution gate is off."""
    return _capture_repository(
        repo, item_id, config=config, force=True, require_pending=False)


def _capture_repository(repo, item_id: str, *, config, force,
                        require_pending) -> PlanSnapshot | None:
    try:
        config_value = _config_value(config)
        canonical = config.file.root
        try:
            requested = Path(repo).resolve(strict=True)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise FeasibilityError("repository is missing or unsafe") from exc
        if requested != canonical:
            raise FeasibilityError("configuration belongs to another repository")
        if not force and "feasibility" not in config_value["gates"]:
            config_state.revalidate(config)
            return None
        if not isinstance(item_id, str) or not _ITEM.fullmatch(item_id):
            raise FeasibilityError(f"invalid item id {item_id!r}")

        root = PurePosixPath(".factory", "items", item_id)
        base_paths = (
            root / "item.md",
            root / "spec.md",
            root / "plan.md",
            root / "acceptance.json",
        )

        # Discover dependency names from one stable acceptance image, then
        # capture the complete authoritative set together.  The final image is
        # parsed again and must name the same dependencies, closing the
        # discovery/read race without trusting the preliminary bytes.
        preliminary = safeio.snapshot_path(
            canonical, root / "acceptance.json", limit=_READ_LIMIT)
        preliminary_acceptance = parse_json_bytes(
            preliminary.data, label=f"{item_id}/acceptance.json")
        preliminary_dependencies = _dependency_ids(preliminary_acceptance)
        dependency_paths = tuple(
            PurePosixPath(".factory", "items", dep, "item.md")
            for dep in preliminary_dependencies
        )
        inputs = safeio.snapshot_many(
            canonical, base_paths + dependency_paths, limit=_READ_LIMIT)
        by_path = {snapshot.relative: snapshot for snapshot in inputs}
        acceptance = parse_json_bytes(
            by_path[root / "acceptance.json"].data,
            label=f"{item_id}/acceptance.json")
        final_dependencies = _dependency_ids(acceptance)
        if final_dependencies != preliminary_dependencies:
            raise FeasibilityError(
                "acceptance dependencies changed during snapshot")

        item_meta = _item_metadata(
            by_path[root / "item.md"], expected=item_id)
        del item_meta  # Parsing and id agreement are the current-item checks.
        dependency_stages = {}
        for dep in final_dependencies:
            relative = PurePosixPath(".factory", "items", dep, "item.md")
            dependency_stages[dep] = _item_metadata(
                by_path[relative], expected=dep)["stage"]

        plan_bytes = by_path[root / "plan.md"].data
        spec_bytes = by_path[root / "spec.md"].data
        report = validate_acceptance(
            acceptance,
            item_id=item_id,
            spec_bytes=spec_bytes,
            plan_bytes=plan_bytes,
            dependency_stages=dependency_stages,
        )
        safeio.revalidate((config.file, *inputs))
        markers = plan_task_markers(plan_bytes)
        pending = tuple(marker.text for marker in markers if not marker.checked)
        if require_pending and not pending:
            raise FeasibilityError(
                "plan.md: implementation requires an unchecked task")
        return PlanSnapshot(
            report=_freeze(report),
            plan_bytes=plan_bytes,
            spec_bytes=spec_bytes,
            acceptance=_freeze(acceptance),
            pending_tasks=pending,
            pending_task_markers=markers,
            inputs=tuple(inputs),
        )
    except FeasibilityError:
        raise
    except (config_state.ConfigStateError, items.ItemError,
            safeio.SafeIOError, UnicodeError, OSError, ValueError) as exc:
        raise FeasibilityError(str(exc)) from exc


def inspect(repo, item_id: str, *, config) -> dict:
    """Return a deterministic, JSON-safe feasibility report without writes."""
    try:
        snapshot = require(repo, item_id, config=config)
        if snapshot is None:
            return _empty_report("disabled", item_id)
        report = _thaw(snapshot.report)
        report["handoff"] = worker_handoff(snapshot)
        return report
    except FeasibilityError as exc:
        report = _empty_report("fail", item_id)
        report["errors"] = list(exc.errors)
        return report


def worker_handoff(snapshot: PlanSnapshot, *, tasks=None) -> str:
    """Render exact inputs and only the current participant's write scope."""
    if not isinstance(snapshot, PlanSnapshot):
        raise FeasibilityError("worker_handoff requires a PlanSnapshot")
    acceptance = _thaw(snapshot.acceptance)
    current = acceptance["item"]
    if tasks is None:
        selected = snapshot.pending_tasks
    else:
        try:
            selected = tuple(tasks)
        except TypeError as exc:
            raise FeasibilityError("tasks must be an ordered iterable") from exc
        available = list(snapshot.pending_tasks)
        if any(type(task) is not str for task in selected):
            raise FeasibilityError("tasks must be pending task texts")
        for task in selected:
            try:
                available.remove(task)
            except ValueError as exc:
                raise FeasibilityError(
                    "tasks must be pending task texts") from exc
    owner = next(row for row in acceptance["participants"]
                 if row["item"] == current)
    payload = {
        "item": current,
        "cursor": snapshot.report["cursor"],
        "tasks": list(selected),
        "owned_paths": list(owner["owned_paths"]),
        "revision": acceptance["revision"],
        "delivery": acceptance["delivery"],
        "resources": acceptance["resources"],
        "interfaces": acceptance["interfaces"],
        "shared_gates": list(acceptance["delivery"]["shared_gates"]),
        "spec": snapshot.spec_bytes.decode("utf-8", errors="strict"),
        "plan": snapshot.plan_bytes.decode("utf-8", errors="strict"),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def prepare_dispatch(repo, item_id, *, config, owner_token, key=None,
                     tasks=None) -> DispatchSnapshot:
    """Validate an owned clean checkout and issue its durable plan ticket."""
    snapshot = require(repo, item_id, config=config)
    if snapshot is None:
        raise FeasibilityError("feasibility is disabled")
    if _snapshot_item_stage(snapshot, item_id) != "implement":
        raise FeasibilityError(f"{item_id} is not at stage implement")
    selected, records, selected_indexes = _select_task_records(snapshot, tasks)
    try:
        verified = ownership.verify(repo, item_id, owner_token)
    except ownership.OwnershipError as exc:
        raise FeasibilityError(str(exc)) from exc
    acceptance = _thaw(snapshot.acceptance)
    current = acceptance["item"]
    owner = next(row for row in acceptance["participants"]
                 if row["item"] == current)
    source_paths = set(owner["owned_paths"])
    source_paths.update(
        row["value"] for row in acceptance["resources"]
        if (row["kind"] == "path" and row["access"] == "modify" and
            row["provider"] == current))
    for relative in sorted(source_paths):
        _validate_checkout_path(verified.checkout, relative)
    head = _git_head(verified.checkout)
    handoff = worker_handoff(snapshot, tasks=selected)
    identity = {
        "head": head,
        "owner_sha256": verified.owner_sha256,
        "inputs": [[str(value.relative), value.sha256]
                   for value in snapshot.inputs],
        "tasks": records,
        "selected": selected_indexes,
    }
    if key is None:
        key = "plan-dispatch:" + sha256_bytes(
            _canonical_json(identity))
    metadata = {
        "version": 1,
        "head": head,
        "tasks": records,
        "selected": selected_indexes,
        "owned_paths": list(owner["owned_paths"]),
        "handoff": handoff,
        "event_ts": _snapshot_item_updated(snapshot, item_id),
    }
    try:
        ticket = control.issue_ticket(
            repo, item_id, kind="plan-dispatch", key=key,
            owner_token=owner_token, config=config,
            inputs=snapshot.inputs, metadata=metadata)
    except control.ControlError as exc:
        raise FeasibilityError(str(exc)) from exc
    revalidate_dispatch(ticket)
    return DispatchSnapshot(
        ticket=ticket, handoff=handoff, tasks=selected, head=head)


def revalidate_dispatch(ticket):
    """Require the ticket's exact clean checkout baseline before launch."""
    metadata = _validate_dispatch_ticket(ticket)
    try:
        control.revalidate_ticket(ticket)
    except control.ControlError as exc:
        raise FeasibilityError("concurrent_plan_change") from exc
    if _git_head(ticket.checkout) != metadata["head"]:
        raise FeasibilityError("history_rewrite")
    status = _git_run(
        ticket.checkout, "status", "--porcelain=v1", "-z").stdout
    if status:
        raise FeasibilityError("dirty_checkout")


def inspect_worker_scope(ticket) -> dict:
    """Inventory every Git-observable path since the ticket baseline."""
    baseline = None
    head = None
    paths = set()
    try:
        metadata = _validate_dispatch_ticket(ticket)
        control.revalidate_ticket(ticket)
        baseline = metadata["head"]
        head = _git_text(ticket.checkout, "rev-parse", "HEAD").strip()
        ancestor = _git_run(
            ticket.checkout, "merge-base", "--is-ancestor", baseline, head,
            allowed=(0, 1))
        if ancestor.returncode == 1:
            return _scope_report(
                "fail", "history_rewrite", baseline, head, paths)
        history = _git_text(
            ticket.checkout, "rev-list", "--reverse", "--parents",
            f"{baseline}..{head}")
        for line in history.splitlines():
            fields = line.split()
            if not fields:
                raise FeasibilityError("Git history returned a malformed record")
            commit, parents = fields[0], fields[1:]
            if not parents:
                raise FeasibilityError("Git history returned a parentless commit")
            for parent in parents:
                raw = _git_run(
                    ticket.checkout, "diff", "--name-status", "-z",
                    "-M", "-C", "--find-copies-harder",
                    parent, commit).stdout
                paths.update(_parse_name_status(raw))
        index = _git_run(
            ticket.checkout, "diff", "--cached", "--name-status", "-z",
            "-M", "-C", "--find-copies-harder").stdout
        working = _git_run(
            ticket.checkout, "diff", "--name-status", "-z", "-M", "-C",
            "--find-copies-harder").stdout
        untracked = _git_run(
            ticket.checkout, "ls-files", "--others", "--exclude-standard",
            "-z").stdout
        dirty = (_parse_name_status(index) |
                 _parse_name_status(working) |
                 _parse_paths(untracked))
        paths.update(dirty)
        outside = sorted(
            path for path in paths
            if not any(_contains(prefix, path)
                       for prefix in metadata["owned_paths"]))
        if outside:
            return _scope_report(
                "fail", "scope_violation", baseline, head, paths,
                violations=outside)
        if dirty:
            return _scope_report(
                "fail", "dirty_checkout", baseline, head, paths)
        return _scope_report("pass", None, baseline, head, paths)
    except (FeasibilityError, control.ControlError, OSError, UnicodeError,
            ValueError) as exc:
        return _scope_report(
            "fail", "scope_inspection_failed", baseline, head, paths,
            detail=str(exc))


def finalize_tasks(repo, item_id, *, ticket_id, owner_token):
    """Atomically tick ticket-selected markers and log final completion."""
    try:
        ticket = control.load_ticket(
            repo, item_id, ticket_id, owner_token=owner_token,
            revalidate_inputs=False)
        metadata = _validate_dispatch_ticket(ticket)
        operation_key = "plan-finalize:" + ticket.ticket_id
        adopted = control.adopt_operation(
            repo, item_id, kind="plan-finalize", key=operation_key)
        if adopted is not None:
            current_plan = safeio.snapshot_path(
                repo, PurePosixPath(
                    ".factory", "items", item_id, "plan.md"))
            remaining = pending_plan_tasks(current_plan.data)
            return {
                "status": "pass",
                "ticket_id": ticket.ticket_id,
                "cursor": remaining[0] if remaining else "COMPLETE",
                "completed": not remaining,
                "operation_id": adopted.operation_id,
            }
        plan_snapshot = _ticket_input(
            ticket, PurePosixPath(".factory", "items", item_id, "plan.md"))
        replacement = bytearray(plan_snapshot.data)
        selected_records = [
            metadata["tasks"][index]
            for index in metadata["selected"]]
        for record in selected_records:
            start, end = record["start"], record["end"]
            if (end != start + 1 or start < 0 or end > len(replacement) or
                    replacement[start:end] != b" "):
                raise FeasibilityError(
                    "ticket task marker does not match captured plan")
            replacement[start:end] = b"x"
        replacement = bytes(replacement)
        scope = inspect_worker_scope(ticket)
        if scope["status"] != "pass":
            reason = scope["reason"]
            if (reason == "scope_inspection_failed" and
                    "ticket no longer matches live state" in
                    scope.get("detail", "")):
                reason = "concurrent_plan_change"
            raise FeasibilityError(reason)
        result_relative = PurePosixPath(
            ".factory", "items", item_id, "worker", "result.json")
        result_snapshot = safeio.snapshot_path(repo, result_relative)
        result = parse_json_bytes(result_snapshot.data, label="worker/result.json")
        result_errors = validate_schema(
            result, initrepo.load_schema("result"), "worker/result.json")
        if result_errors:
            raise FeasibilityError(result_errors)
        if result["status"] != "done":
            raise FeasibilityError("worker result is not successful")
        if (type(result.get("test")) is dict and
                result["test"].get("passed") is False):
            raise FeasibilityError("worker result records failing tests")
        if result.get("dispatch_ticket") != ticket.ticket_id:
            raise FeasibilityError(
                "worker result does not match the dispatch ticket")
        log_snapshot = safeio.snapshot_path(
            repo, PurePosixPath(".factory", "items", item_id, "log.jsonl"),
            limit=control._LOG_IMAGE_LIMIT, allow_missing=True)
        remaining = pending_plan_tasks(replacement)
        events = ()
        if not remaining:
            events = ({
                "event": "implement.completed",
                "ts": metadata["event_ts"],
                "data": {
                    "tasks": len(selected_records),
                    "tests": _result_test_summary(result),
                    "backend": result["backend"],
                },
            },)
        request = {
            "version": 1,
            "ticket": ticket.ticket_id,
            "tasks": list(metadata["selected"]),
            "result_sha256": result_snapshot.sha256,
            "scope": scope,
        }
        prerequisites = _dedupe_snapshots((
            ticket.config.file,
            *(value for value in ticket.inputs
              if value.relative != plan_snapshot.relative),
            *ticket._artifacts,
            result_snapshot,
        ))
        receipt = control.commit_operation(
            repo, item_id, kind="plan-finalize", key=operation_key,
            request=request, prerequisites=prerequisites,
            replacements=((plan_snapshot, replacement),), events=events,
            log_snapshot=log_snapshot)
        return {
            "status": "pass",
            "ticket_id": ticket.ticket_id,
            "cursor": remaining[0] if remaining else "COMPLETE",
            "completed": not remaining,
            "operation_id": receipt.operation_id,
        }
    except FeasibilityError:
        raise
    except (control.ControlError, safeio.SafeIOError, OSError,
            UnicodeError, ValueError) as exc:
        message = str(exc)
        if "snapshot" in message or "live state" in message:
            message = "concurrent_plan_change"
        raise FeasibilityError(message) from exc


def rework_operation_key(source, source_snapshot, finding_ids):
    findings = _finding_ids(finding_ids)
    if source not in {"review", "verify", "assure"}:
        raise FeasibilityError("rework source must be review, verify, or assure")
    if not isinstance(source_snapshot, safeio.FileSnapshot):
        raise FeasibilityError("rework source snapshot is invalid")
    identity = {
        "source": source,
        "source_sha256": source_snapshot.sha256,
        "findings": list(findings),
    }
    return "feasibility-rework:" + sha256_bytes(_canonical_json(identity))


def prepare_rework_entry(repo, item_id, *, config, source, source_snapshot,
                         finding_ids, plan_proposal,
                         acceptance_proposal):
    """Prepare one atomic source-linked plan/acceptance rework transition."""
    from . import machine

    config_value = _config_value(config)
    if "feasibility" not in config_value["gates"]:
        raise FeasibilityError("feasibility is disabled")
    findings = _finding_ids(finding_ids)
    expected_source = _source_relative(item_id, source)
    canonical = config.file.root
    _require_snapshot(source_snapshot, canonical, expected_source,
                      "rework source")
    _require_snapshot(plan_proposal, canonical, None, "plan proposal")
    _require_snapshot(
        acceptance_proposal, canonical, None, "acceptance proposal")
    canonical_plan = PurePosixPath(
        ".factory", "items", item_id, "plan.md")
    canonical_acceptance = PurePosixPath(
        ".factory", "items", item_id, "acceptance.json")
    if plan_proposal.relative in {canonical_plan, canonical_acceptance}:
        raise FeasibilityError("plan proposal must not be a canonical artifact")
    if acceptance_proposal.relative in {canonical_plan, canonical_acceptance}:
        raise FeasibilityError(
            "acceptance proposal must not be a canonical artifact")

    current = validate_present(repo, item_id, config=config)
    if _snapshot_item_stage(current, item_id) != source:
        raise FeasibilityError(
            f"rework source {source!r} does not match the item stage")
    _validate_source_findings(source, source_snapshot, findings)
    proposed_plan = plan_proposal.data
    old_plan = _snapshot_input(current, canonical_plan)
    if pending_plan_tasks(old_plan.data):
        raise FeasibilityError(
            "rework requires a completed canonical plan")
    if not proposed_plan.startswith(old_plan.data):
        raise FeasibilityError(
            "rework plan proposal must append to the canonical plan")
    proposed_pending = pending_plan_tasks(proposed_plan)
    source_label = str(expected_source.relative_to(
        PurePosixPath(".factory", "items", item_id)))
    assignments = []
    for task in proposed_pending:
        matched = [finding for finding in findings
                   if _contains_identifier(task, finding)]
        if source_label not in task or len(matched) != 1:
            raise FeasibilityError(
                "each rework task must name its source artifact and exactly "
                "one finding id")
        assignments.extend(matched)
    if (len(proposed_pending) != len(findings) or
            sorted(assignments) != sorted(findings)):
        raise FeasibilityError(
            "rework requires exactly one unchecked task per finding")

    proposed_acceptance = parse_json_bytes(
        acceptance_proposal.data, label="acceptance proposal")
    dependencies = _dependency_ids(proposed_acceptance)
    dependency_paths = tuple(
        PurePosixPath(".factory", "items", dep, "item.md")
        for dep in dependencies)
    dependency_snapshots = safeio.snapshot_many(
        canonical, dependency_paths, limit=_READ_LIMIT)
    dependency_stages = {
        dep: _item_metadata(snapshot, expected=dep)["stage"]
        for dep, snapshot in zip(dependencies, dependency_snapshots)
    }
    spec_snapshot = _snapshot_input(
        current, PurePosixPath(
            ".factory", "items", item_id, "spec.md"))
    validate_acceptance(
        proposed_acceptance, item_id=item_id,
        spec_bytes=spec_snapshot.data, plan_bytes=proposed_plan,
        dependency_stages=dependency_stages)
    reason = proposed_acceptance["revision"]["reason"]
    if source not in reason or source_snapshot.sha256 not in reason:
        raise FeasibilityError(
            "acceptance revision reason must name source stage and digest")

    item_relative = PurePosixPath(
        ".factory", "items", item_id, "item.md")
    item_snapshot = _snapshot_input(current, item_relative)
    old_acceptance = _snapshot_input(current, canonical_acceptance)
    prerequisites = _dedupe_snapshots((
        *(value for value in current.inputs
          if value.relative not in {
              item_relative, canonical_plan, canonical_acceptance}),
        source_snapshot, plan_proposal, acceptance_proposal,
        *dependency_snapshots,
    ))
    safeio.revalidate((
        config.file, *current.inputs, source_snapshot, plan_proposal,
        acceptance_proposal, *dependency_snapshots))
    event_name = {
        "review": "review.rejected",
        "verify": "verify.rejected",
        "assure": "assure.rejected",
    }[source]
    timestamp = _snapshot_timestamp(source_snapshot)
    event = {
        "event": event_name,
        "ts": timestamp,
        "data": {
            "findings": list(findings),
            "source_sha256": source_snapshot.sha256,
        },
    }
    if source == "review":
        # New review receipts persist the reviewed commit, not a moving HEAD.
        # Keep it on the atomic rejection so the next pass uses the right delta.
        relative = PurePosixPath(
            ".factory", "items", item_id, "reviews", "selection-round-1.json")
        receipt_snapshot = safeio.snapshot_path(
            canonical, relative, limit=_READ_LIMIT, allow_missing=True)
        if isinstance(receipt_snapshot, safeio.FileSnapshot):
            prerequisites = _dedupe_snapshots((*prerequisites, receipt_snapshot))
            receipt = parse_json_bytes(receipt_snapshot.data, label=str(relative))
            diff = receipt.get("diff")
            head = diff.get("head") if isinstance(diff, dict) else None
            if (receipt.get("item") != item_id or receipt.get("round") != 1
                    or not isinstance(head, str)
                    or not re.fullmatch(r"[0-9a-f]{40,64}", head)):
                raise FeasibilityError("review selection receipt has no valid reviewed head")
            event["data"]["head"] = head
    operation_key = rework_operation_key(
        source, source_snapshot, findings)
    log_snapshot = None
    cost_answer_snapshot = None
    try:
        existing = control.operation_intent(
            repo, item_id, kind="implement-entry", key=operation_key)
        if existing is not None:
            stage_events = [
                candidate for candidate in existing["events"]
                if (candidate["event"] == "stage.advance" and
                    candidate.get("data", {}).get("from") == source and
                    candidate.get("data", {}).get("to") == "implement")]
            if len(stage_events) != 1:
                raise control.ControlRefusal(
                    "existing rework entry is invalid")
            timestamp = stage_events[0]["ts"]
            if existing.get("log_snapshot", {}).get("state") == "missing":
                log_snapshot = control._snapshot_from_record(
                    existing["log_snapshot"], {},
                    expected_repo=item_snapshot.root)
            answer_relative = str(PurePosixPath(
                ".factory", "items", item_id, "cost", "answer.md"))
            missing_answers = [
                record for record in existing["prerequisites"]
                if (record["relative"] == answer_relative and
                    record["state"] == "missing")]
            if len(missing_answers) > 1:
                raise control.ControlRefusal(
                    "existing rework entry is invalid")
            if missing_answers:
                cost_answer_snapshot = control._snapshot_from_record(
                    missing_answers[0], {},
                    expected_repo=item_snapshot.root)
        return machine.prepare_implement_entry(
            repo, item_id, operation_key=operation_key,
            config=config, prerequisites=prerequisites,
            replacements=((old_plan, proposed_plan),
                          (old_acceptance, acceptance_proposal.data)),
            events=(event,), item_snapshot=item_snapshot,
            log_snapshot=log_snapshot,
            cost_answer_snapshot=cost_answer_snapshot,
            timestamp=timestamp)
    except (machine.GateError, control.ControlError,
            config_state.ConfigStateError) as exc:
        raise FeasibilityError(str(exc)) from exc


def _select_task_records(snapshot, tasks):
    pending = [marker for marker in snapshot.pending_task_markers
               if not marker.checked]
    if tasks is None:
        selected_markers = pending
    elif type(tasks) is int and not isinstance(tasks, bool):
        if tasks < 1 or tasks > len(pending):
            raise FeasibilityError(
                f"task selection must be between 1 and {len(pending)}")
        selected_markers = [pending[tasks - 1]]
    else:
        try:
            requested = list(tasks)
        except TypeError as exc:
            raise FeasibilityError("task selection is invalid") from exc
        remaining = list(pending)
        selected_markers = []
        for text in requested:
            match = next((marker for marker in remaining
                          if marker.text == text), None)
            if match is None:
                raise FeasibilityError("task selection is not pending")
            selected_markers.append(match)
            remaining.remove(match)
    selected_ids = {id(marker) for marker in selected_markers}
    records = []
    selected_indexes = []
    for index, marker in enumerate(snapshot.pending_task_markers):
        records.append({
            "index": index,
            "text": marker.text,
            "start": marker.start,
            "end": marker.end,
            "checked": marker.checked,
        })
        if id(marker) in selected_ids:
            selected_indexes.append(index)
    return (tuple(marker.text for marker in selected_markers), records,
            selected_indexes)


def _finding_ids(values):
    try:
        values = tuple(values)
    except TypeError as exc:
        raise FeasibilityError("rework finding ids are invalid") from exc
    if (not values or any(type(value) is not str or not value or
                          "\n" in value or "\r" in value
                          for value in values) or
            len(values) != len(set(values))):
        raise FeasibilityError(
            "rework finding ids must be unique nonempty single-line strings")
    return values


def _contains_identifier(text, identifier):
    return re.search(
        rf"(?<![A-Za-z0-9_-]){re.escape(identifier)}"
        rf"(?![A-Za-z0-9_-])", text) is not None


def _source_relative(item_id, source):
    names = {
        "review": PurePosixPath("reviews", "synthesis.md"),
        "verify": PurePosixPath("verify.md"),
        "assure": PurePosixPath("assurance", "verdicts.json"),
    }
    if source not in names:
        raise FeasibilityError("rework source must be review, verify, or assure")
    return PurePosixPath(".factory", "items", item_id) / names[source]


def _require_snapshot(snapshot, root, relative, label):
    if (not isinstance(snapshot, safeio.FileSnapshot) or
            snapshot.root != root or
            (relative is not None and snapshot.relative != relative)):
        raise FeasibilityError(f"{label} snapshot is invalid")


def _snapshot_input(snapshot, relative):
    matches = [value for value in snapshot.inputs
               if value.relative == relative]
    if len(matches) != 1 or not isinstance(matches[0], safeio.FileSnapshot):
        raise FeasibilityError(f"snapshot input is missing: {relative}")
    return matches[0]


def _validate_source_findings(source, snapshot, findings):
    if source == "assure":
        value = parse_json_bytes(snapshot.data, label="assurance verdicts")
        schema_errors = validate_schema(
            value, initrepo.load_schema("assurance-verdicts"),
            "assurance verdicts")
        if schema_errors:
            raise FeasibilityError(schema_errors)
        regressions = {
            scenario["id"]
            for journey in value["journeys"]
            for scenario in journey["scenarios"]
            if (scenario["verdict"] == "fail" and
                scenario.get("attribution") == "regression")
        }
        missing = [finding for finding in findings
                   if finding not in regressions]
    else:
        try:
            text = snapshot.data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise FeasibilityError(
                f"{source} source is invalid UTF-8") from exc
        missing = [
            finding for finding in findings
            if not _contains_identifier(text, finding)
        ]
    if missing:
        raise FeasibilityError(
            f"rework findings are absent or non-regressions: {missing!r}")


def _snapshot_timestamp(snapshot):
    seconds = snapshot.file_identity[3] / 1_000_000_000
    return (datetime.fromtimestamp(seconds, timezone.utc)
            .isoformat(timespec="microseconds").replace("+00:00", "Z"))


def _canonical_json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True) + "\n").encode("utf-8")


def _validate_checkout_path(checkout, relative):
    errors = []
    _safe_path(relative, "checkout path", errors)
    if errors:
        raise FeasibilityError(errors)
    root = safeio._resolve_root(checkout)
    path = PurePosixPath(relative)
    chain = safeio._open_root_chain(root)
    try:
        for component in path.parts[:-1]:
            try:
                safeio._append_directory(chain, component)
            except safeio.SafeIOError as exc:
                if isinstance(exc.__cause__, FileNotFoundError):
                    safeio._require_absent(chain[-1].fd, component)
                    safeio._validate_chain(chain)
                    return
                raise
        try:
            details = os.stat(
                path.name, dir_fd=chain[-1].fd, follow_symlinks=False)
        except FileNotFoundError:
            safeio._require_absent(chain[-1].fd, path.name)
            safeio._validate_chain(chain)
            return
        if not (stat.S_ISREG(details.st_mode) or stat.S_ISDIR(details.st_mode)):
            raise FeasibilityError(
                f"checkout path crosses an unsafe entry: {relative}")
        safeio._validate_chain(chain)
    except safeio.SafeIOError as exc:
        raise FeasibilityError(
            f"checkout path is unsafe: {relative}: {exc}") from exc
    finally:
        safeio._close_chain(chain)


def _git_run(checkout, *args, allowed=(0,)):
    try:
        result = subprocess.run(
            ["git", *args], cwd=checkout, capture_output=True)
    except OSError as exc:
        raise FeasibilityError("Git scope inspection failed") from exc
    if result.returncode not in allowed:
        detail = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        raise FeasibilityError(
            "Git scope inspection failed" + (f": {detail}" if detail else ""))
    return result


def _git_text(checkout, *args):
    try:
        return _git_run(checkout, *args).stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise FeasibilityError("Git returned undecodable output") from exc


def _git_head(checkout):
    head = _git_text(checkout, "rev-parse", "HEAD").strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", head):
        raise FeasibilityError("Git returned an invalid HEAD")
    return head


def _parse_paths(raw):
    if not raw:
        return set()
    if not raw.endswith(b"\0"):
        raise FeasibilityError("Git returned a malformed path record")
    result = set()
    for field in raw[:-1].split(b"\0"):
        try:
            path = field.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise FeasibilityError("Git returned an undecodable path") from exc
        errors = []
        _safe_path(path, "Git path", errors)
        if errors:
            raise FeasibilityError(errors)
        result.add(path)
    return result


def _parse_name_status(raw):
    if not raw:
        return set()
    if not raw.endswith(b"\0"):
        raise FeasibilityError("Git returned a malformed name-status record")
    fields = raw[:-1].split(b"\0")
    index = 0
    paths = set()
    while index < len(fields):
        try:
            status = fields[index].decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise FeasibilityError("Git returned a malformed status") from exc
        index += 1
        count = 2 if status.startswith(("R", "C")) else 1
        if (not re.fullmatch(r"[ACDMRTUXB][0-9]*", status) or
                index + count > len(fields)):
            raise FeasibilityError("Git returned a malformed name-status record")
        paths.update(_parse_paths(b"\0".join(fields[index:index + count]) + b"\0"))
        index += count
    return paths


def _scope_report(status, reason, baseline, head, paths, *, violations=(),
                  detail=None):
    report = {
        "status": status,
        "reason": reason,
        "baseline_head": baseline,
        "head": head,
        "paths": sorted(paths),
        "violations": sorted(violations),
    }
    if detail:
        report["detail"] = detail
    return report


def _validate_dispatch_ticket(ticket):
    if (not isinstance(ticket, control.DurableTicket) or
            ticket.kind != "plan-dispatch"):
        raise FeasibilityError("ticket is not a plan dispatch")
    if (not isinstance(ticket.manifest, control.JSONSnapshot) or
            not isinstance(ticket.manifest.file, safeio.FileSnapshot)):
        raise FeasibilityError("plan dispatch ticket manifest is invalid")
    try:
        manifest = parse_json_bytes(
            ticket.manifest.file.data, label="plan dispatch ticket")
        control._validate_ticket_manifest(
            manifest, expected_repo=ticket.repo)
    except control.ControlError as exc:
        raise FeasibilityError(str(exc)) from exc
    if (manifest["ticket_id"] != ticket.ticket_id or
            manifest["item"] != ticket.item_id or
            manifest["kind"] != ticket.kind or
            manifest["key"] != ticket.key):
        raise FeasibilityError("plan dispatch ticket identity is invalid")
    metadata = manifest["metadata"]
    required = {"version", "head", "tasks", "selected", "owned_paths",
                "handoff", "event_ts"}
    if type(metadata) is not dict or set(metadata) != required:
        raise FeasibilityError("plan dispatch ticket metadata is invalid")
    if (metadata["version"] != 1 or
            type(metadata["head"]) is not str or
            not re.fullmatch(r"[0-9a-f]{40,64}", metadata["head"]) or
            type(metadata["handoff"]) is not str or
            not metadata["handoff"] or
            type(metadata["event_ts"]) is not str or
            not metadata["event_ts"]):
        raise FeasibilityError("plan dispatch ticket metadata is invalid")
    if (type(metadata["tasks"]) is not list or not metadata["tasks"] or
            type(metadata["selected"]) is not list or
            not metadata["selected"] or
            type(metadata["owned_paths"]) is not list or
            not metadata["owned_paths"]):
        raise FeasibilityError("plan dispatch ticket metadata is invalid")
    for index, record in enumerate(metadata["tasks"]):
        if (type(record) is not dict or
                set(record) != {"index", "text", "start", "end", "checked"} or
                record["index"] != index or
                type(record["text"]) is not str or not record["text"] or
                type(record["start"]) is not int or
                type(record["end"]) is not int or
                type(record["checked"]) is not bool):
            raise FeasibilityError("plan dispatch ticket tasks are invalid")
    if (any(type(index) is not int or index < 0 or
            index >= len(metadata["tasks"])
            for index in metadata["selected"]) or
            len(metadata["selected"]) != len(set(metadata["selected"]))):
        raise FeasibilityError("plan dispatch ticket selection is invalid")
    path_errors = []
    _path_set(metadata["owned_paths"], "ticket owned_paths", path_errors)
    if path_errors:
        raise FeasibilityError(path_errors)
    return metadata


def _ticket_input(ticket, relative):
    matches = [value for value in ticket.inputs
               if value.relative == relative]
    if len(matches) != 1 or not isinstance(matches[0], safeio.FileSnapshot):
        raise FeasibilityError(f"ticket input is missing: {relative}")
    return matches[0]


def _snapshot_item_updated(snapshot, item_id):
    relative = PurePosixPath(".factory", "items", item_id, "item.md")
    matches = [value for value in snapshot.inputs
               if value.relative == relative]
    if len(matches) != 1:
        raise FeasibilityError("item metadata input is missing")
    updated = _item_metadata(matches[0], expected=item_id).get("updated")
    if type(updated) is not str or not updated:
        raise FeasibilityError("item metadata has no update timestamp")
    return updated


def _snapshot_item_stage(snapshot, item_id):
    relative = PurePosixPath(".factory", "items", item_id, "item.md")
    matches = [value for value in snapshot.inputs
               if value.relative == relative]
    if len(matches) != 1:
        raise FeasibilityError("item metadata input is missing")
    stage = _item_metadata(matches[0], expected=item_id).get("stage")
    if type(stage) is not str or not stage:
        raise FeasibilityError("item metadata has no stage")
    return stage


def _result_test_summary(result):
    test = result.get("test")
    if not isinstance(test, dict):
        return "no test_command configured"
    prefix = "green: " if test.get("passed") else "RED: "
    return prefix + str(test.get("summary") or "")[:120]


def _dedupe_snapshots(values):
    result = []
    seen = set()
    for value in values:
        key = (value.root, value.relative)
        if key not in seen:
            result.append(value)
            seen.add(key)
    return tuple(result)


def _empty_report(status, item_id):
    return {
        "status": status,
        "item": item_id,
        "spec_sha256": None,
        "plan_structure_sha256": None,
        "cursor": None,
        "task": None,
        "owned_paths": [],
        "delivery": None,
        "errors": [],
        "handoff": None,
    }


def _config_value(config):
    if not isinstance(config, config_state.ConfigSnapshot):
        raise FeasibilityError("config must be a ConfigSnapshot")
    if config.file.relative != PurePosixPath(".factory/config.json"):
        raise FeasibilityError("config snapshot has the wrong path")
    value = parse_json_bytes(config.file.data, label="config.json")
    schema = initrepo.load_schema("config")
    errors = validate_schema(value, schema, "config")
    if errors:
        raise FeasibilityError(errors)
    config_state.revalidate(config)
    return value


def _dependency_ids(acceptance):
    if not isinstance(acceptance, dict):
        raise FeasibilityError("acceptance: expected object")
    rows = acceptance.get("dependencies")
    if not isinstance(rows, list):
        raise FeasibilityError("dependencies: must be an array")
    result = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise FeasibilityError(f"dependencies[{index}]: must be an object")
        dep = row.get("item")
        if not isinstance(dep, str) or not _ITEM.fullmatch(dep):
            raise FeasibilityError(
                f"dependencies[{index}].item: invalid format")
        result.append(dep)
    if len(result) != len(set(result)):
        raise FeasibilityError("dependencies: duplicate item ids")
    return tuple(result)


def _item_metadata(snapshot, *, expected):
    try:
        text = snapshot.data.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise FeasibilityError(f"{expected}/item.md: invalid UTF-8") from exc
    meta, _body = items.parse_item(text)
    if meta["id"] != expected:
        raise FeasibilityError(
            f"item path {expected!r} contains id {meta['id']!r}")
    return meta


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item)
                                 for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value):
    if isinstance(value, dict) or isinstance(value, MappingProxyType):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _validate_shape(value: Any) -> list[str]:
    errors = []
    root = {"version", "item", "spec_sha256", "plan_structure_sha256", "revision",
            "resume_cursor", "participants", "dependencies", "resources",
            "interfaces", "criteria", "tests", "delivery", "out_of_scope"}
    _closed(value, root, "$", errors)
    if errors:
        return errors
    if type(value["version"]) is not int or value["version"] != 1:
        errors.append("version: must be 1")
    _string(value["item"], "item", errors, pattern=_ITEM)
    _string(value["spec_sha256"], "spec_sha256", errors, pattern=_HASH)
    _string(value["plan_structure_sha256"], "plan_structure_sha256", errors, pattern=_HASH)
    _object(value["revision"], {"reason", "changed_sections"}, "revision", errors)
    if isinstance(value["revision"], dict):
        _string(value["revision"].get("reason"), "revision.reason", errors)
        _string_set(value["revision"].get("changed_sections"), "revision.changed_sections", errors)
    _object(value["resume_cursor"], {"strategy"}, "resume_cursor", errors)
    if isinstance(value["resume_cursor"], dict) and value["resume_cursor"].get("strategy") != "first-unchecked-task":
        errors.append("resume_cursor.strategy: must be 'first-unchecked-task'")
    specs = {
        "participants": ({"item", "owned_paths"}, False),
        "dependencies": ({"item", "relation", "provides"}, True),
        "resources": ({"id", "kind", "value", "access", "provider", "availability"}, False),
        "interfaces": ({"id", "owner", "consumers", "contract"}, True),
        "criteria": ({"id", "statement", "requires", "tests"}, False),
        "tests": ({"id", "purpose", "command", "covers"}, False),
    }
    for name, (keys, allow_empty) in specs.items():
        rows = value[name]
        if not isinstance(rows, list) or (not rows and not allow_empty):
            errors.append(f"{name}: must be {'an' if allow_empty else 'a non-'}empty array")
            continue
        for index, row in enumerate(rows):
            _object(row, keys, f"{name}[{index}]", errors)
    if errors:
        return errors
    for i, row in enumerate(value["participants"]):
        _string(row["item"], f"participants[{i}].item", errors, pattern=_ITEM)
        _path_set(row["owned_paths"], f"participants[{i}].owned_paths", errors)
    for i, row in enumerate(value["dependencies"]):
        _string(row["item"], f"dependencies[{i}].item", errors, pattern=_ITEM)
        _enum(row["relation"], {"delivered", "joint"}, f"dependencies[{i}].relation", errors)
        _string_set(row["provides"], f"dependencies[{i}].provides", errors)
    for i, row in enumerate(value["resources"]):
        prefix = f"resources[{i}]"
        for field in ("id", "value", "provider"):
            _string(row[field], f"{prefix}.{field}", errors)
        _enum(row["kind"], {"path", "interface", "runtime", "device", "route"}, f"{prefix}.kind", errors)
        _enum(row["access"], {"read", "modify", "use"}, f"{prefix}.access", errors)
        _enum(row["availability"], {"available", "unavailable"}, f"{prefix}.availability", errors)
        if row["kind"] == "path":
            _safe_path(row["value"], f"{prefix}.value", errors)
    for i, row in enumerate(value["interfaces"]):
        for field in ("id", "contract"):
            _string(row[field], f"interfaces[{i}].{field}", errors)
        _string(row["owner"], f"interfaces[{i}].owner", errors, pattern=_ITEM)
        _item_set(row["consumers"], f"interfaces[{i}].consumers", errors)
    for i, row in enumerate(value["criteria"]):
        for field in ("id", "statement"):
            _string(row[field], f"criteria[{i}].{field}", errors)
        _string_set(row["requires"], f"criteria[{i}].requires", errors)
        _string_set(row["tests"], f"criteria[{i}].tests", errors)
    for i, row in enumerate(value["tests"]):
        _string(row["id"], f"tests[{i}].id", errors)
        _enum(row["purpose"], {"component", "integrated", "full-wave", "release"}, f"tests[{i}].purpose", errors)
        _string_list(row["command"], f"tests[{i}].command", errors, unique=False)
        _string_set(row["covers"], f"tests[{i}].covers", errors)
    _object(value["delivery"], {"mode", "participants", "merge_order", "shared_gates"}, "delivery", errors)
    if isinstance(value["delivery"], dict):
        _enum(value["delivery"].get("mode"), {"solo", "component-only", "joint-staged"}, "delivery.mode", errors)
        _item_set(value["delivery"].get("participants"), "delivery.participants", errors)
        _item_set(value["delivery"].get("merge_order"), "delivery.merge_order", errors)
        _string_list(value["delivery"].get("shared_gates"), "delivery.shared_gates", errors,
                     allow_empty=True)
    _string_set(value["out_of_scope"], "out_of_scope", errors)
    return errors


def _validate_graph(a: dict, current: str, *, dependency_stages=None) -> list[str]:
    errors = []
    participants = _unique_rows(a["participants"], "item", "participant", errors)
    deps = _unique_rows(a["dependencies"], "item", "dependency", errors)
    resources = _unique_rows(a["resources"], "id", "resource", errors)
    interfaces = _unique_rows(a["interfaces"], "id", "interface", errors)
    criteria = _unique_rows(a["criteria"], "id", "criterion", errors)
    tests = _unique_rows(a["tests"], "id", "test", errors)
    graph_items = {current, *deps}
    if current in deps:
        errors.append("dependencies: current item cannot depend on itself")
    if current not in participants:
        errors.append("participants: current item is missing")
    for provider in {r["provider"] for r in resources.values()} - {"environment"}:
        if provider not in graph_items:
            errors.append(f"resource provider {provider!r} is not the current item or a dependency")
    for dep_id, dep in deps.items():
        actual = {rid for rid, resource in resources.items() if resource["provider"] == dep_id}
        if set(dep["provides"]) != actual:
            errors.append(f"dependency {dep_id!r} provides must equal {sorted(actual)!r}")
        if dep["relation"] == "delivered":
            if (dependency_stages is not None and
                    dependency_stages.get(dep_id) != "done"):
                errors.append(
                    f"delivered dependency {dep_id!r} must be at stage done")
            if dep_id in participants:
                errors.append(f"delivered dependency {dep_id!r} must not be a participant")
            if any(resources[rid]["access"] == "modify" for rid in actual):
                errors.append(f"delivered dependency {dep_id!r} cannot provide a modify resource")
        elif dep_id not in participants:
            errors.append(f"joint dependency {dep_id!r} must be a participant")
    joint = {key for key, dep in deps.items() if dep["relation"] == "joint"}
    expected_participants = {current, *joint}
    delivery = a["delivery"]
    if set(participants) != expected_participants:
        errors.append("participants: must equal the current item plus joint dependencies")
    if set(delivery["participants"]) != set(participants):
        errors.append("delivery.participants: must equal participant objects")
    if set(delivery["merge_order"]) != set(participants) or len(delivery["merge_order"]) != len(participants):
        errors.append("delivery.merge_order: must be an exact participant permutation")
    if delivery["mode"] in {"solo", "component-only"}:
        if set(participants) != {current} or joint:
            errors.append(f"delivery.mode {delivery['mode']!r} permits only the current item")
        if delivery["merge_order"] != [current]:
            errors.append(f"delivery.mode {delivery['mode']!r} requires merge_order [item]")
    else:
        if len(participants) < 2 or not joint:
            errors.append("joint-staged delivery requires at least one joint dependency")
    prefixes = []
    for owner, participant in participants.items():
        for path in participant["owned_paths"]:
            prefixes.append((owner, path))
    for left, (owner_a, path_a) in enumerate(prefixes):
        for owner_b, path_b in prefixes[left + 1:]:
            if owner_a != owner_b and _overlap(path_a, path_b):
                errors.append(f"owned path overlap: {owner_a}:{path_a} and {owner_b}:{path_b}")
    for rid, resource in resources.items():
        kind, access, provider = resource["kind"], resource["access"], resource["provider"]
        if provider == "environment" and kind not in {"runtime", "device"}:
            errors.append(f"resource {rid!r}: environment may provide only runtime/device")
        if kind == "path" and access not in {"read", "modify"}:
            errors.append(f"resource {rid!r}: path access must be read/modify")
        if kind != "path" and access != "use":
            errors.append(f"resource {rid!r}: non-path access must be use")
        if resource["availability"] != "available":
            errors.append(f"resource {rid!r}: required resource is unavailable")
        if kind == "path" and access == "modify" and provider in participants:
            owners = [p for p in participants[provider]["owned_paths"]
                      if _contains(p, resource["value"])]
            if len(owners) != 1:
                errors.append(f"resource {rid!r}: modify path must have exactly one provider-owned prefix")
            if provider != current and provider not in joint:
                errors.append(f"resource {rid!r}: external modification requires joint delivery")
    iface_resources = {}
    for rid, resource in resources.items():
        if resource["kind"] == "interface":
            iface_resources.setdefault(resource["value"], []).append((rid, resource))
    for iid, interface in interfaces.items():
        named = iface_resources.get(iid, [])
        if len(named) != 1:
            errors.append(f"interface {iid!r}: must be named by exactly one interface resource")
        elif named[0][1]["provider"] != interface["owner"]:
            errors.append(f"interface {iid!r}: resource provider must equal owner")
        if interface["owner"] not in graph_items:
            errors.append(f"interface {iid!r}: owner is outside item/dependency graph")
        for consumer in interface["consumers"]:
            if consumer not in graph_items:
                errors.append(f"interface {iid!r}: consumer {consumer!r} is outside graph")
    for name in set(iface_resources) - set(interfaces):
        errors.append(f"interface resource names undeclared interface {name!r}")
    used = set()
    shared = set(delivery["shared_gates"])
    for gate in shared:
        if gate not in tests:
            errors.append(f"delivery.shared_gates: dangling test {gate!r}")
        elif tests[gate]["purpose"] not in {"integrated", "full-wave", "release"}:
            errors.append(f"delivery.shared_gates: {gate!r} is not an integrated gate")
    if delivery["mode"] == "joint-staged" and not shared:
        errors.append("joint-staged delivery requires shared gates")
    for cid, criterion in criteria.items():
        required = set(criterion["requires"])
        named_tests = set(criterion["tests"])
        used |= required
        dangling_r = required - set(resources)
        dangling_t = named_tests - set(tests)
        for rid in sorted(dangling_r):
            errors.append(f"criterion {cid!r}: dangling resource {rid!r}")
        for tid in sorted(dangling_t):
            errors.append(f"criterion {cid!r}: dangling test {tid!r}")
        if not dangling_t:
            covered = set().union(*(set(tests[tid]["covers"]) for tid in named_tests))
            if not required <= covered:
                errors.append(f"criterion {cid!r}: named tests do not cover {sorted(required - covered)!r}")
        joint_required = {rid for rid in required & set(resources)
                          if resources[rid]["provider"] in joint}
        if joint_required and not dangling_t:
            local_gates = named_tests & shared
            local_coverage = set().union(*(set(tests[tid]["covers"]) for tid in local_gates)) if local_gates else set()
            if not local_gates or not required <= local_coverage:
                errors.append(f"criterion {cid!r}: criterion-local shared gates do not cover all resources")
        if delivery["mode"] == "component-only" and not dangling_t:
            if any(tests[tid]["purpose"] != "component" for tid in named_tests):
                errors.append(f"criterion {cid!r}: component-only criteria require component tests")
            if any(resources[rid]["kind"] in {"route", "device"} for rid in required if rid in resources):
                errors.append(f"criterion {cid!r}: component-only criteria cannot require route/device")
    for rid in set(resources) - used:
        errors.append(f"resource {rid!r}: not required by any criterion")
    for tid, test in tests.items():
        for rid in set(test["covers"]) - set(resources):
            errors.append(f"test {tid!r}: covers dangling resource {rid!r}")
    return errors


def _closed(value, keys, label, errors):
    if not isinstance(value, dict):
        errors.append(f"{label}: must be an object")
        return
    missing, extra = keys - set(value), set(value) - keys
    if missing:
        errors.append(f"{label}: missing keys {sorted(missing)!r}")
    if extra:
        errors.append(f"{label}: unknown keys {sorted(extra)!r}")


def _object(value, keys, label, errors):
    _closed(value, keys, label, errors)


def _string(value, label, errors, pattern=None):
    if not isinstance(value, str) or not value:
        errors.append(f"{label}: must be a non-empty string")
    elif pattern and not pattern.fullmatch(value):
        errors.append(f"{label}: invalid format")


def _enum(value, allowed, label, errors):
    if value not in tuple(allowed):
        errors.append(f"{label}: must be one of {sorted(allowed)!r}")


def _string_list(value, label, errors, *, unique=True, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty):
        errors.append(f"{label}: must be {'an' if allow_empty else 'a non-'}empty array")
        return
    if any(not isinstance(item, str) or not item for item in value):
        errors.append(f"{label}: entries must be non-empty strings")
    if (unique and all(isinstance(item, str) for item in value) and
            len(value) != len(set(value))):
        errors.append(f"{label}: duplicate entries")


def _string_set(value, label, errors):
    _string_list(value, label, errors)


def _item_set(value, label, errors):
    _string_set(value, label, errors)
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and not _ITEM.fullmatch(item):
                errors.append(f"{label}: invalid item {item!r}")


def _path_set(value, label, errors):
    _string_set(value, label, errors)
    if isinstance(value, list):
        for path in value:
            if isinstance(path, str):
                _safe_path(path, label, errors)


def _safe_path(path, label, errors):
    if not isinstance(path, str) or not path:
        errors.append(f"{label}: path must be non-empty")
        return
    parts = path.split("/")
    if (path.startswith("/") or "\\" in path or "\x00" in path or
            any(part in {"", ".", ".."} for part in parts) or ".git" in parts or
            str(PurePosixPath(path)) != path):
        errors.append(f"{label}: unsafe non-normalized repository path {path!r}")


def _unique_rows(rows, key, label, errors):
    result = {}
    for row in rows:
        value = row[key]
        if value in result:
            errors.append(f"duplicate {label} id {value!r}")
        else:
            result[value] = row
    return result


def _contains(prefix, path):
    return path == prefix or path.startswith(prefix + "/")


def _overlap(left, right):
    return _contains(left, right) or _contains(right, left)
