#!/usr/bin/env python3
"""Factory engine CLI. Exit codes: 0 ok, 1 usage/internal error, 2 gate
refusal or validation errors. Skills call this; humans can too."""

import argparse
import json
import sys

if __package__ in (None, ""):
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.factory.lib import initrepo, items, logs, machine, council, health as health_mod, prune as prune_mod, dispatch, packet as packet_mod
else:
    from .lib import initrepo, items, logs, machine, council, health as health_mod, prune as prune_mod, dispatch, packet as packet_mod


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
    metas, errors = items.list_items_safe(args.repo)
    rows = sorted(metas, key=lambda m: (m.get("priority", 9999), m["id"]))
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        for m in rows:
            priority = m.get("priority", "-")
            print(f"{m['id']:<40} {m['stage']:<14} p{priority:<4} {m['kind']}")
    for error in errors:
        print(error, file=sys.stderr)
    return 2 if errors else 0


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

    p = sub.add_parser("next", help="get the next actionable work item")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("packet", help="write a review packet for an item")
    p.add_argument("item")
    p.set_defaults(func=cmd_packet)

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:
            raise
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
