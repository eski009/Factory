import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, work


def _init_repo():
    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    initrepo.init(repo)
    return tmp, repo


def _set_workers(repo, workers):
    cfg_path = repo / ".factory" / "config.json"
    data = json.loads(cfg_path.read_text())
    data["workers"] = workers
    cfg_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")


class WorkerConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.repo = _init_repo()

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_when_absent(self):
        cfg = work.worker_config(self.repo)
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["backend"], "claude")
        self.assertEqual(cfg["max_parallel"], 2)
        self.assertEqual(cfg["network"], "off")
        self.assertEqual(cfg["retry"]["max_attempts"], 3)
        self.assertEqual(cfg["codex"]["sandbox"], "workspace-write")

    def test_overrides_merge_over_defaults(self):
        _set_workers(self.repo, {"enabled": True, "backend": "codex",
                                 "retry": {"max_attempts": 5}})
        cfg = work.worker_config(self.repo)
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["backend"], "codex")
        self.assertEqual(cfg["retry"]["max_attempts"], 5)
        # unspecified nested key keeps its default
        self.assertEqual(cfg["retry"]["base_delay_seconds"], 20)

    def test_valid_workers_block_passes_validation(self):
        _set_workers(self.repo, {"enabled": True, "backend": "claude",
                                 "max_parallel": 3, "network": "off",
                                 "models": {"claude": "claude-sonnet-5"}})
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_bad_backend_enum_rejected(self):
        _set_workers(self.repo, {"backend": "gpt"})
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("backend" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
