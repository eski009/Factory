"""Idempotent target-repo scaffolding and whole-tree validation.

init() only fills gaps — it never overwrites an existing file — and
never touches product code, CLAUDE.md, or existing docs. Spec §2.
"""

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import items, paths
from .validate import validate

_INSTALL_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = _INSTALL_ROOT / "templates" / "docs-factory"
SCHEMAS = _INSTALL_ROOT / "schemas"
LEDGERS = ("bids", "judgements", "reputation", "escapes")
LEDGER_SCHEMAS = {"bids": "escalation-bid", "judgements": "orchestrator-judgement",
                  "reputation": "reputation-event", "escapes": "escape"}
DEFAULT_CONFIG = {"version": 1, "merge": "auto", "gates": ["design"],
                  "research": {"depth": "web"},
                  "assure": {"attribution": False},
                  "approach_convergence": {"enabled": False}}


def load_schema(name):
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


SPEND_TOKEN_KEYS = ("input", "output", "total")
STRUCTURED_EVENT_SCHEMAS = {
    "test.wave": "test-wave",
    "activity.span": "activity-span",
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def spend_event_errors(data, path):
    """Spend-event contract: schema plus the two conditional rules the
    stdlib validator subset cannot express. Item spec 0004 §1, §4."""
    if not isinstance(data, dict):
        return [f"{path}: spend event data must be an object"]
    errors = validate(data, load_schema("spend-event"), path)
    provenance = data.get("provenance")
    tokens = data.get("tokens")
    if tokens is not None and provenance != "measured":
        errors.append(
            f"{path}: tokens present but provenance is not 'measured'")
    if provenance == "measured" and not (
            isinstance(tokens, dict)
            and any(key in tokens for key in SPEND_TOKEN_KEYS)):
        errors.append(
            f"{path}: measured spend event requires tokens with at least "
            "one of input/output/total")
    return errors


def spend_write_errors(data, path):
    """Validate a newly emitted spend event before append.

    Read validation intentionally accepts a missing scope for legacy ledgers;
    current writes must carry the origin-known discriminator.
    """
    errors = spend_event_errors(data, path)
    if isinstance(data, dict) and "scope" not in data:
        errors.append(
            f"{path}: new spend event requires scope 'leaf' or 'fork'")
    return errors


def _event_time(value):
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _relative_evidence_path(value):
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value \
            or value.startswith("/"):
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))


def evidence_file_digest(repo, relative):
    """Hash one contained regular file without following symlink components."""
    if not _relative_evidence_path(relative):
        return None, "must be a contained repository-relative path"
    parts = relative.split("/")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    file_flags = flags | getattr(os, "O_NOFOLLOW", 0) \
        | getattr(os, "O_NONBLOCK", 0)
    descriptors = []
    try:
        current = os.open(os.fspath(repo), directory_flags)
        descriptors.append(current)
        for component in parts[:-1]:
            current = os.open(component, directory_flags, dir_fd=current)
            descriptors.append(current)
        file_descriptor = os.open(parts[-1], file_flags, dir_fd=current)
        descriptors.append(file_descriptor)
        if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            return None, "is not a regular file"
        digest = hashlib.sha256()
        while True:
            chunk = os.read(file_descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        return digest.hexdigest(), None
    except (OSError, ValueError) as exc:
        return None, f"is missing, unreadable, or crosses a symlink ({exc})"
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _commit_resolves(repo, sha):
    try:
        subprocess.run(
            ["git", "-C", os.fspath(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def structured_event_errors(event_name, data, path, repo=None):
    """Validate the two closed FH-07 evidence event contracts.

    Unknown events deliberately return no errors, preserving the historical
    generic log surface.  Report-range and repository-identity checks belong
    to the read-side ledger because they require a selected Git run.
    """
    if not isinstance(event_name, str):
        return [f"{path}.event: must be a string"]
    schema_name = STRUCTURED_EVENT_SCHEMAS.get(event_name)
    if schema_name is None:
        return []
    if not isinstance(data, dict):
        return [f"{path}: {event_name} data must be an object"]
    errors = validate(data, load_schema(schema_name), path)
    started = _event_time(data.get("started_at"))
    finished = _event_time(data.get("finished_at"))
    if started is None:
        errors.append(f"{path}.started_at: invalid UTC timestamp")
    if finished is None:
        errors.append(f"{path}.finished_at: invalid UTC timestamp")
    if started is not None and finished is not None and finished < started:
        errors.append(f"{path}: finished_at precedes started_at")
    if event_name == "activity.span":
        return errors

    command = data.get("command")
    if isinstance(command, list) and not command:
        errors.append(f"{path}.command: must not be empty")
    tested_sha = data.get("tested_sha")
    green_sha = data.get("green_sha")
    shipping_ref = data.get("shipping_ref")
    if not isinstance(tested_sha, str) or not SHA_RE.fullmatch(tested_sha):
        errors.append(f"{path}.tested_sha: must be 40 lowercase hex characters")
    if data.get("result") == "passed":
        if green_sha != tested_sha:
            errors.append(f"{path}.green_sha: passed wave must equal tested_sha")
        tests = data.get("tests")
        if isinstance(tests, dict) and tests.get("failed") != 0:
            errors.append(f"{path}.tests.failed: passed wave must be zero")
    elif green_sha is not None:
        errors.append(f"{path}.green_sha: non-passed wave must be null")
    if shipping_ref is not None and (
            not isinstance(shipping_ref, str)
            or not SHA_RE.fullmatch(shipping_ref)):
        errors.append(f"{path}.shipping_ref: must be null or 40 lowercase hex characters")
    flows = data.get("flows")
    shipped = data.get("shipped_flows")
    flows_valid = isinstance(flows, list) and all(
        isinstance(value, str) for value in flows)
    shipped_valid = isinstance(shipped, list) and all(
        isinstance(value, str) for value in shipped)
    if flows_valid and len(flows) != len(set(flows)):
        errors.append(f"{path}.flows: duplicate flow id")
    if shipped_valid and len(shipped) != len(set(shipped)):
        errors.append(f"{path}.shipped_flows: duplicate flow id")
    if flows_valid and shipped_valid and not set(shipped).issubset(flows):
        errors.append(f"{path}.shipped_flows: must be a subset of flows")
    if shipping_ref is None and shipped:
        errors.append(f"{path}.shipped_flows: requires shipping_ref")
    if data.get("purpose") == "component" and (shipping_ref is not None or shipped):
        errors.append(f"{path}: component wave cannot claim shipping")
    screenshots = data.get("screenshots")
    if isinstance(screenshots, list):
        for index, screenshot in enumerate(screenshots):
            if not isinstance(screenshot, dict):
                continue
            if not _relative_evidence_path(screenshot.get("path")):
                errors.append(
                    f"{path}.screenshots[{index}].path: must be a contained "
                    "repository-relative path")
            if isinstance(flows, list) and screenshot.get("flow") not in flows:
                errors.append(
                    f"{path}.screenshots[{index}].flow: must be present in flows")
    if repo is not None and not errors:
        for field in ("tested_sha", "green_sha", "shipping_ref"):
            sha = data.get(field)
            if sha is not None and not _commit_resolves(repo, sha):
                errors.append(f"{path}.{field}: commit does not resolve")
        for index, screenshot in enumerate(data["screenshots"]):
            digest, error = evidence_file_digest(repo, screenshot["path"])
            if error:
                errors.append(f"{path}.screenshots[{index}].path: {error}")
            elif digest != screenshot["sha256"]:
                errors.append(f"{path}.screenshots[{index}].sha256: hash mismatch")
    return errors


def structured_event_id(event_name, data):
    if not isinstance(event_name, str):
        return None
    key = {"test.wave": "wave_id", "activity.span": "span_id"}.get(event_name)
    if key is None or not isinstance(data, dict):
        return None
    value = data.get(key)
    return (event_name, value) if isinstance(value, str) else None


def structured_id_conflict_errors(event_name, data, existing_events, path):
    identity = structured_event_id(event_name, data)
    if identity is None:
        return []
    for event in existing_events:
        if structured_event_id(event.get("event"), event.get("data")) == identity:
            return [f"{path}: duplicate {identity[0]} id {identity[1]!r}"]
    return []


def structured_log_duplicate_errors(numbered_events, path):
    grouped = {}
    for lineno, event in numbered_events:
        identity = structured_event_id(event.get("event"), event.get("data"))
        if identity is not None:
            grouped.setdefault(identity, []).append(lineno)
    errors = []
    for (event_name, event_id), lines in sorted(grouped.items()):
        if len(lines) < 2:
            continue
        for lineno in lines:
            errors.append(
                f"{path}:{lineno}: duplicate {event_name} id {event_id!r}")
    return errors


def init(repo, product=None, design_provider=None, designsync_project=None):
    repo = Path(repo)
    created = []
    for d in (paths.items_dir(repo), paths.ledgers_dir(repo),
              paths.factory_root(repo) / "runs", paths.docs_root(repo) / "packets",
              paths.docs_root(repo) / "packets" / "reports"):
        if not d.exists():
            d.mkdir(parents=True)
            created.append(str(d.relative_to(repo)))
    config_path = paths.config_path(repo)
    if not config_path.exists():
        config = dict(DEFAULT_CONFIG)
        if product:
            config["product"] = product
        if design_provider:
            config["design"] = {"provider": design_provider}
        if designsync_project:
            config["designsync_project"] = designsync_project
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        created.append(str(config_path.relative_to(repo)))
    elif design_provider or designsync_project:
        # Fill gaps in an older config, but never replace recorded choices.
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = None
        updated = []
        design = config.get("design") if isinstance(config, dict) else None
        if (design_provider and isinstance(config, dict)
                and (design is None or (isinstance(design, dict)
                                        and "provider" not in design))):
            config.setdefault("design", {})["provider"] = design_provider
            updated.append("design.provider")
        if (designsync_project and isinstance(config, dict)
                and "designsync_project" not in config):
            config["designsync_project"] = designsync_project
            updated.append("designsync_project")
        if updated:
            config_path.write_text(
                json.dumps(config, indent=2, sort_keys=True) + "\n",
                encoding="utf-8")
            created.append(
                f"{config_path.relative_to(repo)} (updated {', '.join(updated)})")
    for name in LEDGERS:
        ledger = paths.ledgers_dir(repo) / f"{name}.jsonl"
        if not ledger.exists():
            ledger.touch()
            created.append(str(ledger.relative_to(repo)))
    for src in sorted(TEMPLATES.rglob("*")):
        if not src.is_file():
            continue
        dest = paths.docs_root(repo) / src.relative_to(TEMPLATES)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest)
            created.append(str(dest.relative_to(repo)))
    return sorted(created)


def validate_tree(repo):
    repo = Path(repo)
    errors = []
    config_path = paths.config_path(repo)
    if not config_path.exists():
        return [f"{config_path.relative_to(repo)}: missing (run init)"]
    config_snapshot = None
    config_start_errors = len(errors)
    try:
        # errors="replace" (matching the log/ledger reads below): byte
        # corruption lands in the JSONDecodeError flag path, never a
        # UnicodeDecodeError traceback. Item spec 0009 §1.
        config = json.loads(
            config_path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(config, dict):
            errors.append("config.json: not an object")
        else:
            errors.extend(validate(config, load_schema("config"), "config"))
    except json.JSONDecodeError as exc:
        errors.append(f"config.json: invalid JSON ({exc})")
    if len(errors) == config_start_errors:
        from . import config_state
        try:
            config_snapshot = config_state.capture(repo)
        except config_state.ConfigStateError as exc:
            errors.append(str(exc))
    schema = load_schema("work-item")
    items_root = paths.items_dir(repo)
    if items_root.exists():
        for sub in sorted(items_root.iterdir()):
            item_md = sub / "item.md"
            meta = None
            schema_errors = []
            if item_md.exists():
                try:
                    meta, _ = items.parse_item(
                        item_md.read_text(encoding="utf-8", errors="replace"))
                    item_id = meta.get("id")
                    if not item_id:
                        # Use the .get value throughout — an id-less or
                        # empty-id frontmatter is flagged, never crashed
                        # on. Item spec 0009 §1.
                        errors.append(f"{sub.name}/item.md: missing id")
                    elif item_id != sub.name:
                        errors.append(
                            f"{sub.name}: id {item_id!r} does not match "
                            "directory name")
                    schema_errors = validate(meta, schema, sub.name)
                    errors.extend(schema_errors)
                except items.ItemError as exc:
                    errors.append(f"{sub.name}/item.md: {exc}")
            log_path = sub / "log.jsonl"
            log_events = []
            numbered_log_events = []
            log_valid = True
            if log_path.exists():
                try:
                    raw_lines = log_path.read_bytes().splitlines()
                except OSError as exc:
                    errors.append(f"{sub.name}/log.jsonl: unreadable ({exc})")
                    raw_lines = []
                    log_valid = False
                for lineno, raw_line in enumerate(raw_lines, 1):
                    if not raw_line.strip():
                        continue
                    try:
                        line = raw_line.decode("utf-8", errors="strict")
                        event = json.loads(line)
                    except UnicodeDecodeError:
                        errors.append(
                            f"{sub.name}/log.jsonl:{lineno}: "
                            "invalid JSON (invalid UTF-8)")
                        log_valid = False
                        continue
                    except json.JSONDecodeError:
                        errors.append(f"{sub.name}/log.jsonl:{lineno}: invalid JSON")
                        log_valid = False
                        continue
                    # Mirror logs.read_events_with_stats' well-formed-event
                    # rule (a parseable line is still corrupt when it is
                    # not a dict, or lacks "event"/"ts" — append_event
                    # writes both unconditionally) so the stage-
                    # reconciliation loop below only ever sees well-formed
                    # events. Item spec 0009 rework (review round 1).
                    if not isinstance(event, dict) or "event" not in event \
                            or "ts" not in event:
                        errors.append(f"{sub.name}/log.jsonl:{lineno}: invalid event")
                        log_valid = False
                        continue
                    log_events.append(event)
                    numbered_log_events.append((lineno, event))
                    if event.get("event") == "spend":
                        errors.extend(spend_event_errors(
                            event.get("data"), f"{sub.name}/log.jsonl:{lineno}"))
                    errors.extend(structured_event_errors(
                        event.get("event"), event.get("data"),
                        f"{sub.name}/log.jsonl:{lineno}", repo=repo))
                errors.extend(structured_log_duplicate_errors(
                    numbered_log_events, f"{sub.name}/log.jsonl"))
            for rel, schema_name in (("assurance/impact.json", "assurance-impact"),
                                     ("assurance/verdicts.json", "assurance-verdicts")):
                apath = sub / rel
                if apath.exists():
                    try:
                        data = json.loads(apath.read_text(
                            encoding="utf-8", errors="replace"))
                    except json.JSONDecodeError as exc:
                        errors.append(f"{sub.name}/{rel}: invalid JSON ({exc})")
                        continue
                    errors.extend(validate(data, load_schema(schema_name),
                                           f"{sub.name}/{rel}"))
            judgement_dir = sub / "approach-judgements"
            if judgement_dir.exists():
                judgement_schema = load_schema("approach-judgement")
                for judgement_path in sorted(judgement_dir.glob("*.json")):
                    rel = f"{sub.name}/approach-judgements/{judgement_path.name}"
                    try:
                        judgement = json.loads(judgement_path.read_text(
                            encoding="utf-8", errors="replace"))
                    except (OSError, UnicodeDecodeError) as exc:
                        errors.append(f"{rel}: unreadable ({exc})")
                        continue
                    except json.JSONDecodeError as exc:
                        errors.append(f"{rel}: invalid JSON ({exc})")
                        continue
                    errors.extend(validate(judgement, judgement_schema, rel))
            if meta is not None and not schema_errors and log_valid:
                acceptance_path = sub / "acceptance.json"
                acceptance_present = (
                    acceptance_path.exists() or acceptance_path.is_symlink())
                feasibility_enabled = bool(
                    config_snapshot is not None and
                    "feasibility" in config_snapshot.value["gates"])
                if (feasibility_enabled and meta["stage"] in {"plan", "implement"}
                        and not acceptance_present):
                    errors.append(
                        f"{sub.name}/acceptance.json: required while "
                        f"feasibility is enabled at stage {meta['stage']}")
                elif acceptance_present and config_snapshot is not None:
                    from . import feasibility
                    try:
                        feasibility.validate_present(
                            repo, sub.name, config=config_snapshot)
                    except feasibility.FeasibilityError as exc:
                        errors.extend(
                            f"{sub.name}/acceptance.json: {message}"
                            for message in exc.errors)
                expected = "idea"
                for event in log_events:
                    if event.get("event") == "stage.advance":
                        data = event.get("data")
                        if isinstance(data, dict):
                            expected = data.get("to", expected)
                if meta["stage"] != expected:
                    errors.append(
                        f"{sub.name}: stage {meta['stage']!r} does not match "
                        f"log (expected {expected!r})")
    graph_path = paths.docs_root(repo) / "journeys" / "graph.json"
    if graph_path.exists():
        try:
            graph = json.loads(graph_path.read_text(
                encoding="utf-8", errors="replace"))
            errors.extend(validate(graph, load_schema("journey-graph"),
                                   "journeys/graph.json"))
        except json.JSONDecodeError as exc:
            errors.append(f"journeys/graph.json: invalid JSON ({exc})")
    entries = {}
    clean = {}
    for name in LEDGERS:
        ledger = paths.ledgers_dir(repo) / f"{name}.jsonl"
        parsed = []
        line_errors = False
        if ledger.exists():
            for lineno, line in enumerate(ledger.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    errors.append(f"ledgers/{name}.jsonl:{lineno}: invalid JSON")
                    line_errors = True
                    continue
                msgs = validate(entry, load_schema(LEDGER_SCHEMAS[name]),
                                 f"ledgers/{name}.jsonl:{lineno}")
                if msgs:
                    errors.extend(msgs)
                    line_errors = True
                else:
                    parsed.append(entry)
                    if name == "escapes":
                        if entry.get("status") == "promoted" and not entry.get("promotion"):
                            errors.append(
                                f"ledgers/escapes.jsonl:{lineno}: promoted escape "
                                "missing promotion reference")
                            line_errors = True
                        if entry.get("status") == "open" and entry.get("promotion"):
                            errors.append(
                                f"ledgers/escapes.jsonl:{lineno}: open escape must "
                                "not carry a promotion")
                            line_errors = True
        entries[name] = parsed
        clean[name] = not line_errors
    if all(clean.values()):
        errors.extend(_check_ledger_consistency(entries))
    return errors


def _check_ledger_consistency(entries):
    from . import council

    errors = []
    bids_by_id = {bid["id"]: bid for bid in entries["bids"]}
    judgements = entries["judgements"]
    reputation = entries["reputation"]

    for ledger_name in ("bids", "judgements"):
        seen = set()
        for entry in entries[ledger_name]:
            entry_id = entry.get("id")
            if entry_id in seen:
                errors.append(f"ledgers/consistency: duplicate id {entry_id}")
            seen.add(entry_id)

    judgements_by_bid = {}
    for jdg in judgements:
        judgements_by_bid.setdefault(jdg["bid"], []).append(jdg)
    for bid_id, jdgs in judgements_by_bid.items():
        if len(jdgs) > 1:
            errors.append(f"ledgers/consistency: bid {bid_id} judged more than once")

    for jdg in judgements:
        if jdg["bid"] not in bids_by_id:
            errors.append(
                f"ledgers/consistency: judgement {jdg['id']} "
                f"references unknown bid {jdg['bid']}")
        if jdg["decision"] in council.AUTHORIZING and not (
                jdg.get("surface") and jdg.get("anchor")):
            errors.append(
                f"ledgers/consistency: judgement {jdg['id']} "
                f"({jdg['decision']}) missing surface/anchor")

    judgements_by_id = {jdg["id"]: jdg for jdg in judgements}
    reputation_by_judgement = {}
    for rep in reputation:
        reputation_by_judgement.setdefault(rep["judgement"], []).append(rep)
        if rep["judgement"] not in judgements_by_id:
            errors.append(
                f"ledgers/consistency: reputation event references "
                f"unknown judgement {rep['judgement']}")

    for jdg in judgements:
        reps = reputation_by_judgement.get(jdg["id"], [])
        if len(reps) != 1:
            errors.append(
                f"ledgers/consistency: judgement {jdg['id']} has "
                f"{len(reps)} reputation events (expected 1)")
            continue
        rep = reps[0]
        bid = bids_by_id.get(jdg["bid"])
        expected_delta = council.DECISION_DELTAS.get(jdg["decision"])
        if bid is None or rep["delta"] != expected_delta \
                or rep["agent"] != bid["agent"] or rep["topic"] != bid["topic"]:
            errors.append(
                f"ledgers/consistency: reputation for {jdg['id']} "
                f"has wrong delta/agent/topic")

    counts = {}
    for entry in entries.get("escapes", []):
        counts.setdefault(entry.get("id"), []).append(entry.get("status"))
    for esc_id, statuses in counts.items():
        if len(statuses) > 2:
            errors.append(f"ledgers/consistency: escape {esc_id} has "
                          f"{len(statuses)} entries (max 2: open then promoted)")
        elif statuses not in (["open"], ["open", "promoted"]):
            errors.append(f"ledgers/consistency: escape {esc_id} entries must "
                          "be open, then promoted")
    return errors
