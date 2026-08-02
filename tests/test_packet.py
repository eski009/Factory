import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.factory.lib import (cost, initrepo, items, logs, machine, packet,
                                 paths)

# AC11 / J-002's `one rework figure` oracle. The packet renders the figure in
# two surface forms — `rework edges: N` at the decision and `N rework edges` in
# the ## Spend receipt — so a pattern that matches only the first cannot fail
# and guards nothing. Both alternatives are pinned by
# test_rework_figure_pattern_matches_both_surface_forms before this is used to
# filter anything.
REWORK_FIGURE_RE = re.compile(r"rework edges: (\d+)|(\d+) rework edges")


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
        html_path = self.repo / "docs/factory/packets/0001-thing.html"
        self.assertTrue(html_path.exists())
        first_html = html_path.read_bytes()
        packet.write_packet(self.repo, "0001-thing")
        self.assertEqual(path.read_text(), first)
        self.assertEqual(html_path.read_bytes(), first_html)

    def test_respond_uses_real_item_id(self):
        text = packet.render_packet(self.repo, "0001-thing")
        self.assertIn("factory choice 0001-thing <option>", text)
        self.assertNotIn("factory choice <id>", text)

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

    def test_packet_lists_assurance_artifacts(self):
        text = packet.render_packet(self.repo, "0001-thing")
        self.assertIn("assurance/verdicts.json", text)
        self.assertIn("assurance/impact.json", text)

    def test_packet_renders_with_corrupt_log_line(self):
        log = self.repo / ".factory/items/0001-thing/log.jsonl"
        with log.open("a", encoding="utf-8") as f:
            f.write('{"event": "spend", "ts": \n')
        text = packet.render_packet(self.repo, "0001-thing")
        self.assertIn("## Spend", text)
        self.assertIn(", corrupt log lines skipped: 1", text)
        section = text.split("## Spend\n")[1].split("\n\n## Respond")[0]
        self.assertEqual(len(section.splitlines()), 3)


class TestCostDecisionPacket(unittest.TestCase):
    """AC10/AC11: the packet a crossing item parks with states its own
    cost, the backlog it is blocking, and the three named options, each
    with one consequence line and one provenance tag."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        self.park("0001-runaway",
                  "cost breaker: 2 rework edges (threshold 2)")

    def park(self, item_id, reason, priority=2):
        """Park the fixture the way production parks — through
        `machine.advance(..., "waiting-human", reason=...)`.

        The engine writes `paused-from`/`paused-reason` itself *and*
        appends a `stage.advance` event carrying `reason`
        (`machine.py:307-308`), which is exactly the event
        `## Recent events` dumps verbatim. A fixture that writes the
        frontmatter straight through `items.save_item` never produces
        that event, so the whole-packet rework guards were counting a
        packet production never renders (review pass 2, F3). The clock
        is pinned across the call so the park stays deterministic.
        """
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

    def other(self, item_id, stage="plan", priority=1):
        items.save_item(self.repo, {
            "id": item_id, "title": item_id, "stage": stage,
            "kind": "backend", "priority": priority,
            "created": "2026-08-02T00:00:00Z",
            "updated": "2026-08-02T00:00:00Z"}, "")

    def section(self, text):
        return text.split("## Cost decision\n", 1)[1].split("\n## ", 1)[0]

    def section_named(self, text, name):
        return text.split(f"## {name}\n", 1)[1].split("\n## ", 1)[0]

    def unprioritise(self):
        meta, body = items.load_item(self.repo, "0001-runaway")
        meta.pop("priority", None)
        items.save_item(self.repo, meta, body)
        self.other("0002-p1", priority=1)
        self.other("0003-p9", priority=9)

    def corrupt(self, *item_ids):
        """Sibling item.md files list_items_safe cannot decode. The
        backlog line must name what it dropped rather than passing the
        survivors off as the whole population (N4)."""
        for item_id in item_ids:
            bad = paths.items_dir(self.repo) / item_id
            bad.mkdir(parents=True, exist_ok=True)
            (bad / "item.md").write_bytes(b"\xff\xfe not utf-8")

    def test_backlog_line_names_the_one_item_it_could_not_read(self):
        self.other("0002-p1", priority=1)
        self.corrupt("0009-corrupt")
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        backlog = [l for l in section.splitlines()
                   if l.startswith("- backlog:")]
        self.assertEqual(len(backlog), 1, backlog)
        self.assertEqual(
            backlog[0],
            "- backlog: 1 actionable items at priority ≤ 2, 1 actionable in "
            "total; 1 item unreadable and excluded")

    def test_backlog_line_pluralises_the_items_it_could_not_read(self):
        self.other("0002-p1", priority=1)
        self.corrupt("0008-corrupt", "0009-corrupt")
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        self.assertIn("1 actionable in total; 2 items unreadable and excluded",
                      section)

    def test_backlog_line_names_dropped_items_when_priority_unset(self):
        self.unprioritise()
        self.corrupt("0009-corrupt")
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        self.assertIn("- backlog: comparison unavailable — this item has no "
                      "priority; 2 actionable in total; 1 item unreadable and "
                      "excluded", section)

    def test_backlog_line_carries_no_qualifier_when_every_item_reads(self):
        self.other("0002-p1", priority=1)
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        self.assertNotIn("unreadable and excluded", section)

    def test_backlog_line_does_not_claim_a_number_when_priority_unset(self):
        self.unprioritise()
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        self.assertNotIn("≤ -", section)
        self.assertNotIn("0 actionable items", section)
        self.assertIn("2 actionable in total", section)

    def test_no_recommendation_asserts_an_empty_backlog_when_priority_unset(self):
        self.unprioritise()
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        self.assertNotIn("nothing else is waiting at this priority", section)
        recommended = [l for l in section.splitlines()
                       if l.startswith("Recommended:")]
        self.assertEqual(len(recommended), 1, recommended)
        self.assertIn("factory priority", recommended[0])
        self.assertNotIn("defer —", recommended[0])
        self.assertNotIn("narrow —", recommended[0])
        self.assertNotIn("continue", recommended[0])

    def test_recommendation_points_at_the_re_render_not_a_stale_file(self):
        """The packet is a static file (`write_packet`): setting a
        priority does not rewrite it, so the action named must be the
        re-render, never "re-read this packet"."""
        self.unprioritise()
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        recommended = [l for l in section.splitlines()
                       if l.startswith("Recommended:")]
        self.assertEqual(
            recommended[0],
            "Recommended: set a priority first — what this item is blocking "
            "cannot be compared until it has one; run factory priority "
            "0001-runaway <n>, then factory packet 0001-runaway to re-render "
            "this decision.")
        self.assertNotIn("re-read this packet", section)

    def test_continue_consequence_carries_no_priority_sentinel(self):
        self.unprioritise()
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        cont = [l for l in section.splitlines() if l.startswith("- continue —")]
        self.assertEqual(len(cont), 1, cont)
        self.assertNotIn("≤ -", cont[0])
        self.assertNotIn("keep waiting", cont[0])

    def test_all_three_options_still_carry_one_consequence_when_unset(self):
        self.unprioritise()
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        for option in ("- continue —", "- narrow —", "- defer —"):
            self.assertEqual(
                len([l for l in section.splitlines() if l.startswith(option)]),
                1, option)

    def test_section_absent_for_a_non_breaker_pause(self):
        meta, body = items.load_item(self.repo, "0001-runaway")
        meta["paused-from"] = "design"
        meta["paused-reason"] = "pick an option"
        items.save_item(self.repo, meta, body)
        self.assertNotIn("## Cost decision",
                         packet.render_packet(self.repo, "0001-runaway"))

    def test_proxy_substrate_leads_the_section(self):
        text = packet.render_packet(self.repo, "0001-runaway")
        first = self.section(text).strip().splitlines()[0]
        self.assertEqual(
            first,
            "- [proxy] rework edges: 2 (backward stage.advance edges into "
            "implement; threshold 2)")

    def test_no_measured_figure_above_the_proxy_substrate(self):
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        self.assertLess(section.index("[proxy] rework edges:"),
                        section.index("[unmeasured] tokens:"))

    def rework_lines(self, text):
        return [line for line in text.splitlines()
                if REWORK_FIGURE_RE.search(line)]

    RECENT_EVENTS = "Recent events"

    def without_recent_events(self, text):
        """The packet minus its `## Recent events` section.

        `## Recent events` is an append-only verbatim dump of the log: it
        records what was *written*, not what is aggregated now, and
        forcing an audit record to agree with a live aggregation would be
        architecturally wrong. So it is excluded from the rework
        accounting **by name, with that reason** (J-002, review pass 2) —
        never by accident, and never by a filter that would also swallow
        a real rendered surface. Everything else on the packet is a
        rendered cost surface and is counted."""
        head, marker, tail = text.partition(f"## {self.RECENT_EVENTS}\n")
        if not marker:
            return text
        _dump, nxt, rest = tail.partition("\n## ")
        return head + (nxt + rest if nxt else "")

    def cost_surface_lines(self, text):
        """Rework figures on *rendered cost surfaces* — every digit-bearing
        rework line except those in the excluded audit dump. See
        `without_recent_events` for what is excluded and why."""
        return self.rework_lines(self.without_recent_events(text))

    def test_a_mistyped_park_reason_does_not_put_a_second_number_on_the_packet(self):
        """F4: skills/factory-dispatch/SKILL.md:50 has an agent hand-copy
        `<n>` into the park reason. A typo there must not reach the
        operator as a rework figure — the decision block, the
        waiting-on-you line and the `## Spend` receipt all derive from
        `summary["rework_edges"]`, so the packet shows one number and it
        is the engine's."""
        self.park("0002-mistyped",
                  "cost breaker: 7 rework edges (threshold 2)")
        text = packet.render_packet(self.repo, "0002-mistyped")
        numbers = set()
        for line in self.cost_surface_lines(text):
            for match in REWORK_FIGURE_RE.finditer(line):
                numbers.add(match.group(1) or match.group(2))
        self.assertEqual(numbers, {"2"}, numbers)
        waiting = [l for l in text.splitlines()
                   if l.startswith("- waiting on you:")]
        self.assertEqual(
            waiting,
            ["- waiting on you: cost breaker: 2 rework edges (threshold 2)"])
        # The other half of why `## Recent events` may be excluded (J-002):
        # it preserves the reason *as logged*. Both halves are pinned here —
        # the audit dump still carries the operator's mistyped 7, and no
        # rendered cost surface does — so the exclusion's justification is a
        # tested property rather than a claim in the contract.
        self.assertIn("7 rework edges",
                      self.section_named(text, self.RECENT_EVENTS))
        self.assertNotIn("7 rework edges", self.without_recent_events(text))

    def test_a_cost_breaker_reason_carrying_extra_text_renders_derived(self):
        """The derivation reconstructs the whole sentence from
        `breaker.PAUSE_PREFIX` (`packet.py:50-53`), so context an agent
        appends beyond the canonical string
        (`skills/factory-dispatch/SKILL.md:50`) is *deliberately* dropped
        from the line that leads the page: that line carries the engine's
        figure and nothing hand-copied. The context is not lost — the
        `## Recent events` dump preserves the reason as logged."""
        self.park("0003-verbose",
                  "cost breaker: 9 rework edges (threshold 2) "
                  "— third rework round, see reviews/synthesis.md")
        text = packet.render_packet(self.repo, "0003-verbose")
        waiting = [l for l in text.splitlines()
                   if l.startswith("- waiting on you:")]
        self.assertEqual(
            waiting,
            ["- waiting on you: cost breaker: 2 rework edges (threshold 2)"])
        self.assertNotIn("third rework round",
                         self.without_recent_events(text))
        self.assertIn("third rework round",
                      self.section_named(text, self.RECENT_EVENTS))

    def test_a_non_breaker_pause_reason_is_echoed_byte_for_byte(self):
        """The complement of the derivation, and the bound on it: the
        rewrite is scoped to the cost-breaker prefix, not to content that
        looks like a rework figure. A design pause's free text — hosted URL
        and all — reaches the operator exactly as it was written."""
        reason = ("design options ready: pick one — "
                  "https://example.com/opt (2 rework edges of context)")
        self.park("0004-design", reason)
        text = packet.render_packet(self.repo, "0004-design")
        waiting = [l for l in text.splitlines()
                   if l.startswith("- waiting on you:")]
        self.assertEqual(waiting, [f"- waiting on you: {reason}"])
        self.assertNotIn("## Cost decision", text)

    def test_rework_figure_pattern_matches_both_surface_forms(self):
        """A self-check on the filter itself, before it is used to count
        anything. The old guard matched only `rework edges: N`, so its
        count was unfalsifiable; without this test a future edit can
        narrow it back to unfalsifiable in silence."""
        self.assertTrue(REWORK_FIGURE_RE.search(
            "- [proxy] rework edges: 2 (backward stage.advance edges into "
            "implement; threshold 2)"))
        self.assertTrue(REWORK_FIGURE_RE.search(
            "- [proxy] active 05h 00m (waiting 00h 00m), 2 advances, "
            "0 dispatches, 2 rework edges"))

    def test_exactly_one_rework_figure_inside_the_cost_decision_section(self):
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        lines = self.rework_lines(section)
        self.assertEqual(len(lines), 1, lines)

    def test_every_rework_number_in_the_packet_agrees(self):
        """Scoped to rendered cost surfaces (`cost_surface_lines`), and
        `test_a_mistyped_park_reason_…` is what makes this fire: without
        it this assertion runs against a fixture whose park reason
        already contains the right number and cannot fail."""
        text = packet.render_packet(self.repo, "0001-runaway")
        numbers = set()
        for line in self.cost_surface_lines(text):
            for match in REWORK_FIGURE_RE.finditer(line):
                numbers.add(match.group(1) or match.group(2))
        self.assertEqual(numbers, {"2"}, numbers)

    def test_only_recent_events_is_excluded_from_the_rework_count(self):
        """The exclusion is exactly one section, and it is real.

        If a future edit widens it, a rendered cost surface stops being
        counted and the two counts stop differing by exactly the audit
        dump — this fails. If the raw packet stops carrying the extra
        figure there, the exclusion is vacuous and the identity
        assertions below fail. Either way the scope cannot drift in
        silence."""
        text = packet.render_packet(self.repo, "0001-runaway")
        every = self.rework_lines(text)
        surfaces = self.cost_surface_lines(text)
        excluded = [l for l in every if l not in surfaces]
        self.assertEqual(len(excluded), 1, excluded)
        dump = self.section_named(text, self.RECENT_EVENTS).splitlines()
        self.assertIn(excluded[0], dump)
        self.assertIn("stage.advance", excluded[0])
        kept = self.without_recent_events(text)
        self.assertNotIn(f"## {self.RECENT_EVENTS}", kept)
        for heading in ("## Cost decision", "## View the options",
                        "## Artifacts", "## Spend", "## Respond"):
            self.assertIn(heading, kept, heading)

    def test_rework_figures_outside_the_decision_section_are_the_two_known_surfaces(self):
        """The two repetitions outside `## Cost decision` are deliberate
        and derived from the same `summary["rework_edges"]`: the
        `- waiting on you:` derived echo and the `## Spend` receipt's
        proxy line, which is the operator's cross-check. They are named
        and counted here so a *fourth* rendered cost surface — a
        differently-derived second figure, the defect J-002 exists to
        remove — fails this test rather than passing unnoticed.

        The count is taken over rendered cost surfaces:
        `## Recent events` is excluded by name and by reason (see
        `without_recent_events`), not because it is inconvenient."""
        text = packet.render_packet(self.repo, "0001-runaway")
        section = self.section(text)
        every = self.cost_surface_lines(text)
        self.assertEqual(len(every), 3, every)
        outside = [l for l in every if l not in section.splitlines()]
        self.assertEqual(len(outside), 2, outside)
        receipt = self.section_named(text, "Spend")
        receipt_lines = [l for l in outside if l in receipt.splitlines()]
        self.assertEqual(len(receipt_lines), 1, receipt_lines)
        self.assertTrue(receipt_lines[0].startswith("- [proxy] active "),
                        receipt_lines[0])
        echo = [l for l in outside if l not in receipt_lines]
        self.assertEqual(len(echo), 1, echo)
        self.assertTrue(
            echo[0].startswith("- waiting on you: cost breaker:"), echo[0])

    def test_measured_figure_is_labelled_or_loudly_unmeasured(self):
        text = packet.render_packet(self.repo, "0001-runaway")
        self.assertIn("- [unmeasured] tokens: UNMEASURED "
                      "(no spend events logged)", self.section(text))
        os.environ["FACTORY_NOW"] = "2026-08-02T05:00:00Z"
        logs.append_event(self.repo, "0001-runaway", "spend",
                          {"provenance": "measured", "stage": "implement",
                           "dispatches": 2, "tokens": {"total": 4914081}})
        os.environ["FACTORY_NOW"] = "2026-08-02T06:00:00Z"
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        self.assertIn("- [measured] tokens: total 4914081 (1 spend events) "
                      "— LOWER BOUND", section)

    def test_backlog_line_names_both_counts(self):
        self.other("0002-p1", priority=1)
        self.other("0003-p9", priority=9)
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        self.assertIn("- backlog: 1 actionable items at priority ≤ 2, "
                      "2 actionable in total", section)

    def test_recommendation_is_defer_when_backlog_at_or_above(self):
        self.other("0002-p1", priority=1)
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        recommended = [line for line in section.splitlines()
                       if line.startswith("Recommended:")]
        self.assertEqual(len(recommended), 1)
        self.assertTrue(recommended[0].startswith("Recommended: defer — "))
        self.assertEqual(recommended[0].count("."), 1)

    def test_recommendation_is_narrow_when_nothing_waits(self):
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        recommended = [line for line in section.splitlines()
                       if line.startswith("Recommended:")]
        self.assertTrue(recommended[0].startswith("Recommended: narrow — "))

    def test_recommendation_is_never_continue(self):
        for extra in ((), ("0002-p1",)):
            for item_id in extra:
                self.other(item_id, priority=1)
            section = self.section(
                packet.render_packet(self.repo, "0001-runaway"))
            self.assertNotIn("Recommended: continue", section)

    def test_each_option_carries_exactly_one_consequence_line(self):
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        for option in ("continue", "narrow", "defer"):
            lines = [line for line in section.splitlines()
                     if line.startswith(f"- {option} — ")]
            self.assertEqual(len(lines), 1, option)

    def test_continue_consequence_names_the_next_count_and_the_backlog(self):
        self.other("0002-p1", priority=1)
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        self.assertIn("the next rework edge parks it again at 3", section)
        self.assertIn("the 1 items at priority ≤ 2 keep waiting", section)

    def test_no_line_promises_backlog_release_unconditionally(self):
        """M9: release is loop-mode behaviour."""
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        self.assertIn("in loop mode the next actionable item runs while this "
                      "one waits; in item/step mode the run stops here",
                      section)

    def test_narrow_and_defer_state_what_v1_does_not_do(self):
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        self.assertIn("v1 does not narrow scope for you.", section)
        self.assertIn("v1 does not re-prioritise for you.", section)

    def test_respond_names_the_real_verb_and_only_it(self):
        text = packet.render_packet(self.repo, "0001-runaway")
        respond = text.split("## Respond\n", 1)[1]
        actions = [line for line in respond.splitlines()
                   if line.startswith("- `")]
        self.assertEqual(len(actions), 1, actions)
        self.assertIn("factory cost-answer 0001-runaway "
                      "<continue|narrow|defer>", actions[0])
        self.assertNotIn("/factory:run", respond)
        self.assertNotIn("factory choice", respond)
        self.assertNotIn("factory confirm", respond)

    def test_every_cost_bearing_line_carries_one_provenance_tag(self):
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        tags = ("[proxy]", "[measured]", "[unmeasured]")
        for line in section.splitlines():
            if "[" not in line:
                continue
            self.assertEqual(sum(line.count(tag) for tag in tags), 1, line)


class TestRespondBranches(unittest.TestCase):
    """AC12/AC26: one branch per pause, always exactly one action."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-08-02T06:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def parked(self, paused_from, reason, kind="ui"):
        items.save_item(self.repo, {
            "id": "0001-thing", "title": "Thing", "stage": "waiting-human",
            "kind": kind, "priority": 1, "paused-from": paused_from,
            "paused-reason": reason, "created": "2026-08-02T00:00:00Z",
            "updated": "2026-08-02T06:00:00Z"}, "# Thing\n")

    def actions(self):
        respond = packet.render_packet(
            self.repo, "0001-thing").split("## Respond\n", 1)[1]
        return [line for line in respond.splitlines()
                if line.startswith("- `")]

    def test_design_pause_names_factory_choice(self):
        self.parked("design", "pick an option")
        actions = self.actions()
        self.assertEqual(len(actions), 1)
        self.assertIn("factory choice 0001-thing <option>", actions[0])

    def test_assure_pause_names_confirm_and_waive_on_one_line(self):
        self.parked("assure", "confirm the walk")
        actions = self.actions()
        self.assertEqual(len(actions), 1)
        self.assertIn("factory confirm 0001-thing", actions[0])
        self.assertIn("factory waive 0001-thing", actions[0])

    def test_generic_pause_still_names_exactly_one_action(self):
        self.parked("plan", "the plan skill is unavailable")
        actions = self.actions()
        self.assertEqual(len(actions), 1)
        self.assertIn("/factory:run", actions[0])


class TestOneAggregationPerPacket(unittest.TestCase):
    """Carried review finding A: every figure on one packet must come from
    one `cost.summarize` call.

    The window is open while an item is parked, so `active_seconds`
    re-reads the wall clock on every call. Rendering the `## Cost
    decision` block and the `## Spend` receipt from two separate
    aggregations therefore prints the same proxy quantity twice, a dozen
    lines apart, with two different values whenever the calls straddle a
    minute boundary. Pinning FACTORY_NOW hides the bug, so these tests
    drive a ticking clock instead.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-08-02T00:00:00Z"
        items.save_item(self.repo, {
            "id": "0001-runaway", "title": "Runaway",
            "stage": "implement", "kind": "backend", "priority": 2,
            "created": "2026-08-02T00:00:00Z",
            "updated": "2026-08-02T00:00:00Z"}, "# Runaway\n")
        for ts in ("2026-08-02T01:00:00Z", "2026-08-02T02:00:00Z"):
            os.environ["FACTORY_NOW"] = ts
            logs.append_event(self.repo, "0001-runaway", "stage.advance",
                              {"from": "review", "to": "implement"})
        os.environ["FACTORY_NOW"] = "2026-08-02T06:00:00Z"
        # Park through the engine, not through frontmatter: `machine.advance`
        # writes `paused-from`/`paused-reason` itself and appends the
        # `stage.advance` event `## Recent events` dumps verbatim
        # (`machine.py:307-308`). A fixture that hand-writes the parked
        # frontmatter renders a packet production never produces — the shape
        # review pass 2 rejected (F3) — so this file no longer contains one.
        machine.advance(self.repo, "0001-runaway", "waiting-human",
                        reason="cost breaker: 2 rework edges (threshold 2)")

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def ticking_clock(self):
        """An unpinned clock that advances one hour per reading, so any
        two aggregations of the same open window disagree visibly."""
        readings = []

        def now_stamp():
            stamp = f"2026-08-02T{6 + len(readings):02d}:00:00Z"
            readings.append(stamp)
            return stamp

        return readings, now_stamp

    def actives(self, text):
        return [value.strip()
                for value in re.findall(r"\[proxy\] active ([^,(]+)", text)]

    def test_the_two_active_figures_on_one_packet_agree(self):
        os.environ.pop("FACTORY_NOW", None)
        readings, clock = self.ticking_clock()
        with mock.patch.object(logs, "now_stamp", clock):
            text = packet.render_packet(self.repo, "0001-runaway")
        actives = self.actives(text)
        self.assertEqual(len(actives), 2, text)
        self.assertEqual(actives[0], actives[1], readings)

    def test_markdown_render_aggregates_the_log_once(self):
        os.environ.pop("FACTORY_NOW", None)
        readings, clock = self.ticking_clock()
        with mock.patch.object(logs, "now_stamp", clock):
            packet.render_packet(self.repo, "0001-runaway")
        self.assertEqual(len(readings), 1, readings)

    def test_html_render_aggregates_the_log_once(self):
        os.environ.pop("FACTORY_NOW", None)
        readings, clock = self.ticking_clock()
        with mock.patch.object(logs, "now_stamp", clock):
            html_text = packet.render_packet_html(self.repo, "0001-runaway")
        self.assertEqual(len(readings), 1, readings)
        actives = self.actives(html_text)
        self.assertEqual(len(actives), 2, html_text)
        self.assertEqual(actives[0], actives[1])

    def test_one_write_gives_both_documents_the_same_figures(self):
        os.environ.pop("FACTORY_NOW", None)
        readings, clock = self.ticking_clock()
        with mock.patch.object(logs, "now_stamp", clock):
            path = packet.write_packet(self.repo, "0001-runaway")
        self.assertEqual(len(readings), 1, readings)
        both = (path.read_text(encoding="utf-8")
                + packet.packet_html_path(
                    self.repo, "0001-runaway").read_text(encoding="utf-8"))
        actives = self.actives(both)
        self.assertEqual(len(actives), 4, actives)
        self.assertEqual(len(set(actives)), 1, actives)


class TestJ001PermittedDiffSet(unittest.TestCase):
    """Carried review finding B: the shipped renderers change the
    `## Respond` block on every packet (item 0016 spec §6, B3), which is a
    third permitted J-001 diff the spec's own narrowing paragraph does not
    name. J-001's contract must name every diff the code actually makes,
    or its byte-comparison oracle reports a false regression the first
    time anyone runs it.
    """

    ORACLE = ("docs/factory/journeys/contracts/"
              "J-001-assure-outcome-readout.md")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-08-02T06:00:00Z"
        items.save_item(self.repo, {
            "id": "0001-thing", "title": "Thing", "stage": "waiting-human",
            "kind": "backend", "priority": 1, "paused-from": "assure",
            "paused-reason": "confirm the assure walk",
            "created": "2026-08-02T00:00:00Z",
            "updated": "2026-08-02T06:00:00Z"}, "# Thing\n")

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def oracle_line(self):
        text = (Path(__file__).resolve().parents[1] / self.ORACLE).read_text(
            encoding="utf-8")
        lines = [l for l in text.splitlines() if l.startswith("| default path")]
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def test_the_respond_block_really_did_change_on_a_j001_packet(self):
        """The pre-change Respond block listed every verb and closed with
        'then run `/factory:run` to resume.'; the shipped one names the
        single verb that answers this pause. A two-diff permitted list
        would flag this as a regression."""
        text = packet.render_packet(self.repo, "0001-thing")
        respond = text.split("## Respond\n", 1)[1]
        self.assertNotIn("then run `/factory:run` to resume.", respond)
        self.assertIn("factory confirm 0001-thing", respond)

    def test_the_oracle_names_the_respond_diff_too(self):
        line = self.oracle_line()
        self.assertIn("narrowed by item 0016", line)
        self.assertIn("`## Respond`", line)


class TestJ001Regression(unittest.TestCase):
    """AC26: this item touches J-001's packet and status surfaces. The
    permitted diffs are the two renames and the `## Respond` block that
    spec §6/B3 mandates on every packet; every other J-001 signal is left
    exactly as this item found it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-08-02T06:00:00Z"
        items.save_item(self.repo, {
            "id": "0001-thing", "title": "Thing", "stage": "waiting-human",
            "kind": "backend", "priority": 1, "paused-from": "assure",
            "paused-reason": "confirm the assure walk",
            "created": "2026-08-02T00:00:00Z",
            "updated": "2026-08-02T06:00:00Z"}, "# Thing\n")

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_respond_still_renders_exactly_one_action(self):
        respond = packet.render_packet(
            self.repo, "0001-thing").split("## Respond\n", 1)[1]
        actions = [line for line in respond.splitlines()
                   if line.startswith("- `")]
        self.assertEqual(len(actions), 1, actions)

    def test_spend_receipt_diff_is_only_the_rework_edges_label(self):
        text = packet.render_packet(self.repo, "0001-thing")
        section = text.split("## Spend\n", 1)[1].split("\n\n## Respond", 1)[0]
        lines = section.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].endswith("0 rework edges"), lines[0])
        self.assertNotIn("retries", text)

    def test_this_item_introduces_no_known_fails_line(self):
        """0013 owns the first-screen known-fails line; 0016 must leave
        that surface exactly as it found it."""
        text = packet.render_packet(self.repo, "0001-thing")
        self.assertNotIn("shipped with known fails", text)

    def test_status_json_spend_key_renamed_and_assurance_untouched(self):
        summary = cost.summarize(self.repo, "0001-thing")
        self.assertIn("rework_edges", summary)
        self.assertNotIn("retries", summary)
        meta, _body = items.load_item(self.repo, "0001-thing")
        self.assertNotIn("assurance", meta)

    def test_no_cost_decision_block_on_a_j001_packet(self):
        """The `## Cost decision` block is a new state, not a diff: it
        appears only on a cost-breaker pause, never on J-001's path."""
        for render in (packet.render_packet, packet.render_packet_html):
            text = render(self.repo, "0001-thing")
            self.assertNotIn("Cost decision", text)


if __name__ == "__main__":
    unittest.main()
