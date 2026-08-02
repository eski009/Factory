import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import cost, initrepo, items, logs

ITEM = "0001-x"

# `.factory/` is gitignored (`.gitignore:6`), so this repo's own item
# specs are absent on CI and in a fresh clone. Prose assertions against
# them are guarded on the file, never weakened.
SPEC_0016 = (Path(__file__).resolve().parents[1]
             / ".factory/items/0016-cost-circuit-breaker-on-engine-authorita"
               "/spec.md")


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

    def test_rework_reentry_counts_entries_and_rework_edges(self):
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
        self.assertEqual(summary["rework_edges"], 1)
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
                    "waiting_seconds", "advances", "rework_edges",
                    "dispatches",
                    "stages", "measured", "unmeasured", "invalid_spend_events",
                    "corrupt_log_lines"}
        self.assertEqual(set(summary), expected)
        self.assertIsNone(summary["measured"])
        self.assertEqual(summary["unmeasured"], "orchestrator main-loop tokens")
        json.dumps(summary, indent=2, sort_keys=True)

    def test_unknown_item_raises_item_error(self):
        with self.assertRaises(items.ItemError):
            cost.summarize(self.repo, "0999-none")


class ReworkEdgeSubstrateTest(CostTestCase):
    """AC1/AC2: the rework figure is derived from the backward
    stage.advance edges the engine writes itself, never from the
    rejection events a skill may forget to log."""

    def seed_full_fixture(self):
        # 4 backward edges into implement + 2 review.rejected + 2
        # assure.rejected, on one item. The edges are the substrate; the
        # rejection events are demoted telemetry.
        self.advance_at("2026-07-03T00:00:00Z", "plan", "implement")
        self.advance_at("2026-07-03T01:00:00Z", "implement", "review")
        self.log_at("2026-07-03T01:10:00Z", "review.rejected", {"round": 1})
        self.advance_at("2026-07-03T01:30:00Z", "review", "implement")
        self.advance_at("2026-07-03T02:00:00Z", "implement", "review")
        self.log_at("2026-07-03T02:10:00Z", "review.rejected", {"round": 2})
        self.advance_at("2026-07-03T02:30:00Z", "review", "implement")
        self.advance_at("2026-07-03T03:00:00Z", "implement", "assure")
        self.log_at("2026-07-03T03:10:00Z", "assure.rejected", {"round": 1})
        self.advance_at("2026-07-03T03:30:00Z", "assure", "implement")
        self.advance_at("2026-07-03T04:00:00Z", "implement", "assure")
        self.log_at("2026-07-03T04:10:00Z", "assure.rejected", {"round": 2})
        self.advance_at("2026-07-03T04:30:00Z", "assure", "implement")
        os.environ["FACTORY_NOW"] = "2026-07-03T05:00:00Z"

    def strip_events(self, names):
        path = self.repo / f".factory/items/{ITEM}/log.jsonl"
        kept = [line for line in path.read_text(encoding="utf-8").splitlines()
                if json.loads(line)["event"] not in names]
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")

    def test_arm_a_edges_and_rejections_report_four(self):
        self.seed_full_fixture()
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["rework_edges"], 4)

    def test_arm_b_deleting_rejection_events_leaves_four(self):
        self.seed_full_fixture()
        self.strip_events({"review.rejected", "assure.rejected"})
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["rework_edges"], 4)

    def test_arm_c_deleting_edges_leaves_zero_with_all_rejections(self):
        self.seed_full_fixture()
        path = self.repo / f".factory/items/{ITEM}/log.jsonl"
        kept = []
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            data = event.get("data") or {}
            if (event["event"] == "stage.advance"
                    and data.get("to") == "implement"
                    and data.get("from") in ("review", "assure", "verify")):
                continue
            kept.append(line)
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["rework_edges"], 0)

    def test_summary_has_no_retries_key(self):
        self.seed_full_fixture()
        self.assertNotIn("retries", cost.summarize(self.repo, ITEM))

    def test_cost_module_never_reads_rejection_events(self):
        src = (Path(__file__).resolve().parents[1]
               / "scripts/factory/lib/cost.py").read_text(encoding="utf-8")
        self.assertNotIn("review.rejected", src)
        self.assertNotIn("assure.rejected", src)

    def test_verify_to_implement_counts_although_engine_admits_none(self):
        self.advance_at("2026-07-03T00:00:00Z", "verify", "implement")
        os.environ["FACTORY_NOW"] = "2026-07-03T01:00:00Z"
        self.assertEqual(cost.summarize(self.repo, ITEM)["rework_edges"], 1)

    def test_missing_from_field_falls_back_to_tracked_stage(self):
        self.advance_at("2026-07-03T00:00:00Z", "plan", "implement")
        self.advance_at("2026-07-03T01:00:00Z", "implement", "review")
        # older log line: no "from" — summarize's tracked current_stage is
        # "review", so this is still a rework edge.
        self.log_at("2026-07-03T01:30:00Z", "stage.advance", {"to": "implement"})
        os.environ["FACTORY_NOW"] = "2026-07-03T02:00:00Z"
        self.assertEqual(cost.summarize(self.repo, ITEM)["rework_edges"], 1)

    def test_waiting_human_resume_is_never_a_rework_edge(self):
        """AC23 (M6): rework laundered through waiting-human is real cost
        and zero backward edges. Stated, not implied."""
        self.advance_at("2026-07-03T00:00:00Z", "review", "verify")
        self.advance_at("2026-07-03T01:00:00Z", "verify", "waiting-human")
        self.advance_at("2026-07-03T02:00:00Z", "waiting-human", "verify")
        self.advance_at("2026-07-03T03:00:00Z", "verify", "assure")
        self.advance_at("2026-07-03T04:00:00Z", "assure", "waiting-human")
        self.advance_at("2026-07-03T05:00:00Z", "waiting-human", "assure")
        os.environ["FACTORY_NOW"] = "2026-07-03T06:00:00Z"
        self.assertEqual(cost.summarize(self.repo, ITEM)["rework_edges"], 0)

    def test_render_text_states_the_substrate_and_its_undercount(self):
        self.seed_full_fixture()
        text = cost.render_text(cost.summarize(self.repo, ITEM))
        self.assertIn(
            "[proxy] rework substrate: backward stage.advance edges "
            "(review|assure|verify → implement); rework routed through "
            "waiting-human is not counted", text)
        self.assertIn("rework edges: 4", text)
        self.assertNotIn("retries", text)

    @unittest.skipUnless(
        SPEC_0016.is_file(),
        ".factory/ is gitignored: item 0016's spec is absent on CI and in a "
        "fresh clone")
    def test_spec_states_the_undercount(self):
        spec = SPEC_0016.read_text(encoding="utf-8")
        self.assertIn("rework routed through `waiting-human` is not counted",
                      spec)


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


class PerStageAttributionTest(CostTestCase):
    """AC3/AC4: the stage bucket is the unit of attribution, and the two
    provenance classes never share a line."""

    def seed(self):
        self.advance_at("2026-07-03T00:00:00Z", "plan", "implement")
        self.advance_at("2026-07-03T01:00:00Z", "implement", "review")
        self.log_at("2026-07-03T01:05:00Z", "spend",
                    {"provenance": "measured", "stage": "implement",
                     "dispatches": 3, "tokens": {"input": 1000, "output": 200}})
        self.log_at("2026-07-03T01:06:00Z", "spend",
                    {"provenance": "measured", "stage": "implement",
                     "dispatches": 1, "tokens": {"total": 50}})
        self.log_at("2026-07-03T01:07:00Z", "spend",
                    {"provenance": "proxy", "stage": "review",
                     "dispatches": 2})
        os.environ["FACTORY_NOW"] = "2026-07-03T02:00:00Z"
        return cost.summarize(self.repo, ITEM)

    def test_bucket_key_set_is_fixed(self):
        summary = self.seed()
        for name, bucket in summary["stages"].items():
            self.assertEqual(
                set(bucket),
                {"active_seconds", "entries", "dispatches", "measured",
                 "proxy_events"}, name)

    def test_measured_tokens_attributed_to_the_named_stage(self):
        summary = self.seed()
        self.assertEqual(summary["stages"]["implement"]["measured"],
                         {"events": 2, "input": 1000, "output": 200,
                          "total": 50})
        self.assertEqual(summary["stages"]["implement"]["proxy_events"], 0)

    def test_proxy_events_counted_per_stage_without_tokens(self):
        summary = self.seed()
        self.assertEqual(summary["stages"]["review"]["proxy_events"], 1)
        self.assertIsNone(summary["stages"]["review"]["measured"])

    def test_stage_less_spend_never_distributed_across_stages(self):
        self.log_at("2026-07-03T10:00:00Z", "spend",
                    {"provenance": "measured", "dispatches": 1,
                     "tokens": {"total": 999}})
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["measured"]["total"], 999)
        for bucket in summary["stages"].values():
            self.assertIsNone(bucket["measured"])

    def test_render_text_separate_measured_and_unmeasured_stage_lines(self):
        text = cost.render_text(self.seed())
        self.assertIn(
            "[measured] stage implement: tokens input 1000, output 200, "
            "total 50 (2 spend events)", text)
        self.assertIn(
            "[unmeasured] stage review: tokens UNMEASURED "
            "(no spend events logged)", text)
        self.assertIn("[proxy] stage implement: active", text)

    def test_no_rendered_line_carries_two_provenance_tags(self):
        text = cost.render_text(self.seed())
        tags = ("[proxy]", "[measured]", "[unmeasured]")
        for line in text.splitlines():
            if line.startswith("["):
                self.assertEqual(sum(line.count(tag) for tag in tags), 1, line)

    def test_no_stage_line_is_silently_omitted(self):
        text = cost.render_text(self.seed())
        for name in ("implement", "review"):
            self.assertIn(f"[proxy] stage {name}:", text)
            self.assertTrue(
                f"[measured] stage {name}:" in text
                or f"[unmeasured] stage {name}:" in text, name)

    def test_receipt_appends_one_bullet_per_measured_stage(self):
        receipt = cost.render_receipt(self.seed())
        lines = receipt.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertEqual(
            lines[3],
            "- [measured] stage implement: input 1000, output 200, total 50 "
            "(2 events)")

    def test_receipt_unchanged_when_no_per_stage_measured_spend(self):
        self.advance_at("2026-07-03T00:00:00Z", "spec", "design")
        os.environ["FACTORY_NOW"] = "2026-07-03T01:00:00Z"
        receipt = cost.render_receipt(cost.summarize(self.repo, ITEM))
        self.assertEqual(len(receipt.splitlines()), 3)


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
            lines[0].endswith(", corrupt log lines skipped: 1"), lines[0])

    def test_receipt_byte_identical_when_zero(self):
        self.log_at("2026-07-03T10:00:00Z", "item.created")
        os.environ["FACTORY_NOW"] = "2026-07-03T10:05:00Z"
        receipt = cost.render_receipt(cost.summarize(self.repo, ITEM))
        self.assertEqual(receipt, "\n".join([
            "- [proxy] active 00h 05m (waiting 00h 00m), "
            "0 advances, 0 dispatches, 0 rework edges",
            "- [measured] tokens: none logged",
            "- [unmeasured] UNMEASURED: orchestrator main-loop tokens",
        ]))


class AggregateModeTest(unittest.TestCase):
    """AC5-AC8: a backlog-wide view that reports exactly three things
    plus the mandatory [unmeasured] line, and never aggregates across
    items — the two spend-event classes measure different quantities, so
    a sum has no provenance class."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T00:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def put(self, item_id, stage="implement", tier=None):
        meta = {"id": item_id, "title": item_id, "stage": stage,
                "kind": "backend", "created": "2026-07-03T00:00:00Z",
                "updated": "2026-07-03T00:00:00Z"}
        if tier:
            meta["tier"] = tier
        items.save_item(self.repo, meta, "")

    def log_at(self, item_id, ts, event, data=None):
        os.environ["FACTORY_NOW"] = ts
        logs.append_event(self.repo, item_id, event, data)

    def seed(self):
        # 0001: one measured spend event, one rework edge, spend carried
        #       by one of its two advances.
        self.put("0001-a")
        self.log_at("0001-a", "2026-07-03T00:00:00Z", "stage.advance",
                    {"from": "plan", "to": "implement"})
        self.log_at("0001-a", "2026-07-03T00:30:00Z", "spend",
                    {"provenance": "measured", "stage": "implement",
                     "dispatches": 1, "tokens": {"total": 100}})
        self.log_at("0001-a", "2026-07-03T01:00:00Z", "stage.advance",
                    {"from": "review", "to": "implement"})
        # 0002: no spend events at all, one advance.
        self.put("0002-b", stage="done", tier="feature")
        self.log_at("0002-b", "2026-07-03T00:00:00Z", "stage.advance",
                    {"from": "ship", "to": "done"})
        # 0003: a proxy-only spend event (valid, but not measured).
        self.put("0003-c", stage="done")
        self.log_at("0003-c", "2026-07-03T00:00:00Z", "spend",
                    {"provenance": "proxy", "stage": "spec", "dispatches": 2})
        self.log_at("0003-c", "2026-07-03T00:10:00Z", "stage.advance",
                    {"from": "ship", "to": "done"})
        os.environ["FACTORY_NOW"] = "2026-07-03T02:00:00Z"
        return cost.summarize_all(self.repo)

    def test_top_level_keys_are_exactly_items_and_coverage(self):
        summary = self.seed()
        self.assertEqual(set(summary), {"items", "coverage"})
        self.assertEqual(
            set(summary["coverage"]),
            {"items_with_spend", "items_total", "advances_with_spend",
             "advances_total", "done_items", "done_with_tier"})

    def test_coverage_figures_are_scanned_not_hardcoded(self):
        """AC8: seeded counts differ from this repo's 9/17."""
        # seed() appends to the logs, so it is called exactly once here:
        # a second call would double every scanned count.
        summary = self.seed()
        cov = summary["coverage"]
        self.assertEqual(cov["items_total"], 3)
        self.assertEqual(cov["items_with_spend"], 2)
        self.assertEqual(cov["advances_total"], 4)
        self.assertEqual(cov["advances_with_spend"], 2)
        self.assertEqual(cov["done_items"], 2)
        self.assertEqual(cov["done_with_tier"], 1)
        text = cost.render_all_text(summary)
        self.assertIn("[coverage] spend events present for 2 of 3 items; "
                      "2 of 4 stage advances carry one", text)
        self.assertNotIn("9 of 17", text)

    def test_measured_line_only_for_items_with_measured_spend(self):
        text = cost.render_all_text(self.seed())
        self.assertIn("[measured] 0001-a: tokens total 100 (1 spend events) "
                      "— LOWER BOUND (not summable)", text)
        self.assertNotIn("[measured] 0002-b:", text)
        self.assertNotIn("[measured] 0003-c:", text)

    def test_proxy_block_present_for_every_item(self):
        text = cost.render_all_text(self.seed())
        for item_id, edges in (("0001-a", 1), ("0002-b", 0), ("0003-c", 0)):
            self.assertIn(f"[proxy] {item_id}: advances ", text)
            self.assertIn(f"rework edges {edges}", text)
        self.assertIn("[proxy] stage implement: active ", text)

    def test_unmeasured_line_names_both_empty_populations(self):
        text = cost.render_all_text(self.seed())
        self.assertIn("[unmeasured] UNMEASURED: orchestrator main-loop "
                      "tokens; per-tier medians (1 of 2 done items carry a "
                      "tier)", text)

    def test_no_cross_item_aggregate_in_text_or_json(self):
        """AC6: the median clause is discharged as UNMEASURED, never as a
        number, and nothing sums or averages across items."""
        summary = self.seed()
        text = cost.render_all_text(summary)
        # 0001-a is the only item with measured tokens (100). Neither a
        # sum nor a mean of the population appears anywhere.
        self.assertNotIn("total: 100", text)
        for line in text.splitlines():
            lowered = line.lower()
            self.assertNotRegex(lowered, r"median[: ]+\d")
            self.assertNotRegex(lowered, r"\b(mean|average)\b")
            self.assertNotIn("cost per item", lowered)
            self.assertNotIn("across all items", lowered)
        payload = json.dumps(summary, sort_keys=True)
        json.loads(payload)
        self.assertEqual(set(json.loads(payload)), {"items", "coverage"})

    def test_every_figure_line_carries_one_tag(self):
        text = cost.render_all_text(self.seed())
        tags = ("[proxy]", "[measured]", "[unmeasured]", "[coverage]")
        for line in text.splitlines():
            self.assertTrue(line.startswith(tags), line)
            self.assertEqual(sum(line.count(tag) for tag in tags), 1, line)


if __name__ == "__main__":
    unittest.main()
