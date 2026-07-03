#!/usr/bin/env python3
"""Factory engine CLI. Exit codes: 0 ok, 1 usage/internal error, 2 gate
refusal or validation errors. Skills call this; humans can too."""

import argparse
import json
import sys

if __package__ in (None, ""):
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.factory.lib import initrepo, items, logs, machine
else:
    from .lib import initrepo, items, logs, machine


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
    items.save_item(args.repo, meta, f"# {args.title}\n")
    logs.append_event(args.repo, item_id, "item.created")
    print(item_id)
    return 0


def cmd_status(args):
    rows = sorted(items.list_items(args.repo),
                  key=lambda m: (m.get("priority", 9999), m["id"]))
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        for m in rows:
            priority = m.get("priority", "-")
            print(f"{m['id']:<40} {m['stage']:<14} p{priority:<4} {m['kind']}")
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
