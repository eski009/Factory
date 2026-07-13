import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory
from scripts.factory.lib import items


class CliTierTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.run_cli("init")
        self.run_cli("add", "A thing", "--kind", "backend")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(self.repo), *args])
        return code, out.getvalue(), err.getvalue()

    def _only_id(self):
        return items.list_items(self.repo)[0]["id"]

    def test_add_with_tier(self):
        code, out, err = self.run_cli("add", "Big thing", "--kind", "mixed",
                                      "--tier", "epic")
        self.assertEqual(code, 0, err)

    def test_tier_set_and_reject(self):
        item_id = self._only_id()
        code, out, err = self.run_cli("tier", item_id, "bug")
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli("tier", item_id, "mega")
        self.assertEqual(code, 2)

    def test_status_shows_tier(self):
        item_id = self._only_id()
        self.run_cli("tier", item_id, "epic")
        code, out, err = self.run_cli("status")
        self.assertEqual(code, 0, err)
        self.assertIn("epic", out)

    def test_add_bad_tier_rejected(self):
        code, out, err = self.run_cli("add", "X", "--tier", "mega")
        self.assertEqual(code, 1)   # argparse choices -> SystemExit -> exit 1

    def test_add_empty_tier_rejected(self):
        code, out, err = self.run_cli("add", "X", "--tier", "")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
