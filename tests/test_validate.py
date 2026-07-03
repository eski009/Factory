import json
import unittest
from pathlib import Path

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


class TestConfigSchema(unittest.TestCase):
    def test_default_config_valid(self):
        cfg = {"version": 1, "merge": "auto", "gates": ["design"]}
        self.assertEqual(validate(cfg, load("config")), [])

    def test_bad_merge_policy(self):
        cfg = {"version": 1, "merge": "yolo", "gates": []}
        self.assertTrue(validate(cfg, load("config")))


if __name__ == "__main__":
    unittest.main()
