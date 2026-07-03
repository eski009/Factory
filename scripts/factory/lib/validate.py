"""Deliberate draft-07 subset validator (stdlib only, no $ref/oneOf).

Returns a list of error strings; empty list means valid.
"""

import re

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


def validate(instance, schema, path="$"):
    errors = []
    expected = schema.get("type")
    if expected and not _TYPE_CHECKS[expected](instance):
        return [f"{path}: expected {expected}"]
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not one of {schema['enum']}")
    if expected == "object":
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}.{key}: required property missing")
        for key, sub in props.items():
            if key in instance:
                errors.extend(validate(instance[key], sub, f"{path}.{key}"))
        if schema.get("additionalProperties") is False:
            for key in sorted(set(instance) - set(props)):
                errors.append(f"{path}.{key}: unexpected property")
    elif expected == "array" and "items" in schema:
        for i, value in enumerate(instance):
            errors.extend(validate(value, schema["items"], f"{path}[{i}]"))
    elif expected == "string":
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match {schema['pattern']}")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
    elif expected in ("integer", "number") and "minimum" in schema:
        if instance < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
    return errors
