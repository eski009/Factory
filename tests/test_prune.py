import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import council, initrepo, prune


class TestPropose(unittest.TestCase):
    def test_no_duplicates_all_kept(self):
        lines = ["# Role", "- a", "- b", "prose"]
        kept, archived = prune.propose(lines)
        self.assertEqual(kept, lines)
        self.assertEqual(archived, [])

    def test_duplicates_archived_first_kept(self):
        lines = ["- a", "- b", "- a", "- a"]
        kept, archived = prune.propose(lines)
        self.assertEqual(kept, ["- a", "- b"])
        self.assertEqual(archived, ["- a", "- a"])

    def test_provenance_invariant(self):
        lines = ["# h", "- x", "- x", "prose", "- y", "- x"]
        kept, archived = prune.propose(lines)
        self.assertEqual(sorted(kept + archived), sorted(lines))

    def test_non_claim_duplicates_untouched(self):
        lines = ["prose", "prose"]
        kept, archived = prune.propose(lines)
        self.assertEqual(kept, lines)
        self.assertEqual(archived, [])


class TestPruneRole(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        self.path = self.repo / "docs/factory/council/customer.md"
        self.path.write_text("# Role\n- dup\n- dup\n- keep\n", encoding="utf-8")

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_dry_run_writes_nothing(self):
        result = prune.prune_role(self.repo, "customer")
        self.assertEqual(result["archived"], 1)
        self.assertIsNone(result["archive_path"])
        self.assertIn("- dup\n- dup", self.path.read_text())
        self.assertFalse((self.repo / ".factory/pruning/customer.md").exists())

    def test_apply_rewrites_and_archives(self):
        result = prune.prune_role(self.repo, "customer", apply=True)
        self.assertEqual(result["kept"], 3)
        self.assertEqual(result["archived"], 1)
        self.assertEqual(self.path.read_text(), "# Role\n- dup\n- keep\n")
        archive = Path(result["archive_path"]).read_text()
        self.assertIn("## pruned 2026-07-03T12:00:00Z", archive)
        self.assertIn("- dup", archive)

    def test_apply_with_nothing_to_archive_writes_no_archive(self):
        prune.prune_role(self.repo, "customer", apply=True)
        result = prune.prune_role(self.repo, "customer", apply=True)
        self.assertEqual(result["archived"], 0)

    def test_unknown_role_refused(self):
        with self.assertRaises(council.CouncilError):
            prune.prune_role(self.repo, "intern")

    def test_missing_role_file_raises_council_error(self):
        # M2: a valid role with no role doc on disk must refuse with a
        # CouncilError ("run init"), not a raw FileNotFoundError.
        self.path.unlink()
        with self.assertRaises(council.CouncilError):
            prune.prune_role(self.repo, "customer")


if __name__ == "__main__":
    unittest.main()
