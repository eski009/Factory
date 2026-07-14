import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, packet


class TestPacketHtml(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        self.meta = {
            "id": "0001-thing", "title": "Thing <one>",
            "stage": "waiting-human", "kind": "ui", "priority": 1,
            "paused-from": "design", "paused-reason": "pick A & B",
            "created": "2026-07-03T10:00:00Z",
            "updated": "2026-07-03T10:00:00Z",
        }
        items.save_item(self.repo, self.meta, "# Thing\n")
        self.item_dir = self.repo / ".factory/items/0001-thing"
        (self.item_dir / "spec.md").write_text("spec\n", encoding="utf-8")
        logs.append_event(self.repo, "0001-thing", "stage.<advance>",
                          {"from": "spec", "to": "design & review"})

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_full_document_callout_links_and_escaping(self):
        text = packet.render_packet_html(self.repo, "0001-thing")
        self.assertTrue(text.startswith("<!doctype html"))
        self.assertTrue(text.rstrip().endswith("</html>"))
        self.assertIn("Thing &lt;one&gt;", text)
        self.assertIn("pick A &amp; B", text)
        self.assertIn("View the options", text)
        self.assertIn((self.item_dir / "spec.md").resolve().as_uri(), text)
        html_view = text.split('<section id="view-options">', 1)[1].split(
            "</section>", 1)[0]
        self.assertIn((self.item_dir / "spec.md").resolve().as_uri(), html_view)
        self.assertNotIn((self.item_dir / "plan.md").resolve().as_uri(), text)
        self.assertIn("plan.md (not yet)", text)
        self.assertIn("stage.&lt;advance&gt;", text)

    def test_hosted_url_is_primary_in_both_renderers(self):
        self.meta["paused-reason"] = (
            "pick a design — view: https://claude.ai/artifact/abc")
        items.save_item(self.repo, self.meta, "# Thing\n")
        options = self.item_dir / "design/options.html"
        options.parent.mkdir(parents=True)
        options.write_text("<!doctype html>\n", encoding="utf-8")
        hosted = "https://claude.ai/artifact/abc"

        markdown = packet.render_packet(self.repo, "0001-thing")
        md_view = markdown.split("## View the options\n", 1)[1].split(
            "\n\n## Artifacts", 1)[0]
        self.assertEqual(md_view.find(hosted), md_view.find("http"))
        self.assertLess(md_view.find(hosted), md_view.find("file://"))

        page = packet.render_packet_html(self.repo, "0001-thing")
        html_view = page.split('<section id="view-options">', 1)[1].split(
            "</section>", 1)[0]
        self.assertEqual(html_view.find(hosted), html_view.find("http"))
        self.assertLess(html_view.find(hosted), html_view.find("file://"))

    def test_view_section_prefers_html_to_markdown(self):
        markdown = packet.render_packet(self.repo, "0001-thing")
        view = markdown.split("## View the options\n", 1)[1].split(
            "\n\n## Artifacts", 1)[0]
        first_url = view.split("](", 1)[1].split(")", 1)[0]
        self.assertTrue(first_url.endswith(".html"), first_url)
        self.assertFalse(first_url.endswith(".md"), first_url)

    def test_view_links_ignores_reason_without_url(self):
        links = packet.view_links(self.repo, "0001-thing", self.meta)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0][0], "Open this packet as a page")


if __name__ == "__main__":
    unittest.main()
