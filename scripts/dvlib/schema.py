"""Validator for the JSON Schema subset used in schemas/*.schema.json."""
from __future__ import annotations

import json
import os
import re

SCHEMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "schemas")

SUPPORTED = {
    "type", "required", "properties", "additionalProperties", "enum", "items",
    "pattern", "minimum", "$ref", "definitions", "description", "title", "$schema",
}
_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def load_schema(name):
    with open(os.path.join(SCHEMA_DIR, f"{name}.schema.json"), encoding="utf-8") as f:
        return json.load(f)


def validate(instance, schema):
    errors = []
    _check(instance, schema, schema, "$", errors)
    return errors


def check_schema(node, path="$"):
    if not isinstance(node, dict):
        return
    unknown = set(node) - SUPPORTED
    if unknown:
        raise ValueError(f"unsupported schema keywords at {path}: {sorted(unknown)}")
    for key in ("properties", "definitions"):
        for name, child in node.get(key, {}).items():
            check_schema(child, f"{path}.{key}.{name}")
    for key in ("items", "additionalProperties"):
        if isinstance(node.get(key), dict):
            check_schema(node[key], f"{path}.{key}")


def _type_ok(value, name):
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def _resolve(root, ref):
    if not ref.startswith("#/"):
        raise ValueError(f"only local $ref is supported: {ref}")
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _check(value, schema, root, path, errors):
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise ValueError(f"unsupported schema keywords at {path}: {sorted(unknown)}")
    if "$ref" in schema:
        _check(value, _resolve(root, schema["$ref"]), root, path, errors)
        return
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(value, n) for n in names):
            errors.append(f"{path}: expected {'|'.join(names)}, got {type(value).__name__}")
            return
    if "enum" in schema and not any(value == e and type(value) is type(e) for e in schema["enum"]):
        errors.append(f"{path}: {value!r} not in {schema['enum']!r}")
    if isinstance(value, str) and "pattern" in schema and not re.fullmatch(schema["pattern"], value):
        errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if _type_ok(value, "integer") and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: {value} is less than {schema['minimum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required '{key}'")
        extra = schema.get("additionalProperties")
        for key, child in value.items():
            if key in props:
                _check(child, props[key], root, f"{path}.{key}", errors)
            elif extra is False:
                errors.append(f"{path}: unexpected property '{key}'")
            elif isinstance(extra, dict):
                _check(child, extra, root, f"{path}.{key}", errors)
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _check(item, schema["items"], root, f"{path}[{i}]", errors)
