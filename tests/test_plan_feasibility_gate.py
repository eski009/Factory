import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory
from unittest import mock

from scripts.factory.lib import (config_state, control, feasibility, initrepo,
                                 items, logs, machine, ownership, work)


ITEM = "0001-feature"


def acceptance(spec, plan):
    return {
        "version": 1,
        "item": ITEM,
        "spec_sha256": hashlib.sha256(spec).hexdigest(),
        "plan_structure_sha256": feasibility.plan_structure_sha256(plan),
        "revision": {
            "reason": "Initial complete contract",
            "changed_sections": ["initial"],
        },
        "resume_cursor": {"strategy": "first-unchecked-task"},
        "participants": [{"item": ITEM, "owned_paths": ["src"]}],
        "dependencies": [],
        "resources": [{
            "id": "code", "kind": "path", "value": "src/feature.py",
            "access": "modify", "provider": ITEM,
            "availability": "available",
        }],
        "interfaces": [],
        "criteria": [{
            "id": "AC-1", "statement": "Feature works",
            "requires": ["code"], "tests": ["unit"],
        }],
        "tests": [{
            "id": "unit", "purpose": "component",
            "command": ["python3", "-m", "unittest"],
            "covers": ["code"],
        }],
        "delivery": {
            "mode": "solo", "participants": [ITEM],
            "merge_order": [ITEM], "shared_gates": [],
        },
        "out_of_scope": ["device proof"],
    }


def tree_bytes(repo):
    result = {}
    for path in sorted(repo.rglob("*")):
        relative = str(path.relative_to(repo))
        if path.is_symlink():
            result[relative] = ("symlink", os.readlink(path))
        elif path.is_file():
            result[relative] = ("file", path.read_bytes())
        elif path.is_dir():
            result[relative] = ("dir", None)
    return result


class PlanFeasibilityGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-09-09T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def set_gate(self, enabled=True):
        path = self.repo / ".factory/config.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["gates"] = ["feasibility"] if enabled else ["design"]
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")

    def write_item(self, stage="plan", *, plan=None, sidecar=True,
                   paused_from=None):
        spec = b"Acceptance.\n"
        plan = b"# Plan\n- [ ] Implement it\n" if plan is None else plan
        meta = {
            "id": ITEM, "title": "Feature", "stage": stage,
            "kind": "backend", "created": "2026-09-09T10:00:00Z",
            "updated": "2026-09-09T10:00:00Z",
        }
        if paused_from:
            meta["paused-from"] = paused_from
            meta["paused-reason"] = "interrupted"
        items.save_item(self.repo, meta, "Fixture.")
        directory = self.repo / ".factory/items" / ITEM
        (directory / "spec.md").write_bytes(spec)
        (directory / "plan.md").write_bytes(plan)
        if sidecar:
            (directory / "acceptance.json").write_text(
                json.dumps(acceptance(spec, plan), indent=2, sort_keys=True) +
                "\n", encoding="utf-8")
        return directory

    def run_cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = factory.main(["--repo", str(self.repo), *args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_enabled_entry_uses_one_transaction_for_all_legal_sources(self):
        for source, paused in (
                ("plan", None), ("review", None), ("verify", None),
                ("assure", None), ("waiting-human", "implement")):
            with self.subTest(source=source):
                with tempfile.TemporaryDirectory() as directory:
                    old_repo = self.repo
                    self.repo = Path(directory)
                    try:
                        initrepo.init(self.repo)
                        self.set_gate()
                        self.write_item(source, paused_from=paused)
                        meta, verdict = machine.advance(
                            self.repo, ITEM, "implement")
                        self.assertEqual(meta["stage"], "implement")
                        self.assertFalse(verdict["fired"])
                        events = logs.read_events(self.repo, ITEM)
                        self.assertEqual(events[-1]["event"], "stage.advance")
                        self.assertEqual(
                            events[-1]["data"],
                            {"from": source, "to": "implement"})
                        operations = (self.repo / ".factory/items" / ITEM /
                                      "control/operations")
                        self.assertEqual(
                            len(list(operations.glob("*/commit.json"))), 1)
                    finally:
                        self.repo = old_repo

    def test_enabled_entry_uses_current_time_and_unique_resume_episodes(self):
        self.set_gate()
        self.write_item("waiting-human", paused_from="implement")
        for index in range(3):
            meta, _verdict = machine.advance(
                self.repo, ITEM, "implement")
            self.assertEqual(meta["updated"], "2026-09-09T12:00:00Z")
            self.assertEqual(
                logs.read_events(self.repo, ITEM)[-1]["ts"],
                "2026-09-09T12:00:00Z")
            if index < 2:
                machine.advance(
                    self.repo, ITEM, "waiting-human",
                    reason="interrupted")
        operations = (self.repo / ".factory/items" / ITEM /
                      "control/operations")
        self.assertEqual(len(list(operations.glob("*/commit.json"))), 3)

    def test_enabled_entry_reuses_persisted_time_after_intent_crash(self):
        self.set_gate()
        self.write_item("plan")
        with (mock.patch.object(
                control, "_after_intent",
                side_effect=RuntimeError("simulated crash")),
              self.assertRaisesRegex(RuntimeError, "simulated crash")):
            machine.advance(self.repo, ITEM, "implement")
        self.assertEqual(
            items.load_item(self.repo, ITEM)[0]["stage"], "plan")

        os.environ["FACTORY_NOW"] = "2026-09-09T13:00:00Z"
        meta, _verdict = machine.advance(self.repo, ITEM, "implement")
        self.assertEqual(meta["updated"], "2026-09-09T12:00:00Z")
        operations = (self.repo / ".factory/items" / ITEM /
                      "control/operations")
        self.assertEqual(len(list(operations.glob("*/commit.json"))), 1)

    def test_enabled_completed_or_invalid_contract_refuses_without_mutation(self):
        self.set_gate()
        complete = b"# Plan\n- [x] complete\n"
        directory = self.write_item(plan=complete)
        before = tree_bytes(self.repo)
        with self.assertRaisesRegex(machine.GateError, "unchecked task"):
            machine.advance(self.repo, ITEM, "implement")
        self.assertEqual(tree_bytes(self.repo), before)
        self.assertFalse((directory / "control/operations").exists())

        value = json.loads((directory / "acceptance.json").read_text())
        value["resources"][0]["availability"] = "unavailable"
        (directory / "acceptance.json").write_text(json.dumps(value))
        before = tree_bytes(self.repo)
        with self.assertRaisesRegex(machine.GateError, "unavailable"):
            machine.advance(self.repo, ITEM, "implement")
        self.assertEqual(tree_bytes(self.repo), before)

    def test_malformed_config_refuses_implementation_without_mutation(self):
        directory = self.write_item(sidecar=False)
        (self.repo / ".factory/config.json").write_bytes(b"{")
        before = tree_bytes(self.repo)
        with self.assertRaisesRegex(machine.GateError, "invalid Factory configuration"):
            machine.advance(self.repo, ITEM, "implement")
        self.assertEqual(tree_bytes(self.repo), before)
        self.assertFalse((directory / "control/operations").exists())

    def test_valid_disabled_transition_retains_legacy_files_and_events(self):
        self.set_gate(False)
        directory = self.write_item(sidecar=False)
        machine.advance(self.repo, ITEM, "implement")
        self.assertEqual(items.load_item(self.repo, ITEM)[0]["stage"], "implement")
        self.assertFalse((directory / "control/operations").exists())
        event = logs.read_events(self.repo, ITEM)[-1]
        self.assertEqual(event["event"], "stage.advance")
        self.assertNotIn("operation_id", event)

    def test_plan_check_pass_disabled_failure_and_json_are_read_only(self):
        self.set_gate()
        directory = self.write_item()
        before = tree_bytes(self.repo)
        code, output, error = self.run_cli("plan-check", ITEM, "--json")
        self.assertEqual((code, error), (0, ""))
        report = json.loads(output)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["cursor"], "Implement it")
        self.assertEqual(tree_bytes(self.repo), before)

        self.set_gate(False)
        code, output, error = self.run_cli("plan-check", ITEM)
        self.assertEqual((code, error), (0, ""))
        self.assertIn("feasibility disabled", output)

        self.set_gate()
        value = json.loads((directory / "acceptance.json").read_text())
        value["spec_sha256"] = "0" * 64
        (directory / "acceptance.json").write_text(json.dumps(value))
        before = tree_bytes(self.repo)
        code, output, error = self.run_cli("plan-check", ITEM)
        self.assertEqual((code, output), (2, ""))
        self.assertIn("spec_sha256", error)
        self.assertEqual(tree_bytes(self.repo), before)

    def test_plan_check_hostile_config_artifact_and_non_repo_fail_cleanly(self):
        self.set_gate()
        directory = self.write_item()
        acceptance_path = directory / "acceptance.json"
        acceptance_path.unlink()
        acceptance_path.symlink_to(self.repo / "outside")
        code, output, error = self.run_cli("plan-check", ITEM, "--json")
        self.assertEqual((code, error), (2, ""))
        self.assertEqual(json.loads(output)["status"], "fail")

        config = self.repo / ".factory/config.json"
        config.unlink()
        config.symlink_to(self.repo / "outside")
        code, output, error = self.run_cli("plan-check", ITEM, "--json")
        self.assertEqual((code, error), (2, ""))
        self.assertEqual(json.loads(output)["status"], "fail")

        with tempfile.TemporaryDirectory() as directory:
            old_repo = self.repo
            self.repo = Path(directory)
            try:
                code, output, error = self.run_cli("plan-check", ITEM)
                self.assertEqual((code, output), (2, ""))
                self.assertIn("not a factory repo", error)
            finally:
                self.repo = old_repo

    def test_plan_dispatch_disabled_is_a_structured_refusal(self):
        self.set_gate(False)
        self.write_item(stage="implement")
        code, output, error = self.run_cli(
            "plan-dispatch", ITEM, "--json")
        self.assertEqual((code, error), (2, ""))
        report = json.loads(output)
        self.assertEqual(report["status"], "fail")
        self.assertIn("disabled", report["error"])

    def test_validate_tree_checks_present_and_required_acceptance(self):
        self.set_gate(False)
        self.write_item(stage="idea")
        logs.append_event(
            self.repo, ITEM, "stage.advance", {"from": "idea", "to": "idea"})
        self.assertEqual(initrepo.validate_tree(self.repo), [])

        sidecar = self.repo / ".factory/items" / ITEM / "acceptance.json"
        value = json.loads(sidecar.read_text())
        value["unexpected"] = True
        sidecar.write_text(json.dumps(value))
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("unexpected" in error for error in errors), errors)

        sidecar.unlink()
        self.set_gate()
        meta, body = items.load_item(self.repo, ITEM)
        meta["stage"] = "plan"
        items.save_item(self.repo, meta, body)
        log = self.repo / ".factory/items" / ITEM / "log.jsonl"
        log.write_text("", encoding="utf-8")
        logs.append_event(
            self.repo, ITEM, "stage.advance", {"from": "idea", "to": "plan"})
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("acceptance.json: required" in error
                            for error in errors), errors)


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True,
        capture_output=True, text=True)


class DispatchAndScopeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name).resolve()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@example.test")
        git(self.repo, "config", "user.name", "Feasibility Test")
        (self.repo / ".gitignore").write_text(".factory/\n", encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src/base.txt").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", ".gitignore", "src/base.txt")
        git(self.repo, "commit", "-q", "-m", "seed")
        git(self.repo, "checkout", "-q", "-b", f"factory/{ITEM}")
        initrepo.init(self.repo)
        git(self.repo, "add", "docs/factory")
        git(self.repo, "commit", "-q", "-m", "factory docs")
        config_path = self.repo / ".factory/config.json"
        config = json.loads(config_path.read_text())
        config["gates"] = ["feasibility"]
        config_path.write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        spec = b"Acceptance.\n"
        self.plan = b"# Plan\n- [ ] first task\n- [ ] second task\n"
        items.save_item(self.repo, {
            "id": ITEM, "title": "Feature", "stage": "implement",
            "kind": "backend", "created": "2026-09-09T10:00:00Z",
            "updated": "2026-09-09T10:00:00Z",
        }, "Fixture.")
        self.item_dir = self.repo / ".factory/items" / ITEM
        (self.item_dir / "spec.md").write_bytes(spec)
        (self.item_dir / "plan.md").write_bytes(self.plan)
        (self.item_dir / "acceptance.json").write_text(
            json.dumps(acceptance(spec, self.plan), indent=2,
                       sort_keys=True) + "\n", encoding="utf-8")
        self.claim = ownership.acquire(self.repo, ITEM)

    def tearDown(self):
        os.environ.pop("FACTORY_WORK_STUB", None)
        os.environ.pop("FACTORY_IMPLEMENTATION_OWNER", None)
        try:
            self.claim.release()
        except ownership.OwnershipError:
            pass
        self.tmp.cleanup()

    def dispatch(self, tasks=None):
        return feasibility.prepare_dispatch(
            self.repo, ITEM, config=config_state.capture(self.repo),
            owner_token=self.claim.token, tasks=tasks)

    def commit_path(self, path="src/feature.py", content="change\n"):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        git(self.repo, "add", "--", path)
        git(self.repo, "commit", "-q", "-m", f"change {path}")

    def write_result(self, dispatch):
        ticket_id = (dispatch if isinstance(dispatch, str)
                     else dispatch.ticket.ticket_id)
        worker = self.item_dir / "worker"
        worker.mkdir(exist_ok=True)
        (worker / "result.json").write_text(json.dumps({
            "id": ITEM, "status": "done", "backend": "stub",
            "branch": f"factory/{ITEM}",
            "dispatch_ticket": ticket_id,
        }), encoding="utf-8")

    def test_dispatch_ticket_binds_head_tasks_and_owner_limited_handoff(self):
        dispatch = self.dispatch(tasks=1)
        self.assertEqual(dispatch.tasks, ("first task",))
        self.assertEqual(dispatch.ticket.metadata["head"],
                         git(self.repo, "rev-parse", "HEAD").stdout.strip())
        self.assertEqual(dispatch.ticket.metadata["selected"], [0])
        payload = json.loads(dispatch.handoff)
        self.assertEqual(payload["owned_paths"], ["src"])
        self.assertNotIn(self.claim.token, dispatch.handoff)
        loaded = control.load_ticket(
            self.repo, ITEM, dispatch.ticket.ticket_id,
            owner_token=self.claim.token)
        self.assertEqual(loaded.metadata, dispatch.ticket.metadata)

    def test_new_ownership_generation_can_retry_unchanged_dispatch(self):
        first = self.dispatch(tasks=1)
        self.claim.release()
        self.claim = ownership.acquire(self.repo, ITEM)
        second = self.dispatch(tasks=1)
        self.assertNotEqual(
            first.ticket.owner_sha256, second.ticket.owner_sha256)
        self.assertNotEqual(first.ticket.ticket_id, second.ticket.ticket_id)

    def test_missing_owned_tail_is_allowed_but_symlink_is_rejected(self):
        contract_path = self.item_dir / "acceptance.json"
        value = json.loads(contract_path.read_text())
        value["participants"][0]["owned_paths"] = ["new/deep"]
        value["resources"][0]["value"] = "new/deep/feature.py"
        contract_path.write_text(json.dumps(value), encoding="utf-8")
        self.assertIsNotNone(self.dispatch().ticket)

        self.claim.release()
        self.claim = ownership.acquire(self.repo, ITEM)
        (self.repo / "owned").symlink_to("src")
        git(self.repo, "add", "owned")
        git(self.repo, "commit", "-q", "-m", "tracked symlink")
        value["participants"][0]["owned_paths"] = ["owned"]
        value["resources"][0]["value"] = "owned/feature.py"
        contract_path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(feasibility.FeasibilityError, "unsafe"):
            self.dispatch()

    def test_scope_passes_in_scope_commit_and_records_all_paths(self):
        dispatch = self.dispatch()
        self.commit_path()
        report = feasibility.inspect_worker_scope(dispatch.ticket)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["paths"], ["src/feature.py"])

    def test_scope_uses_sealed_manifest_not_mutable_ticket_metadata(self):
        dispatch = self.dispatch()
        dispatch.ticket.metadata["head"] = "0" * 40
        dispatch.ticket.metadata["owned_paths"] = ["outside"]
        self.commit_path()
        report = feasibility.inspect_worker_scope(dispatch.ticket)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["baseline_head"], dispatch.head)

    def test_committed_then_reverted_escape_is_still_a_scope_violation(self):
        dispatch = self.dispatch()
        self.commit_path("outside.txt")
        (self.repo / "outside.txt").unlink()
        git(self.repo, "add", "--", "outside.txt")
        git(self.repo, "commit", "-q", "-m", "revert outside")
        report = feasibility.inspect_worker_scope(dispatch.ticket)
        self.assertEqual(report["reason"], "scope_violation")
        self.assertEqual(report["violations"], ["outside.txt"])

    def test_rename_checks_both_old_and_new_paths(self):
        (self.repo / "outside.txt").write_text("outside\n", encoding="utf-8")
        git(self.repo, "add", "outside.txt")
        git(self.repo, "commit", "-q", "-m", "outside baseline")
        dispatch = self.dispatch()
        git(self.repo, "mv", "outside.txt", "src/renamed.txt")
        git(self.repo, "commit", "-q", "-m", "rename into scope")
        report = feasibility.inspect_worker_scope(dispatch.ticket)
        self.assertEqual(report["reason"], "scope_violation")
        self.assertIn("outside.txt", report["violations"])
        self.assertIn("src/renamed.txt", report["paths"])

    def test_copy_checks_both_unchanged_source_and_new_path(self):
        (self.repo / "outside.txt").write_text("outside\n", encoding="utf-8")
        git(self.repo, "add", "outside.txt")
        git(self.repo, "commit", "-q", "-m", "outside baseline")
        dispatch = self.dispatch()
        (self.repo / "src/copied.txt").write_bytes(
            (self.repo / "outside.txt").read_bytes())
        git(self.repo, "add", "src/copied.txt")
        git(self.repo, "commit", "-q", "-m", "copy into scope")
        report = feasibility.inspect_worker_scope(dispatch.ticket)
        self.assertEqual(report["reason"], "scope_violation")
        self.assertIn("outside.txt", report["violations"])
        self.assertIn("src/copied.txt", report["paths"])

    def test_dirty_index_worktree_and_untracked_states_fail(self):
        mutations = {
            "index": lambda: (
                (self.repo / "src/index.txt").write_text("x\n"),
                git(self.repo, "add", "src/index.txt")),
            "worktree": lambda: (self.repo / "src/base.txt").write_text(
                "dirty\n"),
            "untracked": lambda: (self.repo / "src/new.txt").write_text(
                "new\n"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                dispatch = self.dispatch()
                mutate()
                report = feasibility.inspect_worker_scope(dispatch.ticket)
                self.assertEqual(report["reason"], "dirty_checkout")
                git(self.repo, "reset", "-q", "--hard", "HEAD")
                (self.repo / "src/new.txt").unlink(missing_ok=True)

    def test_history_rewrite_and_git_failure_are_distinct(self):
        dispatch = self.dispatch()
        tree = git(self.repo, "write-tree").stdout.strip()
        rewritten = subprocess.run(
            ["git", "commit-tree", tree, "-m", "rewritten"], cwd=self.repo,
            check=True, capture_output=True, text=True).stdout.strip()
        git(self.repo, "reset", "-q", "--hard", rewritten)
        self.assertEqual(
            feasibility.inspect_worker_scope(dispatch.ticket)["reason"],
            "history_rewrite")

        git(self.repo, "reset", "-q", "--hard", dispatch.ticket.metadata["head"])
        with mock.patch.object(
                feasibility, "_git_run",
                side_effect=feasibility.FeasibilityError("simulated Git failure")):
            self.assertEqual(
                feasibility.inspect_worker_scope(dispatch.ticket)["reason"],
                "scope_inspection_failed")

    def test_finalize_ticks_selected_task_without_premature_completion(self):
        dispatch = self.dispatch(tasks=1)
        self.commit_path()
        self.write_result(dispatch)
        result = feasibility.finalize_tasks(
            self.repo, ITEM, ticket_id=dispatch.ticket.ticket_id,
            owner_token=self.claim.token)
        self.assertFalse(result["completed"])
        self.assertEqual(result["cursor"], "second task")
        plan = (self.item_dir / "plan.md").read_text()
        self.assertIn("- [x] first task", plan)
        self.assertIn("- [ ] second task", plan)
        self.assertFalse(any(event["event"] == "implement.completed"
                             for event in logs.read_events(self.repo, ITEM)))

    def test_finalize_all_tasks_is_atomic_and_lost_reply_retry_adopts(self):
        dispatch = self.dispatch()
        self.commit_path()
        self.write_result(dispatch)
        first = feasibility.finalize_tasks(
            self.repo, ITEM, ticket_id=dispatch.ticket.ticket_id,
            owner_token=self.claim.token)
        second = feasibility.finalize_tasks(
            self.repo, ITEM, ticket_id=dispatch.ticket.ticket_id,
            owner_token=self.claim.token)
        self.assertTrue(first["completed"])
        self.assertEqual(second["operation_id"], first["operation_id"])
        completed = [event for event in logs.read_events(self.repo, ITEM)
                     if event["event"] == "implement.completed"]
        self.assertEqual(len(completed), 1)
        self.assertNotIn("- [ ]", (self.item_dir / "plan.md").read_text())

    def test_next_dispatch_cannot_reuse_prior_success_result(self):
        first = self.dispatch(tasks=1)
        self.commit_path()
        self.write_result(first)
        feasibility.finalize_tasks(
            self.repo, ITEM, ticket_id=first.ticket.ticket_id,
            owner_token=self.claim.token)

        second = self.dispatch(tasks=1)
        with self.assertRaisesRegex(
                feasibility.FeasibilityError, "does not match"):
            feasibility.finalize_tasks(
                self.repo, ITEM, ticket_id=second.ticket.ticket_id,
                owner_token=self.claim.token)
        self.assertIn(
            "- [ ] second task", (self.item_dir / "plan.md").read_text())
        self.assertFalse(any(event["event"] == "implement.completed"
                             for event in logs.read_events(self.repo, ITEM)))

    def test_finalize_rejects_malformed_success_result(self):
        dispatch = self.dispatch()
        worker_dir = self.item_dir / "worker"
        worker_dir.mkdir(exist_ok=True)
        (worker_dir / "result.json").write_text(json.dumps({
            "status": "done", "backend": "stub",
        }), encoding="utf-8")
        with self.assertRaisesRegex(
                feasibility.FeasibilityError, "worker/result.json"):
            feasibility.finalize_tasks(
                self.repo, ITEM, ticket_id=dispatch.ticket.ticket_id,
                owner_token=self.claim.token)
        self.assertEqual((self.item_dir / "plan.md").read_bytes(), self.plan)

    def test_post_backend_plan_change_preserves_result_and_suppresses_completion(self):
        dispatch = self.dispatch()
        self.commit_path()
        self.write_result(dispatch)
        plan_path = self.item_dir / "plan.md"
        changed = plan_path.read_bytes() + b"\nchanged\n"
        plan_path.write_bytes(changed)
        with self.assertRaisesRegex(
                feasibility.FeasibilityError, "concurrent_plan_change"):
            feasibility.finalize_tasks(
                self.repo, ITEM, ticket_id=dispatch.ticket.ticket_id,
                owner_token=self.claim.token)
        self.assertEqual(plan_path.read_bytes(), changed)
        self.assertTrue((self.item_dir / "worker/result.json").exists())
        self.assertFalse(any(event["event"] == "implement.completed"
                             for event in logs.read_events(self.repo, ITEM)))

    def test_plan_dispatch_and_finalize_cli_are_owner_authenticated(self):
        os.environ["FACTORY_IMPLEMENTATION_OWNER"] = self.claim.token
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = factory.main([
                "--repo", str(self.repo), "plan-dispatch", ITEM,
                "--task", "1", "--json",
            ])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        dispatched = json.loads(stdout.getvalue())
        self.assertEqual(dispatched["tasks"], ["first task"])
        self.commit_path()
        self.write_result(dispatched["ticket_id"])
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = factory.main([
                "--repo", str(self.repo), "plan-finalize", ITEM,
                "--ticket", dispatched["ticket_id"], "--json",
            ])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        finalized = json.loads(stdout.getvalue())
        self.assertEqual(finalized["cursor"], "second task")

        os.environ["FACTORY_IMPLEMENTATION_OWNER"] = "wrong"
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = factory.main([
                "--repo", str(self.repo), "plan-finalize", ITEM,
                "--ticket", dispatched["ticket_id"], "--json",
            ])
        self.assertEqual((code, stderr.getvalue()), (2, ""))
        self.assertEqual(json.loads(stdout.getvalue())["status"], "fail")

    def test_enabled_run_work_uses_ticket_handoff_scope_and_finalization(self):
        self.claim.release()
        os.environ["FACTORY_WORK_STUB"] = json.dumps({
            "file": "src/worker.py", "content": "implemented\n",
        })
        briefs = []
        real_backend = work.BACKENDS["stub"]

        def capture_brief(brief, *args, **kwargs):
            briefs.append(brief)
            return real_backend(brief, *args, **kwargs)

        with (mock.patch.object(
                work, "_tick_plan",
                side_effect=AssertionError("legacy ticker called")),
              mock.patch.dict(work.BACKENDS, {"stub": capture_brief})):
            code, result = work.run_work(
                self.repo, ITEM, backend="stub")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["status"], "done")
        self.assertRegex(result["dispatch_ticket"], r"^[0-9a-f]{64}$")
        self.assertNotIn("- [ ]", (self.item_dir / "plan.md").read_text())
        completed = [event for event in logs.read_events(self.repo, ITEM)
                     if event["event"] == "implement.completed"]
        self.assertEqual(len(completed), 1)
        self.assertFalse((self.item_dir / "implementation-owner.json").exists())
        self.assertEqual(len(briefs), 1)
        self.assertIn("commit your work", briefs[0])
        self.assertIn('"owned_paths"', briefs[0])
        self.assertIn('"first task"', briefs[0])

    def test_enabled_run_work_scope_refusal_preserves_diagnostics_and_releases(self):
        self.claim.release()
        os.environ["FACTORY_WORK_STUB"] = json.dumps({
            "file": "outside.py", "content": "escaped\n",
        })
        code, result = work.run_work(self.repo, ITEM, backend="stub")
        self.assertEqual(code, 2)
        self.assertEqual(result["reason"], "scope_violation")
        self.assertTrue((self.item_dir / "worker/result.json").exists())
        self.assertFalse(any(event["event"] == "implement.completed"
                             for event in logs.read_events(self.repo, ITEM)))
        self.assertIn("- [ ]", (self.item_dir / "plan.md").read_text())
        self.assertFalse((self.item_dir / "implementation-owner.json").exists())

    def test_enabled_run_work_prelaunch_change_launches_nothing_and_releases(self):
        self.claim.release()
        backend_calls = 0
        real_backend = work.BACKENDS["stub"]
        real_revalidate = control.revalidate_ticket
        validations = 0

        def count_backend(*args, **kwargs):
            nonlocal backend_calls
            backend_calls += 1
            return real_backend(*args, **kwargs)

        def replace_before_launch(ticket):
            nonlocal validations
            validations += 1
            result = real_revalidate(ticket)
            # load_ticket is validation 1; _run_owned_work's initial boundary
            # is validation 2. Change after it so the immediate pre-launch
            # boundary detects the replacement.
            if validations == 2:
                plan = self.item_dir / "plan.md"
                plan.write_bytes(plan.read_bytes() + b"changed\n")
            return result

        with (mock.patch.dict(work.BACKENDS, {"stub": count_backend}),
              mock.patch.object(control, "revalidate_ticket",
                                side_effect=replace_before_launch)):
            code, result = work.run_work(self.repo, ITEM, backend="stub")
        self.assertEqual(code, 2, result)
        self.assertEqual(result["reason"], "concurrent_plan_change")
        self.assertEqual(backend_calls, 0)
        self.assertFalse((self.item_dir / "worker").exists())
        self.assertFalse((self.item_dir / "implementation-owner.json").exists())

    def test_real_backend_attempt_is_created_only_after_both_launch_checks(self):
        dispatch = self.dispatch()
        checks = 0
        attempts = 0
        real_revalidate = feasibility.revalidate_dispatch

        def second_check_refuses(ticket):
            nonlocal checks
            checks += 1
            if checks == 2:
                raise feasibility.FeasibilityError("concurrent_plan_change")
            return real_revalidate(ticket)

        def count_attempt(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            raise AssertionError("attempt created before final launch check")

        with (mock.patch.object(
                feasibility, "revalidate_dispatch",
                side_effect=second_check_refuses),
              mock.patch.object(
                  work.worker_attempts, "create_attempt",
                  side_effect=count_attempt)):
            code, result = work._run_owned_work(
                self.repo, ITEM, self.repo, work.worker_config(self.repo),
                "codex", None, 30, "off", "workspace-write", "medium",
                list(dispatch.tasks), dispatch_snapshot=dispatch,
                owner_token=self.claim.token)
        self.assertEqual(code, 2, result)
        self.assertEqual(result["reason"], "concurrent_plan_change")
        self.assertEqual((checks, attempts), (2, 0))
        self.assertFalse((self.item_dir / "worker").exists())


class ReworkTest(unittest.TestCase):
    def setUp(self):
        self.temps = []

    def tearDown(self):
        for temporary in self.temps:
            temporary.cleanup()

    def fixture(self, source, *, finding=None):
        finding = finding or {
            "review": "F-01", "verify": "V-01", "assure": "S-01",
        }[source]
        temporary = tempfile.TemporaryDirectory()
        self.temps.append(temporary)
        repo = Path(temporary.name).resolve()
        initrepo.init(repo)
        config_path = repo / ".factory/config.json"
        config = json.loads(config_path.read_text())
        config["gates"] = ["feasibility"]
        config_path.write_text(json.dumps(config), encoding="utf-8")
        spec = b"Acceptance.\n"
        old_plan = b"# Plan\n- [x] original work\n"
        items.save_item(repo, {
            "id": ITEM, "title": "Feature", "stage": source,
            "kind": "backend", "created": "2026-09-09T10:00:00Z",
            "updated": "2026-09-09T11:00:00Z",
        }, "Fixture.")
        item_dir = repo / ".factory/items" / ITEM
        (item_dir / "spec.md").write_bytes(spec)
        (item_dir / "plan.md").write_bytes(old_plan)
        (item_dir / "acceptance.json").write_text(
            json.dumps(acceptance(spec, old_plan)), encoding="utf-8")
        source_names = {
            "review": "reviews/synthesis.md",
            "verify": "verify.md",
            "assure": "assurance/verdicts.json",
        }
        source_path = item_dir / source_names[source]
        source_path.parent.mkdir(parents=True, exist_ok=True)
        if source == "assure":
            source_path.write_text(json.dumps({
                "item": ITEM,
                "journeys": [{
                    "id": "J-001", "surface": "cli",
                    "scenarios": [{
                        "id": finding, "verdict": "fail",
                        "expected": "works", "actual": "broken",
                        "attribution": "regression",
                    }],
                }],
            }), encoding="utf-8")
        else:
            source_path.write_text(
                f"# Blocking findings\n- {finding}: broken\n",
                encoding="utf-8")
        proposal_dir = repo / "proposals"
        proposal_dir.mkdir()
        label = source_names[source]
        proposal_plan = old_plan + (
            f"- [ ] Fix {finding} from {label}\n".encode("utf-8"))
        plan_path = proposal_dir / "plan.md"
        plan_path.write_bytes(proposal_plan)
        from scripts.factory.lib import safeio
        source_snapshot = safeio.snapshot_path(
            repo, str(source_path.relative_to(repo)))
        proposed = acceptance(spec, proposal_plan)
        proposed["revision"] = {
            "reason": (f"{source} rejection " + source_snapshot.sha256),
            "changed_sections": ["tasks"],
        }
        acceptance_path = proposal_dir / "acceptance.json"
        acceptance_path.write_text(json.dumps(proposed), encoding="utf-8")
        return {
            "repo": repo, "item_dir": item_dir, "finding": finding,
            "source": source, "source_snapshot": source_snapshot,
            "plan_proposal": safeio.snapshot_path(repo, "proposals/plan.md"),
            "acceptance_proposal": safeio.snapshot_path(
                repo, "proposals/acceptance.json"),
            "config": config_state.capture(repo),
        }

    def prepare(self, fixture):
        return feasibility.prepare_rework_entry(
            fixture["repo"], ITEM, config=fixture["config"],
            source=fixture["source"],
            source_snapshot=fixture["source_snapshot"],
            finding_ids=[fixture["finding"]],
            plan_proposal=fixture["plan_proposal"],
            acceptance_proposal=fixture["acceptance_proposal"])

    def test_review_verify_and_regression_rework_settle_atomically(self):
        for source in ("review", "verify", "assure"):
            with self.subTest(source=source):
                fixture = self.fixture(source)
                before = tree_bytes(fixture["repo"])
                prepared = self.prepare(fixture)
                self.assertEqual(tree_bytes(fixture["repo"]), before)
                meta, _verdict, receipt = machine.commit_implement_entry(prepared)
                self.assertEqual(meta["stage"], "implement")
                self.assertEqual(
                    (fixture["item_dir"] / "plan.md").read_bytes(),
                    fixture["plan_proposal"].data)
                self.assertEqual(
                    (fixture["item_dir"] / "acceptance.json").read_bytes(),
                    fixture["acceptance_proposal"].data)
                events = [event for event in logs.read_events(
                    fixture["repo"], ITEM)
                    if event.get("operation_id") == receipt.operation_id]
                self.assertEqual(
                    [event["event"] for event in events],
                    [{"review": "review.rejected",
                      "verify": "verify.rejected",
                      "assure": "assure.rejected"}[source],
                     "stage.advance"])

    def test_rework_rejects_unlinked_tasks_and_non_regression_assurance(self):
        fixture = self.fixture("review")
        plan = fixture["repo"] / "proposals/plan.md"
        plan.write_bytes(
            (fixture["item_dir"] / "plan.md").read_bytes() +
            b"- [ ] vague task\n")
        from scripts.factory.lib import safeio
        fixture["plan_proposal"] = safeio.snapshot_path(
            fixture["repo"], "proposals/plan.md")
        with self.assertRaisesRegex(feasibility.FeasibilityError, "must name"):
            self.prepare(fixture)

        fixture = self.fixture("assure")
        source = json.loads(fixture["source_snapshot"].data)
        source["journeys"][0]["scenarios"][0]["attribution"] = "pre-existing"
        source_path = fixture["item_dir"] / "assurance/verdicts.json"
        source_path.write_text(json.dumps(source), encoding="utf-8")
        fixture["source_snapshot"] = safeio.snapshot_path(
            fixture["repo"],
            f".factory/items/{ITEM}/assurance/verdicts.json")
        with self.assertRaisesRegex(feasibility.FeasibilityError, "non-regressions"):
            self.prepare(fixture)

    def test_same_source_and_findings_conflicting_proposals_refuse(self):
        fixture = self.fixture("review")
        first = self.prepare(fixture)
        plan_path = fixture["repo"] / "proposals/plan-2.md"
        plan_bytes = fixture["plan_proposal"].data + b"extra prose\n"
        plan_path.write_bytes(plan_bytes)
        proposed = json.loads(fixture["acceptance_proposal"].data)
        proposed["plan_structure_sha256"] = feasibility.plan_structure_sha256(
            plan_bytes)
        acceptance_path = fixture["repo"] / "proposals/acceptance-2.json"
        acceptance_path.write_text(json.dumps(proposed), encoding="utf-8")
        from scripts.factory.lib import safeio
        second = feasibility.prepare_rework_entry(
            fixture["repo"], ITEM, config=fixture["config"], source="review",
            source_snapshot=fixture["source_snapshot"],
            finding_ids=[fixture["finding"]],
            plan_proposal=safeio.snapshot_path(
                fixture["repo"], "proposals/plan-2.md"),
            acceptance_proposal=safeio.snapshot_path(
                fixture["repo"], "proposals/acceptance-2.json"))
        self.assertEqual(second.operation_key, first.operation_key)
        machine.commit_implement_entry(first)
        with self.assertRaises(control.ControlRefusal):
            machine.commit_implement_entry(second)
        self.assertEqual(
            (fixture["item_dir"] / "plan.md").read_bytes(),
            fixture["plan_proposal"].data)

    def test_rework_recovers_or_retries_every_wal_boundary(self):
        hooks = ("_after_intent", "_after_blob", "_after_active",
                 "_after_replacement", "_after_event", "_after_commit")
        for hook in hooks:
            with self.subTest(hook=hook):
                fixture = self.fixture("review")
                prepared = self.prepare(fixture)
                with mock.patch.object(
                        control, hook,
                        side_effect=RuntimeError("simulated crash")):
                    with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                        machine.commit_implement_entry(prepared)
                key = feasibility.rework_operation_key(
                    "review", fixture["source_snapshot"],
                    [fixture["finding"]])
                receipt = control.adopt_operation(
                    fixture["repo"], ITEM, kind="implement-entry", key=key)
                if receipt is None:
                    _meta, _verdict, receipt = machine.commit_implement_entry(
                        prepared)
                self.assertIsNotNone(receipt)
                self.assertEqual(
                    items.load_item(fixture["repo"], ITEM)[0]["stage"],
                    "implement")
                matching = [event for event in logs.read_events(
                    fixture["repo"], ITEM)
                    if event.get("operation_id") == receipt.operation_id]
                self.assertEqual(len(matching), 2)

    def test_plan_rework_cli_is_idempotent_and_never_uses_proposals_as_authority(self):
        fixture = self.fixture("review")
        args = [
            "--repo", str(fixture["repo"]), "plan-rework", ITEM,
            "--source", "review",
            "--source-file", str(fixture["source_snapshot"].relative),
            "--finding", fixture["finding"],
            "--plan-proposal", str(fixture["plan_proposal"].relative),
            "--acceptance-proposal",
            str(fixture["acceptance_proposal"].relative), "--json",
        ]
        outputs = []
        for _attempt in range(2):
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = factory.main(args)
            self.assertEqual((code, stderr.getvalue()), (0, ""))
            outputs.append(json.loads(stdout.getvalue()))
        self.assertEqual(outputs[0]["operation_id"], outputs[1]["operation_id"])
        self.assertEqual(
            (fixture["item_dir"] / "plan.md").read_bytes(),
            fixture["plan_proposal"].data)
        fixture["plan_proposal"].root.joinpath(
            fixture["plan_proposal"].relative).write_bytes(b"later mutation\n")
        self.assertNotEqual(
            (fixture["item_dir"] / "plan.md").read_bytes(), b"later mutation\n")

if __name__ == "__main__":
    unittest.main()
