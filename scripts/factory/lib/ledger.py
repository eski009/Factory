"""Read-only, run-bounded delivery and Factory evidence ledger.

Commit membership is derived from a pinned first-parent range.  Item and
timing observations use the endpoint commit timestamps, but remain explicitly
separate from Git delivery evidence.
"""

import json
import os
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from . import items, machine, paths


DEFAULT_ADMIN_PATHS = (".factory", "docs")
KNOWN_STAGES = frozenset(machine.STAGES) | frozenset(machine.SPECIAL)


class LedgerError(ValueError):
    pass


def _git(repo, *args, binary=False):
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(repo), *args], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise LedgerError(detail or f"git {' '.join(args)} failed") from exc
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", errors="strict").strip()


def _resolve_commit(repo, ref):
    if not isinstance(ref, str) or not ref:
        raise LedgerError("base and head must be non-empty commit references")
    return _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")


def _commit_info(repo, sha):
    raw = _git(repo, "show", "-s", "--format=%H%x00%P%x00%ct", sha)
    fields = raw.split("\0")
    if len(fields) != 3:
        raise LedgerError(f"could not read commit metadata for {sha}")
    return {
        "sha": fields[0],
        "parents": fields[1].split() if fields[1] else [],
        "committer_epoch": int(fields[2]),
    }


def _first_parent_range(repo, base, head):
    if base == head:
        return []
    chain = _git(repo, "rev-list", "--first-parent", head).splitlines()
    if base not in chain:
        raise LedgerError("base is not on head's first-parent chain")
    return _git(
        repo, "rev-list", "--first-parent", "--reverse", f"{base}..{head}"
    ).splitlines()


def _changed_paths(repo, sha, parents):
    if not parents:
        raw = _git(
            repo, "diff-tree", "--root", "--no-commit-id", "-r", "-z",
            "-M", "--name-status", sha, binary=True)
    else:
        raw = _git(
            repo, "diff-tree", "--no-commit-id", "-r", "-z", "-M",
            "--name-status", parents[0], sha, binary=True)
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    paths_out = []
    index = 0
    while index < len(fields):
        status_field = fields[index].decode("ascii", errors="strict")
        index += 1
        count = 2 if status_field.startswith(("R", "C")) else 1
        if index + count > len(fields):
            raise LedgerError(f"malformed diff-tree output for {sha}")
        for raw_path in fields[index:index + count]:
            paths_out.append(raw_path.decode("utf-8", errors="surrogateescape"))
        index += count
    return sorted(set(paths_out))


def _normalize_prefix(value, option):
    if not isinstance(value, str) or not value:
        raise LedgerError(f"{option} must be a non-empty repository-relative path")
    if "\\" in value or value.startswith("/"):
        raise LedgerError(f"invalid {option}: {value!r}")
    normalized = value.rstrip("/")
    if not normalized:
        raise LedgerError(f"invalid {option}: {value!r}")
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise LedgerError(f"invalid {option}: {value!r}")
    return PurePosixPath(normalized).as_posix()


def _matches(path, prefix):
    return path == prefix or path.startswith(prefix + "/")


def _prefixes(product_paths, admin_paths):
    products = tuple(sorted({_normalize_prefix(p, "product path")
                             for p in product_paths}))
    admins = tuple(sorted({_normalize_prefix(p, "admin path")
                           for p in (*DEFAULT_ADMIN_PATHS, *admin_paths)}))
    for product in products:
        for admin in admins:
            if _matches(product, admin) or _matches(admin, product):
                raise LedgerError(
                    f"product/admin path prefixes overlap: {product!r} and {admin!r}")
    return products, admins


def _classify(changed, products, admins):
    categories = set()
    for path in changed:
        if any(_matches(path, prefix) for prefix in products):
            categories.add("product")
        elif any(_matches(path, prefix) for prefix in admins):
            categories.add("admin")
        else:
            categories.add("unclassified")
    if categories == {"product"}:
        classification = "product-only"
    elif categories == {"admin"}:
        classification = "admin-only"
    elif len(categories) >= 2:
        classification = "mixed"
    else:
        classification = "other"
    return classification, "product" in categories


def _available(value):
    return {"status": "available", "value": value}


def _unavailable(reason):
    return {"status": "unavailable", "value": None, "reason": reason}


def _parse_ts(value):
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _fmt_ts(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_item_events(repo, item_id, warnings):
    log_path = paths.item_dir(repo, item_id) / "log.jsonl"
    if not os.path.lexists(log_path):
        return [], None
    try:
        if not stat.S_ISREG(log_path.lstat().st_mode):
            raise OSError("log.jsonl is not a regular file")
        raw_lines = log_path.read_bytes().splitlines()
    except (OSError, UnicodeError) as exc:
        return None, f"{item_id}: log is unreadable ({exc})"
    events = []
    corrupt = 0
    for raw_line in raw_lines:
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            corrupt += 1
            continue
        if (not isinstance(event, dict) or "event" not in event
                or "ts" not in event):
            corrupt += 1
            continue
        events.append(event)
    if corrupt:
        warnings.append(f"{item_id}: {corrupt} corrupt log line(s) excluded")
    return events, None


def _valid_stage_events(events, item_id, warnings):
    stage_events = []
    previous = None
    valid_order = True
    invalid = False
    for ordinal, event in enumerate(events, 1):
        if event.get("event") != "stage.advance":
            continue
        stamp = _parse_ts(event.get("ts"))
        data = event.get("data")
        if (stamp is None or not isinstance(data, dict)
                or not isinstance(data.get("to"), str)
                or data["to"] not in KNOWN_STAGES
                or ("from" in data
                    and (not isinstance(data["from"], str)
                         or data["from"] not in KNOWN_STAGES))):
            warnings.append(f"{item_id}: invalid stage.advance at event {ordinal}")
            invalid = True
            continue
        if previous is not None and stamp < previous:
            valid_order = False
        previous = stamp
        stage_events.append((stamp, data.get("from"), data["to"], ordinal))
    if not valid_order:
        warnings.append(f"{item_id}: out-of-order stage timestamps")
    return stage_events, valid_order and not invalid


def _timing_stage_data(meta, events, stage_events, stage_order_valid):
    item_id = meta["id"]
    created_events = [(ordinal, event) for ordinal, event in enumerate(events, 1)
                      if event.get("event") == "item.created"]
    if len(created_events) != 1:
        return None, f"{item_id}: item.created boundary is missing or duplicated"
    created_ordinal, created_event = created_events[0]
    created = _parse_ts(created_event.get("ts"))
    if created is None:
        return None, f"{item_id}: invalid item.created timestamp"
    if not stage_order_valid:
        return None, f"{item_id}: stage event order is unavailable"
    current = "idea"
    timing_events = []
    for stamp, declared_from, to_stage, ordinal in stage_events:
        if ordinal < created_ordinal or stamp < created:
            return None, f"{item_id}: stage event predates item.created"
        repeated_done = current == "done" and to_stage == "done"
        if (declared_from is not None and declared_from != current
                and not repeated_done):
            return None, (
                f"{item_id}: stage history expected from {current!r}, "
                f"got {declared_from!r}")
        timing_events.append((stamp, declared_from or current, to_stage))
        current = to_stage
    if current != meta.get("stage"):
        return None, (
            f"{item_id}: stage history ends at {current!r}, "
            f"metadata is {meta.get('stage')!r}")
    return {"created": created, "events": timing_events}, None


def _timing_rows(item_id, stage_data, start, end):
    created = stage_data["created"]
    events = stage_data["events"]
    if created > end:
        return []
    current = "idea"
    cursor = created
    rows = []
    for stamp, _from, to in events:
        if stamp > end:
            break
        interval_start = max(cursor, start)
        if current != "done" and stamp > interval_start:
            rows.append({
                "item": item_id,
                "stage": current,
                "category": "waiting" if current in machine.SPECIAL else
                            ("review" if current == "review" else "active"),
                "start": _fmt_ts(interval_start),
                "end": _fmt_ts(stamp),
                "seconds": int((stamp - interval_start).total_seconds()),
                "provenance": "proxy",
                "clipped": cursor < start,
            })
        current = to
        cursor = stamp
    interval_start = max(cursor, start)
    if current != "done" and end > interval_start:
        rows.append({
            "item": item_id,
            "stage": current,
            "category": "waiting" if current in machine.SPECIAL else
                        ("review" if current == "review" else "active"),
            "start": _fmt_ts(interval_start),
            "end": _fmt_ts(end),
            "seconds": int((end - interval_start).total_seconds()),
            "provenance": "proxy",
            "clipped": cursor < start,
        })
    return rows


class _DuplicateKey(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_aliases(repo, known_items, warnings):
    alias_path = paths.factory_root(repo) / "ledger-aliases.json"
    if not os.path.lexists(alias_path):
        return _available({"count": 0, "rows": []})
    try:
        mode = alias_path.lstat().st_mode
        if not stat.S_ISREG(mode):
            raise LedgerError("alias file must be a regular file, not a symlink")
        data = json.loads(alias_path.read_text(encoding="utf-8"),
                          object_pairs_hook=_unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError,
            _DuplicateKey, LedgerError) as exc:
        reason = f"ledger-aliases.json: {exc}"
        warnings.append(reason)
        return _unavailable(reason)
    if not isinstance(data, dict):
        reason = "ledger-aliases.json: root must be an object"
        warnings.append(reason)
        return _unavailable(reason)
    rows = []
    for alias_id in sorted(data):
        value = data[alias_id]
        if (not isinstance(alias_id, str) or not alias_id
                or not isinstance(value, dict)
                or set(value) - {"item", "status"}
                or not isinstance(value.get("item"), str)
                or ("status" in value and value["status"] is not None
                    and not isinstance(value["status"], str))):
            reason = f"ledger-aliases.json: invalid alias {alias_id!r}"
            warnings.append(reason)
            return _unavailable(reason)
        target = value["item"]
        known = target in known_items
        if not known:
            warnings.append(f"alias {alias_id!r}: unknown item {target!r}")
        rows.append({"alias": alias_id, "item": target,
                     "status": value.get("status"), "known_item": known})
    return _available({"count": len(rows), "rows": rows})


def summarize(repo, base, head, product_paths=(), admin_paths=(),
              synthetic=False):
    """Build the Task-1 ledger data without modifying ``repo``."""
    repo = Path(repo)
    base_sha = _resolve_commit(repo, base)
    head_sha = _resolve_commit(repo, head)
    commit_shas = _first_parent_range(repo, base_sha, head_sha)
    products, admins = _prefixes(tuple(product_paths), tuple(admin_paths))
    base_info = _commit_info(repo, base_sha)
    head_info = _commit_info(repo, head_sha)
    interval_ok = base_info["committer_epoch"] <= head_info["committer_epoch"]
    warnings = []
    if not interval_ok:
        warnings.append("commit endpoint timestamps are reversed; time observations unavailable")

    commit_rows = []
    for sha in commit_shas:
        info = _commit_info(repo, sha)
        changed = _changed_paths(repo, sha, info["parents"])
        if products:
            classification, has_product = _classify(changed, products, admins)
        else:
            classification, has_product = "unavailable", None
        commit_rows.append({
            **info,
            "paths": changed,
            "classification": classification,
            "is_merge": len(info["parents"]) > 1,
            "has_product_path": has_product,
        })
    if products:
        product_merges = [r["sha"] for r in commit_rows
                          if r["is_merge"] and r["has_product_path"]]
        admin_only = [r["sha"] for r in commit_rows
                      if r["classification"] == "admin-only"]
        commits_status = "available"
        product_metric = _available(
            {"count": len(product_merges), "shas": product_merges})
        admin_metric = _available(
            {"count": len(admin_only), "shas": admin_only})
    else:
        commits_status = "unavailable"
        reason = "at least one product path is required for classification"
        product_metric = _unavailable(reason)
        admin_metric = _unavailable(reason)

    metas, item_errors = items.list_items_safe(repo)
    metas = sorted(metas, key=lambda value: value["id"])
    warnings.extend(f"unreadable item: {error}" for error in item_errors)
    current_rows = [{"id": meta["id"], "stage": meta["stage"],
                     "kind": meta["kind"]} for meta in metas]
    by_stage = {}
    for row in current_rows:
        by_stage[row["stage"]] = by_stage.get(row["stage"], 0) + 1

    completion_events = []
    completion_ids = set()
    timing_rows = []
    timing_unavailable = []
    if interval_ok:
        start = datetime.fromtimestamp(base_info["committer_epoch"], timezone.utc)
        end = datetime.fromtimestamp(head_info["committer_epoch"], timezone.utc)
        for meta in metas:
            events, read_error = _read_item_events(
                repo, meta["id"], warnings)
            if read_error:
                warnings.append(read_error)
                timing_unavailable.append(
                    {"item": meta["id"], **_unavailable(read_error)})
                continue
            stage_events, stage_order_valid = _valid_stage_events(
                events, meta["id"], warnings)
            if stage_order_valid:
                for stamp, from_stage, to_stage, _ordinal in stage_events:
                    if not (start < stamp <= end and to_stage == "done"):
                        continue
                    completion_ids.add(meta["id"])
                    completion_events.append({
                        "item": meta["id"], "ts": _fmt_ts(stamp),
                        "from": from_stage, "to": to_stage,
                    })
            stage_data, timing_error = _timing_stage_data(
                meta, events, stage_events, stage_order_valid)
            if timing_error:
                warnings.append(timing_error)
                timing_unavailable.append(
                    {"item": meta["id"], **_unavailable(timing_error)})
                continue
            timing_rows.extend(_timing_rows(meta["id"], stage_data, start, end))
        completions = _available({
            "count": len(completion_ids),
            "items": sorted(completion_ids),
            "events": completion_events,
        })
        timing = {"status": "available", "rows": timing_rows,
                  "unavailable": timing_unavailable}
    else:
        reason = "commit endpoint timestamps are reversed"
        completions = _unavailable(reason)
        timing = {**_unavailable(reason), "rows": [], "unavailable": []}

    known_items = {meta["id"] for meta in metas}
    aliases = _read_aliases(repo, known_items, warnings)
    return {
        "run": {
            "base": base_sha,
            "head": head_sha,
            "commit_range": f"{base_sha}..{head_sha}",
            "base_epoch": base_info["committer_epoch"],
            "head_epoch": head_info["committer_epoch"],
            "observation_interval": "available" if interval_ok else "unavailable",
            "synthetic": bool(synthetic),
        },
        "commits": {
            "status": commits_status,
            "rows": commit_rows,
            "product_changing_merges": product_metric,
            "admin_only_commits": admin_metric,
        },
        "factory_items": {
            "current": _available({"count": len(current_rows),
                                   "by_stage": dict(sorted(by_stage.items())),
                                   "items": current_rows,
                                   "unreadable": len(item_errors)}),
            "completions": completions,
        },
        "aliases": aliases,
        "timing": timing,
        "warnings": sorted(warnings),
        "limits": [
            "commit counts are inventory, not speed or throughput",
            "timestamp-selected item observations are not Git delivery attribution",
            "proxy stage intervals are elapsed time, not active effort",
            "timing categories may overlap and must not be summed",
        ],
    }
