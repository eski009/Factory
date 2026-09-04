import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

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
