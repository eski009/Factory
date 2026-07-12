import unittest

from scripts.factory.lib import work


class ClaudeBackendTest(unittest.TestCase):
    def test_argv_has_headless_flags(self):
        argv = work._claude_argv("do it", "/wt", "claude-sonnet-5", "off")
        self.assertEqual(argv[0], "claude")
        self.assertIn("-p", argv)
        self.assertIn("--output-format", argv)
        self.assertIn("json", argv)
        self.assertIn("--add-dir", argv)
        self.assertIn("/wt", argv)
        self.assertIn("--model", argv)
        self.assertIn("claude-sonnet-5", argv)
        self.assertIn("--permission-mode", argv)
        self.assertIn(work.CLAUDE_PERMISSION_MODE, argv)

    def test_parse_success(self):
        raw = {"exit_code": 0, "timed_out": False, "stderr": "",
               "stdout": ('{"subtype": "success", "result": "done it", '
                          '"total_cost_usd": 0.012, '
                          '"usage": {"input_tokens": 900, '
                          '"output_tokens": 120}}')}
        parsed = work._claude_parse(raw)
        self.assertEqual(parsed["status"], "done")
        self.assertEqual(parsed["usage"]["input"], 900)
        self.assertEqual(parsed["usage"]["total"], 1020)
        self.assertEqual(parsed["summary"], "done it")
        self.assertEqual(parsed["cost_usd"], 0.012)

    def test_parse_error_subtype_fails(self):
        raw = {"exit_code": 0, "timed_out": False, "stderr": "",
               "stdout": '{"subtype": "error_during_execution", "usage": {}}'}
        parsed = work._claude_parse(raw)
        self.assertEqual(parsed["status"], "failed")

    def test_parse_rate_limit_reason(self):
        raw = {"exit_code": 1, "timed_out": False,
               "stderr": "Error: 429 overloaded_error",
               "stdout": "{}"}
        parsed = work._claude_parse(raw)
        self.assertEqual(parsed["reason"], "rate_limited")


if __name__ == "__main__":
    unittest.main()
