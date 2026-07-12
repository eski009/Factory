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

    def test_argv_network_off_disallows_web_tools(self):
        argv = work._claude_argv("do it", "/wt", None, "off")
        self.assertIn("--disallowedTools", argv)
        i = argv.index("--disallowedTools")
        self.assertIn("WebFetch", argv[i + 1])
        self.assertIn("WebSearch", argv[i + 1])

    def test_argv_network_on_has_no_disallowed_tools(self):
        argv = work._claude_argv("do it", "/wt", None, "on")
        self.assertNotIn("--disallowedTools", argv)

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

    def test_parse_timeout_reason(self):
        raw = {"exit_code": 124, "timed_out": True, "stderr": "", "stdout": ""}
        parsed = work._claude_parse(raw)
        self.assertEqual(parsed["status"], "failed")
        self.assertEqual(parsed["reason"], "timeout")


class CodexBackendTest(unittest.TestCase):
    def test_argv_workspace_write_when_network_off(self):
        argv = work._codex_argv("do it", "/wt", "gpt-x", "off",
                                "workspace-write")
        self.assertEqual(argv[:2], ["codex", "exec"])
        self.assertIn("--json", argv)
        self.assertIn("-C", argv)
        self.assertIn("/wt", argv)
        self.assertIn("-a", argv)
        self.assertIn("never", argv)
        i = argv.index("--sandbox")
        self.assertEqual(argv[i + 1], "workspace-write")

    def test_argv_full_access_when_network_on(self):
        argv = work._codex_argv("do it", "/wt", None, "on", "workspace-write")
        i = argv.index("--sandbox")
        self.assertEqual(argv[i + 1], "danger-full-access")

    def test_parse_sums_usage_and_reads_message(self):
        raw = {"exit_code": 0, "timed_out": False, "stderr": "", "stdout": "\n".join([
            '{"type": "thread.started"}',
            '{"type": "turn.completed", "usage": {"input_tokens": 400, "output_tokens": 60}}',
            '{"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 20}}',
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "all done"}}',
        ])}
        parsed = work._codex_parse(raw)
        self.assertEqual(parsed["status"], "done")
        self.assertEqual(parsed["usage"]["input"], 500)
        self.assertEqual(parsed["usage"]["output"], 80)
        self.assertEqual(parsed["summary"], "all done")

    def test_parse_turn_failed_is_failure(self):
        raw = {"exit_code": 1, "timed_out": False, "stderr": "", "stdout": "\n".join([
            '{"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}',
            '{"type": "turn.failed"}',
        ])}
        parsed = work._codex_parse(raw)
        self.assertEqual(parsed["status"], "failed")

    def test_argv_includes_model_when_given(self):
        argv = work._codex_argv("do it", "/wt", "gpt-x", "off", "workspace-write")
        self.assertIn("-m", argv)
        self.assertIn("gpt-x", argv)

    def test_argv_omits_model_when_none(self):
        argv = work._codex_argv("do it", "/wt", None, "on", "workspace-write")
        self.assertNotIn("-m", argv)

    def test_parse_turn_failed_reason_crash(self):
        raw = {"exit_code": 1, "timed_out": False, "stderr": "", "stdout": "\n".join([
            '{"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}',
            '{"type": "turn.failed"}',
        ])}
        parsed = work._codex_parse(raw)
        self.assertEqual(parsed["status"], "failed")
        self.assertEqual(parsed["reason"], "crash")

    def test_parse_rate_limit_reason(self):
        raw = {"exit_code": 1, "timed_out": False, "stderr": "Error: 429 overloaded", "stdout": ""}
        parsed = work._codex_parse(raw)
        self.assertEqual(parsed["reason"], "rate_limited")

    def test_parse_timeout_reason(self):
        raw = {"exit_code": 124, "timed_out": True, "stderr": "", "stdout": ""}
        parsed = work._codex_parse(raw)
        self.assertEqual(parsed["status"], "failed")
        self.assertEqual(parsed["reason"], "timeout")


if __name__ == "__main__":
    unittest.main()
