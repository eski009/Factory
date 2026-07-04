import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs


def put(repo, item_id="0001-thing", stage="idea", kind="ui"):
    meta = {"id": item_id, "title": "Thing", "stage": stage, "kind": kind,
            "created": "2026-07-03T10:00:00Z",
            "updated": "2026-07-03T10:00:00Z"}
    items.save_item(repo, meta, "# Thing\n")


class TestSetPriority(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_set_priority_on_fresh_item(self):
        put(self.repo)
        meta = items.set_priority(self.repo, "0001-thing", 3)
        self.assertEqual(meta["priority"], 3)
        self.assertEqual(meta["updated"], "2026-07-03T12:00:00Z")

    def test_set_priority_overwrites(self):
        put(self.repo)
        items.set_priority(self.repo, "0001-thing", 2)
        meta = items.set_priority(self.repo, "0001-thing", 5)
        self.assertEqual(meta["priority"], 5)
        loaded, _ = items.load_item(self.repo, "0001-thing")
        self.assertEqual(loaded["priority"], 5)

    def test_set_priority_non_existent_item_raises(self):
        with self.assertRaises(items.ItemError) as ctx:
            items.set_priority(self.repo, "0999-nope", 1)
        self.assertIn("no such item", str(ctx.exception))

    def test_set_priority_zero_raises(self):
        put(self.repo)
        with self.assertRaises(items.ItemError) as ctx:
            items.set_priority(self.repo, "0001-thing", 0)
        self.assertIn("priority must be >= 1", str(ctx.exception))

    def test_set_priority_negative_raises(self):
        put(self.repo)
        with self.assertRaises(items.ItemError) as ctx:
            items.set_priority(self.repo, "0001-thing", -5)
        self.assertIn("priority must be >= 1", str(ctx.exception))

    def test_set_priority_appends_event(self):
        put(self.repo)
        items.set_priority(self.repo, "0001-thing", 4)
        events = logs.read_events(self.repo, "0001-thing")
        last_event = events[-1]
        self.assertEqual(last_event["event"], "priority.set")
        self.assertEqual(last_event["data"], {"priority": 4})

    def test_set_priority_preserves_body(self):
        meta = {"id": "0001-thing", "title": "Thing", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z",
                "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "# Thing\n\nSome content\n")
        items.set_priority(self.repo, "0001-thing", 2)
        _, body = items.load_item(self.repo, "0001-thing")
        self.assertIn("Some content", body)

    def test_set_priority_stage_unchanged(self):
        put(self.repo, stage="design")
        items.set_priority(self.repo, "0001-thing", 1)
        loaded, _ = items.load_item(self.repo, "0001-thing")
        self.assertEqual(loaded["stage"], "design")

    def test_set_priority_updates_updated_timestamp(self):
        put(self.repo)
        self.assertEqual(os.environ["FACTORY_NOW"], "2026-07-03T12:00:00Z")
        os.environ["FACTORY_NOW"] = "2026-07-04T10:00:00Z"
        items.set_priority(self.repo, "0001-thing", 1)
        loaded, _ = items.load_item(self.repo, "0001-thing")
        self.assertEqual(loaded["updated"], "2026-07-04T10:00:00Z")

    def test_set_priority_keeps_tree_valid(self):
        put(self.repo)
        self.assertEqual(initrepo.validate_tree(self.repo), [])
        items.set_priority(self.repo, "0001-thing", 3)
        # priority.set is gate-neutral: the tree still validates and the
        # stage reconstructed from the log is unaffected.
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_set_priority_rejects_non_integer(self):
        put(self.repo)
        for bad in (2.5, True, "3"):
            with self.assertRaises(items.ItemError) as ctx:
                items.set_priority(self.repo, "0001-thing", bad)
            self.assertIn("integer", str(ctx.exception))
        # a rejected set must not have mutated the item (guard fires first)
        loaded, _ = items.load_item(self.repo, "0001-thing")
        self.assertNotIn("priority", loaded)


if __name__ == "__main__":
    unittest.main()
