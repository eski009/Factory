"""Provenance-preserving prune of council role files.

Invariant: kept + archived == input (nothing silently erased). Only
exact-duplicate claim lines are archived; prose is never touched.
Spec §6.
"""

from . import logs, paths
from .council import ROLES, CouncilError


def propose(lines):
    kept, archived, seen = [], [], set()
    for line in lines:
        if line.startswith("- ") and line in seen:
            archived.append(line)
        else:
            if line.startswith("- "):
                seen.add(line)
            kept.append(line)
    return kept, archived


def prune_role(repo, role, apply=False):
    if role not in ROLES:
        raise CouncilError(f"unknown role {role!r}; one of {ROLES}")
    path = paths.docs_root(repo) / "council" / f"{role}.md"
    if not path.exists():
        raise CouncilError("role file missing - run init")
    lines = path.read_text(encoding="utf-8").splitlines()
    kept, archived = propose(lines)
    archive_path = None
    if apply and archived:
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        archive = paths.factory_root(repo) / "pruning" / f"{role}.md"
        archive.parent.mkdir(parents=True, exist_ok=True)
        with archive.open("a", encoding="utf-8") as f:
            f.write(f"## pruned {logs.now_stamp()}\n")
            f.write("\n".join(archived) + "\n")
        archive_path = str(archive)
    return {"role": role, "kept": len(kept), "archived": len(archived),
            "archive_path": archive_path}
