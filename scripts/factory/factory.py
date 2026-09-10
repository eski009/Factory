#!/usr/bin/env python3
"""Factory engine CLI. Exit codes: 0 ok, 1 usage/internal error, 2 gate
refusal or validation errors. Skills call this; humans can too."""

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.factory.lib import initrepo, items, logs, machine, council, health as health_mod, prune as prune_mod, dispatch, packet as packet_mod, design as design_mod, doctor as doctor_mod, paths, cost, work, pool, assure as assure_mod, escapes as escapes_mod, journeys as journeys_mod, breaker, approach, ownership, config_state, control, feasibility, safeio, reconciliation, convergence, ledger as ledger_mod
else:
    from .lib import initrepo, items, logs, machine, council, health as health_mod, prune as prune_mod, dispatch, packet as packet_mod, design as design_mod, doctor as doctor_mod, paths, cost, work, pool, assure as assure_mod, escapes as escapes_mod, journeys as journeys_mod, breaker, approach, ownership, config_state, control, feasibility, safeio, reconciliation, convergence, ledger as ledger_mod


IMPLEMENTATION_OWNER_ENV = "FACTORY_IMPLEMENTATION_OWNER"


class _OwnershipInheritanceOps:
    """Read-only ops which cannot send inherited acquire down create path."""

    def __init__(self, state):
        self.state = state

    @staticmethod
    def read_bytes(path):
        return path.read_bytes()

    def exists(self, path):
        if path == self.state:
            return True
        return path.exists()


def _require_factory_repo(repo):
    if not paths.config_path(repo).exists():
        print("not a factory repo (run init)", file=sys.stderr)
        return False
    return True


def cmd_init(args):
    for path in initrepo.init(
            args.repo, product=args.product,
            design_provider=args.design_provider,
            designsync_project=args.designsync_project):
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
    if getattr(args, "tier", None):
        meta["tier"] = args.tier
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
            m["tier"] = items.item_tier(m)
            assurance = items.assurance_mode(args.repo, m["id"])
            if assurance:
                m["assurance"] = assurance
            spend = cost.summarize(args.repo, m["id"])
            spend.pop("stages", None)
            m["spend"] = spend
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        corrupt_total = 0
        corrupt_items = 0
        for m in rows:
            priority = m.get("priority", "-")
            print(f"{m['id']:<40} {m['stage']:<14} p{priority:<4} "
                  f"{items.item_tier(m)}/{m['kind']}")
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
        open_esc = escapes_mod.open_escapes(args.repo)
        if open_esc:
            print(f"open escapes: {len(open_esc)} "
                  "(promote each into a contract/test/oracle/rule/decision)")
        debt = journeys_mod.coverage_debt(args.repo)
        if debt and (debt["inventory_only"] or debt["draft"]):
            print(f"journey coverage debt: {debt['inventory_only']} of "
                  f"{debt['total']} journeys inventory-only, "
                  f"{debt['draft']} draft contracts "
                  "(deep contracts exist only where they earn their keep; "
                  "this line is the honest remainder)")
    for error in errors:
        print(error, file=sys.stderr)
    return 2 if errors else 0


def cmd_cost(args):
    # Neither given, or both given, is the same refusal: an aggregate view
    # and an item view answer different questions and never merge.
    if bool(args.all) == bool(args.item):
        print("give an item id or --all", file=sys.stderr)
        return 2
    if args.all:
        if not _require_factory_repo(args.repo):
            return 2
        summary = cost.summarize_all(args.repo)
        if args.json:
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            print(cost.render_all_text(summary))
        return 0
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


def cmd_ledger(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        summary = ledger_mod.summarize(
            args.repo, args.base, args.head,
            product_paths=args.product_path,
            admin_paths=args.admin_path)
    except ledger_mod.LedgerError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(ledger_mod.render_text(summary))
    return 0


def cmd_work(args):
    if not _require_factory_repo(args.repo):
        return 2
    code, result = work.run_work(
        args.repo, args.item, backend=args.backend, model=args.model,
        timeout=args.timeout, network=args.network, worktree=args.worktree,
        reasoning_effort=args.reasoning_effort)
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


def cmd_plan_check(args):
    # A present but hostile/missing config inside an initialized namespace is
    # a structured plan-check failure, not a misleading "not a repo" result.
    if not paths.factory_root(args.repo).is_dir():
        _require_factory_repo(args.repo)
        return 2
    try:
        config = config_state.capture(args.repo)
        report = feasibility.inspect(args.repo, args.item, config=config)
    except config_state.ConfigStateError as exc:
        report = {
            "status": "fail", "item": args.item,
            "spec_sha256": None, "plan_structure_sha256": None,
            "cursor": None, "task": None, "owned_paths": [],
            "delivery": None, "errors": [str(exc)], "handoff": None,
        }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif report["status"] == "pass":
        print(f"{args.item}: feasible ({report['cursor']})")
    elif report["status"] == "disabled":
        print(f"{args.item}: feasibility disabled")
    else:
        for error in report["errors"]:
            print(f"refused: {error}", file=sys.stderr)
    return 2 if report["status"] == "fail" else 0


def cmd_plan_dispatch(args):
    if not paths.factory_root(args.repo).is_dir():
        _require_factory_repo(args.repo)
        return 2
    token = os.environ.get(IMPLEMENTATION_OWNER_ENV)
    try:
        config = config_state.capture(args.repo)
        dispatch_snapshot = feasibility.prepare_dispatch(
            args.repo, args.item, config=config, owner_token=token,
            tasks=args.task)
    except (config_state.ConfigStateError,
            feasibility.FeasibilityError) as exc:
        if args.json:
            print(json.dumps({
                "status": "fail", "item": args.item, "error": str(exc),
            }, indent=2, sort_keys=True))
        else:
            print(f"refused: {exc}", file=sys.stderr)
        return 2
    result = {
        "status": "pass",
        "item": args.item,
        "ticket_id": dispatch_snapshot.ticket.ticket_id,
        "tasks": list(dispatch_snapshot.tasks),
        "handoff": dispatch_snapshot.handoff,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{args.item}: dispatch ticket {result['ticket_id']}")
    return 0


def cmd_plan_finalize(args):
    if not paths.factory_root(args.repo).is_dir():
        _require_factory_repo(args.repo)
        return 2
    token = os.environ.get(IMPLEMENTATION_OWNER_ENV)
    try:
        result = feasibility.finalize_tasks(
            args.repo, args.item, ticket_id=args.ticket,
            owner_token=token)
    except feasibility.FeasibilityError as exc:
        if args.json:
            print(json.dumps({
                "status": "fail", "item": args.item, "error": str(exc),
            }, indent=2, sort_keys=True))
        else:
            print(f"refused: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{args.item}: finalized {result['cursor']}")
    return 0


def cmd_plan_rework(args):
    if not paths.factory_root(args.repo).is_dir():
        _require_factory_repo(args.repo)
        return 2
    try:
        config = config_state.capture(args.repo)
        source_snapshot = safeio.snapshot_path(args.repo, args.source_file)
        plan_proposal = safeio.snapshot_path(args.repo, args.plan_proposal)
        acceptance_proposal = safeio.snapshot_path(
            args.repo, args.acceptance_proposal)
        key = feasibility.rework_operation_key(
            args.source, source_snapshot, args.finding)
        receipt = control.adopt_operation(
            args.repo, args.item, kind="implement-entry", key=key)
        if receipt is None:
            prepared = feasibility.prepare_rework_entry(
                args.repo, args.item, config=config, source=args.source,
                source_snapshot=source_snapshot,
                finding_ids=args.finding, plan_proposal=plan_proposal,
                acceptance_proposal=acceptance_proposal)
            _meta, _verdict, receipt = machine.commit_implement_entry(prepared)
    except (config_state.ConfigStateError, control.ControlError,
            feasibility.FeasibilityError, safeio.SafeIOError) as exc:
        if args.json:
            print(json.dumps({
                "status": "fail", "item": args.item, "error": str(exc),
            }, indent=2, sort_keys=True))
        else:
            print(f"refused: {exc}", file=sys.stderr)
        return 2
    result = {
        "status": "pass", "item": args.item,
        "operation_id": receipt.operation_id,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{args.item}: rework prepared {receipt.operation_id}")
    return 0


def cmd_provision(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        items.load_item(args.repo, args.item)
    except items.ItemError as exc:
        if args.json:
            print(json.dumps({"item": args.item, "prepared": False,
                              "error": str(exc)}, indent=2, sort_keys=True))
        else:
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


def _ownership_error(exc):
    print(f"refused: {exc}", file=sys.stderr)
    return 2


def _required_owner_token(item_id, action):
    token = os.environ.get(IMPLEMENTATION_OWNER_ENV)
    if not token:
        raise ownership.OwnershipRefusal(
            f"{item_id}: ownership {action} requires "
            f"{IMPLEMENTATION_OWNER_ENV}")
    return token


def _acquire_ownership(args):
    token = os.environ.get(IMPLEMENTATION_OWNER_ENV)
    if token:
        state = ownership.owner_state_path(args.repo, args.item)
        claim = ownership.acquire(
            args.repo, args.item, supplied=args.worktree,
            owner_token=token, ops=_OwnershipInheritanceOps(state))
    else:
        claim = ownership.acquire(
            args.repo, args.item, supplied=args.worktree)
    if args.json:
        print(json.dumps({
            "canonical_worktree": str(claim.checkout),
            "owner_token": claim.token,
            "inherited": claim.inherited,
        }, indent=2, sort_keys=True))
    else:
        verb = "inherited" if claim.inherited else "acquired"
        print(f"{args.item}: ownership {verb} for {claim.checkout}")
    return 0


def _check_ownership(args):
    token = _required_owner_token(args.item, "check")
    verified = ownership.verify(
        args.repo, args.item, token, supplied=args.worktree)
    checkout = verified.checkout
    if args.json:
        print(json.dumps({
            "canonical_worktree": str(checkout),
            "owned": True,
        }, indent=2, sort_keys=True))
    else:
        print(f"{args.item}: ownership verified for {checkout}")
    return 0


def _release_ownership(args):
    token = _required_owner_token(args.item, "release")
    checkout = ownership.canonical_worktree(
        args.repo, args.item, args.worktree)
    ownership.release(args.repo, args.item, checkout, token)
    if args.json:
        print(json.dumps({
            "canonical_worktree": str(checkout),
            "released": True,
        }, indent=2, sort_keys=True))
    else:
        print(f"{args.item}: ownership released for {checkout}")
    return 0


def cmd_ownership(args):
    actions = {
        "acquire": _acquire_ownership,
        "check": _check_ownership,
        "release": _release_ownership,
    }
    try:
        return actions[args.ownership_command](args)
    except (ownership.OwnershipRefusal,
            ownership.OwnershipReleaseError) as exc:
        return _ownership_error(exc)


def cmd_advance(args):
    try:
        _meta, verdict = machine.advance(args.repo, args.item, args.stage,
                                         reason=args.reason)
    except (machine.GateError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    # Always the REQUESTED stage: a silent redirect stays unimplementable
    # rather than merely inelegant.
    print(f"{args.item} -> {args.stage}")
    if verdict["fired"]:
        print(f"cost breaker: {verdict['rework_edges']} rework edges "
              f"(threshold {verdict['threshold']}) — park and answer "
              "before the next implement round")
        print(f"next: factory cost-answer {args.item} "
              "<continue|narrow|defer>")
    return 0


def cmd_log(args):
    data = None
    if args.data:
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as exc:
            print(f"--data is not valid JSON: {exc}", file=sys.stderr)
            return 1
    if args.event == items.BUG_ASSURANCE_EVENT:
        print(f"{args.event} is written only by factory bug-assurance",
              file=sys.stderr)
        return 1
    if args.event == "approach.judgement.recorded":
        print("approach.judgement.recorded is written only by factory "
              "approach-judgement", file=sys.stderr)
        return 1
    if args.event == "stage.advance":
        print("stage.advance is written only by factory advance",
              file=sys.stderr)
        return 1
    if args.event in ("assure.waived", "assure.confirmed", "cost.answered",
                      "approach.answered"):
        print(f"{args.event} is written only by its human verb "
              "(factory waive / factory confirm / factory cost-answer / "
              "factory approach-answer)",
              file=sys.stderr)
        return 1
    if (args.event in ("stage.advance", "verify.green") or
            args.event.startswith("evidence.") or
            args.event.startswith("control.")):
        print(f"{args.event} is written only by the Factory engine",
              file=sys.stderr)
        return 1
    if args.event == "spend":
        errors = initrepo.spend_write_errors(data, "spend")
        if errors:
            for error in errors:
                print(f"refused: {error}", file=sys.stderr)
            return 2
    try:
        items.load_item(args.repo, args.item)
    except items.ItemError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    evidence_errors = initrepo.structured_event_errors(
        args.event, data, "--data", repo=args.repo)
    try:
        existing_events = logs.read_events(args.repo, args.item)
    except (OSError, UnicodeError) as exc:
        print(f"cannot inspect existing event ids: {exc}", file=sys.stderr)
        return 1
    evidence_errors.extend(initrepo.structured_id_conflict_errors(
        args.event, data, existing_events, "--data"))
    if evidence_errors:
        for error in evidence_errors:
            print(error, file=sys.stderr)
        return 1
    logs.append_event(args.repo, args.item, args.event, data)
    return 0


def cmd_bug_assurance(args):
    try:
        mode = items.record_bug_assurance(args.repo, args.item)
    except items.ItemError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.item} assurance {mode}")
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


def cmd_cost_answer(args):
    try:
        path = breaker.record_answer(args.repo, args.item, args.answer,
                                     notes=args.notes)
    except (machine.GateError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(path)
    return 0


def cmd_approach_answer(args):
    try:
        path = approach.record_answer(args.repo, args.item, args.answer,
                                      notes=args.notes)
    except (machine.GateError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(path)
    return 0


def cmd_approach_context(args):
    try:
        context = convergence.current_context(args.repo, args.item)
    except (convergence.ConvergenceError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(context, indent=2, sort_keys=True))
    return 0


def cmd_approach_judgement(args):
    try:
        record = json.loads(args.data)
    except json.JSONDecodeError as exc:
        print(f"--data is not valid JSON: {exc}", file=sys.stderr)
        return 1
    try:
        path = convergence.record_judgement(args.repo, args.item, record)
    except (convergence.ConvergenceError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(path.relative_to(Path(args.repo)))
    return 0


def cmd_waive(args):
    try:
        assure_mod.record_waiver(args.repo, args.item, args.reason)
    except (machine.GateError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.item} assurance waived")
    return 0


def cmd_confirm(args):
    try:
        path = assure_mod.record_confirmation(args.repo, args.item)
    except (machine.GateError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(path)
    return 0


def cmd_file_base_defect(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        owner, _deduped = assure_mod.file_base_defect(
            args.repo, args.item, args.journey, args.scenario,
            args.fingerprint, args.title,
            expected=args.expected or "", actual=args.actual or "")
    except (machine.GateError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(owner)
    return 0


def cmd_escape(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        entry = escapes_mod.file_escape(
            args.repo, args.journey, args.finding, args.miss_type,
            item=args.item or "", node=args.node or "",
            evidence=args.evidence or [])
    except escapes_mod.EscapeError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(entry["id"])
    return 0


def cmd_promote(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        escapes_mod.promote(args.repo, args.escape, args.via)
    except escapes_mod.EscapeError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.escape} promoted -> {args.via}")
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


def cmd_tier(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        items.set_tier(args.repo, args.item, args.tier)
    except items.ItemError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.item} tier {args.tier}")
    return 0


def cmd_journeys(args):
    if not _require_factory_repo(args.repo):
        return 2
    try:
        items.set_journeys(args.repo, args.item, args.value)
    except items.ItemError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.item} journeys {args.value}")
    return 0


def cmd_doctor(args):
    report = doctor_mod.report(args.repo)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(doctor_mod.render(report))
    return 0


def _reconcile_json(value):
    print(json.dumps(value, indent=2, sort_keys=True))


def _validate_reconcile_arguments(args):
    """Separate malformed CLI input from unsafe observed repository state."""
    reconciliation._safe_component(args.item, "item id")
    if args.reconcile_command in ("begin", "discover"):
        if (not args.stage.strip() or args.stage != args.stage.strip()):
            raise reconciliation.ReconciliationError(
                "stage must be a non-empty trimmed string")
        if (not args.obligation.strip()
                or args.obligation != args.obligation.strip()):
            raise reconciliation.ReconciliationError(
                "obligation must be a non-empty trimmed string")
        inputs = reconciliation._normalize_paths(args.input, "inputs")
        if args.reconcile_command == "begin":
            evidence = reconciliation._normalize_paths(
                args.evidence, "evidence")
            reconciliation._reject_overlapping_paths(inputs, evidence)
    elif (len(args.attempt) != 32
          or any(character not in "0123456789abcdef"
                 for character in args.attempt)):
        raise reconciliation.ReconciliationError(
            "invalid reconciliation attempt id")
    if (args.reconcile_command == "inspect"
            and args.claim_continuation
            and args.writer_state != "terminal"):
        raise reconciliation.ReconciliationError(
            "--claim-continuation requires a terminal writer")


def cmd_reconcile(args):
    try:
        _validate_reconcile_arguments(args)
    except reconciliation.ReconciliationError as exc:
        _reconcile_json({"error": str(exc)})
        return 1

    try:
        if args.reconcile_command == "begin":
            result = reconciliation.begin(
                args.repo, args.item, args.stage, args.obligation,
                args.input, args.evidence, worktree=args.worktree)
        elif args.reconcile_command == "discover":
            result = reconciliation.discover(
                args.repo, args.item, args.stage, args.obligation,
                args.input, worktree=args.worktree)
        else:
            result = reconciliation.inspect(
                args.repo, args.item, args.attempt, args.writer_state,
                worktree=args.worktree)
            if result["classification"] == "contradictory":
                _reconcile_json(result)
                return 2
            if (args.claim_continuation
                    and result["classification"] == "partial"
                    and result["action"] == "continue"):
                claim = reconciliation.claim_continuation(
                    args.repo, args.item, args.attempt, result)
                if claim["action"] == "stop":
                    result = dict(
                        result, action="stop", reason=claim["reason"])
    except reconciliation.PublicationUncertain as exc:
        _reconcile_json({"error": str(exc)})
        return 2
    except reconciliation.ReconciliationError as exc:
        _reconcile_json({"error": str(exc)})
        return 2
    except Exception as exc:
        _reconcile_json({"error": str(exc)})
        return 1

    _reconcile_json(result)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="factory")
    parser.add_argument("--repo", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="scaffold .factory/ and docs/factory/")
    p.add_argument("--product")
    p.add_argument("--design-provider", choices=["codex", "claude-design"])
    p.add_argument("--designsync-project")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("validate", help="check the whole state tree")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("add", help="create a work item at stage idea")
    p.add_argument("title")
    p.add_argument("--kind", choices=items.KINDS, default="mixed")
    p.add_argument("--tier", choices=list(items.TIERS))
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("status", help="list items by priority")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("cost", help="per-item spend summary, provenance-tagged")
    p.add_argument("item", nargs="?")
    p.add_argument("--all", action="store_true",
                   help="aggregate mode: every item, no cross-item totals")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cost)

    p = sub.add_parser(
        "ledger", help="read-only run-bounded delivery and evidence ledger")
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--product-path", action="append", default=[])
    p.add_argument("--admin-path", action="append", default=[])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ledger)

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

    p = sub.add_parser(
        "bug-assurance",
        help="record the immutable verify-substitution selected by bug intake")
    p.add_argument("item")
    p.set_defaults(func=cmd_bug_assurance)

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
    p.add_argument("--reasoning-effort",
                   choices=["low", "medium", "high", "xhigh", "max", "ultra"])
    p.add_argument("--timeout", type=int)
    p.add_argument("--network", choices=["on", "off"])
    p.add_argument("--worktree")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_work)

    p = sub.add_parser(
        "plan-check", help="validate an item's declared implementation plan")
    p.add_argument("item")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_plan_check)

    p = sub.add_parser(
        "plan-dispatch", help="issue an owner-bound implementation ticket")
    p.add_argument("item")
    p.add_argument("--task", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_plan_dispatch)

    p = sub.add_parser(
        "plan-finalize", help="atomically finalize a plan dispatch")
    p.add_argument("item")
    p.add_argument("--ticket", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_plan_finalize)

    p = sub.add_parser(
        "plan-rework", help="atomically install source-linked rework")
    p.add_argument("item")
    p.add_argument("--source", required=True,
                   choices=["review", "verify", "assure"])
    p.add_argument("--source-file", required=True)
    p.add_argument("--finding", action="append", required=True)
    p.add_argument("--plan-proposal", required=True)
    p.add_argument("--acceptance-proposal", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_plan_rework)

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

    p = sub.add_parser("ownership", help="engine-owned implementation checkout claim")
    subown = p.add_subparsers(dest="ownership_command", required=True)
    for name in ("acquire", "release", "check"):
        own = subown.add_parser(name)
        own.add_argument("item")
        own.add_argument("--worktree")
        own.add_argument("--json", action="store_true")
        own.set_defaults(func=cmd_ownership)

    p = sub.add_parser("packet", help="write a review packet for an item")
    p.add_argument("item")
    p.set_defaults(func=cmd_packet)

    p = sub.add_parser("choice", help="record the human's design-option pick")
    p.add_argument("item")
    p.add_argument("option")
    p.add_argument("--notes")
    p.set_defaults(func=cmd_choice)

    p = sub.add_parser("cost-answer",
                       help="record the human's cost-breaker decision")
    p.add_argument("item")
    p.add_argument("answer", choices=list(breaker.ANSWERS))
    p.add_argument("--notes")
    p.set_defaults(func=cmd_cost_answer)

    p = sub.add_parser("approach-answer",
                       help="record the human's redesign-cap decision")
    p.add_argument("item")
    p.add_argument("answer", choices=list(approach.ANSWERS))
    p.add_argument("--notes")
    p.set_defaults(func=cmd_approach_answer)

    p = sub.add_parser(
        "approach-context",
        help="show the current plan round, hash, tier budget and record path")
    p.add_argument("item")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_approach_context)

    p = sub.add_parser(
        "approach-judgement",
        help="validate and record current-plan approach evidence")
    p.add_argument("item")
    p.add_argument("--data", required=True)
    p.set_defaults(func=cmd_approach_judgement)

    p = sub.add_parser("waive",
                       help="record a human assurance waiver (requires a reason)")
    p.add_argument("item")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_waive)

    p = sub.add_parser("confirm",
                       help="record human confirmation of a passed assurance")
    p.add_argument("item")
    p.set_defaults(func=cmd_confirm)

    p = sub.add_parser("file-base-defect",
                       help="file (or dedupe to) the item that owns a "
                            "pre-existing assurance fail")
    p.add_argument("item")
    p.add_argument("--journey", required=True)
    p.add_argument("--scenario", required=True)
    p.add_argument("--fingerprint", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--expected")
    p.add_argument("--actual")
    p.set_defaults(func=cmd_file_base_defect)

    p = sub.add_parser("escape", help="file a post-assurance human discovery")
    p.add_argument("journey")
    p.add_argument("finding")
    p.add_argument("--miss-type", required=True, dest="miss_type",
                   choices=list(escapes_mod.MISS_TYPES))
    p.add_argument("--item", default="")
    p.add_argument("--node", default="")
    p.add_argument("--evidence", action="append")
    p.set_defaults(func=cmd_escape)

    p = sub.add_parser("promote",
                       help="close an escape by naming its durable promotion")
    p.add_argument("escape")
    p.add_argument("--via", required=True)
    p.set_defaults(func=cmd_promote)

    p = sub.add_parser("priority", help="set an item's priority (1+)")
    p.add_argument("item")
    p.add_argument("priority", type=int)
    p.set_defaults(func=cmd_priority)

    p = sub.add_parser("tier", help="set an item's materiality tier")
    p.add_argument("item")
    p.add_argument("tier")
    p.set_defaults(func=cmd_tier)

    p = sub.add_parser("journeys",
                       help="declare an item's journey impact (none or J-ids)")
    p.add_argument("item")
    p.add_argument("value")
    p.set_defaults(func=cmd_journeys)

    p = sub.add_parser("doctor", help="readout of repo integration state")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser(
        "reconcile", help="recover durable work after a lost child reply")
    subreconcile = p.add_subparsers(
        dest="reconcile_command", required=True)

    begin = subreconcile.add_parser(
        "begin", help="publish a pre-dispatch reconciliation checkpoint")
    begin.add_argument("item")
    begin.add_argument("--stage", required=True)
    begin.add_argument("--obligation", required=True)
    begin.add_argument("--input", nargs="+", required=True)
    begin.add_argument("--evidence", nargs="+", required=True)
    begin.add_argument("--worktree")
    begin.add_argument("--json", action="store_true", required=True)
    begin.set_defaults(func=cmd_reconcile)

    discover = subreconcile.add_parser(
        "discover", help="find safely bound reconciliation checkpoints")
    discover.add_argument("item")
    discover.add_argument("--stage", required=True)
    discover.add_argument("--obligation", required=True)
    discover.add_argument("--input", nargs="+", required=True)
    discover.add_argument("--worktree")
    discover.add_argument("--json", action="store_true", required=True)
    discover.set_defaults(func=cmd_reconcile)

    inspect = subreconcile.add_parser(
        "inspect", help="classify durable progress for one checkpoint")
    inspect.add_argument("item")
    inspect.add_argument("attempt")
    inspect.add_argument(
        "--writer-state", choices=["active", "terminal"], required=True)
    inspect.add_argument("--worktree")
    inspect.add_argument("--claim-continuation", action="store_true")
    inspect.add_argument("--json", action="store_true", required=True)
    inspect.set_defaults(func=cmd_reconcile)

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:
            raise
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
