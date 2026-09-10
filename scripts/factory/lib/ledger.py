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

from . import initrepo, items, machine, paths


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


def _structured_events(repo, events, item_id, event_name, id_key, warnings):
    occurrences = {}
    valid = {}
    for ordinal, event in enumerate(events, 1):
        if event.get("event") != event_name:
            continue
        data = event.get("data")
        event_id = data.get(id_key) if isinstance(data, dict) else None
        if isinstance(event_id, str):
            occurrences.setdefault(event_id, []).append(ordinal)
        errors = initrepo.structured_event_errors(
            event_name, data, f"{item_id}/log.jsonl:{ordinal}", repo=repo)
        if errors:
            warnings.extend(errors)
            continue
        valid[ordinal] = data
    duplicate_ids = {event_id for event_id, ordinals in occurrences.items()
                     if len(ordinals) > 1}
    for event_id in sorted(duplicate_ids):
        warnings.append(
            f"{item_id}: duplicate {id_key} {event_id!r}; all occurrences excluded")
    rows = []
    for ordinal in sorted(valid):
        data = valid[ordinal]
        if data[id_key] not in duplicate_ids:
            rows.append((ordinal, data))
    return rows


def _wave_rows(repo, item_id, events, start, end, range_shas, warnings):
    rows = []
    for ordinal, data in _structured_events(
            repo, events, item_id, "test.wave", "wave_id", warnings):
        try:
            tested_sha = _resolve_commit(repo, data["tested_sha"])
        except LedgerError:
            warnings.append(
                f"{item_id}/log.jsonl:{ordinal}: tested_sha does not resolve")
            continue
        shipping_ref = data["shipping_ref"]
        if shipping_ref is not None:
            try:
                shipping_ref = _resolve_commit(repo, shipping_ref)
            except LedgerError:
                warnings.append(
                    f"{item_id}/log.jsonl:{ordinal}: shipping_ref does not resolve")
                continue
            if shipping_ref not in range_shas:
                warnings.append(
                    f"{item_id}/log.jsonl:{ordinal}: shipping_ref is outside base..head")
                continue
        screenshots = []
        screenshot_error = False
        for screenshot in data["screenshots"]:
            digest, error = initrepo.evidence_file_digest(
                repo, screenshot["path"])
            if error:
                warnings.append(
                    f"{item_id}/log.jsonl:{ordinal}: screenshot "
                    f"{screenshot['path']!r} {error}")
                screenshot_error = True
                continue
            if digest != screenshot["sha256"]:
                warnings.append(
                    f"{item_id}/log.jsonl:{ordinal}: screenshot "
                    f"{screenshot['path']!r} hash mismatch")
                screenshot_error = True
                continue
            screenshots.append({**screenshot, "current_sha256": digest,
                                "hash_matches": True})
        if screenshot_error:
            continue
        finished = _parse_ts(data["finished_at"])
        if not (start < finished <= end):
            continue
        started = _parse_ts(data["started_at"])
        if data["result"] != "passed":
            delivery_status = "not-green"
        elif data["purpose"] == "component":
            delivery_status = "non-production"
        elif tested_sha in range_shas:
            delivery_status = "delivery-bound"
        else:
            delivery_status = "candidate"
        rows.append({
            **data,
            "item": item_id,
            "tested_sha": tested_sha,
            "shipping_ref": shipping_ref,
            "screenshots": screenshots,
            "duration_seconds": int((finished - started).total_seconds()),
            "boundary_crossing": started < start,
            "delivery_status": delivery_status,
            "provenance": "measured",
        })
    return rows


def _span_rows(repo, item_id, events, start, end, warnings):
    rows = []
    structured = _structured_events(
        repo, events, item_id, "activity.span", "span_id", warnings)
    if start >= end:
        return rows
    for _ordinal, data in structured:
        started = _parse_ts(data["started_at"])
        finished = _parse_ts(data["finished_at"])
        if finished <= start or started > end:
            continue
        clipped_start = max(started, start)
        clipped_end = min(finished, end)
        rows.append({
            **data,
            "item": item_id,
            "reported_start": _fmt_ts(clipped_start),
            "reported_end": _fmt_ts(clipped_end),
            "seconds": int((clipped_end - clipped_start).total_seconds()),
            "clipped": clipped_start != started or clipped_end != finished,
            "provenance": "measured",
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
    wave_rows = []
    span_rows = []
    event_cache = {}
    event_read_errors = {}
    for meta in metas:
        events, read_error = _read_item_events(repo, meta["id"], warnings)
        if read_error:
            warnings.append(read_error)
            event_read_errors[meta["id"]] = read_error
        else:
            event_cache[meta["id"]] = events
    if interval_ok:
        start = datetime.fromtimestamp(base_info["committer_epoch"], timezone.utc)
        end = datetime.fromtimestamp(head_info["committer_epoch"], timezone.utc)
        for meta in metas:
            read_error = event_read_errors.get(meta["id"])
            if read_error:
                timing_unavailable.append(
                    {"item": meta["id"], **_unavailable(read_error)})
                continue
            events = event_cache[meta["id"]]
            stage_events, stage_order_valid = _valid_stage_events(
                events, meta["id"], warnings)
            wave_rows.extend(_wave_rows(
                repo, meta["id"], events, start, end, set(commit_shas), warnings))
            span_rows.extend(_span_rows(
                repo, meta["id"], events, start, end, warnings))
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
        categories = {}
        for category in ("test", "review", "admin"):
            ids = [row["span_id"] for row in span_rows
                   if row["category"] == category]
            categories[category] = (_available(ids) if ids else
                                    {"status": "unmeasured", "value": None})
        timing = {"status": "available", "rows": timing_rows,
                  "unavailable": timing_unavailable,
                  "activity_spans": span_rows,
                  "category_status": categories}
        waves = _available({"rows": wave_rows})
    else:
        reason = "commit endpoint timestamps are reversed"
        start = datetime.fromtimestamp(base_info["committer_epoch"], timezone.utc)
        end = datetime.fromtimestamp(head_info["committer_epoch"], timezone.utc)
        for meta in metas:
            events = event_cache.get(meta["id"])
            if events is None:
                continue
            _wave_rows(
                repo, meta["id"], events, start, end, set(commit_shas), warnings)
            _span_rows(repo, meta["id"], events, start, end, warnings)
        completions = _unavailable(reason)
        timing = {**_unavailable(reason), "rows": [], "unavailable": [],
                  "activity_spans": [], "category_status": {}}
        waves = _unavailable(reason)

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
        "waves": waves,
        "warnings": sorted(warnings),
        "limits": [
            "commit counts are inventory, not speed or throughput",
            "timestamp-selected item observations are not Git delivery attribution",
            "proxy stage intervals are elapsed time, not active effort",
            "timing categories may overlap and must not be summed",
        ],
    }


def _field_text(value):
    """Keep one logical rendered field on one physical text-output line."""
    if value is None:
        return "UNAVAILABLE"
    return json.dumps(str(value), ensure_ascii=True)[1:-1]


def _list_text(values):
    return ",".join(_field_text(value) for value in values) if values else "none"


def _unavailable_text(label, metric):
    return (f"[unmeasured] {_field_text(label)}: UNAVAILABLE "
            f"reason={_field_text(metric.get('reason', 'not available'))}")


def render_text(summary):
    """Render the ledger without combining inventories or timing classes."""
    run = summary["run"]
    synthetic = " synthetic=true" if run.get("synthetic") else ""
    lines = [f"[inventory] run: {run['commit_range']}{synthetic}"]

    commits = summary["commits"]
    for key, label in (
            ("product_changing_merges", "product-changing merges"),
            ("admin_only_commits", "admin-only commits")):
        metric = commits[key]
        if metric["status"] != "available":
            lines.append(_unavailable_text(label, metric))
            continue
        value = metric["value"]
        lines.append(
            f"[inventory] {label}: count={value['count']} "
            f"shas={_list_text(value['shas'])}")

    current = summary["factory_items"]["current"]["value"]
    stages = ",".join(
        f"{_field_text(stage)}={count}"
        for stage, count in current["by_stage"].items()
    ) or "none"
    lines.append(
        f"[inventory] Factory items current cumulative: count={current['count']} "
        f"by_stage={stages} unreadable={current['unreadable']}")
    completions = summary["factory_items"]["completions"]
    if completions["status"] == "available":
        value = completions["value"]
        lines.append(
            f"[inventory] Factory item completions observed in run: "
            f"count={value['count']} items={_list_text(value['items'])}")
        for event in sorted(
                value["events"],
                key=lambda row: (row["ts"], row["item"],
                                 str(row.get("from")), row["to"])):
            lines.append(
                f"[inventory] Factory completion event: "
                f"item={_field_text(event['item'])} ts={event['ts']} "
                f"from={_field_text(event.get('from'))} "
                f"to={_field_text(event['to'])}")
    else:
        lines.append(_unavailable_text(
            "Factory item completions observed in run", completions))

    aliases = summary["aliases"]
    if aliases["status"] == "available":
        value = aliases["value"]
        lines.append(
            f"[inventory] external aliases cumulative non-additive: "
            f"count={value['count']}")
        for row in value["rows"]:
            status = _field_text(row["status"])
            lines.append(
                f"[inventory] alias: id={_field_text(row['alias'])} "
                f"item={_field_text(row['item'])} "
                f"status={status} known_item={str(row['known_item']).lower()}")
    else:
        lines.append(_unavailable_text("external aliases cumulative", aliases))

    timing = summary["timing"]
    if timing["status"] != "available":
        lines.append(_unavailable_text("time observations", timing))
    else:
        timing_rows = sorted(
            timing["rows"],
            key=lambda row: (row["start"], row["end"], row["item"],
                             row["stage"], row["category"]))
        for row in timing_rows:
            lines.append(
                f"[proxy] stage interval: item={_field_text(row['item'])} "
                f"stage={_field_text(row['stage'])} "
                f"category={row['category']} seconds={row['seconds']} "
                f"start={row['start']} end={row['end']} "
                f"clipped={str(row['clipped']).lower()}")
        if not timing_rows and not timing["unavailable"]:
            lines.append("[unmeasured] stage intervals: UNMEASURED")
        for row in sorted(timing["unavailable"], key=lambda value: value["item"]):
            lines.append(_unavailable_text(
                f"stage intervals item={row['item']}", row))

        spans = sorted(
            timing["activity_spans"],
            key=lambda row: (row["reported_start"], row["reported_end"],
                             row["item"], row["span_id"]))
        for row in spans:
            lines.append(
                f"[measured] activity span: item={_field_text(row['item'])} "
                f"id={_field_text(row['span_id'])} category={row['category']} "
                f"source={_field_text(row['source'])} seconds={row['seconds']} "
                f"start={row['reported_start']} end={row['reported_end']} "
                f"clipped={str(row['clipped']).lower()}")
        for category in ("test", "review", "admin"):
            metric = timing["category_status"][category]
            if metric["status"] == "unmeasured":
                lines.append(
                    f"[unmeasured] activity category {category}: UNMEASURED")

    waves = summary["waves"]
    if waves["status"] != "available":
        lines.append(_unavailable_text("test waves", waves))
    else:
        wave_rows = sorted(
            waves["value"]["rows"],
            key=lambda row: (row["finished_at"], row["item"], row["wave_id"]))
        if not wave_rows:
            lines.append("[measured] test waves: none observed in interval")
        for row in wave_rows:
            tests = row["tests"]
            green = row["green_sha"] or "UNAVAILABLE"
            shipping = row["shipping_ref"] or "UNAVAILABLE"
            shots = [
                f"{shot['path']}={shot['current_sha256']}"
                for shot in row["screenshots"]
            ]
            lines.append(
                f"[measured] test wave: item={_field_text(row['item'])} "
                f"id={_field_text(row['wave_id'])} "
                f"purpose={row['purpose']} result={row['result']} "
                f"tests=passed:{tests['passed']},failed:{tests['failed']},"
                f"skipped:{tests['skipped']} duration_seconds={row['duration_seconds']} "
                f"green_sha={green} delivery={row['delivery_status']} "
                f"flows={_list_text(row['flows'])} "
                f"shipped_flows={_list_text(row['shipped_flows'])} "
                f"shipping_ref={shipping} screenshots={len(shots)} "
                f"screenshot_hashes={_list_text(shots)} "
                f"boundary_crossing={str(row['boundary_crossing']).lower()}")

    lines.extend(
        f"[warning] {_field_text(warning)}" for warning in summary["warnings"])
    lines.extend(
        f"[warning] limit: {_field_text(limit)}" for limit in summary["limits"])
    return "\n".join(lines)
