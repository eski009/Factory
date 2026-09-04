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
