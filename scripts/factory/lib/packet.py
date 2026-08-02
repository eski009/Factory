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


def waiting_line(meta, summary):
    """The `- waiting on you:` text, one branch shared by both renderers.

    A cost-breaker pause is rendered from `summary["rework_edges"]`,
    never from the operator's free text: the park reason is hand-copied
    by an agent (`skills/factory-dispatch/SKILL.md:50`) and a typo in it
    must not reach the operator as a rework figure (B3/F4) — least of all
    on the line that leads the page. Every other pause reason is echoed
    faithfully; this is scoped to the cost-breaker prefix only, so a
    design pause's free text (and its hosted URL) is untouched.

    `summary` is the render's single aggregation, passed down by the
    caller: re-reading the clock here would let the two documents
    `write_packet` produces disagree."""
    from . import breaker
    reason = meta.get("paused-reason", "")
    if reason.startswith(breaker.PAUSE_PREFIX):
        return (f"{breaker.PAUSE_PREFIX} {summary['rework_edges']} rework "
                f"edges (threshold {breaker.REWORK_THRESHOLD})")
    if reason.startswith("approach cap:"):
        # Derived, never echoed (the same B3/F4 rule as the breaker
        # branch above): the count is the engine's, not the reason's.
        from . import machine
        return (f"approach cap: {summary.get('approach_edges', 0)} "
                f"redesign(s) used (cap {machine.MAX_APPROACH_REJECTIONS})")
    return reason


def redesign_population_lines(summary):
    """The two labelled populations every redesigned item's packet
    renders (item 0015 SS8, B4): a redesign never masquerades as a
    fresh start. [] for items with zero approach edges, so their
    packets stay byte-identical to the pre-change engine. Both figures
    come from the caller's single summarize read; the cumulative echo
    is numerically the receipt/breaker figure by construction."""
    from . import machine
    n = summary.get("approach_edges", 0)
    if not n:
        return []
    since = summary.get("rework_edges_since_last_redesign", 0)
    return [
        f"- [proxy] redesigns: {n} of {machine.MAX_APPROACH_REJECTIONS} "
        "(engine-counted approach.rejected edges; lifetime, never reset)",
        f"- [proxy] rework edges since last redesign: {since} "
        f"(cumulative {summary['rework_edges']} — the breaker counts "
        "the cumulative figure)",
    ]


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
    unreadable = v["backlog"]["unreadable"]
    unpriced = v["backlog"]["unpriced"]
    # B1: `at_or_above is None` means the comparison is impossible, not
    # empty. brain/constraints.md forbids rendering an incomparable
    # population as a number, so all three surfaces that read it — the
    # backlog line, the recommendation and the continue consequence —
    # take the same branch. A remedy on the recommendation alone would
    # leave the other two false statements on screen.
    comparable = at_or_above is not None
    # N4: the items list_items_safe could not read are named rather than
    # dropped, so `total` is never an unqualified denominator.
    dropped = (f"; {unreadable} item{'' if unreadable == 1 else 's'} "
               "unreadable and excluded" if unreadable else "")
    # F5 + F6: the two populations `at_or_above` cannot speak for. An
    # unpriced sibling and an unreadable one are both incomparable, not
    # absent, so any sentence that concludes "nothing is waiting" from a
    # zero must name them — the backlog line already did, while the
    # recommendation and the continue consequence did not.
    unknown_bits = []
    if unpriced:
        unknown_bits.append(
            f"{unpriced} actionable item{'' if unpriced == 1 else 's'} with "
            "no priority")
    if unreadable:
        unknown_bits.append(
            f"{unreadable} unreadable item{'' if unreadable == 1 else 's'}")
    unknown = " and ".join(unknown_bits)
    if comparable:
        at_s = "" if at_or_above == 1 else "s"
        backlog_line = (f"- backlog: {at_or_above} actionable item{at_s} at "
                        f"priority ≤ {priority}, {total} actionable in "
                        f"total{dropped}")
        recommended = "defer" if at_or_above >= 1 else "narrow"
        # AC11: the Recommended line is exactly one sentence, so every
        # qualifier joins with a semicolon or an em dash — never a second
        # full stop (`test_recommendation_is_defer_when_backlog_at_or_above`
        # asserts `count(".") == 1`). `defer` needs none of this: it is
        # reached only when at_or_above >= 1, so it asserts presence, not
        # the emptiness an unknown population could falsify.
        narrow_why = ("nothing else is waiting at this priority, so a smaller "
                      "next round costs less than another full one.")
        if unknown:
            narrow_why = (f"nothing comparable is waiting at this priority; "
                          f"{unknown} cannot be compared either way, so the "
                          "backlog is not established as empty; a smaller "
                          "next round costs less than another full one.")
        why = {
            "defer": ("work at this priority or higher is waiting behind an "
                      "item already reworked past the threshold."),
            "narrow": narrow_why,
        }[recommended]
        recommendation = f"Recommended: {recommended} — {why}"
        waiting = (f"the {at_or_above} item{at_s} at priority ≤ {priority} "
                   f"keep{'s' if at_or_above == 1 else ''} waiting"
                   + (f", alongside {unknown} that cannot be compared"
                      if unknown else "") + "; ")
    else:
        backlog_line = ("- backlog: comparison unavailable — this item has "
                        f"no priority; {total} actionable in total{dropped}")
        # The packet is a static file (`write_packet`), so setting a
        # priority does not rewrite it: the second verb must be the
        # re-render, never "re-read this packet". F8: both verbs are
        # code-spanned — `<n>` matches CommonMark's inline raw-HTML
        # open-tag production and is swallowed by markdown renderers,
        # and for a no-priority item these commands are the operator's
        # only route to a decision.
        recommendation = ("Recommended: set a priority first — what this item "
                          "is blocking cannot be compared until it has one; "
                          f"run `factory priority {item_id} <n>`, then "
                          f"`factory packet {item_id}` to re-render this "
                          "decision.")
        waiting = ""
    return [
        f"- [proxy] rework edges: {edges} (backward stage.advance edges into "
        f"implement; threshold {v['threshold']})",
        f"- [proxy] active {cost.format_duration(summary['active_seconds'])}, "
        f"{summary['advances']} advances, {entries} implement entries",
        "- " + cost.render_lower_bound(summary),
        backlog_line,
        "",
        recommendation,
        "",
        # Deviation from plan Task 10 step 4: the loop-mode clause is joined
        # with a semicolon, not a full stop, so the M9 sentence reads as one
        # lower-case clause exactly as the AC12 test asserts it.
        f"- continue — the item returns to implement; the next rework edge "
        f"parks it again at {edges + 1}; {waiting}in loop mode the next "
        "actionable item runs while this one waits; in item/step mode the "
        "run stops here.",
        f"- narrow — records the decision; edit plan.md, then factory advance "
        f"{item_id} implement. v1 does not narrow scope for you.",
        f"- defer — records the decision and leaves the item parked; drop its "
        f"priority with `factory priority {item_id} <n>`. v1 does not "
        "re-prioritise for you.",
    ]


def redesign_decision_lines(repo, item_id, meta, summary=None):
    """The '## Redesign decision' body (item 0015 SS8), on the 0016
    '## Cost decision' precedent. [] unless the item is parked with an
    approach-cap reason. The two labelled populations lead - a redesign
    never masquerades as a fresh start (B4); every figure derives from
    the render's single summarize read; the graveyard excerpt is
    authored text, labelled as such, never parsed (bid-0086). The
    Recommended line follows the breaker's deterministic backlog rule
    and is never `continue` (AC19)."""
    from . import approach, breaker, machine
    if meta.get("stage") != "waiting-human":
        return []
    if not meta.get("paused-reason", "").startswith(approach.PAUSE_PREFIX):
        return []
    if summary is None:
        summary = cost.summarize(repo, item_id)
    n = summary.get("approach_edges", 0)
    since = summary.get("rework_edges_since_last_redesign",
                        summary["rework_edges"])
    cap = machine.MAX_APPROACH_REJECTIONS
    v = breaker.backlog_counts(repo, meta)
    priority = meta.get("priority", "-")
    at_or_above = v["at_or_above"]
    total = v["actionable_total"]
    unreadable = v["unreadable"]
    unpriced = v["unpriced"]
    comparable = at_or_above is not None
    dropped = (f"; {unreadable} item{'' if unreadable == 1 else 's'} "
               "unreadable and excluded" if unreadable else "")
    unknown_bits = []
    if unpriced:
        unknown_bits.append(
            f"{unpriced} actionable item{'' if unpriced == 1 else 's'} "
            "with no priority")
    if unreadable:
        unknown_bits.append(
            f"{unreadable} unreadable item{'' if unreadable == 1 else 's'}")
    unknown = " and ".join(unknown_bits)
    if comparable:
        at_s = "" if at_or_above == 1 else "s"
        backlog_line = (f"- backlog: {at_or_above} actionable item{at_s} "
                        f"at priority ≤ {priority}, {total} actionable "
                        f"in total{dropped}")
        recommended = "defer" if at_or_above >= 1 else "narrow"
        narrow_why = ("nothing else is waiting at this priority, so a "
                      "narrowed redesign costs less than another full "
                      "one.")
        if unknown:
            narrow_why = ("nothing comparable is waiting at this "
                          f"priority; {unknown} cannot be compared "
                          "either way, so the backlog is not established "
                          "as empty; a narrowed redesign costs less than "
                          "another full one.")
        why = {
            "defer": ("work at this priority or higher is waiting behind "
                      "an item that has already exhausted its redesign "
                      "cap."),
            "narrow": narrow_why,
        }[recommended]
        recommendation = f"Recommended: {recommended} — {why}"
    else:
        backlog_line = ("- backlog: comparison unavailable — this item "
                        f"has no priority; {total} actionable in "
                        f"total{dropped}")
        recommendation = ("Recommended: set a priority first — what this "
                          "item is blocking cannot be compared until it "
                          f"has one; run `factory priority {item_id} "
                          f"<n>`, then `factory packet {item_id}` to "
                          "re-render this decision.")
    forbidden = paths.item_dir(repo, item_id) / "approaches" / "forbidden.md"
    try:
        text = forbidden.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = ""
    headings = [ln.lstrip("#").strip() for ln in text.splitlines()
                if ln.startswith("##")]
    if headings:
        graveyard = ("- forbidden approaches (authored text, "
                     "approaches/forbidden.md): " + "; ".join(headings))
    else:
        graveyard = ("- forbidden approaches: approaches/forbidden.md "
                     "missing, empty or unreadable — the artifact gate "
                     "should have refused the redesign edge; inspect "
                     "the item dir")
    return [
        f"- [proxy] redesigns: {n} of {cap} (engine-counted "
        "approach.rejected edges; lifetime, never reset)",
        f"- [proxy] rework edges since last redesign: {since} "
        f"(cumulative {summary['rework_edges']} — the breaker counts "
        "the cumulative figure)",
        "- " + cost.render_lower_bound(summary),
        backlog_line,
        graveyard,
        "",
        recommendation,
        "",
        f"- continue — admits exactly one more redesign; the resumed "
        f"item re-issues the spec request at redesign {n + 1}, after "
        "which a further request is refused again; in loop mode the "
        "next actionable item runs while this one redesigns; in "
        "item/step mode the run stops here.",
        "- narrow — records the decision and leaves the item parked; "
        "narrow the spec by hand, then resume it yourself. v1 does not "
        "narrow scope for you.",
        f"- defer — records the decision and leaves the item parked; "
        f"drop its priority with `factory priority {item_id} <n>`. v1 "
        "does not re-prioritise for you.",
    ]


def respond_action_lines(repo, item_id, meta):
    """Exactly one copy-pasteable action, naming the verb that actually
    answers THIS pause. One branch, shared by both renderers, so the HTML
    can never tell a cost-breaker pause to run /factory:run."""
    from . import approach, breaker
    paused_from = meta.get("paused-from")
    reason = meta.get("paused-reason", "")
    if reason.startswith(approach.PAUSE_PREFIX):
        return [f"- `factory approach-answer {item_id} "
                "<continue|narrow|defer>` — record the redesign "
                "decision."]
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
        lines.append(f"- waiting on you: {waiting_line(meta, summary)}")
    decision = cost_decision_lines(repo, item_id, meta, summary)
    if decision:
        lines += ["", "## Cost decision", ""] + decision
    redesign = redesign_decision_lines(repo, item_id, meta, summary)
    if redesign:
        lines += ["", "## Redesign decision", ""] + redesign
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
    lines += redesign_population_lines(summary)
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


def _inline_code(text):
    """Escape a markdown line for HTML, rendering its backtick code
    spans as `<code>`. One definition, both renderers: the decision
    block used to escape its lines wholesale while `## Respond` did the
    split, and two renderers disagreeing on a command string is the
    class of bug this item exists to stop (F8).

    Assumes an even backtick count, and may: every caller passes a line
    built by `cost_decision_lines` or `respond_action_lines`, whose only
    interpolations are `item_id` (validated by `items`) and integers. No
    operator-authored text — the `paused-reason` free text in particular
    — reaches this function; `waiting_line`'s output is escaped with
    `_e()` directly. Route operator text through here and an odd
    backtick would wrap the tail of the line in `<code>`, so keep that
    invariant if a caller is ever added."""
    return "".join(f"<code>{_e(part)}</code>" if i % 2 else _e(part)
                   for i, part in enumerate(text.split("`")))


def _decision_section_html(out, section_id, title, lines):
    """Shared decision-block HTML: one loop, both decision sections,
    so the two renderers cannot diverge on list/paragraph handling.

    Deviation from plan (0016) Task 10 step 4: the section carries no
    class="ask" attribute, so the id selector the tests split on stays
    exact; the ask callout styling is attached to the section ids in
    the stylesheet instead."""
    out.append(f'  <section id="{section_id}">')
    out.append(f"    <h2>{title}</h2>")
    in_list = False
    for line in lines:
        if line.startswith("- "):
            if not in_list:
                out.append("    <ul>")
                in_list = True
            out.append(
                f"      <li>{_inline_code(line.removeprefix('- '))}</li>")
            continue
        if in_list:
            out.append("    </ul>")
            in_list = False
        if line.strip():
            out.append(
                f"    <p><strong>{_inline_code(line)}</strong></p>")
    if in_list:
        out.append("    </ul>")
    out.append("  </section>")


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
    decision = cost_decision_lines(repo, item_id, meta, summary)
    redesign = redesign_decision_lines(repo, item_id, meta, summary)

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
    if redesign:
        # Deviation from plan Task 7 step 3: the #redesign-decision
        # stylesheet selectors are added only when the section renders.
        # A static selector change would alter every packet's bytes and
        # regenerate the default-path golden packet.html, which the
        # global constraint (AC20; J-001 regression) forbids — the
        # golden is never regenerated by this item, so the default-path
        # stylesheet must stay byte-identical.
        out[0] = out[0].replace(
            ".ask, #cost-decision {",
            ".ask, #cost-decision, #redesign-decision {").replace(
            ".ask h2, #cost-decision h2 {",
            ".ask h2, #cost-decision h2, #redesign-decision h2 {")

    if meta.get("paused-reason"):
        out += ["  <section class=\"ask\" id=\"waiting-on-you\">",
                "    <h2>waiting on you</h2>",
                f"    <p>{_e(waiting_line(meta, summary))}</p>",
                "  </section>"]

    if decision:
        _decision_section_html(out, "cost-decision", "Cost decision",
                               decision)
    if redesign:
        _decision_section_html(out, "redesign-decision",
                               "Redesign decision", redesign)

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
    for line in redesign_population_lines(summary):
        out.append(f"      <li>{_e(line.removeprefix('- '))}</li>")
    out += ["    </ul>", "  </section>", "  <section id=\"respond\">",
            "    <h2>Respond</h2>",
            "    <p>Reply in session, or use the factory CLI.</p>",
            "    <ul>"]
    for line in respond_action_lines(repo, item_id, meta):
        out.append(f"      <li>{_inline_code(line.removeprefix('- '))}</li>")
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
