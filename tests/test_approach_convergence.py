import fcntl
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.factory import factory
from scripts.factory.lib import initrepo, items, logs, machine, paths
from scripts.factory.lib.validate import validate

ITEM = "0001-thing"
SIGNALS = (
    "natural-language-rule-tail",
    "input-variety-task-growth",
    "unconstrained-output-postprocess",
)


class ConvergenceCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = "2026-09-04T12:00:00Z"
        initrepo.init(self.repo)

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def configure(self, enabled):
        path = paths.config_path(self.repo)
        config = json.loads(path.read_text(encoding="utf-8"))
        config["approach_convergence"] = {"enabled": enabled}
        path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")

    def make_plan_item(self, tier="feature",
                       plan="- [ ] implement the bounded change\n"):
        now = logs.now_stamp()
        meta = {"id": ITEM, "title": "Thing", "stage": "idea",
                "kind": "backend", "tier": tier,
                "created": now, "updated": now}
        items.save_item(self.repo, meta, "# Thing\n")
        machine.advance(self.repo, ITEM, "triage")
        item_dir = paths.item_dir(self.repo, ITEM)
        (item_dir / "triage.md").write_text("build\n", encoding="utf-8")
        items.set_priority(self.repo, ITEM, 1)
        machine.advance(self.repo, ITEM, "spec")
        (item_dir / "spec.md").write_text(
            "# Spec\n\n## Journey impact\nJ-005.\n", encoding="utf-8")
        items.set_journeys(self.repo, ITEM, "J-005")
        machine.advance(self.repo, ITEM, "plan")
        (item_dir / "plan.md").write_text(plan, encoding="utf-8")
        return item_dir

    def context(self):
        from scripts.factory.lib import convergence
        return convergence.current_context(self.repo, ITEM)

    def record(self, signals=(), attempts=(), final_verdict=None,
               disposition=None, tier=None):
        context = self.context()
        signal_rows = [{
            "id": signal,
            "evidence": [{
                "path": f".factory/items/{ITEM}/plan.md",
                "start_line": 1,
                "end_line": 1,
            }],
        } for signal in signals]
        if final_verdict is None:
            final_verdict = "not-triggered" if not signals else "pass"
        if disposition is None:
            disposition = "advance"
        return {
            "version": 1,
            "item": ITEM,
            "planning_round": context["planning_round"],
            "plan_sha256": context["plan_sha256"],
            "configuration": {"enabled": True},
            "tier": tier or context["tier"],
            "planner_invocation": "planner-001",
            "signals": signal_rows,
            "attempts": list(attempts),
            "final_verdict": final_verdict,
            "disposition": disposition,
            "escalation_count": max(0, len(attempts) - 1),
            "escalation_bound": context["escalation_bound"],
        }

    def attempt(self, number, verdict="pass", invocation=None,
                conflict=False, path=None, start=1, end=1):
        return {
            "attempt": number,
            "invocation": invocation or f"reviewer-{number:03d}",
            "timestamp": "2026-09-04T12:00:00Z",
            "verdict": verdict,
            "evidence_conflict": conflict,
            "findings": [{
                "claim": f"attempt {number} evidence",
                "path": path or f".factory/items/{ITEM}/plan.md",
                "start_line": start,
                "end_line": end,
            }],
        }

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(self.repo), *argv])
        return code, out.getvalue(), err.getvalue()


class TestApproachSchemaAndConfig(ConvergenceCase):
    def test_default_is_explicitly_disabled_and_valid(self):
        self.assertEqual(
            initrepo.DEFAULT_CONFIG["approach_convergence"],
            {"enabled": False})
        config = json.loads(paths.config_path(self.repo).read_text(
            encoding="utf-8"))
        self.assertEqual(config["approach_convergence"], {"enabled": False})
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_config_accepts_true_and_rejects_unknown_members(self):
        self.configure(True)
        self.assertEqual(initrepo.validate_tree(self.repo), [])
        path = paths.config_path(self.repo)
        config = json.loads(path.read_text(encoding="utf-8"))
        config["approach_convergence"]["mode"] = "automatic"
        path.write_text(json.dumps(config), encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("config.approach_convergence.mode: unexpected property",
                      errors[0])

    def test_judgement_schema_is_closed_and_names_every_enum(self):
        schema = initrepo.load_schema("approach-judgement")
        self.assertFalse(schema["additionalProperties"])
        props = schema["properties"]
        self.assertEqual(props["signals"]["items"]["properties"]["id"]["enum"],
                         list(SIGNALS))
        self.assertEqual(props["attempts"]["items"]["properties"]["verdict"]["enum"],
                         ["pass", "reject", "uncertain"])
        self.assertEqual(props["final_verdict"]["enum"],
                         ["not-triggered", "pass", "reject", "uncertain"])
        self.assertEqual(props["disposition"]["enum"],
                         ["advance", "escalate", "approach.rejected"])
        self.assertTrue(validate({"version": 1}, schema, "judgement"))


class TestApproachContext(ConvergenceCase):
    def test_context_is_engine_round_exact_hash_and_tier_bound(self):
        from scripts.factory.lib import convergence
        self.configure(True)
        item_dir = self.make_plan_item(tier="feature", plan="- [ ] alpha\n")
        context = convergence.current_context(self.repo, ITEM)
        self.assertEqual(context["item"], ITEM)
        self.assertEqual(context["planning_round"], "plan-0001")
        self.assertEqual(
            context["plan_sha256"],
            __import__("hashlib").sha256(
                (item_dir / "plan.md").read_bytes()).hexdigest())
        self.assertEqual(context["tier"], "feature")
        self.assertEqual(context["escalation_bound"], 1)
        self.assertTrue(context["enabled"])
        self.assertEqual(
            context["record"],
            ".factory/items/0001-thing/approach-judgements/"
            "plan-0001-" + context["plan_sha256"] + ".json")

    def test_bug_has_zero_escalation_but_still_has_context(self):
        from scripts.factory.lib import convergence
        self.configure(True)
        self.make_plan_item(tier="bug")
        context = convergence.current_context(self.repo, ITEM)
        self.assertEqual(context["tier"], "bug")
        self.assertEqual(context["escalation_bound"], 0)

    def test_plan_edit_changes_hash_without_changing_round(self):
        from scripts.factory.lib import convergence
        self.configure(True)
        item_dir = self.make_plan_item(plan="- [ ] first\n")
        first = convergence.current_context(self.repo, ITEM)
        (item_dir / "plan.md").write_text("- [ ] second\n", encoding="utf-8")
        second = convergence.current_context(self.repo, ITEM)
        self.assertEqual(second["planning_round"], first["planning_round"])
        self.assertNotEqual(second["plan_sha256"], first["plan_sha256"])
        self.assertNotEqual(second["record"], first["record"])

    def test_special_resume_does_not_create_a_round(self):
        from scripts.factory.lib import convergence
        self.configure(True)
        self.make_plan_item()
        before = convergence.current_context(self.repo, ITEM)
        machine.advance(self.repo, ITEM, "waiting-human", reason="interrupt")
        machine.advance(self.repo, ITEM, "plan")
        after = convergence.current_context(self.repo, ITEM)
        self.assertEqual(after["planning_round"], before["planning_round"])
        self.assertEqual(after["plan_sha256"], before["plan_sha256"])

    def test_new_non_special_entry_creates_a_new_round(self):
        from scripts.factory.lib import convergence
        self.configure(True)
        item_dir = self.make_plan_item()
        first = convergence.current_context(self.repo, ITEM)
        (item_dir / "approaches" / "forbidden.md").parent.mkdir(
            parents=True, exist_ok=True)
        (item_dir / "approaches" / "forbidden.md").write_text(
            "## rejected at plan\n\nEvidence: plan.md\n", encoding="utf-8")
        machine.advance(self.repo, ITEM, "spec",
                        reason="approach.rejected: cannot converge")
        (item_dir / "spec.md").write_text(
            "# Revised\n\n## Journey impact\nJ-005.\n", encoding="utf-8")
        logs.append_event(self.repo, ITEM, "spec.revised")
        machine.advance(self.repo, ITEM, "plan")
        second = convergence.current_context(self.repo, ITEM)
        self.assertEqual(first["planning_round"], "plan-0001")
        self.assertEqual(second["planning_round"], "plan-0002")

    def test_context_fails_closed_without_engine_plan_entry(self):
        from scripts.factory.lib import convergence
        self.configure(True)
        now = logs.now_stamp()
        items.save_item(self.repo, {
            "id": ITEM, "title": "Thing", "stage": "plan",
            "kind": "backend", "created": now, "updated": now}, "# Thing\n")
        item_dir = paths.item_dir(self.repo, ITEM)
        (item_dir / "plan.md").write_text("- [ ] task\n", encoding="utf-8")
        with self.assertRaises(convergence.ConvergenceError) as ctx:
            convergence.current_context(self.repo, ITEM)
        self.assertIn("no non-special engine entry into plan", str(ctx.exception))

    def test_planning_round_ignores_malformed_or_unknown_origins(self):
        from scripts.factory.lib import convergence
        cases = (
            ("missing", None),
            ("numeric-data", 1),
            ("list-data", []),
            ("missing-origin", {"to": "plan"}),
            ("none-origin", {"from": None, "to": "plan"}),
            ("numeric-origin", {"from": 1, "to": "plan"}),
            ("list-origin", {"from": [], "to": "plan"}),
            ("dict-origin", {"from": {}, "to": "plan"}),
            ("unknown-origin", {"from": "review", "to": "plan"}),
        )
        for label, data in cases:
            with self.subTest(label=label):
                self.tearDown()
                self.setUp()
                self.make_plan_item()
                logs.append_event(self.repo, ITEM, "stage.advance", data)
                self.assertEqual(
                    convergence.planning_round(self.repo, ITEM), "plan-0001")

    def test_planning_round_counts_only_spec_and_design_origins(self):
        from scripts.factory.lib import convergence
        self.make_plan_item()
        for origin in ("design", "spec", "waiting-human", "blocked", "review"):
            logs.append_event(self.repo, ITEM, "stage.advance",
                              {"from": origin, "to": "plan"})
        self.assertEqual(convergence.planning_round(self.repo, ITEM),
                         "plan-0003")


class TestApproachRecordValidation(ConvergenceCase):
    def setUp(self):
        super().setUp()
        self.configure(True)
        self.make_plan_item(plan="- [ ] bounded task\n")

    def assert_invalid(self, record, fragment):
        from scripts.factory.lib import convergence
        meta, _ = items.load_item(self.repo, ITEM)
        with self.assertRaises(convergence.ConvergenceError) as ctx:
            convergence.validate_current(self.repo, meta, record)
        self.assertIn(fragment, str(ctx.exception))

    def test_no_signal_and_one_pass_shapes_validate(self):
        from scripts.factory.lib import convergence
        meta, _ = items.load_item(self.repo, ITEM)
        no_signal = self.record()
        self.assertIs(convergence.validate_current(
            self.repo, meta, no_signal), no_signal)
        passed = self.record(
            signals=(SIGNALS[0],), attempts=(self.attempt(1),))
        self.assertIs(convergence.validate_current(
            self.repo, meta, passed), passed)

    def test_schema_is_closed_and_unknown_enums_are_distinct(self):
        extra = self.record()
        extra["surprise"] = True
        self.assert_invalid(extra, "judgement.surprise: unexpected property")
        signal = self.record(signals=(SIGNALS[0],),
                             attempts=(self.attempt(1),))
        signal["signals"][0]["id"] = "free-form-smell"
        self.assert_invalid(signal, "not one of")

    def test_wrong_item_round_hash_tier_and_bound_are_distinct(self):
        cases = (
            ("item", "0002-other", "wrong item"),
            ("planning_round", "plan-9999", "stale planning round"),
            ("plan_sha256", "0" * 64, "stale plan hash"),
            ("tier", "bug", "tier context stale"),
            ("escalation_bound", 0, "escalation bound stale"),
        )
        for key, value, fragment in cases:
            with self.subTest(key=key):
                record = self.record()
                record[key] = value
                self.assert_invalid(record, fragment)

    def test_signal_citation_must_name_current_plan(self):
        record = self.record(signals=(SIGNALS[0],),
                             attempts=(self.attempt(1),))
        record["signals"][0]["evidence"][0]["path"] = "README.md"
        self.assert_invalid(record, "must cite the current plan")

    def test_citation_missing_empty_escape_and_range_errors_are_distinct(self):
        cases = []
        missing = self.record(signals=(SIGNALS[0],),
                              attempts=(self.attempt(1),))
        missing["attempts"][0]["findings"][0]["path"] = "missing.md"
        cases.append((missing, "citation path missing"))
        empty_path = paths.item_dir(self.repo, ITEM) / "empty.md"
        empty_path.write_text("   \n", encoding="utf-8")
        empty = self.record(signals=(SIGNALS[0],), attempts=(
            self.attempt(1, path=f".factory/items/{ITEM}/empty.md"),))
        cases.append((empty, "citation range is empty"))
        escaped = self.record(signals=(SIGNALS[0],), attempts=(
            self.attempt(1, path="../outside.md"),))
        cases.append((escaped, "citation escapes the repository"))
        ranged = self.record(signals=(SIGNALS[0],), attempts=(
            self.attempt(1, end=9),))
        cases.append((ranged, "citation range out of range"))
        reversed_range = self.record(signals=(SIGNALS[0],), attempts=(
            self.attempt(1, start=2, end=1),))
        cases.append((reversed_range, "citation start exceeds end"))
        for record, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assert_invalid(record, fragment)

    def test_citation_symlink_targets_must_remain_within_repository(self):
        from scripts.factory.lib import convergence
        meta, _ = items.load_item(self.repo, ITEM)
        inside = self.repo / "inside.md"
        inside.write_text("inside\n", encoding="utf-8")
        (self.repo / "in-repo-link.md").symlink_to("inside.md")
        valid = self.record(signals=(SIGNALS[0],), attempts=(
            self.attempt(1, path="in-repo-link.md"),))
        self.assertIs(convergence.validate_current(self.repo, meta, valid), valid)
        with tempfile.TemporaryDirectory() as outside_root:
            outside = Path(outside_root)
            (outside / "outside.md").write_text("outside\n", encoding="utf-8")
            (self.repo / "file-link.md").symlink_to(outside / "outside.md")
            (outside / "directory").mkdir()
            (outside / "directory" / "nested.md").write_text(
                "outside nested\n", encoding="utf-8")
            (self.repo / "directory-link").symlink_to(
                outside / "directory", target_is_directory=True)
            cases = (
                ("file-link.md", "direct file symlink"),
                ("directory-link/nested.md", "directory symlink"),
            )
            for path, label in cases:
                with self.subTest(label=label):
                    escaped = self.record(signals=(SIGNALS[0],), attempts=(
                        self.attempt(1, path=path),))
                    self.assert_invalid(escaped, "citation escapes the repository")

    def test_producer_and_reviewer_invocations_must_be_fresh(self):
        same = self.record(signals=(SIGNALS[0],), attempts=(
            self.attempt(1, invocation="planner-001"),))
        self.assert_invalid(same, "matches planner invocation")
        reused = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"),
                      self.attempt(2, invocation="reviewer-001")),
            final_verdict="pass")
        self.assert_invalid(reused, "reviewer invocation reused")

    def test_attempt_numbers_counts_and_bounds_are_enforced(self):
        numbered = self.record(signals=(SIGNALS[0],), attempts=(
            self.attempt(2),))
        self.assert_invalid(numbered, "attempt numbers must be [1]")
        over = self.record(signals=(SIGNALS[0],), attempts=(
            self.attempt(1, verdict="uncertain"), self.attempt(2),
            self.attempt(3)), final_verdict="pass")
        self.assert_invalid(over, "attempt count 3 exceeds resolved maximum 2")
        count = self.record(signals=(SIGNALS[0],), attempts=(self.attempt(1),))
        count["escalation_count"] = 1
        self.assert_invalid(count, "escalation_count 1 does not match 0")

    def test_only_uncertainty_or_conflict_can_open_second_attempt(self):
        record = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1), self.attempt(2)),
            final_verdict="pass")
        self.assert_invalid(record, "first attempt did not authorize escalation")

    def test_disposition_matrix_is_exact(self):
        rows = (
            ((self.attempt(1, verdict="uncertain"),),
             "uncertain", "escalate", None),
            ((self.attempt(1, verdict="pass", conflict=True),),
             "uncertain", "escalate", None),
            ((self.attempt(1, verdict="reject"),),
             "reject", "approach.rejected", None),
            ((self.attempt(1, verdict="uncertain"), self.attempt(2)),
             "pass", "advance", None),
            ((self.attempt(1, verdict="uncertain"),
              self.attempt(2, verdict="reject")),
             "reject", "approach.rejected", None),
            ((self.attempt(1, verdict="uncertain"),
              self.attempt(2, verdict="uncertain")),
             "uncertain", "approach.rejected", None),
        )
        from scripts.factory.lib import convergence
        meta, _ = items.load_item(self.repo, ITEM)
        for attempts, verdict, disposition, _ in rows:
            with self.subTest(verdict=verdict, disposition=disposition):
                record = self.record(signals=(SIGNALS[0],), attempts=attempts,
                                     final_verdict=verdict,
                                     disposition=disposition)
                self.assertIs(convergence.validate_current(
                    self.repo, meta, record), record)

    def test_bug_uncertainty_exhausts_without_second_attempt(self):
        from scripts.factory.lib import convergence
        self.tmp.cleanup()
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        self.configure(True)
        self.make_plan_item(tier="bug")
        meta, _ = items.load_item(self.repo, ITEM)
        record = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"),),
            final_verdict="uncertain", disposition="approach.rejected")
        self.assertIs(convergence.validate_current(
            self.repo, meta, record), record)

    def test_empty_signal_evidence_and_empty_findings_are_refused(self):
        signal = self.record(signals=(SIGNALS[0],),
                             attempts=(self.attempt(1),))
        signal["signals"][0]["evidence"] = []
        self.assert_invalid(signal, "has no plan citations")
        findings = self.record(signals=(SIGNALS[0],),
                               attempts=(self.attempt(1),))
        findings["attempts"][0]["findings"] = []
        self.assert_invalid(findings, "has no cited findings")


class TestApproachRecordWriter(ConvergenceCase):
    def setUp(self):
        super().setUp()
        self.configure(True)
        self.make_plan_item()

    def test_created_judgement_directory_swap_preserves_replacement(self):
        from scripts.factory.lib import convergence
        record = self.record()
        record["unexpected"] = True
        item_dir = paths.item_dir(self.repo, ITEM)
        canonical = item_dir / "approach-judgements"
        detached = item_dir / "writer-created-detached"
        original_open = os.open
        swapped = False

        def swap_created_directory(name, flags, *args, **kwargs):
            nonlocal swapped
            if name == "approach-judgements" and not swapped:
                canonical.rename(detached)
                canonical.mkdir()
                swapped = True
            return original_open(name, flags, *args, **kwargs)

        with mock.patch.object(os, "open", side_effect=swap_created_directory):
            with self.assertRaises(convergence.ConvergenceError):
                convergence.record_judgement(self.repo, ITEM, record)

        self.assertTrue(swapped)
        self.assertTrue(
            canonical.exists(), "cleanup deleted the unrelated replacement")
        self.assertFalse(
            detached.exists(), "cleanup retained the writer-created directory")
        self.assertEqual(logs.count_events(
            self.repo, ITEM, "approach.judgement.recorded"), 0)
        with self.assertRaisesRegex(machine.GateError, "judgement missing"):
            machine.advance(self.repo, ITEM, "implement")

    def test_initial_temp_cleanup_failure_rolls_back_record_and_audit(self):
        from scripts.factory.lib import convergence
        record = self.record()
        canonical = self.repo / self.context()["record"]
        original_unlink = os.unlink
        injected = False

        def fail_first_temp_cleanup(name, *args, **kwargs):
            nonlocal injected
            if str(name).endswith(".tmp") and not injected:
                injected = True
                raise OSError("injected temp cleanup failure")
            return original_unlink(name, *args, **kwargs)

        with mock.patch.object(os, "unlink", side_effect=fail_first_temp_cleanup):
            with self.assertRaisesRegex(OSError, "temp cleanup failure"):
                convergence.record_judgement(self.repo, ITEM, record)

        self.assertTrue(injected)
        self.assertFalse(canonical.exists())
        self.assertFalse(list(canonical.parent.glob("*.tmp")))
        self.assertEqual(logs.count_events(
            self.repo, ITEM, "approach.judgement.recorded"), 0)
        with self.assertRaisesRegex(machine.GateError, "judgement missing"):
            machine.advance(self.repo, ITEM, "implement")

    def test_update_backup_cleanup_failure_restores_prior_record_and_audit(self):
        from scripts.factory.lib import convergence
        first = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"),),
            final_verdict="uncertain", disposition="escalate")
        canonical = convergence.record_judgement(self.repo, ITEM, first)
        before = canonical.read_bytes()
        second = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"), self.attempt(2)),
            final_verdict="pass", disposition="advance")
        original_unlink = os.unlink
        injected = False

        def fail_first_backup_cleanup(name, *args, **kwargs):
            nonlocal injected
            if str(name).endswith(".previous") and not injected:
                injected = True
                raise OSError("injected backup cleanup failure")
            return original_unlink(name, *args, **kwargs)

        with mock.patch.object(os, "unlink", side_effect=fail_first_backup_cleanup):
            with self.assertRaisesRegex(OSError, "backup cleanup failure"):
                convergence.record_judgement(self.repo, ITEM, second)

        self.assertTrue(injected)
        self.assertEqual(canonical.read_bytes(), before)
        self.assertFalse(list(canonical.parent.glob("*.previous")))
        self.assertEqual(logs.count_events(
            self.repo, ITEM, "approach.judgement.recorded"), 1)

    def test_interrupt_after_initial_link_rolls_back_uncommitted_record(self):
        from scripts.factory.lib import convergence
        record = self.record()
        canonical = self.repo / self.context()["record"]
        original_link = os.link

        def link_then_interrupt(source, target, *args, **kwargs):
            result = original_link(source, target, *args, **kwargs)
            if target == canonical.name:
                raise KeyboardInterrupt("injected after initial link")
            return result

        with mock.patch.object(os, "link", side_effect=link_then_interrupt):
            with self.assertRaisesRegex(KeyboardInterrupt, "initial link"):
                convergence.record_judgement(self.repo, ITEM, record)

        self.assertFalse(canonical.exists())
        self.assertFalse(list(canonical.parent.glob("*.tmp")))
        self.assertEqual(logs.count_events(
            self.repo, ITEM, "approach.judgement.recorded"), 0)
        with self.assertRaisesRegex(machine.GateError, "judgement missing"):
            machine.advance(self.repo, ITEM, "implement")

    def test_interrupt_after_update_replace_restores_prior_record(self):
        from scripts.factory.lib import convergence
        first = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"),),
            final_verdict="uncertain", disposition="escalate")
        canonical = convergence.record_judgement(self.repo, ITEM, first)
        before = canonical.read_bytes()
        second = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"), self.attempt(2)),
            final_verdict="pass", disposition="advance")
        original_replace = os.replace
        injected = False

        def replace_then_interrupt(source, target, *args, **kwargs):
            nonlocal injected
            result = original_replace(source, target, *args, **kwargs)
            if target == canonical.name and not injected:
                injected = True
                raise KeyboardInterrupt("injected after update replace")
            return result

        with mock.patch.object(os, "replace", side_effect=replace_then_interrupt):
            with self.assertRaisesRegex(KeyboardInterrupt, "update replace"):
                convergence.record_judgement(self.repo, ITEM, second)

        self.assertTrue(injected)
        self.assertEqual(canonical.read_bytes(), before)
        self.assertFalse(list(canonical.parent.glob("*.previous")))
        self.assertEqual(logs.count_events(
            self.repo, ITEM, "approach.judgement.recorded"), 1)

    def test_log_concurrent_append_is_preserved(self):
        from scripts.factory.lib import convergence
        record = self.record()
        original_append = logs.append_event

        def interleaved_append(*args, **kwargs):
            original_append(self.repo, ITEM, "concurrent.sentinel")
            fd = kwargs["file_fd"]
            self.assertTrue(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_APPEND)
            os.lseek(fd, 0, os.SEEK_SET)
            return original_append(*args, **kwargs)

        with mock.patch.object(logs, "append_event", side_effect=interleaved_append):
            convergence.record_judgement(self.repo, ITEM, record)
        events = logs.read_events(self.repo, ITEM)
        self.assertEqual(sum(e["event"] == "concurrent.sentinel" for e in events),
                         1, "concurrent append was overwritten")
        self.assertEqual(sum(e["event"] == "approach.judgement.recorded"
                             for e in events), 1)

    def test_successful_cli_append_survives_later_judgement_refusal(self):
        record = self.record()
        item_dir = paths.item_dir(self.repo, ITEM)
        log = item_dir / "log.jsonl"
        directory = item_dir / "approach-judgements"
        original_append = logs.append_event
        original_sync = os.fsync
        for failure in ("directory", "log", "sync"):
            with self.subTest(failure=failure):
                before = log.read_bytes() + b"\xff preexisting bytes\n"
                log.write_bytes(before)
                sentinel_bytes = b""
                fail_sync = False
                with log.open("rb") as pinned:
                    def append_then_refuse(*args, **kwargs):
                        nonlocal sentinel_bytes, fail_sync
                        result = original_append(*args, **kwargs)
                        offset = log.stat().st_size
                        child = subprocess.run(
                            [sys.executable, factory.__file__, "--repo", str(self.repo),
                             "log", ITEM, "concurrent.sentinel"],
                            capture_output=True, text=True, timeout=10)
                        self.assertEqual(child.returncode, 0, child.stderr)
                        sentinel_bytes = log.read_bytes()[offset:]
                        self.assertEqual(json.loads(sentinel_bytes)["event"],
                                         "concurrent.sentinel")
                        if failure == "directory":
                            directory.rename(item_dir / "detached-judgements")
                            directory.mkdir()
                        elif failure == "log":
                            log.rename(item_dir / "detached-log")
                            log.write_bytes(b"replacement must remain unchanged\n")
                        else:
                            fail_sync = True
                        return result

                    def sync(fd):
                        nonlocal fail_sync
                        if fail_sync:
                            fail_sync = False
                            raise OSError("injected sync failure")
                        return original_sync(fd)

                    with mock.patch.object(logs, "append_event", side_effect=append_then_refuse), \
                            mock.patch.object(os, "fsync", side_effect=sync):
                        if failure == "sync":
                            with self.assertRaisesRegex(OSError, "injected sync failure"):
                                self.run_cli("approach-judgement", ITEM,
                                             "--data", json.dumps(record))
                        else:
                            code, _out, err = self.run_cli(
                                "approach-judgement", ITEM, "--data", json.dumps(record))
                            self.assertEqual(code, 2, err)
                            self.assertIn("replaced", err)
                    actual = pinned.read()
                if failure == "log":
                    self.assertEqual(log.read_bytes(), b"replacement must remain unchanged\n")
                    log.unlink()
                    (item_dir / "detached-log").rename(log)
                self.assertEqual(actual, before + sentinel_bytes)
                self.assertEqual(actual[len(before):].count(b'"concurrent.sentinel"'), 1)
                self.assertNotIn(b'"approach.judgement.recorded"', actual)

    def test_log_replacement_inside_append_restores_pinned_inode(self):
        record = self.record()
        log = paths.item_dir(self.repo, ITEM) / "log.jsonl"
        # Retain malformed and non-UTF8 bytes too: rollback is byte-exact.
        with log.open("ab") as stream:
            stream.write(b"\xff sentinel\n")
        before = log.read_bytes()
        original_append = logs.append_event
        for operation in ("rename", "unlink"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                detached = Path(tmp) / "detached.jsonl"
                with log.open("rb") as pinned:
                    def moved_append(*args, **kwargs):
                        if operation == "rename":
                            log.rename(detached)
                        else:
                            log.unlink()
                        log.write_bytes(before)
                        result = original_append(*args, **kwargs)
                        observed = os.pread(pinned.fileno(), 100000, 0)
                        self.assertEqual(observed[:len(before)], before)
                        appended = json.loads(observed[len(before):])
                        self.assertEqual(appended["event"], "approach.judgement.recorded")
                        return result

                    with mock.patch.object(logs, "append_event", side_effect=moved_append):
                        code, _out, err = self.run_cli(
                            "approach-judgement", ITEM, "--data", json.dumps(record))
                    self.assertEqual(code, 2, err)
                    self.assertIn("replaced log.jsonl", err)
                    self.assertEqual(log.read_bytes(), before)
                    self.assertEqual(os.fstat(pinned.fileno()).st_size, len(before))
                    self.assertEqual(pinned.read(), before)
                    if operation == "rename":
                        self.assertEqual(detached.read_bytes(), before)
        for _ in range(2):
            code, _out, err = self.run_cli(
                "approach-judgement", ITEM, "--data", json.dumps(record))
            self.assertEqual(code, 0, err)
        self.assertEqual(logs.count_events(
            self.repo, ITEM, "approach.judgement.recorded"), 1)

    def test_append_io_failure_restores_bytes_and_retry(self):
        record = self.record()
        log = paths.item_dir(self.repo, ITEM) / "log.jsonl"
        before = log.read_bytes()

        original_write = os.write
        wrote_partial = False

        def partial_write(fd, payload):
            nonlocal wrote_partial
            if wrote_partial:
                raise OSError("injected append failure")
            wrote_partial = True
            return original_write(fd, payload[:10])

        with mock.patch.object(os, "write", side_effect=partial_write):
            with self.assertRaisesRegex(OSError, "injected append failure"):
                self.run_cli("approach-judgement", ITEM, "--data", json.dumps(record))
        self.assertEqual(log.read_bytes(), before)
        code, _out, err = self.run_cli(
            "approach-judgement", ITEM, "--data", json.dumps(record))
        self.assertEqual(code, 0, err)
        self.assertEqual(logs.count_events(
            self.repo, ITEM, "approach.judgement.recorded"), 1)

    def test_append_sync_failure_rolls_back_and_reports_failed_recovery(self):
        record = self.record()
        log = paths.item_dir(self.repo, ITEM) / "log.jsonl"
        before = log.read_bytes()
        with mock.patch.object(os, "fsync", side_effect=OSError("sync failed")):
            code, _out, err = self.run_cli(
                "approach-judgement", ITEM, "--data", json.dumps(record))
        self.assertEqual(code, 2, err)
        self.assertIn("audit log rollback failed", err)
        self.assertEqual(log.read_bytes(), before)

    def test_truncate_failure_reports_unrestored_inode(self):
        record = self.record()
        log = paths.item_dir(self.repo, ITEM) / "log.jsonl"
        before = log.read_bytes()
        original_append = logs.append_event

        def failed_append(*args, **kwargs):
            original_append(*args, **kwargs)
            raise OSError("append failed after flush")

        with mock.patch.object(logs, "append_event", side_effect=failed_append), \
                mock.patch.object(os, "ftruncate", side_effect=OSError("truncate failed")):
            code, _out, err = self.run_cli(
                "approach-judgement", ITEM, "--data", json.dumps(record))
        self.assertEqual(code, 2, err)
        self.assertIn("audit log rollback failed", err)
        self.assertIn("truncate failed", err)
        self.assertIn("append failed after flush", err)
        self.assertGreater(log.stat().st_size, len(before))

    def test_log_swap_at_final_verification_rolls_back(self):
        record = self.record()
        log = paths.item_dir(self.repo, ITEM) / "log.jsonl"
        before = log.read_bytes()
        original_stat = os.stat
        original_append = logs.append_event
        appended = False
        checks = 0
        with tempfile.TemporaryDirectory() as tmp:
            detached = Path(tmp) / "detached.jsonl"

            def appended_event(*args, **kwargs):
                nonlocal appended
                result = original_append(*args, **kwargs)
                appended = True
                return result

            def swap_on_final_check(path, *args, **kwargs):
                nonlocal checks
                if appended and path == "log.jsonl":
                    checks += 1
                    if checks == 2:
                        log.rename(detached)
                        log.write_bytes(before)
                        logs.append_event(self.repo, ITEM, "concurrent.sentinel")
                return original_stat(path, *args, **kwargs)

            with mock.patch.object(logs, "append_event", side_effect=appended_event), \
                    mock.patch.object(os, "stat", side_effect=swap_on_final_check):
                code, _out, err = self.run_cli(
                    "approach-judgement", ITEM, "--data", json.dumps(record))
            self.assertEqual(code, 2, err)
            self.assertEqual(detached.read_bytes(), before)
            self.assertEqual(logs.count_events(self.repo, ITEM, "concurrent.sentinel"), 1)
            self.assertEqual(logs.count_events(
                self.repo, ITEM, "approach.judgement.recorded"), 0)

    def test_log_leaf_replacement_after_publication_is_refused(self):
        from scripts.factory.lib import convergence
        record = self.record()
        log = paths.item_dir(self.repo, ITEM) / "log.jsonl"
        before = log.read_bytes()
        original_link = os.link
        with tempfile.TemporaryDirectory() as tmp:
            detached = Path(tmp) / "detached.jsonl"

            def publish_then_move_log(*args, **kwargs):
                original_link(*args, **kwargs)
                log.rename(detached)
                log.write_bytes(before)

            with mock.patch.object(os, "link", side_effect=publish_then_move_log):
                code, _out, err = self.run_cli(
                    "approach-judgement", ITEM, "--data", json.dumps(record))
            self.assertEqual(detached.read_bytes(), before,
                             "writer appended to the externally moved log")
            self.assertEqual(log.read_bytes(), before)
            self.assertEqual(code, 2, "writer accepted a replaced log: " + err)
            convergence.record_judgement(self.repo, ITEM, record)
            convergence.record_judgement(self.repo, ITEM, record)
            self.assertEqual(logs.count_events(
                self.repo, ITEM, "approach.judgement.recorded"), 1)

    def test_log_parent_swap_with_forged_dedup_event_is_refused(self):
        from scripts.factory.lib import convergence
        record = self.record()
        path = self.repo / self.context()["record"]
        directory = paths.item_dir(self.repo, ITEM)
        backup = directory.with_name(directory.name + ".saved")
        before = (directory / "log.jsonl").read_bytes()
        original_link = os.link
        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp) / "external"
            shutil.copytree(directory, external)
            forged = {"event": "approach.judgement.recorded", "ts": logs.now_stamp(),
                      "data": convergence._event_data(self.repo, path, record)}
            external_log = external / "log.jsonl"
            external_log.write_text(json.dumps(forged) + "\n", encoding="utf-8")
            external_before = external_log.read_bytes()

            def publish_then_swap_parent(*args, **kwargs):
                original_link(*args, **kwargs)
                directory.rename(backup)
                directory.symlink_to(external, target_is_directory=True)

            try:
                with mock.patch.object(os, "link",
                                       side_effect=publish_then_swap_parent):
                    code, _out, err = self.run_cli(
                        "approach-judgement", ITEM, "--data", json.dumps(record))
                self.assertEqual((backup / "log.jsonl").read_bytes(), before)
                self.assertEqual(external_log.read_bytes(), external_before)
                self.assertEqual(code, 2,
                                 "forged external event suppressed internal audit: " + err)
            finally:
                if backup.exists():
                    directory.unlink()
                    backup.rename(directory)
            convergence.record_judgement(self.repo, ITEM, record)
            self.assertEqual(logs.count_events(
                self.repo, ITEM, "approach.judgement.recorded"), 1)

    def assert_directory_symlinks_refused(self, after_context=False):
        from scripts.factory.lib import convergence
        record = self.record()
        canonical = self.repo / self.context()["record"]
        for directory in (canonical.parent, canonical.parent.parent,
                          self.repo / ".factory/items", self.repo / ".factory"):
            with self.subTest(directory=directory.relative_to(self.repo)), \
                    tempfile.TemporaryDirectory() as tmp:
                external = Path(tmp) / "external"
                if directory.exists():
                    shutil.copytree(directory, external)
                else:
                    external.mkdir()
                before = {p.relative_to(external): p.read_bytes()
                          for p in external.rglob("*") if p.is_file()}
                original_log = paths.item_dir(self.repo, ITEM) / "log.jsonl"
                log_bytes = original_log.read_bytes()
                backup = directory.with_name(directory.name + ".saved")
                moved = directory.exists()
                swapped = False

                def swap():
                    nonlocal swapped
                    if moved:
                        directory.rename(backup)
                    directory.symlink_to(external, target_is_directory=True)
                    swapped = True

                original_context = convergence.current_context

                def context_then_swap(*args, **kwargs):
                    context = original_context(*args, **kwargs)
                    if not swapped:
                        swap()
                    return context

                try:
                    if not after_context:
                        swap()
                    with mock.patch.object(
                            convergence, "current_context",
                            side_effect=context_then_swap if after_context
                            else original_context):
                        code, _out, err = self.run_cli(
                            "approach-judgement", ITEM,
                            "--data", json.dumps(record))
                    after = {p.relative_to(external): p.read_bytes()
                             for p in external.rglob("*") if p.is_file()}
                    self.assertEqual(after, before,
                                     "writer mutated external files through symlink")
                    self.assertEqual(original_log.read_bytes(), log_bytes)
                    self.assertEqual(code, 2, err)
                    self.assertIn("symlink", err)
                finally:
                    if swapped:
                        directory.unlink()
                    if moved and backup.exists():
                        backup.rename(directory)

    def test_directory_symlinks_refused_without_external_mutation(self):
        self.assert_directory_symlinks_refused()

    def test_parent_symlinks_after_context_refused_without_external_mutation(self):
        self.assert_directory_symlinks_refused(after_context=True)

    def test_detached_item_before_lock_creation_leaves_no_external_mutation(self):
        from scripts.factory.lib import convergence
        record = self.record()
        item_dir = paths.item_dir(self.repo, ITEM)
        canonical = self.repo / self.context()["record"]
        canonical.parent.mkdir(parents=True, exist_ok=True)
        (canonical.parent / "unrelated.bin").write_bytes(b"external state\xff")
        before = {path.relative_to(item_dir): path.read_bytes()
                  for path in item_dir.rglob("*") if path.is_file()}
        original_open = os.open
        detached = False

        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp) / "detached-item"

            def detach_before_lock(name, flags, *args, **kwargs):
                nonlocal detached
                if name == ".approach-judgement.lock" and not detached:
                    item_dir.rename(external)
                    detached = True
                return original_open(name, flags, *args, **kwargs)

            try:
                with mock.patch.object(os, "open", side_effect=detach_before_lock):
                    with self.assertRaises(convergence.ConvergenceError):
                        convergence.record_judgement(self.repo, ITEM, record)
                after = {path.relative_to(external): path.read_bytes()
                         for path in external.rglob("*") if path.is_file()}
                self.assertEqual(after, before)
                self.assertFalse((external / ".approach-judgement.lock").exists())
                self.assertFalse(
                    (external / canonical.relative_to(item_dir)).exists())
                self.assertFalse(list(external.rglob("*.tmp")))
            finally:
                if detached:
                    external.rename(item_dir)

    def test_detached_judgement_at_publication_removes_only_created_record(self):
        from scripts.factory.lib import convergence
        record = self.record()
        item_dir = paths.item_dir(self.repo, ITEM)
        log = item_dir / "log.jsonl"
        log_before = log.read_bytes()
        canonical = self.repo / self.context()["record"]
        canonical.parent.mkdir(parents=True, exist_ok=True)
        unrelated = canonical.parent / "unrelated.bin"
        unrelated.write_bytes(b"external state\xff")
        original_replace = os.replace
        original_link = os.link
        detached = False

        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp) / "detached-judgements"

            def detach_before_publication(source, target, *args, **kwargs):
                nonlocal detached
                if target == canonical.name and not detached:
                    canonical.parent.rename(external)
                    detached = True
                return original_replace(source, target, *args, **kwargs)

            def detach_before_initial_publication(
                    source, target, *args, **kwargs):
                nonlocal detached
                if target == canonical.name and not detached:
                    canonical.parent.rename(external)
                    detached = True
                return original_link(source, target, *args, **kwargs)

            try:
                with mock.patch.object(
                        os, "replace", side_effect=detach_before_publication), \
                        mock.patch.object(
                            os, "link",
                            side_effect=detach_before_initial_publication):
                    with self.assertRaises(convergence.ConvergenceError):
                        convergence.record_judgement(self.repo, ITEM, record)
                self.assertEqual(
                    {path.relative_to(external): path.read_bytes()
                     for path in external.rglob("*") if path.is_file()},
                    {Path("unrelated.bin"): b"external state\xff"})
                self.assertFalse((external / canonical.name).exists())
                self.assertFalse(list(external.glob("*.tmp")))
                self.assertEqual(log.read_bytes(), log_before)
            finally:
                if detached:
                    external.rename(canonical.parent)

    def test_detached_item_during_audit_rolls_back_initial_publication(self):
        record = self.record()
        item_dir = paths.item_dir(self.repo, ITEM)
        log_before = (item_dir / "log.jsonl").read_bytes()
        canonical = self.repo / self.context()["record"]
        self.assertFalse(canonical.parent.exists())
        original_append = logs.append_event
        detached = False

        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp) / "detached-item"

            def append_then_detach(*args, **kwargs):
                nonlocal detached
                result = original_append(*args, **kwargs)
                item_dir.rename(external)
                detached = True
                return result

            try:
                with mock.patch.object(
                        logs, "append_event", side_effect=append_then_detach):
                    code, _out, err = self.run_cli(
                        "approach-judgement", ITEM,
                        "--data", json.dumps(record))
                self.assertEqual(code, 2, err)
                self.assertIn("replaced", err)
                self.assertEqual(
                    (external / "log.jsonl").read_bytes(), log_before)
                self.assertFalse(
                    (external / "approach-judgements").exists(),
                    "failed transaction retained its created directory")
                self.assertFalse(
                    (external / ".approach-judgement.lock").exists())
            finally:
                if detached:
                    external.rename(item_dir)

    def test_detached_item_during_audit_restores_previous_record(self):
        first = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"),),
            final_verdict="uncertain", disposition="escalate")
        code, out, err = self.run_cli(
            "approach-judgement", ITEM, "--data", json.dumps(first))
        self.assertEqual((code, err), (0, ""))
        canonical = self.repo / out.strip()
        record_before = canonical.read_bytes()
        item_dir = paths.item_dir(self.repo, ITEM)
        log_before = (item_dir / "log.jsonl").read_bytes()
        lock_before = (
            item_dir / ".approach-judgement.lock").read_bytes()
        second = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"), self.attempt(2)),
            final_verdict="pass", disposition="advance")
        original_append = logs.append_event
        detached = False

        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp) / "detached-item"

            def append_then_detach(*args, **kwargs):
                nonlocal detached
                result = original_append(*args, **kwargs)
                item_dir.rename(external)
                detached = True
                return result

            try:
                with mock.patch.object(
                        logs, "append_event", side_effect=append_then_detach):
                    code, _out, err = self.run_cli(
                        "approach-judgement", ITEM,
                        "--data", json.dumps(second))
                self.assertEqual(code, 2, err)
                self.assertIn("replaced", err)
                detached_record = (
                    external / canonical.relative_to(item_dir))
                self.assertEqual(detached_record.read_bytes(), record_before)
                self.assertEqual(
                    (external / "log.jsonl").read_bytes(), log_before)
                self.assertEqual(
                    (external / ".approach-judgement.lock").read_bytes(),
                    lock_before)
                self.assertFalse(list(
                    (external / "approach-judgements").glob("*.tmp")))
                self.assertFalse(list(
                    (external / "approach-judgements").glob("*.previous")))
            finally:
                if detached:
                    external.rename(item_dir)

    def test_context_cli_exposes_only_engine_derived_values(self):
        code, out, err = self.run_cli("approach-context", ITEM, "--json")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out), self.context())

    def test_record_cli_writes_canonical_json_and_single_writer_event(self):
        record = self.record()
        code, out, err = self.run_cli(
            "approach-judgement", ITEM, "--data", json.dumps(record))
        self.assertEqual((code, err), (0, ""))
        path = self.repo / out.strip()
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), record)
        self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))
        event = logs.read_events(self.repo, ITEM)[-1]
        self.assertEqual(event["event"], "approach.judgement.recorded")
        self.assertEqual(event["data"]["attempts"], 0)
        self.assertEqual(event["data"]["signals"], [])

    def test_disabled_recording_is_unsolicited_and_refused(self):
        self.configure(False)
        code, _out, err = self.run_cli(
            "approach-judgement", ITEM, "--data", json.dumps(self.record()))
        self.assertEqual(code, 2)
        self.assertIn("unsolicited approach judgement", err)
        self.assertFalse((paths.item_dir(self.repo, ITEM) /
                          "approach-judgements").exists())

    def test_invalid_json_is_usage_error_and_writes_nothing(self):
        code, _out, err = self.run_cli(
            "approach-judgement", ITEM, "--data", "{oops")
        self.assertEqual(code, 1)
        self.assertIn("--data is not valid JSON", err)

    def test_initial_record_cannot_skip_the_persisted_first_attempt(self):
        record = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"), self.attempt(2)),
            final_verdict="pass")
        code, _out, err = self.run_cli(
            "approach-judgement", ITEM, "--data", json.dumps(record))
        self.assertEqual(code, 2)
        self.assertIn("initial write may contain at most one reviewer attempt", err)

    def test_escalation_update_appends_one_fresh_attempt(self):
        from scripts.factory.lib import convergence
        first = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"),),
            final_verdict="uncertain", disposition="escalate")
        path = convergence.record_judgement(self.repo, ITEM, first)
        second = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"), self.attempt(2)),
            final_verdict="pass", disposition="advance")
        self.assertEqual(convergence.record_judgement(
            self.repo, ITEM, second), path)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), second)
        self.assertEqual(logs.count_events(
            self.repo, ITEM, "approach.judgement.recorded"), 2)

    def test_idempotent_retry_writes_no_duplicate_event(self):
        from scripts.factory.lib import convergence
        record = self.record()
        path = convergence.record_judgement(self.repo, ITEM, record)
        self.assertEqual(convergence.record_judgement(
            self.repo, ITEM, record), path)
        self.assertEqual(logs.count_events(
            self.repo, ITEM, "approach.judgement.recorded"), 1)

    def test_retry_after_event_interruption_republishes_exactly_one_event(self):
        from scripts.factory.lib import convergence
        record = self.record()
        path = self.repo / self.context()["record"]
        original_append = logs.append_event
        calls = 0

        def interrupted_append(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("injected interruption after replace")
            return original_append(*args, **kwargs)

        with mock.patch.object(convergence.logs, "append_event",
                               side_effect=interrupted_append):
            with self.assertRaisesRegex(OSError, "injected interruption"):
                convergence.record_judgement(self.repo, ITEM, record)
            self.assertFalse(path.exists())
            self.assertEqual(convergence.record_judgement(
                self.repo, ITEM, record), path)

        expected = {
            "path": self.context()["record"],
            "planning_round": record["planning_round"],
            "plan_sha256": record["plan_sha256"],
            "tier": record["tier"],
            "escalation_bound": record["escalation_bound"],
            "signals": [],
            "attempts": 0,
            "final_verdict": "not-triggered",
            "disposition": "advance",
        }
        events = logs.read_events(self.repo, ITEM)
        matching = [event for event in events
                    if event.get("event") == "approach.judgement.recorded"
                    and event.get("data") == expected]
        self.assertEqual(len(matching), 1)
        self.assertEqual(logs.count_events(
            self.repo, ITEM, "approach.judgement.recorded"), 1)

    def test_final_update_retries_rolled_back_escalation_in_order(self):
        from scripts.factory.lib import convergence
        first = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"),),
            final_verdict="uncertain", disposition="escalate")
        second = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"), self.attempt(2)),
            final_verdict="pass", disposition="advance")
        path = self.repo / self.context()["record"]

        with mock.patch.object(
                convergence.logs, "append_event",
                side_effect=OSError("injected interruption after replace")):
            with self.assertRaisesRegex(OSError, "injected interruption"):
                convergence.record_judgement(self.repo, ITEM, first)

        self.assertFalse(path.exists())
        self.assertEqual(
            convergence.record_judgement(self.repo, ITEM, first), path)
        self.assertEqual(
            convergence.record_judgement(self.repo, ITEM, second), path)
        self.assertEqual(
            convergence.record_judgement(self.repo, ITEM, second), path)

        events = [event["data"] for event in logs.read_events(self.repo, ITEM)
                  if event.get("event") == "approach.judgement.recorded"]
        self.assertEqual(len(events), 2, events)
        self.assertEqual(
            [(event["tier"], event["escalation_bound"], event["attempts"],
              event["final_verdict"], event["disposition"])
             for event in events],
            [("feature", 1, 1, "uncertain", "escalate"),
             ("feature", 1, 2, "pass", "advance")])

    def test_tier_change_after_rolled_back_record_uses_same_canonical_path(self):
        from scripts.factory.lib import convergence
        feature = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"),),
            final_verdict="uncertain", disposition="escalate")
        path = self.repo / self.context()["record"]

        with mock.patch.object(
                convergence.logs, "append_event",
                side_effect=OSError("injected interruption after replace")):
            with self.assertRaisesRegex(OSError, "injected interruption"):
                convergence.record_judgement(self.repo, ITEM, feature)

        items.set_tier(self.repo, ITEM, "bug")
        bug = self.record(
            signals=(SIGNALS[0],),
            attempts=(self.attempt(1, verdict="uncertain"),),
            final_verdict="uncertain", disposition="approach.rejected")
        self.assertEqual(bug["tier"], "bug")
        self.assertEqual(bug["escalation_bound"], 0)
        self.assertEqual(self.repo / self.context()["record"], path)

        self.assertEqual(
            convergence.record_judgement(self.repo, ITEM, bug), path)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), bug)
        self.assertEqual(
            convergence.record_judgement(self.repo, ITEM, bug), path)

        events = [event["data"] for event in logs.read_events(self.repo, ITEM)
                  if event.get("event") == "approach.judgement.recorded"]
        self.assertEqual(
            [(event["tier"], event["escalation_bound"], event["attempts"],
              event["final_verdict"], event["disposition"])
             for event in events],
            [("bug", 0, 1, "uncertain", "approach.rejected")])
        self.assertTrue(all(event["path"] == self.context()["record"]
                            for event in events))

    def test_stale_tier_recovery_refuses_changed_screen_and_attempt_history(self):
        from scripts.factory.lib import convergence
        feature = self.record(
            signals=(SIGNALS[0],), attempts=(self.attempt(1),))
        path = convergence.record_judgement(self.repo, ITEM, feature)
        original_bytes = path.read_bytes()

        items.set_tier(self.repo, ITEM, "bug")
        changed = self.record(
            signals=(SIGNALS[1],),
            attempts=(self.attempt(1, invocation="replacement-reviewer"),))
        changed["planner_invocation"] = "replacement-planner"

        with self.assertRaises(convergence.ConvergenceError) as ctx:
            convergence.record_judgement(self.repo, ITEM, changed)

        message = str(ctx.exception)
        self.assertIn("tier-context replacement", message)
        self.assertIn("planner_invocation", message)
        self.assertIn("signals", message)
        self.assertIn("prior attempts", message)
        self.assertEqual(path.read_bytes(), original_bytes)
        self.assertEqual(logs.count_events(
            self.repo, ITEM, "approach.judgement.recorded"), 1)

    def test_concurrent_incompatible_writers_serialize_without_temp_collision(self):
        from scripts.factory.lib import convergence
        first = self.record()
        second = self.record(signals=(SIGNALS[0],),
                             attempts=(self.attempt(1),))
        path = self.repo / self.context()["record"]
        start = threading.Barrier(3)
        replace = threading.Barrier(2)
        original_replace = Path.replace
        outcomes = []
        errors = []

        def synchronized_fixed_temp_replace(source, target):
            if source.name.endswith(".json.tmp"):
                replace.wait(timeout=5)
            return original_replace(source, target)

        def writer(record):
            start.wait(timeout=5)
            try:
                outcomes.append((record, convergence.record_judgement(
                    self.repo, ITEM, record)))
            except Exception as exc:
                errors.append(exc)

        with mock.patch.object(Path, "replace",
                               new=synchronized_fixed_temp_replace):
            threads = [threading.Thread(target=writer, args=(record,))
                       for record in (first, second)]
            for thread in threads:
                thread.start()
            start.wait(timeout=5)
            for thread in threads:
                thread.join(timeout=5)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], convergence.ConvergenceError)
        self.assertNotIsInstance(errors[0], FileNotFoundError)
        persisted, persisted_path = outcomes[0]
        self.assertEqual(persisted_path, path)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), persisted)
        self.assertFalse(list(path.parent.glob("*.tmp")))
        events = [event for event in logs.read_events(self.repo, ITEM)
                  if event.get("event") == "approach.judgement.recorded"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["data"]["path"], self.context()["record"])
        self.assertEqual(events[0]["data"]["plan_sha256"],
                         persisted["plan_sha256"])
        self.assertEqual(events[0]["data"]["signals"],
                         [signal["id"] for signal in persisted["signals"]])

    def test_existing_final_record_and_changed_screen_are_append_only(self):
        from scripts.factory.lib import convergence
        convergence.record_judgement(self.repo, ITEM, self.record())
        changed = self.record(signals=(SIGNALS[0],),
                              attempts=(self.attempt(1),))
        with self.assertRaises(convergence.ConvergenceError) as ctx:
            convergence.record_judgement(self.repo, ITEM, changed)
        self.assertIn("immutable judgement fields changed", str(ctx.exception))

    def test_plan_edit_keeps_old_record_and_writes_new_hash_path(self):
        from scripts.factory.lib import convergence
        old = convergence.record_judgement(self.repo, ITEM, self.record())
        plan = paths.item_dir(self.repo, ITEM) / "plan.md"
        plan.write_text("- [ ] changed bytes\n", encoding="utf-8")
        new = convergence.record_judgement(self.repo, ITEM, self.record())
        self.assertNotEqual(old, new)
        self.assertTrue(old.exists())
        self.assertTrue(new.exists())

    def test_generic_log_cannot_forge_recorded_event(self):
        code, _out, err = self.run_cli(
            "log", ITEM, "approach.judgement.recorded")
        self.assertEqual(code, 1)
        self.assertIn("written only by factory approach-judgement", err)


class TestApproachRejectionHandoff(ConvergenceCase):
    def test_rejecting_judgement_hands_off_to_shared_redesign_edge(self):
        from scripts.factory.lib import convergence
        cases = (("feature", "reject", None),
                 ("bug", "uncertain", None),
                 ("feature", "uncertain", "reject"),
                 ("feature", "uncertain", "uncertain"))
        for index, (tier, first, second) in enumerate(cases):
            with self.subTest(tier=tier, first=first, second=second):
                if index:
                    self.tearDown()
                    self.setUp()
                self.configure(True)
                item_dir = self.make_plan_item(tier=tier)
                attempts = (self.attempt(1, verdict=first),)
                record = self.record(
                    signals=(SIGNALS[0],), attempts=attempts,
                    final_verdict=first,
                    disposition="escalate" if second else "approach.rejected")
                record_path = convergence.record_judgement(self.repo, ITEM,
                                                            record)
                if second:
                    record = self.record(
                        signals=(SIGNALS[0],),
                        attempts=attempts + (self.attempt(2, verdict=second),),
                        final_verdict=second, disposition="approach.rejected")
                    convergence.record_judgement(self.repo, ITEM, record)
                before = logs.read_events(self.repo, ITEM)
                with self.assertRaises(machine.GateError) as ctx:
                    machine.advance(self.repo, ITEM, "implement")
                self.assertIn(f"route factory advance {ITEM} spec",
                              str(ctx.exception))
                self.assertEqual(items.load_item(self.repo, ITEM)[0]["stage"],
                                 "plan")
                self.assertEqual(logs.read_events(self.repo, ITEM), before)

                # The orchestrator appends the cited rejection while the
                # judgement and plan evidence are fresh, before re-routing.
                cited_record = record_path.relative_to(self.repo).as_posix()
                plan_evidence = record["signals"][0]["evidence"][0]
                citation = (f"{plan_evidence['path']}:"
                            f"{plan_evidence['start_line']}-"
                            f"{plan_evidence['end_line']}")
                forbidden = item_dir / "approaches" / "forbidden.md"
                forbidden.parent.mkdir(parents=True, exist_ok=True)
                entry = ("## 2026-09-04T12:00:00Z - rejected at plan (entry 1)\n\n"
                         "The selected approach has no bounded completion.\n"
                         f"Evidence: {cited_record}; {citation}\n\n")
                with forbidden.open("a", encoding="utf-8") as stream:
                    stream.write(entry)
                reason = "approach.rejected: selected strategy cannot converge"
                meta, _ = machine.advance(self.repo, ITEM, "spec", reason=reason)
                self.assertEqual(meta["stage"], "spec")
                self.assertEqual(forbidden.read_text(encoding="utf-8"), entry)
                self.assertEqual(json.loads(record_path.read_text()), record)
                events = logs.read_events(self.repo, ITEM)
                self.assertEqual(events[-1]["data"],
                                 {"from": "plan", "to": "spec", "reason": reason})
                self.assertEqual(machine._approach_edges(events)[0], 1)
                self.assertFalse(any(
                    event["event"] == "stage.advance"
                    and event["data"]["to"] in {"implement", "blocked"}
                    for event in events))


class TestApproachAdvanceGate(ConvergenceCase):
    def setUp(self):
        super().setUp()
        self.configure(True)
        self.item_dir = self.make_plan_item(
            plan="- [ ] bounded change\n\nreview evidence\n")

    def write_record(self, record):
        path = self.repo / self.context()["record"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        return path

    def assert_advance_refused(self, fragment):
        log_path = self.item_dir / "log.jsonl"
        before = log_path.read_bytes()
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "implement")
        self.assertIn(fragment, str(ctx.exception))
        meta, _body = items.load_item(self.repo, ITEM)
        self.assertEqual(meta["stage"], "plan")
        self.assertEqual(log_path.read_bytes(), before)

    def test_missing_current_record_refuses_without_mutation(self):
        self.assert_advance_refused("current approach judgement missing")

    def test_checkbox_precondition_precedes_missing_judgement(self):
        (self.item_dir / "plan.md").write_text("No executable tasks yet.\n")
        self.assert_advance_refused("plan.md with at least one '- [ ]' task required")

    def test_checkbox_must_exist_in_the_exact_authorized_plan(self):
        from scripts.factory.lib import convergence
        plan = self.item_dir / "plan.md"
        judged_bytes = b"No executable tasks yet.\n"
        plan.write_bytes(judged_bytes)
        convergence.record_judgement(self.repo, ITEM, self.record())
        original_item = (self.item_dir / "item.md").read_bytes()
        plan.write_text("- [ ] temporary unchecked task\n")
        validate_record = convergence.require_authoritative
        calls = []

        def restore_judged_plan_then_validate(*args, **kwargs):
            calls.append("restore")
            plan.write_bytes(judged_bytes)
            return validate_record(*args, **kwargs)

        with mock.patch.object(convergence, "require_authoritative",
                               side_effect=restore_judged_plan_then_validate):
            self.assert_advance_refused(
                "plan.md with at least one '- [ ]' task required")
        self.assertEqual(calls, ["restore"])
        self.assertEqual(plan.read_bytes(), judged_bytes)
        self.assertEqual((self.item_dir / "item.md").read_bytes(), original_item)

    def test_plan_replacement_during_edge_persistence_refuses_without_mutation(self):
        from scripts.factory.lib import convergence
        cases = [(boundary, moment, edit)
                 for boundary in ("save_item", "append_event")
                 for moment in ("before", "after")
                 for edit in ("replace", "in-place")]
        for index, (boundary, moment, edit) in enumerate(cases):
            with self.subTest(boundary=boundary, moment=moment, edit=edit):
                if index:
                    self.tearDown()
                    self.setUp()
                convergence.record_judgement(self.repo, ITEM, self.record())
                plan = self.item_dir / "plan.md"
                original_item = (self.item_dir / "item.md").read_bytes()
                replacement = self.item_dir / "replacement.md"
                replacement.write_text("- [ ] unjudged replacement\n")
                module = items if boundary == "save_item" else logs
                persist = getattr(module, boundary)
                calls = []

                def replace_then_persist(*args, **kwargs):
                    calls.append(boundary)
                    if moment == "after":
                        result = persist(*args, **kwargs)
                    if edit == "replace":
                        replacement.replace(plan)
                    else:
                        plan.write_bytes(replacement.read_bytes())
                    if moment == "before":
                        result = persist(*args, **kwargs)
                    return result

                with mock.patch.object(module, boundary,
                                       side_effect=replace_then_persist):
                    self.assert_advance_refused("plan.md changed")
                self.assertEqual(calls, [boundary])
                self.assertEqual((self.item_dir / "item.md").read_bytes(),
                                 original_item)
                self.assertEqual(plan.read_text(), "- [ ] unjudged replacement\n")

    def test_parent_replacement_during_persistence_never_writes_external_files(self):
        from scripts.factory.lib import convergence
        convergence.record_judgement(self.repo, ITEM, self.record())
        originals = {name: (self.item_dir / name).read_bytes()
                     for name in ("item.md", "log.jsonl", "plan.md")}
        pinned = self.item_dir.with_name("detached-item")
        with tempfile.TemporaryDirectory() as external_tmp:
            external = Path(external_tmp)
            for name, content in originals.items():
                (external / name).write_bytes(content)
            persist = items.save_item

            def replace_then_save(*args, **kwargs):
                self.item_dir.rename(pinned)
                self.item_dir.symlink_to(external, target_is_directory=True)
                return persist(*args, **kwargs)

            with mock.patch.object(items, "save_item", side_effect=replace_then_save):
                self.assert_advance_refused("plan.md changed")
            for name, content in originals.items():
                self.assertEqual((external / name).read_bytes(), content)
                self.assertEqual((pinned / name).read_bytes(), content)

    def test_persistence_error_restores_item_and_log_bytes(self):
        from scripts.factory.lib import convergence
        for index, boundary in enumerate(("save_item", "append_event")):
            with self.subTest(boundary=boundary):
                if index:
                    self.tearDown()
                    self.setUp()
                convergence.record_judgement(self.repo, ITEM, self.record())
                original_item = (self.item_dir / "item.md").read_bytes()
                module = items if boundary == "save_item" else logs
                persist = getattr(module, boundary)

                def persist_then_fail(*args, **kwargs):
                    persist(*args, **kwargs)
                    raise OSError("simulated persistence interruption")

                with mock.patch.object(module, boundary, side_effect=persist_then_fail):
                    self.assert_advance_refused("plan.md changed or became unreadable")
                self.assertEqual((self.item_dir / "item.md").read_bytes(), original_item)

    def test_concurrent_validated_advances_admit_only_one_edge(self):
        from scripts.factory.lib import convergence
        convergence.record_judgement(self.repo, ITEM, self.record())
        validate_record = convergence.require_authoritative
        validated = threading.Barrier(2)
        results, failures = [], []

        def synchronize_validation(*args, **kwargs):
            record = validate_record(*args, **kwargs)
            validated.wait(timeout=5)
            return record

        def advance():
            try:
                results.append(machine.advance(self.repo, ITEM, "implement"))
            except Exception as exc:
                failures.append(exc)

        with mock.patch.object(convergence, "require_authoritative",
                               side_effect=synchronize_validation):
            workers = [threading.Thread(target=advance) for _ in range(2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=10)
                self.assertFalse(worker.is_alive())
        self.assertEqual(len(results), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], machine.GateError)
        exits = [event for event in logs.read_events(self.repo, ITEM)
                 if event.get("event") == "stage.advance"
                 and event.get("data", {}).get("to") == "implement"]
        self.assertEqual(len(exits), 1)

    def test_external_plan_symlink_rejected_before_hash_record_or_advance(self):
        from scripts.factory.lib import convergence
        record = self.record()
        canonical = self.repo / self.context()["record"]
        plan = self.item_dir / "plan.md"
        original_item = (self.item_dir / "item.md").read_bytes()
        original_log = (self.item_dir / "log.jsonl").read_bytes()
        with tempfile.TemporaryDirectory() as external_tmp:
            external = Path(external_tmp) / "plan.md"
            external.write_bytes(plan.read_bytes())
            plan.unlink()
            plan.symlink_to(external)
            with mock.patch.object(convergence.hashlib, "sha256",
                                   wraps=convergence.hashlib.sha256) as digest:
                for operation in ("context", "record", "advance"):
                    with self.subTest(operation=operation):
                        if operation == "advance":
                            # A valid no-signal record must not authorize the
                            # external bytes even when their hash is identical.
                            canonical.parent.mkdir(parents=True, exist_ok=True)
                            canonical.write_text(json.dumps(record))
                            self.assert_advance_refused("untrusted symlink")
                        else:
                            with self.assertRaisesRegex(
                                    convergence.ConvergenceError,
                                    "untrusted symlink"):
                                if operation == "context":
                                    convergence.current_context(self.repo, ITEM)
                                else:
                                    convergence.record_judgement(
                                        self.repo, ITEM, record)
                            self.assertFalse(canonical.exists())
                        digest.assert_not_called()
                        self.assertEqual((self.item_dir / "item.md").read_bytes(),
                                         original_item)
                        self.assertEqual((self.item_dir / "log.jsonl").read_bytes(),
                                         original_log)

    def test_recorded_zero_signal_screen_advances_once(self):
        from scripts.factory.lib import convergence
        record = self.record()
        convergence.record_judgement(self.repo, ITEM, record)

        meta, _verdict = machine.advance(self.repo, ITEM, "implement")

        self.assertEqual(meta["stage"], "implement")
        events = logs.read_events(self.repo, ITEM)
        writer = [event for event in events
                  if event.get("event") == "approach.judgement.recorded"]
        exits = [event for event in events
                 if event.get("event") == "stage.advance"
                 and event.get("data", {}).get("from") == "plan"
                 and event.get("data", {}).get("to") == "implement"]
        self.assertEqual(len(writer), 1)
        self.assertEqual(writer[0]["data"]["attempts"], 0)
        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0]["data"], {
            "from": "plan", "to": "implement",
            "approach": {"planning_round": record["planning_round"],
                         "plan_sha256": record["plan_sha256"]},
        })

    def test_each_signal_shape_requires_then_admits_current_one_pass_record(self):
        from scripts.factory.lib import convergence
        groups = tuple((signal,) for signal in SIGNALS) + (SIGNALS,)
        for index, signals in enumerate(groups):
            with self.subTest(signals=signals):
                if index:
                    self.tearDown()
                    self.setUp()
                self.assert_advance_refused("current approach judgement missing")
                convergence.record_judgement(
                    self.repo, ITEM,
                    self.record(signals=signals, attempts=(self.attempt(1),)))
                meta, _verdict = machine.advance(self.repo, ITEM, "implement")
                self.assertEqual(meta["stage"], "implement")

    def test_escalation_and_rejection_refuse_with_actionable_routes(self):
        from scripts.factory.lib import convergence
        first_attempt = self.attempt(1, verdict="uncertain")
        convergence.record_judgement(
            self.repo, ITEM,
            self.record(signals=(SIGNALS[0],), attempts=(first_attempt,),
                        final_verdict="uncertain", disposition="escalate"))
        self.assert_advance_refused("requires one fresh escalation reviewer")

        convergence.record_judgement(
            self.repo, ITEM,
            self.record(
                signals=(SIGNALS[0],),
                attempts=(first_attempt, self.attempt(2, verdict="reject")),
                final_verdict="reject", disposition="approach.rejected"))
        self.assert_advance_refused("route factory advance")

    def test_direct_malformed_wrong_item_and_unknown_verdict_refuse(self):
        cases = ("malformed", "wrong-item", "unknown-verdict")
        for index, label in enumerate(cases):
            with self.subTest(label=label):
                if index:
                    self.tearDown()
                    self.setUp()
                if label == "malformed":
                    path = self.repo / self.context()["record"]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("{oops\n", encoding="utf-8")
                    fragment = "malformed JSON"
                elif label == "wrong-item":
                    record = self.record()
                    record["item"] = "0002-other"
                    self.write_record(record)
                    fragment = "wrong item"
                else:
                    record = self.record(
                        signals=(SIGNALS[0],), attempts=(self.attempt(1),))
                    record["attempts"][0]["verdict"] = "maybe"
                    self.write_record(record)
                    fragment = "not one of"
                self.assert_advance_refused(fragment)

    def test_external_leaf_symlink_cannot_authorize_implement(self):
        context = self.context()
        canonical = self.repo / context["record"]
        canonical.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as external_tmp:
            external = Path(external_tmp) / "external-record.json"
            external.write_text(
                json.dumps(self.record(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8")
            canonical.symlink_to(external)

            self.assert_advance_refused("untrusted symlink")

    def test_external_parent_symlink_cannot_authorize_implement(self):
        context = self.context()
        canonical = self.repo / context["record"]
        with tempfile.TemporaryDirectory() as external_tmp:
            external = Path(external_tmp)
            external.joinpath(canonical.name).write_text(
                json.dumps(self.record(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8")
            canonical.parent.symlink_to(external, target_is_directory=True)

            self.assert_advance_refused("untrusted symlink")

    def test_direct_validator_failures_refuse_without_log_mutation(self):
        cases = (
            "missing-citation", "empty-citation", "out-of-range",
            "same-invocation", "reused-reviewer", "over-bound",
            "incoherent-resolution",
        )
        for index, label in enumerate(cases):
            with self.subTest(label=label):
                if index:
                    self.tearDown()
                    self.setUp()
                if label == "missing-citation":
                    record = self.record(
                        signals=(SIGNALS[0],),
                        attempts=(self.attempt(1, path="missing.md"),))
                    fragment = "citation path missing"
                elif label == "empty-citation":
                    empty = self.item_dir / "empty.md"
                    empty.write_text("   \n", encoding="utf-8")
                    record = self.record(
                        signals=(SIGNALS[0],),
                        attempts=(self.attempt(
                            1, path=f".factory/items/{ITEM}/empty.md"),))
                    fragment = "citation range is empty"
                elif label == "out-of-range":
                    record = self.record(
                        signals=(SIGNALS[0],),
                        attempts=(self.attempt(1, end=99),))
                    fragment = "citation range out of range"
                elif label == "same-invocation":
                    record = self.record(
                        signals=(SIGNALS[0],),
                        attempts=(self.attempt(
                            1, invocation="planner-001"),))
                    fragment = "matches planner invocation"
                elif label == "reused-reviewer":
                    record = self.record(
                        signals=(SIGNALS[0],),
                        attempts=(
                            self.attempt(1, verdict="uncertain"),
                            self.attempt(2, invocation="reviewer-001"),
                        ),
                        final_verdict="pass")
                    fragment = "reviewer invocation reused"
                elif label == "over-bound":
                    record = self.record(
                        signals=(SIGNALS[0],),
                        attempts=(
                            self.attempt(1, verdict="uncertain"),
                            self.attempt(2, verdict="uncertain"),
                            self.attempt(3),
                        ),
                        final_verdict="pass")
                    fragment = "attempt count 3 exceeds resolved maximum 2"
                else:
                    record = self.record(
                        signals=(SIGNALS[0],), attempts=(self.attempt(1),),
                        final_verdict="reject",
                        disposition="approach.rejected")
                    fragment = "incoherent: expected pass + advance"
                self.write_record(record)
                self.assert_advance_refused(fragment)

    def test_edited_plan_retains_old_record_and_refuses_as_stale(self):
        from scripts.factory.lib import convergence
        old_path = convergence.record_judgement(
            self.repo, ITEM, self.record())
        self.item_dir.joinpath("plan.md").write_text(
            "- [ ] edited bounded change\n", encoding="utf-8")

        self.assert_advance_refused("stale plan judgement retained")
        self.assertTrue(old_path.exists())

    def test_reentered_plan_and_special_resume_keep_old_round_stale(self):
        from scripts.factory.lib import convergence
        old_context = self.context()
        old_path = convergence.record_judgement(
            self.repo, ITEM, self.record())
        forbidden = self.item_dir / "approaches" / "forbidden.md"
        forbidden.parent.mkdir(parents=True, exist_ok=True)
        forbidden.write_text(
            "## Rejected approach\n\n"
            f"Evidence: .factory/items/{ITEM}/plan.md:1\n",
            encoding="utf-8")
        machine.advance(
            self.repo, ITEM, "spec",
            reason="approach.rejected: bounded plan did not converge")
        self.item_dir.joinpath("spec.md").write_text(
            "# Revised spec\n\n## Journey impact\nJ-005.\n",
            encoding="utf-8")
        logs.append_event(self.repo, ITEM, "spec.revised")
        machine.advance(self.repo, ITEM, "plan")

        current = self.context()
        self.assertEqual(current["planning_round"], "plan-0002")
        self.assertEqual(current["plan_sha256"], old_context["plan_sha256"])
        self.assertTrue(old_path.exists())
        self.assert_advance_refused("stale planning-round judgement retained")

        machine.advance(self.repo, ITEM, "waiting-human", reason="interrupt")
        machine.advance(self.repo, ITEM, "plan")
        self.assertEqual(self.context()["planning_round"], "plan-0002")
        self.assert_advance_refused("stale planning-round judgement retained")

    def test_explicitly_disabled_gate_ignores_unsolicited_malformed_record(self):
        self.configure(False)
        path = self.repo / self.context()["record"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{unsolicited malformed\n", encoding="utf-8")
        before = logs.read_events(self.repo, ITEM)

        meta, _verdict = machine.advance(self.repo, ITEM, "implement")

        self.assertEqual(meta["stage"], "implement")
        self.assertEqual(
            logs.read_events(self.repo, ITEM)[len(before):],
            [{"event": "stage.advance", "ts": "2026-09-04T12:00:00Z",
              "data": {"from": "plan", "to": "implement"}}])
