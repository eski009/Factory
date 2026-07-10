"""Render mobile-legible review packets for humans. Spec §5, §9."""

from . import cost, items, logs, paths

ARTIFACTS = ("triage.md", "spec.md", "plan.md", "design/choice.md",
             "reviews/synthesis.md")


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
    lines += ["", "## Artifacts"]
    for rel in ARTIFACTS:
        exists = (item_dir / rel).exists()
        lines.append(f"- {rel}: {'yes' if exists else 'no'}")
    lines += ["", "## Recent events"]
    for event in logs.read_events(repo, item_id)[-5:]:
        lines.append(f"- {event['ts']} {event['event']}"
                     + (f" {event['data']}" if "data" in event else ""))
    lines += ["", "## Spend"]
    lines += cost.render_receipt(cost.summarize(repo, item_id)).splitlines()
    lines += ["", "## Respond",
              "Reply in session, or use the factory CLI to record your",
              "decision (for a design pause: `factory choice <id> <option>`),",
              "then run `/factory:run` to resume.", ""]
    return "\n".join(lines)


def write_packet(repo, item_id):
    path = paths.docs_root(repo) / "packets" / f"{item_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_packet(repo, item_id), encoding="utf-8")
    return path
