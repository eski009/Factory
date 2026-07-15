import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.factory import factory
from scripts.factory.lib import initrepo, items, logs


class TestCliJourneys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-15T12:00:00Z"
        factory.main(["--repo", str(self.repo), "add", "Thing"])

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_journeys_sets_frontmatter_and_event(self):
        code = factory.main(["--repo", str(self.repo), "journeys", "0001-thing", "J-001,J-002"])
        self.assertEqual(code, 0)
        meta, _ = items.load_item(self.repo, "0001-thing")
        self.assertEqual(meta["journeys"], "J-001,J-002")
        self.assertEqual(logs.count_events(self.repo, "0001-thing", "journeys.set"), 1)

    def test_journeys_rejects_bad_value_exit_2(self):
        with patch("sys.stderr", new_callable=StringIO) as err:
            code = factory.main(["--repo", str(self.repo), "journeys", "0001-thing", "J-1"])
        self.assertEqual(code, 2)
        self.assertIn("refused", err.getvalue())

    def test_item_with_journeys_passes_validate(self):
        factory.main(["--repo", str(self.repo), "journeys", "0001-thing", "none"])
        self.assertEqual(factory.main(["--repo", str(self.repo), "validate"]), 0)


if __name__ == "__main__":
    unittest.main()
