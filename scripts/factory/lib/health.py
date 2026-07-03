"""Cheap deterministic memory-health check. Recommends prune/no-prune
with reasons; never mutates council files. Spec §6.
"""

import json

from . import council, logs, paths

THRESHOLDS = {"max_role_lines": 200, "max_duplicate_claims": 2,
              "max_unjudged_bids": 10}


def _role_stats(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    claims = [line for line in lines if line.startswith("- ")]
    seen, duplicates = set(), 0
    for claim in claims:
        if claim in seen:
            duplicates += 1
        seen.add(claim)
    return {"lines": len(lines), "claims": len(claims),
            "duplicate_claims": duplicates}


def compute_health(repo):
    roles = {}
    council_dir = paths.docs_root(repo) / "council"
    for path in sorted(council_dir.glob("*.md")):
        roles[path.stem] = _role_stats(path)
    bids = council.read_ledger(repo, "bids")
    judgements = council.read_ledger(repo, "judgements")
    judged_ids = {j["bid"] for j in judgements}
    ledgers = {
        "bids": len(bids),
        "judged": len(judged_ids),
        "unjudged": sum(1 for b in bids if b["id"] not in judged_ids),
        "deferred": sum(1 for j in judgements if j["decision"] == "defer"),
    }
    reasons = []
    for role, stats in sorted(roles.items()):
        if stats["lines"] > THRESHOLDS["max_role_lines"]:
            reasons.append(f"{role}: {stats['lines']} lines exceeds "
                           f"{THRESHOLDS['max_role_lines']}")
        if stats["duplicate_claims"] > THRESHOLDS["max_duplicate_claims"]:
            reasons.append(f"{role}: {stats['duplicate_claims']} duplicate claims "
                           f"exceeds {THRESHOLDS['max_duplicate_claims']}")
    if ledgers["unjudged"] > THRESHOLDS["max_unjudged_bids"]:
        reasons.append(f"{ledgers['unjudged']} unjudged bids exceeds "
                       f"{THRESHOLDS['max_unjudged_bids']}")
    return {
        "ts": logs.now_stamp(),
        "roles": roles,
        "ledgers": ledgers,
        "recommendation": "prune" if reasons else "ok",
        "reasons": reasons,
    }


def write_health(repo):
    report = compute_health(repo)
    path = paths.factory_root(repo) / "memory-health.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path
