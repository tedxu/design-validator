import unittest

import _path  # noqa: F401
from dvlib import schema

SCHEMA = {
    "type": "object",
    "required": ["id", "items"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": "A[0-9]+"},
        "n": {"type": "integer", "minimum": 1},
        "kind": {"enum": ["a", "b"]},
        "maybe": {"type": ["string", "null"]},
        "items": {"type": "array", "items": {"$ref": "#/definitions/item"}},
    },
    "definitions": {
        "item": {"type": "object", "required": ["x"], "properties": {"x": {"type": "boolean"}}},
    },
}


class ValidateTest(unittest.TestCase):
    def test_cases(self):
        cases = [
            ("valid", {"id": "A1", "items": [{"x": True}], "n": 2, "kind": "a", "maybe": None}, []),
            ("missing required", {"id": "A1"}, ["$: missing required 'items'"]),
            ("extra property", {"id": "A1", "items": [], "zz": 1}, ["$: unexpected property 'zz'"]),
            ("pattern is a full match", {"id": "A1x", "items": []}, ["$.id: 'A1x' does not match A[0-9]+"]),
            ("bool is not integer", {"id": "A1", "items": [], "n": True}, ["$.n: expected integer, got bool"]),
            ("minimum", {"id": "A1", "items": [], "n": 0}, ["$.n: 0 is less than 1"]),
            ("enum", {"id": "A1", "items": [], "kind": "c"}, ["$.kind: 'c' not in ['a', 'b']"]),
            ("ref item", {"id": "A1", "items": [{"x": 1}]}, ["$.items[0].x: expected boolean, got int"]),
            ("wrong root type", [], ["$: expected object, got list"]),
        ]
        for name, instance, want in cases:
            with self.subTest(name):
                self.assertEqual(schema.validate(instance, SCHEMA), want)

    def test_unsupported_keyword(self):
        with self.assertRaises(ValueError):
            schema.validate(1, {"oneOf": []})
        with self.assertRaises(ValueError):
            schema.check_schema({"properties": {"a": {"anyOf": []}}})

    def test_check_schema_accepts_supported(self):
        schema.check_schema(SCHEMA)


if __name__ == "__main__":
    unittest.main()
