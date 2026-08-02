import os
import re
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, machine, packet, paths
# One pattern, one definition: a second copy here could drift back to the
# unfalsifiable single-form filter without the self-check noticing.
from tests.test_packet import REWORK_FIGURE_RE


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
        self.park("0001-runaway",
                  "cost breaker: 2 rework edges (threshold 2)")

    def park(self, item_id, reason, priority=2):
        """The HTML twin of `TestCostDecisionPacket.park` — park through
        `machine.advance`, the way production parks, so the event
        `## Recent events` dumps (`machine.py:307-308`) is present here
        too. See that docstring for why the old `items.save_item`
        fixture made the whole-page guard unfalsifiable (pass 2, F3)."""
        os.environ["FACTORY_NOW"] = "2026-08-02T00:00:00Z"
        items.save_item(self.repo, {
            "id": item_id, "title": "Runaway", "stage": "implement",
            "kind": "backend", "priority": priority,
            "created": "2026-08-02T00:00:00Z",
            "updated": "2026-08-02T00:00:00Z"}, "# Runaway\n")
        for ts in ("2026-08-02T01:00:00Z", "2026-08-02T02:00:00Z"):
            os.environ["FACTORY_NOW"] = ts
            logs.append_event(self.repo, item_id, "stage.advance",
                              {"from": "review", "to": "implement"})
        os.environ["FACTORY_NOW"] = "2026-08-02T06:00:00Z"
        machine.advance(self.repo, item_id, "waiting-human", reason=reason)

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def section(self):
        page = packet.render_packet_html(self.repo, "0001-runaway")
        return page.split('<section id="cost-decision">', 1)[1].split(
            "</section>", 1)[0]

    def unpriced(self, *item_ids):
        """Actionable siblings with no numeric priority — the F6
        population, arranged against the HTML render."""
        for item_id in item_ids:
            items.save_item(self.repo, {
                "id": item_id, "title": item_id, "stage": "plan",
                "kind": "backend", "created": "2026-08-02T00:00:00Z",
                "updated": "2026-08-02T00:00:00Z"}, "")

    def priced(self, item_id, priority):
        items.save_item(self.repo, {
            "id": item_id, "title": item_id, "stage": "plan",
            "kind": "backend", "priority": priority,
            "created": "2026-08-02T00:00:00Z",
            "updated": "2026-08-02T00:00:00Z"}, "")

    def corrupt(self, *item_ids):
        for item_id in item_ids:
            bad = paths.items_dir(self.repo) / item_id
            bad.mkdir(parents=True, exist_ok=True)
            (bad / "item.md").write_bytes(b"\xff\xfe not utf-8")

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

    RECENT_EVENTS = "<h2>Recent events</h2>"

    def without_recent_events(self, page):
        """The page minus its `Recent events` section — the HTML twin of
        `TestCostDecisionPacket.without_recent_events`. Same reason: an
        append-only verbatim dump of what was logged is excluded by name,
        because it records what was written, not what is aggregated now,
        and must not be rewritten to agree (J-002, review pass 2)."""
        head, marker, tail = page.partition(self.RECENT_EVENTS)
        if not marker:
            return page
        _dump, _end, rest = tail.partition("  </section>")
        # Drop the section's own opening tag with it: line-based counting
        # does not care, but leaving an orphaned `<section>` in `kept` would
        # invite a future reader to trust the remainder as well-formed markup.
        return head.rsplit("  <section>", 1)[0] + rest

    def cost_surface_lines(self, page):
        """Rework figures on *rendered cost surfaces* of the HTML page."""
        return [l for l in self.without_recent_events(page).splitlines()
                if REWORK_FIGURE_RE.search(l)]

    def test_html_a_mistyped_park_reason_does_not_put_a_second_number_on_the_page(self):
        """The HTML twin of the markdown divergent-reason guard (F4).
        `render_packet_html` builds its own `id="waiting-on-you"` callout,
        so the markdown assertion leaves this surface unguarded."""
        self.park("0002-mistyped",
                  "cost breaker: 7 rework edges (threshold 2)")
        page = packet.render_packet_html(self.repo, "0002-mistyped")
        numbers = set()
        for line in self.cost_surface_lines(page):
            for match in REWORK_FIGURE_RE.finditer(line):
                numbers.add(match.group(1) or match.group(2))
        self.assertEqual(numbers, {"2"}, numbers)
        ask = page.split('<section class="ask" id="waiting-on-you">', 1)[1] \
                  .split("</section>", 1)[0]
        self.assertIn("<p>cost breaker: 2 rework edges (threshold 2)</p>", ask)
        self.assertNotIn("7 rework edges", ask)
        # The other half of why `Recent events` may be excluded (J-002): it
        # preserves the reason *as logged*. The dump still carries the
        # operator's mistyped 7 while no rendered cost surface does, so the
        # exclusion's justification is tested, not merely asserted.
        dump = page.split(self.RECENT_EVENTS, 1)[1].split("</section>", 1)[0]
        self.assertIn("7 rework edges", dump)
        self.assertNotIn("7 rework edges", self.without_recent_events(page))

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

    def test_html_renders_the_placeholder_commands_as_code(self):
        """F8 on the HTML render: the decision section escaped its lines
        wholesale, so a backticked command arrived as literal backticks
        around an escaped `&lt;n&gt;`. `respond_action_lines`' renderer
        already had the split; the two disagreeing on a command string is
        the class of bug this item exists to stop."""
        self.unprioritise()
        section = self.section()
        self.assertIn("<code>factory priority 0001-runaway &lt;n&gt;</code>",
                      section)
        self.assertIn("<code>factory packet 0001-runaway</code>", section)
        self.assertNotIn("`", section)
        # Every `&lt;n&gt;` on the page is inside a code span: splitting
        # on the tags, the text between them is what a reader sees adrift
        # in a paragraph.
        outside = re.sub(r"<code>.*?</code>", "", section)
        self.assertNotIn("&lt;n&gt;", outside)

    def test_html_defer_consequence_renders_its_command_as_code(self):
        section = self.section()
        self.assertIn("<code>factory priority 0001-runaway &lt;n&gt;</code>",
                      section)
        self.assertNotIn("`", section)

    def test_html_recommendation_does_not_claim_an_empty_backlog(self):
        """F5/F6 against the HTML render. The sentence comes from the
        shared `cost_decision_lines`, but `_inline_code` now post-processes
        every decision line on this side (`packet.py:333`, `:340`), so the
        two renders are no longer string-identical and the markdown guard
        no longer covers this path."""
        self.unpriced("0002-none", "0003-none")
        self.corrupt("0009-corrupt")
        section = self.section()
        self.assertNotIn("nothing else is waiting at this priority", section)
        self.assertIn(
            "Recommended: narrow — nothing comparable is waiting at this "
            "priority; 2 actionable items with no priority and 1 unreadable "
            "item cannot be compared either way, so the backlog is not "
            "established as empty; a smaller next round costs less than "
            "another full one.", section)

    def test_html_continue_consequence_names_what_it_cannot_compare(self):
        self.unpriced("0002-none", "0003-none", "0004-none")
        self.assertIn("the 0 items at priority ≤ 2 keep waiting, alongside "
                      "3 actionable items with no priority that cannot be "
                      "compared;", self.section())

    def test_html_backlog_and_continue_lines_agree_in_number(self):
        """F7 against the HTML render."""
        self.priced("0002-p1", 1)
        section = self.section()
        self.assertIn("backlog: 1 actionable item at priority ≤ 2, "
                      "1 actionable in total", section)
        self.assertNotIn("1 actionable items", section)
        self.assertIn("the 1 item at priority ≤ 2 keeps waiting", section)
        self.assertNotIn("1 items at priority", section)

    def test_html_exactly_one_rework_figure_in_the_cost_decision_section(self):
        """B2 against the HTML render: packet.py builds its own section,
        so the markdown-scoped count leaves this surface unguarded."""
        lines = [l for l in self.section().splitlines()
                 if REWORK_FIGURE_RE.search(l)]
        self.assertEqual(len(lines), 1, lines)

    def test_html_rework_figures_outside_the_section_are_the_two_known_surfaces(self):
        """The HTML analogue of the markdown three-surface accounting.
        `render_packet_html` builds its own markup — the waiting-on-you
        callout, the decision list and the Spend receipt are three
        separate constructions — so a fourth rework surface added to the
        HTML render *only*, carrying the same number, would satisfy both
        the section-scoped count and the numbers-agree assertion and slip
        through. Each of the three is pinned by identity here, so a
        fourth anywhere in the document fails.

        The count is taken over rendered cost surfaces: the
        `Recent events` dump is excluded by name and by reason (see
        `without_recent_events`), not because it is inconvenient."""
        page = packet.render_packet_html(self.repo, "0001-runaway")
        every = self.cost_surface_lines(page)
        self.assertEqual(len(every), 3, every)
        section = self.section().splitlines()
        inside = [l for l in every if l in section]
        self.assertEqual(len(inside), 1, inside)
        outside = [l for l in every if l not in section]
        ask = page.split('<section class="ask" id="waiting-on-you">', 1)[1] \
                  .split("</section>", 1)[0].splitlines()
        echo = [l for l in outside if l in ask]
        self.assertEqual(len(echo), 1, echo)
        self.assertIn("<p>cost breaker: 2 rework edges", echo[0])
        spend = page.split("<h2>Spend</h2>", 1)[1].split(
            "</section>", 1)[0].splitlines()
        receipt = [l for l in outside if l in spend]
        self.assertEqual(len(receipt), 1, receipt)
        self.assertIn("<li>[proxy] active ", receipt[0])
        self.assertEqual(len(echo) + len(receipt), len(outside), outside)

    def test_html_every_rework_number_in_the_page_agrees(self):
        """Scoped to rendered cost surfaces, with
        `test_html_a_mistyped_park_reason_…` as the proof it can fail."""
        page = packet.render_packet_html(self.repo, "0001-runaway")
        numbers = set()
        for line in self.cost_surface_lines(page):
            for match in REWORK_FIGURE_RE.finditer(line):
                numbers.add(match.group(1) or match.group(2))
        self.assertEqual(numbers, {"2"}, numbers)

    def test_html_only_recent_events_is_excluded_from_the_rework_count(self):
        """The HTML twin of the exclusion pin: exactly one section is
        excluded, the raw page really does carry the extra figure there,
        and every other section survives the cut."""
        page = packet.render_packet_html(self.repo, "0001-runaway")
        every = [l for l in page.splitlines() if REWORK_FIGURE_RE.search(l)]
        surfaces = self.cost_surface_lines(page)
        excluded = [l for l in every if l not in surfaces]
        self.assertEqual(len(excluded), 1, excluded)
        dump = page.split(self.RECENT_EVENTS, 1)[1].split(
            "  </section>", 1)[0].splitlines()
        self.assertIn(excluded[0], dump)
        self.assertIn("stage.advance", excluded[0])
        kept = self.without_recent_events(page)
        self.assertNotIn(self.RECENT_EVENTS, kept)
        for marker in ('<section id="cost-decision">', "<h2>Spend</h2>",
                       '<section id="respond">', '<section id="artifacts">',
                       '<section class="ask" id="waiting-on-you">'):
            self.assertIn(marker, kept, marker)

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
