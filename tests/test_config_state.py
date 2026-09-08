import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.factory.lib import config_state


class ConfigStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name).resolve()
        (self.repo / ".factory").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write_config(self, value):
        (self.repo / ".factory" / "config.json").write_text(
            json.dumps(value), encoding="utf-8")

    def replace_config(self, value):
        replacement = self.repo / ".factory" / "replacement.json"
        replacement.write_text(json.dumps(value), encoding="utf-8")
        replacement.replace(self.repo / ".factory" / "config.json")

    def valid(self, gates=None):
        return {"version": 1, "merge": "auto",
                "gates": ["design"] if gates is None else gates}

    def test_capture_validates_and_enabled_reads_only_the_snapshot(self):
        self.write_config(self.valid(["design", "assure"]))
        snapshot = config_state.capture(self.repo)

        self.assertTrue(config_state.enabled(snapshot, "design"))
        self.assertTrue(config_state.enabled(snapshot, "assure"))
        self.assertFalse(config_state.enabled(snapshot, "cost"))

        self.write_config(self.valid([]))
        self.assertTrue(config_state.enabled(snapshot, "design"))
        with self.assertRaises(config_state.ConfigStateError):
            config_state.revalidate(snapshot)

    def test_disabled_to_enabled_replacement_is_rejected(self):
        self.write_config(self.valid([]))
        snapshot = config_state.capture(self.repo)
        self.write_config(self.valid(["design"]))

        self.assertFalse(config_state.enabled(snapshot, "design"))
        with self.assertRaises(config_state.ConfigStateError):
            config_state.revalidate(snapshot)

    def test_concurrent_enabled_to_disabled_replacement_during_capture_refuses(self):
        self.write_config(self.valid(["design"]))
        real_validate = config_state.validate

        def replace_then_validate(*args, **kwargs):
            self.replace_config(self.valid([]))
            return real_validate(*args, **kwargs)

        with mock.patch.object(
                config_state, "validate", side_effect=replace_then_validate):
            with self.assertRaises(config_state.ConfigStateError):
                config_state.capture(self.repo)

    def test_concurrent_disabled_to_enabled_replacement_during_capture_refuses(self):
        self.write_config(self.valid([]))
        real_validate = config_state.validate

        def replace_then_validate(*args, **kwargs):
            self.replace_config(self.valid(["design"]))
            return real_validate(*args, **kwargs)

        with mock.patch.object(
                config_state, "validate", side_effect=replace_then_validate):
            with self.assertRaises(config_state.ConfigStateError):
                config_state.capture(self.repo)

    def test_missing_malformed_duplicate_invalid_and_unsafe_config_refuse(self):
        config = self.repo / ".factory" / "config.json"
        cases = {
            "missing": None,
            "invalid utf8": b"\xff",
            "malformed": b"{",
            "duplicate": b'{"version":1,"version":1,"merge":"auto","gates":[]}',
            "not object": b"[]",
            "schema invalid": b'{"version":1,"merge":"surprise","gates":[]}',
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                config.unlink(missing_ok=True)
                if payload is not None:
                    config.write_bytes(payload)
                with self.assertRaises(config_state.ConfigStateError):
                    config_state.capture(self.repo)

        config.unlink(missing_ok=True)
        outside = self.repo / "outside.json"
        outside.write_text(json.dumps(self.valid()))
        config.symlink_to(outside)
        with self.assertRaises(config_state.ConfigStateError):
            config_state.capture(self.repo)


if __name__ == "__main__":
    unittest.main()
