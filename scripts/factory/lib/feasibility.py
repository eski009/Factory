"""Pure acceptance-plan parsing and feasibility graph validation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Any

from . import config_state, initrepo, items, safeio
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
    try:
        config_value = _config_value(config)
        canonical = config.file.root
        try:
            requested = Path(repo).resolve(strict=True)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise FeasibilityError("repository is missing or unsafe") from exc
        if requested != canonical:
            raise FeasibilityError("configuration belongs to another repository")
        if "feasibility" not in config_value["gates"]:
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
        if not pending:
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
        if (any(type(task) is not str for task in selected) or
                len(set(selected)) != len(selected) or
                any(task not in snapshot.pending_tasks for task in selected)):
            raise FeasibilityError("tasks must be unique pending task texts")
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
    gates = schema["properties"]["gates"]["items"]["enum"]
    if "feasibility" not in gates:
        gates.append("feasibility")
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
