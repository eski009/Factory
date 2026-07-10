import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import cost, initrepo, items, logs

ITEM = "0001-x"


class CostTestCase(unittest.TestCase):
    """Shared fixture: one item, log lines stamped via FACTORY_NOW."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        meta = {"id": ITEM, "title": "X", "stage": "idea", "kind": "backend",
                "created": "2026-07-03T00:00:00Z",
                "updated": "2026-07-03T00:00:00Z"}
        items.save_item(self.repo, meta, "")
        os.environ["FACTORY_NOW"] = "2026-07-03T00:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def log_at(self, ts, event, data=None):
        os.environ["FACTORY_NOW"] = ts
        logs.append_event(self.repo, ITEM, event, data)

    def advance_at(self, ts, frm, to):
        self.log_at(ts, "stage.advance", {"from": frm, "to": to})


class SummarizeTimelineTest(CostTestCase):
    def test_linear_two_stage_timeline(self):
        self.log_at("2026-07-03T10:00:00Z", "item.created")
        self.advance_at("2026-07-03T10:05:00Z", "idea", "triage")
        self.advance_at("2026-07-03T10:20:00Z", "triage", "spec")
        os.environ["FACTORY_NOW"] = "2026-07-03T10:30:00Z"
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["stages"]["idea"]["active_seconds"], 300)
        self.assertEqual(summary["stages"]["triage"]["active_seconds"], 900)
        self.assertEqual(summary["stages"]["spec"]["active_seconds"], 600)
        self.assertEqual(summary["active_seconds"], 1800)
        self.assertEqual(summary["waiting_seconds"], 0)
        self.assertEqual(summary["elapsed_seconds"],
                         summary["active_seconds"] + summary["waiting_seconds"])
        self.assertEqual(summary["advances"], 2)
        self.assertEqual(summary["window"],
                         {"start": "2026-07-03T10:00:00Z",
                          "end": "2026-07-03T10:30:00Z", "open": True})

    def test_pause_gap_attributes_idle_to_waiting(self):
        # 2h design + 16h waiting-human + 30m design: active 9000, waiting 57600.
        self.advance_at("2026-07-03T00:00:00Z", "spec", "design")
        self.advance_at("2026-07-03T02:00:00Z", "design", "waiting-human")
        self.advance_at("2026-07-03T18:00:00Z", "waiting-human", "design")
        self.advance_at("2026-07-03T18:30:00Z", "design", "plan")
        os.environ["FACTORY_NOW"] = "2026-07-03T18:30:00Z"
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["stages"]["design"]["active_seconds"], 9000)
        self.assertEqual(summary["stages"]["design"]["entries"], 1)
        self.assertEqual(summary["waiting_seconds"], 57600)
        self.assertEqual(summary["elapsed_seconds"],
                         summary["active_seconds"] + summary["waiting_seconds"])
        self.assertEqual(summary["elapsed_seconds"], 66600)

    def test_rework_reentry_counts_entries_and_retries(self):
        self.advance_at("2026-07-03T00:00:00Z", "plan", "implement")
        self.advance_at("2026-07-03T01:00:00Z", "implement", "review")
        self.log_at("2026-07-03T01:30:00Z", "review.rejected", {"round": 1})
        self.advance_at("2026-07-03T01:30:00Z", "review", "implement")
        self.advance_at("2026-07-03T02:30:00Z", "implement", "review")
        os.environ["FACTORY_NOW"] = "2026-07-03T03:00:00Z"
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["stages"]["implement"]["entries"], 2)
        self.assertEqual(summary["stages"]["implement"]["active_seconds"], 7200)
        self.assertEqual(summary["stages"]["review"]["active_seconds"], 3600)
        self.assertEqual(summary["retries"], 1)
        self.assertEqual(summary["advances"], 4)

    def test_open_item_window_ends_at_frozen_now(self):
        self.log_at("2026-07-03T09:00:00Z", "item.created")
        os.environ["FACTORY_NOW"] = "2026-07-03T11:00:00Z"
        summary = cost.summarize(self.repo, ITEM)
        self.assertTrue(summary["window"]["open"])
        self.assertEqual(summary["window"]["end"], "2026-07-03T11:00:00Z")
        self.assertEqual(summary["stages"]["idea"]["active_seconds"], 7200)

    def test_done_item_window_closes_at_final_advance(self):
        self.advance_at("2026-07-03T05:00:00Z", "ship", "done")
        os.environ["FACTORY_NOW"] = "2026-07-03T09:00:00Z"
        summary = cost.summarize(self.repo, ITEM)
        self.assertFalse(summary["window"]["open"])
        self.assertEqual(summary["window"]["end"], "2026-07-03T05:00:00Z")

    def test_malformed_stage_advance_is_skipped(self):
        self.log_at("2026-07-03T09:00:00Z", "item.created")
        self.log_at("2026-07-03T09:10:00Z", "stage.advance", "oops")
        self.advance_at("2026-07-03T09:30:00Z", "idea", "triage")
        os.environ["FACTORY_NOW"] = "2026-07-03T09:30:00Z"
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["advances"], 1)
        self.assertEqual(summary["stages"]["idea"]["active_seconds"], 1800)

    def test_summary_has_contract_keys_and_serializes(self):
        os.environ["FACTORY_NOW"] = "2026-07-03T01:00:00Z"
        summary = cost.summarize(self.repo, ITEM)
        expected = {"item", "window", "elapsed_seconds", "active_seconds",
                    "waiting_seconds", "advances", "retries", "dispatches",
                    "stages", "measured", "unmeasured", "invalid_spend_events",
                    "corrupt_log_lines"}
        self.assertEqual(set(summary), expected)
        self.assertIsNone(summary["measured"])
        self.assertEqual(summary["unmeasured"], "orchestrator main-loop tokens")
        json.dumps(summary, indent=2, sort_keys=True)

    def test_unknown_item_raises_item_error(self):
        with self.assertRaises(items.ItemError):
            cost.summarize(self.repo, "0999-none")


class SpendRollupTest(CostTestCase):
    def test_measured_and_proxy_rollup(self):
        self.log_at("2026-07-03T10:00:00Z", "item.created")
        self.log_at("2026-07-03T10:01:00Z", "spend",
                    {"provenance": "measured", "stage": "implement",
                     "source": "factory-implement", "dispatches": 3,
                     "tokens": {"input": 1000, "output": 200}})
        self.log_at("2026-07-03T10:02:00Z", "spend",
                    {"provenance": "measured", "stage": "review",
                     "dispatches": 2,
                     "tokens": {"input": 500, "output": 100, "total": 600}})
        self.log_at("2026-07-03T10:03:00Z", "spend",
                    {"provenance": "proxy", "stage": "implement",
                     "dispatches": 4})
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["dispatches"], 9)
        self.assertEqual(summary["measured"],
                         {"events": 2, "input": 1500, "output": 300,
                          "total": 600})
        self.assertEqual(summary["stages"]["implement"]["dispatches"], 7)
        self.assertEqual(summary["stages"]["review"]["dispatches"], 2)
        self.assertEqual(summary["invalid_spend_events"], 0)

    def test_malformed_spend_event_excluded_and_counted(self):
        self.log_at("2026-07-03T10:00:00Z", "spend",
                    {"provenance": "proxy", "dispatches": 2,
                     "tokens": {"input": 5}})
        self.log_at("2026-07-03T10:01:00Z", "spend",
                    {"provenance": "proxy", "dispatches": 3})
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["invalid_spend_events"], 1)
        self.assertEqual(summary["dispatches"], 3)
        self.assertIsNone(summary["measured"])

    def test_stage_less_spend_counts_in_total_only(self):
        self.log_at("2026-07-03T10:00:00Z", "spend",
                    {"provenance": "proxy", "dispatches": 5})
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["dispatches"], 5)
        self.assertEqual(
            sum(b["dispatches"] for b in summary["stages"].values()), 0)


class RenderTextTest(CostTestCase):
    def figure_summary(self):
        self.advance_at("2026-07-03T00:00:00Z", "spec", "design")
        self.advance_at("2026-07-03T02:00:00Z", "design", "waiting-human")
        self.advance_at("2026-07-03T18:00:00Z", "waiting-human", "design")
        self.log_at("2026-07-03T18:10:00Z", "spend",
                    {"provenance": "measured", "stage": "design",
                     "dispatches": 2, "tokens": {"input": 800, "output": 150}})
        os.environ["FACTORY_NOW"] = "2026-07-03T18:30:00Z"
        return cost.summarize(self.repo, ITEM)

    def test_every_figure_line_carries_exactly_one_provenance_tag(self):
        text = cost.render_text(self.figure_summary())
        tags = ("[proxy]", "[measured]", "[unmeasured]")
        untagged = ("item:", "window:", "elapsed:", "invalid spend events:")
        for line in text.splitlines():
            if line.startswith("["):
                self.assertEqual(sum(line.count(tag) for tag in tags), 1, line)
            else:
                self.assertTrue(line.startswith(untagged), line)

    def test_measured_line_and_stage_dispatches(self):
        text = cost.render_text(self.figure_summary())
        self.assertIn(
            "[measured] tokens: input 800, output 150 (1 spend events)", text)
        self.assertIn(
            "[proxy] stage design: active 02h 30m, entries 1, dispatches 2",
            text)
        self.assertIn("[proxy] waiting: 16h 00m", text)

    def test_unmeasured_literal_present_even_with_empty_log(self):
        os.environ["FACTORY_NOW"] = "2026-07-03T01:00:00Z"
        text = cost.render_text(cost.summarize(self.repo, ITEM))
        self.assertIn(
            "[unmeasured] UNMEASURED: orchestrator main-loop tokens", text)
        self.assertIn("[measured] tokens: none logged", text)

    def test_forbidden_renderings_never_appear(self):
        for summary in (self.figure_summary(),
                        cost.summarize(self.repo, ITEM)):
            text = cost.render_text(summary)
            self.assertIn("UNMEASURED", text)
            self.assertNotIn("$0", text)
            self.assertNotIn("≈$", text)
            for line in text.splitlines():
                self.assertNotEqual(line.strip(), "-")

    def test_invalid_spend_events_line_appended(self):
        self.log_at("2026-07-03T10:00:00Z", "spend",
                    {"provenance": "estimated"})
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        text = cost.render_text(cost.summarize(self.repo, ITEM))
        self.assertIn(
            "invalid spend events: 1 (excluded; run factory validate)", text)

    def test_duration_format(self):
        self.assertEqual(cost.format_duration(9000), "02h 30m")
        self.assertEqual(cost.format_duration(57600), "16h 00m")
        self.assertEqual(cost.format_duration(93780), "1d 02h 03m")
        self.assertEqual(cost.format_duration(59), "00h 00m")

    def test_total_only_events_render_total_not_zero_splits(self):
        self.log_at("2026-07-03T10:00:00Z", "spend",
                    {"provenance": "measured", "stage": "plan",
                     "dispatches": 1, "tokens": {"total": 146946}})
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        summary = cost.summarize(self.repo, ITEM)
        text = cost.render_text(summary)
        self.assertIn("total 146946", text)
        self.assertNotIn("input 0", text)
        self.assertNotIn("output 0", text)
        receipt = cost.render_receipt(summary)
        self.assertIn("total 146946", receipt)
        self.assertIn("(1 events)", receipt)
        self.assertNotIn("input 0", receipt)
        self.assertNotIn("output 0", receipt)

    def test_mixed_keys_render_all_observed(self):
        self.log_at("2026-07-03T10:00:00Z", "spend",
                    {"provenance": "measured", "stage": "plan",
                     "dispatches": 1,
                     "tokens": {"input": 100, "output": 50}})
        self.log_at("2026-07-03T10:01:00Z", "spend",
                    {"provenance": "measured", "stage": "plan",
                     "dispatches": 1, "tokens": {"total": 200}})
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        summary = cost.summarize(self.repo, ITEM)
        text = cost.render_text(summary)
        self.assertIn("input 100, output 50, total 200", text)


class RenderReceiptTest(CostTestCase):
    def test_receipt_is_exactly_three_tagged_bullets(self):
        self.advance_at("2026-07-03T00:00:00Z", "spec", "design")
        os.environ["FACTORY_NOW"] = "2026-07-03T01:00:00Z"
        receipt = cost.render_receipt(cost.summarize(self.repo, ITEM))
        lines = receipt.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("- [proxy] active "))
        self.assertEqual(lines[1], "- [measured] tokens: none logged")
        self.assertEqual(
            lines[2], "- [unmeasured] UNMEASURED: orchestrator main-loop tokens")

    def test_receipt_measured_line_with_tokens(self):
        self.log_at("2026-07-03T00:00:00Z", "spend",
                    {"provenance": "measured", "stage": "review",
                     "source": "factory-review", "dispatches": 6,
                     "tokens": {"input": 182340, "output": 21877}})
        os.environ["FACTORY_NOW"] = "2026-07-03T00:10:00Z"
        receipt = cost.render_receipt(cost.summarize(self.repo, ITEM))
        self.assertIn(
            "- [measured] tokens: input 182340, output 21877 (1 events)",
            receipt)
        self.assertIn("6 dispatches", receipt)


class CorruptLogSurfacingTest(CostTestCase):
    """Item spec 0007 §2: skipped-line count surfaced on every surface."""

    def corrupt_line(self):
        path = self.repo / f".factory/items/{ITEM}/log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write('{"event": "spend", "ts": \n')

    def test_summarize_counts_corrupt_lines(self):
        self.log_at("2026-07-03T10:00:00Z", "item.created")
        self.corrupt_line()
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["corrupt_log_lines"], 1)

    def test_clean_log_zero_and_other_fields_unchanged(self):
        self.log_at("2026-07-03T10:00:00Z", "item.created")
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["corrupt_log_lines"], 0)
        self.assertEqual(summary["advances"], 0)
        self.assertEqual(summary["stages"]["idea"]["active_seconds"], 300)
        self.assertEqual(summary["invalid_spend_events"], 0)

    def test_render_text_corrupt_line_when_nonzero(self):
        self.log_at("2026-07-03T10:00:00Z", "item.created")
        self.corrupt_line()
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        text = cost.render_text(cost.summarize(self.repo, ITEM))
        self.assertIn(
            "corrupt log lines: 1 (skipped; run factory validate)", text)

    def test_render_text_silent_when_zero(self):
        self.log_at("2026-07-03T10:00:00Z", "item.created")
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        text = cost.render_text(cost.summarize(self.repo, ITEM))
        self.assertNotIn("corrupt log lines", text)

    def test_receipt_suffixes_proxy_bullet_when_nonzero(self):
        self.log_at("2026-07-03T10:00:00Z", "item.created")
        self.corrupt_line()
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        receipt = cost.render_receipt(cost.summarize(self.repo, ITEM))
        lines = receipt.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("- [proxy] active "))
        self.assertTrue(
            lines[0].endswith(", 1 corrupt log lines skipped"), lines[0])

    def test_receipt_byte_identical_when_zero(self):
        self.log_at("2026-07-03T10:00:00Z", "item.created")
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        receipt = cost.render_receipt(cost.summarize(self.repo, ITEM))
        self.assertEqual(receipt, "\n".join([
            "- [proxy] active 00h 05m (waiting 00h 00m), "
            "0 advances, 0 dispatches, 0 retries",
            "- [measured] tokens: none logged",
            "- [unmeasured] UNMEASURED: orchestrator main-loop tokens",
        ]))


if __name__ == "__main__":
    unittest.main()
