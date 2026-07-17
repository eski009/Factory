"""Journey-model readouts. The registry is progressive-depth by design
(inventory entries are legitimate); coverage debt makes the shallow end
explicit instead of letting it read as covered. Journey-assurance spec:
shallow or unmapped journeys are named debt, never silent."""

import json

from . import paths


def graph_path(repo):
    return paths.docs_root(repo) / "journeys" / "graph.json"


def coverage_debt(repo):
    """Count journeys by contract depth. Returns None when no graph exists
    (repo has no journey model yet — that absence is surfaced elsewhere);
    otherwise {"total", "inventory_only", "draft", "approved"} where
    inventory_only means no contract at all."""
    path = graph_path(repo)
    if not path.exists():
        return None
    try:
        graph = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    journeys = graph.get("journeys") if isinstance(graph, dict) else None
    if not isinstance(journeys, list):
        return None
    counts = {"total": 0, "inventory_only": 0, "draft": 0, "approved": 0}
    for j in journeys:
        if not isinstance(j, dict):
            continue
        counts["total"] += 1
        status = j.get("status")
        if status == "approved" and j.get("contract"):
            counts["approved"] += 1
        elif status == "draft" or (j.get("contract") and status != "approved"):
            counts["draft"] += 1
        else:
            counts["inventory_only"] += 1
    return counts
