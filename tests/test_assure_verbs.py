import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.factory import factory
from scripts.factory.lib import assure, items, logs, machine, paths


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
