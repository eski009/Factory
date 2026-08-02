import json
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, paths
from scripts.factory.lib.validate import validate

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def load(name):
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


GOOD_ITEM = {
    "id": "0001-dark-mode", "title": "Dark mode", "stage": "idea",
    "kind": "ui", "created": "2026-07-03T10:00:00Z",
    "updated": "2026-07-03T10:00:00Z",
}


class TestValidator(unittest.TestCase):
    def test_type_mismatch(self):
        self.assertTrue(validate("hi", {"type": "integer"}))

    def test_bool_is_not_integer(self):
        self.assertTrue(validate(True, {"type": "integer"}))

    def test_required_and_additional(self):
        schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}},
                  "additionalProperties": False}
        self.assertTrue(validate({}, schema))
        self.assertTrue(validate({"a": "x", "b": 1}, schema))
        self.assertEqual(validate({"a": "x"}, schema), [])

    def test_enum_pattern_minimum(self):
        self.assertTrue(validate("z", {"type": "string", "enum": ["a", "b"]}))
        self.assertTrue(validate("nope", {"type": "string", "pattern": "^\\d+$"}))
        self.assertTrue(validate(0, {"type": "integer", "minimum": 1}))

    def test_array_items(self):
        schema = {"type": "array", "items": {"type": "string", "enum": ["design"]}}
        self.assertEqual(validate(["design"], schema), [])
        self.assertTrue(validate(["nope"], schema))


class TestWorkItemSchema(unittest.TestCase):
    def test_good_item(self):
        self.assertEqual(validate(GOOD_ITEM, load("work-item")), [])

    def test_bad_stage_and_id(self):
        bad = dict(GOOD_ITEM, stage="shipping", id="1-x")
        errors = validate(bad, load("work-item"))
        self.assertEqual(len(errors), 2)

    def test_priority_must_be_positive_int(self):
        self.assertTrue(validate(dict(GOOD_ITEM, priority=0), load("work-item")))
        self.assertEqual(validate(dict(GOOD_ITEM, priority=1), load("work-item")), [])

    def test_bug_field_optional_boolean(self):
        schema = load("work-item")
        self.assertEqual(validate(dict(GOOD_ITEM, bug=True), schema), [])
        self.assertEqual(validate(GOOD_ITEM, schema), [])
        self.assertTrue(validate(dict(GOOD_ITEM, bug="yes"), schema))


class TestConfigSchema(unittest.TestCase):
    def test_default_config_valid(self):
        cfg = {"version": 1, "merge": "auto", "gates": ["design"]}
        self.assertEqual(validate(cfg, load("config")), [])

    def test_bad_merge_policy(self):
        cfg = {"version": 1, "merge": "yolo", "gates": []}
        self.assertTrue(validate(cfg, load("config")))


class TestValidateTreeToleratesInvalidUtf8(unittest.TestCase):
    """Item spec 0007 Task 5: validate flags invalid UTF-8, never crashes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_invalid_utf8_log_line_flagged_not_crash(self):
        meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "")
        log_path = paths.item_dir(self.repo, "0001-x") / "log.jsonl"
        with log_path.open("ab") as f:
            f.write(b'\xff\xfe{"event"\n')
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any(
            "log.jsonl:" in e and "invalid JSON" in e for e in errors))

    def test_invalid_utf8_ledger_line_flagged_not_crash(self):
        ledger_path = paths.ledgers_dir(self.repo) / "bids.jsonl"
        with ledger_path.open("ab") as f:
            f.write(b'\xff\xfe{"id"\n')
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any(
            "bids.jsonl:" in e and "invalid JSON" in e for e in errors))


class TestVerdictsAttributionSchema(unittest.TestCase):
    schema = None

    def setUp(self):
        self.schema = initrepo.load_schema("assurance-verdicts")

    def _payload(self, scenario):
        return {"item": "0001-thing", "journeys": [
            {"id": "J-001", "surface": "cli", "scenarios": [scenario]}]}

    def _scenario(self, **over):
        s = {"id": "S1", "verdict": "fail", "expected": "e", "actual": "a"}
        s.update(over)
        return s

    def test_scenario_without_attribution_still_valid(self):
        from scripts.factory.lib.validate import validate
        self.assertEqual(
            validate(self._payload(self._scenario()), self.schema, "v"), [])

    def test_full_attribution_shape_valid(self):
        from scripts.factory.lib.validate import validate
        scenario = self._scenario(
            attribution="pre-existing", owner="0002-stale-values",
            base={"branch": "main", "merge_base": "a" * 40,
                  "evidence": [{"type": "transcript",
                                "path": "assurance/base/" + "a" * 40 + "/t.txt"}]})
        self.assertEqual(
            validate(self._payload(scenario), self.schema, "v"), [])

    def test_unknown_attribution_class_rejected(self):
        from scripts.factory.lib.validate import validate
        errors = validate(self._payload(
            self._scenario(attribution="out-of-scope")), self.schema, "v")
        self.assertTrue(any("out-of-scope" in e for e in errors), errors)

    def test_malformed_owner_passes_the_schema_shape_check(self):
        from scripts.factory.lib.validate import validate
        errors = validate(self._payload(
            self._scenario(owner="not an id")), self.schema, "v")
        self.assertEqual(errors, [])

    def test_short_merge_base_rejected(self):
        from scripts.factory.lib.validate import validate
        errors = validate(self._payload(self._scenario(
            base={"branch": "main", "merge_base": "abc",
                  "evidence": [{"type": "transcript", "path": "p"}]})),
            self.schema, "v")
        self.assertTrue(errors)

    def test_base_requires_all_three_keys(self):
        from scripts.factory.lib.validate import validate
        errors = validate(self._payload(self._scenario(
            base={"merge_base": "a" * 40,
                  "evidence": [{"type": "transcript", "path": "p"}]})),
            self.schema, "v")
        self.assertTrue(any("branch" in e for e in errors), errors)

    def test_base_rejects_unknown_property(self):
        from scripts.factory.lib.validate import validate
        errors = validate(self._payload(self._scenario(
            base={"branch": "main", "merge_base": "a" * 40, "walked": True,
                  "evidence": [{"type": "transcript", "path": "p"}]})),
            self.schema, "v")
        self.assertTrue(any("walked" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
