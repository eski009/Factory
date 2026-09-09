"""Strict, explicitly revalidated snapshots of Factory configuration."""

import json
from dataclasses import dataclass

from . import initrepo, safeio
from .validate import validate


class ConfigStateError(Exception):
    """The repository configuration is missing, unsafe, or invalid."""


@dataclass(frozen=True)
class ConfigSnapshot:
    file: safeio.FileSnapshot
    value: dict


def _object_without_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def _reject_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def capture(repo) -> ConfigSnapshot:
    try:
        file_snapshot = safeio.snapshot_path(repo, ".factory/config.json")
        text = file_snapshot.data.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
        if not isinstance(value, dict):
            raise ValueError("configuration must be a JSON object")
        errors = validate(value, initrepo.load_schema("config"), "config")
        if errors:
            raise ValueError("; ".join(errors))
        safeio.revalidate(file_snapshot)
        return ConfigSnapshot(file=file_snapshot, value=value)
    except (OSError, UnicodeError, json.JSONDecodeError,
            safeio.SafeIOError, ValueError) as exc:
        raise ConfigStateError(f"invalid Factory configuration: {exc}") from exc


def enabled(snapshot: ConfigSnapshot, gate: str) -> bool:
    if not isinstance(snapshot, ConfigSnapshot):
        raise ConfigStateError("enabled requires a ConfigSnapshot")
    return gate in snapshot.value["gates"]


def revalidate(snapshot: ConfigSnapshot) -> None:
    if not isinstance(snapshot, ConfigSnapshot):
        raise ConfigStateError("revalidate requires a ConfigSnapshot")
    try:
        safeio.revalidate(snapshot.file)
    except (OSError, safeio.SafeIOError) as exc:
        raise ConfigStateError(
            f"Factory configuration changed after capture: {exc}") from exc
