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


if __name__ == "__main__":
    unittest.main()
