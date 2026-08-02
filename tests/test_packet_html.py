import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, packet, paths


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


class TestCostDecisionHtml(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-08-02T06:00:00Z"
        items.save_item(self.repo, {
            "id": "0001-runaway", "title": "Runaway",
            "stage": "waiting-human", "kind": "backend", "priority": 2,
            "paused-from": "implement",
            "paused-reason": "cost breaker: 2 rework edges (threshold 2)",
            "created": "2026-08-02T00:00:00Z",
            "updated": "2026-08-02T06:00:00Z"}, "# Runaway\n")
        for ts in ("2026-08-02T01:00:00Z", "2026-08-02T02:00:00Z"):
            os.environ["FACTORY_NOW"] = ts
            logs.append_event(self.repo, "0001-runaway", "stage.advance",
                              {"from": "review", "to": "implement"})
        os.environ["FACTORY_NOW"] = "2026-08-02T06:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def section(self):
        page = packet.render_packet_html(self.repo, "0001-runaway")
        return page.split('<section id="cost-decision">', 1)[1].split(
            "</section>", 1)[0]

    def unprioritise(self):
        """B1 against the HTML render: packet.py renders its own section,
        so the markdown-only guards leave this path unchecked."""
        meta, body = items.load_item(self.repo, "0001-runaway")
        meta.pop("priority", None)
        items.save_item(self.repo, meta, body)
        for item_id, priority in (("0002-p1", 1), ("0003-p9", 9)):
            items.save_item(self.repo, {
                "id": item_id, "title": item_id, "stage": "plan",
                "kind": "backend", "priority": priority,
                "created": "2026-08-02T00:00:00Z",
                "updated": "2026-08-02T00:00:00Z"}, "")

    def test_html_backlog_line_names_the_items_it_could_not_read(self):
        """N4 on the HTML render: packet.py builds its own section, so
        the markdown assertion leaves this surface unguarded."""
        for item_id in ("0008-corrupt", "0009-corrupt"):
            bad = paths.items_dir(self.repo) / item_id
            bad.mkdir(parents=True, exist_ok=True)
            (bad / "item.md").write_bytes(b"\xff\xfe not utf-8")
        self.assertIn("0 actionable in total; 2 items unreadable and excluded",
                      self.section())

    def test_html_backlog_line_is_unqualified_when_every_item_reads(self):
        self.assertNotIn("unreadable and excluded", self.section())

    def test_html_claims_no_number_for_an_impossible_comparison(self):
        self.unprioritise()
        section = self.section()
        # `≤` is not an HTML-special character, so it escapes to itself.
        self.assertNotIn("≤ -", section)
        self.assertNotIn("0 actionable items", section)
        self.assertNotIn("nothing else is waiting at this priority", section)
        self.assertIn("factory priority", section)

    def test_html_section_leads_with_the_proxy_substrate(self):
        section = self.section()
        self.assertLess(section.index("[proxy] rework edges: 2"),
                        section.index("[unmeasured] tokens:"))

    def test_html_recommendation_and_three_consequences(self):
        section = self.section()
        self.assertIn("Recommended: narrow", section)
        self.assertNotIn("Recommended: continue", section)
        for option in ("continue", "narrow", "defer"):
            self.assertIn(f"{option} — ", section)

    def test_html_respond_names_cost_answer_and_not_factory_run(self):
        page = packet.render_packet_html(self.repo, "0001-runaway")
        respond = page.split('<section id="respond">', 1)[1].split(
            "</section>", 1)[0]
        self.assertIn("factory cost-answer 0001-runaway", respond)
        self.assertNotIn("/factory:run", respond)

    def test_html_section_absent_for_a_non_breaker_pause(self):
        meta, body = items.load_item(self.repo, "0001-runaway")
        meta["paused-reason"] = "the implement skill is unavailable"
        items.save_item(self.repo, meta, body)
        page = packet.render_packet_html(self.repo, "0001-runaway")
        self.assertNotIn('<section id="cost-decision">', page)
        respond = page.split('<section id="respond">', 1)[1].split(
            "</section>", 1)[0]
        self.assertIn("/factory:run", respond)


if __name__ == "__main__":
    unittest.main()
