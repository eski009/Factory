"""Item 0033: confirmed bugs use verification as ship evidence.

The declaration is explicit and orthogonal to materiality (`tier`), repro
evidence (`bug`) and journey impact (`journeys`).  These tests drive the
production state machine and both packet renderers; a list-shape assertion on
its own would not prove that the substituted ship gate actually runs.
"""

import os
import inspect
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, machine, packet, paths


ITEM = "0001-bug"


def make_item(repo, *, stage="verify", assurance="verify", journeys="J-004"):
    meta = {
        "id": ITEM,
        "title": "Small bug",
        "stage": stage,
        "kind": "backend",
        "tier": "bug",
        "bug": True,
        "journeys": journeys,
        "priority": 1,
        "created": "2026-08-04T00:00:00Z",
        "updated": "2026-08-04T00:00:00Z",
    }
    if assurance is not None:
        meta["assurance"] = assurance
    items.save_item(repo, meta, "# Small bug\n")
    return meta


class BugAssuranceModeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-08-04T00:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def mark_round(self):
        logs.append_event(self.repo, ITEM, "stage.advance",
                          {"from": "plan", "to": "implement"})

    def test_assurance_field_round_trips(self):
        make_item(self.repo)
        meta, _ = items.load_item(self.repo, ITEM)
        self.assertEqual(meta["assurance"], "verify")
        self.assertIn("\nassurance: verify\n",
                      (paths.item_dir(self.repo, ITEM) / "item.md").read_text())

    def test_verify_mode_skips_assure_with_affected_journeys(self):
        sequence = machine.stage_sequence(
            "backend", journeys="J-004", assurance="verify")
        self.assertNotIn("design", sequence)
        self.assertNotIn("assure", sequence)
        self.assertEqual(sequence[-4:], ["review", "verify", "ship", "done"])

        meta = make_item(self.repo)
        self.assertEqual(machine.next_stage(meta), "ship")

    def test_absent_or_unknown_mode_keeps_assure(self):
        for assurance in (None, "unknown", "VERIFY", ""):
            with self.subTest(assurance=assurance):
                sequence = machine.stage_sequence(
                    "backend", journeys="J-004", assurance=assurance)
                self.assertIn("assure", sequence)

    def test_engine_does_not_route_assurance_from_tier_or_bug(self):
        source = (inspect.getsource(machine.runs_assure)
                  + inspect.getsource(machine.stage_sequence)
                  + inspect.getsource(machine._gate_ship))
        self.assertNotIn("tier", source)
        self.assertNotIn('meta.get("bug")', source)

    def test_journeys_none_still_skips_assure(self):
        for assurance in (None, "verify", "unknown"):
            with self.subTest(assurance=assurance):
                self.assertNotIn(
                    "assure",
                    machine.stage_sequence(
                        "backend", journeys="none", assurance=assurance))

    def test_fresh_verify_green_drives_production_path_to_done(self):
        make_item(self.repo)
        self.mark_round()

        with self.assertRaisesRegex(machine.GateError, "verify.green"):
            machine.advance(self.repo, ITEM, "ship")

        logs.append_event(self.repo, ITEM, "verify.green",
                          {"criteria": "2/2", "tests": "green"})
        meta, _ = machine.advance(self.repo, ITEM, "ship")
        self.assertEqual(meta["stage"], "ship")
        self.assertEqual(logs.count_events(self.repo, ITEM, "assure.passed"), 0)

        logs.append_event(self.repo, ITEM, "ship.merged")
        meta, _ = machine.advance(self.repo, ITEM, "done")
        self.assertEqual(meta["stage"], "done")

    def test_stale_verify_green_is_refused(self):
        make_item(self.repo)
        self.mark_round()
        logs.append_event(self.repo, ITEM, "verify.green")
        logs.append_event(self.repo, ITEM, "stage.advance",
                          {"from": "verify", "to": "implement"})

        with self.assertRaisesRegex(
                machine.GateError, "predates the latest entry into implement"):
            machine.advance(self.repo, ITEM, "ship")

    def test_declaration_while_at_assure_does_not_strand_item(self):
        meta = make_item(self.repo, stage="assure")
        self.mark_round()
        logs.append_event(self.repo, ITEM, "verify.green")

        self.assertEqual(machine.next_stage(meta), "ship")
        advanced, _ = machine.advance(self.repo, ITEM, "ship")
        self.assertEqual(advanced["stage"], "ship")

    def test_unknown_mode_uses_assurance_ship_gate(self):
        make_item(self.repo, stage="assure", assurance="unknown")
        self.mark_round()
        logs.append_event(self.repo, ITEM, "verify.green")

        with self.assertRaisesRegex(machine.GateError, "assure.passed"):
            machine.advance(self.repo, ITEM, "ship")

    def test_unknown_mode_is_reported_by_tree_validation(self):
        make_item(self.repo, assurance="unknown")
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("assurance" in error for error in errors), errors)


class PacketArtifactApplicabilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-08-04T00:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def render(self, *, assurance="verify", journeys="J-004"):
        make_item(self.repo, stage="done", assurance=assurance,
                  journeys=journeys)
        return (packet.render_packet(self.repo, ITEM),
                packet.render_packet_html(self.repo, ITEM))

    def test_omitted_stage_artifacts_render_na_in_both_packets(self):
        markdown, page = self.render()
        marker = "n/a (not in this item's sequence)"

        self.assertIn(f"- design/choice.md: {marker}", markdown)
        self.assertIn(f"- assurance/verdicts.json: {marker}", markdown)
        self.assertIn(f"design/choice.md — {marker}", page)
        self.assertIn(f"assurance/verdicts.json — {marker}", page)

    def test_spec_owned_impact_and_included_stage_artifacts_stay_missing(self):
        markdown, page = self.render()
        marker = "n/a (not in this item's sequence)"

        self.assertIn("- assurance/impact.json: no", markdown)
        self.assertNotIn(f"assurance/impact.json: {marker}", markdown)
        self.assertIn("assurance/impact.json (not yet)", page)
        self.assertNotIn(f"assurance/impact.json ({marker})", page)
        self.assertIn("- plan.md: no", markdown)
        self.assertIn("plan.md (not yet)", page)

    def test_journeys_none_uses_same_engine_derived_na_state(self):
        markdown, page = self.render(assurance=None, journeys="none")
        marker = "n/a (not in this item's sequence)"
        self.assertIn(f"- assurance/verdicts.json: {marker}", markdown)
        self.assertIn(f"assurance/verdicts.json — {marker}", page)

    def test_item_that_runs_assure_retains_existing_missing_state(self):
        markdown, page = self.render(assurance=None, journeys="J-004")
        self.assertIn("- assurance/verdicts.json: no", markdown)
        self.assertIn("assurance/verdicts.json (not yet)", page)
        self.assertNotIn(
            "assurance/verdicts.json: n/a (not in this item's sequence)",
            markdown)

    def test_existing_artifact_remains_linked_when_stage_is_omitted(self):
        make_item(self.repo, stage="done")
        verdicts = paths.item_dir(self.repo, ITEM) / "assurance/verdicts.json"
        verdicts.parent.mkdir(parents=True, exist_ok=True)
        verdicts.write_text("historical evidence\n", encoding="utf-8")

        markdown = packet.render_packet(self.repo, ITEM)
        page = packet.render_packet_html(self.repo, ITEM)
        self.assertIn("- assurance/verdicts.json: yes — [open]", markdown)
        self.assertIn(verdicts.resolve().as_uri(), page)
        self.assertNotIn(
            "assurance/verdicts.json — n/a (not in this item's sequence)",
            page)


class BugSkillDeclarationTest(unittest.TestCase):
    def test_bug_intake_declares_verify_as_assurance_mode(self):
        skill = (Path(__file__).resolve().parents[1]
                 / "skills/factory-bug/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`assurance: verify`", skill)
        self.assertIn("independent of `tier: bug`", skill)
        self.assertIn("journey impact", skill)

    def test_verify_and_ship_skills_route_the_declared_mode(self):
        root = Path(__file__).resolve().parents[1]
        verify = (root / "skills/factory-verify/SKILL.md").read_text(
            encoding="utf-8")
        ship = (root / "skills/factory-ship/SKILL.md").read_text(
            encoding="utf-8")
        for text in (verify, ship):
            self.assertIn("`assurance: verify`", text)
            self.assertIn("`verify.green`", text)
        self.assertIn("factory advance ITEM ship", verify)


if __name__ == "__main__":
    unittest.main()
