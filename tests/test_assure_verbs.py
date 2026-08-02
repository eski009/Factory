import hashlib
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.factory import factory
from scripts.factory.lib import assure, initrepo, items, logs, machine, paths


def make_item(repo, stage="assure", paused_from=None):
    meta = {"id": "0001-a", "title": "A", "stage": stage, "kind": "ui",
            "journeys": "J-001",
            "created": "2026-07-15T10:00:00Z", "updated": "2026-07-15T10:00:00Z"}
    if paused_from:
        meta["paused-from"] = paused_from
        meta["paused-reason"] = "test"
    items.save_item(repo, meta, "# A\n")
    return meta


class AssureVerbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = "2026-07-15T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_waiver_requires_reason(self):
        make_item(self.repo)
        with self.assertRaises(machine.GateError):
            assure.record_waiver(self.repo, "0001-a", "")
        with self.assertRaises(machine.GateError):
            assure.record_waiver(self.repo, "0001-a", "   ")

    def test_waiver_logs_event_with_reason(self):
        make_item(self.repo)
        assure.record_waiver(self.repo, "0001-a", "no browser in this env")
        events = logs.read_events(self.repo, "0001-a")
        waived = [e for e in events if e["event"] == "assure.waived"]
        self.assertEqual(len(waived), 1)
        self.assertEqual(waived[0]["data"]["reason"], "no browser in this env")

    def test_waiver_refused_outside_assure_context(self):
        make_item(self.repo, stage="verify")
        with self.assertRaises(machine.GateError):
            assure.record_waiver(self.repo, "0001-a", "why not")

    def test_waiver_allowed_when_paused_from_assure(self):
        make_item(self.repo, stage="waiting-human", paused_from="assure")
        assure.record_waiver(self.repo, "0001-a", "fixture impossible here")
        self.assertEqual(logs.count_events(self.repo, "0001-a", "assure.waived"), 1)

    def test_confirm_requires_assure_passed(self):
        make_item(self.repo, stage="waiting-human", paused_from="assure")
        with self.assertRaises(machine.GateError):
            assure.record_confirmation(self.repo, "0001-a")
        logs.append_event(self.repo, "0001-a", "assure.passed")
        path = assure.record_confirmation(self.repo, "0001-a")
        self.assertTrue(path.exists())
        self.assertEqual(logs.count_events(self.repo, "0001-a", "assure.confirmed"), 1)

    def test_confirm_refuses_stale_assure_passed_after_rework(self):
        make_item(self.repo, stage="waiting-human", paused_from="assure")
        logs.append_event(self.repo, "0001-a", "assure.passed")
        logs.append_event(self.repo, "0001-a", "implement.completed")
        with self.assertRaises(machine.GateError):
            assure.record_confirmation(self.repo, "0001-a")

    def test_cli_waive_and_confirm(self):
        from scripts.factory.lib import initrepo
        initrepo.init(self.repo)
        make_item(self.repo)
        code = factory.main(["--repo", str(self.repo), "waive", "0001-a",
                             "--reason", "env blocker"])
        self.assertEqual(code, 0)
        logs.append_event(self.repo, "0001-a", "assure.passed")
        self.assertEqual(factory.main(["--repo", str(self.repo), "confirm", "0001-a"]), 0)
        with patch("sys.stderr", new_callable=StringIO) as err:
            code = factory.main(["--repo", str(self.repo), "waive", "0001-a",
                                 "--reason", "   "])
        self.assertEqual(code, 2)
        self.assertIn("refused", err.getvalue())

    def test_waiver_writes_artifact_file(self):
        make_item(self.repo)
        assure.record_waiver(self.repo, "0001-a", "no browser here")
        path = Path(self.repo) / ".factory" / "items" / "0001-a" / "assurance" / "waiver.md"
        self.assertTrue(path.exists())
        self.assertIn("no browser here", path.read_text(encoding="utf-8"))

    def test_cmd_log_refuses_human_only_events(self):
        from scripts.factory.lib import initrepo
        initrepo.init(self.repo)
        make_item(self.repo)
        for event in ("assure.waived", "assure.confirmed"):
            with patch("sys.stderr", new_callable=StringIO) as err:
                code = factory.main(["--repo", str(self.repo), "log", "0001-a", event])
            self.assertEqual(code, 1)
            self.assertIn("factory waive", err.getvalue())
            self.assertIn("human verb", err.getvalue())


class TestFileBaseDefect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        initrepo.init(self.repo, product="demo")
        items.save_item(self.repo, {
            "id": "0001-thing", "title": "Thing", "stage": "assure",
            "kind": "backend", "tier": "feature",
            "created": "2026-07-03T10:00:00Z",
            "updated": "2026-07-03T10:00:00Z"}, "# Thing\n")
        # validate_tree reconciles stage against the log (item 0009); seed
        # the stage.advance so the assure-stage fixture is log-consistent
        # once filing appends assure.filed to it.
        logs.append_event(self.repo, "0001-thing", "item.created")
        logs.append_event(self.repo, "0001-thing", "stage.advance",
                          {"to": "assure"})
        self.fingerprint = hashlib.sha256(
            "J-001\nS2\ncard is gated on restrictions.length".encode("utf-8")
        ).hexdigest()

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def file(self, fingerprint=None, title="Card gated on restrictions.length"):
        return assure.file_base_defect(
            self.repo, "0001-thing", "J-001", "S2",
            fingerprint or self.fingerprint, title,
            expected="card shows", actual="card missing")

    def test_first_filing_creates_an_open_unprioritised_bug_item(self):
        owner, deduped = self.file()
        self.assertFalse(deduped)
        meta, body = items.load_item(self.repo, owner)
        self.assertEqual(meta["stage"], "idea")
        self.assertEqual(meta["kind"], "backend")
        self.assertEqual(meta["tier"], "bug")
        self.assertNotIn("priority", meta)
        self.assertNotIn("bug", meta)
        self.assertIn(f"- base-defect-fingerprint: {self.fingerprint}", body)
        self.assertIn("- filed-from: 0001-thing", body)
        self.assertIn("- journey: J-001", body)
        self.assertIn("- scenario: S2", body)
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_second_filing_dedupes_to_the_same_item(self):
        first, _ = self.file()
        second, deduped = self.file()
        self.assertEqual(first, second)
        self.assertTrue(deduped)
        dirs = [p.name for p in paths.items_dir(self.repo).iterdir()
                if (p / "item.md").exists()]
        self.assertEqual(sorted(dirs), sorted(["0001-thing", first]))

    def test_filing_logs_assure_filed_on_the_originating_item(self):
        owner, _ = self.file()
        self.file()
        events = [e for e in logs.read_events(self.repo, "0001-thing")
                  if e["event"] == "assure.filed"]
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["data"], {
            "owner": owner, "journey": "J-001", "scenario": "S2",
            "deduped": False})
        self.assertEqual(events[1]["data"]["deduped"], True)

    def test_a_done_owner_does_not_dedupe(self):
        first, _ = self.file()
        meta, body = items.load_item(self.repo, first)
        meta["stage"] = "done"
        items.save_item(self.repo, meta, body)
        second, deduped = self.file()
        self.assertNotEqual(first, second)
        self.assertFalse(deduped)

    def test_a_different_fingerprint_files_a_new_item(self):
        first, _ = self.file()
        second, _ = self.file(fingerprint="f" * 64, title="Other defect")
        self.assertNotEqual(first, second)

    def test_bad_fingerprint_refused(self):
        with self.assertRaises(machine.GateError):
            self.file(fingerprint="not-hex")

    def test_empty_title_refused(self):
        with self.assertRaises(machine.GateError):
            self.file(title="   ")

    def test_unknown_originating_item_refused(self):
        with self.assertRaises(items.ItemError):
            assure.file_base_defect(self.repo, "0099-nope", "J-001", "S2",
                                    self.fingerprint, "T")


class TestFileBaseDefectCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        factory.main(["--repo", self.repo, "init"])
        factory.main(["--repo", self.repo, "add", "Thing", "--kind", "backend"])

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", self.repo, *args])
        return code, out.getvalue(), err.getvalue()

    def test_verb_prints_the_owner_id_and_is_idempotent(self):
        args = ("file-base-defect", "0001-thing", "--journey", "J-001",
                "--scenario", "S2", "--fingerprint", "a" * 64,
                "--title", "Stale values")
        code, first, _ = self.run_cli(*args)
        self.assertEqual(code, 0)
        code, second, _ = self.run_cli(*args)
        self.assertEqual(code, 0)
        self.assertEqual(first.strip(), second.strip())

    def test_bad_fingerprint_exits_2(self):
        code, _, err = self.run_cli(
            "file-base-defect", "0001-thing", "--journey", "J-001",
            "--scenario", "S2", "--fingerprint", "nope", "--title", "T")
        self.assertEqual(code, 2)
        self.assertIn("refused:", err)
