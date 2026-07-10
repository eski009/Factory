"""Read-side per-item cost aggregation. Item spec 0004 §2.

Tier-1 effort proxies (per-stage wall-clock, stage advances, retries)
are derived retroactively from stage.advance events already on disk —
zero new writes. Tier-2 rolls up spend events skills wrote through the
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


def _bucket(stages, name):
    return stages.setdefault(
        name, {"active_seconds": 0, "entries": 0, "dispatches": 0})


def summarize(repo, item_id):
    """Aggregate one item's log into the cost-summary dict (spec §2).

    Raises items.ItemError for an unknown item, mirroring packet.
    Tolerant of malformed events: stage.advance without dict data/"to"
    or a parseable ts is skipped; invalid spend events are excluded
    from every sum and surfaced as invalid_spend_events.
    """
    items.load_item(repo, item_id)
    events = logs.read_events(repo, item_id)
    now = logs.now_stamp()

    stages = {}
    waiting = 0
    advances = 0
    retries = 0
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
        if name == "review.rejected":
            retries += 1
        if name != "stage.advance" or ts is None:
            continue
        data = event.get("data")
        if not isinstance(data, dict) or "to" not in data:
            continue
        seconds = _seconds_between(prev, ts)
        resumed = current_stage in WAITING_STAGES
        if resumed:
            waiting += seconds
        else:
            _bucket(stages, current_stage)["active_seconds"] += seconds
        advances += 1
        current_stage = data["to"]
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
    for event in events:
        if not isinstance(event, dict) or event.get("event") != "spend":
            continue
        data = event.get("data")
        if initrepo.spend_event_errors(data, "spend"):
            invalid += 1
            continue
        count = data.get("dispatches", 0)
        dispatches += count
        stage = data.get("stage")
        if stage is not None and count:
            _bucket(stages, stage)["dispatches"] += count
        if data["provenance"] == "measured":
            if measured is None:
                measured = {"events": 0, "input": 0, "output": 0, "total": 0}
            measured["events"] += 1
            for key in TOKEN_KEYS:
                measured[key] += data["tokens"].get(key, 0)

    active = sum(b["active_seconds"] for b in stages.values())
    return {
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
        "retries": retries,
        "dispatches": dispatches,
        "stages": stages,
        "measured": measured,
        "unmeasured": UNMEASURED_NOTE,
        "invalid_spend_events": invalid,
    }


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


def _measured_text(summary):
    measured = summary["measured"]
    segments = _token_segments(measured)
    if not segments:
        return "[measured] tokens: none logged"
    return (f"[measured] tokens: {', '.join(segments)} "
            f"({measured['events']} spend events)")


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
    lines.append(f"[proxy] advances: {summary['advances']}, "
                 f"retries: {summary['retries']}, "
                 f"dispatches: {summary['dispatches']}")
    lines.append(_measured_text(summary))
    lines.append(f"[unmeasured] UNMEASURED: {UNMEASURED_NOTE} "
                 "(not in any figure above)")
    if summary["invalid_spend_events"]:
        lines.append(f"invalid spend events: "
                     f"{summary['invalid_spend_events']} "
                     "(excluded; run factory validate)")
    return "\n".join(lines)


def render_receipt(summary):
    """Packet receipt block: exactly three bullet lines (spec §5)."""
    proxy = (f"- [proxy] active {format_duration(summary['active_seconds'])} "
             f"(waiting {format_duration(summary['waiting_seconds'])}), "
             f"{summary['advances']} advances, "
             f"{summary['dispatches']} dispatches, "
             f"{summary['retries']} retries")
    measured = summary["measured"]
    segments = _token_segments(measured)
    if not segments:
        measured_line = "- [measured] tokens: none logged"
    else:
        measured_line = (f"- [measured] tokens: {', '.join(segments)} "
                         f"({measured['events']} events)")
    return "\n".join([
        proxy,
        measured_line,
        f"- [unmeasured] UNMEASURED: {UNMEASURED_NOTE}",
    ])
