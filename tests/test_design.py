import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import design, initrepo, items, logs, machine


def put(repo, stage="design", kind="ui", paused_from=None):
    meta = {"id": "0001-thing", "title": "Thing", "stage": stage, "kind": kind,
            "priority": 1, "created": "2026-07-03T10:00:00Z",
            "updated": "2026-07-03T10:00:00Z"}
    if paused_from:
        meta["paused-from"] = paused_from
        meta["paused-reason"] = "pick a design option"
    items.save_item(repo, meta, "# Thing\n")


class TestRecordChoice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_choice_at_design_stage(self):
        put(self.repo)
        path = design.record_choice(self.repo, "0001-thing", "b", notes="darker header")
        text = path.read_text(encoding="utf-8")
        self.assertIn("- option: b", text)
        self.assertIn("- ts: 2026-07-03T12:00:00Z", text)
        self.assertIn("darker header", text)
        events = logs.read_events(self.repo, "0001-thing")
        self.assertEqual(events[-1]["event"], "design.choice")
        self.assertEqual(events[-1]["data"], {"option": "b"})

    def test_choice_while_paused_from_design(self):
        put(self.repo, stage="waiting-human", paused_from="design")
        path = design.record_choice(self.repo, "0001-thing", "a")
        self.assertIn("(no notes)", path.read_text(encoding="utf-8"))

    def test_choice_overwrites(self):
        put(self.repo)
        design.record_choice(self.repo, "0001-thing", "a")
        design.record_choice(self.repo, "0001-thing", "c")
        self.assertIn("- option: c",
                      (self.repo / ".factory/items/0001-thing/design/choice.md").read_text())

    def test_backend_kind_refused(self):
        put(self.repo, kind="backend", stage="plan")
        with self.assertRaises(machine.GateError):
            design.record_choice(self.repo, "0001-thing", "a")

    def test_wrong_stage_refused_with_stage_named(self):
        put(self.repo, stage="implement")
        with self.assertRaises(machine.GateError) as ctx:
            design.record_choice(self.repo, "0001-thing", "a")
        self.assertIn("implement", str(ctx.exception))

    def test_paused_from_other_stage_refused(self):
        put(self.repo, stage="waiting-human", paused_from="review")
        with self.assertRaises(machine.GateError):
            design.record_choice(self.repo, "0001-thing", "a")

    def test_missing_item_raises_item_error(self):
        with self.assertRaises(items.ItemError):
            design.record_choice(self.repo, "0999-nope", "a")

    def test_bad_option_refused(self):
        put(self.repo)
        with self.assertRaises(machine.GateError) as ctx:
            design.record_choice(self.repo, "0001-thing", "zzz")
        self.assertIn("option must be one of a-d or none", str(ctx.exception))

    def test_option_re_matches_exactly_the_five_options(self):
        for opt in ("a", "b", "c", "d", "none"):
            self.assertTrue(design.OPTION_RE.match(opt), opt)
        for bad in ("e", "None", "NONE", "ab", "nonee", "anone",
                    "no", "", " a", "a ", "a-d"):
            self.assertFalse(design.OPTION_RE.match(bad), bad)

    def test_none_at_design_stage(self):
        put(self.repo)
        path = design.record_choice(self.repo, "0001-thing", "none",
                                    notes="[none] missing the timeline view")
        text = path.read_text(encoding="utf-8")
        self.assertIn("- option: none", text)
        self.assertIn("[none] missing the timeline view", text)
        events = logs.read_events(self.repo, "0001-thing")
        self.assertEqual(events[-1]["event"], "design.choice")
        self.assertEqual(events[-1]["data"], {"option": "none"})

    def test_none_while_paused_from_design(self):
        put(self.repo, stage="waiting-human", paused_from="design")
        path = design.record_choice(self.repo, "0001-thing", "none")
        self.assertIn("- option: none", path.read_text(encoding="utf-8"))

    def test_none_backend_kind_refused(self):
        put(self.repo, kind="backend", stage="plan")
        with self.assertRaises(machine.GateError):
            design.record_choice(self.repo, "0001-thing", "none")

    def test_none_wrong_stage_refused(self):
        put(self.repo, stage="implement")
        with self.assertRaises(machine.GateError) as ctx:
            design.record_choice(self.repo, "0001-thing", "none")
        self.assertIn("implement", str(ctx.exception))

    def test_pick_after_none_overwrites(self):
        put(self.repo)
        design.record_choice(self.repo, "0001-thing", "none",
                             notes="[none] not these")
        design.record_choice(self.repo, "0001-thing", "b")
        text = (self.repo /
                ".factory/items/0001-thing/design/choice.md").read_text()
        self.assertIn("- option: b", text)
        self.assertNotIn("- option: none", text)

    def test_structured_notes_preserved_verbatim(self):
        put(self.repo)
        notes = "[b] like the header | [none] missing timeline"
        path = design.record_choice(self.repo, "0001-thing", "b", notes=notes)
        self.assertIn(notes, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
