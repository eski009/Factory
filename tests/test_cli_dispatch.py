import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory


class CliDispatchTest(unittest.TestCase):
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

    def test_next_on_empty_repo_prints_nothing_actionable(self):
        self.run_cli("init")
        code, out, _ = self.run_cli("next")
        self.assertEqual(code, 0)
        self.assertIn("nothing actionable", out)

    def test_next_json_on_empty_repo_prints_null(self):
        self.run_cli("init")
        code, out, _ = self.run_cli("next", "--json")
        self.assertEqual(code, 0)
        parsed = json.loads(out)
        self.assertIsNone(parsed)

    def test_next_after_add_prints_id_and_stage(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        code, out, _ = self.run_cli("next")
        self.assertEqual(code, 0)
        self.assertIn("0001-thing", out)
        self.assertIn("idea", out)

    def test_packet_prints_path_and_file_exists(self):
        self.run_cli("init")
        self.run_cli("add", "Thing")
        code, out, _ = self.run_cli("packet", "0001-thing")
        self.assertEqual(code, 0)
        path = out.strip()
        self.assertTrue(Path(path).exists())

    def test_packet_unknown_item_exits_1(self):
        self.run_cli("init")
        code, _, err = self.run_cli("packet", "0999-nope")
        self.assertEqual(code, 1)
        self.assertIn("no such item", err)

    def test_next_with_corrupt_item_exits_2_with_error_message(self):
        self.run_cli("init")
        self.run_cli("add", "Good Item")
        # Corrupt a second item by writing garbage to .factory/items/0002-bad/item.md
        items_dir = Path(self.repo) / ".factory" / "items" / "0002-bad"
        items_dir.mkdir(parents=True, exist_ok=True)
        (items_dir / "item.md").write_text("garbage data\n", encoding="utf-8")
        code, out, err = self.run_cli("next")
        self.assertEqual(code, 2)
        self.assertIn("0002-bad", err)


if __name__ == "__main__":
    unittest.main()
