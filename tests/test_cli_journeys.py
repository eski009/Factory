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

    def _write_graph(self, journeys):
        graph = self.repo / "docs" / "factory" / "journeys" / "graph.json"
        graph.parent.mkdir(parents=True, exist_ok=True)
        graph.write_text(
            '{"version": 1, "journeys": ' + journeys + '}', encoding="utf-8")

    def test_status_surfaces_journey_coverage_debt(self):
        self._write_graph(
            '[{"id": "J-001", "slug": "a", "title": "A",'
            ' "criticality": "core", "status": "inventory"},'
            ' {"id": "J-002", "slug": "b", "title": "B",'
            ' "criticality": "high", "status": "draft",'
            ' "contract": "contracts/J-002-b.md"},'
            ' {"id": "J-003", "slug": "c", "title": "C",'
            ' "criticality": "standard", "status": "approved",'
            ' "contract": "contracts/J-003-c.md"}]')
        with patch("sys.stdout", new_callable=StringIO) as out:
            code = factory.main(["--repo", str(self.repo), "status"])
        self.assertEqual(code, 0)
        self.assertIn("journey coverage debt: 1 of 3 journeys inventory-only, "
                      "1 draft contracts", out.getvalue())

    def test_status_silent_when_no_debt_or_no_graph(self):
        with patch("sys.stdout", new_callable=StringIO) as out:
            factory.main(["--repo", str(self.repo), "status"])
        self.assertNotIn("coverage debt", out.getvalue())
        self._write_graph(
            '[{"id": "J-001", "slug": "a", "title": "A",'
            ' "criticality": "core", "status": "approved",'
            ' "contract": "contracts/J-001-a.md"}]')
        with patch("sys.stdout", new_callable=StringIO) as out:
            factory.main(["--repo", str(self.repo), "status"])
        self.assertNotIn("coverage debt", out.getvalue())


if __name__ == "__main__":
    unittest.main()
