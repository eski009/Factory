import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import cost, initrepo, items, paths


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/factory/factory.py"
ITEM = "0001-mixed"
QUALIFIER = "PARTIAL — measured leaf events only; coverage incomplete"
MEASURED_119266 = {"events": 1, "input": 0, "output": 0,
                   "total": 119266}


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
            # A historical record remains readable, but is never inferred as a
            # leaf merely because it is measured.
            {"event": "spend", "ts": "2026-09-07T00:01:00Z",
             "data": {"provenance": "measured", "stage": "spec",
                      "dispatches": 1, "tokens": {"total": 70}}},
            {"event": "spend", "ts": "2026-09-07T00:02:00Z",
             "data": {"provenance": "measured", "scope": "fork",
                      "stage": "spec", "dispatches": 1,
                      "tokens": {"total": 98841}}},
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

    def run_cli(self, *args, repo=None):
        return subprocess.run(
            ["python3", str(CLI), "--repo", str(repo or self.repo), *args],
            cwd=ROOT, capture_output=True, text=True)

    def add_item(self, repo, title):
        added = self.run_cli("add", title, repo=repo)
        self.assertEqual(added.returncode, 0, added.stderr)
        return added.stdout.strip()

    def assert_unchanged(self, log, expected):
        self.assertEqual(log.read_bytes(), expected)

    def assert_scope_summary(self, summary, counts):
        self.assertEqual(summary["measured"], MEASURED_119266)
        self.assertEqual(summary["measured_scope"], "leaf")
        self.assertFalse(summary["coverage_complete"])
        self.assertEqual(summary["scope_counts"], counts)

    def assert_qualified_readouts(self, repo, item_id, log, expected, counts):
        count_text = (f"spend events: leaf {counts['leaf']}, fork "
                      f"{counts['fork']}, unclassified "
                      f"{counts['unclassified']}")
        cost_result = self.run_cli("cost", item_id, repo=repo)
        self.assertEqual(cost_result.returncode, 0, cost_result.stderr)
        self.assertIn("total 119266 (1 spend events)", cost_result.stdout)
        self.assertIn(QUALIFIER, cost_result.stdout)
        self.assertIn(count_text, cost_result.stdout)
        self.assert_unchanged(log, expected)

        status = self.run_cli("status", "--json", repo=repo)
        self.assertEqual(status.returncode, 0, status.stderr)
        rows = json.loads(status.stdout)
        self.assertEqual(len(rows), 1)
        self.assert_scope_summary(rows[0]["spend"], counts)
        self.assert_unchanged(log, expected)

        packet_result = self.run_cli("packet", item_id, repo=repo)
        self.assertEqual(packet_result.returncode, 0, packet_result.stderr)
        markdown = (repo / f"docs/factory/packets/{item_id}.md").read_text(
            encoding="utf-8")
        html = (repo / f"docs/factory/packets/{item_id}.html").read_text(
            encoding="utf-8")
        for rendered in (markdown, html):
            self.assertIn("total 119266 (1 spend events)", rendered)
            self.assertIn(QUALIFIER, rendered)
            self.assertIn(count_text, rendered)
        self.assert_unchanged(log, expected)

    def test_mixed_legacy_readers_preserve_bytes_and_shared_leaf_readout(self):
        before = self.log.read_bytes()

        initialized = self.run_cli("init")
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self.assert_unchanged(self.log, before)

        summary = cost.summarize(self.repo, ITEM)
        self.assert_scope_summary(
            summary, {"leaf": 1, "fork": 1, "unclassified": 1})
        self.assert_unchanged(self.log, before)

        self.assert_qualified_readouts(
            self.repo, ITEM, self.log, before,
            {"leaf": 1, "fork": 1, "unclassified": 1})

        validated = self.run_cli("validate")
        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assert_unchanged(self.log, before)

    def test_fresh_writes_and_invalid_legacy_recovery_are_append_only(self):
        fresh_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(fresh_tmp.cleanup)
        fresh = Path(fresh_tmp.name)
        initialized = self.run_cli("init", repo=fresh)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        schema = initrepo.load_schema("spend-event")
        self.assertEqual(schema["required"], ["provenance"])
        self.assertEqual(schema["properties"]["scope"]["enum"],
                         ["leaf", "fork"])

        fresh_item = self.add_item(fresh, "Fresh spend")
        fresh_log = paths.item_dir(fresh, fresh_item) / "log.jsonl"
        for scope in ("leaf", "fork"):
            before_write = fresh_log.read_bytes()
            payload = {"provenance": "proxy", "scope": scope,
                       "stage": "idea", "dispatches": 1}
            written = self.run_cli(
                "log", fresh_item, "spend", "--data", json.dumps(payload),
                repo=fresh)
            self.assertEqual(written.returncode, 0, written.stderr)
            after_write = fresh_log.read_bytes()
            self.assertTrue(after_write.startswith(before_write))
            appended = json.loads(after_write[len(before_write):])
            self.assertEqual(appended["event"], "spend")
            self.assertEqual(appended["data"], payload)
            self.assertNotIn("tokens", appended["data"])
        fresh_before_validate = fresh_log.read_bytes()
        fresh_validate = self.run_cli("validate", repo=fresh)
        self.assertEqual(fresh_validate.returncode, 0, fresh_validate.stderr)
        self.assert_unchanged(fresh_log, fresh_before_validate)

        invalid_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(invalid_tmp.cleanup)
        invalid_repo = Path(invalid_tmp.name)
        initialized = self.run_cli("init", repo=invalid_repo)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        invalid_item = self.add_item(invalid_repo, "Invalid legacy")
        invalid_log = paths.item_dir(invalid_repo, invalid_item) / "log.jsonl"
        with invalid_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "event": "spend", "ts": "2026-09-07T00:01:00Z",
                "data": {"provenance": "measured", "scope": "branch",
                         "stage": "implement", "dispatches": 1,
                         "tokens": {"total": 7}}}, sort_keys=True) + "\n")
        invalid_before_reads = invalid_log.read_bytes()

        invalid_summary = cost.summarize(invalid_repo, invalid_item)
        self.assertIsNone(invalid_summary["measured"])
        self.assertEqual(invalid_summary["scope_counts"],
                         {"leaf": 0, "fork": 0, "unclassified": 1})
        self.assertEqual(invalid_summary["invalid_spend_events"], 1)
        self.assert_unchanged(invalid_log, invalid_before_reads)

        invalid_cost = self.run_cli("cost", invalid_item, repo=invalid_repo)
        self.assertEqual(invalid_cost.returncode, 0, invalid_cost.stderr)
        self.assertIn("UNMEASURED", invalid_cost.stdout)
        self.assertIn(QUALIFIER, invalid_cost.stdout)
        self.assertIn("spend events: leaf 0, fork 0, unclassified 1",
                      invalid_cost.stdout)
        self.assertIn("invalid spend events: 1", invalid_cost.stdout)
        self.assert_unchanged(invalid_log, invalid_before_reads)

        invalid_status = self.run_cli("status", "--json", repo=invalid_repo)
        self.assertEqual(invalid_status.returncode, 0, invalid_status.stderr)
        invalid_spend = json.loads(invalid_status.stdout)[0]["spend"]
        self.assertIsNone(invalid_spend["measured"])
        self.assertEqual(invalid_spend["scope_counts"],
                         {"leaf": 0, "fork": 0, "unclassified": 1})
        self.assertEqual(invalid_spend["invalid_spend_events"], 1)
        self.assert_unchanged(invalid_log, invalid_before_reads)

        invalid_packet = self.run_cli("packet", invalid_item, repo=invalid_repo)
        self.assertEqual(invalid_packet.returncode, 0, invalid_packet.stderr)
        for suffix in ("md", "html"):
            rendered = (invalid_repo / "docs/factory/packets" /
                        f"{invalid_item}.{suffix}").read_text(encoding="utf-8")
            self.assertIn("UNMEASURED", rendered)
            self.assertIn(QUALIFIER, rendered)
            self.assertIn("spend events: leaf 0, fork 0, unclassified 1",
                          rendered)
        self.assert_unchanged(invalid_log, invalid_before_reads)

        invalid_validate = self.run_cli("validate", repo=invalid_repo)
        expected_scope_error = (
            f"{invalid_item}/log.jsonl:2.scope: 'branch' not one of "
            "['leaf', 'fork']\n")
        self.assertEqual(invalid_validate.returncode, 2)
        self.assertEqual(invalid_validate.stderr, expected_scope_error)
        self.assert_unchanged(invalid_log, invalid_before_reads)

        recovered = self.run_cli(
            "log", invalid_item, "spend", "--data", json.dumps({
                "provenance": "measured", "scope": "leaf",
                "stage": "implement", "dispatches": 1,
                "tokens": {"total": 119266}}), repo=invalid_repo)
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        recovered_bytes = invalid_log.read_bytes()
        self.assertTrue(recovered_bytes.startswith(invalid_before_reads))
        appended = json.loads(recovered_bytes[len(invalid_before_reads):])
        self.assertEqual(appended["data"], {
            "provenance": "measured", "scope": "leaf",
            "stage": "implement", "dispatches": 1,
            "tokens": {"total": 119266}})

        recovered_summary = cost.summarize(invalid_repo, invalid_item)
        self.assert_scope_summary(
            recovered_summary, {"leaf": 1, "fork": 0, "unclassified": 1})
        self.assertEqual(recovered_summary["invalid_spend_events"], 1)
        self.assert_unchanged(invalid_log, recovered_bytes)
        self.assert_qualified_readouts(
            invalid_repo, invalid_item, invalid_log, recovered_bytes,
            {"leaf": 1, "fork": 0, "unclassified": 1})

        recovered_validate = self.run_cli("validate", repo=invalid_repo)
        self.assertEqual(recovered_validate.returncode, 2)
        self.assertEqual(recovered_validate.stderr, expected_scope_error)
        self.assert_unchanged(invalid_log, recovered_bytes)


if __name__ == "__main__":
    unittest.main()
