import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from scripts.factory.lib import config_state, control, initrepo, items, logs
from scripts.factory.lib import ownership, safeio
from scripts.factory.lib.validate import validate


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True)


class ControlFixture(unittest.TestCase):
    item = "0001-thing"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name).resolve()
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@example.test")
        _git(self.repo, "config", "user.name", "Control Test")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(self.repo, "add", "seed.txt")
        _git(self.repo, "commit", "-q", "-m", "seed")
        _git(self.repo, "checkout", "-q", "-b", f"factory/{self.item}")
        initrepo.init(self.repo)
        items.save_item(self.repo, {
            "id": self.item,
            "title": "Thing",
            "stage": "implement",
            "kind": "backend",
            "created": "2026-09-08T00:00:00Z",
            "updated": "2026-09-08T00:00:00Z",
        }, "")
        self.item_dir = self.repo / ".factory/items" / self.item
        self.plan = self.item_dir / "plan.md"
        self.plan.write_bytes(b"- [ ] exact task\n")
        self.target = self.item_dir / "state.bin"
        self.target.write_bytes(b"before\n")
        self.created = self.item_dir / "created.bin"
        self.config_bytes = (self.repo / ".factory/config.json").read_bytes()

    def tearDown(self):
        self.tmp.cleanup()

    def _operation_args(self, key="round-1"):
        before = safeio.snapshot_path(
            self.repo, f".factory/items/{self.item}/state.bin")
        missing = safeio.snapshot_path(
            self.repo, f".factory/items/{self.item}/created.bin",
            allow_missing=True)
        config = safeio.snapshot_path(self.repo, ".factory/config.json")
        return {
            "kind": "test.commit",
            "key": key,
            "request": {"round": 1, "source": "test"},
            "prerequisites": (config,),
            "replacements": ((before, b"after\n"),
                             (missing, b"created\n")),
            "events": ({
                "event": "control.test-completed",
                "ts": "2026-09-08T12:00:00Z",
                "data": {"round": 1},
            },),
        }

    def _subprocess(self, source, *, owner_token=None):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        if owner_token is None:
            environment.pop("FACTORY_IMPLEMENTATION_OWNER", None)
        else:
            environment["FACTORY_IMPLEMENTATION_OWNER"] = owner_token
        return subprocess.run(
            ["python3", "-c", source, str(self.repo), self.item],
            cwd=Path(__file__).resolve().parents[1], env=environment,
            capture_output=True, text=True)

    def _crash_operation(self, args, hook="_after_active"):
        with mock.patch.object(
                control, hook, side_effect=RuntimeError("simulated crash")):
            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                control.commit_operation(self.repo, self.item, **args)
        active = json.loads((self.item_dir / "control/active.json").read_text())
        operation = self.item_dir / "control/operations" / active["operation_id"]
        return active["operation_id"], operation

    def _reset_operation_fixture(self):
        control_dir = self.item_dir / "control"
        if control_dir.exists():
            shutil.rmtree(control_dir)
        (self.repo / ".factory/config.json").write_bytes(self.config_bytes)
        self.target.write_bytes(b"before\n")
        if self.created.exists() or self.created.is_symlink():
            self.created.unlink()
        log = self.item_dir / "log.jsonl"
        if log.exists() or log.is_symlink():
            log.unlink()


class TicketTest(ControlFixture):
    def _ticket_manifest_bytes(self, claim, config, inputs, metadata, *,
                               kind, key):
        verified = ownership.verify(
            self.repo, self.item, claim.token, supplied=claim.checkout)
        manifest = {
            "version": 1,
            "item": self.item,
            "kind": kind,
            "key": key,
            "owner_sha256": verified.owner_sha256,
            "checkout": str(verified.checkout),
            "checkout_identity": list(
                control._checkout_identity(verified.checkout)),
            "config": control._snapshot_record(config.file),
            "inputs": [control._snapshot_record(value) for value in inputs],
            "metadata": control._canonical(metadata)[1],
        }
        manifest["ticket_id"] = control._ticket_identity(manifest)
        return control._canonical(manifest)[0]

    def test_ticket_round_trip_preserves_original_snapshots_and_owner_digest(self):
        claim = ownership.acquire(self.repo, self.item)
        try:
            config = config_state.capture(self.repo)
            plan = safeio.snapshot_path(
                self.repo, f".factory/items/{self.item}/plan.md")
            ticket = control.issue_ticket(
                self.repo, self.item, kind="plan.dispatch", key="round-1",
                owner_token=claim.token, config=config, inputs=(plan,),
                metadata={"round": 1})
            loaded = control.load_ticket(
                self.repo, self.item, ticket.ticket_id,
                owner_token=claim.token)

            self.assertEqual(loaded.ticket_id, ticket.ticket_id)
            self.assertEqual(loaded.owner_sha256,
                             ownership.owner_digest(claim.token))
            self.assertEqual(loaded.checkout, claim.checkout)
            self.assertEqual(loaded.config.file, config.file)
            self.assertEqual(loaded.inputs, (plan,))
            self.assertEqual(loaded.metadata, {"round": 1})
            control.revalidate_ticket(loaded)

            manifest = json.loads(loaded.manifest.file.data)
            self.assertEqual(manifest["version"], 1)
            self.assertNotIn(claim.token, json.dumps(manifest, sort_keys=True))
        finally:
            claim.release()

    def test_identical_issue_adopts_and_same_kind_key_conflict_refuses(self):
        claim = ownership.acquire(self.repo, self.item)
        try:
            config = config_state.capture(self.repo)
            plan = safeio.snapshot_path(
                self.repo, f".factory/items/{self.item}/plan.md")
            kwargs = dict(kind="plan.dispatch", key="round-1",
                          owner_token=claim.token, config=config,
                          inputs=(plan,), metadata={"round": 1})
            first = control.issue_ticket(self.repo, self.item, **kwargs)
            second = control.issue_ticket(self.repo, self.item, **kwargs)
            self.assertEqual(second.ticket_id, first.ticket_id)
            with self.assertRaisesRegex(control.ControlRefusal, "conflict"):
                control.issue_ticket(
                    self.repo, self.item, **{**kwargs,
                        "metadata": {"round": 2}})
        finally:
            claim.release()

    def test_wrong_missing_and_released_owner_refuse_without_leaking_token(self):
        claim = ownership.acquire(self.repo, self.item)
        config = config_state.capture(self.repo)
        plan = safeio.snapshot_path(
            self.repo, f".factory/items/{self.item}/plan.md")
        ticket = control.issue_ticket(
            self.repo, self.item, kind="plan.dispatch", key="round-1",
            owner_token=claim.token, config=config, inputs=(plan,), metadata={})
        attempts = (None, "wrong-token")
        for token in attempts:
            with self.subTest(token=token):
                with self.assertRaises(control.ControlRefusal) as raised:
                    control.load_ticket(
                        self.repo, self.item, ticket.ticket_id,
                        owner_token=token)
                self.assertNotIn(claim.token, str(raised.exception))
        claim.release()
        with self.assertRaises(control.ControlRefusal):
            control.load_ticket(
                self.repo, self.item, ticket.ticket_id,
                owner_token=claim.token)

    def test_ticket_reload_and_owner_refusals_cross_real_processes(self):
        claim = ownership.acquire(self.repo, self.item)
        ticket = control.issue_ticket(
            self.repo, self.item, kind="plan.dispatch", key="subprocess",
            owner_token=claim.token, config=config_state.capture(self.repo),
            inputs=(safeio.snapshot_path(
                self.repo, f".factory/items/{self.item}/plan.md"),),
            metadata={"process": "second"})
        load_source = """
import json
import sys
from scripts.factory.lib import control
ticket = control.load_ticket(sys.argv[1], sys.argv[2], %r)
control.revalidate_ticket(ticket)
print(json.dumps(ticket.metadata, sort_keys=True))
""" % ticket.ticket_id

        loaded = self._subprocess(load_source, owner_token=claim.token)
        self.assertEqual(loaded.returncode, 0, loaded.stderr)
        self.assertEqual(json.loads(loaded.stdout), {"process": "second"})
        for label, token in (("missing", None), ("wrong", "wrong-token")):
            with self.subTest(label=label):
                refused = self._subprocess(load_source, owner_token=token)
                self.assertNotEqual(refused.returncode, 0)
                self.assertNotIn(claim.token, refused.stderr)
        claim.release()
        released = self._subprocess(load_source, owner_token=claim.token)
        self.assertNotEqual(released.returncode, 0)
        self.assertNotIn(claim.token, released.stderr)

    def test_ticket_namespace_identities_are_pinned_through_publication(self):
        for boundary in ("tickets", "ticket", "blobs"):
            with self.subTest(boundary=boundary):
                claim = ownership.acquire(self.repo, self.item)
                try:
                    real_publish = control._publish_immutable
                    attacked = False

                    def detach_after_manifest(
                            directory_fd, name, data, **kwargs):
                        nonlocal attacked
                        identity = real_publish(
                            directory_fd, name, data, **kwargs)
                        if name == "manifest.json" and not attacked:
                            attacked = True
                            tickets = self.item_dir / "control/tickets"
                            ticket = next(tickets.iterdir())
                            target = {"tickets": tickets, "ticket": ticket,
                                      "blobs": ticket / "blobs"}[boundary]
                            detached = target.with_name(
                                target.name + "-detached")
                            target.rename(detached)
                            shutil.copytree(detached, target)
                        return identity

                    with (mock.patch.object(
                            control, "_publish_immutable",
                            side_effect=detach_after_manifest),
                          self.assertRaisesRegex(
                              control.ControlError, "identity|detached")):
                        control.issue_ticket(
                            self.repo, self.item, kind="plan.dispatch",
                            key=f"detach-{boundary}", owner_token=claim.token,
                            config=config_state.capture(self.repo), inputs=(),
                            metadata={})
                finally:
                    claim.release()
                self._reset_operation_fixture()

    def test_ticket_revalidation_refuses_config_input_and_checkout_changes(self):
        for changed in ("config", "input", "checkout"):
            with self.subTest(changed=changed):
                claim = ownership.acquire(self.repo, self.item)
                try:
                    ticket = control.issue_ticket(
                        self.repo, self.item, kind="plan.dispatch",
                        key=changed, owner_token=claim.token,
                        config=config_state.capture(self.repo),
                        inputs=(safeio.snapshot_path(
                            self.repo,
                            f".factory/items/{self.item}/plan.md"),),
                        metadata={})
                    if changed == "config":
                        path = self.repo / ".factory/config.json"
                        path.write_bytes(path.read_bytes() + b" ")
                    elif changed == "input":
                        self.plan.write_bytes(b"changed\n")
                    else:
                        with mock.patch.object(
                                control, "_checkout_identity",
                                return_value=(-1, -1)):
                            with self.assertRaises(control.ControlRefusal):
                                control.revalidate_ticket(ticket)
                        continue
                    with self.assertRaises(control.ControlRefusal):
                        control.revalidate_ticket(ticket)
                finally:
                    claim.release()
                if changed == "config":
                    initrepo.init(self.repo)
                elif changed == "input":
                    self.plan.write_bytes(b"- [ ] exact task\n")

    def test_owner_token_bytes_are_never_persisted_in_control_namespace(self):
        claim = ownership.acquire(self.repo, self.item)
        try:
            ticket = control.issue_ticket(
                self.repo, self.item, kind="plan.dispatch", key="round-1",
                owner_token=claim.token, config=config_state.capture(self.repo),
                inputs=(safeio.snapshot_path(
                    self.repo, f".factory/items/{self.item}/plan.md"),),
                metadata={"safe": True})
            control.revalidate_ticket(ticket)
            for path in (self.item_dir / "control").rglob("*"):
                if path.is_file():
                    self.assertNotIn(claim.token.encode("utf-8"),
                                     path.read_bytes(), path)

            with self.assertRaisesRegex(
                    control.ControlRefusal, "ownership token"):
                control.issue_ticket(
                    self.repo, self.item, kind="plan.dispatch", key="leak",
                    owner_token=claim.token,
                    config=config_state.capture(self.repo), inputs=(),
                    metadata={"secret": claim.token})
        finally:
            claim.release()

    def test_ticket_manifest_limit_is_exact_for_issue_reload_and_scan(self):
        claim = ownership.acquire(self.repo, self.item)
        try:
            config = config_state.capture(self.repo)
            metadata = {"payload": "m" * 257}
            kind = "plan.dispatch"
            key = "manifest-boundary"
            manifest_bytes = self._ticket_manifest_bytes(
                claim, config, (), metadata, kind=kind, key=key)
            limit = len(manifest_bytes)

            with (mock.patch.object(
                    control, "_TICKET_MANIFEST_LIMIT", limit - 1,
                    create=True),
                  self.assertRaisesRegex(
                      control.ControlRefusal,
                      "ticket manifest exceeds its read limit")):
                control.issue_ticket(
                    self.repo, self.item, kind=kind, key=key,
                    owner_token=claim.token, config=config, inputs=(),
                    metadata=metadata)

            self.assertEqual(len(manifest_bytes), limit)
            self.assertFalse((self.item_dir / "control").exists())

            with mock.patch.object(
                    control, "_TICKET_MANIFEST_LIMIT", limit, create=True):
                ticket = control.issue_ticket(
                    self.repo, self.item, kind=kind, key=key,
                    owner_token=claim.token, config=config, inputs=(),
                    metadata=metadata)
                loaded = control.load_ticket(
                    self.repo, self.item, ticket.ticket_id,
                    owner_token=claim.token)
                unrelated = control.issue_ticket(
                    self.repo, self.item, kind="verify.dispatch", key="small",
                    owner_token=claim.token, config=config, inputs=(),
                    metadata={})

            self.assertEqual(len(ticket.manifest.file.data), limit)
            self.assertEqual(loaded.ticket_id, ticket.ticket_id)
            self.assertNotEqual(unrelated.ticket_id, ticket.ticket_id)
        finally:
            claim.release()

    def test_ticket_blob_limit_refuses_oversize_before_artifacts_and_reloads_boundary(self):
        claim = ownership.acquire(self.repo, self.item)
        try:
            config = config_state.capture(self.repo)
            input_path = self.item_dir / "large-input.bin"
            input_path.write_bytes(b"i" * (len(config.file.data) + 37))
            input_snapshot = safeio.snapshot_path(
                self.repo, input_path.relative_to(self.repo).as_posix())
            cases = (
                ("config", (), len(config.file.data)),
                ("input", (input_snapshot,), len(input_snapshot.data)),
            )
            for label, inputs, limit in cases:
                with self.subTest(case=label, edge="oversize"):
                    with (mock.patch.object(
                            control, "_TICKET_BLOB_LIMIT", limit - 1,
                            create=True),
                          self.assertRaisesRegex(
                              control.ControlRefusal,
                              "ticket blob exceeds its read limit")):
                        control.issue_ticket(
                            self.repo, self.item, kind="plan.dispatch",
                            key=f"{label}-oversize",
                            owner_token=claim.token, config=config,
                            inputs=inputs, metadata={})
                    self.assertFalse((self.item_dir / "control").exists())

                with self.subTest(case=label, edge="boundary"):
                    with mock.patch.object(
                            control, "_TICKET_BLOB_LIMIT", limit,
                            create=True):
                        ticket = control.issue_ticket(
                            self.repo, self.item, kind="plan.dispatch",
                            key=f"{label}-boundary",
                            owner_token=claim.token, config=config,
                            inputs=inputs, metadata={})
                        loaded = control.load_ticket(
                            self.repo, self.item, ticket.ticket_id,
                            owner_token=claim.token)
                    self.assertEqual(loaded.ticket_id, ticket.ticket_id)
                    expected_sizes = [len(config.file.data), *(
                        len(value.data) for value in inputs)]
                    self.assertIn(limit, expected_sizes)
                    shutil.rmtree(self.item_dir / "control")
        finally:
            claim.release()


class OperationTest(ControlFixture):
    def test_log_capacity_refuses_before_operation_namespace_and_effects(self):
        log_path = self.item_dir / "log.jsonl"
        old = b'{"event": "old", "ts": "durable"}\n'
        log_path.write_bytes(old)
        old_identity = log_path.stat().st_ino
        args = self._operation_args(key="log-capacity-refusal")
        second = {
            "event": "control.second-event",
            "ts": "2026-09-09T15:00:00Z",
            "data": {"round": 2},
        }
        args["events"] = (*args["events"], second)
        intent, _intent_bytes, _blobs = control._build_intent(
            self.repo, self.item, args["kind"], args["key"],
            args["request"], args["prerequisites"], args["replacements"],
            args["events"])
        intended_bytes = b"".join(
            (json.dumps(event, sort_keys=True, allow_nan=False) + "\n").encode(
                "utf-8")
            for event in intent["events"]
        )

        with (mock.patch.object(
                control, "_LOG_IMAGE_LIMIT",
                len(old) + len(intended_bytes) - 1, create=True),
              self.assertRaisesRegex(
                  control.ControlRefusal,
                  "item log image exceeds its read limit")):
            control.commit_operation(self.repo, self.item, **args)

        self.assertEqual(log_path.read_bytes(), old)
        self.assertEqual(log_path.stat().st_ino, old_identity)
        self.assertFalse((self.item_dir / "control").exists())
        self.assertEqual(self.target.read_bytes(), b"before\n")
        self.assertFalse(self.created.exists())

    def test_read_only_log_preflight_is_bounded_descriptor_relative_and_no_follow(self):
        log_path = self.item_dir / "log.jsonl"
        log_path.write_bytes(b'{"event": "old", "ts": "durable"}\n')
        args = dict(
            kind="test.log-preflight", key="bounded-read", request={},
            prerequisites=(), replacements=(),
            events=({
                "event": "control.test-completed",
                "ts": "2026-09-09T15:00:01Z",
            },),
        )
        real_open = control.os.open
        log_opens = []

        def record_open(path, flags, *open_args, **open_kwargs):
            if path == "log.jsonl":
                log_opens.append((flags, open_kwargs.get("dir_fd")))
            return real_open(path, flags, *open_args, **open_kwargs)

        with (mock.patch.object(
                control, "_LOG_IMAGE_LIMIT", len(log_path.read_bytes()) - 1),
              mock.patch.object(control.os, "open", side_effect=record_open),
              mock.patch.object(
                  control.os, "read",
                  side_effect=AssertionError("oversized log payload was read")),
              self.assertRaisesRegex(
                  control.ControlError, "artifact exceeds its read limit")):
            control.commit_operation(self.repo, self.item, **args)

        self.assertTrue(log_opens)
        for flags, directory_fd in log_opens:
            self.assertIsNotNone(directory_fd)
            self.assertTrue(flags & getattr(os, "O_NOFOLLOW", 0))
            self.assertTrue(flags & getattr(os, "O_NONBLOCK", 0))
        self.assertFalse((self.item_dir / "control").exists())

    def test_stale_snapshots_refuse_before_control_namespace_creation(self):
        for snapshot_kind in ("prerequisite", "replacement"):
            with self.subTest(snapshot_kind=snapshot_kind):
                self._reset_operation_fixture()
                args = self._operation_args(key=f"stale-{snapshot_kind}")
                if snapshot_kind == "prerequisite":
                    config = self.repo / ".factory/config.json"
                    config.write_bytes(config.read_bytes() + b" ")
                    expected_message = "prerequisite"
                else:
                    self.target.write_bytes(b"changed after snapshot\n")
                    expected_message = "replacement"

                with self.assertRaisesRegex(
                        control.ControlRefusal, expected_message):
                    control.commit_operation(self.repo, self.item, **args)

                self.assertFalse((self.item_dir / "control").exists())
                self.assertFalse(self.created.exists())

    def test_locked_preflight_repeats_checks_after_read_only_race(self):
        for changed_state in ("log-capacity", "prerequisite", "replacement"):
            with self.subTest(changed_state=changed_state):
                self._reset_operation_fixture()
                args = self._operation_args(key=f"preflight-race-{changed_state}")
                limit = control._LOG_IMAGE_LIMIT
                if changed_state == "log-capacity":
                    intent, _raw, _blobs = control._build_intent(
                        self.repo, self.item, **args)
                    intended_size = sum(
                        len(logs._entry_bytes(event))
                        for event in intent["events"])
                    unrelated = logs._entry_bytes({
                        "event": "ordinary.raced",
                        "ts": "2026-09-09T15:00:02Z",
                    })
                    limit = max(intended_size, len(unrelated))

                real_preflight = control._read_only_operation_preflight

                def preflight_then_change(*preflight_args):
                    real_preflight(*preflight_args)
                    if changed_state == "log-capacity":
                        (self.item_dir / "log.jsonl").write_bytes(unrelated)
                    elif changed_state == "prerequisite":
                        config = self.repo / ".factory/config.json"
                        config.write_bytes(config.read_bytes() + b" ")
                    else:
                        self.target.write_bytes(b"changed after preflight\n")

                expected = ("read limit" if changed_state == "log-capacity"
                            else changed_state)
                with (mock.patch.object(control, "_LOG_IMAGE_LIMIT", limit),
                      mock.patch.object(
                          control, "_read_only_operation_preflight",
                          side_effect=preflight_then_change),
                      self.assertRaisesRegex(control.ControlRefusal, expected)):
                    control.commit_operation(self.repo, self.item, **args)

                self.assertTrue((self.item_dir / "control/lock").is_file())
                self.assertFalse(
                    (self.item_dir / "control/operations").exists())
                self.assertFalse(self.created.exists())

    def test_exact_boundary_recovers_and_retries_with_present_event_prefix(self):
        args = self._operation_args(key="log-capacity-boundary")
        args["events"] = (*args["events"], {
            "event": "control.second-event",
            "ts": "2026-09-09T15:01:00Z",
            "data": {"round": 2},
        })
        intent, _intent_bytes, _blobs = control._build_intent(
            self.repo, self.item, args["kind"], args["key"],
            args["request"], args["prerequisites"], args["replacements"],
            args["events"])
        lines = [
            (json.dumps(event, sort_keys=True, allow_nan=False) + "\n").encode(
                "utf-8")
            for event in intent["events"]
        ]
        log_path = self.item_dir / "log.jsonl"
        log_path.write_bytes(lines[0])
        limit = sum(map(len, lines))

        with (mock.patch.object(
                control, "_LOG_IMAGE_LIMIT", limit, create=True),
              mock.patch.object(
                  control, "_after_active",
                  side_effect=RuntimeError("simulated crash")),
              self.assertRaisesRegex(RuntimeError, "simulated crash")):
            control.commit_operation(self.repo, self.item, **args)

        active_path = self.item_dir / "control/active.json"
        self.assertTrue(active_path.is_file())
        self.assertEqual(log_path.read_bytes(), lines[0])
        self.assertEqual(self.target.read_bytes(), b"before\n")
        with mock.patch.object(
                control, "_LOG_IMAGE_LIMIT", limit, create=True):
            recovered = control.recover_pending(self.repo, self.item)
            retried = control.commit_operation(self.repo, self.item, **args)

        self.assertTrue(recovered.recovered)
        self.assertEqual(retried, recovered.receipt)
        self.assertEqual(log_path.read_bytes(), b"".join(lines))
        self.assertEqual(len(log_path.read_bytes()), limit)
        matching = [
            event for event in logs.read_events(self.repo, self.item)
            if event.get("operation_id") == retried.operation_id
        ]
        self.assertEqual(matching, intent["events"])
        self.assertEqual(self.target.read_bytes(), b"after\n")
        self.assertEqual(self.created.read_bytes(), b"created\n")
        self.assertFalse(active_path.exists())

    def test_recovery_refuses_persisted_log_over_shared_limit_without_mutation(self):
        args = self._operation_args(key="oversized-persisted-log")
        self._crash_operation(args)
        active_path = self.item_dir / "control/active.json"
        active = active_path.read_bytes()
        active_identity = active_path.stat().st_ino
        log_path = self.item_dir / "log.jsonl"
        oversized = (
            b'{"event": "unrelated", "ts": "durable", "padding": "xxxx"}\n'
        )
        log_path.write_bytes(oversized)
        log_identity = log_path.stat().st_ino

        with (mock.patch.object(
                control, "_LOG_IMAGE_LIMIT", len(oversized) - 1, create=True),
              self.assertRaisesRegex(
                  control.ControlError,
                  "control artifact exceeds its read limit")):
            control.recover_pending(self.repo, self.item)

        self.assertEqual(log_path.read_bytes(), oversized)
        self.assertEqual(log_path.stat().st_ino, log_identity)
        self.assertEqual(active_path.read_bytes(), active)
        self.assertEqual(active_path.stat().st_ino, active_identity)
        self.assertEqual(self.target.read_bytes(), b"before\n")
        self.assertFalse(self.created.exists())

    def test_oversized_intent_refuses_before_control_and_boundary_recovers(self):
        event = {
            "event": "control.large-shape",
            "ts": "2026-09-09T12:00:00Z",
            "data": {"payload": "e" * 256},
        }
        args = {
            "kind": "test.intent-limit",
            "key": "exact-boundary",
            "request": {"shape": {"payload": "r" * 256}},
            "events": (event,),
        }
        _intent, intent_bytes, _blobs = control._build_intent(
            self.repo, self.item, args["kind"], args["key"],
            args["request"], (), (), args["events"])
        limit = len(intent_bytes)

        with (mock.patch.object(
                control, "_INTENT_RECORD_LIMIT", limit - 1, create=True),
              self.assertRaisesRegex(
                  control.ControlRefusal,
                  "operation intent exceeds its read limit")):
            control.commit_operation(self.repo, self.item, **args)

        self.assertFalse((self.item_dir / "control").exists())
        self.assertFalse((self.item_dir / "log.jsonl").exists())
        self.assertEqual(self.target.read_bytes(), b"before\n")

        with (mock.patch.object(
                control, "_INTENT_RECORD_LIMIT", limit, create=True),
              mock.patch.object(
                  control, "_after_active",
                  side_effect=RuntimeError("simulated crash")),
              self.assertRaisesRegex(RuntimeError, "simulated crash")):
            control.commit_operation(self.repo, self.item, **args)

        operation = next(
            (self.item_dir / "control/operations").iterdir())
        self.assertEqual(
            len((operation / "intent.json").read_bytes()), limit)
        with (mock.patch.object(
                control, "_INTENT_RECORD_LIMIT", limit - 1, create=True),
              self.assertRaisesRegex(
                  control.ControlError,
                  "control artifact exceeds its read limit")):
            control.recover_pending(self.repo, self.item)
        self.assertTrue((self.item_dir / "control/active.json").is_file())

        with mock.patch.object(
                control, "_INTENT_RECORD_LIMIT", limit, create=True):
            recovered = control.recover_pending(self.repo, self.item)
            retry = control.commit_operation(self.repo, self.item, **args)

        self.assertTrue(recovered.recovered)
        self.assertEqual(retry, recovered.receipt)
        matching = [
            value for value in logs.read_events(self.repo, self.item)
            if value.get("operation_id") == retry.operation_id
        ]
        self.assertEqual(len(matching), 1)
        self.assertFalse((self.item_dir / "control/active.json").exists())

        operation_names = {
            path.name for path in
            (self.item_dir / "control/operations").iterdir()
        }
        with (mock.patch.object(
                control, "_INTENT_RECORD_LIMIT", limit - 1, create=True),
              self.assertRaisesRegex(
                  control.ControlError,
                  "control artifact exceeds its read limit")):
            control.commit_operation(
                self.repo, self.item, kind="test.intent-limit",
                key="conflict-scan", request={}, events=())
        self.assertEqual(
            {path.name for path in
             (self.item_dir / "control/operations").iterdir()},
            operation_names)

    def test_oversized_operation_blobs_refuse_without_control_poison(self):
        cases = ("prerequisite", "replacement-before", "replacement-after")
        for case in cases:
            with self.subTest(case=case):
                self._reset_operation_fixture()
                limit = 8
                oversized = b"x" * (limit + 1)
                self.target.write_bytes(
                    oversized if case in (
                        "prerequisite", "replacement-before") else b"before\n")
                snapshot = safeio.snapshot_path(
                    self.repo, f".factory/items/{self.item}/state.bin")
                kwargs = {
                    "kind": "test.blob-limit",
                    "key": case,
                    "request": {"case": case},
                    "events": (),
                }
                if case == "prerequisite":
                    kwargs["prerequisites"] = (snapshot,)
                else:
                    kwargs["replacements"] = ((
                        snapshot,
                        oversized if case == "replacement-after" else b"ok\n",
                    ),)

                with (mock.patch.object(
                        control, "_OPERATION_BLOB_LIMIT", limit, create=True),
                      self.assertRaisesRegex(
                          control.ControlRefusal,
                          "operation blob exceeds its read limit")):
                    control.commit_operation(self.repo, self.item, **kwargs)

                self.assertFalse((self.item_dir / "control").exists())
                self.assertEqual(
                    self.target.read_bytes(),
                    oversized if case in (
                        "prerequisite", "replacement-before") else b"before\n")
                self.assertFalse((self.item_dir / "log.jsonl").exists())

    def test_boundary_sized_operation_blob_succeeds_after_oversize_refusal(self):
        limit = 8
        before = safeio.snapshot_path(
            self.repo, f".factory/items/{self.item}/state.bin")
        common = {
            "kind": "test.blob-limit",
            "key": "no-poison",
            "request": {"case": "no-poison"},
            "events": (),
        }
        with (mock.patch.object(
                control, "_OPERATION_BLOB_LIMIT", limit, create=True),
              self.assertRaisesRegex(
                  control.ControlRefusal,
                  "operation blob exceeds its read limit")):
            control.commit_operation(
                self.repo, self.item, replacements=((before, b"x" * 9),),
                **common)

        self.assertFalse((self.item_dir / "control").exists())
        with mock.patch.object(
                control, "_OPERATION_BLOB_LIMIT", limit, create=True):
            receipt = control.commit_operation(
                self.repo, self.item, replacements=((before, b"12345678"),),
                **common)

        self.assertTrue(receipt.operation_id)
        self.assertEqual(self.target.read_bytes(), b"12345678")
        self.assertFalse((self.item_dir / "control/active.json").exists())

    def test_oversize_missing_publication_refuses_before_control_artifacts(self):
        data = b"created\n"
        relative = (f".factory/items/{self.item}/deep/" +
                    "/".join(chr(ord("a") + index) for index in range(12)) +
                    "/created.bin")
        missing = safeio.snapshot_path(
            self.repo, relative, allow_missing=True)
        required = safeio._publication_journal_upper_bound(missing, data)
        journal = self.item_dir / safeio._journal_name(missing.relative)

        with (mock.patch.object(
                safeio, "_PUBLICATION_JOURNAL_LIMIT", required - 1),
              self.assertRaisesRegex(
                  control.ControlRefusal, "publication journal.*limit")):
            control.commit_operation(
                self.repo, self.item, kind="test.journal-limit",
                key="oversize", request={},
                replacements=((missing, data),), events=())

        self.assertFalse((self.item_dir / "control").exists())
        self.assertFalse(journal.exists())
        self.assertFalse((self.item_dir / "deep").exists())
        self.assertFalse((self.repo / relative).exists())

        small = safeio.snapshot_path(
            self.repo, f".factory/items/{self.item}/small.bin",
            allow_missing=True)
        with mock.patch.object(
                safeio, "_PUBLICATION_JOURNAL_LIMIT", required - 1):
            receipt = control.commit_operation(
                self.repo, self.item, kind="test.journal-limit",
                key="small-after-refusal", request={},
                replacements=((small, b"small\n"),), events=())
        self.assertTrue(receipt.operation_id)
        self.assertEqual((self.item_dir / "small.bin").read_bytes(), b"small\n")

    def test_exact_publication_journal_boundary_settles_and_retries(self):
        data = b"created\n"
        relative = f".factory/items/{self.item}/exact/deep/created.bin"
        missing = safeio.snapshot_path(
            self.repo, relative, allow_missing=True)
        limit = safeio._publication_journal_upper_bound(missing, data)
        args = dict(
            kind="test.journal-limit", key="exact", request={},
            replacements=((missing, data),), events=())

        with mock.patch.object(
                safeio, "_PUBLICATION_JOURNAL_LIMIT", limit):
            receipt = control.commit_operation(self.repo, self.item, **args)
            retry = control.commit_operation(self.repo, self.item, **args)

        self.assertEqual(retry, receipt)
        self.assertEqual((self.repo / relative).read_bytes(), data)
        self.assertFalse((self.item_dir / "control/active.json").exists())
        self.assertFalse(
            (self.item_dir / safeio._journal_name(missing.relative)).exists())

    def test_commit_applies_ordered_replacements_and_one_authoritative_event(self):
        args = self._operation_args()
        receipt = control.commit_operation(self.repo, self.item, **args)
        retry = control.commit_operation(self.repo, self.item, **args)

        self.assertEqual(retry, receipt)
        self.assertEqual(self.target.read_bytes(), b"after\n")
        self.assertEqual(self.created.read_bytes(), b"created\n")
        events = logs.read_events(self.repo, self.item)
        matching = [event for event in events
                    if event.get("operation_id") == receipt.operation_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["event"], "control.test-completed")
        self.assertFalse((self.item_dir / "control/active.json").exists())
        self.assertTrue((self.item_dir / "control/operations" /
                         receipt.operation_id / "commit.json").is_file())

    def test_overlapping_missing_replacement_tails_refuse_before_publication(self):
        cases = (
            ("direct", ("new/a.bin", "new/b.bin")),
            ("nested", ("new/left/a.bin", "new/right/deep/b.bin")),
        )
        for label, relatives in cases:
            with self.subTest(case=label):
                self._reset_operation_fixture()
                control_dir = self.item_dir / "control"
                self.assertFalse(control_dir.exists())
                replacements = tuple(
                    (safeio.snapshot_path(
                        self.repo, f".factory/items/{self.item}/{relative}",
                        allow_missing=True),
                     f"{index}\n".encode("utf-8"))
                    for index, relative in enumerate(relatives)
                )
                intent, _raw, _blobs = control._build_intent(
                    self.repo, self.item, "test.overlap", label, {}, (),
                    replacements, ())

                with self.assertRaisesRegex(
                        control.ControlRefusal, "overlapping missing"):
                    control.commit_operation(
                        self.repo, self.item, kind="test.overlap", key=label,
                        request={}, replacements=replacements, events=())

                operation = (self.item_dir / "control/operations" /
                             intent["operation_id"])
                self.assertFalse(operation.exists())
                self.assertFalse(
                    (self.item_dir / "control/operations").exists())
                self.assertFalse(
                    (self.item_dir / "control/active.json").exists())
                self.assertFalse(control_dir.exists())
                for relative in relatives:
                    self.assertFalse((self.item_dir / relative).exists())

    def test_missing_prerequisite_replacement_tail_overlap_refuses_early(self):
        cases = (
            ("direct", "direct-new/a.bin", "direct-new/b.bin"),
            ("nested", "nested-new/left/a.bin",
             "nested-new/right/deep/b.bin"),
        )
        for label, prerequisite_relative, replacement_relative in cases:
            with self.subTest(case=label):
                self._reset_operation_fixture()
                control_dir = self.item_dir / "control"
                self.assertFalse(control_dir.exists())
                prerequisite = safeio.snapshot_path(
                    self.repo,
                    f".factory/items/{self.item}/{prerequisite_relative}",
                    allow_missing=True)
                replacement = safeio.snapshot_path(
                    self.repo,
                    f".factory/items/{self.item}/{replacement_relative}",
                    allow_missing=True)

                with self.assertRaisesRegex(
                        control.ControlRefusal,
                        "overlapping missing prerequisite/replacement tails"):
                    control.commit_operation(
                        self.repo, self.item, kind="test.overlap", key=label,
                        request={}, prerequisites=(prerequisite,),
                        replacements=((replacement, b"created\n"),), events=())

                self.assertFalse(control_dir.exists())
                self.assertFalse(
                    (self.item_dir / prerequisite_relative).exists())
                self.assertFalse(
                    (self.item_dir / replacement_relative).exists())

    def test_overlapping_missing_prerequisites_without_replacement_are_valid(self):
        prerequisites = tuple(
            safeio.snapshot_path(
                self.repo, f".factory/items/{self.item}/{relative}",
                allow_missing=True)
            for relative in ("new/left/a.bin", "new/right/deep/b.bin")
        )

        receipt = control.commit_operation(
            self.repo, self.item, kind="test.prerequisites",
            key="overlapping-missing", request={},
            prerequisites=prerequisites, events=())

        self.assertTrue(receipt.operation_id)
        for snapshot in prerequisites:
            self.assertFalse((snapshot.root / snapshot.relative).exists())

    def test_disjoint_missing_replacement_tails_commit(self):
        relatives = ("new-a/deep/a.bin", "new-b/deep/b.bin")
        replacements = tuple(
            (safeio.snapshot_path(
                self.repo, f".factory/items/{self.item}/{relative}",
                allow_missing=True),
             f"{index}\n".encode("utf-8"))
            for index, relative in enumerate(relatives)
        )

        receipt = control.commit_operation(
            self.repo, self.item, kind="test.disjoint", key="missing-tails",
            request={}, replacements=replacements, events=())

        self.assertTrue(receipt.operation_id)
        for index, relative in enumerate(relatives):
            self.assertEqual(
                (self.item_dir / relative).read_bytes(),
                f"{index}\n".encode("utf-8"))

    def test_os_exit_at_each_leaf_identity_boundary_recovers(self):
        boundaries = (
            "_after_leaf_staging_write",
            "_after_leaf_bind",
            "_after_leaf_link",
            "_after_leaf_unlink",
            "_after_leaf_install",
        )
        for index, hook in enumerate(boundaries):
            with self.subTest(hook=hook):
                source = f'''
import os
import sys
from scripts.factory.lib import control, safeio
repo, item = sys.argv[1], sys.argv[2]
missing = safeio.snapshot_path(
    repo, f".factory/items/{{item}}/created.bin", allow_missing=True)
setattr(safeio, "{hook}", lambda *_args: os._exit(110 + {index}))
control.commit_operation(
    repo, item, kind="test.leaf-exit", key="{hook}", request={{}},
    replacements=((missing, b"created\\n"),), events=())
'''
                crashed = self._subprocess(source)
                self.assertEqual(crashed.returncode, 110 + index,
                                 crashed.stderr)
                self.assertTrue(
                    (self.item_dir / "control/active.json").is_file())

                recovered = self._subprocess('''
import sys
from scripts.factory.lib import control
assert control.recover_pending(sys.argv[1], sys.argv[2]).recovered
''')
                self.assertEqual(recovered.returncode, 0, recovered.stderr)
                self.assertEqual(self.created.read_bytes(), b"created\n")
                self.assertFalse(
                    (self.item_dir / "control/active.json").exists())
                self._reset_operation_fixture()

    def test_os_exit_after_journal_link_before_directory_fsync_recovers(self):
        relative = f".factory/items/{self.item}/new/deep/created.bin"
        crashed = self._subprocess(f'''
import os
import sys
from scripts.factory.lib import control, safeio
repo, item = sys.argv[1], sys.argv[2]
missing = safeio.snapshot_path(repo, {relative!r}, allow_missing=True)
real_publish = safeio._publish_bound
def publish_with_journal_crash(directory_fd, name, data, **kwargs):
    after_install = kwargs.get("after_install")
    if name.startswith(".safeio-publish-"):
        after_install = lambda: os._exit(123)
    return real_publish(
        directory_fd, name, data,
        before_install=kwargs.get("before_install"),
        after_install=after_install)
safeio._publish_bound = publish_with_journal_crash
control.commit_operation(
    repo, item, kind="test.journal-exit", key="nested-tail", request={{}},
    replacements=((missing, b"created\\n"),), events=())
''')
        self.assertEqual(crashed.returncode, 123, crashed.stderr)

        active = self.item_dir / "control/active.json"
        self.assertTrue(active.is_file())
        journal = self.item_dir / safeio._journal_name(
            safeio._relative_path(relative))
        self.assertTrue(journal.is_file())
        state = json.loads(journal.read_text(encoding="utf-8"))
        self.assertEqual(state["directories"], [])
        self.assertEqual(state["leaf"]["attempts"][-1]["status"], "planned")
        self.assertFalse((self.item_dir / "new").exists())

        recovered = self._subprocess('''
import sys
from scripts.factory.lib import control
assert control.recover_pending(sys.argv[1], sys.argv[2]).recovered
''')
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual((self.repo / relative).read_bytes(), b"created\n")
        self.assertFalse(journal.exists())
        self.assertFalse(active.exists())

    def test_os_exit_after_link_then_after_unlink_recovers_sequentially(self):
        after_link = self._subprocess('''
import os
import sys
from scripts.factory.lib import control, safeio
repo, item = sys.argv[1], sys.argv[2]
missing = safeio.snapshot_path(
    repo, f".factory/items/{item}/created.bin", allow_missing=True)
safeio._after_leaf_link = lambda *_args: os._exit(121)
control.commit_operation(
    repo, item, kind="test.leaf-sequence", key="link-unlink", request={},
    replacements=((missing, b"created\\n"),), events=())
''')
        self.assertEqual(after_link.returncode, 121, after_link.stderr)
        self.assertTrue(self.created.is_file())
        self.assertEqual(
            len(list(self.item_dir.glob(".safeio-leaf-*.tmp"))), 1)
        self.assertEqual(
            len(list(self.item_dir.glob(".safeio-publish-*.json"))), 1)
        self.assertTrue((self.item_dir / "control/active.json").is_file())

        after_unlink = self._subprocess('''
import os
import sys
from scripts.factory.lib import control, safeio
safeio._after_leaf_unlink = lambda *_args: os._exit(122)
control.recover_pending(sys.argv[1], sys.argv[2])
''')
        self.assertEqual(after_unlink.returncode, 122, after_unlink.stderr)
        self.assertTrue(self.created.is_file())
        self.assertEqual(
            list(self.item_dir.glob(".safeio-leaf-*.tmp")), [])
        self.assertEqual(
            len(list(self.item_dir.glob(".safeio-publish-*.json"))), 1)
        self.assertTrue((self.item_dir / "control/active.json").is_file())

        recovered = self._subprocess('''
import sys
from scripts.factory.lib import control
assert control.recover_pending(sys.argv[1], sys.argv[2]).recovered
''')
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(self.created.read_bytes(), b"created\n")
        self.assertEqual(
            list(self.item_dir.glob(".safeio-publish-*.json")), [])
        self.assertFalse((self.item_dir / "control/active.json").exists())

    def test_fault_at_every_boundary_recovers_forward_exactly_once(self):
        cases = [
            ("_after_intent", 0),
            ("_after_blob", 0),
            ("_after_blob", 1),
            ("_after_blob", 2),
            ("_after_active", 0),
            ("_after_replacement", 0),
            ("_after_replacement", 1),
            ("_after_event", 0),
            ("_after_commit", 0),
            ("_after_active_removal", 0),
        ]
        for hook, fail_index in cases:
            with self.subTest(hook=hook, fail_index=fail_index):
                with tempfile.TemporaryDirectory() as raw:
                    repo = Path(raw).resolve()
                    _git(repo, "init", "-q")
                    initrepo.init(repo)
                    items.save_item(repo, {
                        "id": self.item, "title": "Thing",
                        "stage": "implement", "kind": "backend",
                        "created": "x", "updated": "x",
                    }, "")
                    item_dir = repo / ".factory/items" / self.item
                    (item_dir / "state.bin").write_bytes(b"before\n")
                    before = safeio.snapshot_path(
                        repo, f".factory/items/{self.item}/state.bin")
                    missing = safeio.snapshot_path(
                        repo, f".factory/items/{self.item}/created.bin",
                        allow_missing=True)
                    config = safeio.snapshot_path(repo, ".factory/config.json")
                    args = dict(
                        kind="test.commit", key="round-1",
                        request={"round": 1}, prerequisites=(config,),
                        replacements=((before, b"after\n"),
                                      (missing, b"created\n")),
                        events=({"event": "control.test-completed",
                                 "ts": "2026-09-08T12:00:00Z"},))
                    calls = 0

                    def crash_at(*_unused):
                        nonlocal calls
                        current = calls
                        calls += 1
                        if current == fail_index:
                            raise RuntimeError("simulated crash")

                    with mock.patch.object(control, hook,
                                           side_effect=crash_at):
                        with self.assertRaisesRegex(
                                RuntimeError, "simulated crash"):
                            control.commit_operation(repo, self.item, **args)

                    receipt = control.commit_operation(repo, self.item, **args)
                    self.assertEqual((item_dir / "state.bin").read_bytes(),
                                     b"after\n")
                    self.assertEqual((item_dir / "created.bin").read_bytes(),
                                     b"created\n")
                    matching = [event for event in logs.read_events(
                        repo, self.item)
                        if event.get("operation_id") == receipt.operation_id]
                    self.assertEqual(len(matching), 1)

    def test_recover_pending_uses_persisted_intent_and_conflict_waits(self):
        args = self._operation_args()
        with mock.patch.object(
                control, "_after_active",
                side_effect=RuntimeError("simulated crash")):
            with self.assertRaises(RuntimeError):
                control.commit_operation(self.repo, self.item, **args)

        with self.assertRaisesRegex(control.ControlRefusal, "pending"):
            control.commit_operation(
                self.repo, self.item, **self._operation_args(key="round-2"))
        with self.assertRaisesRegex(control.ControlRefusal, "pending"):
            control.require_settled(self.repo, self.item)

        recovered = control.recover_pending(self.repo, self.item)
        self.assertTrue(recovered.recovered)
        self.assertEqual(self.target.read_bytes(), b"after\n")
        self.assertFalse((self.item_dir / "control/active.json").exists())
        control.require_settled(self.repo, self.item)

    def test_recovery_durability_barrier_precedes_first_effect(self):
        args = self._operation_args(key="recovery-durability-barrier")
        _operation_id, operation = self._crash_operation(args)
        control_dir = self.item_dir / "control"
        blobs = tuple((operation / "blobs").iterdir())
        required = {
            (operation / "intent.json").stat().st_ino,
            *(path.stat().st_ino for path in blobs),
            (control_dir / "active.json").stat().st_ino,
            control_dir.stat().st_ino,
            (control_dir / "operations").stat().st_ino,
            operation.stat().st_ino,
            (operation / "blobs").stat().st_ino,
        }
        synced = set()
        real_fsync = os.fsync
        real_apply = control._apply_replacement

        def record_sync(fd):
            synced.add(os.fstat(fd).st_ino)
            return real_fsync(fd)

        def require_barrier(replacement, values, repo):
            self.assertTrue(required.issubset(synced), required - synced)
            return real_apply(replacement, values, repo)

        with (mock.patch.object(control.os, "fsync", side_effect=record_sync),
              mock.patch.object(
                  control, "_apply_replacement", side_effect=require_barrier)):
            recovered = control.recover_pending(self.repo, self.item)

        self.assertTrue(recovered.recovered)
        self.assertEqual(self.target.read_bytes(), b"after\n")

    def test_recovery_durability_failure_retains_active_without_effects(self):
        args = self._operation_args(key="recovery-durability-refusal")
        _operation_id, operation = self._crash_operation(args)
        intent_inode = (operation / "intent.json").stat().st_ino
        real_fsync = os.fsync

        def refuse_intent_sync(fd):
            if os.fstat(fd).st_ino == intent_inode:
                raise OSError("simulated durability refusal")
            return real_fsync(fd)

        with (mock.patch.object(
                control.os, "fsync", side_effect=refuse_intent_sync),
              self.assertRaises(control.ControlError)):
            control.recover_pending(self.repo, self.item)

        self.assertEqual(self.target.read_bytes(), b"before\n")
        self.assertFalse(self.created.exists())
        self.assertTrue((self.item_dir / "control/active.json").is_file())

    def test_stale_preflight_creates_no_request_directory_and_next_can_commit(self):
        stale = safeio.snapshot_path(self.repo, ".factory/config.json")
        config = self.repo / ".factory/config.json"
        config.write_bytes(config.read_bytes() + b" ")
        stale_args = dict(
            kind="test.stale", key="first", request={"attempt": 1},
            prerequisites=(stale,), replacements=(), events=())
        stale_intent, _raw, _blobs = control._build_intent(
            self.repo, self.item, **stale_args)

        with self.assertRaisesRegex(control.ControlRefusal, "prerequisite"):
            control.commit_operation(self.repo, self.item, **stale_args)

        stale_dir = (self.item_dir / "control/operations" /
                     stale_intent["operation_id"])
        self.assertFalse(stale_dir.exists())
        fresh = safeio.snapshot_path(self.repo, ".factory/config.json")
        receipt = control.commit_operation(
            self.repo, self.item, kind="test.stale", key="second",
            request={"attempt": 2}, prerequisites=(fresh,), events=())
        self.assertEqual(receipt.key, "second")

    def test_eventless_operation_rejects_attributed_events_at_every_boundary(self):
        phases = ("preflight", "recovery", "receipt")
        for phase in phases:
            with self.subTest(phase=phase):
                args = dict(
                    kind="test.eventless", key=phase,
                    request={"phase": phase},
                    prerequisites=(),
                    replacements=((safeio.snapshot_path(
                        self.repo,
                        f".factory/items/{self.item}/state.bin"),
                        b"after\n"),),
                    events=())
                intent, _raw, _blobs = control._build_intent(
                    self.repo, self.item, **args)
                attributed = {
                    "event": "injected.event",
                    "operation_id": intent["operation_id"],
                    "ts": "2026-09-08T11:59:00Z",
                }
                log = self.item_dir / "log.jsonl"

                if phase == "preflight":
                    log.write_text(
                        json.dumps(attributed, sort_keys=True) + "\n",
                        encoding="utf-8")
                elif phase == "recovery":
                    self._crash_operation(args)
                    log.write_text(
                        json.dumps(attributed, sort_keys=True) + "\n",
                        encoding="utf-8")
                else:
                    control.commit_operation(self.repo, self.item, **args)
                    log.write_text(
                        json.dumps(attributed, sort_keys=True) + "\n",
                        encoding="utf-8")

                operation = (control.recover_pending
                             if phase == "recovery"
                             else lambda repo, item: control.commit_operation(
                                 repo, item, **args))
                with self.assertRaisesRegex(
                        control.ControlRefusal, "operation events|event"):
                    operation(self.repo, self.item)
                if phase == "recovery":
                    self.assertTrue(
                        (self.item_dir / "control/active.json").is_file())
                if phase != "receipt":
                    self.assertEqual(self.target.read_bytes(), b"before\n")
                self._reset_operation_fixture()

    def test_event_adoption_compares_exact_canonical_json_types(self):
        substitutions = (1, 1.0)
        phases = ("preflight", "recovery", "receipt")
        for substitution in substitutions:
            for phase in phases:
                with self.subTest(substitution=substitution, phase=phase):
                    args = dict(
                        kind="test.event-types",
                        key=f"{phase}-{type(substitution).__name__}",
                        request={"phase": phase},
                        prerequisites=(),
                        replacements=((safeio.snapshot_path(
                            self.repo,
                            f".factory/items/{self.item}/state.bin"),
                            b"after\n"),),
                        events=({
                            "event": "control.typed-event",
                            "ts": "2026-09-09T16:00:00Z",
                            "data": {"nested": {"value": True}},
                        },),
                    )
                    intent, _raw, _blobs = control._build_intent(
                        self.repo, self.item, **args)
                    conflicting = json.loads(json.dumps(intent["events"][0]))
                    conflicting["data"]["nested"]["value"] = substitution
                    intended_encoding = control._canonical(
                        intent["events"][0])[0]
                    conflicting_encoding = control._canonical(conflicting)[0]
                    self.assertNotEqual(
                        conflicting_encoding, intended_encoding)
                    self.assertEqual(conflicting, intent["events"][0])

                    log_path = self.item_dir / "log.jsonl"
                    active_path = self.item_dir / "control/active.json"
                    if phase == "preflight":
                        log_path.write_bytes(logs._entry_bytes(conflicting))
                        marker_path = None
                    elif phase == "recovery":
                        self._crash_operation(args)
                        log_path.write_bytes(logs._entry_bytes(conflicting))
                        marker_path = active_path
                    else:
                        receipt = control.commit_operation(
                            self.repo, self.item, **args)
                        operation = (self.item_dir / "control/operations" /
                                     receipt.operation_id)
                        marker_path = operation / "commit.json"
                        log_path.write_bytes(logs._entry_bytes(conflicting))

                    log_bytes = log_path.read_bytes()
                    log_identity = log_path.stat().st_ino
                    marker_bytes = (marker_path.read_bytes()
                                    if marker_path is not None else None)
                    marker_identity = (marker_path.stat().st_ino
                                       if marker_path is not None else None)
                    operation = (control.recover_pending
                                 if phase == "recovery"
                                 else lambda repo, item:
                                 control.commit_operation(
                                     repo, item, **args))
                    with self.assertRaisesRegex(
                            control.ControlRefusal,
                            "operation events|event"):
                        operation(self.repo, self.item)

                    self.assertEqual(log_path.read_bytes(), log_bytes)
                    self.assertEqual(log_path.stat().st_ino, log_identity)
                    if marker_path is not None:
                        self.assertEqual(marker_path.read_bytes(), marker_bytes)
                        self.assertEqual(
                            marker_path.stat().st_ino, marker_identity)
                    if phase != "receipt":
                        self.assertEqual(self.target.read_bytes(), b"before\n")
                    self._reset_operation_fixture()

    def test_replacement_authority_survives_repeated_operation_detachment(self):
        relative = f".factory/items/{self.item}/authority/deep/created.bin"
        missing = safeio.snapshot_path(
            self.repo, relative, allow_missing=True)
        args = dict(
            kind="test.authority", key="detached-operation", request={},
            replacements=((missing, b"created\n"),), events=())
        journal = self.item_dir / safeio._journal_name(missing.relative)
        destination = self.repo / relative
        operations = self.item_dir / "control/operations"
        real_publish = control._publish_immutable
        attacks = []

        def detach_during_authority(directory_fd, name, data, **kwargs):
            if not name.endswith(".authority.json"):
                return real_publish(directory_fd, name, data, **kwargs)
            active = json.loads(
                (self.item_dir / "control/active.json").read_text())
            operation = operations / active["operation_id"]
            detached = operations / (
                f"{active['operation_id']}.detached-{len(attacks)}")
            operations_identity = operations.stat().st_ino
            source_identity = operation.stat().st_ino
            operation.rename(detached)
            shutil.copytree(detached, operation)
            substitute_identity = operation.stat().st_ino
            self.assertNotEqual(substitute_identity, source_identity)
            identity = real_publish(directory_fd, name, data, **kwargs)
            authority = detached / name
            attacks.append({
                "detached": detached,
                "operation_identity": source_identity,
                "operations_identity": operations_identity,
                "authority": authority,
                "authority_bytes": authority.read_bytes(),
                "authority_identity": authority.stat().st_ino,
                "published_identity": identity,
            })
            self.assertEqual(authority.read_bytes(), data)
            self.assertEqual(authority.stat().st_ino, identity[1])
            return identity

        with mock.patch.object(
                control, "_publish_immutable",
                side_effect=detach_during_authority):
            with self.assertRaisesRegex(
                    control.ControlError, "identity|detached"):
                control.commit_operation(self.repo, self.item, **args)

            self.assertTrue(journal.is_file())
            journal_bytes = journal.read_bytes()
            journal_identity = journal.stat().st_ino
            destination_bytes = destination.read_bytes()
            destination_identity = destination.stat().st_ino
            active_path = self.item_dir / "control/active.json"
            active_bytes = active_path.read_bytes()
            active_identity = active_path.stat().st_ino

            for _attempt in range(2):
                with self.assertRaisesRegex(
                        control.ControlError, "identity|detached"):
                    control.recover_pending(self.repo, self.item)
                self.assertEqual(journal.read_bytes(), journal_bytes)
                self.assertEqual(journal.stat().st_ino, journal_identity)
                self.assertEqual(destination.read_bytes(), destination_bytes)
                self.assertEqual(destination.stat().st_ino,
                                 destination_identity)
                self.assertEqual(active_path.read_bytes(), active_bytes)
                self.assertEqual(active_path.stat().st_ino, active_identity)
                self.assertFalse((operations / json.loads(
                    active_bytes)["operation_id"] / "commit.json").exists())
                self.assertFalse((self.item_dir / "log.jsonl").exists())
                for attack in attacks:
                    self.assertEqual(
                        attack["detached"].parent.stat().st_ino,
                        attack["operations_identity"])
                    self.assertEqual(
                        attack["detached"].stat().st_ino,
                        attack["operation_identity"])
                    self.assertEqual(
                        attack["authority"].read_bytes(),
                        attack["authority_bytes"])
                    self.assertEqual(
                        attack["authority"].stat().st_ino,
                        attack["authority_identity"])

        operation_id = json.loads(active_bytes)["operation_id"]
        operation = operations / operation_id
        restored = attacks[-1]
        shutil.rmtree(operation)
        restored["detached"].rename(operation)
        self.assertEqual(operation.parent.stat().st_ino,
                         restored["operations_identity"])
        self.assertEqual(operation.stat().st_ino,
                         restored["operation_identity"])
        authority = operation / restored["authority"].name
        self.assertEqual(authority.read_bytes(), restored["authority_bytes"])
        self.assertEqual(authority.stat().st_ino,
                         restored["authority_identity"])

        recovered = control.recover_pending(self.repo, self.item)
        self.assertTrue(recovered.recovered)
        self.assertEqual(destination.read_bytes(), destination_bytes)
        self.assertEqual(destination.stat().st_ino, destination_identity)
        self.assertFalse(journal.exists())
        self.assertFalse(active_path.exists())

    def test_missing_publication_in_place_staging_mutation_fails_closed(self):
        relative = f".factory/items/{self.item}/created-in-place.bin"
        intended = b"created\n"
        foreign = b"hostile\n"
        missing = safeio.snapshot_path(
            self.repo, relative, allow_missing=True)
        args = dict(
            kind="test.authority", key="in-place-staging-mutation", request={},
            replacements=((missing, intended),), events=())
        destination = self.repo / relative
        active = self.item_dir / "control/active.json"
        journal = self.item_dir / safeio._journal_name(missing.relative)
        observed = {}

        def mutate_bound_staging():
            staging, = self.item_dir.glob(".safeio-leaf-*.tmp")
            observed["path"] = staging
            observed["identity"] = safeio._file_identity(staging.stat())
            staging.write_bytes(foreign)
            observed["mutated_identity"] = safeio._file_identity(
                staging.stat())

        with (mock.patch.object(
                safeio, "_before_publish", side_effect=mutate_bound_staging),
              self.assertRaisesRegex(
                  control.ControlRefusal, "replacement.*third state")):
            control.commit_operation(self.repo, self.item, **args)

        staging = observed["path"]
        self.assertNotEqual(
            observed["identity"], observed["mutated_identity"])
        self.assertFalse(destination.exists())
        self.assertEqual(staging.read_bytes(), foreign)
        self.assertTrue(journal.is_file())
        self.assertTrue(active.is_file())
        evidence = {
            "staging": (staging.read_bytes(), safeio._file_identity(
                staging.stat())),
            "journal": (journal.read_bytes(), safeio._file_identity(
                journal.stat())),
            "active": (active.read_bytes(), safeio._file_identity(
                active.stat())),
        }

        for _attempt in range(2):
            with self.assertRaisesRegex(
                    control.ControlRefusal, "replacement.*third state"):
                control.recover_pending(self.repo, self.item)
            self.assertFalse(destination.exists())
            self.assertEqual(
                (staging.read_bytes(), safeio._file_identity(staging.stat())),
                evidence["staging"])
            self.assertEqual(
                (journal.read_bytes(), safeio._file_identity(journal.stat())),
                evidence["journal"])
            self.assertEqual(
                (active.read_bytes(), safeio._file_identity(active.stat())),
                evidence["active"])

    def test_recovery_refuses_same_byte_leaf_and_ancestor_replacement(self):
        for attack in ("leaf", "ancestor"):
            with self.subTest(attack=attack):
                nested = self.item_dir / f"nested-{attack}"
                nested.mkdir()
                target = nested / "state.bin"
                target.write_bytes(b"before\n")
                before = safeio.snapshot_path(
                    self.repo, target.relative_to(self.repo).as_posix())
                args = dict(
                    kind="test.identity", key=attack, request={"attack": attack},
                    replacements=((before, b"after\n"),), events=())
                self._crash_operation(args)
                if attack == "leaf":
                    replacement = nested / "replacement.bin"
                    replacement.write_bytes(b"before\n")
                    os.replace(replacement, target)
                else:
                    detached = self.item_dir / f"nested-{attack}-detached"
                    nested.rename(detached)
                    nested.mkdir()
                    target = nested / "state.bin"
                    target.write_bytes(b"before\n")
                with self.assertRaisesRegex(
                        control.ControlRefusal, "replacement|state|identity"):
                    control.recover_pending(self.repo, self.item)
                self.assertTrue(
                    (self.item_dir / "control/active.json").is_file())
                self._reset_operation_fixture()

    def test_recovery_adopts_after_only_under_original_ancestor_chain(self):
        nested = self.item_dir / "bound-parent"
        nested.mkdir()
        target = nested / "state.bin"
        target.write_bytes(b"before\n")
        before = safeio.snapshot_path(
            self.repo, target.relative_to(self.repo).as_posix())
        args = dict(
            kind="test.identity", key="after-ancestor", request={},
            replacements=((before, b"after\n"),), events=())
        self._crash_operation(args, hook="_after_replacement")
        detached = self.item_dir / "bound-parent-detached"
        nested.rename(detached)
        nested.mkdir()
        target = nested / "state.bin"
        target.write_bytes(b"after\n")

        with self.assertRaisesRegex(
                control.ControlRefusal, "replacement|state|identity"):
            control.recover_pending(self.repo, self.item)
        self.assertTrue((self.item_dir / "control/active.json").is_file())

    def test_missing_publication_conflict_is_not_hidden_by_matching_leaf(self):
        relative = f".factory/items/{self.item}/new/deep/created.bin"
        missing = safeio.snapshot_path(
            self.repo, relative, allow_missing=True)
        args = dict(
            kind="test.missing", key="journal-conflict", request={},
            replacements=((missing, b"created\n"),), events=())
        self._crash_operation(args)
        destination = self.repo / relative
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"created\n")
        journal = self.item_dir / safeio._journal_name(missing.relative)
        journal.write_bytes(b"{}\n")

        with self.assertRaises(control.ControlRefusal):
            control.recover_pending(self.repo, self.item)
        self.assertTrue(journal.is_file())
        self.assertTrue((self.item_dir / "control/active.json").is_file())

    def test_missing_publication_recovery_refuses_copied_created_namespace(self):
        relative = f".factory/items/{self.item}/new/deep/created.bin"
        missing = safeio.snapshot_path(
            self.repo, relative, allow_missing=True)
        args = dict(
            kind="test.missing", key="copied-created-namespace", request={},
            replacements=((missing, b"created\n"),), events=())
        self._crash_operation(args, hook="_after_replacement")

        created_parent = self.item_dir / "new"
        detached = self.item_dir / "new-detached"
        created_parent.rename(detached)
        shutil.copytree(detached, created_parent)

        with self.assertRaisesRegex(
                control.ControlRefusal, "replacement|identity|namespace"):
            control.recover_pending(self.repo, self.item)
        self.assertTrue((self.item_dir / "control/active.json").is_file())

    def test_missing_publication_leaf_identity_is_checked_before_receipt(self):
        relative = f".factory/items/{self.item}/late/deep/created.bin"
        missing = safeio.snapshot_path(
            self.repo, relative, allow_missing=True)
        args = dict(
            kind="test.missing", key="late-leaf-substitution", request={},
            replacements=((missing, b"created\n"),), events=())
        destination = self.repo / relative

        def replace_leaf_with_matching_copy():
            copied = destination.with_name("copied.bin")
            copied.write_bytes(destination.read_bytes())
            os.replace(copied, destination)

        with (mock.patch.object(
                control, "_before_commit_validation",
                side_effect=replace_leaf_with_matching_copy),
              self.assertRaisesRegex(
                  control.ControlRefusal, "replacement|identity|namespace")):
            control.commit_operation(self.repo, self.item, **args)

        active = self.item_dir / "control/active.json"
        self.assertTrue(active.is_file())
        operation_id = json.loads(active.read_text())["operation_id"]
        self.assertFalse((self.item_dir / "control/operations" /
                          operation_id / "commit.json").exists())

    def test_wal_directory_renames_cannot_publish_a_commit_receipt(self):
        for boundary in ("operations", "operation", "blobs"):
            with self.subTest(boundary=boundary):
                args = self._operation_args(key=f"detach-{boundary}")
                attacked = False

                def detach(_index):
                    nonlocal attacked
                    if attacked:
                        return
                    attacked = True
                    active = json.loads((self.item_dir /
                                         "control/active.json").read_text())
                    operations = self.item_dir / "control/operations"
                    operation = operations / active["operation_id"]
                    target = {"operations": operations,
                              "operation": operation,
                              "blobs": operation / "blobs"}[boundary]
                    detached = target.with_name(target.name + "-detached")
                    target.rename(detached)
                    shutil.copytree(detached, target)

                with (mock.patch.object(
                        control, "_after_replacement", side_effect=detach),
                      self.assertRaisesRegex(
                          control.ControlError, "identity|detached")):
                    control.commit_operation(self.repo, self.item, **args)
                self.assertTrue(
                    (self.item_dir / "control/active.json").is_file())
                active = json.loads((self.item_dir /
                                     "control/active.json").read_text())
                self.assertFalse((self.item_dir / "control/operations" /
                                  active["operation_id"] /
                                  "commit.json").exists())

                # Each subtest leaves a deliberately conflicted active WAL, so
                # reset only the fixture-owned control namespace for the next
                # independent boundary attack.
                self._reset_operation_fixture()

    def test_complete_state_is_revalidated_immediately_before_receipt(self):
        mutations = ("prerequisite", "replacement", "event")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                args = self._operation_args(key=f"late-{mutation}")

                def mutate():
                    if mutation == "prerequisite":
                        config = self.repo / ".factory/config.json"
                        config.write_bytes(config.read_bytes() + b" ")
                    elif mutation == "replacement":
                        self.target.write_bytes(b"late-third-state\n")
                    else:
                        log = self.item_dir / "log.jsonl"
                        event = json.loads(log.read_text().splitlines()[-1])
                        log.write_text(
                            log.read_text() + json.dumps(
                                event, sort_keys=True) + "\n",
                            encoding="utf-8")

                with (mock.patch.object(
                        control, "_before_commit_validation",
                        side_effect=mutate),
                      self.assertRaises(control.ControlRefusal)):
                    control.commit_operation(self.repo, self.item, **args)
                self.assertTrue(
                    (self.item_dir / "control/active.json").is_file())
                self._reset_operation_fixture()

    def test_nonempty_log_without_final_newline_refuses_before_effects(self):
        args = self._operation_args(key="unterminated-log")
        log = self.item_dir / "log.jsonl"
        log.write_bytes(json.dumps({
            "event": "ordinary.event", "ts": "2026-09-08T11:00:00Z",
        }, sort_keys=True).encode("utf-8"))

        with self.assertRaisesRegex(control.ControlRefusal, "newline"):
            control.commit_operation(self.repo, self.item, **args)
        self.assertEqual(self.target.read_bytes(), b"before\n")
        self.assertFalse(self.created.exists())

    def test_recovery_fsyncs_adopted_artifacts_effects_events_and_directories(self):
        args = self._operation_args(key="durable-adoption")
        _operation_id, operation = self._crash_operation(
            args, hook="_after_event")
        log = self.item_dir / "log.jsonl"
        blobs = tuple((operation / "blobs").iterdir())
        required = {
            (operation / "intent.json").stat().st_ino,
            *(path.stat().st_ino for path in blobs),
            self.target.stat().st_ino,
            self.created.stat().st_ino,
            log.stat().st_ino,
            operation.stat().st_ino,
            (operation / "blobs").stat().st_ino,
            operation.parent.stat().st_ino,
            self.item_dir.stat().st_ino,
        }
        synced = set()
        real_fsync = os.fsync
        real_publish = control._publish_immutable

        def record_sync(fd):
            synced.add(os.fstat(fd).st_ino)
            return real_fsync(fd)

        def require_sync_before_commit(directory_fd, name, data):
            if name == "commit.json":
                self.assertTrue(required.issubset(synced), required - synced)
            return real_publish(directory_fd, name, data)

        with (mock.patch.object(control.os, "fsync", side_effect=record_sync),
              mock.patch.object(
                  control, "_publish_immutable",
                  side_effect=require_sync_before_commit)):
            control.recover_pending(self.repo, self.item)

    def test_abrupt_death_between_write_and_fsync_recovers_in_subprocess(self):
        source = r'''
import json
import os
import stat
import sys
from pathlib import Path
from scripts.factory.lib import control, safeio
repo = Path(sys.argv[1])
item = sys.argv[2]
item_dir = repo / ".factory/items" / item
before = safeio.snapshot_path(repo, f".factory/items/{item}/state.bin")
real_fsync = os.fsync
item_identity = (item_dir.stat().st_dev, item_dir.stat().st_ino)
def die_before_directory_sync(fd):
    details = os.fstat(fd)
    if (stat.S_ISDIR(details.st_mode) and
            (details.st_dev, details.st_ino) == item_identity and
            (item_dir / "state.bin").read_bytes() == b"after\n" and
            (item_dir / "control/active.json").exists()):
        os._exit(91)
    return real_fsync(fd)
os.fsync = die_before_directory_sync
control.commit_operation(
    repo, item, kind="test.process-death", key="replacement-fsync",
    request={}, replacements=((before, b"after\n"),), events=())
'''
        crashed = self._subprocess(source)
        self.assertEqual(crashed.returncode, 91, crashed.stderr)
        self.assertTrue((self.item_dir / "control/active.json").is_file())

        recover = self._subprocess('''
import sys
from scripts.factory.lib import control
result = control.recover_pending(sys.argv[1], sys.argv[2])
assert result.recovered
''')
        self.assertEqual(recover.returncode, 0, recover.stderr)
        self.assertEqual(self.target.read_bytes(), b"after\n")
        self.assertFalse((self.item_dir / "control/active.json").exists())

    def test_abrupt_death_after_event_write_before_fsync_recovers(self):
        source = r'''
import os
import stat
import sys
from pathlib import Path
from scripts.factory.lib import control, safeio
repo = Path(sys.argv[1])
item = sys.argv[2]
item_dir = repo / ".factory/items" / item
log = item_dir / "log.jsonl"
before = safeio.snapshot_path(repo, f".factory/items/{item}/state.bin")
real_fsync = os.fsync
def die_before_log_sync(fd):
    details = os.fstat(fd)
    try:
        named = log.stat()
        written = b'"operation_id"' in log.read_bytes()
    except FileNotFoundError:
        named = None
        written = False
    if (named is not None and stat.S_ISREG(details.st_mode) and
            (details.st_dev, details.st_ino) ==
            (named.st_dev, named.st_ino) and written and
            (item_dir / "control/active.json").exists()):
        os._exit(92)
    return real_fsync(fd)
os.fsync = die_before_log_sync
control.commit_operation(
    repo, item, kind="test.process-death", key="event-fsync",
    request={}, replacements=((before, b"after\n"),),
    events=({"event": "control.test", "ts": "2026-09-08T12:00:00Z"},))
'''
        crashed = self._subprocess(source)
        self.assertEqual(crashed.returncode, 92, crashed.stderr)
        self.assertTrue((self.item_dir / "control/active.json").is_file())

        recovered = self._subprocess('''
import sys
from scripts.factory.lib import control
assert control.recover_pending(sys.argv[1], sys.argv[2]).recovered
''')
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        events = logs.read_events(self.repo, self.item)
        self.assertEqual(sum(
            event.get("event") == "control.test" for event in events), 1)

    def test_abrupt_death_after_wal_link_before_directory_fsync_retries(self):
        source = r'''
import os
import stat
import sys
from pathlib import Path
from scripts.factory.lib import control, safeio
repo = Path(sys.argv[1])
item = sys.argv[2]
item_dir = repo / ".factory/items" / item
before = safeio.snapshot_path(repo, f".factory/items/{item}/state.bin")
real_fsync = os.fsync
def die_before_intent_directory_sync(fd):
    details = os.fstat(fd)
    if stat.S_ISDIR(details.st_mode):
        try:
            entries = set(os.listdir(fd))
        except OSError:
            entries = set()
        if ("intent.json" in entries and "blobs" in entries and
                not (item_dir / "control/active.json").exists()):
            os._exit(93)
    return real_fsync(fd)
os.fsync = die_before_intent_directory_sync
control.commit_operation(
    repo, item, kind="test.process-death", key="intent-dir-fsync",
    request={}, replacements=((before, b"after\n"),), events=())
'''
        crashed = self._subprocess(source)
        self.assertEqual(crashed.returncode, 93, crashed.stderr)
        self.assertFalse((self.item_dir / "control/active.json").exists())

        retried = self._subprocess('''
import sys
from scripts.factory.lib import control, safeio
repo, item = sys.argv[1], sys.argv[2]
before = safeio.snapshot_path(repo, f".factory/items/{item}/state.bin")
control.commit_operation(
    repo, item, kind="test.process-death", key="intent-dir-fsync",
    request={}, replacements=((before, b"after\\n"),), events=())
''')
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertEqual(self.target.read_bytes(), b"after\n")

    def test_nested_and_leaf_symlink_and_rename_boundary_attacks_refuse(self):
        for attack in ("nested-symlink", "leaf-symlink", "rename-boundary"):
            with self.subTest(attack=attack):
                nested = self.item_dir / f"path-{attack}"
                nested.mkdir()
                target = nested / "state.bin"
                target.write_bytes(b"before\n")
                before = safeio.snapshot_path(
                    self.repo, target.relative_to(self.repo).as_posix())
                args = dict(
                    kind="test.namespace", key=attack, request={},
                    replacements=((before, b"after\n"),), events=())
                self._crash_operation(args)
                outside = Path(self.tmp.name) / f"outside-{attack}"
                outside.mkdir()
                if attack == "nested-symlink":
                    detached = nested.with_name(nested.name + "-detached")
                    nested.rename(detached)
                    nested.symlink_to(outside, target_is_directory=True)
                elif attack == "leaf-symlink":
                    target.unlink()
                    target.symlink_to(outside / "state.bin")
                else:
                    real_before_replace = safeio._before_replace

                    def rename_at_boundary():
                        detached = nested.with_name(nested.name + "-detached")
                        nested.rename(detached)
                        nested.mkdir()
                        (nested / "state.bin").write_bytes(b"before\n")
                        real_before_replace()

                    patcher = mock.patch.object(
                        safeio, "_before_replace", side_effect=rename_at_boundary)
                context = patcher if attack == "rename-boundary" else nullcontext()
                with context, self.assertRaises(
                        (control.ControlError, control.ControlRefusal)):
                    control.recover_pending(self.repo, self.item)
                self.assertTrue(
                    (self.item_dir / "control/active.json").is_file())
                if attack != "rename-boundary":
                    self.assertEqual(list(outside.iterdir()), [])
                self._reset_operation_fixture()

    def test_third_state_and_duplicate_operation_event_fail_closed(self):
        for corruption in ("third-state", "duplicate-event"):
            with self.subTest(corruption=corruption):
                args = self._operation_args(key=corruption)
                with mock.patch.object(
                        control, "_after_active",
                        side_effect=RuntimeError("simulated crash")):
                    with self.assertRaises(RuntimeError):
                        control.commit_operation(self.repo, self.item, **args)
                active = json.loads((self.item_dir /
                                     "control/active.json").read_text())
                operation_id = active["operation_id"]
                if corruption == "third-state":
                    self.target.write_bytes(b"neither\n")
                else:
                    event = {
                        "event": "control.test-completed",
                        "operation_id": operation_id,
                        "ts": "2026-09-08T12:00:00Z",
                        "data": {"round": 1},
                    }
                    raw = (json.dumps(event, sort_keys=True) + "\n") * 2
                    (self.item_dir / "log.jsonl").write_text(
                        raw, encoding="utf-8")
                with self.assertRaises(control.ControlRefusal):
                    control.recover_pending(self.repo, self.item)
                self.assertTrue((self.item_dir /
                                 "control/active.json").is_file())
                if corruption == "third-state":
                    # Recreating the old bytes changes the original WAL-bound
                    # inode and must remain refused; bytes are not identity.
                    self.target.write_bytes(b"before\n")
                    with self.assertRaises(control.ControlRefusal):
                        control.recover_pending(self.repo, self.item)
                else:
                    (self.item_dir / "log.jsonl").unlink()
                    control.recover_pending(self.repo, self.item)
                self._reset_operation_fixture()

    def test_malformed_log_and_wal_records_refuse_without_repair(self):
        args = self._operation_args()
        log_path = self.item_dir / "log.jsonl"
        log_path.write_bytes(b"{not json}\n")
        before = log_path.read_bytes()
        with self.assertRaises(control.ControlRefusal):
            control.commit_operation(self.repo, self.item, **args)
        self.assertEqual(log_path.read_bytes(), before)
        self.assertEqual(self.target.read_bytes(), b"before\n")

        log_path.unlink()
        with mock.patch.object(
                control, "_after_active",
                side_effect=RuntimeError("simulated crash")):
            with self.assertRaises(RuntimeError):
                control.commit_operation(self.repo, self.item, **args)
        intent = next((self.item_dir / "control/operations").glob(
            "*/intent.json"))
        raw = json.loads(intent.read_text(encoding="utf-8"))
        raw["unexpected"] = True
        intent.write_text(json.dumps(raw), encoding="utf-8")
        corrupted = intent.read_bytes()
        with self.assertRaises(control.ControlRefusal):
            control.recover_pending(self.repo, self.item)
        self.assertEqual(intent.read_bytes(), corrupted)

    def test_all_control_namespace_components_reject_symlinks(self):
        attacks = ("control", "tickets", "operations")
        for component in attacks:
            with self.subTest(component=component):
                with tempfile.TemporaryDirectory() as outside_raw:
                    outside = Path(outside_raw)
                    control_dir = self.item_dir / "control"
                    if control_dir.exists():
                        for child in sorted(control_dir.rglob("*"), reverse=True):
                            if child.is_file() or child.is_symlink():
                                child.unlink()
                            else:
                                child.rmdir()
                        control_dir.rmdir()
                    if component == "control":
                        control_dir.symlink_to(outside, target_is_directory=True)
                    else:
                        control_dir.mkdir()
                        (control_dir / component).symlink_to(
                            outside, target_is_directory=True)
                    with self.assertRaises(control.ControlError):
                        if component == "tickets":
                            claim = ownership.acquire(self.repo, self.item)
                            try:
                                control.issue_ticket(
                                    self.repo, self.item, kind="x", key="y",
                                    owner_token=claim.token,
                                    config=config_state.capture(self.repo),
                                    inputs=(), metadata={})
                            finally:
                                claim.release()
                        else:
                            control.commit_operation(
                                self.repo, self.item,
                                kind="x", key="y", request={})
                    self.assertEqual(list(outside.iterdir()), [])
                    if component == "control":
                        control_dir.unlink()
                    else:
                        (control_dir / component).unlink()
                        control_dir.rmdir()


class SharedLockAndSchemaTest(ControlFixture):
    def test_legacy_append_enforces_shared_limit_without_staging(self):
        log_path = self.item_dir / "log.jsonl"
        old = b'{"event": "old", "ts": "durable"}\n'
        fixed_now = "2026-09-09T15:02:00Z"
        entry = {"event": "ordinary.event", "ts": fixed_now}
        payload = (
            json.dumps(entry, sort_keys=True, allow_nan=False) + "\n"
        ).encode("utf-8")
        limit = len(old) + len(payload)
        log_path.write_bytes(old)
        old_identity = log_path.stat().st_ino

        with (mock.patch.dict(os.environ, {"FACTORY_NOW": fixed_now}),
              mock.patch.object(
                  control, "_LOG_IMAGE_LIMIT", limit - 1, create=True),
              self.assertRaisesRegex(
                  control.ControlRefusal,
                  "item log image exceeds its read limit")):
            logs.append_event(self.repo, self.item, "ordinary.event")

        self.assertEqual(log_path.read_bytes(), old)
        self.assertEqual(log_path.stat().st_ino, old_identity)
        self.assertEqual(list(self.item_dir.glob(".log.jsonl.tmp-*")), [])

        with (mock.patch.dict(os.environ, {"FACTORY_NOW": fixed_now}),
              mock.patch.object(
                  control, "_LOG_IMAGE_LIMIT", limit, create=True)):
            appended = logs.append_event(
                self.repo, self.item, "ordinary.event")
            with control.item_lock(self.repo, self.item) as lock:
                parsed = control._strict_log(lock)

        self.assertEqual(appended, entry)
        self.assertEqual(log_path.read_bytes(), old + payload)
        self.assertEqual(len(log_path.read_bytes()), limit)
        self.assertEqual(parsed, [json.loads(old), entry])
        self.assertEqual(list(self.item_dir.glob(".log.jsonl.tmp-*")), [])

    def test_legacy_append_cannot_consume_active_recovery_capacity(self):
        args = dict(
            kind="test.log-reservation", key="partial-events", request={},
            prerequisites=(), replacements=(),
            events=(
                {
                    "event": "control.first-event",
                    "ts": "2026-09-09T16:10:00Z",
                    "data": {"step": 1},
                },
                {
                    "event": "control.second-event",
                    "ts": "2026-09-09T16:10:01Z",
                    "data": {"padding": "x" * 128, "step": 2},
                },
            ),
        )
        intent, _intent_bytes, _blobs = control._build_intent(
            self.repo, self.item, **args)
        event_lines = [logs._entry_bytes(event) for event in intent["events"]]
        limit = sum(len(line) for line in event_lines)

        def crash_after_first(index):
            if index == 0:
                raise RuntimeError("simulated partial-event crash")

        with (mock.patch.object(control, "_LOG_IMAGE_LIMIT", limit),
              mock.patch.object(
                  control, "_after_event", side_effect=crash_after_first),
              self.assertRaisesRegex(RuntimeError, "partial-event crash")):
            control.commit_operation(self.repo, self.item, **args)

        log_path = self.item_dir / "log.jsonl"
        active_path = self.item_dir / "control/active.json"
        partial_bytes = log_path.read_bytes()
        partial_identity = log_path.stat().st_ino
        active_bytes = active_path.read_bytes()
        active_identity = active_path.stat().st_ino
        self.assertEqual(partial_bytes, event_lines[0])

        with (mock.patch.object(control, "_LOG_IMAGE_LIMIT", limit),
              mock.patch.dict(
                  os.environ, {"FACTORY_NOW": "2026-09-09T16:10:02Z"}),
              self.assertRaisesRegex(
                  control.ControlRefusal, "pending recovery|active operation")):
            logs.append_event(self.repo, self.item, "ordinary.event")

        self.assertEqual(log_path.read_bytes(), partial_bytes)
        self.assertEqual(log_path.stat().st_ino, partial_identity)
        self.assertEqual(active_path.read_bytes(), active_bytes)
        self.assertEqual(active_path.stat().st_ino, active_identity)
        self.assertEqual(list(self.item_dir.glob(".log.jsonl.tmp-*")), [])

        with mock.patch.object(control, "_LOG_IMAGE_LIMIT", limit):
            recovered = control.recover_pending(self.repo, self.item)
            retried = control.commit_operation(self.repo, self.item, **args)

        self.assertTrue(recovered.recovered)
        self.assertEqual(retried, recovered.receipt)
        self.assertEqual(log_path.read_bytes(), b"".join(event_lines))
        self.assertFalse(active_path.exists())

        no_active_before = log_path.read_bytes()
        appended = logs.append_event(
            self.repo, self.item, "ordinary.after-recovery")
        self.assertEqual(
            log_path.read_bytes(),
            no_active_before + logs._entry_bytes(appended))

    def test_item_lock_early_refusals_close_every_acquired_fd_once(self):
        real_append = safeio._append_directory
        real_validate = safeio._validate_chain
        real_close = os.close

        for failure in ("append", "validate"):
            for attempt in range(3):
                with self.subTest(failure=failure, attempt=attempt):
                    acquired = []
                    closed = []

                    def append_then_refuse(chain, name):
                        real_append(chain, name)
                        if failure == "append" and name == ".factory":
                            acquired.extend(handle.fd for handle in chain)
                            raise safeio.SafeIOError(
                                "simulated append refusal")

                    def validate_then_refuse(chain):
                        real_validate(chain)
                        if (failure == "validate" and chain and
                                chain[-1].entry_name == self.item):
                            acquired.extend(handle.fd for handle in chain)
                            raise safeio.SafeIOError(
                                "simulated validation refusal")

                    def record_close(fd):
                        closed.append(fd)
                        return real_close(fd)

                    with (mock.patch.object(
                            safeio, "_append_directory",
                            side_effect=append_then_refuse),
                          mock.patch.object(
                              safeio, "_validate_chain",
                              side_effect=validate_then_refuse),
                          mock.patch.object(
                              control.os, "close", side_effect=record_close),
                          self.assertRaisesRegex(
                              control.ControlError,
                              "cannot safely open item namespace")):
                        with control.item_lock(self.repo, self.item):
                            self.fail("item lock unexpectedly acquired")

                    self.assertTrue(acquired)
                    for fd in acquired:
                        self.assertEqual(closed.count(fd), 1)
                        with self.assertRaises(OSError):
                            os.fstat(fd)

    def test_item_lock_refuses_detached_item_before_creating_lock(self):
        detached = self.item_dir.with_name(f"{self.item}-detached")
        observed = {"lock_fds": []}
        real_open_root_chain = safeio._open_root_chain
        real_open_directory = control._open_directory
        real_open_lock_file = control._open_lock_file

        def record_root_chain(root):
            chain = real_open_root_chain(root)
            observed["chain"] = chain
            return chain

        def detach_after_control_sync(parent_fd, name, *, create=False):
            fd = real_open_directory(parent_fd, name, create=create)
            if name == "control":
                observed["control_fd"] = fd
                self.item_dir.rename(detached)
                shutil.copytree(detached, self.item_dir)
            return fd

        def record_lock_open(control_fd):
            fd, identity = real_open_lock_file(control_fd)
            observed["lock_fds"].append(fd)
            return fd, identity

        with (mock.patch.object(
                safeio, "_open_root_chain", side_effect=record_root_chain),
              mock.patch.object(
                  control, "_open_directory",
                  side_effect=detach_after_control_sync),
              mock.patch.object(
                  control, "_open_lock_file", side_effect=record_lock_open),
              self.assertRaises((control.ControlError, safeio.SafeIOError))):
            with control.item_lock(self.repo, self.item):
                self.fail("detached item lock unexpectedly acquired")

        self.assertEqual(observed["lock_fds"], [])
        self.assertFalse((detached / "control/lock").exists())
        self.assertFalse((self.item_dir / "control/lock").exists())
        acquired = [handle.fd for handle in observed["chain"]]
        acquired.append(observed["control_fd"])
        acquired.extend(observed["lock_fds"])
        for fd in acquired:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_legacy_append_waits_for_item_lock_and_installs_exact_full_image(self):
        entered = threading.Event()
        finished = threading.Event()

        def append():
            entered.set()
            logs.append_event(self.repo, self.item, "ordinary.event", {"x": 1})
            finished.set()

        with control.item_lock(self.repo, self.item):
            thread = threading.Thread(target=append)
            thread.start()
            self.assertTrue(entered.wait(2))
            self.assertFalse(finished.wait(0.05))
        thread.join(2)
        self.assertTrue(finished.is_set())

        log_path = self.item_dir / "log.jsonl"
        old = b'{"event": "old", "ts": "earlier", "verbatim": true}\n'
        log_path.write_bytes(old)
        old_identity = log_path.stat().st_ino
        with mock.patch.object(
                logs.os, "fsync", wraps=logs.os.fsync) as fsync:
            entry = logs.append_event(
                self.repo, self.item, "ordinary.event", {"x": 1})
        expected = (json.dumps(entry, sort_keys=True) + "\n").encode("utf-8")
        self.assertEqual(log_path.read_bytes(), old + expected)
        self.assertNotEqual(log_path.stat().st_ino, old_identity)
        self.assertGreaterEqual(fsync.call_count, 1)

    def test_append_write_and_restore_failure_cannot_destroy_old_bytes(self):
        log_path = self.item_dir / "log.jsonl"
        old = b'{"event": "old", "ts": "durable", "padding": "exact"}\n'
        log_path.write_bytes(old)
        # Create the cooperative lock namespace before faulting only the log
        # publication writes.
        with control.item_lock(self.repo, self.item):
            pass
        real_write = logs.os.write
        calls = 0

        def partial_then_fail(fd, data):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_write(fd, bytes(data[:1]))
            raise OSError("injected second write failure")

        with (mock.patch.object(
                logs.os, "write", side_effect=partial_then_fail),
              mock.patch.object(
                  logs.os, "ftruncate", wraps=logs.os.ftruncate) as truncate,
              self.assertRaises(control.ControlError)):
            logs.append_event(self.repo, self.item, "ordinary.event")

        self.assertEqual(log_path.read_bytes(), old)
        self.assertEqual(truncate.call_count, 0)

    def test_log_publication_io_failures_never_remove_old_history(self):
        log_path = self.item_dir / "log.jsonl"
        old = b'{"event": "old", "ts": "durable", "spacing": true}\n'
        fixed_now = "2026-09-09T13:00:00Z"
        cases = (
            ("_write_log_image", False),
            ("_sync_log_staging", False),
            ("_install_log_image", False),
            ("_sync_log_directory", True),
        )
        for seam, installed in cases:
            with self.subTest(seam=seam):
                log_path.write_bytes(old)
                with (mock.patch.dict(
                        os.environ, {"FACTORY_NOW": fixed_now}),
                      mock.patch.object(
                          logs, seam, side_effect=OSError("injected I/O"),
                          create=True),
                      self.assertRaises(control.ControlError)):
                    logs.append_event(
                        self.repo, self.item, "ordinary.event", {"x": 1})
                entry = {
                    "event": "ordinary.event",
                    "ts": fixed_now,
                    "data": {"x": 1},
                }
                appended = (
                    json.dumps(entry, sort_keys=True) + "\n").encode("utf-8")
                self.assertEqual(
                    log_path.read_bytes(), old + appended if installed else old)

    def test_log_install_revalidates_old_namespace_after_test_seam(self):
        log_path = self.item_dir / "log.jsonl"
        detached = self.item_dir / "detached-log.jsonl"
        outside = self.item_dir / "outside.jsonl"
        old = b'{"event": "old", "ts": "durable"}\n'
        outside_bytes = b'{"event": "outside", "ts": "untouched"}\n'
        log_path.write_bytes(old)
        outside.write_bytes(outside_bytes)

        def substitute_namespace(*_args):
            log_path.rename(detached)
            log_path.symlink_to(outside)

        with (mock.patch.object(
                logs, "_before_log_install",
                side_effect=substitute_namespace, create=True),
              self.assertRaises(control.ControlError)):
            logs.append_event(self.repo, self.item, "ordinary.event")

        self.assertTrue(log_path.is_symlink())
        self.assertEqual(detached.read_bytes(), old)
        self.assertEqual(outside.read_bytes(), outside_bytes)

    def test_process_death_at_each_log_publication_boundary_recovers_once(self):
        old = b'{"event": "old", "ts": "durable", "bytes": "exact"}\n'
        cases = (
            ("_after_log_staging_write", 141, False),
            ("_after_log_staging_sync", 142, False),
            ("_before_log_install", 143, False),
            ("_after_log_install", 144, True),
            ("_after_log_directory_sync", 145, True),
        )
        for hook, returncode, installed in cases:
            with self.subTest(hook=hook):
                self._reset_operation_fixture()
                log_path = self.item_dir / "log.jsonl"
                log_path.write_bytes(old)
                crashed = self._subprocess(f'''
import os
import sys
from scripts.factory.lib import control, logs
setattr(logs, {hook!r}, lambda *_args: os._exit({returncode}))
control.commit_operation(
    sys.argv[1], sys.argv[2], kind="test.log-exit", key={hook!r},
    request={{"hook": {hook!r}}},
    events=({{"event": "control.log-boundary",
             "ts": "2026-09-09T14:00:00Z",
             "data": {{"hook": {hook!r}}}}},))
''')
                self.assertEqual(crashed.returncode, returncode, crashed.stderr)
                active = json.loads(
                    (self.item_dir / "control/active.json").read_text())
                operation = (self.item_dir / "control/operations" /
                             active["operation_id"])
                intent = json.loads(
                    (operation / "intent.json").read_text(encoding="utf-8"))
                event_bytes = (json.dumps(
                    intent["events"][0], sort_keys=True) + "\n").encode("utf-8")
                self.assertEqual(
                    log_path.read_bytes(),
                    old + event_bytes if installed else old)

                recovered = self._subprocess('''
import sys
from scripts.factory.lib import control
assert control.recover_pending(sys.argv[1], sys.argv[2]).recovered
''')
                self.assertEqual(recovered.returncode, 0, recovered.stderr)
                self.assertEqual(log_path.read_bytes(), old + event_bytes)
                matching = [
                    event for event in logs.read_events(self.repo, self.item)
                    if event.get("operation_id") == active["operation_id"]
                ]
                self.assertEqual(len(matching), 1)
                self.assertFalse(
                    (self.item_dir / "control/active.json").exists())

    def test_control_schemas_are_closed_and_accept_written_artifacts(self):
        claim = ownership.acquire(self.repo, self.item)
        try:
            ticket = control.issue_ticket(
                self.repo, self.item, kind="plan.dispatch", key="round-1",
                owner_token=claim.token, config=config_state.capture(self.repo),
                inputs=(), metadata={})
            manifest = json.loads(ticket.manifest.file.data)
            schema = initrepo.load_schema("control-ticket")
            self.assertEqual(validate(manifest, schema, "ticket"), [])
            self.assertFalse(schema["additionalProperties"])
            self.assertTrue(validate({**manifest, "extra": True},
                                     schema, "ticket"))
        finally:
            claim.release()

        receipt = control.commit_operation(
            self.repo, self.item, kind="schema", key="one", request={})
        operation = self.item_dir / "control/operations" / receipt.operation_id
        pairs = (("control-intent", "intent.json"),
                 ("control-commit", "commit.json"))
        for schema_name, filename in pairs:
            value = json.loads((operation / filename).read_text(encoding="utf-8"))
            schema = initrepo.load_schema(schema_name)
            self.assertEqual(validate(value, schema, filename), [])
            self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
