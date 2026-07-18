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


def render_packet(repo, item_id):
    meta, _body = items.load_item(repo, item_id)
    item_dir = paths.item_dir(repo, item_id)
    lines = [f"# {meta['title']}", ""]
    lines.append(f"- id: {meta['id']}")
    lines.append(f"- stage: {meta['stage']}")
    lines.append(f"- kind: {meta['kind']}")
    lines.append(f"- priority: {meta.get('priority', '-')}")
    if meta.get("paused-reason"):
        lines.append(f"- waiting on you: {meta['paused-reason']}")
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
    lines += cost.render_receipt(cost.summarize(repo, item_id)).splitlines()
    lines += ["", "## Respond",
              "Reply in session, or use the factory CLI to record your",
              f"decision (design pause: `factory choice {meta['id']} <option>`;",
              f"assurance pause: `factory confirm {meta['id']}` or",
              f'`factory waive {meta["id"]} --reason "..."`),',
              "then run `/factory:run` to resume.", ""]
    return "\n".join(lines)


def _e(value):
    return html.escape(str(value), quote=True)


def _link(label, url):
    return f'<a href="{_e(url)}">{_e(label)}</a>'


def render_packet_html(repo, item_id):
    meta, _body = items.load_item(repo, item_id)
    item_dir = paths.item_dir(repo, item_id)
    links = view_links(repo, item_id, meta)[:-1]
    artifact_links = [
        (f"Open {rel}", (item_dir / rel).resolve().as_uri())
        for rel in ARTIFACTS if (item_dir / rel).exists()
    ]
    events = logs.read_events(repo, item_id)[-5:]
    receipt = cost.render_receipt(cost.summarize(repo, item_id)).splitlines()

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
    .ask { border-left: 5px solid var(--ask-line); background: var(--ask); }
    .ask h2 { text-transform: uppercase; letter-spacing: .08em; font-size: .84rem; }
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
            "    <p>Reply in session, or use the factory CLI.</p>"]
    if meta.get("paused-from") == "design":
        command = f"factory choice {meta['id']} <option>"
        out += [f"    <p>For this design pause: <code>{_e(command)}</code>, then run ",
                "      <code>/factory:run</code> to resume.</p>"]
    else:
        out.append("    <p>Run <code>/factory:run</code> to resume.</p>")
    out += ["  </section>", "</main>", "</body>", "</html>", ""]
    return "\n".join(out)


def write_packet(repo, item_id):
    path = paths.docs_root(repo) / "packets" / f"{item_id}.md"
    html_path = packet_html_path(repo, item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_packet(repo, item_id), encoding="utf-8")
    html_path.write_text(render_packet_html(repo, item_id), encoding="utf-8")
    return path
