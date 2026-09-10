"""Behavioral tests for durable lost-reply reconciliation."""

import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from pathlib import PurePosixPath
from types import SimpleNamespace
from unittest import mock

from scripts.factory import factory as factory_cli
from scripts.factory.lib import control, initrepo, items, logs, reconciliation, safeio


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True,
        capture_output=True, text=True)


class ReconciliationFixture(unittest.TestCase):
    item_id = "0001-thing"
    input_path = ".factory/items/0001-thing/plan.md"
    evidence_paths = (
        ".factory/items/0001-thing/reviews/result.json",
        ".factory/items/0001-thing/reviews/tests.json",
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name).resolve()
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "test@example.test")
        _git(self.repo, "config", "user.name", "Reconciliation Test")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(self.repo, "add", "seed.txt")
        _git(self.repo, "commit", "-q", "-m", "seed")
        initrepo.init(self.repo)
        items.save_item(self.repo, {
            "id": self.item_id,
            "title": "Thing",
            "stage": "plan",
            "kind": "backend",
            "created": "2026-09-08T00:00:00Z",
            "updated": "2026-09-08T00:00:00Z",
        }, "# Thing\n")
        logs.append_event(self.repo, self.item_id, "item.created")
        self.write(self.input_path, "- [ ] Task 1\n")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative, value):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def begin(self, *, evidence=None, worktree=None):
        return reconciliation.begin(
            self.repo, self.item_id, "plan", "plan:judge",
            [self.input_path], evidence or self.evidence_paths,
            worktree=worktree)

    def inspect(self, attempt_id, writer_state="terminal", worktree=None):
        return reconciliation.inspect(
            self.repo, self.item_id, attempt_id, writer_state,
            worktree=worktree)

    def run_cli(self, *arguments, module=False):
        invocation = ([sys.executable, "-m", "scripts.factory.factory"]
                      if module else
                      [sys.executable, "scripts/factory/factory.py"])
        return subprocess.run(
            invocation + ["--repo", str(self.repo), *arguments],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True)

    def expected_json(self, value):
        return json.dumps(value, indent=2, sort_keys=True) + "\n"


class ReconciliationCliTest(ReconciliationFixture):
    def test_begin_emits_exact_json_and_discover_has_script_module_parity(self):
        begun = self.run_cli(
            "reconcile", "begin", self.item_id,
            "--stage", "plan", "--obligation", "plan:judge",
            "--input", self.input_path,
            "--evidence", *self.evidence_paths, "--json")

        self.assertEqual(begun.returncode, 0, begun.stderr)
        payload = json.loads(begun.stdout)
        self.assertEqual(set(payload), {"attempt_id", "cleanup_pending"})
        self.assertRegex(payload["attempt_id"], r"^[0-9a-f]{32}$")
        self.assertFalse(payload["cleanup_pending"])
        self.assertEqual(begun.stdout, self.expected_json(payload))
        self.assertEqual(begun.stderr, "")

        arguments = (
            "reconcile", "discover", self.item_id,
            "--stage", "plan", "--obligation", "plan:judge",
            "--input", self.input_path, "--json")
        direct = self.run_cli(*arguments)
        module = self.run_cli(*arguments, module=True)
        expected = self.expected_json([payload["attempt_id"]])
        self.assertEqual((direct.returncode, direct.stdout, direct.stderr),
                         (0, expected, ""))
        self.assertEqual((module.returncode, module.stdout, module.stderr),
                         (direct.returncode, direct.stdout, direct.stderr))

    def test_malformed_and_untrusted_states_use_distinct_refusal_codes(self):
        malformed = self.run_cli(
            "reconcile", "begin", self.item_id,
            "--stage", "plan", "--obligation", "plan:judge",
            "--input", "../escape", "--evidence", self.evidence_paths[0],
            "--json")
        self.assertEqual(malformed.returncode, 1)
        self.assertEqual(
            malformed.stdout,
            self.expected_json({
                "error": "unsafe repository-relative path: '../escape'",
            }))

        attempt = self.begin()["attempt_id"]
        self.write(self.input_path, "changed after checkpoint\n")
        contradictory = self.run_cli(
            "reconcile", "inspect", self.item_id, attempt,
            "--writer-state", "terminal", "--json")
        expected = reconciliation.inspect(
            self.repo, self.item_id, attempt, "terminal")
        self.assertEqual(contradictory.returncode, 2)
        self.assertEqual(contradictory.stdout, self.expected_json(expected))
        self.assertEqual(expected["classification"], "contradictory")

        invalid_attempt = self.run_cli(
            "reconcile", "inspect", self.item_id, "not-an-attempt",
            "--writer-state", "terminal", "--json")
        self.assertEqual(invalid_attempt.returncode, 1)
        self.assertEqual(
            invalid_attempt.stdout,
            self.expected_json({
                "error": "invalid reconciliation attempt id",
            }))

    def test_durability_uncertainty_is_untrusted_not_an_internal_error(self):
        args = SimpleNamespace(
            repo=self.repo, reconcile_command="begin", item=self.item_id,
            stage="plan",
            obligation="plan:judge", input=[self.input_path],
            evidence=list(self.evidence_paths), worktree=None)
        output = io.StringIO()
        uncertain = reconciliation.PublicationUncertain(
            "checkpoint publication is uncertain", "a" * 32, False)

        with mock.patch.object(
                factory_cli.reconciliation, "begin", side_effect=uncertain):
            with redirect_stdout(output):
                code = factory_cli.cmd_reconcile(args)

        self.assertEqual(code, 2)
        self.assertEqual(
            output.getvalue(),
            self.expected_json({
                "error": "checkpoint publication is uncertain",
            }))

        output = io.StringIO()
        with mock.patch.object(
                factory_cli.reconciliation, "begin",
                side_effect=RuntimeError("injected internal failure")):
            with redirect_stdout(output):
                code = factory_cli.cmd_reconcile(args)
        self.assertEqual(code, 1)
        self.assertEqual(
            output.getvalue(),
            self.expected_json({"error": "injected internal failure"}))

    def test_stale_and_untrusted_repository_states_exit_two(self):
        stale = self.run_cli(
            "reconcile", "begin", self.item_id,
            "--stage", "implement", "--obligation", "plan:judge",
            "--input", self.input_path,
            "--evidence", *self.evidence_paths, "--json")
        self.assertEqual(stale.returncode, 2)
        self.assertEqual(
            stale.stdout,
            self.expected_json({
                "error": "item stage is 'plan', not 'implement'",
            }))

        attempt = self.begin()["attempt_id"]
        pinned = (self.repo / ".factory/items" / self.item_id /
                  "reconciliation" / attempt / "log-prefix.jsonl")
        pinned.unlink()
        untrusted = self.run_cli(
            "reconcile", "discover", self.item_id,
            "--stage", "plan", "--obligation", "plan:judge",
            "--input", self.input_path, "--json")
        self.assertEqual(untrusted.returncode, 2)
        self.assertEqual(
            untrusted.stdout,
            self.expected_json({
                "error": "unsafe reconciliation file: log-prefix.jsonl",
            }))

    def test_claim_requires_terminal_inspection_and_never_claims_active_writer(self):
        attempt = self.begin()["attempt_id"]
        self.write(self.evidence_paths[0], "partial\n")

        inspected = self.run_cli(
            "reconcile", "inspect", self.item_id, attempt,
            "--writer-state", "active", "--json")
        expected = reconciliation.inspect(
            self.repo, self.item_id, attempt, "active")
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(inspected.stdout, self.expected_json(expected))
        self.assertEqual(
            (expected["classification"], expected["action"]),
            ("partial", "wait-active"))

        active = self.run_cli(
            "reconcile", "inspect", self.item_id, attempt,
            "--writer-state", "active", "--claim-continuation", "--json")

        self.assertEqual(active.returncode, 1)
        self.assertEqual(
            active.stdout,
            self.expected_json({
                "error": "--claim-continuation requires a terminal writer",
            }))
        claim = (self.repo / ".factory/items" / self.item_id /
                 "reconciliation" / attempt / "continuations" /
                 "claim.json")
        self.assertFalse(claim.exists())

    def test_claim_output_is_exact_and_repeated_claim_rewrites_to_stop(self):
        attempt = self.begin()["attempt_id"]
        self.write(self.evidence_paths[0], "partial\n")
        inspected = reconciliation.inspect(
            self.repo, self.item_id, attempt, "terminal")
        arguments = (
            "reconcile", "inspect", self.item_id, attempt,
            "--writer-state", "terminal", "--claim-continuation", "--json")

        first = self.run_cli(*arguments)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, self.expected_json(inspected))

        repeated = self.run_cli(*arguments, module=True)
        stopped = dict(inspected, action="stop", reason="already-claimed")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(repeated.stdout, self.expected_json(stopped))


class ParentProtocolIntegrationTest(ReconciliationFixture):
    def setUp(self):
        super().setUp()
        _git(self.repo, "checkout", "-q", "-b", f"factory/{self.item_id}")
        self.spec_path = f".factory/items/{self.item_id}/spec.md"
        self.write(self.spec_path, "# Spec\n\nImplementation contract.\n")
        self.log_path = (
            self.repo / ".factory/items" / self.item_id / "log.jsonl")

    def checkpoint(self, obligation, evidence, *, inputs=None, worktree=None):
        return reconciliation.begin(
            self.repo, self.item_id, "plan", obligation,
            inputs or [self.input_path, self.spec_path], evidence,
            worktree=worktree)["attempt_id"]

    def assert_result(self, result, classification, action):
        self.assertEqual(
            (result["classification"], result["action"]),
            (classification, action), result)

    def claim_path(self, attempt):
        return (self.repo / ".factory/items" / self.item_id /
                "reconciliation" / attempt / "continuations/claim.json")

    def test_parent_protocol_replays_every_observed_lost_reply_seam(self):
        initial_events = self.log_path.read_bytes()

        committed_evidence = [
            f".factory/items/{self.item_id}/worker/task-1.json"]
        committed_attempt = self.checkpoint(
            "implement:task-1", committed_evidence, worktree=self.repo)
        tracked = self.repo / "seed.txt"
        tracked.write_text("committed implementation delta\n", encoding="utf-8")
        _git(self.repo, "add", "seed.txt")
        _git(self.repo, "commit", "-q", "-m", "committed implementation")
        committed_bytes = tracked.read_bytes()
        committed = reconciliation.inspect(
            self.repo, self.item_id, committed_attempt, "terminal", self.repo)
        self.assert_result(committed, "partial", "continue")
        committed_claim = reconciliation.claim_continuation(
            self.repo, self.item_id, committed_attempt, committed)
        self.assertEqual(committed_claim["action"], "continue")
        self.assertEqual(tracked.read_bytes(), committed_bytes)
        self.assertEqual(self.log_path.read_bytes(), initial_events)
        self.assertTrue(self.claim_path(committed_attempt).is_file())

        uncommitted_evidence = [
            f".factory/items/{self.item_id}/worker/task-2.json"]
        uncommitted_attempt = self.checkpoint(
            "implement:task-2", uncommitted_evidence, worktree=self.repo)
        tracked.write_text(
            "uncommitted implementation delta\n", encoding="utf-8")
        uncommitted_bytes = tracked.read_bytes()
        uncommitted = reconciliation.inspect(
            self.repo, self.item_id, uncommitted_attempt,
            "terminal", self.repo)
        self.assert_result(uncommitted, "partial", "continue")
        uncommitted_claim = reconciliation.claim_continuation(
            self.repo, self.item_id, uncommitted_attempt, uncommitted)
        self.assertEqual(uncommitted_claim["action"], "continue")
        self.assertEqual(tracked.read_bytes(), uncommitted_bytes)
        self.assertEqual(self.log_path.read_bytes(), initial_events)
        self.assertTrue(self.claim_path(uncommitted_attempt).is_file())
        tracked.write_bytes(committed_bytes)

        implementation_report = (
            f".factory/items/{self.item_id}/worker/task-3.json")
        implementation_attempt = self.checkpoint(
            "implement:task-3", [implementation_report], worktree=self.repo)
        self.write(implementation_report, '{"status":"complete"}\n')
        implemented = reconciliation.inspect(
            self.repo, self.item_id, implementation_attempt,
            "terminal", self.repo)
        self.assert_result(implemented, "complete", "adopt")

        reviewer_report = (
            f".factory/items/{self.item_id}/reviews/task-3.md")
        reviewer_attempt = self.checkpoint(
            "implement:review-task-3", [reviewer_report],
            inputs=[self.input_path, self.spec_path, implementation_report],
            worktree=self.repo)
        missing_review = reconciliation.inspect(
            self.repo, self.item_id, reviewer_attempt, "terminal", self.repo)
        self.assert_result(missing_review, "absent", "count-failure")

        seed = f".factory/items/{self.item_id}/reviews/seed-context.md"
        self.write(seed, "current council seed\n")
        seats = [
            f".factory/items/{self.item_id}/reviews/round-1/{role}.md"
            for role in ("product", "architecture", "engineering-quality")]
        seats_attempt = self.checkpoint(
            "review:council-round-1", seats, inputs=[seed])
        for seat in seats:
            self.write(seat, f"complete seat: {Path(seat).stem}\n")
        complete_seats = reconciliation.inspect(
            self.repo, self.item_id, seats_attempt, "terminal")
        self.assert_result(complete_seats, "complete", "adopt")

        synthesis = f".factory/items/{self.item_id}/reviews/synthesis.md"
        synthesis_attempt = self.checkpoint(
            "review:council-synthesis", [synthesis], inputs=[seed, *seats])
        self.write(synthesis, "# Complete synthesis\n\nNo blocking findings.\n")
        complete_synthesis = reconciliation.inspect(
            self.repo, self.item_id, synthesis_attempt, "terminal")
        self.assert_result(complete_synthesis, "complete", "adopt")

        impact = f".factory/items/{self.item_id}/assurance/impact.json"
        contract = "docs/factory/journeys/contracts/J-001.md"
        base_sha = (
            f".factory/items/{self.item_id}/assurance/"
            "reconciliation/J-001-base-sha.txt")
        self.write(impact, '{"journeys":["J-001"]}\n')
        self.write(contract, "# J-001\n\n## Run & fixtures\n\nRun it.\n")
        self.write(base_sha, _git(self.repo, "rev-parse", "HEAD").stdout)
        assurance_report = (
            f".factory/items/{self.item_id}/assurance/"
            "journeys/J-001/report.json")
        assurance_evidence = (
            f".factory/items/{self.item_id}/assurance/"
            "transcripts/J-001-S1.txt")
        assurance_attempt = self.checkpoint(
            "assure:J-001", [assurance_report, assurance_evidence],
            inputs=[impact, contract, base_sha])
        self.write(assurance_evidence, "$ app --journey J-001\npartial\n")
        partial_assurance = reconciliation.inspect(
            self.repo, self.item_id, assurance_attempt, "terminal")
        self.assert_result(partial_assurance, "partial", "continue")

        stable_input = (self.repo / self.input_path).read_bytes()
        stale_attempt = self.checkpoint("plan:stale", [
            f".factory/items/{self.item_id}/reviews/stale.json"])
        (self.repo / self.input_path).write_bytes(stable_input + b"changed\n")
        stale = reconciliation.inspect(
            self.repo, self.item_id, stale_attempt, "terminal")
        self.assert_result(stale, "contradictory", "stop")
        (self.repo / self.input_path).write_bytes(stable_input)

        wrong_checkout_attempt = self.checkpoint(
            "implement:wrong-checkout", [
                f".factory/items/{self.item_id}/worker/wrong.json"],
            worktree=self.repo)
        wrong_checkout = self.repo / "not-the-registered-worktree"
        wrong_checkout.mkdir()
        wrong = reconciliation.inspect(
            self.repo, self.item_id, wrong_checkout_attempt,
            "terminal", wrong_checkout)
        self.assert_result(wrong, "contradictory", "stop")

        active_evidence = [
            f".factory/items/{self.item_id}/reviews/active.json",
            f".factory/items/{self.item_id}/reviews/active-tests.json"]
        active_attempt = self.checkpoint("review:active", active_evidence)
        self.write(active_evidence[0], '{"status":"running"}\n')
        active = reconciliation.inspect(
            self.repo, self.item_id, active_attempt, "active")
        self.assert_result(active, "partial", "wait-active")
        self.assertFalse(self.claim_path(active_attempt).exists())

        repeated_evidence = [
            f".factory/items/{self.item_id}/reviews/partial.json",
            f".factory/items/{self.item_id}/reviews/partial-tests.json"]
        repeated_attempt = self.checkpoint(
            "review:partial", repeated_evidence)
        self.write(repeated_evidence[0], '{"status":"partial"}\n')
        unchanged_partial = reconciliation.inspect(
            self.repo, self.item_id, repeated_attempt, "terminal")
        self.assert_result(unchanged_partial, "partial", "continue")
        claims = [
            reconciliation.claim_continuation(
                self.repo, self.item_id, repeated_attempt,
                unchanged_partial)
            for _ in range(2)]
        self.assertEqual([claim["action"] for claim in claims],
                         ["continue", "stop"])
        self.assertEqual(claims[1]["reason"], "already-claimed")
        self.assertEqual(
            list(self.claim_path(repeated_attempt).parent.glob("claim.json")),
            [self.claim_path(repeated_attempt)])

        transition_attempt = self.checkpoint(
            "plan:finalize", [
                f".factory/items/{self.item_id}/reviews/final.json"])
        meta, body = items.load_item(self.repo, self.item_id)
        meta["stage"] = "implement"
        meta["updated"] = "2026-09-08T01:00:00Z"
        items.save_item(self.repo, meta, body)
        logs.append_event(
            self.repo, self.item_id, "stage.advance",
            {"from": "plan", "to": "implement"})
        transitioned_events = self.log_path.read_bytes()
        transitioned = reconciliation.inspect(
            self.repo, self.item_id, transition_attempt, "terminal")
        self.assert_result(transitioned, "complete", "adopt")
        self.assertEqual(self.log_path.read_bytes(), transitioned_events)
        stage_advances = [
            event for event in logs.read_events(self.repo, self.item_id)
            if event["event"] == "stage.advance"]
        self.assertEqual(len(stage_advances), 1)

        no_authorization = (
            missing_review, stale, wrong, active, transitioned,
            complete_seats, complete_synthesis, implemented)
        self.assertNotIn("continue", [row["action"]
                                      for row in no_authorization])
        self.assertEqual(self.log_path.read_bytes(), transitioned_events)


class BeginDiscoverTest(ReconciliationFixture):
    def test_unsafe_duplicate_and_overlapping_paths_are_refused(self):
        bad_inputs = ("/absolute", "../escape", "a//b", "a\\b", "")
        for value in bad_inputs:
            with self.subTest(value=value):
                with self.assertRaises(reconciliation.ReconciliationError):
                    reconciliation.begin(
                        self.repo, self.item_id, "plan", "plan:judge",
                        [value], self.evidence_paths)
        with self.assertRaises(reconciliation.ReconciliationError):
            reconciliation.begin(
                self.repo, self.item_id, "plan", "plan:judge",
                [self.input_path], [self.input_path])
        with self.assertRaises(reconciliation.ReconciliationError):
            reconciliation.begin(
                self.repo, self.item_id, "plan", "plan:judge",
                [".factory/items"], [self.evidence_paths[0]])

    def test_begin_publishes_exact_self_bound_manifest(self):
        log_path = self.repo / ".factory/items" / self.item_id / "log.jsonl"
        baseline_log = log_path.read_bytes()
        baseline_inode = (log_path.stat().st_dev, log_path.stat().st_ino)
        result = self.begin()
        self.assertRegex(result["attempt_id"], r"^[0-9a-f]{32}$")
        self.assertFalse(result["cleanup_pending"])
        attempt = (self.repo / ".factory/items" / self.item_id /
                   "reconciliation" / result["attempt_id"])
        manifest_path = attempt / "manifest.json"
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
        self.assertEqual(raw, reconciliation._canonical_json(manifest))
        self.assertEqual(set(manifest), reconciliation._MANIFEST_KEYS)
        self.assertEqual(manifest["attempt_id"], result["attempt_id"])
        self.assertEqual(manifest["item"], self.item_id)
        self.assertEqual(manifest["stage"], "plan")
        self.assertEqual(manifest["obligation"], "plan:judge")
        self.assertEqual(
            (manifest["attempt_dir"]["dev"], manifest["attempt_dir"]["ino"]),
            (attempt.stat().st_dev, attempt.stat().st_ino))
        self.assertEqual(
            (manifest["manifest_file"]["dev"],
             manifest["manifest_file"]["ino"]),
            (manifest_path.stat().st_dev, manifest_path.stat().st_ino))
        pinned_log = attempt / "log-prefix.jsonl"
        self.assertEqual(pinned_log.read_bytes(), baseline_log)
        self.assertEqual(
            (pinned_log.stat().st_dev, pinned_log.stat().st_ino),
            baseline_inode)
        self.assertEqual(list(attempt.glob(".manifest.json.tmp-*")), [])

    def test_discover_zero_one_and_ambiguous_attempts(self):
        self.assertEqual(reconciliation.discover(
            self.repo, self.item_id, "plan", "plan:judge",
            [self.input_path]), [])
        first = self.begin()["attempt_id"]
        self.assertEqual(reconciliation.discover(
            self.repo, self.item_id, "plan", "plan:judge",
            [self.input_path]), [first])
        second = self.begin()["attempt_id"]
        self.assertEqual(reconciliation.discover(
            self.repo, self.item_id, "plan", "plan:judge",
            [self.input_path]), sorted([first, second]))

    def test_stale_input_is_not_discovered_and_inspection_stops(self):
        attempt = self.begin()["attempt_id"]
        self.write(self.input_path, "changed\n")
        self.assertEqual(reconciliation.discover(
            self.repo, self.item_id, "plan", "plan:judge",
            [self.input_path]), [])
        result = self.inspect(attempt)
        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))
        self.assertIn("input", result["reason"])

    def test_missing_pinned_log_is_not_discoverable_or_adoptable(self):
        attempt = self.begin()["attempt_id"]
        pinned = (self.repo / ".factory/items" / self.item_id /
                  "reconciliation" / attempt / "log-prefix.jsonl")
        pinned.unlink()

        with self.assertRaises(reconciliation.ReconciliationError):
            reconciliation.discover(
                self.repo, self.item_id, "plan", "plan:judge",
                [self.input_path])
        result = self.inspect(attempt)
        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))


class ClassificationTest(ReconciliationFixture):
    def test_absent_partial_complete_and_active(self):
        attempt = self.begin()["attempt_id"]
        absent = self.inspect(attempt)
        self.assertEqual((absent["classification"], absent["action"]),
                         ("absent", "count-failure"))

        self.write(self.evidence_paths[0], '{"status":"partial"}\n')
        active = self.inspect(attempt, "active")
        self.assertEqual((active["classification"], active["action"]),
                         ("partial", "wait-active"))
        partial = self.inspect(attempt)
        self.assertEqual((partial["classification"], partial["action"]),
                         ("partial", "continue"))
        self.assertEqual(partial["changed_evidence"],
                         [self.evidence_paths[0]])

        self.write(self.evidence_paths[1], '{"tests":"red"}\n')
        complete = self.inspect(attempt)
        self.assertEqual((complete["classification"], complete["action"]),
                         ("complete", "adopt"))
        self.assertEqual(complete["changed_evidence"],
                         list(self.evidence_paths))

    def test_engine_transition_is_complete_and_metadata_only_is_stop(self):
        attempt = self.begin()["attempt_id"]
        meta, body = items.load_item(self.repo, self.item_id)
        meta["stage"] = "implement"
        meta["updated"] = "2026-09-08T01:00:00Z"
        items.save_item(self.repo, meta, body)
        logs.append_event(self.repo, self.item_id, "stage.advance",
                          {"from": "plan", "to": "implement"})
        complete = self.inspect(attempt)
        self.assertEqual((complete["classification"], complete["action"]),
                         ("complete", "adopt"))

        other = self.begin_at_stage("implement")
        meta, body = items.load_item(self.repo, self.item_id)
        meta["stage"] = "review"
        items.save_item(self.repo, meta, body)
        stopped = self.inspect(other)
        self.assertEqual((stopped["classification"], stopped["action"]),
                         ("contradictory", "stop"))
        self.assertIn("without a stage transition", stopped["reason"])

    def test_transactional_item_replacement_and_cow_log_are_complete(self):
        attempt = self.begin()["attempt_id"]
        item_relative = PurePosixPath(
            ".factory", "items", self.item_id, "item.md")
        log_relative = PurePosixPath(
            ".factory", "items", self.item_id, "log.jsonl")
        item_snapshot = safeio.snapshot_path(self.repo, item_relative)
        log_snapshot = safeio.snapshot_path(self.repo, log_relative)
        meta, body = items.parse_item(item_snapshot.data.decode("utf-8"))
        meta["stage"] = "implement"
        meta["updated"] = "2026-09-08T01:00:00Z"
        before_inode = item_snapshot.file_identity[:2]
        control.commit_operation(
            self.repo, self.item_id, kind="test.reconciliation",
            key=attempt, request={"attempt": attempt},
            replacements=((
                item_snapshot,
                items.render_item(meta, body).encode("utf-8")),),
            events=({
                "event": "stage.advance",
                "ts": "2026-09-08T01:00:00Z",
                "data": {"from": "plan", "to": "implement"},
            },),
            log_snapshot=log_snapshot)
        self.assertNotEqual(
            (self.repo / item_relative).stat().st_ino, before_inode[1])

        complete = self.inspect(attempt)

        self.assertEqual((complete["classification"], complete["action"]),
                         ("complete", "adopt"))

    def test_metadata_only_change_waits_for_active_writer(self):
        attempt = self.begin()["attempt_id"]
        meta, body = items.load_item(self.repo, self.item_id)
        meta["stage"] = "implement"
        items.save_item(self.repo, meta, body)
        active = self.inspect(attempt, "active")
        terminal = self.inspect(attempt, "terminal")
        self.assertEqual(active["action"], "wait-active")
        self.assertEqual(terminal["action"], "stop")

    def test_leaving_and_reentering_baseline_stage_remains_complete(self):
        attempt = self.begin()["attempt_id"]
        for frm, to in (("plan", "implement"), ("implement", "review"),
                        ("review", "spec"), ("spec", "plan")):
            logs.append_event(self.repo, self.item_id, "stage.advance",
                              {"from": frm, "to": to})
        complete = self.inspect(attempt)
        self.assertEqual((complete["classification"], complete["action"]),
                         ("complete", "adopt"))

    def test_disconnected_transition_history_is_never_adopted(self):
        attempt = self.begin()["attempt_id"]
        meta, body = items.load_item(self.repo, self.item_id)
        meta["stage"] = "ship"
        items.save_item(self.repo, meta, body)
        logs.append_event(self.repo, self.item_id, "stage.advance",
                          {"from": "plan", "to": "implement"})
        logs.append_event(self.repo, self.item_id, "stage.advance",
                          {"from": "review", "to": "ship"})

        result = self.inspect(attempt)

        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))
        self.assertIn("disconnected", result["reason"])

    def test_connected_but_illegal_transition_history_is_never_adopted(self):
        attempt = self.begin()["attempt_id"]
        meta, body = items.load_item(self.repo, self.item_id)
        meta["stage"] = "ship"
        items.save_item(self.repo, meta, body)
        logs.append_event(self.repo, self.item_id, "stage.advance",
                          {"from": "plan", "to": "ship"})

        result = self.inspect(attempt)

        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))
        self.assertIn("illegitimate", result["reason"])

    def test_pause_must_resume_to_the_stage_that_parked(self):
        attempt = self.begin()["attempt_id"]
        meta, body = items.load_item(self.repo, self.item_id)
        meta["stage"] = "review"
        items.save_item(self.repo, meta, body)
        logs.append_event(self.repo, self.item_id, "stage.advance",
                          {"from": "plan", "to": "waiting-human"})
        logs.append_event(self.repo, self.item_id, "stage.advance",
                          {"from": "waiting-human", "to": "review"})

        result = self.inspect(attempt)

        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))
        self.assertIn("illegitimate", result["reason"])

    def test_matching_pause_and_resume_history_remains_adoptable(self):
        attempt = self.begin()["attempt_id"]
        logs.append_event(self.repo, self.item_id, "stage.advance",
                          {"from": "plan", "to": "waiting-human"})
        logs.append_event(self.repo, self.item_id, "stage.advance",
                          {"from": "waiting-human", "to": "plan"})

        result = self.inspect(attempt)

        self.assertEqual((result["classification"], result["action"]),
                         ("complete", "adopt"))

    def test_resume_from_baseline_special_stage_fails_closed(self):
        meta, body = items.load_item(self.repo, self.item_id)
        meta["stage"] = "waiting-human"
        meta["paused-from"] = "plan"
        items.save_item(self.repo, meta, body)
        attempt = self.begin_at_stage("waiting-human")
        meta["stage"] = "plan"
        meta.pop("paused-from")
        items.save_item(self.repo, meta, body)
        logs.append_event(self.repo, self.item_id, "stage.advance",
                          {"from": "waiting-human", "to": "plan"})

        result = self.inspect(attempt)

        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))
        self.assertIn("illegitimate", result["reason"])

    def begin_at_stage(self, stage):
        return reconciliation.begin(
            self.repo, self.item_id, stage, f"{stage}:child",
            [self.input_path], self.evidence_paths)["attempt_id"]

    def test_in_place_torn_suffix_stops_even_for_active_writer(self):
        attempt = self.begin()["attempt_id"]
        log_path = self.repo / ".factory/items" / self.item_id / "log.jsonl"
        with log_path.open("ab") as stream:
            stream.write(b'{"event":"stage.advance"')
        active = self.inspect(attempt, "active")
        terminal = self.inspect(attempt, "terminal")
        self.assertEqual((active["classification"], active["action"]),
                         ("contradictory", "stop"))
        self.assertIn("pinned event log prefix", active["reason"])
        self.assertEqual((terminal["classification"], terminal["action"]),
                         ("contradictory", "stop"))

    def test_in_place_invalid_utf8_suffix_stops_for_active_writer(self):
        attempt = self.begin()["attempt_id"]
        log_path = self.repo / ".factory/items" / self.item_id / "log.jsonl"
        with log_path.open("ab") as stream:
            stream.write(
                b'{"event":"worker.note","ts":"2026-09-08T00:00:00Z",'
                b'"data":"\xff"}\n')
        result = self.inspect(attempt, "active")
        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))
        self.assertIn("pinned event log prefix", result["reason"])

    def test_valid_in_place_append_changes_the_pinned_prefix_and_stops(self):
        attempt = self.begin()["attempt_id"]
        log_path = self.repo / ".factory/items" / self.item_id / "log.jsonl"
        with log_path.open("ab") as stream:
            stream.write(
                b'{"event":"worker.note","ts":"2026-09-08T00:00:00Z"}\n')

        result = self.inspect(attempt, "terminal")

        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))
        self.assertIn("pinned event log prefix", result["reason"])

    def test_invalid_utf8_suffix_stops_for_terminal_writer(self):
        attempt = self.begin()["attempt_id"]
        log_path = self.repo / ".factory/items" / self.item_id / "log.jsonl"
        with log_path.open("ab") as stream:
            stream.write(
                b'{"event":"worker.note","ts":"2026-09-08T00:00:00Z",'
                b'"data":"\xff"}\n')
        result = self.inspect(attempt, "terminal")
        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))

    def test_deleted_or_symlinked_evidence_stops(self):
        existing = self.write(self.evidence_paths[0], "baseline\n")
        attempt = self.begin()["attempt_id"]
        existing.unlink()
        deleted = self.inspect(attempt)
        self.assertEqual(deleted["action"], "stop")
        self.assertIn("deleted", deleted["reason"])

        attempt = self.begin()["attempt_id"]
        outside = self.write("outside.txt", "not evidence\n")
        link = self.repo / self.evidence_paths[1]
        link.symlink_to(outside)
        symlinked = self.inspect(attempt)
        self.assertEqual((symlinked["classification"], symlinked["action"]),
                         ("contradictory", "stop"))


class ContinuationTest(ReconciliationFixture):
    def test_only_one_claim_succeeds_even_concurrently(self):
        attempt = self.begin()["attempt_id"]
        self.write(self.evidence_paths[0], "partial\n")
        result = self.inspect(attempt)
        gate = threading.Barrier(2)
        outcomes = []

        def claim():
            gate.wait()
            outcomes.append(reconciliation.claim_continuation(
                self.repo, self.item_id, attempt, result))

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([row["action"] for row in outcomes].count("continue"), 1)
        self.assertEqual([row["action"] for row in outcomes].count("stop"), 1)
        repeated = reconciliation.claim_continuation(
            self.repo, self.item_id, attempt, result)
        self.assertEqual(repeated["action"], "stop")
        self.assertEqual(repeated["reason"], "already-claimed")

    def test_changed_observation_is_not_claimed(self):
        attempt = self.begin()["attempt_id"]
        first = self.write(self.evidence_paths[0], "partial-one\n")
        result = self.inspect(attempt)
        first.write_text("partial-two\n", encoding="utf-8")
        stopped = reconciliation.claim_continuation(
            self.repo, self.item_id, attempt, result)
        self.assertEqual(stopped["action"], "stop")
        self.assertEqual(stopped["reason"], "observation-changed")
        claim = (self.repo / ".factory/items" / self.item_id /
                 "reconciliation" / attempt / "continuations/claim.json")
        self.assertFalse(claim.exists())


class WorktreeStateTest(ReconciliationFixture):
    def setUp(self):
        super().setUp()
        _git(self.repo, "checkout", "-q", "-b", f"factory/{self.item_id}")

    def test_reconciliation_metadata_is_not_checkout_progress(self):
        attempt = self.begin(worktree=self.repo)["attempt_id"]
        unchanged = self.inspect(attempt, worktree=self.repo)
        self.assertEqual(
            (unchanged["classification"], unchanged["action"]),
            ("absent", "count-failure"))

        (self.repo / "seed.txt").write_text(
            "real child progress\n", encoding="utf-8")
        partial = self.inspect(attempt, worktree=self.repo)
        self.assertEqual(
            (partial["classification"], partial["action"]),
            ("partial", "continue"))
        claimed = reconciliation.claim_continuation(
            self.repo, self.item_id, attempt, partial)
        repeated = reconciliation.claim_continuation(
            self.repo, self.item_id, attempt, partial)
        self.assertEqual(claimed["action"], "continue")
        self.assertEqual(
            (repeated["action"], repeated["reason"]),
            ("stop", "already-claimed"))

    def test_further_edit_to_dirty_file_changes_checkout_fingerprint(self):
        dirty = self.repo / "seed.txt"
        dirty.write_text("first dirty state\n", encoding="utf-8")
        attempt = self.begin(worktree=self.repo)["attempt_id"]
        dirty.write_text("second dirty state\n", encoding="utf-8")
        result = self.inspect(attempt, worktree=self.repo)
        self.assertEqual((result["classification"], result["action"]),
                         ("partial", "continue"))

    def test_unsyncable_checkout_progress_cannot_authorize_continuation(self):
        dirty = self.repo / "seed.txt"
        attempt = self.begin(worktree=self.repo)["attempt_id"]
        dirty.write_text("unsynced child progress\n", encoding="utf-8")
        dirty_identity = (dirty.stat().st_dev, dirty.stat().st_ino)

        class CheckoutSyncFailOps(reconciliation.FilesystemOps):
            def sync_observation(self, fd):
                if reconciliation._identity(os.fstat(fd)) == dirty_identity:
                    raise OSError("injected checkout durability failure")
                return super().sync_observation(fd)

        result = reconciliation.inspect(
            self.repo, self.item_id, attempt, "terminal", self.repo,
            _ops=CheckoutSyncFailOps())

        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))
        self.assertIn("checkout", result["reason"])

    def test_unsyncable_clean_commit_leaf_cannot_authorize_continuation(self):
        dirty = self.repo / "seed.txt"
        attempt = self.begin(worktree=self.repo)["attempt_id"]
        dirty.write_text("committed child progress\n", encoding="utf-8")
        _git(self.repo, "add", "seed.txt")
        _git(self.repo, "commit", "-q", "-m", "child progress")
        dirty_identity = (dirty.stat().st_dev, dirty.stat().st_ino)

        class CheckoutSyncFailOps(reconciliation.FilesystemOps):
            def sync_observation(self, fd):
                if reconciliation._identity(os.fstat(fd)) == dirty_identity:
                    raise OSError("injected committed-leaf durability failure")
                return super().sync_observation(fd)

        result = reconciliation.inspect(
            self.repo, self.item_id, attempt, "terminal", self.repo,
            _ops=CheckoutSyncFailOps())

        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))
        self.assertIn("checkout", result["reason"])

    def test_textconv_cannot_hide_further_tracked_file_progress(self):
        textconv = self.repo / "lossy-textconv.sh"
        textconv.write_text("#!/bin/sh\nprintf 'constant\\n'\n", encoding="utf-8")
        textconv.chmod(0o755)
        (self.repo / ".gitattributes").write_text(
            "seed.txt diff=lossy\n", encoding="utf-8")
        _git(self.repo, "config", "diff.lossy.textconv", str(textconv))
        _git(self.repo, "add", ".gitattributes", "lossy-textconv.sh")
        _git(self.repo, "commit", "-q", "-m", "configure lossy textconv")

        dirty = self.repo / "seed.txt"
        dirty.write_text("first dirty state\n", encoding="utf-8")
        attempt = self.begin(worktree=self.repo)["attempt_id"]
        dirty.write_text("second dirty state\n", encoding="utf-8")
        result = self.inspect(attempt, worktree=self.repo)
        self.assertEqual((result["classification"], result["action"]),
                         ("partial", "continue"))

    def test_non_string_checkout_head_is_a_safe_manifest_refusal(self):
        attempt = self.begin(worktree=self.repo)["attempt_id"]
        manifest = (self.repo / ".factory/items" / self.item_id /
                    "reconciliation" / attempt / "manifest.json")
        value = json.loads(manifest.read_bytes())
        value["checkout"]["head"] = 42
        manifest.write_bytes(reconciliation._canonical_json(value))

        result = self.inspect(attempt, worktree=self.repo)
        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))
        self.assertIn("checkout", result["reason"])
        with self.assertRaises(reconciliation.ReconciliationError):
            reconciliation.discover(
                self.repo, self.item_id, "plan", "plan:judge",
                [self.input_path], worktree=self.repo)

    def test_wrong_registered_worktree_stops(self):
        attempt = self.begin(worktree=self.repo)["attempt_id"]
        other = self.repo / "other"
        other.mkdir()
        result = self.inspect(attempt, worktree=other)
        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))

    def test_untracked_file_and_symlink_target_bytes_change_state(self):
        untracked = self.repo / "untracked.txt"
        untracked.write_text("one\n", encoding="utf-8")
        attempt = self.begin(worktree=self.repo)["attempt_id"]
        untracked.write_text("two\n", encoding="utf-8")
        self.assertEqual(
            self.inspect(attempt, worktree=self.repo)["action"], "continue")

        shutil.rmtree(self.repo / ".factory/items" / self.item_id /
                      "reconciliation")
        target_one = self.repo / "target-one"
        target_two = self.repo / "target-two"
        target_one.write_text("same\n", encoding="utf-8")
        target_two.write_text("same\n", encoding="utf-8")
        link = self.repo / "untracked-link"
        link.symlink_to(target_one.name)
        attempt = self.begin(worktree=self.repo)["attempt_id"]
        link.unlink()
        link.symlink_to(target_two.name)
        self.assertEqual(
            self.inspect(attempt, worktree=self.repo)["action"], "continue")


class FaultOps(reconciliation.FilesystemOps):
    def __init__(self, *, directory_fsync=None, regular_fsync=False,
                 zero_write=False, short_write=False, link_error=False,
                 unlink_error=False, reopen_name=None, link_hook=None,
                 temp_open_error=False, post_publish_open_hook=None):
        self.directory_fsync = directory_fsync
        self.regular_fsync = regular_fsync
        self.zero_write = zero_write
        self.short_write = short_write
        self.link_error = link_error
        self.unlink_error = unlink_error
        self.reopen_name = reopen_name
        self.link_hook = link_hook
        self.temp_open_error = temp_open_error
        self.post_publish_open_hook = post_publish_open_hook
        self.post_publish_opened = False
        self.directory_fsyncs = 0
        self.regular_fsyncs = 0
        self.writes = 0
        self.links = 0
        self.unlinks = 0
        self.published = False

    def open(self, path, flags, mode=0o777, *, dir_fd=None):
        if (self.published and self.post_publish_open_hook is not None
                and not self.post_publish_opened and dir_fd is None):
            self.post_publish_opened = True
            self.post_publish_open_hook()
        if self.temp_open_error and ".tmp-" in str(path):
            raise OSError("injected temporary open failure")
        if self.published and path == self.reopen_name:
            raise OSError("injected final reopen failure")
        return super().open(path, flags, mode, dir_fd=dir_fd)

    def write(self, fd, data):
        self.writes += 1
        if self.zero_write and self.writes == 1:
            return 0
        if self.short_write and self.writes == 1:
            return os.write(fd, memoryview(data)[:7])
        return super().write(fd, data)

    def fsync(self, fd):
        details = os.fstat(fd)
        if stat.S_ISDIR(details.st_mode):
            self.directory_fsyncs += 1
            if self.directory_fsyncs == self.directory_fsync:
                raise OSError("injected directory fsync failure")
        else:
            self.regular_fsyncs += 1
            if self.regular_fsync and self.regular_fsyncs == 1:
                raise OSError("injected file fsync failure")
        return super().fsync(fd)

    def link(self, src, dst, *, src_dir_fd=None, dst_dir_fd=None,
             follow_symlinks=True):
        self.links += 1
        if self.link_hook is not None:
            self.link_hook(src, dst)
        if self.link_error:
            raise OSError("injected link failure")
        result = super().link(
            src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks)
        self.published = True
        return result

    def unlink(self, path, *, dir_fd=None):
        self.unlinks += 1
        if self.unlink_error and self.published:
            raise OSError("injected cleanup unlink failure")
        return super().unlink(path, dir_fd=dir_fd)


class PublicationTest(ReconciliationFixture):
    def call_begin(self, ops):
        return reconciliation.begin(
            self.repo, self.item_id, "plan", "plan:judge",
            [self.input_path], self.evidence_paths, _ops=ops)

    def manifest_paths(self):
        root = self.repo / ".factory/items" / self.item_id / "reconciliation"
        if not root.exists():
            return []
        return list(root.glob("*/manifest.json"))

    @unittest.skipUnless(Path("/dev/fd").exists(), "requires descriptor listing")
    def test_prepublish_failures_leave_no_final_and_leak_no_descriptors(self):
        cases = (
            FaultOps(temp_open_error=True),
            FaultOps(zero_write=True),
            FaultOps(regular_fsync=True),
            FaultOps(link_error=True),
        )
        for ops in cases:
            with self.subTest(ops=vars(ops)):
                before = len(os.listdir("/dev/fd"))
                with self.assertRaises(reconciliation.PublicationUncertain) as ctx:
                    self.call_begin(ops)
                self.assertFalse(ctx.exception.committed)
                self.assertEqual(self.manifest_paths(), [])
                self.assertEqual(len(os.listdir("/dev/fd")), before)

    def test_short_writes_are_completed(self):
        result = self.call_begin(FaultOps(short_write=True))
        self.assertFalse(result["cleanup_pending"])
        self.assertEqual(len(self.manifest_paths()), 1)

    def test_created_directory_fsync_failures_return_no_authorization(self):
        for occurrence in (1, 2):
            with self.subTest(occurrence=occurrence):
                # Each case needs a pristine reconciliation tree.
                ops = FaultOps(directory_fsync=occurrence)
                with self.assertRaises(reconciliation.PublicationUncertain) as ctx:
                    self.call_begin(ops)
                self.assertFalse(ctx.exception.committed)
                root = (self.repo / ".factory/items" / self.item_id /
                        "reconciliation")
                if root.exists():
                    shutil.rmtree(root)

    def test_retry_reestablishes_existing_parent_directory_durability(self):
        ops = FaultOps(directory_fsync=1)
        with self.assertRaises(reconciliation.PublicationUncertain):
            self.call_begin(ops)
        root = (self.repo / ".factory/items" / self.item_id /
                "reconciliation")
        self.assertTrue(root.is_dir())
        failed_count = ops.directory_fsyncs

        ops.directory_fsync = None
        result = self.call_begin(ops)

        self.assertFalse(result["cleanup_pending"])
        self.assertGreater(ops.directory_fsyncs, failed_count)

    def test_uncommitted_manifest_needs_recovery_fsync_before_authority(self):
        ops = FaultOps(directory_fsync=4)
        with self.assertRaises(reconciliation.PublicationUncertain) as ctx:
            self.call_begin(ops)
        self.assertFalse(ctx.exception.committed)
        finals = self.manifest_paths()
        self.assertEqual(len(finals), 1)
        attempt = finals[0].parent
        temps = list(attempt.glob(".manifest.json.tmp-*"))
        self.assertEqual(len(temps), 1)
        self.assertEqual(finals[0].read_bytes(), temps[0].read_bytes())
        self.assertEqual(finals[0].stat().st_ino, temps[0].stat().st_ino)

        attempt_identity = (attempt.stat().st_dev, attempt.stat().st_ino)

        class ManifestCommitFailOps(reconciliation.FilesystemOps):
            def sync_observation(self, fd):
                details = os.fstat(fd)
                if (stat.S_ISDIR(details.st_mode)
                        and reconciliation._identity(details) ==
                        attempt_identity):
                    raise OSError("injected manifest durability failure")
                return super().sync_observation(fd)

        recovery_ops = ManifestCommitFailOps()
        with self.assertRaises(reconciliation.ReconciliationError):
            reconciliation.discover(
                self.repo, self.item_id, "plan", "plan:judge",
                [self.input_path], _ops=recovery_ops)
        refused = reconciliation.inspect(
            self.repo, self.item_id, ctx.exception.attempt_id,
            "terminal", _ops=recovery_ops)
        self.assertEqual((refused["classification"], refused["action"]),
                         ("contradictory", "stop"))
        self.assertIn("attempt namespace", refused["reason"])

        # The visible same-inode residue becomes authority only after a later
        # recovery successfully fsyncs and revalidates the exact manifest and
        # attempt namespace.
        self.assertEqual(
            reconciliation.discover(
                self.repo, self.item_id, "plan", "plan:judge",
                [self.input_path]),
            [ctx.exception.attempt_id])
        recovered = reconciliation.inspect(
            self.repo, self.item_id, ctx.exception.attempt_id, "terminal")
        self.assertEqual((recovered["classification"], recovered["action"]),
                         ("absent", "count-failure"))

    def test_postcommit_cleanup_failures_are_reported_without_revocation(self):
        unlink = self.call_begin(FaultOps(unlink_error=True))
        self.assertTrue(unlink["cleanup_pending"])
        self.assertEqual(len(self.manifest_paths()), 1)

        root = self.repo / ".factory/items" / self.item_id / "reconciliation"
        shutil.rmtree(root)
        cleanup_fsync = self.call_begin(FaultOps(directory_fsync=5))
        self.assertTrue(cleanup_fsync["cleanup_pending"])
        self.assertEqual(len(self.manifest_paths()), 1)

    def test_final_reopen_failure_is_committed_but_unauthorized(self):
        with self.assertRaises(reconciliation.PublicationUncertain) as ctx:
            self.call_begin(FaultOps(reopen_name="manifest.json"))
        self.assertTrue(ctx.exception.committed)
        self.assertEqual(len(self.manifest_paths()), 1)

    def test_attempt_replacement_during_publication_is_detected(self):
        root = self.repo / ".factory/items" / self.item_id / "reconciliation"

        def replace_attempt(_src, dst):
            if dst != "manifest.json":
                return
            attempt = next(path for path in root.iterdir()
                           if path.name != "detached")
            detached = root / "detached"
            attempt.rename(detached)
            attempt.mkdir(mode=0o700)

        with self.assertRaises(reconciliation.PublicationUncertain) as ctx:
            self.call_begin(FaultOps(link_hook=replace_attempt))
        self.assertTrue(ctx.exception.committed)
        attempts = [path for path in root.iterdir()
                    if reconciliation._ATTEMPT_RE.fullmatch(path.name)]
        self.assertEqual(len(attempts), 1)
        self.assertFalse((attempts[0] / "manifest.json").exists())
        self.assertTrue((root / "detached/manifest.json").exists())


class ContinuationPublicationTest(ReconciliationFixture):
    def setUp(self):
        super().setUp()
        self.attempt = self.begin()["attempt_id"]
        self.write(self.evidence_paths[0], "partial\n")
        self.result = self.inspect(self.attempt)
        self.attempt_path = (self.repo / ".factory/items" / self.item_id /
                             "reconciliation" / self.attempt)
        self.bind_continuations()

    def bind_continuations(self):
        repo_path, repo_index, chain = reconciliation._open_attempt_chain(
            self.repo, self.item_id, self.attempt)
        try:
            reconciliation._ensure_directory(
                chain, "continuations", repo_path, repo_index, self.attempt)
            reconciliation._bind_continuation_directory(
                chain, repo_path, repo_index, self.attempt)
        finally:
            reconciliation._close_chain(chain)

    def reset_continuations(self):
        continuations = self.attempt_path / "continuations"
        if continuations.exists():
            shutil.rmtree(continuations)
        binding = self.attempt_path / "continuations.json"
        if binding.exists():
            binding.unlink()
        self.bind_continuations()

    def claim(self, ops):
        return reconciliation.claim_continuation(
            self.repo, self.item_id, self.attempt, self.result, _ops=ops)

    def test_claim_directory_and_file_failures_return_no_authorization(self):
        cases = (
            FaultOps(directory_fsync=1),
            FaultOps(regular_fsync=True),
            FaultOps(link_error=True),
        )
        for ops in cases:
            with self.subTest(ops=vars(ops)):
                self.reset_continuations()
                continuations = self.attempt_path / "continuations"
                with self.assertRaises(reconciliation.PublicationUncertain) as ctx:
                    self.claim(ops)
                self.assertFalse(ctx.exception.committed)
                self.assertFalse((continuations / "claim.json").exists())

    def test_claim_commit_boundary_and_cleanup_result_are_exact(self):
        with self.assertRaises(reconciliation.PublicationUncertain) as ctx:
            self.claim(FaultOps(directory_fsync=2))
        self.assertFalse(ctx.exception.committed)
        claim = self.attempt_path / "continuations/claim.json"
        self.assertTrue(claim.exists())
        temps = list(claim.parent.glob(".claim.json.tmp-*"))
        self.assertEqual(len(temps), 1)
        self.assertEqual(claim.stat().st_ino, temps[0].stat().st_ino)

        self.reset_continuations()
        claimed = self.claim(FaultOps(unlink_error=True))
        self.assertEqual(claimed["action"], "continue")
        self.assertTrue(claimed["cleanup_pending"])

    def test_continuations_replacement_after_precheck_is_committed_refusal(self):
        def replace_continuations(_src, dst):
            if dst != "claim.json":
                return
            current = self.attempt_path / "continuations"
            current.rename(self.attempt_path / "continuations-detached")
            current.mkdir(mode=0o700)

        before = len(os.listdir("/dev/fd"))
        with self.assertRaises(reconciliation.PublicationUncertain) as ctx:
            self.claim(FaultOps(link_hook=replace_continuations))
        self.assertTrue(ctx.exception.committed)
        self.assertFalse(
            (self.attempt_path / "continuations/claim.json").exists())
        self.assertTrue(
            (self.attempt_path / "continuations-detached/claim.json").exists())
        self.assertEqual(len(os.listdir("/dev/fd")), before)

    def test_attempt_replacement_during_claim_is_committed_refusal(self):
        detached = self.attempt_path.with_name("attempt-detached")

        def replace_attempt(_src, dst):
            if dst != "claim.json":
                return
            self.attempt_path.rename(detached)
            self.attempt_path.mkdir(mode=0o700)

        before = len(os.listdir("/dev/fd"))
        with self.assertRaises(reconciliation.PublicationUncertain) as ctx:
            self.claim(FaultOps(link_hook=replace_attempt))
        self.assertTrue(ctx.exception.committed)
        self.assertFalse(
            (self.attempt_path / "continuations/claim.json").exists())
        self.assertTrue((detached / "continuations/claim.json").exists())
        self.assertEqual(len(os.listdir("/dev/fd")), before)

    def test_continuations_replacement_during_post_publish_inspection_refuses(self):
        detached = self.attempt_path / "continuations-detached"

        def replace_continuations():
            current = self.attempt_path / "continuations"
            current.rename(detached)
            current.mkdir(mode=0o700)

        with self.assertRaises(reconciliation.PublicationUncertain) as ctx:
            self.claim(FaultOps(post_publish_open_hook=replace_continuations))
        self.assertTrue(ctx.exception.committed)
        self.assertTrue((detached / "claim.json").exists())
        self.assertFalse(
            (self.attempt_path / "continuations/claim.json").exists())

    def test_replaced_continuation_directory_cannot_authorize_again(self):
        first = self.claim(FaultOps())
        self.assertEqual(first["action"], "continue")
        continuations = self.attempt_path / "continuations"
        continuations.rename(self.attempt_path / "continuations-detached")
        continuations.mkdir(mode=0o700)

        with self.assertRaisesRegex(
                reconciliation.ReconciliationError,
                "directory binding"):
            self.claim(FaultOps())
        self.assertFalse((continuations / "claim.json").exists())


class IdentityAndCorruptionTest(ReconciliationFixture):
    def attempt_path(self, attempt):
        return (self.repo / ".factory/items" / self.item_id /
                "reconciliation" / attempt)

    def test_malformed_and_replaced_manifests_stop_or_refuse(self):
        attempt = self.begin()["attempt_id"]
        manifest = self.attempt_path(attempt) / "manifest.json"
        manifest.write_bytes(b"{\n")
        result = self.inspect(attempt)
        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))

        shutil.rmtree(self.attempt_path(attempt).parent)
        attempt = self.begin()["attempt_id"]
        manifest = self.attempt_path(attempt) / "manifest.json"
        raw = manifest.read_bytes()
        replacement = manifest.with_name("replacement")
        replacement.write_bytes(raw)
        os.replace(replacement, manifest)
        result = self.inspect(attempt)
        self.assertEqual(result["action"], "stop")
        self.assertIn("manifest file identity", result["reason"])

        manifest.unlink()
        manifest.symlink_to(self.input_path)
        with self.assertRaises(reconciliation.ReconciliationError):
            self.inspect(attempt)

    def test_copied_attempt_and_replaced_log_are_rejected(self):
        attempt = self.begin()["attempt_id"]
        attempt_path = self.attempt_path(attempt)
        detached = attempt_path.with_name("detached")
        attempt_path.rename(detached)
        shutil.copytree(detached, attempt_path)
        result = self.inspect(attempt)
        self.assertEqual(result["action"], "stop")
        self.assertIn("attempt directory identity", result["reason"])

        shutil.rmtree(attempt_path.parent)
        attempt = self.begin()["attempt_id"]
        log_path = self.repo / ".factory/items" / self.item_id / "log.jsonl"
        replacement = log_path.with_name("log.copy")
        replacement.write_bytes(log_path.read_bytes())
        os.replace(replacement, log_path)
        result = self.inspect(attempt)
        self.assertEqual(result["action"], "stop")
        self.assertIn("identity changed without an append", result["reason"])

    def test_truncated_prefix_and_malformed_complete_suffix_stop(self):
        attempt = self.begin()["attempt_id"]
        log_path = self.repo / ".factory/items" / self.item_id / "log.jsonl"
        raw = log_path.read_bytes()
        log_path.write_bytes(raw[:-1])
        result = self.inspect(attempt)
        self.assertEqual(result["action"], "stop")
        self.assertIn("pinned event log prefix", result["reason"])

        log_path.write_bytes(raw)
        shutil.rmtree(self.attempt_path(attempt).parent)
        attempt = self.begin()["attempt_id"]
        with log_path.open("ab") as stream:
            stream.write(b"not-json\n")
        active = self.inspect(attempt, "active")
        terminal = self.inspect(attempt, "terminal")
        self.assertEqual(active["action"], "stop")
        self.assertIn("pinned event log prefix", active["reason"])
        self.assertEqual(terminal["action"], "stop")

    def test_inspection_refuses_when_visible_state_cannot_be_made_durable(self):
        class ObservationFailOps(reconciliation.FilesystemOps):
            def sync_observation(self, fd):
                raise OSError("injected observation durability failure")

        attempt = self.begin()["attempt_id"]
        self.write(self.evidence_paths[0], "partial\n")

        result = reconciliation.inspect(
            self.repo, self.item_id, attempt, "terminal",
            _ops=ObservationFailOps())

        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))
        self.assertIn("could not be made durable", result["reason"])

    def test_parent_symlinked_evidence_is_never_followed(self):
        attempt = self.begin()["attempt_id"]
        reviews = self.repo / ".factory/items" / self.item_id / "reviews"
        outside = self.repo / "outside-reviews"
        outside.mkdir()
        reviews.symlink_to(outside, target_is_directory=True)
        result = self.inspect(attempt)
        self.assertEqual((result["classification"], result["action"]),
                         ("contradictory", "stop"))

    def test_chain_validation_is_bottom_up(self):
        class ReplacingAncestorOps:
            detached = False

            def fstat(self, fd):
                return type("Stat", (), {
                    "st_dev": 1, "st_ino": fd,
                    "st_mode": stat.S_IFDIR | 0o700,
                })()

            def stat(self, path, *, dir_fd=None, follow_symlinks=True):
                if path == "attempt":
                    self.detached = True
                inode = {"/repo": 1, ".factory": 2, "attempt": 3}[path]
                if path == ".factory" and self.detached:
                    inode = 99
                return type("Stat", (), {
                    "st_dev": 1, "st_ino": inode,
                    "st_mode": stat.S_IFDIR | 0o700,
                })()

        chain = [
            reconciliation._Handle(1, None, (1, 1)),
            reconciliation._Handle(2, ".factory", (1, 2)),
            reconciliation._Handle(3, "attempt", (1, 3)),
        ]
        with self.assertRaises(reconciliation.ReconciliationError):
            reconciliation._validate_chain(
                chain, Path("/repo"), 0, ReplacingAncestorOps())

    def test_post_open_disappearance_is_not_reported_as_absent(self):
        class DisappearingLeafOps:
            def open(self, path, flags, mode=0o777, *, dir_fd=None):
                return 2

            def fstat(self, fd):
                mode = stat.S_IFDIR if fd == 1 else stat.S_IFREG
                return type("Stat", (), {
                    "st_dev": 1, "st_ino": fd, "st_mode": mode | 0o600,
                    "st_size": 0, "st_mtime_ns": 0, "st_ctime_ns": 0,
                })()

            def read(self, fd, size):
                return b""

            def stat(self, path, *, dir_fd=None, follow_symlinks=True):
                raise FileNotFoundError("leaf removed after it was opened")

            def close(self, fd):
                pass

        chain = [reconciliation._Handle(1, None, (1, 1))]
        with self.assertRaises(reconciliation.ReconciliationError):
            reconciliation._secure_read_from(
                chain, Path("/repo"), 0, "evidence", missing_ok=True,
                ops=DisappearingLeafOps())

    @unittest.skipUnless(hasattr(os, "O_NONBLOCK"), "requires O_NONBLOCK")
    def test_unvalidated_read_leaves_are_opened_nonblocking(self):
        class FlagCheckingOps:
            def open(self, path, flags, mode=0o777, *, dir_fd=None):
                if not flags & os.O_NONBLOCK:
                    raise AssertionError("leaf open could block on a FIFO")
                return 2

            def fstat(self, fd):
                mode = stat.S_IFDIR if fd == 1 else stat.S_IFREG
                return type("Stat", (), {
                    "st_dev": 1, "st_ino": fd,
                    "st_mode": mode | 0o600,
                    "st_size": 0, "st_mtime_ns": 0, "st_ctime_ns": 0,
                })()

            def read(self, fd, size):
                return b""

            def stat(self, path, *, dir_fd=None, follow_symlinks=True):
                if path == "/repo":
                    return type("Stat", (), {
                        "st_dev": 1, "st_ino": 1,
                        "st_mode": stat.S_IFDIR | 0o700,
                    })()
                return self.fstat(2)

            def close(self, fd):
                pass

        ops = FlagCheckingOps()
        chain = [reconciliation._Handle(1, None, (1, 1))]
        reconciliation._secure_read_from(
            chain, Path("/repo"), 0, "evidence", ops=ops)
        reconciliation._secure_read_named(
            chain, Path("/repo"), 0, "manifest.json", ops=ops)


if __name__ == "__main__":
    unittest.main()
