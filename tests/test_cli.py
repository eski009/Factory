import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", self.repo, *args])
        return code, out.getvalue(), err.getvalue()

    def test_init_then_validate_ok(self):
        code, out, _ = self.run_cli("init", "--product", "demo")
        self.assertEqual(code, 0)
        self.assertIn(".factory/config.json", out)
        code, _, _ = self.run_cli("validate")
        self.assertEqual(code, 0)

    def test_validate_without_init_fails(self):
        code, _, err = self.run_cli("validate")
        self.assertEqual(code, 2)
        self.assertIn("run init", err)

    def test_status_without_init_exits_2(self):
        code, _, err = self.run_cli("status")
        self.assertEqual(code, 2)
        self.assertIn("not a factory repo (run init)", err)

    def test_next_without_init_exits_2(self):
        code, _, err = self.run_cli("next")
        self.assertEqual(code, 2)
        self.assertIn("not a factory repo (run init)", err)

    def test_add_and_status(self):
        self.run_cli("init")
        code, out, _ = self.run_cli("add", "Dark mode", "--kind", "ui")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "0001-dark-mode")
        code, out, _ = self.run_cli("status", "--json")
        rows = json.loads(out)
        self.assertEqual(rows[0]["id"], "0001-dark-mode")
        self.assertEqual(rows[0]["stage"], "idea")

    def test_advance_and_gate_refusal_exit_codes(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        code, out, _ = self.run_cli("advance", "0001-thing", "triage")
        self.assertEqual(code, 0)
        self.assertIn("0001-thing -> triage", out)
        code, _, err = self.run_cli("advance", "0001-thing", "spec")
        self.assertEqual(code, 2)
        self.assertIn("triage.md", err)

    def test_log_event(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        code, _, _ = self.run_cli("log", "0001-thing", "verify.green",
                                  "--data", '{"tests": "12 passed"}')
        self.assertEqual(code, 0)
        log = Path(self.repo, ".factory/items/0001-thing/log.jsonl").read_text()
        self.assertIn("verify.green", log)
        self.assertIn("12 passed", log)

    def test_bad_data_json_is_usage_error(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        code, _, err = self.run_cli("log", "0001-thing", "e", "--data", "{oops")
        self.assertEqual(code, 1)
        self.assertIn("--data", err)

    def test_malformed_usage_returns_one(self):
        code, _, err = self.run_cli("add")
        self.assertEqual(code, 1)
        self.assertIn("title", err)

    def test_add_empty_title_rejected(self):
        self.run_cli("init")
        code, _, err = self.run_cli("add", "")
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())
        items_dir = Path(self.repo, ".factory/items")
        self.assertFalse(items_dir.exists() and list(items_dir.iterdir()))

    def test_add_whitespace_only_title_rejected(self):
        self.run_cli("init")
        code, _, err = self.run_cli("add", "   ")
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())
        items_dir = Path(self.repo, ".factory/items")
        self.assertFalse(items_dir.exists() and list(items_dir.iterdir()))

    def test_add_multiline_title_rejected(self):
        self.run_cli("init")
        code, _, err = self.run_cli("add", "Evil\ntitle: hacked")
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())
        items_dir = Path(self.repo, ".factory/items")
        self.assertEqual(list(items_dir.iterdir()), [])

    def test_status_survives_corrupt_item(self):
        self.run_cli("init")
        self.run_cli("add", "Good one")
        self.run_cli("add", "Bad one")
        bad_path = Path(self.repo, ".factory/items/0002-bad-one/item.md")
        bad_path.write_text("not frontmatter\n", encoding="utf-8")
        code, out, err = self.run_cli("status")
        self.assertEqual(code, 2)
        self.assertIn("0002-bad-one", err)
        self.assertIn("0001-good-one", out)
        self.assertNotIn("0002-bad-one", out)

    def test_status_json_survives_corrupt_item(self):
        self.run_cli("init")
        self.run_cli("add", "Good one")
        self.run_cli("add", "Bad one")
        bad_path = Path(self.repo, ".factory/items/0002-bad-one/item.md")
        bad_path.write_text("not frontmatter\n", encoding="utf-8")
        code, out, err = self.run_cli("status", "--json")
        self.assertEqual(code, 2)
        self.assertIn("0002-bad-one", err)
        rows = json.loads(out)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "0001-good-one")

    def test_status_flags_dir_id_mismatch(self):
        # F3: dir/id mismatch causes exit 2, only original in output
        import shutil
        self.run_cli("init")
        self.run_cli("add", "Original")
        # Copy the item dir with a different name
        orig_dir = Path(self.repo, ".factory/items/0001-original")
        copy_dir = Path(self.repo, ".factory/items/0002-copy")
        shutil.copytree(orig_dir, copy_dir)
        # status should show error and only the original item
        code, out, err = self.run_cli("status")
        self.assertEqual(code, 2)
        self.assertIn("0002-copy", err)
        self.assertIn("does not match directory name", err)
        self.assertIn("0001-original", out)
        self.assertNotIn("0002-copy", out)

    def test_add_without_init_exits_2(self):
        # F4: add on uninitialized repo exits 2
        code, out, err = self.run_cli("add", "New item")
        self.assertEqual(code, 2)
        self.assertIn("not a factory repo (run init)", err)
        items_dir = Path(self.repo, ".factory/items")
        self.assertFalse(items_dir.exists() and list(items_dir.iterdir()))

    def test_cost_unknown_item_exits_1(self):
        self.run_cli("init")
        code, _, err = self.run_cli("cost", "0999-none")
        self.assertEqual(code, 1)
        self.assertIn("no such item", err)

    def test_cost_tier1_retroactive_with_zero_spend_events(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        self.run_cli("advance", "0001-thing", "triage")
        code, out, _ = self.run_cli("cost", "0001-thing")
        self.assertEqual(code, 0)
        self.assertIn("[proxy] stage idea:", out)
        self.assertIn("[measured] tokens: none logged", out)
        self.assertIn(
            "[unmeasured] UNMEASURED: orchestrator main-loop tokens", out)

    def test_cost_json_parses_with_contract_keys(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        code, out, _ = self.run_cli("cost", "0001-thing", "--json")
        self.assertEqual(code, 0)
        summary = json.loads(out)
        for key in ("item", "window", "elapsed_seconds", "active_seconds",
                    "waiting_seconds", "advances", "retries", "dispatches",
                    "stages", "measured", "unmeasured",
                    "invalid_spend_events"):
            self.assertIn(key, summary)
        self.assertIsNone(summary["measured"])
        self.assertEqual(summary["window"]["end"], "2026-07-03T12:00:00Z")

    def test_status_json_rows_carry_spend_without_stages(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        code, out, _ = self.run_cli("status", "--json")
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertIn("spend", rows[0])
        self.assertNotIn("stages", rows[0]["spend"])
        self.assertEqual(rows[0]["spend"]["item"], "0001-thing")

    def test_status_table_output_unchanged(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        code, out, _ = self.run_cli("status")
        self.assertEqual(code, 0)
        expected = f"{'0001-thing':<40} {'idea':<14} p{'-':<4} feature/mixed\n"
        self.assertEqual(out, expected)

    def test_validate_exits_2_on_bad_spend_event(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        self.run_cli("log", "0001-thing", "spend", "--data",
                     '{"stage": "implement", "dispatches": 2}')
        code, _, err = self.run_cli("validate")
        self.assertEqual(code, 2)
        self.assertIn("0001-thing/log.jsonl:2", err)
        self.assertIn("provenance", err)

    def test_log_spend_uses_unmodified_write_path(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        code, _, _ = self.run_cli(
            "log", "0001-thing", "spend", "--data",
            '{"provenance":"proxy","stage":"implement","dispatches":2}')
        self.assertEqual(code, 0)
        log = Path(self.repo,
                   ".factory/items/0001-thing/log.jsonl").read_text()
        self.assertIn('"event": "spend"', log)
        code, _, _ = self.run_cli("validate")
        self.assertEqual(code, 0)

    def test_status_json_and_cost_json_surface_corrupt_log_lines(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        log = Path(self.repo, ".factory/items/0001-thing/log.jsonl")
        with log.open("a", encoding="utf-8") as f:
            f.write('{"event": "spend", "ts": \n')
        code, out, _ = self.run_cli("status", "--json")
        self.assertEqual(code, 0)
        rows = json.loads(out)
        for row in rows:
            self.assertIsInstance(row["spend"]["corrupt_log_lines"], int)
        self.assertEqual(rows[0]["spend"]["corrupt_log_lines"], 1)
        code, out, _ = self.run_cli("cost", "0001-thing", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["corrupt_log_lines"], 1)

    def test_cost_and_advance_refuse_undecodable_item_cleanly(self):
        # Item spec 0009 §1 / AC 1: cost exits 1, advance exits 2, both
        # with the ItemError message on stderr — no traceback.
        self.run_cli("init")
        self.run_cli("add", "Thing")
        item_md = Path(self.repo, ".factory/items/0001-thing/item.md")
        item_md.write_bytes(b"\xff\xfe not utf-8 \x80")
        code, _, err = self.run_cli("cost", "0001-thing")
        self.assertEqual(code, 1)
        self.assertIn("0001-thing", err)
        self.assertIn("unreadable", err)
        code, _, err = self.run_cli("advance", "0001-thing", "triage")
        self.assertEqual(code, 2)
        self.assertIn("refused:", err)
        self.assertIn("unreadable", err)

    def test_status_survives_undecodable_item(self):
        # Item spec 0009 §1 / AC 2: the fleet still prints; the broken
        # item is reported on stderr and status exits 2.
        self.run_cli("init")
        self.run_cli("add", "Good one")
        self.run_cli("add", "Bad one")
        bad_path = Path(self.repo, ".factory/items/0002-bad-one/item.md")
        bad_path.write_bytes(b"\xff\xfe not utf-8 \x80")
        code, out, err = self.run_cli("status")
        self.assertEqual(code, 2)
        self.assertIn("0002-bad-one", err)
        self.assertIn("unreadable", err)
        self.assertIn("0001-good-one", out)
        self.assertNotIn("0002-bad-one", out)

    def test_status_text_prints_single_corrupt_log_notice(self):
        # Item spec 0009 §3 / AC 7: one aggregated stderr line,
        # count-after-label, table printed normally, exit code unchanged.
        self.run_cli("init")
        self.run_cli("add", "Thing")
        self.run_cli("add", "Other")
        for item in ("0001-thing", "0002-other"):
            log = Path(self.repo, f".factory/items/{item}/log.jsonl")
            with log.open("a", encoding="utf-8") as f:
                f.write('{"event": "spend", "ts": \n')
        code, out, err = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("0001-thing", out)
        self.assertIn("0002-other", out)
        self.assertEqual(
            err.strip(),
            "corrupt log lines: 2 across 2 items "
            "(skipped; run factory validate)")

    def test_status_text_clean_repo_prints_no_notice(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        code, out, err = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("0001-thing", out)
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
