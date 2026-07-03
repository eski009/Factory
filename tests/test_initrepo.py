import json
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, paths


class InitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_init_creates_expected_tree(self):
        created = initrepo.init(self.repo, product="demo")
        self.assertTrue((self.repo / ".factory/config.json").exists())
        self.assertTrue((self.repo / ".factory/ledgers/bids.jsonl").exists())
        self.assertTrue((self.repo / "docs/factory/roadmap.md").exists())
        self.assertTrue((self.repo / "docs/factory/brain/vision.md").exists())
        self.assertTrue((self.repo / "docs/factory/council/product.md").exists())
        self.assertTrue((self.repo / "docs/factory/packets").is_dir())
        config = json.loads((self.repo / ".factory/config.json").read_text())
        self.assertEqual(config["merge"], "auto")
        self.assertEqual(config["gates"], ["design"])
        self.assertEqual(config["product"], "demo")
        self.assertEqual(created, sorted(created))

    def test_init_is_idempotent_and_never_clobbers(self):
        initrepo.init(self.repo)
        marker = self.repo / "docs/factory/brain/vision.md"
        marker.write_text("MY EDIT\n", encoding="utf-8")
        second = initrepo.init(self.repo)
        self.assertEqual(second, [])
        self.assertEqual(marker.read_text(), "MY EDIT\n")

    def test_validate_missing_config(self):
        errors = initrepo.validate_tree(self.repo)
        self.assertEqual(len(errors), 1)
        self.assertIn("run init", errors[0])

    def test_validate_clean_tree(self):
        initrepo.init(self.repo)
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_validate_flags_bad_item_and_bad_ledger_line(self):
        initrepo.init(self.repo)
        bad = paths.item_dir(self.repo, "0001-bad")
        bad.mkdir(parents=True)
        (bad / "item.md").write_text("not frontmatter\n", encoding="utf-8")
        (paths.ledgers_dir(self.repo) / "bids.jsonl").write_text("{oops\n", encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertEqual(len(errors), 2)

    def test_validate_flags_bad_log_line(self):
        initrepo.init(self.repo)
        meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "")
        log_path = paths.item_dir(self.repo, "0001-x") / "log.jsonl"
        log_path.write_text('{"event": "item.created", "ts": "x"}\n{oops\n',
                             encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertEqual(errors, ["0001-x/log.jsonl:2: invalid JSON"])

    def test_validate_flags_schema_violation(self):
        initrepo.init(self.repo)
        meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "")
        item_md = paths.item_dir(self.repo, "0001-x") / "item.md"
        item_md.write_text(item_md.read_text().replace("stage: idea", "stage: shipping"))
        self.assertTrue(initrepo.validate_tree(self.repo))


if __name__ == "__main__":
    unittest.main()
