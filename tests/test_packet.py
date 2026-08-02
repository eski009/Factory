import os
import re
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
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-08-02T06:00:00Z"
        meta = {"id": "0001-runaway", "title": "Runaway",
                "stage": "waiting-human", "kind": "backend", "priority": 2,
                "paused-from": "implement",
                "paused-reason": "cost breaker: 2 rework edges (threshold 2)",
                "created": "2026-08-02T00:00:00Z",
                "updated": "2026-08-02T06:00:00Z"}
        items.save_item(self.repo, meta, "# Runaway\n")
        for ts in ("2026-08-02T01:00:00Z", "2026-08-02T02:00:00Z"):
            os.environ["FACTORY_NOW"] = ts
            logs.append_event(self.repo, "0001-runaway", "stage.advance",
                              {"from": "review", "to": "implement"})
        os.environ["FACTORY_NOW"] = "2026-08-02T06:00:00Z"

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

    def test_exactly_one_rework_line_and_one_rework_number(self):
        text = packet.render_packet(self.repo, "0001-runaway")
        decision_lines = [line for line in text.splitlines()
                          if re.search(r"rework edges: \d", line)]
        self.assertEqual(len(decision_lines), 1, decision_lines)
        numbers = set()
        for line in text.splitlines():
            for match in re.finditer(
                    r"rework edges: (\d+)|(\d+) rework edges", line):
                numbers.add(match.group(1) or match.group(2))
        self.assertEqual(numbers, {"2"}, numbers)

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


if __name__ == "__main__":
    unittest.main()
