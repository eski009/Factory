import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import cost, initrepo, items, packet, paths


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/factory/factory.py"
ITEM = "0001-mixed"


class SpendScopeCompatibilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        items.save_item(self.repo, {
            "id": ITEM, "title": "Mixed", "stage": "idea",
            "kind": "backend", "created": "2026-09-07T00:00:00Z",
            "updated": "2026-09-07T00:00:00Z"}, "# Mixed\n")
        self.log = paths.item_dir(self.repo, ITEM) / "log.jsonl"
        rows = [
            {"event": "item.created", "ts": "2026-09-07T00:00:00Z"},
            {"event": "spend", "ts": "2026-09-07T00:01:00Z",
             "data": {"provenance": "measured", "stage": "spec",
                      "dispatches": 1, "tokens": {"total": 70}}},
            {"event": "spend", "ts": "2026-09-07T00:02:00Z",
             "data": {"provenance": "measured", "scope": "fork",
                      "stage": "spec", "dispatches": 1,
                      "tokens": {"total": 40}}},
            {"event": "spend", "ts": "2026-09-07T00:03:00Z",
             "data": {"provenance": "measured", "scope": "leaf",
                      "stage": "spec", "dispatches": 1,
                      "tokens": {"total": 119266}}},
        ]
        self.log.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8")
        os.environ["FACTORY_NOW"] = "2026-09-07T01:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            ["python3", str(CLI), "--repo", str(self.repo), *args],
            cwd=ROOT, capture_output=True, text=True)

    def test_init_summary_status_packet_and_validate_never_rewrite_log(self):
        before = self.log.read_bytes()
        initrepo.init(self.repo)
        self.assertEqual(self.log.read_bytes(), before)

        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["measured"]["total"], 119266)
        self.assertEqual(summary["scope_counts"],
                         {"leaf": 1, "fork": 1, "unclassified": 1})
        self.assertEqual(self.log.read_bytes(), before)

        status = self.run_cli("status", "--json")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)[0]["spend"]["measured_scope"],
                         "leaf")
        self.assertEqual(self.log.read_bytes(), before)

        packet.write_packet(self.repo, ITEM)
        markdown = (self.repo / f"docs/factory/packets/{ITEM}.md").read_text()
        html = (self.repo / f"docs/factory/packets/{ITEM}.html").read_text()
        qualifier = "PARTIAL — measured leaf events only; coverage incomplete"
        self.assertIn(qualifier, markdown)
        self.assertIn(qualifier, html)
        self.assertEqual(self.log.read_bytes(), before)

        self.assertEqual(initrepo.validate_tree(self.repo), [])
        self.assertEqual(self.log.read_bytes(), before)

    def test_fresh_init_accepts_first_scoped_leaf_and_fork_writes(self):
        fresh_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(fresh_tmp.cleanup)
        fresh = Path(fresh_tmp.name)
        init = subprocess.run(
            ["python3", str(CLI), "--repo", str(fresh), "init"],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(init.returncode, 0, init.stderr)
        add = subprocess.run(
            ["python3", str(CLI), "--repo", str(fresh), "add",
             "Fresh spend"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(add.returncode, 0, add.stderr)
        item_id = add.stdout.strip()
        for scope in ("leaf", "fork"):
            write = subprocess.run(
                ["python3", str(CLI), "--repo", str(fresh), "log",
                 item_id, "spend", "--data",
                 json.dumps({"provenance": "proxy", "scope": scope,
                             "stage": "idea", "dispatches": 1})],
                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(write.returncode, 0, write.stderr)
        validate = subprocess.run(
            ["python3", str(CLI), "--repo", str(fresh), "validate"],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(validate.returncode, 0, validate.stderr)


if __name__ == "__main__":
    unittest.main()
