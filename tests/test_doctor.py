import json
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import doctor, initrepo, items, paths


class TestDoctor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo, product="demo")

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_repo_report(self):
        r = doctor.report(self.repo)
        self.assertTrue(r["tree_valid"])
        self.assertFalse(r["design_system_present"])   # still placeholder
        self.assertIsNone(r["designsync_project"])
        self.assertFalse(r["schedule_configured"])
        self.assertEqual(r["merge_policy"], "auto")
        self.assertEqual(r["gates"], ["design"])
        self.assertEqual(r["open_items"], 0)
        self.assertEqual(r["pending_human"], 0)

    def test_design_system_present_when_edited(self):
        (self.repo / "docs/factory/brain/design-system.md").write_text(
            "# Design System\n\nPrimary: #101010 (source: brand.md)\n", encoding="utf-8")
        self.assertTrue(doctor.report(self.repo)["design_system_present"])

    def test_config_integrations_surface(self):
        cfg = json.loads(paths.config_path(self.repo).read_text())
        cfg["designsync_project"] = "proj-123"
        cfg["autopilot"] = {"schedule": "0 * * * *"}
        paths.config_path(self.repo).write_text(json.dumps(cfg, sort_keys=True, indent=2) + "\n")
        r = doctor.report(self.repo)
        self.assertEqual(r["designsync_project"], "proj-123")
        self.assertTrue(r["schedule_configured"])
        self.assertEqual(initrepo.validate_tree(self.repo), [])   # still schema-valid

    def test_item_counts(self):
        for i, stage in enumerate(("idea", "done", "waiting-human"), 1):
            items.save_item(self.repo, {"id": f"000{i}-x{i}", "title": "x", "stage": stage,
                                        "kind": "ui", "created": "2026-07-03T10:00:00Z",
                                        "updated": "2026-07-03T10:00:00Z"}, "")
        r = doctor.report(self.repo)
        self.assertEqual(r["open_items"], 2)      # idea + waiting-human (not done)
        self.assertEqual(r["pending_human"], 1)

    def test_render_deterministic(self):
        text = doctor.render(doctor.report(self.repo))
        self.assertIn("tree_valid:", text)
        self.assertEqual(text, doctor.render(doctor.report(self.repo)))

    def test_worker_readiness_reported(self):
        r = doctor.report(self.repo)
        self.assertIn("workers", r)
        workers = r["workers"]
        for key in ("enabled", "backend", "claude_cli", "codex_cli",
                    "anthropic_key", "openai_key"):
            self.assertIn(key, workers)
        for key in ("enabled", "claude_cli", "codex_cli",
                    "anthropic_key", "openai_key"):
            self.assertIsInstance(workers[key], bool)
        # Fresh repo has no workers config block, so worker_config()
        # DEFAULTS apply deterministically (CLI/env keys are machine-
        # dependent and only checked for presence/type above).
        self.assertFalse(workers["enabled"])
        self.assertEqual(workers["backend"], "claude")
        self.assertIn("max_parallel", workers)
        self.assertIn("retry", workers)
        self.assertEqual(workers["max_parallel"], 2)
        self.assertEqual(workers["retry"]["max_attempts"], 3)

    def test_reports_tier_profiles(self):
        r = doctor.report(self.repo)
        self.assertIn("tiers", r)
        self.assertEqual(r["tiers"]["bug"]["review"], "light")
        self.assertEqual(r["tiers"]["epic"]["research"], "deep")
        self.assertEqual(r["tiers"]["feature"]["review"], "full")


if __name__ == "__main__":
    unittest.main()
