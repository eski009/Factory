#!/usr/bin/env python3
"""Factory engine CLI. Exit codes: 0 ok, 1 usage/internal error, 2 gate
refusal or validation errors. Skills call this; humans can too."""

import argparse
import json
import sys

if __package__ in (None, ""):
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.factory.lib import initrepo, items, logs, machine, council, health as health_mod, prune as prune_mod, dispatch, packet as packet_mod, design as design_mod, doctor as doctor_mod, paths, cost, work, pool
else:
    from .lib import initrepo, items, logs, machine, council, health as health_mod, prune as prune_mod, dispatch, packet as packet_mod, design as design_mod, doctor as doctor_mod, paths, cost, work, pool


def _require_factory_repo(repo):
    if not paths.config_path(repo).exists():
        print("not a factory repo (run init)", file=sys.stderr)
        return False
    return True


def cmd_init(args):
    for path in initrepo.init(args.repo, product=args.product):
        print(path)
    return 0


def cmd_validate(args):
    errors = initrepo.validate_tree(args.repo)
    for error in errors:
        print(error, file=sys.stderr)
    return 2 if errors else 0


def cmd_add(args):
    if not _require_factory_repo(args.repo):
        return 2
    if not args.title.strip():
        print("error: title must not be empty", file=sys.stderr)
        return 1
    item_id = items.new_item_id(args.repo, args.title)
    now = logs.now_stamp()
    meta = {"id": item_id, "title": args.title, "stage": "idea",
            "kind": args.kind, "created": now, "updated": now}
    try:
        items.save_item(args.repo, meta, f"# {args.title}\n")
    except items.ItemError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    logs.append_event(args.repo, item_id, "item.created")
    print(item_id)
    return 0


def cmd_status(args):
    if not _require_factory_repo(args.repo):
        return 2
    metas, errors = items.list_items_safe(args.repo)
    rows = sorted(metas, key=lambda m: (m.get("priority", 9999), m["id"]))
    if args.json:
        for m in rows:
            spend = cost.summarize(args.repo, m["id"])
            spend.pop("stages", None)
            m["spend"] = spend
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        corrupt_total = 0
        corrupt_items = 0
        for m in rows:
            priority = m.get("priority", "-")
            print(f"{m['id']:<40} {m['stage']:<14} p{priority:<4} {m['kind']}")
            _, skipped = logs.read_events_with_stats(args.repo, m["id"])
            if skipped:
                corrupt_total += skipped
                corrupt_items += 1
        if corrupt_total:
            # One aggregated notice, count-after-label; per-item detail
            # lives in factory cost. Exit code unchanged. Item spec 0009 §3.
            print(f"corrupt log lines: {corrupt_total} across "
                  f"{corrupt_items} items (skipped; run factory validate)",
                  file=sys.stderr)
    for error in errors:
        print(error, file=sys.stderr)
    return 2 if errors else 0


def cmd_cost(args):
    try:
        summary = cost.summarize(args.repo, args.item)
    except items.ItemError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(cost.render_text(summary))
    return 0


def cmd_work(args):
    if not _require_factory_repo(args.repo):
        return 2
    code, result = work.run_work(
        args.repo, args.item, backend=args.backend, model=args.model,
        timeout=args.timeout, network=args.network, worktree=args.worktree)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif code == 0:
        print(f"{args.item} done ({result.get('backend')}): "
              f"{len(result.get('commits', []))} commit(s)")
    else:
        print(result.get("error")
              or f"{args.item} {result.get('status', 'failed')}: "
                 f"{result.get('reason')}", file=sys.stderr)
    return code


def cmd_provision(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        items.load_item(args.repo, args.item)
    except items.ItemError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    result = pool.provision(args.repo, args.item, backend=args.backend)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result.get("prepared"):
        print(f"{args.item} provisioned: {result['worktree']}")
    else:
        print(f"{args.item} prep failed: {result.get('detail', '')}",
              file=sys.stderr)
    return 0 if result.get("prepared") else 1


def cmd_cleanup(args):
    if not _require_factory_repo(args.repo):
        return 2
    result = pool.cleanup(args.repo, args.item)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        state = "cleaned" if result["removed"] else "nothing to remove"
        kept = " (branch kept)" if result["branch_kept"] else ""
        print(f"{args.item} {state}{kept}")
    return 0


def cmd_advance(args):
    try:
        machine.advance(args.repo, args.item, args.stage, reason=args.reason)
    except (machine.GateError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.item} -> {args.stage}")
    return 0


def cmd_log(args):
    data = None
    if args.data:
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as exc:
            print(f"--data is not valid JSON: {exc}", file=sys.stderr)
            return 1
    try:
        items.load_item(args.repo, args.item)
    except items.ItemError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    logs.append_event(args.repo, args.item, args.event, data)
    return 0


def cmd_bid(args):
    try:
        bid = council.file_bid(args.repo, agent=args.agent, topic=args.topic,
                               claim=args.claim, evidence=args.evidence or [],
                               surface=args.surface, severity=args.severity,
                               item=args.item or "")
    except council.CouncilError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(bid["id"])
    return 0


def cmd_judge(args):
    try:
        jdg, rep = council.record_judgement(args.repo, args.bid, args.decision,
                                            args.reason, surface=args.surface,
                                            anchor=args.anchor)
    except council.CouncilError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.bid} -> {jdg['decision']} "
          f"(rep {rep['agent']}/{rep['topic']} {rep['delta']:+.2f})")
    return 0


def cmd_reputation(args):
    table = council.reputation_table(args.repo)
    _, skipped = council.read_ledger_with_stats(args.repo, "reputation")
    if skipped:
        print(f"ledgers/reputation.jsonl: corrupt lines skipped: {skipped} "
              "(run factory validate)", file=sys.stderr)
    if args.json:
        print(json.dumps(table, indent=2, sort_keys=True))
    else:
        for key in sorted(table):
            print(f"{key:<40} {table[key]:+.2f}")
    return 0


def cmd_health(args):
    path = health_mod.write_health(args.repo)
    report = json.loads(path.read_text(encoding="utf-8"))
    print(f"recommendation: {report['recommendation']}")
    for reason in report["reasons"]:
        print(f"- {reason}")
    return 0


def cmd_prune(args):
    try:
        result = prune_mod.prune_role(args.repo, args.role, apply=args.apply)
    except council.CouncilError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"kept: {result['kept']} archived: {result['archived']}"
          + (f" -> {result['archive_path']}" if result["archive_path"] else ""))
    return 0


def cmd_next(args):
    if not _require_factory_repo(args.repo):
        return 2
    metas, errors = items.list_items_safe(args.repo)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 2
    if args.count is not None:
        rows = dispatch.next_items(args.repo, args.count)
        if args.json:
            print(json.dumps(rows, indent=2, sort_keys=True))
        elif not rows:
            print("nothing actionable")
        else:
            for m in rows:
                print(f"{m['id']} {m['stage']}")
        return 0
    meta = dispatch.next_item(args.repo)
    if args.json:
        print(json.dumps(meta, indent=2, sort_keys=True))
    elif meta is None:
        print("nothing actionable")
    else:
        print(f"{meta['id']} {meta['stage']}")
    return 0


def cmd_packet(args):
    try:
        path = packet_mod.write_packet(args.repo, args.item)
    except items.ItemError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(path)
    return 0


def cmd_choice(args):
    try:
        path = design_mod.record_choice(args.repo, args.item, args.option,
                                        notes=args.notes)
    except (machine.GateError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(path)
    return 0


def cmd_priority(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        items.set_priority(args.repo, args.item, args.priority)
    except items.ItemError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.item} priority {args.priority}")
    return 0


def cmd_doctor(args):
    report = doctor_mod.report(args.repo)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(doctor_mod.render(report))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="factory")
    parser.add_argument("--repo", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="scaffold .factory/ and docs/factory/")
    p.add_argument("--product")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("validate", help="check the whole state tree")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("add", help="create a work item at stage idea")
    p.add_argument("title")
    p.add_argument("--kind", choices=items.KINDS, default="mixed")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("status", help="list items by priority")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("cost", help="per-item spend summary, provenance-tagged")
    p.add_argument("item")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cost)

    p = sub.add_parser("advance", help="move an item to a stage (gate-checked)")
    p.add_argument("item")
    p.add_argument("stage")
    p.add_argument("--reason")
    p.set_defaults(func=cmd_advance)

    p = sub.add_parser("log", help="append an evidence event to an item's log")
    p.add_argument("item")
    p.add_argument("event")
    p.add_argument("--data")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("bid", help="file an escalation bid")
    p.add_argument("agent")
    p.add_argument("topic")
    p.add_argument("claim")
    p.add_argument("--evidence", action="append", required=True)
    p.add_argument("--surface", required=True)
    p.add_argument("--severity", required=True, choices=["low", "medium", "high"])
    p.add_argument("--item", default="")
    p.set_defaults(func=cmd_bid)

    p = sub.add_parser("judge", help="record the orchestrator judgement for a bid")
    p.add_argument("bid")
    p.add_argument("decision")
    p.add_argument("--reason", required=True)
    p.add_argument("--surface")
    p.add_argument("--anchor")
    p.set_defaults(func=cmd_judge)

    p = sub.add_parser("reputation", help="derived reputation per agent/topic")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_reputation)

    p = sub.add_parser("health", help="write memory-health.json and print recommendation")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("prune", help="propose/apply provenance-preserving prune")
    p.add_argument("role")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_prune)

    p = sub.add_parser("next", help="get the next actionable work item(s)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--count", "-n", type=int,
                   help="return up to N top actionable items (as a list)")
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("work",
                       help="run one headless worker for an item at implement")
    p.add_argument("item")
    p.add_argument("--backend", choices=["claude", "codex", "stub"])
    p.add_argument("--model")
    p.add_argument("--timeout", type=int)
    p.add_argument("--network", choices=["on", "off"])
    p.add_argument("--worktree")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_work)

    p = sub.add_parser("provision",
                       help="prepare an item's worktree for a headless worker")
    p.add_argument("item")
    p.add_argument("--backend", choices=["claude", "codex", "stub"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_provision)

    p = sub.add_parser("cleanup",
                       help="remove an item's worker worktree (branch kept)")
    p.add_argument("item")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cleanup)

    p = sub.add_parser("packet", help="write a review packet for an item")
    p.add_argument("item")
    p.set_defaults(func=cmd_packet)

    p = sub.add_parser("choice", help="record the human's design-option pick")
    p.add_argument("item")
    p.add_argument("option")
    p.add_argument("--notes")
    p.set_defaults(func=cmd_choice)

    p = sub.add_parser("priority", help="set an item's priority (1+)")
    p.add_argument("item")
    p.add_argument("priority", type=int)
    p.set_defaults(func=cmd_priority)

    p = sub.add_parser("doctor", help="readout of repo integration state")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:
            raise
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
