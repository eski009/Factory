import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, packet


class TestPacket(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        meta = {"id": "0001-thing", "title": "Thing", "stage": "waiting-human",
                "kind": "ui", "priority": 1, "paused-from": "design",
                "paused-reason": "pick a design option",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "# Thing\n")
        (self.repo / ".factory/items/0001-thing/spec.md").write_text("spec\n")
        logs.append_event(self.repo, "0001-thing", "stage.advance",
                          {"from": "spec", "to": "design"})

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_render_contains_state_and_reason(self):
        text = packet.render_packet(self.repo, "0001-thing")
        self.assertIn("# Thing", text)
        self.assertIn("waiting-human", text)
        self.assertIn("pick a design option", text)
        self.assertIn("spec.md: yes", text)
        self.assertIn("plan.md: no", text)
        self.assertIn("stage.advance", text)
        self.assertIn("## Respond", text)
        self.assertIn("factory choice", text)
        self.assertNotIn("record your decision in the artifact", text)

    def test_write_packet_path_and_determinism(self):
        path = packet.write_packet(self.repo, "0001-thing")
        self.assertEqual(path, self.repo / "docs/factory/packets/0001-thing.md")
        first = path.read_text()
        packet.write_packet(self.repo, "0001-thing")
        self.assertEqual(path.read_text(), first)


if __name__ == "__main__":
    unittest.main()
