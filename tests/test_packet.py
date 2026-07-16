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

    def test_spend_section_three_bullets_before_respond(self):
        text = packet.render_packet(self.repo, "0001-thing")
        self.assertIn("## Spend", text)
        self.assertLess(text.index("## Recent events"), text.index("## Spend"))
        self.assertLess(text.index("## Spend"), text.index("## Respond"))
        section = text.split("## Spend\n")[1].split("\n\n## Respond")[0]
        lines = section.splitlines()
        self.assertEqual(len(lines), 3)
        for line, tag in zip(lines, ("[proxy]", "[measured]", "[unmeasured]")):
            self.assertTrue(line.startswith(f"- {tag}"), line)

    def test_spend_section_is_honest_about_unmeasured(self):
        text = packet.render_packet(self.repo, "0001-thing")
        self.assertIn("UNMEASURED", text)
        self.assertIn("- [measured] tokens: none logged", text)
        self.assertNotIn("$0", text)
        self.assertNotIn("≈$", text)

    def test_packet_lists_assurance_artifacts_and_verbs(self):
        text = packet.render_packet(self.repo, "0001-thing")
        self.assertIn("assurance/verdicts.json", text)
        self.assertIn("assurance/impact.json", text)
        self.assertIn("factory confirm", text)
        self.assertIn("factory waive", text)

    def test_packet_renders_with_corrupt_log_line(self):
        log = self.repo / ".factory/items/0001-thing/log.jsonl"
        with log.open("a", encoding="utf-8") as f:
            f.write('{"event": "spend", "ts": \n')
        text = packet.render_packet(self.repo, "0001-thing")
        self.assertIn("## Spend", text)
        self.assertIn(", corrupt log lines skipped: 1", text)
        section = text.split("## Spend\n")[1].split("\n\n## Respond")[0]
        self.assertEqual(len(section.splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
