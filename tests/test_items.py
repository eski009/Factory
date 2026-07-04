import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import items, paths

VALID = """---
id: 0001-dark-mode
title: Dark mode
stage: idea
kind: ui
created: 2026-07-03T10:00:00Z
updated: 2026-07-03T10:00:00Z
---

# Dark mode
"""


class TestParseRender(unittest.TestCase):
    def test_parse_valid_item(self):
        meta, body = items.parse_item(VALID)
        self.assertEqual(meta["id"], "0001-dark-mode")
        self.assertEqual(meta["stage"], "idea")
        self.assertEqual(body, "# Dark mode\n")

    def test_priority_parsed_as_int(self):
        text = VALID.replace("kind: ui", "kind: ui\npriority: 2")
        meta, _ = items.parse_item(text)
        self.assertEqual(meta["priority"], 2)

    def test_non_integer_priority_rejected(self):
        text = VALID.replace("kind: ui", "kind: ui\npriority: high")
        with self.assertRaises(items.ItemError):
            items.parse_item(text)

    def test_missing_required_field_rejected(self):
        with self.assertRaises(items.ItemError):
            items.parse_item(VALID.replace("stage: idea\n", ""))

    def test_unknown_field_rejected(self):
        with self.assertRaises(items.ItemError):
            items.parse_item(VALID.replace("kind: ui", "kind: ui\ncolour: red"))

    def test_unterminated_frontmatter_rejected(self):
        with self.assertRaises(items.ItemError):
            items.parse_item("---\nid: x\n")

    def test_render_parse_roundtrip(self):
        meta, body = items.parse_item(VALID)
        again, body2 = items.parse_item(items.render_item(meta, body))
        self.assertEqual(meta, again)
        self.assertEqual(body.strip(), body2.strip())

    def test_render_is_deterministic_and_lf_terminated(self):
        meta, body = items.parse_item(VALID)
        out = items.render_item(meta, body)
        self.assertTrue(out.endswith("\n"))
        self.assertNotIn("\r", out)

    def test_render_rejects_multiline_value(self):
        meta, body = items.parse_item(VALID)
        meta["title"] = "Evil\ntitle: hacked"
        with self.assertRaises(items.ItemError):
            items.render_item(meta, body)

    def test_render_rejects_unknown_field(self):
        meta, body = items.parse_item(VALID)
        meta["colour"] = "red"
        with self.assertRaises(items.ItemError):
            items.render_item(meta, body)

    def test_render_rejects_untrimmed_value(self):
        meta, body = items.parse_item(VALID)
        meta["title"] = "Dark mode  "
        with self.assertRaises(items.ItemError):
            items.render_item(meta, body)


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_load(self):
        meta, body = items.parse_item(VALID)
        items.save_item(self.repo, meta, body)
        loaded, loaded_body = items.load_item(self.repo, "0001-dark-mode")
        self.assertEqual(loaded, meta)

    def test_load_missing_raises(self):
        with self.assertRaises(items.ItemError):
            items.load_item(self.repo, "0999-nope")

    def test_load_dir_id_mismatch_raises(self):
        # A copied/renamed item dir whose item.md still carries the
        # original id must be refused, not silently loaded.
        meta, body = items.parse_item(VALID)
        items.save_item(self.repo, meta, body)
        copy_dir = paths.item_dir(self.repo, "0002-dark-mode-copy")
        shutil.copytree(paths.item_dir(self.repo, "0001-dark-mode"), copy_dir)
        with self.assertRaises(items.ItemError):
            items.load_item(self.repo, "0002-dark-mode-copy")

    def test_list_items_sorted(self):
        for i, title in ((2, "b"), (1, "a")):
            meta, _ = items.parse_item(VALID)
            meta["id"] = f"000{i}-{title}"
            items.save_item(self.repo, meta, "")
        ids = [m["id"] for m in items.list_items(self.repo)]
        self.assertEqual(ids, ["0001-a", "0002-b"])

    def test_new_item_id_increments(self):
        self.assertEqual(items.new_item_id(self.repo, "Dark Mode!"), "0001-dark-mode")
        meta, _ = items.parse_item(VALID)
        items.save_item(self.repo, meta, "")
        self.assertEqual(items.new_item_id(self.repo, "Next"), "0002-next")

    def test_slugify(self):
        self.assertEqual(items.slugify("Hello, World! 42"), "hello-world-42")
        self.assertEqual(items.slugify("???"), "item")

    def test_list_items_safe_excludes_id_mismatch(self):
        # F3: when dir name doesn't match item.md id, item is excluded and error recorded
        meta, _ = items.parse_item(VALID)
        items.save_item(self.repo, meta, "")
        # Copy the item dir with a different name (dir name won't match id)
        copy_dir = paths.item_dir(self.repo, "0002-dark-mode-copy")
        shutil.copytree(paths.item_dir(self.repo, "0001-dark-mode"), copy_dir)
        # list_items_safe should return only the original, with error for the copy
        metas, errors = items.list_items_safe(self.repo)
        ids = [m["id"] for m in metas]
        self.assertEqual(ids, ["0001-dark-mode"])
        self.assertEqual(len(errors), 1)
        self.assertIn("0002-dark-mode-copy", errors[0])
        self.assertIn("does not match directory name", errors[0])


if __name__ == "__main__":
    unittest.main()
