import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import dispatch, initrepo, items


def put(repo, item_id, stage, priority=None, kind="mixed"):
    meta = {"id": item_id, "title": item_id, "stage": stage, "kind": kind,
            "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
    if priority:
        meta["priority"] = priority
    items.save_item(repo, meta, "")


class TestNextItem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_repo_returns_none(self):
        self.assertIsNone(dispatch.next_item(self.repo))

    def test_priority_order_wins(self):
        put(self.repo, "0001-low", "spec", priority=5)
        put(self.repo, "0002-high", "idea", priority=1)
        self.assertEqual(dispatch.next_item(self.repo)["id"], "0002-high")

    def test_missing_priority_sorts_last_then_id(self):
        put(self.repo, "0001-a", "idea")
        put(self.repo, "0002-b", "idea", priority=3)
        self.assertEqual(dispatch.next_item(self.repo)["id"], "0002-b")

    def test_done_blocked_waiting_not_actionable(self):
        for i, stage in enumerate(("done", "blocked", "waiting-human"), 1):
            put(self.repo, f"000{i}-x{i}", stage, priority=1)
        self.assertIsNone(dispatch.next_item(self.repo))

    def test_pending_human_lists_waiting(self):
        put(self.repo, "0001-w", "waiting-human", priority=1)
        put(self.repo, "0002-n", "idea", priority=2)
        pending = dispatch.pending_human(self.repo)
        self.assertEqual([m["id"] for m in pending], ["0001-w"])


if __name__ == "__main__":
    unittest.main()
