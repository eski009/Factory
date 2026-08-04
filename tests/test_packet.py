import inspect
import io
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.factory import factory
from scripts.factory.lib import (cost, initrepo, items, logs, machine, packet,
                                 paths)

# AC11 / J-002's `one rework figure` oracle. The packet renders the figure in
# two surface forms — `rework edges: N` at the decision and `N rework edges` in
# the ## Spend receipt — so a pattern that matches only the first cannot fail
# and guards nothing. Both alternatives are pinned by
# test_rework_figure_pattern_matches_both_surface_forms before this is used to
# filter anything.
REWORK_FIGURE_RE = re.compile(r"rework edges: (\d+)|(\d+) rework edges")

# Item 0027. Every pre-existing cost-breaker fixture in this repo parks
# from a hardcoded `implement` stage, so ~25 assertions about the
# `## Respond` block hold for a renderer that answers a plan-origin cost
# pause with `/factory:run` — or, worse, an assure-origin one with
# `factory waive`. These four names are the parameterisation that makes
# the origin visible; one definition, imported by test_packet_html.py,
# on the REWORK_FIGURE_RE precedent above.
PARKED_FROM = ("implement", "plan", "review", "verify", "assure", "design")
PARK_REASONS = {
    "cost": "cost breaker: 2 rework edges (threshold 2)",
    "approach": "approach cap: 1 redesign(s) used (cap 1)",
    "none": "the implement skill is unavailable",
}
DECISION_VERB = {"cost": "factory cost-answer",
                 "approach": "factory approach-answer"}


def park_matrix_fixture(repo, item_id, paused_from, reason, priority=2):
    """Park `item_id` at `paused_from` the way production parks — through
    `machine.advance(..., "waiting-human", reason=...)`, which writes
    `paused-from`/`paused-reason` itself and appends the `stage.advance`
    event `## Recent events` dumps (`machine.py:307-308`). Two backward
    edges into implement are logged first so the cost figures are the
    engine's, not the fixture's."""
    os.environ["FACTORY_NOW"] = "2026-08-02T00:00:00Z"
    items.save_item(repo, {
        "id": item_id, "title": "Runaway", "stage": paused_from,
        "kind": "backend", "priority": priority,
        "created": "2026-08-02T00:00:00Z",
        "updated": "2026-08-02T00:00:00Z"}, "# Runaway\n")
    for ts in ("2026-08-02T01:00:00Z", "2026-08-02T02:00:00Z"):
        os.environ["FACTORY_NOW"] = ts
        logs.append_event(repo, item_id, "stage.advance",
                          {"from": "review", "to": "implement"})
    os.environ["FACTORY_NOW"] = "2026-08-02T06:00:00Z"
    machine.advance(repo, item_id, "waiting-human", reason=reason)


def respond_bullets(markdown):
    """The bullet lines under `## Respond` that lead with a command."""
    respond = markdown.split("## Respond\n", 1)[1]
    return [line for line in respond.splitlines() if line.startswith("- `")]


def leading_command(bullet):
    """The first backtick code span in a `## Respond` bullet — the one
    command the operator is meant to copy."""
    return bullet.split("`")[1]


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

    def unpriced(self, *item_ids):
        """Actionable siblings carrying no numeric priority — the
        population that falls out of `at_or_above` because it cannot be
        compared, not because it is not waiting (F6)."""
        for item_id in item_ids:
            items.save_item(self.repo, {
                "id": item_id, "title": item_id, "stage": "plan",
                "kind": "backend", "created": "2026-08-02T00:00:00Z",
                "updated": "2026-08-02T00:00:00Z"}, "")

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
            "- backlog: 1 actionable item at priority ≤ 2, 1 actionable in "
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

    def recommended(self):
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        lines = [l for l in section.splitlines()
                 if l.startswith("Recommended:")]
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def continue_line(self):
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        lines = [l for l in section.splitlines()
                 if l.startswith("- continue — ")]
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def test_recommendation_does_not_claim_an_empty_backlog_when_siblings_are_unpriced(self):
        """F6: three unprioritised actionable siblings render
        `0 actionable items at priority ≤ 2` — correctly, they cannot be
        compared — and the recommendation used to turn that `0` into
        "nothing else is waiting at this priority". Same brain rule as
        B1 (`constraints.md:110-118`): incomparable is not zero."""
        self.unpriced("0002-none", "0003-none", "0004-none")
        line = self.recommended()
        self.assertNotIn("nothing else is waiting at this priority", line)
        self.assertEqual(
            line,
            "Recommended: narrow — nothing comparable is waiting at this "
            "priority; 3 actionable items with no priority cannot be compared "
            "either way, so the backlog is not established as empty; a "
            "smaller next round costs less than another full one.")
        # AC11: the Recommended line is exactly one sentence.
        self.assertEqual(line.count("."), 1, line)

    def test_recommendation_does_not_claim_an_empty_backlog_when_items_are_unreadable(self):
        """F5, verbatim from the orchestrator's fact-check: the backlog
        line already said `2 items unreadable and excluded` while the
        very next line said "nothing else is waiting at this priority"."""
        self.corrupt("0008-corrupt", "0009-corrupt")
        line = self.recommended()
        self.assertNotIn("nothing else is waiting at this priority", line)
        self.assertEqual(
            line,
            "Recommended: narrow — nothing comparable is waiting at this "
            "priority; 2 unreadable items cannot be compared either way, so "
            "the backlog is not established as empty; a smaller next round "
            "costs less than another full one.")
        self.assertEqual(line.count("."), 1, line)

    def test_recommendation_names_both_unknown_populations_at_once(self):
        self.unpriced("0002-none")
        self.corrupt("0009-corrupt")
        line = self.recommended()
        self.assertIn("1 actionable item with no priority and 1 unreadable "
                      "item cannot be compared either way", line)
        self.assertEqual(line.count("."), 1, line)

    def test_recommendation_is_unqualified_only_when_nothing_is_unknown(self):
        """The qualifier is not unconditional: with every sibling priced
        and readable the backlog really is established empty, and the
        sentence says so."""
        self.other("0002-p9", priority=9)
        self.assertEqual(
            self.recommended(),
            "Recommended: narrow — nothing else is waiting at this priority, "
            "so a smaller next round costs less than another full one.")

    def test_recommendation_is_one_sentence_on_every_branch(self):
        """AC11, swept rather than sampled: the qualifiers F5/F6 add and
        the code spans F8 adds all land on this line, and a single stray
        full stop in any one branch breaks the contract. The pre-existing
        `count(".") == 1` guard only ever ran the `defer` branch."""
        branches = {
            "clean narrow": lambda: None,
            "defer": lambda: self.other("0002-p1", priority=1),
            "unpriced": lambda: self.unpriced("0002-none", "0003-none"),
            "unreadable": lambda: self.corrupt("0009-corrupt"),
            "both": lambda: (self.unpriced("0002-none"),
                             self.corrupt("0009-corrupt")),
            "no priority": self.unprioritise,
            "defer with unknowns": lambda: (self.other("0002-p1", priority=1),
                                            self.corrupt("0009-corrupt")),
        }
        for name, arrange in branches.items():
            with self.subTest(branch=name):
                # Each branch needs its own repo. Tearing down first and
                # setting up second keeps the pairing balanced: the outer
                # setUp owns the fixture the first iteration discards, and
                # the outer tearDown owns the one the last leaves behind.
                self.tearDown()
                self.setUp()
                arrange()
                line = self.recommended()
                self.assertEqual(line.count("."), 1, (name, line))

    def test_continue_consequence_names_what_it_cannot_compare(self):
        """F6 on the third surface: `waiting` asserted the same
        unqualified conclusion the recommendation did."""
        self.unpriced("0002-none", "0003-none", "0004-none")
        self.assertIn("the 0 items at priority ≤ 2 keep waiting, alongside "
                      "3 actionable items with no priority that cannot be "
                      "compared;", self.continue_line())

    def test_backlog_and_continue_lines_agree_in_number_at_one(self):
        """F7: both sentences read `1 items` today while `dropped` in the
        same function pluralises correctly."""
        self.other("0002-p1", priority=1)
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        self.assertIn("- backlog: 1 actionable item at priority ≤ 2, "
                      "1 actionable in total", section)
        self.assertNotIn("1 actionable items", section)
        self.assertIn("the 1 item at priority ≤ 2 keeps waiting", section)
        self.assertNotIn("1 items at priority", section)

    def test_backlog_and_continue_lines_stay_plural_above_one(self):
        self.other("0002-p1", priority=1)
        self.other("0003-p2", priority=2)
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        self.assertIn("- backlog: 2 actionable items at priority ≤ 2, "
                      "2 actionable in total", section)
        self.assertIn("the 2 items at priority ≤ 2 keep waiting", section)

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
            "cannot be compared until it has one; run `factory priority "
            "0001-runaway <n>`, then `factory packet 0001-runaway` to "
            "re-render this decision.")
        self.assertNotIn("re-read this packet", section)

    def test_every_placeholder_command_in_the_section_is_backticked(self):
        """F8: `<n>` matches CommonMark's inline raw-HTML open-tag
        production, so a markdown renderer swallows it and the operator
        is shown `factory priority 0001-runaway ,` — and for a
        no-priority item these commands are the only route to a
        decision. All 12 shipped packets backtick their placeholders.

        Keyed on the placeholder *shape*, not on the literal `<n>`: the
        defect is CommonMark's open-tag production, which any
        `<word>` triggers, so a future `<id>` or `<option>` added to this
        section is caught by the same guard rather than needing a new one.
        """
        self.unprioritise()
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        placeholder = re.compile(r"<[A-Za-z][^>]*>")
        lines = [l for l in section.splitlines() if placeholder.search(l)]
        self.assertEqual(len(lines), 2, lines)
        for line in lines:
            # Splitting on backticks, the even-indexed segments are the
            # text outside code spans — where a placeholder gets swallowed.
            outside = "".join(line.split("`")[::2])
            self.assertIsNone(placeholder.search(outside), line)

    def test_defer_consequence_backticks_its_command(self):
        section = self.section(packet.render_packet(self.repo, "0001-runaway"))
        defer = [l for l in section.splitlines() if l.startswith("- defer — ")]
        self.assertEqual(len(defer), 1, defer)
        self.assertIn("drop its priority with `factory priority "
                      "0001-runaway <n>`.", defer[0])

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
        self.assertIn("- backlog: 1 actionable item at priority ≤ 2, "
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
        self.assertIn("the 1 item at priority ≤ 2 keeps waiting", section)

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


class TestDecisionSectionAndVerbAreCoupled(unittest.TestCase):
    """AC1-AC7, AC12, AC15 (item 0027): the bidirectional
    section-to-bullet invariant, over every (paused-from x reason class)
    pair the engine can park.

    A decision section and the verb that answers it are two surfaces of
    one fact. Asserting them separately, each from a fixture that pins
    one stage, is exactly how the shipped renderer came to show the whole
    `## Cost decision` screen and then tell the operator to run
    `/factory:run`.
    """

    ITEM = "0001-runaway"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)

    def fresh(self, paused_from, reason_key):
        """A fresh repo per case: an item can only be parked once, so the
        matrix cannot share one temp dir."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        initrepo.init(repo)
        park_matrix_fixture(repo, self.ITEM, paused_from,
                            PARK_REASONS[reason_key])
        return repo

    def test_matrix_a_rendered_decision_section_implies_its_own_verb(self):
        """AC5. For every case in which a decision section renders,
        exactly one `## Respond` bullet renders and its leading command is
        that section's answering verb."""
        for paused_from in PARKED_FROM:
            for reason_key in PARK_REASONS:
                with self.subTest(paused_from=paused_from,
                                  reason=reason_key):
                    repo = self.fresh(paused_from, reason_key)
                    md = packet.render_packet(repo, self.ITEM)
                    bullets = respond_bullets(md)
                    self.assertEqual(len(bullets), 1, bullets)
                    command = leading_command(bullets[0])
                    if "## Cost decision" in md:
                        self.assertTrue(
                            command.startswith(DECISION_VERB["cost"]),
                            command)
                    if "## Redesign decision" in md:
                        self.assertTrue(
                            command.startswith(DECISION_VERB["approach"]),
                            command)

    def test_matrix_a_decision_verb_implies_its_own_section(self):
        """AC6. No bullet naming `factory cost-answer` renders unless
        `cost_decision_lines` returned non-empty, and likewise for
        `factory approach-answer` and `redesign_decision_lines`."""
        for paused_from in PARKED_FROM:
            for reason_key in PARK_REASONS:
                with self.subTest(paused_from=paused_from,
                                  reason=reason_key):
                    repo = self.fresh(paused_from, reason_key)
                    meta, _body = items.load_item(repo, self.ITEM)
                    md = packet.render_packet(repo, self.ITEM)
                    bullets = respond_bullets(md)
                    self.assertEqual(len(bullets), 1, bullets)
                    command = leading_command(bullets[0])
                    if command.startswith(DECISION_VERB["cost"]):
                        self.assertNotEqual(
                            packet.cost_decision_lines(
                                repo, self.ITEM, meta), [])
                    if command.startswith(DECISION_VERB["approach"]):
                        self.assertNotEqual(
                            packet.redesign_decision_lines(
                                repo, self.ITEM, meta), [])

    def test_a_plan_origin_cost_park_names_cost_answer_not_factory_run(self):
        """AC2. The filed defect: the decision screen renders and the
        answering verb does not."""
        repo = self.fresh("plan", "cost")
        md = packet.render_packet(repo, self.ITEM)
        self.assertIn("## Cost decision", md)
        respond = md.split("## Respond\n", 1)[1]
        bullets = respond_bullets(md)
        self.assertEqual(len(bullets), 1, bullets)
        self.assertEqual(
            leading_command(bullets[0]),
            "factory cost-answer 0001-runaway <continue|narrow|defer>")
        self.assertEqual(respond.count("/factory:run"), 0, respond)

    def test_an_assure_origin_cost_park_names_neither_confirm_nor_waive(self):
        """AC3 — the anti-shadowing guard, and the reason the conjunct is
        deleted only as part of the hoist.

        `assure` is in `cost.REWORK_FROM` (`cost.py:26`), so this park is
        reachable. `factory waive` is admitted by `assure.py` and treated
        as authoritative by `machine.py:584-586`: a fix that merely
        deleted `paused_from == "implement"` in place, leaving the cost
        arm below the `assure` arm at `packet.py:327`, would ship the item
        on an unanswered spend gate — strictly worse than today's
        fallthrough.
        """
        repo = self.fresh("assure", "cost")
        md = packet.render_packet(repo, self.ITEM)
        self.assertIn("## Cost decision", md)
        respond = md.split("## Respond\n", 1)[1]
        self.assertEqual(len(respond_bullets(md)), 1, respond)
        self.assertIn("factory cost-answer 0001-runaway", respond)
        self.assertNotIn("factory confirm", respond)
        self.assertNotIn("factory waive", respond)

    def test_an_implement_origin_respond_block_is_byte_identical(self):
        """AC4. The canonical path does not regress."""
        repo = self.fresh("implement", "cost")
        md = packet.render_packet(repo, self.ITEM)
        self.assertEqual(
            md.split("## Respond\n", 1)[1],
            "Reply in session, or use the factory CLI to record your "
            "decision.\n\n- `factory cost-answer 0001-runaway "
            "<continue|narrow|defer>` — record the cost decision.\n")

    def test_an_approach_cap_park_resolves_to_approach_answer_everywhere(self):
        """AC12 (J-003 regression). The `approach cap:` arm is already
        reason-keyed and already first, so the hoist must leave it
        behaviourally unchanged from every origin."""
        for paused_from in PARKED_FROM:
            with self.subTest(paused_from=paused_from):
                repo = self.fresh(paused_from, "approach")
                md = packet.render_packet(repo, self.ITEM)
                respond = md.split("## Respond\n", 1)[1]
                bullets = respond_bullets(md)
                self.assertEqual(len(bullets), 1, bullets)
                self.assertEqual(
                    leading_command(bullets[0]),
                    "factory approach-answer 0001-runaway "
                    "<continue|narrow|defer>")
                for other in ("factory confirm", "factory waive",
                              "factory choice", "factory cost-answer",
                              "/factory:run"):
                    self.assertNotIn(other, respond)

    def test_every_reason_prefix_arm_precedes_every_stage_keyed_arm(self):
        """AC1/AC15 — the structural half, read off the source.

        The brain rule (`constraints.md`, judgement on bid-0137): the
        selector that names a pause's answer verb must be reason-keyed,
        and every reason-prefix arm must precede every stage-keyed arm.
        `tests/test_approach.py:752-761` pins the same discipline
        behaviourally for the sibling prefix; this pins the order itself,
        so a later edit cannot re-introduce the shadowing without a
        failing test. The `if` count pins the no-registry constraint:
        exactly two prefix arms plus two stage arms.
        """
        source = inspect.getsource(packet.respond_action_lines)
        body = source.split('"""', 2)[2]
        lines = body.splitlines()
        prefix_arms = [i for i, line in enumerate(lines)
                       if "reason.startswith(" in line]
        stage_arms = [i for i, line in enumerate(lines)
                      if "paused_from ==" in line]
        self.assertEqual(len(prefix_arms), 2, body)
        self.assertEqual(len(stage_arms), 2, body)
        self.assertLess(max(prefix_arms), min(stage_arms), body)
        cost_arm = [line for line in lines if "breaker.PAUSE_PREFIX" in line]
        self.assertEqual(len(cost_arm), 1, cost_arm)
        self.assertNotIn("paused_from", cost_arm[0])
        self.assertEqual(
            sum(1 for line in lines if line.strip().startswith("if ")), 4,
            body)

    def test_the_cost_section_gate_is_not_widened_to_blocked(self):
        """AC15. `packet.py:95`'s `waiting-human` condition is untouched;
        the bid-0079 claim was struck at triage as false as written."""
        source = inspect.getsource(packet.cost_decision_lines)
        self.assertIn('if meta.get("stage") != "waiting-human":', source)
        self.assertNotIn("blocked", source)


class TestNarrowConsequenceNamesThePark(unittest.TestCase):
    """AC8/AC9 (item 0027): the `narrow` consequence hands the operator a
    resume command, and `machine.py:620-622` lets a `waiting-human` item
    resume only to its recorded `paused-from`. A literal `implement`
    there is a copy-pasteable command that errors on every non-implement
    park — the same defect class as the headline `/factory:run`.

    An absent `paused-from` is *named*, never interpolated: a Python
    `None` on the page is the very defect the absorbed 0028 arm removes
    from the refusal path.
    """

    ITEM = "0001-runaway"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)

    def fresh(self, paused_from):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        initrepo.init(repo)
        park_matrix_fixture(repo, self.ITEM, paused_from,
                            PARK_REASONS["cost"])
        return repo

    def narrow_line(self, repo):
        lines = [line for line in packet.render_packet(
            repo, self.ITEM).splitlines()
            if line.startswith("- narrow — ")]
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def run_cli(self, repo, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(repo), *args])
        return code, out.getvalue(), err.getvalue()

    def test_a_plan_origin_narrow_line_names_the_park_not_implement(self):
        """AC8, first half."""
        repo = self.fresh("plan")
        self.assertIn(f"factory advance {self.ITEM} plan",
                      self.narrow_line(repo))
        self.assertNotIn(f"factory advance {self.ITEM} implement",
                         packet.render_packet(repo, self.ITEM))

    def test_an_implement_origin_narrow_line_is_byte_identical(self):
        """AC4's spirit for this line: the canonical park is unchanged."""
        repo = self.fresh("implement")
        self.assertEqual(
            self.narrow_line(repo),
            "- narrow — records the decision; edit plan.md, then factory "
            "advance 0001-runaway implement. v1 does not narrow scope for "
            "you.")

    def test_the_rendered_narrow_command_is_admitted_by_the_engine(self):
        """AC8, second half: the command is not merely different, it is
        the one the engine accepts."""
        repo = self.fresh("plan")
        line = self.narrow_line(repo)
        match = re.search(r"factory advance (\S+) (\S+?)\.", line)
        self.assertIsNotNone(match, line)
        code, _out, err = self.run_cli(repo, "advance", match.group(1),
                                       match.group(2))
        self.assertEqual(code, 0, err)
        self.assertEqual(
            items.load_item(repo, self.ITEM)[0]["stage"], "plan")

    def test_the_literal_implement_command_is_refused_from_that_park(self):
        """AC8, third half: the shipped line's command really does error
        from a plan-origin park, so this is a live defect, not a
        cosmetic one."""
        repo = self.fresh("plan")
        code, _out, err = self.run_cli(repo, "advance", self.ITEM,
                                       "implement")
        self.assertEqual(code, 2, err)
        self.assertIn("may only resume to 'plan'", err)

    def test_a_park_with_no_paused_from_renders_no_python_none(self):
        """AC9. The field is named, not interpolated — in both
        renderers."""
        repo = self.fresh("plan")
        meta, body = items.load_item(repo, self.ITEM)
        meta.pop("paused-from")
        items.save_item(repo, meta, body)
        markdown = packet.render_packet(repo, self.ITEM)
        page = packet.render_packet_html(repo, self.ITEM)
        self.assertIn("## Cost decision", markdown)
        self.assertNotIn("None", markdown)
        self.assertNotIn("None", page)
        self.assertIn("`- paused-from: <stage>`", self.narrow_line(repo))


class ReceiptLinesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def _item(self, item_id="0001-thing", **extra):
        meta = {"id": item_id, "title": "Thing", "stage": "review",
                "kind": "backend", "priority": 1,
                "created": "2026-07-03T10:00:00Z",
                "updated": "2026-07-03T10:00:00Z"}
        meta.update(extra)
        items.save_item(self.repo, meta, "# Thing\n")
        return meta

    def _labels(self, meta):
        return dict(packet.receipt_lines(self.repo, meta))

    def test_declared_tier_and_depth_lines(self):
        meta = self._item(tier="bug")
        lines = self._labels(meta)
        self.assertEqual(lines["tier"], "bug (declared)")
        self.assertEqual(
            lines["depth"],
            "research off, review light, assure node "
            "(tier bug profile, source defaults)")

    def test_undeclared_tier_says_so(self):
        meta = self._item()
        self.assertEqual(self._labels(meta)["tier"],
                         "feature (default — no tier declared)")

    def test_empty_tier_value_is_not_a_declaration(self):
        """Twin of the depth recorder's call site in machine.advance: an
        empty `tier:` line parses to '' with the key present, so keying on
        presence would print `feature (declared)` for a tier nothing
        declared — on the very receipt this item adds to make depth
        auditable. Nothing validates tier on read (only set_tier does, on
        the CLI write path; validate.py checks it not at all)."""
        meta = self._item()
        meta["tier"] = ""
        lines = self._labels(meta)
        self.assertEqual(lines["tier"], "feature (default — no tier declared)")
        self.assertIn("source defaults", lines["depth"])

    def test_repro_line_unverified_for_bug_tier_without_flag(self):
        meta = self._item(tier="bug")
        self.assertIn("bug tier, repro unverified",
                      self._labels(meta)["repro"])

    def test_repro_line_armed_when_bug_flag_set(self):
        meta = self._item(tier="bug", bug=True)
        self.assertIn("bug flag set", self._labels(meta)["repro"])
        self.assertNotIn("repro unverified", self._labels(meta)["repro"])

    def test_no_repro_line_for_a_non_bug_item(self):
        self.assertNotIn("repro", self._labels(self._item(tier="feature")))
        self.assertNotIn("repro", self._labels(self._item(
            item_id="0002-thing", tier="epic")))

    def test_no_triage_line_without_a_triage_intake_event(self):
        self.assertNotIn("triage", self._labels(self._item(tier="bug")))

    def test_triage_line_unverified_without_repro_confirmed(self):
        meta = self._item(tier="bug")
        logs.append_event(self.repo, meta["id"], "triage.intake",
                          {"mode": "bug-intake", "council": "none",
                           "source": "factory-bug"})
        text = self._labels(meta)["triage"]
        self.assertIn("no council triage — bug intake, repro UNVERIFIED", text)
        self.assertIn("source: triage.intake event", text)
        self.assertNotIn("repro-confirmed", text)

    def test_triage_line_confirmed_with_repro_confirmed(self):
        meta = self._item(tier="bug")
        logs.append_event(self.repo, meta["id"], "triage.intake",
                          {"mode": "bug-intake", "council": "none",
                           "source": "factory-bug"})
        logs.append_event(self.repo, meta["id"], "repro.confirmed",
                          {"command": "foo", "exit": 1})
        text = self._labels(meta)["triage"]
        self.assertIn("no council triage — bug intake, repro-confirmed", text)

    def test_triage_intake_with_a_council_is_not_a_bug_intake(self):
        meta = self._item(tier="bug")
        logs.append_event(self.repo, meta["id"], "triage.intake",
                          {"council": "six-seat"})
        self.assertNotIn("triage", self._labels(meta))

    def test_no_receipt_line_carries_a_figure_or_a_saving_claim(self):
        for kw in ({"tier": "bug"}, {"tier": "bug", "bug": True},
                   {"tier": "epic"}, {}):
            meta = self._item(item_id="0001-thing", **kw)
            logs.append_event(self.repo, meta["id"], "triage.intake",
                              {"council": "none"})
            for label, text in packet.receipt_lines(self.repo, meta):
                self.assertIsNone(re.search(r"\d{3,}", text), text)
                for banned in ("saved", "saving", "token"):
                    self.assertNotIn(banned, text.lower(), f"{label}: {text}")

    def test_both_renderers_share_one_builder(self):
        meta = self._item(tier="bug")
        sentinel = [("sentinel", "one definition both renderers")]
        with mock.patch.object(packet, "receipt_lines",
                               return_value=sentinel):
            md = packet.render_packet(self.repo, meta["id"])
            html = packet.render_packet_html(self.repo, meta["id"])
        self.assertIn("- sentinel: one definition both renderers", md)
        self.assertIn(
            "<li><strong>sentinel:</strong> one definition both renderers</li>",
            html)

    def test_both_renderers_render_the_same_label_value_set(self):
        meta = self._item(tier="bug")
        logs.append_event(self.repo, meta["id"], "triage.intake",
                          {"council": "none"})
        md = packet.render_packet(self.repo, meta["id"])
        html = packet.render_packet_html(self.repo, meta["id"])
        for label, text in packet.receipt_lines(self.repo, meta):
            self.assertIn(f"- {label}: {text}", md)
            self.assertIn(f"<li><strong>{label}:</strong>", html)

    def test_no_new_html_section_id_or_stylesheet_rule(self):
        meta = self._item(tier="bug")
        html = packet.render_packet_html(self.repo, meta["id"])
        self.assertEqual(html.count('<ul class="meta">'), 1)
        for banned in ('id="depth"', 'id="receipt"', 'id="tier"',
                       ".receipt", ".depth {"):
            self.assertNotIn(banned, html)


if __name__ == "__main__":
    unittest.main()
