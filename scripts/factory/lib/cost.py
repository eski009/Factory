"""Read-side per-item cost aggregation. Item spec 0004 §2.

Tier-1 effort proxies (per-stage wall-clock, stage advances, rework
edges) are derived retroactively from stage.advance events already on
disk — zero new writes. Tier-2 rolls up spend events skills wrote through the
existing `factory log` path. Every rendered figure carries exactly one
provenance class (measured | proxy | unmeasured), no line ever blends
classes, and the orchestrator's own main-loop tokens are always
reported as UNMEASURED — never silently zero.
"""

from datetime import datetime, timezone

from . import initrepo, items, logs, machine

UNMEASURED_NOTE = "orchestrator main-loop tokens"
WAITING_STAGES = frozenset(machine.SPECIAL)
TOKEN_KEYS = ("input", "output", "total")
SPEND_SCOPES = ("leaf", "fork")
UNCLASSIFIED_SCOPE = "unclassified"
MEASURED_SCOPE = "leaf"
PARTIAL_QUALIFIER = "PARTIAL — measured leaf events only; coverage incomplete"


def _scope_key(data):
    if isinstance(data, dict) and data.get("scope") in SPEND_SCOPES:
        return data["scope"]
    return UNCLASSIFIED_SCOPE


def _empty_scope_counts():
    return {"leaf": 0, "fork": 0, UNCLASSIFIED_SCOPE: 0}


def _merge_measured(target, measured):
    if measured is None:
        return target
    if target is None:
        target = {"events": 0, "input": 0, "output": 0, "total": 0}
    for key in ("events",) + TOKEN_KEYS:
        target[key] += measured[key]
    return target

# The rework substrate: a backward stage.advance edge into implement.
# Engine-written (machine.advance appends every stage.advance itself), so
# no skill can forget to log it. "verify" counts: the edge is admitted and
# capped by machine.MAX_VERIFY_REWORKS. waiting-human -> implement is
# deliberately absent so resumes cannot inflate the count.
REWORK_FROM = frozenset({"review", "assure", "verify"})
REWORK_TO = "implement"
# Item 0015: the redesign firing set - aliased from the one declaration
# in machine.py, the way breaker.py aliases cost.REWORK_FROM (the alias
# direction is dictated by the import graph: cost imports machine).
APPROACH_FROM = machine.APPROACH_FROM
APPROACH_TO = machine.APPROACH_TO
REWORK_SUBSTRATE_NOTE = (
    "backward stage.advance edges (review|assure|verify → implement); "
    "rework routed through waiting-human is not counted")


def _parse_ts(stamp):
    try:
        return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _seconds_between(start, end):
    return max(0, int((end - start).total_seconds()))


def _add_tokens(target, tokens):
    target["events"] += 1
    for key in TOKEN_KEYS:
        target[key] += tokens.get(key, 0)


def _bucket(stages, name):
    """A stage bucket. `measured` stays None until a valid measured spend
    event names this stage — never zero, so a stage with no measurement
    renders the loud UNMEASURED literal rather than a fabricated 0."""
    return stages.setdefault(
        name, {"active_seconds": 0, "entries": 0, "dispatches": 0,
               "measured": None, "proxy_events": 0})


def summarize(repo, item_id):
    """Aggregate one item's log into the cost-summary dict (spec §2).

    Raises items.ItemError for an unknown item, mirroring packet.
    Tolerant of malformed events: stage.advance without dict data, with a
    non-string `from`/`to` stage name, or without a parseable ts is skipped;
    invalid spend events are excluded from every sum and surfaced as
    invalid_spend_events. Corrupt log lines are skipped at the
    logs.read_events_with_stats boundary and surfaced as corrupt_log_lines
    (item spec 0007 §2). A missing `from` retains the legacy tracked-stage
    fallback used for rework counting.
    """
    items.load_item(repo, item_id)
    events, corrupt = logs.read_events_with_stats(repo, item_id)
    now = logs.now_stamp()

    stages = {}
    waiting = 0
    advances = 0
    rework_edges = 0
    approach_edges = 0
    rework_since_redesign = 0
    start = None
    prev = None
    current_stage = "idea"

    for event in events:
        if not isinstance(event, dict):
            continue
        ts = _parse_ts(event.get("ts"))
        if ts is not None and start is None:
            start = ts
            prev = ts
            _bucket(stages, current_stage)["entries"] += 1
        name = event.get("event")
        if name != "stage.advance" or ts is None:
            continue
        data = event.get("data")
        if not isinstance(data, dict) or "to" not in data:
            continue
        to = data["to"]
        if (not isinstance(to, str)
                or ("from" in data and not isinstance(data["from"], str))):
            continue
        rework_from = data.get("from", current_stage)
        approach_from = data.get("from")
        seconds = _seconds_between(prev, ts)
        resumed = current_stage in WAITING_STAGES
        if resumed:
            waiting += seconds
        else:
            _bucket(stages, current_stage)["active_seconds"] += seconds
        advances += 1
        if rework_from in REWORK_FROM and to == REWORK_TO:
            rework_edges += 1
            rework_since_redesign += 1
        if approach_from in APPROACH_FROM and to == APPROACH_TO:
            # Item 0015 SS6: the redesign boundary. approach_edges is
            # lifetime; rework_since_redesign restarts here. The
            # cumulative rework_edges above is deliberately untouched -
            # the breaker measures spend across redesigns (B4).
            approach_edges += 1
            rework_since_redesign = 0
        current_stage = to
        prev = ts
        if current_stage not in WAITING_STAGES and not resumed:
            _bucket(stages, current_stage)["entries"] += 1

    if current_stage == "done" and prev is not None:
        open_ = False
        end = _fmt(prev)
    else:
        open_ = True
        end = now
        end_dt = _parse_ts(now)
        if prev is not None and end_dt is not None:
            seconds = _seconds_between(prev, end_dt)
            if current_stage in WAITING_STAGES:
                waiting += seconds
            else:
                _bucket(stages, current_stage)["active_seconds"] += seconds

    dispatches = 0
    invalid = 0
    measured = None
    scope_counts = _empty_scope_counts()
    for event in events:
        if not isinstance(event, dict) or event.get("event") != "spend":
            continue
        data = event.get("data")
        scope = _scope_key(data)
        scope_counts[scope] += 1
        if not isinstance(data, dict):
            invalid += 1
            continue

        # Validate every field except the scope axis first. This preserves
        # auditable proxy/unmeasured evidence when only scope is invalid,
        # while malformed provenance/token payloads remain fail-closed.
        base_data = dict(data)
        base_data["scope"] = "leaf"
        if initrepo.spend_event_errors(base_data, "spend"):
            invalid += 1
            continue
        if scope == UNCLASSIFIED_SCOPE and "scope" in data:
            invalid += 1

        count = data.get("dispatches", 0)
        dispatches += count
        stage = data.get("stage")
        if stage is not None and count:
            _bucket(stages, stage)["dispatches"] += count
        if data["provenance"] == "measured" and scope == MEASURED_SCOPE:
            if measured is None:
                measured = {"events": 0, "input": 0, "output": 0, "total": 0}
            _add_tokens(measured, data["tokens"])
            if stage is not None:
                bucket = _bucket(stages, stage)
                if bucket["measured"] is None:
                    bucket["measured"] = {"events": 0, "input": 0,
                                          "output": 0, "total": 0}
                _add_tokens(bucket["measured"], data["tokens"])
        elif data["provenance"] != "measured" and stage is not None:
            _bucket(stages, stage)["proxy_events"] += 1

    active = sum(b["active_seconds"] for b in stages.values())
    summary = {
        "item": item_id,
        "window": {
            "start": _fmt(start) if start is not None else now,
            "end": end,
            "open": open_,
        },
        "elapsed_seconds": active + waiting,
        "active_seconds": active,
        "waiting_seconds": waiting,
        "advances": advances,
        "rework_edges": rework_edges,
        "dispatches": dispatches,
        "stages": stages,
        "measured": measured,
        "measured_scope": MEASURED_SCOPE,
        "coverage_complete": False,
        "scope_counts": scope_counts,
        "unmeasured": UNMEASURED_NOTE,
        "invalid_spend_events": invalid,
        "corrupt_log_lines": corrupt,
    }
    if approach_edges:
        # Present only on redesigned items: a zero-approach item's
        # summary - and every byte derived from it (status --json,
        # packets, cost --json) - stays identical to the pre-change
        # engine (item 0015 AC20; J-001 byte-identity regression).
        summary["approach_edges"] = approach_edges
        summary["rework_edges_since_last_redesign"] = rework_since_redesign
    return summary


def format_duration(seconds):
    """Render seconds as 'Dd HHh MMm' (day part omitted when zero),
    truncating to minute precision."""
    minutes = max(0, int(seconds)) // 60
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m"
    return f"{hours:02d}h {minutes:02d}m"


def _token_segments(measured):
    """Render only token keys actually observed (nonzero summed) across
    valid measured events — never fabricate 'input 0'/'output 0' for a
    split that was never logged. Shared by render_text and
    render_receipt so they cannot diverge."""
    if measured is None:
        return []
    return [f"{key} {measured[key]}" for key in TOKEN_KEYS if measured[key]]


def _scope_count_text(summary):
    counts = summary["scope_counts"]
    return (f"spend events: leaf {counts['leaf']}, fork {counts['fork']}, "
            f"unclassified {counts['unclassified']}")


def _measured_text(summary, subject=None, include_scope_counts=True):
    measured = summary["measured"]
    segments = _token_segments(measured)
    label = f"{subject}: " if subject else ""
    token_label = f"{label}tokens" if subject else "tokens:"
    if not segments:
        line = (f"[unmeasured] {token_label} UNMEASURED — "
                f"{PARTIAL_QUALIFIER}")
    else:
        line = (f"[measured] {token_label} {', '.join(segments)} "
                f"({measured['events']} spend events) — {PARTIAL_QUALIFIER}")
    if include_scope_counts:
        line += f" ({_scope_count_text(summary)})"
    return line


def render_text(summary):
    """Greppable text contract (spec §2): every cost-figure line starts
    with exactly one provenance tag; item/window/elapsed are window
    metadata; the UNMEASURED line is always printed."""
    window = summary["window"]
    state = "open" if window["open"] else "closed"
    lines = [
        f"item: {summary['item']}",
        f"window: {window['start']} -> {window['end']} ({state})",
        f"elapsed: {format_duration(summary['elapsed_seconds'])}",
        f"[proxy] active: {format_duration(summary['active_seconds'])}",
        f"[proxy] waiting: {format_duration(summary['waiting_seconds'])}",
    ]
    for name in machine.STAGES:
        bucket = summary["stages"].get(name)
        if bucket is None:
            continue
        line = (f"[proxy] stage {name}: "
                f"active {format_duration(bucket['active_seconds'])}, "
                f"entries {bucket['entries']}")
        if bucket["dispatches"]:
            line += f", dispatches {bucket['dispatches']}"
        lines.append(line)
        segments = _token_segments(bucket["measured"])
        if segments:
            lines.append(f"[measured] stage {name}: tokens "
                         f"{', '.join(segments)} "
                         f"({bucket['measured']['events']} spend events) — "
                         f"{PARTIAL_QUALIFIER}")
        else:
            lines.append(f"[unmeasured] stage {name}: tokens UNMEASURED — "
                         f"{PARTIAL_QUALIFIER}")
    lines.append(f"[proxy] advances: {summary['advances']}, "
                 f"rework edges: {summary['rework_edges']}, "
                 f"dispatches: {summary['dispatches']}")
    lines.append(f"[proxy] rework substrate: {REWORK_SUBSTRATE_NOTE}")
    lines.append(_measured_text(summary))
    lines.append(f"[unmeasured] UNMEASURED: {UNMEASURED_NOTE} "
                 "(not in any figure above)")
    if summary["invalid_spend_events"]:
        lines.append(f"invalid spend events: "
                     f"{summary['invalid_spend_events']} "
                     "(excluded; run factory validate)")
    if summary["corrupt_log_lines"]:
        lines.append(f"corrupt log lines: {summary['corrupt_log_lines']} "
                     "(skipped; run factory validate)")
    return "\n".join(lines)


def render_receipt(summary):
    """Packet receipt block: exactly three bullet lines (spec §5)."""
    proxy = (f"- [proxy] active {format_duration(summary['active_seconds'])} "
             f"(waiting {format_duration(summary['waiting_seconds'])}), "
             f"{summary['advances']} advances, "
             f"{summary['dispatches']} dispatches, "
             f"{summary['rework_edges']} rework edges")
    if summary["corrupt_log_lines"]:
        proxy += f", corrupt log lines skipped: {summary['corrupt_log_lines']}"
    measured_line = "- " + _measured_text(summary)
    lines = [
        proxy,
        measured_line,
        f"- [unmeasured] UNMEASURED: {UNMEASURED_NOTE}",
    ]
    for name in machine.STAGES:
        bucket = summary["stages"].get(name)
        if bucket is None:
            continue
        segments = _token_segments(bucket["measured"])
        if segments:
            lines.append(f"- [measured] stage {name}: {', '.join(segments)} "
                         f"({bucket['measured']['events']} events) — "
                         f"{PARTIAL_QUALIFIER}")
    return "\n".join(lines)


def _coverage_scan(repo, item_id):
    """Walk one item's log in order. An advance 'carries' a spend event
    when at least one valid spend event appears after the previous
    stage.advance (or the start of the log) and before it. Every figure
    here is computed by scanning — no literal is ever baked in."""
    events, _corrupt = logs.read_events_with_stats(repo, item_id)
    advances = 0
    carried = 0
    any_spend = False
    pending = False
    for event in events:
        if not isinstance(event, dict):
            continue
        name = event.get("event")
        if name == "spend":
            if not initrepo.spend_event_errors(event.get("data"), "spend"):
                any_spend = True
                pending = True
        elif name == "stage.advance":
            data = event.get("data")
            if not isinstance(data, dict) or "to" not in data:
                continue
            advances += 1
            if pending:
                carried += 1
            pending = False
    return {"advances": advances, "carried": carried, "any_spend": any_spend}


def summarize_all(repo):
    """Backlog-wide aggregate of valid measured leaf spend and coverage."""
    metas, errors = items.list_items_safe(repo)
    metas = sorted(metas, key=lambda m: m["id"])
    rows = []
    measured = None
    scope_counts = _empty_scope_counts()
    items_with_spend = 0
    advances_total = 0
    advances_with_spend = 0
    done_items = 0
    done_with_tier = 0
    for meta in metas:
        row = summarize(repo, meta["id"])
        rows.append(row)
        measured = _merge_measured(measured, row["measured"])
        for scope in (*SPEND_SCOPES, UNCLASSIFIED_SCOPE):
            scope_counts[scope] += row["scope_counts"][scope]
        scan = _coverage_scan(repo, meta["id"])
        advances_total += scan["advances"]
        advances_with_spend += scan["carried"]
        if scan["any_spend"]:
            items_with_spend += 1
        if meta.get("stage") == "done":
            done_items += 1
            if meta.get("tier"):
                done_with_tier += 1
    return {
        "items": rows,
        "measured": measured,
        "measured_scope": MEASURED_SCOPE,
        "coverage_complete": False,
        "scope_counts": scope_counts,
        "coverage": {
            "items_with_spend": items_with_spend,
            "items_total": len(rows),
            "advances_with_spend": advances_with_spend,
            "advances_total": advances_total,
            "done_items": done_items,
            "done_with_tier": done_with_tier,
            # N4: list_items_safe's dropped items are reported, not
            # discarded — the coverage denominator names what it could
            # not read rather than passing the survivors off as the
            # whole population.
            "unreadable_items": len(errors),
        },
    }


def render_all_text(summary):
    """Aggregate text contract: qualified leaf totals, proxy blocks, one
    [coverage] line, and one [unmeasured] line."""
    lines = [_measured_text(summary, subject="aggregate",
                            include_scope_counts=True)]
    for item in summary["items"]:
        lines.append(_measured_text(item, subject=item["item"],
                                    include_scope_counts=True))
        for name in machine.STAGES:
            bucket = item["stages"].get(name)
            if bucket is None:
                continue
            lines.append(f"[proxy] stage {name}: "
                         f"active {format_duration(bucket['active_seconds'])}, "
                         f"entries {bucket['entries']}")
        lines.append(f"[proxy] {item['item']}: advances {item['advances']}, "
                     f"rework edges {item['rework_edges']}")
    cov = summary["coverage"]
    coverage = (f"[coverage] spend events present for "
                f"{cov['items_with_spend']} of {cov['items_total']} items; "
                f"{cov['advances_with_spend']} of {cov['advances_total']} "
                "stage advances carry one")
    # Conditional, so the line is byte-unchanged when every item read.
    dropped = cov.get("unreadable_items", 0)
    if dropped:
        coverage += (f"; {dropped} item{'' if dropped == 1 else 's'} "
                     "unreadable and excluded")
    lines.append(coverage)
    lines.append(f"[unmeasured] UNMEASURED: {UNMEASURED_NOTE}; per-tier "
                 f"medians ({cov['done_with_tier']} of {cov['done_items']} "
                 "done items carry a tier) — no median is computed")
    return "\n".join(lines)


def render_lower_bound(summary):
    """One leaf-scoped, visibly partial measured-token decision line."""
    return _measured_text(summary)
