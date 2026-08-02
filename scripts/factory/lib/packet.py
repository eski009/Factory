"""Render mobile-legible review packets for humans. Spec §5, §9."""

import html
import re

from . import cost, items, logs, paths

ARTIFACTS = ("triage.md", "spec.md", "plan.md", "design/choice.md",
             "reviews/synthesis.md", "assurance/impact.json",
             "assurance/verdicts.json")
URL_RE = re.compile(r"https?://[^\s<>\"']+")


def packet_html_path(repo, item_id):
    return paths.docs_root(repo) / "packets" / f"{item_id}.html"


def view_links(repo, item_id, meta):
    """Return human-facing packet links in preferred viewing order."""
    links = []
    match = URL_RE.search(meta.get("paused-reason", ""))
    if match:
        links.append(("View the options (opens on phone or desktop)",
                      match.group(0)))
    options = paths.item_dir(repo, item_id) / "design" / "options.html"
    if options.exists():
        links.append(("View the design options (local HTML)",
                      options.resolve().as_uri()))
    links.append(("Open this packet as a page",
                  packet_html_path(repo, item_id).resolve().as_uri()))
    return links


def cost_decision_lines(repo, item_id, meta, summary=None):
    """The '## Cost decision' body, ordered exactly as item spec 0016 §6.
    Returns [] unless the item is parked with a cost-breaker reason. The
    proxy substrate leads: no token headline appears above it, because
    the measured aggregate has been shown untrustworthy.

    `summary` is the render's single aggregation of the item log, passed
    in by the caller. A parked item's window is open, so `active_seconds`
    re-reads the wall clock on every `cost.summarize` call: aggregating
    separately here would print this block's proxy figures and the
    `## Spend` receipt's from two different instants."""
    from . import breaker
    if meta.get("stage") != "waiting-human":
        return []
    if not meta.get("paused-reason", "").startswith(breaker.PAUSE_PREFIX):
        return []
    if summary is None:
        summary = cost.summarize(repo, item_id)
    v = breaker.verdict(repo, item_id, meta, "implement", summary=summary)
    edges = summary["rework_edges"]
    entries = summary["stages"].get("implement", {}).get("entries", 0)
    priority = meta.get("priority", "-")
    at_or_above = v["backlog"]["at_or_above"]
    total = v["backlog"]["actionable_total"]
    recommended = "defer" if at_or_above >= 1 else "narrow"
    why = {
        "defer": ("work at this priority or higher is waiting behind an item "
                  "already reworked past the threshold."),
        "narrow": ("nothing else is waiting at this priority, so a smaller "
                   "next round costs less than another full one."),
    }[recommended]
    return [
        f"- [proxy] rework edges: {edges} (backward stage.advance edges into "
        f"implement; threshold {v['threshold']})",
        f"- [proxy] active {cost.format_duration(summary['active_seconds'])}, "
        f"{summary['advances']} advances, {entries} implement entries",
        "- " + cost.render_lower_bound(summary),
        f"- backlog: {at_or_above} actionable items at priority ≤ {priority}, "
        f"{total} actionable in total",
        "",
        f"Recommended: {recommended} — {why}",
        "",
        # Deviation from plan Task 10 step 4: the loop-mode clause is joined
        # with a semicolon, not a full stop, so the M9 sentence reads as one
        # lower-case clause exactly as the AC12 test asserts it.
        f"- continue — the item returns to implement; the next rework edge "
        f"parks it again at {edges + 1}; the {at_or_above} items at priority "
        f"≤ {priority} keep waiting; in loop mode the next actionable item "
        "runs while this one waits; in item/step mode the run stops here.",
        f"- narrow — records the decision; edit plan.md, then factory advance "
        f"{item_id} implement. v1 does not narrow scope for you.",
        f"- defer — records the decision and leaves the item parked; drop its "
        f"priority with factory priority {item_id} <n>. v1 does not "
        "re-prioritise for you.",
    ]


def respond_action_lines(repo, item_id, meta):
    """Exactly one copy-pasteable action, naming the verb that actually
    answers THIS pause. One branch, shared by both renderers, so the HTML
    can never tell a cost-breaker pause to run /factory:run."""
    from . import breaker
    paused_from = meta.get("paused-from")
    reason = meta.get("paused-reason", "")
    if paused_from == "design":
        return [f"- `factory choice {item_id} <option>` — record your pick."]
    if paused_from == "assure":
        return [f"- `factory confirm {item_id}` — or "
                f'`factory waive {item_id} --reason "..."` to ship with a '
                "recorded waiver."]
    if paused_from == "implement" and reason.startswith(breaker.PAUSE_PREFIX):
        return [f"- `factory cost-answer {item_id} <continue|narrow|defer>` "
                "— record the cost decision."]
    return ["- `/factory:run` — resume the pipeline."]


def render_packet(repo, item_id, summary=None):
    meta, _body = items.load_item(repo, item_id)
    item_dir = paths.item_dir(repo, item_id)
    if summary is None:
        summary = cost.summarize(repo, item_id)
    lines = [f"# {meta['title']}", ""]
    lines.append(f"- id: {meta['id']}")
    lines.append(f"- stage: {meta['stage']}")
    lines.append(f"- kind: {meta['kind']}")
    lines.append(f"- priority: {meta.get('priority', '-')}")
    if meta.get("paused-reason"):
        lines.append(f"- waiting on you: {meta['paused-reason']}")
    decision = cost_decision_lines(repo, item_id, meta, summary)
    if decision:
        lines += ["", "## Cost decision", ""] + decision
    lines += ["", "## View the options"]
    for label, url in view_links(repo, item_id, meta):
        lines.append(f"- [{label}]({url})")
    lines += ["", "## Artifacts"]
    for rel in ARTIFACTS:
        artifact = item_dir / rel
        exists = artifact.exists()
        line = f"- {rel}: {'yes' if exists else 'no'}"
        if exists:
            line += f" — [open]({artifact.resolve().as_uri()})"
        lines.append(line)
    lines += ["", "## Recent events"]
    for event in logs.read_events(repo, item_id)[-5:]:
        lines.append(f"- {event['ts']} {event['event']}"
                     + (f" {event['data']}" if "data" in event else ""))
    lines += ["", "## Spend"]
    lines += cost.render_receipt(summary).splitlines()
    lines += ["", "## Respond",
              "Reply in session, or use the factory CLI to record your "
              "decision.", ""]
    lines += respond_action_lines(repo, item_id, meta)
    lines.append("")
    return "\n".join(lines)


def _e(value):
    return html.escape(str(value), quote=True)


def _link(label, url):
    return f'<a href="{_e(url)}">{_e(label)}</a>'


def render_packet_html(repo, item_id, summary=None):
    meta, _body = items.load_item(repo, item_id)
    item_dir = paths.item_dir(repo, item_id)
    if summary is None:
        summary = cost.summarize(repo, item_id)
    links = view_links(repo, item_id, meta)[:-1]
    artifact_links = [
        (f"Open {rel}", (item_dir / rel).resolve().as_uri())
        for rel in ARTIFACTS if (item_dir / rel).exists()
    ]
    events = logs.read_events(repo, item_id)[-5:]
    receipt = cost.render_receipt(summary).splitlines()

    out = ["""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Factory packet — """ + _e(meta["title"]) + """</title>
  <style>
    :root { color-scheme: light dark; --bg: #f5f5f2; --panel: #fff;
      --text: #252522; --muted: #6f706b; --line: #d9d9d3;
      --accent: #2459a9; --ask: #fff4cc; --ask-line: #d29b20; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text);
      font: 17px/1.55 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { width: min(100% - 32px, 760px); margin: 0 auto; padding: 48px 0 72px; }
    h1 { margin: 0 0 28px; font-size: clamp(2rem, 8vw, 3.25rem); line-height: 1.08; }
    h2 { margin: 0 0 16px; font-size: 1.3rem; }
    section { margin-top: 20px; padding: 24px; border: 1px solid var(--line);
      border-radius: 14px; background: var(--panel); }
    .ask, #cost-decision { border-left: 5px solid var(--ask-line); background: var(--ask); }
    .ask h2, #cost-decision h2 { text-transform: uppercase; letter-spacing: .08em; font-size: .84rem; }
    ul { margin: 0; padding-left: 1.25rem; }
    li + li { margin-top: 10px; }
    .meta { display: flex; flex-wrap: wrap; gap: 8px 18px; padding: 0; list-style: none; }
    .meta li { margin: 0; }
    a { color: var(--accent); font-weight: 650; text-underline-offset: 3px; overflow-wrap: anywhere; }
    .links { list-style: none; padding: 0; }
    .links a { display: block; padding: 14px 16px; border: 1px solid var(--line);
      border-radius: 10px; text-decoration: none; }
    .missing { color: var(--muted); }
    code { padding: .15em .35em; border-radius: 5px; background: color-mix(in srgb, var(--text) 9%, transparent);
      overflow-wrap: anywhere; }
    @media (prefers-color-scheme: dark) {
      :root { --bg: #181918; --panel: #222321; --text: #ededeb; --muted: #aaa9a4;
        --line: #3d3e3a; --accent: #91baff; --ask: #332d1d; --ask-line: #e2ae3d; }
    }
    @media (max-width: 520px) {
      main { width: min(100% - 20px, 760px); padding: 28px 0 48px; }
      section { padding: 20px 18px; border-radius: 11px; }
    }
  </style>
</head>
<body>
<main>""",
           f"  <h1>{_e(meta['title'])}</h1>"]

    if meta.get("paused-reason"):
        out += ["  <section class=\"ask\" id=\"waiting-on-you\">",
                "    <h2>waiting on you</h2>",
                f"    <p>{_e(meta['paused-reason'])}</p>",
                "  </section>"]

    # Deviation from plan Task 10 step 4: the section carries no
    # class="ask" attribute, so the id selector the tests split on stays
    # exact; the ask callout styling is attached to #cost-decision in the
    # stylesheet above instead.
    decision = cost_decision_lines(repo, item_id, meta, summary)
    if decision:
        out += ['  <section id="cost-decision">',
                "    <h2>Cost decision</h2>"]
        in_list = False
        for line in decision:
            if line.startswith("- "):
                if not in_list:
                    out.append("    <ul>")
                    in_list = True
                out.append(f"      <li>{_e(line.removeprefix('- '))}</li>")
                continue
            if in_list:
                out.append("    </ul>")
                in_list = False
            if line.strip():
                out.append(f"    <p><strong>{_e(line)}</strong></p>")
        if in_list:
            out.append("    </ul>")
        out.append("  </section>")

    out += ["  <section aria-label=\"Item metadata\">", "    <ul class=\"meta\">",
            f"      <li><strong>id:</strong> {_e(meta['id'])}</li>",
            f"      <li><strong>stage:</strong> {_e(meta['stage'])}</li>",
            f"      <li><strong>kind:</strong> {_e(meta['kind'])}</li>",
            f"      <li><strong>priority:</strong> {_e(meta.get('priority', '-'))}</li>",
            "    </ul>", "  </section>",
            "  <section id=\"view-options\">", "    <h2>View the options</h2>",
            "    <ul class=\"links\">"]
    if not links:
        out.append('      <li><a href="#artifacts">Review the available packet details</a></li>')
    for label, url in links + artifact_links:
        out.append(f"      <li>{_link(label, url)}</li>")
    out += ["    </ul>", "  </section>",
            "  <section id=\"artifacts\">", "    <h2>Artifacts</h2>", "    <ul>"]
    for rel in ARTIFACTS:
        artifact = item_dir / rel
        if artifact.exists():
            out.append(f"      <li>{_link(rel, artifact.resolve().as_uri())}</li>")
        else:
            out.append(f'      <li class="missing">{_e(rel)} (not yet)</li>')
    out += ["    </ul>", "  </section>", "  <section>",
            "    <h2>Recent events</h2>", "    <ul>"]
    for event in events:
        detail = f" {event['data']}" if "data" in event else ""
        out.append(f"      <li>{_e(event['ts'])} {_e(event['event'])}{_e(detail)}</li>")
    out += ["    </ul>", "  </section>", "  <section>", "    <h2>Spend</h2>",
            "    <ul>"]
    for line in receipt:
        out.append(f"      <li>{_e(line.removeprefix('- '))}</li>")
    out += ["    </ul>", "  </section>", "  <section id=\"respond\">",
            "    <h2>Respond</h2>",
            "    <p>Reply in session, or use the factory CLI.</p>",
            "    <ul>"]
    for line in respond_action_lines(repo, item_id, meta):
        body = line.removeprefix("- ")
        parts = body.split("`")
        rendered = "".join(
            f"<code>{_e(part)}</code>" if i % 2 else _e(part)
            for i, part in enumerate(parts))
        out.append(f"      <li>{rendered}</li>")
    out.append("    </ul>")
    out += ["  </section>", "</main>", "</body>", "</html>", ""]
    return "\n".join(out)


def write_packet(repo, item_id):
    """One aggregation, both documents: the markdown and the HTML packet
    are two views of one moment and must never disagree on a figure."""
    path = paths.docs_root(repo) / "packets" / f"{item_id}.md"
    html_path = packet_html_path(repo, item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = cost.summarize(repo, item_id)
    path.write_text(render_packet(repo, item_id, summary), encoding="utf-8")
    html_path.write_text(render_packet_html(repo, item_id, summary),
                         encoding="utf-8")
    return path
