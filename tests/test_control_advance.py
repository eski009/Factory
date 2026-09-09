import base64
import copy
import json
import os
import pickle
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from scripts.factory.lib import (
    breaker,
    config_state,
    control,
    cost,
    initrepo,
    items,
    logs,
    machine,
    paths,
    safeio,
)
from scripts.factory.lib.machine import GateError


ITEM = "0001-captured-state"


class CapturedStateHelpersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        self.meta = {
            "id": ITEM,
            "title": "Captured state",
            "stage": "waiting-human",
            "kind": "backend",
            "priority": 1,
            "created": "2026-09-09T09:00:00Z",
            "updated": "2026-09-09T12:00:00Z",
        }
        items.save_item(self.repo, self.meta, "")
        config = json.loads(
            paths.config_path(self.repo).read_text(encoding="utf-8"))
        config["gates"] = ["cost"]
        paths.config_path(self.repo).write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        os.environ["FACTORY_NOW"] = "2026-09-09T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def add_event(self, ts, event, data=None):
        os.environ["FACTORY_NOW"] = ts
        logs.append_event(self.repo, ITEM, event, data)

    def captured_events(self):
        events, corrupt = logs.read_events_with_stats(self.repo, ITEM)
        return tuple(events), corrupt, "2026-09-09T12:00:00Z"

    def seed_two_rework_edges(self):
        self.add_event(
            "2026-09-09T09:00:00Z", "stage.advance",
            {"from": "review", "to": "implement"})
        self.add_event(
            "2026-09-09T10:00:00Z", "stage.advance",
            {"from": "assure", "to": "implement"})
        os.environ["FACTORY_NOW"] = "2026-09-09T12:00:00Z"

    def test_supplied_cost_state_is_exact_and_performs_no_reads(self):
        self.seed_two_rework_edges()
        log_path = paths.item_dir(self.repo, ITEM) / "log.jsonl"
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write("not-json\n")
        expected = cost.summarize(self.repo, ITEM)
        events, corrupt, now = self.captured_events()

        with (
            mock.patch.object(cost.items, "load_item",
                              side_effect=AssertionError("item reread")),
            mock.patch.object(cost.logs, "read_events_with_stats",
                              side_effect=AssertionError("log reread")),
            mock.patch.object(cost.logs, "now_stamp",
                              side_effect=AssertionError("clock reread")),
        ):
            actual = cost.summarize_events(ITEM, events, now, corrupt)

        self.assertEqual(actual, expected)
        self.assertEqual(actual["corrupt_log_lines"], 1)

    def test_supplied_breaker_state_is_exact_and_performs_no_reads(self):
        self.seed_two_rework_edges()
        answer_path = breaker.answer_path(self.repo, ITEM)
        answer_path.parent.mkdir(parents=True, exist_ok=True)
        answer_path.write_bytes(
            b"# Cost breaker answer\r\n\r\n"
            b"- answer: continue\r\n- rework-edges: 1\r\n")
        meta = self.meta

        expected_verdict = breaker.verdict(
            self.repo, ITEM, meta, "implement", backlog=False)
        with self.assertRaises(GateError) as expected_error:
            breaker.precondition(self.repo, ITEM, meta, "implement")

        events, corrupt, now = self.captured_events()
        config = config_state.capture(self.repo)
        answer_bytes = answer_path.read_bytes()

        with (
            mock.patch.object(breaker, "_config_gates",
                              side_effect=AssertionError("config reread")),
            mock.patch.object(breaker, "read_answer",
                              side_effect=AssertionError("answer reread")),
            mock.patch.object(breaker, "rework_edges",
                              side_effect=AssertionError("log reread")),
            mock.patch.object(cost.items, "load_item",
                              side_effect=AssertionError("item reread")),
            mock.patch.object(cost.logs, "read_events_with_stats",
                              side_effect=AssertionError("log reread")),
            mock.patch.object(cost.logs, "now_stamp",
                              side_effect=AssertionError("clock reread")),
            mock.patch.object(config_state, "enabled",
                              wraps=config_state.enabled) as enabled,
        ):
            actual_verdict = breaker.verdict(
                self.repo, ITEM, meta, "implement", backlog=False,
                events=events, now=now, corrupt_log_lines=corrupt,
                config=config, answer_bytes=answer_bytes)
            with self.assertRaises(GateError) as actual_error:
                breaker.precondition(
                    self.repo, ITEM, meta, "implement",
                    events=events, now=now, corrupt_log_lines=corrupt,
                    config=config, answer_bytes=answer_bytes)

        self.assertEqual(actual_verdict, expected_verdict)
        self.assertEqual(str(actual_error.exception),
                         str(expected_error.exception))
        self.assertEqual(enabled.call_count, 2)


class PreparedImplementEntryTest(unittest.TestCase):
    def setUp(self):
        os.environ["FACTORY_NOW"] = "2026-09-09T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)

    @contextmanager
    def fixture(self, *, stage="plan", plan=b"- [ ] implement\n",
                paused_from=None, cost_gate=False):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            initrepo.init(repo)
            meta = {
                "id": ITEM,
                "title": "Captured state",
                "stage": stage,
                "kind": "backend",
                "priority": 1,
                "created": "2026-09-09T09:00:00Z",
                "updated": "2026-09-09T11:00:00Z",
            }
            if paused_from is not None:
                meta["paused-from"] = paused_from
                meta["paused-reason"] = "pause"
            items.save_item(repo, meta, "body\n")
            if plan is not None:
                (paths.item_dir(repo, ITEM) / "plan.md").write_bytes(plan)
            if cost_gate:
                config_path = paths.config_path(repo)
                config = json.loads(config_path.read_text(encoding="utf-8"))
                config["gates"] = ["cost"]
                config_path.write_text(
                    json.dumps(config, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
            yield repo

    def prepare(self, repo, key="entry-1", **kwargs):
        return machine.prepare_implement_entry(
            repo, ITEM, operation_key=key, **kwargs)

    @staticmethod
    def event(name, ts="2026-09-09T11:30:00Z", data=None):
        value = {"event": name, "ts": ts}
        if data is not None:
            value["data"] = data
        return value

    def assert_not_advanced(self, repo):
        self.assertEqual(items.load_item(repo, ITEM)[0]["stage"], "plan")
        self.assertNotIn(
            "stage.advance", [event["event"] for event in logs.read_events(repo, ITEM)])

    @staticmethod
    def control_args(prepared):
        request = machine._decode_canonical_value(
            prepared._request_bytes, "request", dict)
        events = machine._decode_canonical_value(
            prepared._events_bytes, "events", list)
        return {
            "kind": "implement-entry",
            "key": prepared.operation_key,
            "request": request,
            "prerequisites": machine._operation_prerequisites(prepared),
            "replacements": prepared.replacements + ((
                prepared.item_snapshot, prepared.replacement_item),),
            "events": events,
            "log_snapshot": prepared.log_snapshot,
        }

    def test_prepare_is_disk_inert_and_needs_no_implementation_worktree(self):
        with self.fixture() as repo:
            item_path = paths.item_dir(repo, ITEM) / "item.md"
            plan_path = paths.item_dir(repo, ITEM) / "plan.md"
            before = (item_path.read_bytes(), plan_path.read_bytes())

            prepared = self.prepare(repo)

            self.assertEqual(prepared.source, "plan")
            self.assertEqual(prepared.destination, "implement")
            self.assertEqual((item_path.read_bytes(), plan_path.read_bytes()), before)
            self.assertFalse((paths.item_dir(repo, ITEM) / "log.jsonl").exists())
            self.assertFalse((paths.item_dir(repo, ITEM) / "control").exists())
            self.assertFalse((repo / ".git").exists())

    def test_plan_replacement_is_required_and_precedes_metadata(self):
        for label, existing in (("completed", b"- [x] done\n"),
                                ("missing", None)):
            with self.subTest(label=label, replacement=False):
                with self.fixture(plan=existing) as repo:
                    with self.assertRaises(GateError):
                        self.prepare(repo)

            with self.subTest(label=label, replacement=True):
                with self.fixture(plan=existing) as repo:
                    plan_path = paths.item_dir(repo, ITEM) / "plan.md"
                    before = safeio.snapshot_path(
                        repo, plan_path.relative_to(repo), allow_missing=True)
                    prepared = self.prepare(
                        repo, replacements=((before, b"- [ ] rework\n"),))
                    observations = []

                    def after_replacement(index):
                        observations.append((
                            index,
                            plan_path.read_bytes(),
                            items.load_item(repo, ITEM)[0]["stage"],
                        ))

                    with mock.patch.object(
                            control, "_after_replacement",
                            side_effect=after_replacement):
                        meta, _verdict, receipt = (
                            machine.commit_implement_entry(prepared))

                    self.assertEqual(meta["stage"], "implement")
                    self.assertEqual(plan_path.read_bytes(), b"- [ ] rework\n")
                    self.assertEqual(observations[0],
                                     (0, b"- [ ] rework\n", "plan"))
                    self.assertEqual(observations[1][0], 1)
                    self.assertEqual(observations[1][2], "implement")
                    self.assertEqual(len(receipt.replacements), 2)

    def test_rework_and_special_legality_and_caps_use_prospective_events(self):
        for source in ("review", "verify", "assure"):
            with self.subTest(source=source, legal=True):
                with self.fixture(stage=source) as repo:
                    self.assertEqual(self.prepare(repo).source, source)
        with self.fixture(stage="waiting-human",
                          paused_from="implement") as repo:
            prepared = self.prepare(repo)
            meta, _body = items.parse_item(
                prepared.replacement_item.decode("utf-8"))
            self.assertNotIn("paused-from", meta)
            self.assertNotIn("paused-reason", meta)

        capped = {
            "review": tuple(self.event("review.rejected", ts=f"2026-09-09T11:0{i}:00Z")
                            for i in range(3)),
            "assure": tuple(self.event("assure.rejected", ts=f"2026-09-09T11:0{i}:00Z")
                            for i in range(3)),
            "verify": tuple(self.event(
                "stage.advance", ts=f"2026-09-09T11:0{i}:00Z",
                data={"from": "verify", "to": "implement"})
                for i in range(2)),
        }
        for source, events in capped.items():
            with self.subTest(source=source, capped=True):
                with self.fixture(stage=source) as repo:
                    with self.assertRaises(GateError):
                        self.prepare(repo, events=events)
        with self.fixture(stage="waiting-human", paused_from="review") as repo:
            with self.assertRaises(GateError):
                self.prepare(repo)

    def test_every_bound_snapshot_mutation_refuses_without_operation_effect(self):
        cases = ("item", "log", "config", "answer",
                 "caller-prerequisite", "caller-replacement")
        for case in cases:
            with self.subTest(case=case):
                with self.fixture() as repo:
                    item_dir = paths.item_dir(repo, ITEM)
                    kwargs = {}
                    sidecar = item_dir / "scope.md"
                    if case in ("caller-prerequisite", "caller-replacement"):
                        sidecar.write_bytes(b"before\n")
                        snapshot = safeio.snapshot_path(
                            repo, sidecar.relative_to(repo))
                        if case == "caller-prerequisite":
                            kwargs["prerequisites"] = (snapshot,)
                        else:
                            kwargs["replacements"] = ((snapshot, b"after\n"),)
                    prepared = self.prepare(repo, **kwargs)

                    if case == "item":
                        meta, body = items.load_item(repo, ITEM)
                        meta["title"] = "mutated"
                        items.save_item(repo, meta, body)
                    elif case == "log":
                        logs.append_event(repo, ITEM, "external.mutation")
                    elif case == "config":
                        config_path = paths.config_path(repo)
                        config_path.write_bytes(config_path.read_bytes() + b" ")
                    elif case == "answer":
                        answer = breaker.answer_path(repo, ITEM)
                        answer.parent.mkdir(parents=True, exist_ok=True)
                        answer.write_bytes(b"created after prepare\n")
                    else:
                        sidecar.write_bytes(b"mutated\n")

                    with self.assertRaises(
                            (control.ControlRefusal, safeio.SafeIOError,
                             config_state.ConfigStateError)):
                        machine.commit_implement_entry(prepared)
                    self.assertNotEqual(
                        items.load_item(repo, ITEM)[0]["stage"], "implement")
                    names = [event["event"] for event in logs.read_events(repo, ITEM)]
                    self.assertNotIn("stage.advance", names)
                    self.assertNotIn("cost.breaker", names)
                    if case == "caller-replacement":
                        self.assertEqual(sidecar.read_bytes(), b"mutated\n")

    def test_locked_log_authority_closes_post_preflight_rejection_race(self):
        with self.fixture(stage="review") as repo:
            prepared = self.prepare(repo)
            real_preflight = control._read_only_operation_preflight

            def preflight_then_reject(*args):
                real_preflight(*args)
                for index in range(3):
                    logs.append_event(
                        repo, ITEM, "review.rejected", {"index": index})

            with (
                mock.patch.object(
                    control, "_read_only_operation_preflight",
                    side_effect=preflight_then_reject),
                self.assertRaisesRegex(
                    control.ControlRefusal,
                    "log changed outside the prepared operation"),
            ):
                machine.commit_implement_entry(prepared)

            self.assertEqual(items.load_item(repo, ITEM)[0]["stage"], "review")
            self.assertEqual(
                [event["event"] for event in logs.read_events(repo, ITEM)],
                ["review.rejected"] * 3)

    def test_retry_refuses_rewritten_captured_log_history(self):
        with self.fixture(stage="review") as repo:
            logs.append_event(repo, ITEM, "history.original")
            prepared = self.prepare(repo)
            machine.commit_implement_entry(prepared)
            log_path = paths.item_dir(repo, ITEM) / "log.jsonl"
            committed = log_path.read_bytes()[len(prepared.log_snapshot.data):]
            log_path.write_bytes(
                logs._entry_bytes({
                    "event": "history.rewritten",
                    "ts": "2026-09-09T11:45:00Z",
                }) + committed)

            with self.assertRaisesRegex(
                    control.ControlRefusal,
                    "log changed outside the prepared operation"):
                machine.commit_implement_entry(prepared)

    def test_commit_uses_sealed_events_request_and_breaker_verdict(self):
        with self.fixture(stage="review", cost_gate=True) as repo:
            logs.append_event(
                repo, ITEM, "stage.advance",
                {"from": "assure", "to": "implement"})
            prepared = self.prepare(repo)
            prepared.events[-1]["event"] = "cost.suppressed"
            prepared.stage_event["data"]["to"] = "review"
            prepared.breaker_verdict["fired"] = False

            meta, verdict, _receipt = machine.commit_implement_entry(prepared)

            self.assertEqual(meta["stage"], "implement")
            self.assertTrue(verdict["fired"])
            self.assertEqual(
                [event["event"] for event in logs.read_events(repo, ITEM)][-2:],
                ["stage.advance", "cost.breaker"])
            self.assertEqual(
                logs.read_events(repo, ITEM)[-2]["data"]["to"], "implement")

    def test_supplied_config_value_mutation_cannot_disable_cost_gate(self):
        with self.fixture(stage="review", cost_gate=True) as repo:
            logs.append_event(
                repo, ITEM, "stage.advance",
                {"from": "review", "to": "implement"})
            logs.append_event(
                repo, ITEM, "stage.advance",
                {"from": "assure", "to": "implement"})
            supplied = config_state.capture(repo)
            supplied.value["gates"] = []

            with self.assertRaisesRegex(GateError, "cost breaker unanswered"):
                self.prepare(repo, config=supplied)

            self.assertEqual(items.load_item(repo, ITEM)[0]["stage"], "review")

    def test_retry_after_own_answer_replacement_crash(self):
        with self.fixture() as repo:
            answer = breaker.answer_path(repo, ITEM)
            before = safeio.snapshot_path(
                repo, answer.relative_to(repo), allow_missing=True)
            answer_bytes = (
                b"# Cost breaker answer\n\n- answer: continue\n"
                b"- rework-edges: 0\n")
            prepared = self.prepare(
                repo, replacements=((before, answer_bytes),))

            def crash_after_answer(index):
                if index == 0:
                    raise RuntimeError("lost after answer replacement")

            with (
                mock.patch.object(
                    control, "_after_replacement",
                    side_effect=crash_after_answer),
                self.assertRaisesRegex(
                    RuntimeError, "lost after answer replacement"),
            ):
                machine.commit_implement_entry(prepared)

            self.assertEqual(answer.read_bytes(), answer_bytes)
            self.assertEqual(items.load_item(repo, ITEM)[0]["stage"], "plan")
            meta, _verdict, _receipt = machine.commit_implement_entry(prepared)
            self.assertEqual(meta["stage"], "implement")

    def test_log_snapshot_overlap_refuses_during_prepare(self):
        with self.fixture(stage="review") as repo:
            logs.append_event(repo, ITEM, "history.original")
            log_path = paths.item_dir(repo, ITEM) / "log.jsonl"
            snapshot = safeio.snapshot_path(repo, log_path.relative_to(repo))

            with self.assertRaisesRegex(
                    control.ControlRefusal,
                    "owns the item log snapshot"):
                self.prepare(repo, prerequisites=(snapshot,))
            self.assertFalse((
                paths.item_dir(repo, ITEM) / "control" / "operations"
            ).exists())

    def test_crash_recovery_at_every_prepared_operation_boundary(self):
        fixed = (("_after_intent", None), ("_after_active", None),
                 ("_before_commit_validation", None),
                 ("_after_commit", None),
                 ("_after_active_removal", None))
        for hook, target in fixed:
            with self.subTest(hook=hook):
                with self.fixture() as repo:
                    prepared = self.prepare(repo, key=f"boundary-{hook}")
                    with (
                        mock.patch.object(
                            control, hook,
                            side_effect=RuntimeError("simulated crash")),
                        self.assertRaisesRegex(RuntimeError, "simulated crash"),
                    ):
                        machine.commit_implement_entry(prepared)
                    meta, _verdict, receipt = (
                        machine.commit_implement_entry(prepared))
                    self.assertEqual(meta["stage"], "implement")
                    self.assertEqual(
                        [event["operation_id"] for event in logs.read_events(
                            repo, ITEM) if event.get("operation_id")],
                        [receipt.operation_id])

        for family in ("blob", "replacement", "event"):
            with self.fixture() as probe_repo:
                probe = self.prepare(probe_repo, key=f"probe-{family}")
                args = self.control_args(probe)
                _intent, _raw, blobs = control._build_intent(
                    probe_repo, ITEM, args["kind"], args["key"],
                    args["request"], args["prerequisites"],
                    args["replacements"], args["events"],
                    args["log_snapshot"])
                count = {"blob": len(blobs),
                         "replacement": len(args["replacements"]),
                         "event": len(args["events"])}[family]
            for target in range(count):
                with self.subTest(family=family, target=target):
                    with self.fixture() as repo:
                        prepared = self.prepare(
                            repo, key=f"boundary-{family}-{target}")

                        def crash_at(index, *_unused):
                            if index == target:
                                raise RuntimeError("simulated crash")

                        with (
                            mock.patch.object(
                                control, f"_after_{family}",
                                side_effect=crash_at),
                            self.assertRaisesRegex(
                                RuntimeError, "simulated crash"),
                        ):
                            machine.commit_implement_entry(prepared)
                        meta, _verdict, receipt = (
                            machine.commit_implement_entry(prepared))
                        self.assertEqual(meta["stage"], "implement")
                        self.assertEqual(
                            [event["operation_id"] for event in logs.read_events(
                                repo, ITEM) if event.get("operation_id")],
                            [receipt.operation_id])

    def test_lost_response_retry_from_independent_process(self):
        with self.fixture(stage="review", cost_gate=True) as repo:
            logs.append_event(
                repo, ITEM, "stage.advance",
                {"from": "assure", "to": "implement"})
            prepared = self.prepare(repo)
            _meta, expected_verdict, expected_receipt = (
                machine.commit_implement_entry(prepared))
            payload = base64.b64encode(pickle.dumps(copy.deepcopy(prepared)))
            source = """
import base64
import json
import pickle
import sys
from scripts.factory.lib import machine
prepared = pickle.loads(base64.b64decode(sys.argv[1]))
meta, verdict, receipt = machine.commit_implement_entry(prepared)
print(json.dumps({"stage": meta["stage"], "verdict": verdict,
                  "operation_id": receipt.operation_id}, sort_keys=True))
"""
            result = subprocess.run(
                [sys.executable, "-c", source, payload.decode("ascii")],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True, text=True, env=os.environ.copy())

            self.assertEqual(result.returncode, 0, result.stderr)
            actual = json.loads(result.stdout)
            self.assertEqual(actual["stage"], "implement")
            self.assertEqual(actual["verdict"], expected_verdict)
            self.assertEqual(
                actual["operation_id"], expected_receipt.operation_id)

    def test_rework_and_special_completed_or_missing_plan_replacement(self):
        cases = (("review", None),
                 ("waiting-human", "implement"))
        for stage, paused_from in cases:
            for plan in (b"- [x] completed\n", None):
                with self.subTest(stage=stage, plan=plan):
                    with self.fixture(
                            stage=stage, paused_from=paused_from,
                            plan=plan) as repo:
                        plan_path = paths.item_dir(repo, ITEM) / "plan.md"
                        before = safeio.snapshot_path(
                            repo, plan_path.relative_to(repo),
                            allow_missing=True)
                        prepared = self.prepare(
                            repo, replacements=((before, b"- [ ] rework\n"),))
                        meta, _verdict, _receipt = (
                            machine.commit_implement_entry(prepared))
                        self.assertEqual(meta["stage"], "implement")
                        self.assertEqual(
                            plan_path.read_bytes(), b"- [ ] rework\n")

    def test_exact_event_order_attribution_and_retry(self):
        with self.fixture(stage="review", cost_gate=True) as repo:
            logs.append_event(
                repo, ITEM, "stage.advance",
                {"from": "review", "to": "implement"})
            caller = self.event("plan.dispatch", data={"ticket": "t-1"})
            prepared = self.prepare(repo, events=(caller,))

            self.assertEqual(
                [event["event"] for event in prepared.events],
                ["plan.dispatch", "stage.advance", "cost.breaker"])
            meta, verdict, first = machine.commit_implement_entry(prepared)
            retry_meta, retry_verdict, second = (
                machine.commit_implement_entry(prepared))

            self.assertEqual(meta, retry_meta)
            self.assertEqual(verdict, retry_verdict)
            self.assertEqual(first, second)
            committed = logs.read_events(repo, ITEM)[-3:]
            self.assertEqual(
                [event["event"] for event in committed],
                ["plan.dispatch", "stage.advance", "cost.breaker"])
            self.assertEqual(
                {event["operation_id"] for event in committed},
                {first.operation_id})
            self.assertEqual(
                [event["event"] for event in logs.read_events(repo, ITEM)].count(
                    "stage.advance"),
                2)
            self.assertEqual(
                [event["event"] for event in logs.read_events(repo, ITEM)].count(
                    "cost.breaker"),
                1)

    def test_breaker_verdict_and_event_are_from_exact_prospective_state(self):
        with self.fixture(stage="review", cost_gate=True) as repo:
            logs.append_event(
                repo, ITEM, "stage.advance",
                {"from": "assure", "to": "implement"})
            prepared = self.prepare(repo)

            self.assertEqual(prepared.breaker_verdict, {
                "over_threshold": True,
                "fired": True,
                "reason": "rework-threshold",
                "rework_edges": 2,
                "threshold": 2,
                "gate": True,
                "answered_at": None,
                "priority": 1,
                "backlog": None,
                "stage": "implement",
            })
            self.assertEqual(prepared.events[-1], {
                "event": "cost.breaker",
                "ts": "2026-09-09T12:00:00Z",
                "data": {"rework_edges": 2, "threshold": 2},
            })
            self.assertEqual(prepared.stage_event["ts"],
                             prepared.events[-1]["ts"])

    def test_issue_ticket_still_refuses_without_owned_clean_checkout(self):
        with self.fixture() as repo:
            with self.assertRaises(control.ControlRefusal):
                control.issue_ticket(
                    repo, ITEM, kind="implement", key="dispatch-1",
                    owner_token="not-an-owner-token",
                    config=config_state.capture(repo), inputs=(), metadata={})

    def test_legacy_advance_holds_lock_and_preserves_exact_bytes_and_order(self):
        with self.fixture(stage="review", cost_gate=True) as repo:
            logs.append_event(
                repo, ITEM, "stage.advance",
                {"from": "review", "to": "implement"})
            item_path = paths.item_dir(repo, ITEM) / "item.md"
            log_path = paths.item_dir(repo, ITEM) / "log.jsonl"
            original_log = log_path.read_bytes()
            expected_meta, body = items.load_item(repo, ITEM)
            expected_meta["stage"] = "implement"
            expected_meta["updated"] = "2026-09-09T12:00:00Z"
            expected_item = items.render_item(expected_meta, body).encode("utf-8")
            expected_log = original_log + logs._entry_bytes({
                "event": "stage.advance",
                "ts": "2026-09-09T12:00:00Z",
                "data": {"from": "review", "to": "implement"},
            }) + logs._entry_bytes({
                "event": "cost.breaker",
                "ts": "2026-09-09T12:00:00Z",
                "data": {"rework_edges": 2, "threshold": 2},
            })
            held = []
            original_lock = control.item_lock
            original_save = machine.items.save_item
            original_append = machine.logs.append_event

            @contextmanager
            def tracking_lock(*args, **kwargs):
                with original_lock(*args, **kwargs) as lock:
                    held.append(lock)
                    yield lock

            def tracking_save(*args, **kwargs):
                control._validate_item_lock(held[-1], repo=repo, item_id=ITEM)
                return original_save(*args, **kwargs)

            def tracking_append(*args, **kwargs):
                self.assertIs(kwargs.get("_lock"), held[-1])
                control._validate_item_lock(held[-1], repo=repo, item_id=ITEM)
                return original_append(*args, **kwargs)

            with (
                mock.patch.object(control, "item_lock", tracking_lock),
                mock.patch.object(machine.items, "save_item",
                                  side_effect=tracking_save),
                mock.patch.object(machine.logs, "append_event",
                                  side_effect=tracking_append),
            ):
                meta, verdict = machine.advance(repo, ITEM, "implement")

            self.assertEqual(meta, expected_meta)
            self.assertTrue(verdict["fired"])
            self.assertEqual(item_path.read_bytes(), expected_item)
            self.assertEqual(log_path.read_bytes(), expected_log)

    def test_legacy_advance_refuses_pending_operation_before_any_effect(self):
        with self.fixture() as repo:
            prepared = self.prepare(repo)
            with (
                mock.patch.object(
                    control, "_after_replacement",
                    side_effect=RuntimeError("crash after item")),
                self.assertRaisesRegex(RuntimeError, "crash after item"),
            ):
                machine.commit_implement_entry(prepared)
            item_path = paths.item_dir(repo, ITEM) / "item.md"
            before_legacy = item_path.read_bytes()

            with self.assertRaisesRegex(
                    control.ControlRefusal, "pending recovery"):
                machine.advance(repo, ITEM, "blocked", "must not land")

            self.assertEqual(item_path.read_bytes(), before_legacy)
            self.assertEqual(items.load_item(repo, ITEM)[0]["stage"], "implement")
            recovered = control.recover_pending(repo, ITEM)
            self.assertTrue(recovered.recovered)
            self.assertEqual(
                [event["event"] for event in logs.read_events(repo, ITEM)],
                ["stage.advance"])


if __name__ == "__main__":
    unittest.main()
