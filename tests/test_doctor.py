import base64
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from scripts.factory.lib import doctor, initrepo, items, paths, work


class TestDoctor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo, product="demo")
        # hermetic: report() -> worker_readiness() reads the codex login
        # home; never let these tests touch a developer's real ~/.codex.
        self.codex_home = tempfile.TemporaryDirectory()
        self._had_codex_home = "CODEX_HOME" in os.environ
        self._old_codex_home = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = self.codex_home.name

    def tearDown(self):
        if self._had_codex_home:
            os.environ["CODEX_HOME"] = self._old_codex_home
        else:
            os.environ.pop("CODEX_HOME", None)
        self.codex_home.cleanup()
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

    def test_doctor_tiers_include_assure(self):
        report = doctor.report(self.repo)
        self.assertEqual(report["tiers"]["bug"]["assure"], "node")


def fake_jwt(exp):
    """Helper to create a fake JWT token with a given exp claim."""
    def seg(obj):
        raw = base64.urlsafe_b64encode(json.dumps(obj).encode()).decode()
        return raw.rstrip("=")
    return f"{seg({'alg': 'none'})}.{seg({'exp': exp})}.sig"


class WorkerReadinessCodexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo, product="demo")
        # Save original env
        self.orig_codex_home = os.environ.get("CODEX_HOME")

    def tearDown(self):
        # Restore original env
        if self.orig_codex_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = self.orig_codex_home
        self.tmp.cleanup()

    def test_empty_codex_home_has_zero_login_ttl(self):
        """With empty CODEX_HOME, codex_login should be 0."""
        empty_home = Path(self.tmp.name) / "codex_empty"
        empty_home.mkdir()
        os.environ["CODEX_HOME"] = str(empty_home)
        workers = doctor.worker_readiness(self.repo)
        self.assertEqual(workers["codex_login"], 0)

    def test_default_auth_is_key(self):
        """With no config, codex_auth should default to 'key'."""
        empty_home = Path(self.tmp.name) / "codex_empty"
        empty_home.mkdir()
        os.environ["CODEX_HOME"] = str(empty_home)
        workers = doctor.worker_readiness(self.repo)
        self.assertEqual(workers["codex_auth"], "key")

    def test_valid_auth_json_returns_positive_ttl(self):
        """With a valid auth.json with future exp, codex_login > 0."""
        codex_home = Path(self.tmp.name) / "codex_valid"
        codex_home.mkdir()
        os.environ["CODEX_HOME"] = str(codex_home)

        # Create auth.json with a token that expires in 7200 seconds
        exp_time = int(time.time()) + 7200
        token = fake_jwt(exp_time)
        auth_data = {"tokens": {"access_token": token}}
        (codex_home / "auth.json").write_text(
            json.dumps(auth_data), encoding="utf-8")

        workers = doctor.worker_readiness(self.repo)
        self.assertGreater(workers["codex_login"], 0)
        # Allow some margin for timing
        self.assertLess(workers["codex_login"], 7210)

    def test_config_auth_chatgpt_surfaces(self):
        """With auth: chatgpt in config, codex_auth should be 'chatgpt'."""
        empty_home = Path(self.tmp.name) / "codex_empty"
        empty_home.mkdir()
        os.environ["CODEX_HOME"] = str(empty_home)

        cfg_path = paths.config_path(self.repo)
        cfg = json.loads(cfg_path.read_text())
        cfg["workers"] = {"codex": {"auth": "chatgpt"}}
        cfg_path.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n")

        workers = doctor.worker_readiness(self.repo)
        self.assertEqual(workers["codex_auth"], "chatgpt")

    def test_expired_token_returns_zero_ttl(self):
        """With an expired token, codex_login should be 0."""
        codex_home = Path(self.tmp.name) / "codex_expired"
        codex_home.mkdir()
        os.environ["CODEX_HOME"] = str(codex_home)

        # Create auth.json with a token that expired 1000 seconds ago
        exp_time = int(time.time()) - 1000
        token = fake_jwt(exp_time)
        auth_data = {"tokens": {"access_token": token}}
        (codex_home / "auth.json").write_text(
            json.dumps(auth_data), encoding="utf-8")

        workers = doctor.worker_readiness(self.repo)
        self.assertEqual(workers["codex_login"], 0)


if __name__ == "__main__":
    unittest.main()
